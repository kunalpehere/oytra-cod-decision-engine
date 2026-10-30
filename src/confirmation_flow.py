"""Local, transactional confirmation/prepaid state machine. Never sends real messages."""

import hashlib
import json
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from src.analysis import money, number
from src.data_pipeline import ROOT
from src.decision_engine import ACTIONS, input_issues, normalize_order
from src.flow_messages import TEMPLATES, intent, message
from src.reply_details import parse_detail_reply,valid_detail_value,address_has_delivery_details

ACTIVE = {'awaiting_confirmation','awaiting_payment','awaiting_details'}
READY = {'ready_to_ship_cod','ready_to_ship_prepaid'}
IST = timezone(timedelta(hours=5,minutes=30))


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)


def load_flow_config(path=ROOT/'config/confirmation_flow.json'):
    config=json.loads(Path(path).read_text(encoding='utf-8'))
    validate_config(config)
    return config


def validate_config(config):
    if config.get('schema_version')!=1:
        raise ValueError('Unsupported conversation config version.')
    for field in ('reminder_hours','payment_expiry_hours','timeout_hours'):
        value=number(config.get(field))
        if type(config.get(field)) not in (int,float) or value is None or not 0<value<=24:
            raise ValueError(f'{field} must be a positive number no greater than 24.')
        if value*3600!=(value*3600).to_integral_value():
            raise ValueError('Timer settings require whole seconds.')
    if config['timeout_hours']!=24 or config['reminder_hours']>=24 or config['payment_expiry_hours']>24:
        raise ValueError('The response deadline is 24 hours; reminders must be earlier.')
    if type(config.get('max_unclear_replies')) is not int or not 1<=config['max_unclear_replies']<=5:
        raise ValueError('Unclear-reply limit must be an integer from 1 to 5.')
    if config.get('default_language') not in TEMPLATES:
        raise ValueError('Unsupported default language.')


def timestamp(value):
    dt=datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError('Simulation start must include an explicit UTC offset.')
    return int(dt.timestamp())


def display_time(seconds):
    return datetime.fromtimestamp(seconds,IST).strftime('%Y-%m-%d %H:%M:%S IST')


class FlowStore:
    def __init__(self,path=ROOT/'data/simulator/conversations.sqlite',config=None,start=None):
        self.path=Path(path)
        self.config=dict(load_flow_config() if config is None else config)
        validate_config(self.config)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY,data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS audit (seq INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, at INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS messages (seq INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, at INTEGER NOT NULL, direction TEXT NOT NULL, text TEXT NOT NULL, template TEXT NOT NULL)')
            initial=timestamp(start) if start else int(datetime.now(timezone.utc).timestamp())
            db.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)',('clock',str(initial)))

    @contextmanager
    def transaction(self):
        with closing(sqlite3.connect(self.path,timeout=5)) as db:
            db.execute('BEGIN IMMEDIATE')
            with db:
                yield db

    def _now(self,db):
        return int(db.execute('SELECT value FROM metadata WHERE key=?',('clock',)).fetchone()[0])

    def _get(self,db,conversation_id):
        row=db.execute('SELECT data FROM conversations WHERE id=?',(conversation_id,)).fetchone()
        if not row:
            raise ValueError('Unknown conversation.')
        return json.loads(row[0])

    def _audit(self,db,c,at,kind,payload):
        db.execute('INSERT INTO audit (conversation_id,at,kind,payload) VALUES (?,?,?,?)',(c['id'],at,kind,canonical(payload)))

    def _save(self,db,c,at,previous,reason):
        db.execute('UPDATE conversations SET data=? WHERE id=?',(canonical(c),c['id']))
        if previous!=c['state']:
            self._audit(db,c,at,'state_changed',dict(previous=previous,state=c['state'],reason=reason))

    def _send(self,db,c,at,key,**extra):
        values=dict(order_id=c['id'],value=c['order']['order_value'],discount=c['discount'],payable=c['payable'],
                    link=c['payment_link'],deadline=display_time(c['deadline']))
        values.update(extra)
        text=message(c['language'],key,**values)
        db.execute('INSERT INTO messages (conversation_id,at,direction,text,template) VALUES (?,?,?,?,?)',(c['id'],at,'outgoing_mock',text,key))

    def _receipt(self,db,event_id,conversation_id,kind,payload):
        if not isinstance(event_id,str) or not 1<=len(event_id)<=160:
            raise ValueError('A unique event ID of 1-160 characters is required.')
        fingerprint=hashlib.sha256(canonical([conversation_id,kind,payload]).encode()).hexdigest()
        existing=db.execute('SELECT fingerprint FROM receipts WHERE id=?',(event_id,)).fetchone()
        if existing:
            if existing[0]!=fingerprint:
                raise ValueError('Event ID was already used with a different payload.')
            return False
        db.execute('INSERT INTO receipts VALUES (?,?)',(event_id,fingerprint))
        return True

    def start(self,order,decision,language=None):
        validate_config(self.config)
        order=normalize_order(order)
        if not order['order_id'] or decision.get('order_id')!=order['order_id'] or decision.get('action') not in ACTIONS:
            raise ValueError('A matching order and Phase 3 recommendation are required.')
        if language is not None and language not in TEMPLATES:
            raise ValueError('Choose English, Hindi or Hinglish.')
        language=language or self.config['default_language']
        source=dict(order=order,decision=decision,language=language,config=self.config)
        fingerprint=hashlib.sha256(canonical(source).encode()).hexdigest()
        with self.transaction() as db:
            now=self._now(db)
            existing=db.execute('SELECT data FROM conversations WHERE id=?',(order['order_id'],)).fetchone()
            if existing:
                if json.loads(existing[0])['creation_fingerprint']!=fingerprint:
                    raise ValueError('This order already has a different conversation; resume it without resetting its deadline.')
                return self._snapshot(db,order['order_id'])
            value=number(order['order_value'])
            discount=number(decision.get('prepaid_discount_inr','0'))
            if decision['action']=='nudge_to_prepaid' and (value is None or discount is None or not 0<discount<value):
                raise ValueError('Prepaid requires a positive discount below the order value.')
            discount=discount if decision['action']=='nudge_to_prepaid' else Decimal(0)
            review=decision.get('address_review',{})
            payment_id='MOCK-'+hashlib.sha256(f'{order["order_id"]}:{now}'.encode()).hexdigest()[:16]
            c=dict(id=order['order_id'],order=order,decision=decision,language=language,config=self.config,
                   creation_fingerprint=fingerprint,created_at=now,deadline=now+86400,
                   reminder_at=now+int(Decimal(str(self.config['reminder_hours']))*3600),reminder_sent=False,
                   payment_expires_at=now+int(Decimal(str(self.config['payment_expiry_hours']))*3600),
                   payment_id=payment_id,payment_link=f'mock://payment/{payment_id}',
                   payment_status='pending' if decision['action']=='nudge_to_prepaid' else 'not_offered',
                   payment_review_required=False,refund_review_required=False,
                   discount=money(discount),payable=money(value-discount) if value is not None and value>0 else '',
                   needs_address=review.get('address_quality')!='complete',
                   needs_name=review.get('name_quality') in (None,'placeholder','unknown'),
                   customer_confirmed=False,unclear_replies=0,mode='prepaid' if decision['action']=='nudge_to_prepaid' else 'COD',
                   state='awaiting_payment' if decision['action']=='nudge_to_prepaid' else 'awaiting_confirmation')
            problems=input_issues(order)
            if decision['action']=='hold_cancel' or problems:
                c['state']='held_for_review'
                c['payment_status']='not_offered'
            elif decision['action']=='ship_as_is':
                # Never let a malformed supplied recommendation bypass outstanding details.
                c['state']='awaiting_confirmation' if c['needs_address'] or c['needs_name'] else 'ready_to_ship_cod'
            db.execute('INSERT INTO conversations VALUES (?,?)',(c['id'],canonical(c)))
            self._audit(db,c,now,'conversation_started',dict(action=decision['action'],state=c['state'],language=language,
                                                          input_issues=problems,simulation_only=True))
            if c['state'] in ACTIVE:
                self._send(db,c,now,'prepaid' if c['mode']=='prepaid' else 'confirm')
                if c['needs_address'] or c['needs_name']:
                    self._send(db,c,now,'details',details=self._details(c))
            return self._snapshot(db,c['id'])

    def _details(self,c):
        labels={'English':('full delivery address','recipient name'),
                'Hindi':('पूरा डिलीवरी पता','प्राप्तकर्ता का नाम'),
                'Hinglish':('poora delivery address','recipient ka naam')}
        a,n=labels[c['language']]
        return ', '.join(([a] if c['needs_address'] else [])+([n] if c['needs_name'] else []))

    def _fallback(self,db,c,at,cause):
        c.update(mode='COD',customer_confirmed=False,state='awaiting_confirmation')
        if c['payment_status']=='pending':
            c['payment_status']='expired' if cause=='expired' else 'closed'
        self._send(db,c,at,'cod_fallback',cause=cause)

    def _release(self,db,c,at):
        if c['needs_address'] or c['needs_name']:
            c['state']='awaiting_details'
            self._send(db,c,at,'details',details=self._details(c))
        elif c['mode']=='prepaid' and c['payment_status']!='verified':
            c['state']='awaiting_payment'
            self._send(db,c,at,'pending_payment')
        elif c['customer_confirmed']:
            c['state']='ready_to_ship_prepaid' if c['payment_status']=='verified' else 'ready_to_ship_cod'
            self._send(db,c,at,'ready_prepaid' if c['state']=='ready_to_ship_prepaid' else 'ready_cod')

    def _tick(self,db,until):
        due=[]
        for row in db.execute('SELECT data FROM conversations ORDER BY id').fetchall():
            c=json.loads(row[0])
            if c['state'] not in ACTIVE:
                continue
            if not c['reminder_sent'] and c['reminder_at']<=until:
                due.append((c['reminder_at'],2,c['id'],'reminder'))
            if c['payment_status']=='pending' and c['payment_expires_at']<=until:
                due.append((c['payment_expires_at'],1,c['id'],'payment_expired'))
            if c['deadline']<=until:
                due.append((c['deadline'],0,c['id'],'timeout'))
        for at,_,identifier,kind in sorted(due):
            c=self._get(db,identifier)
            if c['state'] not in ACTIVE:
                continue
            previous=c['state']
            if kind=='timeout':
                c['state']='held_for_review'
                if c['payment_status']=='pending':
                    c['payment_status']='expired'
                self._send(db,c,at,'timeout')
            elif kind=='payment_expired' and c['payment_status']=='pending':
                self._fallback(db,c,at,'expired')
            elif kind=='reminder' and not c['reminder_sent']:
                c['reminder_sent']=True
                self._send(db,c,at,'reminder')
            else:
                continue
            self._audit(db,c,at,kind,dict(deadline_unchanged=True))
            self._save(db,c,at,previous,kind)

    def advance(self,hours,event_id):
        value=number(hours)
        if isinstance(hours,bool) or value is None or value<=0 or value>8760 or value*3600!=(value*3600).to_integral_value():
            raise ValueError('Advance must be positive, whole-second precision, and at most one year.')
        with self.transaction() as db:
            if self._receipt(db,event_id,'__clock__','advance',{'hours':str(value)}):
                now=self._now(db)+int(value*3600)
                self._tick(db,now)
                db.execute('UPDATE metadata SET value=? WHERE key=?',(str(now),'clock'))
            return dict(now=self._now(db),display_time=display_time(self._now(db)))

    def reply(self,conversation_id,text,event_id):
        if not isinstance(text,str) or not 1<=len(text.strip())<=2000:
            raise ValueError('Reply must contain 1-2000 characters.')
        text=text.strip()
        with self.transaction() as db:
            now=self._now(db)
            self._tick(db,now)
            c=self._get(db,conversation_id)
            if not self._receipt(db,event_id,conversation_id,'reply',{'text':text}):
                return self._snapshot(db,conversation_id)
            previous=c['state']
            db.execute('INSERT INTO messages (conversation_id,at,direction,text,template) VALUES (?,?,?,?,?)',(conversation_id,now,'customer_mock',text,''))
            parsed=intent(text)
            details=None
            detail_error=False
            if c['state'] in ACTIVE:
                try:
                    details=parse_detail_reply(text)
                except ValueError:
                    detail_error=True
            self._audit(db,c,now,'customer_reply',dict(text=text,intent=parsed))
            if c['state'] in READY and parsed=='no':
                c['state']='cancelled'
                c['refund_review_required']=c['payment_status']=='verified'
                self._send(db,c,now,'cancel_after_payment' if c['refund_review_required'] else 'cancelled')
            elif c['state'] not in ACTIVE:
                self._send(db,c,now,'late_reply')
            elif parsed=='no':
                c['state']='cancelled'
                c['refund_review_required']=c['payment_status']=='verified'
                if c['payment_status']=='pending':
                    c['payment_status']='closed'
                self._send(db,c,now,'cancel_after_payment' if c['refund_review_required'] else 'cancelled')
            elif detail_error:
                self._audit(db,c,now,'detail_format_requested',dict(reason='Missing quotes, incomplete or ambiguous labeled values.'))
                self._send(db,c,now,'detail_format')
            elif details:
                self._correct(db,c,now,details)
            elif parsed=='paid_claim':
                self._send(db,c,now,'paid_claim')
            elif parsed=='cod':
                if c['payment_status']=='verified':
                    self._send(db,c,now,'already_prepaid')
                elif c['mode']=='prepaid':
                    self._fallback(db,c,now,'customer chose COD')
                else:
                    self._send(db,c,now,'confirm')
            elif parsed=='yes':
                c['customer_confirmed']=True
                self._release(db,c,now)
            else:
                c['unclear_replies']+=1
                if c['unclear_replies']>=c['config']['max_unclear_replies']:
                    c['state']='held_for_review'
                    self._send(db,c,now,'unclear_hold')
                else:
                    self._send(db,c,now,'clarify')
            self._save(db,c,now,previous,'customer_reply')
            return self._snapshot(db,conversation_id)

    def _correct(self,db,c,at,fields):
        # Validate the whole message before changing either field.
        if any(not valid_detail_value(field,value) for field,value in fields.items()):
            self._send(db,c,at,'invalid_details')
            self._audit(db,c,at,'correction_rejected',dict(fields=sorted(fields)))
            return
        captured=[]
        names={'English':{'name':'name','address':'address'},'Hindi':{'name':'नाम','address':'पता'},'Hinglish':{'name':'name','address':'address'}}
        for field,value in fields.items():
            key='address' if field=='address' else 'customer_name'
            old=c['order'][key]
            c['order'][key]=value
            complete=address_has_delivery_details(value) if field=='address' else True
            c['needs_address' if field=='address' else 'needs_name']=not complete
            captured.append(f'{names[c["language"]][field]} "{value}"')
            self._audit(db,c,at,'customer_corrected_details',dict(field=key,before=old,after=value,
                                                               verified_by='customer_supplied_format_check_only',delivery_details_complete=complete))
        c['customer_confirmed']=False
        c['state']='awaiting_details' if c['needs_address'] or c['needs_name'] else 'awaiting_confirmation'
        next_step=message(c['language'],'next_details',details=self._details(c)) if c['needs_address'] or c['needs_name'] else message(c['language'],'next_confirm')
        self._send(db,c,at,'details_saved',captured=', '.join(captured),next_step=next_step)

    def mock_payment(self,conversation_id,status,event_id,payment_id=None,amount=None):
        if status not in ('success','failed','expired'):
            raise ValueError('Mock payment status must be success, failed or expired.')
        with self.transaction() as db:
            now=self._now(db)
            self._tick(db,now)
            c=self._get(db,conversation_id)
            payment_id=c['payment_id'] if payment_id is None else payment_id
            amount=c['payable'] if amount is None else str(amount)
            if not self._receipt(db,event_id,conversation_id,'mock_payment',dict(status=status,payment_id=payment_id,amount=amount)):
                return self._snapshot(db,conversation_id)
            previous=c['state']
            self._audit(db,c,now,'mock_payment_event',dict(status=status,payment_id=payment_id,amount=amount,simulation_only=True))
            if c['payment_status']=='not_offered' or payment_id!=c['payment_id']:
                self._audit(db,c,now,'payment_rejected',dict(reason='No matching mock payment intent.'))
            elif c['payment_status']=='verified':
                self._audit(db,c,now,'duplicate_payment_status_ignored',dict(status=status))
            elif status=='success':
                matching=number(amount) is not None and number(amount)==number(c['payable'])
                if not matching or c['state'] not in ACTIVE or c['mode']!='prepaid' or c['payment_status']!='pending' or now>=c['payment_expires_at']:
                    c['payment_review_required']=True
                    c['refund_review_required']=True
                    if c['state']!='cancelled':
                        c['state']='held_for_review'
                    c['payment_status']='late_or_mismatched_success'
                    self._send(db,c,now,'payment_review')
                else:
                    c.update(payment_status='verified',customer_confirmed=True)
                    self._release(db,c,now)
            elif c['payment_status']=='pending' and c['state'] in ACTIVE:
                c['payment_status']='failed' if status=='failed' else 'expired'
                self._fallback(db,c,now,status)
            else:
                self._audit(db,c,now,'stale_payment_status_ignored',dict(status=status))
            self._save(db,c,now,previous,'mock_payment')
            return self._snapshot(db,conversation_id)

    def _snapshot(self,db,conversation_id):
        c=self._get(db,conversation_id)
        now=self._now(db)
        c.update(now=now,display_time=display_time(now),deadline_display=display_time(c['deadline']),
                 can_ship=c['state'] in READY,simulation_only=True)
        c['messages']=[dict(seq=row[0],at=row[1],time=display_time(row[1]),direction=row[2],text=row[3],template=row[4])
                       for row in db.execute('SELECT seq,at,direction,text,template FROM messages WHERE conversation_id=? ORDER BY seq',(conversation_id,))]
        c['audit']=[dict(seq=row[0],at=row[1],time=display_time(row[1]),kind=row[2],payload=json.loads(row[3]))
                    for row in db.execute('SELECT seq,at,kind,payload FROM audit WHERE conversation_id=? ORDER BY seq',(conversation_id,))]
        return c

    def snapshot(self,conversation_id):
        with closing(sqlite3.connect(self.path)) as db:
            return self._snapshot(db,conversation_id)

    def list_conversations(self):
        with closing(sqlite3.connect(self.path)) as db:
            return [dict(id=c['id'],state=c['state'],language=c['language']) for c in
                    (json.loads(r[0]) for r in db.execute('SELECT data FROM conversations ORDER BY id'))]

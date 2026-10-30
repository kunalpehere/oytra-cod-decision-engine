"""Read-only daily dashboard views and reconciled hypothetical financial rollups."""

import copy
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from src.address_review import AddressReviewer
from src.analysis import money, number, split_for, valid_value
from src.chat_simulator import load_engine
from src.confirmation_flow import IST
from src.data_pipeline import ROOT, COLUMNS, EXTRA_COLUMNS
from src.decision_engine import ACTIONS, decide, economics, normalize_order, validate_policy
from src.risk import predict
from src.train_engine import canonical_hash

LABELS = dict(ship_as_is='Ship as-is',ship_after_confirmation='Confirm first',
              nudge_to_prepaid='Nudge to prepaid',hold_cancel='Hold / cancel')
BRIDGE = (
    'avoided_rto_loss','new_prepaid_delivery_contribution','negative_held_margin_avoided',
    'genuine_held_margin_at_risk','missed_genuine_delivery_contribution',
    'new_prepaid_rto_loss','discount_cost','payment_fee','message_cost',
)
POSITIVE = {'avoided_rto_loss','new_prepaid_delivery_contribution','negative_held_margin_avoided'}
FINANCIAL_FIELDS = ('forward_shipping','return_shipping','packaging_handling','average_product_cost',
                    'returned_damage_probability','delivered_gross_margin','brief_prepaid_rto_rate')
POLICY_FIELDS = (
    'confirm_risk_threshold','prepaid_risk_threshold','hold_risk_threshold','minimum_expected_contribution',
    'prepaid_discount_inr','maximum_discount_fraction','genuine_confirmation_rate','rto_confirmation_rate',
    'genuine_prepaid_uptake','rto_prepaid_uptake','confirmation_message_cost_inr',
    'prepaid_message_cost_inr','prepaid_payment_fee_fraction',
)


def settings(artifact):
    return dict(policy=copy.deepcopy(artifact['policy']),
                financial_assumptions={key:Decimal(value) for key,value in artifact['financial_assumptions'].items()})


def validate_settings(value):
    validate_policy(value['policy'])
    for field in FINANCIAL_FIELDS:
        n=number(value['financial_assumptions'].get(field))
        if isinstance(value['financial_assumptions'].get(field),bool) or n is None or n<0:
            raise ValueError(f'{field} must be a finite nonnegative number.')
        if field in ('returned_damage_probability','delivered_gross_margin','brief_prepaid_rto_rate') and n>1:
            raise ValueError(f'{field} must be between 0 and 1.')
        if n>Decimal('10000000'):
            raise ValueError(f'{field} exceeds the supported input limit of 10000000.')
    if any(Decimal(str(value['policy'][key]))>Decimal('10000000') for key in POLICY_FIELDS):
        raise ValueError('Scenario policy amounts exceed the supported input limit of 10000000.')
    return value


def scenario_payload(value):
    return dict(policy=value['policy'],financial_assumptions={k:str(v) for k,v in value['financial_assumptions'].items()})


def yesterday_ist(now=None):
    now=now or datetime.now(IST)
    if now.tzinfo is None:
        raise ValueError('The reporting clock must have a timezone.')
    return (now.astimezone(IST).date()-timedelta(days=1)).isoformat()


def check_day(value):
    if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:
        raise ValueError('Select a date in YYYY-MM-DD format.')
    return value


def financial_components(order,action,risk,policy,assumptions):
    """Conditional historical counterfactual bridge, using the same Phase 3 economics.

    Positive components add contribution; costs/losses subtract. Historical COD
    labels are observed; every confirmation/prepaid outcome is an assumption.
    """
    if order.get('final_status') not in ('DELIVERED','RTO') or valid_value(order) is None:
        return None
    if action not in ACTIONS:
        raise ValueError('Unknown initial recommendation.')
    e=economics(order,risk,policy,assumptions)
    returned=order['final_status']=='RTO'
    key='rto' if returned else 'genuine'
    out={field:Decimal(0) for field in BRIDGE}
    q=Decimal(str(policy['rto_confirmation_rate' if returned else 'genuine_confirmation_rate']))
    u=Decimal(str(policy['rto_prepaid_uptake' if returned else 'genuine_prepaid_uptake']))
    r=assumptions['brief_prepaid_rto_rate']
    m,loss=e['margin'],e['unit_loss']
    if action=='hold_cancel':
        if returned:
            out['avoided_rto_loss']=loss
        else:
            out['genuine_held_margin_at_risk']=max(Decimal(0),m)
            out['negative_held_margin_avoided']=max(Decimal(0),-m)
    elif action=='ship_after_confirmation':
        if returned:
            out['avoided_rto_loss']=(1-q)*loss
        else:
            out['missed_genuine_delivery_contribution']=(1-q)*m
        out['message_cost']=Decimal(str(policy['confirmation_message_cost_inr']))
    elif action=='nudge_to_prepaid':
        if returned:
            out['avoided_rto_loss']=(1-(1-u)*q-u*r)*loss
            out['new_prepaid_delivery_contribution']=u*(1-r)*m
        else:
            out['missed_genuine_delivery_contribution']=(1-(1-u)*q-u*(1-r))*m
            out['new_prepaid_rto_loss']=u*r*loss
        out['discount_cost']=u*(1-r)*e['discount']
        out['payment_fee']=u*(1-r)*(Decimal(order['order_value'])-e['discount'])*Decimal(str(policy['prepaid_payment_fee_fraction']))
        out['message_cost']=Decimal(str(policy['prepaid_message_cost_inr']))+(1-u)*Decimal(str(policy['confirmation_message_cost_inr']))
    out['baseline_contribution']=e['conditional']['ship_as_is'][key]
    out['policy_contribution']=e['conditional'][action][key]
    out['net_impact']=out['policy_contribution']-out['baseline_contribution']
    bridge=sum((out[k] if k in POSITIVE else -out[k] for k in BRIDGE),Decimal(0))
    if abs(bridge-out['net_impact'])>Decimal('.000001'):
        raise ValueError('Financial contribution bridge did not reconcile.')
    return out


class DashboardData:
    def __init__(self,input_path=ROOT/'data/processed/orders_clean.csv',
                 artifact_path=ROOT/'artifacts/decision_engine.json',
                 simulator_path=ROOT/'data/simulator/conversations.sqlite'):
        self.input_path,self.simulator_path=Path(input_path),Path(simulator_path)
        self.artifact=load_engine(artifact_path)
        self.frozen=settings(self.artifact)
        self.frozen_september_impact=None
        evaluation_path=ROOT/'reports/engine/summary.json'
        if evaluation_path.exists():
            evaluation=json.loads(evaluation_path.read_text(encoding='utf-8'))
            if (evaluation.get('freeze_sha256')==self.artifact['freeze_sha256'] and
                    evaluation.get('input_sha256')==hashlib.sha256(self.input_path.read_bytes()).hexdigest()):
                self.frozen_september_impact=evaluation['performance']['evaluation']['net_impact_inr']
        with self.input_path.open(encoding='utf-8',newline='') as f:
            reader=csv.DictReader(f)
            if reader.fieldnames!=list(COLUMNS+EXTRA_COLUMNS):
                raise ValueError('Dashboard requires the Phase 1 cleaned schema.')
            self.raw=list(reader)
        if not self.raw or any(None in r or any(v is None for v in r.values()) for r in self.raw):
            raise ValueError('Historical data is empty or malformed.')
        if len({r['source_row'] for r in self.raw})!=len(self.raw):
            raise ValueError('Duplicate source record IDs in cleaned input.')
        ids=Counter(r['order_id'] for r in self.raw)
        self.rows=[]
        self.excluded=Counter()
        for row in self.raw:
            if not row['order_id'] or ids[row['order_id']]!=1 or row['payment_method']!='COD' or 'conflicting_order_id' in row['quality_flags'].split('|'):
                self.excluded['ambiguous_id_or_non_cod']+=1
                continue
            try:
                dt=datetime.strptime(row['order_datetime'],'%Y-%m-%d %H:%M')
                if dt.strftime('%Y-%m-%d %H:%M')!=row['order_datetime']:
                    raise ValueError('Date format')
            except ValueError:
                self.excluded['invalid_date']+=1
                continue
            self.rows.append(row)

    def simulator_rows(self):
        """Read-only snapshot: never create a DB, initialize a clock or send an event."""
        if not self.simulator_path.exists():
            return []
        try:
            uri=self.simulator_path.resolve().as_uri()+'?mode=ro'
            with closing(sqlite3.connect(uri,uri=True,timeout=2)) as db:
                rows=db.execute('SELECT id,data FROM conversations ORDER BY id').fetchall()
            result=[]
            for identifier,data in rows:
                c=json.loads(data)
                if c.get('id')!=identifier or c.get('decision',{}).get('action') not in ACTIONS:
                    raise ValueError('Invalid simulator conversation record.')
                datetime.fromtimestamp(c['created_at'],IST)
                result.append(c)
            return result
        except (sqlite3.Error,KeyError,TypeError,ValueError) as error:
            raise ValueError('Simulator data could not be read. Check its path and schema; no empty-data result was substituted.') from error

    def dates(self,source='historical'):
        if source=='historical':
            return sorted({r['order_datetime'][:10] for r in self.rows})
        if source!='simulator':
            raise ValueError('Unknown dashboard source.')
        return sorted({datetime.fromtimestamp(c['created_at'],IST).date().isoformat() for c in self.simulator_rows()})

    def default_day(self,source='historical',now=None):
        requested=yesterday_ist(now)
        available=self.dates(source)
        selected=requested if requested in available or not available else available[-1]
        return dict(requested_yesterday=requested,selected_day=selected,fell_back_to_latest=(selected!=requested))

    def daily(self,day,source='historical',scenario=None):
        check_day(day)
        applied=validate_settings(copy.deepcopy(scenario if scenario is not None else self.frozen))
        config=scenario_payload(applied)
        frozen_config=scenario_payload(self.frozen)
        is_frozen=config==frozen_config
        result=dict(day=day,source=source,timezone='Asia/Kolkata',scenario='Frozen policy' if is_frozen else 'Exploratory what-if',
                    frozen_artifact_sha256=self.artifact['freeze_sha256'],scenario_sha256=canonical_hash(config),settings=config,
                    frozen_september_impact=self.frozen_september_impact,
                    counts={a:0 for a in ACTIONS},orders=[],money=None,sensitivity=[],
                    exclusions=dict(self.excluded),simulator_states={},simulation_only=(source=='simulator'))
        if source=='simulator':
            if not is_frozen:
                raise ValueError('What-if settings apply to historical replay only; simulator decisions are immutable initial snapshots.')
            conversations=[c for c in self.simulator_rows() if datetime.fromtimestamp(c['created_at'],IST).date().isoformat()==day]
            result['scenario']='Stored simulator recommendations'
            result['simulator_recommendation_artifacts']=sorted({c['decision'].get('frozen_artifact_sha256','unrecorded') for c in conversations})
            for c in conversations:
                action=c['decision']['action']
                result['counts'][action]+=1
                result['orders'].append(dict(order_id=c['id'],initial_action=action,risk_probability=c['decision'].get('risk_probability'),
                                             historical_outcome='',current_state=c['state'],payment_status=c['payment_status'],
                                             reason=c['decision']['reason'],baseline_contribution='',policy_contribution='',net_impact='',
                                             details=c,financial_exclusion='No observed delivery/RTO outcome; simulator totals are not realised profit.'))
            result['simulator_states']=dict(sorted(Counter(c['state'] for c in conversations).items()))
            result['mock_money']=dict(verified_payment_face_value=money(sum((Decimal(c['payable']) for c in conversations if c['payment_status']=='verified'),Decimal(0))),
                                      explicit_cancellations=sum(c['state']=='cancelled' for c in conversations),
                                      review_holds=sum(c['state']=='held_for_review' for c in conversations),
                                      payment_review_orders=sum(bool(c['payment_review_required']) for c in conversations),
                                      refund_review_orders=sum(bool(c['refund_review_required']) for c in conversations))
            result['note']='Initial recommendation counts; current states listed separately. No final delivery outcomes, so financial impact is unavailable. Mock payments are face value, not revenue or profit.'
        elif source=='historical':
            selected=[r for r in self.rows if r['order_datetime'][:10]==day]
            totals={k:Decimal(0) for k in BRIDGE+('baseline_contribution','policy_contribution','net_impact')}
            financial_exclusions=Counter()
            fixed=[]
            for row in selected:
                decision=decide(row,self.artifact['model'],applied['policy'],applied['financial_assumptions'],AddressReviewer('offline'))
                action=decision['action']
                result['counts'][action]+=1
                p=predict(self.artifact['model'],normalize_order(row))
                components=financial_components(row,action,p,applied['policy'],applied['financial_assumptions'])
                exclusion=''
                if components is None:
                    exclusion='unresolved_outcome' if row['final_status'] not in ('RTO','DELIVERED') else 'invalid_order_value'
                    financial_exclusions[exclusion]+=1
                else:
                    for k,v in components.items():
                        totals[k]+=v
                    fixed.append((row,action,p))
                result['orders'].append(dict(order_id=row['order_id'],initial_action=action,risk_probability=decision['risk_probability'],
                                             historical_outcome=row['final_status'],current_state='historical_replay',payment_status='not_observed',
                                             reason=decision['reason'],**{k:money(components[k]) if components else '' for k in ('baseline_contribution','policy_contribution','net_impact')},
                                             details=dict(order=row,decision=decision,financial_components={k:money(v) for k,v in components.items()} if components else None),
                                             financial_exclusion=exclusion))
            result['financial_orders']=len(fixed)
            result['financial_exclusions']=dict(financial_exclusions)
            result['money']={k:money(v) for k,v in totals.items()} if fixed else None
            if fixed:
                result['sensitivity']=self._sensitivity(fixed,applied)
            period=split_for(day+' 12:00')
            result['note']=f'Retrospective {period} replay using offline address heuristics. April-July is in-sample; August selected settings; September was reserved for evaluation but previously inspected in aggregate. Intervention responses and profit impacts remain hypothetical. Historical timestamps are assumed IST for day grouping; the file gives no timezone.'
        else:
            raise ValueError('Unknown dashboard source.')
        result['order_count']=len(result['orders'])
        result['data_sha256']=canonical_hash(result['orders'])
        return result

    def _sensitivity(self,fixed,applied):
        rows=[]
        changes=(('Current assumptions',{}),('Weaker responses',dict(genuine_confirmation_rate=.75,rto_confirmation_rate=.60,genuine_prepaid_uptake=.15,rto_prepaid_uptake=.05)),
                 ('No prepaid uptake',dict(genuine_prepaid_uptake=0,rto_prepaid_uptake=0)),
                 ('No response discrimination',dict(genuine_confirmation_rate=.90,rto_confirmation_rate=.90,genuine_prepaid_uptake=0,rto_prepaid_uptake=0)))
        for label,change in changes:
            policy=dict(applied['policy'],**change)
            total=Decimal(0)
            for row,action,p in fixed:
                total+=financial_components(row,action,p,policy,applied['financial_assumptions'])['net_impact']
            rows.append(dict(scenario=label,net_impact=money(total),decisions='Fixed current assignments; responses vary only'))
        return rows


def export_daily(view,output_root=ROOT/'reports/dashboard/exports'):
    directory=Path(output_root)/f"{view['source']}-{view['day']}-{view['scenario_sha256'][:8]}-{view['data_sha256'][:8]}"
    directory.mkdir(parents=True,exist_ok=True)
    columns=('order_id','initial_action','risk_probability','historical_outcome','current_state','payment_status','reason',
             'baseline_contribution','policy_contribution','net_impact','financial_exclusion')
    def safe(value):
        if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) and number(value) is None:
            return "'"+value
        return value
    def write(path,fields,rows):
        with path.open('w',encoding='utf-8-sig',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=fields,lineterminator='\n')
            writer.writeheader()
            writer.writerows({k:safe(r.get(k,'')) for k in fields} for r in rows)
    write(directory/'orders.csv',columns,view['orders'])
    summary=[dict(metric='order_count',value=view['order_count'])]
    summary.extend(dict(metric=k,value=v) for k,v in view['counts'].items())
    summary.extend(dict(metric=k,value=v) for k,v in (view['money'] or {}).items())
    if view['money'] is None:
        summary.append(dict(metric='financial_impact',value='unavailable'))
    write(directory/'summary.csv',('metric','value'),summary)
    write(directory/'sensitivity.csv',('scenario','net_impact','decisions'),view['sensitivity'])
    # No customer names, phones or addresses are included in the flat export.
    metadata={k:v for k,v in view.items() if k!='orders'}
    (directory/'context.json').write_text(json.dumps(metadata,indent=2,sort_keys=True,ensure_ascii=False)+'\n',encoding='utf-8')
    return directory

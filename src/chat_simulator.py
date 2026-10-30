"""Desktop-only chat and mock payment simulator. No browser/server/account needed."""

import argparse
import hashlib
import json
import uuid
from decimal import Decimal
from pathlib import Path

from src.address_review import AddressReviewer
from src.confirmation_flow import FlowStore, load_flow_config, validate_config
from src.data_pipeline import ROOT
from src.decision_engine import decide, validate_policy


def load_engine(path=ROOT/'artifacts/decision_engine.json'):
    artifact=json.loads(Path(path).read_text(encoding='utf-8'))
    content={key:value for key,value in artifact.items() if key!='freeze_sha256'}
    digest=hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if digest!=artifact['freeze_sha256']:
        raise ValueError('Phase 3 artifact integrity check failed.')
    validate_policy(artifact['policy'])
    return artifact


def score_order(order,artifact):
    result=decide(order,artifact['model'],artifact['policy'],
                  {key:Decimal(value) for key,value in artifact['financial_assumptions'].items()},AddressReviewer('offline'))
    return dict(result,frozen_artifact_sha256=artifact['freeze_sha256'])


class SimulatorWindow:
    def __init__(self,root,store,artifact):
        import tkinter as tk
        from tkinter import ttk
        from tkinter.scrolledtext import ScrolledText
        self.root,self.store,self.artifact=root,store,artifact
        self.examples=json.loads((ROOT/'examples/orders.json').read_text(encoding='utf-8'))
        self.orders={o['order_id']:o for o in self.examples}
        self.current=None
        root.title('COD conversation simulator - local demo')
        root.geometry('1180x820')
        root.minsize(980,700)
        style=ttk.Style(root)
        style.theme_use('clam')
        style.configure('.',font=('Segoe UI',10))
        style.configure('Title.TLabel',font=('Segoe UI',19,'bold'))
        style.configure('State.TLabel',font=('Segoe UI',11,'bold'),foreground='#126473')
        outer=ttk.Frame(root,padding=18)
        outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='Order confirmation lab',style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer,text='LOCAL SIMULATION  |  No WhatsApp, real messages, payments or API calls',foreground='#54616f').pack(anchor='w',pady=(2,14))
        setup=ttk.LabelFrame(outer,text='Start from a Phase 3 recommendation',padding=10)
        setup.pack(fill='x')
        self.example=tk.StringVar(value=self.examples[1]['order_id'])
        self.language=tk.StringVar(value='Hinglish')
        ttk.Combobox(setup,textvariable=self.example,values=list(self.orders),state='readonly',width=27).grid(row=0,column=0,padx=4,pady=4)
        ttk.Combobox(setup,textvariable=self.language,values=['English','Hindi','Hinglish'],state='readonly',width=12).grid(row=0,column=1,padx=4)
        ttk.Button(setup,text='Start / resume order',command=lambda:self.run(self.start)).grid(row=0,column=2,padx=8)
        ttk.Label(setup,text='New conversations only:').grid(row=1,column=0,sticky='e',padx=4)
        self.reminder=tk.StringVar(value=str(store.config['reminder_hours']))
        self.expiry=tk.StringVar(value=str(store.config['payment_expiry_hours']))
        controls=ttk.Frame(setup)
        controls.grid(row=1,column=1,columnspan=2,sticky='w',pady=4)
        ttk.Label(controls,text='Reminder (hours)').pack(side='left')
        ttk.Spinbox(controls,textvariable=self.reminder,from_=1,to=23,width=4).pack(side='left',padx=(4,12))
        ttk.Label(controls,text='Payment expiry (hours)').pack(side='left')
        ttk.Spinbox(controls,textvariable=self.expiry,from_=1,to=24,width=4).pack(side='left',padx=4)
        ttk.Label(setup,text='Response deadline stays at 24 hours. Existing conversations keep their settings.').grid(row=2,column=0,columnspan=3,sticky='w',padx=4)
        body=ttk.Panedwindow(outer,orient='horizontal')
        body.pack(fill='both',expand=True,pady=12)
        left=ttk.Frame(body,padding=(0,0,12,0))
        right=ttk.Frame(body)
        body.add(left,weight=1)
        body.add(right,weight=4)
        ttk.Label(left,text='Conversations').pack(anchor='w')
        self.listbox=tk.Listbox(left,width=30,height=10,font=('Segoe UI',10),exportselection=False)
        self.listbox.pack(fill='both',expand=True,pady=(6,12))
        self.listbox.bind('<<ListboxSelect>>',self.select)
        self.summary=tk.StringVar(value='Choose an example above to begin.')
        ttk.Label(left,textvariable=self.summary,wraplength=245,justify='left').pack(side='bottom',before=self.listbox,anchor='w',fill='x')
        self.state=tk.StringVar(value='No conversation selected')
        ttk.Label(right,textvariable=self.state,style='State.TLabel').pack(anchor='w')
        self.clock=tk.StringVar(value='Clock advances only when you use the controls below.')
        ttk.Label(right,textvariable=self.clock).pack(anchor='w',pady=(3,8))
        notebook=ttk.Notebook(right)
        notebook.pack(fill='both',expand=True)
        chat_frame=ttk.Frame(notebook)
        audit_frame=ttk.Frame(notebook)
        notebook.add(chat_frame,text='Chat')
        notebook.add(audit_frame,text='Audit history')
        self.chat=ScrolledText(chat_frame,height=14,wrap='word',font=('Segoe UI',11),padx=12,pady=12,state='disabled')
        self.chat.pack(fill='both',expand=True)
        self.chat.tag_configure('outgoing_mock',foreground='#126473')
        self.chat.tag_configure('customer_mock',foreground='#74461e')
        self.audit=ScrolledText(audit_frame,height=14,wrap='word',font=('Consolas',10),state='disabled')
        self.audit.pack(fill='both',expand=True)
        reply_row=ttk.Frame(right)
        reply_row.pack(fill='x',pady=(10,4))
        self.reply_text=tk.StringVar()
        self.entry=ttk.Entry(reply_row,textvariable=self.reply_text)
        self.entry.pack(side='left',fill='x',expand=True,padx=(0,8))
        self.entry.bind('<Return>',lambda event:self.run(self.send))
        ttk.Button(reply_row,text='Send customer reply',command=lambda:self.run(self.send)).pack(side='left')
        ttk.Label(right,text='Try YES, NO, COD, PAID, ADDRESS: full address, or NAME: recipient name.').pack(anchor='w')
        events=ttk.LabelFrame(outer,text='Mock service and clock controls',padding=10)
        events.pack(fill='x')
        for label,status in [('Payment succeeds','success'),('Payment fails','failed'),('Payment expires','expired')]:
            ttk.Button(events,text=label,command=lambda s=status:self.run(lambda:self.payment(s))).pack(side='left',padx=4)
        ttk.Separator(events,orient='vertical').pack(side='left',fill='y',padx=12)
        for hours in (1,12,24):
            ttk.Button(events,text=f'+{hours} hours',command=lambda h=hours:self.run(lambda:self.advance(h))).pack(side='left',padx=4)
        self.notice=tk.StringVar(value='Mock payment buttons act as a local payment-service event; never enter real payment details.')
        notice_label=ttk.Label(outer,textvariable=self.notice,wraplength=1100,foreground='#54616f')
        notice_label.pack(anchor='w',pady=(8,0))
        # Allocate fixed controls first; the expandable text area gets the rest.
        # Otherwise Tk can hide the payment/clock controls at laptop heights.
        events.pack_configure(before=body)
        notice_label.pack_configure(before=body)
        self.refresh_list()

    def run(self,callback):
        from tkinter import messagebox
        try:
            callback()
        except (ValueError,OSError,KeyError) as error:
            messagebox.showerror('Simulator',str(error),parent=self.root)

    def event_id(self):
        return str(uuid.uuid4())

    def refresh_list(self):
        self.rows=self.store.list_conversations()
        self.listbox.delete(0,'end')
        for row in self.rows:
            self.listbox.insert('end',row['id'])

    def select(self,event=None):
        selection=self.listbox.curselection()
        if selection:
            self.current=self.rows[selection[0]]['id']
            self.render()

    def start(self):
        identifier=self.example.get()
        if any(row['id']==identifier for row in self.store.list_conversations()):
            self.current=identifier
            self.render()
            return
        config=dict(self.store.config,reminder_hours=float(self.reminder.get()),payment_expiry_hours=float(self.expiry.get()))
        validate_config(config)
        self.store.config=config
        order=self.orders[identifier]
        self.store.start(order,score_order(order,self.artifact),self.language.get())
        self.current=identifier
        self.refresh_list()
        self.render()

    def require_current(self):
        if not self.current:
            raise ValueError('Select or start a conversation first.')

    def send(self):
        self.require_current()
        self.store.reply(self.current,self.reply_text.get(),self.event_id())
        self.reply_text.set('')
        self.render()

    def payment(self,status):
        self.require_current()
        self.store.mock_payment(self.current,status,self.event_id())
        self.render()

    def advance(self,hours):
        self.store.advance(hours,self.event_id())
        if self.current:
            self.render()

    def render(self):
        c=self.store.snapshot(self.current)
        self.state.set(c['state'].replace('_',' ').title()+'  |  '+('Ready to ship (mock)' if c['can_ship'] else 'Shipping blocked'))
        self.clock.set(c['display_time']+'  |  Deadline: '+c['deadline_display'])
        self.summary.set(f"{c['id']}\nLanguage: {c['language']}\nOriginal bucket: {c['decision']['action']}\nPayment: {c['payment_status']}\nOffer discount: INR {c['discount']}\nMock payable: INR {c['payable']}\nPayment review: {c['payment_review_required']}\nRefund review: {c['refund_review_required']}\n\n{c['decision']['reason']}")
        self.chat.configure(state='normal')
        self.chat.delete('1.0','end')
        for msg in c['messages']:
            who='Customer (simulated)' if msg['direction']=='customer_mock' else 'Store (simulated)'
            self.chat.insert('end',f"{who} · {msg['time']}\n{msg['text']}\n\n",msg['direction'])
        self.chat.configure(state='disabled')
        self.chat.see('end')
        self.audit.configure(state='normal')
        self.audit.delete('1.0','end')
        for item in c['audit']:
            self.audit.insert('end',f"{item['time']} | {item['kind']}\n{json.dumps(item['payload'],ensure_ascii=False)}\n\n")
        self.audit.configure(state='disabled')
        self.audit.see('end')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'data/simulator/conversations.sqlite')
    parser.add_argument('--start',help='Initial simulated ISO time with UTC offset, only for a new database.')
    args=parser.parse_args()
    try:
        import tkinter as tk
        from src.app import Workspace
        root=tk.Tk()
        Workspace(root,'confirmations',simulator_path=args.db,start=args.start)
        root.mainloop()
    except (ValueError,OSError,ImportError) as error:
        parser.exit(1,f'Simulator failed: {error}\n')


if __name__=='__main__':
    main()

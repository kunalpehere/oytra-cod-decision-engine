"""Conversation-first desktop interface over the existing local flow state machine."""

import json
import tkinter as tk
from tkinter import ttk

from src.chat_simulator import SimulatorWindow,score_order
from src.confirmation_flow import ACTIVE,validate_config
from src.data_pipeline import ROOT
from src.dashboard_data import LABELS
from src.ui_theme import BG,PAPER,INK,MUTED,LINE,ACCENT,PALE,RED,AMBER,readable,currency,paper,set_window

EXAMPLE_NAMES={
 'DEMO-TRUSTED':'Repeat customer · ready to ship',
 'DEMO-HINGLISH':'Address needs clarification',
 'DEMO-PRIOR-RTO':'Prepaid offer',
 'DEMO-MISSING-PIN':'Missing pincode · review hold',
 'DEMO-PLACEHOLDER':'Recipient name needed',
 'DEMO-LOW-MARGIN':'Low contribution · review hold',
}


class ConfirmationsView(SimulatorWindow):
    def __init__(self,root,store,artifact,parent=None):
        self.root,self.store,self.artifact=root,store,artifact
        self.examples=json.loads((ROOT/'examples/orders.json').read_text(encoding='utf-8'))
        self.orders={o['order_id']:o for o in self.examples}
        self.choices={EXAMPLE_NAMES.get(key,key):key for key in self.orders}
        self.current=None
        if parent is None:
            set_window(root,'Customer confirmations')
        self.frame=ttk.Frame(parent or root,padding=(24,20))
        self.frame.pack(fill='both',expand=True)
        self.frame.columnconfigure(0,weight=1)
        self.frame.rowconfigure(2,weight=1)
        header=ttk.Frame(self.frame)
        header.grid(row=0,column=0,sticky='ew')
        ttk.Label(header,text='Customer confirmations',style='Title.TLabel').pack(side='left')
        ttk.Button(header,text='Timing settings',command=lambda:self.run(self.timing_settings)).pack(side='right')
        self.notice=tk.StringVar(value='Demo conversations only. Messages, payments and shipping stay simulated.')
        notice=ttk.Label(self.frame,textvariable=self.notice,style='Muted.TLabel')
        notice.grid(row=1,column=0,sticky='ew',pady=(8,16))
        self.frame.bind('<Configure>',lambda event:notice.configure(wraplength=max(400,event.width-48)))
        main=ttk.Frame(self.frame)
        main.grid(row=2,column=0,sticky='nsew')
        main.columnconfigure(1,weight=1)
        main.rowconfigure(0,weight=1)
        inbox=paper(main,width=235,padx=12,pady=14)
        inbox.grid(row=0,column=0,sticky='ns',padx=(0,16))
        inbox.grid_propagate(False)
        inbox.columnconfigure(0,weight=1)
        inbox.rowconfigure(1,weight=1)
        ttk.Label(inbox,text='Conversations',style='PaperTitle.TLabel').grid(row=0,column=0,sticky='w',pady=(0,10))
        self.listbox=ttk.Treeview(inbox,columns=('id','state'),displaycolumns=('id',),show='tree',style='Inbox.Treeview',selectmode='browse',height=4)
        self.listbox.column('#0',width=195,minwidth=100,stretch=True)
        self.listbox.column('id',width=0,minwidth=0,stretch=False)
        self.listbox.grid(row=1,column=0,sticky='nsew')
        self.listbox.bind('<<TreeviewSelect>>',self.select)
        starter=tk.Frame(inbox,bg=PAPER)
        starter.grid(row=2,column=0,sticky='ew',pady=(14,0))
        ttk.Label(starter,text='START A DEMO',style='PaperMuted.TLabel').pack(anchor='w',pady=(0,8))
        self.example=tk.StringVar(value=EXAMPLE_NAMES['DEMO-HINGLISH'])
        ttk.Combobox(starter,textvariable=self.example,values=list(self.choices),state='readonly',width=22).pack(fill='x')
        self.language=tk.StringVar(value='Hinglish')
        ttk.Combobox(starter,textvariable=self.language,values=['English','Hindi','Hinglish'],state='readonly',width=22).pack(fill='x',pady=8)
        ttk.Button(starter,text='Start conversation',style='Accent.TButton',command=lambda:self.run(self.start)).pack(fill='x')
        self.reminder=tk.StringVar(value=str(store.config['reminder_hours']))
        self.expiry=tk.StringVar(value=str(store.config['payment_expiry_hours']))
        right=ttk.Frame(main)
        right.grid(row=0,column=1,sticky='nsew')
        right.columnconfigure(0,weight=1)
        right.rowconfigure(2,weight=1)
        context=paper(right,padx=16,pady=12)
        context.grid(row=0,column=0,sticky='ew')
        self.state=tk.StringVar(value='Select or start a conversation')
        self.state_label=ttk.Label(context,textvariable=self.state,style='PaperTitle.TLabel')
        self.state_label.pack(anchor='w')
        self.summary=tk.StringVar(value='Choose an example from the inbox to try the confirmation flow.')
        summary=ttk.Label(context,textvariable=self.summary,style='PaperMuted.TLabel')
        summary.pack(anchor='w',pady=(6,0))
        context.bind('<Configure>',lambda event:summary.configure(wraplength=max(300,event.width-32)))
        tools=ttk.Frame(right)
        tools.grid(row=1,column=0,sticky='ew',pady=10)
        self.clock=tk.StringVar(value='The demo clock moves only when you advance it.')
        ttk.Label(tools,textvariable=self.clock,style='Muted.TLabel').pack(side='left')
        self.payment_menu_button=ttk.Menubutton(tools,text='Simulate payment',state='disabled')
        self.payment_menu_button.pack(side='right',padx=(8,0))
        menu=tk.Menu(self.payment_menu_button,tearoff=False)
        for title,status in [('Payment succeeds','success'),('Payment fails','failed'),('Offer expires','expired')]:
            menu.add_command(label=title,command=lambda s=status:self.run(lambda:self.payment(s)))
        self.payment_menu_button.configure(menu=menu)
        time_button=ttk.Menubutton(tools,text='Advance time')
        time_button.pack(side='right')
        time_menu=tk.Menu(time_button,tearoff=False)
        for title,hours in [('1 hour',1),('12 hours',12),('24 hours',24)]:
            time_menu.add_command(label=title,command=lambda h=hours:self.run(lambda:self.advance(h)))
        time_button.configure(menu=time_menu)
        notebook=ttk.Notebook(right)
        notebook.grid(row=2,column=0,sticky='nsew')
        chat_frame=ttk.Frame(notebook,style='Paper.TFrame')
        activity_frame=ttk.Frame(notebook,style='Paper.TFrame')
        notebook.add(chat_frame,text='Conversation')
        notebook.add(activity_frame,text='Activity')
        chat_frame.rowconfigure(0,weight=1)
        chat_frame.columnconfigure(0,weight=1)
        self.chat=tk.Canvas(chat_frame,bg='#F7F9F5',highlightthickness=0,height=180)
        self.chat.grid(row=0,column=0,sticky='nsew')
        chat_scroll=ttk.Scrollbar(chat_frame,orient='vertical',command=self.chat.yview)
        chat_scroll.grid(row=0,column=1,sticky='ns')
        self.chat.configure(yscrollcommand=chat_scroll.set)
        self.bubbles=tk.Frame(self.chat,bg='#F7F9F5')
        self.bubble_window=self.chat.create_window(0,0,window=self.bubbles,anchor='nw')
        self.bubbles.bind('<Configure>',lambda event:self.chat.configure(scrollregion=self.chat.bbox('all')))
        self.chat.bind('<Configure>',self.resize_chat)
        for widget in (self.chat,self.bubbles):
            widget.bind('<MouseWheel>',self.scroll_chat)
        activity_frame.rowconfigure(0,weight=1)
        activity_frame.columnconfigure(0,weight=1)
        self.audit=ttk.Treeview(activity_frame,columns=('time','event'),show='headings',height=5)
        self.audit.heading('time',text='TIME · IST')
        self.audit.heading('event',text='ACTIVITY')
        self.audit.column('time',width=90,stretch=False)
        self.audit.column('event',width=460)
        self.audit.grid(row=0,column=0,sticky='nsew')
        audit_scroll=ttk.Scrollbar(activity_frame,orient='vertical',command=self.audit.yview)
        audit_scroll.grid(row=0,column=1,sticky='ns')
        self.audit.configure(yscrollcommand=audit_scroll.set)
        composer=paper(right,padx=12,pady=12)
        composer.grid(row=3,column=0,sticky='ew',pady=(10,0))
        composer.columnconfigure(0,weight=1)
        self.reply_text=tk.StringVar()
        self.entry=ttk.Entry(composer,textvariable=self.reply_text)
        self.entry.grid(row=0,column=0,sticky='ew',padx=(0,8))
        self.entry.bind('<Return>',lambda event:self.run(self.send))
        ttk.Button(composer,text='Send reply',style='Accent.TButton',command=lambda:self.run(self.send)).grid(row=0,column=1)
        quick=tk.Frame(composer,bg=PAPER)
        quick.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(8,0))
        for label,text in [('Confirm order','YES'),('Cancel order','NO'),('Keep COD','COD')]:
            ttk.Button(quick,text=label,command=lambda t=text:self.run(lambda:self.quick_reply(t))).pack(side='left',padx=(0,6))
        ttk.Button(quick,text='Update details',command=lambda:self.run(self.correct_details)).pack(side='right')
        self.reply_hint=tk.StringVar(value='Replies here act as the customer in this demo.')
        hint_label=ttk.Label(right,textvariable=self.reply_hint,style='Muted.TLabel')
        hint_label.grid(row=4,column=0,sticky='ew',pady=(7,0))
        right.bind('<Configure>',lambda event:hint_label.configure(wraplength=max(300,event.width)))
        self.refresh_list()
        self.render_empty()

    def run(self,callback):
        try:
            callback()
        except (ValueError,OSError,KeyError) as error:
            self.notice.set(str(error))

    def render_empty(self):
        tk.Label(self.bubbles,text='Try a customer conversation',bg='#F7F9F5',fg=INK,font=('Segoe UI',16,'bold')).pack(pady=(45,10))
        tk.Label(self.bubbles,text='Start with an incomplete address or a prepaid offer.\nThen use the reply buttons to see what happens next.',
                 bg='#F7F9F5',fg=MUTED,font=('Segoe UI',10),justify='center').pack(pady=(0,30))

    def refresh_list(self):
        self.rows=self.store.list_conversations()
        self.listbox.delete(*self.listbox.get_children())
        for row in self.rows:
            title=row['id'].replace('DEMO-','').replace('-',' ').title()
            self.listbox.insert('','end',iid=row['id'],text=title,values=('',row['state']))
        if self.current and self.listbox.exists(self.current):
            self.listbox.selection_set(self.current)

    def select(self,event=None):
        selected=self.listbox.selection()
        if selected:
            self.current=selected[0]
            self.render()

    def start(self):
        identifier=self.choices[self.example.get()]
        if not any(row['id']==identifier for row in self.store.list_conversations()):
            config=dict(self.store.config,reminder_hours=float(self.reminder.get()),payment_expiry_hours=float(self.expiry.get()))
            validate_config(config)
            self.store.config=config
            order=self.orders[identifier]
            self.store.start(order,score_order(order,self.artifact),self.language.get())
        self.current=identifier
        self.refresh_list()
        self.render()

    def quick_reply(self,text):
        self.require_current()
        self.store.reply(self.current,text,self.event_id())
        self.render()

    def send(self):
        super().send()
        self.entry.focus_set()

    def scroll_chat(self,event):
        self.chat.yview_scroll(-int(event.delta/120),'units')

    def resize_chat(self,event):
        self.chat.itemconfigure(self.bubble_window,width=event.width)
        for label in getattr(self,'bubble_labels',[]):
            label.configure(wraplength=max(180,int(event.width*.80)-40))

    def render(self):
        c=self.store.snapshot(self.current)
        self.state.set(readable(c['state']))
        self.state_label.configure(foreground=ACCENT if c['can_ship'] else RED if c['state']=='cancelled' else AMBER)
        review=[]
        if c['needs_address']:
            review.append('address')
        if c['needs_name']:
            review.append('recipient name')
        next_step=('Next: update '+', '.join(review)+', then confirm.' if review and c['state'] in ACTIVE else
                   'No shipment is created by this demo.' if c['can_ship'] else 'Replies and payments are recorded locally.')
        self.summary.set(f"{c['id']} · {c['language']} · {LABELS[c['decision']['action']]}\n{next_step}  Order: {currency(c['order']['order_value'])}. Payment: {readable(c['payment_status'])}.")
        self.clock.set(c['display_time'][11:16]+' IST · '+c['display_time'][:10])
        self.reply_hint.set('Reply deadline: '+c['deadline_display']+' · '+('Shipping is ready in the simulator.' if c['can_ship'] else 'Use quotes: address "full delivery address" and name "Kunal". Then confirm.'))
        if c['payment_review_required'] or c['refund_review_required']:
            self.notice.set('Payment or refund needs operations review. This order will not be released automatically.')
        else:
            self.notice.set('Demo conversations only. Messages, payments and shipping stay simulated.')
        self.payment_menu_button.configure(state='disabled' if c['payment_status']=='not_offered' else 'normal')
        for child in self.bubbles.winfo_children():
            child.destroy()
        self.bubble_labels=[]
        if not c['messages']:
            tk.Label(self.bubbles,text='No customer message needed',bg='#F7F9F5',fg=INK,font=('Segoe UI',15,'bold')).pack(pady=(40,10))
            tk.Label(self.bubbles,text=c['decision']['reason'],bg='#F7F9F5',fg=MUTED,wraplength=400).pack(padx=20,pady=(0,30))
        for msg in c['messages']:
            incoming=msg['direction']=='customer_mock'
            row=tk.Frame(self.bubbles,bg='#F7F9F5')
            row.pack(fill='x',padx=16,pady=7)
            bubble=tk.Frame(row,bg=PALE if incoming else PAPER,padx=14,pady=10,highlightbackground=LINE,highlightthickness=1)
            bubble.pack(side='right' if incoming else 'left')
            tk.Label(bubble,text=('Customer' if incoming else 'Store')+'  ·  '+msg['time'][11:16],bg=bubble['bg'],fg=MUTED,font=('Segoe UI',9)).pack(anchor='w',pady=(0,5))
            label=tk.Label(bubble,text=msg['text'],bg=bubble['bg'],fg=INK,font=('Segoe UI',11),justify='left',
                           wraplength=max(180,int(max(400,self.chat.winfo_width())*.80)-40))
            label.pack(anchor='w')
            self.bubble_labels.append(label)
            for widget in (row,bubble,label):
                widget.bind('<MouseWheel>',self.scroll_chat)
        self.audit.delete(*self.audit.get_children())
        for item in c['audit']:
            payload=item['payload']
            if item['kind']=='state_changed':
                text=readable(payload['previous'])+' → '+readable(payload['state'])
            elif item['kind']=='customer_reply':
                text='Customer replied: '+payload['text']
            elif item['kind']=='mock_payment_event':
                text='Simulated payment: '+payload['status']+' · '+currency(payload.get('amount'))
            elif item['kind']=='customer_corrected_details':
                text='Customer updated '+payload['field'].replace('_',' ')
            else:
                text=item['kind'].replace('_',' ').capitalize()
            self.audit.insert('','end',values=(item['time'][11:16],text))
        self.chat.update_idletasks()
        self.chat.configure(scrollregion=self.chat.bbox('all'))
        self.chat.yview_moveto(1)

    def correct_details(self):
        self.require_current()
        c=self.store.snapshot(self.current)
        if c['state'] not in ACTIVE:
            raise ValueError('This conversation is closed or held for review. Operations must review it before details can change.')
        from tkinter import messagebox
        dialog=tk.Toplevel(self.root)
        dialog.title('Update delivery details')
        dialog.geometry('560x390')
        dialog.transient(self.root)
        frame=ttk.Frame(dialog,padding=22)
        frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Update delivery details',style='Section.TLabel').pack(anchor='w',pady=(0,8))
        ttk.Label(frame,text='These changes are supplied by the simulated customer.\nThe order will still need a fresh confirmation.',style='Muted.TLabel').pack(anchor='w',pady=(0,14))
        ttk.Label(frame,text='Recipient name').pack(anchor='w')
        name=tk.StringVar(value=c['order']['customer_name'])
        ttk.Entry(frame,textvariable=name).pack(fill='x',pady=(5,12))
        ttk.Label(frame,text='Full delivery address').pack(anchor='w')
        address=tk.Text(frame,height=4,font=('Segoe UI',11),relief='solid',borderwidth=1,background=PAPER,foreground=INK)
        address.pack(fill='x',pady=(5,14))
        address.insert('1.0',c['order']['address'])
        def save():
            try:
                changed=False
                for field,value,old in [('NAME',name.get().strip(),c['order']['customer_name']),('ADDRESS',address.get('1.0','end').strip(),c['order']['address'])]:
                    if value!=old:
                        result=self.store.reply(self.current,field+': '+value,self.event_id())
                        changed=True
                        if result['audit'][-1]['kind']=='correction_rejected':
                            self.render()
                            messagebox.showerror('More detail needed','Please enter a clear recipient name or a full building, street and locality address.',parent=dialog)
                            return
                if not changed:
                    messagebox.showinfo('No changes','Update the name or address before saving.',parent=dialog)
                    return
                self.render()
                dialog.destroy()
            except (ValueError,OSError) as error:
                messagebox.showerror('Could not update',str(error),parent=dialog)
        ttk.Button(frame,text='Save details',style='Accent.TButton',command=save).pack(side='right')
        ttk.Button(frame,text='Cancel',command=dialog.destroy).pack(side='right',padx=8)

    def timing_settings(self):
        from tkinter import messagebox
        dialog=tk.Toplevel(self.root)
        dialog.title('Conversation timing')
        dialog.geometry('460x320')
        dialog.transient(self.root)
        frame=ttk.Frame(dialog,padding=22)
        frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Conversation timing',style='Section.TLabel').pack(anchor='w',pady=(0,12))
        ttk.Label(frame,text='Applies to new conversations only.\nThe response deadline remains 24 hours.',style='Muted.TLabel').pack(anchor='w',pady=(0,16))
        for title,variable in [('Reminder after (hours)',self.reminder),('Payment offer expires after (hours)',self.expiry)]:
            row=ttk.Frame(frame)
            row.pack(fill='x',pady=6)
            ttk.Label(row,text=title).pack(side='left')
            ttk.Entry(row,textvariable=variable,width=8).pack(side='right')
        def save():
            try:
                config=dict(self.store.config,reminder_hours=float(self.reminder.get()),payment_expiry_hours=float(self.expiry.get()))
                validate_config(config)
                self.store.config=config
                dialog.destroy()
            except ValueError as error:
                messagebox.showerror('Invalid timing',str(error),parent=dialog)
        ttk.Button(frame,text='Save timing',style='Accent.TButton',command=save).pack(anchor='e',pady=(16,0))

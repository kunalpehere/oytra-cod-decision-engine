"""Readable founder view over the unchanged dashboard data and settings logic."""

import tkinter as tk
from tkinter import ttk
from decimal import Decimal

from src.dashboard import FounderDashboard
from src.dashboard_data import BRIDGE,POSITIVE,LABELS,export_daily,yesterday_ist
from src.ui_theme import BG,PAPER,INK,MUTED,LINE,ACCENT,RED,AMBER,PALE,readable,currency,paper,set_window,note_window

BRIDGE_LABELS={
 'baseline_contribution':'Ship-all contribution','avoided_rto_loss':'RTO costs avoided',
 'new_prepaid_delivery_contribution':'Contribution from assumed prepaid deliveries',
 'negative_held_margin_avoided':'Negative contribution avoided on holds',
 'genuine_held_margin_at_risk':'Genuine order margin at risk on holds',
 'missed_genuine_delivery_contribution':'Other genuine delivery contribution lost',
 'new_prepaid_rto_loss':'Additional prepaid RTO costs','discount_cost':'Prepaid discounts',
 'payment_fee':'Payment fees','message_cost':'Confirmation and prepaid messages',
 'net_impact':'Net contribution change','policy_contribution':'Estimated policy contribution',
}


class OverviewView(FounderDashboard):
    def __init__(self,root,data,parent=None):
        self.root,self.data=root,data
        self.scenario=self.view=None
        if parent is None:
            set_window(root,'Daily overview')
        host=parent or root
        self.frame=ttk.Frame(host,padding=(24,20))
        self.frame.pack(fill='both',expand=True)
        self.frame.columnconfigure(0,weight=1)
        self.frame.rowconfigure(5,weight=1)
        header=ttk.Frame(self.frame)
        header.grid(row=0,column=0,sticky='ew')
        ttk.Label(header,text='Daily overview',style='Title.TLabel').pack(side='left')
        ttk.Button(header,text='Export report',style='Accent.TButton',command=lambda:self.run(self.export)).pack(side='right')
        ttk.Button(header,text='How estimates work',command=self.method).pack(side='right',padx=8)
        controls=ttk.Frame(self.frame)
        controls.grid(row=1,column=0,sticky='ew',pady=(14,16))
        self.source=tk.StringVar(value='Historical replay')
        source=ttk.Combobox(controls,textvariable=self.source,values=['Historical replay','Simulator activity'],state='readonly',width=19)
        source.pack(side='left',padx=(0,10))
        source.bind('<<ComboboxSelected>>',lambda event:self.run(self.source_changed))
        self.day=tk.StringVar()
        self.date_picker=ttk.Combobox(controls,textvariable=self.day,width=12)
        self.date_picker.pack(side='left',padx=(0,5))
        self.date_picker.bind('<<ComboboxSelected>>',lambda event:self.run(self.refresh))
        self.date_picker.bind('<Return>',lambda event:self.run(self.refresh))
        ttk.Button(controls,text='View day',command=lambda:self.run(self.refresh)).pack(side='left',padx=3)
        ttk.Button(controls,text='Yesterday',command=lambda:self.run(self.yesterday)).pack(side='left',padx=3)
        ttk.Button(controls,text='Adjust assumptions',command=lambda:self.run(self.open_settings)).pack(side='right')
        ttk.Button(controls,text='Use baseline',command=lambda:self.run(self.reset)).pack(side='right',padx=8)
        self.bucket_vars={}
        strip=paper(self.frame)
        strip.grid(row=2,column=0,sticky='ew')
        colors=(ACCENT,'#AA803E','#517B9A',RED)
        for i,((action,label),color) in enumerate(zip(LABELS.items(),colors)):
            strip.columnconfigure(i,weight=1,uniform='buckets')
            box=tk.Frame(strip,bg=PAPER,padx=18,pady=12)
            box.grid(row=0,column=i,sticky='ew')
            variable=tk.StringVar(value='0')
            self.bucket_vars[action]=variable
            tk.Label(box,text=label,bg=PAPER,fg=MUTED,font=('Segoe UI',10),anchor='w').pack(fill='x')
            tk.Label(box,textvariable=variable,bg=PAPER,fg=INK,font=('Segoe UI',25,'bold'),anchor='w').pack(fill='x')
            tk.Frame(box,bg=color,height=3).pack(fill='x',pady=(6,0))
            for widget in (box,*box.winfo_children()):
                widget.bind('<Button-1>',lambda event,a=action:self.filter_bucket(a))
                widget.configure(cursor='hand2')
        metrics=ttk.Frame(self.frame)
        metrics.grid(row=3,column=0,sticky='ew',pady=(12,10))
        self.money_vars={}
        self.money_labels={}
        for i,(key,title,hint) in enumerate((
            ('net_impact','Net contribution change','Compared with shipping every order'),
            ('avoided_rto_loss','RTO costs avoided','Shipping, handling and expected damage'),
            ('genuine_held_margin_at_risk','Genuine margin at risk','Orders held within this replay'),
            ('missed_genuine_delivery_contribution','Other contribution lost','Assumed confirmation and prepaid effects'))):
            metrics.columnconfigure(i,weight=1,uniform='money')
            card=paper(metrics,padx=14,pady=12)
            card.grid(row=0,column=i,sticky='nsew',padx=(0,8 if i<3 else 0))
            ttk.Label(card,text=title,style='PaperMuted.TLabel').pack(anchor='w')
            var=tk.StringVar(value='—')
            self.money_vars[key]=var
            label=ttk.Label(card,textvariable=var,style='Money.TLabel')
            label.pack(anchor='w',pady=(5,4))
            self.money_labels[key]=label
            caption=ttk.Label(card,text=hint,style='PaperMuted.TLabel',wraplength=205)
            caption.pack(anchor='w')
            card.bind('<Configure>',lambda event,w=caption:w.configure(wraplength=max(110,event.width-28)))
        self.note=tk.StringVar()
        self.note_label=ttk.Label(self.frame,textvariable=self.note,style='Muted.TLabel')
        self.note_label.grid(row=4,column=0,sticky='ew',pady=(0,10))
        self.notebook=ttk.Notebook(self.frame)
        self.notebook.grid(row=5,column=0,sticky='nsew')
        orders_tab=ttk.Frame(self.notebook,padding=(0,12))
        finance_tab=ttk.Frame(self.notebook,padding=12,style='Paper.TFrame')
        self.notebook.add(orders_tab,text='Orders')
        self.notebook.add(finance_tab,text='Contribution & scenarios')
        orders_tab.rowconfigure(1,weight=1)
        orders_tab.columnconfigure(0,weight=1)
        search=ttk.Frame(orders_tab)
        search.grid(row=0,column=0,sticky='ew',pady=(0,10))
        ttk.Label(search,text='Find an order',style='Muted.TLabel').pack(side='left',padx=(0,8))
        self.query=tk.StringVar()
        self.search_entry=ttk.Entry(search,textvariable=self.query,width=19)
        self.search_entry.pack(side='left')
        self.bucket_filter=tk.StringVar(value='All decisions')
        self.filter_picker=ttk.Combobox(search,textvariable=self.bucket_filter,values=['All decisions',*LABELS.values()],state='readonly',width=19)
        self.filter_picker.pack(side='left',padx=10)
        self.filter_picker.bind('<<ComboboxSelected>>',lambda event:self.render_orders())
        self.result_count=tk.StringVar()
        ttk.Label(search,textvariable=self.result_count,style='Muted.TLabel').pack(side='right')
        self.query.trace_add('write',lambda *args:self.render_orders())
        split=ttk.Panedwindow(orders_tab,orient='horizontal')
        split.grid(row=1,column=0,sticky='nsew')
        table_frame=ttk.Frame(split)
        details_frame=paper(split,padx=16,pady=14)
        split.add(table_frame,weight=3)
        split.add(details_frame,weight=2)
        table_frame.rowconfigure(0,weight=1)
        table_frame.columnconfigure(0,weight=1)
        self.orders=ttk.Treeview(table_frame,columns=('id','action','risk','outcome'),show='headings',height=6,selectmode='browse')
        for key,title,width in [('id','ORDER',130),('action','DECISION',150),('risk','RTO RISK',80),('outcome','OUTCOME / STATUS',155)]:
            self.orders.heading(key,text=title)
            self.orders.column(key,width=width,minwidth=65,stretch=True)
        self.orders.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(table_frame,orient='vertical',command=self.orders.yview)
        scroll.grid(row=0,column=1,sticky='ns')
        self.orders.configure(yscrollcommand=scroll.set)
        self.orders.bind('<<TreeviewSelect>>',self.select_order)
        self.detail_title=tk.StringVar(value='Order details')
        ttk.Label(details_frame,textvariable=self.detail_title,style='PaperTitle.TLabel').pack(anchor='w',pady=(0,10))
        from tkinter.scrolledtext import ScrolledText
        self.detail=ScrolledText(details_frame,width=30,height=7,wrap='word',font=('Segoe UI',10),background=PAPER,foreground=INK,
                                 relief='flat',borderwidth=0,highlightthickness=0,state='disabled')
        self.detail.pack(fill='both',expand=True)
        finance_tab.columnconfigure(0,weight=1)
        finance_tab.rowconfigure(1,weight=1)
        ttk.Label(finance_tab,text='A bridge from ship-all contribution to the selected policy. Costs are shown as deductions.',style='PaperMuted.TLabel').grid(row=0,column=0,sticky='w',pady=(0,10))
        self.breakdown=ttk.Treeview(finance_tab,columns=('component','value'),show='headings',height=5)
        self.breakdown.heading('component',text='CONTRIBUTION COMPONENT')
        self.breakdown.heading('value',text='ESTIMATE')
        self.breakdown.column('component',width=600)
        self.breakdown.column('value',width=170,anchor='e')
        self.breakdown.grid(row=1,column=0,sticky='nsew')
        bar=ttk.Scrollbar(finance_tab,orient='vertical',command=self.breakdown.yview)
        bar.grid(row=1,column=1,sticky='ns')
        self.breakdown.configure(yscrollcommand=bar.set)
        self.sensitivity=ttk.Treeview(finance_tab,columns=('name','impact'),show='headings',height=4)
        self.sensitivity.heading('name',text='SAME DECISIONS · DIFFERENT RESPONSE ASSUMPTIONS')
        self.sensitivity.heading('impact',text='NET CHANGE')
        self.sensitivity.column('name',width=600)
        self.sensitivity.column('impact',width=170,anchor='e')
        self.sensitivity.grid(row=2,column=0,sticky='ew',pady=(12,0))
        self.status=tk.StringVar()
        self.status_label=ttk.Label(self.frame,textvariable=self.status,style='Muted.TLabel')
        self.status_label.grid(row=6,column=0,sticky='ew',pady=(8,0))
        self.frame.bind('<Configure>',self.resize)
        self.source_changed()

    def resize(self,event):
        if event.widget==self.frame:
            self.note_label.configure(wraplength=max(400,event.width-48))
            self.status_label.configure(wraplength=max(400,event.width-48))

    def run(self,callback):
        try:
            callback()
        except (ValueError,OSError,KeyError) as error:
            self.status.set(str(error))
            self.status_label.configure(foreground=RED)

    def method(self):
        text=(self.view['note'] if self.view else '')+'\n\nHistorical delivery outcomes are observed. Confirmation, prepaid uptake and financial impact are estimates. Holds put contribution at risk; they do not prove a permanent lost sale.\n\nChanging assumptions creates an exploratory scenario. It does not replace the published evaluation. No actual messages, payments or shipments are created.'
        note_window(self.root,'About these estimates',text)

    def source_changed(self):
        default=self.data.default_day(self.source_key())
        self.date_picker.configure(values=sorted(set(self.data.dates(self.source_key())+[default['requested_yesterday']])))
        self.day.set(default['selected_day'])
        self.default_date_notice=(default['selected_day'],default['requested_yesterday']) if default['fell_back_to_latest'] else None
        self.refresh()

    def refresh(self):
        self.view=self.data.daily(self.day.get(),self.source_key(),self.scenario if self.source_key()=='historical' else None)
        view=self.view
        for key,var in self.bucket_vars.items():
            var.set(str(view['counts'][key]))
        for key,var in self.money_vars.items():
            var.set(currency(view['money'][key]) if view['money'] is not None else '—')
        net=Decimal(view['money']['net_impact']) if view['money'] else Decimal(0)
        self.money_labels['net_impact'].configure(style='NegativeMoney.TLabel' if net<0 else 'PositiveMoney.TLabel' if net>0 else 'Money.TLabel')
        reference=currency(self.data.frozen_september_impact)
        self.note.set(f"{view['scenario']}  ·  {'Simulated activity; delivery impact is not available.' if view['source']=='simulator' else 'Retrospective estimates, not measured savings.'}  September baseline: {reference}.")
        for tree in (self.breakdown,self.sensitivity):
            tree.delete(*tree.get_children())
        if view['money']:
            for key in ('baseline_contribution',)+BRIDGE+('net_impact','policy_contribution'):
                value=Decimal(view['money'][key])
                if key in BRIDGE and key not in POSITIVE:
                    value=-value
                self.breakdown.insert('','end',values=(BRIDGE_LABELS[key],currency(value)))
        elif view['source']=='simulator':
            for key,value in view['mock_money'].items():
                label=key.replace('_',' ').capitalize()
                self.breakdown.insert('','end',values=(label+' · simulated',currency(value) if key=='verified_payment_face_value' else value))
        else:
            self.breakdown.insert('','end',values=('No resolved, financially eligible orders for this date','Not available'))
        for row in view['sensitivity']:
            self.sensitivity.insert('','end',values=(row['scenario'],currency(row['net_impact'])))
        self.render_orders()
        excluded=sum(view.get('financial_exclusions',{}).values())
        self.status.set(f"{view['order_count']} orders · {view.get('financial_orders',0)} with financial estimates"+(f' · {excluded} excluded from money totals' if excluded else '')+' · Dates shown in IST')
        if getattr(self,'default_date_notice',None) and self.day.get()==self.default_date_notice[0]:
            self.status.set(f"Yesterday ({self.default_date_notice[1]}) has no records. Showing the latest available day instead. Dates shown in IST.")
        self.status_label.configure(foreground=MUTED)

    def filter_bucket(self,action):
        self.bucket_filter.set(LABELS[action])
        self.notebook.select(0)
        self.render_orders()

    def render_orders(self):
        if self.view is None:
            return
        self.orders.delete(*self.orders.get_children())
        query=self.query.get().strip().casefold()
        count=0
        for i,row in enumerate(self.view['orders']):
            if query and query not in row['order_id'].casefold():
                continue
            if self.bucket_filter.get()!='All decisions' and LABELS[row['initial_action']]!=self.bucket_filter.get():
                continue
            self.orders.insert('','end',iid=str(i),values=(row['order_id'],LABELS[row['initial_action']],
                               f"{row['risk_probability']:.0%}" if row['risk_probability'] is not None else '—',
                               readable(row['historical_outcome'] or row['current_state'])))
            count+=1
        self.result_count.set(f'{count} of {self.view["order_count"]} orders')
        self.detail_title.set('Order details')
        self.set_detail('Select an order to see why it was routed, what it needs next, and how its estimate was calculated.' if count else 'No orders match this view. Try another date, clear the search, or select All decisions.')

    def select_order(self,event=None):
        selected=self.orders.selection()
        if not selected:
            return
        row=self.view['orders'][int(selected[0])]
        self.detail_title.set(row['order_id'])
        detail=row['details']
        order=detail.get('order',{})
        decision=detail.get('decision',{})
        lines=[LABELS[row['initial_action']], '',row['reason'],'',
               f"Order value    {currency(order.get('order_value'))}",
               f"RTO estimate    {row['risk_probability']:.1%}" if row['risk_probability'] is not None else 'RTO estimate    Not available',
               f"Destination    {order.get('city','—')}, {order.get('state','—')}"]
        if self.view['source']=='historical':
            lines.extend(['',f"Observed outcome    {readable(row['historical_outcome'])}",f"Estimated contribution change    {currency(row['net_impact'])}"])
        else:
            lines.extend(['',f"Current status    {readable(row['current_state'])}",f"Payment    {readable(row['payment_status'])}",
                          'Payment review    '+('Required' if detail.get('payment_review_required') else 'Not required'),
                          'Refund review    '+('Required' if detail.get('refund_review_required') else 'Not required')])
        requirements=decision.get('required_before_shipping',[])
        if requirements:
            lines.extend(['','Before shipping',*['• '+requirement.capitalize() for requirement in requirements]])
        if row['financial_exclusion']:
            lines.extend(['','Financial estimate unavailable',row['financial_exclusion'].replace('_',' ')])
        self.set_detail('\n'.join(lines))

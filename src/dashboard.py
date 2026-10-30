"""Free local founder dashboard; all historical financial impact is hypothetical."""

import argparse
import copy
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from src.dashboard_data import (DashboardData, FINANCIAL_FIELDS, LABELS, POLICY_FIELDS,
                                export_daily, settings, validate_settings, yesterday_ist)
from src.data_pipeline import ROOT

FRIENDLY={
 'confirm_risk_threshold':'Confirmation risk threshold (0-1)', 'prepaid_risk_threshold':'Prepaid risk threshold (0-1)',
 'hold_risk_threshold':'Review hold threshold (0-1)', 'minimum_expected_contribution':'Minimum expected contribution (INR)',
 'prepaid_discount_inr':'Maximum prepaid discount (INR)', 'maximum_discount_fraction':'Discount / order value cap (0-1)',
 'genuine_confirmation_rate':'Confirmation: genuine orders (0-1)', 'rto_confirmation_rate':'Confirmation: historical RTOs (0-1)',
 'genuine_prepaid_uptake':'Prepaid uptake: genuine orders (0-1)', 'rto_prepaid_uptake':'Prepaid uptake: historical RTOs (0-1)',
 'confirmation_message_cost_inr':'Confirmation message cost (INR)', 'prepaid_message_cost_inr':'Prepaid message cost (INR)',
 'prepaid_payment_fee_fraction':'Prepaid payment fee (0-1)', 'forward_shipping':'Forward shipping (INR)',
 'return_shipping':'Return shipping (INR)', 'packaging_handling':'Packaging and handling (INR)',
 'average_product_cost':'Average product cost (INR)', 'returned_damage_probability':'Returned damage probability (0-1)',
 'delivered_gross_margin':'Delivered gross margin (0-1)', 'brief_prepaid_rto_rate':'Assumed prepaid RTO rate (0-1)',
}


class FounderDashboard:
    def __init__(self,root,data):
        import tkinter as tk
        from tkinter import ttk
        from tkinter.scrolledtext import ScrolledText
        self.root,self.data=root,data
        self.scenario=None
        self.view=None
        root.title('COD founder dashboard - local estimates')
        root.geometry('1280x850')
        root.minsize(1080,730)
        style=ttk.Style(root)
        style.theme_use('clam')
        style.configure('.',font=('Segoe UI',10))
        style.configure('Header.TLabel',font=('Segoe UI',20,'bold'))
        style.configure('Metric.TLabel',font=('Segoe UI',18,'bold'),foreground='#126473')
        frame=ttk.Frame(root,padding=16)
        frame.pack(fill='both',expand=True)
        frame.columnconfigure(0,weight=1)
        frame.rowconfigure(5,weight=1)
        ttk.Label(frame,text='COD daily overview',style='Header.TLabel').grid(row=0,column=0,sticky='w')
        controls=ttk.Frame(frame)
        controls.grid(row=1,column=0,sticky='ew',pady=(8,12))
        self.source=tk.StringVar(value='Historical replay')
        source=ttk.Combobox(controls,textvariable=self.source,values=['Historical replay','Simulator activity'],state='readonly',width=19)
        source.pack(side='left',padx=(0,10))
        source.bind('<<ComboboxSelected>>',lambda event:self.run(self.source_changed))
        self.day=tk.StringVar()
        self.date_picker=ttk.Combobox(controls,textvariable=self.day,width=12)
        self.date_picker.pack(side='left',padx=(0,6))
        self.date_picker.bind('<<ComboboxSelected>>',lambda event:self.run(self.refresh))
        ttk.Button(controls,text='Load date',command=lambda:self.run(self.refresh)).pack(side='left',padx=3)
        ttk.Button(controls,text='Yesterday (IST)',command=lambda:self.run(self.yesterday)).pack(side='left',padx=3)
        ttk.Button(controls,text='What-if settings',command=lambda:self.run(self.open_settings)).pack(side='left',padx=(16,3))
        ttk.Button(controls,text='Reset frozen',command=lambda:self.run(self.reset)).pack(side='left',padx=3)
        ttk.Button(controls,text='Export day',command=lambda:self.run(self.export)).pack(side='right',padx=3)
        self.bucket_vars={}
        buckets=ttk.Frame(frame)
        buckets.grid(row=2,column=0,sticky='ew')
        for i,(action,label) in enumerate(LABELS.items()):
            buckets.columnconfigure(i,weight=1,uniform='bucket')
            card=ttk.LabelFrame(buckets,text=label,padding=10)
            card.grid(row=0,column=i,sticky='ew',padx=(0,8))
            variable=tk.StringVar(value='0')
            self.bucket_vars[action]=variable
            ttk.Label(card,textvariable=variable,style='Metric.TLabel').pack(anchor='w')
        self.money_vars={}
        metrics=ttk.Frame(frame)
        metrics.grid(row=3,column=0,sticky='ew',pady=(10,8))
        for i,(key,label) in enumerate((('avoided_rto_loss','Estimated avoided RTO loss'),
                                       ('genuine_held_margin_at_risk','Genuine held margin at risk'),
                                       ('missed_genuine_delivery_contribution','Other missed genuine contribution'),
                                       ('net_impact','Estimated net impact'))):
            metrics.columnconfigure(i,weight=1,uniform='money')
            card=ttk.LabelFrame(metrics,text=label,padding=10)
            card.grid(row=0,column=i,sticky='ew',padx=(0,8))
            variable=tk.StringVar(value='Unavailable')
            self.money_vars[key]=variable
            ttk.Label(card,textvariable=variable,style='Metric.TLabel').pack(anchor='w')
        self.note=tk.StringVar()
        ttk.Label(frame,textvariable=self.note,wraplength=1200,justify='left',foreground='#5c4a2c').grid(row=4,column=0,sticky='ew',pady=(0,10))
        notebook=ttk.Notebook(frame)
        notebook.grid(row=5,column=0,sticky='nsew')
        order_tab=ttk.Frame(notebook,padding=8)
        finance_tab=ttk.Frame(notebook,padding=8)
        notebook.add(order_tab,text='Orders and conversation details')
        notebook.add(finance_tab,text='Financial breakdown and scenarios')
        order_tab.columnconfigure(0,weight=1)
        order_tab.rowconfigure(0,weight=1)
        order_tab.rowconfigure(1,weight=1)
        columns=('id','action','risk','outcome','state','payment')
        self.orders=ttk.Treeview(order_tab,columns=columns,show='headings',height=7)
        for key,title,width in [('id','Order',150),('action','Initial recommendation',190),('risk','RTO estimate',100),
                                ('outcome','Historical outcome',140),('state','Current / replay state',200),('payment','Payment',140)]:
            self.orders.heading(key,text=title)
            self.orders.column(key,width=width,minwidth=70,stretch=True)
        self.orders.grid(row=0,column=0,sticky='nsew')
        scrollbar=ttk.Scrollbar(order_tab,orient='vertical',command=self.orders.yview)
        scrollbar.grid(row=0,column=1,sticky='ns')
        self.orders.configure(yscrollcommand=scrollbar.set)
        self.orders.bind('<<TreeviewSelect>>',self.select_order)
        self.detail=ScrolledText(order_tab,height=7,wrap='word',font=('Segoe UI',10),state='disabled')
        self.detail.grid(row=1,column=0,columnspan=2,sticky='nsew',pady=(8,0))
        finance_tab.columnconfigure(0,weight=1)
        finance_tab.rowconfigure(0,weight=3)
        finance_tab.rowconfigure(1,weight=1)
        self.breakdown=ttk.Treeview(finance_tab,columns=('component','value'),show='headings',height=10)
        self.breakdown.heading('component',text='Contribution bridge (INR; costs shown negative)')
        self.breakdown.heading('value',text='Estimated amount')
        self.breakdown.column('component',width=650)
        self.breakdown.column('value',width=180,anchor='e')
        self.breakdown.grid(row=0,column=0,sticky='nsew')
        self.sensitivity=ttk.Treeview(finance_tab,columns=('name','impact'),show='headings',height=4)
        self.sensitivity.heading('name',text='Sensitivity: same assignments, changed responses')
        self.sensitivity.heading('impact',text='Net impact (INR)')
        self.sensitivity.column('name',width=650)
        self.sensitivity.column('impact',width=180,anchor='e')
        self.sensitivity.grid(row=1,column=0,sticky='nsew',pady=(8,0))
        self.status=tk.StringVar()
        ttk.Label(frame,textvariable=self.status,wraplength=1200).grid(row=6,column=0,sticky='ew',pady=(8,0))
        self.source_changed()

    def run(self,callback):
        from tkinter import messagebox
        try:
            callback()
        except (ValueError,OSError,KeyError) as error:
            messagebox.showerror('Dashboard',str(error),parent=self.root)

    def source_key(self):
        return 'simulator' if self.source.get()=='Simulator activity' else 'historical'

    def source_changed(self):
        source=self.source_key()
        default=self.data.default_day(source)
        self.date_picker.configure(values=sorted(set(self.data.dates(source)+[default['requested_yesterday']])))
        self.day.set(default['selected_day'])
        self.refresh()
        if default['fell_back_to_latest']:
            self.status.set(f"No {source} orders for yesterday ({default['requested_yesterday']}, IST). Showing latest available date {default['selected_day']}.")

    def yesterday(self):
        self.day.set(yesterday_ist())
        self.refresh()

    def refresh(self):
        view=self.data.daily(self.day.get(),self.source_key(),self.scenario if self.source_key()=='historical' else None)
        self.view=view
        for key,value in self.bucket_vars.items():
            value.set(str(view['counts'][key]))
        for key,value in self.money_vars.items():
            value.set('INR '+view['money'][key] if view['money'] is not None else 'Unavailable')
        self.note.set(view['scenario']+' | '+view['note'])
        for tree in (self.orders,self.breakdown,self.sensitivity):
            tree.delete(*tree.get_children())
        for i,row in enumerate(view['orders']):
            self.orders.insert('', 'end',iid=str(i),values=(row['order_id'],LABELS[row['initial_action']],
                              f"{row['risk_probability']:.1%}" if row['risk_probability'] is not None else 'Unavailable',
                              row['historical_outcome'] or 'Not observed',row['current_state'],row['payment_status']))
        if view['money'] is not None:
            from src.dashboard_data import BRIDGE,POSITIVE
            for key in ('baseline_contribution',)+BRIDGE+('net_impact','policy_contribution'):
                amount=Decimal(view['money'][key])
                if key in BRIDGE and key not in POSITIVE:
                    amount=-amount
                self.breakdown.insert('','end',values=(key.replace('_',' ').title(),f'{amount:,.2f}'))
        elif view['source']=='simulator':
            for key,value in view['mock_money'].items():
                self.breakdown.insert('','end',values=('SIMULATED: '+key.replace('_',' '),value))
        else:
            self.breakdown.insert('','end',values=('No financially eligible resolved orders','Unavailable'))
        for row in view['sensitivity']:
            self.sensitivity.insert('','end',values=(row['scenario'],row['net_impact']))
        self.set_detail('Select an order to inspect the recommendation and its supporting details.')
        reference='INR '+self.data.frozen_september_impact if self.data.frozen_september_impact is not None else 'unavailable (reference hash mismatch or missing report)'
        self.status.set(f"{view['order_count']} orders | financial cohort: {view.get('financial_orders','unavailable')} | {view['scenario']} | Frozen September base scenario: {reference} (not proven savings). No API calls.")

    def set_detail(self,text):
        self.detail.configure(state='normal')
        self.detail.delete('1.0','end')
        self.detail.insert('1.0',text)
        self.detail.configure(state='disabled')

    def select_order(self,event=None):
        selected=self.orders.selection()
        if selected:
            row=self.view['orders'][int(selected[0])]
            self.set_detail(row['reason']+'\n\n'+json.dumps(row['details'],indent=2,ensure_ascii=False))

    def reset(self):
        self.scenario=None
        self.refresh()

    def export(self):
        if self.view is None:
            raise ValueError('Load a reporting day first.')
        directory=export_daily(self.view)
        self.status.set('Exported selected view: '+str(directory))

    def open_settings(self):
        import tkinter as tk
        from tkinter import ttk,messagebox
        if self.source_key()!='historical':
            raise ValueError('Scenario controls apply to historical replay. Simulator activity retains its original recommendations.')
        candidate=copy.deepcopy(self.scenario if self.scenario is not None else settings(self.data.artifact))
        dialog=tk.Toplevel(self.root)
        dialog.title('Exploratory scenario - frozen policy stays unchanged')
        dialog.geometry('650x600')
        dialog.transient(self.root)
        outer=ttk.Frame(dialog,padding=16)
        outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='Apply changes to this dashboard session only.\nThis does not retrain the model or overwrite the frozen evaluation.\nDo not select recommended rules by tuning on September.',wraplength=600).pack(anchor='w',pady=(0,12))
        notebook=ttk.Notebook(outer)
        notebook.pack(fill='both',expand=True)
        entries={}
        groups=(('Thresholds and offer',POLICY_FIELDS[:6],'policy'),('Response assumptions',POLICY_FIELDS[6:],'policy'),
                ('Unit economics',FINANCIAL_FIELDS,'financial_assumptions'))
        for title,fields,section in groups:
            tab=ttk.Frame(notebook,padding=12)
            notebook.add(tab,text=title)
            for row,key in enumerate(fields):
                ttk.Label(tab,text=FRIENDLY[key]).grid(row=row,column=0,sticky='w',pady=7)
                variable=tk.StringVar(value=str(candidate[section][key]))
                entries[(section,key)]=variable
                ttk.Entry(tab,textvariable=variable,width=15).grid(row=row,column=1,padx=12,pady=7)
        includes=tk.BooleanVar(value=candidate['policy']['delivered_margin_includes_fulfilment'])
        ttk.Checkbutton(outer,text='Delivered gross margin includes forward shipping and handling',variable=includes).pack(anchor='w',pady=10)
        def apply():
            try:
                for (section,key),variable in entries.items():
                    candidate[section][key]=float(variable.get()) if section=='policy' else Decimal(variable.get())
                candidate['policy']['delivered_margin_includes_fulfilment']=includes.get()
                validate_settings(candidate)
                self.scenario=candidate
                self.refresh()
                dialog.destroy()
            except (ValueError,ArithmeticError) as error:
                messagebox.showerror('Invalid setting',str(error),parent=dialog)
        ttk.Button(outer,text='Apply what-if scenario',command=apply).pack(side='right')
        ttk.Button(outer,text='Cancel',command=dialog.destroy).pack(side='right',padx=8)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date',help='YYYY-MM-DD for headless export; otherwise latest/yesterday default.')
    parser.add_argument('--export',action='store_true',help='Export a day without opening the GUI.')
    parser.add_argument('--source',choices=('historical','simulator'),default='historical')
    parser.add_argument('--simulator-db',type=Path,default=ROOT/'data/simulator/conversations.sqlite')
    parser.add_argument('--output-root',type=Path,default=ROOT/'reports/dashboard/exports')
    args=parser.parse_args()
    try:
        data=DashboardData(simulator_path=args.simulator_db)
        if args.export:
            day=args.date or data.default_day(args.source)['selected_day']
            view=data.daily(day,args.source)
            directory=export_daily(view,args.output_root)
            print(json.dumps(dict(directory=str(directory),day=day,source=args.source,orders=view['order_count'],counts=view['counts'],money=view['money']),indent=2))
        else:
            import tkinter as tk
            from src.app import Workspace
            root=tk.Tk()
            workspace=Workspace(root,data=data)
            window=workspace.views['overview']
            if args.source=='simulator':
                window.source.set('Simulator activity')
                window.source_changed()
            if args.date:
                window.day.set(args.date)
                window.refresh()
            root.mainloop()
    except (ValueError,OSError,ImportError) as error:
        parser.exit(1,f'Dashboard failed: {error}\n')


if __name__=='__main__':
    main()

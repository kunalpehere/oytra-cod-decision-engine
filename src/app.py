"""Unified local order desk: overview and confirmations in one native window."""

import argparse
from pathlib import Path

from src.data_pipeline import ROOT
from src.ui_theme import BG,NAV,PAPER,PALE,ACCENT,set_window,note_window


class Workspace:
    def __init__(self,root,start_page='overview',data=None,simulator_path=None,start=None):
        import tkinter as tk
        from tkinter import ttk
        from src.dashboard_data import DashboardData
        self.root=root
        self.data=data or DashboardData(simulator_path=simulator_path or ROOT/'data/simulator/conversations.sqlite')
        self.simulator_path=Path(simulator_path or self.data.simulator_path)
        self.start=start
        self.views={}
        self.buttons={}
        set_window(root,'Overview')
        root.columnconfigure(1,weight=1)
        root.rowconfigure(0,weight=1)
        sidebar=tk.Frame(root,bg=NAV,width=174,padx=18,pady=26)
        sidebar.grid(row=0,column=0,sticky='ns')
        sidebar.grid_propagate(False)
        tk.Label(sidebar,text='OYTRA',bg=NAV,fg=PAPER,font=('Segoe UI',20,'bold'),anchor='w').pack(fill='x')
        tk.Label(sidebar,text='ORDER DESK',bg=NAV,fg='#AFC6B8',font=('Segoe UI',9),anchor='w').pack(fill='x',pady=(2,36))
        for key,title in [('overview','Daily overview'),('confirmations','Confirmations')]:
            button=tk.Button(sidebar,text=title,anchor='w',bg=NAV,fg='#CFDED3',activebackground='#294F3B',activeforeground=PAPER,
                             relief='flat',borderwidth=0,padx=12,pady=12,font=('Segoe UI',11),cursor='hand2',command=lambda p=key:self.show(p))
            button.pack(fill='x',pady=3)
            self.buttons[key]=button
        footer=tk.Frame(sidebar,bg=NAV)
        footer.pack(side='bottom',fill='x')
        tk.Button(footer,text='Demo guide',bg=NAV,fg='#CFDED3',activebackground=NAV,activeforeground=PAPER,relief='flat',borderwidth=0,
                  anchor='w',font=('Segoe UI',10),cursor='hand2',command=self.help).pack(fill='x',pady=(0,18))
        tk.Label(footer,text='Local workspace\nSimulated operations',bg=NAV,fg='#AFC6B8',font=('Segoe UI',9),justify='left',anchor='w').pack(fill='x')
        self.content=ttk.Frame(root)
        self.content.grid(row=0,column=1,sticky='nsew')
        self.show(start_page)

    def show(self,page):
        if page not in self.buttons:
            raise ValueError('Unknown workspace page.')
        self.root.title(('Daily overview' if page=='overview' else 'Confirmations')+' · Oytra order desk')
        if page not in self.views:
            if page=='overview':
                from src.ui_dashboard import OverviewView
                self.views[page]=OverviewView(self.root,self.data,self.content)
            else:
                from src.confirmation_flow import FlowStore
                from src.ui_simulator import ConfirmationsView
                self.views[page]=ConfirmationsView(self.root,FlowStore(self.simulator_path,start=self.start),self.data.artifact,self.content)
        for key,view in self.views.items():
            view.frame.pack_forget()
        self.views[page].frame.pack(fill='both',expand=True)
        for key,button in self.buttons.items():
            button.configure(bg=PALE if key==page else NAV,fg=NAV if key==page else '#CFDED3')
        if page=='overview':
            self.views[page].refresh()
        else:
            self.views[page].refresh_list()
        self.active=page

    def help(self):
        note_window(self.root,'Try the order desk',
                    'Daily overview\nChoose a historical day, select an order, and inspect its reason. Click a decision count to filter the list. Contribution & scenarios explains the financial estimate. Adjust assumptions creates a temporary what-if; the baseline stays unchanged.\n\nConfirmations\nStart an example, then act as its customer using the reply buttons. Update details fixes an incomplete name/address. Simulate payment and Advance time exercise the mock flow.\n\nAll messages, payments and shipments are simulated. No WhatsApp login, API key, internet or paid service is needed. Historical financial estimates are hypothetical; the September evaluation remains negative. Exported daily reports include the settings and source context.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--page',choices=('overview','confirmations'),default='overview')
    parser.add_argument('--db',type=Path,default=ROOT/'data/simulator/conversations.sqlite')
    args=parser.parse_args()
    import tkinter as tk
    root=tk.Tk()
    Workspace(root,args.page,simulator_path=args.db)
    root.mainloop()


if __name__=='__main__':
    main()

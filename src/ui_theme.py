"""Shared, dependency-free desktop styling and readable operational labels."""

from decimal import Decimal,InvalidOperation

BG='#F3F5F1'
PAPER='#FFFFFF'
INK='#21362C'
MUTED='#65756B'
LINE='#DDE5DC'
ACCENT='#25694D'
PALE='#E9F2EB'
NAV='#19382C'
RED='#AA4038'
AMBER='#986326'

STATES={
 'awaiting_confirmation':'Waiting for confirmation','awaiting_payment':'Waiting for payment',
 'awaiting_details':'Delivery details needed','ready_to_ship_cod':'Ready to ship · COD',
 'ready_to_ship_prepaid':'Ready to ship · Prepaid','held_for_review':'Operations review',
 'cancelled':'Cancelled by customer','historical_replay':'Historical replay',
 'pending':'Pending','not_offered':'Not offered','verified':'Payment verified',
 'failed':'Payment failed','expired':'Offer expired','closed':'Offer closed',
 'late_or_mismatched_success':'Payment needs review','not_observed':'Not observed',
 'DELIVERED':'Delivered','RTO':'Returned to origin','IN_TRANSIT':'In transit',
}


def readable(value):
    return STATES.get(value,str(value).replace('_',' ').capitalize())


def currency(value):
    if value in (None,''):
        return '—'
    try:
        amount=Decimal(str(value))
        if not amount.is_finite():
            return '—'
    except (InvalidOperation,ValueError):
        return '—'
    return ('−' if amount<0 else '')+f'₹{abs(amount):,.2f}'


def apply_theme(root):
    from tkinter import ttk
    root.configure(background=BG)
    style=ttk.Style(root)
    style.theme_use('clam')
    style.configure('.',font=('Segoe UI',10),background=BG,foreground=INK)
    for name,color in [('TFrame',BG),('Paper.TFrame',PAPER)]:
        style.configure(name,background=color)
    for name,bg,fg,size,weight in (
        ('TLabel',BG,INK,10,'normal'),('Muted.TLabel',BG,MUTED,10,'normal'),
        ('Title.TLabel',BG,INK,24,'bold'),('Section.TLabel',BG,INK,12,'bold'),
        ('Paper.TLabel',PAPER,INK,10,'normal'),('PaperMuted.TLabel',PAPER,MUTED,9,'normal'),
        ('PaperTitle.TLabel',PAPER,INK,12,'bold'),('Number.TLabel',PAPER,INK,25,'bold'),
        ('Money.TLabel',PAPER,INK,22,'bold'),('PositiveMoney.TLabel',PAPER,ACCENT,22,'bold'),
        ('NegativeMoney.TLabel',PAPER,RED,22,'bold')):
        style.configure(name,background=bg,foreground=fg,font=('Segoe UI',size,weight))
    style.configure('TButton',background=PAPER,foreground=INK,bordercolor=LINE,
                    lightcolor=PAPER,darkcolor=PAPER,padding=(12,8),relief='flat')
    style.map('TButton',background=[('active',PALE),('disabled',BG)],foreground=[('disabled','#9BA79E')])
    style.configure('Accent.TButton',background=ACCENT,foreground=PAPER,bordercolor=ACCENT,padding=(14,9))
    style.map('Accent.TButton',background=[('active','#1D553D'),('disabled','#B8C9BB')],foreground=[('disabled',PAPER)])
    style.configure('TEntry',padding=8,fieldbackground=PAPER,bordercolor=LINE,lightcolor=LINE,darkcolor=LINE)
    style.map('TEntry',bordercolor=[('focus',ACCENT)])
    style.configure('TCombobox',padding=7,fieldbackground=PAPER,background=PAPER,bordercolor=LINE,arrowsize=12)
    style.map('TCombobox',fieldbackground=[('readonly',PAPER)],selectbackground=[('readonly',PAPER)],selectforeground=[('readonly',INK)])
    style.configure('TNotebook',background=BG,borderwidth=0,tabmargins=(0,0,0,0))
    style.configure('TNotebook.Tab',padding=(16,10),background=BG,foreground=MUTED,borderwidth=0)
    style.map('TNotebook.Tab',background=[('selected',PAPER)],foreground=[('selected',ACCENT)])
    style.configure('Treeview',background=PAPER,fieldbackground=PAPER,foreground=INK,rowheight=38,borderwidth=0,font=('Segoe UI',10))
    style.configure('Treeview.Heading',background='#EDF1EB',foreground=MUTED,font=('Segoe UI',9,'bold'),padding=(10,10),relief='flat')
    style.map('Treeview',background=[('selected',PALE)],foreground=[('selected',INK)])
    style.configure('Inbox.Treeview',rowheight=54)
    style.configure('TLabelframe',background=BG,bordercolor=LINE,relief='solid')
    style.configure('TLabelframe.Label',font=('Segoe UI',10,'bold'),foreground=INK,background=BG)
    return style


def set_window(root,title):
    root.title(title+' · Oytra order desk')
    width=max(1040,min(1360,root.winfo_screenwidth()-64))
    height=max(680,min(880,root.winfo_screenheight()-100))
    root.geometry(f'{width}x{height}')
    root.minsize(1040,680)
    apply_theme(root)


def paper(parent,**kwargs):
    import tkinter as tk
    return tk.Frame(parent,bg=PAPER,highlightbackground=LINE,highlightthickness=1,**kwargs)


def note_window(root,title,text):
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText
    window=tk.Toplevel(root)
    window.title(title)
    window.geometry('680x480')
    window.transient(root)
    body=ttk.Frame(window,padding=22)
    body.pack(fill='both',expand=True)
    ttk.Label(body,text=title,style='Section.TLabel').pack(anchor='w',pady=(0,14))
    content=ScrolledText(body,wrap='word',font=('Segoe UI',11),background=PAPER,foreground=INK,relief='flat',padx=14,pady=14)
    content.pack(fill='both',expand=True)
    content.insert('1.0',text)
    content.configure(state='disabled')
    ttk.Button(body,text='Close',command=window.destroy).pack(anchor='e',pady=(12,0))
    return window

import unittest
from pathlib import Path

from src.ui_theme import currency,readable
from test_data_pipeline import temporary_directory

try:
    import tkinter as tk
except ImportError:
    tk=None


class PresentationTests(unittest.TestCase):
    def test_money_and_missing_values_are_readable(self):
        self.assertEqual(currency('-889.3'),'−₹889.30')
        self.assertEqual(currency('1234.5'),'₹1,234.50')
        for value in (None,'','NaN','not a number','Infinity'):
            self.assertEqual(currency(value),'—')

    def test_operational_status_labels(self):
        self.assertEqual(readable('awaiting_details'),'Delivery details needed')
        self.assertEqual(readable('ready_to_ship_prepaid'),'Ready to ship · Prepaid')


@unittest.skipIf(tk is None,'Tkinter is not installed; backend tests remain available.')
class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        from src.app import Workspace
        try:
            self.root=tk.Tk()
            self.root.withdraw()
        except tk.TclError:
            self.skipTest('A Tk display is unavailable.')
        self.temp=temporary_directory()
        self.directory=Path(self.temp.__enter__())
        self.db=self.directory/'simulator.sqlite'
        self.app=Workspace(self.root,simulator_path=self.db)
        self.view=self.app.views['overview']
        self.view.day.set('2026-09-30')
        self.view.refresh()

    def tearDown(self):
        if hasattr(self,'root'):
            self.root.update_idletasks()
            self.root.destroy()
        if hasattr(self,'temp'):
            self.temp.__exit__(None,None,None)

    def test_overview_does_not_create_simulator_state(self):
        self.assertFalse(self.db.exists())
        self.assertEqual(self.view.view['order_count'],9)
        self.assertEqual(self.view.bucket_vars['ship_as_is'].get(),'6')

    def test_clickable_buckets_filter_and_search_without_changing_totals(self):
        self.view.filter_bucket('nudge_to_prepaid')
        self.assertEqual(len(self.view.orders.get_children()),1)
        self.assertEqual(self.view.bucket_vars['ship_as_is'].get(),'6')
        self.view.query.set('no-matching-order')
        self.assertEqual(len(self.view.orders.get_children()),0)
        self.assertIn('No orders match',self.view.detail.get('1.0','end'))

    def test_detail_panel_is_a_summary_not_json(self):
        identifier=self.view.orders.get_children()[0]
        self.view.orders.selection_set(identifier)
        self.view.select_order()
        text=self.view.detail.get('1.0','end')
        self.assertIn('Order value',text)
        self.assertIn('Observed outcome',text)
        self.assertNotIn('customer_prior_orders',text)
        self.assertNotIn('"quality_flags"',text)

    def test_navigation_preserves_date_and_scenario(self):
        self.app.show('confirmations')
        self.assertTrue(self.db.exists())
        self.app.show('overview')
        self.assertEqual(self.view.day.get(),'2026-09-30')
        self.assertEqual(self.app.active,'overview')

    def test_quick_replies_follow_existing_shipping_requirements(self):
        self.app.show('confirmations')
        sim=self.app.views['confirmations']
        sim.start()
        sim.quick_reply('YES')
        self.assertEqual(sim.state.get(),'Delivery details needed')
        self.assertFalse(sim.store.snapshot(sim.current)['can_ship'])
        sim.reply_text.set('ADDRESS: House 21, Gali 4, Station Road')
        sim.send()
        sim.quick_reply('YES')
        self.assertEqual(sim.state.get(),'Ready to ship · COD')
        self.assertTrue(sim.store.snapshot(sim.current)['can_ship'])

    def test_title_and_metric_styles_have_distinct_hierarchy(self):
        from tkinter import ttk
        style=ttk.Style(self.root)
        self.assertIn('24',str(style.lookup('Title.TLabel','font')))
        self.assertIn('22',str(style.lookup('Money.TLabel','font')))
        self.assertNotEqual(style.lookup('Title.TLabel','font'),style.lookup('TLabel','font'))


if __name__=='__main__':
    unittest.main()

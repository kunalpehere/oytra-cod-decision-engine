import copy
import csv
import hashlib
import json
import unittest
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path

from src.confirmation_flow import FlowStore
from src.dashboard_data import (BRIDGE,POSITIVE,DashboardData,check_day,export_daily,
                                financial_components,settings,validate_settings,yesterday_ist)
from src.data_pipeline import ROOT
from src.decision_engine import economics
from src.train_engine import simulate
from test_confirmation_flow import recommendation
from test_data_pipeline import order,temporary_directory


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.context=temporary_directory()
        self.directory=Path(self.context.__enter__())
        self.data=DashboardData(simulator_path=self.directory/'simulator.sqlite')
        self.settings=settings(self.data.artifact)

    def tearDown(self):
        self.context.__exit__(None,None,None)

    def test_yesterday_uses_ist_across_utc_midnight(self):
        # 19:00 UTC is 00:30 of the following date in IST.
        self.assertEqual(yesterday_ist(datetime(2026,10,29,19,tzinfo=timezone.utc)),'2026-10-29')
        with self.assertRaises(ValueError):
            yesterday_ist(datetime(2026,10,30))

    def test_latest_date_fallback_is_explicit(self):
        chosen=self.data.default_day(now=datetime(2026,10,30,tzinfo=timezone.utc))
        self.assertEqual(chosen['requested_yesterday'],'2026-10-29')
        self.assertEqual(chosen['selected_day'],'2026-09-30')
        self.assertTrue(chosen['fell_back_to_latest'])

    def test_empty_day_does_not_claim_zero_financial_impact(self):
        view=self.data.daily('2026-10-29')
        self.assertEqual(view['order_count'],0)
        self.assertEqual(sum(view['counts'].values()),0)
        self.assertIsNone(view['money'])
        with self.assertRaises(ValueError):
            check_day('2026-9-1')

    def test_financial_bridge_all_actions_and_outcomes(self):
        for action in ('ship_as_is','ship_after_confirmation','nudge_to_prepaid','hold_cancel'):
            for outcome in ('DELIVERED','RTO'):
                row=order(final_status=outcome)
                c=financial_components(row,action,.5,self.settings['policy'],self.settings['financial_assumptions'])
                bridge=sum((c[k] if k in POSITIVE else -c[k] for k in BRIDGE),Decimal(0))
                self.assertAlmostEqual(bridge,c['net_impact'],places=15)
                e=economics(row,.5,self.settings['policy'],self.settings['financial_assumptions'])
                self.assertEqual(c['policy_contribution'],e['conditional'][action]['rto' if outcome=='RTO' else 'genuine'])

    def test_ship_and_hold_hand_calculations(self):
        row=order()
        c=financial_components(row,'ship_as_is',.5,self.settings['policy'],self.settings['financial_assumptions'])
        self.assertEqual(c['baseline_contribution'],Decimal('402.38'))
        self.assertEqual(c['net_impact'],Decimal(0))
        c=financial_components(row,'hold_cancel',.5,self.settings['policy'],self.settings['financial_assumptions'])
        self.assertEqual(c['genuine_held_margin_at_risk'],Decimal('402.38'))
        self.assertEqual(c['net_impact'],Decimal('-402.38'))

    def test_negative_margin_holds_reconcile_without_fake_lost_profit(self):
        policy=dict(self.settings['policy'],delivered_margin_includes_fulfilment=False)
        c=financial_components(order(order_value='10'),'hold_cancel',.5,policy,self.settings['financial_assumptions'])
        self.assertEqual(c['genuine_held_margin_at_risk'],0)
        self.assertEqual(c['negative_held_margin_avoided'],Decimal('83.80'))
        self.assertEqual(c['net_impact'],Decimal('83.80'))

    def test_invalid_or_unresolved_orders_are_not_money_zeroes(self):
        for row in (order(order_value='0'),order(order_value='NaN'),order(final_status='IN_TRANSIT')):
            self.assertIsNone(financial_components(row,'ship_as_is',.5,self.settings['policy'],self.settings['financial_assumptions']))

    def test_september_reconciles_to_frozen_evaluation(self):
        total=Decimal(0)
        buckets={a:0 for a in ('ship_as_is','ship_after_confirmation','nudge_to_prepaid','hold_cancel')}
        orders=0
        for day in self.data.dates():
            if not day.startswith('2026-09'):
                continue
            view=self.data.daily(day)
            orders+=view['order_count']
            total+=Decimal(view['money']['net_impact']) if view['money'] else 0
            for action,count in view['counts'].items():
                buckets[action]+=count
        summary=json.loads((ROOT/'reports/engine/summary.json').read_text())['performance']['evaluation']
        self.assertEqual(orders,329)
        self.assertEqual(buckets,summary['buckets'])
        # Each daily headline is rounded to paise, while monthly totals round once.
        self.assertLessEqual(abs(total-Decimal(summary['net_impact_inr'])),Decimal('.15'))

    def test_daily_money_matches_phase3_simulation(self):
        rows=[r for r in self.data.rows if r['order_datetime'].startswith('2026-09-30') and r['final_status'] in ('RTO','DELIVERED')]
        phase3,_=simulate(self.data.artifact['model'],rows,self.settings['policy'],self.settings['financial_assumptions'])
        view=self.data.daily('2026-09-30')
        self.assertEqual(view['money']['net_impact'],phase3['net_impact_inr'])
        self.assertEqual(view['money']['avoided_rto_loss'],phase3['gross_avoided_rto_loss_inr'])

    def test_scenario_is_exploratory_and_does_not_mutate_frozen_artifact(self):
        before=(ROOT/'artifacts/decision_engine.json').read_bytes()
        candidate=copy.deepcopy(self.settings)
        candidate['policy']['genuine_confirmation_rate']=.75
        modified=self.data.daily('2026-09-30',scenario=candidate)
        self.assertEqual(modified['scenario'],'Exploratory what-if')
        self.assertNotEqual(modified['scenario_sha256'],self.data.daily('2026-09-30')['scenario_sha256'])
        self.assertEqual((ROOT/'artifacts/decision_engine.json').read_bytes(),before)
        self.assertEqual(self.data.frozen,self.settings)

    def test_settings_validation_and_empty_source(self):
        for key,value in [('forward_shipping',Decimal('-1')),('delivered_gross_margin',Decimal('1.2')),('brief_prepaid_rto_rate',Decimal('NaN'))]:
            candidate=copy.deepcopy(self.settings)
            candidate['financial_assumptions'][key]=value
            with self.assertRaises(ValueError):
                validate_settings(candidate)
        self.assertEqual(self.data.dates('simulator'),[])
        self.assertFalse(self.data.simulator_path.exists())

    def test_simulator_is_read_only_and_counts_initial_bucket_once(self):
        store=FlowStore(self.data.simulator_path,start='2026-10-30T09:00:00+05:30')
        row=order()
        store.start(row,recommendation(row))
        store.reply('A1','YES','yes')
        before=hashlib.sha256(self.data.simulator_path.read_bytes()).hexdigest()
        view=self.data.daily('2026-10-30','simulator')
        self.assertEqual(view['order_count'],1)
        self.assertEqual(view['counts']['ship_after_confirmation'],1)
        self.assertEqual(view['simulator_states'],{'ready_to_ship_cod':1})
        self.assertIsNone(view['money'])
        self.assertEqual(hashlib.sha256(self.data.simulator_path.read_bytes()).hexdigest(),before)
        store.reply('A1','NO','no')
        changed=self.data.daily('2026-10-30','simulator')
        self.assertEqual(changed['counts'],view['counts'])
        self.assertEqual(changed['mock_money']['explicit_cancellations'],1)

    def test_simulator_cannot_rewrite_initial_decisions_with_scenario(self):
        changed=copy.deepcopy(self.settings)
        changed['policy']['prepaid_discount_inr']=10
        with self.assertRaises(ValueError):
            self.data.daily('2026-10-30','simulator',changed)

    def test_broken_simulator_is_not_disguised_as_empty(self):
        self.data.simulator_path.write_bytes(b'not sqlite')
        with self.assertRaises(ValueError):
            self.data.daily('2026-10-30','simulator')

    def test_exports_match_view_and_are_reproducible(self):
        view=self.data.daily('2026-09-30')
        directory=export_daily(view,self.directory/'exports')
        before={p.name:p.read_bytes() for p in directory.iterdir()}
        self.assertEqual(directory,export_daily(view,self.directory/'exports'))
        self.assertEqual(before,{p.name:p.read_bytes() for p in directory.iterdir()})
        with (directory/'orders.csv').open(encoding='utf-8-sig',newline='') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),view['order_count'])
        self.assertNotIn('phone',rows[0])
        context=json.loads((directory/'context.json').read_text())
        self.assertEqual(context['scenario_sha256'],view['scenario_sha256'])
        self.assertEqual(context['money'],view['money'])

    def test_export_neutralizes_formula_text_without_changing_negative_money(self):
        view=self.data.daily('2026-09-30')
        view['orders'][0]['order_id']='=1+1'
        view['orders'][0]['net_impact']='-10.50'
        directory=export_daily(view,self.directory/'exports')
        with (directory/'orders.csv').open(encoding='utf-8-sig',newline='') as f:
            first=next(csv.DictReader(f))
        self.assertEqual(first['order_id'],"'=1+1")
        self.assertEqual(first['net_impact'],'-10.50')


if __name__=='__main__':
    unittest.main()

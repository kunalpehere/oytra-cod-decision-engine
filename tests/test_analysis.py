import csv
import json
import unittest
from decimal import Decimal
from pathlib import Path

from src.analysis import (ROOT, baseline, exclusion_reasons, group_for, history_valid,
                          load_assumptions, loss_per_rto, run_analysis, split_for, stats, wilson)
from src.data_pipeline import COLUMNS, EXTRA_COLUMNS, prepare, write_csv
from test_data_pipeline import order, temporary_directory


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.a = load_assumptions(ROOT/'config/financial_assumptions.json')

    def test_split_boundaries_and_invalid_dates(self):
        cases = {'2026-03-31 23:59': 'excluded_date', '2026-04-01 00:00': 'development',
                 '2026-07-31 23:59': 'development', '2026-08-01 00:00': 'validation',
                 '2026-08-31 23:59': 'validation', '2026-09-01 00:00': 'evaluation',
                 '2026-09-30 23:59': 'evaluation', '2026-10-01 00:00': 'excluded_date',
                 '2026-02-30 12:00': 'excluded_date', '': 'excluded_date'}
        for timestamp, expected in cases.items():
            self.assertEqual(split_for(timestamp), expected)

    def test_financial_arithmetic_and_accounting_sensitivity(self):
        result = baseline([order(order_value='1000'), order(order_id='A2', final_status='RTO')], self.a)
        self.assertEqual(loss_per_rto(self.a), Decimal('169.40'))
        self.assertEqual(result['delivered_gross_profit'], '620.00')
        self.assertEqual(result['expected_rto_loss'], '169.40')
        self.assertEqual(result['contribution_margin_includes_delivery'], '450.60')
        self.assertEqual(result['contribution_margin_excludes_delivery'], '360.60')

    def test_invalid_amounts_excluded_from_matched_financial_cohort(self):
        rows = [order(order_value='0'), order(order_value='NaN', final_status='RTO'),
                order(order_value='-10'), order(order_value='100', final_status='RTO')]
        result = baseline(rows, self.a)
        self.assertEqual(result['financially_eligible_orders'], 1)
        self.assertEqual(result['excluded_invalid_value_orders'], 3)
        self.assertEqual(result['expected_rto_loss'], '169.40')
        self.assertEqual(stats(rows)['orders'], 4)
        self.assertEqual(stats(rows)['valid_value_orders'], 1)

    def test_history_inconsistency_is_not_first_time(self):
        row = order(customer_prior_orders='0', customer_prior_rto='1')
        self.assertFalse(history_valid(row))
        self.assertEqual(group_for(row, 'customer_type'), 'unknown_or_inconsistent')
        for value in ['-1', '1.2', '', 'Infinity']:
            self.assertFalse(history_valid(order(customer_prior_orders=value)))
        self.assertEqual(group_for(order(customer_prior_orders='0'), 'customer_type'), 'first_time')

    def test_descriptive_band_boundaries(self):
        for value, band in [('0', 'unknown_or_invalid'), ('499.99', 'under_500'),
                            ('500', '500_to_999'), ('1000', '1000_to_1499'), ('1500', '1500_plus')]:
            self.assertEqual(group_for(order(order_value=value), 'order_value_band'), band)

    def test_exclusion_policy_keeps_ordinary_feature_defects(self):
        clean, _, _, _ = prepare([(2, order(city='', phone='123'))])
        self.assertEqual(exclusion_reasons(clean[0]), [])
        self.assertEqual(exclusion_reasons(dict(clean[0], final_status='IN_TRANSIT')), ['unresolved_outcome'])
        self.assertIn('non_cod', exclusion_reasons(dict(clean[0], payment_method='PREPAID')))
        self.assertIn('missing_or_conflicting_order_id', exclusion_reasons(dict(clean[0], quality_flags='conflicting_order_id')))

    def test_empty_rates_and_wilson_bounds(self):
        self.assertEqual(wilson(0, 0), ('', ''))
        self.assertEqual(stats([])['average_order_value'], '')
        low, high = map(float, wilson(5, 10))
        self.assertAlmostEqual(low, .236593, places=6)
        self.assertAlmostEqual(high, .763407, places=6)
        self.assertEqual(wilson(10, 10)[1], '1.000000')

    def test_assumptions_reject_invalid_probabilities_and_missing_costs(self):
        with temporary_directory() as temp:
            path = Path(temp)/'bad.json'
            raw = json.loads((ROOT/'config/financial_assumptions.json').read_text())
            for field, value in [('cod_share', '1.01'), ('forward_shipping', '-1'),
                                 ('delivered_gross_margin', 'NaN'), ('monthly_total_orders', '2.5')]:
                changed = dict(raw, **{field: value})
                path.write_text(json.dumps(changed), encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_assumptions(path)
            path.write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError):
                load_assumptions(path)

    def test_future_outcomes_cannot_change_development_summaries(self):
        with temporary_directory() as temp:
            root = Path(temp)
            source = root/'clean.csv'
            originals = [order(order_datetime='2026-07-31 23:59'), order(order_id='A2')]
            clean, _, _, _ = prepare(list(enumerate(originals, start=2)))
            write_csv(source, COLUMNS+EXTRA_COLUMNS, clean)
            first = run_analysis(source, output_root=root/'one')
            clean[1]['final_status'] = 'RTO'
            write_csv(source, COLUMNS+EXTRA_COLUMNS, clean)
            second = run_analysis(source, output_root=root/'two')
            self.assertEqual(first['scopes']['development'], second['scopes']['development'])
            def development_segments(directory):
                with directory.open(encoding='utf-8', newline='') as handle:
                    return [r for r in csv.DictReader(handle) if r['scope']=='development']
            self.assertEqual(development_segments(root/'one/reports/analysis/segments.csv'),
                             development_segments(root/'two/reports/analysis/segments.csv'))

    def test_sample_reconciliation_and_repeatability(self):
        with temporary_directory() as temp:
            root = Path(temp)
            summary = run_analysis(output_root=root)
            self.assertEqual(summary['outcome_analysis_orders'], 1987)
            self.assertEqual([summary['scopes'][s]['orders'] for s in ('development','validation','evaluation')], [1297,361,329])
            self.assertEqual(sum(summary['split_counts'].values()), 1988)
            with (root/'reports/analysis/financial_baseline.csv').open(newline='', encoding='utf-8') as f:
                finances = list(csv.DictReader(f))
            overall = finances[0]
            self.assertEqual(overall['financially_eligible_orders'], '1984')
            self.assertEqual(overall['expected_rto_loss'], '95711.00')
            self.assertEqual(overall['contribution_margin_includes_delivery'], '701658.60')
            for column in ['expected_rto_loss','delivered_revenue','contribution_margin_includes_delivery','contribution_margin_excludes_delivery']:
                self.assertEqual(sum(Decimal(r[column]) for r in finances if r['scope'].startswith('2026-')), Decimal(overall[column]))
            with (root/'reports/analysis/segments.csv').open(newline='', encoding='utf-8') as f:
                segments = list(csv.DictReader(f))
            for scope in ('overall','development','validation','evaluation'):
                for dimension in {r['dimension'] for r in segments}:
                    selected = [r for r in segments if r['scope']==scope and r['dimension']==dimension]
                    self.assertEqual(sum(int(r['orders']) for r in selected), summary['scopes'][scope]['orders'])
                    self.assertEqual(sum(int(r['rto']) for r in selected), summary['scopes'][scope]['rto'])
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            run_analysis(output_root=root)
            self.assertEqual(before, {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_malformed_input_rejected_without_outputs(self):
        with temporary_directory() as temp:
            root=Path(temp)
            source=root/'bad.csv'
            source.write_text('order_id\nA1\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                run_analysis(source, output_root=root/'out')
            self.assertFalse((root/'out').exists())


if __name__ == '__main__':
    unittest.main()

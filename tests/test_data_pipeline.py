import csv
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from src.data_pipeline import COLUMNS, normalize_phone, prepare, read_source, run_pipeline


@contextmanager
def temporary_directory():
    # Keep test writes within this checkout in restricted desktop environments.
    base = Path(__file__).resolve().parents[1] / 'tmp' / 'tests'
    base.mkdir(parents=True, exist_ok=True)
    context = tempfile.TemporaryDirectory(dir=base)
    if not Path(context.name).resolve().is_relative_to(base.resolve()):
        raise RuntimeError('Temporary test path escaped the workspace.')
    with context as directory:
        yield directory


def order(**changes):
    row = dict(zip(COLUMNS, (
        'A1', '2026-09-01 12:30', 'Customer', '9876543210', 'Flat 1, Main Road',
        'Mumbai', 'Maharashtra', '400001', '649', 'Shampoo|Towel', '2', '1', '0',
        'direct', 'Delhivery', 'COD', 'DELIVERED',
    )))
    row.update(changes)
    return row


def write_source(path, rows, columns=COLUMNS):
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


class PipelineTests(unittest.TestCase):
    def test_exact_duplicates_removed_but_different_orders_retained(self):
        a = order()
        clean, _, _, log = prepare([(2, a), (3, a.copy()), (4, order(order_id='A2'))])
        self.assertEqual([r['source_row'] for r in clean], [2, 4])
        self.assertEqual(log[0]['operation'], 'remove_exact_duplicate')
        self.assertIn('record 2', log[0]['detail'])

    def test_conflicting_ids_are_flagged_without_arbitrary_selection(self):
        clean, _, issues, _ = prepare([(2, order()), (3, order(order_value='700'))])
        self.assertEqual(len(clean), 2)
        self.assertTrue(all('conflicting_order_id' in r['quality_flags'] for r in clean))
        self.assertEqual(len(issues), 2)

    def test_normalization_is_logged_and_original_mapping_is_unchanged(self):
        original = order(final_status=' Rto ', payment_method='cod', phone='+91 98765 43210')
        clean, resolved, _, log = prepare([(2, original)])
        self.assertEqual(clean[0]['phone'], '9876543210')
        self.assertEqual(resolved[0]['final_status'], 'RTO')
        self.assertEqual(original['final_status'], ' Rto ')
        self.assertEqual({x['field'] for x in log}, {'phone', 'final_status', 'payment_method'})
        self.assertEqual(clean[0]['pincode'], '400001')

    def test_phone_formats_and_invalid_inputs(self):
        for phone in ['9876543210', '+91 98765-43210', '919876543210', '(987) 654-3210']:
            self.assertEqual(normalize_phone(phone), ('9876543210', True))
        for phone in ['1234567890', '987654321', 'abc9876543210', '++919876543210', '']:
            self.assertEqual(normalize_phone(phone), (phone, False))

    def test_unknown_and_unresolved_statuses_are_retained(self):
        rows = [(2, order()), (3, order(order_id='A2', final_status='IN_TRANSIT')),
                (4, order(order_id='A3', final_status='MYSTERY'))]
        clean, resolved, _, log = prepare(rows)
        self.assertEqual(len(clean), 3)
        self.assertEqual(len(resolved), 1)
        self.assertIn('unknown_status', clean[2]['quality_flags'])
        self.assertEqual(sum(x['operation'] == 'exclude_from_resolved' for x in log), 2)

    def test_missing_and_invalid_values_are_not_imputed(self):
        row = order(city='', pincode='012345', phone='123', order_datetime='2026-02-30 12:00',
                    order_value='0', num_items='-1', customer_prior_orders='0', customer_prior_rto='2')
        clean, resolved, issues, _ = prepare([(2, row)])
        codes = {x['issue'] for x in issues}
        self.assertTrue({'missing_city', 'invalid_pincode', 'invalid_phone', 'invalid_order_datetime',
                         'invalid_order_value', 'invalid_num_items', 'inconsistent_customer_history',
                         'item_count_mismatch'} <= codes)
        self.assertEqual(clean[0]['city'], '')
        self.assertEqual(clean[0]['order_value'], '0')
        self.assertEqual(len(resolved), 1)  # Resolved describes the outcome, not feature validity.

    def test_numeric_nonfinite_fractional_and_nonnumeric_values(self):
        for value in ['NaN', 'Infinity', 'not-a-number']:
            _, _, issues, _ = prepare([(2, order(order_value=value))])
            self.assertIn('invalid_order_value', {x['issue'] for x in issues})
        for value in ['1.5', '-1', 'NaN']:
            _, _, issues, _ = prepare([(2, order(customer_prior_orders=value))])
            self.assertIn('invalid_customer_prior_orders', {x['issue'] for x in issues})

    def test_schema_and_empty_data_fail_before_writing_outputs(self):
        with temporary_directory() as temp:
            root = Path(temp)
            source = root / 'source.csv'
            for contents in ['order_id\nA1\n', ','.join(COLUMNS) + '\n',
                             ','.join(COLUMNS + ('order_id',)) + '\n']:
                source.write_text(contents, encoding='utf-8')
                with self.assertRaises(ValueError):
                    run_pipeline(source, root / 'output')
                self.assertFalse((root / 'output').exists())

    def test_wrong_record_width_is_rejected(self):
        with temporary_directory() as temp:
            path = Path(temp) / 'bad.csv'
            for record in ['A1,too,few', ','.join(['x'] * 18)]:
                path.write_text(','.join(COLUMNS) + '\n' + record + '\n', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'wrong field count'):
                    read_source(path)

    def test_multiline_csv_records_and_reordered_headers(self):
        with temporary_directory() as temp:
            source = Path(temp) / 'source.csv'
            write_source(source, [order(address='Flat 1,\nMain Road')], tuple(reversed(COLUMNS)))
            rows = read_source(source)
            self.assertEqual(rows[0][0], 2)
            self.assertEqual(rows[0][1]['address'], 'Flat 1,\nMain Road')

    def test_repeatable_outputs_and_source_preservation(self):
        with temporary_directory() as temp:
            root = Path(temp)
            source = root / 'source.csv'
            write_source(source, [order(final_status='delivered'), order(final_status='delivered'),
                                 order(order_id='A2', final_status='IN_TRANSIT')])
            original = source.read_bytes()
            summary = run_pipeline(source, root / 'output')
            self.assertEqual(summary['input_rows'], 3)
            self.assertEqual(summary['exact_duplicates_removed'], 1)
            self.assertEqual(summary['resolved_orders'], 1)
            files = {p.relative_to(root / 'output'): p.read_bytes()
                     for p in (root / 'output').rglob('*') if p.is_file()}
            self.assertEqual(summary, run_pipeline(source, root / 'output'))
            self.assertEqual(source.read_bytes(), original)
            for relative, content in files.items():
                self.assertEqual((root / 'output' / relative).read_bytes(), content)

    def test_supplied_sample_reconciliation(self):
        source = Path(__file__).resolve().parents[1] / 'data/raw/orders_sample.csv'
        with temporary_directory() as temp:
            summary = run_pipeline(source, Path(temp))
        self.assertEqual(summary['input_rows'], 2018)
        self.assertEqual(summary['exact_duplicates_removed'], 30)
        self.assertEqual(summary['unique_orders_retained'], 1988)
        self.assertEqual(summary['resolved_orders'], 1987)
        self.assertEqual(summary['unresolved_orders'], 1)
        self.assertEqual(summary['resolved_outcomes'], {'DELIVERED': 1422, 'RTO': 565})


if __name__ == '__main__':
    unittest.main()

"""Deterministic, standard-library-only preparation of historical COD orders."""

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = (
    'order_id', 'order_datetime', 'customer_name', 'phone', 'address', 'city',
    'state', 'pincode', 'order_value', 'items', 'num_items',
    'customer_prior_orders', 'customer_prior_rto', 'utm_source', 'courier',
    'payment_method', 'final_status',
)
EXTRA_COLUMNS = ('source_row', 'quality_flags', 'outcome_resolved')
RESOLVED = {'DELIVERED', 'RTO'}
KNOWN_STATUSES = RESOLVED | {'IN_TRANSIT'}
ISSUE_COLUMNS = ('source_row', 'order_id', 'field', 'issue', 'value', 'detail')
LOG_COLUMNS = ('source_row', 'order_id', 'operation', 'field', 'before', 'after', 'detail')


def read_source(path):
    """Reject malformed file structure before publishing any outputs."""
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)):
            raise ValueError('Duplicate CSV column names.')
        missing, extra = set(COLUMNS) - set(headers), set(headers) - set(COLUMNS)
        if missing or extra:
            raise ValueError(f'Schema mismatch: missing={sorted(missing)}, unexpected={sorted(extra)}')
        rows = []
        for record, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'Malformed CSV record {record}: wrong field count.')
            rows.append((record, row))
    if not rows:
        raise ValueError('CSV contains no orders.')
    return rows


def normalize_phone(value):
    """Accept domestic or +91/91 numbers with spaces, parentheses or hyphens."""
    if not re.fullmatch(r'\+?[0-9 ()-]+', value):
        return value, False
    digits = re.sub(r'[^0-9]', '', value)
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    valid = bool(re.fullmatch(r'[6-9][0-9]{9}', digits))
    return (digits if valid else value), valid


def prepare(rows):
    """Retain questionable unique orders and attach review flags; never infer missing facts."""
    clean, issues, log, seen = [], [], [], {}

    def event(record, order, operation, field='', before='', after='', detail=''):
        log.append(dict(zip(LOG_COLUMNS, (record, order, operation, field, before, after, detail))))

    def flag(row, field, code, detail):
        row['_flags'].add(code)
        issues.append(dict(zip(ISSUE_COLUMNS, (
            row['source_row'], row['order_id'], field, code, row[field], detail,
        ))))

    for record, original in rows:
        fingerprint = tuple(original[key] for key in COLUMNS)
        if fingerprint in seen:
            event(record, original['order_id'], 'remove_exact_duplicate',
                  detail=f'Identical to source record {seen[fingerprint]}.')
            continue
        seen[fingerprint] = record
        row = {key: original[key].strip() for key in COLUMNS}
        row.update(source_row=record, _flags=set())
        for key in ('final_status', 'payment_method'):
            row[key] = row[key].upper()
        row['phone'], phone_valid = normalize_phone(row['phone'])
        for key in COLUMNS:
            if original[key] != row[key]:
                event(record, row['order_id'], 'normalize', key, original[key], row[key],
                      'Trim outer whitespace, standardize label case, or normalize valid phone formatting.')
            if not row[key]:
                flag(row, key, f'missing_{key}', 'Required source value is missing; retained without imputation.')

        if row['phone'] and not phone_valid:
            flag(row, 'phone', 'invalid_phone', 'Expected a 10-digit Indian mobile number starting with 6-9.')
        if row['pincode'] and not re.fullmatch(r'[1-9][0-9]{5}', row['pincode']):
            flag(row, 'pincode', 'invalid_pincode', 'Expected six digits, first digit nonzero; no serviceability claim.')
        if row['order_datetime']:
            try:
                parsed = datetime.strptime(row['order_datetime'], '%Y-%m-%d %H:%M')
                if parsed.strftime('%Y-%m-%d %H:%M') != row['order_datetime']:
                    raise ValueError('Noncanonical format')
            except ValueError:
                flag(row, 'order_datetime', 'invalid_order_datetime', 'Expected a valid YYYY-MM-DD HH:MM; timezone unspecified by source.')

        numeric = {}
        for key in ('order_value', 'num_items', 'customer_prior_orders', 'customer_prior_rto'):
            if not row[key]:
                continue
            try:
                value = Decimal(row[key])
                if not value.is_finite() or (key != 'order_value' and value != value.to_integral_value()):
                    raise ValueError('Nonfinite or noninteger count')
                numeric[key] = value
                if value < 0 or (key in ('order_value', 'num_items') and value == 0):
                    flag(row, key, f'invalid_{key}', 'Value must be positive for order value/item count, nonnegative for history counts.')
            except (InvalidOperation, ValueError):
                flag(row, key, f'invalid_{key}', 'Expected a finite number; counts must be integers.')
        if {'customer_prior_orders', 'customer_prior_rto'} <= numeric.keys():
            if numeric['customer_prior_rto'] > numeric['customer_prior_orders']:
                flag(row, 'customer_prior_rto', 'inconsistent_customer_history', 'Prior RTO count exceeds prior order count; neither value was changed.')
        if row['items'] and 'num_items' in numeric:
            items = row['items'].split('|')
            if any(not item.strip() for item in items) or len(items) != numeric['num_items']:
                flag(row, 'items', 'item_count_mismatch', 'Pipe-separated nonempty items should match num_items.')
        if row['payment_method'] and row['payment_method'] != 'COD':
            flag(row, 'payment_method', 'non_cod_order', 'This dataset is intended for COD orders.')
        if row['final_status'] not in KNOWN_STATUSES and row['final_status']:
            flag(row, 'final_status', 'unknown_status', 'Unknown outcome retained but excluded from resolved outcomes.')
        row['outcome_resolved'] = str(row['final_status'] in RESOLVED).lower()
        if row['final_status'] not in RESOLVED:
            flag(row, 'final_status', 'unresolved_outcome', 'Retained in clean data; excluded from orders_resolved.csv.')
            event(record, row['order_id'], 'exclude_from_resolved', 'final_status', row['final_status'], '',
                  'No resolved delivered/RTO outcome.')
        clean.append(row)

    by_id = Counter(row['order_id'] for row in clean if row['order_id'])
    for row in clean:
        if row['order_id'] and by_id[row['order_id']] > 1:
            flag(row, 'order_id', 'conflicting_order_id', 'Multiple nonidentical source records share this ID; all retained for review.')
        row['quality_flags'] = '|'.join(sorted(row.pop('_flags')))
    resolved = [row for row in clean if row['outcome_resolved'] == 'true']
    return clean, resolved, issues, log


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def run_pipeline(source=ROOT / 'data/raw/orders_sample.csv', output_root=ROOT):
    source, output_root = Path(source), Path(output_root)
    rows = read_source(source)
    clean, resolved, issues, log = prepare(rows)
    processed, reports = output_root / 'data/processed', output_root / 'reports'
    summary = {
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'input_rows': len(rows),
        'exact_duplicates_removed': len(rows) - len(clean),
        'unique_orders_retained': len(clean),
        'resolved_orders': len(resolved),
        'unresolved_orders': len(clean) - len(resolved),
        'flagged_retained_orders': sum(bool(row['quality_flags']) for row in clean),
        'normalization_events': sum(item['operation'] == 'normalize' for item in log),
        'resolved_outcomes': dict(sorted(Counter(row['final_status'] for row in resolved).items())),
        'issue_counts': dict(sorted(Counter(item['issue'] for item in issues).items())),
    }
    write_csv(processed / 'orders_clean.csv', COLUMNS + EXTRA_COLUMNS, clean)
    write_csv(processed / 'orders_resolved.csv', COLUMNS + EXTRA_COLUMNS, resolved)
    write_csv(reports / 'data_quality_issues.csv', ISSUE_COLUMNS, issues)
    write_csv(reports / 'data_transformation_log.csv', LOG_COLUMNS, log)
    reports.mkdir(parents=True, exist_ok=True)
    (reports / 'data_quality_summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    outcomes = summary['resolved_outcomes']
    rate = f"{100 * outcomes.get('RTO', 0) / len(resolved):.2f}%" if resolved else 'unavailable'
    lines = [
        '# Data quality report', '',
        'Source: the assignment orders_sample.csv. Generated by src/data_pipeline.py.', '',
        f"Source SHA-256: `{summary['source_sha256']}`", '',
        '| Metric | Count |', '| --- | ---: |',
        *[f'| {key.replace("_", " ")} | {summary[key]} |' for key in (
            'input_rows', 'exact_duplicates_removed', 'unique_orders_retained',
            'resolved_orders', 'unresolved_orders', 'flagged_retained_orders', 'normalization_events')],
        f"| Delivered | {outcomes.get('DELIVERED', 0)} |", f"| RTO | {outcomes.get('RTO', 0)} |", '',
        f'Resolved-order RTO rate: **{rate}**. Denominator: all unique records with DELIVERED or RTO outcomes, including quality-flagged records.', '',
        '## Issues in retained records', '', '| Issue | Count |', '| --- | ---: |',
        *[f'| {code} | {count} |' for code, count in summary['issue_counts'].items()], '',
        'Counts refer to issue occurrences; one record can have several flags. Duplicate removals are recorded separately in the transformation log.', '',
        '## Treatment and limitations', '',
        '- Raw input is unchanged. Exact duplicates are identified before normalization; the first record is kept.',
        '- source_row is the CSV record number including the header as record 1. It is not a physical line number for quoted multiline fields.',
        '- Only outer whitespace, status/payment case, and valid phone formatting are normalized. Every changed source field is logged with before/after values.',
        '- Phones and pincodes remain strings. Format checks cannot prove ownership, geographic validity, or courier serviceability.',
        '- Missing values, invalid numbers, invalid dates and conflicting IDs are retained with flags. No values are guessed or repaired.',
        '- Resolved means a known delivered/RTO label only. orders_resolved.csv is not automatically model-ready: review flags and conflicting IDs before training or financial aggregation.',
        '- Dates have no timezone in the supplied file; no timezone conversion or date imputation is performed.',
        '- Different order IDs with similar customer, address or basket details are retained. No fuzzy deduplication is performed.',
        '- final_status, outcome_resolved and outcome-derived quality flags are audit/evaluation metadata, never prediction features.',
        '- No model, LLM, risk thresholds, cancellation rules, or intervention savings are implemented in Phase 1.', '',
        'See data_quality_issues.csv for review details and data_transformation_log.csv for all normalizations, exact-duplicate removals and unresolved-outcome exclusions.', '',
    ]
    (reports / 'data_quality_report.md').write_text('\n'.join(lines), encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'data/raw/orders_sample.csv')
    parser.add_argument('--output-root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        summary = run_pipeline(args.input, args.output_root)
    except (ValueError, OSError, csv.Error) as error:
        parser.exit(1, f'Pipeline failed: {error}\n')
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()

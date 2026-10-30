"""Phase 2: descriptive RTO analysis, financial baseline and chronological membership.

No model is trained, no intervention effects are inferred, and no outcome-derived
prediction features are produced. Outputs are deterministic and dependency-free.
"""

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html import escape
from pathlib import Path

from src.data_pipeline import ROOT, COLUMNS, EXTRA_COLUMNS, write_csv

D = Decimal
SCOPES = ('overall', 'development', 'validation', 'evaluation')
DIMENSIONS = ('month', 'customer_type', 'prior_rto', 'utm_source', 'courier',
              'state', 'city', 'pincode', 'order_value_band', 'num_items', 'order_hour')
GROUP_COLUMNS = ('scope', 'dimension', 'group', 'orders', 'delivered', 'rto',
                 'rto_rate', 'wilson_95_low', 'wilson_95_high', 'small_sample',
                 'valid_value_orders', 'average_order_value')


def number(value):
    try:
        result = D(value)
        return result if result.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def money(value):
    return str(value.quantize(D('.01'), rounding=ROUND_HALF_UP))


def load_assumptions(path):
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    names = ('forward_shipping', 'return_shipping', 'packaging_handling',
             'returned_damage_probability', 'average_product_cost', 'delivered_gross_margin',
             'monthly_total_orders', 'cod_share', 'brief_cod_rto_rate',
             'brief_prepaid_rto_rate', 'brief_average_order_value')
    result = {key: number(raw.get(key)) for key in names}
    if any(value is None or value < 0 for value in result.values()):
        raise ValueError('Financial assumptions must contain finite nonnegative numbers.')
    for key in ('returned_damage_probability', 'delivered_gross_margin', 'cod_share',
                'brief_cod_rto_rate', 'brief_prepaid_rto_rate'):
        if result[key] > 1:
            raise ValueError(f'{key} must be between 0 and 1.')
    if result['monthly_total_orders'] != result['monthly_total_orders'].to_integral_value():
        raise ValueError('monthly_total_orders must be an integer.')
    return result


def split_for(timestamp):
    try:
        dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M')
        if dt.strftime('%Y-%m-%d %H:%M') != timestamp:
            return 'excluded_date'
    except (ValueError, TypeError):
        return 'excluded_date'
    if datetime(2026, 4, 1) <= dt < datetime(2026, 8, 1):
        return 'development'
    if datetime(2026, 8, 1) <= dt < datetime(2026, 9, 1):
        return 'validation'
    if datetime(2026, 9, 1) <= dt < datetime(2026, 10, 1):
        return 'evaluation'
    return 'excluded_date'


def exclusion_reasons(row):
    reasons = []
    if row['final_status'] not in {'DELIVERED', 'RTO'}:
        reasons.append('unresolved_outcome')
    if row['payment_method'] != 'COD':
        reasons.append('non_cod')
    if not row['order_id'] or 'conflicting_order_id' in row['quality_flags'].split('|'):
        reasons.append('missing_or_conflicting_order_id')
    return reasons


def valid_value(row):
    value = number(row['order_value'])
    return value if value is not None and value > 0 else None


def history_valid(row):
    prior, rto = number(row['customer_prior_orders']), number(row['customer_prior_rto'])
    return (prior is not None and rto is not None and prior >= 0 and rto >= 0
            and prior == prior.to_integral_value() and rto == rto.to_integral_value() and rto <= prior)


def group_for(row, dimension):
    if dimension in ('customer_type', 'prior_rto'):
        if not history_valid(row):
            return 'unknown_or_inconsistent'
        field = 'customer_prior_orders' if dimension == 'customer_type' else 'customer_prior_rto'
        return ('first_time' if dimension == 'customer_type' else 'no_prior_rto') if D(row[field]) == 0 else (
            'repeat' if dimension == 'customer_type' else 'has_prior_rto')
    if dimension == 'month':
        return row['order_datetime'][:7] if split_for(row['order_datetime']) != 'excluded_date' else 'unknown_or_outside_period'
    if dimension == 'order_hour':
        if split_for(row['order_datetime']) == 'excluded_date':
            return 'unknown_or_outside_period'
        hour = int(row['order_datetime'][11:13])
        return ('00-05', '06-11', '12-17', '18-23')[hour // 6]
    if dimension == 'order_value_band':
        value = valid_value(row)
        if value is None:
            return 'unknown_or_invalid'
        return 'under_500' if value < 500 else '500_to_999' if value < 1000 else '1000_to_1499' if value < 1500 else '1500_plus'
    if dimension == 'num_items':
        value = number(row['num_items'])
        return str(int(value)) if value is not None and value > 0 and value == value.to_integral_value() else 'unknown_or_invalid'
    return row[dimension] or '(missing)'


def wilson(successes, total):
    if total == 0:
        return '', ''
    z, p = 1.959963984540054, successes / total
    center = (p + z*z/(2*total)) / (1 + z*z/total)
    half = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total)) / (1 + z*z/total)
    return f'{max(0, center-half):.6f}', f'{min(1, center+half):.6f}'


def stats(rows):
    n, rto = len(rows), sum(row['final_status'] == 'RTO' for row in rows)
    amounts = [valid_value(row) for row in rows if valid_value(row) is not None]
    low, high = wilson(rto, n)
    return dict(orders=n, delivered=n-rto, rto=rto, rto_rate=f'{rto/n:.6f}' if n else '',
                wilson_95_low=low, wilson_95_high=high, small_sample=str(n < 30).lower(),
                valid_value_orders=len(amounts), average_order_value=money(sum(amounts, D(0))/len(amounts)) if amounts else '')


def loss_per_rto(a):
    return a['forward_shipping'] + a['return_shipping'] + a['packaging_handling'] + a['returned_damage_probability'] * a['average_product_cost']


def baseline(rows, a):
    """Matched cohort: do not count returned orders whose values were excluded elsewhere."""
    eligible = [row for row in rows if valid_value(row) is not None]
    delivered = [row for row in eligible if row['final_status'] == 'DELIVERED']
    rto_count = sum(row['final_status'] == 'RTO' for row in eligible)
    revenue = sum((valid_value(row) for row in delivered), D(0))
    gross = revenue * a['delivered_gross_margin']
    losses = rto_count * loss_per_rto(a)
    delivery_costs = len(delivered) * (a['forward_shipping'] + a['packaging_handling'])
    return dict(orders_in_scope=len(rows), financially_eligible_orders=len(eligible),
                excluded_invalid_value_orders=len(rows)-len(eligible), delivered=len(delivered), rto=rto_count,
                delivered_revenue=money(revenue), delivered_gross_profit=money(gross),
                expected_rto_loss=money(losses),
                contribution_margin_includes_delivery=money(gross-losses),
                additional_delivered_fulfilment_cost=money(delivery_costs),
                contribution_margin_excludes_delivery=money(gross-losses-delivery_costs))


def chart(path, title, records):
    """Dependency-free business bar chart with counts, Wilson intervals and text labels."""
    height = 140 + 55 * len(records)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="{height}" viewBox="0 0 960 {height}" role="img">',
           f'<title>{escape(title)}</title>', '<rect width="100%" height="100%" fill="#fff"/>',
           '<g font-family="Arial,sans-serif" fill="#172b4d">',
           f'<text x="24" y="35" font-size="22">{escape(title)}</text>',
           '<text x="24" y="61" font-size="13">Observed RTO rates; whiskers: approximate 95% Wilson intervals. Descriptive, not causal.</text>']
    for i, r in enumerate(records):
        y, rate = 95 + i*55, float(r['rto_rate'])
        low, high = float(r['wilson_95_low']), float(r['wilson_95_high'])
        svg.extend([f'<text x="24" y="{y+17}" font-size="14">{escape(r["group"])}</text>',
                    f'<rect x="245" y="{y}" width="{rate*450:.2f}" height="25" fill="#137c8b"/>',
                    f'<path d="M {245+low*450:.2f} {y+12} H {245+high*450:.2f}" stroke="#172b4d" stroke-width="2"/>',
                    f'<text x="725" y="{y+17}" font-size="14">{rate:.1%} ({r["rto"]}/{r["orders"]})</text>'])
    svg.extend([f'<text x="245" y="{height-22}" font-size="12">Scale: 0% to 100%; denominator shown for each group.</text>', '</g></svg>'])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(svg) + '\n', encoding='utf-8')


def run_analysis(input_path=ROOT/'data/processed/orders_clean.csv',
                 assumptions_path=ROOT/'config/financial_assumptions.json', output_root=ROOT):
    input_path, assumptions_path, output_root = Path(input_path), Path(assumptions_path), Path(output_root)
    a = load_assumptions(assumptions_path)
    with input_path.open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        expected = COLUMNS + EXTRA_COLUMNS
        if reader.fieldnames != list(expected):
            raise ValueError('Expected Phase 1 orders_clean.csv schema and column order.')
        rows = list(reader)
    if not rows or any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError('Input is empty or contains malformed records.')
    if len({r['source_row'] for r in rows}) != len(rows):
        raise ValueError('Duplicate source_row identifiers; regenerate Phase 1.')
    # Recheck ambiguous IDs instead of trusting only upstream flags.
    counts = Counter(r['order_id'] for r in rows)
    if any(counts[r['order_id']] > 1 and 'conflicting_order_id' not in r['quality_flags'].split('|') for r in rows):
        raise ValueError('Unflagged conflicting IDs; regenerate Phase 1.')
    population = [r for r in rows if not exclusion_reasons(r)]
    scopes = {s: [r for r in population if s == 'overall' or split_for(r['order_datetime']) == s] for s in SCOPES}
    groups = []
    for scope, subset in scopes.items():
        for dimension in DIMENSIONS:
            buckets = defaultdict(list)
            for row in subset:
                buckets[group_for(row, dimension)].append(row)
            groups.extend(dict(scope=scope, dimension=dimension, group=key, **stats(buckets[key])) for key in sorted(buckets))
    memberships = []
    for row in rows:
        reasons = exclusion_reasons(row)
        memberships.append(dict(source_row=row['source_row'], order_id=row['order_id'], order_datetime=row['order_datetime'],
                                split=split_for(row['order_datetime']), outcome_analysis_eligible=str(not reasons).lower(),
                                exclusions='|'.join(reasons), financial_eligible=str(not reasons and valid_value(row) is not None).lower(),
                                history_features_usable=str(history_valid(row)).lower(), quality_flags=row['quality_flags']))
    sensitivity = []
    for scope, subset in scopes.items():
        for cohort, selected in [('all_eligible_resolved', subset), ('no_quality_flags', [r for r in subset if not r['quality_flags']])]:
            sensitivity.append(dict(scope=scope, cohort=cohort, **stats(selected)))
    finances = [dict(scope=s, **baseline(subset, a)) for s, subset in scopes.items()]
    # Also expose monthly financial totals to reconcile the full-sample result.
    for month in sorted({group_for(r, 'month') for r in population}):
        finances.append(dict(scope=month, **baseline([r for r in population if group_for(r, 'month') == month], a)))
    summary = dict(input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
                   assumptions_sha256=hashlib.sha256(assumptions_path.read_bytes()).hexdigest(),
                   retained_input_orders=len(rows), outcome_analysis_orders=len(population),
                   excluded_outcome_analysis_orders=len(rows)-len(population),
                   split_counts=dict(sorted(Counter(m['split'] for m in memberships).items())),
                   rto_loss_per_order=money(loss_per_rto(a)), scopes={s: stats(subset) for s, subset in scopes.items()})
    report_dir = output_root/'reports/analysis'
    write_csv(report_dir/'segments.csv', GROUP_COLUMNS, groups)
    write_csv(report_dir/'cohort_sensitivity.csv', ('scope', 'cohort')+tuple(stats([])), sensitivity)
    write_csv(report_dir/'financial_baseline.csv', tuple(finances[0]), finances)
    write_csv(output_root/'data/processed/split_membership.csv', tuple(memberships[0]), memberships)
    treatment = {
        'invalid_order_value': 'Retain outcome; exclude from amount averages and matched financial cohort.',
        'missing_order_value': 'Retain outcome; exclude from amount averages and matched financial cohort.',
        'inconsistent_customer_history': 'Retain outcome; history grouped as unknown and history features unusable.',
        'invalid_phone': 'Retain outcome and economics; do not treat phone as a verified customer identity.',
        'missing_city': 'Retain; city grouped as (missing).',
        'missing_pincode': 'Retain; pincode grouped as (missing).',
        'unresolved_outcome': 'Exclude from outcome analysis and financial baseline; retain date membership.',
        'conflicting_order_id': 'Exclude all conflicting records from outcome analysis and economics.',
    }
    flag_counts = Counter(flag for row in rows for flag in row['quality_flags'].split('|') if flag)
    reviews = [dict(flag=flag, retained_records=count,
                    treatment=treatment.get(flag, 'Retain with flag; validate the affected feature separately before modeling.'))
               for flag, count in sorted(flag_counts.items())]
    write_csv(report_dir/'quality_review.csv', ('flag', 'retained_records', 'treatment'), reviews)
    (report_dir/'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    for dimension, title in [('month', 'Monthly RTO rate - all eligible resolved orders'),
                             ('customer_type', 'Customer history and RTO - development orders'),
                             ('courier', 'Courier and RTO - development orders')]:
        scope = 'overall' if dimension == 'month' else 'development'
        chart(report_dir/'charts'/f'{dimension}.svg', title, [g for g in groups if g['scope']==scope and g['dimension']==dimension])
    write_report(report_dir, summary, groups, sensitivity, finances, a)
    return summary


def write_report(directory, summary, groups, sensitivity, finances, a):
    development = [g for g in groups if g['scope'] == 'development']
    findings = []
    for dimension in ('customer_type', 'prior_rto', 'utm_source', 'courier'):
        parts = [f"{g['group']}: {g['rto']}/{g['orders']} ({float(g['rto_rate']):.2%})" for g in development if g['dimension'] == dimension]
        findings.append(f'- **{dimension.replace("_", " ")}**: ' + '; '.join(parts) + '.')
    pincodes = [g for g in development if g['dimension']=='pincode' and g['group']!='(missing)']
    small = sum(g['orders'] < 30 for g in pincodes)
    findings.append(f'- **Pincode sparsity:** {small}/{len(pincodes)} observed development pincodes have fewer than 30 orders. Do not use raw pincode rates as cancellation rules.')
    development_stats = summary['scopes']['development']
    findings.append(f"- **Order values differ from the brief:** development AOV is INR {development_stats['average_order_value']} across {development_stats['valid_value_orders']} positive-value orders, versus the brief's INR {a['brief_average_order_value']}. Use actual order values for the sample baseline and keep the brief-based monthly projection separate.")
    monthly_cod = a['monthly_total_orders'] * a['cod_share']
    monthly_rto = monthly_cod * a['brief_cod_rto_rate']
    projection_loss = monthly_rto * loss_per_rto(a)
    average_gross = a['brief_average_order_value'] * a['delivered_gross_margin']
    projection_primary = (monthly_cod-monthly_rto)*average_gross-projection_loss
    projection_alternative = projection_primary-(monthly_cod-monthly_rto)*(a['forward_shipping']+a['packaging_handling'])
    financial_rows = '\n'.join(f"| {f['scope']} | {f['financially_eligible_orders']} | {f['excluded_invalid_value_orders']} | {f['expected_rto_loss']} | {f['contribution_margin_includes_delivery']} | {f['contribution_margin_excludes_delivery']} |" for f in finances)
    sensitivity_rows = '\n'.join(f"| {r['scope']} | {r['cohort']} | {r['orders']} | {float(r['rto_rate']):.2%} |" if r['orders'] else f"| {r['scope']} | {r['cohort']} | 0 | unavailable |" for r in sensitivity)
    text = f'''# Phase 2 - RTO analysis and ship-all baseline

## Population and provenance

Source: Phase 1 orders_clean.csv, derived from the supplied orders_sample.csv. Financial assumptions: assignment pages 1-2, recorded in config/financial_assumptions.json. No external rates are substituted.

Input SHA-256: `{summary['input_sha256']}`

Assumptions SHA-256: `{summary['assumptions_sha256']}`

{summary['retained_input_orders']} retained input records; {summary['outcome_analysis_orders']} eligible resolved COD records; {summary['excluded_outcome_analysis_orders']} excluded from outcome analysis. Missing/conflicting IDs, non-COD and unresolved labels are excluded; ordinary feature defects remain. Membership records show exclusions individually. Invalid/nonpositive amounts are excluded only from financial calculations and amount averages. Invalid history is grouped as unknown; it is never silently treated as a first-time customer.

## Development findings

Only April-July outcomes support the findings below; August and September remain visible in the supporting tables for evaluation and reconciliation. These associations are exploratory, unadjusted and do not establish causation or validated cancellation rules.

{chr(10).join(findings)}

Implications: preserve first-order growth by considering confirmation before cancellation; investigate customer history with other signals; investigate courier/serviceability patterns without assuming a courier change causes improvement. Acquisition-channel differences can reflect customer mix. Future customer value is unknown in this dataset.

## Exclusion sensitivity

| Scope | Cohort | Orders | RTO rate |
| --- | --- | ---: | ---: |
{sensitivity_rows}

The no-quality-flags cohort is a sensitivity check, not the selected training population. Feature-level missingness should be handled explicitly rather than dropping every imperfect order. quality_review.csv records the treatment of each observed flag; split_membership.csv records eligibility for every source record.

## Ship-all-COD financial baseline

All currency values below are INR. These are reconstructed contributions using observed outcomes and assumed unit economics, not audited profit or measured intervention savings.

Expected RTO loss = forward shipping + return shipping + packaging/handling + damage probability x product cost = **{money(loss_per_rto(a))} per RTO**. Damage is an expectation, not an observed loss label.

Delivered gross profit = delivered order value x {a['delivered_gross_margin']}. Primary interpretation: the stated gross margin already includes outbound shipping and handling on delivered orders. Alternative: subtract forward shipping plus packaging/handling for each delivered order. For RTOs both interpretations charge the complete stated RTO loss; no delivered revenue or delivered gross profit is recognized on those orders.

| Scope | Financial orders | Excluded values | Expected RTO loss | Contribution: delivery included | Contribution: delivery excluded |
| --- | ---: | ---: | ---: | ---: | ---: |
{financial_rows}

The two contribution columns bracket one accounting ambiguity; they do not include acquisition spend, payment fees, taxes, overhead or customer lifetime value. Acquisition cost is not subtracted again as an invented incremental cancellation cost. Primary is a disclosed interpretation, not a verified accounting fact.

**Separate brief-based monthly projection:** {monthly_cod} COD orders (all monthly orders x COD share), {monthly_rto} expected RTOs, expected RTO loss INR {money(projection_loss)}, contribution INR {money(projection_primary)} under primary accounting or INR {money(projection_alternative)} under alternative accounting. This projection uses the brief's AOV/rate and is not an extrapolation from the six-month sample. The sample contains COD only; never apply the 55% share to its rows. It does not represent all monthly business orders.

## Chronological evaluation and leakage controls

- Development: 2026-04-01 inclusive to 2026-08-01 exclusive. Validation: August. Evaluation: September. Full-day end dates use exclusive next-month boundaries.
- All retained records have membership rows, including unresolved/invalid records. Outcome eligibility and financial eligibility are independent of date assignment. Invalid/out-of-window dates are assigned excluded_date and never enter a chronological split.
- September aggregate outcomes were inspected before the plan was finalized. Disclose this; September is a reserved chronological evaluation set, not a completely unseen holdout. Do not choose rules or thresholds using its results. Current tables contain no policy tuning or policy backtest.
- No outcome-based customer, courier, city or pincode features are generated. Group summaries are analysis artifacts and must not be joined back as full-data prediction features.
- The file lacks delivery/outcome timestamps. Earlier order placement does not prove its outcome was known at a later decision. Outcome-derived historical features require verified availability timestamps or a documented frozen retrospective snapshot assumption; do not claim a fully point-in-time-valid live backtest from this file.
- Supplied customer_prior_orders/customer_prior_rto are assumed to be order-time snapshots, but that cannot be verified. Inconsistent rows are flagged unusable for history features; future modeling should test performance with and without these fields.
- final_status, outcome_resolved, quality_flags and membership/eligibility metadata are not prediction inputs. No model-ready feature matrix is exported in Phase 2.

## Reading the supporting tables and charts

segments.csv covers month, customer type, prior RTO, channel, courier, state, city, pincode, amount bands, item count and hour bands. Each scope/dimension partitions its eligible population. Rates are fractions, amounts are INR, and blank rates/averages mean unavailable. Amount bands are fixed descriptive bins (not tuned risk thresholds).

Every segment includes numerator, denominator and approximate 95% Wilson bounds. small_sample=true means fewer than 30 orders and is an analysis display convention, not a business rule. Intervals assume independent observations; repeated customers can make them optimistic. Multiple exploratory comparisons are not significance tests. Missing or invalid features are retained as explicit groups.

![Monthly rates](charts/month.svg)

![Development customer history](charts/customer_type.svg)

![Development courier rates](charts/courier.svg)

## Next phase

Use the development findings to propose an interpretable decision baseline, validate choices on August and freeze before evaluating September. Add LLM address interpretation and editable business controls in Phase 3. Confirmation effectiveness, prepaid uptake and discount savings require explicit scenarios or experiments; this file cannot establish their causal effects. The brief's prepaid RTO assumption is not measured by this all-COD dataset.
'''
    (directory/'analysis_report.md').write_text(text, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT/'data/processed/orders_clean.csv')
    parser.add_argument('--assumptions', type=Path, default=ROOT/'config/financial_assumptions.json')
    parser.add_argument('--output-root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = run_analysis(args.input, args.assumptions, args.output_root)
    except (ValueError, OSError, csv.Error) as error:
        parser.exit(1, f'Analysis failed: {error}\n')
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()

"""Fit on April-July, select on August, freeze, then evaluate September offline.

Counterfactual intervention impact is a scenario calculation, never a causal estimate.
"""

import argparse
import csv
import hashlib
import itertools
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from src.address_review import AddressReviewer, PROMPT_VERSION, MODEL
from src.check_address import evaluate_cases
from src.analysis import exclusion_reasons, load_assumptions, money, split_for, valid_value
from src.data_pipeline import ROOT, COLUMNS, EXTRA_COLUMNS, write_csv
from src.decision_engine import ACTIONS, decide, economics, load_policy, normalize_order
from src.risk import calibration, fit_model, metrics, predict

KINDS = ('constant','history_rules','logistic','logistic_without_history')


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def select_model(models, validation):
    return min(models, key=lambda model:(metrics(model,validation)['brier'], KINDS.index(model['kind'])))


def select_policy(model, validation, base_policy, assumptions):
    candidates = []
    for confirm, prepaid in itertools.product((.20,.30,.40),(.40,.50,.60)):
        if prepaid < confirm:
            continue
        policy = dict(base_policy, confirm_risk_threshold=confirm, prepaid_risk_threshold=prepaid)
        performance, _ = simulate(model,validation,policy,assumptions)
        candidates.append(dict(confirm_risk_threshold=confirm,prepaid_risk_threshold=prepaid,
                               scenario_net_impact_inr=performance['net_impact_inr'],
                               scenario_contribution_inr=performance['policy_contribution_inr']))
    # Deterministic tie-break prefers higher thresholds (fewer interventions).
    winner = max(candidates,key=lambda x:(Decimal(x['scenario_contribution_inr']),x['confirm_risk_threshold'],x['prepaid_risk_threshold']))
    selected = dict(base_policy,confirm_risk_threshold=winner['confirm_risk_threshold'],prepaid_risk_threshold=winner['prepaid_risk_threshold'])
    return selected,candidates


def simulate(model, rows, policy, assumptions):
    """Conservative holds: no shipment inside the accounting horizon.

    Known historical labels support realised ship-all economics only. Response
    branches remain conditional assumptions even when their output is positive.
    """
    reviewer = AddressReviewer('offline')
    totals = {k:Decimal(0) for k in ('baseline','policy','avoided_rto','genuine_hold_loss','discounts','message_costs','payment_fees')}
    counts = Counter()
    logs = []
    included, excluded = 0,0
    for raw in rows:
        order=normalize_order(raw)
        result=decide(order,model,policy,assumptions,reviewer)
        action=result['action']
        counts[action]+=1
        y=int(raw['final_status']=='RTO')
        if valid_value(raw) is None:
            excluded+=1
            baseline_value=policy_value=None
            avoided=genuine_loss=discount_cost=msg_cost=payment_fee=Decimal(0)
        else:
            included+=1
            p=predict(model,order)
            e=economics(order,p,policy,assumptions)
            key='rto' if y else 'genuine'
            baseline_value=e['conditional']['ship_as_is'][key]
            policy_value=e['conditional'][action][key]
            totals['baseline']+=baseline_value
            totals['policy']+=policy_value
            q=Decimal(str(policy['rto_confirmation_rate' if y else 'genuine_confirmation_rate']))
            uptake=Decimal(str(policy['rto_prepaid_uptake' if y else 'genuine_prepaid_uptake']))
            prepaid_rto=assumptions['brief_prepaid_rto_rate']
            if action=='hold_cancel':
                avoided=e['unit_loss'] if y else Decimal(0)
                genuine_loss=max(Decimal(0),e['margin']) if not y else Decimal(0)
                discount_cost=msg_cost=payment_fee=Decimal(0)
            elif action=='ship_after_confirmation':
                avoided=(1-q)*e['unit_loss'] if y else Decimal(0)
                genuine_loss=Decimal(0)
                discount_cost=payment_fee=Decimal(0)
                msg_cost=Decimal(str(policy['confirmation_message_cost_inr']))
            elif action=='nudge_to_prepaid':
                # Gross avoided original-RTO logistics; prepaid residual losses
                # and new delivery margins are already inside policy_value.
                avoided=(1-((1-uptake)*q+uptake*prepaid_rto))*e['unit_loss'] if y else Decimal(0)
                genuine_loss=Decimal(0)
                discount_cost=uptake*(1-prepaid_rto)*e['discount']
                payment_fee=uptake*(1-prepaid_rto)*(Decimal(order['order_value'])-e['discount'])*Decimal(str(policy['prepaid_payment_fee_fraction']))
                msg_cost=Decimal(str(policy['prepaid_message_cost_inr']))+(1-uptake)*Decimal(str(policy['confirmation_message_cost_inr']))
            else:
                avoided=genuine_loss=discount_cost=msg_cost=payment_fee=Decimal(0)
            totals['avoided_rto']+=avoided
            totals['genuine_hold_loss']+=genuine_loss
            totals['discounts']+=discount_cost
            totals['message_costs']+=msg_cost
            totals['payment_fees']+=payment_fee
        logs.append(dict(source_row=raw['source_row'],order_id=order['order_id'],action=action,disposition=result['disposition'],
                         risk_probability=result['risk_probability'] if result['risk_probability'] is not None else '',
                         historical_outcome=raw['final_status'],address_source=result['address_review']['source'],
                         reason=result['reason'],financially_eligible=str(baseline_value is not None).lower(),
                         baseline_contribution_inr=money(baseline_value) if baseline_value is not None else '',
                         scenario_contribution_inr=money(policy_value) if policy_value is not None else '',
                         scenario_net_impact_inr=money(policy_value-baseline_value) if policy_value is not None else '',
                         prepaid_discount_inr=result['prepaid_discount_inr']))
    result=dict(orders=len(rows),financial_orders=included,excluded_invalid_values=excluded,
                buckets={action:counts[action] for action in ACTIONS},
                baseline_contribution_inr=money(totals['baseline']),policy_contribution_inr=money(totals['policy']),
                net_impact_inr=money(totals['policy']-totals['baseline']),
                gross_avoided_rto_loss_inr=money(totals['avoided_rto']),
                genuine_held_order_margin_at_risk_inr=money(totals['genuine_hold_loss']),
                expected_discount_cost_inr=money(totals['discounts']),
                expected_message_cost_inr=money(totals['message_costs']),
                expected_payment_fee_inr=money(totals['payment_fees']))
    return result,logs


def run_training(input_path=ROOT/'data/processed/orders_clean.csv', output_root=ROOT,
                 policy_path=ROOT/'config/decision_policy.json', assumptions_path=ROOT/'config/financial_assumptions.json'):
    input_path,output_root=Path(input_path),Path(output_root)
    base_policy,assumptions=load_policy(policy_path),load_assumptions(assumptions_path)
    with input_path.open(encoding='utf-8',newline='') as handle:
        reader=csv.DictReader(handle)
        if reader.fieldnames!=list(COLUMNS+EXTRA_COLUMNS):
            raise ValueError('Expected Phase 1 cleaned input schema.')
        all_rows=list(reader)
    if not all_rows or any(None in r or any(v is None for v in r.values()) for r in all_rows):
        raise ValueError('Empty or malformed training file.')
    if len({r['source_row'] for r in all_rows})!=len(all_rows):
        raise ValueError('Duplicate source record IDs.')
    ids=Counter(r['order_id'] for r in all_rows)
    rows=[r for r in all_rows if not exclusion_reasons(r) and ids[r['order_id']]==1]
    splits={s:[r for r in rows if split_for(r['order_datetime'])==s] for s in ('development','validation','evaluation')}
    if any(not subset for subset in splits.values()):
        raise ValueError('All three chronological cohorts must contain resolved orders.')
    # Models and policy selection functions never receive September rows.
    models=[fit_model(splits['development'],kind) for kind in KINDS]
    selected=select_model(models,splits['validation'])
    policy,threshold_search=select_policy(selected,splits['validation'],base_policy,assumptions)
    report_dir,artifact_dir=output_root/'reports/engine',output_root/'artifacts'
    report_dir.mkdir(parents=True,exist_ok=True)
    artifact_dir.mkdir(parents=True,exist_ok=True)
    freeze=dict(schema_version=1,model=selected,policy=policy,
                financial_assumptions={k:str(v) for k,v in assumptions.items()},
                selection_metric='August Brier score; deterministic offline scenario contribution for threshold search',
                evaluation_address_mode='offline',address_prompt_version=PROMPT_VERSION,live_llm_model=MODEL,
                development_sha256=canonical_hash(splits['development']),validation_sha256=canonical_hash(splits['validation']),
                training_period='2026-04-01 <= order_datetime < 2026-08-01',
                selection_period='2026-08-01 <= order_datetime < 2026-09-01',
                limitations=['Outcome availability timestamps missing; retrospective snapshot assumption.',
                             'September aggregates previously inspected; not completely unseen.',
                             'Offline address analysis is a heuristic, not tested live LLM output.',
                             'Intervention effects, prepaid risk and fees are unverified assumptions.'])
    freeze['freeze_sha256']=canonical_hash(freeze)
    # Persist frozen selection before accessing evaluation labels in metrics/simulation.
    (artifact_dir/'decision_engine.json').write_text(json.dumps(freeze,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    (report_dir/'validation_threshold_search.json').write_text(json.dumps(threshold_search,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    comparison=[]
    calibration_rows=[]
    for model in models:
        for scope,subset in splits.items():
            comparison.append(dict(model=model['kind'],scope=scope,selected=str(model['kind']==selected['kind']).lower(),**metrics(model,subset)))
            calibration_rows.extend(dict(model=model['kind'],scope=scope,**row) for row in calibration(model,subset))
    write_csv(report_dir/'model_comparison.csv',tuple(comparison[0]),comparison)
    write_csv(report_dir/'calibration.csv',tuple(calibration_rows[0]),calibration_rows)
    performance={}
    for scope in ('validation','evaluation'):
        performance[scope],logs=simulate(selected,splits[scope],policy,assumptions)
        write_csv(report_dir/f'{scope}_decisions.csv',tuple(logs[0]),logs)
    scenario_results=[]
    for name,changes in (
        ('base',{}),
        ('weaker_responses',dict(genuine_confirmation_rate=.75,rto_confirmation_rate=.60,genuine_prepaid_uptake=.15,rto_prepaid_uptake=.05)),
        ('no_prepaid_uptake',dict(genuine_prepaid_uptake=0,rto_prepaid_uptake=0)),
        ('delivery_cost_excluded_from_margin',dict(delivered_margin_includes_fulfilment=False)),
        ('no_response_discrimination',dict(genuine_confirmation_rate=.90,rto_confirmation_rate=.90,genuine_prepaid_uptake=0,rto_prepaid_uptake=0)),
    ):
        changed=dict(policy,**changes)
        for scope in ('validation','evaluation'):
            # Freeze base decisions; vary outcomes only, never reroute to flatter a scenario.
            value=score_fixed_decisions(selected,splits[scope],changed,assumptions,policy)
            scenario_results.append(dict(scenario=name,scope=scope,**value))
    write_csv(report_dir/'scenario_sensitivity.csv',tuple(scenario_results[0]),scenario_results)
    summary=dict(freeze_sha256=freeze['freeze_sha256'],input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
                 selected_model=selected['kind'],split_orders={s:len(r) for s,r in splits.items()},
                 retained_input_orders=len(all_rows),excluded_unresolved_or_ambiguous_or_outside_dates=len(all_rows)-sum(map(len,splits.values())),
                 policy=policy,performance=performance,live_llm_verified=False)
    (report_dir/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    examples=json.loads((ROOT/'examples/orders.json').read_text(encoding='utf-8'))
    decisions=[decide(order,selected,policy,assumptions,AddressReviewer('offline')) for order in examples]
    (report_dir/'example_decisions.json').write_text(json.dumps(decisions,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    cases=json.loads((ROOT/'examples/address_cases.json').read_text(encoding='utf-8'))
    fixture_result=evaluate_cases(AddressReviewer('offline'),cases)
    (report_dir/'offline_address_check.json').write_text(json.dumps(fixture_result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    write_report(report_dir,summary,comparison,scenario_results)
    return summary


def score_fixed_decisions(model,rows,policy,assumptions,base_policy):
    total=baseline_total=Decimal(0)
    for raw in rows:
        if valid_value(raw) is None:
            continue
        order=normalize_order(raw)
        decision=decide(order,model,base_policy,assumptions,AddressReviewer('offline'))
        e=economics(order,predict(model,order),policy,assumptions)
        key='rto' if raw['final_status']=='RTO' else 'genuine'
        total+=e['conditional'][decision['action']][key]
        baseline_total+=e['conditional']['ship_as_is'][key]
    return dict(policy_contribution_inr=money(total),baseline_contribution_inr=money(baseline_total),net_impact_inr=money(total-baseline_total))


def write_report(directory,summary,comparison,scenarios):
    selected=summary['selected_model']
    p=summary['policy']
    metric_table='\n'.join(f"| {r['model']} | {r['scope']} | {r['brier']:.4f} | {r['log_loss']:.4f} | {r['auc'] if r['auc'] is not None else 'n.a.'} |" for r in comparison)
    scenario_table='\n'.join(f"| {r['scenario']} | {r['scope']} | {r['net_impact_inr']} |" for r in scenarios)
    details=[]
    for scope,result in summary['performance'].items():
        details.append(f"### {scope.title()}\n\n"+'\n'.join(f'- {k}: {v}' for k,v in result.items()))
    text=f'''# Phase 3 - decision engine and frozen evaluation

## Result and provenance

Selected risk estimator: **{selected}**. Selection used August Brier score only; smaller is better. Source: cleaned assignment orders. Configurations: config/decision_policy.json and config/financial_assumptions.json. Artifact hash: `{summary['freeze_sha256']}`. Raw input hash: `{summary['input_sha256']}`.

**Business result:** August base-scenario net impact INR {summary['performance']['validation']['net_impact_inr']}; September INR {summary['performance']['evaluation']['net_impact_inr']}. The frozen policy does not establish a profitable intervention. Keep this as a shadow/review demo and validate customer response assumptions before operational rollout; do not retune on September to hide the negative result.

Counts: {summary['split_orders']}. Statistical estimators use all eligible resolved orders; invalid feature values have explicit missing/unknown encodings. Operational validation can still hold those same orders. Records with unresolved labels, ambiguous IDs or dates outside the fixed split windows are excluded; total excluded: {summary['excluded_unresolved_or_ambiguous_or_outside_dates']}.

## Estimator comparison

| Model | Period | Brier | Log loss | AUC |
| --- | --- | ---: | ---: | ---: |
{metric_table}

Constant is a smoothed development base rate. History rules use development-only smoothed customer-history groups. Logistic regressions use fixed batch gradient descent, L2 regularization and a fixed feature map; the no-history candidate checks dependence on unverified history snapshots. Candidate coefficients are interpretable associations, not causes. Risk scores are estimates, not independently calibrated guarantees. calibration.csv provides predicted-versus-observed bins. Small bins and repeated customers limit confidence. No calibrator was fit on September.

Feature allowlist: capped amount, item count, night-order indicator, deterministic missing-value indicators, state/courier/channel categories, and optional supplied prior-order/prior-RTO history. Phone, name, full address, pincode, final_status, quality_flags and source-row metadata are not model inputs. Unseen categories contribute zero; no customer or geography outcome aggregates are generated. Courier must be assigned before scoring or supplied as missing.

## Decision policy

- Confirmation eligible at risk >= {p['confirm_risk_threshold']}; prepaid eligible at >= {p['prepaid_risk_threshold']}; operations review at >= {p['hold_risk_threshold']}. These are candidate eligibility gates, not automatic assignments: code compares allowed actions' expected contributions.
- Invalid required fields/history receive a correction hold. Address/name uncertainty or unavailable text analysis requires confirmation. Those LLM findings do not modify the numeric risk score.
- For clean text, choose the highest scenario contribution among permitted actions. Insufficient expected contribution can also trigger review. Holds execute no cancellation and create no actual shipment, message or payment.
- The fourth bucket is hold_cancel with disposition hold_for_review. Automatic cancellation is disabled and cannot be enabled in this version. Customer refusal and payment handling belong to the later message-flow phase.
- No ship-after-confirmation order can ship merely because a score was calculated. The result includes required_before_shipping conditions. Incomplete addresses need correction, not just a bare yes. Prepaid requires verified successful payment; otherwise confirmation is the modeled fallback.

## Discount and money calculations

Offer up to INR {p['prepaid_discount_inr']}, limited to {p['maximum_discount_fraction']:.0%} of order value and max(0, estimated COD risk - brief prepaid risk) x expected RTO loss. Round down to paise. This is a conservative logistics-loss discount budget, not a guarantee of profitable conversion. Refuse prepaid where discounted delivered contribution is nonpositive.

For INR 649 at 28% COD risk versus 4% prepaid: logistics-loss budget = (0.28-0.04) x INR 169.40 = INR 40.656; 5% value cap = INR 32.45; an INR 25 discount fits both. Payment fees and response losses are separately included in the decision economics. Amounts and costs use Decimal; risk fitting uses floating point.

Delivered contribution = value x 62% under primary accounting; alternative subtracts INR 65 forward plus INR 25 handling. RTO contribution = -INR 169.40. Ship EV = (1-p) x delivered contribution - p x RTO loss.

Confirmation EV assumes genuine delivery survives with probability {p['genuine_confirmation_rate']} and historically failed orders still ship with probability {p['rto_confirmation_rate']}, then subtracts message cost INR {p['confirmation_message_cost_inr']}. Confirmation does not magically turn failed deliveries into successes.

Prepaid uptake assumes {p['genuine_prepaid_uptake']} for historically genuine orders and {p['rto_prepaid_uptake']} for historical RTOs. Paid branches use 4% residual RTO and deduct the discount plus a {p['prepaid_payment_fee_fraction']:.0%} fee from successful-delivery contribution. Non-converters use confirmation. Fees are assumed charged only on successful deliveries for simplicity; failed-prepaid refunds/fee retention are not modeled. Message costs are assumed, not a paid integration. Acquisition costs and future customer value are not fabricated or double-counted.

## Historical scenario simulation

The following uses historical COD labels plus **hypothetical intervention responses** and the **offline address heuristic**. It is not measured savings, causal uplift, a live LLM evaluation or the business memo. Holds are conservatively treated as no shipment within the reporting horizon; genuine held margins are at risk, not necessarily permanently lost. Invalid amounts are excluded from every money total but remain in bucket counts.

{chr(10).join(details)}

Net impact is policy contribution minus ship-all contribution. Gross avoided RTO losses alone are not net savings. Discounts, fees, messaging, missed genuine deliveries and assumed new prepaid deliveries are already reflected in policy contribution; do not subtract them twice. Per-order scenario figures round for display; full-precision totals may differ from summed displayed rows by paise.

## Sensitivity of fixed base decisions

| Scenario | Period | Net impact INR |
| --- | --- | ---: |
{scenario_table}

The base decision assignments remain fixed; only assumed response/accounting outcomes change. The no-response-discrimination scenario challenges the assumption that failed deliveries are less likely to confirm. The base policy was selected from nine threshold pairs on August scenario contribution, which can overfit assumptions. Scenario sensitivity is a warning about identification, not validation of response rates. No thresholds were selected from September results.

## LLM integration and free-only boundary

Only Groq-hosted `{MODEL}` is implemented, via a strict JSON schema. Live mode is opt-in, checks GROQ_API_KEY and GROQ_FREE_TIER_CONFIRMED, caps local attempts at 20/day, spaces requests by 10 seconds, caches validated responses and does not retry/switch providers. Free-tier limits and account access can change. The client cannot independently verify an account's billing plan: never use a paid-plan key. A local cap is not a billing guarantee.

No key was available during development. Live LLM quality and connectivity remain **unverified**. Mocked HTTP/schema/error/quota tests are not live accuracy evidence. Offline review is a visibly labeled deterministic heuristic. English/Hindi/Hinglish fixtures are hand-authored expectations, not proof of LLM performance. Run the live fixture check after setting a free-plan key before relying on live address findings.

Only recipient name, address, city/state and pincode are sent to Groq. Phones, order values/history, IDs and outcomes are omitted. Input text is untrusted and cannot override policy. No external geocoding, identity verification, paid tools or paid assets are used. Format and textual completeness cannot establish a real deliverable location. API failures/refusals/bad JSON return unknown and require confirmation; no raw error or API key is logged.

Provider references checked during implementation: [structured outputs](https://console.groq.com/docs/structured-outputs), [API reference](https://console.groq.com/docs/api-reference), [free-tier limits](https://console.groq.com/docs/rate-limits).

## Evaluation limits and next steps

The model/policy artifact is serialized before September evaluation and hashes development/validation only. Mutating September outcomes must not change it. Prior September aggregate inspection is disclosed; it is a reserved chronological evaluation set, not completely unseen. Delivery/outcome availability timestamps are absent: this is a retrospective snapshot backtest. Supplied history is assumed available when orders were placed; logistic_without_history is a sensitivity candidate.

Offline and live text routing may differ, so the offline backtest cannot be advertised as performance of the live LLM policy. The selected settings remain in the frozen artifact; editing config requires explicit regeneration or a CLI override marked as not matching the backtest. New data, thresholds, prompts or models require renewed validation.

Next: verify the live LLM on labeled fixtures, then build confirmation/prepaid state transitions and the founder dashboard. Confirmation effects and retention assumptions need a controlled pilot before shipping/cancelling real orders automatically.
'''
    (directory/'evaluation_report.md').write_text(text,encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=ROOT/'data/processed/orders_clean.csv')
    parser.add_argument('--output-root',type=Path,default=ROOT)
    parser.add_argument('--policy',type=Path,default=ROOT/'config/decision_policy.json')
    parser.add_argument('--assumptions',type=Path,default=ROOT/'config/financial_assumptions.json')
    args=parser.parse_args()
    try:
        summary=run_training(args.input,args.output_root,args.policy,args.assumptions)
    except (ValueError,OSError,KeyError,TypeError) as error:
        parser.exit(1,f'Engine training failed: {error}\n')
    print(json.dumps(summary,indent=2,sort_keys=True))


if __name__=='__main__':
    main()

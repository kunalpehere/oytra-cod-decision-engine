"""Four-bucket COD recommendations with explicit scenario economics and review holds."""

import argparse
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from src.address_review import AddressReviewer
from src.analysis import history_valid, load_assumptions, loss_per_rto, money, number
from src.data_pipeline import ROOT, COLUMNS, normalize_phone
from src.risk import predict, risk_signals

ACTIONS = ('ship_as_is','ship_after_confirmation','nudge_to_prepaid','hold_cancel')
PROBABILITIES = ('confirm_risk_threshold','prepaid_risk_threshold','hold_risk_threshold',
                 'maximum_discount_fraction','genuine_confirmation_rate','rto_confirmation_rate',
                 'genuine_prepaid_uptake','rto_prepaid_uptake','prepaid_payment_fee_fraction')
AMOUNTS = ('prepaid_discount_inr','confirmation_message_cost_inr','prepaid_message_cost_inr','minimum_expected_contribution')


def validate_policy(policy):
    if policy.get('schema_version')!=1 or policy.get('allow_auto_cancel') is not False:
        raise ValueError('Policy version 1 supports review holds, not automatic cancellation.')
    if type(policy.get('delivered_margin_includes_fulfilment')) is not bool:
        raise ValueError('Margin accounting option must be true or false.')
    for field in PROBABILITIES + AMOUNTS:
        value = number(policy.get(field))
        if type(policy.get(field)) not in (int,float) or value is None or value < 0:
            raise ValueError(f'{field} must be a finite nonnegative number.')
        if field in PROBABILITIES and value > 1:
            raise ValueError(f'{field} must be between zero and one.')
    if not policy['confirm_risk_threshold'] <= policy['prepaid_risk_threshold'] <= policy['hold_risk_threshold']:
        raise ValueError('Require confirmation <= prepaid <= hold risk thresholds.')
    return policy


def load_policy(path=ROOT/'config/decision_policy.json'):
    return validate_policy(json.loads(Path(path).read_text(encoding='utf-8')))


def normalize_order(order):
    if not isinstance(order,dict):
        raise ValueError('Order must be a JSON object.')
    result = {}
    for field in COLUMNS:
        value = order.get(field,'')
        if value is None:
            value = ''
        if not isinstance(value,(str,int,float,Decimal)) or isinstance(value,bool):
            raise ValueError(f'{field} must be a string or number.')
        result[field] = str(value).strip()
    result['payment_method'] = result['payment_method'].upper()
    result['phone'], _ = normalize_phone(result['phone'])
    return result


def input_issues(order):
    issues = []
    for field in ('order_id','order_datetime','customer_name','phone','address','city','state','pincode','payment_method'):
        if not order[field]:
            issues.append(f'missing {field.replace("_"," ")}')
    if order['payment_method'] != 'COD':
        issues.append('this engine accepts COD orders only')
    if not normalize_phone(order['phone'])[1]:
        issues.append('phone format needs correction')
    if not (len(order['pincode'])==6 and order['pincode'].isascii() and order['pincode'].isdigit() and order['pincode'][0]!='0'):
        issues.append('pincode format needs correction')
    try:
        dt = datetime.strptime(order['order_datetime'],'%Y-%m-%d %H:%M')
        if dt.strftime('%Y-%m-%d %H:%M')!=order['order_datetime']:
            raise ValueError('Invalid date format')
    except ValueError:
        issues.append('order date needs correction')
    value, items = number(order['order_value']), number(order['num_items'])
    if value is None or value<=0 or value>D('10000000'):
        issues.append('order value must be positive and at most INR 10000000')
    if items is None or items<=0 or items!=items.to_integral_value() or items>10000:
        issues.append('item count must be a positive integer no greater than 10000')
    if not history_valid(order):
        issues.append('customer history is missing or inconsistent')
    if order['items'] and items is not None:
        parts = order['items'].split('|')
        if len(parts)!=items or any(not item.strip() for item in parts):
            issues.append('item list does not match item count')
    return issues


D = Decimal


def economics(order, risk, policy, assumptions):
    """Conditional contributions let backtests integrate unknown intervention replies.

    A historically returned COD order is not assumed to become delivered merely
    after confirmation. Prepaid branches use the brief's unverified prepaid rate.
    """
    p, value = D(str(risk)), D(order['order_value'])
    unit_loss = loss_per_rto(assumptions)
    margin = value*assumptions['delivered_gross_margin']
    if not policy['delivered_margin_includes_fulfilment']:
        margin -= assumptions['forward_shipping']+assumptions['packaging_handling']
    c = {key:D(str(policy[key])) for key in PROBABILITIES+AMOUNTS}
    discounted = min(c['prepaid_discount_inr'],value*c['maximum_discount_fraction'],
                     max(D(0),(p-assumptions['brief_prepaid_rto_rate'])*unit_loss))
    discount = discounted.quantize(D('.01'))
    # Round downward so rounding can never exceed a discount cap.
    if discount>discounted:
        discount -= D('.01')
    paid_margin = margin-discount-(value-discount)*c['prepaid_payment_fee_fraction']
    paid_ev = (1-assumptions['brief_prepaid_rto_rate'])*paid_margin-assumptions['brief_prepaid_rto_rate']*unit_loss
    confirmed_good = c['genuine_confirmation_rate']*margin-c['confirmation_message_cost_inr']
    confirmed_bad = -c['rto_confirmation_rate']*unit_loss-c['confirmation_message_cost_inr']
    good_prepaid = c['genuine_prepaid_uptake']*paid_ev+(1-c['genuine_prepaid_uptake'])*confirmed_good-c['prepaid_message_cost_inr']
    bad_prepaid = c['rto_prepaid_uptake']*paid_ev+(1-c['rto_prepaid_uptake'])*confirmed_bad-c['prepaid_message_cost_inr']
    conditional = {
        'ship_as_is': {'genuine':margin, 'rto':-unit_loss},
        'ship_after_confirmation': {'genuine':confirmed_good, 'rto':confirmed_bad},
        'nudge_to_prepaid': {'genuine':good_prepaid, 'rto':bad_prepaid},
        'hold_cancel': {'genuine':D(0), 'rto':D(0)},
    }
    expected = {action:(1-p)*values['genuine']+p*values['rto'] for action,values in conditional.items()}
    return dict(discount=discount, expected=expected, conditional=conditional, margin=margin,
                prepaid_feasible=discount>0 and paid_margin>0, unit_loss=unit_loss)


def decide(order, model, policy, assumptions, reviewer=None):
    validate_policy(policy)
    order = normalize_order(order)
    problems = input_issues(order)
    if problems:
        return dict(order_id=order['order_id'], action='hold_cancel', disposition='hold_for_review',
                    reason='Hold for correction: ' + '; '.join(problems) + '. No cancellation has been executed.',
                    risk_probability=None, risk_signals=[], address_review={'source':'not_called'},
                    required_before_shipping=problems, prepaid_discount_inr='0.00',
                    expected_contribution_inr={}, selected_expected_contribution_inr=None,
                    scenario_assumptions=True, policy_schema_version=1)
    p = predict(model,order)
    if not 0<=p<=1:
        raise ValueError('Risk model returned an invalid probability.')
    review = (reviewer or AddressReviewer()).review(order)
    e = economics(order,p,policy,assumptions)
    needs_confirmation = review['address_quality']!='complete' or review['name_quality'] in ('placeholder','unknown')
    requirements = []
    if review['address_quality']!='complete':
        requirements.append('customer confirms or corrects delivery-location details')
    if review['name_quality'] in ('placeholder','unknown'):
        requirements.append('customer confirms recipient name')
    candidates = ['ship_as_is']
    if p>=policy['confirm_risk_threshold']:
        candidates.append('ship_after_confirmation')
    if p>=policy['prepaid_risk_threshold'] and e['prepaid_feasible']:
        candidates.append('nudge_to_prepaid')
    if needs_confirmation:
        # Address/name uncertainty is not calibrated into the numeric risk score.
        candidates = ['ship_after_confirmation']
    selected = max(candidates,key=lambda action:e['expected'][action])
    high_risk_hold = p>=policy['hold_risk_threshold']
    if high_risk_hold or (not needs_confirmation and e['expected'][selected]<D(str(policy['minimum_expected_contribution']))):
        selected = 'hold_cancel'
    disposition = 'hold_for_review' if selected=='hold_cancel' else 'recommendation'
    if selected=='hold_cancel':
        reason = ('Hold for operations review: estimated RTO risk exceeds the configured review threshold.' if high_risk_hold else
                  'Hold for operations review: available actions have insufficient estimated contribution under the configured assumptions.')
        requirements.append('operations reviews the financial assumptions and order before release')
    elif needs_confirmation:
        reason = 'Ask the customer to confirm ' + ('delivery details and recipient name' if len(requirements)>1 else 'delivery details' if review['address_quality']!='complete' else 'recipient name') + ' before shipping.'
        if review['source']=='unavailable':
            reason += ' Text analysis was unavailable; no cancellation was recommended.'
    elif selected=='ship_as_is':
        reason = 'Ship: the estimated contribution is highest among the actions allowed by the current risk thresholds.'
    elif selected=='ship_after_confirmation':
        reason = 'Confirm first: the configured response assumptions give a better estimated contribution than shipping immediately.'
    else:
        reason = f'Offer INR {money(e["discount"])} off prepaid; this has the best estimated contribution under the configured uptake assumptions.'
    if selected=='ship_after_confirmation':
        requirements.append('explicit customer confirmation; no shipment before confirmation')
    if selected=='nudge_to_prepaid':
        requirements.append('verified payment success; otherwise use confirmation flow')
    result = dict(order_id=order['order_id'], action=selected, disposition=disposition, reason=reason,
                  risk_probability=round(p,6), risk_signals=risk_signals(model,order), address_review=review,
                  required_before_shipping=requirements,
                  prepaid_discount_inr=money(e['discount']) if selected=='nudge_to_prepaid' else '0.00',
                  expected_contribution_inr={a:money(v) for a,v in e['expected'].items()},
                  selected_expected_contribution_inr=money(e['expected'][selected]),
                  scenario_assumptions=True, policy_schema_version=1)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--order',type=Path,required=True,help='One order object or a list of order objects in JSON.')
    parser.add_argument('--artifact',type=Path,default=ROOT/'artifacts/decision_engine.json')
    parser.add_argument('--policy',type=Path,help='Optional validated override; changes invalidate the published backtest.')
    parser.add_argument('--mode',choices=('offline','groq'),default='offline')
    args = parser.parse_args()
    try:
        artifact=json.loads(args.artifact.read_text(encoding='utf-8'))
        import hashlib
        content = {key:value for key,value in artifact.items() if key!='freeze_sha256'}
        if hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=artifact['freeze_sha256']:
            raise ValueError('Frozen artifact hash does not match its contents; regenerate Phase 3.')
        policy = load_policy(args.policy) if args.policy else validate_policy(artifact['policy'])
        assumptions = {key:D(value) for key,value in artifact['financial_assumptions'].items()}
        orders=json.loads(args.order.read_text(encoding='utf-8'))
        orders=orders if isinstance(orders,list) else [orders]
        reviewer=AddressReviewer(args.mode)
        results=[dict(decide(order,artifact['model'],policy,assumptions,reviewer),
                      frozen_artifact_sha256=artifact['freeze_sha256'], policy_overridden=bool(args.policy),
                      evaluation_mode_matches=(args.mode==artifact['evaluation_address_mode'])) for order in orders]
    except (ValueError,OSError,KeyError,TypeError) as error:
        parser.exit(1,f'Decision failed: {error}\n')
    print(json.dumps(results,indent=2,ensure_ascii=True))


if __name__=='__main__':
    main()

"""Small interpretable risk estimators, fitted on development records only.

Standard-library batch logistic regression uses a fixed feature map and fixed
regularization. No outcome-derived aggregates are joined into feature vectors.
"""

import math
from collections import defaultdict

from src.analysis import group_for, history_valid, number

CATEGORIES = ('state', 'courier', 'utm_source')
NUMERIC = ('value_scaled', 'items_scaled', 'night_order', 'invalid_value', 'invalid_items')
HISTORY = ('prior_orders_scaled', 'prior_rto_rate', 'history_unknown')


def features(order, include_history=True):
    value, items = number(order.get('order_value', '')), number(order.get('num_items', ''))
    value_valid = value is not None and value > 0
    item_valid = items is not None and items > 0 and items == items.to_integral_value()
    result = dict(value_scaled=min(float(value), 3000)/1000 if value_valid else 0.0,
                  items_scaled=min(float(items), 10)/4 if item_valid else 0.0,
                  invalid_value=float(not value_valid), invalid_items=float(not item_valid), night_order=0.0)
    timestamp = order.get('order_datetime', '')
    try:
        result['night_order'] = float(0 <= int(timestamp[11:13]) < 6)
    except ValueError:
        pass
    if include_history:
        valid = history_valid(order)
        prior = number(order['customer_prior_orders']) if valid else 0
        rto = number(order['customer_prior_rto']) if valid else 0
        result.update(prior_orders_scaled=float(min(prior, 10))/5, prior_rto_rate=float(rto/prior) if prior else 0.0,
                      history_unknown=float(not valid))
    for field in CATEGORIES:
        result[f'{field}={order.get(field, "") or "(missing)"}'] = 1.0
    return result


def sigmoid(value):
    return 1/(1+math.exp(-max(-35.0, min(35.0, value))))


def fit_model(rows, kind):
    if not rows or any(r.get('final_status') not in ('DELIVERED', 'RTO') for r in rows):
        raise ValueError('Training requires resolved development records.')
    targets = [int(r['final_status']=='RTO') for r in rows]
    prior = (sum(targets)+1)/(len(rows)+2)
    model = dict(kind=kind, development_orders=len(rows), prior=prior)
    if kind == 'constant':
        return model
    if kind == 'history_rules':
        buckets = defaultdict(list)
        for row, target in zip(rows, targets):
            key = group_for(row, 'prior_rto') + ':' + group_for(row, 'customer_type')
            buckets[key].append(target)
        model['groups'] = {k: (sum(v)+20*prior)/(len(v)+20) for k, v in sorted(buckets.items())}
        return model
    if kind not in ('logistic', 'logistic_without_history'):
        raise ValueError('Unknown model kind.')
    include_history = kind == 'logistic'
    maps = [features(row, include_history) for row in rows]
    names = sorted({name for mapping in maps for name in mapping})
    indices = {name: i for i, name in enumerate(names)}
    vectors = [[(indices[k], v) for k, v in mapping.items() if v] for mapping in maps]
    weights, intercept = [0.0]*len(names), math.log(prior/(1-prior))
    # Fixed optimization recipe; no September/validation-dependent fitting.
    for _ in range(350):
        gradients, intercept_gradient = [0.0]*len(names), 0.0
        for vector, target in zip(vectors, targets):
            error = sigmoid(intercept + sum(weights[i]*v for i, v in vector)) - target
            intercept_gradient += error
            for i, value in vector:
                gradients[i] += error*value
        intercept -= .2*intercept_gradient/len(rows)
        for i in range(len(weights)):
            weights[i] -= .2*(gradients[i]/len(rows) + .02*weights[i])
    model.update(intercept=intercept, coefficients=dict(zip(names, weights)),
                 include_history=include_history, l2_penalty=.02, iterations=350)
    return model


def predict(model, order):
    if model['kind']=='constant':
        return model['prior']
    if model['kind']=='history_rules':
        key = group_for(order, 'prior_rto') + ':' + group_for(order, 'customer_type')
        return model['groups'].get(key, model['prior'])
    values = features(order, model['include_history'])
    return sigmoid(model['intercept'] + sum(coef*values.get(name, 0) for name, coef in model['coefficients'].items()))


def risk_signals(model, order):
    if model['kind'].startswith('logistic'):
        values = features(order, model['include_history'])
        ranked = sorted(((name, coef*values.get(name,0)) for name, coef in model['coefficients'].items()), key=lambda x:-x[1])
        return [dict(feature=name, log_odds_contribution=round(value,6)) for name,value in ranked if value > 0][:3]
    return [dict(feature='development_base_rate' if model['kind']=='constant' else 'smoothed_customer_history_group',
                 probability=round(predict(model, order),6))]


def metrics(model, rows):
    if not rows:
        raise ValueError('Cannot evaluate an empty cohort.')
    pairs = [(predict(model,r), int(r['final_status']=='RTO')) for r in rows]
    n, positives = len(pairs), sum(y for _,y in pairs)
    brier = sum((p-y)**2 for p,y in pairs)/n
    log_loss = -sum(y*math.log(max(p,1e-12))+(1-y)*math.log(max(1-p,1e-12)) for p,y in pairs)/n
    buckets = defaultdict(list)
    for probability, target in pairs:
        buckets[probability].append(target)
    rank, positive_ranks = 1, 0.0
    for probability in sorted(buckets):
        labels = buckets[probability]
        positive_ranks += sum(labels)*(rank+(len(labels)-1)/2)
        rank += len(labels)
    auc = ((positive_ranks-positives*(positives+1)/2)/(positives*(n-positives))) if 0<positives<n else None
    return dict(orders=n, rto=positives, brier=round(brier,8), log_loss=round(log_loss,8),
                auc=round(auc,8) if auc is not None else None,
                mean_predicted_rto=round(sum(p for p,_ in pairs)/n,8), observed_rto_rate=round(positives/n,8))


def calibration(model, rows):
    buckets = defaultdict(list)
    for row in rows:
        p = predict(model,row)
        buckets[min(9,int(p*10))].append((p, int(row['final_status']=='RTO')))
    return [dict(bin=f'{b/10:.1f}-{(b+1)/10:.1f}', orders=len(pairs),
                 mean_predicted=round(sum(p for p,_ in pairs)/len(pairs),6),
                 observed_rate=round(sum(y for _,y in pairs)/len(pairs),6)) for b,pairs in sorted(buckets.items())]

# Phase 3 - decision engine and frozen evaluation

## Result and provenance

Selected risk estimator: **logistic**. Selection used August Brier score only; smaller is better. Source: cleaned assignment orders. Configurations: config/decision_policy.json and config/financial_assumptions.json. Artifact hash: `9be69e4c4aa340604eddf5bf9cf5e951514992aaf98ac9cdb8b7f504e15c120a`. Raw input hash: `71e73f9ddd71ad077b7e93a41a45c16a18e783638370de9458c603b61f6e0b7f`.

**Business result:** August base-scenario net impact INR 2495.37; September INR -889.30. The frozen policy does not establish a profitable intervention. Keep this as a shadow/review demo and validate customer response assumptions before operational rollout; do not retune on September to hide the negative result.

Counts: {'development': 1297, 'validation': 361, 'evaluation': 329}. Statistical estimators use all eligible resolved orders; invalid feature values have explicit missing/unknown encodings. Operational validation can still hold those same orders. Records with unresolved labels, ambiguous IDs or dates outside the fixed split windows are excluded; total excluded: 1.

## Estimator comparison

| Model | Period | Brier | Log loss | AUC |
| --- | --- | ---: | ---: | ---: |
| constant | development | 0.2065 | 0.6034 | 0.5 |
| constant | validation | 0.2016 | 0.5931 | 0.5 |
| constant | evaluation | 0.1940 | 0.5768 | 0.5 |
| history_rules | development | 0.1999 | 0.5865 | 0.58603929 |
| history_rules | validation | 0.1985 | 0.5847 | 0.56477532 |
| history_rules | evaluation | 0.1885 | 0.5611 | 0.58211312 |
| logistic | development | 0.1940 | 0.5738 | 0.67667294 |
| logistic | validation | 0.1974 | 0.5833 | 0.57736101 |
| logistic | evaluation | 0.1867 | 0.5583 | 0.63415159 |
| logistic_without_history | development | 0.1943 | 0.5745 | 0.67395835 |
| logistic_without_history | validation | 0.1978 | 0.5842 | 0.57616146 |
| logistic_without_history | evaluation | 0.1870 | 0.5590 | 0.63049096 |

Constant is a smoothed development base rate. History rules use development-only smoothed customer-history groups. Logistic regressions use fixed batch gradient descent, L2 regularization and a fixed feature map; the no-history candidate checks dependence on unverified history snapshots. Candidate coefficients are interpretable associations, not causes. Risk scores are estimates, not independently calibrated guarantees. calibration.csv provides predicted-versus-observed bins. Small bins and repeated customers limit confidence. No calibrator was fit on September.

Feature allowlist: capped amount, item count, night-order indicator, deterministic missing-value indicators, state/courier/channel categories, and optional supplied prior-order/prior-RTO history. Phone, name, full address, pincode, final_status, quality_flags and source-row metadata are not model inputs. Unseen categories contribute zero; no customer or geography outcome aggregates are generated. Courier must be assigned before scoring or supplied as missing.

## Decision policy

- Confirmation eligible at risk >= 0.4; prepaid eligible at >= 0.4; operations review at >= 0.9. These are candidate eligibility gates, not automatic assignments: code compares allowed actions' expected contributions.
- Invalid required fields/history receive a correction hold. Address/name uncertainty or unavailable text analysis requires confirmation. Those LLM findings do not modify the numeric risk score.
- For clean text, choose the highest scenario contribution among permitted actions. Insufficient expected contribution can also trigger review. Holds execute no cancellation and create no actual shipment, message or payment.
- The fourth bucket is hold_cancel with disposition hold_for_review. Automatic cancellation is disabled and cannot be enabled in this version. Customer refusal and payment handling belong to the later message-flow phase.
- No ship-after-confirmation order can ship merely because a score was calculated. The result includes required_before_shipping conditions. Incomplete addresses need correction, not just a bare yes. Prepaid requires verified successful payment; otherwise confirmation is the modeled fallback.

## Discount and money calculations

Offer up to INR 25, limited to 5% of order value and max(0, estimated COD risk - brief prepaid risk) x expected RTO loss. Round down to paise. This is a conservative logistics-loss discount budget, not a guarantee of profitable conversion. Refuse prepaid where discounted delivered contribution is nonpositive.

For INR 649 at 28% COD risk versus 4% prepaid: logistics-loss budget = (0.28-0.04) x INR 169.40 = INR 40.656; 5% value cap = INR 32.45; an INR 25 discount fits both. Payment fees and response losses are separately included in the decision economics. Amounts and costs use Decimal; risk fitting uses floating point.

Delivered contribution = value x 62% under primary accounting; alternative subtracts INR 65 forward plus INR 25 handling. RTO contribution = -INR 169.40. Ship EV = (1-p) x delivered contribution - p x RTO loss.

Confirmation EV assumes genuine delivery survives with probability 0.9 and historically failed orders still ship with probability 0.3, then subtracts message cost INR 1. Confirmation does not magically turn failed deliveries into successes.

Prepaid uptake assumes 0.35 for historically genuine orders and 0.2 for historical RTOs. Paid branches use 4% residual RTO and deduct the discount plus a 2% fee from successful-delivery contribution. Non-converters use confirmation. Fees are assumed charged only on successful deliveries for simplicity; failed-prepaid refunds/fee retention are not modeled. Message costs are assumed, not a paid integration. Acquisition costs and future customer value are not fabricated or double-counted.

## Historical scenario simulation

The following uses historical COD labels plus **hypothetical intervention responses** and the **offline address heuristic**. It is not measured savings, causal uplift, a live LLM evaluation or the business memo. Holds are conservatively treated as no shipment within the reporting horizon; genuine held margins are at risk, not necessarily permanently lost. Invalid amounts are excluded from every money total but remain in bucket counts.

### Validation

- orders: 361
- financial_orders: 361
- excluded_invalid_values: 0
- buckets: {'ship_as_is': 228, 'ship_after_confirmation': 106, 'nudge_to_prepaid': 20, 'hold_cancel': 7}
- baseline_contribution_inr: 125829.12
- policy_contribution_inr: 128324.49
- net_impact_inr: 2495.37
- gross_avoided_rto_loss_inr: 7634.52
- genuine_held_order_margin_at_risk_inr: 2478.14
- expected_discount_cost_inr: 133.76
- expected_message_cost_inr: 140.35
- expected_payment_fee_inr: 143.79
### Evaluation

- orders: 329
- financial_orders: 329
- excluded_invalid_values: 0
- buckets: {'ship_as_is': 215, 'ship_after_confirmation': 81, 'nudge_to_prepaid': 28, 'hold_cancel': 5}
- baseline_contribution_inr: 115528.68
- policy_contribution_inr: 114639.38
- net_impact_inr: -889.30
- gross_avoided_rto_loss_inr: 4941.06
- genuine_held_order_margin_at_risk_inr: 2752.80
- expected_discount_cost_inr: 192.26
- expected_message_cost_inr: 128.55
- expected_payment_fee_inr: 159.39

Net impact is policy contribution minus ship-all contribution. Gross avoided RTO losses alone are not net savings. Discounts, fees, messaging, missed genuine deliveries and assumed new prepaid deliveries are already reflected in policy contribution; do not subtract them twice. Per-order scenario figures round for display; full-precision totals may differ from summed displayed rows by paise.

## Sensitivity of fixed base decisions

| Scenario | Period | Net impact INR |
| --- | --- | ---: |
| base | validation | 2495.37 |
| base | evaluation | -889.30 |
| weaker_responses | validation | -7382.23 |
| weaker_responses | evaluation | -9323.06 |
| no_prepaid_uptake | validation | 942.89 |
| no_prepaid_uptake | evaluation | -1926.77 |
| delivery_cost_excluded_from_margin | validation | 3201.06 |
| delivery_cost_excluded_from_margin | evaluation | -18.73 |
| no_response_discrimination | validation | -4952.23 |
| no_response_discrimination | evaluation | -6094.01 |

The base decision assignments remain fixed; only assumed response/accounting outcomes change. The no-response-discrimination scenario challenges the assumption that failed deliveries are less likely to confirm. The base policy was selected from nine threshold pairs on August scenario contribution, which can overfit assumptions. Scenario sensitivity is a warning about identification, not validation of response rates. No thresholds were selected from September results.

## LLM integration and free-only boundary

Only Groq-hosted `openai/gpt-oss-20b` is implemented, via a strict JSON schema. Live mode is opt-in, checks GROQ_API_KEY and GROQ_FREE_TIER_CONFIRMED, caps local attempts at 20/day, spaces requests by 10 seconds, caches validated responses and does not retry/switch providers. Free-tier limits and account access can change. The client cannot independently verify an account's billing plan: never use a paid-plan key. A local cap is not a billing guarantee.

No key was available during development. Live LLM quality and connectivity remain **unverified**. Mocked HTTP/schema/error/quota tests are not live accuracy evidence. Offline review is a visibly labeled deterministic heuristic. English/Hindi/Hinglish fixtures are hand-authored expectations, not proof of LLM performance. Run the live fixture check after setting a free-plan key before relying on live address findings.

Only recipient name, address, city/state and pincode are sent to Groq. Phones, order values/history, IDs and outcomes are omitted. Input text is untrusted and cannot override policy. No external geocoding, identity verification, paid tools or paid assets are used. Format and textual completeness cannot establish a real deliverable location. API failures/refusals/bad JSON return unknown and require confirmation; no raw error or API key is logged.

Provider references checked during implementation: [structured outputs](https://console.groq.com/docs/structured-outputs), [API reference](https://console.groq.com/docs/api-reference), [free-tier limits](https://console.groq.com/docs/rate-limits).

## Evaluation limits and next steps

The model/policy artifact is serialized before September evaluation and hashes development/validation only. Mutating September outcomes must not change it. Prior September aggregate inspection is disclosed; it is a reserved chronological evaluation set, not completely unseen. Delivery/outcome availability timestamps are absent: this is a retrospective snapshot backtest. Supplied history is assumed available when orders were placed; logistic_without_history is a sensitivity candidate.

Offline and live text routing may differ, so the offline backtest cannot be advertised as performance of the live LLM policy. The selected settings remain in the frozen artifact; editing config requires explicit regeneration or a CLI override marked as not matching the backtest. New data, thresholds, prompts or models require renewed validation.

Next: verify the live LLM on labeled fixtures, then build confirmation/prepaid state transitions and the founder dashboard. Confirmation effects and retention assumptions need a controlled pilot before shipping/cancelling real orders automatically.

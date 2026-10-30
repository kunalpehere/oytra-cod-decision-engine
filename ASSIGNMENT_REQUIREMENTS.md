# Assignment requirements and delivery map

This summarizes the supplied **Associate Software Engineer – Take-Home Assignment**, dated 29 October 2026. The original company PDF and customer CSV are not redistributed in this public repository. The brief describes a D2C haircare business; the implementation follows that supplied scenario, even though the employer is Oytra.

## What the company said about AI

The company explicitly allows and encourages AI development tools. It also requires useful runtime LLM work, a clear explanation of which work belongs in ordinary code, and an AI usage log with **2–3 real examples of weak or wrong AI output and how it was caught and fixed**.

This project uses Codex for development and optional Groq-hosted GPT-OSS 20B for structured English, Hindi and Hinglish address/name interpretation. Python handles financial calculations, validation, risk scoring, thresholds, timers and state changes. See [AI_USAGE_LOG.md](AI_USAGE_LOG.md) for actual mistakes and corrections. Informal language and unfamiliar names are not fraud evidence; an LLM cannot verify physical deliverability or independently cancel an order.

## Required features and where to review them

| Company requirement | Implementation / evidence |
| --- | --- |
| Analyze the supplied historical COD orders | `src/data_pipeline.py`, `src/analysis.py`, aggregate findings under `reports/analysis/` |
| Decide ship as-is, ship after confirmation, nudge to prepaid, or hold/cancel | `src/decision_engine.py`; runnable synthetic examples in `examples/orders.json` |
| Give each decision a short reason an operations person understands | Decision CLI output and order detail panel in the desktop app |
| Use an LLM where it adds value, rather than for simple maths | `src/address_review.py`; documented boundary in README and AI usage log |
| Allow threshold changes without changing source code | Desktop **Adjust assumptions** controls for temporary scenarios; validated persistent values in `config/decision_policy.json` |
| Build a working WhatsApp confirmation/prepaid mock | **Confirmations** page; `src/confirmation_flow.py`, localized templates in `src/flow_messages.py` |
| Specify message language and timing | English/Hindi/Hinglish; immediate message, default 12-hour reminder, 18-hour offer expiry, fixed 24-hour response deadline |
| Handle yes, no, random replies and no reply within 24 hours | Tested state transitions, clarification guidance, explicit refusal cancellation and timeout review hold |
| Explain the prepaid discount mathematically | Up to INR 25, capped by 5% of order value and estimated RTO-loss reduction; README and founder memo |
| Show yesterday's four buckets, avoided RTO cost, genuine-order contribution at risk and net impact | **Daily overview** and **Contribution & scenarios**; `src/dashboard_data.py` |
| Write a 1–2 page founder memo, the most important deliverable | [Two-page business memo](output/pdf/business_memo.pdf) |
| Include at least three numerical findings, recommended rules and last-month replay | Memo, aggregate reports and frozen September evaluation |
| Resolve Operations vs. Marketing concerns in rupees | Memo retains genuine-buyer attrition costs and the negative September base result |
| Explain risks, monitoring and next two weeks | Memo's risk and follow-up sections |

The brief permits a simulator instead of a real WhatsApp account. This application sends no real messages, takes no payments and creates no shipments. Its hold/cancel bucket uses a review hold; cancellation in the simulator requires explicit customer refusal.

## Business assumptions supplied in the brief

- About 55% of orders are COD; about 28% of COD orders become RTO, versus about 4% for prepaid.
- Each RTO costs INR 65 forward shipping + INR 65 return shipping + INR 25 handling + 8% × INR 180 damage cost = **INR 169.40**.
- Roughly 3,000 monthly orders, INR 649 average basket, and 62% delivered gross margin.
- Marketing cites INR 300+ acquisition spend per new customer; this is already spent and is not deducted twice or treated as invented future customer value.

Historical analysis uses actual supplied order values. Intervention response rates are assumptions, not measured causal effects. The published September scenario remains **INR -889.30 net impact** versus shipping all; the memo recommends a supervised pilot.

## Required submission files

1. Public GitHub repository (or evaluator access) with a README that enables running within ten minutes: [README.md](README.md), [VERIFICATION.md](VERIFICATION.md).
2. Founder memo in PDF or Google Docs: [business_memo.pdf](output/pdf/business_memo.pdf).
3. Running list of important decisions, alternatives and reasons: [DECISION_LOG.md](DECISION_LOG.md).
4. AI tools, uses and actual mistakes/corrections: [AI_USAGE_LOG.md](AI_USAGE_LOG.md).

The brief emphasizes reasoning and the decision log over polish. Source code, synthetic examples and aggregate reports are public; credentials, environment files, customer records, per-order audits and local databases remain excluded. The evaluator provides the assignment CSV to the documented setup command.

## Live LLM check

On 30 October 2026, the user ran `python -m src.check_address --mode groq --case-id hinglish_complete` privately. The revised fixture returned `available=1`, `address_matches=1`, `name_matches=1`, `language=Hinglish`, and `cached=false` from `openai/gpt-oss-20b`. This demonstrates one fresh live response; it is not representative accuracy or physical delivery verification. No API key or credential file is included.

# Oytra COD decision engine

A local desktop system for reviewing Cash on Delivery orders before shipment: explainable RTO risk estimates, four action buckets, simulated customer conversations and a daily financial dashboard. Built for the supplied D2C haircare take-home scenario.

All default behavior is local and free. No WhatsApp login, payment account, API key, hosted deployment or third-party Python package is needed to run the demo.

## Quick start - under 10 minutes

**Prerequisite:** Python 3.10+ with Tkinter (normally included in Python on Windows). Run from the repository root. On Windows, `py -3` can replace `python`.

1. Clone this repository or download and extract its ZIP.
2. Obtain the `orders_sample.csv` supplied with the assignment. Customer records are deliberately excluded from the public repository.
3. Prepare and open the project:

```powershell
python -m src.setup_project --input "C:\path\to\orders_sample.csv"
python -m src.app
```

Setup validates/copies the input without altering the supplied file, cleans data, generates analysis, fits/selects/freezes the policy and creates offline example conversations. It makes zero API calls and refuses to replace a different raw dataset already present. If input is already at `data/raw/orders_sample.csv`, run `python -m src.setup_project`.

The clean-copy run and timing are recorded in [VERIFICATION.md](VERIFICATION.md). No `pip install` step is required for the application or tests. Rebuilding the included PDF is optional authoring work using the free ReportLab package.

## Five-minute demonstration

1. **Daily overview:** selects yesterday in IST or explicitly falls back to the latest populated date. Select `2026-09-30` for 9 orders. Click a bucket to filter, search an order ID, and select a row for its explanation.
2. **Contribution & scenarios:** inspect avoided RTO costs, missed genuine contribution, discounts, fees and net impact. The September reference remains negative; a positive day is not a positive month.
3. **Adjust assumptions:** applies a temporary what-if without retraining or overwriting the frozen policy. **Use baseline** restores published settings.
4. **Confirmations:** start **Address needs clarification**, choose English/Hindi/Hinglish and act as the customer:

```text
mera address ye hai "Satpur Nashik" aur name "Kunal"
```

Both values are saved, but locality/city alone is incomplete. Supply fuller details and confirm separately:

```text
mera address "House 21, Gali 4, Satpur, Nashik" aur name "Kunal"
YES
```

5. Start **Prepaid offer**. `PAID` text is not payment proof. Use **Simulate payment** for success/failure/expiry, or **Keep COD** then **Confirm order**. **Advance time** demonstrates reminders and the 24-hour hold without waiting.

**Update details** offers a form. Quoted corrections support address/pata/पता and name/naam/नाम, including smart quotes. Single-field `ADDRESS:` / `NAME:` commands still work. Ambiguity gets guidance, never guessed or partial updates. Corrections require fresh confirmation.

For isolated conversation state: `python -m src.app --db tmp/my-demo.sqlite`. The original `src.dashboard` and `src.chat_simulator` GUI commands also open the shared interface.

## Findings and financial result

After removing 30 exact duplicates, 1,988 orders remain: 1,987 resolved and one in transit. Overall RTO is 565/1,987 (28.43%). Development data shows higher RTO among first-time buyers and customers with prior RTO; all 845 development pincodes have fewer than 30 orders.

The frozen September replay assigns 215 orders to ship, 81 to confirmation, 28 to prepaid and 5 to review hold. Base-scenario contribution is INR 114,639.38 versus INR 115,528.68 for ship-all: **INR -889.30 net impact**. These are hypothetical intervention effects, not measured savings. The policy needs a supervised pilot rather than automatic rollout.

Read the [two-page founder memo](output/pdf/business_memo.pdf) for the recommendation, discount maths, Operations/Marketing trade-off, risks and next two weeks. Supporting aggregate reports are under `reports/analysis/` and `reports/engine/`; private per-order files regenerate locally.

## Decision approach

- Fit constant, smoothed history-rule, logistic and no-history logistic candidates on April-July 2026. Select by August Brier score; choose from nine August threshold pairs using hypothetical response economics. Freeze before September evaluation.
- Python handles validation, arithmetic, risk, thresholds and decisions. Model features exclude names, phones, full addresses, pincodes, final outcomes and audit metadata. Optional LLM findings do not add invented risk points.
- Compare **Ship as-is**, **Ship after confirmation**, **Nudge to prepaid** and **Hold / cancel**. The engine's fourth bucket is a review hold. The simulator cancels only on explicit customer refusal.
- Offer up to INR 25 prepaid, capped by 5% of value and estimated RTO-logistics reduction. The brief gives INR 169.40 expected loss per RTO. Discounts, assumed fees/messaging, genuine attrition and residual prepaid RTO are included.
- **Adjust assumptions** is a validated session scenario. Editing `config/decision_policy.json` and explicitly regenerating creates a new evaluated artifact. CLI policy overrides are labeled as invalidating the published backtest.

## Conversation and dashboard safeguards

Initial message immediately; default reminder at 12 hours, prepaid expiry at 18 hours, fixed response deadline at 24 hours. Replies do not reset deadlines. Timers run before events at the same boundary. YES cannot bypass incomplete details; PAID cannot verify payment. Failed/expired prepaid falls back to full-price COD confirmation. Duplicate event IDs cannot repeat effects; late/mismatched payments require review. All operations are simulated.

SQLite stores the paused demo clock and audit trail in ignored `data/simulator/`. Overview opens read-only; simulator state initializes when Confirmations opens. Current cancellation/hold/payment states are separate from initial recommendation counts.

Simulator activity has no delivery outcomes: financial impact is **unavailable**, not zero. Historical timestamps have no timezone; day grouping assumes IST without rewriting source dates. Invalid amounts/unresolved outcomes stay in bucket counts but not financial totals. Holds put genuine contribution at risk within the reporting horizon rather than proving permanent lost sales.

## Commands and tests

```powershell
python -m unittest discover -s tests -v
python -m src.decision_engine --order examples/orders.json
python -m src.flow_demo
python -m src.dashboard --export --date 2026-09-30
python tools/audit_repository.py
```

Dataset-dependent tests require the supplied CSV and setup first. GUI tests use withdrawn Tk windows and skip if Tk/a display is unavailable. Individual preparation modules remain available: `src.data_pipeline`, `src.analysis`, `src.train_engine`. `src.flow_demo` writes eight reproducible synthetic transcripts.

Daily exports under ignored `reports/dashboard/exports/` include initial decisions, per-order exclusions and source/settings hashes, without customer names/phones/addresses in flat files. Formula-like CSV text is escaped. Displayed rounded rows/days may differ by paise from a full-precision aggregate.

## Optional LLM - free tier only

Only Groq-hosted `openai/gpt-oss-20b` is implemented. A user-run live Hinglish check successfully reached Groq and classified the address as complete. It classified the original synthetic name Demo Customer as a placeholder, exposing an inconsistent fixture expectation. Non-placeholder fixtures now use a plausible fictional name. The user's revised live check returned available=1, address_matches=1, name_matches=1 and cached=false, with language Hinglish. **Representative interpretation accuracy remains unmeasured**. Provider mocks are not live quality evidence. The labeled offline heuristic matches 7/8 small address expectations and 8/8 name expectations, missing a plausible numberless named house. Eight cases are not representative accuracy evidence.

For live evaluation, use only a Groq **Free Plan** account, verify its tier yourself, and securely set process environment variables `GROQ_API_KEY` and `GROQ_FREE_TIER_CONFIRMED=true`. No credential file or key is shipped/automatically loaded. The client cannot attest billing status; never use a paid-plan key.

```powershell
python -m src.check_address --mode groq --case-id hinglish_complete
```

Check one case at a time. The adapter caches validated replies, caps attempts at 20 per UTC day and spaces attempts by 10 seconds. It never retries, switches providers or upgrades. Missing keys, quota/network errors or bad output require confirmation. Deleting the ignored cache resets the local counter; it does not replace provider/account limits.

Only recipient name and address/city/state/pincode are sent for interpretation, not order IDs, phones, outcomes, amounts or history. The LLM cannot execute actions or establish physical deliverability.

Provider references: [structured outputs](https://console.groq.com/docs/structured-outputs), [API reference](https://console.groq.com/docs/api-reference), [rate limits](https://console.groq.com/docs/rate-limits).

## Limitations

- September aggregates were inspected before the plan was finalized. It is a reserved chronological set, not a completely unseen holdout; it was not used to retune the published policy.
- Outcome-availability timestamps are absent; supplied histories are unverified order-time snapshots. No label-derived historical aggregates are generated. The replay is retrospective.
- Confirmation/prepaid responses, residual prepaid risk, contact costs and fees are assumptions. No causal uplift, customer lifetime value or real WhatsApp/payment/shipping integration is claimed.
- Primary accounting assumes delivered gross margin includes outbound shipping/handling; an alternative is reported and does not establish profitability.
- The overview was visually checked after UI refinement. Conversation behavior has automated coverage and user screenshot validation; its latest automated desktop visual recheck was stopped by the user.

## Submission and privacy

Repository: [kunalpehere/oytra-cod-decision-engine](https://github.com/kunalpehere/oytra-cod-decision-engine).

Credentials, environment files (including the blank template), key containers, raw/processed customer data, contact-value audit logs, databases/caches and private per-order exports are excluded. Source and synthetic examples are publishable. Evaluators supply the assignment CSV separately.

The repository audit reports filenames/categories only, never matched values. It checks the current publishable file set for prohibited paths and common credential patterns, not arbitrary secrets or Git history.

The company's feature, submission and AI-use requirements are mapped to the deliverables in [ASSIGNMENT_REQUIREMENTS.md](ASSIGNMENT_REQUIREMENTS.md).

Submission files: [founder memo](output/pdf/business_memo.pdf), [decision log](DECISION_LOG.md), [AI usage log](AI_USAGE_LOG.md), [verification](VERIFICATION.md), and [checklist](SUBMISSION_CHECKLIST.md). Publication/submission is separate from local preparation.

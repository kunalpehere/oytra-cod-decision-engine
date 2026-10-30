# Decision log

## Phase 1 - 2026-10-30

- Use Python's standard library for preparation. Alternatives: pandas or a database import. The current file is small, CSV processing is sufficient, and zero dependencies keeps setup short.
- Preserve the supplied CSV byte-for-byte under data/raw and record SHA-256 in reports. Alternative: overwrite the original with cleaned values. Preservation makes every transformation auditable.
- Deduplicate only exact original-field matches and keep the first source record. Alternatives: deduplicate on order ID or fuzzy customer/address matching. Those approaches can destroy conflicting evidence or legitimate repeat orders. Conflicting IDs are retained with flags.
- Normalize outer whitespace, status/payment case and valid phone formatting. Preserve numeric/date spellings and semantic address text. Alternative: aggressively rewrite addresses and infer missing values. The source does not justify those corrections.
- Keep invalid or incomplete unique records with review flags. Alternative: drop every record with a defect. That would hide the kinds of orders the future operational engine must handle and could bias findings.
- Define resolved strictly by DELIVERED/RTO labels. Retain IN_TRANSIT/unknown outcomes in clean data and log their exclusion from resolved data. Alternative: treat unknown outcomes as delivered or RTO, which invents labels.
- Treat the resolved file as outcome-resolved, not model-ready. Feature-quality review and chronological modeling rules belong in Phase 2. Flags can depend on outcomes and must not become model inputs.
- Validate amounts with Decimal and counts as finite integers. Alternatives: floating-point checks or coercing invalid values to zero. Decimal avoids precision surprises and invalid input stays visible.
- Reject structural schema errors before generating outputs. Accept reordered headers but reject extra/missing/duplicate columns and malformed record widths, avoiding silent input drift.
- Produce deterministic reports without execution timestamps. Source hashes and source record numbers provide provenance; byte-identical reruns are easy to verify.
- Do not call an LLM for preparation. Parsing, validation, counts and arithmetic have deterministic rules. LLM interpretation of names/addresses is a later phase.
- Preserve source timestamps without assigning a timezone: the assignment file does not identify one.

## Phase 2 - 2026-10-30

- Analyze all resolved COD records with unambiguous IDs; exclude unknown outcomes, non-COD records and conflicting/missing IDs. Retain ordinary feature defects and publish no-flags sensitivity cohorts. Alternative: remove all flagged orders, which conceals operationally relevant cases.
- Group inconsistent customer history as unknown rather than treating zero prior orders with positive prior RTO as a valid first-time customer. Membership records expose history usability.
- Exclude nonpositive/nonfinite amounts only from amount averages and matched financial cohorts. Count outcomes separately. This excludes three zero-value delivered orders from sample economics without pretending their outcome labels are missing.
- Use order-specific values for historical delivered gross profit. Keep the brief's INR 649 AOV only for its separate monthly projection. The development sample's AOV differs materially.
- Present two delivered-margin interpretations because the brief leaves shipping/handling inclusion ambiguous. Neither is presented as audited accounting. RTO loss includes forward/return shipping, handling and expected damage under both.
- Fix April-July development, August validation and September evaluation boundaries before policy construction. September aggregate inspection is disclosed; it is not a completely unseen holdout.
- Produce no outcome-derived historical features. Outcome availability cannot be established from order timestamps. A rolling aggregate of earlier placed orders could still leak not-yet-known delivery outcomes.
- Preserve supplied history as unverified order-time snapshots. Later modeling should compare results without these fields. Feature eligibility is separate from outcome eligibility.
- Show segment counts and Wilson intervals; fewer than 30 observations marks a small descriptive group, not a cancellation threshold. Repeat customers and multiple comparisons limit statistical interpretation.
- Generate dependency-free SVG business charts. Alternative: add a plotting dependency to the core pipeline. SVG keeps setup unchanged and supports browser viewing.
- No model, cancellation policy, confirmation conversion rate or prepaid causal effect is implemented or estimated in Phase 2.

## Phase 3 - 2026-10-30

- Honor the user's free-only constraint: use only standard-library Python and optional Groq Free Plan GPT-OSS 20B. No paid provider alternative, retry, model switching or automatic upgrade exists. Live mode is explicit; account tier must be checked by the user because the API client cannot attest billing status.
- Preserve a zero-network default with an explicitly labeled address heuristic. A Groq key was unavailable; implement a strict schema adapter and mock its HTTP, error, rate-limit and cache boundaries. Do not claim live accuracy or connectivity was verified.
- Fit four interpretable candidates on April-July: constant, smoothed customer-history rules, regularized logistic regression, and logistic regression without history. Fixed feature/optimization settings avoid searching a large model space on limited data. August Brier selects logistic; September is evaluated afterward.
- Select from nine confirmation/prepaid threshold pairs using August's hypothetical response economics. Keep high-risk hold at 0.90 and an expected-contribution floor at zero. Publish every candidate. Do not claim the response assumptions were learned from the CSV.
- Freeze the selected estimator, policy, financial assumptions and development/validation hashes before September evaluation. Integrity-check this artifact at scoring time. Threshold overrides are explicitly marked as invalidating the published backtest.
- Let numeric risk determine expected contributions, with LLM interpretation outside the risk model. No uncalibrated risk points are added for names or address text. Placeholder names and uncertain addresses trigger confirmation, not cancellation.
- Keep the fourth bucket as hold_for_review; no automatic cancellation or external operation is implemented. Missing required input receives correction holds. Genuine held contribution is conservatively counted at risk within the reporting horizon, not declared permanently lost.
- Set a proposed INR 25 prepaid discount, capped at 5% of value and estimated RTO-logistics reduction. Include hypothetical message costs, payment fees and failed confirmation retention. Non-converters fall back to confirmation; actual state transitions are deferred to Phase 4.
- Keep base decisions fixed for intervention/accounting sensitivity. Alternative scenarios change economics, not historical bucket assignments. Model output quality and intervention profitability are distinct questions.
- Retain the negative September scenario: INR -889.30 versus ship-all, despite August INR +2495.37. Do not retune against September to produce flattering numbers. Recommend a shadow/review pilot and measurement of response/retention before an operational rollout.
- Preserve a numberless-house fixture that the offline heuristic misses. The 7/8 address match is a known demonstration limit and a future live-LLM test, not a reason to rewrite the holdout evaluation.

## Phase 4 - 2026-10-30

- Use a local Tkinter desktop window, Python templates and SQLite; no hosted website, paid content, WhatsApp provider, LLM request or real payment integration is needed. A headless demo generator supports evaluators without Tkinter.
- Default to explicit English/Hindi/Hinglish language selection with English fallback. Do not infer language preference from state or name. Match only explicit small reply vocabularies; ambiguous text asks for clarification.
- Anchor all timers to the initial message: reminder at 12 hours, mock offer expiry at 18 hours, final hold at 24 hours. New conversations can change reminder/offer expiry settings, but cannot extend the assignment's 24-hour response window. Process timers in chronological order and before events arriving exactly on boundaries.
- Separate confirmation, detail correction and payment verification. A bare YES cannot repair missing delivery details. PAID text cannot verify payment. Name/address corrections need explicit fresh confirmation and never change model features like state or order value.
- Handle customer NO as explicit cancellation, while nonresponse and repeated unclear replies cause holds. A paid cancellation flags refund review. No automatic cancellation on silence is introduced.
- Model failed/expired/declined prepaid as COD confirmation at the original full price. Keep the original deadline and close the old offer. A later success cannot create a second COD/prepaid collection or silently reopen an order.
- Use transactionally idempotent event IDs with payload fingerprints. Exact replays are ignored and conflicting reuse rejected. Keep immutable audit entries for state changes, messages, detail corrections and mock payment results.
- Snapshot configuration and the Phase 3 recommendation inside each conversation. Persist the controllable clock, messages and payment state across restarts. No scheduled background or real-world action occurs.
- Treat customer-corrected addresses as asserted/format-checked, never physically verified. Broader geographic/contact changes require operations revalidation/rescoring outside this mock flow.
- Visual inspection caught a Tk packing issue hiding payment/clock controls at laptop heights. Reserve space for fixed controls before the expanding conversation area. The user stopped Computer Use before a visual recheck; remaining verification uses non-UI tests.

## Phase 5 - 2026-10-30

- Continue with a local standard-library Tkinter dashboard. No hosted site, paid assets, API call, provider key or external runtime dependency is introduced.
- Separate historical replay from simulator activity. Historical outcomes can support conditional scenario calculations; simulator payment/confirmation states cannot establish final delivery or realised profit.
- Count initial recommendations once per order creation date. Show current cancellation/hold/payment states separately so transitions cannot inflate bucket counts.
- Define yesterday in IST. Explicitly fall back to latest populated data at startup when yesterday is empty; the Yesterday button requests the exact date. Assume historical naive timestamps are IST for grouping without modifying source dates; convert simulator epoch timestamps to IST.
- Implement a complete contribution bridge using the same conditional economics as Phase 3. Show missed genuine delivery contribution, new prepaid delivery contribution, residual RTO loss, discounts, fees and messaging separately. This prevents the avoided-RTO card from implying net savings.
- Preserve unresolved orders in daily bucket counts, but exclude them and invalid amounts from historical financial totals. No eligible financial rows means unavailable, not a healthy zero.
- Treat non-shipped genuine orders in the fourth historical bucket as contribution at risk within the horizon. Actual simulator customer cancellations are separately counted and have no guessed genuine-order profit loss.
- Apply settings only to an explicit exploratory session scenario. Do not mutate configuration, retrain, rewrite the frozen artifact, or edit simulator recommendations. Response sensitivity fixes assignments rather than rerouting under each assumption set.
- Show the frozen September reference only if report, artifact and input hashes agree; retain its negative result. What-if views are not additional holdout validation.
- Export UTF-8 CSV bundles and provenance/settings context under date/scenario/data hashes. Exclude customer contact/address fields from flat exports and escape formula-like text without altering valid negative currency values.

## Frontend refinement - 2026-10-30

- Replace separate utilitarian windows with one native order desk: real navigation between overview and confirmations, shared spacing/typography, restrained semantic colors and system fonts. Keep existing CLI entry points and all backend rules intact.
- Use white reading surfaces, a dark green sidebar and clear currency/type hierarchy. Avoid decorative imagery, new dependencies, external assets or paid content.
- Make decision counts usable filters, add order-ID search and replace raw JSON in the primary detail panel with a concise operational summary. Keep financial limitations and the negative September reference visible.
- Present store/customer messages as distinct bubbles with timestamps, and turn audit payloads into readable activity descriptions. Put recipient/address correction in a form and add explicit reply buttons; internally they still use the tested event/state-machine methods.
- Keep simulator initialization lazy: overview navigation remains read-only. Preserve conversation state in SQLite and keep settings overrides session-scoped.
- The overview was visually reviewed after correcting font hierarchy. The user stopped Computer Use before the conversation visual recheck; automated checks cover navigation, filtering, details and shipping prerequisites.

## Quoted customer corrections - 2026-10-30

- Add deterministic extraction for labeled quoted fields in English, Hindi and Hinglish prose, including both name and address in one reply. Preserve legacy single-field commands. This explicitly delimited input needs no paid or free-tier API call.
- Reject unmatched quotes, empty values, duplicate labels and ambiguous field/value mappings rather than guessing. Validate every field before applying a multi-field update. Format-help replies do not consume the unclear-reply counter.
- Separate capturing text from address completeness. Store a short supplied address such as Satpur Nashik and acknowledge it, but retain the address requirement until fuller delivery details arrive. Quotation marks do not establish deliverability.
- Keep updates transactional/idempotent, require a separate fresh YES and preserve the existing deadline/payment/closed-order protections. Text inside quoted values is never interpreted as an action.

## Public repository preparation - 2026-10-30

- The user chose the public repository kunalpehere/oytra-cod-decision-engine and explicitly prohibited credential files/details. Exclude all environment files, including the blank example template, plus common key/credential containers and local account/state directories.
- Keep original/processed company customer data and contact-value audit logs local. Exclude per-order logs/exports while retaining source, synthetic examples and aggregate analysis. Evaluators supply the assignment CSV to regenerate private outputs after cloning.
- Add a pre-publication audit over Git's current publishable file set. Report only filenames and issue categories, never secret values. Common-pattern scanning is a guard, not a complete secret/history guarantee.

## Final submission preparation - 2026-10-30

- Produce a two-page founder memo leading with a supervised pilot recommendation and the negative September result. Include four development findings, rupee-based trade-offs, capped INR 25 incentive, risks/monitoring and a two-week follow-up plan.
- Add one-command offline setup from an evaluator-supplied CSV. Keep customer data out of the public package while allowing a fresh checkout to regenerate private outputs. Refuse to overwrite a different existing raw input.
- Put quick start and a short demonstration before technical details in the final README. Keep live-model verification, accounting/response assumptions and visual-review limits explicit.
- Prepare an audited source archive without publishing/submitting it. Include the final memo PDF; its optional builder uses free ReportLab, not an application dependency.

## Authorized GitHub publication - 2026-10-30

- Re-read the supplied company PDF and add a requirement/deliverable map, including its explicit AI allowance and required examples of actual AI mistakes. Summarize the assignment rather than redistribute its PDF or customer dataset.
- Record the user-reported fresh Groq Hinglish fixture success for both address and name. Keep representative accuracy unmeasured and the historical replay offline; no financial findings are revised from a single live check.
- The user explicitly authorized pushing the reviewed public files to the existing GitHub repository. Audit before staging and inspect the exact staged snapshot; exclude credentials, environment files, customer records, per-order exports, caches and local state. Publish the memo, source, synthetic examples and aggregate findings. Repository publication is separate from submitting the assignment to the company.

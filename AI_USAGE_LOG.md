# AI usage log

## Tools and responsibilities

- **OpenAI Codex desktop:** assignment/PDF reading, CSV inspection, implementation, debugging, tests, financial analysis, native UI and documentation. The user reviewed the running UI and tested quoted Hinglish input.
- **Runtime LLM adapter:** optional Groq Free Plan `openai/gpt-oss-20b` for structured name/address interpretation. The user privately configured a key and reported successful live Hinglish responses; representative accuracy remains unmeasured.
- **Offline runtime:** deterministic Python, explicit reply parsing, mock provider responses and a labeled address heuristic. These are not live LLM output. No paid project API, UI asset or external account is needed.

## Where AI belongs

An LLM can interpret incomplete English/Hindi/Hinglish addresses and obvious placeholders. Python handles validation, arithmetic, risk, thresholds, scenarios, timers, payments and events. Text findings cannot independently cancel orders, change numeric risk or verify a physical address.

## Three AI mistakes/weak outputs caught and corrected

### 1. SQLite connections stayed open

Codex initially used a SQLite context manager as though it closed the connection. It commits/rolls back but does not close the handle. Windows tests exposed file-lock errors during temporary-database cleanup. Added contextlib.closing, checked cache/error paths and reran the suite. This was a real defect, not a fabricated example.

### 2. Address replies required a rigid format

The first flow understood single-field ADDRESS:/NAME: commands but treated natural Hinglish corrections as unclear. User testing exposed this. Added explicit labeled double-quoted extraction, supporting both fields atomically, with eleven regression tests. "Satpur Nashik" is now saved but remains incomplete for shipping; fuller details and a separate YES are required. Ambiguity gets guidance, not guessed updates.

### 3. A global font setting flattened the UI

The first shared theme set a Tk font option that overrode larger ttk heading/currency styles. Visual inspection showed title and money labels at ordinary text size. Removed the override, reloaded the preview, visually checked the overview and added style-hierarchy coverage. The user stopped desktop inspection before the latest conversation visual recheck; automated interaction checks cover its behavior.

## Weak results retained

The offline heuristic matches 7/8 small address expectations and 8/8 name expectations. Its numberless-house miss is retained for live evaluation; these cases are not representative accuracy evidence.

The frozen September base scenario is **INR -889.30** versus ship-all despite positive August selection results. No September retuning was used to hide that outcome. Unmeasured intervention responses are explicit, and the memo recommends a supervised pilot.

## Verification and publication

The pre-packaging suite passed 113 tests. Phase 6 setup/package checks and final totals appear in VERIFICATION.md. Customer data, credential files and local state are excluded publicly. Audits report categories/filenames only. No key value is included in code, reports or logs, and no live-model accuracy claim is made.

## Live-provider troubleshooting

The user's first live fixture returned unavailable with provider_http_error. Added HTTP status and static diagnostic hints, with three tests confirming that provider bodies/key-like text are never echoed and no retry is added. The rerun identified a security-layer HTTP 403. Two probes using a deliberately invalid, non-credential token reproduced HTTP 403 with the default Python-urllib agent and HTTP 401 (authentication reached) with an explicit application agent. Added User-Agent OytraCODDecisionEngine/1.0, with a transport regression test covering the header, timeout and disabled redirects. The user then reported a successful live inference: available=1, address_matches=1, name_matches=0. Groq classified the original Demo Customer name as a placeholder, a reasonable result that revealed an inconsistent fixture expectation. Replaced Demo Customer with the plausible fictional name Aarav Sharma in non-placeholder fixtures, preserving their intended expected category; the dedicated placeholder case remains unchanged. No prompt/model changes were made to force a match. The user reran the revised fixture and reported available=1, address_matches=1, name_matches=1, language=Hinglish, cached=false. This confirms a fresh successful response for one hand-authored fixture, not representative accuracy.

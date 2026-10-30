# Founder dashboard

Launch locally with `python -m src.dashboard`. All analysis and interaction are local and free. The dashboard does not call an LLM, create messages or mutate simulator state.

The latest historical date is 2026-09-30. Its sample export contains 9 orders: 6 ship as-is, 2 confirmation, 1 prepaid, and 0 holds. Base-scenario net impact is INR +240.19 for that day. This is a hypothetical daily result; the frozen full September result remains INR -889.30 and must not be represented as proven savings.

Read the project's README for settings, financial definitions, timezone assumptions and export instructions. A historical day with no orders shows empty bucket counts and unavailable financial impact. The simulator source reports initial bucket counts and current activity separately, with no realised profit claim.

Generated export bundles are under exports/. Each contains orders.csv, summary.csv, sensitivity.csv and context.json. The folder names include scenario and data hashes. Existing frozen policy/evaluation files are not overwritten by dashboard scenarios or exports.

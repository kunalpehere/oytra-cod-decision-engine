# Submission checklist

## Deliverables prepared

- Repository destination: https://github.com/kunalpehere/oytra-cod-decision-engine
- Founder memo: `output/pdf/business_memo.pdf` (two pages).
- Run instructions and product limitations: `README.md`.
- Company requirements and AI-use instructions: `ASSIGNMENT_REQUIREMENTS.md`.
- Important choices: `DECISION_LOG.md`.
- AI tools and three observed corrections: `AI_USAGE_LOG.md`.
- Final verification: `VERIFICATION.md`.
- Public-safe source archive: `output/submission/oytra-cod-decision-engine-public.zip`.

## Before submission

1. Review the memo and final demonstration yourself. Do not describe scenario estimates as measured savings.
2. Publish the reviewed source files and memo to the repository. The local remote is configured; preparing this package does not push it or submit the assignment.
3. Check the GitHub link from a signed-out browser after publication. The company dataset and all credential/local-state files must remain excluded.
4. Tell the evaluator to use their supplied orders_sample.csv with the one-command setup in the README. No private customer dataset is included publicly.
5. Submit the repository URL and memo file through the company's requested channel. Add your candidate identity in that channel if required.

## LLM verification status

The optional Groq adapter uses the requested free-tier GPT-OSS 20B model. The user's revised live Hinglish check passed both address and name expectations with cached=false after fixing the HTTP client header; representative interpretation accuracy remains unmeasured. The original Demo Customer fixture had an inconsistent name expectation, now corrected by using a plausible fictional name in non-placeholder cases. Offline behavior, provider contract mocks and quota/error handling are tested. The complete desktop demo works without a key. Do not imply that live-model accuracy has been measured.

## Suggested submission message

Hello,

Please find my COD decision-system assignment here:
https://github.com/kunalpehere/oytra-cod-decision-engine

The repository includes setup instructions, the decision and AI usage logs, and the founder memo. The local demo covers explained decisions, confirmation/prepaid conversations and a daily financial dashboard. Please use the supplied assignment CSV with the documented setup command; customer records and credentials are excluded from the public repository.

The memo separates observed outcomes from hypothetical intervention effects and retains the negative September scenario. The optional free-tier LLM integration has mocked tests and a user-reported fresh live Hinglish response matching both address and name expectations; representative live-provider accuracy remains unmeasured.

Thank you.

# Final verification

Verified on 30 October 2026 using Python 3.12.14 on Windows.

## Clean public-safe copy

Copied only Git's publishable files into a new isolated directory, before supplying the assignment CSV separately. No company dataset, environment file, credential container, simulator state or cache was copied as public source. This is a fresh-file copy, not a claim that a remote GitHub clone has been published.

| Check | Result |
| --- | --- |
| One-command preparation from the supplied CSV | Passed in **4.3 seconds**, below ten minutes |
| Offline setup | Zero API calls; 2,018 source rows, 1,988 retained, 1,987 resolved |
| Complete clean-copy test suite | **119 passed**, 0 skipped; 18.32 seconds |
| Decision CLI | All four action buckets demonstrated |
| September 30 export | 9 orders; scenario net impact INR +240.19 |
| Desktop widget startup/navigation | Passed using withdrawn Tk windows |
| Founder memo | Two nonempty pages; key business numbers checked; both rendered pages visually reviewed |
| Protected original data/frozen artifact | Unchanged |

The full September frozen scenario remains INR -889.30. A positive example day is not evidence of positive monthly impact. Response assumptions, accounting alternatives and holdout limits are disclosed in the memo and README.

## Review limits

- The user's revised Groq Hinglish check returned available=1, address_matches=1, name_matches=1 and cached=false from openai/gpt-oss-20b. This is user-reported evidence for one hand-authored fixture, not representative interpretation accuracy. This verifier makes no live API calls; mock provider tests are not live-model accuracy evidence.
- The overview was visually reviewed after refinement. Conversation behavior has automated checks and user screenshot validation; its latest automated desktop recheck was stopped by the user. The clean-copy GUI check verifies widget startup/navigation, not a new visual review.
- Timing excludes installing Python, obtaining the supplied assignment CSV and optional live-provider signup. The application has no pip dependencies. ReportLab/pypdf are optional document-authoring/verification dependencies, not runtime requirements.
- Common credential-pattern/path auditing does not certify arbitrary secrets, Git history or remote contents. No files were pushed or sent to the company by this verification.

## Reproduce

```powershell
python -m src.setup_project --input "C:\path\to\orders_sample.csv"
python -m unittest discover -s tests -v
python -m src.app
python tools/audit_repository.py
```

The optional packaging verifier is `tools/verify_submission.py`; it requires pypdf for checking the included memo. Detailed temporary diagnostics are kept under ignored tmp/ and are excluded from the source archive.

# Verification record

Local verification completed on **7 November 2026**. These checks concern the working prototype and saved artifacts; they do not establish audience lift or live provider availability.

| Check | Result |
| --- | --- |
| Python unit tests | 74 passed, covering parsing, source validation, provider mocks, real-event contracts and simulator isolation |
| Ruff lint and formatting | Passed for application, scripts and tests |
| Frontend syntax and Prettier | Passed for JavaScript, HTML and CSS |
| Isolated HTTP checks | Passed: private-file denial, host/origin checks, malformed inputs, fresh upload, polling and exports |
| Editorial browser flow | Passed: source inspection, filters, coverage, quality, history, new analyses, upload, download and mobile layout |
| Reading browser flow | Passed: consent, randomized cards, reload censoring, continuation, offline retry, test export exclusion, shared-device reset and deletion |
| Synthetic browser flow | Passed for all three scenarios, provenance, model snapshots, downloads, persistence, mobile layout and real-data isolation |
| Fresh source archive | Extracted and ran unit tests, source hygiene, public demo and independent audit without credentials |
| Development installation | Editable installation and pinned development dependency installation passed in a new temporary virtual environment |
| Solution PDF | Exactly two pages; both pages rendered and visually inspected |

The isolated HTTP/browser runner uses a temporary server, free port and database. Its studies and generated responses do not enter the live experiment database. Headless browser testing injects a focus-loss signal to verify the reading-time guard, because headless Chrome can report every tab focused; this is a software test, not attention evidence.

## Saved full-pack evidence

An independent audit of `output/runs/full-pack-qwen` verified all saved artifact checksums and reapplied source/gate checks:

- 50 episodes and 3,727 timestamped events.
- 16,023 generated candidates, 14,758 source-valid intervals and 553 distinct intervals.
- Six shortlisted promos, all source-valid; no selected dialogue cut-throughs.
- 48 usable AI assessments from 100 logical proposal/critique calls. Two critiques were excluded by output/evidence validation; no provider failure is recorded in this final run.
- Provider for this saved run: `qwen/qwen3.8-27b`. Changing the current endpoint does not change this provenance.

These counts are historical run evidence, not a new full-pack inference performed during repository cleanup. Raw model outputs remain unchanged. Source-validity differences versus a fixed-window baseline are structural checks on different selected samples, not causal engagement improvement.

## Scope of the checks

Verification is local. Hosted automation has been removed from the repository; the complete tests and browser checks remain available through the documented commands. No hosted test pass is claimed.

No new external model inference, remote deployment, real-audience model training or applicant-narrated video was performed as part of this verification. The source and private submission archives exclude real participant data. Synthetic outcomes are separately labeled and do not prove customer preferences.

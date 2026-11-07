# Real-interaction reading pilot

This is the executable cold-start experiment. People browse text cards and choose whether to read more. No LLM generates responses, predicts supposed participants, or supplies training labels. There is no behavioral model training or epsilon-greedy selection in this first collection stage.

## Run and collect

1. Start `python3 -m promo_lab serve` and open `http://127.0.0.1:8765`.
2. Select **Reading experiment**. Choose the public demo or a saved analysis run, enter a study name and create it. Leave **Software test** unchecked for real participants.
3. Open the participant link on this computer. Each participant explicitly consents before a session or event is created. People can skip, go back, continue, finish or delete their session.
4. For another person on the same browser, finish the previous session, wait for syncing, then use **New participant on this browser**. Ordinary refreshes resume the same anonymous assignment. Clearing browser storage or switching profiles creates another identity; counts are not verified unique people.
5. Refresh the report or wait for its automatic ten-second refresh. Export JSONL for training and raw events for audits. Stop enrollment with **Close enrollment**; already consented sessions can finish. Remote participant access requires later deployment work.

Each study snapshots its content and definitions. Creating a new study is required to change candidates or thresholds. Existing results and database contents are not overwritten by a new analysis.

## Content and assignment

The public demo has three source-valid cuts from one original fictional screenplay and authored fictional continuations. Saved-run studies use up to 30 shortlisted source-valid cuts and genuine subsequent dialogue/actions from the saved episode timeline, extending into available next episodes if needed. Speaker labels are displayed; camera instructions are omitted. No missing scene or sequel is generated. Candidates with no subsequent source text are excluded; do not generalize results to these excluded candidates or the entire candidate pool.

Six of eight original filler stories are selected and shuffled, then one uniformly sampled target promo is inserted at zero-based position 2, 3, 4 or 5. Every card offers continuation, so the target has no special call to action. Saved-run targets share a neutral title to avoid testing AI-authored titles. These controls reduce some demand and spoiler effects; text cards remain a limited approximation to a reel feed.

Selection probabilities are stored: candidate `1/N`, position `1/4`, joint `1/(4N)`. They describe candidate and position randomization, not the probability of a person reaching that position. This is uniform exploration. When enough data exists, fit a small model, use participant-held-out evaluation, and compare any future exploitation policy to a randomized control. Such learning is not enabled automatically.

## Measurement and events

`view_start` is emitted only when a card is at least 60% visible and the page is visible and focused. Foreground active time accumulates separately for the card and continuation reader. Background tabs, loading continuation content, and time spent in the reader do not increase card dwell. Main-thread stalls are capped at one credited second per timer tick. A visible text unit counts when at least half of the unit or half a reading viewport is visible. Coverage indicates exposure to text, not reading comprehension.

Events are `view_start`, `progress`, `view_end`, `continue_open`, `continuation_progress`, `continuation_close`, and `session_finish`. A five-second heartbeat saves cumulative times and coverage. Each event has a UUID, contiguous session sequence, elapsed session milliseconds and exposure/card identifiers where applicable. Event IDs make identical retries idempotent. Payloads reject arbitrary fields, invalid units, inconsistent clocks, conflicting duplicates and impossible or decreasing cumulative measurements. The server cannot verify human attention or defend against a participant deliberately forging browser telemetry.

The browser persists its queue before uploading and retries after reconnecting. A short-lived per-study tab lease prevents ordinary accidental multi-tab collection. An unload marks the current exposure interrupted; a crash may leave it open, and a later resume closes it as interrupted. Beacons are best effort. The last unsaved heartbeat can be lost if a device or browser fails, so partial outcomes remain partial. The prototype caps sessions at 24 hours and 4,000 events, with an offline queue cap of 500; it pauses rather than dropping events silently. Local storage must be enabled.

## Training row and Y

Only actually observed target exposures are exported. Filler events remain in the raw event audit. There is no row for an unseen assigned promo. Repeated views are separate rows with the same content features and potentially different outcomes; a repeat is not a contradiction.

X freezes content/source hashes and source segments, source event IDs, word/unit/speaker counts, genre, original clip duration, position, preceding card context, prior-exposure count, elapsed session time, UTC hour and weekday at exposure start. Saved-run IDs allow a later training job to join source text or embeddings from the corresponding immutable run. Outcomes never enter X. This prototype does not calculate embeddings.

| Y field | Definition |
| --- | --- |
| active_dwell_ms | Foreground visible card time, excluding continuation reading |
| text_coverage_fraction | Distinct visible card units / total card units |
| held_3s_text | Active card time ≥3 seconds |
| completed_text_proxy | ≥90% units visible and ≥3 active card seconds |
| clicked_continue | Actual click opening the continuation reader |
| continuation_active_ms | Foreground active continuation time after content loads |
| continuation_coverage_fraction | Distinct visible continuation units / total continuation units |
| qualified_reading_continuation | Click plus ≥15 active continuation seconds and ≥75% continuation-unit coverage |

An explicitly closed exposure supplies observed negatives for unmet outcomes. Open or interrupted exposures preserve unknown binary outcomes as `null`; positives already observed remain `1`. Continuous measurements from these exposures are marked `partial`, not completed-duration labels. `label_status` makes this explicit. For binary training, filter to observed values for that target; do not blindly coerce null to zero. A click followed by interrupted continuation proves the click, but does not establish a negative qualification label.

## Reporting and uncertainty

Primary metrics use the first target exposure per anonymous participant, with repeats reported separately. Each outcome has its own numerator, observed denominator, unknown count, rate and descriptive Wilson 95% interval. No observations means a null rate, not 0% success. Different outcomes can have different denominators. Informative dropout can bias observed rates; report the unknown counts. All-exposed missing-outcome bounds additionally range from `successes / exposed` to `(successes + unknown) / exposed`. These bounds concern missing outcomes, whereas the Wilson interval describes sampling uncertainty among observed outcomes.

The report also includes assignments, participants who did not reach their assigned target, explicit finishes, repeat exposures and export row counts. It does not claim causal lift, video attention, model accuracy or convergence. Small samples and employees' reading preferences do not establish external customer performance. Do not choose a supposed top 1% from this small pilot on raw rates alone. Later validation should split by participant and content, use mature windows, and evaluate on fresh traffic.

## Data handling and checks

SQLite persists at `output/experiments/interactions.sqlite3` with restrictive file permissions. The folder is Git-ignored and excluded from source/submission archives. No names, emails, device fingerprints or IPs are stored in experiment records; the server suppresses HTTP request logging. A browser-generated random key is transformed into a study-specific anonymous identifier. Auth tokens stay out of event and training exports. Browser local storage contains the session token and unsynced events; deleting a session removes the server session/events/exposures and local state. Downloaded copies are outside that deletion. There is no automatic retention expiry; the local operator controls retention.

The server binds to loopback and is a single-computer prototype. Admin reports and downloads share its local API; participant consent is not a production authorization boundary. Internet hosting would require separate participant/admin access, secure transport and durable hosting. No experiment responses are sent to Nemotron, Groq or another model provider.

`python3 -m unittest discover -s tests -v` covers assignments, consent, idempotency, atomic rejection, repeated exposures, censoring, qualification, source-only saved-run cards, persistence, deletion, exports and confidence intervals. `node scripts/experiment_smoke.mjs` exercises actual Chrome controls, reload, offline retry, mobile layout and deletion. Browser tests create explicitly marked software-test studies, excluded from default training exports, and delete them afterward. No test data is presented as real audience evidence.

# Synthetic feedback-loop demonstration

Open **Synthetic demo** in the sidebar (`http://127.0.0.1:8765/#simulations`). Choose a study's candidates and generate a seeded run. Real responses stay in the Reading experiment page. The simulator reads only the study's frozen candidate snapshot; it never copies, inserts, modifies or trains on real participant responses.

The default run creates **4,800 explicitly synthetic exposures**: 400 random cold-start viewers, 200 held-out validation viewers and 14 days with 150 policy viewers plus 150 uniform-control viewers per day. Each row records the familiar reading X/Y fields, synthetic provenance, arm, model version and exact candidate/position selection probabilities. These are direct simulated exposure outcomes, not forged browser events, participant consent or sessions.

## Mechanism

1. The simulator assigns each candidate an assumed qualified-reading probability. With different appeal these range from 4% to 26%, shuffled across candidate IDs by a recorded random seed. The mechanism does not inspect script quality, LLM judgments or real feedback. Click and dwell/coverage outcomes are sampled consistently with qualification (at least 15 continuation seconds and 75% unit coverage).
2. Uniform random cold-start exposures supply binary qualification feedback. A **Beta-Bernoulli response model** starts each candidate at Beta(1,1), then increments successes/failures. Its posterior mean predicts qualification for that candidate. This is a working candidate-level baseline, not the proposed future text encoder or an embedding fine-tune.
3. A separate group of synthetic viewers evaluates the frozen cold-start model using Brier score and binary log loss against a constant cold-start-rate predictor. Validation rows never update the model. This checks same-candidate synthetic prediction, not unseen-script or real-audience generalization.
4. Online synthetic viewers are randomly allocated in equal numbers to the learning policy and uniform control each day. Both arms use the same day's response mechanism. The policy freezes its estimates before each day's traffic. Epsilon starts at 60%, decreases to 20% by day 5 and remains there. Exploitation selects the current highest predicted candidate; tied best candidates are sampled uniformly. The logged propensity is `epsilon / N + (1-epsilon) / tied_best_count` for a best candidate and `epsilon / N` otherwise.
5. At day end, only policy-arm feedback updates the model. Historical excess counts decay by 0.9 daily before incorporating the new batch, retaining the Beta(1,1) prior. Control and validation never feed updates. Every model snapshot and pre-traffic prediction is saved. Candidate identity is the only predictor; recorded content/context features are not consumed by this baseline.

## Three scenarios

| Scenario | Assumption | What to discuss |
| --- | --- | --- |
| Different candidate appeal | Fixed, unequal response probabilities | Learning can allocate more traffic to the candidates assumed to work better |
| No signal | Every candidate has 15% qualification probability | Expected policy advantage is zero; observed differences are sampling noise |
| Changing trends | Candidate appeal reverses halfway through | Old feedback can mislead the model and adaptation may lag |

No seed search, forced improvement, smoothing of rewards or predetermined success curve is used. Repeating a seed and configuration reproduces the same synthetic outcomes. Changing the seed can change which candidates appear best and the realized advantage. The curves can rise or fall. Randomized arm comparisons are conditional on this simulator and do not validate its assumed response model.

The report shows realized arm rates, descriptive arm-level Wilson intervals in its JSON, absolute percentage-point difference, cumulative curves, validation losses, per-day exploration and simulator-only expected rates. Assumed candidate probabilities are disclosed in a separate table and never supplied as model features/labels. This prototype does not calculate statistical significance or claim a real-world causal improvement.

## Data boundary

Artifacts live in `output/simulations/<id>/`, separately from `output/experiments/interactions.sqlite3`. They are ignored by Git and excluded from the standard submission archive. Downloads have a `SYNTHETIC-` filename prefix. JSONL rows contain `data_source="synthetic_simulator"`, `is_synthetic=true` and `training_eligible_for_real_model=false`; every Y status is `synthetic`. CSV includes the same provenance columns. Do not manually merge them into real experiment training exports. The demo model rejects real rows and control/validation rows.

Exports include `synthetic_responses.jsonl`, `synthetic_responses.csv`, `report.json`, `model.json` and a frozen `candidate_snapshot.json` with content features and unit counts. The snapshot contains no participant responses. No API key or LLM call is required. The independent random seeds and simulator version are recorded for reproduction.

Run from the CLI if preferred:

```bash
python3 scripts/run_synthetic_demo.py --study YOUR_STUDY_ID --scenario stationary --seed 42
# Omit --study to use original public fiction.
python3 scripts/run_synthetic_demo.py --scenario no_signal --seed 42
```

## Submission wording

“The prototype demonstrates a functioning feedback loop on explicitly synthetic responses. Under an assumed difference in candidate appeal, learned allocation can outperform random selection inside the simulator. This establishes that the implementation works under those assumptions; validating customer preferences and engagement improvement requires real randomized audience data.”

One actual participant response is useful for checking that the logger works, but cannot calibrate a human response simulator or validate a ranking model. Other omitted mechanisms include informative dropout, fatigue, population shift, browser failures, repeated viewers and mismatch between reading and video consumption. A production claim requires enough mature real feedback, a suitable content model, leakage-aware validation and a randomized customer holdout.

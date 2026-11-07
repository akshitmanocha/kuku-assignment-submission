# Promo selection: ML architecture v1

Status: reference specification for the real-audience model. A separately labeled synthetic candidate-level learning baseline is now implemented (docs/SYNTHETIC_DEMO.md); it does not validate the proposed real-audience architecture.
Implementation boundary: the executable six-hour submission uses source-grounded LLM editorial discovery and an offline rules baseline, as documented in README.md. A text-card feed experiment now collects real reading interactions (see docs/EXPERIMENT.md). The embedding encoder, behavioral heads, video feed experiment and epsilon-greedy learning described here are the reference design for a later data-backed stage; no such trained audience model is claimed in the current app.
Scope: a six-hour prototype, with the longer-term experimentation and learning design documented separately below. Deployment infrastructure is deferred. The future learning prototype would use frozen pretrained embeddings; contrastive learning and encoder fine-tuning are future improvements.

## 1. Objective and agreed experiment

Find source-grounded 20–60-second promos and learn which eligible promos cause qualified continuation into the show. The model predicts response probabilities, not guaranteed individual behavior.

The initial experiment is a simulated reel feed: participants scroll through ordinary reels interspersed with randomly assigned candidate promos. No explicit pairwise preferences or ratings are required. Initial labels come from behavior. Footage and cleared surrounding reels are prerequisites; scripts alone cannot produce video-engagement labels.

Use one logical training row per valid promo exposure. Candidate content and metadata may be joined onto that row by ID; separate preference labels are not part of this architecture. Do not fabricate audience outcomes for the assignment.

## 2. Candidate generation and eligibility

1. Parse episode-qualified timestamps, dialogue, actions, and camera descriptions; preserve raw text and stable source IDs. Normalize field capitalization and retain unresolved aliases.
2. Use an LLM to identify hooks, stakes, open questions, resolutions, and required context, each with source evidence. Keep episode summaries out of the candidate-only comprehension assessment.
3. Search forward from hooks and backward from unresolved endings using plausible dialogue/action boundaries. Also enumerate duration-valid intervals at plausible boundaries to reduce annotation-driven omissions.
4. Test neighboring boundary variants. Start with continuous clips; allow up to three chronological segments when they improve coherence. This cap is a v1 assumption, not a brief requirement.
5. Code checks 20–60-second total playback duration, valid source intervals, dialogue truncation, overlapping segments, and duplicate intervals. Overlapping screenplay tracks are not summed as independent time.
6. A candidate-only assessment checks comprehension and a consequential unresolved ending. A separate source-context assessment checks misleading assembly. LLM annotations are estimates, not measured probabilities.
7. Group near-duplicate boundary variants by source overlap and narrative beat. Preserve alternatives for boundary experiments, but do not count them as distinct shortlist discoveries.

Use the hook/comprehension/stakes/progression/cliffhanger/cut-quality rubric for initial editorial screening and as a baseline. It does not create behavioral ground truth. Randomized internal exposure samples eligible candidates broadly, rather than only rubric winners.

## 3. Exposure and label contract

One exposure ID identifies one successfully presented promo opportunity. A valid immediate skip is an outcome, not grounds to exclude the row. Technical playback failure, duplicate telemetry, and unavailable tracking must be identified separately. Track assignment and playback failures for experiment integrity.

Store both event time and when an outcome became available. All features are computed using information available before exposure. Use a fixed timezone for windows and store timestamps in UTC.

Required metadata:

- exposure ID, anonymous viewer ID, session ID, candidate ID, show ID;
- assignment time, exposure time, content/script version and segment definition;
- eligibility-set reference, feature/annotation/encoder versions;
- policy/model version, epsilon, actual selection probability, explore/exploit branch;
- source population (internal or customer), assignment group;
- per-outcome status: pending, observed, unavailable, or invalid.

Repeated legitimate exposures are separate rows, even when X is identical. Do not deduplicate them by promo ID. The repeated rows estimate a conditional probability; they do not require one deterministic label per X. Repeated viewers and promos create dependence that evaluation must account for.

### Behavioral outcomes

| Field | Definition |
| --- | --- |
| held_3_seconds | Foreground active playback reaches three seconds. |
| watch_seconds | Unique active content seconds watched, excluding buffering/background time; replay time logged separately. |
| watch_fraction | watch_seconds / duration, capped at one. |
| completed_promo | End reached, with a documented small player-end tolerance. |
| started_show | Attributed show start within the observation window. |
| qualified_continuation | Attributed show start within the window, followed by at least the agreed active show-watch threshold. |

V1 label parameters: 24-hour show-start window; qualification requires 60 seconds of active show viewing within that window. These are proposed business definitions, to be versioned and changed only explicitly. Very short qualifying content needs a documented alternative definition before testing.

In the internal feed, continuation must actually be available to collect continuation labels. If only promo playback is available, train attention outputs only; do not call an attention prediction a continuation probability.

Use direct exposure-to-show navigation for primary attribution where possible. Deduplicate a conversion to one exposure; ambiguous multi-exposure conversions stay out of the primary causal comparison or follow a prespecified attribution rule. Last-touch attribution is a reporting convention, not proof of causal credit. Missing tracking is not zero. Unshown candidates have no behavioral labels.

## 4. Final X feature contract

### Script/content features, available for new candidates

- Text representations of opening [0, 3s], the entire candidate, and ending [D-5s, D]. Include overlapping source events with interval markers, type, speaker, and playback-relative times. Preserve segment joins and event order. Script line timing cannot reveal exact word availability inside a partial spoken line; mark boundary uncertainty.
- Duration, segment count, scene-transition count, speaking-character count.
- Time to first dialogue and first salient action, with missing indicators.
- Dialogue words per second and union-of-dialogue-interval coverage; overlapping intervals do not double-count coverage.
- Content/theme tags, hook category, stakes clarity, context dependence, unresolved-question assessment, resolution-before-cut assessment.
- Boundary/truncation and continuity flags; annotation missing/uncertain indicators.

Store evidence for narrative annotations. Do not expose logline-only facts or future-episode information as if the viewer saw them. No video-only features are required to rank a fresh script. When actual footage differs, version the creative and record the mismatch.

### Exposure features, known before presentation

- Feed position, elapsed session time, placement.
- Preceding reel category and duration, with missing values for session start.
- Viewer preferred language, new/returning status; prior genre interests only when observed and usable. No individual viewer-ID embedding in v1.
- Number of prior exposures to this promo, time since last exposure, prior similar-content exposure where reliably defined.
- Local hour/day cyclical encodings, days since promo launch.

### Historical features, enabled only when available

- Prior 7-/30-day hold and qualified-continuation rates, separately for internal/customer sources; associated eligible exposure counts and missing indicators.
- Use only outcomes already available at feature time. Smooth rates using a training-only population prior; use the prior plus count zero and missing flags for new promos. Keep the snapshot for reproducible evaluation.
- External topic-trend levels/changes are optional future inputs, not fabricated v1 values. Calendar time does not establish meme relevance. Recent response/fatigue can detect changes but does not establish their cause.

IDs, assignment branch, epsilon, selection probabilities, and model version are analysis metadata, not initial predictor inputs. Current-exposure watch/click/continuation outcomes never enter X.

Fit scaling, category vocabulary, and imputation on training data only. Unknown categories get explicit values. Keep the same feature definitions during training and scoring.

## 5. Model architecture

V1 checkpoint: `nomic-ai/modernbert-embed-base`, used through Sentence Transformers with the documented `search_document: ` prefix. Pin the actual checkpoint revision during implementation. Use its supported 256-dimensional representation, normalized as documented, for each of three text views. The checkpoint is an engineering starting choice, not a validated winner for this task.

Shared encoder E:

    z_open = E(opening text)       # 256 dimensions
    z_full = E(ordered full text)  # 256 dimensions
    z_end  = E(ending text)        # 256 dimensions

Concatenate these 768 values with standardized numeric inputs, missing indicators, and one-hot low-cardinality categorical inputs. Use:

    concat -> Linear(128) -> ReLU -> Dropout(0.1)
           -> Linear(32) -> ReLU
           -> three separate output heads

Outputs:

1. Hold head: sigmoid, P(held_3_seconds).
2. Watch head: sigmoid, expected watch_fraction.
3. Continuation head: sigmoid, P(qualified_continuation), the eventual ranking objective.

Show start and completion are tracked outcomes/metrics, not extra heads in v1. Do not average the three outputs into an arbitrary attention score. Rank by continuation when sufficiently trained and validated. Before continuation labels exist, expose the attention model as a separately named policy with a different objective.

Check actual tokenizer/config input limits; never silently truncate an ending. If a candidate exceeds the supported limit, flag it for preprocessing revision rather than producing an incomplete full-clip representation.

Retain a regularized logistic-regression baseline with frozen content features and the same available metadata. Multitask/MLP complexity is accepted only if it improves held-out evaluation; auxiliary heads can be disabled if they harm the primary objective.

## 6. Prediction-head training with frozen embeddings

With masks m for observed labels:

    L = mean_observed(BCE(qualified_continuation))
      + lambda_hold * mean_observed(BCE(held_3_seconds))
      + lambda_watch * mean_observed(MSE(watch_fraction))

An unavailable head contributes no loss; normalize per head by observed-label weight. Initial auxiliary weights are 0.2 each, chosen as explicit starting hyperparameters and checked against zero-auxiliary baselines using validation data. Primary weight is one. Do not apply positive-class oversampling/weights without accounting for changed probabilities and recalibration.

For the six-hour prototype, keep E frozen throughout. If real behavioral labels are available, fit only the small heads with AdamW, weight decay, and early stopping on grouped validation results. Tune regularization only on development data. Without real labels, use editorial ranking and leave the behavioral heads untrained; demonstrations must not imply validated customer predictions. Cached embeddings carry the pinned encoder version.

Encoder adaptation and contrastive training are outside the prototype implementation scope. No explicit preference-labeling workflow is required.

Retain individual exposure rows; aggregation is optional only for genuinely equivalent inputs and with counts preserved. Internal behavioral data initializes the model but is not assumed representative of customers. Keep source-specific evaluation and transfer calibration; do not blindly pool incompatible populations.

## 7. Initial experiment and epsilon-greedy policy

Before a trained model exists, use randomized exposure over the eligible pool, with balanced coverage and randomized insertion positions. Sample size follows outcome frequency, candidate coverage, and uncertainty, not just participant count. A small employee cohort is a pilot, not proof of external lift. Use cleared footage/content and unfamiliar participants where possible.

Once a validated initial ranker exists, use epsilon-greedy over the full eligible experimental pool, including candidates outside the posting shortlist:

    with probability 1-epsilon: choose highest predicted primary response
    with probability epsilon: choose uniformly from N eligible candidates

For a unique deterministic greedy winner:

    P(winner) = 1-epsilon + epsilon/N
    P(other)  = epsilon/N

Log the actual conditional probability after all eligibility/frequency rules. Prespecify tie-breaking; a randomized tie changes these probabilities. Preserve the assignment candidate set. Stochastic safety or eligibility steps must be reflected in the logged assignment design.

Use higher exploration during early pilots and reduce it as evidence improves. 80% exploitation / 20% exploration is a configurable later operating point, not a guaranteed optimum. Do not decay solely on training-loss stability or elapsed days; keep a nonzero floor and coverage for new creatives.

The final posting shortlist is the top 1% of distinct eligible candidates, subject to minimum editorial quality and sample uncertainty. Do not force a candidate if none qualify. Exploration remains a separate bounded experiment, not restricted to that top 1%.

For an overall show shortlist, score candidates over the same supported reference audience/context distribution and average predicted continuation. Candidate-specific fatigue features remain candidate-specific. Do not rank aggregate raw rates from differing traffic mixes as if exposure conditions were equivalent.

## 8. Evaluation and monitoring

Content-stage checks: audited parsing, valid source/duration rate, grounded annotation rate, duplicate rate, and recovery against independently identified narrative opportunities. Behavioral data from served candidates alone cannot measure missed opportunities. Do not report editorial acceptance if no reviewers actually evaluated it.

Predictive evaluation: primary log loss, Brier score, and calibration; auxiliary hold log loss and watch-fraction MAE. Compare to constant-rate, random selection, editorial, and frozen logistic baselines as applicable. Class accuracy is not primary for rare continuation events. Offline predicted quality is not proof of policy lift.

Behavioral metrics:

- qualified continuation / mature valid attributable exposures (primary);
- show starts / mature valid attributable exposures;
- held_3_seconds / valid observed playback exposures;
- mean watch_fraction and completion / valid observed playback exposures;
- qualified continuations / attributed show starts (diagnostic; composition-dependent);
- controlled absolute and relative lift versus the incumbent selection policy;
- eligible coverage, assignment/telemetry failures, missing-label rate, and exploration allocation.

Always report denominators and uncertainty. Do not drop legitimate early skips or condition primary conversion rates only on completers. Distinguish insufficient volume from bad performance.

Compute pooled rates over 1/7/14/30-day exposure cohorts. Use outcome-specific maturity; exposure dates and conversion dates are not interchangeable. Overlapping windows are not independent confirmations. Compare latest versus preceding nonoverlapping seven-day periods for trend diagnostics. Segment by source population, placement, and duration where volume supports it.

Split forward in time and separately test unseen participants. Keep an additional show/arc and duplicate-family holdout to test new-content generalization; one show cannot establish cross-show robustness. Keep calibration data separate from model selection and final test data. Build historical features using as-of availability, never retrospectively completed labels.

Use viewer-clustered uncertainty in online comparisons; account for promo/show clustering where evaluating content generalization. Keep the incumbent and challenger randomized concurrently, preferably assigned by viewer to reduce carryover. Avoid declaring lift from repeated daily peeking; prespecify a fixed analysis horizon or a valid sequential procedure. Logged propensities support appropriate offline policy analysis, but do not remove unsupported actions, high variance, or confounding by themselves.

## 9. Update protocol and implementation boundary

Collect continuously; construct mature, validated labels before training. Retrain only when adequate new evidence exists. Use accumulated data with validation-selected recency weighting and retain older examples for stability. Train a challenger, evaluate on later/grouped data, calibrate if needed, then use a controlled comparison before promotion. Version and retain the previous encoder, preprocessing, head weights, reward definition, and policy for rollback. Improvement is measured; convergence to globally optimal weights is not promised.

The assignment can implement parsing, candidate generation, source validation, editorial ranking, and raw output generation now. It can implement schemas and model interfaces without claiming an audience-trained model exists. Live video experimentation, real behavioral training, and measured customer lift remain future work until footage, participants, and outcomes exist. No infrastructure/deployment choice is committed here.

## 10. Future improvements: task-specific embedding training

Once there is enough diverse behavioral evidence, investigate adapting the encoder to promo structure and audience response. Evaluate changes against the frozen-encoder baseline on later data and unseen content; exposure count alone is insufficient if observations repeat a few creatives or viewers.

- Fine-tune the last encoder blocks using behavioral prediction losses and a lower encoder learning rate.
- Experiment with an auxiliary contrastive objective such as InfoNCE to learn task-specific representations. Define the anchor and positive relationship explicitly; hard negatives can help but are not a prerequisite for InfoNCE.
- Mine difficult negatives from reliable, context-comparable feedback rather than assuming unseen candidates are disliked. One skip is noisy evidence, and a clip liked by another viewer is not automatically a negative.
- Use same-scene cut variants as candidate training examples, but verify preferences or treat them as weak supervision. Synthetic edits and LLM judgments do not establish customer preference.
- Compare contrastive adaptation with direct behavioral fine-tuning. Adopt it only if it improves held-out performance or controlled policy lift.
- Version updated encoders and regenerate embeddings when encoder weights change.

These are future experiments, not implemented capabilities or prerequisites for the six-hour prototype.

## Sources for design choices

- [ModernBERT Embed model card: representations, prefixes, and supported dimensionality](https://huggingface.co/nomic-ai/modernbert-embed-base).
- [Sentence Transformers: task-specific fine-tuning](https://www.sbert.net/docs/sentence_transformer/training_overview.html).
- [Contrastive Predictive Coding / InfoNCE](https://arxiv.org/abs/1807.03748).
- [Estimation considerations in contextual bandits](https://arxiv.org/abs/1711.07077).

These sources support modeling components; they do not validate this proposed architecture on the assignment's data.

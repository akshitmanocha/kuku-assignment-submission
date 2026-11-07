# Promo Lab: Find the Promos

## Problem and assumptions

Problem 1 is a bounded editorial search task: find source-grounded 20–60-second promos that open with a hook, make sense to a newcomer, and leave a consequential question unanswered. It offers supplied inputs and outputs an editor can inspect directly. The tool returns edit decisions, not video. Every episode is processed, but no per-episode recommendation quota is forced.

Timestamps are assumed episode-relative and screenplay-accurate; overlapping camera/action/dialogue entries describe simultaneous tracks. Dialogue boundaries are protected. Assemblies are chronological and limited to three segments. The top 1% applies after temporal deduplication and remains subject to minimum rubric gates. These choices are explicit prototype assumptions.

## Implemented approach

Parsing retains source event IDs, integer timestamps, raw content, file hashes and timing flags. Code enumerates plausible 20–60-second boundaries. The configured LLM proposes candidates from dialogue/action source entries and, separately, critiques one finalist per episode without episode summaries or the generator rationale. AI-generated source IDs, schema values and evidence references are validated rather than trusted. Six equally weighted editorial dimensions explain the rank. Invalid cuts cannot enter the shortlist; the offline rule baseline and unassessed candidates remain inspectable.

The browser workbench accepts pasted screenplay text, TXT files or ZIPs, shows ranked decisions and source timelines, filters episodes, explains scores, reports coverage and exports JSON/CSV artifacts. The CLI runs the same pipeline. A fresh app opens a saved Nemotron run on original fiction. To run a fresh analysis without credentials, choose the offline engine.

## Evidence and quality

Private editorial results are stored under `output/runs/`. The public demo artifacts are in `promo_lab/demo_run/`. The two-page PDF reports aggregate results and an observed AI error from the full-pack run. The private edition also includes an example recommendation with source dialogue. The separate Synthetic demo demonstrates the feedback loop under disclosed response assumptions. See [the simulation guide](SYNTHETIC_DEMO.md).

The technical baseline selects an approximately 30-second interval from each episode's first spoken line without boundary refinement. Report source/duration validity and dialogue cut-through rates with denominators. The filtered shortlist and baseline are different samples; this comparison demonstrates boundary enforcement, not causal improvement in interest. Human acceptance, candidate recall against an independent reference and audience engagement are unmeasured until corresponding evidence is collected.

## Failure modes and scale

Keyword rules can mistake a question for an unresolved ending. AI can mistake missing context for suspense, infer hidden identities from role labels, or propose a poor/invalid boundary. Evidence IDs and hard checks catch structural errors, not all semantic failures. Text-only input cannot judge delivery, acting, frame-accurate timing or visual joins. One critique per episode is an intentional free-tier compromise that may miss better variants. Temporal overlap grouping does not eliminate all semantic duplication.

For more shows, process/cache episodes independently by source hash and prompt/model version. Boundary enumeration is quadratic within an episode; the supplied episodes are small, but a larger system should prune proposals before critique. Model calls and actual token usage are recorded; avoid claiming a cost or quality result not measured. Human editors retain the final cut decision. Hosting and distributed execution are outside the prototype scope.

## Feedback, simulation and future work

A randomized internal reel-feed experiment would collect one row per real exposure. A frozen text encoder and small behavioral heads could predict attention, watch fraction and qualified continuation. Epsilon-greedy would explore eligible alternatives; promotion would depend on forward/grouped evaluation and controlled customer lift. Monitor mature 1/7/14/30-day cohorts. Contrastive learning and encoder adaptation are later experiments, not prototype functionality.

The implemented **Reading experiment** provides the first collection step with text cards: randomized saved-script promos among filler stories, consent, real reading/continuation events, persistent SQLite logs, uncertainty-aware reports and exposure-level exports. It does not claim that reading outcomes are video outcomes or that a trained audience model already exists. See `docs/EXPERIMENT.md` for the measurement contract.

The separate synthetic demonstration trains candidate response estimates from generated outcomes, then evaluates held-out predictions and daily epsilon-greedy selection against a random control. Its assumptions and provenance are explicit. It demonstrates implementation mechanics, not real customer improvement.

Codex assisted implementation, tests and document drafting. OpenRouter Nemotron is configurable, and the saved full-pack evidence uses Groq Qwen; changing the active provider does not relabel older outputs. The generated PDF includes a concrete failure observed in the real run and explains the mitigation. The applicant should inspect recommendations and understand the design. Confidential source text and raw outputs remain local and Git-ignored.

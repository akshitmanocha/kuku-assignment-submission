# Editorial selection and audit contract


1. **Parse:** preserve dialogue, action, camera, and sound intervals with episode-qualified event IDs and integer millisecond timestamps. Normalize field case. Reject malformed or duplicate episodes instead of silently dropping them.
2. **Generate:** enumerate plausible dialogue/action start/end intervals between 20 and 60 seconds. In AI mode, additionally request up to three proposed promos per episode, in strongest-first order. The previous episode's final ten seconds are available for a limited chronological assembly with generic providers. Groq's free-tier path proposes one within-episode candidate and omits that tail to save tokens. No invented timestamps or dialogue are accepted.
3. **Validate:** check episode bounds, source boundary IDs, duration, chronology, overlap, and every dialogue interval crossing a boundary. A camera cut is not necessarily a dialogue-safe boundary. Partial visual entries are retained and flagged.
4. **Assess:** offline mode uses disclosed keyword heuristics. AI mode critiques one valid finalist per episode using only the selected dialogue/actions in playback order, without the proposal rationale or episode summary. The first valid AI proposal gets priority; otherwise a rules-ranked search candidate is assessed. This is a free-tier budget tradeoff, not exhaustive AI ranking of all candidates.
5. **Rank:** six 0–3 dimensions (hook, comprehension, stakes, progression, cliffhanger, cut quality) receive equal weight. The 0–100 total is an editorial estimate, never a probability. Ties prefer fewer segments, then a stable candidate ID; equal scores do not establish a performance difference. Hook, comprehension, and cliffhanger must each score at least two; technically invalid cuts cannot qualify. In AI mode only successfully AI-assessed candidates qualify for its shortlist; remaining rule estimates stay inspectable.
6. **Group:** nonmaximum suppression at temporal intersection-over-union ≥0.5 groups near-duplicate intervals. Select up to `ceil(distinct_valid_candidates × 1%)` qualifying representatives. The cutoff uses distinct valid source intervals, not all timestamp variants. Return fewer if gates fail. The UI can request 5%/10% for exploration.

AI source checks establish that the segments and cited evidence exist. They do not prove that a generated interpretation is semantically correct. Multi-segment visual continuity and standalone comprehension still need editorial review. Lexical/script-descriptor cues can leak hidden character information; the newcomer prompt explicitly cautions against treating a role label as viewer knowledge.

## What each run saves

Under `output/runs/<run-id>/`:

| File | Contents |
| --- | --- |
| `result.json` | Complete result, source event timelines, config, shortlist and audit |
| `raw_candidates.json` | All generated candidates, including failures, rule/AI assessments and provenance |
| `raw_model_calls.json` | Unedited model responses, prompts, usage, retry attempts and cache status; no auth headers |
| `shortlist.csv` | Ordered source segments, hook, ending, rationale, rubric and concerns |
| `episode_coverage.json` | Every processed episode, candidate counts and flags |
| `evaluation.json` | Measured technical checks, baseline, actual rejection examples, limitations |
| `manifest.json` | Config, source hashes and SHA-256 checksums of the above artifacts |

Raw model calls are checkpointed after each call, including failures. Successful requests are cached privately by exact request and provider/model identity. A rerun of identical requests reuses the original responses; UI call counts are logical calls, not necessarily new billable requests. Groq prompts shorten event references with an exported reversible source-ID map; raw responses remain untouched, while validation uses restored original IDs. Cached earlier prompt variants remain identifiable in the journal. Change the prompt/model or remove the private cache to request fresh generations. A failed run does not masquerade as a completed analysis; partial journal/cache data supports retry.

## Evaluation and honest limits

The included baseline chooses an approximately 30-second interval from each episode's first spoken line without boundary refinement. The report compares measured source/duration validity and dialogue cut-through rates. The baseline covers one interval per episode; the shortlist is filtered and selected, so differing validity rates do **not** establish audience or semantic-quality lift.

Human acceptance and audience continuation in editorial analysis reports remain `null` until actually measured. An LLM assessing its own candidate ecosystem is not independent ground truth. The separate Synthetic demo presents generated rewards and curves with explicit provenance and disclosed assumptions; they are never presented as human outcomes.

Known limitations:

- The rules baseline can reward rhetorical questions or danger words even when an answer already appears in the clip. Its comprehension score is a rough heuristic.
- Independent critique is a separate prompt, not an independent model or human. It can still confuse suspense and missing context.
- A first-valid-proposal budget can miss a stronger alternative; temporal grouping also misses semantic duplicates with different source footage.
- Script timestamps are not word alignment or frame-accurate edit points. The UI preserves timing uncertainty and fast-speech flags.
- The candidate text cannot assess acting, actual visuals, delivery, platform eligibility, conversion, or sustained viewing.
- LLM-proposed assemblies are limited to one episode and the previous episode's tail. Arbitrary distant cross-episode montage search is not implemented.

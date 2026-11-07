# Submission guide

The assignment requires a solution PDF of at most two pages, a runnable prototype link (a repository with clear run steps is acceptable), and unedited full-input outputs for Problem 1. An applicant-narrated video of at most three minutes is optional. Submit through the placement form; this tool does not submit or publish on your behalf.

## Prepare the evidence

The local private run `output/runs/full-pack-qwen/` records the complete 50-episode input and its actual Groq Qwen responses. The saved Nemotron run uses the original public demo. Switching the configured default provider does not relabel old outputs.

```bash
python3 scripts/audit_run.py output/runs/full-pack-qwen
```

The audit independently rechecks source intervals, shortlist gates, duplicate overlap, episode coverage, CSV counts and saved artifact hashes. It does not validate semantic quality or measured audience interest.

If creating a new full-pack run, place the supplied archive locally (it is Git-ignored), configure the desired provider and run:

```bash
python3 -m promo_lab run "/path/to/local-screenplays-scripts.zip" \
  --provider groq --output output/runs/my-full-pack-run
```

Keep original saved runs intact for reproducibility. New provider usage may be rate limited; the default failure behavior is explicit and cached calls support later retry. Do not report a partial run as complete.

## Build the documents and archives

```bash
python3 -m pip install -e '.[documents]'
python3 scripts/build_solution_pdf.py --run output/runs/full-pack-qwen
python3 scripts/package_submission.py --run output/runs/full-pack-qwen
```

The generator verifies the two-page limit before replacing the previous PDF. Inspect both rendered pages before submission. Page one explains LLM candidate retrieval, the internal simulated-feed survey, and epsilon-greedy selection with online training. Page two shows the feedback-loop diagram, saved-run evidence, an observed model error, limitations and AI tools used.

The [public PDF](promo-lab-solution.pdf) keeps the aggregate results and omits private script excerpts and clip details. To rebuild that version, add `--public --output docs/promo-lab-solution.pdf` to the PDF command above.

| Deliverable | Intended handling |
| --- | --- |
| `output/pdf/promo-lab-solution.pdf` | Two-page private solution document |
| `output/promo-lab-source.zip` | Source, original fiction, docs and tests; no credentials or collected data |
| `output/submission-private.zip` | Source archive, solution PDF and unedited private editorial outputs |
| `output/SYNTHETIC-feedback-demo.zip`, if generated | Optional supplementary simulator evidence; explicitly synthetic, not real engagement results |

Real participant data is excluded from all standard submission archives. Synthetic responses are also excluded from the standard source/private archives; use a separately labeled supplement if useful. Existing supplemental archives must be regenerated deliberately after changing simulator logic.

## Final review

- Follow the README from a fresh source archive using the original demo and no keys.
- Verify the source archive contains no private scripts, provider cache, environment file or interaction database.
- Confirm raw full-pack outputs include all source episodes and unchanged model responses; retain manifest checksums.
- Inspect recommendations, including the actual failure described in the PDF. Be ready to explain the assumptions and tradeoffs.
- Keep simulated learning results separate from real audience evidence. A text pilot measures reading, not video conversion.
- Record the optional walkthrough in your own voice using [the outline](WALKTHROUGH.md). No applicant recording or human signature is generated here.
- Upload through the authorized assignment channel, fill in applicant details, and check access to the submitted links. The source repository or deployment is not automatically published by this project.

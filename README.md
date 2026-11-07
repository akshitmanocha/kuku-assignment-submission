# Promo Lab

Promo Lab reads a timestamped screenplay and finds short sections that could work as advertisements. For each recommendation, it shows the episode, exact start and end points, opening hook, unresolved ending, and the reason for choosing it.

This is my submission for **Kuku's “Find the Promos” problem**. The goal is to give an editor a useful shortlist and enough evidence to judge each cut. The project also includes a small reading experiment and a separate simulation of learning from audience feedback.

<details>
<summary>See the workbench</summary>

![Promo Lab showing a recommendation, timestamps and source text from the original public demo](docs/images/workbench.png)

The screenshot uses the included fictional example and the offline scorer.

</details>

## Try it locally

You need **Python 3.10+**. The basic demo needs no API key or additional packages.

```bash
git clone https://github.com/akshitmanocha/promo-lab.git
cd promo-lab
python3 -m promo_lab run promo_lab/examples --output output/runs/original-demo
python3 -m promo_lab serve
```

Open **http://127.0.0.1:8765**. The first command analyses the included example; the second starts the app. On Windows, use `py` instead of `python3` if needed.

To analyse your own scripts, choose **New analysis → Upload your screenplay files**, or use the CLI:

```bash
python3 -m promo_lab run path/to/scripts.zip --output output/runs/my-run
```

TXT files, folders and ZIP archives are supported. The [input guide](docs/INPUT_FORMAT.md) explains the format. The app runs on your computer; it is not a hosted website.

## The approach

The project follows three stages: find promising promos, collect feedback, and use that feedback to improve selection. Script analysis and the reading experiment work on real inputs. The learning loop is currently demonstrated with synthetic responses, so it can be inspected without claiming customer results we have not measured.

![Three-part approach: find source promos, collect real reading feedback, and demonstrate improved selection with synthetic responses](docs/images/approach-overview.png)

### 1. Find promising promos in the scripts

The parser reads each episode's dialogue, actions and timestamps while keeping the original source references. Rules search for possible 20–60-second intervals. With an LLM configured, the model also proposes cuts and then assesses a finalist using only the selected dialogue and actions, without the episode summary.

The assessment asks six questions: does the opening grab attention, can a newcomer understand it, are the stakes clear, does the scene progress, does the ending leave a meaningful question, and is the cut usable? Each receives a 0–3 editorial score. These estimates help decide what to test first.

Code checks the things a model should not be trusted to get right by itself: source IDs, timestamps, duration, segment order and whether either cut interrupts dialogue. Overlapping variants are grouped, and the default shortlist targets the top 1% of distinct valid candidates. It can return fewer if the quality checks fail. Editors can inspect the source, scores, reasons and rejected candidates in the app.

### 2. Collect feedback from people

The **Reading experiment** places one randomly chosen promo among six ordinary text stories. Participants can skip, go back or click **Keep reading**. After consent, the app records active reading time, visible text and continuation choices, with one record for each actual promo exposure.

In the exported dataset, **X** describes the promo and the situation before it was shown: its source details, position in the feed and previous exposure count. **Y** records what happened afterward. The main reading target requires a continuation click, at least 15 active seconds reading the continuation and at least 75% of its text units seen.

The same promo can produce different responses from different people; those are separate observations. A promo that was never reached does not become a failed example. Interrupted visits keep unknown outcomes rather than silently turning them into zeroes. This is a text-reading pilot; video engagement needs a later experiment with actual footage. See the [experiment guide](docs/EXPERIMENT.md).

### 3. Learn from feedback and improve selection

The **Synthetic demo** makes this loop runnable before enough real responses exist. It generates a separate, clearly labeled dataset, uses random cold-start examples to fit a small model, and estimates the chance of successful continuation for each promo. The current model uses successes and failures per candidate (a Beta-Bernoulli model); it does not yet learn from script embeddings.

![Synthetic feedback loop: random cold start, success estimates, 80/20 selection after warm-up, daily updates, and a separate random control](docs/images/feedback-loop.png)

After warm-up, 80% of selection opportunities use the candidate with the highest current estimate and 20% choose randomly. Exploration starts higher and falls to 20% by simulated day five. New feedback updates the estimates daily, with less weight given to older observations. A separate random-control group provides the comparison, while held-out responses check prediction quality. Control and validation data never train the model.

The three scenarios cover fixed preferences, equal preferences and changing trends. They show where the loop can help and where it can struggle. The assumed preferences and generated outcomes are disclosed; real customer preferences are not inferred from the simulation. See the [simulation guide](docs/SYNTHETIC_DEMO.md).

A later live system would train on mature real feedback, evaluate an updated model and introduce it through a controlled rollout. Hosting, real-audience model training and automatic model promotion remain future work. The [current architecture](docs/ARCHITECTURE.md) describes what runs today; the [future ML design](ML_ARCHITECTURE.md) covers the embedding-based model and production evaluation.

## Use an LLM

The app supports an OpenAI-compatible endpoint, a separate Groq configuration, or local Ollama. Copy `.env.example` to `.env`, add your model settings and key, then restart the app. For example:

```dotenv
PROMO_API_BASE=https://openrouter.ai/api/v1
PROMO_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
PROMO_API_KEY=your-key-here
```

```bash
python3 -m promo_lab run promo_lab/examples --provider openai \
  --output output/runs/my-ai-demo
```

Here, `openai` refers to the API format, not necessarily the OpenAI service. The model can be swapped without changing the pipeline. The offline demo remains available if a provider is unavailable. See [provider setup](docs/PROVIDERS.md) for input restrictions, caching, partial runs and the other options.

## Results and limitations

The saved full-pack run processed **50 episodes and 3,727 timestamped events**, generated **16,023 candidate cuts**, and returned **six shortlisted promos**. It used Groq Qwen; a separate Nemotron run checked integration on the included public example. The private screenplay pack and raw outputs are not in this repository.

The quality report compares source validity and dialogue truncation with a simple fixed-window baseline. Those checks show that edit boundaries are being enforced; they do not establish that viewers will prefer the shortlist. LLM scores are editorial estimates, and the synthetic learning curves depend on the simulator's assumptions.

Acting, visual continuity and precise footage timing still need an editor's review. Production hosting, real-audience model training and encoder fine-tuning are future work.

## Run the checks

The core tests use only Python:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_repository.py
python3 scripts/run_http_checks.py
```

For formatting and browser checks:

```bash
python3 -m pip install -e '.[dev]'
npm ci
npx playwright install chromium
make check
npm run format:check
PLAYWRIGHT_CHANNEL=chromium python3 scripts/run_http_checks.py --browser
```

All checks run locally. The browser checks use a temporary server and database, so they do not change saved participant data. Details are in [CONTRIBUTING.md](CONTRIBUTING.md) and the [verification record](docs/VALIDATION.md).

## Repository structure

```text
promo-lab/
├── promo_lab/                  Python application package
│   ├── __main__.py             Entry point for python -m promo_lab
│   ├── cli.py                  Commands and environment configuration
│   ├── domain.py               Parse screenplays, timestamps and ZIP inputs
│   ├── pipeline.py             Generate, validate, score and rank candidate cuts
│   ├── providers.py            Swappable model API adapters and response caching
│   ├── experiment_content.py   Build text cards and source continuations
│   ├── experiments.py          Real interaction logging, labels and reports
│   ├── simulations.py          Synthetic responses and the learning demo
│   ├── web/                    HTML, CSS and JavaScript interface
│   └── examples/               Original public screenplay for trying the app
├── tests/                      Parsing, validation, feedback and simulation tests
├── scripts/                    Local checks, audits and submission packaging
├── docs/                       Architecture, setup, measurement and solution notes
├── pyproject.toml              Python package and optional development dependencies
├── package.json                Optional frontend formatting and browser-test tools
├── Makefile                    Shortcuts for running, checking and packaging
└── .env.example                Model configuration template, without credentials
```

**Why `promo_lab`?** It is the importable Python name for **Promo Lab**, the project's name. The underscore lets it be used as a normal Python package, which is why the command is `python -m promo_lab`. The application code lives in that directory.

Generated files stay separate under the Git-ignored `output/` directory:

| Folder | What it contains |
| --- | --- |
| `output/runs/` | Analyses, source references, raw model responses and audit manifests |
| `output/provider_cache/` | Cached model requests and responses |
| `output/experiments/` | Real participant interaction database |
| `output/simulations/` | Labeled synthetic responses, model snapshots and reports |
| `output/pdf/` | Generated solution document |

The `.env` file, supplied Kuku scripts, private outputs and participant responses are excluded from the public repository.

For the assignment materials, see the [solution notes](docs/SOLUTION.md), [submission guide](docs/SUBMISSION.md) and [short walkthrough outline](docs/WALKTHROUGH.md).

Codex assisted with implementation, tests and documentation. Each saved analysis records which inference model was used, along with its original responses and any rejected proposals.

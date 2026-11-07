# Promo Lab

A local tool for finding 20–60-second promos in microdrama screenplays. It was built for Kuku's **Find the Promos** assignment.

## Start here

If you downloaded a submission ZIP, extract it and open a terminal in the folder containing this README. If you are starting from GitHub, clone the repository and enter it.

```bash
git clone https://github.com/akshitmanocha/promo-lab.git
cd promo-lab
```

### With Python

Use Python 3.10 or newer. On Windows, use `py` in place of `python3` if needed. The local app has no required packages to install and runs without an API key.

```bash
python3 -m promo_lab serve
```

Leave the terminal running and open [Promo Lab on this computer](http://127.0.0.1:8765). Press **Ctrl+C** in the terminal to stop it. If port 8765 is already in use, start with `python3 -m promo_lab serve --port 8766` and open [port 8766](http://127.0.0.1:8766).

### With Docker

Start Docker Desktop or Docker Engine, then run these commands from the repository root. The image comes with a sample analysis. The `promo-lab-data` volume keeps your analyses and experiment records between containers.

```bash
docker build -t promo-lab .
docker run --rm --init -p 127.0.0.1:8765:8765 -v promo-lab-data:/app/output promo-lab
```

Open [Promo Lab on this computer](http://127.0.0.1:8765) after the container starts. For optional AI settings, alternate ports and working with the Docker volume, see the [Docker guide](docs/DOCKER.md).

## Walk through the three stages

### 1. Find promo candidates

1. Open **Find promo candidates**. From **Run history**, you can select **Original fiction · saved AI example** to inspect a saved Nemotron critique. Select the cut and check its opening, ending, score and source timestamps.
2. To run a new analysis, open **New analysis**. Select the original demo, paste the contents of one timestamped `.txt` file, or upload TXT or ZIP files. Choose **Offline editorial baseline** to process locally, then select **Analyze screenplays**.
3. Use **Quality report** to compare the selected cuts with a simple 30-second rule. Use **Export run** to download the results. To generate a new LLM critique, configure an authorized model provider first. [Input format](docs/INPUT_FORMAT.md) · [Model setup](docs/PROVIDERS.md)

### 2. Collect reading feedback

1. Open **Collect reading feedback**. Select **Original public demo · 3 variants**, enter a study name and choose **Create study**. Tick **Software test only** if you are trying the feed yourself.
2. Open the **Participant link** on the same computer. Consent, select **Start reading**, and use **Next story** and **Keep reading** to interact with the cards. Select **Finish session** when done.
3. Return to the study and select **Refresh data**. The report shows exposures, reading time and continuation outcomes. Software-test sessions can be inspected through the event export. For an actual consented pilot, create a separate study and use its training export. [Reading experiment guide](docs/EXPERIMENT.md)

### 3. Simulate online learning

1. Open **Simulate online learning**. Leave **Original public demo** and **Different candidate appeal** selected, then click **Generate synthetic responses + train**. The default run uses seed 42 and 14 simulated days.
2. Compare the learning policy with the random control in the chart, then open **Daily updates and randomized comparison**. The model learns one continuation estimate per promo from synthetic responses. Exploration reaches 20% by day five.
3. Try **No signal** or **Changing trends** to see how the policy behaves under different assumptions. Download the synthetic results or model snapshot from the report. [Simulation guide](docs/SYNTHETIC_DEMO.md)

| Start here | What to look for |
| --- | --- |
| **New analysis** | Run the included example, paste screenplay text, or upload TXT or ZIP files. See the [input format](docs/INPUT_FORMAT.md) and [model setup](docs/PROVIDERS.md). |
| **Episode library** and **Quality report** | Check coverage, compare boundary checks with the baseline and inspect rejected cuts. |
| **Run history** | Reopen the saved AI example or one of your own analyses and export the results. |
| **How it works** | Read the three stages as described in the solution PDF. |

## Where to go in the code

| Path | What it contains |
| --- | --- |
| [`promo_lab/`](promo_lab/) | Python application package. `cli.py` starts the tool and `server.py` serves the interface. |
| [`domain.py`](promo_lab/domain.py), [`pipeline.py`](promo_lab/pipeline.py), [`providers.py`](promo_lab/providers.py) | Screenplay parsing, candidate selection and model connections. |
| [`experiments.py`](promo_lab/experiments.py), [`simulations.py`](promo_lab/simulations.py) | Reading experiment records and the separate synthetic learning demo. |
| [`promo_lab/web/`](promo_lab/web/), [`promo_lab/examples/`](promo_lab/examples/) and [`promo_lab/demo_run/`](promo_lab/demo_run/) | Browser interface, original fictional screenplay and its saved AI run. |
| [`tests/`](tests/) and [`scripts/`](scripts/) | Local tests, audits, PDF generation and submission packaging. |
| [`docs/`](docs/) | Approach, architecture diagrams, experiment details and setup guides. |

The [two-page solution PDF](docs/promo-lab-solution.pdf) explains the approach and results. See the [architecture notes](docs/ARCHITECTURE.md) for the diagrams, the [submission guide](docs/SUBMISSION.md) for deliverables, and the [development guide](CONTRIBUTING.md) for local checks.

Python runs save generated files under `output/`. Docker runs use the named volume. Keep `.env`, the supplied Kuku scripts and private results in your local workspace.

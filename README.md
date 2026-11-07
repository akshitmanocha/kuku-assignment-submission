# Promo Lab

A local tool for finding 20–60-second promos in microdrama screenplays. It was built for Kuku's **Find the Promos** assignment.

## Start here

Clone the project and choose Python or Docker. Open **http://127.0.0.1:8765** to follow the three numbered steps in the app. The bundled fictional screenplay and its saved Nemotron analysis let you review a real AI critique without an API key.

```bash
git clone https://github.com/akshitmanocha/promo-lab.git
cd promo-lab
```

### With Python

Use Python 3.10 or newer. On Windows, use `py` in place of `python3` if needed.

```bash
python3 -m promo_lab serve
```

### With Docker

Start Docker Desktop or Docker Engine, then run these commands from the repository root. The image comes with a sample analysis. The `promo-lab-data` volume keeps your analyses and experiment records between containers.

```bash
docker build -t promo-lab .
docker run --rm --init -p 127.0.0.1:8765:8765 -v promo-lab-data:/app/output promo-lab
```

To try your own script, open **New analysis**, choose **Paste screenplay text**, and paste the contents of a timestamped `.txt` file. Choose **Offline editorial baseline** to process it locally. For optional AI settings, alternate ports and working with the Docker volume, see the [Docker guide](docs/DOCKER.md).

## Where to go in the app

1. **Find promo candidates.** Open the saved AI example and inspect the recommended cut, its timestamps, and the source lines behind the critique.
2. **Collect reading feedback.** Create a study with the original public demo. Choose **Software test only** when trying the participant feed yourself, then return to the study report.
3. **Simulate online learning.** Keep the default demo candidates and choose **Generate synthetic responses + train**. Check the daily policy comparison and the learned estimate per promo.

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

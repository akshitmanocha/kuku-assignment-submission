# Promo Lab

A local tool for finding 20–60-second promos in microdrama screenplays. It was built for Kuku's **Find the Promos** assignment.

## Start here

Clone the project and choose either Python or Docker below. Both open the same app at **http://127.0.0.1:8765** and include an original fictional screenplay to try.

```bash
git clone https://github.com/akshitmanocha/promo-lab.git
cd promo-lab
```

### With Python

Use Python 3.10 or newer. The first command creates a sample analysis and the second starts the app. On Windows, use `py` in place of `python3` if needed.

```bash
python3 -m promo_lab run promo_lab/examples --output output/runs/original-demo
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

| Start here | What to look for |
| --- | --- |
| **Discover promos** | Pick a recommendation and inspect its episode, timestamps, hook, ending and source text. |
| **New analysis** | Run the included example, paste screenplay text, or upload TXT or ZIP files. See the [input format](docs/INPUT_FORMAT.md) and [model setup](docs/PROVIDERS.md). |
| **Episode library** and **Quality report** | Check coverage, compare boundary checks with the baseline and inspect rejected cuts. |
| **Run history** | Reopen a previous analysis and export its shortlist or raw outputs. |
| **Reading experiment** | Create a text-card study, open its participant link and export real reading outcomes. See the [experiment guide](docs/EXPERIMENT.md). |
| **Synthetic demo** | Generate labeled synthetic responses and inspect the daily learning and random-control comparison. See the [simulation guide](docs/SYNTHETIC_DEMO.md). |

## Where to go in the code

| Path | What it contains |
| --- | --- |
| [`promo_lab/`](promo_lab/) | Python application package. `cli.py` starts the tool and `server.py` serves the interface. |
| [`domain.py`](promo_lab/domain.py), [`pipeline.py`](promo_lab/pipeline.py), [`providers.py`](promo_lab/providers.py) | Screenplay parsing, candidate selection and model connections. |
| [`experiments.py`](promo_lab/experiments.py), [`simulations.py`](promo_lab/simulations.py) | Reading experiment records and the separate synthetic learning demo. |
| [`promo_lab/web/`](promo_lab/web/) and [`promo_lab/examples/`](promo_lab/examples/) | Browser interface and original public example. |
| [`tests/`](tests/) and [`scripts/`](scripts/) | Local tests, audits, PDF generation and submission packaging. |
| [`docs/`](docs/) | Approach, architecture diagrams, experiment details and setup guides. |

The [two-page solution PDF](docs/promo-lab-solution.pdf) explains the approach and results. See the [architecture notes](docs/ARCHITECTURE.md) for the diagrams, the [submission guide](docs/SUBMISSION.md) for deliverables, and the [development guide](CONTRIBUTING.md) for local checks.

Python runs save generated files under `output/`. Docker runs use the named volume. Keep `.env`, the supplied Kuku scripts and private results in your local workspace.

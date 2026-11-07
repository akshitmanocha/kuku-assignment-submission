# Development

The application has no required third-party Python runtime dependencies and no frontend build step. Use Python 3.10+ from the repository root. Optional document generation, formatting and browser tests install separately.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[dev,documents]'
npm ci
npx playwright install chromium
```

On Windows activate `.venv\Scripts\activate` and use the corresponding shell syntax for environment variables. `make` is a convenience; every target is a short command listed in the Makefile and README.

## Checks and formatting

```bash
make test
make check
npm run format:check
python3 scripts/run_http_checks.py
PLAYWRIGHT_CHANNEL=chromium python3 scripts/run_http_checks.py --browser
```

Use `make format` after editing Python, JavaScript, CSS, HTML or workflow files. Python formatting/linting is pinned to Ruff 0.15.1; optional frontend dependencies are locked in `package-lock.json`. Browser checks use Playwright and the chosen browser channel. The default channel is system Chrome; set `PLAYWRIGHT_CHANNEL=chromium` after installing Playwright's Chromium. `PLAYWRIGHT_MODULE` can point to an already installed Playwright module.

The isolated HTTP/browser wrapper creates its own temporary data directory and port, uses only public fiction, and always terminates its server. It does not load the repository's `.env` or touch the live experiment SQLite database. The individual smoke scripts instead target `PROMO_TEST_URL` (default localhost:8765); use the wrapper when protecting existing data matters. Browser screenshots are generated under ignored `tmp/screenshots/`.

## GitHub Actions

`.github/workflows/checks.yml` runs on pushes, pull requests or a manual dispatch:

- Python 3.10 and 3.13: lint, formatting, unit tests, source hygiene, original-demo audit and isolated HTTP checks.
- Browser job: locked development dependencies, Chromium, frontend formatting and isolated desktop/mobile browser checks.

The workflow uses read-only repository permissions. It requires no API keys, confidential scripts, saved full-pack runs or live participant data. It does not deploy, train a real-audience model, publish artifacts or run a scheduled retraining job. A successful local check does not mean a workflow has already run on GitHub; it starts after the source is pushed there.

## Data and implementation boundaries

Keep `.env`, the Kuku brief/scripts, generated outputs and participant data out of Git. Run `python3 scripts/check_repository.py` before sharing source. Raw provider journals and cached responses contain screenplay text. Use synthetic exports only as clearly labeled simulator artifacts.

Preserve source IDs and original model responses when changing editorial logic. Keep null outcomes distinct from negative outcomes. Avoid reusing evaluation/control observations for model fitting. Changes to measurement thresholds require a new versioned study, not reinterpretation of old labels.

The repository does not specify a license for redistributing confidential assignment material. The original public example is project-authored fiction; it exists to support fresh-checkout testing.

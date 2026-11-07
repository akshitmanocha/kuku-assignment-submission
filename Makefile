PYTHON ?= python3

.PHONY: run demo test check format browser-test pdf package

run:
	$(PYTHON) -m promo_lab serve

demo:
	$(PYTHON) -m promo_lab run promo_lab/examples --output output/runs/original-demo

test:
	$(PYTHON) -m unittest discover -s tests -v

check:
	ruff check promo_lab scripts tests
	ruff format --check promo_lab scripts tests
	$(PYTHON) scripts/check_repository.py
	node --check promo_lab/web/app.js
	node --check promo_lab/web/experiment.js
	node --check promo_lab/web/experiment_admin.js
	node --check promo_lab/web/simulation_admin.js

format:
	ruff check --fix promo_lab scripts tests
	ruff format promo_lab scripts tests
	npm run format

browser-test:
	npm run test:browser

pdf:
	$(PYTHON) scripts/build_solution_pdf.py --run output/runs/full-pack-qwen

package:
	$(PYTHON) scripts/package_submission.py --run output/runs/full-pack-qwen

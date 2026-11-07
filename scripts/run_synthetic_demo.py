"""Run a labeled demo without an API key. Does not alter real experiments."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from promo_lab.experiments import ExperimentStore
from promo_lab.simulations import SimulationStore

if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Generate explicitly synthetic responses and demonstrate daily learning"
    )
    p.add_argument("--study", help="Existing study ID; default is original public demo")
    p.add_argument("--scenario", choices=["stationary", "no_signal", "drift"], default="stationary")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--days", type=int, default=14)
    a = p.parse_args()
    store = SimulationStore(
        ROOT / "output/simulations", ExperimentStore(ROOT / "output/experiments")
    )
    r = store.create(a.study, seed=a.seed, scenario=a.scenario, days=a.days)
    print(
        json.dumps(
            {
                "id": r["id"],
                "is_synthetic": True,
                "disclaimer": r["disclaimer"],
                "summary": r["summary"],
                "output": str(store.directory / r["id"]),
            },
            indent=2,
        )
    )

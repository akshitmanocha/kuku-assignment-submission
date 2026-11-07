"""An explicitly synthetic, seeded demonstration. Never writes experiment records.

Candidate appeal is a simulator assumption, independently assigned to candidate
IDs. It is not inferred from scripts, editorial scores, or real participants.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import math
from pathlib import Path
import random
from uuid import uuid4

from .experiment_content import public_demo_cards
from .experiments import checked_id, encoded, integer, wilson

VERSION = "synthetic-reading-bandit-v1"
DISCLAIMER = "SYNTHETIC DEMO: generated responses under assumed candidate appeal. Demonstrates collection, fitting and policy evaluation; does not establish human preferences, video engagement or real-world model lift. Real experiment records are not modified."


class ResponseModel:
    """Small candidate-level Beta-Bernoulli model, not a content encoder.

    Each candidate begins with Beta(1,1). Posterior means predict qualified
    reading continuation. Daily decay discounts historical excess counts.
    """

    def __init__(self, candidate_ids, decay=0.9):
        self.counts = {cid: [1.0, 1.0] for cid in candidate_ids}
        self.decay = decay

    def predict(self, candidate_id):
        a, b = self.counts[candidate_id]
        return a / (a + b)

    def fit_batch(self, rows, discount=False):
        if discount:
            self.counts = {
                cid: [1 + (a - 1) * self.decay, 1 + (b - 1) * self.decay]
                for cid, (a, b) in self.counts.items()
            }
        for row in rows:
            if row["data_source"] != "synthetic_simulator" or row["metadata"].get("arm") not in {
                "cold_start",
                "epsilon_greedy",
            }:
                raise ValueError("Demo model accepts only synthetic cold-start or policy rows")
            cid = row["metadata"]["candidate_id"]
            y = row["Y"]["qualified_reading_continuation"]
            if type(y) is not int or y not in {0, 1}:
                raise ValueError("Synthetic demo requires observed binary outcomes")
            self.counts[cid][0 if y else 1] += 1

    def best(self):
        scores = {cid: self.predict(cid) for cid in self.counts}
        maximum = max(scores.values())
        return [cid for cid, p in scores.items() if abs(p - maximum) < 1e-12]

    def snapshot(self, version):
        return {
            "model_version": version,
            "kind": "candidate_level_beta_bernoulli",
            "is_synthetic": True,
            "training_eligible_for_real_model": False,
            "daily_decay": self.decay,
            "parameters": {
                cid: {"alpha": a, "beta": b, "prediction": a / (a + b)}
                for cid, (a, b) in self.counts.items()
            },
            "limitations": "Uses candidate identity and synthetic feedback only. No embeddings or semantic learning; new candidates require exploration. Never trained on validation/control or real participant responses.",
        }


def metrics(rows, predictions, baseline):
    ys = [r["Y"]["qualified_reading_continuation"] for r in rows]

    def score(probs):
        return {
            "brier": sum((p - y) ** 2 for p, y in zip(probs, ys)) / len(ys),
            "log_loss": -sum(
                y * math.log(max(p, 1e-9)) + (1 - y) * math.log(max(1 - p, 1e-9))
                for p, y in zip(probs, ys)
            )
            / len(ys),
        }

    return {
        "count": len(rows),
        "split": "independent_synthetic_viewers_same_candidates_before_online_updates",
        "model": score(predictions),
        "constant_cold_start_baseline": score([baseline] * len(rows)),
        "interpretation": "Held-out synthetic prediction error. Lower is better. Does not measure generalization to unseen scripts or real people.",
    }


def rate(rows):
    total = len(rows)
    wins = sum(r["Y"]["qualified_reading_continuation"] for r in rows)
    return {
        "successes": wins,
        "denominator": total,
        "rate": wins / total if total else None,
        "wilson_95": wilson(wins, total),
    }


def simulate(
    cards,
    *,
    seed=42,
    scenario="stationary",
    days=14,
    cold_start=400,
    validation=200,
    per_arm_per_day=150,
):
    integer(seed, "seed", 2**31 - 1)
    for value, name, lo, hi in [
        (days, "days", 2, 30),
        (cold_start, "cold start size", 50, 2000),
        (validation, "validation size", 50, 1000),
        (per_arm_per_day, "daily viewers per arm", 20, 500),
    ]:
        integer(value, name, hi)
        if value < lo:
            raise ValueError(f"{name} must be at least {lo}")
    if scenario not in {"stationary", "no_signal", "drift"}:
        raise ValueError("Unknown synthetic scenario")
    if not 2 <= len(cards) <= 30:
        raise ValueError("The learning demo needs 2–30 candidates; choose another source")
    ids = [c["id"] for c in cards]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate simulator candidate IDs")
    by_id = {c["id"]: c for c in cards}
    rng, environment_rng = random.Random(seed), random.Random(seed + 100003)
    appeal_rng = random.Random(seed + 200003)
    values = [0.04 + 0.22 * i / (len(ids) - 1) for i in range(len(ids))]
    appeal_rng.shuffle(values)
    base = dict(zip(ids, values if scenario != "no_signal" else [0.15] * len(ids)))
    flipped = {cid: 0.30 - p for cid, p in base.items()}

    def probability(cid, day):
        return flipped[cid] if scenario == "drift" and day > days // 2 else base[cid]

    rows, daily, model_history = [], [], []
    model = ResponseModel(ids)

    def response(cid, day, arm, propensity, model_version, branch, epsilon):
        card = by_id[cid]
        q = probability(cid, day)
        # Coupled binary outcomes enforce qualification implies a continuation.
        qualified = environment_rng.random() < q
        click_p = 0.28 + 1.4 * q
        clicked = qualified or environment_rng.random() < (click_p - q) / (1 - q)
        held = clicked or environment_rng.random() < 0.6
        active = (
            environment_rng.randint(3000, 12000) if held else environment_rng.randint(200, 2900)
        )
        n, nf = len(card["units"]), len(card["continuation"])
        seen = environment_rng.randint(1, n)
        follow = (
            environment_rng.randint(15000, 45000)
            if qualified
            else environment_rng.randint(100, 14999)
            if clicked
            else 0
        )
        follow_seen = (
            environment_rng.randint(math.ceil(nf * 0.75), nf)
            if qualified
            else environment_rng.randint(0, nf)
            if clicked
            else 0
        )
        y = {
            "active_dwell_ms": active,
            "text_coverage_fraction": seen / n,
            "held_3s_text": int(active >= 3000),
            "completed_text_proxy": int(seen / n >= 0.9 and active >= 3000),
            "clicked_continue": int(clicked),
            "continuation_active_ms": follow,
            "continuation_coverage_fraction": follow_seen / nf,
            "qualified_reading_continuation": int(qualified),
        }
        index = len(rows)
        row = {
            "schema_version": 1,
            "data_source": "synthetic_simulator",
            "is_synthetic": True,
            "training_eligible_for_real_model": False,
            "modality": "synthetic_text_reading",
            "X": {
                **card["features"],
                "feed_position": rng.choice([2, 3, 4, 5]),
                "prior_exposure_count": 0,
                "simulation_day": day,
                "utc_hour": rng.randrange(24),
            },
            "Y": y,
            "label_status": {key: "synthetic" for key in y},
            "metadata": {
                "exposure_id": f"synthetic-{index + 1:06d}",
                "participant_id": f"synthetic-person-{index + 1:06d}",
                "candidate_id": cid,
                "arm": arm,
                "simulation_day": day,
                "candidate_selection_probability": propensity,
                "position_selection_probability": 0.25,
                "joint_selection_probability": propensity * 0.25,
                "model_version": model_version,
                "epsilon": epsilon,
                "selection_branch": branch,
                "is_synthetic": True,
                "training_eligible_for_real_model": False,
                "label_version": VERSION,
            },
        }
        rows.append(row)
        return row

    cold = [
        response(rng.choice(ids), 0, "cold_start", 1 / len(ids), "prior", "uniform", 1.0)
        for _ in range(cold_start)
    ]
    model.fit_batch(cold)
    model_history.append(model.snapshot("cold_start"))
    holdout = [
        response(rng.choice(ids), 0, "validation", 1 / len(ids), "cold_start", "uniform", 1.0)
        for _ in range(validation)
    ]
    evaluation = metrics(
        holdout,
        [model.predict(r["metadata"]["candidate_id"]) for r in holdout],
        (1 + sum(r["Y"]["qualified_reading_continuation"] for r in cold)) / (2 + len(cold)),
    )
    all_policy, all_control = [], []
    for day in range(1, days + 1):
        epsilon = 0.6 - 0.4 * min(1, (day - 1) / 4)
        best = model.best()
        # This day's model is frozen before traffic. Updates happen only after
        # both arms finish; no current/future responses enter its decisions.
        predictions = {cid: model.predict(cid) for cid in ids}
        model_version = "cold_start" if day == 1 else f"after_day_{day - 1}"
        control, policy = [], []
        arms = ["uniform_control"] * per_arm_per_day + ["epsilon_greedy"] * per_arm_per_day
        rng.shuffle(arms)
        for arm in arms:
            explore = arm == "uniform_control" or rng.random() < epsilon
            cid = rng.choice(ids if explore else best)
            propensity = (
                1 / len(ids)
                if arm == "uniform_control"
                else epsilon / len(ids) + (1 - epsilon) / len(best)
                if cid in best
                else epsilon / len(ids)
            )
            row = response(
                cid,
                day,
                arm,
                propensity,
                model_version,
                "uniform" if arm == "uniform_control" else "explore" if explore else "exploit",
                1.0 if arm == "uniform_control" else epsilon,
            )
            (control if arm == "uniform_control" else policy).append(row)
        all_policy.extend(policy)
        all_control.extend(control)
        expected_policy = sum(
            (epsilon / len(ids) + (1 - epsilon) / len(best) if cid in best else epsilon / len(ids))
            * probability(cid, day)
            for cid in ids
        )
        daily.append(
            {
                "day": day,
                "epsilon": epsilon,
                "model_version": model_version,
                "predictions_before_traffic": predictions,
                "exploited_candidates": best,
                "uniform_control": rate(control),
                "epsilon_greedy": rate(policy),
                "cumulative_control": rate(all_control),
                "cumulative_policy": rate(all_policy),
                "oracle_expected_control": sum(probability(cid, day) for cid in ids) / len(ids),
                "oracle_expected_policy": expected_policy,
            }
        )
        model.fit_batch(policy, discount=True)
        model_history.append(model.snapshot(f"after_day_{day}"))
    pr, cr = rate(all_policy), rate(all_control)
    difference = pr["rate"] - cr["rate"]
    report = {
        "simulator_version": VERSION,
        "is_synthetic": True,
        "training_eligible_for_real_model": False,
        "disclaimer": DISCLAIMER,
        "config": {
            "seed": seed,
            "scenario": scenario,
            "days": days,
            "cold_start": cold_start,
            "validation": validation,
            "per_arm_per_day": per_arm_per_day,
            "initial_epsilon": 0.6,
            "final_epsilon": 0.2,
            "daily_decay": model.decay,
        },
        "summary": {
            "synthetic_responses": len(rows),
            "real_responses_generated": 0,
            "candidate_count": len(ids),
            "uniform_control": cr,
            "epsilon_greedy": pr,
            "absolute_difference": difference,
            "relative_difference": difference / cr["rate"] if cr["rate"] else None,
        },
        "validation": evaluation,
        "daily": daily,
        "models": model_history,
        "candidates": [
            {
                "id": c["id"],
                "title": c["title"],
                "assumed_initial_qualified_probability": base[c["id"]],
                "assumed_final_qualified_probability": probability(c["id"], days),
                "final_prediction": model.predict(c["id"]),
            }
            for c in cards
        ],
        "assumptions": [
            "Candidate appeal is randomly assigned by the simulator, not learned from scripts, rubric scores or real responses.",
            "Every synthetic viewer reaches and completes one assigned exposure; there are no missing outcomes, bots, fatigue or repeated viewers.",
            "Validation viewers are separate and never update the model. Online uniform-control outcomes never update the policy model.",
            "Daily arms have equal viewer counts and share the same response mechanism. The policy is frozen within each day.",
            "The candidate-level response model does not generalize to new content. Encoder training and real-audience validation remain future work.",
            "No seed search or forced improvement is used. No-signal should have zero expected policy advantage; realized rates can differ by chance.",
        ],
        "preview": rows[:6],
    }
    return report, rows


class SimulationStore:
    def __init__(self, directory: Path, experiments):
        self.directory, self.experiments = directory, experiments

    def create(self, study_id=None, **options):
        if study_id:
            with self.experiments.connect() as db:
                study = self.experiments._study(db, study_id)
                cards = [c for c in json.loads(study["cards"]) if c["kind"] == "promo"]
                source = {
                    "study_id": study_id,
                    "name": study["name"],
                    "source_run_id": json.loads(study["config"]).get("source_run_id"),
                }
        else:
            cards, _ = public_demo_cards()
            source = {"study_id": None, "name": "Original public demo", "source_run_id": None}
        allowed = {"seed", "scenario", "days", "cold_start", "validation", "per_arm_per_day"}
        if set(options) - allowed:
            raise ValueError("Unknown simulation options")
        report, rows = simulate(cards, **options)
        sim_id = uuid4().hex[:16]
        report.update(id=sim_id, created_at=datetime.now(timezone.utc).isoformat(), source=source)
        # Store only content features/unit counts, never copy participant data.
        snapshot = [
            {
                "id": c["id"],
                "features": c["features"],
                "unit_count": len(c["units"]),
                "continuation_unit_count": len(c["continuation"]),
            }
            for c in cards
        ]
        report["candidate_snapshot_sha256"] = sha256(encoded(snapshot).encode()).hexdigest()
        folder = self.directory / sim_id
        folder.mkdir(parents=True, exist_ok=False)
        folder.chmod(0o700)
        files = {
            "report.json": encoded(report),
            "synthetic_responses.jsonl": "".join(encoded(row) + "\n" for row in rows),
            "model.json": encoded(report["models"][-1]),
            "candidate_snapshot.json": encoded(snapshot),
        }
        for name, content in files.items():
            p = folder / name
            p.write_text(content, encoding="utf-8")
            p.chmod(0o600)
        return report

    def path(self, sim_id):
        checked_id(sim_id, "simulation ID")
        folder = self.directory / sim_id
        if not (folder / "report.json").is_file():
            raise FileNotFoundError("Simulation not found")
        return folder

    def report(self, sim_id):
        return json.loads((self.path(sim_id) / "report.json").read_text())

    def list(self):
        paths = sorted(
            self.directory.glob("*/report.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:30]
        return [
            {k: r[k] for k in ("id", "created_at", "source", "config", "summary", "is_synthetic")}
            for r in (json.loads(p.read_text()) for p in paths)
        ]

    def export(self, sim_id, artifact):
        folder = self.path(sim_id)
        if artifact == "synthetic_responses.csv":
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(
                [
                    "is_synthetic",
                    "training_eligible_for_real_model",
                    "candidate_id",
                    "arm",
                    "simulation_day",
                    "X_json",
                    "Y_json",
                    "metadata_json",
                ]
            )
            for line in (folder / "synthetic_responses.jsonl").read_text().splitlines():
                r = json.loads(line)
                m = r["metadata"]
                writer.writerow(
                    [
                        True,
                        False,
                        m["candidate_id"],
                        m["arm"],
                        m["simulation_day"],
                        encoded(r["X"]),
                        encoded(r["Y"]),
                        encoded(m),
                    ]
                )
            return out.getvalue().encode(), "text/csv; charset=utf-8"
        if artifact not in {
            "report.json",
            "synthetic_responses.jsonl",
            "model.json",
            "candidate_snapshot.json",
        }:
            raise ValueError("Unknown synthetic export")
        return (folder / artifact).read_bytes(), "application/x-ndjson" if artifact.endswith(
            "jsonl"
        ) else "application/json"

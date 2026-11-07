import json
from pathlib import Path
import tempfile
import unittest

from promo_lab.experiment_content import public_demo_cards
from promo_lab.experiments import ExperimentStore
from promo_lab.simulations import ResponseModel, SimulationStore, simulate


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.cards, _ = public_demo_cards()
        self.options = dict(seed=42, days=6, cold_start=120, validation=80, per_arm_per_day=40)

    def test_seeded_reproducibility_and_explicit_provenance(self):
        report, rows = simulate(self.cards, **self.options)
        self.assertEqual((report, rows), simulate(self.cards, **self.options))
        self.assertEqual(len(rows), 120 + 80 + 6 * 2 * 40)
        self.assertEqual(report["summary"]["real_responses_generated"], 0)
        for row in rows:
            self.assertTrue(row["is_synthetic"])
            self.assertFalse(row["training_eligible_for_real_model"])
            self.assertEqual(row["data_source"], "synthetic_simulator")
            self.assertTrue(all(s == "synthetic" for s in row["label_status"].values()))
            self.assertNotIn("assumed_initial_qualified_probability", row["X"])
            y = row["Y"]
            self.assertLessEqual(y["qualified_reading_continuation"], y["clicked_continue"])
            self.assertEqual(
                y["qualified_reading_continuation"],
                int(
                    bool(y["clicked_continue"])
                    and y["continuation_active_ms"] >= 15000
                    and y["continuation_coverage_fraction"] >= 0.75
                ),
            )

    def test_control_and_validation_never_update_model(self):
        report, rows = simulate(self.cards, **self.options)
        ids = [c["id"] for c in self.cards]
        model = ResponseModel(ids)
        model.fit_batch([r for r in rows if r["metadata"]["arm"] == "cold_start"])
        self.assertEqual(report["models"][0], model.snapshot("cold_start"))
        for day in report["daily"]:
            self.assertEqual(
                day["predictions_before_traffic"], {cid: model.predict(cid) for cid in ids}
            )
            batch = [
                r
                for r in rows
                if r["metadata"]["arm"] == "epsilon_greedy"
                and r["metadata"]["simulation_day"] == day["day"]
            ]
            model.fit_batch(batch, discount=True)
            self.assertEqual(
                report["models"][day["day"]], model.snapshot(f"after_day_{day['day']}")
            )
        for arm in ("validation", "uniform_control"):
            with self.assertRaises(ValueError):
                model.fit_batch([next(r for r in rows if r["metadata"]["arm"] == arm)])

    def test_model_rejects_real_data(self):
        model = ResponseModel([c["id"] for c in self.cards])
        with self.assertRaises(ValueError):
            model.fit_batch(
                [{"data_source": "real_browser_interaction", "metadata": {"arm": "cold_start"}}]
            )

    def test_propensities_and_annealing(self):
        report, rows = simulate(self.cards, **self.options)
        n = len(self.cards)
        self.assertAlmostEqual(report["daily"][0]["epsilon"], 0.6)
        self.assertAlmostEqual(report["daily"][-1]["epsilon"], 0.2)
        for row in rows:
            m = row["metadata"]
            p = m["candidate_selection_probability"]
            self.assertGreater(p, 0)
            self.assertAlmostEqual(m["joint_selection_probability"], p * 0.25)
            if m["arm"] != "epsilon_greedy":
                self.assertEqual(p, 1 / n)
            else:
                day = report["daily"][m["simulation_day"] - 1]
                best = day["exploited_candidates"]
                expected = day["epsilon"] / n
                if m["candidate_id"] in best:
                    expected += (1 - day["epsilon"]) / len(best)
                self.assertAlmostEqual(p, expected)

    def test_no_signal_has_zero_expected_advantage(self):
        report, _ = simulate(self.cards, scenario="no_signal", **self.options)
        for day in report["daily"]:
            self.assertAlmostEqual(day["oracle_expected_control"], day["oracle_expected_policy"])
        self.assertEqual(
            len({c["assumed_initial_qualified_probability"] for c in report["candidates"]}), 1
        )

    def test_drift_changes_assumed_appeal_midway(self):
        report, _ = simulate(self.cards, scenario="drift", **self.options)
        for c in report["candidates"]:
            self.assertAlmostEqual(
                c["assumed_final_qualified_probability"],
                0.30 - c["assumed_initial_qualified_probability"],
            )

    def test_prior_and_discounted_updates(self):
        model = ResponseModel(["a"])
        self.assertEqual(model.predict("a"), 0.5)
        row = {
            "data_source": "synthetic_simulator",
            "metadata": {"arm": "cold_start", "candidate_id": "a"},
            "Y": {"qualified_reading_continuation": 1},
        }
        model.fit_batch([row])
        self.assertAlmostEqual(model.predict("a"), 2 / 3)
        model.fit_batch([], discount=True)
        self.assertEqual(model.counts["a"], [1.9, 1.0])

    def test_options_validation(self):
        for option in (
            {"scenario": "unknown"},
            {"days": 100},
            {"cold_start": 1},
            {"seed": True},
            {"per_arm_per_day": 100000},
        ):
            with self.assertRaises(ValueError):
                simulate(self.cards, **(self.options | option))
        with self.assertRaises(ValueError):
            simulate(self.cards[:1], **self.options)

    def test_persistence_and_real_experiment_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            exp = ExperimentStore(Path(tmp) / "experiments")
            study = exp.create_study("Real study")
            session = exp.start_session(study["id"], "a" * 24, True)
            exp.ingest_events(
                session["id"],
                session["session_token"],
                [{"event_id": "real-event", "seq": 1, "type": "session_finish", "elapsed_ms": 0}],
            )
            before = exp.report(study["id"])
            events = exp.raw_events(study["id"])
            store = SimulationStore(Path(tmp) / "synthetic", exp)
            r = store.create(study["id"], **self.options)
            self.assertEqual(exp.report(study["id"]), before)
            self.assertEqual(exp.raw_events(study["id"]), events)
            self.assertEqual(exp.rows(study["id"]), [])
            self.assertEqual(store.report(r["id"]), r)
            self.assertEqual(store.list()[0]["id"], r["id"])
            content, _ = store.export(r["id"], "synthetic_responses.jsonl")
            self.assertTrue(all(json.loads(line)["is_synthetic"] for line in content.splitlines()))
            csv, _ = store.export(r["id"], "synthetic_responses.csv")
            self.assertTrue(csv.startswith(b"is_synthetic,training_eligible_for_real_model"))
            with self.assertRaises(ValueError):
                store.export(r["id"], "../../.env")
            with self.assertRaises(ValueError):
                store.report("../other")


if __name__ == "__main__":
    unittest.main()

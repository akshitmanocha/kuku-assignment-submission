import csv
import io
import json
from pathlib import Path
import random
import os
import tempfile
import unittest
from uuid import uuid4
from unittest.mock import patch

from promo_lab.experiments import ExperimentStore, wilson
from promo_lab.providers import ProviderConfig
from promo_lab.experiment_content import cards_from_run
from promo_lab.domain import load_path
from promo_lab.pipeline import run_pipeline
from promo_lab.cli import load_env


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock_ms = 1800000000000
        self.store = ExperimentStore(
            Path(self.tmp.name), rng=random.Random(42), clock=lambda: self.clock_ms
        )
        self.study = self.store.create_study()
        self.session = self.store.start_session(self.study["id"], uuid4().hex, True)
        self.seq = 0
        self.time = 0
        self.exposure = uuid4().hex
        self.card_id = self.promo()["id"]

    def promo(self):
        with self.store.connect() as db:
            session = db.execute(
                "SELECT deck FROM sessions WHERE id=?", (self.session["id"],)
            ).fetchone()
            cid = json.loads(session["deck"])["promo_id"]
            study = db.execute(
                "SELECT cards FROM studies WHERE id=?", (self.study["id"],)
            ).fetchone()
            return next(c for c in json.loads(study["cards"]) if c["id"] == cid)

    def event(self, kind, advance=0, **extra):
        self.seq += 1
        self.time += advance
        self.clock_ms += advance
        e = {"event_id": uuid4().hex, "seq": self.seq, "type": kind, "elapsed_ms": self.time}
        if kind != "session_finish":
            e.update(exposure_id=self.exposure, card_id=self.card_id)
        if kind not in {"view_start", "session_finish"}:
            e.update(active_ms=0, seen_units=[], continuation_ms=0, continuation_seen_units=[])
        e.update(extra)
        return e

    def send(self, *events):
        return self.store.ingest_events(
            self.session["id"], self.session["session_token"], list(events)
        )

    def test_empty_study_has_no_outcomes(self):
        r = self.store.report(self.study["id"])
        self.assertEqual(r["summary"]["assigned_not_exposed"], 1)
        self.assertEqual(r["summary"]["events"], 0)
        self.assertEqual(self.store.rows(self.study["id"]), [])
        self.assertIsNone(r["metrics"]["clicked_continue"]["rate"])
        self.assertIsNone(r["metrics"]["clicked_continue"]["wilson_95"])

    def test_one_promo_assignment_and_stable_resume(self):
        key = uuid4().hex
        first = self.store.start_session(self.study["id"], key, True)
        second = self.store.start_session(self.study["id"], key, True)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["cards"], second["cards"])
        self.assertEqual(len(first["cards"]), 7)
        self.assertTrue(all("kind" not in c and "features" not in c for c in first["cards"]))
        with self.assertRaises(PermissionError):
            self.store.session(first["id"], first["session_token"])
        with self.store.connect() as db:
            deck = json.loads(
                db.execute("SELECT deck FROM sessions WHERE id=?", (first["id"],)).fetchone()[0]
            )
        self.assertIn(deck["promo_position"], [2, 3, 4, 5])
        self.assertEqual(deck["cards"].count(deck["promo_id"]), 1)
        self.assertAlmostEqual(deck["joint_probability"], 1 / 12)

    def test_consent_and_authentication(self):
        for consent in (False, None, 1):
            with self.assertRaises(ValueError):
                self.store.start_session(self.study["id"], uuid4().hex, consent)
        with self.assertRaises(PermissionError):
            self.store.ingest_events(self.session["id"], "wrong", [self.event("view_start")])

    def test_terminal_outcomes_and_frozen_x(self):
        self.send(self.event("view_start"))
        self.send(
            self.event(
                "view_end",
                4000,
                active_ms=3600,
                seen_units=[u["id"] for u in self.promo()["units"]],
                reason="skip",
            )
        )
        row = self.store.rows(self.study["id"])[0]
        self.assertEqual(row["Y"]["clicked_continue"], 0)
        self.assertEqual(row["Y"]["held_3s_text"], 1)
        self.assertEqual(row["Y"]["completed_text_proxy"], 1)
        self.assertEqual(row["X"]["prior_exposure_count"], 0)
        self.assertNotIn("active_dwell_ms", row["X"])
        self.assertEqual(row["metadata"]["joint_selection_probability"], 1 / 12)
        exported = json.loads(self.store.export(self.study["id"], "training.jsonl")[0])
        self.assertEqual(exported, row)
        self.assertNotIn(self.session["session_token"], json.dumps(row))

    def test_interrupted_outcomes_are_unknown(self):
        self.send(self.event("view_start"))
        self.send(self.event("view_end", 1000, active_ms=700, reason="unload"))
        row = self.store.rows(self.study["id"])[0]
        self.assertIsNone(row["Y"]["clicked_continue"])
        self.assertIsNone(row["Y"]["held_3s_text"])
        self.assertEqual(row["label_status"]["active_dwell_ms"], "partial")
        self.assertEqual(
            self.store.report(self.study["id"])["metrics"]["clicked_continue"]["unknown"], 1
        )
        self.assertEqual(
            self.store.report(self.study["id"])["metrics"]["clicked_continue"][
                "missing_outcome_bounds"
            ],
            [0, 1],
        )

    def test_observed_positive_survives_interruption(self):
        self.send(self.event("view_start"), self.event("continue_open", 4000, active_ms=3500))
        self.send(
            self.event("view_end", 2000, active_ms=3500, continuation_ms=1500, reason="unload")
        )
        row = self.store.rows(self.study["id"])[0]
        self.assertEqual(row["Y"]["clicked_continue"], 1)
        self.assertEqual(row["Y"]["held_3s_text"], 1)
        self.assertIsNone(row["Y"]["qualified_reading_continuation"])

    def test_qualified_continuation_requires_both_time_and_coverage(self):
        self.send(self.event("view_start"), self.event("continue_open", 1000, active_ms=500))
        self.send(self.event("continuation_progress", 15000, active_ms=500, continuation_ms=15000))
        self.assertIsNone(
            self.store.rows(self.study["id"])[0]["Y"]["qualified_reading_continuation"]
        )
        seen = [u["id"] for u in self.promo()["continuation"]]
        self.send(
            self.event(
                "continuation_close",
                1000,
                active_ms=500,
                continuation_ms=15000,
                continuation_seen_units=seen,
            )
        )
        self.send(
            self.event(
                "view_end",
                active_ms=500,
                continuation_ms=15000,
                continuation_seen_units=seen,
                reason="exit",
            ),
            self.event("session_finish"),
        )
        self.assertEqual(
            self.store.rows(self.study["id"])[0]["Y"]["qualified_reading_continuation"], 1
        )
        self.assertEqual(self.store.report(self.study["id"])["summary"]["completed_sessions"], 1)

    def test_retries_are_idempotent_even_after_completion(self):
        events = [
            self.event("view_start"),
            self.event("view_end", 1000, reason="exit"),
            self.event("session_finish"),
        ]
        first = self.send(*events)
        self.assertEqual(self.send(*events), first)
        self.assertEqual(len(self.store.raw_events(self.study["id"])), 3)
        changed = dict(events[0], reason="scroll")
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.send(changed)

    def test_batch_rolls_back_on_invalid_event(self):
        a = self.event("view_start")
        b = self.event("progress", 1000, seen_units=["invented"])
        with self.assertRaises(ValueError):
            self.send(a, b)
        self.assertEqual(self.store.raw_events(self.study["id"]), [])
        self.assertEqual(self.store.rows(self.study["id"]), [])

    def test_rejects_out_of_order_future_and_unassigned_events(self):
        a = self.event("view_start")
        with self.assertRaisesRegex(ValueError, "Out-of-order"):
            self.send(dict(a, seq=2))
        with self.assertRaisesRegex(ValueError, "clock"):
            self.send(dict(a, elapsed_ms=10000))
        with self.assertRaisesRegex(ValueError, "assigned"):
            self.send(dict(a, card_id="other-card"))
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            self.send(dict(a, email="do-not-collect"))
        self.send(a)

    def test_rejects_time_reversal_and_impossible_reading(self):
        self.send(self.event("view_start"))
        progress = self.event("progress", 4000, active_ms=3000)
        self.send(progress)
        next_event = self.event("progress", 1000, active_ms=1000)
        with self.assertRaisesRegex(ValueError, "decrease"):
            self.send(next_event)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            self.send(dict(next_event, active_ms=20000))
        with self.assertRaisesRegex(ValueError, "opened"):
            self.send(dict(next_event, active_ms=3000, continuation_ms=1000))

    def test_coverage_and_reader_state_validation(self):
        self.send(self.event("view_start"))
        ids = [u["id"] for u in self.promo()["units"]]
        self.send(self.event("progress", 1000, seen_units=ids))
        e = self.event("progress", 1000)
        with self.assertRaisesRegex(ValueError, "decrease"):
            self.send(e)
        with self.assertRaisesRegex(ValueError, "not open"):
            self.send(dict(e, type="continuation_close", seen_units=ids))

    def test_repeat_exposures_remain_separate_rows(self):
        self.send(self.event("view_start"), self.event("view_end", 1000, reason="next"))
        self.exposure = uuid4().hex
        self.send(self.event("view_start"), self.event("view_end", 1000, reason="back"))
        rows = self.store.rows(self.study["id"])
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[1]["metadata"]["is_first_exposure"])
        self.assertEqual(rows[1]["X"]["prior_exposure_count"], 1)
        r = self.store.report(self.study["id"])
        self.assertEqual(r["summary"]["repeat_exposures"], 1)
        self.assertEqual(r["metrics"]["clicked_continue"]["denominator"], 1)

    def test_test_studies_are_excluded_from_training(self):
        study = self.store.create_study("automated", is_test=True)
        self.study = study
        self.session = self.store.start_session(study["id"], uuid4().hex, True)
        self.card_id = self.promo()["id"]
        self.send(self.event("view_start"), self.event("view_end", reason="exit"))
        self.assertEqual(self.store.rows(study["id"]), [])
        self.assertEqual(len(self.store.rows(study["id"], include_test=True)), 1)
        self.assertEqual(self.store.export(study["id"], "training.jsonl")[0], b"")
        self.assertEqual(
            len(
                list(
                    csv.reader(
                        io.StringIO(self.store.export(study["id"], "training.csv")[0].decode())
                    )
                )
            ),
            1,
        )
        self.assertEqual(self.store.report(study["id"])["summary"]["training_rows"], 0)
        self.store.delete_test_study(study["id"])
        with self.assertRaises(FileNotFoundError):
            self.store.study(study["id"])
        with self.assertRaises(ValueError):
            self.store.delete_test_study(self.store.list_studies()[0]["id"])

    def test_withdraw_deletes_events_and_exposures(self):
        self.send(self.event("view_start"))
        self.store.withdraw(self.session["id"], self.session["session_token"])
        self.assertEqual(self.store.raw_events(self.study["id"]), [])
        self.assertEqual(self.store.rows(self.study["id"]), [])
        self.assertEqual(self.store.report(self.study["id"])["summary"]["sessions"], 0)

    def test_closed_study_blocks_new_sessions_but_existing_can_finish(self):
        self.store.close_study(self.study["id"], True)
        with self.assertRaisesRegex(ValueError, "closed"):
            self.store.start_session(self.study["id"], uuid4().hex, True)
        self.send(
            self.event("view_start"),
            self.event("view_end", reason="exit"),
            self.event("session_finish"),
        )
        self.assertEqual(
            self.store.session(self.session["id"], self.session["session_token"])["status"],
            "complete",
        )

    def test_delayed_delivery_keeps_exposure_time(self):
        e = self.event("view_start", 5000)
        self.clock_ms += 400000
        self.send(e)
        row = self.store.rows(self.study["id"])[0]
        self.assertEqual(row["X"]["elapsed_session_ms_before_exposure"], 5000)
        self.assertLess(
            row["metadata"]["exposed_at"], self.store.raw_events(self.study["id"])[0]["received_at"]
        )

    def test_persistence_after_reopening_store(self):
        self.send(self.event("view_start"))
        reopened = ExperimentStore(Path(self.tmp.name), clock=lambda: self.clock_ms)
        self.assertEqual(len(reopened.rows(self.study["id"])), 1)
        self.assertEqual(
            reopened.session(self.session["id"], self.session["session_token"])["last_seq"], 1
        )

    def test_exports_do_not_leak_session_token(self):
        self.send(self.event("view_start"), self.event("view_end", reason="exit"))
        for artifact in ("report.json", "events.jsonl", "training.csv", "training.jsonl"):
            body, _ = self.store.export(self.study["id"], artifact)
            self.assertNotIn(self.session["session_token"], body.decode())
        with self.assertRaises(ValueError):
            self.store.export(self.study["id"], "../interactions.sqlite3")

    def test_wilson_intervals(self):
        self.assertIsNone(wilson(0, 0))
        self.assertEqual(wilson(5, 10), [0.2366, 0.7634])

    def test_confidential_authorization_does_not_mark_inputs_public(self):
        config = ProviderConfig(
            "openai",
            "https://openrouter.ai/api/v1",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "dummy",
            confidential_input_authorized=True,
        )
        self.assertTrue(config.public_inputs_only)
        config.validate_input(False)
        config.confidential_input_authorized = False
        with self.assertRaises(ValueError):
            config.validate_input(False)

    def test_saved_run_stimuli_use_only_source_text(self):
        episodes = load_path(Path(__file__).resolve().parents[1] / "promo_lab/examples")
        result = run_pipeline(episodes)
        # Use source-valid cuts with available tail, independent of editorial gates.
        for c in result["candidates"]:
            c["shortlisted"] = (
                c["validation"]["valid"] and c["segments"][-1]["end_ms"] < episodes[0].duration_ms
            )
        cards = cards_from_run(result, "test-saved-run")
        source = " ".join(e.text for ep in episodes for e in ep.events)
        for c in cards:
            self.assertTrue(c["continuation"])
            self.assertEqual(c["features"]["source_run_id"], "test-saved-run")
            self.assertTrue(c["features"]["continuation_source_event_ids"])
            for unit in c["continuation"]:
                # A speaker prefix may be added for reading; dialogue is never invented.
                self.assertIn(unit["text"].split(": ", 1)[-1], source)
        study = self.store.create_study(
            "Saved-run pilot", promo_cards=cards, source_run_id="test-saved-run"
        )
        self.assertEqual(study["candidate_count"], len(cards))
        self.assertEqual(study["config"]["source_kind"], "saved_analysis_run")
        self.assertEqual(study["sessions"], 0)

    def test_saved_run_without_following_text_is_rejected(self):
        episodes = load_path(Path(__file__).resolve().parents[1] / "promo_lab/examples")
        result = run_pipeline(episodes)
        for c in result["candidates"]:
            c["shortlisted"] = False
        with self.assertRaisesRegex(ValueError, "no shortlisted promos"):
            cards_from_run(result, "empty-run")

    def test_authorization_flag_is_loaded_from_local_env(self):
        directory = Path(self.tmp.name)
        (directory / ".env").write_text("PROMO_ALLOW_CONFIDENTIAL=1\n")
        with patch.dict(os.environ, {}, clear=True):
            load_env(directory)
            self.assertTrue(ProviderConfig.from_env("openai").confidential_input_authorized)


if __name__ == "__main__":
    unittest.main()

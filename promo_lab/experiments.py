"""Persistent real-browser experiments, event validation and exposure-level exports.

No audience responses are generated here. Client-reported visibility is a reading
proxy, not proof of attention, comprehension, video retention, or ad conversion.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import io
import csv
import json
import math
from pathlib import Path
import secrets
import sqlite3
import time
from uuid import uuid4

from .experiment_content import CONTENT_VERSION, public_demo_cards

SCHEMA_VERSION = 1
LABEL_VERSION = "reading-outcomes-v1"
QUALIFIED_MS = 15000
QUALIFIED_COVERAGE = 0.75
MAX_SESSION_MS = 24 * 60 * 60 * 1000
EVENT_TYPES = {
    "view_start",
    "progress",
    "view_end",
    "continue_open",
    "continuation_progress",
    "continuation_close",
    "session_finish",
}
TERMINAL_REASONS = {"next", "back", "skip", "exit", "finished_feed"}


def now_ms() -> int:
    return int(time.time() * 1000)


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()


def encoded(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def checked_id(value, name="identifier") -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 100
        or not all(c.isascii() and (c.isalnum() or c in "-_") for c in value)
    ):
        raise ValueError(f"Invalid {name}")
    return value


def integer(value, name, maximum=MAX_SESSION_MS) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"Invalid {name}")
    return value


def wilson(successes: int, total: int):
    if not total:
        return None
    p, z = successes / total, 1.96
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [round(max(0, center - radius), 4), round(min(1, center + radius), 4)]


class ExperimentStore:
    def __init__(self, directory: Path, rng=None, clock=now_ms):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "interactions.sqlite3"
        self.rng = rng or secrets.SystemRandom()
        self.clock = clock
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS studies (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, created_ms INTEGER NOT NULL,
                closed INTEGER NOT NULL DEFAULT 0, is_test INTEGER NOT NULL,
                config TEXT NOT NULL, cards TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES studies(id),
                participant_id TEXT NOT NULL, token_hash TEXT NOT NULL, created_ms INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active', deck TEXT NOT NULL, last_seq INTEGER NOT NULL DEFAULT 0,
                last_elapsed_ms INTEGER NOT NULL DEFAULT 0,
                UNIQUE(study_id, participant_id));
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                seq INTEGER NOT NULL, received_ms INTEGER NOT NULL, payload TEXT NOT NULL,
                UNIQUE(session_id, seq));
            CREATE TABLE IF NOT EXISTS exposures (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                card_id TEXT NOT NULL, position INTEGER NOT NULL, created_ms INTEGER NOT NULL,
                started_elapsed_ms INTEGER NOT NULL, prior_count INTEGER NOT NULL,
                state TEXT NOT NULL DEFAULT 'open', end_reason TEXT,
                active_ms INTEGER NOT NULL DEFAULT 0, seen TEXT NOT NULL DEFAULT '[]',
                continued INTEGER NOT NULL DEFAULT 0, continuation_ms INTEGER NOT NULL DEFAULT 0,
                continuation_seen TEXT NOT NULL DEFAULT '[]', reader_open INTEGER NOT NULL DEFAULT 0,
                features TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS sessions_by_study ON sessions(study_id);
            CREATE INDEX IF NOT EXISTS exposures_by_session ON exposures(session_id);
            """)
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_study(
        self,
        name: str = "Reading pilot",
        is_test: bool = False,
        promo_cards=None,
        source_run_id=None,
    ) -> dict:
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise ValueError("Study name must contain 1–100 characters")
        if type(is_test) is not bool:
            raise ValueError("is_test must be a boolean")
        promos, fillers = public_demo_cards()
        if promo_cards is not None:
            promos = promo_cards
        if not promos:
            raise ValueError("A study requires eligible promo cards")
        study_id = uuid4().hex[:16]
        config = {
            "schema_version": SCHEMA_VERSION,
            "label_version": LABEL_VERSION,
            "content_version": CONTENT_VERSION,
            "modality": "text_reading",
            "policy": "uniform_cold_start_v1",
            "candidate_ids": [c["id"] for c in promos],
            "filler_count": 6,
            "promo_positions": [2, 3, 4, 5],
            "qualified_active_ms": QUALIFIED_MS,
            "qualified_coverage": QUALIFIED_COVERAGE,
            "notes": "One randomly assigned target per session. All stories offer continuation. Reading proxies only; no video outcomes or simulated responses.",
        }
        config.update(
            source_run_id=source_run_id,
            content_version="saved-run-reading-v1" if source_run_id else CONTENT_VERSION,
            held_active_ms=3000,
            completed_min_active_ms=3000,
            completed_coverage=0.9,
            maximum_session_ms=MAX_SESSION_MS,
            source_kind="saved_analysis_run" if source_run_id else "original_public_demo",
        )
        with self.connect() as db:
            db.execute(
                "INSERT INTO studies(id,name,created_ms,is_test,config,cards) VALUES(?,?,?,?,?,?)",
                (
                    study_id,
                    name.strip(),
                    self.clock(),
                    int(is_test),
                    encoded(config),
                    encoded(promos + fillers),
                ),
            )
        return self.study(study_id)

    def _study(self, db, study_id):
        checked_id(study_id, "study ID")
        row = db.execute("SELECT * FROM studies WHERE id=?", (study_id,)).fetchone()
        if row is None:
            raise FileNotFoundError("Study not found")
        return row

    def study(self, study_id: str, public=False) -> dict:
        with self.connect() as db:
            row = self._study(db, study_id)
            base = {
                "id": row["id"],
                "name": row["name"],
                "closed": bool(row["closed"]),
                "is_test": bool(row["is_test"]),
                "created_at": iso(row["created_ms"]),
            }
            if public:
                return {
                    **base,
                    "card_count": 7,
                    "consent_text": "This pilot records anonymous interactions with fictional text stories: active viewing time, visible text, skips and continuation choices. It does not collect your name, email, IP address or device fingerprint. You can skip, exit, or delete your session. This is reading research, not a video or advertising performance test.",
                }
            return {
                **base,
                "config": json.loads(row["config"]),
                "candidate_count": len(json.loads(row["config"])["candidate_ids"]),
                "sessions": db.execute(
                    "SELECT COUNT(*) FROM sessions WHERE study_id=?", (study_id,)
                ).fetchone()[0],
            }

    def list_studies(self) -> list:
        with self.connect() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM studies ORDER BY created_ms DESC")]
        return [self.study(s) for s in ids]

    def close_study(self, study_id: str, closed: bool) -> dict:
        if type(closed) is not bool:
            raise ValueError("closed must be a boolean")
        with self.connect() as db:
            self._study(db, study_id)
            db.execute("UPDATE studies SET closed=? WHERE id=?", (int(closed), study_id))
        return self.study(study_id)

    def delete_test_study(self, study_id: str):
        with self.connect() as db:
            row = self._study(db, study_id)
            if not row["is_test"]:
                raise ValueError(
                    "Only software-test studies can be removed through this cleanup endpoint"
                )
            db.execute("DELETE FROM sessions WHERE study_id=?", (study_id,))
            db.execute("DELETE FROM studies WHERE id=?", (study_id,))

    def start_session(self, study_id: str, participant_key: str, consent: bool) -> dict:
        checked_id(participant_key, "anonymous participant key")
        if len(participant_key) < 20 or consent is not True:
            raise ValueError("Anonymous participation requires explicit consent")
        participant_id = sha256((study_id + participant_key).encode()).hexdigest()[:24]
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            study = self._study(db, study_id)
            if study["closed"]:
                raise ValueError("This study is closed to new sessions")
            existing = db.execute(
                "SELECT id FROM sessions WHERE study_id=? AND participant_id=?",
                (study_id, participant_id),
            ).fetchone()
            if existing:
                # Possession of the browser-generated anonymous key resumes the same
                # assignment. Rotating its token invalidates older active tabs.
                session_id = existing["id"]
                db.execute(
                    "UPDATE sessions SET token_hash=? WHERE id=?",
                    (sha256(token.encode()).hexdigest(), session_id),
                )
            else:
                config, cards = json.loads(study["config"]), json.loads(study["cards"])
                promos = [c for c in cards if c["kind"] == "promo"]
                fillers = [c for c in cards if c["kind"] == "filler"]
                promo, position = (
                    self.rng.choice(promos),
                    self.rng.choice(config["promo_positions"]),
                )
                selected = self.rng.sample(fillers, config["filler_count"])
                selected.insert(position, promo)
                assignment = {
                    "cards": [c["id"] for c in selected],
                    "promo_id": promo["id"],
                    "promo_position": position,
                    "candidate_probability": 1 / len(promos),
                    "position_probability": 1 / len(config["promo_positions"]),
                    "joint_probability": 1 / (len(promos) * len(config["promo_positions"])),
                    "policy": config["policy"],
                }
                session_id = uuid4().hex
                db.execute(
                    "INSERT INTO sessions(id,study_id,participant_id,token_hash,created_ms,deck) VALUES(?,?,?,?,?,?)",
                    (
                        session_id,
                        study_id,
                        participant_id,
                        sha256(token.encode()).hexdigest(),
                        self.clock(),
                        encoded(assignment),
                    ),
                )
        return self.session(session_id, token) | {"session_token": token}

    def _session(self, db, session_id, token):
        checked_id(session_id, "session ID")
        row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise FileNotFoundError("Session not found")
        if not isinstance(token, str) or not hmac.compare_digest(
            row["token_hash"], sha256(token.encode()).hexdigest()
        ):
            raise PermissionError("Invalid session token")
        return row

    def session(self, session_id, token):
        with self.connect() as db:
            row = self._session(db, session_id, token)
            study = self._study(db, row["study_id"])
            cards = {c["id"]: c for c in json.loads(study["cards"])}
            deck = json.loads(row["deck"])
            visible = [
                {
                    "id": cid,
                    "title": cards[cid]["title"],
                    "genre": cards[cid]["genre"],
                    "units": cards[cid]["units"],
                    "can_continue": True,
                }
                for cid in deck["cards"]
            ]
            prior = [
                dict(e)
                for e in db.execute(
                    "SELECT id,card_id,state,active_ms,seen,continuation_ms,continuation_seen FROM exposures WHERE session_id=? ORDER BY created_ms,rowid",
                    (session_id,),
                )
            ]
            return {
                "id": row["id"],
                "study_id": row["study_id"],
                "status": row["status"],
                "last_seq": row["last_seq"],
                "elapsed_ms": max(row["last_elapsed_ms"], self.clock() - row["created_ms"]),
                "cards": visible,
                "prior_exposures": prior,
                "is_test": bool(study["is_test"]),
            }

    def continuation(self, session_id, token, card_id):
        with self.connect() as db:
            row = self._session(db, session_id, token)
            if card_id not in json.loads(row["deck"])["cards"]:
                raise ValueError("Card was not assigned to this session")
            study = self._study(db, row["study_id"])
            card = next(c for c in json.loads(study["cards"]) if c["id"] == card_id)
            return {"title": card["title"], "units": card["continuation"]}

    def withdraw(self, session_id, token):
        with self.connect() as db:
            self._session(db, session_id, token)
            db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        return {"deleted": True}

    def ingest_events(self, session_id, token, events):
        if not isinstance(events, list) or not 1 <= len(events) <= 50:
            raise ValueError("Send 1–50 events per batch")
        acknowledged = []
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            session = self._session(db, session_id, token)
            study = self._study(db, session["study_id"])
            cards = {c["id"]: c for c in json.loads(study["cards"])}
            assignment = json.loads(session["deck"])
            last_seq, elapsed = session["last_seq"], session["last_elapsed_ms"]
            for raw in events:
                if not isinstance(raw, dict):
                    raise ValueError("Malformed event")
                allowed = {
                    "event_id",
                    "seq",
                    "type",
                    "elapsed_ms",
                    "exposure_id",
                    "card_id",
                    "active_ms",
                    "seen_units",
                    "continuation_ms",
                    "continuation_seen_units",
                    "reason",
                }
                if set(raw) - allowed:
                    raise ValueError(
                        "Unexpected event fields; never send names or free-text responses"
                    )
                event_id = checked_id(raw.get("event_id"), "event ID")
                seq = integer(raw.get("seq"), "event sequence", 4000)
                if seq < 1:
                    raise ValueError("Sequences begin at one")
                payload = encoded(raw)
                duplicate = db.execute(
                    "SELECT payload,session_id FROM events WHERE event_id=?", (event_id,)
                ).fetchone()
                if duplicate:
                    if duplicate["payload"] != payload or duplicate["session_id"] != session_id:
                        raise ValueError("Conflicting duplicate event")
                    acknowledged.append(event_id)
                    continue
                if session["status"] != "active":
                    raise ValueError("Session is already complete")
                if seq != last_seq + 1:
                    raise ValueError(f"Out-of-order event: expected sequence {last_seq + 1}")
                event_elapsed = integer(raw.get("elapsed_ms"), "elapsed time")
                if (
                    event_elapsed < elapsed
                    or event_elapsed > max(0, self.clock() - session["created_ms"]) + 3000
                ):
                    raise ValueError("Event time is inconsistent with the session clock")
                kind = raw.get("type")
                if kind not in EVENT_TYPES:
                    raise ValueError("Unknown event type")
                if "reason" in raw and raw["reason"] not in TERMINAL_REASONS | {
                    "unload",
                    "reload",
                    "interrupted",
                    "heartbeat",
                    "initial",
                    "scroll",
                    "visibility_hidden",
                    "visibility_visible",
                    "window_blur",
                    "window_focus",
                    "reader_open",
                    "reader_close",
                }:
                    raise ValueError("Unknown event reason")
                if kind == "session_finish":
                    if db.execute(
                        "SELECT 1 FROM exposures WHERE session_id=? AND state='open'", (session_id,)
                    ).fetchone():
                        raise ValueError("Close the current exposure before finishing")
                    db.execute("UPDATE sessions SET status='complete' WHERE id=?", (session_id,))
                    session = dict(session) | {"status": "complete"}
                else:
                    exposure_id = checked_id(raw.get("exposure_id"), "exposure ID")
                    card_id = raw.get("card_id")
                    if card_id not in assignment["cards"]:
                        raise ValueError("Card was not assigned to this session")
                    card = cards[card_id]
                    exposure = db.execute(
                        "SELECT * FROM exposures WHERE id=?", (exposure_id,)
                    ).fetchone()
                    if kind == "view_start":
                        if exposure is not None:
                            raise ValueError("Exposure ID already exists")
                        if db.execute(
                            "SELECT 1 FROM exposures WHERE session_id=? AND state='open'",
                            (session_id,),
                        ).fetchone():
                            raise ValueError("Another exposure is still open")
                        prior = db.execute(
                            "SELECT COUNT(*) FROM exposures WHERE session_id=? AND card_id=?",
                            (session_id, card_id),
                        ).fetchone()[0]
                        position = assignment["cards"].index(card_id)
                        preceding = cards[assignment["cards"][position - 1]] if position else None
                        exposed_ms = session["created_ms"] + event_elapsed
                        features = {
                            **card["features"],
                            "feed_position": position,
                            "preceding_card_id": preceding["id"] if preceding else None,
                            "preceding_genre": preceding["genre"] if preceding else None,
                            "preceding_word_count": preceding["features"]["text_word_count"]
                            if preceding
                            else None,
                            "prior_exposure_count": prior,
                            "elapsed_session_ms_before_exposure": event_elapsed,
                            "utc_hour": datetime.fromtimestamp(
                                exposed_ms / 1000, timezone.utc
                            ).hour,
                            "utc_day_of_week": datetime.fromtimestamp(
                                exposed_ms / 1000, timezone.utc
                            ).weekday(),
                        }
                        db.execute(
                            "INSERT INTO exposures(id,session_id,card_id,position,created_ms,started_elapsed_ms,prior_count,features) VALUES(?,?,?,?,?,?,?,?)",
                            (
                                exposure_id,
                                session_id,
                                card_id,
                                position,
                                exposed_ms,
                                event_elapsed,
                                prior,
                                encoded(features),
                            ),
                        )
                    else:
                        if (
                            exposure is None
                            or exposure["session_id"] != session_id
                            or exposure["card_id"] != card_id
                            or exposure["state"] != "open"
                        ):
                            raise ValueError("Event does not belong to an open assigned exposure")
                        active = integer(raw.get("active_ms"), "active reading time", 3600000)
                        follow = integer(
                            raw.get("continuation_ms"), "continuation reading time", 3600000
                        )
                        if active < exposure["active_ms"] or follow < exposure["continuation_ms"]:
                            raise ValueError("Reading time cannot decrease")
                        if active + follow > event_elapsed - exposure["started_elapsed_ms"] + 2000:
                            raise ValueError("Active time exceeds elapsed exposure time")
                        unit_ids = {u["id"] for u in card["units"]}
                        continuation_ids = {u["id"] for u in card["continuation"]}
                        seen, next_seen = raw.get("seen_units"), raw.get("continuation_seen_units")
                        if not isinstance(seen, list) or not all(
                            isinstance(u, str) and u in unit_ids for u in seen
                        ):
                            raise ValueError("Unknown visible text unit")
                        if not isinstance(next_seen, list) or not all(
                            isinstance(u, str) and u in continuation_ids for u in next_seen
                        ):
                            raise ValueError("Unknown continuation text unit")
                        if not set(json.loads(exposure["seen"])).issubset(seen) or not set(
                            json.loads(exposure["continuation_seen"])
                        ).issubset(next_seen):
                            raise ValueError("Text coverage cannot decrease")
                        if (follow or next_seen) and not exposure["continued"]:
                            raise ValueError("Continuation must be opened before its outcomes")
                        if kind == "continue_open" and exposure["reader_open"]:
                            raise ValueError("Continuation is already open")
                        if (
                            kind in {"continuation_progress", "continuation_close"}
                            and not exposure["reader_open"]
                        ):
                            raise ValueError("Continuation is not open")
                        status, reason = "open", None
                        reader_open = exposure["reader_open"]
                        if kind == "continue_open":
                            reader_open = 1
                        if kind == "continuation_close":
                            reader_open = 0
                        if kind == "view_end":
                            reason = raw.get("reason")
                            if reason not in TERMINAL_REASONS | {"unload", "reload", "interrupted"}:
                                raise ValueError("Invalid exposure-end reason")
                            status = "closed" if reason in TERMINAL_REASONS else "interrupted"
                            reader_open = 0
                        db.execute(
                            "UPDATE exposures SET active_ms=?,seen=?,continuation_ms=?,continuation_seen=?,continued=?,reader_open=?,state=?,end_reason=? WHERE id=?",
                            (
                                active,
                                encoded(sorted(set(seen))),
                                follow,
                                encoded(sorted(set(next_seen))),
                                int(exposure["continued"] or kind == "continue_open"),
                                reader_open,
                                status,
                                reason,
                                exposure_id,
                            ),
                        )
                db.execute(
                    "INSERT INTO events(event_id,session_id,seq,received_ms,payload) VALUES(?,?,?,?,?)",
                    (event_id, session_id, seq, self.clock(), payload),
                )
                acknowledged.append(event_id)
                last_seq, elapsed = seq, event_elapsed
            db.execute(
                "UPDATE sessions SET last_seq=?,last_elapsed_ms=? WHERE id=?",
                (last_seq, elapsed, session_id),
            )
        return {"acknowledged": acknowledged, "last_seq": last_seq}

    def rows(self, study_id, include_test=False):
        with self.connect() as db:
            study = self._study(db, study_id)
            if study["is_test"] and not include_test:
                return []
            config = json.loads(study["config"])
            cards = {c["id"]: c for c in json.loads(study["cards"])}
            exposures = db.execute(
                "SELECT e.*,s.participant_id,s.deck,s.created_ms AS session_created_ms FROM exposures e JOIN sessions s ON s.id=e.session_id WHERE s.study_id=? ORDER BY e.created_ms,e.rowid",
                (study_id,),
            ).fetchall()
            result = []
            for e in exposures:
                card = cards[e["card_id"]]
                if card["kind"] != "promo":
                    continue
                observed_end = e["state"] == "closed"
                coverage = len(json.loads(e["seen"])) / len(card["units"])
                next_coverage = len(json.loads(e["continuation_seen"])) / len(card["continuation"])

                def binary(positive):
                    return 1 if positive else 0 if observed_end else None

                labels = {
                    "active_dwell_ms": e["active_ms"],
                    "text_coverage_fraction": round(coverage, 4),
                    "held_3s_text": binary(e["active_ms"] >= 3000),
                    "completed_text_proxy": binary(coverage >= 0.9 and e["active_ms"] >= 3000),
                    "clicked_continue": binary(bool(e["continued"])),
                    "continuation_active_ms": e["continuation_ms"],
                    "continuation_coverage_fraction": round(next_coverage, 4),
                    "qualified_reading_continuation": binary(
                        bool(e["continued"])
                        and e["continuation_ms"] >= config["qualified_active_ms"]
                        and next_coverage >= config["qualified_coverage"]
                    ),
                }
                assignment = json.loads(e["deck"])
                metadata = {
                    "exposure_id": e["id"],
                    "study_id": study_id,
                    "session_id": e["session_id"],
                    "participant_id": e["participant_id"],
                    "candidate_id": e["card_id"],
                    "exposed_at": iso(e["created_ms"]),
                    "status": e["state"],
                    "end_reason": e["end_reason"],
                    "is_first_exposure": e["prior_count"] == 0,
                    "is_test": bool(study["is_test"]),
                    "policy": assignment["policy"],
                    "candidate_selection_probability": assignment["candidate_probability"],
                    "position_selection_probability": assignment["position_probability"],
                    "joint_selection_probability": assignment["joint_probability"],
                    "label_version": config["label_version"],
                    "measurement": "client_reported_foreground_text_reading",
                }
                result.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "data_source": "real_browser_interaction",
                        "modality": "text_reading",
                        "X": json.loads(e["features"]),
                        "Y": labels,
                        "label_status": {
                            k: "unknown"
                            if v is None
                            else "observed"
                            if k
                            not in {
                                "active_dwell_ms",
                                "text_coverage_fraction",
                                "continuation_active_ms",
                                "continuation_coverage_fraction",
                            }
                            or observed_end
                            else "partial"
                            for k, v in labels.items()
                        },
                        "metadata": metadata,
                    }
                )
            return result

    def report(self, study_id):
        study = self.study(study_id)
        rows = self.rows(study_id, include_test=True)
        first = [r for r in rows if r["metadata"]["is_first_exposure"]]
        with self.connect() as db:
            sessions = db.execute(
                "SELECT deck,status FROM sessions WHERE study_id=?", (study_id,)
            ).fetchall()
            assignment_counts = Counter(json.loads(s["deck"])["promo_id"] for s in sessions)
            event_count = db.execute(
                "SELECT COUNT(*) FROM events e JOIN sessions s ON s.id=e.session_id WHERE s.study_id=?",
                (study_id,),
            ).fetchone()[0]
            raw_study = self._study(db, study_id)
            cards = {c["id"]: c for c in json.loads(raw_study["cards"])}

        def rates(data):
            result = {}
            for key in (
                "held_3s_text",
                "completed_text_proxy",
                "clicked_continue",
                "qualified_reading_continuation",
            ):
                observed = [r["Y"][key] for r in data if r["Y"][key] is not None]
                successes = sum(observed)
                unknown = len(data) - len(observed)
                result[key] = {
                    "successes": successes,
                    "denominator": len(observed),
                    "unknown": unknown,
                    "rate": successes / len(observed) if observed else None,
                    "wilson_95": wilson(successes, len(observed)),
                    "all_exposed_denominator": len(data),
                    "missing_outcome_bounds": [
                        successes / len(data),
                        (successes + unknown) / len(data),
                    ]
                    if data
                    else None,
                }
            return result

        candidates = []
        for cid in study["config"]["candidate_ids"]:
            subset = [r for r in first if r["metadata"]["candidate_id"] == cid]
            candidates.append(
                {
                    "id": cid,
                    "title": cards[cid]["title"],
                    "assigned_sessions": assignment_counts[cid],
                    "first_exposures": len(subset),
                    "finalized": sum(r["metadata"]["status"] == "closed" for r in subset),
                    "metrics": rates(subset),
                }
            )
        return {
            "study": study,
            "summary": {
                "sessions": len(sessions),
                "completed_sessions": sum(s["status"] == "complete" for s in sessions),
                "assigned_not_exposed": len(sessions) - len(first),
                "promo_exposures": len(rows),
                "first_promo_exposures": len(first),
                "repeat_exposures": len(rows) - len(first),
                "events": event_count,
                "training_rows": 0 if study["is_test"] else len(rows),
            },
            "metrics": rates(first),
            "candidates": candidates,
            "interpretation": "First promo exposure per anonymous browser participant is used for primary rates. Counts are not verified unique humans. Unknown/censored outcomes are excluded from each outcome's denominator; informative dropouts can bias those rates. All-exposed missing-outcome bounds separately show the range if unknowns fail or succeed. Confidence intervals are descriptive and assume independent participants. This is reading behavior, not video attention, audience conversion, causal model lift or calibrated ad performance. Test studies are excluded from default training exports.",
        }

    def raw_events(self, study_id):
        with self.connect() as db:
            self._study(db, study_id)
            return [
                {
                    "session_id": row["session_id"],
                    "received_at": iso(row["received_ms"]),
                    **json.loads(row["payload"]),
                }
                for row in db.execute(
                    "SELECT e.* FROM events e JOIN sessions s ON s.id=e.session_id WHERE s.study_id=? ORDER BY e.received_ms,e.rowid",
                    (study_id,),
                )
            ]

    def export(self, study_id, artifact):
        if artifact == "report.json":
            return encoded(self.report(study_id)).encode(), "application/json"
        if artifact == "events.jsonl":
            return "".join(
                encoded(e) + "\n" for e in self.raw_events(study_id)
            ).encode(), "application/x-ndjson"
        rows = self.rows(study_id)
        if artifact == "training.jsonl":
            return "".join(encoded(r) + "\n" for r in rows).encode(), "application/x-ndjson"
        if artifact == "training.csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                [
                    "exposure_id",
                    "session_id",
                    "participant_id",
                    "candidate_id",
                    "is_first_exposure",
                    "status",
                    "X_json",
                    "Y_json",
                    "label_status_json",
                    "assignment_metadata_json",
                ]
            )
            for r in rows:
                m = r["metadata"]
                writer.writerow(
                    [
                        m["exposure_id"],
                        m["session_id"],
                        m["participant_id"],
                        m["candidate_id"],
                        m["is_first_exposure"],
                        m["status"],
                        encoded(r["X"]),
                        encoded(r["Y"]),
                        encoded(r["label_status"]),
                        encoded(m),
                    ]
                )
            return buf.getvalue().encode(), "text/csv; charset=utf-8"
        raise ValueError("Unknown experiment export")

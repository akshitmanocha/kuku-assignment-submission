"""Regression tests for source integrity and model-output trust boundaries."""

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from urllib.error import HTTPError

from promo_lab.domain import ingest, parse_script, parse_time, timecode
from promo_lab.pipeline import (
    critique,
    deduplicate,
    export_csv,
    make_candidate,
    metrics,
    parse_proposals,
    run_pipeline,
    save_run,
    score_candidate,
    segment,
    selected_events,
    validate_segments,
)
from promo_lab.providers import JSONProvider, ProviderConfig

EXAMPLE = Path(__file__).resolve().parents[1] / "promo_lab" / "examples" / "episode-001.txt"


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.text = EXAMPLE.read_text()
        self.ep = parse_script(self.text)
        self.eps = {self.ep.id: self.ep}

    def test_millisecond_timestamp_roundtrip(self):
        self.assertEqual(parse_time("01:02.35"), 62350)
        self.assertEqual(timecode(62350), "01:02.35")
        self.assertEqual(parse_time("01:01:02.35"), 3662350)
        self.assertEqual(timecode(62351), "01:02.351")
        self.assertEqual(parse_time(timecode(62351)), 62351)

    def test_invalid_timestamps(self):
        for value in ["x", "00:60", "-1:00", "00:NaN", "00:Infinity", "00:-1", "00:61:00"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_time(value)

    def test_case_insensitive_metadata_and_crlf(self):
        ep = parse_script(self.text.replace("Scene start", "SCENE START").replace("\n", "\r\n"))
        self.assertEqual(ep.duration_ms, 80000)
        self.assertEqual(len(ep.events), 20)

    def test_missing_event_timing_is_not_silently_dropped(self):
        with self.assertRaisesRegex(ValueError, "missing timing"):
            parse_script(self.text.replace("Start: (00:00.00)", "Missing: (00:00.00)", 1))

    def test_nonpositive_event_rejected(self):
        with self.assertRaisesRegex(ValueError, "nonpositive"):
            parse_script(self.text.replace("End: (00:02.80)", "End: (00:00.00)", 1))

    def test_scenes_not_swallowed_by_previous_action(self):
        altered = self.text.replace(
            "**ELI (Defensive):**",
            "SCENE 02\nScene heading: INT. HALL - NIGHT\nScene start: 00:04.00\nScene end: 01:20.00\n\n**ELI (Defensive):**",
        )
        ep = parse_script(altered)
        self.assertFalse(any("SCENE 02" in e.text for e in ep.events))
        self.assertEqual(next(e for e in ep.events if e.label.startswith("ELI")).scene, "02")

    def test_duplicate_episode_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate episode"):
            ingest([("a.txt", self.text.encode()), ("b.txt", self.text.encode())])

    def test_zip_read_without_extracting_traversal_path(self):
        data = BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("../../episode-001.txt", self.text)
        self.assertEqual(ingest([("pack.zip", data.getvalue())])[0].number, 1)

    def test_zip_bomb_uncompressed_limit(self):
        data = BytesIO()
        with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("episode-001.txt", "x" * 2_000_001)
        with self.assertRaisesRegex(ValueError, "size limit"):
            ingest([("pack.zip", data.getvalue())])

    def test_archive_without_scripts(self):
        data = BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("readme.md", "hello")
        with self.assertRaisesRegex(ValueError, "No .txt"):
            ingest([("pack.zip", data.getvalue())])

    def test_duration_uses_union_timeline_not_sum_of_entries(self):
        c = self.candidate(0, 31000)
        self.assertEqual(c["validation"]["duration_ms"], 31000)
        self.assertTrue(c["validation"]["valid"])
        self.assertGreater(
            sum(e["end_ms"] - e["start_ms"] for e in selected_events(self.eps, c["segments"])),
            31000,
        )

    def candidate(self, start, end):
        a = next(e for e in self.ep.events if e.start_ms == start)
        b = next(e for e in self.ep.events if e.end_ms == end)
        return make_candidate(self.eps, [segment(self.ep, a, b)], "test", 20000, 60000)

    def test_camera_endpoint_inside_dialogue_rejected(self):
        c = self.candidate(0, 5000)
        c["segments"][0].update(end_ms=23000, end="00:23.00")
        validation = validate_segments(self.eps, c["segments"], 20000, 60000)
        self.assertIn("Boundary truncates spoken dialogue", validation["errors"])

    def test_unknown_event_id_rejected(self):
        c = self.candidate(0, 31000)
        c["segments"][0]["start_event_id"] = "invented"
        self.assertFalse(validate_segments(self.eps, c["segments"], 20000, 60000)["valid"])

    def test_assembled_duration_and_chronology(self):
        c = self.candidate(0, 31000)
        second = self.candidate(48000, 80000)
        segments = c["segments"] + second["segments"]
        v = validate_segments(self.eps, segments, 20000, 60000)
        self.assertEqual(v["duration_ms"], 63000)
        self.assertFalse(v["valid"])
        self.assertFalse(
            validate_segments(self.eps, list(reversed(segments)), 20000, 90000)["valid"]
        )

    def test_invented_model_source_rejected(self):
        output = {
            "candidates": [
                {
                    "segments": [
                        {
                            "episode_id": "E001",
                            "start_event_id": "not-real",
                            "end_event_id": "E001-0005",
                        }
                    ]
                }
            ]
        }
        accepted, rejected = parse_proposals(output, self.eps, {"E001"}, 20000, 60000)
        self.assertFalse(accepted)
        self.assertIn("invented", rejected[0]["reason"])

    def test_malformed_model_candidate_not_crash(self):
        accepted, rejected = parse_proposals(
            {"candidates": [None, {"segments": []}]}, self.eps, {"E001"}, 20000, 60000
        )
        self.assertEqual(len(rejected), 2)

    def test_single_proposal_without_wrapper_is_narrowly_normalized(self):
        c = self.candidate(0, 31000)
        s = c["segments"][0]
        accepted, rejected = parse_proposals(
            {
                "title": "Test",
                "segments": [
                    {
                        "episode_id": s["episode_id"],
                        "start_event_id": s["start_event_id"],
                        "end_event_id": s["end_event_id"],
                    }
                ],
            },
            self.eps,
            {"E001"},
            20000,
            60000,
        )
        self.assertEqual(len(accepted), 1)
        self.assertTrue(accepted[0]["validation"]["valid"])
        self.assertFalse(rejected)

    def test_unknown_model_episode_rejected(self):
        accepted, rejected = parse_proposals(
            {"candidates": [{"segments": [{"episode_id": "E999"}]}]},
            self.eps,
            {"E001"},
            20000,
            60000,
        )
        self.assertFalse(accepted)
        self.assertEqual(len(rejected), 1)

    def test_near_duplicate_grouping(self):
        c = self.candidate(0, 31000)
        score_candidate(self.eps, c)
        d = deepcopy(c)
        d["id"] = "second"
        self.assertEqual(len(deduplicate([c, d])), 1)

    def test_critique_cannot_cite_outside_clip(self):
        c = self.candidate(0, 31000)
        score_candidate(self.eps, c)
        fake = type(
            "Fake",
            (),
            {
                "complete": lambda _self, *_args: {
                    "assessments": [
                        {
                            "candidate_id": c["id"],
                            "scores": {k: 3 for k in c["assessment"]["scores"]},
                            "evidence_event_ids": ["E001-9999"],
                            "risks": [],
                            "unanswered_question": "Who?",
                        }
                    ]
                }
            },
        )()
        notices = []
        critique(fake, self.eps, [c], notices)
        self.assertEqual(c["assessment"]["method"], "offline_rules")
        self.assertTrue(notices)

    def test_boolean_is_not_rubric_integer(self):
        c = self.candidate(0, 31000)
        score_candidate(self.eps, c)
        fake = type(
            "Fake",
            (),
            {
                "complete": lambda _self, *_args: {
                    "assessments": [
                        {
                            "candidate_id": c["id"],
                            "scores": {k: True for k in c["assessment"]["scores"]},
                            "evidence_event_ids": [c["assessment"]["hook_event_id"]],
                        }
                    ]
                }
            },
        )()
        critique(fake, self.eps, [c], [])
        self.assertEqual(c["assessment"]["method"], "offline_rules")

    def test_ai_end_to_end_only_assessed_candidates_qualify(self):
        first = next(e for e in self.ep.events if e.start_ms == 0)
        end = next(e for e in self.ep.events if e.end_ms == 31000)

        def complete(provider, _system, payload, purpose):
            provider.journal.append(
                {"purpose": purpose, "response": {"usage": {"total_tokens": 10}}}
            )
            if purpose.startswith("propose_"):
                return {
                    "candidates": [
                        {
                            "title": "The hidden transfer",
                            "segments": [
                                {
                                    "episode_id": self.ep.id,
                                    "start_event_id": first.id,
                                    "end_event_id": end.id,
                                }
                            ],
                        }
                    ]
                }
            c = payload["candidates"][0]
            return {
                "assessments": [
                    {
                        "candidate_id": c["candidate_id"],
                        "scores": {
                            k: 3
                            for k in (
                                "hook",
                                "comprehension",
                                "stakes",
                                "progression",
                                "cliffhanger",
                                "cut_quality",
                            )
                        },
                        "unanswered_question": "Where is their mother?",
                        "reason": "Test fixture",
                        "risks": [],
                        "evidence_event_ids": [first.id, end.id],
                    }
                ]
            }

        with patch("promo_lab.providers.JSONProvider.complete", complete):
            result = run_pipeline(
                [self.ep],
                ProviderConfig("openai", "https://example.com/v1", "mock-model", "mock-key"),
            )
        self.assertEqual(result["summary"]["ai_calls"], 2)
        self.assertEqual(result["summary"]["ai_assessed"], 1)
        self.assertTrue(result["shortlist_ids"])
        self.assertTrue(
            all(
                c["assessment"]["method"] == "llm_newcomer_critique"
                for c in result["candidates"]
                if c["eligible"]
            )
        )

    def test_offline_end_to_end_and_exports(self):
        result = run_pipeline([self.ep])
        self.assertGreater(result["summary"]["candidates"], 0)
        self.assertEqual(result["summary"]["ai_calls"], 0)
        self.assertIsNone(result["evaluation"]["audience_continuation"])
        shortlist = [c for c in result["candidates"] if c["shortlisted"]]
        self.assertTrue(all(c["validation"]["valid"] for c in shortlist))
        self.assertEqual(len(shortlist), len(result["shortlist_ids"]))
        with tempfile.TemporaryDirectory() as tmp:
            save_run(result, Path(tmp))
            manifest = json.loads((Path(tmp) / "manifest.json").read_text())
            self.assertEqual(len(manifest["artifacts"]), 6)
            self.assertEqual(
                json.loads((Path(tmp) / "result.json").read_text())["summary"], result["summary"]
            )

    def test_empty_metrics_are_unknown_not_zero_success(self):
        self.assertIsNone(metrics([])["valid_rate"])

    def test_invalid_pipeline_config(self):
        for kwargs in [{"shortlist_percent": 0}, {"minimum_seconds": 19}, {"maximum_seconds": 61}]:
            with self.assertRaises(ValueError):
                run_pipeline([self.ep], **kwargs)

    def test_partial_ai_run_never_shortlists_unassessed_rules(self):
        config = ProviderConfig(
            "openai", "https://example.com/v1", "mock-model", "fake", allow_partial=True
        )

        def fail(*_args, **_kwargs):
            raise HTTPError(
                "https://example.com/v1", 401, "Unauthorized", {}, BytesIO(b"invalid key")
            )

        with patch("promo_lab.providers.urlopen", side_effect=fail) as call:
            result = run_pipeline([self.ep], config)
        self.assertTrue(result["partial"])
        self.assertTrue(result["provider_failures"])
        self.assertEqual(result["summary"]["episodes"], 1)
        self.assertEqual(result["summary"]["ai_assessed"], 0)
        self.assertEqual(call.call_count, 1)
        self.assertFalse(result["shortlist_ids"])
        self.assertFalse(any(c["eligible"] for c in result["candidates"]))

    def test_csv_formula_protection(self):
        result = run_pipeline([self.ep])
        result["candidates"][0]["assessment"]["hook"] = "=1+1"
        value = export_csv(result, shortlist_only=False)
        self.assertIn("'=1+1", value)


class ProviderTests(unittest.TestCase):
    def test_separate_groq_route_uses_its_own_credentials(self):
        with patch.dict(
            "os.environ",
            {
                "PROMO_API_KEY": "router-only",
                "GROQ_API_KEY": "groq-only",
                "GROQ_MODEL": "qwen/qwen3.8-27b",
            },
            clear=True,
        ):
            config = ProviderConfig.from_env("groq")
        self.assertEqual(config.api_key, "groq-only")
        self.assertEqual(config.base_url, "https://api.groq.com/openai/v1")
        self.assertFalse(config.public_inputs_only)

    def test_missing_groq_key_does_not_use_router_key(self):
        with patch.dict("os.environ", {"PROMO_API_KEY": "router-only"}, clear=True):
            config = ProviderConfig.from_env("groq")
        with self.assertRaises(ValueError):
            config.validate()

    def test_nemotron_free_requires_public_input(self):
        config = ProviderConfig(
            "openai",
            "https://openrouter.ai/api/v1",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "fake-key",
        )
        self.assertTrue(config.public_inputs_only)
        with self.assertRaisesRegex(ValueError, "confidential"):
            config.validate_input(False)
        config.validate_input(True)

    def test_nemotron_known_private_source_blocked_even_if_declared_public(self):
        ep = parse_script(EXAMPLE.read_text())
        config = ProviderConfig(
            "openai",
            "https://openrouter.ai/api/v1",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "fake-key",
        )
        with (
            patch("promo_lab.pipeline.Path.exists", return_value=True),
            patch(
                "promo_lab.pipeline.Path.read_text",
                return_value=json.dumps({"source_hashes": {ep.id: ep.source_hash}}),
            ),
            patch("promo_lab.providers.urlopen") as call,
        ):
            with self.assertRaisesRegex(ValueError, "Kuku scripts are confidential"):
                run_pipeline([ep], config, public_input=True)
        call.assert_not_called()

    def test_openrouter_key_required(self):
        with self.assertRaisesRegex(ValueError, "API provider"):
            ProviderConfig("openai", "https://openrouter.ai/api/v1", "model", "").validate()

    def test_nemotron_transport_uses_supported_parameters(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def read(self, _n):
                return json.dumps({"choices": [{"message": {"content": '{"ok":true}'}}]}).encode()

        journal = []
        provider = JSONProvider(
            ProviderConfig(
                "openai",
                "https://openrouter.ai/api/v1",
                "nvidia/nemotron-3-ultra-550b-a55b:free",
                "fake",
            ),
            journal,
        )
        with patch("promo_lab.providers.urlopen", return_value=Response()):
            self.assertEqual(provider.complete("Return JSON", {}, "test"), {"ok": True})
        body = journal[0]["request"]
        self.assertNotIn("response_format", body)
        self.assertEqual(body["max_tokens"], 2048)
        self.assertEqual(body["reasoning"], {"enabled": False})

    def test_disallow_insecure_remote_url(self):
        with self.assertRaises(ValueError):
            ProviderConfig("openai", "http://example.com/v1", "model", "secret").validate()

    def test_no_credentials_in_url(self):
        with self.assertRaises(ValueError):
            ProviderConfig("openai", "https://key@example.com/v1", "model", "secret").validate()

    def test_fake_http_transport_and_cache(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def read(self, _n):
                return json.dumps({"choices": [{"message": {"content": '{"ok":true}'}}]}).encode()

        with tempfile.TemporaryDirectory() as tmp:
            journal = []
            p = JSONProvider(
                ProviderConfig(
                    "openai",
                    "https://example.com/v1",
                    "model",
                    "fake-secret",
                    cache_dir=tmp,
                    journal_path=str(Path(tmp) / "journal.json"),
                ),
                journal,
            )
            with patch("promo_lab.providers.urlopen", return_value=Response()) as call:
                self.assertEqual(p.complete("Return JSON", {}, "test"), {"ok": True})
                self.assertEqual(p.complete("Return JSON", {}, "test"), {"ok": True})
                self.assertEqual(call.call_count, 1)
            self.assertNotIn("fake-secret", json.dumps(journal))
            self.assertTrue(journal[-1]["cached"])

    def test_compact_groq_ids_restore_original_provenance(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def read(self, _n):
                return json.dumps(
                    {"choices": [{"message": {"content": '{"evidence_event_ids":["v1"]}'}}]}
                ).encode()

        with tempfile.TemporaryDirectory() as tmp:
            journal = []
            p = JSONProvider(
                ProviderConfig(
                    "openai",
                    "https://api.groq.com/openai/v1",
                    "qwen/qwen3.8-27b",
                    "fake-secret",
                    cache_dir=tmp,
                ),
                journal,
            )
            with patch("promo_lab.providers.urlopen", return_value=Response()) as call:
                result = p.complete(
                    "Return JSON", {"events": [["E001-0001", "source text"]]}, "test"
                )
                again = p.complete(
                    "Return JSON", {"events": [["E001-0001", "source text"]]}, "test"
                )
            self.assertEqual(result["evidence_event_ids"], ["E001-0001"])
            self.assertEqual(again, result)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(journal[0]["source_id_map"], {"v1": "E001-0001"})
            self.assertIn('"v1"', journal[0]["response"]["choices"][0]["message"]["content"])

    def test_provider_failure_is_journaled_without_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.json"
            p = JSONProvider(
                ProviderConfig(
                    "openai",
                    "https://example.com/v1",
                    "model",
                    "secret-not-to-log",
                    journal_path=str(path),
                ),
                [],
            )
            with patch(
                "promo_lab.providers.urlopen",
                side_effect=HTTPError(
                    "https://example.com/v1/chat/completions", 401, "Unauthorized", {}, None
                ),
            ):
                with self.assertRaisesRegex(ValueError, "HTTP 401"):
                    p.complete("Return JSON", {}, "failed_test")
            raw = path.read_text()
            self.assertNotIn("secret-not-to-log", raw)
            self.assertEqual(json.loads(raw)[0]["attempts"][0]["status"], 401)

    def test_rate_limit_retry_is_bounded(self):
        p = JSONProvider(ProviderConfig("openai", "https://example.com/v1", "model", "fake"), [])

        def fail(*_args, **_kwargs):
            raise HTTPError(
                "https://example.com/v1", 429, "Rate limit", {}, BytesIO(b"temporary rate limit")
            )

        with (
            patch("promo_lab.providers.urlopen", side_effect=fail) as call,
            patch("promo_lab.providers.time.sleep"),
        ):
            with self.assertRaisesRegex(ValueError, "HTTP 429"):
                p.complete("Return JSON", {}, "test_retry")
            self.assertEqual(call.call_count, 6)

    def test_daily_quota_stops_and_redacts_error_body(self):
        p = JSONProvider(
            ProviderConfig("openai", "https://example.com/v1", "model", "never-log-this"), []
        )

        def fail(*_args, **_kwargs):
            raise HTTPError(
                "https://example.com/v1",
                429,
                "Rate limit",
                {},
                BytesIO(b"tokens per day (TPD) exhausted never-log-this"),
            )

        with (
            patch("promo_lab.providers.urlopen", side_effect=fail) as call,
            patch("promo_lab.providers.time.sleep") as sleep,
        ):
            with self.assertRaisesRegex(ValueError, "daily token quota"):
                p.complete("Return JSON", {}, "test_daily_quota")
            self.assertEqual(call.call_count, 1)
            sleep.assert_not_called()
            self.assertNotIn("never-log-this", json.dumps(p.journal))

    def test_openrouter_daily_request_cap_stops_without_long_retries(self):
        p = JSONProvider(
            ProviderConfig("openai", "https://openrouter.ai/api/v1", "model:free", "fake"), []
        )

        def fail(*_args, **_kwargs):
            raise HTTPError(
                "https://openrouter.ai/api/v1",
                429,
                "Rate limit",
                {},
                BytesIO(b'{"error":{"message":"Rate limit exceeded: free-models-per-day"}}'),
            )

        with (
            patch("promo_lab.providers.urlopen", side_effect=fail) as call,
            patch("promo_lab.providers.time.sleep") as sleep,
        ):
            with self.assertRaisesRegex(ValueError, "daily request quota"):
                p.complete("Return JSON", {}, "test_daily_request_quota")
            self.assertEqual(call.call_count, 1)
            sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Deterministic candidate search, provenance checks, optional AI critique and audit."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import csv
import io
import json
import math
from pathlib import Path
import re
import time
from typing import Callable

from .domain import Episode, Event, timecode
from .providers import CRITIQUE_SYSTEM, PROPOSAL_SYSTEM, JSONProvider, ProviderConfig

RUBRIC = ("hook", "comprehension", "stakes", "progression", "cliffhanger", "cut_quality")
INTENSITY = re.compile(
    r"\b(poison\w*|kill\w*|dead|death|die|hang|gallows|execute\w*|arrest\w*|betray\w*|stole|steal\w*|marry|marrying|wife|husband|duke|witch\w*|blood\w*|fire|burn\w*|guards|disowned|imposter|impostor|prison\w*|ring|secret\w*|traitor\w*)\b",
    re.I,
)
VISUAL_HOOK = re.compile(
    r"\b(slap\w*|strik\w*|struck|explosion|burst\w*|grabs?|seizes?|bloody|bleed\w*|collaps\w*|screams?|kneels?|kneeling|noose|searing|branding|whip\w*)\b",
    re.I,
)
THREAT = re.compile(
    r"\b(will hang|shall hang|will die|kill|execution|gallows|arrest|poison|noose|hot iron|poker|door latch|latch turn|door.*open|accept my hand|coming home)\b",
    re.I,
)
CLOSURE = re.compile(
    r"\b(safe now|thank you|peaceful|contented|resolving chord|tender.*embrace|warm.*smile|trust him|i accept|i am holding still)\b",
    re.I,
)


def selected_events(episodes: dict[str, Episode], segments: list[dict]) -> list[dict]:
    result = []
    offset = 0
    for index, segment in enumerate(segments):
        ep = episodes[segment["episode_id"]]
        start, end = segment["start_ms"], segment["end_ms"]
        for event in ep.events:
            if event.start_ms < end and event.end_ms > start:
                item = {
                    "episode_id": ep.id,
                    "segment_index": index,
                    **event.__dict__,
                    "playback_start_ms": offset + max(0, event.start_ms - start),
                    "playback_end_ms": offset + min(end, event.end_ms) - start,
                    "partial": event.start_ms < start or event.end_ms > end,
                }
                result.append(item)
        offset += end - start
    return result


def validate_segments(
    episodes: dict[str, Episode], segments: list[dict], minimum: int, maximum: int
) -> dict:
    errors, warnings = [], []
    duration = 0
    boundaries = []
    if not 1 <= len(segments) <= 3:
        errors.append("A promo needs one to three segments")
    previous = None
    for segment in segments:
        ep = episodes.get(segment.get("episode_id"))
        start, end = segment.get("start_ms"), segment.get("end_ms")
        if ep is None:
            errors.append("Unknown episode")
            continue
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= ep.duration_ms:
            errors.append("Segment is outside its source timeline")
            continue
        duration += end - start
        order = (ep.number, start)
        if previous and (order < previous[0] or (ep.id == previous[1] and start < previous[2])):
            errors.append("Segments overlap or reverse chronology")
        previous = (order, ep.id, end)
        events_by_id = {e.id: e for e in ep.events}
        se, ee = (
            events_by_id.get(segment.get("start_event_id")),
            events_by_id.get(segment.get("end_event_id")),
        )
        if se is None or ee is None or se.start_ms != start or ee.end_ms != end:
            errors.append("Boundary does not match the referenced source event")
        cut_dialogue = [
            e.id
            for e in ep.events
            if e.kind == "dialogue"
            and (e.start_ms < start < e.end_ms or e.start_ms < end < e.end_ms)
        ]
        if cut_dialogue:
            errors.append("Boundary truncates spoken dialogue")
            boundaries.extend(cut_dialogue)
        spoken = [
            e for e in ep.events if e.kind == "dialogue" and e.start_ms >= start and e.end_ms <= end
        ]
        if spoken:
            if spoken[0].text.lstrip('"“ ').startswith(("...", "…")):
                warnings.append("Opening dialogue continues an earlier sentence")
            if spoken[-1].text.rstrip('"” ').endswith(("...", "…")):
                warnings.append("Ending dialogue trails into a later sentence")
            if any(len(e.text.split()) * 60000 / (e.end_ms - e.start_ms) > 240 for e in spoken):
                warnings.append("Fast scripted speech timing requires footage review")
    if not minimum <= duration <= maximum:
        errors.append(f"Duration must be {minimum // 1000}–{maximum // 1000} seconds")
    if len(segments) > 1:
        warnings.append(
            "Assembly needs a visual continuity review; script checks cannot certify the join"
        )
    return {
        "valid": not errors,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "duration_ms": duration,
        "cut_dialogue_ids": boundaries,
        "checks": {
            "duration": minimum <= duration <= maximum,
            "source_boundaries": not any(
                "source" in x or "Unknown" in x or "outside" in x for x in errors
            ),
            "complete_dialogue": not boundaries,
            "chronology": not any("chronology" in x for x in errors),
        },
    }


def segment(ep: Episode, start: Event, end: Event) -> dict:
    return {
        "episode_id": ep.id,
        "episode_number": ep.number,
        "start_ms": start.start_ms,
        "end_ms": end.end_ms,
        "start": timecode(start.start_ms),
        "end": timecode(end.end_ms),
        "start_event_id": start.id,
        "end_event_id": end.id,
    }


def make_candidate(
    episodes: dict[str, Episode],
    segments: list[dict],
    origin: str,
    minimum: int,
    maximum: int,
    hints: dict | None = None,
) -> dict:
    digest = sha256(
        json.dumps([(s["episode_id"], s["start_ms"], s["end_ms"]) for s in segments]).encode()
    ).hexdigest()[:12]
    candidate = {
        "id": f"P-{digest}",
        "origin": origin,
        "segments": segments,
        "validation": validate_segments(episodes, segments, minimum, maximum),
        "proposal": hints or {},
    }
    candidate["duration_seconds"] = candidate["validation"]["duration_ms"] / 1000
    return candidate


def baseline_features(episodes: dict[str, Episode], candidate: dict) -> dict:
    events = selected_events(episodes, candidate["segments"])
    duration = candidate["validation"]["duration_ms"]
    dialogue = [e for e in events if e["kind"] == "dialogue"]
    narrative = [e for e in events if e["kind"] in {"dialogue", "action"}]
    opening = [e for e in narrative if e["playback_start_ms"] < 3000]
    # Only completed dialogue is credited to an opening. Word-level timing is unavailable.
    opening_complete = [
        e for e in opening if e["kind"] != "dialogue" or e["playback_end_ms"] <= 3000
    ]
    tail = [e for e in narrative if e["playback_end_ms"] > duration - 8000]
    opening_text = " ".join(e["text"] for e in opening_complete)
    tail_text = " ".join(e["text"] for e in tail)
    all_text = " ".join(e["text"] for e in narrative)
    speakers = sorted({e["label"].split("(")[0].strip() for e in dialogue})
    hook_event = max(
        opening,
        key=lambda e: (
            bool(VISUAL_HOOK.search(e["text"])),
            len(INTENSITY.findall(e["text"])),
            e["kind"] == "dialogue",
        ),
        default=events[0] if events else None,
    )
    end_event = (
        dialogue[-1]
        if dialogue
        else (narrative[-1] if narrative else events[-1] if events else None)
    )
    hook = min(
        3,
        int(bool(opening_complete))
        + int(bool(INTENSITY.search(opening_text)))
        + int(bool(VISUAL_HOOK.search(opening_text) or "?" in opening_text)),
    )
    question = bool("?" in tail_text)
    threat = bool(THREAT.search(tail_text))
    closure = bool(CLOSURE.search(tail_text))
    cliff = max(0, min(3, int(question) * 2 + int(threat) * 2) - int(closure) * 2)
    stakes = min(
        3,
        len(set(x.lower() for x in INTENSITY.findall(all_text))) // 2
        + int(bool(THREAT.search(all_text))),
    )
    comprehension = 2 if 1 <= len(speakers) <= 3 and len(dialogue) >= 3 else 1
    if candidate["validation"]["warnings"] and any(
        "continues an earlier" in w for w in candidate["validation"]["warnings"]
    ):
        comprehension = 1
    distinct = len({e["text"] for e in dialogue})
    progression = 2 if distinct >= 4 else 1
    cut_quality = (
        0
        if not candidate["validation"]["valid"]
        else (2 if candidate["validation"]["warnings"] else 3)
    )
    scores = dict(zip(RUBRIC, [hook, comprehension, stakes, progression, cliff, cut_quality]))
    # These flags indicate possible failure, not an asserted resolution or viewer response.
    risks = [
        "Keyword rules cannot establish standalone comprehension or audience interest",
        "Script timing and visual performance require footage review",
    ]
    if question:
        risks.append(
            "A question near the end may already be answered; inspect the selected exchange"
        )
    if closure:
        risks.append("Possible resolution language near the endpoint")
    if any(
        e["kind"] == "dialogue" and e["playback_start_ms"] < 3000 < e["playback_end_ms"]
        for e in events
    ):
        risks.append("Opening dialogue crosses three seconds; exact word timing is unknown")
    return {
        "scores": scores,
        "hook_event_id": hook_event["id"] if hook_event else None,
        "end_event_id": end_event["id"] if end_event else None,
        "hook": hook_event["text"] if hook_event else "No source evidence",
        "cliffhanger": end_event["text"] if end_event else "No source evidence",
        "unanswered_question": "Editorial review required: confirm a consequential question remains unanswered",
        "why": "Opening and ending contain potential narrative signals; score is a transparent rules estimate, not a viewer probability.",
        "risks": risks + candidate["validation"]["warnings"],
        "evidence_event_ids": [e["id"] for e in (hook_event, end_event) if e],
        "method": "offline_rules",
        "speaker_count": len(speakers),
    }


def score_candidate(episodes: dict[str, Episode], candidate: dict) -> None:
    candidate["assessment"] = baseline_features(episodes, candidate)
    update_score(candidate)


def update_score(candidate: dict) -> None:
    assessment = candidate["assessment"]
    candidate["score"] = round(sum(assessment["scores"].values()) / 18 * 100, 1)
    candidate["eligible"] = (
        candidate["validation"]["valid"]
        and assessment["scores"]["hook"] >= 2
        and assessment["scores"]["comprehension"] >= 2
        and assessment["scores"]["cliffhanger"] >= 2
    )
    candidate["status"] = (
        "review"
        if candidate["eligible"]
        else "below_threshold"
        if candidate["validation"]["valid"]
        else "invalid"
    )


def generate(episodes: dict[str, Episode], ep: Episode, minimum: int, maximum: int) -> list[dict]:
    """Enumerate meaningful start/end pairs, preserving safe dialogue boundaries."""
    starts = [e for e in ep.events if e.kind in {"dialogue", "action"}]
    ends = [e for e in ep.events if e.kind in {"dialogue", "action"}]
    candidates, seen = [], set()
    for start in starts:
        for end in ends:
            delta = end.end_ms - start.start_ms
            if not minimum <= delta <= maximum:
                continue
            key = (start.start_ms, end.end_ms)
            if key in seen:
                continue
            seen.add(key)
            c = make_candidate(
                episodes, [segment(ep, start, end)], "boundary_search", minimum, maximum
            )
            score_candidate(episodes, c)
            candidates.append(c)
            if len(candidates) > 5000:
                raise ValueError(
                    f"{ep.title}: more than 5,000 candidate intervals; split this dense screenplay or narrow the CLI duration range"
                )
    return candidates


def overlap(a: dict, b: dict) -> float:
    intersection = 0
    for x in a["segments"]:
        for y in b["segments"]:
            if x["episode_id"] == y["episode_id"]:
                intersection += max(
                    0, min(x["end_ms"], y["end_ms"]) - max(x["start_ms"], y["start_ms"])
                )
    union = a["validation"]["duration_ms"] + b["validation"]["duration_ms"] - intersection
    return intersection / union if union else 0


def deduplicate(candidates: list[dict], threshold: float = 0.5) -> list[dict]:
    distinct = []
    for c in sorted(candidates, key=lambda c: (-c["score"], len(c["segments"]), c["id"])):
        duplicate = next((other for other in distinct if overlap(c, other) >= threshold), None)
        c["duplicate_of"] = duplicate["id"] if duplicate else None
        if not duplicate:
            distinct.append(c)
    return distinct


def parse_proposals(
    provider_result: dict,
    episodes: dict[str, Episode],
    allowed_ids: set[str],
    minimum: int,
    maximum: int,
) -> tuple[list[dict], list[dict]]:
    proposals = provider_result.get("candidates")
    if "candidates" not in provider_result and isinstance(provider_result.get("segments"), list):
        proposals = [provider_result]
    if not isinstance(proposals, list):
        raise ValueError("AI proposal response is missing its candidates array")
    accepted, rejected = [], []
    for proposal in proposals[:10]:
        try:
            if not isinstance(proposal, dict) or not isinstance(proposal.get("segments"), list):
                raise ValueError("Malformed candidate")
            if not 1 <= len(proposal["segments"]) <= 3:
                raise ValueError("Expected one to three source segments")
            segments = []
            for item in proposal["segments"]:
                if not isinstance(item, dict) or item.get("episode_id") not in allowed_ids:
                    raise ValueError("Episode is outside the provided source scope")
                ep = episodes[item["episode_id"]]
                by_id = {e.id: e for e in ep.events}
                start, end = (
                    by_id.get(item.get("start_event_id")),
                    by_id.get(item.get("end_event_id")),
                )
                if start is None or end is None:
                    raise ValueError("Model invented a source event ID")
                segments.append(segment(ep, start, end))
            c = make_candidate(
                episodes,
                segments,
                "llm_proposal",
                minimum,
                maximum,
                {
                    key: str(proposal.get(key, ""))[:1200]
                    for key in ("title", "hook", "cliffhanger", "why")
                },
            )
            score_candidate(episodes, c)
            accepted.append(c)
        except (ValueError, KeyError, TypeError) as exc:
            rejected.append({"proposal": proposal, "reason": str(exc)})
    return accepted, rejected


def critique(
    provider: JSONProvider, episodes: dict[str, Episode], candidates: list[dict], notices: list[str]
) -> None:
    payload = {
        "event_columns": [
            "id",
            "type",
            "speaker",
            "playback_start_seconds",
            "playback_end_seconds",
            "partial",
            "text",
        ],
        "candidates": [
            {
                "candidate_id": c["id"],
                "duration_seconds": c["duration_seconds"],
                "events": [
                    [
                        e["id"],
                        e["kind"],
                        e["label"].split("(")[0].strip(),
                        e["playback_start_ms"] / 1000,
                        e["playback_end_ms"] / 1000,
                        e["partial"],
                        e["text"],
                    ]
                    for e in selected_events(episodes, c["segments"])
                    if e["kind"] in {"dialogue", "action"}
                ],
            }
            for c in candidates
        ],
    }
    result = provider.complete(CRITIQUE_SYSTEM, payload, "newcomer_critique")
    items = result.get("assessments")
    if (
        "assessments" not in result
        and isinstance(result.get("scores"), dict)
        and isinstance(result.get("candidate_id"), str)
    ):
        items = [result]
        notices.append(
            "Normalized an AI single-assessment object missing its assessments wrapper; original response retained"
        )
    if not isinstance(items, list):
        raise ValueError("AI critique response is missing its assessments array")
    by_id = {c["id"]: c for c in candidates}
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            notices.append("Ignored malformed AI assessment")
            continue
        c = by_id.get(item.get("candidate_id"))
        if c is None or c["id"] in seen:
            notices.append("Ignored unknown or repeated AI assessment ID")
            continue
        scores = item.get("scores", {})
        available = {e["id"] for e in selected_events(episodes, c["segments"])}
        evidence = item.get("evidence_event_ids", [])
        risks = item.get("risks", [])
        question = item.get("unanswered_question", "")
        if not isinstance(scores, dict) or not all(
            type(scores.get(k)) is int and 0 <= scores[k] <= 3 for k in RUBRIC
        ):
            notices.append(f"Invalid rubric scores for {c['id']}; retained rules assessment")
            continue
        if (
            not isinstance(evidence, list)
            or not evidence
            or not all(isinstance(e, str) and e in available for e in evidence)
        ):
            notices.append(
                f"Unsupported critique evidence for {c['id']}; retained rules assessment"
            )
            continue
        if (
            not isinstance(risks, list)
            or not all(isinstance(r, str) for r in risks)
            or not isinstance(question, str)
        ):
            notices.append(f"Malformed critique fields for {c['id']}; retained rules assessment")
            continue
        seen.add(c["id"])
        c["rules_assessment"] = c["assessment"]
        c["assessment"] = {
            **c["assessment"],
            "scores": {k: scores[k] for k in RUBRIC},
            "unanswered_question": question[:1000],
            "why": str(item.get("reason", ""))[:1800],
            "risks": risks[:15] + c["validation"]["warnings"],
            "evidence_event_ids": evidence[:20],
            "method": "llm_newcomer_critique",
        }
        if scores["hook"] >= 2 and c["rules_assessment"]["scores"]["hook"] < 2:
            c["assessment"]["risks"].append(
                "AI and opening-cue rules disagree; inspect what is actually communicated in the first three seconds"
            )
        update_score(c)
    if len(seen) < len(candidates):
        notices.append(
            f"AI returned valid critiques for {len(seen)}/{len(candidates)} candidates; other assessments remain explicitly labeled rules estimates"
        )


def fixed_baseline(episodes: dict[str, Episode], minimum: int, maximum: int) -> list[dict]:
    """Fixed duration from a first dialogue: intentionally no boundary refinement."""
    result = []
    for ep in episodes.values():
        first = next((e for e in ep.events if e.kind == "dialogue"), ep.events[0])
        target = min(ep.duration_ms, first.start_ms + min(maximum, max(minimum, 30000)))
        end = min(ep.events, key=lambda e: abs(e.end_ms - target))
        c = make_candidate(
            episodes, [segment(ep, first, end)], "fixed_window_baseline", minimum, maximum
        )
        score_candidate(episodes, c)
        result.append(c)
    return result


def metrics(candidates: list[dict]) -> dict:
    n = len(candidates)
    return {
        "count": n,
        "valid_count": sum(c["validation"]["valid"] for c in candidates),
        "valid_rate": round(sum(c["validation"]["valid"] for c in candidates) / n, 4)
        if n
        else None,
        "dialogue_cut_count": sum(bool(c["validation"]["cut_dialogue_ids"]) for c in candidates),
        "dialogue_cut_rate": round(
            sum(bool(c["validation"]["cut_dialogue_ids"]) for c in candidates) / n, 4
        )
        if n
        else None,
        "mean_editorial_score": round(sum(c["score"] for c in candidates) / n, 1) if n else None,
    }


def run_pipeline(
    episode_list: list[Episode],
    provider_config: ProviderConfig | None = None,
    shortlist_percent: float = 1,
    minimum_seconds: int = 20,
    maximum_seconds: int = 60,
    progress: Callable | None = None,
    public_input: bool = False,
) -> dict:
    if not 20 <= minimum_seconds <= maximum_seconds <= 60:
        raise ValueError("Duration range must stay within 20–60 seconds")
    if not 0 < shortlist_percent <= 100:
        raise ValueError("Shortlist percentage must be in (0, 100]")
    if not episode_list:
        raise ValueError("At least one episode is required")
    config = provider_config or ProviderConfig()
    config.validate()
    config.validate_input(public_input)
    if config.public_inputs_only and not config.confidential_input_authorized:
        known = Path(__file__).resolve().parent.parent / "output/runs/full-pack-qwen/manifest.json"
        if known.exists():
            private_hashes = set(json.loads(known.read_text()).get("source_hashes", {}).values())
            if any(ep.source_hash in private_hashes for ep in episode_list):
                raise ValueError(
                    "The supplied Kuku scripts are confidential and cannot be sent to this public-input-only NVIDIA endpoint"
                )
    episodes = {ep.id: ep for ep in episode_list}
    if len(episodes) != len(episode_list):
        raise ValueError("Duplicate episode IDs")
    started = time.monotonic()
    minimum, maximum = minimum_seconds * 1000, maximum_seconds * 1000
    candidates, journal, rejected, notices, coverage = [], [], [], [], []
    provider = JSONProvider(config, journal) if config.mode != "offline" else None
    for i, ep in enumerate(episode_list):
        if progress:
            progress(i, len(episode_list), f"Searching {ep.title}")
        local = generate(episodes, ep, minimum, maximum)
        if provider:

            def compact(e):
                return [
                    e.id,
                    timecode(e.start_ms),
                    timecode(e.end_ms),
                    e.kind,
                    e.label.split("(")[0].strip(),
                    e.text,
                ]

            source = {
                "event_columns": ["id", "start", "end", "type", "speaker", "text"],
                "duration_range_seconds": [minimum_seconds, maximum_seconds],
                "episode_id": ep.id,
                "events": [compact(e) for e in ep.events if e.kind in {"dialogue", "action"}],
            }
            if i > 0:
                previous = episode_list[i - 1]
                source["previous_episode_tail"] = {
                    "episode_id": previous.id,
                    "events": [
                        compact(e)
                        for e in previous.events
                        if e.end_ms >= previous.duration_ms - 10000
                        and e.kind in {"dialogue", "action"}
                    ],
                }
            response = provider.complete(PROPOSAL_SYSTEM, source, f"propose_{ep.id}")
            if "candidates" not in response and isinstance(response.get("segments"), list):
                notices.append(
                    f"{ep.id}: normalized an AI single-proposal object missing its candidates wrapper; original response retained"
                )
            proposed, bad = parse_proposals(
                response,
                episodes,
                {ep.id} | ({episode_list[i - 1].id} if i else set()),
                minimum,
                maximum,
            )
            local.extend(proposed)
            rejected.extend({"episode_id": ep.id, **b} for b in bad)
        # Merge identical intervals, preserving AI provenance when supplied.
        unique = {c["id"]: c for c in local}
        local = list(unique.values())
        if provider:
            valid = [c for c in local if c["validation"]["valid"]]
            proposal_ids = {c["id"] for c in valid if c["origin"] == "llm_proposal"}
            survivors = deduplicate(valid)
            chosen = [c for c in valid if c["id"] in proposal_ids]
            chosen.extend(c for c in survivors if c["id"] not in proposal_ids)
            chosen = chosen[:1]
            if chosen:
                if progress:
                    progress(i, len(episode_list), f"Critiquing {ep.title} ({len(chosen)} cuts)")
                critique(provider, episodes, chosen, notices)
            # In AI mode only successfully critiqued candidates may enter the AI shortlist.
            for c in local:
                if c["assessment"]["method"] != "llm_newcomer_critique":
                    c["eligible"] = False
                    if c["validation"]["valid"]:
                        c["status"] = "not_ai_assessed"
        candidates.extend(local)
        coverage.append(
            {
                "episode_id": ep.id,
                "episode_number": ep.number,
                "events": len(ep.events),
                "candidates": len(local),
                "valid": sum(c["validation"]["valid"] for c in local),
                "eligible": sum(c["eligible"] for c in local),
                "ai_assessed": sum(
                    c["assessment"]["method"] == "llm_newcomer_critique" for c in local
                ),
                "warnings": len(ep.warnings),
                "status": "processed",
            }
        )
    candidates = list({c["id"]: c for c in candidates}.values())
    valid = [c for c in candidates if c["validation"]["valid"]]
    distinct = deduplicate(valid)
    # Eligibility takes priority within a duplicate family; a high score cannot rescue a failed gate.
    eligible_distinct = deduplicate([c for c in candidates if c["eligible"]])
    target = math.ceil(len(distinct) * shortlist_percent / 100) if distinct else 0
    shortlist = eligible_distinct[:target]
    selected_ids = {c["id"] for c in shortlist}
    for rank, c in enumerate(eligible_distinct, 1):
        c["rank"] = rank
    for c in candidates:
        c["shortlisted"] = c["id"] in selected_ids
        if c["shortlisted"]:
            c["status"] = "shortlisted"
        c["title"] = (
            c["proposal"].get("title")
            or re.sub(r"\s+", " ", c["assessment"]["hook"]).strip('"“” ')[:92]
        )
    baseline = fixed_baseline(episodes, minimum, maximum)
    for item in coverage:
        item["shortlisted"] = sum(
            any(s["episode_id"] == item["episode_id"] for s in c["segments"]) for c in shortlist
        )
    evaluation = {
        "baseline": metrics(baseline),
        "all_generated": metrics(candidates),
        "valid_distinct": metrics(distinct),
        "shortlist": metrics(shortlist),
        "human_acceptance": None,
        "audience_continuation": None,
        "interpretation": "Technical validity is measured against source timestamps. Rubric scores are uncalibrated editorial proxies, not independent quality labels. The fixed-window baseline and filtered shortlist have different selection criteria; validity differences do not establish audience lift.",
        "failures": [
            {
                "id": c["id"],
                "segments": c["segments"],
                "errors": c["validation"]["errors"],
                "risks": c["assessment"]["risks"],
            }
            for c in sorted(candidates, key=lambda c: c["id"])
            if not c["validation"]["valid"]
        ][:20],
    }
    if len(shortlist) < target:
        notices.append(
            f"Only {len(shortlist)} candidates passed the gates for a target of {target}; no quota padding"
        )
    if not provider:
        notices.append(
            "No model was called. This is the reproducible offline rules baseline; AI quality and viewer performance have not been measured."
        )
    failures = provider.failures if provider else []
    if failures:
        notices.append(
            "PARTIAL AI RUN: provider became unavailable. All source episodes were processed, but remaining cuts were not AI-assessed and cannot enter the AI shortlist. Inspect provider_failures and raw_model_calls."
        )
    result = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": config.mode,
        "model": config.model or None,
        "score_kind": "Uncalibrated editorial rubric / 100",
        "config": {
            "minimum_seconds": minimum_seconds,
            "maximum_seconds": maximum_seconds,
            "shortlist_percent": shortlist_percent,
            "duplicate_iou_threshold": 0.5,
            "gates": {"hook": 2, "comprehension": 2, "cliffhanger": 2},
        },
        "summary": {
            "episodes": len(episodes),
            "events": sum(len(ep.events) for ep in episode_list),
            "candidates": len(candidates),
            "valid_candidates": len(valid),
            "distinct_candidates": len(distinct),
            "eligible_distinct": len(eligible_distinct),
            "target_shortlist": target,
            "shortlisted": len(shortlist),
            "source_minutes": round(sum(ep.duration_ms for ep in episode_list) / 60000, 2),
            "seconds": round(time.monotonic() - started, 3),
            "ai_calls": len(journal),
            "ai_assessed": sum(
                c["assessment"]["method"] == "llm_newcomer_critique" for c in candidates
            ),
            "parse_warnings": sum(len(ep.warnings) for ep in episode_list),
        },
        "episodes": [ep.public() for ep in episode_list],
        "coverage": coverage,
        "shortlist_ids": [c["id"] for c in shortlist],
        "candidates": sorted(
            candidates,
            key=lambda c: (not c["shortlisted"], not c["eligible"], -c["score"], c["id"]),
        ),
        "evaluation": evaluation,
        "baseline_candidates": baseline,
        "notices": notices,
        "rejected_proposals": rejected,
        "model_journal": journal,
    }
    result["partial"] = bool(failures)
    result["provider_failures"] = failures
    result["config"]["allow_partial"] = config.allow_partial
    result["config"]["public_input"] = public_input
    result["config"]["confidential_input_authorized"] = config.confidential_input_authorized
    result["summary"]["ai_assessed_episodes"] = sum(row["ai_assessed"] > 0 for row in coverage)
    if progress:
        progress(len(episode_list), len(episode_list), "Complete")
    return result


def export_csv(result: dict, shortlist_only: bool = True) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "rank",
            "promo_id",
            "segment",
            "episode",
            "start",
            "end",
            "promo_seconds",
            "editorial_score_not_probability",
            "method",
            "hook",
            "cliffhanger",
            "unanswered_question",
            "why",
            "warnings",
        ]
    )
    for c in result["candidates"]:
        if shortlist_only and not c["shortlisted"]:
            continue
        for index, s in enumerate(c["segments"], 1):
            values = [
                c.get("rank", ""),
                c["id"],
                index,
                s["episode_number"],
                s["start"],
                s["end"],
                c["duration_seconds"],
                c["score"],
                c["assessment"]["method"],
                c["assessment"]["hook"],
                c["assessment"]["cliffhanger"],
                c["assessment"]["unanswered_question"],
                c["assessment"]["why"],
                " | ".join(c["assessment"]["risks"]),
            ]
            # Protect spreadsheet consumers from formula interpretation of uploaded script text.
            writer.writerow(
                [
                    "'" + v
                    if isinstance(v, str)
                    and v.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
                    else v
                    for v in values
                ]
            )
    return buf.getvalue()


def save_run(result: dict, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)

    def write_json(name: str, value) -> None:
        target = directory / name
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)

    write_json("result.json", result)
    write_json("raw_candidates.json", result["candidates"])
    write_json("raw_model_calls.json", result["model_journal"])
    write_json("evaluation.json", result["evaluation"])
    write_json("episode_coverage.json", result["coverage"])
    (directory / "shortlist.csv").write_text(export_csv(result), encoding="utf-8")
    manifest = {
        "created_at": result["created_at"],
        "mode": result["mode"],
        "model": result["model"],
        "partial": result["partial"],
        "config": result["config"],
        "source_hashes": {ep["id"]: ep["source_hash"] for ep in result["episodes"]},
        "summary": result["summary"],
        "artifacts": {
            name: sha256((directory / name).read_bytes()).hexdigest()
            for name in [
                "result.json",
                "raw_candidates.json",
                "raw_model_calls.json",
                "evaluation.json",
                "episode_coverage.json",
                "shortlist.csv",
            ]
        },
    }
    write_json("manifest.json", manifest)

"""Independent structural audit of a saved run and its artifact checksums."""

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from promo_lab.domain import Episode, Event
from promo_lab.pipeline import overlap, validate_segments


def audit(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    for name, expected in manifest["artifacts"].items():
        assert sha256((directory / name).read_bytes()).hexdigest() == expected, (
            f"Checksum mismatch: {name}"
        )
    result = json.loads((directory / "result.json").read_text())
    episodes = {}
    for raw in result["episodes"]:
        episode = Episode(**{**raw, "events": [Event(**e) for e in raw["events"]]})
        assert manifest["source_hashes"][episode.id] == episode.source_hash
        episodes[episode.id] = episode
    assert len(episodes) == result["summary"]["episodes"] == len(result["coverage"])
    assert sum(len(e.events) for e in episodes.values()) == result["summary"]["events"]
    assert len({c["id"] for c in result["candidates"]}) == len(result["candidates"])
    shortlist = [c for c in result["candidates"] if c["shortlisted"]]
    assert set(c["id"] for c in shortlist) == set(result["shortlist_ids"])
    assert len(shortlist) == result["summary"]["shortlisted"]
    minimum = result["config"]["minimum_seconds"] * 1000
    maximum = result["config"]["maximum_seconds"] * 1000
    for c in result["candidates"]:
        v = validate_segments(episodes, c["segments"], minimum, maximum)
        assert v["valid"] == c["validation"]["valid"], c["id"]
        assert v["duration_ms"] == c["validation"]["duration_ms"]
        if c["shortlisted"]:
            assert c["eligible"] and v["valid"]
            if result["mode"] != "offline":
                assert c["assessment"]["method"] == "llm_newcomer_critique"
            for key in ("hook", "comprehension", "cliffhanger"):
                assert c["assessment"]["scores"][key] >= 2
            for evidence in c["assessment"]["evidence_event_ids"]:
                assert any(e.id == evidence for ep in episodes.values() for e in ep.events)
    for i, a in enumerate(shortlist):
        for b in shortlist[i + 1 :]:
            assert overlap(a, b) < result["config"]["duplicate_iou_threshold"]
    with (directory / "shortlist.csv").open() as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == sum(len(c["segments"]) for c in shortlist)
    print(
        json.dumps(
            {
                "passed": True,
                "episodes": len(episodes),
                "events": result["summary"]["events"],
                "candidates": len(result["candidates"]),
                "shortlisted": len(shortlist),
                "artifact_checksums": "verified",
                "source_and_gate_checks": "verified",
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    audit(parser.parse_args().directory)

"""Exercise local HTTP boundaries and a fresh upload without external services."""

import base64
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = os.getenv("PROMO_TEST_URL", "http://127.0.0.1:8765")


def request(path, value=None, headers=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    data = json.dumps(value).encode() if value is not None else None
    try:
        with urlopen(Request(BASE + path, data, h), timeout=15) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


checks = []
code, raw = request("/api/status")
assert code == 200
demo = next(run for run in json.loads(raw)["runs"] if run.get("built_in"))
demo_path = f"/api/runs/{demo['id']}"
code, raw = request(demo_path)
result = json.loads(raw)
assert code == 200 and result["config"]["public_input"]
assert result["summary"]["ai_assessed"] == 1
assert {call["purpose"] for call in result["model_journal"]} == {
    "propose_E001",
    "newcomer_critique",
}
assert request(demo_path + "?artifact=bundle.zip")[0] == 200
checks.extend(["status", "saved public AI example"])
for path in ["/.env", "/README.md", "/../.env", "/api/runs/not-a-real-run"]:
    assert request(path)[0] == 404, path
checks.append("private files not served")
assert request("/api/status", headers={"Host": "evil.example"})[0] == 403
assert request("/api/runs", {}, {"Origin": "https://evil.example"})[0] == 403
checks.append("host and origin checks")
for body in [
    {"source": "upload", "files": []},
    {"source": "sample", "provider": "unknown"},
    {"source": "sample", "shortlist_percent": None},
    {"source": "sample", "shortlist_percent": 0},
    {
        "source": "upload",
        "files": [{"name": "x.zip", "data": base64.b64encode(b"not a zip").decode()}],
    },
]:
    code, raw = request("/api/runs", body)
    assert code == 400, (body, code, raw)
checks.append("invalid requests rejected")
text = (Path(__file__).resolve().parents[1] / "promo_lab/examples/episode-001.txt").read_bytes()
code, raw = request(
    "/api/runs",
    {
        "source": "upload",
        "provider": "offline",
        "files": [{"name": "episode-001.txt", "data": base64.b64encode(text).decode()}],
    },
)
assert code == 202, raw
job_id = json.loads(raw)["job_id"]
for _ in range(100):
    code, raw = request("/api/jobs/" + job_id)
    job = json.loads(raw)
    if job["status"] != "running":
        break
    time.sleep(0.1)
assert job["status"] == "complete", job
code, raw = request("/api/runs/" + job["run_id"])
result = json.loads(raw)
assert code == 200 and result["summary"]["episodes"] == 1
assert result["mode"] == "offline" and result["summary"]["ai_calls"] == 0
for artifact in ["shortlist.csv", "episode_coverage.json", "raw_model_calls.json", "bundle.zip"]:
    code, raw = request("/api/runs/" + job["run_id"] + "?artifact=" + artifact)
    assert code == 200 and raw
checks.extend(["new upload runs", "job polling", "exports"])
print(json.dumps({"passed": True, "checks": checks}))

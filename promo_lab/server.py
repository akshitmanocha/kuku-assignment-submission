"""Dependency-free, loopback-only app server with background run jobs."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import mimetypes
from pathlib import Path
import re
from threading import Lock
from urllib.parse import parse_qs, urlparse
from uuid import uuid4
import zipfile

from .domain import ingest, load_path
from .pipeline import run_pipeline, save_run
from .providers import ProviderConfig, provider_status
from .experiments import ExperimentStore
from .experiment_content import cards_from_run
from .simulations import SimulationStore

DEMO_RUN_ID = "public-ai-example"
DEMO_RUN = Path(__file__).parent / "demo_run"


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.runs = root / "output" / "runs"
        self.jobs = {}
        self.lock = Lock()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.active = None
        self.experiments = ExperimentStore(root / "output" / "experiments")
        self.simulations = SimulationStore(root / "output" / "simulations", self.experiments)

    def paths(self):
        return sorted(
            self.runs.glob("*/result.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )

    def list_runs(self):
        runs = []
        directories = [(p.parent.name, p.parent, False) for p in self.paths()[:30]]
        directories.append((DEMO_RUN_ID, DEMO_RUN, True))
        for run_id, directory, built_in in directories:
            try:
                manifest = json.loads((directory / "manifest.json").read_text())
                runs.append(
                    {
                        "id": run_id,
                        "built_in": built_in,
                        "created_at": manifest["created_at"],
                        "mode": manifest["mode"],
                        "summary": manifest["summary"],
                    }
                )
            except (OSError, ValueError, KeyError):
                continue
        return runs

    def run_path(self, run_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
            raise ValueError("Invalid run ID")
        path = DEMO_RUN if run_id == DEMO_RUN_ID else self.runs / run_id
        if not (path / "result.json").is_file():
            raise FileNotFoundError("Run not found")
        return path

    def start(self, body: dict) -> str:
        mode = body.get("provider", "offline")
        config = ProviderConfig.from_env(mode)
        config.allow_partial = body.get("allow_partial", False)
        if type(config.allow_partial) is not bool:
            raise ValueError("allow_partial must be a boolean")
        config.validate()
        source = body.get("source", "sample")
        public_input = source == "sample" or body.get("public_input") is True
        config.validate_input(public_input)
        if (
            source == "pack"
            and config.public_inputs_only
            and not config.confidential_input_authorized
        ):
            raise ValueError(
                "Use the original public demo with NVIDIA's free endpoint; the supplied Kuku pack is confidential"
            )
        if source == "sample":
            episodes = load_path(Path(__file__).parent / "examples")
        elif source == "pack":
            packs = sorted(self.root.glob("*-scripts.zip"))
            if not packs:
                raise ValueError(
                    "No local input pack found. Upload a ZIP or use the original demo."
                )
            episodes = load_path(packs[0])
        elif source == "upload":
            uploads = body.get("files")
            if not isinstance(uploads, list) or not 1 <= len(uploads) <= 150:
                raise ValueError("Upload 1–150 screenplay files")
            files = []
            for item in uploads:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("name"), str)
                    or not isinstance(item.get("data"), str)
                ):
                    raise ValueError("Malformed upload")
                try:
                    files.append((item["name"], base64.b64decode(item["data"], validate=True)))
                except ValueError:
                    raise ValueError("Invalid base64 upload") from None
            episodes = ingest(files)
        else:
            raise ValueError("Unknown source")
        selected = body.get("episode_ids", [])
        if selected:
            if not isinstance(selected, list) or not all(isinstance(x, str) for x in selected):
                raise ValueError("Invalid episode selection")
            episodes = [ep for ep in episodes if ep.id in selected]
            if not episodes:
                raise ValueError("No matching episodes")
        percent = float(body.get("shortlist_percent", 1))
        if not 0 < percent <= 100:
            raise ValueError("Shortlist percentage must be in (0, 100]")
        with self.lock:
            if self.active:
                raise ValueError("A run is already active; wait for it to finish")
            job_id = uuid4().hex[:16]
            self.active = job_id
            self.jobs[job_id] = {
                "id": job_id,
                "status": "running",
                "done": 0,
                "total": len(episodes),
                "message": "Preparing timeline",
                "run_id": None,
            }

        def work():
            def progress(done, total, message):
                with self.lock:
                    self.jobs[job_id].update(done=done, total=total, message=message)

            try:
                config.journal_path = str(self.runs / job_id / "raw_model_calls.json")
                result = run_pipeline(
                    episodes, config, percent, progress=progress, public_input=public_input
                )
                save_run(result, self.runs / job_id)
                with self.lock:
                    self.jobs[job_id].update(
                        status="complete", message="Run complete", run_id=job_id
                    )
            except Exception as exc:
                # The provider persists journals on successful and failed calls; no credentials
                # or arbitrary backend response text are exposed in the interface.
                with self.lock:
                    self.jobs[job_id].update(
                        status="failed",
                        message=str(exc)
                        if isinstance(exc, ValueError)
                        else "Run failed; inspect the server console",
                        run_id=None,
                    )
                print(f"Run {job_id} failed ({type(exc).__name__})", flush=True)
            finally:
                with self.lock:
                    self.active = None

        self.executor.submit(work)
        return job_id


def serve_app(root: Path, port: int, *, host: str = "127.0.0.1") -> None:
    store = Store(root)
    web_root = Path(__file__).parent / "web"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(
            self, body: bytes, content_type: str, status: int = 200, filename: str | None = None
        ):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'",
            )
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def json(self, value, status=200):
            self.respond(
                json.dumps(value, ensure_ascii=False).encode(),
                "application/json; charset=utf-8",
                status,
            )

        def allowed_host(self) -> bool:
            return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def do_GET(self):
            if not self.allowed_host():
                return self.json({"error": "Local requests only"}, 403)
            try:
                url = urlparse(self.path)
                path, query = url.path, parse_qs(url.query)
                if path == "/api/status":
                    return self.json(
                        {
                            "providers": provider_status(),
                            "pack_available": bool(list(root.glob("*-scripts.zip"))),
                            "active_job": store.active,
                            "runs": store.list_runs(),
                        }
                    )
                if path == "/api/experiments":
                    return self.json({"studies": store.experiments.list_studies()})
                if path == "/api/simulations":
                    return self.json({"simulations": store.simulations.list()})
                sim_match = re.fullmatch(r"/api/simulations/([A-Za-z0-9_-]+)(?:/(export))?", path)
                if sim_match:
                    sim_id, action = sim_match.groups()
                    if action:
                        artifact = query.get("artifact", ["report.json"])[0]
                        data, kind = store.simulations.export(sim_id, artifact)
                        return self.respond(data, kind, filename=f"SYNTHETIC-{sim_id}-{artifact}")
                    return self.json(store.simulations.report(sim_id))
                study_match = re.fullmatch(
                    r"/api/experiments/([A-Za-z0-9_-]+)(?:/(public|export))?", path
                )
                if study_match:
                    study_id, action = study_match.groups()
                    if action == "public":
                        return self.json(store.experiments.study(study_id, public=True))
                    if action == "export":
                        artifact = query.get("artifact", ["training.jsonl"])[0]
                        data, kind = store.experiments.export(study_id, artifact)
                        return self.respond(data, kind, filename=f"reading-{study_id}-{artifact}")
                    return self.json(store.experiments.report(study_id))
                session_match = re.fullmatch(
                    r"/api/experiment-sessions/([A-Za-z0-9_-]+)(?:/(continuation))?", path
                )
                if session_match:
                    session_id, action = session_match.groups()
                    token = self.headers.get("Authorization", "").removeprefix("Bearer ")
                    if action:
                        return self.json(
                            store.experiments.continuation(
                                session_id, token, query.get("card_id", [""])[0]
                            )
                        )
                    return self.json(store.experiments.session(session_id, token))
                if path.startswith("/api/jobs/"):
                    with store.lock:
                        job = dict(store.jobs.get(path.rsplit("/", 1)[1], {}))
                    return self.json(job or {"error": "Job not found"}, 200 if job else 404)
                if path.startswith("/api/runs/"):
                    run_id = path.split("/")[3]
                    directory = store.run_path(run_id)
                    artifact = query.get("artifact", ["result.json"])[0]
                    allowed = {
                        "result.json",
                        "shortlist.csv",
                        "raw_candidates.json",
                        "raw_model_calls.json",
                        "evaluation.json",
                        "episode_coverage.json",
                        "manifest.json",
                    }
                    if artifact == "bundle.zip":
                        buf = io.BytesIO()
                        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
                            for name in sorted(allowed):
                                archive.write(directory / name, name)
                        scope = "public" if run_id == DEMO_RUN_ID else "private"
                        return self.respond(
                            buf.getvalue(),
                            "application/zip",
                            filename=f"promo-lab-{run_id}-{scope}.zip",
                        )
                    if artifact not in allowed:
                        raise ValueError("Unknown export")
                    body = (directory / artifact).read_bytes()
                    kind = (
                        "text/csv; charset=utf-8"
                        if artifact.endswith(".csv")
                        else "application/json; charset=utf-8"
                    )
                    return self.respond(
                        body, kind, filename=artifact if "download" in query else None
                    )
                static = {
                    "/": "index.html",
                    "/app.js": "app.js",
                    "/styles.css": "styles.css",
                    "/experiment.js": "experiment.js",
                    "/experiment.css": "experiment.css",
                    "/experiment_admin.js": "experiment_admin.js",
                    "/simulation_admin.js": "simulation_admin.js",
                }.get(path)
                if re.fullmatch(r"/experiment/[A-Za-z0-9_-]+", path):
                    static = "experiment.html"
                if not static:
                    raise FileNotFoundError()
                file = web_root / static
                return self.respond(
                    file.read_bytes(), mimetypes.guess_type(file.name)[0] or "text/plain"
                )
            except FileNotFoundError:
                self.json({"error": "Not found"}, 404)
            except PermissionError:
                self.json({"error": "Session authorization required"}, 403)
            except (ValueError, TypeError, OSError) as exc:
                self.json({"error": str(exc)}, 400)

        def do_POST(self):
            if not self.allowed_host():
                return self.json({"error": "Local requests only"}, 403)
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}:
                return self.json({"error": "Cross-origin requests are not allowed"}, 403)
            try:
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("Use application/json")
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= 21_000_000:
                    raise ValueError("Request exceeds upload limit")
                if self.path != "/api/runs" and size > 200_000:
                    raise ValueError("Experiment request exceeds size limit")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("Request must be a JSON object")
                if self.path == "/api/runs":
                    return self.json({"job_id": store.start(body)}, 202)
                if self.path == "/api/simulations":
                    options = {key: value for key, value in body.items() if key != "study_id"}
                    return self.json(store.simulations.create(body.get("study_id"), **options), 201)
                if self.path == "/api/experiments":
                    run_id = body.get("source_run_id")
                    promos = (
                        cards_from_run(
                            json.loads((store.run_path(run_id) / "result.json").read_text()), run_id
                        )
                        if run_id
                        else None
                    )
                    return self.json(
                        store.experiments.create_study(
                            body.get("name", "Reading pilot"),
                            body.get("is_test", False),
                            promos,
                            run_id,
                        ),
                        201,
                    )
                study_match = re.fullmatch(
                    r"/api/experiments/([A-Za-z0-9_-]+)/(sessions|state|remove-test)", self.path
                )
                if study_match:
                    study_id, action = study_match.groups()
                    if action == "sessions":
                        return self.json(
                            store.experiments.start_session(
                                study_id, body.get("participant_key"), body.get("consent")
                            ),
                            201,
                        )
                    if action == "state":
                        return self.json(
                            store.experiments.close_study(study_id, body.get("closed"))
                        )
                    store.experiments.delete_test_study(study_id)
                    return self.json({"deleted": True})
                session_match = re.fullmatch(
                    r"/api/experiment-sessions/([A-Za-z0-9_-]+)/(events|withdraw)", self.path
                )
                if session_match:
                    session_id, action = session_match.groups()
                    token = body.get("session_token", "")
                    if action == "withdraw":
                        return self.json(store.experiments.withdraw(session_id, token))
                    return self.json(
                        store.experiments.ingest_events(session_id, token, body.get("events"))
                    )
                return self.json({"error": "Not found"}, 404)
            except FileNotFoundError:
                self.json({"error": "Not found"}, 404)
            except PermissionError:
                self.json({"error": "Session authorization required"}, 403)
            except (ValueError, TypeError, OSError) as exc:
                self.json({"error": str(exc)}, 400)

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Promo Lab → http://127.0.0.1:{port}", flush=True)
    print(f"Listening on {host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        store.executor.shutdown(wait=False, cancel_futures=True)

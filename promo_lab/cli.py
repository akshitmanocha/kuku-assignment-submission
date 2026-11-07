"""Run from a clean checkout with python3 -m promo_lab."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from .domain import load_path
from .pipeline import run_pipeline, save_run
from .providers import ProviderConfig

ROOT = Path(__file__).resolve().parent.parent


def load_env(root: Path = ROOT) -> None:
    path = root / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {
            "PROMO_API_BASE",
            "PROMO_API_KEY",
            "OPENAI_API_KEY",
            "PROMO_MODEL",
            "PROMO_ALLOW_CONFIDENTIAL",
            "GROQ_API_BASE",
            "GROQ_API_KEY",
            "GROQ_MODEL",
            "OLLAMA_BASE_URL",
            "OLLAMA_MODEL",
        }:
            os.environ.setdefault(key, value.strip().strip("\"'"))


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Promo Lab: source-grounded editorial discovery")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Launch the local browser app")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--host",
        choices=["127.0.0.1", "0.0.0.0"],
        default="127.0.0.1",
        help="Listen on loopback by default. Docker uses 0.0.0.0 inside the container.",
    )
    run = sub.add_parser("run", help="Process a ZIP, script, or folder")
    run.add_argument("input", type=Path)
    run.add_argument("--output", type=Path, default=ROOT / "output" / "runs" / "cli")
    run.add_argument(
        "--provider", choices=["offline", "openai", "groq", "ollama"], default="offline"
    )
    run.add_argument("--shortlist-percent", type=float, default=1)
    run.add_argument("--min-seconds", type=int, default=20)
    run.add_argument("--max-seconds", type=int, default=60)
    run.add_argument(
        "--allow-partial",
        action="store_true",
        help="Keep explicitly labeled results when AI becomes unavailable; unassessed cuts cannot enter the AI shortlist",
    )
    run.add_argument(
        "--public-input",
        action="store_true",
        help="Declare that the supplied input is public and non-confidential",
    )
    args = parser.parse_args()
    try:
        if args.command == "serve":
            from .server import serve_app

            serve_app(ROOT, args.port, host=args.host)
        else:
            episodes = load_path(args.input)

            def progress(done, total, message):
                print(f"[{done}/{total}] {message}", flush=True)

            config = ProviderConfig.from_env(args.provider)
            config.journal_path = str(args.output / "raw_model_calls.json")
            config.allow_partial = args.allow_partial
            public_input = args.public_input or args.input.resolve().is_relative_to(
                Path(__file__).resolve().parent / "examples"
            )
            result = run_pipeline(
                episodes,
                config,
                args.shortlist_percent,
                args.min_seconds,
                args.max_seconds,
                progress,
                public_input=public_input,
            )
            save_run(result, args.output)
            print(
                f"Saved {result['summary']['shortlisted']} recommendations from {len(episodes)} episodes to {args.output.resolve()}"
            )
            print(
                f"Mode: {result['mode']}. Scores are editorial proxies, not audience probabilities."
            )
            if result["partial"]:
                print(
                    "PARTIAL AI COVERAGE: inspect notices and provider_failures before submission."
                )
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)

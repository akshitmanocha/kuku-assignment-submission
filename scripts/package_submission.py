"""Create separate shareable source and confidential submission archives."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package(run: Path, pdf: Path):
    result = json.loads((run / "result.json").read_text())
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    source = output / "promo-lab-source.zip"
    allowed = [
        ROOT / name
        for name in [
            "README.md",
            "pyproject.toml",
            "ML_ARCHITECTURE.md",
            "CONTRIBUTING.md",
            "Makefile",
            "Dockerfile",
            ".dockerignore",
            "package.json",
            "package-lock.json",
            ".editorconfig",
            ".prettierignore",
            ".gitignore",
            ".gitattributes",
            ".env.example",
        ]
    ]
    for folder in ["promo_lab", "scripts", "tests", "docs"]:
        allowed.extend(
            p
            for p in (ROOT / folder).rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and p.suffix not in {".pyc", ".pyo"}
            and p.name != ".DS_Store"
        )
    with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(set(allowed)):
            if not path.is_file():
                continue
            if not path.resolve().is_relative_to(ROOT):
                raise ValueError("Source archive cannot follow files outside the checkout")
            data = path.read_bytes()
            if re.search(
                rb"(?:gsk_[A-Za-z0-9]{20,}|sk-or-v1-[A-Za-z0-9]{20,}|sk-proj-[A-Za-z0-9_-]{30,})",
                data,
            ):
                raise ValueError(f"Potential API credential in source: {path.name}")
            z.writestr(path.relative_to(ROOT).as_posix(), data)
    private = output / "submission-private.zip"
    manifest = json.loads((run / "manifest.json").read_text())
    with zipfile.ZipFile(private, "w", zipfile.ZIP_DEFLATED) as z:
        for name, expected in manifest["artifacts"].items():
            path = run / name
            if sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f"Run artifact checksum mismatch: {name}")
            z.write(path, f"raw-outputs/{name}")
        z.write(run / "manifest.json", "raw-outputs/manifest.json")
        z.write(pdf, "solution.pdf")
        z.write(source, "prototype-source.zip")
        summary = result["summary"]
        z.writestr(
            "SUBMISSION_README.txt",
            f"Promo Lab - confidential assignment submission\n\nRun: {run.name}\nSource episodes processed: {summary['episodes']}\nAI-assessed episodes: {summary.get('ai_assessed_episodes', 0)}\nPartial provider coverage: {result.get('partial', False)}\nShortlisted: {summary['shortlisted']}\n\nprototype-source.zip contains shareable source, run steps and an original demo.\nsolution.pdf is the two-page solution document.\nraw-outputs contains unedited model responses and generated candidates, including confidential screenplay text. Do not publish this bundle or its raw outputs.\n\nScores are editorial estimates, not measured audience performance. Read notices and quality limitations before interpreting results. Applicant narration is optional and should be recorded in their own voice.\n",
        )
    print(
        json.dumps(
            {
                "source_archive": str(source),
                "source_bytes": source.stat().st_size,
                "private_submission": str(private),
                "private_bytes": private.stat().st_size,
                "partial": result.get("partial", False),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=ROOT / "output/runs/full-pack-qwen")
    parser.add_argument("--pdf", type=Path, default=ROOT / "output/pdf/promo-lab-solution.pdf")
    args = parser.parse_args()
    package(args.run, args.pdf)

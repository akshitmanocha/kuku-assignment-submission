"""Create separate shareable source and confidential submission archives."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from promo_lab.domain import MAX_FILE_BYTES, MAX_FILES, MAX_TOTAL_BYTES, ingest


def write_raw_outputs(archive, run, manifest, folder):
    for name, expected in manifest["artifacts"].items():
        if Path(name).name != name:
            raise ValueError("Run manifest contains an invalid artifact name")
        data = (run / name).read_bytes()
        if sha256(data).hexdigest() != expected:
            raise ValueError(f"Run artifact checksum mismatch: {name}")
        archive.writestr(f"{folder}/{name}", data)
    archive.write(run / "manifest.json", f"{folder}/manifest.json")


def episode_files(pack, manifest):
    with zipfile.ZipFile(pack) as archive:
        members = [
            item
            for item in archive.infolist()
            if item.filename.lower().endswith(".txt") and not item.filename.startswith("__MACOSX/")
        ]
        if (
            len(members) > MAX_FILES
            or any(item.file_size > MAX_FILE_BYTES for item in members)
            or sum(item.file_size for item in members) > MAX_TOTAL_BYTES
        ):
            raise ValueError("Episode archive exceeds the app's input limits")
        originals = {Path(item.filename).name: archive.read(item) for item in members}
    if len(originals) != len(members):
        raise ValueError("Episode archive has duplicate filenames")
    episodes = ingest(list(originals.items()))
    if {episode.id: episode.source_hash for episode in episodes} != manifest["source_hashes"]:
        raise ValueError("Episode archive does not match the input recorded in the saved run")
    return {
        f"episode-{episode.number:03d}.txt": originals[episode.filename] for episode in episodes
    }


def package_drive(source, run, pdf, input_pack, manifest):
    if manifest["partial"]:
        raise ValueError("The private Drive bundle requires a complete saved run")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run.name):
        raise ValueError("Saved run directory must use a valid app run ID")
    originals = episode_files(input_pack, manifest)
    run_folder = f"output/runs/{run.name}"
    readme_intro = f"""## This private submission

Extract the entire ZIP to a folder on your computer before launching the app. This bundle contains confidential assignment material. Share it only with authorized reviewers.

| File or folder | What it contains |
| --- | --- |
| [`solution.pdf`](solution.pdf) | Two-page solution with the three-stage architecture and observed AI error. |
| [`episodes/`](episodes/) | All {len(originals)} supplied episode scripts. File names follow episode order and the original text files are preserved byte for byte. |
| [`{run_folder}/`]({run_folder}/) | Required unedited full-pack outputs, including the shortlist, raw model responses and checksum manifest. |
| [`promo_lab/`](promo_lab/) | Runnable project. The steps below apply from this extracted folder. |

**Review the full-pack results.** Start with Python as described below. The app opens the saved run automatically. You can also select **Run history → {run.name} → Open analysis**. Open **Quality report** to compare the shortlist with the 30-second rule, or open `{run_folder}/shortlist.csv` directly. This is a saved AI run you can inspect without credentials.

**Rerun the supplied episodes.** In **New analysis**, select **Upload your screenplay files**, choose the TXT files from `episodes/`, and select **Offline editorial baseline**. To try a single episode, choose **Paste screenplay text** and paste its contents. Docker opens the bundled public example in its separate workspace. Use the same upload steps to run the supplied episodes there.

To run the full set locally from the terminal without credentials, use:

```bash
python3 -m promo_lab run episodes --provider offline --output output/runs/reviewer-offline
```

The offline run uses editorial rules. The archived full-pack results used Groq Qwen. A fresh AI run requires your own authorized provider credentials.

"""
    target = source.parent / "promo-lab-kuku-submission.zip"
    with NamedTemporaryFile(dir=target.parent, prefix=".promo-lab-kuku-", delete=False) as temp:
        draft = Path(temp.name)
    try:
        with (
            zipfile.ZipFile(source) as project,
            zipfile.ZipFile(draft, "w", zipfile.ZIP_DEFLATED) as archive,
        ):
            for name in project.namelist():
                data = project.read(name)
                if name == "README.md":
                    title, tagline, body = data.decode().split("\n\n", 2)
                    data = f"{title}\n\n{tagline}\n\n{readme_intro}{body}".encode()
                archive.writestr(name, data)
            archive.write(pdf, "solution.pdf")
            for name, data in originals.items():
                archive.writestr(f"episodes/{name}", data)
            write_raw_outputs(archive, run, manifest, run_folder)
        draft.replace(target)
    finally:
        draft.unlink(missing_ok=True)
    return target


def package(run: Path, pdf: Path, input_pack: Path | None = None):
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
        write_raw_outputs(z, run, manifest, "raw-outputs")
        z.write(pdf, "solution.pdf")
        z.write(source, "prototype-source.zip")
        summary = result["summary"]
        z.writestr(
            "SUBMISSION_README.txt",
            f"Promo Lab - confidential assignment submission\n\nRun: {run.name}\nSource episodes processed: {summary['episodes']}\nAI-assessed episodes: {summary.get('ai_assessed_episodes', 0)}\nPartial provider coverage: {result.get('partial', False)}\nShortlisted: {summary['shortlisted']}\n\nprototype-source.zip contains shareable source, run steps and an original demo.\nsolution.pdf is the two-page solution document.\nraw-outputs contains unedited model responses and generated candidates, including confidential screenplay text. Do not publish this bundle or its raw outputs.\n\nScores are editorial estimates, not measured audience performance. Read notices and quality limitations before interpreting results. Applicant narration is optional and should be recorded in their own voice.\n",
        )
    report = {
        "source_archive": str(source),
        "source_bytes": source.stat().st_size,
        "private_submission": str(private),
        "private_bytes": private.stat().st_size,
        "partial": result.get("partial", False),
    }
    if input_pack is not None:
        drive = package_drive(source, run, pdf, input_pack, manifest)
        report["private_drive_submission"] = str(drive)
        report["private_drive_bytes"] = drive.stat().st_size
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=ROOT / "output/runs/full-pack-qwen")
    parser.add_argument("--pdf", type=Path, default=ROOT / "output/pdf/promo-lab-solution.pdf")
    parser.add_argument(
        "--input-pack",
        type=Path,
        help="Also build the private Drive ZIP with matching episode files",
    )
    args = parser.parse_args()
    package(args.run, args.pdf, args.input_pack)

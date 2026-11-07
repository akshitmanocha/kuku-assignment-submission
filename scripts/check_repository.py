"""Check public source for accidental credentials, private files and broken doc links."""

from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CREDENTIAL = re.compile(
    rb"(?:gsk_[A-Za-z0-9]{20,}|sk-or-v1-[A-Za-z0-9]{20,}|sk-proj-[A-Za-z0-9_-]{30,})"
)


def source_files():
    for name in (
        "README.md",
        "ML_ARCHITECTURE.md",
        "CONTRIBUTING.md",
        "pyproject.toml",
        "package.json",
        ".env.example",
    ):
        path = ROOT / name
        if path.is_file():
            yield path
    for name in ("promo_lab", "scripts", "tests", "docs"):
        yield from (
            p
            for p in (ROOT / name).rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and p.suffix not in {".pyc", ".pyo"}
            and p.name != ".DS_Store"
        )


def check():
    errors = []
    paths = list(source_files())
    for path in paths:
        if CREDENTIAL.search(path.read_bytes()):
            errors.append(f"Potential credential in {path.relative_to(ROOT)}")
        if path.suffix == ".md":
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
                if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                    continue
                target = target.split("#", 1)[0].split(' "', 1)[0]
                if target and not (path.parent / target).exists():
                    errors.append(f"Broken link in {path.relative_to(ROOT)}: {target}")
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=False)
    for name in result.stdout.decode().split("\0"):
        path = Path(name)
        if name and (
            name in {".env", "solution.pdf"}
            or name.startswith(("episodes/", "output/", "tmp/", "node_modules/"))
            or name.endswith("-scripts.zip")
            or (path.suffix == ".pdf" and path.name.startswith("Kuku"))
        ):
            errors.append(f"Private or generated file is tracked: {name}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(
        f"Repository checks passed: {len(paths)} source files; document links and credential patterns checked."
    )


if __name__ == "__main__":
    check()

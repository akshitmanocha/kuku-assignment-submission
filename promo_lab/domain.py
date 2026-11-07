"""Integer-millisecond source timelines and strict screenplay ingestion."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
import zipfile

MAX_FILES = 150
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 15_000_000
MAX_EVENTS = 2_000


def parse_time(value: str) -> int:
    parts = value.strip().split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"Invalid timestamp: {value!r}")
    try:
        if any(not re.fullmatch(r"\d+", p) for p in parts[:-1]):
            raise ValueError("Invalid time component")
        seconds = Decimal(parts[-1])
        if not seconds.is_finite() or seconds < 0 or seconds >= 60:
            raise ValueError("Seconds must be in [0, 60)")
        if len(parts) == 3 and int(parts[-2]) >= 60:
            raise ValueError("Minutes must be in [0, 60)")
        total = sum(Decimal(p) * (60**i) for i, p in enumerate(reversed(parts)))
        return int((total * 1000).quantize(Decimal("1")))
    except (InvalidOperation, OverflowError) as exc:
        raise ValueError(f"Invalid timestamp: {value!r}") from exc


def timecode(ms: int) -> str:
    if ms % 10:
        minutes, rest = divmod(ms, 60000)
        seconds, fraction = divmod(rest, 1000)
        return f"{minutes:02d}:{seconds:02d}.{fraction:03d}"
    centis = round(ms / 10)
    minutes, rest = divmod(centis, 6000)
    seconds, fraction = divmod(rest, 100)
    return f"{minutes:02d}:{seconds:02d}.{fraction:02d}"


@dataclass
class Event:
    id: str
    start_ms: int
    end_ms: int
    kind: str
    label: str
    text: str
    scene: str


@dataclass
class Episode:
    id: str
    number: int
    filename: str
    title: str
    logline: str
    continuity: str
    duration_ms: int
    events: list[Event]
    source_hash: str
    warnings: list[str] = field(default_factory=list)

    def public(self) -> dict:
        return asdict(self)


def parse_script(text: str, filename: str = "script.txt") -> Episode:
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    number_match = re.search(r"EPISODE\s+NUMBER:\s*(?:Episode\s*)?(\d+)", text, re.I)
    if not number_match:
        number_match = re.search(r"episode[-_ ]*(\d+)", filename, re.I)
    if not number_match:
        raise ValueError(f"{filename}: episode number missing; add EPISODE NUMBER: Episode 1")
    number = int(number_match[1])
    if not 1 <= number <= 999999:
        raise ValueError(f"{filename}: episode number out of range")
    eid = f"E{number:03d}"
    header_pattern = re.compile(r"^\s*\*\*([^\n]+?)\*\*\s*$", re.M)
    headers = list(header_pattern.finditer(text))
    events = []
    warnings = []
    if len(headers) > MAX_EVENTS:
        raise ValueError(f"{filename}: too many events")
    for i, header in enumerate(headers):
        body = text[header.end() : headers[i + 1].start() if i + 1 < len(headers) else len(text)]
        timing = re.match(r"\s*Start:\s*\(([^)]+)\)\s*\|\s*End:\s*\(([^)]+)\)", body, re.I)
        if not timing:
            raise ValueError(f"{filename}: missing timing after {header[1]!r}")
        start, end = parse_time(timing[1]), parse_time(timing[2])
        if end <= start:
            raise ValueError(f"{filename}: nonpositive duration at {timing[1]}")
        content = re.split(
            r"\n\s*(?:SCENE\s+\d+|---\s*SCRIPT END)", body[timing.end() :], maxsplit=1, flags=re.I
        )[0].strip()
        # Scene fields belong to the next scene, never to the preceding action.
        content = re.split(r"\n\s*Scene heading:", content, maxsplit=1, flags=re.I)[0].strip()
        if not content:
            raise ValueError(f"{filename}: empty event at {timing[1]}")
        label = header[1].rstrip(":").strip()
        upper = label.upper()
        kind = {"CAMERA": "camera", "ACTION": "action", "SOUND FX": "sound"}.get(upper, "dialogue")
        scenes = list(re.finditer(r"^\s*SCENE\s+(\d+)\s*$", text[: header.start()], re.M | re.I))
        scene = scenes[-1][1] if scenes else "1"
        events.append(Event(f"{eid}-{i + 1:04d}", start, end, kind, label, content, scene))
        if kind == "dialogue" and len(content.split()) * 60000 / (end - start) > 240:
            warnings.append(
                f"{events[-1].id}: scripted speech exceeds 240 words/min; timing needs footage review"
            )
    if not events:
        raise ValueError(f"{filename}: no timestamped events found")
    events.sort(key=lambda e: (e.start_ms, e.end_ms, e.id))
    duration = max(e.end_ms for e in events)
    if duration > 3_600_000:
        raise ValueError(f"{filename}: episode longer than one hour")

    def metadata(name: str) -> str:
        match = re.search(rf"^{name}:\s*(.*)$", text, re.M | re.I)
        return match[1].strip() if match else ""

    return Episode(
        eid,
        number,
        Path(filename).name,
        f"Episode {number}",
        metadata("EPISODE LOGLINE"),
        metadata("CONTINUITY NOTES"),
        duration,
        events,
        sha256(text.encode()).hexdigest(),
        warnings,
    )


def ingest(files: list[tuple[str, bytes]]) -> list[Episode]:
    """Read ZIP members in memory; never extract untrusted archive paths."""
    expanded = []
    total = 0
    for name, data in files:
        if len(data) > MAX_TOTAL_BYTES:
            raise ValueError("Upload exceeds 15 MB")
        if name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(BytesIO(data)) as archive:
                    members = [
                        m
                        for m in archive.infolist()
                        if m.filename.lower().endswith(".txt")
                        and not m.filename.startswith("__MACOSX/")
                    ]
                    if len(members) > MAX_FILES:
                        raise ValueError("ZIP contains more than 150 scripts")
                    for member in members:
                        if (
                            member.file_size > MAX_FILE_BYTES
                            or total + member.file_size > MAX_TOTAL_BYTES
                        ):
                            raise ValueError("Uncompressed scripts exceed size limit")
                        total += member.file_size
                        expanded.append((member.filename, archive.read(member)))
            except zipfile.BadZipFile as exc:
                raise ValueError("Invalid ZIP archive") from exc
            except (RuntimeError, NotImplementedError, zipfile.LargeZipFile) as exc:
                raise ValueError(
                    "ZIP contains an unreadable, encrypted, or unsupported member"
                ) from exc
        elif name.lower().endswith(".txt"):
            if len(data) > MAX_FILE_BYTES:
                raise ValueError("A script exceeds 2 MB")
            total += len(data)
            expanded.append((name, data))
        else:
            raise ValueError("Only .txt screenplays and .zip archives are supported")
        if total > MAX_TOTAL_BYTES or len(expanded) > MAX_FILES:
            raise ValueError("Input exceeds 150 scripts or 15 MB uncompressed")
    if not expanded:
        raise ValueError("No .txt scripts found")
    episodes = []
    seen = set()
    for name, data in sorted(expanded):
        try:
            episode = parse_script(data.decode("utf-8-sig"), name)
        except UnicodeDecodeError as exc:
            raise ValueError(f"{Path(name).name}: scripts must use UTF-8 encoding") from exc
        if episode.id in seen:
            raise ValueError(f"Duplicate episode number: {episode.number}")
        seen.add(episode.id)
        episodes.append(episode)
    return sorted(episodes, key=lambda e: e.number)


def load_path(path: Path) -> list[Episode]:
    if path.is_dir():
        paths = sorted(path.rglob("*.txt"))
        if len(paths) > MAX_FILES:
            raise ValueError("Too many scripts")
    else:
        paths = [path]
    if any(p.stat().st_size > MAX_TOTAL_BYTES for p in paths):
        raise ValueError("Input file exceeds size limit")
    return ingest([(p.name, p.read_bytes()) for p in paths])

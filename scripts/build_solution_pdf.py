"""Render the two-page solution from saved run artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from xml.sax.saxutils import escape

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
INK = colors.HexColor("#202b26")
MUTED = colors.HexColor("#606b62")
ACCENT = colors.HexColor("#d5f16b")
PAPER = colors.HexColor("#f2f4ed")


def clean(text: str, maximum: int = 650) -> str:
    text = (
        re.sub(r"\s+", " ", str(text))
        .replace("—", " - ")
        .replace("–", "-")
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("…", "...")
    )
    if len(text) > maximum:
        text = text[: maximum - 3].rsplit(" ", 1)[0] + "..."
    return escape(text)


def build(run_dir: Path, output: Path) -> None:
    result = json.loads((run_dir / "result.json").read_text())
    summary, evaluation = result["summary"], result["evaluation"]
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="BodyLab",
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.1,
            textColor=INK,
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallLab",
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.3,
            textColor=MUTED,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="HeadingLab",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=INK,
            spaceBefore=8,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TitleLab",
            fontName="Helvetica-Bold",
            fontSize=27,
            leading=32,
            textColor=INK,
            spaceAfter=8,
        )
    )
    story = []

    def p(text, small=False):
        return Paragraph(text, styles["SmallLab" if small else "BodyLab"])

    def heading(text):
        story.append(Paragraph(text, styles["HeadingLab"]))

    def rate(value):
        return "unmeasured" if value is None else f"{100 * value:.1f}%"

    story.append(p("KUKU AI GENERALIST ASSIGNMENT / PROBLEM 1", small=True))
    story.append(Paragraph("Promo Lab", styles["TitleLab"]))
    story.append(
        p(
            "I chose Find the Promos because editors can verify each cut against the script, and viewers can show us which cuts make them want to continue. My approach uses an LLM to find promising promos, then learns from viewer behavior."
        )
    )
    story.append(
        p(
            "<b>Assumptions.</b> Timestamps are episode-relative, and dialogue, action and camera tracks can overlap. A 20-60 second promo can join up to three segments in chronological order. With scripts as input, the pilot uses reading as a proxy for watching."
        )
    )
    story.append(Spacer(1, 2))
    story.append(
        Image(
            str(ROOT / "docs/images/approach-overview.png"),
            width=175 * mm,
            height=99 * mm,
            kind="proportional",
        )
    )

    heading("My three-stage pipeline")
    story.append(
        p(
            "<b>1. LLM candidate retrieval.</b> Parse scripts into timestamped events. Generate cuts from script boundaries and ask the LLM for more using event IDs. Code checks source, duration, order and dialogue boundaries. A second LLM pass scores the hook, clarity, stakes, progression, cliffhanger and cut quality. Group overlaps and target the top 1% of distinct valid cuts, subject to score thresholds."
        )
    )
    story.append(
        p(
            "<b>2. Internal survey in a simulated feed.</b> Ask employees to browse a reel-style feed with one random promo among six unrelated stories. The text-card prototype logs one row per exposure with consent. A positive label requires a continuation click, 15 active seconds and 75% of the continuation text seen. These behavior labels would train the first model."
        )
    )
    story.append(
        p(
            "<b>3. Epsilon-greedy selection and online training.</b> In a live pilot, start with the model trained on internal feedback. Explore heavily at first. Once stable, show the highest-scoring promo 80% of the time and choose randomly 20%. Log each outcome and selection probability. Update daily, giving older feedback less weight. Compare qualified continuation against a separate random control. The prototype simulates this loop with per-promo estimates and held-out validation."
        )
    )
    heading("How it would scale")
    story.append(
        p(
            "Process episodes in parallel, cache by source, prompt and model, and prune similar cuts before critique. Track uncached token use, cost and coverage per show. Collect feedback on real footage, evaluate on later data and compare the updated policy with a randomized control before rollout."
        )
    )

    story.append(PageBreak())
    story.append(p("SYNTHETIC LEARNING / FULL-PACK EVALUATION", small=True))
    story.append(Paragraph("Feedback loop and results", styles["TitleLab"]))
    story.append(
        Image(
            str(ROOT / "docs/images/feedback-loop.png"),
            width=175 * mm,
            height=99 * mm,
            kind="proportional",
        )
    )
    heading("What I checked")
    usage = [(entry.get("response") or {}).get("usage", {}) for entry in result["model_journal"]]
    tokens = sum(item.get("total_tokens", 0) for item in usage)
    uncached = sum(not entry.get("cached", False) for entry in result["model_journal"])
    rows = [
        ["Check", "Observed result"],
        [
            "Input coverage",
            f"{summary['episodes']} episodes and {summary['events']:,} timestamped events",
        ],
        [
            "Candidate search",
            f"{summary['candidates']:,} generated, {summary['valid_candidates']:,} source-valid, {summary['distinct_candidates']:,} distinct",
        ],
        [
            "Shortlist",
            f"{summary['shortlisted']} selected from {summary['ai_assessed']} AI-assessed candidates"
            if result["mode"] != "offline"
            else f"{summary['shortlisted']} selected by the offline rules",
        ],
        [
            "Model usage",
            f"{summary['ai_calls']} logical calls ({uncached} uncached) and {tokens:,} reported tokens, including cached responses",
        ],
        [
            "Fixed-window baseline",
            f"n={evaluation['baseline']['count']}, valid {rate(evaluation['baseline']['valid_rate'])}, dialogue cuts {rate(evaluation['baseline']['dialogue_cut_rate'])}",
        ],
        [
            "Selected cuts",
            f"n={evaluation['shortlist']['count']}, valid {rate(evaluation['shortlist']['valid_rate'])}, dialogue cuts {rate(evaluation['shortlist']['dialogue_cut_rate'])}",
        ],
    ]
    evidence = Table(
        [[p(clean(value), small=True) for value in row] for row in rows],
        colWidths=[46 * mm, 129 * mm],
        hAlign="LEFT",
    )
    evidence.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PAPER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LINEBELOW", (0, 0), (-1, -1), 0.35, colors.HexColor("#dde2d5")),
            ]
        )
    )
    story.append(evidence)
    story.append(Spacer(1, 6))
    story.append(
        p(
            "The audit rechecks source intervals and artifact hashes. The baseline starts at each episode's first spoken line and takes about 30 seconds. This comparison checks cut boundaries. Audience preference requires a controlled study."
        )
    )
    if result.get("partial"):
        story.append(
            p(
                "Provider availability limited AI coverage. The exports identify affected episodes and candidates.",
                small=True,
            )
        )
    elif (
        result["mode"] != "offline"
        and summary.get("ai_assessed_episodes", summary["ai_assessed"]) < summary["episodes"]
    ):
        story.append(
            p(
                "Some critiques failed source-evidence or candidate-ID validation and were excluded from the shortlist.",
                small=True,
            )
        )

    shortlist = [candidate for candidate in result["candidates"] if candidate["shortlisted"]]
    if shortlist:
        sample = min(shortlist, key=lambda candidate: candidate["duration_seconds"])
        spans = ", ".join(
            f"EP {item['episode_number']} {item['start']}-{item['end']}"
            for item in sample["segments"]
        )
        heading("An example recommendation")
        story.append(
            p(
                f"<b>{clean(sample['title'], 110)}</b> | {clean(spans)} | {sample['duration_seconds']:.2f}s | rank {sample.get('rank', '-')}<br/><b>Hook</b> {clean(sample['assessment']['hook'], 150)}<br/><b>Ending</b> {clean(sample['assessment']['cliffhanger'], 150)}",
                small=True,
            )
        )

    heading("Where it fails")
    invalid_proposal = next(
        (
            candidate
            for candidate in result["candidates"]
            if candidate["origin"] == "llm_proposal" and not candidate["validation"]["valid"]
        ),
        None,
    )
    if invalid_proposal:
        spans = ", ".join(
            f"EP {item['episode_number']} {item['start']}-{item['end']}"
            for item in invalid_proposal["segments"]
        )
        reasons = ". ".join(invalid_proposal["validation"]["errors"])
        story.append(
            p(
                f"<b>Observed AI error.</b> The model proposed a {invalid_proposal['duration_seconds']:.2f}-second cut ({clean(spans)}). The source check rejected it. {clean(reasons, 180)}. The original response remains in the raw outputs."
            )
        )
    elif result["rejected_proposals"]:
        reason = clean(result["rejected_proposals"][0]["reason"], 220)
        story.append(
            p(
                f"<b>Observed AI error.</b> One proposal failed validation for this reason: {reason}. The raw output retains the original response."
            )
        )
    story.append(
        p(
            "A model can mistake missing context for suspense or infer details from speaker labels. Reviewing one finalist per episode can miss better cuts. Acting, visual joins and frame-accurate timing need a footage review."
        )
    )

    heading("AI tools used")
    story.append(
        p(
            f"Codex assisted implementation, tests and writing. The reported run used {clean(result['model'] or 'offline rules')}. OpenRouter Nemotron was checked on the original public example. ImageGen created both diagrams. Saved run {clean(run_dir.name)}.",
            small=True,
        )
    )

    output.parent.mkdir(parents=True, exist_ok=True)

    def decorate(canvas, doc):
        width, height = A4
        canvas.setFillColor(ACCENT)
        canvas.rect(0, height - 7 * mm, width, 7 * mm, fill=1, stroke=0)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(
            15 * mm, 12 * mm, "PROMO LAB / KUKU AI GENERALIST ASSIGNMENT / CONFIDENTIAL"
        )
        canvas.drawRightString(width - 15 * mm, 12 * mm, f"{doc.page} / 2")

    with NamedTemporaryFile(
        dir=output.parent, prefix=f".{output.stem}-", suffix=".pdf", delete=False
    ) as temporary:
        draft = Path(temporary.name)
    try:
        doc = SimpleDocTemplate(
            str(draft),
            pagesize=A4,
            rightMargin=15 * mm,
            leftMargin=15 * mm,
            topMargin=14 * mm,
            bottomMargin=20 * mm,
            title="Promo Lab - Solution",
            author="Assignment applicant",
            pageCompression=1,
        )
        doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
        pages = len(PdfReader(draft).pages)
        if pages != 2:
            raise ValueError(f"Expected exactly two pages, generated {pages}")
        draft.replace(output)
    finally:
        draft.unlink(missing_ok=True)
    print(f"Created {output.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=ROOT / "output/runs/full-pack-qwen")
    parser.add_argument("--output", type=Path, default=ROOT / "output/pdf/promo-lab-solution.pdf")
    args = parser.parse_args()
    build(args.run, args.output)

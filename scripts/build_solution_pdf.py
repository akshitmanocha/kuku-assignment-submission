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
)


ROOT = Path(__file__).resolve().parents[1]
INK = colors.HexColor("#202b26")
MUTED = colors.HexColor("#606b62")
ACCENT = colors.HexColor("#d5f16b")


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


def build(run_dir: Path, output: Path, *, public: bool = False) -> None:
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
    story.append(p("SYNTHETIC LEARNING / SCRIPT ANALYSIS RESULTS", small=True))
    story.append(Paragraph("Feedback loop and results", styles["TitleLab"]))
    story.append(
        Image(
            str(ROOT / "docs/images/feedback-loop.png"),
            width=175 * mm,
            height=99 * mm,
            kind="proportional",
        )
    )
    heading(f"From {summary['episodes']} episodes to {summary['shortlisted']} promos")
    selection = (
        f"The AI successfully scored {summary['ai_assessed']} finalists, at most one per episode. "
        if result["mode"] != "offline"
        else "The offline rules scored the possible clips. "
    )
    story.append(
        p(
            f"I ran the tool on the supplied scripts. Of {summary['candidates']:,} possible clips, "
            f"{summary['valid_candidates']:,} passed the script and timing checks. Grouping near-duplicates "
            f"left {summary['distinct_candidates']:,} distinct clips. The {result['config']['shortlist_percent']:g}% target "
            f"gave {summary['target_shortlist']} slots after rounding up. {selection}"
            f"The tool recommended the {summary['shortlisted']} highest-ranked clips that met the scoring rules."
        )
    )
    if result.get("partial"):
        story.append(
            p(
                "The AI service was unavailable for parts of the run. The exports show which clips it missed.",
                small=True,
            )
        )

    heading("How I checked the recommendations")
    baseline, recommended = evaluation["baseline"], evaluation["shortlist"]
    story.append(
        p(
            "I checked that the timestamps matched the script, the clips lasted 20-60 seconds and no lines were cut short. "
            "For comparison, I took roughly 30 seconds from each episode's first spoken line. "
            f"{baseline['valid_count']} of those {baseline['count']} clips passed, and {baseline['dialogue_cut_count']} cut a line short. "
            f"Of the {recommended['count']} recommendations, {recommended['valid_count']} passed "
            f"and {recommended['dialogue_cut_count']} cut a line short. Viewer interest still needs to be measured in the feed."
        )
    )

    shortlist = [candidate for candidate in result["candidates"] if candidate["shortlisted"]]
    if shortlist and not public:
        sample = min(shortlist, key=lambda candidate: candidate["duration_seconds"])
        spans = ", ".join(
            f"episode {item['episode_number']}, {item['start']} to {item['end']}"
            for item in sample["segments"]
        )
        heading("An example recommendation")
        story.append(
            p(
                f"<b>{clean(sample['title'], 110)}</b> is a {sample['duration_seconds']:.2f}-second promo "
                f"from {clean(spans)}.<br/>"
                f"<b>Early hook</b> {clean(sample['assessment']['hook'], 150)}<br/>"
                f"<b>Closing line</b> {clean(sample['assessment']['cliffhanger'], 150)}"
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
    if public:
        if invalid_proposal and not invalid_proposal["validation"]["checks"]["duration"]:
            story.append(
                p(
                    f"<b>Observed AI error.</b> The model suggested a {invalid_proposal['duration_seconds']:.2f}-second clip. "
                    "The tool rejected it because a promo must last 20-60 seconds."
                )
            )
        elif invalid_proposal or result["rejected_proposals"]:
            story.append(
                p(
                    "<b>Observed AI error.</b> The tool rejected a proposed clip that failed validation."
                )
            )
    elif invalid_proposal:
        spans = ", ".join(
            f"episode {item['episode_number']}, {item['start']} to {item['end']}"
            for item in invalid_proposal["segments"]
        )
        reasons = ". ".join(invalid_proposal["validation"]["errors"])
        story.append(
            p(
                f"<b>Observed AI error.</b> The model suggested a {invalid_proposal['duration_seconds']:.2f}-second clip "
                f"from {clean(spans)}. The tool rejected it. {clean(reasons, 180)}."
            )
        )
    elif result["rejected_proposals"]:
        reason = clean(result["rejected_proposals"][0]["reason"], 220)
        story.append(
            p(
                f"<b>Observed AI error.</b> The tool rejected a clip suggested by the model. {reason}."
            )
        )
    story.append(
        p(
            "The model can mistake a confusing ending for suspense. Scoring one finalist per episode can miss a stronger clip. An editor still needs to watch the footage to check performances and transitions."
        )
    )

    heading("AI tools used")
    run_note = "" if public else f" Saved run {clean(run_dir.name)}."
    story.append(
        p(
            f"Codex assisted implementation, tests and writing. The reported run used {clean(result['model'] or 'offline rules')}. OpenRouter Nemotron was checked on the original public example. ImageGen created both diagrams.{run_note}",
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
        edition = "PUBLIC SUMMARY" if public else "CONFIDENTIAL"
        canvas.drawString(
            15 * mm, 12 * mm, f"PROMO LAB / KUKU AI GENERALIST ASSIGNMENT / {edition}"
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
    parser.add_argument("--output", type=Path)
    parser.add_argument("--public", action="store_true", help="Omit private screenplay excerpts")
    args = parser.parse_args()
    default_name = "promo-lab-public.pdf" if args.public else "promo-lab-solution.pdf"
    build(args.run, args.output or ROOT / "output/pdf" / default_name, public=args.public)

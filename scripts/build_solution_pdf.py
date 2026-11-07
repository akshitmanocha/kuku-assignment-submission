"""Render a two-page solution document from an actual saved run, never fake metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak


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
    s, e = result["summary"], result["evaluation"]
    ai = result["mode"] != "offline"
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="BodyLab",
            fontName="Helvetica",
            fontSize=9,
            leading=12.4,
            textColor=INK,
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallLab",
            fontName="Helvetica",
            fontSize=8,
            leading=10.8,
            textColor=MUTED,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="HeadingLab",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=INK,
            spaceBefore=10,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TitleLab",
            fontName="Helvetica-Bold",
            fontSize=27,
            leading=32,
            textColor=INK,
            spaceAfter=7,
        )
    )
    story = []

    def p(text, small=False):
        return Paragraph(text, styles["SmallLab" if small else "BodyLab"])

    def heading(text):
        story.append(Paragraph(text, styles["HeadingLab"]))

    def rate(value):
        return "not measured" if value is None else f"{100 * value:.1f}%"

    def table(rows, widths):
        t = Table(
            [[p(clean(v), small=True) for v in row] for row in rows],
            colWidths=widths,
            hAlign="LEFT",
        )
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), PAPER),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.35, colors.HexColor("#dde2d5")),
                ]
            )
        )
        return t

    story.append(p("PROBLEM 1 / FIND THE PROMOS", small=True))
    story.append(Paragraph("Find the moment.", styles["TitleLab"]))
    story.append(
        p(
            "<b>Promo Lab</b> turns timestamped screenplays into a ranked, source-grounded editorial shortlist. It recommends cuts; it does not generate video or claim proven ad performance."
        )
    )
    heading("Why this problem; what I assumed")
    story.append(
        p(
            "The supplied scripts make the task testable: an editor can inspect exact intervals and their evidence. I chose a narrow, rerunnable workflow over training an audience predictor without labels. Times are episode-relative. Camera, action and dialogue overlap; their durations cannot be added. Promos total 20-60 seconds. Assemblies are chronological, capped at three segments, and require human visual review."
        )
    )
    heading("The working pipeline")
    story.append(
        p(
            "<b>1. Parse and preserve.</b> Normalize field case, retain stable source IDs and hashes, and flag questionable speech timing. Reject malformed inputs instead of silently losing episodes."
        )
    )
    story.append(
        p(
            "<b>2. Search.</b> Enumerate dialogue/action boundaries within the duration limit. Generic AI mode requests up to three strongest-first proposals per episode, with a short previous-episode tail. Groq budget mode requests one within-episode proposal. Convert referenced event IDs to original timestamps; the model does not invent edit points."
        )
    )
    story.append(
        p(
            "<b>3. Validate and critique.</b> Code checks bounds, duration, chronology and dialogue crossing either cut. A separate newcomer prompt sees only the selected dialogue/actions, without summaries or proposal rationale. It assesses hook, comprehension, stakes, progression, cliffhanger and cut quality on 0-3 anchors. One finalist per episode is critiqued to constrain free-tier usage."
        )
    )
    story.append(
        p(
            "<b>4. Rank transparently.</b> Equal-weight scores are editorial estimates, not probabilities. Hook, comprehension and cliffhanger must each reach two. Group temporal variants at 0.5 IoU, then return up to the top 1% of distinct valid candidates; do not pad a failed quota. Only successfully AI-assessed cuts enter an AI shortlist."
        )
    )
    heading("What the editor gets")
    story.append(
        p(
            "Upload ZIP/TXT inputs or use the CLI. Each result includes ordered episode timestamps, duration, source hook/ending, unanswered question, rationale, checks and concerns. Inspect overlapping source tracks, every episode's coverage, actual failures and earlier runs. Export CSV or a private bundle of raw candidates, model calls, evaluation, source hashes and checksums."
        )
    )
    heading("A short recommendation from this run")
    selected = [c for c in result["candidates"] if c["shortlisted"]]
    if selected:
        c = min(selected, key=lambda candidate: candidate["duration_seconds"])
        spans = "; ".join(
            f"EP {x['episode_number']} {x['start']}-{x['end']}" for x in c["segments"]
        )
        story.append(
            p(
                f"<b>{clean(c['title'], 110)}</b><br/>{clean(spans)} | {c['duration_seconds']:.2f}s | rank {c.get('rank', '-')} | {c['score']}/100 editorial estimate"
            )
        )
        story.append(
            p(
                f"<b>Hook:</b> {clean(c['assessment']['hook'], 180)}<br/><b>Ending:</b> {clean(c['assessment']['cliffhanger'], 180)}",
                small=True,
            )
        )
    else:
        story.append(
            p(
                "No candidates passed the current gates. The run records abstention rather than inventing a recommendation."
            )
        )

    story.append(PageBreak())
    story.append(p("EVIDENCE / LIMITS / NEXT STEPS", small=True))
    story.append(Paragraph("Inspect the evidence.", styles["TitleLab"]))
    heading("Measured full-input execution")
    usage = [(entry.get("response") or {}).get("usage", {}) for entry in result["model_journal"]]
    tokens = sum(u.get("total_tokens", 0) for u in usage)
    fresh = sum(not entry.get("cached", False) for entry in result["model_journal"])
    rows = [
        ["Measure", "Observed result"],
        [
            "Input coverage",
            f"{s['episodes']} episodes; {s['events']:,} timestamped events; {s['source_minutes']} scripted minutes",
        ],
        [
            "Candidate search",
            f"{s['candidates']:,} cuts; {s['valid_candidates']:,} source-valid; {s['distinct_candidates']:,} distinct",
        ],
        [
            "Final shortlist",
            f"{s['shortlisted']} selected; {s['ai_assessed']} AI-assessed; target {s['target_shortlist']}",
        ],
        ["Provider", result["model"] or "Offline rules; no model called"],
        [
            "Logical model use",
            f"{s['ai_calls']} calls ({fresh} uncached); {tokens:,} response-reported tokens incl. cached responses",
        ],
        [
            "Fixed-window baseline",
            f"n={e['baseline']['count']}; validity {rate(e['baseline']['valid_rate'])}; dialogue cuts {rate(e['baseline']['dialogue_cut_rate'])}",
        ],
        [
            "Selected cuts",
            f"n={e['shortlist']['count']}; validity {rate(e['shortlist']['valid_rate'])}; dialogue cuts {rate(e['shortlist']['dialogue_cut_rate'])}",
        ],
    ]
    if ai:
        rows.insert(
            5,
            [
                "AI episode coverage",
                f"{s.get('ai_assessed_episodes', s['ai_assessed'])} / {s['episodes']} episodes; {'PARTIAL - provider unavailable' if result.get('partial') else 'no provider failure'}",
            ],
        )
    story.append(table(rows, [52 * mm, 128 * mm]))
    story.append(Spacer(1, 6))
    story.append(
        p(
            "Baseline: roughly 30 seconds from each episode's first spoken line, without boundary refinement. The filtered shortlist and baseline are different samples. These rates verify structural enforcement, not improved audience appeal. Human acceptance, independent opportunity recall and continuation remain unmeasured.",
            small=True,
        )
    )
    if (
        ai
        and not result.get("partial")
        and s.get("ai_assessed_episodes", s["ai_assessed"]) < s["episodes"]
    ):
        story.append(
            p(
                "All episode proposal/critique requests returned. Critiques failing source-evidence or candidate-ID validation were excluded, explaining the lower usable-assessment count.",
                small=True,
            )
        )
    if result.get("partial"):
        story.append(
            p(
                "Provider quota interrupted AI coverage. All source episodes were processed, but unassessed cuts were excluded from the AI shortlist. The failure and per-episode coverage are exported; cached calls support resuming later.",
                small=True,
            )
        )
    heading("What failed; what AI got wrong")
    # Find an actual proposal rejected by technical validation, not an invented anecdote.
    bad_ai = next(
        (
            c
            for c in result["candidates"]
            if c["origin"] == "llm_proposal" and not c["validation"]["valid"]
        ),
        None,
    )
    if bad_ai:
        spans = "; ".join(
            f"EP {x['episode_number']} {x['start']}-{x['end']}" for x in bad_ai["segments"]
        )
        story.append(
            p(
                f"<b>Observed AI error:</b> proposal {clean(bad_ai['id'])} ({clean(spans)}) failed: {clean('; '.join(bad_ai['validation']['errors']), 200)}. Code retained the raw proposal but excluded it from selection. Source references alone do not make a proposed cut valid."
            )
        )
    elif result["rejected_proposals"]:
        bad = result["rejected_proposals"][0]
        story.append(
            p(
                f"<b>Observed AI error:</b> a proposal was rejected because {clean(bad['reason'], 250)}. The original response and rejection are retained for inspection."
            )
        )
    elif ai:
        story.append(
            p(
                "No malformed AI proposal was observed in this run. That does not establish semantic quality; I would not invent a model-error anecdote. The raw assessments should be inspected for context assumptions and overconfident cliffhanger judgments."
            )
        )
    else:
        story.append(
            p(
                "No inference model was called in this offline run, so there is no observed editorial-model error to report. The rules can reward a rhetorical question even when its answer is already present. Implementation AI also needed correction when a first source-header regex placed the colon outside the bold marker."
            )
        )
    story.append(
        p(
            "A question can mean confusion rather than suspense; source role labels can reveal information a viewer never hears. Text cannot establish acting, frame-accurate timing, visual joins or conversion. One critique per episode may miss a better cut. Temporal grouping can leave semantic duplicates. Keep a human editor in the final decision."
        )
    )
    disagreements = [
        c for c in selected if c.get("rules_assessment", {}).get("scores", {}).get("hook", 3) < 2
    ]
    if disagreements:
        story.append(
            p(
                "Some selected openings scored strongly with AI despite weak rule-based hook cues. The interface flags this disagreement; high scores are not a substitute for reviewing the first three seconds.",
                small=True,
            )
        )
    heading("Rerun, feedback, and future learning")
    story.append(
        p(
            "README run steps support new uploads and swappable server-side providers. Cache by content, prompt and model; process episodes independently. Quadratic boundary search needs pruning for larger inputs. Tests and isolated browser checks support reruns; logged free-tier usage does not establish production cost."
        )
    )
    story.append(
        p(
            "Implemented: a consent-based randomized text feed logs real reading/continuation, with unknown outcomes preserved. A separate, labeled synthetic demo fits candidate success estimates, holds out validation data and updates epsilon-greedy daily against random control. It tests mechanics under assumed appeal, not customer lift. Real video labels, embedding-based training, production rollout and contrastive learning remain future work."
        )
    )
    heading("Tools and confidentiality")
    story.append(
        p(
            f"Codex assisted code, tests and drafting; {clean(result['model'] or 'no inference provider')} supplied this run's editorial inference. Applicant review and understanding remain essential. Confidential scripts, raw outputs, caches and credentials are Git-ignored; submit private materials only through the authorized assignment channel. This PDF records run {clean(run_dir.name)}.",
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

    doc = SimpleDocTemplate(
        str(output),
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
    try:
        from pypdf import PdfReader

        pages = len(PdfReader(output).pages)
        if pages != 2:
            raise ValueError(
                f"Expected exactly two pages, generated {pages}; revise layout before submission"
            )
    except ImportError:
        pass
    print(f"Created {output.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=ROOT / "output/runs/full-pack-qwen")
    parser.add_argument("--output", type=Path, default=ROOT / "output/pdf/promo-lab-solution.pdf")
    args = parser.parse_args()
    build(args.run, args.output)

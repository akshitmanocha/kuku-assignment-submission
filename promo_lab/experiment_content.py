"""Frozen text stimuli from original fiction or an existing source-validated run.

This module never generates audience response labels or calls an AI provider.
"""

from hashlib import sha256
from pathlib import Path
import re

from .domain import Episode, Event, load_path
from .pipeline import make_candidate, segment, selected_events

CONTENT_VERSION = "public-reading-v1"

FILLERS = [
    (
        "The spare key",
        "Slice of life",
        [
            "For three years, Nina had watered the plant outside apartment 4B. She had never met its owner.",
            "One morning the plant was gone. In its place sat a small envelope: a key and a note saying, 'The balcony gets better light. Would you mind?'",
            "Nina knocked before trying the lock. From inside, someone laughed. 'Finally. I thought that plant would have to introduce us forever.'",
        ],
        [
            "The owner was an elderly illustrator who had drawn the plant each morning. She showed Nina a folder of sketches, each including a little of Nina's sleeve or the corner of her watering can.",
            "They began having tea on Sundays. The plant moved back outside the door, because both agreed the hallway needed an excuse for people to stop.",
            "Years later, a new neighbor arrived with a drooping fern. Nina fetched a second watering can.",
        ],
    ),
    (
        "Platform nine",
        "Small mystery",
        [
            "The station clock had been seven minutes slow for as long as Arun could remember. Every commuter complained; nobody fixed it.",
            "Then the clock was replaced. On his first punctual morning, Arun missed the woman who sold tea under it.",
            "Her stall carried a handwritten sign: 'Back in seven minutes.' He finally sat down to wait.",
        ],
        [
            "When she returned, she admitted the old clock had belonged to her father. He had set it slow so people would stop rushing long enough to drink their tea.",
            "Arun asked whether she would change the sign now. 'No,' she said. 'Some things should take as long as they take.'",
            "The following week, Arun began arriving early. He stopped checking which clock was right.",
        ],
    ),
    (
        "A recipe for rain",
        "Comfort",
        [
            "The village bakery offered a discount every time it rained. In a dry summer, customers began discussing ways to fool its owner.",
            "A teenager brought a watering can. A grandfather played thunder on his phone. Neither worked.",
            "Then a little girl drew a cloud on the window. The baker looked at it for a long time and brought out the cinnamon rolls.",
        ],
        [
            "The drawing reminded the baker of the clouds his sister painted when they were children. He gave the girl a box of chalk and asked for a whole sky.",
            "By closing time, the window was full of weather. Customers had added snow, wind and one very uncertain rainbow.",
            "The sign changed the next day: 'Discount whenever you make someone smile.' Nobody needed to check the forecast.",
        ],
    ),
    (
        "The last rehearsal",
        "Music",
        [
            "Leah could play every note of the audition piece except its final chord. Her teacher suggested practicing everything before it in silence.",
            "For a week she tapped the rhythm on bus windows and imagined the sound. At the audition, the piano's highest key stuck.",
            "She paused, changed the ending, and played a chord she had never practiced. The room stayed quiet after her hands lifted.",
        ],
        [
            "The panel asked why she had changed the ending. Leah pointed to the stuck key and apologized.",
            "One judge shook his head. 'I heard someone listening instead of reciting.' He asked her to play the new ending again.",
            "She did not get every scholarship she applied for. But she began writing music that left room for mistakes.",
        ],
    ),
    (
        "Borrowed sunlight",
        "Travel",
        [
            "The hostel had one sunny chair and twelve guests. Someone taped a booking sheet to it, with twenty-minute slots.",
            "By noon, the sheet contained an argument in four languages. By evening, a carpenter staying upstairs had disappeared with the chair.",
            "He returned carrying a bench. The booking sheet became a list of names for tomorrow's picnic.",
        ],
        [
            "Nobody agreed on where the picnic should be. They packed food from six countries and walked until the youngest guest found a patch of sunlight big enough for everyone.",
            "The carpenter took a photograph of the empty bench before they left. On its back, he wrote the names from the booking sheet.",
            "The hostel still had very little sunlight. Somehow, nobody minded.",
        ],
    ),
    (
        "The wrong package",
        "Comedy",
        [
            "Sam ordered a desk lamp and received a box of rubber ducks. Customer support offered a refund, but asked him to keep the ducks.",
            "He placed one on the office printer. By Friday, colleagues had named it and formed a committee to discuss its career.",
            "When the lamp finally arrived, Sam found a tiny paper promotion letter beside the printer. The duck was now head of operations.",
        ],
        [
            "The duck's first achievement was a rule requiring everyone to refill the paper tray. Its second was getting Sam to leave work on time.",
            "A month later the printer broke. The committee moved the duck to the coffee machine while repairs were arranged.",
            "Nobody could explain whether office productivity improved. The coffee queue was certainly friendlier.",
        ],
    ),
    (
        "A map in pencil",
        "Adventure",
        [
            "The map showed a bridge that no longer existed. Inez almost turned back, until she noticed a fresh pencil line leading upstream.",
            "She followed it to a fallen tree and crossed carefully. On the far bank stood a weatherproof box full of pencils.",
            "Inside the lid, someone had written: 'Leave the map better than you found it.'",
        ],
        [
            "Inez added a warning about loose stones and drew the place where wildflowers covered the path. She signed with a small star rather than her name.",
            "On her next visit, the map had three new routes and a sketch of a dog beside the old bridge.",
            "She never met its other authors. Their pencil marks made the mountain feel less lonely.",
        ],
    ),
    (
        "Closing time",
        "Slice of life",
        [
            "At six each evening, the bookshop owner turned the sign to closed. At six-oh-one, her dog brought the sign back to open.",
            "She blamed a loose hook until a customer filmed the dog using its nose. The next evening she hid the sign.",
            "The dog carried a book to the door instead. It was a guide to training difficult humans.",
        ],
        [
            "The owner began taking the dog for a walk before closing. It turned out the evening argument was about missing the busy street, not selling books.",
            "She put a bench outside and spent ten minutes there each night. Regular customers began joining them.",
            "The sign stayed closed. The conversations did not.",
        ],
    ),
]

FOLLOWUP = [
    "Mara turned the key. Inside the cabinet was an old answering machine, its speaker tapping against the wooden shelf. A red light blinked beside a cassette labeled with her name.",
    "Her mother's recorded voice filled the room. 'If Eli lets you hear this, he has finally stopped trying to protect me. The signature on the transfer is mine. The name beneath the fold is the one you must not trust.'",
    "Mara unfolded the last corner of the document. The witness was the hospital administrator. She remembered him calling every week, always asking whether her mother had spoken to anyone outside the family.",
    "Eli placed an envelope on the desk. It contained the hospital's original invoices and photographs of their mother leaving by a side door. 'She found out they were taking money from patients who had already paid,' he said. 'She needed somewhere they could not find her.'",
    "The stranger on the phone interrupted. 'She is safe for now. But the person who bought the house has arrived, and they know someone opened the cabinet.' Outside the office, a key began to turn in the lock.",
]


def units(texts: list[str], prefix: str) -> list[dict]:
    result = []
    for text in texts:
        words = text.split()
        # Readable blocks also make visible-text coverage measurable on small screens.
        for offset in range(0, len(words), 65):
            result.append(
                {"id": f"{prefix}-{len(result) + 1}", "text": " ".join(words[offset : offset + 65])}
            )
    return result


def public_demo_cards() -> tuple[list[dict], list[dict]]:
    ep = load_path(Path(__file__).parent / "examples" / "episode-001.txt")[0]
    episodes = {ep.id: ep}
    promos = []
    for start_ms, end_ms, title in [
        (0, 31000, "The transfer"),
        (22000, 56000, "The witness"),
        (48000, 80000, "The cabinet"),
    ]:
        first = next(e for e in ep.events if e.start_ms == start_ms and e.kind == "dialogue")
        last = next(e for e in ep.events if e.end_ms == end_ms and e.kind == "dialogue")
        candidate = make_candidate(
            episodes, [segment(ep, first, last)], "experiment_public_demo", 20000, 60000
        )
        events = [
            e
            for e in selected_events(episodes, candidate["segments"])
            if e["kind"] in {"dialogue", "action"}
        ]
        text = [
            f"{e['label'].split('(')[0].strip().title()}: {e['text']}"
            if e["kind"] == "dialogue"
            else e["text"]
            for e in events
        ]
        tail = [
            f"{e.label.split('(')[0].strip().title()}: {e.text}" if e.kind == "dialogue" else e.text
            for e in ep.events
            if e.start_ms >= end_ms and e.kind in {"dialogue", "action"}
        ]
        visible_units = units(text, candidate["id"])
        continuation = units(tail + FOLLOWUP, f"{candidate['id']}-next")
        promos.append(
            {
                "id": candidate["id"],
                "kind": "promo",
                "title": title,
                "genre": "Family mystery",
                "units": visible_units,
                "continuation": continuation,
                "features": {
                    "source": "original_public_demo",
                    "source_hash": ep.source_hash,
                    "source_duration_seconds": candidate["duration_seconds"],
                    "segments": candidate["segments"],
                    "segment_count": 1,
                    "speaker_count": len(
                        {e["label"].split("(")[0] for e in events if e["kind"] == "dialogue"}
                    ),
                    "source_event_ids": [e["id"] for e in events],
                },
            }
        )
    fillers = [
        {
            "id": f"filler-{i + 1}",
            "kind": "filler",
            "title": title,
            "genre": genre,
            "units": units(text, f"filler-{i + 1}"),
            "continuation": units(followup, f"filler-{i + 1}-next"),
            "features": {"source": "original_public_filler"},
        }
        for i, (title, genre, text, followup) in enumerate(FILLERS)
    ]
    for card in promos + fillers:
        card["content_hash"] = sha256(
            "\n".join(u["text"] for u in card["units"]).encode()
        ).hexdigest()
        card["features"].update(
            {
                "title": card["title"],
                "genre": card["genre"],
                "content_hash": card["content_hash"],
                "text_word_count": sum(
                    len(re.findall(r"\b\w+\b", u["text"])) for u in card["units"]
                ),
                "text_unit_count": len(card["units"]),
                "content_version": CONTENT_VERSION,
            }
        )
    return promos, fillers


def cards_from_run(result: dict, run_id: str) -> list[dict]:
    """Use the saved shortlist with genuine subsequent script text as continuation.

    Endpoint-only cuts with no following source are omitted: inventing a sequel
    would change what a continuation click means. Original timestamps remain X
    features, not text-reading outcome durations.
    """
    episodes = {
        ep["id"]: Episode(**(ep | {"events": [Event(**e) for e in ep["events"]]}))
        for ep in result["episodes"]
    }
    ordered = sorted(episodes.values(), key=lambda ep: ep.number)
    candidates = [c for c in result["candidates"] if c["shortlisted"] and c["validation"]["valid"]]
    cards = []

    def text(event):
        label = event["label"].split("(")[0].strip().title()
        return f"{label}: {event['text']}" if event["kind"] == "dialogue" else event["text"]

    for candidate in candidates[:30]:
        events = [
            e
            for e in selected_events(episodes, candidate["segments"])
            if e["kind"] in {"dialogue", "action"}
        ]
        last = candidate["segments"][-1]
        end_episode = episodes[last["episode_id"]]
        following = []
        for ep in ordered:
            if ep.number < end_episode.number:
                continue
            for e in ep.events:
                if e.kind not in {"dialogue", "action"}:
                    continue
                if ep.id == end_episode.id and e.start_ms < last["end_ms"]:
                    continue
                following.append({"episode_id": ep.id, **e.__dict__})
                if sum(len(x["text"].split()) for x in following) >= 350:
                    break
            if sum(len(x["text"].split()) for x in following) >= 350:
                break
        if not following or not events:
            continue
        cid = candidate["id"]
        card = {
            "id": cid,
            "kind": "promo",
            "title": "An unfinished story",
            "genre": "Drama",
            "units": units([text(e) for e in events], cid),
            "continuation": units([text(e) for e in following], f"{cid}-next"),
            "features": {
                "source": "saved_analysis_run",
                "source_run_id": run_id,
                "source_hashes": {
                    s["episode_id"]: episodes[s["episode_id"]].source_hash
                    for s in candidate["segments"]
                },
                "source_duration_seconds": candidate["duration_seconds"],
                "segments": candidate["segments"],
                "segment_count": len(candidate["segments"]),
                "speaker_count": len(
                    {e["label"].split("(")[0] for e in events if e["kind"] == "dialogue"}
                ),
                "source_event_ids": [e["id"] for e in events],
                "continuation_source_event_ids": [e["id"] for e in following],
                "continuation_source_hashes": {
                    e["episode_id"]: episodes[e["episode_id"]].source_hash for e in following
                },
                "content_version": "saved-run-reading-v1",
            },
        }
        card["content_hash"] = sha256(
            "\n".join(u["text"] for u in card["units"]).encode()
        ).hexdigest()
        card["features"].update(
            title=card["title"],
            genre=card["genre"],
            content_hash=card["content_hash"],
            text_word_count=sum(len(re.findall(r"\b\w+\b", u["text"])) for u in card["units"]),
            text_unit_count=len(card["units"]),
        )
        cards.append(card)
    if not cards:
        raise ValueError(
            "This saved run has no shortlisted promos with available source continuation. Use the original demo or another run."
        )
    return cards

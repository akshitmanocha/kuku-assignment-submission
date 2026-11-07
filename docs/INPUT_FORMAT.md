# Screenplay input format

In **New analysis**, paste the contents of one UTF-8 `.txt` file, upload one or more `.txt` files, or upload a `.zip` containing them. The CLI also accepts a file, folder or archive. ZIP contents are read without extracting arbitrary archive paths. Choose the offline engine to keep processing on your computer.

The complete original fictional input is [episode-001.txt](../promo_lab/examples/episode-001.txt). Preserve its header structure when preparing a new input:

```text
EPISODE NUMBER: Episode 1
EPISODE LOGLINE: An original story

SCENE 01
Scene heading: INT. OFFICE - DAY
Scene start: 00:00.00
Scene end: 00:30.00

**MARA (Worried):**
Start: (00:00.00) | End: (00:04.00)
The account was emptied this morning.
```

This is a partial four-second example; use the complete example for action/camera/sound entries and enough content for a 20–60-second promo. Speaker headers are bold and include the colon inside the closing bold marker. Each timing line contains `Start: (...) | End: (...)`. Metadata matching is case-insensitive. Episode numbers can also be inferred from names such as `episode-001.txt`; duplicate episode IDs are rejected.

Timestamps accept `MM:SS`, fractional seconds such as `01:02.35`, and hour-form `HH:MM:SS`. Times are episode-relative. Every event needs a positive start/end interval; malformed or missing event timing is rejected. Dialogue, action and camera tracks may overlap because they describe concurrent events. Promo duration is the selected timeline duration, not the sum of overlapping entries.

The prototype bounds upload size, archive expansion, episode/event counts and candidate search. Very dense episodes may exceed the 5,000 generated-interval limit; split them or narrow the CLI duration range. Script timestamps do not supply word alignment or frame-accurate footage cuts.

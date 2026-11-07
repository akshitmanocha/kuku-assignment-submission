# README image prompts

These two diagrams were generated with the built-in `image_gen` tool and approved by the repository owner on 7 November 2026. They illustrate the approach and the synthetic learning loop; they are not screenshots of a deployed audience system.

- `approach-overview.png`: three-part approach.
- `feedback-loop.png`: daily learning and selection in the synthetic demonstration.

The prompts below are retained verbatim for reproducibility.

## Image 1

```text
Use case: infographic-diagram.
Asset type: draft explanatory image for a GitHub README, awaiting owner approval.
Primary request: a beautifully clear, technically accurate, landscape infographic explaining the actual Promo Lab prototype to a non-specialist. Original flat editorial illustration, generous spacing, crisp typography, cream paper background, dark forest-green headings, restrained lime accents matching the app. Wide 16:9 composition, high-resolution legible text, clean arrows. No screenshots, private scripts, faces, fake numbers, or performance charts.
Main title verbatim: "Promo Lab"
Subtitle verbatim: "From screenplay to better promo selection"
Three equal-width columns connected left to right, each with a simple illustration (script and film strip, text story cards with anonymous feedback, and a feedback loop).
Column 1 heading: "1. Find promising promos"
Status: "Implemented"
Four steps verbatim: "Read scripts and timestamps", "Propose 20–60 second cuts", "Check hook, cliffhanger and source", "Rank a short list".
Column 2 heading: "2. Collect user feedback"
Status: "Reading pilot implemented"
Four steps verbatim: "Randomly show text cards", "Measure reading and continuation", "Save one row per exposure", "Build a dataset for training".
Column 3 heading: "3. Improve selection"
Status: "Synthetic demo; production planned"
Four steps verbatim: "Estimate success per promo", "Explore and exploit", "Update from new feedback", "Compare with random selection".
Footer verbatim: "Current learning demo uses synthetic responses. Live customer deployment is future work."
Use all provided words accurately, avoid extra claims, preserve distinction between real collection and synthetic learning. Professional documentation image, not a marketing poster.
```

## Image 2

```text
Use case: infographic-diagram.
Asset type: draft explanatory image for the same Promo Lab GitHub README, awaiting owner approval.
Primary request: a polished, plain-language landscape flow diagram with crisp editorial illustrations and highly legible labels explaining the implemented synthetic feedback loop. Cream paper background, forest-green text and thin connectors, restrained lime highlights matching Promo Lab, generous spacing, 16:9 landscape. No fake performance curve, no stock photos or private source content.
Title verbatim: "How the feedback loop works"
Prominent small subtitle verbatim: "Synthetic demonstration"
Draw the following exact logical flow with unambiguous arrows:
"Start with random examples" -> "Estimate each promo's success" -> decision branch labeled "After warm-up".
Two parallel branch boxes: "80%: Choose the current best" and "20%: Try a random promo".
Both branches merge into "Show the chosen promo", then "Observe continuation", then "Update estimates daily".
A clear return arrow from "Update estimates daily" back to "Estimate each promo's success" completes the loop.
A separate comparison lane is labeled "Separate random control" and leads to "Compare results". This lane must not have an arrow updating the model; it only provides a comparison.
Footer text verbatim: "Real feedback is collected separately. Synthetic results do not establish customer lift."
Second footer line verbatim: "Control and validation data do not train the model."
Keep labels accurate and readable without text crowding; no invented metrics or guarantee of improvement. Show that the loop is a working simulation, not an already deployed customer system.
```


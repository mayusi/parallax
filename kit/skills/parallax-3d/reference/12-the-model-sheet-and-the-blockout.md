<!-- reference for the parallax-3d route card: the two stages the owner approves before a piece is detailed (2026-11-11) -->

## The model sheet (stage 2) and the blockout (stage 4): the two cheap things the owner approves

The owner, 2026-11-11: "A concept sheet we really need ... block[out] approval." A studio's modeller builds from a
sheet the art director signed, and the big shapes are signed off while changing them costs seconds. The kit went
from a brief straight to a baked build: the first picture the owner saw was a finished model, a wrong proportion was
found under its details, and every fix was a full rebuild. Both stages are for a NEW complex / hero / aaa piece; a
prop needs neither, and a piece that existed on 2026-11-11 is exempt (`board/locks.json`, `grandfathered["3d-stages"]`).
Nothing here is drawn by hand: both pages are made from the files the gather stage and the shape round already leave.

### Stage 2 — the model sheet: `lune run kit sheet <asset>`
One page, `assets/models/<asset>.sheet.png` (+ `.sheet.json`), from the brief, the traced views and the pack:

- **VIEWS**: every traced view's own picture cropped to the object, the hero features boxed and numbered on it; a
  view a hero / aaa piece should have and does not (`NO FRONT VIEW TRACED`) is shown empty, in red.
- **HERO FEATURES**: one large callout per hero feature of the brief — its box from its picture, its route, its size
  in mm, its pixels per mm.
- **COLOUR PLAN** (kit/tools/colour_plan.py): EVERY colour of the pack (`kit pack <asset> colours`: the parts'
  measured colours) with its SHARE of the object in the side picture and the ROLE that gives it: MAIN (the
  largest), SECOND (every other colour from 12%), ACCENT (under 12% and standing out from the main: where the eye
  goes), minor; a colour this view does not show says 0%, a twin names its twin. The shares as one bar (the
  designer's rule of thumb is about 60 / 30 / 10), and the picture read in THREE GREYS - its own dark, middle and
  light families, with the one that leads (the squint test: detail gone, the big value shapes left; a tall
  object is laid on its side there; an object of two values has an empty family, said as "none"). It adds NOTES,
  never a refusal: no colour leads, no accent, a share at the line between accent and second, part of the object
  near no palette colour (the palette misses one), no value family leads, the piece is one value, two large
  parts that are ONE grey (only hue or gloss tells them apart - not at a distance, nor for a colour-blind
  player). The summary says it in a line (`colours: main body 55%, second barrel 21%, second grip 14%, accent
  strip 6%; values: dark leads 69%`) and `<asset>.sheet.json` keeps it (`colour_plan`). Read the three-grey
  picture yourself: two parts that must read apart and are one grey there are a design fault to fix on the
  palette before any build.
  WITHOUT measured colours the colours are SAMPLED off the object and get NO role (they are bands of the
  picture's shading, not parts): the sheet shows them with their shares, the three-grey read still holds, and
  the summary says `colours: sampled (no roles)` - measure the parts first.
  How it reads the picture: the OBJECT is what lies inside the view's traced outline (else a cut-out's opaque
  part, else what is off the picture's ground - and then it says "the ground is not plain: the shares are
  unsure" when the corners disagree or the border reads as object); a pixel is the palette colour whose SHADE it
  is nearest to (a colour in shadow is that colour; between a black part and the shadow of a grey one, the black
  part wins). It cannot know a white highlight on a dark part (it counts toward the nearest light colour, or
  "other"). No build is held to the plan yet.
- **SCALE** (a sourced length in the pack) and the **PARTS PLAN** (each part's stack, data and surface).

**It is refused (exit 6) while a hero feature cannot be modelled from its pictures**, each one named with its fix:
no picture · no box in its picture (`<picture> x0,y0,x1,y1`) · a picture that is not a file · no size in mm and no
scaled view to read it from · under 2 px per mm (ask the owner for a close-up — the Gjallarhorn's six hero features
were 1.0–1.5 px/mm in its one picture, and its wolf was modelled from a 275 px crop). Write the features properly in
the brief; the same boxes are what every build pairs with the model afterwards (`f_<n>_<feature>.png`, rule 8).

LOOK at the sheet yourself first, then SHOW it to the owner. His yes:
`lune run kit approve 3d <asset> "<his words>" --by owner --stage sheet`. It is recorded with the sheet's id (a hash
of everything the sheet shows: features, boxes, pictures, traces, palette): change any of it and `kit sheet` again —
the lock then asks for his word again. `kit asset` (any build, `--geo` included) refuses the piece without it.
`kit sheet <asset> --out <file.png>` draws a trial copy and leaves the asset's own sheet and its approval alone.

An ORIGINAL design gets its pictures before the sheet, by the tools: `kit design explore` (silhouettes) -> the owner's
pick -> `kit design concept` (side / front / top / three-quarter drawn from the pick) -> `kit trace` each view ->
the hero features boxed on them in the brief -> `kit sheet`.

### Stage 4 — the blockout: `lune run kit blockout <asset>`
Write the build script as a BLOCKOUT first: every part as its simplest solid (a box, a cylinder, a plain extrusion)
at the sheet's proportions, one `a.trace_match` per traced view, NO detail, bevel study, material work or stamps.
`kit blockout` runs the shape round (`kit asset <asset> --geo --blockout`: seconds, no bake, no export) and draws
`assets/models/<asset>.blockout.png` (+ `.blockout.json`):

- per traced view: the reference's object box | the model in CLAY from that picture's own camera at the picture's
  scale | the build's overlap picture with the overlap number against its bar (red when under it);
- six clay views (front, back, left, right, top, three-quarter): one matte colour, so nothing flatters the form;
- the model beside an R6 character (5 studs tall) and its size in studs.

Fix what the page shows wrong BEFORE showing it (a shape round costs seconds), then SHOW the owner. His yes:
`lune run kit approve 3d <asset> "<his words>" --by owner --stage blockout`. Without it `kit asset <asset>` (the
baked build) is refused; `--geo` rounds stay free. The approval is of THOSE proportions:

- it holds while the shape is detailed — the script changing does not stale it;
- a new model sheet does (another target needs another blockout);
- `kit blockout` on an approved blockout is refused unless `--again` (drawing it again replaces what he approved and
  needs his word again);
- a later build whose size moved more than 5% from the approved blockout says so: the `blockout_drift` warning.

Both stages show in `lune run kit plan <asset>` (stage 2 and stage 4, at most five commands each, the later stages
LOCKED until they are done) and in `kit help --stage 3d:sheet` / `3d:blockout`. A step the owner chooses to skip for
one piece: `lune run kit approve 3d <asset> "<his words>" --by owner --waive sheet` (or `blockout`).

Both pages hold crops of the reference pictures: a PRIVATE piece's sheet and blockout stay uncommitted with the
rest of the piece (rule 5); the `.sheet.json` / `.blockout.json` records name no picture content.

### Who asks for the approvals, and who does not
- Every command that BUILDS the piece asks: `kit asset` (any build: the sheet; a baked build: the blockout too),
  `kit watch` (the same, by its `--geo`), `kit fit` (shape rounds: the sheet), `kit optimize` (a baked build: both),
  `kit blockout` (the sheet).
- `kit verify` does not: a piece that waits for the owner's yes never turns the shared gate red for other sessions.
  `kit plan` shows the stage as open instead.
- `kit make` is let through for the script it writes itself (it gathers, builds and judges in one run, so no sheet
  can exist at its door); the first `kit asset` by hand on that piece asks for both. Making it stop at the two
  pages is the 3D plan's H3 (`board/plans/archive/2026-11-11-3d-studio-route-plan.md`).
- The plan and the lock read the same two things the same way: the tier is `aaa`, `hero` or `complex` anywhere in
  the brief's `- quality:` line, and a record is the owner's only by the rule of `kit/lib/locks.luau` (`by` starts
  with "owner"; a `who` that is not the owner cancels it).

---
name: parallax-ui
description: Build Roblox screens (HUDs, menus, shops, death screens, status sheets, dialogs) that look like ONE game and no other — identity-first. An identity pack (assets/ui/identities/<name>.json) decides tokens, type, shape language, drawn plates, motion and bans BEFORE any screen; screens are JSON specs compiled to Rojo models, gated (readability, touch, AI-tells), previewed with the REAL fonts at phone/tablet/desktop with motion strips, judged by a fresh reviewer for bugs and by the OWNER for quality, and driven in game by the kit Ui runtime (springs, choreographed enters, bar ghosts, rolling counters). Use for any UI/GUI task.
---

# parallax-ui — the route card (the detail is in `reference/`; the record is in `kit/knowledge/vault/ui/`)

Start: `lune run kit status --dept ui`, then `lune run kit ui plan <Screen>` — the stage board; `kit help --stage
ui:<stage>` prints the stage's ≤ 5 commands. Start from proof: `kit examples screen` (the owner's scores beside each;
Arcade5Title / Arcade5Menu / Arcade5Health 9.2, WitchGauge 8.5, FieldHud 8, WitchSmearCard 8).

## The clock and the route (the owner, 2026-11-10: "Yes, same budgets" - card b6m2)
- **The clock**: a piece gets 3D's budgets - 10 minutes simple, 30 complex, 60 hero (its spec's `"tier"`, a UI
  screen's `"quality"`; a screen is simple unless its `"quality"` says; hero only with `kit approve`). `kit ui <Screen>` starts it; `kit ui` (every screen) starts the clock of any screen new or changed since the last such build.
  A change is a change to what the piece is made of (its spec, the assets it names, a dossier's clip sources) -
  never a look's own output. Past the budget NO CHANGE builds (the piece as it was may still be played, looked
  at, rebuilt): show the owner what there is and its open cards; only his words reopen it: `kit clock ui
  <name> --extend <minutes> "<his words>"` or `--restart "<his words>"`.
- **The route**: its pieces' routes (render, trace, ink, letter, drawn, typed ...) and its identity pack. A piece made a NEW way (a way gained, not one dropped) refuses its build until
  `kit answer ui <name> --reroute` and every lesson is answered again for the new route (a copied answer
  does not count).

## Owner faults that are gates now (card qfab, 2026-11-10)
- **A HUD written as game code** (Sample Game's ChamberHud sizes itself at runtime, where no spec, compile or gauge
  sees it) keeps a size contract, `<root>assets/ui/huds/<Hud>.json`: its code's path, its own block helper and
  resize function, the reference's measured size of each block (the owner-approved round, with his words) and a
  floor. `kit ui hudsize` (and `kit verify`) runs the HUD's own code at 1920x1080 and desktop sizes and FAILS a
  block under floor x its reference. The owner's sg_hud5 3/10 ("what the hell, I told you not this small": R2 put
  every block at 0.58 of the 1080p design) is its selftest bad example. A smaller HUD only on his words, then
  re-measure the reference.
- **A realistic identity's bans as words**: `"banned_components"` fails a node whose TYPE is a banned word (a HUD
  component, or a base type such as `plate`) or whose NAME holds one inside one of its words (camel humps, `_` and
  digits split words: "map" is in Minimap, "hp" is not in FlashPrompt; "feed" is still in HitFeedback - name such a
  node otherwise); `"banned_components_grandfather"` keeps a listed screen at a warning. The field identity's words come from its own bans[] and the owner's FieldHud_v1
  verdict (he chose them, 2026-11-10): plate cutout chrome glow halo pill gloss + map feed hp rounds reserve. The
  real FieldHud_v1 (1/10, "AI slop, I asked realistic") is the selftest bad example. An identity's words are the
  owner's: show him the list before writing it.

## The owner's rules (every one has a date and a verdict behind it)
0. DIRECTION before identity (2026-10-24: "take my bullshit prompting and turn it into something out of this
   world"): `kit ui direct new <name> --ask "<their words, verbatim>" [--game G]` -> 3-5 directions, each an OBJECT of
   the game's world with a verb and one signature moment -> `check` -> `board` (sketch frames on the world shot) -> the
   OWNER picks (`pick ... --by owner` drafts the identity). A new identity is locked until then. `reference/12-*`.
1. Identity FIRST: tokens sampled from real stills by script, a font trio, shape language, motion, bans, minimums.
2. Real sources beat generated ones; the source is the ceiling: a 3D render through any filter is a splat; official
   2D key art through `kit ui ink --mode cel` reads at once; a prompt-made stand-in for a known character is slop.
3. Type is the grammar (Persona = a face per glyph, mixed case, tilt, overlap, ink outline + paper rim; realistic =
   condensed type with a soft edge); shapes carry the style (scissor cuts, three colours; chrome only in metal worlds).
4. Realistic means ABSENCE: report only what the player cannot feel; when the references show an absence, it is the design.
5. Measure, never guess (1:1 stills ≥ 1080p; judges read 50% sheets as screen pixels); the owner's eye outranks the
   median by 30-45 points; change the MEDIUM (render / letter / ink / spin) before polishing; show every round.
6. The library rule: everything the pipeline makes is saved in `library/ui/` (`kit verify` fails otherwise).

## The hero route (7 stages; `kit ui plan` locks each)
| # | Stage | Its gate | Read |
|---|---|---|---|
| 0 | direct | a NEW look: the owner picked one of 3-5 checked directions on `kit ui direct board` (older identities exempt) | `reference/12-*` |
| 1 | refs | ≥ 2 real stills of the EXACT screen type at ≥ 1080p, measured at 1:1 into REFS.md (never a gallery sheet, never a pasted contact sheet) | `reference/05-*` step 1 |
| 2 | identity | `kit ui identity <id> --from refs`: sampled tokens, fonts, shape, motion, bans, minimums, lettering defaults | `reference/05-*` step 2 |
| 3 | pieces | every hero piece rendered (`kit ui render`), traced (`trace`), inked (`ink`), lettered (`letter`) or spun (`spin`) — never a font glyph with a tint; the render reads its picture back | `reference/05-*` steps 3-4 |
| 4 | assemble | from anchors (`kit ui gauge`); `crest_width` sets the scale; children follow a warped parent; the spec compiles with its gates | `reference/06-*`, `07-*` |
| 5 | look | the sheet at phone / tablet / desktop + the motion strip LOOKED at, numbers sampled; `kit ui look` recorded (no look, no judge, no promote) | `reference/05-*` step 6 |
| 6 | judge | two fresh judges for BUGS (wrong state, empty flip face, "1 HITS"); the verifier's diff + one edit per piece; the OWNER's verdict (`kit verdict screen`) | `reference/05-*` step 7 |
| 7 | promote | `kit upload` (art not uploaded shows BLANK in game); `kit ui vault check`; `kit promote` only on an owner verdict ≥ 7 with render / trace / anchors / REFS | `reference/05-*` step 8 |

Gameplay motion: `kit ui reel <Screen>` renders `<Screen>.reel.json` to a GIF + strip (hits, ghost drains, rolling
counters); the engine proof is `kit ui booth <Screen>` (Studio). The spec's shape: `reference/07-*`; the runtime
(`ReplicatedStorage.kit.Ui`): `reference/09-*`; gates: `reference/10-*`; fonts: `reference/11-*`.

## What never worked (`kit/knowledge/vault/ui/graveyard.md`)
Typed glyphs + flat tints + PIL rectangles as a HUD ("genuine AI slop") · a FLUX stand-in for Heroine · a 3D
render through halftone ink · one display face for a Persona screen · ransom lettering for a LIST · torn plates
for P5 (scissor cuts instead) · re-scaling on a judge's word · tracing from a 760x940 gallery sheet (plateau 57-67)
· the arcade checklist in muted paint for "realistic" · PIL polish past a plateau.

## Traps (the full list: `lune run kit lessons ui`)
`imageAlpha` is TRANSPARENCY (0.85 = faint) · `size_x` is a scale share · plate names are reserved (frame, rays,
ribbon, grain, glow, vignette) · lettering keeps desktop pixels (one `at.<vp>.scale` per group; LOOK at phone +
tablet) · TextSize caps at 100 · a UIGradient tints children · keep the top-left 260x58 clear · no TTF, no
letter-spacing (glyph lists) · the preview's textGradient draws its first stop · a derived screen drops new nodes ·
a converted curve carries its own UV layer (bind a named UV Map; cards want `--exposure -0.8`) · SigLIP cannot find
faces in ink art · never carry an owner verdict onto a changed build (sha-keyed).

## Read next
`reference/02-the-owner-s-taste-*.md` · `reference/03-start-from-proof-*.md` · `reference/04-commands-at-a-glance-*.md`
· `kit/knowledge/vault/ui/index.md` · `board/plans/archive/ui-pipeline-state.md` · `[[shared/images]]`.

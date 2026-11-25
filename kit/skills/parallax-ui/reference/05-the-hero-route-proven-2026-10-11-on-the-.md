<!-- reference for the parallax-ui route card; verbatim from the skill page (2026-10-16) -->

## The hero route (proven 2026-10-11 on the character-action gauges and the Umbra gauge — follow it in this order)

A hero HUD is **art assembled by data**, never typed. Every round that skipped a step below was called "AI slop"
by the owner or scored under 50 by two fresh judges; every round that followed it moved the picture. `lune run kit
ui plan <Screen>` is this list as a stage board — run it first and after every stage.

1. **References before anything.** Two or more real stills of the HUD you are matching or drawing in the spirit
   of, into `assets/ui/refs/<identity>/`, measured at 1:1 into `REFS.md` (source URL, frame size, every piece's
   pixel box and sampled colour; scale them to 1080p). A gallery sheet is NOT a reference: its zoom is unknown and
   a trace cannot exceed its resolution (the five character-action gauges plateaued at 60-67 on a 760x940 sheet). Crop with the
   picture's own pixels, never a pasted contact sheet (one was 180 px off).
2. **Identity from the measurements.** `assets/ui/identities/<name>.json`: tokens sampled from the stills (the
   compiler flags the generic indigo accent), fonts, shape language, bans (write the other identities' tells in),
   `minimums`, and `references` with `image` + `measured` (they land in the judge packet as refs.png).
3. **Pieces by route — rendered or traced, by name:**
   - **Replica** → `kit ui trace <identity>/<piece> --from <still> --box x,y,w,h [--cutout] [--gauge] [--lift]`:
     the reference's own pixels, upscaled, matted, cells blanked and anchored. Boxes generous; `--cutout` on
     plates too; bad trace = retrace.
   - `imageAlpha` on images and plates is TRANSPARENCY (0.85 = faint, 0.5 = a wash) — a backdrop at 0.12 is nearly opaque.
   - **A character, a logo, a hero motif that EXISTS as a picture** (the owner's key art, an official render, a
     photo) → `kit ui ink <identity>/<piece> --from <picture> [--mode ink|cel] [--palette own|identity|mono]
     [--colors 6] [--line-px 3] [--rim 12] [--rim-ink 4] [--mid halftone|accent] [--dark .36] [--light .68]`: cut out, split into ink / mid / paper, the mid-tone as a halftone screen (or the
     accent flat), TEED lines, a paper rim — Persona's character art from a real picture, with a `.ink.json` sidecar.
     The owner: "grab a proper picture ... and make it like the Persona one" — a prompt-made stand-in for a
     character the owner can picture is the AI-slop tell; `kit ui plan` warns on it (the sources stage).
   - **Original** → `kit ui render <identity>/<piece>` (Blender): `text` items for logotypes (chrome_gold /
     silver / red / black_steel or a custom metal, horizon band, outline, glow), `ring` for energy strokes,
     `gauge` for the plate (troughs + caps; `cap`/`cap_left: "horn"`, `bow`, `taper`, `frame_pad`, per-row
     `cell`; custom `frame` metal; `wear_scale` ~50), `gem` for ONE glass cell per state (lit with a halo, unlit
     smoked). Painted motifs (a butterfly, a crest) → `kit vision concept ... --sheet single` → `kit vision
     cutout` → square-crop; prompt "flat, front-facing, clean game-UI illustration, no text".
   - The render reads its picture back and names the knob when it is off (a gem clipping to white, a pale plate,
     a clipped logotype) — act on `next_action`. A hairline guard clears stray glyph lines.
   - **Never** a font glyph with a flat tint or a PIL rectangle as a hero piece. The compiler warns on a hero
     screen with no art at all.
4. **Type is a piece too — never a font with a tint.** Display words (a logo, menu items, a shout) are written as
   text with `"lettering": true` (or overrides `{size, seed, scale, caps, shadow_color, ...}`); the `kit ui` words
   step bakes them into `art:<identity>/w_<slug>` with the identity's `"lettering"` defaults (`style: persona` = a
   face per glyph, mixed case, tilt, overlap, word outline + paper rim — the round the owner called "genuinely
   amazing"; `flat` = one face, ink outline, hard drop). A word re-bakes only when its recipe changes; live numbers
   stay real text. Baked art keeps its desktop pixels, so give each GROUP one `"at": {"phone": {"scale": 0.55},
   "tablet": {"scale": 0.72}}` — it shrinks the node and everything inside it — then LOOK at phone and tablet
   (the first lettered build collided there on both screens).
5. **Assemble from anchors.** `assets/ui/<Screen>.gauge.json` → `kit ui gauge <Screen>`: cells laid over the
   plate's wells from `<plate>.anchors.json`; `crest_width` (the measured crest in 1080p px) sets the scale, never
   the picture's zoom; `cells: {art_lit, art_unlit}` for rendered gems; `pips: {art_lit, art_unlit, count, lit}`
   for live pips; `nudge` to move a traced piece off a bad crop. **Children follow a warped parent:** a bowed
   holder's wells carry their tangent (`rot`) and every cell is placed by its centre and rotated to it. Size
   from the data: plate_width so a cell is ~12 px tall at 1080p for a thin bar, the character-action 30x14 for a chunky one.
6. **Look at every milestone, with numbers.** Compose a contact sheet (the pieces + the HUD corner of the preview
   at 1:1 or 4x) and LOOK; sample pixels by script (a plate's mean under ~90/255 reads as steel; a lit cell's
   max channel under 245). `kit ui look <Screen> "<what you saw>"` after each look — the packet refuses an
   unlooked build. Views cost (10/hour across judges): batch, crop tight, measure by script when a number will do.
7. **Judge by two, read the gaps, not the number.** `kit ui judge <Screen>` → two FRESH judges (Opus, medium;
   sheet.png and the real refs, nothing else) → `--record` both → the median. Two judges differ by ~5-10 and
   consecutive pairs contradicted each other on size (1.4x too big, then 1.25x too small): measure, never
   re-scale on a judge's word. The owner's eye outranks the median (the Umbra gauge: owner "genuinely
   impressed" at a 49.5 median). Fix located gaps in the order the judges agree on; one pair per round.
8. **Ship with the data.** `kit upload`; `kit promote screen <Screen>` carries the identity, the art AND its
   render / trace / anchors specs, PROVENANCE.md, the gauge spec and REFS.md (an example must rebuild); a
   lesson for anything a future model would have to rediscover; the handoff names the next gap.

Time: an original gauge from two stills to a judged screen took ~70 min; each owner correction ~25 min.
The owner's budgets (10 min prop, 30 complex, 1 h hero) are the pace — look at hour 1, never grind blind.

### A realistic HUD (FieldHud, 2026-10-12) — the quiet grammar, by the same route
- **References:** the genre's store shots show NO HUD (realistic shooters keep it minimal): keep one as the identity's
  `art/<identity>/world.png` (the preview backdrop — a sunlit frame is the hardest legibility case) and find a real
  HUD still on a wiki (`kit ui refs <id> "<game>" "HUD" --wiki <sub>`); measure it at 1:1 by script (numeral height,
  margins, bar height, minimap box and fill luma) and size the roles from those pixels.
- **Identity:** no plates, square corners, colour only as a signal (amber objective, blue friend, red damage),
  condensed sans (RobotoCondensed / Oswald / RobotoMono), every text with `"textOutline": "shadow"`; `rules` with
  `accent_share` near zero; bans that name the stylized identities' tells.
- **Icons:** `kit ui ink <id>/<piece> --from <side render> --mode icon` (outline + TEED interior lines + faint fill +
  a dark `--halo`), from the kit's own 3D builds (`build/renders/*side*`); an outline-only LOD (`--lines none
  --outline-px 7`) for 50 px uses. Drawn-by-script pieces (minimap, compass strip, view cone) live in `_scratch/ui_<id>/`.
- **Structure lifts the secondary blocks** (the judges' consistent read: "everything but the ammo is generic"):
  feed rows on faint strips with your kill edged, squad rows with per-mate bars, armour plates, hollow spent rounds,
  a faint dark backing under any small text over a warm scene (three judges read white-on-sand as red).
- A picture that IS content (a minimap) carries `"attributes": {"Kit_Content": true}` so the empty-panel check counts it.

### Round 3 — "the font and the visuals look ugly, not Persona" (owner, 2026-10-11): the LETTERING is the grammar
- **`kit ui letter <identity>/<piece> --style persona --text "WORD"`**: every glyph its own face from a pool (Cinzel
  black, Oswald bold, Luckiest Guy, EB Garamond, Montserrat black + italic, Roboto Condensed black, Michroma), mixed
  case (the first letter a big capital), each glyph resized, tilted (`--wobble 7`), lifted off the baseline and
  tucked under its neighbour (`--overlap 0.06`); spacing by each glyph's INK; then ONE thick ink outline around the
  whole word (`--outline 0.07`) and a thin paper rim outside it (`--rim-px 4`). A logo: `--caps --rim-px 0 --shadow
  0.08 --shadow-color <accent>` (an ink drop vanishes on black). One face (Bangers) for everything read as a comic,
  not Persona. Words are baked as art (buttons with `text: ""` and the word as an image child); live numbers stay text.
- **Plates of the grammar**: `tear_band` (a long torn strip in two tones — the tint gives the accent and a darker
  accent) over `tear_fringe` (its white paper fringe, `color: paper`), `zebra` (hand-cut diagonal stripes, a stamp),
  `halftone` dots, `cut_*` splashes behind the selected item.
- **The figure is a black silhouette with sparse white and a paper rim** (`kit ui ink --mode cel --palette mono
  --dark 0.5 --light 0.72 --rim 9`), always on a loud ground (the band, an accent cut) — never on plain black.

### The owner's verdict on the first Persona-type title ("horrible") and what fixed it (2026-10-11)
1. **The figure's SOURCE decides everything.** A 3D render through any filter (halftone ink, cel-mono, two-tone,
   cleaned) was a splat every time. Official 2D key art (`kit ui refs <identity> "<game>" "<words>" --wiki <sub>`
   → keep the drawn full-body piece → `kit ui ink <identity>/<piece> --from <art> --mode cel --palette mono
   --clean 2`) read as an illustration on the first try. Pick a DRAWN picture; the render is for proportions only.
2. **Scissor cuts, not tears.** Persona's shapes are a few long straight runs with sharp corners: the `cut` family
   (`cut`, `cut_b`, `cut_c`, `cut_black`, `cut_field`, `cut_strip`). `torn` is pixel wobble — it reads as noise at
   field scale. The accent field = `cut_field` over an ink `cut_field` offset a few px (the double cut).
3. **Three colours.** Ink, paper, the one accent. The chrome logotype, the gold script and the grey crest were
   five materials on a three-colour grammar; the logo is `kit ui letter <identity>/<piece> --text ... --font
   bangers --shadow 0.09 --lean -5` (flat paper letters, ink outline, a hard drop). `--cards --wobble 6` = ransom.
4. **Layout from the measured still** (`kit ui measure`): the field high on the left falling to the bottom by 75 %,
   the logo top-left over the field's edge, the figure huge bottom-centre-right, the menu staircase ON the field
   lower-left (paper strips with ink type, the selected one inverted) — not floating on black (ink strips vanish).
5. **`plateColor`** on a label / button tints its plate and is its contrast ground; a list is whole-word strips
   (`cut_strip`), never ransom letters.

### What the kit does for you now (ideas 5-10 of `board/plans/archive/ui-pipeline-v4-ideas.md`, shipped 2026-10-11)
- **Composition gates** (`identity.rules`: `lean_min`, `lean_share`, `overlap`, `accent_share: [lo, hi]`, `hero_biggest`;
  `kit ui identity --from` writes them from the stills): the compiler measures the screen at 1920x1080 and warns
  `composition: ...` when the top blocks sit level, touch nothing, when the accent paints too little or too much
  (every tinted plate counted by its painted share, `opaque` in art.json), or when the biggest PICTURE (a file
  piece, painted area) is not the hero. A title names `"hero": "Title.Witch"` when the focus (the logo) is not
  the hero. The Umbra title went 96% accent / 1 of 4 leaning to 45% / 5 of 9 on these numbers alone.
- **Type treatments**: `"ransom": true` (every glyph its own cutout; the runtime rebuilds a changed word from the
  recipe, `Kit_RansomSeed` + `Kit_Inverted`), `"stacked": true` (a phrase as a stair of whole-WORD strips,
  alternating ink / paper, each leaning — Persona's command list; a word list is readable where ransom letters
  were not), `tracking`, chrome logotypes by `kit ui render`.
- **A picture through `kit ui ink --mode cel`**: the picture's own colours flattened to a few (`--colors 6`),
  TEED lines grown to `--line-px 3`, a paper rim + `--rim-ink 4`; `--palette mono` (black, two greys, white) is
  the P5 figure that sits ON the accent field — `identity` (ink / accent / paper) vanished on the field, and the
  halftone `ink` mode made a 3D render into a scribble. From the owner's render: cel-mono read as a figure, ink
  did not.
- **Owner anchors**: `kit ui judge <Screen> --owner 85 "the owner's words"` keeps the sheet in
  `assets/ui/anchors/`; every later packet shows them (anchors.png) and asks the judge to place the new screen
  between them; `--record` lists the gaps two judges AGREE on first.
- **Sources stage** in `kit ui plan`: every piece's provenance (render / trace / ink sidecar or a PROVENANCE row);
  a prompt-made hero piece is flagged.
- **`kit ui booth <Screen>`**: the screen in the REAL engine — through the shared capture bridge (no network): the
  run's Studio script shows the scratch place's own copy of the screen in StarterGui, plays its arrival through
  `src/kit/Ui.luau`, and `kit/vfx/capture.py studio` reads Studio's window at every moment
  (`--moments 0,0.15,0.4,1,2`) → `build/ui/booth/<Screen>_engine.png`. Needs the scratch place open and uploaded art.
- **`kit ui find "<words>"`**: the piece bank — proven pieces across identities and the starter library, with
  how each was made; look before any generator is asked.

<!-- reference for the parallax-ui route card; verbatim from the skill page (2026-10-16) -->

## Recipe (one pass)
0. `lune run kit lessons ui` · `lune run kit examples screen` (RpgHud, RpgTitle, RpgBonfire, RpgLevelUp,
   RpgDeath = a dark-fantasy RPG-type pack; SimHud, SimShop, SimPets, SimEgg, SimRebirth, SimDaily, SimCodes,
   SimSettings = a complete pet/clicker simulator pack in the chunky `sim` identity; hud_example / main_menu =
   the skin-only starters).
1. **Identity.** `assets/ui/identities/<name>.json` — copy `souls.json` and change EVERYTHING to the game's world:
   `about` (one line), `world`, `tokens` (measure them from references, never from habit), `fonts` (an Enum.Font
   trio: Garamond for a souls-like, Oswald for military, Michroma for sci-fi…), `radius`, `roles` (the type
   scale), `shape` (line, line2, fill, width, corner flourish|bracket|chamfer|round|none, glow, grain),
   `motion` (the default enter + stagger), `bans`, `references` (what each real screen does, measured) and
   `minimums` (`{"text": 16, "button": 56, "icon": 40}` — the scale floors measured from those references; the
   compiler warns under them: every undersized pack's first judge verdict was "everything is tiny").
   `lune run kit ui identities` lists them. Ask the owner for the references; a hero screen without an identity
   is an ERROR.
2. **Art.** `lune run kit ui` draws the identity's plates in its shape language into `build/ui/art/<name>/`
   (frame, frame_line, slot, cap, track, divider, band, vignette, grain, highlight, keycap, glow, ornament,
   corner, arrow, ring, ribbon) plus the **chunky family** (bubble, pill, badge, card, banner, track_chunky,
   gloss, burst, close, plus) — and a finished colour variant of bubble / pill / badge / banner for every token
   in `shape.buttons` (`bubble_good`, `pill_danger`...) and a `card_<tier>` for every `rarity_<tier>` token.
   The shape's `width` (outline), `gloss`, `shade`, `shadow` (drop offset) and `card` colour decide the look:
   souls = thin gold flourish, sim = 5 px navy outline + white gloss. LOOK at them. Generated pieces (icons, emblems, logos): `lune run kit vision
   concept "<a <game> style item icon: ...>" --sheet single -o x.png` → `kit vision cutout x.png --rgba -o x_cut.png`
   → crop + square → `assets/ui/art/<identity>/<name>.png` (the next `kit ui` takes them in as `art:<identity>/<name>`).
   **Hero pieces are RENDERED, not typed:** a chrome logotype, a bevelled rank letter, a lit metal plate come from
   `lune run kit ui render <identity>/<name>` — Blender (Cycles, GPU) renders `assets/ui/art/<identity>/<name>.render.json`
   (text items in any Enum.Font from the font cache, scale / position / lean, `material` chrome_gold | chrome_silver |
   chrome_red | black_steel or {base, roughness, metallic}, `depth`, `bevel`, `outline`, `glow`, `horizon` (the
   reflected-horizon gradient that makes a flat face read as chrome — on by default), and `"ring": true` items =
   broken emissive energy strokes) to a transparent PNG in ~10 s; render-only faces (Pirata One blackletter,
   Kaushan Script brush italic) live in fonts.json beside the Enum.Font twins; the screen shows it as
   `art:<identity>/<name>` (an image node can be the `focus`). A font glyph with a flat tint is the AI-slop tell;
   the real game's HUD is painted art, so make art. Reference pictures: `assets/ui/refs/<identity>/` + REFS.md with
   the measurements and the crop origins (a contact sheet pasted at an offset once mis-measured by 180 px).
   **Ornate gauge HUDs** (character-action-style style gauges, segmented bars in a metal frame with an emblem): a `"gauge": true`
   render item makes the plate (leaning troughs of inset wells, bladed caps) and writes `<piece>.anchors.json` — every
   well's rectangle in pixels; `lune run kit ui gauge <Screen>` turns `assets/ui/<Screen>.gauge.json` (plate, fills
   per row, emblem art, pip art + lit count, a name) into the screen spec with live cells laid exactly over the
   wells (slant plates tinted with the fill token: scripts light `Hud.Plate.Row0.C3`). Emblems and pips come from
   `kit vision concept` cutouts. Edit the .gauge.json, never the generated screen.
   **A 1:1 replica is TRACED, not generated:** `lune run kit ui trace <identity>/<piece> --from <picture> --box x,y,w,h
   [--x 4] [--cutout] [--gauge] [--repaint "<instruction>"]` crops the reference at 1:1, upscales it (Real-ESRGAN x4),
   cuts it out (BiRefNet), and for `--gauge` finds the green cells, blanks them to empty wells and writes their
   anchors; `--repaint` runs Qwen-Image-Edit on the crop for a cleaner take. Each piece carries its box
   (`<piece>.trace.json`), so a `.gauge.json` with `"from_trace": true` lays the emblem, the pip strip
   (`"pips": {"strip": ...}`) and a traced name exactly where the picture has them. The reference's pixels are
   the art; text prompts give look-alikes (the judges called every prompted emblem "a different design").
   **The measured HUD sets the scale, never the picture:** a gallery sheet is zoomed, so give the gauge
   `"crest_width": 220` (the real crest's width in 1080p px, from REFS.md) and the plate is sized from the traced
   boxes to match; `"nudge": [dx, dy]` on the emblem or the name moves a piece off its traced place (a crop that
   put the name onto the crest). Two judge rounds disagreed by 1.4x on the same build's size — measure, don't ask.
   **An ORIGINAL gauge in a game's spirit (no picture to trace):** identity from two measured stills → the crest and
   the pips as FLUX concepts (`kit vision concept ... --sheet single`, cut out, squared) → the plate as a `gauge`
   render item with `"cap": "horn"` (a crescent curl) or `"spike"`, a custom `frame: {base, roughness, metallic}`
   (a mirror steel reflects the lights and reads pale: base ~0.1, roughness 0.4, exposure ~0.12 reads as steel),
   `wear_scale` ~50 for a brushed grain (18 is blotchy grime); a curling identity wants the SWEEP options, not the
   character-action trough: `"bow": 0.1` (the row rises at its middle), `"taper": 0.3` (thinner to the right), `"cap_left": "horn"`
   (both ends curl), `"frame_pad": 0.03` + a row's own `"cell": [w, h]` (thin bars, a thinner second row); size the
   screen from the anchors (plate_width so a cell is ~12 px tall at 1080p); the CELLS are rendered too — a `gem`
   item per state (`{"gem": true, "size": [2.4, 0.66], "color": [r, g, b], "lit": true, "glow": 0.9, "halo": 0.4}`,
   exposure ~0.03: a glass slab in a dark lip with a halo; unlit = smoked dark glass) and the gauge spec's
   `"cells": {"art_lit": "cell_lit", "art_unlit": "cell_unlit"}` stretches each picture until its slab covers the
   well (a tinted slant plate reads as a flat slab; a rendered gem reads as lit energy). A bowed holder's cells
   FOLLOW the bow: every well's anchor carries the bar's tangent (`rot`) and `kit ui gauge` places each cell by its
   centre and rotates it to it — level cells inside a curved bar are the wrong picture → the name as a text render → the gauge spec with
   `"pips": {"art_lit", "art_unlit", "count", "lit"}` (an unlit pip as its own painting, not a ghost) → look, judge.
   The Umbra gauge (WitchGauge, identity `witch`) is the example: ~45 min from stills to a judged screen.
   **A whole HUD in a borrowed GRAMMAR** (Arcade5Hud: a stylized anime RPG's cutouts in Heroine's world): the grammar is
   plates — `torn` / `torn_black` (a paper cutout over its ink layer, offset 8-14 px, both leaning -6..-12),
   `halftone` (tint with the accent, imageAlpha 0.35-0.5), `rays` (behind the one hero piece) — and the rule
   "nothing level, nothing alone": every block leans and overlaps a neighbour, paper white under every cutout,
   one accent does all the shouting. Reuse proven pieces across identities by copying the art folder entries
   (the Umbra gauge + its anchors went into arcade5 untouched) and graft a `kit ui gauge` subtree into a
   hand-authored screen. A role's font may be a face name (`"script": {"font": "Fondamento"}`). A title /
   menu in that grammar (Arcade5Title): the logotype as a chrome render on a torn paper + ink pile, the menu as a
   leaning stack of torn `button`s (the selected one in the accent with a `rays` marker), a seamless `dots` tile
   (`"fit": "tile", "tile": 120`) for a halftone sky (the gradient `halftone` stretched over a screen gives
   fist-sized dots), a FLUX black silhouette with a white rim as the character cutout. The owner rejected the
   first menu ("looks bad") — the fix was MORE references: Persona's actual title still (refs/arcade5/REFS.md)
   measures as a torn accent FIELD on 35 % of the frame, lower-left, its edge falling to the right (the `torn_field`
   plate, drawn large so its tears stay paper-scale), the logo over the field's upper edge, the character huge over
   the field, and the menu on the BLACK side as a diagonal staircase of torn black ribbons (same lean, stepping
   down-right), the selected one on an accent splash much bigger than its ribbon. Structure first, then the pile.
   Every text render passes a hairline guard (stray 1-2 px lines from a glyph's open contour are cleared).
   Live pips: trace one lit and one unlit pip (`t_pip_lit_x`, `t_pip_unlit_x`) and give the gauge
   `"pips": {"strip": "<traced strip>", "art_lit": ..., "art_unlit": ..., "count": 10, "lit": 3}` — `count` pips
   spread along the strip's box, the lit ones breathing. The generated screen uses `insets: core` (the cluster
   sits under Roblox's buttons) unless the .gauge.json says otherwise. Trace colour-matches each channel to the
   1:1 crop after the upscale (`--sharpen`, `--gap` for seams) — a traced crest keeps its reds and its chrome.
3. **Screens.** `lune run kit new screen <Pascal> --from RpgHud` (the identity + its art come along) → edit `assets/ui/<Name>.json`: `"identity"`,
   `"quality": "hero"`, `"kind": "hud"|"menu"`, `"insets"`, `"scale": {"phone": 0.72}`, **`"focus": "<Root>.<Node>"`**
   (the one text the eye lands on first — the compiler checks it is the biggest; a hero screen without one is
   warned), then nodes. `lune run kit ui plan <Name>` at any time: the stage board (identity → art → spec →
   build → preview → look → judge → promote) with the next command.
4. `lune run kit ui --motion` → fonts (fetched + pinned) → kit art → plates → compile (gates) → build → the
   built place checked → `build/ui/<Name>.png` (desktop + phone + tablet, REAL faces) + `<Name>.motion.png`
   (six frames of the enter choreography). Fix every `[error]`, then every warning it names. LOOK at both sheets
   — then say so: `lune run kit ui look <Name> "<what you saw, what you will change>" --as "<model>@<harness>"`
   (≥ 40 characters, tied to this build; the judge packet and `kit promote` refuse a build nobody looked at).
   A screenshot of the game saved as `assets/ui/art/<identity>/world.png` becomes the preview's backdrop, so the
   screen is judged over the world it ships in, not a painted gradient.
5. **Judge.** `lune run kit ui judge <Screens...>` → `build/judge/ui/<…>/PROMPT.md` + `sheet.png` (desktop at 50 %
   + phone, each tile with a ruler = 100 real px, so a judge reads sizes against the ruler and the identity's
   floors, not in sheet pixels) + `motion.png` + `references.md` (+ `refs.png`: the real screens, when a reference
   carries `"image": "<path>"`) and the designer's claims (focus + look note) for the judge to test. Give it to a
   FRESH model (another session / a subagent that saw nothing). Record its
   answer: `--record verdict.json` → `assets/ui/<Screen>.judge.json` (several judges: the median). Bars: prop
   55 / hero 75 / aaa 88. The score is reported, never chased — `--record`'s next_action is the lowest screen's
   located gaps; fix those, rebuild, new packet.
6. `lune run kit upload` (art goes up, screens recompile with the ids). Drive it with the **Ui** runtime (below).
   Good → `lune run kit promote screen <Name> --about "…"`.

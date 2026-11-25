<!-- reference for the parallax-vfx route card; verbatim from the skill page (2026-10-16) -->

## Learned from references and shipped games (2026-10-11; sources in VETLOG.md and the memory note)
- **References first, in the folder**: `assets/effects/refs/<name>/` (ignored by git — copyrighted stills are private
  measure-only) holds frames of the target look; the player's `refs` panel shows them beside the viewport (`O`
  overlays one at 50%) and `kit vfx judge` puts them in the packet. Starblade: ufotable frames = hard-edged cel
  light (jagged lemon-yellow blades with white cores and a thin gold rim), a dense gold sparkle field during the
  gather, full white-out frames at release and impact, the beam as a THIN white line in a wide soft gold sheath.
- **Impact frames** (read from the owner's reference set: One Piece, MHA, Samurai Champloo, a Roblox game, a
  negative game frame — the full read is `board/plans/archive/impact-frames.md`; stills in `assets/effects/refs/impact_frames/`):
  TWO TONES and nothing else — a flat PAPER (white, black, or one flat hue) and an INK (the paper's opposite); the
  SUBJECT is the real pose of that frame flattened to a silhouette (never a redrawn illustration); the effect's
  ENERGY is thresholded to one thing (the paper, the ink, or ONE accent hue: gold, orange, red, cyan); RADIAL
  LINES converge on the hit (hundreds of thin speed lines, thick bristle wedges, a few huge dry-brush strokes,
  splatter); no sky, no lit ground, no bloom; the frames ALTERNATE light / dark / tinted, 2-4 frames each, clock
  held, then the white-out. Owner rulings 2026-10-11: a grade of the 3D scene is not one; a generated painting
  (a knight, a crater, a redrawn beam) is not one; "the impact frame should correspond to the vfx itself", "keep
  it black and white, maybe some yellow — it depends on the case of the visuals". Kit: `impact` with
  `"style": "frame"` BUILDS the frame from the scene at that instant: `paper`, `ink`, `accent` (what the hottest
  energy becomes; `hot` / `mark` override), `energy: [markT, hotT]` (0.22 / 0.8), `lines` (`speed_lines` |
  `bristle_burst` | `dry_brush` | `none`; `linesColor`, `linesScale` in screen heights, `linesStrength`), `focus`
  (a point; the hit), `subject` (`actor` = the rig + flying debris | `all`). Sequence per hit, inside the hitstop:
  white frame (speed lines, the effect's colour as the hot) 0.08 → black frame (white silhouettes, bristle burst)
  0.08 → white frame with dry brush 0.06 → `mode: flash` 0.05. A tinted frame = `paper: [255, 60, 40]` or the
  effect's colour. THE OWNER (2026-10-25): frames are OPTIONAL - "not everything needs impact frame ... impress me
  with the effect itself"; when a hit has them they must LINE UP with the shot on screen (`camera: "none"` = the
  live view; re-cropped / re-framed frames that do not match the attack read as weird). Where a big hit earns them,
  the `impact_frames` PART —
  `"use": [{"part": "impact_frames", "as": "<hit>", "at": "<beat>", "point": "<where the hit is>", "palette": {"accent": "<the effect's colour>"}}]`
  (four drawn frames + the white-out, 0.32 s, inside the hit's hitstop: a = the beam as a wedge + a spiky star + the
  rig's silhouette with a rim light from a low camera; b = black paper, white line art, bold lines, close-up;
  c = pure calligraphy (no scene: clouds, strokes, masses); d = wide, the wedge and star with perspective lines
  on the beam's far end; paper / ink per frame are palette names paper_a..ink_d, so `palette: {"paper_c": [255, 60, 40]}`
  tints a frame red; mute "*.white" / "*.frame_d" to drop one). A WORD is never in the default frames: the owner
  rejected a generic "DON!!" — a call-out is OPT-IN, and when asked for it is the ATTACK'S NAME in a deadly face
  that slams in with real exaggeration and then hands over to the attack: the `attack_call` part
  (`{"part": "attack_call", "as": "call", "at": "release", "point": "muzzle", "text": "STARBLADE", "sub": "HOLY SWORD", "palette": {"accent": "gold"}}`).
  A text frame is a DESIGNED TITLE CARD (the research: Demon Slayer's calligraphy on a brush band, manga SFX
  lettering, fighting-game cut-ins): the word is an ORIGINAL GRAPHIC — a heavy clean scaffold face (Impact by
  default) skewed into the motion, cut through by the blade, the glyphs jittered, a small spaced subline above —
  on a diagonal BAND with torn edges and streaks in the third of the frame away from the hit (`textPos: "band"`),
  the rig's silhouette beside it; SLAM motion over three frames: ENTRY (band + name slide in along the band, the
  trailing letters lagging, a 1.5x smear, the frame punched) → CONTACT (overshoot + squash, shake, splatter) →
  SETTLE (inverted, the attack's star and wedge begin); the face is split-toned (a light tint on top, the accent
  below) with a black outline and hard shadow, a glint sweeps the accent half on the contact frame, motion lines
  trail off the letters on the entry frame, an accent edge runs along the band, and a GHOST word (`ghost: "聖剣"`,
  Yu Gothic) stands hatched in the band's contrast colour behind the name. Every lettering knob may be a CURVE over
  the frame's life (`[[u, v], ...]`, u 0..1), so the card MOVES: the band whips in (`bandOffset`), the name slides
  after it (`offset`) smeared (`stretch`) and overshooting (`scale`), lands with a squash (`squash`), the glint
  sweeps (`glint`); two frames of 0.09 s are enough — a word that stands still for 0.07 s reads as a slide.
  THE OWNER'S FAVOURITE (2026-10-11): the name IS the impact frame — `lettering.cover: true` makes a full-screen card
  (`cardColor`), the name huge across it, torn (`rough`), blood running off the letters and spattered around
  (`drips`, `blood`); the blade's slash line flashes across (`cutFlash`), then the card is CUT (`cutAngle`): the
  halves tear apart (`gap`, up to 4), fly off to their sides (`slide`) spinning away (`spin`), sparks and blood
  chips in the gap — and what they reveal is the frame's own drawing (the silhouette, the wedge, the star). The
  `attack_call` part does it in 0.28 s (CARD 0.12 → BREAK 0.16): the cut is a demon's CLAW — `claws` parallel
  slashes `clawSpacing` apart, zig-zag cracks (`jag`) that CRAWL across the card first (`crawl` 0..1 with
  `cutFlash`), then every strip flies its own way and SHATTERS into shards (`shatter`) that spin off. Then
  `impact_frames` straight after, under ONE hit-stop (up to 0.8 s): no world time between the name and the hit.
  The owner loved the rip and asked to SEE it longer: the RIP is four 0.08 s frames whose curves continue one global
  tear (gap / slide / spin / shatter sampled per frame) while the card flickers black → white → blood red → white
  (the hit's drawing underneath alternating paper and line art); the gap opens slowly so the word stays readable
  until the last frame, the strips leave only at the end. LINGER (the owner: "make me feel the dread"): a hit-stop
  takes a `span` — the preset seconds of frames it plays through — shorter than its `hold`, so the frames play in
  slow motion while the world stands still (Starblade: hold 1.8 s over span 0.97 s; the card 0.20 + rip 4 x 0.11 =
  ~1.2 s real, the hit's frames ~0.6 s real). Holds cap at 1.8 s; a part `use` can also take `slow` (its times and
  lives stretched). The card is centred on the SCREEN (it ignores the frame's zoom toward the hit; it keeps the
  shake) and the word is ALIVE (`distort`, a curve): a heat ripple runs through the letters, rows glitch sideways,
  the word breathes, a blood echo trails it — animated by the held clock, on 24 fps ticks. The name must GRAB the
  viewer (the owner; NOT a literal spotlight): `reveal` stamps the letters in left to right, the newest one burning
  white; `spot` (the pull) converges ink speed lines on the word from the edges and crushes the edges to black;
  `scale` pushes the word in toward the viewer while it holds.
- **Pacing for dread** (the owner: "you should feel 'oh yeah, I'm gone' from your chair"): `timewarp: [[t, rate], ...]`
  is the clock's speed over the effect's time (rate 0.05..1; beat names allowed; player AND engine). Starblade: the
  gather tightens (1 → 0.6), the swing falls in bullet time (0.18–0.2: ~2.9 s real), the name + hit hold 1.8 s, the
  black ball's silence crawls (~0.5: ~3 s real), the blast's frames linger (hold 0.9 over span 0.36) and the blast
  unfolds slowly (0.25 → 1), then the aftermath in real time; low drones under the gather and the silence. The
  owner then asked "a bit quicker": every timewarp rate x1.3, the name hold 1.5 s — ~18 s.
- **Pillars are beams of racing light, never a mesh tube** (a translucent tube reads as a plastic can): `holy_column`
  (the `flow` recipe at high contrast, scrolled upward fast) in two crossed copies over a thin bright core, plus
  fire climbing the column (`blast_fireball` sprites rising). **Explosions are a simulated fireball** (`blast_fireball`:
  `fire_sim` with `emitter_z` ~0.1 so it bursts mid-air, `temperature_k` ~2200 and a gold `tint` for a white-gold
  core, low `flame_smoke`) plus a rolling dust wall (`dust_dome`: `smoke_sim`, strong vorticity, warm dust) spawned
  on a ground ring. Dome-shaped sim flipbooks must stay UPRIGHT (`rotation` ±12°): spun at random they read as
  wedges. After baking new textures, rebuild the play bundle (`kit vfx play`), the bundle lists textures.
- **No hard edges, ever** (the owner: "they look cut off, like barriers"). The four causes, all measured and now
  guarded: (1) a beam's ends — every beam fades in and out over `softEnds` (default 0.12 of its length; 0 = a hard
  cap) in player AND engine; (2) a beam strip's sides — the finish rolls off the sides of every wrapping strip
  (`post.side`, 0.2) and the gate `soft_sides` fails a strip whose edges are not dark; (3) the floor slicing a
  sprite — Roblox has no soft particles, so ground-level blast layers take a `zOffset` (studs toward the camera;
  the player now does the same push, not only draw order); (4) a flipbook cut at its cell — `not_clipped`: widen the
  sim's `frame`, keep a rays origin inside the cell (`origin`, `below`, `reach`).
- **A sheet needs a flipbook.** A 4x4 texture on a sprite without `flipbook` draws all 16 frames at once: a grid of
  little copies (Starblade's "white blobs" round the blast were a flash and a dust wave doing this). The validator
  now refuses it.
- **Magic circles (Fate)**: textures from the `circle` recipe (rings, star polygons, rune / Greek / Latin text bands,
  ticks, satellite circles, dots), drawn on a mesh `disc` with `params.planar: 1` (without it the texture wraps
  round the disc and turns into spirals). Cast them: an overshoot scale (0 -> 1.22R -> R in 0.12 s), a hold, a flare
  out. PLACE them, never scatter: one big circle under the caster, a few stacked through the pillar, a ring of
  satellites round the main rim cast in order, an arc of standing circles behind the caster (`aim` at it), a barrel
  of circles down the line the attack fires through.
- **A black hole is born from the strike**: it sits exactly where the beam ends (the beam's `to` IS the hole), it
  grows while the river pours in, then implodes into the detonation. The `blackhole` recipe renders it (black core,
  tilted swirling disc, lensed arc, photon ring; loops). Keep it off the floor (the floor cuts a big sprite) and keep
  the camera far enough that a 256-px frame is never magnified 10x. Its impact frames draw the hole too:
  `impact_frames_void` (draw knobs `void` and `crack`).
- Mesh layers take `rotate`, not `rot` (an unknown key is silently ignored). Beams take `curve` + `curveAxis` (the
  player now draws Roblox's Bezier). Debris takes `shape: "rock"` (faceted stones built at runtime) and Neon = hot.
- **Sims dissolve, they do not fade** (how AAA packs do it: a grayscale erosion map, not alpha). Fire and smoke
  sims take `post.erode` in the finish (a noise threshold eating the puff from its thin parts inward, a hot edge on
  the cut; the threshold is relative to each frame's densest point) and `sheet_end` (0.6: the sheet ends while the
  puff is still dense, the erosion finishes it). A sim's `emitter_z` / `temperature_k` / `tint` shape the fireball.
- **`squash` without `"orientation": "VelocityParallel"` stretches every sprite straight UP on screen** — it reads
  as rain. Streaks that converge on a point need the velocity orientation.
- **A black hole reads by its rim, not its black**: a black core + a tilted (`rot`) accretion disc + a camera-facing
  ring sprite (never a flat disc seen edge-on) + crackle, and the world dimmed (saturation and brightness down).
- **Impact frames may invert the palette** for the second hit (black paper, white ink, a blood-red frame): the
  blast reads as a different beat from the swing. Check them on the REAL time of the hold, not on the effect clock.
  `lettering: {skew, cut, stagger, stretch, squash, offset, scale, tilt, band, bandLines, bandColor, bandOffset,
  sub, ghost, ghostFont, split, glint, trail}`; `textSize` in screen heights, `textRot`; then `impact_frames` at +0.21 under
  TWO hitstops (0.22 + 0.36; a hold is capped at 0.5). Never a novelty face floating mid-frame — the gate
  fails a hitstop hit without frames (`frames_at_hits`) and a frame outside a hitstop (`frames_in_hitstop`). The
  viewer draws the frames live from any camera; the GAME gets them baked: `lune run kit vfx play <preset> --frames
  --views player` (the page draws each frame once, kit/vfx/frames.py writes plate specs `frame_<preset>_<layer>` +
  `assets/effects/frames/<preset>.json` + the contact sheet `build/vfx/booth/<preset>_frames.png` — LOOK at it; then
  `kit vfx`, then `kit upload --only frame_<preset>_`); Vfx.luau hands
  the map to VfxCompose, which gives each frame layer its `image` in-game (one camera's drawing, every view).
  THE DRAWING (without it the frame is a flat negative — owner): `exaggeration` (master) and
  `draw: {warp, grow, smear, outline, hatch, splatter, zoom, shake, flash, lineart, boil}` — a zoom punch and
  jitter on the hit, every edge noise-warped and re-rolled per frame (line boil), the energy grown and smeared
  away from the hit, Sobel outlines (`lineart` = outlined + hatched silhouettes for the dark frame), broken speed
  lines, hatching in the mid band, ink splatter heavier near the hit, a jagged white mass (`flash`, screen heights)
  at the hit in the light frame. Give every frame of a sequence different knobs (light: flash + hatch; dark:
  lineart + splatter; calligraphy: no outline, exaggeration 2+). Engine: paper = fog at zero range, silhouettes =
  Highlight fills on the rig models, lines = a ScreenGui image at the focus; the energy marks and the drawing are
  player-only until measured in the booth. `image` (a
  full-screen plate) and `ink | flash | white | black | mono` (grades) remain for special cases.
- **Slashes are asymmetric**: a sharp leading edge and a wider, stretched trailing edge (Genshin uses a 3D crescent
  mesh whose tail is pushed back by a vertex shader; the `slash` recipe draws the same thing as a flipbook). Keep the
  palette narrow; push the contrasting colour to the centre of the slash.
- **Impacts inherit the swing**: orient the impact burst by the weapon's direction and give its particles a share of
  the slash's velocity; "manga action lines" / impact stars on camera-locked planes sell the hit.
- **Hard-edged vector shapes beat soft gradients** for anime: fire as stacked jagged shapes, light as cel bands
  (`post.color: "cel"`, `bands` 2-3; `cel_wedge`, `light_blades`, `slash_cel`, `cel_puff`).
- **Timing**: cut particle lifespans in half from your first instinct; erosion that ends slow and linear reads as
  mush; the hit is instant, the build-up is long.
- **Vetted packs in the forge** (`"recipe": "import"`): Kenney Particle Pack 1.1 (CC0: 80 x 512² sprites — slash,
  trace, flare, light, star, twirl, scorch, spark, muzzle, smoke...) as `kn_*`; Unity Labs HDR EXR sequences
  (Thomas Iché, CC0: explosions, fireballs, flames, wispy smoke, clouds) as `ul_*` — HDR frames go through the same
  glow / hot-core / alpha / sheet finish as a render. `source` (dir or file), `select {start, step, count}`, `cell`
  (resize), `crop`, `premultiply`. Record every pack in VETLOG.md (licence quote, hash, what was inspected).

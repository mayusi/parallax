---
name: parallax-vfx
description: Make Roblox VFX that look AAA — anime ultimates, beams, slashes, explosions, impacts, auras, charge-ups — as version-3 layer-stack presets built from a SCENE BREAKDOWN of the real source (the scene's own frames + text + a beat sheet), approved as a beat chart with one test frame, textured in Blender (real renders: light bursts, wind ribbons, lit dust, volumetric light/fire, energy flows, glowing cracks) and as runtime mesh shells, played on one clock (hit-stop, slow motion), made and judged in the browser player as the EFFECT ALONE (no Studio, nothing animated around it - the owner, 2026-10-16) with the OWNER's verdict as the bar. Use for any effect or "make it feel impactful" task.
---

# parallax-vfx — the route card (the detail is in `reference/`; the record is in `kit/knowledge/vault/vfx/`)

Start: `lune run kit status --dept vfx` (the golden set, the graveyard, the owner's last verdicts), then
`kit help --stage vfx:<stage>` for the stage's ≤ 5 commands. Reuse mechanics, never the look: `kit vfx vault find
"<words>"`, `kit new vfx <name> --from starblade`, the parts in `assets/effects/parts/`.

## The clock and the route (the owner, 2026-11-10: "Yes, same budgets" - card b6m2)
- **The clock**: a piece gets 3D's budgets - 10 minutes simple, 30 complex, 60 hero (its spec's `"tier"`, a UI
  screen's `"quality"`; an effect is complex unless it says; hero only with `kit approve`). `kit vfx <name>` / `evolve <name>` start it; `kit vfx play` / `booth` (looks) start it only when the preset changed since it was last seen.
  A change is a change to what the piece is made of (its spec, the assets it names, a dossier's clip sources) -
  never a look's own output. Past the budget NO CHANGE builds (the piece as it was may still be played, looked
  at, rebuilt): show the owner what there is and its open cards; only his words reopen it: `kit clock vfx
  <name> --extend <minutes> "<his words>"` or `--restart "<his words>"`.
- **The route**: the technique families its layers use (mesh, flipbook, particles, beam, camera, light, ground). A piece made a NEW way (a way gained, not one dropped) refuses its build until
  `kit answer vfx <name> --reroute` and every lesson is answered again for the new route (a copied answer
  does not count).

## The owner's rules (every one has a date and a verdict behind it)
1. ORIGINALITY: every effect gets its OWN look from ITS source's real frames at anime / AAA quality; never re-skin
   the last success; never a genre swap (Delaware as a comic print = "trash"); one test frame before a whole version.
2. THE LIBRARY RULE: everything the pipeline makes is saved by part in `library/vfx/` with a README (`kit verify`
   fails on anything unsaved or stale); nothing is ever deleted; a loved version is never overwritten (new names).
3. No frames, no build: Hollow Purple v1 and the Explosion ("look really bad") were built from lore text + memory.
4. Impact frames are drawn from the scene (two tones, the real pose flattened, radial lines) — no grades, no
   generated paintings; only for massive hits.
5. The hybrid is THE base (saiyan_ssj_3d d3e33b6: mesh flame shells + flipbook cards, "10 TIMES BETTER"); the all-mesh
   rebuilds were "so bad"; small steps, one change at a time, shown each time.
6. "Not AAA yet": colour / norm / timing scores are never the bar; presentation (a real rig, a real attack clip,
   post, a reacting ground) and the source's own detail are.

## The route (8 stages)
| # | Stage | Its gate | Read |
|---|---|---|---|
| 1 | breakdown | the scene's frames in order (`kit vfx breakdown <set> --clip <file> --fps 2`; the owner's yes per source; private, measure-only) + the technique / episode text (`refs lore`, `refs brief`) + `refs_measured/<set>.beats.md` with measured colours; then the scene's TIMING: `kit vfx breakdown <set> --dense` reads every beat's shots at the clip's full frame rate (how the light arrives / stays / goes, a freeze, on ones / twos / threes) -> `refs_measured/<set>.timing.md` + the frames large in `build/vfx/breakdown/<set>_dense/` - time the chart from it, never from the 2 fps sheet; then the scene's DRAWINGS: `kit vfx trace <set> --beat N [--box ...] [--lit 0.6]` reads a beat's frames into outline curves, flat tones and holds (`build/vfx/trace/<set>/`: OPEN `beat<k>_d<nn>.png`, the trace laid on each frame; frame ONE element with `--box`, a whole key beat is a screen, not a card; a flood or a speckle is refused) | `reference/09-*`, `16-*`, `17-*` |
| 2 | chart | `kit vfx chart <set>`: every beat on the clock with hold / slow-mo marks, the scene frame beside each, the palette, ONE test frame of the key beat — approved by the OWNER (`kit vfx chart <set> --approve "<his words>" --by owner`, the record the build lock reads; or his click on `kit review <effect>`: the chart, the style sheet, the dailies and the finished effect on one page) before a whole version. THE STYLE SHEET (`kit vfx stylesheet <effect>`, after a recorded play): EVERY beat's look as a pair - the scene's frame at that beat's peak beside ours at ours, the effect's five colours and the key read under each, where ours falls short said in plain words (`build/vfx/stylesheet/<effect>/beat<k>.png`: OPEN each); his yes for it: `kit approve vfx <effect> "<his words>" --by owner --stage style` (it holds for that preset: an edited preset has another id) | `reference/08-*` |
| 1b | the camera | A shot whose CAMERA moves reads as an effect that changes on every frame. `kit vfx trace` measures the camera itself and REFUSES a moving one: run it with `--track` (the frames are stabilised, the trace is inside the window every frame covers). `kit vfx track <set> --beat N` shows what is followed: OPEN `build/vfx/track/<set>/beat<k>_track.png` (on its bottom row the background sits under the same lines). A flat background "could not be followed": nothing is guessed | `reference/21-*` |
| 2a | method plan | `kit vfx methods --set <set>`: every beat of the chart says which of the OWNER'S 104 methods it is made with (`kit vfx methods` = the list, `kit vfx methods <words>` = one method: how, its tool, what proves it is used). Write it BEFORE the chart is shown: `--beat N --use id,id`; a method the beat's own words ask for (a flame, a slash, smoke = hand-drawn: trace + ink) is used or left out with `--not id="<why>"`. The chart draws the plan and the reasons under each beat in his words; his approval keeps the plan he saw. THE GATE (`kit vfx`, every preset built from a scene since 2026-11-13): a beat with no plan, a planned method that no layer of that beat uses, a reason he has not seen, a method he saw and the plan dropped = refused. More methods than planned are free | `reference/18-*` |
| 2b | animatic | (a beat that must STAND somewhere - a pillar, a crater, an orb - may be a `"solid"` in the chart, checked from the gameplay angles with `--angles`: `reference/16-*`) `kit vfx animatic <set>`: the MOTION before the look - every beat as one flat shape (disc, ring, arc, bar, wall) at the chart's timing and the scene's measured share of the frame, with the hit-stops; recorded in the player, read back against its own plan, and laid beside the scene IN MOTION (`build/vfx/animatic/<set>_side.mp4`: WATCH it; `build/vfx/dailies/<set>_animatic/`: the frames and what differs). The OWNER's yes: `kit approve vfx <set> "<his words>" --by owner --stage animatic` or his click on `kit review <set> --lane vfx`. Read the NOTES in `build/vfx/animatic/<set>.plan.json` first (every number the plan settled itself). After the build: `kit vfx animatic <set> --drift <effect>` names a beat whose light arrives more than ONE drawing off the animatic's, came early, or has no light of its own - and says whether that animatic is the one the owner approved. It reads light only: a guard against layers placed late or early, not a judge of the motion | `reference/16-*` |
| 3 | textures | A SURFACE look (a skin, a ring, a glow, cracks - not what the scene DRAWS: that is inked, next) is TRIED in seconds before any Blender recipe: `kit vfx comp <key> --new ring\|skin\|blobs\|branches\|map`, edit its `comp` block (shape, panning noise, warp, erosion, the scene's colours in its ramp, halftone), run `kit vfx comp <key>` again and OPEN `build/vfx/comp/<key>_strip.png` (`reference/20-*`). A look made of PARTS that behave differently (a steady core in a halo that tears, one noise masking another, a bend of one part only) is a graph of nodes, not the one stack: `kit vfx comp <key> --new graph`, then wire its `"graph"` (`reference/36-*`). DRAWN sheets first: `kit vfx ink <key> --from build/vfx/trace/<set>/beat<k>.json [--drawings a-b] [--between 1]` draws a trace's drawings again as a sheet, one cell a drawing (OPEN `build/vfx/ink/<key>_strip.png`; play it with the `flipbook` line its summary gives, `blend: false`; `reference/17-*`). `assets/textures/<key>.json` (`engine: fx`) Blender recipes made for each surface's UV axis (beam strips upright; a tube's V along its height); `kit vfx` renders what changed; LOOK at `build/textures/_fx_review.png`; `kit upload --only build/textures/<key>.png` | `reference/06-*` |
| 4 | preset | A thing that BREAKS (a ground slab that heaves, a pane, ice) is its OWN pieces, not thrown rocks: `kit vfx fracture <name> --size w,d[,h] [--pieces 14] [--impact x,z]` (OPEN `build/vfx/fracture/<name>.png`), then a debris layer with `"pieces": "<name>"` (`reference/22-*`; a beat whose words say shatter / fracture / crumble must use it or say why). Pieces that should LIE where they land (not shrink away in the air): `"rest": true` on that layer, and `kit vfx settle <name> --life <the layer's life>` says when the last one rests (`reference/25-*`). Particles that are THINGS (stones caught in a whirl, rubble drawn in, grit that tumbles): a swarm of `"shape": "Rock"` (40 at most, each a faceted stone that tumbles; `reference/29-*`). CLOTH (a banner, a flag, a sheet let go) is simulated and baked, never a wobbling plane: `kit vfx cloth <name> --pin top|left|corners --wind x,y,z [--loop]` (OPEN `build/vfx/cloth/<name>.png`), then a mesh layer of `"shape": "seq"` naming it (`reference/30-*`). A body that GIVES where it lands (jelly, a slime, a soft orb) is simulated and baked the same way, never a mesh scaled by a curve: `kit vfx soft <name> --drop 6 --soft 0.6 [--throw x,y,z]` (OPEN `build/vfx/soft/<name>.png`; `reference/31-*`). A HEAP (sand, ash, rubble that slides and settles) is its angle of repose, not a cone scaled up: `kit vfx sand <name> --mode slump|pour --repose 34` (OPEN `build/vfx/sand/<name>.png`; `reference/32-*`; the grains that fly are a swarm beside it). HAIR or FUR (a mane, a tassel, a fringe, strands that lag a turn and overshoot) is strands, never a wobbling shell: `kit vfx hair <name> --root cap|line --move toss|sway|none [--wind x,y,z] [--loop]` (OPEN `build/vfx/hair/<name>.png`; `reference/34-*`). A surface that RIPPLES from a point, or small pieces SCATTERED over an area that appear as a front passes (a shock over water, shards rising from the ground): Blender's Geometry Nodes, baked: `kit vfx geonodes <name> --recipe ripple|scatter` (OPEN `build/vfx/geonodes/<name>.png`; `reference/37-*`; needs Blender). WATER whose surface moves by water's own rules (rings from a drop, rain, a tank that rocks; a dam that breaks into a bore, a mound let go): `kit vfx water <name> --recipe drop|rain|slosh|dam|surge` (OPEN `build/vfx/water/<name>.png`; `reference/38-*`; the mathematics is held, it was never matched to a real scene; nothing breaks or sprays). LIQUID that splashes, seen from the side (a block of it let go, a body falling into a pool, a pool that rocks), with the foam and spray it makes: `kit vfx liquid <key> --solver flip|pbf --scene dam|drop|slosh` (OPEN `build/vfx/liquid/<key>.png`; `reference/39-*`; a flipbook, a slice with no depth, never matched to a real scene). A SHOCK that must BEND what it passes over (the ground under a blast, a plate of the scene): a comp sheet's `"shock"` - `kit vfx comp <key> --new shock` (`reference/20-*`; it bends that sheet's picture, not the live scene behind it). Particles that must go SOMEWHERE (round a column, up a fountain, along a drawn line) follow an authored field, not noise: `kit vfx field <name> --new vortex|wind|fountain|path` (edit the file, run it again, OPEN `build/vfx/field/<name>.png`), then a swarm layer's `"field": { "name": "<name>" }` (`reference/26-*`). Particles that GATHER INTO A SHAPE (a sigil, a letter, a ring of motes that forms and lets go): `kit vfx points <name> --new ring|disc|sphere|spiral|star` or `--picture <png>` (OPEN `build/vfx/points/<name>.png`), then a swarm layer's `"cloud": { "name": "<name>", "size": 6, "pull": [[0, 0], [0.4, 10], [1, 10]] }` (`reference/33-*`). A mesh whose SIZE on the screen is the director's, not the lens's (a far moon, an arc judged at one distance and seen at another): `"forced": { "ref": 40, "keep": 1 }` on its layer (`kit vfx forced --ref 40 --keep 1` prints what it does at each distance; `reference/28-*`). A light the CAMERA sees (a sun, a blast's core, a muzzle) gets a real lens flare: a lens layer with `"flare": { "strength", "ghosts", "streak", "squeeze" }` at the light's `point` - a glow, a level streak and ghosts that swing through the middle of the screen (`kit vfx flare --light x,y` draws where they fall; `reference/23-*`; speed `streaks` are not a flare). A drawn look's INNER lines (core against body, band against band) come from the texture: `"post": { "edges": { "threshold": 0.08 } }` draws a line wherever the packed picture steps, `"keep": false` keeps the lines alone (`reference/24-*`; `post.outline` is the silhouette only). A lens's colour fringe ON the effect itself (red past a bright rim, blue short of it): `"post": { "aberration": { "amount": 0.03 } }` on a sheet that keeps its own colours (`reference/27-*`; the lens layer's `aberration` is the screen's stand-in). A sheet that STEPS (few rendered frames of something that travels: a flame's lick, a slash, drifting smoke) gets the cells between from its own motion vectors, not more renders and never a cross-fade: `"post": { "inbetween": true }` with FEWER `frames` than the `grid` has cells: the grid is filled, no cell empty (`reference/35-*`). A mesh that BREAKS UP plays a baked sheet, never `erode` (player-only: the validator warns, the method gate refuses it on a new piece): `kit vfx dissolve <key> --from <its texture \| plain>` (OPEN `build/vfx/dissolve/<key>_strip.png`), then `"texture": "<key>", "surface": 1, "flipbook": {"layout": "4x4", "mode": "OneShot", "over": [start, end]}` (`reference/19-*`). `assets/effects/<name>.json` version 3; the validator (caps: ≤ 150 layers, count ≤ 200, rate ≤ 400, ~1,500 live particles, light range ≤ 60; cut-offs; unknown textures) + the pro norms (~44% non-additive, lives ~0.58 s, front-loaded curves, a dark twin behind every bright shape, ~5 colours); mesh shells (`flame`, `tongue`, `spiral`, `bolt`) for volume, cards for the anime silhouette | `reference/04-*`, `07-*`, `08-*` |
| 5 | play | `kit vfx play <name> [--record]`: the browser player at full frame rate with the measured Roblox rules — WHERE THE EFFECT IS MADE AND JUDGED, the effect alone (owner 2026-10-16); then `kit checks run vfx <name>` - the owner's words as checks ("static" = how much the hero recording moves - the library's, else the player's newest `build/vfx/booth/<name>_play_hero.mp4`; it reports beside the loved effects' range until the owner's verdicts give it a threshold); the gate's `frames_on_screen`: frames that re-frame the shot need the strike on screen first (>= 3 % of the hero view in the second before). A recorded play ENDS with `LOOK: build/vfx/dailies/<name>/` (`kit vfx dailies <name>`, run by `--record` itself): the scene's consecutive frames above ours at the same moments from the hit, 640 px a frame, two a picture (`beat<k>_<nn>.png` arrive at full size: OPEN them, the key beat's at least), the two light curves on `beat<k>_page.png`, and what differs said in seconds | `reference/10-*`, `16-*` |
| 6 | ~~booth~~ | OFF the route (owner 2026-10-16: "stop making vfx in roblox studio ... WITHOUT ANIMATING ANYTHING"): no Studio captures, no animated rig / stages; Studio only proves an engine fact | vault `vfx/graveyard` |
| 7 | judge | `kit vfx judge <name>`: the verifier — scene frame vs render per beat, one difference + ONE edit; `kit vfx evolve`: four variants, the OWNER picks (the owner's own picks steer each axis of the next round - gallery tuning; an agent's pick never does); `kit verdict vfx` | `reference/11-*` |
| 8 | ship | `kit vfx vault check` green; `kit promote vfx` only on an owner verdict ≥ 7; `kit lesson vfx` | `reference/02-*` |

Runtime (`ReplicatedStorage.kit`): `VfxStage` (one clock: hit-stop, slow motion; freezing a stage also disables rate
emitters), `VfxCompose` (beats / parts / variants), `VfxMesh` (EditableMesh shells; FLIP_V), `VfxValidate3` — `reference/12-*`.

## What never worked (`kit/knowledge/vault/vfx/graveyard.md`)
An all-mesh aura · a genre swap for originality · re-using the last showpiece's frames / title card / glow ·
building from lore text + memory · all-additive long-lived layers · untextured Neon ribbons and sprite rings
seen edge-on for air and energy ("plastic", "a white barcode") · magic circles scattered or edge-on · a black hole
floating off its beam · blind parameter rounds past the third (judge noise ±1.5) · originals from a brief alone (no real
frames, no chart: 4-6, "the quality degraded alot") · smoke as a swarm of LIT puff cards (quenchstrike "smoke looks
horrible", nuke_v3; ONE simulated event card: nuke_v4 8.7) · untextured solid meshes (quicksilver "meshes very low
quality") · frames that re-frame the shot over a strike that is a speck on screen (seam, sandfall, quicksilver,
noctiluca "bad impact frames"). Each is now a check that fails the REAL piece as he judged it
(`kit/selftest/vfx/owner_faults/`; `node kit/vfx/gate_replay.cjs <metrics.json> <expanded.json>` re-runs the recording
gate on a stored recording; kit selftest runs `kit vfx director calibrate --evidence-only`: a rule that misses its own
evidence fails). Grey footage (dust, smoke, steam): `kit vfx refs rank|measure <set> --grey`.
**Scope and the scene's intensity (2026-11-11, flame_arc_keybeat REDO):** a piece built from a breakdown says which
beats it builds (every layer's `"beat"`) and builds them ALL or is named for the beat it is (the scene gate's scope
check); and before showing a test frame, `kit vfx keyread <set> --effect <name>` reads it beside the scene's key frame
(coverage, white-hot light, colour layers, detail, separate pieces) - short of the scene on two or more, it is not ready.

## Engine facts and traps (`reference/13-*` is the full measured list)
Beam textures run the image's VERTICAL axis along the beam; `Beam.FaceCamera=false` = a one-sided wall · a
ParticleEmitter with TimeScale 0 still EMITS · two ColorCorrections ADD (end grades before a flash frame) · squash
needs VelocityParallel · a 4x4 sheet without a flipbook draws 16 blobs · disc textures need `planar` · three.js v=1
top vs EditableMesh v=0 (FLIP_V) · impact frames back to back inside one hit-stop · comic pages need an object
mask · an inflated outline shell draws first with no depth write · measured anime colours wash out in additive Neon
(pre-saturate, keep the compare winner) · refs silhouette only on full shots (n ≥ 8); BiRefNet counts an aura as
foreground · Mantaflow needs the temp_override and its cache deleted · record mode reads the render target, not the
canvas · the GPU-idle rule · a runtime MESH ignores vertex alpha (fades / erode) AND TextureID alpha — its only
alpha + glow route is a layer's `surface` (a SurfaceAppearance; vault `vfx/refs/engine-facts`) - so a mesh dissolves by a baked sheet's cells (`kit vfx dissolve`, `flipbook.over`), not by `erode`.

## The pro techniques (2026-10-18; `reference/15-*` has every key)
Ease / echo / bursts / flicker / rim / boil / haze / path / onDeath / lit / onMaterial as layer keys; kinds `world`
(the scene reacts), `lens`, `crater`, `swarm` (scripted particles); spot / surface lights, wind, arc `skew`, mesh
sequences (`shape: "seq"`), the negative impact frame. Process: `--blockout`, `--with`, the `combat` view, judging
skies, `kit vfx timing`, `kit vfx style`, `kit vfx cost --mobile`. Example: `kit/starter/vfx/techniques.json`.
**Slashes (2026-10-23):** build the smear and the wave IN the actor's swing plane; arc v2 (`jag` torn edges, `ridge`
depth, `twist`, `strands`) + `sweep` {head, tail} (draw in along the swing, erase behind, unfold / collapse); impact
frames v4 drawn from the slash (`draw.slash / split / slide / cutSmear`, `lines: "cut"`, `camera: "cut"`) and the part
`impact_frames_slash`. Every recording sheet is a LIFECYCLE sheet (all stages + the impact window frame by frame); the
gate checks `frames_draw_cut` and `dissipates`. Use the Blender recipes (`slash wave shards crack lightning ...`) before
drawing a texture in code, and look at each texture before using it.
**Research 2026-10-23:** pick the impact-frame STYLE per hit (slash / kanada / silhouette / flashinvert / beam sets);
a strike = `blade_glint` -> cut + shake `kick` (the camera bumps with the strike) -> frames; lens `streaks` for
directional speed lines; `draw.flare` (Kanada). Sources + the gap map: `board/plans/archive/vfx-research-2026-10-23.md`.
Also: `impact_frames_mono` (selective colour), `shock_ring`, `anime_smoke_burst` (GPU sim -> drawn cel puff), the
player's real blur + depth of field, gate checks `focal` + `strike_snap` (`reference/15-*`).

## Originals: the creative director (owner 2026-10-24: "original ideas ... a creative director")
An effect with no anime scene is built from a CONCEPT BRIEF (`"scene": {"original": "<brief>", "set": "<refs set>"}`, under
the owner's go-ahead `kit approve vfx originals`) AND REAL FRAMES (2026-11-10, R-vfx-5: the eight brief-only originals of
2026-10-24 scored 4-6; every 8+ was built from real frames): `set` is real footage of the phenomenon (or a scene of its
kind) broken down like a scene's, and the owner approves its chart (ONE test frame) before the whole piece - the scene
gate refuses a new original without them (the older ones: kit/vfx/scene_gate.json `original_refs`, frozen). `kit vfx director learn` distils the vault (golden, graveyard, orders,
lessons, taste rules) into `kit/knowledge/vault/vfx/director.md` - re-run after every verdict / lesson; `coverage` lists
the techniques and parts no effect uses yet; `new <name> --idea "..."` writes `assets/effects/briefs/<name>.md` from the
taste profile; `check` refuses a wish (8 sections, >= 3 timed beats, its OWN palette, >= 1 never-used technique, an
impact style, a breakdown not a fade, what it is NOT); `lint` runs the TASTE RULES
(`kit/knowledge/vault/vfx/director_rules.json`: lessons a number can check - add one whenever a lesson is measurable);
`review` turns a recording into a critique sheet. Nature / real footage is the reference when there is no anime scene.
`kit vfx swarm <preset> [--layers <prefix>]` tunes a swarm OFFLINE (the player's maths; wide = a flock, tall = a
fountain); swarm `attract.strength` / `swirl` take curves over the layer's life (an implosion that lets go).
A mesh's `spin` takes keys of its SPEED over life (`[[u, [x, y, z]], ...]`, degrees per second; the angle is the
integral: a whirl that spins UP and winds down); a `flame` shell's `twist` (degrees, feet to tip) makes it a helix.
Impact frames drawn FROM a mesh form need `draw.semantic: false` (semantic frames drop every mesh layer).
`director new` refuses while the lane holds 3 pieces the owner has not scored (kit new's verdict lock): show them
first. A texture spec's ONE source image with `frames` > 1 and a `grid` is a finished sheet (sliced row by row); the
finish gate's `frames_count` fails a texture that got fewer frames than its spec asks for.
Impact frames for an effect with no figure: `camera: "subject"` (a close-up of the effect's own drawn mask; `fill`,
`roll`) - `assets/effects/generators/_frames.py` `subject_frames(...)` builds strike / invert / flood / void beats with the
drama on, `fit_hitstop(preset)` fits the hold; the gate `frames_fill` is a floor for the speck. Smoke / steam / mist /
dust: SIMULATE THE EVENT as one lit flipbook (`kit/vfx/gpusim.py`: `surge`, `stem`, `swirl` for a vortex), never many
generic puff cards (the owner: cotton balls). Liquid metal / chrome: mesh `reflectance` (+ `roughness` in the player).

## Read next
`reference/03-the-loop-*.md` · `reference/05-learned-from-references-*.md` (what shipped games do) ·
`reference/09-packs-and-references-*.md` (every command) · `kit/knowledge/vault/vfx/index.md` ·
`board/plans/archive/impact-frames.md` · `board/plans/archive/2026-10-13-vfx-3d-mesh-workflow.md` · `[[shared/studio-mcp]]`.

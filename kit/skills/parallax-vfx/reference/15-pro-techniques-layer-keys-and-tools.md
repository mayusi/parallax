<!-- reference for the parallax-vfx route card: the pro / AAA techniques built 2026-10-18 (board/plans/archive/aaa-vfx-research.md) -->

## Pro techniques: layer keys, layer kinds and tools (proven in the player; Roblox side NOT yet Studio-proven)
The working example of every one is `kit/starter/vfx/techniques.json` (`kit new vfx <name> --from techniques`). It is a
test bench for the MECHANICS, not a look: give each effect its own look from its own source (the originality rule).

### Keys that expand into plain layers (VfxTech, inside VfxCompose: the game, player and validator never see them)
| Key | On | What it gives |
|---|---|---|
| `{ "ease": "backOut", "from": a, "to": b, "keys": 12, "over": [u0, u1] }` | any curve field | keyframes from an ease: linear quadIn quadOut quadInOut cubicOut expoIn expoOut backIn backOut elasticOut bounceOut snap anticipate settle |
| `echo { count, lag, fade, shrink }` | mesh | afterimages: copies replaying the mesh `lag` s apart, each fainter and smaller (anime smears, dashes) |
| `bursts { count, tilt: [min, max], cone, stagger, seed }` | sprite, debris | the emission split into cones at different tilts (debris never flies as one even sphere) |
| `flicker { amount, rate, field, seed }` | light, mesh, glow | the field x (1 + amount * smooth noise): living fire |
| `rim { color, scale, transparency }` | mesh | a ForceField shell: an edge that glows at grazing angles |
| `boil { texture, uvScroll, scale, color }` | mesh | a second shell, another texture scrolling another way: two noises crossing = boiling energy |
| `haze { scale, strength, wobble }` | mesh | a wobbling Glass shell: heat shimmer (desktop only, opaque things only) |
| `path { points: 2-6 offsets, keys, ease, segments }` | mesh, sprite | a Bezier: a mesh `move`; a sprite emitter hops along it in windows |
| `onDeath { ...sprite fields, ratio }` | sprite | a child emitter where the parents die (sub-emitter: each spark ends in a puff) |
| `lit { top, left, right, back, front }` | sprite | textures baked lit from each side; the stage picks by where the sun is, seen from the camera |
| `onMaterial { "Slate\|Rock": {...}, "Water": { "mute": true }, "*": {...} }` | any layer | overrides picked by the ground under the effect (one raycast; the player: `booth.ground`) |

### New runtime keys and kinds (VfxStage + the player)
- `light`: `type` point | spot (a cone along +Y: `aim` / `rotate`, `angle`) | surface (`size` [w, d] panel, `angle`).
- `sprite.wind: true` (needs `drag` > 0): drifts with Workspace.GlobalWind; the player uses `booth.wind`.
- `mesh` `shape: "arc"` + `params.skew` (0.05-0.95): the widest point along the slash (0.78 = razor front, fat tail).
- `mesh` `shape: "seq"` + `params { seq, fps, loop }`: a baked MESH SEQUENCE (`python kit/vfx/meshseq.py <name>
  --recipe billow|crown` -> assets/effects/seq/<name>.json, synced as VfxPresets.seq.<name>) replayed on an EditableMesh.
- `impact.mode: "invert"`: the negative frame (contrast -2 = 1 - c in the player; Roblox's mapping NOT yet proven).
- kind `world`: `exposure` (stops), `fog` (x), `fogColor` + `fogAmount`, `sky` + `skyAmount`, `sun`, `ambient`,
  `sunRays` (0-1), `dof` (0-1) + `focus`, `radius` - the whole scene reacts; the Lighting is restored afterwards.
- kind `lens`: `vignette`, `aberration` (lens_fringe red + cyan), `dirt` (+ `color`, `dirtTexture`), `zoom` (radial
  streaks) - 0-1 curves, full-screen images (Roblox UI blends normally: no additive).
- kind `crater`: `point`, `radius`, `depth` - terrain carved to Air at `at`, the voxels restored when its life ends.
- kind `swarm`: SCRIPTED particles (<= 150 parts): `curl { strength, scale, speed }`, `attract { point, strength,
  swirl }`, `gravity`, `drag`, `floor { y, bounce }`, `trail { lifetime }`, size / colour / transparency per life.
  Luau every frame: `kit vfx cost` counts it (~15 us a part with curl, estimated).

### Tools
- `kit vfx play <name> --blockout` (plain shapes: judge the TIMING first) · `--with a,b` (effects judged together) ·
  `--views combat` (game-camera distance) · `booth.sky`: night | day | overcast | sunset.
- `kit vfx timing <name>`: the sound's hits vs the recording's picture hits (83 ms = two frames).
- `kit vfx style <name>` / `kit vfx style derive <style> --from a,b`: a game's VFX style guide
  (assets/effects/styles/<style>.json; a preset opts in with "style").
- `kit vfx cost <name> --mobile`: the phone tier (particles, Luau, lights, SurfaceAppearances, Glass, post effects).
- `python kit/vfx/masks.py`: 9 tileable masks (mask_fbm cells cracks streaks caustics electric swirl heat sparkle).
- `python kit/vfx/flowbake.py <out> --from <texture> --flow swirl|wind|vortex|burst`: flow baked into a LOOPING flipbook.
- `python kit/vfx/lens.py`: the lens images. fxlab sims: `params.light` + `{"recipe": "lit_variant", "of", "light"}`
  specs = one bake, several lightings. 64-frame sims: `"frames": 64, "grid": 8, "cell": 128` (res 128 ~ 30 min).
- **GPU sims (2026-10-18): `"recipe": "gpu_smoke" | "gpu_fire"`** -> `kit/vfx/gpusim.py` (PyTorch + CUDA, runs first in
  `kit vfx`): seconds a sim (a 192x192x272 mushroom cloud ~55 s, a puff ~8 s) instead of Mantaflow's ~38 s a FRAME. Params:
  res, steps, heat, buoyancy, vorticity, turbulence, ceiling (an inversion: caps spread), stem (a floor source), max_speed,
  density / albedo / ambient / key / fill / light. Lit variants (`lit_variant`) render from the same simulation. Examples:
  gpu_smoke, gpu_fireball, gpu_dust_puff, nk_mushroom_gpu (+ _left / _right / _back).
- Player truth fixes: flipbook frames crossfade like the game; a normal-blended sprite is NOT dimmed by CAL.sprite (that
  0.4 was measured on additive glow - smoke read 2.5x too dark); `lit` treats a sun above ~37 degrees as top light.
- **Impostors (view variants):** `{"recipe": "view_variant", "of": <gpu sim>, "yaw": 90}` renders the same simulation
  turned (yaw 180 = the exact mirror of 0, measured); a sprite's `views { "0": tex, "90": tex, ... }` picks the view
  nearest the camera's angle round the effect (0 = camera on +Z, positive = camera moved to its left; game and player).
  `views` wins over `lit` (one table per sprite).
- **Hit flash on the target:** a `highlight` layer flashes ANY anchor the game passes - `Vfx.play(name, where,
  { anchors = { victim = theirModel } })` + `"target": "@victim"` (fill / outline curves).

### Slashes, impact frames v4 and lifecycle evaluation (2026-10-23: "push the existing pipeline further")
- **Arc v2** (`shape: "arc"`, `src/kit/VfxArc.luau` = the player's `arcPoint`, equal to 1e-15): `params.jag` (0-0.5) torn
  edges in the GEOMETRY (the inner edge rougher; the centreline never moves) + `jagFreq`, `seed`; `ridge` (0-1) a bowed
  cross-section with depth (reads nearly edge-on); `twist` (deg over the arc); `strands` (1-5) + `strandSpread` layered
  ribbons in one mesh (the outer ones thinner, set behind). All off by default: old presets do not move.
- **Sweep** (mesh layer key, arcs only): `"sweep": {"head": <0-1 curve>, "tail": <0-1 curve>}` lays the arc over a
  window of itself over the life - a slash DRAWS IN along the swing (head leads) and ERASES behind (tail follows); a
  wave can UNFOLD from its middle (head 0.55 -> 1, tail 0.45 -> 0) and collapse back into it. It moves vertices (the
  engine ignores vertex alpha), the texture stays pinned to the arc.
- **Build the slash ON THE SWING**: read the actor's facing and swing plane first (the player's stand-in faces -Z and
  pitches overhead -> 105 deg forward in `swingTime`), put the smear on the blade tip's path in that plane and the wave in
  the same plane; film it from cameras on / square to the axis. A crescent stood across the cut "goes to the side".
- **Impact frames v4 - drawn from the slash**: the frame reads the nearest arc's real centreline. `draw.slash` (a brush
  stroke: white core, accent body, ink edge, dry-brush bristles), `draw.split` (the frame cut in two along it, the far
  side inverted) + `draw.slide` (that side slid along the cut), `draw.cutSmear` (energy dragged along the cut),
  `lines: "cut"` (speed lines running WITH the swing), `camera: "cut"` (square to the arc's plane, cut + figure in frame,
  a dutch roll). The part **`impact_frames_slash`** composes four different frames from them (the cut through the world,
  the drag, the colour split, the afterimage) + exposure recovery: `{"part": "impact_frames_slash", "as": "cut", "at":
  <the hit>, "point": <the cut's middle>, "palette": {"accent": <slash colour>, "paper_c": <a colour that fights it>}}`.
  The arc must be ALIVE and full size at the hit (start soft glow sprites after the frames: they threshold into blobs).
- **Lifecycle sheets**: every `vfx play --record` sheet is staged by the preset's clock - the whole life by EFFECT time
  (anticipation / impact / follow-through / dissipation labelled) + the impact window frame by frame. Judge every stage,
  not the peak.
- **New recording checks**: `frames_draw_cut` (the drawn frame read back on the slash's centreline: >= 60 % stroke),
  `dissipates` (the tail must break down - coverage falling with the light - never a plain opacity fade or a one-frame
  pop; scenery layers such as a moon fade with the effect too).
- **fxlab `wave`** takes `mid` (the middle colour stop; it was hard-coded gold). Before drawing a texture in code, look
  for the Blender recipe: `slash`, `wave`, `shards`, `crack`, `lightning`, `shockwave`, `rays`, `blast`, sims - and LOOK
  at every texture before using it (`pillar_glow` is a square card, `cs_wave` read as a bubble as a sprite).

### From the research (2026-10-23, `board/plans/archive/vfx-research-2026-10-23.md`)
- **Pick the impact-frame STYLE for the hit**, never one look for all: a slash → `impact_frames_slash`; a stark flash of
  light → `impact_frames_kanada` (black then white, one straight-line flare, straight lines, nothing else); a heavy,
  quiet hit → `impact_frames_silhouette` (ufotable: the scene sinks to shadow, rim-lit silhouettes, only the energy
  glows, exposure recovering); a light combo hit → `impact_frames_flashinvert` (a white-out, then the negative); a beam
  or a blast → `impact_frames` / `_smash` / `_void` / `_shatter`.
- **`draw.flare`** (0-3): a Kanada light flare at the hit - straight razor lines (a long cross, short diagonals) +
  ghost rings; white on dark paper, ink on light.
- **A strike = glint -> cut + kick -> frames -> follow-through.** `blade_glint` (part, `@tip`): a Kanada flare flipbook
  (`kit/vfx/flares.py` -> `kanada_flare`) snapping open on the blade ~0.1 s before the swing. Shake **`kick`** [x, y]
  (degrees the PICTURE jolts, x right, y up; an overhead cut = [0, -4]) + `kickCurve`: the camera bumps WITH the strike
  (Demon Slayer). Game and player use the same signs (measured: the horizon drops 15 px for [0, -5]).
- **Lens `streaks`** (0-1 curve) + `streakAngle` (deg, counter-clockwise) + `streakSpeed` + `streakColor`: parallel
  speed lines across the screen along the action (`lens_streaks`); the radial `zoom` is the rush toward a point.
- **Shake / fov refuse keys they never read.** The FOV punch key is `delta`; the v2 names `fov` (FOV) and `frequency`
  (shake) are flagged as warnings: those punches never played (78 presets) - switching them on is the owner's call.
- Not possible in-engine (global post effects only): desaturating everything but the effect - only inside a baked
  impact frame. The player's screen blur / depth of field are still stubs (no preset uses them).

### The plan built from the research (R1-R6, 2026-10-23)
- **Selective colour** (`draw.selective` 0-1) + part **`impact_frames_mono`**: the world drains to flat grey, the
  effect keeps its own rendered colour - impossible in-engine (colour correction is global), so it lives in the frame.
  Use it when the energy's COLOUR is its identity; the energy must be big at the hit or there is nothing to keep.
- **`shock_ring`** (part): a torn ground shockwave from arc v2 at 360 deg (taper 0, `jag`, `ridge` = a rolling crest,
  2 strands), expo-out, eroding; cracks decal, rock bursts, a dust skirt, a light. Keep the band THIN (~0.2 of the
  radius): scaled up, a fat band reads as a filled disc.
- **Anime smoke**: a GPU sim finished as a drawn puff - fxfinish `color: "cel"` + `bands` + **`floor`** (the shadow
  band's tone, never black) + **`cut`** (a hard silhouette) + `outline` (ink) -> `gpu_smoke_cel`; part
  **`anime_smoke_burst`** (tilted bursts of puffs that shrink as they go, a rising column). Give the sim headroom
  (no `ceiling`, `sheet_end` ~0.6) or the cap reads flat.
- **The player now draws** a screen layer's `blur` (Roblox BlurEffect Size) and a world layer's `dof` from the depth
  buffer, far field only like the game's DepthOfFieldEffect (FocusDistance = focus, else the camera's distance;
  InFocusRadius 30). Before, blur was never drawn and dof blurred the whole frame.
- **Gate checks**: `focal` (in its biggest moments >= 45 % of the effect in ONE connected shape: a clear focal point)
  and `strike_snap` (at each hit the light climbs 10 -> 90 % within 0.15 s: prepare long, STRIKE in a frame).
- **A sprite's cone key is `spread`** (degrees, or [x, y]) - NOT `spreadAngle` (Roblox's property name), which nothing
  reads: 309 layers in 2026-10-23's audit emit with no cone (a validator warning; switching them on is the owner's
  call), and the `bursts` technique wrote it too (fixed: every burst flew in a line).
- The player now draws the lens overlays into RECORDINGS too (they only reached the screen before), and applies shake /
  kick about the camera's own axes (from the hero / side views the kick went the wrong way).

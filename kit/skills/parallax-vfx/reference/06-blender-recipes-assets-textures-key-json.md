<!-- reference for the parallax-vfx route card; verbatim from the skill page (2026-10-16) -->

## Blender recipes (`assets/textures/<key>.json`)
`{ "engine": "fx", "recipe": "...", "frames": 16, "grid": 4, "cell": 256, "samples": 32, "seed": 1, "params": {}, "post": {} }`
- `burst` — 3D spikes of light from a hot core (flashes, impacts, glints: `"spikes": 0` = a mote)
- `wind` — ribbons whipping around an axis (wind barriers, tornado starts, spin attacks)
- `dust` — lumpy LIT volumes billowing out and thinning (dust, smoke; `post.color: "gray"` = tintable)
- `blast` — an emissive volume exploding: white core, gold/amber rim, tongues (light / fire explosions, novas)
- `flow` — a seamless energy strip for Beams (`"wrap": true, "beam": true`; scroll it with `textureSpeed`)
- `crack` — a glowing fissure + branch cracks + scorch, seen from above (ground decals)
- `ring` — a shockwave from above: bright torn leading edge, a streaky wash inside, expanding (flat sprites:
  `orientation: "VelocityPerpendicular"`, `speed: 0.001`, `direction: "Top"` = lying on the ground)
- `wave` — a crescent wave of light, face-on, streaks trailing behind it (slash waves; fly it down a beam as a
  `VelocityPerpendicular` sprite with speed along the path)
- `rays` — god rays fanning up from a point (upright `FacingCameraWorldUp` sprites above an impact / a charge)
- `import` — frames from a vetted downloaded pack (`source`, `select`, `cell`, `crop`, `premultiply`); see above
- `smoke_sim` / `fire_sim` — OUR OWN simulated elements: a Mantaflow gas domain baked headless (Blender 5.2 bakes
  under a temp_override), lit by a key and a fill, rendered as a Cycles volume flipbook — a real billowing puff /
  a fireball with its smoke (one-shot: the inflow stops at `inflow_until`). Params: resolution, bake_frames,
  emitter, velocity, dissolve, render_density, key / fill, blackbody (fire). ~1-2 min each.
- `shockwave` — a 3D ground shockwave from a low angle: an expanding torus of light with a hot edge + a flash disc
  (reads as a wave with perspective; lay it flat under an impact)
- `gradient` — a pure glow strip (a gaussian across the width, no noise body): pillars, tubes, halos — a strip with
  a dim noise body adds up to a brown slab on a double-sided tube; this one does not
- `glyph` — a magic circle decal: rings, tick marks, a hexagram, runes (Segoe UI Historic on Windows; `font` for
  another .ttf), one still or a slow spin across the sheet
- `lightning` — jagged ribbon bolts from the top down with forking branches, a white core in a coloured glow;
  `strikes` bolts in turn across the sheet, flashing in, flickering, snapping out (chain lightning, thunder strikes,
  electric auras: `rate` + `flipbook` random start)
- `slash` — a sword's slash ARC drawn in from its start angle to its end (sharp leading edge, white core on the outer
  radius, tail thinning into streaks), then fading; `post.color: "cel"` = flat anime bands (`slash_cel`)
- `shards` — faceted crystal / glass / ice shards flying out and spinning, lit by facing + rim only (tint it: ice,
  glass, gems); one-shot
- `cel` — an anime cel puff: overlapping spheres shaded by facing + a baked key light, posterised by `post.color:
  "cel"` + `bands` (hand-drawn smoke, impact puffs; `solid: 1` keeps the silhouette hard)
`post`: `glow {bloom, radius}`, `streaks {count, length, strength, angle}` (star flares), `exposure`, `alpha`
(`glow` = brightness, `coverage` = the render's own), `solid` (0 = alpha from light only), `color` (`color` baked |
`gray` tintable | `cel` + `bands` anime cel shading). Recipe params: see `kit/vfx/fxlab.py` (each documents its own).
Blender is the default source. (Local AI — FLUX.2 klein is installed — is not wired into the VFX forge yet.)

`kit vfx` also writes `build/textures/_library.png` + `_library.md` (every registered texture: a frame, recipe, grid,
upload state, which presets / parts use it) — LOOK there and reuse before rendering a new element.

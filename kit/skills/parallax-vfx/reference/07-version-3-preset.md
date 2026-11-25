<!-- reference for the parallax-vfx route card; verbatim from the skill page (2026-10-16) -->

## Version-3 preset
```json
{ "version": 3, "mode": "burst", "duration": 7.5,
  "palette": { "gold": [255, 205, 96], "dust": [196, 172, 140] },
  "points":  { "muzzle": [0, 4.5, -3], "target": [0, 8, -298] },
  "booth":   { "motion": { "raise": 0.55, "swingAt": 2.45 }, "views": ["player", "side", "hero"] },
  "layers": [ { "name": "release_flash", "kind": "sprite", "at": 2.56, "point": "muzzle", ... }, ... ] }
```
Points: `[x, y, z]` (x right, y up, -z forward; `scale` multiplies), a name from `points`, `"target"` (the caller's
target overrides it), `"@anchor"` (a part / attachment the caller passes; follows it every frame) or `"@anchor^170"`
(170 studs along the anchor's +Y, a sword's length axis: a beam from `"@tip"` to `"@tip^170"` is a pillar standing
ON the blade that swings with the chop).
Every layer: `name` (unique), `kind`, `at` (s), `life` (s); sequences `[[u, v], ...]` run 0..1 over that life.
Preset-level `"hitstop": [{ "at": 2.6, "hold": 0.09 }]` stops the whole clock for `hold` REAL seconds at `at` (the
anime hit-stop: particles, beams, meshes and the camera feel all hold).
- `sprite` — ParticleEmitter, every engine property: `texture`, `count` | `rate` + `for`, `lifetime`, `speed`,
  `spread`, `drag`, `acceleration`, `size`, `transparency`, `squash`, `color` (palette names ok), `brightness`,
  `lightEmission` (-10..1), `lightInfluence`, `zOffset`, `orientation`, `direction`, `rotation`, `rotSpeed`,
  `lockedToPart`, `timeScale` (lingering layers 0.6-0.95), `shape {type Box|Sphere|Cylinder|Disc, size, style,
  inOut, partial}`, `flipbook {layout "4x4" | [cols, rows], fps, mode, startRandom, blend}`, `twin {...overrides}`,
  `point`, `aim` (+Y of the emitter points at it).
- `beam` — `from`, `to`, `texture`, `plane` camera (ribbon facing the camera) | up (a standing WALL of light, both
  faces drawn) | flat (a sheet lying along the path), `width` (seq), `taper` [start, end], `grow` (s for the front to arrive),
  `copies`, `widthSpread`, `jitter`, `curve`, `textureLength`, `textureSpeed` (number or [min, max]),
  `brightness` (seq), `fade` (seq), `transparency` (along the length: soft-start a beam with `[[0, 1], [0.04, 0]...]`).
- `mesh` — runtime EditableMesh (`ring disc tube cone sphere dome spiral arc` + `params`) or `Ball/Block/Cylinder`;
  `material` Neon | ForceField (draws its texture as a glowing pattern) | Glass | SmoothPlastic; `scale` (seq of number
  or [x, y, z]), `uvScroll` [u, v] /s, `spin`, `pivot` base | center, `aim`.
- `decal` (ground marks; `glow` > 1 = overbright), `light` (range <= 60), `debris` (kinematic rocks on the clock),
  `screen` (brightness / contrast / saturation / tint / blur / `bloom` boost), `impact` (white = stark contrast-stretched | black | mono |
  flash = a flat white-out, the ufotable frame; <= 0.3 s), `shake` (degrees), `fov` (degrees), `sound` (kit sound name: `kit sfx <name>` renders it, `kit upload --only build/sounds/<name>.ogg` makes it live),
  `glow` (turns `@part` to light).

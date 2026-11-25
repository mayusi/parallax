<!-- reference for the parallax-vfx route card; verbatim from the skill page (2026-10-16) -->

## Caps (enforced)
v3: <= 150 layers · count <= 200 · rate <= 400 · lifetime <= 20 s · flipbook fps <= 30 · ~1500 live particles
(warn 800) · light range <= 60 · everything ends by `duration`. Version 1/2 presets (`elements`) still play:
see `src/kit/VfxValidate.luau` for their rules.

## Legacy keys (errors on a new piece since 2026-11-18)
A sprite's `spreadAngle` (the cone key is `spread`), a fov layer's `fov` (the stage reads `delta`), a shake's
`frequency` (a fixed rate) and a big opaque camera-facing card standing on the ground (it tilts back: give it
`"orientation": "FacingCameraWorldUp"`) are warnings on the presets of 2026-11-18 (`kit/vfx/legacy_keys.json`,
frozen) and ERRORS on any piece made after (`kit/lib/vfxlegacy.luau`). `lune run kit vfx migrate` lists what each
preset carries; `--apply <name> ...` fixes those in place (a piece the owner judged: only with his words,
`--judged "<them>"`) - it changes the look (the cone opens, the punch plays), so record it and look before keeping it.

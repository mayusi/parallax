<!-- reference for the parallax-vfx route card: the baked dissolve (2026-11-13; the VFX methods audit, stage 3) -->

## A dissolve the game shows (`kit vfx dissolve`)

**The fault it answers.** A mesh layer's `erode` (and the edge fades in its `params`) write per-vertex alpha. Roblox
IGNORES a runtime mesh's vertex alpha (measured in Studio 2026-10-16, `reference/13-*`): what breaks up in the browser
player pops off in the game. 205 mesh layers in 21 presets used `erode` on 2026-11-13. The validator now WARNS
(once a preset, with the count), and the method gate REFUSES it on a new piece - also when the owner has waived the
piece's method plan: an engine fact is not a plan.

**What the engine does show on a mesh** (both measured the same day): the alpha of a SurfaceAppearance's texture (a
layer's `surface`), and a sheet's cells stepped on the mesh (its `flipbook`). So the dissolve is baked into a sheet.

### `lune run kit vfx dissolve <key> --from <texture key | plain> [options]`
- `--from` a built FX texture (an `"engine": "fx"` spec; `build/textures/<key>.png`, its first cell when it is a
  sheet) or `plain`: an opaque square for a shell that has no texture (116 of the 205 had none) - white, or
  `--tint r,g,b`. In the PLAYER a white sheet takes the layer's `color`; in the GAME the stage sets only the
  surface's glow tint, and whether the sheet itself is tinted is NOT measured: bake the colour in with `--tint`.
- `--cells 16` (4, 16 or 64: a 2x2, 4x4 or 8x8 sheet), `--cell 256` (the sheet is at most 1024 px).
- `--pattern patches` (default): smooth noise that TILES, so a shell whose texture wraps shows no seam; `--scale 5`
  patches across; `--density 0.35` = how much the texture's own alpha steers it (thin parts go first).
  `--pattern dither`: an ordered 8x8 screen, `--dot 4` px a dot - dithered transparency, a hard printed fade.
- `--soft 0.08` the width of the front. `--soft 0` = a hard cut-out: alpha clipping whose threshold moves over the
  layer's life.
- `--edge 0.06 --edge-color r,g,b [--edge-gain 1.6]` a burning rim along the front.
- `--curve 1` above 1 starts slowly and ends fast.
The pattern is levelled: every cell removes an even share of the texture's AREA (no cell pops, none stalls).

Its checks (a sheet that fails one writes NO spec and NO frames; an older sheet of that key stays): `source`,
`whole` (cell 0 IS the texture), `clears` (the last cell is empty), `monotone` (nothing comes back), `steps` (every
cell removes something and none more than three even shares), `packs` (every cell changes enough for the kit's
packer: a texture that covers 1 % of its cell cannot fill 16 cells), `breaks` (the middle cell is in pieces: at most
45 % of its pixels half-transparent - more is an even fade and is refused), `tiles` (a texture that wraps: the
pattern wraps too).
Writes `build/fxlab/<key>/NNN.npy` + `assets/textures/<key>.json` (`"recipe": "dissolve"`, `"from"`, its options)
and `build/vfx/dissolve/<key>_strip.png`: every cell over a dark and a light ground. OPEN it. `lune run kit vfx`
bakes it again when its spec or its source texture changed, then packs, checks and registers it - in its own step,
AFTER the run's fx textures are packed, so it is always baked from the source as it is now.

### Playing it
On a mesh layer:
```json
"texture": "<key>", "surface": 1,
"flipbook": { "layout": "4x4", "mode": "OneShot", "over": [0.6, 1] }
```
`over` is new (VfxStage, the player, the validator): the part of the layer's life the cells play in - cell 0 until
its start, the last cell from its end. It takes the place of `erode: [0.6, 1]`. The validator refuses `over`
without `"mode": "OneShot"` and without `surface` (without a SurfaceAppearance the game draws every cell as a full
square); the method gate refuses a dissolve sheet on any mesh that has no `surface`. On a sprite the sheet is an
ordinary OneShot flipbook.

### Limits, said plainly
- **Not proven in Studio.** Every part is an engine fact the kit measured on 2026-10-16 (a surface's alpha; cells
  stepped on a mesh), but the two together, and `over`, have only been type-checked and read in the player's code.
  One Studio capture settles it: the owner's decision.
- **A shell that scrolls its texture cannot play it**: a flipbook mesh steps its UVs cell by cell, so `uvScroll` and
  a dissolve sheet exclude each other (44 of the 205 scrolled). Not built: a one-column sheet that scrolls along U.
- A cell is a sixteenth of the sheet: a 256 px cell on a large shell is coarser than the shell's own texture was.
- The pattern sits on the TEXTURE (it turns and wobbles with the shell); `erode` sat on the vertices.
- A mesh's edge fades (`params.fadeIn` / `fadeOut` / `fadeSides`) are the same engine fault and are not fixed
  here: give the texture itself transparent edges and a `surface`.
- A surface needs its texture uploaded (`kit vfx surfaces` writes templates only for uploaded sheets).
- A layer too short, or held on twos (`step: 12`), shows only a few of the cells: 16 cells need about 16 drawings
  inside `over` (life x the window x the drawings a second). Nothing checks this yet.
- A source is an fx texture or `plain`: a painted (`textures.py`) or Blender-flipbook texture is refused.

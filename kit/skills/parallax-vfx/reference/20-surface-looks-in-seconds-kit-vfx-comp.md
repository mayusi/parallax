<!-- reference for the parallax-vfx route card: surface looks in seconds (2026-11-13; the VFX methods audit, stage 4) -->

## Surface looks in seconds (`kit vfx comp`)

Roblox has no custom shaders, so what a shader artist does live - scroll a noise through a shape, bend the lookup,
erode by a threshold, map grey to colour - is baked into a sheet. The Blender recipes do that in minutes a round;
`comp` does the 2D part in about a second or less (16 frames of 256 px: 0.3-1.3 s), so a look can be TRIED and tried again. Blender stays for what needs
real light or a simulation. What the scene DRAWS (a flame, a slash, smoke) is not a surface look: it is inked
(`reference/17-*`).

### The commands
- `lune run kit vfx comp <key> --new ring|skin|blobs|branches|map` - a starter spec `assets/textures/<key>.json`
  (never over an existing one). A starter's ramp is WHITE on purpose: the library is for mechanics, the colours are
  the scene's measured ones (the originality rule).
- `lune run kit vfx comp <key>` - bake it now: the frames, the time it took, and
  `build/vfx/comp/<key>_strip.png` (every frame over a dark and a light ground). OPEN it, edit the spec, run again.
- `lune run kit vfx` then packs, checks and registers the sheet like every other.

### The stack (the spec's `"comp"` block; every part is optional, something must show)
| Part | What it does |
|---|---|
| `"loop": true` | the frames loop: every `pan` is then in WHOLE patterns a loop, so the last frame steps into the first. `false` = a one-shot |
| `"tile": true` | the frame wraps: a skin a shell or a beam scrolls. No shape then |
| `"shape": {"sdf": ...}` | a SIGNED DISTANCE shape, centred: `ring` (radius, width), `disc`, `box` (size, round), `streak` (length, width, angle), `star` (points, inner, outer, sharp), `blobs` (count, radius, spread, `k`: discs joined by a smooth minimum - metaballs), `branches` (origin, angle, length, width, depth, forks, spread, shrink, `trunks`: a trunk that forks and thins - lightning, veins; several trunks round a point - cracks). `soft` = the edge; `falloff` > 0 = a gradient inwards for the ramp |
| `"source": {"texture": "<key>"}` | instead of a shape: a built FX texture's luminance x alpha - gradient mapping, and warping an existing texture |
| `"noise": {scale, octaves, pan, seed, contrast, mix}` | tiling noise multiplied in, panning |
| `"warp": {scale, amount, pan, seed}` | UV distortion: every lookup above is bent by a second, panning noise |
| `"erode": {"at": x}` or `{"from": a, "to": b}`, `soft` | the SHARE of the look cut away, its faintest parts first (0 = nothing, 1 = all). One number for a loop; `from` -> `to` over a one-shot's frames: every frame then removes an even share of the area and `"to": 1` empties exactly the last frame. A shape of ONE value (no noise, no falloff) has no faintest part: its erosion is refused |
| `"ramp": [[pos, [r, g, b]], ...]`, `"bands": n` | grey -> colour, colours 0-255 as everywhere in the kit; bands > 1 = flat steps |
| `"halftone": {"dot": px, "angle": deg}` | the alpha as a printed screen of dots sized by the value. On a `tile` only a square screen that fits (`angle` 0 or 90, `dot` dividing the cell) |

The spec around it: `"frames"` fill the `"grid"` exactly, the grid is 1, 2, 4 or 8 cells a side (a sheet's sides are
powers of two), `"post"` is the pass-through `{"alpha": "coverage", "tonemap": false, "border": 0}` (any other finish
would pack another picture than the strip shows), and a key a block does not read is refused (a typo would be baked
as its default).

### Its checks (a sheet that fails one writes NO frames; the strip is still drawn)
`fills` (the fullest frame covers 6 % of its cell or more), `moves` (no two neighbouring frames show the same
picture), `packs` (every frame's ALPHA changes enough for the kit's packer, which reads alpha alone), `loops` (a
loop's seam is no harder than 1.5 times its hardest ordinary step), `clear` (a shape touches no edge of its cell) or
`tiles` (a tile wraps on both axes, in colour and in alpha, read low-passed), `ends` (a one-shot that erodes ends
empty). A sheet that passes these is one the packer takes: a look that passed here and failed `kit vfx` was a
fault of the first version (a review, 2026-11-13).

### In the build chain
A plain stack is baked BEFORE the packer and packed like every sheet. A stack with a `source` is baked AFTER the
packer's general pass (its source is then this run's) and packed by its own step, before the dissolve step - so a
mapped skin can be a dissolve's source in the same run. A `source` is an fx texture; a dissolve sheet or another
mapped stack is refused.

### Which of the owner's methods it carries (the method gate proves each from the spec's blocks)
UV distortion (`warp`) - Texture warping (`source` + `warp`) - Gradient-mapped effects (`ramp`) - Signed distance
field effects (`shape`) - Metaball effects (`blobs`) - Procedural branching (`branches`) - Halftone (`halftone`).
A hand-typed spec for another engine, or an import that carries a `comp` block, proves none of them.

### Limits, said plainly
- **An opaque look whose colours alone move is not a flipbook here** (`packs`): the packer reads alpha alone and
  would refuse it. Bake ONE frame (`"frames": 1, "grid": 1`) and let the layer scroll it (`uvScroll`,
  `textureSpeed`); a flipbook is for a look whose shape changes.
- A `source` gives its FIRST cell, squared to the comp's cell: an animated source becomes a still.
- One broken comp spec fails its step and with it the `kit vfx` run (as a broken ink or dissolve spec does).
- A star's edge is exact; its soft edge and falloff are a little wider between its points (its distance is along
  the ray from the centre). Halftone at full alpha leaves pin-holes at the dots' corners.
- It is 2D: no light, no depth, no simulation. A look that needs volume is a Blender or a GPU-sim recipe.
- The noise is one kind (smooth, tiling); no cells, no streaks, no caustics here (`masks.py` has those as textures:
  map one with `source`).
- A warp over a shape near its cell's edge is refused by `clear`: make the shape smaller.
- A panning noise makes a one-shot's erosion non-monotonic per pixel (the pattern moves); for a break-up that only
  removes, bake the look as a loop and break it up with `kit vfx dissolve`.
- Nothing here was looked at in Roblox: a comp sheet is an ordinary flipbook.

### A shock that bends the picture (`"shock"`, 2026-11-15; the VFX methods audit, stage 30)
**The fault it answers.** A shock ring was drawn as light: it bent nothing. Shockwave distortion was the last of the
owner's methods the kit had nothing for.
```
lune run kit vfx comp <key> --new shock      (then edit the spec, and: lune run kit vfx comp <key>)
```
```json
"shock": { "from": 0.08, "to": 0.45, "width": 0.07, "amount": 0.02, "centre": [0.5, 0.5] }
```
A ring runs out from `centre` (its radius `from` -> `to` over the frames, in cells) and BENDS the picture it passes
over, as a lens does: just outside its line the picture is pushed outward, just inside pulled in, by `amount` of the
cell at most, a `width` from the line; over 3 widths away NOTHING changes. The starter bends a mottled disc so that
it bakes as it is. A `"source"` (a built texture) may stand in place of the shape and the noise - but a source is
read as a GREY MASK (luminance x alpha: its colours are not kept, its dark parts are clear) and, the sheet not being
a tile, it must fade to clear before the cell's edge: a full plate of the ground or of the scene CANNOT be baked
this way (it fails `clear`). A one-shot (`"loop": false`), not on a tile, not in a graph, not with `erode` or
`halftone`, and it starts a width or more out from its centre.
- Refused before baking: an `amount` over three tenths of the `width` (the picture is stretched to over twice its
  length at the line and smears into streaks), of 0 or under a pixel (nothing is seen), a `from` under the `width`
  (the ring would start on its own centre), a ring that jumps over one and a half of its width a frame (with the
  starter's numbers that needs 6 frames or more), under 4 frames, with `erode` or `halftone`.
- Refused after baking (no frames written): `bends` - the ring does not change the picture where it is in three
  frames of four (a flat fill has nothing to move; a ring that runs where the picture is not); `bends only at its
  ring`; `runs out` - what it bends is not further out at the end than at the start.
- **Enforced:** a beat that plans **Shockwave distortion** needs a layer whose texture is a comp sheet with a
  `shock` whose `amount` is above 0 - and whose spec the comp would bake (a loop, a graph beside it, an amount it
  refuses prove nothing).
- **Limits, said plainly.** This bends the SHEET's own picture, not the live scene behind the sheet. The live scene
  is bent by Roblox's Glass material only: a ring or shell mesh layer with `"material": "Glass"` and some
  transparency bends the OPAQUE things behind it - from quality level 16 of 21 up (looked at in Studio, 2026-11-15:
  16, 18, 21 bend; 15, 14, 8, 1 are plain see-through), not on a phone, not in the browser player, never particles
  or other see-through things. So the register closes the row as "the engine cannot, a stand-in is held": the Glass
  ring where it bends, this baked ring where it does not.
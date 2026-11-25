<!-- reference for the parallax-vfx route card: chromatic aberration (2026-11-14; the VFX methods audit, stage 12) -->

## Colours pulled apart at the rim (a texture's `post.aberration`, the lens layer's `aberration`)

**The fault it answers.** The kit's chromatic aberration was two tinted ring pictures laid over the screen's edge: a
stand-in that never touches the effect itself. A lens really pulls a bright shape's red and blue apart. Roblox has
no pass that could split the screen's colours, but an effect's OWN picture is a texture, and a texture can be split
when it is packed.

### On a texture spec (`assets/textures/<key>.json`)
```json
"post": { "aberration": { "amount": 0.03, "mode": "radial" } }
"post": { "aberration": { "amount": 0.03, "mode": "axis", "angle": 20 } }
```
- `radial` (unless said): red is drawn LARGER and blue SMALLER about the cell's middle. Nothing parts at the middle;
  at the cell's edge each has moved `amount` of the cell from green. A bright rim gets red outside it and blue
  inside it.
- `axis`: red is slid one way and blue the other along `angle` (degrees, counter-clockwise, 0 = red to the right),
  by `amount` of the cell's SHORT side, the same everywhere.
- `amount` 0.004-0.1. It must part the colours by a pixel or more of the sheet AS IT IS SAVED (the packer says the
  least amount).
- What moves is each colour's light. Where red reaches past the shape the fringe is as opaque as that red is
  bright: a white shape gets a full red fringe, an ice-blue one a faint one, a green one none.
- It is the LAST look: after cel bands, `cut`, `outline`, `erode` and `edges` (a drawn line parts into its colours
  too), before the cell's border fade.
- Refused: on a strip that wraps or a beam's texture; with a wrong block; and when no frame gets a fringe - an
  empty or flat picture, a picture with no red or blue in it (pure green), or (radial) a small shape at the cell's
  middle, where nothing parts (`"mode": "axis"` parts it).
- A picture that fills its cell keeps its colours at the cell's edge.

### On the screen
The lens layer's `"aberration": 0-1` still lays its red and cyan fringe pictures over the frame's edge: a stand-in
for the whole screen, where a real split is not possible.

### Enforced
A beat that plans **Chromatic aberration** needs a texture with `post.aberration` playing in it, or a lens layer
with `aberration` above 0.

### Limits, said plainly
- **Baked, not live**: the split is in the sheet's frames, about the CELL's middle - not about the middle of the
  screen. A sprite off to one side of the view is split as if it sat in the middle of it.
- The red and the blue are redrawn a fraction of a pixel off their grid, which softens their finest detail a
  little all over the picture, not only at the rim.
- A fringe pushed to the cell's edge is cut there, and the packer SAYS so (a warning, `fringe_whole`: a quarter or
  more of a parted colour arrives on the cell's outermost pixels where the picture had nothing).
- By design: the red and blue planes are moved with a linear resample (a slight softening of the finest detail; a
  sharper resample rings on hard edges), and the split is about the CELL's middle - a baked texture has no screen;
  the fringe about the screen's middle is the `lens` layer's `aberration`.
- A sprite is tinted by its layer's colour AFTER this: a white sheet split into red / green / blue and then tinted
  orange shows orange fringes of different strengths, not a rainbow. Use it on sheets that keep their own colours.
- `kit vfx comp` refuses it in a comp spec's `post`; `kit vfx dissolve` and `kit vfx ink` write their sheet's
  `post` themselves (a hand-added block there is lost).
- Not shown in Roblox or the browser player in this stage, and no real sheet was packed with it.

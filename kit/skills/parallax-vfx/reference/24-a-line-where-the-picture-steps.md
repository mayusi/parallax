<!-- reference for the parallax-vfx route card: edge detection and outlines (2026-11-14; the VFX methods audit, stage 9) -->

## A line where the picture steps (a texture's `post.edges`) and the kit's outlines

**The fault it answers.** `post.outline` inks a ring round a sheet's silhouette and nothing inside it. A drawn effect
has lines INSIDE the shape too: the border between the white core and the body of a flame, between two bands of
cel smoke. Roblox has no pass to find edges on the screen, so the line is found in the texture, when it is packed.

### On a texture spec (`assets/textures/<key>.json`)
```json
"post": { "color": "cel_color", "bands": 4,
          "edges": { "threshold": 0.08, "grow": 0, "color": [0.04, 0.05, 0.09], "keep": true } }
```
- A line is drawn wherever the finished picture STEPS: in any colour of it inside the shape (red against a green
  as bright is a step too), or in its alpha (the silhouette). It runs after every other look AND after a baked
  dissolve (`erode`: the holes it opens get their lines), so `cel` / `cel_color` bands and a `cut` get theirs.
- `threshold` 0.01-0.3 (0.08 unless said): how sharp a step is a line. A full step (black to white, or the hard
  silhouette) measures about 0.32; the border between two of FOUR bands about 0.1, of five about 0.08 (five bands
  or more: say 0.05); a soft ramp or a glow measures next to nothing and gets no line at any setting worth using.
  `grow`: extra pixels of line (0-8). `color`: the line, 0-1 each.
- A shape of ONE flat tone gets its silhouette only: that is an outline, whatever the step is called.
- With `post.outline` on the same sheet the ink ring is not lined a second time.
- `"keep": false` keeps the LINES ALONE (line art): the fill is dropped, the sheet is its lines.
- An empty block (`"edges": {}`) is the step at its defaults.
- A sheet that asks for edges and has none in any frame is REFUSED by the packer (`found no edge`): give the
  picture bands or a cut, lower the threshold, or drop the step.

### The kit's outlines, all of them
| On | How |
|---|---|
| a mesh of the effect, a character | the `highlight` layer (the engine's own screen-space outline) |
| a mesh or debris layer | `"outline"` (an ink shell behind it) |
| a sprite | in its texture: `post.outline` (round the shape), `post.edges` (inside it too) |

### Enforced
A beat that plans **Edge detection** needs a texture with `post.edges` playing in it (or an impact frame's
`draw.outline` / `draw.lineart`); a ring round the silhouette alone (`post.outline`) no longer counts. **Screen-space
outlines** is proved by any row of the table above.

### Limits, said plainly
- **Baked, not live**: the line is in the sheet's frames. Nothing finds edges on the game's screen (no pass to run
  it in), so two sprites that overlap get no line where they meet.
- A comp sheet may ask for `edges` (and `aberration`) in its `post` beside the pass-through finish; `kit vfx
  dissolve` / `kit vfx ink` keep an `edges` or `aberration` block added to their sheet's spec when they run again.
- The packer SAYS when the lines are all on the silhouette (a warning, `inner_lines`: fewer than 24 line pixels four
  or more pixels inside the shape): that is an outline, not edge detection. The method gate reads the spec, not the
  built sheet, so such a sheet still counts for the method on a plan: the warning at the build is what tells.
  Five bands or more want a threshold near 0.05 (the default 0.08 misses the faintest steps).
- The line's width is about 3 px of the CELL plus `grow`: a sheet shown very large shows a soft line, shown very
  small loses it.
- Not shown in Roblox or the browser player in this stage: a sheet is a sheet, and no real sheet was packed with it.

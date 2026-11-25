<!-- reference for the parallax-vfx route card: motion vectors (2026-11-14; the VFX methods audit, stage 20) -->

## The cells between, from motion vectors (`post.inbetween`)

**The fault it answers.** A flipbook of few rendered frames STEPS: a flame's lick, a slash or drifting smoke jumps
from one drawing to the next. Studios fix that by blending two frames along their motion vectors in a shader;
Roblox has no such shader. Here the same vectors are measured at pack time and the cells between are drawn into
the sheet.

### In a texture spec
```json
{ "frames": 6, "grid": 4, "post": { "inbetween": true } }
```
- The `grid` is FILLED from fewer rendered frames: 6 frames fill all 16 cells of a 4 x 4 sheet. Every cell is a
  moment of the frames' own timeline, evenly on; the first cell is the first frame and the last cell the last.
  The grid must have more cells than there are frames. No cell is ever left empty (Roblox plays every cell).
- `{ "inbetween": { "loop": true } }` for a sheet that plays round: the last cell is one step short of the first
  frame again.
- A cell between two frames is drawn from their motion: the packer measures where each bit of the picture goes (a
  motion vector a pixel, both ways), moves both frames part of the way along them and mixes the two - ONE shape
  part of the way. A cross-fade of the same two frames is two ghosts.
- It runs after every look and after `erode`, before `edges` and `aberration` (lines and fringes are drawn on
  every cell). A cell that falls ON a rendered frame is that frame, unchanged.

### Refused
- A picture that **stands still** between every two frames (under half a pixel of motion).
- **Over the whole sheet** the vectors account for under half the change between frames: the picture changes
  instead of moving, or its frames are too far apart.
- **A part of the picture is not followed** (any sixteenth of the cell that holds a fiftieth of the change, with
  under 0.4 accounted for): something small jumps further than it is wide while the rest drifts - it would be drawn
  twice.
- As many frames as the grid has cells (nothing to draw); a strip that wraps, a plate, a single picture.

### Enforced
A beat that plans **Motion vector-based effects** needs a layer whose texture's spec has `post.inbetween` on.

### Limits, said plainly
- **Not shown in Roblox or the browser player.** The made tests are discs that slide; no real sheet (a flame, a
  smoke sim) was packed with it.
- It follows what MOVES. Measured on made frames, these are refused as "changes instead of moving": a burst that
  grows more than about 6 px of radius a frame, two things that cross, a bright spark over a dim mover, a colour
  that changes while it moves, a fade of 30 % a frame. Slow drift under a boiling surface (1 px a frame) is
  refused too, while 3 px a frame packs: such a sheet needs its real frames.
- The vectors are measured from the PICTURES (dense optical flow), not saved by the simulation. Accuracy on made
  frames: a 20 px slide is placed to half a pixel but its area grows 13 % (a smear); a bar turned 30 degrees
  keeps its angle but loses a fifth of its area in the middle cell.
- The gate reads the spec, not the sheet: it holds that the step is asked for; the packer holds that it worked. A
  repack that is refused leaves the older sheet in place while the spec passes the gate (the same is true of
  `erode`, `edges` and `aberration`).
- It makes cells, not time: a sheet that plays ONCE over its particle's life is simply smoother. A sheet that
  LOOPS at a rate plays the same motion slower when it has more cells, and `flipbook.fps` stops at 30: a 24 fps
  loop cannot be doubled.
- Something that leaves the cell between two frames is cut at the cell's edge.

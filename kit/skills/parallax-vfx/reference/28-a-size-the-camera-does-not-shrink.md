<!-- reference for the parallax-vfx route card: forced perspective (2026-11-14; the VFX methods audit, stage 13) -->

## A size the camera does not shrink (a mesh layer's `"forced"`, `kit vfx forced`)

**The fault it answers.** In a drawn scene the size of a thing is the director's, not the lens's: a moon that fills
the frame from a mile off, an arc that stays as large on the screen whether the camera is near or far. A game
camera shrinks everything with distance, so an effect judged at one distance is a speck at another.

### On a mesh layer
```json
{ "kind": "mesh", "shape": "ring", "point": [0, 30, -200], "forced": { "ref": 100, "keep": 1, "min": 0.25, "max": 4 } }
```
Every frame the layer's size is multiplied by `(distance / ref) ^ keep`, held between `min` and `max`; the
distance is from the camera to the layer's point, in studs (an effect played larger or smaller keeps its forced
layer in step with its other layers).
- `ref` (MUST be said): the distance at which the layer is the size it was made at.
- `keep` 1 (unless said): it holds its size ON THE SCREEN while the multiplier is inside `min`..`max` - with the
  defaults from a quarter of `ref` to four times it (25 to 400 studs for a ref of 100). 0.5: its size on the screen
  falls with the square root of the distance (4 times as far: half the size, where the lens alone gives a quarter).
  Negative (down to -1): it shrinks faster than the lens. A keep nearer 0 than 0.05, or `min` and `max` both 1, does
  nothing and is refused.
- `min` / `max` (0.25 and 4 unless said): the multiplier never leaves them, so a camera that flies into the layer
  does not shrink it to nothing and one a mile off does not make it swallow the map.

### `lune run kit vfx forced [--ref 40] [--keep 1] [--min 0.25] [--max 4] [--at 10,20,40,80,160]`
Prints the multiplier, and the layer's on-screen size against its size at `ref`, at each distance. Read what a
block does before writing it. It writes nothing.

### Enforced
A beat that plans **Forced-perspective effects** needs a mesh layer with a `forced` block that has a `ref` and a
keep that is not 0 (or an impact frame with its own `camera`). The validator refuses a block with no `ref`, a block
that does nothing, an unread key, or a number out of range.

### Limits, said plainly
- **Run in the browser player and in Roblox (2026-11-15)** on two made rings, one plain and one forced
  (`python kit/selftest/vfx/player/made.py`, a made preset played from build/ by a headless browser and measured on its frames; `kit/selftest/vfx/studio/layers.md`, the same preset in a Studio play client): in the player, between a camera 28 and one 18 studs away, the plain ring's width on the screen
  changes 1.61 times and the forced ring's 1.03; in Roblox, `ref` 28, the forced ring is 7.8 studs with the camera
  28 studs away, 15.6 at 56, 3.9 at 14, held at 1.95 (x 0.25) at 3 and at 31.2 (x 4) at 400, the plain ring 7.8
  throughout. Studio's own camera script must be held off (a Scriptable camera set every frame) or it moves the
  camera back. The multiplier is one arithmetic in three places (the
  game's code, the player's, `forced.py`), compared in 600 cases. How each side measures the distance and where it
  applies the multiplier were read side by side, not run; a layer changing size as a camera moves was never seen.
- An impact frame drawn through its own camera (`cut`, `subject`) gives a forced layer the size THAT camera's
  distance asks (the player rebuilds the layer for the bake and puts it back after; it kept the main camera's).
  The game's impact frames are those baked plates. Read and type-checked, not run: no preset has a forced layer
  in an impact frame yet.
- A layer held "on twos" (`step`) keeps its size for the whole drawing: read when the drawing starts (the game
  once a drawing; the player from the camera at the drawing's start).
- Mesh layers only (not sprites, beams, debris or swarms).
- Only the SIZE changes: the layer's place stays, so a thing made larger also reaches further - toward the camera
  and through the ground too.
- In the game the camera's place is read in the layer's own update, a frame behind the picture: on a fast camera
  the size lags by that frame. Kept as that, by design: the stage updates every layer on Heartbeat, after the
  frame's camera has rendered; moving one layer's size into the render step would split a layer's update across
  two clocks for one frame (16 ms at 60 frames a second).
- The distance is to the layer's `point`, before `move`: a layer that travels far by `move` is sized as if it had
  not left.

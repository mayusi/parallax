<!-- reference for the parallax-vfx route card: cloth (2026-11-14; the VFX methods audit, stage 15) -->

## Cloth, simulated and baked (`kit vfx cloth`)

**The fault it answers.** A banner, a flag or a sheet in an effect was a flat mesh with `wobble` (a sine wave) or
nothing. Cloth hangs from where it is held, bellies in the wind and ripples from the held edge outward; a sine
wave does none of that.

### Bake one
```
lune run kit vfx cloth <name> [--size 6,4] [--pin top|left|corners] [--wind 0,0,14] [--gust 0.5]
                              [--gravity 30] [--start hang|flat] [--loop] [--frames 48] [--fps 24]
```
- `--pin top` a banner or a cape's collar; `left` a flag on its pole; `corners` a sheet on a line.
- `--wind x,y,z` in studs a second; `--gust 0..1` how much it swells, drops and ripples (0 = steady: a steady wind
  on a held sheet settles and the bake is refused as still).
- `--start flat` lets the sheet go lying level on frame 1 (it falls open); `hang` starts already blowing.
- `--loop` for a layer that plays it round: the wind comes round once a sequence, the sheet is blown six times round
  before the frames are kept, and what is left of a jump is taken out over the last quarter. At least a second long.
- OPEN `build/vfx/cloth/<name>.png`: six frames, from the front and from the side.

### Play it
```json
{ "kind": "mesh", "shape": "seq", "pivot": "origin", "params": { "seq": "<name>", "fps": 24, "loop": true }, "scale": 6 }
```
The bake is unit size (its longest side is 1): `scale` is the sheet's longest side in studs. `fps` is the bake's
(the command prints it); another number plays it faster or slower than it was simulated.

### Refused
- A sheet that **hangs still** (under 0.05 of its length a second, on average).
- Links that are **not the sheet's**: their mean under 0.9 of their own length in a frame, or one under 0.7 (a
  crumpled sheet, or frames that are not this grid's).
- A link **stretched** past 1.12 times its length in any frame.
- A point that **jumps** more than 0.2 of the sheet's length in one frame.
- A **held point that moved**.
- A looped bake whose **seam** jumps more than two and a half times a usual frame's largest move.

### Enforced
The layer must sit by its own origin (`"pivot": "origin"`): one that does not proves nothing.
A beat that plans **Cloth simulation** needs a mesh layer of `"shape": "seq"` whose `params.seq` names a cloth bake
that is there and whose OWN frames pass the checks above (read again from the file: a billow, a missing file, frames
pulled apart by hand prove nothing). A layer with `"loop": true` needs a bake made with `--loop`, and its `fps` is
from half to twice the bake's, its life at that speed at least half the bake's frames. The checks read the file's own `size` and `pin`: a file written by hand to fit
them would pass.

### Limits, said plainly
- **Where it sits.** With `"pivot": "origin"` (which the method gate asks for, stage 26) the file's own origin is on the
  layer's point. WITHOUT it both runtimes place a `seq` mesh by the bounding box of
  its FIRST frame (its middle, unless the layer says a `pivot`; `pivot: "base"` is not the same in the game and in
  the player for a sequence). A banner's box middle is near the middle of the sheet, not its top edge. (`pivot: "base"` on a sequence is two different places in the game and the player: the validator warns. A first frame with NO thickness one way - a cloth laid flat - is not settled in the game: it needs a Studio session.)
- **Not played in Roblox, not played in the browser player.** The bake rides the `seq` mesh shape both already
  have; no cloth bake was watched in either.
- Baked, not live: the wind is the bake's. A layer that turns or moves does not change how the sheet blows.
- The sheet does not collide with itself, with a character or with the ground (a sheet let go falls through a
  floor).
- The wind is a model, not air: it pushes each point along the sheet's normal by how fast the air meets it, in
  travelling waves. There is no vortex shedding (what makes a real flag snap), and a wind that blows ALONG the
  sheet's own plane does not push it at all (no drag along the cloth): blow across it.
- The frames ride into the game: 600 KB of file at most (16 x 10 x 48 frames is about 190 KB; the largest grid the
  command takes, 48 x 24, does not fit even 48 frames).
- The sequence's origin is the middle of the sheet's TOP edge: a flag's pole (`--pin left`) stands half the layer's
  scale to the left of the layer's origin.
- The sheet is stepped at least 192 times a second whatever `--fps`; bakes at different `--fps` are close, not the
  same.
- A long thin sheet on many rows (cells far from square) stretches and is refused: fewer rows.

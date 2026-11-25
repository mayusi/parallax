<!-- reference for the parallax-vfx route card: sand / granular (2026-11-14; the VFX methods audit, stage 17) -->

## Sand, simulated and baked (`kit vfx sand`)

**The fault it answers.** A heap of sand, ash or rubble was a cone mesh scaled up, or debris that shrank away. Sand
holds a slope up to its angle of repose and no steeper: a pillar of it slides down into a heap of exactly that
slope, and a pour builds a cone whose sides slide every time they pass it.

### Bake one
```
lune run kit vfx sand <name> [--mode slump|pour] [--size 8] [--height 4] [--width 2.5] [--repose 34]
                             [--rate 6] [--settle s] [--frames 40] [--fps 24]
```
- `--mode slump` a pillar (`--width` across, `--height` tall) let go; `--settle` is how long the slide takes
  (seconds; four fifths of the sequence unless said), fast at first and slowing.
- `--mode pour` sand poured on the middle at `--rate` cubic studs a second.
- `--repose` the steepest slope the sand holds: fine ash about 25, dry sand 34, gravel 40, wet sand 45.
- `--size` the square of ground it may spread over (studs).
- OPEN `build/vfx/sand/<name>.png`: six frames, the heap cut through its middle and from above.

### Play it
```json
{ "kind": "mesh", "shape": "seq", "pivot": "origin", "params": { "seq": "<name>", "fps": 24 }, "scale": 8 }
```
The bake is unit size (its ground is 1 wide): `scale` is the ground's width in studs, the layer's origin on the
ground. It is played once. The grains that FLY off it are a swarm or particles beside it, not this.

### Refused
- Sand that **does not move** (a pillar lower than its slope stands as it is).
- Sand **made or lost** (a frame's volume off by more than 3 % of the pillar's, or of what was poured by then).
- A heap **not at rest** in its last frame (one more pass of the simulation would still move it by a fiftieth of its
  height, any of 16 ways), or steeper than its angle of repose by 1.5 degrees: the last frame is held, it must not
  be a slide cut short. A `--settle` longer than the sequence is refused outright.
- Sand that moves in **under 0.4 of its frames** (one jump, then nothing), or that **climbs** between two frames of a
  slump.
- Sand **at the edge** of its ground (it would be cut off there): a larger `--size`.

### Enforced
The layer must sit by its own origin (`"pivot": "origin"`): one that does not proves nothing.
A beat that plans **Sand / granular simulation** needs a mesh layer of `"shape": "seq"` whose `params.seq` names a
sand bake that is there and whose OWN frames pass the checks above. A layer that loops it is refused, and so is one
whose `fps` is under half or over twice the bake's (a layer with no `fps` plays at 24: say it for a bake at 8 or 60), or whose life at that speed shows under half the
bake's frames.

### Limits, said plainly
- **Where it sits.** With `"pivot": "origin"` (which the method gate asks for, stage 26) the file's own origin is on the
  layer's point. WITHOUT it both runtimes place a `seq` mesh by the bounding box of
  its FIRST frame (its middle, unless the layer says a `pivot`; `pivot: "base"` is not the same in the game and in
  the player for a sequence). A pillar's first frame is the pillar: the layer's point is half the pillar's height above the ground. (`pivot: "base"` on a sequence is two different places in the game and the player: the validator warns. A first frame with NO thickness one way - a cloth laid flat - is not settled in the game: it needs a Studio session.)
- **Not played in Roblox, not played in the browser player.**
- It is the heap's SURFACE that is simulated (a height over each place of the ground), not grains: nothing flies,
  bounces, sprays or rolls off; no grain has a size. Overhangs and tunnels cannot be.
- A slump's SHAPES are the simulation's; its TIMING is `--settle` (the slide has no clock of its own here). A
  pour's clock is real.
- "Does not move" is measured in ground widths a second: a small slide on a wide ground, or a slow pour, is refused
  as still. A smaller `--size`.
- The frames ride into the game: 600 KB of file at most (20 x 20 x 40 frames is about 256 KB; 24 x 24 x 64 does not
  fit).
- Flat ground, one heap, a round pillar whose outline is the grid's (20 x 20 unless said; 24 x 24 at most, and
  cols = rows).
- The surface is a plain grid mesh: where the heap ends, the mesh lies flat on the ground around it (it needs a
  ground of its own colour under it, or a texture that fades at the rim).

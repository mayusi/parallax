<!-- reference for the parallax-vfx route card: water as a height field (2026-11-15; the VFX methods audit, stage 24) -->

## Water as a height field, simulated and baked (`kit vfx water`)

**The fault it answers.** The kit had no water that MOVES by water's own rules: water was a painted texture, and
the `wave` recipe is a wave of light. Two of the owner's methods - Wave simulation and Shallow-water simulation -
were missing.

**Never matched to a real scene.** No clip of water was read for this (a download waits on the owner). The tests
hold the mathematics; whether it looks like the water he has in mind is his to judge, and nobody has looked.

### Bake one
```
lune run kit vfx water <name> --recipe drop  [--at x,z] [--width 0.08] [--amount 0.3] [--damp 0.6]
lune run kit vfx water <name> --recipe rain  [--drops 6] [--seed 1] [--width 0.06] [--amount 0.2] [--damp 0.6]
lune run kit vfx water <name> --recipe slosh [--mode 1] [--amount 0.3] [--loop]
lune run kit vfx water <name> --recipe dam   [--at x] [--amount 1.0]
lune run kit vfx water <name> --recipe surge [--at x,z] [--width 0.12] [--amount 1.5]
                              [--speed 0.6] [--depth 0.1] [--frames 40] [--fps 24] [--cols 20] [--rows 20]
```
The water is the height of its surface over a flat bed, in a square tank with four walls.
- **Waves** (`drop`, `rain`, `slosh`): the wave equation. Every wave runs at ONE speed (`--speed`, tank widths a
  second), two waves pass through each other and add, a wall sends a wave back. `drop`: one drop's crater and rim;
  `rain`: several, at seeded places and moments; `slosh`: the whole tank rocking (`--loop` moves the speed to the
  nearest one whose rocking comes round in the sequence; the sequence must be about a whole rocking long, 2 /
  (mode x speed) seconds: `--speed 0.75 --frames 64` does, the plain defaults are refused saying so).
- **Shallow water** (`dam`, `surge`): the shallow-water equations (mass and momentum kept). A HIGH wave runs faster
  than a low one and its front steepens into a bore - a wall of water - which the wave equation cannot make.
  `dam`: water `--amount` x depth deeper on one side of a wall that is gone at the first frame; `surge`: a mound
  of water let go.
- `--depth` is the depth at rest as a part of the tank's width; `--amount` a height as a part of the depth.
- OPEN `build/vfx/water/<name>.png`: six frames cut through the middle (heights drawn three times as tall, the bed
  under them) and from above.

### Play it
```json
{ "kind": "mesh", "shape": "seq", "pivot": "origin", "params": { "seq": "<name>", "fps": 24 }, "scale": 24 }
```
The bake is unit size (the tank is 1 wide, y up, y = 0 the water at rest): `scale` is the tank's width in studs.
What the surface is drawn with (colour, shine, see-through) is the layer's own look.

### Refused
- Asks that cannot work, before anything is solved: a drop narrower than a cell of the mesh; a speed that moves a
  wave over 0.9 of its width a frame (a place would flip from frame to frame); a dam or a surge whose bore runs
  over 2 points of the mesh a frame (the game blends frames: a wall that jumps further fades from place to place); a
  slosh under 12 points a wave or
  that comes round in under 8 frames; a `--loop` whose nearest speed is far from the one asked; `--loop` on anything
  but a slosh.
- A file whose frames are **not what its own asks solve to** (the check solves them again and allows a hundredth
  of the highest wave: a file changed by hand, or another bake's frames under this one's asks), waves under 0.003 of
  the tank high (not seen), water that does not move, water made or lost, a bed laid bare,
  a place that flips from frame to frame; a layer that loops a bake that does not come round, or plays it far off
  its speed.

### Enforced
The layer must sit by its own origin (`"pivot": "origin"`): one that does not proves nothing.
A beat that plans **Wave simulation** needs a mesh layer of `"shape": "seq"` whose `params.seq` names a water bake
of a drop, rain or a slosh that is there and passes the checks above, played at half to twice its speed for at
least half its frames; **Shallow-water simulation** needs the same of a dam or a surge. One does not prove the
other.

### What the tests hold (the mathematics)
- No wave outruns the speed said, and its front is where that speed puts it; two waves add to 1e-12; a standing
  wave is half way round after 1 / (mode x speed) seconds, as far down as it was up.
- A dam's break against Stoker's exact solution: the shelf's height to 1.5 % and the bore's place to a cell and a
  half on the solver's grid (to 3 % and a point and a half on the baked mesh). A high dam's bore outruns a low one's.
- Water neither made nor lost (to 1e-12 on the solver's grid), none crosses a wall, still water stays still, a
  surge in the middle stays the same all four ways.
- The waves are solved at a rate set by their speed alone: the same water at 12 and 48 frames a second.

### Limits, said plainly
- **Not played in Roblox, not played in the browser player, never matched to a real scene.**
- A height has ONE value a place: nothing curls over, breaks, splashes or sprays; there is no foam. The bed is flat
  and always wet (no shore, no slope, nothing running up a beach); nothing floats; water does not flow round a thing.
- The tank is a square with four walls: waves come back from them. Water that should run off the edge of the mesh
  does not.
- The shallow-water solver is first order (Rusanov): a bore's rise is smeared over about SEVEN of its 64 cells (a
  ninth of the tank: 2.6 studs at a scale of 24), which on a 20-point mesh is a ramp two points wide - a steep
  slope that travels, not a wall of water. A small wave on it dies down sooner than real water's would.
- A drop's mark holds no water in all: what the walls cut off a wide one is taken off NEAR the drop (a soft ring
  twice its width), not off the whole tank (a test: the far corner of a drop by the wall is not lowered).
- Rain's moments are drawn over 1.15 s of the clock, not over the run: the same ask with other `--frames` is the
  same rain (a drop after the run's end is not in it; a test holds 30 and 48 frames to the same first 30).
- The wave equation's waves all run at one speed: real ripples of different lengths do not (no dispersion), so a
  drop's rings do not spread into a train as a pond's do.
- The mesh is 25 x 25 points at most and 600 KB of file. A wave needs about six points to show; the asks allow a
  drop as narrow as one cell, whose rings are then about four points long: the bake then SAYS it is coarse, with the
  width or the mesh that would do.
- Where it sits: with `"pivot": "origin"` (which the method gate asks for) the file's own origin is on the layer's
  point. Without it both runtimes centre a `seq` mesh on the box of its FIRST frame, which is somewhere else (and with a
  `spin` the two do not even agree on where: the player turns it about the point, the game about the box's middle -
  card vmqb). A first frame with NO thickness one way (a sheet laid flat, still water) is not settled either: how
  the engine sizes a part made from a flat mesh, and so how tall later frames are drawn, needs a Studio session.

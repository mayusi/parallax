<!-- reference for the parallax-vfx route card: soft body (2026-11-14; the VFX methods audit, stage 16) -->

## A soft body, simulated and baked (`kit vfx soft`)

**The fault it answers.** A blob, an orb of jelly or a slime that lands was a mesh scaled by a curve: it grew and
shrank as a whole. A soft body flattens WHERE it touches, widens by what its height lost, springs back and wobbles.

### Bake one
```
lune run kit vfx soft <name> [--size 4] [--drop 6] [--throw 0,0,0] [--soft 0.6] [--squash 0.7] [--gravity 60]
                             [--frames 48] [--fps 24]
```
- `--drop` how far its underside starts above the floor (studs); `--throw x,y,z` the speed it starts with.
- `--soft` 0.1 a firm rubber ball .. 0.8 a water balloon. The softer it is, the less drop it takes.
- `--squash` 0 = it only dents where it is touched; 0.8 (the most taken) = the whole ball flattens and widens.
- OPEN `build/vfx/soft/<name>.png`: six frames from the side, the floor drawn.

### Play it
```json
{ "kind": "mesh", "shape": "seq", "pivot": "origin", "params": { "seq": "<name>", "fps": 24 }, "scale": 4 }
```
The bake is unit size (the ball's width is 1): `scale` is its width in studs. The floor is y = 0 of the sequence:
put the layer's origin on the ground. It is played once (no `loop`).

### Refused
- A ball that **keeps its shape** (its height against its width leaves what it starts at by 8 % in fewer than two
  frames): a rigid ball. Usually it had not landed yet: more `--frames`.
- A ball **crushed flat** (under a fifth of its height against its width): a puddle.
- A **volume** under 0.75 or over 1.3 of the first frame's.
- A point **under the floor**, a **seam or pole that opened**, a ball that **sits still**.
- A **jump in its skin** over a quarter of its width in one frame, the ball's own travel taken out (it spins or
  lands too fast for the frames to follow).

### Enforced
The layer must sit by its own origin (`"pivot": "origin"`): one that does not proves nothing.
A beat that plans **Soft body simulation** needs a mesh layer of `"shape": "seq"` whose `params.seq` names a soft
bake that is there and whose OWN frames pass the checks above. Refused too: a layer that loops it, one whose `fps`
is under half or over twice the bake's, and one whose life at that speed shows under half the bake's frames (a
ball gone before it lands).

### Limits, said plainly
- **Where it sits.** With `"pivot": "origin"` (which the method gate asks for, stage 26) the file's own origin is on the
  layer's point. WITHOUT it both runtimes place a `seq` mesh by the bounding box of
  its FIRST frame (its middle, unless the layer says a `pivot`; `pivot: "base"` is not the same in the game and in
  the player for a sequence). A dropped ball's first frame is the ball in the air: the layer's point is the ball's middle THERE, not the floor. (`pivot: "base"` on a sequence is two different places in the game and the player: the validator warns. A first frame with NO thickness one way - a cloth laid flat - is not settled in the game: it needs a Studio session.)
- **Not played in Roblox, not played in the browser player.** The bake rides the `seq` mesh shape both already
  have; no soft bake was watched in either.
- A ball only (no other shape), and it collides with a flat floor only: no walls, no character, no second body.
- Baked, not live: it lands where the bake's floor is, whatever the game's ground does.
- The body is its skin: points that keep their distances, pulled back to the ball's shape (shape matching) with its
  volume kept by widening. It is a model for the eye, not a material: `--soft` is not a stiffness in any unit.
- A straight drop has no spin. A thrown ball mostly SLIDES to a stop: the floor grips what touches it (a fixed grip,
  not a friction number) and the wobble's damping takes its spin with it. It turns far less than a rolling ball.
- The bake does **not** come to rest: 48 frames of the default ask end in its second bounce, a quarter stud up. A
  layer that outlives the bake holds that last frame (a ball hanging still). No check covers it: more `--frames`,
  or a life no longer than the bake.
- `--drop`, `--gravity` and `--size` are in studs and the give is not scaled to them: the same `--soft` squashes a
  small ball more than a large one. The ball is stepped at least 192 times a second whatever `--fps`; bakes at
  different `--fps` are close, not the same.
- The frames ride into the game: 600 KB of file at most (16 x 10 x 48 frames is about 175 KB).

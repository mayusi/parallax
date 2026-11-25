<!-- reference for the parallax-vfx route card: hair / fur (2026-11-14; the VFX methods audit, stage 19) -->

## Hair and fur, simulated and baked (`kit vfx hair`)

**The fault it answers.** A mane, a tassel, a fringe or a head of hair in an effect was a shell that wobbled as
one piece. Hair is strands: each keeps its length, lags the turn of what it grows from, overshoots and settles.

### Bake one
```
lune run kit vfx hair <name> [--root cap|line] [--strands 16] [--length 3] [--width 0.25] [--head 1.2]
                             [--move toss|sway|none] [--amount 0.8] [--wind x,y,z] [--gust 0.5]
                             [--stiff 0.15] [--gravity 40] [--loop] [--frames 48] [--fps 24] [--segments 8]
```
- `--root cap` strands grow out of the top of a head (a ball `--head` studs across: the hair lies over it, never
  through it); `line` strands hang from a row `--head` studs long (a mane, a tassel, a fringe).
- `--move toss` the root turns left and right, `--amount` radians each way; `sway` it slides side to side,
  `--amount` studs each way; `none` only the wind moves the hair.
- `--stiff` 0 wet string, 0.15 hair, 0.6 bristles. Fur: a short `--length`, more `--stiff`, more `--strands`.
- `--loop` the move and the wind come round once a sequence (at least a second long).
- OPEN `build/vfx/hair/<name>.png`: six frames from the front and from above, each strand's middle line.

### Play it
```json
{ "kind": "mesh", "shape": "seq", "pivot": "origin", "params": { "seq": "<name>", "fps": 24, "loop": true }, "scale": 3 }
```
The bake is unit size (a strand is 1 long): `scale` is a strand's length in studs. In the FILE the origin is the
head's middle (`cap`) or the middle of the row (`line`); see the first limit for where the layer puts it. Each strand is its own strip of the mesh (a ribbon 2 points wide that
narrows to its tip): the sequence file says `"strips"`, and the `seq` shape builds one grid a strip.

### Refused
- Hair that **does not move** (its tips under 0.05 of a strand a second).
- A strand that **stretches** (under 0.9 or over 1.1 of its length), or whose segments are uneven.
- **Roots that come apart** (two roots nearer or farther than they started: they are on one body).
- Hair that is **one stiff piece**: laid by its best rigid move (any turn, any slide) onto its own first frame, no
  point of it is 0.02 of a strand off. Hair too heavy to swing is refused the same way.
- A tip that **jumps** over 0.35 of a strand in a frame (its root's own move taken out); a **ribbon that turns over**
  from one row or frame to the next; a ribbon wider than half a strand; a loop whose seam jumps.

### Enforced
The layer must sit by its own origin (`"pivot": "origin"`): one that does not proves nothing.
A beat that plans **Hair / fur simulation** needs a mesh layer of `"shape": "seq"` whose `params.seq` names a hair
bake that is there and whose OWN frames pass the checks above; a looped layer needs a bake made with `--loop`; its
`fps` is from half to twice the bake's and its life shows at least half the bake's frames.

### Limits, said plainly
- **Where it sits.** With `"pivot": "origin"` (which the method gate asks for, stage 26) the file's own origin is on the
  layer's point. WITHOUT it both runtimes place a `seq` mesh by the bounding box of
  its FIRST frame (its middle, unless the layer says a `pivot`; `pivot: "base"` is not the same in the game and in
  the player for a sequence). A tossed head's box middle is about a quarter of a strand below the head's middle. (`pivot: "base"` on a sequence is two different places in the game and the player: the validator warns. A first frame with NO thickness one way - a cloth laid flat - is not settled in the game: it needs a Studio session.)
- **Not played in Roblox, not played in the browser player.** The `seq` shape's strips are new in both (one grid a
  strip, in the frames' order): the two were read against each other and against the file's order, not built or run.
- The move is the bake's own toss or sway. It does not follow a character's head: baked, not live.
- Strands do not collide with one another, and only a `cap`'s own head ball keeps hair out (no shoulders, no body).
- A ribbon faces sideways to the head's middle (`cap`) or to +z (`line`); it does not turn to the camera, so a
  strand seen edge-on is thin.
- 600 KB of file: about 30 strands at 8 segments x 48 frames (16 strands is about 300 KB); the command takes up to
  64 strands, which need fewer frames or segments. Short fur (`--length` under about 0.5) swung hard is refused as
  jumping: less `--amount`, more `--fps`.
- The strands are stepped 240 times a second whatever `--fps`, and a frame is read between two steps: the same hair
  at any `--fps`.
- The head rubs hair that lies on it only against sliding; a turning head does not drag it along.
- `--stiff` is how hard a point is pulled toward straight on from the two before it, not a material's number;
  bristles still bend.

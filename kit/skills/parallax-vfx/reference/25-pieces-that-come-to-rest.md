<!-- reference for the parallax-vfx route card: pieces that come to rest and meet (2026-11-15; the VFX methods audit, stages 10 and 23) -->

## Pieces that come to rest (a debris layer's `"rest"`, `kit vfx settle`)

**The fault it answers.** A fracture plan's pieces (`reference/22-*`) flew, bounced once and then SHRANK away in
mid-tumble. A slab that breaks leaves its pieces on the ground.

### On the debris layer
```json
{ "kind": "debris", "pieces": "slab_a", "rest": true, "life": 2.5, "speed": 30 }
```
With `"rest": true` every piece falls, bounces back a third of its fall (losing most of its sideways speed and
half its tumble), slides to a stop, tips onto its NEAREST flat face and lies there. It does not shrink: it fades
out over the last 15 % of the layer's `life`.

**The pieces meet (stage 23).** Two pieces on the ground that lie IN each other are pushed apart along their own
outlines, the smaller giving way more, as a slide (8 studs a second at most, at the plan's own size), until they
only touch. A piece that lands with its middle over a piece lying FLAT on the ground lies ON it; when that piece
is pushed out from under it, it falls. Pieces that only touch are left alone: a slab whose pieces are neither
pushed nor spun stays whole (a layer's `speed` scales the plan's push AND its spin, in the rule and in both
runtimes: a slab played slow turns its pieces slowly too). A piece jammed between
others, whose pushes cancel, stays where it is and counts as at rest: such a pile can end up to 0.04 studs deep.

`rest` is for `pieces` only (thrown rocks keep the old flight), for
a slab that lies LEVEL (the validator refuses it with `aim` / `rotate`: a wall's pieces cannot lie flat yet) and
needs a gravity of 1 or more.

### `lune run kit vfx settle <plan> [--life 2.5] [--gravity 120] [--speed 30] [--height 0] [--fps <one rate>]`
Flies the plan's pieces together by the same rule at 30, 60 and 144 frames a second and says when the LAST one
comes to rest (the latest of the three), how far the furthest lies from where it sat and how many lie on another.
It FAILS when a piece is still moving (falling, sliding or being pushed) when the fade starts (85 % of `--life`)
at any of the three, and says the life that does do; and when two pieces at rest lie in each other. Give it the layer's own `life`, `gravity` and `speed`, and with `--height` how far above the
effect's origin the layer's `point` puts the slab (a slab up high lands later). It writes nothing.

### Enforced
A beat that plans **Rigid body simulation** needs a debris layer that flies a plan that is there (`"pieces"`) with
`"rest": true`, AND the gate flies that layer's own pieces (its `life`, `gravity` and `speed`, the slab taken to sit
on the floor) at 30, 60 and 144 frames a second: every piece must be at rest before the fade with no two lying in
each other. A life too short for the pieces to land and part proves nothing. Pieces that shrink away in the air,
and thrown rocks, do not count. The validator refuses a `rest`
that is not true / false and warns on a life under a second.

### Limits, said plainly
- **REAL rigid bodies are one key away** (stage 36): `"floor": "world"` on the layer hands the pieces to the
  engine's own physics on the client - each sits in the slab until the break reaches it, is let go with the plan's
  push and spin, and falls on the real ground (a slope, a step, a wall) and on the other pieces. Seen in a Studio
  play client: 18 pieces at rest on a floor, a step and a ramp. What it costs: the pieces are solid to the local
  player while they lie (no collision group; they stop being solid when the layer is over), they do NOT follow the
  effect's clock (a hit-stop or slow motion does not hold them), and a late start lets every overdue piece go at
  once. The rest of this page is the kit's OWN rest, for
  where there is no physics to ask (the server's copy, the browser player, a layer without `floor`).
- **The kit's own rest is not a rigid-body solver.** Pieces do not meet in the AIR:
  they pass through one another until both are on the ground, so a piece can sink into another as it lands and
  then slide out of it. A meeting never turns or tips a piece and passes no speed on. A piece lies on another only
  whole (its middle over it): it is never propped on an edge, and its corners can hang over nothing. The floor is
  ONE flat height (the effect's origin): no steps, no slopes, no walls. A piece tips about one axis only. An
  effect played on a surface tilted more than about 10 degrees is SAID in the game (a warning a layer); the
  answer is `"floor": "world"`: the engine's own physics lays the pieces on the real slope (run in Roblox).
- Where two pieces meet depends on the frame rate by a little: the pile is not the same at 30, 60 and 144 frames a
  second, and the last piece's rest differs by a few tenths of a second. The RULE is the same arithmetic in the
  game and the player (the parity run: fixed steps, three frame yaws and two scales). What the parity run does not
  run is the game's uneven frame times. Where each side STARTS a piece - its place, speed, spin, half height and
  width and its flat OUTLINE at a scale and a push (`debrisStart` in both) - IS run against the rule, on every piece
  of a made slab at two scales and two pushes (56 starts); and the frame's YAW the pieces are met by (`frameYaw`) is
  read by Roblox's own CFrame (Lune's roblox library) and by the player's three.js on seven turns, tilted ones too,
  and must be each turn's own yaw (`kit/selftest/vfx/settle/run.py parity`; a wrong order of turns fails it).
- A slab played in a frame that is turned about the up axis is met by its outlines turned the same way (a piece on
  its other face is mirrored about its own axis first). A frame that is TILTED is not handled (the validator
  refuses `rest` with `aim` / `rotate`, but an effect played on a tilted surface is not caught).
- The rule runs every frame of the layer's life, also when every piece lies still (about 0.1 to 0.2 ms a step for
  64 pieces, measured outside Roblox) until a step leaves every piece exactly as it was and at rest; then it is
  not run again until another piece leaves the slab (a test: a still pile stays still at any frame time).
- A piece the break has not reached yet (its `delay`) is not met: a piece already on the ground can lie in it
  for that moment.
- Roblox's own physics (`"floor": "world"`) does the real thing in the game - run in a Studio play client on 18
  pieces over a floor, a step and a ramp (12-runtime) - and nothing in the browser player.
- **Run in the browser player and in Roblox (2026-11-15):** a made slab's 14 pieces come to rest on the floor in
  both (`python kit/selftest/vfx/player/made.py`, a made preset played from build/ by a headless browser and measured on its frames; `kit/selftest/vfx/studio/layers.md`, the same preset in a Studio play client); pieces that meet each other as REAL bodies (`"floor": "world"`) were run in Roblox on 18
  pieces (12-runtime). The rule is one arithmetic in three places (the game's
  code, the player's, `settle.py`), compared step by step over 240 steps in 19 cases, and for pieces that meet
  over 3 seconds of 13 piles (squares in each other, a square dropped on a slab, six pieces dropped on one place,
  a triangle thrown into a slab, a real slab's own pieces); how a piece is TURNED on the
  screen from its tilt and yaw (the game's CFrame, the player's quaternion): the yaw is run (above); the tilt a piece
  lies at on the screen is each side's own drawing of the rule's numbers, read by a review.
- The gate flies the slab from the height its `point` [x, y, z] lifts it to (a named point is taken to sit on the
  floor), as `kit vfx settle --height` and `kit vfx play` do. The validator does not fly anything: a layer that plans no method can
  still have a `life` too short for its pieces to land (it only warns under a second). `kit vfx play` DOES fly them (with the
  layer's own life, gravity, speed and height) and warns when they are still moving at the fade; the play goes on.

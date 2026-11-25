<!-- reference for the parallax-vfx route card: Geometry Nodes (2026-11-14; the VFX methods audit, stage 22) -->

## Geometry Nodes, baked (`kit vfx geonodes`)

**The fault it answers.** The kit built every runtime mesh with plain mesh code; Blender's Geometry Nodes - a
node tree that builds and moves a mesh, with scattering and instancing - were not used at all. Roblox cannot run a
node tree, so the tree runs in Blender (headless, from the kit) and what it makes is baked into a mesh sequence.

### Bake one
```
lune run kit vfx geonodes <name> --recipe ripple  [--waves 3] [--speed 1.5] [--amount 0.08] [--cols 20] [--rows 20] [--loop]
lune run kit vfx geonodes <name> --recipe scatter [--count 24] [--seed 1] [--size 0.08] [--speed 0.5] [--rise 0.2] [--spin 2]
                                 [--frames 32] [--fps 24] [--blender <blender.exe>]
```
- **ripple**: a Grid whose points a Set Position node lifts by rings that run out from the middle with the Scene
  Time and die at the rim. `--waves` rings across the radius, `--speed` rings a second passing a place, `--amount`
  their height. `--loop`: the rings come round a whole number of times in the sequence.
- **scatter**: points Distributed on the Faces of a disc, a small quad Instanced on each, every instance growing
  as a front that runs out from the middle reaches it and turning; Realized, so every quad is its own strip of the
  mesh. The number of quads is what the tree gives for about `--count`.
- OPEN `build/vfx/geonodes/<name>.png`: six frames from the front (heights drawn three times as tall) and above.

### Play it
```json
{ "kind": "mesh", "shape": "seq", "pivot": "origin", "params": { "seq": "<name>", "fps": 24, "loop": true }, "scale": 12 }
```
The bake is unit size (its ground is 1 wide, y up): `scale` is the ground's width in studs.

### Refused
- A mesh that **does not move** (under 0.01 of the ground a second, or under a fifth of its points moving), or
  that **jumps** a quarter of the ground in a frame.
- A ripple whose **grid slides** sideways, whose **rim lifts**, whose **rings run inward**, or that is under 0.005
  high or never goes both over and under the ground along its middle; a looped layer on a bake made without
  `--loop`.
- Asks that cannot work: `--speed` over a quarter of a ring a frame (the rings would seem to run back in), `--waves`
  at under 5 points a ring, a `--loop` whose nearest speed is far from the one asked, a `--blender` that is not
  there, a scatter the tree gives under 4 quads for.
- A scatter whose strips are **not squares flat on the ground**, whose instances **wander**, or whose quads do not
  **grow in order of distance** (half of them by the last frame, none shrinking); a layer that loops it.

### Enforced
The layer must sit by its own origin (`"pivot": "origin"`): one that does not proves nothing.
A beat that plans **Geometry Nodes effects** needs a mesh layer of `"shape": "seq"` whose `params.seq` names a
geometry-nodes bake that is there and whose OWN frames pass the checks above, played at half to twice its speed
for at least half its frames.

### Limits, said plainly
- **Not played in Roblox, not played in the browser player.** The self-test bakes both recipes through Blender and
  holds every point to the tree's own formula; that proves the tree and the bake, not the look in the game.
- It needs Blender on the machine (found as `--blender`, `KIT_BLENDER`, `blender` on the PATH, or the newest
  "Blender Foundation" folder). Baked with Blender 5.2 (the reviewer baked both recipes with 4.5 too); another
  version may name a node or a socket differently. Where there is no Blender the unit tests that bake are skipped,
  and the three self-test rows FAIL saying "NOT RUN - no Blender here": nothing is shown as checked.
- TWO recipes. The tree is built by the kit for the recipe; a tree drawn by hand in Blender cannot be baked by
  this yet, and a tree that changes its number of points from frame to frame never can (a sequence keeps its
  points).
- The file says which Blender and which nodes made it, and the checks trust that: a file written by hand to fit
  the checks would pass as a Geometry Nodes bake.
- Where it sits: with `"pivot": "origin"` (which the method gate asks for) the file's own origin is on the layer's
  point. Without it both runtimes centre a `seq` mesh on the box of its FIRST frame, which is somewhere else (and with a
  `spin` the two do not even agree on where: the player turns it about the point, the game about the box's middle -
  card vmqb). A first frame with NO thickness one way (a sheet laid flat, still water) is not settled either: how
  the engine sizes a part made from a flat mesh, and so how tall later frames are drawn, needs a Studio session.
- A scatter's quads start at a fiftieth of their size, not at nothing: a mesh is built from its first frame, and a
  first frame of points with no size has no triangle to build from. Whether Roblox builds a mesh of such small
  triangles was not tried.
- A ripple on 20 x 20 points with 3 rings is coarse (under 7 points a ring): more `--cols` / `--rows` or fewer
  `--waves`. 600 KB of file at most.

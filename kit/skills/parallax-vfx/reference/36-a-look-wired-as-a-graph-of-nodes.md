<!-- reference for the parallax-vfx route card: node-based compositing (2026-11-14; the VFX methods audit, stage 21) -->

## A look wired as a graph of nodes (`kit vfx comp`, `"graph"`)

**The fault it answers.** `kit vfx comp`'s stack is ONE shape (or source), ONE noise, ONE warp, in a fixed order:
the noise and the warp act on the whole look. A look made of parts that behave differently - a steady core inside
a halo that tears, one noise masking another, a bend of one part only - could not be said. A compositor says it as
a graph: nodes that read each other by name.

### In a comp spec
```
lune run kit vfx comp <key> --new graph      a starter: a core, and a halo torn by one noise and bent by another
lune run kit vfx comp <key>                  bake it (the starter: under a second); OPEN build/vfx/comp/<key>_strip.png
```
```json
"comp": { "loop": true,
  "graph": {
    "nodes": {
      "core":   { "op": "shape", "sdf": "disc", "radius": 0.16, "soft": 0.03, "falloff": 0.16 },
      "halo":   { "op": "shape", "sdf": "ring", "radius": 0.33, "width": 0.05 },
      "clouds": { "op": "noise", "scale": 5, "pan": [1, 0], "seed": 3, "contrast": 1.6 },
      "drift":  { "op": "noise", "scale": 3, "pan": [0, 1], "seed": 11 },
      "torn":   { "op": "mul",  "a": "halo", "b": "clouds" },
      "bent":   { "op": "warp", "of": "torn", "by": "drift", "amount": 0.03 },
      "both":   { "op": "max",  "a": "core", "b": "bent" } },
    "value": "both" },
  "ramp": [[0, [40, 6, 2]], [1, [255, 240, 200]]] }
```
- **Sources:** `shape` (every key of the stack's `shape`), `noise` (`scale`, `octaves`, `pan`, `seed`, `contrast`),
  `value` (`is`: a number 0-1).
- **Joins:** `add`, `sub`, `mul`, `max`, `min`, `screen` (`a`, `b`) and `mix` (`a`, `b`, `by`: a mask). An input is
  a node's name or a number 0-1.
- **One input:** `invert` (`of`), `levels` (`of`, `low`, `high`, `gamma`).
- **`warp`** (`of`, `by`, `amount`): the node `of` read at places bent by the node `by` - any node by any node. It
  bends by how far `by` is from its own MEAN: a noise bends everywhere, a mask bends where it is and does not slide
  the picture, a flat `by` bends nothing (and is refused as doing nothing).
- `value` names the node the picture is read from; `alpha`, when said, the node that is its alpha (else the value
  is). The stack's `ramp`, `bands`, `erode` and `halftone` follow as before; `loop` and `tile` mean the same.
- A graph stands IN PLACE of `shape`, `source`, `noise` and `warp` (it cannot be mixed with them). 3 to 24 nodes.

### Refused
- A name that names no node; a key a node does not read; a ring (a node that reads itself, however far round).
- A node **no output reads** (a typo, or left over).
- A graph in which **no node joins two others**, or with **under two shapes or noises**: that is the stack.
- A node that **does nothing**: halved, what the SHEET shows must change - by 0.002 on average, or strongly in a
  small place (a spark, a thin line), at one of three moments. A node times nothing, one hidden under a `max`, one
  that is 0 everywhere, one that only feeds a `value` no colour reads (an `alpha` node with no ramp, or a ramp of
  one colour). A constant 0 or 1 is written as a number in the join, not as a `value` node.
- Every check of a comp sheet still holds (fills, moves, packs, loops, clear or tiles, ends).

### Enforced
A beat that plans **Node-based compositing** needs a layer whose texture is a `comp` sheet with a `graph`.

### Limits, said plainly
- **Not shown in Roblox or the browser player.** Only the starter and made graphs were baked.
- The kit's own nodes, not Blender's compositor: no blur, no glare, no image input (`source` is not a node yet), no
  colour maths - a node is one grey value a pixel; colour comes from the one `ramp` at the end.
- A graph sheet does not prove the stack's own methods (signed-distance shapes, UV distortion): the gate reads
  those from the stack's blocks.
- The gate reads the spec, not the sheet: it holds that the graph is there; the bake holds that it is sound.
- "Does nothing" is measured by halving a node at three moments, at 128 px, on the value through the ramp under the
  alpha (the erosion and the halftone are left out): a node that only shows at another moment, or whose join is
  already clipped at white, can be refused though it matters. It does not catch a node cancelled by its own
  opposite (a node added to its own `invert`).
- The starter bakes in under a second at 256 px (3.4 s at 512); a 24-node graph takes a few seconds. A warp reads
  its bending node on the plain grid: a warp bent by a warp is not bent twice over.
- The method gate holds that the spec has a graph with nodes and a value; a spec the bake would refuse still passes
  the gate until it is baked.

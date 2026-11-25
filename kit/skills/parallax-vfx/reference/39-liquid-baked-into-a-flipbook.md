<!-- reference for the parallax-vfx route card: liquid, simulated and baked into a flipbook (2026-11-15; the VFX methods audit, stage 25) -->

## Liquid, simulated and baked into a flipbook (`kit vfx liquid`)

**The fault it answers.** The kit had no liquid that moves by a liquid's own rules: water was a painted texture.
Four of the owner's methods were missing - Liquid simulation, FLIP fluid simulation, Particle fluid simulation,
Foam and spray simulation.

**Never matched to a real scene.** No clip of liquid was read for this (a download waits on the owner). The tests
hold the physics; whether it looks like the liquid he has in mind is his to judge, and nobody has looked.

### Bake one
```
lune run kit vfx liquid <key> [--solver flip|pbf] [--scene dam|drop|slosh] [--gravity 4] [--fill 0.4]
                              [--seed 1] [--fps 24] [--grid 8|4] [--cell 128] [--no-foam]
lune run kit vfx
```
A tank seen from the SIDE (1 wide, 1 tall), liquid in it, gravity (in tank heights a second, a second).
- `--solver flip`: FLIP / PIC. Particles carry the liquid's speed; each step a grid is made to keep its volume
  (a pressure solve: nothing into a full cell or through a wall, the surface free) and the change is handed back.
  A couple of seconds a sheet.
- `--solver pbf`: a particle fluid (position based fluids), no grid: every particle is pushed off its neighbours
  until the liquid is nowhere denser than at rest. About half a minute a sheet; softer, more spray.
- `--scene dam`: a block of liquid against the left wall, let go. `drop`: a pool and a round body of liquid falling
  into it. `slosh`: a pool that starts tilted.
- **Foam and spray** are read off the solve, not painted: spray is liquid that has left the body, foam is surface
  liquid whose speed is being changed hard (air is beaten in); foam lasts half a second. Both are drawn brighter
  than the body, in the same sheet. `--no-foam` draws the body alone (no foam, no spray).
- The sheet is `--grid` x `--grid` cells (8: 64 frames; 4: 16) and must come to 256, 512 or 1024 px a side. The
  picture is white: the layer's own colour tints it.
- The command writes `assets/textures/<key>.json` (recipe `liquid`) and its frames; `kit vfx` packs the sheet (and
  bakes it again whenever its spec changes). OPEN `build/vfx/liquid/<key>.png`: every cell in order.

### Play it
On a sprite or a mesh's surface: `"texture": "<key>"`, its frames played once at the sheet's `fps`.

### Refused
- Before solving: a grid that is not 4 or 8, a sheet that is not 256 / 512 / 1024 px, gravity so high that falling
  liquid crosses over a fifth of the tank a frame, a dam with a fill over 0.42 (its run-up on the far wall reaches
  the top of the picture), another recipe's sheet of the same key.
- After solving (nothing is written then, and a sheet whose bake fails in `kit vfx` loses its old frames): liquid
  made or lost or outside the tank; energy that rises (over 0.0015 x gravity a particle in a step, or higher at the
  end than at the start); liquid that does not move; a picture whose drawn liquid differs from its first frame's by
  over 0.15; any liquid in the top two rows of its cell (it would be cut off); a dam or a drop baked with foam whose
  PICTURE is under 1.5 % white at its wildest moment.

### Enforced
A beat that plans **Liquid simulation** needs a layer whose texture is a recipe `liquid` sheet; **FLIP fluid
simulation** one solved by `flip`; **Particle fluid simulation** one solved by `pbf`; **Foam and spray simulation**
one of a dam or a drop with foam left on. The gate reads the SPEC, and only one `kit vfx` would bake (engine `fx`,
a block the solver takes); the sheet is what the solver gives for that spec because `kit vfx` bakes it again whenever
the spec or the solver's own code changes. Nothing compares the picture with the spec afterwards, and the gate does
not know whether the sheet was built at all (a spec written by hand and never baked still proves its methods).

### What the tests hold (the physics)
- FLIP: a still pool stays still to 1e-6 and its pressure at the bed is gravity x depth; a body in the air falls
  as gravity says (to 0.004 of the tank in a fifth of a second) and does not spread; after the pressure solve no wet
  cell fills or empties (to 1e-5 of what it did before); nothing crosses a wall.
- The particle fluid: a pool is nowhere over 8 % denser than at rest; a body falls as gravity says.
- FLIP keeps its liquid: over a dam's 64 frames its wet cells never fall under 0.93 of the first frame's and its
  drawn area stays within 8 % (before its particles were kept apart it lost 14 % and 12 %).
- Foam is SEEN: a dam's picture is over 5 % white at its wildest moment; a still pool shows none under FLIP and
  under half the least a bake needs under the particle fluid; with `--no-foam` nothing white is drawn.
- Both: the number of particles never changes, none leaves the tank, the energy a particle never rises by over
  0.0015 x gravity in a step (watched from the first step) and ends lower than it began; a dam's front runs no faster than shallow-water theory's
  2 x sqrt(gravity x height); the frames do not depend on the frames a second.

### Limits, said plainly
- **Not played in Roblox, not played in the browser player, never matched to a real scene.**
- A SLICE: there is no depth. A splash's crown, a jet turning toward the camera, a wave seen from above cannot be.
- No surface tension (no drops that bead, no thin sheets that hold), no air, nothing in the liquid's way but the
  tank's four walls and its lid. Liquid that should leave the picture cannot: it runs up the walls.
- FLIP on 48 x 48 cells with 4 particles a cell. A sheet of liquid two particles thin or less is NOT drawn (the
  picture is a blurred count of particles cut at a level): thin jets vanish or bead, and a run-up along a wall is a
  ragged thread. Its volume is not held exactly: the drawn liquid may drift by up to 0.15 before a bake is refused
  (about 0.05 on the default dam).
- Air caught in the liquid is drawn as clear HOLES in the body, not as white bubbles.
- The tank's floor and walls are the cell's own straight edges: on a sprite the liquid ends in a square cut.
- The particle fluid's pool sags by about a hundredth of the tank as it settles (it is a little squeezable) and
  loses energy faster than a real liquid would.
- Foam and spray are a rule of thumb, not a model of bubbles: no mist that hangs in the air, no foam that rides the
  surface for long, no spray that falls back as its own drops. The particle fluid's foam is noisier than FLIP's
  (its particles are jostled into place every step). How much white there is was not judged by anyone.
- A flipbook: one view, one size, played once. 64 cells at 24 frames a second are 2.7 seconds.
- Three scenes only; the body's shape and place are the scene's, not yours to draw yet.
- The method gate counts a liquid sheet (any texture) only when it was BAKED: in the effects folder's texture
  registry, which the build writes when it packs a sheet (a spec written by hand and never baked proved its methods). It does not ask whether the
  sheet is UPLOADED (an id the game can fetch): that is the owner's step, and a registered sheet with no id plays its
  fallback in the game.

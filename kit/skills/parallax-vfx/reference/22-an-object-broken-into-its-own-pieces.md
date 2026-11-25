<!-- reference for the parallax-vfx route card: breaking things (2026-11-14; the VFX methods audit, stage 5) -->

## An object broken into its own pieces (`kit vfx fracture`, debris `"pieces"`)

**The fault it answers.** The `debris` layer throws generic rock chunks from one point. Nothing BREAKS: a ground slab
that heaves, a pane that shatters, are the object's own surface coming apart - pieces that fit together until the
blow, small and fast where it lands, large and slow at the rim.

### `lune run kit vfx fracture <name> --size w,d[,h] [--shape slab|disc] [--pieces 14] [--impact x,z] [--focus 0.6] [--speed 30] [--lift 0.6] [--wave 60] [--seed 3]`
A slab (width, depth, thickness in studs; `disc` = a round plate) is cut into `--pieces` CONVEX pieces that tile it
exactly (a Voronoi cut clipped to the slab). `--impact` is where the blow lands, from the slab's centre; `--focus`
makes the pieces smaller round it. Each piece gets its push (away from the blow and up by `--lift`, slower the
further out), a spin, and the moment the break reaches it (its distance / `--wave`).
- Its checks (a plan that fails one is not written; an older plan of that name stays): `count`, `tiles` (the
  pieces' areas add up to the slab's, to a thousandth), `convex`, `slivers` (none under a twentieth of the mean
  area, none thinner than a fifth of its length, or of the slab's short side on a plank), `focus`, `outward`. About
  one seed in ten fails `slivers`: take another `--seed`. A refused cut leaves the picture alone too.
- The name is lowercase letters, digits and `_` (the game finds a plan by its exact letters).
- Writes `assets/effects/fractures/<name>.json` (in the game: `VfxPresets.fractures.<name>`) and
  `build/vfx/fracture/<name>.png`: the cut from above with the blow marked, and the pieces a quarter of a second
  later. OPEN it.

### Flying it
A debris layer with `"pieces": "<name>"`: every piece starts where it sat in the slab (the layer's `point` is the
slab's centre on the ground, `aim` / `rotate` turn it), waits for the break to reach it, then flies by the debris
layer's own flight (gravity, the bounce, the shrink at the end of `life`). `speed` (ONE number, above 0) is the
plan's `--speed` over again: every push is scaled by it (the piece nearest the blow flies a little under it, and
no piece flies quite flat: a tenth of the push is always up). `life` must outlast the break (a piece the break has
not reached when `life` is over never moves). `material`, `color`, `gravity`, `outline`, `toon` as on any debris (`toon`: flat
in the game - SmoothPlastic - and cel-shaded in the player). The player's hot reload reads a plan cut again. A layer that names a plan the game or the player does not have flies NOTHING and warns. `count`, `size`, `spread`,
`shape` and the rock keys are not read (the validator says so). The slab's texture places are on the pieces (a
`piece` mesh's UVs are its place in the slab), so a surface could break with them: no layer key sets that texture
yet, and which way up the game shows it against the player is not settled (card vmqb).

### Enforced
A beat whose words say shatter, fracture, crumble, breaks apart, splits apart or cracks open must plan **Fracture
simulation** or leave it out with a reason the owner reads on the chart (an ASK method, `reference/18-*`). Planned,
a debris layer of that beat must carry `"pieces"` naming a plan that IS in `assets/effects/fractures`, with a speed
above 0 and a `life` longer than the break takes to reach the last piece: thrown rocks, a misspelt name or pieces
that never leave do not count.

### Limits, said plainly
- **Run in the browser player and in Roblox (2026-11-15)** on a made slab of 14 pieces (`python kit/selftest/vfx/player/made.py`, a made preset played from build/ by a headless browser and measured on its frames; `kit/selftest/vfx/studio/layers.md`, the same preset in a Studio play client): in the player
  the slab breaks, its pieces fall a fifth of the frame's height and lie at rest; in Roblox all 14 pieces are
  meshes (after `Vfx.prewarm`), lie on the floor and are gone when the layer ends. The plan is proven (the pieces make up the slab, painted
  pixel by pixel); the piece's solid is the same from the game's code and the player's (both texts run on three
  outlines); the layer's code is type-checked. How a break LOOKS on a real piece: nobody has judged one.
- A FLAT slab only: no cutting of an arbitrary 3D object, no cracks before the break, no pieces breaking again.
- The flight is the debris layer's: no piece meets another, none comes to rest lying flat.
- Up to 64 pieces; the debris layer's count cap of 40 does not apply to pieces `kit vfx cost` counts each piece as a
  built mesh for the whole effect (against the default ceiling of 100).
- In the game each piece is its own mesh, and building one takes a quarter of a second: call `Vfx.prewarm(name)`
  when the effect becomes possible. Without it a first play flies BLOCKS of each piece's size (they overlap) and
  swaps the real pieces in as they are built. A published game without "Allow Mesh & Image APIs" flies the blocks
  throughout.
- Every piece is cut at least 0.05 studs wide (`meets`: the pieces' rule parts two pieces only when they lie deeper in
  each other than 0.02 studs - a thinner piece could lie wholly inside another, unparted); the method gate measures a
  hand-edited plan's pieces from their own points and refuses one narrower, or a line of points.
- A piece's width is measured exactly (each edge of its hull and the point farthest from it), not sampled: a thin
  slanted sliver or points on a slanted line are refused whichever way they lie.

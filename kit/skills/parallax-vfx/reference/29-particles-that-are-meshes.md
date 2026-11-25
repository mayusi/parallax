<!-- reference for the parallax-vfx route card: mesh particles (2026-11-14; the VFX methods audit, stage 14) -->

## Particles that are meshes (a swarm of `"shape": "Rock"`)

**The fault it answers.** A Roblox ParticleEmitter emits flat pictures only. The kit's scripted particles (the
`swarm` layer) could be steered - curl, attraction, an authored field, drag, a floor - but they were balls and
blocks; its real stones (the `debris` layer's `rock`) could only be thrown and fall.

### On a swarm layer
```json
{ "kind": "swarm", "shape": "Rock", "count": 24, "material": "Slate", "size": [[0, 0.6], [1, 0.3]],
  "rock": { "cuts": 9, "jag": 0.5 }, "tumble": [2, 6], "field": { "name": "whirl" } }
```
- Every particle is one of the kit's faceted stones (the debris layer's stone: `rock` takes its `cuts`, `jag`,
  `spike`, `flat`, in the same ranges) - eight different stones, cycled through the swarm - turning about its own
  axis at a speed between `tumble`'s two numbers (radians a second; `[2, 6]` unless said).
- Its `material` is Slate unless said (a swarm of balls is Neon unless said).
- `size` is the stone's LONGEST side. Everything else is the swarm's: `curl`, `attract`, `field`, `gravity`, `drag`,
  `floor`, `color`, `transparency`, `lifetime`, `spawn`.
- 40 at most, and no `trail` (the validator refuses both).

### Enforced
A beat that plans **Mesh particle effects** needs a swarm of `"shape": "Rock"`, a debris layer of `"shape": "rock"`,
or a debris layer flying a fracture plan's `pieces`. A swarm of balls or blocks, or debris blocks, no longer count.

### Limits, said plainly
- **Run in the browser player and in Roblox (2026-11-15)** on a made swarm of 24 stones (`python kit/selftest/vfx/player/made.py`, a made preset played from build/ by a headless browser and measured on its frames; `kit/selftest/vfx/studio/layers.md`, the same preset in a Studio play client): in the
  player the stones draw and fly; in Roblox, after `Vfx.prewarm` and twelve seconds, 8 of the 24 were meshes 0.2 s
  into the layer (the others blocks) and all 24 by 2.2 s. There is no rule here that could be run outside them:
  this stage is checked by the validator's tests and the gate's, by the type checker, and by parsing the player.
- In the game every stone is its own runtime mesh and takes about a quarter of a second to build: each particle is
  a BLOCK until its stone is built and swapped in. `Vfx.prewarm(name)` builds them all ahead (about ten seconds for
  40, once); WITHOUT it a first play of 40 shows blocks for several seconds. Played stones go back to a pool that
  keeps up to 6 of each of the eight (48 meshes a stone setup, kept for good). A game without "Allow Mesh & Image
  APIs" keeps the blocks throughout.
- The browser player draws the same EIGHT stones the game cycles (particle i is stone i % 8, each stone drawn as
  instances of itself).
- The game's and the player's random numbers are not the same generator: which way each stone turns differs.
- `kit vfx cost` counts each stone as a built mesh for the whole effect, and a debris layer's thrown rocks too
  (found by running it: the line said `starblade` holds 25 meshes at once where a Studio play client held 127 -
  four rock layers; it now says 128 built at once, over the default ceiling's 90 in use: the game builds every
  rock, stone and piece when the effect is set up and holds it until the effect is over, whatever the layer's `at`).
- Stones only: no other mesh shape, no uploaded mesh.

<!-- reference for the parallax-vfx route card: point cloud (2026-11-14; the VFX methods audit, stage 18) -->

## A point cloud a swarm gathers into (`kit vfx points`)

**The fault it answers.** A swarm's particles could be thrown, swirled and blown along a field, but never brought
to a SHAPE: motes that form a sigil, a letter, a ring and then let go.

### Make a cloud
```
lune run kit vfx points <name> --new ring|disc|sphere|spiral|star [--count 60]
lune run kit vfx points <name> --picture <png> [--count 60]      points on a picture's own bright pixels
lune run kit vfx points <name> [--pull 8]                        check a cloud that is there; when is it whole?
```
- The file is `assets/effects/points/<name>.json`: `{ "points": [[x, y, z], ...] }`, 8 to 150 points, unit size (the
  farthest point is 1 from the middle). A cloud is never overwritten.
- `--picture`: a picture you have (a sigil, a crest, a letter). On a clear ground whatever is opaque is the figure
  (black ink too); on an opaque light ground its dark pixels are; on an opaque dark ground its bright ones. The points are spread evenly over it, standing upright.
- OPEN `build/vfx/points/<name>.png`: the points from the front and from above.

### On a swarm layer
```json
{ "kind": "swarm", "count": 70, "cloud": { "name": "<name>", "size": 6, "pull": [[0, 0], [0.4, 10], [1, 10]] } }
```
- Particle i is drawn to point i (round again when there are more particles than points). `size` is the cloud's
  radius in studs (4 unless said), about the layer's `point`.
- `pull` is how hard, a number or a curve over the LAYER's life (8 unless said; 0 lets go): a particle that starts
  a few cloud sizes away is on its point about 8 / pull seconds later (later at a high pull on long frames: a pull
  of 60 takes 0.18 s at 60 frames a second, 0.33 s at 15). It never flies off, whatever the frame rate; from rest
  it never passes its point (thrown at its point fast, it passes once and comes back).
- The pull is applied last in a particle's step: `gravity` sags a held particle by gravity / pull^2 studs (20 at a
  pull of 8: a third of a stud).
- Everything else the swarm has still acts: `curl` makes the shape shimmer, an `attract` or a `field` fights it.

### Refused
A cloud whose points are not unit size, are a clump (under 0.8 long or 0.15 wide), sit on top of one another, or
leave one point far from all the others (over 6 times the usual gap).

### Enforced
A beat that plans **Point cloud effects** needs a swarm layer whose `cloud.name` names a cloud that is there and
passes those checks, and the shape must be SEEN: at least as many particles as the cloud has points (40 at most
for a swarm of Rock), a `size` of half a stud or more, and enough pull for long enough - the pull over the layer's
life, and the peak pull over a particle's longest `lifetime`, each come to 8 (a particle needs about 8 / pull
seconds). A pull of 8 with a lifetime of 1 s just passes.

### Limits, said plainly
- **Run in the browser player and in Roblox (2026-11-15)** on a made star of 60 points and a swarm of 70
  (`python kit/selftest/vfx/player/made.py`, a made preset played from build/ by a headless browser and measured on its frames; `kit/selftest/vfx/studio/layers.md`, the same preset in a Studio play client): in the player the scattered specks gather into the star; in Roblox a scatter 16 studs wide and
  deep becomes the flat figure (11.3 x 12 studs, 0.13 deep; the cloud at `size` 6 is 11.4 x 10.9). The rule
  (`cloudPull`) is one arithmetic in the game's code,
  the player's and `points.py`, compared in 2,000 cases; how each side finds a particle's point (which point, the
  layer's `point`, the scale) was read, not run.
- The cloud does not turn with the effect: its x, y, z are the world's (an authored field's the same).
- A cloud under 0.15 wide is refused as a clump: a straight line of points, or two small figures far apart, cannot
  be a cloud.
- Nothing runs the two call sites against each other; `kit vfx play` refuses a cloud whose points are not 8 to 150
  triples and runs the command's own full checks (a clump, a line: it warns and the play goes on).
- 150 points at most (a swarm's particles). It is a shape of dots, not a surface.
- A picture's points are picked by weighted chance and spread by taking the farthest of 24 picks: even to the eye,
  not exact; another `--seed` gives another spread.
- Which particle goes to which point is by number, not by nearness: paths cross on the way in.

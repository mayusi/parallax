<!-- reference for the parallax-vfx route card: an authored vector field (2026-11-14; the VFX methods audit, stage 11) -->

## An authored vector field (`kit vfx field`, a swarm layer's `"field"`)

**The fault it answers.** The swarm's only field was `curl`: generated noise, the same swirl everywhere. When the
particles of an effect must go SOMEWHERE - round a column, up a fountain and out, along a line drawn through the
air - someone has to say where the air goes.

### The field: `assets/effects/fields/<name>.json`
```json
{ "schema": 1, "bounds": 8,
  "elements": [ { "kind": "wind",   "dir": [1, 0, 0], "speed": 4 },
                { "kind": "vortex", "at": [0, 0, 0], "axis": [0, 1, 0], "radius": 4, "speed": 12, "pull": 3, "lift": 2 },
                { "kind": "point",  "at": [0, 2, 0], "radius": 3, "speed": -8 },
                { "kind": "path",   "points": [[-6, 0, 0], [0, 4, 0], [6, 0, 0]], "radius": 2, "speed": 10, "pull": 6 } ] }
```
The air's velocity at a place is the SUM of the elements (up to 16). Places are studs from the swarm layer's
`point`, along the WORLD's axes (a field does not turn with the effect). Speeds are studs a second.
- **wind**: one direction, everywhere.
- **vortex**: turns round the line through `at` along `axis`, fastest at `radius` (still on the axis, fading
  beyond); `pull` draws in toward the axis, `lift` blows along it. A negative `speed` turns the other way.
- **point**: pushes away from `at` out to about `radius`, strongest a third of the way out and dying to nothing AT
  the point; a negative `speed` pulls in (specks come to rest at the point, they do not shoot through it).
- **path**: flows along the drawn line and (`pull`) draws specks onto it, within about `radius` of it. Past its
  last point the specks do not stop: they come to hang `speed x radius / pull` beyond it (end a path where the
  particles' lifetime ends, or put a `point` there to scatter them).
- `bounds`: the half-size of the space the field is made for (what the check and the picture look at).

### `lune run kit vfx field <name> [--new vortex|wind|fountain|path]`
`--new` writes a starter to edit (it never overwrites a field). Without it: the file is checked and
`build/vfx/field/<name>.png` is drawn - 64 specks let go in the bounds, their trails from above and from the side,
brighter where faster. OPEN it. The checks: every element's keys and ranges; `moves` (somewhere inside the bounds
the air moves); `bounded` (no speed over 400); `carries` (specks let go in the bounds, and beside each element,
GET somewhere). A field that fails is not drawn. Run it again after every edit of the file.

### On a swarm layer
```json
{ "kind": "swarm", "point": [0, 2, 0], "count": 80, "lifetime": [1.5, 2.5],
  "field": { "name": "whirl", "follow": 6, "gain": [[0, 0], [0.2, 1], [1, 1]] } }
```
Each particle's velocity is drawn toward the field's where it is: `follow` a second (6 unless said; high = it
rides the field, low = it drifts into it; the same at any frame rate). `gain` scales the field (-5 to 5; a number
or a curve over the layer's life; negative runs it backwards). `curl`, `attract`, `gravity` and `drag` still add to it. A layer that names a field
the game or the player does not have warns and plays without it; `kit vfx play` refuses the preset.

### Enforced
A beat that plans **Vector field-driven effects** needs a swarm layer whose `field.name` names a field that IS in
`assets/effects/fields`, is a field that passes `kit vfx field`'s own checks (an empty or broken file, or air
that stands still, does not count), with a gain that is not 0 all its life (or a swarm with `curl`: the generated
field). The validator refuses a field block that is not `{ name, follow, gain }` or a name the game could not
find; `kit vfx play` refuses a field file with no elements.

### Limits, said plainly
- **Run in the browser player and in Roblox (2026-11-15)** on a made vortex field and a swarm of 80 (`python kit/selftest/vfx/player/made.py`, a made preset played from build/ by a headless browser and measured on its frames; `kit/selftest/vfx/studio/layers.md`, the same preset in a Studio play client):
  in the player the swarm's centre moves and it spreads as the air turns it; in Roblox the specks are carried at
  4.9 studs a second, lifted (4.5 to 6.3 studs up) and spread (2.4 to 4.4 studs from their middle). The field's
  rule is one arithmetic in three places (the
  game's code, the player's, `field.py`), compared at 1,000 places; how a swarm rides it (the follow step in each)
  was read, never run.
- Not a simulation: nothing in the field is pushed back by the particles or the world, and it does not change over
  time (only `gain` does). Not a baked 3D grid (.fga): Roblox has nowhere to read one.
- The field keeps the world's axes: an effect played turned does not turn its field.
- The method gate AND `kit vfx play` run a field's own checks (the play warns and goes on: a field whose air stands
  still in its bounds, or carries nothing, is said by name). The GAME does not: a hand-edited file reaches it
  unchecked (a radius of 0 is passed over, never a NaN). The player's hot reload reads a field made again (and a fracture plan, a point cloud), and a variant
  that names a field of its own has it in its bundle. The in-engine booth capture does not load fields: what
  would show one there is a capture run in Studio, which the owner has set aside (no Studio VFX).
- Every particle asks every element every frame (150 particles x 16 elements at most); `kit vfx cost` adds
  it to the Luau time at 1 microsecond an element a particle - an ESTIMATE, not measured in Roblox.

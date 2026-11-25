---
name: parallax-world
description: Build Roblox levels and maps (battlegrounds arenas, lobbies, obbies, towns, interiors, open terrain) from JSON blueprints with generators — rooms, parametric buildings with stairs, cover, paths, breakables, walls, rings, scatter, spawns — terrain made by rivers and real elevation, scanned materials and vetted CC0 meshes, lighting; PROVEN to play by numbers (R6 reachability, traps, spawn fairness, camera clearance, knockback room, sightlines) and LOOKED AT from a player's eyes beside measured references, then walked in Studio. Use for any building / level / map task.
---

# parallax-world — the route card (the detail is in `reference/`; the record is in `kit/knowledge/vault/world/`)

Start: `lune run kit status --dept world`, then `kit help --stage world:<stage>`. A world lives in its game:
`games/<Name>/assets/worlds/<World>.json` (`kit game new` / `--game <Name>`; `games/.active` is shared — never flip it).

## The clock and the route (the owner, 2026-11-10: "Yes, same budgets" - card b6m2)
- **The clock**: a piece gets 3D's budgets - 10 minutes simple, 30 complex, 60 hero (its spec's `"tier"`, a UI
  screen's `"quality"`; a world is complex unless it says; hero only with `kit approve`). `kit world` (every blueprint) starts the clock of any blueprint new or changed since the last build.
  A change is a change to what the piece is made of (its spec, the assets it names, a dossier's clip sources) -
  never a look's own output. Past the budget NO CHANGE builds (the piece as it was may still be played, looked
  at, rebuilt): show the owner what there is and its open cards; only his words reopen it: `kit clock world
  <name> --extend <minutes> "<his words>"` or `--restart "<his words>"`.
- **The route**: terrain (heightmap land) and/or mesh skins on its generators. A piece made a NEW way (a way gained, not one dropped) refuses its build until
  `kit answer world <name> --reroute` and every lesson is answered again for the new route (a copied answer
  does not count).

## The owner's rules
1. Quality, not quantity: ONE world pushed to impressive beside its references (SampleRegion); five mediocre worlds
   missed the point. New worlds only when the owner asks.
2. "The quality of the terrain is horrid": land is made by RIVERS (stream-power incision) and the painter, and by
   real elevation data — never noise + thermal erosion alone (talus-angle cones).
3. Real meshes are the jump: scanned rocks / cliffs (Poly Haven CC0), generated trees, meshed buildings; primitive
   parts (lollipops, boxes, prisms) cap the look. Stylised packs never in a realistic world.
4. Words make generic maps: references first (game maps, real places, stills measured by script).
5. A top-down render cannot judge a world: eye-level shots beside the references; Studio is the proof.
6. Direction before building (the owner, 2026-10-24: "the craft is fine, creative DIRECTION is the gap"): every
   original piece gets `kit world direction <Piece> --new` - intent, ONE idea, >= 6 references from >= 3 media
   (take / leave), 3 pillars, bans, three directions that differ on >= 2 axes, each a `kit world frame` render from
   the kit's real pieces; `kit world board` shows the owner; build only to the pick. `kit world colorscript` lays the
   places out in journey order (palette, value, warmth): neighbours with no change of mood get re-thought.

## The route (direction + 8 stages)
| # | Stage | Its gate | Read |
|---|---|---|---|
| 0 | direction | `kit world direction <Piece>` ready -> the owner's pick in `## Pick` (frames: `kit world frame <scene.frame.json>`; board: `kit world board`) | `kit/direction.py` |
| 1 | refs | ≥ 6 real stills measured (horizon line, value structure, haze, palette, landmark placement) into REFS.md; a world identity from the numbers | `reference/01-*` |
| 1b | lessons | `kit world lessons <Name>`: the world lessons ranked for this world by its own words (blueprint, brief, direction) as a sheet (`<worlds>/<Name>.lessons.md`); each ANSWER lesson (up to five) applied (how) or skipped (why), 6+ words, before anything is built; run it again to check: passed, the applied ones are recorded on the world (the owner's verdict credits or flags each) and board/answers.json keeps what was asked and the text that passed - `kit world plan` reads the stage done for that text only - a town / interior world's plan also offers the past house layouts (`*.layout.json`) as examples, never a template | `kit world lessons <Name> --show` |
| 2 | terrain | `kit world terrain <Name>` (rivers `--stream`, `--thermal`, droplet `--erosion`, the painter, keep masks, the lake-bed `anchor`; real elevation `--dem` where the world mission adds it); LOOK at the relief and the paint | `reference/03-*` |
| 3 | materials | the painter's roles as MaterialVariants from the scans (`kit materials --fetch <ids> --res 1K`) | `reference/03-*` |
| 4 | meshes | `assets/worlds/imports/<set>.json` -> `kit world import` (split, ≤ 20k tris, 1024 textures); forest / rocks / spires use them; ≤ 10k parts; no z-fighting | `reference/02-*` |
| 5 | dressing | roads FIRST (scatter, cover, breakables keep off them); set dressing by story | `reference/02-*` |
| 6 | check | `kit world check <Name>`: 0 errors (reachability with the real jump arc, traps, spawn fairness, camera, knockback room, sightlines); look lint clean (floaters, buried, trees in buildings, rocks on roads) | `reference/04-*` |
| 7 | look | `kit world look <Name>`: every STATION at 1920 x 1080 (each spawn behind the rig, the blueprint's `views`, back from each objective, from above), labelled, ONE PAGE each - its reference still above ours at the same framing (`build/worlds/look/<Name>/pages/`; which still, its crop, or "none": `refs/<Name>/stations.json`). Open EVERY page: one difference + one edit per station. `kit world` ends with `LOOK: <folder>` lines and renders a changed world itself. `kit world shots` daily; `kit world web` = art direction, not proof | `reference/01-*` |
| 8 | studio | `kit world studio <Name>`: the SAME stations in Roblox Studio's own light (Blender's is a stand-in) - it makes the scratch place (the world alone; nothing saved or uploaded, so plain parts, no meshes) and `capture.luau`; open that place, start `kit world studio <Name> --capture` in the background, run the script ONCE through the MCP (that window's studio_id, never another place's) -> three panes a station: reference, Blender, Studio. Then `rojo serve games/<Name>/default.project.json`; the MCP walks the stations with 0 console errors; the OWNER walks it; `kit verdict world` | `[[shared/studio-mcp]]` |

Generators (studs; rot = degrees like CFrame.Angles; N = -Z, S = +Z, E = +X, W = -X): rooms, buildings with stairs,
cover, paths, breakables, walls, rings, scatter, forest, ruin, tower, bridge, grace, pine, palm, palisade, peak,
dunes, city, crosswalk, row — every parameter in `reference/02-*`. A TOWN is planned, not typed: a `town` step lays
out a square entered at its corners, streets that end on house fronts, blocks of terraced lots on a 4-stud grid and
one landmark on the main gate's line of sight; `kit world town <Name>` draws the plan from above with its numbers
and its kit of house types — open it before dressing anything; `kit world town <Name> --kit` writes one house
mesh recipe per type for a town that names `"skins"`, then `kit world meshes --set town_<World>` makes them
(`reference/05-town-plan.md`).

**Methods the lane holds you to** (the owner, 2026-11-13: every method on his list built into the pipeline "and
enforced in the terms of being used"; the list and what enforces each: `board/plans/archive/2026-11-13-world-methods-audit.md`):
- a place of houses is laid out by its plan: the build refuses 12 or more `building` steps typed one by one (one
  `town` step instead; the owner alone may waive it: `kit approve world <Name> "<their words>" --by owner --waive layout`);
- `kit world check` fails a `city` grid, a `town` with no `"skins"` and a typed `building` with no `"skin"`; a skin
  that does not fit its house fails the compile (`kit world town <Name> --kit` cuts every recipe to fit);
- every build of a world with a town ends on its plan page (a `LOOK:` line): read it before dressing;
- a road, a row, a palisade or a wall along points that turns more than 20 degrees at a typed point says how it
  bends, or the build stops: `"curve": true` (the smooth line through its points) or `"curve": false` (a hard corner,
  meant). A river shape of `kit world terrain` takes `"curve": true` too;
- any step stands on any angle with `"turn": <degrees>` (`reference/02-*`); `kit world check` measures a lane that
  runs on neither axis across itself, on the parts;
- a town says how its streets run, or the build stops: `"bend": <3 to 8>` (its blocks of houses turned and settled
  round the square: streets that funnel and meet at odd angles) or `"bend": 0` (straight, meant). A bent town sets
  its own spawn pads at its gate with `"spawns": 2` (`reference/05-town-plan.md`);
- a world whose played part (far scenery left out) reaches more than 1,024 studs across says how it streams, or
  the build stops: `"streaming": { "cell": 256 }` (every step a Model with the engine's far stand-in, a step wider
  than a cell cut by cells; `reference/04-*`). StreamingEnabled itself is the game project's switch: the build
  also stops a world that says `"streaming"` while the game's `default.project.json` leaves it off (Workspace
  `"$properties": { "StreamingEnabled": true }` - the project file is the game's: ask before changing it);
- a world that streams says how its players move, or the build stops: `"streaming": { "speed": <studs a second,
  16 on foot>, "fall": <their highest drop> }`. The game's project is then held to it (4 s of that way kept
  loaded, twice that streamed in, the engine's pause for players faster than a walk; a long drop's landing named
  as an arrival); every landmark - typed, a tower of 60, a house of three storeys, a town's - says `"stream":
  "always"` or `"area"` (`reference/04-*`);
- a house big enough for two rooms (a typed `building` 20 studs or more on a side; a town's `"house"`) says
  whether it has rooms, or the build stops: `"rooms": true` (each floor cut by rule into rooms with a doorway each,
  every room reached from every other, the stair hall kept clear) or `"rooms": false` (one open room a floor, meant);
- a town says how its land lies, or the build stops: `"slope": { "rise": 4, "toward": "N" }` (a hillside: tilted
  ground, the houses step up it) or `"slope": false`;
- a town says whether its yards are dressed, or the build stops: `"yards": true` (each shut yard opened by a court
  and a gate in place of one house, then woodpiles and wash lines by rule) or `"yards": false`;
- a town with `"skins"` says how its houses are made, or the build stops: `"facade": true` (modules by a grammar:
  5 meshes a storey height and 3 for the town, houses of one type differ) or `"facade": false` (one whole mesh a house type);
- a town says whether its square holds a market, or the build stops: `"market": true` (stalls by rule, the gate's
  view and the streets' mouths kept clear) or `"market": false`;
- a town's lamps come from the town (`"lamps": true`: one at each gate, each mouth of the square, each crossing no lamp lights yet),
  never from a `row` along its streets: `kit world check` fails a world whose middle lamp has 3 others within 80 studs.

## What never worked (`kit/knowledge/vault/world/graveyard.md`)
Five showcase worlds instead of one · terrain from noise + thermal erosion alone · a backdrop range from long
straight ridges (reads as a wall; peaks = two short ridges crossed, lower than the hero landmark, far land under
them) · primitive-part trees / buildings / rocks.

## Traps (the full list: `lune run kit lessons world`)
Erosion moves the min height (anchor the lake bed; keep basin / plateau / ramp) · a far-terrain ring's middle sinks
(centre y) · water lit by coloured light goes muddy (light by strength, keep its hue) · Rojo model JSON `Content`
properties are implicit strings · web shaders unroll loops (textureLod, one call site) · headless Edge hands the
page to a child (kill by profile dir; timers not rAF) · the jump arc is real (v = sqrt(2gJ)) · unreachable warnings
must ignore thin strips · heightmap pixel edges terrace (blur) · ring gaps must be fewer than segments.

## Read next
`reference/01-the-workflow-*.md` · `reference/02-generators-*.md` · `reference/03-terrain-lighting.md` ·
`reference/05-town-plan.md` · `board/plans/archive/2026-11-13-world-methods-audit.md` (what the lane has, and lacks) ·
`kit/knowledge/vault/world/index.md` · `board/plans/archive/2026-10-12-world-pipeline-v2.md` · `[[shared/reference-tools]]`.

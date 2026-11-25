<!-- reference for the parallax-world route card: the town-plan generator (2026-11-13, the world methods audit) -->

## A town by plan (`"town"` step, `kit world town <Name>`)

The `city` generator is a regular grid of box buildings. A `town` step is a PLAN, made the way old towns stand, and
expanded by the compiler into steps it already knows (floor, building, wall, fit) — so the check, the look and the
Studio stage read a town like any other world. Code: `kit/lib/worldtown.luau` (pure, seeded); the page:
`kit/world/townplan.py`.

```json
{ "town": { "name": "Old Town", "center": [0, 0, 0], "area": [320, 320], "seed": 7, "gates": ["S", "E"],
            "mats": { "street": "cobble", "square": "flag", "block": "pave", "wall": "plaster", "wallAlt": "brick",
                      "roof": "slate", "landmark": "hall" } } }
```

What the plan does, by rule:
- **The square is entered at its corners, pinwheel-wise** (Camillo Sitte's "turbine" square): each of the four arms
  leaves along one edge, so no street crosses the square and every view across it ends on a house front. An arm to a
  side named in `"gates"` is a main street that runs out of the town there; the others are lanes.
- **The landmark** stands on the square's wall where the FIRST gate's street points: its lot is set out first, its
  middle on that line of sight, two storeys over the tallest house the town may build. `"landmark": { "width": 40,
  "floors": 6, "name": "Hall" }`; one typed no taller than a house is refused. Replace its building with your own
  piece by reading its lot from the plan page. (Should no row of houses stand there the build WARNS: say so on the
  board.)
- **Lanes and alleys end on another street** (T-junctions), never opening onto the square and never lined up across
  a street into a crossing. `"ring": true` (the default) runs a wall street inside the edge: every lane closes into a
  loop, no dead end. The plan builds NO town wall: beyond the wall street the edge is open ground (add `wall` steps
  with gaps at the gates). `"ring": false` lets the lanes run out of the town.
- **Blocks are built round their edge in terraced lots**: two rows back to back or round a yard; a block too shallow
  for two rows gets THROUGH houses (door on the better street, windows on both). No street shows an empty half block.
- **Every line lies on a 4-stud grid** (`"grid"`), and lots come in a few sizes (`"lots": { "width": [16, 24],
  "depth": [24, 24], "yard": 12 }`), so a town's houses fall into TYPES (`<front>x<depth>_<storeys>f<storey height>`,
  `_e` / `_w` = a corner's windowed flank, `_t` = a through house). A frontage no count of such lots fills exactly
  gets one lot of an odd width (one more type). One house mesh per type skins every house of it: `"skins":
  "<prefix>"` (a name, nothing else) gives each house the skin `<prefix>_<type>` (kit world meshes kind
  `gothic_house`; a skin's footprint is the lot less one wall thickness, and less the trim gap: the plan page's
  record lists it per type). `"floorHeights": [14]` and a single lot depth keep the kit small. Without `"skins"` a
  NEW world's town fails the design gate, as a typed street of plain buildings does.
- **Heights**: taller on the square and the main streets (`"floors": { "square": [3, 4], "main": [3, 4], "lane":
  [2, 3], "alley": [2, 3] }`, each a range of whole storeys, least first); two houses side by side in a row never
  stand to the same top. A rank left only ONE possible top (one storey count and one storey height) cannot keep that
  rule: the build warns.
- **Scale**: a house's wall faces stand ON its lot's lines (with trim: a stud and a half inside them, see below), so
  a street measures what it is planned at (`"streets": { "main": 32, "lane": 12, "alley": 8 }`; the R6 sheet wants a
  street >= 30 and an alley >= 8). Every street with houses on both sides claims its width (the wall street does
  not); in a world with `"scale": "r6"` `kit world check` measures each claim between the walls.
- `"house": { ... }` = building fields every house takes (windows, roof, slab, trim, glass, thickness, door size).
  Its `"windows": { "sides": [...] }` are the HOUSE's own sides (its front is S), turned to every lot; left out,
  a house has windows on its street faces. With trim (`house.trim` or `mats.trim`) houses stand a wall and a stud
  apart on every side (`"gap"`), so their posts, bands and ridge beams share no plane.
  `"square": { "at": [x, z], "size": [96, 72] }`, `"block": [40, 88]` (the shortest block worth cutting off, the
  longest left uncut). `"claims": false` drops the scale claims. A value typed wrong (`"area": [256]`, a storey range
  backwards) is an error, never a silent default.

`lune run kit world town <Name>` draws `build/worlds/town/<World>_<Town>.png`: the plan from above — every street
with its name and width, every lot shaded by its storeys with its door marked, the gates' walk to the square in
seconds, the landmark and the main gate's line of sight, T-junctions / crossings / dead ends — and beside it the
layout's numbers (loops, dead ends, the square's walled share, the farthest walk, the built share of the street
fronts) and the kit of house types. OPEN IT before dressing anything. The numbers are for reading a layout, never a
score: the owner's verdict is the only one.

## Bent streets (`"bend": <degrees>`) and the town's own spawn pads (`"spawns": 2`)

The plan above is cut on two axes. `"bend": 8` twists it round the square: a block of houses stands where the twist
carries it and is turned by the twist's own rotation there - a few degrees near the square, up to about one and a
half times the bend at the town's edge, each block by its own angle (the seed picks which way the town twists).
Every block (its houses, yard walls, pavement) moves and turns as ONE rigid piece: nothing shears, every house and
every mesh skin is the house of the straight town. The blocks are then settled against each other until each two
across a street stand, at their nearest, as far apart as planned: **no street is narrower than typed; it is its
planned width at its narrowest, give or take, and widens along its length** by what its two sides' angles differ.
Measured over 48 towns at bend 8, the narrowest point of a street between two facing blocks: an 8-stud alley 8.3
studs on average (15.8 in the worst case), a 12-stud lane 12.8 (19.8), a 32-stud main street 32.8 (38.0). What you
get is funnels and odd angles - streets whose two sides are not parallel, lanes that meet off the square - not
sweeping curves. `"bend"` is 0 to 8 (past 8 the blocks round a crossing have turned too far against each other for a
street's middle line to run between them: measured, and refused); `"bend": 0` is the straight town, said on purpose.
**A new world's town must say one or the other: the build stops a town with no `"bend"`.** Same plan either way:
same lots, same types (the same kit of houses skins both), same street graph. `kit world town <Name>` draws it as it
stands; `kit world check` measures every bent street across itself, piece by piece, on the houses' own walls. The
landmark was in view from the main gate in every town tried (48 at bend 4, 48 at bend 8); the page says so for
yours, or says it is not.

A bent town carries its gate away from any coordinate you could type: let it set its own spawn pads -
`"spawns": 2` (1 to 8; `mats.spawn` names their palette entry) puts them inside the main gate, in pairs across the
main street. Anything else you place in a bent town by hand: read where it stands from the plan page first.

**Lamps with a reason** (`"lamps": true`, `mats.lamp` and `mats.lampLight`): the town sets its own lamps, one
where a walker decides something - at each gate and at each mouth of the square (and at a crossing of four ways that
no gate's lamp already lights; in the towns the plan makes today every crossing is the one just inside a gate, so in
practice gates and mouths). Each stands at the foot of a house corner within 40 studs of its node, its arm toward
the junction; no two nearer than 24 studs. That is 5 to 7 lamps in the towns tried. The rule holds itself to the
owner's measure: where a small square puts its mouths and a gate all within 80 studs of each other, lamps are taken
away (never a gate's) until the middle lamp has fewer than 3 others within 80 studs. NEVER a `row` of lamps along a
town's streets, and not a lamp at every junction: measured over 30 towns that is 14 to 41 lamps, and in 18 of the 30
it is the "lamp everywhere" the owner hated and `kit world check` fails. The plan page marks each lamp with a warm
ring and counts them by reason.

**A market on the square** (`"market": true`, `mats.stall` and `mats.cloth`): stalls (a counter, four posts, a cloth
awning) in rows on the square, about a third left out by the seed, each turned up to 6 degrees. They keep clear what
the square is for, measured to a stall's nearest corner: the line of sight from the main gate to the landmark as
built (10 studs either side), the opening of every street's mouth (16 studs), and the square's edge where the house
doors are (10 studs). A square with room for fewer than two stalls is an error (the default 96 x 72 square holds
three or four; one of 64 x 56 or less holds none): make it bigger or say `"market": false`, an empty square said on purpose.
The build asks a new world's town to say one or the other. The plan page draws each stall.

**Things in the yards** (`"yards": true`, `mats.wood` - or `mats.stall` - and `mats.cloth`): a block's yard is the
ground between the backs of its rows. Most yards are shut on all four sides, so with `"yards": true` the plan first
OPENS each shut yard 10 studs or wider: one house of its rows gives way to a walled court with a gate - the house
on the quietest street, nearest the middle of the yard's side; never one on the square, never the only house the
block has on that street, never one a street ends on (its front closes that street's view). A yard with no such
house stays shut. The town has that many houses fewer and every house that stays is unchanged (the same storeys,
type and wall as with `"yards": false`); the page marks each gate green and counts them. Then every yard a walker
can enter, 10 studs or wider between the back walls, gets along it every 12 studs and never within 8 of an end, by
turns: a woodpile against a house's back wall (7.8 studs of way or more stay beside it) and a wash line tied 10
studs up from back wall to facing back wall (both houses 11 studs or taller, the yard no wider than 24), its
sheets' hems 8 studs up; about a third of the places stay empty by the seed. A town with no such yard is an error
(3 towns in 40 of the usual sizes, and every town of 192 x 160): `"yards": false` - bare yards, all houses kept,
said on purpose - or a bigger area. The build asks a new world's town to say one or the other.

**A town on a slope** (`"slope": { "rise": 4, "toward": "N" }`): the town lies on one hillside that rises `rise` studs
in every 100 (over 0 to 6) toward that side. The ground - streets, square, pavements, yards - is tilted plates cut
round the houses; each house stands level with its floor at the street's height at its own front door, so houses
step up a street one by one, hold the hill back with their uphill walls, and stand on a plinth where the ground
falls away under them. Yard walls, lamps, stalls, yard things and spawn pads stand at the ground's height where
they are (a spawn pad level, on its lowest edge's ground); a street's claim says its floor's height at each end and
`kit world check` measures its width from the ground under each sample. `"slope": false` is level ground, said on
purpose: the build asks a new world's town to say one or the other. NOT built: a bent town on a slope (`"bend"`
over 0 with a slope is an error), stairs or terraces between streets, a bridge. Mind: at the town's edge the gate
streets end as much above or below the town's own level as the hill has climbed (half its drop): what lies
outside a gate must meet that height.

NOT in a bend: a `"turn"` on the town step (an error: a town is placed by its `"center"`), the town on a slope, a
town wall (`wall` with `"points"` and `"curve"` round it, typed from the plan page).

## The town's kit of houses (`kit world town <Name> --kit`)

A town with `"skins": "<prefix>"` wears a mesh on every house. `lune run kit world town <Name> --kit` reads the
blueprint (a skinned town does not compile until its meshes exist) and writes `<worlds>/meshes/town_<World>.json`:
one `gothic_house` recipe per house TYPE, named `<prefix>_<type>`, cut on the numbers of the building the plan makes
of that type — its footprint (the lot less one wall, less the trim gap), storeys, storey height, the door, the
window run (all written out in full) and which of the mesh's own sides have windows (its front is S; a corner's
flank E or W; a through house's back N). The compiler's skin check passes for every house, and the mesh's door and
windows stand in the building's own bays (`kit/world/housebays.py`: one rule for both). Then:

```
lune run kit world meshes --set town_<World>     # about 7 s a mesh; LOOK at build/worldmeshes/<name>.preview.png
lune run kit world town <Name>                   # the plan page
lune run kit world look <Name>                   # the town from its stations, in its meshes
```

- A house needs a BAY for its door: a wall has floor((length - 4) / every) bays, so a front under a window's
  spacing + 4 (14 by default) has none. The least lot width is raised to fit (20 with trim); one typed too narrow
  is an error.
- The looks of the kit are the town's: `"kit": { "stones": [[r, g, b], ...], "slate": [r, g, b], "chimneys": 0.5 }`
  (stones are shared out by type; a gable is as steep as the front is wide; the landmark gets a taller gable and no
  chimney). `"kit": { "thickness" }` is the MESH's wall depth (the house's wall + 0.2 unless typed). A type is the
  same house in every build (its seed comes from its name). Give the town a `"glass"` material: without panes a
  window is a hole into an unlit room.
- A town is changed in its BLUEPRINT and the list written again: never edit `town_<World>.json` by hand.
- Towns cut alike share their meshes, whatever they are called. A mesh name that another town of the world, or
  another list in `<worlds>/meshes`, already cuts differently is refused: give that town its own prefix.
- How many meshes (measured on 256 x 224 towns): 40-60 houses of 24-35 types with `"floorHeights": [14]`, 30-42
  with two storey heights. Fewer types: one storey height, one lot depth, a narrower `"lots": { "width": [20, 24] }`.
- Known, not yet right (board card y39y): the mesh's stone face stands 0.45 studs inside the invisible wall you
  collide with (the mesh takes its width as its outer face, the building as its walls' centre lines); a flank
  window's surround is drawn on the wrong plane; hood moulds read as awnings at eye level.
- `"facade": true` (a town with `"skins"` must say it, or `"facade": false`: the build stops without the word):
  every house is put together from MODULES by a grammar (`kit/lib/worldfacade.luau`) in place of one whole mesh a
  type. Each storey of each wall is split on the very gaps the wall is cut with: a door module, a window module on
  each window, whole 4-stud wall panels stretched to fill the runs between; a band at each upper storey's foot; a
  roof grown to the house's front and laid end to end along its ridge (its gable to the street, unless the house
  is so much wider than deep that the ridge runs along the front). 5 modules a storey height (`<skins>_wall_14`,
  `_window_14`, `_windowb_14`, `_door_14`, `_oriel_14`) and 3 for the town (`_band`, `_roof`, `_chimney`): 8
  meshes with one storey height, 13 with two, where a town needed 30 to 65. A module's own front is its +Z. A house's own seed picks its window and whether an oriel hangs over its
  door, so two houses of one type differ. `kit world town <Name> --kit` writes the module recipes (kind
  `gothic_module`). A module that is missing, or cut for another door / window / storey height, is one compile
  error and the houses are built plain. `kit world meshes --set town_<World>` makes the modules (kind
  `gothic_module` in `kit/world/gothic_blender.py`: wall, pointed window, cross window, doorway, oriel, band,
  roof, chimney; 10 to 240 triangles each) and files each one's kind, storey height, opening and box. NOT built
  yet: a shopfront, corner quoins (a notch 0.6 studs square stays open at each corner), one shared texture
  sheet for all modules (each has its own 1,024 px picture today).
- Roblox shows a mesh only after it is uploaded (`kit upload`, each picture judged first). Until then a skinned
  house shows its own plain walls and roof in a game build (the runtime's stand-in: `src/kit/WorldMeshes.luau`), `kit world studio`'s scratch
  place shows the plain blockout instead, and the meshes are seen in the Blender look and the web viewer.

Not in this version (say so, do not work round it): streets run on the two axes only (the building generator cannot
turn a house); the town stands on level ground (`"ground": true` is not followed); one square, one landmark; a
later scatter / forest step does not know the town's streets (give it `"avoid"` circles).

<!-- reference for the parallax-world route card; verbatim from the skill page (2026-10-16) -->

## Generators (studs; rot = degrees like CFrame.Angles; N = -Z, S = +Z, E = +X, W = -X)
ANY ANGLE: `"turn": <degrees>` on a step turns everything the step made (its walls, floors, stairs, furniture,
panes, its mesh skin and its scale claims) about a vertical line: through `"about": [x, z]` (two numbers, no
height) when given, else through the step's `center` / `pos`, else through the middle of its `from` / `to` (a wall,
a bridge, a crosswalk). Several steps turned about ONE point keep their places to each other (a block of houses, two
walls of a lane). Positive = +X swings toward -Z, as `rot`'s yaw. Followed by: part, fit, wall, floor, stairs, ring,
grid, room, breakable, building, mesh, ruin, tower, bridge, arch, city, crosswalk, ziggurat (`stairs`, `grid` and
`fit` have no centre of their own: give them `"about"`). Not by any other step (a path, a forest, a spawn ...: type
it where and how it stands), not together with `"ground": true`, and not by a `town` (its streets bend by its own
`"bend"`). On land, a part is kept or dropped as hidden under the land by where it stands AFTER the turn.
`kit world check` measures a lane or a run wall that runs on neither axis across itself, on what stands there.
ROOMS: `"rooms": true` on a `building` (or in a town's `"house"`) cuts every floor into rooms by rule: across its
longer side, no room under 9 studs on the side it was cut across (a floor too narrow for that stays whole), at most
four a floor, each cut a partition wall with ONE doorway (5 wide, 8.5 high, claimed on the scale sheet), so every
room is reached from every other. No partition ends in the front door, a window or another partition's doorway.
`"stairs": true`: a flight a floor by the west wall. From the second flight on they TURN BACK - two lanes of 4
studs side by side, each flight climbing the other way to the one below, the stairwell cut over the top of the
flight beneath (a house of three floors, or two under a flat roof, needs 11 studs inside its walls or the
compile says so). With `"stairs": true` the west strip - the flight and a body's width beside it - is a stair hall no partition
crosses. `"rooms": { "least": 10, "depth": 1, "door": 5, "mat": "plaster", "seed": 4 }` tunes it (a doorway under
4.5 is an error); `"rooms": false` is one open room a floor, said on purpose - only true, false or that table is a
word (the build asks a new world's bigger houses to say one). `"interior"` furniture is set out for one room a floor
and is left out of a house with rooms (furniture by room is not built).
CURVES: `"curve": true` on a `path`, `row`, `palisade` or a `wall` with `"points"` makes the line through the typed
points smooth (every typed point stays on it; `"curve": { "step": 12, "maxTurn": 6, "least": 1, "closed": true }`
tunes the pieces or closes a ring). `"curve": false` says a hard corner is meant: the build asks a new world's line
that turns more than 20 degrees to say one or the other. A curve is as tight as its typed points: a right angle typed
with 100-stud legs turns 6 degrees a piece, with 20-stud legs 19 - type a bend with room, or more points. A curved
path laps its pieces by each joint's own angle (its rim stays closed); a path narrower than its bend is tight stays
whole, a wider one laps itself on the inside. A wall ALONG points: `{ "wall": { "points": [[x, z], ...], "y": 0,
"height": 12, "thickness": 2, "mat": "brick", "gaps": [{ "at": 60, "width": 6, "height": 8 }] } }` (a gap's `at` is
measured along the whole line; a hard corner gets a corner post; a curved wall takes no `crenels`, `buttresses` or
`mesh` modules yet). A river shape of `kit world terrain` reads `"curve"` the same way.
```json
{ "part":      { "name": "Crate", "size": [4, 4, 4], "pos": [0, 2, 0], "rot": [0, 45, 0], "mat": "wood", "shape": "Block" } }
{ "wall":      { "from": [x, z], "to": [x, z], "y": 0, "height": 12, "thickness": 2, "mat": "brick",
                 "gaps": [{ "at": 10, "width": 6, "height": 8, "sill": 0 }] } }       // sill > 0 = a window
{ "floor":     { "center": [0, 0, 0], "size": [100, 100], "thickness": 1, "mat": "ground", "checker": [10, "tile"] } }
{ "stairs":    { "start": [x, y, z], "dir": "+X", "steps": 8, "rise": 1, "run": 2, "width": 8, "mat": "metal" } }
{ "ring":      { "center": [0, 0, 0], "radius": 70, "height": 14, "thickness": 3, "segments": 24, "mat": "brick", "gaps": 4 } }
{ "grid":      { "origin": [-40, 0, -40], "count": [3, 3], "spacing": [40, 40], "part": { "size": [3, 18, 3], "mat": "metal" } } }
{ "scatter":   { "center": [0, 0, 40], "area": [70, 30], "count": 10, "seed": 7, "gap": 1.5, "part": { "size": [[3, 3, 3], [5, 5, 5]], "mat": "wood" } } }
// a scatter BY DENSITY (no "count" and no step "gap": they come out of the density; scatters that together come to 40 pieces
// or more must each say "density": {...} or "density": false):
{ "scatter":   { "center": [0, 0, 40], "area": [300, 300], "seed": 7, "part": { "size": [2, 2, 2], "mat": "stone" },
                 "density": { "gap": 6,                                         // least distance between two pieces where the field is full;
                                                                                // no less than the widest piece's diagonal (pieces are turned)
                              "noise": { "scale": 60, "seed": 3, "floor": 0.1 },  // clumps and clearings by themselves
                              "spots": [ { "at": [40, 60], "radius": 90, "weight": 1 } ],  // full at a spot, thinning to its radius
                              "away":  [ { "at": [0, 0], "radius": 20 } ] } } }   // nothing inside, growing back over a third more
// or a painted grid in place of them: "map": { "origin": [-150, -110] (its north-west corner), "cell": 75,
//   "rows": [ "0139", "0259", "0599", "0999" ] } - one string a row going south, one digit a cell going east, 0 nothing .. 9 full
// the field is the PRODUCT of what is given (a spot and a map that do not overlap place nothing: a compile error); pieces
// stand gap / sqrt(field) apart (up to 3 gaps, thinned by chance below that), spread as a true Poisson-disk sample until
// the area takes no more. Make the "area" the place the pieces are meant for: one that is nearly all clearing is cut short
// (a warning). kit/lib/worldscatter.luau
// a FOREST takes the same "density" (clumps, glades, an edge that thins out; no "count", no step "gap"; the gap is no less
// than half the tallest tree and 4): { "forest": { "center": [0, 0, 0], "area": [200, 160], "ground": true, "height": [18, 26],
//   "trunk": "bark", "leaves": "leaf", "density": { "gap": 17, "noise": { "scale": 90 }, "away": [ { "at": [40, 0], "radius": 30 } ] } } }
// (a built tree is 15 to 21 parts: the world's part budget is reached at about 500 of them - mesh trees are one part each)
// scatters and forests that together come to 40 pieces or more each say "density": {...} or "density": false (the build's lock)
// A FOREST THAT GREW - which kind stands where, how old, how tall comes out of its years (no count, styles, height, density):
{ "forest": { "name": "Wood", "center": [0, 0, 0], "area": [300, 240], "seed": 4, "ground": true, "trunk": "bark", "leaves": "leaf",
              "ecosystem": { "years": 120, "species": [
                { "name": "birch", "style": "oak",  "height": [4, 22], "crown": 14, "years": 12, "life": 45,  "shade": 0,    "seeds": 3, "throw": 60 },
                { "name": "oak",   "style": "pine", "height": [4, 36], "crown": 30, "years": 50, "life": 300, "shade": 0.99, "seeds": 1, "throw": 40 } ] } } }
// year by year every plant is a year older and wider (to its "crown" over its "years"), dies past its "life", dies with its stem
// under the crown of a TALLER plant unless its kind bears shade ("shade" = its chance to live through a year of it; in the inner
// 0.6 of such a crown it is crowded out whatever its kind; a low wide bush shades no tree), and - once grown - sets "seeds" a year
// up to "throw" studs away. The quick kind takes open ground, the shade-bearing kind comes up under it and takes it over: with the
// two above, 8 seeds, after 30 years 540 to 716 birch and 6 oak stand; after 300 years 0 to 441 birch and 375 to 690 oak (the oak
// has overtaken the birch two to one in 7 of the 8; how far it gets is the seed's).
// A kind says "style" (oak, dead, pine, palm, jungle, fern, bush, golden) or "meshes": [world mesh names]; its seedling is 2 to 20
// studs tall; its crown is at least half its grown height (grown trees stand no closer than 0.3 of a crown: trunks never touch;
// crowns as BUILT are about as wide as the tree is tall and interlock, as in a wood). Seedlings stand too (a tree as tall as its
// age). Narrow crowns in a large area are MANY trees (the two above on 300 x 240: about 700 to 1,000, some 20 parts each as
// blockout trees - the compile warns): wider crowns or a smaller area. Fewer first seedlings than asked is a warning.
// forests of two or more kinds - one forest of several, or forests of different kinds laid over each other - that together come
// to 40 trees or more say "ecosystem": {...} or "ecosystem": false (the build's lock)
// ROOMS AND CORRIDORS BY RULE - a crypt, a cellar maze, a keep's lower floor (six or more "room" steps typed one by one must be
// this, or say "dungeon": false at the blueprint's top: the build's lock):
{ "dungeon": { "name": "Crypt", "center": [0, 0, 0], "area": [240, 200], "rooms": 9, "seed": 4, "mat": "stone", "floor": "flag",
               "roof": "stone", "start": true,            // a ceiling over it; a spawn in the first room
               "room": [[16, 16], [32, 28]], "corridor": 8, "loops": 0.15, "height": 12, "thickness": 1 } }
// rooms are set down on a 4-stud grid, 8 studs or more apart, joined into one tree by corridors (8, 12 or 16 wide) with a few more
// ways for loops ("loops": 0 = one way to each room); floor under every room and corridor, a wall on every edge of the floor.
// Every room is reached from every other by construction. The rooms' places and the plan's measures come back with the build
// (extras.dungeons: a room's ways out and the dead ends are counted on the built floor). Walls are 12 studs or higher (a body
// jumps 7.2). A room's size is a multiple of 4 between its least and its most. A dungeon step does not excuse rooms typed beside
// it. No doors, no stairs between levels, no furniture: one level of bare rooms. kit/lib/worlddungeon.luau
// A PLACE LAID OUT OF TILES THAT FIT (wave function collapse) - a ruin of walls, a maze, a yard of pens: the look is in the pieces
{ "tiles": { "name": "Ruin", "center": [0, 0, 0], "cell": 16, "grid": [24, 14], "seed": 5,
    "set": { "border": "open",                      // the word every outer side of the grid shows
      "tiles": [ { "name": "court",  "edges": ["open", "open", "open", "open"], "weight": 3, "parts": [] },
                 { "name": "wall",   "edges": ["open", "wall", "open", "wall"], "weight": 2, "parts": [
                     { "name": "Post", "size": [2, 10, 2], "pos": [0, 5, 0], "mat": "stone" },
                     { "size": [7, 10, 2], "pos": [4.5, 5, 0], "mat": "stone" }, { "size": [7, 10, 2], "pos": [-4.5, 5, 0], "mat": "stone" } ] },
                 { "name": "corner", "edges": ["open", "wall", "wall", "open"], "parts": [ ... ] } ] },
    "fixed": [ { "at": [12, 7], "tile": "court" } ] } }
// "edges" = the word on a tile's north (-z), east (+x), south (+z), west (-x) side; two tiles lie side by side only where the words
// that touch are the same. A tile is laid in any quarter turn (clockwise from above; "turns": false = only as written), its parts
// (boxes, placed from the tile's middle on the ground, never over its side) turned with it - also a tile whose four words read the
// same turned. "weight" is how often a TILE is taken beside the others, however many turns it has. A set that cannot be laid on the
// grid is an error (one seen before any tile is chosen is said at once; a hard one is begun again 40 times: 2,500 cells of a set
// that cannot be laid can take a minute and a half to say so). The layout comes back with the build (extras.tiles). It does NOT promise a way from end to end: cells closed all round
// are real - check a world built with it (kit world check). A set's own parts must not overlap (a post in the middle, stubs that
// stop at it): the compile's z-fighting warning names them. kit/lib/worldwfc.luau
// A CAVE GROWN BY A CELLULAR AUTOMATON - chambers and winding passages, no two caves alike:
{ "cave": { "name": "Grotto", "center": [0, 0, 0], "area": [240, 200], "seed": 4, "mat": "rock", "floor": "dirt",
            "roof": "rock", "start": true,                // a ceiling over it; a spawn in its widest chamber
            "fill": 0.45, "turns": 4, "height": 12, "thickness": 1 } }
// every 4-stud cell is rock or open by chance ("fill" = the share of rock, 0.3 wide halls to 0.5 narrow), then "turns" times each
// cell becomes what most of the nine cells round it are. What is left is mended by rule: open ground counts only where a body 8
// studs wide can stand (a square of 2 x 2 cells); the largest group of such squares that body can slide through is the cave (the
// rest are pockets, dropped); floor touching by a corner is opened into the group. So a body 8 studs wide gets from any place of
// the floor to any other. A cave that closes up (under 12% floor) is an error: a lower fill or another seed. The start (the middle
// of the largest square of floor, 8 studs or more), the place the longest walk from it (for an objective) and the measures come
// back with the build (extras.caves). Its walls run in 4-stud steps and its floor is flat: the cave's plan, not its rock. An area
// of 800 x 800 comes to nearly 10,000 parts (the compile warns). kit/lib/worldcave.luau
// a ROAD ACROSS THE LAND that finds its own way (in place of "points"; a "path" with "ground": true):
{ "path": { "name": "PassRoad", "ground": true, "width": 8, "mat": "cobble", "worn": "Ground", "curve": true,
            "route": { "from": [-300, -250], "to": [300, 260], "grade": 0.15 } } }
// grade = the steepest it may climb (rise over run), held over every 2 studs of road; "via": [[x, z], ...] leads it through
// places; "cell" (8) = the grid the way is searched on (the land is read every 2 studs whatever the cell); "reach" = how far to
// each side of the straight line it may look (as far as the two ends are apart, 256 at least). A routed road says "curve": true
// or false. It goes round water that lies over the land (a lake a season froze too), painted rivers (the kit builds no bridge)
// and what the step keeps off ("avoid"); steeper costs more, so it takes a pass rather than a ridge. No way within the grade is
// a compile error; a road laid over a quarter steeper than its grade (a rounded corner, an edge of the land) is a warning.
// Roads on the land that together run 200 studs or more each say a "route" or "route": false (typed by hand, meant: the
// build's lock). One search may take seconds on rough land: lead a long road with "via". kit/lib/worldroute.luau
{ "room":      { "center": [x, floorTop, z], "size": [w, d], "height": 10, "thickness": 1, "mat": "wall", "floor": "tile", "roof": "slate",
                 "openings": [{ "side": "S", "at": 0, "width": 6, "height": 8 }, { "side": "N", "width": 4, "height": 6, "sill": 3 }] } }
{ "building":  { "center": [x, groundTop, z], "size": [w, d], "floors": 2, "floorHeight": 13, "mat": "wall", "slab": "trim",
                 "roof": "flat" | "gable", "roofMat": "roof", "stairs": true, "door": { "side": "S", "width": 6, "height": 9 },
                 "windows": { "every": 9, "width": 4, "height": 5, "sill": 3 } } }   // stairs: a flight per floor + roof hatch
{ "cover":     { "center": [x, y, z], "area": [40, 90], "count": 6, "seed": 3, "half": 0.6, "mat": "cover", "gap": 7 } }   // 3 / 7 studs
{ "path":      { "points": [[0, 128], [0, 70], [30, 40]], "y": 0.2, "width": 12, "mat": "path", "curb": { "height": 0.6, "width": 1 } } }
{ "breakable": { "name": "Crate", "size": [5, 5, 5], "pos": [30, 2.5, -30], "mat": "crate", "health": 40 } }   // KitBreakable + KitHealth
{ "spawn":     { "pos": [0, 0.75, 0], "mat": "spawnPad" } }
// open-world generators (SampleRegion): "ground": true on any step = stand it on the terrain (structures sink 4 studs
// so slopes never show a gap; "sink": false to stop); scatter / cover / forest also take slopeMax, above, below,
// avoid [[x, z, r]]; path + "ground": true lays tilted 6-stud road pieces that follow the land
{ "tree":      { "pos": [x, 0, z], "height": 30, "style": "oak" | "dead" | "golden" | "erd", "seed": 1, "trunk": "bark", "leaves": "leaf" } }
{ "forest":    { "center": [x, 0, z], "area": [w, d], "count": 20, "styles": ["oak", "dead"], "height": [16, 30],
                 "leaves": "leaf", "leavesAlt": "autumn", "altShare": 0.35, "ground": true, "slopeMax": 32, "avoid": [[x, z, r]] } }
{ "ruin":      { "center": [x, 0, z], "size": [44, 30], "height": 14, "decay": 0.55, "openings": [...],
                 "columns": { "count": 5, "radius": 1.4, "height": 16 }, "rubble": { "count": 30 }, "ground": true } }
{ "tower":     { "center": [x, 0, z], "radius": 9, "height": 34, "segments": 16, "roof": "cone", "roofMat": "roof", "ground": true } }
               // "door": { "width": 5, "height": 9, "angle": 45 } (0 = +X, 90 = +Z, the default): a corner tower's door faces its
               // courtyard, never the wall it joins; end curtain walls INSIDE the tower ring (radius - thickness/2), never at its
               // centre (the interior splits into sealed quadrants). "roofCollide": false on a roof no one can climb onto (towers,
               // buildings, rooms) — decoration, not floor; kit world check names unreachable roofs.
// building "interior": true | { "floors": ["hall", "chamber", "store"], "mats": { "wood": "...", "cloth": "..." } }:
// furnished floors by RULE (kit/lib/interior.luau): pieces back to a wall, a 4-stud walkway in front of each, never on
// the stair lane / landings or in the door's swing, nothing taller than a sill under a window; the hall's hearth faces
// the door, a long table + benches down the middle; hearth + candles lit; a broken rule is a compile ERROR.
// (and a body can WALK it: Interior.walk - from the door a body 2.5 studs wide reaches every piece's open side and the stairs, 30% of the floor stays open; a piece that breaks it is left out, a typed layout that breaks it is a compile error)
// LOOK: python kit/world/floorplan.py build/worlds/<World>.json <Building> -> build/worlds/floorplans/<World>_<Building>.png
// THINGS ON A MESH'S SURFACE - moss on a cliff's ledges, ivy on a wall's face: first the points, made in Blender by Geometry Nodes:
//   lune run kit world scatter-on <mesh> --as moss --gap 4 [--facing up|side|down|any] [--steep 0.5] [--seed 1] [--most 400]
// then the mesh's step sets a part on each: { "mesh": { "mesh": "<mesh>", "pos": [x, y, z], "mat": "stone",
//   "on": { "points": "moss", "part": { "size": [3, 0.4, 3], "mat": "moss" }, "sink": 0.1, "share": 1, "seed": 1, "turn": true } } }
// a piece's foot is on the surface and its y stands along the surface's normal; the points are the mesh's own (scaled and turned
// with it). Points made on another build of the mesh are refused (its triangle count and its box are kept with them): make them
// again after kit world meshes. A scatter-on that fails removes the points an earlier run made. Faces that do not face the way
// asked take no points and thin none; a face that leans between two facings counts for both; two kept faces closer than the gap
// (both sides of a thin wall) share their points. It is a spread, not a packing: about 0.6 points a gap squared on an open face.
// ECOLOGY: forest / scatter / rocks / cover with "ground": true take "roles": [...] (only on these painted roles) and
// "avoidRoles": [...] (never on them) - the painter's meadow / lush / dirt / mud / rock / cliff / snow / sand / scree
// (the heightmap op needs "paint": true). Living woods ["meadow","lush","dirt"]; shore dead wood ["mud","dirt","sand",
// "lush"]; boulders ["rock","scree","dirt","cliff"]. Spacing stays the generators' own min-distance (Poisson-like).
{ "bridge":    { "from": [x, z], "to": [x, z], "y": 16, "width": 8, "arches": 6, "pierDepth": 11, "mat": "stone" } }
{ "grace":     { "pos": [x, 0, z], "mat": "grace", "stone": "trim", "ground": true } }   // glow + light + motes; a place in the web viewer
{ "horizon":   { "radius": 2300, "count": 15, "height": [200, 460], "y": -60, "mat": "farrock", "cap": "snow", "floor": "farland" } }
               // distant ranges all round (backdrop): lopsided peaks of crossed short ridges + far land, so the world never ends in a void
{ "rocks":     { "center": [x, 0, z], "area": [w, d], "count": 9, "spires": 4, "spireHeight": [40, 75], "size": [7, 16],
                 "mat": "crag", "matAlt": "cragAlt", "ground": true, "slopeMax": 55, "avoid": [[x, z, r]] } }   // crags + leaning spires
{ "arch":      { "pos": [x, 0, z], "span": 12, "height": 11, "depth": 5, "pier": 2.5, "stones": 11, "yaw": 0, "mat": "stone", "keystone": "trim" } }
{ "palisade":  { "points": [[x, z], ...], "height": 13, "radius": 1.4, "mat": "log", "gaps": [{ "at": 62.8, "width": 12 }], "ground": true } }
{ "peak":      { "pos": [x, -60, z], "height": 1150, "base": 1500, "mat": "mountain", "cap": "snow", "beam": "light" } }  // ONE landmark mountain (backdrop), optional light beam
{ "ziggurat":  { "center": [x, 0, z], "base": [96, 96], "tiers": 6, "tierHeight": 7, "shrink": 0.8, "stair": "S", "mat": "temple", "shrine": { "mat": "temple", "glow": "relic" } } }
{ "falls":     { "top": [x, y, z], "bottom": [x, y, z], "width": 16, "mat": "water", "foam": "foam" } }   // a cascade down a slope (or "height" + "yaw" for a sheer drop)
{ "city":      { "center": [x, 0, z], "area": [440, 440], "block": [56, 48], "street": 16, "heights": [18, 72], "mat": "concrete", "glass": "lit", "signs": ["neon"], "sidewalk": "pave", "plaza": [[x, z, r]] } }
{ "crosswalk": { "from": [x, z], "to": [x, z], "width": 8, "mat": "stripe" } }   { "row": { "points": [...], "every": 30, "side": 7, "item": "lamp" } }
// building: "trim": mat (corner posts, floor bands, ridge beam), "glass": mat (a pane in every window: Neon = lit)
// trees: style "oak" | "dead" | "golden" | "erd" | "pine" (crossed-prism tiers; "snow": mat caps the top tiers) | "palm" | "jungle" | "fern" | "bush"
// wall: "crenels": true (battlements), "buttresses": { "every": 16, "depth": 3, "width": 3, "side": 1 | -1 } (which face)
// path + "ground": true: "worn": "Ground" (+ "wornWidth") wears a trail INTO the terrain; "parts": false = a dirt trail only
// any part: "light": { "type": "point" | "spot", "color": [r, g, b], "range": 18, "brightness": 3 },
//           "particles": "grace_motes" | "golden_leaves" | "mist" | "embers", "transparency", "backdrop": true
//           (backdrop = scenery beyond the map: never collides, ignored by the check and the look's framing)
//           "query": false (with "collide": false) = raycasts pass through it: decor on a wall a game ray reads
//           (a wall-run ray that hits an inlay's side reads a sideways wall and breaks the run)
```
The check works on voxels (1 stud; 2 studs on maps over ~400k sq studs): walls thinner than a voxel still block,
corner seams are sealed and jumps need a body-wide (2-stud) path, but a gap narrower than the body that still holds a
whole voxel (e.g. a 0.8-stud slit between offset walls) can read as passable: close gaps you mean to close.
Floors: `center.y` is the TOP surface. R6 numbers the check uses: 5 studs tall, 2 wide, walks 16 st/s, jumps 7.2
(a gap of ~8.7 studs on the flat), steps up 1 stud; half cover 3, full 7; a third-person camera needs room behind.

{ "cliffs":    { "meshes": ["ph_rockface"], "screeMeshes": ["ph_boulder"], "mat": "crag", "ground": true, "spacing": 22, "max": 140 } }
               // rock faces over the land too steep for Roblox terrain to hold (slope >= minSlope 35 on painted "cliff"
               // cells), turned downhill, as tall as the land drops, sunk into the hill; they COLLIDE only above
               // blockSlope 55 (on a climbable slope the terrain stays the walkable truth), never near the land's edge
{ "story":     { "kind": "camp" | "battle" | "cart", "center": [x, 0, z], "ground": true, "seed": 3, "mats": { "wood": "deadwood", "cloth": "ruin" } } }
               // set dressing that tells a story, by rule round its anchor: a camp (fire ring + lit fire, logs, bedrolls,
               // a tent, crates), a battle aftermath (blades stuck at angles, fallen shields, scorch, debris), a lost cart
               // (a wheel gone, the load spilled); every prop on its own ground

DECALS (a picture laid on a wall or a floor: a leak under a ledge, a stain, a crack, moss, soot over a torch):
`lune run kit world decal <Name> --kind leak|stain|crack|moss|soot [--seed n] [--size 256|512|1024] [--tint r,g,b]`
makes the picture by rule -> build/decals/<Name>.png + .decal.json. Its border is fully clear (a decal whose edge is
not clear shows its square on the wall) and the run refuses one that is not, one that is too faint, a leak heavier at
its foot; a tint that reads as blood is refused (no blood in this kit). LOOK at the picture. A build step lays it:
{ "decal": { "name": "Leak1", "at": [x, y, z], "size": [w, h], "facing": "north" } }      one: "at" is its middle ON the face
{ "decal": { "names": ["Leak1", "Moss2"], "along": { "from": [x, z], "to": [x, z] }, "y": [lo, hi], "count": 6,
             "size": [2, 4], "facing": "north", "seed": 4 } }       many along a wall, side by side, none over another
"facing" is the side the face looks toward: north (-Z) | east (+X) | south | west | up | down (many: walls only).
Optional: "transparency" 0..<1, "tint" [r, g, b] (a tint that reads as blood, alone or over the picture's own, is
refused). BUILD THE WALL BEFORE THE DECAL: the WHOLE decal must lie on the face of a solid, seen block that stands
square (not turned off the axes, not a ball, cylinder or wedge, not a part nobody can touch, not a mesh's unseen
stand-in), with no other part over the spot - or, facing up, within a quarter stud of the land; anything else is an
error that says why (hangs off the face, covered, under the land, two on one spot). The blueprint needs a "palette"
(any entry). A decal on a wall that breaks stays where it was. A decal never made is an error; one not uploaded is said
once and LEFT OUT (its id must stand in the project's ids file as decals.<Name>; kit upload does not take decals
yet). In the game it is a thin unseen part 0.03 studs off the face (no collision, no shadow, rays pass) with a Decal
on its outward side - seen in Studio to show there, upright on a wall; on a floor the picture's top lies toward +Z. Not turned by "turn". kit/world/decals.py, kit/lib/worlddecal.luau

PREFABS (a group of steps named once and set down many times: a market stall, a guard post, a camp):
"prefabs": { "Stall":  [ { "part": { ... "pos": [0, 1.5, 0] } }, { "part": { ... } } ],
             "Market": [ { "prefab": { "name": "Stall", "at": [-10, 0, 0] } },
                         { "prefab": { "name": "Stall", "at": [10, 0, 0], "turn": 180 } } ] }
{ "prefab": { "name": "Market", "at": [120, 0, 40], "turn": 90, "as": "NorthMarket" } }       a build step
Type a prefab's steps ROUND THE ORIGIN. "at" is where that origin lands, "turn" turns the whole of it about that
point (any angle), "as" names the placement (else <name>_<n>); two placements may not share a name. A prefab may
hold prefabs, 4 deep at most; none may hold itself. Each step's Model in the game is named by its placement:
NorthMarket.Stall_2.Counter. A placed prefab is the SAME THING MOVED: its steps are built where they are typed and
what they made (parts, scale claims) is shifted and turned afterwards - so only steps that make parts and nothing
else may stand in one (part, wall, floor, stairs, ring, grid, room, breakable, building, mesh, ruin, tower, bridge,
arch, crosswalk, ziggurat, decal, spawn), and none may say "ground": true (give the height in "at"). A step's own
"turn" inside a prefab is made first. Two placements in one prefab may not share a name either. A DECAL in a prefab
lies on its prefab's own wall (it is moved before it is judged) and needs the prefab turned by quarter turns only.
The build's rules (typed houses, typed rooms, the design gate on plain buildings ...) count what is IN prefabs.
kit/lib/worldprefab.luau

TRAILS WORN BY WALKERS (the footpaths between a village's houses, its well and its field - nobody plans them):
{ "trails": { "name": "Tracks", "places": [[x, z], ...], "walkers": 60, "seed": 3, "grade": 0.6, "wear": 0.6,
              "mat": "dirt", "width": 4, "worn": "Ground", "parts": false } }
places = 3 to 40 places people go between; walkers = how many walks are made (each place is walked from once at least;
the rest by the seed); grade = the steepest a walker climbs (steeper costs more: a trail goes round a hill); wear = how
much easier trodden ground is, 0 (every walker his own way: a web of lines) to 0.9 (0.6 when not said: a few shared
trails). Optional: "cell" (8: the grid they step on), "reach" (48: how far outside the places a trail may swing to
get round something - a pass further off is not found, and the walks across are said as lost), "curve" (true).
Each run of trail between two forks becomes a "path" of its own (<name>_<n>), the most trodden as wide as "width",
the least half of it; on land they follow it ("worn" paints the trail into the land, "parts": false leaves only that).
They go round water (keeping half the widest trail and 2 studs off it), painted rivers, land too steep and - a step
aslant - round the corner of a cliff or a pond; a strip nobody may stand on is seen down to a quarter of a cell (2
studs at the usual cell: a stream thinner than that is crossed). A trail ends AT its place. "parts": false needs land
and a "worn" material (else it would make nothing: an error).
What comes back with the build (extras.trails): runs, studs of trail, studs walked, walks lost.
NOT known to the walkers: buildings and walls (a trail may run through a house: lay trails before the houses' doors
are decided, or keep places clear of them). kit/lib/worldtrails.luau

A ROAD'S BED (cut and fill: a road on the land that holds its grade instead of following every bump):
{ "path": { ..., "ground": true, "bed": { "grade": 0.1, "shoulder": 12 } } }     or "bed": true on a routed road
The bed is the road's own line through the land, never steeper than "grade" (rise over run; a routed road hands on
its route's grade): of all lines that hold the grade, the one nearest the land's own (eased) - its worst cut or fill
the least, so a misfit is SHARED by both ends, never left at the end alone. A road whose last point is its first is a
loop: one height where it closes. Where the land stands higher it is CUT down to the bed, where it lies lower it is
FILLED up to it, across the road's width and a stud each side; over the "shoulder" (10 studs when not said) the land
comes back to itself (its sides fall 1.5 x deeper than they are wide at their steepest: a shoulder 1.5 x the depth
or more makes a bank, not a wall). The road's pieces, its worn trail, and EVERYTHING BUILT AFTER IT stand on the
graded land - lay roads with beds before the houses beside them: a part built before that the bed moves by more
than a stud is SAID (it floats or is buried). One rule for the game (it writes the voxels by it), the compiler and
kit world check (src/kit/RoadBed.luau; the check's heights carry the beds whoever builds the record).
Errors: no grade to go by, a road that leaves its land, a bed on a path that is not on the land, a road over a second
ground that stands higher (a bed is cut into one ground), the beds over 120,000 characters of the game's record of
its land (about 200,000 in all). Said: a bed over 24 studs deep (a tunnel, a bridge or a way round may be meant),
sides steeper than 45 degrees; cut and fill are read on the line AND at the road's edges (a side slope).
What comes back with the build (extras.beds): the grade asked, the steepest it is, the most it cuts and fills, a
loop; a routed road's record (extras.routes) is measured on its bed.
SEEN IN THE ENGINE (2026-11-16): Roblox's land under and beside a bedded road matched the kit's to 0.01 studs, and an
R6 body walked it end to end with streaming on. The painted ground (rock, river, the climate's roles) is NOT regraded: a cut through rock
paint keeps it. No camber or banked curves.

SNOW AND DUST ON WHAT IS BUILT (a blueprint's top-level "cover" - not the "cover" build step, which places crates):
"cover": { "snow": { "depth": 0.6, "above": 20 }, "dust": { "depth": 0.1 } }      either, or both; or "cover": false
Every level top is read cell by cell (2 studs) against what is over it, each part by its own turned box, and the
land: open sky (nothing within 40 studs) -> SNOW (at or over "above"); a roof within 16 studs -> DUST (a floor under a
roof, a shelf); something standing on it (a crate, a wall), the land over it, a roof 16-40 studs up -> nothing.
An upright wedge of 50 degrees or less (a gable roof's half) takes snow along its slope; two halves meet over the
ridge. Snow solid (walked on), dust a veil nobody touches; each slab goes with its part (same Model, same streaming).
Nothing on balls, cylinders, tilted parts, steeper wedges, breakable or loose parts, or meshes themselves - a mesh's
unseen stand-in counts as a roof over what is under it (extras.cover counts each). A season may bring its own "cover"
(false: bare that season). THE BUILD'S LOCK asks a world under snow (its land Snow or Glacier by any of its words, a
painted land with snow, snow falling in its "ambient" or weather - as written or in any season) that builds anything
to say "cover". kit/lib/worldcover.luau
FOG THAT LIES LOW (Roblox's haze is by distance only; the stand-in: see-through sheets stacked over the land):
{ "fog": { "over": "low", "below": 0, "mat": "fog", "layers": 6, "thick": 0.6, "cell": 4, "mist": 12, "seed": 1 } }
"over": "low" = under a fog line ("below", a height); "water" = over every water box and painted river, to its surface
+ "depth" (6), one cell onto the bank; "hollows" = wherever the land lies "deep" (4) under the mean ground within
"reach" (48), filled to its floor + depth, never over the land round it (the land's edge is no hollow). The fog is a
BLANKET "depth" thick under its top (a fog line: 12, or less over land not that far under it): every place under the
whole blanket has every sheet (straight down: "thick"); a sheet lies where any of a cell's land, or the water over it,
lies under it (never under water). "center" + "area" bound it (default: the play land, never far scenery). Seen
through, never walked, touched or snowed on, no shadow; "mist": slow mist puffs in it. "mat": a palette entry
(SmoothPlastic, pale grey / blue). Over 4,000 sheets: an error (a bigger "cell", fewer "layers", a smaller "area").
At the blueprint's top "fog" is only false. THE BUILD'S LOCK asks a world whose weather closes the air in ("fog" 0.5
or more in any stage, or a season's) to lay one, or say "fog": false at its top. kit/lib/worldfog.luau

A REAL THING PHOTOGRAPHED (a rock, a statue, a well, a stump, photographed all round):
lune run kit world scan <Name> --from <photos folder> --size <metres> [--axis height|length|width] [--quality low|medium|high]
-> the 3D lane's photogrammetry route (kit/tools/photoscan.py; read from the main checkout when this one has none) makes
a checked, levelled, textured mesh; it comes into the world meshes (the active game's) AT ITS REAL SIZE in studs
(0.28 m a stud), the asset and its pieces stamped "scan". Place it at its real size: { "mesh": { "mesh": "<Name>",
"pos": [x, y, z], "mat": "stone" } } (no "height"). A scatter / rocks / forest "meshes" list sets it by ITS OWN sizes
(scatter: 1.4 x the part's height). --size is required (photos have no size). A mesh step that sets it (or its piece)
more than a quarter off its real height is a compile error unless "resize": true; another step that does is warned
once. A scan never replaces a world mesh that was not scanned.
kit/world/scan_world.py

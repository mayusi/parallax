<!-- reference for the parallax-world route card; verbatim from the skill page (2026-10-16) -->

## Terrain + lighting
```json
"lighting": "golden",   // golden | noon | overcast | storm | night | scifi_dusk, or { "preset": "storm", "clockTime": 15 }
"terrain": [
  { "heightmap": { "center": [0, 0, 0], "size": [512, 512], "source": "assets/worlds/terrain/<Name>.hm.json",
                   "material": "Grass", "rock": "Rock", "rockSlope": 38, "flat": [{ "center": [0, 0], "radius": 60 }] } },
  { "ground": { "center": [0, 0, 0], "size": [600, 600], "material": "Grass", "under": "Rock",
                "noise": { "amplitude": 9, "scale": 110, "seed": 11 }, "flat": [{ "center": [0, 60], "radius": 26, "height": 0 }] } },
  { "ball": { "center": [130, 2, -170], "radius": 26, "material": "Rock" } },
  { "water": { "center": [110, -6, 40], "size": [60, 8, 40] } } ]
```
`"lighting": "erdtree"` = golden hour under a golden haze; `"jungle"` = a humid green-gold morning; `"neon_night"` = a neon city; `"frost"` = a northern winter (low sun, blue skylight);
`"desert"` = a copper end-of-day (Journey). `"ambient": "snow" | "sand" | "ash" | "leaves" | "embers"` = weather around the
player (a client emitter over the camera; the viewer shows it too); a world with one says `"weather": false` (that
one weather for ever, meant: the build's lock asks). WEATHER THAT CHANGES, in place of `"ambient"`: `"weather": { "cycle":
[ { "ambient": "clear", "minutes": 10 }, { "ambient": "rain", "minutes": 6, "fog": 0.5, "dim": 0.25 } ], "change": 40 }`
- each stage lasts its minutes and fades into the next over the last `change` seconds (the last into the first); `fog`
0..1 closes the air in (the Atmosphere's density and haze), `dim` 0..0.6 takes daylight; two stages or more, no two the
same in a row, `change` at most half the shortest stage; a key the rules do not know (a typo) is an error. Read off
the server's clock: every player is in the same weather (the server writes three numbers - Brightness, the
Atmosphere's Density and Haze - from what the lighting or the time of day asks for at that moment, twice a second:
a script of the game's that sets those three is overwritten; each client sets what falls round its camera). Rules: `src/kit/WeatherRules.luau`; never seen in Roblox yet.
SEASONS - one world, built in several: `"seasons": { "winter": { "lighting": "frost", "ambient": "snow", "weather": false,
"terrain": { "Grass": "Snow", "Water": "Glacier" }, "palette": { "leaf": { "material": "Snow", "color": [236, 240, 246] } },
"skip": [ "Flower beds" ] } }, "season": "winter"` (or `"season": false`: the world as written; the build's lock asks).
A season may change lighting, day, wind, ambient, weather, decoration, terrainColors (its own in place of the world's;
false = none this season - for `weather` and `decoration` false is their own word and is kept), `terrain` (a material
swap over the land: ground and heightmap ops with what lies under them, their rock, patches, layers and every role the
painter paints; blocks, balls, cylinders; paths' worn trails; the worn skirt under buildings - water swapped to a solid
becomes a block of it, a frozen lake), `palette` (entries the world already has, re-made), `skip` (step names left
out). Every season is read at every build: a typo, a material the land has not, a step that does not exist, a bad
lighting / day / wind / ambient / weather / palette material in ANY season is a compile error. The built world's json
(`kit world flatten`, the check, the look, the viewer) is of the season built. A season is chosen when the world is
built, not while the game runs. `kit/lib/worldseason.luau`. `"decoration": true` = Roblox's animated grass on Grass terrain.
A SKY OF THE KIT'S OWN (six pictures in place of Roblox's default sky):
`lune run kit world sky <Name> --sun <elevation>,<azimuth> [--clouds 0..1] [--seed n] [--size 256|512|1024]` renders one
physical sky in Blender - the sun where asked (azimuth from -Z round toward +X; under the horizon no disc is drawn),
clouds by noise - as six square pictures, one for each face of Roblox's sky cube -> build/skies/<Name>_ft.png, _bk, _lf,
_rt, _up, _dn + <Name>.sky.json. Which way each face looks is MEASURED (Studio, 2026-11-15; Roblox's page does not say):
Ft is seen looking toward -Z, Lf toward +X, both upright; the Up picture's top edge lies toward +X, the Dn picture's
toward -X; Bk is seen looking toward +Z and Rt toward -X, both upright (all six measured). A run checks what Blender can: six test suns, one off the middle
of each face, must show at their places (a camera turned, mirrored or looking elsewhere than that table fails), and the
sky must be brighter on the sun's side. It cannot check the table against Roblox. A run that fails leaves no pictures.
A world's lighting names it: `"lighting": { "preset": "noon", "sky": "<Name>" }` (one sky a world: not in a day's keys).
It is in a game ONLY ONCE THE SIX PICTURES ARE UPLOADED and their ids stand in the project's ids file as
skies.<Name>.SkyboxFt ... (kit upload does not take skies yet): until then the compile says so and Roblox's own sky
stays. In the game the kit's Sky replaces any other, Roblox's own sun, moon and stars are not drawn (a night world
needs a sky rendered for the night), and the sky is turned about the vertical - at the start and as the world's clock
moves - so that the drawn sun stands over the side the light comes from; at night it is left as it stands. That turn's
direction is SEEN in Studio (SkyboxOrientation +90 carries Ft from -Z to -X). Render the sky for the sun's height the world's clock gives: the turn
mends its compass side only. kit/world/sky.py, sky_blender.py, src/kit/SkyRules.luau
FAR RIDGES PAINTED IN THE SKY (a matte painting): `--ridges 1..3 [--ridge-height 2..25]` paints ranges of far
mountains into the same six pictures, one behind the other: the farthest the highest and the palest, each nearer one
lower and darker, mist at their feet; the height is the degrees the highest crest stands over the horizon (8 when not
said). They are in the sky's own shader, by the compass side a ray points to, so they cross the pictures' seams
unbroken (the cameras' check holds that; a run also reads the ranges back: a crest on every compass side, none over
the height asked, no step at a seam over half as much again as the steepest inside a face). A sky with ridges is NOT TURNED to the light in the game (mountains do not wheel round the
horizon with the hour): render it with the sun on the side the world's light comes from - NO TOOL OF THE KIT GIVES
THAT SIDE and nothing compares the two (in Studio: Lighting:GetSunDirection()); under a day's cycle the compile says
the drawn sun will stay while the light moves. A sun lower than the ranges may be hidden behind a crest (the run says). They are a picture: flat tones, no light of their own,
nothing to walk to - far scenery you can reach is real land ("backdrop": true).
CAVES, OVERHANGS, ARCHES - LAND AS A SIGNED DISTANCE (a terrain op, AFTER the ground it is cut out of: a ground or
heightmap op listed after it is a compile error - the game writes the ops in order and the ground would fill the caves):
`{ "sdf": { "material": "Rock", "shapes": [ { "box": { "center": [70, 12, 30], "size": [12, 24, 40], "round": 3 } },
{ "capsule": { "from": [60, 8, 30], "to": [80, 8, 30], "radius": 8 }, "cut": true } ] } }` - each shape is a `ball`
(center, radius), a `box` (center, size, round) or a `capsule` (from, to, radius: a tunnel, a rib of rock); read in
order, each is JOINED to what the op has made, or with `"cut": true` taken OUT of it and out of the land that was there
before the op (the heightmap's, a block's): a tunnel through a ridge, a cave mouth, the opening of an arch. `blend`
rounds a seam by that many studs: between a shape and the op's own land, and between two cuts where they meet; ONE cut
through older land is as wide with a blend as without (that land has no seam to round). A cut that reaches under the
ground digs a pit: stop it at the ground. A cut is 4 studs of radius or more (8 across for a box): the game writes
4-stud cells and a narrower cut often does not open; a wall thinner than a cell between two cuts may vanish. The game
writes it when the place starts - measured in Studio: 45,900 cells in 0.06 s, 401,408 cells of 21 shapes in 1.7 s - and
what the engine then holds was read back against these rules cell by cell. kit world check walks it. One op: 512 studs a
side and 500,000 cells at most; all of a world's together 1,500,000. The web viewer and the Blender look do not draw it:
land it adds is missing there and its caves look solid. src/kit/SdfRules.luau, kit/world/sdf.py
TREES GROWN BY A GRAMMAR (mesh recipes, `kit world meshes`): a tree recipe says `"grammar": "broadleaf" | "conifer" |
"dead" | "shrub"` and its wood is grown by that kind's L-system (a word rewritten a few turns, read by a turtle that
walks, turns and forks: kit/world/lsystem.py) - a broadleaf forks three ways and again, a conifer is a leader with
whorls of level boughs that shorten toward the top, a dead tree forks in two and carries no leaves. A kind of your own:
`"grammar": { "axiom": "FFA", "rules": { "A": "[&FLA]////[&FLA]////[&FLA]" }, "angle": 30, "turns": 3, "taper": 0.62,
"shorten": 0.8, "wobble": 0.1 }` (F wood, L a leaf mass, + - & ^ \ / turns, [ ] a branch; a rule may be `[[weight, word],
...]`; wobble = the share by which every turn and length is off, by the seed, so two trees of one kind differ). A tree
recipe must say its grammar or `"grammar": false` (limbs at chance angles, the older tree) - null or "" is no word; only
a tree already UPLOADED into the game (its name in the project's ids file) is not asked. Refused: over 90 pieces of
wood, over 60 leaf masses, a seed that is no whole number 0 to 65535, a trunk over a quarter of the height. The leaf
cards' size and number are the recipe's (`"leaf"`, `"density"`), not the grammar's.
STAMPS - land forms placed by name: `lune run kit world terrain <Name> --stamp kind,x,z,radius,height[,turn][,worked]`
(as often as wanted; x, z in studs from the map's middle): `crater` (a bowl with a raised rim), `mesa` (one flat top,
steep sides; it never lowers ground that stands higher), `cone` (a mountain with a crater in its top), `ridge` /
`valley` (long, along `turn` degrees: 0 = along z), `mound`, `pit`. A stamp is laid on the FINISHED land: crisp, and
outside its radius not one height changes - that is how a land is edited without moving what stands on it. `worked`
lays it before the rivers and the erosion, so they work on it - and then the WHOLE land comes out another land (the
erosion is chaotic): use it when the land is first made, never on a land things already stand on. A stamp off the land,
or one that digs under the land's floor (height 0), stops the command. Stamps are part of the land's recipe:
`kit world check` re-makes the land from it (a land changed by hand in its heights fails its route proof).
A CLIMATE for the painter (biomes by moisture and temperature): `lune run kit world terrain <Name> --climate
"wind=270,rain=0.6,sea=0.8,lapse=0.35,shade=0.12"` (or the design's `"paint": {"climate": {...}}`): wind = the bearing
it blows FROM (0 = north, -Z); rain 0..1 = how wet the air; sea 0..1 = how warm at height 0; lapse = colder by that
much every 100 studs up; shade = how much colder a north face (and warmer a south face) than level ground. The side of
a ridge the wind meets is wet (lush); behind a ridge that stands 30 studs or more over the land the ground is bare,
then sand where it is warm, fading out 240 studs behind it (a wide gentle rise casts little shadow); snow lies where
it freezes, lower on a north face, on everything flatter than 48 degrees but running water (the kit's defaults - sea
0.7, lapse 0.3 - freeze only above 233 studs: lower the sea or raise the lapse for snow). A climate makes its own
snowline: a typed one beside it is refused. Under a warm climate rock, cliff and scree stay the land's own shape. The
heights are not moved. A painted land made with no climate says `"climate": false` on its heightmap op (the build's lock asks).
PAINTED terrain: a heightmap made by `kit world terrain` carries its roles; the op uses them when it has no `layers` or
says `"paint": true` (a role map remaps: `"paint": {"meadow": "Grass", "lush": "LeafyGrass", "dirt": "Ground", "mud":
"Mud", "rock": "Rock", "cliff": "Slate", "snow": "Snow", "sand": "Sand", "scree": "Ground"}` — those are the defaults;
`"paint": false` = off). Roblox fills each 4-stud column with its role's material (borders dithered); the viewer paints
the same map. Without paint, heightmap `layers` paint by height and slope (later wins):
`[{ "material": "Sand", "minHeight": 12, "maxHeight": 16, "maxSlope": 18 }, { "material": "Ground", "minHeight": 120 }]`.
`"terrainColors": { "Grass": [112, 122, 58], ... }` and `"water": { "color", "transparency", "waveSize", "waveSpeed",
"reflectance" }` at the blueprint's top. Designed land: `kit world terrain <Name> --design <file>` (rim / plateau / basin /
hill / ridge / ramp / dunes (crescents with a steep lee face: run it with --erosion 0) / ring shapes + a domain warp, then erosion) — example `games/SampleRegion/assets/worlds/terrain/SampleRegion.design.json`; far mountains around a map: a second, coarse heightmap with `"backdrop": true` and a `ring` shape (`SampleRegionFar.design.json`).
Heightmap samples ride inside the world model (`KitTerrain<i>_<k>` ModuleScripts, chunked under Roblox's ~200k-character Source cap, joined then destroyed at run time) — the game, the check and the look all
read the same heights. Applied at runtime by the kit's Environment (Rojo cannot carry terrain or lighting effects).

REAL LAND: `kit world dem <Name> --bbox lon0,lat0,lon1,lat1` (USGS 3DEP, public domain, US only) -> a terrain design
with `"dem": {"file": "<Name>.dem.tif", "blur": 1.2}` uses it as its base (slopes TRUE: the ground the heights cover = the map's
size - the service widens a box that is not square to a SQUARE about its middle, and the sidecar's "covers" says what
that is; `"vexag"` exaggerates, `"relief"` fits a range); shapes / keep masks / anchor still apply. Refine LIGHTLY
(`--stream 0 --erosion 40000 --thermal 10`): real land is already eroded, the river pass tuned for noise over-carves it.
A ~3 km box makes ~2.9 m per stud on a 1024-stud map.

REAL COVER (what grows and lies on that land, from above): `kit world imagery <Name> --bbox <the dem's box> [--size 512]`
(USDA NAIP aerial pictures, public domain, US only; vetted in VETLOG.md) -> <Name>.img.png + .img.json beside the dem
(git-ignored: fetched again when needed). The picture is asked for the SAME SQUARE OF GROUND the box's heights cover
(not the box as typed: see REAL LAND), so the two lie on each other. LOOK at the picture. `kit world terrain <Name>
--design <the dem's design> --imagery <Name>.img.png` (or the design's `"paint": {"imagery": "<file>"}`) paints the
land by it: green = meadow, dark green = lush, grey = rock, brown = dirt, pale tan = sand, very white = snow, dark =
mud. It changes the SOIL only: rock a slope made stays rock (and takes snow, on nothing steeper than 48 degrees),
cliffs, scree and the mud where water runs are the land's own shape and stay, what reads as water says nothing; a
`--shore` still lays its sand over it at the water. Each cell of the land takes the ground that covers most of it
(colours are not mixed before they are read). Refused: a picture of another box than the design's dem, a picture
fetched before 2026-11-15's fix (it does not lie on the land), a land with no dem (noise is no place), a climate, a
snowline or --no-paint beside it, a sidecar with no box of four numbers or no credit. The painted land records the
picture (file, box, credit) and that answers the build's climate lock. It is a READ OF COLOUR, not a land-cover map,
and it is wrong where colour is: a shadow reads as lush or mud, snow in shadow as dirt or water, asphalt as mud, dry
yellow grass as dirt, the seams between two flights show as borders, a flight with a blue cast reads as water.
A picture named in a design is looked for from where the command runs, then beside the design.
kit/world/imagery.py, terrain.py (paint)

MATERIALS (Roblox draws the scans): `kit world materials` -> build/terrainmaps (color / normal / roughness 1024 PNG per
scan) -> `kit upload` (ids.terrainmaps) -> `kit world` writes a MaterialVariant per painted material into
src/materials/<World>.model.json (the game's Rojo project maps MaterialService.KitWorldMaterials -> src/materials; Rojo
writes the maps, a game script cannot) and the runtime calls MaterialService:SetBaseMaterialOverride per material.

## Time of day + one wind (kit WorldClock)
`"day": { "length": 1440, "start": 9, "keys": [{ "hour": 7, "preset": "golden" }, { "hour": 10, "preset": "erdtree" },
{ "hour": 20.5, "preset": "night" }] }` - keys are lighting presets or fields, blended (eased) between, round the clock;
the server runs Lighting.ClockTime. `"wind": { "direction": 300, "speed": [3, 14], "period": 45 }` drives
Workspace.GlobalWind (terrain grass, wind-affected particles) and the ambience: open / stone beds swell with it, scatter
rules take `"hours": [20, 5]` (crickets at night, birds by day).

## Water in the valleys (kit world rivers)
After `kit world terrain <Name>`, run `lune run kit world rivers <Name>` ONCE: D8 drainage over the stored heights, the
cells where the most water gathers (the top 1.2 %, never a cliff or the map edge; the biggest widened, specks under 8
cells dropped) become the painted role "river" -> Water. LOOK at `<Name>.hm.rivers.png`. Re-running is stable, but it
gives the previous river cells back as meadow: after a new terrain, run it on the fresh paint.

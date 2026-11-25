-- world.luau — compile assets/worlds/<Name>.json (level blueprints) into a Rojo model + a flat part list, and gate it.
-- Pure Luau (runs in Lune). Blueprint shape:
-- {
--   "name": "Arena",
--   "palette": { "stone": { "material": "Slate", "color": [90, 92, 98] }, "glass": { "material": "Glass", "color": [180, 220, 255], "transparency": 0.6 } },
--   "build": [ step, ... ]         -- each step is one generator; it becomes a Model named after "name" (or the kind)
-- }
-- Generators (all positions in studs; rot = degrees, same as CFrame.Angles):
--   { "part":  { name?, size, pos, rot?, mat, shape?: Block|Ball|Cylinder|Wedge, collide?, physics? } }
--   { "wall":  { from: [x, z], to: [x, z], y?: 0, height, thickness, mat, gaps?: [{ at, width, height }] } }
--   { "floor": { center: [x, y, z], size: [w, d], thickness?: 1, mat, checker?: [tileSize, "otherMat"] } }
--   { "stairs": { start: [x, y, z], dir: "+X"|"-X"|"+Z"|"-Z", steps, rise, run, width, mat } }
--   { "ring":  { center: [x, y, z], radius, height, thickness, segments, mat, gaps?: n } }
--   { "grid":  { origin: [x, y, z], count: [nx, nz], spacing: [sx, sz], part: { size, mat, shape?, rot? } } }
--   { "scatter": { center: [x, y, z], area: [w, d], count, seed, part: { size: [[min],[max]] | size, mat, shape? }, gap? } }
--   { "spawn": { pos: [x, y, z] } }
-- "lighting": preset | {...} and "terrain": [ops] — see kit/lib/environment.luau (applied at runtime).
-- Gates: sizes 0 < s ≤ 2048 · nothing below the kill plane (y < -400) · part budget (error > 10000, warn > 3000) ·
--        spawns not buried inside geometry · z-fighting (coplanar overlapping faces facing the same way) · palette names.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Cave = require("./worldcave")
local Config = require("./config")
local Cover = require("./worldcover")
local Curve = require("./worldcurve")
local Decal = require("./worlddecal")
local Dungeon = require("./worlddungeon")
local Eco = require("./worldecosystem")
local Environment = require("./environment")
local Facade = require("./worldfacade")
local Fog = require("./worldfog")
local Interior = require("./interior")
local Junction = require("./worldjunction")
local Prefab = require("./worldprefab")
local RoadBed = require("../../src/kit/RoadBed")
local Rooms = require("./worldrooms")
local Route = require("./worldroute")
local Scatter = require("./worldscatter")
local Season = require("./worldseason")
local Stream = require("./worldstream")
local Town = require("./worldtown")
local Trails = require("./worldtrails")
local Weather = require("../../src/kit/WeatherRules")
local Wfc = require("./worldwfc")
local WorldLight = require("./worldlight")

local World = {}

-- one generated ModuleScript's Source stays under this (Roblox caps a string property near 200,000 characters)
World.MODULE_CHARS = 100000

export type Issue = { path: string, message: string, severity: string }
export type Part = {
	name: string,
	class: string,
	size: { number },
	pos: { number },
	rot: { { number } },
	color: { number },
	material: string,
	transparency: number,
	collide: boolean,
	query: boolean?, -- false: raycasts pass through it (decor on a run wall: a ray that hits an inlay's side reads a
	-- sideways wall; only on a part that does not collide)
	anchored: boolean,
	shape: string?,
	spawn: boolean?,
	axisAligned: boolean,
	attributes: { [string]: any }?, -- (breakable: KitBreakable + KitHealth, read by the game)
	children: { any }?, -- lights / particle emitters / a decal
	castShadow: boolean?, -- false: it throws no shadow (a decal's unseen part)
	cover: boolean?, -- a slab of snow or dust laid on another part (kit/lib/worldcover.luau)
	touch: boolean?, -- false: CanTouch off (nothing fires Touched on it: fog)
	fog: boolean?, -- a sheet or puff of low fog (kit/lib/worldfog.luau): seen through, never walked or snowed on
	backdrop: boolean?, -- far scenery (a giant tree on the horizon): seen, never walked, outside the analysis
	mesh: string?, -- a world mesh (kit world meshes) this invisible placeholder becomes at runtime
	module: string?, -- a facade module (kit/lib/worldfacade.luau): which kind this mesh is (wall, window, door ...)
	meshCollide: boolean?, -- that mesh is solid (rocks; not leaves): the viewer walks on it and keeps cameras out
}

local SHAPES = { Block = true, Ball = true, Cylinder = true, Wedge = true }

-- particle presets a part can carry ("particles": "<name>"): Rojo-typed ParticleEmitter properties, Roblox's own
-- built-in textures (no upload needed). Colours 0..1.
local SPARK = "rbxasset://textures/particles/sparkles_main.dds"
local SMOKE = "rbxasset://textures/particles/smoke_main.dds"
local function seq(points: { { number } }): any
	local k = {}
	for _, p in points do
		table.insert(k, { time = p[1], value = p[2], envelope = 0 })
	end
	return { NumberSequence = { keypoints = k } }
end
local function cseq(points: { { any } }): any
	local k = {}
	for _, p in points do
		table.insert(k, { time = p[1], color = p[2] })
	end
	return { ColorSequence = { keypoints = k } }
end
local PARTICLES: { [string]: { [string]: any } } = {
	-- snow falling over the whole map (an "ambient": "snow" world hangs one wide emitter high above it)
	snowfall = {
		Texture = SMOKE,
		Rate = 260,
		Lifetime = { NumberRange = { 14, 20 } },
		Speed = { NumberRange = { 6, 9 } },
		EmissionDirection = { Enum = 4 },
		SpreadAngle = { Vector2 = { 12, 12 } },
		Acceleration = { Vector3 = { 1.5, 0, 0.6 } },
		RotSpeed = { NumberRange = { -60, 60 } },
		Size = seq({ { 0, 0.32 }, { 1, 0.26 } }),
		Transparency = seq({ { 0, 0.15 }, { 0.85, 0.3 }, { 1, 1 } }),
		Color = cseq({ { 0, { 1, 1, 1 } }, { 1, { 0.92, 0.95, 1 } } }),
		LightEmission = 0.2,
		LightInfluence = 0.8,
	},
	-- a Site of Grace: golden motes rising slowly
	grace_motes = {
		Texture = SPARK,
		Rate = 7,
		Lifetime = { NumberRange = { 2, 4 } },
		Speed = { NumberRange = { 0.4, 1.4 } },
		SpreadAngle = { Vector2 = { 25, 25 } },
		Acceleration = { Vector3 = { 0, 1.2, 0 } },
		Size = seq({ { 0, 0.28 }, { 1, 0 } }),
		Transparency = seq({ { 0, 0.15 }, { 1, 1 } }),
		Color = cseq({ { 0, { 1, 0.86, 0.45 } }, { 1, { 1, 0.66, 0.2 } } }),
		LightEmission = 1,
		LightInfluence = 0,
	},
	-- the Erdtree's golden leaves drifting down
	golden_leaves = {
		Texture = SPARK,
		Rate = 14,
		Lifetime = { NumberRange = { 7, 12 } },
		Speed = { NumberRange = { 1, 3 } },
		SpreadAngle = { Vector2 = { 180, 180 } },
		Acceleration = { Vector3 = { 0.8, -1.1, 0.4 } },
		Size = seq({ { 0, 0.45 }, { 1, 0.3 } }),
		Transparency = seq({ { 0, 0.1 }, { 0.8, 0.3 }, { 1, 1 } }),
		Color = cseq({ { 0, { 1, 0.8, 0.3 } }, { 1, { 0.95, 0.55, 0.15 } } }),
		Rotation = { NumberRange = { 0, 360 } },
		RotSpeed = { NumberRange = { -80, 80 } },
		LightEmission = 0.7,
		LightInfluence = 0.3,
	},
	-- low mist over water and hollows
	mist = {
		Texture = SMOKE,
		Rate = 2.5,
		Lifetime = { NumberRange = { 14, 20 } },
		Speed = { NumberRange = { 0.3, 0.9 } },
		SpreadAngle = { Vector2 = { 180, 10 } },
		Acceleration = { Vector3 = { 0.2, 0.02, 0 } },
		Size = seq({ { 0, 14 }, { 1, 26 } }),
		Transparency = seq({ { 0, 1 }, { 0.3, 0.82 }, { 0.7, 0.86 }, { 1, 1 } }),
		Color = cseq({ { 0, { 0.86, 0.9, 0.95 } }, { 1, { 0.78, 0.82, 0.9 } } }),
		LightEmission = 0.1,
		LightInfluence = 1,
	},
	-- embers off a brazier / a fire
	embers = {
		Texture = SPARK,
		Rate = 10,
		Lifetime = { NumberRange = { 1.5, 3 } },
		Speed = { NumberRange = { 2, 4 } },
		SpreadAngle = { Vector2 = { 20, 20 } },
		Acceleration = { Vector3 = { 0.4, 2, 0 } },
		Size = seq({ { 0, 0.18 }, { 1, 0 } }),
		Transparency = seq({ { 0, 0 }, { 1, 1 } }),
		Color = cseq({ { 0, { 1, 0.6, 0.2 } }, { 1, { 1, 0.25, 0.05 } } }),
		LightEmission = 1,
		LightInfluence = 0,
	},
}
local PARTICLE_NAMES = "grace_motes | golden_leaves | mist | embers"
World.PARTICLES = PARTICLES

-- a building's "skin": a whole-building mesh (kit world meshes kind "gothic_house") whose door and windows are cut
-- where the building generator puts its gaps - so you walk in through its door and see in through its windows
-- (the owner, 2026-11-11: whole buildings you walk into, "Very detailed"). The mesh's front is its S side; it turns
-- to face the building's door side, and every side (and its run of windows) turns with it.
World.SKIN_YAW = { S = 0, E = 90, N = 180, W = 270 }
-- a W3 trim sheet's maps (kit/world/trims.py writes kit_trim_<sheet>_<map>.png; kit upload -> ids.worldtextures)
-- and the SurfaceAppearance property each one fills
World.TRIM_MAPS = { { "color", "ColorMap" }, { "normal", "NormalMap" }, { "roughness", "RoughnessMap" } }
-- studs a gothic skin's outer wall faces stand out from the building's box (gothic_blender.py: W / 2 + 0.05): where its
-- corner quoins stand
World.QUOIN_OUT = 0.05
-- a road on the land ("ground": true): a stretch steeper than ROAD_STAIR_DEG becomes stone steps about ROAD_STAIR_RISE
-- apart in height (the r6 sheet's step: rise 0.9..1.1, run 1.8 or more - ROAD_STAIR_RUN); a stretch gentler than that
-- banks with the land across it, ROAD_BANK_MAX degrees at most (LIMITATIONS_FIXES_V3.md stage E.3)
World.ROAD_STAIR_DEG = 16
-- an HLOD proxy's triangle budget (the horizon's "hlod": V3 stage F.2)
World.HLOD_TRIS = 2000
World.ROAD_STAIR_RISE = 1
World.ROAD_STAIR_RUN = 1.8
World.ROAD_BANK_MAX = 12
-- the worlds whose roads were laid before the steps, the banking and the junctions (by blueprint name): such a world
-- keeps its roads as they were unless a road asks ("stairs": true, "bank": true, "junction": true), so a kit change is
-- never a side effect on built worlds. The kit ships the list empty: every world gets the current roads, and a road
-- can still turn a feature off itself ("bank": false, "junction": false).
World.ROAD_V3_BEFORE = {} :: { [string]: boolean }
-- studs: a skin's corner this near another building's wall is butted against it - no free corner, no quoins
World.QUOIN_BUTT = 0.6
local SKIN_TURN = {
	[0] = { S = "S", E = "E", N = "N", W = "W" },
	[90] = { S = "E", E = "N", N = "W", W = "S" },
	[180] = { S = "N", E = "W", N = "S", W = "E" },
	[270] = { S = "W", E = "S", N = "E", W = "N" },
}

-- the building side a skin's own side lands on when the skin is turned `yaw` degrees
function World.skinSide(yaw: number, side: string): string
	return (SKIN_TURN[yaw % 360] or SKIN_TURN[0])[side] or side
end

-- why this skin cannot wrap this building (nil = it fits): the registry keeps the recipe's own footprint, floors,
-- door and windows (projecting sills make the bounding box wider than the walls); a mismatch would put a gap in the
-- invisible walls behind solid stone, or a doorway in front of a wall
function World.skinProblem(
	reg: any,
	name: string,
	size: { number },
	floors: number,
	fh: number,
	door: any,
	win: any,
	yaw: number
): string?
	if type(reg) ~= "table" then
		return `no world mesh "{name}" - make it: lune run kit world meshes`
	end
	local fp = reg.footprint
	if type(fp) ~= "table" then
		return `world mesh "{name}" is not a building skin (no footprint: kit world meshes kind "gothic_house")`
	end
	local w, d = size[1], size[2]
	if yaw % 180 ~= 0 then
		w, d = size[2], size[1]
	end
	if math.abs(fp[1] - w) > 0.01 or math.abs(fp[2] - d) > 0.01 then
		return `the skin "{name}" is cut for a {fp[1]} x {fp[2]} front x depth, the building is {w} x {d} (its door and windows would miss the building's)`
	end
	if reg.floors ~= floors or math.abs((reg.floorHeight or 14) - fh) > 0.01 then
		return `the skin "{name}" has {tostring(reg.floors)} floors of {tostring(reg.floorHeight)}, the building {floors} of {fh}`
	end
	local rd = reg.door
	if type(door) == "table" and type(rd) == "table" then
		if
			math.abs((rd.width or 6) - (door.width or 6)) > 0.01
			or math.abs((rd.height or 8.5) - (door.height or 8.5)) > 0.01
		then
			return `the skin "{name}"'s door is {tostring(rd.width)} x {tostring(rd.height)}, the building's {door.width or 6} x {door.height or 8.5}`
		end
	elseif (type(door) == "table") ~= (type(rd) == "table") then
		return `the skin "{name}" and its building disagree on having a door`
	end
	local rw = reg.windows or {}
	for _, k in { "every", "width", "height", "sill" } do
		if type(rw[k]) == "number" and type(win[k]) == "number" and math.abs(rw[k] - win[k]) > 0.01 then
			return `the skin "{name}"'s windows have {k} {rw[k]}, the building's {win[k]}`
		end
	end
	local want, have = {}, {}
	for _, sd in (if type(win.sides) == "table" then win.sides else { "N", "E", "S", "W" }) do
		want[sd] = true
	end
	for _, sd in (if type(rw.sides) == "table" then rw.sides else { "N", "E", "S", "W" }) do
		have[World.skinSide(yaw, sd)] = true
	end
	for _, sd in { "N", "E", "S", "W" } do
		if (want[sd] or false) ~= (have[sd] or false) then
			return `the skin "{name}" has windows on {if have[sd] then "" else "no "}{sd} side, the building {if want[sd]
				then ""
				else "none "}there (a gap behind stone, or stone over a gap)`
		end
	end
	return nil
end

-- the rotation whose local X axis points along d (cylinders and beams): columns = X, Y, Z in world space
function World.alongX(d: { number }): { { number } }
	local len = math.sqrt(d[1] ^ 2 + d[2] ^ 2 + d[3] ^ 2)
	local x = { d[1] / len, d[2] / len, d[3] / len }
	local ref = if math.abs(x[2]) < 0.99 then { 0, 1, 0 } else { 1, 0, 0 }
	local z = { x[2] * ref[3] - x[3] * ref[2], x[3] * ref[1] - x[1] * ref[3], x[1] * ref[2] - x[2] * ref[1] }
	local zl = math.sqrt(z[1] ^ 2 + z[2] ^ 2 + z[3] ^ 2)
	z = { z[1] / zl, z[2] / zl, z[3] / zl }
	local y = { z[2] * x[3] - z[3] * x[2], z[3] * x[1] - z[1] * x[3], z[1] * x[2] - z[2] * x[1] }
	return { { x[1], y[1], z[1] }, { x[2], y[2], z[2] }, { x[3], y[3], z[3] } }
end
local MATERIALS = {
	Plastic = true,
	SmoothPlastic = true,
	Wood = true,
	WoodPlanks = true,
	Slate = true,
	Concrete = true,
	Brick = true,
	Cobblestone = true,
	Rock = true,
	Sandstone = true,
	Basalt = true,
	Granite = true,
	Marble = true,
	Metal = true,
	DiamondPlate = true,
	CorrodedMetal = true,
	Foil = true,
	Glass = true,
	Neon = true,
	Ice = true,
	Sand = true,
	Grass = true,
	Ground = true,
	Mud = true,
	Snow = true,
	Fabric = true,
	Pebble = true,
	Asphalt = true,
	Pavement = true,
	LeafyGrass = true,
	Limestone = true,
	CrackedLava = true,
	Glacier = true,
	Salt = true,
	Cardboard = true,
	Carpet = true,
	CeramicTiles = true,
	ClayRoofTiles = true,
	RoofShingles = true,
	Leather = true,
	Plaster = true,
	Rubber = true,
}
local KILL_PLANE = -400
local BUDGET_MAX, BUDGET_WARN = 10000, 3000

-- ---------------------------------------------------------------- 3x3 rotation math (CFrame.Angles order: Rx*Ry*Rz)
local IDENTITY = { { 1, 0, 0 }, { 0, 1, 0 }, { 0, 0, 1 } }
local function mul(a: { { number } }, b: { { number } }): { { number } }
	local out = {}
	for i = 1, 3 do
		out[i] = {}
		for j = 1, 3 do
			out[i][j] = a[i][1] * b[1][j] + a[i][2] * b[2][j] + a[i][3] * b[3][j]
		end
	end
	return out
end
function World.rotation(rot: { number }?): { { number } }
	if not rot then
		return IDENTITY
	end
	local x, y, z = math.rad(rot[1] or 0), math.rad(rot[2] or 0), math.rad(rot[3] or 0)
	local rx = { { 1, 0, 0 }, { 0, math.cos(x), -math.sin(x) }, { 0, math.sin(x), math.cos(x) } }
	local ry = { { math.cos(y), 0, math.sin(y) }, { 0, 1, 0 }, { -math.sin(y), 0, math.cos(y) } }
	local rz = { { math.cos(z), -math.sin(z), 0 }, { math.sin(z), math.cos(z), 0 }, { 0, 0, 1 } }
	return mul(mul(rx, ry), rz)
end
-- a turn about the vertical: the matrix of `deg` degrees of yaw (CFrame.Angles(0, yaw, 0)); quarter turns are
-- exact (cos 90 is 6e-17 in floating point: a wall turned a quarter would stand a hair off its axis)
function World.turnMatrix(deg: number): { { number } }
	local c, sn = math.cos(math.rad(deg)), math.sin(math.rad(deg))
	if deg % 90 == 0 then
		c, sn = math.round(c), math.round(sn)
	end
	return { { c, 0, sn }, { 0, 1, 0 }, { -sn, 0, c } }
end
-- the point (x, z) turned `deg` degrees about (px, pz), the way a part's CFrame turns
function World.turnPoint(x: number, z: number, px: number, pz: number, deg: number): (number, number)
	local m = World.turnMatrix(deg)
	local dx, dz = x - px, z - pz
	return px + m[1][1] * dx + m[1][3] * dz, pz + m[3][1] * dx + m[3][3] * dz
end
-- the generators a "curve" is followed by: the ones that walk a line of typed "points" (kit/lib/worldcurve.luau)
World.CURVED = { path = true, row = true, palisade = true, wall = true }
-- a wall along points: a joint that turns more than this many degrees is a hard corner (it gets a corner post);
-- up to it the two pieces lap each other (a curve's joints turn far less)
World.WALL_CORNER = 12
-- the characters all the roads' beds may come to in the game's record of its land (one string of about 200,000)
World.BED_CHARS = 120000
-- a SCANNED thing (kit world scan: a real thing photographed, its registry entry carries "scan") keeps its real size:
-- placed more than this share taller or shorter than it is, the mesh step refuses it (unless "resize": true) and any
-- other step that sets it down (scatter, rocks, forest, ...) is warned
World.SCAN_SPREAD = 0.25
-- a curved path: how many pieces in a row may lap one spot and still lie each at its own height (0.01 studs apart)
World.PATH_LEVELS = 6
-- a building's GROUND floor: its boards stand this far over the ground it is built on (card my7f: GothicCourtyard's
-- WoodPlanks floor and the court's Slate floor both had their tops at y = 0 and flickered in Roblox; two faces of two
-- looks in one plane always do - kit world check's z-fighting error). Its foot stays where it was (the slab is that
-- much thicker: a plinth or the ground's cut meets it with no slit); the floors above sit on their storey lines.
World.GROUND_LIFT = 0.08
-- lights that cast shadows near one another (V3 stage F.2: "cap shadow lights, <= 16-24 active"): within SHADOW_REACH
-- studs of any one, more than SHADOW_WARN is a warning, more than SHADOW_MAX an error
World.SHADOW_REACH = 120
World.SHADOW_WARN = 16
World.SHADOW_MAX = 24
-- the generators a "turn" is followed by: everything they make is parts and scale claims (a path also paints the
-- land and keeps later scatter off it, a forest stands each tree on the land under it: those are typed at an angle
-- by their own points, never turned afterwards)
World.TURNABLE = {
	part = true,
	fit = true, -- (a claim typed beside turned things: a lane between two turned walls)
	wall = true,
	floor = true,
	stairs = true,
	ring = true,
	grid = true,
	room = true,
	breakable = true,
	building = true,
	mesh = true,
	ruin = true,
	tower = true,
	bridge = true,
	arch = true,
	city = true,
	crosswalk = true,
	ziggurat = true,
}
-- the generators a PREFAB may hold (kit/lib/worldprefab.luau): what they make is parts and scale claims and nothing
-- else, so it can be moved once it is built - the turned kinds, and a decal and a spawn
World.IN_PREFAB = table.clone(World.TURNABLE)
World.IN_PREFAB.decal = true
World.IN_PREFAB.spawn = true
World.IN_PREFAB.city = nil -- (a city grid is refused by the check: not handed on in prefabs)
local function isIdentity(m: { { number } }): boolean
	for i = 1, 3 do
		for j = 1, 3 do
			if math.abs(m[i][j] - (if i == j then 1 else 0)) > 1e-6 then
				return false
			end
		end
	end
	return true
end

-- deterministic RNG (scatter must give the same layout every compile)
-- A PLAN OF CELLS BUILT (a dungeon's, a cave's: kit/lib/worlddungeon.luau, worldcave.luau): a floor slab under every
-- rectangle of floor cells (and a roof slab over it when the step names a roof), a wall on every edge between floor
-- and not-floor
local function layCells(
	add: (string, any, { number }, { number }) -> any,
	path: string,
	plan: any,
	c: { number },
	h: number,
	t: number,
	spec: any,
	floorName: string
)
	for _, r in Dungeon.floors(plan) do
		local x0, z0, x1, z1 = Dungeon.studs(plan, c, r[1], r[2], r[3], r[4])
		add(
			path,
			{ name = floorName, mat = spec.floor },
			{ x1 - x0, 1, z1 - z0 },
			{ (x0 + x1) / 2, c[2] - 0.5, (z0 + z1) / 2 }
		)
		if spec.roof then
			add(
				path,
				{ name = "Roof", mat = spec.roof },
				{ x1 - x0, 1, z1 - z0 },
				{ (x0 + x1) / 2, c[2] + h + 0.5, (z0 + z1) / 2 }
			)
		end
	end
	for _, w in Dungeon.walls(plan) do
		if w.side == "N" or w.side == "S" then
			local x0, z0, x1, z1 = Dungeon.studs(plan, c, w.i0, w.j, w.i1, w.j)
			-- (lengthened by its thickness where it turns an outer corner, so the corner is shut)
			local lo = x0 - (if w.extend.low then t else 0)
			local hi = x1 + (if w.extend.high then t else 0)
			local z = if w.side == "N" then z0 - t / 2 else z1 + t / 2
			add(path, { name = "Wall", mat = spec.mat }, { hi - lo, h, t }, { (lo + hi) / 2, c[2] + h / 2, z })
		else
			local x0, z0, x1, z1 = Dungeon.studs(plan, c, w.i, w.j0, w.i, w.j1)
			local x = if w.side == "W" then x0 - t / 2 else x1 + t / 2
			-- (at an inner corner the wall along x already fills the corner square)
			local lo = z0 + (if w.trim.low then t else 0)
			local hi = z1 - (if w.trim.high then t else 0)
			-- (a run one cell long between two inner corners, walls 2 thick: the two corner squares
			-- already shut it)
			if hi - lo > 1e-6 then
				add(path, { name = "Wall", mat = spec.mat }, { t, h, hi - lo }, { x, c[2] + h / 2, (lo + hi) / 2 })
			end
		end
	end
end

local function lcg(seed: number): () -> number
	local state = (seed or 1) % 2147483647
	if state <= 0 then
		state += 2147483646
	end
	return function()
		state = (state * 48271) % 2147483647
		return state / 2147483647
	end
end

-- what may fall round the player ("ambient"; a season's too)
local AMBIENTS = { snow = true, ash = true, leaves = true, embers = true, sand = true, rain = true }

-- the blueprint as it stands in the season it is built in (kit/lib/worldseason.luau): what the compiler builds.
-- Whatever writes a built world down beside the model (kit world flatten, kit content) reads THIS, not the file.
function World.inSeason(bp: any): any
	if type(bp) ~= "table" or type(bp.build) ~= "table" then
		return bp
	end
	return Season.apply(bp, bp.season)
end

-- ---------------------------------------------------------------- compile
-- opts.meshes: a mesh registry in place of build/worldmeshes/meshes.json (the kit's own specs: no Blender run);
-- opts.ids: an ids table in place of assets/ids.json (the kit's own specs: no upload)
function World.compile(bp: any, opts: any?): (any?, { Part }, { Issue }, any)
	local issues: { Issue } = {}
	local function err(path: string, message: string)
		table.insert(issues, { path = path, message = message, severity = "error" })
	end
	local function warn(path: string, message: string)
		table.insert(issues, { path = path, message = message, severity = "warn" })
	end
	if type(bp) ~= "table" or type(bp.name) ~= "string" or type(bp.build) ~= "table" then
		err("blueprint", 'needs "name" and "build": [steps]')
		return nil, {}, issues
	end
	-- ONE WORLD IN SEVERAL SEASONS (kit/lib/worldseason.luau): "seasons" say what each other season changes,
	-- "season" which one this build is. Every season is read here, not only the one built: a broken winter is
	-- found while the summer is built. From here on `bp` is the world as it stands in its season.
	if bp.seasons ~= nil or bp.season ~= nil then
		local wrong = Season.problems(bp)
		for _, p in wrong do
			err("seasons", p)
		end
		if #wrong == 0 then
			for _, name in Season.names(bp) do
				if name ~= bp.season then
					-- (its air, cheaply: the lighting, day, wind and weather it would have - not its land)
					local other = Season.apply(bp, name)
					local _, airIssues = Environment.compile({
						lighting = other.lighting,
						day = other.day,
						wind = other.wind,
						terrainColors = other.terrainColors,
					})
					for _, issue in airIssues do
						if issue.severity == "error" then
							err(`seasons.{name}.{issue.path}`, issue.message)
						end
					end
					if other.weather ~= nil and other.weather ~= false then
						local _, weatherProblems = Weather.read(other.weather)
						for _, p in weatherProblems do
							err(`seasons.{name}.weather`, p)
						end
						if other.ambient ~= nil then
							err(
								`seasons.{name}`,
								`in {name} the world has an "ambient" and a "weather" cycle: one of them`
							)
						end
					end
					if other.ambient ~= nil and not AMBIENTS[other.ambient] then
						err(
							`seasons.{name}.ambient`,
							`ambient is "snow" | "rain" | "ash" | "leaves" | "embers" | "sand" (got "{tostring(
								other.ambient
							)}")`
						)
					end
					local remade = bp.seasons[name].palette
					for entry, made in if type(remade) == "table" then remade else {} do
						local m = made.material or "Plastic"
						if not MATERIALS[m] then
							err(`seasons.{name}.palette.{tostring(entry)}`, `unknown material "{tostring(m)}"`)
						end
					end
				end
			end
			bp = Season.apply(bp, bp.season)
		end
	end
	local palette = bp.palette or {}
	local parts: { Part } = {}
	local groups: { { name: string, parts: { Part }, stream: any } } = {}
	-- the corner quoins placed (a skin's strips), each with the offset from its middle to its corner and whose
	-- building it dresses: one on a corner butted against another building is taken out at the end of the build
	local quoined: { { part: Part, c: { number }, owner: string? } } = {}
	local current: { Part } = {}
	-- worn trails painted INTO the terrain (path "worn": "<Material>"): { material, width, points = {{x, y, z}} }
	local paints: { any } = {}
	-- every road / trail laid so far ({ points = {{x, z}}, r = keep-clear radius }): later scatter / forest / rocks
	-- steps keep off them by themselves ("avoidRoads": false to allow it)
	local roadLines: { { points: { { number } }, r: number } } = {}
	local function nearRoad(x: number, z: number, margin: number): boolean
		for _, rl in roadLines do
			local pts = rl.points
			for k = 1, #pts - 1 do
				local x1, z1, x2, z2 = pts[k][1], pts[k][2], pts[k + 1][1], pts[k + 1][2]
				local vx, vz = x2 - x1, z2 - z1
				local t = math.clamp(((x - x1) * vx + (z - z1) * vz) / math.max(vx * vx + vz * vz, 1e-9), 0, 1)
				if (x - x1 - vx * t) ^ 2 + (z - z1 - vz * t) ^ 2 < (rl.r + margin) ^ 2 then
					return true
				end
			end
		end
		return false
	end

	-- the terrain parts can stand on: a step with "ground": true is lifted onto the compiled ground at its anchor
	-- (center / pos / from / start / first point) and its lowest blocks sink into the slope (nothing floats)
	local groundOps = {}
	-- ROAD BEDS (src/kit/RoadBed.luau; the owner's W-R07): the beds each ground op carries, by the op's place among the
	-- ground ops - laid by "bed" on a path, handed to the game with the land and to kit world check with its heights
	local bedsOf: { [number]: { any } } = {}
	local bedsLaid: { any } = {} -- (each bed: its road, its grade, the most it cuts and fills)
	local junctionsLaid: { any } = {} -- (each junction pad: its node, kind, radius, arms, tilt - kit/lib/worldjunction.luau)
	local roomsFurnished: { any } = {} -- (each room of a floor cut into rooms that was furnished: interior_v2)
	local bedChars = 0 -- (the characters the beds come to in the game's record of its land)
	local waterOps = {} -- (water a routed road goes round: kit/lib/worldroute.luau)
	do
		local envG = Environment.compile(bp)
		for _, op in (envG and envG.terrain) or {} do
			if op.kind == "ground" then
				table.insert(groundOps, op.spec)
			elseif op.kind == "water" or (op.kind == "block" and op.spec.wasWater == true) then
				-- (a lake a season froze - kit/lib/worldseason.luau makes it a block of ice - is still a lake to
				-- the road: the same road in every season, and never laid under the ice)
				table.insert(waterOps, op.spec)
			end
		end
	end
	local function groundAt(x: number, z: number): number?
		local best: number? = nil
		for _, s in groundOps do
			if math.abs(x - s.center[1]) <= s.size[1] / 2 and math.abs(z - s.center[3]) <= s.size[2] / 2 then
				local h = World.groundHeight(s, x, z)
				if best == nil or h > best then
					best = h
				end
			end
		end
		return best
	end
	-- the painted role under (x, z): the topmost ground op that is painted there
	local function roleAt(x: number, z: number): string?
		local best: number?, role: string? = nil, nil
		for _, s in groundOps do
			if math.abs(x - s.center[1]) <= s.size[1] / 2 and math.abs(z - s.center[3]) <= s.size[2] / 2 then
				local h = World.groundHeight(s, x, z)
				if best == nil or h > best then
					best, role = h, World.roleAt(s, x, z)
				end
			end
		end
		return role
	end
	-- may an item of a scatter / cover step stand at (x, z)? With "ground": true it stands on the terrain (and the
	-- terrain's height is returned), "slopeMax" (degrees) keeps it off cliffs, "above" / "below" bound the height,
	-- "avoid": [[x, z, radius], ...] keeps paths, plazas and water clear.
	local function terrainSite(spec: any, x: number, z: number): (boolean, number)
		for _, a in spec.avoid or {} do
			if (x - a[1]) ^ 2 + (z - a[2]) ^ 2 < a[3] ^ 2 then
				return false, 0
			end
		end
		if spec.avoidRoads ~= false and nearRoad(x, z, spec.roadMargin or 4) then
			return false, 0
		end
		if spec.ground ~= true then
			return true, 0
		end
		local h = groundAt(x, z)
		if h == nil then
			return false, 0
		end
		if (spec.above and h < spec.above) or (spec.below and h > spec.below) then
			return false, h
		end
		-- ECOLOGY from the painter: "roles": only on these painted roles; "avoidRoles": never on these
		if type(spec.roles) == "table" or type(spec.avoidRoles) == "table" then
			local role = roleAt(x, z)
			if type(spec.roles) == "table" and (role == nil or not table.find(spec.roles, role)) then
				return false, h
			end
			if type(spec.avoidRoles) == "table" and role ~= nil and table.find(spec.avoidRoles, role) then
				return false, h
			end
		end
		if spec.slopeMax then
			local e = 2
			local gx = ((groundAt(x + e, z) or h) - (groundAt(x - e, z) or h)) / (2 * e)
			local gz = ((groundAt(x, z + e) or h) - (groundAt(x, z - e) or h)) / (2 * e)
			if math.deg(math.atan(math.sqrt(gx * gx + gz * gz))) > spec.slopeMax then
				return false, h
			end
		end
		return true, h
	end
	-- per step: { dy = lift, sink = studs blocks reach below their base } while a "ground" step is being built
	local stepGround: { dy: number, sink: number }? = nil

	local function mat(path: string, key: any): (string, { number }, number)
		local entry = palette[key]
		if type(entry) ~= "table" then
			err(path, `unknown palette entry "{tostring(key)}" — add it to "palette"`)
			return "Plastic", { 163, 162, 165 }, 0
		end
		local m = entry.material or "Plastic"
		if not MATERIALS[m] then
			err(path, `palette "{key}": unknown material "{m}"`)
		end
		return m, entry.color or { 163, 162, 165 }, entry.transparency or 0
	end

	-- world meshes (kit world meshes -> build/worldmeshes/meshes.json; kit upload -> ids.worldmeshes / worldtextures)
	local meshReg: { [string]: any } = {}
	local mapIds: { [string]: any } = {}
	local meshIds, texIds = {}, {}
	do
		local rp = Config.build("worldmeshes") .. "/meshes.json"
		if type(opts) == "table" and type(opts.meshes) == "table" then
			meshReg = opts.meshes
		elseif fs.isFile(rp) then
			local ok, r = pcall(serde.decode, "json" :: any, fs.readFile(rp))
			if ok and type(r) == "table" then
				meshReg = r
			end
		end
		local ip = Config.path("ids")
		if type(opts) == "table" and type(opts.ids) == "table" then
			-- (opts.ids: an ids table in place of assets/ids.json - the kit's own specs: no upload)
			meshIds, texIds = opts.ids.worldmeshes or {}, opts.ids.worldtextures or {}
			mapIds = opts.ids.terrainmaps or {}
		elseif fs.isFile(ip) then
			local ok, ids = pcall(serde.decode, "json" :: any, fs.readFile(ip))
			if ok and type(ids) == "table" then
				meshIds, texIds = ids.worldmeshes or {}, ids.worldtextures or {}
				mapIds = ids.terrainmaps or {}
			end
		end
	end
	local meshesNoId: { [string]: boolean } = {}
	local trimsNoId: { [string]: boolean } = {} -- (the W3 kit's trim maps not uploaded yet: kit_trim_<sheet>_<map>)
	-- scanned meshes set far from their real size: one warning each (the first place, how many), not one a copy
	local scanOff: { [string]: { path: string, n: number, lo: number, hi: number, r: any } } = {}
	local scanOrder: { string } = {}
	local placeMesh: (string, string, number, number, number, number, number, boolean, any) -> Part? -- (below `add`)
	-- THE GREYBOX (kit world greybox; LIMITATIONS_FIXES_V3.md stage A.2, W1 "walked greybox ... before meshes"): the
	-- world with no mesh - a skin or a facade not worn (the house built plain, its walls seen), the far ranges as their
	-- wedges, every other mesh a plain grey box of its own size where it stands
	local greybox = type(opts) == "table" and opts.greybox == true

	-- the turn of the step being built ({ deg, x, z }, set at the step's start): `add` drops a part wholly under the
	-- land, and must ask that of where the part WILL stand once its step is turned (a fresh reader, 2026-11-13: a part
	-- turned onto open ground was dropped for the hill it was typed under, with no message)
	local stepTurn: any = nil
	-- the step being built stands in a placed PREFAB (kit/lib/worldprefab.luau): it is built where it is typed and
	-- moved after, so `add` must not judge it by the land where it is typed
	local stepPlaced = false
	-- the building being DRESSED (a skin, a facade): its path while it is built. Every part of it made unseen says
	-- whose it is (KitBlockout) and every mesh that dresses it says the same (KitDress), so the runtime can show a
	-- building's own walls while its meshes are not there (src/kit/WorldMeshes.luau; the owner's W-R01)
	-- (not only a building: a mesh TREE has an unseen trunk you bump into, a castle WALL of modules and a mesh
	-- TOWER stand on unseen collision too - a fresh reader found all three still invisible obstacles)
	local dressKey: string? = nil
	local dressSeq = 0
	local function dressBegin(path: string)
		dressSeq += 1
		dressKey = `{path}#{dressSeq}`
	end
	local function add(path: string, spec: any, size: { number }, pos: { number }, rot: { { number } }?)
		local m, color, transparency = mat(path .. ".mat", spec.mat)
		local shape = spec.shape or "Block"
		if not SHAPES[shape] then
			err(path .. ".shape", "shape must be Block | Ball | Cylinder | Wedge")
		end
		for i = 1, 3 do
			if type(size[i]) ~= "number" or size[i] <= 0 or size[i] > 2048 then
				err(path .. ".size", `size must be 3 numbers in 0..2048 (got {tostring(size[i])})`)
				return
			end
		end
		local r = rot or World.rotation(spec.rot)
		if stepGround then
			pos = { pos[1], pos[2] + stepGround.dy, pos[3] }
			-- a block resting at the step's base sinks into the terrain (on a slope one side would float)
			local upright = math.abs(r[2][2]) > 0.999
			if stepGround.sink > 0 and shape == "Block" and upright and spec.sink ~= false then
				local bottom = pos[2] - size[2] / 2
				if bottom <= stepGround.dy + 0.6 then
					size = { size[1], size[2] + stepGround.sink, size[3] }
					pos = { pos[1], pos[2] - stepGround.sink / 2, pos[3] }
				end
			end
		end
		-- a part wholly under the land is wasted budget nobody sees or touches (kit world check's look lint): its top
		-- below the land at its centre and corners -> never emitted (spawns, lights, particles and backdrops kept)
		if
			#groundOps > 0
			and not stepPlaced -- (a prefab's step is built where it is typed and moved after: not judged here)
			and not spec.backdrop
			and spec.name ~= "Spawn"
			and not spec.light
			and not spec.particles
		then
			local tr, tx, tz = r, pos[1], pos[3] -- (as it will stand)
			if stepTurn then
				tr = mul(World.turnMatrix(stepTurn.deg), r)
				tx, tz = World.turnPoint(pos[1], pos[3], stepTurn.x, stepTurn.z, stepTurn.deg)
			end
			local ex = math.abs(tr[1][1]) * size[1] / 2
				+ math.abs(tr[1][2]) * size[2] / 2
				+ math.abs(tr[1][3]) * size[3] / 2
			local ey = math.abs(tr[2][1]) * size[1] / 2
				+ math.abs(tr[2][2]) * size[2] / 2
				+ math.abs(tr[2][3]) * size[3] / 2
			local ez = math.abs(tr[3][1]) * size[1] / 2
				+ math.abs(tr[3][2]) * size[2] / 2
				+ math.abs(tr[3][3]) * size[3] / 2
			local lowest = math.huge
			for _, o in { { 0, 0 }, { -1, -1 }, { 1, -1 }, { -1, 1 }, { 1, 1 } } do
				local h = groundAt(tx + o[1] * ex, tz + o[2] * ez)
				if h == nil then
					lowest = -math.huge
					break
				end
				lowest = math.min(lowest, h)
			end
			if pos[2] + ey < lowest - 0.5 then
				return nil
			end
		end
		local p: Part = {
			name = spec.name or "Part",
			class = if shape == "Wedge" then "WedgePart" else "Part",
			shape = if shape == "Wedge" then nil else shape,
			size = size,
			pos = pos,
			rot = r,
			color = color,
			material = m,
			transparency = spec.transparency or transparency,
			collide = spec.collide ~= false,
			query = if spec.collide == false and spec.query == false then false else nil,
			anchored = not spec.physics,
			axisAligned = isIdentity(r),
			backdrop = spec.backdrop,
		}
		-- glows and particles ride as children of the part (PointLight / SpotLight, ParticleEmitter presets)
		if spec.light or spec.particles then
			p.children = {}
			if type(spec.light) == "table" then
				table.insert(p.children, { kind = "light", spec = spec.light })
			end
			if spec.particles then
				if not PARTICLES[spec.particles] then
					err(path .. ".particles", `unknown particle preset "{tostring(spec.particles)}" ({PARTICLE_NAMES})`)
				else
					table.insert(p.children, { kind = "particles", preset = spec.particles })
				end
			end
		end
		-- ACOUSTICS: a part that does not collide lets sound through (leaves, grass, flames, rugs, mist) - except a
		-- roof, a window pane or a "audio": true part; "audio": false lets a colliding part pass too (Acoustics runtime)
		if World.audioPass(p.name, p.collide, spec) then
			p.attributes = p.attributes or {}
			p.attributes.KitAudioPass = true
		end
		if dressKey and spec.transparency == 1 and spec.name ~= "KitMesh" then
			p.attributes = p.attributes or {}
			p.attributes.KitBlockout = dressKey
		end
		table.insert(parts, p)
		table.insert(current, p)
		return p
	end

	-- a world mesh standing at (x, base, z): an invisible placeholder the runtime (kit WorldMeshes) turns into the
	-- MeshPart (AssetService:CreateMeshPartAsync — nothing can write MeshId, measured), scaled to `height`, turned
	-- `yaw` degrees. The mesh's own origin (its trunk's foot, a rock's base) is put on (x, base, z).
	placeMesh = function(path, name, x, base, z, height, yaw, collide, palMat, scanResize: boolean?)
		local r = meshReg[name]
		if not r then
			err(path, `no world mesh "{name}" — make it: lune run kit world meshes`)
			return nil
		end
		if greybox and type(r.size) == "table" then
			local g = height / math.max(r.size[2], 0.01)
			local lo = if type(r.min) == "table" then r.min else { -r.size[1] / 2, 0, -r.size[3] / 2 }
			local gx, gy, gz = (lo[1] + r.size[1] / 2) * g, (lo[2] + r.size[2] / 2) * g, (lo[3] + r.size[3] / 2) * g
			local ga = math.rad(yaw)
			return add(
				path,
				{ name = "Greybox", mat = palMat, collide = collide, sink = false },
				{ math.max(r.size[1] * g, 0.05), math.max(r.size[2] * g, 0.05), math.max(r.size[3] * g, 0.05) },
				{ x + gx * math.cos(ga) + gz * math.sin(ga), base + gy, z - gx * math.sin(ga) + gz * math.cos(ga) },
				World.rotation({ 0, yaw, 0 })
			)
		end
		local k = height / math.max(r.size[2], 0.01)
		if r.scan and math.abs(k - 1) > World.SCAN_SPREAD and not scanResize then
			local o = scanOff[name]
			if not o then
				o = { path = path, n = 0, lo = height, hi = height, r = r }
				scanOff[name] = o
				table.insert(scanOrder, name)
			end
			o.n += 1
			o.lo, o.hi = math.min(o.lo, height), math.max(o.hi, height)
		end
		if r.parts then -- an imported asset: one MeshPart per material (a MeshPart carries one texture), placed together
			local first = nil
			local a = math.rad(yaw)
			for _, pn in r.parts do
				local pr = meshReg[pn]
				if pr then
					local pcx, pcy, pcz =
						(pr.min[1] + pr.size[1] / 2) * k,
						(pr.min[2] + pr.size[2] / 2) * k,
						(pr.min[3] + pr.size[3] / 2) * k
					local prx, prz = pcx * math.cos(a) + pcz * math.sin(a), -pcx * math.sin(a) + pcz * math.cos(a)
					local p = add(
						path,
						{ name = "KitMesh", mat = palMat, collide = false, transparency = 1, sink = false },
						{
							math.max(pr.size[1] * k, 0.05),
							math.max(pr.size[2] * k, 0.05),
							math.max(pr.size[3] * k, 0.05),
						},
						{ x + prx, base + pcy, z + prz },
						World.rotation({ 0, yaw, 0 })
					)
					if p then
						p.mesh = pn
						p.meshCollide = (collide and not pr.foliage) or nil
						local id, tex = meshIds[pn], texIds[pn]
						p.attributes = {
							KitMesh = pn,
							MeshId = if id then `rbxassetid://{string.match(tostring(id), "%d+")}` else nil,
							TextureId = if tex then `rbxassetid://{string.match(tostring(tex), "%d+")}` else nil,
							Collide = collide and not pr.foliage,
							KitAudioPass = (not (collide and not pr.foliage)) or nil, -- (foliage lets sound through)
							KitDress = dressKey,
						}
						if not id then
							meshesNoId[pn] = true
						end
						first = first or p
					end
				end
			end
			return first
		end
		local size = { r.size[1] * k, r.size[2] * k, r.size[3] * k }
		local cx, cy, cz =
			(r.min[1] + r.size[1] / 2) * k, (r.min[2] + r.size[2] / 2) * k, (r.min[3] + r.size[3] / 2) * k
		local a = math.rad(yaw)
		local rx, rz = cx * math.cos(a) + cz * math.sin(a), -cx * math.sin(a) + cz * math.cos(a)
		local p = add(
			path,
			{ name = "KitMesh", mat = palMat, collide = false, transparency = 1, sink = false },
			size,
			{ x + rx, base + cy, z + rz },
			World.rotation({ 0, yaw, 0 })
		)
		if p then
			p.mesh = name
			p.meshCollide = collide or nil
			local id, tex = meshIds[name], texIds[name]
			p.attributes = {
				KitMesh = name,
				MeshId = if id then `rbxassetid://{string.match(tostring(id), "%d+")}` else nil,
				TextureId = if tex then `rbxassetid://{string.match(tostring(tex), "%d+")}` else nil,
				Collide = collide,
				KitAudioPass = (not collide) or nil,
				KitDress = dressKey,
			}
			if not id then
				meshesNoId[name] = true
			end
		end
		return p
	end

	-- a FACADE MODULE (kit/lib/worldfacade.luau; kit world meshes kind "gothic_module") with its own origin - the
	-- foot of its middle, on the wall's centre line - on (x, base, z), turned `yaw`, STRETCHED sx / sy / sz along its
	-- own width / height / depth (a MeshPart's Size is free per axis). Seen only: the wall behind it is the collision.
	-- (the stretch is asked against the module's recipe BOX - registry "box" - not the mesh's own bounds: a hood
	-- mould or an eave that stands past the box must not shrink the whole module)
	local function placeModule(path, name, x, base, z, yaw, sx, sy, sz, palMat, own: any?)
		local r = meshReg[name]
		if not r then
			return nil
		end
		-- a module cut from the W3 kit (registry "parts"): its meshes on the OTHER trim sheet stand with it, in the
		-- same frame, stretched by the same factors (each placed by its own bounds)
		if own == nil and type(r.parts) == "table" then
			for _, part in r.parts do
				if type(part) == "string" and type(meshReg[part]) == "table" then
					placeModule(path, part, x, base, z, yaw, sx, sy, sz, palMat, r)
				end
			end
		end
		local cx, cy, cz =
			(r.min[1] + r.size[1] / 2) * sx, (r.min[2] + r.size[2] / 2) * sy, (r.min[3] + r.size[3] / 2) * sz
		local a = math.rad(yaw)
		local rx, rz = cx * math.cos(a) + cz * math.sin(a), -cx * math.sin(a) + cz * math.cos(a)
		local p = add(
			path,
			{ name = "KitMesh", mat = palMat, collide = false, transparency = 1, sink = false },
			{ math.max(r.size[1] * sx, 0.05), math.max(r.size[2] * sy, 0.05), math.max(r.size[3] * sz, 0.05) },
			{ x + rx, base + cy, z + rz },
			World.rotation({ 0, yaw, 0 })
		)
		if p then
			p.mesh = name
			p.module = r.module
			local id, tex = meshIds[name], texIds[name]
			p.attributes = {
				KitMesh = name,
				MeshId = if id then `rbxassetid://{string.match(tostring(id), "%d+")}` else nil,
				TextureId = if tex then `rbxassetid://{string.match(tostring(tex), "%d+")}` else nil,
				Collide = false,
				KitAudioPass = true,
				KitDress = dressKey,
			}
			if not id then
				meshesNoId[name] = true
			end
			-- ITS TRIM SHEET (registry "trim": the W3 kit's shared sheets, kit/world/trims.py): the sheet's three maps
			-- as a SurfaceAppearance the runtime moves onto the MeshPart (a game script cannot write its maps; Rojo
			-- can). A map not uploaded yet: no SurfaceAppearance at all (never one with a hole in it) - the mesh wears
			-- its palette colour, as a mesh with no texture does - and it is said once, with the meshes
			if type(r.trim) == "string" then
				local maps, whole = {}, true
				for _, m in World.TRIM_MAPS do
					local key = `kit_trim_{r.trim}_{m[1]}`
					local mid = texIds[key]
					if mid then
						maps[m[2]] = `rbxassetid://{string.match(tostring(mid), "%d+")}`
					else
						whole = false
						trimsNoId[key] = true
					end
				end
				if whole then
					local kids: { any } = p.children or {}
					table.insert(kids, { kind = "surface", maps = maps })
					p.children = kids
				end
			end
		end
		return p
	end
	local facadeSaid: { [string]: boolean } = {}

	-- a cylinder from a to b (Roblox cylinders lie along local X: the X column of the rotation is a -> b)
	local function between(path: string, spec: any, a: { number }, b: { number }, radius: number): Part?
		local d = { b[1] - a[1], b[2] - a[2], b[3] - a[3] }
		local len = math.sqrt(d[1] ^ 2 + d[2] ^ 2 + d[3] ^ 2)
		if len < 0.05 then
			return nil
		end
		local s = table.clone(spec)
		s.shape = "Cylinder"
		return add(path, s, { len, radius * 2, radius * 2 }, {
			(a[1] + b[1]) / 2,
			(a[2] + b[2]) / 2,
			(a[3] + b[3]) / 2,
		}, World.alongX(d))
	end

	-- a wall from -> to with gaps (doorways: open to the floor; windows: "sill" > 0 keeps a wall under them)
	local function buildWall(path: string, spec: any)
		-- "mesh": a castle wall module (kit world meshes kind "wall") tiled along it: the parts stay as invisible
		-- collision (walking, reachability and kit world check are unchanged), the modules are what is seen
		local hide = if spec.mesh or spec.hidden then 1 else nil
		local ownDress = spec.mesh ~= nil and dressKey == nil -- (a wall of modules that is no building's)
		if ownDress then
			dressBegin(path)
		end
		local fx, fz, tx, tz = spec.from[1], spec.from[2], spec.to[1], spec.to[2]
		local dx, dz = tx - fx, tz - fz
		local len = math.sqrt(dx * dx + dz * dz)
		local y0, h, t = spec.y or 0, spec.height, spec.thickness
		if len <= 0 or not h or not t then
			err(path, "wall needs from != to, height and thickness")
			return
		end
		local yaw = math.deg(math.atan2(-dz, dx)) -- CFrame.Angles yaw so local +X runs from -> to
		local r = World.rotation({ 0, yaw, 0 })
		local gaps = table.clone(spec.gaps or {})
		table.sort(gaps, function(a, b)
			return a.at < b.at
		end)
		local cursor = 0
		local function segment(a: number, b: number, bottom: number, top: number, name: string)
			if b - a <= 0.01 or top - bottom <= 0.01 then
				return
			end
			local mid = (a + b) / 2
			add(path, { name = name, mat = spec.mat, transparency = hide }, { b - a, top - bottom, t }, {
				fx + dx / len * mid,
				y0 + (bottom + top) / 2,
				fz + dz / len * mid,
			}, r)
		end
		for gi, g in gaps do
			local gs, ge = g.at - g.width / 2, g.at + g.width / 2
			if gs < cursor or ge > len then
				err(`{path}.gaps[{gi}]`, "gap must lie inside the wall and not overlap the previous gap")
				continue
			end
			segment(cursor, gs, 0, h, "Wall")
			segment(gs, ge, 0, g.sill or 0, "Sill")
			segment(gs, ge, g.height or (h * 0.7), h, "Lintel")
			cursor = ge
		end
		segment(cursor, len, 0, h, "Wall")
		local function inGap(at: number, pad: number): boolean
			for _, g in gaps do
				if math.abs(at - g.at) < g.width / 2 + pad then
					return true
				end
			end
			return false
		end
		-- "crenels": true | { width } — merlons along the top (a battlement)
		if spec.crenels then
			local cw = if type(spec.crenels) == "table" then spec.crenels.width or 1.6 else 1.6
			local at = cw / 2
			while at <= len - cw / 2 do
				-- (no merlon over a gateway that opens to the top of the wall)
				local overGap = false
				for _, g in gaps do
					if math.abs(at - g.at) < g.width / 2 and (g.height or (h * 0.7)) >= h then
						overGap = true
					end
				end
				if overGap then
					at += cw * 2
					continue
				end
				add(path, { name = "Merlon", mat = spec.mat, sink = false, transparency = hide }, { cw, 2.4, t }, {
					fx + dx / len * at,
					y0 + h + 1.2,
					fz + dz / len * at,
				}, r)
				at += cw * 2
			end
		end
		-- "buttresses": { every, depth, width, side: 1 | -1 } — piers against one face with a sloped cap
		local b = spec.buttresses
		if type(b) == "table" and not spec.mesh then
			local every, bd, bw, side = b.every or 12, b.depth or 3, b.width or 2.5, b.side or 1
			local nx, nz = r[1][3] * side, r[3][3] * side -- the wall's local Z, toward the chosen face
			local capYaw = yaw + (if side > 0 then 180 else 0) -- the cap's back (vertical) face against the wall
			local at = every / 2
			while at < len do
				if not inGap(at, bw) then
					local px = fx + dx / len * at + nx * (t / 2 + bd / 2)
					local pz = fz + dz / len * at + nz * (t / 2 + bd / 2)
					local bh = h * 0.72
					add(path, { name = "Buttress", mat = spec.mat }, { bw, bh, bd }, { px, y0 + bh / 2, pz }, r)
					add(
						path,
						{ name = "ButtressCap", mat = spec.mat, shape = "Wedge", sink = false },
						{ bw, h * 0.18, bd },
						{ px, y0 + bh + h * 0.09, pz },
						World.rotation({ 0, capYaw, 0 })
					)
				end
				at += every
			end
		end
		if spec.mesh then
			if not meshReg[spec.mesh] then
				err(path .. ".mesh", `no world mesh "{spec.mesh}" — make it: lune run kit world meshes`)
				return
			end
			-- scale: the module's walkway (meshWalk, studs in the mesh) lands on the wall's walkable top; each run
			-- between gaps is then filled by a whole number of modules, stretched a few % to fit exactly
			local k0 = h / (spec.meshWalk or 14.85)
			local front = if spec.meshFront == -1 then -1 else 1 -- which face is the castle's outside: local +Z or -Z
			local nx, nz = r[1][3] * front, r[3][3] * front -- (the wall's local Z, toward the outside)
			local function run(ra: number, rb: number, name: string)
				local reg = meshReg[name]
				if not reg or rb - ra < 1 then
					return
				end
				local n = math.max(1, math.floor((rb - ra) / (reg.size[1] * k0) + 0.5))
				local k = (rb - ra) / (n * reg.size[1])
				for i = 0, n - 1 do
					-- the module's origin is its outer face at its start; it runs along +X (front 1) or back (front -1)
					local along = if front == 1 then ra + i * reg.size[1] * k else rb - i * reg.size[1] * k
					local ox = fx + dx / len * along + nx * t / 2
					local oz = fz + dz / len * along + nz * t / 2
					placeMesh(
						path,
						name,
						ox,
						y0,
						oz,
						reg.size[2] * k,
						if front == 1 then yaw else yaw + 180,
						false,
						spec.mat
					)
				end
			end
			local cur = 0
			for _, g in gaps do
				local gs, ge = g.at - g.width / 2, g.at + g.width / 2
				run(cur, gs, spec.mesh)
				if spec.gateMesh then -- a gate module (kind "wall", open "ground") spans the gap
					run(gs, ge, spec.gateMesh)
				end
				cur = ge
			end
			run(cur, len, spec.mesh)
		end
		if ownDress then
			dressKey = nil
		end
	end

	-- a triangular prism (two wedges back to back): crest along local X at height H over (cx, by, cz), base D deep.
	-- Two of them crossed at right angles make a point from any side: mountain peaks, pine tiers, spires.
	local function prism(
		path: string,
		spec: any,
		cx: number,
		by: number,
		cz: number,
		L: number,
		H: number,
		D: number,
		yaw: number
	)
		L, H, D = math.min(L, 2048), math.min(H, 2048), math.min(D, 4096)
		local ry = World.rotation({ 0, yaw, 0 })
		for side = -1, 1, 2 do
			local s = table.clone(spec)
			s.shape = "Wedge"
			local off = side * D / 4
			add(path, s, { L, H, D / 2 }, {
				cx + ry[1][3] * off,
				by + H / 2,
				cz + ry[3][3] * off,
			}, World.rotation({ 0, yaw + (if side > 0 then 180 else 0), 0 }))
		end
	end

	-- a room's furniture as parts: each piece in its role's material, a candle flame on top of what holds one, a fire
	-- in a hearth's mouth (both lit); `y` is the floor's top
	local function placeFurniture(spec: any, path: string, pieces: { Interior.Piece }, y: number)
		local cfg = if type(spec.interior) == "table" then spec.interior else {}
		local mats = if type(cfg.mats) == "table" then cfg.mats else {}
		local function roleMat(role: string): string
			if type(mats[role]) == "string" then
				return mats[role]
			end
			if role == "wood" then
				return if palette.wood then "wood" else spec.slab or spec.mat
			elseif role == "cloth" then
				return if palette.cloth then "cloth" else spec.roofMat or spec.mat
			elseif role == "metal" then
				return if palette.metal then "metal" else spec.trim or spec.mat
			elseif role == "fire" then
				return if palette.fire then "fire" else spec.mat
			end
			return spec.mat
		end
		for _, p in pieces do
			add(path, { name = p.name, mat = roleMat(p.role), sink = false, collide = not p.flat }, p.size, p.pos)
			if p.flame then -- a candle flame on top, lit
				add(path, {
					name = "Candle",
					mat = roleMat("fire"),
					collide = false,
					sink = false,
					light = { color = { 255, 170, 90 }, range = 14, brightness = 1.2 },
				}, { 0.5, 0.8, 0.5 }, { p.pos[1], p.pos[2] + p.size[2] / 2 + 0.4, p.pos[3] })
			end
			if p.light then -- a hearth: a fire in its mouth, lit
				add(path, {
					name = "HearthFire",
					mat = roleMat("fire"),
					collide = false,
					sink = false,
					light = { color = { 255, 140, 60 }, range = 22, brightness = 2.5 },
				}, { math.max(1, p.size[1] * 0.4), 1.2, math.max(1, p.size[3] * 0.4) }, {
					p.pos[1],
					y + 0.6,
					p.pos[3],
				})
			end
		end
	end

	-- a building floor's furniture (spec.interior = true | { floors = {"hall", "chamber", ...}, mats = {wood=, ...} }):
	-- the inner room, its clear zones (the stair lane + landings, the door's swing and path in) and its windows go to
	-- Interior.layout; Interior.check re-proves the rules (a broken one is an error, never a silent clutter)
	local function furnish(
		spec: any,
		path: string,
		f: number,
		y: number,
		fh: number,
		t: number,
		lane: any,
		flight: number,
		openings: { any },
		sides: any
	)
		local c, s = spec.center, spec.size
		local cfg = if type(spec.interior) == "table" then spec.interior else {}
		local kinds = if type(cfg.floors) == "table" then cfg.floors else { "hall", "chamber", "store" }
		local kind = kinds[math.min(f + 1, #kinds)]
		if f > 0 and kind == "hall" then
			kind = "chamber"
		end
		if not table.find(Interior.KINDS, kind) then
			-- (an unknown kind furnished nothing, said nowhere: an empty room)
			err(`{path}.interior.floors`, `no room kind "{tostring(kind)}" ({table.concat(Interior.KINDS, " | ")})`)
			return
		end
		local room: Interior.Room = {
			x0 = c[1] - s[1] / 2 + t / 2,
			x1 = c[1] + s[1] / 2 - t / 2,
			z0 = c[3] - s[2] / 2 + t / 2,
			z1 = c[3] + s[2] / 2 - t / 2,
			y = y,
			height = fh,
			clear = {},
			windows = {},
			door = if f == 0 and type(spec.door) == "table" then spec.door.side else nil,
		}
		if spec.stairs == true then
			table.insert(room.clear :: { Interior.Rect }, {
				x0 = lane.x - lane.w / 2 - 0.5,
				x1 = (lane.east or (lane.x + lane.w / 2)) + 0.5,
				z0 = lane.z0 - Interior.WALKWAY,
				z1 = lane.z0 + flight + Interior.WALKWAY,
			})
		end
		for _, o in openings do
			local sd = sides[o.side]
			local ax, az = sd[2][1] - sd[1][1], sd[2][2] - sd[1][2]
			local along = (sd[3] / 2 + o.at) / sd[3]
			local px, pz = sd[1][1] + ax * along, sd[1][2] + az * along
			if (o.sill or 0) > 0 then
				local axis = if o.side == "N" or o.side == "S" then px else pz
				table.insert(
					room.windows :: { any },
					{ side = o.side, from = axis - o.width / 2, to = axis + o.width / 2, sill = o.sill }
				)
			else -- a door: its swing and the path in stay clear (width + 2 across, 7 studs in)
				local half = o.width / 2 + 1
				local depth = 7
				local r: Interior.Rect = if o.side == "N"
					then { x0 = px - half, x1 = px + half, z0 = room.z0, z1 = room.z0 + depth }
					elseif o.side == "S" then { x0 = px - half, x1 = px + half, z0 = room.z1 - depth, z1 = room.z1 }
					elseif o.side == "W" then { x0 = room.x0, x1 = room.x0 + depth, z0 = pz - half, z1 = pz + half }
					else { x0 = room.x1 - depth, x1 = room.x1, z0 = pz - half, z1 = pz + half }
				table.insert(room.clear :: { Interior.Rect }, r)
			end
		end
		local pieces = Interior.layout(room, kind, f)
		for _, problem in Interior.check(room, pieces) do
			err(`{path}.interior.floor{f + 1}`, problem)
		end
		placeFurniture(spec, path, pieces, y)
	end

	-- FURNITURE BY ROOM (LIMITATIONS_FIXES_V4 5.1 / 13.5, interior_v2): a floor cut into rooms by the binary split
	-- (kit/lib/worldrooms.luau) gets each room furnished on its own - its kind from Interior.program (the biggest room
	-- the floor's main use, the smallest one open to the stair hall its stair_shaft / landing; "interior": { "byRoom":
	-- true, "rooms": [["hall", "kitchen"], ...] } names them per floor), its walls inside the partitions, every
	-- doorway of its partitions and of the outer walls a way in kept clear (7 studs in, a stud each side), its side
	-- open to the stair hall a way in, its windows from the outer walls; Interior.check proves each room
	local function furnishRooms(
		spec: any,
		path: string,
		f: number,
		floors: number,
		y: number,
		fh: number,
		t: number,
		lane: any,
		flight: number,
		openings: { any },
		sides: any,
		floorPlan: any,
		ox: number,
		oz: number
	)
		local cfg = if type(spec.interior) == "table" then spec.interior else {}
		local half = Rooms.DEFAULTS.thickness / 2
		local infos = {}
		for _, r in floorPlan.rooms do
			table.insert(infos, { area = (r.x1 - r.x0) * (r.z1 - r.z0), openToHall = r.openToHall })
		end
		local kinds = Interior.program(infos, f, floors, spec.stairs == true)
		local named = if type(cfg.rooms) == "table" then cfg.rooms[f + 1] else nil
		local c, s = spec.center, spec.size
		-- the outer walls' inner faces (where a room meets the outside)
		local inX0, inX1 = c[1] - s[1] / 2 + t / 2, c[1] + s[1] / 2 - t / 2
		local inZ0, inZ1 = c[3] - s[2] / 2 + t / 2, c[3] + s[2] / 2 - t / 2
		for k, r in floorPlan.rooms do
			local kind = kinds[k]
			if type(named) == "table" and named[k] ~= nil then
				kind = named[k]
			end
			if not table.find(Interior.KINDS, kind) then
				err(`{path}.interior.rooms`, `no room kind "{tostring(kind)}" ({table.concat(Interior.KINDS, " | ")})`)
				continue
			end
			local room: Interior.Room = {
				x0 = ox + r.x0,
				x1 = ox + r.x1,
				z0 = oz + r.z0,
				z1 = oz + r.z1,
				y = y,
				height = fh,
				clear = {},
				windows = {},
			}
			local clear = room.clear :: { Interior.Rect }
			local ways: { string } = {} -- (the sides its ways in are on, the first is its door)
			-- its partitions: the room stands inside them, each doorway in them a way in
			for _, wall in floorPlan.walls do
				if wall.axis == "z" then
					local onLo, onHi = math.abs(r.x0 - wall.at) < 1e-6, math.abs(r.x1 - wall.at) < 1e-6
					if (onLo or onHi) and wall.from < r.z1 - 1e-6 and wall.to > r.z0 + 1e-6 then
						if onLo then
							room.x0 = ox + r.x0 + half
						else
							room.x1 = ox + r.x1 - half
						end
						if wall.door > r.z0 and wall.door < r.z1 then
							local dz, hw = oz + wall.door, wall.doorWidth / 2 + 1
							if onLo then
								table.insert(clear, { x0 = room.x0, x1 = room.x0 + 7, z0 = dz - hw, z1 = dz + hw })
								table.insert(ways, "W")
							else
								table.insert(clear, { x0 = room.x1 - 7, x1 = room.x1, z0 = dz - hw, z1 = dz + hw })
								table.insert(ways, "E")
							end
						end
					end
				else
					local onLo, onHi = math.abs(r.z0 - wall.at) < 1e-6, math.abs(r.z1 - wall.at) < 1e-6
					if (onLo or onHi) and wall.from < r.x1 - 1e-6 and wall.to > r.x0 + 1e-6 then
						if onLo then
							room.z0 = oz + r.z0 + half
						else
							room.z1 = oz + r.z1 - half
						end
						if wall.door > r.x0 and wall.door < r.x1 then
							local dx, hw = ox + wall.door, wall.doorWidth / 2 + 1
							if onLo then
								table.insert(clear, { x0 = dx - hw, x1 = dx + hw, z0 = room.z0, z1 = room.z0 + 7 })
								table.insert(ways, "N")
							else
								table.insert(clear, { x0 = dx - hw, x1 = dx + hw, z0 = room.z1 - 7, z1 = room.z1 })
								table.insert(ways, "S")
							end
						end
					end
				end
			end
			-- (the clear zones were cut before the partition's half was known on the other axis: kept inside)
			for _, z in clear do
				z.x0, z.x1 = math.max(z.x0, room.x0), math.min(z.x1, room.x1)
				z.z0, z.z1 = math.max(z.z0, room.z0), math.min(z.z1, room.z1)
			end
			-- its side open to the stair hall: the whole side a way in, a walkway deep
			if r.openToHall and floorPlan.hall > 0 and math.abs(r.x0 - floorPlan.hall) < 1e-6 then
				table.insert(clear, {
					x0 = room.x0,
					x1 = room.x0 + Interior.WALKWAY,
					z0 = room.z0,
					z1 = room.z1,
				})
				table.insert(ways, "W")
			end
			-- the outer walls' openings on its sides: a door a way in, a window kept clear of tall pieces
			for _, o in openings do
				local sd = sides[o.side]
				local ax, az = sd[2][1] - sd[1][1], sd[2][2] - sd[1][2]
				local along = (sd[3] / 2 + o.at) / sd[3]
				local px, pz = sd[1][1] + ax * along, sd[1][2] + az * along
				local onSide = (o.side == "N" and math.abs(room.z0 - inZ0) < 0.01 and px > room.x0 and px < room.x1)
					or (o.side == "S" and math.abs(room.z1 - inZ1) < 0.01 and px > room.x0 and px < room.x1)
					or (o.side == "W" and math.abs(room.x0 - inX0) < 0.01 and pz > room.z0 and pz < room.z1)
					or (o.side == "E" and math.abs(room.x1 - inX1) < 0.01 and pz > room.z0 and pz < room.z1)
				if onSide then
					local axis = if o.side == "N" or o.side == "S" then px else pz
					if (o.sill or 0) > 0 then
						table.insert(
							room.windows :: { any },
							{ side = o.side, from = axis - o.width / 2, to = axis + o.width / 2, sill = o.sill }
						)
					else
						local hw = o.width / 2 + 1
						table.insert(
							clear,
							if o.side == "N"
								then { x0 = px - hw, x1 = px + hw, z0 = room.z0, z1 = room.z0 + 7 }
								elseif o.side == "S" then {
									x0 = px - hw,
									x1 = px + hw,
									z0 = room.z1 - 7,
									z1 = room.z1,
								}
								elseif o.side == "W" then {
									x0 = room.x0,
									x1 = room.x0 + 7,
									z0 = pz - hw,
									z1 = pz + hw,
								}
								else { x0 = room.x1 - 7, x1 = room.x1, z0 = pz - hw, z1 = pz + hw }
						)
						table.insert(ways, 1, o.side) -- (the street door is the room's door)
					end
				end
			end
			if spec.stairs == true then -- (the flight and its landings, where they reach into this room)
				local st = {
					x0 = lane.x - lane.w / 2 - 0.5,
					x1 = (lane.east or (lane.x + lane.w / 2)) + 0.5,
					z0 = lane.z0 - Interior.WALKWAY,
					z1 = lane.z0 + flight + Interior.WALKWAY,
				}
				if Interior.overlaps(st, { x0 = room.x0, x1 = room.x1, z0 = room.z0, z1 = room.z1 }) then
					table.insert(clear, st)
				end
			end
			room.door = ways[1]
			local pieces = Interior.layout(room, kind, f * 17 + k)
			-- (a room its kind cannot furnish - a 20 x 9 chamber whose doors' ways in leave no wall a bed fits - takes
			-- the next kind that fits it: a study, a store; a stair's room left clear is a passage, as meant)
			local function standing(ps: { Interior.Piece }): number
				local n = 0
				for _, p in ps do
					n += if p.flat then 0 else 1
				end
				return n
			end
			if standing(pieces) == 0 and kind ~= "stair_shaft" and kind ~= "landing" then
				for _, other in { "study", "store", "landing" } do
					local tryPieces = Interior.layout(room, other, f * 17 + k)
					if standing(tryPieces) > 0 then
						pieces, kind = tryPieces, other
						break
					end
				end
			end
			for _, problem in Interior.check(room, pieces) do
				err(`{path}.interior.floor{f + 1}.room{k}`, `({kind}) {problem}`)
			end
			placeFurniture(spec, path, pieces, y)
			table.insert(roomsFurnished, {
				building = spec.name or path,
				floor = f + 1,
				y = y,
				room = k,
				kind = kind,
				rect = { room.x0, room.z0, room.x1, room.z1 },
				pieces = #pieces,
				standing = standing(pieces),
				ways = #clear,
			})
		end
	end

	-- a procedural tree (see the "tree" generator); the forest generator calls it per tree
	local function buildTree(path: string, spec: any)
		-- { pos: [x, y, z], height, style: "oak" | "dead" | "golden" | "erd", seed, trunk: mat, leaves: mat,
		--   radius?, spread? } — a procedural tree: a leaning, tapering trunk, branches from its upper part,
		-- canopy clusters at the branch tips. "golden" glows (Neon canopy + light + falling leaves); "erd" is a
		-- colossal backdrop of twisting trunk strands under a golden dome (never collides, not analysed).
		local rnd = lcg(spec.seed or 1)
		local style = spec.style or "oak"
		local H = spec.height or 30
		local base = spec.pos or { 0, 0, 0 }
		if style == "bush" then
			-- undergrowth: 3 low overlapping clumps
			for k = 1, 3 do
				local a = rnd() * math.pi * 2
				local d = if k == 1 then 0 else H * 0.35
				local rr = H * (0.42 + rnd() * 0.2)
				add(
					path,
					{ name = "Canopy", mat = spec.leaves, shape = "Ball", collide = false },
					{ rr * 2, rr * 2, rr * 2 },
					{
						base[1] + math.cos(a) * d,
						base[2] + rr * 0.55,
						base[3] + math.sin(a) * d,
					}
				)
			end
			return
		end
		if style == "fern" then
			-- a ground fern: 7 fronds radiating from the ground, arching out and down (no trunk)
			for k = 1, 7 do
				local a = k / 7 * 360 + rnd() * 30
				local len = H * (0.8 + rnd() * 0.4)
				local r = World.rotation({ 0, a, 18 + rnd() * 14 })
				add(path, { name = "Frond", mat = spec.leaves, collide = false }, { len, 0.2, H * 0.22 }, {
					base[1] + r[1][1] * len / 2,
					base[2] + r[2][1] * len / 2 + 0.2,
					base[3] + r[3][1] * len / 2,
				}, r)
			end
			return
		end
		if style == "jungle" then
			-- a jungle giant: a tall straight trunk on buttress roots, a wide flat crown of clusters, vines hanging
			local rt = H * 0.035
			between(
				path,
				{ name = "Trunk", mat = spec.trunk },
				{ base[1], base[2] - 1, base[3] },
				{ base[1], base[2] + H * 0.8, base[3] },
				rt
			)
			for k = 1, 4 do -- buttresses: thin slabs flaring out at the foot
				local a = k / 4 * 360 + rnd() * 30
				local r = World.rotation({ 0, a, 0 })
				local L = H * 0.12
				add(path, { name = "Buttress", mat = spec.trunk, shape = "Wedge" }, { 0.6, H * 0.14, L }, {
					base[1] + r[1][3] * (rt + L / 2),
					base[2] + H * 0.07 - 0.5,
					base[3] + r[3][3] * (rt + L / 2),
				}, World.rotation({ 0, a + 180, 0 }))
			end
			local top = base[2] + H * 0.74
			local cr = H * 0.2
			local tips = {}
			for k = 1, 9 do
				local a = rnd() * math.pi * 2
				local d = if k == 1 then 0 else cr * (0.9 + rnd() * 0.9)
				local p = { base[1] + math.cos(a) * d, top + (rnd() - 0.3) * cr * 0.5, base[3] + math.sin(a) * d }
				local rr = cr * (0.7 + rnd() * 0.5)
				add(
					path,
					{ name = "Canopy", mat = spec.leaves, shape = "Ball", collide = false },
					{ rr * 2, rr * 2, rr * 2 },
					p
				)
				table.insert(tips, p)
			end
			for _ = 1, 3 do -- vines from the crown
				local t = tips[1 + math.floor(rnd() * #tips)]
				local len = H * (0.3 + rnd() * 0.35)
				local vx, vz = t[1] + (rnd() - 0.5) * cr, t[3] + (rnd() - 0.5) * cr
				add(
					path,
					{ name = "Vine", mat = spec.vine or spec.leaves, shape = "Cylinder", collide = false },
					{ len, 0.35, 0.35 },
					{
						vx,
						t[2] - cr * 0.4 - len / 2,
						vz,
					},
					World.rotation({ 0, 0, 90 })
				)
			end
			return
		end
		if style == "palm" then
			-- a palm: a trunk of 5 segments bending one way, a crown of 8 long fronds drooping outward
			local bendYaw = rnd() * math.pi * 2
			local bend = 0.1 + rnd() * 0.12
			local p = { base[1], base[2] - 1, base[3] }
			for k = 1, 5 do
				local t = k / 5
				local q = {
					base[1] + math.cos(bendYaw) * bend * H * t * t,
					base[2] + H * t,
					base[3] + math.sin(bendYaw) * bend * H * t * t,
				}
				between(path, { name = "Trunk", mat = spec.trunk }, p, q, H * (0.032 - 0.01 * t))
				p = q
			end
			for k = 1, 8 do
				local a = k / 8 * 360 + rnd() * 20
				local len = H * (0.42 + rnd() * 0.12)
				local droop = 22 + rnd() * 18
				local r = World.rotation({ 0, a, -droop })
				add(path, { name = "Frond", mat = spec.leaves, collide = false }, { len, 0.35, H * 0.07 }, {
					p[1] + r[1][1] * len / 2,
					p[2] + r[2][1] * len / 2,
					p[3] + r[3][1] * len / 2,
				}, r)
			end
			return
		end
		if style == "pine" then
			-- a conifer: a straight tapering trunk and 3-5 stacked tiers, each two short crossed prisms (a cone
			-- from any side), narrowing to the tip; "snow": mat lays a white cap on every tier
			local lean = { (rnd() - 0.5) * 0.06 * H, (rnd() - 0.5) * 0.06 * H }
			local top = { base[1] + lean[1], base[2] + H * 0.95, base[3] + lean[2] }
			between(path, { name = "Trunk", mat = spec.trunk }, { base[1], base[2] - 1, base[3] }, top, H * 0.03)
			local tiers = 3 + math.floor(rnd() * 3)
			for t = 1, tiers do
				local f = (t - 1) / tiers
				local w = H * (0.46 - 0.34 * f) * (0.9 + rnd() * 0.2)
				local th = H * (0.34 - 0.08 * f)
				local by = base[2] + H * (0.16 + 0.68 * f)
				local cx, cz = base[1] + lean[1] * (by - base[2]) / H, base[3] + lean[2] * (by - base[2]) / H
				local yaw = rnd() * 90
				for _, turn in { 0, 90 } do
					prism(
						path,
						{ name = "Needles", mat = spec.leaves, collide = false },
						cx,
						by,
						cz,
						w * 0.42,
						th,
						w,
						yaw + turn
					)
					if spec.snow and t >= tiers - 1 then -- snow on the top tiers (parts are a budget)
						prism(
							path,
							{ name = "Snow", mat = spec.snow, collide = false },
							cx,
							by + th * 0.62,
							cz,
							w * 0.18,
							th * 0.4,
							w * 0.42,
							yaw + turn
						)
					end
				end
			end
			return
		end
		local r0 = spec.radius or H * (if style == "erd" then 0.07 else 0.045)
		local giant = style == "erd"
		local tspec = { name = "Trunk", mat = spec.trunk, collide = not giant, backdrop = giant or nil }
		local strands = if giant then 7 else 1
		local tips = {}
		local jspec = { name = "Knot", mat = spec.trunk, shape = "Ball", collide = false, backdrop = giant or nil }
		if giant then -- flared roots, so it stands on the land instead of on stilts
			for k = 1, 8 do
				local a = (k / 8) * math.pi * 2 + rnd() * 0.4
				local from = { base[1] + math.cos(a) * r0 * 0.5, base[2] + H * 0.07, base[3] + math.sin(a) * r0 * 0.5 }
				local to = { base[1] + math.cos(a) * r0 * 2.8, base[2] - H * 0.02, base[3] + math.sin(a) * r0 * 2.8 }
				between(
					path,
					{ name = "Root", mat = spec.trunk, collide = false, backdrop = true },
					from,
					to,
					r0 * 0.32
				)
			end
		end
		for sIdx = 1, strands do
			local ang = (sIdx / strands) * math.pi * 2
			local off = if giant then r0 * 0.9 else 0
			local p = { base[1] + math.cos(ang) * off, base[2], base[3] + math.sin(ang) * off }
			local segs = if giant then 9 else 5
			local lean = { (rnd() - 0.5) * 0.25, (rnd() - 0.5) * 0.25 }
			for k = 1, segs do
				local t = k / segs
				local twist = if giant then ang + t * 1.6 else 0
				local q = {
					base[1] + math.cos(twist) * off * (1 - 0.5 * t) + lean[1] * H * t + (rnd() - 0.5) * H * 0.03,
					base[2] + H * 0.62 * t,
					base[3] + math.sin(twist) * off * (1 - 0.5 * t) + lean[2] * H * t + (rnd() - 0.5) * H * 0.03,
				}
				local rr = r0 * (1 - 0.5 * t) * (if giant then 0.55 else 1)
				between(path, tspec, p, q, rr)
				if k < segs and (giant or style == "golden") then -- a knot hides the seam at a bend (big trunks only: parts are a budget)
					add(path, jspec, { rr * 2, rr * 2, rr * 2 }, q)
				end
				p = q
			end
			table.insert(tips, p)
		end
		local top = tips[1]
		local nBranch = spec.branches or (if giant then 14 elseif style == "dead" then 6 else 5)
		local bspec = { name = "Branch", mat = spec.trunk, collide = false, backdrop = giant or nil }
		local ends = {}
		for b = 1, nBranch do
			local from = tips[(b - 1) % #tips + 1]
			local start = {
				from[1],
				base[2] + H * (0.42 + 0.2 * rnd()),
				from[3],
			}
			if b <= #tips then
				start = from
			end
			local yaw = (b / nBranch) * math.pi * 2 + rnd() * 0.6
			local up = if giant
				then 0.25 + rnd() * 0.25
				elseif style == "dead" then 0.5 + rnd() * 0.4
				else 0.55 + rnd() * 0.35
			local len = H * (if giant then 0.42 else 0.32) * (0.7 + rnd() * 0.5) * (spec.spread or 1)
			local dir = { math.cos(yaw), up, math.sin(yaw) }
			local dl = math.sqrt(dir[1] ^ 2 + dir[2] ^ 2 + dir[3] ^ 2)
			local e = {
				start[1] + dir[1] / dl * len,
				start[2] + dir[2] / dl * len,
				start[3] + dir[3] / dl * len,
			}
			between(path, bspec, start, e, r0 * 0.38 * (if giant then 0.6 else 1))
			if style == "dead" or giant then -- a crooked second fork
				local yaw2 = yaw + (rnd() - 0.5) * 1.6
				local e2 = {
					e[1] + math.cos(yaw2) * len * 0.45,
					e[2] + len * (0.15 + rnd() * 0.25),
					e[3] + math.sin(yaw2) * len * 0.45,
				}
				between(path, bspec, e, e2, r0 * 0.22 * (if giant then 0.6 else 1))
				table.insert(ends, e2)
			end
			table.insert(ends, e)
		end
		if style ~= "dead" then
			local glow = style == "golden" or giant
			local cr = H * (if giant then 0.1 else 0.16)
			local lspec = {
				name = "Canopy",
				mat = spec.leaves,
				shape = "Ball",
				collide = false,
				backdrop = giant or nil,
				transparency = if glow then 0.12 else nil,
			}
			local lit = false
			for idx, e in ends do
				local n = if giant then 6 else 2
				for _ = 1, n do
					local rr = cr * (0.6 + rnd() * 0.7)
					local spread = if giant then 2.6 else 1 -- the Erdtree's crown: wide and flat, a cloud of clusters
					local c = {
						e[1] + (rnd() - 0.5) * cr * spread,
						e[2] + (rnd() - 0.2) * cr * 0.6,
						e[3] + (rnd() - 0.5) * cr * spread,
					}
					local s = table.clone(lspec)
					if glow and not lit and idx == 1 then
						s.light = { color = { 255, 205, 110 }, range = 60, brightness = if giant then 6 else 3 }
						s.particles = "golden_leaves"
						lit = true
					end
					add(path, s, { rr * 2, rr * 2, rr * 2 }, c)
				end
			end
			-- crown over the top so the silhouette is a dome, not a bouquet
			local crown = table.clone(lspec)
			add(path, crown, { cr * 3, cr * 2.2, cr * 3 }, { top[1], top[2] + cr * 0.9, top[3] })
		end
	end

	-- LANDMARKS (AAA gap W2: the world's "weenies", for kit world check's landmark guidance): a step marked
	-- "landmark": true, or one that obviously is (a tree >= 150 studs, a tower >= 60, a building of 3+ floors, a peak);
	-- its top is the highest point of the parts it built (after its lift onto the land)
	local landmarks: { any } = {}
	-- SCALE CLAIMS (kit world check's "scale" sheet): what each piece says it is (a door w x h, a stair's rise x run,
	-- a rail, a room's clear height, an alley / street / run wall / push-up wall / roof gap), measured against the
	-- rig's sheet; a piece out of scale FAILS the check. Stairs claim themselves; "fit": "<kind>" on a part; the
	-- "fit" op claims what has no part of its own (a mesh building's door, a street between rows)
	local fits: { any } = {}
	-- TURN (2026-11-13; the owner's method list: procedural buildings, modular construction, splines - "the building
	-- generator on any angle"): "turn": <degrees> on a step turns EVERYTHING the step made - its parts (walls, slabs,
	-- stairs, furniture, panes, its mesh skin) and its scale claims - about a vertical line through its anchor
	-- ("about": [x, z]; else its center / pos; a wall's middle). The generators stay axis-aligned inside and are
	-- turned once they are done, so a turned house is the same house: same rooms, same door, same claims.
	local turning: any = nil
	local function finishTurn()
		local t = turning
		if not t then
			return
		end
		turning = nil
		local m = World.turnMatrix(t.deg)
		for _, p in t.parts do
			local x, z = World.turnPoint(p.pos[1], p.pos[3], t.x, t.z, t.deg)
			p.pos = { x, p.pos[2], z } -- (a new table: a part's pos can be the blueprint's own)
			p.rot = mul(m, p.rot)
			p.axisAligned = isIdentity(p.rot)
		end
		for i = t.firstFit, #fits do
			local f = fits[i]
			if type(f.pos) == "table" then
				local x, z = World.turnPoint(f.pos[1], f.pos[3], t.x, t.z, t.deg)
				f.pos = { x, f.pos[2], z }
			end
			for _, key in { "from", "to" } do
				local v = f[key]
				if type(v) == "table" and #v == 2 then
					local x, z = World.turnPoint(v[1], v[2], t.x, t.z, t.deg)
					f[key] = { x, z }
				elseif type(v) == "table" and #v == 3 then
					local x, z = World.turnPoint(v[1], v[3], t.x, t.z, t.deg)
					f[key] = { x, v[2], z }
				end
			end
			f.yaw = (f.yaw or 0) + t.deg -- (kit world check measures a turned claim in its own frame)
		end
	end
	-- PREFABS (kit/lib/worldprefab.luau): a step that stands in a placed prefab was built where it is typed (round
	-- the prefab's origin); what it made is moved here, after its own turn: shifted to the placement's "at" and
	-- turned about it, then again by each prefab that one stands in
	local placing: any = nil
	local function finishPlace()
		local t = placing
		if not t then
			return
		end
		placing = nil
		for _, move in t.moves do
			local m = World.turnMatrix(move.deg)
			for _, p in t.parts do
				local x, z = World.turnPoint(p.pos[1] + move.dx, p.pos[3] + move.dz, move.x, move.z, move.deg)
				p.pos = { x, p.pos[2] + move.dy, z }
				if move.deg % 360 ~= 0 then
					p.rot = mul(m, p.rot)
					p.axisAligned = isIdentity(p.rot)
				end
			end
			for i = t.firstFit, #fits do
				local f = fits[i]
				if type(f.pos) == "table" then
					local x, z = World.turnPoint(f.pos[1] + move.dx, f.pos[3] + move.dz, move.x, move.z, move.deg)
					f.pos = { x, f.pos[2] + move.dy, z }
				end
				for _, key in { "from", "to" } do
					local v = f[key]
					if type(v) == "table" and #v == 2 then
						local x, z = World.turnPoint(v[1] + move.dx, v[2] + move.dz, move.x, move.z, move.deg)
						f[key] = { x, z }
					elseif type(v) == "table" and #v == 3 then
						local x, z = World.turnPoint(v[1] + move.dx, v[3] + move.dz, move.x, move.z, move.deg)
						f[key] = { x, v[2] + move.dy, z }
					end
				end
				-- (a claim's own ground heights - a sloped lane's two ends - are lifted with it)
				if type(f.ground) == "table" then
					local lifted = {}
					for k, v in f.ground do
						lifted[k] = if type(v) == "number" then v + move.dy else v
					end
					f.ground = lifted
				elseif type(f.ground) == "number" then
					f.ground += move.dy
				end
				f.yaw = (f.yaw or 0) + move.deg
			end
		end
	end
	local pending: any = nil
	local function finishLandmark()
		if not pending then
			return
		end
		local best: any = nil
		for _, p in current do
			local ey = math.abs(p.rot[2][1]) * p.size[1] / 2
				+ math.abs(p.rot[2][2]) * p.size[2] / 2
				+ math.abs(p.rot[2][3]) * p.size[3] / 2
			local top = p.pos[2] + ey
			if not best or top > best[2] then
				best = { p.pos[1], top, p.pos[3] }
			end
		end
		if best then
			table.insert(landmarks, { name = pending, top = best })
		end
		pending = nil
	end
	-- MACRO generators: a "town" step is a PLAN (kit/lib/worldtown.luau: streets as a graph round a closed square,
	-- blocks, terraced lots); it is expanded HERE into the steps it stands for (floor, building, wall, fit), each
	-- keeping the town step's own path in its messages. The plan's record rides out in the extras (kit world town)
	local expanded: { any }, stepPaths: { string } = {}, {}
	local stepPlaces: { [number]: any } = {} -- (a step of a placed prefab: its moves and its placement's name)
	local prefabsPlaced: { any } = {} -- (each placement: its prefab, its name, how many steps it came to)
	local prefabsOk = bp.prefabs == nil
	if bp.prefabs ~= nil then
		local wrong = Prefab.problems(bp.prefabs, World.IN_PREFAB)
		for _, p in wrong do
			err("prefabs", p)
		end
		prefabsOk = #wrong == 0
	end
	local trailsGrown: { any } = {} -- (each trails step: its runs, its length, how far its walkers walked)
	local fogLaid: { any } = {} -- (each fog step: its sheets and cells, handed back in the extras)
	local placedCount: { [string]: number } = {}
	local placedNames: { [string]: boolean } = {}
	local towns: { any } = {}
	local routes: { any } = {} -- (each routed road: its points and measures, handed back in the extras)
	local ecosystems: { any } = {} -- (each grown forest: how many of each kind stand, its census, its dead)
	local decalsLaid: { any } = {} -- (each decal step: how many it lays, how many are in the game, which wait)
	local decalsWaiting: { [string]: boolean } = {} -- (decals made and not uploaded: said once each)
	local decalsAt: { [string]: boolean } = {} -- (where a decal lies already: two on one spot flicker)
	local tileLayouts: { any } = {} -- (each place laid out of tiles: how many of each tile, how often it was begun)
	local onMeshes: { any } = {} -- (each mesh with things set down on its surface: how many points, how many placed)
	-- THE POINTS ON A MESH'S SURFACE (kit world scatter-on <mesh> --as <name>: Geometry Nodes in Blender,
	-- kit/world/gnscatter_blender.py -> build/worldmeshes/<mesh>.on.<name>.json); opts.scatters["<mesh>.<name>"]
	-- in its place (the kit's own specs: no Blender run)
	local function pointsOn(mesh: string, name: string): any?
		if type(opts) == "table" and type(opts.scatters) == "table" then
			return opts.scatters[`{mesh}.{name}`]
		end
		local file = `{Config.build("worldmeshes")}/{mesh}.on.{name}.json`
		if fs.isFile(file) then
			local ok, data = pcall(serde.decode, "json" :: any, fs.readFile(file))
			if ok and type(data) == "table" then
				return data
			end
		end
		return nil
	end
	local dungeons: { any } = {} -- (each dungeon: its rooms' places and its measures, handed back in the extras)
	local caves: { any } = {} -- (each cave: its start, its farthest place and its measures)
	for i, step in bp.build do
		local kind, spec = next(step)
		if kind == "town" and type(spec) == "table" then
			local here = `build[{i}].town`
			local plan = Town.plan(spec)
			for _, issue in plan.issues do
				if issue.severity == "error" then
					err(here, issue.message)
				else
					warn(here, issue.message)
				end
			end
			if spec.ground == true then
				warn(here, 'a town stands on level ground in this version ("ground": true is not followed)')
			end
			if spec.turn ~= nil or spec.about ~= nil then
				err(
					here .. ".turn",
					'a town is not turned by "turn": its streets bend by its own "bend": <degrees>, its place is its "center"'
				)
			end
			if spec.stream ~= nil then
				err(
					here .. ".stream",
					'a town is not kept loaded as a whole: say it of its landmark house - "landmark": { "stream": "always" } (or "area")'
				)
			end
			for _, made in Town.steps(plan, spec) do
				local _, madeSpec = next(made)
				-- (the town's landmark house carries the town's own word for it: "landmark": { "stream": ... })
				if madeSpec.landmark == true and type(spec.landmark) == "table" and spec.landmark.stream ~= nil then
					madeSpec.stream = spec.landmark.stream
				end
				table.insert(expanded, made)
				table.insert(stepPaths, `{here}.{madeSpec.name or "?"}`)
			end
			if #plan.lots > 0 then
				table.insert(towns, Town.record(spec.name or "Town", plan))
			end
		elseif kind == "trails" then
			-- TRAILS WORN BY WALKERS (kit/lib/worldtrails.luau): walkers go between the places, each the easiest way,
			-- trodden ground easier still; the web they wear is handed on as "path" steps, one a run
			local here = `build[{i}].trails`
			local wrong = Trails.problems(spec)
			for _, p in wrong do
				err(here, p)
			end
			if #wrong == 0 and (type(spec.mat) ~= "string" or palette[spec.mat] == nil) then
				err(here, 'trails: "mat" is the palette entry the trails are made of')
				wrong = { "mat" }
			end
			if #wrong == 0 then
				local onLand = #groundOps > 0
				-- (water is kept off by half the widest trail and 2 studs, as a routed road keeps off it)
				local off = (spec.width or 4) / 2 + 2
				if spec.parts == false and not onLand then
					err(
						here,
						'trails: "parts": false leaves only the trail worn into the land, and this world has no land'
					)
				elseif spec.parts == false and spec.worn == nil then
					err(
						here,
						'trails: "parts": false with no "worn" would make nothing: say the terrain material the trails wear ("worn": "Ground")'
					)
				end
				local grown, why = Trails.grow(spec, function(x: number, z: number): number?
					if not onLand then
						return 0
					end
					return groundAt(x, z)
				end, function(x: number, z: number): boolean
					for _, wop in waterOps do
						if
							math.abs(x - wop.center[1]) <= wop.size[1] / 2 + off
							and math.abs(z - wop.center[3]) <= wop.size[3] / 2 + off
							and (groundAt(x, z) or math.huge) < wop.center[2] + wop.size[2] / 2
						then
							return true
						end
					end
					return roleAt(x, z) == "river"
				end)
				if not grown then
					err(here, `trails: {why}`)
				else
					if #grown.lost > 0 then
						warn(
							here,
							`{#grown.lost} of {spec.walkers} walks found no way within a grade of {spec.grade} (the first: from place {grown.lost[1][1]} to place {grown.lost[1][2]}): those places may be joined by no trail`
						)
					end
					local name = spec.name or "Trails"
					local width = spec.width or 4
					for r, run in grown.runs do
						-- (the most trodden run is as wide as said; the least, half of it)
						local w = math.max(2, math.floor(width * (0.5 + 0.5 * run.feet / grown.most) * 2 + 0.5) / 2)
						table.insert(expanded, {
							path = {
								name = `{name}_{r}`,
								points = run.points,
								width = w,
								mat = spec.mat,
								worn = spec.worn,
								wornWidth = spec.wornWidth,
								thickness = spec.thickness,
								-- (on level ground two runs that meet at a fork do not lie in one plane: each a hair higher
								-- than the last; on land every run lies on the land)
								y = if onLand then nil else ((r - 1) % 7) * 0.07,
								parts = spec.parts,
								ground = if onLand then true else nil,
								route = if onLand then false else nil, -- (walked, not typed: the lock's word)
								curve = if spec.curve == nil then true else spec.curve,
								stream = spec.stream,
							},
						})
						table.insert(stepPaths, `{here}.{name}_{r}`)
					end
					table.insert(trailsGrown, {
						name = name,
						runs = #grown.runs,
						length = grown.length,
						walked = grown.walked,
						most = grown.most,
						walks = grown.walks,
						lost = #grown.lost,
					})
				end
			end
		elseif kind == "prefab" then
			local here = `build[{i}].prefab`
			if bp.prefabs == nil then
				err(here, 'a "prefab" step sets down a prefab of this blueprint\'s "prefabs", and it has none')
			elseif prefabsOk then
				local wrong = Prefab.placement(spec, bp.prefabs)
				for _, p in wrong do
					err(here, p)
				end
				if #wrong == 0 then
					placedCount[spec.name] = (placedCount[spec.name] or 0) + 1
					local as = spec.as or `{spec.name}_{placedCount[spec.name]}`
					if placedNames[as] then
						err(here, `two placements are called "{as}": say "as" on one of them`)
					end
					placedNames[as] = true
					local steps, why = Prefab.expand(spec, bp.prefabs, here, as)
					if not steps then
						err(here, why or "the prefab could not be set down")
					elseif #expanded + #steps > Prefab.MOST * 2 then
						err(here, `the blueprint's prefabs come to more than {Prefab.MOST * 2} steps in all`)
					else
						for _, made in steps do
							table.insert(expanded, made.step)
							table.insert(stepPaths, made.path)
							stepPlaces[#expanded] = made
						end
						table.insert(
							prefabsPlaced,
							{ prefab = spec.name, name = as, steps = #steps, at = spec.at, turn = spec.turn or 0 }
						)
					end
				end
			end
		else
			table.insert(expanded, step)
			table.insert(stepPaths, `build[{i}]`)
		end
	end
	-- JUNCTIONS (LIMITATIONS_FIXES_V4 5.1, E8 - kit/lib/worldjunction.luau): where "ground": true roads meet - a lane's
	-- end on another road (a T), ends at one spot (a Y) - a pad in the land's plane and every road cut at its rim,
	-- its roll eased into the pad's. Found on the roads' lines as laid (curved, never routed, turned or placed);
	-- "junction": false keeps a road out; the worlds laid before (World.ROAD_V3_BEFORE) say "junction": true to join
	local junctionsOf: { [number]: { Junction.Node } } = {}
	local junctionPlanes: { [Junction.Node]: { number } | false } = {}
	local junctionLaid: { [Junction.Node]: boolean } = {}
	do
		local before = World.ROAD_V3_BEFORE[tostring(bp.name)] == true
		local roads: { Junction.Road } = {}
		for i, step in expanded do
			local kind, spec = next(step)
			if
				kind == "path"
				and type(spec) == "table"
				and spec.ground == true
				and spec.parts ~= false
				and spec.route == nil
				and spec.turn == nil
				and stepPlaces[i] == nil
				and (if spec.junction == nil then not before else spec.junction == true)
				and type(spec.points) == "table"
				and #spec.points >= 2
			then
				local ok = true
				for _, pt in spec.points do
					if type(pt) ~= "table" or type(pt[1]) ~= "number" or type(pt[2]) ~= "number" then
						ok = false
					end
				end
				if ok then
					local pts = spec.points
					if
						spec.curve ~= nil
						and spec.curve ~= false
						and (spec.curve == true or type(spec.curve) == "table")
					then
						pts = Curve.through(pts, if type(spec.curve) == "table" then spec.curve else {})
					end
					table.insert(roads, { id = i, points = pts, width = spec.width or 8 })
				end
			end
		end
		if #roads > 1 then
			local _, byRoad = Junction.find(roads)
			junctionsOf = byRoad
		end
	end
	for i, step in expanded do
		local path = stepPaths[i]
		local kind, spec = next(step)
		if type(spec) ~= "table" then
			err(path, 'each step is { "<generator>": { ... } }')
			continue
		end
		if spec.density ~= nil and kind ~= "scatter" and kind ~= "forest" then
			-- (rocks or cover with a "density" were built by their count and the word dropped unsaid)
			err(
				path .. ".density",
				`"density" is a scatter's and a forest's word: a {kind} step places by its own count`
			)
			continue
		end
		finishTurn() -- (the step before this one)
		finishPlace()
		stepTurn = nil
		dressKey = nil
		finishLandmark()
		current = {}
		stepPlaced = stepPlaces[i] ~= nil
		if stepPlaced then
			placing = { moves = stepPlaces[i].moves, parts = current, firstFit = #fits + 1 }
		end
		-- ROUTE (the owner's method list: procedural road networks - a road across open land): "route": { "from",
		-- "to", "via"?, "grade", "cell"?, "reach"? } on a path that lies on the land ("ground": true) in place of
		-- typed "points": the road finds its own way over the compiled ground, never steeper than its grade, round
		-- the water and what the step keeps off ("avoid"). kit/lib/worldroute.luau. "route": false = typed by hand,
		-- meant (the build's lock asks a long road across the land to say which). A "curve" then rounds its corners.
		local routedRoad: any = nil
		if spec.route ~= nil and spec.route ~= false then
			local wrong = Route.problems(spec.route)
			for _, p in wrong do
				err(path .. ".route", p)
			end
			local routed = false
			local keepOff = true
			if spec.avoid ~= nil then
				-- (a circle typed wrongly is an error, never a crash of the whole build)
				if type(spec.avoid) ~= "table" then
					keepOff = false
				else
					for _, a in spec.avoid do
						if
							type(a) ~= "table"
							or type(a[1]) ~= "number"
							or type(a[2]) ~= "number"
							or type(a[3]) ~= "number"
						then
							keepOff = false
						end
					end
				end
			end
			if kind ~= "path" or spec.ground ~= true then
				err(path .. ".route", 'a "route" is for a path on the land: a "path" step with "ground": true')
			elseif not keepOff then
				err(path .. ".avoid", '"avoid" is a list of circles the road keeps off: [[x, z, radius], ...]')
			elseif type(spec.curve) ~= "boolean" and type(spec.curve) ~= "table" then
				-- (the build's lock asks a road of typed points whether its corners are rounded; a routed road has
				-- no typed points for it to read, so the word is asked here)
				err(
					path .. ".curve",
					'a routed road says "curve": true (its corners rounded) or "curve": false (the straight runs it found)'
				)
			elseif spec.points ~= nil then
				err(path .. ".points", 'a path with a "route" has no "points": the road finds them')
			elseif #groundOps == 0 then
				err(path .. ".route", "a route needs land to cross: the world has no ground or heightmap")
			elseif #wrong == 0 then
				local half = (spec.width or 8) / 2
				local found, why = Route.find(groundAt, spec.route, function(x: number, z: number): boolean
					for _, wop in waterOps do
						-- (water's box, where its surface lies over the land: the road keeps half its width off it)
						if
							math.abs(x - wop.center[1]) <= wop.size[1] / 2 + half
							and math.abs(z - wop.center[3]) <= wop.size[3] / 2 + half
							and (groundAt(x, z) or math.huge) < wop.center[2] + wop.size[2] / 2
						then
							return true
						end
					end
					-- (a river the terrain painter laid is water too: the road goes round it or finds no way -
					-- the kit builds no bridge by itself)
					if roleAt(x, z) == "river" then
						return true
					end
					for _, a in spec.avoid or {} do
						if (x - a[1]) ^ 2 + (z - a[2]) ^ 2 < (a[3] + half) ^ 2 then
							return true
						end
					end
					return false
				end)
				if found then
					spec = table.clone(spec) -- (never the blueprint's own table)
					local pts = {}
					for _, p in found.points do
						table.insert(pts, { p[1], p[3] })
					end
					spec.points = pts
					routed = true
					routedRoad = {
						name = spec.name or path,
						points = pts,
						length = found.length,
						climb = found.climb,
						fall = found.fall,
						steepest = found.steepest,
						grade = spec.route.grade,
					}
					table.insert(routes, routedRoad)
				else
					err(path .. ".route", why :: string)
				end
			end
			if not routed then
				continue -- (said above: nothing is built of a road that found no way)
			end
		end
		-- CURVE (2026-11-13; the owner's method list: spline-based roads, paths, fences and walls): "curve": true on a
		-- step that walks typed "points" makes the line through them smooth - the step is handed the curve's own
		-- points, many where two were typed ("curve": { "step": 12, "maxTurn": 6, "closed": true } to tune it or to
		-- close a ring). "curve": false says a hard corner is meant (the build's lock asks a new world to say which).
		local curved = false
		if World.CURVED[kind] and type(spec.points) == "table" then
			-- (a point typed wrongly is an error here: the generators below do arithmetic on what they are given)
			local ok = true
			for _, pt in spec.points do
				if type(pt) ~= "table" or type(pt[1]) ~= "number" or type(pt[2]) ~= "number" then
					ok = false
				end
			end
			if not ok then
				err(path .. ".points", "every point is [x, z]")
				continue
			end
		end
		if spec.curve ~= nil and spec.curve ~= false then
			if spec.curve ~= true and type(spec.curve) ~= "table" then
				err(path .. ".curve", '"curve" is true, false or { "step", "maxTurn", "closed" }')
			elseif not World.CURVED[kind] then
				err(
					path .. ".curve",
					`a "{kind}" step walks no line of points: "curve" is for path, row, palisade and a wall with "points"`
				)
			elseif type(spec.points) ~= "table" then
				err(path .. ".curve", '"curve" needs "points": [[x, z], ...] to pass through')
			else
				spec = table.clone(spec) -- (never the blueprint's own table)
				spec.points = Curve.through(spec.points, if type(spec.curve) == "table" then spec.curve else {})
				curved = true
			end
		end
		if routedRoad then
			-- the road as it is LAID (its corners rounded, if it says so), measured on the land every half stud:
			-- what it hands back is this, and a road steeper than it was asked to be says so
			local length, climb, fall, steepest = Route.measure(groundAt, spec.points)
			routedRoad.points = spec.points
			routedRoad.length, routedRoad.climb, routedRoad.fall, routedRoad.steepest = length, climb, fall, steepest
			if
				steepest > routedRoad.grade * 1.25
				and not (spec.ground == true and spec.bed ~= nil and spec.bed ~= false)
			then
				warn(
					path .. ".route",
					`this road is laid steeper than its grade: {math.floor(steepest * 100 + 0.5) / 100} at its steepest, {routedRoad.grade} asked for{if curved
						then ' (rounding its corners moved it off the way it found: say "curve": false, or a gentler grade)'
						else ' (the land is rougher than the road can read: say a smaller "cell", or a gentler grade)'}`
				)
			end
		end
		if spec.turn ~= nil then
			local about = spec.about
			local anchor = spec.center or spec.pos
			local ax: number?, az: number? = nil, nil
			if about ~= nil then -- (a point typed wrongly is an error, never quietly the step's own centre)
				-- (exactly two numbers: every other point of a blueprint is [x, y, z], and [0, 5, 0] read as x 0, z 5
				-- would turn the step round the wrong place without a word)
				if
					type(about) == "table"
					and #about == 2
					and type(about[1]) == "number"
					and type(about[2]) == "number"
				then
					ax, az = about[1], about[2]
				end
			elseif type(anchor) == "table" and type(anchor[1]) == "number" and type(anchor[3]) == "number" then
				ax, az = anchor[1], anchor[3]
			elseif
				type(spec.from) == "table"
				and type(spec.to) == "table"
				and type(spec.from[1]) == "number"
				and type(spec.from[2]) == "number"
				and type(spec.to[1]) == "number"
				and type(spec.to[2]) == "number"
			then
				ax, az = (spec.from[1] + spec.to[1]) / 2, (spec.from[2] + spec.to[2]) / 2
			end
			if type(spec.turn) ~= "number" or spec.turn ~= spec.turn or math.abs(spec.turn) == math.huge then
				err(path .. ".turn", `"turn" is a number of degrees (got {tostring(spec.turn)})`)
			elseif not World.TURNABLE[kind] then
				err(
					path .. ".turn",
					`a "{kind}" step is not turned by "turn": type it where and how it stands (turned are: part, fit, wall, floor, stairs, ring, grid, room, breakable, building, mesh, ruin, tower, bridge, arch, city, crosswalk, ziggurat)`
				)
			elseif spec.ground == true then
				err(
					path .. ".turn",
					'"turn" and "ground": true together are not followed yet: a turned step stands at its typed height'
				)
			elseif about ~= nil and ax == nil then
				err(path .. ".about", '"about" is the point a step turns round: [x, z] (two numbers, no height)')
			elseif ax == nil or az == nil then
				err(path .. ".turn", '"turn" needs a point to turn round: the step\'s center / pos, or "about": [x, z]')
			elseif spec.turn % 360 ~= 0 then
				turning = { deg = spec.turn, x = ax, z = az, parts = current, firstFit = #fits + 1 }
				stepTurn = turning
			end
		end
		if
			spec.landmark == true
			or (
				spec.landmark ~= false
				and (
					(kind == "tree" and (spec.height or 0) >= 150)
					or (kind == "tower" and (spec.height or 0) >= 60)
					or (kind == "building" and (spec.floors or 0) >= 3)
					or kind == "peak"
				)
			)
		then
			pending = spec.name or kind
		end
		stepGround = nil
		local perItem = kind == "scatter"
			or kind == "cover"
			or kind == "path"
			or kind == "rocks"
			or kind == "cliffs"
			or kind == "story"
			or kind == "palisade"
			or kind == "city"
			or kind == "crosswalk"
			or kind == "row"
		if spec.ground == true and not perItem then
			-- one lift for the whole structure (a building stays level), taken at its anchor
			local a = spec.center or spec.pos or spec.start
			local ax, az
			if type(a) == "table" and #a >= 3 then
				ax, az = a[1], a[3]
			elseif type(spec.from) == "table" then
				ax, az = spec.from[1], spec.from[2]
			end
			local h = if ax then groundAt(ax, az) else nil
			if h == nil then
				err(
					path .. ".ground",
					'"ground": true but no terrain ground under this step (add a ground / heightmap op)'
				)
			else
				local structural = kind ~= "tree" and kind ~= "grace"
				stepGround = { dy = h, sink = spec.sink or (if structural then 4 else 0) }
			end
		end
		if kind == "part" then
			add(path, spec, spec.size or {}, spec.pos or { 0, 0, 0 })
			if type(spec.fit) == "string" then
				table.insert(fits, { kind = spec.fit, name = spec.name, size = spec.size, pos = spec.pos, path = path })
			end
		elseif kind == "wall" then
			if spec.points ~= nil then
				-- a wall ALONG points (a town wall, a churchyard's, a fence): one straight piece a pair of points, same
				-- height / thickness / mat; "gaps" are measured along the WHOLE line. How its pieces meet (a fresh
				-- reader, 2026-11-13, found slivers of wall standing in a gate and a notch at every hard corner):
				--   - a GENTLE joint (up to WALL_CORNER degrees: a curve's): each piece runs past the joint by what the
				--     joint's own angle opens at the wall's outer face, so no slit shows;
				--   - a HARD corner: the pieces end on the joint and a corner post stands on it (a hair proud of both,
				--     so no two faces share a plane), unless a gate is cut there;
				--   - a gate that crosses a joint is cut out of both pieces to their very ends: nothing is left in it.
				local pts = if type(spec.points) == "table" then Curve.distinct(spec.points) else {}
				if type(spec.points) ~= "table" or #spec.points < 2 then
					err(path, 'a wall along "points" needs at least 2 points [[x, z], ...]')
					continue
				end
				if #pts < 2 then
					err(path, 'a wall along "points" needs two points that are apart')
					continue
				end
				if curved and (spec.crenels or spec.buttresses or spec.mesh) then
					-- (each short piece would start its own row of merlons, piers or modules)
					err(
						path .. ".curve",
						'a curved wall takes no "crenels", "buttresses" or "mesh" modules yet: leave them off, or type the wall with "curve": false'
					)
					continue
				end
				local t = if type(spec.thickness) == "number" then spec.thickness else 0
				local h = if type(spec.height) == "number" then spec.height else 0
				local gapList = {}
				for _, g in spec.gaps or {} do
					if type(g) == "table" and type(g.at) == "number" and type(g.width) == "number" then
						table.insert(gapList, g)
					end
				end
				local function inGap(at: number): boolean
					for _, g in gapList do
						if at > g.at - g.width / 2 - 1e-6 and at < g.at + g.width / 2 + 1e-6 then
							return true
						end
					end
					return false
				end
				-- the turn at each inner joint (degrees), and what a gentle one needs of each piece
				local turns = {}
				for k = 2, #pts - 1 do
					turns[k] = Curve.turn(pts[k - 1], pts[k], pts[k + 1])
				end
				local function lapAt(k: number): number -- (joint k is point k; the line's two ends are no joints)
					local d = turns[k]
					if not d or d > World.WALL_CORNER then
						return 0
					end
					return t / 2 * math.tan(math.rad(d) / 2) + 0.01
				end
				local walked = 0
				for k = 1, #pts - 1 do
					local a, b = pts[k], pts[k + 1]
					local dx, dz = b[1] - a[1], b[2] - a[2]
					local len = math.sqrt(dx * dx + dz * dz)
					local l0, l1 = lapAt(k), lapAt(k + 1)
					local piece = table.clone(spec)
					piece.points = nil
					piece.curve = nil
					piece.from = { a[1] - dx / len * l0, a[2] - dz / len * l0 }
					piece.to = { b[1] + dx / len * l1, b[2] + dz / len * l1 }
					local gaps = {}
					for _, g in gapList do
						local g0, g1 = g.at - g.width / 2, g.at + g.width / 2
						if math.min(g1, walked + len) - math.max(g0, walked) > 0.01 then
							-- (in the piece's own run, which starts l0 before the joint; a gate that goes on past a
							-- joint takes the piece's lap there with it)
							local from = if g0 <= walked + 1e-6 and k > 1 then 0 else math.max(g0 - walked, 0) + l0
							local to = if g1 >= walked + len - 1e-6 and k < #pts - 1
								then len + l0 + l1
								else math.min(g1 - walked, len) + l0
							table.insert(
								gaps,
								{ at = (from + to) / 2, width = to - from, height = g.height, sill = g.sill }
							)
						end
					end
					piece.gaps = gaps
					buildWall(`{path}.piece{k}`, piece)
					walked += len
					-- a hard corner's post (not on the line's last point, not where a gate is cut)
					local d = turns[k + 1]
					if d and d > World.WALL_CORNER and t > 0 and h > 0 and not inGap(walked) then
						add(
							path,
							{ name = "WallCorner", mat = spec.mat, transparency = if spec.hidden then 1 else nil },
							{ t + 0.04, h + 0.02, t + 0.04 },
							{ b[1], (spec.y or 0) + (h + 0.02) / 2, b[2] },
							World.rotation({ 0, math.deg(math.atan2(-dz, dx)), 0 })
						)
					end
				end
				for gi, g in gapList do
					if g.at - g.width / 2 < 0 or g.at + g.width / 2 > walked then
						err(
							`{path}.gaps[{gi}]`,
							`gap must lie inside the wall's {math.floor(walked * 10 + 0.5) / 10} studs of line`
						)
					end
				end
			else
				buildWall(path, spec)
			end
		elseif kind == "floor" then
			local c, s, th = spec.center, spec.size, spec.thickness or 1
			if spec.checker then
				local tile, other = spec.checker[1], spec.checker[2]
				local nx, nz = math.max(1, math.floor(s[1] / tile)), math.max(1, math.floor(s[2] / tile))
				for ix = 0, nx - 1 do
					for iz = 0, nz - 1 do
						local m = if (ix + iz) % 2 == 0 then spec.mat else other
						add(path, { name = "Tile", mat = m }, { s[1] / nx, th, s[2] / nz }, {
							c[1] - s[1] / 2 + (ix + 0.5) * s[1] / nx,
							c[2] - th / 2,
							c[3] - s[2] / 2 + (iz + 0.5) * s[2] / nz,
						})
					end
				end
			else
				add(path, { name = "Floor", mat = spec.mat }, { s[1], th, s[2] }, { c[1], c[2] - th / 2, c[3] })
			end
		elseif kind == "stairs" then
			local dirs = { ["+X"] = { 1, 0 }, ["-X"] = { -1, 0 }, ["+Z"] = { 0, 1 }, ["-Z"] = { 0, -1 } }
			local d = dirs[spec.dir]
			if not d then
				err(path .. ".dir", 'dir must be "+X" | "-X" | "+Z" | "-Z"')
				continue
			end
			local s0 = spec.start
			table.insert(fits, {
				kind = "step",
				name = spec.name,
				rise = spec.rise,
				run = spec.run,
				width = spec.width,
				pos = s0,
				path = path,
			})
			for k = 1, spec.steps do
				local h = spec.rise * k -- solid steps (no floating treads)
				local along = (k - 0.5) * spec.run
				local size = if d[1] ~= 0 then { spec.run, h, spec.width } else { spec.width, h, spec.run }
				add(
					path,
					{ name = "Step", mat = spec.mat },
					size,
					{ s0[1] + d[1] * along, s0[2] + h / 2, s0[3] + d[2] * along }
				)
			end
		elseif kind == "ring" then
			local c, n = spec.center, spec.segments or 16
			local gapCount = spec.gaps or 0
			if n < 3 then
				err(path .. ".segments", "a ring needs at least 3 segments")
				continue
			end
			if gapCount < 0 or gapCount >= n then
				err(
					path .. ".gaps",
					`gaps must be 0..{n - 1} (with {n} segments, {gapCount} gaps removes the whole ring)`
				)
				continue
			end
			-- spread the gaps evenly: gap k replaces segment floor(k * n / gaps)
			local isGap: { [number]: boolean } = {}
			for k = 0, gapCount - 1 do
				isGap[math.floor(k * n / gapCount)] = true
			end
			-- segment length that closes the OUTER corners (inner edge then overlaps slightly, which is hidden)
			local chord = 2 * (spec.radius + spec.thickness / 2) * math.sin(math.pi / n)
			for k = 0, n - 1 do
				if isGap[k] then
					continue
				end
				local a = (k + 0.5) * 2 * math.pi / n
				local yaw = -math.deg(a) - 90 -- local +X tangent to the circle (Ry maps X to (cos, 0, -sin))
				add(path, { name = "RingWall", mat = spec.mat }, { chord, spec.height, spec.thickness }, {
					c[1] + math.cos(a) * spec.radius,
					c[2] + spec.height / 2,
					c[3] + math.sin(a) * spec.radius,
				}, World.rotation({ 0, yaw, 0 }))
			end
		elseif kind == "grid" then
			local o, cnt, sp, pt = spec.origin, spec.count, spec.spacing, spec.part
			for ix = 0, cnt[1] - 1 do
				for iz = 0, cnt[2] - 1 do
					add(path, pt, pt.size, { o[1] + ix * sp[1], o[2] + pt.size[2] / 2, o[3] + iz * sp[2] })
				end
			end
		elseif kind == "scatter" then
			-- { center, area: [w, d], part: { size | [lo, hi], mat, ... }, meshes?, seed?, gap?, tilt?, embed? } and
			--   "count": N              N pieces thrown evenly over the area (30 tries each)
			--   or "density": { ... }   how full each place is and how close two pieces stand: the count comes out
			--                           of it (kit/lib/worldscatter.luau: a field + a true Poisson-disk sample)
			local c, area, pt = spec.center, spec.area, spec.part
			local dense = spec.density ~= nil and spec.density ~= false
			if dense then
				local wrong = Scatter.problems(spec.density)
				for _, p in wrong do
					err(path .. ".density", p)
				end
				if spec.count ~= nil then
					err(
						path .. ".count",
						'a scatter with a "density" has no "count": how many pieces there are comes out of the gap and the field'
					)
				end
				if #wrong > 0 or spec.count ~= nil then
					continue
				end
			elseif type(spec.count) ~= "number" or spec.count < 1 then
				err(path .. ".count", "scatter count must be ≥ 1")
				continue
			end
			local rnd = lcg(spec.seed or 1)
			local function sized(): { number }
				local size = pt.size
				if type(size[1]) == "table" then
					local lo, hi = size[1], size[2]
					size = {
						lo[1] + (hi[1] - lo[1]) * rnd(),
						lo[2] + (hi[2] - lo[2]) * rnd(),
						lo[3] + (hi[3] - lo[3]) * rnd(),
					}
				end
				return size
			end
			local function put(x: number, z: number, gy: number, size: { number })
				if spec.meshes then -- real rocks: a mesh each, sized by the part's height range
					local mname = spec.meshes[math.floor(rnd() * #spec.meshes) + 1]
					placeMesh(
						path,
						mname,
						x,
						gy + c[2] - (spec.embed or 0.2) * size[2],
						z,
						size[2] * 1.4,
						rnd() * 360,
						true,
						pt.mat
					)
				else
					local tilt = spec.tilt or 0
					add(path, {
						name = pt.name or "Prop",
						mat = pt.mat,
						shape = pt.shape,
						collide = pt.collide,
						rot = { (rnd() - 0.5) * 2 * tilt, rnd() * 360, (rnd() - 0.5) * 2 * tilt },
					}, size, { x, gy + c[2] + size[2] / 2 - (spec.embed or 0) * size[2], z })
				end
			end
			if dense then
				if spec.gap ~= nil then
					err(
						path .. ".gap",
						'a scatter with a "density" says its gap there ("density": { "gap" }), not beside it'
					)
					continue
				end
				-- two pieces at the least gap must not stand in each other. Each is turned any way round, so a piece
				-- reaches half its DIAGONAL: the gap is no less than the widest piece's diagonal (of a size range:
				-- the larger of the two ends, axis by axis)
				local wx, wz = pt.size[1], pt.size[3]
				if type(pt.size[1]) == "table" then
					wx = math.max(pt.size[1][1], pt.size[2][1])
					wz = math.max(pt.size[1][3], pt.size[2][3])
				end
				local across = math.sqrt(wx * wx + wz * wz)
				if spec.density.gap < across - 1e-9 then
					err(
						path .. ".density.gap",
						`the gap ({spec.density.gap}) is under the widest piece's diagonal ({math.ceil(across * 100) / 100} studs: a piece {wx} x {wz}, turned any way round): two pieces at the least gap would stand in each other`
					)
					continue
				end
				local pts, over = Scatter.sample(
					{ c[1], c[3], area[1], area[2] },
					spec.density,
					rnd,
					function(x: number, z: number): boolean
						return (terrainSite(spec, x, z))
					end
				)
				if over == "over" then
					err(
						path .. ".density",
						`this density comes to over {Scatter.MOST} pieces: widen the gap, thin the field or make the area smaller`
					)
					continue
				elseif over == "short" and #pts > 0 then
					warn(
						path .. ".density",
						`this scatter was cut short at {#pts} pieces: nearly all of its area is where nothing may stand ({Scatter.TRIES} tries) - make the "area" the place the pieces are meant for`
					)
				end
				if #pts == 0 then
					err(path .. ".density", "this density places nothing: the field is 0 wherever a piece may stand")
					continue
				end
				for _, q in pts do
					local _, gy = terrainSite(spec, q[1], q[2])
					put(q[1], q[2], gy, sized())
				end
				-- (no `continue` here: the step's group is made after this chain - without it the pieces are
				-- counted by the checks and never reach the model the game loads)
			else
				local placed: { { number } } = {}
				local tries = 0
				while #placed < spec.count and tries < spec.count * 30 do
					tries += 1
					local size = sized()
					local x = c[1] + (rnd() - 0.5) * area[1]
					local z = c[3] + (rnd() - 0.5) * area[2]
					local radius = math.max(size[1], size[3]) / 2 + (spec.gap or 1)
					local free = true
					for _, q in placed do
						if (q[1] - x) ^ 2 + (q[2] - z) ^ 2 < (q[3] + radius) ^ 2 then
							free = false
							break
						end
					end
					local okSite, gy = terrainSite(spec, x, z)
					if free and okSite then
						table.insert(placed, { x, z, radius })
						put(x, z, gy, size)
					end
				end
				if #placed < spec.count then
					warn(
						path,
						`scatter placed {#placed}/{spec.count} — area too small for the gap; enlarge area or lower count`
					)
				end
			end
		elseif kind == "room" then
			-- { center: [x, floorTop, z], size: [w, d], height, thickness, mat, floor?, roof?,
			--   openings: [{ side: "N"|"S"|"E"|"W", at: offset from the side's centre, width, height, sill? }] }
			-- N = -Z, S = +Z, E = +X, W = -X (the map's +Z is down / south)
			local c, s = spec.center, spec.size
			local h, t = spec.height or 12, spec.thickness or 1
			if type(c) ~= "table" or type(s) ~= "table" then
				err(path, "room needs center [x, floorTop, z] and size [w, d]")
				continue
			end
			-- the room CLAIMS its ceiling (only under a roof: a roofless yard or ruin has none) and its doorways (an
			-- opening with no sill, door-wide) for the rig's sheet; windows are not claimed (clerestories, broken gaps)
			if spec.roof then
				table.insert(fits, {
					kind = "ceiling",
					name = spec.name or "room",
					size = { s[1] - 2 * t, h, s[2] - 2 * t },
					pos = { c[1], c[2] + h / 2, c[3] },
					path = path,
				})
			end
			for k, o in spec.openings or {} do
				-- (a window - an opening with a sill - is not claimed; a gap wider than 8 is an open side, not a door)
				local window = type(o) == "table" and type(o.sill) == "number" and o.sill > 0
				if type(o) == "table" and not window and (o.width or 6) <= 8 then
					table.insert(fits, {
						kind = "opening",
						name = `{spec.name or "room"} opening {k}`,
						size = { o.width or 6, o.height or 8, t },
						pos = { c[1], c[2], c[3] },
						path = path,
					})
				end
			end
			local hw, hd = s[1] / 2, s[2] / 2
			local sides = {
				N = { from = { c[1] - hw, c[3] - hd }, to = { c[1] + hw, c[3] - hd }, len = s[1] },
				E = { from = { c[1] + hw, c[3] - hd }, to = { c[1] + hw, c[3] + hd }, len = s[2] },
				S = { from = { c[1] + hw, c[3] + hd }, to = { c[1] - hw, c[3] + hd }, len = s[1] },
				W = { from = { c[1] - hw, c[3] + hd }, to = { c[1] - hw, c[3] - hd }, len = s[2] },
			}
			for _, side in { "N", "E", "S", "W" } do
				local sd = sides[side]
				local gaps = {}
				for _, o in spec.openings or {} do
					if o.side == side then
						table.insert(gaps, {
							at = sd.len / 2 + (o.at or 0),
							width = o.width or 6,
							height = o.height or 8,
							sill = o.sill,
						})
					end
				end
				buildWall(
					`{path}.{side}`,
					{ from = sd.from, to = sd.to, y = c[2], height = h, thickness = t, mat = spec.mat, gaps = gaps }
				)
			end
			if spec.floor then
				add(path, { name = "RoomFloor", mat = spec.floor }, { s[1], 1, s[2] }, { c[1], c[2] - 0.5, c[3] })
			end
			if spec.roof then
				add(
					path,
					{ name = "Roof", mat = spec.roof, collide = spec.roofCollide ~= false },
					{ s[1] + t, 1, s[2] + t },
					{ c[1], c[2] + h + 0.5, c[3] }
				)
			end
		elseif kind == "dungeon" then
			-- ROOMS AND CORRIDORS BY RULE (kit/lib/worlddungeon.luau): rooms set down in the area, joined into one
			-- tree by corridors, a few more ways for loops; floor under every room and corridor cell, a wall on every
			-- edge between floor and not-floor
			local wrong = Dungeon.problems(spec)
			for _, p in wrong do
				err(path, p)
			end
			if #wrong == 0 and (type(spec.mat) ~= "string" or type(spec.floor) ~= "string") then
				err(path, 'a dungeon needs "mat" (its walls) and "floor" (palette entries)')
				wrong = { "mat" }
			end
			if #wrong == 0 then
				local plan = Dungeon.plan(spec)
				local measure = Dungeon.measure(plan)
				local reached, cut = Dungeon.reach(plan)
				if #plan.rooms < 2 then
					err(
						path,
						`the area holds {#plan.rooms} room(s) of that size: a dungeon is two or more - make the area larger or the rooms smaller`
					)
				elseif reached < #plan.rooms or cut > 0 then
					-- (never seen: the rooms are joined by construction - said if a change ever breaks it)
					err(
						path,
						`{#plan.rooms - reached} room(s) and {cut} floor cell(s) cannot be reached from the first room`
					)
				else
					if #plan.rooms < plan.asked then
						warn(
							path,
							`dungeon placed {#plan.rooms}/{plan.asked} rooms — make the area larger, the rooms smaller or ask for fewer`
						)
					end
					local c = spec.center
					local h = spec.height or Dungeon.DEFAULTS.height
					local t = spec.thickness or Dungeon.DEFAULTS.thickness
					layCells(add, path, plan, c, h, t, spec, "DungeonFloor")
					local places = {}
					for k, r in plan.rooms do
						local x0, z0, x1, z1 = Dungeon.studs(plan, c, r[1], r[2], r[3], r[4])
						table.insert(
							places,
							{ center = { (x0 + x1) / 2, c[2], (z0 + z1) / 2 }, size = { x1 - x0, z1 - z0 } }
						)
						if spec.roof then -- (a room under a roof claims its ceiling for the rig's sheet)
							table.insert(fits, {
								kind = "ceiling",
								name = `{spec.name or "dungeon"} room {k}`,
								size = { x1 - x0, h, z1 - z0 },
								pos = { (x0 + x1) / 2, c[2] + h / 2, (z0 + z1) / 2 },
								path = path,
							})
						end
					end
					if spec.start == true then
						local part = add(
							path,
							{ name = "Spawn", mat = spec.floor },
							{ 6, 1, 6 },
							{ places[1].center[1], c[2] + 0.5, places[1].center[3] }
						)
						if part then
							part.class = "SpawnLocation"
							part.spawn = true
						end
					end
					table.insert(
						dungeons,
						{ name = spec.name or path, rooms = places, links = plan.links, measure = measure }
					)
				end
			end
		elseif kind == "tiles" then
			-- A PLACE LAID OUT OF TILES THAT FIT (kit/lib/worldwfc.luau: wave function collapse): a grid filled with
			-- the set's tiles so that the words on two sides that touch are the same; each tile's parts set down
			-- in its cell, turned with it
			local wrong = Wfc.problems(spec)
			for _, p in wrong do
				err(path, p)
			end
			if #wrong == 0 then
				local laid, tries = Wfc.solve(spec)
				if not laid then
					err(path, `tiles: {tries}`)
				else
					local c, cell = spec.center, spec.cell
					local nx, nz = spec.grid[1], spec.grid[2]
					local count: { [string]: number } = {}
					for ti = 1, nx do
						for tj = 1, nz do
							local way = laid[ti][tj]
							local t = spec.set.tiles[way.tile]
							count[t.name] = (count[t.name] or 0) + 1
							local cx = c[1] - nx * cell / 2 + (ti - 0.5) * cell
							local cz = c[3] - nz * cell / 2 + (tj - 0.5) * cell
							-- (a quarter turn clockwise seen from above is a yaw of -90)
							local rot = World.turnMatrix(-90 * way.turn)
							for _, q in t.parts do
								local x, z = Wfc.turned(q.pos[1], q.pos[3], way.turn)
								add(
									path,
									{ name = q.name or t.name, mat = q.mat },
									{ q.size[1], q.size[2], q.size[3] },
									{ cx + x, c[2] + q.pos[2], cz + z },
									rot
								)
							end
						end
					end
					table.insert(
						tileLayouts,
						{ name = spec.name or path, cells = nx * nz, count = count, tries = tries, grid = laid }
					)
				end
			end
		elseif kind == "decal" then
			-- DECALS ON WALLS AND FLOORS (kit/lib/worlddecal.luau): a picture made by `kit world decal`, laid on a
			-- face that is there. Each is a thin unseen part just off the face with a Decal on its outward side
			local wrong = Decal.problems(spec)
			for _, p in wrong do
				err(path, p)
			end
			if #wrong == 0 then
				local boxes = {}
				for _, q in parts do
					-- (a face a decal can lie on: a block that stands square - not turned, not round - solid and seen)
					local square = q.shape == nil or q.shape == "Block"
					for a = 1, 3 do
						for c = 1, 3 do
							local v = math.abs(q.rot[a][c])
							square = square and (v < 1e-6 or math.abs(v - 1) < 1e-6)
						end
					end
					if square and q.collide and q.transparency < 1 and not q.backdrop then
						local half = {}
						for a = 1, 3 do
							half[a] = math.abs(q.rot[a][1]) * q.size[1] / 2
								+ math.abs(q.rot[a][2]) * q.size[2] / 2
								+ math.abs(q.rot[a][3]) * q.size[3] / 2
						end
						table.insert(boxes, { pos = q.pos, half = half })
					end
				end
				local read = if type(opts) == "table" and type(opts.decals) == "function"
					then opts.decals
					else Decal.read
				local known: { [string]: any } = {}
				local placed, waiting, floating = 0, 0, 0
				local laid = Decal.lay(spec)
				if stepPlaces[i] then
					-- IN A PREFAB: the walls of its prefab that were built before it stand where they will stand
					-- (each step is moved before the next begins), so the decal is moved FIRST and judged there -
					-- its place, and the side it looks toward; and it is not moved again
					placing = nil
					local moved = {}
					for _, d in laid do
						local x, y, z, deg = Prefab.moved(stepPlaces[i].moves, d.at[1], d.at[2], d.at[3])
						local f = Decal.FACING[d.facing]
						local nx, nz = Prefab.turn(f.normal[1], f.normal[3], 0, 0, deg)
						local side = if deg % 90 == 0
							then Decal.facingOf(math.round(nx), f.normal[2], math.round(nz))
							else nil
						if not side then
							err(
								path,
								`a decal in a prefab turned {deg} degrees in all: a decal lies on a face that stands square (quarter turns only)`
							)
							moved = {}
							break
						end
						-- (on a floor a quarter turn changes which way its width runs)
						local size = d.size
						if f.normal[2] ~= 0 and deg % 180 ~= 0 then
							size = { d.size[2], d.size[1] }
						end
						table.insert(moved, { name = d.name, at = { x, y, z }, size = size, facing = side })
					end
					laid = moved
				end
				if next(palette) == nil then
					err(
						path,
						'a decal needs the blueprint to have a "palette" (any entry: its unseen part is made of one)'
					)
					laid = {}
				end
				for _, d in laid do
					local spot = `{d.facing}:{d.at[1]}:{d.at[2]}:{d.at[3]}`
					if decalsAt[spot] then
						err(
							path,
							`two decals lie on one spot ({d.at[1]}, {d.at[2]}, {d.at[3]}) looking {d.facing}: they would flicker through each other`
						)
					end
					decalsAt[spot] = true
					if known[d.name] == nil then
						local record, id = read(d.name)
						known[d.name] = { record = record, id = id }
						if record == nil then
							err(
								path,
								`no decal "{d.name}" - make it: lune run kit world decal {d.name} --kind leak|stain|crack|moss|soot`
							)
						elseif record == false then
							err(
								path,
								`the decal "{d.name}" has no record that can be read (its .decal.json is damaged) - make it again: lune run kit world decal {d.name} --kind ...`
							)
						elseif id == nil and not decalsWaiting[d.name] then
							decalsWaiting[d.name] = true
							warn(
								path,
								`the decal "{d.name}" is not uploaded: it is left out of the game until its picture is uploaded and its id stands in the project's ids file as decals.{d.name} (kit upload does not take decals yet)`
							)
						end
					end
					local k = known[d.name]
					if type(k.record) == "table" then
						-- (the picture's own tint under the step's: what it comes to must not read as blood either)
						local made = k.record.tint
						if
							spec.tint
							and type(made) == "table"
							and type(made[1]) == "number"
							and type(made[2]) == "number"
							and type(made[3]) == "number"
							and Decal.bloody(
								made[1] * spec.tint[1] / 255,
								made[2] * spec.tint[2] / 255,
								made[3] * spec.tint[3] / 255
							)
						then
							err(
								path,
								`the decal "{d.name}" under this "tint" reads as blood: not laid (no blood or gore in this kit)`
							)
							continue
						end
						local why = Decal.lies(d, boxes, groundAt(d.at[1], d.at[3]))
						if why then
							floating += 1
							if floating <= 3 then
								err(
									path,
									`a decal lies on nothing at ({d.at[1]}, {d.at[2]}, {d.at[3]}): {why} (build the wall before the decal)`
								)
							end
						elseif k.id == nil then
							waiting += 1
						else
							local size, pos, face = Decal.part(d)
							local part =
								add(path, { name = `Decal_{d.name}`, mat = next(palette), sink = false }, size, pos)
							if part then
								part.transparency = 1
								part.collide = false
								part.query = false
								part.castShadow = false
								part.children = {
									{
										kind = "decal",
										id = k.id,
										face = face,
										transparency = spec.transparency,
										tint = spec.tint,
									},
								}
								placed += 1
							else
								-- (the compiler drops a part that stands wholly under the land: said, never silent)
								err(
									path,
									`a decal at ({d.at[1]}, {d.at[2]}, {d.at[3]}) lies under the land: it would not be seen`
								)
							end
						end
					end
				end
				if floating > 3 then
					err(path, `{floating} decals of this step lie on nothing in all`)
				end
				table.insert(
					decalsLaid,
					{ name = path, laid = #laid, placed = placed, waiting = waiting, floating = floating }
				)
			end
		elseif kind == "cave" then
			-- A CAVE GROWN BY A CELLULAR AUTOMATON (kit/lib/worldcave.luau): rock and open cells by chance, settled by
			-- the neighbours' rule, then mended into one piece of floor no narrower than 8 studs; floor under every
			-- open cell, a wall on every edge of it
			local wrong = Cave.problems(spec)
			for _, p in wrong do
				err(path, p)
			end
			if #wrong == 0 and (type(spec.mat) ~= "string" or type(spec.floor) ~= "string") then
				err(path, 'a cave needs "mat" (its walls) and "floor" (palette entries)')
				wrong = { "mat" }
			end
			if #wrong == 0 then
				local plan = Cave.plan(spec)
				local reached, cut = Dungeon.reach(plan)
				local bodies, thin = Cave.wide(plan)
				if plan.share < Cave.LEAST then
					err(
						path,
						`the cave closed up: {math.floor(plan.share * 100 + 0.5)}% of the area is floor (under {Cave.LEAST * 100}%) - a lower "fill" (it is {spec.fill or Cave.DEFAULTS.fill}) or another seed`
					)
				elseif reached ~= 1 or cut > 0 or bodies ~= 1 or thin > 0 or Cave.pinches(plan) > 0 then
					-- (never seen: the floor is one piece a body 8 studs wide slides through, by construction - said if
					-- a change ever breaks it)
					err(
						path,
						`the cave's floor is not one piece a body 8 studs wide gets through ({cut} cell(s) cut off, {bodies} group(s), {thin} thin cell(s), {Cave.pinches(
							plan
						)} corner(s) touching)`
					)
				else
					local c = spec.center
					local h = spec.height or Cave.DEFAULTS.height
					local t = spec.thickness or Cave.DEFAULTS.thickness
					layCells(add, path, plan, c, h, t, spec, "CaveFloor")
					local function place(cell: { number }): { number }
						local x0, z0, x1, z1 = Dungeon.studs(plan, c, cell[1], cell[2], cell[1], cell[2])
						return { (x0 + x1) / 2, c[2], (z0 + z1) / 2 }
					end
					-- the widest chamber: the largest square of floor; the start is its middle (8 studs or more
					-- across: the spawn's pad lies wholly on it)
					local low = place({ 1, 1 })
					local start = {
						low[1] - plan.cell / 2 + plan.start[1] * plan.cell,
						c[2],
						low[3] - plan.cell / 2 + plan.start[2] * plan.cell,
					}
					local side = plan.side * plan.cell
					if spec.roof then -- (under a roof the widest chamber claims its ceiling for the rig's sheet)
						table.insert(fits, {
							kind = "ceiling",
							name = `{spec.name or "cave"} chamber`,
							size = { side, h, side },
							pos = { start[1], c[2] + h / 2, start[3] },
							path = path,
						})
					end
					if spec.start == true then
						local part = add(
							path,
							{ name = "Spawn", mat = spec.floor },
							{ 6, 1, 6 },
							{ start[1], c[2] + 0.5, start[3] }
						)
						if part then
							part.class = "SpawnLocation"
							part.spawn = true
						end
					end
					table.insert(caves, {
						name = spec.name or path,
						start = start,
						far = place(plan.far),
						measure = {
							floor = plan.cells * plan.cell * plan.cell,
							share = plan.share,
							chamber = side,
							walk = plan.walk * plan.cell,
							closed = plan.closed,
							pockets = plan.pockets,
							opened = plan.opened,
						},
					})
				end
			end
		elseif kind == "cover" then
			-- { center: [x, y, z], area: [w, d], count, seed, half?: share 0..1 (default 0.6), mat, gap? }
			-- half cover = 3 studs (crouch-less R6: you see over it, it blocks a body shot), full = 7 (breaks sight)
			local rnd = lcg(spec.seed or 1)
			local c, area = spec.center, spec.area or { 40, 40 }
			local placed, tries = {}, 0
			local count = spec.count or 6
			while #placed < count and tries < count * 40 do
				tries += 1
				local full = rnd() > (spec.half or 0.6)
				local w = 4 + rnd() * 6
				local size = { w, if full then 7 else 3, 1.5 + rnd() * 1.5 }
				local x = c[1] + (rnd() - 0.5) * area[1]
				local z = c[3] + (rnd() - 0.5) * area[2]
				local radius = w / 2 + (spec.gap or 6)
				local free = true
				for _, q in placed do
					if (q[1] - x) ^ 2 + (q[2] - z) ^ 2 < (q[3] + radius) ^ 2 then
						free = false
						break
					end
				end
				local okSite, gy = terrainSite(spec, x, z)
				if free and okSite then
					table.insert(placed, { x, z, radius })
					add(path, {
						name = if full then "FullCover" else "HalfCover",
						mat = spec.mat,
						rot = { 0, rnd() * 180, 0 },
					}, { size[1], size[2] + (if spec.ground then 2 else 0), size[3] }, {
						x,
						gy + c[2] + size[2] / 2 - (if spec.ground then 1 else 0),
						z,
					})
				end
			end
			if #placed < count then
				warn(path, `cover placed {#placed}/{count} — enlarge the area or lower the gap`)
			end
		elseif kind == "path" then
			-- { points: [[x, z], ...], y: top, width, thickness?, mat, curb?: { height, width, mat } }
			local pts, y, w = spec.points, spec.y or 0, spec.width or 8
			local th = spec.thickness or 0.4
			if type(pts) ~= "table" or #pts < 2 then
				err(path, "path needs at least 2 points [[x, z], ...]")
				continue
			end
			local painted = if spec.worn ~= nil then (spec.wornWidth or w * 1.6) else w
			table.insert(roadLines, { points = pts, r = math.max(w, painted) / 2 + 3 })
			if spec.bed ~= nil and spec.bed ~= false and spec.ground ~= true then
				err(path .. ".bed", 'a "bed" is cut into the land: it is for a path with "ground": true')
			end
			if spec.ground == true and spec.bed ~= nil and spec.bed ~= false then
				-- A BED (the owner's W-R07): the road's own line through the land, never steeper than its grade; the
				-- land is cut down to it and filled up to it, and comes back to itself over a shoulder. Laid BEFORE
				-- the road's pieces and its worn trail, so both lie on the graded land - and so does every later step
				local b = if spec.bed == true then {} else spec.bed
				local grade = if type(b) == "table" then b.grade else nil
				if grade == nil and type(spec.route) == "table" then
					grade = spec.route.grade
				end
				local shoulder = if type(b) == "table" and b.shoulder ~= nil then b.shoulder else 10
				if type(b) ~= "table" then
					err(path .. ".bed", '"bed" is true or { "grade": 0.15, "shoulder": 10 }')
				elseif type(grade) ~= "number" or grade ~= grade or grade <= 0 or grade > 1 then
					err(
						path .. ".bed",
						'a bed needs its "grade" (the steepest it may climb, rise over run: over 0, 1 at most; a routed road hands on its own)'
					)
				elseif type(shoulder) ~= "number" or shoulder ~= shoulder or shoulder < 2 or shoulder > 64 then
					err(path .. ".bed", 'a bed\'s "shoulder" is 2 to 64 studs')
				elseif w + 2 > 64 then
					err(path .. ".bed", "a road over 62 studs wide takes no bed")
				else
					-- (the ground op the road lies on: the one its first point stands on; a road that leaves it has
					-- no land to be cut into there)
					local index: number? = nil
					for gi, g in groundOps do
						if
							index == nil
							and math.abs(pts[1][1] - g.center[1]) <= g.size[1] / 2
							and math.abs(pts[1][2] - g.center[3]) <= g.size[2] / 2
						then
							index = gi
						end
					end
					local made, why = nil, "the road's first point stands on no land"
					local higher: { number }? = nil -- (a place on the road where another ground stands higher)
					if index then
						local g = groundOps[index]
						made, why = RoadBed.profile(pts, function(x: number, z: number): number?
							if
								math.abs(x - g.center[1]) > g.size[1] / 2
								or math.abs(z - g.center[3]) > g.size[2] / 2
							then
								return nil
							end
							local h = World.groundHeight(g, x, z)
							-- (the land a body walks is the highest ground there: a bed cut into one ground under
							-- another would lie buried)
							local top = groundAt(x, z)
							if higher == nil and top ~= nil and top > h + 1e-6 then
								higher = { x, z }
							end
							return h
						end, grade, nil, w / 2 + 1)
					end
					if made and higher then
						err(
							path .. ".bed",
							`no bed: where this road runs ([{math.floor(higher[1] + 0.5)}, {math.floor(higher[2] + 0.5)}]) another ground stands higher than the one its bed would be cut into - a bed is cut into one ground: lay the road on one, or let the other have no land there`
						)
					elseif not made or not index then
						err(path .. ".bed", `no bed: {why}`)
					else
						-- (a copy of the op: the blueprint's own table is never written on)
						local old = groundOps[index]
						local g = table.clone(old)
						groundOps[index] = g
						local bed = { points = made.points, width = w + 2, shoulder = shoulder }
						g.beds = if g.beds then table.clone(g.beds) else {}
						table.insert(g.beds, bed)
						bedsOf[index] = bedsOf[index] or {}
						table.insert(bedsOf[index], bed)
						-- (the game's record of its land is one string of about 200,000 characters in all)
						bedChars += #serde.encode("json", bed)
						if bedChars > World.BED_CHARS then
							err(
								path .. ".bed",
								`the roads' beds come to {bedChars} characters in the game's record of its land ({World.BED_CHARS} at most: it holds about 200,000 in all) - fewer or shorter roads with beds`
							)
						end
						local record = {
							name = spec.name or path,
							grade = grade,
							steepest = RoadBed.steepest(made.points),
							cut = made.cut,
							fill = made.fill,
							length = made.length,
							loop = made.loop,
						}
						table.insert(bedsLaid, record)
						if routedRoad then
							-- (a routed road is measured on its bed: that is where its pieces lie)
							routedRoad.steepest = record.steepest
							routedRoad.bed = true
						end
						local depth = math.max(made.cut, made.fill)
						-- (a side falls by the smoothstep's steepest, 1.5 times the depth over the shoulder: past one, it
						-- stands steeper than 45 degrees - at the road's sides and round its ends alike)
						if depth * 1.5 > shoulder and depth <= 24 then
							warn(
								path .. ".bed",
								`this bed's sides stand steeper than 45 degrees at its deepest ({math.floor(depth + 0.5)} studs of cut or fill, at the road's edge or on its line, over a shoulder of {shoulder}): a "shoulder" of {math.ceil(
									depth * 1.5
								)} or more makes a bank, not a wall`
							)
						end
						if made.cut > 24 or made.fill > 24 then
							warn(
								path .. ".bed",
								`this bed cuts {math.floor(made.cut + 0.5)} studs into the land and fills {math.floor(
									made.fill + 0.5
								)} at its most: a tunnel, a bridge or a way round may be what is meant (a "route" finds one)`
							)
						end
						-- what was built BEFORE the road stands on the land as it was: where the bed moved it by more
						-- than a stud, it now floats or is buried - said
						local moved, firstMoved = 0, nil
						for _, q in parts do
							if
								not q.backdrop
								and math.abs(q.pos[1] - g.center[1]) <= g.size[1] / 2
								and math.abs(q.pos[3] - g.center[3]) <= g.size[2] / 2
							then
								local before = World.groundHeight(old, q.pos[1], q.pos[3])
								local after = World.groundHeight(g, q.pos[1], q.pos[3])
								if math.abs(after - before) > 1 then
									moved += 1
									firstMoved = firstMoved or q
								end
							end
						end
						if firstMoved then
							warn(
								path .. ".bed",
								`{moved} part(s) built before this road stand where its bed moved the land by more than a stud (the first: "{firstMoved.name}" at [{math.floor(
									firstMoved.pos[1] + 0.5
								)}, {math.floor(firstMoved.pos[3] + 0.5)}]): they stand on the land as it was, floating or buried - lay the road before them`
							)
						end
					end
				end
			end
			if spec.ground == true then
				-- a road over the terrain: short pieces, each tilted from ground to ground (y = height above it).
				-- "worn": "<terrain material>" also wears a trail INTO the land (wider than the road, ragged at the
				-- edge in the viewer); "parts": false = only the trail (a dirt path, no stones)
				if spec.worn ~= nil then
					if not Environment.MATERIALS[spec.worn] then
						err(path .. ".worn", `unknown terrain material "{tostring(spec.worn)}"`)
					else
						local stroke = { material = spec.worn, width = spec.wornWidth or w * 1.6, points = {} }
						for k = 1, #pts - 1 do
							local a, b = pts[k], pts[k + 1]
							local len = math.sqrt((b[1] - a[1]) ^ 2 + (b[2] - a[2]) ^ 2)
							local n = math.max(1, math.ceil(len / 4))
							for j = 0, n - (if k < #pts - 1 then 1 else 0) do
								local f = j / n
								local x, z = a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f
								table.insert(stroke.points, { x, groundAt(x, z) or 0, z })
							end
						end
						table.insert(paints, stroke)
					end
				end
				local stairSaid = false -- (a road too steep for R6 steps is said once, not at every stretch)
				-- (on by default; the worlds built before them keep their ramps and level planks unless they say
				-- "stairs": true / "bank": true - World.ROAD_V3_BEFORE)
				local before = World.ROAD_V3_BEFORE[tostring(bp.name)] == true
				local stairsOn = if spec.stairs == nil then not before else spec.stairs == true
				local bankOn = if spec.bank == nil then not before else spec.bank == true
				-- (where it meets other roads: cut at each pad's rim, its ends on the pad's plane - kit/lib/worldjunction.luau)
				local myNodes = junctionsOf[i] or {}
				local function planeOf(nd: Junction.Node): { number }?
					if junctionPlanes[nd] == nil then
						junctionPlanes[nd] = Junction.plane(nd, groundAt, World.ROAD_BANK_MAX) or false
					end
					local pl = junctionPlanes[nd]
					return if pl then pl else nil
				end
				local function landY(x: number, z: number): number
					for _, nd in myNodes do
						local pl = planeOf(nd)
						if pl and (x - nd.x) ^ 2 + (z - nd.z) ^ 2 <= (nd.r + 0.01) ^ 2 then
							return Junction.height(nd, pl, x, z)
						end
					end
					return groundAt(x, z) or 0
				end
				local runs = if #myNodes > 0 then Junction.cut(pts, myNodes, w) else { pts }
				for _, line in runs do
					local laid = line
					for k = 1, if spec.parts == false then 0 else #laid - 1 do
						local a, b = laid[k], laid[k + 1]
						local len = math.sqrt((b[1] - a[1]) ^ 2 + (b[2] - a[2]) ^ 2)
						local n = math.max(1, math.ceil(len / 6))
						for j = 0, n - 1 do
							local f0, f1 = j / n, (j + 1) / n
							local x0, z0 = a[1] + (b[1] - a[1]) * f0, a[2] + (b[2] - a[2]) * f0
							local x1, z1 = a[1] + (b[1] - a[1]) * f1, a[2] + (b[2] - a[2]) * f1
							local y0 = landY(x0, z0) + y
							local y1 = landY(x1, z1) + y
							local d = { x1 - x0, y1 - y0, z1 - z0 }
							local l3 = math.sqrt(d[1] ^ 2 + d[2] ^ 2 + d[3] ^ 2)
							local flat = math.sqrt(d[1] ^ 2 + d[3] ^ 2)
							local pitch = math.deg(math.atan2(math.abs(d[2]), math.max(flat, 1e-6)))
							if stairsOn and pitch > World.ROAD_STAIR_DEG and flat > 0.5 then
								-- STONE STEPS (LIMITATIONS_FIXES_V3.md stage E.3: "stone stairs > 16 deg"): a stretch
								-- steeper than a cart climbs is a flight - treads about a stud apart in height (the r6
								-- step), each a block from its tread down to the stretch's foot, square to the road
								local rises = math.max(1, math.floor(math.abs(d[2]) / World.ROAD_STAIR_RISE + 0.5))
								local run = flat / rises
								local foot = math.min(y0, y1) - th
								local r = World.alongX({ d[1], 0, d[3] })
								for st = 1, rises do
									local top = if d[2] >= 0
										then y0 + d[2] * st / rises
										else y0 + d[2] * (st - 1) / rises
									local mid = (st - 0.5) / rises
									add(path, { name = "Step", mat = spec.mat }, { run + 0.05, top - foot, w }, {
										x0 + d[1] * mid,
										(top + foot) / 2,
										z0 + d[3] * mid,
									}, r)
								end
								if run < World.ROAD_STAIR_RUN and not stairSaid then
									stairSaid = true
									warn(
										path,
										`this road climbs {math.floor(pitch + 0.5)} degrees on the land: its steps are {math.floor(
											run * 10 + 0.5
										) / 10} studs deep, under an R6 stair's {World.ROAD_STAIR_RUN} - a gentler line (a "route" with its "grade") or a bed`
									)
								end
							else
								-- BANKED with the land across it (V3 stage E.3: "banked roads"): a piece rolls about its own
								-- line to the land's fall from one side to the other, up to ROAD_BANK_MAX degrees - a level
								-- plank on a hillside stood in the air on its low side and in the land on its high one
								local rot = World.alongX(d)
								local zx, zz = rot[1][3], rot[3][3]
								local roll: number? = nil
								if bankOn then
									local mx, mz = (x0 + x1) / 2, (z0 + z1) / 2
									local hi = groundAt(mx + zx * w / 2, mz + zz * w / 2)
									local lo = groundAt(mx - zx * w / 2, mz - zz * w / 2)
									if hi and lo then
										local cap = math.rad(World.ROAD_BANK_MAX)
										roll = math.clamp(math.atan((hi - lo) / w), -cap, cap)
									end
								end
								-- (near a junction the roll goes over to the pad's: the slope of its plane across this road -
								-- all of it at the piece's end nearest the rim, none an EASE past it)
								if #myNodes > 0 then
									local t0, n0 = Junction.ease(myNodes, x0, z0)
									local t1, n1 = Junction.ease(myNodes, x1, z1)
									local t, nd = t0, n0
									if t1 ~= nil and (t == nil or t1 < t) then
										t, nd = t1, n1
									end
									local pl = if nd then planeOf(nd) else nil
									if t ~= nil and pl then
										roll = Junction.roll(pl, d[1], d[3], zx, zz) * (1 - t) + (roll or 0) * t
									end
								end
								if roll ~= nil and roll ~= 0 then
									local c, sn = math.cos(roll), math.sin(roll)
									for row = 1, 3 do
										local yy, zz2 = rot[row][2], rot[row][3]
										rot[row][2] = yy * c - zz2 * sn
										rot[row][3] = zz2 * c + yy * sn
									end
								end
								add(path, { name = "Road", mat = spec.mat }, { l3 + 0.8, th, w }, {
									(x0 + x1) / 2,
									(y0 + y1) / 2 - th / 2,
									(z0 + z1) / 2,
								}, rot)
							end
						end
					end
				end
				-- the PAD of each junction (laid once, by the first road that reaches it): a disc in the plane that fits
				-- the land round it, its top Junction.LIFT over the roads' ends, its foot a stud down in the land
				for _, nd in myNodes do
					if junctionLaid[nd] or spec.parts == false then
						continue
					end
					junctionLaid[nd] = true
					local pl = planeOf(nd)
					if not pl then
						warn(
							path,
							`a junction at [{math.floor(nd.x + 0.5)}, {math.floor(nd.z + 0.5)}] has no land all round it: no pad`
						)
						continue
					end
					local nl = math.sqrt(pl[1] ^ 2 + 1 + pl[2] ^ 2)
					local up = { -pl[1] / nl, 1 / nl, -pl[2] / nl }
					local tall = Junction.LIFT + th + 1
					local topY = pl[3] + y + Junction.LIFT
					add(path, { name = "Junction", mat = spec.mat, shape = "Cylinder" }, { tall, nd.r * 2, nd.r * 2 }, {
						nd.x - up[1] * tall / 2,
						topY - up[2] * tall / 2,
						nd.z - up[3] * tall / 2,
					}, World.alongX(up))
					table.insert(junctionsLaid, {
						name = spec.name or path,
						kind = nd.kind,
						at = { nd.x, nd.z },
						radius = nd.r,
						arms = #nd.arms,
						tilt = math.deg(math.atan(math.sqrt(pl[1] ^ 2 + pl[2] ^ 2))),
					})
				end
				table.insert(groups, { name = spec.name or "Path", parts = current, stream = spec.stream }) -- (continue skips the loop's own insert)
				continue
			end
			for k = 1, #pts - 1 do
				local a, b = pts[k], pts[k + 1]
				local dx, dz = b[1] - a[1], b[2] - a[2]
				local len = math.sqrt(dx * dx + dz * dz)
				if len <= 0 then
					continue
				end
				local r = World.rotation({ 0, math.deg(math.atan2(-dz, dx)), 0 })
				local mx, mz = (a[1] + b[1]) / 2, (a[2] + b[2]) / 2
				-- a curved path's pieces meet at an angle: each runs past a joint by what that joint's OWN angle opens
				-- at the path's rim (never past the path's typed ends), and six pieces in a row lie each a hair lower
				-- than the last (two tops in one plane would flicker where they lap; on a tight bend several lap)
				local l0, l1, dip = 0, 0, 0
				if curved then
					local function lapOf(at: number, half: number): number
						if at <= 1 or at >= #pts then
							return 0
						end
						local d = math.min(Curve.turn(pts[at - 1], pts[at], pts[at + 1]), 120)
						return half * math.tan(math.rad(d) / 2) + 0.02
					end
					l0, l1 = lapOf(k, w / 2), lapOf(k + 1, w / 2)
					dip = (k % World.PATH_LEVELS) * 0.01
					mx, mz = mx + dx / len * (l1 - l0) / 2, mz + dz / len * (l1 - l0) / 2
				end
				add(path, { name = "Path", mat = spec.mat }, { len + l0 + l1, th, w }, { mx, y - th / 2 - dip, mz }, r)
				local curb = spec.curb
				if curb then
					for _, side in { -1, 1 } do
						-- the curb sits just outside the path's edge, perpendicular offset in the ground plane
						local ox, oz =
							-dz / len * side * (w / 2 + (curb.width or 1) / 2),
							dx / len * side * (w / 2 + (curb.width or 1) / 2)
						add(path, { name = "Curb", mat = curb.mat or spec.mat }, {
							-- (a curb stands farther out than the rim: it laps by its own reach, and dips with its piece)
							len + (l0 + l1) * (1 + 2 * (curb.width or 1) / w),
							curb.height or 0.6,
							curb.width or 1,
						}, { mx + ox, y + (curb.height or 0.6) / 2 - th - dip, mz + oz }, r)
					end
				end
				if k < #pts - 1 and not curved then -- a square pad on the joint so turns have no wedge-shaped hole
					add(path, { name = "PathJoint", mat = spec.mat }, { w, th, w }, { b[1], y - th / 2, b[2] })
				end
			end
		elseif kind == "breakable" then
			-- a part the combat code may break: tagged KitBreakable (+ KitHealth) for the game to read
			local part = add(path, spec, spec.size or {}, spec.pos or { 0, 0, 0 })
			if part then
				part.attributes = { KitBreakable = true, KitHealth = spec.health or 50 }
			end
		elseif kind == "building" then
			-- { center: [x, groundTop, z], size: [w, d], floors, floorHeight?, thickness?, mat, slab?, roof?: "flat" |
			--   "gable", roofMat?, door?: { side, width, height }, windows?: { every, width, height, sill } }
			--   (roofCollide: false — a pitched / flat roof no one can climb onto is decoration, not floor)
			local c, s = spec.center, spec.size
			if type(c) ~= "table" or type(s) ~= "table" then
				err(path, "building needs center [x, groundTop, z] and size [w, d]")
				continue
			end
			-- the defaults sit on the owner's R6 rig (kit world check's r6 sheet; his 2026-10-29 verdict "some things are
			-- not ... to perfectly fit my R6 rig" was "a room a head too low and a rail at the knee"): 14 floor to floor =
			-- 13 clear under the 1-stud slab (12 was 11 clear: a room a head too low), a 3.5-stud window sill
			local floors, fh, t = spec.floors or 2, spec.floorHeight or 14, spec.thickness or 1
			local win = spec.windows or { every = 10, width = 4, height = 8, sill = 3.5 }
			-- "skin": the building's look is a whole-building mesh (World.skinProblem says when it cannot wrap this one):
			-- its walls and roof stay as invisible collision, its floors, panes and furniture stay seen
			local skin = if type(spec.skin) == "string" and not greybox then spec.skin else nil
			local skinYaw = World.SKIN_YAW[if type(spec.door) == "table" then spec.door.side or "S" else "S"] or 0
			if skin then
				local bad = World.skinProblem(meshReg[skin], skin, s, floors, fh, spec.door, win, skinYaw)
				if bad then
					err(path .. ".skin", bad)
					skin = nil
				end
			end
			-- "facade": "<prefix>" - the building's look is put together from MODULES (kit/lib/worldfacade.luau): every
			-- wall of every storey split into its openings and the plain runs between, each filled by one stretched
			-- module "<prefix>_<kind>_<storey height>". Its walls and roof stay as invisible collision, as with a skin.
			-- A module that is missing or made for other openings is said once, and the house is built plain.
			local facade = if not skin
					and not greybox
					and type(spec.facade) == "string"
					and spec.facade ~= ""
				then spec.facade
				else nil
			if type(spec.skin) == "string" and type(spec.facade) == "string" then
				err(path .. ".facade", 'a building wears a "skin" (one whole mesh) or a "facade" (modules), not both')
				skin, facade = nil, nil -- (which one was meant is not the compiler's to guess: built plain)
			end
			local facadeWin, facadeOriel = "window", false
			if facade then
				local seed = if type(spec.seed) == "number" then spec.seed else math.floor(c[1] * 7 + c[3] * 13)
				facadeWin, facadeOriel = Facade.pick(seed, floors)
				local door = if type(spec.door) == "table" then spec.door else nil
				local winGap =
					{ width = win.width or 4, height = (win.sill or 3.5) + (win.height or 5), sill = win.sill or 3.5 }
				local wants =
					{ { kind = "wall", floorHeight = fh }, { kind = facadeWin, floorHeight = fh, gap = winGap } }
				if door then
					table.insert(wants, {
						kind = "door",
						floorHeight = fh,
						gap = { width = door.width or 6, height = door.height or 8.5, sill = 0 },
					})
				end
				if facadeOriel then
					table.insert(wants, { kind = "oriel", floorHeight = fh, gap = winGap })
				end
				if floors > 1 then
					table.insert(wants, { kind = "band" })
				end
				if spec.roof == "gable" then
					local alongX = skinYaw == 0 or skinYaw == 180
					table.insert(wants, {
						kind = "roof",
						front = (if alongX then s[1] else s[2]) + 2 * t,
						depth = (if alongX then s[2] else s[1]) + 2 * t,
					})
					table.insert(wants, { kind = "chimney" })
				end
				local ok = true
				for _, want in wants do
					local name = Facade.name(facade, want.kind, fh)
					local bad = Facade.problem(meshReg[name], name, want)
					-- (a W3 module's meshes on its other trim sheet: a window without its glass is no window)
					local reg = meshReg[name]
					if not bad and type(reg) == "table" and type(reg.parts) == "table" then
						for _, part in reg.parts do
							local pr = meshReg[part]
							if type(pr) ~= "table" or type(pr.min) ~= "table" or type(pr.size) ~= "table" then
								bad =
									`the module "{name}"'s part "{tostring(part)}" is not in the registry: make it again, kit world meshes`
							end
						end
					end
					if bad then
						ok = false
						if not facadeSaid[bad] then -- (once a fault, not once a house of a hundred)
							facadeSaid[bad] = true
							err(path .. ".facade", bad)
						end
					end
				end
				if not ok then
					facade = nil
				end
			end
			local dressed = skin ~= nil or facade ~= nil
			dressKey = nil
			if dressed then
				dressBegin(path)
			end
			-- "stairs": true — a flight per floor (and to a flat roof) along the inside of the west wall, and a
			-- stairwell cut in the slab above where a 5-stud body would hit its head. The R6 run is 1.8; a building too
			-- shallow for it keeps a steeper flight (down to the old 1.6) and the r6 sheet names the step
			local lane = { w = 4, run = 1.8, x = c[1] - s[1] / 2 + t + 2, z0 = c[3] - s[2] / 2 + t + 1 }
			if math.ceil(fh) * lane.run > s[2] - 2 * t - 2 then
				lane.run = math.max(1.6, (s[2] - 2 * t - 2) / math.ceil(fh))
			end
			local flight = math.ceil(fh) * lane.run
			if spec.stairs == true and flight > s[2] - 2 * t - 2 then
				err(path .. ".stairs", `a {fh}-stud floor needs a {flight}-stud stair run; the building is {s[2]} deep`)
			end
			-- THE FLIGHTS TURN BACK (a switchback; card u3re, 2026-11-15). Every flight was built in the SAME lane,
			-- each starting again at the north end: the upper flight's solid steps then stood on the very hole the
			-- flight below comes up through - 0 studs over its top tread. No building of three floors, or of two
			-- under a flat roof, could be climbed past its first floor. Now the flights alternate between two lanes
			-- side by side: flight 0 runs south in the first, flight 1 comes back north in the second, flight 2
			-- runs south in the first again. Each slab's stairwell is cut over the top of the flight BELOW it.
			local flights = if spec.stairs == true then floors - (if spec.roof == "gable" then 1 else 0) else 0
			local twoLanes = flights >= 2
			lane.east = lane.x + lane.w / 2 + (if twoLanes then lane.w else 0) -- (the stair hall's east edge)
			if twoLanes and s[1] - 2 * t < 2 * lane.w + 3 then
				err(
					path .. ".stairs",
					`{flights} flights of stairs turn back beside each other: two lanes of {lane.w} studs and a body's width, {2 * lane.w + 3} inside the walls - the building is {s[1]} wide (inside: {s[1] - 2 * t})`
				)
			end
			-- flight g (from floor g up): which lane, and which way it climbs along z
			local function flightOf(g: number): (number, number)
				return if g % 2 == 0 then lane.x else lane.x + lane.w, if g % 2 == 0 then 1 else -1
			end
			-- the building CLAIMS its own sizes (like stairs do): every floor's clear ceiling, the door, the stair
			-- flight - kit world check holds them to the rig's sheet when the world names one (window sills are not
			-- claimed: a high sill is a choice, not a misfit)
			local label = spec.name or "building"
			for f = 0, floors - 1 do
				-- under the next floor's 1-stud slab: fh - 1 clear; the top floor has the whole fh under its flat roof
				-- (which sits on top of the walls), and no ceiling at all under a gable (open to the ridge)
				local top = f == floors - 1
				if not (top and spec.roof == "gable") then
					local clear = if top then fh else fh - 1
					table.insert(fits, {
						kind = "ceiling",
						name = `{label} floor {f + 1}`,
						size = { s[1] - 2 * t, clear, s[2] - 2 * t },
						pos = { c[1], c[2] + f * fh + clear / 2, c[3] },
						path = path,
					})
				end
			end
			if type(spec.door) == "table" then
				local dz = if spec.door.side == "N" then -s[2] / 2 elseif spec.door.side == "S" then s[2] / 2 else 0
				local dx = if spec.door.side == "W" then -s[1] / 2 elseif spec.door.side == "E" then s[1] / 2 else 0
				table.insert(fits, {
					kind = "opening",
					name = `{label} door`,
					size = { spec.door.width or 6, spec.door.height or 8.5, t },
					pos = { c[1] + dx, c[2], c[3] + dz },
					path = path,
				})
			end
			if spec.stairs == true then
				table.insert(fits, {
					kind = "step",
					name = `{label} stairs`,
					rise = fh / math.ceil(fh),
					run = lane.run,
					width = lane.w,
					pos = { lane.x, c[2], lane.z0 },
					path = path,
				})
			end
			local holeLen = math.min(flight, (6 / (fh / math.ceil(fh))) * lane.run + 2)
			-- below: the flight that comes up through this slab (its number: the floor it starts on)
			-- lift: the ground floor's boards stand that much over the storey line, the slab's foot where it was (a house's
			-- plinth or the ground's cut meets it with no slit)
			local function slabWithHole(y: number, hole: boolean, below: number?, lift: number?)
				local slabMat = spec.slab or spec.mat
				local x0, x1 = c[1] - s[1] / 2, c[1] + s[1] / 2
				local z0, z1 = c[3] - s[2] / 2, c[3] + s[2] / 2
				if not hole then
					local up = lift or 0
					add(
						path,
						{ name = "Slab", mat = slabMat },
						{ s[1], 1 + up, s[2] },
						{ c[1], y - 0.5 + up / 2, c[3] }
					)
					return
				end
				-- the stairwell: over the TOP end of the flight below, in that flight's own lane
				local fx, dir = flightOf(below or 0)
				local lx0, lx1 = fx - lane.w / 2, fx + lane.w / 2
				local hz0, hz1 = lane.z0 + flight - holeLen, lane.z0 + flight
				if dir < 0 then
					hz0, hz1 = lane.z0, lane.z0 + holeLen
				end
				local function piece(ax: number, bx: number, az: number, bz: number)
					if bx - ax > 0.05 and bz - az > 0.05 then
						add(
							path,
							{ name = "Slab", mat = slabMat },
							{ bx - ax, 1, bz - az },
							{ (ax + bx) / 2, y - 0.5, (az + bz) / 2 }
						)
					end
				end
				piece(x0, lx0, z0, z1) -- west of the stairwell
				piece(lx1, x1, z0, z1) -- east of it
				piece(lx0, lx1, z0, hz0) -- the lane before the hole
				piece(lx0, lx1, hz1, z1) -- the lane after it
			end
			for f = 0, floors - 1 do
				local openings = {}
				for _, side in { "N", "E", "S", "W" } do
					local len = if side == "N" or side == "S" then s[1] else s[2]
					local n = math.floor((len - 4) / (win.every or 10))
					for k = 1, n do
						local at = -len / 2 + (k - 0.5) * len / n
						local isDoor = f == 0 and spec.door and spec.door.side == side and k == math.ceil(n / 2)
						local noWin = type(win.sides) == "table" and not table.find(win.sides, side)
						if not isDoor and noWin then
							continue
						end
						if isDoor then
							table.insert(
								openings,
								{ side = side, at = at, width = spec.door.width or 6, height = spec.door.height or 8.5 }
							)
						else
							table.insert(openings, {
								side = side,
								at = at,
								width = win.width or 4,
								height = (win.sill or 3.5) + (win.height or 5),
								sill = win.sill or 3.5,
							})
						end
					end
				end
				local y = c[2] + f * fh
				local hw, hd = s[1] / 2, s[2] / 2
				local sides = {
					N = { { c[1] - hw, c[3] - hd }, { c[1] + hw, c[3] - hd }, s[1] },
					E = { { c[1] + hw, c[3] - hd }, { c[1] + hw, c[3] + hd }, s[2] },
					S = { { c[1] + hw, c[3] + hd }, { c[1] - hw, c[3] + hd }, s[1] },
					W = { { c[1] - hw, c[3] + hd }, { c[1] - hw, c[3] - hd }, s[2] },
				}
				for _, side in { "N", "E", "S", "W" } do
					local sd = sides[side]
					local gaps = {}
					for _, o in openings do
						if o.side == side then
							table.insert(
								gaps,
								{ at = sd[3] / 2 + o.at, width = o.width, height = o.height, sill = o.sill }
							)
						end
					end
					buildWall(`{path}.floor{f + 1}.{side}`, {
						from = sd[1],
						to = sd[2],
						y = y,
						height = fh,
						thickness = t,
						mat = spec.mat,
						gaps = gaps,
						hidden = dressed,
					})
					local ax, az = sd[2][1] - sd[1][1], sd[2][2] - sd[1][2]
					local alen = math.sqrt(ax * ax + az * az)
					if facade then
						-- this storey's wall in modules, split on the very gaps the wall was cut with; the oriel (if
						-- this house wears one) is the middle window of the first upper storey over the door
						-- (a module's own front is its +Z, as a skin's is; the wall's own +Z is the house's inside:
						-- a half turn sets the module's face to the street)
						local wyaw = math.deg(math.atan2(-az, ax)) + 180
						table.sort(gaps, function(g1, g2)
							return g1.at < g2.at
						end)
						local oriel = nil
						if facadeOriel and f == 1 and spec.door and spec.door.side == side and #gaps > 0 then
							oriel = math.ceil(#gaps / 2)
						end
						for _, piece in Facade.wall(alen, gaps, { window = facadeWin, oriel = oriel }) do
							local name = Facade.name(facade, piece.kind, fh)
							local own = meshReg[name].box or meshReg[name].size
							placeModule(
								`{path}.floor{f + 1}.{side}`,
								name,
								sd[1][1] + ax / alen * piece.at,
								y,
								sd[1][2] + az / alen * piece.at,
								wyaw,
								piece.width / own[1],
								fh / own[2],
								1,
								spec.mat
							)
						end
						-- the kit's QUOIN (optional, Facade.EXTRA): up the corner at this wall's END, on the outer
						-- edge the wall modules leave open (they meet on the centre lines), turned as the wall's
						-- modules are (its long blocks back along this wall, its return along the next one) - unless
						-- an opening on either face starts inside its reach
						local qname = Facade.name(facade, "quoin", fh)
						local qreg, wreg = meshReg[qname], meshReg[Facade.name(facade, "wall", fh)]
						if
							type(qreg) == "table"
							and qreg.module == "quoin"
							and type(qreg.floorHeight) == "number"
							and math.abs(qreg.floorHeight - fh) <= 0.05
							and type(wreg) == "table"
						then
							local nxt = ({ N = "E", E = "S", S = "W", W = "N" })[side]
							local clear = true
							for _, g in gaps do
								if alen - (g.at + g.width / 2) < Facade.QUOIN_REACH then
									clear = false
								end
							end
							for _, o in openings do
								if o.side == nxt and sides[nxt][3] / 2 + o.at - o.width / 2 < Facade.QUOIN_REACH then
									clear = false
								end
							end
							if clear then
								local half = (wreg.box or wreg.size)[3] / 2 -- (the wall module's own half-thickness)
								local ux, uz = ax / alen, az / alen
								local nx, nz = uz, -ux
								if nx * (sd[1][1] - c[1]) + nz * (sd[1][2] - c[3]) < 0 then
									nx, nz = -nx, -nz
								end
								placeModule(
									`{path}.floor{f + 1}.{side}`,
									qname,
									sd[2][1] + (ux + nx) * half,
									y,
									sd[2][2] + (uz + nz) * half,
									wyaw,
									1,
									1,
									1,
									spec.mat
								)
							end
						end
						if f > 0 then
							local name = Facade.name(facade, "band")
							local own = meshReg[name].box or meshReg[name].size
							for _, piece in Facade.band(alen) do
								placeModule(
									`{path}.floor{f + 1}.{side}`,
									name,
									sd[1][1] + ax / alen * piece.at,
									y,
									sd[1][2] + az / alen * piece.at,
									wyaw,
									piece.width / own[1],
									1,
									1,
									spec.mat
								)
							end
						end
					end
					-- "glass": a pane in every window (Neon = lit at night, Glass = glazed)
					if spec.glass then
						for _, g in gaps do
							if (g.sill or 0) > 0 then
								local along = g.at / alen
								add(
									path,
									{ name = "Pane", mat = spec.glass, collide = false, sink = false },
									{ g.width, g.height or 4, 0.2 },
									{ sd[1][1] + ax * along, y + g.sill + (g.height or 4) / 2, sd[1][2] + az * along },
									World.rotation({ 0, math.deg(math.atan2(-az, ax)), 0 })
								)
							end
						end
					end
					-- "trim": a band along the floor line, standing proud of the wall (a cornice, a timber sill)
					if spec.trim and f > 0 and not dressed then -- (not at the foot: on a slope it would sink into the land)
						local ox, oz = -az / alen * (t / 2 + 0.3), ax / alen * (t / 2 + 0.3)
						add(path, { name = "Band", mat = spec.trim, sink = false }, { alen + t + 0.6, 0.7, 0.6 }, {
							(sd[1][1] + sd[2][1]) / 2 - ox,
							y + 0.35,
							(sd[1][2] + sd[2][2]) / 2 - oz,
						}, World.rotation({ 0, math.deg(math.atan2(-az, ax)), 0 }))
					end
				end
				-- the slab under this floor: whole, or with the stairwell of the flight below cut out
				slabWithHole(y, f > 0 and spec.stairs == true, f - 1, if f == 0 then World.GROUND_LIFT else 0)
				if spec.stairs == true and (f < floors - 1 or spec.roof ~= "gable") then
					-- a flight by the west wall, solid steps of <= 1 stud: even floors climb +Z (north -> south) in the
					-- first lane, odd floors come back -Z in the second
					local steps = math.ceil(fh / 1)
					local rise = fh / steps
					local fx, dir = flightOf(f)
					for k = 1, steps do
						local h = rise * k
						add(path, { name = "Stair", mat = spec.slab or spec.mat }, { lane.w, h, lane.run }, {
							fx,
							y + h / 2,
							if dir > 0 then lane.z0 + (k - 0.5) * lane.run else lane.z0 + flight - (k - 0.5) * lane.run,
						})
					end
				end
				-- "rooms": true | { least, depth, door, mat } - the floor is cut into ROOMS by rule (kit/lib/worldrooms.luau):
				-- partition walls under the slab above, one doorway each, every room reached from every other; with
				-- "stairs" the strip the flight runs in (the west side) is a stair hall no partition crosses
				if spec.rooms ~= nil and spec.rooms ~= false and spec.rooms ~= true and type(spec.rooms) ~= "table" then
					-- (a word that means "no" must not turn rooms ON: "no", 0 and "false" each built 18 partitions)
					if f == 0 then
						err(
							path .. ".rooms",
							`"rooms" is true, false or \{ "least", "depth", "door", "mat", "seed" } (got {tostring(
								spec.rooms
							)})`
						)
					end
				elseif spec.rooms == true or type(spec.rooms) == "table" then
					local ro = if type(spec.rooms) == "table" then spec.rooms else {}
					if f == 0 and ro.door ~= nil and (type(ro.door) ~= "number" or ro.door < 4.5) then
						err(
							path .. ".rooms.door",
							`a room's doorway is at least 4.5 studs wide (the rig's sheet; got {tostring(ro.door)})`
						)
					end
					local iw, id = s[1] - t, s[2] - t -- (inside the outer walls, which are centred on the footprint)
					local seed = 0
					for ch in string.gmatch(label, ".") do
						seed = (seed * 31 + string.byte(ch)) % 1000003
					end
					-- this floor's door and windows, by the side of the floor they are on (a wall's own run starts at:
					-- N the west corner, E the north, S the EAST, W the SOUTH): no partition ends in one
					local keep = {}
					for _, o in openings do
						local len = if o.side == "N" or o.side == "S" then s[1] else s[2]
						local along = len / 2 + o.at -- (from the wall's start corner, on the footprint)
						if o.side == "S" or o.side == "W" then
							along = len - along
						end
						table.insert(keep, {
							side = if o.side == "N"
								then "z0"
								elseif o.side == "S" then "z1"
								elseif o.side == "W" then "x0"
								else "x1",
							at = along - t / 2,
							width = o.width,
						})
					end
					local floorPlan = Rooms.plan(iw, id, {
						least = ro.least,
						depth = ro.depth,
						door = ro.door,
						-- (the flight runs lane.w wide from the wall's inner face, which stands half a wall inside the
						-- floor's edge; the hall is the flight and a body's width beside it, whatever the wall's thickness)
						hall = if spec.stairs == true then t / 2 + lane.w * (if twoLanes then 2 else 1) + 2 else 0,
						seed = (if type(ro.seed) == "number" then ro.seed else seed) + f * 7919,
						keep = keep,
					})
					local ox, oz = c[1] - iw / 2, c[3] - id / 2
					-- (under the next floor's 1-stud slab; the top floor's walls reach the roof, flat or gabled)
					local wallTop = if f == floors - 1 then fh else fh - 1
					for wi, wall in floorPlan.walls do
						local from, to
						if wall.axis == "z" then
							from, to = { ox + wall.at, oz + wall.from }, { ox + wall.at, oz + wall.to }
						else
							from, to = { ox + wall.from, oz + wall.at }, { ox + wall.to, oz + wall.at }
						end
						buildWall(`{path}.floor{f + 1}.room{wi}`, {
							from = from,
							to = to,
							y = y,
							height = wallTop,
							thickness = Rooms.DEFAULTS.thickness,
							mat = ro.mat or spec.mat,
							gaps = {
								{
									at = wall.door - wall.from,
									width = wall.doorWidth,
									height = Rooms.DEFAULTS.doorHeight,
								},
							},
						})
						local mid = if wall.axis == "z"
							then { ox + wall.at, y, oz + wall.door }
							else { ox + wall.door, y, oz + wall.at }
						table.insert(fits, {
							kind = "opening",
							name = `{label} floor {f + 1} room door {wi}`,
							size = { wall.doorWidth, Rooms.DEFAULTS.doorHeight, Rooms.DEFAULTS.thickness },
							pos = mid,
							path = path,
						})
					end
					if type(spec.interior) == "table" and spec.interior.byRoom == true then
						-- interior_v2: every room of the split furnished on its own (furnishRooms)
						furnishRooms(
							spec,
							path,
							f,
							floors,
							if f == 0 then y + World.GROUND_LIFT else y,
							fh,
							t,
							lane,
							flight,
							openings,
							sides,
							floorPlan,
							ox,
							oz
						)
					elseif spec.interior and f == 0 then
						warn(
							path .. ".rooms",
							'"interior" furniture is set out for one room a floor: with "rooms" it is left out (furniture by room is not built yet here: "interior": { "byRoom": true } builds it)'
						)
					end
				end
				-- "interior": furnished rooms by rules (kit/lib/interior.luau): a hall below, chambers / stores above
				if spec.interior and (spec.rooms == nil or spec.rooms == false) then
					furnish(
						spec,
						path,
						f,
						if f == 0 then y + World.GROUND_LIFT else y,
						fh,
						t,
						lane,
						flight,
						openings,
						sides
					)
				end
			end
			local top = c[2] + floors * fh
			if spec.trim and not dressed then -- corner posts the full height (a timber frame, stone quoins)
				for _, cxz in { { -1, -1 }, { 1, -1 }, { 1, 1 }, { -1, 1 } } do
					add(path, { name = "Post", mat = spec.trim }, { t + 0.8, top - c[2], t + 0.8 }, {
						c[1] + cxz[1] * s[1] / 2,
						c[2] + (top - c[2]) / 2,
						c[3] + cxz[2] * s[2] / 2,
					})
				end
			end
			-- a facade's roof, laid out first: the roof you bump into (below) is then the roof you see - its ridge the
			-- module's ridge, its height the module's (a fresh reader: the hidden roof's ridge ran along X whatever
			-- the house, across the seen roof's on half the houses, and stood under half as high)
			local facadeRoof: any = nil
			if facade and spec.roof == "gable" then
				local alongX = skinYaw == 0 or skinYaw == 180
				local roofReg = meshReg[Facade.name(facade, "roof")]
				local own = roofReg.box or roofReg.size
				local lay =
					Facade.roof((if alongX then s[1] else s[2]) + 2 * t, (if alongX then s[2] else s[1]) + 2 * t, own)
				local yaw = skinYaw + (if lay.turned then 90 else 0)
				facadeRoof = { lay = lay, yaw = yaw, own = own, rise = own[2] * lay.scale, ridgeX = yaw % 180 == 90 }
			end
			if spec.roof == "gable" then
				local rise = if facadeRoof then facadeRoof.rise else math.min(s[1], s[2]) * 0.35
				if facadeRoof and not facadeRoof.ridgeX then
					-- two wedges back to back along Z (the ridge runs from the street to the yard)
					local half = s[1] / 2 + t
					for _, side in { -1, 1 } do
						add(path, {
							name = if side < 0 then "RoofN" else "RoofS",
							mat = spec.roofMat or spec.mat,
							shape = "Wedge",
							rot = { 0, if side < 0 then 90 else 270, 0 },
							collide = spec.roofCollide ~= false,
							transparency = 1,
						}, { s[2] + t * 2, rise, half }, { c[1] + side * half / 2, top + rise / 2, c[3] })
					end
				else
					-- two wedges back to back along X: each high at its back (+Z local) = the ridge in the middle
					local half = s[2] / 2 + t
					add(path, {
						name = "RoofN",
						mat = spec.roofMat or spec.mat,
						shape = "Wedge",
						collide = spec.roofCollide ~= false,
						transparency = if dressed then 1 else nil,
					}, { s[1] + t * 2, rise, half }, { c[1], top + rise / 2, c[3] - half / 2 })
					add(path, {
						name = "RoofS",
						mat = spec.roofMat or spec.mat,
						shape = "Wedge",
						rot = { 0, 180, 0 },
						collide = spec.roofCollide ~= false,
						transparency = if dressed then 1 else nil,
					}, { s[1] + t * 2, rise, half }, { c[1], top + rise / 2, c[3] + half / 2 })
				end
				if spec.trim and not dressed then -- the ridge beam
					add(
						path,
						{ name = "Ridge", mat = spec.trim, sink = false, collide = spec.roofCollide ~= false },
						{ s[1] + t * 2 + 1, 0.8, 0.8 },
						{ c[1], top + rise, c[3] }
					)
				end
			elseif spec.stairs == true then
				-- a flat roof you can climb onto: the last flight comes up through a hatch
				slabWithHole(top + 1, true, floors - 1)
			else
				add(
					path,
					-- (a facade has no flat-roof module: its flat roof stays the seen slab)
					{ name = "Roof", mat = spec.roofMat or spec.mat, transparency = if skin then 1 else nil },
					{ s[1] + t, 1, s[2] + t },
					{ c[1], top + 0.5, c[3] }
				)
			end
			if facadeRoof then
				-- the roof modules: the gable to the street (turned as a skin is) unless the rule turned it, grown to
				-- the house's front, end to end along the ridge, the height with the front (the module's own pitch)
				local name = Facade.name(facade :: string, "roof")
				local lay, roofYaw = facadeRoof.lay, facadeRoof.yaw
				local m = World.turnMatrix(roofYaw) -- (the module's own +X across the gable, +Z along its ridge)
				for _, tile in lay.tiles do
					placeModule(
						path,
						name,
						c[1] + m[1][3] * tile.at,
						top,
						c[3] + m[3][3] * tile.at,
						roofYaw,
						lay.scale,
						lay.scale,
						tile.stretch,
						spec.roofMat or spec.mat
					)
				end
				local seed = if type(spec.seed) == "number" then spec.seed else math.floor(c[1] * 7 + c[3] * 13)
				if Facade.chimney(seed) then
					-- a chimney on the roof's SLOPE: a quarter of the gable off the ridge (the roof is half its
					-- height there), a quarter of the ridge's length back, its foot half a stud into the slates on its
					-- DOWNHILL side (the roof falls its own pitch across the stack's half width: set at its middle the
					-- stack's lower face hung 0.9 studs over the slates, open underneath)
					local gable = facadeRoof.own[1] * lay.scale
					local ridge = (if facadeRoof.ridgeX then s[1] else s[2]) + 2 * t
					local u, v = gable / 4, -ridge / 4
					placeModule(
						path,
						Facade.name(facade :: string, "chimney"),
						c[1] + m[1][1] * u + m[1][3] * v,
						top
							+ facadeRoof.rise / 2
							- 0.5
							- (facadeRoof.own[2] / (facadeRoof.own[1] / 2))
								* meshReg[Facade.name(facade :: string, "chimney")].size[1]
								/ 2,
						c[3] + m[3][1] * u + m[3][3] * v,
						roofYaw,
						1,
						1,
						1,
						spec.mat
					)
				end
			end
			if skin then -- the look: the mesh on the building's footprint, turned to face its door, at its own size
				placeMesh(path, skin, c[1], c[2], c[3], meshReg[skin].size[2], skinYaw, false, spec.mat)
				-- ITS CORNER QUOINS (LIMITATIONS_FIXES_V3.md stage B.1: "corner quoins as instanced strips - never
				-- stripped"): the skin names a strip (kit world meshes kind gothic_quoin: one storey of one corner) and it
				-- stands at every corner of every storey - one mesh, placed many times. A strip that is not made is said:
				-- the house is never quietly built without them.
				local q = meshReg[skin].quoins
				if type(q) == "string" then
					if type(meshReg[q]) ~= "table" or type(meshReg[q].quoin) ~= "table" then
						err(
							path .. ".skin",
							`the skin "{skin}" wears corner quoins "{q}" and they are not made - make them: lune run kit world meshes`
						)
					else
						-- (the corners of the skin's outer faces, World.QUOIN_OUT out from the building's box; the strip
						-- is made for the south-west corner and turned for the others)
						local hx, hz = s[1] / 2 + World.QUOIN_OUT, s[2] / 2 + World.QUOIN_OUT
						local rq = meshReg[q]
						local k = fh / math.max(rq.size[2], 0.01)
						local mid = {
							(rq.min[1] + rq.size[1] / 2) * k,
							(rq.min[2] + rq.size[2] / 2) * k,
							(rq.min[3] + rq.size[3] / 2) * k,
						}
						for f = 0, floors - 1 do
							for _, cn in { { -hx, hz, 0 }, { hx, hz, 90 }, { hx, -hz, 180 }, { -hx, -hz, 270 } } do
								local qp = placeMesh(
									path,
									q,
									c[1] + cn[1],
									c[2] + f * fh,
									c[3] + cn[2],
									fh,
									cn[3],
									false,
									spec.mat
								)
								if qp then
									table.insert(quoined, { part = qp, c = mid, owner = dressKey })
								end
							end
						end
					end
				end
			end
			dressKey = nil
		elseif kind == "mesh" then
			-- one world mesh (kit world meshes) at pos: { mesh, pos: [x, y, z], height? (its own), yaw?, collide?, mat? }
			local r = meshReg[spec.mesh or ""]
			if not r then
				err(path .. ".mesh", `no world mesh "{tostring(spec.mesh)}" — make it: lune run kit world meshes`)
			elseif
				r.scan
				and spec.height ~= nil
				and spec.resize ~= true
				and math.abs(spec.height / math.max(r.size[2], 0.01) - 1) > World.SCAN_SPREAD
			then
				err(
					path .. ".height",
					`"{spec.mesh}" is a scanned real thing, {string.format("%.1f", r.size[2])} studs tall ({r.scan.metres} m along its {r.scan.axis}): a height of {spec.height} is not its size - leave "height" out, or write "resize": true to change it on purpose`
				)
			else
				local p = spec.pos or { 0, 0, 0 }
				placeMesh(
					path,
					spec.mesh,
					p[1],
					p[2],
					p[3],
					spec.height or r.size[2],
					spec.yaw or 0,
					spec.collide == true,
					spec.mat,
					spec.resize == true
				)
				-- THINGS SET DOWN ON ITS SURFACE ("on": { "points", "part": { "size", "mat" }, "sink"?, "share"?,
				-- "seed"?, "turn"?, "collide"? }): one part on every point Geometry Nodes scattered over the mesh, its
				-- foot on the surface and its up along the surface's normal - moss on a cliff's ledges, ivy on a
				-- wall's face, barnacles under an arch. The points are the MESH'S (its own space): they are scaled
				-- and turned with it
				local on = spec.on
				if on ~= nil and on ~= false then
					local wrong: { string } = {}
					if type(on) ~= "table" then
						wrong = { ' is { "points": "<name>", "part": { "size": [x, y, z], "mat": "<palette>" } }' }
						on = {}
					end
					local known = {
						points = true,
						part = true,
						sink = true,
						share = true,
						seed = true,
						turn = true,
						collide = true,
					}
					for word in on do
						if not known[word] then
							table.insert(
								wrong,
								`.{tostring(word)} is not a word it knows (points, part, sink, share, seed, turn, collide)`
							)
						end
					end
					local function finite(v: any): boolean
						return type(v) == "number" and v == v and math.abs(v) ~= math.huge
					end
					local part = on.part
					local size = if type(part) == "table" then part.size else nil
					if
						type(size) ~= "table"
						or #size ~= 3
						or not (finite(size[1]) and finite(size[2]) and finite(size[3]))
						or math.min(size[1], size[2], size[3]) < 0.05
						or math.max(size[1], size[2], size[3]) > 64
						or type(part.mat) ~= "string"
					then
						table.insert(
							wrong,
							'.part is { "size": [x, y, z] (0.05 to 64 studs each; y stands along the surface\'s normal), "mat": a palette entry }'
						)
					end
					for word in if type(part) == "table" then part else {} do
						if word ~= "size" and word ~= "mat" then
							table.insert(wrong, `.part.{tostring(word)} is not a word a piece knows (size, mat)`)
						end
					end
					if type(on.points) ~= "string" or on.points == "" then
						table.insert(
							wrong,
							".points is the name the points were made as (kit world scatter-on <mesh> --as <name>)"
						)
					end
					if
						on.sink ~= nil
						and (
							not finite(on.sink)
							or on.sink < 0
							or (type(size) == "table" and finite(size[2]) and on.sink > size[2])
						)
					then
						table.insert(wrong, ".sink is how deep a piece sits in the surface, 0 to its own height")
					end
					if on.share ~= nil and (not finite(on.share) or on.share <= 0 or on.share > 1) then
						table.insert(wrong, ".share is the share of the points that take a piece, over 0 to 1")
					end
					if
						on.seed ~= nil and (not finite(on.seed) or on.seed % 1 ~= 0 or on.seed < 0 or on.seed > 65535)
					then
						table.insert(wrong, ".seed is a whole number 0 to 65535")
					end
					for _, word in { "turn", "collide" } do
						if on[word] ~= nil and type(on[word]) ~= "boolean" then
							table.insert(wrong, `.{word} is true or false`)
						end
					end
					if type(part) == "table" and type(part.mat) == "string" and type(palette[part.mat]) ~= "table" then
						-- (said once here: not once a point by every piece that would be made of it)
						table.insert(wrong, `.part.mat: unknown palette entry "{part.mat}"`)
					end
					if r.parts then
						table.insert(
							wrong,
							": this mesh is several meshes placed together (an imported asset); points are made on one mesh"
						)
					end
					for _, w in wrong do
						err(path .. ".on", `a mesh's "on"{w}`)
					end
					local data = if #wrong == 0 then pointsOn(spec.mesh, on.points) else nil
					if #wrong > 0 then
						data = nil
					elseif type(data) ~= "table" or type(data.points) ~= "table" then
						err(
							path .. ".on",
							`no points "{on.points}" on the mesh "{spec.mesh}" - make them: lune run kit world scatter-on {spec.mesh} --as {on.points} --gap 3 --facing up`
						)
						data = nil
					else
						-- THE POINTS ARE THIS BUILD'S OF THE MESH: the same count of triangles and the same box (a mesh
						-- made again is another surface; one made larger with as many triangles is too). Points that
						-- do not say both are not trusted
						local same = type(data.tris) == "number" and data.tris == r.tris
						local boxed = type(data.min) == "table" and type(data.size) == "table"
						for k = 1, 3 do
							same = same
								and boxed
								and finite(data.min[k])
								and finite(data.size[k])
								and math.abs(data.min[k] - r.min[k]) <= 0.01
								and math.abs(data.size[k] - r.size[k]) <= 0.01
						end
						local listed = 0
						for _ in data.points do
							listed += 1
						end
						if not same then
							err(
								path .. ".on",
								`the points "{on.points}" were made on another build of "{spec.mesh}" (they say {tostring(
									data.tris
								)} triangles in a box of {if boxed
									then table.concat(data.size, " x ")
									else "no size"}; the mesh has {tostring(r.tris)} in {table.concat(
									r.size,
									" x "
								)}) - make them again: lune run kit world scatter-on {spec.mesh} --as {on.points} ...`
							)
							data = nil
						elseif listed ~= #data.points or listed == 0 then
							err(path .. ".on", `the points "{on.points}" are no list of points`)
							data = nil
						elseif #data.points > 4000 then
							err(path .. ".on", `{#data.points} points: over 4000 pieces on one mesh`)
							data = nil
						end
					end
					-- (every point is looked at before any piece is set down: half a scatter is not built)
					for at, q in if data then data.points else {} do
						local pos, n =
							if type(q) == "table" then q.pos else nil, if type(q) == "table" then q.normal else nil
						if
							type(pos) ~= "table"
							or type(n) ~= "table"
							or not (finite(pos[1]) and finite(pos[2]) and finite(pos[3]))
							or not (finite(n[1]) and finite(n[2]) and finite(n[3]))
							or n[1] ^ 2 + n[2] ^ 2 + n[3] ^ 2 < 1e-6
						then
							err(
								path .. ".on",
								`point {at} of "{on.points}" is not \{ "pos": [x, y, z], "normal": [x, y, z] }`
							)
							data = nil
							break
						end
						-- (a point is ON the mesh: inside its box, to half a stud)
						local inside = true
						for k = 1, 3 do
							inside = inside and pos[k] >= r.min[k] - 0.5 and pos[k] <= r.min[k] + r.size[k] + 0.5
						end
						if not inside then
							err(path .. ".on", `point {at} of "{on.points}" lies outside the mesh "{spec.mesh}"`)
							data = nil
							break
						end
					end
					if data then
						local k = (spec.height or r.size[2]) / math.max(r.size[2], 0.01)
						local a = math.rad(spec.yaw or 0)
						local ca, sa = math.cos(a), math.sin(a)
						local rnd = lcg(on.seed or 1)
						local sink = on.sink or 0
						local placed = 0
						for _, q in data.points do
							local keep, spin = rnd(), rnd() -- (drawn for every point: a share keeps the others where they are)
							local pos, n = q.pos, q.normal
							if keep < (on.share or 1) then
								-- the point and its normal, scaled and turned with the mesh
								local wx = p[1] + (pos[1] * ca + pos[3] * sa) * k
								local wy = p[2] + pos[2] * k
								local wz = p[3] + (-pos[1] * sa + pos[3] * ca) * k
								local len = math.sqrt(n[1] ^ 2 + n[2] ^ 2 + n[3] ^ 2)
								local nx, ny, nz =
									(n[1] * ca + n[3] * sa) / len, n[2] / len, (-n[1] * sa + n[3] * ca) / len
								-- a side way u across the normal (level where the surface is not), turned about the normal
								-- by chance; w = u x n: the piece's X, Y, Z are u, n, w
								local ux, uy, uz = nz, 0, -nx -- (up x n)
								local ul = math.sqrt(ux * ux + uz * uz)
								if ul < 1e-6 then
									ux, uy, uz = 1, 0, 0
								else
									ux, uz = ux / ul, uz / ul
								end
								if on.turn ~= false then
									local t = spin * 2 * math.pi
									-- (n x u, the other side way)
									local vx, vy, vz = ny * uz - nz * uy, nz * ux - nx * uz, nx * uy - ny * ux
									ux, uy, uz =
										ux * math.cos(t) + vx * math.sin(t),
										uy * math.cos(t) + vy * math.sin(t),
										uz * math.cos(t) + vz * math.sin(t)
								end
								local wwx, wwy, wwz = uy * nz - uz * ny, uz * nx - ux * nz, ux * ny - uy * nx
								local lift = size[2] / 2 - sink
								local piece = add(
									path,
									{ name = "On", mat = part.mat, collide = on.collide == true, sink = false },
									{ size[1], size[2], size[3] },
									{ wx + nx * lift, wy + ny * lift, wz + nz * lift },
									{ { ux, nx, wwx }, { uy, ny, wwy }, { uz, nz, wwz } }
								)
								if piece then
									placed += 1
								end
							end
						end
						table.insert(onMeshes, {
							name = spec.name or path,
							mesh = spec.mesh,
							points = #data.points,
							placed = placed,
							gap = if finite(data.gap) then data.gap * k else nil,
						})
					end
				end
			end
		elseif kind == "tree" then
			if spec.mesh then -- a real mesh tree (+ an invisible trunk to bump into)
				local p, H = spec.pos or { 0, 0, 0 }, spec.height or 30
				dressBegin(path) -- (its unseen trunk is shown while its mesh is not there)
				placeMesh(path, spec.mesh, p[1], p[2], p[3], H, spec.yaw or 0, false, spec.leaves or spec.trunk)
				add(
					path,
					{ name = "TrunkCollider", mat = spec.trunk, shape = "Cylinder", transparency = 1, sink = false },
					{
						H * 0.6,
						H * 0.07,
						H * 0.07,
					},
					{ p[1], p[2] + H * 0.3, p[3] },
					World.rotation({ 0, 0, 90 })
				)
			else
				buildTree(path, spec)
			end
		elseif kind == "forest" then
			-- { center: [x, y, z], area: [w, d], count, seed, styles?: ["oak", "dead"], height?: [lo, hi], trunk, leaves,
			--   leavesAlt?: a second canopy material (autumn), ground: true, slopeMax?, avoid?, gap? } — trees on the terrain
			if spec.seed ~= nil and type(spec.seed) ~= "number" then
				err(path .. ".seed", `a forest's "seed" is a number`) -- (it crashed the compile)
				continue
			end
			local rnd = lcg(spec.seed or 1)
			local c, area = spec.center, spec.area or { 100, 100 }
			local styles = spec.styles or { "oak" }
			local hr = spec.height or { 18, 30 }
			if type(hr) ~= "table" or type(hr[1]) ~= "number" or type(hr[2]) ~= "number" then
				err(path .. ".height", 'a forest\'s "height" is [lowest, tallest] in studs')
				continue
			end
			-- one tree at (x, z) on the ground gy, H studs tall (a grown forest says each tree's style or meshes)
			local function plant(x: number, z: number, gy: number, H: number, style: string?, meshes: { string }?)
				local meshList = meshes or (if style then nil else spec.meshes)
				local leaves = spec.leaves
				if spec.leavesAlt and rnd() < (spec.altShare or 0.3) then
					leaves = spec.leavesAlt
				end
				if meshList then -- real mesh trees, one of the list each (on THIS tree's ground, no step lift)
					stepGround = nil
					local mname = meshList[math.floor(rnd() * #meshList) + 1]
					dressBegin(path) -- (each tree its own: one missing mesh shows that tree's trunk only)
					placeMesh(path, mname, x, gy + c[2], z, H, rnd() * 360, false, spec.leaves or spec.trunk)
					add(path, {
						name = "TrunkCollider",
						mat = spec.trunk,
						shape = "Cylinder",
						transparency = 1,
						sink = false,
					}, {
						H * 0.6,
						H * 0.06,
						H * 0.06,
					}, { x, gy + c[2] + H * 0.3, z }, World.rotation({ 0, 0, 90 }))
					return
				end
				stepGround = { dy = gy, sink = 0 }
				buildTree(path, {
					pos = { x, c[2] - 0.5, z },
					height = H,
					style = style or styles[math.floor(rnd() * #styles) + 1],
					seed = math.floor(rnd() * 1e6),
					trunk = spec.trunk,
					leaves = leaves,
					snow = spec.snow,
				})
				stepGround = nil
			end
			-- GROWN ("ecosystem": { "years", "species": [...] }: kit/lib/worldecosystem.luau): the trees come up, grow,
			-- shade each other out, seed and die for that many years; which kind stands where, how old and how tall
			-- comes out of it
			if spec.ecosystem ~= nil and spec.ecosystem ~= false then
				local wrong = Eco.problems(spec.ecosystem)
				for _, p in wrong do
					err(path .. ".ecosystem", p)
				end
				local beside = false
				for _, word in { "count", "density", "gap", "height", "styles", "meshes" } do
					if spec[word] ~= nil and spec[word] ~= false then
						beside = true
						err(
							path .. "." .. word,
							`a forest with an "ecosystem" has no "{word}": how many trees there are, how tall and of which kind comes out of its years (a kind says its own "height", "style" or "meshes")`
						)
					end
				end
				if
					type(area) ~= "table"
					or type(area[1]) ~= "number"
					or type(area[2]) ~= "number"
					or not (area[1] >= 8 and area[1] <= 4000 and area[2] >= 8 and area[2] <= 4000)
				then
					err(path .. ".area", 'a grown forest\'s "area" is [width, depth], 8 to 4000 studs each way')
					beside = true
				end
				if
					spec.seed ~= nil
					and (type(spec.seed) ~= "number" or spec.seed % 1 ~= 0 or spec.seed < 0 or spec.seed > 65535)
				then
					err(path .. ".seed", 'a grown forest\'s "seed" is a whole number 0 to 65535')
					beside = true
				end
				if #wrong > 0 or beside then
					continue
				end
				local grown = Eco.run(spec.ecosystem, area, spec.seed or 1, function(x: number, z: number): boolean
					return (terrainSite(spec, c[1] + x, c[3] + z))
				end)
				if grown.full then
					err(
						path .. ".ecosystem",
						`this forest fills up: over {Eco.MOST} plants alive at once - wider crowns, fewer seeds or a smaller area`
					)
					continue
				elseif #grown.plants == 0 then
					err(
						path .. ".ecosystem",
						`nothing stands after {grown.years} years: every kind died out (a kind lives its "life" and must seed before it) or no seedling found a place`
					)
					continue
				end
				if grown.first.set < grown.first.asked then
					warn(
						path .. ".ecosystem",
						`only {grown.first.set} of the {grown.first.asked} first seedlings found a place: the area is small for them, or little of it is where a tree may stand`
					)
				end
				local stand: { [string]: number } = {}
				for _, k in spec.ecosystem.species do
					stand[k.name] = 0
				end
				for _, p in grown.plants do
					local k = spec.ecosystem.species[p.kind]
					stand[k.name] += 1
					local _, gy = terrainSite(spec, c[1] + p.x, c[3] + p.z)
					plant(c[1] + p.x, c[3] + p.z, gy, p.height, if k.meshes then nil else (k.style or "oak"), k.meshes)
				end
				table.insert(ecosystems, {
					name = spec.name or path,
					trees = #grown.plants,
					stand = stand,
					years = grown.years,
					first = grown.first,
					census = grown.census,
					dead = grown.dead,
				})
				-- (no `continue` here: the step's group is made after this chain)
			elseif spec.density ~= nil and spec.density ~= false then
				local wrong = Scatter.problems(spec.density)
				for _, p in wrong do
					err(path .. ".density", p)
				end
				if spec.count ~= nil then
					err(
						path .. ".count",
						'a forest with a "density" has no "count": how many trees there are comes out of the gap and the field'
					)
				end
				if spec.gap ~= nil then
					err(
						path .. ".gap",
						'a forest with a "density" says its gap there ("density": { "gap" }), not beside it'
					)
				end
				if #wrong > 0 or spec.count ~= nil or spec.gap ~= nil then
					continue
				end
				-- two trees at the least gap stand as far apart as two of the tallest do by a count: a crown reaches
				-- about a quarter of its tree's height, and a count keeps 2 studs round each (half the tallest + 4)
				local tallest = math.max(hr[1], hr[2])
				local least = tallest * 0.5 + 4
				if spec.density.gap < least - 1e-9 then
					err(
						path .. ".density.gap",
						`the gap ({spec.density.gap}) is under what two of the tallest trees need ({tallest} studs tall: half of it and 4, {least}): two crowns at the least gap would stand in each other`
					)
					continue
				end
				local pts, how = Scatter.sample(
					{ c[1], c[3], area[1], area[2] },
					spec.density,
					rnd,
					function(x: number, z: number): boolean
						return (terrainSite(spec, x, z))
					end
				)
				if how == "over" then
					err(
						path .. ".density",
						`this density comes to over {Scatter.MOST} trees: widen the gap, thin the field or make the area smaller`
					)
					continue
				elseif #pts == 0 then
					err(path .. ".density", "this density places nothing: the field is 0 wherever a tree may stand")
					continue
				elseif how == "short" then
					warn(
						path .. ".density",
						`this forest was cut short at {#pts} trees: nearly all of its area is where nothing may stand ({Scatter.TRIES} tries) - make the "area" the place the trees are meant for`
					)
				end
				for _, q in pts do
					local _, gy = terrainSite(spec, q[1], q[2])
					plant(q[1], q[2], gy, hr[1] + (hr[2] - hr[1]) * rnd())
				end
				-- (no `continue` here: the step's group is made after this chain)
			else
				local placed, tries = {}, 0
				local count = spec.count or 10
				while #placed < count and tries < count * 40 do
					tries += 1
					local x = c[1] + (rnd() - 0.5) * area[1]
					local z = c[3] + (rnd() - 0.5) * area[2]
					local H = hr[1] + (hr[2] - hr[1]) * rnd()
					local radius = H * 0.25 + (spec.gap or 2)
					local free = true
					for _, q in placed do
						if (q[1] - x) ^ 2 + (q[2] - z) ^ 2 < (q[3] + radius) ^ 2 then
							free = false
							break
						end
					end
					local okSite, gy = terrainSite(spec, x, z)
					if free and okSite then
						table.insert(placed, { x, z, radius })
						plant(x, z, gy, H)
					end
				end
				if #placed < count then
					warn(path, `forest placed {#placed}/{count} — enlarge the area, relax slopeMax or the gap`)
				end
			end
		elseif kind == "ruin" then
			-- { center: [x, y, z], size: [w, d], height, thickness, mat, decay: 0..1, seed, chunk?: studs,
			--   openings?: like room, columns?: { count, radius, height, mat }, rubble?: { count, mat } }
			-- broken walls (chunks missing, tops jagged), broken + fallen columns, rubble where it fell
			local rnd = lcg(spec.seed or 1)
			local c, s = spec.center, spec.size
			local h, t = spec.height or 10, spec.thickness or 2
			local decay = spec.decay or 0.5
			local chunk = spec.chunk or 3
			local hw, hd = s[1] / 2, s[2] / 2
			local sides = {
				N = { { c[1] - hw, c[3] - hd }, { c[1] + hw, c[3] - hd }, s[1] },
				E = { { c[1] + hw, c[3] - hd }, { c[1] + hw, c[3] + hd }, s[2] },
				S = { { c[1] + hw, c[3] + hd }, { c[1] - hw, c[3] + hd }, s[1] },
				W = { { c[1] - hw, c[3] + hd }, { c[1] - hw, c[3] - hd }, s[2] },
			}
			for _, side in { "N", "E", "S", "W" } do
				local sd = sides[side]
				local fx, fz = sd[1][1], sd[1][2]
				local dx, dz = (sd[2][1] - fx) / sd[3], (sd[2][2] - fz) / sd[3]
				local r = World.rotation({ 0, math.deg(math.atan2(-dz, dx)), 0 })
				local holes = {}
				for _, o in spec.openings or {} do
					if o.side == side then
						table.insert(holes, {
							sd[3] / 2 + (o.at or 0) - (o.width or 6) / 2,
							sd[3] / 2 + (o.at or 0) + (o.width or 6) / 2,
						})
					end
				end
				local along = 0
				while along < sd[3] - 0.01 do
					local w = math.min(chunk * (0.7 + rnd() * 0.6), sd[3] - along)
					local mid = along + w / 2
					local inHole = false
					for _, hl in holes do
						if mid > hl[1] and mid < hl[2] then
							inHole = true
						end
					end
					if not inHole and rnd() > decay * 0.35 then
						local hh = h * (1 - decay * rnd() ^ 1.4)
						add(path, { name = "RuinWall", mat = spec.mat }, { w, math.max(1, hh), t }, {
							fx + dx * mid,
							c[2] + math.max(1, hh) / 2,
							fz + dz * mid,
						}, r)
					end
					along += w
				end
			end
			local col = spec.columns
			if col then
				local n = col.count or 4
				for k = 1, n do
					-- a colonnade along the front (south) side, one stud in from the wall
					local x = c[1] - hw + (k - 0.5) * s[1] / n
					local z = c[3] + hd + (col.offset or 4)
					local ch = (col.height or h * 1.3) * (1 - decay * 0.8 * rnd())
					local cspec = { name = "Column", mat = col.mat or spec.mat }
					add(
						path,
						{ name = "Plinth", mat = col.mat or spec.mat },
						{ (col.radius or 1.4) * 2.8, 1, (col.radius or 1.4) * 2.8 },
						{ x, c[2] + 0.5, z }
					)
					if rnd() < decay * 0.5 then -- fallen: the shaft lies where it toppled
						local yaw = rnd() * math.pi * 2
						local L = col.height or h * 1.3
						between(
							path,
							cspec,
							{ x + math.cos(yaw) * 1.5, c[2] + (col.radius or 1.4), z + math.sin(yaw) * 1.5 },
							{
								x + math.cos(yaw) * (1.5 + L * 0.7),
								c[2] + (col.radius or 1.4),
								z + math.sin(yaw) * (1.5 + L * 0.7),
							},
							col.radius or 1.4
						)
					else
						between(path, cspec, { x, c[2] + 1, z }, { x, c[2] + 1 + ch, z }, col.radius or 1.4)
					end
				end
			end
			local rub = spec.rubble
			if rub then
				for _ = 1, rub.count or 12 do
					local ang = rnd() * math.pi * 2
					local rr = math.max(hw, hd) * (0.6 + rnd() * 0.7)
					local sz = 0.8 + rnd() * 2.4
					add(
						path,
						{
							name = "Rubble",
							mat = rub.mat or spec.mat,
							rot = { rnd() * 40, rnd() * 360, rnd() * 40 },
							sink = false,
						},
						{
							sz * (1 + rnd()),
							sz,
							sz * (0.8 + rnd()),
						},
						(function()
							local x, z = c[1] + math.cos(ang) * rr, c[3] + math.sin(ang) * rr
							local lift = stepGround and stepGround.dy or 0
							local land = if stepGround then (groundAt(x, z) or lift) - lift else 0
							return { x, c[2] + land + sz * 0.35, z }
						end)()
					)
				end
			end
		elseif kind == "tower" then
			-- { center: [x, y, z], radius, height, thickness, segments, mat, crenels?: true, roof?: "cone" | "flat",
			--   roofMat?, door?: { width, height, angle? (degrees, 0 = +X, 90 = +Z: the default) } } — a round keep tower
			--   with merlons and a pointed roof (a corner tower's door faces its courtyard, not the wall it joins)
			--   (roofCollide: false — a roof no one can reach is decoration: kit world check names unreachable roofs)
			local c, R, h = spec.center, spec.radius or 8, spec.height or 30
			local t, n = spec.thickness or 2, spec.segments or 16
			-- "mesh" / "roofMesh": a meshed tower (kit world meshes kind "tower", its door at local +X) + its slate roof;
			-- the segment ring stays as the tower's INSIDE (a mesh has no inner faces), the top, merlons and cone hide
			local hideTop = if spec.mesh then 1 else nil
			if spec.mesh then
				dressBegin(path) -- (its unseen top and merlons are shown while its mesh is not there)
			end
			local chord = 2 * (R + t / 2) * math.sin(math.pi / n)
			for k = 0, n - 1 do
				local a = (k + 0.5) * 2 * math.pi / n
				local yaw = -math.deg(a) - 90
				local rr = World.rotation({ 0, yaw, 0 })
				local px, pz = c[1] + math.cos(a) * R, c[3] + math.sin(a) * R
				-- the door: the segments within one segment's width of door.angle (degrees: 0 = +X, 90 = +Z, the default)
				local da = math.rad(if spec.door and type(spec.door.angle) == "number" then spec.door.angle else 90)
				local off = math.abs(((a - da + math.pi) % (2 * math.pi)) - math.pi)
				local door = spec.door and off < 2 * math.pi / n
				if door then
					local dh = spec.door.height or 9
					add(
						path,
						{ name = "TowerWall", mat = spec.mat },
						{ chord, h - dh, t },
						{ px, c[2] + dh + (h - dh) / 2, pz },
						rr
					)
				else
					add(path, { name = "TowerWall", mat = spec.mat }, { chord, h, t }, { px, c[2] + h / 2, pz }, rr)
				end
				if spec.crenels ~= false and k % 2 == 0 then
					add(
						path,
						{ name = "Merlon", mat = spec.mat, transparency = hideTop },
						{ chord, 2.5, t },
						{ px, c[2] + h + 1.25, pz },
						rr
					)
				end
			end
			add(path, {
				name = "TowerFloor",
				mat = spec.mat,
				shape = "Cylinder",
				rot = { 0, 0, 90 },
				-- (the top floor is the roof, or under a cone its underside: decoration with it)
				collide = spec.roofCollide ~= false,
				transparency = hideTop,
			}, { 1, R * 2, R * 2 }, { c[1], c[2] + h - 0.5, c[3] })
			if spec.mesh then
				local rt = meshReg[spec.mesh]
				if not rt then
					err(path .. ".mesh", `no world mesh "{spec.mesh}" — make it: lune run kit world meshes`)
				else
					-- the mesh's fighting top (meshTop studs) lands on the tower's top; its door (local +X) faces door.angle
					local kT = h / (spec.meshTop or 27.7)
					local doorAngle = if spec.door and type(spec.door.angle) == "number" then spec.door.angle else 0
					placeMesh(path, spec.mesh, c[1], c[2], c[3], rt.size[2] * kT, -doorAngle, false, spec.mat)
					local rr_ = spec.roofMesh and meshReg[spec.roofMesh]
					if spec.roofMesh and not rr_ then
						err(path .. ".roofMesh", `no world mesh "{spec.roofMesh}"`)
					elseif rr_ then
						placeMesh(
							path,
							spec.roofMesh,
							c[1],
							c[2] + (spec.meshRoofAt or 28) * kT,
							c[3],
							rr_.size[2] * kT,
							0,
							false,
							spec.roofMat or spec.mat
						)
					end
				end
			elseif spec.roof == "cone" then -- an eight-sided spire: four crossed prisms over a short eave ring
				local bw = (R + t) * 2.3
				add(path, {
					name = "Eave",
					mat = spec.roofMat or spec.mat,
					shape = "Cylinder",
					rot = { 0, 0, 90 },
					collide = spec.roofCollide ~= false,
				}, { 1, bw, bw }, { c[1], c[2] + h + 0.5, c[3] })
				for _, yaw in { 0, 45, 90, 135 } do
					prism(
						path,
						{ name = "Roof", mat = spec.roofMat or spec.mat, collide = spec.roofCollide ~= false },
						c[1],
						c[2] + h + 1,
						c[3],
						bw * 0.16,
						R * 2,
						bw,
						yaw
					)
				end
			end
		elseif kind == "bridge" then
			-- { from: [x, z], to: [x, z], y: deck top, width, thickness?, mat, arches?: n, pierDepth?, rails?: true }
			local fx, fz, tx, tz = spec.from[1], spec.from[2], spec.to[1], spec.to[2]
			local dx, dz = tx - fx, tz - fz
			local len = math.sqrt(dx * dx + dz * dz)
			local y, w, th = spec.y or 0, spec.width or 8, spec.thickness or 2
			local r = World.rotation({ 0, math.deg(math.atan2(-dz, dx)), 0 })
			local mx, mz = (fx + tx) / 2, (fz + tz) / 2
			add(path, { name = "Deck", mat = spec.mat, sink = false }, { len, th, w }, { mx, y - th / 2, mz }, r)
			local n = spec.arches or 3
			local depth = spec.pierDepth or 14
			for k = 0, n do
				local f = k / n
				local px, pz = fx + dx * f, fz + dz * f
				add(
					path,
					{ name = "Pier", mat = spec.mat, sink = false },
					{ 4, depth, w + 1 },
					{ px, y - th - depth / 2, pz },
					r
				)
			end
			for k = 0, n - 1 do -- each arch: three stepped blocks under the deck read as a curve from afar
				local span = len / n
				for j = 1, 3 do
					local f = (k + 0.5) / n
					local cx, cz = fx + dx * f, fz + dz * f
					local ww = span * (1 - j * 0.28)
					add(
						path,
						{ name = "Arch", mat = spec.mat, sink = false },
						{ ww, 1.2, w },
						{ cx, y - th - 1.2 * j + 0.6, cz },
						r
					)
				end
			end
			if spec.rails ~= false then
				-- the R6 rail: 3 studs over the deck (it was 2.2 - "a rail at the knee"); the bridge claims it for the sheet
				local railH = if type(spec.railHeight) == "number" then spec.railHeight else 3
				for _, side in { -1, 1 } do
					local ox, oz = -dz / len * side * (w / 2 - 0.5), dx / len * side * (w / 2 - 0.5)
					add(
						path,
						{ name = "Rail", mat = spec.mat, sink = false },
						{ len, railH, 1 },
						{ mx + ox, y + railH / 2, mz + oz },
						r
					)
				end
				table.insert(fits, {
					kind = "rail",
					name = `{spec.name or "bridge"} rails`,
					size = { len, railH, 1 },
					pos = { mx, y + railH / 2, mz },
					path = path,
				})
			end
		elseif kind == "grace" then
			-- a Site of Grace: a golden light hovering over the ground (light + rising motes), walk-through
			local p = spec.pos or { 0, 0, 0 }
			add(path, {
				name = spec.name or "Grace",
				mat = spec.mat,
				shape = "Ball",
				collide = false,
				transparency = 0.45,
				light = { color = { 255, 196, 92 }, range = 22, brightness = 2.5 },
				particles = "grace_motes",
			}, { 0.6, 0.6, 0.6 }, { p[1], p[2] + 1.6, p[3] }) -- (a small flicker, as in the source: a big neon ball blooms over the view)
			add(
				path,
				{ name = "GraceStone", mat = spec.stone or spec.mat, rot = { 0, 20, 0 } },
				{ 2.4, 0.8, 2 },
				{ p[1], p[2] + 0.4, p[3] }
			)
		elseif kind == "horizon" then
			-- { center?: [x, z], radius, count, height: [lo, hi], y?: base, mat, cap?: mat (snow on the crests), seed }
			-- distant ranges all round the map, so the world never ends in a void: backdrop ridges (never collide,
			-- not analysed). Each peak is 2-3 ridges (two wedges back to back), the tallest with a cap on its crest.
			local rnd = lcg(spec.seed or 1)
			local c = spec.center or { 0, 0 }
			local R = spec.radius or 1500
			local n = spec.count or 24
			local hl, hh = (spec.height or { 200, 500 })[1], (spec.height or { 200, 500 })[2]
			local y0 = spec.y or 0
			-- HLOD PROXIES (LIMITATIONS_FIXES_V3.md stage F.2: "batch far blocks into <= 2k-tri HLOD proxy clusters
			-- replacing the cardboard wedges"): "hlod": "<prefix>" names four proxy meshes, <prefix>_1 .. _4 (kit world
			-- meshes kind "hlod_ring": a quarter of the ring each, World.HLOD_TRIS at most). They DRESS the step: its
			-- wedges are still built, unseen, and the game shows them only while a proxy is not there (as a skin's walls)
			local proxies: { string }? = nil
			if spec.hlod ~= nil and not greybox then
				if type(spec.hlod) ~= "string" or spec.hlod == "" then
					err(path .. ".hlod", '"hlod" is the name its four proxies start with ("<name>_1" .. "<name>_4")')
				else
					local names, ok = {}, true
					for q = 1, 4 do
						local name = `{spec.hlod}_{q}`
						local r = meshReg[name]
						if type(r) ~= "table" or type(r.hlod) ~= "table" then
							err(
								path .. ".hlod",
								`no HLOD proxy "{name}" - make the ring's four quarters: lune run kit world meshes (kind "hlod_ring", "quadrant" 1 .. 4)`
							)
							ok = false
						elseif type(r.tris) ~= "number" or r.tris > World.HLOD_TRIS then
							err(
								path .. ".hlod",
								`HLOD proxy "{name}" has {tostring(r.tris)} triangles: {World.HLOD_TRIS} at most`
							)
							ok = false
						elseif
							r.hlod.quadrant ~= q
							or type(r.hlod.radius) ~= "number"
							or math.abs(r.hlod.radius - R) > 1
						then
							-- (made for another quarter or another ring: the wedges would hide at this radius and the
							-- proxy stand at its own - a fresh review, 2026-11-19)
							err(
								path .. ".hlod",
								`HLOD proxy "{name}" was made as quarter {tostring(r.hlod.quadrant)} of a ring of radius {tostring(
									r.hlod.radius
								)}: this horizon is quarter {q} of radius {R} - its recipe's "quadrant" and "radius" must match`
							)
							ok = false
						end
						table.insert(names, name)
					end
					if ok then
						proxies = names
						dressBegin(path)
					end
				end
			end
			local function ridge(
				name: string,
				m: any,
				cx: number,
				by: number,
				cz: number,
				L: number,
				H: number,
				D: number,
				yaw: number
			)
				L, H, D = math.min(L, 2048), math.min(H, 2048), math.min(D, 4096)
				local ry = World.rotation({ 0, yaw, 0 })
				for side = -1, 1, 2 do
					local r = World.rotation({ 0, yaw + (if side > 0 then 180 else 0), 0 })
					local off = side * D / 4
					add(path, {
						name = name,
						mat = m,
						collide = false,
						backdrop = true,
						shape = "Wedge",
						transparency = if proxies then 1 else nil, -- (a stand-in for its proxy: shown while it is not there)
					}, { L, H, D / 2 }, {
						cx + ry[1][3] * off,
						by + H / 2,
						cz + ry[3][3] * off,
					}, r)
				end
			end
			if spec.floor then -- far land under the ranges (9 tiles; inside the map they lie under the terrain)
				for gx = -1, 1 do
					for gz = -1, 1 do
						add(
							path,
							{ name = "FarLand", mat = spec.floor, collide = false, backdrop = true },
							{ 2048, 8, 2048 },
							{
								c[1] + gx * 2048,
								y0 + 36,
								c[2] + gz * 2048,
							}
						)
					end
				end
			end
			for k = 1, n do
				local a = (k + rnd() * 0.6) / n * 2 * math.pi
				local rr = R * (0.9 + rnd() * 0.25)
				local px, pz = c[1] + math.cos(a) * rr, c[2] + math.sin(a) * rr
				local h = hl + (hh - hl) * rnd()
				-- a long straight crest reads as a wall: every peak is two SHORT ridges crossed at right angles, so its
				-- silhouette is a point from any side; 2-3 peaks of falling height make the massif's skyline
				local peaks = 2 + math.floor(rnd() * 2)
				for j = 1, peaks do
					local hj = h * (if j == 1 then 1 else 0.45 + rnd() * 0.35)
					local L = hj * (0.35 + rnd() * 0.4)
					local D = hj * (1.6 + rnd() * 0.6)
					local yaw = rnd() * 180
					local ox, oz = (rnd() - 0.5) * h * 1.2, (rnd() - 0.5) * h * 1.2
					for t, turn in { 0, 90 } do
						-- the crossing ridge is lower, shorter and off-centre: a lopsided peak, never a pyramid
						local kh = if t == 1 then 1 else 0.68 + rnd() * 0.22
						local sx, sz =
							if t == 1 then 0 else (rnd() - 0.5) * hj * 0.5,
							if t == 1 then 0 else (rnd() - 0.5) * hj * 0.5
						ridge(
							"Range",
							spec.mat,
							px + ox + sx,
							y0,
							pz + oz + sz,
							L * (0.6 + rnd() * 0.8),
							hj * kh,
							D * kh,
							yaw + turn
						)
						if j == 1 and spec.cap then -- the crest: the same shape's top quarter, a hair bigger
							ridge(
								"RangeCap",
								spec.cap,
								px + ox + sx,
								y0 + hj * kh * 0.74,
								pz + oz + sz,
								L * 0.3,
								hj * kh * 0.27,
								D * kh * 0.27,
								yaw + turn
							)
						end
					end
				end
			end
			if proxies then -- the ring's four quarters, on its centre and foot
				for _, name in proxies do
					local p = placeMesh(path, name, c[1], y0, c[2], meshReg[name].size[2], 0, false, spec.mat)
					if p then
						p.backdrop = true
					end
				end
				dressKey = nil
			end
		elseif kind == "story" then
			-- { kind: "camp" | "battle" | "cart", center: [x, 0, z], ground: true, seed, yaw?, mats?: { wood, cloth,
			--   stone, metal, fire, scorch } } — SET DRESSING THAT TELLS A STORY (AAA gap W7): a small scene placed by
			--   rule round its anchor, every prop on its own ground. Primitives for now (meshes: the modular kit, W3)
			local rnd = lcg(spec.seed or 1)
			local c = spec.center or { 0, 0, 0 }
			local m = spec.mats or {}
			local function pal(role: string, fallback: string): string
				if type(m[role]) == "string" then
					return m[role]
				end
				return if palette[role] then role else fallback
			end
			local wood, cloth = pal("wood", spec.mat or next(palette)), pal("cloth", spec.mat or next(palette))
			local stone, metal = pal("stone", spec.mat or next(palette)), pal("metal", spec.mat or next(palette))
			local yaw0 = spec.yaw or rnd() * 360
			local function at(dx: number, dz: number): (number, number, number)
				local a = math.rad(yaw0)
				local x = c[1] + dx * math.cos(a) + dz * math.sin(a)
				local z = c[3] - dx * math.sin(a) + dz * math.cos(a)
				local gy = if spec.ground == true then groundAt(x, z) or c[2] else c[2]
				return x, gy, z
			end
			local function prop(
				name: string,
				pm: string,
				size: { number },
				dx: number,
				dz: number,
				lift: number,
				rot: { number }?,
				extra: any?
			)
				local x, gy, z = at(dx, dz)
				local s = { name = name, mat = pm, sink = false }
				for k, v in extra or {} do
					s[k] = v
				end
				add(path, s, size, { x, gy + lift, z }, World.rotation(rot or { 0, yaw0 + (rnd() - 0.5) * 40, 0 }))
			end
			local story = spec.kind or "camp"
			if story == "camp" then
				for k = 0, 9 do -- the fire ring
					local a = k / 10 * 2 * math.pi
					prop("RingStone", stone, { 1.2, 0.8, 1.2 }, math.cos(a) * 2.6, math.sin(a) * 2.6, 0.3)
				end
				prop("Fire", pal("fire", wood), { 1.6, 1, 1.6 }, 0, 0, 0.5, { 0, 0, 0 }, {
					collide = false,
					particles = "embers",
					light = { color = { 255, 140, 60 }, range = 24, brightness = 2.5 },
				})
				for k = 0, 2 do -- logs to sit on, round the fire
					local a = (k / 3) * 2 * math.pi + 0.4
					prop(
						"Log",
						wood,
						{ 5, 1.2, 1.2 },
						math.cos(a) * 6,
						math.sin(a) * 6,
						0.6,
						{ 0, math.deg(-a) + 90 + yaw0, 0 },
						{
							shape = "Cylinder",
						}
					)
				end
				for k = 0, 1 do -- bedrolls
					prop("Bedroll", cloth, { 2.4, 0.5, 6 }, -9 + k * 3.2, 7, 0.25, nil, { collide = false })
				end
				-- an A-frame tent: two cloth slopes back to back
				local tx, tz = 9, 8
				prop("Tent", cloth, { 7, 6, 4.2 }, tx, tz - 2.1, 3, { 0, yaw0, 0 }, { shape = "Wedge" })
				prop("Tent", cloth, { 7, 6, 4.2 }, tx, tz + 2.1, 3, { 0, yaw0 + 180, 0 }, { shape = "Wedge" })
				prop("Crate", wood, { 3, 3, 3 }, 11, -4, 1.5)
				prop("Crate", wood, { 2.4, 2.4, 2.4 }, 12.5, -1.4, 1.2)
			elseif story == "battle" then
				for _ = 1, 7 do -- broken blades and spears stuck in the ground at angles
					local dx, dz = (rnd() - 0.5) * 30, (rnd() - 0.5) * 30
					local len = 3 + rnd() * 4
					prop("Blade", metal, { 0.3, len, 0.8 }, dx, dz, len * 0.35, {
						(rnd() - 0.5) * 50,
						rnd() * 360,
						(rnd() - 0.5) * 50,
					})
				end
				for _ = 1, 4 do -- fallen shields
					prop("Shield", wood, { 0.4, 3.6, 3.6 }, (rnd() - 0.5) * 28, (rnd() - 0.5) * 28, 0.3, {
						0,
						rnd() * 360,
						85,
					}, { shape = "Cylinder" })
				end
				for _ = 1, 3 do -- scorched earth where the fires burned
					prop(
						"Scorch",
						pal("scorch", stone),
						{ 6 + rnd() * 4, 0.1, 6 + rnd() * 4 },
						(rnd() - 0.5) * 24,
						(rnd() - 0.5) * 24,
						0.05,
						nil,
						{
							collide = false,
						}
					)
				end
				for _ = 1, 6 do -- debris
					prop(
						"Debris",
						stone,
						{ 1 + rnd() * 1.5, 0.8 + rnd(), 1 + rnd() * 1.5 },
						(rnd() - 0.5) * 30,
						(rnd() - 0.5) * 30,
						0.4
					)
				end
			elseif story == "cart" then
				prop("CartBed", wood, { 5, 1.2, 9 }, 0, 0, 2.4, { 6, yaw0, -8 }) -- (tilted: a wheel is gone)
				for _, w in { { -2.9, -3 }, { 2.9, -3 }, { -2.9, 3 } } do
					prop("Wheel", wood, { 0.6, 3.6, 3.6 }, w[1], w[2], 1.6, { 0, yaw0, 0 }, { shape = "Cylinder" })
				end
				prop("Wheel", wood, { 0.6, 3.6, 3.6 }, 6, 6, 0.35, { 0, yaw0 + 30, 90 }, { shape = "Cylinder" }) -- (the lost one)
				for _ = 1, 4 do -- the load, spilled
					local big = rnd() < 0.5
					prop(
						if big then "Crate" else "Sack",
						if big then wood else cloth,
						if big then { 2.6, 2.6, 2.6 } else { 2.2, 1.6, 2.6 },
						3 + rnd() * 6,
						-4 + rnd() * 8,
						if big then 1.3 else 0.8
					)
				end
			else
				err(path .. ".kind", 'story kind is "camp" | "battle" | "cart"')
			end
		elseif kind == "cliffs" then
			-- { meshes: [rock-face names], screeMeshes?: [names], center?, area? (default: the whole land), spacing?: 22,
			--   roles?: ["cliff"], minSlope?: 35, blockSlope?: 55, height?: [12, 60], max?: 160, seed, mat, avoid? } — Roblox terrain
			--   cannot hold a sharp cliff: a scanned rock face over every steep painted cell, turned downhill, as tall as
			--   the land drops there, its foot sunk; scree rocks at the foot (AAA gap W4)
			if type(spec.meshes) ~= "table" or #spec.meshes == 0 then
				err(path .. ".meshes", "cliffs need rock-face meshes (kit world import: ph_rockface, cliff_a ...)")
				continue
			end
			local rnd = lcg(spec.seed or 1)
			local spacing = spec.spacing or 22
			local roles = spec.roles or { "cliff" }
			local minSlope = spec.minSlope or 35
			local hlo, hhi = (spec.height or { 12, 60 })[1], (spec.height or { 12, 60 })[2]
			local x0, x1, z0, z1
			if spec.area then
				local cc = spec.center or { 0, 0, 0 }
				x0, x1 = cc[1] - spec.area[1] / 2, cc[1] + spec.area[1] / 2
				z0, z1 = cc[3] - spec.area[2] / 2, cc[3] + spec.area[2] / 2
			else
				for _, g in groundOps do
					if not g.backdrop then
						x0 = math.min(x0 or math.huge, g.center[1] - g.size[1] / 2)
						x1 = math.max(x1 or -math.huge, g.center[1] + g.size[1] / 2)
						z0 = math.min(z0 or math.huge, g.center[3] - g.size[2] / 2)
						z1 = math.max(z1 or -math.huge, g.center[3] + g.size[2] / 2)
					end
				end
			end
			if not x0 then
				err(path, "cliffs need terrain ground (a heightmap op) or a center + area")
				continue
			end
			local cands = {}
			local gx = (x0 :: number) + spacing / 2
			while gx < (x1 :: number) do
				local gz = (z0 :: number) + spacing / 2
				while gz < (z1 :: number) do
					local x, z = gx + (rnd() - 0.5) * spacing * 0.6, gz + (rnd() - 0.5) * spacing * 0.6
					local h = groundAt(x, z)
					if h then
						local e = 3
						local ddx = ((groundAt(x + e, z) or h) - (groundAt(x - e, z) or h)) / (2 * e)
						local ddz = ((groundAt(x, z + e) or h) - (groundAt(x, z - e) or h)) / (2 * e)
						local slope = math.deg(math.atan(math.sqrt(ddx * ddx + ddz * ddz)))
						local role = roleAt(x, z)
						-- truly steep only (a face on walkable land is a new wall: traps), and never the land's rim
						local steep = slope >= minSlope and (role == nil or table.find(roles, role) ~= nil)
						local rim =
							math.min(x - (x0 :: number), (x1 :: number) - x, z - (z0 :: number), (z1 :: number) - z)
						local free = rim > 48 and not nearRoad(x, z, 6)
						for _, a in spec.avoid or {} do
							free = free and (x - a[1]) ^ 2 + (z - a[2]) ^ 2 >= a[3] ^ 2
						end
						if steep and free then
							table.insert(cands, { x = x, z = z, h = h, dx = ddx, dz = ddz, slope = slope })
						end
					end
					gz += spacing
				end
				gx += spacing
			end
			-- too many: the steepest first (they are the ones terrain renders worst)
			table.sort(cands, function(a, b)
				return a.slope > b.slope
			end)
			local max = spec.max or 160
			for ci = 1, math.min(#cands, max) do
				local cd = cands[ci]
				local len = math.sqrt(cd.dx * cd.dx + cd.dz * cd.dz)
				local ux, uz = if len > 0 then -cd.dx / len else 0, if len > 0 then -cd.dz / len else 1 -- (downhill)
				local up = groundAt(cd.x - ux * spacing / 2, cd.z - uz * spacing / 2) or cd.h
				local down = groundAt(cd.x + ux * spacing / 2, cd.z + uz * spacing / 2) or cd.h
				local H = math.clamp((up - down) * 1.3, hlo, hhi)
				local yaw = math.deg(math.atan2(ux, uz)) + (rnd() - 0.5) * 40
				local mname = spec.meshes[math.floor(rnd() * #spec.meshes) + 1]
				-- sunk INTO the slope: shifted uphill by a sixth of its height, its foot below the downhill ground, so it
				-- covers the face of the hill instead of standing on it
				local fx, fz = cd.x - ux * H * 0.15, cd.z - uz * H * 0.15
				-- it COLLIDES only where the hill is already too steep to climb (blockSlope): on a climbable slope the terrain
				-- under it stays the walkable truth (a colliding face there turned a hill into a one-way drop: a trap)
				local blocks = cd.slope >= (spec.blockSlope or 55)
				-- a tall face near the land's edge spills past it (a ledge you drop onto and never leave): keep it in
				local edge =
					math.min(fx - (x0 :: number), (x1 :: number) - fx, fz - (z0 :: number), (z1 :: number) - fz)
				if edge < H * 1.2 + 24 then
					continue
				end
				-- a face buried by its own shift uphill shows nothing (wasted budget): its top must stand proud
				if down - H * 0.25 + H < (groundAt(fx, fz) or down) + 2 then
					continue
				end
				placeMesh(path, mname, fx, down - H * 0.25, fz, H, yaw, blocks, spec.mat)
				if type(spec.screeMeshes) == "table" and #spec.screeMeshes > 0 then
					for _ = 1, 2 do
						local d = spacing * 0.55 + rnd() * 6
						local sx, sz = cd.x + ux * d + (rnd() - 0.5) * 8, cd.z + uz * d + (rnd() - 0.5) * 8
						local sh = groundAt(sx, sz)
						if sh and not nearRoad(sx, sz, 4) then
							local smesh = spec.screeMeshes[math.floor(rnd() * #spec.screeMeshes) + 1]
							local SH = 2 + rnd() * 4
							placeMesh(path, smesh, sx, sh - SH * 0.3, sz, SH, rnd() * 360, true, spec.mat)
						end
					end
				end
			end
		elseif kind == "rocks" then
			-- { center: [x, y, z], area: [w, d], count, seed, size: [lo, hi], mat, matAlt?, spires?: n,
			--   spireHeight?: [lo, hi], ground, slopeMax, avoid, meshes?: [names], spireMeshes?: [names] } — crags: each
			--   outcrop is 3-5 tilted blocks around one big one, half sunk into the land; spires are leaning stacks of
			--   tapering blocks. With "meshes" (scanned rocks: kit world import) each block is a real rock instead, and
			--   with "spireMeshes" each spire is one tall scanned rock face
			local rnd = lcg(spec.seed or 1)
			local c, area = spec.center or { 0, 0, 0 }, spec.area or { 100, 100 }
			local lo, hi = (spec.size or { 6, 16 })[1], (spec.size or { 6, 16 })[2]
			local function pick(): any
				return if spec.matAlt and rnd() < 0.35 then spec.matAlt else spec.mat
			end
			local function site(): (number?, number, number)
				for _ = 1, 40 do
					local x = c[1] + (rnd() - 0.5) * area[1]
					local z = c[3] + (rnd() - 0.5) * area[2]
					local ok, h = terrainSite(spec, x, z)
					if ok then
						return x, z, if spec.ground == true then h else c[2]
					end
				end
				return nil, 0, 0
			end
			local placed = 0
			for _ = 1, spec.count or 8 do
				local x, z, base = site()
				if not x then
					continue
				end
				local sz = lo + (hi - lo) * rnd()
				for j = 1, 3 + math.floor(rnd() * 3) do
					local f = if j == 1 then 1 else 0.4 + rnd() * 0.45
					local size =
						{ sz * f * (0.8 + rnd() * 0.6), sz * f * (0.55 + rnd() * 0.6), sz * f * (0.8 + rnd() * 0.6) }
					local ox = if j == 1 then 0 else (rnd() - 0.5) * sz
					local oz = if j == 1 then 0 else (rnd() - 0.5) * sz
					if spec.meshes then
						local mname = spec.meshes[math.floor(rnd() * #spec.meshes) + 1]
						placeMesh(
							path,
							mname,
							(x :: number) + ox,
							base - size[2] * 0.25,
							z + oz,
							size[2] * 1.25,
							rnd() * 360,
							true,
							pick()
						)
						continue
					end
					add(path, { name = "Rock", mat = pick() }, size, {
						(x :: number) + ox,
						base + size[2] * 0.22,
						z + oz,
					}, World.rotation({ (rnd() - 0.5) * 46, rnd() * 360, (rnd() - 0.5) * 46 }))
				end
				placed += 1
			end
			local sl, sh = (spec.spireHeight or { 30, 60 })[1], (spec.spireHeight or { 30, 60 })[2]
			for _ = 1, spec.spires or 0 do
				local x, z, base = site()
				if not x then
					continue
				end
				local H = sl + (sh - sl) * rnd()
				if spec.spireMeshes then
					local mname = spec.spireMeshes[math.floor(rnd() * #spec.spireMeshes) + 1]
					placeMesh(path, mname, x :: number, base - H * 0.12, z, H, rnd() * 360, true, pick())
					placed += 1
					continue
				end
				local segs = 3 + math.floor(rnd() * 2)
				local w0 = H * (0.2 + rnd() * 0.08)
				local lean = { (rnd() - 0.5) * 0.22, (rnd() - 0.5) * 0.22 }
				local y = base - 2
				for k = 1, segs do
					local f = 1 - (k - 1) / segs * 0.62
					local sh2 = H / segs * 1.12
					add(
						path,
						{ name = "Spire", mat = pick() },
						{ w0 * f, sh2, w0 * f * (0.8 + rnd() * 0.3) },
						{
							(x :: number) + lean[1] * (y - base),
							y + sh2 / 2,
							z + lean[2] * (y - base),
						},
						World.rotation({
							lean[2] * 40 + (rnd() - 0.5) * 8,
							rnd() * 360,
							-lean[1] * 40 + (rnd() - 0.5) * 8,
						})
					)
					y += H / segs
				end
				placed += 1
			end
			if placed == 0 then
				warn(path, "rocks: no site fitted (area, slopeMax, avoid)")
			end
		elseif kind == "arch" then
			-- { pos: [x, y, z] (the opening's centre at its floor), span: opening width, height: where the curve
			--   starts, depth: thickness through, pier: pier width, yaw, stones?: 9, mat, keystone?: mat } — a round
			--   arch: two piers and a ring of stones around a semicircle, the middle one a keystone
			local p = spec.pos or { 0, 0, 0 }
			local span, hgt = spec.span or 8, spec.height or 10
			local dep, pw = spec.depth or 3, spec.pier or 2.5
			local yaw = spec.yaw or 0
			local r = World.rotation({ 0, yaw, 0 })
			local function at(lx: number, ly: number): { number }
				return { p[1] + r[1][1] * lx, p[2] + ly, p[3] + r[3][1] * lx }
			end
			for _, sgn in { -1, 1 } do
				add(
					path,
					{ name = "Pier", mat = spec.mat },
					{ pw, hgt, dep },
					at(sgn * (span / 2 + pw / 2), hgt / 2),
					r
				)
			end
			local n = spec.stones or 9
			local R = span / 2 + pw / 2
			for k = 0, n - 1 do
				local th = (k + 0.5) / n * math.pi
				local key = k == math.floor(n / 2)
				local len = math.pi * R / n * (if key then 1.25 else 1.04)
				add(
					path,
					{
						name = if key then "Keystone" else "Voussoir",
						mat = if key then (spec.keystone or spec.mat) else spec.mat,
						sink = false,
					},
					{ len, pw * (if key then 1.25 else 1), dep * (if key then 1.08 else 1) },
					at(math.cos(th) * R, hgt + math.sin(th) * R),
					World.rotation({ 0, yaw, math.deg(th) + 90 })
				)
			end
		elseif kind == "peak" then
			-- { pos: [x, y, z] (its base), height, base (width), mat, cap?: mat, beam?: mat (a Neon light rising from
			--   the summit, "beamHeight"), seed } — ONE landmark mountain (backdrop): crossed prisms + a ring of
			--   foothills, so it reads from every side; the beam is the Journey mountain's light
			local rnd = lcg(spec.seed or 1)
			local p, H, B = spec.pos or { 0, 0, 0 }, spec.height or 800, spec.base or (spec.height or 800) * 1.4
			for _, yaw in { 0, 60, 120 } do
				prism(
					path,
					{ name = "Peak", mat = spec.mat, collide = false, backdrop = true },
					p[1],
					p[2],
					p[3],
					B * 0.12,
					H,
					B,
					yaw
				)
			end
			for k = 1, 6 do
				local a = k / 6 * math.pi * 2 + rnd() * 0.5
				local hh = H * (0.35 + rnd() * 0.25)
				local d = B * (0.32 + rnd() * 0.16)
				prism(
					path,
					{ name = "Foothill", mat = spec.mat, collide = false, backdrop = true },
					p[1] + math.cos(a) * d,
					p[2],
					p[3] + math.sin(a) * d,
					hh * 0.4,
					hh,
					hh * 1.5,
					math.deg(a) + rnd() * 40
				)
			end
			if spec.cap then
				for _, yaw in { 0, 60, 120 } do
					prism(
						path,
						{ name = "PeakCap", mat = spec.cap, collide = false, backdrop = true },
						p[1],
						p[2] + H * 0.72,
						p[3],
						B * 0.12 * 0.3,
						H * 0.29,
						B * 0.29,
						yaw
					)
				end
			end
			if spec.beam then
				local bh = spec.beamHeight or H * 2
				add(
					path,
					{
						name = "Beam",
						mat = spec.beam,
						shape = "Cylinder",
						collide = false,
						backdrop = true,
						transparency = 0.35,
						light = { color = { 255, 236, 200 }, range = 60, brightness = 6 },
					},
					{ math.min(bh, 2048), H * 0.03, H * 0.03 },
					{ p[1], p[2] + H + math.min(bh, 2048) / 2, p[3] },
					World.rotation({ 0, 0, 90 })
				)
			end
		elseif kind == "city" then
			-- { center: [x, y, z], area: [w, d], block: [bw, bd] (one city block), street: width, heights: [lo, hi],
			--   mat, matAlt?, glass: mat (window bands), signs?: [mat, ...] (neon boards), plaza?: [[x, z, r]] (kept
			--   open), seed, ground } — blocks of buildings between streets: each block split into 1-3 buildings,
			--   each with a roof ledge, bands of lit windows on its street faces and now and then a neon sign
			local rnd = lcg(spec.seed or 1)
			local c, area = spec.center or { 0, 0, 0 }, spec.area or { 300, 300 }
			local bw, bd = (spec.block or { 60, 60 })[1], (spec.block or { 60, 60 })[2]
			local st = spec.street or 14
			local hl, hh = (spec.heights or { 16, 60 })[1], (spec.heights or { 16, 60 })[2]
			local nx = math.max(1, math.floor((area[1] + st) / (bw + st)))
			local nz = math.max(1, math.floor((area[2] + st) / (bd + st)))
			local x0 = c[1] - (nx * bw + (nx - 1) * st) / 2
			local z0 = c[3] - (nz * bd + (nz - 1) * st) / 2
			local function inPlaza(x: number, z: number, pad: number): boolean
				for _, pz in spec.plaza or {} do
					if (x - pz[1]) ^ 2 + (z - pz[2]) ^ 2 < (pz[3] + pad) ^ 2 then
						return true
					end
				end
				return false
			end
			local made = 0
			for ix = 0, nx - 1 do
				for iz = 0, nz - 1 do
					local bx, bz = x0 + ix * (bw + st), z0 + iz * (bd + st)
					if spec.sidewalk and not inPlaza(bx + bw / 2, bz + bd / 2, math.max(bw, bd) / 2) then
						local sb = if spec.ground == true then (groundAt(bx + bw / 2, bz + bd / 2) or c[2]) else c[2]
						add(
							path,
							{ name = "Sidewalk", mat = spec.sidewalk, sink = false, backdrop = spec.backdrop },
							{ bw + 4, 0.5, bd + 4 },
							{
								bx + bw / 2,
								sb + 0.25,
								bz + bd / 2,
							}
						)
					end
					-- split the block along its longer side into 1-3 lots
					local splits = 1 + math.floor(rnd() * 3)
					local alongX = bw >= bd
					for k = 1, splits do
						local f0, f1 = (k - 1) / splits, k / splits
						local lx0 = if alongX then bx + bw * f0 else bx
						local lx1 = if alongX then bx + bw * f1 else bx + bw
						local lz0 = if alongX then bz else bz + bd * f0
						local lz1 = if alongX then bz + bd else bz + bd * f1
						local gap = 1.5 -- an alley between lots
						lx0, lx1, lz0, lz1 = lx0 + gap, lx1 - gap, lz0 + gap, lz1 - gap
						local cx, cz = (lx0 + lx1) / 2, (lz0 + lz1) / 2
						local w, d = lx1 - lx0, lz1 - lz0
						if w < 6 or d < 6 or inPlaza(cx, cz, math.max(w, d) / 2) then
							continue
						end
						local base = if spec.ground == true then (groundAt(cx, cz) or c[2]) else c[2]
						local h = hl + (hh - hl) * rnd() ^ 1.6
						local m = if spec.matAlt and rnd() < 0.4 then spec.matAlt else spec.mat
						add(
							path,
							{ name = "Building", mat = m, backdrop = spec.backdrop, collide = spec.backdrop ~= true },
							{ w, h + 4, d },
							{ cx, base + h / 2 - 2, cz }
						)
						add(path, {
							name = "Ledge",
							mat = m,
							sink = false,
							backdrop = spec.backdrop,
							collide = spec.backdrop ~= true,
						}, { w + 1, 1, d + 1 }, { cx, base + h + 0.5, cz })
						-- window bands on the long faces: thin glowing strips every floor
						if spec.glass then
							local floors = math.floor((h - 4) / 4.5)
							for fl = 1, floors do
								if rnd() < 0.82 then
									local y = base + 2 + fl * 4.5
									local lit = if rnd() < 0.55 then spec.glass else (spec.glassDark or spec.glass)
									for _, side in { -1, 1 } do
										if alongX then
											add(path, {
												name = "Windows",
												mat = lit,
												collide = false,
												sink = false,
												backdrop = spec.backdrop,
											}, { w * 0.86, 1.6, 0.2 }, {
												cx,
												y,
												cz + side * (d / 2 + 0.1),
											})
										else
											add(path, {
												name = "Windows",
												mat = lit,
												collide = false,
												sink = false,
												backdrop = spec.backdrop,
											}, { 0.2, 1.6, d * 0.86 }, {
												cx + side * (w / 2 + 0.1),
												y,
												cz,
											})
										end
									end
								end
							end
						end
						-- a vertical neon sign hanging off a corner, now and then
						-- (an alongX block's middle lots face alleys on both X sides: no sign there)
						local streetSide = if not alongX
							then (if rnd() < 0.5 then -1 else 1)
							elseif k == 1 then -1
							elseif k == splits then 1
							else 0
						if streetSide ~= 0 and spec.signs and #spec.signs > 0 and rnd() < 0.45 and h > 20 then
							local sm = spec.signs[math.floor(rnd() * #spec.signs) + 1]
							local sh = math.min(h * 0.45, 18)
							local sx = if streetSide < 0 then lx0 - 0.3 else lx1 + 0.3 -- flush on the wall
							add(path, {
								name = "Sign",
								mat = sm,
								collide = false,
								backdrop = spec.backdrop,
								sink = false,
								light = {
									color = (palette[sm] and palette[sm].color) or { 255, 120, 200 },
									range = 18,
									brightness = 1.6,
								},
							}, { 0.6, sh, 3.2 }, { sx, base + h - sh / 2 - 2, cz })
						end
						made += 1
					end
				end
			end
			if made == 0 then
				warn(path, "city: no lot fitted (area, block, plaza)")
			end
		elseif kind == "crosswalk" then
			-- { from: [x, z], to: [x, z], width: 10, stripe: 1.2, gap: 1.2, y: 0.05, mat, ground } — zebra stripes
			-- across a road: each stripe a thin slab crossing the from -> to line
			local fx, fz, tx, tz = spec.from[1], spec.from[2], spec.to[1], spec.to[2]
			local dx, dz = tx - fx, tz - fz
			local len = math.sqrt(dx * dx + dz * dz)
			if len < 0.5 then
				err(path, "crosswalk needs from != to")
				continue
			end
			local stripe, gap, w = spec.stripe or 1.2, spec.gap or 1.2, spec.width or 10
			local r = World.rotation({ 0, math.deg(math.atan2(-dz, dx)), 0 })
			local at = stripe / 2
			while at <= len - stripe / 2 do
				local x, z = fx + dx / len * at, fz + dz / len * at
				local base = if spec.ground == true then (groundAt(x, z) or 0) else 0
				add(path, { name = "Stripe", mat = spec.mat, sink = false }, { stripe, 0.12, w }, {
					x,
					base + (spec.y or 0.05),
					z,
				}, r)
				at += stripe + gap
			end
		elseif kind == "row" then
			-- { points: [[x, z], ...], every: 24, side?: 6 (offset to the right of the line; negative = left),
			--   item: "lamp" | { part spec }, mat, light?: mat (lamp head), color?: [r, g, b], ground } — things set out
			--   along a line: street lamps (pole, arm, glowing head + light), bollards, posts
			local pts = spec.points
			if type(pts) ~= "table" or #pts < 2 then
				err(path, "row needs at least 2 points [[x, z], ...]")
				continue
			end
			-- a lamp only where it has a reason: the owner on the District (2026-10-28) "I hate the fact that you added a
			-- lamp everywhere" - a row of lamps defaults to 90 studs apart (a lamp every 24 was that street); other
			-- items (bollards, posts) keep 24. kit world check fails a new world whose lamps crowd (worldcheck lamp_density)
			local every = spec.every or (if spec.item == "lamp" then 90 else 24)
			local side = spec.side or 0
			local walked = 0
			for k = 1, #pts - 1 do
				local a, b = pts[k], pts[k + 1]
				local dx, dz = b[1] - a[1], b[2] - a[2]
				local len = math.sqrt(dx * dx + dz * dz)
				if len < 0.01 then
					continue
				end
				local nxs, nzs = -dz / len, dx / len -- right-hand normal
				local d = (every - walked % every) % every
				local last = k == #pts - 1
				while d < len or (last and d <= len) do -- (a corner belongs to the next segment)
					local x = a[1] + dx / len * d + nxs * side
					local z = a[2] + dz / len * d + nzs * side
					local base = if spec.ground == true then (groundAt(x, z) or 0) else (spec.y or 0)
					if spec.item == "lamp" then
						local hgt = spec.height or 12
						add(
							path,
							{ name = "LampPole", mat = spec.mat, sink = false },
							{ 0.5, hgt, 0.5 },
							{ x, base + hgt / 2, z }
						)
						local toward = if side >= 0 then -1 else 1 -- the arm reaches back over the road
						local ax, az = x + nxs * 1.6 * toward, z + nzs * 1.6 * toward
						add(path, { name = "LampArm", mat = spec.mat, sink = false }, { 0.3, 0.3, 1.9 }, {
							(x + ax) / 2,
							base + hgt - 0.2,
							(z + az) / 2,
						}, World.rotation({ 0, math.deg(math.atan2(nxs, nzs)), 0 }))
						add(path, {
							name = "LampHead",
							mat = spec.light or spec.mat,
							collide = false,
							sink = false,
							light = {
								color = spec.color or { 255, 214, 160 },
								range = spec.range or 22,
								brightness = 2,
							},
						}, { 1, 0.5, 1 }, { ax, base + hgt - 0.6, az })
					elseif type(spec.item) == "table" then
						local s = table.clone(spec.item)
						s.sink = false
						local sz = s.size or { 1, 1, 1 }
						add(path, s, sz, { x, base + sz[2] / 2, z })
					end
					d += every
				end
				walked += len
			end
		elseif kind == "ziggurat" then
			-- { center: [x, y, z], base: [w, d], tiers: 5, tierHeight: 8, shrink: 0.78, mat, stair: "S" | "N" | "E" | "W",
			--   stairMat?, shrine?: { mat, roofMat }, ground } — a stepped temple pyramid: tiers narrowing upward, one
			--   grand stair up the middle of a face (steps of 1 stud), a shrine on the summit
			local c = spec.center or { 0, 0, 0 }
			local w, d = (spec.base or { 80, 80 })[1], (spec.base or { 80, 80 })[2]
			local tiers, th, shrink = spec.tiers or 5, spec.tierHeight or 8, spec.shrink or 0.78
			local y = c[2]
			local tw, td = w, d
			for _ = 1, tiers do
				add(path, { name = "Tier", mat = spec.mat }, { tw, th, td }, { c[1], y + th / 2, c[3] })
				-- a ledge band where the next tier sits (shadow line)
				add(
					path,
					{ name = "TierLip", mat = spec.stairMat or spec.mat, sink = false },
					{ tw + 1, 0.8, td + 1 },
					{
						c[1],
						y + th - 0.4,
						c[3],
					}
				)
				y += th
				tw, td = tw * shrink, td * shrink
			end
			local H = tiers * th
			local side = spec.stair or "S"
			local dir = ({ S = { 0, 1 }, N = { 0, -1 }, E = { 1, 0 }, W = { -1, 0 } })[side] or { 0, 1 }
			local reach = if dir[1] ~= 0 then w / 2 else d / 2
			local steps = math.ceil(H / 1)
			local stepRun = (reach - (if dir[1] ~= 0 then tw else td) / 2 + 2) / steps
			local sw = spec.stairWidth or math.min(w, d) * 0.18
			for k = 1, steps do
				local h = k * (H / steps)
				local out = reach + 2 - (k - 0.5) * stepRun
				local sx, sz = c[1] + dir[1] * out, c[3] + dir[2] * out
				add(
					path,
					{ name = "Stair", mat = spec.stairMat or spec.mat },
					if dir[1] ~= 0 then { stepRun + 0.05, h, sw } else { sw, h, stepRun + 0.05 },
					{ sx, c[2] + h / 2, sz }
				)
			end
			if spec.shrine then
				local sh = spec.shrine
				local sw2, sd2 = tw / shrink * 0.6, td / shrink * 0.6
				local sy = c[2] + H
				for _, o in { { -1, -1 }, { 1, -1 }, { 1, 1 }, { -1, 1 } } do
					add(path, { name = "ShrinePillar", mat = sh.mat or spec.mat }, { 2, 9, 2 }, {
						c[1] + o[1] * (sw2 / 2 - 1),
						sy + 4.5,
						c[3] + o[2] * (sd2 / 2 - 1),
					})
				end
				add(
					path,
					{ name = "ShrineRoof", mat = sh.roofMat or sh.mat or spec.mat, sink = false },
					{ sw2 + 2, 2, sd2 + 2 },
					{
						c[1],
						sy + 10,
						c[3],
					}
				)
				prism(
					path,
					{ name = "ShrineCap", mat = sh.roofMat or sh.mat or spec.mat },
					c[1],
					sy + 11,
					c[3],
					sw2 * 0.5,
					5,
					sd2 + 2,
					0
				)
				if sh.glow then
					add(path, {
						name = "Relic",
						mat = sh.glow,
						shape = "Ball",
						collide = false,
						light = { color = { 120, 255, 200 }, range = 30, brightness = 3 },
					}, { 2.2, 2.2, 2.2 }, { c[1], sy + 2.5, c[3] })
				end
			end
		elseif kind == "fog" then
			-- FOG THAT LIES LOW (kit/lib/worldfog.luau): see-through sheets stacked over the land under a fog line, over
			-- water, or in the hollows; each sheet only where the land lies under it
			-- (the PLAY land only: far scenery - a backdrop ground - takes no fog and does not widen where it may lie)
			local play = {}
			local x0, z0, x1, z1 = math.huge, math.huge, -math.huge, -math.huge
			for _, s in groundOps do
				if not s.backdrop then
					table.insert(play, s)
					x0, x1 = math.min(x0, s.center[1] - s.size[1] / 2), math.max(x1, s.center[1] + s.size[1] / 2)
					z0, z1 = math.min(z0, s.center[3] - s.size[2] / 2), math.max(z1, s.center[3] + s.size[2] / 2)
				end
			end
			local function playAt(x: number, z: number): number?
				local best: number? = nil
				for _, s in play do
					if math.abs(x - s.center[1]) <= s.size[1] / 2 and math.abs(z - s.center[3]) <= s.size[2] / 2 then
						local h = World.groundHeight(s, x, z)
						if best == nil or h > best then
							best = h
						end
					end
				end
				return best
			end
			if #play == 0 then
				err(path, "fog lies over the land: this world has no ground (a terrain ground / heightmap step)")
			elseif spec.mat == nil then
				err(
					path .. ".mat",
					'fog needs "mat": a palette entry for its colour (SmoothPlastic, a pale grey or blue)'
				)
			else
				local sheets, mist, rec, problems = Fog.lay(spec, playAt, { x0, z0, x1, z1 }, function(x, z)
					local best: number? = nil
					for _, wop in waterOps do
						local surface = wop.center[2] + wop.size[2] / 2
						if
							math.abs(x - wop.center[1]) <= wop.size[1] / 2
							and math.abs(z - wop.center[3]) <= wop.size[3] / 2
							and (groundAt(x, z) or -math.huge) < surface
							and (best == nil or surface > best)
						then
							best = surface
						end
					end
					if best == nil and roleAt(x, z) == "river" then
						best = groundAt(x, z)
					end
					return best
				end)
				for _, m in problems do
					err(path, m)
				end
				if #problems == 0 and rec.fogged == 0 then
					local over = spec.over or "low"
					warn(
						path,
						if over == "water"
							then "fog over water: no water in it (a terrain water box or a painted river) - nothing laid"
							elseif over == "hollows" then "fog in hollows: no hollow in the land here - nothing laid"
							else `fog under {spec.below}: no land lies under that line - nothing laid`
					)
				end
				for _, sh in sheets do
					local p = add(path, {
						name = "Fog",
						mat = spec.mat,
						collide = false,
						query = false,
						sink = false,
						transparency = sh.transparency,
					}, sh.size, sh.pos)
					if p then
						p.castShadow = false
						p.touch = false
						p.fog = true
						p.attributes = { KitFog = sh.layer, KitAudioPass = true }
					end
				end
				for _, m in mist do
					local p = add(path, {
						name = "FogMist",
						mat = spec.mat,
						collide = false,
						query = false,
						sink = false,
						transparency = 1,
						particles = "mist",
					}, { 4, 0.2, 4 }, m.pos)
					if p then
						p.castShadow = false
						p.touch = false
						p.fog = true
					end
				end
				table.insert(fogLaid, { path = path, sheets = rec.sheets, fogged = rec.fogged, cells = rec.cells })
			end
		elseif kind == "falls" then
			-- { top: [x, y, z], height, width, yaw, mat (the falling sheet), foam?: mat, ground? } — a waterfall: a
			--   sheet of falling water from a lip, a foam slab and mist where it lands
			local t = spec.top or { 0, 40, 0 }
			local h, w = spec.height or 30, spec.width or 12
			local r = World.rotation({ 0, spec.yaw or 0, 0 })
			if spec.bottom then -- a cascade down a slope: the sheet runs lip -> foot, a little proud of the rock
				local b = spec.bottom
				local d = { b[1] - t[1], b[2] - t[2], b[3] - t[3] }
				local len = math.sqrt(d[1] ^ 2 + d[2] ^ 2 + d[3] ^ 2)
				add(
					path,
					{ name = "Falls", mat = spec.mat, collide = false, transparency = 0.2, sink = false },
					{ len, 1.2, w },
					{
						(t[1] + b[1]) / 2,
						(t[2] + b[2]) / 2 + 2,
						(t[3] + b[3]) / 2,
					},
					World.alongX(d)
				)
				add(path, {
					name = "Foam",
					mat = spec.foam or spec.mat,
					collide = false,
					sink = false,
					particles = "mist",
				}, { w + 6, 0.4, w + 6 }, { b[1], b[2] + 0.3, b[3] })
				table.insert(groups, { name = spec.name or "Falls", parts = current, stream = spec.stream }) -- (continue skips the loop's own insert)
				continue
			end
			add(
				path,
				{ name = "Falls", mat = spec.mat, collide = false, transparency = 0.25, sink = false },
				{ w, h, 1.2 },
				{
					t[1],
					t[2] - h / 2,
					t[3],
				},
				r
			)
			add(
				path,
				{ name = "FallsLip", mat = spec.mat, collide = false, transparency = 0.25, sink = false },
				{ w, 1.4, 3 },
				{
					t[1] - r[1][3] * 1.5,
					t[2],
					t[3] - r[3][3] * 1.5,
				},
				r
			)
			add(path, {
				name = "Foam",
				mat = spec.foam or spec.mat,
				collide = false,
				sink = false,
				particles = "mist",
			}, { w + 4, 0.4, 6 }, { t[1] + r[1][3] * 2, t[2] - h + 0.2, t[3] + r[3][3] * 2 }, r)
		elseif kind == "palisade" then
			-- { points: [[x, z], ...], height, radius?: 1.2, mat, gaps?: [{ at, width }] (studs along the line), seed,
			--   ground } — a wall of upright logs, each standing on the land, heights uneven
			local pts = spec.points
			if type(pts) ~= "table" or #pts < 2 then
				err(path, "palisade needs at least 2 points [[x, z], ...]")
				continue
			end
			local rnd = lcg(spec.seed or 1)
			local r, hgt = spec.radius or 1.2, spec.height or 12
			local spacing = r * 1.96
			local walked = 0
			for k = 1, #pts - 1 do
				local a, b = pts[k], pts[k + 1]
				local len = math.sqrt((b[1] - a[1]) ^ 2 + (b[2] - a[2]) ^ 2)
				if len < 0.01 then -- a repeated point: nothing to walk
					continue
				end
				local d = (spacing - walked % spacing) % spacing
				while d <= len do
					local along = walked + d
					local open = false
					for _, g in spec.gaps or {} do
						if math.abs(along - g.at) < (g.width or 8) / 2 then
							open = true
						end
					end
					if not open then
						local x, z = a[1] + (b[1] - a[1]) * d / len, a[2] + (b[2] - a[2]) * d / len
						local base = if spec.ground == true then (groundAt(x, z) or 0) else (spec.y or 0)
						local h = hgt * (0.86 + rnd() * 0.28)
						add(
							path,
							{ name = "Log", mat = spec.mat, shape = "Cylinder" },
							{ h + 2, r * 2 * (0.9 + rnd() * 0.2), r * 2 },
							{ x, base + h / 2 - 1, z },
							World.rotation({ (rnd() - 0.5) * 4, rnd() * 360, 90 })
						)
					end
					d += spacing
				end
				walked += len
			end
		elseif kind == "spawn" then
			local p = spec.pos
			local part = add(
				path,
				{ name = "Spawn", mat = spec.mat or next(palette) },
				{ 6, 1, 6 },
				{ p[1], p[2] + 0.5, p[3] }
			)
			if part then
				part.class = "SpawnLocation"
				part.spawn = true
			end
		elseif kind == "fit" then
			-- { "fit": { kind, name?, size?: [w, h, d], pos: [x, y, z], from?: [x, z], to?: [x, z], ... } }: a claim only
			-- (no part): kit world check holds it to the scale sheet and, for an alley / street / run wall, MEASURES it.
			-- An alley / street on sloping ground adds "ground": [its floor's height at from, at to] and, where the
			-- hill climbs across it, "cross": studs up for every stud to its left: its width is then read in a band
			-- that follows the floor's plane (a town on a slope writes both: kit/lib/worldtown.luau)
			if type(spec.kind) ~= "string" or type(spec.pos) ~= "table" then
				err(path, '"fit" needs kind + pos (and size, or from / to)')
			else
				local f = table.clone(spec)
				f.path = path
				table.insert(fits, f)
			end
		else
			err(
				path,
				`unknown generator "{tostring(kind)}" (part | fit | town | mesh | wall | floor | stairs | ring | grid | scatter | room | dungeon | cave | tiles | cover | path | breakable | building | tree | forest | ruin | tower | bridge | grace | horizon | rocks | cliffs | story | arch | palisade | peak | city | crosswalk | row | ziggurat | falls | spawn | decal | prefab | trails | fog)`
			)
		end
		table.insert(groups, {
			-- (a placed prefab's step carries its placement's name: Market_1.Stall_2.Counter)
			name = (if stepPlaces[i] then stepPlaces[i].prefix .. "." else "")
				.. (spec.name or (kind:sub(1, 1):upper() .. kind:sub(2))),
			parts = current,
			stream = spec.stream,
		})
	end
	finishTurn() -- (the last step's: before any gate below reads where a part stands)
	finishPlace()
	-- QUOINS ON A BUTTED CORNER: a corner that stands against another building's wall (a row of houses meeting at a
	-- court's corner) is no free corner - its quoins were wedged into the half-stud between the two (looked at in
	-- GothicCourtyard, 2026-11-19). Read where every part finally stands (a turned or placed step has moved them).
	if #quoined > 0 then
		local walls: { Part } = {}
		for _, p in parts do
			if p.name == "Wall" then
				table.insert(walls, p)
			end
		end
		local function box(p: Part): ({ number }, { number })
			local lo, hi = {}, {}
			for a = 1, 3 do
				local e = 0
				for b = 1, 3 do
					e += math.abs(p.rot[a][b]) * p.size[b] / 2
				end
				lo[a], hi[a] = p.pos[a] - e, p.pos[a] + e
			end
			return lo, hi
		end
		local gone: { [Part]: boolean } = {}
		for _, q in quoined do
			local p, R, m = q.part, q.part.rot, q.c
			local wx = p.pos[1] - (R[1][1] * m[1] + R[1][2] * m[2] + R[1][3] * m[3])
			local wz = p.pos[3] - (R[3][1] * m[1] + R[3][2] * m[2] + R[3][3] * m[3])
			local y0, y1 = p.pos[2] - p.size[2] / 2, p.pos[2] + p.size[2] / 2
			for _, w in walls do
				local owner = if w.attributes then w.attributes.KitBlockout else nil
				if owner == nil or owner ~= q.owner then
					local lo, hi = box(w)
					-- (in the wall's own frame: a turned wall's axis-aligned box is far bigger than it - a fresh review)
					local dx, dz = wx - w.pos[1], wz - w.pos[3]
					local ax = math.abs(w.rot[1][1] * dx + w.rot[3][1] * dz)
					local az = math.abs(w.rot[1][3] * dx + w.rot[3][3] * dz)
					if
						ax <= w.size[1] / 2 + World.QUOIN_BUTT
						and az <= w.size[3] / 2 + World.QUOIN_BUTT
						and lo[2] < y1 - 0.5
						and hi[2] > y0 + 0.5
					then
						gone[p] = true
						break
					end
				end
			end
		end
		if next(gone) then
			local function keep(list: { Part }) -- (in place: other tables may hold this list)
				local n = 0
				for i = 1, #list do
					local p = list[i]
					if not gone[p] then
						n += 1
						list[n] = p
					end
				end
				for i = #list, n + 1, -1 do
					list[i] = nil
				end
			end
			keep(parts)
			for _, g in groups do
				keep(g.parts)
			end
		end
	end
	-- (the blueprint's top says only "fog": false - the haze alone, meant; low fog is a step in "build")
	if bp.fog ~= nil and bp.fog ~= false then
		err(
			"fog",
			'at the top of a blueprint "fog" is only false (the haze alone, meant): low fog is a step in "build": { "fog": { "over": "low", "below": <height>, "mat": "<palette>" } }'
		)
	end
	-- SNOW AND DUST ON WHAT IS BUILT (kit/lib/worldcover.luau): laid when every part stands where it will stand
	local coverRecord: any = nil
	if bp.cover ~= nil then
		local wrong = Cover.problems(bp.cover)
		for _, problem in wrong do
			err("cover", problem)
		end
		if #wrong == 0 and bp.cover ~= false then
			local slabs, rec = Cover.lay(parts, bp.cover, groundAt)
			coverRecord = rec
			-- (each slab goes with the part it lies on: the same Model, the same streaming)
			local groupOf: { [any]: any } = {}
			for _, g in groups do
				for _, q in g.parts do
					groupOf[q] = g
				end
			end
			for _, slab in slabs do
				local owner = parts[slab.owner]
				table.insert(parts, slab)
				local g = owner and groupOf[owner]
				if g then
					table.insert(g.parts, slab)
				else
					table.insert(groups, { name = "Cover", parts = { slab }, stream = nil })
				end
			end
			if rec.capped then
				warn("cover", `more than {Cover.MOST} faces take snow or dust: the rest are left bare`)
			end
		end
	end

	for _, name in scanOrder do
		local o = scanOff[name]
		local span = if o.hi - o.lo < 0.05
			then string.format("%.1f", o.lo)
			else string.format("%.1f to %.1f", o.lo, o.hi)
		warn(
			o.path,
			`the scanned "{name}" is {string.format("%.1f", o.r.size[2])} studs tall (a real {o.r.scan.metres} m along its {o.r.scan.axis}) but is set {span} tall {if o.n
					== 1
				then "here"
				else `in {o.n} places (the first here)`}: a scanned thing keeps its real size (give a size near it, or place it with a mesh step)`
		)
	end

	local missing = {}
	for n in meshesNoId do
		table.insert(missing, n)
	end
	if #missing > 0 then
		table.sort(missing)
		warn(
			"meshes",
			`{#missing} world mesh(es) not uploaded yet ({table.concat(missing, ", ")}): Roblox shows nothing for them until lune run kit upload`
		)
	end
	local trimsMissing = {}
	for n in trimsNoId do
		table.insert(trimsMissing, n)
	end
	if #trimsMissing > 0 then
		table.sort(trimsMissing)
		warn(
			"meshes",
			`{#trimsMissing} trim map(s) not uploaded yet ({table.concat(trimsMissing, ", ")}): the modules on them wear their palette colour, no SurfaceAppearance, until lune run kit upload`
		)
	end

	-- ---------------------------------------------------------------- gates
	if #parts > BUDGET_MAX then
		err(
			"parts",
			`{#parts} parts — over the {BUDGET_MAX} budget; merge pieces or use meshes{if coverRecord
				then ` ({coverRecord.snow + coverRecord.dust} of them slabs of snow and dust: "cover")`
				else ""}`
		)
	elseif #parts > BUDGET_WARN then
		warn("parts", `{#parts} parts — heavy for mobile (> {BUDGET_WARN})`)
	end
	local spawns = 0
	for _, p in parts do
		if p.pos[2] - p.size[2] / 2 < KILL_PLANE then
			err(p.name, `below the kill plane (y {p.pos[2]}) — Roblox destroys it`)
		end
		if p.spawn then
			spawns += 1
		end
	end
	if spawns == 0 then
		warn("spawn", "no spawn step — players will spawn at the default location")
	end
	-- spawns buried: a point 3 studs above the pad must not be inside any other solid part
	local function inside(pt: { number }, q: Part): boolean
		local d = { pt[1] - q.pos[1], pt[2] - q.pos[2], pt[3] - q.pos[3] }
		-- into the part's local frame: R^T * d
		local r = q.rot
		local lx = r[1][1] * d[1] + r[2][1] * d[2] + r[3][1] * d[3]
		local ly = r[1][2] * d[1] + r[2][2] * d[2] + r[3][2] * d[3]
		local lz = r[1][3] * d[1] + r[2][3] * d[2] + r[3][3] * d[3]
		return math.abs(lx) < q.size[1] / 2 and math.abs(ly) < q.size[2] / 2 and math.abs(lz) < q.size[3] / 2
	end
	for _, s in parts do
		if s.spawn then
			local probe = { s.pos[1], s.pos[2] + 3, s.pos[3] }
			for _, q in parts do
				if q ~= s and q.collide and inside(probe, q) then
					err(
						s.name,
						`spawn at ({s.pos[1]}, {s.pos[3]}) is buried inside "{q.name}" — move it into open space`
					)
					break
				end
			end
		end
	end
	-- z-fighting: axis-aligned faces on the same plane, facing the same way, overlapping in area
	local buckets: { [string]: { any } } = {}
	for idx, p in parts do
		if not p.axisAligned or p.class ~= "Part" or (p.shape and p.shape ~= "Block") or p.transparency >= 1 then
			continue
		end
		for axis = 1, 3 do
			for _, sign in { -1, 1 } do
				local plane = p.pos[axis] + sign * p.size[axis] / 2
				local u, v = axis % 3 + 1, (axis + 1) % 3 + 1
				local key = `{axis}:{sign}:{math.floor(plane * 1000 + 0.5)}`
				buckets[key] = buckets[key] or {}
				table.insert(buckets[key], {
					idx = idx,
					u0 = p.pos[u] - p.size[u] / 2,
					u1 = p.pos[u] + p.size[u] / 2,
					v0 = p.pos[v] - p.size[v] / 2,
					v1 = p.pos[v] + p.size[v] / 2,
				})
			end
		end
	end
	-- A face pressed against an opposite-facing surface on the same plane (e.g. two bottoms resting on the
	-- ground) is never visible, so it can't flicker: skip overlaps fully covered by such a surface.
	local function hidden(key: string, u0: number, u1: number, v0: number, v1: number): boolean
		local axis, sign, plane = string.match(key, "^(%d):(%-?%d):(%-?%d+)$")
		local opposite = buckets[`{axis}:{-tonumber(sign) :: number}:{plane}`]
		for _, o in opposite or {} do
			if o.u0 <= u0 + 0.01 and o.u1 >= u1 - 0.01 and o.v0 <= v0 + 0.01 and o.v1 >= v1 - 0.01 then
				return true
			end
		end
		return false
	end
	local zfight, reported = 0, {}
	for key, list in buckets do
		for a = 1, #list do
			for b = a + 1, #list do
				local A, B = list[a], list[b]
				local ou = math.min(A.u1, B.u1) - math.max(A.u0, B.u0)
				local ov = math.min(A.v1, B.v1) - math.max(A.v0, B.v0)
				if
					ou > 0.01
					and ov > 0.01
					and not hidden(
						key,
						math.max(A.u0, B.u0),
						math.min(A.u1, B.u1),
						math.max(A.v0, B.v0),
						math.min(A.v1, B.v1)
					)
				then
					zfight += 1
					local pa, pb = parts[A.idx], parts[B.idx]
					local pairKey = A.idx .. "/" .. B.idx
					if not reported[pairKey] and zfight <= 5 then
						reported[pairKey] = true
						warn(
							pa.name,
							`z-fighting with "{pb.name}" near ({math.floor(pa.pos[1])}, {math.floor(pa.pos[2])}, {math.floor(
								pa.pos[3]
							)}) — offset one face by 0.01+ or merge them`
						)
					end
				end
			end
		end
	end
	if zfight > 5 then
		warn("parts", `{zfight} coplanar overlapping faces in total (flicker in game)`)
	end
	-- W5, WHICH LAMPS CAST SHADOWS ("shadows": "auto" | { "most": 16 }; kit/lib/worldlight.luau Light.pick): the
	-- brightest, widest lamps first, never two a pace apart, never more than "most" within World.SHADOW_REACH of one;
	-- every other lamp "shadows": false. A lamp that says "shadows" itself keeps its word.
	local shadowPlan = nil
	if bp.shadows ~= nil then
		local most = if bp.shadows == "auto"
			then WorldLight.MOST
			elseif type(bp.shadows) == "table" and type(bp.shadows.most) == "number" then bp.shadows.most
			else nil
		if most == nil or most ~= most or most < 0 or most > World.SHADOW_MAX then
			err(
				"shadows",
				`"shadows" is "auto" or \{ "most": 0..{World.SHADOW_MAX} } (lamps casting shadows within {World.SHADOW_REACH} studs of one)`
			)
		else
			local lamps, owners = {}, {}
			for _, p in parts do
				for _, c in p.children or {} do
					if c.kind == "light" and type(c.spec) == "table" and c.spec.shadows == nil then
						table.insert(lamps, {
							x = p.pos[1],
							z = p.pos[3],
							range = c.spec.range or 16,
							brightness = c.spec.brightness or 2,
						})
						table.insert(owners, c)
					end
				end
			end
			local chosen = WorldLight.pick(lamps, most, World.SHADOW_REACH)
			local on = {}
			for _, i in chosen do
				on[i] = true
			end
			for i, c in owners do
				c.spec = table.clone(c.spec) -- (a palette's or a recipe's table is shared: never written on)
				c.spec.shadows = on[i] == true
			end
			shadowPlan = {
				lamps = #lamps,
				casters = #chosen,
				worst = WorldLight.worst(lamps, chosen, World.SHADOW_REACH),
				most = most,
			}
		end
	end
	-- LIGHTS THAT CAST SHADOWS (LIMITATIONS_FIXES_V3.md stage F.2): each one renders the scene again from where it
	-- stands, so a player who sees many at once pays for all of them. Counted round every such light, within
	-- World.SHADOW_REACH studs across the ground (about the streaming radius): over World.SHADOW_WARN a warning, over
	-- World.SHADOW_MAX an error. (On 2026-11-18 no world in the repo had one: GothicCourtyard's 52 lights,
	-- SampleCity's 175 - every one Shadows = false.)
	do
		local shadowed = {}
		for _, p in parts do
			for _, c in p.children or {} do
				if c.kind == "light" and type(c.spec) == "table" and c.spec.shadows == true then
					table.insert(shadowed, { p = p, x = p.pos[1], z = p.pos[3] })
				end
			end
		end
		local worst, at = 0, nil
		local r2 = World.SHADOW_REACH * World.SHADOW_REACH
		for _, a in shadowed do
			local n = 0
			for _, b in shadowed do
				if (a.x - b.x) ^ 2 + (a.z - b.z) ^ 2 <= r2 then
					n += 1
				end
			end
			if n > worst then
				worst, at = n, a
			end
		end
		if at and worst > World.SHADOW_WARN then
			local say = if worst > World.SHADOW_MAX then err else warn
			say(
				at.p.name,
				`{worst} lights that cast shadows within {World.SHADOW_REACH} studs of the one near ({math.floor(at.x)}, {math.floor(
					at.z
				)}) - at most {if worst > World.SHADOW_MAX then World.SHADOW_MAX else World.SHADOW_WARN} (each renders the scene again): give the rest "shadows": false`
			)
		end
	end

	-- ---------------------------------------------------------------- Rojo model
	local function partModel(p: Part): any
		local props: { [string]: any } = {
			Anchored = p.anchored,
			CanCollide = p.collide,
			CanQuery = if p.query == false then false else nil,
			CanTouch = if p.touch == false then false else nil,
			Size = { Vector3 = p.size },
			CFrame = { CFrame = { position = p.pos, orientation = p.rot } },
			Color = { Color3uint8 = { math.floor(p.color[1]), math.floor(p.color[2]), math.floor(p.color[3]) } },
			Material = p.material,
			Transparency = p.transparency,
			CastShadow = if p.castShadow == false then false else nil,
			TopSurface = "Smooth",
			BottomSurface = "Smooth",
		}
		if p.shape and p.class == "Part" then
			props.Shape = p.shape
		end
		if p.class == "SpawnLocation" then
			props.Neutral = true
			props.Duration = 0
		end
		if p.attributes then
			local attrs = {}
			for k, v in p.attributes do
				attrs[k] = if type(v) == "boolean"
					then { Bool = v }
					elseif type(v) == "number" then { Float64 = v }
					else { String = tostring(v) }
			end
			props.Attributes = { Attributes = attrs }
		end
		local kids = nil
		for _, c in p.children or {} do
			kids = kids or {}
			if c.kind == "light" then
				local l = c.spec
				local col = l.color or { 255, 214, 140 }
				local cls = if l.type == "spot" then "SpotLight" else "PointLight"
				local lp: { [string]: any } = {
					Brightness = l.brightness or 2,
					Range = math.clamp(l.range or 16, 0, 60),
					Color = { Color3 = { col[1] / 255, col[2] / 255, col[3] / 255 } },
					Shadows = l.shadows == true,
				}
				if cls == "SpotLight" then
					lp.Angle = l.angle or 60
				end
				table.insert(kids, { Name = "KitLight", ClassName = cls, Properties = lp })
			elseif c.kind == "decal" then
				local dp: { [string]: any } = { Texture = c.id, Face = c.face, Transparency = c.transparency or 0 }
				if c.tint then
					dp.Color3 = { Color3 = { c.tint[1] / 255, c.tint[2] / 255, c.tint[3] / 255 } }
				end
				table.insert(kids, { Name = "KitDecal", ClassName = "Decal", Properties = dp })
			elseif c.kind == "particles" then
				table.insert(kids, { Name = c.preset, ClassName = "ParticleEmitter", Properties = PARTICLES[c.preset] })
			elseif c.kind == "surface" then
				-- a W3 module's trim sheet (placeModule): Rojo takes a map's Content as a plain string (kit/lib/models.luau)
				table.insert(kids, { Name = "SurfaceAppearance", ClassName = "SurfaceAppearance", Properties = c.maps })
			end
		end
		return { Name = p.name, ClassName = p.class, Properties = props, Children = kids }
	end
	-- STREAMING + LOD (AAA gap W11; "streaming": { "cell": 256, "lod": true }): a step whose parts spread wider than a
	-- cell (a forest, a scatter) is split into one Model per cell, so streaming and the far stand-in mesh
	-- (LevelOfDetail = StreamingMesh) work per area, never for a map-wide Model
	local streaming = if type(bp.streaming) == "table" then bp.streaming else nil
	local cellSize = if streaming then math.max(64, tonumber(streaming.cell) or 256) else math.huge
	local lodProps = if streaming and streaming.lod ~= false then { LevelOfDetail = "StreamingMesh" } else nil
	-- LOADING INTENT (kit/lib/worldstream.luau; the owner's W-R03): how its players move, what must never be
	-- missing, where a player is sent to
	if streaming then
		local _, intentProblems = Stream.intent(streaming)
		for _, problem in intentProblems do
			err("streaming", problem)
		end
	end
	local always = 0
	local children = {}
	for _, g in groups do
		if #g.parts > 0 then
			local x0, x1, z0, z1 = math.huge, -math.huge, math.huge, -math.huge
			for _, p in g.parts do
				x0, x1 = math.min(x0, p.pos[1]), math.max(x1, p.pos[1])
				z0, z1 = math.min(z0, p.pos[3]), math.max(z1, p.pos[3])
			end
			-- the skyline (backdrop: the great tree, far ranges, peaks) is never split and never streams out
			local backdrop = true
			for _, p in g.parts do
				backdrop = backdrop and p.backdrop == true
			end
			-- the step's own word: "always" (Persistent), "whole" (Atomic), "area" / none (with its place)
			local mode, badWord = Stream.mode(g.stream)
			if badWord then
				err(`{g.name}.stream`, badWord)
				mode = ""
			elseif g.stream ~= nil and not streaming then
				warn(`{g.name}.stream`, '"stream" does nothing: the blueprint has no "streaming" block')
				mode = ""
			end
			if streaming and (backdrop or mode == "Persistent") then
				if not backdrop then
					always += #g.parts
				end
				local kids = {}
				for _, p in g.parts do
					table.insert(kids, partModel(p))
				end
				table.insert(children, {
					Name = g.name,
					ClassName = "Model",
					Properties = { ModelStreamingMode = "Persistent" },
					Children = kids,
				})
			elseif streaming and mode == "Atomic" then
				-- one piece, however wide: it is never cut into cells (half of it would arrive without the rest)
				local kids = {}
				for _, p in g.parts do
					table.insert(kids, partModel(p))
				end
				-- (how far it really reaches: its parts' own boxes, not their middles)
				local ax0, ax1, az0, az1 = math.huge, -math.huge, math.huge, -math.huge
				for _, p in g.parts do
					local ex = math.abs(p.rot[1][1]) * p.size[1] / 2
						+ math.abs(p.rot[1][2]) * p.size[2] / 2
						+ math.abs(p.rot[1][3]) * p.size[3] / 2
					local ez = math.abs(p.rot[3][1]) * p.size[1] / 2
						+ math.abs(p.rot[3][2]) * p.size[2] / 2
						+ math.abs(p.rot[3][3]) * p.size[3] / 2
					ax0, ax1 = math.min(ax0, p.pos[1] - ex), math.max(ax1, p.pos[1] + ex)
					az0, az1 = math.min(az0, p.pos[3] - ez), math.max(az1, p.pos[3] + ez)
				end
				local across = math.max(ax1 - ax0, az1 - az0)
				if across > 2 * cellSize then
					warn(
						`{g.name}.stream`,
						`"whole": {math.floor(across + 0.5)} studs across arrives all at once, as soon as any part of it is near a player - more than two cells ({cellSize} studs each) is a lot to send in one piece`
					)
				end
				local props: { [string]: any } = { ModelStreamingMode = "Atomic" }
				for k, v in lodProps or {} do
					props[k] = v
				end
				table.insert(children, { Name = g.name, ClassName = "Model", Properties = props, Children = kids })
			elseif streaming and (x1 - x0 > cellSize or z1 - z0 > cellSize) then
				local cells: { [string]: { any } } = {}
				local order = {}
				for _, p in g.parts do
					local key = `{math.floor(p.pos[1] / cellSize)}_{math.floor(p.pos[3] / cellSize)}`
					if not cells[key] then
						cells[key] = {}
						table.insert(order, key)
					end
					table.insert(cells[key], partModel(p))
				end
				table.sort(order)
				for _, key in order do
					table.insert(
						children,
						{ Name = `{g.name}_c{key}`, ClassName = "Model", Properties = lodProps, Children = cells[key] }
					)
				end
			else
				local kids = {}
				for _, p in g.parts do
					table.insert(kids, partModel(p))
				end
				table.insert(children, { Name = g.name, ClassName = "Model", Properties = lodProps, Children = kids })
			end
		end
	end
	if always > Stream.ALWAYS_MOST then
		err(
			"streaming",
			`{always} parts are marked "stream": "always" - Roblox keeps them loaded for every player wherever they stand, and its own page says that is for a few things only: {Stream.ALWAYS_MOST} at most (a landmark's silhouette, not a district)`
		)
	end
	-- ARRIVALS: the places a player is sent to. Each is a small unseen part in a model that never streams out
	-- (the server and every client can ask where it is); src/kit/WorldStream.luau asks Roblox for the ground round
	-- it before the player is moved. An arrival must stand on something: a floor of the world within
	-- ARRIVAL_DROP studs under it, or the land
	local streamExtra: any = nil
	if streaming then
		local arrivals, arrivalProblems = Stream.arrivals(streaming)
		for _, problem in arrivalProblems do
			err("streaming.arrivals", problem)
		end
		local kids = {}
		for _, a in arrivals do
			local x, y, z = a.pos[1], a.pos[2], a.pos[3]
			-- where a look straight down from `fromY` first meets a part (its own box, turned as it stands - a
			-- ramp's surface where the player stands, not the top of the box round it): the height, or nil
			local function under(p: Part, fromY: number): number?
				local ox, oy, oz = x - p.pos[1], fromY - p.pos[2], z - p.pos[3]
				local r = p.rot
				local t0, t1 = 0, math.huge
				for axis = 1, 3 do
					-- (the part's own axis `axis` is column `axis` of its rotation)
					local o = ox * r[1][axis] + oy * r[2][axis] + oz * r[3][axis]
					local d = -r[2][axis]
					local half = p.size[axis] / 2
					if math.abs(d) < 1e-9 then
						if math.abs(o) > half then
							return nil
						end
					else
						local ta, tb = (-half - o) / d, (half - o) / d
						if ta > tb then
							ta, tb = tb, ta
						end
						t0, t1 = math.max(t0, ta), math.min(t1, tb)
						if t0 > t1 then
							return nil
						end
					end
				end
				return fromY - t0
			end
			-- its feet stand on something: the land, or a part's surface within ARRIVAL_DROP under them ...
			local floor = false
			local land = groundAt(x, z)
			if land ~= nil and land <= y + 0.5 and y - land <= Stream.ARRIVAL_DROP then
				floor = true
			end
			-- ... and nothing solid stands where the body will: from half a stud over the feet to 5.5 (an R6 rig)
			local within: string? = nil
			if land ~= nil and land > y + 0.5 then
				within = "the land"
			end
			for _, p in parts do
				if p.collide and not p.backdrop and p.class ~= "SpawnLocation" then
					local top = under(p, y + 0.5)
					if top ~= nil and y - top <= Stream.ARRIVAL_DROP then
						floor = true
					end
					local head = under(p, y + 5.5)
					if head ~= nil and head > y + 0.5 + 1e-6 then
						within = within or p.name
					end
				end
			end
			if not floor then
				err(
					"streaming.arrivals",
					`arrival "{a.name}" at ({x}, {y}, {z}) stands on nothing: no floor of the world within {Stream.ARRIVAL_DROP} studs under it (a player sent there falls)`
				)
			elseif within then
				err(
					"streaming.arrivals",
					`arrival "{a.name}" at ({x}, {y}, {z}) stands inside {within}: a body 5.5 studs tall has no room there ("pos" is where the feet stand)`
				)
			end
			table.insert(kids, {
				Name = a.name,
				ClassName = "Part",
				Properties = {
					Anchored = true,
					CanCollide = false,
					CanQuery = false,
					CanTouch = false,
					Transparency = 1,
					Size = { Vector3 = { 1, 1, 1 } },
					CFrame = { CFrame = { position = { x, y, z }, orientation = IDENTITY } },
					Attributes = { Attributes = { KitArrival = { String = a.name } } },
				},
			})
		end
		if #kids > 0 then
			table.insert(children, {
				Name = "KitArrivals",
				ClassName = "Model",
				Properties = { ModelStreamingMode = "Persistent" },
				Children = kids,
			})
		end
		local intent = Stream.intent(streaming)
		streamExtra = { need = Stream.need(intent), always = always, arrivals = arrivals }
	end
	-- lighting + terrain: validated here, applied at runtime by the kit's Environment script
	local env, envIssues = Environment.compile(bp)
	if env and next(bedsOf) ~= nil then
		-- (the land the game writes carries its beds: the ground ops in the order they were read above)
		local gi = 0
		for _, op in env.terrain or {} do
			if op.kind == "ground" then
				gi += 1
				if bedsOf[gi] then
					op.spec = table.clone(op.spec) -- (never the blueprint's own table)
					op.spec.beds = bedsOf[gi]
				end
			end
		end
	end
	for _, issue in envIssues do
		table.insert(issues, issue)
	end
	if env then
		-- heightmap samples ride as ModuleScripts INSIDE the model (KitTerrain<i>_<k>): too big for an attribute, and
		-- one script's Source is capped near 200,000 characters in Roblox (a 257 x 257 grid is ~390 KB), so they are
		-- CHUNKED under World.MODULE_CHARS each; the runtime joins the chunks in order, then destroys the modules
		-- (they are for the server's start only: never replicated to players)
		for i, op in env.terrain or {} do
			local s = op.spec and op.spec.samples
			if s and s.heights then
				local names = {}
				local part, size, k = {}, 0, 0
				local function flush()
					if #part == 0 then
						return
					end
					k += 1
					local name = `KitTerrain{i}_{k}`
					table.insert(names, name)
					table.insert(children, {
						Name = name,
						ClassName = "ModuleScript",
						Properties = {
							Source = `-- generated by kit world (heightmap samples, chunk {k})\nreturn \{ `
								.. table.concat(part, ",")
								.. " }\n",
						},
					})
					part, size = {}, 0
				end
				for _, v in s.heights do
					local t = tostring(v)
					if size + #t + 1 > World.MODULE_CHARS then
						flush()
					end
					table.insert(part, t)
					size += #t + 1
				end
				flush()
				local splatNames = nil
				if type(s.splat) == "string" then -- the painted roles, one character per cell
					splatNames = {}
					for j = 1, math.ceil(#s.splat / World.MODULE_CHARS) do
						local name = `KitTerrainPaint{i}_{j}`
						table.insert(splatNames, name)
						table.insert(children, {
							Name = name,
							ClassName = "ModuleScript",
							Properties = {
								-- (%q: role 44 is a backslash, which a plain "..." would read as an escape)
								Source = "-- generated by kit world (terrain paint: roles per cell)\nreturn "
									.. string.format(
										"%q",
										string.sub(s.splat, (j - 1) * World.MODULE_CHARS + 1, j * World.MODULE_CHARS)
									)
									.. "\n",
							},
						})
					end
				end
				op.spec = table.clone(op.spec)
				op.spec.samples =
					{ nx = s.nx, nz = s.nz, modules = names, splatModules = splatNames, palette = s.palette }
			end
		end
	end
	finishLandmark() -- (the last step's)
	-- GROUND CONTACT (AAA gap W5; "contact": { material?: "Ground", max?: 600 }): nothing meets the grass with a clean
	-- seam - a ragged skirt of worn ground is painted under every colliding part and solid mesh whose foot touches the
	-- land (floors, stairs, spawns and backdrops skipped), several jittered 4-stud patches round the footprint
	local contact: any = nil
	if type(bp.contact) == "table" and #groundOps > 0 then
		local cmat = bp.contact.material or "Ground"
		local budget = bp.contact.max or 600
		local rndc = lcg(bp.contact.seed or 11)
		-- snapped to the terrain's 4-stud grid and deduplicated: one flat list of integers (x, y, z, x, y, z ...),
		-- small enough for the environment attribute (2911 raw points were 190k characters)
		local seen: { [string]: boolean } = {}
		local flat: { number } = {}
		local function cell(x: number, y: number, z: number)
			local cx, cz = math.floor(x / 4) * 4 + 2, math.floor(z / 4) * 4 + 2
			local key = `{cx},{cz}`
			if not seen[key] then
				seen[key] = true
				table.insert(flat, cx)
				table.insert(flat, math.floor(y + 0.5))
				table.insert(flat, cz)
			end
		end
		local skip = { Slab = true, Stair = true, Spawn = true, Floor = true, Rug = true }
		for _, p in parts do
			if budget <= 0 then
				break
			end
			local solid = (p.collide and not p.mesh) or p.meshCollide == true
			if solid and not p.backdrop and not skip[p.name] then
				local ex = math.abs(p.rot[1][1]) * p.size[1] / 2 + math.abs(p.rot[1][3]) * p.size[3] / 2
				local ez = math.abs(p.rot[3][1]) * p.size[1] / 2 + math.abs(p.rot[3][3]) * p.size[3] / 2
				local ey = math.abs(p.rot[2][1]) * p.size[1] / 2
					+ math.abs(p.rot[2][2]) * p.size[2] / 2
					+ math.abs(p.rot[2][3]) * p.size[3] / 2
				local gy = groundAt(p.pos[1], p.pos[3])
				if gy and math.min(ex, ez) >= 1 and p.pos[2] - ey <= gy + 1.5 then
					cell(p.pos[1], gy, p.pos[3])
					local ring = math.clamp(math.floor((ex + ez) / 3), 3, 8)
					for i = 1, ring do
						local a = (i / ring) * 2 * math.pi + rndc() * 0.6
						local rx, rz = (ex + 1.5 + rndc() * 2.5) * math.cos(a), (ez + 1.5 + rndc() * 2.5) * math.sin(a)
						local px, pz = p.pos[1] + rx, p.pos[3] + rz
						cell(px, groundAt(px, pz) or gy, pz)
					end
					budget -= 1
				end
			end
		end
		if #flat > 0 then
			contact = { material = cmat, cells = flat }
		end
	end
	local weatherSpec: any = nil
	if bp.weather ~= nil and bp.weather ~= false then
		if bp.ambient ~= nil then
			err(
				"weather",
				`a world says "ambient" (one weather for ever) or a "weather" cycle, not both: put the {tostring(
					bp.ambient
				)} in the cycle as a stage, or say "weather": false`
			)
		else
			local spec, problems = Weather.read(bp.weather)
			for _, p in problems do
				err("weather", p)
			end
			weatherSpec = spec
		end
	end
	if env then
		if contact then
			env.contact = contact -- ground contact: the runtime wears these 4-stud cells after the trails
		end
		if #paints > 0 then
			env.paint = paints -- worn trails: the runtime wears them into the terrain after it is filled
		end
		if bp.ambient ~= nil then
			if not AMBIENTS[bp.ambient] then
				err(
					"ambient",
					`ambient is "snow" | "rain" | "ash" | "leaves" | "embers" | "sand" (got "{tostring(bp.ambient)}")`
				)
			else
				env.ambient = bp.ambient -- weather around the player (kit client Ambient script; the web viewer)
			end
		end
		-- WEATHER THAT CHANGES: "weather": { "cycle": [ { "ambient", "minutes", "fog"?, "dim"? } .. ], "change": <s> }
		-- (src/kit/WeatherRules.luau reads it; every client plays it off the server's clock). false = one weather
		-- for ever, meant. A world says "ambient" (one weather) or a cycle, not both.
		if weatherSpec then
			env.weather = weatherSpec
		end
		if bp.decoration ~= nil then
			env.decoration = bp.decoration == true -- Roblox's animated grass on Grass terrain
		end
	elseif weatherSpec then
		-- (a world with no lighting, day, wind or terrain carries no environment: its weather would be dropped unsaid)
		err("weather", `a "weather" cycle rides in the world's environment: give the world its "lighting" too`)
	end
	-- terrain MaterialVariants (kit world materials -> kit upload): one per material this world's terrain paints with,
	-- once its three maps are uploaded. They ride into MaterialService (src/materials: Rojo writes the maps, which a
	-- game script cannot); the runtime overrides each base material with its variant (SetBaseMaterialOverride)
	local materialsModel = nil
	if env and env.terrain then
		local used: { [string]: boolean } = {}
		for _, op in env.terrain do
			if op.kind == "ground" and op.spec then
				for _, m in (op.spec.samples and op.spec.samples.palette) or {} do
					used[m] = true
				end
				for _, m in { op.spec.material, op.spec.rock, op.spec.under } do
					if type(m) == "string" then
						used[m] = true
					end
				end
			end
		end
		local reg: { [string]: any } = {}
		local rp = Config.build("terrainmaps") .. "/terrainmaps.json"
		if fs.isFile(rp) then
			local ok, r = pcall(serde.decode, "json" :: any, fs.readFile(rp))
			if ok and type(r) == "table" then
				reg = r
			end
		end
		local function idOf(file: any): string?
			local stem = if type(file) == "string" then string.match(file, "^([%w_]+)%.png$") else nil
			local id = stem and mapIds[stem]
			return if id then `rbxassetid://{string.match(tostring(id), "%d+")}` else nil
		end
		local names = {}
		for m in used do
			table.insert(names, m)
		end
		table.sort(names)
		local variants, waiting, overrides = {}, {}, {}
		for _, m in names do
			local r = reg[m]
			if r then
				local c, n, ro = idOf(r.color), idOf(r.normal), idOf(r.roughness)
				if c and n and ro then
					table.insert(variants, {
						Name = `Kit{m}`,
						ClassName = "MaterialVariant",
						Properties = {
							BaseMaterial = m,
							ColorMap = c,
							NormalMap = n,
							RoughnessMap = ro,
							StudsPerTile = r.studs or 10,
							MaterialPattern = "Organic", -- (breaks the tile grid on terrain)
						},
					})
					table.insert(overrides, { material = m, variant = `Kit{m}` })
				else
					table.insert(waiting, m)
				end
			end
		end
		if #variants > 0 then
			materialsModel = { ClassName = "Folder", Children = variants }
			env.materialVariants = overrides
		end
		if #waiting > 0 then
			warn(
				"materials",
				`{#waiting} terrain material(s) have scanned maps not uploaded yet ({table.concat(waiting, ", ")}): lune run kit upload, then lune run kit world`
			)
		end
	end
	local model: { [string]: any } = { ClassName = "Model", Children = if #children > 0 then children else nil }
	if env then
		model.Properties = {
			Attributes = { Attributes = { KitEnvironment = { String = serde.encode("json", env) } } },
		}
	end
	return model,
		parts,
		issues,
		{
			paints = paints,
			materials = materialsModel,
			landmarks = landmarks,
			fits = fits,
			towns = towns,
			routes = routes,
			ecosystems = ecosystems,
			tiles = tileLayouts,
			decals = decalsLaid,
			prefabs = prefabsPlaced,
			trails = trailsGrown,
			fog = fogLaid,
			cover = coverRecord,
			beds = bedsLaid,
			junctions = junctionsLaid,
			rooms = roomsFurnished,
			shadows = shadowPlan,
			bedsOf = bedsOf,
			onMeshes = onMeshes,
			dungeons = dungeons,
			caves = caves,
			streaming = streamExtra,
		}
end

-- ---------------------------------------------------------------- terrain as data (for the offline analysis)
-- The ground surface height at (x, z) — the SAME formula as src/kit/Environment.luau groundHeight (runtime): Lune
-- has the engine's math.noise, so `kit world check` walks the real hills. Keep the two in step.
local function smooth(t: number): number
	t = math.clamp(t, 0, 1)
	return t * t * (3 - 2 * t)
end

-- a heightmap's samples (kit world terrain), bilinear, relative to the op's centre height
function World.sampleHeight(spec: any, x: number, z: number): number
	local s = spec.samples
	local fx = math.clamp((x - (spec.center[1] - spec.size[1] / 2)) / spec.size[1], 0, 1) * (s.nx - 1)
	local fz = math.clamp((z - (spec.center[3] - spec.size[2] / 2)) / spec.size[2], 0, 1) * (s.nz - 1)
	local ix, iz = math.min(math.floor(fx), s.nx - 2), math.min(math.floor(fz), s.nz - 2)
	local tx, tz = fx - ix, fz - iz
	local function at(a: number, b: number): number
		return s.heights[a * s.nz + b + 1]
	end
	return (at(ix, iz) * (1 - tx) + at(ix + 1, iz) * tx) * (1 - tz)
		+ (at(ix, iz + 1) * (1 - tx) + at(ix + 1, iz + 1) * tx) * tz
end

-- does sound pass through a compiled part? (Roblox Acoustic Simulation: every part blocks unless AudioCanCollide is
-- off). Non-colliding parts pass, except the shells that should still muffle: roofs, eaves, tower tops, glass panes;
-- a spec says it outright with "audio": true (blocks) / false (passes). Mesh placeholders decide by their mesh.
local AUDIO_BLOCKERS =
	{ Roof = true, RoofN = true, RoofS = true, Ridge = true, Eave = true, TowerFloor = true, Pane = true }
function World.audioPass(name: string, collide: boolean, spec: any): boolean
	if type(spec) == "table" and spec.audio ~= nil then
		return spec.audio == false
	end
	if collide or name == "KitMesh" then
		return false
	end
	return not AUDIO_BLOCKERS[name]
end

-- the painted terrain ROLE at (x, z) (meadow, lush, dirt, mud, rock, cliff, snow, sand, scree), or nil when unpainted
function World.roleAt(spec: any, x: number, z: number): string?
	local s = spec.samples
	if not s or type(s.splat) ~= "string" or type(s.roles) ~= "table" then
		return nil
	end
	local fx = math.clamp((x - (spec.center[1] - spec.size[1] / 2)) / spec.size[1], 0, 1) * (s.nx - 1)
	local fz = math.clamp((z - (spec.center[3] - spec.size[2] / 2)) / spec.size[2], 0, 1) * (s.nz - 1)
	local k = math.round(fx) * s.nz + math.round(fz) + 1
	local b = string.byte(s.splat, k)
	return if b then s.roles[b - 47] else nil -- ("0" = 48 -> the first role)
end

function World.groundHeight(spec: any, x: number, z: number): number
	local h
	if spec.samples and spec.samples.heights then
		h = spec.center[2] + World.sampleHeight(spec, x, z)
	else
		local n = spec.noise or {}
		local amp, scale, seed = n.amplitude or 0, n.scale or 80, (n.seed or 1) * 0.6180339
		local f, a, total, norm = 1 / scale, 1, 0, 0
		for _ = 1, n.octaves or 3 do
			total += math.noise(x * f, z * f, seed) * a
			norm += a
			f *= 2
			a *= 0.5
		end
		h = spec.center[2] + amp * (total / norm) * 1.6
	end
	for _, pad in spec.flat or {} do
		local d = math.sqrt((x - pad.center[1]) ^ 2 + (z - pad.center[2]) ^ 2)
		local w = smooth((d - pad.radius) / (pad.radius * 0.6 + 8))
		h = (pad.height or spec.center[2]) * (1 - w) + h * w
	end
	-- (a road's bed cuts and fills it: src/kit/RoadBed.luau - the game's rule, the same file)
	return RoadBed.apply(spec.beds, x, z, h)
end

-- terrain for the analysis: ground ops sampled on a grid (step studs), the solid ops and water as shapes
-- bedsOf = the road beds of each ground op (World.compile's extras.bedsOf): the heights are the land's WITH them
function World.terrainField(bp: any, step: number?, bedsOf: { [number]: { any } }?): any
	if bedsOf == nil and type(bp) == "table" and type(bp.build) == "table" then
		-- (no beds handed in, and a road of the blueprint has one: the build is compiled to find them - every reader
		-- of a world's land reads the land WITH its beds)
		for _, laid in bp.build do
			local road = if type(laid) == "table" then laid.path else nil
			if type(road) == "table" and road.ground == true and road.bed ~= nil and road.bed ~= false then
				local ok, _, _, _, extras = pcall(World.compile, bp)
				bedsOf = if ok and type(extras) == "table" then extras.bedsOf else nil
				break
			end
		end
	end
	local env = Environment.compile(bp)
	local out = { ground = {}, solids = {}, water = {} }
	if not env then
		return out
	end
	if bedsOf then
		local gi = 0
		for _, op in env.terrain or {} do
			if op.kind == "ground" then
				gi += 1
				if bedsOf[gi] then
					op.spec = table.clone(op.spec) -- (never the blueprint's own table)
					op.spec.beds = bedsOf[gi]
				end
			end
		end
	end
	local s = step or 2
	for _, op in env.terrain or {} do
		local spec = op.spec
		if op.kind == "ground" then
			local gs = if spec.backdrop then math.max(s, 8) else s -- scenery: coarser (it is far away)
			local x0, z0 = spec.center[1] - spec.size[1] / 2, spec.center[3] - spec.size[2] / 2
			local nx, nz = math.floor(spec.size[1] / gs) + 1, math.floor(spec.size[2] / gs) + 1
			local heights = table.create(nx * nz)
			for ix = 0, nx - 1 do
				for iz = 0, nz - 1 do
					heights[ix * nz + iz + 1] = math.round(World.groundHeight(spec, x0 + ix * gs, z0 + iz * gs) * 100)
						/ 100
				end
			end
			table.insert(out.ground, {
				x0 = x0,
				z0 = z0,
				step = gs,
				nx = nx,
				nz = nz,
				heights = heights,
				rock = spec.rock,
				rockSlope = spec.rockSlope,
				-- (the surface: the web viewer paints the same materials Environment.ground fills with)
				material = spec.material,
				cy = spec.center and spec.center[2] or 0,
				-- scenery land around the map (far mountains): drawn, never analysed
				backdrop = spec.backdrop,
				layers = spec.layers,
				-- the painted surface (kit world terrain) on its own sample grid: a role per cell + role -> material
				splat = if spec.samples and spec.samples.splat
					then {
						nx = spec.samples.nx,
						nz = spec.samples.nz,
						x0 = x0,
						z0 = z0,
						w = spec.size[1],
						d = spec.size[2],
						roles = spec.samples.splat,
						palette = spec.samples.palette,
					}
					else nil,
			})
		elseif op.kind == "water" then
			table.insert(out.water, { center = spec.center, size = spec.size })
		else
			table.insert(out.solids, { kind = op.kind, spec = spec })
		end
	end
	return out
end

-- ---------------------------------------------------------------- the scratch place (kit world studio)
-- A compiled world model as Roblox Studio can show it with NOTHING uploaded. A mesh skin's placeholder (KitMesh) is
-- invisible until the runtime makes its MeshPart from an uploaded id, and the blockout that skin replaced is hidden
-- under it ("the parts stay as invisible collision") - so, as compiled, Studio would show a town with no walls. In
-- every step that holds a skin the hidden blockout is shown again as plain parts; the placeholders stay invisible; an
-- invisible part of a step with no skin (a barrier the blueprint asked for) is left alone.
-- -> (a copy: the model is not touched, the parts shown again, the skins that have no mesh to show)
function World.scratchModel(model: any): (any, number, number)
	local function deep(v: any): any
		if type(v) ~= "table" then
			return v
		end
		local out = {}
		for k, x in v do
			out[k] = deep(x)
		end
		return out
	end
	local shown, skins = 0, 0
	local function walk(node: any, underSkin: boolean)
		local children = if type(node.Children) == "table" then node.Children else {}
		local here = underSkin
		for _, child in children do
			if child.Name == "KitMesh" then
				here = true
			end
		end
		for _, child in children do
			local props = child.Properties
			if type(props) == "table" and props.Size ~= nil and props.Transparency == 1 then
				if child.Name == "KitMesh" then
					skins += 1
				elseif here then
					props.Transparency = 0
					shown += 1
				end
			end
			walk(child, here)
		end
	end
	local root = deep(model)
	walk(root, false)
	return root, shown, skins
end

-- the Rojo project of a world's scratch place: the world alone under Workspace.KitWorld (its model file beside the
-- project), the kit's runtime in ReplicatedStorage (its Environment applies the world's own light and terrain, as the
-- game does at start), Future lighting, and a marker (Workspace.KitWorldScratch = the world's name) the Studio
-- capture checks before it touches anything - it refuses every other place. `kitPath`: src/kit as seen from the
-- project file's folder (nil: a project with no kit runtime - the place then keeps Studio's default light).
-- `build`: what this place was built from (a digest of the world and its stations), kept in the marker's Build value:
-- Studio does not reload a place file that is rebuilt on disk, so the capture script carries the same key and
-- refuses a place that still shows an older build.
function World.scratchProject(name: string, kitPath: string?, build: string?): any
	return {
		name = World.scratchName(name),
		tree = {
			["$className"] = "DataModel",
			Lighting = { ["$className"] = "Lighting", ["$properties"] = { Technology = "Future" } },
			ReplicatedStorage = {
				["$className"] = "ReplicatedStorage",
				kit = if kitPath then { ["$path"] = kitPath } else nil,
			},
			-- the kit's own two scripts where a game's project puts them, so that PLAY in the scratch place runs
			-- the world as a game does: the land filled, the lighting set, the weather and the time of day running
			-- (found in the first Studio session, 2026-11-15: the place held the kit under ReplicatedStorage only,
			-- where a script does not run - a play session showed a bare model under Studio's default light)
			ServerScriptService = if kitPath
				then {
					["$className"] = "ServerScriptService",
					KitEnvironment = { ["$path"] = `{kitPath}/server/Environment.server.luau` },
				}
				else nil,
			StarterPlayer = if kitPath
				then {
					["$className"] = "StarterPlayer",
					StarterPlayerScripts = {
						["$className"] = "StarterPlayerScripts",
						KitAmbient = { ["$path"] = `{kitPath}/client/Ambient.client.luau` },
					},
				}
				else nil,
			Workspace = {
				["$className"] = "Workspace",
				KitWorldScratch = {
					["$className"] = "StringValue",
					["$properties"] = { Value = name },
					Build = { ["$className"] = "StringValue", ["$properties"] = { Value = build or "" } },
				},
				KitWorld = { ["$className"] = "Folder", [name] = { ["$path"] = `{name}.model.json` } },
			},
		},
	}
end

-- the scratch place's name: its file (<this>.rbxlx) and so its Studio window's title - what the capture looks for
function World.scratchName(name: string): string
	return `KitWorldScratch_{name}`
end

return World

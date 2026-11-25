-- worldroadsteps.spec.luau (kit) — A ROAD ON THE LAND THAT CLIMBS AND LEANS (LIMITATIONS_FIXES_V3.md stage E.3: "banked
-- ... roads (<= 22 deg grade, stone stairs > 16 deg ...)"). A road with "ground": true is laid in short pieces from
-- ground to ground; a piece steeper than World.ROAD_STAIR_DEG was a tilted plank no R6 body walks well. It is now a
-- flight of stone steps about a stud apart in height; a gentler piece BANKS with the land's fall across it (up to
-- World.ROAD_BANK_MAX degrees): a level plank on a hillside stood in the air on its low side.
-- Held here on lands made by hand (a 30-degree climb, a 10-degree climb, an 8- and a 30-degree side slope): steps
-- where it is steep and nowhere else, each tread on the land and a stud or so above the last; no steps when the road
-- says "stairs": false; a piece's roll follows the side slope, capped, and none when it says "bank": false.
-- Not claimed: how a flight looks, or that Roblox's voxels lie where the heights say (that is the engine).
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local World = require("../../lib/world")

local DIR = "build/selftest/worldroadsteps"
local N, STEP = 33, 4 -- (a 128-stud land, a sample every 4 studs, centred on the origin)

-- a land of heights h(x, z), written as a heightmap file (samples x-major, as kit world terrain writes them)
local function land(name: string, h: (number, number) -> number): string
	if not fs.isDir(DIR) then
		fs.writeDir(DIR)
	end
	local heights = {}
	for ix = 0, N - 1 do
		for iz = 0, N - 1 do
			table.insert(heights, h(-64 + ix * STEP, -64 + iz * STEP))
		end
	end
	local path = `{DIR}/{name}.hm.json`
	fs.writeFile(path, serde.encode("json", { nx = N, nz = N, step = STEP, heights = heights }))
	return path
end

local function compile(source: string, more: any?, worldName: string?): ({ any }, { string })
	local road: any =
		{ name = "Lane", mat = "stone", width = 8, ground = true, curve = false, points = { { -50, 0 }, { 50, 0 } } }
	for k, v in more or {} do
		road[k] = v
	end
	local _, parts, issues = World.compile({
		name = worldName or "T",
		palette = { stone = { material = "Cobblestone", color = { 120, 118, 112 } } },
		lighting = "noon",
		terrain = { { heightmap = { center = { 0, 0, 0 }, size = { 128, 128 }, source = source, material = "Grass" } } },
		build = { { path = road } },
	}, { meshes = {} })
	local errors = {}
	for _, i in issues do
		if i.severity == "error" and i.path ~= "spawn" then
			table.insert(errors, i.message)
		end
	end
	return parts, errors
end

local function named(parts: { any }, name: string): { any }
	local out = {}
	for _, p in parts do
		if p.name == name then
			table.insert(out, p)
		end
	end
	table.sort(out, function(a, b)
		return a.pos[1] < b.pos[1]
	end)
	return out
end

-- a climb along x between x = -20 and x = 20 at `deg` degrees, level before and after
local function climb(deg: number): (number, number) -> number
	local k = math.tan(math.rad(deg))
	return function(x: number, _z: number): number
		return math.clamp(x + 20, 0, 40) * k
	end
end

return function()
	test.suite("A road on the land: stone steps where it is steep", function()
		test.case("a 30-degree climb is a flight of steps, a stud or so a tread; the level ends stay road", function()
			local parts, errors = compile(land("climb30", climb(30)))
			check.equal(#errors, 0, table.concat(errors, " | "))
			local steps = named(parts, "Step")
			check.truthy(#steps >= 18, `{#steps} steps`) -- (23 studs of climb)
			local last: number? = nil
			for _, s in steps do
				-- on the climb, never on the level ends
				check.truthy(s.pos[1] > -21 and s.pos[1] < 21, `step at x {s.pos[1]}`)
				local top = s.pos[2] + s.size[2] / 2
				if last then
					local rise = top - last
					check.truthy(rise > 0.5 and rise < 1.3, `a tread {rise} above the last`)
				end
				last = top
			end
			-- the road's own pieces lie on the level ends
			local roads = named(parts, "Road")
			check.truthy(#roads >= 4)
			for _, r in roads do
				check.truthy(r.pos[1] < -15 or r.pos[1] > 15, `road piece at x {r.pos[1]} on the climb`)
			end
		end)

		test.case('a gentle climb stays road; "stairs": false keeps a steep one a ramp', function()
			local gentle = compile(land("climb10", climb(10)))
			check.equal(#named(gentle, "Step"), 0)
			local ramp = compile(land("climb30b", climb(30)), { stairs = false })
			check.equal(#named(ramp, "Step"), 0)
			check.truthy(#named(ramp, "Road") >= 16)
		end)
	end)

	test.suite("A road on the land: banked with the land across it", function()
		local function side(deg: number): (number, number) -> number
			local k = math.tan(math.rad(deg))
			return function(_x: number, z: number): number
				return 30 + z * k
			end
		end
		-- the sine of a road piece's lean across its line: its up axis's share toward -z (rot's second column)
		local function lean(p: any): number
			return -p.rot[3][2]
		end
		test.case("on an 8-degree side slope each piece leans 8 degrees with it", function()
			local parts, errors = compile(land("side8", side(8)))
			check.equal(#errors, 0, table.concat(errors, " | "))
			local roads = named(parts, "Road")
			check.truthy(#roads >= 10)
			for _, r in roads do
				check.truthy(math.abs(lean(r) - math.sin(math.rad(8))) < 0.02, `lean {lean(r)}`)
				-- (and still level along its line: the land does not climb along x)
				check.truthy(math.abs(r.rot[2][1]) < 1e-6)
			end
		end)

		test.case('a 30-degree side slope leans it 12 at most; "bank": false keeps it level', function()
			local steep = compile(land("side30", side(30)))
			for _, r in named(steep, "Road") do
				check.truthy(math.abs(lean(r) - math.sin(math.rad(World.ROAD_BANK_MAX))) < 0.02, `lean {lean(r)}`)
			end
			local level = compile(land("side8b", side(8)), { bank = false })
			for _, r in named(level, "Road") do
				check.truthy(math.abs(lean(r)) < 1e-6)
			end
		end)

		test.case("a world built before the steps keeps its ramps and level planks unless it asks", function()
			World.ROAD_V3_BEFORE.SampleRegion = true -- (a project's built world: the kit ships the list empty)
			local old = compile(land("climb30c", climb(30)), nil, "SampleRegion")
			local asked = compile(land("climb30d", climb(30)), { stairs = true }, "SampleRegion")
			World.ROAD_V3_BEFORE.SampleRegion = nil
			check.equal(#named(old, "Step"), 0)
			check.truthy(#named(asked, "Step") >= 18)
		end)
	end)
end

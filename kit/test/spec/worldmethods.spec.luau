-- worldmethods.spec.luau (kit) — the world lane's METHOD RULES: what leads a session that builds a world to the
-- methods the kit has, or stops it without them (the owner, 2026-11-13: "every method i mentioned for each pipeline
-- keep going up until they are all mastered and implmented into each pipeline and enforced in the terms of being
-- used"). The audit: board/plans/archive/2026-11-13-world-methods-audit.md, column "enforced by".
local frk = require("../frk")
local test, check = frk.test, frk.check

local fs = require("@lune/fs")
local serde = require("@lune/serde")

local LaneLocks = require("../../lib/lanelocks")
local Locks = require("../../lib/locks")
local WorldCmd = require("../../cmd/world")

local ROOT = ".verify/worldmethods-spec"

local function house(i: number): any
	return { building = { name = `House {i}`, center = { i * 30, 0, 0 }, size = { 20, 24 }, floors = 2, mat = "wall" } }
end

-- a worlds folder with one blueprint of `typed` typed houses (+ `more` steps); -> the lock's lines that speak of layout
local function layoutLines(name: string, typed: number, more: { any }?): { string }
	if fs.isDir(ROOT) then
		fs.removeDir(ROOT)
	end
	fs.writeDir(ROOT)
	local build: { any } = {}
	for i = 1, typed do
		table.insert(build, house(i))
	end
	for _, step in more or {} do
		table.insert(build, step)
	end
	fs.writeFile(`{ROOT}/{name}.json`, serde.encode("json", { name = name, scale = "r6", build = build }))
	local lines = {}
	for _, line in LaneLocks.world(nil, ROOT) do
		if string.find(line, 'one "town" step in', 1, true) then
			table.insert(lines, line)
		end
	end
	fs.removeDir(ROOT)
	return lines
end

-- run `body` with the lock record swapped for `json` (the owner's waivers are read from it)
local function withLocks(json: string, body: () -> ())
	local real = Locks.FILE
	local tmp = ".verify/worldmethods-locks.json"
	fs.writeFile(tmp, json)
	Locks.FILE = tmp
	Locks.reset()
	local ok, err = pcall(body)
	Locks.FILE = real
	Locks.reset()
	fs.removeFile(tmp)
	if not ok then
		error(err, 0)
	end
end

return function()
	test.suite("World methods: a town is laid out by its plan", function()
		test.case("typed houses are the blueprint's own building steps, nothing else", function()
			check.equal(LaneLocks.typedHouses({ build = { house(1), house(2), { floor = {} }, { town = {} } } }), 2)
			check.equal(LaneLocks.typedHouses({ build = { { building = true }, { building = "x" }, "building" } }), 0)
			check.equal(LaneLocks.typedHouses({}), 0)
			check.equal(LaneLocks.typedHouses(nil), 0)
			check.equal(LaneLocks.typedHouses({ build = "building" }), 0)
		end)

		test.case("a whole-house mesh placed by a mesh step is a typed house; a tree or a rock is not", function()
			local reg = {
				gh_a = { kind = "gothic_house" },
				oak = { kind = "tree" },
				crag = { kind = "rock" },
				bare = "gothic_house",
			}
			local houses = LaneLocks.houseMeshes(reg)
			check.truthy(houses.gh_a)
			check.falsy(houses.oak)
			check.falsy(houses.bare)
			local bp = {
				build = {
					house(1),
					{ mesh = { mesh = "gh_a", pos = { 0, 0, 0 } } },
					{ mesh = { mesh = "gh_a", pos = { 40, 0, 0 } } },
					{ mesh = { mesh = "oak", pos = { 80, 0, 0 } } },
					{ mesh = { mesh = "nothing", pos = { 80, 0, 0 } } },
					{ mesh = { pos = { 80, 0, 0 } } },
					{ mesh = "gh_a" },
				},
			}
			check.equal(LaneLocks.typedHouses(bp, reg), 3)
			check.equal(LaneLocks.typedHouses(bp, {}), 1)
			-- a town's skinned houses are the plan's, not typed: its "skins" name no mesh step
			check.equal(LaneLocks.typedHouses({ build = { { town = { skins = "gh" } } } }, reg), 0)
		end)

		test.case("a city grid is counted apart from houses, and holds the build by itself", function()
			local _, cities = LaneLocks.typedHouses({ build = { house(1), { city = {} }, { city = true } } })
			check.equal(cities, 2)
			local lines = layoutLines("Grid", 0, { { city = { name = "Blocks", area = { 240, 240 } } } })
			check.equal(#lines, 1)
			check.truthy(string.find(lines[1], 'Grid: 1 "city" step(s)', 1, true))
			check.truthy(string.find(lines[1], "--waive layout", 1, true))
			check.truthy(string.find(lines[1], "reference/05-town-plan.md", 1, true))
			-- a city AND a dozen typed houses are two lines, each its own fault
			check.equal(#layoutLines("Both", 12, { { city = {} } }), 2)
			withLocks(
				[[{"grandfathered": {}, "waivers": {"world": {"Grid": {"by": "owner", "words": "a grid", "steps": ["layout"]}}}}]],
				function()
					check.equal(#layoutLines("Grid", 0, { { city = {} } }), 0)
				end
			)
		end)

		test.case("a dozen houses typed one by one hold the build; eleven do not", function()
			check.equal(LaneLocks.LAYOUT_TYPED, 12)
			check.equal(#layoutLines("Eleven", 11), 0)
			local lines = layoutLines("Dozen", 12)
			check.equal(#lines, 1)
			check.truthy(string.find(lines[1], "Dozen: 12 houses typed one by one", 1, true))
			check.truthy(string.find(lines[1], '"town" step', 1, true))
			check.truthy(string.find(lines[1], "typed one by one", 1, true))
			check.truthy(string.find(lines[1], "lune run kit world town Dozen", 1, true))
			check.truthy(string.find(lines[1], "reference/05-town-plan.md", 1, true))
			check.truthy(fs.isFile("kit/skills/parallax-world/reference/05-town-plan.md"))
			check.truthy(string.find(lines[1], "--waive layout", 1, true))
			check.truthy(string.find(layoutLines("Forty", 40)[1], "Forty: 40 houses", 1, true))
		end)

		test.case(
			"a town's own houses are not typed: a town step with a few typed buildings beside it passes",
			function()
				local town = { town = { name = "Old Town", area = { 256, 224 }, gates = { "S" }, skins = "gh" } }
				check.equal(#layoutLines("Planned", 3, { town }), 0)
				-- ... but a town step is no licence to type a second town beside it
				check.equal(#layoutLines("Both", 12, { town }), 1)
			end
		)

		test.case("the owner's waiver of the layout step lifts it; a waiver of another step does not", function()
			withLocks(
				[[{"grandfathered": {}, "waivers": {"world": {
				"Dozen": {"by": "owner", "words": "type it", "steps": ["layout"]},
				"Other": {"by": "owner", "words": "no refs", "steps": ["refs"]},
				"Model": {"by": "model-proposed", "steps": ["layout"]}}}}]],
				function()
					check.equal(#layoutLines("Dozen", 12), 0)
					check.equal(#layoutLines("Other", 12), 1)
					check.equal(#layoutLines("Model", 12), 1)
					check.equal(#layoutLines("Nobody", 12), 1)
				end
			)
		end)

		test.case("a world that existed before the locks is not asked to be laid out again", function()
			-- (grandfathered is by path: the same folder and name the lock walks)
			withLocks(`\{"grandfathered": \{"world": ["{ROOT}/Old.json"]}, "waivers": \{}}`, function()
				check.equal(#layoutLines("Old", 12), 0)
				check.equal(#layoutLines("New", 12), 1)
			end)
		end)

		test.case(
			"the kit's own fixture of a typed town is caught, and the kept court of nine is under the count",
			function()
				local caught, grid = false, false
				for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_layout") do
					caught = caught or string.find(line, "TypedTown: 12 houses typed one by one", 1, true) ~= nil
					grid = grid or string.find(line, 'GridTown: 1 "city" step(s)', 1, true) ~= nil
				end
				check.truthy(caught)
				check.truthy(grid)
				if fs.isFile("assets/worlds/GothicCourtyard.json") then
					local bp = serde.decode("json", fs.readFile("assets/worlds/GothicCourtyard.json"))
					check.truthy(LaneLocks.typedHouses(bp) < LaneLocks.LAYOUT_TYPED)
				end
			end
		)
	end)

	test.suite("World methods: a line of points says how it bends", function()
		local function road(points: { { number } }, more: any?): any
			local r: any = { name = "Road", points = points, width = 10, mat = "wall" }
			for k, v in more or {} do
				r[k] = v
			end
			return { path = r }
		end
		local CORNER = { { 0, 0 }, { 100, 0 }, { 100, 100 } }

		test.case(
			"a hard corner with no word is named with its angle; a gentle bend, a straight line, two points are not",
			function()
				check.equal(LaneLocks.BEND_KINK, 20)
				local bends = LaneLocks.unsaidBends({ build = { road(CORNER) } })
				check.equal(#bends, 1)
				check.equal(bends[1], 'path "Road" (90 degrees)')
				check.equal(#LaneLocks.unsaidBends({ build = { road({ { 0, 0 }, { 100, 0 }, { 200, 30 } }) } }), 0) -- 17 degrees
				check.equal(#LaneLocks.unsaidBends({ build = { road({ { 0, 0 }, { 100, 0 }, { 200, 40 } }) } }), 1) -- 22 degrees
				check.equal(#LaneLocks.unsaidBends({ build = { road({ { 0, 0 }, { 100, 0 }, { 200, 0 } }) } }), 0)
				check.equal(#LaneLocks.unsaidBends({ build = { road({ { 0, 0 }, { 100, 0 } }) } }), 0)
				-- a point typed twice hides no corner
				check.equal(
					#LaneLocks.unsaidBends({ build = { road({ { 0, 0 }, { 100, 0 }, { 100, 0 }, { 100, 90 } }) } }),
					1
				)
			end
		)

		test.case("the blueprint's own word settles it, either way", function()
			check.equal(#LaneLocks.unsaidBends({ build = { road(CORNER, { curve = true }) } }), 0)
			check.equal(#LaneLocks.unsaidBends({ build = { road(CORNER, { curve = false }) } }), 0)
			check.equal(#LaneLocks.unsaidBends({ build = { road(CORNER, { curve = { closed = true } }) } }), 0)
		end)

		test.case("every generator that walks points is asked: a row, a palisade, a wall along points", function()
			local bends = LaneLocks.unsaidBends({
				build = {
					{ row = { name = "Lamps", points = CORNER, item = "lamp" } },
					{ palisade = { points = CORNER, height = 12 } },
					{ wall = { name = "Town wall", points = CORNER, height = 20, thickness = 3 } },
					{ wall = { name = "Plain", from = { 0, 0 }, to = { 50, 0 }, height = 10, thickness = 1 } },
					{ scatter = { points = CORNER } },
					"path",
					{ path = "points" },
					{ path = { points = "here" } },
					{ path = { points = { "a", { 1 }, { 0, 0 }, { 9, 0 }, { 9, 9 } } } },
				},
			})
			check.equal(#bends, 4)
			check.equal(bends[1], 'row "Lamps" (90 degrees)')
			check.equal(bends[2], 'palisade "build[2]" (90 degrees)')
			check.equal(bends[3], 'wall "Town wall" (90 degrees)')
			check.equal(bends[4], 'path "build[9]" (90 degrees)')
			check.equal(#LaneLocks.unsaidBends(nil), 0)
			check.equal(#LaneLocks.unsaidBends({ build = "path" }), 0)
		end)

		test.case("the build's lock holds a new world on it and names the fix; an old world is left alone", function()
			local function bendLines(name: string, step: any): { string }
				if fs.isDir(ROOT) then
					fs.removeDir(ROOT)
				end
				fs.writeDir(ROOT)
				fs.writeFile(
					`{ROOT}/{name}.json`,
					serde.encode("json", { name = name, scale = "r6", build = { step } })
				)
				local lines = {}
				for _, line in LaneLocks.world(nil, ROOT) do
					if string.find(line, "do not say how they bend", 1, true) then
						table.insert(lines, line)
					end
				end
				fs.removeDir(ROOT)
				return lines
			end
			local lines = bendLines("Kinked", road(CORNER))
			check.equal(#lines, 1)
			check.truthy(string.find(lines[1], "Kinked: 1 line(s) of points turn a hard corner", 1, true))
			check.truthy(string.find(lines[1], 'path "Road" (90 degrees)', 1, true))
			check.truthy(string.find(lines[1], '"curve": true', 1, true))
			check.truthy(string.find(lines[1], '"curve": false', 1, true))
			check.equal(#bendLines("Said", road(CORNER, { curve = true })), 0)
			check.equal(#bendLines("Meant", road(CORNER, { curve = false })), 0)
			withLocks(`\{"grandfathered": \{"world": ["{ROOT}/Old.json"]}, "waivers": \{}}`, function()
				check.equal(#bendLines("Old", road(CORNER)), 0)
			end)
			-- (no waiver lifts it: the word is the blueprint's own)
			withLocks(
				[[{"grandfathered": {}, "waivers": {"world": {"Kinked": {"by": "owner", "words": "any"}}}}]],
				function()
					check.equal(#bendLines("Kinked", road(CORNER)), 1)
				end
			)
		end)

		test.case("the kit's own fixture of a kinked road is caught", function()
			local caught = false
			for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_bends") do
				caught = caught
					or string.find(line, "KinkedRoad: 2 line(s) of points turn a hard corner", 1, true) ~= nil
			end
			check.truthy(caught)
		end)
	end)

	test.suite("World methods: a town says how its streets run", function()
		local function town(more: any?): any
			local t: any = { name = "Old Town", area = { 256, 224 }, gates = { "S" }, skins = "gh" }
			for k, v in more or {} do
				t[k] = v
			end
			return { town = t }
		end

		test.case('a town with no "bend" is named; "bend": 8 and "bend": 0 both settle it', function()
			local unsaid = LaneLocks.unsaidTownBends({
				build = { town(), { town = { area = { 256, 224 } } }, town({ bend = 8 }), town({ bend = 0 }) },
			})
			check.equal(#unsaid, 2)
			check.equal(unsaid[1], "Old Town")
			check.equal(unsaid[2], "build[2]")
			check.equal(#LaneLocks.unsaidTownBends({ build = { town({ bend = 0 }) } }), 0)
			check.equal(#LaneLocks.unsaidTownBends({ build = { { town = "Old Town" }, "town", { building = {} } } }), 0)
			check.equal(#LaneLocks.unsaidTownBends(nil), 0)
		end)

		test.case(
			"the build's lock holds a new world on it and names both answers; an old world is left alone",
			function()
				local function townLines(name: string, step: any): { string }
					if fs.isDir(ROOT) then
						fs.removeDir(ROOT)
					end
					fs.writeDir(ROOT)
					fs.writeFile(
						`{ROOT}/{name}.json`,
						serde.encode("json", { name = name, scale = "r6", build = { step } })
					)
					local lines = {}
					for _, line in LaneLocks.world(nil, ROOT) do
						if string.find(line, "do not say how their streets run", 1, true) then
							table.insert(lines, line)
						end
					end
					fs.removeDir(ROOT)
					return lines
				end
				local lines = townLines("Straight", town())
				check.equal(#lines, 1)
				check.truthy(
					string.find(lines[1], 'Straight: 1 town(s) do not say how their streets run: "Old Town"', 1, true)
				)
				check.truthy(string.find(lines[1], '"bend": <3 to 8 degrees>', 1, true))
				check.truthy(string.find(lines[1], '"bend": 0', 1, true))
				check.equal(#townLines("Bent", town({ bend = 8 })), 0)
				check.equal(#townLines("Meant", town({ bend = 0 })), 0)
				withLocks(`\{"grandfathered": \{"world": ["{ROOT}/Old.json"]}, "waivers": \{}}`, function()
					check.equal(#townLines("Old", town()), 0)
				end)
			end
		)

		test.case("the kit's own fixture of a town that does not say is caught", function()
			local caught = false
			for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_bends") do
				caught = caught
					or string.find(line, "UnsaidTown: 1 town(s) do not say how their streets run", 1, true) ~= nil
			end
			check.truthy(caught)
		end)
	end)

	test.suite("World methods: a large world says how it streams", function()
		local PAL = { g = { material = "Concrete", color = { 96, 98, 104 } } }
		local function world(build: { any }, more: any?): any
			local bp: any = { name = "W", scale = "r6", palette = PAL, build = build }
			for k, v in more or {} do
				bp[k] = v
			end
			return bp
		end
		local function slab(x: number, z: number, w: number, d: number, more: any?): any
			local part: any = { name = "Slab", size = { w, 2, d }, pos = { x, 1, z }, mat = "g" }
			for k, v in more or {} do
				part[k] = v
			end
			return { part = part }
		end

		test.case("reach is MEASURED on what the compiler builds, far scenery left out", function()
			-- (a fresh reader, 2026-11-14: read off the blueprint's numbers, a grid 1,564 studs across was 0, stairs
			-- 1,600 long were 0, a part turned about a far point was 4 - and a far ring of mountains counted)
			check.equal(LaneLocks.reach(nil), 0)
			check.equal(LaneLocks.reach({ build = {} }), 0)
			check.equal(LaneLocks.reach(world({})), 0)
			check.equal(LaneLocks.reach(world({ slab(0, 0, 400, 100) })), 400)
			check.equal(LaneLocks.reach(world({ slab(-700, 0, 10, 10), slab(700, 0, 10, 10) })), 1410)
			-- a tall thin part reaches only its footprint
			check.equal(
				LaneLocks.reach(world({ { part = { size = { 10, 900, 60 }, pos = { 0, 450, 0 }, mat = "g" } } })),
				60
			)
			-- a grid has no centre and size of its own: 8 slabs 200 apart, each 190 wide
			local grid = {
				grid = {
					origin = { -700, 0, 0 },
					count = { 8, 1 },
					spacing = { 200, 200 },
					part = { size = { 190, 2, 190 }, mat = "g" },
				},
			}
			local reach = LaneLocks.reach(world({ grid }))
			check.truthy(reach > 1500 and reach < 1700)
			-- a part turned half round about a point 800 studs off stands 1,600 away from where it was typed
			local far =
				LaneLocks.reach(world({ slab(0, 0, 4, 4), slab(0, 0, 4, 4, { turn = 180, about = { 800, 0 } }) }))
			check.truthy(math.abs(far - 1604) < 1)
			-- far scenery (a backdrop part) never streams and is not what a player walks: not counted
			check.equal(
				LaneLocks.reach(world({ slab(0, 0, 400, 100), slab(3000, 0, 500, 500, { backdrop = true }) })),
				400
			)
			-- land counts by the size typed for it; a far ring of land does not
			local land = { heightmap = { center = { 0, 0, 0 }, size = { 2048, 1024 }, source = "none.hm.json" } }
			local ring = {
				heightmap = { center = { 0, 0, 0 }, size = { 6144, 6144 }, source = "none.hm.json", backdrop = true },
			}
			check.equal(LaneLocks.reach(world({ slab(0, 0, 10, 10) }, { terrain = { land } })), 2048)
			check.equal(LaneLocks.reach(world({ slab(0, 0, 10, 10) }, { terrain = { ring } })), 10)
			-- nonsense reaches nothing and crashes nothing
			check.equal(LaneLocks.reach({ name = "W", build = { "x", { part = "y" }, { 1, 2 } } }), 0)
		end)

		test.case("a streaming block must do something: a real cell, the far stand-ins left on", function()
			check.truthy(LaneLocks.streams({ streaming = { cell = 256 } }))
			check.truthy(LaneLocks.streams({ streaming = { cell = 64, lod = true } }))
			-- (each of these compiled SampleSpire to no cells and no stand-ins, and passed the first lock)
			check.falsy(LaneLocks.streams({ streaming = {} }))
			check.falsy(LaneLocks.streams({ streaming = { cell = 100000 } }))
			check.falsy(LaneLocks.streams({ streaming = { cell = "x" } }))
			check.falsy(LaneLocks.streams({ streaming = { cell = 256, lod = false } }))
			check.falsy(LaneLocks.streams({ streaming = true }))
			check.falsy(LaneLocks.streams({}))
			check.falsy(LaneLocks.streams(nil))
		end)

		test.case("past 1,024 studs with no working block the build is held; the owner's waiver lifts it", function()
			local function reachLines(name: string, bp: any): { string }
				if fs.isDir(ROOT) then
					fs.removeDir(ROOT)
				end
				fs.writeDir(ROOT)
				bp.name = name
				fs.writeFile(`{ROOT}/{name}.json`, serde.encode("json", bp))
				local lines = {}
				for _, line in LaneLocks.world(nil, ROOT) do
					if string.find(line, "does not say how it streams", 1, true) then
						table.insert(lines, line)
					end
				end
				fs.removeDir(ROOT)
				return lines
			end
			local wide = { slab(-700, 0, 10, 10), slab(700, 0, 10, 10) }
			check.equal(LaneLocks.STREAM_REACH, 1024)
			local lines = reachLines("Wide", world(wide))
			check.equal(#lines, 1)
			check.truthy(string.find(lines[1], "Wide: its played world reaches 1410 studs across", 1, true))
			check.truthy(string.find(lines[1], '"streaming": { "cell": 256 }', 1, true))
			-- (the switch in the game's project: checked by the build since stage 14, still not written by the kit)
			check.truthy(
				string.find(
					lines[1],
					"the build checks it once the world says how it streams; the kit does not write it",
					1,
					true
				)
			)
			check.truthy(string.find(lines[1], "--waive streaming", 1, true))
			check.equal(#reachLines("Edge", world({ slab(0, 0, 1024, 10) })), 0)
			check.equal(#reachLines("Cut", world(wide, { streaming = { cell = 256 } })), 0)
			check.equal(#reachLines("Empty", world(wide, { streaming = {} })), 1)
			check.equal(#reachLines("Off", world(wide, { streaming = { cell = 256, lod = false } })), 1)
			-- far scenery alone holds nobody
			check.equal(
				#reachLines("Ring", world({ slab(0, 0, 400, 100), slab(3000, 0, 500, 500, { backdrop = true }) })),
				0
			)
			withLocks(`\{"grandfathered": \{"world": ["{ROOT}/Old.json"]}, "waivers": \{}}`, function()
				check.equal(#reachLines("Old", world(wide)), 0)
			end)
			withLocks(
				[[{"grandfathered": {}, "waivers": {"world": {
				"Wide": {"by": "owner", "words": "one place, no streaming", "steps": ["streaming"]},
				"Other": {"by": "owner", "words": "no refs", "steps": ["refs"]}}}}]],
				function()
					check.equal(#reachLines("Wide", world(wide)), 0)
					check.equal(#reachLines("Other", world(wide)), 1)
				end
			)
		end)

		test.case("the kit's own fixture of a wide played world is caught by its measured reach", function()
			local caught = false
			for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_reach") do
				caught = caught
					or string.find(line, "WideLand: its played world reaches 1590 studs across", 1, true) ~= nil
			end
			check.truthy(caught)
		end)
	end)

	test.suite("World methods: a house says whether it has rooms", function()
		local function big(more: any?): any
			local b: any =
				{ name = "Hall", center = { 0, 0, 0 }, size = { 30, 34 }, floors = 2, mat = "wall", skin = "gh" }
			for k, v in more or {} do
				b[k] = v
			end
			return { building = b }
		end

		test.case("a house big enough for two rooms, and a town, are named until they say", function()
			check.equal(LaneLocks.ROOMS_FROM, 20)
			local bare = LaneLocks.unsaidRooms({
				build = {
					big(),
					big({ name = "Shed", size = { 12, 19 } }), -- too small to cut: not asked
					big({ name = "Said", rooms = true }),
					big({ name = "Open", rooms = false }),
					{ town = { name = "Old Town" } },
					{ town = { name = "New Town", house = { rooms = true } } },
					{ town = { name = "Shells", house = { rooms = false } } },
					{ town = { name = "Half", house = { roof = "gable" } } },
					{ building = "x" },
					"building",
				},
			})
			check.equal(#bare, 3)
			check.equal(bare[1], 'building "Hall"')
			check.equal(bare[2], 'town "Old Town" (its "house")')
			check.equal(bare[3], 'town "Half" (its "house")')
			-- a word that is not true, false or a table says nothing (and the compiler refuses it)
			check.equal(
				#LaneLocks.unsaidRooms({ build = { big({ rooms = "no" }), big({ rooms = 0 }), big({ rooms = {} }) } }),
				2
			)
			check.equal(#LaneLocks.unsaidRooms({ build = { { town = { name = "T", house = { rooms = "no" } } } } }), 1)
			check.equal(#LaneLocks.unsaidRooms(nil), 0)
		end)

		test.case(
			"the build's lock holds a new world on it and names both answers; an old world is left alone",
			function()
				local function roomLines(name: string, step: any): { string }
					if fs.isDir(ROOT) then
						fs.removeDir(ROOT)
					end
					fs.writeDir(ROOT)
					fs.writeFile(
						`{ROOT}/{name}.json`,
						serde.encode("json", { name = name, scale = "r6", build = { step } })
					)
					local lines = {}
					for _, line in LaneLocks.world(nil, ROOT) do
						if string.find(line, "do not say whether they have rooms inside", 1, true) then
							table.insert(lines, line)
						end
					end
					fs.removeDir(ROOT)
					return lines
				end
				local lines = roomLines("Bare", big())
				check.equal(#lines, 1)
				check.truthy(
					string.find(
						lines[1],
						'Bare: 1 house(s) do not say whether they have rooms inside: building "Hall"',
						1,
						true
					)
				)
				check.truthy(string.find(lines[1], '"rooms": true', 1, true))
				check.truthy(string.find(lines[1], '"rooms": false', 1, true))
				check.equal(#roomLines("Said", big({ rooms = true })), 0)
				check.equal(#roomLines("Open", big({ rooms = false })), 0)
				withLocks(`\{"grandfathered": \{"world": ["{ROOT}/Old.json"]}, "waivers": \{}}`, function()
					check.equal(#roomLines("Old", big()), 0)
				end)
			end
		)

		test.case("the kit's own fixture of a house that does not say is caught", function()
			local caught = false
			for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_rooms") do
				caught = caught
					or string.find(line, "BareHouse: 1 house(s) do not say whether they have rooms inside", 1, true)
						~= nil
			end
			check.truthy(caught)
			-- the owner's kept court stood before the rule: none of the lane's method rules holds it
			if fs.isFile("assets/worlds/GothicCourtyard.json") then
				for _, line in LaneLocks.world({ "GothicCourtyard" }, "assets/worlds") do
					for _, words in
						{ "rooms inside", "how it streams", "how they bend", "streets run", '"town" step in' }
					do
						check.falsy(string.find(line, words, 1, true))
					end
				end
			end
		end)
	end)

	test.suite("World methods: a world that streams needs the game's own switch", function()
		local function lines(dir: string, project: string?): { string }
			local out = {}
			for _, line in LaneLocks.world(nil, dir, project) do
				if string.find(line, "does not turn streaming on", 1, true) then
					table.insert(out, line)
				end
			end
			return out
		end

		test.case(
			"the project file is read: on (both of Rojo's ways), off, false, other properties, missing, not a project",
			function()
				check.equal(LaneLocks.streamSwitch("kit/selftest/locks/worlds_switch_on/default.project.json"), "on")
				check.equal(LaneLocks.streamSwitch("kit/selftest/locks/worlds_switch_bool/default.project.json"), "on")
				check.equal(LaneLocks.streamSwitch("kit/selftest/locks/worlds_switch/default.project.json"), "off")
				check.equal(
					LaneLocks.streamSwitch("kit/selftest/locks/worlds_switch_false/default.project.json"),
					"off"
				)
				check.equal(
					LaneLocks.streamSwitch("kit/selftest/locks/worlds_switch_other/default.project.json"),
					"off"
				)
				check.equal(LaneLocks.streamSwitch("kit/selftest/locks/worlds_switch/no-such.project.json"), "missing")
				check.equal(
					LaneLocks.streamSwitch("kit/selftest/locks/worlds_switch_unread/default.project.json"),
					"unread"
				)
				-- a world's blueprint is JSON but no Rojo project: never read as "on"
				check.equal(LaneLocks.streamSwitch("kit/selftest/locks/worlds_switch/StreamsOff.json"), "unread")
				-- the kit's home project does not turn it on (read only; worlds_switch above covers "on")
				check.equal(LaneLocks.streamSwitch("default.project.json"), "off")
			end
		)

		test.case("which project file is asked: the one named, the active game's, or a fixture folder's own", function()
			local Config = require("../../lib/config")
			-- the build (no folder, no name): the game's project file from the kit's config; missing is a fault
			local path, must = LaneLocks.projectFor(nil, nil)
			check.equal(path, Config.load().rojo)
			check.truthy(must)
			check.truthy(string.find(path, "default.project.json", 1, true))
			-- kit verify names each root's own file; missing is a fault
			path, must = LaneLocks.projectFor("games/X/assets/worlds", "games/X/default.project.json")
			check.equal(path, "games/X/default.project.json")
			check.truthy(must)
			-- a fixture folder alone: its own file, and none asks nothing
			path, must = LaneLocks.projectFor("kit/selftest/locks/worlds_switch", nil)
			check.equal(path, "kit/selftest/locks/worlds_switch/default.project.json")
			check.falsy(must)
		end)

		test.case(
			"a world that says how it streams is named when the project leaves streaming off, and not when it is on",
			function()
				local off = lines("kit/selftest/locks/worlds_switch")
				check.equal(#off, 1)
				check.truthy(string.find(off[1], "StreamsOff: it is prepared for streaming", 1, true))
				check.truthy(
					string.find(
						off[1],
						"kit/selftest/locks/worlds_switch/default.project.json: no StreamingEnabled",
						1,
						true
					)
				)
				check.truthy(string.find(off[1], '"StreamingEnabled": true', 1, true))
				check.truthy(string.find(off[1], "--waive streaming", 1, true))
				check.equal(#lines("kit/selftest/locks/worlds_switch_on"), 0)
				check.equal(#lines("kit/selftest/locks/worlds_switch_bool"), 0)
				-- said and false; other properties only; not a project at all: each is named
				check.equal(#lines("kit/selftest/locks/worlds_switch_false"), 1)
				check.equal(#lines("kit/selftest/locks/worlds_switch_other"), 1)
				local unread = lines("kit/selftest/locks/worlds_switch_unread")
				check.equal(#unread, 1)
				check.truthy(string.find(unread[1], "not a Rojo project", 1, true))
				-- a world that does NOT say how it streams is not asked for the switch (the reach lock asks it its own way),
				-- and a fixture folder with no project file of its own asks nothing
				check.equal(#lines("kit/selftest/locks/worlds_reach"), 0)
				check.equal(#lines("kit/selftest/locks/worlds_bends"), 0)
				-- every fixture world really is prepared for streaming (the lock's own reading of the block)
				for _, f in
					{
						"kit/selftest/locks/worlds_switch/StreamsOff.json",
						"kit/selftest/locks/worlds_switch_on/StreamsOn.json",
						"kit/selftest/locks/worlds_switch_false/StreamsFalse.json",
					}
				do
					check.truthy(LaneLocks.streams(serde.decode("json" :: any, fs.readFile(f))))
				end
			end
		)

		test.case(
			"the owner's waiver of streaming lifts the switch; a waiver of another step does not; an old world is not asked",
			function()
				withLocks(
					[[{"grandfathered": {}, "waivers": {"world": {"StreamsOff": {"by": "owner", "words": "turned on in Studio", "steps": ["streaming"]}}}}]],
					function()
						check.equal(#lines("kit/selftest/locks/worlds_switch"), 0)
					end
				)
				withLocks(
					[[{"grandfathered": {}, "waivers": {"world": {"StreamsOff": {"by": "owner", "words": "a grid", "steps": ["layout"]}}}}]],
					function()
						check.equal(#lines("kit/selftest/locks/worlds_switch"), 1)
					end
				)
				-- a world older than the locks is not asked (its record names it)
				withLocks(
					[[{"grandfathered": {"world": ["kit/selftest/locks/worlds_switch/StreamsOff.json"]}, "waivers": {}}]],
					function()
						check.equal(#lines("kit/selftest/locks/worlds_switch"), 0)
					end
				)
			end
		)

		test.case(
			"the way kit verify asks: the project file is NAMED, and a named file that is not there is a fault",
			function()
				-- the world's folder has no project file of its own (as assets/worlds never has): naming the game's finds it
				check.equal(
					#lines(
						"kit/selftest/locks/worlds_switch_on",
						"kit/selftest/locks/worlds_switch/default.project.json"
					),
					1
				)
				check.equal(
					#lines(
						"kit/selftest/locks/worlds_switch",
						"kit/selftest/locks/worlds_switch_on/default.project.json"
					),
					0
				)
				local missing = lines(
					"kit/selftest/locks/worlds_switch_on",
					"kit/selftest/locks/worlds_switch_on/no-such.project.json"
				)
				check.equal(#missing, 1)
				check.truthy(string.find(missing[1], "no such file", 1, true))
				check.truthy(string.find(missing[1], '"rojo" in kit.config.json', 1, true))
				-- ... while the same missing file as a folder's own asks nothing (a fixture folder)
				check.equal(#lines("kit/selftest/locks/worlds_reach"), 0)
				-- kit verify's own loop passes each root's project file: its text names it
				local src = fs.readFile("kit/lib/lanelocks.luau")
				check.truthy(
					string.find(
						src,
						'LaneLocks.world(nil, root .. "assets/worlds", root .. "default.project.json")',
						1,
						true
					)
				)
			end
		)
	end)

	test.suite("World methods: a town with house meshes says how its houses are made", function()
		test.case("named with no word or a word that is no yes / no; a town with no skins is not asked", function()
			local unsaid = LaneLocks.unsaidFacades({
				build = {
					{ town = { name = "Old Town", skins = "gh" } },
					{ town = { name = "Modules", skins = "gh", facade = true } },
					{ town = { name = "Whole", skins = "gh", facade = false } },
					{ town = { name = "Word", skins = "gh", facade = "yes" } },
					{ town = { name = "Bare" } },
					{ town = { name = "NoName", skins = "" } },
					{ town = { skins = "gh" } },
					{ building = {} },
				},
			})
			check.equal(table.concat(unsaid, " | "), "Old Town | Word | build[7]")
			check.equal(#LaneLocks.unsaidFacades(nil), 0)
			check.equal(#LaneLocks.unsaidFacades({ build = "x" }), 0)
			local lines = {}
			for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_facade") do
				if string.find(line, "do not say how their houses are made", 1, true) then
					table.insert(lines, line)
				end
				-- (that fixture says its ground, its market and its yards: those locks have nothing on it)
				check.falsy(string.find(line, "how their land lies", 1, true))
				check.falsy(string.find(line, "square holds a market", 1, true))
				check.falsy(string.find(line, "yards are dressed", 1, true))
			end
			check.equal(#lines, 1)
			check.truthy(string.find(lines[1], "UnsaidFronts: 1 town(s)", 1, true))
			check.truthy(string.find(lines[1], '"Old Town"', 1, true))
			check.truthy(string.find(lines[1], '"facade": true', 1, true))
			check.truthy(string.find(lines[1], '"facade": false', 1, true))
		end)
	end)

	test.suite("World methods: a town says how its land lies", function()
		test.case(
			"a town with no word is named; a slope and false both settle it; a word that is neither does not",
			function()
				local unsaid = LaneLocks.unsaidSlopes({
					build = {
						{ town = { name = "Old Town" } },
						{ town = { name = "Hill", slope = { rise = 4, toward = "N" } } },
						{ town = { name = "Plain", slope = false } },
						{ town = { name = "Word", slope = "steep" } },
						{ town = { name = "Yes", slope = true } },
						{ building = {} },
					},
				})
				check.equal(#unsaid, 3)
				check.equal(unsaid[1], "Old Town")
				check.equal(unsaid[2], "Word")
				check.equal(unsaid[3], "Yes")
				check.equal(#LaneLocks.unsaidSlopes(nil), 0)
				local lines = {}
				for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_slope") do
					if string.find(line, "do not say how their land lies", 1, true) then
						table.insert(lines, line)
					end
					-- (that fixture says its market and its yards: those locks have nothing on it)
					check.falsy(string.find(line, "square holds a market", 1, true))
					check.falsy(string.find(line, "yards are dressed", 1, true))
				end
				check.equal(#lines, 1)
				check.truthy(string.find(lines[1], "UnsaidGround: 1 town(s)", 1, true))
				check.truthy(string.find(lines[1], '"slope": false', 1, true))
			end
		)
	end)

	test.suite("World methods: a town says whether its yards are dressed", function()
		test.case(
			"a town with no word is named; true and false both settle it; a word that is neither does not",
			function()
				local unsaid = LaneLocks.unsaidYards({
					build = {
						{ town = { name = "Old Town" } },
						{ town = { name = "Lived In", yards = true } },
						{ town = { name = "Bare", yards = false } },
						{ town = { name = "Word", yards = "yes" } },
						{ building = {} },
					},
				})
				check.equal(#unsaid, 2)
				check.equal(unsaid[1], "Old Town")
				check.equal(unsaid[2], "Word")
				check.equal(#LaneLocks.unsaidYards(nil), 0)
				local lines = {}
				for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_yards") do
					if string.find(line, "do not say whether their yards are dressed", 1, true) then
						table.insert(lines, line)
					end
				end
				check.equal(#lines, 1)
				check.truthy(string.find(lines[1], "BareYards: 1 town(s)", 1, true))
				check.truthy(string.find(lines[1], '"yards": false', 1, true))
				-- (that fixture says its market: the market's lock has nothing on it)
				for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_yards") do
					check.falsy(string.find(line, "square holds a market", 1, true))
				end
			end
		)
	end)

	test.suite("World methods: a town says whether its square holds a market", function()
		test.case(
			"a town with no word is named; true and false both settle it; a word that is neither does not",
			function()
				local unsaid = LaneLocks.unsaidMarkets({
					build = {
						{ town = { name = "Old Town" } },
						{ town = { name = "Fair", market = true } },
						{ town = { name = "Bare", market = false } },
						{ town = { name = "Word", market = "yes" } },
						{ building = {} },
					},
				})
				check.equal(#unsaid, 2)
				check.equal(unsaid[1], "Old Town")
				check.equal(unsaid[2], "Word")
				check.equal(#LaneLocks.unsaidMarkets(nil), 0)
				local lines = {}
				for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_bends") do
					if string.find(line, "do not say whether their square holds a market", 1, true) then
						table.insert(lines, line)
					end
				end
				check.equal(#lines, 1)
				check.truthy(string.find(lines[1], "UnsaidTown: 1 town(s)", 1, true))
				check.truthy(string.find(lines[1], '"market": false', 1, true))
			end
		)
	end)

	test.suite("World methods: a build of a town ends on its plan page", function()
		test.case("a town is known from the blueprint's own steps", function()
			check.truthy(WorldCmd.hasTown("kit/selftest/world/_selftest_town.json"))
			check.falsy(WorldCmd.hasTown("kit/selftest/world/_selftest_city_grid.json"))
			check.falsy(WorldCmd.hasTown("kit/selftest/world/no_such_world.json"))
			check.falsy(WorldCmd.hasTown("kit/skills/parallax-world/SKILL.md"))
		end)

		test.case("a world with no town, or no blueprint, gets no line and is not compiled for one", function()
			local flat = "build/worlds/SelftestCityGrid.json"
			local before = if fs.isFile(flat) then fs.readFile(flat) else nil
			check.equal(#WorldCmd.townLooks({ "kit/selftest/world/_selftest_city_grid.json", "NoSuchWorld" }), 0)
			check.equal(#WorldCmd.townLooks({}), 0)
			local after = if fs.isFile(flat) then fs.readFile(flat) else nil
			check.equal(after, before)
		end)

		test.case("the page is drawn from the blueprint alone: no compiled file needs to be there first", function()
			local flat, page = "build/worlds/SelftestTown.json", "build/worlds/town/SelftestTown_Town.png"
			for _, f in { flat, page } do
				if fs.isFile(f) then
					fs.removeFile(f)
				end
			end
			local lines = WorldCmd.townLooks({ "kit/selftest/world/_selftest_town.json" })
			check.equal(#lines, 1)
			check.equal(string.sub(lines[1], 1, 6), "LOOK: ")
			check.truthy(string.find(lines[1], "SelftestTown: 60 house(s)", 1, true))
			check.truthy(string.find(lines[1], "read it before dressing", 1, true))
			check.truthy(fs.isFile(page))
		end)

		test.case("more towns than a build draws are named, not dropped", function()
			local real = WorldCmd.TOWN_LOOKS
			WorldCmd.TOWN_LOOKS = 1
			local ok, err = pcall(function()
				local t = "kit/selftest/world/_selftest_town.json"
				local lines = WorldCmd.townLooks({ t, t, t })
				check.equal(#lines, 2)
				check.truthy(string.find(lines[2], "2 more town(s) have no plan page from this build", 1, true))
			end)
			WorldCmd.TOWN_LOOKS = real
			if not ok then
				error(err, 0)
			end
		end)
	end)
end

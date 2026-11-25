-- worldstairs.spec.luau (kit) — a building's stairs can be CLIMBED, floor after floor (kit/lib/world.luau, "THE
-- FLIGHTS TURN BACK"; card u3re). Every flight used to stand in one lane, so each upper flight's solid steps sat
-- on the hole the flight below comes up through: 0 studs over its top tread, in every building of three floors or
-- of two under a flat roof. Measured here on the parts the compiler makes, with no help from the stair code:
-- room over every tread, a step from each flight's top onto the next, a floor to step off onto.
local frk = require("../frk")
local test, check = frk.test, frk.check

local World = require("../../lib/world")

local PALETTE = { stone = { material = "Slate", color = { 90, 90, 90 } } }
local BODY = 5 -- studs: an R6 rig, feet to the top of its head

local function building(more: any): ({ any }, { string })
	local b: any = {
		name = "H",
		center = { 0, 0, 0 },
		size = { 22, 30 },
		floors = 3,
		floorHeight = 14,
		thickness = 1,
		mat = "stone",
		roof = "gable",
		stairs = true,
		door = { side = "S", width = 6, height = 8.5 },
	}
	for k, v in more do
		b[k] = v
	end
	local _, parts, issues = World.compile({ name = "T", palette = PALETTE, build = { { building = b } } })
	local errors = {}
	for _, i in issues do
		if i.severity == "error" then
			table.insert(errors, i.message)
		end
	end
	return parts, errors
end

-- a part's half reach along x and z as it stands (a wall along z is a box turned a quarter)
local function reach(q: any): (number, number)
	local r = q.rot
	return math.abs(r[1][1]) * q.size[1] / 2 + math.abs(r[1][2]) * q.size[2] / 2 + math.abs(r[1][3]) * q.size[3] / 2,
		math.abs(r[3][1]) * q.size[1] / 2 + math.abs(r[3][2]) * q.size[2] / 2 + math.abs(r[3][3]) * q.size[3] / 2
end

-- the lowest solid thing over the point (x, z) from the height y up: how much room is there
local function roomOver(parts: { any }, self: any, x: number, y: number, z: number): number
	local room = math.huge
	for _, q in parts do
		if q ~= self and q.collide then
			local bottom = q.pos[2] - q.size[2] / 2
			local ex, ez = reach(q)
			if bottom >= y - 1e-6 and math.abs(x - q.pos[1]) < ex - 1e-6 and math.abs(z - q.pos[3]) < ez - 1e-6 then
				room = math.min(room, bottom - y)
			end
		end
	end
	return room
end

-- the highest solid top at or under y at (x, z): what a foot there stands on
local function floorUnder(parts: { any }, x: number, y: number, z: number): number
	local best = -math.huge
	for _, q in parts do
		if q.collide then
			local top = q.pos[2] + q.size[2] / 2
			local ex, ez = reach(q)
			if top <= y + 1e-6 and math.abs(x - q.pos[1]) < ex - 1e-6 and math.abs(z - q.pos[3]) < ez - 1e-6 then
				best = math.max(best, top)
			end
		end
	end
	return best
end

-- the flights of a building: its Stair parts grouped by the floor they stand on, each sorted by tread height
local function flightsOf(parts: { any }, fh: number): { { any } }
	local out: { { any } } = {}
	for _, p in parts do
		if p.name == "Stair" then
			local base = p.pos[2] - p.size[2] / 2
			local f = math.floor(base / fh + 0.5) + 1
			out[f] = out[f] or {}
			table.insert(out[f], p)
		end
	end
	for _, flight in out do
		table.sort(flight, function(a, b)
			return a.size[2] < b.size[2]
		end)
	end
	return out
end

return function()
	test.suite("A building's stairs can be climbed", function()
		local SHAPES = {
			{ floors = 2, roof = "gable", flights = 1 },
			{ floors = 2, roof = "flat", flights = 2 },
			{ floors = 3, roof = "gable", flights = 2 },
			{ floors = 3, roof = "flat", flights = 3 },
			{ floors = 4, roof = "gable", flights = 3 },
			{ floors = 5, roof = "flat", flights = 5 },
		}

		test.case("a body's height of room over every tread of every flight", function()
			for _, shape in SHAPES do
				for _, fh in { 14, 12, 15.5 } do
					local parts, errors = building({ floors = shape.floors, roof = shape.roof, floorHeight = fh })
					check.equal(#errors, 0)
					local flights = flightsOf(parts, fh)
					check.equal(#flights, shape.flights)
					for _, flight in flights do
						check.equal(#flight, math.ceil(fh))
						for _, tread in flight do
							local top = tread.pos[2] + tread.size[2] / 2
							-- over the tread's middle and a body's half width toward each of its sides
							for _, dx in { -1, 0, 1 } do
								for _, dz in { -0.6, 0, 0.6 } do
									check.truthy(
										roomOver(parts, tread, tread.pos[1] + dx, top, tread.pos[3] + dz) >= BODY
									)
								end
							end
						end
					end
				end
			end
		end)

		test.case("each flight hands on to the next: its top tread beside the next one's first, a stud up", function()
			for _, shape in SHAPES do
				local fh = 14
				local parts = building({ floors = shape.floors, roof = shape.roof })
				local flights = flightsOf(parts, fh)
				for g = 1, #flights do
					local top = flights[g][#flights[g]]
					local level = top.pos[2] + top.size[2] / 2
					check.truthy(math.abs(level - g * fh) < 1e-6) -- (it arrives ON the floor above, to the stud)
					-- a way off the stair at the top: a floor at that level beside the top tread (east of the lanes)
					local off = false
					for _, dx in { 3, 5, 7 } do
						-- (a floor's slab is level with the tread; a flat roof's lies one stud over it: a step up)
						local beside = floorUnder(parts, top.pos[1] + dx, level + 1, top.pos[3])
						off = off or (beside >= level - 1e-6 and beside <= level + 1 + 1e-6)
					end
					-- (under a flat roof the hatch's own slab piece is the floor beside it)
					check.truthy(off)
					if g < #flights then
						local first = flights[g + 1][1]
						-- side by side (one lane apart), at the same place along the wall, one stud higher
						check.truthy(math.abs(math.abs(first.pos[1] - top.pos[1]) - top.size[1]) < 1e-6)
						check.truthy(math.abs(first.pos[3] - top.pos[3]) < 1e-6)
						check.truthy(first.pos[2] + first.size[2] / 2 - level <= 1 + 1e-6)
						-- and the next flight climbs the OTHER way along the wall
						local a = flights[g][#flights[g]].pos[3] - flights[g][1].pos[3]
						local b = flights[g + 1][#flights[g + 1]].pos[3] - flights[g + 1][1].pos[3]
						check.truthy(a * b < 0)
					end
				end
			end
		end)

		test.case("no flight stands on a stairwell: under every step is the floor it starts from", function()
			for _, shape in SHAPES do
				local fh = 14
				local parts = building({ floors = shape.floors, roof = shape.roof })
				for g, flight in flightsOf(parts, fh) do
					for _, tread in flight do
						local base = tread.pos[2] - tread.size[2] / 2
						check.truthy(math.abs(base - (g - 1) * fh) < 1e-6)
						-- a slab's top right under its foot (the floors' at f x 14; the ground floor's boards stand
						-- World.GROUND_LIFT over the ground, card my7f: the first flight's foot is sunk that much in them)
						local want = base + (if g == 1 then World.GROUND_LIFT else 0)
						local under = -math.huge
						for _, q in parts do
							if q.name == "Slab" then
								local top = q.pos[2] + q.size[2] / 2
								if
									math.abs(top - want) < 1e-6
									and math.abs(tread.pos[1] - q.pos[1]) < q.size[1] / 2
									and math.abs(tread.pos[3] - q.pos[3]) < q.size[3] / 2
								then
									under = top
								end
							end
						end
						check.truthy(under > -math.huge)
					end
				end
			end
		end)

		test.case("one flight needs one lane; flights that turn back need room for two, or it is said", function()
			-- 9 studs inside the walls: one flight (two floors under a gable) fits, two do not (4 + 4 + 3)
			local _, one = building({ size = { 11, 30 }, floors = 2, roof = "gable" })
			check.equal(#one, 0)
			local _, two = building({ size = { 11, 30 }, floors = 3, roof = "gable" })
			check.equal(#two, 1)
			check.truthy(string.find(two[1], "turn back beside each other", 1, true))
			check.truthy(string.find(two[1], "the building is 11 wide", 1, true))
			local _, wide = building({ size = { 13, 30 }, floors = 3, roof = "gable" })
			check.equal(#wide, 0)
			-- the rule to the stud: 11 INSIDE the walls is enough, 10.9 is not - whatever the walls' thickness
			check.equal(#select(2, building({ size = { 12.9, 30 }, floors = 3 })), 1) -- (10.9 inside walls of 1)
			check.equal(#select(2, building({ size = { 15, 30 }, floors = 3, thickness = 2 })), 0) -- (11 inside walls of 2)
			check.equal(#select(2, building({ size = { 14.9, 30 }, floors = 3, thickness = 2 })), 1)
			check.equal(#select(2, building({ size = { 14, 30 }, floors = 3, thickness = 2 })), 1) -- (12 inside walls of 1; 10 of 2)
			-- no stairs: nothing asked
			local _, none = building({ size = { 8, 30 }, floors = 4, stairs = false })
			check.equal(#none, 0)
		end)

		test.case(
			"a house cut into rooms keeps both lanes clear of partitions; a furnished one of furniture",
			function()
				local parts, errors = building({ floors = 3, rooms = true, size = { 30, 30 } })
				check.equal(#errors, 0)
				local flights = flightsOf(parts, 14)
				check.equal(#flights, 2)
				-- a partition is a wall piece standing inside the house, off its four outer walls: none reaches west
				-- into either lane (the second lane's east edge is 8.5 studs in from the west wall's middle)
				local partitions = 0
				for _, p in parts do
					if
						(p.name == "Wall" or p.name == "Lintel")
						and math.abs(p.pos[1]) < 14
						and math.abs(p.pos[3]) < 14
					then
						partitions += 1
						local ex = reach(p)
						check.truthy(p.pos[1] - ex >= -15 + 8.5 - 1e-6)
					end
				end
				check.truthy(partitions >= 6) -- (the house really is cut into rooms)
				local furnished, furnishErrors = building({ floors = 3, interior = true, size = { 30, 30 } })
				check.equal(#furnishErrors, 0)
				local lanesEast = -15 + 1 + 8 -- (the west wall's inner face and two lanes of 4)
				for _, p in furnished do
					if
						p.name == "Bed"
						or p.name == "Chest"
						or p.name == "Wardrobe"
						or p.name == "Cupboard"
						or p.name == "Crate"
					then
						check.truthy(p.pos[1] - p.size[1] / 2 >= lanesEast - 1e-6)
					end
				end
			end
		)
		test.case(
			"a town drops the stairs of a house too narrow for flights that turn back, and still compiles",
			function()
				local Town = require("../../lib/worldtown")
				local spec = {
					center = { 0, 0, 0 },
					area = { 256, 224 },
					seed = 3,
					gates = { "S" },
					bend = 0,
					mats = { street = "stone", block = "stone", wall = "stone", roof = "stone" },
					lots = { depth = { 34, 36 }, width = { 12, 16 } },
					house = { stairs = true, thickness = 2 },
				}
				local kept, dropped = 0, 0
				for _, st in Town.steps(Town.plan(spec), spec) do
					local b = st.building
					if b then
						local flights = b.floors - (if b.roof == "gable" then 1 else 0)
						local inside = b.size[1] - 2 * (b.thickness or 1)
						if b.stairs == true then
							kept += 1
							check.truthy(flights < 2 or inside >= 11) -- (what keeps its stairs has room for them)
						elseif flights >= 2 and inside < 11 then
							dropped += 1
						end
					end
				end
				check.truthy(dropped >= 5) -- (narrow terraced houses with walls of 2: no stairs, rather than no town)
				local _, _, issues = World.compile({
					name = "T",
					palette = PALETTE,
					build = { { town = spec } },
				})
				for _, i in issues do
					check.truthy(
						i.severity ~= "error" or string.find(i.message, "turn back", 1, true) == nil,
						i.message
					)
				end
				local _ = kept
			end
		)
	end)
end

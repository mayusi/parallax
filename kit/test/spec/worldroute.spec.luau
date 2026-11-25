-- worldroute.spec.luau (kit) — A ROAD ACROSS OPEN LAND, BY RULE (kit/lib/worldroute.luau; the owner's method list,
-- "Procedural road networks": a road across country was typed point by point). On lands made of plain formulas -
-- a plain, a hill, a ridge with a pass, a slope too steep to climb straight, a lake - the road is held to what a
-- road must do: never steeper than its grade, never across what it may not cross, round what it cannot climb,
-- and no longer than it need be.
-- Not claimed here: that a road laid this way looks right on a real land. That is a built world, looked at.
local frk = require("../frk")
local test, check = frk.test, frk.check

local fs = require("@lune/fs")
local serde = require("@lune/serde")

local LaneLocks = require("../../lib/lanelocks")
local Route = require("../../lib/worldroute")
local World = require("../../lib/world")

local PALETTE = { stone = { material = "Slate", color = { 90, 90, 90 } } }
-- rolling land: about 45 studs from its hollows to its tops, slopes up to about 1 in 3
local ROLLING = {
	center = { 0, 40, 0 },
	size = { 768, 768 },
	material = "Grass",
	noise = { amplitude = 22, scale = 220, seed = 5 },
}

-- a world of one path step on some land: (model, the Road parts, errors, the routes handed back)
local function laid(pathStep: any, terrain: { any }?): (any, { any }, { string }, { any })
	pathStep.name = pathStep.name or "Road"
	pathStep.width = pathStep.width or 8
	pathStep.mat = "stone"
	if pathStep.route and pathStep.curve == nil then
		pathStep.curve = false -- (a routed road says the word: the straight runs it found, unless a case says other)
	end
	local model, parts, issues, extras = World.compile({
		name = "T",
		palette = PALETTE,
		terrain = terrain,
		build = { { path = pathStep } },
	})
	local roads, errors = {}, {}
	for _, q in parts do
		if q.name == "Road" then
			table.insert(roads, q)
		end
	end
	for _, i in issues do
		if i.severity == "error" then
			table.insert(errors, i.message)
		end
	end
	return model, roads, errors, (extras and extras.routes) or {}
end

local function flat(_x: number, _z: number): number?
	return 10
end

-- a round hill 60 studs high at the origin, 120 studs to its foot
local function hill(x: number, z: number): number?
	local d = math.sqrt(x * x + z * z) / 120
	return if d >= 1 then 0 else 60 * (1 - d * d * (3 - 2 * d))
end

-- a ridge along z (x = 0), 80 studs high and 60 wide at its foot, with a pass 50 studs wide round z = 200
local function ridge(x: number, z: number): number?
	local across = math.max(0, 1 - math.abs(x) / 30)
	local gate = math.clamp(math.abs(z - 200) / 25, 0, 1) -- (0 in the pass, 1 away from it)
	return 80 * across * gate
end

local function wall(x: number, _z: number): number?
	return 80 * math.max(0, 1 - math.abs(x) / 30)
end

-- the road re-measured here, a stud at a time: its steepest stretch, its length, the least distance to a point
local function measured(height: (number, number) -> number?, points: { { number } }): (number, number)
	local steepest, length = 0, 0
	for i = 2, #points do
		local a, b = points[i - 1], points[i]
		local len = math.sqrt((b[1] - a[1]) ^ 2 + (b[3] - a[3]) ^ 2)
		local n = math.max(1, math.ceil(len / 4))
		local prev = height(a[1], a[3]) :: number
		for k = 1, n do
			local t = k / n
			local h = height(a[1] + (b[1] - a[1]) * t, a[3] + (b[3] - a[3]) * t) :: number
			steepest = math.max(steepest, math.abs(h - prev) / (len / n))
			prev = h
		end
		length += len
	end
	return steepest, length
end

local function nearest(points: { { number } }, x: number, z: number): number
	local best = math.huge
	for i = 2, #points do
		local a, b = points[i - 1], points[i]
		local vx, vz = b[1] - a[1], b[3] - a[3]
		local t = math.clamp(((x - a[1]) * vx + (z - a[3]) * vz) / math.max(vx * vx + vz * vz, 1e-9), 0, 1)
		best = math.min(best, math.sqrt((a[1] + vx * t - x) ^ 2 + (a[3] + vz * t - z) ^ 2))
	end
	return best
end

return function()
	test.suite("A road across open land, by rule", function()
		test.case("what is wrong with a route is said", function()
			local function wrong(route: any, text: string)
				local problems = Route.problems(route)
				check.truthy(#problems >= 1)
				check.truthy(string.find(table.concat(problems, " | "), text, 1, true), table.concat(problems, " | "))
			end
			check.equal(#Route.problems({ from = { 0, 0 }, to = { 100, 0 }, grade = 0.25 }), 0)
			check.equal(
				#Route.problems({ from = { 0, 0 }, to = { 100, 0 }, via = { { 50, 40 } }, grade = 0.25, cell = 4 }),
				0
			)
			wrong(true, '"route" is {')
			wrong({ from = { 0, 0 }, grade = 0.2 }, "route.from and route.to are [x, z]")
			wrong({ from = { 0, 0 }, to = { 0, 0 }, grade = 0.2 }, "the same place")
			wrong({ from = { 0, 0 }, to = { 9, 0 } }, "route.grade")
			wrong({ from = { 0, 0 }, to = { 9, 0 }, grade = 2 }, "route.grade")
			wrong({ from = { 0, 0 }, to = { 9, 0 }, grade = 0.2, cell = 1 }, "route.cell")
			wrong({ from = { 0, 0 }, to = { 9, 0 }, grade = 0.2, via = {} }, "route.via is a list")
			wrong({ from = { 0, 0 }, to = { 9, 0 }, grade = 0.2, via = { { 1 } } }, "route.via[1]")
			wrong({ from = { 0, 0 }, to = { 9, 0 }, grade = 0.2, slope = 0.1 }, "route.slope")
			-- two stops in a row that are one place (it made a road piece of no direction)
			wrong({ from = { 0, 0 }, to = { 9, 0 }, grade = 0.2, via = { { 0, 0 } } }, "same place ([0, 0])")
			wrong({ from = { 0, 0 }, to = { 9, 0 }, grade = 0.2, via = { { 9, 0 } } }, "same place ([9, 0])")
			wrong({ from = { 0, 0 }, to = { 9, 0 }, grade = 0.2, via = { { 4, 4 }, { 4, 4 } } }, "same place ([4, 4])")
			check.equal(#Route.problems({ from = { 0, 0 }, to = { 0, 0 }, grade = 0.2, via = { { 40, 0 } } }), 0) -- (there and back)
			wrong({ from = { 0, 0 }, to = { 9, 0 }, grade = 0.2, reach = 4 }, "route.reach")
		end)

		test.case("across a plain the road is the straight line, end to end", function()
			local road, why = Route.find(flat, { from = { -150, 40 }, to = { 230, -95 }, grade = 0.25 })
			check.equal(why, nil)
			check.equal(#road.points, 2)
			check.equal(road.points[1][1], -150)
			check.equal(road.points[1][2], 10) -- (each point carries the land's height)
			check.equal(road.points[1][3], 40)
			check.equal(road.points[2][1], 230)
			check.equal(road.points[2][3], -95)
			check.truthy(math.abs(road.length - math.sqrt(380 ^ 2 + 135 ^ 2)) < 1e-6)
			check.equal(road.climb, 0)
			check.equal(road.steepest, 0)
			-- two places a stud apart: still a road
			local short = Route.find(flat, { from = { 0, 0 }, to = { 1, 0 }, grade = 0.25 })
			check.equal(#short.points, 2)
		end)

		test.case("a hill in the way: round it, never steeper than the grade, not much longer than need be", function()
			-- (straight over the top the hill climbs 0.75 in 1 at its steepest)
			local route = { from = { -200, 0 }, to = { 200, 0 }, grade = 0.15 }
			local road, why = Route.find(hill, route)
			check.equal(why, nil)
			local steepest, length = measured(hill, road.points)
			check.truthy(steepest <= 0.15 * 1.05) -- (re-measured here a stud at a time)
			check.truthy(road.steepest <= 0.15 + 1e-9)
			check.truthy(math.abs(length - road.length) < 1e-6)
			check.truthy(nearest(road.points, 0, 0) > 60) -- (it does not cross the top)
			check.truthy(road.length > 400 and road.length < 400 * 1.35) -- (round the foot: a sixth longer at most)
			check.truthy(#road.points <= 14) -- (pulled straight: not a point every cell)
			-- its ends are the two places asked for
			check.equal(road.points[1][1], -200)
			check.equal(road.points[#road.points][1], 200)
			check.equal(road.points[#road.points][3], 0)
			-- the same land, the same road
			local again = Route.find(hill, route)
			check.equal(#again.points, #road.points)
			check.equal(again.points[3][1], road.points[3][1])
			-- a steeper road may cut the hill's shoulder: shorter, and it climbs
			local bold = Route.find(hill, { from = { -200, 0 }, to = { 200, 0 }, grade = 0.6 })
			check.truthy(bold.length < road.length)
			check.truthy(bold.climb > road.climb)
		end)

		test.case(
			"a ridge with one pass: the road goes through the pass; with none there is no way, and it says so",
			function()
				local road, why = Route.find(ridge, { from = { -150, 0 }, to = { 150, 0 }, grade = 0.2 })
				check.equal(why, nil)
				check.truthy(nearest(road.points, 0, 200) < 25) -- (through the gap, 200 studs up the ridge)
				check.truthy((measured(ridge, road.points)) <= 0.2 * 1.05)
				local none, said = Route.find(wall, { from = { -150, 0 }, to = { 150, 0 }, grade = 0.2 })
				check.equal(none, nil)
				check.truthy(string.find(said, "no way from [-150, 0] to [150, 0] within a grade of 0.2", 1, true))
				-- ... a road allowed to climb it does
				local over = Route.find(wall, { from = { -150, 0 }, to = { 150, 0 }, grade = 1 })
				check.truthy(over ~= nil)
				check.truthy(over.climb > 70)
			end
		)

		test.case("a slope too steep to climb straight is climbed aslant, in turns", function()
			-- the land rises 1 in 2 toward +x; the road may climb 1 in 5: it cannot go straight up
			local function slope(x: number, _z: number): number?
				return 0.5 * x
			end
			local road, why = Route.find(slope, { from = { 0, 0 }, to = { 160, 0 }, grade = 0.2 })
			check.equal(why, nil)
			check.truthy(road.steepest <= 0.2 + 1e-9)
			check.truthy((measured(slope, road.points)) <= 0.2 + 1e-6)
			check.truthy(math.abs(road.climb - road.fall - 80) < 1e-6) -- (80 studs up in all)
			check.truthy(road.length >= 80 / 0.2 - 1e-6) -- (80 studs at 1 in 5: 400 of road at least)
			check.truthy(road.length < 400 * 1.3)
			-- it turns back on itself: it goes both ways along the slope
			local north, south = false, false
			for i = 2, #road.points do
				local dz = road.points[i][3] - road.points[i - 1][3]
				north, south = north or dz < -1, south or dz > 1
			end
			check.truthy(north and south)
		end)

		test.case("what the road may not cross, it does not; a via is passed through", function()
			local function lake(x: number, z: number): boolean
				return x * x + z * z < 90 * 90
			end
			local road = Route.find(flat, { from = { -200, 10 }, to = { 200, 10 }, grade = 0.25 }, lake)
			check.truthy(nearest(road.points, 0, 0) >= 90 - 4) -- (read every half cell: 4 studs)
			check.truthy(road.length > 400 and road.length < 400 * 1.25)
			-- shut in on every side: no way
			local function moat(x: number, z: number): boolean
				local d = math.sqrt(x * x + z * z)
				return d > 40 and d < 70
			end
			local none, said = Route.find(flat, { from = { 0, 0 }, to = { 200, 0 }, grade = 0.25 }, moat)
			check.equal(none, nil)
			check.truthy(string.find(said, "no way", 1, true))
			-- a via: the road passes through it, once
			local led = Route.find(flat, { from = { -200, 0 }, to = { 200, 0 }, via = { { 0, 150 } }, grade = 0.25 })
			check.equal(#led.points, 3)
			check.equal(led.points[2][1], 0)
			check.equal(led.points[2][3], 150)
			check.truthy(math.abs(led.length - 2 * math.sqrt(200 ^ 2 + 150 ^ 2)) < 1e-6)
		end)

		test.case(
			"a short steep way or a longer gentle one: the road takes the cheaper, and is not pulled over the ridge",
			function()
				-- a ridge 30 high whose sides climb 0.375 (lawful at a grade of 0.4), with a level pass 50 studs along it.
				-- Over the top is 170 studs of road, by the pass about 220: with steepness costing nothing the road
				-- goes over; a road that pays for its climb goes through the pass
				local function low(x: number, z: number): number?
					return 30 * math.max(0, 1 - math.abs(x) / 80) * math.clamp(math.abs(z - 50) / 15, 0, 1)
				end
				local road = Route.find(low, { from = { -85, 0 }, to = { 85, 0 }, grade = 0.4 })
				check.truthy(nearest(road.points, 0, 50) < 12)
				check.truthy(road.climb < 18) -- (it cuts the pass's corners a little: under two thirds of the ridge)
				check.truthy(road.length < 270 * 1.05)
				-- ... with the pass far off, over the top is the cheaper: it climbs
				local function far(x: number, z: number): number?
					return 30 * math.max(0, 1 - math.abs(x) / 80) * math.clamp(math.abs(z - 400) / 15, 0, 1)
				end
				local over = Route.find(far, { from = { -85, 0 }, to = { 85, 0 }, grade = 0.4 })
				check.truthy(math.abs(over.climb - 30) < 1)
				check.truthy(over.length < 180)
			end
		)

		test.case("round a lake the road is close to the shortest way there is", function()
			local function lake(x: number, z: number): boolean
				return x * x + z * z < 90 * 90
			end
			-- (the shortest way round a disc of 90 from 200 on one side to 200 on the other: two tangents and an arc)
			local shortest = 2 * math.sqrt(200 ^ 2 - 90 ^ 2) + 90 * (math.pi - 2 * math.acos(90 / 200))
			local road = Route.find(flat, { from = { -200, 0 }, to = { 200, 0 }, grade = 0.25, cell = 4 }, lake)
			check.truthy(road.length >= shortest * 0.97) -- (it may clip the shore by the 2 studs it reads at)
			check.truthy(road.length <= shortest * 1.03)
		end)

		test.case("a gap in the land is gone round, not crossed", function()
			-- land with an inlet cut into it from the south: no ground where |x| < 20 and z < 50
			local function inlet(x: number, z: number): number?
				return if math.abs(x) < 20 and z < 50 then nil else 0
			end
			local road = Route.find(inlet, { from = { -80, 0 }, to = { 80, 0 }, grade = 0.25 })
			for i = 2, #road.points do
				for k = 0, 40 do
					local x = road.points[i - 1][1] + (road.points[i][1] - road.points[i - 1][1]) * k / 40
					local z = road.points[i - 1][3] + (road.points[i][3] - road.points[i - 1][3]) * k / 40
					check.truthy(not (math.abs(x) < 16 and z < 46)) -- (the land is read every 4 studs: that much grace)
				end
			end
			check.truthy(road.length > 160 * 1.2)
		end)

		test.case("off the land, and too far for its cell, are said", function()
			local function island(x: number, z: number): number?
				return if math.abs(x) <= 100 and math.abs(z) <= 100 then 5 else nil
			end
			local none, said = Route.find(island, { from = { 0, 0 }, to = { 300, 0 }, grade = 0.25 })
			check.equal(none, nil)
			check.truthy(string.find(said, "off the land", 1, true))
			-- across the island it stays on it
			local on = Route.find(island, { from = { -90, -90 }, to = { 90, 90 }, grade = 0.25 })
			check.equal(#on.points, 2)
			-- (the search's allowance is cut for the test: the real one is 150,000 grid points)
			local allowance = Route.NODES
			Route.NODES = 3000
			local far, why = Route.find(ridge, { from = { -9000, 0 }, to = { 9000, 0 }, grade = 0.2, cell = 2 })
			Route.NODES = allowance
			check.equal(far, nil)
			check.truthy(string.find(why, "the search ran out", 1, true))
			check.truthy(string.find(why, '"via"', 1, true))
			check.equal(string.find(why, "larger", 1, true), nil) -- (a larger cell reads the land more coarsely: never the advice)
			check.truthy(allowance >= 50000)
		end)

		test.case(
			"the measures: a road up an even slope climbs what the land rises, at the land's own grade",
			function()
				local function ramp(x: number, _z: number): number?
					return 0.1 * x
				end
				local road = Route.find(ramp, { from = { 0, 0 }, to = { 300, 0 }, grade = 0.25 })
				check.equal(#road.points, 2)
				check.truthy(math.abs(road.climb - 30) < 1e-6)
				check.equal(road.fall, 0)
				check.truthy(math.abs(road.steepest - 0.1) < 1e-6)
				check.truthy(math.abs(road.points[2][2] - 30) < 1e-9)
				-- down it: a fall, no climb
				local down = Route.find(ramp, { from = { 300, 0 }, to = { 0, 0 }, grade = 0.25 })
				check.truthy(math.abs(down.fall - 30) < 1e-6)
				check.equal(down.climb, 0)
			end
		)

		test.case(
			"the land is read every 2 studs whatever the cell: a narrow stream, a sharp ridge between two reads",
			function()
				-- a stream 3 studs wide across the whole way, with one gap: a road read every half cell (16 studs at a
				-- cell of 32) stepped over it
				local function stream(x: number, z: number): boolean
					return math.abs(x) < 1.5 and math.abs(z - 150) > 12
				end
				for _, cell in { 8, 32 } do
					local road =
						Route.find(flat, { from = { -200, 0 }, to = { 200, 0 }, grade = 0.25, cell = cell }, stream)
					check.truthy(road ~= nil)
					for i = 2, #road.points do
						for k = 0, 400 do
							local x = road.points[i - 1][1] + (road.points[i][1] - road.points[i - 1][1]) * k / 400
							local z = road.points[i - 1][3] + (road.points[i][3] - road.points[i - 1][3]) * k / 400
							check.truthy(not (math.abs(x) < 0.4 and math.abs(z - 150) > 13.5))
						end
					end
					check.truthy(nearest(road.points, 0, 150) < 12)
				end
				-- a ridge 6 studs wide and 12 high (it climbs 4 in 1) across the way: no road at 1 in 4, at any cell
				local function sharp(x: number, _z: number): number?
					return 12 * math.max(0, 1 - math.abs(x - 3) / 3)
				end
				for _, cell in { 8, 32, 64 } do
					local none = Route.find(
						sharp,
						{ from = { -200, 0 }, to = { 200, 0 }, grade = 0.25, cell = cell, reach = 128 }
					)
					check.equal(none, nil)
				end
				-- the finished road's "steepest" is measured every half stud: on a land with a kink it tells the truth
				local function kinked(x: number, _z: number): number?
					return if x < 0 then 0 elseif x < 1 then 0.3 * x else 0.3 -- (0.3 up in one stud: 1 in 3.3)
				end
				local over = Route.find(kinked, { from = { -50, 0 }, to = { 50, 0 }, grade = 0.2 })
				check.truthy(over ~= nil) -- (read every 2 studs it is 0.15: lawful to the search)
				check.truthy(math.abs(over.steepest - 0.3) < 1e-6) -- (and said as it is)
			end
		)

		test.case("an end beside water is reached from the open side; an end IN the water is said", function()
			local function lake(x: number, _z: number): boolean
				return x < 64
			end
			-- (the grid point nearest the end stands in the water: the end is its own point, reached from the east)
			local road = Route.find(flat, { from = { 200, 40 }, to = { 65.5, 0 }, grade = 0.25 }, lake)
			check.truthy(road ~= nil)
			check.equal(road.points[#road.points][1], 65.5)
			check.equal(road.points[#road.points][3], 0)
			local none, why = Route.find(flat, { from = { 200, 40 }, to = { 20, 0 }, grade = 0.25 }, lake)
			check.equal(none, nil)
			check.truthy(string.find(why, "stands in water or where the road is kept off", 1, true))
			-- two places closer than a cell: still found, and round what lies between them
			local function fence(x: number, z: number): boolean
				return math.abs(x) < 1.5 and math.abs(z) < 30
			end
			local round = Route.find(flat, { from = { -3, 0 }, to = { 3, 0 }, grade = 0.25 }, fence)
			check.truthy(round ~= nil)
			check.truthy(round.length > 60)
		end)

		test.case("how far to each side the road may look is its reach", function()
			-- the ridge's one pass is 200 studs off the straight line
			local none = Route.find(ridge, { from = { -150, 0 }, to = { 150, 0 }, grade = 0.2, reach = 120 })
			check.equal(none, nil)
			local found = Route.find(ridge, { from = { -150, 0 }, to = { 150, 0 }, grade = 0.2, reach = 260 })
			check.truthy(found ~= nil)
			check.truthy(nearest(found.points, 0, 200) < 25)
		end)

		test.case("the compiler: a path with a route is laid over the land, never steeper than its grade", function()
			local route = { from = { -300, -250 }, to = { 300, 260 }, grade = 0.15 }
			local model, roads, errors, routes = laid(
				{ ground = true, route = route, curve = false },
				{ { ground = ROLLING } }
			)
			check.equal(#errors, 0)
			check.equal(#routes, 1)
			local r = routes[1]
			check.equal(r.name, "Road")
			check.truthy(r.steepest <= 0.15 + 1e-9)
			check.equal(r.grade, 0.15)
			-- (the straight line between the two places climbs 1 in 3.6 at its steepest: the road found another way)
			local function land(x: number, z: number): number?
				return World.groundHeight(ROLLING, x, z)
			end
			check.truthy((measured(land, { { -300, 0, -250 }, { 300, 0, 260 } })) > 0.25)
			local asLaid = {}
			for _, pt in r.points do
				table.insert(asLaid, { pt[1], 0, pt[2] })
			end
			local steepest, length = measured(land, asLaid)
			check.truthy(steepest <= 0.15 * 1.05)
			check.truthy(math.abs(length - r.length) < 1e-6)
			check.truthy(r.length < math.sqrt(600 ^ 2 + 510 ^ 2) * 1.25) -- (a quarter longer than straight at most)
			check.equal(r.points[1][1], -300)
			check.equal(r.points[#r.points][2], 260)
			-- the road's pieces lie along it, on the land
			check.truthy(#roads > 100)
			for _, q in roads do
				check.truthy(nearest(asLaid, q.pos[1], q.pos[3]) < 4.5)
				check.truthy(math.abs(q.pos[2] - (land(q.pos[1], q.pos[3]) :: number)) < 3)
			end
			-- ... and are in the model the game loads, under the step's name
			local held = 0
			for _, c in model.Children do
				if c.Name == "Road" then
					held = #c.Children
				end
			end
			check.equal(held, #roads)
			-- the blueprint's own step is not changed (the route is found anew at each build)
			local step = { ground = true, route = route, curve = false }
			laid(step, { { ground = ROLLING } })
			check.equal(step.points, nil)
			check.equal(step.route, route)
		end)

		test.case("the compiler: the road goes round water and what the step keeps off", function()
			local terrain = {
				{ ground = { center = { 0, 10, 0 }, size = { 768, 768 }, material = "Grass" } },
				{ water = { center = { 0, 8, 0 }, size = { 120, 8, 200 } } }, -- (its top at 12: over the land at 10)
			}
			local _, _, errors, routes =
				laid({ ground = true, route = { from = { -250, 0 }, to = { 250, 0 }, grade = 0.2, cell = 2 } }, terrain)
			check.equal(#errors, 0)
			local pts = {}
			for _, pt in routes[1].points do
				table.insert(pts, { pt[1], 0, pt[2] })
			end
			-- no stretch of it inside the lake's box widened by half the road (read every 20th of a stretch)
			for i = 2, #pts do
				for k = 0, 20 do
					local x = pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * k / 20
					local z = pts[i - 1][3] + (pts[i][3] - pts[i - 1][3]) * k / 20
					-- (the lake's box and half the road's 8 studs; the land is read every stud: 1 stud of grace)
					check.truthy(math.abs(x) > 60 + 4 - 1.01 or math.abs(z) > 100 + 4 - 1.01)
				end
			end
			check.truthy(routes[1].length > 500 * 1.05) -- (round the lake's end)
			-- a road along the lake's long side keeps half its width off the shore there too
			local _, _, _, beside = laid(
				{ ground = true, route = { from = { 30, -250 }, to = { 30, 250 }, grade = 0.2, cell = 2 } },
				terrain
			)
			for i = 2, #beside[1].points do
				for k = 0, 40 do
					local a, b = beside[1].points[i - 1], beside[1].points[i]
					local x, z = a[1] + (b[1] - a[1]) * k / 40, a[2] + (b[2] - a[2]) * k / 40
					check.truthy(math.abs(x) > 60 + 4 - 1.01 or math.abs(z) > 100 + 4 - 1.01)
				end
			end
			check.truthy(beside[1].length < 520) -- (round its side, 34 studs out: not round its far end)
			-- a lake UNDER the land's surface is no lake to the road (its top at 12, the land there at 30)
			local dry = {
				{ ground = { center = { 0, 30, 0 }, size = { 768, 768 }, material = "Grass" } },
				{ water = { center = { 0, 8, 0 }, size = { 120, 8, 200 } } },
			}
			local _, _, _, over =
				laid({ ground = true, route = { from = { -250, 0 }, to = { 250, 0 }, grade = 0.2 } }, dry)
			check.equal(#over[1].points, 2)
			-- "avoid": a circle the road keeps its half width off
			local _, _, _, round = laid({
				ground = true,
				avoid = { { 0, 0, 80 } },
				route = { from = { -250, 0 }, to = { 250, 0 }, grade = 0.2 },
			}, { { ground = { center = { 0, 10, 0 }, size = { 768, 768 }, material = "Grass" } } })
			local clear = {}
			for _, pt in round[1].points do
				table.insert(clear, { pt[1], 0, pt[2] })
			end
			check.truthy(nearest(clear, 0, 0) >= 80 + 4 - 4.01)
		end)

		test.case("the compiler: what cannot be routed is said", function()
			local flatLand = { { ground = { center = { 0, 10, 0 }, size = { 768, 768 }, material = "Grass" } } }
			local function wrong(step: any, terrain: any, text: string)
				local _, roads, errors = laid(step, terrain)
				check.equal(#roads, 0)
				check.truthy(#errors >= 1)
				check.truthy(string.find(table.concat(errors, " | "), text, 1, true), table.concat(errors, " | "))
			end
			local route = { from = { -100, 0 }, to = { 100, 0 }, grade = 0.2 }
			wrong({ route = route }, flatLand, 'a "path" step with "ground": true')
			wrong({ ground = true, route = route, points = { { 0, 0 }, { 9, 9 } } }, flatLand, 'has no "points"')
			wrong({ ground = true, route = route }, nil, "needs land to cross")
			wrong({ ground = true, route = { from = { -100, 0 }, to = { 100, 0 } } }, flatLand, "route.grade")
			wrong(
				{ ground = true, route = { from = { -100, 0 }, to = { 100, 0 }, grade = 0.2, grad = 1 } },
				flatLand,
				"route.grad"
			)
			wrong({ ground = true, route = true }, flatLand, '"route" is {')
			wrong(
				{ ground = true, route = { from = { -100, 0 }, to = { 900, 0 }, grade = 0.2 } },
				flatLand,
				"off the land"
			)
			-- a cliff across the whole land: no way within the grade
			wrong({ ground = true, route = { from = { -300, 0 }, to = { 300, 0 }, grade = 0.1 } }, {
				{
					ground = {
						center = { 0, 40, 0 },
						size = { 768, 768 },
						material = "Grass",
						noise = { amplitude = 60, scale = 60, seed = 5 },
					},
				},
			}, "no way from [-300, 0] to [300, 0] within a grade of 0.1")
			-- a route on a step that walks no road
			local _, _, issues = World.compile({
				name = "T",
				palette = PALETTE,
				terrain = flatLand,
				build = { { row = { name = "Posts", route = route, ground = true } } },
			})
			local said = false
			for _, i in issues do
				said = said
					or (
						i.severity == "error"
						and string.find(i.message, 'a "route" is for a path on the land', 1, true) ~= nil
					)
			end
			check.truthy(said)
			-- "route": false is a road typed by hand, built from its points as before
			local _, roads, errors, routes =
				laid({ ground = true, route = false, points = { { -100, 0 }, { 100, 0 } } }, flatLand)
			check.equal(#errors, 0)
			check.equal(#routes, 0)
			check.truthy(#roads > 20)
		end)

		test.case("the lock: a long road across the land says how its way was found", function()
			local function bp(...: any): any
				local build = {}
				for _, step in { ... } do
					table.insert(build, { path = step })
				end
				return { build = build }
			end
			local long = { { -150, 0 }, { 0, 40 }, { 150, 0 } }
			check.equal(#LaneLocks.unsaidRoutes(bp({ name = "Hill", ground = true, points = long })), 1)
			check.equal(LaneLocks.unsaidRoutes(bp({ name = "Hill", ground = true, points = long }))[1], "Hill")
			check.equal(#LaneLocks.unsaidRoutes(bp({ name = "Hill", ground = true, points = long, route = false })), 0)
			check.equal(#LaneLocks.unsaidRoutes(bp({ name = "Hill", ground = true, route = { grade = 0.2 } })), 0)
			-- a street on a floor (no "ground") and a short path are not asked
			check.equal(#LaneLocks.unsaidRoutes(bp({ name = "Street", points = long })), 0)
			check.equal(
				#LaneLocks.unsaidRoutes(bp({ name = "Step", ground = true, points = { { 0, 0 }, { 199, 0 } } })),
				0
			)
			check.equal(
				#LaneLocks.unsaidRoutes(bp({ name = "Step", ground = true, points = { { 0, 0 }, { 200, 0 } } })),
				1
			)
			check.equal(#LaneLocks.unsaidRoutes({}), 0)
			local named = 0
			for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_route") do
				if string.find(line, "do not say how their way was found", 1, true) then
					named += 1
					check.truthy(string.find(line, "RoadByEye", 1, true))
					check.truthy(string.find(line, '"HillRoad"', 1, true))
					check.truthy(string.find(line, '"Doorstep"', 1, true)) -- (counted together with it: asked the same)
					check.equal(string.find(line, "OldRoad", 1, true), nil)
				end
			end
			check.equal(named, 1)
		end)

		test.case(
			"the compiler: on a real heightmap the road as laid keeps to its grade, measured every half stud",
			function()
				-- (the kit's own 1024-stud terrain, 228 studs of relief. A fresh reader: read every 4 studs the road
				-- reported 0.498 and was 0.935 at its steepest)
				local terrain = {
					{
						heightmap = {
							center = { 0, 0, 0 },
							size = { 1024, 1024 },
							source = "kit/selftest/world/terrain/_selftest_terrain_v1.hm.json",
							material = "Grass",
							paint = false,
						},
					},
				}
				local laidAny = 0
				for _, try in
					{
						{ from = { -300, -300 }, to = { 300, 300 }, grade = 0.4 },
						{ from = { -200, 250 }, to = { 250, -150 }, grade = 0.5, cell = 16 },
						{ from = { -350, 0 }, to = { 350, 0 }, grade = 0.6 },
					} :: { any }
				do
					local _, _, errors, routes = laid({ ground = true, route = try }, terrain)
					if #errors == 0 then
						laidAny += 1
						-- (a quarter over, a stud at a time, is the build's own warning line: an edge of the land between two reads)
						check.truthy(routes[1].steepest <= try.grade * 1.25)
						check.truthy(routes[1].steepest > 0.05) -- (it is a real climb, really measured)
					else
						check.truthy(
							string.find(errors[1], "no way", 1, true) ~= nil
								or string.find(errors[1], "ran out", 1, true) ~= nil
						)
					end
				end
				check.truthy(laidAny >= 2)
			end
		)

		test.case("the compiler: a painted river, a frozen lake and a typed curve", function()
			-- a painted land (written here: 33 x 33 heights every 4 studs, flat) with a river from its west edge to
			-- its middle: the road from south to north goes round the river's end
			local nx = 33
			local heights, paint = table.create(nx * nx, 5), table.create(nx * nx, "0")
			for ix = 0, 15 do
				paint[ix * nx + 16 + 1] = "1"
			end
			fs.writeDir("build/scratch/routespec")
			fs.writeFile(
				"build/scratch/routespec/river.hm.json",
				serde.encode("json", {
					nx = nx,
					nz = nx,
					step = 4,
					heights = heights,
					roles = { "meadow", "river" },
					paint = table.concat(paint),
				})
			)
			local river = {
				{
					heightmap = {
						center = { 0, 0, 0 },
						size = { 128, 128 },
						source = "build/scratch/routespec/river.hm.json",
						material = "Grass",
					},
				},
			}
			local _, _, errors, routes = laid(
				{ ground = true, route = { from = { -40, -40 }, to = { -40, 40 }, grade = 0.25, cell = 4 } },
				river
			)
			check.equal(#errors, 0)
			local east = -math.huge
			for _, pt in routes[1].points do
				east = math.max(east, pt[1])
			end
			check.truthy(east >= -2) -- (round the river's end at x -2: not straight across it)
			check.truthy(routes[1].length > 80 * 1.3)
			-- ... a river from edge to edge: no way, said
			for ix = 0, nx - 1 do
				paint[ix * nx + 16 + 1] = "1"
			end
			fs.writeFile(
				"build/scratch/routespec/river.hm.json",
				serde.encode("json", {
					nx = nx,
					nz = nx,
					step = 4,
					heights = heights,
					roles = { "meadow", "river" },
					paint = table.concat(paint),
				})
			)
			local _, _, shut = laid(
				{ ground = true, route = { from = { -40, -40 }, to = { -40, 40 }, grade = 0.25, cell = 4 } },
				river
			)
			check.truthy(#shut == 1 and string.find(shut[1], "no way", 1, true) ~= nil)
			fs.removeDir("build/scratch/routespec")

			-- a lake that a season freezes is still a lake to the road: the same road in winter, not one under the ice
			local function world(season: any): any
				return {
					name = "T",
					palette = PALETTE,
					lighting = "noon",
					terrain = {
						{ ground = { center = { 0, 10, 0 }, size = { 768, 768 }, material = "Grass" } },
						{ water = { center = { 0, 8, 0 }, size = { 120, 8, 200 } } },
					},
					seasons = { winter = { terrain = { Water = "Glacier" } } },
					season = season,
					build = {
						{
							path = {
								name = "Road",
								ground = true,
								width = 8,
								mat = "stone",
								curve = false,
								route = { from = { -250, 0 }, to = { 250, 0 }, grade = 0.2 },
							},
						},
					},
				}
			end
			local _, _, _, summer = World.compile(world(false))
			local _, _, issues, winter = World.compile(world("winter"))
			for _, i in issues do
				check.truthy(i.severity ~= "error", i.message)
			end
			check.truthy(#summer.routes[1].points > 2)
			check.equal(#winter.routes[1].points, #summer.routes[1].points)
			check.equal(winter.routes[1].points[2][2], summer.routes[1].points[2][2])

			-- a routed road says whether its corners are rounded; rounded, it is measured as it is laid
			local flatLand = { { ground = ROLLING } }
			local _, _, unsaid = laid(
				{ ground = true, curve = "?", route = { from = { -300, -250 }, to = { 300, 260 }, grade = 0.15 } },
				flatLand
			)
			check.truthy(#unsaid == 1 and string.find(unsaid[1], 'a routed road says "curve"', 1, true) ~= nil)
			local _, _, none, sharp = laid(
				{ ground = true, curve = false, route = { from = { -300, -250 }, to = { 300, 260 }, grade = 0.15 } },
				flatLand
			)
			local _, roads, noErrors, rounded = laid(
				{ ground = true, curve = true, route = { from = { -300, -250 }, to = { 300, 260 }, grade = 0.15 } },
				flatLand
			)
			check.equal(#none + #noErrors, 0)
			check.truthy(#rounded[1].points > #sharp[1].points * 3) -- (the curve's own points)
			check.truthy(#roads > 100)
			-- (re-measured here: what is handed back is the laid line's own measure)
			local line = {}
			for _, pt in rounded[1].points do
				table.insert(line, { pt[1], pt[2] })
			end
			local length, _, _, steepest = Route.measure(function(x: number, z: number): number?
				return World.groundHeight(ROLLING, x, z)
			end, line)
			check.truthy(math.abs(steepest - rounded[1].steepest) < 1e-9)
			check.truthy(math.abs(length - rounded[1].length) < 1e-6)
		end)

		test.case(
			"the compiler: a circle typed wrongly is an error, not a crash; the lock counts roads together",
			function()
				local flatLand = { { ground = { center = { 0, 10, 0 }, size = { 768, 768 }, material = "Grass" } } }
				for _, avoid in { { { 0, 0 } }, { { x = 0 } }, 5 } :: { any } do
					local _, roads, errors = laid(
						{ ground = true, avoid = avoid, route = { from = { -100, 0 }, to = { 100, 0 }, grade = 0.2 } },
						flatLand
					)
					check.equal(#roads, 0)
					check.truthy(
						#errors == 1 and string.find(errors[1], '"avoid" is a list of circles', 1, true) ~= nil
					)
				end
				-- the road keeps half its width off a circle (read every stud at a cell of 2)
				local _, _, _, round = laid({
					ground = true,
					avoid = { { 0, 0, 80 } },
					route = { from = { -250, 0 }, to = { 250, 0 }, grade = 0.2, cell = 2 },
				}, flatLand)
				local clear = {}
				for _, pt in round[1].points do
					table.insert(clear, { pt[1], 0, pt[2] })
				end
				check.truthy(nearest(clear, 0, 0) >= 80 + 4 - 1.01)
				-- one road cut into two short ones is asked the same
				local two = {
					build = {
						{ path = { name = "A", ground = true, points = { { 0, 0 }, { 150, 0 } } } },
						{ path = { name = "B", ground = true, points = { { 150, 0 }, { 300, 0 } } } },
					},
				}
				check.equal(#LaneLocks.unsaidRoutes(two), 2)
				two.build[2].path.route = false
				check.equal(#LaneLocks.unsaidRoutes(two), 0)
			end
		)
	end)
end

-- worldtown.spec.luau (kit) — the town-plan generator (kit/lib/worldtown.luau): a square entered at its corners,
-- streets as a graph with no dead end and no grid crossing, blocks built round their edge in lots on a 4-stud grid,
-- one landmark on the main gate's line of sight; and what the world compiler makes of a "town" step.
local frk = require("../frk")
local test, check = frk.test, frk.check

local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Config = require("../../lib/config")
local Run = require("../../lib/run")
local Town = require("../../lib/worldtown")
local World = require("../../lib/world")
local WorldCmd = require("../../cmd/world")

-- kit world town --kit as the specs call it: a refusal a case ASKS for is not printed as a failure of the run
local function townKit(target: string, out: string?, lists: string?): (any, string?)
	Run.expectingFailure = true
	local step, wrote = WorldCmd.townKit(target, out, lists)
	Run.expectingFailure = false
	return step, wrote
end

local MATS = { street = "cobble", block = "pave", wall = "plaster", roof = "slate" }
local PALETTE = {
	cobble = { material = "Cobblestone", color = { 84, 82, 80 } },
	pave = { material = "Slate", color = { 98, 96, 94 } },
	plaster = { material = "Concrete", color = { 150, 140, 124 } },
	slate = { material = "Slate", color = { 58, 60, 68 } },
}

local function spec(seed: number, gates: { string }?, more: any?): any
	local s: any = { center = { 0, 0, 0 }, area = { 320, 320 }, seed = seed, gates = gates or { "S" }, mats = MATS }
	for k, v in more or {} do
		s[k] = v
	end
	return s
end

local function errors(plan: any): string
	local out = {}
	for _, i in plan.issues do
		if i.severity == "error" then
			table.insert(out, i.message)
		end
	end
	return table.concat(out, "\n")
end

local function overlap(a: any, b: any): boolean
	return math.min(a.x1, b.x1) - math.max(a.x0, b.x0) > 0.01 and math.min(a.z1, b.z1) - math.max(a.z0, b.z0) > 0.01
end

local function onGrid(v: number): boolean
	return math.abs(v / 4 - math.floor(v / 4 + 0.5)) < 1e-6
end

local SIDES = { { "S" }, { "N" }, { "E" }, { "W" }, { "S", "E" }, { "N", "S", "E", "W" } }

return function()
	test.suite("Town plan: the same town from the same seed", function()
		test.case("a seed gives one plan, another seed another", function()
			local a, b, c = Town.plan(spec(7)), Town.plan(spec(7)), Town.plan(spec(8))
			check.equal(#a.lots, #b.lots)
			check.equal(#a.streets, #b.streets)
			for k, lot in a.lots do
				check.equal(lot.rect.x0, b.lots[k].rect.x0)
				check.equal(lot.rect.z1, b.lots[k].rect.z1)
				check.equal(lot.type, b.lots[k].type)
			end
			local same = #a.streets == #c.streets
			if same then
				for k, s in a.streets do
					if s.at ~= c.streets[k].at or s.from ~= c.streets[k].from then
						same = false
					end
				end
			end
			check.is_false(same)
		end)
	end)

	test.suite("Town plan: every line on the grid, nothing on top of anything", function()
		test.case("streets, blocks, the square and lots lie on the 4-stud grid", function()
			for seed = 1, 8 do
				local plan = Town.plan(spec(seed, SIDES[seed % #SIDES + 1]))
				check.equal(errors(plan), "")
				for _, s in plan.streets do
					local r = Town.strip(s)
					check.is_true(onGrid(r.x0) and onGrid(r.x1) and onGrid(r.z0) and onGrid(r.z1))
				end
				for _, lot in plan.lots do
					local r = lot.rect
					check.is_true(onGrid(r.x0) and onGrid(r.x1) and onGrid(r.z0) and onGrid(r.z1))
				end
				local q = plan.square
				check.is_true(onGrid(q.x0) and onGrid(q.x1) and onGrid(q.z0) and onGrid(q.z1))
			end
		end)
		test.case("no lot lies on a street, on the square or on another lot; each lies inside one block", function()
			for seed = 1, 8 do
				local plan = Town.plan(spec(seed, SIDES[seed % #SIDES + 1]))
				for i, lot in plan.lots do
					check.is_false(overlap(lot.rect, plan.square))
					for _, s in plan.streets do
						check.is_false(overlap(lot.rect, Town.strip(s)))
					end
					for j = i + 1, #plan.lots do
						check.is_false(overlap(lot.rect, plan.lots[j].rect))
					end
					local B = plan.blocks[lot.block]
					local r = lot.rect
					check.is_true(
						r.x0 >= B.x0 - 0.01 and r.x1 <= B.x1 + 0.01 and r.z0 >= B.z0 - 0.01 and r.z1 <= B.z1 + 0.01
					)
				end
				for i, b in plan.blocks do
					check.is_false(overlap(b, plan.square))
					for _, s in plan.streets do
						check.is_false(overlap(b, Town.strip(s)))
					end
					for j = i + 1, #plan.blocks do
						check.is_false(overlap(b, plan.blocks[j]))
					end
				end
			end
		end)
		test.case("a frontage is cut into whole-grid lots that sum to it exactly", function()
			local rnd = function()
				return 0.37
			end
			for _, len in { 16, 32, 36, 60, 88, 124 } do
				local sum = 0
				for _, w in Town.cut(len, 16, 24, rnd, 4) do
					check.is_true(w >= 16 and w <= 24 and onGrid(w))
					sum += w
				end
				check.equal(sum, len)
			end
			-- 28 is no sum of 16..24 lots: one house of the odd size, never a gap or a 12-stud sliver beside a 16
			local odd = Town.cut(28, 16, 24, rnd, 4)
			check.equal(#odd, 1)
			check.equal(odd[1], 28)
		end)
		test.case("every door is on a street or the square", function()
			for seed = 1, 6 do
				local plan = Town.plan(spec(seed, { "S", "W" }))
				for _, lot in plan.lots do
					local r = lot.rect
					local front = if lot.front == "N"
						then { x0 = r.x0, x1 = r.x1, z0 = r.z0, z1 = r.z0 }
						elseif lot.front == "S" then { x0 = r.x0, x1 = r.x1, z0 = r.z1, z1 = r.z1 }
						elseif lot.front == "W" then { x0 = r.x0, x1 = r.x0, z0 = r.z0, z1 = r.z1 }
						else { x0 = r.x1, x1 = r.x1, z0 = r.z0, z1 = r.z1 }
					local faces = Town.touch(front, plan.square, 1)
					for _, s in plan.streets do
						faces = faces or Town.touch(front, Town.strip(s), 1)
					end
					check.is_true(faces)
				end
			end
		end)
	end)

	test.suite("Town plan: the street graph", function()
		test.case("with the wall street: no dead end, every junction joined to the square, loops to walk", function()
			for seed = 1, 12 do
				local gates = SIDES[seed % #SIDES + 1]
				local plan = Town.plan(spec(seed, gates))
				local m = Town.measure(plan)
				check.equal(m.deadEnds, 0)
				check.equal(m.cutOff, 0)
				check.equal(m.parts, 1)
				check.is_true(m.loops >= 4)
				check.equal(#m.walks, #gates) -- (every gate has a walk to the square)
				for _, w in m.walks do
					check.is_true(w.seconds > 0 and w.seconds < 60)
				end
			end
		end)
		test.case(
			"no lane lines up across a street: the only crossings are where a gate's street passes the wall street",
			function()
				for seed = 1, 12 do
					local gates = SIDES[seed % #SIDES + 1]
					local m = Town.measure(Town.plan(spec(seed, gates)))
					check.equal(m.crossings, #gates)
					check.is_true(m.tees >= 8) -- (a town of lanes, each ending on another street)
				end
			end
		)
		test.case("only the four arms open onto the square", function()
			for seed = 1, 12 do
				local plan = Town.plan(spec(seed, { "S", "E" }))
				local entries = 0
				for _, n in Town.measure(plan).graph.nodes do
					if n.kind == "entry" then
						entries += 1
					end
				end
				check.equal(entries, 4)
			end
		end)
		test.case("without the wall street the lanes run out of the town, and the measure says so", function()
			local plan = Town.plan(spec(3, { "S" }, { ring = false }))
			local exits = 0
			for _, n in Town.measure(plan).graph.nodes do
				if n.kind == "exit" then
					exits += 1
				end
			end
			check.is_true(exits >= 3)
		end)
		test.case("a street the graph cannot join is counted (a hand-broken plan)", function()
			local plan = Town.plan(spec(3))
			table.insert(
				plan.streets,
				{ name = "Stub", rank = "alley", axis = "x", at = 1000, from = 1000, to = 1100, width = 12 }
			)
			local m = Town.measure(plan)
			check.equal(m.deadEnds, 2) -- (both ends of the stub)
			check.is_true(m.cutOff >= 2)
			check.equal(m.parts, 2)
		end)
	end)

	test.suite("Town plan: the landmark and the houses", function()
		test.case(
			"the landmark stands on the square where the main gate's street points, taller than every house",
			function()
				for seed = 1, 10 do
					for _, gates in SIDES do
						local plan = Town.plan(spec(seed, gates))
						local lm = nil
						for _, lot in plan.lots do
							if lot.landmark then
								check.is_true(lm == nil) -- (one only)
								lm = lot
							end
						end
						check.not_nil(lm)
						local r, v = lm.rect, plan.view.at
						check.equal(lm.rank, Town.RANK.square)
						-- the line of sight lands on its front
						if lm.front == "S" or lm.front == "N" then
							check.is_true(v[1] >= r.x0 and v[1] <= r.x1)
						else
							check.is_true(v[2] >= r.z0 and v[2] <= r.z1)
						end
						for _, lot in plan.lots do
							if lot ~= lm then
								check.is_true(lot.floors * lot.floorHeight < lm.floors * lm.floorHeight)
							end
						end
					end
				end
			end
		)
		test.case(
			"no two houses side by side in a row stand to the same height (their roofs would share a plane)",
			function()
				for seed = 1, 8 do
					local plan = Town.plan(spec(seed, { "S", "E" }))
					local pairs = 0
					for i, a in plan.lots do
						for j = i + 1, #plan.lots do
							local b = plan.lots[j]
							local touching = a.block == b.block
								and a.front == b.front
								and math.min(a.rect.x1, b.rect.x1) - math.max(a.rect.x0, b.rect.x0) > -0.01
								and math.min(a.rect.z1, b.rect.z1) - math.max(a.rect.z0, b.rect.z0) > -0.01
							if touching then
								pairs += 1
								check.is_true(math.abs(a.floors * a.floorHeight - b.floors * b.floorHeight) >= 1)
							end
						end
					end
					check.is_true(pairs > 20) -- (the rule was tried: a town has rows)
				end
			end
		)
		test.case("houses of one type are one house: same front, depth and storeys", function()
			local plan = Town.plan(spec(5, { "S", "E" }, { floorHeights = { 14 } }))
			local seen: { [string]: any } = {}
			local count = 0
			for _, lot in plan.lots do
				local r = lot.rect
				local alongX = lot.front == "N" or lot.front == "S"
				local fw = if alongX then r.x1 - r.x0 else r.z1 - r.z0
				local dp = if alongX then r.z1 - r.z0 else r.x1 - r.x0
				local was = seen[lot.type]
				if was then
					check.equal(was.fw, fw)
					check.equal(was.dp, dp)
					check.equal(was.floors, lot.floors)
					check.equal(was.corner, lot.corner ~= nil)
				else
					seen[lot.type] = { fw = fw, dp = dp, floors = lot.floors, corner = lot.corner ~= nil }
					count += 1
				end
			end
			check.equal(Town.measure(plan).types, count)
			check.is_true(count < #plan.lots) -- (types repeat: a kit, not a house apiece)
			local record = Town.record("T", plan)
			check.equal(#record.types, count)
		end)
	end)

	test.suite("Town plan: what it refuses", function()
		test.case("no room for the square, no gate, a missing material, a width off the grid", function()
			check.is_true(errors(Town.plan(spec(1, { "S" }, { area = { 120, 120 } }))):find("too small") ~= nil)
			check.is_true(errors(Town.plan(spec(1, {}))):find("at least one gate") ~= nil)
			check.is_true(errors(Town.plan(spec(1, { "Q" }))):find('"N" | "E" | "S" | "W"', 1, true) ~= nil)
			check.is_true(
				errors(Town.plan(spec(1, { "S" }, { mats = { street = "cobble" } }))):find('needs "wall"', 1, true)
					~= nil
			)
			check.is_true(errors(Town.plan(spec(1, { "S" }, { streets = { alley = 10 } }))):find("grid") ~= nil)
			-- a square put where no row of houses fits beside it is said, not silently moved
			check.is_true(
				errors(Town.plan(spec(1, { "S" }, { square = { at = { 130, 0 } } }))):find(
					"no room for a row of houses"
				) ~= nil
			)
		end)
	end)

	test.suite("World compiler: a town step", function()
		local function compile(town: any, more: { any }?): (any, { any }, { any }, any)
			local build: { any } = { { town = town } }
			for _, s in more or {} do
				table.insert(build, s)
			end
			return World.compile({ name = "T", palette = PALETTE, build = build })
		end
		-- how many pairs of faces the compiler finds in one plane (its z-fighting warning: the first five named, then a total)
		local function coplanar(issues: { any }): number
			local named, total = 0, nil
			for _, i in issues do
				local n = i.message:match("^(%d+) coplanar overlapping faces in total")
				if n then
					total = tonumber(n)
				elseif i.message:find("z%-fighting") then
					named += 1
				end
			end
			return total or named
		end
		test.case(
			"it compiles to houses with no error, and puts no two faces in one plane that a house alone has not",
			function()
				for seed = 1, 4 do
					local s = spec(seed, { "S", "E" }, { name = "Old Town", area = { 256, 224 } })
					local plan = Town.plan(s)
					local _, parts, issues, extras = compile(s)
					for _, i in issues do
						check.is_false(i.severity == "error")
					end
					-- (the building generator's own warnings - a lintel's top under the floor above - are each house's; what
					-- a town could ADD is a kerb in a slab's plane, or two neighbours' party walls on one line)
					-- the same houses stood far apart (no kerb under them, no neighbour beside them), in one compile
					local apart: { any } = {}
					for _, step in Town.steps(plan, s) do
						if step.building then
							local b = table.clone(step.building)
							b.center = { #apart * 1000, 0, 0 }
							table.insert(apart, { building = b })
						end
					end
					local _, _, own = World.compile({ name = "T", palette = PALETTE, build = apart })
					local alone = coplanar(own)
					check.is_true(coplanar(issues) <= alone)
					check.is_true(#parts > 500)
					check.equal(#extras.towns, 1)
					check.equal(extras.towns[1].name, "Old Town")
					check.equal(#extras.towns[1].lots, #plan.lots)
					-- every house claims its door, the streets claim their widths (kit world check measures them)
					local doors, streets, alleys = 0, 0, 0
					for _, f in extras.fits do
						if f.kind == "opening" then
							doors += 1
						elseif f.kind == "street" then
							streets += 1
						elseif f.kind == "alley" then
							alleys += 1
						end
					end
					check.equal(doors, #plan.lots)
					check.equal(streets, 2) -- (the two gates' streets)
					check.is_true(alleys >= 4)
				end
			end
		)
		test.case("its messages carry the town step's own path, and the steps after it keep theirs", function()
			local _, _, issues = compile(
				spec(2, { "S" }, { area = { 256, 224 }, mats = { street = "cobble", wall = "nope", roof = "slate" } }),
				{
					{ part = { size = { 1, 1, 1 }, pos = { 0, 5, 0 }, mat = "missing" } },
				}
			)
			local town, after = false, false
			for _, i in issues do
				if i.path:sub(1, 15) == "build[1].town.H" then
					town = true
				end
				if i.path:sub(1, 8) == "build[2]" and i.message:find("missing") then
					after = true
				end
			end
			check.is_true(town)
			check.is_true(after)
		end)
		test.case('"skins" asks one mesh per house type, and says which are not made', function()
			local s = spec(2, { "S" }, { area = { 256, 224 }, skins = "gh", floorHeights = { 14 } })
			local _, _, issues = compile(s)
			local types = Town.measure(Town.plan(s)).types
			local asked: { [string]: boolean } = {}
			local n = 0
			for _, i in issues do
				local name = i.message:match('no world mesh "(gh_[%w_]+)"')
				if name and not asked[name] then
					asked[name] = true
					n += 1
				end
			end
			check.equal(n, types)
		end)
		test.case("a town on a slope is said to be flat", function()
			local _, _, issues = compile(spec(2, { "S" }, { area = { 256, 224 }, ground = true }))
			local said = false
			for _, i in issues do
				said = said or i.message:find("level ground") ~= nil
			end
			check.is_true(said)
		end)
	end)

	-- what a fresh reader broke on 2026-11-13 (each case failed before its fix)
	test.suite("Town plan: the cases a fresh reader broke", function()
		local function landmarkOf(plan: any): any
			local found = nil
			for _, lot in plan.lots do
				if lot.landmark then
					found = lot
				end
			end
			return found
		end
		test.case("a landmark in every town: other sizes, the square on a block's short end", function()
			-- (256 x 224 with gates E + W, seed 3, had none: its block on the line of sight was 40 studs long, its houses
			-- faced away from the square)
			local towns = 0
			for _, area in { { 256, 224 }, { 400, 300 }, { 480, 480 }, { 224, 200 } } do
				for _, gates in { { "E", "W" }, { "W", "S", "E" }, { "S", "N" }, { "N" }, { "W" } } do
					for seed = 1, 12 do
						local plan = Town.plan(spec(seed, gates, { area = area }))
						check.equal(errors(plan), "")
						local lm = landmarkOf(plan)
						check.not_nil(lm)
						if lm then
							local r, v = lm.rect, plan.view.at
							if lm.front == "S" or lm.front == "N" then
								check.is_true(v[1] >= r.x0 and v[1] <= r.x1)
							else
								check.is_true(v[2] >= r.z0 and v[2] <= r.z1)
							end
						end
						towns += 1
					end
				end
			end
			check.equal(towns, 240)
			local once = Town.plan(spec(3, { "E", "W" }, { area = { 256, 224 } }))
			check.not_nil(landmarkOf(once))
		end)
		test.case("the landmark is inside the height rule, and one no taller than a house is refused", function()
			-- typed at 5 storeys of 14 = 70: taller than any house (4 x 15 = 60), and no row neighbour shares its top
			for seed = 1, 20 do
				local plan = Town.plan(spec(seed, { "S" }, { landmark = { floors = 5 } }))
				check.equal(errors(plan), "")
				local lm = landmarkOf(plan)
				for _, lot in plan.lots do
					if lot ~= lm then
						check.is_true(lot.floors * lot.floorHeight < lm.floors * lm.floorHeight)
					end
				end
			end
			-- 4 storeys of 14 = 56 is a house's height (4 x 14): refused, with the numbers
			local low = errors(Town.plan(spec(2, { "S" }, { landmark = { floors = 4 } })))
			check.is_true(low:find("no taller than the tallest house", 1, true) ~= nil)
			check.is_true(low:find("56", 1, true) ~= nil and low:find("60", 1, true) ~= nil)
		end)
		test.case(
			"a storey range typed backwards, or as one number, is an error - never a crash or a silent default",
			function()
				local back = Town.plan(spec(1, { "S" }, { floors = { lane = { 3, 2 } } }))
				check.is_true(errors(back):find("floors.lane [3, 2] is not a range", 1, true) ~= nil)
				check.is_true(#back.lots > 0) -- (the plan is still made, on the default range)
				check.is_true(
					errors(Town.plan(spec(1, { "S" }, { floors = { lane = 3 } }))):find(
						"floors.lane needs two numbers",
						1,
						true
					) ~= nil
				)
				check.is_true(
					errors(Town.plan(spec(1, { "S" }, { area = { 256 } }))):find("area needs two numbers", 1, true)
						~= nil
				)
				check.is_true(
					errors(Town.plan(spec(1, { "S" }, { lots = { depth = { 24 } } }))):find(
						"lots.depth needs two numbers",
						1,
						true
					) ~= nil
				)
				-- the compiler passes the error on instead of throwing
				local _, _, issues = World.compile({
					name = "T",
					palette = PALETTE,
					build = { { town = spec(1, { "S" }, { area = { 256, 224 }, floors = { lane = { 3, 2 } } }) } },
				})
				local said = false
				for _, i in issues do
					said = said or (i.severity == "error" and i.message:find("floors.lane", 1, true) ~= nil)
				end
				check.is_true(said)
			end
		)
		test.case("one possible top for a rank is said (houses side by side would share a roof plane)", function()
			local one = Town.plan(spec(1, { "S" }, {
				floorHeights = { 14 },
				floors = { square = { 3, 3 }, main = { 3, 3 }, lane = { 2, 2 }, alley = { 2, 2 } },
			}))
			local warned = 0
			for _, i in one.issues do
				if i.severity == "warn" and i.message:find("share a roof plane", 1, true) then
					warned += 1
				end
			end
			check.equal(warned, 4)
			-- two storey counts, or two storey heights, and nothing is said
			for _, i in Town.plan(spec(1, { "S" }, { floorHeights = { 14 } })).issues do
				check.is_true(i.message:find("share a roof plane", 1, true) == nil)
			end
		end)
		test.case('"skins" is a name: anything else is refused (it would skin nothing)', function()
			for _, bad in { true, 1, { "gh" }, "" } do
				check.is_true(
					errors(Town.plan(spec(1, { "S" }, { skins = bad }))):find('"skins" is the name', 1, true) ~= nil
				)
			end
			check.equal(errors(Town.plan(spec(1, { "S" }, { skins = "gh" }))), "")
		end)
		test.case(
			"the longest view is a street between houses; one that leaves by a gate is said to run out",
			function()
				for seed = 1, 20 do
					local plan = Town.plan(spec(seed, { "S", "E" }))
					local v = Town.measure(plan).vista
					check.is_true(v.street:sub(1, 11) ~= "Wall street")
					check.is_true(v.length > 0)
					local street = nil
					for _, s in plan.streets do
						if s.name == v.street then
							street = s
						end
					end
					check.equal(v.closed, street.gate == nil)
				end
				-- with no wall street a lane that reaches the edge runs out of the town too
				local open = Town.plan(spec(3, { "S" }, { ring = false }))
				local v = Town.measure(open).vista
				for _, s in open.streets do
					if s.name == v.street then
						local out = if s.axis == "z"
							then (s.from == open.area.z0 or s.to == open.area.z1)
							else (s.from == open.area.x0 or s.to == open.area.x1)
						check.equal(v.closed, not out)
					end
				end
			end
		)
		test.case("with trim no two posts share a plane: the gap is kept behind and beside every house", function()
			-- (the gap was taken off a house's front axis only: rows back to back stood on one line)
			local function coplanar(issues: { any }): number
				local named, total = 0, nil
				for _, i in issues do
					local n = i.message:match("^(%d+) coplanar overlapping faces in total")
					if n then
						total = tonumber(n)
					elseif i.message:find("z%-fighting") then
						named += 1
					end
				end
				return total or named
			end
			for seed = 1, 3 do
				local s = spec(seed, { "S", "E" }, {
					area = { 256, 224 },
					mats = { street = "cobble", block = "pave", wall = "plaster", roof = "slate", trim = "slate" },
				})
				local plan = Town.plan(s)
				check.equal(plan.gap, 2)
				local steps = Town.steps(plan, s)
				local _, _, issues = World.compile({ name = "T", palette = PALETTE, build = { { town = s } } })
				local apart: { any } = {}
				for _, step in steps do
					if step.building then
						local b = table.clone(step.building)
						b.center = { #apart * 1000, 0, 0 }
						table.insert(apart, { building = b })
					end
				end
				local _, _, own = World.compile({ name = "T", palette = PALETTE, build = apart })
				check.is_true(coplanar(own) > 0) -- (posts and bands are there: the count is of something)
				check.is_true(coplanar(issues) <= coplanar(own))
			end
		end)
		test.case(
			"houses of one type are the same BUILDING: size, storeys, door and windows in the house's own frame",
			function()
				-- the house's own side for a world side, by the compiler's turn
				local function own(front: string, side: string): string
					for _, o in { "S", "E", "N", "W" } do
						if World.skinSide(World.SKIN_YAW[front], o) == side then
							return o
						end
					end
					return "?"
				end
				for seed = 1, 10 do
					local s = spec(seed, { "S", "W" }, { skins = "gh" })
					local seen: { [string]: string } = {}
					local repeats = 0
					for _, step in Town.steps(Town.plan(s), s) do
						local b = step.building
						if b then
							local alongX = b.door.side == "N" or b.door.side == "S"
							local sides = {}
							for _, side in b.windows.sides do
								table.insert(sides, own(b.door.side, side))
							end
							table.sort(sides)
							local key = table.concat({
								if alongX then b.size[1] else b.size[2],
								if alongX then b.size[2] else b.size[1],
								b.floors,
								b.floorHeight,
								b.door.width,
								b.door.height,
								table.concat(sides, ""),
							}, "|")
							if seen[b.skin] then
								repeats += 1
								check.equal(seen[b.skin], key)
							else
								seen[b.skin] = key
							end
						end
					end
					check.is_true(repeats > 10)
				end
			end
		)
		test.case("a template's window sides are the house's own, turned to every lot", function()
			-- "sides": ["S"] = windows on each house's FRONT (it gave north-facing houses windows on their backs only)
			local s = spec(
				4,
				{ "S", "E" },
				{ house = { windows = { every = 10, width = 4, height = 7, sill = 3.5, sides = { "S" } } } }
			)
			local fronts: { [string]: number } = {}
			for _, step in Town.steps(Town.plan(s), s) do
				local b = step.building
				if b then
					check.equal(#b.windows.sides, 1)
					check.equal(b.windows.sides[1], b.door.side)
					fronts[b.door.side] = (fronts[b.door.side] or 0) + 1
				end
			end
			check.is_true((fronts.N or 0) > 0 and (fronts.S or 0) > 0 and (fronts.E or 0) > 0 and (fronts.W or 0) > 0)
			for front, row in Town.TURN do
				for o, side in row do
					check.equal(World.skinSide(World.SKIN_YAW[front], o), side)
				end
			end
		end)
		test.case("every BUILDING's door is on a street or the square", function()
			for seed = 1, 6 do
				local s = spec(seed, { "S", "W" })
				local plan = Town.plan(s)
				local doors = 0
				for _, step in Town.steps(plan, s) do
					local b = step.building
					if b then
						-- the building's own door wall, a stud outside its footprint
						local hw, hd = b.size[1] / 2 + 1, b.size[2] / 2 + 1
						local x, z = b.center[1], b.center[3]
						local probe = if b.door.side == "N"
							then { x0 = x - 2, x1 = x + 2, z0 = z - hd - 1, z1 = z - hd }
							elseif b.door.side == "S" then { x0 = x - 2, x1 = x + 2, z0 = z + hd, z1 = z + hd + 1 }
							elseif b.door.side == "W" then { x0 = x - hw - 1, x1 = x - hw, z0 = z - 2, z1 = z + 2 }
							else { x0 = x + hw, x1 = x + hw + 1, z0 = z - 2, z1 = z + 2 }
						local on = overlap(probe, plan.square)
						for _, st in plan.streets do
							on = on or overlap(probe, Town.strip(st))
						end
						check.is_true(on)
						doors += 1
					end
				end
				check.equal(doors, #plan.lots)
			end
		end)
		test.case("the record the plan page reads has every field the page reads", function()
			local s = spec(3, { "S" }, { name = "Old Town", area = { 256, 224 } })
			local r = Town.record("Old Town", Town.plan(s))
			for _, key in
				{
					"name",
					"seed",
					"area",
					"square",
					"streets",
					"blocks",
					"lots",
					"types",
					"gates",
					"view",
					"nodes",
					"measures",
					"summary",
				}
			do
				check.not_nil(r[key])
			end
			for _, key in { "name", "rank", "axis", "at", "from", "to", "width" } do
				check.not_nil(r.streets[1][key])
			end
			for _, key in { "name", "rect", "front", "floors", "type" } do
				check.not_nil(r.lots[1][key])
			end
			for _, key in { "type", "count", "footprint", "floors", "floorHeight" } do
				check.not_nil(r.types[1][key])
			end
			for _, key in { "x", "z", "kind", "degree" } do
				check.not_nil(r.nodes[1][key])
			end
			for _, key in
				{
					"lots",
					"blocks",
					"loops",
					"deadEnds",
					"tees",
					"crossings",
					"squareClosed",
					"walks",
					"farthestSeconds",
					"vista",
					"frontageBuilt",
					"streets",
					"cutOff",
				}
			do
				check.not_nil(r.measures[key])
			end
			check.not_nil(r.measures.walks[1].gate)
			check.not_nil(r.measures.walks[1].seconds)
			check.not_nil(r.view.at)
			check.equal(r.measures.graph, nil) -- (the graph itself stays out of the build file)
			local landmarks = 0
			for _, lot in r.lots do
				if lot.landmark then
					landmarks += 1
				end
			end
			check.equal(landmarks, 1)
		end)
	end)

	-- the KIT OF HOUSES (Town.kit, kit world town --kit): a skinned town's mesh recipes, one per house type
	test.suite("Town kit: one mesh recipe per house type", function()
		-- a recipe as kit/world/meshes_blender.py files it in build/worldmeshes/meshes.json (what the compiler reads),
		-- WITH that file's own defaults for what a recipe leaves out (main(): a door 5 x 9, windows 3.4 x 7 every 10):
		-- a number the recipe does not say is a number the two sides may disagree on
		local function registry(recipes: { any }): { [string]: any }
			local reg = {}
			for _, r in recipes do
				local w, d = r.windows or {}, r.door or {}
				reg[r.name] = {
					footprint = { r.width or 22, r.depth or 22 },
					floors = r.floors or 4,
					floorHeight = r.floorHeight or 14,
					windows = {
						every = w.every or 10,
						width = w.width or 3.4,
						height = w.height or 7,
						sill = w.sill or 3.5,
						sides = w.sides or { "N", "E", "S", "W" },
					},
					door = { side = d.side or "S", width = d.width or 5, height = d.height or 9 },
				}
			end
			return reg
		end
		local function misfits(s: any, reg: { [string]: any }): (number, number, string?)
			local n, houses, first = 0, 0, nil
			for _, step in Town.steps(Town.plan(s), s) do
				local b = step.building
				if b then
					houses += 1
					local why = World.skinProblem(
						reg[b.skin],
						b.skin,
						b.size,
						b.floors,
						b.floorHeight,
						b.door,
						b.windows,
						World.SKIN_YAW[b.door.side]
					)
					if why then
						n += 1
						first = first or why
					end
				end
			end
			return n, houses, first
		end
		test.case("a mesh's own side for a house's side is the compiler's turn, read backwards", function()
			for front, yaw in World.SKIN_YAW do
				for _, own in { "S", "E", "N", "W" } do
					check.equal(Town.SKIN_SIDE[front][World.skinSide(yaw, own)], own)
				end
			end
		end)
		test.case(
			"every house of a skinned town fits the recipe of its type (the compiler's own skin check)",
			function()
				local houses = 0
				for seed = 1, 12 do
					for _, gates in SIDES do
						local s = spec(seed, gates, { skins = "gh" })
						local plan = Town.plan(s)
						local recipes, problem = Town.kit(plan, s)
						check.equal(problem, nil)
						check.equal(#recipes, Town.measure(plan).types) -- (one recipe a type, no more)
						local bad, n, why = misfits(s, registry(recipes))
						check.equal(why, nil)
						check.equal(bad, 0)
						houses += n
					end
				end
				check.is_true(houses > 3000)
			end
		)
		test.case(
			"the check is live here: a recipe cut a storey short, or with a window side dropped, is named",
			function()
				local s = spec(4, { "S", "E" }, { skins = "gh" })
				local recipes = Town.kit(Town.plan(s), s)
				local short = registry(recipes)
				for _, r in short do
					r.floors -= 1
				end
				local bad, houses, why = misfits(s, short)
				check.equal(bad, houses)
				check.is_true(why ~= nil and why:find("floors") ~= nil)
				local blind = registry(recipes)
				local corners = 0
				for name, r in blind do
					if name:find("_[ew]$") or name:find("_[ew]_t$") then
						r.windows = table.clone(r.windows)
						r.windows.sides = { "S" }
						corners += 1
					end
				end
				check.is_true(corners > 0)
				local badSides, _, whySides = misfits(s, blind)
				check.is_true(badSides >= corners)
				check.is_true(whySides ~= nil and whySides:find("windows on") ~= nil)
			end
		)
		test.case("with trim the houses stand apart and their recipes are cut narrower to match", function()
			local s = spec(4, { "S" }, { skins = "gh", house = { trim = "plaster" } })
			local plan = Town.plan(s)
			check.equal(plan.gap, 2)
			local recipes = Town.kit(plan, s)
			local bad = misfits(s, registry(recipes))
			check.equal(bad, 0)
			for _, r in recipes do
				local front = tonumber(r.name:match("(%d+)x%d+_"))
				check.equal(r.width, front - 2 - 1) -- (the lot's front less the gap less one wall)
			end
		end)
		test.case("recipes are steady, sorted and named by type; the looks come from the town's kit", function()
			local s = spec(6, { "S" }, {
				skins = "old",
				kit = { stones = { { 80, 80, 90 }, { 100, 96, 90 } }, slate = { 20, 22, 30 }, chimneys = 1 },
			})
			local a, b = Town.kit(Town.plan(s), s), Town.kit(Town.plan(s), s)
			check.equal(serde.encode("json", a), serde.encode("json", b))
			local stones: { [string]: boolean } = {}
			local landmarks = 0
			for k, r in a do
				check.equal(r.kind, "gothic_house")
				check.equal(r.name:sub(1, 4), "old_")
				check.equal(r.door.side, "S") -- (a mesh's front is its S side; the compiler turns it to the door)
				check.is_true(table.find(r.windows.sides, "S") ~= nil)
				check.is_true(r.gable.height >= 8 and r.gable.height <= 30 and r.gable.steps >= 3)
				if k > 1 then
					check.is_true(a[k - 1].name < r.name)
				end
				stones[serde.encode("json", r.stone)] = true
				check.equal(serde.encode("json", r.slate), "[20,22,30]")
				if r.name:find("landmark") then
					landmarks += 1
					check.is_false(r.chimney) -- (a hall, not a house)
				else
					check.is_true(r.chimney) -- (chimneys = 1: every house)
				end
			end
			check.equal(landmarks, 1)
			local count = 0
			for _ in stones do
				count += 1
			end
			check.equal(count, 2) -- (both stones are used)
		end)
		test.case("a town with no skins has no kit, and says what to add", function()
			local s = spec(2)
			local recipes, problem = Town.kit(Town.plan(s), s)
			check.equal(#recipes, 0)
			check.is_true(problem ~= nil and problem:find('"skins"', 1, true) ~= nil)
		end)
		test.case(
			"kit world town --kit writes the list from the blueprint; two towns may not share a mesh name",
			function()
				local dir = Config.build("selftest") .. "/worldtown_spec"
				Config.ensureDir(dir)
				local function write(name: string, build: { any }): string
					local path = `{dir}/{name}.json`
					fs.writeFile(path, serde.encode("json", { name = name, palette = PALETTE, build = build }))
					return path
				end
				local one = spec(3, { "S" }, { name = "Old", area = { 256, 224 }, skins = "gh" })
				local out = `{dir}/kit.json`
				local step, wrote = townKit(write("KitTown", { { town = one } }), out)
				check.is_true(step.ok)
				check.equal(wrote, out)
				local list = serde.decode("json", fs.readFile(out))
				check.equal(#list, Town.measure(Town.plan(one)).types)
				check.is_true(step.result.next_action:find("kit world meshes --set town_KitTown", 1, true) ~= nil)
				-- the same prefix on a second town whose houses are cut differently (other windows): refused, by name
				local two = spec(3, { "S" }, {
					name = "New",
					area = { 256, 224 },
					skins = "gh",
					house = { windows = { every = 10, width = 3, height = 7, sill = 3.5 } },
				})
				local clash = townKit(write("TwoTowns", { { town = one }, { town = two } }), `{dir}/two.json`)
				check.is_false(clash.ok)
				check.is_true(clash.tail:find("its own", 1, true) ~= nil and clash.tail:find("prefix", 1, true) ~= nil)
				check.is_false(fs.isFile(`{dir}/two.json`))
				-- no town, and a town with no skins
				check.is_false(townKit(write("NoTown", { { spawn = { pos = { 0, 0, 0 } } } }), `{dir}/none.json`).ok)
				local plain = townKit(write("Plain", { { town = spec(3) } }), `{dir}/plain.json`)
				check.is_false(plain.ok)
				check.is_true(plain.tail:find('"skins"', 1, true) ~= nil)
				for _, f in fs.readDir(dir) do
					fs.removeFile(`{dir}/{f}`)
				end
				fs.removeDir(dir)
			end
		)
		-- what a fresh reader broke on 2026-11-13 (each case failed before its fix)
		test.case(
			"a half-typed door or window template still fits: the recipe and the building read the same numbers",
			function()
				-- (a door typed as { width = 4.5 }: the recipe left its height out, the mesh registry filled in 9, the
				-- building generator 8.5, and every house of the town was refused its skin)
				local templates = {
					{ door = { width = 4.5 } },
					{ door = { height = 8 } },
					{ windows = { every = 8 } },
					{ windows = { width = 3, sill = 3 } },
					{ windows = { every = 10, width = 4, height = 7, sill = 3.5, sides = { "S", "N" } } },
					{ thickness = 2 },
					{ trim = "plaster", windows = { every = 8 } },
				}
				local houses = 0
				for k, house in templates do
					for seed = 1, 6 do
						local s = spec(seed, SIDES[(seed + k) % #SIDES + 1], { skins = "gh", house = house })
						local plan = Town.plan(s)
						check.equal(errors(plan), "")
						local bad, n, why = misfits(s, registry(Town.kit(plan, s)))
						check.equal(why, nil)
						check.equal(bad, 0)
						houses += n
					end
				end
				check.is_true(houses > 2000)
				-- and the recipe says every number itself
				local s = spec(
					2,
					{ "S" },
					{ skins = "gh", house = { door = { width = 4.5 }, windows = { every = 8 } } }
				)
				for _, r in Town.kit(Town.plan(s), s) do
					check.equal(r.door.width, 4.5)
					check.equal(r.door.height, 8.5)
					check.equal(r.windows.every, 8)
					check.equal(r.windows.width, 4)
					check.equal(r.windows.height, 7)
					check.equal(r.windows.sill, 3.5)
				end
			end
		)
		test.case("every house has a bay for its door: no lot leaves a front under a window's spacing + 4", function()
			-- (the building generator gives a wall floor((length - 4) / every) bays and puts the door in one: a 13-stud
			-- front - a 16-stud lot with trim - had none, a sealed box; a skin mesh cut a door into it all the same)
			local function bays(s: any): (number, number)
				local least, houses = math.huge, 0
				for _, step in Town.steps(Town.plan(s), s) do
					local b = step.building
					if b then
						local front = if b.door.side == "N" or b.door.side == "S" then b.size[1] else b.size[2]
						least = math.min(least, math.floor((front - 4) / b.windows.every))
						houses += 1
					end
				end
				return least, houses
			end
			for seed = 1, 10 do
				for _, more in
					{
						{},
						{
							mats = {
								street = "cobble",
								block = "pave",
								wall = "plaster",
								roof = "slate",
								trim = "slate",
							},
						},
						{ house = { thickness = 2 } },
						{ house = { windows = { every = 12 } } },
						{ area = { 256, 224 }, ring = false },
					}
				do
					local s = spec(seed, SIDES[seed % #SIDES + 1], more)
					check.equal(errors(Town.plan(s)), "")
					local least, houses = bays(s)
					check.is_true(houses > 20)
					check.is_true(least >= 1)
				end
			end
			-- a lot width TYPED too narrow is an error that names the front it leaves and the lot that fits
			local narrow = errors(Town.plan(spec(1, { "S" }, { lots = { width = { 12, 20 } } })))
			check.is_true(narrow:find("leaves a house a 11-stud front", 1, true) ~= nil)
			check.is_true(narrow:find("a lot of 16", 1, true) ~= nil)
			local trimmed =
				errors(Town.plan(spec(1, { "S" }, { lots = { width = { 16, 24 } }, house = { trim = "plaster" } })))
			check.is_true(trimmed:find("13-stud front", 1, true) ~= nil and trimmed:find("a lot of 20", 1, true) ~= nil)
		end)
		test.case("with trim a recipe is cut shallower as well as narrower", function()
			local s = spec(4, { "S" }, { skins = "gh", house = { trim = "plaster" } })
			for _, r in Town.kit(Town.plan(s), s) do
				local front, depth = r.name:match("(%d+)x(%d+)_")
				check.equal(r.width, tonumber(front) - 2 - 1)
				check.equal(r.depth, tonumber(depth) - 2 - 1)
			end
		end)
		test.case(
			"two towns cut alike share their meshes whatever they are called; a name another list cuts differently is refused",
			function()
				local dir = Config.build("selftest") .. "/worldtown_spec_lists"
				local lists = dir .. "/meshes"
				Config.ensureDir(lists)
				local function write(name: string, build: { any }): string
					local path = `{dir}/{name}.json`
					fs.writeFile(path, serde.encode("json", { name = name, palette = PALETTE, build = build }))
					return path
				end
				local old = spec(3, { "S" }, { name = "Old", area = { 256, 224 }, skins = "gh" })
				local new = spec(
					3,
					{ "S" },
					{ name = "New", center = { 600, 0, 0 }, area = { 256, 224 }, skins = "gh" }
				)
				local step, out =
					townKit(write("Twins", { { town = old }, { town = new } }), `{lists}/town_Twins.json`, lists)
				check.is_true(step.ok)
				local list = serde.decode("json", fs.readFile(out :: string))
				check.equal(#list, Town.measure(Town.plan(old)).types) -- (one set of meshes for both)
				for _, r in list do
					check.equal(r.town, nil) -- (a recipe carries no town's name)
				end
				-- another world asks for the same names with other windows: refused, naming the list that has them
				local other = spec(3, { "S" }, {
					name = "Other",
					area = { 256, 224 },
					skins = "gh",
					house = { windows = { every = 10, width = 3, height = 7, sill = 3.5 } },
				})
				local clash = townKit(write("Elsewhere", { { town = other } }), `{lists}/town_Elsewhere.json`, lists)
				check.is_false(clash.ok)
				check.is_true(
					clash.tail:find("town_Twins.json", 1, true) ~= nil and clash.tail:find("another", 1, true) ~= nil
				)
				check.is_false(fs.isFile(`{lists}/town_Elsewhere.json`))
				-- its own prefix, and it is written; writing Twins again over its own list is no clash
				other.skins = "oth"
				check.is_true(
					townKit(write("Elsewhere", { { town = other } }), `{lists}/town_Elsewhere.json`, lists).ok
				)
				check.is_true(townKit(`{dir}/Twins.json`, `{lists}/town_Twins.json`, lists).ok)
				-- a world with no name has no list to write
				fs.writeFile(
					`{dir}/Nameless.json`,
					serde.encode("json", { palette = PALETTE, build = { { town = old } } })
				)
				local nameless = townKit(`{dir}/Nameless.json`, `{lists}/x.json`, lists)
				check.is_false(nameless.ok)
				check.is_true(nameless.tail:find('no "name"', 1, true) ~= nil)
				for _, d in { lists, dir } do
					for _, f in fs.readDir(d) do
						if fs.isFile(`{d}/{f}`) then
							fs.removeFile(`{d}/{f}`)
						end
					end
				end
				fs.removeDir(lists)
				fs.removeDir(dir)
			end
		)
	end)
end

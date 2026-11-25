-- worldrooms.spec.luau (kit) — the rooms of a floor by rule (kit/lib/worldrooms.luau) and what the building
-- generator makes of them ("rooms": true).
local frk = require("../frk")
local test, check = frk.test, frk.check

local Rooms = require("../../lib/worldrooms")
local World = require("../../lib/world")

local PALETTE = { wall = { material = "Brick", color = { 140, 120, 104 } } }

local function near(a: number, b: number): boolean
	return math.abs(a - b) < 1e-6
end

-- every floor this spec walks: (plan, w, d, hall, seed)
local function eachPlan(body: (any, number, number, number, number) -> ())
	for _, size in { { 14, 22 }, { 19, 23 }, { 29, 33 }, { 40, 24 }, { 60, 60 }, { 9, 9 }, { 18, 8 } } do
		for _, hall in { 0, 6 } do
			for seed = 1, 25 do
				body(Rooms.plan(size[1], size[2], { hall = hall, seed = seed }), size[1], size[2], hall, seed)
			end
		end
	end
end

local function house(more: any?): any
	local b: any = {
		name = "House",
		center = { 0, 0, 0 },
		size = { 30, 34 },
		floors = 2,
		mat = "wall",
		roof = "gable",
		stairs = true,
		door = { side = "S", width = 5, height = 8.5 },
	}
	for k, v in more or {} do
		b[k] = v
	end
	return b
end

local function compile(build: { any }): ({ any }, string, any, { any })
	local _, parts, issues, extras = World.compile({ name = "T", palette = PALETTE, build = build })
	local errs = {}
	for _, i in issues do
		if i.severity == "error" then
			table.insert(errs, `{i.path}: {i.message}`)
		end
	end
	return parts, table.concat(errs, " | "), extras, issues
end

return function()
	test.suite("World rooms: a floor cut into rooms", function()
		test.case(
			"the rooms tile the floor beside the hall exactly: no gap, no overlap, none narrower than the least",
			function()
				local cutFloors = 0
				eachPlan(function(plan, w, d, hall)
					local area = 0
					for i, r in plan.rooms do
						check.truthy(r.x0 >= hall - 1e-6 and r.x1 <= w + 1e-6 and r.z0 >= -1e-6 and r.z1 <= d + 1e-6)
						check.truthy(r.x1 > r.x0 and r.z1 > r.z0)
						area += (r.x1 - r.x0) * (r.z1 - r.z0)
						for j = i + 1, #plan.rooms do
							local o = plan.rooms[j]
							local overlapX = math.min(r.x1, o.x1) - math.max(r.x0, o.x0)
							local overlapZ = math.min(r.z1, o.z1) - math.max(r.z0, o.z0)
							check.falsy(overlapX > 1e-6 and overlapZ > 1e-6)
						end
						if #plan.rooms > 1 then
							check.truthy(
								r.x1 - r.x0 >= Rooms.DEFAULTS.least - 1e-6 or r.z1 - r.z0 >= Rooms.DEFAULTS.least - 1e-6
							)
							-- (the side a cut was made across is never under the least)
							check.truthy(
								math.min(r.x1 - r.x0, r.z1 - r.z0) >= math.min(Rooms.DEFAULTS.least, w - hall, d) - 1e-6
							)
						end
					end
					check.truthy(near(area, math.max(w - hall, 0) * d))
					check.equal(#plan.rooms, #plan.walls + 1) -- (each cut makes one room more and one wall: a tree)
					check.truthy(#plan.rooms <= 4)
					cutFloors += if #plan.walls > 0 then 1 else 0
				end)
				check.truthy(cutFloors > 150) -- (the floors big enough ARE cut: the properties above are not empty)
			end
		)

		test.case("every room is reached from every other, through the doors and the hall", function()
			eachPlan(function(plan)
				check.truthy(Rooms.connected(plan))
			end)
			-- ... and the walk is no constant: a plan whose only door is moved off its wall is not connected
			local plan = Rooms.plan(40, 24, { seed = 3 })
			check.truthy(#plan.walls >= 1)
			local sealed = { rooms = plan.rooms, hall = 0, walls = {} }
			for _, wall in plan.walls do
				table.insert(sealed.walls, {
					axis = wall.axis,
					at = wall.at + 1000,
					from = wall.from,
					to = wall.to,
					door = wall.door,
					doorWidth = wall.doorWidth,
				})
			end
			check.falsy(Rooms.connected(sealed))
		end)

		test.case(
			"a doorway stands inside its wall with a stud of wall each side, and no partition ends in one",
			function()
				eachPlan(function(plan, _, _, hall)
					for _, wall in plan.walls do
						check.truthy(wall.door - wall.doorWidth / 2 >= wall.from + 1 - 1e-6)
						check.truthy(wall.door + wall.doorWidth / 2 <= wall.to - 1 + 1e-6)
						check.truthy(wall.doorWidth >= 4.5)
						-- no partition crosses the stair hall
						if wall.axis == "x" then
							check.truthy(wall.from >= hall - 1e-6)
						else
							check.truthy(wall.at >= hall - 1e-6)
						end
						for _, other in plan.walls do
							if other ~= wall and other.axis ~= wall.axis then
								-- `other` ends on `wall` when one of its ends is at wall.at
								local ends = math.abs(other.from - wall.at) < 1e-6
									or math.abs(other.to - wall.at) < 1e-6
								if ends and other.at > wall.from and other.at < wall.to then
									check.truthy(math.abs(other.at - wall.door) >= wall.doorWidth / 2 + 1 - 1e-6)
								end
							end
						end
					end
				end)
			end
		)

		test.case(
			"the same floor and seed give the same rooms; another seed another plan; a small floor stays whole",
			function()
				local a, b = Rooms.plan(29, 33, { seed = 5, hall = 6 }), Rooms.plan(29, 33, { seed = 5, hall = 6 })
				check.equal(#a.walls, #b.walls)
				for i, wall in a.walls do
					check.equal(wall.at, b.walls[i].at)
					check.equal(wall.door, b.walls[i].door)
				end
				local places = {}
				local count = 0
				for seed = 1, 12 do
					local p = Rooms.plan(29, 33, { seed = seed })
					local key = `{p.walls[1].axis}{p.walls[1].at}`
					if not places[key] then
						places[key] = true
						count += 1
					end
				end
				check.truthy(count >= 4)
				check.equal(#Rooms.plan(9, 9, { seed = 1 }).rooms, 1)
				check.equal(#Rooms.plan(17, 8, { seed = 1 }).rooms, 1) -- (under twice the least: no cut)
				check.equal(#Rooms.plan(40, 30, { seed = 1, depth = 0 }).rooms, 1)
				check.equal(#Rooms.plan(40, 30, { seed = 1, depth = 1 }).rooms, 2)
			end
		)
	end)

	test.suite("World rooms: in a building", function()
		test.case(
			"without the word a house is the house it was; with it, partitions with doorways stand inside",
			function()
				local plain, e0 = compile({ { building = house() } })
				local same, e1 = compile({ { building = house({ rooms = false }) } })
				check.equal(e0, "")
				check.equal(e1, "")
				check.equal(#same, #plain)
				local roomed, e2, extras = compile({ { building = house({ rooms = true }) } })
				check.equal(e2, "")
				check.truthy(#roomed > #plain + 4)
				-- every new part stands inside the house's outer walls and under its top
				local seen = {}
				for _, p in plain do
					seen[`{p.name}:{p.pos[1]}:{p.pos[2]}:{p.pos[3]}`] = true
				end
				local added = 0
				for _, p in roomed do
					if not seen[`{p.name}:{p.pos[1]}:{p.pos[2]}:{p.pos[3]}`] then
						added += 1
						check.truthy(math.abs(p.pos[1]) < 15 and math.abs(p.pos[3]) < 17)
						check.truthy(p.pos[2] > 0 and p.pos[2] < 28)
						check.truthy(p.name == "Wall" or p.name == "Lintel")
					end
				end
				check.truthy(added >= 4)
				-- each room door claims its size (the r6 sheet holds it)
				local doors = 0
				for _, f in extras.fits do
					if f.kind == "opening" and string.find(f.name, "room door", 1, true) then
						doors += 1
						check.truthy(f.size[1] >= 4.5 and f.size[2] >= 7.5)
					end
				end
				check.truthy(doors >= 2)
			end
		)

		test.case("the stair flight is not walled off: no partition stands in the hall the flight runs in", function()
			local roomed = compile({ { building = house({ rooms = true }) } })
			local plain = compile({ { building = house() } })
			local stairs = {}
			for _, p in plain do
				if p.name == "Stair" then
					table.insert(stairs, p)
				end
			end
			check.truthy(#stairs > 10)
			local seen = {}
			for _, p in plain do
				seen[`{p.name}:{p.pos[1]}:{p.pos[2]}:{p.pos[3]}`] = true
			end
			for _, p in roomed do
				if not seen[`{p.name}:{p.pos[1]}:{p.pos[2]}:{p.pos[3]}`] then
					-- a partition's box (axis-aligned or a quarter turned) against every stair's box in x and z
					local hx = (math.abs(p.rot[1][1]) * p.size[1] + math.abs(p.rot[1][3]) * p.size[3]) / 2
					local hz = (math.abs(p.rot[3][1]) * p.size[1] + math.abs(p.rot[3][3]) * p.size[3]) / 2
					for _, st in stairs do
						local apartX = math.abs(p.pos[1] - st.pos[1]) - hx - st.size[1] / 2
						local apartZ = math.abs(p.pos[3] - st.pos[3]) - hz - st.size[3] / 2
						check.truthy(apartX > 0.5 or apartZ > -1e-6)
					end
				end
			end
		end)

		test.case(
			"cases a fresh reader broke: the front door, a doorway really cut, a thick wall's stair hall, words",
			function()
				-- the parts "rooms" adds to a house (everything the plain house does not have)
				local function added(spec: any): ({ any }, any)
					local plain = compile({ { building = house(spec) } })
					local seen = {}
					for _, p in plain do
						seen[`{p.name}:{p.pos[1]}:{p.pos[2]}:{p.pos[3]}:{p.size[1]}`] = true
					end
					local more: any = table.clone(spec)
					more.rooms = true
					local roomed, errs, extras = compile({ { building = house(more) } })
					check.equal(errs, "")
					local out = {}
					for _, p in roomed do
						if not seen[`{p.name}:{p.pos[1]}:{p.pos[2]}:{p.pos[3]}:{p.size[1]}`] then
							table.insert(out, p)
						end
					end
					return out, extras
				end
				-- a part's reach along x and z (partitions run on an axis)
				local function box(p: any): (number, number, number, number)
					local hx = (math.abs(p.rot[1][1]) * p.size[1] + math.abs(p.rot[1][3]) * p.size[3]) / 2
					local hz = (math.abs(p.rot[3][1]) * p.size[1] + math.abs(p.rot[3][3]) * p.size[3]) / 2
					return p.pos[1] - hx, p.pos[1] + hx, p.pos[3] - hz, p.pos[3] + hz
				end

				-- 1. NO partition stands in the front door (1,842 of 6,724 houses had one): a body's way in, 5 wide and
				--    3 deep behind the door, on every side and many sizes
				local houses = 0
				for _, side in { "N", "E", "S", "W" } do
					for w = 20, 44, 4 do
						for d = 20, 44, 6 do
							local parts = added({
								size = { w, d },
								floors = 1,
								stairs = false,
								roof = "flat",
								door = { side = side, width = 5, height = 8.5 },
							})
							-- the door's bay: the middle bay of its wall, counted from the wall's start corner
							local len = if side == "N" or side == "S" then w else d
							local n = math.floor((len - 4) / 10)
							local at = -len / 2 + (math.ceil(n / 2) - 0.5) * len / n
							if side == "S" or side == "W" then
								at = -at
							end
							local dx0, dx1, dz0, dz1
							if side == "N" then
								dx0, dx1, dz0, dz1 = at - 2.5, at + 2.5, -d / 2, -d / 2 + 3.5
							elseif side == "S" then
								dx0, dx1, dz0, dz1 = at - 2.5, at + 2.5, d / 2 - 3.5, d / 2
							elseif side == "W" then
								dx0, dx1, dz0, dz1 = -w / 2, -w / 2 + 3.5, at - 2.5, at + 2.5
							else
								dx0, dx1, dz0, dz1 = w / 2 - 3.5, w / 2, at - 2.5, at + 2.5
							end
							for _, p in parts do
								local x0, x1, z0, z1 = box(p)
								if
									x0 < dx1 - 0.01
									and x1 > dx0 + 0.01
									and z0 < dz1 - 0.01
									and z1 > dz0 + 0.01
									and p.pos[2] < 8
								then
									error(`a partition stands in the {side} door of a {w} x {d} house`, 0)
								end
							end
							houses += 1
						end
					end
				end
				check.truthy(houses >= 100)

				-- 2. a doorway is really CUT: over each claimed room door a lintel hangs from 8.5 up, and nothing of the
				--    partition stands in the 5 x 8.5 opening under it (a copy with no gap at all passed every case before)
				local parts, extras = added({ size = { 40, 30 }, floors = 2, stairs = true })
				local doors = 0
				for _, f in extras.fits do
					if f.kind == "opening" and string.find(f.name, "room door", 1, true) then
						doors += 1
						local lintel = false
						for _, p in parts do
							local x0, x1, z0, z1 = box(p)
							local over = f.pos[1] > x0 - 0.01
								and f.pos[1] < x1 + 0.01
								and f.pos[3] > z0 - 0.01
								and f.pos[3] < z1 + 0.01
							if over then
								local bottom = p.pos[2] - p.size[2] / 2
								if bottom < f.pos[2] + 8.5 - 0.01 then
									error(`{f.name}: the partition stands in its own doorway`, 0)
								end
								lintel = lintel or p.name == "Lintel"
							end
						end
						check.truthy(lintel)
					end
				end
				check.truthy(doors >= 3)
				-- ... on the upper floor too: partitions stand above the first storey
				local upstairs = 0
				for _, p in parts do
					upstairs += if p.pos[2] > 14 then 1 else 0
				end
				check.truthy(upstairs >= 2)

				-- 3. the stair hall is the flight and a body's width beside it, whatever the wall's thickness (it was a
				--    fixed 6 studs: with a 4-stud wall the first partition touched the steps)
				for _, thick in { 1, 2, 3, 4 } do
					local roomed =
						compile({ { building = house({ size = { 44, 40 }, thickness = thick, rooms = true }) } })
					local flightEast = -22 + thick + 4 -- (the flight's east edge: the wall's inner face + its 4 studs)
					for _, p in roomed do
						if (p.name == "Wall" or p.name == "Lintel") and p.size[3] < 0.7 then -- a partition (0.6 thick)
							local x0 = box(p)
							check.truthy(x0 >= flightEast + 1.7 - 0.01)
						end
					end
				end

				-- 4. under a flat roof the top floor's partitions reach the roof (they stopped a stud short)
				local flat = added({ size = { 40, 30 }, floors = 2, stairs = false, roof = "flat" })
				local top = 0
				for _, p in flat do
					top = math.max(top, p.pos[2] + p.size[2] / 2)
				end
				check.truthy(math.abs(top - 28) < 1e-6)

				-- 5. a word that is not true, false or a table of options is an error, never rooms turned on; a doorway
				--    under the rig's 4.5 is refused, not quietly made 5
				for _, word in { "no", 0, "false", "yes" } :: { any } do
					local built, errs = compile({ { building = house({ rooms = word }) } })
					check.truthy(string.find(errs, '"rooms" is true, false or', 1, true))
					check.equal(#built, #compile({ { building = house() } }))
				end
				local _, small = compile({ { building = house({ rooms = { door = 4 } }) } })
				check.truthy(string.find(small, "at least 4.5 studs wide", 1, true))
				-- 6. at most four rooms a floor, whatever depth is asked
				check.truthy(#Rooms.plan(60, 60, { depth = 3, seed = 1 }).rooms <= 4)
				check.truthy(#Rooms.plan(60, 60, { depth = 9, seed = 2 }).rooms <= 4)
			end
		)

		test.case("furniture set out for one room a floor is left out of a house with rooms, and said", function()
			local _, errs, _, issues = compile({ { building = house({ rooms = true, interior = true }) } })
			check.equal(errs, "")
			local said = 0
			for _, i in issues do
				if i.severity == "warn" and string.find(i.message, "furniture by room is not built yet", 1, true) then
					said += 1
				end
			end
			check.equal(said, 1)
		end)
	end)
end

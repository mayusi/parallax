-- worlddungeon.spec.luau (kit) — ROOMS AND CORRIDORS BY RULE (kit/lib/worlddungeon.luau; the owner's method list:
-- "Procedural dungeon generation", "Room-and-corridor generation"). The plan is held to what a dungeon must be:
-- its rooms apart and inside the area, all of them reached from the first by walking the floor's cells, the floor
-- covered once, a wall on every edge - and then the parts the compiler makes of it are FLOODED: a body let loose
-- in the first room at chest height never gets out of the walls, and gets into every room.
-- Not claimed here: that a dungeon looks right, or plays well. That is a built world, looked at and walked.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Dungeon = require("../../lib/worlddungeon")
local LaneLocks = require("../../lib/lanelocks")
local World = require("../../lib/world")

local PALETTE = {
	stone = { material = "Slate", color = { 90, 90, 90 } },
	flag = { material = "Cobblestone", color = { 110, 108, 100 } },
}

local function spec(more: any?): any
	local s: any = {
		name = "Crypt",
		center = { 0, 0, 0 },
		area = { 240, 200 },
		rooms = 9,
		seed = 4,
		mat = "stone",
		floor = "flag",
	}
	for k, v in more or {} do
		s[k] = v
	end
	return s
end

local function compile(s: any): (any, { any }, { string }, { string }, any)
	local model, parts, issues, extras =
		World.compile({ name = "T", scale = "r6", palette = PALETTE, build = { { dungeon = s } } })
	local errors, warns = {}, {}
	for _, i in issues do
		table.insert(if i.severity == "error" then errors else warns, i.message)
	end
	return model, parts, errors, warns, extras
end

-- the compiled walls on a half-stud grid (the thinnest wall is half a stud), and a flood through what is not wall
-- from a place: does it get out of the grid's edge, and which of the places asked about does it reach
local STEP = 0.5
local function flood(parts: { any }, from: { number }, ask: { { number } }): (boolean, number)
	local lo, hi = -220, 220
	local n = math.floor((hi - lo) / STEP)
	local wall: { [number]: boolean } = {}
	local function cellOf(v: number): number
		return math.floor((v - lo) / STEP)
	end
	for _, p in parts do
		if p.name == "Wall" then
			local x0, x1 = p.pos[1] - p.size[1] / 2, p.pos[1] + p.size[1] / 2
			local z0, z1 = p.pos[3] - p.size[3] / 2, p.pos[3] + p.size[3] / 2
			for x = cellOf(x0), cellOf(x1) do
				for z = cellOf(z0), cellOf(z1) do
					-- (the cell's middle is inside the wall)
					local mx, mz = lo + (x + 0.5) * STEP, lo + (z + 0.5) * STEP
					if mx > x0 and mx < x1 and mz > z0 and mz < z1 then
						wall[z * n + x] = true
					end
				end
			end
		end
	end
	local seen: { [number]: boolean } = {}
	local sx, sz = cellOf(from[1]), cellOf(from[2])
	local stack = { { sx, sz } }
	seen[sz * n + sx] = true
	local out = false
	while #stack > 0 do
		local at = table.remove(stack) :: { number }
		-- (the eight neighbours: a corner left open between two walls is a way out, as it is a hole to the eye)
		for _, d in { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 }, { 1, 1 }, { 1, -1 }, { -1, 1 }, { -1, -1 } } do
			local x, z = at[1] + d[1], at[2] + d[2]
			if x < 0 or x >= n or z < 0 or z >= n then
				out = true
			elseif not wall[z * n + x] and not seen[z * n + x] then
				seen[z * n + x] = true
				table.insert(stack, { x, z })
			end
		end
	end
	local reached = 0
	for _, a in ask do
		if seen[cellOf(a[2]) * n + cellOf(a[1])] then
			reached += 1
		end
	end
	return out, reached
end

return function()
	test.suite("Rooms and corridors by rule", function()
		test.case("what is wrong with a dungeon is said", function()
			local function wrong(more: any, text: string)
				local problems = Dungeon.problems(spec(more))
				check.truthy(#problems >= 1)
				check.truthy(string.find(table.concat(problems, " | "), text, 1, true), table.concat(problems, " | "))
			end
			check.equal(#Dungeon.problems(spec()), 0)
			check.equal(
				#Dungeon.problems(
					spec({ roof = "stone", start = true, loops = 0, corridor = 12, height = 14, thickness = 2 })
				),
				0
			)
			wrong({ area = { 40, 200 } }, "dungeon.area")
			wrong({ area = "big" }, "dungeon.area")
			wrong({ center = { 0, 0 } }, "dungeon.center")
			wrong({ rooms = 1 }, "dungeon.rooms")
			wrong({ rooms = 2.5 }, "dungeon.rooms")
			wrong({ rooms = 61 }, "dungeon.rooms")
			wrong({ room = { { 8, 16 }, { 20, 20 } } }, "12 studs or more")
			wrong({ room = { { 20, 20 }, { 16, 30 } } }, "no less than its least")
			wrong({ room = { 16, 16 } }, "dungeon.room is")
			wrong({ corridor = 4 }, "dungeon.corridor") -- (a doorway on the rig's sheet is wider than 4)
			wrong({ corridor = 10 }, "dungeon.corridor")
			wrong({ loops = 2 }, "dungeon.loops")
			wrong({ height = 5 }, "dungeon.height")
			wrong({ height = 11 }, "dungeon.height is 12 to 60") -- (a body jumps 7.2 studs: lower walls are climbed)
			wrong({ height = 61 }, "dungeon.height")
			check.equal(#Dungeon.problems(spec({ height = 12 })), 0)
			check.equal(#Dungeon.problems(spec({ height = 60 })), 0)
			wrong({ thickness = 0.4 }, "dungeon.thickness")
			wrong({ roof = true }, "dungeon.roof is a palette entry's name")
			wrong({ mat = 5 }, "dungeon.mat is a palette entry's name")
			wrong({ floor = false }, "dungeon.floor is a palette entry's name")
			wrong({ start = "yes" }, "dungeon.start is true or false")
			-- a size the 4-stud grid cannot give between least and most
			wrong({ room = { { 13, 13 }, { 13, 13 } } }, "no multiple of 4 studs lies between 13 and 13")
			wrong({ room = { { 12, 17 }, { 16, 19 } } }, "between 17 and 19")
			check.equal(#Dungeon.problems(spec({ room = { { 13, 13 }, { 16, 16 } } })), 0)
			wrong({ thickness = 3 }, "dungeon.thickness") -- (two walls back to back in one 4-stud cell)
			wrong({ seed = 1.5 }, "dungeon.seed")
			wrong({ romos = 4 }, "dungeon.romos")
			check.truthy(#Dungeon.problems(5) == 1)
		end)

		test.case("the plan: rooms apart and inside the area, the same for the same seed", function()
			for seed = 1, 30 do
				local plan = Dungeon.plan(spec({ seed = seed, rooms = 10 }))
				check.truthy(#plan.rooms >= 6)
				for a, r in plan.rooms do
					-- a cell clear of the area's edge, 3 cells or more each way
					check.truthy(r[1] >= 2 and r[2] >= 2 and r[3] <= plan.nx - 1 and r[4] <= plan.nz - 1)
					check.truthy(r[3] - r[1] + 1 >= 3 and r[4] - r[2] + 1 >= 3)
					for b = a + 1, #plan.rooms do
						local q = plan.rooms[b]
						local gapI = math.max(q[1] - r[3], r[1] - q[3]) - 1
						local gapJ = math.max(q[2] - r[4], r[2] - q[4]) - 1
						check.truthy(math.max(gapI, gapJ) >= 2) -- (two cells: 8 studs of ground between two rooms)
					end
				end
			end
			-- a room is never under its least nor over its most (in studs, on the 4-stud grid)
			for seed = 1, 40 do
				for _, size in
					{
						{ { 12, 12 }, { 14, 14 } },
						{ { 14, 22 }, { 18, 30 } },
						{ { 20, 12 }, { 20, 12 } },
						{ { 13, 13 }, { 16, 16 } },
						{ { 12, 12 }, { 15, 15 } },
					}
				do
					local plan = Dungeon.plan(spec({ seed = seed, room = size }))
					check.truthy(#plan.rooms >= 2)
					for _, r in plan.rooms do
						local w, d = (r[3] - r[1] + 1) * 4, (r[4] - r[2] + 1) * 4
						check.truthy(w >= size[1][1] and w <= size[2][1], `{w} wide of {size[1][1]}..{size[2][1]}`)
						check.truthy(d >= size[1][2] and d <= size[2][2], `{d} deep of {size[1][2]}..{size[2][2]}`)
					end
				end
			end
			local a, b = Dungeon.plan(spec()), Dungeon.plan(spec())
			check.equal(#a.rooms, #b.rooms)
			check.equal(a.rooms[3][1], b.rooms[3][1])
			check.equal(#a.links, #b.links)
			local c = Dungeon.plan(spec({ seed = 5 }))
			check.truthy(c.rooms[1][1] ~= a.rooms[1][1] or c.rooms[1][2] ~= a.rooms[1][2])
		end)

		test.case("every room is reached from the first by walking the floor's cells; no floor is cut off", function()
			for seed = 1, 60 do
				for _, loops in { 0, 0.15, 1 } do
					local plan = Dungeon.plan(spec({ seed = seed, rooms = 12, loops = loops, area = { 320, 240 } }))
					local reached, cut = Dungeon.reach(plan)
					check.equal(reached, #plan.rooms)
					check.equal(cut, 0)
					-- the links: a tree first (one fewer than the rooms), then the loops
					check.truthy(#plan.links >= #plan.rooms - 1)
					check.equal(plan.loops, #plan.links - (#plan.rooms - 1))
					if loops == 0 then
						check.equal(plan.loops, 0)
					end
					-- every room is in a link, none linked to itself, no link twice
					local inLink: { [number]: boolean } = {}
					local twice: { [string]: boolean } = {}
					for _, l in plan.links do
						check.truthy(l[1] ~= l[2])
						local k = `{math.min(l[1], l[2])}-{math.max(l[1], l[2])}`
						check.equal(twice[k], nil)
						twice[k] = true
						inLink[l[1]], inLink[l[2]] = true, true
					end
					for r = 1, #plan.rooms do
						check.truthy(inLink[r])
					end
				end
			end
			-- the walk is its own judge: a plan whose second room no corridor reaches is told apart
			local broken = Dungeon.plan(spec({ rooms = 2, seed = 3, loops = 0 }))
			check.equal(#broken.rooms, 2)
			local cells = 0
			for i = 1, broken.nx do
				for j = 1, broken.nz do
					if broken.kind[i][j] == 2 then
						broken.kind[i][j] = 0 -- (the corridor taken out)
					end
				end
			end
			local second = broken.rooms[2]
			cells = (second[3] - second[1] + 1) * (second[4] - second[2] + 1)
			local reachedBroken, cutBroken = Dungeon.reach(broken)
			check.equal(reachedBroken, 1)
			check.equal(cutBroken, cells)
			-- a corridor is as wide as it says everywhere: every corridor cell lies in a square of floor that wide
			for _, cw in { 2, 3 } do
				local plan = Dungeon.plan(spec({ seed = 9, rooms = 10, corridor = cw * 4 }))
				local function floor(i: number, j: number): boolean
					return i >= 1 and i <= plan.nx and j >= 1 and j <= plan.nz and plan.kind[i][j] ~= 0
				end
				local corridors = 0
				for i = 1, plan.nx do
					for j = 1, plan.nz do
						if plan.kind[i][j] == 2 then
							corridors += 1
							local wide = false
							for oi = i - cw + 1, i do
								for oj = j - cw + 1, j do
									local all = true
									for a = oi, oi + cw - 1 do
										for b = oj, oj + cw - 1 do
											all = all and floor(a, b)
										end
									end
									wide = wide or all
								end
							end
							check.truthy(wide)
						end
					end
				end
				check.truthy(corridors > 50)
			end
			-- more loops asked, more links made (over many seeds)
			local few, many = 0, 0
			for seed = 1, 30 do
				few += Dungeon.plan(spec({ seed = seed, rooms = 12, loops = 0.1, area = { 320, 240 } })).loops
				many += Dungeon.plan(spec({ seed = seed, rooms = 12, loops = 0.9, area = { 320, 240 } })).loops
			end
			check.truthy(many > few * 3)
		end)

		test.case("the floor is covered once, and a wall stands on every edge of it, once", function()
			for seed = 1, 25 do
				local plan = Dungeon.plan(spec({ seed = seed, rooms = 10 }))
				-- the floor's rectangles: every floor cell in exactly one
				local covered: { [number]: number } = {}
				for _, r in Dungeon.floors(plan) do
					for i = r[1], r[3] do
						for j = r[2], r[4] do
							covered[j * 1000 + i] = (covered[j * 1000 + i] or 0) + 1
						end
					end
				end
				-- the walls: every edge between floor and not-floor in exactly one run
				local edges: { [string]: number } = {}
				for _, w in Dungeon.walls(plan) do
					if w.side == "N" or w.side == "S" then
						for i = w.i0, w.i1 do
							edges[`{w.side}{i},{w.j}`] = (edges[`{w.side}{i},{w.j}`] or 0) + 1
						end
					else
						for j = w.j0, w.j1 do
							edges[`{w.side}{w.i},{j}`] = (edges[`{w.side}{w.i},{j}`] or 0) + 1
						end
					end
				end
				local function floor(i: number, j: number): boolean
					return i >= 1 and i <= plan.nx and j >= 1 and j <= plan.nz and plan.kind[i][j] ~= 0
				end
				local wanted = 0
				for i = 1, plan.nx do
					for j = 1, plan.nz do
						check.equal(covered[j * 1000 + i] or 0, if floor(i, j) then 1 else 0)
						if floor(i, j) then
							for side, d in { N = { 0, -1 }, S = { 0, 1 }, W = { -1, 0 }, E = { 1, 0 } } do
								if not floor(i + d[1], j + d[2]) then
									wanted += 1
									check.equal(edges[`{side}{i},{j}`], 1)
								end
							end
						end
					end
				end
				local made = 0
				for _, n in edges do
					made += n
				end
				check.equal(made, wanted) -- (and no wall where there is no edge)
			end
		end)

		test.case("built: a body let loose in the first room never gets out, and gets into every room", function()
			for _, more in
				{
					{ seed = 4 },
					{ seed = 11, rooms = 14, area = { 320, 280 }, loops = 0.6 },
					{ seed = 23, corridor = 12, thickness = 2 },
					{ seed = 7, rooms = 5, room = { { 12, 12 }, { 16, 16 } }, area = { 120, 120 } },
					{ seed = 31, center = { 40, 10, -30 }, thickness = 0.5 },
				} :: { any }
			do
				local s = spec(more)
				local _, parts, errors, warns, extras = compile(s)
				check.equal(#errors, 0)
				for _, w in warns do
					check.equal(string.find(w, "z-fighting", 1, true), nil) -- (no two walls in one place)
					check.equal(string.find(w, "coplanar", 1, true), nil)
				end
				local rooms = extras.dungeons[1].rooms
				local ask = {}
				for _, r in rooms do
					table.insert(ask, { r.center[1], r.center[3] })
				end
				local out, reached = flood(parts, ask[1], ask)
				check.equal(out, false)
				check.equal(reached, #rooms)
				-- a place outside the dungeon is NOT reached from inside (the flood is not let through the walls)
				local _, outside = flood(parts, ask[1], { { s.center[1] - s.area[1] / 2 - 20, s.center[3] } })
				check.equal(outside, 0)
				-- no wall stands on the floor: every wall's box is clear of every floor slab's inside
				for _, w in parts do
					if w.name == "Wall" then
						for _, f in parts do
							if f.name == "DungeonFloor" then
								local overX = math.min(w.pos[1] + w.size[1] / 2, f.pos[1] + f.size[1] / 2)
									- math.max(w.pos[1] - w.size[1] / 2, f.pos[1] - f.size[1] / 2)
								local overZ = math.min(w.pos[3] + w.size[3] / 2, f.pos[3] + f.size[3] / 2)
									- math.max(w.pos[3] - w.size[3] / 2, f.pos[3] - f.size[3] / 2)
								check.truthy(overX <= 1e-6 or overZ <= 1e-6)
							end
						end
					end
				end
			end
		end)

		test.case("the compiler: floor, walls, a roof and a start; all of it in the model the game loads", function()
			local model, parts, errors, _, extras = compile(spec({ roof = "stone", start = true, height = 14 }))
			check.equal(#errors, 0)
			local count: { [string]: number } = {}
			local spawn
			for _, p in parts do
				count[p.name] = (count[p.name] or 0) + 1
				if p.name == "Spawn" then
					spawn = p
				end
			end
			check.truthy(count.DungeonFloor >= 9 and count.Wall >= 36)
			check.equal(count.Roof, count.DungeonFloor) -- (a slab over every piece of floor)
			check.equal(count.Spawn, 1)
			local first = extras.dungeons[1].rooms[1]
			check.equal(spawn.pos[1], first.center[1])
			check.equal(spawn.pos[3], first.center[3])
			check.equal(spawn.pos[2], 0.5) -- (a 1-stud pad lying on the floor's top)
			check.equal(spawn.size[2], 1)
			check.truthy(spawn.spawn == true)
			-- floor top at the centre's height, walls 14 high standing on it, the roof over them
			for _, p in parts do
				if p.name == "DungeonFloor" then
					check.equal(p.pos[2] + p.size[2] / 2, 0)
				elseif p.name == "Wall" then
					check.equal(p.pos[2] - p.size[2] / 2, 0)
					check.equal(p.size[2], 14)
				elseif p.name == "Roof" then
					check.equal(p.pos[2] - p.size[2] / 2, 14)
				end
			end
			local held = 0
			for _, c in model.Children do
				if c.Name == "Crypt" then
					held = #c.Children
				end
			end
			check.equal(held, #parts)
			-- its measures are handed back
			local m = extras.dungeons[1].measure
			check.equal(m.rooms, #extras.dungeons[1].rooms)
			check.equal(m.links, #extras.dungeons[1].links)
			check.truthy(m.floor > 4000)
			-- a roofed room claims its ceiling for the rig's sheet: one a room, as wide and deep as the room, 14 high
			local ceilings = 0
			for _, f in extras.fits do
				if f.kind == "ceiling" then
					ceilings += 1
					local r = extras.dungeons[1].rooms[ceilings]
					check.equal(f.size[1], r.size[1])
					check.equal(f.size[2], 14)
					check.equal(f.size[3], r.size[2])
					check.equal(f.pos[2], 7)
				end
				check.truthy(f.kind ~= "opening") -- (no doorway is claimed: a corridor's mouth has no lintel)
			end
			check.equal(ceilings, m.rooms)
			local _, _, _, _, open = compile(spec())
			for _, f in open.fits do
				check.truthy(f.kind ~= "ceiling") -- (no roof, no ceiling claimed)
			end
			-- no roof, no start: neither part
			local _, bare = compile(spec())
			for _, p in bare do
				check.truthy(p.name ~= "Roof" and p.name ~= "Spawn")
			end
		end)

		test.case("dead ends are counted on the built floor, not on the links it was laid by", function()
			-- an independent count: the floor outside a room, joined into pieces by touching sides (a flood over the
			-- cells that border the room); each piece is one way out
			local function waysOut(plan: any, r: { number }): number
				local function floor(i: number, j: number): boolean
					return i >= 1 and i <= plan.nx and j >= 1 and j <= plan.nz and plan.kind[i][j] ~= 0
				end
				local border: { [number]: boolean } = {}
				for i = r[1], r[3] do
					border[(r[2] - 1) * 1000 + i] = floor(i, r[2] - 1) or nil
					border[(r[4] + 1) * 1000 + i] = floor(i, r[4] + 1) or nil
				end
				for j = r[2], r[4] do
					border[j * 1000 + r[1] - 1] = floor(r[1] - 1, j) or nil
					border[j * 1000 + r[3] + 1] = floor(r[3] + 1, j) or nil
				end
				local pieces = 0
				local seen: { [number]: boolean } = {}
				for key in border do
					if not seen[key] then
						pieces += 1
						local stack = { key }
						seen[key] = true
						while #stack > 0 do
							local at = table.remove(stack) :: number
							for _, d in { 1, -1, 1000, -1000 } do
								if border[at + d] and not seen[at + d] then
									seen[at + d] = true
									table.insert(stack, at + d)
								end
							end
						end
					end
				end
				return pieces
			end
			local differs, plans = 0, 0
			for seed = 1, 60 do
				for _, loops in { 0, 0.5 } do
					local plan = Dungeon.plan(spec({ seed = seed, rooms = 12, loops = loops, area = { 320, 240 } }))
					local ways = Dungeon.doorways(plan)
					local m = Dungeon.measure(plan)
					local dead = 0
					local degree: { number } = table.create(#plan.rooms, 0)
					for _, l in plan.links do
						degree[l[1]] += 1
						degree[l[2]] += 1
					end
					local byLinks = 0
					for k, r in plan.rooms do
						check.equal(ways[k], waysOut(plan, r))
						check.truthy(ways[k] >= 1) -- (every room has a way out)
						check.equal(m.ways[k], ways[k])
						dead += if ways[k] == 1 then 1 else 0
						byLinks += if degree[k] == 1 then 1 else 0
					end
					check.equal(m.deadEnds, dead)
					plans += 1
					differs += if byLinks ~= dead then 1 else 0
				end
			end
			check.truthy(differs >= 1, `the links and the floor agreed in all {plans} plans: the test proves nothing`)
			-- by hand: a room with one mouth on its west side and one on its south
			local plan: any = { nx = 9, nz = 9, kind = {}, rooms = { { 4, 4, 6, 6 } } }
			for i = 1, 9 do
				plan.kind[i] = table.create(9, 0)
			end
			for i = 4, 6 do
				for j = 4, 6 do
					plan.kind[i][j] = 1
				end
			end
			check.equal(Dungeon.doorways(plan)[1], 0)
			plan.kind[3][5], plan.kind[3][6] = 2, 2 -- (one mouth, two cells wide, on the west)
			check.equal(Dungeon.doorways(plan)[1], 1)
			plan.kind[4][7] = 2 -- (round the corner, on the south: a second way out)
			check.equal(Dungeon.doorways(plan)[1], 2)
			plan.kind[6][7] = 2 -- (the same side, one cell of wall between: a third)
			check.equal(Dungeon.doorways(plan)[1], 3)
			plan.kind[5][7] = 2 -- (the wall between opened: the two on the south are one)
			check.equal(Dungeon.doorways(plan)[1], 2)
		end)

		test.case("the compiler: what cannot be built is said", function()
			local function wrong(more: any, text: string)
				local _, parts, errors = compile(spec(more))
				check.equal(#parts, 0)
				check.truthy(#errors >= 1)
				check.truthy(string.find(table.concat(errors, " | "), text, 1, true), table.concat(errors, " | "))
			end
			wrong({ corridor = 4 }, "dungeon.corridor")
			wrong({ romos = 4 }, "dungeon.romos")
			wrong({ mat = false }, "dungeon.mat is a palette entry's name")
			wrong({ height = 7 }, "dungeon.height is 12 to 60")
			-- no material said at all
			local bare = spec()
			bare.mat = nil
			local _, none, said = compile(bare)
			check.equal(#none, 0)
			check.truthy(string.find(table.concat(said, " | "), 'needs "mat"', 1, true), table.concat(said, " | "))
			-- an area that holds one room of the size asked: said, not a dungeon of one
			wrong({ area = { 48, 48 }, room = { { 36, 36 }, { 40, 40 } } }, "a dungeon is two or more")
			-- fewer rooms than asked is built, and said
			local _, parts, errors, warns = compile(spec({ rooms = 40, area = { 160, 160 } }))
			check.equal(#errors, 0)
			check.truthy(#parts > 20)
			check.truthy(string.find(table.concat(warns, " | "), "dungeon placed", 1, true))
		end)

		test.case("the lock: six rooms typed one by one are a dungeon by rule, or say they are meant", function()
			local function bp(rooms: number, more: any?): any
				local build = {}
				for k = 1, rooms do
					table.insert(build, { room = { name = `Cell{k}` } })
				end
				local b: any = { build = build }
				for k, v in more or {} do
					b[k] = v
				end
				return b
			end
			check.equal(LaneLocks.typedRooms(bp(6)), 6)
			check.equal(LaneLocks.typedRooms(bp(9)), 9)
			check.equal(LaneLocks.typedRooms(bp(5)), 0)
			check.equal(LaneLocks.typedRooms(bp(9, { dungeon = false })), 0) -- (typed by hand, meant)
			local mixed = bp(9)
			table.insert(mixed.build, { dungeon = spec() })
			check.equal(LaneLocks.typedRooms(mixed), 9) -- (a dungeon step elsewhere excuses no typed room)
			check.equal(LaneLocks.typedRooms({}), 0)
			check.equal(LaneLocks.typedRooms(nil), 0)
			local named = 0
			for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_rooms_typed") do
				if string.find(line, "rooms typed one by one", 1, true) then
					named += 1
					check.truthy(string.find(line, "CellsByHand: 6 rooms", 1, true))
					check.truthy(string.find(line, '"dungeon": false', 1, true))
				end
			end
			check.equal(named, 1)
		end)
	end)
end

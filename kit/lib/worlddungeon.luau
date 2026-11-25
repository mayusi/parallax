--!strict
-- worlddungeon.luau (kit) — ROOMS AND CORRIDORS BY RULE (the owner's method list: "Procedural dungeon generation",
-- "Room-and-corridor generation"; and the room GRAPH that "Graph-based generation" lacked). A house's floor is cut
-- into rooms (worldrooms.luau); a place MADE of rooms - a crypt, a cellar maze, a keep's lower floor - was typed
-- room by room.
--   "dungeon": { "name", "center": [x, floorTop, z], "area": [w, d], "rooms": 9, "seed": 4,
--                "room": [[16, 16], [32, 28]],   least and most size of a room (studs)
--                "corridor": 8,                  a corridor's width (studs)
--                "loops": 0.15,                  the share of extra ways between rooms (0 = a tree: one way to each)
--                "height": 12 (or more), "thickness": 1, "mat", "floor", "roof"?, "start"?: true (a spawn in the
--                first room) }
-- HOW. The area is a grid of 4-stud cells. Rooms are set down at random, never nearer than 2 cells to each other.
-- They are joined into ONE tree by the shortest links there are (each room to its nearest joined room), then some
-- more links are added to make loops. A link is a corridor: out of one room's middle, along x then z (or z then
-- x), into the other's. Every cell that is a room or a corridor is FLOOR; a wall stands on every edge between
-- floor and not-floor. So there is no gap a body falls through, no wall across a way, and every room is reached
-- from every other BY CONSTRUCTION - which Dungeon.reach then checks on the cells, with no help from the links.
-- Pure and seeded: the same dungeon and seed give the same plan. kit/test/spec/worlddungeon.spec.luau
local Dungeon = {}

Dungeon.CELL = 4 -- studs: the grid everything stands on
Dungeon.APART = 2 -- cells between two rooms at least (room for their walls and a corridor's turn)
Dungeon.DEFAULTS = {
	rooms = 8,
	room = { { 16, 16 }, { 32, 28 } },
	corridor = 8,
	loops = 0.15,
	height = 12,
	thickness = 1,
}

local function lcg(seed: number): () -> number
	local state = (seed or 1) % 2147483647
	if state <= 0 then
		state += 2147483646
	end
	state = (state * 48271) % 2147483647
	state = (state * 48271) % 2147483647
	return function()
		state = (state * 48271) % 2147483647
		return state / 2147483647
	end
end

local function number(v: any): boolean
	return type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge
end

local KEYS = {
	name = true,
	center = true,
	area = true,
	rooms = true,
	seed = true,
	room = true,
	corridor = true,
	loops = true,
	height = true,
	thickness = true,
	mat = true,
	floor = true,
	roof = true,
	start = true,
	stream = true,
	landmark = true,
}

-- what is wrong with a dungeon step (nothing = it can be planned)
function Dungeon.problems(spec: any): { string }
	local out: { string } = {}
	if type(spec) ~= "table" then
		return { '"dungeon" is { "center", "area", "rooms", "mat", "floor", ... }' }
	end
	for k in spec do
		if not KEYS[k] then
			table.insert(out, `dungeon.{tostring(k)}: a dungeon does not know this word`)
		end
	end
	local c, a = spec.center, spec.area
	local function place(v: any): boolean
		return number(v) and math.abs(v) <= 1e6
	end
	if type(c) ~= "table" or not (place(c[1]) and place(c[2]) and place(c[3])) then
		table.insert(out, "dungeon.center is [x, floorTop, z], within a million studs of the middle")
	end
	if
		type(a) ~= "table"
		or not (number(a[1]) and number(a[2]))
		or a[1] < 48
		or a[2] < 48
		or a[1] > 2048
		or a[2] > 2048
	then
		table.insert(out, "dungeon.area is [w, d], each 48 to 2048 studs")
	end
	local n = spec.rooms
	if n ~= nil and (not number(n) or n % 1 ~= 0 or n < 2 or n > 60) then
		table.insert(out, `dungeon.rooms is a whole number, 2 to 60 (got {tostring(n)})`)
	end
	local r = spec.room
	if r ~= nil then
		local ok = type(r) == "table" and type(r[1]) == "table" and type(r[2]) == "table"
		if ok then
			for i = 1, 2 do
				for j = 1, 2 do
					ok = ok and number(r[i][j])
				end
			end
		end
		if not ok then
			table.insert(out, "dungeon.room is [[least w, least d], [most w, most d]] in studs")
		elseif r[1][1] < 12 or r[1][2] < 12 or r[2][1] < r[1][1] or r[2][2] < r[1][2] then
			table.insert(out, "dungeon.room: a room is 12 studs or more each way, and its most no less than its least")
		else
			-- (rooms stand on the 4-stud grid: between least and most there must be a size the grid has)
			for j = 1, 2 do
				if math.ceil(r[1][j] / Dungeon.CELL) > math.floor(r[2][j] / Dungeon.CELL) then
					table.insert(
						out,
						`dungeon.room: no multiple of {Dungeon.CELL} studs lies between {r[1][j]} and {r[2][j]} - a room stands on the {Dungeon.CELL}-stud grid`
					)
				end
			end
		end
	end
	local cw = spec.corridor
	if cw ~= nil and (not number(cw) or cw < 8 or cw > 16 or cw % Dungeon.CELL ~= 0) then
		table.insert(out, `dungeon.corridor is 8, 12 or 16 studs wide (got {tostring(cw)})`)
	end
	if spec.loops ~= nil and (not number(spec.loops) or spec.loops < 0 or spec.loops > 1) then
		table.insert(out, `dungeon.loops is 0 to 1 (got {tostring(spec.loops)})`)
	end
	-- (12: the rig's sheet wants a ceiling that high, and a wall a body cannot jump onto - it jumps 7.2 studs and
	-- a fresh reader's body climbed out over walls of 7)
	if spec.height ~= nil and (not number(spec.height) or spec.height < 12 or spec.height > 60) then
		table.insert(out, `dungeon.height is 12 to 60 studs (got {tostring(spec.height)})`)
	end
	for _, word in { "mat", "floor", "roof" } do
		if spec[word] ~= nil and type(spec[word]) ~= "string" then
			table.insert(out, `dungeon.{word} is a palette entry's name (got {tostring(spec[word])})`)
		end
	end
	if spec.start ~= nil and type(spec.start) ~= "boolean" then
		table.insert(out, `dungeon.start is true or false (got {tostring(spec.start)})`)
	end
	-- (two walls can stand back to back in one 4-stud cell between two floors: 2 studs each at most)
	if spec.thickness ~= nil and (not number(spec.thickness) or spec.thickness < 0.5 or spec.thickness > 2) then
		table.insert(out, `dungeon.thickness is 0.5 to 2 studs (got {tostring(spec.thickness)})`)
	end
	if spec.seed ~= nil and (not number(spec.seed) or spec.seed % 1 ~= 0) then
		table.insert(out, `dungeon.seed is a whole number (got {tostring(spec.seed)})`)
	end
	return out
end

-- THE PLAN (call with a spec that has no problems). In CELLS, the grid's low corner at (0, 0):
--   nx, nz, cell; kind[i][j] = 0 nothing | 1 room | 2 corridor (i along x from 1, j along z from 1);
--   rooms = { { i0, j0, i1, j1 } } (inclusive cells); links = { { a, b } } (room indices; the first #rooms - 1 are
--   the tree); asked (the rooms the spec asked for), loops (links over the tree)
function Dungeon.plan(spec: any): any
	local cell = Dungeon.CELL
	local d = Dungeon.DEFAULTS
	local rnd = lcg(spec.seed or 1)
	local nx, nz = math.floor(spec.area[1] / cell), math.floor(spec.area[2] / cell)
	local want = spec.rooms or d.rooms
	local size = spec.room or d.room
	local cw = (spec.corridor or d.corridor) / cell
	local kind: { { number } } = table.create(nx)
	for i = 1, nx do
		kind[i] = table.create(nz, 0)
	end
	-- the rooms: set down at random, a cell clear of the area's edge, APART cells clear of each other
	local rooms: { { number } } = {}
	local tries = 0
	while #rooms < want and tries < want * 80 do
		tries += 1
		-- (a whole number of cells, never under its least nor over its most)
		local w = math.clamp(
			math.floor((size[1][1] + (size[2][1] - size[1][1]) * rnd()) / cell + 0.5),
			math.ceil(size[1][1] / cell),
			math.floor(size[2][1] / cell)
		)
		local dd = math.clamp(
			math.floor((size[1][2] + (size[2][2] - size[1][2]) * rnd()) / cell + 0.5),
			math.ceil(size[1][2] / cell),
			math.floor(size[2][2] / cell)
		)
		if w > nx - 2 or dd > nz - 2 then
			continue
		end
		local i0 = 2 + math.floor(rnd() * (nx - w - 1))
		local j0 = 2 + math.floor(rnd() * (nz - dd - 1))
		local i1, j1 = i0 + w - 1, j0 + dd - 1
		local free = true
		for _, r in rooms do
			if
				i0 <= r[3] + Dungeon.APART
				and i1 >= r[1] - Dungeon.APART
				and j0 <= r[4] + Dungeon.APART
				and j1 >= r[2] - Dungeon.APART
			then
				free = false
				break
			end
		end
		if free then
			table.insert(rooms, { i0, j0, i1, j1 })
			for i = i0, i1 do
				for j = j0, j1 do
					kind[i][j] = 1
				end
			end
		end
	end
	local function middle(r: { number }): (number, number)
		return (r[1] + r[3]) / 2, (r[2] + r[4]) / 2
	end
	local function apart(a: number, b: number): number
		local ax, az = middle(rooms[a])
		local bx, bz = middle(rooms[b])
		return math.abs(ax - bx) + math.abs(az - bz)
	end
	-- ONE tree: each room joined to the nearest room already joined (the shortest links there are)
	local links: { { number } } = {}
	local joined: { [number]: boolean } = { [1] = true }
	for _ = 2, #rooms do
		local best, from, to = math.huge, 0, 0
		for a in joined do
			for b = 1, #rooms do
				if not joined[b] then
					local dist = apart(a, b)
					if dist < best or (dist == best and (a < from or (a == from and b < to))) then
						best, from, to = dist, a, b
					end
				end
			end
		end
		joined[to] = true
		table.insert(links, { from, to })
	end
	local tree = #links
	-- ... and some more ways, to make loops: a room's nearest neighbours it is not yet linked to, by chance
	local linked: { [string]: boolean } = {}
	for _, l in links do
		linked[`{math.min(l[1], l[2])}-{math.max(l[1], l[2])}`] = true
	end
	local share = spec.loops or d.loops
	for a = 1, #rooms do
		local near: { number } = {}
		for b = 1, #rooms do
			if b ~= a then
				table.insert(near, b)
			end
		end
		table.sort(near, function(p: number, q: number): boolean
			local dp, dq = apart(a, p), apart(a, q)
			return if dp == dq then p < q else dp < dq
		end)
		for k = 1, math.min(3, #near) do
			local b = near[k]
			local key = `{math.min(a, b)}-{math.max(a, b)}`
			if not linked[key] and rnd() < share then
				linked[key] = true
				table.insert(links, { a, b })
			end
		end
	end
	-- the corridors: out of one room's middle, along x then z or z then x, into the other's; cw cells wide
	local function lay(i: number, j: number)
		for di = 0, cw - 1 do
			for dj = 0, cw - 1 do
				local ci, cj = i + di, j + dj
				if ci >= 1 and ci <= nx and cj >= 1 and cj <= nz and kind[ci][cj] == 0 then
					kind[ci][cj] = 2
				end
			end
		end
	end
	for _, l in links do
		local ax, az = middle(rooms[l[1]])
		local bx, bz = middle(rooms[l[2]])
		-- (the corridor's low corner cell: its middle line runs through the rooms' middles)
		local ai, aj = math.floor(ax - (cw - 1) / 2 + 0.5), math.floor(az - (cw - 1) / 2 + 0.5)
		local bi, bj = math.floor(bx - (cw - 1) / 2 + 0.5), math.floor(bz - (cw - 1) / 2 + 0.5)
		local xFirst = rnd() < 0.5
		local i, j = ai, aj
		if xFirst then
			for s = math.min(ai, bi), math.max(ai, bi) do
				lay(s, aj)
			end
			i = bi
			for s = math.min(aj, bj), math.max(aj, bj) do
				lay(i, s)
			end
		else
			for s = math.min(aj, bj), math.max(aj, bj) do
				lay(ai, s)
			end
			j = bj
			for s = math.min(ai, bi), math.max(ai, bi) do
				lay(s, j)
			end
		end
	end
	return {
		nx = nx,
		nz = nz,
		cell = cell,
		kind = kind,
		rooms = rooms,
		links = links,
		asked = want,
		loops = #links - tree,
		corridor = cw,
	}
end

-- WALKED ON THE CELLS (no help from the links): from the first room's first cell, stepping to the four neighbours
-- that are floor -> how many rooms are reached, and how many floor cells are not
function Dungeon.reach(plan: any): (number, number)
	local seen: { [number]: boolean } = {}
	local function key(i: number, j: number): number
		return j * (plan.nx + 2) + i
	end
	local first = plan.rooms[1]
	if not first then
		return 0, 0
	end
	local stack = { { first[1], first[2] } }
	seen[key(first[1], first[2])] = true
	while #stack > 0 do
		local at = table.remove(stack) :: { number }
		for _, step in { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } } do
			local i, j = at[1] + step[1], at[2] + step[2]
			if i >= 1 and i <= plan.nx and j >= 1 and j <= plan.nz and plan.kind[i][j] ~= 0 and not seen[key(i, j)] then
				seen[key(i, j)] = true
				table.insert(stack, { i, j })
			end
		end
	end
	local reached = 0
	for _, r in plan.rooms do
		if seen[key(r[1], r[2])] then
			reached += 1
		end
	end
	local cut = 0
	for i = 1, plan.nx do
		for j = 1, plan.nz do
			if plan.kind[i][j] ~= 0 and not seen[key(i, j)] then
				cut += 1
			end
		end
	end
	return reached, cut
end

-- THE FLOOR as few rectangles as rows of cells give: { { i0, j0, i1, j1 } } (inclusive cells), never overlapping,
-- covering every floor cell once
function Dungeon.floors(plan: any): { { number } }
	local out: { { number } } = {}
	local open: { [string]: { number } } = {} -- runs of the row above, by their i extent: grown down while it repeats
	for j = 1, plan.nz do
		local now: { [string]: { number } } = {}
		local i = 1
		while i <= plan.nx do
			if plan.kind[i][j] ~= 0 then
				local i0 = i
				while i <= plan.nx and plan.kind[i][j] ~= 0 do
					i += 1
				end
				local k = `{i0}-{i - 1}`
				local run = open[k]
				if run then
					run[4] = j
					open[k] = nil
				else
					run = { i0, j, i - 1, j }
					table.insert(out, run)
				end
				now[k] = run
			else
				i += 1
			end
		end
		open = now
	end
	return out
end

-- THE WALLS: one on every edge between floor and not-floor, joined into straight runs.
-- { { side = "N"|"S"|"E"|"W" (the side of the floor it shuts), i0, i1, j } for N / S (cells i0..i1 of row j),
--   { side, j0, j1, i } for E / W; extend = { low: boolean, high: boolean } for N / S runs: whether the run is
--   lengthened by the wall's thickness at that end to fill an outer corner (never into a floor's inner corner);
--   trim = { low, high } for E / W runs: whether the run stops its thickness short at an inner corner
function Dungeon.walls(plan: any): { any }
	local out: { any } = {}
	local function floor(i: number, j: number): boolean
		return i >= 1 and i <= plan.nx and j >= 1 and j <= plan.nz and plan.kind[i][j] ~= 0
	end
	-- N and S: along x
	for _, side in { "N", "S" } do
		local dj = if side == "N" then -1 else 1
		for j = 1, plan.nz do
			local i = 1
			while i <= plan.nx do
				if floor(i, j) and not floor(i, j + dj) then
					local i0 = i
					while i <= plan.nx and floor(i, j) and not floor(i, j + dj) do
						i += 1
					end
					table.insert(out, {
						side = side,
						i0 = i0,
						i1 = i - 1,
						j = j,
						-- (the cell beyond the end, in the wall's own row: floor there = an inner corner)
						extend = { low = not floor(i0 - 1, j + dj), high = not floor(i, j + dj) },
					})
				else
					i += 1
				end
			end
		end
	end
	-- E and W: along z
	for _, side in { "W", "E" } do
		local di = if side == "W" then -1 else 1
		for i = 1, plan.nx do
			local j = 1
			while j <= plan.nz do
				if floor(i, j) and not floor(i + di, j) then
					local j0 = j
					while j <= plan.nz and floor(i, j) and not floor(i + di, j) do
						j += 1
					end
					table.insert(out, {
						side = side,
						j0 = j0,
						j1 = j - 1,
						i = i,
						-- (an INNER corner of the floor: the wall along x already fills the corner square there, so this
						-- one stops its thickness short - two walls in one place flicker)
						trim = { low = floor(i + di, j0 - 1), high = floor(i + di, j) },
					})
				else
					j += 1
				end
			end
		end
	end
	return out
end

-- a cell rectangle's place in studs round the dungeon's centre: (x0, z0, x1, z1)
function Dungeon.studs(
	plan: any,
	center: { number },
	i0: number,
	j0: number,
	i1: number,
	j1: number
): (number, number, number, number)
	local ox = center[1] - plan.nx * plan.cell / 2
	local oz = center[3] - plan.nz * plan.cell / 2
	return ox + (i0 - 1) * plan.cell, oz + (j0 - 1) * plan.cell, ox + i1 * plan.cell, oz + j1 * plan.cell
end

-- THE DOORWAYS of each room, counted on the floor as it is built (not on the links it was laid by: two corridors
-- may leave a room by one mouth, and a corridor may run through a third room): the ring of cells just outside the
-- room is walked once round, and every unbroken run of floor in it is one way out
function Dungeon.doorways(plan: any): { number }
	local out: { number } = {}
	local function floor(i: number, j: number): boolean
		return i >= 1 and i <= plan.nx and j >= 1 and j <= plan.nz and plan.kind[i][j] ~= 0
	end
	for k, r in plan.rooms do
		local ring: { boolean } = {}
		for i = r[1], r[3] do -- along its north side, west to east
			table.insert(ring, floor(i, r[2] - 1))
		end
		table.insert(ring, false) -- (a corner: a run on one side and a run on the next are two ways out)
		for j = r[2], r[4] do -- down its east side
			table.insert(ring, floor(r[3] + 1, j))
		end
		table.insert(ring, false)
		for i = r[3], r[1], -1 do -- back along its south side
			table.insert(ring, floor(i, r[4] + 1))
		end
		table.insert(ring, false)
		for j = r[4], r[2], -1 do -- up its west side
			table.insert(ring, floor(r[1] - 1, j))
		end
		table.insert(ring, false)
		local ways = 0
		for n = 1, #ring do
			if ring[n] and not ring[if n == 1 then #ring else n - 1] then
				ways += 1
			end
		end
		out[k] = ways
	end
	return out
end

-- what the plan comes to: rooms, the links it was laid by, and - counted on the built floor - each room's ways
-- out; a DEAD END is a room with one way out
function Dungeon.measure(plan: any): any
	local ways = Dungeon.doorways(plan)
	local dead = 0
	for _, n in ways do
		dead += if n == 1 then 1 else 0
	end
	local cells = 0
	for i = 1, plan.nx do
		for j = 1, plan.nz do
			cells += if plan.kind[i][j] ~= 0 then 1 else 0
		end
	end
	return {
		rooms = #plan.rooms,
		asked = plan.asked,
		links = #plan.links,
		loops = plan.loops,
		deadEnds = dead,
		ways = ways,
		floor = cells * plan.cell * plan.cell,
	}
end

return Dungeon

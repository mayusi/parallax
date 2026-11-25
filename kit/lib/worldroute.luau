--!strict
-- worldroute.luau (kit) — A ROAD ACROSS OPEN LAND, BY RULE (the owner's method list: "Procedural road networks" -
-- a town's streets are generated; a road across country was typed point by point, by eye, over land nobody had
-- looked at from above). Given where it starts, where it ends and how steep it may be, the road finds its own
-- way: round the hill rather than over it, through the pass, along the valley.
--   "route": { "from": [x, z], "to": [x, z], "via"?: [ [x, z], ... ], "grade": 0.25, "cell"?: 8, "reach"?: 400 }
-- reach = how far to each side of the straight line the road may look for its way (studs; as far as the two
-- places are apart when it says none, 256 at least): a pass further off than that is not found, and it says so.
-- grade = the steepest the road may climb (rise over run: 0.25 = 1 stud up in 4 along; an R6 walks up to about 1).
-- How: the land is read on a grid of `cell` studs; from each point the road may step to 48 others (the 8 round it
-- and longer steps between, so it is not held to 45-degree turns and can climb a slope aslant); a step steeper
-- than the grade, or onto a
-- place the caller refuses (water, a building's ground), is not taken. Every step costs its length, more the
-- steeper it is (up to twice at the limit): the cheapest way from start to end is found (A*: the first way
-- found is the cheapest there is on that grid). The staircase of grid steps is then pulled straight wherever a
-- straight run is as lawful, and the road's length, climb and steepest stretch are handed back with its points.
-- Pure: no files, no instances; the same land gives the same road. kit/test/spec/worldroute.spec.luau
local Route = {}

Route.CELL = 8 -- studs between two grid points when the route says none
Route.STEEP = 1 -- a step at the grade's limit costs 1 + this times its length (a flat one: its length)
Route.READ = 2 -- the land is read this often along every stretch of road (studs), whatever the cell: a heightmap
-- has a height every 4 studs, and a road read at its cell's half took slopes of twice its grade between two reads
Route.FINE = 1 -- ... and the finished road is measured this finely (its "steepest" is that measure, not the search's:
-- where the land has an edge - a heightmap has a facet every 4 studs - one stud of road can be steeper than the
-- 2 studs round it; measured on the kit's roughest land: 0.49 over a stud where 0.4 was asked, 0.41 over three)
Route.NODES = 60000 -- grid points a search may open (a route across a land far larger than its cell says so)
Route.MARGIN = 1 -- the search looks this share of the start-to-end distance to each side when no "reach" is said
Route.REACH = 256 -- ... and this many studs at least
Route.SLACK = 1.1 -- a straightened run may cost this much of the stretch it replaces

-- the steps a road may take from a grid point: the 8 round it and the longer ones (2,1) (3,1) (3,2) (4,1) (5,1)
-- in every turn and mirror - 48 headings. On an even slope the gentlest of them climbs 11 degrees off the level
-- line, a fifth of the slope's own grade: a slope more than five times the road's grade cannot be climbed aslant
local STEPS: { { number } } = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 }, { 1, 1 }, { 1, -1 }, { -1, 1 }, { -1, -1 } }
for _, long in { { 2, 1 }, { 3, 1 }, { 3, 2 }, { 4, 1 }, { 5, 1 } } do
	for _, sx in { 1, -1 } do
		for _, sz in { 1, -1 } do
			table.insert(STEPS, { long[1] * sx, long[2] * sz })
			table.insert(STEPS, { long[2] * sx, long[1] * sz })
		end
	end
end

local function number(v: any): boolean
	return type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge
end

local function point(v: any): boolean
	return type(v) == "table" and number(v[1]) and number(v[2])
end

-- what is wrong with a "route" (nothing = it can be used)
function Route.problems(route: any): { string }
	local out: { string } = {}
	if type(route) ~= "table" then
		return {
			'"route" is { "from": [x, z], "to": [x, z], "grade": <rise over run>, "via"?, "cell"? } (or false: points typed by hand)',
		}
	end
	for k in route do
		if k ~= "from" and k ~= "to" and k ~= "via" and k ~= "grade" and k ~= "cell" and k ~= "reach" then
			table.insert(
				out,
				`route.{tostring(k)}: a route says "from", "to", "via", "grade", "cell", "reach" - nothing else`
			)
		end
	end
	if not point(route.from) or not point(route.to) then
		table.insert(out, "route.from and route.to are [x, z]")
	elseif route.from[1] == route.to[1] and route.from[2] == route.to[2] and route.via == nil then
		table.insert(out, "route.from and route.to are the same place")
	end
	if not number(route.grade) or route.grade < 0.02 or route.grade > 1 then
		table.insert(
			out,
			`route.grade is the steepest the road may climb, rise over run: 0.02 to 1 (got {tostring(route.grade)})`
		)
	end
	if route.cell ~= nil and (not number(route.cell) or route.cell < 2 or route.cell > 64) then
		table.insert(
			out,
			`route.cell is the studs between two points the land is read at: 2 to 64 (got {tostring(route.cell)})`
		)
	end
	if route.reach ~= nil and (not number(route.reach) or route.reach < 16 or route.reach > 8192) then
		table.insert(
			out,
			`route.reach is how far to each side of the straight line the road may look: 16 to 8192 studs (got {tostring(
				route.reach
			)})`
		)
	end
	if route.via ~= nil then
		if type(route.via) ~= "table" or #route.via == 0 then
			table.insert(out, "route.via is a list of [x, z] the road passes through, in order")
		else
			for i, v in route.via do
				if not point(v) then
					table.insert(out, `route.via[{i}] is [x, z]`)
				end
			end
		end
	end
	-- two stops in a row that are one place: a stretch of no length (it made a road piece of no direction)
	if #out == 0 then
		local stops = { route.from }
		for _, v in route.via or {} do
			table.insert(stops, v)
		end
		table.insert(stops, route.to)
		for i = 2, #stops do
			if stops[i][1] == stops[i - 1][1] and stops[i][2] == stops[i - 1][2] and not (i == 2 and #stops == 2) then
				table.insert(out, `route: two stops in a row are the same place ([{stops[i][1]}, {stops[i][2]}])`)
			end
		end
	end
	return out
end

-- the steepest grade along the straight run a -> b, read every `step` studs (nil: it leaves the land or crosses a
-- refused place); and the run's cost
local function run(
	height: (number, number) -> number?,
	refuse: ((number, number) -> boolean)?,
	ax: number,
	az: number,
	bx: number,
	bz: number,
	step: number,
	grade: number
): (number?, number)
	local len = math.sqrt((bx - ax) ^ 2 + (bz - az) ^ 2)
	local n = math.max(1, math.ceil(len / step))
	local prev = height(ax, az)
	if prev == nil then
		return nil, 0
	end
	local steepest, cost = 0, 0
	for k = 1, n do
		local t = k / n
		local x, z = ax + (bx - ax) * t, az + (bz - az) * t
		local h = height(x, z)
		if h == nil or (refuse ~= nil and refuse(x, z)) then
			return nil, 0
		end
		local g = math.abs(h - prev) / (len / n)
		if g > grade + 1e-9 then
			return nil, 0
		end
		steepest = math.max(steepest, g)
		cost += (len / n) * (1 + Route.STEEP * (g / grade) ^ 2)
		prev = h
	end
	return steepest, cost
end

-- one leg, a -> b: the cheapest way on the grid -> points { { x, z } } (a and b themselves at its ends), or nil
-- and why ("no way": every way is steeper than the grade or shut; "too far": the search ran out of grid points)
local function leg(
	height: (number, number) -> number?,
	refuse: ((number, number) -> boolean)?,
	a: { number },
	b: { number },
	grade: number,
	cell: number,
	reach: number?
): ({ { number } }?, string?)
	if height(a[1], a[2]) == nil or height(b[1], b[2]) == nil then
		return nil, "off the land"
	end
	if refuse ~= nil and (refuse(a[1], a[2]) or refuse(b[1], b[2])) then
		return nil, "shut"
	end
	-- the grid: its origin at a, so that a is a grid point; b is reached from the grid point nearest it
	local ox, oz = a[1], a[2]
	local gi, gj = math.floor((b[1] - ox) / cell + 0.5), math.floor((b[2] - oz) / cell + 0.5)
	local span = math.sqrt((b[1] - a[1]) ^ 2 + (b[2] - a[2]) ^ 2)
	local margin = math.ceil((reach or math.max(Route.REACH, span * Route.MARGIN)) / cell)
	local i0, i1 = math.min(0, gi) - margin, math.max(0, gi) + margin
	local j0, j1 = math.min(0, gj) - margin, math.max(0, gj) + margin
	local width = i1 - i0 + 1
	local function key(i: number, j: number): number
		return (j - j0) * width + (i - i0)
	end
	-- a binary heap of { f, key }
	local heap: { { number } } = {}
	local function push(f: number, k: number)
		table.insert(heap, { f, k })
		local at = #heap
		while at > 1 do
			local up = at // 2
			if heap[up][1] <= heap[at][1] then
				break
			end
			heap[up], heap[at] = heap[at], heap[up]
			at = up
		end
	end
	local function pop(): { number }
		local top = heap[1]
		local last = table.remove(heap) :: { number }
		if #heap > 0 then
			heap[1] = last
			local at = 1
			while true do
				local l, r, least = at * 2, at * 2 + 1, at
				if l <= #heap and heap[l][1] < heap[least][1] then
					least = l
				end
				if r <= #heap and heap[r][1] < heap[least][1] then
					least = r
				end
				if least == at then
					break
				end
				heap[at], heap[least] = heap[least], heap[at]
				at = least
			end
		end
		return top
	end
	local best: { [number]: number } = { [key(0, 0)] = 0 }
	local from: { [number]: number } = {}
	local done: { [number]: boolean } = {}
	-- the end is its own point (-1): any grid point within a cell and a half of it may make the last run to it, so
	-- an end beside water, or off the grid's lines, is reached from whichever side is open
	local GOAL = -1
	local near = (1.5 * cell) ^ 2
	local read = math.min(cell / 2, Route.READ)
	push(0, key(0, 0))
	local opened = 0
	while #heap > 0 do
		local top = pop()
		local k = top[2]
		if done[k] then
			continue
		end
		done[k] = true
		if k == GOAL then
			break
		end
		opened += 1
		if opened > Route.NODES then
			return nil, "too far"
		end
		local i, j = k % width + i0, k // width + j0
		local x, z = ox + i * cell, oz + j * cell
		if (x - b[1]) ^ 2 + (z - b[2]) ^ 2 <= near then
			local ok, cost = run(height, refuse, x, z, b[1], b[2], read, grade)
			if ok ~= nil and (best[GOAL] == nil or best[k] + cost < best[GOAL] - 1e-9) then
				best[GOAL] = best[k] + cost
				from[GOAL] = k
				push(best[GOAL], GOAL)
			end
		end
		for _, s in STEPS do
			local ni, nj = i + s[1], j + s[2]
			if ni < i0 or ni > i1 or nj < j0 or nj > j1 then
				continue
			end
			local nk = key(ni, nj)
			if done[nk] then
				continue
			end
			local nx, nz = ox + ni * cell, oz + nj * cell
			local ok, cost = run(height, refuse, x, z, nx, nz, read, grade)
			if ok == nil then
				continue
			end
			local g = best[k] + cost
			if best[nk] == nil or g < best[nk] - 1e-9 then
				best[nk] = g
				from[nk] = k
				-- (what is left is never cheaper than the straight line to the end: the first way to reach it is
				-- the cheapest)
				push(g + math.sqrt((b[1] - nx) ^ 2 + (b[2] - nz) ^ 2), nk)
			end
		end
	end
	if not done[GOAL] then
		return nil, "no way"
	end
	local back: { { number } } = { b }
	local k = from[GOAL]
	while true do
		table.insert(back, { ox + (k % width + i0) * cell, oz + (k // width + j0) * cell })
		if k == key(0, 0) then
			break
		end
		k = from[k]
	end
	local pts: { { number } } = {}
	for n = #back, 1, -1 do
		-- (the start's own grid point may be the end's neighbour: never the same place twice)
		local q = back[n]
		if #pts == 0 or pts[#pts][1] ~= q[1] or pts[#pts][2] ~= q[2] then
			table.insert(pts, q)
		end
	end
	return pts, nil
end

-- the staircase of grid steps pulled straight: from each point the furthest later point a lawful straight run
-- reaches, as long as that run costs no more than Route.SLACK of the stretch it replaces
local function straighten(
	height: (number, number) -> number?,
	refuse: ((number, number) -> boolean)?,
	pts: { { number } },
	grade: number,
	cell: number
): { { number } }
	local costs: { number } = { 0 }
	for i = 2, #pts do
		local _, c = run(
			height,
			refuse,
			pts[i - 1][1],
			pts[i - 1][2],
			pts[i][1],
			pts[i][2],
			math.min(cell / 2, Route.READ),
			grade
		)
		costs[i] = costs[i - 1] + c
	end
	local out = { pts[1] }
	local at = 1
	while at < #pts do
		local reach = at + 1
		for j = #pts, at + 2, -1 do
			local ok, c =
				run(height, refuse, pts[at][1], pts[at][2], pts[j][1], pts[j][2], math.min(cell / 2, Route.READ), grade)
			if ok ~= nil and c <= (costs[j] - costs[at]) * Route.SLACK then
				reach = j
				break
			end
		end
		table.insert(out, pts[reach])
		at = reach
	end
	return out
end

-- a line of [x, z] points measured on the land, read every Route.FINE studs: its length, the studs it climbs and
-- falls, and its steepest stretch (rise over run). Finer than the search reads: this is the road's own truth, and
-- the compiler measures the road again after a curve has rounded its corners.
function Route.measure(height: (number, number) -> number?, line: { { number } }): (number, number, number, number)
	local length, climb, fall, steepest = 0, 0, 0, 0
	for i = 2, #line do
		local q, p = line[i - 1], line[i]
		local len = math.sqrt((p[1] - q[1]) ^ 2 + (p[2] - q[2]) ^ 2)
		if len <= 0 then
			continue
		end
		local n = math.max(1, math.ceil(len / Route.FINE))
		local prev = height(q[1], q[2]) or 0
		for k = 1, n do
			local t = k / n
			local h = height(q[1] + (p[1] - q[1]) * t, q[2] + (p[2] - q[2]) * t) or prev
			climb += math.max(0, h - prev)
			fall += math.max(0, prev - h)
			steepest = math.max(steepest, math.abs(h - prev) / (len / n))
			prev = h
		end
		length += len
	end
	return length, climb, fall, steepest
end

-- THE ROAD. height(x, z) = the land's height there, nil off the land; refuse(x, z) = true where no road may go
-- (water, a building's ground), optional.
-- -> { points = { { x, y, z } }, length, climb (studs gained, uphill only), fall, steepest (rise over run) }, or nil
-- and why: `no way from [x, z] to [x, z] within a grade of g`, `... is off the land`, `... is too far for a cell of c`
function Route.find(
	height: (number, number) -> number?,
	route: any,
	refuse: ((number, number) -> boolean)?
): (any?, string?)
	local cell = route.cell or Route.CELL
	local stops: { { number } } = { route.from }
	for _, v in route.via or {} do
		table.insert(stops, v)
	end
	table.insert(stops, route.to)
	local all: { { number } } = {}
	for s = 1, #stops - 1 do
		local a, b = stops[s], stops[s + 1]
		local pts, why = leg(height, refuse, a, b, route.grade, cell, route.reach)
		if not pts then
			local where = `from [{a[1]}, {a[2]}] to [{b[1]}, {b[2]}]`
			if why == "off the land" then
				return nil, `{where}: one of the two is off the land`
			elseif why == "shut" then
				return nil, `{where}: one of the two stands in water or where the road is kept off`
			elseif why == "too far" then
				return nil,
					`{where}: the search ran out ({Route.NODES} places looked at with a cell of {cell} studs) - lead the road with a "via" on the way, or let it look less far to each side ("reach")`
			end
			return nil,
				`no way {where} within a grade of {route.grade}: every way is steeper, or shut by what the road may not cross - raise "grade", lead it round with a "via", or let it look further to each side ("reach")`
		end
		local straight = straighten(height, refuse, pts, route.grade, cell)
		for i, p in straight do
			if not (s > 1 and i == 1) then -- (a via is one point, not two)
				table.insert(all, p)
			end
		end
	end
	local points: { { number } } = {}
	for _, p in all do
		table.insert(points, { p[1], height(p[1], p[2]) :: number, p[2] })
	end
	local length, climb, fall, steepest = Route.measure(height, all)
	return { points = points, length = length, climb = climb, fall = fall, steepest = steepest }, nil
end

return Route

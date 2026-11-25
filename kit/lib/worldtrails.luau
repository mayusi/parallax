-- worldtrails.luau (kit) — TRAILS WORN BY WALKERS (the owner's method list: "Agent-based generation"). Nobody plans
-- the footpaths between a village's houses, its well and its field: people walk, each the easiest way they can see,
-- and where many have walked the ground is easier still - so later walkers bend their way onto the worn one, and a
-- few shared trails grow where a web of straight lines would have been.
--   { "trails": { "name": "Tracks", "places": [[x, z], ...], "walkers": 60, "seed": 3, "grade": 0.6,
--                 "wear": 0.6, "cell": 8, "width": 4, "mat": "dirt" } }
-- places  = where people go from and to (3 to 40)
-- walkers = how many walks are made, each between two places drawn by the seed (every place is walked from at least
--           once: the first walks go round the places in turn)
-- reach   = how far outside the places' box a trail may swing to get round something (studs; 48 when not said)
-- grade   = the steepest a walker climbs (rise over run); steeper costs more, so a trail goes round a hill
-- wear    = how much easier trodden ground is, 0 (none: every walker goes his own way) to 0.9
-- HOW: the land is read on a grid of `cell` studs. A walker steps to one of the 8 cells round him; a step costs its
-- length, more the steeper it is (twice at the grade's limit), LESS the more feet have passed over both its cells
-- (by up to `wear`). Each walker takes the cheapest way there is (Dijkstra's search with a straight-line guess:
-- A*), then his steps are counted onto the ground. A step aslant passes between two cells: both must be ground he
-- could step onto, so no trail clips the corner of a cliff or of a pond. What comes back is the web of stretches that were walked, each
-- with how many walkers used it, joined into runs between the places and the forks, and each run pulled straight
-- wherever a straight walk is as lawful and no dearer (walkers on a grid go in 8 headings; feet do not).
-- Pure: no files, no instances; the same land, places and seed give the same trails.
local Trails = {}

Trails.CELL = 8
Trails.NODES = 40000 -- grid cells a trails step may cover
Trails.WALKS = 400 -- walks at most
Trails.STEEP = 1 -- a step at the grade's limit costs 1 + this times its length
Trails.SOFT = 3 -- feet after which trodden ground is half as much easier as it can get
Trails.SLACK = 1.02 -- a run pulled straight may cost this much of the grid steps it stands for

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

local KNOWN = {
	name = true,
	places = true,
	walkers = true,
	seed = true,
	grade = true,
	wear = true,
	cell = true,
	width = true,
	mat = true,
	worn = true,
	wornWidth = true,
	thickness = true,
	curve = true,
	stream = true,
	reach = true,
	parts = true,
}

-- what is wrong with a trails step, in words ({} = nothing)
function Trails.problems(spec: any): { string }
	local out: { string } = {}
	if type(spec) ~= "table" then
		return { 'trails needs { "places": [[x, z], ...], "walkers", "grade" }' }
	end
	for k in spec do
		if not KNOWN[k] then
			table.insert(out, `trails: "{tostring(k)}" is not a word it knows`)
		end
	end
	local places = spec.places
	local ok = type(places) == "table" and #places >= 3 and #places <= 40
	if ok then
		for _, p in places do
			ok = ok and type(p) == "table" and #p == 2 and number(p[1]) and number(p[2])
		end
	end
	if not ok then
		table.insert(out, 'trails: "places" is 3 to 40 places people walk between: [[x, z], ...]')
	end
	if not (number(spec.walkers) and spec.walkers % 1 == 0 and spec.walkers >= 1 and spec.walkers <= Trails.WALKS) then
		table.insert(out, `trails: "walkers" is how many walks are made, a whole number 1 to {Trails.WALKS}`)
	elseif ok and spec.walkers < #places then
		table.insert(
			out,
			`trails: {spec.walkers} walkers for {#places} places: each place is walked from once at least (say {#places} or more)`
		)
	end
	if not (number(spec.grade) and spec.grade > 0 and spec.grade <= 2) then
		table.insert(out, 'trails: "grade" is the steepest a walker climbs, rise over run: over 0, 2 at most')
	end
	if spec.wear ~= nil and not (number(spec.wear) and spec.wear >= 0 and spec.wear <= 0.9) then
		table.insert(out, 'trails: "wear" is how much easier trodden ground is, 0 to 0.9')
	end
	if spec.cell ~= nil and not (number(spec.cell) and spec.cell >= 4 and spec.cell <= 32) then
		table.insert(out, 'trails: "cell" is the grid the walkers step on, 4 to 32 studs')
	end
	if spec.reach ~= nil and not (number(spec.reach) and spec.reach >= 0 and spec.reach <= 1024) then
		table.insert(out, 'trails: "reach" is how far outside the places a trail may swing, 0 to 1024 studs')
	end
	if
		spec.seed ~= nil and not (number(spec.seed) and spec.seed % 1 == 0 and spec.seed >= 0 and spec.seed <= 65535)
	then
		table.insert(out, 'trails: "seed" is a whole number 0 to 65535')
	end
	if spec.width ~= nil and not (number(spec.width) and spec.width >= 2 and spec.width <= 16) then
		table.insert(out, 'trails: "width" is the most trodden trail\'s width, 2 to 16 studs')
	end
	if #out == 0 then
		local cell = spec.cell or Trails.CELL
		local x0, x1, z0, z1 = math.huge, -math.huge, math.huge, -math.huge
		for _, p in places do
			x0, x1 = math.min(x0, p[1]), math.max(x1, p[1])
			z0, z1 = math.min(z0, p[2]), math.max(z1, p[2])
		end
		local nx, nz =
			math.ceil((x1 - x0) / cell) + 1 + 2 * Trails.margin(cell, spec.reach),
			math.ceil((z1 - z0) / cell) + 1 + 2 * Trails.margin(cell, spec.reach)
		if nx * nz > Trails.NODES then
			table.insert(
				out,
				`trails: the places lie {math.floor(x1 - x0)} x {math.floor(z1 - z0)} studs apart: {nx * nz} cells of {cell} studs ({Trails.NODES} at most: a larger "cell", a smaller "reach", or places closer together)`
			)
		end
		for i = 1, #places do
			for j = i + 1, #places do
				if math.abs(places[i][1] - places[j][1]) < cell and math.abs(places[i][2] - places[j][2]) < cell then
					table.insert(
						out,
						`trails: places {i} and {j} stand within one cell ({cell} studs) of each other: they are one place`
					)
				end
			end
		end
	end
	return out
end

-- cells of room round the places' box (a trail may swing out past the outermost place: by `reach` studs, 48 when
-- none is said)
function Trails.margin(cell: number, reach: number?): number
	return math.max(1, math.ceil((reach or 48) / cell))
end

export type Run = { points: { { number } }, feet: number }

-- THE TRAILS. height(x, z) = the land's height there (nil: off the land); refuse(x, z) = true where nobody walks
-- (water, a building's ground), optional.
-- -> { runs = { { points = { {x, z}, ... }, feet = n } }, length (studs of trail), walked (studs all walkers walked),
--      most (the most feet on one stretch), walks, lost = { {from, to} } (walks that found no way) }, or nil and why
function Trails.grow(
	spec: any,
	height: (number, number) -> number?,
	refuse: ((number, number) -> boolean)?
): (any?, string?)
	local cell: number = spec.cell or Trails.CELL
	local wear: number = if spec.wear == nil then 0.6 else spec.wear
	local grade: number = spec.grade
	local places = spec.places
	local x0, x1, z0, z1 = math.huge, -math.huge, math.huge, -math.huge
	for _, p in places do
		x0, x1 = math.min(x0, p[1]), math.max(x1, p[1])
		z0, z1 = math.min(z0, p[2]), math.max(z1, p[2])
	end
	local pad = Trails.margin(cell, spec.reach)
	local nx, nz = math.ceil((x1 - x0) / cell) + 1 + 2 * pad, math.ceil((z1 - z0) / cell) + 1 + 2 * pad
	local ox, oz = x0 - pad * cell, z0 - pad * cell
	local function key(i: number, j: number): number
		return (j - 1) * nx + i
	end
	-- the land at each cell, read once (false: nobody stands there)
	local land: { [number]: number | boolean } = {}
	local function at(i: number, j: number): number?
		local k = key(i, j)
		local h = land[k]
		if h == nil then
			local x, z = ox + (i - 1) * cell, oz + (j - 1) * cell
			local y = height(x, z)
			if y == nil or (refuse and refuse(x, z)) then
				land[k] = false
				return nil
			end
			land[k] = y
			return y
		end
		return if h == false then nil else h :: number
	end
	local home: { { number } } = {}
	for n, p in places do
		local i, j = math.round((p[1] - ox) / cell) + 1, math.round((p[2] - oz) / cell) + 1
		-- (the place itself, and the grid point the walkers start from - within half a cell of it)
		if height(p[1], p[2]) == nil or (refuse and refuse(p[1], p[2])) then
			return nil,
				`place {n} [{p[1]}, {p[2]}] is off the land, in water or on a building's ground: nobody walks from there`
		end
		if at(i, j) == nil then
			return nil,
				`place {n} [{p[1]}, {p[2]}] stands at the very edge of ground a walker can stand on (the grid point beside it, [{ox + (i - 1) * cell}, {oz + (j - 1) * cell}], is off the land or in water): move it a few studs`
		end
		home[n] = { i, j }
	end
	local feet: { [number]: number } = {} -- (feet over each cell)
	-- IS THE WAY BETWEEN TWO NEIGHBOURING CELLS OPEN: read at its quarter points too (a stream or a strip nobody may
	-- stand on that is thinner than a cell lies BETWEEN two grid points; thinner than a quarter cell it is not seen)
	local shut: { [string]: boolean } = {}
	local function open(k: number, nk: number, i: number, j: number, ni: number, nj: number): boolean
		local id = `{math.min(k, nk)}:{math.max(k, nk)}`
		local v = shut[id]
		if v == nil then
			v = false
			for _, t in { 0.25, 0.5, 0.75 } do
				local x, z = ox + (i - 1 + (ni - i) * t) * cell, oz + (j - 1 + (nj - j) * t) * cell
				if height(x, z) == nil or (refuse and refuse(x, z)) then
					v = true
				end
			end
			shut[id] = v
		end
		return not v
	end
	local STEPS = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 }, { 1, 1 }, { 1, -1 }, { -1, 1 }, { -1, -1 } }
	local cheapest = 1 - wear -- (no step costs less than this share of its length: the search's guess stays lawful)

	-- one walk a -> b: the cheapest way -> the cells walked { key }, in order, or nil
	local function walk(a: { number }, b: { number }): { number }?
		local goal = key(b[1], b[2])
		local cost: { [number]: number } = { [key(a[1], a[2])] = 0 }
		local from: { [number]: number } = {}
		local done: { [number]: boolean } = {}
		-- a heap of { guess, key, i, j }
		local heap: { { number } } = {}
		local function push(item: { number })
			table.insert(heap, item)
			local c = #heap
			while c > 1 do
				local p = c // 2
				if heap[p][1] <= heap[c][1] then
					break
				end
				heap[p], heap[c] = heap[c], heap[p]
				c = p
			end
		end
		local function pop(): { number }
			local top = heap[1]
			local last = table.remove(heap) :: { number }
			if #heap > 0 then
				heap[1] = last
				local p = 1
				while true do
					local l, r, s = p * 2, p * 2 + 1, p
					if l <= #heap and heap[l][1] < heap[s][1] then
						s = l
					end
					if r <= #heap and heap[r][1] < heap[s][1] then
						s = r
					end
					if s == p then
						break
					end
					heap[p], heap[s] = heap[s], heap[p]
					p = s
				end
			end
			return top
		end
		local function guess(i: number, j: number): number
			return math.sqrt((i - b[1]) ^ 2 + (j - b[2]) ^ 2) * cell * cheapest
		end
		push({ guess(a[1], a[2]), key(a[1], a[2]), a[1], a[2] })
		while #heap > 0 do
			local item = pop()
			local k, i, j = item[2], item[3], item[4]
			if not done[k] then
				done[k] = true
				if k == goal then
					local cells = { k }
					while from[cells[#cells]] do
						table.insert(cells, from[cells[#cells]])
					end
					local n = #cells
					for q = 1, n // 2 do
						cells[q], cells[n + 1 - q] = cells[n + 1 - q], cells[q]
					end
					return cells
				end
				local here = at(i, j) :: number
				for _, s in STEPS do
					local ni, nj = i + s[1], j + s[2]
					if ni >= 1 and ni <= nx and nj >= 1 and nj <= nz then
						local nk = key(ni, nj)
						local there = if done[nk] then nil else at(ni, nj)
						-- (a diagonal step does not cut a corner: both cells it passes between must be ground a walker
						-- could step onto from here and from there - not water, not a wall of land)
						local square = true
						if there ~= nil and s[1] ~= 0 and s[2] ~= 0 then
							for _, corner in { at(ni, j), at(i, nj) } :: { any } do
								square = square
									and corner ~= nil
									and math.abs(corner - here) / cell <= grade
									and math.abs(corner - there) / cell <= grade
							end
							square = square and at(ni, j) ~= nil and at(i, nj) ~= nil
						end
						if there ~= nil and square and open(k, nk, i, j, ni, nj) then
							local run = cell * (if s[1] ~= 0 and s[2] ~= 0 then math.sqrt(2) else 1)
							local slope = math.abs(there - here) / run
							if slope <= grade then
								local trod = math.min(feet[k] or 0, feet[nk] or 0)
								local ease = 1 - wear * trod / (trod + Trails.SOFT)
								local c = cost[k] + run * (1 + Trails.STEEP * slope / grade) * ease
								if cost[nk] == nil or c < cost[nk] - 1e-9 then
									cost[nk] = c
									from[nk] = k
									push({ c + guess(ni, nj), nk, ni, nj })
								end
							end
						end
					end
				end
			end
		end
		return nil
	end

	local rand = lcg((spec.seed or 1) * 31 + 7)
	local used: { [string]: number } = {} -- (feet over each stretch between two neighbouring cells: "a:b", a < b)
	local walked, walks = 0, 0
	local lost: { { number } } = {}
	local function cellXZ(k: number): (number, number)
		local i, j = (k - 1) % nx + 1, (k - 1) // nx + 1
		return ox + (i - 1) * cell, oz + (j - 1) * cell
	end
	for w = 1, spec.walkers do
		-- the first walks start from each place in turn; where to, and every later walk, by the seed
		local a = if w <= #places then w else 1 + math.floor(rand() * #places)
		local b = 1 + math.floor(rand() * (#places - 1))
		if b >= a then
			b += 1
		end
		a, b = math.min(a, #places), math.min(b, #places)
		local cells = walk(home[a], home[b])
		if not cells then
			table.insert(lost, { a, b })
		else
			walks += 1
			for q = 1, #cells do
				feet[cells[q]] = (feet[cells[q]] or 0) + 1
				if q > 1 then
					local lo, hi = math.min(cells[q - 1], cells[q]), math.max(cells[q - 1], cells[q])
					local id = `{lo}:{hi}`
					used[id] = (used[id] or 0) + 1
					local ax, az = cellXZ(lo)
					local bx, bz = cellXZ(hi)
					walked += math.sqrt((ax - bx) ^ 2 + (az - bz) ^ 2)
				end
			end
		end
	end
	if walks == 0 then
		return nil, `no walker found a way between any two places within a grade of {grade}`
	end

	-- the web of stretches, joined into runs: a run ends at a place, at a fork, or where the feet on it change
	local near: { [number]: { { number } } } = {} -- (cell -> { { other cell, feet } })
	local ids: { string } = {}
	for id in used do
		table.insert(ids, id)
	end
	table.sort(ids)
	local length, most = 0, 0
	for _, id in ids do
		local lo, hi = string.match(id, "^(%d+):(%d+)$")
		local a, b, n = tonumber(lo) :: number, tonumber(hi) :: number, used[id]
		near[a] = near[a] or {}
		near[b] = near[b] or {}
		table.insert(near[a], { b, n })
		table.insert(near[b], { a, n })
		most = math.max(most, n)
	end
	local isHome: { [number]: boolean } = {}
	for _, h in home do
		isHome[key(h[1], h[2])] = true
	end
	local function knot(k: number): boolean
		local n = near[k]
		return isHome[k] or #n ~= 2 or n[1][2] ~= n[2][2]
	end
	local taken: { [string]: boolean } = {}
	-- what a straight walk a -> b costs (its length, more the steeper: as a grid step does, wear left out), read every
	-- quarter cell; nil where it leaves the land, crosses what nobody walks, or climbs over the grade
	local function stretch(a: { number }, b: { number }): number?
		local d = math.sqrt((a[1] - b[1]) ^ 2 + (a[2] - b[2]) ^ 2)
		local n = math.max(1, math.ceil(d / (cell / 4)))
		local prev = height(a[1], a[2])
		if prev == nil then
			return nil
		end
		local cost = 0
		for q = 1, n do
			local x, z = a[1] + (b[1] - a[1]) * q / n, a[2] + (b[2] - a[2]) * q / n
			local y = height(x, z)
			if y == nil or (refuse and refuse(x, z)) then
				return nil
			end
			local slope = math.abs(y - prev) / (d / n)
			if slope > grade + 1e-9 then
				return nil
			end
			cost += d / n * (1 + Trails.STEEP * slope / grade)
			prev = y
		end
		return cost
	end
	local runs: { Run } = {}
	local cellsSorted: { number } = {}
	for k in near do
		table.insert(cellsSorted, k)
	end
	table.sort(cellsSorted)
	local function follow(start: number, first: { number })
		local points = { { cellXZ(start) } }
		local prev, here, n = start, first[1], first[2]
		while true do
			taken[`{math.min(prev, here)}:{math.max(prev, here)}`] = true
			table.insert(points, { cellXZ(here) })
			if knot(here) then
				break
			end
			local nextOne = if near[here][1][1] == prev then near[here][2] else near[here][1]
			if taken[`{math.min(here, nextOne[1])}:{math.max(here, nextOne[1])}`] then
				break
			end
			prev, here = here, nextOne[1]
		end
		-- PULLED STRAIGHT: walkers on a grid go in 8 headings, feet do not. From each point of the run the furthest
		-- later point is taken that a straight walk reaches as lawfully (on land, off what nobody walks, never over
		-- the grade) and no dearer than the stretch of grid steps it stands for
		local line = { points[1] }
		local q = 1
		while q < #points do
			local sofar = 0
			local best = q + 1
			for r = q + 1, #points do
				local a, b = points[r - 1], points[r]
				-- (a grid step was walked, so it stands; read finer than the grid it may cross something thinner than a
				-- cell - then it is counted at its dearest and nothing is pulled straight across it)
				sofar += stretch(a, b) or math.sqrt((a[1] - b[1]) ^ 2 + (a[2] - b[2]) ^ 2) * (1 + Trails.STEEP)
				local direct = stretch(points[q], points[r])
				if direct ~= nil and direct <= sofar * Trails.SLACK then
					best = r
				end
			end
			table.insert(line, points[best])
			q = best
		end
		table.insert(runs, { points = line, feet = n })
	end
	for _, k in cellsSorted do
		if knot(k) then
			table.sort(near[k], function(p, q)
				return p[1] < q[1]
			end)
			for _, n in near[k] do
				if not taken[`{math.min(k, n[1])}:{math.max(k, n[1])}`] then
					follow(k, n)
				end
			end
		end
	end
	-- (a ring with no knot on it: no place, no fork - cannot be, every walk starts at a place; kept safe all the same)
	for _, k in cellsSorted do
		for _, n in near[k] do
			if not taken[`{math.min(k, n[1])}:{math.max(k, n[1])}`] then
				follow(k, n)
			end
		end
	end
	-- a run that ends at a place ends AT the place, not at the grid point beside it
	for _, run in runs do
		for _, e in { 1, #run.points } do
			local pt = run.points[e]
			for n, h in home do
				local hx, hz = ox + (h[1] - 1) * cell, oz + (h[2] - 1) * cell
				if math.abs(pt[1] - hx) < 1e-6 and math.abs(pt[2] - hz) < 1e-6 then
					run.points[e] = { places[n][1], places[n][2] }
				end
			end
		end
	end
	for _, run in runs do
		for q = 2, #run.points do
			length += math.sqrt(
				(run.points[q][1] - run.points[q - 1][1]) ^ 2 + (run.points[q][2] - run.points[q - 1][2]) ^ 2
			)
		end
	end
	return { runs = runs, length = length, walked = walked, most = most, walks = walks, lost = lost }, nil
end

return Trails

-- RoadBed.luau (kit runtime, pure) — A ROAD'S BED CUT INTO AND FILLED ONTO THE LAND (the owner's finding W-R07:
-- "grounded roads are slabs, no grade or cut and fill"). A road laid on the land followed every bump of it. A bed is
-- the road's own line through the land: a height at every few studs of its length, never steeper than its grade.
-- Where the land stands higher than the bed it is CUT down to it; where it lies lower it is FILLED up to it; and
-- beside the road the land comes back to itself over a shoulder.
--   bed = { points = { { x, y, z }, ... }, width = studs across the level top, shoulder = studs from the top's edge
--           back to the untouched land }
-- A place takes the bed's height on the NEAREST point of its whole line (the first such stretch, on a tie), and as
-- much of it as its distance allows: all of it on the level top, none past the shoulder.
-- ONE RULE for all three readers of the land: the game writes the land's voxels by it (src/kit/Environment.luau),
-- the compiler sets everything down on it (kit/lib/world.luau requires this file), and kit world check walks the
-- heights the compiler samples through it (World.terrainField).
-- Pure: no game calls.
local RoadBed = {}

RoadBed.STEP = 8 -- studs between two points of a bed's line, at most
RoadBed.TOLERANCE = 0.05 -- studs a stored line may stray from the line worked out (a straight run is two points)

local function smooth(t: number): number
	t = math.clamp(t, 0, 1)
	return t * t * (3 - 2 * t)
end

local function number(v: any): boolean
	return type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge
end

-- what is wrong with a bed, in words ({} = nothing)
function RoadBed.problems(bed: any): { string }
	if type(bed) ~= "table" then
		return { "a bed is { points, width, shoulder }" }
	end
	local out: { string } = {}
	local pts = bed.points
	local ok = type(pts) == "table" and #pts >= 2
	if ok then
		for _, p in pts do
			ok = ok and type(p) == "table" and #p == 3 and number(p[1]) and number(p[2]) and number(p[3])
		end
	end
	if not ok then
		table.insert(out, "a bed's points are two or more [x, y, z]")
	end
	if not (number(bed.width) and bed.width >= 2 and bed.width <= 64) then
		table.insert(out, "a bed's width is 2 to 64 studs")
	end
	if not (number(bed.shoulder) and bed.shoulder >= 2 and bed.shoulder <= 64) then
		table.insert(out, "a bed's shoulder is 2 to 64 studs")
	end
	return out
end

-- THE BED'S INDEX: its stretches by the square cells their boxes touch (cells as wide as the bed reaches, so every
-- stretch within reach of a place lies in the 3 x 3 cells round it). Made once for a bed and kept while the bed is
-- (a table that forgets what nothing else holds): a place far from every road is done with in a few look-ups
local INDEX: { [any]: any } = setmetatable({}, { __mode = "k" }) :: any

local function cellKey(i: number, j: number): number
	return (i + 1048576) * 2097152 + (j + 1048576)
end

local function indexOf(bed: any): any
	local found = INDEX[bed]
	if found then
		return found
	end
	local reach = bed.width / 2 + bed.shoulder
	local size = math.max(reach, 8)
	local cells: { [number]: { number } } = {}
	local x0, z0, x1, z1 = math.huge, math.huge, -math.huge, -math.huge
	local pts = bed.points
	for k = 1, #pts - 1 do
		local a, b = pts[k], pts[k + 1]
		local ax, bx = math.min(a[1], b[1]), math.max(a[1], b[1])
		local az, bz = math.min(a[3], b[3]), math.max(a[3], b[3])
		x0, x1, z0, z1 = math.min(x0, ax), math.max(x1, bx), math.min(z0, az), math.max(z1, bz)
		for i = math.floor(ax / size), math.floor(bx / size) do
			for j = math.floor(az / size), math.floor(bz / size) do
				local key = cellKey(i, j)
				local list = cells[key]
				if list == nil then
					list = {}
					cells[key] = list
				end
				table.insert(list, k) -- (in rising order: stretches are visited in order)
			end
		end
	end
	found = { size = size, cells = cells, box = { x0 - reach, z0 - reach, x1 + reach, z1 + reach } }
	INDEX[bed] = found
	return found
end

-- THE BED AT A PLACE: its height on the line's nearest point, and how much of the place is the bed's
-- (1 on the level top, falling to 0 over the shoulder) -> height, share; nil, 0 when the place is out of its reach
function RoadBed.at(bed: any, x: number, z: number): (number?, number)
	local idx = indexOf(bed)
	local box = idx.box
	if x < box[1] or x > box[3] or z < box[2] or z > box[4] then
		return nil, 0
	end
	-- (the stretches in the 3 x 3 cells round the place, each once, in their own order)
	local ci, cj = math.floor(x / idx.size), math.floor(z / idx.size)
	local seen: { [number]: boolean } = {}
	local near: { number } = {}
	for i = ci - 1, ci + 1 do
		for j = cj - 1, cj + 1 do
			local list = idx.cells[cellKey(i, j)]
			if list then
				for _, k in list do
					if not seen[k] then
						seen[k] = true
						table.insert(near, k)
					end
				end
			end
		end
	end
	if #near == 0 then
		return nil, 0
	end
	table.sort(near)
	local best, bestY = math.huge, 0
	local pts = bed.points
	for _, k in near do
		local a, b = pts[k], pts[k + 1]
		local vx, vz = b[1] - a[1], b[3] - a[3]
		local len2 = vx * vx + vz * vz
		local t = if len2 > 0 then math.clamp(((x - a[1]) * vx + (z - a[3]) * vz) / len2, 0, 1) else 0
		local dx, dz = x - (a[1] + vx * t), z - (a[3] + vz * t)
		local d = dx * dx + dz * dz
		if d < best then
			best, bestY = d, a[2] + (b[2] - a[2]) * t
		end
	end
	local share = 1 - smooth((math.sqrt(best) - bed.width / 2) / bed.shoulder)
	if share <= 0 then
		return nil, 0
	end
	return bestY, share
end

-- THE LAND WITH ITS BEDS: h = the land's own height at the place -> its height once every bed has cut or filled it
-- (in the order they are listed: a later road crosses an earlier one at its own level)
function RoadBed.apply(beds: { any }?, x: number, z: number, h: number): number
	if beds == nil then
		return h
	end
	for _, bed in beds :: { any } do
		local y, share = RoadBed.at(bed, x, z)
		if y ~= nil then
			h = y * share + h * (1 - share)
		end
	end
	return h
end

-- the line kept short: a point is left out where the line through its neighbours passes within TOLERANCE of it
-- (across and in height), and every number is kept to a thousandth of a stud
local function thin(points: { { number } }): { { number } }
	local function round(v: number): number
		return math.round(v * 1000) / 1000
	end
	local out = { points[1] }
	local anchor = 1
	local k = 2
	while k <= #points do
		-- (the furthest point from the anchor whose chord passes every point between within the tolerance)
		local far = k
		for m = k + 1, #points do
			local a, b = points[anchor], points[m]
			local vx, vz = b[1] - a[1], b[3] - a[3]
			local len2 = vx * vx + vz * vz
			local fits = len2 > 0
			for q = anchor + 1, m - 1 do
				if not fits then
					break
				end
				local p = points[q]
				local t = math.clamp(((p[1] - a[1]) * vx + (p[3] - a[3]) * vz) / len2, 0, 1)
				local across = math.sqrt((p[1] - a[1] - vx * t) ^ 2 + (p[3] - a[3] - vz * t) ^ 2)
				local up = math.abs(p[2] - (a[2] + (b[2] - a[2]) * t))
				fits = across <= RoadBed.TOLERANCE and up <= RoadBed.TOLERANCE
			end
			if fits then
				far = m
			else
				break
			end
		end
		table.insert(out, points[far])
		anchor, k = far, far + 1
	end
	for i, p in out do
		out[i] = { round(p[1]), round(p[2]), round(p[3]) }
	end
	return out
end

-- A BED'S LINE FROM A ROAD'S: line = { { x, z }, ... } (the road's own points; the last on the first = a loop),
-- height(x, z) = the land there (nil off the land), grade = the steepest the bed may climb (rise over run),
-- half = how far either side of the line the road's own edges lie (its cut and fill are read there too)
-- -> { points = { { x, y, z } } (kept short: see thin), cut = the most the land is cut down under the road, fill = the
--      most it is filled up (on the line and at both edges), length, loop }, or nil and why.
-- The bed is the line nearest the land's own (eased) that never climbs over the grade: of all such lines, the one
-- whose worst cut or fill is the least - so a misfit is shared between both ends, never left at the end alone
function RoadBed.profile(
	line: { { number } },
	height: (number, number) -> number?,
	grade: number,
	step: number?,
	half: number?
): (any?, string?)
	local every = step or RoadBed.STEP
	local first, last = line[1], line[#line]
	local loop = #line >= 4 and math.abs(first[1] - last[1]) < 1e-6 and math.abs(first[2] - last[2]) < 1e-6
	local pts: { { number } } = {} -- { x, z, along }
	local along = 0
	for k = 1, #line - 1 do
		local a, b = line[k], line[k + 1]
		local len = math.sqrt((b[1] - a[1]) ^ 2 + (b[2] - a[2]) ^ 2)
		if len > 1e-9 then -- (a point typed twice is one point)
			local n = math.max(1, math.ceil(len / every - 1e-9))
			for q = if #pts == 0 then 0 else 1, n do
				table.insert(pts, { a[1] + (b[1] - a[1]) * q / n, a[2] + (b[2] - a[2]) * q / n, along + len * q / n })
			end
			along += len
		end
	end
	if #pts < 2 or along <= 0 then
		return nil, "a bed needs a road of some length"
	end
	-- (a loop: its last point IS its first - worked out once, and closed again at the end)
	local n = if loop then #pts - 1 else #pts
	local land: { number } = {}
	for k = 1, n do
		local h = height(pts[k][1], pts[k][2])
		if h == nil then
			return nil, `the road leaves the land at [{pts[k][1]}, {pts[k][2]}]: no bed can be laid there`
		end
		land[k] = h
	end
	-- the distance along the road from point k to the next (round to the first again, on a loop)
	local function gap(k: number): number
		if k < n then
			return pts[k + 1][3] - pts[k][3]
		end
		return along - pts[n][3] -- (a loop's closing stretch)
	end
	-- the land's own line, eased (three passes of a quarter-half-quarter mean: a bump of one point is no hill)
	local e = table.clone(land)
	for _ = 1, 3 do
		local was = table.clone(e)
		for k = 1, n do
			local prev = if k > 1 then k - 1 elseif loop then n else nil
			local nxt = if k < n then k + 1 elseif loop then 1 else nil
			if prev and nxt then
				e[k] = was[prev] * 0.25 + was[k] * 0.5 + was[nxt] * 0.25
			end
		end
	end
	-- the highest line under the grade that lies on or under the eased land everywhere (lo), and the lowest on or over
	-- it (hi): each the land's own line seen from every other point at the grade, both ways along the road (twice
	-- round a loop). Halfway between them is the line of the least worst cut or fill that holds the grade
	local lo, hi = table.clone(e), table.clone(e)
	local laps = if loop then 2 else 1
	for _ = 1, laps do
		for k = 1, n do
			local prev = if k > 1 then k - 1 elseif loop then n else nil
			if prev then
				local r = grade * gap(prev)
				lo[k] = math.max(lo[k], lo[prev] - r)
				hi[k] = math.min(hi[k], hi[prev] + r)
			end
		end
	end
	for _ = 1, laps do
		for k = n, 1, -1 do
			local nxt = if k < n then k + 1 elseif loop then 1 else nil
			if nxt then
				local r = grade * gap(k)
				lo[k] = math.max(lo[k], lo[nxt] - r)
				hi[k] = math.min(hi[k], hi[nxt] + r)
			end
		end
	end
	local out = {}
	for k = 1, n do
		out[k] = { pts[k][1], (lo[k] + hi[k]) / 2, pts[k][2] }
	end
	if loop then
		out[n + 1] = { pts[1][1], out[1][2], pts[1][2] }
	end
	-- how much it cuts and fills: on the line, and at both of the road's edges
	local cut, fill = 0, 0
	for k = 1, n do
		local y = out[k][2]
		cut = math.max(cut, land[k] - y)
		fill = math.max(fill, y - land[k])
		if half and half > 0 then
			local prev = if k > 1 then k - 1 elseif loop then n else k
			local nxt = if k < n then k + 1 elseif loop then 1 else k
			local tx, tz = pts[nxt][1] - pts[prev][1], pts[nxt][2] - pts[prev][2]
			local len = math.sqrt(tx * tx + tz * tz)
			if len > 1e-9 then
				for _, side in { -1, 1 } do
					local ex, ez = pts[k][1] - tz / len * half * side, pts[k][2] + tx / len * half * side
					local h = height(ex, ez)
					if h ~= nil then
						cut = math.max(cut, h - y)
						fill = math.max(fill, y - h)
					end
				end
			end
		end
	end
	return { points = thin(out), cut = cut, fill = fill, length = along, loop = loop }, nil
end

-- the steepest stretch of a bed's line (rise over run)
function RoadBed.steepest(points: { { number } }): number
	local worst = 0
	for k = 2, #points do
		local a, b = points[k - 1], points[k]
		local run = math.sqrt((b[1] - a[1]) ^ 2 + (b[3] - a[3]) ^ 2)
		if run > 1e-9 then
			worst = math.max(worst, math.abs(b[2] - a[2]) / run)
		end
	end
	return worst
end

return RoadBed

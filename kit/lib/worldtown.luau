-- worldtown.luau — a TOWN PLAN by rules (the world methods audit, 2026-11-13: board/plans/archive/2026-11-13-world-methods-audit.md).
-- The `city` generator is a regular grid of box buildings; the owner on the District built from it: "the city does not
-- feel or look like a genuine proper open world". A town here is planned the way old towns stand:
--   * a SQUARE entered at its corners, pinwheel-wise (Camillo Sitte's "turbine" square, 1889): each street leaves along
--     one edge, so no street crosses the square and every view across it ends on a house front, never on a gap;
--   * the LANDMARK stands against the square's wall where the main gate's street points - seen from the gate on;
--   * the quarters between are cut by lanes and alleys that END on another street (T-junctions: a closed view at the
--     end of every lane), never lined up across it into a grid;
--   * a street along the inside of the edge (the wall street) closes every lane into a loop: no dead ends;
--   * every block is built round its edge in TERRACED LOTS (narrow fronts, party walls, a yard inside), each house's
--     door on its own street, taller on the square and the main streets, no two neighbours the same height.
-- It is a MACRO generator: Town.plan lays the streets, blocks and lots out, Town.steps turns the plan into the steps
-- the compiler already knows (floor, building, wall, fit) - so the check, the look and the Studio stage read a town
-- like any other world. Town.measure reads the plan as a street graph (loops, dead ends, T / X junctions, the walk
-- from each gate to the square, the longest straight view): numbers to READ a layout by, never a gate on its look.
-- Streets run on the two axes only (the building generator cannot turn a house): a later stage.
-- Pure: no Roblox APIs, no file access; same seed -> same town. kit/test/spec/worldtown.spec.luau.
local Facade = require("./worldfacade")

local Town = {}

export type Rect = { x0: number, x1: number, z0: number, z1: number }
export type Street = {
	name: string,
	rank: string, -- "main" | "lane" | "alley"
	axis: string, -- "x" (runs east-west: z fixed) | "z" (runs north-south: x fixed)
	at: number, -- the centre line's fixed coordinate
	from: number, -- the centre line's span along its axis
	to: number,
	width: number,
	gate: string?, -- the side ("N" | "E" | "S" | "W") whose gate it leaves the town by
}
export type Lot = {
	name: string,
	rect: Rect,
	front: string, -- the side its door is on
	rank: number, -- what it faces: 4 the square, 3 a main street, 2 a lane, 1 an alley
	block: number,
	corner: string?, -- the second street side of a corner lot
	floors: number,
	floorHeight: number,
	landmark: boolean?,
	through: string?, -- a through house: the side its back shows to another street
	type: string?, -- its house type: "<front>x<depth>_<floors>f<floor height>[_e | _w][_t]" (a corner's windowed flank; a through house)
}

Town.RANK = { square = 4, main = 3, lane = 2, alley = 1 }
Town.SPEED = 16 -- the R6 walk, studs a second (kit/world/worldcheck.py PLAYER.speed)
Town.DEFAULTS = {
	area = { 320, 320 },
	grid = 4, -- every street edge, block and lot line lies on this grid (Roblox's terrain cell too)
	-- the r6 sheet wants a street >= 30 and an alley >= 8, MEASURED between the walls by kit world check: a house's
	-- wall faces stand on its lot's lines (Town.steps), so a street measures what it is planned at
	streets = { main = 32, lane = 12, alley = 8 },
	square = { 96, 72 }, -- (room on its far wall for the landmark beside a 32-stud street's mouth)
	-- a lot's front and depth are whole grid steps inside these ranges: a town's houses come in a FEW sizes, so a small
	-- kit of house meshes (one per type: Town.record's "types") can skin every one of them
	lots = { width = { 16, 24 }, depth = { 24, 24 }, yard = 12 },
	block = { 40, 88 }, -- a block's shortest worth cutting off / longest left uncut
	floors = { square = { 3, 4 }, main = { 3, 4 }, lane = { 2, 3 }, alley = { 2, 3 } },
	floorHeights = { 14, 15 },
	kerb = 0.4, -- a block's pavement over the street
	sill = 0.1, -- a house floor a hair over its pavement: in one plane the two would flicker inside every house
}

-- deterministic RNG (the same generator as kit/lib/world.luau's scatter)
local function lcg(seed: number): () -> number
	local state = (seed or 1) % 2147483647
	if state <= 0 then
		state += 2147483646
	end
	-- (this generator's FIRST draw barely moves from one seed to the next: for every seed under about a thousand the
	-- square sat a tenth west of the middle, the first house wore the second wall colour, and seeds 1 to 12 twisted a
	-- bent town the same way - a fresh reader, 2026-11-13. Two draws are thrown away before any is used.)
	state = (state * 48271) % 2147483647
	state = (state * 48271) % 2147483647
	return function()
		state = (state * 48271) % 2147483647
		return state / 2147483647
	end
end

local function pair(v: any, fallback: { number }, what: string?, complain: ((string, string) -> ())?): { number }
	if type(v) == "table" and type(v[1]) == "number" and type(v[2]) == "number" then
		return { v[1], v[2] }
	end
	if v ~= nil and what and complain then
		-- (a value given wrong is said: never swapped for the default in silence)
		complain(
			"error",
			`{what} needs two numbers [a, b] (got {if type(v) == "table" then `a list of {#v}` else tostring(v)})`
		)
	end
	return { fallback[1], fallback[2] }
end

-- a street's strip on the ground
function Town.strip(s: Street): Rect
	if s.axis == "z" then
		return { x0 = s.at - s.width / 2, x1 = s.at + s.width / 2, z0 = s.from, z1 = s.to }
	end
	return { x0 = s.from, x1 = s.to, z0 = s.at - s.width / 2, z1 = s.at + s.width / 2 }
end

-- two rectangles share ground or an edge longer than `least` (a corner touch is no connection)
local function touch(a: Rect, b: Rect, least: number): boolean
	local ox = math.min(a.x1, b.x1) - math.max(a.x0, b.x0)
	local oz = math.min(a.z1, b.z1) - math.max(a.z0, b.z0)
	return (ox > least and oz > -0.01) or (oz > least and ox > -0.01)
end
Town.touch = touch

-- a frontage of length `len` cut into lots whose widths are whole `grid` steps inside [lo, hi] and sum to `len`
-- exactly (a terrace has no leftover slit). A length no count of such lots makes (shorter than lo, or between two
-- counts) gives its last lot the odd remainder: one house of an odd size, never a gap.
function Town.cut(len: number, lo: number, hi: number, rnd: () -> number, grid: number?): { number }
	local g = grid or 1
	local n = math.max(1, math.floor(len / ((lo + hi) / 2) + 0.5))
	while n > 1 and n * lo > len + 1e-6 do
		n -= 1
	end
	while n * hi < len - 1e-6 do
		n += 1
	end
	local out = table.create(n, lo)
	if n * lo > len + 1e-6 then
		-- no count fits (n lots at their least are already too long): fewer lots, the last one takes what is left
		n = math.max(1, n - 1)
		out = table.create(n, lo)
		out[n] = len - (n - 1) * lo
		return out
	end
	-- hand the rest out a grid step at a time to lots that still have room
	local rest = len - n * lo
	while rest > 1e-6 do
		local step = math.min(g, rest)
		-- the lot the dice name, or the next one after it that still has room (n * hi >= len: one always has)
		local k = math.min(n, math.floor(rnd() * n) + 1)
		local tried = 0
		while out[k] + step > hi + 1e-6 and tried < n do
			k = k % n + 1
			tried += 1
		end
		if tried >= n then
			out[k] += rest -- (no lot has a whole step's room left: the last sliver goes to one of them)
			break
		end
		out[k] += step
		rest -= step
	end
	return out
end

-- ---------------------------------------------------------------- the plan
-- ---------------------------------------------------------------- the bend
-- "bend": <degrees> (2026-11-13; the owner's method list: splines, procedural roads - and the audit's own line "every
-- street runs on one of two axes"). The plan above is cut on two axes; a bent town TWISTS it round the square: a
-- point at distance r from the square's middle is carried round by an angle that grows from nothing at the square
-- to about `bend` degrees at the town's edge (a third more or less by direction, by the seed). Streets that left
-- the square straight now curve away from it; cross lanes meet them off the square.
-- Houses do not shear: each BLOCK (its houses, yard walls and pavement) moves and turns as ONE rigid piece - to
-- where the twist carries its middle, by the twist's own rotation there (its angle plus half its shear). Rigid
-- blocks under a twist pinch some streets and open others, so the blocks are then SETTLED: every two blocks the
-- plan set across a street from each other are moved, a little at a time, until they stand at their nearest
-- exactly as far apart as planned - no nearer (no street is narrower than planned), and no farther than they must.
-- A street is its planned width at its narrowest and widens along its length by what its two sides' angles differ:
-- a funnel, as old streets are. (The first version spread every block from the square by one factor until the
-- worst pair cleared: a 12-stud lane came out 21 wide at its narrowest. Measured, and thrown away, 2026-11-13.)
-- (the most a town may bend. Measured over 56 towns: up to 8 degrees a street's middle line - what its width is
-- claimed along, where the town's own spawn pads and lamps stand - moves about a stud between points half a stud
-- apart; at 10 it steps 4 studs in places, at 12 5: the blocks round a crossing have turned too far against each
-- other for one line to run between them. A bigger bend needs lots laid along a curve, not turned blocks.)
Town.BEND_MAX = 8
-- (settling: BEND_PULL rounds that push and pull, then rounds that only push until no pair is nearer than planned.
-- A 960 x 960 town of 163 blocks settles in under 500; the first cap, 400 with half of them pulling, refused every
-- town that size at any bend and told the blueprint to "bend less" - a fresh reader, 2026-11-13)
Town.BEND_PULL = 100
Town.BEND_ROUNDS = 4000

-- the point (x, z) turned `deg` about (px, pz) the way a part's CFrame turns (kit/lib/world.luau World.turnPoint: a
-- spec holds the two to one another; this file cannot require that one)
local function turnPoint(x: number, z: number, px: number, pz: number, deg: number): (number, number)
	local c, sn = math.cos(math.rad(deg)), math.sin(math.rad(deg))
	local dx, dz = x - px, z - pz
	return px + c * dx + sn * dz, pz - sn * dx + c * dz
end
Town.turnPoint = turnPoint

-- a rect moved as a rigid piece: turned `deg` about its own middle, its middle set at (cx, cz); corners in the
-- order NW, NE, SE, SW of the rect it was
local function quadOf(r: Rect, cx: number, cz: number, deg: number): { { number } }
	local ox, oz = (r.x0 + r.x1) / 2, (r.z0 + r.z1) / 2
	local out = {}
	for _, c in { { r.x0, r.z0 }, { r.x1, r.z0 }, { r.x1, r.z1 }, { r.x0, r.z1 } } do
		local x, z = turnPoint(c[1], c[2], ox, oz, deg)
		table.insert(out, { x + cx - ox, z + cz - oz })
	end
	return out
end
Town.quadOf = quadOf

local function pointSeg(px: number, pz: number, a: { number }, b: { number }): number
	local vx, vz = b[1] - a[1], b[2] - a[2]
	local t = math.clamp(((px - a[1]) * vx + (pz - a[2]) * vz) / math.max(vx * vx + vz * vz, 1e-12), 0, 1)
	return math.sqrt((px - a[1] - vx * t) ^ 2 + (pz - a[2] - vz * t) ^ 2)
end

-- how far apart two convex quads stand (0 = they touch or overlap), and the unit direction from the first to the
-- second along their nearest points (from middle to middle when they overlap)
function Town.quadsApart(a: { { number } }, b: { { number } }): (number, number, number)
	local apart = false
	for _, q in { a, b } do
		for i = 1, 4 do
			local p1, p2 = q[i], q[i % 4 + 1]
			local nx, nz = p2[2] - p1[2], -(p2[1] - p1[1]) -- an edge's normal: a line that could part the two
			local amin, amax, bmin, bmax = math.huge, -math.huge, math.huge, -math.huge
			for _, v in a do
				local d = v[1] * nx + v[2] * nz
				amin, amax = math.min(amin, d), math.max(amax, d)
			end
			for _, v in b do
				local d = v[1] * nx + v[2] * nz
				bmin, bmax = math.min(bmin, d), math.max(bmax, d)
			end
			if amax < bmin or bmax < amin then
				apart = true
			end
		end
	end
	if not apart then
		local ax, az = (a[1][1] + a[3][1]) / 2, (a[1][2] + a[3][2]) / 2
		local bx, bz = (b[1][1] + b[3][1]) / 2, (b[1][2] + b[3][2]) / 2
		local d = math.max(math.sqrt((bx - ax) ^ 2 + (bz - az) ^ 2), 1e-9)
		return 0, (bx - ax) / d, (bz - az) / d
	end
	-- (apart: the nearest points are a corner of one and a point of the other's edge)
	local best, ux, uz = math.huge, 0, 0
	local function try(px: number, pz: number, e1: { number }, e2: { number }, flip: number)
		local vx, vz = e2[1] - e1[1], e2[2] - e1[2]
		local t = math.clamp(((px - e1[1]) * vx + (pz - e1[2]) * vz) / math.max(vx * vx + vz * vz, 1e-12), 0, 1)
		local qx, qz = e1[1] + vx * t, e1[2] + vz * t
		local d = math.sqrt((px - qx) ^ 2 + (pz - qz) ^ 2)
		if d < best then
			best = d
			local n = math.max(d, 1e-9)
			ux, uz = flip * (qx - px) / n, flip * (qz - pz) / n
		end
	end
	for i = 1, 4 do
		for j = 1, 4 do
			try(a[i][1], a[i][2], b[j], b[j % 4 + 1], 1) -- a's corner to b's edge: toward b
			try(b[i][1], b[i][2], a[j], a[j % 4 + 1], -1) -- b's corner to a's edge: reversed, still a toward b
		end
	end
	return best, ux, uz
end

local function rectsApart(a: Rect, b: Rect): number
	local dx = math.max(a.x0 - b.x1, b.x0 - a.x1, 0)
	local dz = math.max(a.z0 - b.z1, b.z0 - a.z1, 0)
	return math.sqrt(dx * dx + dz * dz)
end

-- does the segment a-b cross the convex quad q (or start / end inside it)?
function Town.segmentHits(a: { number }, b: { number }, q: { { number } }): boolean
	local function side(p: { number }, u: { number }, v: { number }): number
		return (v[1] - u[1]) * (p[2] - u[2]) - (v[2] - u[2]) * (p[1] - u[1])
	end
	local function inside(pt: { number }): boolean
		local pos, neg = false, false
		for i = 1, 4 do
			local d = side(pt, q[i], q[i % 4 + 1])
			pos = pos or d > 1e-9
			neg = neg or d < -1e-9
		end
		return not (pos and neg)
	end
	if inside(a) or inside(b) then
		return true
	end
	for i = 1, 4 do
		local u, v = q[i], q[i % 4 + 1]
		local d1, d2 = side(a, u, v), side(b, u, v)
		local d3, d4 = side(u, a, b), side(v, a, b)
		if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)) then
			return true
		end
	end
	return false
end

-- the bend of a plan: the twist's field, each block's rigid move, the spread that keeps every street's width
function Town.bendOf(plan: any, deg: number, problem: (string, string) -> ()): any
	local S: Rect, A: Rect = plan.square, plan.area
	local cx, cz = (S.x0 + S.x1) / 2, (S.z0 + S.z1) / 2
	local r0 = math.min(S.x1 - S.x0, S.z1 - S.z0) / 2
	local r1 = 0
	for _, c in { { A.x0, A.z0 }, { A.x1, A.z0 }, { A.x1, A.z1 }, { A.x0, A.z1 } } do
		r1 = math.max(r1, math.sqrt((c[1] - cx) ^ 2 + (c[2] - cz) ^ 2))
	end
	local span = math.max(r1 - r0, 1)
	local rnd = lcg((plan.seed or 1) + 4801)
	local sign = if rnd() < 0.5 then -1 else 1
	local phase = rnd() * 2 * math.pi
	-- (the twist's angle at a point, and half its shear there: together a rigid piece's own turn), in degrees
	local function field(x: number, z: number): (number, number)
		local dx, dz = x - cx, z - cz
		local r = math.sqrt(dx * dx + dz * dz)
		local t = math.clamp((r - r0) / span, 0, 1)
		local amp = sign * deg * (1 + 0.3 * math.sin(2 * math.atan2(dz, dx) + phase))
		return amp * t * t * (3 - 2 * t), 0.5 * r * amp * 6 * t * (1 - t) / span
	end
	local bent: any = { deg = deg, cx = cx, cz = cz, sign = sign, blocks = {} }
	-- each block: turned by the twist's own rotation at its middle, set where the twist carries its middle
	for bi, B in plan.blocks do
		local bx, bz = (B.x0 + B.x1) / 2, (B.z0 + B.z1) / 2
		local phi, half = field(bx, bz)
		local px, pz = turnPoint(bx, bz, cx, cz, phi)
		bent.blocks[bi] = { ox = bx, oz = bz, x = px, z = pz, turn = phi + half, quad = quadOf(B, px, pz, phi + half) }
	end
	-- SETTLE. The pieces: every block, and the square's inside (its rect drawn in by SQUARE_IN studs: it does not
	-- move, and a block that fronts the square stays that far from it - on the square's edge, not in it). The
	-- pairs: every two pieces the plan set within a main street's width and a half of each other, with that
	-- distance. Each round moves the two blocks of a pair along the line of their nearest points by a share of how
	-- far their distance is from the plan's; then rounds that only push apart, until no pair stands nearer than
	-- planned.
	-- The square's four EDGES do not move: each is a strip drawn SQUARE_IN studs inside the square, and a block that
	-- fronts that edge stays SQUARE_IN from the strip - on the square's edge, not in it. (One rect drawn in for the
	-- whole square let a turned block's corner stand 0.6 studs inside: a rect's corner is round to a distance.)
	local SQUARE_IN = 6
	local fixed: { { rect: Rect, quad: { { number } } } } = {}
	for _, r in
		{
			{ x0 = S.x0, x1 = S.x1, z0 = S.z0 + SQUARE_IN, z1 = S.z0 + SQUARE_IN + 1 }, -- north edge
			{ x0 = S.x0, x1 = S.x1, z0 = S.z1 - SQUARE_IN - 1, z1 = S.z1 - SQUARE_IN }, -- south
			{ x0 = S.x0 + SQUARE_IN, x1 = S.x0 + SQUARE_IN + 1, z0 = S.z0, z1 = S.z1 }, -- west
			{ x0 = S.x1 - SQUARE_IN - 1, x1 = S.x1 - SQUARE_IN, z0 = S.z0, z1 = S.z1 }, -- east
		}
	do
		table.insert(fixed, { rect = r, quad = quadOf(r, (r.x0 + r.x1) / 2, (r.z0 + r.z1) / 2, 0) })
	end
	local reach = 0
	for _, st in plan.streets do
		reach = math.max(reach, st.width)
	end
	reach *= 1.5
	-- { block, other (a block; -k = the square's k-th edge), the planned distance, do they FACE each other }
	local near = {}
	for i = 1, #plan.blocks do
		local A2: Rect = plan.blocks[i]
		for j = i + 1, #plan.blocks do
			local B2: Rect = plan.blocks[j]
			local d0 = rectsApart(A2, B2)
			if d0 <= reach then
				-- (facing: across a street from each other, not corner to corner over a crossing)
				local facing = (A2.x0 < B2.x1 and B2.x0 < A2.x1) or (A2.z0 < B2.z1 and B2.z0 < A2.z1)
				table.insert(near, { i, j, d0, facing })
			end
		end
		for k, piece in fixed do
			local dS = rectsApart(A2, piece.rect)
			if dS <= SQUARE_IN + 0.01 then -- (only a block that fronts that edge of the square)
				table.insert(near, { i, -k, dS, false })
			end
		end
	end
	local function quadAt(i: number): { { number } }
		return if i < 0 then fixed[-i].quad else bent.blocks[i].quad
	end
	local function shift(i: number, dx: number, dz: number)
		if i < 0 then
			return
		end
		local blk = bent.blocks[i]
		blk.x += dx
		blk.z += dz
		blk.quad = quadOf(plan.blocks[i], blk.x, blk.z, blk.turn)
	end
	local settled, rounds = false, 0
	for round = 1, Town.BEND_ROUNDS do
		rounds = round
		local pushOnly = round > Town.BEND_PULL
		local worst = 0
		for _, pr in near do
			local d, ux, uz = Town.quadsApart(quadAt(pr[1]), quadAt(pr[2]))
			local e = d - pr[3] -- (under 0: nearer than planned)
			if e < 0 then
				worst = math.max(worst, -e)
			end
			if e < -1e-7 or (not pushOnly and e > 0.05) then
				-- (a fixed piece moves nothing: the block takes the whole step)
				local step = if e < 0 then e - 1e-4 else e * 0.5
				local whole = pr[2] < 0
				shift(pr[1], ux * step * (if whole then 1 else 0.5), uz * step * (if whole then 1 else 0.5))
				shift(pr[2], -ux * step * 0.5, -uz * step * 0.5)
			end
		end
		if pushOnly and worst <= 1e-6 then
			settled = true
			break
		end
	end
	bent.rounds = rounds
	if not settled then
		problem(
			"error",
			`bend {deg}: the town's {#plan.blocks} blocks did not settle to their streets' widths in {Town.BEND_ROUNDS} rounds (a fault of the kit's settling, not of the blueprint: put it on the board with this town's numbers; "bend": 0 builds it straight)`
		)
	end
	-- how much wider than planned the STREETS are at their narrowest, on average and at most (studs): over the
	-- blocks that face each other across a street (two blocks corner to corner over a crossing are no street)
	local sum, most, count = 0, 0, 0
	for _, pr in near do
		if pr[2] > 0 and pr[4] then
			local e = Town.quadsApart(quadAt(pr[1]), quadAt(pr[2])) - pr[3]
			sum += e
			most = math.max(most, e)
			count += 1
		end
	end
	bent.wider = { mean = if count > 0 then sum / count else 0, most = most }
	-- a point of block bi's own (a lot's corner, a yard wall's end), moved with its block
	function bent.place(bi: number, x: number, z: number): (number, number)
		local blk = bent.blocks[bi]
		local tx, tz = turnPoint(x, z, blk.ox, blk.oz, blk.turn)
		return tx + blk.x - blk.ox, tz + blk.z - blk.oz
	end
	-- where a point of the STREETS stands (a junction, a street's middle line): between where the blocks near it
	-- carry it, each weighed by how near it is - a block as near as the nearest counts whole, one WARP_FADE studs
	-- farther not at all, smoothly between. In the middle of a street its two sides count alike (the middle of the
	-- bent street); at a crossing all four corners. The weights change smoothly along a street, so its line does
	-- not jump. (The first version took the plain mean of the blocks within 2 studs of the nearest: where that set
	-- changed, the line jumped up to 18 studs and at bend 12 passed through houses - a fresh reader, 2026-11-13.)
	local WARP_FADE = 24
	function bent.warp(x: number, z: number): (number, number)
		local least = math.huge
		local ds = table.create(#plan.blocks)
		for bi, B in plan.blocks do
			local dx = math.max(B.x0 - x, x - B.x1, 0)
			local dz = math.max(B.z0 - z, z - B.z1, 0)
			ds[bi] = math.sqrt(dx * dx + dz * dz)
			least = math.min(least, ds[bi])
		end
		local sx, sz, n = 0, 0, 0
		for bi in plan.blocks do
			local w = 1 - (ds[bi] - least) / WARP_FADE
			if w > 0 then
				w = w * w
				local px, pz = bent.place(bi, x, z)
				sx, sz, n = sx + px * w, sz + pz * w, n + w
			end
		end
		local wx, wz = sx / n, sz / n
		-- ... and never in a block: where blocks round a crossing have turned far against each other, the mean can
		-- fall under a corner that has swung in. The point is moved out of any block it stands in or nearer than
		-- `clear` to (as near as the plan had it to its nearest block, 1.5 studs at most)
		local clear = math.min(least, 1.5)
		if clear > 0 then
			for bi in plan.blocks do
				if ds[bi] <= least + WARP_FADE then
					local q = bent.blocks[bi].quad
					local mx, mz = (q[1][1] + q[3][1]) / 2, (q[1][2] + q[3][2]) / 2
					local within, edgeD, enx, enz = true, -math.huge, 0, 0
					for i = 1, 4 do
						local a, b = q[i], q[i % 4 + 1]
						local nx, nz = b[2] - a[2], -(b[1] - a[1])
						local len = math.max(math.sqrt(nx * nx + nz * nz), 1e-9)
						nx, nz = nx / len, nz / len
						if (mx - a[1]) * nx + (mz - a[2]) * nz > 0 then -- (the normal that points away from the middle)
							nx, nz = -nx, -nz
						end
						local d = (wx - a[1]) * nx + (wz - a[2]) * nz
						if d > 0 then
							within = false
						end
						if d > edgeD then
							edgeD, enx, enz = d, nx, nz
						end
					end
					if within then
						wx, wz = wx + enx * (clear - edgeD), wz + enz * (clear - edgeD)
					else
						local best, px, pz = math.huge, wx, wz
						for i = 1, 4 do
							local a, b = q[i], q[i % 4 + 1]
							local vx, vz = b[1] - a[1], b[2] - a[2]
							local t = math.clamp(
								((wx - a[1]) * vx + (wz - a[2]) * vz) / math.max(vx * vx + vz * vz, 1e-12),
								0,
								1
							)
							local ex, ez = a[1] + vx * t, a[2] + vz * t
							local d = math.sqrt((wx - ex) ^ 2 + (wz - ez) ^ 2)
							if d < best then
								best, px, pz = d, ex, ez
							end
						end
						if best < clear and best > 1e-9 then
							wx, wz = px + (wx - px) / best * clear, pz + (wz - pz) / best * clear
						end
					end
				end
			end
		end
		return wx, wz
	end
	return bent
end

-- where the town's own spawn pads stand: inside the main gate, in pairs across the main street's middle line, the
-- first pair 10 studs in and each next pair 8 farther - as the town stands (bent or straight). {} with no main street.
function Town.spawnSpots(plan: any, count: number): { { number } }
	local street = nil
	for _, st in plan.streets do
		if st.gate == plan.mainGate and st.rank == "main" then
			street = st
		end
	end
	if not street or count < 1 then
		return {}
	end
	-- the street's middle line walked from its gate end (the end farther from the square), a point every 2 studs
	local n = math.max(2, math.ceil((street.to - street.from) / 2))
	local line = {}
	for i = 0, n do
		local t = street.from + (street.to - street.from) * i / n
		local x, z = if street.axis == "z" then street.at else t, if street.axis == "z" then t else street.at
		if plan.bent then
			x, z = plan.bent.warp(x, z)
		end
		table.insert(line, { x, z })
	end
	local S: Rect = plan.square
	local sx, sz = (S.x0 + S.x1) / 2, (S.z0 + S.z1) / 2
	if (line[1][1] - sx) ^ 2 + (line[1][2] - sz) ^ 2 < (line[#line][1] - sx) ^ 2 + (line[#line][2] - sz) ^ 2 then
		local flipped = {}
		for i = #line, 1, -1 do
			table.insert(flipped, line[i])
		end
		line = flipped
	end
	local out = {}
	for k = 1, count do
		local row = math.floor((k - 1) / 2)
		local at = math.min(#line - 1, 1 + math.floor((10 + 8 * row) / 2 + 0.5))
		local a, b = line[at], line[at + 1]
		local dx, dz = b[1] - a[1], b[2] - a[2]
		local len = math.max(math.sqrt(dx * dx + dz * dz), 1e-9)
		-- (one pad stands on the line; a pair stands 4 studs either side of it)
		local side = if count == 1 then 0 elseif k % 2 == 1 then -4 else 4
		table.insert(out, { a[1] - dz / len * side, a[2] + dx / len * side })
	end
	return out
end

-- A TOWN ON A SLOPE (the owner's method list: "Vertical level design", "Terracing"; the audit's rank 6, levels).
-- The ground is one hillside: it rises `rise` studs in 100 toward one side. What stands on it:
--   * the GROUND is tilted plates - streets, the square, each block's pavement and yards - cut round the houses,
--     so no ground rises through a house's floor;
--   * each HOUSE stands level, its floor at the height of the street at its own front door: houses step up a
--     street house by house, as on a hill. Its uphill walls hold the ground back; where the ground falls away
--     below its floor a PLINTH (a foundation course under its walls, in their planes) carries it;
--   * a yard wall, a lamp, a stall, a woodpile and a spawn pad stand at the ground's height where they are (a wall
--     on its lower end, its top level, its gate's opening kept whole); a street's claim says its floor's height
--     at each end, and kit world check measures its width from the ground under each sample.
-- SLOPE_MOST 6: a house 24 studs deep then holds at most a stud and a half of ground at its back.
Town.SLOPE_MOST = 6
-- the ground's height over the town's own level at (x, z): 0 at the middle of the area
function Town.groundAt(plan: any, x: number, z: number): number
	local sl = plan.slope
	if not sl then
		return 0
	end
	local A: Rect = plan.area
	local cx, cz = (A.x0 + A.x1) / 2, (A.z0 + A.z1) / 2
	local g = sl.rise / 100
	if sl.toward == "N" then
		return -g * (z - cz)
	elseif sl.toward == "S" then
		return g * (z - cz)
	elseif sl.toward == "E" then
		return g * (x - cx)
	end
	return -g * (x - cx)
end
-- where a house's front door meets the street: the middle of its lot's front line
function Town.doorPoint(lot: any): (number, number)
	local r: Rect = lot.rect
	if lot.front == "N" then
		return (r.x0 + r.x1) / 2, r.z0
	elseif lot.front == "S" then
		return (r.x0 + r.x1) / 2, r.z1
	elseif lot.front == "W" then
		return r.x0, (r.z0 + r.z1) / 2
	end
	return r.x1, (r.z0 + r.z1) / 2
end
-- the ground of a town on a slope, cut round the houses: { { rect, class = "street" | "square" | "block" } }, no
-- two overlapping, together the whole area less every house's lot. (Cells between every edge of the area, the
-- square, the blocks and the lots; a row's cells of one class joined, then rows alike joined downward.)
function Town.groundPlates(plan: any): { any }
	local A: Rect, S: Rect = plan.area, plan.square
	local xs: { number }, zs: { number } = {}, {}
	local seenX: { [number]: boolean }, seenZ: { [number]: boolean } = {}, {}
	local function edges(r: Rect)
		for _, x in { r.x0, r.x1 } do
			if not seenX[x] and x >= A.x0 and x <= A.x1 then
				seenX[x] = true
				table.insert(xs, x)
			end
		end
		for _, z in { r.z0, r.z1 } do
			if not seenZ[z] and z >= A.z0 and z <= A.z1 then
				seenZ[z] = true
				table.insert(zs, z)
			end
		end
	end
	-- a house's own floor slab: its lot less half the gap and half a wall all round (the building's footprint). The
	-- ground reaches under the walls to that slab - under the door too, or a body would step over a gap there
	local slabs: { Rect } = {}
	local inset = ((plan.gap or 0) + (plan.wall or 1)) / 2
	for _, lot in plan.lots do
		local r: Rect = lot.rect
		table.insert(slabs, { x0 = r.x0 + inset, x1 = r.x1 - inset, z0 = r.z0 + inset, z1 = r.z1 - inset })
	end
	edges(A)
	edges(S)
	for _, B in plan.blocks do
		edges(B)
	end
	for _, slab in slabs do
		edges(slab)
	end
	table.sort(xs)
	table.sort(zs)
	local function inside(r: Rect, x: number, z: number): boolean
		return x > r.x0 and x < r.x1 and z > r.z0 and z < r.z1
	end
	local function classAt(x: number, z: number): string?
		for _, slab in slabs do
			if inside(slab, x, z) then
				return nil
			end
		end
		for _, B in plan.blocks do
			if inside(B, x, z) then
				return "block"
			end
		end
		if inside(S, x, z) then
			return "square"
		end
		return "street"
	end
	local out: { any } = {}
	local open: { [string]: any } = {} -- (a plate still growing downward, by its run and class)
	for j = 1, #zs - 1 do
		local z0, z1 = zs[j], zs[j + 1]
		local nextOpen: { [string]: any } = {}
		local i = 1
		while i < #xs do
			local class = classAt((xs[i] + xs[i + 1]) / 2, (z0 + z1) / 2)
			local k = i
			while k + 1 < #xs and classAt((xs[k + 1] + xs[k + 2]) / 2, (z0 + z1) / 2) == class do
				k += 1
			end
			if class then
				local key = `{xs[i]}:{xs[k + 1]}:{class}`
				local plate = open[key]
				if plate and plate.rect.z1 == z0 then
					plate.rect.z1 = z1
				else
					plate = { rect = { x0 = xs[i], x1 = xs[k + 1], z0 = z0, z1 = z1 }, class = class }
					table.insert(out, plate)
				end
				nextOpen[key] = plate
			end
			i = k + 1
		end
		open = nextOpen
	end
	-- a plate that lies under a house's wall (between its footprint and the walls' outer plane: the plinth's outline)
	-- ends Town.INTO inside that plane, so its end face lies inside the house's plinth. Ended IN the plane, the
	-- ground's edge (Slate) and the plinth / wall (Brick, Concrete) lay in one plane and flickered - 220 pairs in the
	-- sloped town's fixture (kit world check's z-fighting error; the fresh review of card my7f). The plate outside
	-- keeps its end, pressed face to face on the plinth (two faces facing each other: nothing flickers), and the
	-- sliver between the two lies inside the plinth.
	local half = (plan.wall or 1) / 2
	for _, plate in out do
		local r: Rect = plate.rect
		local w0, w1, n0, n1 = false, false, false, false -- (each end pulled back once, however many houses it is under)
		for _, f in slabs do
			local g = { x0 = f.x0 - half, x1 = f.x1 + half, z0 = f.z0 - half, z1 = f.z1 + half }
			local acrossZ = r.z0 < g.z1 - 1e-6 and g.z0 < r.z1 - 1e-6
			local acrossX = r.x0 < g.x1 - 1e-6 and g.x0 < r.x1 - 1e-6
			w0 = w0 or (acrossZ and math.abs(r.x0 - g.x0) < 1e-6)
			w1 = w1 or (acrossZ and math.abs(r.x1 - g.x1) < 1e-6)
			n0 = n0 or (acrossX and math.abs(r.z0 - g.z0) < 1e-6)
			n1 = n1 or (acrossX and math.abs(r.z1 - g.z1) < 1e-6)
		end
		r.x0 += if w0 then Town.INTO else 0
		r.x1 -= if w1 then Town.INTO else 0
		r.z0 += if n0 then Town.INTO else 0
		r.z1 -= if n1 then Town.INTO else 0
	end
	return out
end

-- THINGS IN THE YARDS (the owner's method list: "Set dressing", "Environmental storytelling"; the audit's rank 7).
-- A block's yard is the strip between the backs of its rows. Only a yard a walker can ENTER is dressed (one with a
-- gated wall at an end, or a shut one the plan opened by a court in place of one house: `yd.way`; a yard nobody
-- enters is seen by nobody, its things would be parts for nothing),
-- and only one YARD_WIDE or wider between the backs. Along it, every YARD_STEP studs and never within YARD_END of
-- an end (the gate's way in stays clear), by turns: a WOODPILE against a house's back wall (one side, then the
-- other: 7.8 studs or more stay clear beside it), and a WASH LINE from one back wall to the facing one, over a
-- body's head. About a third of the places stay empty by the seed. A woodpile needs a house's back behind its
-- whole length, a wash line a house's back at both its ends.
-- -> { { kind = "pile" | "line", yard, block, x, z, alongX, side?, span? } } in the PLAN's coordinates
Town.YARD_WIDE = 10
Town.YARD_END = 8
Town.YARD_STEP = 12
Town.PILE_SIZE = { 5, 2 } -- (along the wall, out from it)
Town.LINE_MOST = 24 -- (the widest yard a wash line is strung across)
-- a yard's clear ground: its rect less the strips its own block's houses stand on. A house stands on the side its
-- FRONT is on (a W-fronted lot takes a strip off the yard's west), whatever its shape - the least of the four cuts
-- took the wrong side off wherever a side row's lot is narrower than it is deep (a fresh reader, 2026-11-14)
function Town.yardClear(plan: any, yd: any): Rect?
	local r: Rect = yd.rect
	local c = { x0 = r.x0, x1 = r.x1, z0 = r.z0, z1 = r.z1 }
	for _, lot in plan.lots do
		local l: Rect = lot.rect
		if
			lot.block == yd.block
			and l.x0 < r.x1 - 1e-6
			and l.x1 > r.x0 + 1e-6
			and l.z0 < r.z1 - 1e-6
			and l.z1 > r.z0 + 1e-6
		then
			if lot.front == "W" then
				c.x0 = math.max(c.x0, l.x1)
			elseif lot.front == "E" then
				c.x1 = math.min(c.x1, l.x0)
			elseif lot.front == "N" then
				c.z0 = math.max(c.z0, l.z1)
			else
				c.z1 = math.min(c.z1, l.z0)
			end
		end
	end
	if c.x1 - c.x0 < 1e-6 or c.z1 - c.z0 < 1e-6 then
		return nil
	end
	return c
end

function Town.yardThings(plan: any): { any }
	local out = {}
	-- a house's wall stands half the plan's gap inside its lot's lines (with trim a stud; without, on the line), and
	-- with trim its corner posts stand out at each end of that wall: things keep POST clear of a wall's ends
	local inset = (plan.gap or 0) / 2
	local post = if inset > 0 then 1.5 else 0
	for yi, yd in plan.yards do
		local c = Town.yardClear(plan, yd)
		if not c or (#yd.open == 0 and not yd.way) then
			continue
		end
		local alongX = (c.x1 - c.x0) >= (c.z1 - c.z0)
		local lo, hi = if alongX then c.x0 else c.z0, if alongX then c.x1 else c.z1
		-- the two long sides: the lots' lines, and the houses' back WALLS just inside them
		local lineA, lineB = if alongX then c.z0 else c.x0, if alongX then c.z1 else c.x1
		local a, b = lineA - inset, lineB + inset -- (a wall stands INSIDE its lot: the yard is that much wider)
		if b - a < Town.YARD_WIDE - 1e-6 then
			continue
		end
		-- a house of this block stands with its back wall on that side, behind the whole of [t0, t1], at least
		-- `tall` studs high (a wash line is tied to a wall, not hung over a low roof)
		local function backed(line: number, t0: number, t1: number, tall: number): boolean
			for _, lot in plan.lots do
				local l: Rect = lot.rect
				if lot.block == yd.block then
					local l0, l1 = if alongX then l.x0 else l.z0, if alongX then l.x1 else l.z1
					local n0, n1 = if alongX then l.z0 else l.x0, if alongX then l.z1 else l.x1
					if
						(math.abs(n1 - line) < 1e-6 or math.abs(n0 - line) < 1e-6)
						and l0 + inset + post <= t0 + 1e-6
						and l1 - inset - post >= t1 - 1e-6
						and (lot.floors or 0) * (lot.floorHeight or 0) >= tall - 1e-6
					then
						return true
					end
				end
			end
			return false
		end
		local rnd = lcg((plan.seed or 1) + 7331 + yi * 131)
		local k = 0
		local t = lo + Town.YARD_END + Town.PILE_SIZE[1] / 2
		while t <= hi - Town.YARD_END - Town.PILE_SIZE[1] / 2 + 1e-6 do
			k += 1
			local gap = rnd() <= 0.33
			local shift = (rnd() - 0.5) * 3 -- (not on a ruler: up to a stud and a half either way)
			local hang = { 0.2 + rnd() * 0.12, 0.62 + rnd() * 0.12 } -- (where a line's two sheets hang, along it)
			local at = math.clamp(t + shift, lo + Town.YARD_END + 2.5, hi - Town.YARD_END - 2.5)
			if not gap then
				if k % 2 == 1 then
					local side = if k % 4 == 1 then "a" else "b"
					if
						backed(
							if side == "a" then lineA else lineB,
							at - Town.PILE_SIZE[1] / 2,
							at + Town.PILE_SIZE[1] / 2,
							3
						)
					then
						-- (its back a fifth of a stud off the house's wall)
						local off = if side == "a"
							then a + 0.2 + Town.PILE_SIZE[2] / 2
							else b - 0.2 - Town.PILE_SIZE[2] / 2
						table.insert(out, {
							kind = "pile",
							yard = yi,
							block = yd.block,
							x = if alongX then at else off,
							z = if alongX then off else at,
							alongX = alongX,
							side = side,
						})
					end
				elseif
					b - a <= Town.LINE_MOST + 1e-6 -- (a cord across a wide court would sag to the ground: none there)
					and backed(lineA, at - 0.5, at + 0.5, 11)
					and backed(lineB, at - 0.5, at + 0.5, 11)
				then
					table.insert(out, {
						kind = "line",
						yard = yi,
						block = yd.block,
						x = if alongX then at else (a + b) / 2,
						z = if alongX then (a + b) / 2 else at,
						alongX = alongX,
						span = b - a, -- (from one back wall's face to the facing one's)
						hang = hang,
					})
				end
			end
			t += Town.YARD_STEP
		end
	end
	return out
end

-- the shut yards the plan opened: { { yard, block, front, rect, gate = { x, z } } } - the gate's middle AS BUILT
function Town.yardWays(plan: any): { any }
	local out = {}
	for yi, yd in plan.yards do
		local way = yd.way
		if way then
			local r: Rect = way.rect
			local gx, gz
			if way.front == "W" or way.front == "E" then
				gx, gz = if way.front == "W" then r.x0 + 0.5 else r.x1 - 0.5, (r.z0 + r.z1) / 2
			else
				gx, gz = (r.x0 + r.x1) / 2, if way.front == "N" then r.z0 + 0.5 else r.z1 - 0.5
			end
			if plan.bent then
				gx, gz = plan.bent.place(yd.block, gx, gz)
			end
			table.insert(out, { yard = yi, block = yd.block, front = way.front, rect = r, gate = { x = gx, z = gz } })
		end
	end
	return out
end

-- ... as BUILT: where each thing stands and how it is turned (a bent town moves a yard with its block)
function Town.yardThingsBuilt(plan: any): { any }
	local out = {}
	for _, th in Town.yardThings(plan) do
		local copy = table.clone(th)
		copy.turn = 0
		if plan.bent then
			copy.x, copy.z = plan.bent.place(th.block, th.x, th.z)
			copy.turn = plan.bent.blocks[th.block].turn
		end
		table.insert(out, copy)
	end
	return out
end

-- A MARKET ON THE SQUARE (the owner's method list: "Set dressing", "Environmental storytelling"; the audit's rank
-- 7, dressing with a reason). Stalls stand where a market stands: in rows on the square - and they keep clear what
-- the square is FOR: the line of sight from the main gate to the landmark (a lane STALL_VIEW wide either side of
-- it), the mouth of every street (STALL_MOUTH round each), and the square's edge where the house doors are
-- (STALL_EDGE). Every distance is to the stall's nearest CORNER as it stands turned (STALL_REACH: its half diagonal,
-- 4.72, rounded up), a mouth's from the street's opening (its middle and half its width). Rows 16 apart, stalls 14 apart along a row, about a third left out by the seed (a market has gaps),
-- each stall turned a few degrees. -> { { x, z, turn } }; a stall is STALL_SIZE on the ground.
Town.STALL_SIZE = { 8, 5 }
Town.STALL_VIEW = 10
Town.STALL_MOUTH = 16
Town.STALL_EDGE = 10
Town.STALL_REACH = 5
-- the line a walker looks along from the main gate: from the main street's end on the square to the landmark's
-- front AS BUILT (a bent town moves that front: the same line the plan page draws)
function Town.viewLine(plan: any): { { number } }?
	if type(plan.view) ~= "table" or type(plan.view.at) ~= "table" then
		return nil
	end
	local S: Rect = plan.square
	local sx, sz = (S.x0 + S.x1) / 2, (S.z0 + S.z1) / 2
	local best, from = math.huge, nil
	for _, st in plan.streets do
		if st.gate == plan.mainGate and st.rank == "main" then
			-- (the street's end on the square: the one nearer the square's middle)
			for _, t in { st.from, st.to } do
				local x, z = if st.axis == "z" then st.at else t, if st.axis == "z" then t else st.at
				local d = (x - sx) ^ 2 + (z - sz) ^ 2
				if d < best then
					best, from = d, { x, z }
				end
			end
		end
	end
	if not from then
		return nil
	end
	local at = { plan.view.at[1], plan.view.at[2] }
	if plan.bent then
		at = { plan.bent.warp(at[1], at[2]) }
	end
	return { from, at }
end
function Town.stallSpots(plan: any): { any }
	local S: Rect = plan.square
	local g = Town.graph(plan)
	-- a mouth: where a street enters the square, with half that street's width (its opening)
	local mouths = {}
	local function mouth(nd: any)
		local half = 0
		for _, st in plan.streets do
			local r = Town.strip(st)
			if nd.x >= r.x0 - 1 and nd.x <= r.x1 + 1 and nd.z >= r.z0 - 1 and nd.z <= r.z1 + 1 then
				half = math.max(half, st.width / 2)
			end
		end
		table.insert(mouths, { x = nd.px, z = nd.pz, half = half })
	end
	for _, ed in g.edges do
		if ed.a == g.square then
			mouth(g.nodes[ed.b])
		elseif ed.b == g.square then
			mouth(g.nodes[ed.a])
		end
	end
	local view = Town.viewLine(plan)
	local rnd = lcg((plan.seed or 1) + 6151)
	local out = {}
	local places = {}
	-- (a stall turned its most, 6 degrees, reaches 4.24 by 2.91 from its middle: 4.25 and 2.95 keep its corners in)
	local x0, x1 = S.x0 + Town.STALL_EDGE + 4.25, S.x1 - Town.STALL_EDGE - 4.25
	local z0, z1 = S.z0 + Town.STALL_EDGE + 2.95, S.z1 - Town.STALL_EDGE - 2.95
	local z = z0
	while z <= z1 + 1e-6 do
		local x = x0
		while x <= x1 + 1e-6 do
			local gap = rnd() <= 0.33 -- (a market has gaps: about a third of its places stay empty)
			local keep = true
			local turn = (rnd() - 0.5) * 12
			local reach = Town.STALL_REACH
			if view and pointSeg(x, z, view[1], view[2]) < Town.STALL_VIEW + reach then
				keep = false
			end
			for _, nd in mouths do
				if (nd.x - x) ^ 2 + (nd.z - z) ^ 2 < (Town.STALL_MOUTH + reach + nd.half) ^ 2 then
					keep = false
				end
			end
			if keep then
				table.insert(places, { x = x, z = z, turn = turn, gap = gap })
			end
			x += 14
		end
		z += 16
	end
	for _, place in places do
		if not place.gap then
			table.insert(out, { x = place.x, z = place.z, turn = place.turn })
		end
	end
	if #out < 2 then
		-- (the seed's gaps never empty a market: a small square keeps every place the rules leave it)
		out = {}
		for _, place in places do
			table.insert(out, { x = place.x, z = place.z, turn = place.turn })
		end
	end
	return out
end

-- LAMPS WITH A REASON (the owner on the District, 2026-10-28: "I hate the fact that you added a lamp everywhere").
-- A town's lamps stand only where a walker decides something: at each GATE, at each MOUTH of the square (where a
-- street enters it), and at a CROSSING (four ways or more) that no lamp already lights - in the towns the plan
-- makes today every crossing is the one just inside a gate, so in practice: gates and mouths, 4 to 8 lamps.
-- Not at every junction: measured over 30 towns that is 14 to 41 lamps, and in 18 of the 30 the middle lamp has 3 or
-- more others within 80 studs - the crowd kit world check fails (worldcheck.py lamp_density).
-- Each lamp stands at the foot of a house corner near its node, a stud and a half out into the street, its arm
-- toward the junction. -> { { x, z, toX, toZ, why, nodeX, nodeZ } }
Town.LAMP_APART = 24 -- studs: two lamps never stand nearer than this (one light's reach is 22)
Town.LAMP_REACH = 40 -- studs: a lamp stands at a house corner this near its gate / mouth / crossing, or not at all
Town.INTO = 0.08 -- studs: a sloped town's ground under a house's wall ends this far inside its outer plane
Town.LAMP_LIGHT = 22 -- studs: one lamp's light reaches this far: a crossing a lamp stands this near is lit already
function Town.lampSpots(plan: any): { any }
	local g = Town.graph(plan)
	local onSquare: { [number]: boolean } = {}
	for _, ed in g.edges do
		if ed.a == g.square then
			onSquare[ed.b] = true
		elseif ed.b == g.square then
			onSquare[ed.a] = true
		end
	end
	local corners = {}
	for _, lot in plan.lots do
		for _, c in Town.lotQuad(plan, lot) do
			table.insert(corners, c)
		end
	end
	local out = {}
	-- (a gate first, then the square's mouths, then crossings: where two reasons meet - a crossing just inside a
	-- gate - ONE lamp stands, the first's; the first page drawn showed two on one house corner)
	local order = {}
	for _, want in { "gate", "mouth", "crossing" } do
		for i, nd in g.nodes do
			local why = if nd.kind == "gate"
				then "gate"
				elseif onSquare[i] and i ~= g.square then "mouth"
				elseif nd.kind == "junction" and nd.degree >= 4 then "crossing"
				else nil
			if why == want then
				table.insert(order, { nd = nd, why = why })
			end
		end
	end
	for _, entry in order do
		local nd, why = entry.nd, entry.why
		-- a CROSSING that a lamp already lights gets none. (It took "the next corner" as a mouth does: the crossing
		-- just inside a gate then set its lamp on the corner ACROSS the gate's street from the gate's own lamp - two
		-- posts face to face in a 32-stud street, which read 28 wide where the sheet wants 30: card mkmc.)
		local lit = false
		if why == "crossing" then
			for _, other in out do
				lit = lit or (other.x - nd.px) ^ 2 + (other.z - nd.pz) ^ 2 < Town.LAMP_LIGHT ^ 2
			end
		end
		-- the house corners near the node, nearest first: the lamp stands at the first that no other lamp already
		-- lights (a mouth whose own corner is taken stands at its next one - it lost its lamp altogether before)
		local near = {}
		for _, c in corners do
			local d = math.sqrt((c[1] - nd.px) ^ 2 + (c[2] - nd.pz) ^ 2)
			if d > 0.01 and d < Town.LAMP_REACH then
				table.insert(near, { d, c[1], c[2] })
			end
		end
		table.sort(near, function(p, q)
			return if p[1] ~= q[1] then p[1] < q[1] elseif p[2] ~= q[2] then p[2] < q[2] else p[3] < q[3]
		end)
		for _, c in if lit then {} else near do
			-- (a stud and a half from the corner toward the junction: off the house, at the street's edge)
			local ux, uz = (nd.px - c[2]) / c[1], (nd.pz - c[3]) / c[1]
			local x, z = c[2] + ux * 1.5, c[3] + uz * 1.5
			local taken = false
			for _, other in out do
				taken = taken or (other.x - x) ^ 2 + (other.z - z) ^ 2 < Town.LAMP_APART ^ 2
			end
			if not taken then
				table.insert(out, { x = x, z = z, toX = ux, toZ = uz, why = why, nodeX = nd.px, nodeZ = nd.pz })
				break
			end
		end
	end
	-- ... and the town's lamps must pass the owner's own measure (kit/world/worldcheck.py lamp_density: with 6 or
	-- more lamps, the middle one has fewer than 3 others within 80 studs). A small square has its four mouths and
	-- a gate all within 80 studs of each other: lamps are taken away, the last reason first (never a gate's),
	-- until the town is no "lamp everywhere". (A fresh reader found 2 towns in 1,008 whose own lamps failed it.)
	local function crowded(): boolean
		if #out < 6 then
			return false
		end
		local counts = {}
		for i, p1 in out do
			local n = 0
			for j, p2 in out do
				if i ~= j and (p1.x - p2.x) ^ 2 + (p1.z - p2.z) ^ 2 <= 80 * 80 then
					n += 1
				end
			end
			table.insert(counts, n)
		end
		table.sort(counts)
		local mid = if #counts % 2 == 1
			then counts[(#counts + 1) / 2]
			else (counts[#counts / 2] + counts[#counts / 2 + 1]) / 2
		return mid >= 3
	end
	while crowded() do
		local drop = nil
		for i = #out, 1, -1 do
			if out[i].why ~= "gate" then
				drop = i
				break
			end
		end
		if not drop then
			break
		end
		table.remove(out, drop)
	end
	return out
end

-- a lot's four corners as the town stands (NW, NE, SE, SW of its rect; moved with its block when the town is bent)
function Town.lotQuad(plan: any, lot: any): { { number } }
	local r: Rect = lot.rect
	local out = {}
	for _, c in { { r.x0, r.z0 }, { r.x1, r.z0 }, { r.x1, r.z1 }, { r.x0, r.z1 } } do
		if plan.bent then
			local x, z = plan.bent.place(lot.block, c[1], c[2])
			table.insert(out, { x, z })
		else
			table.insert(out, c)
		end
	end
	return out
end

function Town.plan(spec: any): any
	local D = Town.DEFAULTS
	local issues: { { severity: string, message: string } } = {}
	local function problem(severity: string, message: string)
		table.insert(issues, { severity = severity, message = message })
	end
	local rnd = lcg(spec.seed or 1)
	local c = if type(spec.center) == "table" then spec.center else { 0, 0, 0 }
	local area = pair(spec.area, D.area, "area", problem)
	local sw = spec.streets or {}
	local W =
		{ main = sw.main or D.streets.main, lane = sw.lane or D.streets.lane, alley = sw.alley or D.streets.alley }
	local lots = spec.lots or {}
	local lotW = pair(lots.width, D.lots.width, "lots.width", problem)
	local lotD = pair(lots.depth, D.lots.depth, "lots.depth", problem)
	local yard = lots.yard or D.lots.yard
	local houseSpec = if type(spec.house) == "table" then spec.house else {}
	local wallT = houseSpec.thickness or 1
	local gapT = spec.gap
		or (if houseSpec.trim or (type(spec.mats) == "table" and spec.mats.trim) then wallT + 1 else 0)
	-- a house's door stands in a BAY of its front: the building generator gives a wall floor((length - 4) / every)
	-- bays, so a front under every + 4 has none - no door, no window, a sealed box. A lot is never narrower than
	-- that front plus its wall and gap: the least width is raised to it when the blueprint did not type one, and a
	-- typed one too small is an error (with trim a 16-stud lot left a 13-stud front)
	local winEvery = (type(houseSpec.windows) == "table" and houseSpec.windows.every) or 10
	local needFront = winEvery + 4
	local needLot = needFront + wallT + gapT
	if lotW[1] < needLot then
		local fits = math.ceil(needLot / (spec.grid or D.grid) - 1e-9) * (spec.grid or D.grid)
		if type(lots.width) == "table" then
			problem(
				"error",
				`lots.width [{lotW[1]}, {lotW[2]}] leaves a house a {lotW[1] - wallT - gapT}-stud front: no bay for its door (a window every {winEvery} needs {needFront}; with a {wallT}-stud wall{if gapT
						> 0
					then ` and a {gapT}-stud gap`
					else ""} that is a lot of {fits})`
			)
		end
		lotW = { fits, math.max(lotW[2], fits) }
	end
	-- a row (or what a landmark leaves of one) shorter than this holds no house
	local leastRow = math.max(lotW[1] * 0.75, needLot)
	local blk = pair(spec.block, D.block, "block", problem)
	local ring = spec.ring ~= false
	local gates: { [string]: boolean } = {}
	local gateOrder: { string } = {}
	for _, g in if type(spec.gates) == "table" then spec.gates else { "S" } do
		if g == "N" or g == "E" or g == "S" or g == "W" then
			if not gates[g] then
				gates[g] = true
				table.insert(gateOrder, g)
			end
		else
			problem("error", `gates are sides "N" | "E" | "S" | "W" (got "{tostring(g)}")`)
		end
	end
	if spec.skins ~= nil and (type(spec.skins) ~= "string" or spec.skins == "") then
		problem("error", `"skins" is the name its house meshes start with (a word, got {tostring(spec.skins)})`)
	end
	-- "facade": true - the houses are put together from MODULES by a grammar (kit/lib/worldfacade.luau): 5 a storey
	-- height and 3 for the town, named "<skins>_<kind>...", in place of one whole mesh a house type; false - one
	-- whole mesh a type, meant
	if spec.facade ~= nil and type(spec.facade) ~= "boolean" then
		problem(
			"error",
			`"facade" is true (the houses are made of modules by rule: 5 meshes a storey height and 3 for the town) or false (one whole mesh a house type) (got {tostring(
				spec.facade
			)})`
		)
	elseif spec.facade == true and (type(spec.skins) ~= "string" or spec.skins == "") then
		problem("error", '"facade": true needs "skins": "<prefix>" (the name its modules start with)')
	end
	for _, need in { "street", "wall", "roof" } do
		if type(spec.mats) ~= "table" or type(spec.mats[need]) ~= "string" then
			problem(
				"error",
				`"mats" needs "{need}" (a palette entry; also: square, block, wallAlt, yard, trim, glass, landmark)`
			)
		end
	end
	if #gateOrder == 0 then
		problem("error", "a town needs at least one gate (the side its main street enters by)")
		gates.S = true
		gateOrder = { "S" }
	end
	local G = spec.grid or D.grid
	local function snap(v: number): number
		return math.floor(v / G + 0.5) * G
	end
	for name, v in { main = W.main, lane = W.lane, alley = W.alley, ["area width"] = area[1], ["area depth"] = area[2] } do
		if math.abs(v / G - math.floor(v / G + 0.5)) > 1e-6 then
			problem(
				"error",
				`{name} {v} is not a whole number of {G}-stud grid steps (every line of a town lies on its grid)`
			)
		end
	end
	local X0, X1 = snap(c[1] - area[1] / 2), snap(c[1] - area[1] / 2) + area[1]
	local Z0, Z1 = snap(c[3] - area[2] / 2), snap(c[3] - area[2] / 2) + area[2]
	local rw = if ring then W.lane else 0
	local I: Rect = { x0 = X0 + rw, x1 = X1 - rw, z0 = Z0 + rw, z1 = Z1 - rw } -- inside the wall street

	-- the square: where the blueprint says, or off the middle by the seed (a square dead centre is a diagram)
	local sq = spec.square or {}
	local ss = pair(sq.size, D.square, "square.size", problem)
	local scx, scz
	if type(sq.at) == "table" then
		scx, scz = sq.at[1], sq.at[2]
	else
		scx = c[1] + (rnd() - 0.5) * 0.24 * (I.x1 - I.x0)
		scz = c[3] + (rnd() - 0.5) * 0.24 * (I.z1 - I.z0)
	end
	-- its edges on the grid
	local sx0, sz0 = snap(scx - ss[1] / 2), snap(scz - ss[2] / 2)
	local S: Rect = { x0 = sx0, x1 = sx0 + snap(ss[1]), z0 = sz0, z1 = sz0 + snap(ss[2]) }
	-- room for a row of houses on every side of it
	local least = lotD[1]
	if S.x0 - I.x0 < least or I.x1 - S.x1 < least or S.z0 - I.z0 < least or I.z1 - S.z1 < least then
		if type(sq.at) == "table" then
			problem(
				"error",
				`the square at ({scx}, {scz}) leaves no room for a row of houses ({least} studs) on every side inside the {area[1]} x {area[2]} area`
			)
		end
		-- pull it back inside (an area too small for any square is said below)
		local dx = math.max(0, I.x0 + least - S.x0) - math.max(0, S.x1 - (I.x1 - least))
		local dz = math.max(0, I.z0 + least - S.z0) - math.max(0, S.z1 - (I.z1 - least))
		S = { x0 = S.x0 + dx, x1 = S.x1 + dx, z0 = S.z0 + dz, z1 = S.z1 + dz }
	end
	if I.x1 - I.x0 < ss[1] + 2 * least or I.z1 - I.z0 < ss[2] + 2 * least then
		problem(
			"error",
			`the area {area[1]} x {area[2]} is too small for a {ss[1]} x {ss[2]} square with houses round it (needs {math.ceil(
				ss[1] + 2 * (least + rw)
			)} x {math.ceil(ss[2] + 2 * (least + rw))})`
		)
		return {
			issues = issues,
			streets = {},
			blocks = {},
			lots = {},
			square = S,
			area = { x0 = X0, x1 = X1, z0 = Z0, z1 = Z1 },
		}
	end

	-- the four arms, pinwheel-wise: each leaves the square along one edge, a main street to a gate, a lane otherwise
	local function armWidth(side: string): (number, string)
		return if gates[side] then W.main else W.lane, if gates[side] then "main" else "lane"
	end
	local wN, rN = armWidth("N")
	local wE, rE = armWidth("E")
	local wS, rS = armWidth("S")
	local wW, rW = armWidth("W")
	local streets: { Street } = {
		{
			name = "North street",
			rank = rN,
			axis = "z",
			at = S.x0 + wN / 2,
			from = if gates.N then Z0 else I.z0,
			to = S.z0,
			width = wN,
			gate = if gates.N then "N" else nil,
		},
		{
			name = "East street",
			rank = rE,
			axis = "x",
			at = S.z0 + wE / 2,
			from = S.x1,
			to = if gates.E then X1 else I.x1,
			width = wE,
			gate = if gates.E then "E" else nil,
		},
		{
			name = "South street",
			rank = rS,
			axis = "z",
			at = S.x1 - wS / 2,
			from = S.z1,
			to = if gates.S then Z1 else I.z1,
			width = wS,
			gate = if gates.S then "S" else nil,
		},
		{
			name = "West street",
			rank = rW,
			axis = "x",
			at = S.z1 - wW / 2,
			from = if gates.W then X0 else I.x0,
			to = S.x0,
			width = wW,
			gate = if gates.W then "W" else nil,
		},
	}
	if ring then
		table.insert(
			streets,
			{ name = "Wall street N", rank = "lane", axis = "x", at = Z0 + rw / 2, from = X0, to = X1, width = rw }
		)
		table.insert(
			streets,
			{ name = "Wall street S", rank = "lane", axis = "x", at = Z1 - rw / 2, from = X0, to = X1, width = rw }
		)
		table.insert(
			streets,
			{ name = "Wall street W", rank = "lane", axis = "z", at = X0 + rw / 2, from = I.z0, to = I.z1, width = rw }
		)
		table.insert(
			streets,
			{ name = "Wall street E", rank = "lane", axis = "z", at = X1 - rw / 2, from = I.z0, to = I.z1, width = rw }
		)
	end
	-- the four quarters the arms leave
	local quarters: { Rect } = {
		{ x0 = I.x0, x1 = S.x0, z0 = I.z0, z1 = S.z1 - wW }, -- NW
		{ x0 = S.x0 + wN, x1 = I.x1, z0 = I.z0, z1 = S.z0 }, -- NE
		{ x0 = S.x1, x1 = I.x1, z0 = S.z0 + wE, z1 = I.z1 }, -- SE
		{ x0 = I.x0, x1 = S.x1 - wS, z0 = S.z1, z1 = I.z1 }, -- SW
	}

	-- a quarter is cut by a lane, each half by alleys, until no block is longer than blk[2]. A cut ends on the streets
	-- round its piece (a T at both ends); it never opens onto the square, and never lines up with a street that ends on
	-- the other side of the same street (that would be a crossing: the start of a grid)
	local blocks: { Rect } = {}
	local lanes, alleys = 0, 0
	local function opensOnSquare(axis: string, at: number, w: number, from: number, to: number): boolean
		local lo, hi = at - w / 2, at + w / 2
		if axis == "z" then
			return hi > S.x0 and lo < S.x1 and (math.abs(from - S.z1) < 0.01 or math.abs(to - S.z0) < 0.01)
		end
		return hi > S.z0 and lo < S.z1 and (math.abs(from - S.x1) < 0.01 or math.abs(to - S.x0) < 0.01)
	end
	local function linesUp(axis: string, at: number, w: number, from: number, to: number): boolean
		for _, o in streets do
			if o.axis == axis and math.abs(o.at - at) < (o.width + w) / 2 + 6 then
				-- beyond one of this cut's ends, across a street's width
				if (o.from > to and o.from - to < W.main + 2) or (o.to < from and from - o.to < W.main + 2) then
					return true
				end
			end
		end
		return false
	end
	local function cut(R: Rect, depth: number)
		local w, d = R.x1 - R.x0, R.z1 - R.z0
		local long = math.max(w, d)
		local width = if depth == 0 then W.lane else W.alley
		if long <= blk[2] or long - width < 2 * blk[1] or depth > 6 then
			table.insert(blocks, R)
			return
		end
		local acrossX = w >= d -- the long side is X: the cut runs along Z
		local lo = if acrossX then R.x0 else R.z0
		local axis = if acrossX then "z" else "x"
		local from, to = if acrossX then R.z0 else R.x0, if acrossX then R.z1 else R.x1
		local at: number? = nil
		-- a piece houses fill: one through row, two rows back to back, or rows round a yard worth the name
		local function fills(v: number): boolean
			return v <= lotD[2] + 1e-6 or (v >= 2 * lotD[1] and v <= 2 * lotD[2] + 1e-6) or v >= 2 * lotD[1] + yard
		end
		for _ = 1, 16 do
			local f = 0.36 + 0.28 * rnd()
			-- the street's near edge on the grid (so both blocks it parts are whole grid steps)
			local try = snap(lo + long * f - width / 2) + width / 2
			local before, after = try - width / 2 - lo, lo + long - (try + width / 2)
			if
				before >= blk[1]
				and after >= blk[1]
				and not opensOnSquare(axis, try, width, from, to)
				and not linesUp(axis, try, width, from, to)
			then
				if fills(before) and fills(after) then
					at = try
					break
				end
				at = at or try -- (the first place that works, should none leave both pieces well filled)
			end
		end
		if not at then
			table.insert(blocks, R)
			return
		end
		if depth == 0 then
			lanes += 1
		else
			alleys += 1
		end
		table.insert(streets, {
			name = if depth == 0 then `Lane {lanes}` else `Alley {alleys}`,
			rank = if depth == 0 then "lane" else "alley",
			axis = axis,
			at = at,
			from = from,
			to = to,
			width = width,
		})
		if acrossX then
			cut({ x0 = R.x0, x1 = at - width / 2, z0 = R.z0, z1 = R.z1 }, depth + 1)
			cut({ x0 = at + width / 2, x1 = R.x1, z0 = R.z0, z1 = R.z1 }, depth + 1)
		else
			cut({ x0 = R.x0, x1 = R.x1, z0 = R.z0, z1 = at - width / 2 }, depth + 1)
			cut({ x0 = R.x0, x1 = R.x1, z0 = at + width / 2, z1 = R.z1 }, depth + 1)
		end
	end
	for _, q in quarters do
		if q.x1 - q.x0 >= lotD[1] and q.z1 - q.z0 >= lotD[1] then
			cut(q, 0)
		end
	end

	-- what a block's side faces: the square (4), a main street (3), a lane (2), an alley (1), nothing (0: the edge)
	local strips: { Rect } = {}
	for k, s in streets do
		strips[k] = Town.strip(s)
	end
	local function facing(side: Rect): number
		local best = 0
		if touch(side, S, 1) then
			best = Town.RANK.square
		end
		for k, s in streets do
			if touch(side, strips[k], 1) then
				best = math.max(best, Town.RANK[s.rank])
			end
		end
		return best
	end
	local function sideRect(B: Rect, side: string): Rect
		if side == "N" then
			return { x0 = B.x0, x1 = B.x1, z0 = B.z0, z1 = B.z0 }
		elseif side == "S" then
			return { x0 = B.x0, x1 = B.x1, z0 = B.z1, z1 = B.z1 }
		elseif side == "W" then
			return { x0 = B.x0, x1 = B.x0, z0 = B.z0, z1 = B.z1 }
		end
		return { x0 = B.x1, x1 = B.x1, z0 = B.z0, z1 = B.z1 }
	end

	-- the LANDMARK's place: where the first gate's street, carried on across the square, meets the square's far wall.
	-- Its lot is set out FIRST, its middle on that line of sight; the row is cut into houses either side of it.
	local main = gateOrder[1]
	local px, pz, want
	if main == "S" then
		px, pz, want = S.x1 - wS / 2, S.z0, "S"
	elseif main == "N" then
		px, pz, want = S.x0 + wN / 2, S.z1, "N"
	elseif main == "E" then
		px, pz, want = S.x0, S.z0 + wE / 2, "E"
	else
		px, pz, want = S.x1, S.z1 - wW / 2, "W"
	end
	local lmSpec = if type(spec.landmark) == "table" then spec.landmark else {}
	local lmWide = snap(lmSpec.width or math.max(2 * lotW[1], 40))

	-- the lots: terraces round each block's edge
	local allLots: { Lot } = {}
	local yards: { any } = {} -- { block, rect, open = { side, ... } }: the ground inside a block's rows
	local frontage, built = 0, 0
	local function row(
		bi: number,
		side: string,
		a: number,
		b: number,
		edge: number,
		depth: number,
		B: Rect,
		corners: boolean
	)
		-- lots along [a, b] on the block's `side`, `depth` deep from the edge line `edge`
		local len = b - a
		if len < leastRow then
			return
		end
		local widths: { number } = {}
		local landmarkAt: number? = nil -- (which of `widths` is the landmark's lot)
		local sight = if side == "S" or side == "N" then px else pz
		local wall = if side == "S" or side == "N" then pz else px
		if side == want and math.abs(edge - wall) < 0.01 and sight >= a - 0.01 and sight <= b + 0.01 then
			local wide = math.min(lmWide, len)
			local lo = math.clamp(snap(sight - wide / 2), a, b - wide)
			local hi = lo + wide
			-- a leftover too narrow for a house joins the landmark
			if lo - a < leastRow then
				lo = a
			end
			if b - hi < leastRow then
				hi = b
			end
			if lo - a > 0 then
				for _, w in Town.cut(lo - a, lotW[1], lotW[2], rnd, G) do
					table.insert(widths, w)
				end
			end
			table.insert(widths, hi - lo)
			landmarkAt = #widths
			if b - hi > 0 then
				for _, w in Town.cut(b - hi, lotW[1], lotW[2], rnd, G) do
					table.insert(widths, w)
				end
			end
		else
			widths = Town.cut(len, lotW[1], lotW[2], rnd, G)
		end
		local at = a
		for k, w in widths do
			local r: Rect
			if side == "N" then
				r = { x0 = at, x1 = at + w, z0 = edge, z1 = edge + depth }
			elseif side == "S" then
				r = { x0 = at, x1 = at + w, z0 = edge - depth, z1 = edge }
			elseif side == "W" then
				r = { x0 = edge, x1 = edge + depth, z0 = at, z1 = at + w }
			else
				r = { x0 = edge - depth, x1 = edge, z0 = at, z1 = at + w }
			end
			local front = sideRect(r, side)
			local rank = facing(front)
			local corner: string? = nil
			if corners and (k == 1 or k == #widths) then
				-- the side street a corner lot also shows a face to
				local other = if side == "N" or side == "S"
					then (if k == 1 then "W" else "E")
					else (if k == 1 then "N" else "S")
				if #widths == 1 then
					-- one lot the whole row: both ends are corners; the better street gets the windows
					local alt = if side == "N" or side == "S" then "E" else "S"
					if facing(sideRect(B, alt)) > facing(sideRect(B, other)) then
						other = alt
					end
				end
				if facing(sideRect(B, other)) > 0 then
					corner = other
				end
			end
			if rank > 0 and corner then
				built += depth -- (its flank on the side street is frontage too)
			end
			if rank > 0 then
				table.insert(allLots, {
					name = if k == landmarkAt then (lmSpec.name or "Landmark") else `House {bi}.{#allLots + 1}`,
					rect = r,
					front = side,
					rank = rank,
					block = bi,
					corner = corner,
					floors = 0,
					floorHeight = 0,
					landmark = if k == landmarkAt then true else nil,
				})
				built += w
			end
			at += w
		end
	end
	local layout: (number, Rect, boolean) -> ()
	layout = function(bi: number, B: Rect, whole: boolean)
		local w, d = B.x1 - B.x0, B.z1 - B.z0
		local rank = {
			N = facing(sideRect(B, "N")),
			S = facing(sideRect(B, "S")),
			W = facing(sideRect(B, "W")),
			E = facing(sideRect(B, "E")),
		}
		if whole then
			for side, r in rank do
				if r > 0 then
					frontage += if side == "N" or side == "S" then w else d
				end
			end
		end
		local short = math.min(w, d)
		if short >= 2 * lotD[1] then
			-- rows round a yard, or back to back when the block is no deeper than two houses (a block one row could not
			-- fill would show a street an empty half). The pair of sides that holds the block's best street takes the
			-- corners (so a row on the square runs its whole side); a tie: the better pair, then the longer
			local depth = math.min(lotD[2], math.floor(short / 2 / G) * G)
			if short - 2 * depth > 0 and short - 2 * depth < yard and short >= 2 * lotD[1] + yard then
				depth = math.max(lotD[1], math.floor((short - yard) / 2 / G) * G) -- (a yard worth the name, not a slit)
			end
			local ns = rank.N + rank.S
			local we = rank.W + rank.E
			local nsBest, weBest = math.max(rank.N, rank.S), math.max(rank.W, rank.E)
			local nsCorners = if nsBest ~= weBest then nsBest > weBest elseif ns ~= we then ns > we else w >= d
			local open: { string } = {}
			if nsCorners then
				if rank.N > 0 then
					row(bi, "N", B.x0, B.x1, B.z0, depth, B, true)
				end
				if rank.S > 0 then
					row(bi, "S", B.x0, B.x1, B.z1, depth, B, true)
				end
				local z0 = if rank.N > 0 then B.z0 + depth else B.z0
				local z1 = if rank.S > 0 then B.z1 - depth else B.z1
				for _, side in { "W", "E" } do
					if rank[side] > 0 and z1 - z0 >= leastRow then
						row(bi, side, z0, z1, if side == "W" then B.x0 else B.x1, depth, B, false)
					else
						table.insert(open, side)
					end
				end
				table.insert(yards, {
					block = bi,
					rect = { x0 = B.x0, x1 = B.x1, z0 = z0, z1 = z1 },
					open = open,
				})
			else
				if rank.W > 0 then
					row(bi, "W", B.z0, B.z1, B.x0, depth, B, true)
				end
				if rank.E > 0 then
					row(bi, "E", B.z0, B.z1, B.x1, depth, B, true)
				end
				local x0 = if rank.W > 0 then B.x0 + depth else B.x0
				local x1 = if rank.E > 0 then B.x1 - depth else B.x1
				for _, side in { "N", "S" } do
					if rank[side] > 0 and x1 - x0 >= leastRow then
						row(bi, side, x0, x1, if side == "N" then B.z0 else B.z1, depth, B, false)
					else
						table.insert(open, side)
					end
				end
				table.insert(yards, {
					block = bi,
					rect = { x0 = x0, x1 = x1, z0 = B.z0, z1 = B.z1 },
					open = open,
				})
			end
		else
			-- too shallow for two rows: one row of THROUGH houses, the block's whole depth (a row with a walled yard behind
			-- it would turn a blank wall to the street at its back), their doors on the better long side and windows
			-- on both
			local alongX = w >= d
			local a, b = if alongX then "N" else "W", if alongX then "S" else "E"
			-- the block's best street on one of its short ENDS (the square, mostly): that end gets a row of its own,
			-- facing it, and what is left of the block is laid out again behind that row
			for _, e in if alongX then { "W", "E" } else { "N", "S" } do
				local long = if alongX then w else d
				if rank[e] > math.max(rank[a], rank[b]) and long - lotD[2] < lotD[1] then
					-- no room for a row behind this one: the end's houses run the block's whole length, their doors on
					-- the best street (found by a fresh reader, 2026-11-13: without this a square whose landmark block
					-- was 40-47 studs long got houses that faced away from it, and no landmark)
					local far = if e == "W" then "E" elseif e == "E" then "W" elseif e == "N" then "S" else "N"
					local first = #allLots + 1
					if e == "W" or e == "E" then
						row(bi, e, B.z0, B.z1, if e == "W" then B.x0 else B.x1, long, B, true)
					else
						row(bi, e, B.x0, B.x1, if e == "N" then B.z0 else B.z1, long, B, true)
					end
					if rank[far] > 0 then
						for k = first, #allLots do
							allLots[k].through = far
						end
						built += if alongX then d else w
					end
					return
				end
				if rank[e] > math.max(rank[a], rank[b]) then
					local rest: Rect = { x0 = B.x0, x1 = B.x1, z0 = B.z0, z1 = B.z1 }
					if e == "W" then
						row(bi, e, B.z0, B.z1, B.x0, lotD[2], B, true)
						rest.x0 = B.x0 + lotD[2]
					elseif e == "E" then
						row(bi, e, B.z0, B.z1, B.x1, lotD[2], B, true)
						rest.x1 = B.x1 - lotD[2]
					elseif e == "N" then
						row(bi, e, B.x0, B.x1, B.z0, lotD[2], B, true)
						rest.z0 = B.z0 + lotD[2]
					else
						row(bi, e, B.x0, B.x1, B.z1, lotD[2], B, true)
						rest.z1 = B.z1 - lotD[2]
					end
					layout(bi, rest, false)
					return
				end
			end
			local side = if rank[a] > rank[b] then a elseif rank[b] > rank[a] then b elseif rnd() < 0.5 then a else b
			local back = if side == a then b else a
			if rank[side] > 0 then
				local first = #allLots + 1
				if alongX then
					row(bi, side, B.x0, B.x1, if side == "N" then B.z0 else B.z1, d, B, true)
				else
					row(bi, side, B.z0, B.z1, if side == "W" then B.x0 else B.x1, w, B, true)
				end
				if rank[back] > 0 then
					for k = first, #allLots do
						allLots[k].through = back
					end
					built += if alongX then w else d
				end
			end
		end
	end
	for bi, B in blocks do
		layout(bi, B, true)
	end

	-- heights: taller on the square and the main streets, and never the same top as a house it touches (two roofs in
	-- one plane flicker where they overlap, and a street of equal eaves reads as one long box)
	local fl = spec.floors or {}
	local heights = if type(spec.floorHeights) == "table" and #spec.floorHeights > 0
		then spec.floorHeights
		else D.floorHeights
	local floorRange: { [string]: { number } } = {}
	local tallest = 0
	for _, key in { "square", "main", "lane", "alley" } do
		local r = pair(fl[key], D.floors[key], `floors.{key}`, problem)
		if r[1] < 1 or r[2] < r[1] or r[1] % 1 ~= 0 or r[2] % 1 ~= 0 then
			problem("error", `floors.{key} [{r[1]}, {r[2]}] is not a range of whole storeys (least first)`)
			r = { D.floors[key][1], D.floors[key][2] }
		end
		floorRange[key] = r
		-- two houses side by side need two tops to choose from, or their roofs share a plane
		if r[1] == r[2] and #heights < 2 then
			problem(
				"warn",
				`floors.{key} [{r[1]}, {r[2]}] with one storey height gives every {key} house the same top: houses side by side will share a roof plane (a second storey count, or a second "floorHeights")`
			)
		end
		for _, h in heights do
			tallest = math.max(tallest, r[2] * h)
		end
	end
	local function floorsFor(rank: number): { number }
		local key = if rank >= 4 then "square" elseif rank == 3 then "main" elseif rank == 2 then "lane" else "alley"
		return floorRange[key]
	end
	local function touching(a: Rect, b: Rect): boolean
		return math.min(a.x1, b.x1) - math.max(a.x0, b.x0) > -0.01
			and math.min(a.z1, b.z1) - math.max(a.z0, b.z0) > -0.01
	end
	local landmark: Lot? = nil
	for _, lot in allLots do
		if lot.landmark then
			landmark = lot
		end
	end
	if landmark then
		-- its height first (the houses beside it are then chosen against it): two storeys over the tallest house the
		-- square may have - the one roof every street can find. A landmark typed no taller than a house is refused
		landmark.floors = lmSpec.floors or (floorsFor(Town.RANK.square)[2] + 2)
		landmark.floorHeight = heights[1]
		if landmark.floors * landmark.floorHeight <= tallest then
			problem(
				"error",
				`the landmark at {landmark.floors} storeys of {landmark.floorHeight} ({landmark.floors * landmark.floorHeight} studs) is no taller than the tallest house the town may build ({tallest}): give "landmark": \{ "floors": ... \} more`
			)
		end
	else
		problem(
			"warn",
			"no row of houses stands on the square where the main gate's street points: the town has no landmark (say so on the board: the plan should always find one)"
		)
	end
	for k, lot in allLots do
		if lot.landmark then
			continue
		end
		local range = floorsFor(lot.rank)
		local options = {}
		for f = range[1], range[2] do
			for _, h in heights do
				table.insert(options, { f, h })
			end
		end
		-- first a height no house it touches has (side, back or corner); a block too tight for that still never gives
		-- two houses SIDE BY SIDE in a row the same top: there their roofs share a plane and would flicker
		local start = math.floor(rnd() * #options)
		local pick: { number }? = nil
		for pass = 1, 2 do
			for step = 0, #options - 1 do
				local o = options[(start + step) % #options + 1]
				local clash = false
				for j = 1, k - 1 do
					local other = allLots[j]
					if
						other.block == lot.block
						and (pass == 1 or other.front == lot.front)
						and touching(lot.rect, other.rect)
						and math.abs(other.floors * other.floorHeight - o[1] * o[2]) < 0.5
					then
						clash = true
						break
					end
				end
				if not clash then
					pick = o
					break
				end
			end
			if pick then
				break
			end
		end
		local chosen = pick or options[start + 1]
		lot.floors, lot.floorHeight = chosen[1], chosen[2]
	end

	-- every house's TYPE: front x depth, storeys, and (a corner) which flank shows windows, in the house's own frame
	-- (its front is its S side, as a skin mesh's is). Houses of one type are the same house: one mesh skins them all.
	local FLANK = {
		S = { W = "w", E = "e" },
		N = { E = "w", W = "e" },
		E = { S = "w", N = "e" },
		W = { N = "w", S = "e" },
	}
	for _, lot in allLots do
		local r = lot.rect
		local alongX = lot.front == "N" or lot.front == "S"
		local fw, dp = if alongX then r.x1 - r.x0 else r.z1 - r.z0, if alongX then r.z1 - r.z0 else r.x1 - r.x0
		local flank = if lot.corner then FLANK[lot.front][lot.corner] else nil
		lot.type = `{if lot.landmark then "landmark_" else ""}{fw}x{dp}_{lot.floors}f{lot.floorHeight}{if flank
			then "_" .. flank
			else ""}{if lot.through then "_t" else ""}`
	end

	-- A WAY INTO A SHUT YARD ("yards": true; card d6u3). Most yards are shut on all four sides by their block's
	-- rows: nobody enters them, so nothing is set out in them. Where such a yard is YARD_WIDE or wider, ONE house of
	-- its rows gives way to a walled court with a gate on the street (Town.steps builds the wall). Which house:
	--   * on the QUIETEST street (an alley before a lane before a main street: a back way in, never off the square),
	--     nearest the middle of the yard's side;
	--   * never the only house its block has on that street (the block keeps a front there), a corner house, the
	--     landmark or a through house;
	--   * never one a street ENDS on (this file's first rule: a house front closes the view at the end of every
	--     lane - a gate in a low wall there would open it);
	--   * only one whose whole back is on the yard's clear ground.
	-- A yard with no such house stays shut. It is done HERE, after every house has its storeys and its type: the
	-- houses that stay are the very houses of the same town with bare yards (each lot keeps its place in the seed's
	-- draws: `order`; Town.steps skips a missing one's draw). Before, 55 of a town's 100 kept houses changed height
	-- and 36 their wall when "yards" was turned on (a fresh reader, 2026-11-14).
	for k, lot in allLots do
		lot.order = k
	end
	local dressMats = type(spec.mats) == "table"
		and (spec.mats.wood ~= nil or spec.mats.stall ~= nil)
		and spec.mats.cloth ~= nil
	if spec.yards == true and dressMats then
		-- a street ends facing this lot's front (within the widest street's width and a pavement of it)
		local function closesView(lot: any): boolean
			local l: Rect = lot.rect
			for _, st in streets do
				if st.axis == "z" and st.at > l.x0 + 1e-6 and st.at < l.x1 - 1e-6 then
					if lot.front == "N" and l.z0 >= st.to - 1e-6 and l.z0 <= st.to + 36 then
						return true
					elseif lot.front == "S" and l.z1 <= st.from + 1e-6 and l.z1 >= st.from - 36 then
						return true
					end
				elseif st.axis == "x" and st.at > l.z0 + 1e-6 and st.at < l.z1 - 1e-6 then
					if lot.front == "W" and l.x0 >= st.to - 1e-6 and l.x0 <= st.to + 36 then
						return true
					elseif lot.front == "E" and l.x1 <= st.from + 1e-6 and l.x1 >= st.from - 36 then
						return true
					end
				end
			end
			return false
		end
		for _, yd in yards do
			local clear = if #yd.open == 0 then Town.yardClear({ lots = allLots }, yd) else nil
			if clear and math.min(clear.x1 - clear.x0, clear.z1 - clear.z0) >= Town.YARD_WIDE - 1e-6 then
				local fronts: { [string]: number } = {}
				for _, lot in allLots do
					if lot.block == yd.block then
						fronts[lot.front] = (fronts[lot.front] or 0) + 1
					end
				end
				local best, bestScore = nil, math.huge
				for i, lot in allLots do
					local l: Rect = lot.rect
					if
						lot.block == yd.block
						and not lot.corner
						and not lot.landmark
						and not lot.through
						and lot.rank < Town.RANK.square
						and fronts[lot.front] >= 2
						and not closesView(lot)
					then
						local onYard, off = false, 0
						if lot.front == "W" or lot.front == "E" then
							onYard = math.abs((if lot.front == "W" then l.x1 - clear.x0 else l.x0 - clear.x1)) < 1e-6
								and l.z0 >= clear.z0 - 1e-6
								and l.z1 <= clear.z1 + 1e-6
							off = math.abs((l.z0 + l.z1) / 2 - (clear.z0 + clear.z1) / 2)
						else
							onYard = math.abs((if lot.front == "N" then l.z1 - clear.z0 else l.z0 - clear.z1)) < 1e-6
								and l.x0 >= clear.x0 - 1e-6
								and l.x1 <= clear.x1 + 1e-6
							off = math.abs((l.x0 + l.x1) / 2 - (clear.x0 + clear.x1) / 2)
						end
						local score = lot.rank * 10000 + off
						if onYard and score < bestScore then
							best, bestScore = i, score
						end
					end
				end
				if best then
					local lot = table.remove(allLots, best)
					local l: Rect = lot.rect
					yd.way = { front = lot.front, rect = l, rank = lot.rank, name = lot.name }
					built -= if lot.front == "N" or lot.front == "S" then l.x1 - l.x0 else l.z1 - l.z0
				end
			end
		end
	end

	local plan = {
		issues = issues,
		seed = spec.seed or 1,
		area = { x0 = X0, x1 = X1, z0 = Z0, z1 = Z1 },
		inner = I,
		square = S,
		streets = streets,
		blocks = blocks,
		lots = allLots,
		yards = yards,
		gates = gateOrder,
		mainGate = main,
		ring = ring,
		y = c[2] or 0,
		frontage = { total = frontage, built = built },
		view = { from = main, at = { px, pz } }, -- where the main street's view lands on the square's wall
		-- a house's walls (their outer faces on the lot's lines) and, with trim, the gap between two houses: their
		-- ridge beams reach a wall and a half past the footprint (their corner posts and floor bands less), so a wall
		-- and a stud between two footprints lets the beams meet end to end and nothing share a plane. A skin mesh is
		-- cut for the lot less both
		wall = wallT,
		gap = gapT,
	}
	if #allLots == 0 then
		problem("error", "no lot fitted (area, square, block, lots)")
	end
	-- "spawns": <1 to 8> - the town sets that many spawn pads itself, inside its main gate (a bent town carries its
	-- gate away from any typed coordinate: a spawn typed where the gate WAS stands in a wall)
	local pads = spec.spawns
	if pads ~= nil then
		if type(pads) ~= "number" or pads ~= math.floor(pads) or pads < 1 or pads > 8 then
			problem(
				"error",
				`"spawns" is how many spawn pads the town sets inside its main gate: 1 to 8 (got {tostring(pads)})`
			)
			pads = nil
		elseif type(spec.mats) ~= "table" or spec.mats.spawn == nil then
			problem("error", '"spawns" needs mats.spawn (the pads\' palette entry)')
			pads = nil
		end
	end
	plan.spawns = pads or 0
	-- "lamps": true - the town sets its own lamps, each where it has a REASON (Town.lampSpots): never a row of them
	local lamps = spec.lamps
	if lamps ~= nil and type(lamps) ~= "boolean" then
		problem(
			"error",
			`"lamps" is true (the town sets a lamp at each gate, each mouth of the square and each crossing) or false (got {tostring(
				lamps
			)})`
		)
		lamps = nil
	elseif lamps == true and (type(spec.mats) ~= "table" or spec.mats.lamp == nil) then
		problem("error", '"lamps": true needs mats.lamp (the posts\' palette entry; mats.lampLight for the lit head)')
		lamps = nil
	end
	if lamps == true and spec.mats.lampLight == nil then
		problem(
			"warn",
			'"lamps": true with no mats.lampLight: each lamp\'s lit head wears mats.lamp (a dark head that still casts light)'
		)
	end
	plan.lamps = lamps == true
	plan.facade = spec.facade == true and type(spec.skins) == "string" and spec.skins ~= ""
	-- "market": true - stalls on the square, set out by rule (Town.stallSpots); mats.stall (timber), mats.cloth (awning)
	local market = spec.market
	if market ~= nil and type(market) ~= "boolean" then
		problem("error", `"market" is true (stalls on the square, set out by rule) or false (got {tostring(market)})`)
		market = nil
	elseif market == true and (type(spec.mats) ~= "table" or spec.mats.stall == nil or spec.mats.cloth == nil) then
		problem("error", '"market": true needs mats.stall (the stalls\' timber) and mats.cloth (their awnings)')
		market = nil
	end
	plan.market = market == true
	-- "yards": true - woodpiles and wash lines in the yards a walker can enter (Town.yardThings); mats.wood (or
	-- mats.stall: the same timber) and mats.cloth
	local dress = spec.yards
	if dress ~= nil and type(dress) ~= "boolean" then
		problem("error", `"yards" is true (things in the yards, set out by rule) or false (got {tostring(dress)})`)
		dress = nil
	elseif
		dress == true
		and (type(spec.mats) ~= "table" or (spec.mats.wood == nil and spec.mats.stall == nil) or spec.mats.cloth == nil)
	then
		problem(
			"error",
			'"yards": true needs mats.wood (the woodpiles; mats.stall serves too) and mats.cloth (the washing)'
		)
		dress = nil
	end
	plan.yardDress = dress == true
	-- "slope": { "rise": <studs in 100>, "toward": "N" | "E" | "S" | "W" } - the town lies on a hillside that rises
	-- toward that side (Town.SLOPE_MOST at most); "slope": false - level ground, meant
	local slope = spec.slope
	plan.slope = nil
	if slope ~= nil and slope ~= false then
		if
			type(slope) ~= "table"
			or type(slope.rise) ~= "number"
			or slope.rise ~= slope.rise
			or slope.rise <= 0
			or slope.rise > Town.SLOPE_MOST
			or not ({ N = true, E = true, S = true, W = true })[slope.toward]
		then
			problem(
				"error",
				`"slope" is false (level ground) or \{ "rise": over 0 to {Town.SLOPE_MOST} studs in 100, "toward": "N" | "E" | "S" | "W" } (got {if type(
						slope
					) == "table"
					then `rise {tostring(slope.rise)}, toward {tostring(slope.toward)}`
					else tostring(slope)})`
			)
		elseif type(spec.bend) == "number" and spec.bend > 0 then
			problem(
				"error",
				'"slope" with "bend": a bent town on a slope is not built yet - "bend": 0, or "slope": false'
			)
		else
			plan.slope = { rise = slope.rise, toward = slope.toward }
		end
	end
	local bend = spec.bend
	if bend ~= nil and (type(bend) ~= "number" or bend ~= bend or bend < 0 or bend > Town.BEND_MAX) then
		problem("error", `"bend" is 0 (streets on two axes, meant) to {Town.BEND_MAX} degrees (got {tostring(bend)})`)
		bend = nil
	end
	plan.bend = bend or 0
	local broken = false
	for _, issue in issues do
		broken = broken or issue.severity == "error"
	end
	if plan.bend > 0 and #allLots > 0 and not broken then -- (a plan with a fault of its own is not bent on top)
		plan.bent = Town.bendOf(plan, plan.bend, problem)
	end
	if plan.yardDress and not broken and #Town.yardThings(plan) == 0 then
		-- (said, never silent: a town whose yards are all slits or all shut gets nothing from "yards": true)
		problem(
			"error",
			`"yards": true, but this town has no yard {Town.YARD_WIDE} studs wide between the houses' backs to dress (a small town's blocks are one or two rows deep) - "yards": false, or a bigger "area"`
		)
		plan.yardDress = false
	end
	if plan.market and not broken then
		-- (80 of 80 towns with a 40 x 40 square built NO stall and said nothing: a market is two stalls or more;
		-- the default 96 x 72 square holds three or four, one of 64 x 56 none)
		local stalls = #Town.stallSpots(plan)
		if stalls < 2 then
			local on: Rect = plan.square
			problem(
				"error",
				`"market": true, but this square ({on.x1 - on.x0} x {on.z1 - on.z0} studs) has room for {stalls} stall(s) once the gate's view, the streets' mouths and its edge are kept clear - a bigger "square" or "market": false`
			)
			plan.market = false
		end
	end
	return plan
end

-- ---------------------------------------------------------------- the street graph + its measures
-- nodes: where two streets meet, where a street enters the square, a gate, a dead end. edges: the street between two
-- neighbouring nodes. The square is one more node, joined to each of its entries (open ground: walked straight).
function Town.graph(plan: any): any
	local nodes: { any } = {}
	local byKey: { [string]: number } = {}
	local function node(x: number, z: number, kind: string, name: string?): number
		local key = `{math.floor(x * 2 + 0.5)}:{math.floor(z * 2 + 0.5)}`
		local id = byKey[key]
		if id then
			-- a gate or a square entry outranks a plain junction at the same spot
			if kind ~= "junction" then
				nodes[id].kind = kind
				nodes[id].name = name or nodes[id].name
			end
			return id
		end
		table.insert(nodes, { x = x, z = z, kind = kind, name = name, degree = 0 })
		byKey[key] = #nodes
		return #nodes
	end
	local streets: { Street } = plan.streets
	local S: Rect = plan.square
	local A: Rect = plan.area
	local strips: { Rect } = {}
	local on: { { { t: number, id: number } } } = {}
	for k, s in streets do
		strips[k] = Town.strip(s)
		on[k] = {}
	end
	local function put(k: number, id: number)
		local s = streets[k]
		local t = if s.axis == "z" then nodes[id].z else nodes[id].x
		for _, e in on[k] do
			if e.id == id then
				return
			end
		end
		table.insert(on[k], { t = t, id = id })
	end
	for a = 1, #streets do
		for b = a + 1, #streets do
			local sa, sb = streets[a], streets[b]
			if not touch(strips[a], strips[b], 0.5) then
				continue
			end
			if sa.axis ~= sb.axis then
				local x = if sa.axis == "z" then sa.at else sb.at
				local z = if sa.axis == "x" then sa.at else sb.at
				local id = node(x, z, "junction")
				put(a, id)
				put(b, id)
			elseif math.abs(sa.at - sb.at) < (sa.width + sb.width) / 2 then
				-- two streets end to end: one walk
				local t = if math.abs(sa.to - sb.from) < math.abs(sb.to - sa.from) then sa.to else sa.from
				local id = if sa.axis == "z" then node(sa.at, t, "junction") else node(t, sa.at, "junction")
				put(a, id)
				put(b, id)
			end
		end
	end
	local square = node((S.x0 + S.x1) / 2, (S.z0 + S.z1) / 2, "square", "Square")
	local edges: { any } = {}
	local function edge(a: number, b: number, rank: string, street: string?)
		if a == b then
			return
		end
		local dx, dz = nodes[a].x - nodes[b].x, nodes[a].z - nodes[b].z
		table.insert(edges, { a = a, b = b, length = math.sqrt(dx * dx + dz * dz), rank = rank, street = street })
		nodes[a].degree += 1
		nodes[b].degree += 1
	end
	for k, s in streets do
		if touch(strips[k], S, 0.5) then
			-- the end of the street that lies on the square's edge
			local nearFrom = if s.axis == "z"
				then math.abs(s.from - S.z1) < math.abs(s.to - S.z0)
				else math.abs(s.from - S.x1) < math.abs(s.to - S.x0)
			local t = if nearFrom then s.from else s.to
			local id = if s.axis == "z" then node(s.at, t, "entry", s.name) else node(t, s.at, "entry", s.name)
			put(k, id)
			edge(id, square, "square", nil)
		end
		-- an end on the town's edge: a gate, or (no wall street) a way out
		for _, t in { s.from, s.to } do
			local atEdge = if s.axis == "z"
				then (math.abs(t - A.z0) < 0.01 or math.abs(t - A.z1) < 0.01)
				else (math.abs(t - A.x0) < 0.01 or math.abs(t - A.x1) < 0.01)
			if atEdge then
				local isGate = false
				if s.gate then
					local side = s.gate
					isGate = (side == "N" and math.abs(t - A.z0) < 0.01)
						or (side == "S" and math.abs(t - A.z1) < 0.01)
						or (side == "W" and math.abs(t - A.x0) < 0.01)
						or (side == "E" and math.abs(t - A.x1) < 0.01)
				end
				if isGate or not plan.ring then
					local kind = if isGate then "gate" else "exit"
					local name = if isGate then `{s.gate} gate` else nil
					local id = if s.axis == "z" then node(s.at, t, kind, name) else node(t, s.at, kind, name)
					put(k, id)
				end
			end
		end
	end
	for k, s in streets do
		local list = on[k]
		table.sort(list, function(p, q)
			return p.t < q.t
		end)
		-- an end no street, square or gate takes up is a dead end
		local first = if #list > 0 then list[1].t else math.huge
		local last = if #list > 0 then list[#list].t else -math.huge
		if first - s.from > s.width then
			local id = if s.axis == "z"
				then node(s.at, s.from, "deadend", s.name)
				else node(s.from, s.at, "deadend", s.name)
			table.insert(list, 1, { t = s.from, id = id })
		end
		if s.to - last > s.width then
			local id = if s.axis == "z"
				then node(s.at, s.to, "deadend", s.name)
				else node(s.to, s.at, "deadend", s.name)
			table.insert(list, { t = s.to, id = id })
		end
		for i = 1, #list - 1 do
			edge(list[i].id, list[i + 1].id, s.rank, s.name)
		end
	end
	-- where each node STANDS (px, pz): its plan place, carried by the twist when the town is bent - an edge is as
	-- long as the walk between where its ends stand
	for _, nd in nodes do
		nd.px, nd.pz = nd.x, nd.z
		if plan.bent then
			nd.px, nd.pz = plan.bent.warp(nd.x, nd.z)
		end
	end
	if plan.bent then
		for _, ed in edges do
			local a, b = nodes[ed.a], nodes[ed.b]
			ed.length = math.sqrt((a.px - b.px) ^ 2 + (a.pz - b.pz) ^ 2)
		end
	end
	return { nodes = nodes, edges = edges, square = square }
end

-- a street's middle line as the town stands: points every `every` studs from its `from` to its `to` (two points
-- when the town is straight)
function Town.streetLine(plan: any, st: any, every: number?): { { number } }
	local out = {}
	local n = if plan.bent then math.max(1, math.ceil((st.to - st.from) / (every or 8))) else 1
	for i = 0, n do
		local t = st.from + (st.to - st.from) * i / n
		local x, z = if st.axis == "z" then st.at else t, if st.axis == "z" then t else st.at
		if plan.bent then
			x, z = plan.bent.warp(x, z)
		end
		table.insert(out, { x, z })
	end
	return out
end

-- the longest stretch of a line of points you can see along: its ends no farther apart than the line strays
-- `slack` from the straight between them
local function straightRun(line: { { number } }, slack: number): (number, number, number)
	local best, from, to = 0, 1, 1
	for i = 1, #line - 1 do
		for j = #line, i + 1, -1 do
			local ok = true
			for m = i + 1, j - 1 do
				if pointSeg(line[m][1], line[m][2], line[i], line[j]) > slack then
					ok = false
					break
				end
			end
			if ok then
				local len = math.sqrt((line[j][1] - line[i][1]) ^ 2 + (line[j][2] - line[i][2]) ^ 2)
				if len > best then
					best, from, to = len, i, j
				end
				break
			end
		end
	end
	return best, from, to
end

-- from where the LANDMARK is seen: its front's middle from the main gate, and from how much of the main street
-- (a line of sight no other house's lot stands in). nil when the plan has no landmark or no main street.
function Town.landmarkSight(plan: any): any?
	local landmark, street = nil, nil
	for _, lot in plan.lots do
		if lot.landmark then
			landmark = lot
		end
	end
	for _, st in plan.streets do
		if st.gate == plan.mainGate and st.rank == "main" then
			street = st
		end
	end
	if not landmark or not street then
		return nil
	end
	local q = Town.lotQuad(plan, landmark)
	local EDGE = { N = { 1, 2 }, E = { 2, 3 }, S = { 3, 4 }, W = { 4, 1 } }
	local e = EDGE[landmark.front]
	local target = { (q[e[1]][1] + q[e[2]][1]) / 2, (q[e[1]][2] + q[e[2]][2]) / 2 }
	-- (a hair off the front, so the landmark's own lot is never in the way of its own face)
	local mx, mz = (q[1][1] + q[3][1]) / 2, (q[1][2] + q[3][2]) / 2
	local off = math.sqrt((target[1] - mx) ^ 2 + (target[2] - mz) ^ 2)
	target = { target[1] + (target[1] - mx) / off * 0.5, target[2] + (target[2] - mz) / off * 0.5 }
	local others = {}
	for _, lot in plan.lots do
		if lot ~= landmark then
			table.insert(others, Town.lotQuad(plan, lot))
		end
	end
	local function seen(from: { number }): boolean
		for _, quad in others do
			if Town.segmentHits(from, target, quad) then
				return false
			end
		end
		return true
	end
	local line = Town.streetLine(plan, street, 8)
	if not plan.bent then -- (a straight street is two points: walk it in steps all the same)
		line = {}
		local n = math.max(1, math.ceil((street.to - street.from) / 8))
		for i = 0, n do
			local t = street.from + (street.to - street.from) * i / n
			table.insert(line, if street.axis == "z" then { street.at, t } else { t, street.at })
		end
	end
	-- the gate's end of the street is the one farther from the square
	local S: Rect = plan.square
	local sx, sz = (S.x0 + S.x1) / 2, (S.z0 + S.z1) / 2
	local function far(pt: { number }): number
		return (pt[1] - sx) ^ 2 + (pt[2] - sz) ^ 2
	end
	local gate = if far(line[1]) > far(line[#line]) then line[1] else line[#line]
	local count = 0
	for _, pt in line do
		if seen(pt) then
			count += 1
		end
	end
	return { fromGate = seen(gate), share = count / #line }
end

function Town.measure(plan: any): any
	local g = Town.graph(plan)
	local n, e = #g.nodes, #g.edges
	-- components (union-find) and the loops a walker can make: E - N + C
	local parent = {}
	for i = 1, n do
		parent[i] = i
	end
	local function find(i: number): number
		while parent[i] ~= i do
			parent[i] = parent[parent[i]]
			i = parent[i]
		end
		return i
	end
	for _, ed in g.edges do
		parent[find(ed.a)] = find(ed.b)
	end
	local comps = 0
	for i = 1, n do
		if find(i) == i then
			comps += 1
		end
	end
	local tees, crossings, dead = 0, 0, 0
	for _, nd in g.nodes do
		if nd.kind == "deadend" then
			dead += 1
		elseif nd.kind == "junction" then
			if nd.degree == 3 then
				tees += 1
			elseif nd.degree >= 4 then
				crossings += 1
			end
		end
	end
	-- the walk from the square to everywhere (Dijkstra over a few dozen nodes)
	local dist = table.create(n, math.huge)
	local done = table.create(n, false)
	dist[g.square] = 0
	local adj: { { { to: number, len: number } } } = {}
	for i = 1, n do
		adj[i] = {}
	end
	for _, ed in g.edges do
		table.insert(adj[ed.a], { to = ed.b, len = ed.length })
		table.insert(adj[ed.b], { to = ed.a, len = ed.length })
	end
	for _ = 1, n do
		local best, at = math.huge, 0
		for i = 1, n do
			if not done[i] and dist[i] < best then
				best, at = dist[i], i
			end
		end
		if at == 0 then
			break
		end
		done[at] = true
		for _, link in adj[at] do
			if dist[at] + link.len < dist[link.to] then
				dist[link.to] = dist[at] + link.len
			end
		end
	end
	local walks, farthest, cut = {}, 0, 0
	for i, nd in g.nodes do
		if dist[i] == math.huge then
			cut += 1
		else
			farthest = math.max(farthest, dist[i])
			if nd.kind == "gate" then
				table.insert(walks, { gate = nd.name, studs = dist[i], seconds = dist[i] / Town.SPEED })
			end
		end
	end
	-- the longest straight view down one street between houses, and whether a house front ends it (open = it runs
	-- out of the town: by a gate, or - with no wall street - off the edge). The wall street itself is left out: it
	-- runs along the town's open edge (the plan builds no town wall), which is no view at all
	local A: Rect = plan.area
	local vista = { length = 0, street = "", closed = true }
	local byRank: { [string]: { count: number, length: number } } = {}
	for _, s in plan.streets do
		local len = s.to - s.from
		local r = byRank[s.rank] or { count = 0, length = 0 }
		r.count += 1
		r.length += len
		byRank[s.rank] = r
		local out = if s.axis == "z"
			then (math.abs(s.from - A.z0) < 0.01 or math.abs(s.to - A.z1) < 0.01)
			else (math.abs(s.from - A.x0) < 0.01 or math.abs(s.to - A.x1) < 0.01)
		if plan.bent then
			-- a bent street is not one view: its longest stretch you can see along (the line strays no more than
			-- half the street's width from the straight between the stretch's ends) - which runs out of the town
			-- only if it reaches the street's own open end
			local line = Town.streetLine(plan, s, 8)
			local run, i, j = straightRun(line, s.width / 2)
			len = run
			local outFrom = math.abs(s.from - (if s.axis == "z" then A.z0 else A.x0)) < 0.01
			local outTo = math.abs(s.to - (if s.axis == "z" then A.z1 else A.x1)) < 0.01
			out = (outFrom and i == 1) or (outTo and j == #line)
		end
		if s.name:sub(1, 11) ~= "Wall street" and len > vista.length then
			vista = { length = len, street = s.name, closed = not out }
		end
	end
	local seen, typeCount = {}, 0
	for _, lot in plan.lots do
		if lot.type and not seen[lot.type] then
			seen[lot.type] = true
			typeCount += 1
		end
	end
	local squarePerimeter = 2 * ((plan.square.x1 - plan.square.x0) + (plan.square.z1 - plan.square.z0))
	local mouths = 0
	for _, s in plan.streets do
		if touch(Town.strip(s), plan.square, 0.5) then
			mouths += s.width
		end
	end
	return {
		nodes = n,
		edges = e,
		parts = comps,
		loops = e - n + comps,
		tees = tees,
		crossings = crossings,
		deadEnds = dead,
		cutOff = cut,
		walks = walks,
		farthestSeconds = farthest / Town.SPEED,
		vista = vista,
		streets = byRank,
		blocks = #plan.blocks,
		lots = #plan.lots,
		types = typeCount,
		frontageBuilt = if plan.frontage.total > 0 then plan.frontage.built / plan.frontage.total else 0,
		squareClosed = if squarePerimeter > 0 then 1 - mouths / squarePerimeter else 0,
		bend = plan.bend or 0,
		-- (how much wider than planned a bent town's streets are at their narrowest: { mean, most } studs)
		wider = if plan.bent then plan.bent.wider else nil,
		landmarkSeen = Town.landmarkSight(plan),
		graph = g,
	}
end

-- one line a session (and the owner) can read the layout by
function Town.summary(_plan: any, m: any): string
	local walk = {}
	for _, w in m.walks do
		table.insert(walk, `{w.gate} {math.floor(w.seconds + 0.5)} s`)
	end
	return `{m.lots} house(s) of {m.types} type(s) in {m.blocks} block(s); {m.loops} loop(s), {m.deadEnds} dead end(s), {m.tees} T-junction(s), {m.crossings} crossing(s); square {math.floor(
		m.squareClosed * 100 + 0.5
	)}% walled; gate to square: {if #walk > 0 then table.concat(walk, ", ") else "no gate reaches it"}; longest straight view {math.floor(
		m.vista.length + 0.5
	)} studs ({m.vista.street}, {if m.vista.closed then "ends inside the town" else "runs out of a gate"}){if (
			m.bend or 0
		) > 0
		then `; streets bent {m.bend} degrees round the square`
		else ""}`
end

-- a house's own side (its front is S) as the side of the world it lands on when its door faces `front` (the
-- compiler's World.skinSide by another name: kit/test/spec/worldtown.spec.luau holds the two together)
local TURN = {
	S = { S = "S", E = "E", N = "N", W = "W" },
	E = { S = "E", E = "N", N = "W", W = "S" },
	N = { S = "N", E = "W", N = "S", W = "E" },
	W = { S = "W", E = "S", N = "E", W = "N" },
}
Town.TURN = TURN

-- ---------------------------------------------------------------- the steps
-- the plan as steps the compiler knows. spec.mats names palette entries: street, square, block (the pavement), wall,
-- wallAlt?, roof, yard? (yard walls), trim?, glass?; spec.house = building fields every house takes (windows, roof,
-- slab, stairs, skin ...); spec.claims ~= false writes the streets' scale claims (kit world check measures them).
function Town.steps(plan: any, spec: any): { any }
	local D = Town.DEFAULTS
	local out: { any } = {}
	if #plan.lots == 0 then
		return out
	end
	local mats = spec.mats or {}
	local y = plan.y
	local kerb, sill = spec.kerb or D.kerb, spec.sill or D.sill
	local A: Rect, S: Rect = plan.area, plan.square
	local rnd = lcg((plan.seed or 1) + 7919)
	local bent = plan.bent
	-- the ground the streets are: the plan's area - or, bent, the box round every block as it stands and round the
	-- twisted edge, with a wall street's width to spare
	local G = { x0 = A.x0, x1 = A.x1, z0 = A.z0, z1 = A.z1 }
	if bent then
		local function reach(x: number, z: number)
			G.x0, G.x1 = math.min(G.x0, x), math.max(G.x1, x)
			G.z0, G.z1 = math.min(G.z0, z), math.max(G.z1, z)
		end
		for _, b in bent.blocks do
			for _, c in b.quad do
				reach(c[1], c[2])
			end
		end
		for _, c in { { A.x0, A.z0 }, { A.x1, A.z0 }, { A.x1, A.z1 }, { A.x0, A.z1 } } do
			reach(bent.warp(c[1], c[2]))
		end
		local edge = 0
		for _, st in plan.streets do
			if st.name:sub(1, 11) == "Wall street" then
				edge = math.max(edge, st.width)
			end
		end
		G = { x0 = G.x0 - edge, x1 = G.x1 + edge, z0 = G.z0 - edge, z1 = G.z1 + edge }
	end
	local slope = plan.slope
	local lotOf: { [any]: any } = {}
	if not slope then
		table.insert(out, {
			floor = {
				name = "Streets",
				center = { (G.x0 + G.x1) / 2, y, (G.z0 + G.z1) / 2 },
				size = { G.x1 - G.x0, G.z1 - G.z0 },
				mat = mats.street,
			},
		})
	end
	if not slope and mats.square and mats.square ~= mats.street then
		-- the square's own paving: a thin slab a hair over the street (never in its plane). Bent, the blocks round
		-- the square have moved out and turned: the paving reaches under their pavements (which lie over it)
		local grow = if bent then 1.1 else 1
		table.insert(out, {
			floor = {
				name = "Square",
				center = { (S.x0 + S.x1) / 2, y + 0.1, (S.z0 + S.z1) / 2 },
				size = { (S.x1 - S.x0) * grow, (S.z1 - S.z0) * grow },
				thickness = 0.5,
				mat = mats.square,
			},
		})
	end
	for bi, B in if slope then {} else plan.blocks do
		local at = if bent then bent.blocks[bi] else nil
		table.insert(out, {
			floor = {
				name = `Block {bi}`,
				center = { if at then at.x else (B.x0 + B.x1) / 2, y + kerb, if at then at.z else (B.z0 + B.z1) / 2 },
				size = { B.x1 - B.x0, B.z1 - B.z0 },
				-- (its underside inside the street's slab, level with nothing: a house's ground slab ends at -0.5)
				thickness = kerb + 0.7,
				mat = mats.block or mats.street,
				turn = if at then at.turn else nil,
			},
		})
	end
	local house = if type(spec.house) == "table" then spec.house else {}
	-- with trim, a house's corner posts and floor bands stand 0.9 proud of its walls: neighbours keep that much apart
	-- (their posts meet face to face) so no two lie in one plane
	local gap = plan.gap
	local nextOrder = 1
	for _, lot in plan.lots do
		-- (a house that gave way to a yard's court keeps its place in the seed's draws: the houses that stay get the
		-- walls they have in the same town with bare yards)
		while lot.order and nextOrder < lot.order do
			if mats.wallAlt then
				rnd()
			end
			nextOrder += 1
		end
		nextOrder = (lot.order or nextOrder) + 1
		local r: Rect = lot.rect
		local w, d = r.x1 - r.x0, r.z1 - r.z0
		local b = table.clone(house)
		b.name = lot.name
		b.center = { (r.x0 + r.x1) / 2, y + kerb + sill, (r.z0 + r.z1) / 2 }
		if bent then
			-- the house moves with its block and turns by the block's turn (about its own middle: one rigid piece)
			local hx, hz = bent.place(lot.block, b.center[1], b.center[3])
			b.center = { hx, b.center[2], hz }
			b.turn = bent.blocks[lot.block].turn
		end
		-- the building generator centres its walls on the footprint's edge: the footprint is the lot less half a wall
		-- all round, so the walls' outer faces stand ON the lot's lines - a street is as wide as planned, and two
		-- neighbours' party walls stand back to back (on one line they would be one wall twice: faces in one plane).
		-- With trim the gap is kept on EVERY side (a row behind and a corner's flank have posts too): the faces then
		-- stand half the gap inside the lot's lines
		local t = plan.wall
		b.size = { w - gap - t, d - gap - t }
		b.floors = lot.floors
		b.floorHeight = lot.floorHeight
		b.mat = if lot.landmark and mats.landmark
			then mats.landmark
			elseif mats.wallAlt and rnd() < 0.35 then mats.wallAlt
			else (house.mat or mats.wall)
		b.roof = house.roof or "gable"
		b.roofMat = house.roofMat or mats.roof
		b.roofCollide = if house.roofCollide ~= nil then house.roofCollide else false
		b.trim = house.trim or mats.trim
		b.glass = house.glass or mats.glass
		-- (the door and the windows are written out in FULL - a template may give half of them: the building generator
		-- and a skin mesh's recipe then read the same numbers, never each its own default)
		local door = if type(house.door) == "table" then table.clone(house.door) else {}
		door.width = door.width or 5
		door.height = door.height or 8.5
		door.side = lot.front
		b.door = door
		-- windows on the street faces only: a party wall has a neighbour behind it, a back wall the yard
		local win = if type(house.windows) == "table" then table.clone(house.windows) else {}
		win.every = win.every or 10
		win.width = win.width or 4
		win.height = win.height or 7
		win.sill = win.sill or 3.5
		if type(win.sides) == "table" then
			-- a template's sides are the HOUSE's own (its front is S, as a skin mesh's is): turned to this lot
			local turned = {}
			for _, own in win.sides do
				table.insert(turned, TURN[lot.front][own] or own)
			end
			win.sides = turned
		else
			win.sides = if lot.corner then { lot.front, lot.corner } else { lot.front }
			if lot.through then
				table.insert(win.sides, lot.through) -- (a through house shows its back to a street too)
			end
		end
		b.windows = win
		b.landmark = lot.landmark == true
		if b.stairs == true then
			-- the stair flight runs along Z: only a house deep enough that way keeps it
			local fh = lot.floorHeight
			if math.ceil(fh) * 1.6 > b.size[2] - 2 * (b.thickness or 1) - 2 then
				b.stairs = nil
			end
			-- ... and from the second flight on the flights turn back between two lanes (kit/lib/world.luau): two
			-- lanes of 4 and a body's width inside the walls, or the house has no stairs (a narrow terraced house
			-- would stop the whole town's compile)
			local flights = (b.floors or 2) - (if b.roof == "gable" then 1 else 0)
			if flights >= 2 and b.size[1] - 2 * (b.thickness or 1) < 2 * 4 + 3 then
				b.stairs = nil
			end
		end
		-- "skins": "<prefix>" - every house wears the mesh "<prefix>_<its type>" (kit world meshes kind "gothic_house",
		-- one recipe per type); the compiler says which are missing or cut for another size
		if type(spec.skins) == "string" and spec.skins ~= "" and spec.facade == true then
			-- (a facade: the modules' prefix, and the house's own seed - which window it wears, an oriel or none)
			b.facade = spec.skins
			b.seed = (lot.order or #out + 1) * 100003
				+ (spec.seed or 1) * 7919
				+ math.floor(math.abs(b.center[1]) * 3 + math.abs(b.center[3]) * 5)
		elseif type(spec.skins) == "string" then
			b.skin = `{spec.skins}_{lot.type}`
		end
		lotOf[b] = lot
		table.insert(out, { building = b })
	end
	-- a yard open at a side (a block with rows on two sides only) is closed by a wall with one gate
	for _, yd in plan.yards do
		local r: Rect = yd.rect
		local n = if table.find(yd.open, "N") then 1 else 0
		local s2 = if table.find(yd.open, "S") then 1 else 0
		for _, side in yd.open do
			local from, to
			if side == "W" then
				from, to = { r.x0 + 0.5, r.z0 + n }, { r.x0 + 0.5, r.z1 - s2 }
			elseif side == "E" then
				from, to = { r.x1 - 0.5, r.z0 + n }, { r.x1 - 0.5, r.z1 - s2 }
			elseif side == "N" then
				from, to = { r.x0, r.z0 + 0.5 }, { r.x1, r.z0 + 0.5 }
			else
				from, to = { r.x0, r.z1 - 0.5 }, { r.x1, r.z1 - 0.5 }
			end
			local len = math.abs(to[1] - from[1]) + math.abs(to[2] - from[2])
			if bent then
				from = { bent.place(yd.block, from[1], from[2]) }
				to = { bent.place(yd.block, to[1], to[2]) }
			end
			if len >= 2 then
				table.insert(out, {
					wall = {
						name = `Yard wall {yd.block}{side}`,
						from = from,
						to = to,
						y = y + kerb,
						height = 10,
						thickness = 1,
						mat = mats.yard or mats.wall,
						gaps = if len >= 9 then { { at = len / 2, width = 5, height = 8.5 } } else nil,
					},
				})
			end
		end
	end
	-- a shut yard's way in: where a house gave way, a wall on the street's line with one gate (the court behind it is
	-- the block's own pavement, open to the yard)
	for _, yd in plan.yards do
		local way = yd.way
		if way then
			local r: Rect = way.rect
			local from, to
			if way.front == "W" then
				from, to = { r.x0 + 0.5, r.z0 }, { r.x0 + 0.5, r.z1 }
			elseif way.front == "E" then
				from, to = { r.x1 - 0.5, r.z0 }, { r.x1 - 0.5, r.z1 }
			elseif way.front == "N" then
				from, to = { r.x0, r.z0 + 0.5 }, { r.x1, r.z0 + 0.5 }
			else
				from, to = { r.x0, r.z1 - 0.5 }, { r.x1, r.z1 - 0.5 }
			end
			local len = math.abs(to[1] - from[1]) + math.abs(to[2] - from[2])
			if bent then
				from = { bent.place(yd.block, from[1], from[2]) }
				to = { bent.place(yd.block, to[1], to[2]) }
			end
			table.insert(out, {
				wall = {
					name = `Yard way {yd.block}{way.front}`,
					from = from,
					to = to,
					y = y + kerb,
					height = 10,
					thickness = 1,
					mat = mats.yard or mats.wall,
					gaps = { { at = len / 2, width = 5, height = 8.5 } },
				},
			})
		end
	end
	if plan.yardDress then
		local wood = mats.wood or mats.stall
		for k, th in Town.yardThingsBuilt(plan) do
			local about = { th.x, th.z }
			-- (dx runs along the yard, dz across it, whichever way the yard lies)
			local function piece(
				name: string,
				along: number,
				high: number,
				across: number,
				dAlong: number,
				dy: number,
				dAcross: number,
				mat: any,
				more: any?
			)
				local part: any = {
					name = name,
					size = if th.alongX then { along, high, across } else { across, high, along },
					pos = if th.alongX
						then { th.x + dAlong, y + kerb + dy, th.z + dAcross }
						else { th.x + dAcross, y + kerb + dy, th.z + dAlong },
					mat = mat,
					turn = th.turn,
					about = about,
				}
				for key, v in more or {} do
					part[key] = v
				end
				table.insert(out, { part = part })
			end
			if th.kind == "pile" then
				-- a woodpile: the stacked logs and a plank cover a little wider than they are
				piece(`Yard {k} woodpile`, Town.PILE_SIZE[1], 2.6, Town.PILE_SIZE[2], 0, 1.3, 0, wood)
				piece(`Yard {k} woodpile cover`, Town.PILE_SIZE[1] + 0.4, 0.2, Town.PILE_SIZE[2] + 0.3, 0, 2.7, 0, wood)
			else
				-- a wash line: a cord from back wall to back wall 10 studs up, two sheets hanging from it - their hems
				-- 8 studs up, over a body's head; nothing of it stops a body
				piece(`Yard {k} wash line`, 0.15, 0.15, th.span, 0, 10, 0, wood, { collide = false })
				for i, f in th.hang do
					piece(
						`Yard {k} washing {i}`,
						0.1,
						1.9,
						2.2,
						0,
						9,
						(f - 0.5) * th.span,
						mats.cloth,
						{ collide = false }
					)
				end
			end
		end
	end
	if plan.market then
		-- a stall: a counter, four posts and a cloth awning, all turned as one about the stall's middle
		local w, d = Town.STALL_SIZE[1], Town.STALL_SIZE[2]
		for k, stall in Town.stallSpots(plan) do
			local about = { stall.x, stall.z }
			local function piece(
				name: string,
				size: { number },
				dx: number,
				dy: number,
				dz: number,
				mat: any,
				more: any?
			)
				local part: any = {
					name = name,
					size = size,
					pos = { stall.x + dx, y + dy, stall.z + dz },
					mat = mat,
					turn = stall.turn,
					about = about,
				}
				for key, v in more or {} do
					part[key] = v
				end
				table.insert(out, { part = part })
			end
			piece(`Stall {k} counter`, { w - 1.4, 3, 2.2 }, 0, 1.5, d / 2 - 1.8, mats.stall)
			for _, c in { { -1, -1 }, { 1, -1 }, { 1, 1 }, { -1, 1 } } do
				piece(`Stall {k} post`, { 0.5, 8, 0.5 }, c[1] * (w / 2 - 0.3), 4, c[2] * (d / 2 - 0.3), mats.stall)
			end
			piece(`Stall {k} awning`, { w + 1, 0.3, d + 1 }, 0, 8.15, 0, mats.cloth, { collide = false })
		end
	end
	if plan.lamps then
		for k, lamp in Town.lampSpots(plan) do
			-- (one lamp: a "row" of one - its line runs across the way to the junction, so its arm reaches toward it)
			table.insert(out, {
				row = {
					name = `Lamp {k} ({lamp.why})`,
					points = { { lamp.x, lamp.z }, { lamp.x - lamp.toZ, lamp.z + lamp.toX } },
					every = 100000,
					item = "lamp",
					y = y,
					mat = mats.lamp,
					light = mats.lampLight,
					curve = false,
				},
			})
		end
	end
	for k, spot in Town.spawnSpots(plan, plan.spawns or 0) do
		table.insert(out, { spawn = { name = `Spawn {k}`, pos = { spot[1], y, spot[2] }, mat = mats.spawn } })
	end
	if spec.claims ~= false then
		for _, s in plan.streets do
			-- a street claims its width where houses stand on both sides of it (the wall street has the edge on one)
			if s.name:sub(1, 11) ~= "Wall street" then
				local mid = (s.from + s.to) / 2
				-- (the claim's line stops a house depth short of each end: past it the street runs into another street)
				local a, b = s.from + 4, s.to - 4
				if bent and b - a >= 8 then
					-- a bent street claims its width piece by piece along its middle line as it stands (kit world
					-- check measures each piece ACROSS itself, on the houses' own walls)
					local n = math.max(1, math.ceil((b - a) / 24))
					local prev: { number }? = nil
					for i = 0, n do
						local t = a + (b - a) * i / n
						local px, pz = bent.warp(if s.axis == "z" then s.at else t, if s.axis == "z" then t else s.at)
						if prev then
							table.insert(out, {
								fit = {
									kind = if s.rank == "main" then "street" else "alley",
									name = if n > 1 then `{s.name} ({i} of {n})` else s.name,
									pos = { (prev[1] + px) / 2, y, (prev[2] + pz) / 2 },
									from = prev,
									to = { px, pz },
								},
							})
						end
						prev = { px, pz }
					end
				elseif b - a >= 8 then
					table.insert(out, {
						fit = {
							kind = if s.rank == "main" then "street" else "alley",
							name = s.name,
							pos = if s.axis == "z" then { s.at, y, mid } else { mid, y, s.at },
							from = if s.axis == "z" then { s.at, a } else { a, s.at },
							to = if s.axis == "z" then { s.at, b } else { b, s.at },
						},
					})
				end
			end
		end
	end
	if slope then
		-- everything onto the hillside (Town.groundAt): see A TOWN ON A SLOPE
		local g = slope.rise / 100
		local function H(x: number, z: number): number
			return Town.groundAt(plan, x, z)
		end
		local onHill: { any } = {}
		for _, st in out do
			local kind, v = next(st)
			if kind == "building" then
				local lot = lotOf[v]
				local dx, dz = Town.doorPoint(lot)
				local base = H(dx, dz)
				local r: Rect = lot.rect
				local low = math.min(H(r.x0, r.z0), H(r.x1, r.z0), H(r.x0, r.z1), H(r.x1, r.z1))
				v.center = { v.center[1], v.center[2] + base, v.center[3] }
				if base - low > 0.05 then
					-- the plinth: from under the lowest corner's ground up to the UNDERSIDE of the house's own slab (a
					-- stud under its floor, whatever the kerb and sill), its faces in the walls' own planes below
					-- them - not proud: a fifth of a stud each side took an 8-stud alley under 8 at the feet
					local top, bottom = v.center[2] - 1, y + low - 0.6
					if top - bottom > 0.05 then
						table.insert(onHill, {
							part = {
								name = `{v.name} plinth`,
								size = { v.size[1] + plan.wall, top - bottom, v.size[2] + plan.wall },
								pos = { v.center[1], (top + bottom) / 2, v.center[3] },
								mat = mats.yard or v.mat,
							},
						})
					end
				end
			elseif kind == "wall" then
				local a, b = H(v.from[1], v.from[2]), H(v.to[1], v.to[2])
				local lo = math.min(a, b)
				local len = math.sqrt((v.to[1] - v.from[1]) ^ 2 + (v.to[2] - v.from[2]) ^ 2)
				v.y += lo
				v.height += math.abs(a - b)
				for _, gate in v.gaps or {} do
					-- (the gate's opening stays whole over the ground where it stands)
					gate.height += a + (b - a) * (if len > 0 then gate.at / len else 0) - lo
				end
			elseif kind == "part" then
				if v.about then
					-- a thing of several parts (a stall, a woodpile, a wash line) stands level, set down so that none
					-- of it floats over the falling ground: its uphill feet sink a little
					local dh = H(v.about[1], v.about[2]) - g * 5
					v.pos = { v.pos[1], v.pos[2] + dh, v.pos[3] }
				else
					v.pos = { v.pos[1], v.pos[2] + H(v.pos[1], v.pos[3]), v.pos[3] }
				end
			elseif kind == "row" then
				v.y += H(v.points[1][1], v.points[1][2])
			elseif kind == "spawn" then
				-- a spawn pad (6 x 6, a stud thick) lies level: set on the ground under its LOWEST edge, a hair under,
				-- so its top is nowhere more than a stud over the street beside it - set at its middle's ground, its
				-- downhill edge stood 1.2 studs proud and a main street read 2 studs wide between its two pads
				v.pos = { v.pos[1], v.pos[2] + H(v.pos[1], v.pos[3]) - g * 3 - 0.05, v.pos[3] }
			elseif kind == "fit" then
				-- a street's claim says its floor's height at each end ("ground"): kit world check then reads its
				-- width in a band that follows the floor, sample by sample - on the street's own ground from end to
				-- end. (The first way lifted each claim to an even height over its highest ground, in pieces: the
				-- band stood up to 3.8 studs over the street's low end and anything lower hid - a fresh reader.)
				if v.from and v.to then
					v.ground = { v.pos[2] + H(v.from[1], v.from[2]), v.pos[2] + H(v.to[1], v.to[2]) }
					-- ... and how the floor climbs ACROSS it: studs up for every stud to its left (the side
					-- (-(dz), dx) of from -> to), so the band follows the hill's plane and not the middle line only
					local dx, dz = v.to[1] - v.from[1], v.to[2] - v.from[2]
					local len = math.sqrt(dx * dx + dz * dz)
					if len > 0 then
						local mx, mz = (v.from[1] + v.to[1]) / 2, (v.from[2] + v.to[2]) / 2
						v.cross = H(mx - dz / len, mz + dx / len) - H(mx, mz)
					end
				end
				v.pos = { v.pos[1], v.pos[2] + H(v.pos[1], v.pos[3]), v.pos[3] }
			end
			table.insert(onHill, st)
		end
		-- the ground itself: tilted plates cut round the houses (a plate's long way down the slope is its plan
		-- length over the cosine, so plates meet edge to edge)
		local angle = math.atan(g)
		local deg = math.deg(angle)
		local alongZ = slope.toward == "N" or slope.toward == "S"
		local rot = if slope.toward == "N"
			then { deg, 0, 0 }
			elseif slope.toward == "S" then { -deg, 0, 0 }
			elseif slope.toward == "E" then { 0, 0, deg }
			else { 0, 0, -deg }
		local ground: { any } = {}
		for _, plate in Town.groundPlates(plan) do
			local r: Rect = plate.rect
			local th = if plate.class == "block" then kerb + 0.7 else 1
			local top = if plate.class == "block" then kerb else 0
			local cx, cz = (r.x0 + r.x1) / 2, (r.z0 + r.z1) / 2
			local w, d = r.x1 - r.x0, r.z1 - r.z0
			table.insert(ground, {
				part = {
					name = "Floor",
					size = if alongZ then { w, th, d / math.cos(angle) } else { w / math.cos(angle), th, d },
					pos = { cx, y + top + H(cx, cz) - th / 2 / math.cos(angle), cz },
					rot = rot,
					mat = if plate.class == "block"
						then (mats.block or mats.street)
						elseif plate.class == "square" then (mats.square or mats.street)
						else mats.street,
				},
			})
		end
		for _, st in onHill do
			table.insert(ground, st)
		end
		return ground
	end
	return out
end

-- what the build keeps of a town for the plan page (kit/world/townplan.py) and the look's labels
function Town.record(name: string, plan: any): any
	local storeyHeights, seenHeight = 0, {}
	for _, lot in plan.lots do
		if lot.floorHeight and not seenHeight[lot.floorHeight] then
			seenHeight[lot.floorHeight] = true
			storeyHeights += 1
		end
	end
	local m = Town.measure(plan)
	local nodes = {}
	for _, nd in m.graph.nodes do
		-- (where the node STANDS: the page and the look's labels are drawn on the town as built)
		table.insert(nodes, { x = nd.px, z = nd.pz, kind = nd.kind, name = nd.name, degree = nd.degree })
	end
	local lots = {}
	local types: { [string]: number } = {}
	local footprints: { [string]: { number } } = {}
	for _, lot in plan.lots do
		table.insert(lots, {
			name = lot.name,
			rect = lot.rect,
			front = lot.front,
			rank = lot.rank,
			floors = lot.floors,
			height = lot.floors * lot.floorHeight,
			landmark = lot.landmark,
			through = lot.through,
			type = lot.type,
			-- (a bent town: the lot's corners as it stands - NW, NE, SE, SW of its rect - and its turn)
			quad = if plan.bent then Town.lotQuad(plan, lot) else nil,
			turn = if plan.bent then plan.bent.blocks[lot.block].turn else nil,
		})
		types[lot.type] = (types[lot.type] or 0) + 1
		local r = lot.rect
		local alongX = lot.front == "N" or lot.front == "S"
		local fw, dp = if alongX then r.x1 - r.x0 else r.z1 - r.z0, if alongX then r.z1 - r.z0 else r.x1 - r.x0
		-- (what a skin mesh of this type is cut for: front x depth of the walls' centre lines, storeys, storey height)
		footprints[lot.type] = { fw - plan.gap - plan.wall, dp - plan.gap - plan.wall, lot.floors, lot.floorHeight }
	end
	local typeList = {}
	for t, count in types do
		local f = footprints[t]
		table.insert(
			typeList,
			{ type = t, count = count, footprint = { f[1], f[2] }, floors = f[3], floorHeight = f[4] }
		)
	end
	table.sort(typeList, function(a, b)
		return if a.count ~= b.count then a.count > b.count else a.type < b.type
	end)
	m.graph = nil
	local area, streets, blocks = plan.area, plan.streets, plan.blocks
	local view = plan.view
	if plan.bent then
		-- as built: every street with its middle line, every block with its corners, the box that holds them all
		local box = { x0 = math.huge, x1 = -math.huge, z0 = math.huge, z1 = -math.huge }
		local function reach(x: number, z: number)
			box.x0, box.x1 = math.min(box.x0, x), math.max(box.x1, x)
			box.z0, box.z1 = math.min(box.z0, z), math.max(box.z1, z)
		end
		streets = {}
		for _, st in plan.streets do
			local copy = table.clone(st)
			copy.line = Town.streetLine(plan, st, 8)
			for _, pt in copy.line do
				reach(pt[1], pt[2])
			end
			table.insert(streets, copy)
		end
		blocks = {}
		for bi, B in plan.blocks do
			local copy = table.clone(B)
			copy.quad = plan.bent.blocks[bi].quad
			for _, c in copy.quad do
				reach(c[1], c[2])
			end
			table.insert(blocks, copy)
		end
		area = { x0 = box.x0 - 6, x1 = box.x1 + 6, z0 = box.z0 - 6, z1 = box.z1 + 6 }
		local line = Town.viewLine(plan)
		if type(view) == "table" and line then
			view = { from = view.from, at = line[2] } -- (one line: the stalls keep clear of this same one)
		end
	end
	return {
		name = name,
		seed = plan.seed,
		bend = plan.bend or 0,
		area = area,
		square = plan.square,
		streets = streets,
		blocks = blocks,
		lots = lots,
		types = typeList, -- (the kit of houses this town is made of: one mesh per type skins them all)
		-- (a facade: how many modules make every house of it - 5 a storey height, 3 for the town)
		modules = if plan.facade then #Facade.STOREY * storeyHeights + #Facade.TOWN else nil,
		gates = plan.gates,
		mainGate = plan.mainGate,
		view = view,
		-- (the town's own lamps, each with its reason: the page marks them)
		slope = if plan.slope
			then {
				rise = plan.slope.rise,
				toward = plan.slope.toward,
				-- (from the lowest edge of the town to the highest)
				drop = plan.slope.rise / 100 * (if plan.slope.toward == "N" or plan.slope.toward == "S"
					then plan.area.z1 - plan.area.z0
					else plan.area.x1 - plan.area.x0),
			}
			else nil,
		lamps = if plan.lamps then Town.lampSpots(plan) else nil,
		stalls = if plan.market then Town.stallSpots(plan) else nil, -- (the market on the square: the page marks it)
		yardThings = if plan.yardDress then Town.yardThingsBuilt(plan) else nil, -- (woodpiles, wash lines: as built)
		yardWays = if plan.yardDress then Town.yardWays(plan) else nil, -- (shut yards opened by a court and a gate)
		nodes = nodes,
		measures = m,
		summary = Town.summary(plan, m),
	}
end

-- ---------------------------------------------------------------- the kit of houses
-- a skin mesh's own side (its front is S) for each side of a house whose door faces `front` - the inverse of the
-- compiler's World.skinSide (kit/lib/world.luau SKIN_TURN; kit/test/spec/worldtown.spec.luau holds the two together)
local SKIN_SIDE = {
	S = { S = "S", E = "E", N = "N", W = "W" },
	E = { E = "S", N = "E", W = "N", S = "W" },
	N = { N = "S", W = "E", S = "N", E = "W" },
	W = { W = "S", S = "E", E = "N", N = "W" },
}
Town.SKIN_SIDE = SKIN_SIDE

-- a small steady number from a type's name (a recipe's seed: the same type is the same house in every build)
local function hash(text: string): number
	local h = 7
	for i = 1, #text do
		h = (h * 31 + string.byte(text, i)) % 2147483647
	end
	return h
end

-- The KIT a skinned town needs: one mesh recipe (kit world meshes kind "gothic_house") per house type, cut for
-- exactly the building Town.steps makes of that type - its footprint, storeys, door and every window - so the
-- compiler's own skin check (World.skinProblem) passes for every house. spec.skins = the prefix of their names;
-- spec.kit = { stones = { {r, g, b}, ... }, slate = {r, g, b}, chimneys = 0.5 } (looks), thickness (the mesh's own
-- wall depth: a reveal a little deeper than the house's wall unless typed).
-- Returns (recipes sorted by name, problem?).
function Town.kit(plan: any, spec: any): ({ any }, string?)
	if type(spec.skins) ~= "string" or spec.skins == "" then
		return {}, 'the town has no "skins": "<prefix>" (the name its house meshes start with)'
	end
	local look = if type(spec.kit) == "table" then spec.kit else {}
	local stones = if type(look.stones) == "table" and #look.stones > 0 then look.stones else nil
	if spec.facade == true then
		-- a facade's kit: the modules, cut for the town's own storey heights, door and windows
		local heights, seen = {}, {}
		local door, win, thick = nil, nil, nil
		for _, step in Town.steps(plan, spec) do
			local b = step.building
			if b and b.facade then
				if not seen[b.floorHeight] then
					seen[b.floorHeight] = true
					table.insert(heights, b.floorHeight)
				end
				door = door or { width = b.door.width, height = b.door.height }
				win = win
					or { width = b.windows.width, height = b.windows.sill + b.windows.height, sill = b.windows.sill }
				thick = thick or (b.thickness or 1)
			end
		end
		if #heights == 0 then
			return {}, "the town has no house to make modules for"
		end
		local list = Facade.kit({
			prefix = spec.skins,
			floorHeights = heights,
			thickness = look.thickness or (thick + 0.2),
			door = door,
			window = win,
		})
		for _, r in list do
			if stones then
				r.stone = stones[1]
			end
			if type(look.slate) == "table" then
				r.slate = look.slate
			end
		end
		return list, nil
	end
	local byName: { [string]: any } = {}
	local names: { string } = {}
	for _, step in Town.steps(plan, spec) do
		local b = step.building
		if b and type(b.skin) == "string" and not byName[b.skin] then
			local front = b.door.side
			local alongX = front == "N" or front == "S"
			local width, depth = if alongX then b.size[1] else b.size[2], if alongX then b.size[2] else b.size[1]
			local sides = {}
			for _, side in { "S", "E", "N", "W" } do -- (in the mesh's own order)
				for _, have in b.windows.sides do
					if SKIN_SIDE[front][have] == side then
						table.insert(sides, side)
					end
				end
			end
			local h = hash(b.skin)
			local landmark = b.landmark == true
			local recipe: any = {
				name = b.skin,
				kind = "gothic_house",
				width = width,
				depth = depth,
				floors = b.floors,
				floorHeight = b.floorHeight,
				thickness = look.thickness or (plan.wall + 0.2), -- (the mesh's wall: a reveal deeper than the house's)
				windows = {
					every = b.windows.every,
					width = b.windows.width,
					height = b.windows.height,
					sill = b.windows.sill,
					sides = sides,
				},
				door = { side = "S", width = b.door.width, height = b.door.height },
				-- a gable as steep as the front is wide (a narrow house a sharp one), stepped once every 3 studs or so
				gable = {
					height = math.clamp(math.floor(width * (if landmark then 0.9 else 0.7) + 0.5), 8, 30),
					steps = math.clamp(math.floor(width / 6 + 0.5), 3, 8),
				},
				chimney = not landmark and (h % 100) / 100 < (look.chimneys or 0.5),
				seed = h % 9973 + 1,
			}
			if stones then
				recipe.stone = stones[h % #stones + 1]
			end
			if type(look.slate) == "table" then
				recipe.slate = look.slate
			end
			byName[b.skin] = recipe
			table.insert(names, b.skin)
		end
	end
	table.sort(names)
	local out = {}
	for _, n in names do
		table.insert(out, byName[n])
	end
	return out, nil
end

return Town

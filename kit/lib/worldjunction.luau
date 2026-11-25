--!strict
-- worldjunction.luau (kit) - WHERE ROADS ON THE LAND MEET: banked Y and T junctions (LIMITATIONS_FIXES_V4 5.1 / 13.5,
-- card E8: "E8 Y/T junctions unbuilt"; the V3 banked roads, b28826184a, said "Y / T junctions are not built").
--
-- Why: a "ground": true road is laid in short pieces, each rolled with the land's fall across it. Where a lane ended
-- ON another road (a T) or three roads ended at one spot (a Y), each laid its own pieces over the other's: two
-- surfaces crossing at two different rolls - one stood out of the other by up to w/2 * tan(roll difference), the
-- other's edge sank into it - and their tops lay near one plane over the whole overlap (a flicker).
--
-- What is built: the junction is a NODE - its middle on the through road's line (a T) or the middle of the ends that
-- meet (a Y, an L) - and a round PAD there, laid in the plane that fits the land round the node best (least squares,
-- tilted at most World.ROAD_BANK_MAX). Every road that reaches the node is CUT at the pad's rim (radius: half the
-- widest road there and a stud) and runs into the pad by the rim's sagitta over its own width (so its square end's
-- corners lie inside the disc: no gap between the arc and the end); within EASE studs of the rim its roll goes over
-- from the land's to the pad's (the slope of the pad's plane across that road) and its ends on the rim take the
-- pad's height - so every road meets the pad edge to edge, at one roll. The pad lies LIFT studs over the roads' plane
-- (two tops in one plane flicker: World.GROUND_LIFT's number).
--
-- Not here: roads that only CROSS (an X with no end at the node is two roads, each whole - a crossing is typed as
-- four arms ending at one point, a Y of four), routed roads (their line is found while compiling), and how a pad
-- looks in Roblox (a Cylinder part; not yet seen in Studio). Pure: no requires, no files.
local Junction = {}

Junction.EASE = 12 -- studs past the rim over which a road's roll goes from the pad's to the land's
Junction.MARGIN = 1 -- studs the pad's rim stands out past half the widest road at the node
Junction.LIFT = 0.08 -- studs the pad's top stands over the roads' (World.GROUND_LIFT)
Junction.ON = 0.5 -- studs: an end within half the other road's width and this of its line lies ON it
Junction.MOST = 1.5 -- a pad's rim at most this many of its widest road's widths out (a fork splayed a few degrees)

export type Road = { id: number, points: { { number } }, width: number }
export type Arm = { id: number, at: "first" | "last" | "through" }
export type Node = { x: number, z: number, r: number, kind: "T" | "Y", arms: { Arm } }

-- the closest point of a polyline to (x, z): its distance, the point, and whether that point is one of its ends
local function closest(points: { { number } }, x: number, z: number): (number, number, number, boolean)
	local best, bx, bz, atEnd = math.huge, 0, 0, false
	for k = 1, #points - 1 do
		local a, b = points[k], points[k + 1]
		local dx, dz = b[1] - a[1], b[2] - a[2]
		local l2 = dx * dx + dz * dz
		local t = if l2 > 0 then math.clamp(((x - a[1]) * dx + (z - a[2]) * dz) / l2, 0, 1) else 0
		local px, pz = a[1] + dx * t, a[2] + dz * t
		local d = math.sqrt((x - px) ^ 2 + (z - pz) ^ 2)
		if d < best then
			best, bx, bz = d, px, pz
			atEnd = (k == 1 and t <= 0) or (k == #points - 1 and t >= 1)
		end
	end
	return best, bx, bz, atEnd
end
Junction.closest = closest

-- the nodes where the given roads meet. A road's end that lies on another road's line, away from its ends, makes a
-- T (its middle on that line); ends that lie within half their two widths of each other make a Y (their middle).
-- Candidates nearer than the widest road there are one node. -> nodes, and each road's nodes by its id.
function Junction.find(roads: { Road }): ({ Node }, { [number]: { Node } })
	local cands: { { x: number, z: number, t: boolean, w: number, arms: { Arm } } } = {}
	for _, a in roads do
		if #a.points < 2 then
			continue
		end
		for _, which in { "first", "last" } do
			local e = if which == "first" then a.points[1] else a.points[#a.points]
			for _, b in roads do
				if b.id == a.id or #b.points < 2 then
					continue
				end
				local d, px, pz, onEnd = closest(b.points, e[1], e[2])
				if d <= b.width / 2 + Junction.ON and not onEnd then
					-- (on the line, not at an end of it: a T - the other road runs through the node)
					table.insert(cands, {
						x = px,
						z = pz,
						t = true,
						w = math.max(a.width, b.width),
						arms = { { id = a.id, at = which :: any }, { id = b.id, at = "through" } },
					})
				else
					for _, w2 in { "first", "last" } do
						local f = if w2 == "first" then b.points[1] else b.points[#b.points]
						if math.sqrt((e[1] - f[1]) ^ 2 + (e[2] - f[2]) ^ 2) <= (a.width + b.width) / 2 then
							table.insert(cands, {
								x = (e[1] + f[1]) / 2,
								z = (e[2] + f[2]) / 2,
								t = false,
								w = math.max(a.width, b.width),
								arms = { { id = a.id, at = which :: any }, { id = b.id, at = w2 :: any } },
							})
						end
					end
				end
			end
		end
	end
	-- (candidates of one meeting: merged; a T's point wins over the ends' middle - the through road's line is fixed)
	local nodes: { Node } = {}
	local members: { { any } } = {}
	for _, c in cands do
		local into = nil
		for k, n in nodes do
			if math.sqrt((n.x - c.x) ^ 2 + (n.z - c.z) ^ 2) <= math.max(c.w, n.r * 2 - 2 * Junction.MARGIN) then
				into = k
				break
			end
		end
		if into == nil then
			table.insert(
				nodes,
				{ x = c.x, z = c.z, r = c.w / 2 + Junction.MARGIN, kind = if c.t then "T" else "Y", arms = {} }
			)
			table.insert(members, {})
			into = #nodes
		end
		local n = nodes[into]
		table.insert(members[into], c)
		n.r = math.max(n.r, c.w / 2 + Junction.MARGIN)
		for _, arm in c.arms do
			local seen = false
			for _, o in n.arms do
				if o.id == arm.id and o.at == arm.at then
					seen = true
				end
			end
			if not seen then
				table.insert(n.arms, arm)
			end
		end
	end
	for k, n in nodes do
		local ts, sx, sz, cnt = false, 0, 0, 0
		for _, c in members[k] do
			if c.t then
				if not ts then
					ts, sx, sz, cnt = true, 0, 0, 0
				end
				sx, sz, cnt = sx + c.x, sz + c.z, cnt + 1
			elseif not ts then
				sx, sz, cnt = sx + c.x, sz + c.z, cnt + 1
			end
		end
		n.x, n.z = sx / cnt, sz / cnt
		n.kind = if ts then "T" else "Y"
		table.sort(n.arms, function(p, q)
			if p.id ~= q.id then
				return p.id < q.id
			end
			return p.at < q.at
		end)
	end
	-- the rim reaches past where any two of its roads overlap. Each road leaves the node as a RAY (a lane's end one, a
	-- through road two, back to back), a half-strip its width wide; two rays splayed at a sharp angle overlap far out
	-- (a square T of 8 and 6: half the diagonal of 8 x 6), back to back hardly at all. Measured by walking each ray's
	-- cross-section out from the node and asking whether it lies in the other's half-strip - a lane's square end met
	-- the through road's surface outside a rim of half the widest road (looked at 2026-11-20: a lip where they lapped)
	local byId: { [number]: Road } = {}
	for _, r in roads do
		byId[r.id] = r
	end
	-- the rays an arm leaves the node along: { dx, dz } unit vectors
	local function rays(arm: Arm, n: Node): { { number } }
		local pts = byId[arm.id].points
		local a, b
		if arm.at == "first" then
			a, b = pts[1], pts[2]
		elseif arm.at == "last" then
			a, b = pts[#pts], pts[#pts - 1]
		else
			local best = math.huge
			for k = 1, #pts - 1 do
				local d = closest({ pts[k], pts[k + 1] }, n.x, n.z)
				if d < best then
					best, a, b = d, pts[k], pts[k + 1]
				end
			end
		end
		local dx, dz = b[1] - a[1], b[2] - a[2]
		local l = math.max(math.sqrt(dx * dx + dz * dz), 1e-9)
		dx, dz = dx / l, dz / l
		if arm.at == "through" then
			return { { dx, dz }, { -dx, -dz } }
		end
		return { { dx, dz } }
	end
	-- how far from the node the half-strips (ray a, half-width ha) and (ray b, half-width hb) still overlap
	local function reach(a: { number }, ha: number, b: { number }, hb: number, cap: number): number
		local far = 0
		local s = 0
		while s <= cap do
			for k = -4, 4 do
				local u = ha * k / 4
				local px, pz = a[1] * s - a[2] * u, a[2] * s + a[1] * u
				local along = px * b[1] + pz * b[2]
				local off = math.abs(-px * b[2] + pz * b[1])
				if along >= 0 and off <= hb then
					far = math.max(far, math.sqrt(px * px + pz * pz))
				end
			end
			s += 0.25
		end
		return far
	end
	for _, n in nodes do
		local widest = 0
		for _, arm in n.arms do
			widest = math.max(widest, byId[arm.id].width)
		end
		local cap = Junction.MOST * widest -- (a fork splayed only a few degrees overlaps for ever: its rim stops here)
		for p = 1, #n.arms do
			for q = p + 1, #n.arms do
				local A, B = n.arms[p], n.arms[q]
				if A.id ~= B.id then
					local ha, hb = byId[A.id].width / 2, byId[B.id].width / 2
					for _, ra in rays(A, n) do
						for _, rb in rays(B, n) do
							local d = math.max(reach(ra, ha, rb, hb, cap), reach(rb, hb, ra, ha, cap))
							n.r = math.max(n.r, math.min(d, cap) + Junction.MARGIN)
						end
					end
				end
			end
		end
	end
	local byRoad: { [number]: { Node } } = {}
	for _, n in nodes do
		for _, arm in n.arms do
			byRoad[arm.id] = byRoad[arm.id] or {}
			if not table.find(byRoad[arm.id], n) then
				table.insert(byRoad[arm.id], n)
			end
		end
	end
	return nodes, byRoad
end

-- how far into the disc a road of width w must run so its square end's corners lie inside the rim
function Junction.sagitta(r: number, w: number): number
	local h = math.min(w / 2, r)
	return r - math.sqrt(math.max(0, r * r - h * h)) + 0.05
end

-- a polyline with the stretches inside the nodes' discs cut out: the runs that are left (each at least 2 points),
-- every cut end set back into its disc by the sagitta of a road `width` wide
function Junction.cut(points: { { number } }, nodes: { Node }, width: number): { { { number } } }
	if #nodes == 0 then
		return { points }
	end
	local rins = {}
	for k, n in nodes do
		rins[k] = n.r - Junction.sagitta(n.r, width)
	end
	local function inside(x: number, z: number): boolean
		for k, n in nodes do
			if (x - n.x) ^ 2 + (z - n.z) ^ 2 < rins[k] * rins[k] - 1e-9 then
				return true
			end
		end
		return false
	end
	local runs: { { { number } } } = {}
	local cur: { { number } } = {}
	local within = inside(points[1][1], points[1][2])
	if not within then
		table.insert(cur, points[1])
	end
	for k = 1, #points - 1 do
		local a, b = points[k], points[k + 1]
		local dx, dz = b[1] - a[1], b[2] - a[2]
		local A = dx * dx + dz * dz
		-- every place along a -> b where it crosses an inner circle (a segment may pass through a disc whole)
		local ts: { number } = {}
		if A > 0 then
			for m, n in nodes do
				local fx, fz = a[1] - n.x, a[2] - n.z
				local B = 2 * (fx * dx + fz * dz)
				local C = fx * fx + fz * fz - rins[m] * rins[m]
				local disc = B * B - 4 * A * C
				if disc > 0 then
					for _, t in { (-B - math.sqrt(disc)) / (2 * A), (-B + math.sqrt(disc)) / (2 * A) } do
						if t > 1e-9 and t < 1 - 1e-9 then
							table.insert(ts, t)
						end
					end
				end
			end
		end
		table.sort(ts)
		for _, t in ts do
			local p = { a[1] + dx * t, a[2] + dz * t }
			-- (inside or out just past the crossing: overlapping discs cross twice without leaving)
			local after = inside(a[1] + dx * (t + 1e-6), a[2] + dz * (t + 1e-6))
			if after and not within then
				table.insert(cur, p)
				if #cur >= 2 then
					table.insert(runs, cur)
				end
				cur = {}
			elseif within and not after then
				cur = { p }
			end
			within = after
		end
		within = inside(b[1], b[2])
		if not within then
			table.insert(cur, b)
		end
	end
	if #cur >= 2 then
		table.insert(runs, cur)
	end
	-- (drop the zero-length runs a point exactly on a rim can leave)
	local out = {}
	for _, run in runs do
		local len = 0
		for k = 1, #run - 1 do
			len += math.sqrt((run[k + 1][1] - run[k][1]) ^ 2 + (run[k + 1][2] - run[k][2]) ^ 2)
		end
		if len > 0.05 then
			table.insert(out, run)
		end
	end
	return out
end

-- the plane y = a x + b z + c that fits the heights h(x, z) round a node best (least squares on a 5 x 5 grid over
-- the disc and its ease), tilted at most capDeg; nil when the land is not there
function Junction.plane(n: Node, h: (number, number) -> number?, capDeg: number): { number }?
	local reach = n.r + Junction.EASE / 2
	local sxx, sxz, szz, sx, sz, s1, sxy, szy, sy = 0, 0, 0, 0, 0, 0, 0, 0, 0
	for i = -2, 2 do
		for j = -2, 2 do
			local x, z = i / 2 * reach, j / 2 * reach
			local y = h(n.x + x, n.z + z)
			if y == nil then
				return nil
			end
			sxx += x * x
			sxz += x * z
			szz += z * z
			sx += x
			sz += z
			s1 += 1
			sxy += x * y
			szy += z * y
			sy += y
		end
	end
	-- (the grid is symmetric about the node: sx = sz = sxz = 0, so the three equations come apart)
	local a = sxy / sxx
	local b = szy / szz
	local c = sy / s1
	local tilt = math.sqrt(a * a + b * b)
	local cap = math.tan(math.rad(capDeg))
	if tilt > cap then
		a, b = a * cap / tilt, b * cap / tilt
	end
	local _ = sx + sz + sxz
	-- (c is the plane's height AT the node: x and z are measured from it) - raised until no land inside the disc
	-- stands over it: on a crowned land the plane that fits best lay under the land's middle and the pad was buried
	-- in a band across it (looked at 2026-11-20)
	local over = 0
	for i = -4, 4 do
		for j = -4, 4 do
			local x, z = i / 4 * n.r, j / 4 * n.r
			if x * x + z * z <= n.r * n.r + 1e-9 then
				local y = h(n.x + x, n.z + z)
				if y ~= nil then
					over = math.max(over, y - (c + a * x + b * z))
				end
			end
		end
	end
	return { a, b, c + over }
end

-- the plane's height at a world point
function Junction.height(n: Node, plane: { number }, x: number, z: number): number
	return plane[3] + plane[1] * (x - n.x) + plane[2] * (z - n.z)
end

-- the roll (radians) a road heading along (dx, dz) takes to lie in the plane across its width: the plane's rise to
-- the road's left side (the side World.alongX's Z column points to) over a stud
function Junction.roll(plane: { number }, dx: number, dz: number, zx: number, zz: number): number
	local _ = dx + dz
	return math.atan(plane[1] * zx + plane[2] * zz)
end

-- the share of the land's own roll a piece whose middle is (x, z) keeps (0 on the rim, 1 an EASE past it); nil when
-- it is near no node
function Junction.ease(nodes: { Node }, x: number, z: number): (number?, Node?)
	local best, bn = nil, nil
	for _, n in nodes do
		local d = math.sqrt((x - n.x) ^ 2 + (z - n.z) ^ 2)
		local t = math.clamp((d - n.r) / Junction.EASE, 0, 1)
		if t < 1 and (best == nil or t < best) then
			best, bn = t, n
		end
	end
	return best, bn
end

return Junction

-- SdfRules.luau (kit runtime, pure) — LAND AS A SIGNED DISTANCE (the owner's method list: "Signed distance field /
-- SDF terrain"). A heightmap is one height at each place: it cannot hold a cave, an overhang or an arch. A signed
-- distance can: every shape says how far a point is from its surface (below 0 = inside it), and shapes are joined
-- (the least of their distances) or cut out of each other (a point inside a cutting shape is outside the land),
-- with a blend that rounds the seam.
--
--   an "sdf" terrain op: { material, shapes: [ shape ... ] }, each shape one of
--     { ball: { center: [x, y, z], radius } }
--     { box: { center, size: [x, y, z], round?: studs its edges are rounded by } }
--     { capsule: { from: [x, y, z], to: [x, y, z], radius } }      (a tunnel, a rib of rock)
--   and optionally  cut: true  (this shape is taken OUT of the land - what the op has made so far, and the land
--   that was there before it: a cave, a doorway through a hill)  and  blend: studs (the seam is rounded that far:
--   between a shape and the op's land so far; between a cut and the cuts before it. Land that was there before the
--   op has no seam to round: one cut through a ridge is as wide with a blend as without).
--   Shapes are read in order. What is taken out of the land before the op is everything inside a cut that the
--   op's own land does not fill at the end.
--
-- The same rules are read by the game (src/kit/Environment.luau writes the voxels), by the compiler (the op's box)
-- and, in Python, by kit world check (kit/world/sdf.py: the same numbers, held together by one table of points in
-- both tests). Pure: no game calls.
local Sdf = {}

Sdf.SHAPES = 24 -- shapes an op may have
Sdf.SIDE = 512 -- studs its box may be on a side
Sdf.CELLS = 500000 -- 4-stud cells its box may come to (what the game fills when the place starts)
Sdf.FAR = 1e9
Sdf.OPEN = 4 -- studs of radius a cut needs to open in 4-stud cells (measured on the cells: under it, often it does not)
Sdf.REACH = 16000 -- studs from the middle a shape may lie

local function number(v: any): boolean
	return type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge
end

local function point(v: any): boolean
	return type(v) == "table" and #v == 3 and number(v[1]) and number(v[2]) and number(v[3])
end

-- a place: a point within REACH of the middle (the engine's land does not go on for ever)
local function place(v: any): boolean
	return point(v) and math.max(math.abs(v[1]), math.abs(v[2]), math.abs(v[3])) <= Sdf.REACH
end

-- what is wrong with an sdf op's spec (nothing = it can be made)
function Sdf.problems(spec: any): { string }
	local out: { string } = {}
	if type(spec) ~= "table" then
		return { "sdf is { material, shapes: [ { ball | box | capsule: {...}, cut?, blend? } ] }" }
	end
	for k in spec do
		if k ~= "material" and k ~= "shapes" then
			table.insert(out, `sdf.{tostring(k)} is not a word it knows (material, shapes)`)
		end
	end
	if type(spec.material) ~= "string" or spec.material == "" then
		table.insert(out, 'sdf.material is the terrain material it is made of ("Rock", "Ground" ...)')
	elseif spec.material == "Water" or spec.material == "Air" then
		table.insert(out, `sdf.material "{spec.material}": land is made of a solid (a cut makes the air)`)
	end
	local shapes = spec.shapes
	if type(shapes) ~= "table" or #shapes < 1 or #shapes > Sdf.SHAPES then
		table.insert(out, `sdf.shapes is a list of one to {Sdf.SHAPES} shapes`)
		return out
	end
	for i, s in shapes do
		local at = `sdf.shapes[{i}]`
		if type(s) ~= "table" then
			table.insert(out, `{at} is \{ ball | box | capsule: \{...\}, cut?, blend? \}`)
			continue
		end
		local kinds = 0
		for k in s do
			if k == "ball" or k == "box" or k == "capsule" then
				kinds += 1
			elseif k ~= "cut" and k ~= "blend" then
				table.insert(out, `{at}.{tostring(k)} is not a word a shape knows (ball, box, capsule, cut, blend)`)
			end
		end
		if kinds ~= 1 then
			table.insert(out, `{at} is ONE of ball, box, capsule`)
			continue
		end
		if s.cut ~= nil and type(s.cut) ~= "boolean" then
			table.insert(out, `{at}.cut is true or false`)
		end
		if s.blend ~= nil and (not number(s.blend) or s.blend < 0 or s.blend > 64) then
			table.insert(out, `{at}.blend is 0 to 64 studs`)
		end
		local b = s.ball
		if b ~= nil then
			if type(b) ~= "table" or not place(b.center) or not number(b.radius) or b.radius < 2 or b.radius > 256 then
				table.insert(out, `{at}.ball is \{ center: [x, y, z], radius: 2 to 256 \}`)
			elseif s.cut == true and b.radius < Sdf.OPEN then
				table.insert(
					out,
					`{at}: a cut of radius {b.radius} does not open in the game's 4-stud cells: {Sdf.OPEN} or more`
				)
			end
		end
		local x = s.box
		if x ~= nil then
			local ok = type(x) == "table" and place(x.center) and point(x.size)
			if ok then
				ok = math.min(x.size[1], x.size[2], x.size[3]) >= 4 and math.max(x.size[1], x.size[2], x.size[3]) <= 512
			end
			if not ok then
				table.insert(out, `{at}.box is \{ center: [x, y, z], size: [x, y, z] (4 to 512 each), round? \}`)
			elseif
				x.round ~= nil
				and (not number(x.round) or x.round < 0 or x.round > math.min(x.size[1], x.size[2], x.size[3]) / 2)
			then
				table.insert(out, `{at}.box.round is 0 to half its least side`)
			elseif s.cut == true and math.min(x.size[1], x.size[2], x.size[3]) < Sdf.OPEN * 2 then
				table.insert(
					out,
					`{at}: a cut {math.min(x.size[1], x.size[2], x.size[3])} studs across does not open in the game's 4-stud cells: {Sdf.OPEN * 2} or more`
				)
			end
		end
		local c = s.capsule
		if c ~= nil then
			if
				type(c) ~= "table"
				or not place(c.from)
				or not place(c.to)
				or not number(c.radius)
				or c.radius < 2
				or c.radius > 256
			then
				table.insert(out, `{at}.capsule is \{ from: [x, y, z], to: [x, y, z], radius: 2 to 256 \}`)
			elseif s.cut == true and c.radius < Sdf.OPEN then
				table.insert(
					out,
					`{at}: a cut of radius {c.radius} does not open in the game's 4-stud cells: {Sdf.OPEN} or more`
				)
			end
		end
	end
	if #out == 0 then
		local lo, hi = Sdf.bounds(spec)
		for a = 1, 3 do
			local side = hi[a] - lo[a]
			if side > Sdf.SIDE then
				table.insert(
					out,
					`sdf: its shapes span {math.ceil(side)} studs on one side (over {Sdf.SIDE}): make it of two ops`
				)
			end
		end
		local cells = Sdf.cells(spec)
		if cells > Sdf.CELLS then
			table.insert(
				out,
				`sdf: its box comes to {cells} cells of 4 studs (over {Sdf.CELLS}): smaller shapes, or two ops`
			)
		end
	end
	return out
end

-- how far a point is from ONE shape's surface (below 0 = inside it)
function Sdf.shape(s: any, x: number, y: number, z: number): number
	if s.ball then
		local c = s.ball.center
		return math.sqrt((x - c[1]) ^ 2 + (y - c[2]) ^ 2 + (z - c[3]) ^ 2) - s.ball.radius
	elseif s.box then
		local c, size, r = s.box.center, s.box.size, s.box.round or 0
		local qx = math.abs(x - c[1]) - (size[1] / 2 - r)
		local qy = math.abs(y - c[2]) - (size[2] / 2 - r)
		local qz = math.abs(z - c[3]) - (size[3] / 2 - r)
		local out = math.sqrt(math.max(qx, 0) ^ 2 + math.max(qy, 0) ^ 2 + math.max(qz, 0) ^ 2)
		return out + math.min(math.max(qx, qy, qz), 0) - r
	end
	local a, b = s.capsule.from, s.capsule.to
	local bx, by, bz = b[1] - a[1], b[2] - a[2], b[3] - a[3]
	local px, py, pz = x - a[1], y - a[2], z - a[3]
	local len2 = bx * bx + by * by + bz * bz
	local t = if len2 > 0 then math.clamp((px * bx + py * by + pz * bz) / len2, 0, 1) else 0
	return math.sqrt((px - bx * t) ^ 2 + (py - by * t) ^ 2 + (pz - bz * t) ^ 2) - s.capsule.radius
end

-- the least of two distances, the seam rounded over k studs (k = 0: a sharp seam)
function Sdf.smin(a: number, b: number, k: number): number
	if k <= 0 then
		return math.min(a, b)
	end
	local h = math.max(k - math.abs(a - b), 0) / k
	return math.min(a, b) - h * h * k / 4
end

-- THE LAND'S DISTANCE at a point, and the CUT's: -> d (below 0 = inside what this op makes), cut (below 0 =
-- inside a cutting shape). The land that was there before the op is taken out where cut is below 0 and the op's own
-- land does not stand (d not below 0): a shape added after a cut fills it again by being land, nothing else
function Sdf.at(spec: any, x: number, y: number, z: number): (number, number)
	local d, cut = Sdf.FAR, Sdf.FAR
	for _, s in spec.shapes do
		local di = Sdf.shape(s, x, y, z)
		local k = s.blend or 0
		if s.cut then
			d = -Sdf.smin(-d, di, k) -- (the greater of d and -di, rounded: outside the cutter and inside the land)
			cut = Sdf.smin(cut, di, k) -- (the cuts together: where two meet, the seam is rounded by the later one's blend)
		else
			d = Sdf.smin(d, di, k)
		end
	end
	return d, cut
end

-- the box its shapes lie in (each shape's own box, a blend's reach and a cell wider): lo, hi
function Sdf.bounds(spec: any): ({ number }, { number })
	local lo, hi = { math.huge, math.huge, math.huge }, { -math.huge, -math.huge, -math.huge }
	for _, s in spec.shapes do
		local pad = (s.blend or 0) + 4
		local a, b
		if s.ball then
			local r = s.ball.radius
			a = { s.ball.center[1] - r, s.ball.center[2] - r, s.ball.center[3] - r }
			b = { s.ball.center[1] + r, s.ball.center[2] + r, s.ball.center[3] + r }
		elseif s.box then
			local c, size = s.box.center, s.box.size
			a = { c[1] - size[1] / 2, c[2] - size[2] / 2, c[3] - size[3] / 2 }
			b = { c[1] + size[1] / 2, c[2] + size[2] / 2, c[3] + size[3] / 2 }
		else
			local f, t, r = s.capsule.from, s.capsule.to, s.capsule.radius
			a = { math.min(f[1], t[1]) - r, math.min(f[2], t[2]) - r, math.min(f[3], t[3]) - r }
			b = { math.max(f[1], t[1]) + r, math.max(f[2], t[2]) + r, math.max(f[3], t[3]) + r }
		end
		for k = 1, 3 do
			lo[k] = math.min(lo[k], a[k] - pad)
			hi[k] = math.max(hi[k], b[k] + pad)
		end
	end
	return lo, hi
end

-- the 4-stud cells the game reads and writes for an op: its box, carried out to the cells' own grid
function Sdf.cells(spec: any): number
	local lo, hi = Sdf.bounds(spec)
	local n = 1
	for a = 1, 3 do
		n *= math.ceil(hi[a] / 4) - math.floor(lo[a] / 4)
	end
	return n
end

-- WHAT A 4-STUD CELL BECOMES: from the land's distance and the cut's at its middle ->
--   fill (0..1: how full of the op's material; 0 = it adds nothing), clear (0..1: how much of what was there is
--   taken out; 0 = nothing). A cell half a cell inside is full, half a cell outside is empty: the surface runs
--   through the cells between
function Sdf.cell(d: number, cut: number): (number, number)
	local fill = math.clamp(0.5 - d / 4, 0, 1)
	local clear = if cut < Sdf.FAR / 2 then math.clamp(0.5 - cut / 4, 0, 1) else 0
	return fill, clear
end

return Sdf

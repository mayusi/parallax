--!strict
-- worldscatter.luau (kit) — WHERE SCATTERED THINGS GO (the owner's method list: "Density map scattering", "Poisson
-- disk scattering"). A scatter step used to throw a typed COUNT of darts evenly over its area: every corner as full
-- as the middle, and a number somebody had to guess. With a "density" the step says how FULL each place is and how
-- close two pieces may stand; the count comes out of that.
--   "density": {
--     "gap": 6,                         least distance between two pieces where the field is full (studs)
--     "noise": { "scale": 60, "seed": 3, "floor": 0.1 },      clumps and clearings by themselves (0..1)
--     "spots": [ { "at": [x, z], "radius": 40, "weight": 1 } ],   full at each spot, thinning to its radius
--     "away":  [ { "at": [x, z], "radius": 20 } ],                nothing inside, growing back over a third more
--     "map": { "origin": [x, z], "cell": 16, "rows": [ "0139", "0259", ... ] }   a painted grid, 0..9 a cell
--   }
-- The field at a place is the product of what is given (noise x spots x away x map), 0 = nothing, 1 = full.
-- The number of pieces on a patch of ground follows the field: half the field, half the pieces. Two things do
-- it, the way a hand places things: pieces stand WIDER apart where it is low (at least gap / sqrt(field), up to 3
-- gaps), and below that (a field under 1/9) the few that would stand there are THINNED by chance.
-- The spread is a true Poisson-disk sample: candidates are thrown until the area takes no more (a run of them
-- refused by their neighbours), on a grid so that a large area stays fast; no two pieces closer than their gap, no
-- hole a piece still fits.
-- Pure: no files, no instances; the same seed gives the same pieces. kit/test/spec/worldscatter.spec.luau
local Scatter = {}

Scatter.WIDEST = 3 -- a sparse place spreads its pieces at most this many gaps apart
Scatter.MISSES = 3000 -- candidates refused by their neighbours in a row before the area is called full
Scatter.TRIES = 600000 -- candidates in all (an area that is nearly all clearing must still end: then it says so)
Scatter.SPOTS = 64 -- spots, and clearings, a density may list (each candidate asks every one)
Scatter.SEEDS = 65535 -- a noise seed is a whole number 0 to this (the lattice's hash stays exact)
Scatter.MOST = 4000 -- pieces a step may come to (a compile error says so: more is a typo in the gap)

local function number(v: any): boolean
	return type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge
end

local function point(v: any): boolean
	return type(v) == "table" and number(v[1]) and number(v[2])
end

-- value noise 0..1, smooth, the same for the same seed (an integer lattice hashed, cubic between)
local function lattice(ix: number, iz: number, seed: number): number
	local h =
		bit32.bxor(bit32.band(ix * 374761393, 0xFFFFFFFF), bit32.band(iz * 668265263, 0xFFFFFFFF), seed * 2246822519)
	h = bit32.band(bit32.bxor(h, bit32.rshift(h, 13)) * 1274126177, 0xFFFFFFFF)
	h = bit32.bxor(h, bit32.rshift(h, 16))
	return h / 0xFFFFFFFF
end

local function noiseAt(x: number, z: number, scale: number, seed: number): number
	local fx, fz = x / scale, z / scale
	local ix, iz = math.floor(fx), math.floor(fz)
	local tx, tz = fx - ix, fz - iz
	tx, tz = tx * tx * (3 - 2 * tx), tz * tz * (3 - 2 * tz)
	local a, b = lattice(ix, iz, seed), lattice(ix + 1, iz, seed)
	local c, d = lattice(ix, iz + 1, seed), lattice(ix + 1, iz + 1, seed)
	return (a + (b - a) * tx) + ((c + (d - c) * tx) - (a + (b - a) * tx)) * tz
end

-- a key the rules do not know is said (a typo'd "sead" would be a seed of 1 without a word)
local function strays(out: { string }, path: string, t: any, known: { string })
	for k in t do
		if not table.find(known, k) then
			table.insert(out, `{path}.{tostring(k)}: {path} says "{table.concat(known, '", "')}" - nothing else`)
		end
	end
end

-- what is wrong with a "density" (nothing = it can be used)
function Scatter.problems(density: any): { string }
	local out: { string } = {}
	if type(density) ~= "table" then
		return { '"density" is { "gap": <studs>, "noise"? | "spots"? | "away"? | "map"? } (or false: an even count)' }
	end
	for k in density do
		if k ~= "gap" and k ~= "noise" and k ~= "spots" and k ~= "away" and k ~= "map" then
			table.insert(
				out,
				`density.{tostring(k)}: a density says "gap", "noise", "spots", "away", "map" - nothing else`
			)
		end
	end
	if not number(density.gap) or density.gap < 0.5 or density.gap > 500 then
		table.insert(
			out,
			`density.gap is the least distance between two pieces, 0.5 to 500 studs (got {tostring(density.gap)})`
		)
	end
	local n = density.noise
	if n ~= nil then
		if type(n) ~= "table" or not number(n.scale) or n.scale < 4 then
			table.insert(out, 'density.noise is { "scale": <studs across one clump, 4 or more>, "seed"?, "floor"? }')
		elseif n.floor ~= nil and (not number(n.floor) or n.floor < 0 or n.floor >= 1) then
			table.insert(out, `density.noise.floor is 0 to under 1 (got {tostring(n.floor)})`)
		elseif n.seed ~= nil and (not number(n.seed) or n.seed % 1 ~= 0 or n.seed < 0 or n.seed > Scatter.SEEDS) then
			table.insert(out, `density.noise.seed is a whole number 0 to {Scatter.SEEDS} (got {tostring(n.seed)})`)
		else
			strays(out, "density.noise", n, { "scale", "seed", "floor" })
		end
	end
	for _, field in { "spots", "away" } do
		local list = density[field]
		if list ~= nil then
			if type(list) ~= "table" or #list == 0 then
				table.insert(out, `density.{field} is a list of \{ "at": [x, z], "radius": <studs> }`)
			elseif #list > Scatter.SPOTS then
				table.insert(out, `density.{field} lists {#list}: {Scatter.SPOTS} at most (paint a "map" for more)`)
			else
				for i, s in list do
					if type(s) ~= "table" or not point(s.at) or not number(s.radius) or s.radius <= 0 then
						table.insert(out, `density.{field}[{i}] is \{ "at": [x, z], "radius": <studs over 0> }`)
					elseif
						field == "spots"
						and s.weight ~= nil
						and (not number(s.weight) or s.weight <= 0 or s.weight > 1)
					then
						table.insert(out, `density.spots[{i}].weight is over 0, up to 1 (got {tostring(s.weight)})`)
					else
						strays(
							out,
							`density.{field}[{i}]`,
							s,
							if field == "spots" then { "at", "radius", "weight" } else { "at", "radius" }
						)
					end
				end
			end
		end
	end
	local m = density.map
	if m ~= nil then
		if
			type(m) ~= "table"
			or not point(m.origin)
			or not number(m.cell)
			or m.cell < 1
			or type(m.rows) ~= "table"
			or #m.rows == 0
		then
			table.insert(
				out,
				'density.map is { "origin": [x, z] (its north-west corner), "cell": <studs>, "rows": [ "0139", ... ] }'
			)
		else
			local width = nil
			local any = false
			for i, row in m.rows do
				if type(row) ~= "string" or #row == 0 or string.find(row, "[^%d]") ~= nil then
					table.insert(out, `density.map.rows[{i}] is a string of digits, 0 (nothing) to 9 (full)`)
				elseif width ~= nil and #row ~= width then
					table.insert(
						out,
						`density.map.rows[{i}] has {#row} cells, the first row {width}: every row the same`
					)
				else
					width = width or #row
					any = any or string.find(row, "[1-9]") ~= nil
				end
			end
			if #out == 0 and not any then
				table.insert(out, "density.map is 0 everywhere: nothing would be placed")
			end
		end
	end
	return out
end

-- the field: (x, z) -> 0..1. Call only with a density that has no problems.
function Scatter.field(density: any): (number, number) -> number
	local noise, spots, away, map = density.noise, density.spots, density.away, density.map
	local rows: { { number } } = {}
	if map then
		for i, row in map.rows do
			rows[i] = {}
			for j = 1, #row do
				rows[i][j] = (string.byte(row, j) - 48) / 9
			end
		end
	end
	local function cellValue(i: number, j: number): number
		local r = rows[math.clamp(i, 1, #rows)]
		return r[math.clamp(j, 1, #r)]
	end
	return function(x: number, z: number): number
		local f = 1
		if noise then
			local floor = noise.floor or 0
			-- (stretched: plain value noise keeps to the middle, and a field that never reaches 0 or 1 is no field)
			local v = math.clamp((noiseAt(x, z, noise.scale, noise.seed or 1) - 0.25) / 0.5, 0, 1)
			f *= floor + (1 - floor) * v
		end
		if spots then
			local best = 0
			for _, s in spots do
				local d = math.sqrt((x - s.at[1]) ^ 2 + (z - s.at[2]) ^ 2) / s.radius
				if d < 1 then
					local fall = 1 - d * d * (3 - 2 * d) -- (full at the spot, eased to nothing at its radius)
					best = math.max(best, fall * (s.weight or 1))
				end
			end
			f *= best
		end
		if away then
			for _, s in away do
				local d = math.sqrt((x - s.at[1]) ^ 2 + (z - s.at[2]) ^ 2) / s.radius
				if d < 1 then
					return 0
				elseif d < 4 / 3 then
					f *= (d - 1) * 3
				end
			end
		end
		if map then
			-- between the cells' middles, so that a painted edge is a slope and not a step
			local gx, gz = (x - map.origin[1]) / map.cell + 0.5, (z - map.origin[2]) / map.cell + 0.5
			if gx < 0.5 or gz < 0.5 or gx > #rows[1] + 0.5 or gz > #rows + 0.5 then
				return 0 -- (off the map: nothing)
			end
			local j, i = math.floor(gx), math.floor(gz)
			local tx, tz = gx - j, gz - i
			local top = cellValue(i, j) + (cellValue(i, j + 1) - cellValue(i, j)) * tx
			local bottom = cellValue(i + 1, j) + (cellValue(i + 1, j + 1) - cellValue(i + 1, j)) * tx
			f *= top + (bottom - top) * tz
		end
		return math.clamp(f, 0, 1)
	end
end

-- the least distance a piece at a place of field `f` keeps from its neighbours
function Scatter.gapAt(gap: number, f: number): number
	return gap * math.min(Scatter.WIDEST, 1 / math.sqrt(math.max(f, 1e-6)))
end

-- THE SAMPLE. area = { cx, cz, w, d }; `rnd` = a 0..1 generator (the step's own, so the seed is the step's);
-- `site(x, z)` = may a piece stand here at all (the land, roads, water: the compiler's own test), optional.
-- -> { { x, z, gap } } in the order placed, and how it ended: nil (the area took no more), "over" (it comes to
-- more than Scatter.MOST pieces: nothing is handed back) or "short" (Scatter.TRIES ran out before the area was
-- full - nearly all of it is clearing: what was placed is handed back, and the compiler says so)
function Scatter.sample(
	area: { number },
	density: any,
	rnd: () -> number,
	site: ((number, number) -> boolean)?
): ({ { number } }, string?)
	local field = Scatter.field(density)
	local gap = density.gap
	local cx, cz, w, d = area[1], area[2], area[3], area[4]
	local x0, z0 = cx - w / 2, cz - d / 2
	-- a grid of cells one (smallest) gap wide: a piece's neighbours are in the cells its own gap reaches
	local cell = gap
	local grid: { [number]: { number } } = {}
	local nx = math.max(1, math.ceil(w / cell))
	local placed: { { number } } = {}
	local function free(x: number, z: number, r: number): boolean
		local reach = math.ceil(math.max(r, gap * Scatter.WIDEST) / cell)
		local gi, gj = math.floor((x - x0) / cell), math.floor((z - z0) / cell)
		for i = gi - reach, gi + reach do
			for j = gj - reach, gj + reach do
				local list = grid[j * nx * 4 + i]
				if list then
					for _, index in list do
						local q = placed[index]
						-- (each of the two keeps its own distance: the wider one decides)
						local need = math.max(r, q[3])
						if (q[1] - x) ^ 2 + (q[2] - z) ^ 2 < need * need then
							return false
						end
					end
				end
			end
		end
		return true
	end
	-- candidates are thrown only where the field can be over 0: the box round the spots, the painted grid's own
	-- (a spot in a wide empty land is not found by throwing at the whole land)
	local bx0, bx1, bz0, bz1 = x0, x0 + w, z0, z0 + d
	if density.spots then
		local sx0, sx1, sz0, sz1 = math.huge, -math.huge, math.huge, -math.huge
		for _, s in density.spots do
			sx0, sx1 = math.min(sx0, s.at[1] - s.radius), math.max(sx1, s.at[1] + s.radius)
			sz0, sz1 = math.min(sz0, s.at[2] - s.radius), math.max(sz1, s.at[2] + s.radius)
		end
		bx0, bx1, bz0, bz1 = math.max(bx0, sx0), math.min(bx1, sx1), math.max(bz0, sz0), math.min(bz1, sz1)
	end
	if density.map then
		local m = density.map
		bx0, bx1 = math.max(bx0, m.origin[1]), math.min(bx1, m.origin[1] + m.cell * #m.rows[1])
		bz0, bz1 = math.max(bz0, m.origin[2]), math.min(bz1, m.origin[2] + m.cell * #m.rows)
	end
	if bx1 <= bx0 or bz1 <= bz0 then
		return {}, nil -- (the field is 0 over the whole area)
	end
	local misses, tries = 0, 0
	local mayStand: { [number]: boolean } = {}
	local fields: { number } = {}
	local least = 1 / Scatter.WIDEST ^ 2
	local coming = 0 -- (how many of the placed the thinning below will keep, as it goes)
	while misses < Scatter.MISSES and tries < Scatter.TRIES do
		tries += 1
		local x, z = bx0 + rnd() * (bx1 - bx0), bz0 + rnd() * (bz1 - bz0)
		local f = field(x, z)
		-- (a candidate where nothing may stand says nothing about how full the rest is: not a miss)
		if f <= 0 then
			continue
		end
		local r = Scatter.gapAt(gap, f)
		-- (the neighbours first: near the end nearly every candidate is refused by them, and the compiler's word
		-- on a place walks every road of the world. A refused candidate is a miss only where a piece MAY stand:
		-- asked once a grid cell, at its middle, and remembered - the exact word is asked of what is placed)
		if not free(x, z, r) then
			if site ~= nil then
				local gi, gj = math.floor((x - x0) / cell), math.floor((z - z0) / cell)
				local key = gj * nx * 4 + gi
				local may = mayStand[key]
				if may == nil then
					may = site(x0 + (gi + 0.5) * cell, z0 + (gj + 0.5) * cell)
					mayStand[key] = may
				end
				if not may then
					continue
				end
			end
			misses += 1
			continue
		end
		if site ~= nil and not site(x, z) then
			continue
		end
		misses = 0
		coming += math.min(1, f / least)
		if coming > Scatter.MOST then
			return {}, "over"
		end
		table.insert(placed, { x, z, r })
		fields[#placed] = f
		local key = math.floor((z - z0) / cell) * nx * 4 + math.floor((x - x0) / cell)
		grid[key] = grid[key] or {}
		table.insert(grid[key], #placed)
	end
	-- where the field is under what the widest gap already gives (1 / WIDEST^2), the pieces are thinned by chance
	local kept: { { number } } = {}
	for i, q in placed do
		if fields[i] >= least or rnd() < fields[i] / least then
			table.insert(kept, q)
		end
	end
	return kept, if misses < Scatter.MISSES then "short" else nil
end

return Scatter

--!strict
-- worldfog.luau (kit) — FOG THAT LIES LOW (a "fog" build step; the owner's method list: "Layered fog").
-- Roblox has no fog by height and no fog volumes: its Atmosphere is one haze by distance (its own Atmosphere page;
-- height fog is an open request on the DevForum). The stand-in games use: see-through SHEETS stacked low over the
-- ground. Here the fog is a BLANKET `depth` thick under its top: `layers` level sheets at even heights in that band;
-- each cell takes a sheet where any of its land (or the water over it) lies under the sheet, so the fog's edge follows
-- the land's contour, never runs through a hill and never lies under water. Every place under the whole band has all
-- the sheets: straight down they add up to `thick` (a place in the band's upper part, fewer - the fog thins at its
-- edge). Looking across, many sheets overlap and the fog closes in - as fog does.
--   { "fog": { "over": "low" | "water" | "hollows", "below": y (for "low": the fog's top, a height),
--              "depth": the blanket's thickness (low: 12, or less over land not that far under the line; water: how high it rises over the water, 6; hollows: over
--              the hollow's floor, 6), "center": [x, y, z] + "area": [w, d] (where it may lie; default: the play land,
--              never the far scenery), "layers": 6, "thick": 0.6, "cell": 4 (bigger by itself over a big area),
--              "mat": "<palette>", "mist": 0..40 (slow mist puffs in it), "seed": 1, "deep": 4, "reach": 48 } }
-- "water": over every water box of the terrain and every painted river cell (and one cell onto the bank);
-- "hollows": over every place the ground lies `deep` studs or more under the mean ground round it (within `reach`,
-- read only where that whole round lies on the land: the land's edge is no hollow), each hollow filled to its own
-- level (its floor + depth, never over the land round it) and the fog spread to every joined place under that level
-- (a wide basin is filled across, not only round its rim).
-- Pure: no Instance, no services. -> sheets { size, pos, transparency, layer }, mist { pos }, a record, problems.
local Fog = {}

Fog.LAYERS = 6
Fog.THICK = 0.6
Fog.CELL = 4 -- (the finest a step gets by itself; a bigger area gets bigger cells, so it stays under MOST_CELLS)
Fog.DEPTH = 6 -- (water and hollows)
Fog.DEPTH_LOW = 12 -- (a fog line's blanket)
Fog.DEEP = 4
Fog.REACH = 48
Fog.SHEET = 0.05 -- a sheet's thickness (studs)
Fog.MOST = 4000 -- sheets in one step at most: over it, an error (never a silent cut)
Fog.MOST_CELLS = 40000 -- cells read at most (a 800-stud square at 4)
Fog.MOST_MIST = 40
Fog.WIDEST = 2048 -- a part's widest side in Roblox: a sheet is cut there

local OVER = { low = true, water = true, hollows = true }
local KEYS = {
	over = true,
	below = true,
	depth = true,
	center = true,
	area = true,
	layers = true,
	thick = true,
	cell = true,
	mat = true,
	mist = true,
	seed = true,
	deep = true,
	reach = true,
	name = true,
	stream = true,
}

local function num(v: any): boolean
	return type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge
end

-- what is wrong with a fog step -> a list of problems
function Fog.problems(spec: any): { string }
	local out = {}
	if type(spec) ~= "table" then
		return { "fog is { over, ... }" }
	end
	for k in spec do
		if not KEYS[k] then
			table.insert(
				out,
				`fog.{tostring(k)}: not a fog word (over, below, depth, center, area, layers, thick, cell, mat, mist, seed, deep, reach, name, stream)`
			)
		end
	end
	local over = spec.over or "low"
	if not OVER[over] then
		table.insert(out, `fog.over is "low", "water" or "hollows" (got {tostring(over)})`)
	end
	if over == "low" and not num(spec.below) then
		table.insert(out, 'fog over "low" needs "below": the height its top lies at')
	end
	local function range(k: string, lo: number, hi: number, whole: boolean?)
		local v = spec[k]
		if v ~= nil and (not num(v) or v < lo or v > hi or (whole and v % 1 ~= 0)) then
			table.insert(out, `fog.{k} is {if whole then "a whole number " else ""}{lo} to {hi} (got {tostring(v)})`)
		end
	end
	range("layers", 1, 12, true)
	range("thick", 0.05, 0.95)
	range("cell", 2, 64)
	range("depth", 0.5, 60)
	range("deep", 0.5, 100)
	range("reach", 8, 400)
	range("mist", 0, Fog.MOST_MIST, true)
	if spec.seed ~= nil and not num(spec.seed) then
		table.insert(out, `fog.seed is a number (got {tostring(spec.seed)})`)
	end
	if spec.area ~= nil then
		local a = spec.area
		if type(a) ~= "table" or not num(a[1]) or not num(a[2]) or a[1] <= 0 or a[2] <= 0 then
			table.insert(out, "fog.area is [width, depth] in studs, both over 0")
		end
		local c = spec.center
		if type(c) ~= "table" or not num(c[1]) or not num(c[2]) or not num(c[3]) then
			table.insert(out, "fog.area needs its center [x, y, z]")
		end
	elseif spec.center ~= nil then
		table.insert(out, 'fog.center goes with "area" (where the fog may lie)')
	end
	return out
end

-- a sheet's transparency so that `n` sheets seen straight down add up to `thick`
function Fog.sheetTransparency(n: number, thick: number): number
	return (1 - thick) ^ (1 / n)
end

-- lay the fog.
--   ground(x, z) -> the land's height there or nil (no land: no fog)
--   bounds: { x0, z0, x1, z1 } the land's extent (where "area" is not given)
--   waterAt(x, z) -> the water's surface there, or nil
-- -> sheets, mist, record, problems
function Fog.lay(
	spec: any,
	ground: (number, number) -> number?,
	bounds: { number },
	waterAt: (number, number) -> number?
): ({ any }, { any }, any, { string })
	local problems = Fog.problems(spec)
	local record = { sheets = 0, cells = 0, fogged = 0 }
	if #problems > 0 then
		return {}, {}, record, problems
	end
	local over = spec.over or "low"
	local n = spec.layers or Fog.LAYERS
	local span = spec.depth or (if over == "low" then Fog.DEPTH_LOW else Fog.DEPTH)
	local x0, z0, x1, z1
	if spec.area then
		x0, x1 = spec.center[1] - spec.area[1] / 2, spec.center[1] + spec.area[1] / 2
		z0, z1 = spec.center[3] - spec.area[2] / 2, spec.center[3] + spec.area[2] / 2
	else
		x0, z0, x1, z1 = bounds[1], bounds[2], bounds[3], bounds[4]
	end
	local cell = spec.cell
	if cell == nil then
		cell = math.max(Fog.CELL, math.ceil(math.sqrt((x1 - x0) * (z1 - z0) / Fog.MOST_CELLS)))
	end
	local nu, nv = math.max(1, math.floor((x1 - x0) / cell + 0.5)), math.max(1, math.floor((z1 - z0) / cell + 0.5))
	if nu * nv > Fog.MOST_CELLS then
		table.insert(
			problems,
			`fog: {nu} x {nv} cells is over {Fog.MOST_CELLS} - give a bigger "cell" or a smaller "area"`
		)
		return {}, {}, record, problems
	end
	local du, dv = (x1 - x0) / nu, (z1 - z0) / nv
	-- each cell: its land at the middle (g), the lowest of its land at the middle and four corners (low), the water
	-- over it (wet), and what the fog may lie on (floor: the lowest land, or the water's surface over it)
	local g: { { number? } } = {}
	local floorOf: { { number? } } = {}
	local wet: { { number? } } = {}
	local top: { { number? } } = {}
	for u = 1, nu do
		g[u], floorOf[u], wet[u], top[u] = {}, {}, {}, {}
		for v = 1, nv do
			local cx, cz = x0 + (u - 0.5) * du, z0 + (v - 0.5) * dv
			local mid = ground(cx, cz)
			g[u][v] = mid
			local lowest = mid
			for _, o in { { -0.45, -0.45 }, { 0.45, -0.45 }, { -0.45, 0.45 }, { 0.45, 0.45 } } do -- (just inside: never the next cell's land)
				local h = ground(cx + o[1] * du, cz + o[2] * dv)
				if h and (lowest == nil or h < lowest) then
					lowest = h
				end
			end
			local w = waterAt(cx, cz)
			wet[u][v] = w
			if lowest ~= nil and w ~= nil and w > lowest then
				lowest = w -- (fog lies on the water, never under it)
			end
			floorOf[u][v] = lowest
		end
	end
	record.cells = nu * nv
	if over == "low" then
		local lowest = math.huge
		for u = 1, nu do
			for v = 1, nv do
				local f = floorOf[u][v]
				if f and f < spec.below then
					top[u][v] = spec.below
					lowest = math.min(lowest, f)
				end
			end
		end
		if spec.depth == nil and lowest < math.huge then
			span = math.min(span, spec.below - lowest) -- (by itself, no thicker than the air over its lowest land)
		end
	elseif over == "water" then
		for u = 1, nu do -- (the water's cells, and one cell onto its bank: fog does not stop at the water's edge)
			for v = 1, nv do
				local best: number? = nil
				for a = math.max(1, u - 1), math.min(nu, u + 1) do
					for b = math.max(1, v - 1), math.min(nv, v + 1) do
						local w = wet[a][b]
						if w and (best == nil or w > best) then
							best = w
						end
					end
				end
				local f = floorOf[u][v]
				if best and f ~= nil and f < best + span then
					top[u][v] = best + span
				end
			end
		end
	else -- hollows
		local deep, reach = spec.deep or Fog.DEEP, spec.reach or Fog.REACH
		local r = math.max(1, math.floor(reach / math.min(du, dv) + 0.5))
		local low: { { boolean } } = {}
		local mean: { { number } } = {}
		for u = 1, nu do
			low[u], mean[u] = {}, {}
			for v = 1, nv do
				local h = g[u][v]
				local sum, k, whole = 0, 0, true
				if h and u - r >= 1 and u + r <= nu and v - r >= 1 and v + r <= nv then
					for a = u - r, u + r do
						for b = v - r, v + r do
							if (a - u) ^ 2 + (b - v) ^ 2 <= r * r then
								local q = g[a][b]
								if q then
									sum += q
									k += 1
								else
									whole = false
								end
							end
						end
					end
				else
					whole = false -- (its round runs off the land or the area: the land's edge is no hollow)
				end
				mean[u][v] = if k > 0 then sum / k else math.huge
				low[u][v] = whole and h ~= nil and k > 0 and h <= sum / k - deep
			end
		end
		local seen: { [number]: boolean } = {}
		for u = 1, nu do
			for v = 1, nv do
				if low[u][v] and not seen[u * 65536 + v] then
					local comp, stack = {}, { { u, v } }
					seen[u * 65536 + v] = true
					local floor, cap = math.huge, math.huge
					while #stack > 0 do
						local c = table.remove(stack) :: { number }
						table.insert(comp, c)
						floor = math.min(floor, g[c[1]][c[2]] :: number)
						cap = math.min(cap, mean[c[1]][c[2]])
						for _, d in { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } } do
							local a, b = c[1] + d[1], c[2] + d[2]
							if a >= 1 and a <= nu and b >= 1 and b <= nv and low[a][b] and not seen[a * 65536 + b] then
								seen[a * 65536 + b] = true
								table.insert(stack, { a, b })
							end
						end
					end
					local level = math.min(floor + span, cap)
					if level > floor then
						-- spread to every joined cell under the level (the hollow's sides; a wide basin across)
						local filled: { [number]: boolean } = {}
						local queue = {}
						for _, c in comp do
							filled[c[1] * 65536 + c[2]] = true
							table.insert(queue, c)
						end
						local head = 1
						while head <= #queue do
							local c = queue[head]
							head += 1
							local f = floorOf[c[1]][c[2]]
							if f and f < level then
								local t = top[c[1]][c[2]]
								top[c[1]][c[2]] = if t then math.max(t, level) else level
								for _, d in { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } } do
									local a, b = c[1] + d[1], c[2] + d[2]
									if a >= 1 and a <= nu and b >= 1 and b <= nv and not filled[a * 65536 + b] then
										filled[a * 65536 + b] = true
										table.insert(queue, { a, b })
									end
								end
							end
						end
					end
				end
			end
		end
	end
	-- the sheets: for each top, `n` levels in the blanket under it; each level over the cells of that top whose floor
	-- lies under it, joined into rectangles (no side over Roblox's widest part)
	local tops: { [number]: boolean } = {}
	for u = 1, nu do
		for v = 1, nv do
			local t = top[u][v]
			if t then
				record.fogged += 1
				local key = math.floor(t * 1000 + 0.5) / 1000
				top[u][v] = key
				tops[key] = true
			end
		end
	end
	local tr = Fog.sheetTransparency(n, spec.thick or Fog.THICK)
	local sheets = {}
	local order = {}
	for t in tops do
		table.insert(order, t)
	end
	table.sort(order)
	local mu, mv = math.max(1, math.floor(Fog.WIDEST / du)), math.max(1, math.floor(Fog.WIDEST / dv))
	local wanted = 0
	for _, t in order do
		for i = 1, n do
			local y = t - span * (i - 0.5) / n -- (sheet 1 just under the top, sheet n near the blanket's floor)
			local used: { [number]: boolean } = {}
			local function ok(a: number, b: number): boolean
				local f = floorOf[a][b]
				return top[a][b] == t and not used[a * 65536 + b] and f ~= nil and f < y
			end
			for v = 1, nv do
				for u = 1, nu do
					if ok(u, v) then
						local u1 = u
						while u1 + 1 <= nu and u1 + 1 - u < mu and ok(u1 + 1, v) do
							u1 += 1
						end
						local v1 = v
						local grow = true
						while grow and v1 + 1 <= nv and v1 + 1 - v < mv do
							for a = u, u1 do
								if not ok(a, v1 + 1) then
									grow = false
									break
								end
							end
							if grow then
								v1 += 1
							end
						end
						for a = u, u1 do
							for b = v, v1 do
								used[a * 65536 + b] = true
							end
						end
						wanted += 1
						if #sheets < Fog.MOST then
							table.insert(sheets, {
								size = { (u1 - u + 1) * du, Fog.SHEET, (v1 - v + 1) * dv },
								pos = { x0 + (u - 1 + u1) / 2 * du, y, z0 + (v - 1 + v1) / 2 * dv },
								transparency = tr,
								layer = i,
							})
						end
					end
				end
			end
		end
	end
	if wanted > Fog.MOST then
		table.insert(
			problems,
			`fog needs {wanted} sheets, over {Fog.MOST} - give a bigger "cell", fewer "layers" or a smaller "area" (nothing is cut by itself)`
		)
		return {}, {}, record, problems
	end
	record.sheets = #sheets
	-- mist: slow puffs over fogged cells, in the blanket, by the seed (the compiler's own Park-Miller)
	local mist = {}
	local want = spec.mist or 0
	if want > 0 and record.fogged > 0 then
		local state = (spec.seed or 1) % 2147483647
		if state <= 0 then
			state += 2147483646
		end
		local cells = {}
		for u = 1, nu do
			for v = 1, nv do
				if top[u][v] then
					table.insert(cells, { u, v })
				end
			end
		end
		for _ = 1, math.min(want, #cells) do
			state = (state * 48271) % 2147483647
			local k = math.floor(state / 2147483647 * #cells) + 1
			local c = table.remove(cells, k) :: { number }
			local t = top[c[1]][c[2]] :: number
			local f = math.max(floorOf[c[1]][c[2]] :: number, t - span)
			table.insert(mist, { pos = { x0 + (c[1] - 0.5) * du, f + (t - f) * 0.4, z0 + (c[2] - 0.5) * dv } })
		end
	end
	return sheets, mist, record, problems
end

return Fog

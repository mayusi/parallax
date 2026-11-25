-- worldcover.luau (kit) — SNOW AND DUST ON WHAT IS BUILT (the owner's method list: "Procedural snow / dust coverage").
-- The land is snowed on by its painter (a climate that freezes, a snowline, a season's swap). Roofs, walls' tops,
-- ledges, crates and steps stayed bare. A world's "cover" lays them:
--   "cover": { "snow": { "depth": 0.6, "above": 20 }, "dust": { "depth": 0.1 } }      (either, or both)
--   "cover": false                                                                    (none, meant)
-- Every level top of a square-standing block (turned about the vertical or not) is read cell by cell (cells of at
-- most CELL studs, at most SIDE a side) by a vertical line through each cell's middle, against every part (each by
-- its own turned box, not the box round it) and the land:
--   OPEN   nothing over it within OVER studs           -> snow (at or over "above")
--   ROOFED something over it, the lowest within ROOF   -> dust (a floor under a roof, a shelf in a room)
--   NONE   something standing on it or through it (a crate, a wall), the land over it (a tunnel), a roof higher
--          than ROOF (a bridge high over a square), or an earlier part's top lying flush with it there (that one
--          takes it; and each face's slabs lie a hair, LIFT, apart in height, so cells that overlap at two faces'
--          edges never lie in one plane)
-- The cells of a face that take the same are joined into rectangles: one slab each, the face's own turn, flush with
-- one another, a hair in from the face's own edges. Snow is solid (walked on); dust nobody touches.
-- An upright WEDGE (a gable roof's half) of SLIDE degrees or less takes snow along its slope when three quarters of
-- its cells see the sky: one slab on the slope, run a little past its high end so two halves meet over the ridge.
-- What takes nothing, counted: a ball, a cylinder, a tilted part or a steeper wedge (shapes); a seen-through stand-in
-- for a mesh (meshes: a mesh building's walls and roof are not snowed on - but its stand-ins DO count as a roof over
-- what is under them); a part that breaks or moves (loose: a slab would be left in the air).
-- A season may bring its own (kit/lib/worldseason.luau: "cover" in a season, false = none that season).
-- Pure: no file reads, no game calls.
local Cover = {}

Cover.MOST = 4000 -- slabs one world may get
Cover.SKY = 0.75 -- the share of a wedge's cells the sky must see for its slab
Cover.CELL = 2 -- studs a side of the cells a face is read in, at most
Cover.SIDE = 48 -- cells a side of a face, at most (a larger face is read in larger cells)
Cover.LOOK = 16 -- studs a side of the cells parts are looked up by
Cover.SLIDE = 50 -- degrees: on a roof steeper than this snow slides off
Cover.ROOF = 16 -- studs: something this close over a top makes it a room's (dust)
Cover.OVER = 40 -- studs: something higher over a top than this is open sky to it (a bridge high over a square)
Cover.ON = 0.05 -- studs: something reaching this close over a top stands on it
Cover.LIFT = 0.012 -- studs between the slabs of two faces that lie flush

local function number(v: any): boolean
	return type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge
end

-- what is wrong with a world's "cover", in words ({} = nothing)
function Cover.problems(spec: any): { string }
	if spec == false then
		return {}
	end
	if type(spec) ~= "table" then
		return { '"cover" is { "snow": { "depth" }, "dust": { "depth" } } or false' }
	end
	local out: { string } = {}
	for k in spec do
		if k ~= "snow" and k ~= "dust" then
			table.insert(out, `cover: "{tostring(k)}" is not a word it knows (snow, dust)`)
		end
	end
	if spec.snow == nil and spec.dust == nil then
		table.insert(out, 'cover: say "snow", "dust" or both (or "cover": false)')
	end
	local snow = spec.snow
	if snow ~= nil then
		if type(snow) ~= "table" then
			table.insert(out, 'cover: "snow" is { "depth": studs, "above": a height }')
		else
			for k in snow do
				if k ~= "depth" and k ~= "above" then
					table.insert(out, `cover.snow: "{tostring(k)}" is not a word it knows (depth, above)`)
				end
			end
			if not (number(snow.depth) and snow.depth >= 0.1 and snow.depth <= 4) then
				table.insert(out, 'cover.snow: "depth" is how thick it lies, 0.1 to 4 studs')
			end
			if snow.above ~= nil and not number(snow.above) then
				table.insert(out, 'cover.snow: "above" is the height under which no snow lies')
			end
		end
	end
	local dust = spec.dust
	if dust ~= nil then
		if type(dust) ~= "table" then
			table.insert(out, 'cover: "dust" is { "depth": studs }')
		else
			for k in dust do
				if k ~= "depth" then
					table.insert(out, `cover.dust: "{tostring(k)}" is not a word it knows (depth)`)
				end
			end
			if not (number(dust.depth) and dust.depth >= 0.02 and dust.depth <= 0.5) then
				table.insert(out, 'cover.dust: "depth" is how thick it lies, 0.02 to 0.5 studs')
			end
		end
	end
	return out
end

local function mul(a: { { number } }, b: { { number } }): { { number } }
	local out = {}
	for r = 1, 3 do
		out[r] = {}
		for c = 1, 3 do
			out[r][c] = a[r][1] * b[1][c] + a[r][2] * b[2][c] + a[r][3] * b[3][c]
		end
	end
	return out
end

local function key(i: number, j: number): number
	return (i + 1048576) * 2097152 + (j + 1048576)
end

-- the part a mesh stands for (seen through: the mesh is what is seen)
local function standIn(p: any): boolean
	local a = p.attributes
	return p.mesh ~= nil or (type(a) == "table" and (a.KitBlockout ~= nil or a.KitDress ~= nil))
end

-- does a part count as something over a top (a roof, a crate on it, a canopy)
local function solid(p: any): boolean
	if p.backdrop or p.fog or p.cover == true then
		return false
	end
	return (p.transparency or 0) < 0.5 or standIn(p)
end

-- the vertical line through (x, z) against a part's own turned box -> the heights it is inside between, or nil
local function span(p: any, x: number, z: number): (number?, number?)
	local r = p.rot
	local dx, dz = x - p.pos[1], z - p.pos[3]
	local lo, hi = -math.huge, math.huge
	for a = 1, 3 do
		-- (local coordinate along axis a at height y: q + (y - pos.y) * rate)
		local q = r[1][a] * dx + r[3][a] * dz
		local rate = r[2][a]
		local half = p.size[a] / 2
		if math.abs(rate) < 1e-9 then
			if math.abs(q) > half + 1e-9 then
				return nil, nil
			end
		else
			local t1, t2 = (-half - q) / rate, (half - q) / rate
			if t1 > t2 then
				t1, t2 = t2, t1
			end
			lo, hi = math.max(lo, t1), math.min(hi, t2)
		end
	end
	if lo > hi then
		return nil, nil
	end
	return p.pos[2] + lo, p.pos[2] + hi
end

-- a part's box along the world's axes (for the look-up cells)
local function box(p: any): (number, number, number, number)
	local ex = math.abs(p.rot[1][1]) * p.size[1] / 2
		+ math.abs(p.rot[1][2]) * p.size[2] / 2
		+ math.abs(p.rot[1][3]) * p.size[3] / 2
	local ez = math.abs(p.rot[3][1]) * p.size[1] / 2
		+ math.abs(p.rot[3][2]) * p.size[2] / 2
		+ math.abs(p.rot[3][3]) * p.size[3] / 2
	return p.pos[1] - ex, p.pos[3] - ez, p.pos[1] + ex, p.pos[3] + ez
end

-- the cells of a grid that take the same, joined into rectangles -> { { u0, v0, u1, v1 } } (cells, inclusive)
local function rectangles(grid: { { string } }, nu: number, nv: number, want: string): { { number } }
	local used: { [number]: boolean } = {}
	local out = {}
	for v = 1, nv do
		for u = 1, nu do
			if grid[u][v] == want and not used[u * 4096 + v] then
				local u1 = u
				while u1 + 1 <= nu and grid[u1 + 1][v] == want and not used[(u1 + 1) * 4096 + v] do
					u1 += 1
				end
				local v1 = v
				local grow = true
				while grow and v1 + 1 <= nv do
					for uu = u, u1 do
						if grid[uu][v1 + 1] ~= want or used[uu * 4096 + v1 + 1] then
							grow = false
							break
						end
					end
					if grow then
						v1 += 1
					end
				end
				for uu = u, u1 do
					for vv = v, v1 do
						used[uu * 4096 + vv] = true
					end
				end
				table.insert(out, { u, v, u1, v1 })
			end
		end
	end
	return out
end

-- THE SLABS: parts = every part of the world (as it stands, after every move); ground(x, z) = the land's height there
-- (nil: none) -> slabs (each a Part-like table: kind = "snow" | "dust", owner = the index of the part it lies on),
-- a record { snow, dust (slabs), faces (faces that took any), shapes, meshes, loose, capped }
function Cover.lay(parts: { any }, spec: any, ground: ((number, number) -> number?)?): ({ any }, any)
	local record = { snow = 0, dust = 0, faces = 0, shapes = 0, meshes = 0, loose = 0, capped = false }
	if type(spec) ~= "table" then
		return {}, record
	end
	local cells: { [number]: { number } } = {}
	for idx, p in parts do
		if solid(p) then
			local x0, z0, x1, z1 = box(p)
			for i = math.floor(x0 / Cover.LOOK), math.floor(x1 / Cover.LOOK) do
				for j = math.floor(z0 / Cover.LOOK), math.floor(z1 / Cover.LOOK) do
					local k = key(i, j)
					cells[k] = cells[k] or {}
					table.insert(cells[k], idx)
				end
			end
		end
	end
	-- what lies over (x, top, z): "open" | "roof" | "none"
	local function over(x: number, top: number, z: number, own: number): string
		if ground then
			local g = ground(x, z)
			if g ~= nil and g > top + Cover.ON then
				return "none" -- (buried in the land)
			end
		end
		local lowest = math.huge
		for _, idx in cells[key(math.floor(x / Cover.LOOK), math.floor(z / Cover.LOOK))] or {} do
			if idx ~= own then
				local lo, hi = span(parts[idx], x, z)
				-- (two tops lying flush: the first part's face takes the cell, the later one's none)
				if lo and hi and idx < own and math.abs(hi - top) <= Cover.ON then
					return "none"
				end
				if lo and hi and hi > top + Cover.ON then
					if lo <= top + Cover.ON then
						return "none" -- (it stands on the top, or through it)
					end
					lowest = math.min(lowest, lo)
				end
			end
		end
		if lowest - top <= Cover.ROOF then
			return "roof"
		elseif lowest - top <= Cover.OVER then
			return "none"
		end
		return "open"
	end
	local out = {}
	local function full(): boolean
		if #out >= Cover.MOST then
			record.capped = true
			return true
		end
		return false
	end
	for idx, p in parts do
		if p.backdrop or p.spawn or p.fog or p.cover == true then
			continue
		end
		if standIn(p) then
			record.meshes += 1
			continue
		end
		if (p.transparency or 0) >= 0.5 then
			continue
		end
		local a = p.attributes
		if p.anchored == false or (type(a) == "table" and a.KitBreakable ~= nil) then
			record.loose += 1
			continue
		end
		if p.class == "WedgePart" then
			-- (a Roblox wedge is full height at its local +Z and nothing at its -Z: its slope rises toward +Z)
			local w, h, d = p.size[1], p.size[2], p.size[3]
			local slope = math.deg(math.atan2(h, d))
			if not spec.snow then
				continue -- (dust lies on no slope)
			end
			if p.rot[2][2] < 0.999 or slope > Cover.SLIDE then
				record.shapes += 1
				continue
			end
			if spec.snow.above ~= nil and p.pos[2] + h / 2 < spec.snow.above then
				continue
			end
			local nu = math.clamp(math.ceil(w / Cover.CELL), 1, Cover.SIDE)
			local nv = math.clamp(math.ceil(d / Cover.CELL), 1, Cover.SIDE)
			local open = 0
			for iu = 1, nu do
				for iv = 1, nv do
					local du = ((iu - 0.5) / nu - 0.5) * w
					local dv = ((iv - 0.5) / nv - 0.5) * d
					local x = p.pos[1] + p.rot[1][1] * du + p.rot[1][3] * dv
					local z = p.pos[3] + p.rot[3][1] * du + p.rot[3][3] * dv
					if over(x, p.pos[2] + dv * h / d, z, idx) == "open" then
						open += 1
					end
				end
			end
			if open / (nu * nv) < Cover.SKY or full() then
				continue
			end
			local depth = spec.snow.depth
			local L = math.sqrt(h * h + d * d)
			-- run past the high end by depth * h / d: two halves of a gable meet over the ridge, no groove
			local extra = depth * h / d
			local tilt = { { 1, 0, 0 }, { 0, d / L, h / L }, { 0, -h / L, d / L } }
			-- (out of the slope by half the depth, and up it by half the extra)
			local n = {
				0,
				d / L * depth / 2 + h / L * extra / 2,
				-h / L * depth / 2 + d / L * extra / 2,
			}
			table.insert(out, {
				kind = "snow",
				name = "Snow",
				class = "Part",
				size = { math.max(0.05, w - 0.02), depth, L + extra },
				pos = {
					p.pos[1] + p.rot[1][1] * n[1] + p.rot[1][2] * n[2] + p.rot[1][3] * n[3],
					p.pos[2] + p.rot[2][1] * n[1] + p.rot[2][2] * n[2] + p.rot[2][3] * n[3],
					p.pos[3] + p.rot[3][1] * n[1] + p.rot[3][2] * n[2] + p.rot[3][3] * n[3],
				},
				rot = mul(p.rot, tilt),
				color = { 242, 246, 252 },
				material = "Snow",
				transparency = 0,
				collide = true,
				anchored = true,
				axisAligned = false,
				cover = true,
				slope = slope,
				owner = idx,
			})
			record.snow += 1
			record.faces += 1
			continue
		end
		-- a level top: the local axis that stands upright
		local up: number? = nil
		if p.class == "Part" and (p.shape == nil or p.shape == "Block") then
			for ax = 1, 3 do
				if math.abs(math.abs(p.rot[2][ax]) - 1) < 1e-6 then
					up = ax
				end
			end
		end
		if up == nil then
			record.shapes += 1
			continue
		end
		local top = p.pos[2] + p.size[up] / 2
		local u = if up == 1 then 2 else 1
		local v = if up == 3 then 2 else 3
		local su, sv = p.size[u], p.size[v]
		local nu = math.clamp(math.ceil(su / Cover.CELL), 1, Cover.SIDE)
		local nv = math.clamp(math.ceil(sv / Cover.CELL), 1, Cover.SIDE)
		local cu, cv = su / nu, sv / nv
		local grid: { { string } } = {}
		local snowOk = spec.snow ~= nil and (spec.snow.above == nil or top >= spec.snow.above)
		for iu = 1, nu do
			grid[iu] = {}
			for iv = 1, nv do
				local du = -su / 2 + (iu - 0.5) * cu
				local dv = -sv / 2 + (iv - 0.5) * cv
				local x = p.pos[1] + p.rot[1][u] * du + p.rot[1][v] * dv
				local z = p.pos[3] + p.rot[3][u] * du + p.rot[3][v] * dv
				local seen = over(x, top, z, idx)
				local takes = if seen == "open" and snowOk
					then "snow"
					elseif seen == "roof" and spec.dust ~= nil then "dust"
					else "none"
				grid[iu][iv] = takes
			end
		end
		local took = false
		for _, kind in { "snow", "dust" } do
			local depth = if kind == "snow" then (spec.snow and spec.snow.depth) else (spec.dust and spec.dust.depth)
			if depth then
				for _, rc in rectangles(grid, nu, nv, kind) do
					if full() then
						break
					end
					-- (a hair in from the face's own edges only: inner slabs meet flush)
					local u0 = -su / 2 + (rc[1] - 1) * cu + (if rc[1] == 1 then 0.01 else 0)
					local u1 = -su / 2 + rc[3] * cu - (if rc[3] == nu then 0.01 else 0)
					local v0 = -sv / 2 + (rc[2] - 1) * cv + (if rc[2] == 1 then 0.01 else 0)
					local v1 = -sv / 2 + rc[4] * cv - (if rc[4] == nv then 0.01 else 0)
					local mu, mv = (u0 + u1) / 2, (v0 + v1) / 2
					local size = { p.size[1], p.size[2], p.size[3] }
					size[up] = depth
					size[u] = math.max(0.02, u1 - u0)
					size[v] = math.max(0.02, v1 - v0)
					table.insert(out, {
						kind = kind,
						name = if kind == "snow" then "Snow" else "Dust",
						class = "Part",
						size = size,
						pos = {
							p.pos[1] + p.rot[1][u] * mu + p.rot[1][v] * mv,
							-- (a hair over the face, by the part's place in the list: where two faces' cells still
							-- overlap at their edges, their slabs never lie in one plane)
							top + depth / 2 + (idx % 4) * Cover.LIFT,
							p.pos[3] + p.rot[3][u] * mu + p.rot[3][v] * mv,
						},
						rot = p.rot,
						color = if kind == "snow" then { 242, 246, 252 } else { 150, 138, 118 },
						material = if kind == "snow" then "Snow" else "Sand",
						transparency = if kind == "snow" then 0 else 0.35,
						collide = kind == "snow",
						query = if kind == "dust" then false else nil,
						castShadow = if kind == "dust" then false else nil,
						anchored = true,
						axisAligned = p.axisAligned,
						cover = true,
						owner = idx,
					})
					record[kind] += 1
					took = true
				end
			end
		end
		if took then
			record.faces += 1
		end
	end
	return out, record
end

return Cover

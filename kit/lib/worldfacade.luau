--!strict
-- worldfacade.luau (kit) - A FACADE GRAMMAR: a house front split into storeys, each storey's wall into its openings
-- and the plain runs between them, each piece filled by ONE OF A SMALL SET OF MODULES stretched to fit.
--
-- Why (the audit of 2026-11-13, rank 5; card yzvz): a town's look was one whole-house mesh per house TYPE - 30 to 65
-- meshes for one town, each with its own texture, and two houses of one type are the same house. A split grammar
-- (Mueller et al., "Procedural Modeling of Buildings", 2006: facade -> floors -> tiles) makes every house from the
-- same few pieces: 5 a storey height (wall, window, a second window, door, oriel) and 3 for the town (band, roof,
-- chimney). Which window a house wears, and whether it has an oriel, comes from the house's own seed - houses of one
-- type differ, the town keeps one rhythm.
--
-- What is NOT here: the module meshes themselves (kit world meshes, kind "gothic_module": Blender), and the
-- openings - the compiler's own gaps are the grammar's input, so what you see and what you walk through are one
-- layout by construction. Pure: no requires, no files.
local Facade = {}

-- the modules a storey height needs, and the ones a town needs once
Facade.STOREY = { "wall", "window", "windowb", "door", "oriel" }
Facade.TOWN = { "band", "roof", "chimney" }
Facade.PANEL = 4 -- studs: a plain wall module's own width; a run is filled by whole panels stretched to fit
Facade.BAND = 8 -- studs: a band module's own length
Facade.ROOF = { 20, 24 } -- studs: the roof module's own front x depth
Facade.ROOF_SCALE = { 0.5, 2.2 } -- the roof module grown or shrunk past this with its front: slates the wrong size
Facade.ROOF_SKEW = { 0.6, 1.6 } -- its depth stretched this much more than its front: past it the slates smear
Facade.ORIEL_OUT = 2 -- studs: an oriel stands this far out of the wall's face
Facade.ORIEL_ONE_IN = 3 -- one house in three with an upper storey wears an oriel over its door
-- a kit's OPTIONAL storey module: when the registry holds "<prefix>_quoin_<storey height>" (the W3 kit makes one), it
-- stands up every corner of every storey, its blocks reaching QUOIN_REACH studs along each face from the corner's
-- outer edge (the walls' modules meet on their centre lines: the quoin closes the corner they leave open)
Facade.EXTRA = { "quoin" }
Facade.QUOIN_REACH = 2.6
-- the kits a module may be cut from (recipe field "kit"; none = kit/world/gothic_blender.py's own ashlar and atlas):
-- "w3" = the W3 modular kit on its two shared trim sheets (kit/world/modkit_facade.py)
Facade.KITS = { w3 = true }

-- (a storey height in a name: to a thousandth, so 13.3 and 13.34 are two names - to a tenth they were one, and
-- one of the two heights' houses could never find a module that fits)
local function fmt(n: number): string
	if n == math.floor(n) then
		return tostring(n)
	end
	return (string.format("%.3f", n):gsub("0+$", ""):gsub("%.$", ""))
end

-- a module's mesh name: "<prefix>_<kind>_<storey height>" for a storey's modules, "<prefix>_<kind>" for the town's
function Facade.name(prefix: string, kind: string, floorHeight: number?): string
	if table.find(Facade.TOWN, kind) then
		return `{prefix}_{kind}`
	end
	return `{prefix}_{kind}_{fmt(floorHeight or 14)}`
end

-- what a house's own seed decides: { windowKind, oriel: boolean }
-- (the seed is MIXED first, every bit of it into every bit of the result: houses along a street have seeds a fixed
-- step apart, and read straight off the seed their windows alternated house by house and the whole pattern came
-- round every sixth house; one multiply left a street of the same window)
local function mul32(a: number, b: number): number
	local lo, hi = bit32.band(a, 0xFFFF), bit32.rshift(a, 16)
	return (lo * b + (hi * b % 65536) * 65536) % 4294967296
end
local function mix(seed: number, salt: number): number
	local x = (math.floor(math.abs(seed)) + salt * 2654435769) % 4294967296
	x = bit32.bxor(x, bit32.rshift(x, 16))
	x = mul32(x, 0x45D9F3B)
	x = bit32.bxor(x, bit32.rshift(x, 16))
	x = mul32(x, 0x45D9F3B)
	return bit32.bxor(x, bit32.rshift(x, 16))
end
function Facade.pick(seed: number, floors: number): (string, boolean)
	return if mix(seed, 1) % 2 == 0 then "window" else "windowb",
		floors >= 2 and mix(seed, 2) % Facade.ORIEL_ONE_IN == 0
end

-- does this house carry a chimney (about half do)
function Facade.chimney(seed: number): boolean
	return mix(seed, 3) % 2 == 0
end

-- ONE STOREY OF ONE WALL, split: its gaps (as the compiler cut them: { at, width, sill? }, `at` from the wall's
-- start) become door / window modules, the runs between them whole wall panels.
-- opts: { window = "window" | "windowb", oriel = <index of the gap that is an oriel>? }
-- -> { { kind, at, width } } in order along the wall, covering 0..len exactly (no gap, no overlap)
function Facade.wall(len: number, gaps: { any }, opts: any?): { any }
	local o = opts or {}
	local sorted = table.clone(gaps)
	table.sort(sorted, function(a, b)
		return a.at < b.at
	end)
	local out = {}
	local function run(a: number, b: number)
		local w = b - a
		if w <= 0.01 then
			return
		end
		local n = math.max(1, math.floor(w / Facade.PANEL + 0.5))
		for i = 1, n do
			table.insert(out, { kind = "wall", at = a + (i - 0.5) * w / n, width = w / n })
		end
	end
	local cursor = 0
	for i, g in sorted do
		local gs, ge = g.at - g.width / 2, g.at + g.width / 2
		-- (a gap outside the wall or over the one before: the compiler already said it; one with no width, or no
		-- number for its place, is no opening)
		if not (g.width > 0.01) or g.at ~= g.at or gs < cursor - 1e-6 or ge > len + 1e-6 then
			continue
		end
		run(cursor, gs)
		local kind = if (g.sill or 0) <= 0 then "door" elseif o.oriel == i then "oriel" else (o.window or "window")
		table.insert(out, { kind = kind, at = g.at, width = g.width })
		cursor = ge
	end
	run(cursor, len)
	return out
end

-- a band along a wall of `len`: whole band modules stretched to fit -> { { at, width } }
function Facade.band(len: number): { any }
	local n = math.max(1, math.floor(len / Facade.BAND + 0.5))
	local out = {}
	for i = 1, n do
		table.insert(out, { at = (i - 0.5) * len / n, width = len / n })
	end
	return out
end

-- THE ROOF over a house `front` wide and `depth` deep, from the module modelled `own` = { front, height, depth }:
-- grown with the house's front (its height with it: the pitch stays the module's own), and along the ridge as many
-- whole modules one behind the other as keep each one's slates nearest their own shape (a gable roof is the same
-- section all along its ridge, so they join without a seam).
-- -> { scale (front and height), turned, tiles = { { at (along the ridge, from its middle), stretch (along it) } } }
-- The gable faces the street, as a town house's does - unless the house is so much wider than deep (a landmark,
-- 41 x 25) that the module would be squeezed along its ridge past ROOF_SKEW: then the ridge runs along the front
-- (`turned`: the module a quarter turn round), where that smears it less.
function Facade.roof(front: number, depth: number, own: { number }): any
	local function lay(f: number, d: number): (number, number, number)
		local scale = f / own[1]
		local n = math.max(1, math.floor(d / (own[3] * scale) + 0.5))
		return scale, n, d / n / own[3] / scale -- (its size, how many along the ridge, each one's skew)
	end
	local scale, n, skew = lay(front, depth)
	local turned = false
	if skew < Facade.ROOF_SKEW[1] or skew > Facade.ROOF_SKEW[2] then
		local s2, n2, skew2 = lay(depth, front)
		if math.abs(math.log(skew2)) < math.abs(math.log(skew)) then
			turned = true
			front, depth = depth, front
			scale, n = s2, n2
		end
	end
	local tiles = {}
	for i = 1, n do
		table.insert(tiles, { at = -depth / 2 + (i - 0.5) * depth / n, stretch = depth / n / own[3] })
	end
	return { scale = scale, tiles = tiles, turned = turned }
end

-- THE KIT A TOWN NEEDS: one recipe a module (kit world meshes, kind "gothic_module"), each with the box it is
-- modelled at and, for a door or a window, the opening it must leave.
-- look: { prefix, floorHeights: { number }, thickness, door: { width, height }, window: { width, height, sill },
-- kit?: "w3" (cut from the W3 modular kit on its two shared trim sheets, kit/world/modkit_facade.py: every recipe says
-- so, and a quoin a storey height joins them) }
function Facade.kit(look: any): { any }
	local out = {}
	local heights, named = {}, {}
	for _, fh in look.floorHeights do
		local key = Facade.name(look.prefix, "wall", fh)
		if not named[key] then -- (two heights one name are one height)
			named[key] = true
			table.insert(heights, fh)
		end
	end
	table.sort(heights)
	local t = look.thickness
	for _, fh in heights do
		for _, kind in Facade.STOREY do
			local recipe: any = {
				name = Facade.name(look.prefix, kind, fh),
				kind = "gothic_module",
				module = kind,
				floorHeight = fh,
				thickness = t,
			}
			if kind == "wall" then
				recipe.size = { Facade.PANEL, fh, t }
			elseif kind == "door" then
				recipe.size = { look.door.width, fh, t }
				recipe.gap = { width = look.door.width, height = look.door.height, sill = 0 }
			else
				-- (an oriel is the window's opening with a bay standing out in front of the wall)
				recipe.size = { look.window.width, fh, if kind == "oriel" then t + Facade.ORIEL_OUT else t }
				recipe.gap = { width = look.window.width, height = look.window.height, sill = look.window.sill }
			end
			table.insert(out, recipe)
		end
		if look.kit == "w3" then
			table.insert(out, {
				name = Facade.name(look.prefix, "quoin", fh),
				kind = "gothic_module",
				module = "quoin",
				floorHeight = fh,
				thickness = t,
				size = { Facade.QUOIN_REACH + 0.15, fh, Facade.QUOIN_REACH + 0.15 },
			})
		end
	end
	table.insert(out, {
		name = Facade.name(look.prefix, "band"),
		kind = "gothic_module",
		module = "band",
		size = { Facade.BAND, 0.7, 0.6 },
		thickness = t, -- (the wall it stands proud of)
	})
	table.insert(out, {
		name = Facade.name(look.prefix, "roof"),
		kind = "gothic_module",
		module = "roof",
		size = { Facade.ROOF[1], Facade.ROOF[1] * 0.7, Facade.ROOF[2] },
	})
	table.insert(out, {
		name = Facade.name(look.prefix, "chimney"),
		kind = "gothic_module",
		module = "chimney",
		size = { 2.4, 7, 2.4 },
	})
	if look.kit ~= nil then
		for _, r in out do
			r.kit = look.kit
		end
	end
	return out
end

local function close(a: any, b: any): boolean
	return type(a) == "number" and type(b) == "number" and math.abs(a - b) <= 0.05
end

-- why this module cannot fill this place (nil = it can). reg = its entry in the mesh registry; want = { kind,
-- floorHeight?, gap?: { width, height, sill }, front?, depth? }
function Facade.problem(reg: any, name: string, want: any): string?
	if type(reg) ~= "table" then
		return `no world mesh "{name}" - a facade needs its modules: lune run kit world town <Name> --kit, then kit world meshes --set <list>`
	end
	if reg.kind ~= "gothic_module" or reg.module ~= want.kind then
		return `the mesh "{name}" is no "{want.kind}" module (it is a {tostring(reg.kind)}{if reg.module
			then " " .. tostring(reg.module)
			else ""})`
	end
	-- (its box and its origin are what places it: without them the compiler has nothing to stretch)
	for _, k in { "size", "min" } do
		local v = reg[k]
		if type(v) ~= "table" or type(v[1]) ~= "number" or type(v[2]) ~= "number" or type(v[3]) ~= "number" then
			return `the module "{name}" has no {k} in the registry (three numbers): make it again, kit world meshes`
		end
	end
	if reg.size[1] <= 0 or reg.size[2] <= 0 or reg.size[3] <= 0 then
		return `the module "{name}" has no size in the registry: make it again, kit world meshes`
	end
	if want.floorHeight and not close(reg.floorHeight, want.floorHeight) then
		return `the module "{name}" is made for a storey of {tostring(reg.floorHeight)}, the house's is {want.floorHeight}`
	end
	if want.gap then
		local g = if type(reg.gap) == "table" then reg.gap else {}
		for _, k in { "width", "height", "sill" } do
			if not close(g[k], want.gap[k]) then
				return `the module "{name}"'s opening has {k} {tostring(g[k])}, the house's {want.gap[k]} (you would see a doorway where the wall is, or walk into stone)`
			end
		end
	end
	if want.kind == "roof" then
		local size = reg.size
		local r = Facade.roof(want.front, want.depth, size)
		if r.scale < Facade.ROOF_SCALE[1] or r.scale > Facade.ROOF_SCALE[2] then
			return `the roof module "{name}" ({size[1]} wide) would be {string.format("%.2f", r.scale)} times its size on a front of {want.front}: past {Facade.ROOF_SCALE[1]}..{Facade.ROOF_SCALE[2]} its slates are the wrong size beside the next house's`
		end
		local skew = r.tiles[1].stretch / r.scale
		if skew < Facade.ROOF_SKEW[1] or skew > Facade.ROOF_SKEW[2] then
			return `the roof module "{name}" would be stretched {string.format("%.2f", skew)} times more along the house's depth ({want.depth}) than along its front ({want.front}): past {Facade.ROOF_SKEW[1]}..{Facade.ROOF_SKEW[2]} its slates smear`
		end
	end
	return nil
end

return Facade

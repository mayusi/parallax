-- interior.luau — furnished rooms by RULES (world mission ladder 2: interiors for the keep). The building generator
-- hands each floor's inner room, what must stay clear (the stair lane and its landings, the stairwell, the door's
-- swing and the path in) and its windows; Interior.layout returns the furniture, Interior.check proves the rules:
--   * every piece stands against a wall (its back to it) inside the room
--   * every piece keeps a 4-stud WALKWAY clear in front of its open face (no piece in another's walkway)
--   * nothing on the stair lane, its landings or in a door's clearance; nothing taller than a sill under a window
--   * A BODY CAN WALK IT (Interior.walk; the owner's limitations list, W-R06: "interior validation is primarily
--     rectangular 2D clearance ... furniture placement must preserve actual interaction / movement"): from the door
--     a body BODY studs wide reaches every piece's open side and every other way in or out of the room (the
--     stairs), and OPEN of the floor is left free. The rectangle rules alone let a piece's walkway be shut in by
--     its neighbours, and a row of pieces cut a room in two.
-- Rooms by kind (Interior.KINDS): "hall" (a long table with benches, a hearth with firelight, barrels), "chamber" (bed, chest at its
-- foot, shelf, desk + stool), "store" (weapon racks, crates), "kitchen" (oven, worktable, stores), "study" (bookcases,
-- desk, lectern), "workshop" (bench, tool rack, anvil), "stair_shaft" (bench, light, chest by the flight), "landing"
-- (chest, light, bench, side table), "sanctum" (a lit altar, pews, lectern, candelabras); Interior.program names a
-- floor's rooms by size (interior_v2). Pure: no Roblox APIs; kit/test/spec/interior.spec.luau, interiorv2.spec.luau.
local Interior = {}

Interior.WALKWAY = 4
Interior.BODY = 2.5 -- studs: an R6 body (2 wide) with a hand's breadth each side - what must pass
Interior.CELL = 0.5 -- studs: the grid a room is walked on (a gap under BODY never passes, one of BODY + CELL always
-- does; between the two it depends on where the gap falls on the grid, and reads as shut)
-- the least share of a room's floor that furniture leaves free (LIMITATIONS_FIXES_V3.md stage D: furniture covers at
-- most 40 % of a room's floor; it was 70 %, and measured over 972 rooms the layouts covered up to 46.6 %)
Interior.OPEN = 0.6
Interior.LOST = 0.15 -- the most of the floor a body could stand on that furniture may wall off from the way in
-- pieces that keep APART, the least gap between their footprints (studs; V3 stage D: "dining tables strictly >= 6
-- studs clear of hearths and beds" - a hall's table stood 4.5 from its hearth in 18 of 100 measured halls, the
-- walkway rule alone allowed it): { a, b, studs }
Interior.APART = { { "Table", "Hearth", 6 }, { "Table", "Bed", 6 } }
-- THE SPINE (V3 stage D: "a >= 4.5-stud clear circulation spine"): a way SPINE studs wide from the room's way in to
-- every other way in (the stairs, a second door) and on into the far half of the room - the route a room is crossed
-- by, wider than the BODY that reaches each piece. Where it ends: at the ways in and the room's middle line; a
-- piece is reached off it by the narrower BODY. A room too small to hold it even empty is not held to it.
Interior.SPINE = 4.5
-- NO SLIVERS (V3 stage D: "a >= 3.2-stud furniture gap"): two pieces stand flush (TOUCH or less apart) or at least
-- GAP apart - a gap between that is too narrow to walk and too wide to read as one piece of furniture; measured over
-- 972 generated rooms, 2,965 pairs stood in such a gap (2,527 under a stud). A table and its benches are one group.
Interior.GAP = 3.2
Interior.TOUCH = 0.05

-- the gap between two footprints (0 when they touch or overlap)
local function gapOf(a: Rect, b: Rect): number
	local dx = math.max(0, math.max(a.x0, b.x0) - math.min(a.x1, b.x1))
	local dz = math.max(0, math.max(a.z0, b.z0) - math.min(a.z1, b.z1))
	return math.sqrt(dx * dx + dz * dz)
end

-- the least gap two pieces keep by name (0 = no rule)
local function apart(a: string, b: string): number
	for _, r in Interior.APART do
		if (r[1] == a and r[2] == b) or (r[1] == b and r[2] == a) then
			return r[3]
		end
	end
	return 0
end

-- a sliver between two footprints (neither flush nor GAP apart)
local function sliver(a: Rect, b: Rect): (boolean, number)
	local g = gapOf(a, b)
	return g > Interior.TOUCH and g < Interior.GAP - 1e-6, g
end

export type Rect = { x0: number, x1: number, z0: number, z1: number }
export type Piece = {
	name: string,
	role: string, -- "wood" | "cloth" | "stone" | "metal" | "fire"
	size: { number }, -- { x, y, z } after the yaw
	pos: { number }, -- centre
	front: Rect?, -- the walkway it keeps clear
	light: boolean?, -- a fire in its mouth (a hearth)
	flame: boolean?, -- a candle flame on top
	flat: boolean?, -- on the floor, walked over (a rug): never blocks
	key: boolean?, -- what the room is FOR (the hearth, a bed, the first weapon rack): the last thing taken out
}
export type Room = {
	x0: number,
	x1: number,
	z0: number,
	z1: number,
	y: number,
	height: number,
	clear: { Rect }?, -- must stay empty (stairs, landings, doors)
	door: string?, -- the side the door is on ("N" | "E" | "S" | "W"; upper floors: the stairs' arrival side)
	windows: { { side: string, from: number, to: number, sill: number } }?,
}

local function overlaps(a: Rect, b: Rect): boolean
	return a.x0 < b.x1 - 1e-6 and b.x0 < a.x1 - 1e-6 and a.z0 < b.z1 - 1e-6 and b.z0 < a.z1 - 1e-6
end
Interior.overlaps = overlaps

local function footprint(p: Piece): Rect
	return {
		x0 = p.pos[1] - p.size[1] / 2,
		x1 = p.pos[1] + p.size[1] / 2,
		z0 = p.pos[3] - p.size[3] / 2,
		z1 = p.pos[3] + p.size[3] / 2,
	}
end
Interior.footprint = footprint

-- the pieces a room of `kind` asks for, in placing order: { name, role, w (along the wall), h, d (out from it), light }
-- (away = this piece prefers the wall OPPOSITE the door: a hearth faces you as you come in, beds sit away from it;
--  fire = lit in its mouth, flame = a candle flame on top)
local WANTS = {
	hall = {
		{ name = "Hearth", role = "stone", w = 7, h = 8, d = 2.5, fire = true, away = true },
		{ name = "Cupboard", role = "wood", w = 6, h = 7, d = 2 },
		{ name = "Candelabra", role = "metal", w = 1.5, h = 5.5, d = 1.5, flame = true },
		{ name = "Candelabra", role = "metal", w = 1.5, h = 5.5, d = 1.5, flame = true },
		{ name = "Barrel", role = "wood", w = 2.5, h = 3.5, d = 2.5 },
		{ name = "Barrel", role = "wood", w = 2.5, h = 3.5, d = 2.5 },
		{ name = "Bench", role = "wood", w = 7, h = 1.8, d = 1.4 },
	},
	chamber = {
		{ name = "Bed", role = "cloth", w = 4.5, h = 2.4, d = 7.5, away = true },
		{ name = "Bed", role = "cloth", w = 4.5, h = 2.4, d = 7.5, away = true },
		{ name = "Wardrobe", role = "wood", w = 5, h = 8, d = 2.5 },
		{ name = "Shelf", role = "wood", w = 6, h = 8, d = 1.6 },
		{ name = "Desk", role = "wood", w = 5, h = 3, d = 2.5 },
		{ name = "Candelabra", role = "metal", w = 1.5, h = 5.5, d = 1.5, flame = true },
		{ name = "Chest", role = "wood", w = 3.5, h = 2.5, d = 2.2 },
		{ name = "Chest", role = "wood", w = 3.5, h = 2.5, d = 2.2 },
	},
	store = {
		{ name = "WeaponRack", role = "wood", w = 6, h = 6.5, d = 1.5, away = true },
		{ name = "WeaponRack", role = "wood", w = 6, h = 6.5, d = 1.5 },
		{ name = "ArmorStand", role = "metal", w = 2.5, h = 6, d = 2.5 },
		{ name = "Crate", role = "wood", w = 3.5, h = 3.5, d = 3.5 },
		{ name = "Crate", role = "wood", w = 3.5, h = 3.5, d = 3.5 },
		{ name = "Crate", role = "wood", w = 3, h = 3, d = 3 },
		{ name = "Barrel", role = "wood", w = 2.5, h = 3.5, d = 2.5 },
		{ name = "Sack", role = "cloth", w = 2.5, h = 2, d = 2.5 },
		{ name = "Sack", role = "cloth", w = 2.5, h = 2, d = 2.5 },
	},
	-- (LIMITATIONS_FIXES_V3.md stage D: room kinds "beyond 3 box archetypes (hall, chamber, store)"; a house's floors
	-- name them: "interior": { "floors": ["kitchen", "chamber", "study"] })
	kitchen = { -- the oven faces you as you come in; a worktable, shelves, stores
		{ name = "Oven", role = "stone", w = 6, h = 6, d = 3, fire = true, away = true },
		{ name = "Worktable", role = "wood", w = 6, h = 3, d = 3 },
		{ name = "Cupboard", role = "wood", w = 5, h = 7, d = 2 },
		{ name = "Shelf", role = "wood", w = 5, h = 7, d = 1.6 },
		{ name = "Barrel", role = "wood", w = 2.5, h = 3.5, d = 2.5 },
		{ name = "Barrel", role = "wood", w = 2.5, h = 3.5, d = 2.5 },
		{ name = "Sack", role = "cloth", w = 2.5, h = 2, d = 2.5 },
	},
	study = { -- books away from the door, a desk lit by a candelabra, a lectern, a chest
		{ name = "Bookcase", role = "wood", w = 6, h = 9, d = 1.6, away = true },
		{ name = "Bookcase", role = "wood", w = 6, h = 9, d = 1.6 },
		{ name = "Desk", role = "wood", w = 5, h = 3, d = 2.5 },
		{ name = "Candelabra", role = "metal", w = 1.5, h = 5.5, d = 1.5, flame = true },
		{ name = "Lectern", role = "wood", w = 2, h = 4, d = 2 },
		{ name = "Chest", role = "wood", w = 3.5, h = 2.5, d = 2.2 },
	},
	workshop = { -- the bench is what the room is for; tools on the wall, an anvil, stock
		{ name = "Workbench", role = "wood", w = 7, h = 3.2, d = 3, away = true },
		{ name = "ToolRack", role = "wood", w = 5, h = 6, d = 1 },
		{ name = "Anvil", role = "metal", w = 2.5, h = 2.5, d = 1.5 },
		{ name = "Crate", role = "wood", w = 3.5, h = 3.5, d = 3.5 },
		{ name = "Crate", role = "wood", w = 3, h = 3, d = 3 },
		{ name = "Barrel", role = "wood", w = 2.5, h = 3.5, d = 2.5 },
	},
	-- (LIMITATIONS_FIXES_V4 5.1 / 13.5, interior_v2: "Interior.KINDS (6 rooms) lacks stair_shaft / landing / sanctum")
	-- the room at the foot of a house's stair: kept for passing through - a bench to sit by the flight, a light, a
	-- chest for boots and cloaks; the open floor rule (OPEN) and the spine hold it clear like any room
	stair_shaft = {
		{ name = "Bench", role = "wood", w = 5, h = 1.8, d = 1.4, away = true },
		{ name = "Candelabra", role = "metal", w = 1.5, h = 5.5, d = 1.5, flame = true },
		{ name = "Chest", role = "wood", w = 3.5, h = 2.5, d = 2.2 },
	},
	-- an upper floor's landing where the flight arrives: a chest under a light, a bench, a narrow side table
	landing = {
		{ name = "Chest", role = "wood", w = 3.5, h = 2.5, d = 2.2, away = true },
		{ name = "Candelabra", role = "metal", w = 1.5, h = 5.5, d = 1.5, flame = true },
		{ name = "Bench", role = "wood", w = 5, h = 1.8, d = 1.4 },
		{ name = "SideTable", role = "wood", w = 4, h = 3, d = 1.6 },
	},
	-- a house's chapel (the dark gothic city's own room): the altar faces you as you come in, lit; two pews; a
	-- lectern; candelabras either side
	sanctum = {
		{ name = "Altar", role = "stone", w = 6, h = 4, d = 3, away = true, flame = true },
		{ name = "Candelabra", role = "metal", w = 1.5, h = 5.5, d = 1.5, flame = true },
		{ name = "Candelabra", role = "metal", w = 1.5, h = 5.5, d = 1.5, flame = true },
		{ name = "Pew", role = "wood", w = 7, h = 3, d = 2 },
		{ name = "Pew", role = "wood", w = 7, h = 3, d = 2 },
		{ name = "Lectern", role = "wood", w = 2, h = 4, d = 2 },
	},
}
Interior.KINDS = { "hall", "chamber", "store", "kitchen", "study", "workshop", "stair_shaft", "landing", "sanctum" }

-- THE ROOM PROGRAM of a floor cut into rooms (kit/lib/worldrooms.luau's binary split, LIMITATIONS_FIXES_V4 5.1
-- interior_v2: "BSP room graphs + furnishing", after ProcTHOR's room specs: the biggest room gets the floor's main
-- use, the next the next): the ground floor a hall, a kitchen, a store, a workshop; the upper floors chambers and a
-- study; the top floor of three or more a sanctum. Where the stair rises (stairs and three rooms or more), the
-- smallest room open to the stair hall is its stair_shaft (the ground floor) or landing (above). rooms: { area,
-- openToHall } in the plan's order -> one kind per room.
Interior.PROGRAM = {
	ground = { "hall", "kitchen", "store", "workshop" },
	upper = { "chamber", "study", "chamber", "store" },
	top = { "sanctum", "chamber", "study", "store" },
}
function Interior.program(
	rooms: { { area: number, openToHall: boolean? } },
	floor: number,
	floors: number,
	stairs: boolean?
): { string }
	local list = if floor == 0
		then Interior.PROGRAM.ground
		elseif floor == floors - 1 and floors >= 3 then Interior.PROGRAM.top
		else Interior.PROGRAM.upper
	local order = {}
	for k = 1, #rooms do
		table.insert(order, k)
	end
	table.sort(order, function(a, b)
		if math.abs(rooms[a].area - rooms[b].area) > 1e-6 then
			return rooms[a].area > rooms[b].area
		end
		return a < b
	end)
	local kinds: { string } = {}
	local stairRoom: number? = nil
	if stairs and #rooms >= 3 then
		for i = #order, 1, -1 do
			if rooms[order[i]].openToHall then
				stairRoom = order[i]
				break
			end
		end
	end
	local next = 1
	for _, k in order do
		if k == stairRoom then
			kinds[k] = if floor == 0 then "stair_shaft" else "landing"
		else
			kinds[k] = list[math.min(next, #list)]
			next += 1
		end
	end
	return kinds
end

-- walls of the room: side, the axis it runs along, its fixed coordinate and the inward direction
local function walls(room: Room)
	return {
		{ side = "N", along = "x", fixed = room.z0, inward = 1, from = room.x0, to = room.x1 },
		{ side = "S", along = "x", fixed = room.z1, inward = -1, from = room.x0, to = room.x1 },
		{ side = "W", along = "z", fixed = room.x0, inward = 1, from = room.z0, to = room.z1 },
		{ side = "E", along = "z", fixed = room.x1, inward = -1, from = room.z0, to = room.z1 },
	}
end

-- a piece of (w along, d out) with its back to `wall` at position `at` along it -> footprint + front walkway
local function onWall(wall: any, at: number, w: number, d: number): (Rect, Rect)
	local inner = wall.fixed + wall.inward * d
	local frontEnd = inner + wall.inward * Interior.WALKWAY
	if wall.along == "x" then
		local fp = {
			x0 = at - w / 2,
			x1 = at + w / 2,
			z0 = math.min(wall.fixed, inner),
			z1 = math.max(wall.fixed, inner),
		}
		local fr = { x0 = at - w / 2, x1 = at + w / 2, z0 = math.min(inner, frontEnd), z1 = math.max(inner, frontEnd) }
		return fp, fr
	end
	local fp = { z0 = at - w / 2, z1 = at + w / 2, x0 = math.min(wall.fixed, inner), x1 = math.max(wall.fixed, inner) }
	local fr = { z0 = at - w / 2, z1 = at + w / 2, x0 = math.min(inner, frontEnd), x1 = math.max(inner, frontEnd) }
	return fp, fr
end

local function inside(r: Rect, room: Room): boolean
	return r.x0 >= room.x0 - 1e-6 and r.x1 <= room.x1 + 1e-6 and r.z0 >= room.z0 - 1e-6 and r.z1 <= room.z1 + 1e-6
end

local function underWindow(room: Room, side: string, a: number, b: number, h: number): boolean
	for _, win in room.windows or {} do
		if win.side == side and a < win.to and win.from < b and h > win.sill then
			return true
		end
	end
	return false
end

-- may a footprint + walkway go here, given the room, its clear zones and the pieces already placed?
local function fits(room: Room, placed: { Piece }, fp: Rect, fr: Rect, name: string?): boolean
	if not inside(fp, room) then
		return false
	end
	local walk = {
		x0 = math.max(fr.x0, room.x0),
		x1 = math.min(fr.x1, room.x1),
		z0 = math.max(fr.z0, room.z0),
		z1 = math.min(fr.z1, room.z1),
	}
	for _, c in room.clear or {} do
		if overlaps(fp, c) then
			return false
		end
	end
	for _, p in placed do
		local pf = footprint(p)
		if overlaps(fp, pf) or overlaps(walk, pf) or (p.front and overlaps(fp, p.front :: Rect)) then
			return false
		end
		if name and gapOf(fp, pf) < apart(name, p.name) then
			return false
		end
		if sliver(fp, pf) then
			return false
		end
	end
	return true
end

local function centreGroup(room: Room, placed: { Piece }, out: { Piece })
	-- the hall's long table + its two benches down the middle of the long axis, if the room has the space
	local w, d = room.x1 - room.x0, room.z1 - room.z0
	local alongX = w >= d
	local long = (if alongX then w else d) - 2 * (Interior.WALKWAY + 3)
	local across = (if alongX then d else w)
	if long < 6 or across < 2 * Interior.WALKWAY + 4 + 2 * 1.4 + 2 * 3 then
		return
	end
	local len = math.min(long, 18)
	local mx, mz = (room.x0 + room.x1) / 2, (room.z0 + room.z1) / 2
	local group = {
		{ name = "Table", role = "wood", h = 3, off = 0, depth = 4 },
		{ name = "Bench", role = "wood", h = 1.8, off = 2 + 0.6 + 0.7, depth = 1.4 },
		{ name = "Bench", role = "wood", h = 1.8, off = -(2 + 0.6 + 0.7), depth = 1.4 },
	}
	-- from the middle outwards (a door or a stair lane pushes the table aside instead of cancelling it)
	local shifts = { { 0, 0 } }
	for k = 1, 8 do
		for _, sgn in { 1, -1 } do
			table.insert(shifts, { sgn * k, 0 })
			table.insert(shifts, { 0, sgn * k })
		end
	end
	for _, sh in shifts do
		local cx, cz = mx + sh[1], mz + sh[2]
		local all = {
			x0 = cx - (if alongX then len / 2 else 3.7) - Interior.WALKWAY,
			x1 = cx + (if alongX then len / 2 else 3.7) + Interior.WALKWAY,
			z0 = cz - (if alongX then 3.7 else len / 2) - Interior.WALKWAY,
			z1 = cz + (if alongX then 3.7 else len / 2) + Interior.WALKWAY,
		}
		local ok = inside(all, room)
		for _, c in room.clear or {} do
			ok = ok and not overlaps(all, c)
		end
		for _, p in placed do
			ok = ok and not overlaps(all, footprint(p))
		end
		if ok then
			for _, g in group do
				local size = if alongX then { len, g.h, g.depth } else { g.depth, g.h, len }
				local pos = if alongX
					then { cx, room.y + g.h / 2, cz + g.off }
					else { cx + g.off, room.y + g.h / 2, cz }
				table.insert(out, { name = g.name, role = g.role, size = size, pos = pos, front = all })
			end
			return
		end
	end
end

-- the furniture of one room (deterministic for a room + kind + seed)
function Interior.layout(room: Room, kind: string, seed: number?): { Piece }
	local wants = WANTS[kind]
	if not wants then
		return {}
	end
	local out: { Piece } = {}
	if kind == "hall" then
		centreGroup(room, out, out)
	end
	local ws = walls(room)
	local start = (seed or 0) % 4
	local opposite = { N = "S", S = "N", E = "W", W = "E" }
	for i, want in wants do
		local done = false
		-- the walls to try, in order: the one opposite the door first for an "away" piece, else round the room
		local order = {}
		for k = 0, 3 do
			table.insert(order, ws[((start + i + k) % 4) + 1])
		end
		if want.away and room.door then
			table.sort(order, function(a, b)
				local ra = if a.side == opposite[room.door :: string] then 0 elseif a.side == room.door then 2 else 1
				local rb = if b.side == opposite[room.door :: string] then 0 elseif b.side == room.door then 2 else 1
				return ra < rb
			end)
		end
		for _, wall in order do
			local span = wall.to - wall.from
			local steps = math.floor(span)
			local mid = (wall.from + wall.to) / 2
			-- where along the wall to try: from the middle outwards a stud at a time (a hearth centred on its wall,
			-- beds in from corners), and every place that stands it FLUSH against a piece already there, or a whole
			-- GAP from it, or tight in a corner - a stud's steps alone left it a sliver from its neighbour
			local cands: { { number } } = {}
			for s = 0, steps do
				local off = if s % 2 == 0 then s / 2 else -(s + 1) / 2
				table.insert(cands, { mid + off, #cands })
			end
			local function also(at: number)
				table.insert(cands, { at, #cands })
			end
			also(wall.from + want.w / 2)
			also(wall.to - want.w / 2)
			for _, p in out do
				local pf = footprint(p)
				local a0, a1 = if wall.along == "x" then pf.x0 else pf.z0, if wall.along == "x" then pf.x1 else pf.z1
				also(a0 - want.w / 2)
				also(a1 + want.w / 2)
				also(a0 - Interior.GAP - want.w / 2)
				also(a1 + Interior.GAP + want.w / 2)
			end
			table.sort(cands, function(a, b)
				local da, db = math.abs(a[1] - mid), math.abs(b[1] - mid)
				if math.abs(da - db) > 1e-9 then
					return da < db
				end
				return a[2] < b[2]
			end)
			for _, cand in cands do
				local at = cand[1]
				local fp, fr = onWall(wall, at, want.w, want.d)
				if
					not underWindow(room, wall.side, at - want.w / 2, at + want.w / 2, want.h)
					and fits(room, out, fp, fr, want.name)
				then
					table.insert(out, {
						name = want.name,
						role = want.role,
						size = { fp.x1 - fp.x0, want.h, fp.z1 - fp.z0 },
						pos = { (fp.x0 + fp.x1) / 2, room.y + want.h / 2, (fp.z0 + fp.z1) / 2 },
						front = fr,
						light = want.fire or nil,
						flame = want.flame or nil,
						key = want.away or nil,
					})
					done = true
					break
				end
			end
			if done then
				break
			end
		end
	end
	-- A BODY CAN WALK IT: while a piece is shut in, a way in is cut, part of the floor is walled off or too little
	-- of it is open, ONE piece is taken out again - the one whose going leaves the fewest faults (so what stands
	-- IN THE WAY goes, not what it shut in: the first cut took the victims and kept the wardrobe that cut the
	-- room). What the room is for (the hearth, a bed) goes only when nothing else mends it; between equals the
	-- piece placed last goes; a table goes with its benches.
	local function faults(pieces: { Piece }): number
		local w = Interior.walk(room, pieces)
		local sp = Interior.spine(room, pieces)
		return #w.shut
			+ 10 * #w.cut
			+ (if sp.held then 0 else 5)
			+ (if w.lost > Interior.LOST then 5 else 0)
			+ (if w.open < Interior.OPEN then 5 else 0)
	end
	for _ = 1, #out do
		local now = faults(out)
		if now == 0 then
			break
		end
		-- (what the room is for is not looked at while taking anything else out still mends something)
		local best: { Piece }? = nil
		local bestScore = math.huge
		for _, keys in { false, true } do
			for i = #out, 1, -1 do
				local group = out[i].front
				local without: { Piece } = {}
				local key = false
				for j, p in out do
					if j == i or (group ~= nil and p.front == group) then
						key = key or p.key == true
					else
						table.insert(without, p)
					end
				end
				if key == keys then
					local score = faults(without)
					if score < bestScore - 1e-9 then
						best, bestScore = without, score
					end
				end
			end
			if best and bestScore < now - 1e-9 then
				break
			end
		end
		if not best or bestScore >= now - 1e-9 then
			break -- (taking any one piece out mends nothing)
		end
		out = best :: { Piece }
	end
	-- an upper room's rug: flat cloth in the open middle (walked over: never blocks, never a walkway breaker)
	if kind ~= "hall" then
		local w, d = room.x1 - room.x0, room.z1 - room.z0
		local rw, rd = math.min(12, w * 0.4), math.min(8, d * 0.35)
		local cx, cz = (room.x0 + room.x1) / 2, (room.z0 + room.z1) / 2
		local rug = { x0 = cx - rw / 2, x1 = cx + rw / 2, z0 = cz - rd / 2, z1 = cz + rd / 2 }
		local free = rw >= 4 and rd >= 3
		for _, c in room.clear or {} do
			free = free and not overlaps(rug, c)
		end
		for _, p in out do
			free = free and not overlaps(rug, footprint(p))
		end
		if free then
			table.insert(
				out,
				{ name = "Rug", role = "cloth", size = { rw, 0.15, rd }, pos = { cx, room.y + 0.075, cz }, flat = true }
			)
		end
	end
	return out
end

-- WALK THE ROOM: where can a body BODY wide stand, and what does it reach from the room's first way in?
-- A cell is free when a BODY x BODY square on its middle lies inside the room and on no piece (a rug is walked
-- over). The ways in are the room's clear zones (a door's clearance, the stair lane and its landings); a room with
-- none is entered at the middle of its door's wall, or its own middle. The walk starts at the way in that lies on
-- the DOOR's wall when the room names its door (the compiler lists the stair lane first), else at the first.
-- What it does NOT know: the stair lane is walked as floor - the flight's own steps, and the headroom under the
-- flight above, are not in it.
-- -> { shut = { piece indices no body reaches }, cut = { clear-zone indices the first way in does not reach },
--      tight = { clear-zone indices no body fits in at all }, open = share of the floor free of furniture,
--      lost = share of the floor a body could stand on that the way in does not reach (walled off) }
function Interior.walk(room: Room, pieces: { Piece }, body: number?): any
	local cell, half = Interior.CELL, (body or Interior.BODY) / 2
	local nx = math.max(1, math.floor((room.x1 - room.x0) / cell + 1e-6))
	local nz = math.max(1, math.floor((room.z1 - room.z0) / cell + 1e-6))
	local function centre(i: number, j: number): (number, number)
		return room.x0 + (i - 0.5) * cell, room.z0 + (j - 0.5) * cell
	end
	local blocked: { [number]: boolean } = {}
	local covered = 0
	for _, p in pieces do
		if not p.flat then
			local fp = footprint(p)
			covered += math.max(0, math.min(fp.x1, room.x1) - math.max(fp.x0, room.x0)) * math.max(
				0,
				math.min(fp.z1, room.z1) - math.max(fp.z0, room.z0)
			)
			-- (a body's middle may not come within half a body of the piece)
			local i0 = math.max(1, math.floor((fp.x0 - half - room.x0) / cell) + 1)
			local i1 = math.min(nx, math.ceil((fp.x1 + half - room.x0) / cell))
			local j0 = math.max(1, math.floor((fp.z0 - half - room.z0) / cell) + 1)
			local j1 = math.min(nz, math.ceil((fp.z1 + half - room.z0) / cell))
			for i = i0, i1 do
				for j = j0, j1 do
					local x, z = centre(i, j)
					if
						x > fp.x0 - half + 1e-6
						and x < fp.x1 + half - 1e-6
						and z > fp.z0 - half + 1e-6
						and z < fp.z1 + half - 1e-6
					then
						blocked[(j - 1) * nx + i] = true
					end
				end
			end
		end
	end
	local function free(i: number, j: number): boolean
		if i < 1 or i > nx or j < 1 or j > nz or blocked[(j - 1) * nx + i] then
			return false
		end
		local x, z = centre(i, j)
		return x - half >= room.x0 - 1e-6
			and x + half <= room.x1 + 1e-6
			and z - half >= room.z0 - 1e-6
			and z + half <= room.z1 + 1e-6
	end
	local function cellsIn(r: Rect): { number }
		local out = {}
		local i0 = math.max(1, math.floor((r.x0 - room.x0) / cell) + 1)
		local i1 = math.min(nx, math.ceil((r.x1 - room.x0) / cell))
		local j0 = math.max(1, math.floor((r.z0 - room.z0) / cell) + 1)
		local j1 = math.min(nz, math.ceil((r.z1 - room.z0) / cell))
		for i = i0, i1 do
			for j = j0, j1 do
				local x, z = centre(i, j)
				if x >= r.x0 - 1e-6 and x <= r.x1 + 1e-6 and z >= r.z0 - 1e-6 and z <= r.z1 + 1e-6 and free(i, j) then
					table.insert(out, (j - 1) * nx + i)
				end
			end
		end
		return out
	end
	local ways: { { number } } = {}
	local tight: { number } = {}
	for k, c in room.clear or {} do
		ways[k] = cellsIn(c)
		if #ways[k] == 0 then
			table.insert(tight, k)
		end
	end
	-- where the walk starts: the way in on the door's wall; else the first a body fits in; else the free cell
	-- nearest the door's wall / the middle
	local start: { number } = {}
	local first = 0
	for k, c in room.clear or {} do
		local onDoorWall = (room.door == "N" and c.z0 <= room.z0 + 1e-6)
			or (room.door == "S" and c.z1 >= room.z1 - 1e-6)
			or (room.door == "W" and c.x0 <= room.x0 + 1e-6)
			or (room.door == "E" and c.x1 >= room.x1 - 1e-6)
		-- (a door's clearance is a short reach in from its wall: the stair lane, which runs most of a wall's length,
		-- may touch the door's wall too and is not the door)
		local short = math.min(c.x1 - c.x0, c.z1 - c.z0) <= 10 and math.max(c.x1 - c.x0, c.z1 - c.z0) <= 12
		if onDoorWall and short and #ways[k] > 0 and first == 0 then
			first = k
		end
	end
	for k = 1, #ways do
		if first == 0 and #ways[k] > 0 then
			first = k
		end
	end
	if first > 0 then
		start = ways[first]
	end
	if #start == 0 then
		local sx, sz = (room.x0 + room.x1) / 2, (room.z0 + room.z1) / 2
		if room.door == "N" then
			sz = room.z0
		elseif room.door == "S" then
			sz = room.z1
		elseif room.door == "W" then
			sx = room.x0
		elseif room.door == "E" then
			sx = room.x1
		end
		local best, bestD = nil, math.huge
		for i = 1, nx do
			for j = 1, nz do
				if free(i, j) then
					local x, z = centre(i, j)
					local d = (x - sx) ^ 2 + (z - sz) ^ 2
					if d < bestD then
						best, bestD = (j - 1) * nx + i, d
					end
				end
			end
		end
		if best then
			start = { best }
		end
	end
	local seen: { [number]: boolean } = {}
	local queue = table.clone(start)
	for _, k in queue do
		seen[k] = true
	end
	local head = 1
	while head <= #queue do
		local k = queue[head]
		head += 1
		local i, j = (k - 1) % nx + 1, (k - 1) // nx + 1
		for _, d in { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } } do
			local a, b = i + d[1], j + d[2]
			local key = (b - 1) * nx + a
			if not seen[key] and free(a, b) then
				seen[key] = true
				table.insert(queue, key)
			end
		end
	end
	local function reached(cells: { number }): boolean
		for _, k in cells do
			if seen[k] then
				return true
			end
		end
		return false
	end
	local shut: { number } = {}
	for i, p in pieces do
		if not p.flat and p.front then
			local f = p.front :: Rect
			local open = {
				x0 = math.max(f.x0, room.x0),
				x1 = math.min(f.x1, room.x1),
				z0 = math.max(f.z0, room.z0),
				z1 = math.min(f.z1, room.z1),
			}
			-- reached AT the piece: a body standing in its walkway hard by its face (within a cell of touching it),
			-- not somewhere in the far half of a 4-stud walkway with something between
			local fp = footprint(p)
			local near = false
			for _, k in cellsIn(open) do
				if seen[k] then
					local x, z = centre((k - 1) % nx + 1, (k - 1) // nx + 1)
					local dx = math.max(fp.x0 - x, 0, x - fp.x1)
					local dz = math.max(fp.z0 - z, 0, z - fp.z1)
					if math.max(dx, dz) <= half + cell + 1e-6 then
						near = true
						break
					end
				end
			end
			if not near then
				table.insert(shut, i)
			end
		end
	end
	local cut: { number } = {}
	for k = 1, #ways do
		if #ways[k] > 0 and not reached(ways[k]) then
			table.insert(cut, k)
		end
	end
	-- how much of the floor a body could stand on is walled off from the way in
	local standable = 0
	for i = 1, nx do
		for j = 1, nz do
			standable += if free(i, j) then 1 else 0
		end
	end
	local area = math.max((room.x1 - room.x0) * (room.z1 - room.z0), 1e-6)
	-- how far into the room the walk gets from its door's wall (share of the room's depth across it; 1 when the room
	-- names no door)
	local deep = if room.door then 0 else 1
	if room.door then
		local span = if room.door == "N" or room.door == "S" then room.z1 - room.z0 else room.x1 - room.x0
		for k in seen do
			local x, z = centre((k - 1) % nx + 1, (k - 1) // nx + 1)
			local d = if room.door == "N"
				then z - room.z0
				elseif room.door == "S" then room.z1 - z
				elseif room.door == "W" then x - room.x0
				else room.x1 - x
			deep = math.max(deep, d / math.max(span, 1e-6))
		end
	end
	return {
		deep = deep,
		shut = shut,
		cut = cut,
		tight = tight,
		open = 1 - covered / area,
		lost = if standable > 0 then 1 - #queue / standable else 0,
		from = first,
	}
end

-- THE SPINE: a body SPINE studs wide from the room's way in to every other way in and on past the room's middle
-- line (away from its door). -> { held = boolean, cut = { way indices it does not reach }, deep = share of the depth
-- it reaches, owed = false when the room cannot hold it even empty but for what it is for (then it is not held to
-- it) }
function Interior.spine(room: Room, pieces: { Piece }): any
	local w = Interior.walk(room, pieces, Interior.SPINE)
	-- (what it is owed is measured with what the room is FOR standing - its hearth, its beds: a chamber 12 wide holds
	-- a bed or a spine, and the bed is what the room is for, so it keeps the bed and is not held to the spine)
	local keys = {}
	for _, p in pieces do
		if p.key then
			table.insert(keys, p)
		end
	end
	local empty = Interior.walk(room, keys, Interior.SPINE)
	local owed = #empty.cut == 0
		and #empty.tight == 0
		and empty.deep >= 0.5
		and (room.clear == nil or #room.clear == 0 or empty.from > 0)
	-- (a way in a body this wide cannot stand in even empty - a narrow door's swing - is not owed either)
	local cut = {}
	for _, k in w.cut do
		table.insert(cut, k)
	end
	for _, k in w.tight do
		if not table.find(empty.tight, k) then
			table.insert(cut, k)
		end
	end
	return { held = not owed or (#cut == 0 and w.deep >= 0.5), cut = cut, deep = w.deep, owed = owed }
end

-- every rule, re-proved on a finished layout -> problems (empty = fine)
function Interior.check(room: Room, pieces: { Piece }): { string }
	local problems = {}
	for i, p in pieces do
		local fp = footprint(p)
		if p.flat then
			continue -- (a rug is walked over)
		end
		if not inside(fp, room) then
			table.insert(problems, `{p.name} {i} pokes through a wall`)
		end
		for _, c in room.clear or {} do
			if overlaps(fp, c) then
				table.insert(problems, `{p.name} {i} stands in a stair lane / door clearance`)
			end
		end
		for j, q in pieces do
			if q.flat then
				continue
			end
			if j > i then
				if overlaps(fp, footprint(q)) and not (p.front == q.front and p.front ~= nil) then
					table.insert(problems, `{p.name} {i} overlaps {q.name} {j}`)
				end
			end
			if j ~= i and q.front and p.front ~= q.front and overlaps(fp, q.front :: Rect) then
				table.insert(problems, `{p.name} {i} stands in {q.name} {j}'s {Interior.WALKWAY}-stud walkway`)
			end
		end
	end
	-- pieces that keep apart (a dining table from a hearth and from a bed)
	for i, p in pieces do
		for j, q in pieces do
			if j > i and not p.flat and not q.flat then
				local want = apart(p.name, q.name)
				local g = gapOf(footprint(p), footprint(q))
				if g < want - 1e-6 then
					table.insert(
						problems,
						`{p.name} {i} stands {math.floor(g * 10 + 0.5) / 10} studs from {q.name} {j}: they keep {want} apart`
					)
				end
			end
		end
	end
	-- no sliver between two pieces (a table and its benches are one group)
	for i, p in pieces do
		for j, q in pieces do
			if j > i and not p.flat and not q.flat and not (p.front ~= nil and p.front == q.front) then
				local bad, g = sliver(footprint(p), footprint(q))
				if bad then
					table.insert(
						problems,
						`{p.name} {i} stands {math.floor(g * 10 + 0.5) / 10} studs from {q.name} {j}: flush or at least {Interior.GAP} apart, never a sliver between`
					)
				end
			end
		end
	end
	-- the spine
	local sp = Interior.spine(room, pieces)
	if not sp.held then
		table.insert(
			problems,
			if #sp.cut > 0
				then `no {Interior.SPINE}-stud spine: a way that wide does not get from the room's way in to way {sp.cut[1]} (a door or the stairs)`
				else `no {Interior.SPINE}-stud spine: a way that wide gets only {math.floor(sp.deep * 100 + 0.5)}% of the way into the room from its door (at least half)`
		)
	end
	-- ... and a body can walk it
	local w = Interior.walk(room, pieces)
	for _, i in w.shut do
		table.insert(
			problems,
			`{pieces[i].name} {i} cannot be reached: no body {Interior.BODY} studs wide gets from the room's way in to its open side`
		)
	end
	for _, k in w.cut do
		table.insert(
			problems,
			`the room is cut in two: a body {Interior.BODY} studs wide cannot get from its way in (way {w.from}) to way {k} (a door or the stairs)`
		)
	end
	for _, k in w.tight do
		table.insert(
			problems,
			`way {k} into the room (a door or the stairs) is blocked: no body {Interior.BODY} studs wide can stand anywhere in its clear zone`
		)
	end
	if w.lost > Interior.LOST then
		table.insert(
			problems,
			`{math.floor(w.lost * 100 + 0.5)}% of the floor a body could stand on is walled off from the room's way in by furniture (at most {math.floor(
				Interior.LOST * 100 + 0.5
			)}%)`
		)
	end
	if w.open < Interior.OPEN then
		table.insert(
			problems,
			`only {math.floor(w.open * 100 + 0.5)}% of the floor is open: furniture leaves at least {math.floor(
				Interior.OPEN * 100 + 0.5
			)}%`
		)
	end
	return problems
end

return Interior

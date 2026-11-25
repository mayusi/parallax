-- worldrooms.luau — the ROOMS of a floor, by rule (the owner's method list, 2026-11-13: "Procedural floor plan
-- generation", "Room-and-corridor generation"). Before this a house had one empty room a floor.
--
-- A floor is a rectangle (the space inside the outer walls). It is cut the way a small house is: across its longer
-- side, never into a room narrower than `least`, at most `depth` times over (2 = up to four rooms), every cut a
-- partition wall with ONE doorway. Each cut divides one room in two and puts a door between the two, so the rooms
-- and doors always make one tree: every room is reached from every other.
-- A STAIR HALL (`hall` studs along the floor's low-x side, where a building's flight runs) is never cut: the
-- partitions stop at its edge, and a room that touches the hall stands open to it along that side.
-- Pure and seeded: the same floor and seed give the same rooms.
local Rooms = {}

Rooms.DEFAULTS = {
	least = 9, -- studs: no room narrower (an R6 body is 2 wide and the sheet wants a 4.5-stud door with wall beside it)
	depth = 2, -- cuts deep: 1 = two rooms, 2 = up to four
	door = 5, -- studs: a doorway's width
	doorHeight = 8.5,
	thickness = 0.6, -- a partition wall
}

local function lcg(seed: number): () -> number
	local state = (seed or 1) % 2147483647
	if state <= 0 then
		state += 2147483646
	end
	-- (the first draws of this generator barely move from seed to seed: two are thrown away)
	state = (state * 48271) % 2147483647
	state = (state * 48271) % 2147483647
	return function()
		state = (state * 48271) % 2147483647
		return state / 2147483647
	end
end

export type Room = { x0: number, x1: number, z0: number, z1: number, openToHall: boolean? }
-- a partition: it runs along `axis` ("x" or "z") at `at` on the other axis, from `from` to `to`, with one doorway
-- whose middle is `door` along it
export type Wall = { axis: string, at: number, from: number, to: number, door: number, doorWidth: number }

-- the rooms and partitions of a floor w (along x) by d (along z), its low corner at (0, 0)
function Rooms.plan(w: number, d: number, opts: any?): { rooms: { Room }, walls: { Wall }, hall: number }
	local o = opts or {}
	local D = Rooms.DEFAULTS
	local least = if type(o.least) == "number" and o.least >= 6 then o.least else D.least
	local depth = if type(o.depth) == "number" then math.clamp(math.floor(o.depth), 0, 2) else D.depth
	-- the openings of the floor's outer walls no partition may end in: { side = "x0" | "x1" | "z0" | "z1", at, width }
	local keep: { any } = if type(o.keep) == "table" then o.keep else {}
	local door = if type(o.door) == "number" and o.door >= 4.5 then o.door else D.door
	local hall = if type(o.hall) == "number" and o.hall > 0 then math.min(o.hall, w) else 0
	local rnd = lcg(if type(o.seed) == "number" then o.seed else 1)
	local rooms: { Room } = {}
	local walls: { Wall } = {}
	local function cut(r: Room, left: number)
		local rw, rd = r.x1 - r.x0, r.z1 - r.z0
		local alongX = rw >= rd -- (cut across the longer side)
		local len = if alongX then rw else rd
		local across = if alongX then rd else rw
		-- a cut needs two rooms of `least` and a partition long enough for its door with a stud of wall each side
		if left <= 0 or len < 2 * least or across < door + 2 then
			table.insert(rooms, r)
			return
		end
		local lo, hi = least, len - least
		-- (a partition must not end IN a doorway of the wall it meets: up to 8 places are tried, then the room is
		-- left whole)
		local at = nil
		for _ = 1, 8 do
			local try = math.floor(lo + (hi - lo) * rnd() + 0.5)
			local abs = (if alongX then r.x0 else r.z0) + try
			local e0, e1 = if alongX then r.z0 else r.x0, if alongX then r.z1 else r.x1
			local clear = true
			-- ... nor in an opening of the floor's OUTER wall: the front door, a window (`keep`: the openings by
			-- the side they are on). 1,842 of 6,724 houses had a partition standing in their front door before.
			for _, hole in keep do
				local onEnd = (
					alongX and ((hole.side == "z0" and e0 < 1e-6) or (hole.side == "z1" and math.abs(e1 - d) < 1e-6))
				)
					or (
						not alongX
						and ((hole.side == "x0" and e0 < 1e-6) or (hole.side == "x1" and math.abs(e1 - w) < 1e-6))
					)
				if onEnd and math.abs(hole.at - abs) < hole.width / 2 + 1 then
					clear = false
				end
			end
			for _, other in walls do
				local crosses = other.axis == (if alongX then "x" else "z")
				if crosses and (math.abs(other.at - e0) < 1e-6 or math.abs(other.at - e1) < 1e-6) then
					if math.abs(other.door - abs) < other.doorWidth / 2 + 1 then
						clear = false
					end
				end
			end
			if clear then
				at = try
				break
			end
		end
		if at == nil then
			table.insert(rooms, r)
			return
		end
		local a0 = if alongX then r.z0 else r.x0
		local doorAt = a0 + door / 2 + 1 + (across - door - 2) * rnd()
		if alongX then
			table.insert(walls, { axis = "z", at = r.x0 + at, from = r.z0, to = r.z1, door = doorAt, doorWidth = door })
			cut({ x0 = r.x0, x1 = r.x0 + at, z0 = r.z0, z1 = r.z1, openToHall = r.openToHall }, left - 1)
			cut({ x0 = r.x0 + at, x1 = r.x1, z0 = r.z0, z1 = r.z1 }, left - 1)
		else
			table.insert(walls, { axis = "x", at = r.z0 + at, from = r.x0, to = r.x1, door = doorAt, doorWidth = door })
			cut({ x0 = r.x0, x1 = r.x1, z0 = r.z0, z1 = r.z0 + at, openToHall = r.openToHall }, left - 1)
			cut({ x0 = r.x0, x1 = r.x1, z0 = r.z0 + at, z1 = r.z1, openToHall = r.openToHall }, left - 1)
		end
	end
	if w - hall >= 1 and d >= 1 then
		cut({ x0 = hall, x1 = w, z0 = 0, z1 = d, openToHall = hall > 0 }, depth)
	end
	return { rooms = rooms, walls = walls, hall = hall }
end

-- can every room be reached from the first, through the doors and the hall? (what the plan promises; a spec walks it)
function Rooms.connected(plan: any): boolean
	local rooms: { Room } = plan.rooms
	if #rooms <= 1 then
		return true
	end
	local function touches(r: Room, wall: Wall): boolean
		-- the door's middle lies on a side of the room
		if wall.axis == "z" then
			return (math.abs(r.x0 - wall.at) < 1e-6 or math.abs(r.x1 - wall.at) < 1e-6)
				and wall.door > r.z0
				and wall.door < r.z1
		end
		return (math.abs(r.z0 - wall.at) < 1e-6 or math.abs(r.z1 - wall.at) < 1e-6)
			and wall.door > r.x0
			and wall.door < r.x1
	end
	local seen = { [1] = true }
	local grew = true
	while grew do
		grew = false
		for i, a in rooms do
			if seen[i] then
				for j, b in rooms do
					if not seen[j] then
						local joined = plan.hall > 0 and a.openToHall and b.openToHall
						for _, wall in plan.walls do
							joined = joined or (touches(a, wall) and touches(b, wall))
						end
						if joined then
							seen[j] = true
							grew = true
						end
					end
				end
			end
		end
	end
	for i in rooms do
		if not seen[i] then
			return false
		end
	end
	return true
end

return Rooms

--!strict
-- AnimMatch (ReplicatedStorage.kit.AnimMatch) — the pure maths of three matching methods, on tables baked from built
-- clips by kit/anim/match_tables.py (the build side holds the same maths; the kit's tests compare the two):
--   AnimMatch.poseFrame(table, pose)                 POSE MATCHING: the frame to ENTER a clip at, nearest the pose the
--                                                    character is in (pose: { [joint] = { x, y, z, w } })
--   AnimMatch.distanceFrame(table, distance)         DISTANCE MATCHING: the frame (it may fall between two) at which
--                                                    `distance` studs are still to travel to the stop / the landing
--   AnimMatch.motionNext(db, pose, vel, current)     MOTION MATCHING: the { clip, frame } to play NEXT out of several
--                                                    clips, from the pose the body is in now and how it has just
--                                                    turned; it stays on its clip unless another fits better by db.stay
--   AnimMatch.motionStep(db, prev, pose, dt, current) one step of the game's own loop: the body's pose a moment apart
--                                                    -> the clip and frame to play next, and whether that is a jump
--   AnimMatch.velocity(a, b, fps)                    how a joint is turning between two of its turns (the db's unit)
--   AnimMatch.wanted(mx, mz, lx, lz, speed, turnIn)  STEERING: where the player wants to go, in the body's own frame -
--                                                    hand it to motionNext / motionStep as `want` and the search counts
--                                                    each row's own travel and turn against it (the owner's limitations
--                                                    list 2026-11-15, A-R02); `only` = the clips the game allows now
-- No services, no instances. NOT YET CALLED BY A GAME: reading the character's pose off its Motor6Ds and setting an
-- AnimationTrack's TimePosition from the answer is a Studio session's proof.
local AnimMatch = {}

export type PoseTable = { joints: { string }, rows: { { number } }, fps: number }
export type DistanceTable = { remaining: { number }, fps: number }
export type MotionDb = {
	joints: { string },
	rows: { { number } },
	index: { { any } },
	clips: { [string]: { first: number, frames: number, loop: boolean } },
	vel_weight: number,
	stay: number,
	fps: number,
	rest: string?, -- (a motion SET's: the looping clip the body goes back to)
	-- STEERING: where each row's clip is going - { vx, vz, turn } (studs a second in the body's own frame, -Z ahead;
	-- radians a second, + = to the left) - and the scales a miss is counted in (the set's top speed and top turn)
	traj: { { number } }?,
	traj_weight: number?,
	traj_tol: number?, -- how much worse than the best a row's travel may miss the ask and still be chosen by its pose
	speed: number?,
	turn: number?,
}

-- the mean over joints of the ANGLE between a row's turns and a pose's (flat x y z w ..., taken at unit length),
-- as a share of a half turn: 0 = the same pose, 1 = every joint a half turn away
local function poseCost(row: { number }, pose: { number }, joints: number): number
	local sum = 0
	for k = 0, joints - 1 do
		local i = k * 4
		local x, y, z, w = pose[i + 1], pose[i + 2], pose[i + 3], pose[i + 4]
		local len = math.max(math.sqrt(x * x + y * y + z * z + w * w), 1e-12)
		x, y, z, w = x / len, y / len, z / len, w / len
		local ax, ay, az, aw = row[i + 1], row[i + 2], row[i + 3], row[i + 4]
		local d = ax * x + ay * y + az * z + aw * w
		-- the angle from the DIFFERENCE of the two turns (exact near 0, where the dot alone loses a quarter degree)
		local vx = aw * x - w * ax - (ay * z - az * y)
		local vy = aw * y - w * ay - (az * x - ax * z)
		local vz = aw * z - w * az - (ax * y - ay * x)
		sum += 2 * math.atan2(math.sqrt(vx * vx + vy * vy + vz * vz), math.abs(d)) / math.pi
	end
	return sum / joints
end

function AnimMatch.poseFrame(t: PoseTable, pose: { [string]: { number } }): number
	local n = #t.joints
	local best, at = math.huge, 0
	local flat = table.create(n * 4)
	for i, row in t.rows do
		for k, joint in t.joints do
			local q = pose[joint]
			local o = (k - 1) * 4
			if q then
				local len = math.sqrt(q[1] * q[1] + q[2] * q[2] + q[3] * q[3] + q[4] * q[4])
				len = math.max(len, 1e-12)
				flat[o + 1], flat[o + 2], flat[o + 3], flat[o + 4] = q[1] / len, q[2] / len, q[3] / len, q[4] / len
			else -- a joint the pose does not name counts as the row's own
				flat[o + 1], flat[o + 2], flat[o + 3], flat[o + 4] = row[o + 1], row[o + 2], row[o + 3], row[o + 4]
			end
		end
		local c = poseCost(row, flat, n)
		if c < best - 1e-12 then
			best, at = c, i - 1
		end
	end
	return at
end

function AnimMatch.distanceFrame(t: DistanceTable, distance: number): number
	local r = t.remaining
	distance = math.max(distance, r[#r]) -- past the stop is AT the stop: the first frame that is there
	if distance >= r[1] then
		return 0
	end
	for i = 2, #r do
		if distance >= r[i] then
			local span = r[i - 1] - r[i]
			return (i - 2) + (if span > 1e-9 then (r[i - 1] - distance) / span else 1)
		end
	end
	return #r - 1
end

local function motionCost(db: MotionDb, row: { number }, pose: { number }, vel: { number }): number
	local n = #db.joints
	local sum = 0
	for k = 0, n - 1 do
		local i = n * 4 + k * 3
		local dx, dy, dz = row[i + 1] - vel[k * 3 + 1], row[i + 2] - vel[k * 3 + 2], row[i + 3] - vel[k * 3 + 3]
		sum += math.sqrt(dx * dx + dy * dy + dz * dz)
	end
	return poseCost(row, pose, n) + db.vel_weight * sum / n
end

-- what row i's own travel and turn miss the WANTED ones by, in the pose cost's unit (0 when nothing is wanted or the
-- database carries no travel: the search is then the one that only continues motion)
local function trajCost(db: MotionDb, i: number, want: { number }?): number
	local traj = db.traj
	if not want or not traj then
		return 0
	end
	local t = traj[i]
	local dx, dz = t[1] - want[1], t[2] - want[2]
	return math.sqrt(dx * dx + dz * dz) / math.max(db.speed or 1, 1e-6)
		+ math.abs(t[3] - (want[3] or 0)) / math.max(db.turn or 1, 1e-6)
end

-- THE SPATIAL GRID (LIMITATIONS_FIXES_V4 4.4 / 13.4.3): a steered search looked at EVERY row's travel to find the
-- least miss, then every row's pose among those that miss least - O(N) a step. The rows are hashed by their travel
-- (vx and vz in db.speed's unit, the turn in db.turn's: the very unit trajCost counts in) into cubes GRID_CELL wide;
-- a query walks the cubes outward from the ask's, shell by shell, and stops once a shell's nearest point is further
-- than the least miss found (a cube r shells out is at least (r - 1) cells away on one axis, and the miss is at least
-- that), so it reads the rows near the ask only. The answer is the scan's own: every row the scan would keep is in a
-- cube the walk reaches, and the rows kept are taken in the scan's order (its ties fall the same way).
--   AnimMatch.grid(db, cell?)   builds it (motionNext builds it once a database, on its first steered query;
--                               call again after changing db.traj)
--   AnimMatch.visited           how many rows the last steered query read the travel of (the proof it is not all)
local GRID_CELL = 0.25
AnimMatch.GRID_CELL = GRID_CELL
AnimMatch.visited = 0

export type Grid = {
	cell: number,
	cells: { [string]: { number } },
	lo: { number },
	hi: { number },
	of: { [any]: boolean }, -- (the traj table it was built from: a new table is built anew)
}

local function cellKey(x: number, y: number, z: number): string
	return `{x},{y},{z}`
end

local function travelAt(db: MotionDb, t: { number }): (number, number, number)
	local s, r = math.max(db.speed or 1, 1e-6), math.max(db.turn or 1, 1e-6)
	return t[1] / s, t[2] / s, (t[3] or 0) / r
end

function AnimMatch.grid(db: MotionDb, cell: number?): Grid
	local h = if type(cell) == "number" and cell > 0 and cell < math.huge then cell else GRID_CELL
	local g: Grid = {
		cell = h,
		cells = {},
		lo = { math.huge, math.huge, math.huge },
		hi = { -math.huge, -math.huge, -math.huge },
		of = {},
	}
	local traj = db.traj
	if not traj then
		return g
	end
	g.of[traj] = true
	for i, t in traj do
		local x, y, z = travelAt(db, t)
		if
			x == x
			and y == y
			and z == z
			and math.abs(x) < math.huge
			and math.abs(y) < math.huge
			and math.abs(z) < math.huge
		then
			local c = { math.floor(x / h), math.floor(y / h), math.floor(z / h) }
			local key = cellKey(c[1], c[2], c[3])
			local list = g.cells[key]
			if not list then
				list = {}
				g.cells[key] = list
			end
			table.insert(list, i)
			for a = 1, 3 do
				g.lo[a], g.hi[a] = math.min(g.lo[a], c[a]), math.max(g.hi[a], c[a])
			end
		end
	end
	return g
end

-- the least travel miss among the offered rows and, in the scan's order, every offered row within 1e-9 of it - read
-- off the grid, shell by shell from the ask's cube (only the shells inside the grid's own box are walked: an ask far
-- off starts at the box's nearest shell)
local function nearestRows(db: MotionDb, want: { number }, offered: (number) -> boolean): (number, { number })
	local g: Grid = (db :: any).grid
	if not g or not db.traj or not g.of[db.traj] then
		g = AnimMatch.grid(db);
		(db :: any).grid = g
	end
	local h = g.cell
	local wx, wy, wz = travelAt(db, want)
	local c = { math.floor(wx / h), math.floor(wy / h), math.floor(wz / h) }
	local least, seen = math.huge, {}
	local visited = 0
	if g.lo[1] > g.hi[1] then
		AnimMatch.visited = 0
		return least, seen
	end
	-- the first shell that can hold a cube of the grid, and the last one there is
	local r0, r1 = 0, 0
	for a = 1, 3 do
		r0 = math.max(r0, g.lo[a] - c[a], c[a] - g.hi[a])
		r1 = math.max(r1, math.abs(g.lo[a] - c[a]), math.abs(g.hi[a] - c[a]))
	end
	local found: { { number } } = {}
	for r = r0, r1 do
		if r >= 1 and (r - 1) * h > least + 1e-9 then
			break
		end
		for x = math.max(g.lo[1], c[1] - r), math.min(g.hi[1], c[1] + r) do
			for y = math.max(g.lo[2], c[2] - r), math.min(g.hi[2], c[2] + r) do
				local zlo, zhi = math.max(g.lo[3], c[3] - r), math.min(g.hi[3], c[3] + r)
				local zs: { number } = {}
				if math.abs(x - c[1]) == r or math.abs(y - c[2]) == r then
					for z = zlo, zhi do
						table.insert(zs, z)
					end
				else -- (inside the shell's x / y rim only its two z faces are on the shell)
					local faces: { number } = if r == 0 then { c[3] } else { c[3] - r, c[3] + r }
					for _, z in faces do
						if z >= zlo and z <= zhi then
							table.insert(zs, z)
						end
					end
				end
				for _, z in zs do
					local list = g.cells[cellKey(x, y, z)]
					if list then
						for _, i in list do
							if offered(i) then
								visited += 1
								local cost = trajCost(db, i, want)
								least = math.min(least, cost)
								table.insert(found, { i, cost })
							end
						end
					end
				end
			end
		end
	end
	AnimMatch.visited = visited
	for _, e in found do
		if e[2] <= least + 1e-9 then
			table.insert(seen, e[1])
		end
	end
	table.sort(seen)
	return least, seen
end

-- WHERE THE PLAYER WANTS TO GO, in the body's own frame: (mx, mz) the direction asked for in the world (a Humanoid's
-- MoveDirection: length 0..1), (lx, lz) the way the body faces in the world, speed in studs a second. turnIn: the
-- seconds in which the body is to face the way it goes (nil: it keeps its facing - a strafe stays a strafe).
-- -> { vx, vz, turn }: -Z ahead, +X right, radians a second, + = to the left
function AnimMatch.wanted(mx: number, mz: number, lx: number, lz: number, speed: number, turnIn: number?): { number }
	local len = math.sqrt(lx * lx + lz * lz)
	if not (len >= 1e-9 and len < math.huge) or mx ~= mx or mz ~= mz or speed ~= speed then
		return { 0, 0, 0 } -- (no facing, or a number that is not one: nothing can be said)
	end
	lx, lz = lx / len, lz / len
	local right, ahead = mx * -lz + mz * lx, mx * lx + mz * lz
	local turn = 0
	if turnIn and turnIn > 0 and right * right + ahead * ahead > 1e-6 then
		turn = math.atan2(-right, ahead) / turnIn
	end
	return { right * speed, -ahead * speed, turn }
end

-- pose: flat { x, y, z, w, ... }, the pose the body is in NOW; vel: flat { x, y, z, ... }, how each joint turned
-- since the frame before (AnimMatch.velocity(before, now, fps)), both in db.joints order; current: { clip, frame }
-- being played, or nil. Returns { clip, frame } to play NEXT: the frame after the row that fits - the one being
-- played unless another row fits better by db.stay. A clip that does not loop holds its last offered frame.
-- want: { vx, vz, turn } the player asks for (AnimMatch.wanted) - each row's own travel counts beside its pose; only:
-- the clips the game allows now ({ [clip] = true }: a clip not in it is never chosen and gets no `stay`; when it
-- allows none of the set's, the clip being played simply goes on).
function AnimMatch.motionNext(
	db: MotionDb,
	pose: { number },
	vel: { number },
	current: { any }?,
	want: { number }?,
	only: { [string]: boolean }?
): { any }
	if want then
		for k = 1, #want do
			local v = want[k]
			if type(v) ~= "number" or v ~= v or math.abs(v) == math.huge then
				want = nil -- (an ask that is not numbers is no ask)
				break
			end
		end
	end
	local playing = if current and type(current[1]) == "string" then db.clips[current[1]] else nil
	if playing and not playing.loop then
		want = nil -- A MOVE IN FLIGHT IS NOT STEERED: a clip that does not loop (an attack) keeps the search it had
	end
	-- WHERE IT GOES FIRST, THEN HOW IT FITS (seen in Studio 2026-11-15: summed, a far gait's pose cost and its travel
	-- could be too close to call): a NEW clip is entered only among the rows whose travel misses the ask LEAST (a jog
	-- at exactly the asked speed beats a walk 2 studs a second off); among those the pose and its turning choose.
	-- The clip being played is kept while its own travel is within traj_tol of that least miss (a stick that wavers
	-- does not flip the gait). Nothing asked: every offered row is in the running.
	local function offered(i: number): boolean
		local name = db.index[i][1]
		-- STEERING NEVER STARTS A MOVE: under an ask, a clip that does not loop is offered only when the game names it
		return (not only or only[name] == true)
			and not (want ~= nil and not db.clips[name].loop and not (only ~= nil and only[name] == true))
	end
	local bar = math.huge
	local best, at = math.huge, 0
	if want and db.traj then
		-- (the rows that miss the ask least, read off the spatial grid - not every row's travel)
		local least, near = nearestRows(db, want, offered)
		bar = least + (db.traj_tol or 0.08)
		for _, i in near do
			local c = motionCost(db, db.rows[i], pose, vel)
			if c < best - 1e-12 then
				best, at = c, i
			end
		end
	else
		for i, row in db.rows do
			if offered(i) then
				local c = motionCost(db, row, pose, vel)
				if c < best - 1e-12 then
					best, at = c, i
				end
			end
		end
	end
	if at == 0 then
		best, at, only, bar = math.huge, 1, nil, math.huge -- (nothing is allowed: what plays goes on)
	end
	local span = if current then db.clips[current[1]] else nil
	if
		current
		and span
		and (not only or only[current[1]])
		and type(current[2]) == "number"
		and current[2] == current[2]
		and math.abs(current[2]) < 1e9
	then
		-- the frame being played may lie BETWEEN two rows (the game reads a clock): the nearer-fitting of the two
		-- stands for it
		local f = math.floor(current[2])
		local own, ownAt = math.huge, -1
		for g = f, if current[2] > f then f + 1 else f do
			-- (the clip being played keeps its `stay` only while it still goes where asked)
			if g >= 0 and g < span.frames and trajCost(db, span.first + g + 1, want) <= bar + 1e-12 then
				local c = motionCost(db, db.rows[span.first + g + 1], pose, vel)
				if c < own - 1e-12 then
					own, ownAt = c, g
				end
			end
		end
		if ownAt >= 0 and own <= best + db.stay then
			at = span.first + ownAt + 1
		end
	end
	local name, frame = db.index[at][1], db.index[at][2]
	local own = db.clips[name]
	local nxt = frame + 1
	if own.loop then
		nxt %= own.frames
	end
	return { name, math.min(nxt, own.frames - 1) }
end

-- how a joint is turning from turn a to turn b (each { x, y, z, w }), one frame apart at `fps`: the vector part of
-- b * inverse(a), in half-turns a second (the unit of a motion database's rows)
function AnimMatch.velocity(a: { number }, b: { number }, fps: number): { number }
	local bx, by, bz, bw = b[1], b[2], b[3], b[4]
	if a[1] * bx + a[2] * by + a[3] * bz + a[4] * bw < 0 then
		bx, by, bz, bw = -bx, -by, -bz, -bw
	end
	local ax, ay, az, aw = -a[1], -a[2], -a[3], a[4]
	local s = 2 * fps / math.pi
	return {
		(bw * ax + aw * bx + (by * az - bz * ay)) * s,
		(bw * ay + aw * by + (bz * ax - bx * az)) * s,
		(bw * az + aw * bz + (bx * ay - by * ax)) * s,
	}
end

-- ONE STEP OF MOTION MATCHING as a game runs it (src/kit/Anim.motion calls this a few times a second): prev / pose =
-- the body's pose a moment apart ({ [joint] = { x, y, z, w } }, dt seconds; prev nil on the first step), current =
-- { clip, frame } being played (the frame may be a fraction). Returns clip, frame (to play NEXT) and jump: whether
-- that is anything but the next frame of the clip being played (the game then cross-fades to it).
function AnimMatch.motionStep(
	db: MotionDb,
	prev: { [string]: { number } }?,
	pose: { [string]: { number } },
	dt: number,
	current: { any }?,
	want: { number }?, -- (steering: AnimMatch.wanted)
	only: { [string]: boolean }? -- (the clips the game allows now)
): (string, number, boolean)
	if current and type(current[2]) == "number" and current[2] == current[2] then
		local own = db.clips[current[1]]
		if own and not own.loop and current[2] >= own.frames - 1 then
			-- a clip that does not loop is in its last frames (they are not offered: nothing follows them): it
			-- plays out - the game goes to the set's rest when it has ended
			return current[1], own.frames - 1, false
		end
	end
	local flat, vel = table.create(#db.joints * 4), table.create(#db.joints * 3)
	local fps = if dt == dt and dt > 0 then 1 / dt else 0
	for k, joint in db.joints do
		local q = pose[joint] or { 0, 0, 0, 1 }
		local len = math.max(math.sqrt(q[1] * q[1] + q[2] * q[2] + q[3] * q[3] + q[4] * q[4]), 1e-12)
		local now = { q[1] / len, q[2] / len, q[3] / len, q[4] / len }
		local o = (k - 1) * 4
		flat[o + 1], flat[o + 2], flat[o + 3], flat[o + 4] = now[1], now[2], now[3], now[4]
		local p = if prev then prev[joint] else nil
		local v = { 0, 0, 0 }
		if p and fps > 0 then
			local plen = math.max(math.sqrt(p[1] * p[1] + p[2] * p[2] + p[3] * p[3] + p[4] * p[4]), 1e-12)
			v = AnimMatch.velocity({ p[1] / plen, p[2] / plen, p[3] / plen, p[4] / plen }, now, fps)
		end
		local w = (k - 1) * 3
		vel[w + 1], vel[w + 2], vel[w + 3] = v[1], v[2], v[3]
	end
	local nxt = AnimMatch.motionNext(db, flat, vel, current, want, only)
	local name: string, frame: number = nxt[1], nxt[2]
	local jump = true
	if current and current[1] == name and type(current[2]) == "number" and current[2] == current[2] then
		-- not a jump: the answer is where the clip being played is about to be anyway (within a row of its next
		-- frame; a loop's last frame is followed by its first; a clip that does not loop holds its last offered frame)
		local span = db.clips[name]
		local ahead = frame - current[2]
		if span.loop and ahead < -span.frames / 2 then
			ahead += span.frames
		end
		jump = not (
			(ahead >= 0 and ahead <= 2) or (not span.loop and frame == span.frames - 1 and current[2] >= frame - 1)
		)
	end
	return name, frame, jump
end

-- where to ENTER a clip, in seconds, from the tables the build baked into its metadata (Meta.<clip>.match): by the
-- studs still to travel when a distance is given and the clip carries a distance table, else by the pose when it
-- carries a pose table. nil = no entry (the clip is played from its start), with the reason: "no table" (the clip
-- carries none for that) or "no shared joint" (the body has none of the pose table's joints: an R15 body, a prop).
function AnimMatch.enterTime(clipMeta: any, pose: { [string]: { number } }?, distance: number?): (number?, string?)
	local m = if type(clipMeta) == "table" then clipMeta.match else nil
	if type(m) ~= "table" then
		return nil, "no table"
	end
	local function usable(t: any, rows: string): boolean
		return type(t) == "table"
			and type(t.fps) == "number"
			and t.fps > 0
			and type(t[rows]) == "table"
			and #t[rows] > 0
	end
	if distance and distance == distance and usable(m.distance, "remaining") then
		return AnimMatch.distanceFrame(m.distance, distance) / m.distance.fps, nil
	end
	if pose and usable(m.pose, "rows") and type(m.pose.joints) == "table" then
		-- a body that has none of the table's joints cannot be matched: every row would cost nothing and frame 0
		-- would win, silently
		for _, joint in m.pose.joints do
			if pose[joint] then
				return AnimMatch.poseFrame(m.pose, pose) / m.pose.fps, nil
			end
		end
		return nil, "no shared joint"
	end
	return nil, "no table"
end

return AnimMatch

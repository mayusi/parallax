-- animgrid.spec.luau — THE SPATIAL GRID of steered motion matching (LIMITATIONS_FIXES_V4 4.4 / 13.4.3): a steered
-- query reads the rows near the ask off a grid of their travel, not every row - and answers exactly what the full
-- scan answers. The scan is written out here as it was (the reference); made-up databases of up to 9,000 rows,
-- 400 asks each, compared answer for answer, and the rows read counted.
local frk = require("../frk")
local test, check = frk.test, frk.check

local AnimMatch = require("../../../src/kit/AnimMatch")

-- a seeded generator (the same databases every run)
local function rng(seed: number): () -> number
	local s = seed
	return function(): number
		s = (s * 1103515245 + 12345) % 2147483648
		return s / 2147483648
	end
end

-- `clips` clips of `frames` frames each, two joints; each clip goes its own way (a few share a travel exactly - ties)
local function database(clips: number, frames: number, seed: number): any
	local r = rng(seed)
	local db: any = {
		joints = { "Torso", "Head" },
		rows = {},
		index = {},
		clips = {},
		traj = {},
		traj_weight = 0.5,
		traj_tol = 0.08,
		speed = 16,
		turn = 3,
		vel_weight = 0.05,
		stay = 0.05,
		fps = 30,
	}
	local same = { 0, 0, 0 }
	for c = 1, clips do
		local name = `Clip{c}`
		db.clips[name] = { first = #db.rows, frames = frames, loop = c % 7 ~= 0 }
		local vx, vz, turn = (r() - 0.5) * 32, (r() - 0.5) * 32, (r() - 0.5) * 6
		if c % 11 == 0 then
			vx, vz, turn = same[1], same[2], same[3] -- (clips that go the very same way: ties)
		end
		for f = 0, frames - 1 do
			local row = {}
			for _ = 1, 2 do
				local a = r() * math.pi
				local x, y, z = r() - 0.5, r() - 0.5, r() - 0.5
				local l = math.sqrt(x * x + y * y + z * z)
				table.insert(row, x / l * math.sin(a / 2))
				table.insert(row, y / l * math.sin(a / 2))
				table.insert(row, z / l * math.sin(a / 2))
				table.insert(row, math.cos(a / 2))
			end
			for _ = 1, 6 do
				table.insert(row, (r() - 0.5) * 2)
			end
			table.insert(db.rows, row)
			table.insert(db.index, { name, f })
			-- (a row's travel drifts a little through its clip, as a built one's does)
			table.insert(db.traj, { vx + (r() - 0.5) * 0.4, vz + (r() - 0.5) * 0.4, turn + (r() - 0.5) * 0.05 })
		end
	end
	return db
end

-- the FULL SCAN, as motionNext searched before the grid (the reference the grid is held to)
local function scan(
	db: any,
	pose: { number },
	vel: { number },
	current: { any }?,
	want: { number }?,
	only: { [string]: boolean }?
): { any }
	local playing = if current and type(current[1]) == "string" then db.clips[current[1]] else nil
	if playing and not playing.loop then
		want = nil
	end
	local function traj(i: number): number
		if not want then
			return 0
		end
		local t = db.traj[i]
		local dx, dz = t[1] - want[1], t[2] - want[2]
		return math.sqrt(dx * dx + dz * dz) / math.max(db.speed or 1, 1e-6)
			+ math.abs(t[3] - (want[3] or 0)) / math.max(db.turn or 1, 1e-6)
	end
	local function offered(i: number): boolean
		local name = db.index[i][1]
		return (not only or only[name] == true)
			and not (want ~= nil and not db.clips[name].loop and not (only ~= nil and only[name] == true))
	end
	local least = math.huge
	if want then
		for i in db.rows do
			if offered(i) then
				least = math.min(least, traj(i))
			end
		end
	end
	local enter = if want then least + 1e-9 else math.huge
	-- the pose cost (AnimMatch's own, through a one-row pose table: the rows here are joints + turning)
	local best, at = math.huge, 0
	for i in db.rows do
		if offered(i) and traj(i) <= enter then
			-- (the cost: summed the way motionNext's own motionCost does - pose angle share + weighted turning miss)
			local row = db.rows[i]
			local sum, n = 0, #db.joints
			for k = 0, n - 1 do
				local o = k * 4
				local x, y, z, w = pose[o + 1], pose[o + 2], pose[o + 3], pose[o + 4]
				local len = math.max(math.sqrt(x * x + y * y + z * z + w * w), 1e-12)
				x, y, z, w = x / len, y / len, z / len, w / len
				local ax, ay, az, aw = row[o + 1], row[o + 2], row[o + 3], row[o + 4]
				local d = ax * x + ay * y + az * z + aw * w
				local vx = aw * x - w * ax - (ay * z - az * y)
				local vy = aw * y - w * ay - (az * x - ax * z)
				local vz = aw * z - w * az - (ax * y - ay * x)
				sum += 2 * math.atan2(math.sqrt(vx * vx + vy * vy + vz * vz), math.abs(d)) / math.pi
			end
			local vsum = 0
			for k = 0, n - 1 do
				local o = n * 4 + k * 3
				local dx, dy, dz = row[o + 1] - vel[k * 3 + 1], row[o + 2] - vel[k * 3 + 2], row[o + 3] - vel[k * 3 + 3]
				vsum += math.sqrt(dx * dx + dy * dy + dz * dz)
			end
			local c = sum / n + db.vel_weight * vsum / n
			if c < best - 1e-12 then
				best, at = c, i
			end
		end
	end
	if at == 0 then
		at = 1
	end
	local name, frame = db.index[at][1], db.index[at][2]
	local own = db.clips[name]
	local nxt = frame + 1
	if own.loop then
		nxt %= own.frames
	end
	return { name, math.min(nxt, own.frames - 1) }
end

return function()
	test.suite("the spatial grid of steered motion matching (V4 13.4.3)", function()
		test.case("its answer is the full scan's, ask for ask, on databases of 300 to 9,000 rows", function()
			for _, size in { { 10, 30, 1 }, { 60, 50, 2 }, { 150, 60, 3 } } do
				local db = database(size[1], size[2], size[3])
				local r = rng(100 + size[3])
				local wrong, steered = 0, 0
				for q = 1, 400 do
					local pose = {}
					for _ = 1, 2 do
						local a = r() * math.pi
						table.insert(pose, 0)
						table.insert(pose, math.sin(a / 2))
						table.insert(pose, 0)
						table.insert(pose, math.cos(a / 2))
					end
					local vel = { r() - 0.5, r() - 0.5, r() - 0.5, r() - 0.5, r() - 0.5, r() - 0.5 }
					-- asks: near a clip, between clips, far outside every clip, exactly on a shared travel
					local want: { number }? = { (r() - 0.5) * 40, (r() - 0.5) * 40, (r() - 0.5) * 8 }
					if q % 9 == 0 then
						want = { 400, -900, 50 }
					elseif q % 13 == 0 then
						want = { 0, 0, 0 }
					elseif q % 17 == 0 then
						want = nil
					end
					local only: { [string]: boolean }? = nil
					if q % 5 == 0 then
						only = {}
						for c = 1, size[1], 3 do
							(only :: any)[`Clip{c}`] = true
						end
					end
					-- (the grid's answer against the scan's; the clip being played is weighed after the search, the same
					-- code either way)
					local got = AnimMatch.motionNext(db, pose, vel, nil, want, only)
					local ref = scan(db, pose, vel, nil, want, only)
					if got[1] ~= ref[1] or got[2] ~= ref[2] then
						wrong += 1
					end
					if want then
						steered += 1
					end
				end
				check.equal(wrong, 0)
				check.is_true(steered > 300)
			end
		end)

		test.case("a steered query reads the rows near the ask, not every row", function()
			local db = database(150, 60, 3) -- 9,000 rows
			local pose = { 0, 0, 0, 1, 0, 0, 0, 1 }
			local vel = { 0, 0, 0, 0, 0, 0 }
			local t = db.traj[61] -- (the ask: Clip2's own travel)
			AnimMatch.motionNext(db, pose, vel, nil, { t[1], t[2], t[3] })
			check.is_true(AnimMatch.visited > 0)
			check.is_true(AnimMatch.visited < 9000 / 20) -- (a twentieth of the rows at most; the full scan read 9,000)
		end)

		test.case(
			"a database whose travel changes is gridded anew; one with no travel is searched as before",
			function()
				local db = database(20, 10, 4)
				local t = db.traj[15]
				local a = AnimMatch.motionNext(
					db,
					{ 0, 0, 0, 1, 0, 0, 0, 1 },
					{ 0, 0, 0, 0, 0, 0 },
					nil,
					{ t[1], t[2], t[3] }
				)
				check.equal(a[1], db.index[15][1])
				local moved = {}
				for i, tr in db.traj do
					moved[i] = if i == 155 then { t[1], t[2], t[3] } else { tr[1] + 100, tr[2], tr[3] }
				end
				db.traj = moved -- (only Clip16's row 155 goes the asked way now)
				local b = AnimMatch.motionNext(
					db,
					{ 0, 0, 0, 1, 0, 0, 0, 1 },
					{ 0, 0, 0, 0, 0, 0 },
					nil,
					{ t[1], t[2], t[3] }
				)
				check.equal(b[1], db.index[155][1])
				db.traj = nil
				local c = AnimMatch.motionNext(
					db,
					{ 0, 0, 0, 1, 0, 0, 0, 1 },
					{ 0, 0, 0, 0, 0, 0 },
					nil,
					{ t[1], t[2], t[3] }
				)
				check.is_true(type(c[1]) == "string")
			end
		)
	end)
end

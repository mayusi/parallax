-- animwarp.spec.luau — THE RULES OF A ROOT TRAVEL THAT MEETS THE WORLD (the owner's limitations list, 2026-11-15,
-- A-R04): swept clearance before the move and frame by frame, when a moving or lost target may still change the
-- warp, what the body does when something else moved it, and the whole root update as the game runs it
-- (src/kit/AnimWarp begin / step, called by src/kit/Anim applyRoot). Made-up roots and walls only: what a body does
-- in a game is Studio's to show.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local AnimLayers = require("../../../src/kit/AnimLayers")
local AnimWarp = require("../../../src/kit/AnimWarp")

-- a root that walks 6 studs straight ahead (-Z) in one second, 60 frames a second
local function straight(): { { number } }
	local root = {}
	for i = 0, 60 do
		table.insert(root, { 0, -6 * i / 60, 0 })
	end
	return root
end

local function near(a: number, b: number, eps: number?): boolean
	return math.abs(a - b) <= (eps or 1e-6)
end

-- a wall across the way at z = at (met going toward -Z): the studs a sweep gets before it
local function wallZ(at: number): AnimWarp.Cast
	return function(_ax, az, _bx, bz, extra)
		local len = math.abs(bz - az)
		if bz < az and az > at and az - at <= len + extra then
			return az - at
		end
		return nil
	end
end

local W = { from = 0.2, to = 0.8 }

return function()
	test.suite("a root travel that meets the world: commit and cancel", function()
		local w = { from = 0.2, to = 0.8, scale = 1, turn = 0 }
		test.case("free before the window, steered to its commit point, committed after it, done at its end", function()
			check.equal(AnimWarp.phase(w, 0.1), "free")
			check.equal(AnimWarp.phase(w, 0.2), "steer")
			check.equal(AnimWarp.phase(w, 0.49), "steer")
			check.equal(AnimWarp.phase(w, 0.5), "committed")
			check.equal(AnimWarp.phase(w, 0.79), "committed")
			check.equal(AnimWarp.phase(w, 0.8), "done")
			check.equal(AnimWarp.phase(w, 0.3, { commit = 0 }), "committed") -- a move that commits at once
			check.equal(AnimWarp.phase(w, 0.79, { commit = 1 }), "steer") -- one that never does
			-- a window written backwards has no length: it is over as it begins
			check.equal(AnimWarp.phase({ from = 0.5, to = 0.2, scale = 1, turn = 0 }, 0.5), "done")
		end)
		test.case(
			"before the window a moved target changes the warp at once; a lost one gives the clip back",
			function()
				local want = { from = 0.2, to = 0.8, scale = 1.5, turn = 0.4 }
				check.truthy(AnimWarp.retarget(w, want, 0.1, 1 / 60) == want)
				check.truthy(AnimWarp.retarget(w, nil, 0.1, 1 / 60) == nil)
				-- no warp was planned (no target at the start): one may begin before its window, never inside it
				check.truthy(AnimWarp.retarget(nil, want, 0.1, 1 / 60) == want)
				check.truthy(AnimWarp.retarget(nil, want, 0.3, 1 / 60) == nil)
			end
		)
		test.case("inside the window, before the commit point, the target is followed at a bounded rate", function()
			local want = { from = 0.2, to = 0.8, scale = 1.6, turn = math.rad(35) }
			local got = AnimWarp.retarget(w, want, 0.3, 0.1) :: any
			check.truthy(near(got.scale, 1 + AnimWarp.SCALE_RATE * 0.1)) -- 0.2 of the 0.6 asked
			check.truthy(near(got.turn, AnimWarp.TURN_RATE * 0.1)) -- 18 of the 35 degrees asked
			check.truthy(got.from == 0.2 and got.to == 0.8)
			-- a small ask is met exactly, never overshot
			local small = AnimWarp.retarget(w, { from = 0.2, to = 0.8, scale = 1.01, turn = -0.01 }, 0.3, 0.1) :: any
			check.truthy(near(small.scale, 1.01) and near(small.turn, -0.01))
			local slow = AnimWarp.retarget(w, want, 0.3, 0.1, { scaleRate = 0.5, turnRate = 0.1 }) :: any
			check.truthy(near(slow.scale, 1.05) and near(slow.turn, 0.01))
			-- a clock that ran backwards changes nothing
			local back = AnimWarp.retarget(w, want, 0.3, -1) :: any
			check.truthy(back.scale == 1 and back.turn == 0)
			-- a lost target: the body is on its way, the warp stands
			check.truthy(AnimWarp.retarget(w, nil, 0.3, 0.1) == w)
		end)
		test.case("after the commit point nothing the target does changes the warp", function()
			local want = { from = 0.2, to = 0.8, scale = 0.5, turn = -0.5 }
			check.truthy(AnimWarp.retarget(w, want, 0.5, 0.1) == w)
			check.truthy(AnimWarp.retarget(w, want, 0.9, 0.1) == w)
			check.truthy(AnimWarp.retarget(w, nil, 0.6, 0.1) == w)
		end)
		test.case("a move cut short ends its travel where the body is", function()
			check.truthy(AnimWarp.cancelled(false, true) and AnimWarp.cancelled(true, false))
			check.truthy(not AnimWarp.cancelled(true, true))
		end)
		test.case("a window the rules can work with is two numbers, the end after the start", function()
			check.truthy(AnimWarp.window({ from = 0.2, to = 0.8, contact = 2 }) ~= nil)
			for _, bad in
				{
					{ from = 0.5, to = 0.2 } :: any,
					{ from = 0 / 0, to = 1 },
					{ from = 0, to = 0 / 0 },
					{ from = 0.3, to = 0.3 },
					{ from = "0", to = 1 },
					{},
					"window",
					false,
				}
			do
				check.truthy(AnimWarp.window(bad) == nil)
			end
			check.truthy(AnimWarp.window(nil) == nil)
		end)
	end)

	test.suite("a root travel that meets the world: the root track as the rules read it", function()
		test.case("the build's rows in each of their forms", function()
			local rows = AnimWarp.rows(
				{ "1 -2 0.5", { 3, -4, 0.25 }, { 0, math.sin(0.1), 0, math.cos(0.1), 5, 9, -6 }, 7, "x" } :: any
			)
			check.equal(#rows, 4)
			check.truthy(rows[1][1] == 1 and rows[1][2] == -2 and rows[1][3] == 0.5)
			check.truthy(rows[2][1] == 3 and rows[2][2] == -4 and rows[2][3] == 0.25)
			check.truthy(rows[3][1] == 5 and rows[3][2] == -6 and near(rows[3][3], 0.2)) -- the full form: px, pz, the yaw
			check.truthy(rows[4][1] == 0 and rows[4][2] == 0) -- (a row of no numbers stands still)
		end)
		test.case("a spin's yaw is carried on past a whole turn: no frame turns the long way round", function()
			-- the data's yaw is 2 * atan2(qy, qw): it jumps by whole turns as a spin goes round
			local raw = {}
			for i = 0, 60 do
				local a = 0.2 * i
				table.insert(raw, { 0, 0, (a + math.pi) % (2 * math.pi) - math.pi })
			end
			local rows = AnimWarp.rows(raw)
			for i = 2, #rows do
				check.truthy(near(rows[i][3] - rows[i - 1][3], 0.2, 1e-9))
			end
			-- sampled BETWEEN frames, as a game's clock does, no step is more than its share of 0.2
			local t = 0
			while t < 1 - 1e-9 do
				local _, _, dyaw = AnimWarp.advance(rows, 60, t, t + 1 / 240, nil)
				check.truthy(near(dyaw, 0.05, 1e-9))
				t += 1 / 240
			end
		end)
	end)

	test.suite("a root travel that meets the world: the travel, step by step", function()
		local root = straight()
		test.case("summed frame by frame it is the warped root itself, with a warp and without", function()
			for _, w in { { from = 0.2, to = 0.8, scale = 1.5, turn = math.rad(30) } :: any, false } do
				local warp = if w then w else nil
				local x, z, yaw = 0, 0, 0
				local t = 0
				while t < 1 - 1e-9 do
					local dx, dz, dyaw = AnimWarp.advance(root, 60, t, t + 1 / 120, warp)
					x, z, yaw = x + dx, z + dz, yaw + dyaw
					t += 1 / 120
				end
				local ex, ez, eyaw = AnimLayers.warpedRootAt(root, 60, 1, warp)
				check.truthy(near(x, ex, 1e-6) and near(z, ez, 1e-6) and near(yaw, eyaw, 1e-6))
			end
		end)
		test.case("a warp that changes under the travel bends what is to come and never jumps the body", function()
			local cur: any = { from = 0.2, to = 0.8, scale = 1, turn = 0 }
			local want = { from = 0.2, to = 0.8, scale = 1.6, turn = 0 }
			local z, t, longest = 0, 0, 0
			while t < 1 - 1e-9 do
				cur = AnimWarp.retarget(cur, want, t, 1 / 60)
				local _, dz = AnimWarp.advance(root, 60, t, t + 1 / 60, cur)
				longest = math.max(longest, math.abs(dz))
				z += dz
				t += 1 / 60
			end
			check.truthy(longest <= 0.1 * 1.6 + 1e-6) -- 0.1 studs a frame is the clip's own pace
			local _, whole = AnimLayers.warpedRootAt(root, 60, 0.5, want)
			local _, plain = AnimLayers.warpedRootAt(root, 60, 0.5, { from = 0.2, to = 0.8, scale = 1, turn = 0 })
			check.truthy(math.abs(whole - plain) > 0.5) -- (the jump a whole swap at 0.5 s would have been)
			check.truthy(z < -6 and z > -6 * 1.6)
		end)
	end)

	test.suite("a root travel that meets the world: swept clearance", function()
		local root = straight()
		local w = { from = 0.2, to = 0.8, scale = 1.5, turn = 0 } -- the window travels 5.4 studs, from z = -1.2
		test.case("the window's path is its warped travel, start to end", function()
			local points = AnimWarp.path(root, 60, w, 6)
			check.equal(#points, 7)
			check.truthy(near(points[1][2], -1.2) and near(points[7][2], -6.6))
			check.truthy(near(points[4][2], -1.2 - 2.7))
		end)
		test.case("a free way leaves the warp as it was", function()
			local got, cut = AnimWarp.fit(root, 60, w, function()
				return nil
			end)
			check.truthy(got.scale == 1.5 and got.turn == 0 and cut == 0)
			-- a wall the margin or more beyond the travel's end is no stop
			local far, farCut = AnimWarp.fit(root, 60, w, wallZ(-6.6 - AnimWarp.MARGIN))
			check.truthy(far.scale == 1.5 and farCut == 0)
		end)
		test.case("a wall in the way: the travel ends the margin short of it, and the cut is told", function()
			local got, cut = AnimWarp.fit(root, 60, w, wallZ(-4))
			local _, ze = AnimLayers.warpedRootAt(root, 60, 0.8, got)
			check.truthy(near(ze, -4 + AnimWarp.MARGIN, 1e-6))
			check.truthy(near(cut, 5.4 - (4 - AnimWarp.MARGIN - 1.2), 1e-6))
			check.truthy(got.from == 0.2 and got.to == 0.8 and got.turn == 0)
			-- a wall just past the travel's end, nearer than the margin: cut too
			local close = AnimWarp.fit(root, 60, w, wallZ(-6.8))
			local _, zc = AnimLayers.warpedRootAt(root, 60, 0.8, close)
			check.truthy(near(zc, -6.3, 1e-6))
			local wide = AnimWarp.fit(root, 60, w, wallZ(-4), { margin = 1.5 })
			local _, zw = AnimLayers.warpedRootAt(root, 60, 0.8, wide)
			check.truthy(near(zw, -2.5, 1e-6))
		end)
		test.case("a wall at the start: the window does not travel at all", function()
			local got, cut = AnimWarp.fit(root, 60, w, wallZ(-1.3))
			check.equal(got.scale, 0)
			check.truthy(near(cut, 5.4, 1e-6))
			local _, ze = AnimLayers.warpedRootAt(root, 60, 0.8, got)
			check.truthy(near(ze, -1.2))
		end)
		test.case("a turned travel is swept again after its cut, and only a travel seen free is taken", function()
			-- turned to the left the travel swings toward -X: a wall along x = -1
			local turned = { from = 0.2, to = 0.8, scale = 1.5, turn = math.rad(35) }
			local sweeps, lastStart = 0, math.huge
			local function wallX(ax: number, _az: number, bx: number, _bz: number, extra: number): number?
				if ax >= lastStart - 1e-9 or lastStart == math.huge then
					sweeps += 1 -- (a path's first piece: a new sweep)
				end
				lastStart = ax
				local len = math.sqrt((bx - ax) ^ 2 + (_bz - _az) ^ 2)
				local ux = (bx - ax) / len
				if ux < 0 and ax > -1 and (ax + 1) / -ux <= len + extra then
					return (ax + 1) / -ux
				end
				return nil
			end
			local xe = AnimLayers.warpedRootAt(root, 60, 0.8, turned)
			check.truthy(xe < -1) -- (unfitted it does pass the wall)
			local got = AnimWarp.fit(root, 60, turned, wallX)
			check.truthy(got.scale < 1.5 and got.scale > 0)
			for _, p in AnimWarp.path(root, 60, got, 32) do
				check.truthy(p[1] > -1)
			end
			check.truthy(sweeps >= 2) -- (the cut travel was swept again)
			-- a caster that never lets go: nothing is travelled
			local stuck = AnimWarp.fit(root, 60, turned, function()
				return 0.1
			end)
			check.equal(stuck.scale, 0)
		end)
		test.case("frame by frame: a step stops the margin short of what it meets; what it loses is told", function()
			local dx, dz, lost = AnimWarp.stepClear(0, -1, nil)
			check.truthy(dx == 0 and dz == -1 and lost == 0)
			local _, bz, blost = AnimWarp.stepClear(0, -2, 1.5, 0.5) -- met 1.5 studs in
			check.truthy(near(bz, -1) and near(blost, 1))
			local cx, cz, clost = AnimWarp.stepClear(0.3, -0.4, 0.25) -- met inside the margin
			check.truthy(cx == 0 and cz == 0 and near(clost, 0.5))
			-- met BEYOND the step but within the margin of its end: the margin is kept all the same
			local _, mz, mlost = AnimWarp.stepClear(0, -0.1, 0.4, 0.5)
			check.truthy(mz == 0 and near(mlost, 0.1))
			local _, fz, flost = AnimWarp.stepClear(0, -0.1, 0.65, 0.5) -- the margin and more to spare
			check.truthy(near(fz, -0.1) and flost == 0)
			local sx, sz, slost = AnimWarp.stepClear(0, 0, 0.2)
			check.truthy(sx == 0 and sz == 0 and slost == 0)
			local ex, ez = AnimWarp.stepClear(3, -4, 3, 1) -- 5 long, met 3 in, stops at 2: the direction is kept
			check.truthy(near(ex, 1.2) and near(ez, -1.6))
		end)
	end)

	test.suite("a root travel that meets the world: a body something else moved", function()
		test.case("a shove is taken back, a move on purpose is where the travel goes on from", function()
			check.equal(AnimWarp.displaced(0, 0), "hold")
			check.equal(AnimWarp.displaced(0.03, 0.03), "hold")
			check.equal(AnimWarp.displaced(0.5, 0), "pull")
			check.equal(AnimWarp.displaced(2, -2), "pull") -- 2.83 studs
			check.equal(AnimWarp.displaced(3, 0), "accept")
			check.equal(AnimWarp.displaced(0, -40), "accept") -- a teleport
			check.equal(AnimWarp.displaced(0 / 0, 0), "accept")
			check.equal(AnimWarp.displaced(1, 0, { snap = 0.5 }), "accept")
			check.equal(AnimWarp.displaced(1, 0, { hold = 2 }), "hold")
		end)
	end)

	test.suite("a root travel that meets the world: the root update, whole", function()
		local root = straight()
		-- the game's loop: the body is put where the step says and is there on the next frame, unless `shove` moves it
		local function run(
			s: AnimWarp.State,
			body: { x: number, z: number },
			times: { number },
			window: any,
			target: ((t: number) -> { number }?)?,
			cast: AnimWarp.Cast?,
			shove: ((t: number, body: { x: number, z: number }) -> ())?
		): (number, number, number, number)
			local yaw, prev, longest = 0, s.t, 0
			for _, t in times do
				if shove then
					shove(t, body)
				end
				local bx, bz = body.x, body.z
				local x, z, y = AnimWarp.step(
					s,
					root,
					60,
					t,
					t - prev,
					body.x,
					body.z,
					window,
					if target then target(t) else nil,
					cast
				)
				longest = math.max(longest, math.sqrt((x - bx) ^ 2 + (z - bz) ^ 2))
				body.x, body.z, yaw, prev = x, z, y, t
			end
			return body.x, body.z, yaw, longest
		end
		local function clock(from: number, to: number, step: number): { number }
			local out = {}
			local t = from + step
			while t < to - 1e-9 do
				table.insert(out, t)
				t += step
			end
			table.insert(out, to)
			return out
		end
		test.case(
			"no warp, no wall, nothing asked: the clip's own travel from where the body stood and faced",
			function()
				-- a root that bends and turns; the body stands at (10, 5) facing a quarter turn to the left (-X)
				local bent = {}
				for i = 0, 60 do
					table.insert(bent, { 0.02 * i, -0.1 * i, 0.01 * i })
				end
				local facing = math.pi / 2
				for _, step in { 1 / 60, 1 / 240, 0.0371 } do -- on the frames, between them, off any grid
					local body = { x = 10, z = 5 }
					local s = AnimWarp.begin(bent, 60, 0, { x = 10, z = 5, yaw = facing }, nil, nil, nil)
					local yaw = 0
					for _, t in clock(0, 1, step) do
						local x, z, y = AnimWarp.step(s, bent, 60, t, step, body.x, body.z, nil, nil, nil)
						body.x, body.z, yaw = x, z, y
						-- at EVERY frame: the clip's root there, turned to the body's facing (-Z ahead becomes -X)
						local rx, rz, ryaw = AnimLayers.rootSample(bent, 60, t)
						check.truthy(near(x, 10 + rz, 1e-6) and near(z, 5 - rx, 1e-6) and near(y, facing + ryaw, 1e-6))
					end
					check.truthy(
						near(body.x, 10 - 6, 1e-6) and near(body.z, 5 - 1.2, 1e-6) and near(yaw, facing + 0.6, 1e-6)
					)
				end
			end
		)
		test.case("entered late, or first seen some way in: only what is left is travelled", function()
			local body = { x = 0, z = 0 }
			local s = AnimWarp.begin(root, 60, 0.5, { x = 0, z = 0, yaw = 0 }, nil, nil, nil)
			local _, z, _, longest = run(s, body, clock(0.5, 1, 1 / 60), nil)
			check.truthy(near(z, -3, 1e-6)) -- the second half of 6 studs
			check.truthy(longest <= 0.1 + 1e-6) -- and no jump on its first frame
		end)
		test.case("a wall in the way of a travel with no warp: the body stops short and never catches up", function()
			local body = { x = 0, z = 0 }
			local wall: AnimWarp.Cast? = wallZ(-3)
			local function cast(ax, az, bx, bz, extra)
				return if wall then wall(ax, az, bx, bz, extra) else nil
			end
			local s = AnimWarp.begin(root, 60, 0, { x = 0, z = 0, yaw = 0 }, nil, nil, cast)
			local _, z = run(s, body, clock(0, 0.7, 1 / 60), nil, nil, cast)
			check.truthy(z <= -3 + AnimWarp.MARGIN + 0.1 + 1e-6 and z >= -3 + AnimWarp.MARGIN - 1e-6) -- within a step of the margin
			-- the wall goes away: the travel goes on at the clip's pace from where the body stands
			wall = nil
			local _, z2, _, longest = run(s, body, clock(0.7, 1, 1 / 60), nil, nil, cast)
			check.truthy(near(z2, z - 6 * 0.3, 1e-6) and longest <= 0.1 + 1e-6)
		end)
		test.case("a body moved on purpose keeps its new place; a shoved one is taken back to its line", function()
			local body = { x = 0, z = 0 }
			local s = AnimWarp.begin(root, 60, 0, { x = 0, z = 0, yaw = 0 }, nil, nil, nil)
			local x, z = run(s, body, clock(0, 1, 1 / 60), nil, nil, nil, function(t, b)
				if near(t, 0.5, 1e-9) then
					b.x += 20 -- a knockback, a teleport
				end
			end)
			check.truthy(near(x, 20, 1e-6) and near(z, -6, 1e-6))
			local body2 = { x = 0, z = 0 }
			local s2 = AnimWarp.begin(root, 60, 0, { x = 0, z = 0, yaw = 0 }, nil, nil, nil)
			local x2, z2 = run(s2, body2, clock(0, 1, 1 / 60), nil, nil, nil, function(t, b)
				if near(t, 0.5, 1e-9) then
					b.x += 1
				end
			end)
			check.truthy(near(x2, 0, 1e-6) and near(z2, -6, 1e-6))
		end)
		test.case(
			"a track wound back: a jitter goes back with it, a replay is a new travel from where the body is",
			function()
				local s = AnimWarp.begin(root, 60, 0, { x = 0, z = 0, yaw = 0 }, nil, nil, nil)
				local _, z1 = AnimWarp.step(s, root, 60, 0.5, 0.5, 0, 0, nil, nil, nil)
				check.truthy(near(z1, -3))
				-- a clock that reads one frame back: the body goes back that frame's travel
				local _, zj = AnimWarp.step(s, root, 60, 0.5 - 1 / 60, 1 / 60, 0, -3, nil, nil, nil)
				check.truthy(near(zj, -2.9))
				-- played again from 0.2 s while it still plays (a motion set's jump within a clip): the body is NOT carried
				-- back the 1.7 studs - it stays, and travels on from there
				local x, z = AnimWarp.step(s, root, 60, 0.2, 1 / 60, 0, zj, nil, nil, nil)
				check.truthy(x == 0 and near(z, zj))
				local _, z2 = AnimWarp.step(s, root, 60, 0.3, 0.1, 0, z, nil, nil, nil)
				check.truthy(near(z2, zj - 0.6))
				-- its facing is kept too
				local turned = AnimWarp.begin(root, 60, 0, { x = 0, z = 0, yaw = 0.7 }, nil, nil, nil)
				AnimWarp.step(turned, root, 60, 0.5, 0.5, 0, 0, nil, nil, nil)
				local _, _, yaw = AnimWarp.step(turned, root, 60, 0.1, 1 / 60, 5, 5, nil, nil, nil)
				check.truthy(near(yaw, 0.7))
			end
		)
		test.case(
			"a target: the window's travel ends the contact distance short of it, from where the window begins",
			function()
				-- 7 studs ahead: the window begins 1.2 in, so 2.8 of its own 3.6 studs bring the body 3 short
				local body = { x = 0, z = 0 }
				local tgt = { 0, -7 }
				local s = AnimWarp.begin(root, 60, 0, { x = 0, z = 0, yaw = 0 }, W, tgt, nil)
				local _, z = run(s, body, clock(0, 0.8, 1 / 60), W, function()
					return tgt
				end)
				check.truthy(near(z, -4, 1e-6))
				-- a target off to the left: the body ends on the line to it, turned its way
				local body2 = { x = 0, z = 0 }
				local side = { -2, -1.2 - 5 }
				local s2 = AnimWarp.begin(root, 60, 0, { x = 0, z = 0, yaw = 0 }, W, side, nil)
				local x2, z2, yaw2 = run(s2, body2, clock(0, 0.8, 1 / 60), W, function()
					return side
				end)
				local angle = math.atan2(2, 5)
				check.truthy(near(yaw2, angle, 1e-6))
				local reach = math.sqrt(29) - 3
				check.truthy(
					near(x2, -reach * math.sin(angle), 1e-6) and near(z2, -1.2 - reach * math.cos(angle), 1e-6)
				)
			end
		)
		test.case(
			"a target that moves before the window is met where it is; after the commit point it is not followed",
			function()
				local body = { x = 0, z = 0 }
				local s = AnimWarp.begin(root, 60, 0, { x = 0, z = 0, yaw = 0 }, W, { 0, -7 }, nil)
				local _, z = run(s, body, clock(0, 0.8, 1 / 60), W, function(t)
					return if t < 0.1 then { 0, -7 } else { 0, -6 }
				end)
				check.truthy(near(z, -3, 1e-6))
				local body2 = { x = 0, z = 0 }
				local s2 = AnimWarp.begin(root, 60, 0, { x = 0, z = 0, yaw = 0 }, W, { 0, -7 }, nil)
				local _, z2 = run(s2, body2, clock(0, 0.8, 1 / 60), W, function(t)
					return if t < 0.55 then { 0, -7 } else { 0, -5.5 }
				end)
				check.truthy(near(z2, -4, 1e-6))
				-- a target lost before the window: the clip's own travel
				local body3 = { x = 0, z = 0 }
				local s3 = AnimWarp.begin(root, 60, 0, { x = 0, z = 0, yaw = 0 }, W, { 0, -7 }, nil)
				local _, z3 = run(s3, body3, clock(0, 0.8, 1 / 60), W, function(t)
					return if t < 0.1 then { 0, -7 } else nil
				end)
				check.truthy(near(z3, -4.8, 1e-6))
				-- a target that appears inside the window is not reached for
				local body4 = { x = 0, z = 0 }
				local s4 = AnimWarp.begin(root, 60, 0, { x = 0, z = 0, yaw = 0 }, W, nil, nil)
				local _, z4 = run(s4, body4, clock(0, 0.8, 1 / 60), W, function(t)
					return if t < 0.3 then nil else { 0, -9 }
				end)
				check.truthy(near(z4, -4.8, 1e-6))
			end
		)
		test.case("a target that runs inside the window is followed at the bounded rate, and no frame jumps", function()
			local body = { x = 0, z = 0 }
			local s = AnimWarp.begin(root, 60, 0, { x = 0, z = 0, yaw = 0 }, W, { 0, -7 }, nil)
			local _, z, _, longest = run(s, body, clock(0, 0.8, 1 / 60), W, function(t)
				return if t < 0.25 then { 0, -7 } else { 0, -9 }
			end)
			check.truthy(z < -4 - 0.2 and z > -6) -- further than the first plan, short of the new ask: it began late
			check.truthy(longest <= 0.1 * 1.6 + 1e-6)
		end)
		test.case("what a wall cut from the window's travel is not grown back by steering", function()
			-- the target stands behind a wall 4 studs ahead: the plan is cut to end at -3.5
			local body = { x = 0, z = 0 }
			local cast = wallZ(-4)
			local tgt = { 0, -9 }
			local s = AnimWarp.begin(root, 60, 0, { x = 0, z = 0, yaw = 0 }, W, tgt, cast)
			check.truthy(s.cap < 1 and near((s.warp :: any).scale, s.cap))
			local _, z, _, longest = run(s, body, clock(0, 0.8, 1 / 60), W, function()
				return tgt
			end, cast)
			check.truthy(near(z, -3.5, 1e-6))
			check.truthy(longest <= 0.1 + 1e-6)
			check.truthy(near((s.warp :: any).scale, s.cap)) -- through the whole steer phase
		end)
	end)

	test.suite("timing that follows the distance: the wind-up pays for the travel (AN-14)", function()
		-- a move that stands for `still` seconds, then walks 6 studs in `run` seconds; 60 frames a second
		local function lunge(still: number, run: number): { { number } }
			local root = {}
			local a, b = math.floor(still * 60 + 0.5), math.floor(run * 60 + 0.5)
			for _ = 0, a do
				table.insert(root, { 0, 0, 0 })
			end
			for i = 1, b do
				table.insert(root, { 0, -6 * i / b, 0 })
			end
			return root
		end
		local window = { from = 0, to = 1 }
		test.case("a far target: a shorter wind-up, a longer run - and the same time to the window's end", function()
			local root = lunge(0.4, 0.6)
			local p = AnimWarp.pace(root, 60, window, 1.5) :: AnimWarp.Pace
			check.truthy(p)
			check.is_true(p.travel < 1 and p.wind > 1)
			check.is_true(near(AnimWarp.paceSeconds(p, 60), 1, 1e-6))
			-- the feet's speed over the floor: 1.5 times the clip's unpaced, less when paced (scale x rate)
			check.is_true(1.5 * p.travel < 1.5 - 0.2)
			check.is_true(p.travel >= 1 / AnimWarp.PACE_TRAVEL - 1e-9 and p.wind <= AnimWarp.PACE_WIND + 1e-9)
			-- where it stands it plays at the wind-up's rate, where it travels at the travel's, after the window at 1
			check.is_true(near(AnimWarp.paceRate(p, 60, 0.1), p.wind))
			check.is_true(near(AnimWarp.paceRate(p, 60, 0.7), p.travel))
			check.is_true(AnimWarp.paceRate(p, 60, 1.0) == 1 and AnimWarp.paceRate(p, 60, 1.4) == 1)
			check.is_true(AnimWarp.paceRate(nil, 60, 0.3) == 1)
		end)
		test.case("a near target: a longer wind-up, a quicker step - the same time again", function()
			local root = lunge(0.4, 0.6)
			local p = AnimWarp.pace(root, 60, window, 0.5) :: AnimWarp.Pace
			check.is_true(p.travel > 1 and p.wind < 1)
			check.is_true(near(AnimWarp.paceSeconds(p, 60), 1, 1e-6))
			check.is_true(0.5 * p.travel > 0.5 + 0.1) -- (the feet: nearer the clip's own speed than half of it)
			check.is_true(p.travel <= AnimWarp.PACE_TRAVEL + 1e-9 and p.wind >= 1 / AnimWarp.PACE_WIND - 1e-9)
		end)
		test.case("every scale a warp may ask for keeps the time, inside the bounds", function()
			for _, shape in { { 0.4, 0.6 }, { 0.1, 0.9 }, { 0.8, 0.2 }, { 0.5, 0.5 } } do
				local root = lunge(shape[1], shape[2])
				for k = 0, 11 do
					local scale = 0.5 + k * 0.1
					local p = AnimWarp.pace(root, 60, window, scale)
					if p then
						check.is_true(near(AnimWarp.paceSeconds(p, 60), p.to - p.from, 1e-6))
						check.is_true(
							p.travel >= 1 / AnimWarp.PACE_TRAVEL - 1e-9 and p.travel <= AnimWarp.PACE_TRAVEL + 1e-9
						)
						check.is_true(p.wind >= 1 / AnimWarp.PACE_WIND - 1e-9 and p.wind <= AnimWarp.PACE_WIND + 1e-9)
						check.is_true((p.travel < 1) == (scale > 1))
					else
						check.is_true(near(scale, 1, 0.021))
					end
				end
			end
		end)
		test.case("a short wind-up gives what it has: the travel's rate is held by it", function()
			-- 0.1 s of standing can become 0.067 s at the least: 0.033 s is all the 0.9 s run gets
			local p = AnimWarp.pace(lunge(0.1, 0.9), 60, window, 1.6) :: AnimWarp.Pace
			check.is_true(near(p.wind, AnimWarp.PACE_WIND, 1e-6))
			check.is_true(p.travel > 0.95 and p.travel < 1)
		end)
		test.case("nothing to pace: no wind-up, no travel, no scale to speak of, a window already over", function()
			check.is_true(AnimWarp.pace(straight(), 60, window, 1.5) == nil) -- it travels from its first frame
			check.is_true(AnimWarp.pace(lunge(0.4, 0.6), 60, window, 1.01) == nil)
			local stand = {}
			for _ = 0, 60 do
				table.insert(stand, { 0, 0, 0 })
			end
			check.is_true(AnimWarp.pace(stand, 60, window, 1.5) == nil)
			check.is_true(AnimWarp.pace(lunge(0.4, 0.6), 60, window, 1.5, 1.0) == nil)
			check.is_true(AnimWarp.pace(lunge(0.4, 0.6), 60, window, 0 / 0) == nil)
		end)
		test.case("entered part way in: only what is left is paced, and its time is kept", function()
			local p = AnimWarp.pace(lunge(0.4, 0.6), 60, window, 1.5, 0.2) :: AnimWarp.Pace
			check.is_true(near(p.from, 0.2, 1e-6) and near(p.to, 1, 1e-6))
			check.is_true(near(AnimWarp.paceSeconds(p, 60), 0.8, 1e-6))
			check.is_true(AnimWarp.paceRate(p, 60, 0.1) == 1)
		end)
		test.case("one slow frame in a run is the run's, and the game asks the rule", function()
			local root = lunge(0.4, 0.6)
			root[40] = table.clone(root[39]) -- (a frame that does not move, in the middle of the run)
			local p = AnimWarp.pace(root, 60, window, 1.5) :: AnimWarp.Pace
			local flips = 0
			for i = 2, #p.rates do
				if p.rates[i] ~= p.rates[i - 1] then
					flips += 1
				end
			end
			check.is_true(flips == 1)
			local anim = fs.readFile("src/kit/Anim.luau")
			for _, line in
				{
					"if window and window.pace then",
					"paceClock = AnimWarp.paceClock()",
					"local paceDt = if clock.scale == nil then 0 else gameNow - lastGame",
					"local lastGame = time()",
					"AnimWarp.paceStep(clock, root, fps, window, if warp then warp.scale else nil, t, paceDt, track.Speed)",
					"track:AdjustSpeed(want)",
				}
			do
				check.truthy(string.find(anim, line, 1, true) ~= nil)
			end
			local strike = fs.readFile("kit/anim/strike.py")
			check.truthy(string.find(strike, 'clip["warp"]["pace"] = True', 1, true) ~= nil)
		end)
		test.case("the plan's rate and its clock, frame by frame, at their edges", function()
			local p = AnimWarp.pace(lunge(0.4, 0.6), 60, window, 1.5) :: AnimWarp.Pace
			-- the first 24 steps stand, the 36 after travel (the vote of three moves the edge by none here)
			check.is_true(
				near(AnimWarp.paceRate(p, 60, 0), p.wind) and near(AnimWarp.paceRate(p, 60, 23.9 / 60), p.wind)
			)
			check.is_true(
				near(AnimWarp.paceRate(p, 60, 25.1 / 60), p.travel)
					and near(AnimWarp.paceRate(p, 60, 59.9 / 60), p.travel)
			)
			check.is_true(AnimWarp.paceRate(p, 60, -0.01) == 1)
			-- the clock: where the clip is after so many real seconds - and back
			check.is_true(near(AnimWarp.paceAt(p, 60, 0), 0, 1e-9))
			local windSeconds = (24 / 60) / p.wind
			check.is_true(near(AnimWarp.paceAt(p, 60, windSeconds), 24 / 60, 1e-6))
			check.is_true(near(AnimWarp.paceAt(p, 60, windSeconds / 2), 12 / 60, 1e-6))
			check.is_true(near(AnimWarp.paceAt(p, 60, 1), 1, 1e-6))
			check.is_true(near(AnimWarp.paceAt(p, 60, 1.25), 1.25, 1e-6)) -- after the plan: as drawn
		end)
		-- THE ENGINE, MADE UP: each real frame the clip goes on by speed x the frame, then the rule is asked (as the
		-- Heartbeat does) -> the real seconds at which the clip reaches the window's end
		local function play(
			root: { { number } },
			w: AnimWarp.Window,
			scaleAt: (t: number) -> number?,
			frames: { number },
			outside: ((real: number, speed: number) -> number)?
		): (number, number)
			local c = AnimWarp.paceClock()
			local t, real, speed, k, sets = 0, 0, 1, 0, 0
			local felt = speed -- (a speed set now is felt a frame later: Studio)
			while real < 10 do
				k += 1
				local d = frames[(k - 1) % #frames + 1]
				local before = t
				t += felt * d
				if t >= w.to then
					return real + (w.to - before) / felt, sets
				end
				felt = speed
				real += d
				if outside then
					speed = outside(real, speed)
				end
				local want = AnimWarp.paceStep(c, root, 60, w, scaleAt(t), t, d, speed)
				if want then
					speed = want
					sets += 1
				end
			end
			return real, sets
		end
		local uneven = { 1 / 60, 1 / 25, 1 / 40, 1 / 15, 1 / 60, 1 / 30 }
		test.case("played frame by frame the window's end comes when it would have, within 25 ms", function()
			-- (the first cut picked a rate from where the clip was: up to 53 ms short on uneven frames)
			local zig = {}
			for i = 0, 60 do
				local z = if i <= 12
					then 0
					elseif i <= 27 then -(i - 12) * 0.2
					elseif i <= 42 then -3
					else -3 - (i - 42) * 0.2
				table.insert(zig, { 0, z, 0 })
			end
			for _, root in { lunge(0.4, 0.6), lunge(0.2, 0.8), lunge(0.7, 0.3), zig } do
				for _, frames in { { 1 / 60 }, { 1 / 30 }, { 1 / 20 }, uneven } do
					for k = 0, 11 do
						local scale = 0.5 + k * 0.1
						local real = play(root, window, function()
							return scale
						end, frames)
						check.is_true(math.abs(real - 1) < 0.025)
					end
				end
			end
			-- ... and it does pace: the clip is behind an unpaced one in the wind-up of a near target
			local c = AnimWarp.paceClock()
			local want = AnimWarp.paceStep(c, lunge(0.4, 0.6), 60, window, 0.5, 0, 0, 1)
			check.is_true(want ~= nil and (want :: number) < 0.9)
			-- the speed asked stays near the plan's two rates: never thrown to the clock's bounds (the first fix of
			-- the review asked for a whole miss back in one frame, and in Studio swung between 0.25 and 3)
			local c2 = AnimWarp.paceClock()
			local root = lunge(0.4, 0.6)
			local t, speed, felt = 0, 1, 1
			local low, high = math.huge, 0
			while t < 1 do
				t += felt / 60
				felt = speed
				speed = AnimWarp.paceStep(c2, root, 60, window, 1.5, t, 1 / 60, speed) or speed
				if t < 1 then
					low, high = math.min(low, speed), math.max(high, speed)
				end
			end
			local plan = c2.pace or AnimWarp.pace(root, 60, window, 1.5) :: AnimWarp.Pace
			check.is_true(low > plan.travel - 0.15 and high < plan.wind + 0.15)
		end)
		test.case("a target that closes in is paced anew in the time that is left", function()
			-- planned for a far target, then a near one from 0.2 s on: the travel is played FASTER after it
			local root = lunge(0.4, 0.6)
			local c = AnimWarp.paceClock()
			AnimWarp.paceStep(c, root, 60, window, 1.6, 0, 0, 1)
			local far = (c.pace :: AnimWarp.Pace).travel
			AnimWarp.paceStep(c, root, 60, window, 0.5, 0.2, 0.2, 1)
			local near2 = (c.pace :: AnimWarp.Pace).travel
			check.is_true(far < 1 and near2 > 1)
			-- a scale that moves a little is the same plan
			local kept = c.pace
			AnimWarp.paceStep(c, root, 60, window, 0.55, 0.22, 1 / 60, c.set :: number)
			check.is_true(c.pace == kept)
			local real = play(root, window, function(t)
				return if t < 0.2 then 1.6 else 0.5
			end, { 1 / 60 })
			check.is_true(math.abs(real - 1) < 0.025)
			-- no warp yet, then one: the plan begins when the warp does, with what is left
			real = play(root, window, function(t)
				return if t < 0.1 then nil else 1.5
			end, { 1 / 60 })
			check.is_true(math.abs(real - 1) < 0.025)
		end)
		test.case("somebody else's speed is kept: a slow motion, a caller's own, a hit-stop", function()
			local root = lunge(0.4, 0.6)
			-- the whole move at 1.2 by its caller: the window's end at 1 / 1.2 s
			local c = AnimWarp.paceClock()
			local t, real, speed = 0, 0, 1.2
			while t < 1 do
				local before = t
				t += speed / 60
				if t >= 1 then
					real += (1 - before) / speed
					break
				end
				real += 1 / 60
				speed = AnimWarp.paceStep(c, root, 60, window, 1.5, t, 1 / 60, speed) or speed
			end
			check.is_true(math.abs(real - 1 / 1.2) < 0.025)
			-- a slow motion of x0.3 from 0.3 s on: the rest takes 0.3 times as fast (the first cut undid it in a frame)
			local slowed = false
			local ends = play(root, window, function()
				return 1.5
			end, { 1 / 60 }, function(realNow, sp)
				if realNow >= 0.3 and not slowed then
					slowed = true
					return 0.3
				end
				return sp
			end)
			check.is_true(ends > 2.2 and ends < 2.9)
			-- a hit-stop (speed 0) is left alone and spends none of the plan
			local held = AnimWarp.paceClock()
			AnimWarp.paceStep(held, root, 60, window, 1.5, 0, 0, 1)
			local spent = held.spent
			check.is_true(AnimWarp.paceStep(held, root, 60, window, 1.5, 0.1, 0.5, 0) == nil and held.spent == spent)
			-- after the window the speed is the caller's again, once
			local done = AnimWarp.paceClock()
			AnimWarp.paceStep(done, root, 60, window, 1.5, 0, 0, 1)
			check.is_true(
				near(AnimWarp.paceStep(done, root, 60, window, 1.5, 1.0, 1 / 60, done.set :: number) :: number, 1)
			)
			check.is_true(done.done and AnimWarp.paceStep(done, root, 60, window, 1.5, 1.1, 1 / 60, 1) == nil)
		end)
		test.case(
			"travel before the window is the clip's own, and a travel a wall cut to nothing is not paced",
			function()
				-- a step in (frames 6..18), a stand, then the window's lunge from 0.6 s
				local root = {}
				for i = 0, 60 do
					local z = if i <= 6
						then 0
						elseif i <= 18 then -(i - 6) * 0.1
						elseif i <= 36 then -1.2
						else -1.2 - (i - 36) * 0.2
					table.insert(root, { 0, z, 0 })
				end
				local w = { from = 0.6, to = 1 }
				local p = AnimWarp.pace(root, 60, w, 1.6) :: AnimWarp.Pace
				check.is_true(near(AnimWarp.paceRate(p, 60, 12 / 60), 1)) -- (the first cut played the step-in slower)
				check.is_true(AnimWarp.paceRate(p, 60, 2 / 60) > 1 and AnimWarp.paceRate(p, 60, 50 / 60) < 1)
				check.is_true(near(AnimWarp.paceSeconds(p, 60), 1, 1e-6))
				check.is_true(AnimWarp.pace(lunge(0.4, 0.6), 60, window, 0) == nil)
				check.is_true(AnimWarp.pace(lunge(0.4, 0.6), 60, window, 0.01) == nil)
			end
		)
	end)

	test.suite("a root travel that meets the world: the game calls the rules", function()
		test.case("the root update is the rules' own, with a cast that also sees what it starts inside", function()
			local anim = fs.readFile("src/kit/Anim.luau")
			for _, line in
				{
					'local AnimWarp = require("./AnimWarp")',
					"local root = AnimWarp.rows(raw)",
					"local window = AnimWarp.window(clipMeta.warp)",
					"AnimWarp.cancelled(track.IsPlaying, rootPart.Parent ~= nil)",
					"s = AnimWarp.begin(",
					"AnimWarp.step(s :: AnimWarp.State, root, fps, t, dt, here.X, here.Z, window, targetNow(), cast)",
					"workspace:Spherecast(from, BALL, dir.Unit * (len + extra), params)",
					"workspace:GetPartBoundsInRadius(Vector3.new(bx, y, bz), PROBE, over)",
					"params.RespectCanCollide = true",
					"known.enteredAt = known.enteredAt or enteredAt",
				}
			do
				check.truthy(string.find(anim, line, 1, true) ~= nil)
			end
		end)
	end)
end

-- animwhole.spec.luau — THE WHOLE RULE of three runtime rule sets the game already runs (the owner's method lists,
-- 2026-11-14: animation state machines, blend trees, motion warping): the cases the older specs did not have - the
-- attack state machine's cancel window at its edges, the busy state, the parry's lockout; the locomotion blend's own
-- back / strafe clips, a partial set, the air; the motion warp inside and after its window.
local frk = require("../frk")
local fs = require("@lune/fs")
local roblox = require("@lune/roblox")
local Vector3 = (roblox :: any).Vector3
local test, check = frk.test, frk.check

local AnimBlend = require("../../../src/kit/AnimBlend")
local AnimLayers = require("../../../src/kit/AnimLayers")
local MovesRules = require("../../../src/kit/MovesRules")

local function near(a: number, b: number, tol: number?): boolean
	return math.abs(a - b) <= (tol or 1e-9)
end

-- startup 10, active 4, recovery 20: frames 0..33; it may be cancelled into B on frames 16..30
local A = {
	name = "A",
	frames = { fps = 60, startup = 10, active = 4, recovery = 20 },
	cancel = { into = { "B" }, from = 16, to = 30 },
}
local B = { name = "B", frames = { fps = 60, startup = 8, active = 3, recovery = 12 } }
local SET = {
	moves = { A = A, B = B, Taunt = { name = "Taunt", frames = { fps = 60, startup = 5, active = 1, recovery = 5 } } },
	combo = { "A", "B" },
}

return function()
	test.suite("the attack state machine, whole", function()
		test.case("the cancel window opens ON its first frame and closes AFTER its last", function()
			check.equal(MovesRules.canCancel(A, 15 / 60, "B"), false)
			check.equal(MovesRules.canCancel(A, 16 / 60, "B"), true)
			check.equal(MovesRules.canCancel(A, 30 / 60, "B"), true)
			check.equal(MovesRules.canCancel(A, 30.9 / 60, "B"), true) -- still frame 30
			check.equal(MovesRules.canCancel(A, 31 / 60, "B"), false)
			check.equal(MovesRules.canCancel(B, 5 / 60, "A"), false) -- a move with no cancel table
			check.equal(MovesRules.canCancel({ cancel = { into = { "B" } } }, 0.2, "B"), false) -- a window with no frames
		end)
		test.case("busy: nothing starts during a move outside its window, the reason is said; done = free", function()
			local function try(name: string, t: number): (boolean, string?)
				local ok, why =
					MovesRules.allowed(SET, { moveName = "A", moveT = t, comboIndex = 1, lastUsed = {} }, name, 10)
				return ok, why
			end
			local ok1, why1 = try("B", 15 / 60)
			check.truthy(ok1 == false and why1 == "busy")
			check.truthy((try("B", 16 / 60)) == true and (try("B", 30 / 60)) == true)
			local ok2, why2 = try("B", 31 / 60) -- the window has closed, the move is not over
			check.truthy(ok2 == false and why2 == "busy")
			local ok3, why3 = try("Taunt", 20 / 60) -- inside the window, but not a move it cancels into
			check.truthy(ok3 == false and why3 == "busy")
			check.truthy((try("Taunt", 34 / 60)) == true) -- the move is done: anything not in the combo may start
			check.truthy((try("A", 34 / 60)) == true)
		end)
		test.case("the combo: from the window, or inside the gap after the move ended - not after it", function()
			local function after(ended: number, gap: number?): boolean
				local s = { lastName = "A", lastEnded = ended, comboIndex = 1, lastUsed = {} }
				return (MovesRules.allowed(SET, s, "B", 10, gap))
			end
			check.truthy(after(9.2) == true and after(9.0) == false) -- the default gap is 0.9 s
			check.truthy(after(9.9, 0.2) == true and after(9.7, 0.2) == false) -- a game's own gap
			local ok, why, idx = MovesRules.allowed(SET, { comboIndex = 0, lastUsed = {} }, "Ghost", 10)
			check.truthy(ok == false and why == "unknown move" and idx == 0)
			local _, _, i = MovesRules.allowed(SET, { comboIndex = 3, lastUsed = {} }, "Taunt", 10)
			check.equal(i, 1) -- a move outside the combo starts the count again
			local _, _, i2 =
				MovesRules.allowed(SET, { moveName = "A", moveT = 20 / 60, comboIndex = 1, lastUsed = {} }, "B", 10)
			check.equal(i2, 2)
		end)
		test.case("a cooldown ends exactly when it has run", function()
			local set = {
				moves = {
					B = { name = "B", cooldown = 2, frames = { fps = 60, startup = 1, active = 1, recovery = 1 } },
				},
			}
			check.equal((MovesRules.allowed(set, { lastUsed = { B = 8.01 } }, "B", 10)), false)
			check.equal((MovesRules.allowed(set, { lastUsed = { B = 8 } }, "B", 10)), true)
			check.equal((MovesRules.allowed(set, { lastUsed = {} }, "B", 10)), true)
		end)
		test.case("the input buffer after the window has closed: the move's end", function()
			check.truthy(near(MovesRules.waitFor(A, 31 / 60, "B"), (34 - 31) / 60))
			check.truthy(near(MovesRules.waitFor(A, 16 / 60, "B"), 0) and near(MovesRules.waitFor(A, 30 / 60, "B"), 0))
			check.truthy(near(MovesRules.waitFor(A, 40 / 60, "B"), 0)) -- the move is over: now
		end)
		test.case("the input buffer BEFORE the window: until it opens; a cooldown is said before busy", function()
			check.truthy(near(MovesRules.waitFor(A, 4 / 60, "B"), 12 / 60)) -- frame 4: the window opens at 16
			check.truthy(near(MovesRules.waitFor(A, 4 / 60, "Taunt"), 30 / 60)) -- not a cancel: the move's end (frame 34)
			local set = { moves = { A = A, B = { name = "B", cooldown = 5, frames = B.frames } }, combo = { "A", "B" } }
			local state = { moveName = "A", moveT = 5 / 60, comboIndex = 1, lastUsed = { B = 8 } }
			local ok, why = MovesRules.allowed(set, state, "B", 10) -- on cooldown AND the move is busy
			check.truthy(ok == false and why == "cooldown")
			state.lastUsed = {}
			local ok2, why2 = MovesRules.allowed(set, state, "B", 10)
			check.truthy(ok2 == false and why2 == "busy")
		end)
		test.case("a parry: its window, then a lockout", function()
			check.equal(MovesRules.parryAllowed(nil, 10), true)
			check.equal(MovesRules.parryAllowed(10, 10 + MovesRules.PARRY_COOLDOWN - 0.01), false)
			check.equal(MovesRules.parryAllowed(10, 10 + MovesRules.PARRY_COOLDOWN + 1e-9), true)
			check.truthy(MovesRules.PARRY_COOLDOWN > MovesRules.PARRY_WINDOW) -- the lockout outlasts the window: no window held open
			check.equal(MovesRules.parryAllowed(0 / 0, 10), true)
			local moves = fs.readFile("src/kit/Moves.luau")
			check.truthy(string.find(moves, "MovesRules.parryAllowed(s.parryAt, now)", 1, true) ~= nil)
		end)
	end)

	test.suite("the locomotion blend, whole", function()
		local meta = {
			Walk = { speed = 6.8 },
			Run = { speed = 10.8 },
			Back = { speed = 4 },
			StrafeL = { speed = 5 },
			StrafeR = { speed = 5.3 },
		}
		local full = {
			idle = "Idle",
			walk = "Walk",
			run = "Run",
			back = "Back",
			strafeLeft = "StrafeL",
			strafeRight = "StrafeR",
		}
		local function sum(w: any): number
			local s = 0
			for _, p in w do
				s += p.weight
			end
			return s
		end
		test.case("backward and left have their OWN clips, played forward at their own ground speed", function()
			local w = AnimBlend.weights(full, meta, Vector3.new(0, 0, 1), 4)
			check.truthy(w.Back ~= nil and near(w.Back.weight, 1) and near(w.Back.rate, 1) and w.Walk == nil)
			local l = AnimBlend.weights(full, meta, Vector3.new(-1, 0, 0), 10)
			check.truthy(
				l.StrafeL ~= nil and near(l.StrafeL.weight, 1) and near(l.StrafeL.rate, 2) and l.StrafeR == nil
			)
			local d = AnimBlend.weights(full, meta, Vector3.new(-1, 0, 1), 5) -- back-left: half each
			check.truthy(near(d.Back.weight, 0.5) and near(d.StrafeL.weight, 0.5) and near(sum(d), 1))
		end)
		test.case("a set with its own back clip and no strafes: sideways is the walk, played forward", function()
			local set = { idle = "Idle", walk = "Walk", back = "Back" }
			local side = AnimBlend.weights(set, meta, Vector3.new(1, 0, 0), 5)
			check.truthy(near(side.Walk.weight, 1) and near(side.Walk.rate, 5 / 6.8) and side.Back == nil)
			local diag = AnimBlend.weights(set, meta, Vector3.new(1, 0, 1), 5) -- back-right: the back clip and the walk
			check.truthy(near(diag.Back.weight, 0.5) and near(diag.Back.rate, 5 / 4) and near(diag.Walk.weight, 0.5))
			check.truthy(near(diag.Walk.rate, 5 / 6.8)) -- the walk carries the sideways half: forward, never reversed
		end)
		test.case("a walk-only set walks at any speed; a run-only set runs", function()
			local w = AnimBlend.weights({ idle = "Idle", walk = "Walk" }, meta, Vector3.new(0, 0, -1), 20)
			check.truthy(near(w.Walk.weight, 1) and near(w.Walk.rate, 20 / 6.8) and w.Run == nil)
			local r = AnimBlend.weights({ idle = "Idle", run = "Run" }, meta, Vector3.new(0, 0, -1), 5.4)
			check.truthy(near(r.Run.weight, 1) and near(r.Run.rate, 0.5))
		end)
		test.case("what a set lacks, what plays carries the whole weight", function()
			-- only a left strafe, moving forward-left: forward has no clip, the strafe carries it all
			local w = AnimBlend.weights({ idle = "Idle", strafeLeft = "StrafeL" }, meta, Vector3.new(-1, 0, -1), 5)
			check.truthy(near(w.StrafeL.weight, 1) and near(sum(w), 1) and w.Idle == nil)
			-- only an idle, moving: the idle (never a silent character)
			local i = AnimBlend.weights({ idle = "Idle" }, meta, Vector3.new(0, 0, -1), 10)
			check.truthy(near(i.Idle.weight, 1))
		end)
		test.case("a clip the build measured no speed for is taken at 8 (a walk) or 16 (a run)", function()
			local w = AnimBlend.weights({ idle = "Idle", walk = "Stroll" }, {}, Vector3.new(0, 0, -1), 8)
			check.truthy(near(w.Stroll.rate, 1))
			local r = AnimBlend.weights({ idle = "Idle", run = "Dash" }, {}, Vector3.new(0, 0, -1), 16)
			check.truthy(near(r.Dash.rate, 1))
		end)
		test.case("a walk asked for backwards and sideways in equal parts still moves its feet", function()
			local w = AnimBlend.weights({ idle = "Idle", walk = "Walk" }, meta, Vector3.new(-1, 0, 1), 6)
			check.truthy(near(w.Walk.weight, 1) and near(w.Walk.rate, AnimBlend.MIN_RATE)) -- never a rate of 0: a statue
			local back = AnimBlend.weights({ idle = "Idle", walk = "Walk" }, meta, Vector3.new(0, 0, 1), 6.8)
			check.truthy(near(back.Walk.rate, -1)) -- straight back: the walk played backwards
		end)
		test.case("idle below half a stud a second, with no direction, or straight up", function()
			check.truthy(AnimBlend.weights(full, meta, Vector3.new(0, 0, -1), AnimBlend.IDLE_SPEED - 0.01).Idle ~= nil)
			check.truthy(AnimBlend.weights(full, meta, Vector3.new(0, 0, -1), AnimBlend.IDLE_SPEED).Idle == nil)
			check.truthy(AnimBlend.weights(full, meta, Vector3.new(0, 0, 0), 12).Idle ~= nil)
			check.truthy(AnimBlend.weights(full, meta, Vector3.new(0, 1, 0), 12).Idle ~= nil)
		end)
		test.case(
			"the air: a jump and a land play once, a fall replaces the ground blend and ends with any other state",
			function()
				local set = { idle = "Idle", walk = "Walk", jump = "Jump", fall = "Fall", land = "Land" }
				check.equal(AnimBlend.oneShot(set, "Jumping"), "Jump")
				check.equal(AnimBlend.oneShot(set, "Landed"), "Land")
				check.truthy(AnimBlend.oneShot(set, "Freefall") == nil and AnimBlend.oneShot(set, "Running") == nil)
				check.truthy(AnimBlend.oneShot({ idle = "Idle" }, "Jumping") == nil) -- a set with no jump plays none
				check.truthy(AnimBlend.falling("Freefall") == true)
				for _, state in { "Landed", "Running", "Climbing", "Swimming", "Seated", "Jumping" } do
					check.truthy(AnimBlend.falling(state) == false)
				end
				local ground = AnimBlend.weights(set, meta, Vector3.new(0, 0, -1), 6.8)
				local air = AnimBlend.airborne(set, true, ground)
				check.truthy(air.Fall ~= nil and air.Fall.weight == 1 and air.Walk == nil)
				check.truthy(AnimBlend.airborne(set, false, ground) == ground)
				check.truthy(AnimBlend.airborne({ idle = "Idle", walk = "Walk" }, true, ground) == ground) -- no fall clip: the ground blend
				local anim = fs.readFile("src/kit/Anim.luau")
				check.truthy(
					string.find(
						anim,
						"AnimBlend.airborne(set, falling, AnimBlend.weights(set, meta, localMove, speed))",
						1,
						true
					) ~= nil
				)
				check.truthy(string.find(anim, "oneShot(AnimBlend.oneShot(set, new.Name))", 1, true) ~= nil)
			end
		)
	end)

	test.suite("the motion warp, whole", function()
		local root = {}
		for i = 0, 60 do
			table.insert(root, { 0, -i * 0.1, 0 }) -- 6 studs forward (-Z) over 1 s at 60 fps
		end
		test.case("inside the window the travel is scaled; half way through, half of it", function()
			local w = { from = 0.2, to = 0.6, scale = 2, turn = 0 }
			local _, z0 = AnimLayers.warpedRootAt(root, 60, 0.2, w)
			check.truthy(near(z0, -1.2, 1e-6)) -- before and at the window's start: the clip's own
			local _, zm = AnimLayers.warpedRootAt(root, 60, 0.4, w)
			check.truthy(near(zm, -1.2 - 1.2 * 2, 1e-6)) -- 1.2 studs of the window travelled, doubled
			local _, ze = AnimLayers.warpedRootAt(root, 60, 0.6, w)
			check.truthy(near(ze, -1.2 - 2.4 * 2, 1e-6))
		end)
		test.case("after the window the clip's own travel goes on from where the warp left it", function()
			local w = { from = 0.2, to = 0.6, scale = 2, turn = 0 }
			local _, z = AnimLayers.warpedRootAt(root, 60, 1.0, w)
			check.truthy(near(z, -1.2 - 4.8 - 2.4, 1e-6)) -- 1.2 before + 2.4 doubled + the last 2.4 as the clip has it
			local _, zb = AnimLayers.warpedRootAt(root, 60, 0.1, w)
			check.truthy(near(zb, -0.6, 1e-6)) -- before the window: untouched
		end)
		test.case("a turn bends the window's travel, and what follows keeps that heading", function()
			local w = { from = 0, to = 0.5, scale = 1, turn = math.rad(90) }
			local xe, ze, yawE = AnimLayers.warpedRootAt(root, 60, 0.5, w)
			-- 3 studs forward turned a quarter to the LEFT: all of it along -X
			check.truthy(near(xe, -3, 1e-6) and near(ze, 0, 1e-6) and near(yawE, math.rad(90)))
			local x, z = AnimLayers.warpedRootAt(root, 60, 1.0, w)
			check.truthy(near(x, -6, 1e-6) and near(z, 0, 1e-6)) -- the last 3 studs go on to the left too
			local _, _, yawM = AnimLayers.warpedRootAt(root, 60, 0.25, w)
			check.truthy(near(yawM, math.rad(45), 1e-6)) -- half way through the window: half the turn (the ease is even there)
		end)
		test.case("a window written backwards is a window with no length (it used to throw every frame)", function()
			local w = { from = 0.5, to = 0.2, scale = 1.5, turn = math.rad(20) }
			local x, z, yaw = AnimLayers.warpedRootAt(root, 60, 0.8, w)
			-- 3 studs before it as the clip has them, the 1.8 after it turned 20 degrees to the left
			check.truthy(
				near(x, -1.8 * math.sin(math.rad(20)), 1e-6) and near(z, -3 - 1.8 * math.cos(math.rad(20)), 1e-6)
			)
			check.truthy(near(yaw, math.rad(20)))
			local _, zb = AnimLayers.warpedRootAt(root, 60, 0.3, w)
			check.truthy(near(zb, -1.8, 1e-6)) -- before it: untouched
		end)
		test.case("a turn in a window that opens late starts from no turn at all", function()
			local w = { from = 0.2, to = 0.6, scale = 2, turn = math.rad(30) }
			local _, za, ya = AnimLayers.warpedRootAt(root, 60, 0.2 - 1e-6, w)
			local _, zb, yb = AnimLayers.warpedRootAt(root, 60, 0.2 + 1e-6, w)
			check.truthy(math.abs(za - zb) < 1e-4 and math.abs(ya - yb) < 1e-4 and math.abs(ya) < 1e-9) -- no jump as it opens
		end)
		test.case("a window with no length takes its whole warp at once", function()
			local w = { from = 0.5, to = 0.5, scale = 1.5, turn = math.rad(20) }
			local _, z, yaw = AnimLayers.warpedRootAt(root, 60, 0.5, w)
			check.truthy(near(z, -3, 1e-6) and near(yaw, math.rad(20)))
		end)
		test.case("a root track of one row or none stays where it is", function()
			local w = { from = 0, to = 0.5, scale = 2, turn = math.rad(30) }
			local x, z, yaw = AnimLayers.warpedRootAt({}, 60, 0.3, w)
			check.truthy(x == 0 and z == 0 and near(yaw, math.rad(30) * 0.648, 1e-3)) -- nothing to travel; the turn still eases in
			local x1, z1 = AnimLayers.warpedRootAt({ { 2, -1, 0 } }, 60, 0.3, w)
			check.truthy(near(x1, 2) and near(z1, -1))
		end)
		test.case("the warp that reaches a target: scale and turn, each inside its limits", function()
			local s, t = AnimLayers.warpFor(4, 9, math.rad(10)) -- 9 studs away, stop 3 short: 6 of travel wanted over 4
			check.truthy(near(s, 1.5) and near(t, math.rad(10)))
			local s2, t2 =
				AnimLayers.warpFor(4, 9, math.rad(-80), 1, { minScale = 0.8, maxScale = 1.2, maxTurnDeg = 20 })
			check.truthy(near(s2, 1.2) and near(t2, math.rad(-20)))
			local s3 = AnimLayers.warpFor(0, 9, 0) -- a clip that does not travel is not scaled
			check.equal(s3, 1)
			local s4 = AnimLayers.warpFor(4, 2, 0) -- a target nearer than the stop: the least travel allowed
			check.truthy(near(s4, 0.5))
		end)
	end)
end

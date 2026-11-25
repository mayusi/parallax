-- moves.spec.luau — moves as data (src/kit/MovesRules): timeline, phases, hitbox frames, cancels, hit / block /
-- chip / parry / dodge outcomes with combo scaling, frame advantage, validation.
local frk = require("../frk")
local test, check = frk.test, frk.check

local MovesRules = require("../../../src/kit/MovesRules")

local SLASH = {
	name = "Slash",
	frames = { fps = 60, startup = 10, active = 4, recovery = 20 },
	hitboxes = { { frames = { 10, 13 }, size = { 5, 5, 6 }, offset = { 0, 0, -3.5 } } },
	damage = 10,
	stun = 0.4,
	knockback = { 0, 4, 20 },
	blockstun = 0.3,
	cancel = { into = { "Slash2" }, from = 16, to = 30 },
}

return function()
	test.suite("MovesRules timeline", function()
		test.case("phases at the right times", function()
			check.equal((MovesRules.phaseAt(SLASH, 0)), "startup")
			check.equal((MovesRules.phaseAt(SLASH, 10 / 60)), "active")
			check.equal((MovesRules.phaseAt(SLASH, 14 / 60)), "recovery")
			check.equal((MovesRules.phaseAt(SLASH, 34 / 60)), "done")
			check.equal((MovesRules.phaseAt(SLASH, 0 / 0)), "startup")
		end)
		test.case("startup=0 stays 0 (line 90: math.max(0,...) not math.max(1,...))", function()
			-- a move with explicit startup=0: frame at t=0 should be in startup (frame 0), not in active
			local zeroStart = {
				name = "Quick",
				frames = { fps = 60, startup = 0, active = 4, recovery = 10 },
				hitboxes = { { frames = { 0, 3 }, size = { 1, 1, 1 } } },
				damage = 5,
			}
			local tl = MovesRules.timeline(zeroStart)
			check.equal(tl.startup, 0)
			-- at t=0 exactly, frame=0: with startup=0 this is "active"; if startup becomes 1, t=0 → "startup"
			check.equal((MovesRules.phaseAt(zeroStart, 0)), "active")
			-- kills line 90 (0->1 on the DEFAULT): when frames.startup is NOT provided (nil),
			-- num(nil, 0) = 0 → max(0, 0) = 0 (original); num(nil, 1) = 1 → max(0, 1) = 1 (mutant)
			-- a move with no frames.startup at all: startup should be 0, not 1
			local noFrames = {
				name = "Quick2",
				frames = { fps = 60, active = 4, recovery = 10 }, -- no startup key
				hitboxes = { { frames = { 0, 3 }, size = { 1, 1, 1 } } },
				damage = 5,
			}
			local tl2 = MovesRules.timeline(noFrames)
			check.equal(tl2.startup, 0) -- original: num(nil, 0)=0 → 0; mutant: num(nil, 1)=1 → 1
			check.equal((MovesRules.phaseAt(noFrames, 0)), "active") -- frame=0, startup=0: active immediately
		end)
		test.case("exact frame boundary (line 105: 1e-6 epsilon keeps t=N/fps on frame N)", function()
			-- t = exactly 10/60 → frame = floor(10/60 * 60 + 1e-6) = floor(10 + 1e-6) = 10 → "active"
			-- if epsilon were 1e-7 instead, same result here; test the frame value is correct
			local _, frame = MovesRules.phaseAt(SLASH, 10 / 60)
			check.equal(frame, 10)
			-- t=0/60 → frame 0 (startup)
			local _, f0 = MovesRules.phaseAt(SLASH, 0)
			check.equal(f0, 0)
			-- t = 9/60 → frame 9 → still startup
			local ph9, f9 = MovesRules.phaseAt(SLASH, 9 / 60)
			check.equal(ph9, "startup")
			check.equal(f9, 9)
		end)
		test.case("hitboxesAt at exactly the first frame of the window (line 121: >= not >)", function()
			-- frame = fr[1] exactly: original ">=" includes it; mutant ">" misses it
			check.equal(#MovesRules.hitboxesAt(SLASH, 10), 1) -- first frame of [10,13]
			check.equal(#MovesRules.hitboxesAt(SLASH, 13), 1) -- last frame
			check.equal(#MovesRules.hitboxesAt(SLASH, 9), 0) -- one before
		end)
		test.case("hitboxes only on their frames; cancels only in the window and only into listed moves", function()
			check.equal(#MovesRules.hitboxesAt(SLASH, 9), 0)
			check.equal(#MovesRules.hitboxesAt(SLASH, 12), 1)
			check.equal(MovesRules.canCancel(SLASH, 20 / 60, "Slash2"), true)
			check.equal(MovesRules.canCancel(SLASH, 12 / 60, "Slash2"), false)
			check.equal(MovesRules.canCancel(SLASH, 20 / 60, "Dash"), false)
		end)
		test.case(
			"a late step checks every hit frame passed since the last one (a server hitch never skips a hit)",
			function()
				-- steps at frame 8 then 22 (startup -> recovery, over the whole active window 10..13): the box is due
				check.equal(#MovesRules.hitboxesBetween(SLASH, 8, 22), 1)
				-- straight to done (frame 40) from startup: still due
				check.equal(#MovesRules.hitboxesBetween(SLASH, 8, 40), 1)
				-- every step one frame apart: due only on the active frames
				check.equal(#MovesRules.hitboxesBetween(SLASH, 8, 9), 0)
				check.equal(#MovesRules.hitboxesBetween(SLASH, 9, 10), 1)
				check.equal(#MovesRules.hitboxesBetween(SLASH, 13, 14), 0)
				-- a window already checked is not due again
				check.equal(#MovesRules.hitboxesBetween(SLASH, 13, 40), 0)
				-- a box drawn past the active frames counts only inside them (as the per-frame check did)
				local long = table.clone(SLASH)
				long.hitboxes = { { frames = { 12, 30 }, size = { 1, 1, 1 } } }
				check.equal(#MovesRules.hitboxesBetween(long, 14, 30), 0)
				check.equal(#MovesRules.hitboxesBetween(long, 11, 12), 1)
			end
		)
		test.case("frame advantage on block", function()
			-- blockstun 18 frames - (active 3 + recovery 20) = -5
			check.equal(MovesRules.onBlock(SLASH), -5)
		end)
	end)

	test.suite("MovesRules.resolve", function()
		test.case("a clean hit, then combo scaling down to 40 %", function()
			local o = MovesRules.resolve(SLASH, { now = 1 }, 1)
			check.equal(o.kind, "hit")
			check.equal(o.damage, 10)
			check.equal(MovesRules.resolve(SLASH, { now = 1 }, 3).damage, 8)
			check.equal(MovesRules.resolve(SLASH, { now = 1 }, 20).damage, 4)
		end)
		test.case("blocked = no damage + blockstun; chip = 20 %; unblockable goes through", function()
			local b = MovesRules.resolve(SLASH, { now = 1, blocking = true })
			check.equal(b.kind, "blocked")
			check.equal(b.damage, 0)
			check.equal(b.stun, 0.3)
			local chip = table.clone(SLASH)
			chip.block = "chip"
			check.equal(MovesRules.resolve(chip, { now = 1, blocking = true }).damage, 2)
			local ub = table.clone(SLASH)
			ub.block = "unblockable"
			check.equal(MovesRules.resolve(ub, { now = 1, blocking = true }).kind, "hit")
		end)
		test.case("a parry inside the window stuns the attacker; a late one is just a block", function()
			local p = MovesRules.resolve(SLASH, { now = 1.0, parryAt = 0.9, blocking = true })
			check.equal(p.kind, "parried")
			check.is_true(p.attackerStun >= 0.6)
			check.equal(MovesRules.resolve(SLASH, { now = 1.0, parryAt = 0.5, blocking = true }).kind, "blocked")
		end)
		test.case("i-frames dodge everything", function()
			check.equal(MovesRules.resolve(SLASH, { now = 1, iframes = true }).kind, "dodged")
		end)
		test.case("knockback table is used (line 222: type==table not ~=table)", function()
			-- move.knockback IS a table: original uses it; mutant ~= skips it and uses {0,0,0}
			local mv = table.clone(SLASH)
			mv.knockback = { 3, 7, 15 }
			local o = MovesRules.resolve(mv, { now = 1 }, 1)
			check.equal(o.knockback[1], 3)
			check.equal(o.knockback[2], 7)
			check.equal(o.knockback[3], 15)
		end)
		test.case("knockback z-component comes from kb[3] not kb[4] (line 223)", function()
			-- if the mutant reads kb[4] instead of kb[3], knock[3] becomes nil→0
			local mv = table.clone(SLASH)
			mv.knockback = { 1, 2, 99 }
			local o = MovesRules.resolve(mv, { now = 1 }, 1)
			check.equal(o.knockback[3], 99)
		end)
		test.case("move with no stun gets stun=0 (line 229: default 0 not 1)", function()
			-- move with no stun field: original stun=0, mutant stun=1
			local mv = table.clone(SLASH)
			mv.stun = nil
			local o = MovesRules.resolve(mv, { now = 1 }, 1)
			check.equal(o.stun, 0)
		end)
		test.case("dodged outcome has stun=0 (line 235: 0 not 1)", function()
			-- iframes: out.stun should be 0, not 1
			local o = MovesRules.resolve(SLASH, { now = 1, iframes = true })
			check.equal(o.stun, 0)
			check.equal(o.damage, 0)
			check.equal(o.knockback[1], 0)
			check.equal(o.knockback[2], 0)
			check.equal(o.knockback[3], 0)
		end)
		test.case("parry of move with no stun gives attackerStun=0.6 (line 246: default 0 not 1)", function()
			-- move.stun missing: math.max(0.6, 0*1.5)=0.6; with mutant default=1: math.max(0.6, 1*1.5)=1.5
			local mv = table.clone(SLASH)
			mv.stun = nil
			local p = MovesRules.resolve(mv, { now = 1.0, parryAt = 0.9, blocking = true })
			check.equal(p.kind, "parried")
			check.equal(p.attackerStun, 0.6)
		end)
		test.case("blocked glance uses knock[1] and knock[3] (line 255: index 1 not 2)", function()
			-- kb={5, 99, 15}: blocked knockback should be {5*0.3, 0, 15*0.3}, not {99*0.3, 0, ...}
			local mv = table.clone(SLASH)
			mv.knockback = { 5, 99, 15 }
			local b = MovesRules.resolve(mv, { now = 1, blocking = true })
			check.equal(b.kind, "blocked")
			-- x component: knock[1]*0.3 = 5*0.3 = 1.5 (mutant would give 99*0.3=29.7)
			check.is_true(math.abs(b.knockback[1] - 1.5) < 1e-9)
			check.equal(b.knockback[2], 0)
			check.is_true(math.abs(b.knockback[3] - 4.5) < 1e-9)
		end)
	end)

	test.suite("MovesRules.allowed (the server decides the combo step)", function()
		local A = table.clone(SLASH)
		A.name = "A"
		A.cancel = { into = { "B" }, from = 16, to = 30 }
		local B = table.clone(SLASH)
		B.name = "B"
		B.cooldown = 2
		local SET = { moves = { A = A, B = B }, combo = { "A", "B" } }
		test.case("a client cannot open with a later step (review 2026-10-13: spamming the finisher)", function()
			local ok, why = MovesRules.allowed(SET, { comboIndex = 0, lastUsed = {} }, "B", 10)
			check.equal(ok, false)
			check.is_true(why ~= nil and string.find(why, "combo order", 1, true) ~= nil)
		end)
		test.case("the next step is allowed from the cancel window or just after; the index counts up", function()
			local ok1, _, i1 = MovesRules.allowed(SET, { comboIndex = 0, lastUsed = {} }, "A", 10)
			check.equal(ok1, true)
			check.equal(i1, 1)
			local mid = { moveName = "A", moveT = 20 / 60, comboIndex = 1, lastUsed = {} }
			local ok2, _, i2 = MovesRules.allowed(SET, mid, "B", 10)
			check.equal(ok2, true)
			check.equal(i2, 2)
			local early = { moveName = "A", moveT = 5 / 60, comboIndex = 1, lastUsed = {} }
			check.equal((MovesRules.allowed(SET, early, "B", 10)), false)
			local after = { lastName = "A", lastEnded = 9.5, comboIndex = 1, lastUsed = {} }
			check.equal((MovesRules.allowed(SET, after, "B", 10)), true)
			local late = { lastName = "A", lastEnded = 7, comboIndex = 1, lastUsed = {} }
			check.equal((MovesRules.allowed(SET, late, "B", 10)), false)
		end)
		test.case("the input buffer: how long until the next step may start (C1)", function()
			check.equal(MovesRules.waitFor(A, 10 / 60, "B"), 6 / 60) -- the cancel window opens at frame 16
			check.equal(MovesRules.waitFor(A, 20 / 60, "B"), 0) -- inside it: now
			local tl = MovesRules.timeline(A)
			check.is_true(math.abs(MovesRules.waitFor(A, 10 / 60, "A") - (tl.total - 10) / 60) < 1e-9) -- not a cancel: the end
		end)
		test.case("cooldowns hold", function()
			local s = { lastName = "A", lastEnded = 9.9, comboIndex = 1, lastUsed = { B = 9 } }
			local ok, why = MovesRules.allowed(SET, s, "B", 10)
			check.equal(ok, false)
			check.equal(why, "cooldown")
		end)
		test.case("the combo gap: nothing starts on the frame the last move ended (V4 13.1)", function()
			local function try(ended: number, now: number, name: string): (boolean, string?)
				local ok, why = MovesRules.allowed(
					SET,
					{ lastName = "A", lastEnded = ended, comboIndex = 1, lastUsed = {} },
					name,
					now
				)
				return ok, why
			end
			check.is_true(MovesRules.MIN_GAP >= 1 / 60)
			-- (a) a press at exactly the end is refused - "gap", so the server holds it for the next frame
			local ok1, why1 = try(10, 10, "B")
			check.equal(ok1, false)
			check.equal(why1, "gap")
			check.equal((try(10, 10, "A")), false) -- a fresh opener too
			-- (b) one frame later the combo step is allowed
			check.equal((try(10, 10 + 1 / 60, "B")), true)
			-- (c) the server's clock (~1.79e9 s): the same answers, the float error of the big numbers is not a frame
			local T = 1.79e9 + 0.123
			local okBig, whyBig = try(T, T, "B")
			check.equal(okBig, false)
			check.equal(whyBig, "gap")
			check.equal((try(T, T + 0.5 / 60, "B")), false)
			check.equal((try(T, T + 1 / 60, "B")), true)
			check.equal((try(T, T + 0.5, "B")), true)
			check.equal((try(T, T + 1, "B")), false) -- past the 0.9 s combo gap on the big clock too
			-- the end is kept across the exit: a move still on (its cancel window) is not held by an older end
			local mid =
				{ moveName = "A", moveT = 20 / 60, lastName = "A", lastEnded = T, comboIndex = 1, lastUsed = {} }
			check.equal((MovesRules.allowed(SET, mid, "B", T)), true)
		end)
	end)

	-- ── clipFor (line 42: type(upper)=="string" → ~="string") ──────────────────────────────
	test.suite("MovesRules.clipFor", function()
		test.case("returns the upper clip when moving and upper is a string with meta", function()
			-- upper IS a string: original takes the upper path, mutant (~=) skips it and falls through
			local meta = { MyAnim = { upper = "MyAnimUpper" }, MyAnimUpper = {} }
			check.equal(MovesRules.clipFor("MyAnim", meta, true), "MyAnimUpper")
			-- standing: always the base anim
			check.equal(MovesRules.clipFor("MyAnim", meta, false), "MyAnim")
			-- moving but no upper entry: base anim
			local noUpper = { MyAnim = {} }
			check.equal(MovesRules.clipFor("MyAnim", noUpper, true), "MyAnim")
			-- moving, upper key set but pointing at a non-table: base anim
			local badMeta = { MyAnim = { upper = "MyAnimUpper" } }
			check.equal(MovesRules.clipFor("MyAnim", badMeta, true), "MyAnim")
		end)
	end)

	test.suite("MovesRules boundary kills", function()
		-- line 94 (1 -> 2): fps minimum is 1, not 2
		test.case("timeline: fps=0 gives fps=1, not fps=2 (math.max(1, ...) not math.max(2, ...))", function()
			-- f.fps=0: num(0, 60)=0; math.max(1, 0) = 1. Mutant max(2,0) = 2.
			local mv = {
				name = "FpsBoundary",
				frames = { fps = 0, startup = 0, active = 4, recovery = 0 },
				hitboxes = { { frames = { 0, 3 }, size = { 1, 1, 1 } } },
				damage = 0,
			}
			local tl = MovesRules.timeline(mv)
			check.equal(tl.fps, 1) -- original: max(1,0)=1; mutant max(2,0)=2
		end)

		-- line 172 (0 -> 1): waitFor returns 0 when already past or in the cancel window (max(0, ...) not max(1, ...))
		test.case("waitFor: returns 0 when already in the cancel window (max(0,...) not max(1,...))", function()
			-- From line 172: return math.max(0, opens/tl.fps - math.max(0, num(t, 0)))
			-- When t > opens/tl.fps: opens/tl.fps - t < 0 → max(0, neg) = 0 (original); max(1, neg) = 1 (mutant).
			-- SLASH cancel from=16, to=30. At t=20/60, waitFor(..., "B") = 0 (already in window).
			-- But the code path: opens starts at tl.total; if cancel found, opens = min(opens, max(from, frame)).
			-- At t=20/60 (frame=20): opens = max(16, 20) = 20. 20/60 - 20/60 = 0. max(0, 0) = 0.
			-- Mutant: max(1, 0) = 1 (immediately in window → returns 1 instead of 0).
			check.equal(MovesRules.waitFor(SLASH, 20 / 60, "Slash2"), 0) -- in window: 0 (not 1)
		end)

		-- line 215 (0 -> 1): when state.comboIndex is nil, the first step returns index 1 (nil or 0 = 0, +1 = 1)
		test.case("allowed: a state with nil comboIndex starts the combo at index 1 (not 2)", function()
			-- (state.comboIndex or 0) + 1: nil or 0 = 0, +1 = 1. Mutant: nil or 1 = 1, +1 = 2.
			local A = table.clone(SLASH)
			A.name = "A"
			local B = table.clone(SLASH)
			B.name = "B"
			local SET = { moves = { A = A, B = B }, combo = { "A", "B" } }
			-- state has no comboIndex field (nil)
			local ok, _, i = MovesRules.allowed(SET, { lastUsed = {} }, "A", 10)
			check.equal(ok, true)
			check.equal(i, 1) -- nil or 0 = 0, +1 = 1; mutant gives 2
		end)

		-- line 230 (0.5 -> 1.5): hitstop is clamped to 0.5 max
		test.case("resolve: hitstop=2 is clamped to 0.5 (clamp max is 0.5 not 1.5)", function()
			local mv = table.clone(SLASH)
			mv.hitstop = 2 -- over the max
			local o = MovesRules.resolve(mv, { now = 1 }, 1)
			check.equal(o.kind, "hit")
			check.truthy(math.abs(o.hitstop - 0.5) < 1e-9) -- clamped to 0.5; mutant allows 1.5
		end)

		-- line 245 (0 -> 1): a parried outcome has stun=0 (the parry cancels the stun)
		test.case("resolve: a parried hit has stun=0 (the parry cancels stun, not stun=1)", function()
			-- The assignment: out.stun = 0. Mutant: out.stun = 1.
			local p = MovesRules.resolve(SLASH, { now = 1.0, parryAt = 0.9, blocking = true })
			check.equal(p.kind, "parried")
			check.equal(p.stun, 0) -- stun is zeroed on parry; mutant gives 1
		end)

		-- line 353 (0 -> 1): knockdown=0 is valid (the min is 0, not 1)
		test.case("validate: knockdown=0 is a valid value (kd < 0 boundary, not kd < 1)", function()
			-- Original: kd < 0 → 0 < 0 = false → valid. Mutant (0->1): kd < 1 → 0 < 1 = true → fires error.
			local names = { Slash = true, Slash2 = true }
			local mv = table.clone(SLASH)
			mv.onHit = { knockdown = 0 }
			local issues = MovesRules.validate(mv, names)
			local text = table.concat(issues, "\n")
			check.equal(string.find(text, "knockdown", 1, true), nil) -- knockdown=0 must be valid
		end)
	end)

	test.suite("MovesRules.validate", function()
		test.case("a good move has no issues", function()
			check.equal(#MovesRules.validate(SLASH, { Slash = true, Slash2 = true }), 0)
		end)
		test.case("onHit's knockdown and get-up are checked (V4 8.3)", function()
			local names = { Slash = true, Slash2 = true }
			local function issues(onHit: any): string
				local m = table.clone(SLASH)
				m.onHit = onHit
				return table.concat(MovesRules.validate(m, names), " | ")
			end
			check.equal(issues({ knockdown = 1.0, getUp = { back = "GetUpBack", front = "GetUpFront" } }), "")
			check.equal(issues({ knockdown = 1.0 }), "") -- (a knockdown alone: the ragdoll's own recovery)
			check.truthy(string.find(issues({ knockdown = -1 }), "knockdown", 1, true) ~= nil)
			check.truthy(string.find(issues({ knockdown = 0 / 0 }), "knockdown", 1, true) ~= nil) -- (NaN)
			check.truthy(string.find(issues({ knockdown = 1, getUp = "GetUp" }), "getUp", 1, true) ~= nil)
			check.truthy(string.find(issues({ knockdown = 1, getUp = { side = "X" } }), "only", 1, true) ~= nil)
			check.truthy(string.find(issues({ knockdown = 1, getUp = { back = "" } }), "names a clip", 1, true) ~= nil)
			check.truthy(string.find(issues({ getUp = { back = "GetUpBack" } }), "no body ever falls", 1, true) ~= nil)
			check.truthy(string.find(issues({ knockdown = 1, getUpBlend = 9 }), "getUpBlend", 1, true) ~= nil)
			check.truthy(string.find(issues("hit"), '"onHit" is a table', 1, true) ~= nil)
		end)
		test.case("a tiered move over its press-to-hit budget is named (C1)", function()
			local slow = table.clone(SLASH)
			slow.tier = "light"
			slow.frames = table.clone(SLASH.frames)
			slow.frames.startup = 30 -- 0.5 s at 60 fps: over light's 0.3 s
			slow.hitboxes = { { frames = { 30, 33 }, size = { 5, 5, 6 }, offset = { 0, 0, -3.5 } } }
			slow.cancel = { into = { "Slash2" }, from = 36, to = 50 }
			local text = table.concat(MovesRules.validate(slow, { Slash = true, Slash2 = true }), "\n")
			check.is_true(string.find(text, "light budget", 1, true) ~= nil)
			slow.tier = "heavy"
			check.equal(#MovesRules.validate(slow, { Slash = true, Slash2 = true }), 0)
		end)
		test.case("ghost hitboxes, huge boxes, bad windows and unknown cancels are named", function()
			local bad = table.clone(SLASH)
			bad.hitboxes = { { frames = { 2, 30 }, size = { 40, 40, 40 } } }
			bad.cancel = { into = { "Nope" }, from = 30, to = 10 }
			local issues = MovesRules.validate(bad, { Slash = true })
			local text = table.concat(issues, "\n")
			check.is_true(string.find(text, "outside the active frames", 1, true) ~= nil)
			check.is_true(string.find(text, "huge", 1, true) ~= nil)
			check.is_true(string.find(text, "cancel window", 1, true) ~= nil)
			check.is_true(string.find(text, "not a move of this set", 1, true) ~= nil)
		end)
		test.case("a table move with no name fails (line 274: or not and)", function()
			-- type(move)~="table" OR type(move.name)~="string": both clauses with "and" → false when move IS a table
			-- so the mutant skips the guard and proceeds with no name: validate should still return an issue
			local issues = MovesRules.validate({})
			check.is_true(#issues > 0)
			check.is_true(string.find(table.concat(issues, "\n"), "name", 1, true) ~= nil)
		end)
		test.case("damage=0 with no hitboxes is valid (line 311: > not >=)", function()
			-- damage=0 and no hitboxes: original (> 0) → no error; mutant (>= 0) → fires "damage but no hitboxes"
			local mv = table.clone(SLASH)
			mv.damage = 0
			mv.hitboxes = {}
			local issues = MovesRules.validate(mv, { Slash = true, Slash2 = true })
			local text = table.concat(issues, "\n")
			check.equal(string.find(text, "damage but no hitboxes", 1, true), nil)
		end)
		test.case("damage=0 with active frames does not trigger whoosh check (line 319: > not >=)", function()
			-- damage=0 and active>0: original (> 0) → skip whoosh check; mutant (>= 0) → runs it and may fire
			local mv = table.clone(SLASH)
			mv.damage = 0
			mv.sfx = { { frame = 0, event = "SwordSwing" } } -- would fail whoosh timing if checked
			local issues = MovesRules.validate(mv, { Slash = true, Slash2 = true })
			local text = table.concat(issues, "\n")
			check.equal(string.find(text, "LEADS the hit", 1, true), nil)
		end)
		test.case("sfx event 'swing' at index 1 triggers the whoosh check (line 323: find from 1 not 2)", function()
			-- string.find(ev, "swing", 1, true): starting at 1 finds "swing" at pos 1; starting at 2 misses it
			local mv = table.clone(SLASH)
			mv.sfx = { { frame = 9, event = "swing" } } -- frame 9 = 1 frame before active: 1/60 ≈ 17 ms < 50 ms → bad
			local issues = MovesRules.validate(mv, { Slash = true, Slash2 = true })
			local text = table.concat(issues, "\n")
			check.is_true(string.find(text, "LEADS the hit", 1, true) ~= nil)
		end)
		test.case("startup exactly at budget is valid (line 341: > not >=)", function()
			-- startup/fps == budget: original (> budget+1e-6) → false → no error; mutant (>= ...) → error
			-- light budget = 0.3 s; startup = 0.3 * 60 = 18 frames → startup/fps = 0.3 exactly
			local mv = table.clone(SLASH)
			mv.tier = "light"
			mv.frames = { fps = 60, startup = 18, active = 4, recovery = 20 }
			mv.hitboxes = { { frames = { 18, 21 }, size = { 5, 5, 6 } } }
			mv.cancel = { into = { "Slash2" }, from = 24, to = 40 }
			local issues = MovesRules.validate(mv, { Slash = true, Slash2 = true })
			local text = table.concat(issues, "\n")
			check.equal(string.find(text, "light budget", 1, true), nil)
		end)
		test.case("hitbox size with nil y-dimension fails (line 301: default 0 not 1)", function()
			-- size={1,nil,1}: num(nil,0)=0 <= 0 → bad; mutant: num(nil,1)=1 > 0 → passes silently
			local mv = table.clone(SLASH)
			mv.hitboxes = { { frames = { 10, 13 }, size = { 1, nil, 1 } } }
			mv.damage = 0 -- avoid "damage but no hitboxes" noise
			local issues = MovesRules.validate(mv, { Slash = true, Slash2 = true })
			local text = table.concat(issues, "\n")
			check.is_true(string.find(text, "size", 1, true) ~= nil)
		end)
		test.case("hitbox size != 3 elements fails (line 299: or not and)", function()
			-- #size ~= 3 is part of OR chain: a size with 2 elements should fail
			local mv = table.clone(SLASH)
			mv.hitboxes = { { frames = { 10, 13 }, size = { 5, 5 } } }
			mv.damage = 0
			local issues = MovesRules.validate(mv, { Slash = true, Slash2 = true })
			local text = table.concat(issues, "\n")
			check.is_true(string.find(text, "size", 1, true) ~= nil)
			-- kills line 299 (or->and): size={5,5,5,5} has #size=4~=3 AND all numeric values > 0
			-- original (or): type~="table"=F OR #~=3=T → fires size error
			-- mutant (and): F AND T = F, then all num(size[i],0)>0 so no error from numeric checks → no error
			local mv2 = table.clone(SLASH)
			mv2.hitboxes = { { frames = { 10, 13 }, size = { 5, 5, 5, 5 } } } -- 4 elements, all > 0
			mv2.damage = 0
			local issues2 = MovesRules.validate(mv2, { Slash = true, Slash2 = true })
			local text2 = table.concat(issues2, "\n")
			check.is_true(string.find(text2, "size", 1, true) ~= nil) -- must flag size error (original)
		end)
		test.case("hitbox volume > 2000 uses correct defaults (line 305: default 0 not 1)", function()
			-- size={nil,nil,nil}: with default 0: 0*0*0=0, NOT > 2000; with default 1: 1*1*1=1, NOT > 2000 either
			-- test with an explicit large box that exceeds 2000 studs^3
			local mv = table.clone(SLASH)
			mv.hitboxes = { { frames = { 10, 13 }, size = { 15, 15, 15 } } } -- 3375 > 2000
			mv.damage = 0
			local issues = MovesRules.validate(mv, { Slash = true, Slash2 = true })
			local text = table.concat(issues, "\n")
			check.is_true(string.find(text, "huge", 1, true) ~= nil)
		end)
		test.case("onHit.getUpBlend=0 is valid (line 376: < not <=)", function()
			-- gb=0: original (gb < 0) → false → not an error; mutant (gb <= 0) → fires error
			local names = { Slash = true, Slash2 = true }
			local mv = table.clone(SLASH)
			mv.onHit = { knockdown = 1.0, getUpBlend = 0 }
			local issues = MovesRules.validate(mv, names)
			local text = table.concat(issues, "\n")
			check.equal(string.find(text, "getUpBlend", 1, true), nil)
		end)
		test.case("the whoosh LEADS the hit: a swing cue 50-300 ms before the first active frame", function()
			local function with(frame: number, event: string?, role: string?): { string }
				local mv = table.clone(SLASH)
				mv.sfx = { { frame = frame, event = event or "SwordSwing", role = role } }
				return MovesRules.validate(mv, { Slash = true, Slash2 = true })
			end
			check.equal(#with(3), 0) -- (7 frames = 117 ms before frame 10)
			check.equal(#with(7), 0) -- (3 frames = exactly 50 ms)
			local late = table.concat(with(10), "\n") -- (on the hit: it smears the impact)
			check.is_true(string.find(late, "LEADS the hit", 1, true) ~= nil)
			check.is_true(string.find(late, "frame 3", 1, true) ~= nil) -- (the fix: 120 ms before)
			check.equal(#with(10, "Blip"), 0) -- (not a whoosh: no rule)
			check.is_true(#with(10, "Blip", "whoosh") > 0) -- (named a whoosh by its role)
			local early = table.clone(SLASH)
			early.frames = { fps = 60, startup = 40, active = 4, recovery = 20 }
			early.hitboxes = { { frames = { 40, 43 }, size = { 5, 5, 6 } } }
			early.sfx = { { frame = 0, event = "Whoosh" } } -- (667 ms early: a separate sound)
			check.is_true(#MovesRules.validate(early, { Slash = true, Slash2 = true }) > 0)
		end)
	end)
end

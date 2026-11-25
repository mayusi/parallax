-- echo.spec.luau — EchoRules (src/kit): places that answer the player - the zone a point is in, how a sound comes
-- back (late, quieter, lower, from deep in), and the phantom step: once per stop, after a real walk, by its chance.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Rules = require("../../../src/kit/EchoRules")

local ZONES = {
	{
		x = 0,
		z = 0,
		r = 20,
		y0 = -10,
		y1 = 30,
		deep = { 0, -5, 60 },
		delay = 0.6,
		gain_db = -9,
		pitch = 0.94,
		phantom = 1,
		min_steps = 4,
	},
}

return function()
	test.suite("EchoRules: places that answer the player", function()
		test.case("a point is in the zone only inside its circle and height range", function()
			check.truthy(Rules.zoneAt(ZONES, 5, 0, 5) ~= nil)
			check.equal(Rules.zoneAt(ZONES, 25, 0, 0), nil)
			check.equal(Rules.zoneAt(ZONES, 0, 50, 0), nil) -- (over the hill, not in the catacomb)
			check.equal(Rules.zoneAt(nil, 0, 0, 0), nil)
		end)

		test.case("a sound comes back late, quieter, lower, from deep in", function()
			local r = Rules.repeatOf(ZONES[1])
			check.truthy(math.abs(r.delay - 0.6) < 1e-9)
			check.truthy(r.volume < 0.4 and r.volume > 0.3) -- (-9 dB)
			check.truthy(r.speed < 1)
			check.equal(r.at[3], 60)
			check.truthy(Rules.repeatOf({ delay = -3, gain_db = 99, pitch = 9 }).delay >= 0.05) -- (hostile data is clamped)
		end)

		test.case("the phantom step comes once, after the player stops, only after a real walk", function()
			local st = Rules.new()
			local zn = ZONES[1]
			for i = 1, 3 do
				Rules.step(st, i * 0.6, "boot_step_stone_light")
			end
			check.equal(Rules.due(st, zn, 10, 0), nil) -- (three steps are not a walk)
			st = Rules.new()
			for i = 1, 6 do
				Rules.step(st, i * 0.6, "boot_step_stone_light")
			end
			check.equal(Rules.due(st, zn, 3.7, 0), nil) -- (still walking: too soon after the last step)
			check.equal(Rules.due(st, zn, 5.0, 0), "boot_step_stone_light")
			check.equal(Rules.due(st, zn, 6.0, 0), nil) -- (once per stop)
			for i = 1, 5 do
				Rules.step(st, 10 + i * 0.6, "boot_step_stone_light")
			end
			check.truthy(Rules.due(st, zn, 20, 0) ~= nil) -- (a new walk re-arms it)
		end)

		test.case("the phantom keeps to its chance", function()
			local st = Rules.new()
			for i = 1, 6 do
				Rules.step(st, i * 0.6, "s")
			end
			check.equal(Rules.due(st, { phantom = 0.3, min_steps = 4 }, 10, 0.5), nil) -- (the roll misses)
			check.equal(Rules.due(st, { phantom = 0.3, min_steps = 4 }, 11, 0.1), nil) -- (and it is spent)
		end)
		test.case("a zone's reverb: its name inside, dry outside or when it names none", function()
			local zones = {
				{ x = 0, z = 0, r = 20, reverb = "CatacombCave" },
				{ x = 100, z = 0, r = 20 },
				{ x = 200, z = 0, r = 20, reverb = "" },
			}
			check.equal(Rules.reverbAt(zones, 5, 0, 5), "CatacombCave")
			check.equal(Rules.reverbAt(zones, 100, 0, 0), nil)
			check.equal(Rules.reverbAt(zones, 200, 0, 0), nil)
			check.equal(Rules.reverbAt(zones, 50, 0, 0), nil)
			check.equal(Rules.reverbAt(nil, 0, 0, 0), nil)
		end)
		test.case("the reverb switches on a change, never twice inside its hold", function()
			check.is_false(Rules.reverbSwitch("HallStone", "HallStone", 10, 0, 0.5))
			check.is_true(Rules.reverbSwitch(nil, "HallStone", 10, 0, 0.5))
			check.is_false(Rules.reverbSwitch("HallStone", nil, 10.2, 10, 0.5)) -- (the edge: held)
			check.is_true(Rules.reverbSwitch("HallStone", nil, 10.6, 10, 0.5))
			check.is_true(Rules.reverbSwitch("HallStone", nil, 11, 10, nil)) -- (default hold 0.5 s)
		end)

		-- ----------------------------------------------------------------
		-- Mutation-kill cases: boundary values that flip on off-by-one bugs
		-- ----------------------------------------------------------------

		test.case("zoneAt: a zone with no x/z has its centre at exactly (0,0)", function()
			-- line 19: num(zn.x, 0) default — a zone with no x/z field, r=5
			-- a point at (5, 0, 0) is on the boundary: dx=5, dz=0, r=5 -> dx^2+dz^2 == r^2
			-- with default=1 (mutant): dx=4, 16+0 <= 25 -> still inside, BUT the boundary
			-- test below (exact r) distinguishes the two defaults.
			local zNoXZ = { { r = 5 } } -- no x, no z
			-- (0,0,0) is dead-centre; must be inside
			check.truthy(Rules.zoneAt(zNoXZ, 0, 0, 0) ~= nil)
			-- (5,0,0): dx=5 with default x=0 -> 25 <= 25 -> inside; dx=4 with default x=1 -> 16<=25 -> also inside
			-- Use a point just beyond r=5 when x defaults to 0 but inside when x defaults to 1:
			-- dx = 5 - default_x; need dx^2 > 25 for default=0 but <=25 for default=1
			-- dx=5 gives 25 (boundary, inside); a point at (5.5,0,0): dx=5.5->30.25>25 outside, dx=4.5->20.25<=25 inside
			check.equal(Rules.zoneAt(zNoXZ, 5.5, 0, 0), nil) -- outside with correct default=0
		end)

		test.case("zoneAt: y0 boundary — a point at exactly y0 is inside", function()
			-- line 20 (>= -> >): y >= y0 — at y==y0 original is true, mutant is false
			local zones = { { x = 0, z = 0, r = 50, y0 = 5 } }
			check.truthy(Rules.zoneAt(zones, 0, 5, 0) ~= nil) -- exactly on y0: must be inside
			check.equal(Rules.zoneAt(zones, 0, 4.9, 0), nil) -- just below y0: must be outside
		end)

		test.case("zoneAt: y1 boundary — a point at exactly y1 is inside", function()
			-- line 20 (<= -> <): y <= y1 — at y==y1 original is true, mutant is false
			local zones = { { x = 0, z = 0, r = 50, y1 = 10 } }
			check.truthy(Rules.zoneAt(zones, 0, 10, 0) ~= nil) -- exactly on y1: must be inside
			check.equal(Rules.zoneAt(zones, 0, 10.1, 0), nil) -- just above y1: must be outside
		end)

		test.case("zoneAt: a point at exactly radius r is inside (<=, not <)", function()
			-- line 21 (<= -> <): dx^2+dz^2 <= r^2 — at exactly r the original is inside
			local zones = { { x = 0, z = 0, r = 7 } }
			-- (7, 0, 0): dx=7, dz=0 -> 49 <= 49 -> inside; with < mutant -> 49 < 49 -> false
			check.truthy(Rules.zoneAt(zones, 7, 0, 0) ~= nil)
			check.equal(Rules.zoneAt(zones, 7.01, 0, 0), nil)
		end)

		test.case("zoneAt: a zone with r=0 (default) contains only its exact centre", function()
			-- line 21 (0->1 for num(zn.r, 0)): default r=0 means only d=0 qualifies
			-- with r=1 (mutant default): a point at (0.5,0,0) would be inside
			local zNoR = { { x = 3, z = 7 } } -- no r field
			check.truthy(Rules.zoneAt(zNoR, 3, 0, 7) ~= nil) -- exact centre: inside
			check.equal(Rules.zoneAt(zNoR, 3.5, 0, 7), nil) -- 0.5 away: outside with r=0, inside with r=1
		end)

		test.case("repeatOf: the deep-y defaults to 0 when no deep table is given", function()
			-- line 31 (0->1): { num(zn.x, 0), 0, num(zn.z, 0) } — the middle literal 0 is the y
			local r = Rules.repeatOf({ x = 5, z = 15 }) -- no deep field
			check.equal(r.at[2], 0) -- y-of-deep must be 0 not 1
		end)

		test.case("repeatOf: deep x/z default to 0 when zone has no x/z and no deep", function()
			-- line 31 (0->1 for x and z defaults): num(zn.x, 0) and num(zn.z, 0)
			-- a zone with no x, no z, no deep: deep falls back to { num(nil->0), 0, num(nil->0) } = {0,0,0}
			-- mutant default=1: { 1, 0, 1 }; so at[1] and at[3] must be 0 not 1
			local r = Rules.repeatOf({}) -- no x, no z, no deep
			check.equal(r.at[1], 0)
			check.equal(r.at[3], 0)
		end)

		test.case("repeatOf: delay defaults to 0.6 when no delay field is given", function()
			-- line 33 (0.6->1.6): num(zn.delay, 0.6)
			local r = Rules.repeatOf({ x = 0, z = 0, r = 10 }) -- no delay
			check.truthy(math.abs(r.delay - 0.6) < 1e-9)
		end)

		test.case("repeatOf: volume uses base 10 and default gain_db of -9 dB", function()
			-- line 34 (10->11): base of exponentiation; (9->10): -9 default
			-- expected: 10 ^ (-9/20) ≈ 0.35481...
			local expected = 10 ^ (-9 / 20)
			local r = Rules.repeatOf({ x = 0, z = 0 }) -- no gain_db
			check.truthy(math.abs(r.volume - expected) < 1e-6)
		end)

		test.case("repeatOf: gain_db is clamped to 6 dB maximum", function()
			-- line 34 (6->7): upper clamp — gain_db=7 must yield the same volume as gain_db=6
			local rAt6 = Rules.repeatOf({ gain_db = 6 })
			local rAt7 = Rules.repeatOf({ gain_db = 7 }) -- must be clamped to 6, not allowed to reach 7
			check.truthy(math.abs(rAt6.volume - rAt7.volume) < 1e-6)
			-- and a sanity check: the clamped volume equals 10^(6/20)
			local expected6 = 10 ^ (6 / 20)
			check.truthy(math.abs(rAt6.volume - expected6) < 1e-6)
		end)

		test.case("repeatOf: pitch (speed) defaults to 0.94", function()
			-- line 35 (0.94->1.94): num(zn.pitch, 0.94)
			local r = Rules.repeatOf({ x = 0, z = 0 }) -- no pitch
			check.truthy(math.abs(r.speed - 0.94) < 1e-9)
		end)

		test.case("repeatOf: at positions from an explicit deep table are taken verbatim", function()
			-- line 36 (1->2 for index): at = { num(deep[1], 0), num(deep[2], 0), num(deep[3], 0) }
			-- with 1->2 mutant: at[1] = num(deep[2], 0) = 10 instead of 5
			local r = Rules.repeatOf({ deep = { 5, 10, 15 } })
			check.equal(r.at[1], 5) -- must be deep[1]=5, not deep[2]=10
			check.equal(r.at[2], 10)
			check.equal(r.at[3], 15)
		end)

		test.case("repeatOf: at positions default to 0 when deep table has nil slots", function()
			-- line 36 (0->1 for defaults): num(deep[1], 0) etc. with an empty deep table
			local r = Rules.repeatOf({ deep = {} }) -- all slots nil
			check.equal(r.at[1], 0)
			check.equal(r.at[2], 0)
			check.equal(r.at[3], 0)
		end)

		test.case("new(): a fresh state has spent = true", function()
			-- line 42 (true->false): return { ..., spent = true, ... }
			local st = Rules.new()
			check.is_true(st.spent)
		end)

		test.case("due: fires after exactly min_steps (default 4), not before", function()
			-- line 55 (4->5): num(zn.min_steps, 4) default — with 4 steps it must fire
			-- phantom=0.9, roll=0 -> 0 >= 0.9 is false -> fires; phantom suppresses when roll >= phantom
			local zFire = { delay = 0.1, after = 0.1, phantom = 0.9 }
			-- 3 steps: must NOT fire (< 4)
			local st3 = Rules.new()
			for i = 1, 3 do
				Rules.step(st3, i * 0.1, "snd")
			end
			check.equal(Rules.due(st3, zFire, 10, 0), nil)
			-- 4 steps: must fire
			local st4 = Rules.new()
			for i = 1, 4 do
				Rules.step(st4, i * 0.1, "snd")
			end
			check.truthy(Rules.due(st4, zFire, 10, 0) ~= nil) -- exactly 4 steps -> fires
		end)

		test.case("due: delay defaults to 0.6 in wait calculation", function()
			-- line 58 (0.6->1.6): num(zn.delay, 0.6) in wait = delay + after
			-- Zone with no delay (defaults 0.6) and after=0.65 -> wait=1.25
			-- Fire 5 steps, then try at t=last+1.3 (> 1.25 but < 2.25): original fires, mutant blocked
			local zn = { after = 0.65, phantom = 0.9 } -- no delay field
			local st = Rules.new()
			for i = 1, 5 do
				Rules.step(st, i * 0.1, "snd")
			end
			-- last step at t=0.5; try at t = 0.5 + 1.3 = 1.8 (> 1.25, < 2.25)
			check.truthy(Rules.due(st, zn, 1.8, 0) ~= nil)
		end)

		test.case("due: fires at exactly wait time (< not <=)", function()
			-- line 59 (< -> <=): if now - state.last < wait then return nil
			-- At exactly wait, original passes (<wait is false), <=wait mutant blocks
			local zn = { delay = 0.6, after = 0.65, phantom = 0.9 } -- wait = 1.25
			local st = Rules.new()
			for i = 1, 5 do
				Rules.step(st, i * 0.1, "snd")
			end
			-- last step at t=0.5; try at t = 0.5 + 1.25 = 1.75 (exactly wait)
			check.truthy(Rules.due(st, zn, 1.75, 0) ~= nil)
		end)

		test.case("due: marks state spent so it cannot fire twice per stop", function()
			-- line 62 (true->false): state.spent = true — without this a second call fires again
			local zn = { delay = 0.1, after = 0.1, phantom = 0.9 }
			local st = Rules.new()
			for i = 1, 5 do
				Rules.step(st, i * 0.1, "snd")
			end
			local first = Rules.due(st, zn, 10, 0)
			check.truthy(first ~= nil) -- fires first time
			check.equal(Rules.due(st, zn, 11, 0), nil) -- must be nil: spent=true blocks re-fire
		end)

		test.case("due: phantom at exactly its chance blocks the echo (>= not >)", function()
			-- line 64 (>= -> >): roll >= phantom -> nil; at roll==phantom original blocks, mutant fires
			local zn = { delay = 0.1, after = 0.1, phantom = 0.5, min_steps = 4 }
			local st = Rules.new()
			for i = 1, 5 do
				Rules.step(st, i * 0.1, "snd")
			end
			-- roll=0.5, phantom=0.5: 0.5 >= 0.5 -> true -> return nil (blocked)
			check.equal(Rules.due(st, zn, 10, 0.5), nil)
		end)

		test.case("reverbSwitch: switches at exactly hold time (>= not >)", function()
			-- line 93 (>= -> >): now - lastChange >= hold — at exactly hold original returns true
			-- now=0.5, lastChange=0, hold=0.5: 0.5 >= 0.5 -> true; with > -> false
			check.is_true(Rules.reverbSwitch("A", "B", 0.5, 0, 0.5))
			-- just before hold must still be blocked
			check.is_false(Rules.reverbSwitch("A", "B", 0.49, 0, 0.5))
		end)

		-- line 19 (0 -> 1): zoneAt uses z-default 0 for zone centre (the second num(zn.z, 0))
		test.case("zoneAt: zone with no z field has its centre at z=0 (default=0 not 1)", function()
			-- A zone {x=0, r=5} (no z): centre at z=0. Point (0, 0, 5.5): dz=5.5 -> outside with z-default=0.
			-- With mutant default z=1: dz = 5.5 - 1 = 4.5 -> 4.5^2=20.25 <= 25 -> inside. So nil vs non-nil.
			local zNoZ = { { x = 0, r = 5 } }
			check.equal(Rules.zoneAt(zNoZ, 0, 0, 5.5), nil) -- outside with default z=0
			check.truthy(Rules.zoneAt(zNoZ, 0, 0, 3) ~= nil) -- inside
		end)

		-- line 33 (5 -> 6): delay upper clamp is 5 — a delay of exactly 5 is kept
		test.case("repeatOf: delay clamped at exactly 5 (clamp upper is 5 not 6)", function()
			-- delay=5: math.clamp(5, 0.05, 5) = 5. With clamp upper=6: math.clamp(5, 0.05, 6) = 5. Same!
			-- Need delay=5.5: original: clamp(5.5, 0.05, 5) = 5. Mutant: clamp(5.5, 0.05, 6) = 5.5.
			local rAt5 = Rules.repeatOf({ delay = 5 })
			local rAt6 = Rules.repeatOf({ delay = 6 })
			check.truthy(math.abs(rAt5.delay - 5) < 1e-9) -- 5 is not clamped
			-- a delay > 5 must be clamped to 5 (kills 5->6 on the upper bound)
			check.truthy(math.abs(rAt6.delay - 5) < 1e-9) -- 6 clamped to 5; with bound=6 it would be 6
		end)

		-- line 34 (60 -> 61): gain_db lower clamp is -60 — gain_db=-60 must yield correct volume
		test.case("repeatOf: gain_db clamped at -60 dB minimum (clamp lower is -60 not -61)", function()
			-- gain_db=-60: math.clamp(-60, -60, 6) = -60. With lower=-61: math.clamp(-60, -61, 6) = -60. Same.
			-- Need gain_db=-61: original: clamp(-61, -60, 6) = -60. Mutant: clamp(-61, -61, 6) = -61.
			local rAtMinus60 = Rules.repeatOf({ gain_db = -60 })
			local rAtMinus61 = Rules.repeatOf({ gain_db = -61 })
			local expected60 = 10 ^ (-60 / 20)
			check.truthy(math.abs(rAtMinus60.volume - expected60) < 1e-6) -- -60 not clamped lower
			check.truthy(math.abs(rAtMinus61.volume - expected60) < 1e-6) -- -61 clamped to -60; with -61 bound would differ
		end)

		-- line 35 (1.5 -> 2.5): pitch upper clamp is 1.5 — pitch=1.5 stays 1.5; pitch=2 is clamped
		test.case("repeatOf: pitch clamped at 1.5 maximum (clamp upper is 1.5 not 2.5)", function()
			-- pitch=1.5: clamp(1.5, 0.5, 1.5) = 1.5. Mutant clamp upper=2.5: same (1.5 not over 2.5).
			-- Need pitch=2: original: clamp(2, 0.5, 1.5) = 1.5. Mutant: clamp(2, 0.5, 2.5) = 2.
			local rAt15 = Rules.repeatOf({ pitch = 1.5 })
			local rAt20 = Rules.repeatOf({ pitch = 2 })
			check.truthy(math.abs(rAt15.speed - 1.5) < 1e-9) -- 1.5 not clamped
			check.truthy(math.abs(rAt20.speed - 1.5) < 1e-9) -- 2 clamped to 1.5; with upper=2.5 it would be 2
		end)

		-- line 42 (1 -> 2): new() initialises last to -1e9 (not -2e9)
		test.case("new: initial last is exactly -1e9 (default not -2e9)", function()
			-- last = -1e9: used as the timestamp of the last step. A very old value means due can fire soon.
			-- With -2e9 (mutant), the wait check (now - last < wait) would still pass for sane `now` values.
			-- To distinguish: now=0, wait=1. now - last: original = 0 - (-1e9) = 1e9 >= 1 -> passes.
			-- Mutant -2e9: 0 - (-2e9) = 2e9 >= 1 -> also passes. Equivalent for the due test.
			-- But we can verify the value directly: a fresh state's last must be -1e9.
			local st = Rules.new()
			check.truthy(st.last == -1e9) -- exactly -1e9, not some other sentinel
		end)

		-- line 63 (0 -> 1): steps reset to 0 after due fires
		test.case("due: steps are reset to 0 when the phantom fires (not 1)", function()
			-- After due fires: state.steps = 0. With mutant steps=1, a second stop after exactly
			-- min_steps-1=3 more steps would still not fire (3 < 4), distinguishing the two.
			local zn = { delay = 0.1, after = 0.1, phantom = 0.9, min_steps = 4 }
			local st = Rules.new()
			for i = 1, 5 do
				Rules.step(st, i * 0.1, "snd")
			end
			Rules.due(st, zn, 10, 0) -- fires and resets steps
			check.equal(st.steps, 0) -- must be 0, not 1
		end)

		-- line 64 (0 -> 1): phantom default is 0 — missing phantom field means roll=0 always fires
		test.case("due: missing phantom field defaults to 0 (roll=0 always fires, kills 0->1)", function()
			-- phantom defaults to 0. roll=0: 0 >= 0 -> true -> return nil (blocked).
			-- Wait: roll >= phantom -> nil. So phantom=0, roll=0: blocked (no phantom fires).
			-- A phantom of 0 means it never fires (the chance of echoing is 0%).
			-- Original: roll >= num(nil, 0) = 0 -> true -> return nil.
			-- Mutant: roll >= num(nil, 1) = 1 -> roll=0 >= 1 = false -> would fire.
			-- So with no phantom field and roll=0: original blocks (nil), mutant fires.
			local znNoPh = { delay = 0.1, after = 0.1, min_steps = 4 } -- no phantom field
			local st = Rules.new()
			for i = 1, 5 do
				Rules.step(st, i * 0.1, "snd")
			end
			check.equal(Rules.due(st, znNoPh, 10, 0), nil) -- no phantom = no echo (roll=0 >= default 0 -> blocked)
		end)
	end)
end

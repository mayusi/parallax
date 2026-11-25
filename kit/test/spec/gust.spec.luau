-- gust.spec.luau — GustRules (src/kit): rare moments the wind causes fire on a real gust only (a rise above the
-- wind's own recent average, the rising edge), rest for their cooldown, and keep to their chance.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Rules = require("../../../src/kit/GustRules")

return function()
	test.suite("GustRules: the wind causes rare moments", function()
		test.case("the running mean follows the wind slowly", function()
			local st = Rules.new()
			check.equal(Rules.track(st, 5, 0.25, 20), 5)
			for _ = 1, 4 do
				Rules.track(st, 15, 0.25, 20)
			end
			check.truthy(st.mean > 5 and st.mean < 7) -- (one second of a strong gust barely moves a 20 s mean)
		end)

		test.case("a steady wind never fires; a gust fires once on its rising edge", function()
			local st = Rules.new()
			Rules.track(st, 6, 1, 20)
			local rule = { rise = 1.3, floor = 4, cooldown = 0, chance = 1 }
			check.falsy(Rules.fires(st, 1, rule, 6, 0, 0)) -- (steady)
			check.truthy(Rules.fires(st, 1, rule, 9, 1, 0)) -- (gust: 9 >= 6 * 1.3)
			check.falsy(Rules.fires(st, 1, rule, 9.5, 2, 0)) -- (the same gust, still above: no second knock)
			check.falsy(Rules.fires(st, 1, rule, 6, 3, 0)) -- (it passed)
			check.truthy(Rules.fires(st, 1, rule, 9, 4, 0)) -- (the next gust)
		end)

		test.case("the cooldown and the chance keep it rare", function()
			local st = Rules.new()
			Rules.track(st, 6, 1, 20)
			local rule = { rise = 1.3, floor = 4, cooldown = 90, chance = 0.5 }
			check.truthy(Rules.fires(st, 1, rule, 9, 0, 0.1))
			Rules.fires(st, 1, rule, 6, 1, 0.1)
			check.falsy(Rules.fires(st, 1, rule, 9, 30, 0.1)) -- (inside the cooldown)
			Rules.fires(st, 1, rule, 6, 31, 0.1)
			check.falsy(Rules.fires(st, 1, rule, 9, 120, 0.9)) -- (a gust past the cooldown, but the roll misses)
			Rules.fires(st, 1, rule, 6, 121, 0.1)
			check.truthy(Rules.fires(st, 1, rule, 9, 200, 0.2))
		end)

		test.case("calm air below the floor never fires, whatever its ratio", function()
			local st = Rules.new()
			Rules.track(st, 1, 1, 20)
			check.falsy(Rules.fires(st, 1, { rise = 1.3, floor = 4, cooldown = 0, chance = 1 }, 3, 0, 0))
		end)
		test.case("window=0 is clamped to 1; window=1 and window=2 give different means", function()
			-- math.max(1, ...) clamps window=0 to 1; mutant max(2,...) would clamp it to 2 and move less
			local st = Rules.new()
			Rules.track(st, 5, 1, 0) -- seed the mean at 5
			Rules.track(st, 15, 0.5, 1) -- w=1, dt=0.5: k = 1 - exp(-0.5) ≈ 0.393
			local w1_mean = st.mean :: number
			local st2 = Rules.new()
			Rules.track(st2, 5, 1, 0)
			Rules.track(st2, 15, 0.5, 2) -- w=2: smaller k, mean moves less
			check.truthy(w1_mean > (st2.mean :: number))
		end)
		test.case("default window is 20, not 21: a measured mean after a large dt differs", function()
			-- nil window uses default=20; at dt=20: k = 1-exp(-1) ≈ 0.632; w=21 gives k=1-exp(-20/21) ≈ 0.618
			local st = Rules.new()
			Rules.track(st, 5, 1, nil) -- seed mean=5
			Rules.track(st, 15, 20, nil) -- nil -> default 20
			local m20 = st.mean :: number
			local st2 = Rules.new()
			Rules.track(st2, 5, 1, nil)
			Rules.track(st2, 15, 20, 21) -- explicitly w=21
			check.truthy(math.abs(m20 - (st2.mean :: number)) > 0.01) -- different means
		end)
		test.case("dt=0.5 contributes to the mean; dt=0 does not (math.max(0,dt) clamp)", function()
			-- math.max(0, dt): dt=0 -> k=0 -> no change; dt=0.5 -> k=1-exp(-0.5/w) > 0 -> mean changes
			local st = Rules.new()
			Rules.track(st, 5, 1, 1) -- seed mean=5
			local before = st.mean :: number
			Rules.track(st, 15, 0, 20) -- dt=0: original max(0,0)=0, k=0, no change
			check.truthy(math.abs((st.mean :: number) - before) < 1e-9)
			-- with dt=0.5 (< 1), original max(0, 0.5)=0.5 (mean moves); mutant max(1,0.5)=1 (mean moves more)
			local st2 = Rules.new()
			Rules.track(st2, 5, 1, 1)
			Rules.track(st2, 15, 0.5, 1) -- dt=0.5, w=1: k=1-exp(-0.5) ≈ 0.393
			local after_05 = st2.mean :: number
			local st3 = Rules.new()
			Rules.track(st3, 5, 1, 1)
			Rules.track(st3, 15, 1, 1) -- dt=1, w=1: k=1-exp(-1) ≈ 0.632 (more)
			check.truthy(after_05 > before and (st3.mean :: number) > after_05)
		end)
		test.case("the gust test uses >= for rise: a speed above the threshold fires, below does not", function()
			-- mean = 10 (first track call), rise = 1.3: threshold = 10 * 1.3 = 13.0 exactly (integers)
			local st = Rules.new()
			Rules.track(st, 10, 1, 20) -- first call: mean = 10 exactly
			local rule = { rise = 1.3, floor = 4, cooldown = 0, chance = 1 }
			check.truthy(Rules.fires(st, 1, rule, 13, 0, 0)) -- 13 >= 10 * 1.3 = 13.0: fires
			Rules.fires(st, 1, rule, 6, 1, 0) -- not a gust: reset edge
			check.falsy(Rules.fires(st, 1, rule, 12, 2, 0)) -- 12 < 13.0: not a gust
		end)
		test.case("the gust test uses >= for floor: speed at exactly floor fires", function()
			-- mean = 2 (very low): any speed >= 2*1.3=2.6 passes ratio; floor=4: speed=4 passes >= 4
			local st = Rules.new()
			Rules.track(st, 2, 1, 20) -- mean = 2 exactly
			local rule2 = { rise = 1.3, floor = 4, cooldown = 0, chance = 1 }
			check.truthy(Rules.fires(st, 1, rule2, 4, 0, 0)) -- 4 >= 2*1.3=2.6 AND 4 >= floor=4: fires
			Rules.fires(st, 1, rule2, 2, 1, 0) -- not a gust: reset
			check.falsy(Rules.fires(st, 1, rule2, 3, 2, 0)) -- 3 < floor=4: does not fire
		end)
		test.case("default floor is 4, not 5: speed 4.5 fires with floor=4 but not floor=5", function()
			local st = Rules.new()
			Rules.track(st, 2, 1, 20) -- low mean: rise always passes
			local rule = { rise = 1.0, cooldown = 0, chance = 1 } -- floor = nil: default 4
			check.truthy(Rules.fires(st, 1, rule, 4.5, 0, 0)) -- default floor=4: 4.5 >= 4 fires
			Rules.fires(st, 1, rule, 1, 1, 0)
			local rule5 = { rise = 1.0, floor = 5, cooldown = 0, chance = 1 }
			local st2 = Rules.new()
			Rules.track(st2, 2, 1, 20)
			check.falsy(Rules.fires(st2, 1, rule5, 4.5, 0, 0)) -- floor=5: 4.5 < 5 does NOT fire
		end)
		test.case("cooldown uses <: at elapsed = cooldown exactly it fires again", function()
			local st = Rules.new()
			Rules.track(st, 6, 1, 20)
			local rule = { rise = 1.3, floor = 4, cooldown = 90, chance = 1 }
			Rules.fires(st, 1, rule, 9, 0, 0) -- fires at t=0
			Rules.fires(st, 1, rule, 6, 1, 0) -- not a gust
			check.falsy(Rules.fires(st, 1, rule, 9, 89, 0)) -- 89 < 90: inside cooldown
			Rules.fires(st, 1, rule, 6, 90, 0)
			check.truthy(Rules.fires(st, 1, rule, 9, 90, 0)) -- 90 is NOT < 90: fires again
		end)
		test.case("default cooldown is 90, not 91: fires at elapsed 90 with nil cooldown", function()
			local st = Rules.new()
			Rules.track(st, 6, 1, 20)
			local rule = { rise = 1.3, floor = 4, chance = 1 } -- cooldown = nil: default 90
			Rules.fires(st, 1, rule, 9, 0, 0) -- fires at t=0
			Rules.fires(st, 1, rule, 6, 1, 0)
			check.truthy(Rules.fires(st, 1, rule, 9, 90, 0)) -- elapsed=90: 90 NOT < 90, fires
		end)
		test.case("chance uses >=: roll at exactly 0.5 is blocked; default chance is 0.5", function()
			local st = Rules.new()
			Rules.track(st, 6, 1, 20)
			-- roll = chance = 0.5: original >= blocks it; > would let it through
			local rule = { rise = 1.3, floor = 4, cooldown = 0, chance = 0.5 }
			check.falsy(Rules.fires(st, 1, rule, 9, 0, 0.5)) -- 0.5 >= 0.5: blocked
			Rules.fires(st, 1, rule, 6, 1, 0)
			check.truthy(Rules.fires(st, 1, rule, 9, 2, 0.49)) -- 0.49 < 0.5: fires
			-- default chance = 0.5: a roll of 0.9 is blocked (0.9 >= 0.5); mutant 1.5 would fire
			local rule_no_chance = { rise = 1.3, floor = 4, cooldown = 0 }
			local st2 = Rules.new()
			Rules.track(st2, 6, 1, 20)
			check.falsy(Rules.fires(st2, 1, rule_no_chance, 9, 0, 0.9)) -- default chance=0.5: 0.9 >= 0.5 blocked
			Rules.fires(st2, 1, rule_no_chance, 6, 1, 0)
			check.truthy(Rules.fires(st2, 1, rule_no_chance, 9, 2, 0.1)) -- 0.1 < 0.5: fires
		end)

		test.case("rules keep their own edges and cooldowns", function()
			local st = Rules.new()
			Rules.track(st, 6, 1, 20)
			local a = { cooldown = 90, chance = 1 }
			local b = { cooldown = 0, chance = 1 }
			check.truthy(Rules.fires(st, 1, a, 9, 0, 0))
			check.truthy(Rules.fires(st, 2, b, 9, 0, 0))
		end)
	end)
end

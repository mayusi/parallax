-- uitext.spec.luau — UiTextRules (src/kit): the player's own text size (GuiService.PreferredTextSize) as a factor the
-- compiler and the runtime share - the scaled size, the engine's cap, and whether a text still fits its box at Largest.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Rules = require("../../../src/kit/UiTextRules")

return function()
	test.suite("UiTextRules: the player's preferred text size", function()
		test.case("each setting's factor; anything else is 1", function()
			check.equal(Rules.factor("Medium"), 1)
			check.equal(Rules.factor("Large"), 1.15)
			check.equal(Rules.factor("Larger"), 1.3)
			check.equal(Rules.factor("Largest"), 1.5)
			check.equal(Rules.factor("Huge"), 1)
			check.equal(Rules.factor(nil), 1)
			check.equal(Rules.factor(3), 1)
		end)
		test.case("the scaled size is whole pixels and never past the engine's cap", function()
			check.equal(Rules.scaled(18, "Large"), 21) -- (20.7 -> 21)
			check.equal(Rules.scaled(20, "Largest"), 30)
			check.equal(Rules.scaled(80, "Largest"), 100) -- (120 capped)
			check.equal(Rules.scaled(18, "Medium"), 18)
			check.is_true(Rules.scaled(0 / 0, "Large") ~= Rules.scaled(0 / 0, "Large")) -- (NaN passes through untouched)
		end)
		test.case("a text fits its box at Largest, or names the height it needs", function()
			local ok, need = Rules.fits(20, 40)
			check.is_true(ok)
			check.equal(need, 36) -- (30 px at Largest x 1.2 line)
			local tight = Rules.fits(20, 24)
			check.is_false(tight)
			local two, need2 = Rules.fits(20, 60, 2)
			check.is_false(two)
			check.equal(need2, 72)
			check.is_true((Rules.fits(20, nil))) -- (a box with no pixel height is not judged)
		end)
		test.case("scaled: a base of exactly 0 or 1 matters at Largest", function()
			-- base <= 0 guard: 0 is not > 0, so it passes through unchanged
			check.equal(Rules.scaled(0, "Large"), 0)
			-- negative base also passes through (not a valid size)
			check.equal(Rules.scaled(-5, "Large"), -5)
			-- base = 1: the guard does NOT fire (1 > 0); at Largest: floor(1 * 1.5 + 0.5) = floor(2) = 2
			check.equal(Rules.scaled(1, "Largest"), 2)
			-- 10 at Large is floor(10 * 1.15 + 0.5) = floor(12.0) = 12
			check.equal(Rules.scaled(10, "Large"), 12)
		end)
		test.case("fits: boundary values for boxHeight and the +0.5 tolerance", function()
			-- boxHeight <= 0: 0 is not > 0, so the guard fires and returns true
			check.is_true((Rules.fits(20, 0)))
			-- negative boxHeight: also not a valid box
			check.is_true((Rules.fits(20, -10)))
			-- boxHeight = 1: the guard does NOT fire (1 > 0); 36 <= 1.5 is false
			check.is_false((Rules.fits(20, 1)))
			-- need = 36; boxHeight = 35.5 (need == boxHeight + 0.5 exactly): fits with <=
			check.is_true((Rules.fits(20, 35.5)))
			-- a box of exactly 36 also fits
			check.is_true((Rules.fits(20, 36)))
			-- a box of 35 does not fit (36 > 35.5)
			check.is_false((Rules.fits(20, 35)))
		end)
	end)
end

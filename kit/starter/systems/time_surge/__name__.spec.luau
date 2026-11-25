-- __name__.spec.luau — rules of the __NAME__ system (pure, headless). Add a case for every rule you add.
local frk = require("@kit/test/frk")
local test, check = frk.test, frk.check

local __NAME__Config = require("../src/shared/__NAME__Config")
local __NAME__Rules = require("../src/shared/__NAME__Rules")

return function()
	test.suite("__NAME__Rules", function()
		test.case("a fresh player can activate", function()
			check.is_true((__NAME__Rules.canActivate(__NAME__Rules.new(), 100)))
		end)
		test.case("active for DURATION, then cooling down for COOLDOWN, then ready", function()
			local s = __NAME__Rules.activate(__NAME__Rules.new(), 100)
			check.is_true(__NAME__Rules.isActive(s, 100 + __NAME__Config.DURATION - 0.01))
			check.is_false((__NAME__Rules.canActivate(s, 101)))
			local afterEnd = 100 + __NAME__Config.DURATION + 0.01
			check.is_false(__NAME__Rules.isActive(s, afterEnd))
			check.is_false((__NAME__Rules.canActivate(s, afterEnd)))
			check.is_true((__NAME__Rules.canActivate(s, afterEnd + __NAME__Config.COOLDOWN)))
		end)
		test.case("the boost is added (and later removed) as an amount", function()
			check.equal(16 + __NAME__Rules.boost(16), 16 * __NAME__Config.SPEED_MULTIPLIER)
			check.equal(__NAME__Rules.boost(0), 0) -- a rooted player stays rooted
			check.equal(__NAME__Rules.boost(-5), 0)
		end)
	end)
end

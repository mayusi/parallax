-- __name__.spec.luau — rules of the __NAME__ system (pure, headless). Add a case for every rule you add.
local frk = require("@kit/test/frk")
local test, check = frk.test, frk.check

local __NAME__Config = require("../src/shared/__NAME__Config")
local __NAME__Rules = require("../src/shared/__NAME__Rules")

return function()
	test.suite("__NAME__Rules.check", function()
		test.case("accepts a valid request", function()
			check.is_true((__NAME__Rules.check(5, 10)))
		end)
		test.case("rejects hostile power values", function()
			for _, bad in { 0 / 0, math.huge, -1, 0, __NAME__Config.MAX_POWER + 1, "5", {} } do
				check.is_false((__NAME__Rules.check(bad, 10)))
			end
		end)
		test.case("rejects targets out of range", function()
			check.is_false((__NAME__Rules.check(5, __NAME__Config.RANGE + 0.1)))
		end)
	end)
end

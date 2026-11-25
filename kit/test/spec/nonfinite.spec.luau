-- nonfinite.spec.luau — the remote validators refuse NaN / inf / a missing key instead of letting them through or
-- throwing (LIMITATIONS_FIXES_V4 8.3: "reject NaN/inf/wrong types ... fuzz clean"). RateLimit.take used to throw
-- "table index is NaN" on a NaN key and let a NaN / inf clock poison its bucket for good (it never refilled); Guard.number
-- let ANY number through a NaN bound (`v < NaN` is false for every v).
local frk = require("../frk")
local test, check = frk.test, frk.check

local Guard = require("../../../src/kit/Guard")
local RateLimit = require("../../../src/kit/RateLimit")

local NAN = 0 / 0

return function()
	test.suite("RateLimit under a non-finite clock or key", function()
		test.case("a NaN / inf / -inf / non-number clock is refused", function()
			local limit = RateLimit.new(3, 1)
			for _, bad in { NAN, math.huge, -math.huge, "1", nil, {} } do
				check.is_false(limit:take("p", bad :: any))
			end
		end)
		test.case("a refused clock leaves the bucket as it was: it still refills on the real clock", function()
			local limit = RateLimit.new(1, 1)
			check.is_true(limit:take("p", 0))
			check.is_false(limit:take("p", 0)) -- (empty)
			limit:take("p", NAN)
			limit:take("p", math.huge)
			check.is_true(limit:take("p", 1.01)) -- one second later: refilled (a poisoned bucket stayed empty forever)
		end)
		test.case("a fresh key's first call with a NaN clock makes no bucket", function()
			local limit = RateLimit.new(1, 1)
			check.is_false(limit:take("q", NAN))
			check.equal(limit.buckets["q"], nil)
			check.is_true(limit:take("q", 5))
		end)
		test.case("a nil or NaN key is refused, never thrown", function()
			local limit = RateLimit.new(3, 1)
			local ok, res = pcall(function()
				return limit:take(NAN, 0)
			end)
			check.is_true(ok)
			check.is_false(res)
			check.is_false(limit:take(nil, 0))
			check.is_true(limit:take(0, 0)) -- (a real key 0 is fine)
		end)
	end)

	test.suite("Guard.number with a NaN bound refuses", function()
		test.case("NaN min or max lets nothing through", function()
			check.is_false((Guard.number(5, NAN, 10)))
			check.is_false((Guard.number(5, 0, NAN)))
			check.is_false((Guard.integer(5, NAN, NAN)))
		end)
		test.case("the bounds themselves are inside (inclusive)", function()
			check.is_true((Guard.number(0, 0, 10)))
			check.is_true((Guard.number(10, 0, 10)))
			check.is_false((Guard.number(10.000001, 0, 10)))
			check.is_false((Guard.number(-0.000001, 0, 10)))
		end)
	end)
end

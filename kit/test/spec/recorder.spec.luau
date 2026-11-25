-- recorder.spec.luau — the flight recorder (src/kit/Recorder): a ring buffer of the last remote calls, hostile input
-- kept short, written out once per error burst.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Recorder = require("../../../src/kit/Recorder")

return function()
	test.suite("Recorder", function()
		test.case("keeps the last CAPACITY calls, oldest first", function()
			Recorder.clear()
			for i = 1, Recorder.CAPACITY + 5 do
				Recorder.record("Strike.Request", i, "ok", i)
			end
			local list = Recorder.list()
			check.equal(#list, Recorder.CAPACITY)
			check.equal(list[1].user, 6)
			check.equal(list[#list].user, Recorder.CAPACITY + 5)
			Recorder.clear()
			check.equal(#Recorder.list(), 0)
		end)
		test.case("hostile arguments stay short: long strings cut, tables counted, NaN named", function()
			check.equal(Recorder.summarize(0 / 0), "nan")
			check.equal(Recorder.summarize(1.5), "1.5")
			local long = Recorder.summarize(string.rep("x", 100000))
			check.is_true(#long < 50)
			check.is_true(string.find(long, "+99976", 1, true) ~= nil)
			local cyclic = {}
			cyclic.self = cyclic
			check.equal(Recorder.summarize(cyclic), "table(1)")
			local big = {}
			for i = 1, 5000 do
				big[i] = i
			end
			check.equal(Recorder.summarize(big), "table(999+)")
			check.equal(Recorder.summarize(nil), "nil")
			Recorder.clear()
			local many = {}
			for i = 1, 20 do
				many[i] = i
			end
			Recorder.record("X.Y", 1, "rejected a", table.unpack(many))
			check.is_true(string.find(Recorder.list()[1].args, "+12 more", 1, true) ~= nil)
		end)
		test.case("an error writes the buffer out once per burst", function()
			Recorder.clear()
			Recorder.record("Session.Start", 7, "limited")
			Recorder.record("Strike.Request", 7, "rejected power", 1, 0 / 0, "heavy")
			local fire
			local fakeContext = {
				Error = {
					Connect = function(_, fn)
						fire = fn
						return {}
					end,
				},
			}
			local said = {}
			Recorder.watch(fakeContext, function(text)
				table.insert(said, text)
			end)
			fire("attempt to index nil")
			fire("attempt to index nil") -- (the same burst: quiet)
			check.equal(#said, 1)
			check.is_true(string.find(said[1], "attempt to index nil", 1, true) ~= nil)
			check.is_true(
				string.find(said[1], 'Strike.Request user 7 rejected power (1, nan, "heavy")', 1, true) ~= nil
			)
			check.is_true(string.find(said[1], "Session.Start user 7 limited", 1, true) ~= nil)
			Recorder.clear()
		end)
	end)
end

-- animprop.spec.luau — A PROP'S CLIP ON A CHARACTER'S CLOCK (src/kit/AnimProp; LIMITATIONS_FIXES_V3 Stage D): the
-- prop's time for the character's (an offset, a rate, held at its ends, a looped prop wrapping) and its markers said
-- once whatever the clock does (a rewind, a wrap, a late entry, a cancel, a clip that ran to its end). The rules
-- only: that the engine's joints follow the time set is Studio's to show.
local frk = require("../frk")
local test, check = frk.test, frk.check

local P = require("../../../src/kit/AnimProp")

local function names(list: { P.Event }): string
	local out = {}
	for _, e in list do
		table.insert(out, e.name)
	end
	return table.concat(out, ",")
end

local function near(a: number, b: number): boolean
	return math.abs(a - b) < 1e-9
end

return function()
	test.suite("a prop's clip on a character's clock: its time", function()
		test.case("the same time, an offset, a rate", function()
			local link = { length = 1.2 }
			check.is_true(near(P.timeFor(0.5, link), 0.5))
			check.is_true(near(P.timeFor(0.5, { length = 1.2, offset = 0.2 }), 0.3))
			check.is_true(near(P.timeFor(0.5, { length = 1.2, offset = 0.2, rate = 2 }), 0.6))
		end)
		test.case("held at its first frame before it starts, at its last after it ends", function()
			check.is_true(P.timeFor(0.1, { length = 1.2, offset = 0.2 }) == 0)
			check.is_true(near(P.timeFor(5, { length = 1.2 }), 1.2))
		end)
		test.case(
			"a looped prop clip wraps (a wheel that keeps turning), backwards too; a time that is not one is 0",
			function()
				check.is_true(near(P.timeFor(2.5, { length = 1, loop = true }), 0.5))
				check.is_true(near(P.timeFor(-0.25, { length = 1, loop = true }), 0.75))
				check.is_true(P.timeFor(0 / 0, { length = 1 }) == 0)
				check.is_true(P.timeFor(3, { length = 0, loop = true }) == 0) -- (a clip of no length: held, not divided by 0)
			end
		)
	end)

	test.suite("a prop's clip on a character's clock: its markers, each once", function()
		local events = { { name = "Rack", t = 0.3 }, { name = "Click", t = 0.1 }, { name = "Seat", t = 0.8 } }
		test.case("in time order as the clock reaches them; one long step says all it crossed, in order", function()
			local m = P.marks(events)
			check.is_true(names(P.cross(m, 0.05, 1)) == "")
			check.is_true(names(P.cross(m, 0.1, 1)) == "Click") -- (exactly at the clock: reached)
			check.is_true(names(P.cross(m, 0.9, 1)) == "Rack,Seat")
			check.is_true(names(P.cross(m, 1, 1)) == "")
		end)
		test.case("a rewind over a marker (a hit-stop's jitter, a clip wound back) never says it again", function()
			local m = P.marks(events)
			P.cross(m, 0.35, 1)
			check.is_true(names(P.cross(m, 0.2, 1)) == "")
			check.is_true(names(P.cross(m, 0.4, 1)) == "")
			check.is_true(names(P.cross(m, 0.85, 1)) == "Seat")
		end)
		test.case("a looped prop's wrap: the end of the pass it left, then the new pass", function()
			local m = P.marks(events)
			local link = { length = 1, loop = true }
			local t, c = P.timeFor(0.5, link)
			P.cross(m, t, 1, true, c) -- Click, Rack
			t, c = P.timeFor(1.15, link) -- (0.5 -> 1.0 -> 0.15 in one long step: Seat of pass 1, then Click of pass 2)
			check.is_true(near(t, 0.15) and c == 1)
			check.is_true(names(P.cross(m, t, 1, true, c)) == "Seat,Click" and m.pass == 2)
			check.is_true(names(P.cross(m, 0.1, 1, true, 1)) == "") -- (a step back in the same cycle is no wrap)
			-- told no cycle: a clock that went back more than half the clip wrapped, a smaller step back did not
			local n = P.marks(events)
			P.cross(n, 0.95, 1, true)
			check.is_true(names(P.cross(n, 0.05, 1, true)) == "" and n.pass == 2)
			check.is_true(names(P.cross(n, 0.12, 1, true)) == "Click")
			check.is_true(names(P.cross(n, 0.02, 1, true)) == "" and n.pass == 2)
		end)
		test.case("an entry past a marker does not owe it; a new pass owes them all again", function()
			local m = P.marks(events, 0.5)
			check.is_true(names(P.cross(m, 0.6, 1)) == "")
			check.is_true(names(P.cross(m, 0.9, 1)) == "Seat")
			P.pass(m)
			check.is_true(names(P.cross(m, 0.9, 1)) == "Click,Rack,Seat")
		end)
		test.case("a cancel ends them; a clip that ran to its end says what its last step missed, once", function()
			local m = P.marks(events)
			P.cross(m, 0.2, 1)
			P.cancel(m)
			check.is_true(names(P.cross(m, 0.9, 1)) == "")
			check.is_true(names(P.finish(m, 1)) == "")
			local n = P.marks({ { name = "End", t = 1.2 }, { name = "Mid", t = 0.6 } })
			P.cross(n, 1.19, 1.2)
			check.is_true(names(P.finish(n, 1.2)) == "End")
			check.is_true(names(P.finish(n, 1.2)) == "" and names(P.cross(n, 1.2, 1.2)) == "")
		end)
		test.case("a new pass counts the loop's cycles afresh (the review: a wrap read twice)", function()
			local m = P.marks({ { name = "Zero", t = 0 }, { name = "Half", t = 0.5 } })
			check.is_true(names(P.cross(m, 0.6, 1, true, 3)) == "Zero,Half")
			P.pass(m, 0)
			check.is_true(m.cycle == nil)
			check.is_true(names(P.cross(m, 0.1, 1, true, 4)) == "Zero") -- (a pass's first step is no wrap)
			check.is_true(names(P.cross(m, 0.2, 1, true, 4)) == "")
		end)
		test.case("the clip's own list is not changed (sorted in a copy)", function()
			local m = P.marks(events)
			check.is_true(events[1].name == "Rack" and m.events[1].name == "Click")
		end)
	end)
end

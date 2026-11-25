-- animmarks.spec.luau — ONE EFFECT FOR ONE MARKER (the owner's older list, AN-34): the rule src/kit/AnimMarks keeps
-- for every track's markers, built on what the engine was measured to do in Studio (2026-11-15): a marker fires each
-- time the clip's time crosses it, not while frozen on it, not when jumped over, not after a stop, and late.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local M = require("../../../src/kit/AnimMarks")

-- the kesa's own events
local events: { M.Event } = {
	{ name = "Swing", t = 0.3833 },
	{ name = "ActiveStart", t = 0.4167 },
	{ name = "Hit", t = 0.4333 },
	{ name = "ActiveEnd", t = 0.5167 },
}

local function near(a: number, b: number): boolean
	return math.abs(a - b) < 1e-6
end

return function()
	test.suite("AnimMarks: one effect for one marker", function()
		test.case("a marker is taken once, with its own time and how late the handler is", function()
			local s = M.new()
			local r = M.take(s, "Hit", 0.462, events) :: M.Record -- (the handler runs a frame past the marker)
			check.truthy(r ~= nil and r.name == "Hit" and r.index == 1 and r.pass == 1 and r.count == 1)
			check.truthy(near(r.time, 0.4333) and near(r.late, 0.462 - 0.4333))
		end)
		test.case(
			"a looped clip's marker AT its end (t == duration) is one effect a loop, whichever runs first",
			function()
				-- (the owner's V3 list, anim stage F.1: the edge t == duration was never tested) the engine's loop signal
				-- (Anim: DidLoop -> AnimMarks.pass) and the marker's handler come in either order in the wrap frame
				local ends: { M.Event } = { { name = "Loop", t = 1.0 } }
				for _, order in
					{ { "before", "before", "before" }, { "after", "after", "after" }, { "before", "after", "before" } }
				do
					local s = M.new()
					local got = 0
					for loop = 1, 3 do
						local mid = M.take(s, "Loop", 0.5, ends, nil, true, 1.0) -- (a stray read mid-loop takes nothing)
						check.truthy(mid == nil)
						if order[loop] == "before" then -- the handler at the very end, then the wrap
							if M.take(s, "Loop", 0.999, ends, nil, true, 1.0) then
								got += 1
							end
							M.pass(s)
						else -- the wrap first, the handler a frame into the next loop
							M.pass(s)
							if M.take(s, "Loop", 0.012, ends, nil, true, 1.0) then
								got += 1
							end
						end
					end
					check.equal(got, 3)
				end
				-- a clip that does not loop, its marker at its very last instant: taken once
				local s = M.new()
				check.truthy(M.take(s, "Loop", 1.0, ends, nil, false, 1.0) ~= nil)
				check.truthy(M.take(s, "Loop", 1.0, ends, nil, false, 1.0) == nil)
			end
		)
		test.case("crossed again in the same pass (the clip's time wound back) it is dropped", function()
			local s = M.new()
			check.truthy(M.take(s, "Hit", 0.44, events) ~= nil)
			check.truthy(M.take(s, "Hit", 0.45, events) == nil)
			check.truthy(M.take(s, "Hit", 0.4333, events) == nil)
			check.truthy(M.take(s, "Swing", 0.39, events) ~= nil) -- another marker of the pass is its own
			check.truthy(M.take(s, "Swing", 0.40, events) == nil)
		end)
		test.case("a new play is a new pass: every marker is taken once more", function()
			local s = M.new()
			for pass = 1, 3 do
				local r = M.take(s, "Hit", 0.44, events) :: M.Record
				check.truthy(r ~= nil and r.pass == pass and r.count == pass)
				check.truthy(M.take(s, "Hit", 0.44, events) == nil)
				M.pass(s)
			end
		end)
		test.case("after a cancel nothing is taken, until a new pass", function()
			local s = M.new()
			M.cancel(s)
			check.truthy(M.take(s, "Hit", 0.44, events) == nil)
			check.truthy(M.take(s, "Swing", 0.39, events) == nil)
			M.pass(s)
			check.truthy(M.take(s, "Hit", 0.44, events) ~= nil)
		end)
		test.case("two handlers on one marker each get it", function()
			-- (the kit's camera kick and a game's sound on "Hit": sharing one record, only the first to run got it)
			local s = M.new()
			local kick, sound = M.listener(), M.listener()
			check.truthy(M.take(s, "Hit", 0.44, events, kick) ~= nil)
			check.truthy(M.take(s, "Hit", 0.44, events, sound) ~= nil)
			check.truthy(M.take(s, "Hit", 0.45, events, kick) == nil) -- ... once each
			check.truthy(M.take(s, "Hit", 0.45, events, sound) == nil)
			M.cancel(s)
			M.pass(s)
			check.truthy(M.take(s, "Hit", 0.44, events, sound) ~= nil and M.take(s, "Hit", 0.44, events, kick) ~= nil)
		end)
		test.case("two markers of one name are taken first, then second, however late the handlers run", function()
			-- nine built clips have two Hits 0.1 to 0.23 s apart; a handler runs up to 0.06 s late at 25 frames a
			-- second, more at 10. (Choosing "the nearest event", a first fire 0.07 s late on a 0.1 s gap was taken
			-- for the SECOND Hit and the real second fire dropped: one effect lost)
			for _, gap in { 0.1, 0.167, 0.233 } do
				local two: { M.Event } = { { name = "Hit", t = 0.30 }, { name = "Hit", t = 0.30 + gap } }
				for late = 0, 12 do
					local s = M.new()
					local a = M.take(s, "Hit", 0.30 + late / 100, two) :: M.Record
					local b = M.take(s, "Hit", 0.30 + gap + late / 100, two) :: M.Record
					check.truthy(a ~= nil and a.index == 1 and near(a.time, 0.30))
					check.truthy(b ~= nil and b.index == 2 and near(b.time, 0.30 + gap) and b.count == 2)
					check.truthy(M.take(s, "Hit", 0.30 + gap + 0.05, two) == nil) -- a third fire is a duplicate
				end
			end
			-- one long frame crosses both: two fires at the same late time, taken in order
			local two: { M.Event } = { { name = "Hit", t = 0.30 }, { name = "Hit", t = 0.40 } }
			local s = M.new()
			local a = M.take(s, "Hit", 0.42, two) :: M.Record
			local b = M.take(s, "Hit", 0.42, two) :: M.Record
			check.truthy(a.index == 1 and b.index == 2 and M.take(s, "Hit", 0.42, two) == nil)
			-- a marker a hair AHEAD of the time read is still it (a frame's grace); one well ahead is not
			check.truthy((M.take(M.new(), "Hit", 0.295, two) :: M.Record).index == 1)
			check.truthy(M.take(M.new(), "Hit", 0.20, two) == nil)
			-- the first, wound back to and crossed again: a duplicate, never handed to the second
			local w = M.new()
			check.truthy((M.take(w, "Hit", 0.31, two) :: M.Record).index == 1)
			check.truthy(M.take(w, "Hit", 0.32, two) == nil)
			check.truthy((M.take(w, "Hit", 0.41, two) :: M.Record).index == 2)
		end)
		test.case("a looped clip's time going back is a new pass, whichever signal comes first", function()
			-- a 0.2 s loop with Shots at 0 and 0.1 (three built gun loops have a Shot at 0)
			local loop: { M.Event } = { { name = "Shot", t = 0 }, { name = "Shot", t = 0.1 } }
			local s, me = M.new(), M.listener()
			local n = 0
			for _ = 1, 5 do
				for _, at in { 0.01, 0.11 } do
					if M.take(s, "Shot", at, loop, me, true, 0.2) then
						n += 1
					end
				end
			end
			check.equal(n, 10) -- (told only by the engine's loop signal, the Shot at 0 was dropped on the first wrap)
			-- a marker in the clip's last frame, its handler run after the wrap: still taken, once a pass
			local tail: { M.Event } = { { name = "Step", t = 0.1 }, { name = "End", t = 0.79 } }
			local t, mine = M.new(), M.listener()
			local ends = 0
			for _ = 1, 4 do
				check.truthy(M.take(t, "Step", 0.12, tail, mine, true, 0.8) ~= nil)
				local r = M.take(t, "End", 0.01, tail, mine, true, 0.8) -- (read after the wrap)
				if r then
					ends += 1
					check.truthy(near(r.time, 0.79) and near(r.late, 0.02))
				end
			end
			check.equal(ends, 4)
			-- a clip that does NOT loop: its time going back is a rewind, not a pass
			local once = M.new()
			check.truthy(M.take(once, "Shot", 0.11, loop) ~= nil) -- (both Shots are behind 0.11: the first is taken)
			check.truthy(M.take(once, "Shot", 0.11, loop) ~= nil) -- ... then the second
			check.truthy(M.take(once, "Shot", 0.01, loop) == nil)
		end)
		test.case("a clip entered late owes nothing before its entry", function()
			local two: { M.Event } = { { name = "Hit", t = 0.30 }, { name = "Hit", t = 0.40 } }
			local s = M.new()
			M.entered(s, 0.35) -- (the first Hit was jumped over: the engine never fires it)
			local r = M.take(s, "Hit", 0.42, two) :: M.Record
			check.truthy(r ~= nil and r.index == 2 and near(r.time, 0.40))
			check.truthy(M.take(s, "Hit", 0.43, two) == nil)
			M.pass(s) -- played again from its start: the entry is forgotten
			check.truthy((M.take(s, "Hit", 0.31, two) :: M.Record).index == 1)
		end)
		test.case("a marker the clip's events do not list, and times that are not numbers", function()
			local s = M.new()
			local r = M.take(s, "Whoosh", 0.2, events) :: M.Record
			check.truthy(r ~= nil and r.index == 1 and near(r.time, 0.2) and r.late == 0)
			check.truthy(M.take(s, "Whoosh", 0.25, events) == nil)
			check.truthy(M.take(M.new(), "Hit", 0 / 0, events) == nil)
			local none = M.take(M.new(), "Hit", 0.44, nil) :: M.Record
			check.truthy(none ~= nil and near(none.time, 0.44))
			local odd: any = { { name = "Hit" }, "x", { name = "Hit", t = 0 / 0 }, { name = "Hit", t = 0.5 } }
			local got = M.take(M.new(), "Hit", 0.52, odd) :: M.Record
			check.truthy(got.index == 1 and near(got.time, 0.5))
		end)
		test.case("the markers an entry jumped over, and the state a late entry still owes", function()
			-- (measured: a clip entered past a marker never fires it; one exactly at the entry does)
			local skipped = M.skipped(events, 0, 0.42)
			check.equal(#skipped, 2)
			check.truthy(skipped[1].name == "Swing" and skipped[2].name == "ActiveStart")
			check.equal(#M.skipped(events, 0, 0), 0)
			check.equal(#M.skipped(events, 0, 0.3833), 0)
			check.equal(#M.skipped(nil, 0, 9), 0)
			local faces: { M.Event } = {
				{ name = "Face", t = 0.1, value = "111" },
				{ name = "Vanish", t = 0.2 },
				{ name = "Face", t = 0.3, value = "222" },
				{ name = "Appear", t = 0.5 },
			}
			local worn = M.lastSkipped(faces, "Face", 0.4) :: M.Event
			check.truthy(worn ~= nil and worn.value == "222")
			check.truthy((M.lastSkipped(faces, "Face", 0.2) :: M.Event).value == "111")
			check.truthy(M.lastSkipped(faces, "Face", 0.05) == nil)
			-- entered between the Vanish and the Appear: gone; entered after the Appear: back
			local gone, back = M.lastSkipped(faces, "Vanish", 0.4), M.lastSkipped(faces, "Appear", 0.4)
			check.truthy(gone ~= nil and back == nil)
			back = M.lastSkipped(faces, "Appear", 0.6)
			check.truthy(back ~= nil and (back :: M.Event).t >= (gone :: M.Event).t)
		end)
		test.case("the runtime takes its own markers through the record", function()
			local anim = fs.readFile("src/kit/Anim.luau")
			local _, raw = string.gsub(anim, "GetMarkerReachedSignal%(", "")
			check.equal(raw, 1) -- (Anim.marker alone asks the engine)
			for _, line in
				{
					'Anim.marker(track, "Hit", m.events):Connect(function()',
					'Anim.marker(track, "Vanish", events):Connect(function()',
					'Anim.marker(track, "Face", events):Connect(function(value: string?)',
					'Anim.marker(track, "Afterimage", events):Connect(function(value: string?)',
					'Anim.marker(track, "Smear", events):Connect(function(value: string?)',
					"local mine = AnimMarks.listener()",
					"AnimMarks.take(info.state, name, track.TimePosition, events, mine, track.Looped, track.Length)",
					"AnimMarks.cancel(made.state)",
					"AnimMarks.entered(marksOf(track).state, at)",
					"if kicking.turn ~= mine then",
					"hum.CameraOffset += now - kicking.delta",
					'local gone = AnimMarks.lastSkipped(events, "Vanish", enteredAt)',
					'AnimMarks.lastSkipped(events, "Face", enteredAt)',
				}
			do
				check.truthy(string.find(anim, line, 1, true) ~= nil)
			end
		end)
	end)
end

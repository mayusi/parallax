--!strict
-- src/kit/AnimCurve: a kit clip as a Roblox curve animation - which keys a track keeps (thin), and what the engine's
-- 30-a-second playback of a curve animation drops (lost; measured in Studio 2026-11-15). The Instance side
-- (fromSequence) is seen in Studio; here its rule and a tripwire on its text.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local C = require("../../../src/kit/AnimCurve")

local function near(a: number, b: number, eps: number?): boolean
	return math.abs(a - b) <= (eps or 1e-9)
end

-- what plays at time t when only the kept keys remain (straight lines between them)
local function played(times: { number }, values: { number }, kept: { number }, t: number): number
	for k = 1, #kept - 1 do
		local a, b = kept[k], kept[k + 1]
		if t >= times[a] and t <= times[b] then
			return C.lerpNumber(values[a], values[b], (t - times[a]) / (times[b] - times[a]))
		end
	end
	return values[kept[#kept]]
end

return function()
	test.suite("AnimCurve: which keys a track keeps", function()
		test.case("a straight stretch keeps its two ends; a bend keeps its corner", function()
			local times, line = {}, {}
			for i = 0, 20 do
				table.insert(times, i / 60)
				table.insert(line, i * 0.5)
			end
			check.equal(#C.thin(times, line, 0.01, C.lerpNumber, C.distNumber), 2)
			local bend = table.clone(line)
			for i = 12, 21 do
				bend[i] = bend[11] -- flat from key 11 on
			end
			local kept = C.thin(times, bend, 0.01, C.lerpNumber, C.distNumber)
			check.equal(#kept, 3)
			check.equal(kept[2], 11)
		end)
		test.case("no dropped key is further than the tolerance from what plays", function()
			local times, wave = {}, {}
			for i = 0, 120 do
				table.insert(times, i / 60)
				table.insert(wave, 30 * math.sin(i / 9) + 5 * math.sin(i / 2.3))
			end
			for _, tol in { 0.05, 0.5, 3 } do
				local kept = C.thin(times, wave, tol, C.lerpNumber, C.distNumber)
				check.truthy(#kept < #wave and kept[1] == 1 and kept[#kept] == #wave)
				local worst = 0
				for i = 1, #wave do
					worst = math.max(worst, math.abs(wave[i] - played(times, wave, kept, times[i])))
				end
				check.truthy(worst <= tol + 1e-9)
			end
			-- a tighter tolerance keeps more keys
			local loose = #C.thin(times, wave, 3, C.lerpNumber, C.distNumber)
			local tight = #C.thin(times, wave, 0.05, C.lerpNumber, C.distNumber)
			check.truthy(tight > loose)
		end)
		test.case(
			"edges: few keys, a tolerance that is not one, two keys at one time, a distance that is not a number",
			function()
				check.equal(#C.thin({}, {}, 1, C.lerpNumber, C.distNumber), 0)
				check.equal(#C.thin({ 0 }, { 4 }, 1, C.lerpNumber, C.distNumber), 1)
				check.equal(#C.thin({ 0, 1 }, { 4, 9 }, 1, C.lerpNumber, C.distNumber), 2)
				local t, v = { 0, 1, 2, 3 }, { 0, 1, 2, 3 }
				check.equal(#C.thin(t, v, 0 / 0, C.lerpNumber, C.distNumber), 2) -- (a line needs no tolerance)
				check.equal(#C.thin(t, { 0, 5, 2, 3 }, 0 / 0, C.lerpNumber, C.distNumber), 4) -- (not a number: nothing dropped)
				check.equal(#C.thin(t, { 0, 5, 2, 3 }, -1, C.lerpNumber, C.distNumber), 4)
				-- two keys at the same time (a marker's keyframe beside a frame's): both kept, nothing divided by zero
				local kept = C.thin({ 0, 1, 1, 2 }, { 0, 1, 1, 2 }, 0.01, C.lerpNumber, C.distNumber)
				check.truthy(#kept >= 2 and kept[1] == 1 and kept[#kept] == 4)
				local nan = C.thin(t, v, 0.5, C.lerpNumber, function(_a: number, _b: number): number
					return 0 / 0
				end)
				check.equal(#nan, 4)
			end
		)
	end)
	test.suite("AnimCurve: what the engine's 30-a-second playback drops", function()
		test.case("a clip made at 30 a second loses nothing; a 60-a-second one loses its odd frames' bend", function()
			local t30, v30, t60, v60 = {}, {}, {}, {}
			for i = 0, 30 do
				table.insert(t30, i / 30)
				table.insert(v30, 40 * math.sin(i / 3))
			end
			for i = 0, 60 do
				table.insert(t60, i / 60)
				table.insert(v60, 40 * math.sin(i / 6))
			end
			check.equal(C.lost(t30, v30, C.lerpNumber, C.distNumber), 0)
			local lost = C.lost(t60, v60, C.lerpNumber, C.distNumber)
			-- the most an odd key lies off the line between its even neighbours: 40 (1 - cos(1/6)) at the crest
			check.truthy(near(lost, 40 * (1 - math.cos(1 / 6)), 0.02))
			-- a straight 60-a-second stretch loses nothing either: what is dropped is on the line
			local line = {}
			for i = 0, 60 do
				table.insert(line, i * 2)
			end
			check.truthy(near(C.lost(t60, line, C.lerpNumber, C.distNumber), 0))
			-- one spike on an odd frame is lost whole; the same spike on an even frame plays
			local odd, even = table.clone(line), table.clone(line)
			odd[12] += 9 -- key 12 = frame 11
			even[13] += 9 -- key 13 = frame 12
			check.truthy(near(C.lost(t60, odd, C.lerpNumber, C.distNumber), 9))
			check.truthy(near(C.lost(t60, even, C.lerpNumber, C.distNumber), 4.5)) -- (its odd neighbours sit off the line it bends)
		end)
		test.case("the loss is what the 30-a-second samples play, at any key rate", function()
			-- the engine as measured: the track's value at each grid moment, straight lines between them
			local function engine(times: { number }, values: { number }): number
				local function value(t: number): number
					for i = 2, #values do
						if t <= times[i] then
							return C.lerpNumber(
								values[i - 1],
								values[i],
								(t - times[i - 1]) / (times[i] - times[i - 1])
							)
						end
					end
					return values[#values]
				end
				local worst = 0
				for i = 1, #values do
					local g = times[i] * 30
					local lo, hi = math.floor(g) / 30, math.ceil(g) / 30
					local plays = C.lerpNumber(value(lo), value(hi), g - math.floor(g))
					worst = math.max(worst, math.abs(values[i] - plays))
				end
				return worst
			end
			for _, rate in { 24, 50, 60, 120 } do
				local t, v = {}, {}
				for i = 0, rate do
					table.insert(t, i / rate)
					table.insert(v, 40 * math.sin(i * 12 / rate) + 6 * math.sin(i * 47 / rate))
				end
				check.truthy(near(C.lost(t, v, C.lerpNumber, C.distNumber), engine(t, v), 1e-9))
			end
			-- a key squeezed between two frames of a 60-a-second clip (the first cut read 4 here: the engine plays 5 off)
			local t, v = {}, {}
			for i = 0, 12 do
				table.insert(t, i / 60)
				table.insert(v, 0)
			end
			table.insert(t, 3, 0.025)
			table.insert(v, 3, 10)
			check.truthy(near(C.lost(t, v, C.lerpNumber, C.distNumber), engine(t, v), 1e-9))
			check.truthy(C.lost(t, v, C.lerpNumber, C.distNumber) > 4.5)
			-- the last key counts too (a clip that ends on an odd frame)
			local t2, v2 = { 0, 1 / 60, 2 / 60, 3 / 60 }, { 0, 0, 0, 9 }
			check.truthy(C.lost(t2, v2, C.lerpNumber, C.distNumber) > 0)
		end)
		test.case("a long straight stretch keeps a key every RUN keys at least", function()
			local t, v = {}, {}
			for i = 0, 600 do
				table.insert(t, i / 60)
				table.insert(v, 0)
			end
			local calls = 0
			local kept = C.thin(t, v, 0.01, C.lerpNumber, function(a: number, b: number): number
				calls += 1
				return math.abs(a - b)
			end)
			check.truthy(#kept >= 600 / C.RUN and #kept <= 600 / C.RUN + 3)
			check.truthy(calls < 601 * C.RUN) -- (not 180,000: every key against every key since the last kept one)
			for k = 2, #kept do
				check.truthy(kept[k] - kept[k - 1] <= C.RUN)
			end
		end)
		test.case("the builder still carries the rule, the loss and the warning", function()
			local src = fs.readFile("src/kit/AnimCurve.luau")
			for _, line in
				{
					"AnimCurve.GRID = 30",
					"local turns = AnimCurve.thin(track.times, track.frames, rotTol, turnLerp, turnDist)",
					"local places = AnimCurve.thin(track.times, track.frames, posTol, placeLerp, placeDist)",
					"math.max(report.lostDeg, math.deg(AnimCurve.lost(track.times, track.frames, turnLerp, turnDist)))",
					"if report.lostDeg > math.deg(rotTol) or report.lostStuds > posTol then",
					"if pose.EasingStyle ~= Enum.PoseEasingStyle.Linear then",
					'curve.Name = sequence.Name .. "Curve"',
					"return math.min(angle, 2 * math.pi - angle)",
					"mc:InsertMarkerAtTime(k.Time, m.Value)",
				}
			do
				check.truthy(string.find(src, line, 1, true) ~= nil)
			end
			local anim = fs.readFile("src/kit/Anim.luau")
			check.truthy(string.find(anim, 'if seq:IsA("CurveAnimation") then', 1, true) ~= nil)
			check.truthy(
				string.find(anim, 'game:GetService("AnimationClipProvider"):RegisterAnimationClip(seq)', 1, true) ~= nil
			)
		end)
	end)
end

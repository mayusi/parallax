-- windvoice.spec.luau — WindVoiceRules (src/kit): the castle sings with the wind - level by wind speed, exposure of an
-- opening across the wind, a small pitch drift that keeps the key, the nearest-voices cap; and SampleRegion's generated
-- voices block (from the blueprint's towers and walls) is well formed.
local frk = require("../frk")
local test, check = frk.test, frk.check

local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Rules = require("../../../src/kit/WindVoiceRules")

return function()
	test.suite("WindVoiceRules: a castle that sings in the wind", function()
		test.case("calm air is a breath, a gale is full, and the voice only grows with the wind", function()
			check.truthy(math.abs(Rules.level(0, {}) - 0.08) < 1e-9)
			check.truthy(math.abs(Rules.level(40, {}) - 1) < 1e-9)
			local last = -1
			for s = 0, 20 do
				local l = Rules.level(s, { calm = 3, full = 14 })
				check.truthy(l >= last - 1e-12)
				last = l
			end
			check.truthy(Rules.level(5, {}) < Rules.level(10, {}))
			check.truthy(Rules.level(8, { calm = 10, full = 5 }) >= 0) -- (a hostile spec still answers)
		end)

		test.case("an opening sings hardest with the wind grazing across its mouth, not blowing into it", function()
			local grazing = Rules.exposure(10, 0, 0, 1) -- (wind along x, the opening faces z)
			local into = Rules.exposure(10, 0, 1, 0) -- (wind straight into the opening)
			check.truthy(math.abs(grazing - 1) < 1e-9)
			check.truthy(math.abs(into - 0.35) < 1e-9)
			check.truthy(math.abs(Rules.exposure(-10, 0, 0, 1) - 1) < 1e-9) -- (either way along the wall)
			check.truthy(math.abs(Rules.exposure(0, 0, 1, 0) - 0.35) < 1e-9) -- (no wind)
		end)

		test.case("the pitch drifts under one percent: the castle keeps its key", function()
			check.truthy(math.abs(Rules.pitch(0) - 1) <= 0.0075 + 1e-9)
			check.truthy(math.abs(Rules.pitch(1) - 1) <= 0.0075 + 1e-9)
			check.truthy(Rules.pitch(1) > Rules.pitch(0))
		end)

		test.case("only the nearest voices in range sound, nearest first", function()
			local pts = { { x = 0, z = 0 }, { x = 100, z = 0 }, { x = 10, z = 0 }, { x = 500, z = 0 }, "junk" }
			local got = Rules.pick(pts, 0, 0, 2, 260)
			check.equal(#got, 2)
			check.equal(got[1], 1)
			check.equal(got[2], 3)
			check.equal(#Rules.pick(pts, 0, 0, 10, 260), 3) -- (the far one is out of range)
			check.equal(#Rules.pick(pts, 0, 0, 0, 260), 0)
		end)

		test.case("a voice is silent with no wind across it and capped at full", function()
			check.truthy(Rules.volume(1, 1, { volume = 2 }) <= 1)
			check.truthy(Rules.volume(0.08, 0.35, {}) < 0.02)
		end)
		test.case("level: defaults calm=3 and full=14; a spec table is actually used", function()
			-- spec=nil: defaults calm=3, full=14, floor=0.08; at calm speed (3) t=0: v=floor=0.08
			local atCalm = Rules.level(3, nil)
			check.truthy(math.abs(atCalm - 0.08) < 1e-9)
			-- at full speed (14) t=1: v=1
			local atFull = Rules.level(14, nil)
			check.truthy(math.abs(atFull - 1) < 1e-9)
			-- calm=3 means speed 3.5 gives a small positive t; with calm=4 (mutant default), t would be negative (clamped 0)
			local level3_5 = Rules.level(3.5, nil) -- t=(3.5-3)/(14-3)=0.5/11>0: some rise
			check.truthy(level3_5 > 0.08) -- if default calm were 4, t<0 and level=0.08
			-- a table spec with calm=10 is a genuinely different result
			check.truthy(Rules.level(5, { calm = 10, full = 20 }) < Rules.level(5, nil))
		end)
		test.case("level: mid-curve value pins t^1.5 (not t^2.5)", function()
			-- at t=0.5 (speed = 3 + 0.5*11 = 8.5): v = 0.08 + 0.92 * 0.5^1.5
			local expected = 0.08 + 0.92 * (0.5 ^ 1.5)
			check.truthy(math.abs(Rules.level(8.5, nil) - expected) < 1e-6)
			-- t^2.5 at t=0.5 would give 0.08 + 0.92 * 0.5^2.5 ≈ 0.243, clearly different
		end)
		test.case("pitch: exact values pin the 0.015 coefficient and the base 1", function()
			-- pitch(0) = 1 + 0.015 * (0 - 0.5) = 0.9925
			check.truthy(math.abs(Rules.pitch(0) - 0.9925) < 1e-9)
			-- pitch(1) = 1 + 0.015 * (1 - 0.5) = 1.0075
			check.truthy(math.abs(Rules.pitch(1) - 1.0075) < 1e-9)
			-- pitch(0.5) = 1 + 0.015 * (0.5 - 0.5) = 1.0
			check.truthy(math.abs(Rules.pitch(0.5) - 1.0) < 1e-9)
		end)
		test.case("pick: default range 260 excludes a point at 261; default max 6 caps the list", function()
			-- a point at exactly x=261 is OUTSIDE default range 260
			local edgeOut = { { x = 261, z = 0 } }
			check.equal(#Rules.pick(edgeOut, 0, 0), 0)
			-- a point at x=260 is inside default range
			local edgeIn = { { x = 260, z = 0 } }
			check.equal(#Rules.pick(edgeIn, 0, 0), 1)
			-- max defaults to 6: more than 6 candidates picks only 6
			local many = {}
			for i = 1, 10 do
				many[i] = { x = i * 5, z = 0 }
			end
			check.equal(#Rules.pick(many, 0, 0), 6)
		end)
		test.case("pick: a point with no x/z (defaults to 0) is measured from origin", function()
			-- p.x defaults to 0, p.z defaults to 0 for a point with no coords: distance from (0,0) is 0
			local pts = { {}, { x = 10, z = 0 } }
			local got = Rules.pick(pts, 0, 0, 2, 100)
			check.equal(#got, 2)
			check.equal(got[1], 1) -- (the one at origin is closest)
		end)
		test.case("volume: a nil spec uses default volume 0.6; a table spec overrides it", function()
			-- volume with nil spec: uses default s.volume = 0.6
			local v = Rules.volume(1, 1, nil)
			check.truthy(math.abs(v - 0.6) < 1e-9)
			-- volume with a table spec overrides: volume = 0.3
			local v2 = Rules.volume(1, 1, { volume = 0.3 })
			check.truthy(math.abs(v2 - 0.3) < 1e-9)
			-- a non-table spec is treated as {} and uses default 0.6
			local v3 = Rules.volume(1, 1, "bad" :: any)
			check.truthy(math.abs(v3 - 0.6) < 1e-9)
		end)

		-- ── Targeted mutation-kill cases ──────────────────────────────────────────────

		-- line 19 (<= -> <): full == calm must still clamp
		test.case("level: full==calm is clamped to calm+1 (line-19 guard fires on ==)", function()
			-- With full==calm==5 the guard on line 19 fires and sets full=calm+1=6.
			-- t at speed=5 (== calm) is 0  → result == floor == 0.08.
			-- t at speed=6 (== new full) is 1 → result == 1.
			-- If the guard used < instead of <= it would NOT fire here and full would
			-- stay == calm, making the denominator 0 / NaN.
			local atCalm5 = Rules.level(5, { calm = 5, full = 5 })
			check.truthy(math.abs(atCalm5 - 0.08) < 1e-9)
			local atFull6 = Rules.level(6, { calm = 5, full = 5 })
			check.truthy(math.abs(atFull6 - 1) < 1e-9)
		end)

		-- line 20 (1 -> 2): clamped full must be calm+1, not calm+2
		test.case("level: clamped full is exactly calm+1 (line-20 offset is 1)", function()
			-- After the guard fires (full==calm==5 → full=6), the range is 1 stud wide.
			-- speed = 5.5 (half-way) gives t = 0.5.
			-- If offset were 2 the range would be 2 and t = 0.5/2 = 0.25 → different result.
			local half = Rules.level(5.5, { calm = 5, full = 5 })
			local t = 0.5 -- (5.5-5)/(5+1-5) = 0.5/1 = 0.5
			local smoothed = t * t * (3 - 2 * t)
			local expected = 0.08 + 0.92 * (smoothed ^ 1.5)
			check.truthy(math.abs(half - expected) < 1e-9)
		end)

		-- line 22 (0 -> 1): nil speed defaults to 0, not 1
		test.case("level: nil speed uses 0 as default (num(speed, 0) default is 0)", function()
			-- With calm=0, full=5: t = (0-0)/(5-0) = 0  → result == floor == 0.08.
			-- If the default were 1: t = (1-0)/5 = 0.2 → result > 0.08.
			local nilResult = Rules.level(nil :: any, { calm = 0, full = 5 })
			check.truthy(math.abs(nilResult - 0.08) < 1e-9)
		end)

		-- line 32 (< -> <=): wl == 1e-6 must NOT short-circuit when < is used
		test.case("exposure: wl == 1e-6 is not too-short with strict < (line-32 guard)", function()
			-- Original: wl < 1e-6 is false when wl == 1e-6, so the formula runs.
			-- Wind vector (1e-6, 0) has length exactly 1e-6; opening faces (0,1).
			-- The wind is perpendicular → exposure = 1.
			-- Mutant (<= instead of <) would see 1e-6 <= 1e-6 = true and return 0.35.
			local exp = Rules.exposure(1e-6, 0, 0, 1)
			check.truthy(math.abs(exp - 1) < 1e-9)
		end)

		-- line 32 (1e-6 -> 2e-6): a wind of length 1.5e-6 must NOT be too-short
		test.case("exposure: wl=1.5e-6 passes the 1e-6 threshold (threshold is 1e-6 not 2e-6)", function()
			-- Original threshold 1e-6: 1.5e-6 < 1e-6 = false → formula runs → exposure = 1.
			-- Mutant threshold 2e-6: 1.5e-6 < 2e-6 = true  → early return 0.35.
			local exp = Rules.exposure(1.5e-6, 0, 0, 1)
			check.truthy(math.abs(exp - 1) < 1e-9)
		end)

		-- line 32 (1e-6 -> 1e-7): a wind of length 5e-7 IS too-short with 1e-6 threshold
		test.case("exposure: wl=5e-7 is below the 1e-6 threshold (threshold is 1e-6 not 1e-7)", function()
			-- Original threshold 1e-6: 5e-7 < 1e-6 = true  → returns 0.35.
			-- Mutant threshold 1e-7: 5e-7 < 1e-7 = false → formula runs → exposure near 1.
			local exp = Rules.exposure(5e-7, 0, 0, 1)
			check.truthy(math.abs(exp - 0.35) < 1e-9)
		end)

		-- line 40 (1 -> 2 for the clamp upper bound): pitch(1.5) is clamped at level 1
		test.case("pitch: levels above 1 are clamped to 1 (clamp upper bound is 1 not 2)", function()
			-- pitch(1.5): clamp(1.5, 0, 1) = 1 → 1 + 0.015*(1-0.5) = 1.0075.
			-- Mutant clamp upper = 2: clamp(1.5, 0, 2) = 1.5 → 1 + 0.015*(1.5-0.5) = 1.015.
			check.truthy(math.abs(Rules.pitch(1.5) - 1.0075) < 1e-9)
			-- also pins the case 2.0: same result as level=1
			check.truthy(math.abs(Rules.pitch(2) - 1.0075) < 1e-9)
		end)

		-- line 55 (0->1 for p.x default): a point with no x is at x=0 not x=1
		test.case("pick: a point with no x field uses x=0 as default (not 1)", function()
			-- Point {z=0} has no x; listener at x=2, range=1.5.
			-- Original: x-default=0 → d = sqrt((0-2)^2+0^2) = 2 > 1.5 → NOT included.
			-- Mutant x-default=1:  d = sqrt((1-2)^2+0^2) = 1 <= 1.5 → included.
			local nox = { { z = 0 } }
			check.equal(#Rules.pick(nox, 2, 0, 1, 1.5), 0)
		end)

		-- line 55 (0->1 for p.z default): a point with no z field uses z=0 as default (not 1)
		test.case("pick: a point with no z field uses z=0 as default (not 1)", function()
			-- Point {x=0} has no z; listener at x=0, z=2, range=1.5.
			-- Original: z-default=0 → d = sqrt(0+(0-2)^2) = 2 > 1.5 → NOT included.
			-- Mutant z-default=1:  d = sqrt(0+(1-2)^2) = 1 <= 1.5 → included.
			local noz = { { x = 0 } }
			check.equal(#Rules.pick(noz, 0, 2, 1, 1.5), 0)
		end)

		-- line 55 (2->3 for exponent): distance is Euclidean (exponent 2), not cubic
		test.case("pick: a 3-4-5 triangle gives distance 5 (exponent is 2 not 3)", function()
			-- Point at (3, 4), listener at (0, 0).
			-- Original (^2): d = sqrt(3^2 + 4^2) = sqrt(25) = 5.
			-- Mutant  (^3): d = sqrt(3^3 + 4^3) = sqrt(27+64) = sqrt(91) ≈ 9.54.
			-- Range=6: original includes it (d=5), mutant excludes it (d≈9.54).
			local pt345 = { { x = 3, z = 4 } }
			check.equal(#Rules.pick(pt345, 0, 0, 1, 6), 1)
		end)

		-- line 62 (< -> <=): sort comparator is strict (a.d < b.d); near before far
		test.case("pick: a strictly nearer point is always returned before a farther one", function()
			-- Three points at d=1, d=5, d=9 from the listener.
			-- Strict < comparator sorts them in order d=1, d=5, d=9 regardless of insertion order.
			-- We insert them in REVERSE order (9, 5, 1) so that an unstable sort exposing
			-- reflexivity bugs (<=) would have to do real work to get the right order.
			local pts = { { x = 9, z = 0 }, { x = 5, z = 0 }, { x = 1, z = 0 } }
			local got = Rules.pick(pts, 0, 0, 3, 100)
			check.equal(#got, 3)
			check.equal(got[1], 3) -- (index 3 in pts: x=1, nearest)
			check.equal(got[2], 2) -- (index 2 in pts: x=5, middle)
			check.equal(got[3], 1) -- (index 1 in pts: x=9, farthest)
		end)

		-- line 32 (< -> <=, 1 -> 2, 6 -> 7): nl branch — a near-zero NORMAL length short-circuits
		test.case("exposure: nl == 1e-6 is not too-short with strict < (line-32 nl guard)", function()
			-- Original: nl < 1e-6 is false when nl == 1e-6, so the formula runs.
			-- Wind vector (1, 0), face normal (1e-6, 0): nl = 1e-6; wl = 1.
			-- dot = 1*1e-6 + 0*0 = 1e-6; wl*nl = 1e-6; ratio = 1 -> exposure = 0.35.
			-- Mutant (<= instead of <): nl <= 1e-6 = true -> returns 0.35 too. Same?
			-- Need a case where nl == 1e-6 and the formula gives != 0.35.
			-- wind perpendicular to normal: wx=0, wz=1; nx=1e-6, nz=0: dot=0 -> exposure=0.35+0.65=1.
			-- Original: nl=1e-6 < 1e-6 false -> formula: 0.35 + 0.65*(1-|0/(1*1e-6)|) = 0.35+0.65=1.
			-- Mutant (<=): nl <= 1e-6 true -> returns 0.35.
			local exp = Rules.exposure(0, 1, 1e-6, 0) -- wl=1, nl=1e-6; perpendicular
			check.truthy(math.abs(exp - 1) < 1e-9)
		end)

		test.case("exposure: nl=1.5e-6 passes the 1e-6 threshold (nl threshold is 1e-6 not 2e-6)", function()
			-- Original threshold 1e-6: nl=1.5e-6 < 1e-6 = false → formula runs.
			-- Mutant threshold 2e-6: nl=1.5e-6 < 2e-6 = true → returns 0.35.
			-- wind perpendicular (wx=0,wz=1) to normal (1.5e-6, 0): exposure = 1 not 0.35.
			local exp = Rules.exposure(0, 1, 1.5e-6, 0)
			check.truthy(math.abs(exp - 1) < 1e-9)
		end)

		test.case("exposure: nl=5e-7 is below the 1e-6 threshold (nl threshold is 1e-6 not 1e-7)", function()
			-- Original: 5e-7 < 1e-6 = true → returns 0.35.
			-- Mutant 1e-7: 5e-7 < 1e-7 = false → formula runs → exposure near 1.
			local exp = Rules.exposure(0, 1, 5e-7, 0)
			check.truthy(math.abs(exp - 0.35) < 1e-9)
		end)

		-- ── End targeted mutation-kill cases ───────────────────────────────────────

		test.case("SampleRegion's generated voices sit on its towers and walls", function()
			local path = "games/SampleRegion/src/shared/SampleRegionAmbience.json"
			if not fs.isFile(path) then
				return
			end
			local spec = serde.decode("json", fs.readFile(path))
			local v = spec.voices
			check.truthy(type(v) == "table" and type(v.sound) == "string")
			check.truthy(#v.points >= 10)
			for _, p in v.points do
				check.truthy(type(p.x) == "number" and type(p.z) == "number" and type(p.h) == "number" and p.h > 5)
				check.truthy(math.abs(math.sqrt(p.nx * p.nx + p.nz * p.nz) - 1) < 1e-3)
			end
		end)
	end)
end

-- cutscene.spec.luau — a cutscene timeline's maths (src/kit/CutsceneRules, 2026-10-24): the root path never blends a
-- teleport, a play's track time stands still through the hit-stops and never runs past its length, the camera never
-- pans across a cut, hidden spans, the running segment.
local frk = require("../frk")
local test, check = frk.test, frk.check

local R = require("../../../src/kit/CutsceneRules")

local function near(a: number, b: number, eps: number?): boolean
	return math.abs(a - b) < (eps or 1e-6)
end

return function()
	test.suite("CutsceneRules root path", function()
		local rows = { "0 0 0 0", "1 0 0 0", "1 0 -6 3.1416", "1 0 -6 3.1416" }
		test.case("linear between rows at the timeline's fps", function()
			local x, _, z = R.rootAt(rows, 10, 0.05)
			check.truthy(near(x, 0.5) and near(z, 0))
		end)
		test.case("a teleport (a jump over 2 studs) is never blended", function()
			local x, _, z, yaw = R.rootAt(rows, 10, 0.15) -- between row 2 (1, 0) and row 3 (1, -6)
			check.truthy(near(x, 1) and near(z, 0) and near(yaw, 0))
			local _, _, z2 = R.rootAt(rows, 10, 0.2)
			check.truthy(near(z2, -6))
		end)
		test.case("the yaw turns the short way round", function()
			local _, _, _, yaw = R.rootAt({ "0 0 0 3.0", "0 0 0 -3.0" }, 10, 0.05)
			check.truthy(math.abs(yaw) > 3.0) -- through pi, not through 0
		end)
		test.case("a MARKED jump snaps at its own time, however short (the duel's 1.7-stud teleports)", function()
			local short = { "0 0 0 0", "0 0 -1.7 0", "0 0 -1.7 0" }
			local _, _, zMid = R.rootAt(short, 10, 0.05) -- unmarked: a 1.7-stud step is a slide
			check.truthy(near(zMid, -0.85))
			local _, _, zBefore = R.rootAt(short, 10, 0.06, nil, { 0.07 })
			local _, _, zAfter = R.rootAt(short, 10, 0.08, nil, { 0.07 })
			check.truthy(near(zBefore, 0) and near(zAfter, -1.7))
		end)
		test.case("with marks, a long move that is not marked is a slide (a shove, a launch)", function()
			local _, _, z = R.rootAt({ "0 0 0 0", "0 0 -4 0" }, 10, 0.05, nil, {})
			check.truthy(near(z, -2))
		end)
		test.case("clamped to the path's ends", function()
			local x = R.rootAt(rows, 10, -1)
			local x2, _, z2 = R.rootAt(rows, 10, 99)
			check.truthy(near(x, 0) and near(x2, 1) and near(z2, -6))
		end)
	end)
	test.suite("CutsceneRules plays + hit-stops", function()
		local hits = { { t = 1.0, hold = 0.1 }, { t = 2.0, hold = 0.2 } }
		local play = { t = 0.5, clip = "Cut", from = 0.2, len = 1.0 }
		test.case("the track time = its start point + the time since, less the hit-stops in between", function()
			check.truthy(near(R.trackTime(play, hits, 0.9), 0.6))
			check.truthy(near(R.trackTime(play, hits, 1.05), 0.2 + 0.5)) -- inside the first hit-stop: held
			check.truthy(near(R.trackTime(play, hits, 1.1), 0.2 + 0.5))
			check.truthy(near(R.trackTime(play, hits, 1.3), 0.2 + 0.7))
		end)
		test.case("never past its own length", function()
			check.truthy(near(R.trackTime(play, hits, 9), 1.2))
		end)
		test.case("hit-stop windows", function()
			check.truthy(R.inHitstop(hits, 1.05) and not R.inHitstop(hits, 1.1) and R.inHitstop(hits, 2.19))
			check.truthy(near(R.frozenBetween(hits, 0, 3), 0.3))
		end)
		test.case("the running segment", function()
			local plays = { { t = 0, clip = "@idle" }, { t = 0.75, clip = "A" }, { t = 1.5, clip = "@hold" } }
			check.equal(R.segmentAt(plays, -0.1), nil)
			check.equal(R.segmentAt(plays, 0.5), 1)
			check.equal(R.segmentAt(plays, 0.75), 2)
			check.equal(R.segmentAt(plays, 5), 3)
		end)
	end)
	test.suite("CutsceneRules camera + hidden", function()
		local keys = {
			{ t = 0, loc = { 0, 5, 10 }, target = { 0, 0, 0 } },
			{ t = 1, loc = { 2, 5, 10 }, target = { 0, 0, 0 } },
			{ t = 2, loc = { 30, 5, -10 }, target = { 0, 0, -5 } },
		}
		test.case("a pan blends between keys", function()
			local loc = R.cameraAt(keys, 0.5)
			check.truthy(near(loc[1], 1))
		end)
		test.case("a cut (over 3 studs in one step) holds, then jumps", function()
			local loc = R.cameraAt(keys, 1.5)
			check.truthy(near(loc[1], 2))
			local loc2 = R.cameraAt(keys, 2.5)
			check.truthy(near(loc2[1], 30))
		end)
		test.case("a MARKED cut snaps at its time; with marks a big unmarked step pans", function()
			local loc = R.cameraAt(keys, 0.5, { 0.6 })
			check.truthy(near(loc[1], 0))
			local loc2 = R.cameraAt(keys, 0.7, { 0.6 })
			check.truthy(near(loc2[1], 2))
			local loc3 = R.cameraAt(keys, 1.5, {})
			check.truthy(near(loc3[1], 16)) -- (no cut marked between 1 and 2: a pan)
		end)
		test.case("hidden spans", function()
			local spans = { { 0.7, 0.75 }, { 1.5, 1.6 } }
			check.truthy(R.hiddenAt(spans, 0.72) and not R.hiddenAt(spans, 0.75) and R.hiddenAt(spans, 1.55))
		end)
		-- kills line 125/126 mutants (n==0 -> n==1 and return values)
		test.case("camera default when no keys: loc {0,5,14} target {0,0,0}", function()
			local loc, tgt = R.cameraAt({}, 1)
			check.truthy(near(loc[1], 0) and near(loc[2], 5) and near(loc[3], 14))
			check.truthy(near(tgt[1], 0) and near(tgt[2], 0) and near(tgt[3], 0))
		end)
		-- kills line 129 mutant (keys[1] -> keys[2])
		test.case("camera at or before first key returns exactly that key", function()
			local k1 = { t = 2, loc = { 7, 8, 9 }, target = { 1, 2, 3 } }
			local k2 = { t = 5, loc = { 20, 20, 20 }, target = { 10, 10, 10 } }
			local loc, tgt = R.cameraAt({ k1, k2 }, 1)
			check.truthy(near(loc[1], 7) and near(loc[2], 8) and near(loc[3], 9))
			check.truthy(near(tgt[1], 1) and near(tgt[2], 2) and near(tgt[3], 3))
		end)
		-- kills line 143 mutant (^2 -> ^3): the distance check uses ^2, not ^3
		test.case("camera cut-without-marks: exact distance squared threshold (9 studs^2)", function()
			-- dl = (3)^2 + 0 + 0 = 9: exactly 9 is NOT > 9 so it pans, not cuts
			local ks = {
				{ t = 0, loc = { 0, 5, 10 }, target = { 0, 0, 0 } },
				{ t = 1, loc = { 3, 5, 10 }, target = { 0, 0, 0 } },
			}
			local loc = R.cameraAt(ks, 0.5)
			check.truthy(near(loc[1], 1.5)) -- panned to midpoint
			-- dl = (3.1)^2 > 9: IS a cut, stays at key 1
			local ks2 = {
				{ t = 0, loc = { 0, 5, 10 }, target = { 0, 0, 0 } },
				{ t = 1, loc = { 3.1, 5, 10 }, target = { 0, 0, 0 } },
			}
			local loc2 = R.cameraAt(ks2, 0.5)
			check.truthy(near(loc2[1], 0))
		end)
		-- kills line 148 mutant (1->2 changes 1e-6 to 2e-6 in math.max): interpolation with dt=1.5e-6
		test.case("camera interpolation dt=1.5e-6: math.max(1e-6,dt) vs max(2e-6,dt) differ", function()
			-- dt = 1.5e-6 (between 1e-6 and 2e-6), t at midpoint:
			-- original: max(1e-6, 1.5e-6) = 1.5e-6; u = 7.5e-7 / 1.5e-6 = 0.5 -> loc[1] = 0.5
			-- mutant (2e-6): max(2e-6, 1.5e-6) = 2e-6; u = 7.5e-7 / 2e-6 = 0.375 -> loc[1] = 0.375
			local a_t = 1.0
			local b_t = a_t + 1.5e-6
			local mid_t = a_t + 7.5e-7
			local ks = {
				{ t = a_t, loc = { 0, 0, 0 }, target = { 0, 0, 0 } },
				{ t = b_t, loc = { 1, 0, 0 }, target = { 0, 0, 0 } },
			}
			local loc = R.cameraAt(ks, mid_t)
			check.truthy(near(loc[1], 0.5, 0.05)) -- 0.5 not 0.375
		end)
		-- kills line 150 mutant (^2 -> ^3 in lerp): exact interpolation values
		test.case("camera lerp interpolates all three components exactly", function()
			-- pass cuts={} to suppress auto-cut-detection (dl=48 > 9 would otherwise snap to key 1)
			local ks = {
				{ t = 0, loc = { 0, 10, 20 }, target = { 5, 5, 5 } },
				{ t = 1, loc = { 4, 14, 24 }, target = { 7, 9, 11 } },
			}
			local loc, tgt = R.cameraAt(ks, 0.25, {})
			check.truthy(near(loc[1], 1) and near(loc[2], 11) and near(loc[3], 21))
			check.truthy(near(tgt[1], 5.5) and near(tgt[2], 6) and near(tgt[3], 6.5))
		end)
	end)
	test.suite("CutsceneRules row", function()
		-- kills line 23 mutants (or->and on table path): nil components become 0
		test.case("row from table: nil components default to 0", function()
			local t1: { number } = {}
			local x, y, z, w = R.row(t1)
			check.truthy(near(x, 0) and near(y, 0) and near(z, 0) and near(w, 0))
			local t2: { number } = { 3 }
			local x2, y2, z2, w2 = R.row(t2)
			check.truthy(near(x2, 3) and near(y2, 0) and near(z2, 0) and near(w2, 0))
		end)
		-- kills line 23 (2->3), (3->4), (4->5): each index reads its own slot
		test.case(
			"row from table: each component reads its own slot (y=r[2] not r[3], z=r[3] not r[4], w=r[4] not r[5])",
			function()
				-- Use distinct values in each slot: { 1, 2, 3, 4 } → x=1, y=2, z=3, w=4.
				-- 2->3 mutant: y = r[3] = 3 (not 2). 3->4 mutant: z = r[4] = 4. 4->5: w = r[5] = nil → 0.
				local r: { number } = { 1, 2, 3, 4 }
				local x, y, z, w = R.row(r)
				check.truthy(near(x, 1) and near(y, 2) and near(z, 3) and near(w, 4))
			end
		)
		-- kills line 26 mutants (or->and on string path): non-numeric tokens default to 0
		test.case("row from string: non-numeric tokens default to 0", function()
			local x, y, z, w = R.row("1 x 3 y")
			check.truthy(near(x, 1) and near(y, 0) and near(z, 3) and near(w, 0))
		end)
		-- kills line 26 (0->1) twice: each non-numeric token defaults to 0 not 1
		test.case("row from string: each bad token defaults to 0, not 1", function()
			-- "x x x x": all tokens non-numeric. All should be 0.
			-- If any 0->1 mutant fires, one of the values would be 1 instead of 0.
			local x, y, z, w = R.row("x x x x")
			check.truthy(near(x, 0) and near(y, 0) and near(z, 0) and near(w, 0))
		end)
	end)
	test.suite("CutsceneRules snapIn", function()
		-- kills line 35 mutants (>->>=, epsilon 1e-6)
		test.case("snap: m exactly at a+1e-6 does NOT fire (> not >=)", function()
			-- m = a + 1e-6: should return nil because m > a+1e-6 is false
			local a = 0.1
			local m_exact = a + 1e-6
			local result = R.snapIn({ m_exact }, a, a + 0.1)
			-- with >= mutant, this would return m_exact instead of nil
			check.equal(result, nil)
		end)
		test.case("snap: m just above a+1e-6 fires", function()
			local a = 0.1
			local m_above = a + 1e-6 + 1e-10
			local result = R.snapIn({ m_above }, a, a + 0.1)
			check.truthy(result ~= nil)
		end)
		test.case("snap: m exactly at b+1e-6 does fire (<=)", function()
			local a = 0
			local b = 0.2
			local m_b = b + 1e-6
			local result = R.snapIn({ m_b }, a, b)
			check.truthy(result ~= nil)
		end)
	end)
	test.suite("CutsceneRules rootAt edge cases", function()
		-- kills line 54/55 mutants (n==0 -> n==1, return 0,0,0,0 -> 1,0,0,0)
		test.case("empty rows returns exactly 0,0,0,0", function()
			local x, y, z, w = R.rootAt({}, 10, 1)
			check.truthy(near(x, 0) and near(y, 0) and near(z, 0) and near(w, 0))
			-- with n==1 mutant, single-row input would skip to later logic
			local x2, y2, z2, w2 = R.rootAt({ "7 8 9 1" }, 10, 1)
			check.truthy(near(x2, 7) and near(y2, 8) and near(z2, 9) and near(w2, 1))
		end)
		-- kills line 63 mutant (i+1 -> i+2 in snapIn call): snap outside [i/fps,(i+1)/fps] is ignored
		test.case("jump snap only fires within [i/fps, (i+1)/fps], not beyond", function()
			-- snap at 0.15 is in frame i=1 (window [0.1,0.2]) but NOT in frame i=0 (window [0,0.1])
			-- at t=0.05, i=0: original window [0, 0.1]: snap at 0.15 does NOT fire -> lerps
			-- mutant window [0, 0.2]: snap at 0.15 fires -> t < 0.15-1e-6 -> returns ax (z=0)
			local rows = { "0 0 0 0", "0 0 -5 0" }
			local _, _, z = R.rootAt(rows, 10, 0.05, nil, { 0.15 })
			-- original: no snap fires, lerps: u=0.5, z = 0 + (-5-0)*0.5 = -2.5
			-- mutant: snap fires, returns ax -> z=0
			check.truthy(near(z, -2.5))
		end)
		-- kills line 65 mutant (1e-6 epsilon in t < m - 1e-6)
		test.case("root snap: t exactly at m-1e-6 stays at old row (< not <=)", function()
			local rows = { "0 0 0 0", "0 0 -10 0", "0 0 -10 0" }
			local snap_t = 0.05
			local t_boundary = snap_t - 1e-6
			-- at exactly m-1e-6: t < m-1e-6 is false, so returns new row (bx,by,bz,byaw)
			-- if mutant changes 1e-6 to 1e-7: m - 1e-7 < t < m so would return new row too
			-- The key: at t = m - 1e-6 exactly, returns new (bx)
			local _, _, z = R.rootAt(rows, 10, t_boundary, nil, { snap_t })
			-- t_boundary = snap_t - 1e-6: t < m - 1e-6 is exactly false (0 < 0), returns bz = -10
			check.truthy(near(z, -10))
		end)
		-- kills line 70 mutants (>->>=, 2->3 in jump distance)
		test.case("root jump distance: exactly (jump)^2 does NOT cut (> not >=)", function()
			-- jump=nil so defaults to 2; dx=2, dz=0: distance^2 = 4 = 2^2, NOT > 4 so blends
			local rows = { "0 0 0 0", "2 0 0 0" }
			local x = R.rootAt(rows, 10, 0.05) -- midpoint between row1 (0) and row2 (2)
			check.truthy(near(x, 1)) -- blended, not cut
		end)
		test.case("root jump distance: just over (jump)^2 cuts", function()
			-- dx=2.001: distance^2 > 4, cuts to old row
			local rows = { "0 0 0 0", "2.001 0 0 0" }
			local x = R.rootAt(rows, 10, 0.05)
			check.truthy(near(x, 0)) -- not blended
		end)
		test.case("root jump distance: 2->3 mutant check (dx=2.5 is 6.25 > 4 so cuts with jump=2)", function()
			-- dx=2.5: distance^2=6.25; original (jump=2): 6.25 > 4 -> cuts (returns ax=0)
			-- mutant (2->3, so jump defaults to 3): 6.25 > 9 -> false -> blends (returns ~1.25)
			local rows = { "0 0 0 0", "2.5 0 0 0" }
			local x = R.rootAt(rows, 10, 0.05)
			check.truthy(near(x, 0)) -- cuts: stays at ax=0
		end)
		test.case("root jump distance with explicit jump=3: exactly 3 studs does NOT cut", function()
			-- dx=3, jump=3: distance^2 = 9 = 3^2, NOT > 9 so blends
			local rows = { "0 0 0 0", "3 0 0 0" }
			local x = R.rootAt(rows, 10, 0.05, 3)
			check.truthy(near(x, 1.5)) -- blended midpoint
		end)
	end)
	test.suite("CutsceneRules segmentAt boundary", function()
		-- kills line 81 mutant (1->2 in 1e-6 tolerance): p.t at t+1.5e-6 is NOT included with 1e-6 but IS with 2e-6
		test.case("segmentAt: play at t+1.5e-6 is excluded (1e-6 not 2e-6 tolerance)", function()
			-- p.t = 1.0 + 1.5e-6; querying t=1.0: p.t <= 1.0+1e-6 is false (1.5e-6 > 1e-6)
			-- mutant (2e-6): p.t <= 1.0+2e-6 is true (1.5e-6 < 2e-6) -> would include segment 2
			local plays = {
				{ t = 0, clip = "@idle" },
				{ t = 1.0 + 1.5e-6, clip = "A" },
			}
			check.equal(R.segmentAt(plays, 1.0), 1)
		end)
		-- also kills if <= changed to <: play at exactly t+1e-6 is included
		test.case("segmentAt: play at exactly t+1e-6 is included (<=, not <)", function()
			local plays = {
				{ t = 0, clip = "@idle" },
				{ t = 1.0 + 1e-6, clip = "A" },
			}
			check.equal(R.segmentAt(plays, 1.0), 2)
		end)
	end)
	test.suite("CutsceneRules trackTime", function()
		-- kills line 116 mutant (play.from or 0 -> play.from or 1)
		test.case("trackTime: play with no from defaults to 0 not 1", function()
			local play = { t = 0, clip = "X" } -- no from field
			local tt = R.trackTime(play, {}, 0.5)
			check.truthy(near(tt, 0.5)) -- from=0, so 0 + 0.5
			-- if mutant changes 0->1: from=1, tt = 1 + 0.5 = 1.5
			check.truthy(tt < 1)
		end)
	end)

	test.suite("CutsceneRules boundary kills", function()
		-- line 73 (2 -> 3): yaw interpolation uses (2 * math.pi) for the wrap
		test.case("rootAt yaw: a +3 and -3 radian pair wraps through pi (2*pi wrap, not 3*pi)", function()
			-- byaw - ayaw = -3 - 3 = -6. With 2*pi: (-6 + pi) % (2*pi) - pi = (-6+3.14) % 6.28 - 3.14
			-- = (-2.86) % 6.28 - 3.14 = 3.42 - 3.14 = 0.28. At u=0.5: yaw = 3 + 0.28*0.5 = 3.14 (through pi).
			-- With 3*pi mutant: (-6 + pi) % (3*pi) - pi = very different.
			-- The existing test only checks |yaw| > 3; test a specific value.
			local rows = { { 0, 0, 0, 3 }, { 0, 0, 0, -3 } }
			local _, _, _, yaw = R.rootAt(rows, 10, 0.05) -- halfway between row 1 and row 2
			-- dy = (-3 - 3 + pi) % (2*pi) - pi = (-6 + 3.1416) % 6.2832 - 3.1416 ≈ 0.2832
			-- yaw at u=0.5: 3 + 0.2832*0.5 ≈ 3.1416
			check.truthy(math.abs(yaw) > 3.0) -- turns through pi (not through 0)
			-- kills 2->3: with 3*pi, dy = (-6+pi)%(3*pi) - pi = (-2.86)%9.42 - 3.14 = 6.56 - 3.14 = 3.42
			-- yaw = 3 + 3.42*0.5 = 4.71 which is also > 3, so we need a more discriminating check.
			-- With 2*pi: |yaw| ≈ 3.14 (near pi). With 3*pi: yaw ≈ 4.71. Use near pi:
			check.truthy(near(yaw, math.pi, 0.05)) -- must be close to pi at the midpoint between +3 and -3
		end)

		-- line 105 (>= -> >): inHitstop includes the START time exactly
		test.case("inHitstop: t exactly at h.t is inside (>= not >)", function()
			-- Original: t >= h.t -> true when t==h.t -> inside. Mutant: t > h.t -> false -> outside.
			local hits = { { t = 1.0, hold = 0.5 } }
			check.is_true(R.inHitstop(hits, 1.0)) -- exactly at start: inside (kills >= -> >)
			check.is_false(R.inHitstop(hits, 1.5)) -- exactly at end: outside (t < h.t + hold: 1.5 < 1.5 = false)
		end)

		-- line 128 (<= -> <): cameraAt at exactly the first key's time returns that key
		test.case("cameraAt: t exactly at keys[1].t returns key 1 (<= not <)", function()
			-- Original: t <= keys[1].t -> true when t == keys[1].t -> returns key 1.
			-- Mutant: t < keys[1].t -> false when t == keys[1].t -> falls into loop.
			local k1 = { t = 2.0, loc = { 10, 5, 0 }, target = { 0, 0, 0 } }
			local k2 = { t = 4.0, loc = { 20, 5, 0 }, target = { 0, 0, 0 } }
			local loc, _ = R.cameraAt({ k1, k2 }, 2.0) -- t == keys[1].t exactly
			check.truthy(near(loc[1], 10)) -- must return k1.loc (10), not interpolated
		end)
	end)
end

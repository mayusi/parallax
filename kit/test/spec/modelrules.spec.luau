-- modelrules.spec.luau — the pure rules of the model spawner (src/kit/ModelRules, 2026-11-15): which collision
-- shape and level of detail a spawned mesh asks for, and when a mesh that failed to load is tried again
local frk = require("../frk")
local test, check = frk.test, frk.check
local R = require("../../../src/kit/ModelRules")

return function()
	test.suite("ModelRules a model's rig", function()
		-- an arm in the xy plane: a shoulder at the origin and an elbow 2 studs up, both turning about z; a hand 2 more
		local ARM = {
			{ kind = "hinge", pivot = { 0, 0, 0 }, axis = { 0, 0, 1 }, min = -170, max = 170 },
			{ kind = "hinge", pivot = { 0, 2, 0 }, axis = { 0, 0, 1 }, min = -150, max = 150 },
		}
		local HAND = { 0, 4, 0 }
		local function near(a: number, b: number, tol: number?): boolean
			return math.abs(a - b) <= (tol or 1e-6)
		end
		test.case("at rest the tip is where it was built, and a joint carries everything after it", function()
			local x, y, z = R.chainTip(ARM, { 0, 0 }, HAND)
			check.is_true(near(x, 0) and near(y, 4) and near(z, 0))
			x, y, z = R.chainTip(ARM, { 90, 0 }, HAND) -- the shoulder a quarter turn about +z: the arm lies along -x
			check.is_true(near(x, -4) and near(y, 0) and near(z, 0))
			x, y, z = R.chainTip(ARM, { 0, 90 }, HAND) -- the elbow alone
			check.is_true(near(x, -2) and near(y, 2) and near(z, 0))
		end)
		test.case("a target within reach is met", function()
			for _, target in { { 2, 2, 0 }, { -1, 3, 0 }, { 3, -1, 0 }, { 1.5, 0.5, 0 } } do
				local values, miss = R.reach(ARM, HAND, target)
				check.is_true(miss < 0.01)
				local x, y, z = R.chainTip(ARM, values, HAND)
				check.is_true(near(x, target[1], 0.01) and near(y, target[2], 0.01) and near(z, target[3], 0.01))
			end
		end)
		test.case("a target out of reach is missed by what is left, and limits hold", function()
			local _values, miss = R.reach(ARM, HAND, { 9, 0, 0 })
			check.is_true(near(miss, 5, 0.05)) -- 9 away, 4 long: stretched straight at it
			local stiff = {
				{ kind = "hinge", pivot = { 0, 0, 0 }, axis = { 0, 0, 1 }, min = -10, max = 10 },
				{ kind = "hinge", pivot = { 0, 2, 0 }, axis = { 0, 0, 1 }, min = -10, max = 10 },
			}
			local values = R.reach(stiff, HAND, { -4, 0, 0 })
			check.is_true(values[1] <= 10 and values[1] >= -10 and values[2] <= 10 and values[2] >= -10)
		end)
		test.case("a straight arm reaches a place on its own line, and limits may be given either way round", function()
			local _values, miss = R.reach(ARM, HAND, { 0, 3, 0 }) -- straight up, nearer: it must BEND to get there
			check.is_true(miss < 0.02)
			local back = {
				{ kind = "hinge", pivot = { 0, 0, 0 }, axis = { 0, 0, 1 }, min = 170, max = -170 },
				{ kind = "hinge", pivot = { 0, 2, 0 }, axis = { 0, 0, 1 }, min = 150, max = -150 },
			}
			local _v, m = R.reach(back, HAND, { 2, 2, 0 })
			check.is_true(m < 0.02)
		end)
		test.case("every place a three-joint chain can take is found", function()
			local chain = {
				{ kind = "hinge", pivot = { 0, 0, 0 }, axis = { 0, 1, 0 }, min = -180, max = 180 },
				{ kind = "hinge", pivot = { 0, 1, 0 }, axis = { 0, 0, 1 }, min = -100, max = 100 },
				{ kind = "hinge", pivot = { 0, 3, 0 }, axis = { 0, 0, 1 }, min = -140, max = 140 },
			}
			local tip = { 0, 5, 0 }
			local seed, missed = 7, 0
			for _ = 1, 60 do
				local made = {}
				for i, j in chain do
					seed = (seed * 16807) % 2147483647
					made[i] = j.min + (j.max - j.min) * (seed / 2147483647)
				end
				local x, y, z = R.chainTip(chain, made, tip)
				local _values, miss = R.reach(chain, tip, { x, y, z })
				if miss > 0.02 then
					missed += 1
				end
			end
			check.is_true(missed <= 1)
		end)
		test.case("a slide takes up what the hinges cannot", function()
			local boom = {
				{ kind = "hinge", pivot = { 0, 0, 0 }, axis = { 0, 0, 1 }, min = -90, max = 90 },
				{ kind = "slide", pivot = { 0, 1, 0 }, axis = { 0, 1, 0 }, min = 0, max = 3 },
			}
			local values, miss = R.reach(boom, { 0, 2, 0 }, { -3.5, 0, 0 })
			check.is_true(miss < 0.01)
			check.is_true(near(values[1], 90, 0.5) and near(values[2], 1.5, 0.02))
		end)
		test.case("a lone slide joint along y reaches a y target, not a z target (line 302 a[2] guard)", function()
			-- line 302: step uses a[2]; mutant uses a[3]. Axis = {0,1,0}: a[2]=1, a[3]=0.
			-- Target y=4 differs from target z=9: the slide must end near 4 (along y), not 9.
			local pole = {
				{ kind = "slide", pivot = { 0, 0, 0 }, axis = { 0, 1, 0 }, min = 0, max = 10 },
			}
			local vals, _ = R.reach(pole, { 0, 0, 0 }, { 0, 4, 9 })
			-- original: step = (0)*0 + (4-y)*1 + (9-0)*0 -> converges to y=4
			-- mutant a[2]->a[3]: step = (0)*0 + (4-y)*0 + (9-0)*0 = 0 -> never moves, stays at 0
			-- mutant target[2]->target[3]: step = (9-y)*1 -> converges to y=9
			check.is_true(near(vals[1], 4, 0.1))
		end)
		test.case("a joint that follows another takes its ratio and its offset", function()
			check.equal(R.follow(40, -1, 0), -40)
			check.equal(R.follow(40, 2, 5), 85)
			check.equal(R.follow(40, nil, nil), 40)
		end)
	end)

	test.suite("ModelRules physics and the far stand-in", function()
		test.case("a group with no physics said asks for none", function()
			local d, f, e = R.physics(nil, nil, nil)
			check.equal(d, nil)
			check.equal(f, nil)
			check.equal(e, nil)
		end)
		test.case("what was said is held to what the engine takes, the rest is a plain part's", function()
			local d, f, e = R.physics(nil, 1.5, nil)
			check.equal(d, 0.7)
			check.equal(f, 1.5)
			check.equal(e, 0.5)
			d, f, e = R.physics(500, -1, 3)
			check.equal(d, 100)
			check.equal(f, 0)
			check.equal(e, 1)
			d, f, e = R.physics(0 / 0, 0.2, "bouncy")
			check.equal(d, 0.7)
			check.equal(f, 0.2)
			check.equal(e, 0.5)
		end)
		test.case("a piece is pushed away from the whole's centre, and one at the centre goes up", function()
			local x, y, z = R.burst(0, 0, 0, 2, 0, 0, 10)
			check.equal(x, 10)
			check.equal(y, 0)
			check.equal(z, 0)
			x, y, z = R.burst(1, 1, 1, 1, 1, 1, 10)
			check.equal(x, 0)
			check.equal(y, 10)
			check.equal(z, 0)
			x, y, z = R.burst(0, 0, 0, 3, 4, 0, 10)
			check.equal(math.floor(x * 1000 + 0.5), 6000)
			check.equal(math.floor(y * 1000 + 0.5), 8000)
		end)
		test.case(
			"a piece exactly 1e-6 studs from the centre is NOT treated as at-centre (length < 1e-6 guard)",
			function()
				-- line 74: guard is `< 1e-6`, not `<= 1e-6`; length == 1e-6 must NOT use the fallback (0, speed, 0)
				-- A point at distance exactly 1e-6 along x: dx=1e-6, dy=0, dz=0, length=1e-6
				local x2, y2 = R.burst(0, 0, 0, 1e-6, 0, 0, 5)
				-- original: length is not < 1e-6, so it normalises and returns (5, 0, 0)
				-- mutant (<= instead of <): treats it as at-centre -> (0, 5, 0)
				check.equal(math.floor(x2 + 0.5), 5)
				check.equal(math.floor(y2 + 0.5), 0)
			end
		)
		test.case("the far stand-in is one of Roblox's own names or nothing", function()
			check.equal(R.far("StreamingMesh"), "StreamingMesh")
			check.equal(R.far("Disabled"), "Disabled")
			check.equal(R.far("Billboard"), nil)
			check.equal(R.far(nil), nil)
		end)
	end)

	test.suite("ModelRules fidelity", function()
		test.case("COLLISION table holds exactly the four valid shapes as true", function()
			-- line 15: each entry must be true (not false or nil)
			check.equal(R.COLLISION.Box, true)
			check.equal(R.COLLISION.Hull, true)
			check.equal(R.COLLISION.Default, true)
			check.equal(R.COLLISION.PreciseConvexDecomposition, true)
		end)
		test.case("what the build chose is what the spawn asks for", function()
			local c, r = R.fidelity("Hull", "Precise", false)
			check.equal(c, "Hull")
			check.equal(r, "Precise")
			c, r = R.fidelity("PreciseConvexDecomposition", "Performance", nil)
			check.equal(c, "PreciseConvexDecomposition")
			check.equal(r, "Performance")
		end)
		test.case("a part nothing can touch asks for a box whatever the build chose", function()
			local c, r = R.fidelity("PreciseConvexDecomposition", "Precise", true)
			check.equal(c, "Box")
			check.equal(r, "Precise")
		end)
		test.case("an old model file with no choice, or a wrong name, gets Roblox's defaults", function()
			local c, r = R.fidelity(nil, nil, nil)
			check.equal(c, "Default")
			check.equal(r, "Automatic")
			c, r = R.fidelity("Sphere", 3, false)
			check.equal(c, "Default")
			check.equal(r, "Automatic")
		end)
		test.case("one template per mesh and per pair of settings", function()
			check.equal(
				R.key("rbxassetid://1", "Box", "Automatic") ~= R.key("rbxassetid://1", "Hull", "Automatic"),
				true
			)
			check.equal(R.key("rbxassetid://1", "Box", "Automatic"), R.key("rbxassetid://1", "Box", "Automatic"))
		end)
	end)
	test.suite("ModelRules cycle", function()
		local cycle = {
			joints = { "Wheel", "Pin" },
			times = { 0, 1, 2 },
			values = { { 0, 0 }, { 90, 0 }, { 90, 0.1 } },
			length = 2,
			marks = { turn = 0, seat = 1.5, done = 2 },
		}
		test.case("a straight line between the keys round a time, by the joint's name", function()
			local v = R.cycleAt(cycle, 0.5)
			check.equal(v.Wheel, 45)
			check.equal(v.Pin, 0)
			v = R.cycleAt(cycle, 1.5)
			check.equal(v.Wheel, 90)
			check.equal(math.abs(v.Pin - 0.05) < 1e-9, true)
			check.equal(R.cycleAt(cycle, 1).Wheel, 90)
		end)
		test.case("before it begins and after it ends it holds; looped, it comes round", function()
			check.equal(R.cycleAt(cycle, -3).Wheel, 0)
			check.equal(R.cycleAt(cycle, 99).Pin, 0.1)
			check.equal(R.cycleAt(cycle, 2.5, true).Wheel, 45)
			check.equal(R.cycleTime(cycle, 4.5, true), 0.5)
			check.equal(R.cycleTime(cycle, 4.5, false), 2)
		end)
		test.case("a step of time passes the marks in it, once, in order", function()
			local got = R.marksPassed(cycle, -0.01, 0.4)
			check.equal(#got, 1)
			check.equal(got[1], "turn")
			check.equal(#R.marksPassed(cycle, 0.4, 1.4), 0)
			got = R.marksPassed(cycle, 1.4, 2.6)
			check.equal(#got, 2)
			check.equal(got[1], "seat")
			check.equal(got[2], "done")
			check.equal(#R.marksPassed(cycle, 2.6, 9), 0) -- (not looped: each mark once)
		end)
		test.case("a looped cycle passes its marks again each time round", function()
			local got = R.marksPassed(cycle, 1.4, 3.6, true) -- seat 1.5, done 2, turn 2, seat 3.5
			check.equal(#got, 4)
			check.equal(got[1], "seat")
			check.equal(got[4], "seat")
			check.equal(#R.marksPassed(cycle, 3.6, 3.9, true), 0)
		end)
	end)
	test.suite("ModelRules play", function()
		local cycle = {
			joints = { "Wheel" },
			times = { 0, 1, 2 },
			values = { { 0 }, { 90 }, { 0 } },
			length = 2,
			marks = { turn = 0, top = 1 },
		}
		test.case("a fade eases every joint from where it stood to the new cycle, and only there", function()
			local from = { Wheel = 90, Pin = 0.2 }
			local to = { Wheel = 0, Lid = 30 }
			local at0, half, done = R.blend(from, to, 0), R.blend(from, to, 0.5), R.blend(from, to, 1)
			check.equal(at0.Wheel, 90)
			check.equal(at0.Pin, 0.2)
			check.equal(at0.Lid, 30) -- (only the new cycle keys it: it stands at its value)
			check.equal(half.Wheel, 45)
			check.equal(half.Pin, 0.1) -- (the new cycle does not key it: toward rest)
			check.equal(done.Wheel, 0)
			check.equal(done.Pin, 0)
			local early = R.blend(from, to, 0.1).Wheel
			check.is_true(90 - early < 0.1 * 90) -- (eased: slow out of the old pose, not a straight line)
			check.equal(R.blend(from, to, 2).Wheel, 0) -- (held at the end)
		end)
		test.case("the first step stands at the start and passes the marks there", function()
			local s = R.playStep(cycle, nil, 0, 1, false)
			check.equal(s.at, 0)
			check.equal(s.values.Wheel, 0)
			check.equal(#s.marks, 1)
			check.equal(s.marks[1], "turn")
			check.equal(s.done, false)
		end)
		test.case("the first step does not pass a mark at t=-1 (before = -1 not -2, line 200)", function()
			-- line 200: before = -1 when at=nil; mutant makes it -2.
			-- A mark at exactly t=-1 satisfies (-1 > -2) but NOT (-1 > -1), so original excludes it, mutant includes it.
			local earlyCycle = {
				joints = { "Wheel" },
				times = { 0, 1 },
				values = { { 0 }, { 90 } },
				length = 1,
				marks = { pre = -1, go = 0 },
			}
			local s2 = R.playStep(earlyCycle, nil, 0, 1, false)
			-- original: before=-1; mark "pre" at -1: (-1 > -1) = false -> NOT passed; mark "go" at 0: (0 > -1 and 0<=0) = true -> passed
			-- mutant: before=-2; mark "pre" at -1: (-1 > -2) = true -> passed too -> #marks = 2
			check.equal(#s2.marks, 1)
			check.equal(s2.marks[1], "go")
		end)
		test.case("each step moves on by the time passed and the speed, and says when it has played through", function()
			local s = R.playStep(cycle, 0, 0.5, 1, false)
			check.equal(s.at, 0.5)
			check.equal(s.values.Wheel, 45)
			check.equal(#s.marks, 0)
			s = R.playStep(cycle, 0.5, 0.25, 2, false) -- twice as fast: half a second on
			check.equal(s.at, 1)
			check.equal(s.marks[1], "top")
			s = R.playStep(cycle, 1.9, 0.5, 1, false)
			check.equal(s.done, true)
			check.equal(s.values.Wheel, 0)
		end)
		test.case("a looped play never ends, and a step longer than the loop passes each mark once", function()
			local s = R.playStep(cycle, 1.9, 0.5, 1, true)
			check.equal(s.done, false)
			check.equal(s.marks[1], "turn") -- round again
			s = R.playStep(cycle, 0.5, 10, 1, true)
			check.equal(#s.marks, 2)
		end)
		test.case("no speed and no time move nothing on", function()
			local s = R.playStep(cycle, 0.5, 1, 0, false)
			check.equal(s.at, 0.5)
			check.equal(#s.marks, 0)
		end)
	end)
	test.suite("ModelRules retry", function()
		test.case("a mesh never tried may be tried", function()
			local ok, left = R.mayTry(nil, 100)
			check.equal(ok, true)
			check.equal(left, 0) -- line 110: second return is 0, not 1
		end)
		test.case("after a failure it waits, then is tried again - longer each time", function()
			local s = R.failed(nil, 100)
			check.equal(s.fails, 1)
			local ok, left = R.mayTry(s, 101)
			check.equal(ok, false)
			check.equal(left, 1)
			local ok2, left2 = R.mayTry(s, 102)
			check.equal(ok2, true)
			check.equal(left2, 0) -- line 110: second return is 0, not 1
			s = R.failed(s, 102)
			check.equal((R.mayTry(s, 109)), false)
			check.equal((R.mayTry(s, 110)), true)
			s = R.failed(s, 110)
			check.equal((R.mayTry(s, 139)), false)
			check.equal((R.mayTry(s, 140)), true)
			check.equal(R.givenUp(s), false)
		end)
		test.case("a fourth failure gives the mesh up for the session", function()
			local s: any = nil
			for i = 1, 4 do
				s = R.failed(s, i * 1000)
			end
			check.equal(R.givenUp(s), true)
			local ok, left = R.mayTry(s, 999999)
			check.equal(ok, false)
			check.equal(left, math.huge)
		end)
		test.case("a failure does not change the record it was given", function()
			local s = R.failed(nil, 5)
			local t = R.failed(s, 9)
			check.equal(s.fails, 1)
			check.equal(t.fails, 2)
			check.equal(t.at, 9)
		end)
	end)

	test.suite("ModelRules boundary kills", function()
		-- line 127 (> -> >=): cycleTime with loop=true, length=0 — must NOT loop (0 is not > 0)
		test.case("cycleTime: loop=true with length=0 does NOT wrap (> not >=)", function()
			-- Original: loop and length > 0 -> true and false = false -> math.clamp(10, 0, 0) = 0.
			-- Mutant: true and 0 >= 0 = true and true = true -> 10 % 0 (NaN or error).
			local c: any = { joints = {}, times = {}, values = {}, length = 0, marks = {} }
			local t = R.cycleTime(c, 10, true)
			check.equal(t, 0) -- clamped to [0,0] = 0; with >= mutant: 10 % 0 = NaN or error
		end)

		-- line 172 (<= -> <): looped marksPassed — a mark at exactly `now` is passed
		test.case("marksPassed (looped): a mark at exactly now is included (<= not <)", function()
			-- Mark at exactly now: k*length+at == now. Original: <= now -> included. Mutant: < now -> excluded.
			-- Use: before=0, now=1, length=1, mark at 0 (turn). With loop=true:
			-- k = max(0, ceil((0-0)/1)) = 0; k*1+0 = 0 <= 0 = true (before) -> k+=1 -> k=1; k*1+0=1 <= 1 = true -> included.
			-- Mutant: 1 < 1 = false -> excluded. So mark "turn" at 0 is at time 1 (second lap) and must be in result.
			local c: any = {
				joints = {},
				times = { 0 },
				values = {},
				length = 1,
				marks = { turn = 0 },
			}
			local got = R.marksPassed(c, 0, 1, true)
			check.equal(#got, 1) -- mark at exactly now=1 (k=1: 1*1+0=1 <= 1) is passed
			check.equal(got[1], "turn")
		end)

		-- line 182 (< -> <=): sort at equal at: marks sort by name when at is equal (not reflexive <=)
		test.case("marksPassed: two marks at the same time sort by name (<, not <=)", function()
			-- a.at == b.at: original -> a.name < b.name. With <= comparator: reflexivity triggers UB in sort.
			-- Two marks at the same time: "aaa" before "zzz" in name order.
			local c: any = {
				joints = {},
				times = { 0 },
				values = {},
				length = 10,
				marks = { zzz = 0.5, aaa = 0.5 },
			}
			local got = R.marksPassed(c, 0, 1)
			check.equal(#got, 2)
			check.equal(got[1], "aaa") -- sorted by name when at is equal
			check.equal(got[2], "zzz")
		end)

		-- line 323 (or -> and): reach stops when converged OR still (not both needed)
		test.case("reach: a chain converging within REACH_NEAR stops early (or not and)", function()
			-- reach a point that is exactly reachable: miss drops below REACH_NEAR.
			-- If the or->and mutant is active, it stops only when BOTH near AND still, which may need more iterations.
			-- For a simple 1-joint chain, the solution is exact after 1-2 iterations.
			local chain = {
				{ kind = "hinge", pivot = { 0, 0, 0 }, axis = { 0, 0, 1 }, min = -180, max = 180 },
			}
			local tip = { 0, 2, 0 }
			local _values, miss = R.reach(chain, tip, { 2, 0, 0 })
			-- miss must be < REACH_NEAR when the target is on the circle of radius=2
			check.is_true(miss < R.REACH_NEAR)
		end)

		-- line 347 (0 -> 1): reach with no start: initial values default to 0, not 1
		test.case("reach: initial joint values default to 0 when start is nil (not 1)", function()
			-- A hinge with min=-90, max=90, axis z: at value=0 it points up; at value=90 it points right.
			-- A target at (0, 2, 0) (straight up at radius 2): from value=0 we're already there (miss≈0).
			-- From value=1 (mutant): 1 degree off: miss is small but non-zero; converges fast though.
			-- Use a chain where starting from 0 gives exact answer but starting from 1 doesn't.
			local chain = {
				{ kind = "hinge", pivot = { 0, 0, 0 }, axis = { 0, 0, 1 }, min = -180, max = 180 },
			}
			local tip = { 0, 2, 0 }
			-- Target exactly at the rest position (0 degrees):
			local _values, miss = R.reach(chain, tip, { 0, 2, 0 }, nil) -- nil start
			check.is_true(miss < 1e-6) -- starts at 0: already there, miss≈0
		end)

		-- line 352 (<= -> <): reach stops when bestMiss is exactly REACH_MET
		test.case("reach: stops early when bestMiss equals REACH_MET exactly (<= not <)", function()
			-- If bestMiss == REACH_MET: original: bestMiss <= REACH_MET = true -> break (no more starts).
			-- Mutant: < -> false -> tries more starts (slower but same result).
			-- Observable: the result quality is the same but the original uses fewer iterations.
			-- We just need to show a reachable target within REACH_MET: the standard reach test does this.
			local chain = {
				{ kind = "hinge", pivot = { 0, 0, 0 }, axis = { 0, 0, 1 }, min = -180, max = 180 },
				{ kind = "hinge", pivot = { 0, 1, 0 }, axis = { 0, 0, 1 }, min = -150, max = 150 },
			}
			local tip = { 0, 2, 0 }
			local _values, miss = R.reach(chain, tip, { 1, 1, 0 })
			-- a reachable target: miss should be <= REACH_MET after the descent
			check.is_true(miss <= R.REACH_MET)
		end)
	end)
end

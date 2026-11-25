-- animstance.spec.luau — FOOT PLACEMENT WITH CONTACT STATE (the owner's limitations list, 2026-11-15, A-R03): which
-- foot is planted, in its swing or unsupported; the ground a flat sole stands on (the support's normal); only planted
-- feet carry the pelvis; the pelvis's lean; a planted foot led by a moving support (src/kit/AnimRules stance /
-- stanceStep, called by src/kit/Anim.feet). Numbers only: slopes, steps, edges and moving platforms under a real
-- body are Studio's to show.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local R = require("../../../src/kit/AnimRules")

local function near(a: number, b: number, eps: number?): boolean
	return math.abs(a - b) <= (eps or 1e-9)
end
-- a foot: the ground's height under it, how far the clip lifts it, and (optionally) the ground's slope in degrees
-- rising AHEAD (+) and its speed
local function foot(height: number, lifted: number?, riseAhead: number?, vy: number?): R.Sample
	local a = math.rad(riseAhead or 0)
	return { height = height, lifted = lifted or 0, nx = 0, ny = math.cos(a), nz = math.sin(a), vy = vy }
end
local NONE = 0 / 0

return function()
	test.suite("foot placement with contact state: one foot", function()
		test.case("a flat sole stands on the highest ground under it", function()
			local h, slope = R.soleGround(foot(0.2))
			check.truthy(near(h, 0.2) and near(slope, 0))
			-- 30 degrees: half a stud of sole reaches 0.5 * tan(30) higher at its uphill edge
			local h30, s30 = R.soleGround(foot(0.2, 0, 30))
			check.truthy(near(h30, 0.2 + 0.5 * math.tan(math.rad(30)), 1e-9) and near(s30, 30, 1e-9))
			-- the same whichever way the ground leans
			local side = R.soleGround({
				height = 0,
				lifted = 0,
				nx = math.sin(math.rad(30)),
				ny = math.cos(math.rad(30)),
				nz = 0,
			})
			check.truthy(near(side, 0.5 * math.tan(math.rad(30)), 1e-9))
			local small = R.soleGround(foot(0, 0, 30), 0.25) -- its own sole
			check.truthy(near(small, 0.25 * math.tan(math.rad(30)), 1e-9))
			-- no normal given: flat
			check.truthy(near((R.soleGround({ height = 0.4, lifted = 0 })), 0.4))
			-- no ground; a wall
			local none, noSlope = R.soleGround(foot(NONE))
			check.truthy(none ~= none and noSlope ~= noSlope)
			local _, wall = R.soleGround({ height = 0, lifted = 0, nx = 1, ny = 0, nz = 0 })
			check.equal(wall, 90)
		end)
		test.case("planted when the clip has it down, in its swing when the clip lifts it", function()
			check.equal(R.footState(nil, foot(0, 0)), "planted")
			check.equal(R.footState(nil, foot(0, 0.15)), "planted")
			check.equal(R.footState(nil, foot(0, 0.16)), "swing")
			check.equal(R.footState(nil, foot(0, 2)), "swing")
			check.equal(R.footState(nil, foot(0, -0.05)), "planted") -- (the clip dips it a little under its floor)
			check.equal(R.footState(nil, foot(0, 0 / 0)), "planted") -- (a lift that is not a number is no lift)
			-- its own band
			check.equal(R.footState(nil, foot(0, 0.2), { contact = 0.3 }), "planted")
		end)
		test.case(
			"a planted foot stays planted until the clip lifts it twice the band: no flicker at the edge",
			function()
				check.equal(R.footState("planted", foot(0, 0.2)), "planted")
				check.equal(R.footState("planted", foot(0, 0.3)), "planted")
				check.equal(R.footState("planted", foot(0, 0.31)), "swing")
				check.equal(R.footState("unsupported", foot(0, 0.2)), "planted")
				check.equal(R.footState("swing", foot(0, 0.2)), "swing") -- (coming down, it plants at the band itself)
				check.equal(R.footState("swing", foot(0, 0.15)), "planted")
			end
		)
		test.case("planted by the clip with nothing to stand on is unsupported", function()
			check.equal(R.footState(nil, foot(NONE, 0)), "unsupported") -- an edge: no ground under it
			check.equal(R.footState(nil, foot(0, 0, 51)), "unsupported") -- too steep to stand on
			check.equal(R.footState(nil, foot(0, 0, 50)), "planted")
			check.equal(R.footState(nil, foot(0, 0, 60), { slope = 70 }), "planted")
			check.equal(R.footState(nil, foot(-1.31, 0)), "unsupported") -- further down than the body can go
			check.equal(R.footState(nil, foot(-1.3, 0)), "planted")
			check.equal(R.footState(nil, { height = 0, lifted = 0, nx = 1, ny = 0, nz = 0 }), "unsupported") -- a wall
			-- a swinging foot is in its swing whatever is under it
			check.equal(R.footState(nil, foot(NONE, 1)), "swing")
		end)
	end)

	test.suite("foot placement with contact state: a step under the toe", function()
		test.case("a sole stands on the highest ground under its toe, middle or heel", function()
			-- crossing the edge of a 0.6-stud step: the middle is still over the low ground, the toe over the step
			local crossing: R.Sample = { height = 0, lifted = 0, more = { 0.6, 0 } }
			check.truthy(near((R.soleGround(crossing)), 0.6)) -- (read at the middle only this was 0: the toe went in)
			local s = R.stance(crossing, foot(0))
			check.truthy(s.stateLeft == "planted" and near(s.left, 0.6) and near(s.pelvis, 0))
			-- stepping DOWN off it: the heel is still on the step, the foot stays up until the heel is off
			local leaving: R.Sample = { height = 0, lifted = 0, more = { 0, 0.6 } }
			check.truthy(near((R.soleGround(leaving)), 0.6))
			-- lower ground under the toe does not pull a foot down that stands on its middle
			check.truthy(near((R.soleGround({ height = 0.3, lifted = 0, more = { -0.5, 0.3 } })), 0.3))
			-- no samples, or samples that found nothing: the middle's own
			check.truthy(near((R.soleGround({ height = 0.3, lifted = 0, more = {} })), 0.3))
			check.truthy(near((R.soleGround({ height = 0.3, lifted = 0, more = { 0 / 0, 0 / 0 } })), 0.3))
		end)
		test.case("a wall in front of the foot is not ground: a point a leg cannot step onto does not count", function()
			local wall: R.Sample = { height = 0, lifted = 0, more = { 3, 0 } } -- the toe's ray lands on a 3-stud ledge
			check.truthy(near((R.soleGround(wall)), 0))
			check.truthy(near((R.soleGround({ height = 0, lifted = 0, more = { R.LIFT, 0 } })), R.LIFT)) -- as high as a leg lifts
			check.truthy(near((R.soleGround({ height = 0, lifted = 0, more = { R.LIFT + 0.01, 0 } })), 0))
		end)
		test.case(
			"a toe or a heel on ground too steep to stand on does not count; the limits are the game's own",
			function()
				-- the toe's ray lands on a 60-degree rock 0.78 up: not ground a sole stands on
				local rock: R.Sample = { height = 0, lifted = 0, more = { 0.78, 0 }, moreSlope = { 60, 0 } }
				check.truthy(near((R.soleGround(rock)), 0))
				check.truthy(
					near((R.soleGround({ height = 0, lifted = 0, more = { 0.78, 0 }, moreSlope = { 40, 0 } })), 0.78)
				)
				check.truthy(near((R.soleGround(rock, nil, { slope = 70 })), 0.78)) -- (a game that says steeper is fine)
				-- nothing under the middle, the heel on a 70-degree face: no support
				local cliff: R.Sample = { height = 0 / 0, lifted = 0, more = { 0 / 0, 0 }, moreSlope = { 0, 70 } }
				check.truthy((R.soleGround(cliff)) ~= (R.soleGround(cliff)))
				check.equal(R.footState(nil, cliff), "unsupported")
				-- a leg that lifts less takes a lower step only; a body that drops less reaches less far down for a heel
				local step: R.Sample = { height = 0, lifted = 0, more = { 0.6, 0 } }
				check.truthy(near((R.soleGround(step, nil, { lift = 0.5 })), 0))
				local low: R.Sample = { height = 0 / 0, lifted = 0, more = { 0 / 0, -1.2 } }
				check.truthy(near((R.soleGround(low)), -1.2))
				check.truthy((R.soleGround(low, nil, { drop = 0.5 })) ~= (R.soleGround(low, nil, { drop = 0.5 })))
				-- on a plain ramp the slope's raise and the toe's height are one thing: the higher, never both added
				local ramp = foot(0, 0, 30)
				ramp.more = { 0.26, -0.26 }
				check.truthy(near((R.soleGround(ramp)), 0.5 * math.tan(math.rad(30)), 1e-9))
			end
		)
		test.case("a foot the toe already lifted is not led again when its middle crosses the edge", function()
			-- the sole's ground is 0.6 before and after the middle crosses (toe first, then the middle): no speed
			local before: R.Sample = { height = 0, lifted = 0, more = { 0.6, 0 } }
			local after: R.Sample = { height = 0.6, lifted = 0, more = { 0.6, 0 } }
			check.equal(R.groundRate((R.soleGround(before)), (R.soleGround(after)), 1 / 30), 0)
			-- (fed the MIDDLE's height it read 18 studs a second: a half-stud overshoot above ground that never moved)
			check.truthy(near(R.groundRate(before.height, after.height, 1 / 30), 18, 1e-9))
		end)
		test.case("a foot half over an edge stands on what its heel still has", function()
			local edge: R.Sample = { height = 0 / 0, lifted = 0, more = { 0 / 0, 0 } } -- nothing under the middle or the toe
			local ground, slope = R.soleGround(edge)
			check.truthy(near(ground, 0) and slope == 0)
			check.equal(R.footState(nil, edge), "planted") -- (it was "unsupported": the leg hung while the heel stood)
			-- nothing under any of it: no ground
			local none = R.soleGround({ height = 0 / 0, lifted = 0, more = { 0 / 0, 0 / 0 } })
			check.truthy(none ~= none)
			check.equal(R.footState(nil, { height = 0 / 0, lifted = 0, more = { 0 / 0, 0 / 0 } }), "unsupported")
			-- a heel sample far below the body's reach is no ground either
			local deep = R.soleGround({ height = 0 / 0, lifted = 0, more = { 0 / 0, -5 } })
			check.truthy(deep ~= deep)
		end)
	end)

	test.suite("foot placement with contact state: both feet", function()
		test.case("both planted on flat ground: the first rule's own answer", function()
			for _, pair in { { 0, 0 }, { 0.5, 0 }, { 0, -0.6 }, { -0.4, -0.9 }, { 1.5, 0 }, { 0.3, 0.3 } } do
				local old = R.feet(pair[1], pair[2])
				local new = R.stance(foot(pair[1]), foot(pair[2]))
				check.truthy(near(new.pelvis, old.pelvis) and near(new.left, old.left) and near(new.right, old.right))
				check.truthy(near(new.shortLeft, old.shortLeft) and near(new.shortRight, old.shortRight))
				check.truthy(
					new.stateLeft == "planted" and new.stateRight == "planted" and new.pitch == 0 and new.roll == 0
				)
			end
		end)
		test.case("a foot swinging over a hole does not pull the body down", function()
			-- the first rule drops the pelvis 0.7 for the hole under the lifted foot
			check.truthy(near(R.feet(0, -1).pelvis, -0.7))
			local s = R.stance(foot(0), foot(-1, 0.8))
			check.equal(s.stateRight, "swing")
			check.truthy(near(s.pelvis, 0) and near(s.left, 0))
			check.truthy(near(s.right, -R.REACH)) -- (the swinging leg still follows its own ground as far as it reaches)
			-- and a swinging foot over a STEP is lifted over it
			local up = R.stance(foot(0), foot(0.6, 0.8))
			check.truthy(near(up.pelvis, 0) and near(up.right, 0.6))
		end)
		test.case("a foot past an edge hangs as the clip has it; the other carries the body", function()
			local s = R.stance(foot(-0.5), foot(NONE))
			check.truthy(s.stateLeft == "planted" and s.stateRight == "unsupported")
			check.truthy(near(s.pelvis, -0.2) and near(s.left, -0.3) and s.right == 0 and s.shortRight == 0)
			-- neither foot has ground it can stand on: the clip's own pose
			local none = R.stance(foot(NONE), foot(0, 0, 80))
			check.truthy(none.pelvis == 0 and none.left == 0 and none.right == 0)
			-- both in their swing (the clip jumps): the pelvis stays
			local air = R.stance(foot(-0.8, 1), foot(-0.8, 1))
			check.truthy(air.pelvis == 0 and near(air.left, -0.3) and near(air.right, -0.3))
		end)
		test.case("on a slope each sole stands on the highest ground under it", function()
			local rise = 0.5 * math.tan(math.rad(20))
			local s = R.stance(foot(0.2, 0, 20), foot(-0.2, 0, 20))
			-- the lower foot: -0.2 + rise = -0.018 -> the pelvis drops for what that leg cannot reach (nothing: reach 0.3)
			check.truthy(near(s.pelvis, 0))
			check.truthy(near(s.left, 0.2 + rise, 1e-9) and near(s.right, -0.2 + rise, 1e-9))
			check.truthy(s.pitch == 0 and s.roll == 0) -- (no lean unless asked)
		end)
		test.case(
			"the pelvis leans with the ground of the planted feet only when asked, never past its limit",
			function()
				local lim = { tilt = 8 }
				local up = R.stance(foot(0, 0, 5), foot(0, 0, 5), nil, nil, lim) -- the ground rises 5 degrees ahead
				check.truthy(near(up.pitch, math.rad(5), 1e-9) and near(up.roll, 0, 1e-9)) -- it leans back with it
				local steep = R.stance(foot(0, 0, 30), foot(0, 0, 30), nil, nil, lim)
				check.truthy(near(steep.pitch, math.rad(8), 1e-9))
				local down = R.stance(foot(0, 0, -30), foot(0, 0, -30), nil, nil, lim)
				check.truthy(near(down.pitch, -math.rad(8), 1e-9))
				-- the ground rises to the body's right (+X): the normal leans to -X, the body leans to its left
				local a = math.rad(4)
				local side: R.Sample = { height = 0, lifted = 0, nx = -math.sin(a), ny = math.cos(a), nz = 0 }
				local rolled = R.stance(side, side, nil, nil, lim)
				check.truthy(near(rolled.roll, a, 1e-9) and near(rolled.pitch, 0, 1e-9))
				-- a swinging or unsupported foot's ground does not count
				local one = R.stance(foot(0, 0, 6), foot(0, 1, -40), nil, nil, lim)
				check.truthy(near(one.pitch, math.rad(6), 1e-9))
				local nobody = R.stance(foot(0, 1, 6), foot(NONE, 0), nil, nil, lim)
				check.truthy(nobody.pitch == 0 and nobody.roll == 0)
			end
		)
		test.case("the states carry over between frames", function()
			local first = R.stance(foot(0, 0.1), foot(0, 0.25))
			check.truthy(first.stateLeft == "planted" and first.stateRight == "swing")
			local second = R.stance(foot(0, 0.25), foot(0, 0.25), first.stateLeft, first.stateRight)
			check.truthy(second.stateLeft == "planted" and second.stateRight == "swing") -- the same lift, two states
		end)
	end)

	test.suite("foot placement with contact state: one frame of it", function()
		test.case("a planted foot follows its ground faster than a swinging one, and nothing snaps", function()
			local l, r = foot(0.5), foot(0.5, 1)
			local want = R.stance(l, r)
			local one = R.stanceStep({ 0, 0, 0, 0, 0 }, want, l, r, 1 / 60)
			check.truthy(near(one[2], 0.5 * (1 - math.exp(-R.PLANTED_RATE / 60)), 1e-9))
			check.truthy(near(one[3], 0.5 * (1 - math.exp(-12 / 60)), 1e-9))
			check.truthy(one[2] > one[3] and one[2] < 0.5)
			local cur = { 0, 0, 0, 0, 0 }
			for _ = 1, 120 do
				cur = R.stanceStep(cur, want, l, r, 1 / 60)
			end
			check.truthy(near(cur[2], 0.5, 1e-3) and near(cur[3], 0.5, 1e-3))
			-- its own rates; a planted rate under the other is raised to it
			local own = R.stanceStep({ 0, 0, 0, 0, 0 }, want, l, r, 1 / 60, 6, 60)
			check.truthy(
				near(own[2], 0.5 * (1 - math.exp(-1)), 1e-9) and near(own[3], 0.5 * (1 - math.exp(-0.1)), 1e-9)
			)
			local low = R.stanceStep({ 0, 0, 0, 0, 0 }, want, l, r, 1 / 60, 20, 5)
			check.truthy(near(low[2], low[3], 1e-12))
		end)
		test.case("no time passed, or a time that is not a number: nothing moves", function()
			local l, r = foot(0.5), foot(-0.5)
			local want = R.stance(l, r)
			for _, dt in { 0, -1, 0 / 0 } do
				local held = R.stanceStep({ 0.1, 0.2, 0.3, 0.01, 0.02 }, want, l, r, dt)
				check.truthy(
					held[1] == 0.1 and held[2] == 0.2 and held[3] == 0.3 and held[4] == 0.01 and held[5] == 0.02
				)
			end
		end)
		test.case("a planted foot MEETS a support that rises under it; a swinging one is not led", function()
			-- the ground under the left foot rises 3 studs a second: followed frame after frame, the foot settles ON
			-- it (an eased follower with no lead trails a moving target by speed / rate: 0.1 studs sunk in here)
			local function settle(lead: boolean): number
				local cur, h = { 0, 0, 0, 0, 0 }, 0
				local last: number? = nil
				for _ = 1, 240 do
					h += 3 / 60
					local l: R.Sample =
						{ height = h, lifted = 0, vy = if lead then R.groundRate(last, h, 1 / 60) else 0 }
					local r: R.Sample = { height = 0, lifted = 2 } -- (the other foot swings: the pelvis is the left's)
					last = h
					cur = R.stanceStep(cur, R.stance(l, r, "planted", "swing", { lift = 100 }), l, r, 1 / 60)
				end
				return h - cur[2] -- how far the foot is under its ground
			end
			check.truthy(math.abs(settle(true)) < 0.03)
			check.truthy(settle(false) > 0.07) -- (what the lead is for: 0.077 sunk in without it)
			-- a lead is bounded (a number gone wild does not throw the leg)
			local r0: R.Sample = { height = 0, lifted = 0 }
			local wild: R.Sample = { height = 0, lifted = 0, vy = 1e6 }
			local w = R.stanceStep({ 0, 0, 0, 0, 0 }, R.stance(wild, r0), wild, r0, 1 / 60)
			check.truthy(w[2] <= 0.5 and w[2] > 0)
			-- in its swing the same ground leads nothing
			local sw: R.Sample = { height = 0, lifted = 1, vy = 3 }
			check.equal(R.stanceStep({ 0, 0, 0, 0, 0 }, R.stance(sw, r0), sw, r0, 1 / 60)[2], 0)
		end)
		test.case("how fast a foot's ground moves is read off its own height, never off the body's speed", function()
			check.truthy(near(R.groundRate(0.2, 0.25, 1 / 60), 3, 1e-9)) -- it rose 0.05 in a frame
			check.truthy(near(R.groundRate(0.25, 0.2, 1 / 60), -3, 1e-9))
			-- a body climbing a ramp, landing or riding a lift: the height under a planted foot (measured against the
			-- body's own floor) does not change, so nothing is led - whatever the body's own speed is
			check.equal(R.groundRate(0.1, 0.1, 1 / 60), 0)
			-- the first look after a swing or the air, a look with no ground, no time: nothing to go by
			check.equal(R.groundRate(nil, 0.3, 1 / 60), 0)
			check.equal(R.groundRate(0 / 0, 0.3, 1 / 60), 0)
			check.equal(R.groundRate(0.3, 0 / 0, 1 / 60), 0)
			check.equal(R.groundRate(0.3, 0.4, 0), 0)
			-- a height that JUMPS (the foot crossed a step's edge) is not a speed
			check.equal(R.groundRate(0, 0.6, 1 / 60), 0)
			check.truthy(near(R.groundRate(0, 0.6, 1 / 60, 100), 36, 1e-9)) -- (its own bound)
		end)
		test.case(
			"a square sole stands on its uphill CORNER; a foot swinging past a wall keeps the clip's own",
			function()
				-- a slope that falls away diagonally: the corner is further uphill than the edge's middle
				local a = math.rad(20)
				local d = math.sin(a) / math.sqrt(2)
				local diag = R.soleGround({ height = 0, lifted = 0, nx = d, ny = math.cos(a), nz = d })
				check.truthy(near(diag, 0.5 * math.tan(a) * math.sqrt(2), 1e-9))
				-- the raise never asks for more than a leg can lift
				local steep = R.soleGround({ height = 0, lifted = 0, nx = 0, ny = 0.05, nz = math.sqrt(1 - 0.0025) })
				check.truthy(near(steep, R.LIFT))
				-- a swinging foot over ground too steep to stand on is not lifted for it
				local s = R.stance(foot(0), foot(0.4, 1, 70))
				check.truthy(s.stateRight == "swing" and s.right == 0 and s.shortRight == 0)
			end
		)
		test.case("the lean eases too", function()
			local l = foot(0, 0, 6)
			local want = R.stance(l, l, nil, nil, { tilt = 8 })
			local one = R.stanceStep({ 0, 0, 0, 0, 0 }, want, l, l, 1 / 60)
			check.truthy(one[4] > 0 and one[4] < math.rad(6) and one[5] == 0)
		end)
	end)

	test.suite("foot placement with contact state: the game calls the rule", function()
		test.case("Anim.feet samples each foot's ground, normal, speed and lift, and keeps the states", function()
			local anim = fs.readFile("src/kit/Anim.luau")
			for _, line in
				{
					"local want = AnimRules.stance(sl, sr, stateL, stateR, o.limits)",
					"stateL, stateR = want.stateLeft, want.stateRight",
					"cur = AnimRules.stanceStep(cur, want, sl, sr, waited, o.rate, o.plantedRate)",
					"local n = root.CFrame:VectorToObjectSpace(hit.Normal)",
					"sl.vy = AnimRules.groundRate(lastL, groundL, waited)",
					'lastL = if stateL == "planted" then groundL else nil',
					"out.more, out.moreSlope = more, slopes",
					"- (leg.Size.X / 2) * math.abs(leg.CFrame.RightVector.Y)",
					"lifted = low - floorY - slide",
					"for _, at in { sole + ahead, sole - ahead } do",
					"(if i == 1 then lean else lean:Inverse())",
					"if o.contact == false then",
				}
			do
				check.truthy(string.find(anim, line, 1, true) ~= nil)
			end
		end)
	end)
end

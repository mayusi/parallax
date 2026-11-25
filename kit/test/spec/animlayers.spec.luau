-- animlayers.spec.luau — the runtime layers' maths (src/kit/AnimLayers, AAA gaps v2 waves 3/4): inertialization
-- decays to exactly 0 without overshoot, warping scales/turns only inside its window, reaction sides, tracking,
-- the camera kick and the secondary spring settle.
local frk = require("../frk")
local test, check = frk.test, frk.check

local L = require("../../../src/kit/AnimLayers")

return function()
	test.suite("AnimLayers inertialization (D1)", function()
		test.case("starts at the offset, ends at 0, never crosses it", function()
			check.truthy(math.abs(L.inertial(0.5, 0, 0.2, 0) - 0.5) < 1e-9)
			check.equal(L.inertial(0.5, 0, 0.2, 0.2), 0)
			local prev = 0.5
			for i = 1, 40 do
				local y = L.inertial(0.5, -1, 0.2, i * 0.005)
				check.truthy(y >= -1e-9 and y <= prev + 1e-9) -- monotone toward 0, no overshoot
				prev = y
			end
			check.truthy(L.inertial(-0.3, 0, 0.2, 0.1) < 0 and L.inertial(-0.3, 0, 0.2, 0.1) > -0.3)
		end)
		-- V3 anim stage F.1: the blend started still (v0 = 0) whatever the old clip was doing
		test.case(
			"the offset's own speed: read a frame apart along its axis, a gap or a teleport is no speed",
			function()
				-- a joint turned 0.5 rad off the new pose, 0.52 a frame (1/60 s) before: closing at 1.2 rad/s
				check.truthy(math.abs(L.offsetRate(0.5, 0.52, 1 / 60) + 1.2) < 1e-9)
				check.equal(L.offsetRate(0.5, nil, 1 / 60), 0) -- nothing kept (a body's first blend)
				check.equal(L.offsetRate(0.5, 0.52, 0.5), 0) -- the kept frame is from long ago
				check.equal(L.offsetRate(0.5, 3.5, 1 / 60), -60) -- a jump of 3 rad in a frame: held to the bar
				-- two readings either side of the half turn: the short way round
				check.truthy(math.abs(L.offsetRate(-3.1, 3.1, 1 / 60) - (2 * math.pi - 6.2) * 60) < 1e-6)
			end
		)
		test.case("twist: the turn along an axis, none across it", function()
			local h = math.rad(40) / 2
			-- 40 degrees about +Y, read about +Y and about -Y
			check.truthy(math.abs(L.twist(0, math.sin(h), 0, math.cos(h), 0, 1, 0) - math.rad(40)) < 1e-9)
			check.truthy(math.abs(L.twist(0, math.sin(h), 0, math.cos(h), 0, -1, 0) + math.rad(40)) < 1e-9)
			check.truthy(math.abs(L.twist(math.sin(h), 0, 0, math.cos(h), 0, 1, 0)) < 1e-9) -- about X: none along Y
			check.equal(L.twist(1, 0, 0, 0, 0, 1, 0), 0) -- a half turn at right angles
		end)
		test.case("a blend started at the old clip's speed leaves at that speed, not from a stop", function()
			local x0, T, dt = 0.6, 0.2, 1e-4
			local v0 = L.offsetRate(x0, 0.62, 1 / 60) -- -1.2 rad/s toward the new pose
			local slope = (L.inertial(x0, v0, T, dt) - x0) / dt
			check.truthy(math.abs(slope - v0) < 0.01)
			local still = (L.inertial(x0, 0, T, dt) - x0) / dt -- the old blend: it braked to 0 first
			check.truthy(math.abs(still) < 0.01)
			-- and it still lands exactly, with no overshoot
			check.equal(L.inertial(x0, v0, T, T), 0)
			for i = 1, 40 do
				check.truthy(L.inertial(x0, v0, T, i * T / 40) >= -1e-9)
			end
		end)
	end)
	test.suite("AnimLayers motion warping (C5)", function()
		local root = {}
		for i = 0, 60 do
			table.insert(root, { 0, -i * 0.1, 0 }) -- 6 studs forward over 1 s at 60 fps
		end
		test.case("no warp = the clip's own root", function()
			local x, z = L.warpedRootAt(root, 60, 0.5, nil)
			check.truthy(math.abs(x) < 1e-9 and math.abs(z + 3) < 1e-9)
		end)
		test.case("scale 1.5 in the window: 9 studs by its end, the clip's travel after it", function()
			local w = { from = 0, to = 1, scale = 1.5, turn = 0 }
			local _, z = L.warpedRootAt(root, 60, 1, w)
			check.truthy(math.abs(z + 9) < 1e-6)
		end)
		test.case("a turn bends the travel toward the target", function()
			local w = { from = 0, to = 1, scale = 1, turn = math.rad(30) }
			local x, _, yaw = L.warpedRootAt(root, 60, 1, w)
			check.truthy(x < -1 and math.abs(yaw - math.rad(30)) < 1e-9) -- +turn = to the left (-X) going -Z
		end)
		test.case("warpFor clamps the scale and the turn", function()
			local s, t = L.warpFor(6, 30, math.rad(80))
			check.truthy(math.abs(s - 1.6) < 1e-9 and math.abs(t - math.rad(35)) < 1e-9)
			local s2 = L.warpFor(6, 6, 0, 3)
			check.truthy(math.abs(s2 - 0.5) < 1e-9)
		end)
	end)
	test.suite("AnimLayers reaction side, tracking, kick, swing", function()
		test.case("the side of the victim the blow came from", function()
			-- a victim at the origin looking -Z (forward)
			check.equal(L.reactionSide(0, -5, 0, 0, 0, -1), "Front")
			check.equal(L.reactionSide(0, 5, 0, 0, 0, -1), "Back")
			check.equal(L.reactionSide(5, 0, 0, 0, 0, -1), "Right")
			check.equal(L.reactionSide(-5, 0, 0, 0, 0, -1), "Left")
		end)
		test.case("look-at: ahead = 0, left = +yaw, clamped past the neck", function()
			local y0, p0 = L.lookAngles(0, 0, -5)
			check.truthy(math.abs(y0) < 1e-9 and math.abs(p0) < 1e-9)
			local y1 = L.lookAngles(-5, 0, -5)
			check.truthy(math.abs(y1 - math.rad(45)) < 1e-9)
			local y2 = L.lookAngles(0, 0, 5)
			check.truthy(math.abs(math.abs(y2) - math.rad(70)) < 1e-9) -- behind: clamped to the neck's reach
		end)
		test.case("active frames lock the turn by default", function()
			check.equal(L.turnAllowed("active", {}), 0)
			check.equal(L.turnAllowed("startup", { startup = 360 }), 360)
			check.equal(L.turnAllowed("active", nil), math.huge)
		end)
		test.case("the kick is full at once and mostly gone in 0.3 s", function()
			check.truthy(math.abs(L.kick(0, 1) - 1) < 1e-9 and L.kick(0.3, 1) < 0.02 and L.kick(-0.1, 1) == 0)
		end)
		test.case("the swing settles back after a push", function()
			local s = { x = 0, v = 0 }
			s = L.swing(s, 30, 0.1)
			check.truthy(math.abs(s.x) > 0.01)
			for _ = 1, 60 do
				s = L.swing(s, 0, 1 / 30)
			end
			check.truthy(math.abs(s.x) < 1e-3)
		end)
	end)
	test.suite("AnimLayers reaction matrix (C3)", function()
		local function has(set: { string }): (string) -> boolean
			return function(n: string): boolean
				return table.find(set, n) ~= nil
			end
		end
		test.case("the most specific clip that exists wins; one reaction is the floor", function()
			local all = has({ "HitAir", "HitBackHeavy", "HitBack", "HitHeavy", "Hit" })
			check.equal(L.reactionName("Hit", "Back", "heavy", true, all), "HitAir")
			check.equal(L.reactionName("Hit", "Back", "heavy", false, all), "HitBackHeavy")
			check.equal(L.reactionName("Hit", "Back", "light", false, all), "HitBack")
			check.equal(L.reactionName("Hit", "Front", "heavy", false, all), "HitHeavy")
			check.equal(L.reactionName("Hit", "Left", nil, false, has({})), "Hit")
		end)
	end)
	test.suite("AnimLayers camera track (D9)", function()
		local keys = {
			{ t = 0, loc = { 0, 5, 10 }, target = { 0, 2, 0 }, fov = 70 },
			{ t = 1, loc = { 10, 5, 0 }, target = { 0, 2, 0 }, fov = 50 },
		}
		test.case("holds the ends, eases between keys (half way = the middle)", function()
			local l0, _, f0 = L.cameraAt(keys, -1)
			check.equal(l0[1], 0)
			check.equal(f0, 70)
			local l1, _, f1 = L.cameraAt(keys, 5)
			check.equal(l1[1], 10)
			check.equal(f1, 50)
			local lm, _, fm = L.cameraAt(keys, 0.5)
			check.truthy(math.abs(lm[1] - 5) < 1e-9 and math.abs((fm :: number) - 60) < 1e-9)
			local lq = L.cameraAt(keys, 0.25)
			check.truthy(lq[1] < 2.5) -- eased: slower than linear at the start
		end)
	end)
	test.suite("AnimLayers additive sampling (D3)", function()
		test.case("finds the two rows around t; a one-shot holds the ends, a loop wraps", function()
			local times = { 0, 0.1, 0.3, 0.6 }
			local i, j, f = L.sampleAt(times, 0.2)
			check.equal(i, 2)
			check.equal(j, 3)
			check.truthy(math.abs(f - 0.5) < 1e-9)
			check.equal((L.sampleAt(times, 2)), 4)
			check.equal((L.sampleAt(times, -1)), 1)
			local li, lj, lf = L.sampleAt(times, 0.8, true) -- 0.8 wraps to 0.2
			check.equal(li, 2)
			check.equal(lj, 3)
			check.truthy(math.abs(lf - 0.5) < 1e-9)
		end)
		test.case("the layer fades in, holds, fades out to exactly 0 at its end", function()
			check.equal(L.layerWeight(0, 1, 0.1, 0.2), 0)
			check.equal(L.layerWeight(0.5, 1, 0.1, 0.2), 1)
			check.equal(L.layerWeight(1, 1, 0.1, 0.2), 0)
			check.equal(L.layerWeight(5, math.huge, 0.1, 0.2), 1) -- a loop never fades out by itself
		end)
	end)

	test.suite("AnimLayers: attention beyond the head (AN-30)", function()
		local function deg(r: number): number
			return math.deg(r)
		end
		local function close(a: number, b: number): boolean
			return math.abs(a - b) < 1e-6
		end
		test.case("the head alone, as before, when the body takes no share", function()
			local yaw = L.lookRaw(-5, 0, -5) -- 45 degrees to the right
			local body, head, pitch = L.lookSplit(yaw, 0)
			check.truthy(body == 0 and close(deg(head), deg(yaw)) and pitch == 0)
			local y, p = L.lookAngles(-5, 0, -5)
			check.truthy(close(head, y) and close(pitch, p))
		end)
		test.case("the body leads with its share, the head takes the rest, each inside its limit", function()
			local body, head = L.lookSplit(math.rad(40), 0, 0.3)
			check.truthy(close(deg(body), 12) and close(deg(head), 28))
			body, head = L.lookSplit(math.rad(85), 0, 0.3) -- the body at its 20, the head takes 65
			check.truthy(close(deg(body), 20) and close(deg(head), 65))
			body, head = L.lookSplit(math.rad(-85), 0, 0.3)
			check.truthy(close(deg(body), -20) and close(deg(head), -65))
			-- together they reach further than a neck: 90 degrees is head 70 + body 20, full weight
			body, head = L.lookSplit(math.rad(90), 0, 0.3)
			check.truthy(close(deg(body), 20) and close(deg(head), 70))
			-- the body's own limit and share are the caller's
			body, head = L.lookSplit(math.rad(60), 0, 0.5, 40)
			check.truthy(close(deg(body), 30) and close(deg(head), 30))
		end)
		test.case("a target behind is not craned at, and passing straight behind does not snap the head", function()
			check.equal(L.lookWeight(math.rad(60), 70), 1)
			check.equal(L.lookWeight(math.rad(70), 70), 1)
			check.truthy(close(L.lookWeight(math.rad(82.5), 70), 0.5))
			check.equal(L.lookWeight(math.rad(95), 70), 0)
			check.equal(L.lookWeight(math.rad(180), 70), 0)
			-- straight behind, a hair to either side: clamped alone the head read +70 then -70
			local _, left = L.lookSplit(math.rad(179), 0)
			local _, right = L.lookSplit(math.rad(-179), 0)
			check.truthy(left == 0 and right == 0)
			-- and on the way there it eases out: no step anywhere from 60 to 120 degrees
			local last: number? = nil
			for a = 60, 120 do
				local _, h = L.lookSplit(math.rad(a), 0)
				if last then
					check.truthy(math.abs(deg(h) - deg(last)) < 6)
				end
				last = h
			end
			-- the pitch fades with it
			local _, _, p = L.lookSplit(math.rad(180), math.rad(20))
			check.equal(p, 0)
		end)
		test.case("numbers that are not numbers turn nothing", function()
			local b, h, p = L.lookSplit(0 / 0, 0, 0.3)
			check.truthy(b == 0 and h == 0 and p == 0)
			b, h, p = L.lookSplit(0, 0 / 0, 0.3)
			check.truthy(b == 0 and h == 0 and p == 0)
			b, h = L.lookSplit(math.rad(40), 0, 5) -- a share over 1 is 1
			check.truthy(close(deg(b), 20) and close(deg(h), 20))
		end)
		test.case("the body takes what the head cannot reach, whatever its share", function()
			-- (share 0.1, target at 85: the head sat pinned at its 70 with the body at 8.5 - the shoulder-pinned
			-- look the fade was meant to end - at full weight)
			local body, head = L.lookSplit(math.rad(85), 0, 0.1)
			check.truthy(close(deg(body), 15) and close(deg(head), 70))
			body, head = L.lookSplit(math.rad(90), 0, 0.01)
			check.truthy(close(deg(body), 20) and close(deg(head), 70))
			body, head = L.lookSplit(math.rad(-90), 0, 0.01)
			check.truthy(close(deg(body), -20) and close(deg(head), -70))
			body, head = L.lookSplit(math.rad(40), 0, 0.1) -- inside the head's reach: its share, no more
			check.truthy(close(deg(body), 4) and close(deg(head), 36))
			-- no step in head + body as the target sweeps from behind to behind, for any share
			for _, share in { 0.01, 0.1, 0.3, 1 } do
				local last: number? = nil
				for a = -1800, 1800 do
					local b, h = L.lookSplit(math.rad(a / 10), 0, share)
					local sum = deg(b) + deg(h)
					if last then
						check.truthy(math.abs(sum - last) < 0.6)
					end
					last = sum
				end
			end
		end)
		test.case("the look is laid over the clip's own twist: the head turns that much less", function()
			-- the clip has turned the torso 40 degrees left; the target is 60 left of the body's facing
			local body, head = L.lookSplit(math.rad(60), 0, 0.3, nil, nil, nil, math.rad(40))
			check.truthy(close(deg(body), 18) and close(deg(head), 2)) -- 40 + 18 + 2 = 60
			-- the target straight ahead of the body, the torso wound up 60 degrees: the body adds nothing, the head
			-- looks back at it (it took 18 degrees of the wind-up back when measured from the twisted torso)
			body, head = L.lookSplit(0, 0, 0.3, nil, nil, nil, math.rad(60))
			check.truthy(body == 0 and close(deg(head), -60))
			body, head = L.lookSplit(0, 0, 0.3, nil, nil, nil, 0 / 0) -- a twist that is not a number: none
			check.truthy(body == 0 and head == 0)
		end)
		test.case("straight overhead is ahead, and options that are not numbers do not break the look", function()
			local yaw, pitch = L.lookRaw(0, 5, 0)
			check.truthy(yaw == 0 and math.abs(deg(pitch) - 90) < 0.01)
			local _, _, p = L.lookSplit(yaw, pitch, 0.3)
			check.truthy(close(deg(p), 35)) -- (it read "behind": no look at all)
			local b, h = L.lookSplit(math.rad(40), 0, 0 / 0)
			check.truthy(b == 0 and close(deg(h), 40))
			b, h = L.lookSplit(math.rad(40), 0, 0.3, -20, -70) -- (a negative limit threw every frame)
			check.truthy(close(deg(b), 12) and close(deg(h), 28))
			b, h = L.lookSplit(math.rad(40), 0, 0.3, 0 / 0, 0 / 0)
			check.truthy(close(deg(b), 12) and close(deg(h), 28))
		end)
		test.case("a leg is kept where it stands whatever the clip has done to the torso", function()
			local roblox = require("@lune/roblox")
			local CFrame, Vector3 = (roblox :: any).CFrame, (roblox :: any).Vector3
			-- the R6 rig's own joints (kit/anim/rigs/r6.json)
			local rootC = CFrame.new(0, 0, 0, -1, 0, 0, 0, 0, 1, 0, 1, 0)
			local hips = {
				{
					c0 = CFrame.new(-1, -1, 0, 0, 0, -1, 0, 1, 0, 1, 0, 0),
					c1 = CFrame.new(-0.5, 1, 0, 0, 0, -1, 0, 1, 0, 1, 0, 0),
				},
				{
					c0 = CFrame.new(1, -1, 0, 0, 0, 1, 0, 1, 0, -1, 0, 0),
					c1 = CFrame.new(0.5, 1, 0, 0, 0, 1, 0, 1, 0, -1, 0, 0),
				},
			}
			local function leg(rootT: any, hip: any, hipT: any): any
				local torso = rootC * rootT * rootC:Inverse()
				return torso * hip.c0 * hipT * hip.c1:Inverse()
			end
			local turn = rootC.Rotation:Inverse() * CFrame.Angles(0, math.rad(20), 0) * rootC.Rotation -- the look's 20 degrees
			for _, clip in
				{
					CFrame.new(), -- at rest
					CFrame.Angles(math.rad(30), 0, 0), -- the clip pitches the torso 30 degrees
					CFrame.Angles(0, 0, math.rad(25)) * CFrame.new(0.3, -0.4, 0.2), -- rolled and dropped
					CFrame.Angles(math.rad(10), math.rad(40), math.rad(-15)), -- leaned and twisted
				}
			do
				for _, hip in hips do
					local hipT = CFrame.Angles(math.rad(12), 0, math.rad(-7)) * CFrame.new(0, 0.2, 0) -- the clip's own leg pose
					local before = leg(clip, hip, hipT)
					local keep = L.keepLeg(rootC, rootC, clip, turn * clip, hip.c0)
					local after = leg(turn * clip, hip, keep * hipT)
					check.truthy((after.Position - before.Position).Magnitude < 1e-4)
					check.truthy((after.LookVector - before.LookVector).Magnitude < 1e-4)
					check.truthy((after.UpVector - before.UpVector).Magnitude < 1e-4)
					-- (turned back about the torso's own up alone, the pitched torso carried this foot half a stud)
					local naive = hip.c0.Rotation:Inverse() * CFrame.Angles(0, math.rad(-20), 0) * hip.c0.Rotation
					local wrong = leg(turn * clip, hip, naive * hipT)
					local foot = Vector3.new(0, -1, 0)
					if clip ~= CFrame.new() and (clip.Position.Magnitude > 0 or math.abs(clip.LookVector.Y) > 0.1) then
						check.truthy((wrong * foot - before * foot).Magnitude > 0.05)
					end
				end
			end
		end)
		test.case("a committed move, a ragdoll and a seat do not permit the look", function()
			check.equal(L.lookPermit(true, false, false), 1)
			check.equal(L.lookPermit(false, false, false), 0) -- (Moves took AutoRotate away: the active frames)
			check.equal(L.lookPermit(true, true, false), 0)
			check.equal(L.lookPermit(true, false, true), 0)
		end)
		test.case("of several things to look at: the highest priority, then the one named last", function()
			check.truthy(L.attention({}) == nil)
			check.equal(L.attention({ door = { priority = 1, since = 1 } }), "door")
			check.equal(
				L.attention({ door = { priority = 1, since = 1 }, threat = { priority = 5, since = 0 } }),
				"threat"
			)
			check.equal(L.attention({ a = { priority = 2, since = 3 }, b = { priority = 2, since = 7 } }), "b")
			check.equal(L.attention({ a = { priority = 2, since = 7 }, b = { priority = 2, since = 7 } }), "a") -- (a tie all the way: by name, so it does not flicker)
			check.equal(L.attention({ a = { priority = 0 / 0, since = 1 }, b = { priority = -3, since = 1 } }), "b")
		end)
	end)
end

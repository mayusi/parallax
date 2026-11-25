-- anim.spec.luau (kit) — character-space rotations become the right joint transforms (the five cases were also
-- verified on a real R6 rig in Studio), the engine-read rigs place every part where the engine does (forward
-- kinematics against the probe's rest offsets), the template compiles, and the gate rejects bad specs.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Anim = require("../../lib/anim")
local AnimBlend = require("../../../src/kit/AnimBlend")
local AnimFeel = require("../../../src/kit/AnimFeel")
local Vector3 = require("@lune/roblox").Vector3 -- (Lune has no Roblox globals; the blend maths only reads .X .Z .Unit .Magnitude)

local function near(a: { { number } }, b: { { number } }): boolean
	for i = 1, 3 do
		for j = 1, 3 do
			if math.abs(a[i][j] - b[i][j]) > 1e-4 then
				return false
			end
		end
	end
	return true
end

local function close(a: { number }, b: { number }, tol: number): boolean
	for i = 1, #a do
		if math.abs(a[i] - b[i]) > tol then
			return false
		end
	end
	return true
end

local function errorsOf(spec: any): string
	local _, _, issues = Anim.compile(spec)
	local out = {}
	for _, i in issues do
		if i.severity == "error" then
			table.insert(out, i.message)
		end
	end
	return table.concat(out, "\n")
end

return function()
	test.suite("Anim character-space → joint space (engine-verified cases)", function()
		local J = Anim.RIGS.R6.joints
		test.case("Right Arm [90,0,0] (points forward)", function()
			check.is_true(
				near((Anim.toJoint(J["Right Arm"].c0, { 90, 0, 0 })), { { 0, -1, 0 }, { 1, 0, 0 }, { 0, 0, 1 } })
			)
		end)
		test.case("Right Arm [0,0,90] (raised to the right)", function()
			check.is_true(
				near((Anim.toJoint(J["Right Arm"].c0, { 0, 0, 90 })), { { 1, 0, 0 }, { 0, 0, 1 }, { 0, -1, 0 } })
			)
		end)
		test.case("Left Arm [0,0,-90] (raised to the left)", function()
			check.is_true(
				near((Anim.toJoint(J["Left Arm"].c0, { 0, 0, -90 })), { { 1, 0, 0 }, { 0, 0, 1 }, { 0, -1, 0 } })
			)
		end)
		test.case("Torso [0,30,0] (twist left)", function()
			local c, s = math.cos(math.rad(30)), math.sin(math.rad(30))
			check.is_true(near((Anim.toJoint(J.Torso.c0, { 0, 30, 0 })), { { c, -s, 0 }, { s, c, 0 }, { 0, 0, 1 } }))
		end)
	end)

	test.suite("Anim rigs read from the engine (kit/anim/rigs/*.json)", function()
		test.case("R6 and R15 are known, parents come before children", function()
			local names = Anim.rigs()
			check.is_true(table.find(names, "r6") ~= nil and table.find(names, "r15") ~= nil)
			for _, rigName in { "R6", "R15" } do
				local rig = Anim.rig(rigName)
				local seen = { [rig.root] = true }
				for _, part in rig.order do
					check.is_true(seen[rig.joints[part].parent] == true)
					seen[part] = true
				end
			end
		end)
		test.case("R6 data from the probe is the data the kit shipped with (Right Shoulder C0/C1)", function()
			local j = Anim.rig("R6").joints["Right Arm"]
			check.equal(j.joint, "Right Shoulder")
			check.is_true(close(j.c0, { 1, 0.5, 0, 0, 0, 1, 0, 1, 0, -1, 0, 0 }, 1e-6))
			check.is_true(close(j.c1, { -0.5, 0.5, 0, 0, 0, 1, 0, 1, 0, -1, 0, 0 }, 1e-6))
		end)
		test.case("rest-pose forward kinematics lands every part on the engine's rest offset", function()
			for _, rigName in { "R6", "R15" } do
				local rig = Anim.rig(rigName)
				local world = Anim.fk(rig)
				for _, part in rig.order do
					local got, want = world[part], rig.rest[part]
					check.is_true(close({ got[1], got[2], got[3] }, { want[1], want[2], want[3] }, 2e-3))
				end
			end
		end)
		test.case("R15: [90,0,0] on RightUpperArm swings the hand forward at shoulder height", function()
			local rig = Anim.rig("R15")
			local t, p = Anim.toJoint(rig.joints.RightUpperArm.c0, { 90, 0, 0 })
			local hand = Anim.fk(rig, { RightUpperArm = { rot = t, pos = p } }).RightHand
			check.is_true(hand[3] < -1.5) -- forward is -Z: the hand is out in front
			check.is_true(math.abs(hand[2] - 0.85) < 0.05) -- level with the shoulder pivot
			check.is_true(math.abs(hand[1] - 1.47) < 0.02) -- still on the right side
		end)
		test.case("R15: the elbow bends the forearm, the upper arm stays", function()
			local rig = Anim.rig("R15")
			local t, p = Anim.toJoint(rig.joints.RightLowerArm.c0, { 90, 0, 0 })
			local world = Anim.fk(rig, { RightLowerArm = { rot = t, pos = p } })
			check.is_true(close(world.RightUpperArm, rig.rest.RightUpperArm, 2e-3))
			check.is_true(world.RightHand[3] < -0.5 and world.RightHand[2] > rig.rest.RightHand[2])
		end)
		test.case("CFrame math: inverse and product cancel", function()
			local a = Anim.CF.angles({ 33, -70, 12 }, { 1, 2, 3 })
			check.is_true(close(Anim.CF.mul(a, Anim.CF.inv(a)), Anim.IDENTITY, 1e-9))
			check.is_true(close(Anim.CF.mul(Anim.CF.inv(a), a), Anim.IDENTITY, 1e-9))
		end)
	end)

	test.suite("Anim compile + gate", function()
		test.case("the kit template compiles with markers", function()
			local spec = serde.decode("json", string.gsub(fs.readFile("kit/templates/anim.json"), "__NAME__", "T"))
			local model, data = Anim.compile(spec)
			check.is_true(model ~= nil)
			check.equal(#errorsOf(spec), 0) -- (the R6 fold WARNS that the waist twist takes the legs)
			check.equal(#data.frames, 5)
			local markers = 0
			for _, kf in model.Children do
				for _, c in kf.Children or {} do
					if c.ClassName == "KeyframeMarker" then
						markers += 1
					end
				end
			end
			check.equal(markers, 1)
		end)
		test.case("joints hold their last value (every keyframe is complete)", function()
			local _, data = Anim.compile({
				name = "H",
				keys = {
					{ t = 0, pose = { ["Right Arm"] = { 90, 0, 0 } } },
					{ t = 0.5, pose = { Head = { 10, 0, 0 } } },
				},
			})
			check.equal(data.frames[2].pose["Right Arm"].rot[1], 90)
		end)
		test.case("bad specs are rejected with fixes", function()
			local errs = errorsOf({
				name = "B",
				rig = "R6",
				priority = "Urgent",
				keys = {
					{ t = 0.1, ease = "Wobble", pose = { Tail = { 0, 0, 0 } } },
					{ t = 0.05, pose = { Head = { 999, 0, 0 } } },
				},
				events = { { t = 9, name = "bad name" } },
			})
			for _, needle in
				{
					"priority must",
					"first key must",
					"strictly increase",
					"ease must",
					"is not a joint",
					"rotation must",
					"event name",
					"event time",
				}
			do
				check.is_true(string.find(errs, needle, 1, true) ~= nil)
			end
		end)
		test.case("unknown rig values are refused", function()
			check.is_true(string.find(errorsOf({ name = "R", rig = "R7", keys = {} }), "rig must be", 1, true) ~= nil)
		end)
	end)

	test.suite("Anim R15 + partial joints (engine-verified semantics)", function()
		local spec = {
			name = "Aim",
			priority = "Action",
			keys = {
				{ t = 0, pose = { ["Right Arm"] = { 90, 0, 0 }, RightLowerArm = { 20, 0, 0 } } },
				{ t = 0.5, pose = { ["Right Arm"] = { 80, 0, 0 } } },
			},
		}
		local function find(model: any, name: string): any
			local hit = nil
			local function walk(n: any)
				if n.Name == name and n.ClassName == "Pose" then
					hit = hit or n
				end
				for _, c in n.Children or {} do
					walk(c)
				end
			end
			walk(model.Children[1])
			return hit
		end
		test.case("R6 names drive the matching R15 joint; R15 transform = the character-space rotation", function()
			local model, _, issues = Anim.compile(spec, "R15")
			check.equal(#issues, 0)
			local arm = find(model, "RightUpperArm")
			check.is_true(arm ~= nil)
			check.equal(arm.Properties.Weight, 1)
			local o = arm.Properties.CFrame.CFrame.orientation
			check.is_true(near(o, { { 1, 0, 0 }, { 0, 0, -1 }, { 0, 1, 0 } }))
			check.is_true(find(model, "RightLowerArm") ~= nil) -- R15-only joint used in the R15 version
		end)
		test.case("only moved joints are controlled; parents are Weight-0 containers; legs untouched", function()
			local model = Anim.compile(spec, "R15")
			check.equal(find(model, "UpperTorso").Properties.Weight, 0)
			check.equal(find(model, "LowerTorso").Properties.Weight, 0)
			check.is_true(find(model, "RightUpperLeg") == nil)
			check.is_true(find(model, "Head") == nil)
			local r6 = Anim.compile(spec, "R6")
			check.equal(find(r6, "Torso").Properties.Weight, 0)
			check.is_true(find(r6, "Right Leg") == nil)
			check.is_true(find(r6, "RightLowerArm") == nil) -- R15-only name has no R6 joint
		end)
	end)

	test.suite("Anim easing, quaternions, the neutral clip", function()
		test.case("easing: ends pinned, InOut symmetric, Out is the mirror of In", function()
			for _, style in { "Linear", "Cubic", "Elastic", "Bounce", "CubicV2" } do
				for _, dir in { "In", "Out", "InOut" } do
					check.is_true(math.abs(Anim.ease(style, dir, 0)) < 1e-9)
					check.is_true(math.abs(Anim.ease(style, dir, 1) - 1) < 1e-9)
				end
				check.is_true(math.abs(Anim.ease(style, "InOut", 0.5) - 0.5) < 1e-9)
				check.is_true(math.abs(Anim.ease(style, "Out", 0.3) - (1 - Anim.ease(style, "In", 0.7))) < 1e-9)
			end
			check.is_true(math.abs(Anim.ease("Cubic", "In", 0.5) - 0.125) < 1e-9)
			check.equal(Anim.ease("Constant", "In", 0.9), 0)
			check.equal(Anim.ease("Constant", "Out", 0.1), 1)
		end)
		test.case("quaternions: matrix round trip, slerp halves the angle", function()
			local q = Anim.Q.fromEuler({ 33, -70, 12 })
			local back = Anim.Q.fromMatrix(Anim.Q.toMatrix(q))
			check.is_true(
				math.abs(math.abs(q[1] * back[1] + q[2] * back[2] + q[3] * back[3] + q[4] * back[4]) - 1) < 1e-9
			)
			local a, b = Anim.Q.fromEuler({ 0, 0, 0 }), Anim.Q.fromEuler({ 90, 0, 0 })
			local mid = Anim.Q.slerp(a, b, 0.5)
			check.is_true(math.abs(Anim.Q.angle(a, mid) - 45) < 1e-6)
			check.is_true(math.abs(Anim.Q.angle(mid, b) - 45) < 1e-6)
		end)
		test.case("the template becomes a clip: R15 names, a key per joint per spec key, dense frames", function()
			local spec = serde.decode("json", string.gsub(fs.readFile("kit/templates/anim.json"), "__NAME__", "T"))
			local clip, issues = Anim.clipFromSpec(spec)
			check.equal(#issues, 0)
			check.equal(clip.rig, "R15")
			check.is_true(
				clip.joints.RightUpperArm ~= nil and clip.joints.UpperTorso ~= nil and clip.joints.Head ~= nil
			)
			check.is_true(clip.joints["Right Arm"] == nil)
			check.equal(#clip.joints.RightUpperArm.keys, 5)
			check.equal(#clip.times, 24) -- 0 .. 22/30 and the exact end 0.75
			check.equal(#clip.joints.RightUpperArm.frames, 24)
			-- the frame on a key time is that key
			local k2 = clip.joints.RightUpperArm.keys[2]
			local i = 1
			for idx, t in clip.times do
				if math.abs(t - k2.t) < 1e-9 then
					i = idx
				end
			end
			check.is_true(math.abs(clip.times[i] - 0.25) < 1e-9 or i == 1)
			local rot = Anim.eulerOf((Anim.frameValue(clip.joints.RightUpperArm, i)))
			check.is_true(math.abs(rot[1] - k2.rot[1]) < 0.01 or i == 1)
		end)
		test.case("a joint keyed late holds rest before its first key, then its value", function()
			local clip = Anim.clipFromSpec({
				name = "L",
				keys = {
					{ t = 0, ease = "Linear", pose = { Head = { 0, 0, 0 } } },
					{ t = 0.5, ease = "Linear", pose = { ["Right Arm"] = { 90, 0, 0 } } },
					{ t = 1, pose = { ["Right Arm"] = { 90, 0, 0 } } },
				},
			})
			local arm = clip.joints.RightUpperArm
			check.equal(#arm.keys, 3)
			check.equal(arm.keys[1].rot[1], 0)
			check.equal(arm.keys[2].rot[1], 90)
			-- frame 7 is t = 0.2: 0.2 / 0.5 of the way to the first real key (Linear) = 36 degrees
			local mid = Anim.eulerOf((Anim.frameValue(arm, 7)))
			check.is_true(math.abs(mid[1] - 36) < 0.5)
		end)
		test.case("an additive track is the change from its base frame: base * delta = the pose (D3)", function()
			local clip = Anim.clipFromSpec({
				name = "Flinch",
				keys = {
					{ t = 0, pose = { LowerTorso = { 0, 0, 0 }, UpperTorso = { 0, 10, 0 } } },
					{ t = 0.3, pose = { LowerTorso = { 15, 0, 5 }, UpperTorso = { -10, 30, 0 } } },
				},
			})
			local _, r6 = Anim.modelFromClip((Anim.foldToR6(clip)), "R6")
			local add = Anim.additiveTrack(r6, 0)
			local rows = add.joints.Torso
			check.is_true(#rows >= 2 and #rows <= #r6.frames)
			check.equal(#add.times, #rows)
			local function nums(row: string): { number }
				local out = {}
				for _, v in string.split(row, " ") do
					table.insert(out, tonumber(v) :: number)
				end
				return out
			end
			local first = nums(rows[1])
			check.is_true(close(first, { 0, 0, 0, 1, 0, 0, 0 }, 1e-4)) -- the base frame adds nothing
			local last = nums(rows[#rows])
			local b, p = r6.frames[1].transforms.Torso, r6.frames[#r6.frames].transforms.Torso
			local d = Anim.Q.toMatrix({ last[1], last[2], last[3], last[4] })
			local composed = {}
			for i = 1, 3 do
				composed[i] = {}
				for j = 1, 3 do
					composed[i][j] = b.rot[i][1] * d[1][j] + b.rot[i][2] * d[2][j] + b.rot[i][3] * d[3][j]
				end
			end
			check.is_true(near(composed, p.rot))
		end)
		test.case("R6 Torso folds LowerTorso and UpperTorso together; R15 keeps them apart", function()
			local clip = Anim.clipFromSpec({
				name = "Twist",
				keys = {
					{ t = 0, pose = { LowerTorso = { 0, 0, 0 }, UpperTorso = { 0, 0, 0 } } },
					{ t = 0.5, pose = { LowerTorso = { 0, 20, 0 }, UpperTorso = { 0, 30, 0 } } },
				},
			})
			local _, r6 = Anim.modelFromClip((Anim.foldToR6(clip)), "R6")
			check.is_true(math.abs(r6.frames[2].pose.Torso.rot[2] - 50) < 0.01)
			local _, r15 = Anim.modelFromClip(clip, "R15")
			check.equal(r15.frames[2].pose.LowerTorso.rot[2], 20)
			check.equal(r15.frames[2].pose.UpperTorso.rot[2], 30)
		end)
		test.case("the R6 fold re-keys a leg it lifted: every key equals its frame, the sole stays up", function()
			local clip = Anim.clipFromSpec({
				name = "Kick", -- a knee folded under the hip: the straight R6 leg would stand on the floor mid-air
				keys = {
					{
						t = 0, -- both legs in the clip: the fold grounds and lifts legs only in a clip that has both
						pose = {
							RightUpperLeg = { 0, 0, 0 },
							RightLowerLeg = { 0, 0, 0 },
							RightFoot = { 0, 0, 0 },
							LeftUpperLeg = { 0, 0, 0 },
							LeftLowerLeg = { 0, 0, 0 },
							LeftFoot = { 0, 0, 0 },
						},
					},
					-- the foot levels (the shin tilts back 20: the sole would otherwise touch toe-first)
					{
						t = 0.2,
						pose = { RightUpperLeg = { 20, 0, 0 }, RightLowerLeg = { -40, 0, 0 }, RightFoot = { 20, 0, 0 } },
					},
					{ t = 0.4, pose = { RightUpperLeg = { 0, 0, 0 }, RightLowerLeg = { 0, 0, 0 } } },
				},
			})
			local folded = (Anim.foldToR6(clip))
			local leg = folded.joints["Right Leg"]
			check.is_true(leg ~= nil and leg.keys ~= nil and #leg.keys == 3)
			local byTime = {}
			for i, t in folded.times do
				byTime[t] = i
			end
			local lifted = false
			for _, k in leg.keys :: any do
				local f = (leg.frames :: any)[byTime[k.t]]
				check.is_true(close(k.rot, Anim.eulerOf(Anim.Q.toMatrix({ f[1], f[2], f[3], f[4] })), 1e-3))
				check.is_true(close(k.pos, { f[5], f[6], f[7] }, 1e-3))
				lifted = lifted or f[6] > 0.01
			end
			check.is_true(lifted) -- the kicked leg slid up into the torso rather than through the floor
			local rigR6 = Anim.rig("R6")
			local floor = rigR6.rest["Right Leg"][2] - rigR6.sizes["Right Leg"][2] / 2
			for i = 1, #folded.times do
				local transforms = {}
				for name, j in folded.joints do
					local m, pp = Anim.frameValue(j, i)
					local jt, jp = Anim.toJointM(rigR6.joints[name].c0, m, pp)
					transforms[name] = { rot = jt, pos = jp }
				end
				local world = Anim.fk(rigR6, transforms)
				local sole = Anim.CF.mul(world["Right Leg"], { 0, -1, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1 })
				check.is_true(sole[2] > floor - 0.02)
			end
		end)
		test.case("a waist twist alone keeps the R6 legs planted (the inverse turn), R15 legs untouched", function()
			local clip = Anim.clipFromSpec({
				name = "Waist",
				keys = {
					{ t = 0, pose = { UpperTorso = { 0, 0, 0 } } },
					{ t = 0.5, pose = { UpperTorso = { 0, 30, 0 } } },
				},
			})
			local folded, foldIssues = Anim.foldToR6(clip)
			check.is_true(#foldIssues == 1 and foldIssues[1].severity == "warn")
			local r6model, r6 = Anim.modelFromClip(folded, "R6")
			check.is_true(r6.moved["Right Leg"] == true and r6.moved["Left Leg"] == true)
			check.is_true(math.abs(r6.frames[2].pose["Right Leg"].rot[2] + 30) < 0.01)
			check.is_true(math.abs(r6.frames[2].pose.Torso.rot[2] - 30) < 0.01)
			check.is_true(r6model ~= nil)
			-- the feet stay where they were: forward kinematics on the written joint transforms
			local rigR6 = Anim.rig("R6")
			local before = Anim.fk(rigR6, r6.frames[1].transforms)
			local after = Anim.fk(rigR6, r6.frames[2].transforms)
			for _, leg in { "Right Leg", "Left Leg" } do
				check.is_true(
					close(
						{ after[leg][1], after[leg][2], after[leg][3] },
						{ before[leg][1], before[leg][2], before[leg][3] },
						1e-3
					)
				)
				check.is_true(close(after[leg], before[leg], 1e-3)) -- orientation too
			end
			local _, r15 = Anim.modelFromClip(clip, "R15")
			check.is_true(r15.moved.RightUpperLeg == nil and r15.moved.UpperTorso == true)
		end)
		test.case("a dense clip (no keys: a bake) compiles to one Linear keyframe per frame", function()
			local clip = Anim.clipFromSpec({
				name = "D",
				fps = 10,
				keys = { { t = 0, pose = { Head = { 0, 0, 0 } } }, { t = 1, pose = { Head = { 30, 0, 0 } } } },
			})
			clip.joints.Head.keys = nil -- what a Blender bake hands over: frames only
			local model, data = Anim.modelFromClip(clip, "R15")
			check.equal(#data.frames, 11)
			local function headPose(n: any): any
				if n.Name == "Head" and n.ClassName == "Pose" then
					return n
				end
				for _, c in n.Children or {} do
					local hit = headPose(c)
					if hit then
						return hit
					end
				end
				return nil
			end
			check.equal(headPose(model.Children[1]).Properties.EasingStyle, "Linear")
		end)
	end)

	test.suite("AnimBlend: the moments between the loops (AN-28)", function()
		-- a body's ground velocity fed frame by frame at 60 a second; the moments that begin are collected
		local function run(script: { { number } }, walkSpeed: number?): { string }
			local flow = AnimBlend.flow()
			local out: { string } = {}
			for _, step in script do
				local seconds, vx, vz, yaw = step[1], step[2], step[3], step[4] or 0
				for _ = 1, math.floor(seconds * 60 + 0.5) do
					local m = AnimBlend.transition(flow, vx, vz, yaw, 1 / 60, walkSpeed or 16)
					if m then
						table.insert(out, m)
					end
				end
			end
			return out
		end
		local function same(got: { string }, want: { string }): boolean
			if #got ~= #want then
				return false
			end
			for i = 1, #want do
				if got[i] ~= want[i] then
					return false
				end
			end
			return true
		end
		test.case("a fast walker's halt is read inside a window as long as its braking (V3 anim stage F.1)", function()
			-- at 32 studs a second the pace is 16: braking under it for 0.6 s, then still, is a HALT (the window was
			-- 0.45 s at every speed: this read as a drift to a stop and its stop was never played)
			local brake = { { 0.5, 0, 0 }, { 1, 0, -32 }, { 0.6, 0, -8 }, { 0.5, 0, 0 } }
			check.is_true(same(run(brake, 32), { "start", "stop" }))
			-- the same 0.6 s at 16 is still a drift: the window is never shorter than measured, nor longer there
			check.is_true(same(run({ { 0.5, 0, 0 }, { 1, 0, -16 }, { 0.6, 0, -4 }, { 0.5, 0, 0 } }, 16), { "start" }))
			check.is_true(math.abs(AnimBlend.haltWindow(32) - 2 * AnimBlend.HALT) < 1e-9)
			check.is_true(math.abs(AnimBlend.haltWindow(8) - AnimBlend.HALT) < 1e-9)
			check.is_true(math.abs(AnimBlend.haltWindow(0 / 0) - AnimBlend.HALT) < 1e-9)
		end)
		test.case("a start, then a halt", function()
			check.is_true(same(run({ { 0.5, 0, 0 }, { 1, 0, -16 }, { 0.5, 0, 0 } }), { "start", "stop" }))
			-- a halt takes a few frames in the engine: still a halt inside HALT seconds
			check.is_true(
				same(run({ { 0.5, 0, 0 }, { 1, 0, -16 }, { 0.1, 0, -4 }, { 0.5, 0, 0 } }), { "start", "stop" })
			)
		end)
		test.case(
			"a body that takes a few frames to reach pace still starts, and one that settles with a swing still halts",
			function()
				-- (seen in Studio: the first start of a walk was missed - the body passed through half speed for some
				-- frames - and a halt was taken for a turn on the spot because the body swung round as it stopped)
				check.is_true(
					same(run({ { 0.5, 0, 0 }, { 0.15, 0, -4 }, { 1, 0, -16 }, { 0.5, 0, 0 } }), { "start", "stop" })
				)
				check.is_true(same(run({ { 0.5, 0, 0 }, { 1, 0, -16 }, { 0.4, 0, 0, 300 } }), { "start", "stop" }))
				-- the engine's own braking from 16: half a second, the second half of it under pace (measured)
				check.is_true(
					same(
						run({ { 0.5, 0, 0 }, { 1, 0, -16 }, { 0.2, 0, -10 }, { 0.3, 0, -4 }, { 0.5, 0, 0 } }),
						{ "start", "stop" }
					)
				)
				-- turning round where it stands and walking off: the turn, then the start (not held back by the turn)
				check.is_true(same(run({ { 0.5, 0, 0 }, { 0.2, 0, 0, 400 }, { 1, 0, 16 } }), { "turnLeft", "start" }))
				-- a slow walk that only much later breaks into a run is not a start
				check.is_true(same(run({ { 0.5, 0, 0 }, { 1.5, 0, -4 }, { 1, 0, -16 } }), {}))
			end
		)
		test.case("a body that drifts down slowly has not halted, and a slow walk is neither", function()
			check.is_true(same(run({ { 0.5, 0, 0 }, { 1, 0, -16 }, { 0.9, 0, -3 }, { 0.5, 0, 0 } }), { "start" }))
			check.is_true(same(run({ { 0.5, 0, 0 }, { 2, 0, -3 }, { 0.5, 0, 0 } }), {})) -- under half its WalkSpeed
			check.is_true(same(run({ { 0.5, 0, 0 }, { 1, 0, -3 }, { 0.5, 0, 0 } }, 4), { "start", "stop" })) -- its WalkSpeed is 4
		end)
		test.case("a reversal is a pivot, not a stop and a start", function()
			check.is_true(same(run({ { 0.5, 0, 0 }, { 1, 0, -16 }, { 1, 0, 16 } }), { "start", "pivot" }))
			-- through a frame or two of nothing, as the engine does it
			check.is_true(
				same(run({ { 0.5, 0, 0 }, { 1, 0, -16 }, { 0.04, 0, 0 }, { 1, 0, 16 } }), { "start", "pivot" })
			)
			-- one frame back at pace and then still (a body told to stop where it is oversteps): a halt, not a pivot
			check.is_true(
				same(run({ { 0.5, 0, 0 }, { 1, 0, -16 }, { 0.034, 0, 16 }, { 0.5, 0, 0 } }), { "start", "stop" })
			)
			-- a quarter turn while running is the blend's (strafe weights), not a pivot
			check.is_true(same(run({ { 0.5, 0, 0 }, { 1, 0, -16 }, { 1, 16, 0 } }), { "start" }))
		end)
		test.case("the same at eight and twenty frames a second, and at an uneven rate", function()
			local function at(frames: { number }, script: { { number } }): { string }
				local flow = AnimBlend.flow()
				local out: { string } = {}
				local k = 0
				for _, step in script do
					local left = step[1]
					while left > 1e-9 do
						k += 1
						local dt = math.min(frames[(k - 1) % #frames + 1], left)
						left -= dt
						local m = AnimBlend.transition(flow, step[2], step[3], step[4] or 0, dt, 16)
						if m then
							table.insert(out, m)
						end
					end
				end
				return out
			end
			for _, frames in { { 1 / 8 }, { 1 / 20 }, { 1 / 60, 1 / 40, 1 / 20 } } do
				check.is_true(same(at(frames, { { 0.5, 0, 0 }, { 1, 0, -16 }, { 0.6, 0, 0 } }), { "start", "stop" }))
				check.is_true(same(at(frames, { { 0.5, 0, 0 }, { 1, 0, -16 }, { 1, 0, 16 } }), { "start", "pivot" }))
				-- one long frame is not a standstill and not a turn: a reversal through one frame of nothing is still
				-- a pivot, a half-turn in one frame is a teleport
				check.is_true(
					same(
						at(frames, { { 0.5, 0, 0 }, { 1, 0, -16 }, { frames[1], 0, 0 }, { 1, 0, 16 } }),
						{ "start", "pivot" }
					)
				)
				check.is_true(
					same(at(frames, { { 0.5, 0, 0 }, { frames[1], 0, 0, 170 / frames[1] }, { 0.5, 0, 0 } }), {})
				)
			end
		end)
		test.case("a tight U-turn and a slow reversal are pivots; a wide curve and a quarter turn are not", function()
			-- the way it goes swept half round over `seconds` at 16 studs a second
			local function sweep(seconds: number, degrees: number): { { number } }
				local script: { { number } } = { { 0.5, 0, 0 }, { 1, 0, -16 } }
				local n = math.floor(seconds * 60 + 0.5)
				for i = 1, n do
					local a = math.rad(degrees * i / n)
					table.insert(script, { 1 / 60, 16 * math.sin(a), -16 * math.cos(a) })
				end
				local a = math.rad(degrees)
				table.insert(script, { 1, 16 * math.sin(a), -16 * math.cos(a) })
				return script
			end
			check.is_true(same(run(sweep(0.2, 180)), { "start", "pivot" }))
			check.is_true(same(run(sweep(0.4, 180)), { "start", "pivot" }))
			check.is_true(same(run(sweep(2.5, 180)), { "start" })) -- a wide curve: the blend's
			check.is_true(same(run(sweep(0.2, 90)), { "start" }))
			check.is_true(same(run(sweep(0.05, 110)), { "start" })) -- under 120 degrees round
			check.is_true(same(run(sweep(0.05, 135)), { "start", "pivot" }))
			-- a reversal that slows through nothing over 0.6 s (never standing a tenth of a second): a pivot - the
			-- first cut read NOTHING there
			local slow: { { number } } = { { 0.5, 0, 0 }, { 1, 0, -16 } }
			for i = 1, 36 do
				table.insert(slow, { 1 / 60, 0, -16 + 32 * i / 36 })
			end
			table.insert(slow, { 1, 0, 16 })
			check.is_true(same(run(slow), { "start", "pivot" }))
		end)
		test.case("a halt that swings round as it settles is the halt's, however slow the halt", function()
			-- (a slow halt - no stop - then a 300 degrees a second swing within half a second of pace: no turn)
			check.is_true(same(run({ { 0.5, 0, 0 }, { 1, 0, -16 }, { 0.9, 0, -3 }, { 0.3, 0, 0, 300 } }), { "start" }))
			-- ... and once it has stood QUIET seconds, a turn is a turn again
			check.is_true(
				same(
					run({ { 0.5, 0, 0 }, { 1, 0, -16 }, { 0.9, 0, -3 }, { 0.7, 0, 0 }, { 0.3, 0, 0, 300 } }),
					{ "start", "turnLeft" }
				)
			)
		end)
		test.case("standing and turning on the spot: after a moment, one turn at a time", function()
			check.is_true(same(run({ { 0.5, 0, 0 }, { 0.05, 0, 0, 200 } }), {})) -- a flick is not a turn
			check.is_true(same(run({ { 0.5, 0, 0 }, { 0.3, 0, 0, 200 } }), { "turnLeft" }))
			check.is_true(same(run({ { 0.5, 0, 0 }, { 0.3, 0, 0, -200 } }), { "turnRight" }))
			check.is_true(same(run({ { 0.5, 0, 0 }, { 0.3, 0, 0, 80 } }), {})) -- slower than TURN_RATE: the idle carries it
			-- ONE turn a turning: a camera panned steadily round a standing body is one turn, not one every third
			-- of a second for as long as it pans (the first cut: three in 1.2 s)
			check.is_true(same(run({ { 0.5, 0, 0 }, { 1.2, 0, 0, 200 } }), { "turnLeft" }))
			check.is_true(same(run({ { 0.5, 0, 0 }, { 3, 0, 0, -200 } }), { "turnRight" }))
			-- it stops turning, then turns again: a second turn
			check.is_true(
				same(
					run({ { 0.5, 0, 0 }, { 0.3, 0, 0, 200 }, { 0.5, 0, 0 }, { 0.3, 0, 0, 200 } }),
					{ "turnLeft", "turnLeft" }
				)
			)
			-- a SHAKING facing (a camera-locked body: +150 / -150 a frame, or eight frames each way) is no turn
			local shake: { { number } } = { { 0.5, 0, 0 } }
			for i = 1, 180 do
				table.insert(shake, { 1 / 60, 0, 0, if i % 2 == 0 then 150 else -150 })
			end
			check.is_true(same(run(shake), {}))
			local sway: { { number } } = { { 0.5, 0, 0 } }
			for i = 1, 20 do
				table.insert(sway, { 8 / 60, 0, 0, if i % 2 == 0 then 150 else -150 })
			end
			check.is_true(same(run(sway), {}))
			-- one frame that turns the body half round is a teleport or a respawn, not a turn
			check.is_true(same(run({ { 0.5, 0, 0 }, { 1 / 60, 0, 0, 180 * 60 }, { 0.5, 0, 0 } }), {}))
			-- turning WHILE it runs is the run's
			check.is_true(same(run({ { 0.5, 0, 0 }, { 1, 0, -16, 200 } }), { "start" }))
		end)
		test.case("one moment at a time, and numbers that are not numbers begin nothing", function()
			-- start, halt and start again inside the cool-down: the second start waits it out
			local got = run({ { 0.5, 0, 0 }, { 0.2, 0, -16 }, { 0.12, 0, 0 }, { 0.1, 0, -16 }, { 1, 0, -16 } })
			check.is_true(got[1] == "start" and #got <= 3)
			-- a moment the wait holds back is played when the wait ends: a stop is never dropped while its start
			-- was played (tapping walk on and off: starts with no stop between them, the first cut)
			local taps: { { number } } = { { 0.5, 0, 0 } }
			for _ = 1, 6 do
				table.insert(taps, { 0.15, 0, -16 })
				table.insert(taps, { 0.45, 0, 0 })
			end
			local seen = run(taps)
			check.is_true(#seen >= 4)
			for i = 1, #seen do
				check.is_true(seen[i] == (if i % 2 == 1 then "start" else "stop"))
			end
			local flow = AnimBlend.flow()
			check.is_true(AnimBlend.transition(flow, 0 / 0, 0, 0, 1 / 60, 16) == nil)
			check.is_true(AnimBlend.transition(flow, 0, -16, 0, 0, 16) == nil)
			check.is_true(AnimBlend.transition(flow, 0, -16, 0, 0 / 0, 16) == nil)
			check.is_true(flow.t == 0)
			-- a WalkSpeed that is not one: 16
			check.is_true(same(run({ { 0.5, 0, 0 }, { 1, 0, -9 }, { 0.5, 0, 0 } }, 0 / 0), { "start", "stop" }))
		end)
		test.case("the blend plays the set's clip for the moment, entered by pose when it can be", function()
			local anim = fs.readFile("src/kit/Anim.luau")
			for _, line in
				{
					"moment = AnimBlend.transition(flow, over.X, over.Z, turned / math.max(dt, 1e-3), dt, humanoid.WalkSpeed)",
					"local over = velocity - floorVelocity(character, humanoid, root, velocity)",
					"and AnimBlend.onFoot(humanoid:GetState().Name, humanoid.PlatformStand, humanoid.Sit)",
					"flow = AnimBlend.flow()",
					"playMoment(between)",
					"loaded.Priority = Enum.AnimationPriority.Movement",
					"if busy() then",
					"local at = Anim.enterTime(m, Anim.poseOf(character), nil)",
				}
			do
				check.is_true(string.find(anim, line, 1, true) ~= nil)
			end
		end)
	end)
	test.suite("AnimBlend: locomotion weights and rates", function()
		local set = { idle = "Idle", walk = "Walk", run = "Run", strafeLeft = "StrafeL", strafeRight = "StrafeR" }
		local meta =
			{ Walk = { speed = 6.8 }, Run = { speed = 10.8 }, StrafeL = { speed = 5.3 }, StrafeR = { speed = 5.3 } }
		local function total(w: any): number
			local sum = 0
			for _, p in w do
				sum += p.weight
			end
			return sum
		end
		test.case("standing still idles", function()
			local w = AnimBlend.weights(set, meta, Vector3.new(0, 0, -1), 0)
			check.is_true(w.Idle ~= nil and w.Idle.weight == 1 and w.Walk == nil)
		end)
		test.case("full speed forward is the run, at the rate that matches the feet", function()
			local w = AnimBlend.weights(set, meta, Vector3.new(0, 0, -1), 16)
			check.is_true(w.Run ~= nil and math.abs(w.Run.weight - 1) < 1e-6)
			check.is_true(math.abs(w.Run.rate - 16 / 10.8) < 1e-6)
			check.is_true(w.Walk == nil)
		end)
		test.case("between the walk's and the run's speeds both play, weights summing to 1", function()
			local w = AnimBlend.weights(set, meta, Vector3.new(0, 0, -1), 8.8)
			check.is_true(w.Walk ~= nil and w.Run ~= nil)
			check.is_true(math.abs(w.Walk.weight - 0.5) < 1e-6 and math.abs(w.Run.weight - 0.5) < 1e-6)
			check.is_true(math.abs(total(w) - 1) < 1e-6)
		end)
		test.case("a diagonal mixes forward and strafe; no back clip falls back to the walk", function()
			local w = AnimBlend.weights(set, meta, Vector3.new(1, 0, -1).Unit, 6)
			check.is_true(w.StrafeR ~= nil and math.abs(w.StrafeR.weight - 0.5) < 1e-6)
			check.is_true(math.abs(total(w) - 1) < 1e-6)
			local b = AnimBlend.weights(set, meta, Vector3.new(0, 0, 1), 6)
			check.is_true(b.Walk ~= nil and math.abs(b.Walk.weight - 1) < 1e-6)
			check.is_true(b.Walk.rate < 0) -- played in reverse: the planted foot moves the right way
			-- a mostly-backward diagonal on a set with neither back nor strafe clips: still in reverse (rates
			-- blend by weight), and the clamp keeps the sign
			local diag =
				AnimBlend.weights({ idle = "Idle", walk = "Walk", run = "Run" }, meta, Vector3.new(-0.3, 0, 1).Unit, 6)
			check.is_true(diag.Walk ~= nil and math.abs(diag.Walk.weight - 1) < 1e-6)
			check.is_true(diag.Walk.rate <= -AnimBlend.MIN_RATE)
			local up = AnimBlend.weights(set, meta, Vector3.new(0, 1, 0), 6)
			check.is_true(up.Idle ~= nil and up.Idle.weight == 1) -- straight up: no ground direction
		end)
		test.case("a body walked by MoveTo is going the way it moves (its MoveDirection is zero)", function()
			-- seen in Studio 2026-11-15: MoveTo at WalkSpeed 8 and 16, MoveDirection (0, 0, 0), the idle at weight 1
			local x, z = AnimBlend.going(0, 0, 0, 8, 8, true)
			check.is_true(x == 0 and math.abs(z - 1) < 1e-9)
			local w = AnimBlend.weights(set, meta, Vector3.new(x, 0, -1), 8) -- (ahead in the body's own space)
			check.is_true(w.Idle == nil and w.Walk ~= nil and math.abs(total(w) - 1) < 1e-9)
			-- slower than its WalkSpeed: that share; faster (pushed along): 1 at most; sideways keeps its direction
			x, z = AnimBlend.going(0, 0, 3, -4, 10, true)
			check.is_true(math.abs(x - 0.3) < 1e-9 and math.abs(z + 0.4) < 1e-9)
			x, z = AnimBlend.going(0, 0, 30, 0, 8, true)
			check.is_true(math.abs(x - 1) < 1e-9 and z == 0)
			-- what the body is ASKED wins whenever it is asked anything (a player's stick, Humanoid:Move)
			x, z = AnimBlend.going(0.6, 0, 0, 8, 8, true)
			check.is_true(x == 0.6 and z == 0)
			x, z = AnimBlend.going(0, -1, 0, 0, 8, false)
			check.is_true(x == 0 and z == -1)
			-- not on foot (thrown, falling, a ragdoll), slower than an idle, or numbers that are not: going nowhere
			for _, a in
				{
					{ 0, 0, 0, 20, 8, false },
					{ 0, 0, 0, 0.3, 8, true },
					{ 0, 0, 0 / 0, 8, 8, true },
					{ 0, 0, math.huge, 0, 8, true },
					{ 0 / 0, 0, 0, 0, 8, true },
				}
			do
				local gx, gz = AnimBlend.going(a[1], a[2], a[3], a[4], a[5], a[6])
				check.is_true(gx == 0 and gz == 0)
			end
			-- a WalkSpeed of 0 or not a number: the direction alone
			x, z = AnimBlend.going(0, 0, 0, -6, 0, true)
			check.is_true(x == 0 and z == -1)
		end)
		test.case("on foot is a walking state on a body that is not flung or seated", function()
			for _, state in { "Running", "RunningNoPhysics", "Landed" } do
				check.is_true(AnimBlend.onFoot(state, false, false))
				-- (a ragdoll knocked on another machine can still read Running here: PlatformStand says it)
				check.is_true(not AnimBlend.onFoot(state, true, false))
				check.is_true(not AnimBlend.onFoot(state, false, true))
			end
			for _, state in
				{ "Freefall", "Jumping", "Physics", "FallingDown", "Ragdoll", "GettingUp", "Dead", "Swimming", "" }
			do
				check.is_true(not AnimBlend.onFoot(state, false, false))
			end
			-- a body standing on a floor that moves at 10: its velocity AGAINST THE FLOOR is nothing - going nowhere
			local x, z = AnimBlend.going(0, 0, 0 - 0, 10 - 10, 16, AnimBlend.onFoot("Running", false, false))
			check.is_true(x == 0 and z == 0)
		end)
		test.case("the runtime reads the way a body is going in one place", function()
			local anim = fs.readFile("src/kit/Anim.luau")
			-- (the rule inside Anim.going, not only its callers: put back to MoveDirection alone, these fail)
			check.is_true(
				string.find(anim, "AnimBlend.going(move.X, move.Z, v.X, v.Z, humanoid.WalkSpeed, onFoot)", 1, true)
					~= nil
			)
			check.is_true(
				string.find(
					anim,
					"AnimBlend.onFoot(humanoid:GetState().Name, humanoid.PlatformStand, humanoid.Sit)",
					1,
					true
				) ~= nil
			)
			check.is_true(string.find(anim, "v -= floorVelocity(character, humanoid, root, v)", 1, true) ~= nil)
			local _, n = string.gsub(anim, "%.MoveDirection", "")
			check.equal(n, 1) -- (Anim.going alone: locomotion and steering ask it)
			check.is_true(string.find(anim, "root.CFrame:VectorToObjectSpace(Anim.going(humanoid))", 1, true) ~= nil)
			check.is_true(string.find(anim, "Anim.going(steerHum), steerRoot.CFrame.LookVector", 1, true) ~= nil)
			local moves = fs.readFile("src/kit/Moves.luau")
			check.is_true(string.find(moves, "MoveDirection.Magnitude", 1, true) == nil)
			check.is_true(string.find(moves, "Anim.going(hum).Magnitude > MovesRules.MOVING", 1, true) ~= nil)
		end)
		test.case("rates are clamped", function()
			local w = AnimBlend.weights(set, meta, Vector3.new(0, 0, -1), 100)
			check.is_true(w.Run.rate == AnimBlend.MAX_RATE)
		end)
		test.case("a set without a walk still carries full weight on what it has", function()
			local small = { idle = "Idle", run = "Run" }
			local b = AnimBlend.weights(small, meta, Vector3.new(0, 0, 1), 6)
			check.is_true(b.Run ~= nil and math.abs(b.Run.weight - 1) < 1e-6)
			local l = AnimBlend.weights(small, meta, Vector3.new(-1, 0, 0), 6)
			check.is_true(l.Run ~= nil and math.abs(total(l) - 1) < 1e-6)
			local only = AnimBlend.weights({ idle = "Idle" }, meta, Vector3.new(0, 0, -1), 6)
			check.is_true(only.Idle ~= nil and only.Idle.weight == 1)
		end)
	end)
	test.suite("AnimFeel.rootAt: a one-shot's root motion (a dash moves the character)", function()
		test.case("interpolates the root track, clamps to the clip, turns the short way", function()
			local s = math.sin(math.rad(170) / 2)
			local c = math.cos(math.rad(170) / 2)
			local s2 = math.sin(math.rad(-170) / 2)
			local c2 = math.cos(math.rad(-170) / 2)
			local root = {
				{ 0, 0, 0, 1, 0, 0, 0 },
				{ 0, s, 0, c, 0, 0, -6 },
				{ 0, s2, 0, c2, 1, 0, -12 },
			}
			local x, y, z, yaw = AnimFeel.rootAt(root, 30, 0.5 / 30) -- halfway into the first step
			check.is_true(math.abs(z + 3) < 1e-9 and x == 0 and y == 0)
			check.is_true(math.abs(yaw - math.rad(85)) < 1e-6)
			local _, _, zEnd = AnimFeel.rootAt(root, 30, 10) -- past the end: the last frame
			check.is_true(zEnd == -12)
			local _, _, _, mid = AnimFeel.rootAt(root, 30, 1.5 / 30) -- 170 -> -170 deg: through 180, not through 0
			check.is_true(math.abs(math.abs(mid) - math.pi) < 1e-6)
			local cx, cy, cz, cyaw = AnimFeel.rootAt({ { 0, 0, 0 }, { 2, -6, 0.5 } }, 30, 0.5 / 30) -- the compact form
			check.is_true(cx == 1 and cy == 0 and cz == -3 and math.abs(cyaw - 0.25) < 1e-9)
			local x0, _, z0, y0 = AnimFeel.rootAt({}, 30, 1)
			check.is_true(x0 == 0 and z0 == 0 and y0 == 0)
		end)
	end)
	test.suite("AnimFeel: the critically damped spring and the runtime lean", function()
		test.case("the spring reaches its goal without overshoot, frame-rate independent", function()
			local s: any = { x = 0, v = 0 }
			local maxX = 0
			for _ = 1, 300 do
				s = AnimFeel.spring(s, 1, 0.1, 1 / 60)
				maxX = math.max(maxX, s.x)
			end
			check.is_true(math.abs(s.x - 1) < 1e-3)
			check.is_true(maxX <= 1 + 1e-6)
			local one = AnimFeel.spring({ x = 0, v = 0 }, 1, 0.2, 0.1)
			local ten: any = { x = 0, v = 0 }
			for _ = 1, 10 do
				ten = AnimFeel.spring(ten, 1, 0.2, 0.01)
			end
			check.is_true(math.abs(one.x - ten.x) < 1e-9 and math.abs(one.v - ten.v) < 1e-9)
		end)
		test.case("the lean follows speed, leans harder while accelerating, and is clamped", function()
			local st = AnimFeel.newLean()
			local pitch, roll = 0, 0
			for _ = 1, 240 do -- running forward at 16 studs/s (forward is -Z)
				st, pitch, roll = AnimFeel.lean(st, 0, -16, 1 / 60)
			end
			check.is_true(math.abs(pitch - 16 * AnimFeel.LEAN_DEFAULTS.speedPitch) < 1e-3 and math.abs(roll) < 1e-6)
			local st2 = AnimFeel.newLean()
			local p2 = 0
			for i = 1, 12 do -- pushing off: speed rising 0 -> 16 in 0.2 s
				st2, p2 = AnimFeel.lean(st2, 0, -16 * i / 12, 1 / 60)
			end
			check.is_true(p2 > 16 * AnimFeel.LEAN_DEFAULTS.speedPitch)
			local st3 = AnimFeel.newLean()
			local p3 = 0
			for _ = 1, 600 do
				st3, p3 = AnimFeel.lean(st3, 0, -5000, 1 / 60)
			end
			check.is_true(p3 <= AnimFeel.LEAN_DEFAULTS.maxPitch + 1e-9)
		end)
	end)
end

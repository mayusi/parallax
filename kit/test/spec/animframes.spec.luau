-- animframes.spec.luau — ONE FRAME CONVENTION, PROVEN ON THE LUAU ROUTES (the owner's older list, AN-03): the
-- calibration motion of kit/anim/frame_contract.py (five poses, each moving one thing whose place is written by hand:
-- kit/selftest/anim/frame_contract.json) goes through kit/lib/anim.luau modelFromClip - the KeyframeSequence's Poses,
-- what the engine is given - and the parts are put together HERE from those Poses and the rig's joints alone
-- (part = parent x C0 x Pose x C1 inverse). The places must be the contract's; a mirrored, axis-swapped or metre copy
-- must not. The R15 -> R6 fold keeps a turn's sense.
local frk = require("../frk")
local fs = require("@lune/fs")
local serde = require("@lune/serde")
local test, check = frk.test, frk.check

local Anim = require("../../lib/anim")

type M = { { number } } -- 3 rows of a rotation
type F = { r: M, p: { number } }

local function mul(a: M, b: M): M
	local m = { { 0, 0, 0 }, { 0, 0, 0 }, { 0, 0, 0 } }
	for i = 1, 3 do
		for j = 1, 3 do
			m[i][j] = a[i][1] * b[1][j] + a[i][2] * b[2][j] + a[i][3] * b[3][j]
		end
	end
	return m
end

local function apply(a: M, v: { number }): { number }
	return {
		a[1][1] * v[1] + a[1][2] * v[2] + a[1][3] * v[3],
		a[2][1] * v[1] + a[2][2] * v[2] + a[2][3] * v[3],
		a[3][1] * v[1] + a[3][2] * v[2] + a[3][3] * v[3],
	}
end

local function transpose(a: M): M
	return { { a[1][1], a[2][1], a[3][1] }, { a[1][2], a[2][2], a[3][2] }, { a[1][3], a[2][3], a[3][3] } }
end

local function compose(a: F, b: F): F
	local p = apply(a.r, b.p)
	return { r = mul(a.r, b.r), p = { a.p[1] + p[1], a.p[2] + p[2], a.p[3] + p[3] } }
end

local function inverse(a: F): F
	local t = transpose(a.r)
	local p = apply(t, a.p)
	return { r = t, p = { -p[1], -p[2], -p[3] } }
end

-- a CFrame as the rig holds it: the place, then the rotation's rows
local function of12(c: { number }): F
	return { r = { { c[4], c[5], c[6] }, { c[7], c[8], c[9] }, { c[10], c[11], c[12] } }, p = { c[1], c[2], c[3] } }
end

local IDENT: F = { r = { { 1, 0, 0 }, { 0, 1, 0 }, { 0, 0, 1 } }, p = { 0, 0, 0 } }

-- every keyframe's named points, from the model's Poses and the rig's joints only
local function placesOf(model: any, info: any, points: { [string]: any }): { { [string]: { number } } }
	local out = {}
	for _, kf in model.Children do
		local poses: { [string]: F } = {}
		local function walk(node: any)
			if node.ClassName == "Pose" then
				local cf = node.Properties.CFrame.CFrame
				poses[node.Name] = { r = cf.orientation, p = cf.position }
				for _, c in node.Children or {} do
					walk(c)
				end
			end
		end
		for _, c in kf.Children do
			walk(c)
		end
		local world: { [string]: F } = { [info.root] = IDENT }
		for _, part in info.order do
			local j = info.joints[part]
			world[part] =
				compose(compose(compose(world[j.parent], of12(j.c0)), poses[part] or IDENT), inverse(of12(j.c1)))
		end
		local row = {}
		for name, at in points do
			local w = world[at[1]]
			local p = apply(w.r, at[2])
			row[name] = { w.p[1] + p[1], w.p[2] + p[2], w.p[3] + p[3] }
		end
		table.insert(out, row)
	end
	return out
end

local function offBy(got: { { [string]: { number } } }, expected: { { [string]: { number } } }, tol: number): number
	local off = 0
	if #got ~= #expected then
		return math.huge
	end
	for i, e in expected do
		for name, want in e do
			local g = got[i][name]
			local d = math.sqrt((g[1] - want[1]) ^ 2 + (g[2] - want[2]) ^ 2 + (g[3] - want[3]) ^ 2)
			if not (d <= tol) then
				off += 1
			end
		end
	end
	return off
end

local function deep(v: any): any
	if type(v) ~= "table" then
		return v
	end
	local c = {}
	for k, x in v do
		c[k] = deep(x)
	end
	return c
end

return function()
	local contract = serde.decode("json", fs.readFile("kit/selftest/anim/frame_contract.json"))

	test.suite("one frame convention: the calibration motion through the kit's Luau routes (AN-03)", function()
		test.case("the KeyframeSequence the kit compiles puts every part where the contract has it", function()
			local model, info, issues = Anim.modelFromClip(deep(contract.clip), "R6")
			check.truthy(model)
			check.is_true(#issues == 0)
			check.is_true(#model.Children == 6)
			check.is_true(offBy(placesOf(model, info, contract.points), contract.expected, contract.tol) == 0)
			-- (the hand's own numbers, said here too: the right arm ahead, the left arm out to the LEFT)
			local places = placesOf(model, info, contract.points)
			check.is_true(
				math.abs(places[2].right_hand[3] - -1.5) < 0.01 and math.abs(places[2].right_hand[1] - 1.5) < 0.01
			)
			check.is_true(
				math.abs(places[3].left_hand[1] - -2.5) < 0.01 and math.abs(places[3].left_hand[2] - 1) < 0.01
			)
			check.is_true(math.abs(places[4].face[1] - -0.5) < 0.01)
		end)
		test.case("a mirrored, an axis-swapped and a metre copy do NOT", function()
			local function with(fn: ({ number }) -> { number }): number
				local clip = deep(contract.clip)
				for _, j in clip.joints do
					for i, f in j.frames do
						j.frames[i] = fn(f)
					end
				end
				local model, info = Anim.modelFromClip(clip, "R6")
				return offBy(placesOf(model, info, contract.points), contract.expected, contract.tol)
			end
			check.is_true(with(function(f)
				return { -f[1], -f[2], -f[3], f[4], f[5], f[6], f[7] } -- left-handed turns
			end) > 0)
			check.is_true(with(function(f)
				return { f[1], -f[2], -f[3], f[4], -f[5], f[6], f[7] } -- the right on -X
			end) > 0)
			check.is_true(with(function(f)
				return { f[1], f[3], f[2], f[4], f[5], f[7], f[6] } -- up and ahead swapped
			end) > 0)
			check.is_true(with(function(f)
				return { -f[1], f[2], -f[3], f[4], f[5], f[6], -f[7] } -- ahead is +Z
			end) > 0)
			check.is_true(with(function(f)
				return { f[1], f[2], f[3], f[4], f[5] * 0.28, f[6] * 0.28, f[7] * 0.28 } -- metres
			end) > 0)
			-- and the check itself is not a thing that fails everything: the clip as it is, again
			check.is_true(with(function(f)
				return f
			end) == 0)
		end)
		test.case("the R15 -> R6 fold keeps a turn's sense: ahead stays ahead, left stays left", function()
			local s, c = math.sin(math.pi / 4), math.cos(math.pi / 4)
			local rest = { 0, 0, 0, 1, 0, 0, 0 }
			local function r15(moved: { [string]: { number } }): any
				local joints = {}
				for name in Anim.RIGS.R15.joints do
					joints[name] = { frames = { table.clone(rest), table.clone(moved[name] or rest) } }
				end
				return {
					schema = 1,
					name = "Cal15",
					rig = "R15",
					fps = 30,
					loop = false,
					times = { 0, 1 / 30 },
					events = {},
					joints = joints,
				}
			end
			-- (the fold aims an arm at the source's wrist, so its turn is not the upper arm's own: the PLACE is held)
			local function last(moved: { [string]: { number } }): { [string]: { number } }
				local model, info = Anim.modelFromClip((Anim.foldToR6(r15(moved))), "R6")
				local places = placesOf(model, info, contract.points)
				return places[#places]
			end
			local ahead = last({ RightUpperArm = { s, 0, 0, c, 0, 0, 0 } })
			check.is_true(ahead.right_hand[3] < -1.2 and ahead.right_hand[2] > 0.2) -- ahead (-Z) and up, not behind
			check.is_true(math.abs(ahead.left_hand[1] - -1.5) < 0.02 and math.abs(ahead.left_hand[2] - -1) < 0.02)
			local out = last({ LeftUpperArm = { 0, 0, -s, c, 0, 0, 0 } })
			check.is_true(out.left_hand[1] < -2.2 and out.left_hand[2] > 0.5) -- out to the LEFT (-X), not the right
			local turned = last({ Head = { 0, s, 0, c, 0, 0, 0 } })
			check.is_true(math.abs(turned.face[1] - -0.5) < 0.02 and math.abs(turned.face[3]) < 0.02) -- the face to the left
			local stepped = last({ RightUpperLeg = { s, 0, 0, c, 0, 0, 0 } })
			check.is_true(stepped.right_sole[3] < -1.2 and math.abs(stepped.right_sole[1] - 0.5) < 0.05) -- the leg ahead
			check.is_true(math.abs(stepped.left_sole[1] - -0.5) < 0.05 and math.abs(stepped.left_sole[3]) < 0.05) -- the other stands
			check.is_true(math.abs(ahead.right_sole[3]) < 0.05 and math.abs(out.right_hand[1] - 1.5) < 0.05)
		end)
		test.case("the kept KeyframeSequence dump is what the kit compiles today", function()
			-- (kit/test/python/test_anim_frame_contract.py imports this file back through kit/anim/kfs_import.py)
			local Dump = require("../../selftest/anim/frame_contract_dump")
			local kept = serde.decode("json", fs.readFile("kit/selftest/anim/frame_contract.kfs.json"))
			local now = Dump.of(deep(contract.clip))
			check.is_true(#kept.keyframes == #now.keyframes and #now.keyframes == 6)
			for i, kf in now.keyframes do
				check.is_true(math.abs(kept.keyframes[i].t - kf.t) < 1e-9)
				for part, pose in kf.poses do
					for k = 1, 12 do
						check.is_true(math.abs(kept.keyframes[i].poses[part].cf[k] - pose.cf[k]) < 1e-9)
					end
				end
			end
		end)
		test.case(
			"the weapon's own joint: the compiled Handle pose puts the blade where the contract has it",
			function()
				-- kit/lib/anim.luau writes the clip's `grip` track as a "Handle" Pose under the Right Arm; the game builds that
				-- joint with RightGrip's C0 (src/kit/AnimGrip). The weapon = the arm x that C0 x the Pose, put together here.
				local AnimGrip = require("../../../src/kit/AnimGrip")
				local model, info = Anim.modelFromClip(deep(contract.clip), "R6")
				local g = AnimGrip.GRIP_C0
				local c0: F = {
					r = { { g[1][1], g[1][2], g[1][3] }, { g[2][1], g[2][2], g[2][3] }, { g[3][1], g[3][2], g[3][3] } },
					p = { g[1][4], g[2][4], g[3][4] },
				}
				for index, want in contract.weapon do
					local kf = model.Children[tonumber(index) :: number + 1]
					local poses: { [string]: F } = {}
					local function walk(node: any)
						if node.ClassName == "Pose" then
							local cf = node.Properties.CFrame.CFrame
							poses[node.Name] = { r = cf.orientation, p = cf.position }
							for _, c in node.Children or {} do
								walk(c)
							end
						end
					end
					for _, c in kf.Children do
						walk(c)
					end
					local world: { [string]: F } = { [info.root] = IDENT }
					for _, part in info.order do
						local j = info.joints[part]
						world[part] = compose(
							compose(compose(world[j.parent], of12(j.c0)), poses[part] or IDENT),
							inverse(of12(j.c1))
						)
					end
					local handle = compose(compose(world["Right Arm"], c0), poses.Handle or IDENT)
					local tip = apply(handle.r, { 0, contract.blade, 0 })
					local edge = apply(handle.r, { -1, 0, 0 }) -- (the weapon's -X is its edge)
					local got = {
						weapon_grip = handle.p,
						weapon_tip = { handle.p[1] + tip[1], handle.p[2] + tip[2], handle.p[3] + tip[3] },
						weapon_edge = { handle.p[1] + edge[1], handle.p[2] + edge[2], handle.p[3] + edge[3] },
					}
					for name, at in want do
						local d = math.sqrt(
							(got[name][1] - at[1]) ^ 2 + (got[name][2] - at[2]) ^ 2 + (got[name][3] - at[3]) ^ 2
						)
						check.is_true(d <= contract.tol)
					end
				end
				check.is_true(contract.weapon["3"].weapon_tip[1] == -1.5) -- (the blade to the body's LEFT)
				check.is_true(contract.weapon["1"].weapon_grip[2] == 1.5) -- (with the arm lifted, the grip rides UP with it)
			end
		)
		test.case("the fixture is the contract's own file, and the contract names its routes", function()
			local src = fs.readFile("kit/anim/frame_contract.py")
			for _, line in
				{
					"_with(right_hand=(1.5, 0.5, -1.5)),",
					"_with(left_hand=(-2.5, 1.0, 0.0)),",
					"_with(face=(-0.5, 1.5, 0.0)),",
					"kit/test/spec/animframes.spec.luau",
				}
			do
				check.truthy(string.find(src, line, 1, true) ~= nil)
			end
			check.is_true(#contract.expected == 6 and contract.tol == 0.01)
			check.is_true(contract.expected[2].right_hand[3] == -1.5)
		end)
	end)
end

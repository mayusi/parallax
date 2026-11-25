-- animstack.spec.luau — SEVERAL RUNTIME LAYERS ON ONE JOINT (the owner's list, AN-29: "layer interaction needs
-- adversarial validation ... without transform accumulation"). The rule: src/kit/AnimLayers stackBase / stackWrite /
-- stackRelease, one record a joint shared by look-at, additive and feet (src/kit/Anim). A joint's value is a NUMBER
-- here (an angle); a layer adds its own offset to the base it is given. Seen in Studio before the rule (2026-11-15):
-- two look-at layers on a still neck read 121, 75, 39 degrees and left it turned after both had stopped.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local L = require("../../../src/kit/AnimLayers")

local function same(a: number, b: number): boolean
	return math.abs(a - b) < 1e-3
end

-- a joint with layers on it, stepped frame by frame. animator: the value a track writes each frame (nil: no track
-- drives the joint - what it holds stands). layers: the offset each adds, in the order they run
local function run(
	frames: number,
	animator: ((frame: number) -> number?)?,
	layers: (frame: number) -> { number }
): { number }
	local stack = L.newStack()
	stack.users = 99 -- (who is on the joint is not what these cases are about)
	local joint = 0
	local seen = {}
	for f = 1, frames do
		local a = if animator then animator(f) else nil
		if a then
			joint = a
		end
		for _, offset in layers(f) do
			local base = L.stackBase(stack, joint, f, same)
			joint = base + offset
			L.stackWrite(stack, joint)
			-- (the engine reads a value back a hair off what was written)
			joint += 1e-5
		end
		table.insert(seen, joint)
	end
	return seen
end

local function near(a: number, b: number): boolean
	return math.abs(a - b) < 1e-2
end

return function()
	test.suite("AnimLayers: several layers on one joint", function()
		test.case("one layer on a joint nothing animates does not compound", function()
			local seen = run(200, nil, function()
				return { 30 }
			end)
			check.truthy(near(seen[1], 30) and near(seen[200], 30))
		end)
		test.case("two layers on a joint nothing animates stack once and stay there", function()
			-- (each keeping its own record, the first took the second's write for the Animator's: 45, 135, 225 ...)
			local seen = run(200, nil, function()
				return { 30, 15 }
			end)
			for _, f in { 1, 2, 3, 50, 200 } do
				check.truthy(near(seen[f], 45))
			end
			local three = run(100, nil, function()
				return { 10, 20, 5 }
			end)
			check.truthy(near(three[1], 35) and near(three[100], 35))
		end)
		test.case("layers follow their own changing offsets on a still joint", function()
			local seen = run(60, nil, function(f)
				return { f, -2 * f }
			end)
			check.truthy(near(seen[1], -1) and near(seen[40], -40) and near(seen[60], -60))
		end)
		test.case("a track that rewrites the joint every frame is the base, whatever the layers left", function()
			local seen = run(120, function(f)
				return 100 + f
			end, function()
				return { 30, 15 }
			end)
			check.truthy(near(seen[1], 146) and near(seen[120], 265))
			-- a track that HOLDS one pose (writes the same value every frame) is still the base, not the layers' write
			local held = run(120, function()
				return 100
			end, function()
				return { 30, 15 }
			end)
			check.truthy(near(held[1], 145) and near(held[120], 145))
		end)
		test.case(
			"a track that starts or stops driving the joint mid-way hands over without a jump of its own",
			function()
				-- no track for 20 frames, a track for 20, none again: the joint then holds the track's last value under the layers
				local seen = run(60, function(f)
					return if f > 20 and f <= 40 then 80 else nil
				end, function()
					return { 30, 15 }
				end)
				check.truthy(near(seen[20], 45) and near(seen[21], 125) and near(seen[40], 125))
				check.truthy(near(seen[41], 125) and near(seen[60], 125))
			end
		)
		test.case("a layer that skips frames, and layers that come and go, do not compound", function()
			local seen = run(90, nil, function(f)
				local out = { 30 }
				if f % 3 == 0 then
					table.insert(out, 15) -- (a crowd's far character: animated every third frame)
				end
				if f > 30 and f <= 60 then
					table.insert(out, 7)
				end
				return out
			end)
			check.truthy(near(seen[1], 30) and near(seen[3], 45) and near(seen[4], 30))
			check.truthy(near(seen[33], 52) and near(seen[34], 37) and near(seen[61], 30) and near(seen[90], 45))
		end)
		test.case(
			"the last layer to leave gives the joint its clean value back; an earlier one gives nothing",
			function()
				local stack = L.newStack()
				stack.users = 2
				local joint = 12 -- (what the joint held before any layer)
				for f = 1, 5 do
					joint = L.stackBase(stack, joint, f, same) + 30
					L.stackWrite(stack, joint)
					joint = L.stackBase(stack, joint, f, same) + 15
					L.stackWrite(stack, joint)
				end
				check.truthy(near(joint, 57))
				check.truthy(L.stackRelease(stack, joint, same) == nil) -- one layer is still on it
				check.equal(stack.users, 1)
				joint = L.stackBase(stack, joint, 6, same) + 30 -- the one left builds on the clean value by itself
				L.stackWrite(stack, joint)
				check.truthy(near(joint, 42))
				local back = L.stackRelease(stack, joint, same)
				check.truthy(back ~= nil and near(back :: number, 12))
				check.equal(stack.users, 0)
				-- a joint a track took over is not put back (the track's value stands)
				local driven = L.newStack()
				driven.users = 1
				local j = L.stackBase(driven, 5, 1, same) + 30
				L.stackWrite(driven, j)
				check.truthy(L.stackRelease(driven, 90, same) == nil)
				-- a release with nothing written, and one release too many
				local empty = L.newStack()
				check.truthy(L.stackRelease(empty, 0, same) == nil)
				check.equal(empty.users, 0)
			end
		)
		test.case("a frame number that stands still does not make a layer stack on its own write", function()
			-- (frames 1 2 2 2 3 4: the same number three frames running - a clock that stood still. Without knowing
			-- WHO asked, one layer of 30 read 30 30 60 90 30 30)
			for _, layers in { { "a" }, { "a", "b" } } do
				local stack = L.newStack()
				stack.users = 9
				local joint, seen = 0, {}
				for _, stamp in { 1, 2, 2, 2, 3, 4 } do
					for _, who in layers do
						joint = L.stackBase(stack, joint, stamp, same, who) + (if who == "a" then 30 else 15)
						L.stackWrite(stack, joint)
					end
					table.insert(seen, joint)
				end
				for _, v in seen do
					check.truthy(near(v, if #layers == 1 then 30 else 45))
				end
			end
		end)
		test.case("layers that join and leave over time, in any order, leave the joint as they found it", function()
			-- a straightforward model: the joint is the clean value plus each layer on it, once
			local seed = 7
			local function rnd(n: number): number
				seed = (seed * 1103515245 + 12345) % 2147483648
				return seed % n
			end
			for _ = 1, 200 do
				local stack = L.newStack()
				local clean, joint = rnd(50), 0
				joint = clean
				local on: { [string]: number } = {}
				for frame = 1, 60 do
					for _, who in { "a", "b", "c" } do
						if on[who] == nil and rnd(6) == 0 then
							on[who] = 5 + rnd(40)
							stack.users += 1
						elseif on[who] ~= nil and rnd(8) == 0 then
							on[who] = nil
							local back = L.stackRelease(stack, joint, same)
							if back ~= nil then
								joint = back
							end
						end
					end
					local want = clean
					local order = { "a", "b", "c" }
					if rnd(2) == 0 then
						order = { "c", "a", "b" } -- (which layer runs first is not ours to choose)
					end
					for _, who in order do
						if on[who] ~= nil then
							joint = L.stackBase(stack, joint, frame, same, who) + on[who]
							L.stackWrite(stack, joint)
							want += on[who]
						end
					end
					check.truthy(near(joint, want))
				end
			end
		end)
		test.case("the value under the layers, read outside a frame", function()
			local stack = L.newStack()
			local joint = L.stackBase(stack, 12, 1, same, "a") + 30
			L.stackWrite(stack, joint)
			check.truthy(near(L.stackClean(stack, joint, same), 12)) -- the joint holds the layers' write: the clean value
			check.truthy(near(L.stackClean(stack, 77, same), 77)) -- a track rewrote it: what it holds
			check.truthy(near(L.stackClean(L.newStack(), 5, same), 5))
			check.truthy(L.stackOf(stack) == L.stackOf(stack) and L.stackOf(stack) ~= L.stackOf({}))
		end)
		test.case("the runtime's three layers use the one record", function()
			local anim = fs.readFile("src/kit/Anim.luau")
			local _, bases = string.gsub(anim, "layerBase%(", "")
			check.equal(bases, 8) -- (the function; look-at's neck, torso and hips; additive; feet; the starting blend's two)
			local rag = fs.readFile("src/kit/AnimRagdoll.luau")
			check.truthy(
				string.find(rag, "AnimLayers.stackBase(stack, m.Transform, frame, sameCF, joined)", 1, true) ~= nil
			)
			check.truthy(string.find(rag, "AnimLayers.stackWrite(stack, cf)", 1, true) ~= nil)
			check.truthy(string.find(rag, "written[m] = cf", 1, true) == nil) -- (the get-up keeps no record of its own)
			for _, line in
				{
					"return AnimLayers.stackBase(stack, motor.Transform, frame, sameCF, mem)",
					"AnimLayers.stackWrite(AnimLayers.stackOf(motor), value)",
					"local back = AnimLayers.stackRelease(AnimLayers.stackOf(motor), motor.Transform, sameCF)",
					-- the blend when a clip starts is one of the layers, and measures against the clip's own pose
					"(before :: any)[m] = layerClean(m)",
					"local new = AnimLayers.stackOf(m).clean or m.Transform",
					"if stopped then -- (a handler still called after its stop would join the joint again for good)",
					"local neckWas = layerBase(motor, mem, frame)",
					"layerBase(motor, mem, frame) * CFrame.new():Lerp(d, w))",
					"layerBase(m, mem, stamp)",
					"stamp = frame",
				}
			do
				check.truthy(string.find(anim, line, 1, true) ~= nil)
			end
			check.truthy(string.find(anim, "written = {}, clean = {}", 1, true) == nil) -- (no layer keeps its own record)
		end)
		test.case("a layer that writes a WHOLE pose keeps the offset of the layers before it, not its own", function()
			-- (src/kit/AnimRagdoll's get-up blend writes the pose it wants - the clip's under it plus the eased offset
			-- or the root's hold - and keeps on top what layers before it laid on the joint this frame. Seen in Studio
			-- 2026-11-20 (tests/playtest/anim_getup_root): a get-up from a 4 deg tilt laid the torso over to 79 deg,
			-- because "what the layers before laid on" was measured from what the joint HOLDS - on a joint no track
			-- drives that is the blend's own write of the frame before, laid on again every frame.)
			local function blend(measureFromBase: boolean, animator: boolean, before: number): { number }
				local stack = L.newStack()
				stack.users = 99
				local joint, seen = 0, {}
				for f = 1, 30 do
					if animator then
						joint = 0 -- (a track writes the clip's 0 every frame)
					end
					if before ~= 0 then -- a layer that runs before the blend this frame (a look-at): its offset
						joint = L.stackBase(stack, joint, f, same, "look") + before
						L.stackWrite(stack, joint)
					end
					local base = L.stackBase(stack, joint, f, same, "blend")
					local want = (stack.clean :: number) + 10 * (1 - f / 30) -- the clip's pose plus the eased hold
					local over = (if measureFromBase then base else joint) - (stack.clean :: number)
					joint = want + over
					L.stackWrite(stack, joint)
					joint += 1e-5 -- (read back a hair off)
					table.insert(seen, joint - before)
				end
				return seen
			end
			for _, animator in { false, true } do
				for _, before in { 0, 15 } do
					local got = blend(true, animator, before)
					for f, v in got do
						check.truthy(near(v, 10 * (1 - f / 30)))
					end
				end
			end
			-- the old measure: on a joint no track drives, the hold is laid on again every frame (10 + 9.7 + ...)
			check.truthy(blend(false, false, 0)[5] > 40)
			-- the runtime measures from the base stackBase gives (the limbs' and the root joint's both)
			local rag = fs.readFile("src/kit/AnimRagdoll.luau")
			check.truthy(
				string.find(rag, "bases[m] = AnimLayers.stackBase(stack, m.Transform, frame, sameCF, joined)", 1, true)
					~= nil
			)
			check.truthy(string.find(rag, "(bases[m] or m.Transform) * stack.clean:Inverse()", 1, true) ~= nil)
			check.truthy(
				string.find(
					rag,
					"local base = AnimLayers.stackBase(stack, rj.Transform, frame, sameCF, joined)",
					1,
					true
				) ~= nil
			)
			check.truthy(string.find(rag, "then base * stack.clean:Inverse()", 1, true) ~= nil)
			check.truthy(string.find(rag, "then m.Transform * stack.clean:Inverse()", 1, true) == nil)
			check.truthy(string.find(rag, "then rj.Transform * stack.clean:Inverse()", 1, true) == nil)
		end)
	end)
end

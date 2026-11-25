-- handoff_model.luau — `lune run kit/selftest/anim/handoff_model.luau <clip.json>`: the clip compiled by
-- kit/lib/anim.luau modelFromClip for R6, and every Pose that is not a body part (an object a clip carries on a
-- joint of its own: kit/anim/handoff.py clip.props) printed as one JSON line {keyframes, objects: {name: {parent,
-- cfs}}} - kit/test/python/test_anim_handoff.py holds it to the track the clip carries
local Anim = require("../../lib/anim")
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local clip = serde.decode("json", fs.readFile(process.args[1]))
local model = Anim.modelFromClip(clip, "R6")
local body = { HumanoidRootPart = true, Torso = true, Head = true }
for _, n in { "Left Arm", "Right Arm", "Left Leg", "Right Leg", "Handle" } do
	body[n] = true
end
local objects, count = {}, 0
for _, kf in model.Children do
	if kf.ClassName ~= "Keyframe" then
		continue
	end
	count += 1
	local function walk(node: any, parent: string?)
		if node.ClassName ~= "Pose" then
			return
		end
		if not body[node.Name] then
			local o = objects[node.Name] or { parent = parent, cfs = {} }
			objects[node.Name] = o
			local cf = node.Properties.CFrame.CFrame
			table.insert(o.cfs, { kf.Properties.Time, cf.position, cf.orientation })
		end
		for _, c in node.Children or {} do
			walk(c, node.Name)
		end
	end
	for _, c in kf.Children or {} do
		walk(c, nil)
	end
end
print(serde.encode("json", { keyframes = count, objects = objects }))

-- frame_contract_dump.luau — the calibration motion (kit/selftest/anim/frame_contract.json, written by
-- kit/anim/frame_contract.py) compiled by kit/lib/anim.luau modelFromClip, as the KeyframeSequence DUMP that
-- kit/anim/kfs_import.py reads ({ keyframes = { { t, poses = { [part] = { cf = 12 numbers } } } } }):
--   lune run kit/selftest/anim/frame_contract_write.luau         -> kit/selftest/anim/frame_contract.kfs.json
-- kit/test/spec/animframes.spec.luau holds the kept file to what this gives today; kit/test/python/
-- test_anim_frame_contract.py imports it back and holds the result to the contract.
local Anim = require("../../lib/anim")

local Dump = {}

function Dump.of(clip: any): any
	local model = Anim.modelFromClip(clip, "R6")
	local keyframes = {}
	for _, kf in model.Children do
		local poses = {}
		local function walk(node: any)
			if node.ClassName == "Pose" then
				local cf = node.Properties.CFrame.CFrame
				local o, p = cf.orientation, cf.position
				poses[node.Name] = {
					cf = {
						p[1],
						p[2],
						p[3],
						o[1][1],
						o[1][2],
						o[1][3],
						o[2][1],
						o[2][2],
						o[2][3],
						o[3][1],
						o[3][2],
						o[3][3],
					},
					easing = "Linear",
					dir = "In",
				}
				for _, c in node.Children or {} do
					walk(c)
				end
			end
		end
		for _, c in kf.Children do
			walk(c)
		end
		poses.HumanoidRootPart = nil
		table.insert(keyframes, { t = kf.Properties.Time, poses = poses })
	end
	return { name = clip.name, loop = false, keyframes = keyframes }
end

return Dump

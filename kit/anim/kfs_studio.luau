-- kfs_studio.luau — run INSIDE Roblox Studio (execute_luau, Edit mode, logged in): fetch Creator Store models by
-- asset id, find every KeyframeSequence inside, and return them as the kit's dump JSON (the same shape as
-- kit/anim/kfs_dump.luau writes), one entry per sequence. Nothing from the model is parented into the place and no
-- script in it runs: the model is loaded, read, and destroyed.
--
--   local IDS = { 8304861128, 125909948357929 }   -- edit, then execute this whole file as the code
--
-- Save the returned text to _downloads/creator_store/<assetId>.kfs.json (one file per asset) and import a sequence:
--   lune run kit anim import _downloads/creator_store/<assetId>.kfs.json --clip <KeyframeSequence name> --as <Name>
local IDS = { 8304861128 }

local HttpService = game:GetService("HttpService")
local InsertService = game:GetService("InsertService")

local function enumName(v)
	return tostring(v):gsub("^Enum%.%w+%.", "")
end

local function walkPoses(pose, acc)
	for _, child in pose:GetChildren() do
		if child:IsA("Pose") then
			local x, y, z, r00, r01, r02, r10, r11, r12, r20, r21, r22 = child.CFrame:GetComponents()
			acc[child.Name] = {
				cf = { x, y, z, r00, r01, r02, r10, r11, r12, r20, r21, r22 },
				easing = enumName(child.EasingStyle),
				dir = enumName(child.EasingDirection),
				weight = child.Weight,
			}
			walkPoses(child, acc)
		end
	end
end

local function dumpSequence(kfs, assetId)
	local out = { name = kfs.Name, loop = kfs.Loop, priority = enumName(kfs.Priority), keyframes = {}, asset = assetId }
	for _, kf in kfs:GetChildren() do
		if kf:IsA("Keyframe") then
			local poses, markers = {}, {}
			walkPoses(kf, poses)
			for _, m in kf:GetChildren() do
				if m:IsA("KeyframeMarker") then
					table.insert(markers, { name = m.Name, value = m.Value })
				end
			end
			table.insert(out.keyframes, { t = kf.Time, name = kf.Name, poses = poses, markers = markers })
		end
	end
	table.sort(out.keyframes, function(a, b)
		return a.t < b.t
	end)
	return out
end

local report = {}
for _, id in IDS do
	local ok, model = pcall(function()
		return InsertService:LoadAsset(id)
	end)
	if not ok or not model then
		report[tostring(id)] = { error = tostring(model) }
		continue
	end
	local sequences, scripts, animations = {}, {}, {}
	for _, inst in model:GetDescendants() do
		if inst:IsA("KeyframeSequence") then
			table.insert(sequences, dumpSequence(inst, id))
		elseif inst:IsA("LuaSourceContainer") then
			table.insert(scripts, inst:GetFullName())
		elseif inst:IsA("Animation") then
			table.insert(animations, { name = inst.Name, id = inst.AnimationId })
		end
	end
	report[tostring(id)] = { name = model.Name, sequences = sequences, scripts = scripts, animations = animations }
	model:Destroy()
end
return HttpService:JSONEncode(report)

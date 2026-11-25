-- kfs_dump.luau — `lune run kit/anim/kfs_dump.luau <file.rbxm|rbxmx> <out.json> [<KeyframeSequence name>]`
-- A Roblox model file (a community animation pack, a Roblox-owned default animation fetched as reference) ->
-- one KeyframeSequence as JSON: its keyframes (time, name), every Pose (joint-space CFrame components, easing
-- style/direction, weight), the sequence's Loop and Priority, and the names of every KeyframeSequence in the file.
-- The file is DATA: only Keyframes and Poses are read; nothing in it runs. kit/anim/kfs_import.py turns the JSON
-- into the kit's R6 clip.
local fs = require("@lune/fs")
local process = require("@lune/process")
local roblox = require("@lune/roblox")
local serde = require("@lune/serde")

local function emit(status: string, summary: string, nextAction: string, extra: { [string]: any }?)
	local rec: { [string]: any } = { schema = 1, status = status, summary = summary, next_action = nextAction }
	for k, v in extra or {} do
		rec[k] = v
	end
	print(serde.encode("json", rec))
	process.exit(if status == "pass" then 0 else 1)
end

local inPath, outPath, want = process.args[1], process.args[2], process.args[3]
if not inPath or not outPath then
	emit(
		"fail",
		"kfs_dump: needs <file.rbxm> <out.json> [<KeyframeSequence name>]",
		"lune run kit/anim/kfs_dump.luau <file.rbxm> <out.json> Walk"
	)
end
local okRead, raw = pcall(fs.readFile, inPath)
if not okRead then
	emit("fail", `kfs_dump: cannot read {inPath}`, "check the path")
end
local okModel, model = pcall(function()
	if string.match(string.lower(inPath), "%.rbxlx?$") then
		-- a place file: its DataModel's services are the roots
		local dm = roblox.deserializePlace(raw)
		return dm:GetChildren()
	end
	return roblox.deserializeModel(raw)
end)
if not okModel then
	emit(
		"fail",
		`kfs_dump: {inPath} is not a Roblox model file ({tostring(model)})`,
		"a .rbxm / .rbxmx saved from Studio"
	)
end

local all, scripts = {}, {}
local function findAll(list)
	for _, inst in list do
		if inst.ClassName == "KeyframeSequence" then
			table.insert(all, inst)
		elseif inst.ClassName == "Script" or inst.ClassName == "LocalScript" or inst.ClassName == "ModuleScript" then
			table.insert(scripts, inst:GetFullName())
		end
		findAll(inst:GetChildren())
	end
end
findAll(model)
if #all == 0 then
	emit(
		"fail",
		`kfs_dump: no KeyframeSequence in {inPath}`,
		"a file holding KeyframeSequence objects (the Animation Editor's 'Save to Roblox' or a free model)"
	)
end
local names = {}
for _, k in all do
	table.insert(names, k.Name)
end
local kfs = all[1]
if want then
	kfs = nil
	for _, k in all do
		if k.Name == want then
			kfs = k
		end
	end
	if not kfs then
		emit("fail", `kfs_dump: no KeyframeSequence named "{want}" in {inPath}`, `one of: {table.concat(names, ", ")}`)
	end
end

local out = {
	name = kfs.Name,
	loop = kfs.Loop,
	priority = string.gsub(tostring(kfs.Priority), "^Enum%.AnimationPriority%.", ""),
	keyframes = {},
	all = names,
	scripts = scripts,
	file = inPath,
}
local function walkPoses(pose, acc)
	for _, child in pose:GetChildren() do
		if child.ClassName == "Pose" then
			local x, y, z, r00, r01, r02, r10, r11, r12, r20, r21, r22 = child.CFrame:GetComponents()
			acc[child.Name] = {
				cf = { x, y, z, r00, r01, r02, r10, r11, r12, r20, r21, r22 },
				easing = string.gsub(tostring(child.EasingStyle), "^Enum%.PoseEasingStyle%.", ""),
				dir = string.gsub(tostring(child.EasingDirection), "^Enum%.PoseEasingDirection%.", ""),
				weight = child.Weight,
			}
			walkPoses(child, acc)
		end
	end
end
for _, kf in kfs:GetChildren() do
	if kf.ClassName == "Keyframe" then
		local poses = {}
		walkPoses(kf, poses)
		local markers = {}
		for _, m in kf:GetChildren() do
			if m.ClassName == "KeyframeMarker" then
				table.insert(markers, { name = m.Name, value = m.Value })
			end
		end
		table.insert(out.keyframes, { t = kf.Time, name = kf.Name, poses = poses, markers = markers })
	end
end
table.sort(out.keyframes, function(a, b)
	return a.t < b.t
end)
fs.writeFile(outPath, serde.encode("json", out, true))
emit(
	"pass",
	`kfs_dump {kfs.Name}: {#out.keyframes} keyframes, loop={tostring(kfs.Loop)}, priority={out.priority}{if #scripts
			> 0
		then ` — {#scripts} script(s) in the file (not run)`
		else ""}`,
	`python kit/anim/kfs_import.py {outPath}`,
	{ all = names, scripts = scripts }
)

-- uploadjobs.luau (kit) — WHAT `kit upload` sends: every built file of an uploadable kind, minus private studies
-- (Models.unshippedAssets) and held UI art (assets/ui/upload.hold.json). One list for the upload itself and for the
-- moderation audit (kit/lib/moderation.luau), so the two never disagree on what would leave.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Config = require("./config")
local Models = require("./models")

local UploadJobs = {}

export type Job = { file: string, assetType: string, name: string }
type Job = Job

function UploadJobs.list(dir: string, ext: string): { string }
	local out = {}
	if fs.isDir(dir) then
		for _, f in fs.readDir(dir) do
			if string.sub(f, -#ext - 1) == "." .. ext and string.sub(f, 1, 1) ~= "_" then
				table.insert(out, `{dir}/{f}`)
			end
		end
	end
	table.sort(out)
	return out
end

-- KeyframeSequences from the built place -> build/animations/<Name>.rbxm (the Animation upload format)
function UploadJobs.exportAnimations(): ({ string }, string?)
	local place = Config.build("place.rbxlx")
	if not fs.isFile(place) then
		return {}, nil
	end
	local roblox = require("@lune/roblox")
	-- a place another session is still writing (or one lune cannot read) must not stop every other upload
	local ok, game = pcall(roblox.deserializePlace, fs.readFile(place))
	if not ok then
		return {}, `animations skipped: {place} does not load ({game})`
	end
	local folder = game:GetService("ReplicatedStorage"):FindFirstChild("KitAnimations")
	if not folder then
		return {}, nil
	end
	local out = {}
	local dir = Config.build("animations")
	Config.ensureDir(dir)
	for _, seq in folder:GetChildren() do
		if seq.ClassName == "KeyframeSequence" then
			local path = `{dir}/{seq.Name}.rbxm`
			fs.writeFile(path, roblox.serializeModel({ seq }))
			table.insert(out, path)
		end
	end
	return out, nil
end

function UploadJobs.jobs(projectName: string, noExport: boolean?): { Job }
	local B = function(sub: string): string
		return Config.build(sub)
	end
	local out: { Job } = {}
	-- PRIVATE assets (rbx.Asset(private=True): a study of someone else's design) never go up — not their meshes, not
	-- their groups' meshes, not their maps (all named after the asset)
	local manifests = {}
	if fs.isDir(B("models")) then
		for _, f in fs.readDir(B("models")) do
			if string.match(f, "%.manifest%.json$") then
				local ok, m = pcall(serde.decode, "json" :: any, fs.readFile(`{B("models")}/{f}`))
				manifests[f] = if ok then m else nil
			end
		end
	end
	local private = Models.unshippedAssets(manifests)
	local function add(file: string, assetType: string)
		local stem = string.match(file, "([^/]+)%.[%w]+$") or file
		if Models.isPrivateFile(stem, private) then
			return
		end
		local name = string.sub(`{projectName}-{stem}`, 1, 50)
		table.insert(out, { file = file, assetType = assetType, name = name })
	end
	for _, f in UploadJobs.list(B("textures"), "png") do
		add(f, "Image")
	end
	for _, f in UploadJobs.list(B("models") .. "/textures", "png") do
		-- a trim sheet's own bake files stay home: its models use the faded copies beside them (<...>_trim.png),
		-- nothing uses these (card fczy)
		local trimmed = string.sub(f, -4) == ".png" and fs.isFile(string.sub(f, 1, -5) .. "_trim.png")
		if not trimmed then
			add(f, "Image")
		end
	end
	for _, f in UploadJobs.list(B("models"), "fbx") do
		if not string.find(f, "calibration", 1, true) then
			add(f, "Mesh")
		end
	end
	for _, f in UploadJobs.list(B("vfxmeshes"), "fbx") do
		add(f, "Mesh")
	end
	-- a world's real meshes + their texture atlases (kit world meshes): -> ids.worldmeshes / ids.worldtextures
	for _, f in UploadJobs.list(B("worldmeshes"), "fbx") do
		add(f, "Mesh")
	end
	-- a world's terrain MaterialVariant maps (kit world materials): -> ids.terrainmaps
	for _, f in UploadJobs.list(B("terrainmaps"), "png") do
		add(f, "Image")
	end
	for _, f in UploadJobs.list(B("worldmeshes"), "png") do
		if not string.find(f, ".preview.", 1, true) then
			add(f, "Image")
		end
	end
	for _, f in UploadJobs.list(B("ui") .. "/art", "png") do
		add(f, "Image")
	end
	-- every identity's plates + its own art: build/ui/art/<identity>/*.png -> ids.ui["<identity>/<name>"] — except a
	-- HELD piece (assets/ui/upload.hold.json: art derived from a real character's pictures stays off Roblox, whatever runs)
	local held: { [string]: boolean } = {}
	local holdPath = Config.path("ui") .. "/upload.hold.json"
	if fs.isFile(holdPath) then
		local ok, h = pcall(serde.decode, "json" :: any, fs.readFile(holdPath))
		if ok and type(h) == "table" and type(h.hold) == "table" then
			for k in h.hold do
				held[k] = true
			end
		end
	end
	if fs.isDir(B("ui") .. "/art") then
		for _, sub in fs.readDir(B("ui") .. "/art") do
			if fs.isDir(`{B("ui")}/art/{sub}`) then
				for _, f in UploadJobs.list(`{B("ui")}/art/{sub}`, "png") do
					local stem = string.match((string.gsub(f, string.char(92), "/")), "([^/]+)%.png$") or f
					local base = string.gsub(stem, "__glint$", "")
					if not held[`{sub}/{stem}`] and not held[`{sub}/{base}`] then
						add(f, "Image")
					end
				end
			end
		end
	end
	for _, f in UploadJobs.list(B("sounds"), "ogg") do
		add(f, "Audio")
	end
	-- (noExport: the animations as last exported - the moderation audit reads names, it never loads the place)
	local anims = if noExport then UploadJobs.list(B("animations"), "rbxm") else (UploadJobs.exportAnimations())
	for _, f in anims do
		add(f, "Animation")
	end
	return out
end

return UploadJobs

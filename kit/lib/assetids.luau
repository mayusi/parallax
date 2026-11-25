-- assetids.luau — record an uploaded asset's id everywhere the game reads it. Used by `kit asset-id` (manual) and
-- `kit upload` (automatic): assets/ids.json (Assets.id / Assets.play / Anim), the VFX texture registry
-- (flipbooks switch on) and the VFX mesh registry (custom meshes replace their stand-ins).
local fs = require("@lune/fs")
local serde = require("@lune/serde")
local task = require("@lune/task")

local Config = require("./config")

local AssetIds = {}

-- Windows: a scanner can map a just-written file for a moment ("user-mapped section open", os error 1224); the upload
-- already happened, so a lost write strands the asset - retry briefly instead of crashing
local function writeFile(path: string, text: string)
	for attempt = 1, 20 do
		local ok, err = pcall(fs.writeFile, path, text)
		if ok then
			return
		end
		if attempt == 20 or not string.find(tostring(err), "1224", 1, true) then
			error(err, 0)
		end
		task.wait(0.25)
	end
end

-- build/sounds/explosion_big.ogg -> ("sounds", "explosion_big"); build/animations/Slash.rbxm -> ("animations", "Slash");
-- build/ui/art/ring.png -> ("ui", "ring") (screen specs say "image": "art:ring")
function AssetIds.classify(file: string): (string, string)
	local norm = string.gsub(file, "\\", "/")
	-- a world's terrain MaterialVariant maps (kit world materials): <scan>__<color|normal|roughness>.png -> terrainmaps
	if string.find(norm, "/terrainmaps/", 1, true) then
		return "terrainmaps", string.match(norm, "([%w_]+)%.png$") or norm
	end
	-- a world's real meshes (kit world meshes): the FBX -> worldmeshes, its texture atlas -> worldtextures
	if string.find(norm, "/worldmeshes/", 1, true) then
		local stem = string.match(norm, "([%w_]+)%.[%w]+$") or norm
		return if string.match(norm, "%.png$") then "worldtextures" else "worldmeshes", stem
	end
	local kind = (string.find(norm, "/ui/art/", 1, true) and "ui")
		or string.match(norm, "/(sounds)/")
		or string.match(norm, "/(vfxmeshes)/")
		or string.match(norm, "/(models)/")
		or string.match(norm, "/(textures)/")
		or string.match(norm, "^(animations)/")
		or string.match(norm, "/(animations)/")
	local logical = string.match(norm, "([%w_]+)%.[%w]+$") or string.match(norm, "([%w_]+)$") or norm
	if kind == "ui" then
		-- an identity's piece keeps its folder: build/ui/art/souls/frame.png -> "souls/frame" (art:souls/frame)
		local sub = string.match(norm, "/ui/art/([%w_]+)/[%w_]+%.[%w]+$")
		if sub then
			logical = `{sub}/{logical}`
		end
	end
	if kind == "vfxmeshes" then
		kind = "files" -- kept where earlier projects recorded them; the mesh registry is what the game reads
	elseif kind == "models" and string.find(norm, "/models/textures/", 1, true) then
		kind = "textures"
	elseif not kind then
		kind = if string.match(norm, "%.png$") or string.match(norm, "%.jpe?g$") then "images" else "files"
	end
	return kind, logical
end

-- -> one-line description of what was updated
function AssetIds.record(file: string, id: string): string
	if string.match(id, "^%d+$") then
		id = "rbxassetid://" .. id
	end
	local idsPath = Config.path("ids")
	local ids = if fs.isFile(idsPath) then serde.decode("json", fs.readFile(idsPath)) else {}
	local kind, logical = AssetIds.classify(file)
	ids[kind] = ids[kind] or {}
	ids[kind][logical] = id
	Config.ensureDir((string.match(idsPath, "^(.*)/[^/]*$") or "."))
	writeFile(idsPath, serde.encode("json", ids, true) .. "\n")
	local norm = string.gsub(file, "\\", "/")
	local extra = ""
	local key = string.match(norm, "/textures/([%w_]+)%.png$")
	local registryPath = Config.path("vfx") .. "/_textures.json"
	if key and fs.isFile(registryPath) then
		local reg = serde.decode("json", fs.readFile(registryPath))
		if type(reg[key]) == "table" then
			reg[key].id = id
			writeFile(registryPath, serde.encode("json", reg, true) .. "\n")
			extra = ` + VFX texture "{key}" (flipbook on)`
		end
	end
	local meshKey = string.match(norm, "/vfxmeshes/([%w_]+)%.fbx$")
	local meshReg = Config.path("vfx") .. "/_meshes.json"
	if meshKey and fs.isFile(meshReg) then
		local reg = serde.decode("json", fs.readFile(meshReg))
		if type(reg[meshKey]) == "table" then
			reg[meshKey].id = id
			writeFile(meshReg, serde.encode("json", reg, true) .. "\n")
			extra = ` + VFX mesh "{meshKey}" (replaces its {reg[meshKey].fallback} stand-in)`
		end
	end
	return `{kind}.{logical} = {id}{extra}`
end

return AssetIds

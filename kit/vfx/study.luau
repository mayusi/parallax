-- study.luau — learn how a REAL Roblox VFX is built, offline: `lune run kit/vfx/study.luau <file.rbxm|rbxmx|rbxl|rbxlx>`
-- Reads the file as DATA (scripts are never run; their count is reported for `kit audit`), walks every instance and
-- writes one JSON report: every ParticleEmitter / Beam / Trail / mesh (MeshPart, SpecialMesh) / Decal / Texture / light
-- with the properties that make the look (sizes, lifetimes, rates, LightEmission, LightInfluence, ZOffset, flipbooks,
-- textures, mesh ids, colours, transparency curves), plus STATISTICS across them (how many of each, typical lifetimes,
-- additive share, flipbook use, mesh use) — the numbers a pro Roblox VFX artist actually uses.
-- Prints one JSON line {status, summary, next_action, file, stats, items}. Why (owner 2026-10-14): "expand on to tools
-- that are free"; my own effects looked low quality — learn the craft from the community's open-source effects.
local fs = require("@lune/fs")
local process = require("@lune/process")
local roblox = require("@lune/roblox")
local serde = require("@lune/serde")

local path = process.args[1]
local function finish(rec)
	rec.schema = 1
	rec.file = path
	print(serde.encode("json", rec))
	process.exit(if rec.status == "fail" then 1 else 0)
end
if not path then
	finish({
		status = "fail",
		summary = "study: needs a .rbxm / .rbxl file",
		next_action = "lune run kit/vfx/study.luau <file>",
	})
end
local okR, raw = pcall(fs.readFile, path)
if not okR then
	finish({ status = "fail", summary = "study: cannot read " .. tostring(path), next_action = "check the path" })
end
local okM, roots = pcall(function()
	if string.match(string.lower(path), "%.rbxlx?$") then
		return roblox.deserializePlace(raw):GetChildren()
	end
	return roblox.deserializeModel(raw)
end)
if not okM then
	finish({
		status = "fail",
		summary = "study: not a readable Roblox file: " .. string.sub(tostring(roots), 1, 120),
		next_action = "vet the file",
	})
end

local function get(inst: any, prop: string): any
	local ok, v = pcall(function()
		return inst[prop]
	end)
	return if ok then v else nil
end
local function num(v: any): any
	if type(v) == "number" then
		return math.floor(v * 1000 + 0.5) / 1000
	end
	return nil
end
local function nseq(v: any): any -- NumberSequence / NumberRange -> plain tables
	if typeof(v) == "NumberSequence" then
		local out = {}
		for _, k in v.Keypoints do
			table.insert(out, { num(k.Time), num(k.Value) })
		end
		return out
	elseif typeof(v) == "NumberRange" then
		return { num(v.Min), num(v.Max) }
	end
	return num(v)
end
local function cseq(v: any): any
	if typeof(v) == "ColorSequence" then
		local out = {}
		for _, k in v.Keypoints do
			table.insert(out, {
				num(k.Time),
				{ math.floor(k.Value.R * 255), math.floor(k.Value.G * 255), math.floor(k.Value.B * 255) },
			})
		end
		return out
	elseif typeof(v) == "Color3" then
		return { math.floor(v.R * 255), math.floor(v.G * 255), math.floor(v.B * 255) }
	end
	return nil
end
local function content(v: any): any
	if v == nil then
		return nil
	end
	local s = tostring(v)
	return if s == "" then nil else s
end
local function enum(v: any): any
	return if v ~= nil then tostring(v) else nil
end

local items, counts, scripts = {}, {}, 0
local lifetimes, additive, emitters, flipbooks, sizes = {}, 0, 0, 0, {}
local textures = {}
local function visit(inst: any, depth: number, trail: string)
	local cls = inst.ClassName
	local here = trail .. "/" .. inst.Name
	if cls == "Script" or cls == "LocalScript" or cls == "ModuleScript" then
		scripts += 1
	end
	local rec: any = nil
	if cls == "ParticleEmitter" then
		emitters += 1
		local le = get(inst, "LightEmission") or 0
		if le >= 0.5 then
			additive += 1
		end
		local life = get(inst, "Lifetime")
		if typeof(life) == "NumberRange" then
			table.insert(lifetimes, (life.Min + life.Max) / 2)
		end
		local layout = enum(get(inst, "FlipbookLayout"))
		if layout and not string.find(layout, "None") then
			flipbooks += 1
		end
		local size = get(inst, "Size")
		if typeof(size) == "NumberSequence" then
			local mx = 0
			for _, k in size.Keypoints do
				mx = math.max(mx, k.Value)
			end
			table.insert(sizes, mx)
		end
		rec = {
			texture = content(get(inst, "Texture")),
			rate = num(get(inst, "Rate")),
			lifetime = nseq(life),
			speed = nseq(get(inst, "Speed")),
			size = nseq(size),
			transparency = nseq(get(inst, "Transparency")),
			color = cseq(get(inst, "Color")),
			lightEmission = num(le),
			lightInfluence = num(get(inst, "LightInfluence")),
			brightness = num(get(inst, "Brightness")),
			zOffset = num(get(inst, "ZOffset")),
			orientation = enum(get(inst, "Orientation")),
			rotation = nseq(get(inst, "Rotation")),
			rotSpeed = nseq(get(inst, "RotSpeed")),
			spreadAngle = tostring(get(inst, "SpreadAngle")),
			acceleration = tostring(get(inst, "Acceleration")),
			drag = num(get(inst, "Drag")),
			shape = enum(get(inst, "Shape")),
			flipbook = layout,
			flipbookFps = num(get(inst, "FlipbookFramerate") and get(inst, "FlipbookFramerate").Max),
			flipbookMode = enum(get(inst, "FlipbookMode")),
			squash = nseq(get(inst, "Squash")),
			lockedToPart = get(inst, "LockedToPart"),
			enabled = get(inst, "Enabled"),
		}
	elseif cls == "Beam" or cls == "Trail" then
		rec = {
			texture = content(get(inst, "Texture")),
			width0 = num(get(inst, "Width0")),
			width1 = num(get(inst, "Width1")),
			curve0 = num(get(inst, "CurveSize0")),
			curve1 = num(get(inst, "CurveSize1")),
			segments = num(get(inst, "Segments")),
			textureSpeed = num(get(inst, "TextureSpeed")),
			textureLength = num(get(inst, "TextureLength")),
			textureMode = enum(get(inst, "TextureMode")),
			lightEmission = num(get(inst, "LightEmission")),
			lightInfluence = num(get(inst, "LightInfluence")),
			brightness = num(get(inst, "Brightness")),
			transparency = nseq(get(inst, "Transparency")),
			color = cseq(get(inst, "Color")),
			faceCamera = get(inst, "FaceCamera"),
			lifetime = num(get(inst, "Lifetime")),
			zOffset = num(get(inst, "ZOffset")),
		}
	elseif cls == "MeshPart" or cls == "SpecialMesh" then
		rec = {
			mesh = content(get(inst, "MeshId")) or content(get(inst, "MeshContent")),
			texture = content(get(inst, "TextureID")) or content(get(inst, "TextureId")),
			meshType = enum(get(inst, "MeshType")),
			scale = tostring(get(inst, "Scale") or get(inst, "Size")),
			material = enum(get(inst, "Material")),
			color = cseq(get(inst, "Color")),
			transparency = num(get(inst, "Transparency")),
			vertexColor = tostring(get(inst, "VertexColor")),
		}
	elseif cls == "Decal" or cls == "Texture" then
		rec = {
			texture = content(get(inst, "Texture")),
			face = enum(get(inst, "Face")),
			transparency = num(get(inst, "Transparency")),
		}
	elseif cls == "PointLight" or cls == "SpotLight" or cls == "SurfaceLight" then
		rec = {
			color = cseq(get(inst, "Color")),
			brightness = num(get(inst, "Brightness")),
			range = num(get(inst, "Range")),
		}
	elseif cls == "Part" then
		local mat = enum(get(inst, "Material"))
		if mat and (string.find(mat, "Neon") or string.find(mat, "ForceField")) then
			rec = {
				material = mat,
				shape = enum(get(inst, "Shape")),
				size = tostring(get(inst, "Size")),
				transparency = num(get(inst, "Transparency")),
				color = cseq(get(inst, "Color")),
			}
		end
	end
	if rec then
		rec.class = cls
		rec.path = here
		counts[cls] = (counts[cls] or 0) + 1
		table.insert(items, rec)
		if rec.texture then
			textures[rec.texture] = (textures[rec.texture] or 0) + 1
		end
	end
	for _, c in inst:GetChildren() do
		visit(c, depth + 1, here)
	end
end
for _, r in roots do
	visit(r, 0, "")
end

local function median(t: { number }): any
	if #t == 0 then
		return nil
	end
	table.sort(t)
	return num(t[math.floor((#t + 1) / 2)])
end
local nTex = 0
for _ in textures do
	nTex += 1
end
local stats = {
	counts = counts,
	scripts = scripts,
	emitters = emitters,
	additive_share = if emitters > 0 then num(additive / emitters) else nil,
	flipbook_share = if emitters > 0 then num(flipbooks / emitters) else nil,
	median_lifetime = median(lifetimes),
	median_max_size = median(sizes),
	distinct_textures = nTex,
}
local parts = {}
for k, v in counts do
	table.insert(parts, `{v} {k}`)
end
table.sort(parts)
finish({
	status = if #items > 0 then "pass" else "warn",
	summary = `study {path}: {#items} VFX pieces ({table.concat(parts, ", ")}); {scripts} script(s) (read as data, never run; kit audit before any reuse); emitters: {math.floor(
		(stats.additive_share or 0) * 100
	)}% additive, {math.floor((stats.flipbook_share or 0) * 100)}% flipbooks, median lifetime {stats.median_lifetime}s, median max size {stats.median_max_size}`,
	next_action = "read stats + items (the pro's numbers); reuse only with the file's licence (VETLOG)",
	stats = stats,
	items = items,
})

-- Vfx (ReplicatedStorage.kit.Vfx) — plays the data presets in ReplicatedStorage.VfxPresets (= assets/effects/*.json).
--   Vfx.broadcast(name, where, scale?, target?, opts?)   SERVER: the clients play it locally (smooth, no server tweens).
--       WHO is sent it: players within a reach of the effect or of its target - opts.reach, else the preset's "reach",
--       else Vfx.setReach's, else a rule from the effect's own size; one who comes into reach while it lasts is sent it
--       then. Every event carries the server's clock: a client that gets it late starts the effect that far in, or not
--       at all once it is over (VfxNet: the rules)
--   Vfx.play(name, where, scale?, parent?, target?, late?) play once here (client cosmetics, or server if you must);
--       late = REAL seconds it should already have been playing: a version 3 effect starts where its clock would be
-- Elements: particles flash ring light debris trail + sound (kit Assets) shake screen beam (client feel).
-- Any element can have "delay" (seconds) to stage wind-up -> impact -> aftermath in one preset.
-- particles/light/mesh take "offset" [x, y, z] (emit up in the sky, beside the target); particles take "area"
-- { "shape": "Box"|"Sphere"|"Cylinder", "size": [x, y, z] } to emit through a volume (cloud banks, dust fields).
--   Vfx.attach(name, part, offset?, scale?) -> stop()   continuous effect riding a part (exhaust, aura)
-- `where` is a Vector3 or CFrame. Presets are validated on load; invalid ones warn and refuse to play.
local Debris = game:GetService("Debris")
local Lighting = game:GetService("Lighting")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")
local Workspace = game:GetService("Workspace")

local AssetService = game:GetService("AssetService")
local Players = game:GetService("Players")

local VfxBudget = require("./VfxBudget")
local VfxCompose = require("./VfxCompose")
local VfxMesh = require("./VfxMesh")
local VfxNet = require("./VfxNet")
local VfxStage = require("./VfxStage")
local VfxValidate = require("./VfxValidate")
local presetFolder = ReplicatedStorage:WaitForChild("VfxPresets")
-- registries are found at runtime: (require :: any) tells the type checker not to resolve them statically
local textures: any = (require :: any)(presetFolder:WaitForChild("_textures"))
-- effect-mesh registry (assets/effects/_meshes.json, written by `kit vfx`): { name = { id, fallback, size } }
local meshesModule = presetFolder:FindFirstChild("_meshes")
local meshes: any = if meshesModule then (require :: any)(meshesModule) else {}

local REMOTE_NAME = "VfxPlay"
local rng = Random.new()

local Vfx = {}

local presets: { [string]: any } = {}
-- reusable sub-effects: assets/effects/parts/<name>.json -> VfxPresets.parts.<name>
local partsFolder = presetFolder:FindFirstChild("parts")
local function loadPart(partName: string): any?
	local m = partsFolder and partsFolder:FindFirstChild(partName)
	return if m and m:IsA("ModuleScript") then (require :: any)(m) else nil
end
-- baked impact frames: assets/effects/frames/<preset>.json -> VfxPresets.frames.<preset> = { [layer] = texture }
local framesFolder = presetFolder:FindFirstChild("frames")
local function loadFrames(presetName: string): any?
	local m = framesFolder and framesFolder:FindFirstChild(presetName)
	if not (m and m:IsA("ModuleScript")) then
		return nil
	end
	-- only frames whose plate is registered (kit vfx ran after the bake); the rest keep the engine's own frame
	local map, out = (require :: any)(m), {}
	for layer, key in map do
		if type(key) == "string" and textures[key] ~= nil then
			out[layer] = key
		end
	end
	return out
end
local function register(name: string, preset: any, variant: string?)
	local issues = {}
	if type(preset) == "table" and preset.version == 3 then -- beats / use / variants expand first
		local base = string.split(name, "@")[1]
		preset, issues = VfxCompose.expand(preset, { variant = variant, parts = loadPart, frames = loadFrames(base) })
	end
	for _, issue in VfxValidate.preset(name, preset, textures, meshes) do
		table.insert(issues, issue)
	end
	local errors = VfxValidate.errors(issues)
	if #errors > 0 then
		warn(`[Vfx] preset "{name}" rejected: {errors[1].path}: {errors[1].message}`)
	else
		presets[name] = preset
	end
end
local function load(module: Instance)
	if not module:IsA("ModuleScript") or string.sub(module.Name, 1, 1) == "_" then
		return
	end
	local preset = require(module) :: any
	register(module.Name, preset, nil)
	for _, variant in VfxCompose.variants(preset) do -- Vfx.play("starblade@ice", ...)
		register(`{module.Name}@{variant}`, preset, variant)
	end
end
for _, module in presetFolder:GetChildren() do
	load(module)
end
-- a preset that REPLICATES AFTER this module was required is taken too (the owner's limitations file, F-R02: the list
-- was read once, so a preset that came a moment late could never play - Vfx.has stayed false for the session)
presetFolder.ChildAdded:Connect(function(module)
	local ok, why = (pcall :: any)(load, module)
	if not ok then
		warn(`[Vfx] preset "{module.Name}" could not be loaded: {why}`)
	end
end)
-- version-3 effects load their textures up front: a texture's first use arrives a few frames late
if RunService:IsClient() then
	task.spawn(function()
		for _, p in presets do
			if p.version == 3 then
				VfxStage.preload(p, textures)
			end
		end
	end)
end

-- ---------------------------------------------------------------- converters (JSON shapes -> Roblox types)
local function rgb(c: any): Color3
	return Color3.fromRGB(c[1], c[2], c[3])
end

local function range(v: any, scale: number): NumberRange
	if type(v) == "number" then
		return NumberRange.new(v * scale)
	end
	return NumberRange.new(v[1] * scale, v[2] * scale)
end

local function numberSeq(v: any, scale: number): NumberSequence
	if type(v) == "number" then
		return NumberSequence.new(v * scale)
	end
	local kps = {}
	for _, kp in v do
		table.insert(kps, NumberSequenceKeypoint.new(kp[1], kp[2] * scale, (kp[3] or 0) * scale))
	end
	return NumberSequence.new(kps)
end

local function colorSeq(v: any): ColorSequence
	if type(v[1]) == "number" then
		return ColorSequence.new(rgb(v))
	end
	local kps = {}
	for _, kp in v do
		table.insert(kps, ColorSequenceKeypoint.new(kp[1], rgb(kp[2])))
	end
	return ColorSequence.new(kps)
end

local function vec(v: any, scale: number): Vector3
	return Vector3.new(v[1] * scale, v[2] * scale, v[3] * scale)
end

local function texture(key: string): (string, number)
	local entry = textures[key]
	if entry.id ~= nil and entry.id ~= "" then
		return entry.id, entry.grid or 1
	end
	return entry.fallback, 1 -- built-in fallback has no frames: flipbook is switched off
end

local function tween(inst: Instance, time: number, goal: { [string]: any })
	TweenService:Create(inst, TweenInfo.new(time, Enum.EasingStyle.Quad, Enum.EasingDirection.Out), goal):Play()
end

-- ---------------------------------------------------------------- element builders
local function emitter(el: any, scale: number): ParticleEmitter
	local pe = Instance.new("ParticleEmitter")
	local id, grid = texture(el.texture)
	pe.Texture = id
	pe.Lifetime = range(el.lifetime, 1)
	pe.Speed = range(el.speed or 0, scale)
	pe.SpreadAngle = Vector2.new(el.spread or 0, el.spread or 0)
	pe.Size = numberSeq(el.size or 1, scale)
	pe.Transparency = numberSeq(el.transparency or 0, 1)
	pe.Color = colorSeq(el.color or { 255, 255, 255 })
	pe.LightEmission = el.lightEmission or 0
	pe.LightInfluence = el.lightInfluence or 0
	pe.Drag = el.drag or 0
	pe.Acceleration = vec(el.acceleration or { 0, 0, 0 }, scale)
	pe.Rotation = range(el.rotation or 0, 1)
	pe.RotSpeed = range(el.rotSpeed or 0, 1)
	pe.Rate = el.rate or 0
	pe.EmissionDirection = (Enum.NormalId :: any)[el.direction or "Top"]
	pe.Orientation = (Enum.ParticleOrientation :: any)[el.orientation or "FacingCamera"]
	if el.flipbook and grid > 1 then
		pe.FlipbookLayout = (Enum.ParticleFlipbookLayout :: any)[el.flipbook.layout]
		pe.FlipbookMode = (Enum.ParticleFlipbookMode :: any)[el.flipbook.mode or "Loop"]
		pe.FlipbookFramerate = NumberRange.new(el.flipbook.fps)
	end
	return pe
end

local function effectPart(name: string, cframe: CFrame, parent: Instance): Part
	local part = Instance.new("Part")
	part.Name = name
	part.Anchored = true
	part.CanCollide = false
	part.CanQuery = false
	part.CanTouch = false
	part.CastShadow = false
	part.CFrame = cframe
	part.Parent = parent
	return part
end

local function playElement(el: any, holder: BasePart, attachment: Attachment, scale: number, duration: number)
	local kind = el.kind
	if kind == "particles" then
		local pe = emitter(el, scale)
		pe.Enabled = false
		-- "offset": emit somewhere else than the origin (a cloud bank 600 studs up); "area": emit throughout a
		-- volume ({ "shape": "Box"|"Sphere"|"Cylinder", "size": [x, y, z] }) instead of from one point
		local off = el.offset or { 0, 0, 0 }
		local at = holder.CFrame * CFrame.new(off[1] * scale, off[2] * scale, off[3] * scale)
		if el.area then
			local volume = effectPart("Emitter", at, holder)
			volume.Transparency = 1
			local sz = el.area.size or { 10, 10, 10 }
			volume.Size = Vector3.new(sz[1], sz[2], sz[3]) * scale
			pe.Shape = (Enum.ParticleEmitterShape :: any)[el.area.shape or "Box"]
			pe.ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume
			pe.Parent = volume
		elseif el.offset then
			local att = Instance.new("Attachment")
			att.Parent = holder
			att.WorldCFrame = at
			pe.Parent = att
		else
			pe.Parent = attachment
		end
		if (el.burst or 0) > 0 then
			pe:Emit(el.burst)
		end
		if (el.rate or 0) > 0 then
			pe.Enabled = true
			task.delay(el.emit or 0.2, function()
				pe.Enabled = false
			end)
		end
	elseif kind == "flash" then
		local part = effectPart("Flash", holder.CFrame, holder)
		part.Shape = (Enum.PartType :: any)[el.shape or "Ball"]
		part.Material = Enum.Material.Neon
		part.Color = rgb(el.color or { 255, 255, 255 })
		local tr = el.transparency or { 0, 1 }
		part.Transparency = tr[1]
		part.Size = Vector3.one * el.size[1] * scale
		tween(part, el.time or 0.3, { Size = Vector3.one * el.size[2] * scale, Transparency = tr[2] })
	elseif kind == "ring" then
		local part = effectPart("Ring", holder.CFrame * CFrame.Angles(0, 0, math.rad(90)), holder)
		part.Shape = Enum.PartType.Cylinder
		part.Material = Enum.Material.Neon
		part.Color = rgb(el.color or { 255, 255, 255 })
		local tr = el.transparency or { 0, 1 }
		part.Transparency = tr[1]
		local t = el.thickness * scale
		part.Size = Vector3.new(t, el.size[1] * scale, el.size[1] * scale)
		tween(
			part,
			el.time or 0.5,
			{ Size = Vector3.new(t, el.size[2] * scale, el.size[2] * scale), Transparency = tr[2] }
		)
	elseif kind == "light" then
		local light = Instance.new("PointLight")
		light.Color = rgb(el.color or { 255, 255, 255 })
		light.Range = math.min(el.range * scale, 60)
		light.Brightness = el.brightness[1]
		light.Shadows = false
		if el.offset then
			local att = Instance.new("Attachment")
			att.Parent = holder
			att.WorldPosition = (holder.CFrame * CFrame.new(
				el.offset[1] * scale,
				el.offset[2] * scale,
				el.offset[3] * scale
			)).Position
			light.Parent = att
		else
			light.Parent = holder
		end
		tween(light, el.time or duration, { Brightness = el.brightness[2] })
	elseif kind == "debris" then
		for _ = 1, el.count do
			local s = el.size
			-- parented beside the holder (not inside it) so each chunk lives its own lifetime, not the preset duration
			local chunk = effectPart("Debris", holder.CFrame + Vector3.new(0, 1, 0), holder.Parent or Workspace)
			chunk.Anchored = false
			chunk.Transparency = 0
			chunk.Size = Vector3.new(rng:NextNumber(s[1], s[2]), rng:NextNumber(s[1], s[2]), rng:NextNumber(s[1], s[2]))
				* scale
			chunk.Color = rgb(el.color or { 60, 50, 45 })
			chunk.Material = (Enum.Material :: any)[el.material or "Slate"]
			-- random direction inside an upward cone of `spread` degrees
			local spread = math.rad(el.spread or 45)
			local yaw = rng:NextNumber(0, 2 * math.pi)
			local tilt = rng:NextNumber(0, spread)
			local dir = Vector3.new(math.sin(tilt) * math.cos(yaw), math.cos(tilt), math.sin(tilt) * math.sin(yaw))
			chunk.AssemblyLinearVelocity = dir * rng:NextNumber(el.speed[1], el.speed[2]) * scale
			chunk.AssemblyAngularVelocity =
				Vector3.new(rng:NextNumber(-8, 8), rng:NextNumber(-8, 8), rng:NextNumber(-8, 8))
			Debris:AddItem(chunk, el.lifetime or duration)
		end
	end
end

-- ---------------------------------------------------------------- client feel: shake, screen, beams
-- Camera shake: one shared "trauma" value (0..1) that decays; offset = trauma² × smooth noise. Bound after the
-- camera updates so it composes with any camera script instead of fighting it.
local trauma = 0
local shakeBound = false
local function addShake(amount: number)
	trauma = math.min(1, trauma + amount)
	if shakeBound or not RunService:IsClient() then
		return
	end
	shakeBound = true
	local t0 = os.clock()
	RunService:BindToRenderStep("KitVfxShake", Enum.RenderPriority.Camera.Value + 1, function(dt: number)
		local camera = Workspace.CurrentCamera
		if trauma <= 0.001 or not camera then
			trauma = 0
			shakeBound = false
			RunService:UnbindFromRenderStep("KitVfxShake")
			return
		end
		local t = (os.clock() - t0) * 18
		local s = trauma * trauma
		local pitch = math.noise(t, 0.1) * 0.06 * s
		local yaw = math.noise(t, 7.3) * 0.06 * s
		local roll = math.noise(t, 13.9) * 0.08 * s
		camera.CFrame = camera.CFrame * CFrame.Angles(pitch, yaw, roll)
		trauma = math.max(0, trauma - dt * 1.6)
	end)
end

-- 1 at the effect, 0 at `radius` studs (or beyond) from the local camera; 1 on the server (not used there)
local function falloff(position: Vector3, radius: number?): number
	local camera = Workspace.CurrentCamera
	if not camera or not RunService:IsClient() then
		return 1
	end
	local d = (camera.CFrame.Position - position).Magnitude
	return math.clamp(1 - d / (radius or 120), 0, 1)
end

local function screenFlash(el: any, position: Vector3)
	local k = falloff(position, el.radius)
	if k <= 0 then
		return
	end
	-- overlapping flashes add up in Roblox; cap the combined boost so a big fight can't white out the screen
	local active = 0
	for _, other in Lighting:GetChildren() do
		if other.Name == "KitVfxScreen" and other:IsA("ColorCorrectionEffect") then
			active += other.Brightness
		end
	end
	local cc = Instance.new("ColorCorrectionEffect")
	cc.Name = "KitVfxScreen"
	cc.TintColor = rgb(el.color or { 255, 255, 255 })
	cc.Brightness = math.max(0, math.min((el.flash or 0.4) * k, 1 - active))
	cc.Contrast = (el.contrast or 0) * k
	cc.Saturation = (el.saturation or 0) * k
	cc.Parent = Lighting
	local time = el.time or 0.3
	TweenService:Create(cc, TweenInfo.new(time, Enum.EasingStyle.Quad, Enum.EasingDirection.Out), {
		Brightness = 0,
		Contrast = 0,
		Saturation = 0,
		TintColor = Color3.new(1, 1, 1),
	}):Play()
	Debris:AddItem(cc, time + 0.1)
end

-- A beam from A to B. lightning = jagged segments that re-roll every 50 ms (flicker), then fade out.
local function beam(el: any, origin: CFrame, target: Vector3?, scale: number, duration: number)
	local fromOffset = el.from or { 0, 0, 0 }
	local a = (origin * CFrame.new(fromOffset[1] * scale, fromOffset[2] * scale, fromOffset[3] * scale)).Position
	local b: Vector3
	if el.to == "target" then
		if not target then
			warn("[Vfx] beam wants a target — pass one to Vfx.play/broadcast")
			return
		end
		b = target
	else
		b = (origin * CFrame.new(el.to[1] * scale, el.to[2] * scale, el.to[3] * scale)).Position
	end
	local segments = if el.lightning then (el.segments or 8) else 1
	local width = el.width or { 1, 1 }
	local id = if el.texture then (texture(el.texture)) else ""
	local container = Instance.new("Folder")
	container.Name = "KitVfxBeam"
	container.Parent = Workspace.Terrain
	local atts: { Attachment } = {}
	for i = 0, segments do
		local att = Instance.new("Attachment")
		att.WorldPosition = a:Lerp(b, i / segments)
		att.Parent = Workspace.Terrain
		table.insert(atts, att)
	end
	local beams: { Beam } = {}
	for i = 1, segments do
		local bm = Instance.new("Beam")
		bm.Attachment0 = atts[i]
		bm.Attachment1 = atts[i + 1]
		bm.Width0 = width[1] * scale
		bm.Width1 = width[2] * scale
		bm.FaceCamera = true
		bm.LightEmission = el.lightEmission or 1
		bm.LightInfluence = 0
		bm.Color = colorSeq(el.color or { 255, 255, 255 })
		bm.Transparency = numberSeq(el.transparency or 0, 1)
		bm.Texture = id
		bm.TextureMode = Enum.TextureMode.Stretch
		bm.Segments = 1
		bm.Parent = container
		table.insert(beams, bm)
	end
	local life = el.time or math.min(0.4, duration)
	local length = (b - a).Magnitude
	local axis = if length > 0 then (b - a).Unit else Vector3.yAxis
	local side = axis:Cross(if math.abs(axis.Y) < 0.9 then Vector3.yAxis else Vector3.xAxis).Unit
	local up = axis:Cross(side).Unit
	task.spawn(function()
		local start = os.clock()
		while os.clock() - start < life do
			local fade = (os.clock() - start) / life
			if el.lightning then
				local amp = length * 0.06 * (el.jitter or 1)
				for i = 2, segments do
					atts[i].WorldPosition = a:Lerp(b, (i - 1) / segments)
						+ side * rng:NextNumber(-amp, amp)
						+ up * rng:NextNumber(-amp, amp)
				end
			end
			for _, bm in beams do
				bm.Transparency = NumberSequence.new(math.clamp(fade, 0, 1))
			end
			task.wait(0.05)
		end
		container:Destroy()
		for _, att in atts do
			att:Destroy()
		end
	end)
end

local AssetsModule: any = nil
local function playSound(el: any, position: Vector3)
	if not AssetsModule then
		local ok, mod = pcall(require, script.Parent:FindFirstChild("Assets") :: ModuleScript)
		AssetsModule = if ok then mod else false
	end
	if not AssetsModule then
		return
	end
	local pitch = el.pitch or 1
	local speed = if type(pitch) == "table" then rng:NextNumber(pitch[1], pitch[2]) else pitch
	AssetsModule.play(el.name, position, {
		Volume = el.volume or 1,
		PlaybackSpeed = speed,
		RollOffMaxDistance = el.radius or 400,
	})
end

-- ---------------------------------------------------------------- v2: meshes, afterimages, grades
-- value of a number sequence ([[t, v], ...] or a constant) at u in 0..1
local function numAt(v: any, u: number, default: number): number
	if v == nil then
		return default
	end
	if type(v) == "number" then
		return v
	end
	for i = 1, #v - 1 do
		local a, b = v[i], v[i + 1]
		if u <= b[1] then
			local k = if b[1] > a[1] then (u - a[1]) / (b[1] - a[1]) else 0
			return a[2] + (b[2] - a[2]) * math.clamp(k, 0, 1)
		end
	end
	return v[#v][2]
end

local function colorAt(v: any, u: number): Color3
	if v == nil then
		return Color3.new(1, 1, 1)
	end
	if type(v[1]) == "number" then
		return rgb(v)
	end
	for i = 1, #v - 1 do
		local a, b = v[i], v[i + 1]
		if u <= b[1] then
			local k = if b[1] > a[1] then (u - a[1]) / (b[1] - a[1]) else 0
			return rgb(a[2]):Lerp(rgb(b[2]), math.clamp(k, 0, 1))
		end
	end
	return rgb(v[#v][2])
end

local function scaleAt(v: any, u: number): Vector3
	local function toVec(x: any): Vector3
		return if type(x) == "number" then Vector3.one * x else Vector3.new(x[1], x[2], x[3])
	end
	if type(v) == "number" or (type(v) == "table" and type(v[1]) == "number") then
		return toVec(v)
	end
	for i = 1, #v - 1 do
		local a, b = v[i], v[i + 1]
		if u <= b[1] then
			local k = if b[1] > a[1] then (u - a[1]) / (b[1] - a[1]) else 0
			return toVec(a[2]):Lerp(toVec(b[2]), math.clamp(k, 0, 1))
		end
	end
	return toVec(v[#v][2])
end

local PRIMITIVE_SHAPES = { Ball = true, Block = true, Cylinder = true }
-- loaded MeshPart templates by key; false = the load failed (never retried: a bad id must not yield every play)
local meshTemplates: { [string]: BasePart | false } = {}

-- a fresh part for a mesh element + its native size (studs at scale 1). MAY YIELD (CreateMeshPartAsync).
local function meshPart(key: string): (BasePart, Vector3)
	local entry = meshes[key]
	local shape = if entry then entry.fallback or "Ball" else key
	local native = if entry and entry.size
		then Vector3.new(entry.size[1], entry.size[2], entry.size[3])
		else Vector3.one
	if entry and type(entry.id) == "string" and entry.id ~= "" then
		if meshTemplates[key] == nil then
			local ok, made = pcall(function()
				return AssetService:CreateMeshPartAsync(entry.id)
			end)
			if not ok or not made then
				warn(`[Vfx] mesh "{key}" ({entry.id}) failed to load, using a {shape} from now on: {made}`)
			end
			meshTemplates[key] = if ok and made then made else false
		end
		local template = meshTemplates[key]
		if template then
			return (template :: BasePart):Clone(), native
		end
	end
	local part: BasePart
	if shape == "Wedge" then
		part = Instance.new("WedgePart")
	else
		local p = Instance.new("Part")
		p.Shape = (Enum.PartType :: any)[if PRIMITIVE_SHAPES[shape] then shape else "Ball"]
		part = p
	end
	return part, native
end

-- one animated mesh: scale / colour / transparency over `time`, spinning. loop = repeat until stop() (attach).
-- anchor: when it leaves the game (the attached part was destroyed) the mesh ends too.
-- Returns stop() immediately; loading the mesh happens on its own thread so it never delays other elements.
local function playMesh(el: any, origin: () -> CFrame, scale: number, loop: boolean, anchor: Instance?): () -> ()
	local alive = true
	task.spawn(function()
		local part, native = meshPart(el.mesh)
		if not alive then
			part:Destroy()
			return
		end
		part.Name = "VfxMesh"
		part.Anchored = true
		part.CanCollide = false
		part.CanQuery = false
		part.CanTouch = false
		part.CastShadow = false
		part.Material = (Enum.Material :: any)[el.material or "Neon"]
		if el.texture and part:IsA("MeshPart") then
			part.TextureID = (texture(el.texture))
		end
		local off = el.offset or { 0, 0, 0 }
		local rot = el.rotation or { 0, 0, 0 }
		local spin = el.spin or { 0, 0, 0 }
		local base = CFrame.new(off[1] * scale, off[2] * scale, off[3] * scale)
			* CFrame.Angles(math.rad(rot[1]), math.rad(rot[2]), math.rad(rot[3]))
		-- Everything (size, spin) is computed in the kit's Y-up mesh frame. A Roblox cylinder runs along X, so the
		-- stand-in gets its size axes swapped and one extra quarter turn applied LAST, after the spin.
		local upright = part:IsA("Part") and (part :: Part).Shape == Enum.PartType.Cylinder
		local uprightCF = if upright then CFrame.Angles(0, 0, math.rad(90)) else CFrame.identity
		local life = el.time or 1
		local start = os.clock()
		local function step(): boolean
			local age = os.clock() - start
			if age >= life then
				if not loop then
					return false
				end
				age %= life
			end
			local u = age / life
			local size = native * scaleAt(el.scale, u) * scale
			part.Size = if upright then Vector3.new(size.Y, size.X, size.Z) else size
			part.Transparency = numAt(el.transparency, u, 0)
			part.Color = colorAt(el.color, u)
			part.CFrame = origin()
				* base
				* CFrame.Angles(math.rad(spin[1] * age), math.rad(spin[2] * age), math.rad(spin[3] * age))
				* uprightCF
			return true
		end
		if not step() then
			part:Destroy()
			return
		end
		part.Parent = Workspace.Terrain
		local conn: RBXScriptConnection
		conn = RunService.Heartbeat:Connect(function()
			if not alive or not part.Parent or (anchor and not anchor.Parent) or not step() then
				conn:Disconnect()
				part:Destroy()
			end
		end)
	end)
	return function()
		alive = false
	end
end

-- fading copies of a character every `interval` while it moves (Time Surge, dashes, speed modes).
-- Stops by itself when the character dies or leaves; stop() ends it early.
local function playAfterimages(el: any, model: Model): () -> ()
	local running = true
	local folder = Instance.new("Folder")
	folder.Name = "KitVfxAfterimages"
	folder.Parent = Workspace.Terrain
	local material = (Enum.Material :: any)[el.material or "Neon"]
	local function cleanupLater()
		task.delay((el.lifetime or 1) + 0.2, function()
			folder:Destroy()
		end)
	end
	task.spawn(function()
		local lastPos: Vector3? = nil
		local t0 = os.clock()
		local humanoid = model:FindFirstChildOfClass("Humanoid")
		while running and model.Parent and not (humanoid and humanoid.Health <= 0) do
			local root = model.PrimaryPart or model:FindFirstChild("HumanoidRootPart")
			local pos = if root and root:IsA("BasePart") then root.Position else nil
			if pos and (lastPos == nil or (pos - lastPos).Magnitude > 0.5) then
				lastPos = pos
				-- cycle: the copy's colour comes from the sequence by clock time (rainbow trails); else it fades
				local phase = if el.cycle then ((os.clock() - t0) / el.cycle) % 1 else nil
				local ghost: { BasePart } = {}
				for _, d in model:GetDescendants() do
					if d:IsA("BasePart") and d.Transparency < 1 and d.Name ~= "HumanoidRootPart" then
						local c = d:Clone() -- nil when the part is not Archivable
						if not c then
							continue
						end
						for _, child in c:GetChildren() do
							-- keep the shape (R6 heads and classic hats are Part + SpecialMesh); drop everything else
							if child:IsA("DataModelMesh") then
								if child:IsA("FileMesh") then
									child.TextureId = ""
								end
							else
								child:Destroy()
							end
						end
						c.Anchored = true
						c.CanCollide = false
						c.CanQuery = false
						c.CanTouch = false
						c.CastShadow = false
						c.Massless = true
						c.Material = material
						if c:IsA("MeshPart") then
							c.TextureID = ""
						end
						c.CFrame = d.CFrame
						c.Parent = folder
						table.insert(ghost, c)
					end
				end
				local born = os.clock()
				task.spawn(function()
					while os.clock() - born < el.lifetime do
						local u = (os.clock() - born) / el.lifetime
						local color = colorAt(el.color, phase or u)
						local tr = numAt(el.transparency, u, u)
						for _, c in ghost do
							c.Color = color
							c.Transparency = tr
						end
						RunService.Heartbeat:Wait()
					end
					for _, c in ghost do
						c:Destroy()
					end
				end)
			end
			task.wait(el.interval)
		end
		if running then -- ended on its own (death / left): don't leave the folder behind
			running = false
			cleanupLater()
		end
	end)
	return function()
		if running then
			running = false
			cleanupLater()
		end
	end
end

-- screen colour grade + blur + FOV punch. hold = nil: hold until the returned stop() is called
local function playGrade(el: any, hold: number?): () -> ()
	local cc = Instance.new("ColorCorrectionEffect")
	cc.Name = "KitVfxGrade"
	cc.Brightness, cc.Contrast, cc.Saturation, cc.TintColor = 0, 0, 0, Color3.new(1, 1, 1)
	cc.Parent = Lighting
	local blur: BlurEffect? = nil
	if (el.blur or 0) > 0 then
		local b = Instance.new("BlurEffect")
		b.Name = "KitVfxGrade"
		b.Size = 0
		b.Parent = Lighting
		blur = b
	end
	local fov = el.fov or 0
	-- FOV is a delta on top of whatever the game sets. If something else writes FieldOfView meanwhile (a sprint
	-- or zoom script, a new camera after respawn), our previous delta is gone: start counting from 0 again, so
	-- we never subtract a delta that is no longer there.
	local applied, lastCamera, lastWritten = 0, nil :: Camera?, nil :: number?
	local fadeIn, fadeOut = el.fadeIn or 0.15, el.fadeOut or 0.35
	local function set(k: number)
		cc.Brightness = (el.brightness or 0) * k
		cc.Contrast = (el.contrast or 0) * k
		cc.Saturation = (el.saturation or 0) * k
		cc.TintColor = Color3.new(1, 1, 1):Lerp(rgb(el.tint or { 255, 255, 255 }), k)
		if blur then
			blur.Size = el.blur * k
		end
		local camera = Workspace.CurrentCamera
		if camera and fov ~= 0 then
			if camera ~= lastCamera or (lastWritten and math.abs(camera.FieldOfView - lastWritten) > 0.01) then
				applied = 0
			end
			local want = fov * k
			camera.FieldOfView += want - applied
			applied = want
			lastCamera, lastWritten = camera, camera.FieldOfView
		end
	end
	local stopped = false
	local function fade(from: number, to: number, time: number)
		local t0 = os.clock()
		while os.clock() - t0 < time do
			local k = (os.clock() - t0) / time
			set(from + (to - from) * (1 - (1 - k) * (1 - k)))
			RunService.RenderStepped:Wait()
		end
		set(to)
	end
	local function finish()
		fade(1, 0, fadeOut)
		cc:Destroy()
		if blur then
			blur:Destroy()
		end
	end
	task.spawn(function()
		fade(0, 1, fadeIn)
		if hold then
			task.wait(hold)
			finish()
		else
			while not stopped do
				task.wait(0.05)
			end
			finish()
		end
	end)
	return function()
		stopped = true
	end
end

-- grades are screen effects: decide whether THIS client should see one
local function gradeVisible(el: any, position: Vector3, owner: Player?): boolean
	if not RunService:IsClient() then
		return false
	end
	local who = el.who or (if owner then "owner" else "near")
	if who == "owner" then
		return owner ~= nil and owner == Players.LocalPlayer
	elseif who == "near" then
		return falloff(position, el.radius) > 0
	end
	return true
end

-- ---------------------------------------------------------------- public API
function Vfx.has(name: string): boolean
	return presets[name] ~= nil
end

-- build a version-3 preset's runtime meshes AHEAD of its first play (in a task: building one yields ~0.2-0.35 s, which
-- an impact's first frames cannot wait for): `copies` of every mesh layer's shape and of every mesh trail's ribbon,
-- kept in VfxMesh's pool. Call it when the effect becomes possible (a weapon equipped), not at the hit.
-- what the kit keeps beside the presets and a layer names (VfxPresets.fractures.<name>, VfxPresets.fields.<name>)
local function keptLoader(folderName: string): (string) -> any
	return function(itemName: string): any
		local folder = presetFolder:FindFirstChild(folderName)
		local m = folder and folder:FindFirstChild(itemName)
		return if m and m:IsA("ModuleScript") then (require :: any)(m) else nil
	end
end

-- MESHES ARE MADE BEFORE THE EFFECT, NOT DURING IT (ten cold Studio sessions, 2026-11-16: an effect of two mesh
-- layers played 2 to 5 s into a client's life showed NO mesh in 8 of 10 - nothing refused: the engine's
-- CreateMeshPartAsync takes 1.15 to 1.65 s a call while the player's avatar is loading, 0.15 to 0.22 s after, and an
-- effect's meshes are built one after another on its own clock).
--   Vfx.prewarmAtSpawn({ names })   client: waits until the local player's avatar has loaded, then makes every mesh
--                                   of those presets into the pool, off any effect's clock; calls back when done
--   Vfx.prewarm(name)               the same for one preset, now (in the background)
--   Vfx.isWarm(name)                does the pool HOLD every mesh it builds, now (checked, not remembered: an effect
--                                   that plays takes them and gives them back; one the pool could not keep is not warm).
--                                   A mesh sequence's frames and a mark draped over the ground are built at play, never
--                                   kept: they are left out of it
--   Vfx.coldPlays()                 -> (cold, early): version 3 plays on this client of a preset that was not warm; and
--                                   those of them made before the avatar had loaded or just after (Vfx.SPAWN_QUIET) -
--                                   the ones whose meshes may never show. Each preset played early is warned of once
-- THE CLIENT'S DETAIL LEVEL (Vfx.setDetail, below): declared here, where the warm-up reads it too
local detailLevel: string? = nil
local coldCount, earlyCount = 0, 0
local earlySaid: { [string]: boolean } = {}

local function planOf(planName: string): any
	local folder = presetFolder:FindFirstChild("fractures")
	local m = folder and folder:FindFirstChild(planName)
	local ok, plan = pcall(function(): any
		return if m and m:IsA("ModuleScript") then (require :: any)(m) else nil
	end)
	return if ok
			and type(plan) == "table"
			and type(plan.pieces) == "table"
			and type(plan.size) == "table"
		then plan
		else nil
end

-- what a preset's layers build, by the pool's key, with the params the STAGE builds them with (VfxStage: mesh layers,
-- a debris layer's rocks - seeds i + seed x 37 - or its fracture's pieces, a swarm's eight stones cycled, a ribbon)
-- -> ({ { shape, params, wobble, erode, n } | { ribbon, samples, reach, n } }, the meshes built at play and never kept)
-- level: the play's detail level - a layer it drops builds nothing (VfxStage drops it the same way)
local needsCache: { [any]: any } = setmetatable({}, { __mode = "k" }) :: any
local function needsOf(preset: any, level: string?): ({ any }, number)
	local byLevel = needsCache[preset]
	if not byLevel then
		byLevel = {}
		needsCache[preset] = byLevel
	end
	local cached = byLevel[level or ""]
	if cached then
		return cached.needs, cached.unpooled
	end
	local tiers = if level ~= nil then VfxBudget.auto(preset.layers) else {}
	local out, byKey, unpooled = {}, {}, 0
	local function want(shape: string, params: any, wobble: any, erode: any)
		local key = VfxMesh.keyOf(shape, params, wobble, erode)
		local w = byKey[key]
		if w then
			w.n += 1
		else
			w = { shape = shape, params = params, wobble = wobble, erode = erode, n = 1, key = key }
			byKey[key] = w
			table.insert(out, w)
		end
	end
	local ribbons: any = nil
	for index, raw in preset.layers or {} do
		local el = if type(raw) == "table" then VfxBudget.layerAt(raw, level, tiers[index]) else nil
		if type(el) ~= "table" then
			continue
		end
		if el.kind == "mesh" then
			if el.shape == "seq" or not VfxMesh.SHAPES[el.shape or "ring"] then
				unpooled += 1
			else
				want(el.shape or "ring", el.params, el.wobble, el.erode)
			end
		elseif el.kind == "trail" and el.mesh == true then
			-- ribbons: ONE need of them all, of the most samples and reach any asks (a kept ribbon serves one as long or
			-- shorter; two layers of one size were each served by the same ribbon); the reach at scale 1.5 (warmNow
			-- says a play at a greater scale is cold for them)
			if not ribbons then
				ribbons = { ribbon = true, samples = 4, reach = 0, n = 0 }
				table.insert(out, ribbons)
			end
			ribbons.samples = math.max(ribbons.samples, math.clamp(el.samples or 48, 4, 120))
			ribbons.reach = math.max(ribbons.reach, (el.reach or 12) * 1.5)
			ribbons.n += 1
		elseif el.kind == "decal" and (el.wrap == true or type(el.wrap) == "number") then
			unpooled += 1
		elseif el.kind == "swarm" and el.shape == "Rock" then
			local rock: any = if type(el.rock) == "table" then el.rock else {}
			for i = 1, math.clamp(el.count or 40, 1, 40) do
				want("rock", {
					seed = 500 + ((i - 1) % 8) + (el.seed or 0) * 37,
					cuts = rock.cuts,
					jag = rock.jag,
					spike = rock.spike,
					flat = rock.flat,
				}, nil, nil)
			end
		elseif el.kind == "debris" and type(el.pieces) == "string" then
			local plan = planOf(el.pieces)
			if plan then
				for _, pc in plan.pieces do
					want("piece", {
						points = pc.points,
						height = plan.size[3],
						centre = pc.centre,
						slab = { plan.size[1], plan.size[2] },
					}, nil, nil)
				end
			end
		elseif el.kind == "debris" and el.shape == "rock" then
			for i = 1, math.min(el.count or 6, 40) do
				want(
					"rock",
					{ seed = i + (el.seed or 0) * 37, cuts = el.cuts, jag = el.jag, spike = el.spike, flat = el.flat },
					nil,
					nil
				)
			end
		end
	end
	byLevel[level or ""] = { needs = out, unpooled = unpooled }
	return out, unpooled
end

local function avatarLoaded(): boolean
	local player = Players.LocalPlayer
	if not player or not player.Character then
		return false
	end
	local ok, loaded = pcall(function()
		return player:HasAppearanceLoaded()
	end)
	return not ok or loaded == true
end

-- WHEN the avatar was first seen loaded (the client's clock), nil until then. The engine is still slow for a while
-- AFTER that (found proving this: three plays made 0.02 to 0.41 s after the character appeared showed no mesh, and
-- were not called early): a play is early until SPAWN_QUIET seconds after it. A place with no characters: the client's
-- first SPAWN_WAIT seconds count as the avatar's loading (it was early for ever)
local avatarSince: number? = nil
Vfx.SPAWN_QUIET = 3 -- seconds after the avatar has loaded in which a mesh is still built slowly (measured: 1.65 s a call at most)
Vfx.SPAWN_WAIT = 20 -- seconds at most that the avatar is waited for (a place with no characters: then it goes on)
if RunService:IsClient() then
	task.spawn(function()
		local t0 = os.clock()
		while not avatarLoaded() and os.clock() - t0 < Vfx.SPAWN_WAIT do
			task.wait(0.1)
		end
		avatarSince = os.clock()
	end)
end

local function tooEarly(): boolean
	return avatarSince == nil or os.clock() - avatarSince < Vfx.SPAWN_QUIET
end

local function warmNow(preset: any, level: string?, scale: number?): boolean
	local needs = needsOf(preset, level)
	for _, w in needs do
		-- (a ribbon is built at reach x scale: the pool must hold ones that long for THIS play - kept at 1.5 by a
		-- warm-up, or longer by an earlier play at a greater scale)
		local have = if w.ribbon
			then VfxMesh.keptRibbons(w.samples, w.reach / 1.5 * math.max(scale or 1, 1))
			else VfxMesh.keptKey(w.key)
		if have < w.n then
			return false
		end
	end
	return true
end

-- (called by every version 3 play on a client, before its stage is made)
local function noteCold(name: string, preset: any, level: string?, scale: number?)
	if not RunService:IsClient() or #(needsOf(preset, level)) == 0 or warmNow(preset, level, scale) then
		return
	end
	coldCount += 1
	if tooEarly() then
		earlyCount += 1
		if not earlySaid[name] then
			earlySaid[name] = true
			warn(
				`[Vfx] "{name}" was played before its meshes were made, before or just after the player's avatar loaded: the engine builds a mesh in over a second then, and the effect may be over first (its mesh layers draw their plain stand-in meanwhile). Vfx.prewarmAtSpawn(\{ "{name}" \}) makes them ahead`
			)
		end
	end
end

function Vfx.isWarm(name: string): boolean
	local preset = presets[name]
	if type(preset) ~= "table" then
		return false
	end
	return warmNow(preset, detailLevel, 1)
end

function Vfx.coldPlays(): (number, number)
	return coldCount, earlyCount
end

-- what every warm-up so far asked the pool to keep, by preset (a second preset warmed must not push the first one's
-- out; the SAME preset warmed again - a game that warms on every respawn - asks once, not once a respawn)
local keepAsks: { [string]: number } = {} -- (by the preset's NAME: one loaded again is a new table)
local keepPerKey = 0
local function prewarmNow(name: string, preset: any, n: number): boolean
	local needs = needsOf(preset, detailLevel)
	local total = 0
	for _, w in needs do
		total += w.n * n
		keepPerKey = math.max(keepPerKey, w.n * n)
	end
	keepAsks[name] = math.max(keepAsks[name] or 0, total)
	local keepAsked = 0
	for _, k in keepAsks do
		keepAsked += k
	end
	VfxMesh.keep(keepAsked, keepPerKey)
	if keepAsked > VfxMesh.KEEP_MOST then
		warn(
			`[Vfx] the effects warmed so far need {keepAsked} meshes kept ahead; the pool keeps {VfxMesh.KEEP_MOST} at most (the engine's memory): some will be built when they play`
		)
	end
	for _, w in needs do
		if w.ribbon then
			VfxMesh.prewarmRibbon(w.samples, w.reach, w.n * n)
		else
			VfxMesh.prewarm(w.shape, w.params, w.wobble, w.erode, w.n * n)
		end
	end
	return warmNow(preset, detailLevel, 1)
end

function Vfx.prewarm(name: string, copies: number?)
	local preset = presets[name]
	if type(preset) ~= "table" or preset.version ~= 3 then
		return
	end
	task.spawn(function()
		prewarmNow(name, preset, copies or 1)
	end)
end

Vfx.SPAWN_SETTLE = 0.5 -- seconds after the avatar has loaded before the first mesh is made (they are made off any effect's clock: slow is no harm)
-- done(cold): called when every preset's meshes have been made; `cold` names the presets the pool could not hold whole
function Vfx.prewarmAtSpawn(names: { string }, done: ((cold: { string }) -> ())?, copies: number?)
	if not RunService:IsClient() then
		return
	end
	task.spawn(function()
		local t0 = os.clock()
		while not avatarLoaded() and os.clock() - t0 < Vfx.SPAWN_WAIT do
			task.wait(0.1)
		end
		task.wait(Vfx.SPAWN_SETTLE)
		for _, name in names do
			local preset = presets[name]
			if type(preset) == "table" and preset.version == 3 then
				prewarmNow(name, preset, copies or 1)
			end
		end
		local cold = {}
		for _, name in names do
			if not Vfx.isWarm(name) then
				table.insert(cold, name)
			end
		end
		if done then
			done(cold)
		end
	end)
end

local function assetsModule(): any
	if AssetsModule == nil then
		local ok, mod = pcall(require, script.Parent:FindFirstChild("Assets") :: ModuleScript)
		AssetsModule = if ok then mod else false
	end
	return AssetsModule or nil
end

-- version-3 presets (layer stacks on one clock): the stage itself, for hit-stop / slow motion / anchors.
--   local stage = Vfx.stage("starblade", cframe, { target = hitPos, anchors = { blade = swordBlade } })
--   stage:freeze(); task.wait(0.08); stage:resume()        (hit-stop)
-- THE CLIENT'S DETAIL LEVEL (the owner's limitations file, F-R06): "Low" | "Medium" | "High", or nil for none (the
-- default: every layer plays as written). Every version 3 effect played after this - Vfx.play, a broadcast, an
-- attach, an impact - drops the layers whose "tier" is above the level and cuts the ones with a "tierCount"
-- (src/kit/VfxBudget). The game sets it, from its own graphics setting; the kit does not guess one.
-- (detailLevel is declared above, with the warm-up that reads it)
function Vfx.setDetail(level: string?)
	detailLevel = if VfxBudget.rank(level) then level else nil
end
function Vfx.detail(): string?
	return detailLevel
end

function Vfx.stage(name: string, where: Vector3 | CFrame, opts: any?): VfxStage.Stage?
	local preset = presets[name]
	if not preset or preset.version ~= 3 then
		warn(`[Vfx] no version-3 preset "{name}"`)
		return nil
	end
	local o = table.clone(opts or {})
	o.detail = o.detail or detailLevel -- (the client's level, unless this play says its own: Vfx.setDetail)
	o.textures = textures
	o.assets = assetsModule()
	o.name = name
	o.seq = o.seq
		or function(
			seqName: string
		): any -- mesh sequences: VfxPresets.seq.<name> (assets/effects/seq, kit/vfx/meshseq.py)
			local folder = presetFolder:FindFirstChild("seq")
			local m = folder and folder:FindFirstChild(seqName)
			return if m and m:IsA("ModuleScript") then (require :: any)(m) else nil
		end
	o.fracture = o.fracture
		or function(
			planName: string
		): any -- fracture plans: VfxPresets.fractures.<name> (assets/effects/fractures, kit/vfx/fracture.py)
			local folder = presetFolder:FindFirstChild("fractures")
			local m = folder and folder:FindFirstChild(planName)
			return if m and m:IsA("ModuleScript") then (require :: any)(m) else nil
		end
	o.field = o.field
		or function(
			fieldName: string
		): any -- authored vector fields: VfxPresets.fields.<name> (assets/effects/fields, kit/vfx/field.py)
			local folder = presetFolder:FindFirstChild("fields")
			local m = folder and folder:FindFirstChild(fieldName)
			return if m and m:IsA("ModuleScript") then (require :: any)(m) else nil
		end
	o.cloud = o.cloud or keptLoader("points") -- point clouds: VfxPresets.points.<name> (assets/effects/points, kit/vfx/points.py)
	local cframe = if typeof(where) == "CFrame" then where else CFrame.new(where :: Vector3)
	noteCold(name, preset, o.detail, o.scale)
	return VfxStage.play(preset, cframe, o)
end

-- target: optional Vector3 for beams with "to": "target" (a laser's hit point, a lightning strike's ground point)
-- returns the effect's container (a Part for version 1/2 presets, a Folder for version 3)
-- late: REAL seconds the effect should already have been playing (a broadcast that arrived late): a version 3 stage
-- runs its clock to where it would be by now before its first frame; older (version 1 / 2) presets play from their start
function Vfx.play(
	name: string,
	where: Vector3 | CFrame,
	scale: number?,
	parent: Instance?,
	target: Vector3?,
	late: number?
): Instance?
	local preset = presets[name]
	if preset and preset.version == 3 then
		local stage = Vfx.stage(name, where, { scale = scale, parent = parent, target = target, late = late })
		return stage and stage.root
	end
	if not preset or preset.mode == "attach" then
		warn(`[Vfx] no burst preset "{name}"`)
		return nil
	end
	local s = scale or 1
	local cframe = if typeof(where) == "CFrame" then where else CFrame.new(where :: Vector3)
	local holder = effectPart(`Vfx_{name}`, cframe, parent or Workspace)
	holder.Transparency = 1
	holder.Size = Vector3.one * 0.2
	local attachment = Instance.new("Attachment")
	attachment.Parent = holder
	local isClient = RunService:IsClient()
	for _, el in preset.elements do
		local function run()
			if not holder.Parent then
				return
			end
			local kind = el.kind
			if kind == "sound" then
				playSound(el, cframe.Position)
			elseif kind == "shake" then
				if isClient then
					addShake(el.intensity * 0.5 * falloff(cframe.Position, el.radius))
				end
			elseif kind == "screen" then
				if isClient then
					screenFlash(el, cframe.Position)
				end
			elseif kind == "beam" then
				beam(el, cframe, target, s, preset.duration)
			elseif kind == "mesh" then
				playMesh(el, function()
					return cframe
				end, s, false)
			elseif kind == "grade" then
				if gradeVisible(el, cframe.Position, nil) then
					playGrade(el, el.time)
				end
			else
				playElement(el, holder, attachment, s, preset.duration)
			end
		end
		if el.delay and el.delay > 0 then
			task.delay(el.delay, run)
		else
			run()
		end
	end
	Debris:AddItem(holder, preset.duration)
	return holder
end

function Vfx.attach(name: string, part: BasePart, offset: CFrame?, scale: number?): () -> ()
	local preset = presets[name]
	if not preset or preset.mode ~= "attach" then
		warn(`[Vfx] no attach preset "{name}"`)
		return function() end
	end
	if preset.version == 3 then -- a layer stack riding the part until stop()
		noteCold(name, preset, detailLevel, scale)
		local stage = VfxStage.play(preset, part.CFrame * (offset or CFrame.identity), {
			follow = part,
			offset = offset,
			scale = scale,
			textures = textures,
			assets = assetsModule(),
			name = name,
			detail = detailLevel, -- (the client's detail level: an attached effect is tiered as every other)
			anchors = { part = part },
			-- (an aura round a character is the natural home of a vortex: attached effects read their fields and
			-- fracture plans as staged ones do)
			fracture = keptLoader("fractures"),
			field = keptLoader("fields"),
			cloud = keptLoader("points"),
		})
		return function()
			stage:stop()
		end
	end
	local s = scale or 1
	local attachment = Instance.new("Attachment")
	attachment.Name = `Vfx_{name}`
	attachment.CFrame = offset or CFrame.identity
	attachment.Parent = part
	local made: { Instance } = { attachment }
	local stoppers: { () -> () } = {}
	local model = part:FindFirstAncestorOfClass("Model")
	local owner = if model then Players:GetPlayerFromCharacter(model) else nil
	for _, el in preset.elements do
		if el.kind == "mesh" then
			table.insert(
				stoppers,
				playMesh(el, function()
					return attachment.WorldCFrame
				end, s, true, attachment)
			)
		elseif el.kind == "afterimage" then
			if model then
				table.insert(stoppers, playAfterimages(el, model))
			end
		elseif el.kind == "grade" then
			if gradeVisible(el, part.Position, owner) then
				table.insert(stoppers, playGrade(el, nil))
			end
		elseif el.kind == "particles" then
			local pe = emitter(el, s)
			pe.Parent = attachment
		elseif el.kind == "light" then
			local light = Instance.new("PointLight")
			light.Color = rgb(el.color or { 255, 255, 255 })
			light.Range = math.min(el.range * s, 60)
			light.Brightness = el.brightness[1]
			light.Parent = attachment
		elseif el.kind == "trail" then
			local half = (el.width or 1) * s / 2
			local a0 = Instance.new("Attachment")
			a0.CFrame = attachment.CFrame * CFrame.new(0, half, 0)
			a0.Parent = part
			local a1 = Instance.new("Attachment")
			a1.CFrame = attachment.CFrame * CFrame.new(0, -half, 0)
			a1.Parent = part
			local trail = Instance.new("Trail")
			trail.Attachment0 = a0
			trail.Attachment1 = a1
			trail.Lifetime = el.lifetime
			trail.Color = colorSeq(el.color or { 255, 255, 255 })
			trail.Transparency = numberSeq(el.transparency or 0, 1)
			trail.LightEmission = el.lightEmission or 0
			trail.FaceCamera = true
			trail.MinLength = 0
			trail.Parent = part
			table.insert(made, a0)
			table.insert(made, a1)
			table.insert(made, trail)
		end
	end
	return function()
		for _, stop in stoppers do
			stop()
		end
		for _, inst in made do
			if inst:IsA("Attachment") then
				for _, child in inst:GetChildren() do
					if child:IsA("ParticleEmitter") then
						child.Enabled = false
					end
				end
			end
		end
		task.delay(2, function()
			for _, inst in made do
				inst:Destroy()
			end
		end)
	end
end

local remote: RemoteEvent? = nil
if RunService:IsServer() then
	local existing = ReplicatedStorage:FindFirstChild(REMOTE_NAME)
	if existing and existing:IsA("RemoteEvent") then
		remote = existing
	else
		local created = Instance.new("RemoteEvent")
		created.Name = REMOTE_NAME
		created.Parent = ReplicatedStorage
		remote = created
	end
end

-- how long a preset REALLY plays, in real seconds (its duration, its hit-stops' holds and its slow motion together;
-- math.huge: until it is stopped) - what a late broadcast is measured against
function Vfx.realLengthOf(name: string): number
	local preset = presets[name]
	if not preset then
		return 0
	end
	if type(preset.duration) ~= "number" then
		return if preset.mode == "attach" then math.huge else 5
	end
	return VfxNet.realLength(preset.duration, preset.hitstop, preset.timewarp)
end

-- WHO IS SENT AN EFFECT (the owner's limitations file, F-R03). The audience is a reach in studs round the effect's
-- origin and round its target: opts.reach (false or "all" = everyone), else the preset's own "reach", else the
-- game's (Vfx.setReach), else the kit's rule from the effect's own size (VfxNet.audience). A player with no
-- character is always sent it (a spectator's camera can be anywhere). Every event is stamped with the server's clock,
-- so a client knows how late it is (VfxClient). A player who comes INTO reach while the effect still lasts is sent it
-- then, with its first stamp: their client starts it where its clock is by now. Returns how many clients it was sent
-- to at once.
-- NOT covered, and why: reach is measured from the character, not the camera (the server is not told a client's
-- camera); an effect that never ends by itself (attach mode) is not kept for those who come later; a version 1 / 2
-- preset sent late plays from its start (only the version 3 stage can run its clock on).
local gameReach: any = nil -- Vfx.setReach: a number of studs, false (everyone), nil (the kit's rule)
local live: { any } = {} -- events that went to an audience and still last (VfxNet.newcomers)
local watching = false
local LOOK_EVERY = 0.25 -- seconds between two looks for who has come into reach

-- one reach for every effect that says none of its own (studs); false = everyone is sent everything; nil = the kit's
-- rule (the effect's own size)
function Vfx.setReach(v: any)
	gameReach = if v == false then false elseif type(v) == "number" and v > 0 then v else nil
end

local function placeOf(player: Player): any
	local character = player.Character
	if not character then
		return false
	end
	local at = character:GetPivot().Position
	return { at.X, at.Y, at.Z }
end

local function watch()
	if watching then
		return
	end
	watching = true
	task.spawn(function()
		while #live > 0 do
			task.wait(LOOK_EVERY)
			-- (one look that throws must not end the watch for good: no one would be served again, and the list would
			-- never be emptied)
			local ok, why = pcall(function()
				local places = {}
				for _, player in Players:GetPlayers() do
					places[player] = placeOf(player)
				end
				for _, send in VfxNet.newcomers(live, Workspace:GetServerTimeNow(), places, false) do
					local ev = send[2]
					if remote and (send[1] :: Player).Parent then
						remote:FireClient(send[1], ev.name, ev.where, ev.scale, ev.target, ev.sent)
					end
				end
			end)
			if not ok then
				warn(`[Vfx] the look for who came into reach failed: {why}`)
			end
		end
		watching = false
	end)
end

function Vfx.broadcast(
	name: string,
	where: Vector3 | CFrame,
	scale: number?,
	target: Vector3?,
	opts: { reach: any }?
): number
	assert(RunService:IsServer(), "Vfx.broadcast is server-only; clients call Vfx.play")
	local preset = presets[name]
	if not preset then
		warn(`[Vfx] broadcast of unknown preset "{name}"`)
		return 0
	end
	if not remote then
		return 0
	end
	local sent = Workspace:GetServerTimeNow()
	-- (a version 1 / 2 preset keeps its parts in `elements`: read as none, every one of them was sent 300 studs)
	local extent, felt = VfxNet.extent(preset.layers or preset.elements)
	local reach = VfxNet.audience(
		if type(opts) == "table" then opts.reach else nil,
		preset.reach,
		gameReach,
		scale or 1,
		extent,
		felt
	)
	if reach == nil then
		remote:FireAllClients(name, where, scale or 1, target, sent)
		return #Players:GetPlayers()
	end
	local origin = if typeof(where) == "CFrame" then (where :: CFrame).Position else where :: Vector3
	local length = Vfx.realLengthOf(name)
	local ev = {
		name = name,
		where = where,
		scale = scale or 1,
		target = target,
		sent = sent,
		x = origin.X,
		y = origin.Y,
		z = origin.Z,
		tx = if target then target.X else nil,
		ty = if target then target.Y else nil,
		tz = if target then target.Z else nil,
		reach = reach,
		over = sent + length,
		to = {},
	}
	local places = {}
	for _, player in Players:GetPlayers() do
		places[player] = placeOf(player)
	end
	local first = VfxNet.newcomers({ ev }, sent - 1, places, true) -- (the same rule as for those who come later)
	for _, send in first do
		remote:FireClient(send[1], name, where, scale or 1, target, sent)
	end
	if length > 0 and length < math.huge then
		table.insert(live, ev)
		watch()
	end
	return #first
end

Vfx.REMOTE_NAME = REMOTE_NAME

return Vfx

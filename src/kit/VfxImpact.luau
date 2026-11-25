-- VfxImpact (ReplicatedStorage.KitVfx.VfxImpact) — a hit's impact one-shot BY SURFACE, in one call: the kind from
-- the material, the look from ONE version-3 preset whose layers carry `onMaterial` overrides keyed by the kind
-- ("Stone|Brick": dust + chips, "Wood": splinters, "Metal": sparks + a hot glow, "Water": a splash + ring, ...).
--   VfxImpact.kindOf(material) -> kind               every Enum.Material, parts AND terrain, -> one of VfxImpact.KINDS
--   VfxImpact.play(kind, pos, normal, color?) -> ok  ok = false: no look for that kind / culled / over the cap
--   VfxImpact.hit(result: RaycastResult) -> ok        the kind + colour from the ray (terrain: the material's colour)
--   VfxImpact.configure({ preset = "impact", maxLive = 10, cull = 350, detail = "Low" | "Medium" | "High" })
--   A detail level also sets what each impact is MADE of: the preset's layers say the lowest level they play at
--   ("tier": "Medium") and the share of their count a level keeps ("tierCount": { Low = 0.4 }) - src/kit/VfxBudget.
--   VfxImpact.ready() -> can an impact play NOW. Not yet (the kit or the presets have not replicated) is not "never":
--       it is looked for again, RETRY_EVERY seconds apart at most; after RETRY_FOR seconds that is said once, and it is
--       looked for every RETRY_SLOW seconds from then on (never given up for good)
-- The preset is played with opts.material = the kind and opts.palette = { surface, surfaceDark } (the hit part's
-- Color), so chips are the wall's own colour. Its +Y is the surface normal (spread layers fan out of the surface).
-- NEVER an EditableMesh (a Play client holds ~8, the sword keeps 5): a preset with a mesh layer, rock debris, a mesh
-- trail or a crater anywhere (overrides included) is refused once with a warning. Chips are `debris` with
-- floor = "world": real physics, they fall to the real ground and bounce.
-- Client only (cosmetic, local): the caller relays other players' shots itself, as GunFx does.
--   VfxImpact.onVictimHit(victim: Model, hit: CFrame, cutNormal: Vector3, power: 0..10?, opts?) -> boolean
--       F2 (LIMITATIONS_FIXES_V4 3.4 step 3): a struck body's reaction - LIGHT ONLY, never blood (src/kit/VfxVictim.luau):
--       a white rim flash on a pooled Highlight slot (VfxStage's 31-slot pool, as a HERO), sparks thrown along the
--       cut's normal (ONE emitter, Emit(n)), and a hitstop tremor on the body (its root joint's C0, alternating sides
--       each 60 fps frame, back where it was on the last). opts = { hitstop = frames (0..30), color = {r, g, b} } -
--       a blood-red colour is refused (warm white sparks instead, said once). false: no body to react.
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")
-- (the victim's rules are required when a victim is first hit, not here: kit/test/spec/vfx.spec.luau loads this file
-- in a sandbox with no require, for its pure kind-of-material table)
local VfxVictim: any = nil

local VfxImpact = {}

VfxImpact.KINDS = {
	"Stone",
	"Brick",
	"Plaster",
	"Wood",
	"Metal",
	"Glass",
	"Plastic",
	"Fabric",
	"Dirt",
	"Sand",
	"Grass",
	"Snow",
	"Water",
	"Rubber",
}

-- Enum.Material names (strings: a material newer than the running engine never errors) -> kind; the rest = DEFAULT
local KIND_OF: { [string]: string } = {
	Concrete = "Stone",
	Slate = "Stone",
	Granite = "Stone",
	Marble = "Stone",
	Pebble = "Stone",
	Cobblestone = "Stone",
	Rock = "Stone",
	Basalt = "Stone",
	Limestone = "Stone",
	Sandstone = "Stone",
	Pavement = "Stone",
	Asphalt = "Stone",
	CrackedLava = "Stone",
	CeramicTiles = "Stone",
	RoofShingles = "Stone",
	Brick = "Brick",
	ClayRoofTiles = "Brick",
	Plaster = "Plaster",
	Wood = "Wood",
	WoodPlanks = "Wood",
	Cardboard = "Wood",
	Metal = "Metal",
	CorrodedMetal = "Metal",
	DiamondPlate = "Metal",
	Foil = "Metal",
	Glass = "Glass",
	ForceField = "Glass",
	Plastic = "Plastic",
	SmoothPlastic = "Plastic",
	Neon = "Plastic",
	Fabric = "Fabric",
	Carpet = "Fabric",
	Leather = "Fabric",
	Ground = "Dirt",
	Mud = "Dirt",
	Clay = "Dirt",
	Sand = "Sand",
	Salt = "Sand",
	Grass = "Grass",
	LeafyGrass = "Grass",
	Snow = "Snow",
	Ice = "Snow",
	Glacier = "Snow",
	Water = "Water",
	Rubber = "Rubber",
}
local DEFAULT = "Plaster" -- (the hole runtime's own fallback: the two always agree)

local config = { preset = "impact", maxLive = 10, cull = 350, detail = nil :: string? }
-- a graphics setting's level -> how many play at once and how far away they still play (maxLive / cull win when given)
local DETAIL = {
	Low = { maxLive = 3, cull = 120 },
	Medium = { maxLive = 6, cull = 220 },
	High = { maxLive = 10, cull = 350 },
}
local live: { any } = {}
-- preset name -> playable, or refused FOR GOOD (it loaded and would build EditableMeshes; the kit's module threw; it
-- never came). What is only NOT THERE YET is not in here (the owner's limitations file, F-R02: an impact asked for
-- before the kit had replicated was remembered as unplayable, and no impact played for the rest of the session)
local checked: { [string]: boolean } = {}
local waiting: { [string]: { since: number, last: number, gaveUp: boolean } } = {} -- preset name -> since when it is waited for, when last looked for, said to be late
local Vfx: any = nil -- nil: not there yet (looked for again); false: its module threw (for good)
VfxImpact.RETRY_EVERY = 0.5 -- seconds: the least between two looks for what has not come yet (a burst of hits does not search every hit)
VfxImpact.RETRY_FOR = 60 -- seconds: how long it is waited for before it is said, once, that it has not come
VfxImpact.RETRY_SLOW = 10 -- seconds between two looks after that (never given up for good: a slow place still gets its impacts)

function VfxImpact.configure(o: { preset: string?, maxLive: number?, cull: number?, detail: string? })
	local was = config.preset
	local level = o.detail and DETAIL[o.detail]
	if level then
		config.maxLive, config.cull = level.maxLive, level.cull
		-- ... and what each impact is MADE of: the preset's layers carry "tier" / "tierCount", and the stage drops
		-- and cuts by this level (the owner's limitations file, F-R06: a level changed only how many and how far)
		config.detail = o.detail
	end
	for k, v in o :: any do
		if k ~= "detail" then
			(config :: any)[k] = v
		end
	end
	if o.preset and o.preset ~= was then -- ANOTHER preset: nothing is remembered of it (the same name again changes nothing)
		checked[o.preset] = nil
		waiting[o.preset] = nil
	end
end

function VfxImpact.kindOf(material: Enum.Material | string): string
	local name = if typeof(material) == "EnumItem" then (material :: EnumItem).Name else tostring(material)
	return KIND_OF[name] or DEFAULT
end

-- the layers of a preset that would build an EditableMesh (pure: the offline test reads it); [] = budget-safe
function VfxImpact.meshLayers(preset: any): { string }
	local out = {}
	local function check(el: any, path: string)
		if type(el) ~= "table" then
			return
		end
		if
			el.kind == "mesh"
			or el.kind == "crater"
			or (el.kind == "trail" and el.mesh == true)
			or (el.kind == "debris" and el.shape == "rock")
		then
			table.insert(out, path)
		end
	end
	for i, el in if type(preset) == "table" then preset.layers or {} else {} do
		local path = `layers[{i}]{if type(el.name) == "string" then " " .. el.name else ""}`
		check(el, path)
		for pattern, over in if type(el.onMaterial) == "table" then el.onMaterial else {} do
			if type(over) == "table" and not over.mute then
				-- the layer as that surface plays it (VfxStage's withMaterial: the override's keys over the layer's)
				local merged = table.clone(el)
				for k, v in over do
					merged[k] = v
				end
				check(merged, `{path}.onMaterial.{pattern}`)
			end
		end
	end
	return out
end

-- the kit's Vfx module: nil while it (or the presets' folder, or its texture registry) is NOT THERE YET - nothing is
-- remembered then, it is looked for again; false for good only when the module is there and THROWS.
-- It is looked for BESIDE this module first (the kit's runtime is one folder: ReplicatedStorage.kit in a kit project),
-- then by the names it has been mounted under (kit, KitVfx). It was looked for as KitVfx alone: in a kit project no
-- impact could ever play (a review, 2026-11-15).
local function vfxModule(): any
	local here: any = script
	local folders = {
		if here ~= nil then here.Parent else nil,
		ReplicatedStorage:FindFirstChild("kit"),
		ReplicatedStorage:FindFirstChild("KitVfx"),
	}
	for i = 1, 3 do
		local folder = folders[i]
		local module = if folder then folder:FindFirstChild("Vfx") else nil
		if module then
			return module
		end
	end
	return nil
end

local function vfx(): any
	if Vfx == nil then
		local module = vfxModule()
		local presets = ReplicatedStorage:FindFirstChild("VfxPresets")
		-- (Vfx waits for the presets' "_textures" when it is required, with no time limit: requiring it before that
		-- child is there would hold the shooter's own code)
		if not module or not presets or not presets:FindFirstChild("_textures") then
			return nil
		end
		local ok, mod = pcall(require, module)
		Vfx = if ok then mod else false
		if not ok then
			warn(`[VfxImpact] the kit's Vfx module threw, no impact will play: {mod}`)
		end
	end
	return Vfx or nil
end

local function playable(name: string): boolean
	if checked[name] ~= nil then
		return checked[name]
	end
	local now = os.clock()
	local w = waiting[name]
	if w and now - w.last < (if w.gaveUp then VfxImpact.RETRY_SLOW else VfxImpact.RETRY_EVERY) then
		return false -- looked for a moment ago: not again for every hit of a burst
	end
	local v = vfx()
	if Vfx == false then
		checked[name] = false
		return false
	end
	local folder = ReplicatedStorage:FindFirstChild("VfxPresets")
	local module = folder and folder:FindFirstChild(name)
	if v == nil or not v.has(name) or module == nil or not module:IsA("ModuleScript") then
		-- NOT YET: the kit, the presets' folder or this preset has not replicated (or the kit did not take the
		-- preset). Remembered only as "waited for": after RETRY_FOR seconds it is said once, and looked for more slowly
		local wait: { since: number, last: number, gaveUp: boolean } = if w
			then w
			else { since = now, last = now, gaveUp = false }
		wait.last = now
		waiting[name] = wait
		if not wait.gaveUp and now - wait.since >= VfxImpact.RETRY_FOR then
			wait.gaveUp = true
			warn(
				`[VfxImpact] {name}: not playable after {VfxImpact.RETRY_FOR} s - the kit's Vfx module is not there, or it has no preset "{name}" (one it rejected is said by [Vfx]); looked for every {VfxImpact.RETRY_SLOW} s from now`
			)
		end
		return false
	end
	waiting[name] = nil
	local got, raw = pcall(require, module :: ModuleScript)
	if not got then
		warn(`[VfxImpact] {name} refused: the preset's module threw ({raw})`)
		checked[name] = false
		return false
	end
	-- (found in the engine, 2026-11-15: an old preset - not version 3 - was "ready", and no impact of it ever played:
	-- the stage plays version 3 only)
	if type(raw) ~= "table" or raw.version ~= 3 then
		warn(`[VfxImpact] {name} refused: it is not a version-3 preset (the stage plays no other)`)
		checked[name] = false
		return false
	end
	local bad = VfxImpact.meshLayers(raw)
	if #bad > 0 then
		warn(`[VfxImpact] {name} refused: it would build EditableMeshes ({table.concat(bad, ", ")})`)
	end
	checked[name] = #bad == 0
	return checked[name]
end

-- can an impact play NOW (the configured preset): false while the kit has not replicated - and true once it has
function VfxImpact.ready(): boolean
	return playable(config.preset)
end

local function rgb(c: Color3, k: number): { number }
	return {
		math.floor(math.clamp(c.R * k, 0, 1) * 255 + 0.5),
		math.floor(math.clamp(c.G * k, 0, 1) * 255 + 0.5),
		math.floor(math.clamp(c.B * k, 0, 1) * 255 + 0.5),
	}
end

-- +Y along the normal, a random roll about it (no two hits alike)
local function frameOn(pos: Vector3, normal: Vector3): CFrame
	local up = if normal.Magnitude > 1e-3 then normal.Unit else Vector3.yAxis
	local ref = if math.abs(up.Y) < 0.95 then Vector3.yAxis else Vector3.xAxis
	local right = ref:Cross(up).Unit
	return CFrame.fromMatrix(pos, right, up, right:Cross(up)) * CFrame.Angles(0, math.random() * math.pi * 2, 0)
end

function VfxImpact.play(kind: string, pos: Vector3, normal: Vector3, color: Color3?): boolean
	local name = config.preset
	if not table.find(VfxImpact.KINDS, kind) or not playable(name) then
		return false
	end
	local cam = Workspace.CurrentCamera
	if cam and (cam.CFrame.Position - pos).Magnitude > config.cull then
		return false
	end
	for i = #live, 1, -1 do
		if live[i].finished then
			table.remove(live, i)
		end
	end
	if #live >= config.maxLive then
		return false -- a burst of fire: the hits already playing say it; the hole still lands (the caller's)
	end
	local palette = if color then { surface = rgb(color, 1), surfaceDark = rgb(color, 0.55) } else nil
	local ok, stage =
		pcall(vfx().stage, name, frameOn(pos, normal), { material = kind, palette = palette, detail = config.detail })
	if not ok then
		warn(`[VfxImpact] {name} ({kind}): {stage}`)
		return false
	end
	if stage then
		table.insert(live, stage)
	end
	return stage ~= nil
end

-- the VFX stage's Highlight slots (31 a client, heroes first): the victim's flash takes one like the stage's own rims
local function highlightSlots(): any
	local here: any = script
	local module = here and here.Parent and here.Parent:FindFirstChild("VfxStage")
	if not module then
		return nil
	end
	local ok, stage = pcall(require, module)
	return if ok and type(stage) == "table" then stage._highlights else nil
end

local saidBlood = false
local tremors: { [Instance]: boolean } = {}
function VfxImpact.onVictimHit(victim: Model, hit: CFrame, cutNormal: Vector3, power: number?, opts: any?): boolean
	if typeof(victim) ~= "Instance" or not victim:IsA("Model") or not victim.Parent then
		return false
	end
	if VfxVictim == nil then
		VfxVictim = require(script.Parent:WaitForChild("VfxVictim") :: ModuleScript) :: any
	end
	local o = opts or {}
	local p = VfxVictim.power(power)
	-- 1. the rim flash: a Highlight on the body, solid white the first frame, fading, on a HERO slot
	local flash = VfxVictim.flash(p)
	local h = Instance.new("Highlight")
	h.Name = "KitVictimFlash"
	h.FillColor = Color3.new(1, 1, 1)
	h.OutlineColor = Color3.new(1, 1, 1)
	h.DepthMode = Enum.HighlightDepthMode.Occluded
	h.Enabled = false
	h.Adornee = victim
	h.Parent = victim
	local slots = highlightSlots()
	local held = true
	if slots then
		local ok, lost = slots:claim(h, 2) -- VfxHighlight.HERO
		held = ok
		if lost ~= nil and typeof(lost) == "Instance" and (lost :: Instance):IsA("Highlight") then
			(lost :: Highlight).Enabled = false
		end
	end
	-- 2. sparks along the cut's normal: one emitter at the hit, an explicit burst
	local n = cutNormal
	local dir = VfxVictim.sparkDirection(if typeof(n) == "Vector3" then { n.X, n.Y, n.Z } else nil)
	local colour, refused = VfxVictim.sparkColor(o.color)
	if refused and not saidBlood then
		saidBlood = true
		warn(
			"[VfxImpact] onVictimHit: a blood-red spark colour was asked for - never drawn (warm white sparks instead)"
		)
	end
	local anchor = Instance.new("Part")
	anchor.Name = "KitVictimSparks"
	anchor.Anchored, anchor.CanCollide, anchor.CanQuery, anchor.CanTouch = true, false, false, false
	anchor.Transparency, anchor.Size = 1, Vector3.one * 0.1
	local up = Vector3.new(dir[1], dir[2], dir[3])
	local ref = if math.abs(up.Y) < 0.95 then Vector3.yAxis else Vector3.xAxis
	local right = ref:Cross(up).Unit
	anchor.CFrame = CFrame.fromMatrix(hit.Position, right, up, right:Cross(up))
	anchor.Parent = Workspace
	local at = Instance.new("Attachment")
	at.Parent = anchor
	local em = Instance.new("ParticleEmitter")
	em.Enabled, em.Rate = false, 0
	em.EmissionDirection = Enum.NormalId.Top -- the anchor's +Y is the cut's normal
	em.SpreadAngle = Vector2.new(22, 22)
	em.Speed = NumberRange.new(18 + 4 * p, 34 + 6 * p)
	em.Lifetime = NumberRange.new(0.12, 0.28)
	em.Drag = 6
	em.Acceleration = Vector3.new(0, -30, 0)
	em.Size = NumberSequence.new(0.18 + 0.02 * p, 0)
	em.Color = ColorSequence.new(Color3.fromRGB(colour[1], colour[2], colour[3]))
	em.LightEmission = 1
	em.LightInfluence = 0
	em.Transparency = NumberSequence.new(0, 1)
	em.Parent = at
	em:Emit(VfxVictim.sparkCount(p))
	-- 3. the hitstop tremor: the body's root joint shaken side to side, one 60 fps frame a step (visual, local)
	-- (a prop - no Humanoid, no root joint - gets the flash and the sparks only)
	local root = victim:FindFirstChild("HumanoidRootPart")
	local joint: Motor6D? = nil
	if root then
		local j = root:FindFirstChild("RootJoint") or root:FindFirstChild("Root")
		joint = if j and j:IsA("Motor6D") then j else nil
	end
	if not joint then
		local lower = victim:FindFirstChild("LowerTorso")
		local j = lower and lower:FindFirstChild("Root")
		joint = if j and j:IsA("Motor6D") then j else nil
	end
	local shake = VfxVictim.tremor(o.hitstop or 6, p)
	local c0: CFrame? = nil
	if joint and #shake > 0 and not tremors[joint] then
		tremors[joint] = true
		c0 = joint.C0
	end
	local side = hit.RightVector
	local frame, acc, drawn = 0, 0, false
	local conn: RBXScriptConnection
	conn = RunService.RenderStepped:Connect(function(dt: number)
		-- (the first frame DRAWN is frame 1 - the solid white one - whatever came before it: counted, the hit's own
		-- hitch (this call, the burst, a first use that loads the stage) skipped it - Studio 2026-11-20, the first
		-- flash drawn was 0.75 transparent, tests/playtest/vfx_sequence_victim)
		if drawn then
			acc += dt
		end
		drawn = true
		local f = math.floor(acc * 60 + 1e-6)
		if f == frame and frame > 0 then
			return
		end
		frame = math.max(f, 1)
		local k = flash[frame]
		h.FillTransparency = if k then k else 1
		h.OutlineTransparency = if k then k * 0.5 else 1
		h.Enabled = held and k ~= nil
		if joint and c0 then
			local off = shake[frame]
			if off then
				local local_ = (root :: BasePart).CFrame:VectorToObjectSpace(side * off)
				joint.C0 = c0 * CFrame.new(local_)
			else
				joint.C0 = c0
			end
		end
		if frame > #flash and frame > #shake then
			conn:Disconnect()
			if slots then
				slots:release(h)
			end
			h:Destroy()
			if joint and c0 then
				joint.C0 = c0
				tremors[joint] = nil
			end
			task.delay(0.4, function()
				anchor:Destroy()
			end)
		end
	end)
	return true
end

function VfxImpact.hit(result: RaycastResult): boolean
	local inst = result.Instance
	local color: Color3? = nil
	if inst and inst:IsA("Terrain") then
		local ok, c = pcall((inst :: Terrain).GetMaterialColor, inst :: Terrain, result.Material)
		color = if ok then c else nil
	elseif inst and inst:IsA("BasePart") then
		color = (inst :: BasePart).Color
	end
	return VfxImpact.play(VfxImpact.kindOf(result.Material), result.Position, result.Normal, color)
end

return VfxImpact

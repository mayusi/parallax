-- VfxValidate.luau — pure checks for VFX presets (src/shared/VfxPresets/*.json). No game APIs: runs in Lune + Roblox.
-- Each issue says what is wrong and how to fix it. Caps: rate ≤400 (warn >100 for mobile), lifetime ≤20s,
-- flipbook ≤30 FPS, ≤20 keypoints per sequence, particle budget ≤600 per preset (warn >300).
local VfxValidate3 = require("./VfxValidate3")

local VfxValidate = {}

export type Issue = { path: string, message: string, severity: string }

local KINDS = {
	particles = true,
	flash = true,
	ring = true,
	light = true,
	debris = true,
	trail = true,
	sound = true, -- plays a kit sound by name (Assets registry) at the effect
	shake = true, -- camera shake for nearby players (client)
	screen = true, -- full-screen colour flash / grade (client)
	beam = true, -- laser / lightning between two points
	mesh = true, -- a 3D effect mesh (kit-built dome/ring/crescent/... or a primitive) animated over its time
	afterimage = true, -- fading coloured copies of the character the preset is attached to
	grade = true, -- screen colour grade / blur / FOV punch over time (client; "owner" = only that player's screen)
}
local KIND_LIST =
	"particles | flash | ring | light | debris | trail | sound | shake | screen | beam | mesh | afterimage | grade"
local PRIMITIVES = { Ball = true, Block = true, Cylinder = true, Wedge = true }
local MESH_MATERIALS = { Neon = true, ForceField = true, Glass = true, SmoothPlastic = true }
local LAYOUTS = { Grid2x2 = 2, Grid4x4 = 4, Grid8x8 = 8 }
local FLIP_MODES = { Loop = true, OneShot = true, PingPong = true, Random = true }
local SHAPES = { Ball = true, Block = true, Cylinder = true }
local DIRECTIONS = { Top = true, Bottom = true, Left = true, Right = true, Front = true, Back = true }
local ORIENTATIONS =
	{ FacingCamera = true, FacingCameraWorldUp = true, VelocityParallel = true, VelocityPerpendicular = true }
local MATERIALS = {
	Slate = true,
	Concrete = true,
	Rock = true,
	Metal = true,
	Wood = true,
	Plastic = true,
	Neon = true,
	Glass = true,
	Sand = true,
	Ground = true,
}

local BUDGET_MAX = 600
local BUDGET_MOBILE = 300

local function isNum(v: any): boolean
	return type(v) == "number" and v == v
end

local function isRange(v: any): boolean
	return isNum(v) or (type(v) == "table" and #v == 2 and isNum(v[1]) and isNum(v[2]) and v[1] <= v[2])
end

local function rangeMax(v: any): number
	return if isNum(v) then v else v[2]
end

local function isColor(v: any): boolean
	if type(v) ~= "table" or #v ~= 3 then
		return false
	end
	for _, c in v do
		if not isNum(c) or c < 0 or c > 255 then
			return false
		end
	end
	return true
end

-- meshes: the effect-mesh registry (assets/effects/_meshes.json); nil = only primitives are known
function VfxValidate.preset(name: string, preset: any, textures: any, meshes: any?): { Issue }
	if type(preset) == "table" and preset.version == 3 then -- the layer-stack format (VfxStage)
		return VfxValidate3.preset(name, preset, textures)
	end
	local issues: { Issue } = {}
	local function err(path: string, message: string)
		table.insert(issues, { path = `{name}.{path}`, message = message, severity = "error" })
	end
	local function warn(path: string, message: string)
		table.insert(issues, { path = `{name}.{path}`, message = message, severity = "warn" })
	end

	-- sequence: number | { {t, v} | {t, v, envelope} } with t from 0 to 1, increasing, ≤20 keypoints
	local function sequence(path: string, v: any, lo: number?, hi: number?, color: boolean?)
		if v == nil then
			return
		end
		local function value(x: any, at: string)
			if color then
				if not isColor(x) then
					err(at, "color must be [r, g, b] with 0-255 values")
				end
			elseif not isNum(x) then
				err(at, "must be a number")
			elseif (lo and x < lo) or (hi and x > hi) then
				err(at, `value {x} outside {lo or "-inf"}..{hi or "inf"}`)
			end
		end
		if isNum(v) or (color and isColor(v)) then
			value(v, path)
			return
		end
		if type(v) ~= "table" or #v < 2 then
			err(path, "use a constant or a list of [time, value] keypoints (at least 2: time 0 and time 1)")
			return
		end
		if #v > 20 then
			err(path, `{#v} keypoints — Roblox allows at most 20`)
		end
		local last = -1
		for i, kp in v do
			if type(kp) ~= "table" or not isNum(kp[1]) then
				err(`{path}[{i}]`, "keypoint must be [time, value]")
				continue
			end
			if kp[1] <= last then
				err(`{path}[{i}]`, "keypoint times must increase")
			end
			last = kp[1]
			value(kp[2], `{path}[{i}]`)
		end
		local first = v[1]
		local final = v[#v]
		if type(first) == "table" and first[1] ~= 0 then
			err(path, "first keypoint time must be 0")
		end
		if type(final) == "table" and final[1] ~= 1 then
			err(path, "last keypoint time must be 1")
		end
	end

	local function fromTo(path: string, v: any, lo: number, hi: number?)
		if type(v) ~= "table" or #v ~= 2 or not isNum(v[1]) or not isNum(v[2]) then
			err(path, "must be [from, to]")
		elseif v[1] < lo or v[2] < lo or (hi and (v[1] > hi or v[2] > hi)) then
			err(path, `values must be within {lo}..{hi or "inf"}`)
		end
	end

	if type(preset) ~= "table" then
		err("", "preset must be a JSON object")
		return issues
	end
	local mode = preset.mode or "burst"
	if mode ~= "burst" and mode ~= "attach" then
		err("mode", 'must be "burst" (plays once at a point) or "attach" (runs on a part until stopped)')
	end
	local duration = preset.duration
	if mode == "burst" and (not isNum(duration) or duration <= 0 or duration > 20) then
		err("duration", "burst presets need duration in seconds, 0 < duration ≤ 20")
		duration = 20
	end
	-- "reach": who a broadcast of this effect is sent to - studs at scale 1, or "all" (VfxNet.audience; the same
	-- rule as a version 3 preset's: a reach that is no reach was read as none, and the mistake was never said)
	if preset.reach ~= nil and preset.reach ~= "all" and not (isNum(preset.reach) and preset.reach > 0) then
		err(
			"reach",
			'reach: how far from the effect (or its target) players are sent it, in studs at scale 1 - or "all"'
		)
	end
	if type(preset.elements) ~= "table" or #preset.elements == 0 then
		err("elements", "needs at least one element")
		return issues
	end

	local budget = 0
	for i, el in preset.elements do
		local p = `elements[{i}]`
		if type(el) ~= "table" or not KINDS[el.kind] then
			err(p .. ".kind", "kind must be " .. KIND_LIST)
			continue
		end
		local kind = el.kind
		if kind == "particles" then
			local off = el.offset
			if
				off ~= nil
				and not (type(off) == "table" and #off == 3 and isNum(off[1]) and isNum(off[2]) and isNum(off[3]))
			then
				err(p .. ".offset", "offset must be [x, y, z] (studs from the effect origin)")
			end
			if el.area ~= nil then
				local a = el.area
				local shapes = { Box = true, Sphere = true, Cylinder = true }
				if type(a) ~= "table" or not shapes[a.shape or "Box"] then
					err(p .. ".area", 'area must be { "shape": "Box" | "Sphere" | "Cylinder", "size": [x, y, z] }')
				elseif
					not (
						type(a.size) == "table"
						and #a.size == 3
						and isNum(a.size[1])
						and a.size[1] > 0
						and a.size[1] <= 2048
					)
				then
					err(p .. ".area.size", "area size must be [x, y, z] studs, each 0..2048")
				end
			end
			local tex = textures and textures[el.texture]
			if type(tex) ~= "table" then
				err(
					p .. ".texture",
					`unknown texture "{tostring(el.texture)}" — add it to src/shared/VfxTextures.json`
				)
			end
			if not isRange(el.lifetime) or rangeMax(el.lifetime) <= 0 or rangeMax(el.lifetime) > 20 then
				err(p .. ".lifetime", "lifetime must be a number or [min, max], 0 < max ≤ 20")
			end
			local rate = el.rate or 0
			local burst = el.burst or 0
			if not isNum(rate) or rate < 0 or rate > 400 then
				err(p .. ".rate", "rate must be 0..400")
			elseif rate > 100 then
				warn(p .. ".rate", "rate > 100 drops frames on mobile")
			end
			if not isNum(burst) or burst < 0 or burst > 200 or burst % 1 ~= 0 then
				err(p .. ".burst", "burst must be a whole number 0..200")
			end
			if isNum(rate) and isNum(burst) and rate <= 0 and burst <= 0 then
				err(p, "emits nothing — set rate > 0 or burst > 0")
			end
			if mode == "attach" and isNum(rate) and rate <= 0 then
				err(p .. ".rate", "attach presets run until stopped, so particles need rate > 0")
			end
			if isNum(rate) and isNum(burst) and isRange(el.lifetime) then
				local emitFor = el.emit or (if mode == "attach" then rangeMax(el.lifetime) else 0.2)
				budget += burst + rate * (if mode == "attach" then rangeMax(el.lifetime) else emitFor)
			end
			if el.speed ~= nil and (not isRange(el.speed) or (isNum(el.speed) and el.speed < 0)) then
				err(p .. ".speed", "speed must be a number or [min, max] ≥ 0")
			end
			if el.spread ~= nil and (not isNum(el.spread) or el.spread < 0 or el.spread > 180) then
				err(p .. ".spread", "spread is a cone angle 0..180")
			end
			sequence(p .. ".size", el.size, 0, 200)
			sequence(p .. ".transparency", el.transparency, 0, 1)
			sequence(p .. ".color", el.color, nil, nil, true)
			for _, key in { "lightEmission", "lightInfluence" } do
				local v = el[key]
				if v ~= nil and (not isNum(v) or v < 0 or v > 1) then
					err(`{p}.{key}`, "must be 0..1")
				end
			end
			if el.direction ~= nil and not DIRECTIONS[el.direction] then
				err(p .. ".direction", "direction must be Top | Bottom | Left | Right | Front | Back")
			end
			if el.orientation ~= nil and not ORIENTATIONS[el.orientation] then
				err(
					p .. ".orientation",
					"orientation must be FacingCamera | FacingCameraWorldUp | VelocityParallel | VelocityPerpendicular"
				)
			end
			local fb = el.flipbook
			if fb ~= nil then
				local grid = LAYOUTS[fb.layout]
				if not grid then
					err(p .. ".flipbook.layout", "layout must be Grid2x2 | Grid4x4 | Grid8x8")
				elseif type(tex) == "table" and tex.grid ~= grid then
					err(p .. ".flipbook.layout", `texture "{el.texture}" has grid {tex.grid}, layout needs {grid}`)
				end
				if not isNum(fb.fps) or fb.fps <= 0 or fb.fps > 30 then
					err(p .. ".flipbook.fps", "flipbook fps must be 1..30")
				end
				if fb.mode ~= nil and not FLIP_MODES[fb.mode] then
					err(p .. ".flipbook.mode", "mode must be Loop | OneShot | PingPong | Random")
				end
			elseif type(tex) == "table" and tex.grid and tex.grid > 1 then
				warn(
					p .. ".flipbook",
					`texture "{el.texture}" is a {tex.grid}x{tex.grid} flipbook — add "flipbook" or every frame shows at once`
				)
			end
		elseif kind == "flash" then
			if el.shape ~= nil and not SHAPES[el.shape] then
				err(p .. ".shape", "shape must be Ball | Block | Cylinder")
			end
			fromTo(p .. ".size", el.size, 0)
			fromTo(p .. ".transparency", el.transparency or { 0, 1 }, 0, 1)
		elseif kind == "ring" then
			fromTo(p .. ".size", el.size, 0)
			fromTo(p .. ".transparency", el.transparency or { 0, 1 }, 0, 1)
			if not isNum(el.thickness) or el.thickness <= 0 then
				err(p .. ".thickness", "ring needs thickness > 0")
			end
		elseif kind == "light" then
			if not isNum(el.range) or el.range <= 0 or el.range > 60 then
				err(p .. ".range", "PointLight range must be 0 < range ≤ 60")
			end
			fromTo(p .. ".brightness", el.brightness, 0)
		elseif kind == "debris" then
			if not isNum(el.count) or el.count < 1 or el.count > 20 or el.count % 1 ~= 0 then
				err(p .. ".count", "debris count must be a whole number 1..20")
			end
			if not isRange(el.size) or not isRange(el.speed) then
				err(p, "debris needs size and speed as [min, max]")
			end
			if el.material ~= nil and not MATERIALS[el.material] then
				err(
					p .. ".material",
					"material must be a common Enum.Material name (Slate, Concrete, Rock, Metal, ...)"
				)
			end
		elseif kind == "trail" then
			if mode ~= "attach" then
				err(p, "trails only work in attach presets (they need a moving part)")
			end
			if not isNum(el.lifetime) or el.lifetime <= 0 or el.lifetime > 20 then
				err(p .. ".lifetime", "trail lifetime must be 0 < lifetime ≤ 20")
			end
			sequence(p .. ".transparency", el.transparency, 0, 1)
			sequence(p .. ".color", el.color, nil, nil, true)
		elseif kind == "sound" then
			if type(el.name) ~= "string" or not string.match(el.name, "^[%w_]+$") then
				err(
					p .. ".name",
					'sound needs the name of a kit sound (assets/sounds/<name>.json), e.g. "explosion_big"'
				)
			end
			if el.volume ~= nil and (not isNum(el.volume) or el.volume < 0 or el.volume > 10) then
				err(p .. ".volume", "volume must be 0..10")
			end
			if el.pitch ~= nil and (not isRange(el.pitch) or rangeMax(el.pitch) <= 0 or rangeMax(el.pitch) > 4) then
				err(p .. ".pitch", "pitch must be a number or [min, max] within 0..4")
			end
		elseif kind == "shake" then
			if not isNum(el.intensity) or el.intensity <= 0 or el.intensity > 3 then
				err(p .. ".intensity", "shake intensity must be 0 < intensity ≤ 3 (1 = strong hit, 3 = nuke)")
			end
			if el.radius ~= nil and (not isNum(el.radius) or el.radius <= 0 or el.radius > 1000) then
				err(p .. ".radius", "radius (studs; players farther feel nothing) must be 0..1000")
			end
		elseif kind == "screen" then
			if el.flash ~= nil and (not isNum(el.flash) or el.flash < 0 or el.flash > 1) then
				err(p .. ".flash", "flash (brightness boost) must be 0..1")
			end
			if el.radius ~= nil and (not isNum(el.radius) or el.radius <= 0 or el.radius > 1000) then
				err(p .. ".radius", "radius must be 0..1000 studs")
			end
		elseif kind == "mesh" then
			local m = el.mesh
			if type(m) ~= "string" or not (PRIMITIVES[m] or (meshes and type(meshes[m]) == "table")) then
				err(
					p .. ".mesh",
					`mesh must be Ball | Block | Cylinder | Wedge or a kit effect mesh (assets/effects/meshes/<name>.json), got "{tostring(
						m
					)}"`
				)
			end
			if el.material ~= nil and not MESH_MATERIALS[el.material] then
				err(p .. ".material", "material must be Neon | ForceField | Glass | SmoothPlastic")
			end
			if el.texture ~= nil and type(textures and textures[el.texture]) ~= "table" then
				err(p .. ".texture", `unknown texture "{tostring(el.texture)}"`)
			end
			-- scale: number | [[t, s] | [t, [x, y, z]], ...] — multiplies the mesh's own size (primitives: studs)
			local function scaleValue(v: any): boolean
				return (isNum(v) and v >= 0 and v <= 2000)
					or (type(v) == "table" and #v == 3 and isNum(v[1]) and isNum(v[2]) and isNum(v[3]))
			end
			if el.scale == nil or (not scaleValue(el.scale) and type(el.scale) ~= "table") then
				err(p .. ".scale", "scale must be a number or [[0, s], ..., [1, s]] (s = number or [x, y, z])")
			elseif type(el.scale) == "table" and not scaleValue(el.scale) then
				local last = -1
				for k, kp in el.scale do
					if type(kp) ~= "table" or not isNum(kp[1]) or not scaleValue(kp[2]) or kp[1] <= last then
						err(`{p}.scale[{k}]`, "keypoint must be [time, scale] with increasing times 0..1")
						break
					end
					last = kp[1]
				end
				local first, final = el.scale[1], el.scale[#el.scale]
				if
					#el.scale < 2
					or type(first) ~= "table"
					or first[1] ~= 0
					or type(final) ~= "table"
					or final[1] ~= 1
				then
					err(p .. ".scale", "keypoints must start at time 0 and end at time 1")
				end
			end
			sequence(p .. ".transparency", el.transparency, 0, 1)
			sequence(p .. ".color", el.color, nil, nil, true)
			if mode == "burst" and (not isNum(el.time) or el.time <= 0) then
				err(p .. ".time", "mesh needs time (seconds it lives; scale/colour/transparency run over it)")
			end
			for _, key in { "spin", "offset", "rotation" } do
				local v = el[key]
				if
					v ~= nil and not (type(v) == "table" and #v == 3 and isNum(v[1]) and isNum(v[2]) and isNum(v[3]))
				then
					err(`{p}.{key}`, `{key} must be [x, y, z]`)
				end
			end
		elseif kind == "afterimage" then
			if mode ~= "attach" then
				err(p, "afterimages need an attach preset (they copy the character the preset is attached to)")
			end
			if not isNum(el.interval) or el.interval < 0.03 or el.interval > 2 then
				err(p .. ".interval", "interval (seconds between copies) must be 0.03..2")
			end
			if not isNum(el.lifetime) or el.lifetime <= 0 or el.lifetime > 3 then
				err(p .. ".lifetime", "lifetime (seconds each copy lasts) must be 0 < lifetime ≤ 3")
			elseif isNum(el.interval) and el.interval > 0 and el.lifetime / el.interval > 40 then
				err(p, "more than 40 copies alive at once — raise interval or lower lifetime")
			end
			if el.material ~= nil and not MESH_MATERIALS[el.material] then
				err(p .. ".material", "material must be Neon | ForceField | Glass | SmoothPlastic")
			end
			if el.cycle ~= nil and (not isNum(el.cycle) or el.cycle < 0.1 or el.cycle > 10) then
				err(p .. ".cycle", "cycle (seconds to run through the colour sequence across copies) must be 0.1..10")
			end
			sequence(p .. ".color", el.color, nil, nil, true)
			sequence(p .. ".transparency", el.transparency, 0, 1)
		elseif kind == "grade" then
			if el.tint ~= nil and not isColor(el.tint) then
				err(p .. ".tint", "tint must be [r, g, b] 0-255")
			end
			for _, key in { "saturation", "contrast", "brightness" } do
				local v = el[key]
				if v ~= nil and (not isNum(v) or v < -1 or v > 1) then
					err(`{p}.{key}`, "must be -1..1")
				end
			end
			if el.blur ~= nil and (not isNum(el.blur) or el.blur < 0 or el.blur > 56) then
				err(p .. ".blur", "blur size must be 0..56")
			end
			if el.fov ~= nil and (not isNum(el.fov) or el.fov < -40 or el.fov > 40) then
				err(p .. ".fov", "fov (degrees added to the camera) must be -40..40")
			end
			for _, key in { "fadeIn", "fadeOut" } do
				local v = el[key]
				if v ~= nil and (not isNum(v) or v < 0 or v > 5) then
					err(`{p}.{key}`, "must be 0..5 seconds")
				end
			end
			if el.who ~= nil and el.who ~= "owner" and el.who ~= "all" and el.who ~= "near" then
				err(p .. ".who", 'who must be "owner" (the attached player only), "near" (within radius) or "all"')
			end
			if mode == "burst" and (not isNum(el.time) or el.time <= 0) then
				err(p .. ".time", "burst grades need time (seconds held between fadeIn and fadeOut)")
			end
			if mode == "burst" and el.who == "owner" then
				err(p .. ".who", 'a burst effect has no owner (it plays at a point) — use "near" (+ radius) or "all"')
			end
			if el.radius ~= nil and (not isNum(el.radius) or el.radius <= 0 or el.radius > 1000) then
				err(p .. ".radius", "radius must be 0..1000 studs")
			end
		elseif kind == "beam" then
			local function vec3(v: any): boolean
				return type(v) == "table" and #v == 3 and isNum(v[1]) and isNum(v[2]) and isNum(v[3])
			end
			if el.from ~= nil and not vec3(el.from) then
				err(p .. ".from", "from must be [x, y, z] (offset from the effect origin, studs)")
			end
			if el.to ~= "target" and not vec3(el.to) then
				err(p .. ".to", 'to must be [x, y, z] or "target" (the target passed to Vfx.play/broadcast)')
			end
			fromTo(p .. ".width", el.width or { 1, 1 }, 0, 50)
			if el.texture ~= nil and type(textures and textures[el.texture]) ~= "table" then
				err(p .. ".texture", `unknown texture "{tostring(el.texture)}"`)
			end
			if el.segments ~= nil and (not isNum(el.segments) or el.segments < 1 or el.segments > 24) then
				err(p .. ".segments", "segments must be 1..24 (lightning zig-zags)")
			end
			sequence(p .. ".color", el.color, nil, nil, true)
			sequence(p .. ".transparency", el.transparency, 0, 1)
		end
		if el.delay ~= nil and (not isNum(el.delay) or el.delay < 0 or (mode == "burst" and el.delay >= duration)) then
			err(p .. ".delay", "delay must be ≥ 0 and less than the preset duration (it starts this element later)")
		end
		local sequenced = { particles = true, trail = true, beam = true, mesh = true, afterimage = true }
		if el.color ~= nil and not sequenced[kind] and not isColor(el.color) then
			err(p .. ".color", "color must be [r, g, b] with 0-255 values")
		end
		if el.time ~= nil and (not isNum(el.time) or el.time <= 0 or (mode == "burst" and el.time > duration)) then
			err(p .. ".time", "time must be > 0 and ≤ the preset duration")
		end
	end

	if budget > BUDGET_MAX then
		err("elements", `~{math.floor(budget)} particles alive — budget is {BUDGET_MAX}; lower burst/rate/lifetime`)
	elseif budget > BUDGET_MOBILE then
		warn("elements", `~{math.floor(budget)} particles alive — over the {BUDGET_MOBILE} mobile budget`)
	end
	return issues
end

function VfxValidate.errors(issues: { Issue }): { Issue }
	local out = {}
	for _, issue in issues do
		if issue.severity == "error" then
			table.insert(out, issue)
		end
	end
	return out
end

return VfxValidate

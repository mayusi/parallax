-- VfxValidate3.luau — pure checks for version-3 VFX presets (the layer-stack format VfxStage plays). No game APIs:
-- runs in Lune (kit vfx / kit verify) and in Roblox (presets are re-checked when the game loads them).
-- Every issue says what is wrong and how to fix it.
local VfxValidate3 = {}

export type Issue = { path: string, message: string, severity: string }

local KINDS = {
	sprite = true,
	beam = true,
	mesh = true,
	decal = true,
	light = true,
	debris = true,
	screen = true,
	impact = true,
	shake = true,
	fov = true,
	sound = true,
	glow = true,
	trail = true,
	highlight = true,
	world = true,
	crater = true,
	lens = true,
	swarm = true,
}
local KIND_LIST =
	"sprite | beam | mesh | decal | light | debris | screen | impact | shake | fov | sound | glow | trail | highlight | world | crater | lens | swarm"
local MESH_SHAPES = {
	ring = true,
	disc = true,
	tube = true,
	crown = true,
	cone = true,
	torus = true,
	sphere = true,
	dome = true,
	spiral = true,
	arc = true,
	flame = true,
	tongue = true,
	bolt = true,
	spikes = true,
	cards = true,
	corona = true,
	rock = true,
	seq = true,
	Ball = true,
	Block = true,
	Cylinder = true,
}
-- the keys a mesh / debris layer is READ with (player + engine): anything else is silently ignored at runtime, so it
-- is an error here ("rot" instead of "rotate" once cost a black hole its whole tilt)
local VfxBounce = require("./VfxBounce")
local VfxBudget = require("./VfxBudget")
local COMMON_KEYS = {
	name = true,
	kind = true,
	at = true,
	life = true,
	about = true,
	frames = true,
	beat = true,
	tier = true, -- the lowest detail level the layer plays at (VfxBudget: Low | Medium | High)
	tierCount = true, -- the share of its count / rate each level keeps: { Low = 0.4, Medium = 0.7 }
	critical = true, -- a cue that must not be lost: its mesh may use the budget's reserve (VfxBudget.admit)
} -- frames: false keeps a layer out of impact frames; beat: the scene beat a layer builds (an authoring tag the kit's scope gate reads - the runtime never does)
local MESH_KEYS = {
	forced = true,
	point = true,
	aim = true,
	rotate = true,
	shape = true,
	params = true,
	texture = true,
	material = true,
	color = true,
	spin = true,
	reflectance = true,
	roughness = true,
	scale = true,
	move = true,
	smooth = true,
	transparency = true,
	uvScroll = true,
	wobble = true,
	flipbook = true,
	step = true,
	erode = true,
	surface = true,
	pivot = true,
	glow = true,
	toon = true,
	outline = true,
	outlineWidth = true,
	sweep = true,
}
local DEBRIS_KEYS = {
	pieces = true,
	rest = true,
	point = true,
	aim = true,
	rotate = true,
	count = true,
	size = true,
	speed = true,
	spread = true,
	gravity = true,
	material = true,
	color = true,
	shape = true,
	seed = true,
	cuts = true,
	jag = true,
	spike = true,
	flat = true,
	toon = true,
	outline = true,
	floor = true,
}
local ALIASES =
	{ rot = "rotate", rotation = "rotate", position = "point", pos = "point", lifetime = "life", tex = "texture" }
local MESH_MATERIALS = { Neon = true, ForceField = true, Glass = true, SmoothPlastic = true }
local MATERIALS = { -- every Enum.Material a part can take (Air / Water are terrain-only)
	Plastic = true,
	SmoothPlastic = true,
	Neon = true,
	Wood = true,
	WoodPlanks = true,
	Marble = true,
	Basalt = true,
	Slate = true,
	CrackedLava = true,
	Concrete = true,
	Limestone = true,
	Granite = true,
	Pavement = true,
	Brick = true,
	Pebble = true,
	Cobblestone = true,
	Rock = true,
	Sandstone = true,
	CorrodedMetal = true,
	DiamondPlate = true,
	Foil = true,
	Metal = true,
	Grass = true,
	LeafyGrass = true,
	Sand = true,
	Fabric = true,
	Snow = true,
	Mud = true,
	Ground = true,
	Asphalt = true,
	Salt = true,
	Ice = true,
	Glacier = true,
	Glass = true,
	ForceField = true,
	Cardboard = true,
	Carpet = true,
	CeramicTiles = true,
	ClayRoofTiles = true,
	RoofShingles = true,
	Leather = true,
	Plaster = true,
	Rubber = true,
}
local ORIENTATIONS =
	{ FacingCamera = true, FacingCameraWorldUp = true, VelocityParallel = true, VelocityPerpendicular = true }
local DIRECTIONS = { Top = true, Bottom = true, Left = true, Right = true, Front = true, Back = true }
local SHAPES = { Box = true, Sphere = true, Cylinder = true, Disc = true }
local IN_OUT = { Outward = true, Inward = true, InAndOut = true }
local FLIP_MODES = { Loop = true, OneShot = true, PingPong = true, Random = true }
local GRIDS = { ["2x2"] = 2, ["4x4"] = 4, ["8x8"] = 8 }
local PARTICLES_ERROR, PARTICLES_WARN = 1500, 800

local function isNum(v: any): boolean
	return type(v) == "number" and v == v
end

local function isVec(v: any): boolean
	return type(v) == "table" and #v == 3 and isNum(v[1]) and isNum(v[2]) and isNum(v[3])
end

local function rangeMax(v: any): number
	if isNum(v) then
		return v
	end
	if type(v) == "table" and isNum(v[2]) then
		return v[2]
	end
	return 0
end

function VfxValidate3.preset(name: string, preset: any, textures: any): { Issue }
	local issues: { Issue } = {}
	local function err(path: string, message: string)
		table.insert(issues, { path = `{name}.{path}`, message = message, severity = "error" })
	end
	local function warn(path: string, message: string)
		table.insert(issues, { path = `{name}.{path}`, message = message, severity = "warn" })
	end
	local function knownKeys(p: string, el: any, keys: { [string]: boolean })
		for k in el do
			if type(k) == "string" and not COMMON_KEYS[k] and not keys[k] and k:sub(1, 1) ~= "_" then
				local hint = if ALIASES[k] then ` — did you mean "{ALIASES[k]}"?` else ""
				err(`{p}.{k}`, `"{k}" is not read by a {tostring(el.kind)} layer (it would be silently ignored){hint}`)
			end
		end
	end
	if type(preset) ~= "table" then
		err("", "preset must be a JSON object")
		return issues
	end
	local palette = if type(preset.palette) == "table" then preset.palette else {}
	local points = if type(preset.points) == "table" then preset.points else {}
	for k, c in palette do
		if not (type(c) == "table" and #c == 3 and isNum(c[1]) and isNum(c[2]) and isNum(c[3])) then
			err(`palette.{k}`, "a palette colour is [r, g, b] with 0-255 values")
		end
	end
	for k, p in points do
		if not isVec(p) then
			err(`points.{k}`, "a point is [x, y, z] studs in the effect's space (x right, y up, -z forward)")
		end
	end
	local mode = preset.mode or "burst"
	if mode ~= "burst" and mode ~= "attach" then
		err("mode", 'mode: "burst" (plays once at a point) | "attach" (rides a part until stopped: Vfx.attach)')
	end
	local duration = preset.duration
	if mode == "attach" then
		if duration ~= nil and (not isNum(duration) or duration <= 0 or duration > 300) then
			err("duration", "an attach preset's duration (optional: it runs until stopped) must be 0 < duration <= 300")
		end
		duration = if isNum(duration) then duration else 1e9
	elseif not isNum(duration) or duration <= 0 or duration > 30 then
		err("duration", "duration (seconds until everything is cleaned up) must be 0 < duration <= 30")
		duration = 30
	end
	-- "reach": who a broadcast of this effect is sent to - studs at scale 1, or "all" (VfxNet.audience)
	if preset.reach ~= nil and preset.reach ~= "all" and not (isNum(preset.reach) and preset.reach > 0) then
		err(
			"reach",
			'reach: how far from the effect (or its target) players are sent it, in studs at scale 1 - or "all"'
		)
	end
	if preset.hits ~= nil then -- the moments something lands (the metrics gate allows an intensity peak at each)
		if type(preset.hits) ~= "table" then
			err("hits", "hits is a list of seconds, e.g. [2.6, 2.88]")
		else
			for i, h in preset.hits do
				if not isNum(h) or h < 0 or h >= duration then
					err(`hits[{i}]`, "a hit is a time in seconds, 0 <= t < duration")
				end
			end
		end
	end
	if preset.timewarp ~= nil then -- the clock's speed over the effect's time: [[t, rate], ...]
		local w = preset.timewarp
		if type(w) ~= "table" or #w < 2 then
			err("timewarp", "timewarp: [[t, rate], ...] — at least two keys, t rising, rate 0.05..1 (bullet time)")
		else
			local last = -1
			for i, kv in w do
				if type(kv) ~= "table" or not isNum(kv[1]) or not isNum(kv[2]) then
					err(`timewarp[{i}]`, "each key is [t, rate]")
				else
					if kv[1] <= last or kv[1] < 0 or kv[1] > duration then
						err(`timewarp[{i}]`, "t must rise and stay inside 0..duration")
					end
					if kv[2] < 0.05 or kv[2] > 1 then
						err(`timewarp[{i}]`, "rate 0.05..1 (1 = real time)")
					end
					last = kv[1]
				end
			end
		end
	end
	if preset.hitstop ~= nil then
		if type(preset.hitstop) ~= "table" then
			err(
				"hitstop",
				'hitstop is a list of { "at": seconds, "hold": real seconds 0.02..1.8, "span": preset seconds the hold plays through }'
			)
		else
			for i, h in preset.hitstop do
				if type(h) ~= "table" then
					err(`hitstop[{i}]`, 'each hit-stop is { "at": seconds, "hold": real seconds }')
					continue
				end
				if not isNum(h.at) or h.at <= 0 or h.at >= duration then
					err(`hitstop[{i}].at`, "at (seconds on the effect clock) must be 0 < at < duration")
				end
				if h.hold ~= nil and (not isNum(h.hold) or h.hold < 0.02 or h.hold > 1.8) then -- up to 1.8 s: a lingering, dreadful ultimate hit
					err(`hitstop[{i}].hold`, "hold (real seconds the clock stops) must be 0.02..1.8")
				end
				if h.span ~= nil and (not isNum(h.span) or h.span < 0.02 or (isNum(h.hold) and h.span > h.hold)) then
					err(
						`hitstop[{i}].span`,
						"span: the preset seconds of impact frames the hold plays through, 0.02..hold (span < hold = the frames linger in slow motion)"
					)
				end
			end
		end
	end
	if type(preset.layers) ~= "table" or #preset.layers == 0 then
		err("layers", "needs at least one layer")
		return issues
	end
	if #preset.layers > 150 then
		err("layers", `{#preset.layers} layers — keep an effect under 150 (each emitter is a draw call)`)
	end

	local function color(path: string, c: any)
		if type(c) == "string" then
			if palette[c] == nil then
				err(path, `unknown palette colour "{c}" (palette: add it, or use [r, g, b])`)
			end
		elseif not (type(c) == "table" and #c == 3 and isNum(c[1]) and isNum(c[2]) and isNum(c[3])) then
			err(path, "a colour is [r, g, b] (0-255) or a palette name")
		else
			for _, v in c do
				if v < 0 or v > 255 then
					err(path, "colour values are 0-255")
					break
				end
			end
		end
	end
	-- a constant or [[u, v], ...] with u from 0 to 1, increasing
	local function seq(path: string, v: any, check: (p: string, x: any) -> (), maxKeys: number?)
		if v == nil then
			return
		end
		if type(v) ~= "table" or type(v[1]) ~= "table" then
			check(path, v)
			return
		end
		if #v < 2 then
			err(path, "a sequence needs at least two keys: [[0, a], [1, b]]")
			return
		end
		if maxKeys and #v > maxKeys then
			err(path, `{#v} keys — Roblox sequences hold at most {maxKeys}`)
		end
		local last = -1
		for i, kp in v do
			if type(kp) ~= "table" or not isNum(kp[1]) then
				err(`{path}[{i}]`, "a key is [u, value] with u 0..1")
				continue
			end
			if kp[1] <= last then
				err(`{path}[{i}]`, "key times must increase")
			end
			last = kp[1]
			check(`{path}[{i}]`, kp[2])
		end
		if v[1][1] ~= 0 or v[#v][1] ~= 1 then
			err(path, "sequence keys must start at 0 and end at 1 (the layer's life)")
		end
	end
	local function num(lo: number?, hi: number?): (p: string, x: any) -> ()
		return function(p: string, x: any)
			if not isNum(x) then
				err(p, "must be a number")
			elseif (lo and x < lo) or (hi and x > hi) then
				err(p, `{x} is outside {lo or "-inf"}..{hi or "inf"}`)
			end
		end
	end
	local function numOrVec(lo: number, hi: number): (p: string, x: any) -> ()
		return function(p: string, x: any)
			if isNum(x) then
				num(lo, hi)(p, x)
			elseif isVec(x) then
				for _, c in x do
					num(lo, hi)(p, c)
				end
			else
				err(p, "must be a number or [x, y, z]")
			end
		end
	end
	local function range(path: string, v: any, lo: number, hi: number)
		if v == nil then
			return
		end
		if isNum(v) then
			num(lo, hi)(path, v)
		elseif type(v) == "table" and #v == 2 and isNum(v[1]) and isNum(v[2]) and v[1] <= v[2] then
			num(lo, hi)(path, v[1])
			num(lo, hi)(path, v[2])
		else
			err(path, "must be a number or [min, max] (min <= max)")
		end
	end
	-- [a, b] of numbers within lo..hi (optional field)
	local function pair(path: string, v: any, lo: number, hi: number)
		if v == nil then
			return
		end
		if type(v) ~= "table" or #v ~= 2 or not isNum(v[1]) or not isNum(v[2]) then
			err(path, "must be [a, b] (two numbers)")
			return
		end
		num(lo, hi)(path, v[1])
		num(lo, hi)(path, v[2])
	end
	local function point(path: string, v: any, required: boolean?)
		if v == nil then
			if required then
				err(path, 'missing (a point: [x, y, z], a name from points, "target" or "@anchor")')
			end
			return
		end
		if isVec(v) then
			return
		end
		if type(v) == "string" then
			if v == "target" or points[v] ~= nil then
				return
			end
			if string.sub(v, 1, 1) == "@" then
				if string.match(v, "^@[%w_]+$") or string.match(v, "^@[%w_]+%^%-?[%d%.]+$") then
					return
				end
				err(path, `"{v}": an anchor is "@name" or "@name^studs" (studs along the anchor's +Y, e.g. "@tip^170")`)
				return
			end
			err(
				path,
				`unknown point "{v}" — add it to points, or use [x, y, z] / "target" / "@anchor" / "@anchor^studs"`
			)
			return
		end
		err(path, 'a point is [x, y, z], a name from points, "target" or "@anchor"')
	end
	local function texture(path: string, key: any, required: boolean?): any
		if key == nil then
			if required then
				err(path, "missing texture (a key of assets/effects/_textures.json)")
			end
			return nil
		end
		local e = textures and textures[key]
		if type(e) ~= "table" then
			err(path, `unknown texture "{tostring(key)}" (assets/textures/<key>.json -> lune run kit vfx registers it)`)
			return nil
		end
		return e
	end
	local function colorSeq(path: string, v: any)
		seq(path, v, color, 20)
	end

	local names: { [string]: boolean } = {}
	local samples: { number } = {} -- particle estimate every 0.1 s (samples[k] = time (k - 1) / 10)
	-- an attach effect runs "forever": its steady state shows within 30 s (every lifetime is <= 20 s)
	for _ = 1, math.ceil(math.min(duration, 30) * 10) + 1 do
		table.insert(samples, 0)
	end
	-- measured in Studio 2026-10-16 (kit/knowledge/vault/vfx/refs/engine-facts.md): the engine ignores a runtime
	-- mesh's per-vertex alpha, which is what "erode" writes. The player draws it, so the two disagree on those layers.
	-- Said ONCE a preset, with how many (a line a layer was 205 lines in 21 presets)
	local eroding, firstEroding = 0, nil :: any
	for _, el in preset.layers do
		if type(el) == "table" and el.kind == "mesh" and el.erode ~= nil then
			eroding += 1
			firstEroding = firstEroding or el.name
		end
	end
	if eroding > 0 then
		warn(
			"layers",
			`{eroding} mesh layer(s) break up by "erode" (the first: {tostring(firstEroding)}): erode shows in the browser player only - Roblox ignores the vertex alpha of a runtime mesh, so in the game these layers do not break up, they pop off. A dissolve the game shows is a baked sheet: lune run kit vfx dissolve <key> --from <its texture | plain>, then "texture": "<key>", "surface": 1, "flipbook": \{ "layout": "4x4", "mode": "OneShot", "over": [start, end] \}`
		)
	end
	for _, said in VfxBudget.problems(preset.layers) do -- detail tiers: a tier that is no level, nothing left at Low
		local where, what = string.match(said, "^(layers%[%d+%][^:]*): (.*)$")
		err(where or "layers", what or said)
	end
	for i, el in preset.layers do
		local p = `layers[{i}]`
		if type(el) == "table" and el.critical ~= nil then
			if type(el.critical) ~= "boolean" then
				err(
					p .. ".critical",
					"critical is true or false (a cue that must not be lost under mesh-pool pressure)"
				)
			elseif not (el.kind == "mesh" or (el.kind == "trail" and el.mesh == true)) then
				-- (it is read where a mesh is built for the layer itself: on any other layer it would do nothing)
				err(
					p .. ".critical",
					"critical is for a mesh layer or a mesh trail (the layers that build a mesh of their own)"
				)
			end
		end
		if type(el) ~= "table" or not KINDS[el.kind] then
			err(p .. ".kind", "kind must be " .. KIND_LIST)
			continue
		end
		if type(el.name) == "string" then
			if names[el.name] then
				err(p .. ".name", `two layers are called "{el.name}" — names must be unique`)
			end
			names[el.name] = true
			p = `{p}({el.name})`
		end
		if el.frames ~= nil and type(el.frames) ~= "boolean" then -- (review 2026-10-25: "false" or 0 passed and was ignored)
			err(p .. ".frames", "frames is true / false (false keeps the layer out of impact frames)")
		end
		local at = el.at or 0
		if not isNum(at) or at < 0 or at >= duration then
			err(p .. ".at", "at (start, seconds) must be 0 <= at < duration")
			at = 0
		end
		local life = el.life
		if life ~= nil and (not isNum(life) or life <= 0) then
			err(p .. ".life", "life (seconds the layer runs) must be > 0")
			life = 1
		end
		local kind = el.kind
		local ends = at + (if isNum(life) then life else 1)
		if el.rotate ~= nil and not isVec(el.rotate) then
			err(p .. ".rotate", "rotate is [x, y, z] degrees")
		end
		if el.onMaterial ~= nil then
			if type(el.onMaterial) ~= "table" then
				err(
					p .. ".onMaterial",
					'onMaterial is { "Slate|Rock": { overrides }, "Water": { "mute": true }, "*": {...} }'
				)
			else
				for pattern, over in el.onMaterial do
					if type(over) ~= "table" then
						err(
							p .. ".onMaterial." .. tostring(pattern),
							"each material maps to a table of layer overrides"
						)
					elseif over.texture ~= nil then
						texture(p .. ".onMaterial." .. tostring(pattern) .. ".texture", over.texture, true)
					end
					if pattern ~= "*" then
						for _, m in string.split(tostring(pattern), "|") do
							if not MATERIALS[m] and m ~= "Water" and m ~= "Air" then
								err(
									p .. ".onMaterial",
									`"{m}" is not a Roblox material (Slate, Metal, Wood, Grass, Water, ...)`
								)
							end
						end
					end
				end
			end
		end

		if kind == "sprite" then
			-- `spreadAngle` (Roblox's own property name) is NOT read: the stage and the player read `spread` - 309 layers in
			-- the 2026-10-23 audit emit with no cone. A warning, not an error: switching them on changes judged looks
			if el.spreadAngle ~= nil then
				warn(
					p .. ".spreadAngle",
					"`spreadAngle` is not read: the emitter's cone key is `spread` (degrees, or [x, y]) - this layer emits with no spread"
				)
			end
			local tex = texture(p .. ".texture", el.texture, true)
			point(p .. ".point", el.point)
			point(p .. ".aim", el.aim)
			if el.lit ~= nil then
				if type(el.lit) ~= "table" then
					err(p .. ".lit", "lit is { left, right, top, back, front } -> textures baked lit from that side")
				else
					for side, key in el.lit do
						if
							side ~= "left"
							and side ~= "right"
							and side ~= "top"
							and side ~= "back"
							and side ~= "front"
						then
							err(p .. ".lit." .. tostring(side), "a lit side is left | right | top | back | front")
						else
							texture(p .. ".lit." .. side, key, true)
						end
					end
				end
			end
			-- a BIG camera-facing card STANDING ON THE GROUND tilts back when the camera looks up at it and its bottom lifts
			-- off the floor (nuke_v4 round 1: a 230-stud surge floated mid-air): opaque ground cards this size stay upright
			local biggest = 0
			if isNum(el.size) then
				biggest = el.size
			elseif type(el.size) == "table" then
				for _, kv in el.size do
					if type(kv) == "table" and isNum(kv[2]) then
						biggest = math.max(biggest, kv[2])
					end
				end
			end
			local pt = if isVec(el.point)
				then el.point
				elseif type(el.point) == "string" and type(preset.points) == "table" then preset.points[el.point]
				else nil
			local onGround = isVec(pt) and pt[2] - biggest / 2 <= 1 -- the card's bottom edge at (or under) the floor
			local opaque = not isNum(el.lightEmission) or el.lightEmission < 0.5
			if
				biggest >= 40
				and onGround
				and opaque
				and (el.orientation == nil or el.orientation == "FacingCamera")
			then
				warn(
					p .. ".orientation",
					`a {biggest}-stud camera-facing card tilts back and lifts off the ground when the camera looks up: "orientation": "FacingCameraWorldUp" keeps it standing`
				)
			end
			if el.views ~= nil then
				if type(el.views) ~= "table" then
					err(
						p .. ".views",
						'views is { "0": tex, "90": tex, ... } - yaw degrees -> the cloud seen from that side'
					)
				else
					for yaw, key in el.views do
						if tonumber(yaw) == nil then
							err(p .. ".views", `"{tostring(yaw)}" is not a yaw in degrees`)
						else
							texture(p .. ".views." .. tostring(yaw), key, true)
						end
					end
				end
			end
			if el.wind ~= nil and type(el.wind) ~= "boolean" then
				err(p .. ".wind", "wind: true = drift with Workspace.GlobalWind (needs drag > 0)")
			elseif el.wind == true and not (isNum(el.drag) and el.drag > 0) then
				err(p .. ".wind", "wind needs drag > 0 (Roblox only lets wind act through drag)")
			end
			local count, rate, for_ = el.count or 0, el.rate or 0, el["for"] or 0
			if not isNum(count) or count < 0 or count > 200 or count % 1 ~= 0 then
				err(p .. ".count", "count (particles emitted at `at`) must be a whole number 0..200")
				count = 0
			end
			if mode == "attach" and isNum(rate) and rate > 0 and for_ == 0 then
				for_ = 1e9 -- an attach layer emits until the effect is stopped
			end
			if not isNum(rate) or rate < 0 or rate > 400 then
				err(p .. ".rate", "rate must be 0..400 per second")
				rate = 0
			elseif rate > 0 and (not isNum(for_) or for_ <= 0) then
				err(p .. ".for", 'rate needs "for": seconds of emission from `at`')
				for_ = 0
			end
			if count == 0 and rate == 0 then
				err(p, "emits nothing — set count > 0 (a burst) or rate + for")
			end
			range(p .. ".lifetime", el.lifetime, 0.01, 20)
			local maxLife = rangeMax(el.lifetime or 1)
			local ts = el.timeScale or 1
			if not isNum(ts) or ts <= 0 or ts > 1 then
				err(p .. ".timeScale", "timeScale must be 0 < timeScale <= 1 (slower lingering layers)")
				ts = 1
			end
			ends = at + for_ + maxLife / ts
			range(p .. ".speed", el.speed, 0, 5000)
			range(p .. ".rotation", el.rotation, -3600, 3600)
			range(p .. ".rotSpeed", el.rotSpeed, -3600, 3600)
			if el.spread ~= nil and not (isNum(el.spread) or (type(el.spread) == "table" and #el.spread == 2)) then
				err(p .. ".spread", "spread is a cone angle 0..180 or [x, y]")
			end
			seq(p .. ".size", el.size or 1, num(0, 2048), 20)
			seq(p .. ".transparency", el.transparency, num(0, 1), 20)
			seq(p .. ".squash", el.squash, num(-20, 20), 20)
			colorSeq(p .. ".color", el.color)
			num(0, 1000)(p .. ".brightness", el.brightness or 1)
			num(-10, 1)(p .. ".lightEmission", el.lightEmission or 0)
			num(0, 2)(p .. ".lightInfluence", el.lightInfluence or 0)
			num(-500, 500)(p .. ".zOffset", el.zOffset or 0)
			if el.acceleration ~= nil and not isVec(el.acceleration) then
				err(p .. ".acceleration", "acceleration is [x, y, z] studs/s²")
			end
			if el.orientation ~= nil and not ORIENTATIONS[el.orientation] then
				err(
					p .. ".orientation",
					"orientation: FacingCamera | FacingCameraWorldUp | VelocityParallel | VelocityPerpendicular"
				)
			end
			if el.direction ~= nil and not DIRECTIONS[el.direction] then
				err(p .. ".direction", "direction: Top | Bottom | Left | Right | Front | Back")
			end
			if el.orientation == "VelocityPerpendicular" and rangeMax(el.speed or 0) <= 0 then
				err(
					p .. ".speed",
					"a VelocityPerpendicular sprite needs a speed (0.001 is enough) or it is never drawn"
				)
			end
			local sh = el.shape
			if sh ~= nil then
				if type(sh) ~= "table" or not SHAPES[sh.type or "Sphere"] then
					err(p .. ".shape", 'shape is { "type": "Box" | "Sphere" | "Cylinder" | "Disc", "size": [x, y, z] }')
				else
					if sh.size ~= nil and not isVec(sh.size) then
						err(p .. ".shape.size", "size is [x, y, z] studs")
					end
					if sh.inOut ~= nil and not IN_OUT[sh.inOut] then
						err(p .. ".shape.inOut", "inOut: Outward | Inward | InAndOut")
					end
					if sh.style ~= nil and sh.style ~= "Volume" and sh.style ~= "Surface" then
						err(p .. ".shape.style", "style: Volume | Surface")
					end
					if sh.partial ~= nil then
						num(0, 1)(p .. ".shape.partial", sh.partial)
					end
				end
			end
			local fb = el.flipbook
			if fb == nil and tex and type(tex.grid) == "number" and tex.grid > 1 then
				-- a sheet drawn without a flipbook shows every frame at once: a grid of little copies
				err(
					p .. ".flipbook",
					`texture "{el.texture}" is a {tostring(tex.grid)}x{tostring(tex.grid)} sheet — add a flipbook (layout, fps, mode) or every frame shows at once`
				)
			end
			if fb ~= nil then
				if type(fb) ~= "table" then
					err(p .. ".flipbook", 'flipbook is { "layout": "4x4", "fps": 24, "mode": "OneShot" }')
				else
					local layout = fb.layout or "4x4"
					local cells = 0
					if type(layout) == "string" and GRIDS[layout] then
						cells = GRIDS[layout]
						if tex and tex.grid ~= nil and tex.grid ~= cells then
							err(
								p .. ".flipbook.layout",
								`texture "{el.texture}" is a {tostring(tex.grid)} grid, layout says {layout}`
							)
						end
					elseif type(layout) == "table" and #layout == 2 and isNum(layout[1]) and isNum(layout[2]) then
						cells = layout[1]
					else
						err(p .. ".flipbook.layout", 'layout is "2x2" | "4x4" | "8x8" or [columns, rows]')
					end
					if cells > 0 and tex and (tex.grid == nil or tex.grid == 1) then
						err(
							p .. ".flipbook",
							`texture "{el.texture}" is a single image, not a sheet — drop the flipbook`
						)
					end
					num(1, 30)(p .. ".flipbook.fps", fb.fps or 24)
					if fb.mode ~= nil and not FLIP_MODES[fb.mode] then
						err(p .. ".flipbook.mode", "mode: Loop | OneShot | PingPong | Random")
					end
				end
			end
			local twin = el.twin
			local tCount, tRate, tLife = 0, 0, 1
			if twin ~= nil and type(twin) ~= "table" then
				err(
					p .. ".twin",
					'twin is { "color": [0, 0, 0], "brightness": 0.01, "zOffset": -0.5, "lifeScale": 1.1 }'
				)
				twin = nil
			elseif twin then
				colorSeq(p .. ".twin.color", twin.color)
				seq(p .. ".twin.transparency", twin.transparency, num(0, 1), 20)
				num(0, 1000)(p .. ".twin.brightness", twin.brightness or 1)
				num(-10, 1)(p .. ".twin.lightEmission", twin.lightEmission or 0)
				num(-500, 500)(p .. ".twin.zOffset", twin.zOffset or 0)
				num(0.1, 10)(p .. ".twin.lifeScale", twin.lifeScale or 1)
				num(0.1, 10)(p .. ".twin.sizeScale", twin.sizeScale or 1)
				-- the runtime fires the twin with its main emitter: no main count / rate = no twin of that kind
				tCount = if count > 0 then twin.count or count else 0
				tRate = if rate > 0 then twin.rate or rate else 0
				tLife = if isNum(twin.lifeScale) then twin.lifeScale else 1
				if not isNum(tCount) or tCount < 0 or tCount > 200 or tCount % 1 ~= 0 then
					err(p .. ".twin.count", "twin count must be a whole number 0..200")
					tCount = 0
				end
				if not isNum(tRate) or tRate < 0 or tRate > 400 then
					err(p .. ".twin.rate", "twin rate must be 0..400 per second")
					tRate = 0
				end
				ends = math.max(ends, at + for_ + maxLife * tLife / ts)
			end
			-- particle estimate over time (the twin counted with its own numbers)
			local function alive(t: number, c: number, r: number, span: number): number
				local n = 0
				if c > 0 and t >= at and t <= at + span then
					n += c
				end
				if r > 0 and t >= at then
					n += r * math.max(0, math.min(t, at + for_) - math.max(at, t - span))
				end
				return n
			end
			for s = 1, #samples do
				local t = (s - 1) / 10
				samples[s] += alive(t, count, rate, maxLife / ts)
				if twin then
					samples[s] += alive(t, tCount, tRate, maxLife * tLife / ts)
				end
			end
		elseif kind == "beam" then
			point(p .. ".from", el.from, true)
			point(p .. ".to", el.to, true)
			texture(p .. ".texture", el.texture)
			seq(p .. ".width", el.width or 1, num(0, 500))
			seq(p .. ".brightness", el.brightness, num(0, 1000))
			seq(p .. ".fade", el.fade, num(0, 1))
			seq(p .. ".transparency", el.transparency, num(0, 1), 20)
			if el.softEnds ~= nil then -- the stretch of the length each end fades over (0 = a hard cap; default 0.12)
				num(0, 0.5)(p .. ".softEnds", el.softEnds)
			end
			colorSeq(p .. ".color", el.color)
			range(p .. ".textureSpeed", el.textureSpeed, -200, 200)
			num(0.01, 5000)(p .. ".textureLength", el.textureLength or 10)
			num(1, 100)(p .. ".segments", el.segments or 10)
			num(1, 8)(p .. ".copies", el.copies or 1)
			if el.grow ~= nil then
				num(0.001, 30)(p .. ".grow", el.grow)
			end
			pair(p .. ".taper", el.taper, 0, 20)
			pair(p .. ".curve", el.curve, -500, 500)
			if el.curveAxis ~= nil then -- the attachments' X axis (effect space): the direction the curve bends
				if type(el.curveAxis) ~= "table" or #el.curveAxis ~= 3 then
					err(p .. ".curveAxis", "curveAxis is [x, y, z] (the direction the curve bends)")
				end
			end
			num(0, 500)(p .. ".jitter", el.jitter or 0)
			num(-5, 5)(p .. ".widthSpread", el.widthSpread or 0)
			num(-10, 10)(p .. ".zStep", el.zStep or 0.05)
			if el.plane ~= nil and el.plane ~= "camera" and el.plane ~= "up" and el.plane ~= "flat" then
				err(
					p .. ".plane",
					"plane: camera (faces the camera) | up (a standing wall along the path) | flat (lying)"
				)
			end
			if el.plane ~= nil and el.plane ~= "camera" and el.curve ~= nil then
				err(
					p .. ".curve",
					"a wall / flat beam cannot curve (its two faces would bend apart) — drop curve or plane"
				)
			end
			if el.growEase ~= nil and el.growEase ~= "in" and el.growEase ~= "out" and el.growEase ~= "linear" then
				err(p .. ".growEase", "growEase: in | out | linear")
			end
			if
				el.textureMode ~= nil
				and el.textureMode ~= "Wrap"
				and el.textureMode ~= "Stretch"
				and el.textureMode ~= "Static"
			then
				err(p .. ".textureMode", "textureMode: Wrap | Stretch | Static")
			end
		elseif kind == "mesh" then
			knownKeys(p, el, MESH_KEYS)
			if el.forced ~= nil then -- forced perspective: the size answers the camera's distance (kit/vfx/forced.py)
				if type(el.forced) ~= "table" then
					err(p .. ".forced", 'forced is a block: "forced": { "ref": 40, "keep": 1, "min": 0.25, "max": 4 }')
				else
					local f = el.forced
					for key in f do
						if key ~= "ref" and key ~= "keep" and key ~= "min" and key ~= "max" then
							err(`{p}.forced.{tostring(key)}`, "forced reads ref, keep, min and max")
						end
					end
					if f.ref == nil then
						err(
							p .. ".forced.ref",
							"ref is the distance (studs) at which the layer is the size it was made at"
						)
					else
						num(1, 5000)(p .. ".forced.ref", f.ref)
					end
					if f.keep ~= nil then
						num(-1, 1)(p .. ".forced.keep", f.keep)
						if isNum(f.keep) and math.abs(f.keep) < 0.05 then
							err(p .. ".forced.keep", "a keep nearer 0 than 0.05 does nothing: drop forced")
						end
					end
					if f.min ~= nil then
						num(0.01, 1)(p .. ".forced.min", f.min)
					end
					if f.max ~= nil then
						num(1, 100)(p .. ".forced.max", f.max)
					end
					if f.min == 1 and f.max == 1 then
						err(p .. ".forced", "min 1 and max 1 hold the multiplier at 1: forced does nothing")
					end
				end
			end
			if el.shape == "seq" then
				local sp = el.params or {}
				if type(sp.seq) ~= "string" or sp.seq == "" then
					err(
						p .. ".params.seq",
						"a seq mesh names its baked sequence: params.seq (kit/vfx/meshseq.py -> assets/effects/seq/<name>.json)"
					)
				end
				if sp.fps ~= nil then
					num(1, 120)(p .. ".params.fps", sp.fps)
				end
			end
			if not MESH_SHAPES[el.shape or "ring"] then
				err(
					p .. ".shape",
					"shape: ring | disc | tube | crown | cone | sphere | torus | dome | spiral | arc | flame | tongue | bolt | spikes | cards | corona (runtime meshes) or Ball | Block | Cylinder"
				)
			end
			if not MESH_MATERIALS[el.material or "Neon"] then
				err(p .. ".material", "material: Neon | ForceField (glowing texture pattern) | Glass | SmoothPlastic")
			end
			local mtex = texture(p .. ".texture", el.texture)
			if el.flipbook ~= nil then -- a flipbook sheet played ON the mesh (its UVs step from cell to cell)
				local fb = el.flipbook
				if type(fb) ~= "table" or (fb.layout ~= nil and not GRIDS[fb.layout]) then
					err(p .. ".flipbook", 'flipbook is { "layout": "2x2" | "4x4" | "8x8", "fps": 16, "mode": "Loop" }')
				else
					num(1, 30)(p .. ".flipbook.fps", fb.fps or 24)
					if fb.mode ~= nil and fb.mode ~= "Loop" and fb.mode ~= "OneShot" then
						err(p .. ".flipbook.mode", "mode on a mesh: Loop | OneShot")
					end
					if fb.over ~= nil then -- the part of the layer's life a OneShot sheet plays in (a baked dissolve)
						local o = fb.over
						if
							type(o) ~= "table"
							or #o ~= 2
							or not isNum(o[1])
							or not isNum(o[2])
							or o[1] < 0
							or o[2] > 1
							or o[1] >= o[2]
						then
							err(
								p .. ".flipbook.over",
								"over is [start, end] of the layer's life: 0 <= start < end <= 1"
							)
						elseif fb.mode ~= "OneShot" then
							err(
								p .. ".flipbook.over",
								'over needs "mode": "OneShot" (a looping sheet has no first and last cell)'
							)
						elseif el.surface == nil then
							-- the sheet's holes are texture ALPHA: on a runtime mesh the engine shows that only through a
							-- SurfaceAppearance (the same measurement); without it the game draws every cell as a full square
							err(
								p .. ".flipbook.over",
								'a sheet that breaks up needs "surface": 1 on its mesh: the game shows the alpha of a mesh texture only through a SurfaceAppearance'
							)
						end
					end
					local cells = GRIDS[fb.layout or "4x4"]
					if mtex and mtex.grid ~= nil and mtex.grid ~= cells then
						err(
							p .. ".flipbook.layout",
							`texture "{el.texture}" is a {tostring(mtex.grid)} grid, not {fb.layout or "4x4"}`
						)
					end
					if el.uvScroll ~= nil then
						err(p .. ".uvScroll", "a flipbook mesh steps its UVs cell by cell — drop uvScroll")
					end
				end
			end
			point(p .. ".point", el.point)
			point(p .. ".aim", el.aim)
			seq(p .. ".scale", el.scale or 1, numOrVec(0, 4096))
			if el.move ~= nil then -- a position offset over life, in the layer's frame (studs): a cloud that RISES
				seq(p .. ".move", el.move, numOrVec(-4096, 4096))
			end
			seq(p .. ".transparency", el.transparency, num(0, 1))
			colorSeq(p .. ".color", el.color)
			if el.uvScroll ~= nil and not (type(el.uvScroll) == "table" and #el.uvScroll == 2) then
				err(p .. ".uvScroll", "uvScroll is [u, v] texture repeats per second")
			end
			-- surface: the texture as a SurfaceAppearance (ColorMap + EmissiveMask + AlphaMode Transparency) - the only
			-- way a mesh gets texture alpha AND glow in the engine (measured 2026-10-16, vault vfx/refs/engine-facts)
			if el.surface ~= nil then
				if not (el.surface == true or (isNum(el.surface) and el.surface >= 0 and el.surface <= 50)) then
					err(
						p .. ".surface",
						"surface is true or the emissive strength 0-50 (the glow of the texture's lit texels)"
					)
				elseif not el.texture then
					err(
						p .. ".surface",
						"surface needs a texture (it becomes the SurfaceAppearance's colour, alpha and glow)"
					)
				end
			end
			if
				el.wobble ~= nil
				and not (
					type(el.wobble) == "table"
					and #el.wobble == 3
					and isNum(el.wobble[1])
					and isNum(el.wobble[2])
					and isNum(el.wobble[3])
				)
			then
				err(p .. ".wobble", "wobble is [amp studs, freq lobes round the axis, speed radians per second]")
			end
			if el.step ~= nil then -- drawings per second (12 = on twos)
				num(1, 60)(p .. ".step", el.step)
			end
			if el.erode ~= nil then
				local e = el.erode
				local ok = type(e) == "table"
					and #e >= 2
					and isNum(e[1])
					and isNum(e[2])
					and e[1] >= 0
					and e[2] <= 1
					and e[1] < e[2]
					and (e[3] == nil or (isNum(e[3]) and e[3] > 0 and e[3] <= 1))
				if not ok then
					err(p .. ".erode", "erode is [start, end, soft?]: 0 <= start < end <= 1, soft in (0, 1]")
				elseif el.shape == "Ball" or el.shape == "Block" or el.shape == "Cylinder" then
					err(
						p .. ".erode",
						"erode needs a runtime mesh shape (a primitive part has no vertices to dissolve)"
					)
				end
			end
			if el.shape == "crown" and type(el.params) == "table" and el.params.scallops ~= nil then
				local n = el.params.scallops
				if not isNum(n) or n < 0 or n % 1 ~= 0 then -- a fractional count leaves a crack at the seam (u = 0 / 1)
					err(p .. ".params.scallops", "scallops is a whole number >= 0 (a fraction cracks the crown's seam)")
				end
			end
			if el.reflectance ~= nil then -- a mirror: the part's Reflectance (liquid metal, chrome)
				num(0, 1)(p .. ".reflectance", el.reflectance)
			end
			if el.roughness ~= nil then -- the player's mirror blur (the engine's reflection is sharp)
				num(0, 1)(p .. ".roughness", el.roughness)
			end
			-- spin: [x, y, z] degrees per second, or keys of that SPEED over life (the angle is its integral: spin up)
			seq(p .. ".spin", el.spin, function(q: string, x: any)
				if not isVec(x) then
					err(q, "spin is [x, y, z] degrees per second (or keys [[u, [x, y, z]], ...] of that speed)")
				end
			end)
			if el.pivot == "base" and el.shape == "seq" then
				-- the game puts the first frame's box bottom on the point, the player the file's own origin: two places
				warn(
					p .. ".pivot",
					'pivot "base" on a mesh sequence is NOT the same place in the game and in the player: "origin" is (the file\'s own origin on the point)'
				)
			end
			if el.pivot == "origin" then
				if el.shape ~= "seq" then
					err(
						p .. ".pivot",
						'pivot "origin" is for a mesh sequence ("shape": "seq"): its file\'s own origin on the point'
					)
				end
			elseif el.pivot ~= nil and el.pivot ~= "base" and el.pivot ~= "center" then
				err(
					p .. ".pivot",
					"pivot: base (starts at its point, runs along +Y) | center | origin (a mesh sequence's own origin on its point)"
				)
			end
			if el.params ~= nil then
				if type(el.params) ~= "table" then
					err(p .. ".params", "params is an object of numbers (the shape's size settings)")
				else
					for k, v in el.params do
						-- a mesh sequence names its frames (params.seq) and may loop (params.loop): the only non-numbers
						local seqKey = el.shape == "seq"
							and ((k == "seq" and type(v) == "string") or (k == "loop" and type(v) == "boolean"))
						if not isNum(v) and not seqKey then
							err(`{p}.params.{k}`, "shape params are numbers")
						end
					end
				end
			end
			if el.sweep ~= nil then -- an arc drawn in along itself and erased behind (VfxArc): the visible window over life
				if el.shape ~= "arc" then
					err(p .. ".sweep", "sweep draws an ARC along itself: shape must be arc")
				elseif el.wobble ~= nil then -- both rewrite the vertices: wobble restores the full arc every frame
					err(p .. ".sweep", "sweep and wobble both move the arc's vertices: use one")
				elseif type(el.sweep) ~= "table" or (el.sweep.head == nil and el.sweep.tail == nil) then
					err(
						p .. ".sweep",
						"sweep is { head: 0-1 curve, tail: 0-1 curve }: the part of the arc shown over the life"
					)
				else
					seq(p .. ".sweep.head", el.sweep.head, num(0, 1))
					seq(p .. ".sweep.tail", el.sweep.tail, num(0, 1))
				end
			end
		elseif kind == "decal" then
			texture(p .. ".texture", el.texture, true)
			point(p .. ".point", el.point)
			seq(p .. ".size", el.size or 10, numOrVec(0, 4096))
			-- "wrap": the mark draped over the real ground - true, or the cells a side (2 to 16)
			if el.wrap ~= nil and el.wrap ~= true and el.wrap ~= false then
				if type(el.wrap) ~= "number" or el.wrap ~= math.floor(el.wrap) or el.wrap < 2 or el.wrap > 16 then
					err(p .. ".wrap", "wrap: true, or the cells a side of the draped mark (a whole number, 2 to 16)")
				end
			end
			if el.reach ~= nil and (type(el.reach) ~= "number" or el.reach <= 0 or el.reach > 64) then
				err(p .. ".reach", "reach: how far above and below the mark the ground is looked for (studs, up to 64)")
			end
			seq(p .. ".glow", el.glow, num(0, 50))
			seq(p .. ".transparency", el.transparency, num(0, 1))
			colorSeq(p .. ".color", el.color)
		elseif kind == "light" then
			point(p .. ".point", el.point)
			point(p .. ".aim", el.aim)
			seq(p .. ".range", el.range or 16, num(0, 60))
			seq(p .. ".brightness", el.brightness or 1, num(0, 100))
			colorSeq(p .. ".color", el.color)
			if el.type ~= nil and el.type ~= "point" and el.type ~= "spot" and el.type ~= "surface" then
				err(p .. ".type", "type: point | spot (a cone along +Y: aim / rotate) | surface (a size [w, d] panel)")
			end
			if el.angle ~= nil then
				num(0, 180)(p .. ".angle", el.angle)
			end
			if el.size ~= nil and not (type(el.size) == "table" and isNum(el.size[1])) then
				err(p .. ".size", "size: [width, depth] studs of a surface light's panel")
			end
		elseif kind == "swarm" then
			point(p .. ".point", el.point)
			num(1, 150)(p .. ".count", el.count or 40)
			range(p .. ".lifetime", el.lifetime, 0.05, 20)
			range(p .. ".speed", el.speed, 0, 500)
			num(0, 200)(p .. ".radius", el.radius or 1)
			num(0, 20)(p .. ".spawn", el.spawn or 0)
			seq(p .. ".size", el.size or 0.3, num(0, 50))
			seq(p .. ".transparency", el.transparency, num(0, 1))
			colorSeq(p .. ".color", el.color)
			num(0, 1000)(p .. ".gravity", el.gravity or 0)
			seq(p .. ".drag", el.drag or 0, num(0, 50)) -- a number, or a curve over the layer's life
			if el.material ~= nil and not MATERIALS[el.material] then
				err(p .. ".material", `"{tostring(el.material)}" is not a Roblox material`)
			end
			if el.shape ~= nil and el.shape ~= "Ball" and el.shape ~= "Block" and el.shape ~= "Rock" then
				err(p .. ".shape", "shape: Ball | Block | Rock (mesh particles: faceted stones that tumble)")
			end
			if el.shape == "Rock" then -- mesh particles: each is a runtime mesh, built one by one
				if isNum(el.count) and el.count > 40 then
					err(
						p .. ".count",
						"a swarm of Rock is 40 at most (each stone is its own mesh, built in a quarter of a second)"
					)
				end
				if el.trail ~= nil then
					err(
						p .. ".trail",
						"a swarm of Rock has no trail (the stone is swapped in for its block after the trail is made): drop trail, or Ball / Block"
					)
				end
				if el.rock ~= nil then
					if type(el.rock) ~= "table" then
						err(p .. ".rock", 'rock is a block: "rock": { "cuts": 9, "jag": 0.5, "spike": 0, "flat": 1 }')
					else
						for key in el.rock do
							if key ~= "cuts" and key ~= "jag" and key ~= "spike" and key ~= "flat" then
								err(
									`{p}.rock.{tostring(key)}`,
									"rock reads cuts, jag, spike and flat (the debris layer's stone keys)"
								)
							end
						end
						-- (the debris layer's ranges for the same stone: outside them it is a ball, an inside-out
						-- mesh, a stone with no height, or a client that freezes)
						local ranges: { [string]: { number } } =
							{ cuts = { 3, 24 }, jag = { 0, 0.9 }, spike = { 0, 1 }, flat = { 0.1, 6 } }
						for key, span in ranges do
							if el.rock[key] ~= nil then
								num(span[1], span[2])(`{p}.rock.{key}`, el.rock[key])
							end
						end
					end
				end
				if el.tumble ~= nil then
					if
						type(el.tumble) ~= "table"
						or not isNum(el.tumble[1])
						or not isNum(el.tumble[2])
						or el.tumble[1] > el.tumble[2]
					then
						err(p .. ".tumble", "tumble is [slowest, fastest] in radians a second, e.g. [2, 6]")
					elseif el.tumble[1] < 0 or el.tumble[2] > 40 then
						err(p .. ".tumble", "tumble is 0 to 40 radians a second")
					end
				end
			elseif el.rock ~= nil or el.tumble ~= nil then
				err(
					p .. (if el.rock ~= nil then ".rock" else ".tumble"),
					'rock and tumble are read with "shape": "Rock" only'
				)
			end
			for _, k in { "curl", "attract", "floor", "trail" } do
				if el[k] ~= nil and type(el[k]) ~= "table" then
					err(
						p .. "." .. k,
						`{k} is a table (curl \{strength, scale, speed\}, attract \{point, strength, swirl\}, floor \{y, bounce\}, trail \{lifetime\})`
					)
				end
			end
			-- F1b: a bounce's own burst (src/kit/VfxBounce.luau: the rules both players read)
			if type(el.floor) == "table" and el.floor.onBounce ~= nil then
				local okB, badB = VfxBounce.checked(el.floor.onBounce)
				if not okB then
					for _, m in badB do
						err(p .. ".floor.onBounce", m)
					end
				end
			end
			if el.field ~= nil then -- an authored vector field the particles follow (kit vfx field)
				if type(el.field) ~= "table" then
					err(
						p .. ".field",
						'field is a block: "field": { "name": "<a field of kit vfx field>", "follow": 6, "gain": 1 }'
					)
				else
					local f = el.field
					for key in f do
						if key ~= "name" and key ~= "follow" and key ~= "gain" then
							err(`{p}.field.{tostring(key)}`, "a field block reads name, follow and gain")
						end
					end
					if type(f.name) ~= "string" or not string.match(f.name, "^[a-z][a-z0-9_]*$") then
						err(
							p .. ".field.name",
							"name is a field of lune run kit vfx field <name> (lowercase letters, digits, _)"
						)
					end
					if f.follow ~= nil then
						num(0.1, 60)(p .. ".field.follow", f.follow)
					end
					seq(p .. ".field.gain", f.gain, num(-5, 5)) -- (a field's own speeds go to 400: scale them there)
				end
			end
			if el.cloud ~= nil then -- a point cloud the particles gather into (kit vfx points)
				if type(el.cloud) ~= "table" then
					err(
						p .. ".cloud",
						'cloud is a block: "cloud": { "name": "<a cloud of kit vfx points>", "size": 6, "pull": 8 }'
					)
				else
					local c = el.cloud
					for key in c do
						if key ~= "name" and key ~= "size" and key ~= "pull" then
							err(`{p}.cloud.{tostring(key)}`, "a cloud block reads name, size and pull")
						end
					end
					if type(c.name) ~= "string" or not string.match(c.name, "^[a-z][a-z0-9_]*$") then
						err(
							p .. ".cloud.name",
							"name is a cloud of lune run kit vfx points <name> (lowercase letters, digits, _)"
						)
					end
					if c.size ~= nil then
						num(0.1, 500)(p .. ".cloud.size", c.size)
					end
					seq(p .. ".cloud.pull", c.pull, num(0, 60)) -- (a curve over the layer's life: 0 lets go)
				end
			end
			if type(el.attract) == "table" then
				point(p .. ".attract.point", el.attract.point)
				-- a number, or a curve over the layer's life (an implosion that lets go)
				seq(p .. ".attract.strength", el.attract.strength, num(-2000, 2000))
				seq(p .. ".attract.swirl", el.attract.swirl, num(-2000, 2000))
			end
		elseif kind == "lens" then
			-- (where its flare's light is: a point that is no point was read as the origin, and never said)
			point(p .. ".point", el.point)
			point(p .. ".aim", el.aim)
			seq(p .. ".vignette", el.vignette, num(0, 1))
			seq(p .. ".aberration", el.aberration, num(0, 1))
			seq(p .. ".dirt", el.dirt, num(0, 1))
			seq(p .. ".zoom", el.zoom, num(0, 1))
			seq(p .. ".streaks", el.streaks, num(0, 1)) -- directional speed lines across the screen
			if el.streakAngle ~= nil then
				num(-360, 360)(p .. ".streakAngle", el.streakAngle)
			end
			if el.streakSpeed ~= nil then
				num(0, 10)(p .. ".streakSpeed", el.streakSpeed)
			end
			colorSeq(p .. ".color", el.color)
			colorSeq(p .. ".zoomColor", el.zoomColor)
			colorSeq(p .. ".streakColor", el.streakColor)
			if el.dirtTexture ~= nil then
				texture(p .. ".dirtTexture", el.dirtTexture, true)
			end
			if el.flare ~= nil then -- the lens answering a light at the layer's point (kit/vfx/flare.py is the rule)
				if type(el.flare) ~= "table" then
					err(p .. ".flare", 'flare is a block: "flare": { "strength": 0.8, "ghosts": 5, "streak": 0.6 }')
				else
					local f = el.flare
					local read = {
						strength = true,
						ghosts = true,
						size = true,
						streak = true,
						squeeze = true,
						color = true,
						occlude = true,
					}
					for key in f do
						if not read[key] then
							err(
								`{p}.flare.{tostring(key)}`,
								"a flare reads strength, ghosts, size, streak, squeeze, color and occlude"
							)
						end
					end
					if f.strength == nil then
						err(
							p .. ".flare.strength",
							"say how strong the flare is: a number 0-1 or a curve over the layer's life"
						)
					end
					seq(p .. ".flare.strength", f.strength, num(0, 1))
					if f.occlude ~= nil and type(f.occlude) ~= "boolean" then
						err(
							p .. ".flare.occlude",
							"occlude is true or false: hide the flare while something stands before its light"
						)
					end
					if f.ghosts ~= nil then
						num(0, 8)(p .. ".flare.ghosts", f.ghosts)
					end
					if f.size ~= nil then
						num(0.01, 1)(p .. ".flare.size", f.size)
					end
					if f.streak ~= nil then
						num(0, 2)(p .. ".flare.streak", f.streak)
					end
					if f.squeeze ~= nil then
						num(1, 3)(p .. ".flare.squeeze", f.squeeze)
					end
					colorSeq(p .. ".flare.color", f.color)
					-- its three pictures are made once a project (python kit/vfx/lens.py lens_glow lens_ghost lens_streak)
					for _, key in { "lens_glow", "lens_ghost", "lens_streak" } do
						if not (textures and type(textures[key]) == "table") then
							err(
								p .. ".flare",
								`a flare draws the texture "{key}": python kit/vfx/lens.py lens_glow lens_ghost lens_streak, then lune run kit vfx`
							)
							break
						end
					end
					if el.point == nil then
						warn(
							p .. ".flare",
							"a flare with no point answers the effect's own origin: say where the light is"
						)
					else
						point(p .. ".point", el.point) -- (a misspelt named point would put the light at the origin)
					end
				end
			end
			if el.radius ~= nil then
				num(0, 5000)(p .. ".radius", el.radius)
			end
		elseif kind == "crater" then
			point(p .. ".point", el.point)
			num(0.5, 80)(p .. ".radius", el.radius or 6)
			if el.depth ~= nil then
				num(0, 80)(p .. ".depth", el.depth)
			end
			-- on a part floor the crater is a ROCK RING (src/kit/VfxRockRing.luau): its mark's texture (default
			-- rock_ring) and how many chunks it throws up (default about one a stud of radius; 0 = the mark alone)
			texture(p .. ".texture", el.texture)
			if el.rocks ~= nil then
				num(0, 32)(p .. ".rocks", el.rocks)
			end
			if el.seed ~= nil then
				num(0, 1000000)(p .. ".seed", el.seed)
			end
		elseif kind == "world" then
			seq(p .. ".exposure", el.exposure, num(-3, 3))
			seq(p .. ".fog", el.fog, num(0, 20))
			seq(p .. ".fogAmount", el.fogAmount, num(0, 1))
			colorSeq(p .. ".fogColor", el.fogColor)
			colorSeq(p .. ".sky", el.sky)
			seq(p .. ".skyAmount", el.skyAmount, num(0, 1))
			seq(p .. ".sun", el.sun, num(0, 10))
			seq(p .. ".ambient", el.ambient, num(0, 10))
			seq(p .. ".sunRays", el.sunRays, num(0, 1))
			seq(p .. ".dof", el.dof, num(0, 1))
			if el.focus ~= nil then
				num(0, 5000)(p .. ".focus", el.focus)
			end
			if el.radius ~= nil then
				num(0, 5000)(p .. ".radius", el.radius)
			end
		elseif kind == "debris" then
			knownKeys(p, el, DEBRIS_KEYS)
			point(p .. ".point", el.point)
			point(p .. ".aim", el.aim)
			num(1, 40)(p .. ".count", el.count or 6)
			range(p .. ".speed", el.speed, 0, 1000)
			range(p .. ".size", el.size, 0.05, 50)
			num(0, 1000)(p .. ".gravity", el.gravity or 120)
			num(0, 180)(p .. ".spread", el.spread or 60)
			colorSeq(p .. ".color", el.color)
			if el.pieces ~= nil then -- a fracture plan's own pieces (kit vfx fracture): they are what flies
				if type(el.pieces) ~= "string" or not string.match(el.pieces, "^[a-z][a-z0-9_]*$") then
					err(
						p .. ".pieces",
						'pieces names a fracture plan: "pieces": "<name>" (lune run kit vfx fracture <name> --size w,d)'
					)
				end
				if el.shape ~= nil then
					err(p .. ".shape", "a layer of pieces has their shapes from its fracture plan - drop shape")
				end
				if el.rest ~= nil and type(el.rest) ~= "boolean" then
					err(p .. ".rest", "rest is true (the pieces come to rest and lie there) or false")
				elseif el.rest == true and (el.aim ~= nil or el.rotate ~= nil) then
					-- (the rule's floor and its flat faces are the WORLD's level: a slab turned by aim / rotate - a wall -
					-- would have its pieces come to rest buried or standing on edge)
					err(
						p .. ".rest",
						"rest is for a slab that lies level: drop aim / rotate, or drop rest (a turned slab's pieces cannot lie flat yet)"
					)
				elseif el.rest == true and isNum(el.gravity) and el.gravity < 1 then
					err(p .. ".rest", "with rest, gravity is 1 or more: without it no piece ever lands")
				elseif el.rest == true and isNum(el.life) and el.life < 1 then
					warn(
						p .. ".rest",
						"pieces rarely come to rest in under a second: lune run kit vfx settle <plan> --life <this life> says when the last one does"
					)
				end
				if el.speed ~= nil and not isNum(el.speed) then
					err(p .. ".speed", "with pieces, speed is ONE number: the speed of the piece nearest the blow")
				elseif isNum(el.speed) and el.speed <= 0 then
					err(
						p .. ".speed",
						"with pieces, speed above 0: at 0 no piece leaves the slab (drop it for the plan's own)"
					)
				end
				for _, key in { "count", "size", "spread", "cuts", "jag", "spike", "flat", "seed" } do
					if el[key] ~= nil then
						warn(
							p .. "." .. key,
							`{key} is not read when the layer flies a fracture plan's pieces - drop it`
						)
					end
				end
			end
			if el.rest ~= nil and el.pieces == nil then
				err(
					p .. ".rest",
					'rest is for a layer that flies a fracture plan ("pieces": "<name>"): thrown rocks keep the old flight'
				)
			end
			if el.shape ~= nil and el.shape ~= "rock" and el.shape ~= "block" then
				err(p .. ".shape", "shape: rock (faceted stones, built at runtime) | block (the default)")
			end
			if el.floor ~= nil and el.floor ~= "hit" and el.floor ~= "world" then
				err(
					p .. ".floor",
					"floor: hit (a floor at the effect's height, the default) | world (real physics on the place)"
				)
			end
			if el.cuts ~= nil then
				num(3, 24)(p .. ".cuts", el.cuts)
			end
			if el.jag ~= nil then
				num(0, 0.9)(p .. ".jag", el.jag)
			end
			if el.spike ~= nil then
				num(0, 1)(p .. ".spike", el.spike)
			end
			if el.flat ~= nil then
				num(0.1, 6)(p .. ".flat", el.flat)
			end
			if el.material ~= nil and not MATERIALS[el.material] then
				err(
					p .. ".material",
					`"{tostring(el.material)}" is not a Roblox material (Slate, Basalt, Rock, Ground, ...)`
				)
			end
		elseif kind == "screen" then
			seq(p .. ".brightness", el.brightness, num(-1, 2))
			seq(p .. ".contrast", el.contrast, num(-2, 4))
			seq(p .. ".saturation", el.saturation, num(-1, 2))
			seq(p .. ".blur", el.blur, num(0, 56))
			seq(p .. ".bloom", el.bloom, num(0, 10))
			seq(p .. ".tintAmount", el.tintAmount, num(0, 1))
			colorSeq(p .. ".tint", el.tint)
			if el.radius ~= nil then
				num(0, 5000)(p .. ".radius", el.radius)
			end
		elseif kind == "impact" then
			if
				el.mode ~= nil
				and el.mode ~= "white"
				and el.mode ~= "black"
				and el.mode ~= "mono"
				and el.mode ~= "flash"
				and el.mode ~= "ink"
				and el.mode ~= "invert"
			then
				err(
					p .. ".mode",
					"mode: white (stark: contrast-stretched) | black | mono | flash (a flat white-out) | ink (black world, white silhouette) | invert (the negative frame)"
				)
			end
			if el.style ~= nil and el.style ~= "frame" and el.style ~= "comic" and el.style ~= "anime" then
				err(
					p .. ".style",
					"style: frame (ink-paper, built from the scene) | comic (the lit scene printed as a comic page) | anime (TV-anime cut-ins: look tone | burst | sky)"
				)
			end
			if el.style == "anime" then
				if el.look ~= nil and el.look ~= "tone" and el.look ~= "burst" and el.look ~= "sky" then
					err(
						p .. ".look",
						"anime look: tone (the shot duotoned, hatched, energy glowing) | burst (radial colour + speed lines + white core) | sky"
					)
				end
				for _, k in { "shadow", "light", "hatch", "energy", "core", "edge", "linesColor" } do
					local v = el[k]
					if v ~= nil and v ~= "white" and v ~= "black" then
						color(p .. "." .. k, v)
					end
				end
				seq(p .. ".zoom", el.zoom, num(0.3, 8))
				seq(p .. ".push", el.push, num(0.3, 4))
				seq(p .. ".linesK", el.linesK, num(0, 3))
				seq(p .. ".coreSize", el.coreSize, num(0, 1.5))
			end
			if el.style == "comic" then
				for _, k in { "paper", "ink", "spot", "spot2", "wordColor", "balloonColor" } do
					local v = el[k]
					if v ~= nil and v ~= "white" and v ~= "black" then
						color(p .. "." .. k, v)
					end
				end
				if el.panels ~= nil then
					num(1, 3)(p .. ".panels", el.panels)
				end
				if el.halftone ~= nil then
					num(0.003, 0.05)(p .. ".halftone", el.halftone)
				end
				if el.misreg ~= nil then
					num(0, 0.03)(p .. ".misreg", el.misreg)
				end
				if el.lines ~= nil and el.lines ~= "radial" and el.lines ~= "speed" and el.lines ~= "none" then
					err(p .. ".lines", "comic lines: radial | speed | none")
				end
				seq(p .. ".wordSize", el.wordSize, num(0.02, 1.2))
				seq(p .. ".wordRot", el.wordRot, num(-60, 60))
				seq(p .. ".push", el.push, num(0.3, 4))
				seq(p .. ".slant", el.slant, num(-40, 40))
				seq(p .. ".shake", el.shake, num(0, 0.05))
				point(p .. ".focus2", el.focus2)
			end
			if el.style == "frame" then
				for _, k in { "paper", "ink", "accent", "hot", "mark", "linesColor" } do
					local v = el[k]
					if v ~= nil and v ~= "white" and v ~= "black" then
						color(p .. "." .. k, v)
					end
				end
				if el.text ~= nil then -- an onomatopoeia frame
					if type(el.text) ~= "string" or #el.text == 0 or #el.text > 12 then
						err(p .. ".text", "text: 1-12 characters (DON!!)")
					end
					num(0.1, 1.5)(p .. ".textSize", el.textSize or 0.55)
					num(-60, 60)(p .. ".textRot", el.textRot or -12)
					if el.textColor ~= nil and el.textColor ~= "white" and el.textColor ~= "black" then
						color(p .. ".textColor", el.textColor)
					end
					if el.textAt ~= nil then
						point(p .. ".textAt", el.textAt)
					end
					if el.lettering ~= nil then -- the word as a graphic + the slam
						if type(el.lettering) ~= "table" then
							err(
								p .. ".lettering",
								"lettering: { skew, cut, stagger, stretch, squash, offset, band, bandLines, bandColor, sub }"
							)
						else
							local ranges = {
								skew = { -0.6, 0.6 },
								stagger = { 0, 2 },
								stretch = { 0.3, 3 },
								squash = { 0.3, 3 },
								offset = { -1, 1 },
								bandLines = { 0, 3 },
								split = { 0, 1 },
								glint = { -1, 1.5 },
								trail = { 0, 3 },
							}
							ranges.scale = { 0.2, 3 }
							ranges.tilt = { -40, 40 }
							ranges.bandOffset = { -2, 2 }
							ranges.cutAngle = { -90, 90 }
							ranges.gap = { 0, 4 }
							ranges.slide = { -3, 3 }
							ranges.cutFlash = { 0, 4 }
							ranges.rough = { 0, 3 }
							ranges.drips = { 0, 3 }
							ranges.spin = { -60, 60 }
							ranges.claws = { 1, 4 }
							ranges.clawSpacing = { 0, 0.6 }
							ranges.jag = { 0, 4 }
							ranges.shatter = { 0, 4 }
							ranges.crawl = { 0, 1 }
							ranges.distort = { 0, 4 }
							ranges.spot = { 0, 3 }
							ranges.reveal = { 0, 1 }
							for k, v in el.lettering do
								if ranges[k] then -- a number, or a curve over the frame's life: [[u, v], ...]
									seq(p .. ".lettering." .. k, v, num(ranges[k][1], ranges[k][2]))
								elseif k == "cut" or k == "band" or k == "cover" then
									if type(v) ~= "boolean" then
										err(p .. ".lettering." .. k, k .. ": true | false")
									end
								elseif k == "sub" then
									if type(v) ~= "string" or #v > 40 then
										err(
											p .. ".lettering.sub",
											"sub: the small line above the name, up to 40 characters"
										)
									end
								elseif k == "ghost" or k == "ghostFont" then
									if type(v) ~= "string" or #v > 60 then
										err(
											p .. ".lettering." .. k,
											k
												.. ": a short string (a kanji or a second word behind the band; the font family)"
										)
									end
								elseif k == "bandColor" or k == "cardColor" or k == "blood" then
									if v ~= "white" and v ~= "black" then
										color(p .. ".lettering." .. k, v)
									end
								else
									err(
										p .. ".lettering." .. tostring(k),
										"unknown lettering knob (skew cut stagger stretch squash offset band bandLines bandColor bandOffset sub ghost ghostFont split glint trail scale tilt cover cardColor cutAngle cutFlash gap slide rough drips blood spin claws clawSpacing jag shatter crawl distort spot reveal)"
									)
								end
							end
						end
					end
					if el.textPos ~= nil and el.textPos ~= "center" and el.textPos ~= "band" then
						err(
							p .. ".textPos",
							'textPos: "center" | "band" (the third away from the hit); else the word sits above the hit, or at textAt'
						)
					end
					if el.textFont ~= nil and (type(el.textFont) ~= "string" or #el.textFont > 60) then
						err(
							p .. ".textFont",
							"textFont: a font family name installed on the machine that bakes the plates (Chiller, Showcard Gothic, Stencil, Impact)"
						)
					end
				end
				if
					el.lines ~= nil
					and el.lines ~= "none"
					and el.lines ~= "fine"
					and el.lines ~= "bold"
					and el.lines ~= "both"
					and el.lines ~= "perspective"
					and el.lines ~= "cut"
				then
					texture(p .. ".lines", el.lines) -- a texture burst; fine | bold | both | perspective | cut are drawn
				end
				if el.camera ~= nil then -- the cut-in camera: a preset or { az, el, k, min, fov, roll, look }
					if type(el.camera) == "table" then
						for k, v in el.camera do
							if
								not (
									k == "az"
									or k == "el"
									or k == "k"
									or k == "min"
									or k == "fov"
									or k == "roll"
									or k == "look"
								)
							then
								err(
									p .. ".camera." .. tostring(k),
									"camera: closeup | low | wide | none, or { az, el, k, min, fov, roll, look }"
								)
							elseif not isNum(v) then
								err(p .. ".camera." .. tostring(k), "a number")
							end
						end
					elseif
						el.camera ~= "closeup"
						and el.camera ~= "low"
						and el.camera ~= "wide"
						and el.camera ~= "none"
						and el.camera ~= "cut"
						and el.camera ~= "subject"
					then
						err(
							p .. ".camera",
							"camera: closeup | low | wide | cut (square to the slash's arc) | subject (a close-up of the effect's own drawn shape) | none, or { az, el, k, min, fov, roll, look }"
						)
					end
				end
				if el.fill ~= nil then -- camera "subject": the share of the frame its subject fills
					num(0.3, 0.98)(p .. ".fill", el.fill)
				end
				if el.roll ~= nil then -- camera "subject": the dutch angle, degrees
					num(-45, 45)(p .. ".roll", el.roll)
				end
				if el.focus ~= nil then
					point(p .. ".focus", el.focus)
				end
				if el.subject ~= nil and el.subject ~= "actor" and el.subject ~= "all" then
					err(p .. ".subject", "subject: actor (the rig + flying debris) | all (rocks and walls too)")
				end
				num(0.2, 6)(p .. ".linesScale", el.linesScale or 1.6)
				num(0, 3)(p .. ".linesStrength", el.linesStrength or 1)
				num(0, 1)(p .. ".linesHole", el.linesHole or 0.08) -- the lines fade out this close to the focus (screen heights): the hit's core stays clean
				num(0, 4)(p .. ".exaggeration", el.exaggeration or 1) -- the master over the drawing: warp, grow, smear, splatter
				if el.draw ~= nil then -- the drawing stage (player; the engine frame is the plain version until the booth measures it)
					if type(el.draw) ~= "table" then
						err(
							p .. ".draw",
							"draw: { warp, grow, smear, outline, hatch, splatter, zoom, shake, flash, lineart, boil }"
						)
					else
						local ranges = {
							warp = { 0, 4 },
							grow = { 0, 4 },
							smear = { 0, 4 },
							outline = { 0, 4 },
							hatch = { 0, 1 },
							splatter = { 0, 4 },
							zoom = { 0, 0.3 },
							shake = { 0, 0.05 },
							flash = { 0, 1 },
							rim = { 0, 4 },
							soot = { 0, 4 },
							mass = { 0, 4 },
							wedge = { 0, 4 },
							star = { 0, 2 },
							void = { 0, 2 },
							crack = { 0, 2 },
							bolts = { 0, 3 },
							specks = { 0, 4 },
							smoke = { 0, 4 },
							slash = { 0, 4 }, -- impact frames v4: the slash's arc drawn as a brush stroke
							split = { 0, 4 }, -- the frame cut in two along it, the far side inverted
							slide = { 0, 0.3 }, -- that side slid along the cut (screen heights)
							cutSmear = { 0, 4 }, -- the energy smeared along the cut
							flare = { 0, 3 }, -- a Kanada light flare at the hit (straight lines + ghost rings)
							selective = { 0, 1 }, -- the world grey, the effect in its own colour
						}
						for k, v in el.draw do
							if ranges[k] then
								num(ranges[k][1], ranges[k][2])(p .. ".draw." .. k, v)
							elseif k == "lineart" or k == "boil" or k == "semantic" or k == "abstract" then
								if type(v) ~= "boolean" then
									err(p .. ".draw." .. k, k .. ": true | false")
								end
							else
								err(
									p .. ".draw." .. k,
									"unknown draw knob (warp grow smear outline hatch splatter zoom shake flash lineart boil rim soot mass wedge star specks smoke semantic abstract void crack bolts slash split slide cutSmear flare selective)"
								)
							end
						end
					end
				end
				if el.energy ~= nil then
					if type(el.energy) ~= "table" or #el.energy ~= 2 then
						err(
							p .. ".energy",
							"energy: [markThreshold, hotThreshold] in 0..1 (the effect's brightness that becomes an ink mark / the hot colour)"
						)
					else
						num(0, 1)(p .. ".energy[1]", el.energy[1])
						num(0, 1)(p .. ".energy[2]", el.energy[2])
					end
				end
			end
			if el.image ~= nil then -- a drawn plate over the whole screen (kit vision plate -> kit vfx import)
				texture(p .. ".image", el.image)
				num(0, 1)(p .. ".imageTransparency", el.imageTransparency or 0)
			end
			local maxLife = if el.style == "frame"
					or el.style == "comic"
					or el.style == "anime"
					or el.image ~= nil
				then 0.6
				else 0.3 -- a drawn frame may linger
			if isNum(life) and life > maxLife then
				err(
					p .. ".life",
					"an impact frame lasts a few frames: life <= 0.3 s (a drawn frame, style frame / image: <= 0.6 s)"
				)
			end
		elseif kind == "shake" then
			-- a key the stage never reads is an error (2026-10-23: a fov `amount` sat silently at 0 for a whole effect)
			-- `frequency` is a v2 key the v3 stage never read (the noise runs at a fixed rate): a warning, not an error,
			-- so the 2026-10-23 audit's 285 old layers stay valid while it shows
			if el.frequency ~= nil then
				warn(p .. ".frequency", "legacy `frequency` is not read: the shake runs at a fixed rate (drop the key)")
			end
			knownKeys(p, el, { amplitude = true, radius = true, kick = true, kickCurve = true, frequency = true })
			seq(p .. ".amplitude", el.amplitude or 1, num(0, 10))
			if el.kick ~= nil and not (type(el.kick) == "table" and isNum(el.kick[1]) and isNum(el.kick[2])) then
				err(p .. ".kick", "kick is [x, y]: degrees the picture jolts with the strike (x right, y up)")
			elseif el.kick ~= nil and (math.abs(el.kick[1]) > 20 or math.abs(el.kick[2]) > 20) then
				err(p .. ".kick", "a kick over 20 degrees throws the camera off the action: a bump is 1-6")
			end
			seq(p .. ".kickCurve", el.kickCurve, num(0, 1))
		elseif kind == "fov" then
			-- `fov` is the v2 name: the v3 stage reads `delta`, so a layer keyed `fov` has NEVER punched (150 layers in
			-- 78 presets at the 2026-10-23 audit) - flagged, not silently switched on (it would change judged looks)
			if el.fov ~= nil then
				warn(
					p .. ".fov",
					"legacy `fov`: the engine reads `delta` - this FOV punch never plays (rename it to delta to switch it on)"
				)
			end
			knownKeys(p, el, { delta = true, radius = true, fov = true })
			seq(p .. ".delta", el.delta or 0, num(-40, 40))
		elseif kind == "sound" then
			if type(el.sound) ~= "string" then
				err(p .. ".sound", "sound is the name of a kit sound (assets/sounds/<name>.json)")
			end
			ends = at
		elseif kind == "trail" then
			if el.target ~= nil and (type(el.target) ~= "string" or string.sub(el.target, 1, 1) ~= "@") then
				err(
					p .. ".target",
					'target is "@<anchor>" (a part the caller passes: the trail rides it), or use from / to'
				)
			end
			if el.target == nil then
				point(p .. ".from", el.from, true)
				point(p .. ".to", el.to, true)
			end
			if
				el.span ~= nil
				and not (type(el.span) == "table" and #el.span == 2 and isVec(el.span[1]) and isVec(el.span[2]))
			then
				err(p .. ".span", "span is two local offsets on the target part: [[x, y, z], [x, y, z]]")
			end
			range(p .. ".lifetime", el.lifetime, 0.01, 20)
			texture(p .. ".texture", el.texture)
			seq(p .. ".transparency", el.transparency, num(0, 1), 20)
			seq(p .. ".widthScale", el.widthScale, num(0, 100), 20)
			if el.mesh ~= nil and type(el.mesh) ~= "boolean" then
				err(
					p .. ".mesh",
					"mesh: true draws the trail as a ribbon of real geometry (VfxMesh.ribbon), false / absent = a Roblox Trail"
				)
			end
			if el.mesh == true and el.target == nil then
				err(p .. ".mesh", 'a mesh trail rides a part: target "@<anchor>" + span')
			end
			if el.surface ~= nil then
				num(0, 100)(p .. ".surface", el.surface)
			end
			if el.samples ~= nil then
				num(4, 120)(p .. ".samples", el.samples)
			end
			colorSeq(p .. ".color", el.color)
			num(0, 1000)(p .. ".brightness", el.brightness or 1)
			num(0, 1)(p .. ".lightEmission", el.lightEmission or 1)
			if
				el.textureMode ~= nil
				and el.textureMode ~= "Wrap"
				and el.textureMode ~= "Stretch"
				and el.textureMode ~= "Static"
			then
				err(p .. ".textureMode", "textureMode: Wrap | Stretch | Static")
			end
			ends = at + (if isNum(life) then life else 1) + rangeMax(el.lifetime or 0.5)
		elseif kind == "highlight" then
			if type(el.target) ~= "string" or string.sub(el.target, 1, 1) ~= "@" then
				err(p .. ".target", 'target is "@<anchor>" — the model or part the caller passes in (e.g. "@body")')
			end
			colorSeq(p .. ".fill", el.fill)
			colorSeq(p .. ".outline", el.outline)
			seq(p .. ".fillTransparency", el.fillTransparency, num(0, 1))
			seq(p .. ".outlineTransparency", el.outlineTransparency, num(0, 1))
			if el.depthMode ~= nil and el.depthMode ~= "Occluded" and el.depthMode ~= "AlwaysOnTop" then
				err(p .. ".depthMode", "depthMode: Occluded | AlwaysOnTop")
			end
		elseif kind == "glow" then
			if type(el.target) ~= "string" or string.sub(el.target, 1, 1) ~= "@" then
				err(p .. ".target", 'target is "@<anchor>" — a part the caller passes in (e.g. the blade)')
			end
			colorSeq(p .. ".color", el.color)
			seq(p .. ".transparency", el.transparency, num(0, 1))
			if el.material ~= nil and not MATERIALS[el.material] then
				err(
					p .. ".material",
					`"{tostring(el.material)}" is not a Roblox material (Neon, ForceField, Glass, ...)`
				)
			end
		end
		if mode ~= "attach" and ends > duration + 1e-6 then -- attach layers run until the effect is stopped
			err(
				p,
				`still running at {string.format("%.2f", ends)} s but the preset ends at {duration} s — it gets cut off; raise duration or shorten the layer`
			)
		end
	end
	local peak = 0
	for _, v in samples do
		peak = math.max(peak, v)
	end
	if peak > PARTICLES_ERROR then
		err(
			"layers",
			`~{math.floor(peak)} particles alive at the peak — keep it under {PARTICLES_ERROR} (lower rate / count / lifetime)`
		)
	elseif peak > PARTICLES_WARN then
		warn(
			"layers",
			`~{math.floor(peak)} particles alive at the peak — over {PARTICLES_WARN} drops frames on phones`
		)
	end
	return issues
end

return VfxValidate3

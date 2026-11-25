-- VfxCompose.luau — pure (Lune + Roblox): expands a version-3 preset's composition features into the plain layer
-- stack that VfxValidate3, VfxStage, the booth and the browser player consume. Nothing downstream knows about them.
--
--   beats     { "windup": 0.4, "chop": 2.6 }      every `at` (layers, hits, hitstop, use) may be a beat: "chop",
--                                                 "chop+0.2", "chop-0.1". Retime the whole effect from one table.
--   use       [ { "part": "slash_arc", "at": "chop", "as": "cut", "point": "tip" | [x, y, z], "scale": 1.5,
--                 "palette": { "core": "gold" }, "mute": ["dust"], "rot": 30 } ]
--             a reusable sub-effect (assets/effects/parts/<part>.json: palette, points, beats, layers, hits) copied
--             in: layer names "<as>.<name>", times shifted by `at`, its colours mapped onto the host palette
--             (`palette`: part colour -> host colour name or [r, g, b]; unmapped part colours join the host palette
--             as "<as>.<colour>"), its points offset to `point` and scaled by `scale` (sizes, widths, radii, spans,
--             speeds too), `mute` drops part layers by name. A part may name host points / "@anchors" directly.
--   variants  { "ice": { "palette": { "gold": [120, 200, 255] }, "scale": 0.8, "mute": ["beam_*"],
--                        "beats": { "chop": 2.2 }, "about": "..." } }
--             expand(preset, { variant = "ice" }) applies one before anything else (Vfx registers "<name>@ice").
--
--   VfxCompose.expand(preset, { variant = name?, parts = (name) -> part? }) -> (expanded, issues)
--   VfxCompose.partAsPreset(part) -> a stand-alone preset so a part can be validated on its own
-- `expanded` is a deep copy: `use` and `variants` are gone, `beats` stays (informational), every `at` is a number.
-- Issues are { path, message, severity = "error" } like VfxValidate's, so callers prepend them.
local VfxTech = require("./VfxTech")

local VfxCompose = {}

export type Issue = { path: string, message: string, severity: string }

local COLOR_FIELDS = {
	color = true,
	tint = true,
	paper = true,
	ink = true,
	accent = true,
	hot = true,
	mark = true,
	linesColor = true,
	textColor = true,
}
local POINT_FIELDS = { point = true, from = true, to = true, aim = true, focus = true, textAt = true }
-- lengths a part's `scale` multiplies (studs or studs/s); not angles, times, counts or rates
local LENGTH_FIELDS = {
	size = true,
	width = true,
	radius = true,
	span = true,
	speed = true,
	acceleration = true,
	range = true,
	scale = true,
	zOffset = true,
	textureLength = true,
}

local function isNum(v: any): boolean
	return type(v) == "number" and v == v
end

local function isVec(v: any): boolean
	return type(v) == "table" and #v == 3 and isNum(v[1]) and isNum(v[2]) and isNum(v[3])
end

local function deepCopy(v: any): any
	if type(v) ~= "table" then
		return v
	end
	local out = {}
	for k, x in v do
		out[k] = deepCopy(x)
	end
	return out
end

-- "beat", "beat+0.2", "beat-0.1" or a number -> seconds
local function resolveTime(v: any, beats: any, path: string, issues: { Issue }): number?
	if isNum(v) then
		return v
	end
	if type(v) ~= "string" then
		return nil
	end
	local name, sign, delta = string.match(v, "^%s*([%a_][%w_]*)%s*([%+%-]?)%s*([%d%.]*)%s*$")
	if not name then
		table.insert(issues, {
			path = path,
			message = `"{v}" is not a time: a number, a beat name, or "beat+0.2" / "beat-0.1"`,
			severity = "error",
		})
		return nil
	end
	local base = beats and beats[name]
	if not isNum(base) then
		table.insert(issues, {
			path = path,
			message = `unknown beat "{name}" — add it to beats: \{ "{name}": seconds \}`,
			severity = "error",
		})
		return nil
	end
	local d = if delta ~= "" then tonumber(delta) else 0
	if sign ~= "" and (d == nil or delta == "") then
		table.insert(
			issues,
			{ path = path, message = `"{v}": the offset after {sign} must be a number`, severity = "error" }
		)
		return nil
	end
	return base + (if sign == "-" then -(d or 0) else (d or 0))
end

-- a glob with `*` -> does the layer name match
local function globMatch(pattern: string, name: string): boolean
	if pattern == name then
		return true
	end
	if not string.find(pattern, "*", 1, true) then
		return false
	end
	local lua = "^" .. string.gsub(string.gsub(pattern, "[%^%$%(%)%%%.%[%]%+%-%?]", "%%%0"), "%*", ".*") .. "$"
	return string.match(name, lua) ~= nil
end

local function removeMuted(layers: { any }, mute: any, path: string, issues: { Issue }): { any }
	if mute == nil then
		return layers
	end
	if type(mute) ~= "table" then
		table.insert(
			issues,
			{ path = path, message = 'mute is a list of layer names (globs allowed: "beam_*")', severity = "error" }
		)
		return layers
	end
	local kept = {}
	for _, el in layers do
		local drop = false
		for _, m in mute do
			if type(m) == "string" and type(el.name) == "string" and globMatch(m, el.name) then
				drop = true
				break
			end
		end
		if not drop then
			table.insert(kept, el)
		end
	end
	return kept
end

-- multiply every length in a value (number | [x, y, z] | sequence of them) by s
local function scaleValue(v: any, s: number): any
	if isNum(v) then
		return v * s
	end
	if type(v) == "table" and #v > 0 and isNum(v[1]) then -- [x, y, z] or a [min, max] range
		local out = {}
		for i, x in v do
			out[i] = if isNum(x) then x * s else x
		end
		return out
	end
	if type(v) == "table" and type(v[1]) == "table" and #v[1] == 2 and isNum(v[1][1]) then -- [[u, value], ...]
		local out = {}
		for i, kp in v do
			out[i] = { kp[1], scaleValue(kp[2], s) }
		end
		return out
	end
	if type(v) == "table" and v.ease ~= nil and (v.from ~= nil or v.to ~= nil) then -- { ease, from, to, keys? }
		local out = table.clone(v)
		out.from = if v.from ~= nil then scaleValue(v.from, s) else nil
		out.to = if v.to ~= nil then scaleValue(v.to, s) else nil
		return out
	end
	return v
end

-- walk the colour fields of one layer: a colour is a palette name, [r, g, b] or a sequence of those
local function mapColors(el: any, map: (string) -> any)
	for k, v in el do
		if COLOR_FIELDS[k] then
			if type(v) == "string" then
				el[k] = map(v)
			elseif type(v) == "table" and type(v[1]) == "table" and #v[1] == 2 and isNum(v[1][1]) then
				for _, kp in v do
					if type(kp[2]) == "string" then
						kp[2] = map(kp[2])
					end
				end
			end
		elseif type(v) == "table" and not isVec(v) and k ~= "layers" then
			mapColors(v, map)
		end
	end
end

local function mapPoints(el: any, map: (any) -> any)
	for k, v in el do
		if POINT_FIELDS[k] then
			el[k] = map(v)
		elseif k == "span" and type(v) == "table" and isVec(v[1]) and isVec(v[2]) then
			el[k] = { map(v[1]), map(v[2]) }
		end
	end
end

local function scaleLengths(el: any, s: number)
	for k, v in el do
		if LENGTH_FIELDS[k] and k ~= "span" then
			el[k] = scaleValue(v, s)
		end
	end
	if type(el.shape) == "table" and el.shape.size ~= nil then -- an emitter volume
		el.shape.size = scaleValue(el.shape.size, s)
	end
	-- a mesh's `params` (radius, width, length ...) build it at scale 1 and its `scale` multiplies the whole mesh about its
	-- point: a mesh with no `scale` gets one (2026-10-24: a shock_ring used at 0.42 kept its full 26-stud crest)
	if el.kind == "mesh" and el.scale == nil then
		el.scale = { s, s, s }
	end
	-- a Roblox light reaches 60 studs at most (the engine's own cap, and the validator's): a scaled-up stack keeps it
	if el.kind == "light" and isNum(el.range) and el.range > 60 then
		el.range = 60
	end
end

-- a part on its own, as a preset the validator can check (duration = the last layer's end, 1 s margin)
function VfxCompose.partAsPreset(part: any): any
	local preset = deepCopy(part)
	preset.part = nil
	preset.version = 3
	preset.mode = preset.mode or "burst"
	local expanded, _ = VfxCompose.expand(preset, {})
	if not isNum(expanded.duration) then
		local last = 1
		for _, el in expanded.layers or {} do
			local at = if isNum(el.at) then el.at else 0
			local life = if isNum(el.life) then el.life else 1
			local for_ = if isNum(el["for"]) then el["for"] else 0
			local lt = el.lifetime -- a particle's own life: a number or [min, max]
			local lifetime = if isNum(lt) then lt elseif type(lt) == "table" and isNum(lt[2]) then lt[2] else 0
			last = math.max(last, at + for_ + life + lifetime + 1)
		end
		expanded.duration = math.min(last, 30)
	end
	return expanded
end

-- one `use` entry -> layers appended to the host (the host's palette / points / hits / hitstop grow)
local function applyUse(host: any, i: number, u: any, opts: any, issues: { Issue })
	local p = `use[{i}]`
	if type(u) ~= "table" or type(u.part) ~= "string" then
		table.insert(issues, {
			path = p,
			message = 'a use is { "part": "<name>", "at": time, ... } (assets/effects/parts/<name>.json)',
			severity = "error",
		})
		return
	end
	local part = if type(opts.parts) == "function" then opts.parts(u.part) else nil
	if type(part) ~= "table" or type(part.layers) ~= "table" then
		table.insert(issues, {
			path = p .. ".part",
			message = `unknown part "{u.part}" — assets/effects/parts/{u.part}.json (lune run kit new vfx {u.part} --part)`,
			severity = "error",
		})
		return
	end
	part = deepCopy(part)
	local prefix = if type(u.as) == "string" and u.as ~= "" then u.as else `{u.part}{i}`
	local at = resolveTime(if u.at == nil then 0 else u.at, host.beats, p .. ".at", issues) or 0
	local scale = if isNum(u.scale) then u.scale else 1
	if scale <= 0 then
		table.insert(issues, { path = p .. ".scale", message = "scale must be > 0", severity = "error" })
		scale = 1
	end
	-- where the part's origin lands in the host: [x, y, z] or a host point name
	local origin = { 0, 0, 0 }
	if isVec(u.point) then
		origin = u.point
	elseif type(u.point) == "string" then
		local hp = host.points and host.points[u.point]
		if isVec(hp) then
			origin = hp
		else
			table.insert(issues, {
				path = p .. ".point",
				message = `point "{u.point}" is not a host point (use [x, y, z] or a name from points; a part's own layers may say "@anchor")`,
				severity = "error",
			})
		end
	elseif u.point ~= nil then
		table.insert(
			issues,
			{ path = p .. ".point", message = "point is [x, y, z] or a host point name", severity = "error" }
		)
	end
	-- the part's own beats first (relative times inside the part), then the shift
	local partBeats = if type(part.beats) == "table" then part.beats else {}
	-- `slow` on a use plays the part slower (2 = twice as long): its times and lives stretch, the shape does not
	local slow = if isNum(u.slow) and u.slow > 0 then u.slow else 1
	local function partTime(v: any, path: string): number
		local t = resolveTime(if v == nil then 0 else v, partBeats, path, issues) or 0
		return t * slow + at
	end
	-- colours: the use's map first, then the part's palette (copied in prefixed), then the host's own names
	local colorMap = if type(u.palette) == "table" then u.palette else {}
	host.palette = host.palette or {}
	local function mapColor(name: string): any
		local m = colorMap[name]
		if m ~= nil then
			return m
		end
		if type(part.palette) == "table" and part.palette[name] ~= nil then
			local key = prefix .. "." .. name
			host.palette[key] = part.palette[name]
			return key
		end
		return name -- a host palette name (or an error the validator reports)
	end
	-- points: the part's points become "<as>.<name>" in the host, moved to the origin and scaled
	host.points = host.points or {}
	local function place(v: any): any
		if isVec(v) then
			return { v[1] * scale + origin[1], v[2] * scale + origin[2], v[3] * scale + origin[3] }
		end
		return v
	end
	if type(part.points) == "table" then
		for name, pt in part.points do
			host.points[prefix .. "." .. name] = place(pt)
		end
	end
	local function mapPoint(v: any): any
		if type(v) == "string" and type(part.points) == "table" and part.points[v] ~= nil then
			return prefix .. "." .. v
		end
		if type(v) == "string" then
			return v -- "target", "@anchor" or a host point: pass through
		end
		return place(v)
	end
	local layers = removeMuted(part.layers, u.mute, p .. ".mute", issues)
	for j, el in layers do
		if type(el) ~= "table" then
			continue
		end
		local lp = `{p}.layers[{j}]`
		el.name = prefix .. "." .. tostring(el.name or j)
		-- the scene beat this use builds (an authoring tag: the kit's scope and method gates read it; the game does
		-- not) passes to the part's layers that say none of their own
		if u.beat ~= nil and el.beat == nil then
			el.beat = u.beat
		end
		el.at = partTime(el.at, lp .. ".at")
		if slow ~= 1 and isNum(el.life) then
			el.life = el.life * slow
		end
		if el.hitstop ~= nil and type(el.hitstop) == "table" and el.hitstop.at ~= nil then
			el.hitstop.at = partTime(el.hitstop.at, lp .. ".hitstop.at")
		end
		mapColors(el, mapColor)
		if el.text ~= nil and type(u.text) == "string" then -- the attack's name, from the use (an attack_call part)
			el.text = u.text
		end
		if el.text ~= nil and type(u.textFont) == "string" then
			el.textFont = u.textFont
		end
		if el.text ~= nil and type(u.sub) == "string" then -- the small line above the name
			el.lettering = if type(el.lettering) == "table" then el.lettering else {}
			el.lettering.sub = u.sub
		end
		if el.text ~= nil and type(u.ghost) == "string" then -- the ghost word behind the band
			el.lettering = if type(el.lettering) == "table" then el.lettering else {}
			el.lettering.ghost = u.ghost
		end
		if scale ~= 1 then
			scaleLengths(el, scale)
		end
		mapPoints(el, mapPoint)
		if isNum(u.rot) and u.rot ~= 0 then
			el.rot = (if isNum(el.rot) then el.rot else 0) + u.rot
		end
		table.insert(host.layers, el)
	end
	if type(part.hits) == "table" then
		host.hits = host.hits or {}
		for k, h in part.hits do
			table.insert(host.hits, partTime(h, `{p}.hits[{k}]`))
		end
	end
	if type(part.hitstop) == "table" then
		host.hitstop = host.hitstop or {}
		for k, hs in part.hitstop do
			if type(hs) == "table" then
				local copy = deepCopy(hs)
				copy.at = partTime(hs.at, `{p}.hitstop[{k}].at`)
				table.insert(host.hitstop, copy)
			end
		end
	end
end

function VfxCompose.expand(preset: any, opts: any?): (any, { Issue })
	local o = opts or {}
	local issues: { Issue } = {}
	if type(preset) ~= "table" then
		return preset, issues
	end
	local out = deepCopy(preset)
	out.layers = if type(out.layers) == "table" then out.layers else {}
	-- 1. the variant: palette / beats merged over the host's, scale, mute, about
	if o.variant ~= nil then
		local v = type(out.variants) == "table" and out.variants[o.variant]
		if type(v) ~= "table" then
			table.insert(issues, {
				path = "variants",
				message = `no variant "{tostring(o.variant)}" (variants: \{ "<name>": \{ palette, beats, scale, mute, about \} \})`,
				severity = "error",
			})
		else
			if type(v.palette) == "table" then
				out.palette = out.palette or {}
				for k, c in v.palette do
					out.palette[k] = c
				end
			end
			if type(v.beats) == "table" then
				out.beats = out.beats or {}
				for k, t in v.beats do
					out.beats[k] = t
				end
			end
			if type(v.about) == "string" then
				out.about = v.about
			end
			out.variantScale = if isNum(v.scale) then v.scale else nil
			out.variantMute = v.mute
		end
	end
	out.variants = nil
	-- 1b. the overlay (kit vfx evolve, mission 02-vfx 5.6): a picked look over the host - scale and mute ride the
	-- variant machinery (sizes AND positions), time and saturation apply once the clock is resolved (see the end)
	local ov = if type(out.overlay) == "table" then out.overlay else nil
	if ov then
		if isNum(ov.scale) then
			out.variantScale = (out.variantScale or 1) * ov.scale
		end
		if type(ov.mute) == "table" then
			local m = {}
			for _, x in (if type(out.variantMute) == "table" then out.variantMute else {}) :: { any } do
				table.insert(m, x)
			end
			for _, x in ov.mute do
				table.insert(m, x)
			end
			out.variantMute = m
		end
	end
	out.overlay = nil
	if out.beats ~= nil and type(out.beats) ~= "table" then
		table.insert(issues, { path = "beats", message = 'beats is { "<name>": seconds }', severity = "error" })
		out.beats = nil
	end
	if type(out.beats) == "table" then
		for k, t in out.beats do
			if not isNum(t) or t < 0 then
				table.insert(
					issues,
					{ path = `beats.{k}`, message = "a beat is a time in seconds >= 0", severity = "error" }
				)
			end
		end
	end
	-- 2. sub-effects (their layers join the host before the host's own times resolve, so part layers can also say
	--    host beats: a part's `at` is relative to the use's `at`, which may itself be a beat)
	if out.use ~= nil then
		if type(out.use) ~= "table" then
			table.insert(issues, {
				path = "use",
				message = "use is a list of { part, at, as, point, scale, palette, mute }",
				severity = "error",
			})
		else
			for i, u in out.use do
				applyUse(out, i, u, o, issues)
			end
		end
		out.use = nil
	end
	-- 3. beats -> numbers everywhere
	local beats = out.beats
	for i, el in out.layers do
		if type(el) == "table" and type(el.at) == "string" then
			el.at = resolveTime(el.at, beats, `layers[{i}].at`, issues) or 0
		end
	end
	if type(out.hits) == "table" then
		for i, h in out.hits do
			if type(h) == "string" then
				out.hits[i] = resolveTime(h, beats, `hits[{i}]`, issues) or 0
			end
		end
	end
	if type(out.hitstop) == "table" then
		for i, hs in out.hitstop do
			if type(hs) == "table" and type(hs.at) == "string" then
				hs.at = resolveTime(hs.at, beats, `hitstop[{i}].at`, issues) or 0
			end
		end
	end
	if type(out.timewarp) == "table" then -- beat names in the timewarp keys
		for i, kv in out.timewarp do
			if type(kv) == "table" and kv[1] ~= nil then
				kv[1] = resolveTime(kv[1], beats, `timewarp[{i}]`, issues) or 0
			end
		end
	end
	-- 3b. the techniques (VfxTech: ease, echo, bursts, flicker, rim, boil, path, onDeath) become plain layers
	for _, issue in VfxTech.expand(out) do
		table.insert(issues, issue)
	end
	-- 4. the variant's scale and mutes apply to the whole expanded stack
	if isNum(out.variantScale) and out.variantScale > 0 and out.variantScale ~= 1 then
		local s = out.variantScale
		for _, el in out.layers do
			if type(el) == "table" then
				scaleLengths(el, s)
				mapPoints(el, function(v)
					return if isVec(v) then { v[1] * s, v[2] * s, v[3] * s } else v
				end)
			end
		end
		if type(out.points) == "table" then
			for k, pt in out.points do
				if isVec(pt) then
					out.points[k] = { pt[1] * s, pt[2] * s, pt[3] * s }
				end
			end
		end
	end
	if out.variantMute ~= nil then
		out.layers = removeMuted(out.layers, out.variantMute, "variants.mute", issues)
	end
	-- baked impact frames (kit vfx play --frames -> assets/effects/frames/<preset>.json): in the game every frame
	-- layer shows its drawn plate instead of the plain fog / Highlight frame (the viewer keeps drawing live)
	if type(o.frames) == "table" and type(out.layers) == "table" then
		for _, el in out.layers do
			if
				type(el) == "table"
				and el.kind == "impact"
				and (el.style == "frame" or el.style == "comic" or el.style == "anime")
				and type(o.frames[el.name]) == "string"
			then
				el.image = o.frames[el.name]
				el.style = nil
				el.draw = nil
			end
		end
	end
	if ov then
		VfxCompose.overlayClockAndColour(out, ov)
	end
	out.variantScale = nil
	out.variantMute = nil
	return out, issues
end

-- the overlay's time (x every time: at, lifetime, life, duration, hit-stops) and saturate (+- the saturation of every
-- colour: palette and layer colours, keyframes too) on an EXPANDED preset (every `at` a number)
function VfxCompose.overlayClockAndColour(out: any, ov: any)
	local function mul(v: any, k: number): any -- a number, a [min, max] range or [[t, value], ...] keyframes
		if isNum(v) then
			return v * k
		elseif type(v) == "table" then
			local o = {}
			for i, x in v do
				if type(x) == "table" and #x == 2 and isNum(x[1]) then
					o[i] = { x[1], mul(x[2], k) } -- a keyframe's time is the layer's own 0..1 life: it stays
				else
					o[i] = mul(x, k)
				end
			end
			return o
		end
		return v
	end
	local function sat(c: any, d: number): any
		if type(c) == "table" and #c == 3 and isNum(c[1]) and isNum(c[2]) and isNum(c[3]) then
			-- pure Luau (this module also runs in Lune, which has no Color3): scale the chroma about the value
			local mx = math.max(c[1], c[2], c[3])
			local s = if mx > 0 then (mx - math.min(c[1], c[2], c[3])) / mx else 0
			local s2 = math.clamp(s * (1 + d), 0, 1)
			local k = if s > 0 then s2 / s else 1
			local function ch(x: number): number
				return math.clamp(math.round(mx - (mx - x) * k), 0, 255)
			end
			return { ch(c[1]), ch(c[2]), ch(c[3]) }
		elseif type(c) == "table" then
			local o = {}
			for i, x in c do
				o[i] = if type(x) == "table" and #x == 2 and isNum(x[1]) then { x[1], sat(x[2], d) } else sat(x, d)
			end
			return o
		end
		return c
	end
	local t, d = ov.time, ov.saturate
	for _, el in (if type(out.layers) == "table" then out.layers else {}) :: { any } do
		if type(el) == "table" then
			if isNum(t) then
				if isNum(el.at) then
					el.at *= t
				end
				el.lifetime = mul(el.lifetime, t)
				el.life = mul(el.life, t)
			end
			if isNum(d) then
				el.color = sat(el.color, d)
			end
		end
	end
	if isNum(t) then
		out.duration = (if isNum(out.duration) then out.duration else 1) * t
		for _, h in (if type(out.hitstop) == "table" then out.hitstop else {}) :: { any } do
			if type(h) == "table" and isNum(h.at) then
				h.at *= t
			end
		end
	end
	if isNum(d) and type(out.palette) == "table" then
		for k, c in out.palette do
			out.palette[k] = sat(c, d)
		end
	end
end

-- the variant names a preset declares (so loaders can register "<name>@<variant>")
function VfxCompose.variants(preset: any): { string }
	local names = {}
	if type(preset) == "table" and type(preset.variants) == "table" then
		for k in preset.variants do
			if type(k) == "string" then
				table.insert(names, k)
			end
		end
		table.sort(names)
	end
	return names
end

return VfxCompose

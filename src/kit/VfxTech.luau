-- VfxTech.luau — pure (Lune + Roblox): the pro techniques (board/plans/archive/aaa-vfx-research.md, section 7) written as layer
-- KEYS and expanded into the plain layer stack, so the game (VfxStage), the browser player, the validator and the cost
-- line all get them without knowing they exist. Called by VfxCompose.expand once every `at` is a number.
--
--   ease     any curve field may be { "ease": "backOut", "from": a, "to": b, "keys": 12, "over": [u0, u1] }
--            -> keyframes. a / b: numbers, [x, y, z] or colours. Eases: linear quadIn quadOut quadInOut cubicOut
--            expoOut expoIn backOut backIn elasticOut bounceOut snap anticipate settle
--   echo     (mesh) { "count": 4, "lag": 0.035, "fade": 0.45, "shrink": 0.97 } -> afterimages: N copies replaying the
--            mesh `lag` s apart, each fainter (x (1 - fade)) and smaller (x shrink)
--   bursts   (sprite, debris) { "count": 4, "tilt": [20, 70], "cone": 22, "stagger": 0.025, "seed": 7 } -> the
--            emission split into N cones at random tilts (debris and sparks never fly as one even sphere)
--   flicker  (light, mesh, sprite-less) { "amount": 0.35, "rate": 14, "field": "brightness", "seed": 3 } -> the
--            field's curve x (1 + amount * smooth noise), `rate` wobbles a second (living fire)
--   rim      (mesh) { "color": [..], "scale": 1.06, "transparency": 0.35 } -> a ForceField shell round the mesh (an
--            energy edge that glows at grazing angles)
--   boil     (mesh) { "texture": "...", "uvScroll": [u, v], "scale": 1.02, "transparency": .., "color": .. } -> a
--            second shell with its own texture scrolling another way (two noises crossing = boiling energy / fire)
--   path     (mesh) { "points": [p0, p1, p2, p3?], "keys": 16, "ease": "linear" } -> a Bézier `move` (offsets in the
--            layer's frame, studs); (sprite) the same curve walked by short emitter windows (`segments`, default 8)
--            - a sprite emitter cannot move, so the emission point hops along the curve
--   haze     (mesh) { "scale": 1.15, "strength": 0.5, "wobble": [amp, freq, speed] } -> a wobbling Glass shell, strength
--            0..1 = 0.99..0.96 transparent: heat shimmer (Roblox Glass refracts the OPAQUE world behind it - from
--            quality level 16 of 21 up, looked at in Studio 2026-11-15; below that it is plain see-through)
--   onDeath  (sprite) { ...sprite fields..., "ratio": 1 } -> a second sprite layer where the first one's particles die
--            (sub-emitter: each spark ends in a puff). Roblox has no particle events: the children are emitted over
--            the parents' death window, in the shell their speed carried them to
--
--   VfxTech.expand(preset) -> issues   (edits preset.layers in place; preset is an expanded copy)
local VfxTech = {}

type Issue = { path: string, message: string, severity: string }

local function isNum(v: any): boolean
	return type(v) == "number" and v == v
end

local function isVec(v: any): boolean
	return type(v) == "table" and isNum(v[1]) and isNum(v[2]) and isNum(v[3]) and v[4] == nil
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

local function round(x: number, d: number?): number
	local m = 10 ^ (d or 3)
	return math.floor(x * m + 0.5) / m
end

-- ---------------------------------------------------------------- easing
local C1 = 1.70158
local EASES: { [string]: (number) -> number } = {
	linear = function(t)
		return t
	end,
	quadIn = function(t)
		return t * t
	end,
	quadOut = function(t)
		return 1 - (1 - t) * (1 - t)
	end,
	quadInOut = function(t)
		return if t < 0.5 then 2 * t * t else 1 - (-2 * t + 2) ^ 2 / 2
	end,
	cubicOut = function(t)
		return 1 - (1 - t) ^ 3
	end,
	expoOut = function(t)
		return if t >= 1 then 1 else 1 - 2 ^ (-10 * t)
	end,
	expoIn = function(t)
		return if t <= 0 then 0 else 2 ^ (10 * t - 10)
	end,
	backOut = function(t) -- overshoot, then settle
		return 1 + (C1 + 1) * (t - 1) ^ 3 + C1 * (t - 1) ^ 2
	end,
	backIn = function(t) -- a dip back before going
		return (C1 + 1) * t ^ 3 - C1 * t * t
	end,
	elasticOut = function(t)
		if t <= 0 or t >= 1 then
			return t
		end
		return 2 ^ (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1
	end,
	bounceOut = function(t)
		local n, d = 7.5625, 2.75
		if t < 1 / d then
			return n * t * t
		elseif t < 2 / d then
			t -= 1.5 / d
			return n * t * t + 0.75
		elseif t < 2.5 / d then
			t -= 2.25 / d
			return n * t * t + 0.9375
		end
		t -= 2.625 / d
		return n * t * t + 0.984375
	end,
	snap = function(t) -- the anime snap: almost all of it in the first fifth
		return if t >= 1 then 1 else 1 - 2 ^ (-18 * t)
	end,
	anticipate = function(t) -- a clear wind-back (~15 %) then a fast commit
		local s = 2.6
		return (s + 1) * t ^ 3 - s * t * t
	end,
	settle = function(t) -- overshoot ~12 %, one damped bounce back
		if t >= 1 then
			return 1
		end
		return 1 - math.exp(-7 * t) * math.cos(9 * t)
	end,
}
VfxTech.EASES = EASES

local function lerpValue(a: any, b: any, k: number): any
	if isNum(a) and isNum(b) then
		return a + (b - a) * k
	end
	if type(a) == "table" and type(b) == "table" and #a == #b then
		local out = {}
		for i = 1, #a do
			out[i] = lerpValue(a[i], b[i], k)
		end
		return out
	end
	return if k < 0.5 then a else b
end

local function roundValue(v: any, isColour: boolean): any
	if isNum(v) then
		return if isColour then math.clamp(math.floor(v + 0.5), 0, 255) else round(v)
	end
	if type(v) == "table" then
		local out = {}
		for i, x in v do
			out[i] = roundValue(x, isColour)
		end
		return out
	end
	return v
end

-- { ease, from, to, keys, over } -> [[u, value], ...]
function VfxTech.easeKeys(spec: any, field: string?): (any?, string?)
	local f = EASES[spec.ease]
	if not f then
		local names = {}
		for k in EASES do
			table.insert(names, k)
		end
		table.sort(names)
		return nil, `unknown ease "{tostring(spec.ease)}" ({table.concat(names, " ")})`
	end
	if spec.from == nil or spec.to == nil then
		return nil, "an ease needs from and to"
	end
	local n = math.clamp(math.floor(if isNum(spec.keys) then spec.keys else 12), 2, 40)
	local over = if type(spec.over) == "table"
			and isNum(spec.over[1])
			and isNum(spec.over[2])
		then spec.over
		else { 0, 1 }
	local u0, u1 = math.clamp(over[1], 0, 1), math.clamp(over[2], 0, 1)
	local colour = field == "color" or field == "tint"
	local keys = {}
	if u0 > 0 then
		table.insert(keys, { 0, roundValue(spec.from, colour) })
	end
	for i = 0, n - 1 do
		local t = i / (n - 1)
		table.insert(keys, { round(u0 + (u1 - u0) * t), roundValue(lerpValue(spec.from, spec.to, f(t)), colour) })
	end
	if u1 < 1 then
		table.insert(keys, { 1, roundValue(spec.to, colour) })
	end
	return keys
end

-- ---------------------------------------------------------------- noise (deterministic, smooth)
local function hash(i: number, seed: number): number
	local x = math.sin(i * 127.1 + seed * 311.7) * 43758.5453
	return x - math.floor(x)
end

local function smoothNoise(x: number, seed: number): number -- -1 .. 1
	local i = math.floor(x)
	local f = x - i
	local a, b = hash(i, seed), hash(i + 1, seed)
	local s = f * f * (3 - 2 * f)
	return (a + (b - a) * s) * 2 - 1
end

local function seedOf(name: any, given: any): number
	if isNum(given) then
		return given
	end
	local h = 7
	for i = 1, #tostring(name) do
		h = (h * 31 + string.byte(tostring(name), i)) % 100003
	end
	return h
end

local function rng(seed: number): () -> number
	local s = seed % 2147483647
	if s <= 0 then
		s += 2147483646
	end
	return function()
		s = (s * 16807) % 2147483647
		return (s - 1) / 2147483646
	end
end

local function numAt(v: any, u: number, default: number): number
	if v == nil then
		return default
	end
	if isNum(v) then
		return v
	end
	if type(v) ~= "table" or type(v[1]) ~= "table" then
		return default
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

local function maxOf(v: any): number
	if isNum(v) then
		return v
	end
	if type(v) == "table" and isNum(v[2]) then
		return v[2]
	end
	return if type(v) == "table" and isNum(v[1]) then v[1] else 0
end

local function minOf(v: any): number
	if isNum(v) then
		return v
	end
	return if type(v) == "table" and isNum(v[1]) then v[1] else 0
end

-- ---------------------------------------------------------------- Bézier
local function bezier(pts: { any }, t: number): { number }
	local work = {}
	for i, p in pts do
		work[i] = { p[1], p[2], p[3] }
	end
	for level = #work - 1, 1, -1 do
		for i = 1, level do
			local a, b = work[i], work[i + 1]
			work[i] = { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
		end
	end
	return work[1]
end

-- ---------------------------------------------------------------- the techniques
local MESH_ONLY = { echo = true, rim = true, boil = true, haze = true }
local TECH_KEYS = { echo = true, rim = true, boil = true, bursts = true, flicker = true, path = true, onDeath = true }

local function scaleCurve(v: any, k: number): any
	if v == nil then
		return k
	end
	if isNum(v) then
		return v * k
	end
	if isVec(v) then
		return { v[1] * k, v[2] * k, v[3] * k }
	end
	if type(v) == "table" and type(v[1]) == "table" then
		local out = {}
		for i, kv in v do
			out[i] = { kv[1], scaleCurve(kv[2], k) }
		end
		return out
	end
	return v
end

local function fadeCurve(v: any, keep: number): any -- transparency t -> 1 - (1 - t) * keep
	if v == nil then
		return round(1 - keep)
	end
	if isNum(v) then
		return round(1 - (1 - v) * keep)
	end
	if type(v) == "table" and type(v[1]) == "table" then
		local out = {}
		for i, kv in v do
			out[i] = { kv[1], round(1 - (1 - kv[2]) * keep) }
		end
		return out
	end
	return v
end

local function shellOf(el: any, suffix: string, k: number): any
	local c = deepCopy(el)
	c.name = el.name .. suffix
	c.scale = scaleCurve(el.scale, k)
	c.echo, c.rim, c.boil, c.flicker, c.path = nil, nil, nil, nil, nil
	c.outline, c.outlineWidth, c.toon = nil, nil, nil
	return c
end

function VfxTech.expand(preset: any): { Issue }
	local issues: { Issue } = {}
	if type(preset) ~= "table" or type(preset.layers) ~= "table" then
		return issues
	end
	local function err(path: string, message: string)
		table.insert(issues, { path = path, message = message, severity = "error" })
	end
	local out = {}
	for i, el in preset.layers do
		if type(el) ~= "table" then
			table.insert(out, el)
			continue
		end
		local p = `layers[{i}]({tostring(el.name)})`
		-- ease: any field written as { ease, from, to } (a technique's own `ease`, e.g. path.ease, is not a curve)
		for field, v in el do
			if not TECH_KEYS[field] and type(v) == "table" and type(v.ease) == "string" then
				local keys, why = VfxTech.easeKeys(v, field)
				if keys then
					el[field] = keys
				else
					err(`{p}.{field}`, why or "bad ease")
					el[field] = nil
				end
			end
		end
		-- lit variants: the default texture (what a server-side or camera-less stage shows) is the top-lit one
		if type(el.views) == "table" and el.texture == nil then -- impostors: the default is the 0-degree view
			el.texture = el.views["0"] or el.views[0]
		end
		if type(el.lit) == "table" and el.texture == nil then
			el.texture = el.lit.top or el.lit.left or el.lit.right or el.lit.front or el.lit.back
		end
		for key in MESH_ONLY do
			if el[key] ~= nil and el.kind ~= "mesh" then
				err(`{p}.{key}`, `{key} is a mesh technique (this layer is a {tostring(el.kind)})`)
				el[key] = nil
			end
		end
		local extra = {}
		local consumed = false
		-- flicker
		local fl = el.flicker
		if fl ~= nil then
			el.flicker = nil
			if type(fl) ~= "table" then
				err(`{p}.flicker`, "flicker is { amount, rate, field, seed }")
			elseif el.kind ~= "light" and el.kind ~= "mesh" and el.kind ~= "glow" then
				err(
					`{p}.flicker`,
					"flicker drives a light, mesh or glow curve (sprites are NumberSequences: 20 keys max)"
				)
			else
				local field = if type(fl.field) == "string" then fl.field else "brightness"
				local life = if isNum(el.life) then el.life else 1
				local rate = if isNum(fl.rate) then math.max(fl.rate, 0.5) else 12
				local amount = if isNum(fl.amount) then math.clamp(fl.amount, 0, 1) else 0.3
				local n = math.clamp(math.ceil(life * rate * 2) + 1, 3, 120)
				local seed = seedOf(el.name, fl.seed)
				local base = el[field]
				local keys = {}
				for k = 0, n - 1 do
					local u = k / (n - 1)
					local wob = 1 + amount * smoothNoise(u * life * rate, seed)
					table.insert(keys, { round(u), round(numAt(base, u, 1) * wob) })
				end
				el[field] = keys
			end
		end
		-- path
		local pa = el.path
		if pa ~= nil then
			el.path = nil
			local pts = type(pa) == "table" and pa.points
			local okPts = type(pts) == "table" and #pts >= 2 and #pts <= 6
			if okPts then
				for _, q in pts do
					okPts = okPts and isVec(q)
				end
			end
			if not okPts then
				err(`{p}.path`, "path is { points: 2-6 [x, y, z] (offsets in studs), keys?, ease?, segments? }")
			elseif el.kind == "mesh" then
				if el.move ~= nil then
					err(`{p}.path`, "a mesh has a path OR a move, not both")
				else
					local n = math.clamp(math.floor(if isNum(pa.keys) then pa.keys else 16), 2, 60)
					local f = EASES[pa.ease or "linear"] or EASES.linear
					local mv: { any } = {}
					for k = 0, n - 1 do
						local u = k / (n - 1)
						local b = bezier(pts, f(u))
						local key: { any } = { round(u), { round(b[1], 2), round(b[2], 2), round(b[3], 2) } }
						table.insert(mv, key)
					end
					el.move = mv
				end
			elseif el.kind == "sprite" then
				if not isVec(el.point) then
					err(`{p}.path`, "a sprite path needs a [x, y, z] point (the curve is added to it)")
				else
					local dur = if isNum(el["for"]) then el["for"] else 0.5
					local segs = math.clamp(math.floor(if isNum(pa.segments) then pa.segments else 8), 2, 30)
					local f = EASES[pa.ease or "linear"] or EASES.linear
					local w = dur / segs
					for k = 0, segs - 1 do
						local c = deepCopy(el)
						c.name = `{el.name}_p{k + 1}`
						c.at = round((el.at or 0) + k * w)
						c["for"] = round(w)
						local b = bezier(pts, f((k + 0.5) / segs))
						c.point =
							{ round(el.point[1] + b[1], 2), round(el.point[2] + b[2], 2), round(el.point[3] + b[3], 2) }
						if isNum(el.count) then
							c.count = math.max(1, math.ceil(el.count / segs))
						end
						table.insert(extra, c)
					end
					consumed = true
				end
			else
				err(`{p}.path`, "path moves a mesh or walks a sprite emitter")
			end
		end
		if consumed then
			for _, c in extra do
				table.insert(out, c)
			end
			continue
		end
		-- onDeath (sub-emitter)
		local od = el.onDeath
		if od ~= nil then
			el.onDeath = nil
			if type(od) ~= "table" or el.kind ~= "sprite" then
				err(`{p}.onDeath`, "onDeath { ...sprite fields, ratio } follows a sprite layer")
			else
				local lo, hi = minOf(el.lifetime or 1), maxOf(el.lifetime or 1)
				local reach = maxOf(el.speed or 0) * (lo + hi) / 2 * (if isNum(el.drag) and el.drag > 0 then 0.5 else 1)
				local c = deepCopy(el)
				for k, v in od do
					c[k] = deepCopy(v)
				end
				c.name = if type(od.name) == "string" then od.name else el.name .. "_death"
				c.ratio = nil
				c.onDeath, c.bursts, c.path = nil, nil, nil
				c.at = round((el.at or 0) + lo)
				c["for"] = round((if isNum(el["for"]) then el["for"] else 0) + math.max(hi - lo, 0.05))
				local ratio = if isNum(od.ratio) then od.ratio else 1
				if isNum(el.count) and od.count == nil then
					c.count = nil
					c.rate = round(el.count * ratio / c["for"], 2)
				elseif isNum(el.rate) and od.rate == nil then
					c.rate = round(el.rate * ratio, 2)
				end
				if od.shape == nil then
					local s = round(math.max(reach * 2, 0.5), 2)
					c.shape = { type = "Sphere", size = { s, s, s }, style = "Surface" }
				end
				if od.speed == nil then
					c.speed = { 0, 1 }
				end
				table.insert(extra, c)
			end
		end
		-- bursts
		local bu = el.bursts
		if bu ~= nil then
			el.bursts = nil
			if type(bu) ~= "table" or (el.kind ~= "sprite" and el.kind ~= "debris") then
				err(
					`{p}.bursts`,
					"bursts { count, tilt: [min, max], cone, stagger, seed } split a sprite or debris layer"
				)
			else
				local n = math.clamp(math.floor(if isNum(bu.count) then bu.count else 4), 2, 8)
				local tilt = if type(bu.tilt) == "table" then bu.tilt else { 20, 70 }
				local cone = if isNum(bu.cone) then bu.cone else 22
				local stagger = if isNum(bu.stagger) then bu.stagger else 0.025
				local r = rng(seedOf(el.name, bu.seed))
				local base = el.rotate or { 0, 0, 0 }
				local yaw0 = r() * 360
				for k = 1, n do
					local c = deepCopy(el)
					c.name = `{el.name}_b{k}`
					c.at = round((el.at or 0) + (k - 1) * stagger)
					local t = minOf(tilt) + (maxOf(tilt) - minOf(tilt)) * r()
					local yaw = yaw0 + (k - 1) * 360 / n + (r() - 0.5) * 360 / n * 0.6
					-- tilt +Y (the emission axis) away by t degrees toward the yaw direction
					c.rotate = {
						round(base[1] + t * math.cos(math.rad(yaw)), 1),
						base[2],
						round(base[3] + t * math.sin(math.rad(yaw)), 1),
					}
					if c.kind == "sprite" then
						c.spread = cone -- the key the stage and the player READ (spreadAngle was never read: every burst flew in a line)
						if isNum(el.count) then
							c.count = math.max(1, math.ceil(el.count / n * (0.6 + 0.8 * r())))
						end
						if isNum(el.rate) then
							c.rate = round(el.rate / n, 2)
						end
					else
						c.count = math.max(1, math.ceil((el.count or 8) / n))
						c.spread = cone
						if c.seed ~= nil then
							c.seed = (c.seed or 0) + k
						end
					end
					table.insert(extra, c)
				end
				for _, c in extra do
					table.insert(out, c)
				end
				continue
			end
		end
		-- echo (afterimages)
		local ec = el.echo
		if ec ~= nil then
			el.echo = nil
			if type(ec) ~= "table" then
				err(`{p}.echo`, "echo is { count, lag, fade, shrink }")
			else
				local n = math.clamp(math.floor(if isNum(ec.count) then ec.count else 4), 1, 8)
				local lag = if isNum(ec.lag) then ec.lag else 0.035
				local fade = if isNum(ec.fade) then math.clamp(ec.fade, 0, 0.95) else 0.45
				local shrink = if isNum(ec.shrink) then ec.shrink else 0.97
				for k = 1, n do
					local c = shellOf(el, `_echo{k}`, shrink ^ k)
					c.at = round((el.at or 0) + k * lag)
					c.transparency = fadeCurve(el.transparency, (1 - fade) ^ k)
					c.glow = if el.glow ~= nil then scaleCurve(el.glow, (1 - fade) ^ k) else nil
					table.insert(extra, c)
				end
			end
		end
		-- rim
		local ri = el.rim
		if ri ~= nil then
			el.rim = nil
			if type(ri) ~= "table" then
				err(`{p}.rim`, "rim is { color, scale, transparency }")
			else
				local c = shellOf(el, "_rim", if isNum(ri.scale) then ri.scale else 1.06)
				c.material, c.texture, c.surface, c.uvScroll, c.flipbook, c.erode, c.glow =
					"ForceField", nil, nil, nil, nil, nil, nil
				c.color = ri.color or el.color
				c.transparency = if ri.transparency ~= nil then ri.transparency else fadeCurve(el.transparency, 0.65)
				table.insert(extra, c)
			end
		end
		-- boil
		local bo = el.boil
		if bo ~= nil then
			el.boil = nil
			if type(bo) ~= "table" or type(bo.texture) ~= "string" then
				err(`{p}.boil`, "boil is { texture, uvScroll, scale, color, transparency }")
			else
				local c = shellOf(el, "_boil", if isNum(bo.scale) then bo.scale else 1.02)
				c.texture = bo.texture
				c.uvScroll = bo.uvScroll or { -(el.uvScroll and el.uvScroll[1] or 0.1), 0.25 }
				c.flipbook = nil
				if bo.color ~= nil then
					c.color = bo.color
				end
				c.transparency = if bo.transparency ~= nil then bo.transparency else fadeCurve(el.transparency, 0.6)
				table.insert(extra, c)
			end
		end
		-- haze: heat shimmer - a slightly larger Glass shell that wobbles (Roblox Glass bends the OPAQUE world behind it:
		-- from quality level 16 of 21 up - looked at in Studio, 2026-11-15: 16, 18, 21 bend; 15, 14, 8, 1 do not - not
		-- particles, not on phones - kit vfx cost --mobile names it)
		local hz = el.haze
		if hz ~= nil then
			el.haze = nil
			if type(hz) ~= "table" then
				err(`{p}.haze`, "haze is { scale, strength, wobble }")
			else
				local c = shellOf(el, "_haze", if isNum(hz.scale) then hz.scale else 1.15)
				c.material, c.texture, c.surface, c.uvScroll, c.flipbook, c.erode, c.glow, c.smooth =
					"Glass", nil, nil, nil, nil, nil, nil, true
				c.color = { 255, 255, 255 }
				local strength = if isNum(hz.strength) then math.clamp(hz.strength, 0, 1) else 0.5
				-- strength 0..1 -> the shell 0.99..0.96 transparent (V4 3.1 / 13.3; the owner, 2026-11-21: "Yes, remap
				-- haze"). Glass that is any less clear reads as a grey bubble, not shimmer; the bend is the material's
				-- own. It was 1 - 0.35 x strength (0.825 at the default), measured in Studio by vfx_stage_parity
				c.transparency = fadeCurve(el.transparency, 0.01 + 0.03 * strength)
				c.wobble = if type(hz.wobble) == "table" then hz.wobble else { 0.08, 6, 9 }
				table.insert(extra, c)
			end
		end
		table.insert(out, el)
		for _, c in extra do
			table.insert(out, c)
		end
	end
	preset.layers = out
	return issues
end

return VfxTech

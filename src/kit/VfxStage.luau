-- VfxStage (ReplicatedStorage.kit.VfxStage) — plays version-3 VFX presets (assets/effects/<name>.json with
-- "version": 3) the way pro Roblox effects are built: MANY layers, usually one sprite each, every one timed, all on
-- ONE clock. Because the clock is ours, an effect can freeze (hit-stop), run in slow motion and be held at an exact
-- moment for capture (kit vfx booth).
--   local stage = VfxStage.play(preset, cframe, { scale = 1, target = Vector3?, textures = registry, anchors = {} })
--   stage:freeze()  stage:resume()  stage:setTimeScale(0.25)  stage:advanceTo(1.2)  stage:stop()  stage.time
--   stage:release()  stops DRAWING (trails and sprites emit nothing new) while what is drawn fades by itself and
--   the rest plays out: a new swing on the same blade takes over from the last one without stacking on it
-- Layer kinds: sprite (ParticleEmitter, every engine property), beam (scrolling, growing, curved), mesh (runtime
-- EditableMesh with flowing UVs, or a primitive), decal (ground marks that glow), light, debris (on the clock),
-- screen (colour flash / grade / blur / bloom boost), impact (anime impact frame), shake, fov, sound.
-- Times: every layer has "at" (seconds) and runs over "life"; sequences ([[u, v], ...], u 0..1) run over that life.
-- Points: [x, y, z] studs in the effect's own space (x right, y up, -z forward; `scale` multiplies), a name from
-- preset.points, "target" (the caller's target, else points.target) or "@<anchor>" (a part/attachment passed in
-- opts.anchors — follows it every frame, e.g. "@blade").
-- opts.palette = { name = [r, g, b] } overrides the preset's palette for this play (an impact's chips in the hit wall's
-- colour); opts.material = the surface name `onMaterial` picks by (default: one raycast down).
local Lighting = game:GetService("Lighting")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local CraterRefs = require("./CraterRefs")
local VfxBounce = require("./VfxBounce")
local VfxBudget = require("./VfxBudget")
local VfxDebris = require("./VfxDebris")
local VfxEmit = require("./VfxEmit")
local VfxHighlight = require("./VfxHighlight")
local VfxMesh = require("./VfxMesh")
local VfxMood = require("./VfxMood")
local VfxNet = require("./VfxNet")
local VfxRockRing = require("./VfxRockRing")

local VfxStage = {}

export type Stage = {
	time: number,
	duration: number,
	frozen: boolean,
	timeScale: number,
	finished: boolean,
	released: boolean,
	freeze: (self: Stage) -> (),
	resume: (self: Stage) -> (),
	setTimeScale: (self: Stage, s: number) -> (),
	advanceTo: (self: Stage, t: number) -> (),
	stop: (self: Stage) -> (),
	release: (self: Stage) -> (),
	[string]: any,
}

local rng = Random.new()

-- the client's ONE mood stack (src/kit/VfxMood.luau): every world layer and impact frame pushes what it wants into
-- it; the scene's own Lighting / Atmosphere value of a key is read once and written back when the last effect lets go
local LIGHT_KEYS = {
	exposure = "ExposureCompensation",
	brightness = "Brightness",
	ambient = "OutdoorAmbient",
	fogEnd = "FogEnd",
	fogStart = "FogStart",
	fogColor = "FogColor",
}
local ATMO_KEYS = {
	["atmo.density"] = "Density",
	["atmo.offset"] = "Offset",
	["atmo.color"] = "Color",
	["atmo.decay"] = "Decay",
	["atmo.glare"] = "Glare",
	["atmo.haze"] = "Haze",
}
local mood = VfxMood.new(function(key: string): any
	local l = LIGHT_KEYS[key]
	if l then
		return (Lighting :: any)[l]
	end
	local a = ATMO_KEYS[key]
	local atmo = if a then Lighting:FindFirstChildOfClass("Atmosphere") else nil
	return if atmo then (atmo :: any)[a] else nil
end, function(key: string, value: any)
	local l = LIGHT_KEYS[key]
	if l then
		(Lighting :: any)[l] = value
		return
	end
	local a = ATMO_KEYS[key]
	local atmo = if a then Lighting:FindFirstChildOfClass("Atmosphere") else nil
	if atmo then
		(atmo :: any)[a] = value
	end
end)
VfxStage._mood = mood -- (read by the specs and a Studio probe: how many effects hold the scene's mood)

-- the client's Highlight slots (src/kit/VfxHighlight.luau): the engine draws 31 at most; every Highlight the runtime
-- turns on claims one first - a fighter's aura and the impact frame's silhouettes as HEROES, an effect's outlines
-- below them - so a busy fight never loses the attacker's or the victim's rim to a far spark's outline
local highlightSlots = VfxHighlight.new()
VfxStage._highlights = highlightSlots

-- the terrain cells the client's crater layers hold (src/kit/CraterRefs.luau): two bowls that overlap give the ground
-- back only when the last of them ends, as it was before the first (each wrote its own snapshot back: clobbered)
local craterCells = CraterRefs.new()
VfxStage._craterCells = craterCells

-- turn a Highlight on (if it gets a slot) or off (giving its slot back); a hero that took a lower one's slot turns
-- that one off - its own updater asks again next frame and is refused while the client is full
local function lightUp(h: Highlight, priority: number, on: boolean)
	if not on then
		highlightSlots:release(h)
		h.Enabled = false
		return
	end
	local ok, lost = highlightSlots:claim(h, priority)
	if lost ~= nil and typeof(lost) == "Instance" and (lost :: Instance):IsA("Highlight") then
		(lost :: Highlight).Enabled = false
	end
	h.Enabled = ok
end

-- ---------------------------------------------------------------- value helpers
local function rgb(c: any, palette: any): Color3
	if type(c) == "string" then
		c = palette and palette[c] or { 255, 0, 255 }
	end
	return Color3.new(c[1] / 255, c[2] / 255, c[3] / 255)
end

-- a colour NAME missing from the preset's palette is drawn magenta (rgb above): the first play of a preset says so, once
-- per layer + name, so a stale or hand-edited copy never hides (Sample Game 2026-10-29: a magenta pad was blamed on it)
local COLOR_KEYS = { color = true, tint = true, fill = true, outline = true, zoomColor = true, streakColor = true }
local paletteChecked: { [any]: boolean } = setmetatable({} :: any, { __mode = "k" })

local function namesIn(v: any, out: { string })
	if type(v) == "string" then
		table.insert(out, v)
	elseif type(v) == "table" then
		for _, x in v do
			namesIn(x, out)
		end
	end
end

local function checkPalette(preset: any, label: string)
	if paletteChecked[preset] then
		return
	end
	paletteChecked[preset] = true
	local palette = if type(preset.palette) == "table" then preset.palette else {}
	local said = {}
	local function walk(node: any, layer: string)
		for k, v in node do
			if COLOR_KEYS[k] then
				local names = {}
				namesIn(v, names)
				for _, n in names do
					if palette[n] == nil and not said[layer .. "\0" .. n] then
						said[layer .. "\0" .. n] = true
						warn(`[VfxStage] {label} layer "{layer}": colour "{n}" is not in the palette (drawn magenta)`)
					end
				end
			elseif k ~= "palette" and type(v) == "table" then
				walk(v, if type(v.name) == "string" then v.name else layer)
			end
		end
	end
	walk(preset, "-")
end

local function isSeq(v: any): boolean
	return type(v) == "table" and type(v[1]) == "table"
end

-- which cell of a sheet a mesh layer shows now (pure: no game API; kit/selftest/vfx/dissolve/run.py runs THIS text and
-- the player's twin on one sweep, so the game and the player cannot drift apart). OneShot spreads the cells over the
-- layer's life u, or - "over": [u0, u1] - over that part of it: the first cell until u0, the last from u1 (a baked
-- dissolve, kit vfx dissolve: the texture whole, then breaking up, then gone). Any other mode runs at fps
local function sheetFrame(fb: any, u: number, age: number, frames: number, start: number): number
	if fb.mode == "OneShot" then
		local uu = u
		if type(fb.over) == "table" then
			local u0 = if type(fb.over[1]) == "number" then fb.over[1] else 0
			local u1 = if type(fb.over[2]) == "number" then fb.over[2] else 1
			uu = math.clamp((u - u0) / math.max(u1 - u0, 1e-4), 0, 1)
		end
		return math.min(math.floor(uu * frames), frames - 1)
	end
	return (math.floor(age * (fb.fps or 24)) + start) % frames
end
-- (end of sheetFrame)

-- A LENS FLARE's pictures for a light at (lx, ly) of the screen (0,0 top left): a glow on the light, a level streak
-- through it, and ghosts on the line from the light through the middle of the screen (kit/vfx/flare.py `marks` is
-- the rule; kit/vfx/player/player.js `flareMarks` is the same text in JavaScript; kit/selftest/vfx/flare/run.py
-- parity runs all three). Sizes are shares of the screen's HEIGHT
local flareBinds = 0 -- (a render-step binding needs a name of its own)
local FLARE_K = { 0.35, 0.62, 0.9, 1.25, 1.6, 1.85, 2.1, 2.4 }
local FLARE_S = { 0.22, 0.4, 0.16, 0.6, 0.3, 0.9, 0.25, 0.5 }
local FLARE_A = { 0.5, 0.35, 0.6, 0.25, 0.4, 0.18, 0.45, 0.2 }
local function flareMarks(lx: number, ly: number, aspect: number, f: any): { any }
	local size = if type(f.size) == "number" then f.size else 0.18
	local n = math.clamp(math.floor(if type(f.ghosts) == "number" then f.ghosts else 5), 0, 8)
	local streak = if type(f.streak) == "number" then f.streak else 0
	local squeeze = math.clamp(if type(f.squeeze) == "number" then f.squeeze else 1, 1, 3)
	local d = math.max(math.abs(lx - 0.5), math.abs(ly - 0.5)) * 2
	local vis = if d <= 1 then 1 elseif d >= 1.3 then 0 else 1 - (d - 1) / 0.3
	local out: { any } = {}
	if vis <= 0 then
		return out
	end
	table.insert(out, { kind = 1, i = 0, x = lx, y = ly, w = size, h = size, a = vis, c = 0 })
	if streak > 0 then
		table.insert(
			out,
			{ kind = 2, i = 0, x = lx, y = ly, w = streak * aspect, h = size * 0.35, a = vis * 0.9, c = 0 }
		)
	end
	for i = 1, n do
		local s = size * FLARE_S[i]
		table.insert(out, {
			kind = 3,
			i = i,
			x = lx + (0.5 - lx) * FLARE_K[i],
			y = ly + (0.5 - ly) * FLARE_K[i],
			w = s * squeeze,
			h = s,
			a = vis * FLARE_A[i],
			c = i / n,
		})
	end
	return out
end
-- (end of flareMarks)

-- A MESH TRAIL'S HISTORY (the owner's limitations file, F-R01): the ribbon is drawn through the places its host was.
-- A stage that is RELEASED stops emitting (its particles and its flat Trails did; the ribbon went on taking samples
-- for as long as its layer lived): no new sample is taken, the tail it has ages out, and then the ribbon is done.
-- does the ribbon take a sample at time t (its layer alive, its host there, the stage not released)
local function ribbonEmits(t: number, at: number, life: number, hostThere: boolean, released: boolean): boolean
	return t >= at and (t - at) / life <= 1 and hostThere and not released
end
-- one frame of the history: a new sample when `sample` is given (asked for only then), samples older than `lifetime`
-- dropped, never more than `samples` of them
local function ribbonHistory(hist: { any }, t: number, lifetime: number, samples: number, sample: (() -> (any, any))?)
	if sample then
		local last = hist[#hist]
		if not last or t > last.t then
			local a, b = sample()
			table.insert(hist, { t = t, a = a, b = b })
		end
	end
	while hist[1] and t - hist[1].t > lifetime do
		table.remove(hist, 1)
	end
	while #hist > samples do
		table.remove(hist, 1)
	end
end
-- is the ribbon finished (back to the pool now): its tail is gone AND it will take no more samples - its layer's
-- life is over (u > 1) or its stage was released
local function ribbonDone(u: number, released: boolean, count: number): boolean
	return count == 0 and (u > 1 or released)
end
-- (end of the ribbon's rules)

-- THE MIDDLE OF A BAKED FRAME'S BOX (the VFX methods audit, stage 26): the engine centres a MeshPart on the bounds of
-- the mesh it was made from - for a mesh sequence, its FIRST frame's - so the file's own origin (the water at rest,
-- the ground the sand lies on, the pole a cloth hangs from) is NOT where the layer's point is. With "pivot": "origin"
-- the stage moves the part by this middle, and the file's origin sits on the point. frame = { x, y, z, x, y, z ... }
local function seqMiddle(frame: { number }): (number, number, number)
	local x0, x1, y0, y1, z0, z1 = math.huge, -math.huge, math.huge, -math.huge, math.huge, -math.huge
	for k = 1, #frame - 2, 3 do
		x0, x1 = math.min(x0, frame[k]), math.max(x1, frame[k])
		y0, y1 = math.min(y0, frame[k + 1]), math.max(y1, frame[k + 1])
		z0, z1 = math.min(z0, frame[k + 2]), math.max(z1, frame[k + 2])
	end
	if x0 > x1 then
		return 0, 0, 0
	end
	return (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
end
-- (end of seqMiddle)

-- A PIECE THAT COMES TO REST: one step of a fracture piece's flight when its debris layer says "rest" - it falls,
-- bounces losing most of its speed, slides to a stop, tips onto its nearest flat face and lies there
-- (kit/vfx/settle.py `step` is the rule; kit/vfx/player/player.js `debrisStep` is the same arithmetic;
-- kit/selftest/vfx/settle/run.py parity runs all three). s = { x, y, z, vx, vy, vz, tilt, yaw, tilt speed,
-- yaw speed, at rest 0 / 1 }; hy = half the piece's thickness, hw = half its width
local function debrisStep(s: { number }, dt: number, g: number, floor: number, hy: number, hw: number): { number }
	local x, y, z, vx, vy, vz, tilt, yaw, wt, wy, rest =
		s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8], s[9], s[10], s[11]
	if rest == 1 then
		return s
	end
	vy = vy - g * dt
	x = x + vx * dt
	y = y + vy * dt
	z = z + vz * dt
	tilt = tilt + wt * dt
	yaw = yaw + wy * dt
	local h = math.abs(math.cos(tilt)) * hy + math.abs(math.sin(tilt)) * hw
	if y <= floor + h then
		y = floor + h
		if vy < 0 then
			if -vy > g * dt * 2 then
				vy = -vy * 0.3
				vx = vx * 0.6
				vz = vz * 0.6
				wt = wt * 0.5
				wy = wy * 0.6
			else
				vy = 0
			end
		end
		if vy == 0 then
			local k = math.max(0, 1 - 6 * dt)
			vx = vx * k
			vz = vz * k
			wy = wy * k
			wt = 0
			local target = math.floor(tilt / math.pi + 0.5) * math.pi
			tilt = tilt + (target - tilt) * math.min(1, 10 * dt)
			y = floor + math.abs(math.cos(tilt)) * hy + math.abs(math.sin(tilt)) * hw
			if math.sqrt(vx * vx + vz * vz) < g * 0.004 and math.abs(target - tilt) < 0.01 then
				rest = 1
				tilt = target
				vx = 0
				vz = 0
				wy = 0
				y = floor + hy
			end
		end
	end
	return { x, y, z, vx, vy, vz, tilt, yaw, wt, wy, rest }
end
-- (end of debrisStep)

-- PIECES THAT MEET (the VFX methods audit, stage 23): ALL the pieces of a "rest" debris layer that have left the slab,
-- one step - what each lies ON (the floor, or the top of a piece on the ground under its middle), pieces on the ground
-- that lie IN each other pushed apart (the lighter gives way more, a slide not a jump), then every piece's own
-- debrisStep. kit/vfx/settle.py `meet` is the rule; kit/vfx/player/player.js `debrisMeet` is the same arithmetic
-- (kit/selftest/vfx/settle/run.py parity runs all three). shapes: each piece's flat outline { x, z, x, z ... } about
-- its state's x, z; H, W: half its thickness and half its width; A: its area
-- turn: the yaw of the frame the slab is played in (a piece is drawn frame x yaw x tilt: the mirror of a piece on its
-- other face is about its OWN z, so the outline is mirrored first and turned after); unit: the play's scale
local DEBRIS_SKIN, DEBRIS_PART, DEBRIS_NUDGE, DEBRIS_HITCH = 0.02, 8, 0.001, 1 / 30
local function debrisLying(s: { number }, shape: { number }, turn: number): { number }
	local flip = math.floor(s[7] / math.pi + 0.5) % 2 ~= 0
	local c, n = math.cos(s[8] + turn), math.sin(s[8] + turn)
	local out = table.create(#shape)
	for k = 1, #shape, 2 do
		local px, pz = shape[k], shape[k + 1]
		if flip then
			pz = -pz
		end
		out[k] = s[1] + px * c + pz * n
		out[k + 1] = s[3] - px * n + pz * c
	end
	return out
end
local function debrisWithin(poly: { number }, x: number, z: number): boolean
	local pos, neg, n = false, false, #poly
	for k = 1, n, 2 do
		local ax, az = poly[k], poly[k + 1]
		local bx, bz = poly[(k + 1) % n + 1], poly[(k + 2) % n + 1]
		local cr = (bx - ax) * (z - az) - (bz - az) * (x - ax)
		if cr > 0 then
			pos = true
		elseif cr < 0 then
			neg = true
		end
	end
	return not (pos and neg)
end
local function debrisApart(a: { number }, b: { number }): (number, number, number)
	local best, bx, bz = math.huge, 0, 0
	for which = 1, 2 do
		local poly = if which == 1 then a else b
		local n = #poly
		for k = 1, n, 2 do
			local ex, ez = poly[(k + 1) % n + 1] - poly[k], poly[(k + 2) % n + 1] - poly[k + 1]
			local ln = math.sqrt(ex * ex + ez * ez)
			if ln >= 1e-9 then
				local nx, nz = ez / ln, -ex / ln
				local a0, a1, b0, b1 = math.huge, -math.huge, math.huge, -math.huge
				for q = 1, #a, 2 do
					local d = a[q] * nx + a[q + 1] * nz
					a0, a1 = math.min(a0, d), math.max(a1, d)
				end
				for q = 1, #b, 2 do
					local d = b[q] * nx + b[q + 1] * nz
					b0, b1 = math.min(b0, d), math.max(b1, d)
				end
				local o = math.min(a1, b1) - math.max(a0, b0)
				if o <= 0 then
					return 0, 0, 0
				end
				if o < best - 1e-9 then -- (two ways out as deep as each other: the first, in every runtime)
					best = o
					if a0 + a1 < b0 + b1 then
						bx, bz = -nx, -nz
					else
						bx, bz = nx, nz
					end
				end
			end
		end
	end
	if best == math.huge then
		return 0, 0, 0
	end
	return best, bx, bz
end
local function debrisMeet(
	states: { { number } },
	shapes: { { number } },
	H: { number },
	W: { number },
	A: { number },
	dt: number,
	g: number,
	base: number,
	turn: number,
	unit: number
): ({ { number } }, { number }, boolean)
	local n = #states
	local overlapped = false -- (any two pieces deeper in each other than the skin: the early stop is not taken then)
	local skin, pushMost = DEBRIS_SKIN * unit, DEBRIS_PART * unit * math.min(dt, DEBRIS_HITCH)
	local mvx: { number }, mvz: { number }, lies: { boolean } = table.create(n, 0), table.create(n, 0), table.create(n)
	local S: { { number } } = table.create(n)
	local half: { number }, poly: { { number } }, reach: { number } = table.create(n), table.create(n), table.create(n)
	local order: { number }, floor: { number }, down: { boolean } = table.create(n), table.create(n), table.create(n)
	local pushed: { boolean } = table.create(n)
	for i = 1, n do
		S[i] = table.clone(states[i])
		lies[i] = math.abs(S[i][7] - math.floor(S[i][7] / math.pi + 0.5) * math.pi) < 0.01
		half[i] = math.abs(math.cos(S[i][7])) * H[i] + math.abs(math.sin(S[i][7])) * W[i]
		poly[i] = debrisLying(S[i], shapes[i], turn)
		local r = 0
		for k = 1, #shapes[i], 2 do
			r = math.max(r, shapes[i][k] * shapes[i][k] + shapes[i][k + 1] * shapes[i][k + 1])
		end
		reach[i] = math.sqrt(r)
		order[i] = i
		floor[i] = base
		down[i] = false
		pushed[i] = false
	end
	for a = 2, n do -- from the lowest up: what a piece lies on is always lower than it
		local k = order[a]
		local b = a - 1
		while b >= 1 and S[order[b]][2] > S[k][2] do
			order[b + 1] = order[b]
			b -= 1
		end
		order[b + 1] = k
	end
	for a = 1, n do
		local i = order[a]
		local bottom = S[i][2] - half[i]
		local fell = math.max(0, -S[i][5] * dt) -- (a falling piece is caught by a top it passed in this step)
		for b = 1, a - 1 do
			local j = order[b]
			local top = S[j][2] + half[j]
			if
				down[j]
				and lies[j]
				and top > floor[i]
				and top <= bottom + fell + 1e-6
				and debrisWithin(poly[j], S[i][1], S[i][3])
			then
				floor[i] = top
			end
		end
		down[i] = S[i][5] == 0 and bottom <= floor[i] + 1e-6
		if S[i][11] == 1 and math.abs(bottom - floor[i]) > 1e-6 then
			S[i][11] = 0 -- what it lay on has gone (or come): it is not at rest
		end
	end
	for i = 1, n do
		for j = i + 1, n do
			if not (down[i] and down[j]) then
				continue
			end
			if
				math.min(S[i][2] + half[i], S[j][2] + half[j]) - math.max(S[i][2] - half[i], S[j][2] - half[j]) <= 1e-4
			then
				continue -- one lies ON the other, or over it
			end
			local dx, dz = S[i][1] - S[j][1], S[i][3] - S[j][3]
			if dx * dx + dz * dz >= (reach[i] + reach[j]) * (reach[i] + reach[j]) then
				continue
			end
			local deep, nx, nz = debrisApart(poly[i], poly[j])
			if deep <= skin + 1e-9 then
				continue
			end
			overlapped = true
			local m = math.min(deep - skin / 2, pushMost) -- (parted to HALF the skin: not at the edge of being pushed again)
			local wi = A[j] / (A[i] + A[j])
			local mi, mj = m * wi, m * (1 - wi)
			-- (all the pushes of a step are worked out from where the pieces lay at its start, and added)
			mvx[i] += nx * mi
			mvz[i] += nz * mi
			mvx[j] -= nx * mj
			mvz[j] -= nz * mj
		end
	end
	for i = 1, n do
		local d = math.sqrt(mvx[i] * mvx[i] + mvz[i] * mvz[i])
		if d > DEBRIS_NUDGE * unit then -- pushes that cancel (a piece jammed between others) move nothing: it can rest
			local k = math.min(1, pushMost / d)
			S[i][1] += mvx[i] * k
			S[i][3] += mvz[i] * k
			pushed[i] = true
			S[i][11] = 0
		end
	end
	local out: { { number } } = table.create(n)
	for i = 1, n do
		out[i] = debrisStep(S[i], dt, g, floor[i], H[i], W[i])
		if pushed[i] then
			out[i][11] = 0 -- (a piece that is being pushed is not at rest, however slow it is)
		end
	end
	return out, floor, overlapped
end
-- (end of debrisMeet)

-- A PIECE AS IT SITS IN THE SLAB (stage 10's leftover: the start was read side by side, never run against the rule):
-- a plan's piece -> (its eleven numbers in the layer's own frame, half its height, half its width). x, z is the
-- middle of the piece's BOX (the MeshPart sits and turns there); speeds are the plan's push x the layer's scale and
-- push. kit/vfx/settle.py `start` is the rule, kit/vfx/player/player.js `debrisStart` the same arithmetic
-- (kit/selftest/vfx/settle/run.py parity runs all three)
-- the debris layers already told they rest on a level floor while played tilted (once a layer: not every play)
local tiltSaid: { [string]: boolean } = {}

local function debrisStart(
	pc: any,
	thick: number,
	scale: number,
	push: number
): ({ number }, number, number, { number })
	local x0, x1, z0, z1 = math.huge, -math.huge, math.huge, -math.huge
	for _, q in pc.points do
		x0, x1, z0, z1 = math.min(x0, q[1]), math.max(x1, q[1]), math.min(z0, q[2]), math.max(z1, q[2])
	end
	local ox, oz = (x0 + x1) / 2, (z0 + z1) / 2
	local k = scale * push
	-- its flat outline about the middle of its box, in its OWN axes (debrisMeet turns it by the frame's yaw)
	local shape = table.create(#pc.points * 2)
	for _, q in pc.points do
		table.insert(shape, (q[1] - ox) * scale)
		table.insert(shape, (q[2] - oz) * scale)
	end
	return {
		(pc.centre[1] + ox) * scale,
		thick * scale / 2,
		(pc.centre[2] + oz) * scale,
		pc.vel[1] * k,
		pc.vel[2] * k,
		pc.vel[3] * k,
		0,
		0,
		pc.spin[1] * push, -- (a layer's speed scales the plan's spin as well as its push)
		pc.spin[2] * push,
		0,
	},
		thick * scale / 2,
		math.max(z1 - z0, 0.05) * scale / 2,
		shape
end
-- (end of debrisStart)

-- the frame's YAW, the turn about the up axis a slab's pieces are met by (Roblox's CFrame:ToOrientation, whose Y is the
-- yaw of a Y-X-Z turn; kit/vfx/player/player.js `frameYaw` reads the same from its quaternion - the settle parity runs
-- both on the same turns, tilted ones too)
local function frameYaw(cf: CFrame): number
	local _, yaw = cf:ToOrientation() -- (one value: select(2, ...) passed the roll along too)
	return yaw
end
-- (end of frameYaw)

-- AN AUTHORED VECTOR FIELD's velocity at a place (studs from the swarm layer's point, world axes): the sum of its
-- elements - wind, vortex, point, path (kit/vfx/field.py `at` is the rule and says each; kit/vfx/player/player.js
-- `fieldAt` is the same arithmetic; kit/selftest/vfx/field/run.py parity runs all three)
local function fieldAt(elements: { any }, x: number, y: number, z: number): { number }
	local vx, vy, vz = 0, 0, 0
	for _, e in elements do
		local kind = e.kind
		if kind == "wind" then
			local d = e.dir
			local n = math.sqrt(d[1] * d[1] + d[2] * d[2] + d[3] * d[3])
			if n > 1e-9 then
				local s = e.speed / n
				vx = vx + d[1] * s
				vy = vy + d[2] * s
				vz = vz + d[3] * s
			end
		elseif kind == "vortex" then
			local a = e.at
			local ax = e.axis
			if type(ax) ~= "table" or #ax ~= 3 then
				ax = { 0, 1, 0 }
			end
			local n = math.sqrt(ax[1] * ax[1] + ax[2] * ax[2] + ax[3] * ax[3])
			local rad = e.radius
			if n > 1e-9 and rad > 1e-9 then
				local nx, ny, nz = ax[1] / n, ax[2] / n, ax[3] / n
				local rx, ry, rz = x - a[1], y - a[2], z - a[3]
				local h = rx * nx + ry * ny + rz * nz
				local px, py, pz = rx - h * nx, ry - h * ny, rz - h * nz
				local d = math.sqrt(px * px + py * py + pz * pz)
				local lift = (e.lift or 0) * math.exp(-((d / (2 * rad)) * (d / (2 * rad))))
				vx = vx + nx * lift
				vy = vy + ny * lift
				vz = vz + nz * lift
				if d > 1e-9 then
					local f = (d / rad) * math.exp(1 - d / rad)
					local ux, uy, uz = px / d, py / d, pz / d
					local turn = e.speed * f
					local pull = (e.pull or 0) * f
					vx = vx + (ny * uz - nz * uy) * turn - ux * pull
					vy = vy + (nz * ux - nx * uz) * turn - uy * pull
					vz = vz + (nx * uy - ny * ux) * turn - uz * pull
				end
			end
		elseif kind == "point" then
			local a = e.at
			local rx, ry, rz = x - a[1], y - a[2], z - a[3]
			local d = math.sqrt(rx * rx + ry * ry + rz * rz)
			local rad = e.radius
			if d > 1e-9 and rad > 1e-9 then
				local core = d / (0.25 * rad)
				local s = e.speed * math.exp(-((d / rad) * (d / rad))) * (1 - math.exp(-(core * core))) / d
				vx = vx + rx * s
				vy = vy + ry * s
				vz = vz + rz * s
			end
		elseif kind == "path" then
			local pts = e.points
			local best = -1
			local cx, cy, cz, tx, ty, tz = 0, 0, 0, 0, 0, 0
			for i = 1, #pts - 1 do
				local p0, p1 = pts[i], pts[i + 1]
				local sx, sy, sz = p1[1] - p0[1], p1[2] - p0[2], p1[3] - p0[3]
				local ln = math.sqrt(sx * sx + sy * sy + sz * sz)
				if ln > 1e-9 then
					local u = ((x - p0[1]) * sx + (y - p0[2]) * sy + (z - p0[3]) * sz) / (ln * ln)
					u = math.max(0, math.min(1, u))
					local qx, qy, qz = p0[1] + sx * u, p0[2] + sy * u, p0[3] + sz * u
					local dd = (x - qx) * (x - qx) + (y - qy) * (y - qy) + (z - qz) * (z - qz)
					if best < 0 or dd < best then
						best = dd
						cx, cy, cz = qx, qy, qz
						tx, ty, tz = sx / ln, sy / ln, sz / ln
					end
				end
			end
			local rad = e.radius
			if best >= 0 and rad > 1e-9 then
				local w = math.exp(-(best / (rad * rad)))
				local along = e.speed * w
				local pull = (e.pull or 0) / rad * w
				vx = vx + tx * along + (cx - x) * pull
				vy = vy + ty * along + (cy - y) * pull
				vz = vz + tz * along + (cz - z) * pull
			end
		end
	end
	return { vx, vy, vz }
end
-- (end of fieldAt)

-- A POINT CLOUD (a swarm layer's "cloud"): the new speed, along one axis, of a particle `d` from its point moving at
-- `v`, pulled at `w` over a step `dt` - a critically damped spring stepped implicitly: it never overshoots or blows
-- up, whatever the step (kit/vfx/points.py `pull` is the rule; kit/vfx/player/player.js `cloudPull` is the same
-- arithmetic; kit/selftest/vfx/points/run.py parity runs all three)
local function cloudPull(d: number, v: number, w: number, dt: number): number
	return (v - w * w * d * dt) / (1 + 2 * w * dt + w * w * dt * dt)
end
-- (end of cloudPull)

-- FORCED PERSPECTIVE: the size multiplier of a mesh layer `dist` studs from the camera - (dist / ref) ^ keep, held
-- between min and max (keep 1 = it holds its size ON THE SCREEN at any distance; kit/vfx/forced.py `scale` is the
-- rule; kit/vfx/player/player.js `forcedScale` is the same arithmetic; kit/selftest/vfx/forced/run.py parity)
local function forcedScale(dist: number, f: any): number
	local ref = f.ref
	local keep = if type(f.keep) == "number" then f.keep else 1
	local lo = if type(f.min) == "number" then f.min else 0.25
	local hi = if type(f.max) == "number" then f.max else 4
	if type(ref) ~= "number" or not (ref > 1e-6) then
		return 1
	end
	local s = math.pow(math.max(dist, 1e-3) / ref, keep)
	return math.max(lo, math.min(hi, s))
end
-- (end of forcedScale)

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

local function colorAt(v: any, u: number, palette: any): Color3
	if v == nil then
		return Color3.new(1, 1, 1)
	end
	if not isSeq(v) then
		return rgb(v, palette)
	end
	for i = 1, #v - 1 do
		local a, b = v[i], v[i + 1]
		if u <= b[1] then
			local k = if b[1] > a[1] then (u - a[1]) / (b[1] - a[1]) else 0
			return rgb(a[2], palette):Lerp(rgb(b[2], palette), math.clamp(k, 0, 1))
		end
	end
	return rgb(v[#v][2], palette)
end

local function vecAt(v: any, u: number): Vector3
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

-- a mesh's spin angles (degrees) at `age`: spin is [x, y, z] degrees per second, or keys [[u, [x, y, z]], ...] of that
-- SPEED over the layer's life - the angle is its integral (exact: the speed is linear between keys), so a whirl can
-- spin UP and wind down. The player's spinAngle does the same.
local function spinAngle(spin: any, age: number, life: number): Vector3
	if spin == nil then
		return Vector3.zero
	end
	if type(spin[1]) == "number" then
		return Vector3.new(spin[1], spin[2], spin[3]) * age
	end
	local u = age / life
	local pts = { 0 }
	for _, k in spin do
		if k[1] > 0 and k[1] < u then
			table.insert(pts, k[1])
		end
	end
	table.insert(pts, u)
	local out = Vector3.zero
	for i = 1, #pts - 1 do
		out += (vecAt(spin, pts[i]) + vecAt(spin, pts[i + 1])) * ((pts[i + 1] - pts[i]) * life / 2)
	end
	return out
end

local function range(v: any, k: number): NumberRange
	if v == nil then
		return NumberRange.new(0)
	end
	if type(v) == "number" then
		return NumberRange.new(v * k)
	end
	return NumberRange.new(v[1] * k, v[2] * k)
end

local function numberSeq(v: any, k: number): NumberSequence
	if type(v) == "number" then
		return NumberSequence.new(v * k)
	end
	local kps = {}
	for _, kp in v do
		table.insert(kps, NumberSequenceKeypoint.new(kp[1], kp[2] * k, (kp[3] or 0) * k))
	end
	return NumberSequence.new(kps)
end

local function colorSeq(v: any, palette: any): ColorSequence
	if not isSeq(v) then
		return ColorSequence.new(rgb(v or { 255, 255, 255 }, palette))
	end
	local kps = {}
	for _, kp in v do
		table.insert(kps, ColorSequenceKeypoint.new(kp[1], rgb(kp[2], palette)))
	end
	return ColorSequence.new(kps)
end

-- transparency along a beam (seq over its length) faded by an overall 0..1 visibility
local function fadedSeq(v: any, visible: number): NumberSequence
	if v == nil or type(v) == "number" then
		local t = if v == nil then 0 else v
		return NumberSequence.new(1 - (1 - t) * visible)
	end
	local kps = {}
	for _, kp in v do
		table.insert(kps, NumberSequenceKeypoint.new(kp[1], 1 - (1 - kp[2]) * visible))
	end
	return NumberSequence.new(kps)
end

-- soft ends: a beam fades in over the first `se` of its length and out over the last (no flat cap at either end)
local function softEnds(seq: NumberSequence, se: number): NumberSequence
	if se <= 0 then
		return seq
	end
	local function at(t: number): number
		local kps = seq.Keypoints
		for i = 1, #kps - 1 do
			local a, b = kps[i], kps[i + 1]
			if t <= b.Time then
				local k = if b.Time > a.Time then (t - a.Time) / (b.Time - a.Time) else 0
				return a.Value + (b.Value - a.Value) * k
			end
		end
		return kps[#kps].Value
	end
	local times = { 0, se * 0.5, se, 1 - se, 1 - se * 0.5, 1 }
	for _, kp in seq.Keypoints do
		if kp.Time > se and kp.Time < 1 - se then
			table.insert(times, kp.Time)
		end
	end
	table.sort(times)
	local out = {}
	local last = -1
	for _, t in times do
		if t > last + 1e-4 then
			local e = math.min(1, t / se) * math.min(1, (1 - t) / se)
			e = e * e * (3 - 2 * e)
			table.insert(out, NumberSequenceKeypoint.new(t, 1 - (1 - at(t)) * e))
			last = t
		end
	end
	if #out > 20 then -- Roblox allows 20 keypoints
		local thin = {}
		local step = (#out - 1) / 19
		for i = 0, 19 do
			table.insert(thin, out[math.floor(i * step + 0.5) + 1])
		end
		out = thin
	end
	return NumberSequence.new(out)
end

local function ease(k: number, style: string?): number
	k = math.clamp(k, 0, 1)
	if style == "in" then
		return k * k
	elseif style == "linear" then
		return k
	end
	return 1 - (1 - k) * (1 - k) * (1 - k)
end

local function textureId(textures: any, key: string?): string
	if not key or not textures then
		return ""
	end
	local e = textures[key]
	if type(e) ~= "table" then
		return ""
	end
	if type(e.id) == "string" and e.id ~= "" then
		return e.id
	end
	return e.fallback or ""
end

-- a mesh layer's texture as a SurfaceAppearance (layer field `surface`): the only way a runtime mesh gets texture
-- ALPHA and GLOW in the engine — measured 2026-10-16 (kit/knowledge/vault/vfx/refs/engine-facts.md): TextureID alpha
-- and vertex alpha are ignored on a MeshPart; ColorMap + EmissiveMask (the same sheet) + AlphaMode Transparency works.
-- A game script cannot set the maps (Plugin capability), so a live game clones an authored template from
-- ReplicatedStorage.VfxPresets._surfaces.<texture key> (kit vfx surfaces); Studio (the booth, plugin rights) builds one on the spot. Returns
-- false when neither works (the caller falls back to TextureID).
local surfaceWarned = false
local ribbonWarned = false -- mesh trails are drawn as flat Trails from now on (ribbons failed RIBBON_GIVE_UP times running)
-- one failed ribbon is the memory budget (Sample Game 2026-10-29): that trail alone is flat; only failures in a row (the
-- place has "Allow Mesh & Image APIs" off) turn every later ribbon flat at once
local RIBBON_GIVE_UP = 3
local ribbonFails = 0
local function applySurface(mp: MeshPart, key: string, id: string, strength: number): boolean
	-- kit vfx surfaces writes the templates to assets/effects/_surfaces.model.json -> ReplicatedStorage.VfxPresets._surfaces
	local rs = game:GetService("ReplicatedStorage")
	local presets = rs:FindFirstChild("VfxPresets")
	local folder = (presets and presets:FindFirstChild("_surfaces")) or rs:FindFirstChild("VfxSurfaces")
	local template = folder and folder:FindFirstChild(key)
	local sa: SurfaceAppearance? = nil
	if template and template:IsA("SurfaceAppearance") then
		sa = template:Clone() :: SurfaceAppearance
	else
		local ok, made = pcall(function()
			local s = Instance.new("SurfaceAppearance")
			s.AlphaMode = Enum.AlphaMode.Transparency
			-- ColorMap is a plugin-security property the type definitions leave out (they know ColorMapContent
			-- only); the cast keeps the types gate green without changing what Studio does here
			local untyped: any = s
			untyped.ColorMap = id
			s.EmissiveMaskContent = Content.fromUri(id)
			return s
		end)
		if ok then
			sa = made
		elseif not surfaceWarned then
			surfaceWarned = true
			warn(
				`[VfxStage] surface "{key}": no ReplicatedStorage.VfxSurfaces.{key} template and this context cannot set ColorMap — drawing it with TextureID (opaque ground)`
			)
		end
	end
	if not sa then
		return false
	end
	local s = sa :: SurfaceAppearance
	pcall(function()
		s.EmissiveStrength = strength
	end)
	s.Parent = mp
	return true
end

-- WHERE A WRAPPED MARK'S POINTS LIE (the decal layer's "wrap"; a pure rule: a spec runs it against made ground).
-- cells x cells cells over a mark of w x d studs in `frame`; find(point on the mark's own plane) -> (where the ground
-- is, its normal) or nothing. A point lies a little off the ground along its normal (LIFT: a mark in the surface
-- flickers); one that finds no ground lies on the mark's own plane. Row by row, cells + 1 a row: VfxMesh.sheet's order.
local WRAP_LIFT = 0.06
local function wrapPoints(
	cells: number,
	w: number,
	d: number,
	frame: CFrame,
	find: (Vector3) -> (Vector3?, Vector3?)
): { Vector3 }
	local out = table.create((cells + 1) * (cells + 1))
	for j = 0, cells do
		for i = 0, cells do
			local flat = frame:PointToWorldSpace(Vector3.new((i / cells - 0.5) * w, 0, (j / cells - 0.5) * d))
			local hit, normal = find(flat)
			if hit then
				table.insert(out, hit + (if normal then normal else frame.UpVector) * WRAP_LIFT)
			else
				table.insert(out, flat + frame.UpVector * WRAP_LIFT)
			end
		end
	end
	return out
end

-- WHEN a wrapped mark is laid again: its place, its size and how it is turned, each to a share of one cell (a
-- hundredth of a stud had a growing mark cast its rays every frame; a mark that only turned was never laid again)
local function wrapKey(cells: number, w: number, d: number, frame: CFrame): string
	local step = math.max(math.min(w, d) / cells / 4, 0.02)
	local function q(v: number): number
		return math.floor(v / step + 0.5)
	end
	local p, look = frame.Position, frame.LookVector
	return string.format(
		"%d %d %d %d %d %d %d %d",
		q(p.X),
		q(p.Y),
		q(p.Z),
		q(w),
		q(d),
		math.floor(look.X * 64 + 0.5),
		math.floor(look.Y * 64 + 0.5),
		math.floor(look.Z * 64 + 0.5)
	)
end

-- how many mesh layers have shown their stand-in on this client (VfxStage.standIns: a playtest reads it)
local standInsShown = 0

local function plainPart(name: string, parent: Instance): Part
	local p = Instance.new("Part")
	p.Name = name
	p.Anchored = true
	p.CanCollide = false
	p.CanQuery = false
	p.CanTouch = false
	p.CastShadow = false
	p.Massless = true
	p.Transparency = 1
	p.Size = Vector3.one * 0.2
	p.Parent = parent
	return p
end

-- ---------------------------------------------------------------- camera feel (shared by every stage)
-- shake: sum of active layers' amplitudes (degrees) as smooth noise; fov: sum of deltas; both re-applied per frame.
-- Every running stage holds its own share (stage.contrib: shake degrees, fov degrees, bloom boost); the totals are
-- summed each frame from the stages that are still TICKING, so a stage whose script died (character script on
-- death) stops counting instead of leaving the camera shaking / bloom raised forever. Bloom: the boost goes on top
-- of the place's intensity captured when the first boost starts, and that is restored when the last one ends.
local feel = {
	appliedFov = 0,
	t = 0,
	bound = false,
	lastShake = CFrame.identity,
	shakenCF = nil :: CFrame?, -- the camera CFrame we wrote with the shake on it
	bloomEffect = nil :: BloomEffect?,
	bloomBase = 0,
}
local live: { [any]: boolean } = {}

local function totals(): (number, number, number, number, number)
	local shake, fov, bloom, kx, ky = 0, 0, 0, 0, 0
	local now = os.clock()
	for st in live do
		local idle = now - st.lastTick
		if idle > 10 then
			live[st] = nil -- its script is gone for good
		elseif idle <= 0.5 and not st.finished then
			shake += st.contrib.shake
			fov += st.contrib.fov
			bloom += st.contrib.bloom
			kx += st.contrib.kickX
			ky += st.contrib.kickY
		end
	end
	return shake, fov, bloom, kx, ky
end

local function applyBloom()
	local _, _, boost = totals()
	if boost > 1e-4 then
		local b = feel.bloomEffect
		if not b or not b.Parent then
			b = Lighting:FindFirstChildOfClass("BloomEffect")
			feel.bloomEffect = b
			feel.bloomBase = if b then b.Intensity else 0
		end
		if b then
			b.Intensity = feel.bloomBase + boost
		end
	elseif feel.bloomEffect then
		feel.bloomEffect.Intensity = feel.bloomBase
		feel.bloomEffect = nil
	end
end

local function applyFeel(dt: number)
	applyBloom() -- every frame, so a stage whose script died drops its bloom too (not only shake / fov)
	local camera = Workspace.CurrentCamera
	if not camera then
		return
	end
	feel.t += dt
	local shake, fov, _, kx, ky = totals()
	if shake > 0.001 or math.abs(kx) + math.abs(ky) > 0.001 then
		local s = math.rad(shake)
		local t = feel.t * 22
		-- the KICK: the picture jolts WITH the strike (kick [x, y] in degrees, x right, y up), the camera turns the
		-- other way; it rides in the same offset the unshake takes back off
		local offset = CFrame.Angles(math.rad(ky), math.rad(kx), 0)
			* CFrame.Angles(math.noise(t, 0.3) * s, math.noise(t, 4.1) * s, math.noise(t, 9.7) * s * 0.6)
		camera.CFrame = camera.CFrame * offset
		feel.lastShake = offset
		feel.shakenCF = camera.CFrame
	end
	if math.abs(fov - feel.appliedFov) > 1e-3 then
		camera.FieldOfView += fov - feel.appliedFov
		feel.appliedFov = fov
	end
end

-- client: the shake goes on after the camera scripts and comes off again before them, so a camera that does not
-- rewrite its CFrame every frame (a scripted / fixed camera) never drifts
local function bindFeel()
	if feel.bound or not RunService:IsClient() then
		return
	end
	feel.bound = true
	RunService:BindToRenderStep("KitVfxStageUnshake", Enum.RenderPriority.Camera.Value - 1, function()
		local camera = Workspace.CurrentCamera
		local shaken = feel.shakenCF
		-- undo only if nobody moved the camera since we shook it (a tweened / Heartbeat-driven cutscene camera
		-- already wrote a clean CFrame: undoing would cancel the shake)
		if camera and shaken and feel.lastShake ~= CFrame.identity then
			local c = camera.CFrame
			if (c.Position - shaken.Position).Magnitude < 1e-3 and c.LookVector:Dot(shaken.LookVector) > 0.999999 then
				camera.CFrame = c * feel.lastShake:Inverse()
			end
		end
		feel.lastShake = CFrame.identity
		feel.shakenCF = nil
	end)
	RunService:BindToRenderStep("KitVfxStageFeel", Enum.RenderPriority.Camera.Value + 1, applyFeel)
end

-- distance falloff from the local camera: 1 at the effect, 0 at radius
-- swarm noise: smooth 3D value noise and its curl (a divergence-free swirl: smoke and embers curl instead of flying
-- straight). The browser player runs the same formulas (player.js curl3)
local function hash3(i: number, j: number, k: number): number
	local x = math.sin(i * 127.1 + j * 311.7 + k * 74.7) * 43758.5453
	return x - math.floor(x)
end

local function noise3(x: number, y: number, z: number): number
	local i, j, k = math.floor(x), math.floor(y), math.floor(z)
	local fx, fy, fz = x - i, y - j, z - k
	local ux, uy, uz = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy), fz * fz * (3 - 2 * fz)
	local function lerp(a: number, b: number, t: number): number
		return a + (b - a) * t
	end
	local x00 = lerp(hash3(i, j, k), hash3(i + 1, j, k), ux)
	local x10 = lerp(hash3(i, j + 1, k), hash3(i + 1, j + 1, k), ux)
	local x01 = lerp(hash3(i, j, k + 1), hash3(i + 1, j, k + 1), ux)
	local x11 = lerp(hash3(i, j + 1, k + 1), hash3(i + 1, j + 1, k + 1), ux)
	return lerp(lerp(x00, x10, uy), lerp(x01, x11, uy), uz) * 2 - 1
end

local function curl3(x: number, y: number, z: number): Vector3
	local e = 0.1
	local function psi(px: number, py: number, pz: number): Vector3
		return Vector3.new(
			noise3(px, py, pz),
			noise3(px + 31.4, py + 7.1, pz + 2.9),
			noise3(px + 11.3, py + 53.7, pz + 17.2)
		)
	end
	local dx1, dx0 = psi(x + e, y, z), psi(x - e, y, z)
	local dy1, dy0 = psi(x, y + e, z), psi(x, y - e, z)
	local dz1, dz0 = psi(x, y, z + e), psi(x, y, z - e)
	local k = 1 / (2 * e)
	return Vector3.new(
		((dy1.Z - dy0.Z) - (dz1.Y - dz0.Y)) * k,
		((dz1.X - dz0.X) - (dx1.Z - dx0.Z)) * k,
		((dx1.Y - dx0.Y) - (dy1.X - dy0.X)) * k
	)
end

-- lit variants (a sprite's `lit` = { left, right, top, back, front } textures baked with the key light from that side,
-- kit/vfx/fxlab.py `light`): pick the one whose light matches where the world's sun is, seen from the camera. The
-- Roblox stand-in for six-way lighting (board/plans/archive/aaa-vfx-research.md)
local LIT_ORDER = { "top", "left", "right", "front", "back" }
local function pickLit(lit: any): string?
	local camera = Workspace.CurrentCamera
	local sunDir = Lighting:GetSunDirection() -- toward the sun
	local want = "top"
	if camera and sunDir.Y < 0.6 then -- a sun above ~37 degrees lights the TOP (a daylight test: 44 degrees picked the dark back-lit puffs)
		local travel = Vector3.new(-sunDir.X, 0, -sunDir.Z) -- the light's way across the ground
		local right = camera.CFrame.RightVector
		local look = Vector3.new(camera.CFrame.LookVector.X, 0, camera.CFrame.LookVector.Z)
		local dr, df = travel:Dot(right), travel:Dot(if look.Magnitude > 1e-3 then look.Unit else look)
		if math.abs(dr) >= math.abs(df) then
			want = if dr > 0 then "left" else "right" -- travelling right = lit from the left
		else
			want = if df > 0 then "front" else "back" -- travelling away from the camera = lit from its side
		end
	end
	if lit[want] then
		return lit[want]
	end
	for _, k in LIT_ORDER do
		if lit[k] then
			return lit[k]
		end
	end
	return nil
end

-- view variants (impostors: a sprite's `views` = { ["0"] = tex, ["90"] = tex, ... } - the same simulated cloud seen from
-- round the side, kit/vfx/gpusim.py view_variant): the one nearest the camera's angle round the effect (0 = the camera on
-- the effect's +Z side, positive = the camera moved to its LEFT, as gpusim turns the volume). The player: same rule
local function pickView(views: any, frame: CFrame): string?
	local camera = Workspace.CurrentCamera
	local yaw = 0
	if camera then
		local rel = frame:PointToObjectSpace(camera.CFrame.Position)
		yaw = math.deg(math.atan2(-rel.X, rel.Z)) % 360
	end
	local best, bestD = nil, math.huge
	for key, tex in views do
		local k = tonumber(key)
		if k then
			local d = math.abs(((yaw - k) + 180) % 360 - 180)
			if d < bestD then
				best, bestD = tex, d
			end
		end
	end
	return best
end

local function falloff(pos: Vector3, radius: number?): number
	local camera = Workspace.CurrentCamera
	if not camera or not radius then
		return 1
	end
	return math.clamp(1 - (camera.CFrame.Position - pos).Magnitude / radius, 0, 1)
end

-- every texture a preset uses, loaded before it plays (a texture shown for the first time arrives a few frames late:
-- a burst that fires in those frames is lost). Yields; call it once per preset, early (on equip, on join).
function VfxStage.preload(preset: any, textures: any)
	local ids: { Instance }, seen = {}, {}
	for _, el in preset.layers or {} do
		local id = textureId(textures, el.texture)
		if id ~= "" and not seen[id] then
			seen[id] = true
			local d = Instance.new("Decal")
			d.Texture = id
			table.insert(ids, d)
		end
		-- a `surface` layer's SurfaceAppearance streams its maps on its own (measured: > 1 s on first use, the arc drew
		-- pale and untextured): warm one with the same maps where this context may set them (Studio, the booth)
		if el.surface ~= nil and id ~= "" and not seen["sa:" .. id] then
			seen["sa:" .. id] = true
			pcall(function()
				local sa: any = Instance.new("SurfaceAppearance") -- ColorMap: not in the type definitions, real in the engine
				sa.ColorMap = id
				sa.EmissiveMaskContent = Content.fromUri(id)
				table.insert(ids, sa)
			end)
		end
	end
	if #ids > 0 then
		pcall(function()
			game:GetService("ContentProvider"):PreloadAsync(ids)
		end)
	end
	for _, d in ids do
		d:Destroy()
	end
end

-- ---------------------------------------------------------------- the stage
function VfxStage.play(preset: any, where: CFrame, opts: any?): Stage
	local o = opts or {}
	local scale = o.scale or 1
	local palette = preset.palette or {}
	if type(o.palette) == "table" then
		palette = table.clone(palette)
		for k, v in o.palette do
			palette[k] = v
		end
	end
	checkPalette(preset, tostring(o.name or "effect"))
	local textures = o.textures
	local anchors = o.anchors or {}
	local isClient = RunService:IsClient()
	local booth = o.booth == true -- edit-mode capture: camera feel is applied directly, every frame
	local root = Instance.new("Folder")
	root.Name = "VfxStage_" .. tostring(o.name or "effect")
	root.Parent = o.parent or Workspace
	local base = plainPart("Origin", root)
	base.CFrame = where
	-- attach: the effect rides o.follow (a part) at o.offset; `where` is re-read every frame (the closures below
	-- see the new value) and the stage runs until stop() unless the preset gives a duration
	local followPart: BasePart? = o.follow
	local followOffset: CFrame = o.offset or CFrame.identity
	local attachMode = preset.mode == "attach"

	local self: any = {
		contrib = { shake = 0, fov = 0, bloom = 0, kickX = 0, kickY = 0 },
		lastTick = os.clock(),
		time = 0,
		duration = preset.duration or (if attachMode then math.huge else 5),
		frozen = false,
		timeScale = 1,
		finished = false,
		released = false,
	}
	local cleanups: { () -> () } = {}
	local updaters: { (t: number, dt: number) -> () } = {}
	-- want: the layer wants this emitter emitting (rate layers); it is only Enabled while the clock runs — a frozen
	-- emitter (TimeScale 0) still EMITS, so a freeze / hit-stop / capture hold would pile sprites up (measured 2026-10-10)
	local emitters: { { pe: ParticleEmitter, scale: number, want: boolean } } = {}
	local clockRunning = true
	local scrolling: { { beam: Beam, speed: number } } = {} -- beam textures scroll on the stage clock too
	-- the low-graphics guard (src/kit/VfxEmit.luau): at a low graphics level (or Automatic: the engine may have chosen
	-- one) the engine throttles a ParticleEmitter's Rate by 50-80 %, so a sprite's `rate` is thrown by Emit(n) on the
	-- stage's own clock instead (o.emitGuard = true / false forces it; read once a play: the setting can change)
	local emitGuard = VfxEmit.guarded(
		VfxEmit.levelOf((function(): any
			local ok, saved = pcall(function(): any
				return (UserSettings():GetService("UserGameSettings") :: any).SavedQualityLevel
			end)
			return if ok then saved else nil
		end)()),
		o.emitGuard
	)
	self.emitGuard = emitGuard -- (read by the specs and a Studio probe: whether this play throws its rates itself)

	-- points --------------------------------------------------------------
	local function localPoint(v: any): Vector3
		if type(v) == "table" then
			return Vector3.new(v[1], v[2], v[3]) * scale
		end
		if v == "target" and o.target then
			return where:PointToObjectSpace(o.target)
		end
		local named = (preset.points or {})[v]
		if named then
			return Vector3.new(named[1], named[2], named[3]) * scale
		end
		return Vector3.zero
	end
	local function worldPoint(v: any): Vector3
		if type(v) == "string" and string.sub(v, 1, 1) == "@" then
			-- "@tip" = the anchor; "@tip^170" = 170 studs along the anchor's +Y (a sword's length axis) from it, so a
			-- pillar standing on the blade swings WITH the blade
			local name, along = string.match(v, "^@([%w_]+)%^(%-?[%d%.]+)$")
			local a = anchors[name or string.sub(v, 2)]
			local dist = if along then tonumber(along) or 0 else 0
			if a and a:IsA("Attachment") then
				local cf = (a :: Attachment).WorldCFrame
				return cf.Position + cf.UpVector * dist * scale
			elseif a and a:IsA("BasePart") then
				local cf = (a :: BasePart).CFrame
				return cf.Position + cf.UpVector * dist * scale
			end
			return where.Position
		end
		return where:PointToWorldSpace(localPoint(v or { 0, 0, 0 }))
	end
	-- frame at a point; +Y aimed at `aim` (a point) when given, else the effect's own orientation; `rot` degrees
	local function frameAt(point: any, aim: any, rot: any): CFrame
		local p = worldPoint(point)
		local cf: CFrame
		if aim ~= nil then
			local a = worldPoint(aim)
			if (a - p).Magnitude > 1e-3 then
				cf = CFrame.lookAt(p, a) * CFrame.Angles(-math.pi / 2, 0, 0)
			else
				cf = CFrame.new(p) * where.Rotation
			end
		else
			cf = CFrame.new(p) * where.Rotation
		end
		if rot then
			cf *= CFrame.Angles(math.rad(rot[1] or 0), math.rad(rot[2] or 0), math.rad(rot[3] or 0))
		end
		return cf
	end

	local function lifeOf(el: any): number
		return math.max(el.life or 1, 1e-3)
	end

	-- builders: each registers an updater (called every frame with the stage time) -------------------------
	local builders: { [string]: (el: any, flat: boolean?) -> () } = {}

	builders.sprite = function(el)
		local holder = plainPart("Sprite_" .. tostring(el.name or ""), root)
		holder.CFrame = frameAt(el.point, el.aim, el.rotate)
		local parentFor: Instance = holder
		if el.shape then
			local sz = el.shape.size or { 4, 4, 4 }
			holder.Size = Vector3.new(sz[1], sz[2], sz[3]) * scale
		else
			local att = Instance.new("Attachment")
			att.Parent = holder
			parentFor = att
		end
		local follow = type(el.point) == "string" and string.sub(el.point, 1, 1) == "@"
		local function emitter(over: any): ParticleEmitter
			local function pick(key: string): any
				if over[key] ~= nil then
					return over[key]
				end
				return el[key]
			end
			local pe = Instance.new("ParticleEmitter")
			pe.Name = el.name or "Sprite"
			pe.Enabled = false
			pe.Rate = 0
			local tex = el.texture
			if type(el.views) == "table" then
				tex = pickView(el.views, where) or tex
			elseif type(el.lit) == "table" then
				tex = pickLit(el.lit) or tex
			end
			pe.Texture = textureId(textures, tex)
			local life = el.lifetime or { 1, 1 }
			local lifeK = over.lifeScale or 1
			pe.Lifetime = if type(life) == "number"
				then NumberRange.new(life * lifeK)
				else NumberRange.new(life[1] * lifeK, life[2] * lifeK)
			pe.Speed = range(el.speed or 0, scale)
			local spread = el.spread or 0
			pe.SpreadAngle = if type(spread) == "number"
				then Vector2.new(spread, spread)
				else Vector2.new(spread[1], spread[2])
			pe.Size = numberSeq(el.size or 1, scale * (over.sizeScale or 1))
			pe.Transparency = numberSeq(pick("transparency") or 0, 1)
			if el.squash then
				pe.Squash = numberSeq(el.squash, 1)
			end
			pe.Color = colorSeq(pick("color") or { 255, 255, 255 }, palette)
			pe.Brightness = pick("brightness") or 1
			pe.LightEmission = pick("lightEmission") or 0
			pe.LightInfluence = el.lightInfluence or 0
			pe.ZOffset = (el.zOffset or 0) * scale + (over.zOffset or 0) * scale
			pe.Drag = el.drag or 0
			pe.WindAffectsDrag = el.wind == true -- drift with Workspace.GlobalWind (needs Drag > 0)
			local acc = el.acceleration or { 0, 0, 0 }
			pe.Acceleration = Vector3.new(acc[1], acc[2], acc[3]) * scale
			pe.Rotation = range(el.rotation or 0, 1)
			pe.RotSpeed = range(el.rotSpeed or 0, 1)
			pe.Orientation = (Enum.ParticleOrientation :: any)[el.orientation or "FacingCamera"]
			pe.EmissionDirection = (Enum.NormalId :: any)[el.direction or "Top"]
			pe.LockedToPart = el.lockedToPart == true or follow
			pe.VelocityInheritance = el.velocityInheritance or 0
			if el.shape then
				pe.Shape = (Enum.ParticleEmitterShape :: any)[el.shape.type or "Sphere"]
				pe.ShapeStyle = (Enum.ParticleEmitterShapeStyle :: any)[el.shape.style or "Volume"]
				pe.ShapeInOut = (Enum.ParticleEmitterShapeInOut :: any)[el.shape.inOut or "Outward"]
				pe.ShapePartial = el.shape.partial or 1
			end
			local fb = el.flipbook
			if fb then
				local layout = fb.layout or "4x4"
				if type(layout) == "table" then
					pe.FlipbookLayout = Enum.ParticleFlipbookLayout.Custom
					pe.FlipbookSizeX = layout[1]
					pe.FlipbookSizeY = layout[2]
				else
					pe.FlipbookLayout = (Enum.ParticleFlipbookLayout :: any)["Grid" .. layout]
				end
				pe.FlipbookMode = (Enum.ParticleFlipbookMode :: any)[fb.mode or "OneShot"]
				pe.FlipbookFramerate = range(fb.fps or 24, 1)
				pe.FlipbookStartRandom = fb.startRandom == true
				pe.FlipbookBlendFrames = fb.blend ~= false
			end
			pe.Parent = parentFor
			table.insert(emitters, { pe = pe, scale = el.timeScale or 1, want = false })
			return pe
		end
		local main = emitter({})
		local twin = if el.twin then emitter(el.twin) else nil
		local function want(pe: ParticleEmitter, on: boolean)
			for _, e in emitters do
				if e.pe == pe then
					e.want = on
					pe.Enabled = on and clockRunning and not self.released
					return
				end
			end
		end
		local emitted, enabled = false, false
		local rate = el.rate or 0
		local for_ = el["for"] or (if attachMode then math.huge else 0)
		-- the guard's clock (VfxEmit.step): where the rate was last paid up to, and the fraction carried (main, twin)
		local paidTo: number? = nil
		local carry, twinCarry = 0, 0
		table.insert(updaters, function(t)
			if follow then
				holder.CFrame = frameAt(el.point, el.aim, el.rotate)
			end
			if t < (el.at or 0) then
				return
			end
			if not emitted and (el.count or 0) > 0 and not self.released then
				emitted = true
				main:Emit(el.count)
				if twin then
					twin:Emit(el.twin.count or el.count)
				end
			end
			if rate > 0 and emitGuard then
				-- low graphics: the Rate stays 0 and the stage throws what it owes, each frame of its own clock
				local at = el.at or 0
				local stopAt = at + for_
				local from = paidTo or at
				local upTo = math.min(t, stopAt)
				paidTo = math.max(from, upTo)
				if upTo > from and clockRunning and not self.released then
					local n
					n, carry = VfxEmit.step(rate, upTo - from, carry)
					if n > 0 then
						main:Emit(n)
					end
					if twin then
						n, twinCarry = VfxEmit.step(el.twin.rate or rate, upTo - from, twinCarry)
						if n > 0 then
							twin:Emit(n)
						end
					end
				end
			elseif rate > 0 then
				local on = t < (el.at or 0) + for_
				if on ~= enabled then
					enabled = on
					main.Rate = rate
					want(main, on)
					if twin then
						twin.Rate = el.twin.rate or rate
						want(twin, on)
					end
				end
			end
		end)
	end

	-- plane: "camera" (default: a ribbon that always faces the camera) | "up" (a vertical WALL of light along the
	-- path, its width standing up) | "flat" (a sheet lying along the path, its width sideways). Measured: with
	-- FaceCamera off a Beam is one-sided and its width runs along Attachment0's Y, so a wall is two beams facing
	-- opposite ways (both sides seen).
	builders.beam = function(el)
		local copies = math.max(1, el.copies or 1)
		local life = lifeOf(el)
		local made = {}
		local id = textureId(textures, el.texture)
		local plane = el.plane or "camera"
		local faces: { number } = if plane == "camera" then { 0 } else { 1, -1 }
		for c = 1, copies do
			local jitter = (el.jitter or 0) * scale
			local off = Vector3.new(rng:NextNumber(-1, 1), rng:NextNumber(-1, 1), rng:NextNumber(-1, 1)) * jitter
			local speeds = el.textureSpeed or 1
			local speed = if type(speeds) == "table"
				then speeds[1] + (speeds[2] - speeds[1]) * rng:NextNumber()
				else speeds
			for _, face in faces do
				local a0 = Instance.new("Attachment")
				local a1 = Instance.new("Attachment")
				a0.Parent = base
				a1.Parent = base
				local b = Instance.new("Beam")
				b.Name = el.name or "Beam"
				b.Attachment0 = a0
				b.Attachment1 = a1
				b.Texture = id
				b.TextureMode = (Enum.TextureMode :: any)[el.textureMode or "Wrap"]
				b.TextureLength = (el.textureLength or 10) * scale
				b.TextureSpeed = speed
				b.FaceCamera = plane == "camera"
				b.LightEmission = el.lightEmission or 1
				b.LightInfluence = el.lightInfluence or 0
				b.Segments = el.segments or 10
				b.ZOffset = (el.zOffset or 0) + (c - 1) * (el.zStep or 0.05)
				b.Color = colorSeq(el.color or { 255, 255, 255 }, palette)
				b.Enabled = false
				b.Parent = base
				table.insert(made, { b = b, a0 = a0, a1 = a1, off = off, face = face, copy = c })
				table.insert(scrolling, { beam = b, speed = b.TextureSpeed })
			end
		end
		local width = el.width or 1
		local taper = el.taper or { 1, 1 }
		table.insert(updaters, function(t)
			local at = el.at or 0
			local u = (t - at) / life
			local alive = t >= at and u <= 1
			for _, m in made do
				m.b.Enabled = alive
			end
			if not alive then
				return
			end
			local p0 = worldPoint(el.from)
			local p1 = worldPoint(el.to)
			local grow = if el.grow then ease((t - at) / el.grow, el.growEase) else 1
			local w = numAt(width, u, 1) * scale
			local vis = 1 - numAt(el.fade, u, 0)
			local bright = numAt(el.brightness, u, 1)
			local curve = el.curve or { 0, 0 }
			-- the wall's frame: width along vY, the visible side along -vZ (flipped for the second face)
			local dir = p1 - p0
			dir = if dir.Magnitude > 1e-4 then dir.Unit else Vector3.zAxis
			local vY: Vector3, vZ: Vector3
			if plane == "flat" then
				vY = dir:Cross(Vector3.yAxis)
				vY = if vY.Magnitude > 1e-4 then vY.Unit else Vector3.xAxis
				vZ = dir:Cross(vY).Unit
			else
				local w0 = if math.abs(dir.Y) < 0.95 then Vector3.yAxis else Vector3.xAxis
				vY = (w0 - dir * dir:Dot(w0)).Unit
				vZ = dir:Cross(vY).Unit
			end
			for _, m in made do
				local k = if copies > 1 then (m.copy - 1) / (copies - 1) else 0
				local q0 = p0 + m.off * 0.25
				local q1 = p0:Lerp(p1, grow) + m.off
				if m.face == 0 and el.curveAxis then -- the curve bends along this (effect-space) axis
					local ax = where:VectorToWorldSpace(Vector3.new(el.curveAxis[1], el.curveAxis[2], el.curveAxis[3]))
					ax = if ax.Magnitude > 1e-4 then ax.Unit else Vector3.xAxis
					local up = if math.abs(ax.Y) < 0.95 then Vector3.yAxis else Vector3.xAxis
					local z = ax:Cross(up).Unit
					local y = z:Cross(ax)
					m.a0.WorldCFrame = CFrame.fromMatrix(q0, ax, y, z)
					m.a1.WorldCFrame = CFrame.fromMatrix(q1, ax, y, z)
				elseif m.face == 0 then
					m.a0.WorldPosition = q0
					m.a1.WorldPosition = q1
				else
					local z = vZ * m.face
					local x = dir -- a Beam bends along Attachment X: both faces share it, so a curve matches
					local y = z:Cross(x)
					m.a0.WorldCFrame = CFrame.fromMatrix(q0, x, y, z)
					m.a1.WorldCFrame = CFrame.fromMatrix(q1, x, y, z)
				end
				local wk = 1 + (el.widthSpread or 0) * (k - 0.5) * 2
				m.b.Width0 = w * taper[1] * wk
				m.b.Width1 = w * taper[2] * wk
				m.b.CurveSize0 = curve[1] * scale
				m.b.CurveSize1 = curve[2] * scale
				m.b.Brightness = bright
				m.b.Transparency =
					softEnds(fadedSeq(el.transparency, vis), if el.softEnds == nil then 0.12 else el.softEnds)
			end
		end)
	end

	-- outlines: ONE Model holding every outlined part of the effect, ONE Highlight on it (31 Highlights per client)
	local outlineModel: Model? = nil
	local function outlined(color: any): Instance
		if not outlineModel then
			local m = Instance.new("Model")
			m.Name = "Outlined"
			m.Parent = root
			local h = Instance.new("Highlight")
			h.FillTransparency = 1
			h.OutlineColor = colorAt(color, 0, palette)
			h.OutlineTransparency = 0
			h.DepthMode = Enum.HighlightDepthMode.Occluded
			h.Enabled = false
			h.Adornee = m
			h.Parent = m
			outlineModel = m
			lightUp(h, VfxHighlight.AMBIENT, true)
			table.insert(updaters, function()
				if not highlightSlots:holds(h) then
					lightUp(h, VfxHighlight.AMBIENT, true)
				end
			end)
			table.insert(cleanups, function()
				highlightSlots:release(h)
			end)
		end
		return outlineModel :: Model
	end

	builders.mesh = function(el)
		local life = lifeOf(el)
		-- A STAND-IN while the mesh is not there: a plain ball at the layer's own size, colour and transparency,
		-- drawn until the mesh is built - and for the whole layer when it never is (a build refused, or one that
		-- the engine finishes after the layer: ten cold Studio sessions, 2026-11-16 - an effect played as the avatar
		-- arrived drew NO mesh for its whole life). A mesh layer never plays invisible
		local standin: Part? = nil
		local standinShown = false
		if VfxMesh.SHAPES[el.shape or "ring"] then
			local p = plainPart("MeshStandIn", root)
			p.Shape = Enum.PartType.Ball
			p.Material = (Enum.Material :: any)[if el.toon then "SmoothPlastic" else (el.material or "Neon")]
			if el.outline ~= nil then -- (outlined as the mesh will be)
				p.Parent = outlined(el.outline)
			end
			standin = p
		end
		local flipStart = if el.flipbook and el.flipbook.startRandom then math.random(0, 63) else 0
		local built: VfxMesh.Built? = nil
		local part: BasePart? = nil
		local native = Vector3.one
		local middle = Vector3.zero -- (a sequence's first frame's middle, in the file's own units: "pivot": "origin")
		local shape = el.shape or "ring"
		task.spawn(function()
			if VfxMesh.SHAPES[shape] then
				local params = el.params
				if shape == "seq" then -- the baked frames: o.seq(name) (Vfx passes VfxPresets.seq.<name>)
					params = table.clone(el.params or {})
					params.data = if o.seq and params.seq then o.seq(params.seq) else nil
					if
						type(params.data) == "table"
						and type(params.data.frames) == "table"
						and type(params.data.frames[1]) == "table"
					then
						middle = Vector3.new(seqMiddle(params.data.frames[1]))
					end
					if params.data == nil then
						warn(
							`[VfxStage] mesh layer "{el.name}": no sequence "{tostring(params.seq)}" (kit/vfx/meshseq.py)`
						)
					end
				end
				local b, why = VfxMesh.build(shape, params, el.wobble, el.erode, el.critical)
				if b and self.finished then -- the stage ended while the mesh was being built (it yields)
					b.destroy()
					return
				end
				if b then
					built = b
					part = b.part
					native = b.native
					if standin then -- the mesh is here: its stand-in goes
						standin:Destroy()
						standin = nil
					end
				elseif why and string.sub(why, 1, 20) ~= "over the mesh budget" then
					-- (a build the budget turned away is counted in VfxMesh.stats(), not warned of: a burst would
					-- print a line a layer)
					warn(`[VfxStage] mesh layer "{el.name}" skipped: {why}`)
				end
			else
				local p = plainPart("Mesh", root)
				p.Shape = (Enum.PartType :: any)[shape] or Enum.PartType.Ball
				p.Transparency = 0
				part = p
			end
			local mp = part
			if not mp then
				return
			end
			mp.Name = el.name or "Mesh"
			mp.Material = (Enum.Material :: any)[if el.toon then "SmoothPlastic" else (el.material or "Neon")]
			-- a mirror (liquid metal, chrome): the part reflects the sky (the player's metal + envMap). Always written:
			-- the part comes from a pool, and one that was a mirror stayed one for the next layer that used it
			mp.Reflectance = if type(el.reflectance) == "number" then el.reflectance else 0
			if el.texture and mp:IsA("MeshPart") then
				local id = textureId(textures, el.texture)
				local strength = if type(el.surface) == "number" then el.surface else 5
				if not (el.surface ~= nil and id ~= "" and applySurface(mp :: MeshPart, el.texture, id, strength)) then
					(mp :: MeshPart).TextureID = id
				end
			end
			mp.Transparency = 1
			mp.Parent = if el.outline ~= nil then outlined(el.outline) else root
		end)
		table.insert(cleanups, function()
			if built then
				built.destroy()
			end
			if standin then
				standin:Destroy()
				standin = nil
			end
		end)
		-- forced perspective held on a drawing ("step"): the multiplier and the drawing it was read in
		local forcedHeld: number? = nil
		local forcedDrawing: number? = nil
		table.insert(updaters, function(t)
			local mp: BasePart? = part or standin
			if not mp then
				return
			end
			local at = el.at or 0
			if mp == standin and t >= at and (t - at) / life <= 1 and not standinShown then
				standinShown = true
				standInsShown += 1
			end
			if t < at or (t - at) / life > 1 then
				mp.Transparency = 1
				local b = built
				if b and t >= at then -- faded (the clock only runs forward): its EditableMesh back to the pool now
					built, part = nil, nil
					b.destroy()
				end
				return
			end
			-- step: the layer's clock held on drawings (12 = "on twos", the anime cadence)
			local age = if el.step then math.floor((t - at) * el.step) / el.step else t - at
			local u = age / life
			local grow = vecAt(el.scale or 1, u) * scale -- (studs to one of the mesh's own units)
			local size = native * grow
			local spin = spinAngle(el.spin, age, life)
			local cf = frameAt(el.point, el.aim, el.rotate)
			if type(el.forced) == "table" then -- forced perspective: the layer's size answers the camera's distance
				local cam = Workspace.CurrentCamera
				-- (a layer held on drawings - "step" - keeps its size for the whole drawing: read once when a drawing
				-- starts. It changed every frame: a layer on twos that still grew between its drawings)
				local drawing = if el.step then math.floor((t - at) * el.step) else nil
				if cam and (drawing == nil or drawing ~= forcedDrawing or forcedHeld == nil) then
					forcedHeld = forcedScale((cam.CFrame.Position - cf.Position).Magnitude, el.forced) -- (studs: `ref` is studs)
					forcedDrawing = drawing
				end
				if forcedHeld then
					size *= forcedHeld
					grow *= forcedHeld
				end
			end
			if el.move ~= nil then -- a position offset over life in the layer's frame (a cloud that rises, a cap that climbs)
				cf *= CFrame.new(vecAt(el.move, u) * scale)
			end
			-- "base": the shape STARTS at its point and runs along +Y (a beam shell, a cone, a pillar); the default
			-- for tube / cone / spiral, which are built from y = 0 up. Everything else is centred on its point.
			local pivot = el.pivot
				or (
					if shape == "tube"
							or shape == "crown"
							or shape == "cone"
							or shape == "spiral"
							or shape == "flame"
							or shape == "tongue"
							or shape == "bolt"
							or shape == "spikes"
						then "base"
						else "center"
				)
			if pivot == "base" then
				cf *= CFrame.new(0, size.Y / 2, 0)
			end
			cf *= CFrame.Angles(math.rad(spin.X), math.rad(spin.Y), math.rad(spin.Z))
			if pivot == "origin" then
				-- a sequence's OWN origin on the point (and it spins about that): the part is centred on its first frame's
				-- box, so it goes where that box's middle is (the player draws the mesh from its origin: the same place)
				cf *= CFrame.new(middle * grow)
			end
			if mp:IsA("Part") and (mp :: Part).Shape == Enum.PartType.Cylinder then
				size = Vector3.new(size.Y, size.X, size.Z)
				cf *= CFrame.Angles(0, 0, math.rad(90))
			end
			mp.Size = size
			mp.CFrame = cf
			mp.Transparency = numAt(el.transparency, u, 0)
			mp.Color = colorAt(el.color, u, palette)
			if el.surface ~= nil then -- the glow takes the layer's colour too
				local sa = mp:FindFirstChildOfClass("SurfaceAppearance")
				if sa then
					sa.EmissiveTint = mp.Color
				end
			end
			local scroll = el.uvScroll
			if built and scroll then
				built.scroll(Vector2.new(scroll[1] * age, scroll[2] * age))
			end
			if built and built.deform then
				built.deform(age)
			end
			if built and built.erode then
				built.erode(u)
			end
			if built and built.sweep and type(el.sweep) == "table" then -- an arc drawn in along itself and erased behind
				built.sweep(numAt(el.sweep.tail, u, 0), numAt(el.sweep.head, u, 1))
			end
			local fb = el.flipbook
			if built and fb then -- a flipbook sheet played on the mesh: step its UVs to the frame's cell
				local n = ({ ["2x2"] = 2, ["4x4"] = 4, ["8x8"] = 8 })[fb.layout or "4x4"] or 4
				local frames = n * n
				local f = sheetFrame(fb, u, age, frames, flipStart)
				built.cell(f % n, f // n, n, n)
			end
		end)
	end

	-- decal: a mark on the ground - a flat Decal on a thin part at the effect's height.
	-- "wrap": N (or true = 8) - the mark DRAPED over the real ground: Roblox has no projector (a Decal sits on one face
	-- of one part, so on a slope, a step or rubble a flat mark floats or is cut off), so the mark is a mesh sheet of
	-- N x N cells whose points are where rays cast down find the place (VfxMesh.sheet), its picture through a
	-- SurfaceAppearance (`kit vfx surfaces` makes its template: without one a live game cannot give a runtime mesh
	-- a picture with alpha). "reach" (studs, default 8): how far above and below the mark's own height the ground is
	-- looked for; a point that finds none lies at the mark's height. Players' characters, parts that do not collide
	-- and parts that cannot be seen are not ground (an NPC is). Laid again only when the mark moved, turned or grew by
	-- a share of a cell - ground that moves under a still mark is not followed. On a client only; the server's copy,
	-- a place with no EditableMesh and the browser player (its ground is flat) draw the flat mark.
	builders.decal = function(el)
		local life = lifeOf(el)
		local p = plainPart("Decal_" .. tostring(el.name or ""), root)
		local d = Instance.new("Decal")
		d.Face = Enum.NormalId.Top
		d.Texture = textureId(textures, el.texture)
		d.Transparency = 1
		d.Parent = p
		local cells = if el.wrap == true
			then 8
			elseif type(el.wrap) == "number" then math.clamp(math.floor(el.wrap), 2, 16)
			else 0
		local reach = (if type(el.reach) == "number" then el.reach else 8) * scale
		local sheet: VfxMesh.Sheet? = nil
		-- while the sheet is being built the flat mark is NOT shown (on uneven ground it would show cut off or floating
		-- for a few frames, then jump to the draped one); it stands in only once the build has failed
		local building = false
		if cells > 0 and isClient then
			building = true
			-- the sheet's own box must hold the mark wherever its points go (the engine culls by it): half the largest
			-- the mark gets, along its diagonal, and how far the ground is looked for
			local most = 0
			for k = 0, 8 do
				local sz = vecAt(el.size or 10, k / 8) * scale
				most = math.max(most, sz.X, sz.Z)
			end
			local box = math.max(64 * scale, most * 0.75 + reach + 1)
			task.spawn(function()
				local s = VfxMesh.sheet(cells, cells, box)
				building = false
				if not s then
					return -- (no mesh to be had: the flat mark stands)
				end
				if self.finished then
					s.destroy()
					return
				end
				local mp = s.part
				mp.Name = "Mark_" .. tostring(el.name or "")
				mp.Material = Enum.Material.SmoothPlastic
				local id = textureId(textures, el.texture)
				if id ~= "" and not applySurface(mp, el.texture, id, 0) then
					mp.TextureID = id
				end
				mp.Transparency = 1
				mp.Parent = root
				sheet = s
			end)
			table.insert(cleanups, function()
				if sheet then
					sheet.destroy()
				end
			end)
		end
		local laid: string? = nil -- where the sheet was last laid (rays are cast again only when the mark moved, turned or grew)
		table.insert(updaters, function(t)
			local at = el.at or 0
			local u = (t - at) / life
			if t < at or u > 1 then
				d.Transparency = 1
				if sheet then
					sheet.part.Transparency = 1
				end
				return
			end
			local sz = vecAt(el.size or 10, u) * scale
			local rot = el.rotate or { 0, 0, 0 }
			local centre = worldPoint(el.point or { 0, 0, 0 })
			local frame = CFrame.new(centre) * where.Rotation * CFrame.Angles(0, math.rad(rot[2] or 0), 0)
			local glow = numAt(el.glow, u, 1)
			local c = colorAt(el.color, u, palette)
			local s = sheet
			if s then
				d.Transparency = 1
				local key = wrapKey(cells, sz.X, sz.Z, frame)
				if key ~= laid then
					laid = key
					local rp = RaycastParams.new()
					rp.FilterType = Enum.RaycastFilterType.Exclude
					rp.RespectCanCollide = true -- (a trigger or a zone part is not ground)
					local skip: { Instance } = { root }
					for _, pl in Players:GetPlayers() do
						if pl.Character then
							table.insert(skip, pl.Character)
						end
					end
					rp.FilterDescendantsInstances = skip
					local up = frame.UpVector
					local points = wrapPoints(cells, sz.X, sz.Z, frame, function(from: Vector3): (Vector3?, Vector3?)
						local hit = Workspace:Raycast(from + up * reach, -up * reach * 2, rp)
						if hit and hit.Instance.Transparency < 1 then -- (nothing you cannot see is ground either)
							return hit.Position, hit.Normal
						end
						return nil, nil
					end)
					s.set(points, centre)
				end
				local tint = Color3.new(math.min(c.R * glow, 1), math.min(c.G * glow, 1), math.min(c.B * glow, 1))
				s.part.Color = tint
				-- (seen in the engine, 2026-11-15: a part's Color does not tint a SurfaceAppearance's picture - the mark
				-- drew grey; the appearance's own Color does, and a glow above 1 is its emissive)
				local sa = s.part:FindFirstChildOfClass("SurfaceAppearance")
				if sa then
					pcall(function()
						sa.Color = tint
						sa.EmissiveTint = c
						sa.EmissiveStrength = math.max(glow - 1, 0)
					end)
				end
				s.part.Transparency = numAt(el.transparency, u, 0)
				return
			end
			if building then
				d.Transparency = 1
				return
			end
			p.Size = Vector3.new(sz.X, 0.05, sz.Z)
			p.CFrame = frame + Vector3.new(0, 0.03, 0)
			d.Color3 = Color3.new(c.R * glow, c.G * glow, c.B * glow)
			d.Transparency = numAt(el.transparency, u, 0)
		end)
	end

	builders.light = function(el)
		local life = lifeOf(el)
		-- type: point (all round) | spot (a cone along the layer's +Y: aim it with `aim` / `rotate`) | surface (a wide
		-- light thrown from a `size` [w, d] panel, e.g. the front of a blast)
		local kind = el.type or "point"
		local holder: Instance
		local light: Light
		if kind == "surface" then
			local panel = plainPart("Light_" .. tostring(el.name or ""), root)
			local sz = el.size or { 6, 6 }
			panel.Size = Vector3.new(sz[1], 0.2, sz[2] or sz[1]) * scale
			local sl = Instance.new("SurfaceLight")
			sl.Face = Enum.NormalId.Top
			sl.Angle = el.angle or 90
			holder, light = panel, sl
		else
			local att = Instance.new("Attachment")
			-- named like the surface panel: a probe (tests/playtest/vfx_stage_parity) and a dev in the Explorer tell the
			-- layers' lights apart
			att.Name = "Light_" .. tostring(el.name or "")
			att.Parent = base
			if kind == "spot" then
				local sp = Instance.new("SpotLight")
				sp.Face = Enum.NormalId.Top
				sp.Angle = el.angle or 60
				light = sp
			else
				light = Instance.new("PointLight")
			end
			holder = att
		end
		light.Shadows = el.shadows == true
		light.Color = colorAt(el.color, 0, palette)
		light.Enabled = false
		light.Parent = holder
		table.insert(updaters, function(t)
			local at = el.at or 0
			local u = (t - at) / life
			local alive = t >= at and u <= 1
			light.Enabled = alive
			if not alive then
				return
			end
			if kind == "point" then
				(holder :: Attachment).WorldPosition = worldPoint(el.point or { 0, 0, 0 })
			elseif kind == "spot" then
				(holder :: Attachment).WorldCFrame = frameAt(el.point or { 0, 0, 0 }, el.aim, el.rotate)
			else
				(holder :: BasePart).CFrame = frameAt(el.point or { 0, 0, 0 }, el.aim, el.rotate)
			end
			light.Brightness = numAt(el.brightness, u, 1)
			local lit: any = light -- Point / Spot / SurfaceLight all have Range, the Light base class does not
			lit.Range = math.min(numAt(el.range, u, 16) * scale, 60)
			light.Color = colorAt(el.color, u, palette)
		end)
	end

	builders.debris = function(el)
		local life = lifeOf(el)
		local chunks: { any } = {}
		local function pair(v: any, default: { number }): { number }
			if type(v) == "number" then
				return { v, v }
			end
			return if type(v) == "table" then v else default
		end
		local size = pair(el.size, { 0.5, 1.5 })
		local speed = pair(el.speed, { 20, 40 })
		local spread = math.rad(el.spread or 60)
		local g = (el.gravity or 120) * scale
		-- floor "world": real physics against the place (impacts on walls); "hit" (default): a floor at the effect's height
		local world = el.floor == "world" and isClient
		local started = false
		local rocks: { VfxMesh.Built } = {}
		local stillAt: number? = nil -- (how many pieces lay still and unchanged after the last step: the early stop)
		-- "pieces": a fracture plan (kit/vfx/fracture.py; o.fracture(name), Vfx passes VfxPresets.fractures.<name>):
		-- the chunks are the slab's OWN pieces, each starting where it sat in the slab, pushed as the plan says, and
		-- leaving when the break reaches it. The flight below is the same for them as for thrown rocks
		local plan: any = nil
		if type(el.pieces) == "string" then
			plan = if o.fracture then o.fracture(el.pieces) else nil
			if type(plan) ~= "table" or type(plan.pieces) ~= "table" or type(plan.size) ~= "table" then
				warn(`[VfxStage] debris layer "{tostring(el.name)}": no fracture plan "{el.pieces}" (kit vfx fracture)`)
				plan = nil
			end
		end
		-- a layer that names a plan the game does not have flies NOTHING (stray rocks would pass for the break)
		local lost = type(el.pieces) == "string" and plan == nil
		local shards: { [number]: VfxMesh.Built } = {}
		if plan then
			task.spawn(function()
				for i, pc in plan.pieces do
					local b = VfxMesh.build("piece", {
						points = pc.points,
						height = plan.size[3],
						centre = pc.centre,
						slab = { plan.size[1], plan.size[2] },
					})
					if not b then
						break -- no EditableMesh here: the pieces stay blocks of their own size
					end
					if self.finished then
						b.destroy()
						break
					end
					shards[i] = b
					if not started then
						b.part.Parent = nil
						continue
					end
					-- built after the layer started (a first play that was not prewarmed): the piece flew as a block
					-- of its own size until now - its real solid takes the block's place
					for _, ch in chunks do
						if ch.shard == i then
							local old: BasePart = ch.part
							b.part.Size = old.Size
							b.part.Color = old.Color
							b.part.Material = old.Material
							b.part.Transparency = old.Transparency
							b.part.CFrame = old.CFrame
							b.part.Parent = old.Parent
							if not old.Anchored then -- (a piece the engine's physics is flying: the solid flies on as it was)
								b.part.CanCollide = true
								VfxDebris.mark(b.part) -- (the world only: never a character, never another piece, never a raycast)
								b.part.Massless = false
								b.part.CustomPhysicalProperties = old.CustomPhysicalProperties
								b.part.Anchored = false
								b.part.AssemblyLinearVelocity = old.AssemblyLinearVelocity
								b.part.AssemblyAngularVelocity = old.AssemblyAngularVelocity
							end
							ch.part = b.part
							old:Destroy()
						end
					end
				end
			end)
			table.insert(cleanups, function()
				for _, b in shards do
					b.destroy()
				end
			end)
		end
		if el.shape == "rock" then
			task.spawn(function()
				for i = 1, el.count or 6 do
					local b = VfxMesh.build("rock", {
						seed = i + (el.seed or 0) * 37,
						cuts = el.cuts,
						jag = el.jag,
						spike = el.spike,
						flat = el.flat,
					})
					if not b then
						break -- no EditableMesh here: the chunks stay blocks
					end
					if self.finished or started then
						b.destroy()
						break
					end
					b.part.Parent = nil
					table.insert(rocks, b)
				end
			end)
			table.insert(cleanups, function()
				for _, b in rocks do
					b.destroy()
				end
			end)
		end
		table.insert(updaters, function(t, dt)
			local at = el.at or 0
			if t < at then
				return
			end
			if not started then
				started = true
				local cf = frameAt(el.point, el.aim, el.rotate)
				-- the kit's own rest lies on ONE flat floor at the effect's height: an effect played on a TILTED surface
				-- would lay its pieces level in a tilted slab (nothing caught it). Said once a layer; "floor": "world"
				-- lets the engine's physics lay them on the real slope
				-- (keyed by the preset's name and the layer's: a tiered or a surface's layer is a fresh table every play)
				local said = `{tostring(o.name)}/{tostring(el.name)}`
				if
					plan
					and el.rest == true
					and el.floor ~= "world"
					and not tiltSaid[said]
					and cf.UpVector.Y < 0.985
				then
					tiltSaid[said] = true
					warn(
						`[VfxStage] debris layer "{tostring(el.name)}": played on a surface tilted {math.floor(
							math.deg(math.acos(math.clamp(cf.UpVector.Y, -1, 1))) + 0.5
						)} degrees - its pieces come to rest on a LEVEL floor; "floor": "world" lays them on the real slope`
					)
				end
				if plan then
					local thick = plan.size[3]
					-- a layer's "speed" (one number) is the speed of the piece nearest the blow: the plan's pushes scaled to it
					local made = if type(plan.made) == "table" and type(plan.made.speed) == "number"
						then plan.made.speed
						else 0
					local push = if type(el.speed) == "number" and made > 0 then el.speed / made else 1
					for i, pc in plan.pieces do
						local x0, x1, z0, z1 = math.huge, -math.huge, math.huge, -math.huge
						for _, q in pc.points do
							x0, x1, z0, z1 =
								math.min(x0, q[1]), math.max(x1, q[1]), math.min(z0, q[2]), math.max(z1, q[2])
						end
						local c: BasePart = if shards[i] then shards[i].part else plainPart("Debris", root)
						c.Parent = if el.outline ~= nil then outlined(el.outline) else root
						c.Transparency = 0
						-- (toon: flat, as a mesh layer's - a debris layer's "toon" was read by the player alone)
						c.Material = (Enum.Material :: any)[if el.toon
							then "SmoothPlastic"
							else (el.material or "Slate")]
						c.Color = colorAt(el.color or { 70, 60, 52 }, rng:NextNumber(), palette)
						c.Size = Vector3.new(math.max(x1 - x0, 0.05), thick, math.max(z1 - z0, 0.05)) * scale
						-- (a MeshPart sits on the middle of its mesh's box, which is not the piece's own middle: debrisStart)
						local s0, _, _, s0shape = debrisStart(pc, thick, scale, push)
						local mid = Vector3.new(s0[1], s0[2], s0[3])
						table.insert(chunks, {
							part = c,
							pos = cf:PointToWorldSpace(mid),
							vel = cf:VectorToWorldSpace(Vector3.new(s0[4], s0[5], s0[6])),
							rot = cf.Rotation,
							spin = Vector3.new(pc.spin[1], pc.spin[2], pc.spin[3]) * push,
							size = c.Size,
							floor = where.Position.Y,
							wait = pc.delay,
							shard = i,
						})
						-- "floor": "world" - the fracture's pieces are REAL RIGID BODIES (the engine's own physics): each sits
						-- where it sat in the slab until the break reaches it, is let go with the plan's push and spin, and
						-- falls on the real ground - a slope, a step, a wall, the other pieces - and comes to rest there.
						-- The kit's own rest (debrisStep / debrisMeet: a flat floor at the effect's height) is for where
						-- there is no physics to ask: the server's copy, the browser player
						if el.rest == true and not world then -- the piece comes to rest (debrisStep): its flight is eleven numbers
							local ch = chunks[#chunks]
							ch.st = {
								ch.pos.X,
								ch.pos.Y,
								ch.pos.Z,
								ch.vel.X,
								ch.vel.Y,
								ch.vel.Z,
								0,
								0,
								s0[9],
								s0[10],
								0,
							}
							ch.hy = c.Size.Y / 2
							ch.hw = c.Size.Z / 2 -- (it tips about its own X: the side that stands up is its Z)
							ch.shape = s0shape -- (its flat outline in its own axes: debrisStart)
							ch.turn = frameYaw(cf)
							ch.area = math.max(if type(pc.area) == "number" then pc.area else 0, 1e-6)
						end
						c.CFrame = CFrame.new(chunks[#chunks].pos) * cf.Rotation
					end
				end
				for i = 1, if plan or lost then 0 else (el.count or 6) do
					local c: BasePart = if rocks[i] then rocks[i].part else plainPart("Debris", root)
					c.Parent = if el.outline ~= nil then outlined(el.outline) else root
					c.Transparency = 0
					c.Material = (Enum.Material :: any)[el.material or "Slate"]
					c.Color = colorAt(el.color or { 70, 60, 52 }, rng:NextNumber(), palette)
					local s = rng:NextNumber(size[1], size[2]) * scale
					c.Size = Vector3.new(s, s * rng:NextNumber(0.5, 1), s * rng:NextNumber(0.6, 1.2))
					local yaw = rng:NextNumber(0, math.pi * 2)
					local tilt = rng:NextNumber(0, spread)
					local dir = cf:VectorToWorldSpace(
						Vector3.new(math.sin(tilt) * math.cos(yaw), math.cos(tilt), math.sin(tilt) * math.sin(yaw))
					)
					local ch = {
						part = c,
						pos = cf.Position,
						vel = dir * rng:NextNumber(speed[1], speed[2]) * scale,
						rot = CFrame.Angles(rng:NextNumber(0, 6), rng:NextNumber(0, 6), 0),
						spin = Vector3.new(rng:NextNumber(-6, 6), rng:NextNumber(-6, 6), rng:NextNumber(-6, 6)),
						size = c.Size,
						floor = where.Position.Y,
					}
					if world then
						-- the engine's own physics: the chip leaves the surface, falls to the REAL ground and bounces there
						-- (a wall hit's chips would stop in mid-air on the hit's own height otherwise); not on the clock
						c.Anchored = false
						c.CanCollide = true
						VfxDebris.mark(c)
						c.Massless = false
						c.CustomPhysicalProperties = PhysicalProperties.new(0.7, 0.4, 0.35)
						c.CFrame = CFrame.new(ch.pos + dir * s * 0.75) * ch.rot
						c.AssemblyLinearVelocity = ch.vel
						c.AssemblyAngularVelocity = ch.spin
					end
					table.insert(chunks, ch)
				end
			end
			local u = (t - at) / life
			if plan and el.rest == true and u <= 1 then
				-- "rest": the pieces that have left the slab take ONE step together (debrisMeet): each lands on the floor
				-- or on a piece under it, slides, tips flat and LIES there, and pieces that lie in each other part
				local moving, S, shapes, H, W, A = {}, {}, {}, {}, {}, {}
				for _, ch in chunks do
					if ch.st and not (ch.wait and t - at < ch.wait) then
						table.insert(moving, ch)
						table.insert(S, ch.st)
						table.insert(shapes, ch.shape)
						table.insert(H, ch.hy)
						table.insert(W, ch.hw)
						table.insert(A, ch.area)
					end
				end
				-- an EARLY STOP (a review leftover, stage 23): once a step left every piece exactly as it was, at rest, the
				-- rule is not run again until another piece leaves the slab (a step of pieces that lie still, apart and at
				-- rest changes nothing: the rule is the same arithmetic on the same numbers)
				if #moving > 0 and stillAt ~= #moving then
					local new, _, overlapped =
						debrisMeet(S, shapes, H, W, A, dt, g, moving[1].floor, moving[1].turn, scale)
					local same = not overlapped
					for i, ch in moving do
						local a, b = ch.st, new[i]
						if b[11] ~= 1 then
							same = false
						else
							for k = 1, 11 do
								if a[k] ~= b[k] then
									same = false
									break
								end
							end
						end
						ch.st = b
					end
					-- (only a step with time to push in says the pile is still: in a hit-stop or a freeze the step is 0 and
					-- pieces lying in each other are not parted in it - they would never be parted after: a review)
					if dt * DEBRIS_PART > DEBRIS_NUDGE then
						stillAt = if same then #moving else nil
					end
				end
			end
			for _, ch in chunks do
				if u > 1 then
					ch.part.Transparency = 1
					if world then
						-- (over: an unseen piece must not stay solid - it blocked the player and was hit by rays)
						ch.part.Anchored = true
						ch.part.CanCollide = false
					end
					continue
				end
				if world then
					if ch.wait ~= nil and not ch.let then
						if t - at < ch.wait then
							continue -- the break has not reached this piece: it sits where it sat in the slab
						end
						ch.let = true
						local c: BasePart = ch.part
						c.CanCollide = true
						VfxDebris.mark(c)
						c.Massless = false
						c.CustomPhysicalProperties = PhysicalProperties.new(0.7, 0.4, 0.35)
						c.Anchored = false
						c.AssemblyLinearVelocity = ch.vel
						c.AssemblyAngularVelocity = ch.spin
					end
					-- (a piece that rests fades late, as the kit's own rest does: it lies there to be seen)
					local from = if ch.wait ~= nil and el.rest == true then 0.85 else 0.7
					ch.part.Transparency = math.clamp((u - from) / (1 - from), 0, 1)
					continue
				end
				if ch.wait and t - at < ch.wait then
					continue -- the break has not reached this piece: it sits where it sat in the slab
				end
				if ch.st then
					-- "rest" (stepped above, all together): it fades over the last 15 % of the life instead of
					-- shrinking in mid-tumble
					local st = ch.st
					ch.part.Transparency = math.clamp((u - 0.85) / 0.15, 0, 1)
					ch.part.CFrame = CFrame.new(st[1], st[2], st[3])
						* ch.rot
						* CFrame.Angles(0, st[8], 0)
						* CFrame.Angles(st[7], 0, 0)
					continue
				end
				ch.vel -= Vector3.new(0, g * dt, 0)
				ch.pos += ch.vel * dt
				if ch.pos.Y < ch.floor + ch.size.Y / 2 then
					ch.pos = Vector3.new(ch.pos.X, ch.floor + ch.size.Y / 2, ch.pos.Z)
					ch.vel = Vector3.new(ch.vel.X * 0.5, -ch.vel.Y * 0.25, ch.vel.Z * 0.5)
				end
				ch.rot *= CFrame.Angles(ch.spin.X * dt, ch.spin.Y * dt, ch.spin.Z * dt)
				local shrink = 1 - math.clamp((u - 0.7) / 0.3, 0, 1)
				ch.part.Size = ch.size * math.max(shrink, 0.01)
				ch.part.CFrame = CFrame.new(ch.pos) * ch.rot
			end
		end)
	end

	-- screen: a colour flash / grade over the layer's life (brightness, contrast, saturation, tint), plus
	-- optional blur and a temporary boost of the place's Bloom (a flood of light)
	builders.screen = function(el)
		if not (isClient or booth) then
			return
		end
		local life = lifeOf(el)
		local cc = Instance.new("ColorCorrectionEffect")
		cc.Name = "KitVfxStage"
		cc.Enabled = false
		cc.Parent = Lighting
		local blur: BlurEffect? = nil
		if el.blur then
			local b = Instance.new("BlurEffect")
			b.Name = "KitVfxStage"
			b.Size = 0
			b.Parent = Lighting
			blur = b
		end
		local boost = 0 -- this layer's share of the stage's bloom
		table.insert(cleanups, function()
			cc:Destroy()
			if blur then
				blur:Destroy()
			end
			self.contrib.bloom -= boost
			boost = 0
		end)
		table.insert(updaters, function(t)
			local at = el.at or 0
			local u = (t - at) / life
			local alive = t >= at and u <= 1
			local k = if alive then falloff(where.Position, el.radius) else 0
			cc.Enabled = alive
			cc.Brightness = numAt(el.brightness, u, 0) * k
			cc.Contrast = numAt(el.contrast, u, 0) * k
			cc.Saturation = numAt(el.saturation, u, 0) * k
			cc.TintColor = Color3.new(1, 1, 1):Lerp(colorAt(el.tint, u, palette), k * numAt(el.tintAmount, u, 1))
			if blur then
				blur.Size = if alive then numAt(el.blur, u, 0) * k else 0
			end
			if el.bloom then
				local want = if alive then numAt(el.bloom, u, 0) * k else 0
				self.contrib.bloom += want - boost
				boost = want
			end
		end)
	end

	-- impact frame: the anime beat where the world turns to stark black / white for a few frames
	builders.impact = function(el)
		if not (isClient or booth) then
			return
		end
		local life = lifeOf(el)
		local cc = Instance.new("ColorCorrectionEffect")
		cc.Name = "KitVfxImpact"
		cc.Enabled = false
		cc.Parent = Lighting
		table.insert(cleanups, function()
			cc:Destroy()
		end)
		-- a drawn plate: the picture over the whole screen for the frame's life (the One Piece impact frame: an
		-- ink illustration shown for a few frames). Any camera, any scene behind it.
		local plate: ScreenGui? = nil
		if type(el.image) == "string" then
			local gui = Instance.new("ScreenGui")
			gui.Name = "KitVfxPlate"
			gui.IgnoreGuiInset = true
			gui.DisplayOrder = 1000
			gui.ResetOnSpawn = false
			gui.Enabled = false
			local img = Instance.new("ImageLabel")
			img.Size = UDim2.fromScale(1, 1)
			img.BackgroundTransparency = 1
			img.ScaleType = Enum.ScaleType.Crop
			img.Image = textureId(textures, el.image)
			img.ImageTransparency = el.imageTransparency or 0
			img.Parent = gui
			local player = if isClient then Players.LocalPlayer else nil
			gui.Parent = if player then player:WaitForChild("PlayerGui") else game:GetService("StarterGui")
			plate = gui
			table.insert(cleanups, function()
				gui:Destroy()
			end)
		end
		-- style "frame": the frame BUILT from the scene (the owner's reference set, 2026-10-11): the world a flat paper
		-- colour (fog at zero range), the rig models as flat ink silhouettes (Highlight fills, drawn through the fog),
		-- a radial speed-line burst centred on the hit (a ScreenGui image at the focus point's viewport position).
		-- The effect's own energy as ink marks is the player's job for now (particles are fogged away in-engine):
		-- measure it in the booth before relying on it in a game.
		local frame: { [string]: any }? = nil
		if el.style == "frame" then
			local function col(v: any, fallback: Color3): Color3
				if v == "white" then
					return Color3.new(1, 1, 1)
				elseif v == "black" then
					return Color3.new(0, 0, 0)
				elseif v ~= nil then
					return rgb(v, palette)
				end
				return fallback
			end
			local paper = col(el.paper, Color3.new(1, 1, 1))
			local light = paper.R * 0.3 + paper.G * 0.59 + paper.B * 0.11 > 0.5
			local ink = col(el.ink, if light then Color3.new(0, 0, 0) else Color3.new(1, 1, 1))
			local models: { Model } = {}
			for _, a in anchors do
				local m = (a :: Instance):FindFirstAncestorOfClass("Model")
				if m and not table.find(models, m) then
					table.insert(models, m)
				end
			end
			if isClient then
				local lp = game:GetService("Players").LocalPlayer
				local ch = if lp then lp.Character else nil
				if ch and not table.find(models, ch) then
					table.insert(models, ch)
				end
			end
			local highlights: { Highlight } = {}
			for _, m in models do
				local h = Instance.new("Highlight")
				h.FillColor = ink
				h.FillTransparency = 0
				h.OutlineTransparency = 1
				h.DepthMode = Enum.HighlightDepthMode.AlwaysOnTop
				h.Enabled = false
				h.Adornee = m
				h.Parent = m
				table.insert(highlights, h)
			end
			local gui = Instance.new("ScreenGui")
			gui.Name = "KitVfxFrame"
			gui.IgnoreGuiInset = true
			gui.DisplayOrder = 999
			gui.ResetOnSpawn = false
			gui.Enabled = false
			local lines: ImageLabel? = nil
			if el.lines ~= "none" then
				local img = Instance.new("ImageLabel")
				img.BackgroundTransparency = 1
				img.AnchorPoint = Vector2.new(0.5, 0.5)
				img.ScaleType = Enum.ScaleType.Stretch
				local linesKey = el.lines
				if
					linesKey == nil
					or linesKey == "fine"
					or linesKey == "bold"
					or linesKey == "both"
					or linesKey == "perspective"
					or linesKey == "cut"
				then
					linesKey = "speed_lines" -- the drawn focus lines are the player's; in-engine the texture burst stands in
				end
				img.Image = textureId(textures, linesKey)
				img.ImageColor3 = col(el.linesColor, ink)
				img.Parent = gui
				lines = img
			end
			local lp = if isClient then game:GetService("Players").LocalPlayer else nil
			gui.Parent = if lp then lp:WaitForChild("PlayerGui") else game:GetService("StarterGui")
			local id = {} -- the frame's place in the mood stack
			frame = {
				paper = paper,
				highlights = highlights,
				gui = gui,
				lines = lines,
				scale = el.linesScale or 1.6,
				focus = el.focus or el.point or "target",
				id = id,
				on = false,
			}
			table.insert(cleanups, function()
				mood:pop(id)
				for _, h in highlights do
					highlightSlots:release(h)
					h:Destroy()
				end
				gui:Destroy()
			end)
		end
		local mode = el.mode or (if plate or frame then "none" else "white")
		table.insert(updaters, function(t)
			local at = el.at or 0
			local alive = t >= at and t <= at + life
			if plate then
				plate.Enabled = alive
			end
			if frame then
				if alive and not frame.on then
					frame.on = true
					-- the paper: the old fog for a place without an Atmosphere, and the Atmosphere filled with it
					-- (the engine ignores FogEnd while one exists); over any world layer (priority 10)
					mood:push(frame.id, 10, {
						fogColor = frame.paper,
						fogStart = 0,
						fogEnd = 1,
						["atmo.density"] = 1,
						["atmo.offset"] = 0,
						["atmo.color"] = frame.paper,
						["atmo.decay"] = frame.paper,
						["atmo.glare"] = 0,
						["atmo.haze"] = 10,
					})
					for _, h in frame.highlights do
						lightUp(h, VfxHighlight.HERO, true)
					end
					frame.gui.Enabled = true
				elseif not alive and frame.on then
					frame.on = false
					mood:pop(frame.id)
					for _, h in frame.highlights do
						lightUp(h, VfxHighlight.HERO, false)
					end
					frame.gui.Enabled = false
				end
				if alive and frame.lines then
					local cam = Workspace.CurrentCamera
					if cam then
						local v = cam:WorldToViewportPoint(worldPoint(frame.focus))
						local vp = cam.ViewportSize
						local size = math.max(vp.X, vp.Y) * frame.scale
						frame.lines.Position = UDim2.fromOffset(v.X, v.Y)
						frame.lines.Size = UDim2.fromOffset(size, size)
					end
				end
			end
			cc.Enabled = alive and mode ~= "none" and falloff(where.Position, el.radius) > 0
			if mode == "flash" then -- a flat white-out (the ufotable frame): brightness 1 clamps every pixel to white
				cc.Brightness, cc.Contrast, cc.Saturation = 1, 0, 0
			elseif mode == "ink" then -- the anime ink frame: the world black, only the hottest light stays as a white silhouette
				cc.Brightness, cc.Contrast, cc.Saturation = -1, 2.5, 0
			elseif mode == "black" then
				cc.Brightness, cc.Contrast, cc.Saturation = -0.6, 3, -1
			elseif mode == "mono" then
				cc.Brightness, cc.Contrast, cc.Saturation = 0.1, 2.5, -1
			elseif mode == "invert" then -- the negative frame (Genshin / anime): if Roblox maps contrast like the player,
				-- (c - 0.5) * (1 + contrast) + 0.5, contrast -2 = 1 - c. NOT yet proven in Roblox (an engine fact to confirm)
				cc.Brightness, cc.Contrast, cc.Saturation = 0, -2, 0
			else
				cc.Brightness, cc.Contrast, cc.Saturation = 0.9, 1.5, -0.6
			end
			cc.TintColor = rgb(el.tint or { 255, 255, 255 }, palette)
		end)
	end

	builders.shake = function(el)
		if not (isClient or booth) then
			return
		end
		local life = lifeOf(el)
		local current, curX, curY = 0, 0, 0
		-- the kick (2026-10-23, the Demon Slayer rule: on each impact the camera bumps in the strike's direction):
		-- `kick` [x, y] degrees the picture jolts, enveloped by `kickCurve` (default: a 0.06-of-life punch, eased home)
		local kick = if type(el.kick) == "table" then el.kick else nil
		local env = el.kickCurve or { { 0, 0 }, { 0.06, 1 }, { 0.35, 0.3 }, { 1, 0 } }
		table.insert(cleanups, function()
			self.contrib.shake -= current
			self.contrib.kickX -= curX
			self.contrib.kickY -= curY
		end)
		table.insert(updaters, function(t)
			local at = el.at or 0
			local u = (t - at) / life
			local alive = t >= at and u <= 1
			local fall = if alive then falloff(where.Position, el.radius) else 0
			local want = if alive then numAt(el.amplitude, u, 0) * fall else 0
			local wx, wy = 0, 0
			if kick and alive then
				local k = numAt(env, u, 0) * fall
				-- yaw +x turns the camera left (the picture moves right); pitch -y looks down (the picture moves up)
				wx, wy = (kick[1] or 0) * k, -(kick[2] or 0) * k
			end
			if booth and o.noShake then
				want, wx, wy = 0, 0, 0
			end
			self.contrib.shake += want - current
			self.contrib.kickX += wx - curX
			self.contrib.kickY += wy - curY
			current, curX, curY = want, wx, wy
		end)
	end

	builders.fov = function(el)
		if not (isClient or booth) then
			return
		end
		local life = lifeOf(el)
		local current = 0
		table.insert(cleanups, function()
			self.contrib.fov -= current
		end)
		table.insert(updaters, function(t)
			local at = el.at or 0
			local u = (t - at) / life
			local want = if t >= at and u <= 1 then numAt(el.delta, u, 0) * falloff(where.Position, el.radius) else 0
			self.contrib.fov += want - current
			current = want
		end)
	end

	-- glow: an anchored part of the caller's (a sword blade: "@blade") turns to light over the layer's life, then
	-- gets its own colour / material back
	-- trail: a Roblox Trail between two points: on a part the caller passes ("target": "@blade", "span": two local
	-- offsets along it: a sword's trail) or between two effect points ("from" / "to", re-read every frame)
	-- trail "mesh": true - the RIBBON: the same swept surface as real geometry (VfxMesh.ribbon), its texture's alpha + glow
	-- through a SurfaceAppearance (`surface` = the glow strength, 0 = none), u / v as the player draws it, never turned
	-- to the camera (a Roblox Trail's FaceCamera twisted a blade's smear toward the viewer: Sample Game 2026-10-28,
	-- the owner: "they don't look proper"). The engine ignores vertex alpha, so the fade along the trail is the
	-- texture's; `transparency` runs over the LAYER's life, the whole ribbon at once.
	local function meshRibbon(el: any, host: BasePart)
		local life = lifeOf(el)
		local lifetime = el.lifetime or 0.5
		local samples = math.clamp(el.samples or 48, 4, 120)
		local span = el.span or { { 0, -1, 0 }, { 0, 1, 0 } }
		local s0 = Vector3.new(span[1][1], span[1][2], span[1][3]) * scale
		local s1 = Vector3.new(span[2][1], span[2][2], span[2][3]) * scale
		local hist: { { t: number, a: Vector3, b: Vector3 } } = {}
		local ribbon: VfxMesh.Ribbon? = nil
		task.spawn(function()
			local r, why = VfxMesh.ribbon(samples, (el.reach or 12) * scale, el.critical)
			if r and self.finished then
				r.destroy()
				return
			end
			if not r then
				-- no EditableMesh (the memory budget, or a place with "Allow Mesh & Image APIs" off): the same smear as a
				-- FLAT Roblox Trail - never facing the camera - its glow from `surface`, its fade along the trail as a trail's
				ribbonFails += 1
				if ribbonFails >= RIBBON_GIVE_UP and not ribbonWarned then
					ribbonWarned = true
					warn(`[VfxStage] mesh trails drawn as flat Trails (enable Allow Mesh & Image APIs): {why}`)
				end
				if not self.finished then
					builders.trail(el, true)
				end
				return
			end
			ribbonFails = 0
			local mp = r.part
			mp.Name = el.name or "Ribbon"
			mp.Material = (Enum.Material :: any)[el.material or "SmoothPlastic"]
			local id = textureId(textures, el.texture)
			local strength = if type(el.surface) == "number" then el.surface else 0
			if id ~= "" and not applySurface(mp, el.texture, id, strength) then
				mp.TextureID = id
			end
			mp.Color = colorAt(el.color, 0, palette)
			mp.Transparency = 1
			mp.Parent = root
			ribbon = r
		end)
		table.insert(cleanups, function()
			if ribbon then
				ribbon.destroy()
			end
		end)
		table.insert(updaters, function(t)
			local at = el.at or 0
			local u = (t - at) / life
			-- (a released stage takes no new sample: the tail it has fades out - ribbonEmits)
			local takes = ribbonEmits(t, at, life, host.Parent ~= nil, self.released)
			ribbonHistory(
				hist,
				t,
				lifetime,
				samples,
				if takes
					then function()
						local cf = host.CFrame
						return cf:PointToWorldSpace(s0), cf:PointToWorldSpace(s1)
					end
					else nil
			)
			local r = ribbon
			if not r then
				return
			end
			if ribbonDone(u, self.released, #hist) then -- its tail aged out and no sample will come: back to the pool now
				ribbon = nil
				r.destroy()
				return
			end
			if #hist < 2 then
				r.part.Transparency = 1
				return
			end
			local ends = table.create(#hist)
			for i, h in hist do
				-- widthScale over the sample's age, about the span's middle (as the player's trail)
				local ws = numAt(el.widthScale, (t - h.t) / lifetime, 1)
				local mid = h.a:Lerp(h.b, 0.5)
				ends[i] = { mid:Lerp(h.a, ws), mid:Lerp(h.b, ws) }
			end
			r.set(ends, hist[#hist].a:Lerp(hist[#hist].b, 0.5))
			r.part.Transparency = numAt(el.transparency, math.clamp(u, 0, 1), 0)
		end)
	end

	-- flat: draw a mesh trail as a flat Trail now (its ribbon could not be built)
	builders.trail = function(el, flat: boolean?)
		local life = lifeOf(el)
		local host: BasePart = base
		if el.mesh and not flat and not ribbonWarned then -- once ribbons are given up, every later one is flat at once
			local target = el.target
			local a = if type(target) == "string" and string.sub(target, 1, 1) == "@"
				then anchors[string.sub(target, 2)]
				else nil
			if a and a:IsA("BasePart") then
				meshRibbon(el, a :: BasePart)
				return
			end
		end
		local target = el.target
		if type(target) == "string" and string.sub(target, 1, 1) == "@" then
			local a = anchors[string.sub(target, 2)]
			if a and a:IsA("BasePart") then
				host = a :: BasePart
			end
		end
		local a0 = Instance.new("Attachment")
		local a1 = Instance.new("Attachment")
		a0.Name = "KitTrail0"
		a1.Name = "KitTrail1"
		a0.Parent = host
		a1.Parent = host
		local span = el.span or { { 0, -1, 0 }, { 0, 1, 0 } }
		if host ~= base then
			a0.Position = Vector3.new(span[1][1], span[1][2], span[1][3]) * scale
			a1.Position = Vector3.new(span[2][1], span[2][2], span[2][3]) * scale
		end
		if el.mesh then -- a mesh trail after a ribbon failed: drawn flat, as the fallback in meshRibbon
			el = table.clone(el)
			el.faceCamera = false
			el.lightInfluence = 0
			el.lightEmission = if (el.surface or 0) > 0 then 1 else 0
			el.brightness = math.max(el.surface or 1, 1)
			el.transparency = el.trailTransparency or { { 0, 0 }, { 0.6, 0.25 }, { 1, 1 } }
		end
		local trail = Instance.new("Trail")
		trail.Name = el.name or "Trail"
		trail.Attachment0 = a0
		trail.Attachment1 = a1
		trail.Lifetime = el.lifetime or 0.5
		trail.Texture = textureId(textures, el.texture)
		trail.TextureLength = el.textureLength or 1
		trail.TextureMode = (Enum.TextureMode :: any)[el.textureMode or "Stretch"]
		trail.Color = colorSeq(el.color or { 255, 255, 255 }, palette)
		trail.Transparency = numberSeq(el.transparency or 0, 1)
		trail.LightEmission = el.lightEmission or 1
		trail.LightInfluence = el.lightInfluence or 0
		trail.Brightness = el.brightness or 1
		trail.FaceCamera = el.faceCamera ~= false
		trail.MinLength = el.minLength or 0
		trail.WidthScale = numberSeq(el.widthScale or 1, 1)
		trail.Enabled = false
		trail.Parent = host
		table.insert(cleanups, function()
			trail:Destroy()
			a0:Destroy()
			a1:Destroy()
		end)
		table.insert(updaters, function(t)
			local at = el.at or 0
			local u = (t - at) / life
			local alive = t >= at and u <= 1
			trail.Enabled = alive and not self.released
			if alive and host == base then
				a0.WorldPosition = worldPoint(el.from or { 0, -1, 0 })
				a1.WorldPosition = worldPoint(el.to or { 0, 1, 0 })
			end
		end)
	end

	-- highlight: Roblox's Highlight on a model or part the caller passes in ("@body" = the character): the body takes
	-- the effect's colour (fill) and a glowing rim (outline) — an aura lighting its fighter. 31 Highlights per client.
	builders.highlight = function(el)
		local a = anchors[string.sub(tostring(el.target or ""), 2)]
		if not (a and (a:IsA("Model") or a:IsA("BasePart"))) then
			return
		end
		local life = lifeOf(el)
		local h = Instance.new("Highlight")
		h.Name = "Highlight_" .. tostring(el.name or "")
		h.Adornee = a
		h.Enabled = false
		h.DepthMode = (Enum.HighlightDepthMode :: any)[el.depthMode or "Occluded"]
		h.Parent = root
		table.insert(cleanups, function()
			highlightSlots:release(h)
			h:Destroy()
		end)
		table.insert(updaters, function(t)
			local at = el.at or 0
			local u = (t - at) / life
			if t < at or u > 1 then
				lightUp(h, VfxHighlight.HERO, false)
				return
			end
			lightUp(h, VfxHighlight.HERO, true)
			h.FillColor = colorAt(el.fill, u, palette)
			h.OutlineColor = colorAt(el.outline, u, palette)
			h.FillTransparency = numAt(el.fillTransparency, u, 0.6)
			h.OutlineTransparency = numAt(el.outlineTransparency, u, 0)
		end)
	end

	builders.glow = function(el)
		local a = anchors[string.sub(tostring(el.target or ""), 2)]
		if not (a and a:IsA("BasePart")) then
			return
		end
		local part = a :: BasePart
		local life = lifeOf(el)
		local saved = { color = part.Color, material = part.Material, transparency = part.Transparency }
		local on = false
		local function restore()
			if on then
				on = false
				part.Color, part.Material, part.Transparency = saved.color, saved.material, saved.transparency
			end
		end
		table.insert(cleanups, restore)
		table.insert(updaters, function(t)
			local at = el.at or 0
			local u = (t - at) / life
			if t < at or u > 1 then
				restore()
				return
			end
			on = true
			part.Material = (Enum.Material :: any)[el.material or "Neon"]
			part.Color = colorAt(el.color, u, palette)
			part.Transparency = numAt(el.transparency, u, saved.transparency)
		end)
	end

	-- swarm: SCRIPTED particles for hero moments (board/plans/archive/aaa-vfx-research.md) - what a ParticleEmitter cannot do:
	-- curl-noise swirl (curl {strength, scale, speed}), attraction / vortex toward a point (attract {point, strength,
	-- swirl}), gravity, drag, a floor they bounce on (floor {y, bounce}), a Trail behind each (trail {lifetime, width}).
	-- `count` (<= 150) parts spawned over `spawn` s in a ball of `radius` round `point`, flying out at `speed`; size /
	-- colour / transparency over each one's own life. Moved with BulkMoveTo every frame (cost: kit vfx cost)
	builders.swarm = function(el)
		local count = math.clamp(el.count or 40, 1, if el.shape == "Rock" then 40 else 150)
		local rngS = Random.new(el.seed or 1)
		local folder = Instance.new("Folder")
		folder.Name = "Swarm_" .. tostring(el.name or "")
		folder.Parent = root
		local parts: { BasePart } = {}
		local state: { any } = {}
		local lo, hi = 1, 1
		if type(el.lifetime) == "table" then
			lo, hi = el.lifetime[1], el.lifetime[2]
		elseif type(el.lifetime) == "number" then
			lo, hi = el.lifetime, el.lifetime
		end
		local sp = el.speed or { 4, 8 }
		local spLo, spHi = if type(sp) == "number" then sp else sp[1], if type(sp) == "number" then sp else sp[2]
		for i = 1, count do
			local part = Instance.new("Part")
			part.Name = "P" .. i
			part.Anchored, part.CanCollide, part.CanQuery, part.CanTouch, part.CastShadow =
				true, false, false, false, false
			part.Shape = if el.shape == "Block" or el.shape == "Rock" then Enum.PartType.Block else Enum.PartType.Ball
			part.Material = (Enum.Material :: any)[el.material or (if el.shape == "Rock" then "Slate" else "Neon")]
			if el.reflectance then -- mirror beads (liquid metal): the player's metal swarm
				part.Reflectance = el.reflectance
			end
			part.Transparency = 1
			part.Size = Vector3.one * 0.2
			part.Parent = folder
			if el.trail then
				local a0, a1 = Instance.new("Attachment"), Instance.new("Attachment")
				a0.Position, a1.Position = Vector3.new(0, 0.05, 0), Vector3.new(0, -0.05, 0)
				a0.Parent, a1.Parent = part, part
				local tr = Instance.new("Trail")
				tr.Attachment0, tr.Attachment1 = a0, a1
				tr.Lifetime = el.trail.lifetime or 0.25
				tr.WidthScale = NumberSequence.new(1, 0)
				tr.LightEmission = if (el.material or "Neon") == "Neon" then 1 else 0
				tr.FaceCamera = true
				tr.Parent = part
			end
			parts[i] = part
			local dir = rngS:NextUnitVector()
			state[i] = {
				born = (el.at or 0) + (el.spawn or 0) * (i - 1) / math.max(count - 1, 1),
				life = lo + (hi - lo) * rngS:NextNumber(),
				off = dir * (el.radius or 1) * rngS:NextNumber() ^ (1 / 3) * scale,
				vel = dir * (spLo + (spHi - spLo) * rngS:NextNumber()) * scale,
				seed = rngS:NextNumber() * 100,
				pos = nil :: Vector3?,
			}
		end
		-- "shape": "Rock" - MESH PARTICLES: every particle is one of the kit's faceted stones (VfxMesh "rock", its own
		-- seed), tumbling about its own axis, steered by everything the swarm has (curl, attract, field, drag, floor).
		-- A stone is built in about a quarter of a second: each particle is a block until its stone is built and
		-- swapped in (Vfx.prewarm builds them all ahead: eight stones, cycled). A game without EditableMesh keeps the blocks
		local stones: { VfxMesh.Built } = {}
		local native: { [number]: Vector3 } = {}
		if el.shape == "Rock" then
			local tum = if type(el.tumble) == "table" then el.tumble else { 2, 6 }
			for i = 1, count do -- (drawn after every other number, so a swarm of balls keeps the numbers it had)
				state[i].axis = rngS:NextUnitVector()
				state[i].rate = tum[1] + (tum[2] - tum[1]) * rngS:NextNumber()
			end
			local rock: any = if type(el.rock) == "table" then el.rock else {}
			task.spawn(function()
				for i = 1, count do
					local b = VfxMesh.build("rock", {
						seed = 500 + ((i - 1) % 8) + (el.seed or 0) * 37, -- (eight stones, cycled; Vfx.prewarm: the same)
						cuts = rock.cuts,
						jag = rock.jag,
						spike = rock.spike,
						flat = rock.flat,
					})
					if not b then
						break -- no EditableMesh here: the particles stay blocks
					end
					if self.finished then
						b.destroy()
						break
					end
					local old = parts[i]
					native[i] = b.native -- (the mesh's own size: a pooled stone's Size is whatever its last user left)
					b.part.Material = old.Material
					b.part.Reflectance = old.Reflectance
					b.part.Color = old.Color
					b.part.Transparency = old.Transparency
					b.part.CFrame = old.CFrame
					b.part.Parent = folder
					parts[i] = b.part
					old:Destroy()
					table.insert(stones, b)
				end
			end)
		end
		table.insert(cleanups, function()
			for _, b in stones do -- (back to the pool BEFORE their folder goes: a pooled stone must outlive it)
				b.part.Reflectance = 0 -- (the pool does not reset it: the next user would get mirror stones)
				b.destroy()
			end
			folder:Destroy()
		end)
		local cfs: { CFrame } = table.create(count)
		local curl = el.curl
		local att = el.attract
		-- "field": an AUTHORED vector field (kit vfx field; o.field(name), Vfx passes VfxPresets.fields.<name>) - each
		-- particle's velocity is drawn toward the field's where it is, `follow` a second; `gain` scales the field
		local fieldEls: any = nil
		if type(el.field) == "table" and type(el.field.name) == "string" then
			local f: any = if o.field then o.field(el.field.name) else nil
			if type(f) == "table" and type(f.elements) == "table" and #f.elements > 0 then
				fieldEls = f.elements
			else
				warn(`[VfxStage] swarm layer "{tostring(el.name)}": no field "{el.field.name}" (kit vfx field)`)
			end
		end
		-- "cloud": a POINT CLOUD (kit vfx points; o.cloud(name), Vfx passes VfxPresets.points.<name>) - particle i is
		-- drawn to point i of it (round again past the last), `size` studs from the layer's point, `pull` hard
		local cloudPts: any = nil
		if type(el.cloud) == "table" and type(el.cloud.name) == "string" then
			local c: any = if o.cloud then o.cloud(el.cloud.name) else nil
			if type(c) == "table" and type(c.points) == "table" and #c.points > 0 then
				cloudPts = c.points
			else
				warn(`[VfxStage] swarm layer "{tostring(el.name)}": no cloud "{el.cloud.name}" (kit vfx points)`)
			end
		end
		local grav = (el.gravity or 0) * scale
		local drag = el.drag or 0
		local floor = el.floor
		-- F1b: a bounce on the floor throws a burst of its own (floor.onBounce; src/kit/VfxBounce.luau): ONE emitter
		-- at the contact, an explicit Emit(n) per bounce (kept on low graphics settings, where a Rate is throttled)
		local onBounce = if type(floor) == "table" and type(floor.onBounce) == "table" then floor.onBounce else nil
		local subAt: Attachment? = nil
		local subEm: ParticleEmitter? = nil
		local subUsed = 0
		if onBounce then
			local anchor = Instance.new("Part")
			anchor.Name = "BounceSparks"
			anchor.Anchored, anchor.CanCollide, anchor.CanQuery, anchor.CanTouch = true, false, false, false
			anchor.Transparency, anchor.Size = 1, Vector3.one * 0.1
			anchor.Parent = folder
			local at = Instance.new("Attachment")
			at.Parent = anchor
			local em = Instance.new("ParticleEmitter")
			em.Enabled = false
			em.Rate = 0
			local sp2 = onBounce.speed or { 4, 10 }
			em.Speed = NumberRange.new(sp2[1] * scale, sp2[2] * scale)
			em.Lifetime = NumberRange.new((onBounce.life or 0.35) * 0.7, onBounce.life or 0.35)
			em.SpreadAngle = Vector2.new(onBounce.spread or 35, onBounce.spread or 35)
			em.EmissionDirection = Enum.NormalId.Top
			em.Acceleration = Vector3.new(0, -(onBounce.gravity or 40) * scale, 0)
			em.Size = NumberSequence.new((onBounce.size or 0.15) * scale, 0)
			em.Color = ColorSequence.new(rgb(onBounce.color or { 255, 236, 190 }, palette))
			em.LightEmission = 1
			em.Transparency = NumberSequence.new(0, 1)
			em.Parent = at
			subAt, subEm = at, em
		end
		local last = nil :: number?
		-- its own frame budget (VfxBudget.swarmStride: past 0.5 ms the next frames move every k-th part, each by the
		-- time since it last moved) and a swarm far from the camera left where it is (VfxBudget.swarmCulled)
		local stride, frameN = 1, 0
		table.insert(updaters, function(t)
			local frameDt = if last then math.clamp(t - last, 0, 1 / 15) else 0
			last = t
			local cam = Workspace.CurrentCamera
			if cam and VfxBudget.swarmCulled((cam.CFrame.Position - worldPoint(el.point or { 0, 0, 0 })).Magnitude) then
				return
			end
			frameN += 1
			local spent = os.clock()
			for i, q in state do
				local part = parts[i]
				local age = t - q.born
				if age < 0 or age > q.life then
					part.Transparency = 1
					cfs[i] = part.CFrame
					if age < 0 then
						q.pos = nil
					end
					q.moved = nil
					continue
				end
				if q.pos ~= nil and q.moved ~= nil and not VfxBudget.swarmMoves(i, frameN, stride) then
					continue -- (its turn comes: it moves then by all the time since it last did)
				end
				local dt = if q.moved ~= nil then math.clamp(t - q.moved, 0, 0.25) else frameDt
				q.moved = t
				if q.pos == nil then
					q.pos = worldPoint(el.point or { 0, 0, 0 }) + q.off
				end
				local pos = q.pos :: Vector3
				local v = q.vel
				if curl then
					local sc = (curl.scale or 4) * scale
					local c = curl3(pos.X / sc + q.seed * 0.01, pos.Y / sc + t * (curl.speed or 0.3), pos.Z / sc)
					v += c * (curl.strength or 10) * scale * dt
				end
				if att then
					-- strength / swirl may be curves over the LAYER's life (an implosion that lets go: [[0, 80], [0.6, 80], [0.61, 0]])
					local lu = math.clamp((t - (el.at or 0)) / math.max(el.life or 1, 1e-3), 0, 1)
					local to = worldPoint(att.point or el.point or { 0, 0, 0 }) - pos
					local d = math.max(to.Magnitude, 0.5)
					v += to.Unit * numAt(att.strength, lu, 20) * scale * dt
					local swirl = numAt(att.swirl, lu, 0)
					if swirl ~= 0 then
						v += to.Unit:Cross(Vector3.yAxis) * (swirl * scale / math.sqrt(d)) * dt
					end
				end
				if fieldEls then
					local fu = math.clamp((t - (el.at or 0)) / math.max(el.life or 1, 1e-3), 0, 1)
					local fieldBase = worldPoint(el.point or { 0, 0, 0 })
					local fv = fieldAt(
						fieldEls,
						(pos.X - fieldBase.X) / scale,
						(pos.Y - fieldBase.Y) / scale,
						(pos.Z - fieldBase.Z) / scale
					)
					local want = Vector3.new(fv[1], fv[2], fv[3]) * (scale * numAt(el.field.gain, fu, 1))
					v += (want - v) * (1 - math.exp(
						-(if type(el.field.follow) == "number" then el.field.follow else 6) * dt
					)) -- (the same at any frame rate)
				end
				v += Vector3.new(0, -grav * dt, 0)
				-- drag may be a curve over the layer's life like attract (held in a shell, then a free fall)
				local dg = numAt(drag, math.clamp((t - (el.at or 0)) / math.max(el.life or 1, 1e-3), 0, 1), 0)
				if dg > 0 then
					v *= math.exp(-dg * 0.693 * dt)
				end
				-- (the cloud's pull LAST, on the speed everything else has made: gravity then sags a held particle by
				-- gravity / pull^2 at any frame rate, and cannot push it past its point)
				if cloudPts then
					local cu = math.clamp((t - (el.at or 0)) / math.max(el.life or 1, 1e-3), 0, 1)
					local w = numAt(el.cloud.pull, cu, 8) -- (a curve over the LAYER's life: 0 lets go)
					if w > 0 then
						local pt = cloudPts[(i - 1) % #cloudPts + 1]
						local reach = (if type(el.cloud.size) == "number" then el.cloud.size else 4) * scale
						local to = worldPoint(el.point or { 0, 0, 0 }) + Vector3.new(pt[1], pt[2], pt[3]) * reach
						v = Vector3.new(
							cloudPull(pos.X - to.X, v.X, w, dt),
							cloudPull(pos.Y - to.Y, v.Y, w, dt),
							cloudPull(pos.Z - to.Z, v.Z, w, dt)
						)
					end
				end
				pos += v * dt
				if floor then
					local fy = worldPoint({ 0, floor.y or 0, 0 }).Y
					local hit, y2, vy2, land = VfxBounce.contact(pos.Y, v.Y, fy, floor.bounce)
					if hit then
						pos = Vector3.new(pos.X, y2, pos.Z)
						v = Vector3.new(v.X * 0.8, vy2, v.Z * 0.8)
						local n = if onBounce then VfxBounce.burst(onBounce, land / scale, subUsed) else 0
						if n > 0 and subAt and subEm then
							subUsed += 1
							subAt.WorldPosition = pos
							subEm:Emit(n)
						end
					end
				end
				q.pos, q.vel = pos, v
				local u = age / q.life
				local size = numAt(el.size, u, 0.3) * scale
				local own = native[i] -- (a stone: `size` is its LONGEST side, whatever its own shape)
				part.Size = if own
					then own * (math.max(size, 0.05) / math.max(own.X, own.Y, own.Z, 1e-3))
					else Vector3.one * math.max(size, 0.05)
				part.Color = colorAt(el.color, u, palette)
				part.Transparency = numAt(el.transparency, u, 0)
				cfs[i] = if q.axis
					then CFrame.new(pos) * CFrame.fromAxisAngle(q.axis, q.rate * age)
					else CFrame.new(pos)
			end
			Workspace:BulkMoveTo(parts, cfs, Enum.BulkMoveMode.FireCFrameChanged)
			self.swarmMs = (os.clock() - spent) * 1000 -- the last update's cost (tests/playtest/vfx_stage_parity: <= 0.5 ms)
			stride = VfxBudget.swarmStride((os.clock() - spent) * 1000, stride)
		end)
	end

	-- lens: the camera's own marks on a huge hit (board/plans/archive/aaa-vfx-research.md) as full-screen images over the view -
	-- Roblox has no lens post effects: vignette (black corners), aberration (lens_fringe drawn red + cyan at two sizes:
	-- the colour split at the frame's edge), dirt (smudges + bokeh, tinted by `color`), zoom (radial streaks rushing
	-- in). Every amount a 0-1 curve; the local player's screen only
	builders.lens = function(el)
		local player = Players.LocalPlayer
		if not isClient or not player then
			return
		end
		local pg = player:FindFirstChildOfClass("PlayerGui")
		if not pg then
			return
		end
		local life = lifeOf(el)
		local gui = Instance.new("ScreenGui")
		gui.Name = "KitVfxLens"
		gui.IgnoreGuiInset = true
		gui.ResetOnSpawn = false
		gui.DisplayOrder = 40
		gui.Parent = pg
		local function img(key: string, color: Color3, z: number): ImageLabel
			local i = Instance.new("ImageLabel")
			i.BackgroundTransparency = 1
			i.AnchorPoint = Vector2.new(0.5, 0.5)
			i.Position = UDim2.fromScale(0.5, 0.5)
			i.Size = UDim2.fromScale(1, 1)
			i.Image = textureId(textures, key)
			i.ImageColor3 = color
			i.ImageTransparency = 1
			i.ZIndex = z
			i.Parent = gui
			return i
		end
		local vig = if el.vignette then img("lens_vignette", Color3.new(0, 0, 0), 4) else nil
		local red = if el.aberration then img("lens_fringe", Color3.fromRGB(255, 50, 40), 2) else nil
		local cyan = if el.aberration then img("lens_fringe", Color3.fromRGB(40, 210, 255), 2) else nil
		local dirt = if el.dirt then img(el.dirtTexture or "lens_dirt", Color3.new(1, 1, 1), 3) else nil
		local zoom = if el.zoom then img("lens_zoom", Color3.new(1, 1, 1), 1) else nil
		-- streaks: parallel speed lines across the screen at streakAngle (counter-clockwise degrees), sliding along it
		-- at streakSpeed screen widths a second; oversized so the turned image never shows its edge (the player's)
		-- a SQUARE as big as the screen's diagonal (no edge shows at any angle) showing HALF the sheet (two seamless
		-- periods) through ImageRectOffset, scrolled along the lines' own length (review 3: a 1.6x screen-shaped image
		-- showed its edges past 25 deg and crabbed sideways); the player draws the same numbers
		local streaks = if el.streaks then img("lens_streaks", Color3.new(1, 1, 1), 1) else nil
		if streaks then
			streaks.Rotation = -(el.streakAngle or 0) -- Roblox turns clockwise
			streaks.ImageRectSize = Vector2.new(512, 1024) -- half of the 1024 sheet (kit/vfx/lens.py N)
		end
		-- "flare": the lens answering a light at the layer's `point` - a glow on it, a level streak through it,
		-- ghosts on the line through the middle of the screen, placed every frame from where the point falls on the
		-- screen (flareMarks above; nothing when the point is behind the camera). "occlude": true hides it while
		-- something solid and seen stands between the camera and the light (one ray a frame; cut, not faded)
		local flare: any = if type(el.flare) == "table" then el.flare else nil
		local flareImgs: { ImageLabel } = {}
		local flareStrength = 0 -- (set by the updater below; 0 = the layer is not playing)
		if flare then
			flareImgs[1] = img("lens_glow", Color3.new(1, 1, 1), 5)
			flareImgs[2] = img("lens_streak", Color3.new(1, 1, 1), 5)
			for i = 1, math.clamp(math.floor(if type(flare.ghosts) == "number" then flare.ghosts else 5), 0, 8) do
				flareImgs[2 + i] = img("lens_ghost", Color3.new(1, 1, 1), 5)
			end
			-- the marks are PLACED in the render step, after the camera has moved (and after the kit's own shake,
			-- Camera + 1): placed in the updater they would be a frame behind the light on a shake or a fast turn
			flareBinds += 1
			local flareRay = RaycastParams.new() -- (one a layer, not one a frame)
			flareRay.FilterType = Enum.RaycastFilterType.Exclude
			local bound = "KitVfxFlare" .. flareBinds
			RunService:BindToRenderStep(bound, Enum.RenderPriority.Camera.Value + 2, function()
				local cam = Workspace.CurrentCamera
				local marks: { any } = {}
				local aspect = 16 / 9
				if cam and flareStrength > 0 then
					local vp = cam.ViewportSize
					if vp.X >= 1 and vp.Y >= 1 then
						aspect = vp.X / vp.Y
						local light = frameAt(el.point, el.aim, el.rotate).Position
						local v = cam:WorldToViewportPoint(light)
						local hidden = false
						if flare.occlude == true and v.Z > 0 then
							-- what is SEEN hides it, solid or not (a visible curtain does; an invisible wall, a trigger or a
							-- zone part does not: the ray goes on through those, a few times). Never the effect's own parts,
							-- the part it rides, or the viewer's own character (a flare on the caster's chest was hidden by
							-- the caster's torso on their own screen)
							local skip: { Instance } = { root }
							local me = Players.LocalPlayer
							if me and me.Character then
								table.insert(skip, me.Character)
							end
							if followPart then
								table.insert(skip, followPart:FindFirstAncestorOfClass("Model") or followPart)
							end
							local from = cam.CFrame.Position
							for _ = 1, 4 do
								flareRay.FilterDescendantsInstances = skip
								local hit = Workspace:Raycast(from, light - from, flareRay)
								if not hit then
									break
								end
								if hit.Instance.Transparency < 0.5 then
									hidden = true
									break
								end
								table.insert(skip, hit.Instance)
							end
						end
						if v.Z > 0 and not hidden then
							marks = flareMarks(v.X / vp.X, v.Y / vp.Y, aspect, flare)
						end
					end
				end
				local shown: { [number]: boolean } = {}
				for _, m in marks do
					local slot = if m.kind == 1 then 1 elseif m.kind == 2 then 2 else 2 + m.i
					local im = flareImgs[slot]
					if im then
						shown[slot] = true
						im.Position = UDim2.fromScale(m.x, m.y)
						im.Size = UDim2.fromScale(m.w / aspect, m.h)
						im.ImageTransparency = 1 - math.clamp(m.a * flareStrength, 0, 1)
						im.ImageColor3 = colorAt(flare.color or { 255, 240, 220 }, m.c, palette)
					end
				end
				for slot, im in flareImgs do
					if not shown[slot] then
						im.ImageTransparency = 1
					end
				end
			end)
			table.insert(cleanups, function()
				RunService:UnbindFromRenderStep(bound)
			end)
		end
		table.insert(cleanups, function()
			gui:Destroy()
		end)
		table.insert(updaters, function(t)
			local at = el.at or 0
			local u = (t - at) / life
			local alive = t >= at and u <= 1
			gui.Enabled = alive
			if not alive then
				flareStrength = 0
				return
			end
			local k = falloff(where.Position, el.radius)
			if vig then
				vig.ImageTransparency = 1 - math.clamp(numAt(el.vignette, u, 0) * k, 0, 1)
			end
			if red and cyan then
				local ab = math.clamp(numAt(el.aberration, u, 0) * k, 0, 1)
				red.ImageTransparency, cyan.ImageTransparency = 1 - ab, 1 - ab
				red.Size = UDim2.fromScale(1 + 0.03 * ab, 1 + 0.03 * ab)
				cyan.Size = UDim2.fromScale(1 - 0.015 * ab, 1 - 0.015 * ab)
			end
			if dirt then
				dirt.ImageTransparency = 1 - math.clamp(numAt(el.dirt, u, 0) * k, 0, 1)
				dirt.ImageColor3 = colorAt(el.color or { 255, 240, 220 }, u, palette)
			end
			if zoom then
				local z = math.clamp(numAt(el.zoom, u, 0) * k, 0, 1)
				zoom.ImageTransparency = 1 - z
				zoom.ImageColor3 = colorAt(el.zoomColor or { 255, 255, 255 }, u, palette)
				zoom.Size = UDim2.fromScale(1.25 - 0.25 * u, 1.25 - 0.25 * u) -- the streaks rush inward over the life
			end
			if streaks then
				local cam = Workspace.CurrentCamera
				local vp = if cam then cam.ViewportSize else Vector2.new(1920, 1080)
				local side = math.sqrt(vp.X * vp.X + vp.Y * vp.Y) * 1.02
				streaks.Size = UDim2.fromOffset(side, side)
				local aspect = vp.X / math.max(vp.Y, 1)
				local uOff = (((el.streakSpeed or 1.5) * (t - at) * aspect / (side / math.max(vp.Y, 1))) * 0.5) % 0.5
				streaks.ImageRectOffset = Vector2.new(uOff * 1024, 0)
				streaks.ImageTransparency = 1 - math.clamp(numAt(el.streaks, u, 0) * k, 0, 1)
				streaks.ImageColor3 = colorAt(el.streakColor or { 255, 255, 255 }, u, palette)
			end
			if flare then
				flareStrength = math.clamp(numAt(flare.strength, u, 1) * k, 0, 1)
			end
		end)
	end

	-- crater: the ground is CHANGED (board/plans/archive/aaa-vfx-research.md, world interaction) - terrain under `point` carved
	-- to Air in a ball of `radius` studs sunk `depth` below the surface, at `at`; the voxels it took come back when the
	-- layer's life ends (or the stage stops), so a replayed effect never digs a hole to the core. On a PART floor (no
	-- terrain under the point: most arenas, the booth's own floor) the ROCK RING instead (src/kit/VfxRockRing.luau): the
	-- rock_ring mark laid on that part's face in its colour, and a ring of chunks of its material thrown up round the
	-- rim, leaning out from the hit, sinking back and fading over the last quarter of the life. "rocks": the number of
	-- chunks (default about one a stud of radius; 0 = the mark alone), "texture": the mark (default rock_ring)
	builders.crater = function(el)
		if not (isClient or booth) then
			return
		end
		local terrain = Workspace.Terrain
		local life = lifeOf(el)
		local saved: any = nil
		local region: Region3? = nil
		local mode: string? = nil -- what was under the point when it went off: "terrain" | "part" | "none"
		local ring: { folder: Folder, mark: Decal, chunks: { { part: BasePart, rest: CFrame, height: number } } }? = nil
		local function dropRing()
			if ring then
				ring.folder:Destroy()
				ring = nil
			end
		end
		table.insert(cleanups, dropRing)
		local function groundUnder(at: Vector3): RaycastResult?
			local rp = RaycastParams.new()
			rp.FilterType = Enum.RaycastFilterType.Exclude
			rp.RespectCanCollide = true -- (a trigger or a zone part is not ground)
			local skip: { Instance } = { root }
			for _, pl in Players:GetPlayers() do
				if pl.Character then
					table.insert(skip, pl.Character)
				end
			end
			rp.FilterDescendantsInstances = skip
			return Workspace:Raycast(at + Vector3.new(0, 3, 0), Vector3.new(0, -12, 0), rp)
		end
		local function layRing(hit: RaycastResult)
			local floorPart = hit.Instance :: BasePart
			local r = (el.radius or 6) * scale
			local up = hit.Normal
			local side = if math.abs(up.Y) < 0.95
				then Vector3.new(0, 1, 0):Cross(up)
				else Vector3.new(1, 0, 0):Cross(up)
			local frame = CFrame.fromMatrix(hit.Position, side.Unit, up)
			local folder = Instance.new("Folder")
			folder.Name = "RockRing_" .. tostring(el.name or "")
			folder.Parent = root
			local w = VfxRockRing.decalWidth(r)
			local plate = plainPart("RockRingMark", folder)
			plate.Size = Vector3.new(w, 0.05, w)
			plate.CFrame = frame * CFrame.new(0, 0.03, 0)
			local mark = Instance.new("Decal")
			mark.Face = Enum.NormalId.Top
			mark.Texture = textureId(textures, el.texture or VfxRockRing.TEXTURE)
			mark.Color3 = floorPart.Color -- the grey mark in the floor's own colour
			mark.Parent = plate
			local chunks: { { part: BasePart, rest: CFrame, height: number } } = {}
			for i, rock in VfxRockRing.plan(r, el.seed or 1, el.rocks) do
				local p = plainPart("RockRingChunk", folder)
				p.Size = Vector3.new(rock.size[1], rock.size[2], rock.size[3])
				p.Material = floorPart.Material
				p.MaterialVariant = floorPart.MaterialVariant
				p.Color = floorPart.Color:Lerp(Color3.new(0, 0, 0), 0.06 + 0.12 * VfxRockRing.hash(i, 9, el.seed or 1))
				p.CastShadow = true
				p.Transparency = 0
				-- round the rim, turned its own way, then leaned OUT from the hit about the rim's tangent
				local out = Vector3.new(math.cos(rock.angle), 0, math.sin(rock.angle))
				local rest = frame
					* CFrame.new(out * rock.distance)
					* CFrame.fromAxisAngle(Vector3.new(-out.Z, 0, out.X), -rock.tilt)
					* CFrame.Angles(0, rock.yaw, 0)
				table.insert(chunks, { part = p :: BasePart, rest = rest, height = rock.size[2] })
			end
			ring = { folder = folder, mark = mark, chunks = chunks }
		end
		local function poseRing(lt: number)
			local rg = ring
			if not rg then
				return
			end
			local up = VfxRockRing.rise(lt, life)
			for _, c in rg.chunks do
				-- sunk: its top at the floor; up: 85 % of it stands out of the floor
				c.part.CFrame = c.rest * CFrame.new(0, c.height * (up * 0.85 - 0.5), 0)
			end
			rg.mark.Transparency = VfxRockRing.fade(lt, life)
		end
		local function restore()
			if saved and region then
				local back = CraterRefs.give(craterCells, saved.keys)
				if next(back) ~= nil then
					local mats, occ = terrain:ReadVoxels(region, 4)
					for k, cell in back do
						local i = saved.at[k]
						mats[i[1]][i[2]][i[3]] = cell.material
						occ[i[1]][i[2]][i[3]] = cell.occupancy
					end
					terrain:WriteVoxels(region, 4, mats, occ)
				end
				saved = nil
			end
		end
		table.insert(cleanups, restore)
		table.insert(updaters, function(t)
			local at = el.at or 0
			if t < at then
				return
			end
			if mode == nil and t <= at + life then
				-- what is under the point decides, once: terrain is carved, a part gets the rock ring
				local hit = groundUnder(worldPoint(el.point or { 0, 0, 0 }))
				mode = VfxRockRing.ground(if hit then { terrain = hit.Instance == terrain } else nil)
				if mode == "part" and hit then
					layRing(hit)
				end
			end
			if mode == "part" then
				if t > at + life then
					dropRing()
				else
					poseRing(t - at)
				end
				return
			end
			if t > at + life then
				restore()
				return
			end
			if saved or region then
				return
			end
			local r = (el.radius or 6) * scale
			local depth = math.min((el.depth or (el.radius or 6) * 0.4) * scale, r) -- the bowl's depth below the surface
			local centre = worldPoint(el.point or { 0, 0, 0 }) + Vector3.new(0, r - depth, 0)
			local pad = Vector3.one * (r + 4)
			local reg = Region3.new(centre - pad, centre + pad):ExpandToGrid(4)
			region = reg
			local materials, occupancies = terrain:ReadVoxels(reg, 4)
			local corner = reg.CFrame.Position - reg.Size / 2
			local n = materials.Size
			local keys, cellAt = CraterRefs.grid(
				math.round(corner.X / 4),
				math.round(corner.Y / 4),
				math.round(corner.Z / 4),
				n.X,
				n.Y,
				n.Z
			)
			CraterRefs.take(craterCells, keys, function(k: string): CraterRefs.Cell
				local i = cellAt[k]
				return { material = materials[i[1]][i[2]][i[3]], occupancy = occupancies[i[1]][i[2]][i[3]] }
			end)
			saved = { keys = keys, at = cellAt }
			terrain:FillBall(centre, r, Enum.Material.Air)
		end)
	end

	-- world: the whole scene reacts (board/plans/archive/aaa-vfx-research.md): exposure, fog / atmosphere, sky, sun, ambient,
	-- sun rays, depth of field - every field a curve, the Lighting restored when the layer ends or the stage stops
	builders.world = function(el)
		if not (isClient or booth) then
			return
		end
		local life = lifeOf(el)
		local hasAtmo = Lighting:FindFirstChildOfClass("Atmosphere") ~= nil
		local id = {} -- this layer's place in the mood stack (priority 0: an impact frame goes over it)
		local rays: SunRaysEffect? = nil
		if el.sunRays then
			local r = Instance.new("SunRaysEffect")
			r.Name = "KitVfxStage"
			r.Intensity = 0
			r.Spread = 1
			r.Parent = Lighting
			rays = r
		end
		local dof: DepthOfFieldEffect? = nil
		if el.dof then
			local d = Instance.new("DepthOfFieldEffect")
			d.Name = "KitVfxStage"
			d.FarIntensity = 0
			d.NearIntensity = 0
			d.InFocusRadius = 30
			d.Parent = Lighting
			dof = d
		end
		table.insert(cleanups, function()
			mood:pop(id)
			if rays then
				rays:Destroy()
			end
			if dof then
				dof:Destroy()
			end
		end)
		table.insert(updaters, function(t)
			local at = el.at or 0
			local u = (t - at) / life
			local alive = t >= at and u <= 1
			if not alive then
				mood:pop(id)
				if rays then
					rays.Intensity = 0
				end
				if dof then
					dof.FarIntensity = 0
				end
				return
			end
			local k = falloff(where.Position, el.radius)
			local scene = function(key: string, fallback: any): any
				local v = mood:baseOf(key)
				return if v == nil then fallback else v
			end
			local want: { [string]: any } = {}
			want.exposure = scene("exposure", 0) + numAt(el.exposure, u, 0) * k
			want.brightness = scene("brightness", 1) * (1 + (numAt(el.sun, u, 1) - 1) * k)
			local amb = 1 + (numAt(el.ambient, u, 1) - 1) * k
			local ambient: Color3 = scene("ambient", Color3.new(0.5, 0.5, 0.5))
			want.ambient =
				Color3.new(math.min(ambient.R * amb, 1), math.min(ambient.G * amb, 1), math.min(ambient.B * amb, 1))
			local fog = 1 + (numAt(el.fog, u, 1) - 1) * k
			local fogMix = numAt(el.fogAmount, u, if el.fogColor then 1 else 0) * k
			local fogColor: Color3 = scene("fogColor", Color3.new(1, 1, 1))
			local fogCol = if el.fogColor then colorAt(el.fogColor, u, palette) else fogColor
			if hasAtmo then
				want["atmo.density"] = math.clamp(scene("atmo.density", 0) * fog, 0, 1)
				want["atmo.haze"] = math.clamp(scene("atmo.haze", 0) * fog, 0, 10)
				want["atmo.color"] = (scene("atmo.color", Color3.new(1, 1, 1)) :: Color3):Lerp(fogCol, fogMix)
				if el.sky then
					want["atmo.decay"] = (scene("atmo.decay", Color3.new(1, 1, 1)) :: Color3):Lerp(
						colorAt(el.sky, u, palette),
						numAt(el.skyAmount, u, 1) * k
					)
				end
			else
				want.fogEnd = scene("fogEnd", 100000) / math.max(fog, 0.05)
				want.fogColor = fogColor:Lerp(fogCol, fogMix)
			end
			mood:push(id, 0, want)
			if rays then
				rays.Intensity = math.clamp(numAt(el.sunRays, u, 0) * k, 0, 1)
			end
			if dof then
				dof.FarIntensity = math.clamp(numAt(el.dof, u, 0) * k, 0, 1)
				local cam = Workspace.CurrentCamera
				dof.FocusDistance = if el.focus
					then el.focus * scale
					elseif cam then (cam.CFrame.Position - where.Position).Magnitude
					else 30
			end
		end)
	end

	builders.sound = function(el)
		local played = false
		table.insert(updaters, function(t)
			if played or t < (el.at or 0) or not o.assets then
				return
			end
			played = true
			if self.catchTo and (el.at or 0) < self.catchTo - 0.1 then
				return -- a late start: this sound's moment is past (played now it would sound with every other one)
			end
			local pitch = el.pitch or 1
			o.assets.play(el.sound, worldPoint(el.point or { 0, 0, 0 }), {
				Volume = el.volume or 1,
				PlaybackSpeed = if type(pitch) == "table" then rng:NextNumber(pitch[1], pitch[2]) else pitch,
				RollOffMaxDistance = el.radius or 500,
			})
		end)
	end

	local muted: { [string]: boolean } = {}
	local mutedPrefixes: { string } = {}
	for _, m in o.mute or {} do
		if string.sub(m, -1) == "*" then
			table.insert(mutedPrefixes, string.sub(m, 1, -2))
		else
			muted[m] = true
		end
	end
	local function isMuted(name: any): boolean
		if type(name) ~= "string" then
			return false
		end
		if muted[name] then
			return true
		end
		for _, pre in mutedPrefixes do
			if string.sub(name, 1, #pre) == pre then
				return true
			end
		end
		return false
	end
	-- surface-aware layers (board/plans/archive/aaa-vfx-research.md): `onMaterial` = { "Slate|Rock": { ...overrides },
	-- "Metal": {...}, "Water": { mute = true }, "*": {...} } - the ground under the effect (one raycast, or opts.material)
	-- picks which overrides apply: stone dust on stone, sparks on metal, splinters on wood, a splash on water
	local groundMaterial: string? = o.material
	local function groundAt(): string
		if groundMaterial then
			return groundMaterial
		end
		local params = RaycastParams.new()
		params.FilterType = Enum.RaycastFilterType.Exclude
		local ignore: { Instance } = { root }
		for _, x in o.ignore or {} do
			table.insert(ignore, x)
		end
		params.FilterDescendantsInstances = ignore
		local hit = Workspace:Raycast(where.Position + Vector3.new(0, 3, 0), Vector3.new(0, -40, 0), params)
		local found = if hit then hit.Material.Name else "Air"
		groundMaterial = found
		return found
	end
	local function withMaterial(el: any): any?
		local om = el.onMaterial
		if type(om) ~= "table" then
			return el
		end
		local mat = groundAt()
		local pick = nil
		for pattern, over in om do
			if pattern ~= "*" and table.find(string.split(pattern, "|"), mat) then
				pick = over
			end
		end
		pick = pick or om["*"]
		if pick == nil then
			return el
		end
		if pick.mute then
			return nil
		end
		local c = table.clone(el)
		c.onMaterial = nil
		for k, v in pick do
			c[k] = v
		end
		return c
	end
	-- DETAIL TIERS (the owner's limitations file, F-R06): played at a detail level (opts.detail: Low | Medium | High),
	-- a layer whose tier is above it is not built at all, and one with a tierCount for it emits that share of its
	-- count and rate (VfxBudget.layerAt). A layer's tier is its own ("tier" / "tierCount") or, where it says none,
	-- the kit's rule (VfxBudget.auto: every effect is tiered). With no level, everything plays as it is written
	local tiers = if o.detail ~= nil then VfxBudget.auto(preset.layers) else {}
	for index, raw in preset.layers or {} do
		local el = VfxBudget.layerAt(withMaterial(raw), o.detail, tiers[index])
		if el == nil then
			continue
		end
		local b = builders[el.kind]
		if isMuted(el.name) then
			continue
		end
		if b then
			b(el)
		else
			warn(`[VfxStage] unknown layer kind "{el.kind}"`)
		end
	end

	-- clock -------------------------------------------------------------------------------------------------
	local target: number? = nil
	local holdUntil: number? = nil
	local catching = false -- a late start is running the clock forward (below): steps are the effect's own time
	local conn: RBXScriptConnection
	local function applyScale()
		local s = if self.frozen or holdUntil then 0 else self.timeScale
		clockRunning = s > 0
		for _, e in emitters do
			e.pe.TimeScale = math.clamp(s * e.scale, 0, 1)
			e.pe.Enabled = e.want and clockRunning and not self.released
		end
		for _, sc in scrolling do
			sc.beam.TextureSpeed = sc.speed * s
		end
	end
	local function finish()
		if self.finished then
			return
		end
		self.finished = true
		conn:Disconnect()
		for _, c in cleanups do
			pcall(c)
		end
		for _, e in emitters do
			e.pe.Enabled = false
		end
		root:Destroy()
		live[self] = nil
		applyBloom()
		if booth then
			applyFeel(0)
		end
	end
	-- a step moves the clock by the frame's time, but never by more than the REAL time since the last step (or since
	-- the stage was made): a Heartbeat's dt is the whole PREVIOUS frame, and an effect played inside a long frame (the
	-- avatar arriving hitches a client 0.3 to 1.3 s) jumped that far into its life on its first step - seen in Studio,
	-- 2026-11-16: 1.35 s of the effect gone 0.02 s after it was played
	local stepClock = os.clock()
	local function step(dt: number)
		if self.finished then
			return
		end
		if not catching then
			dt, stepClock = VfxNet.stepBy(dt, os.clock(), stepClock)
		end
		self.lastTick = os.clock()
		if followPart then
			if not followPart.Parent then
				finish()
				return
			end
			where = followPart.CFrame * followOffset
			base.CFrame = where
		end
		-- hit-stop: preset.hitstop = [{ at, hold }] freezes the clock for `hold` REAL seconds when it crosses `at`
		if holdUntil then
			if os.clock() < holdUntil then
				for _, u in updaters do -- layers still get their frame (anchors move, camera feel settles)
					pcall(u, self.time, 0)
				end
				return
			end
			holdUntil = nil
			applyScale()
		end
		-- timewarp: preset.timewarp [[t, rate], ...] = the clock's speed over the effect's time (bullet time, slow silences)
		local warp = 1
		local w = preset.timewarp
		if type(w) == "table" and #w > 0 then
			local now = self.time
			if now >= w[1][1] and now <= w[#w][1] then
				for i = 1, #w - 1 do
					local a, b = w[i], w[i + 1]
					if now <= b[1] then
						warp = a[2] + (b[2] - a[2]) * ((now - a[1]) / math.max(1e-6, b[1] - a[1]))
						break
					end
				end
			end
		end
		local d = if self.frozen then 0 elseif catching then dt else dt * self.timeScale * warp
		local t = self.time + d
		if target and t >= target then
			d = math.max(0, target - self.time)
			t = target
			target = nil
			self.frozen = true
			applyScale()
		end
		for _, h in preset.hitstop or {} do
			if not catching and self.time < h.at and t >= h.at then
				t = h.at
				d = h.at - self.time
				holdUntil = os.clock() + (h.hold or 0.08)
				applyScale()
				break
			end
		end
		self.time = t
		-- one broken layer must not keep the whole effect alive: it is warned about once and dropped
		for i, u in updaters do
			local ok, err = (pcall :: any)(u, t, d)
			if not ok then
				warn(`[VfxStage] {o.name or "effect"}: a layer failed and was dropped: {err}`)
				updaters[i] = function() end
			end
		end
		applyBloom()
		if booth then
			local camera = Workspace.CurrentCamera
			if camera and o.cameraBase then
				if type(o.cameraBase) == "function" then
					local cf, fov = o.cameraBase(t)
					camera.CFrame = cf
					camera.FieldOfView = fov or o.cameraFov or 70
				else
					camera.CFrame = o.cameraBase
					camera.FieldOfView = o.cameraFov or 70
				end
				feel.appliedFov = 0
			end
			applyFeel(d)
		end
		if t >= self.duration then
			finish()
		end
	end
	if not booth then
		bindFeel()
	end
	live[self] = true
	conn = RunService.Heartbeat:Connect(step)
	applyScale()
	step(0)
	-- a LATE start (a broadcast that arrived o.late REAL seconds late): the effect's clock is run to where it would be
	-- by now - VfxNet.clockAt counts the hit-stops it would have held at and its slow motion - in small steps of its
	-- own time, before the first frame is drawn. A hit-stop passed over does not hold again; one it lands IN is held
	-- for what is left of it. A sound whose moment is over 0.1 s past is not played (a second late, fifteen sounds
	-- would sound at once). What it cannot do: particles emitted in those steps are all born now (a burst that
	-- should be half faded is fresh)
	local catchTo, holdLeft = VfxNet.clockAt(o.late, self.duration, preset.hitstop, preset.timewarp)
	if catchTo > 0 then
		catching = true
		self.catchTo = catchTo
		for _, d in VfxNet.catchUp(catchTo) do
			if self.finished then
				break
			end
			step(d)
		end
		catching = false
		self.catchTo = nil
		if holdLeft > 0 and not self.finished then
			holdUntil = os.clock() + holdLeft
			applyScale()
		end
	end

	function self.freeze(s: any)
		s.frozen = true
		applyScale()
	end
	function self.resume(s: any)
		s.frozen = false
		applyScale()
	end
	-- 0..1: particles cannot run faster than real time, so neither does the rest of the stage
	function self.setTimeScale(s: any, k: number)
		s.timeScale = math.clamp(k, 0, 1)
		applyScale()
	end
	-- run (at the current time scale) until the clock reaches t, then freeze exactly there; the clock never runs
	-- backwards (an earlier t just freezes now)
	function self.advanceTo(s: any, t: number)
		if t <= s.time + 1e-6 then
			s.frozen = true
			applyScale()
			return
		end
		target = t
		s.frozen = false
		applyScale()
	end
	function self.stop(_s: any)
		finish()
	end
	function self.release(s: any)
		s.released = true
		applyScale()
	end
	self.root = root
	return self :: Stage
end

-- how many mesh layers drew their stand-in shape at least one frame, because their mesh was not built yet or
-- never was (a playtest holds a game to 0 once its effects are warmed: Vfx.prewarmAtSpawn)
function VfxStage.standIns(): number
	return standInsShown
end

return VfxStage

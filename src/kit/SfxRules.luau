--!strict
-- SfxRules (ReplicatedStorage.kit.SfxRules) — the PURE half of the Sfx runtime (no game APIs; tested headless in
-- kit/test/spec/sfx.spec.luau). Game-audio middleware ideas, as data (assets/sounds/events.json):
--   an EVENT ("SwordHit") resolves through a SWITCH (a parameter picks a case: surface = metal | flesh),
--   a BLEND (a number picks the nearest sound: weight 0.15 / 0.5 / 0.9 -> light / medium / heavy) and the sound's
--   takes are the RANDOM container (Assets picks _2/_3). Volume and pitch get their random ranges here.
-- Voices: per-event cap + a global cap; when full, a new sound steals the quietest-priority voice only if it
-- outranks it (the limit sits on the PARENT, never on each child: the middleware pitfall that starved ambiences).
--
-- events.json:
-- { "buses": { "sfx": { "volume": 1 }, "ui": {...}, "music": {...}, "ambience": {...}, "voice": {...} },
--   "snapshots": { "combat": { "ambience": 0.6, "music": 0.8 } },
--   "maxVoices": 32,
--   "events": {
--     "SwordHit": { "bus": "sfx", "priority": 60, "voices": 4, "cooldown": 0.03, "volume": 1, "pitch": [0.97, 1.03],
--                   "rolloff": [8, 140], "duck": { "bus": "ambience", "to": 0.5, "seconds": 0.35 },
--                   "switch": "surface", "default": "metal",
--                   "cases": { "metal": { "blend": "weight", "sounds": { "0.15": "sword_hit_metal_light", "0.5": "sword_hit_metal_medium", "0.9": "sword_hit_metal_heavy" } },
--                              "flesh": "sword_hit_flesh_medium" } },
--     "UiClick": { "bus": "ui", "sound": "ui_click", "priority": 90 },
--     "PropImpact": { "derive": { "weight": { "from": "speed", "range": [8, 60] } },     raw game value -> blend param
--                     "rtpc": { "speed": { "range": [8, 60], "volume": [0.4, 1], "pitch": [1.05, 0.95] } },  -> volume / pitch
--                     "sounds": { "0.2": "crate_hit_light", "0.8": "crate_hit_heavy" } } } }
local SfxRules = {}

export type Resolved = {
	event: string,
	sound: string,
	bus: string,
	priority: number,
	volume: number,
	pitch: number,
	rolloff: { number },
	voices: number,
	cooldown: number,
	duck: any?,
	directivity: { [number]: number }?,
}

export type Voice = { event: string, priority: number, started: number, id: number }

local DEFAULT_BUSES = { "sfx", "ui", "music", "ambience", "voice" }

local function num(v: any, fallback: number): number
	if type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge then
		return v
	end
	return fallback
end

local function range(v: any, fallback: number, roll: number): number
	if type(v) == "table" and #v == 2 then
		local lo, hi = num(v[1], fallback), num(v[2], fallback)
		return lo + (hi - lo) * roll
	end
	return num(v, fallback)
end

-- a raw value -> 0..1 along [lo, hi] (clamped; a bad range is the identity on 0..1)
function SfxRules.curve(v: number, bounds: unknown): number
	if type(bounds) ~= "table" or type((bounds :: any)[1]) ~= "number" or type((bounds :: any)[2]) ~= "number" then
		return math.clamp(v, 0, 1)
	end
	local lo, hi = (bounds :: any)[1], (bounds :: any)[2]
	if hi == lo then
		return if v >= hi then 1 else 0
	end
	return math.clamp((v - lo) / (hi - lo), 0, 1)
end

-- the sound a case names: a string, or { blend = "<param>", sounds = { ["<number>"] = name } } (nearest wins)
local function pickCase(case: any, params: { [string]: any }): string?
	if type(case) == "string" then
		return case
	end
	if type(case) ~= "table" then
		return nil
	end
	if type(case.sound) == "string" then
		return case.sound
	end
	local sounds = case.sounds
	if type(sounds) ~= "table" then
		return nil
	end
	local x = num(params[case.blend or "weight"], 0.5)
	local best, bestD = nil, math.huge
	-- deterministic over keys: sort them (pairs order is not stable)
	local keys = {}
	for k in sounds do
		table.insert(keys, k)
	end
	table.sort(keys)
	for _, k in keys do
		local at = tonumber(k)
		if at and type(sounds[k]) == "string" and math.abs(at - x) < bestD then
			best, bestD = sounds[k], math.abs(at - x)
		end
	end
	return best
end

-- resolve an event to one concrete sound. roll1/roll2 in [0, 1) (the caller's Random: tests pass fixed ones).
-- Returns nil + a reason for an unknown event or a case that names nothing.
function SfxRules.resolve(
	catalog: any,
	event: string,
	params: { [string]: any }?,
	roll1: number?,
	roll2: number?
): (Resolved?, string?)
	local p: { [string]: any } = table.clone(params or {})
	local events = type(catalog) == "table" and catalog.events
	local e = type(events) == "table" and events[event]
	if type(e) ~= "table" then
		return nil, `unknown sfx event "{event}"`
	end
	-- DERIVE (AAA gap S3): a blend parameter from a raw game value the caller knows - "derive": { "weight": { "from":
	-- "speed", "range": [10, 60] } } turns an impact speed into a 0..1 weight (a weight the caller gives wins)
	if type(e.derive) == "table" then
		for name, d in e.derive do
			if p[name] == nil and type(d) == "table" and type(d.from) == "string" then
				local v = p[d.from]
				if type(v) == "number" and v == v then
					p[name] = SfxRules.curve(v, d.range)
				end
			end
		end
	end
	local sound: string?
	if type(e.switch) == "string" and type(e.cases) == "table" then
		local key = p[e.switch]
		local case = if key ~= nil then e.cases[tostring(key)] else nil
		if case == nil and e.default ~= nil then
			case = e.cases[tostring(e.default)]
		end
		sound = pickCase(case, p)
	elseif type(e.sounds) == "table" then
		sound = pickCase(e, p)
	elseif type(e.sound) == "string" then
		sound = e.sound
	end
	-- the FAR layer (AAA gap S7): a distant hit is a different sound, not the near one turned down - "far": { "sound":
	-- "<name>", "beyond": studs } (the caller passes params.distance; the runtime does)
	if type(e.far) == "table" and type(e.far.sound) == "string" and type(p.distance) == "number" then
		if p.distance > num(e.far.beyond, math.huge) then
			sound = e.far.sound
		end
	end
	if not sound then
		return nil, `sfx event "{event}" names no sound for {e.switch or "its"} = {tostring(p[e.switch or ""])}`
	end
	local bus = if type(e.bus) == "string" then e.bus else "sfx"
	local roll = e.rolloff
	-- RTPC curves (AAA gap S3): a raw game value moves volume / pitch continuously - "rtpc": { "speed": { "range":
	-- [10, 60], "volume": [0.5, 1], "pitch": [0.95, 1.1] } } (a value the caller does not give leaves them alone)
	local rv, rp = 1, 1
	if type(e.rtpc) == "table" then
		for name, c in e.rtpc do
			local v = p[name]
			if type(v) == "number" and v == v and type(c) == "table" then
				local t = SfxRules.curve(v, c.range)
				if type(c.volume) == "table" then
					rv *= num(c.volume[1], 1) + (num(c.volume[2], 1) - num(c.volume[1], 1)) * t
				end
				if type(c.pitch) == "table" then
					rp *= num(c.pitch[1], 1) + (num(c.pitch[2], 1) - num(c.pitch[1], 1)) * t
				end
			end
		end
	end
	return {
		event = event,
		sound = sound,
		bus = bus,
		priority = num(e.priority, 50),
		volume = math.clamp(range(e.volume, 1, roll1 or 0.5) * num(p.volume, 1) * rv, 0, 4),
		pitch = math.clamp(range(e.pitch, 1, roll2 or 0.5) * num(p.pitch, 1) * rp, 0.25, 4),
		rolloff = if type(roll) == "table" and #roll == 2 then { num(roll[1], 8), num(roll[2], 140) } else { 8, 140 },
		voices = math.max(1, math.floor(num(e.voices, 6))),
		cooldown = math.max(0, num(e.cooldown, 0)),
		duck = e.duck,
		directivity = SfxRules.angleCurve(e.directivity),
	},
		nil
end

-- how a resolved sound is heard from `distance` studs (AAA gaps S6 / S7) -> (priority, low-pass cutoff Hz):
--   the player's OWN sounds outrank the rest (+25) and far sounds yield (-20 at the edge of hearing) when voices run
--   short; the air eats the highs - 20 kHz at the source down to 2 kHz at the rolloff's far end (a log sweep)
SfxRules.OWN_BONUS = 25
SfxRules.FAR_PENALTY = 20
function SfxRules.listen(r: Resolved, distance: number?, mine: boolean?): (number, number)
	local far = if type(r.rolloff) == "table" then num(r.rolloff[2], 140) else 140
	local t = if type(distance) == "number"
			and distance == distance
			and far > 0
		then math.clamp(distance / far, 0, 1)
		else 0
	local priority = r.priority + (if mine then SfxRules.OWN_BONUS else 0) - t * SfxRules.FAR_PENALTY
	return priority, 20000 * (2000 / 20000) ^ t
end

-- May this sound start now? active = the voices playing. Returns ok, and the voice to steal (stop) if any.
-- Rules: the same event within its cooldown -> no; the event at its own cap -> steal its OLDEST voice;
-- the global cap -> steal the lowest-priority voice only if the new one outranks it (ties: keep what plays).
function SfxRules.admit(
	r: Resolved,
	active: { Voice },
	now: number,
	lastStart: { [string]: number },
	maxVoices: number
): (boolean, Voice?)
	local last = lastStart[r.event]
	if last and now - last < r.cooldown then
		return false, nil
	end
	local mine: { Voice } = {}
	for _, v in active do
		if v.event == r.event then
			table.insert(mine, v)
		end
	end
	if #mine >= r.voices then
		table.sort(mine, function(a, b)
			return a.started < b.started
		end)
		return true, mine[1]
	end
	if #active >= maxVoices then
		local lowest: Voice? = nil
		for _, v in active do
			if lowest == nil or v.priority < lowest.priority then
				lowest = v
			end
		end
		if lowest and lowest.priority < r.priority then
			return true, lowest
		end
		return false, nil
	end
	return true, nil
end

-- the bus volumes a snapshot sets (unknown buses ignored, missing ones back to their base volume)
function SfxRules.snapshot(catalog: any, name: string?): { [string]: number }
	local out: { [string]: number } = {}
	local buses = (type(catalog) == "table" and catalog.buses) or {}
	for _, b in DEFAULT_BUSES do
		out[b] = num(type(buses[b]) == "table" and buses[b].volume, 1)
	end
	for b, v in buses do
		if type(v) == "table" then
			out[b] = num(v.volume, 1)
		end
	end
	local snaps = type(catalog) == "table" and catalog.snapshots
	local snap = name and type(snaps) == "table" and snaps[name]
	if type(snap) == "table" then
		for b, v in snap do
			if out[b] ~= nil then
				out[b] = math.clamp(num(v, out[b]), 0, 4)
			end
		end
	end
	return out
end

-- every sound name an event can resolve to (for the catalog check and preloading)
function SfxRules.sounds(catalog: any): { [string]: { string } }
	local out: { [string]: { string } } = {}
	local events = type(catalog) == "table" and catalog.events or {}
	for name, e in events do
		local list = {}
		local function add(case: any)
			if type(case) == "string" then
				table.insert(list, case)
			elseif type(case) == "table" then
				if type(case.sound) == "string" then
					table.insert(list, case.sound)
				end
				if type(case.sounds) == "table" then
					for _, s in case.sounds do
						if type(s) == "string" then
							table.insert(list, s)
						end
					end
				end
			end
		end
		if type(e) == "table" then
			add(e)
			if type(e.cases) == "table" then
				for _, c in e.cases do
					add(c)
				end
			end
		end
		table.sort(list)
		out[name] = list
	end
	return out
end

-- ---------------------------------------------------------------- the mix graph (LIMITATIONS_FIXES_V4 SFX-X 7.3)
-- What the runtime builds, decided here so a spec can read it and a Studio playtest can hold the built graph to it:
--   AudioPlayer -> [AudioFilter, the air] -> AudioEmitter (acoustic sim, angle curve) -> AudioListener per spatial bus
--   -> [AudioReverb per zone, bypassed when dry] -> Bus fader -> [sidechain AudioCompressor on music] -> Master fader
--   -> master AudioCompressor -> AudioDeviceOutput.
-- Units are the engine's: Threshold / MakeupGain / Wet / Dry in dB, Attack / Release / Decay / delays in seconds.

-- DIRECTIVITY (AngleAttenuation): degrees off the emitter's LookVector (0 = straight ahead, 180 = behind) -> gain.
-- Named shapes from how the sources radiate: a barrel throws its blast forward (the classic muzzle cardioid, about
-- -10 dB behind); a swung blade is nearly omni (its whoosh rides the whole arc, a few dB down at the back); a mouth is
-- a soft cardioid (-6 dB behind). A sound with no directivity stays omni (no curve: the engine's constant 1).
SfxRules.DIRECTIVITY = {
	muzzle = { [0] = 1, [30] = 1, [90] = 0.55, [150] = 0.35, [180] = 0.32 },
	blade = { [0] = 1, [90] = 0.9, [180] = 0.7 },
	voice = { [0] = 1, [60] = 0.95, [120] = 0.7, [180] = 0.5 },
}

-- a directivity -> an engine curve ({ [degrees] = gain }, 0..180 and 0..1, at least two points incl. 0), or nil (omni).
-- A named shape, or a hand table ({ "0": 1, "180": 0.4 } from JSON: keys may be strings). A bad table is omni.
function SfxRules.angleCurve(d: unknown): { [number]: number }?
	if type(d) == "string" then
		local named = SfxRules.DIRECTIVITY[d]
		return if named then table.clone(named) else nil
	end
	if type(d) ~= "table" then
		return nil
	end
	local out: { [number]: number } = {}
	local n = 0
	for k, v in d :: { [any]: any } do
		local deg = tonumber(k)
		local gain = if type(v) == "number" then v else nil
		if deg == nil or gain == nil or deg ~= deg or gain ~= gain or deg < 0 or deg > 180 then
			return nil
		end
		out[deg] = math.clamp(gain, 0, 1)
		n += 1
	end
	if n < 2 or out[0] == nil then
		return nil
	end
	return out
end

-- COMPRESSORS. Standard values, said here so nobody re-guesses them:
--   master: a peak-catching bus glue - 4:1 above -6 dB, 5 ms attack, 150 ms release, no makeup (it only stops a pile of
--     hits clipping the output; at normal levels it does nothing).
--   sidechain duck (music under sfx + voice): the broadcast ducking recipe - 4:1 keyed at -30 dB, 10 ms attack (fast
--     enough to clear room for a hit's transient), 250 ms release (the music comes back without pumping).
-- The event duck ("duck": {...} on an event, a fader tween) is KEPT: it is a scripted dip for one named moment; the
-- compressor is the continuous one. They stack.
SfxRules.MASTER_COMP = { threshold = -6, ratio = 4, attack = 0.005, release = 0.15, makeup = 0 }
SfxRules.DUCK_COMP = { threshold = -30, ratio = 4, attack = 0.01, release = 0.25, makeup = 0 }
SfxRules.DUCK_DEFAULT = { music = { "sfx", "voice" } }

-- the engine's ranges for an AudioCompressor's properties
local COMP_RANGE: { [string]: { number } } = {
	threshold = { -80, 0 },
	ratio = { 1, 50 },
	attack = { 0.0001, 1 },
	release = { 0.001, 5 },
	makeup = { -80, 30 },
}
local function comp(base: { [string]: number }, over: unknown): { [string]: number }
	local out = table.clone(base)
	if type(over) == "table" then
		for k, r in COMP_RANGE do
			local v = (over :: any)[k]
			if type(v) == "number" and v == v then
				out[k] = math.clamp(v, r[1], r[2])
			end
		end
	end
	return out
end

-- REVERB presets for zones (AudioReverb). Typical decay times for the spaces (an open stone courtyard ~1.2 s, a stone
-- hall ~2.6 s, a catacomb / cave ~3.8 s) - textbook RT60 ranges, NOT fitted to measured impulse responses (the OpenAIR
-- IR ingest of SFX-X 7.3 is still open: fit these when it lands). Wet / dry in dB; highCut: stone eats the air.
SfxRules.REVERBS = {
	CourtyardOpen = {
		decay = 1.2,
		early = 0.012,
		late = 0.02,
		density = 0.6,
		diffusion = 0.7,
		wet = -14,
		dry = 0,
		highCut = 9000,
	},
	HallStone = {
		decay = 2.6,
		early = 0.022,
		late = 0.03,
		density = 1,
		diffusion = 1,
		wet = -9,
		dry = 0,
		highCut = 6500,
	},
	CatacombCave = {
		decay = 3.8,
		early = 0.035,
		late = 0.045,
		density = 1,
		diffusion = 0.85,
		wet = -7,
		dry = -1,
		highCut = 4200,
	},
}
local REVERB_RANGE: { [string]: { number } } = {
	decay = { 0.1, 20 },
	early = { 0, 0.3 },
	late = { 0, 0.1 },
	density = { 0, 1 },
	diffusion = { 0, 1 },
	wet = { -80, 20 },
	dry = { -80, 20 },
	highCut = { 20, 20000 },
}

-- a reverb name (or a hand table) -> its clamped parameters, or nil (dry: the reverb is bypassed)
function SfxRules.reverb(spec: unknown, catalog: any?): { [string]: number }?
	local base: any = nil
	if type(spec) == "string" then
		local own = type(catalog) == "table" and type(catalog.reverbs) == "table" and catalog.reverbs[spec]
		base = if type(own) == "table" then own else SfxRules.REVERBS[spec]
	elseif type(spec) == "table" then
		base = spec
	end
	if type(base) ~= "table" then
		return nil
	end
	local ref: { [string]: number } = SfxRules.REVERBS.HallStone
	local out: { [string]: number } = {}
	for k, r in REVERB_RANGE do
		local v = base[k]
		out[k] = math.clamp(if type(v) == "number" and v == v then v else ref[k], r[1], r[2])
	end
	return out
end

export type GraphBus = { name: string, volume: number, spatial: boolean, acoustic: boolean, reverb: boolean }
export type Graph = {
	buses: { GraphBus },
	master: { [string]: number },
	ducks: { { bus: string, keys: { string }, comp: { [string]: number } } },
}

local SPATIAL_BUSES = { sfx = true, ambience = true, voice = true } -- ui + music play 2D
local REVERB_BUSES = { sfx = true, voice = true } -- ambience beds carry their own space

-- the whole graph the runtime builds from a catalog. catalog.mix (all optional):
--   { "master": { threshold, ratio, attack, release, makeup } | false,
--     "duck": { "<bus>": { "keys": ["sfx", "voice"], threshold, ... } | false },
--     "acoustic": false }   (acoustic simulation on every spatial emitter / listener unless false)
-- A sidechain keyed by its own bus, by an unknown bus, or with no keys is dropped (a loop / nothing to listen to).
function SfxRules.graph(catalog: any): Graph
	local mix = (type(catalog) == "table" and type(catalog.mix) == "table") and catalog.mix or {}
	local vols = SfxRules.snapshot(catalog, nil)
	local acoustic = mix.acoustic ~= false
	local buses: { GraphBus } = {}
	local known: { [string]: boolean } = {}
	for _, name in DEFAULT_BUSES do
		known[name] = true
		table.insert(buses, {
			name = name,
			volume = vols[name] or 1,
			spatial = SPATIAL_BUSES[name] == true,
			acoustic = acoustic and SPATIAL_BUSES[name] == true,
			reverb = REVERB_BUSES[name] == true,
		})
	end
	local ducks = {}
	local spec: any = if type(mix.duck) == "table" then mix.duck else SfxRules.DUCK_DEFAULT
	local names = {}
	for bus in spec do
		if type(bus) == "string" then
			table.insert(names, bus)
		end
	end
	table.sort(names)
	for _, bus in names do
		local d = spec[bus]
		local keysIn = if type(d) == "table" and type(d.keys) == "table"
			then d.keys
			elseif type(d) == "table" then d
			else nil
		if known[bus] and keysIn then
			local keys = {}
			for _, k in keysIn do
				if type(k) == "string" and known[k] and k ~= bus and not table.find(keys, k) then
					table.insert(keys, k)
				end
			end
			if #keys > 0 then
				table.insert(ducks, { bus = bus, keys = keys, comp = comp(SfxRules.DUCK_COMP, d) })
			end
		end
	end
	return {
		buses = buses,
		master = if mix.master == false then {} else comp(SfxRules.MASTER_COMP, mix.master),
		ducks = ducks,
	}
end

return SfxRules

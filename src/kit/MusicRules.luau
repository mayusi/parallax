--!strict
-- MusicRules.luau — the decisions of the adaptive music (pure; kit/test/spec/music.spec.luau). AAA gap S5:
--   VERTICAL LAYERING: stems that loop together, each faded in as the INTENSITY climbs ("from" -> "full")
--   INTENSITY: gameplay events (kit Bus: Hit, Parried, Death ...) bump it, it decays with a half-life
--   HORIZONTAL TIMING: changes land on the beat / bar (a stinger waits for the next beat)
-- music json: { "bpm": 90, "beatsPerBar": 4, "halfLife": 6, "bumps": { "Hit": 0.2, "Death": 0.5 },
--   "stems": [ { "sound": "dojo_pad", "from": 0 }, { "sound": "dojo_drums", "from": 0.25, "full": 0.55 } ],
--   "stingers": { "Death": "dojo_stinger" } }
local MusicRules = {}

local function finite(x: unknown): boolean
	return type(x) == "number" and x == x and x ~= math.huge and x ~= -math.huge
end

-- an event's push on the intensity (0..1)
function MusicRules.bump(spec: any, intensity: number, event: string): number
	local b = if type(spec) == "table" and type(spec.bumps) == "table" then spec.bumps[event] else nil
	if not finite(b) then
		return intensity
	end
	return math.clamp(intensity + (b :: number), 0, 1)
end

-- the intensity after `dt` seconds of nothing happening (a half-life decay)
function MusicRules.decay(spec: any, intensity: number, dt: number): number
	local h = if type(spec) == "table" and finite(spec.halfLife) and spec.halfLife > 0 then spec.halfLife else 6
	if not finite(dt) or dt <= 0 then
		return intensity
	end
	return intensity * 0.5 ^ (dt / h)
end

-- each stem's volume at this intensity: 0 below its "from", rising (eased) to 1 at its "full"
function MusicRules.stems(spec: any, intensity: number): { [string]: number }
	local out: { [string]: number } = {}
	for _, s in (if type(spec) == "table" and type(spec.stems) == "table" then spec.stems else {}) :: { any } do
		if type(s) == "table" and type(s.sound) == "string" then
			local from = if finite(s.from) then s.from else 0
			local full = if finite(s.full) and s.full > from then s.full else from
			local v
			if intensity < from then
				v = 0
			elseif full <= from then
				v = 1
			else
				local t = math.clamp((intensity - from) / (full - from), 0, 1)
				v = t * t * (3 - 2 * t)
			end
			out[s.sound] = math.max(out[s.sound] or 0, v * (if finite(s.volume) then s.volume else 1))
		end
	end
	return out
end

local function beat(spec: any): number
	local bpm = if type(spec) == "table" and finite(spec.bpm) and spec.bpm > 0 then spec.bpm else 90
	return 60 / bpm
end

-- the next beat (or bar) boundary after `now`, counted from `start` (when the stems began)
function MusicRules.nextBeat(spec: any, start: number, now: number): number
	local b = beat(spec)
	return start + math.ceil((now - start) / b - 1e-9) * b
end

function MusicRules.nextBar(spec: any, start: number, now: number): number
	local per = if type(spec) == "table"
			and finite(spec.beatsPerBar)
			and spec.beatsPerBar > 0
		then spec.beatsPerBar
		else 4
	local bar = beat(spec) * per
	return start + math.ceil((now - start) / bar - 1e-9) * bar
end

-- the named mood at an intensity (for snapshots / UI): calm < tension < combat
function MusicRules.mood(intensity: number): string
	return if intensity >= 0.6 then "combat" elseif intensity >= 0.2 then "tension" else "calm"
end

return MusicRules

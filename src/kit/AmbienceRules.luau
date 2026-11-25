--!strict
-- AmbienceRules.luau — the decisions of the Ambience runtime (pure, spec-tested in kit/test/spec/ambience.spec.luau).
-- A world's ambience (src/shared/<World>Ambience.json, made by `kit sfx ambience <World>` from its blueprint) has zones
-- of four kinds - forest, water, stone, and open (everywhere else) - a bed per kind and scatter rules. Here: how
-- present each kind is at a point, the beds' volumes there, and when / where a scatter one-shot plays.
local AmbienceRules = {}

AmbienceRules.KINDS = { "open", "forest", "water", "stone" }

local function finite(x: unknown): boolean
	return type(x) == "number" and x == x and x ~= math.huge and x ~= -math.huge
end

-- how present each kind is at (x, z), 0..1: 1 inside a zone, fading to 0 over its fade past the edge; "open" is what
-- the other kinds leave (1 - the strongest of them)
function AmbienceRules.presence(spec: any, x: number, z: number): { [string]: number }
	local out = { open = 0, forest = 0, water = 0, stone = 0 }
	if type(spec) ~= "table" or not finite(x) or not finite(z) then
		out.open = 1
		return out
	end
	local strongest = 0
	for _, zone in (if type(spec.zones) == "table" then spec.zones else {}) :: { any } do
		if type(zone) == "table" and out[zone.kind] ~= nil and zone.kind ~= "open" then
			local zx, zz, r = zone.x, zone.z, zone.r
			if finite(zx) and finite(zz) and finite(r) then
				local fade = if finite(zone.fade) and zone.fade > 0 then zone.fade else 0
				local d = math.sqrt((x - zx) ^ 2 + (z - zz) ^ 2)
				local w = if d <= r then 1 elseif fade > 0 then math.clamp(1 - (d - r) / fade, 0, 1) else 0
				out[zone.kind] = math.max(out[zone.kind], w)
				strongest = math.max(strongest, w)
			end
		end
	end
	out.open = 1 - strongest
	return out
end

-- the wind on the exposed beds: open land and stone swell with it (0.55x in still air -> 1x at `windFull` studs/s);
-- forests and water keep their own level (spec.windy lists the kinds; default open + stone)
AmbienceRules.WIND_FULL = 14
function AmbienceRules.windScale(spec: any, kind: string, wind: number?): number
	if not finite(wind) then
		return 1
	end
	local windy = if type(spec) == "table" and type(spec.windy) == "table" then spec.windy else { "open", "stone" }
	if not table.find(windy, kind) then
		return 1
	end
	return 0.55 + 0.45 * math.clamp((wind :: number) / AmbienceRules.WIND_FULL, 0, 1)
end

-- the beds' target volumes at (x, z): { [bed] = presence x the kind's volume [x the wind] } (two kinds on one bed:
-- the louder)
function AmbienceRules.beds(spec: any, x: number, z: number, wind: number?): { [string]: number }
	local here = AmbienceRules.presence(spec, x, z)
	local out: { [string]: number } = {}
	local beds = if type(spec) == "table" and type(spec.beds) == "table" then spec.beds else {}
	local volume = if type(spec) == "table" and type(spec.volume) == "table" then spec.volume else {}
	for _, kind in AmbienceRules.KINDS do
		local bed = beds[kind]
		if type(bed) == "string" then
			local v = if finite(volume[kind]) then math.clamp(volume[kind], 0, 2) else 1
			out[bed] = math.max(out[bed] or 0, here[kind] * v * AmbienceRules.windScale(spec, kind, wind))
		end
	end
	return out
end

-- is `hour` inside a rule's "hours" [from, to)? (wraps past midnight: { 20, 5 } is the night; no hours = always)
function AmbienceRules.inHours(range: unknown, hour: number?): boolean
	if not finite(hour) or type(range) ~= "table" or not finite((range :: any)[1]) or not finite((range :: any)[2]) then
		return true
	end
	local from, to, h = (range :: any)[1] % 24, (range :: any)[2] % 24, (hour :: number) % 24
	if from <= to then
		return h >= from and h < to
	end
	return h >= from or h < to
end

-- a scatter rule's chance to sound here [at this hour]: its kinds' strongest presence (0 outside its hours, 0 for a
-- rule with no kinds)
function AmbienceRules.chance(rule: any, here: { [string]: number }, hour: number?): number
	if type(rule) == "table" and not AmbienceRules.inHours(rule.hours, hour) then
		return 0
	end
	local best = 0
	for _, kind in (if type(rule) == "table" and type(rule.kinds) == "table" then rule.kinds else {}) :: { any } do
		local p = here[kind]
		if finite(p) then
			best = math.max(best, p)
		end
	end
	return best
end

local function between(range: unknown, roll: number, default: number): number
	if type(range) == "table" and finite((range :: any)[1]) and finite((range :: any)[2]) then
		local lo, hi = (range :: any)[1], (range :: any)[2]
		if hi < lo then
			lo, hi = hi, lo
		end
		return lo + (hi - lo) * math.clamp(roll, 0, 1)
	end
	return default
end

-- the next moment a rule may fire after `now` (roll 0..1 picks inside "every"); never sooner than 0.5 s
function AmbienceRules.nextAt(rule: any, now: number, roll: number): number
	local every = if type(rule) == "table" then rule.every else nil
	return now + math.max(0.5, between(every, roll, 10))
end

-- where a one-shot plays, from the listener: (dx, dy, dz) from three 0..1 rolls (angle, distance, height)
function AmbienceRules.offset(rule: any, ra: number, rd: number, rh: number): (number, number, number)
	local r = if type(rule) == "table" then rule else {}
	local angle = math.clamp(ra, 0, 1) * 2 * math.pi
	local d = between(r.distance, rd, 40)
	local h = between(r.height, rh, 8)
	return math.cos(angle) * d, h, math.sin(angle) * d
end

return AmbienceRules

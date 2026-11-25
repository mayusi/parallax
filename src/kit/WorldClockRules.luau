--!strict
-- WorldClockRules.luau — the decisions of the world's clock and wind (pure; kit/test/spec/worldclock.spec.luau). AAA
-- gaps W8 / W9 / S8: ONE time of day and ONE wind that the lighting, the grass and particles (Workspace.GlobalWind) and
-- the ambience all read.
--   day  = { length = seconds per day, start = hour, keys = { { hour, ambient, outdoorAmbient, brightness, exposure,
--            atmosphere = { density, haze, glare, offset, color, decay } }, ... } }   (sorted by hour; resolved by kit world)
--   wind = { direction = degrees (0 = +Z, 90 = +X), speed = { low, high } studs/s, period = seconds of a gust cycle }
local WorldClockRules = {}

local function finite(x: unknown): boolean
	return type(x) == "number" and x == x and x ~= math.huge and x ~= -math.huge
end

-- the hour of the day `seconds` after the start (wraps at 24)
function WorldClockRules.hourAt(day: any, seconds: number): number
	local length = if type(day) == "table" and finite(day.length) and day.length > 0 then day.length else 1200
	local start = if type(day) == "table" and finite(day.start) then day.start else 12
	return (start + (seconds / length) * 24) % 24
end

local function lerp(a: any, b: any, t: number): any
	if type(a) == "number" and type(b) == "number" then
		return a + (b - a) * t
	end
	if type(a) == "table" and type(b) == "table" then
		local out = {}
		for k, v in a do
			out[k] = if b[k] ~= nil then lerp(v, b[k], t) else v
		end
		for k, v in b do
			if out[k] == nil then
				out[k] = v
			end
		end
		return out
	end
	return if t < 0.5 then a else b
end
WorldClockRules.lerp = lerp

-- the lighting at `hour`: the keys either side blended (round the clock: the last key blends into the first)
function WorldClockRules.at(day: any, hour: number): any
	local keys = if type(day) == "table" and type(day.keys) == "table" then day.keys else {}
	if #keys == 0 then
		return nil
	end
	if #keys == 1 then
		return keys[1]
	end
	local h = hour % 24
	local prev, nxt = keys[#keys], keys[1]
	for i, k in keys do
		if k.hour > h then
			nxt = k
			prev = keys[if i == 1 then #keys else i - 1]
			break
		end
		prev = k
		nxt = keys[if i == #keys then 1 else i + 1]
	end
	local span = (nxt.hour - prev.hour) % 24
	local t = if span > 0 then ((h - prev.hour) % 24) / span else 0
	-- a smooth step: dawn and dusk ease in and out instead of a straight ramp
	t = t * t * (3 - 2 * t)
	return lerp(prev, nxt, t)
end

-- the wind `seconds` in: (unit x, unit z, speed) - a slow gust cycle and a small swing of direction
function WorldClockRules.wind(wind: any, seconds: number): (number, number, number)
	if type(wind) ~= "table" then
		return 0, 0, 0
	end
	local dir = math.rad(if finite(wind.direction) then wind.direction else 0)
	local lo = if type(wind.speed) == "table" and finite(wind.speed[1]) then wind.speed[1] else 2
	local hi = if type(wind.speed) == "table" and finite(wind.speed[2]) then wind.speed[2] else lo
	local p = if finite(wind.period) and wind.period > 0 then wind.period else 40
	local g = 0.5
		+ 0.5
			* (0.6 * math.sin(2 * math.pi * seconds / p) + 0.4 * math.sin(2 * math.pi * seconds / (p * 0.37) + 1.3))
	g = math.clamp(g, 0, 1)
	local swing = math.rad(12) * math.sin(2 * math.pi * seconds / (p * 2.7))
	return math.sin(dir + swing), math.cos(dir + swing), lo + (hi - lo) * g
end

-- is `hour` inside [from, to)? (wraps past midnight: { 20, 5 } is the night)
function WorldClockRules.inHours(range: unknown, hour: number): boolean
	if type(range) ~= "table" or not finite((range :: any)[1]) or not finite((range :: any)[2]) then
		return true
	end
	local from, to = (range :: any)[1] % 24, (range :: any)[2] % 24
	local h = hour % 24
	if from <= to then
		return h >= from and h < to
	end
	return h >= from or h < to
end

return WorldClockRules

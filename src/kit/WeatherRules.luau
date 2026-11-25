--!strict
-- WeatherRules.luau (kit) — WEATHER THAT CHANGES (the owner's method list: "Dynamic weather systems" - the kit had
-- one weather a world, for ever). A world's blueprint may say a CYCLE of weathers:
--   "weather": { "cycle": [ { "ambient": "clear", "minutes": 10 },
--                            { "ambient": "rain", "minutes": 6, "fog": 0.5, "dim": 0.25 } ], "change": 40 }
-- Each stage lasts its minutes; over the last "change" seconds of a stage it fades into the next, and the last
-- stage fades into the first. The cycle is read off ONE clock - the server's (workspace:GetServerTimeNow()) - so
-- every player stands in the same weather at the same moment and nothing is sent between them.
--   ambient: what falls ("clear" | "rain" | "snow" | "ash" | "leaves" | "embers" | "sand")
--   fog:     0..1, how far the air closes in (the server thickens Roblox's Atmosphere by it: WorldClock.
--            In a place with no Atmosphere one is made, which turns Roblox's older FogStart / FogEnd off)
--   dim:     0..0.6, how much of the daylight the weather takes
-- Pure: no services, no instances (kit/test/spec/worldweather.spec.luau). The compiler checks a blueprint with
-- Rules.read and writes what it returns into the world; the server's WorldClock plays its light and air (they
-- replicate), each client's Ambient script what falls round its own camera - both off that one clock.
local Rules = {}

Rules.KINDS = { clear = true, rain = true, snow = true, ash = true, leaves = true, embers = true, sand = true }
Rules.CHANGE = 30 -- seconds: a stage's fade into the next when the blueprint says none
Rules.MINUTES = { 0.5, 180 } -- a stage lasts this long
Rules.DIM_MOST = 0.6 -- a weather never takes more of the light than this (a world is lit by its own lighting)

local function number(v: any): boolean
	return type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge
end

-- a blueprint's "weather" -> what the world carries ({ change, total, stages = { { ambient, seconds, fog, dim } } }),
-- and what is wrong with it (then nothing is carried)
function Rules.read(weather: any): (any, { string })
	local problems = {}
	if type(weather) ~= "table" or type(weather.cycle) ~= "table" then
		return nil,
			{
				'"weather" is { "cycle": [ { "ambient": "clear", "minutes": 10 }, { "ambient": "rain", "minutes": 6 } ], "change": <seconds> } (or false: one weather for ever)',
			}
	end
	-- (a list, in the author's order: a JSON object's stages would come in any order)
	local count = 0
	for _ in weather.cycle do
		count += 1
	end
	if count ~= #weather.cycle then
		return nil, { 'weather.cycle is a list: [ { "ambient", "minutes" }, ... ]' }
	end
	for k in weather do
		if k ~= "cycle" and k ~= "change" then
			table.insert(problems, `weather.{tostring(k)}: a weather says "cycle" and "change", nothing else`)
		end
	end
	local stages = {}
	for i, st in weather.cycle do
		if type(st) ~= "table" then
			table.insert(problems, `weather.cycle[{i}] is \{ "ambient", "minutes", "fog"?, "dim"? }`)
			continue
		end
		local stray = false
		for k in st do
			if k ~= "ambient" and k ~= "minutes" and k ~= "fog" and k ~= "dim" then
				table.insert(
					problems,
					`weather.cycle[{i}].{tostring(k)}: a stage says "ambient", "minutes", "fog", "dim", nothing else`
				)
				stray = true
			end
		end
		if stray then
			continue
		end
		local ambient = if st.ambient == nil then "clear" else st.ambient
		if type(ambient) ~= "string" or not Rules.KINDS[ambient] then
			table.insert(
				problems,
				`weather.cycle[{i}].ambient is "clear" | "rain" | "snow" | "ash" | "leaves" | "embers" | "sand" (got {tostring(
					st.ambient
				)})`
			)
			continue
		end
		if not number(st.minutes) or st.minutes < Rules.MINUTES[1] or st.minutes > Rules.MINUTES[2] then
			table.insert(
				problems,
				`weather.cycle[{i}].minutes is how long the {ambient} lasts: {Rules.MINUTES[1]} to {Rules.MINUTES[2]} (got {tostring(
					st.minutes
				)})`
			)
			continue
		end
		local fog, dim = st.fog, st.dim
		if fog ~= nil and (not number(fog) or fog < 0 or fog > 1) then
			table.insert(problems, `weather.cycle[{i}].fog is 0 to 1 (got {tostring(fog)})`)
			continue
		end
		if dim ~= nil and (not number(dim) or dim < 0 or dim > Rules.DIM_MOST) then
			table.insert(problems, `weather.cycle[{i}].dim is 0 to {Rules.DIM_MOST} (got {tostring(dim)})`)
			continue
		end
		table.insert(stages, { ambient = ambient, seconds = st.minutes * 60, fog = fog or 0, dim = dim or 0 })
	end
	if #problems > 0 then
		return nil, problems
	end
	if #stages < 2 then
		return nil, { 'a weather "cycle" has two stages or more: with one, nothing changes (say "ambient" instead)' }
	end
	-- two stages in a row that are the same weather are one stage (the last and the first are in a row too)
	for i, st in stages do
		local nxt = stages[i % #stages + 1]
		if st.ambient == nxt.ambient and st.fog == nxt.fog and st.dim == nxt.dim then
			return nil,
				{
					`weather.cycle[{i}] and the stage after it are the same weather ({st.ambient}): nothing changes between them - make them one stage`,
				}
		end
	end
	local change = if weather.change == nil then Rules.CHANGE else weather.change
	local shortest = math.huge
	for _, st in stages do
		shortest = math.min(shortest, st.seconds)
	end
	if not number(change) or change < 1 or change > shortest / 2 then
		return nil,
			{
				`weather.change is the seconds one weather takes to become the next: 1 to half the shortest stage ({shortest / 2} here; got {tostring(
					weather.change
				)})`,
			}
	end
	local total = 0
	for _, st in stages do
		total += st.seconds
	end
	return { change = change, total = total, stages = stages }, problems
end

-- WHERE THE CYCLE STANDS at `t` seconds on the shared clock:
-- -> { index (the stage it is in), from, to (the stage it is fading into: the same when it is not fading),
--      blend (0 = wholly `from` .. 1 = wholly `to`), left (seconds of this stage still to run) }
function Rules.at(spec: any, t: number): any
	local stages = spec.stages
	local at = t % spec.total
	local index = 0
	for i, st in stages do
		if at < st.seconds then
			index = i
			break
		end
		at -= st.seconds
	end
	if index == 0 then
		-- (a hair under the cycle's end, rounded onto it - or a hair under 0: the first stage's first moment)
		index, at = 1, 0
	end
	local st = stages[index]
	local left = st.seconds - at
	local nxt = stages[index % #stages + 1]
	if left >= spec.change then
		return { index = index, from = st, to = st, blend = 0, left = left }
	end
	-- (eased: a weather comes on slowly, is mostly there by the middle of the change, and settles)
	local x = 1 - left / spec.change
	return { index = index, from = st, to = nxt, blend = x * x * (3 - 2 * x), left = left }
end

-- WHAT IS IN THE AIR at that moment: how much of each ambient (0..1 of its full fall), the fog and the dimming
-- -> { fall = { [ambient]: number } ("clear" is never in it), fog, dim }
function Rules.air(state: any): any
	local fall: { [string]: number } = {}
	local a, b, k = state.from, state.to, state.blend
	if a.ambient ~= "clear" then
		fall[a.ambient] = (fall[a.ambient] or 0) + (1 - k)
	end
	if b.ambient ~= "clear" then
		fall[b.ambient] = (fall[b.ambient] or 0) + k
	end
	return { fall = fall, fog = a.fog + (b.fog - a.fog) * k, dim = a.dim + (b.dim - a.dim) * k }
end

-- WHAT THE WORLD'S OWN AIR AND LIGHT BECOME under that weather. `base` = what the world's lighting set
-- ({ density, haze: its Atmosphere's; brightness: Lighting's }); a weather only ever closes the air in and takes
-- light, from those values: with fog 0 and dim 0 the world looks as its lighting made it.
Rules.FOG_DENSITY = 0.6 -- fog 1 takes the Atmosphere's density this share of the way from the world's own to 1
Rules.FOG_HAZE = 4 -- ... and adds this much haze (Roblox's Haze runs 0..10)
function Rules.look(air: any, base: any): any
	return {
		density = base.density + (1 - base.density) * Rules.FOG_DENSITY * air.fog,
		haze = math.min(10, base.haze + Rules.FOG_HAZE * air.fog),
		brightness = base.brightness * (1 - air.dim),
	}
end

-- what a lighting key (the world's lighting, or its time of day at this moment) gives the weather to start from;
-- `own` = what Lighting held before any weather, for what the key does not say
function Rules.base(key: any, own: any): any
	local a = if type(key) == "table" and type(key.atmosphere) == "table" then key.atmosphere else nil
	return {
		density = if a and type(a.density) == "number" then a.density else own.density,
		haze = if a and type(a.haze) == "number" then a.haze else own.haze,
		brightness = if type(key) == "table" and type(key.brightness) == "number"
			then key.brightness
			else own.brightness,
	}
end

-- does the cycle ever close the air in
function Rules.fogs(spec: any): boolean
	for _, st in spec.stages do
		if st.fog > 0 then
			return true
		end
	end
	return false
end

-- every ambient a cycle ever shows (the client makes one emitter each, once)
function Rules.kinds(spec: any): { string }
	local seen, out = {}, {}
	for _, st in spec.stages do
		if st.ambient ~= "clear" and not seen[st.ambient] then
			seen[st.ambient] = true
			table.insert(out, st.ambient)
		end
	end
	table.sort(out)
	return out
end

return Rules

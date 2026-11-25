-- worldweather.spec.luau (kit) — WEATHER THAT CHANGES (src/kit/WeatherRules.luau; the owner's method list, "Dynamic
-- weather systems": the kit had one weather a world, for ever). What a blueprint may say, where the cycle stands at
-- any second of the shared clock, what is in the air then, what the compiler writes and what the lock asks.
-- Not claimed here: what it looks like. The client script that plays it (src/kit/client/Ambient.client.luau) runs
-- only in Roblox.
local frk = require("../frk")
local test, check = frk.test, frk.check

local serde = require("@lune/serde")

local LaneLocks = require("../../lib/lanelocks")
local Rules = require("../../../src/kit/WeatherRules")
local World = require("../../lib/world")

local function near(a: number, b: number): boolean
	return math.abs(a - b) < 1e-6
end

local function cycle(): any
	return {
		cycle = {
			{ ambient = "clear", minutes = 10 },
			{ ambient = "rain", minutes = 6, fog = 0.5, dim = 0.25 },
			{ ambient = "snow", minutes = 4, fog = 0.2 },
		},
		change = 40,
	}
end

local function compile(more: any): (any, { string })
	local bp: any = {
		name = "T",
		scale = "r6",
		lighting = "noon",
		palette = { stone = { material = "Concrete", color = { 96, 98, 104 } } },
		build = { { floor = { name = "Ground", center = { 0, 0, 0 }, size = { 120, 120 }, mat = "stone" } } },
	}
	for k, v in more do
		bp[k] = v
	end
	if more.lighting == false then
		bp.lighting = nil
	end
	local model, _, issues = World.compile(bp)
	local errors = {}
	for _, i in issues do
		if i.severity == "error" then
			table.insert(errors, i.message)
		end
	end
	local env = nil
	local function walk(node: any)
		local a = node.Properties and node.Properties.Attributes and node.Properties.Attributes.Attributes
		if a and a.KitEnvironment then
			env = serde.decode("json", a.KitEnvironment.String)
		end
		for _, c in node.Children or {} do
			walk(c)
		end
	end
	if model then
		walk(model)
	end
	return env, errors
end

return function()
	test.suite("Weather that changes over time", function()
		test.case("a cycle is read: each stage's seconds, fog and dim, the change, the whole length", function()
			local spec, problems = Rules.read(cycle())
			check.equal(#problems, 0)
			check.equal(#spec.stages, 3)
			check.equal(spec.total, 20 * 60)
			check.equal(spec.change, 40)
			check.equal(spec.stages[2].ambient, "rain")
			check.equal(spec.stages[2].seconds, 360)
			check.equal(spec.stages[2].fog, 0.5)
			check.equal(spec.stages[1].fog, 0)
			check.equal(spec.stages[1].dim, 0)
			-- no "ambient" on a stage is clear air; no "change" is the kit's
			local plain = Rules.read({ cycle = { { minutes = 5 }, { ambient = "ash", minutes = 5 } } })
			check.equal(plain.stages[1].ambient, "clear")
			check.equal(plain.change, Rules.CHANGE)
		end)

		test.case("what is wrong with a cycle is said, and nothing is carried", function()
			local function wrong(weather: any, text: string)
				local spec, problems = Rules.read(weather)
				check.equal(spec, nil)
				check.truthy(#problems >= 1)
				check.truthy(string.find(table.concat(problems, " | "), text, 1, true), table.concat(problems, " | "))
			end
			wrong(true, '"weather" is {')
			wrong({}, '"weather" is {')
			wrong({ cycle = { { ambient = "hail", minutes = 5 }, { minutes = 5 } } }, "cycle[1].ambient")
			wrong({ cycle = { { ambient = "rain" }, { minutes = 5 } } }, "cycle[1].minutes")
			wrong({ cycle = { { ambient = "rain", minutes = 0.1 }, { minutes = 5 } } }, "cycle[1].minutes")
			wrong({ cycle = { { ambient = "rain", minutes = 500 }, { minutes = 5 } } }, "cycle[1].minutes")
			wrong({ cycle = { { minutes = 5 }, { ambient = "rain", minutes = 5, fog = 1.5 } } }, "cycle[2].fog")
			wrong({ cycle = { { minutes = 5 }, { ambient = "rain", minutes = 5, dim = 0.9 } } }, "cycle[2].dim")
			wrong({ cycle = { { minutes = 5 }, "rain" } }, "cycle[2] is")
			-- a typo is said, not read as "no fog"
			wrong({ cycle = { { minutes = 5 }, { ambient = "rain", minutes = 5, fogg = 0.5 } } }, "cycle[2].fogg")
			wrong({ cycle = { { minutes = 5 }, { ambient = "rain", minutes = 5 } }, chnage = 40 }, "weather.chnage")
			-- a cycle is a list, in its author's order
			wrong({ cycle = { a = { minutes = 5 }, b = { ambient = "rain", minutes = 5 } } }, "cycle is a list")
			-- one stage changes nothing
			wrong({ cycle = { { ambient = "rain", minutes = 5 } } }, "two stages or more")
			wrong({ cycle = {} }, "two stages or more")
			-- two stages in a row that are the same weather (the last and the first are in a row)
			wrong({ cycle = { { ambient = "rain", minutes = 5 }, { ambient = "rain", minutes = 9 } } }, "same weather")
			wrong({
				cycle = {
					{ ambient = "rain", minutes = 5 },
					{ ambient = "snow", minutes = 5 },
					{ ambient = "rain", minutes = 7 },
				},
			}, "cycle[3] and the stage after it")
			-- ... the same thing falling harder is another weather
			local harder = Rules.read({
				cycle = { { ambient = "rain", minutes = 5 }, { ambient = "rain", minutes = 5, fog = 0.6 } },
			})
			check.truthy(harder ~= nil)
			-- the change fits in half the shortest stage: a stage is wholly itself for a while
			wrong({ cycle = { { minutes = 1 }, { ambient = "rain", minutes = 5 } }, change = 31 }, "weather.change")
			check.truthy(
				Rules.read({ cycle = { { minutes = 1 }, { ambient = "rain", minutes = 5 } }, change = 30 }) ~= nil
			)
			wrong({ cycle = { { minutes = 1 }, { ambient = "rain", minutes = 5 } }, change = 0 }, "weather.change")
			wrong({ cycle = { { minutes = 1 }, { ambient = "rain", minutes = 5 } }, change = "slow" }, "weather.change")
			-- a stage shorter than twice the kit's own change, with none said: said too
			wrong({ cycle = { { minutes = 0.5 }, { ambient = "rain", minutes = 5 } } }, "weather.change")
		end)

		test.case("where the cycle stands: wholly one weather, then fading into the next over the change", function()
			local spec = Rules.read(cycle())
			local a = Rules.at(spec, 0)
			check.equal(a.index, 1)
			check.equal(a.blend, 0)
			check.equal(a.from.ambient, "clear")
			check.equal(a.to.ambient, "clear")
			check.equal(a.left, 600)
			-- the fade starts 40 s before the stage ends
			check.equal(Rules.at(spec, 559).blend, 0)
			check.equal(Rules.at(spec, 560).blend, 0)
			local mid = Rules.at(spec, 580)
			check.equal(mid.index, 1)
			check.equal(mid.to.ambient, "rain")
			check.truthy(near(mid.blend, 0.5))
			check.truthy(Rules.at(spec, 570).blend < 0.25) -- (eased: slow to come on)
			check.truthy(Rules.at(spec, 590).blend > 0.75)
			-- ... and never runs back
			local last = 0
			for t = 560, 600, 0.5 do
				local b = Rules.at(spec, t - 1e-9).blend
				check.truthy(b >= last)
				last = b
			end
			check.truthy(last > 0.999)
			-- the next stage starts wholly itself
			local b = Rules.at(spec, 600)
			check.equal(b.index, 2)
			check.equal(b.blend, 0)
			check.equal(b.from.ambient, "rain")
			-- the last stage fades into the first
			local c = Rules.at(spec, 1200 - 20)
			check.equal(c.index, 3)
			check.equal(c.to.ambient, "clear")
			check.truthy(near(c.blend, 0.5))
		end)

		test.case("the cycle comes round: any second and the same second a whole cycle on are the same", function()
			local spec = Rules.read(cycle())
			-- (the server's clock is seconds since 1970: about 1.8 thousand million)
			for _, t0 in { 0, 123.25, 579, 600, 1199.5, 1763200000.5, -30 } do
				local a, b = Rules.at(spec, t0), Rules.at(spec, t0 + spec.total * 7)
				check.equal(a.index, b.index)
				check.truthy(math.abs(a.blend - b.blend) < 1e-4)
				check.truthy(a.index >= 1 and a.index <= 3)
				check.truthy(a.blend >= 0 and a.blend <= 1)
				check.truthy(a.left > 0 and a.left <= a.from.seconds)
			end
		end)

		test.case("what is in the air never jumps: across every second of a cycle, stage ends too", function()
			local spec = Rules.read(cycle())
			local before = Rules.air(Rules.at(spec, -0.25))
			local most = 0
			for t = 0, spec.total, 0.25 do
				local air = Rules.air(Rules.at(spec, t))
				for _, kind in { "rain", "snow" } do
					most = math.max(most, math.abs((air.fall[kind] or 0) - (before.fall[kind] or 0)))
				end
				most = math.max(most, math.abs(air.fog - before.fog), math.abs(air.dim - before.dim))
				check.equal(air.fall.clear, nil) -- (clear air is nothing falling)
				before = air
			end
			-- a quarter second moves nothing by more than a hundredth (the steepest of the eased fade: 1.5 / 40 a second)
			check.truthy(most > 0)
			check.truthy(most <= 1.5 / 40 * 0.25 + 1e-6)
		end)

		test.case("the air between two weathers: one going, one coming, fog and dim between the two", function()
			local spec = Rules.read(cycle())
			-- wholly rain
			local rain = Rules.air(Rules.at(spec, 700))
			check.equal(rain.fall.rain, 1)
			check.equal(rain.fall.snow, nil)
			check.equal(rain.fog, 0.5)
			check.equal(rain.dim, 0.25)
			-- rain into snow, halfway
			local half = Rules.air(Rules.at(spec, 960 - 20))
			check.truthy(near(half.fall.rain, 0.5))
			check.truthy(near(half.fall.snow, 0.5))
			check.truthy(near(half.fog, 0.35))
			check.truthy(near(half.dim, 0.125))
			-- clear into rain: only the rain, coming
			local coming = Rules.air(Rules.at(spec, 580))
			check.truthy(near(coming.fall.rain, 0.5))
			check.equal(coming.fall.snow, nil)
			-- the same thing falling harder: it keeps falling whole through the change
			local harder = Rules.read({
				cycle = { { ambient = "rain", minutes = 5 }, { ambient = "rain", minutes = 5, fog = 0.6 } },
				change = 60,
			})
			local through = Rules.air(Rules.at(harder, 300 - 30))
			check.truthy(near(through.fall.rain, 1))
			check.truthy(near(through.fog, 0.3))
		end)

		test.case("a weather only closes the air in and takes light, from what the world's lighting set", function()
			local base = { density = 0.3, haze = 1, brightness = 2.5 }
			local same = Rules.look({ fall = {}, fog = 0, dim = 0 }, base)
			check.equal(same.density, 0.3)
			check.equal(same.haze, 1)
			check.equal(same.brightness, 2.5)
			local last = same
			for fog = 0.1, 1, 0.1 do
				local look = Rules.look({ fall = {}, fog = fog, dim = fog * 0.6 }, base)
				check.truthy(look.density > last.density and look.density <= 1)
				check.truthy(look.haze > last.haze and look.haze <= 10)
				check.truthy(look.brightness < last.brightness and look.brightness > 0)
				last = look
			end
			-- a world already thick with haze stays inside Roblox's ranges
			local thick = Rules.look({ fall = {}, fog = 1, dim = 0.6 }, { density = 0.9, haze = 9, brightness = 3 })
			check.truthy(thick.density <= 1)
			check.equal(thick.haze, 10)
		end)

		test.case("what the weather starts from: the lighting key's own numbers, else what Lighting held", function()
			local own = { brightness = 3, density = 0.1, haze = 0.5 }
			local key = { brightness = 2, atmosphere = { density = 0.3, haze = 1, glare = 0.2 } }
			local base = Rules.base(key, own)
			check.equal(base.brightness, 2)
			check.equal(base.density, 0.3)
			check.equal(base.haze, 1)
			-- a key that says no brightness and has no atmosphere, and no key at all (no time of day)
			for _, bare in { {}, false } do
				local from = Rules.base(bare or nil, own)
				check.equal(from.brightness, 3)
				check.equal(from.density, 0.1)
				check.equal(from.haze, 0.5)
			end
			-- half of each
			local half = Rules.base({ atmosphere = { haze = 2 } }, own)
			check.equal(half.brightness, 3)
			check.equal(half.density, 0.1)
			check.equal(half.haze, 2)
			-- the key is read, never written (the time of day hands the same tables out again)
			check.equal(key.brightness, 2)
			check.equal(key.atmosphere.density, 0.3)
			check.equal(Rules.fogs(Rules.read(cycle())), true)
			check.equal(
				Rules.fogs(Rules.read({ cycle = { { minutes = 5 }, { ambient = "snow", minutes = 5, dim = 0.2 } } })),
				false
			)
		end)

		test.case("a hair under the cycle's end, or under 0, is the first stage's first moment", function()
			local spec = Rules.read(cycle())
			-- (t % total can round onto the total itself: the walk through the stages then ran off their end and
			-- answered the LAST stage whole, a tick of the wrong weather)
			for _, t in { -1e-20, spec.total * 3 - 1e-20 } do
				local s0 = Rules.at(spec, t)
				check.equal(s0.index, 1)
				check.equal(s0.blend, 0)
				check.equal(s0.left, 600)
			end
			-- stages whose seconds do not add up exactly, at the server's clock (seconds since 1970): every answer
			-- is a stage of the cycle, and the air next to a cycle's end is the first stage's
			local odd = Rules.read({
				cycle = {
					{ minutes = 7.31 },
					{ ambient = "rain", minutes = 9.77, fog = 0.5 },
					{ ambient = "snow", minutes = 2.774, fog = 0.9, dim = 0.5 },
				},
			})
			local n = math.floor(1.8e9 / odd.total)
			for k = n, n + 400 do
				for _, d in { -1e-7, 0, 1e-7 } do
					local air = Rules.air(Rules.at(odd, k * odd.total + d))
					check.truthy(air.fog < 0.01 and air.dim < 0.01 and (air.fall.snow or 0) < 0.01)
				end
			end
		end)

		test.case("one emitter for each weather the cycle ever shows; clear needs none", function()
			local spec = Rules.read({
				cycle = {
					{ minutes = 5 },
					{ ambient = "snow", minutes = 5 },
					{ minutes = 5, fog = 0.3 },
					{ ambient = "rain", minutes = 5 },
					{ ambient = "snow", minutes = 5, fog = 0.4 },
				},
			})
			local kinds = Rules.kinds(spec)
			check.equal(#kinds, 2)
			check.equal(kinds[1], "rain")
			check.equal(kinds[2], "snow")
		end)

		test.case("the compiler writes the cycle into the world, and it plays from what was written", function()
			local env, errors = compile({ weather = cycle() })
			check.equal(#errors, 0)
			check.truthy(env and env.weather)
			check.equal(env.ambient, nil)
			-- (the client reads it back out of JSON: the same answers)
			local direct = Rules.read(cycle())
			for _, t in { 0, 580, 700, 940, 1190 } do
				local a, b = Rules.air(Rules.at(env.weather, t)), Rules.air(Rules.at(direct, t))
				check.truthy(near(a.fog, b.fog))
				check.truthy(near(a.dim, b.dim))
				check.truthy(near(a.fall.rain or 0, b.fall.rain or 0))
				check.truthy(near(a.fall.snow or 0, b.fall.snow or 0))
			end
			-- "weather": false and no word at all write nothing
			local off = compile({ weather = false, ambient = "snow" })
			check.equal(off.weather, nil)
			check.equal(off.ambient, "snow")
			check.equal((compile({})).weather, nil)
		end)

		test.case("a bad cycle, or a cycle beside an ambient, is a compile error", function()
			local env, errors = compile({ weather = { cycle = { { ambient = "rain", minutes = 5 } } } })
			check.equal(#errors, 1)
			check.truthy(string.find(errors[1], "two stages or more", 1, true))
			check.equal(env and env.weather, nil)
			local _, both = compile({ weather = cycle(), ambient = "snow" })
			check.equal(#both, 1)
			check.truthy(string.find(both[1], "not both", 1, true))
			local _, word = compile({ weather = true })
			check.equal(#word, 1)
			-- a word that is no cycle is said in a world with no environment too
			local _, _, bare = World.compile({
				name = "T",
				scale = "r6",
				weather = "rain",
				palette = { stone = { material = "Concrete", color = { 96, 98, 104 } } },
				build = { { floor = { name = "Ground", center = { 0, 0, 0 }, size = { 120, 120 }, mat = "stone" } } },
			})
			local told = false
			for _, i in bare do
				told = told or (i.severity == "error" and string.find(i.message, '"weather" is {', 1, true) ~= nil)
			end
			check.truthy(told)
			-- a world with no lighting carries no environment: its weather is not dropped unsaid
			local _, _, issues = World.compile({
				name = "T",
				scale = "r6",
				weather = cycle(),
				palette = { stone = { material = "Concrete", color = { 96, 98, 104 } } },
				build = { { floor = { name = "Ground", center = { 0, 0, 0 }, size = { 120, 120 }, mat = "stone" } } },
			})
			local said = false
			for _, i in issues do
				said = said or (i.severity == "error" and string.find(i.message, 'its "lighting" too', 1, true) ~= nil)
			end
			check.truthy(said)
			-- ... with a wind and no lighting it has one, and the cycle rides in it (the weather moves three
			-- numbers from whatever the place's Lighting holds: it needs no lighting of the kit's)
			local windy, none = compile({ weather = cycle(), lighting = false, wind = { speed = { 2, 6 } } })
			check.equal(#none, 0)
			check.truthy(windy and windy.weather)
		end)

		test.case("the lock: a world with a weather says whether it ever changes", function()
			check.equal(LaneLocks.unsaidWeather({ ambient = "snow" }), true)
			check.equal(LaneLocks.unsaidWeather({ ambient = "snow", weather = false }), false)
			check.equal(LaneLocks.unsaidWeather({ weather = cycle() }), false)
			check.equal(LaneLocks.unsaidWeather({}), false) -- (no weather at all: nothing to ask)
			check.equal(LaneLocks.unsaidWeather(nil), false)
			local named = 0
			for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_weather") do
				if string.find(line, "does not say whether it ever changes", 1, true) then
					named += 1
					check.truthy(string.find(line, "SnowForEver", 1, true))
					check.truthy(string.find(line, '"weather": false', 1, true))
				end
			end
			check.equal(named, 1)
		end)
	end)
end

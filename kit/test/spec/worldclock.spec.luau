-- worldclock.spec.luau — one clock + one wind (src/kit/WorldClockRules) and how the world compiler resolves "day" /
-- "wind" (kit/lib/environment); the ambience reads both (AmbienceRules hours + wind).
local frk = require("../frk")
local test, check = frk.test, frk.check

local Ambience = require("../../../src/kit/AmbienceRules")
local Env = require("../../lib/environment")
local Rules = require("../../../src/kit/WorldClockRules")

local DAY = {
	length = 1200,
	start = 9,
	keys = {
		{ hour = 6, brightness = 1, atmosphere = { density = 0.4 } },
		{ hour = 12, brightness = 3, atmosphere = { density = 0.2 } },
		{ hour = 22, brightness = 0.5, atmosphere = { density = 0.5 } },
	},
}

local function near(a: number, b: number): boolean
	return math.abs(a - b) < 1e-9
end

return function()
	test.suite("WorldClockRules", function()
		test.case("the hour runs from the start and wraps at 24", function()
			check.equal(Rules.hourAt(DAY, 0), 9)
			check.equal(Rules.hourAt(DAY, 600), 21)
			check.equal(Rules.hourAt(DAY, 900), 3) -- (past midnight)
		end)
		test.case(
			"on a key it is that key; between keys an eased blend; round the clock the last blends into the first",
			function()
				check.equal(Rules.at(DAY, 12).brightness, 3)
				local mid = Rules.at(DAY, 9) -- (half way 6 -> 12, eased: still exactly the middle)
				check.is_true(near(mid.brightness, 2))
				check.is_true(near(mid.atmosphere.density, 0.3))
				local night = Rules.at(DAY, 2) -- (22 -> 6 wraps: 4 of 8 hours)
				check.is_true(near(night.brightness, 0.75))
				check.equal(Rules.at({ keys = {} }, 3), nil)
			end
		)
		test.case("the wind gusts between its speeds, swings a little round its direction", function()
			local w = { direction = 90, speed = { 3, 14 }, period = 40 }
			local lo, hi = math.huge, -math.huge
			for s = 0, 200, 0.5 do
				local x, z, v = Rules.wind(w, s)
				lo, hi = math.min(lo, v), math.max(hi, v)
				check.is_true(x > 0.9 and math.abs(z) < 0.25) -- (+X, within the swing)
			end
			check.is_true(lo >= 3 and hi <= 14 and hi - lo > 6)
			local x, z, v = Rules.wind(nil, 3)
			check.equal(x + z + v, 0)
		end)
		test.case("hours wrap past midnight", function()
			check.is_true(Rules.inHours({ 20, 5 }, 23))
			check.is_true(Rules.inHours({ 20, 5 }, 2))
			check.is_false(Rules.inHours({ 20, 5 }, 12))
			check.is_true(Rules.inHours(nil, 12))
		end)
	end)

	test.suite("kit world day / wind", function()
		test.case("a key names a preset: resolved, sorted, its own clockTime dropped", function()
			local env = Env.compile({
				day = { keys = { { hour = 18, preset = "golden" }, { hour = 7, preset = "noon" } } },
				wind = { direction = 300, speed = { 3, 14 } },
			})
			check.equal(env.day.keys[1].hour, 7)
			check.equal(env.day.keys[2].hour, 18)
			check.equal(env.day.keys[1].clockTime, nil)
			check.is_true(env.day.keys[2].brightness ~= nil)
			check.equal(env.wind.period, 40)
		end)
		test.case("bad days and winds are named", function()
			local _, issues = Env.compile({
				day = { keys = { { hour = 30 }, { hour = 3, preset = "disco" } } },
				wind = { speed = { 9, 2 } },
			})
			local text = ""
			for _, i in issues do
				text ..= i.path .. ": " .. i.message .. "\n"
			end
			check.is_true(string.find(text, "hour 0..24", 1, true) ~= nil)
			check.is_true(string.find(text, "unknown preset", 1, true) ~= nil)
			check.is_true(string.find(text, "wind", 1, true) ~= nil)
		end)
	end)

	test.suite("AmbienceRules time + wind", function()
		local spec = {
			beds = { open = "bed_meadow", forest = "bed_forest", water = "bed_lake", stone = "bed_castle" },
			zones = { { kind = "forest", x = 0, z = 0, r = 50 } },
		}
		test.case("a scatter rule sounds only in its hours", function()
			local rule = { kinds = { "open" }, hours = { 20, 5 } }
			local here = Ambience.presence(spec, 500, 500)
			check.equal(Ambience.chance(rule, here, 12), 0)
			check.equal(Ambience.chance(rule, here, 23), 1)
			check.equal(Ambience.chance(rule, here, nil), 1) -- (no clock: always)
		end)
		test.case("open land swells with the wind, the forest keeps its level; no wind = as authored", function()
			local still = Ambience.beds(spec, 500, 500, 0)
			local gale = Ambience.beds(spec, 500, 500, 30)
			check.is_true(near(still.bed_meadow, 0.55))
			check.equal(gale.bed_meadow, 1)
			check.equal(Ambience.beds(spec, 0, 0, 0).bed_forest, 1)
			check.equal(Ambience.beds(spec, 500, 500, nil).bed_meadow, 1)
		end)
	end)
end

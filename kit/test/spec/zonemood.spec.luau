-- zonemood.spec.luau — ZoneMood.blend (src/kit): the colour grade where the player stands is the presence-weighted
-- mood of the zone kinds round them; SampleRegion's compiled ambience carries a mood for every kind.
local frk = require("../frk")
local test, check = frk.test, frk.check

local fs = require("@lune/fs")
local serde = require("@lune/serde")

local ZoneMood = require("../../../src/kit/ZoneMood")

local MOODS = {
	open = { tint = { 255, 250, 240 }, saturation = 0.1, contrast = 0, brightness = 0 },
	forest = { tint = { 215, 245, 215 }, saturation = -0.1, contrast = 0.1, brightness = -0.1 },
}

local function near(a: number, b: number): boolean
	return math.abs(a - b) < 1e-9
end

return function()
	test.suite("ZoneMood", function()
		test.case("deep in one kind: its mood; between two: the presence-weighted middle", function()
			local f = ZoneMood.blend(MOODS, { open = 0, forest = 1, water = 0, stone = 0 })
			check.equal(f.tint[2], 245)
			check.equal(f.contrast, 0.1)
			local half = ZoneMood.blend(MOODS, { open = 0.5, forest = 0.5, water = 0, stone = 0 })
			check.equal(half.tint[1], 235)
			check.is_true(near(half.saturation, 0))
			check.is_true(near(half.brightness, -0.05))
		end)
		test.case("a kind with no mood is neutral; nothing present, or no moods at all, is neutral", function()
			local w = ZoneMood.blend(MOODS, { open = 0, forest = 0, water = 1, stone = 0 })
			check.equal(w.tint[1], 255)
			check.equal(w.saturation, 0)
			check.equal(ZoneMood.blend(MOODS, {}).saturation, 0)
			check.equal(ZoneMood.blend(nil, { open = 1 }).tint[3], 255)
			check.equal(ZoneMood.blend(MOODS, { open = 0 / 0 }).saturation, 0)
		end)
		test.case("SampleRegion's compiled ambience has a mood for every zone kind", function()
			local path = "games/SampleRegion/src/shared/SampleRegionAmbience.json"
			if not fs.isFile(path) then
				return
			end
			local spec = serde.decode("json", fs.readFile(path))
			for _, kind in ZoneMood.KINDS do
				check.not_nil(spec.moods[kind])
			end
		end)
	end)
end

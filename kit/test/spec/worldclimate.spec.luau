-- worldclimate.spec.luau (kit) — A PAINTED LAND SAYS WHAT CLIMATE PAINTED IT (kit/world/terrain.py --climate; the
-- owner's method list: "Rule-based biome distribution"). The climate's own rules are tested in Python
-- (kit/test/python/test_world_climate.py); here: what the compiler makes of a land's climate and what the build's
-- lock asks.
local frk = require("../frk")
local test, check = frk.test, frk.check

local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Environment = require("../../lib/environment")
local LaneLocks = require("../../lib/lanelocks")

local DIR = "build/scratch/climatespec"

-- a small painted land written here: 9 x 9 heights every 4 studs, two roles; with or without a climate on record
local function land(name: string, climate: any, painted: boolean?): string
	local n = 9
	local hm: any = { nx = n, nz = n, step = 4, relief = 5, seed = 1, heights = table.create(n * n, 5), options = {} }
	if painted ~= false then
		hm.roles = { "meadow", "lush" }
		hm.paint = string.rep("0", n * n - 9) .. string.rep("1", 9)
	end
	hm.climate = climate
	fs.writeDir(DIR)
	local path = `{DIR}/{name}.hm.json`
	fs.writeFile(path, serde.encode("json", hm))
	return path
end

local function world(source: string, more: any?): any
	local op: any = { center = { 0, 0, 0 }, size = { 32, 32 }, source = source, material = "Grass" }
	for k, v in more or {} do
		op[k] = v
	end
	return { name = "T", lighting = "noon", terrain = { { heightmap = op } }, build = {} }
end

return function()
	test.suite("A painted land says what climate painted it", function()
		test.case("the compiler carries whether a land's paint had a climate", function()
			local plain = land("plain", nil)
			local wet = land("wet", { wind = 270, rain = 0.6, sea = 0.8, lapse = 0.3, shade = 0.12 })
			local env, issues = Environment.compile(world(plain))
			check.equal(#issues, 0)
			check.equal(env.terrain[1].spec.climate, nil) -- (painted with none, and the op says nothing)
			check.equal(env.terrain[1].spec.source, plain)
			check.equal(Environment.compile(world(wet)).terrain[1].spec.climate, true)
			check.equal(Environment.compile(world(plain, { climate = false })).terrain[1].spec.climate, false)
			-- a land with no paint at all has no climate to say
			local bare = land("bare", nil, false)
			check.equal(Environment.compile(world(bare)).terrain[1].spec.climate, nil)
			check.equal(Environment.compile(world(bare)).terrain[1].spec.samples.splat, nil)
			check.equal(Environment.compile(world(bare, { climate = false })).terrain[1].spec.climate, nil)
			-- the op can only say "none, meant": a climate is made with the land
			for _, word in { true, "wet", { wind = 90 } } :: { any } do
				local _, said = Environment.compile(world(plain, { climate = word }))
				check.equal(#said, 1)
				check.truthy(string.find(said[1].message, "made with the land", 1, true))
			end
			fs.removeDir(DIR)
		end)

		test.case("the lock: a painted land with no climate and no word is named", function()
			local plain = land("plain", nil)
			local wet = land("wet", { wind = 270, rain = 0.6, sea = 0.8, lapse = 0.3, shade = 0.12 })
			local bare = land("bare", nil, false)
			check.equal(#LaneLocks.unsaidClimates(world(plain)), 1)
			check.equal(LaneLocks.unsaidClimates(world(plain))[1], plain)
			check.equal(#LaneLocks.unsaidClimates(world(plain, { climate = false })), 0)
			check.equal(#LaneLocks.unsaidClimates(world(wet)), 0)
			check.equal(#LaneLocks.unsaidClimates(world(bare)), 0) -- (not painted: nothing to ask)
			-- an empty table, or a climate with words missing, is no record that one painted the land
			check.equal(#LaneLocks.unsaidClimates(world(land("empty", {}))), 1)
			check.equal(#LaneLocks.unsaidClimates(world(land("half", { wind = 270, rain = 0.6 }))), 1)
			check.equal(#LaneLocks.unsaidClimates(world(land("word", "wet"))), 1)
			check.equal(#LaneLocks.unsaidClimates(world(plain, { paint = false })), 0) -- (its paint is not used)
			check.equal(#LaneLocks.unsaidClimates(world(plain, { backdrop = true })), 0) -- (far scenery is not asked)
			check.equal(#LaneLocks.unsaidClimates({ name = "T", build = {} }), 0)
			check.equal(#LaneLocks.unsaidClimates(nil), 0)
			-- a land painted by an aerial picture of the place (kit world terrain --imagery) has its answer: the
			-- painter's record of the picture and its box; a word or half a record is none
			local function seen(name: string, imagery: any): string
				local path = land(name, nil)
				local hm = serde.decode("json", fs.readFile(path))
				hm.imagery = imagery
				fs.writeFile(path, serde.encode("json", hm))
				return path
			end
			local box = { -119.6, 37.7, -119.5, 37.8 }
			local picture = seen("seen", { file = "Y.img.png", credit = "USGS", bbox = box })
			check.equal(#LaneLocks.unsaidClimates(world(picture)), 0)
			check.equal(Environment.compile(world(picture)).terrain[1].spec.climate, true)
			check.equal(#LaneLocks.unsaidClimates(world(seen("s1", "Y.img.png"))), 1)
			check.equal(#LaneLocks.unsaidClimates(world(seen("s2", { file = "Y.img.png" }))), 1)
			check.equal(#LaneLocks.unsaidClimates(world(seen("s3", { file = "Y.img.png", bbox = { 1, 2, 3 } }))), 1)
			check.equal(#LaneLocks.unsaidClimates(world(seen("s4", { bbox = box }))), 1)
			check.equal(#LaneLocks.unsaidClimates(world(seen("s5", { file = "Y", bbox = { 1, 2, "3", 4 } }))), 1)
			check.equal(#LaneLocks.unsaidClimates(world(seen("s6", { file = "", bbox = box }))), 1)
			fs.removeDir(DIR)
			local named = 0
			for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_climate") do
				if string.find(line, "do not say what climate painted them", 1, true) then
					named += 1
					check.truthy(string.find(line, "NoClimateSaid", 1, true))
					check.truthy(string.find(line, "terrain/flat.hm.json", 1, true))
					check.truthy(string.find(line, '"climate": false', 1, true))
				end
			end
			check.equal(named, 1)
		end)
	end)
end

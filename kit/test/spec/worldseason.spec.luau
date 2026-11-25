-- worldseason.spec.luau (kit) — ONE WORLD IN SEVERAL SEASONS (kit/lib/worldseason.luau; the owner's method list,
-- "Seasonal world variation": the kit had nothing). What a season may change, what is wrong with one, what the
-- world is in each, what the compiler builds and what the lock asks.
-- Not claimed here: what a season looks like. That is a built world, looked at.
local frk = require("../frk")
local test, check = frk.test, frk.check

local serde = require("@lune/serde")

local LaneLocks = require("../../lib/lanelocks")
local Season = require("../../lib/worldseason")
local World = require("../../lib/world")

local function world(): any
	return {
		name = "Vale",
		scale = "r6",
		lighting = "noon",
		palette = {
			stone = { material = "Concrete", color = { 96, 98, 104 } },
			leaf = { material = "Grass", color = { 70, 120, 50 } },
		},
		terrain = {
			{
				ground = {
					center = { 0, 0, 0 },
					size = { 256, 256 },
					material = "Grass",
					under = "Ground",
					rock = "Rock",
					patches = { { material = "LeafyGrass", above = 0.6 } },
					layers = { { material = "Mud", maxHeight = 2 } },
				},
			},
			{ block = { center = { 90, 4, 0 }, size = { 8, 8, 8 }, material = "Rock" } },
			{ water = { center = { 0, -4, 90 }, size = { 60, 8, 40 } } },
		},
		build = {
			{ floor = { name = "Square", center = { 0, 0.5, 0 }, size = { 40, 40 }, mat = "stone" } },
			{ floor = { name = "Flower beds", center = { 60, 0.5, 0 }, size = { 12, 12 }, mat = "leaf" } },
			{ spawn = { name = "Start", pos = { 0, 1, 0 } } },
		},
		seasons = {
			winter = {
				lighting = "frost",
				ambient = "snow",
				weather = false,
				terrain = { Grass = "Snow", LeafyGrass = "Snow", Mud = "Glacier", Water = "Glacier" },
				palette = { leaf = { material = "Snow", color = { 236, 240, 246 } } },
				skip = { "Flower beds" },
			},
			autumn = {
				palette = { leaf = { material = "Grass", color = { 190, 110, 40 } } },
				wind = { speed = { 4, 12 } },
			},
		},
		season = false,
	}
end

local function compile(bp: any): (any, { any }, { string })
	local model, parts, issues = World.compile(bp)
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
	return env, parts, errors
end

-- how many parts are made of the palette's entry (by its colour: winter re-makes "leaf")
local COLOURS = { leaf = 70, stone = 96 }
local function count(parts: { any }, entry: string): number
	local n = 0
	for _, p in parts do
		if p.name == "Floor" and p.color and p.color[1] == COLOURS[entry] then
			n += 1
		end
	end
	return n
end

return function()
	test.suite("One world in several seasons", function()
		test.case("the world as written is untouched; a season hands back a new one", function()
			local bp = world()
			check.equal(Season.apply(bp, false), bp)
			check.equal(Season.apply(bp, nil), bp)
			local winter = Season.apply(bp, "winter")
			check.truthy(winter ~= bp)
			-- the world itself is as it was (a second season is made from it)
			check.equal(bp.lighting, "noon")
			check.equal(bp.ambient, nil)
			check.equal(bp.palette.leaf.material, "Grass")
			check.equal(bp.terrain[1].ground.material, "Grass")
			check.equal(bp.terrain[1].ground.patches[1].material, "LeafyGrass")
			check.equal(#bp.build, 3)
		end)

		test.case("winter: its own air, the land swapped everywhere a material is named, a step left out", function()
			local winter = Season.apply(world(), "winter")
			check.equal(winter.lighting, "frost")
			check.equal(winter.ambient, "snow")
			check.equal(winter.weather, false)
			local g = winter.terrain[1].ground
			check.equal(g.material, "Snow")
			check.equal(g.under, "Ground") -- (not in the swap: as it was)
			check.equal(g.rock, "Rock")
			check.equal(g.patches[1].material, "Snow")
			check.equal(g.patches[1].above, 0.6)
			check.equal(g.layers[1].material, "Glacier")
			check.equal(g.layers[1].maxHeight, 2)
			check.equal(g.paint, nil) -- (no heightmap: no painter to tell)
			check.equal(winter.terrain[2].block.material, "Rock")
			-- the lake freezes: water made solid is a BLOCK of it (the runtime fills every "water" op with water)
			check.equal(winter.terrain[3].water, nil)
			check.equal(winter.terrain[3].block.material, "Glacier")
			check.equal(winter.terrain[3].block.size[1], 60)
			check.equal(#World.terrainField(World.inSeason(world())).water, 1)
			local frozen = world()
			frozen.season = "winter"
			check.equal(#World.terrainField(World.inSeason(frozen)).water, 0) -- (what the check walks: ice, not a lake)
			check.equal(winter.palette.leaf.material, "Snow")
			check.equal(winter.palette.stone.material, "Concrete")
			check.equal(#winter.build, 2)
			-- autumn changes other things, from the same world
			local autumn = Season.apply(world(), "autumn")
			check.equal(autumn.lighting, "noon")
			check.equal(autumn.palette.leaf.color[1], 190)
			check.equal(autumn.terrain[1].ground.material, "Grass")
			check.equal(#autumn.build, 3)
			check.equal(autumn.wind.speed[2], 12)
		end)

		test.case("a painted heightmap: every role's material is swapped, the op's own map kept", function()
			local bp = world()
			bp.terrain = {
				{
					heightmap = {
						center = { 0, 0, 0 },
						size = { 512, 512 },
						source = "terrain/Vale.hm.json",
						material = "Grass",
						paint = { dirt = "Mud", cliff = "Basalt" },
					},
				},
			}
			check.equal(#Season.problems(bp), 0) -- (LeafyGrass, Mud and Water are the painter's: the land has them)
			local g = Season.apply(bp, "winter").terrain[1].heightmap
			check.equal(g.material, "Snow")
			check.equal(g.paint.meadow, "Snow") -- (the meadow follows the op's material)
			check.equal(g.paint.lush, "Snow")
			check.equal(g.paint.dirt, "Glacier") -- (the op's own Mud, swapped)
			check.equal(g.paint.mud, "Glacier")
			check.equal(g.paint.cliff, "Basalt") -- (the op's own, not in the swap)
			check.equal(g.paint.rock, "Rock")
			check.equal(g.paint.river, "Glacier")
			check.equal(g.paint.sand, "Sand")
			-- an op that paints with layers and never asked for the painter keeps to its layers
			bp.terrain[1].heightmap.paint = nil
			bp.terrain[1].heightmap.layers = { { material = "Mud" } }
			local layered = Season.apply(bp, "winter").terrain[1].heightmap
			check.equal(layered.paint, nil)
			check.equal(layered.layers[1].material, "Glacier")
			-- (with the painter off the land is its material and its layers only: the swap names those)
			bp.terrain[1].heightmap.paint = false
			bp.seasons.winter.terrain = { Grass = "Snow", Mud = "Glacier" }
			local off = Season.apply(bp, "winter").terrain[1].heightmap
			check.equal(off.material, "Snow")
			check.equal(off.paint, false)
			-- a flat "ground" has no painter: nothing of the painter's is the land's
			local flat = world()
			flat.terrain = { { ground = { center = { 0, 0, 0 }, size = { 64, 64 }, material = "Grass" } } }
			flat.seasons = { winter = { terrain = { Mud = "Snow" } } }
			check.truthy(string.find(Season.problems(flat)[1], 'has no "Mud" to swap', 1, true))
		end)

		test.case("a real painted land, compiled in winter: no summer material is left on it", function()
			-- (the kit's own river terrain: nine painted roles - a fresh reader found it stayed green under a
			-- snow meadow, because the season looked for the painter on the wrong kind of op)
			local bp = {
				name = "Rivers",
				lighting = "noon",
				terrain = {
					{
						heightmap = {
							center = { 0, 0, 0 },
							size = { 256, 256 },
							source = "kit/selftest/world/terrain/_selftest_terrain_rivers.hm.json",
							material = "Grass",
							rock = "Rock",
						},
					},
				},
				build = {},
				seasons = {
					winter = {
						terrain = {
							Grass = "Snow",
							LeafyGrass = "Snow",
							Ground = "Snow",
							Mud = "Glacier",
							Sand = "Snow",
							Water = "Glacier",
						},
					},
				},
				season = false,
			}
			local summer, _, errors = compile(bp)
			check.equal(#errors, 0)
			local has = {}
			for _, m in summer.terrain[1].spec.samples.palette do
				has[m] = true
			end
			check.truthy(has.Grass and has.LeafyGrass and has.Ground and has.Mud) -- (it is a green land as written)
			bp.season = "winter"
			local winter, _, werrors = compile(bp)
			check.equal(#werrors, 0)
			local palette = winter.terrain[1].spec.samples.palette
			check.equal(#palette, #summer.terrain[1].spec.samples.palette)
			for _, m in palette do
				check.truthy(m == "Snow" or m == "Glacier" or m == "Rock" or m == "Slate", m)
			end
			check.equal(winter.terrain[1].spec.material, "Snow")
			-- the heights are the same land
			check.equal(winter.terrain[1].spec.samples.heights, summer.terrain[1].spec.samples.heights)
		end)

		test.case(
			"what lies under the ground, its rock, the worn trails and the skirt under buildings turn too",
			function()
				local bp = world()
				table.insert(bp.build, {
					path = {
						name = "Lane",
						points = { { -60, 0, -60 }, { 60, 0, -60 } },
						width = 6,
						mat = "stone",
						worn = "Mud",
					},
				})
				bp.contact = {}
				bp.seasons = { winter = { terrain = { Ground = "Snow", Rock = "Basalt", Mud = "Glacier" } } }
				check.equal(#Season.problems(bp), 0)
				local winter = Season.apply(bp, "winter")
				local g = winter.terrain[1].ground
				check.equal(g.under, "Snow")
				check.equal(g.rock, "Basalt")
				check.equal(g.material, "Grass")
				check.equal(winter.terrain[2].block.material, "Basalt")
				check.equal(winter.build[4].path.worn, "Glacier")
				check.equal(winter.build[4].path.width, 6)
				check.equal(winter.contact.material, "Snow") -- (a skirt that names no material is Ground)
				-- the world as written keeps its own
				check.equal(bp.build[4].path.worn, "Mud")
				check.equal(bp.contact.material, nil)
				check.equal(bp.terrain[1].ground.under, "Ground")
				-- a world whose only Ground is the skirt may swap it; with no skirt it has none
				local skirt = world()
				skirt.terrain[1].ground.under = nil
				skirt.contact = { max = 200 }
				skirt.seasons = { winter = { terrain = { Ground = "Snow" } } }
				check.equal(#Season.problems(skirt), 0)
				check.equal(Season.apply(skirt, "winter").contact.material, "Snow")
				check.equal(Season.apply(skirt, "winter").contact.max, 200)
				skirt.contact = nil
				check.equal(#Season.problems(skirt), 1)
				-- each of the three is the land's on its own: a world that has the material nowhere else may swap it
				local only = world()
				only.terrain = {
					{
						ground = {
							center = { 0, 0, 0 },
							size = { 64, 64 },
							material = "Grass",
							under = "Sandstone",
							rock = "Basalt",
						},
					},
				}
				table.insert(only.build, {
					path = {
						name = "Lane",
						points = { { -20, 0, -20 }, { 20, 0, -20 } },
						width = 6,
						mat = "stone",
						worn = "Mud",
					},
				})
				for _, from in { "Sandstone", "Basalt", "Mud" } do
					only.seasons = { winter = { terrain = { [from] = "Snow" } } }
					check.equal(#Season.problems(only), 0)
				end
				only.seasons = { winter = { terrain = { Ground = "Snow" } } }
				check.equal(#Season.problems(only), 1)
				-- ... and a skipped step is skipped after its trail is swapped (one list, both changes)
				bp.seasons.winter.skip = { "Square" }
				local both = Season.apply(bp, "winter")
				check.equal(#both.build, 3)
				check.equal(both.build[3].path.worn, "Glacier")
			end
		)

		test.case("a season's own time of day, grass and terrain colours; false for each", function()
			local bp = world()
			bp.day = { length = 600, keys = { { hour = 6, preset = "golden" }, { hour = 13, preset = "noon" } } }
			bp.decoration = true
			bp.terrainColors = { Grass = { 90, 130, 60 } }
			bp.seasons = {
				winter = {
					day = {
						length = 300,
						keys = { { hour = 9, preset = "frost" }, { hour = 15, preset = "overcast" } },
					},
					decoration = false,
					terrainColors = { Snow = { 240, 244, 250 } },
				},
				autumn = { day = false, terrainColors = false },
			}
			check.equal(#Season.problems(bp), 0)
			local winter = Season.apply(bp, "winter")
			check.equal(winter.day.length, 300)
			check.equal(winter.decoration, false) -- (false is the grass's own word: off - not "unsaid")
			check.equal(winter.terrainColors.Snow[1], 240)
			check.equal(winter.terrainColors.Grass, nil)
			local autumn = Season.apply(bp, "autumn")
			check.equal(autumn.day, nil)
			check.equal(autumn.terrainColors, nil)
			check.equal(autumn.decoration, true)
			-- compiled: the winter's day runs, the grass is turned OFF (the runtime leaves an unsaid one alone)
			bp.season = "winter"
			local env, _, errors = compile(bp)
			check.equal(#errors, 0)
			check.equal(env.day.length, 300)
			check.equal(env.decoration, false)
			-- a broken day, wind or colour in a season NOT built is said
			for _, broken in
				{
					{ day = { keys = { { hour = 30 } } } },
					{ wind = { speed = { 9, 2 } } },
					{ terrainColors = { Snoww = { 1, 2, 3 } } },
				} :: { any }
			do
				local other = world()
				other.seasons.winter = broken
				local _, _, said = compile(other)
				check.equal(#said, 1)
				check.truthy(string.find(said[1], "", 1, true))
			end
		end)

		test.case("a season says false for what the world has and it has not", function()
			local bp = world()
			bp.ambient, bp.weather = "leaves", false
			bp.wind = { speed = { 2, 6 } }
			bp.seasons.winter.ambient = false
			bp.seasons.winter.wind = false
			local winter = Season.apply(bp, "winter")
			check.equal(winter.ambient, nil)
			check.equal(winter.wind, nil)
			check.equal(winter.weather, false) -- (a weather's false is a word of its own: it stays)
		end)

		test.case("what is wrong with a season is said, for every season, built or not", function()
			local function wrong(change: (any) -> (), text: string)
				local bp = world()
				change(bp)
				local problems = Season.problems(bp)
				check.truthy(#problems >= 1)
				check.truthy(string.find(table.concat(problems, " | "), text, 1, true), table.concat(problems, " | "))
				-- ... and the world is then built as written, never half-seasoned
				check.equal(Season.apply(bp, "winter"), bp)
			end
			check.equal(#Season.problems(world()), 0)
			wrong(function(bp)
				bp.seasons.winter.lightning = "frost"
			end, "seasons.winter.lightning")
			wrong(function(bp)
				bp.seasons.autumn = {}
			end, "seasons.autumn changes nothing")
			wrong(function(bp)
				bp.seasons.winter.terrain = { Grass = "Sno" }
			end, "both are terrain materials")
			wrong(function(bp)
				bp.seasons.winter.terrain = { Grass = "Grass" }
			end, "changes nothing")
			wrong(function(bp)
				bp.seasons.winter.terrain = { Sand = "Snow" }
			end, 'has no "Sand" to swap')
			wrong(function(bp)
				bp.seasons.winter.palette = { leaves = { material = "Snow", color = { 1, 2, 3 } } }
			end, 'palette has no "leaves"')
			wrong(function(bp)
				bp.seasons.winter.skip = { "Flowerbeds" }
			end, 'no build step is named "Flowerbeds"')
			wrong(function(bp)
				bp.seasons.winter = "snowy"
			end, "seasons.winter is {")
			wrong(function(bp)
				bp.seasons.winter.palette = { leaf = "white" }
			end, "seasons.winter.palette.leaf is {")
			wrong(function(bp)
				bp.seasons.winter.palette = { leaf = {} }
			end, "seasons.winter.palette.leaf is {")
			wrong(function(bp)
				bp.season = "spring"
			end, "is none of this world's seasons (autumn, winter")
			wrong(function(bp)
				bp.seasons = {}
			end, '"seasons" is {')
			-- a season named in a world with none
			local lone = world()
			lone.seasons, lone.season = nil, "winter"
			check.truthy(string.find(Season.problems(lone)[1], 'no "seasons"', 1, true))
			lone.season = false
			check.equal(#Season.problems(lone), 0)
		end)

		test.case("the compiler builds the season the world says", function()
			local bp = world()
			local env, parts, errors = compile(bp)
			check.equal(#errors, 0)
			check.equal(env.ambient, nil)
			check.equal(env.terrain[1].spec.material, "Grass")
			check.equal(count(parts, "leaf"), 1)
			bp.season = "winter"
			local wenv, wparts, werrors = compile(bp)
			check.equal(#werrors, 0)
			check.equal(wenv.ambient, "snow")
			check.equal(wenv.terrain[1].spec.material, "Snow")
			check.equal(wenv.terrain[1].spec.layers[1].material, "Glacier")
			check.equal(count(wparts, "leaf"), 0) -- (the flower beds are left out)
			check.equal(count(wparts, "stone"), 1)
			-- the frost preset's light, not noon's
			local noon = (compile(world())).lighting
			check.truthy(wenv.lighting.brightness ~= noon.brightness or wenv.lighting.clockTime ~= noon.clockTime)
			-- the same streets and walls: every part that is in both stands where it stood
			check.equal(#wparts, #parts - 1)
		end)

		test.case("a broken season is a compile error while another season is built", function()
			local bp = world()
			bp.seasons.winter.lighting = "blizzard" -- (no such preset) - and the build is of the world as written
			local _, _, errors = compile(bp)
			check.equal(#errors, 1)
			check.truthy(string.find(errors[1], "blizzard", 1, true))
			-- a season's weather cycle is read too
			bp = world()
			bp.seasons.autumn.weather = { cycle = { { ambient = "rain", minutes = 5 } } }
			local _, _, cycleErrors = compile(bp)
			check.equal(#cycleErrors, 1)
			check.truthy(string.find(cycleErrors[1], "two stages or more", 1, true))
			-- ... and a season that ends with an ambient beside a cycle
			bp = world()
			bp.seasons.winter.weather = { cycle = { { minutes = 5 }, { ambient = "snow", minutes = 5 } } }
			local _, _, both = compile(bp)
			check.equal(#both, 1)
			check.truthy(string.find(both[1], "one of them", 1, true))
			-- what falls, and what a palette entry is made of, in a season that is not the one built
			bp = world()
			bp.seasons.winter.ambient = "blizzard"
			local _, _, falls = compile(bp)
			check.equal(#falls, 1)
			check.truthy(string.find(falls[1], "blizzard", 1, true))
			bp = world()
			bp.seasons.winter.palette = { leaf = { material = "Snw", color = { 1, 2, 3 } } }
			local _, _, made = compile(bp)
			check.equal(#made, 1)
			check.truthy(string.find(made[1], '"Snw"', 1, true))
			-- a structural fault stops the build of any season
			bp = world()
			bp.seasons.winter.skip = { "Nothing" }
			local _, _, structural = compile(bp)
			check.equal(#structural, 1)
		end)

		test.case("the lock: a world with seasons says which one it is built in", function()
			local bp = world()
			check.equal(LaneLocks.unsaidSeason(bp), false) -- ("season": false is a word)
			bp.season = nil
			check.equal(LaneLocks.unsaidSeason(bp), true)
			bp.season = "winter"
			check.equal(LaneLocks.unsaidSeason(bp), false)
			check.equal(LaneLocks.unsaidSeason({ name = "X" }), false)
			local named1 = 0
			for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_season") do
				if string.find(line, "does not say which one it is built in", 1, true) then
					named1 += 1
					check.truthy(string.find(line, "NoSeasonSaid", 1, true))
					check.truthy(string.find(line, "(winter)", 1, true))
				end
			end
			check.equal(named1, 1)
			-- (through the lock itself: the fixture's winter brings snow and says nothing of whether it changes)
			local asked = 0
			for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_season") do
				if string.find(line, "does not say whether it ever changes", 1, true) then
					asked += 1
					check.truthy(string.find(line, "WinterSnow", 1, true))
					check.truthy(string.find(line, '"ambient": "snow"', 1, true))
					check.truthy(string.find(line, "in its winter", 1, true))
				end
			end
			check.equal(asked, 1)
			-- the weather lock asks of the world in the season it is built in: a winter that brings its own snow
			local snowy = world()
			snowy.season = "winter"
			snowy.seasons.winter.weather = nil
			check.equal(LaneLocks.unsaidWeather(Season.apply(snowy, snowy.season)), true)
			check.equal(LaneLocks.unsaidWeather(snowy), false) -- (as written it has no weather at all)
			-- asked of every season, built or not (a winter's snow is found while the summer is built)
			snowy.season = false
			local found = LaneLocks.unsaidWeatherIn(snowy)
			check.equal(found.where, "in its winter")
			check.equal(found.ambient, "snow")
			snowy.seasons.winter.weather = false
			check.equal(LaneLocks.unsaidWeatherIn(snowy), nil)
			snowy.ambient = "leaves"
			check.equal(LaneLocks.unsaidWeatherIn(snowy).where, "as written")
		end)
	end)
end

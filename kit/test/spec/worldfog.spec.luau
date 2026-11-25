-- worldfog.spec.luau (kit) — FOG THAT LIES LOW (kit/lib/worldfog.luau, a "fog" step; the owner's method list:
-- "Layered fog"). Held here, on land whose height is known at every point: the fog is a blanket `depth` thick under its
-- top, every place under the whole blanket has every sheet (straight down they add up to "thick") - a deep pit beside
-- it changes nothing; a cell takes a sheet where any of its land lies under it, and never one over land wholly above
-- it; over water the sheets lie over the surface, never under it; one cell onto the bank; in a bowl, filled to its
-- floor + depth, never over the land round it, across a wide basin, never along the land's edge; the sheet limit is
-- an error, never a cut; a sheet is cut at Roblox's widest part; the mist in the blanket, the same for the same seed;
-- the words; the step in a world (never walked, touched, hit or snowed on; the far scenery takes none); the lock.
-- Not claimed here: how the fog looks. That is a built world, looked at.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Fog = require("../../lib/worldfog")
local LaneLocks = require("../../lib/lanelocks")
local World = require("../../lib/world")

-- a valley along x: the land rises 0.2 a stud from its floor (y -10 at x 0) each way
local function valley(x: number, _z: number): number?
	return -10 + 0.2 * math.abs(x)
end
local BOUNDS = { -100, -40, 100, 40 }
local function dry(_x: number, _z: number): number?
	return nil
end

-- the sheets over (x, z), lowest first
local function over(sheets: { any }, x: number, z: number): { any }
	local out = {}
	for _, s in sheets do
		if math.abs(x - s.pos[1]) <= s.size[1] / 2 and math.abs(z - s.pos[3]) <= s.size[3] / 2 then
			table.insert(out, s)
		end
	end
	table.sort(out, function(a, b)
		return a.pos[2] < b.pos[2]
	end)
	return out
end

local function near(a: number, b: number, e: number?): boolean
	return math.abs(a - b) <= (e or 1e-6)
end

local function opacity(list: { any }): number
	local seen = 1
	for _, s in list do
		seen *= s.transparency
	end
	return 1 - seen
end

return function()
	test.suite("Fog that lies low", function()
		test.case("under a fog line: a blanket under its top, sheets only where land lies under them", function()
			local sheets, mist, rec, problems =
				Fog.lay({ over = "low", below = 0, depth = 8, layers = 4, thick = 0.6, cell = 4 }, valley, BOUNDS, dry)
			check.equal(#problems, 0, table.concat(problems, " | "))
			check.equal(#mist, 0)
			-- four levels in the blanket: 0 - 8 * (i - 0.5) / 4
			local ys = {}
			for _, s in over(sheets, 2, 0) do
				table.insert(ys, s.pos[2])
			end
			check.equal(#ys, 4)
			check.truthy(near(ys[1], -7) and near(ys[2], -5) and near(ys[3], -3) and near(ys[4], -1))
			check.truthy(near(opacity(over(sheets, 2, 0)), 0.6, 1e-9)) -- (straight down: "thick")
			for _, s in sheets do
				check.truthy(s.pos[2] < 0)
				-- its outermost cell has land under it at its inner edge, the next cell out has none
				local edge = math.max(math.abs(s.pos[1] - s.size[1] / 2), math.abs(s.pos[1] + s.size[1] / 2))
				check.truthy((valley(edge - 4, 0) :: number) < s.pos[2], `sheet at y {s.pos[2]} out to {edge}`)
				check.truthy((valley(edge, 0) :: number) >= s.pos[2], `sheet at y {s.pos[2]} out to {edge}`)
			end
			-- land at y -0.8 (x 46) has the top sheet over its lower side; land over the top has none
			check.equal(#over(sheets, 46, 0), 1)
			check.equal(#over(sheets, 60, 0), 0)
			check.truthy(rec.fogged > 0 and rec.fogged < rec.cells)
			-- with no "depth" the blanket is no thicker than the air over its lowest land: flat land 5 under the line
			-- has both its sheets
			local function plain(_x: number, _z: number): number?
				return 0
			end
			check.equal(
				#over(
					Fog.lay({ over = "low", below = 5, layers = 2, cell = 4 }, plain, { -20, -20, 20, 20 }, dry),
					0,
					0
				),
				2
			)
			-- the valley runs along z: each level is ONE strip, joined into one rectangle
			check.equal(#sheets, 4)
		end)

		test.case("a deep pit beside it does not thin the fog over the rest", function()
			-- flat land at y 5, a 12 x 12 pit to y -40 in it; fog under y 10, 4 thick
			local function pitted(x: number, z: number): number?
				return if math.abs(x) < 6 and math.abs(z) < 6 then -40 else 5
			end
			local sheets = Fog.lay(
				{ over = "low", below = 10, depth = 4, layers = 4, cell = 4 },
				pitted,
				{ -40, -40, 40, 40 },
				dry
			)
			check.equal(#over(sheets, 30, 30), 4) -- (the flat: every sheet)
			check.equal(#over(sheets, 0, 0), 4) -- (the pit: the same blanket, not more)
			check.truthy(near(opacity(over(sheets, 30, 30)), 0.6, 1e-9))
			for _, s in sheets do
				check.truthy(s.pos[2] > 5 and s.pos[2] < 10) -- (in the blanket over the flat, never down the pit)
			end
		end)

		test.case("over water: over the surface (never under it), one cell onto the bank, nowhere else", function()
			-- flat land at y 0, a pool in x 0..20 whose surface is y 1, its bed at y -4
			local function flat(x: number, _z: number): number?
				return if x >= 0 and x <= 20 then -4 else 0
			end
			local function pool(x: number, _z: number): number?
				return if x >= 0 and x <= 20 then 1 else nil
			end
			local sheets, mist, rec = Fog.lay(
				{ over = "water", depth = 5, cell = 4, layers = 3, mist = 4 },
				flat,
				{ -40, -8, 40, 8 },
				pool
			)
			check.truthy(#sheets > 0)
			for _, s in sheets do
				check.truthy(s.pos[2] > 1 + 0.05 and s.pos[2] < 6) -- (over the surface 1, under 1 + depth 5)
				check.truthy(s.pos[1] - s.size[1] / 2 >= -4 - 1e-6) -- (one 4-stud cell onto the bank, no more)
				check.truthy(s.pos[1] + s.size[1] / 2 <= 24 + 1e-6)
			end
			check.equal(#over(sheets, 10, 0), 3)
			check.truthy(near(opacity(over(sheets, 10, 0)), 0.6, 1e-9))
			check.truthy(#over(sheets, -2, 0) > 0) -- (the bank's cell)
			check.equal(#over(sheets, -10, 0), 0)
			check.equal(#over(sheets, 30, 0), 0)
			for _, m in mist do
				check.truthy(m.pos[2] > 1) -- (the mist on the water, never in it)
			end
			check.truthy(rec.fogged > 0)
			-- two pools of one surface, one shallow and one deep: the same blanket over both
			local function two(x: number, _z: number): number?
				return if x >= -30 and x <= -10 then -1 elseif x >= 10 and x <= 30 then -30 else 3
			end
			local function both(x: number, _z: number): number?
				return if (x >= -30 and x <= -10) or (x >= 10 and x <= 30) then 0 else nil
			end
			local s2 = Fog.lay({ over = "water", depth = 4, cell = 4, layers = 4 }, two, { -40, -8, 40, 8 }, both)
			check.equal(#over(s2, -20, 0), 4)
			check.equal(#over(s2, 20, 0), 4)
			-- a fog LINE over the pool: its blanket runs under the surface, its sheets do not
			local line = Fog.lay(
				{ over = "low", below = 3, depth = 8, cell = 4, layers = 4 },
				flat,
				{ -40, -8, 40, 8 },
				pool
			)
			check.equal(#over(line, 10, 0), 1)
			for _, s in over(line, 10, 0) do
				check.truthy(s.pos[2] > 1)
			end
			check.equal(#over(line, -20, 0), 1) -- (the land at 0 lies under the sheet at 2 only: 2, 0, -2, -4)
			-- no water: nothing
			local none = Fog.lay({ over = "water", cell = 4 }, flat, { -40, -8, 40, 8 }, dry)
			check.equal(#none, 0)
		end)

		test.case(
			"in a hollow: to its floor + depth, never over the land round it, never on the land's edge",
			function()
				-- a plain at y 0 with a bowl 8 deep, 30 across, round (40, 0)
				local function bowl(x: number, z: number): number?
					local d = math.sqrt((x - 40) ^ 2 + z ^ 2)
					return if d < 15 then -8 * (1 - (d / 15) ^ 2) else 0
				end
				local B = { -60, -80, 100, 80 }
				local sheets, _, rec = Fog.lay({ over = "hollows", depth = 7, cell = 2, layers = 3 }, bowl, B, dry)
				check.truthy(#sheets > 0)
				for _, s in sheets do
					check.truthy(s.pos[2] < -8 + 7) -- (the floor + depth)
					check.truthy(math.abs(s.pos[1] - 40) <= 15 and math.abs(s.pos[3]) <= 15) -- (in the bowl)
				end
				check.equal(#over(sheets, 41, 1), 3)
				check.equal(#over(sheets, 0, 0), 0)
				check.truthy(#over(sheets, 51, 1) > 0) -- (its sides, no hollow by themselves, fogged from it)
				check.truthy(rec.fogged < 200, `{rec.fogged} cells fogged`) -- (the bowl's ~177 cells and its edge's)
				-- a thin fill (depth 2) stays 2 over the floor
				local thin = Fog.lay({ over = "hollows", depth = 2, cell = 2, layers = 2 }, bowl, B, dry)
				check.truthy(#thin > 0)
				for _, s in thin do
					check.truthy(s.pos[2] < -6)
				end
				-- a shallow dish (2 deep) is no hollow at deep 4; it is at deep 1, and never fogged over the plain
				local function dish(x: number, z: number): number?
					local d = math.sqrt((x - 40) ^ 2 + z ^ 2)
					return if d < 15 then -2 * (1 - (d / 15) ^ 2) else 0
				end
				check.equal(#Fog.lay({ over = "hollows", cell = 2 }, dish, B, dry), 0)
				local said = Fog.lay({ over = "hollows", cell = 2, deep = 1 }, dish, B, dry)
				check.truthy(#said > 0)
				for _, s in said do
					check.truthy(s.pos[2] < 0)
				end
				-- a plain slope with no hollow: its low edge is no hollow (the round runs off the land)
				local function slope(x: number, _z: number): number?
					return 0.2 * x
				end
				check.equal(#Fog.lay({ over = "hollows", cell = 4 }, slope, { -200, -100, 200, 100 }, dry), 0)
				-- a wide flat basin (300 across, 10 deep) is filled across, not only round its rim
				local function basin(x: number, z: number): number?
					return if math.abs(x) < 150 and math.abs(z) < 150 then -10 else 0
				end
				local wide = Fog.lay({ over = "hollows", cell = 8, depth = 6 }, basin, { -300, -300, 300, 300 }, dry)
				check.truthy(#over(wide, 0, 0) > 0)
				check.truthy(#over(wide, 140, 0) > 0)
				check.equal(#over(wide, 200, 0), 0)
			end
		)

		test.case("the mist in the blanket, the same for the same seed", function()
			local function lay(seed: number)
				local _, m = Fog.lay({ over = "low", below = 0, cell = 4, mist = 12, seed = seed }, valley, BOUNDS, dry)
				return m
			end
			local a, b, c = lay(5), lay(5), lay(6)
			check.equal(#a, 12)
			local same, differ = true, false
			for i, m in a do
				check.truthy((valley(m.pos[1], m.pos[3]) :: number) < 0.5) -- (over fogged land)
				check.truthy(m.pos[2] < 0 and m.pos[2] >= (valley(m.pos[1], m.pos[3]) :: number) - 0.5)
				same = same and m.pos[1] == b[i].pos[1] and m.pos[3] == b[i].pos[3]
				differ = differ or m.pos[1] ~= c[i].pos[1] or m.pos[3] ~= c[i].pos[3]
			end
			check.truthy(same)
			check.truthy(differ)
		end)

		test.case("limits: too many sheets is an error, never a cut; a sheet is cut at Roblox's widest part", function()
			-- a checkerboard of 4-stud pits: every cell its own sheet
			local function checker(x: number, z: number): number?
				return if (math.floor(x / 4) + math.floor(z / 4)) % 2 == 0 then -5 else 5
			end
			local sheets, _, _, problems = Fog.lay(
				{ over = "low", below = 0, cell = 4, layers = 2 },
				checker,
				{ -200, -200, 200, 200 },
				dry
			)
			check.equal(#sheets, 0)
			check.truthy(string.find(table.concat(problems, " "), "nothing is cut by itself", 1, true))
			-- flat land 3000 wide: its sheets cut at 2048
			local function plain(_x: number, _z: number): number?
				return 0
			end
			local wide = Fog.lay(
				{ over = "low", below = 5, depth = 5, cell = 16, layers = 1 },
				plain,
				{ -1500, -50, 1500, 50 },
				dry
			)
			check.truthy(#wide >= 2)
			local across = 0
			for _, s in wide do
				check.truthy(s.size[1] <= 2048 and s.size[3] <= 2048)
				across += s.size[1] * s.size[3]
			end
			check.truthy(near(across, 3000 * 100, 1e-3))
		end)

		test.case("the words", function()
			local function says(spec: any, text: string)
				local all = table.concat(Fog.problems(spec), " | ")
				check.truthy(string.find(all, text, 1, true), text .. " <- " .. all)
			end
			check.equal(#Fog.problems({ over = "low", below = 3 }), 0)
			check.equal(#Fog.problems({ over = "water" }), 0)
			check.equal(#Fog.problems({ over = "hollows", deep = 2, reach = 30, depth = 3, mist = 5 }), 0)
			check.equal(#Fog.problems({ over = "water", center = { 0, 0, 0 }, area = { 10, 20 }, seed = 4 }), 0)
			says({ over = "low" }, 'needs "below"')
			says({ over = "sky" }, '"low", "water" or "hollows"')
			says({ over = "water", layers = 0 }, "fog.layers is a whole number 1 to 12")
			says({ over = "water", layers = 2.5 }, "fog.layers is a whole number 1 to 12")
			says({ over = "water", thick = 1 }, "fog.thick is 0.05 to 0.95")
			says({ over = "water", cell = 1 }, "fog.cell is 2 to 64")
			says({ over = "water", mist = 41 }, "fog.mist is a whole number 0 to 40")
			says({ over = "water", height = 4 }, "fog.height: not a fog word")
			says({ over = "water", area = { 10, 10 } }, "needs its center")
			says({ over = "water", area = { 10, 10 }, center = { 0, 0 } }, "needs its center")
			says({ over = "water", area = { -10, 10 }, center = { 0, 0, 0 } }, "both over 0")
			says({ over = "water", center = { 0, 0, 0 } }, 'goes with "area"')
			says({ over = "water", seed = "abc" }, "fog.seed is a number")
			says({ over = "low", below = 0 / 0 }, 'needs "below"')
			local sheets, _, _, problems = Fog.lay(
				{ over = "low", below = 0, cell = 2 },
				valley,
				{ -1000, -1000, 1000, 1000 },
				dry
			)
			check.equal(#sheets, 0)
			check.truthy(string.find(table.concat(problems, " "), "cells is over", 1, true))
		end)

		test.case("in a world: never walked, touched, hit or snowed on; the far scenery takes none", function()
			local function world(fog: any, more: any?): any
				local bp = {
					name = "T",
					palette = {
						fog = { material = "SmoothPlastic", color = { 200, 206, 214 } },
						wood = { material = "Wood", color = { 110, 84, 60 } },
					},
					terrain = {
						{
							ground = {
								center = { 0, 0, 0 },
								size = { 120, 120 },
								material = "Snow",
								noise = { amplitude = 10, scale = 60, seed = 2 },
							},
						},
					},
					build = { { fog = fog } },
				}
				for k, v in more or {} do
					bp[k] = v
				end
				local _, parts, issues, extras = World.compile(bp, { meshes = {} })
				local errors = {}
				for _, i in issues do
					if i.severity == "error" then
						table.insert(errors, i.message)
					end
				end
				return parts, errors, extras
			end
			local parts, errors, extras = world(
				{ over = "low", below = 0, mat = "fog", mist = 3 },
				{ cover = { snow = { depth = 0.5 } } }
			)
			check.equal(#errors, 0, table.concat(errors, " | "))
			local sheets, puffs = 0, 0
			for _, p in parts do
				if p.fog then
					check.equal(p.collide, false)
					check.equal(p.query, false)
					check.equal(p.castShadow, false)
					check.equal(p.touch, false)
					if p.name == "Fog" then
						sheets += 1
						check.truthy(p.attributes.KitAudioPass)
					else
						puffs += 1
					end
				end
			end
			check.truthy(sheets > 0)
			check.equal(puffs, 3)
			check.equal(extras.fog[1].sheets, sheets)
			-- one dense sheet (1 layer, 0.9 thick: 0.1 see-through) is still no roof for snow to lie on
			local dense = world(
				{ over = "low", below = 0, mat = "fog", layers = 1, thick = 0.9 },
				{ cover = { snow = { depth = 0.5 } } }
			)
			local fogs, onFog = 0, 0
			for _, f in dense do
				if f.fog and f.name == "Fog" then
					fogs += 1
					for _, p in dense do
						if
							p.cover
							and math.abs(p.pos[1] - f.pos[1]) < f.size[1] / 2
							and math.abs(p.pos[3] - f.pos[3]) < f.size[3] / 2
							and math.abs((p.pos[2] - p.size[2] / 2) - (f.pos[2] + f.size[2] / 2)) <= 0.05
						then
							onFog += 1
						end
					end
				end
			end
			check.truthy(fogs > 0)
			check.equal(onFog, 0)
			-- far scenery (a backdrop ground 1,800 across round the play land) takes none, nor widens where it lies
			local ringed = world({ over = "low", below = 0, mat = "fog" }, {
				terrain = {
					{
						ground = {
							center = { 0, 0, 0 },
							size = { 120, 120 },
							material = "Grass",
							noise = { amplitude = 10, scale = 60, seed = 2 },
						},
					},
					{ ground = { center = { 0, -30, 0 }, size = { 1800, 1800 }, material = "Rock", backdrop = true } },
				},
			})
			local inPlay, outside = 0, 0
			for _, p in ringed do
				if p.fog and p.name == "Fog" then
					if math.abs(p.pos[1]) <= 60 + 1e-6 and math.abs(p.pos[3]) <= 60 + 1e-6 then
						inPlay += 1
					else
						outside += 1
					end
				end
			end
			check.truthy(inPlay > 0)
			check.equal(outside, 0)
			-- the step's own errors; a "fog" at the blueprint's top is only false
			local _, e2 = world({ over = "low", below = 0 })
			check.truthy(string.find(table.concat(e2, " "), 'fog needs "mat"', 1, true))
			local _, e3 = world({ over = "low", mat = "fog" })
			check.truthy(string.find(table.concat(e3, " "), 'needs "below"', 1, true))
			local _, e4 = world({ over = "low", below = 0, mat = "fog" }, { fog = { over = "low" } })
			check.truthy(string.find(table.concat(e4, " "), '"fog" is only false', 1, true))
			local _, e5 = world({ over = "low", below = 0, mat = "fog" }, { fog = false })
			check.equal(#e5, 0)
		end)

		test.case("the lock: a world whose weather closes the air in says where the fog lies low", function()
			local LAND = { { ground = { center = { 0, 0, 0 }, size = { 100, 100 }, material = "Grass" } } }
			local THICK = { cycle = { { ambient = "rain", minutes = 5, fog = 0.7 } } }
			local THIN = { cycle = { { ambient = "rain", minutes = 5, fog = 0.3 } } }
			check.equal(LaneLocks.unsaidFog({ terrain = LAND, weather = THICK, build = {} }), "as written")
			check.equal(LaneLocks.unsaidFog({ terrain = LAND, weather = THICK, build = {}, fog = false }), nil)
			check.equal(
				LaneLocks.unsaidFog({ terrain = LAND, weather = THICK, build = { { fog = { over = "water" } } } }),
				nil
			)
			check.equal(LaneLocks.unsaidFog({ terrain = LAND, weather = THIN, build = {} }), nil)
			check.equal(LaneLocks.unsaidFog({ terrain = {}, weather = THICK, build = {} }), nil) -- (no land)
			check.equal(
				LaneLocks.unsaidFog({
					terrain = LAND,
					weather = THIN,
					build = {},
					seasons = { autumn = { weather = THICK } },
				}),
				"in its autumn"
			)
			-- a season that leaves the fog step out while its weather is thick is named
			check.equal(
				LaneLocks.unsaidFog({
					terrain = LAND,
					weather = THICK,
					build = { { fog = { name = "LowFog", over = "low", below = 0 } } },
					seasons = { autumn = { skip = { "LowFog" } } },
				}),
				"in its autumn"
			)
			local named = 0
			for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_fog") do
				if string.find(line, "does not say where the fog lies low", 1, true) then
					named += 1
					check.truthy(string.find(line, "FogUnsaid", 1, true))
				end
			end
			check.equal(named, 1)
		end)
	end)
end

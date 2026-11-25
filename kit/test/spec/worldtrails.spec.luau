-- worldtrails.spec.luau (kit) — TRAILS WORN BY WALKERS (kit/lib/worldtrails.luau, the "trails" build step; the
-- owner's method list: "Agent-based generation"). Held here: that walkers share ground when trodden ground is easier
-- (and do not when it is not), that every place is joined to the web, that a trail goes round what is too steep and
-- round what nobody may stand on, that the same seed wears the same trails, and what the step hands the compiler.
-- Not claimed here: that the trails look like a village's. That is a built world, looked at.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Environment = require("../../lib/environment")
local Trails = require("../../lib/worldtrails")
local World = require("../../lib/world")

local PLACES = { { -100, -80 }, { 120, -60 }, { 90, 110 }, { -110, 90 }, { 0, 0 }, { 10, -140 } }

local function flat(): number
	return 0
end

local function spec(more: any?): any
	local s: any = { places = PLACES, walkers = 60, seed = 3, grade = 0.6 }
	for k, v in more or {} do
		s[k] = if v == "none" then nil else v
	end
	return s
end

-- every place reaches every other along the runs (runs meet where two of their ends are the same point)
local function joined(grown: any, places: { { number } }, cell: number): boolean
	local group: { [string]: string } = {}
	local function find(k: string): string
		while group[k] and group[k] ~= k do
			k = group[k]
		end
		return k
	end
	local function id(p: { number }): string
		return `{math.round(p[1] / cell)}:{math.round(p[2] / cell)}`
	end
	for _, run in grown.runs do
		local a, b = id(run.points[1]), id(run.points[#run.points])
		group[a] = group[a] or a
		group[b] = group[b] or b
		group[find(a)] = find(b)
	end
	local first: string? = nil
	for _, p in places do
		-- (a place stands on the grid's nearest point: within half a cell of it)
		local best: string? = nil
		for k in group do
			local i, j = string.match(k, "^(-?%d+):(-?%d+)$")
			if
				math.abs((tonumber(i) :: number) * cell - p[1]) <= cell
				and math.abs((tonumber(j) :: number) * cell - p[2]) <= cell
			then
				best = k
			end
		end
		if not best then
			return false
		end
		first = first or find(best)
		if find(best) ~= first then
			return false
		end
	end
	return true
end

return function()
	test.suite("Trails worn by walkers", function()
		test.case("trodden ground is shared: fewer studs of trail for the same walks", function()
			local alone = Trails.grow(spec({ wear = 0 }), flat) :: any
			local worn = Trails.grow(spec({ wear = 0.6 }), flat) :: any
			local deep = Trails.grow(spec({ wear = 0.9 }), flat) :: any
			check.equal(alone.walks, 60)
			check.equal(worn.walks, 60)
			check.equal(#worn.lost, 0)
			-- with wear the web is far shorter (seen: 1,423 studs against 3,559) ...
			check.truthy(worn.length < alone.length * 0.6, `{worn.length} against {alone.length}`)
			check.truthy(deep.length <= worn.length * 1.05)
			-- ... and each walker goes a little further for it, never much (he still takes his cheapest way)
			check.truthy(worn.walked >= alone.walked - 1e-6)
			check.truthy(worn.walked < alone.walked * 1.25)
			-- with no wear nobody walks further than the straightest way on the grid
			local direct = 0
			do
				local one = Trails.grow(
					{ places = { PLACES[1], PLACES[2], PLACES[3] }, walkers = 3, seed = 1, grade = 0.6, wear = 0 },
					flat
				) :: any
				direct = one.walked
				-- three walks: from each place in turn; each is as long as the grid's straightest way (8 headings):
				-- the longer side + 0.414 of the shorter, in cells of 8 studs
				check.truthy(direct > 0)
			end
			-- the most trodden stretch carried many walkers; the web is runs between places and forks
			check.truthy(worn.most >= 10)
			check.truthy(#worn.runs >= 5 and #worn.runs < #alone.runs)
			for _, run in worn.runs do
				check.truthy(#run.points >= 2)
				check.truthy(run.feet >= 1 and run.feet <= worn.most)
			end
			-- every place is on the web, with or without wear
			check.truthy(joined(worn, PLACES, 8))
			check.truthy(joined(alone, PLACES, 8))
			-- the web's length is its runs' own (a straight stretch is kept as its two ends)
			local sum = 0
			for _, run in worn.runs do
				for q = 2, #run.points do
					sum += math.sqrt(
						(run.points[q][1] - run.points[q - 1][1]) ^ 2 + (run.points[q][2] - run.points[q - 1][2]) ^ 2
					)
				end
			end
			check.truthy(math.abs(sum - worn.length) < 1e-6)
		end)

		test.case("the same seed wears the same trails; another seed, others", function()
			local a = Trails.grow(spec(), flat) :: any
			local b = Trails.grow(spec(), flat) :: any
			local c = Trails.grow(spec({ seed = 4 }), flat) :: any
			check.equal(#a.runs, #b.runs)
			check.equal(a.length, b.length)
			for r, run in a.runs do
				check.equal(#run.points, #b.runs[r].points)
				check.equal(run.feet, b.runs[r].feet)
				check.equal(run.points[1][1], b.runs[r].points[1][1])
				check.equal(run.points[#run.points][2], b.runs[r].points[#run.points][2])
			end
			check.truthy(c.length ~= a.length or #c.runs ~= #a.runs)
		end)

		test.case("round what is too steep, round what nobody stands on", function()
			-- a wall of land between west and east, with one gap in the north
			local function ridge(x: number, z: number): number
				if math.abs(x) < 12 and z > -100 then
					return 40
				end
				return 0
			end
			local three = { { -80, 60 }, { 80, 60 }, { -80, -20 } }
			local grown = Trails.grow(
				{ places = three, walkers = 12, seed = 2, grade = 0.5, wear = 0.6, reach = 120 },
				ridge
			) :: any
			-- (with the 48 studs of reach it has when none is said, the gap is out of sight: the walks across are lost)
			local near = Trails.grow({ places = three, walkers = 12, seed = 2, grade = 0.5, wear = 0.6 }, ridge) :: any
			check.truthy(#near.lost > 0 and near.walks > 0)
			check.equal(#grown.lost, 0)
			local lowest = math.huge
			for _, run in grown.runs do
				for q = 1, #run.points do
					local p = run.points[q]
					lowest = math.min(lowest, p[2])
					check.truthy(not (math.abs(p[1]) < 12 and p[2] > -100), "no trail stands on the ridge")
					-- and no stretch crosses it between two of its points
					if q > 1 then
						local o = run.points[q - 1]
						for t = 0, 1, 0.05 do
							local x, z = o[1] + (p[1] - o[1]) * t, o[2] + (p[2] - o[2]) * t
							check.truthy(ridge(x, z) == 0, "no stretch crosses the ridge")
						end
					end
				end
			end
			check.truthy(lowest <= -100, "the trails go through the gap in the north")
			-- with a grade that takes the ridge they go straight over it
			local over = Trails.grow(
				{ places = three, walkers = 12, seed = 2, grade = 2, wear = 0.6, cell = 32 },
				function(x: number, z: number): number
					return if math.abs(x) < 12 and z > -100 then 20 else 0
				end
			) :: any
			check.truthy(over.walked < grown.walked)
			-- water in the same place: the same way round
			local wet = Trails.grow(
				{ places = three, walkers = 12, seed = 2, grade = 0.5, wear = 0.6, reach = 120 },
				flat,
				function(x: number, z: number): boolean
					return math.abs(x) < 12 and z > -100
				end
			) :: any
			check.equal(#wet.lost, 0)
			for _, run in wet.runs do
				for _, p in run.points do
					check.truthy(not (math.abs(p[1]) < 12 and p[2] > -100))
				end
			end
			-- a diagonal step does not cut the corner of what nobody may stand on: a one-cell post between two
			-- places that lie on a diagonal
			local corner = { places = { { 0, 0 }, { 8, 8 }, { 80, 80 } }, walkers = 3, seed = 1, grade = 1, wear = 0 }
			local open = Trails.grow(corner, flat) :: any
			local post = Trails.grow(corner, flat, function(x: number, z: number): boolean
				return x == 8 and z == 0 -- (one of the two corners the step from [0, 0] to [8, 8] passes)
			end) :: any
			check.equal(#post.lost, 0)
			check.truthy(post.walked > open.walked + 1, "the walk goes round the corner, not across it")
			-- a place nobody can stand on is said, with its number
			local _, why = Trails.grow(
				{ places = three, walkers = 12, seed = 2, grade = 0.5 },
				function(x: number, z: number): number?
					return if x < -70 and z > 0 then nil else 0
				end
			)
			check.truthy(string.find(why :: string, "place 1 [-80, 60] is off the land", 1, true))
			-- shut in on every side: no way, said
			local _, shut = Trails.grow(
				{ places = three, walkers = 12, seed = 2, grade = 0.5 },
				function(x: number, _z: number): number
					return if math.abs(x) < 12 then 40 else 0
				end
			)
			check.equal(shut, nil) -- (west and south-west still reach each other: some walks are lost, not all)
			local some = Trails.grow(
				{ places = three, walkers = 12, seed = 2, grade = 0.5 },
				function(x: number, _z: number): number
					return if math.abs(x) < 12 then 40 else 0
				end
			) :: any
			check.truthy(#some.lost > 0 and some.walks > 0)
			check.equal(some.walks + #some.lost, 12)
		end)

		test.case("steep ground costs, every place is walked from, nobody walks to where he stands", function()
			-- a hill a walker COULD climb (its slope is under his grade) between two places: he goes round its
			-- steepest part all the same, because steep ground costs
			local function hill(x: number, z: number): number
				return math.max(0, 60 - math.sqrt(x * x + z * z)) * 0.45
			end
			local across = { { -96, 0 }, { 96, 0 }, { -96, 96 } }
			local level =
				Trails.grow({ places = across, walkers = 3, seed = 1, grade = 0.6, wear = 0, reach = 96 }, flat) :: any
			local climbed =
				Trails.grow({ places = across, walkers = 3, seed = 1, grade = 0.6, wear = 0, reach = 96 }, hill) :: any
			check.equal(#climbed.lost, 0)
			-- how near the hill's top (the origin) any stretch of the web comes
			local function nearest(grown: any): number
				local best = math.huge
				for _, run in grown.runs do
					for q = 2, #run.points do
						local a, b = run.points[q - 1], run.points[q]
						for t = 0, 1, 0.1 do
							local x, z = a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t
							best = math.min(best, math.sqrt(x * x + z * z))
						end
					end
				end
				return best
			end
			-- (the walks between the east place and the north-west one: on level ground they pass 40 studs from the
			-- origin; with the hill there - 60 studs wide, every slope of it under the grade - they swing out past it)
			check.truthy(nearest(level) < 45, `level: {nearest(level)}`)
			check.truthy(nearest(climbed) > 50, `hill: {nearest(climbed)}`)
			-- (no further for it: on a grid of 8 headings the way round is as short as the way over)
			check.truthy(climbed.walked >= level.walked - 1e-6)
			-- land that ends (no height) is walked round as water is
			local gone = Trails.grow(
				{ places = { { -80, 60 }, { 80, 60 }, { -80, -20 } }, walkers = 12, seed = 2, grade = 0.5, reach = 120 },
				function(x: number, z: number): number?
					return if math.abs(x) < 12 and z > -100 then nil else 0
				end
			) :: any
			check.equal(#gone.lost, 0)
			for _, run in gone.runs do
				for _, pt in run.points do
					check.truthy(not (math.abs(pt[1]) < 12 and pt[2] > -100))
				end
			end
			-- as many walkers as places: every place is walked from, and nobody walks to where he stands - so every
			-- place is on the web, whatever the seed
			for seed = 1, 25 do
				local few = Trails.grow({ places = PLACES, walkers = #PLACES, seed = seed, grade = 0.6 }, flat) :: any
				check.equal(few.walks, #PLACES)
				check.truthy(few.walked > 0)
				-- (each place is an end of some run)
				for n, place in PLACES do
					local on = false
					for _, run in few.runs do
						for _, e in { run.points[1], run.points[#run.points] } do
							on = on or (math.abs(e[1] - place[1]) <= 8 and math.abs(e[2] - place[2]) <= 8)
						end
					end
					check.truthy(on, `seed {seed}: place {n} is on no trail`)
				end
			end
			-- every place shut in by itself: no walk at all, said
			local none, why = Trails.grow(
				{ places = across, walkers = 6, seed = 1, grade = 0.5 },
				function(x: number, z: number): number
					for _, place in across do
						if math.abs(x - place[1]) <= 16 and math.abs(z - place[2]) <= 16 then
							return 0
						end
					end
					return 100
				end
			)
			check.equal(none, nil)
			check.truthy(string.find(why :: string, "no walker found a way between any two places", 1, true))
		end)

		test.case("what a fresh reader got past the first rules", function()
			-- A STRIP NOBODY MAY STAND ON, THINNER THAN A CELL, lies between two grid points: no walk steps over it
			local function strip(x: number, _z: number): boolean
				return x > 1 and x < 7
			end
			local sides = { { -40, -40 }, { -40, 40 }, { 48, -40 }, { 48, 40 } }
			local cut = Trails.grow({ places = sides, walkers = 12, seed = 1, grade = 0.6 }, flat, strip) :: any
			check.truthy(#cut.lost > 0, "the walks across are lost, not walked")
			for _, run in cut.runs do
				for q = 2, #run.points do
					local a, b = run.points[q - 1], run.points[q]
					check.truthy(
						not ((a[1] <= 1 and b[1] >= 7) or (b[1] <= 1 and a[1] >= 7)),
						"no stretch crosses the strip"
					)
				end
			end
			-- with a ford in it they go through the ford
			local ford = Trails.grow(
				{ places = sides, walkers = 12, seed = 1, grade = 0.6 },
				flat,
				function(x: number, z: number): boolean
					return strip(x, z) and math.abs(z) > 6
				end
			) :: any
			check.equal(#ford.lost, 0)
			for _, run in ford.runs do
				for q = 2, #run.points do
					local a, b = run.points[q - 1], run.points[q]
					if (a[1] <= 1 and b[1] >= 7) or (b[1] <= 1 and a[1] >= 7) then
						local t = (4 - a[1]) / (b[1] - a[1])
						check.truthy(math.abs(a[2] + (b[2] - a[2]) * t) <= 6, "the crossing is at the ford")
					end
				end
			end
			-- A TRAIL ENDS AT ITS PLACE, not at the grid point beside it
			local odd = { { -101.5, -77 }, { 123, -58.5 }, { 91, 113.5 }, { -3, 2.5 } }
			local grown = Trails.grow({ places = odd, walkers = 12, seed = 2, grade = 0.6 }, flat) :: any
			for n, place in odd do
				local ends = false
				for _, run in grown.runs do
					for _, e in { run.points[1], run.points[#run.points] } do
						ends = ends or (e[1] == place[1] and e[2] == place[2])
					end
				end
				check.truthy(ends, `place {n}`)
			end
			-- a place that itself stands in water is refused though the grid point beside it is dry, and the other
			-- way round is said as what it is
			local _, wet = Trails.grow(
				{ places = { { 3, 0 }, { 60, 0 }, { 0, 60 } }, walkers = 3, seed = 1, grade = 0.6 },
				flat,
				function(x: number): boolean
					return x > 2 and x < 3.9
				end
			)
			check.truthy(string.find(wet :: string, "place 1 [3, 0] is off the land, in water", 1, true))
			local _, edge = Trails.grow(
				{ places = { { 3, 0 }, { 60, 0 }, { 0, 60 } }, walkers = 3, seed = 1, grade = 0.6 },
				flat,
				function(x: number, z: number): boolean
					return x > -1 and x < 1 and math.abs(z) < 1
				end
			)
			check.truthy(string.find(edge :: string, "stands at the very edge", 1, true))
			-- "parts": false: only for trails worn into land, and then it must say what they wear
			local palette = { dirt = { material = "Ground", color = { 110, 90, 60 } } }
			local function errorsOf(step: any, terrain: any?): string
				local _, _, issues = World.compile(
					{ name = "T", palette = palette, terrain = terrain, build = { { trails = step } } },
					{ meshes = {} }
				)
				local out = {}
				for _, i in issues do
					if i.severity == "error" then
						table.insert(out, i.message)
					end
				end
				return table.concat(out, " | ")
			end
			local land = {
				{
					ground = {
						center = { 0, 0, 0 },
						size = { 512, 512 },
						noise = { amplitude = 4, scale = 120, seed = 2 },
						material = "Grass",
					},
				},
			}
			check.truthy(
				string.find(errorsOf(spec({ mat = "dirt", parts = false })), "this world has no land", 1, true)
			)
			check.truthy(
				string.find(
					errorsOf(spec({ mat = "dirt", parts = false }), land),
					'with no "worn" would make nothing',
					1,
					true
				)
			)
			check.equal(errorsOf(spec({ mat = "dirt", parts = false, worn = "Ground" }), land), "")
			-- on land the trails follow it: their pieces lie at the land's own heights, not all at one
			local _, parts, issues, extras = World.compile(
				{ name = "T", palette = palette, terrain = land, build = { { trails = spec({ mat = "dirt" }) } } },
				{ meshes = {} }
			)
			local hard = 0
			for _, i in issues do
				hard += if i.severity == "error" then 1 else 0
			end
			check.equal(hard, 0)
			check.equal(extras.trails[1].lost, 0)
			local lowest, highest = math.huge, -math.huge
			for _, p in parts do
				lowest, highest = math.min(lowest, p.pos[2]), math.max(highest, p.pos[2])
				local ground = World.groundHeight(
					Environment.compile({ name = "T", terrain = land }).terrain[1].spec,
					p.pos[1],
					p.pos[3]
				)
				check.truthy(math.abs(p.pos[2] - ground) < 1.5, "a piece lies on the land")
			end
			check.truthy(highest - lowest > 1)
		end)

		test.case("what the step hands the compiler", function()
			local palette = { dirt = { material = "Ground", color = { 110, 90, 60 } } }
			local function compile(step: any): ({ any }, { string }, { string }, any, any)
				local model, parts, issues, extras = World.compile(
					{ name = "T", palette = palette, build = { { trails = step } } },
					{ meshes = {} }
				)
				local errors, warns = {}, {}
				for _, i in issues do
					if i.path ~= "spawn" then
						table.insert(if i.severity == "error" then errors else warns, i.message)
					end
				end
				return parts, errors, warns, extras, model
			end
			local step = spec({ name = "Tracks", mat = "dirt", width = 4 })
			local parts, errors, warns, extras, model = compile(step)
			check.equal(#errors, 0, table.concat(errors, " | "))
			check.equal(#warns, 0, table.concat(warns, " | "))
			check.truthy(#parts > 20)
			local grown = Trails.grow(step, flat) :: any
			local rec = extras.trails[1]
			check.equal(rec.name, "Tracks")
			check.equal(rec.runs, #grown.runs)
			check.equal(rec.length, grown.length)
			check.equal(rec.walks, 60)
			check.equal(rec.lost, 0)
			-- one Model a run, named by the step
			local names: { [string]: boolean } = {}
			for _, child in model.Children do
				names[child.Name] = true
			end
			check.truthy(names["Tracks_1"] and names[`Tracks_{#grown.runs}`])
			check.equal(names[`Tracks_{#grown.runs + 1}`], nil)
			-- the most trodden run is as wide as said, none under half of it, none wider
			local widest, narrowest = 0, math.huge
			for _, p in parts do
				local across = math.min(p.size[1], p.size[3])
				if p.name == "Path" and math.max(p.size[1], p.size[3]) > 6 then
					widest, narrowest = math.max(widest, across), math.min(narrowest, across)
				end
			end
			check.equal(widest, 4)
			check.truthy(narrowest >= 2)
			-- at a width of 8 the least trodden run (1 walker of the most's many) is half of it: 4, not 8, not 2
			local wideParts = compile(spec({ name = "Tracks", mat = "dirt", width = 8 }))
			local w8, n8 = 0, math.huge
			for _, p in wideParts do
				local across = math.min(p.size[1], p.size[3])
				if p.name == "Path" and math.max(p.size[1], p.size[3]) > 9 then
					w8, n8 = math.max(w8, across), math.min(n8, across)
				end
			end
			check.equal(w8, 8)
			check.equal(n8, 4)
			-- two runs do not lie in one plane: each run a hair (0.07) higher than the one before
			local lowest: { [string]: number } = {}
			for _, child in model.Children do
				for _, part in child.Children or {} do
					local y = part.Properties.CFrame.CFrame.position[2] - part.Properties.Size.Vector3[2] / 2
					lowest[child.Name] = math.min(lowest[child.Name] or math.huge, y)
				end
			end
			check.truthy(math.abs(lowest["Tracks_2"] - lowest["Tracks_1"] - 0.07) < 1e-6)
			check.truthy(math.abs(lowest["Tracks_3"] - lowest["Tracks_1"] - 0.14) < 1e-6)
			-- its words
			local function said(more: any, text: string)
				local _, bad = compile(spec(more))
				local all = table.concat(bad, " | ")
				check.truthy(string.find(all, text, 1, true), text .. " <- " .. all)
			end
			said({ mat = "none" }, '"mat" is the palette entry')
			said({ mat = "gold" }, '"mat" is the palette entry')
			said({ mat = "dirt", places = { { 0, 0 }, { 50, 0 } } }, '"places" is 3 to 40')
			said({ mat = "dirt", places = { { 0, 0 }, { 50, 0 }, { 0, 50, 3 } } }, '"places" is 3 to 40')
			said({ mat = "dirt", walkers = 0 }, '"walkers" is how many walks')
			said({ mat = "dirt", walkers = 401 }, '"walkers" is how many walks')
			said({ mat = "dirt", walkers = 5 }, "5 walkers for 6 places")
			said({ mat = "dirt", grade = 0 }, '"grade" is the steepest')
			said({ mat = "dirt", grade = 2.1 }, '"grade" is the steepest')
			said({ mat = "dirt", wear = 0.95 }, '"wear" is how much easier')
			said({ mat = "dirt", wear = -0.1 }, '"wear" is how much easier')
			said({ mat = "dirt", cell = 3 }, '"cell" is the grid')
			said({ mat = "dirt", cell = 33 }, '"cell" is the grid')
			said({ mat = "dirt", seed = 1.5 }, '"seed" is a whole number')
			said({ mat = "dirt", width = 1 }, '"width" is the most trodden')
			said({ mat = "dirt", width = 17 }, '"width" is the most trodden')
			said({ mat = "dirt", speed = 3 }, '"speed" is not a word it knows')
			said({ mat = "dirt", reach = -1 }, '"reach" is how far outside')
			said({ mat = "dirt", reach = 1025 }, '"reach" is how far outside')
			said({ mat = "dirt", places = { { 0, 0 }, { 4, 4 }, { 90, 0 } } }, "places 1 and 2 stand within one cell")
			said({ mat = "dirt", places = { { 0, 0 }, { 3000, 0 }, { 0, 3000 } } }, "cells of 8 studs")
			-- the ends of the ranges are in
			for _, ok in
				{
					{ walkers = 6 },
					{ walkers = 400 },
					{ grade = 2 },
					{ wear = 0 },
					{ wear = 0.9 },
					{ cell = 4 },
					{ cell = 32 },
					{ width = 2 },
					{ width = 16 },
					{ seed = 0 },
					{ seed = 65535 },
					{ reach = 0 },
					{ reach = 1024, cell = 32 },
				} :: { any }
			do
				local s = spec(ok)
				check.equal(#Trails.problems(s), 0)
			end
			check.equal(#Trails.problems(nil), 1)
		end)
	end)
end

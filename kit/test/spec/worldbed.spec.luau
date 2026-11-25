-- worldbed.spec.luau (kit) — A ROAD ON THE LAND WITH A BED (a path's "bed"; the owner's finding W-R07: "grounded roads
-- are slabs, no grade or cut and fill"). The bed's own rule is held in worldroadbed.spec.luau. Here the compiler is
-- held to what it does with one: the road's pieces lie on the bed and never climb over its grade, the land the game
-- gets carries the bed, the heights kit world check walks are the land WITH it, and what is built after the road
-- stands on the graded land.
-- Not claimed here: how a cutting looks, or that the game's voxels are what the heights say (that is the engine).
local frk = require("../frk")
local test, check = frk.test, frk.check

local RoadBed = require("../../../src/kit/RoadBed")
local World = require("../../lib/world")
local serde = require("@lune/serde")

local PALETTE = { stone = { material = "Cobblestone", color = { 120, 118, 112 } } }
local LINE = { { -220, -40 }, { 0, 20 }, { 220, -30 } }

local function blueprint(bed: any, more: any?): any
	local road: any = {
		name = "Road",
		mat = "stone",
		width = 8,
		ground = true,
		curve = false,
		route = false,
		bed = bed,
		points = LINE,
	}
	for k, v in more or {} do
		road[k] = if v == "none" then nil else v
	end
	return {
		name = "T",
		palette = PALETTE,
		lighting = "noon",
		terrain = {
			{
				ground = {
					center = { 0, 0, 0 },
					size = { 512, 512 },
					noise = { amplitude = 40, scale = 90, seed = 3, octaves = 3 },
					material = "Grass",
				},
			},
		},
		build = {
			{ path = road },
			{ part = { name = "Hut", mat = "stone", size = { 6, 6, 6 }, pos = { 0, 0, 20 }, ground = true } },
		},
	}
end

local function compile(bp: any): (any, { any }, { string }, { string }, any)
	local model, parts, issues, extras = World.compile(bp, { meshes = {} })
	local errors, warns = {}, {}
	for _, i in issues do
		if i.path ~= "spawn" then
			table.insert(if i.severity == "error" then errors else warns, i.message)
		end
	end
	return model, parts, errors, warns, extras
end

-- the road's own pieces in the order they lie: their middles
local function pieces(parts: { any }): { any }
	local out = {}
	for _, p in parts do
		if p.name == "Road" or p.name == "Pass" then
			table.insert(out, p)
		end
	end
	table.sort(out, function(a, b)
		return a.pos[1] < b.pos[1]
	end)
	return out
end

-- the steepest climb between two neighbouring pieces' middles (rise over run)
local function steepest(list: { any }): number
	local worst = 0
	for k = 2, #list do
		local a, b = list[k - 1], list[k]
		local run = math.sqrt((b.pos[1] - a.pos[1]) ^ 2 + (b.pos[3] - a.pos[3]) ^ 2)
		if run > 1 then
			worst = math.max(worst, math.abs(b.pos[2] - a.pos[2]) / run)
		end
	end
	return worst
end

return function()
	test.suite("A road on the land with a bed", function()
		test.case("the road holds its grade; the land is cut and filled to it", function()
			-- (the plain road kept a ramp: since V3 stage E.3 a stretch steeper than 16 degrees is stone steps, and this
			-- case compares a bed's pieces with a ramp's)
			local _, plain, e0 = compile(blueprint(nil, { stairs = false }))
			check.equal(#e0, 0, table.concat(e0, " | "))
			local model, parts, errors, warns, extras = compile(blueprint({ grade = 0.08, shoulder = 12 }))
			check.equal(#errors, 0, table.concat(errors, " | "))
			-- without a bed the road follows the land, far steeper than 0.08; with one it holds it
			check.truthy(steepest(pieces(plain)) > 0.3, `plain {steepest(pieces(plain))}`)
			check.truthy(steepest(pieces(parts)) <= 0.08 + 0.01, `bedded {steepest(pieces(parts))}`)
			check.equal(#pieces(parts), #pieces(plain))
			-- what came back with the build
			check.equal(#extras.beds, 1)
			local bed = extras.beds[1]
			check.equal(bed.name, "Road")
			check.equal(bed.grade, 0.08)
			check.truthy(bed.steepest <= 0.08 + 0.003)
			check.truthy(bed.cut > 5 and bed.fill > 5)
			-- cut and fill are read at the road's edges too (the road's 8 studs and a stud of bed each side)
			local plainSpec = serde.decode(
				"json",
				(compile(blueprint(nil))).Properties.Attributes.Attributes.KitEnvironment.String
			).terrain[1].spec
			local edged = RoadBed.profile(LINE, function(x: number, z: number): number
				return World.groundHeight(plainSpec, x, z)
			end, 0.08, nil, 5) :: any
			check.truthy(
				math.abs(bed.cut - edged.cut) < 1e-6 and math.abs(bed.fill - edged.fill) < 1e-6,
				`{bed.cut} {edged.cut}`
			)
			local centred = RoadBed.profile(LINE, function(x: number, z: number): number
				return World.groundHeight(plainSpec, x, z)
			end, 0.08) :: any
			check.truthy(bed.cut + bed.fill > centred.cut + centred.fill + 0.5)
			-- (the misfit is shared: neither the start nor the end carries it all)
			check.truthy(math.abs(bed.cut - bed.fill) < bed.cut * 0.5)
			check.truthy(math.abs(bed.length - (math.sqrt(220 ^ 2 + 60 ^ 2) + math.sqrt(220 ^ 2 + 50 ^ 2))) < 1e-6)
			-- (this land is rough: the bed's sides stand as walls over a shoulder of 12, and it says so)
			check.equal(#warns, 1)
			check.truthy(string.find(warns[1], "steeper than 45 degrees", 1, true))
			-- the land the GAME gets carries the bed: the road's whole line, kept short, its numbers to a thousandth
			local env = serde.decode("json", model.Properties.Attributes.Attributes.KitEnvironment.String)
			local beds = env.terrain[1].spec.beds
			check.truthy(type(beds) == "table" and #beds == 1)
			check.equal(#RoadBed.problems(beds[1]), 0)
			check.equal(beds[1].width, 10) -- (the road's 8 and a stud of bed each side)
			check.equal(beds[1].shoulder, 12)
			check.truthy(#beds[1].points < 30, `{#beds[1].points} points`) -- (every 8 studs would be 60)
			for _, pt in beds[1].points do
				for c = 1, 3 do
					check.equal(math.round(pt[c] * 1000) / 1000, pt[c])
				end
			end
			check.equal(beds[1].points[1][1], -220)
			check.equal(beds[1].points[#beds[1].points][1], 220)
			local plainEnv =
				serde.decode("json", (compile(blueprint(nil))).Properties.Attributes.Attributes.KitEnvironment.String)
			check.equal(plainEnv.terrain[1].spec.beds, nil)
			-- the heights kit world check walks: the land WITH the bed - level across the road, the land's own far off
			local with = World.terrainField(blueprint({ grade = 0.08, shoulder = 12 }), 4, extras.bedsOf).ground[1]
			local without = World.terrainField(blueprint(nil), 4).ground[1]
			local function at(g: any, x: number, z: number): number
				return g.heights[math.floor((x - g.x0) / g.step) * g.nz + math.floor((z - g.z0) / g.step) + 1]
			end
			-- (at the road's middle point [0, 20] and 4 studs to each side across it: one level)
			check.truthy(math.abs(at(with, 0, 20) - at(with, 0, 24)) < 0.6)
			check.truthy(math.abs(at(with, 0, 20) - at(with, 0, 16)) < 0.6)
			check.truthy(math.abs(at(with, 0, 20) - at(without, 0, 20)) > 3) -- (the land was cut or filled there)
			check.equal(at(with, 0, 200), at(without, 0, 200)) -- (far from the road the land is its own)
			check.equal(at(with, -240, -200), at(without, -240, -200))
			-- without the beds handed in (kit content's record of a build) the field finds them itself: the same land
			local found = World.terrainField(blueprint({ grade = 0.08, shoulder = 12 }), 4).ground[1]
			for x = -240, 240, 16 do
				for z = -80, 80, 16 do
					check.equal(at(found, x, z), at(with, x, z))
				end
			end
			-- the road's pieces lie ON that land (their tops a slab's thickness over it)
			for _, p in pieces(parts) do
				local land = World.groundHeight(env.terrain[1].spec, p.pos[1], p.pos[3])
				check.truthy(math.abs(p.pos[2] - land) < 1.2, `piece at {p.pos[1]}: {p.pos[2]} on {land}`)
			end
			-- the blueprint itself is never written on: built twice from ONE table it is the same road, and its land
			-- says nothing of beds
			local same = blueprint({ grade = 0.08, shoulder = 12 })
			local _, first, _, _, x1 = compile(same)
			local _, second, _, _, x2 = compile(same)
			check.equal(same.terrain[1].ground.beds, nil)
			check.equal(x1.beds[1].cut, x2.beds[1].cut)
			check.equal(x1.beds[1].fill, x2.beds[1].fill)
			check.equal(#first, #second)
			for k, part in first do
				check.equal(part.pos[2], second[k].pos[2])
			end
			check.equal(at(World.terrainField(same, 4).ground[1], 0, 20), at(with, 0, 20))
			-- what is built AFTER the road stands on the graded land
			local hut, hutPlain: any = nil, nil
			for _, p in parts do
				hut = if p.name == "Hut" then p else hut
			end
			for _, p in plain do
				hutPlain = if p.name == "Hut" then p else hutPlain
			end
			check.truthy(math.abs(hut.pos[2] - hutPlain.pos[2]) > 3)
			-- (it moved by what the land under it was cut or filled)
			check.truthy(math.abs((hut.pos[2] - hutPlain.pos[2]) - (at(with, 0, 20) - at(without, 0, 20))) < 1)
		end)

		test.case("a routed road hands its own grade to its bed", function()
			local step = {
				name = "Pass",
				mat = "stone",
				width = 8,
				ground = true,
				curve = false,
				bed = true,
				route = { from = { -200, -40 }, to = { 200, -30 }, grade = 0.6 },
			}
			local bp = blueprint(nil)
			bp.build = { { path = step } }
			local _, parts, errors, _, extras = compile(bp)
			check.equal(#errors, 0, table.concat(errors, " | "))
			check.equal(#extras.beds, 1)
			check.equal(extras.beds[1].grade, 0.6)
			check.truthy(extras.beds[1].steepest <= 0.6 + 0.003)
			check.truthy(#pieces(parts) > 10)
			-- the route's own record is measured on the bed (where its pieces lie), and a bed of its own grade is held
			local held = table.clone(step)
			held.bed = { grade = 0.06, shoulder = 40 }
			bp.build = { { path = held } }
			local _, _, e2, w2, x2 = compile(bp)
			check.equal(#e2, 0, table.concat(e2, " | "))
			check.equal(x2.routes[1].bed, true)
			check.equal(x2.routes[1].steepest, x2.beds[1].steepest)
			check.truthy(x2.routes[1].steepest <= 0.06 + 0.003)
			check.equal(string.find(table.concat(w2, " | "), "laid steeper than its grade", 1, true), nil)
			-- a road whose rounded corners lay it steeper than its grade on the land says so; with a bed it lies on the
			-- bed, and does not
			local rounded = { name = "Pass", mat = "stone", width = 8, ground = true, curve = true }
			rounded.route = { from = { -200, -40 }, to = { 200, -30 }, grade = 0.5, cell = 24 }
			bp.build = { { path = rounded } }
			local _, _, _, w3 = compile(bp)
			check.truthy(string.find(table.concat(w3, " | "), "laid steeper than its grade", 1, true))
			local bedded = table.clone(rounded)
			bedded.bed = { grade = 0.5, shoulder = 40 }
			bp.build = { { path = bedded } }
			local _, _, _, w4, x4 = compile(bp)
			check.equal(string.find(table.concat(w4, " | "), "laid steeper than its grade", 1, true), nil)
			check.truthy(x4.routes[1].steepest <= 0.5 + 0.003)
		end)

		test.case("what a fresh reader got past the first rules", function()
			-- the order of the land's ops: a water op listed before the ground does not move the bed onto another op
			local wet = blueprint({ grade = 0.08 })
			table.insert(wet.terrain, 1, { water = { center = { 0, -60, 0 }, size = { 20, 4, 20 } } })
			local model, _, errors = compile(wet)
			check.equal(#errors, 0, table.concat(errors, " | "))
			local env = serde.decode("json", model.Properties.Attributes.Attributes.KitEnvironment.String)
			local carried = 0
			for _, op in env.terrain do
				if op.spec.beds then
					carried += 1
					check.equal(op.kind, "ground")
				end
			end
			check.equal(carried, 1)
			-- a shoulder said by no one is 10
			check.equal(env.terrain[2].spec.beds[1].shoulder, 10)
			-- a road over two grounds where the other stands higher: no bed (it would lie buried), said
			local two = blueprint({ grade = 0.08 })
			table.insert(two.terrain, { ground = { center = { 100, 30, 0 }, size = { 200, 200 }, material = "Grass" } })
			local _, _, buried = compile(two)
			check.truthy(string.find(table.concat(buried, " | "), "another ground stands higher", 1, true))
			-- what was built BEFORE the road and now floats or is buried: said, with the first of them
			local before = blueprint({ grade = 0.08, shoulder = 40 })
			table.insert(
				before.build,
				1,
				{ part = { name = "Shed", mat = "stone", size = { 4, 4, 4 }, pos = { 0, 0, 20 }, ground = true } }
			)
			local _, _, _, warns = compile(before)
			local all = table.concat(warns, " | ")
			check.truthy(string.find(all, "built before this road stand where its bed moved the land", 1, true), all)
			check.truthy(string.find(all, '"Shed" at [0, 20]', 1, true), all)
			-- (a part far from the road is not counted)
			local far = blueprint({ grade = 0.08, shoulder = 40 })
			table.insert(
				far.build,
				1,
				{ part = { name = "Shed", mat = "stone", size = { 4, 4, 4 }, pos = { 0, 0, 200 }, ground = true } }
			)
			local _, _, _, farWarns = compile(far)
			check.equal(string.find(table.concat(farWarns, " | "), "built before this road", 1, true), nil)
			-- a closed loop of road: one height where it began and where it ends, round the loop
			local loop = blueprint({ grade = 0.02, shoulder = 40 }, {
				points = { { -120, -120 }, { 120, -120 }, { 120, 120 }, { -120, 120 }, { -120, -120 } },
			})
			local _, _, loopErr, _, loopX = compile(loop)
			check.equal(#loopErr, 0, table.concat(loopErr, " | "))
			check.equal(loopX.beds[1].loop, true)
			local pts = loopX.bedsOf[1][1].points
			check.equal(pts[1][2], pts[#pts][2])
			-- the beds' share of the game's record of its land is held
			local keep = World.BED_CHARS
			World.BED_CHARS = 50
			local _, _, big = compile(blueprint({ grade = 0.08 }))
			World.BED_CHARS = keep
			check.truthy(string.find(table.concat(big, " | "), "characters in the game's record of its land", 1, true))
		end)

		test.case("what a bed may not say", function()
			local function said(bed: any, more: any?, text: string)
				local _, _, errors = compile(blueprint(bed, more))
				local all = table.concat(errors, " | ")
				check.truthy(string.find(all, text, 1, true), text .. " <- " .. all)
			end
			said(true, nil, 'a bed needs its "grade"') -- (typed points, no route: nothing to take a grade from)
			said({}, nil, 'a bed needs its "grade"')
			said({ grade = 0 }, nil, 'a bed needs its "grade"')
			said({ grade = 1.5 }, nil, 'a bed needs its "grade"')
			said({ grade = "steep" }, nil, 'a bed needs its "grade"')
			said("yes", nil, '"bed" is true or {')
			said({ grade = 0.1, shoulder = 1 }, nil, '"shoulder" is 2 to 64')
			said({ grade = 0.1, shoulder = 65 }, nil, '"shoulder" is 2 to 64')
			said({ grade = 0.1 }, { ground = "none" }, 'it is for a path with "ground": true')
			said({ grade = 0.1 }, { width = 63 }, "takes no bed")
			said({ grade = 0.1 }, { points = { { -220, -40 }, { 400, 0 } } }, "the road leaves the land")
			said({ grade = 0.1 }, { points = { { -400, -40 }, { 0, 0 } } }, "stands on no land")
			-- a bed deeper than its shoulder is wide has walls for sides: said (and not said when the shoulder is wide)
			local function warnsOf(bed: any): string
				local _, _, _, warns = compile(blueprint(bed, { points = { { -60, -40 }, { 60, -30 } } }))
				return table.concat(warns, " | ")
			end
			check.truthy(string.find(warnsOf({ grade = 0.05, shoulder = 2 }), "steeper than 45 degrees", 1, true))
			check.equal(string.find(warnsOf({ grade = 0.05, shoulder = 64 }), "steeper than 45 degrees", 1, true), nil)
			-- (past one and a half times the depth over the shoulder - not past the shoulder alone)
			local _, _, _, _, probe =
				compile(blueprint({ grade = 0.05, shoulder = 64 }, { points = { { -60, -40 }, { 60, -30 } } }))
			local depth = math.max(probe.beds[1].cut, probe.beds[1].fill)
			local between = math.floor(depth * 1.2 + 0.5)
			if between >= 2 and between <= 64 and between < depth * 1.5 and between > depth then
				check.truthy(
					string.find(warnsOf({ grade = 0.05, shoulder = between }), "steeper than 45 degrees", 1, true)
				)
			end
			-- "bed": false is no bed, and says nothing
			local _, _, none, _, extras = compile(blueprint(false))
			check.equal(#none, 0)
			check.equal(#extras.beds, 0)
			-- the ends of the ranges
			for _, ok in
				{ { grade = 1 }, { grade = 0.01 }, { grade = 0.1, shoulder = 2 }, { grade = 0.1, shoulder = 64 } } :: { any }
			do
				local _, _, errors = compile(blueprint(ok))
				check.equal(#errors, 0, table.concat(errors, " | "))
			end
		end)
	end)
end

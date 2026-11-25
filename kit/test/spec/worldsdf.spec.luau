-- worldsdf.spec.luau (kit) — LAND AS A SIGNED DISTANCE (src/kit/SdfRules.luau; the owner's method list: "Signed
-- distance field / SDF terrain"). The rules the game and the compiler read are held to ONE TABLE OF POINTS that the
-- walk check's own copy (kit/world/sdf.py, kit/test/python/test_world_sdf.py) is held to as well - the game and
-- the check read the same land - and to what a spec may say.
-- Not claimed here: that a cave or an arch made this way looks like rock. That is a built world, looked at.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Sdf = require("../../../src/kit/SdfRules")
local World = require("../../lib/world")

-- (the same table stands in kit/test/python/test_world_sdf.py; written by one script from one run)
local SPEC = {
	material = "Rock",
	shapes = {
		{ box = { center = { 0, 20, 0 }, size = { 80, 40, 24 }, round = 6 } },
		{ ball = { center = { 50, 30, 0 }, radius = 22 }, blend = 10 },
		{ capsule = { from = { -20, 12, -30 }, to = { 10, 16, 30 }, radius = 9 }, cut = true, blend = 4 },
		{ ball = { center = { -30, 40, 0 }, radius = 14 }, cut = true },
		{ capsule = { from = { 0, 45, 0 }, to = { 0, 70, 0 }, radius = 5 } },
	},
}
local ROWS = {
	{ -18.66, 16.92, -20.83, 8.829999999999998, -3.7394524107385942 },
	{ 19.31, 26.33, -22.1, 9.679088856877495, 25.13308656818763 },
	{ 15.89, 2.7, -3.32, -2.6999999999999993, 14.296803667371023 },
	{ -39.82, 38.19, 7.84, 1.4036545030140344, -1.3045638121409944 },
	{ -30.14, 16.07, 6.37, -5.63, 10.763711353510807 },
	{ 68.73, 41.55, -5.17, 0.6040770658746446, 63.97624989606432 },
	{ -1.59, 24.51, 23.53, 11.530000000000001, 2.812223218365629 },
	{ -27.69, 8.48, -9.58, -2.42, 7.60284612821339 },
	{ 52.94, 13.01, 4.08, -4.281362919231061, 41.07392862724592 },
	{ -33.06, 41.15, -10.49, 3.0124525029468003, -3.0124525029468003 },
	{ -37.85, 14.83, 9.02, -1.106851729203374, 13.865961314837143 },
	{ 6.31, 22.62, 4.28, -2.5104078908609786, 2.5104078908609786 },
	{ -11.21, 20.88, 1.97, -0.4559375575879656, 0.4559375575879656 },
	{ -15.71, 41.36, 1.26, 1.3599999999999994, 0.40976405080943756 },
	{ 60.02, 52.52, -10.6, 4.831153534650728, 64.11710529919745 },
	{ -39.17, 38.03, 6.17, 2.773304137013419, -2.773304137013419 },
	{ -26.76, 35.21, -23.04, 11.082906661338402, 9.754647966240206 },
	{ 35.19, 55.05, 3.65, 7.202514535433577, 43.484529581104816 },
	{ 1.79, 20.19, 24.79, 12.79, -2.142807478089088 },
	{ 24.59, 32.85, 17.0, 4.009291444060401, 16.476592443519902 },
	{ 68.36, 34.14, 8.21, -1.4662886939550042, 55.88261169219378 },
	{ -25.16, 43.53, 11.83, 5.171830646765105, -0.7397058856147538 },
	{ 53.63, 20.49, -5.71, -10.328620475710679, 46.24121005871529 },
	{ 35.24, 1.62, -1.92, -1.4478576472170825, 30.186232307789822 },
	{ -24.15, 2.09, -13.48, 2.4402902793683587, 6.390687949327905 },
	{ -29.48, 17.83, -5.45, -6.55, 8.835976002789987 },
	{ 59.57, 5.8, -2.54, 4.147208263981071, 50.69387559033003 },
	{ -20.8, 47.66, 8.74, 7.932092448731451, 0.8223884714981047 },
	{ -11.59, 29.9, -7.06, -4.835928177669666, 7.6495934139638955 },
	{ 61.1, 68.96, -17.45, 22.108889126796193, 77.0144440282447 },
	{ -21.15, 6.3, -19.79, 7.789999999999999, -0.6468354649138259 },
	{ 25.69, 18.92, -24.8, 11.05796817687888, 29.919364146657884 },
	{ 5.27, 26.59, 3.32, -5.328899250012758, 5.35759520377384 },
	{ -25.43, 40.37, 2.82, 8.617231195750648, -8.617231195750648 },
	{ 36.14, 3.89, 19.98, 7.765810606306739, 21.50167372456797 },
	{ 48.6, 62.96, 14.89, 14.194387686490842, 53.63795734217392 },
	{ -10.65, 4.05, -3.23, -1.1730170409418008, 1.2653314491471885 },
	{ -37.53, 4.85, -14.56, 3.3304340735037634, 14.794756262627995 },
	{ -25.52, 24.48, -22.37, 10.370000000000001, 5.782408802656535 },
	{ -38.37, 30.44, -3.27, 0.879657016678264, -0.879657016678264 },
	{ -41.94, 62.95, 5.7, 24.01909558930782, 12.490679492983944 },
	{ -27.17, 18.16, -7.63, -4.368313310962939, 8.205722720399358 },
	{ -18.13, 21.83, 3.68, -6.262170330195694, 6.581945040619697 },
	{ 10.92, 34.84, -20.71, 8.733964164473864, 22.83975689498862 },
	{ -32.74, 24.67, -11.76, -0.2400000000000002, 5.514458742173709 },
	{ -38.13, 28.55, 10.82, 0.3473852884475219, 3.727712768431239 },
	{ 18.39, 10.56, 2.16, -9.46362900067849, 11.386036677302581 },
	{ -41.75, 38.02, 23.93, 13.942612667351288, 12.732523262872139 },
}

local function near(a: number, b: number): boolean
	return math.abs(a - b) < 1e-9
end

return function()
	test.suite("Land as a signed distance", function()
		test.case("the same land as the walk check reads: one table of points", function()
			local inside, cut = 0, 0
			for _, r in ROWS do
				local d, c = Sdf.at(SPEC, r[1], r[2], r[3])
				check.truthy(near(d, r[4]), `{d} for {r[4]}`)
				check.truthy(near(c, r[5]), `{c} for {r[5]}`)
				inside += if r[4] < 0 then 1 else 0
				cut += if r[5] < 0 then 1 else 0
			end
			check.truthy(inside >= 10 and cut >= 5 and #ROWS - inside >= 10)
			check.equal(#Sdf.problems(SPEC), 0)
		end)

		test.case("each shape by plain geometry; joined, blended, cut", function()
			local ball = { ball = { center = { 10, 20, 30 }, radius = 5 } }
			check.truthy(near(Sdf.shape(ball, 10, 20, 30), -5) and near(Sdf.shape(ball, 13, 24, 30), 0))
			local box = { box = { center = { 0, 0, 0 }, size = { 20, 10, 8 } } }
			check.truthy(near(Sdf.shape(box, 0, 0, 0), -4) and near(Sdf.shape(box, 13, 9, 0), 5))
			local rounded = { box = { center = { 0, 0, 0 }, size = { 20, 10, 8 }, round = 2 } }
			check.truthy(
				near(Sdf.shape(rounded, 13, 0, 0), 3) and near(Sdf.shape(rounded, 10, 5, 4), math.sqrt(12) - 2)
			)
			local cap = { capsule = { from = { 0, 0, 0 }, to = { 10, 0, 0 }, radius = 3 } }
			check.truthy(near(Sdf.shape(cap, 5, 0, 7), 4) and near(Sdf.shape(cap, 13, 4, 0), 2))
			check.truthy(
				near(Sdf.shape({ capsule = { from = { 1, 2, 3 }, to = { 1, 2, 3 }, radius = 3 } }, 1, 7, 3), 2)
			)
			check.equal(Sdf.smin(3, 5, 0), 3)
			check.truthy(near(Sdf.smin(3, 3, 4), 2) and near(Sdf.smin(3, 4, 4), 3 - (3 / 4) ^ 2))
			local hill = {
				shapes = {
					{ ball = { center = { 0, 0, 0 }, radius = 20 } },
					{ capsule = { from = { -30, 0, 0 }, to = { 30, 0, 0 }, radius = 5 }, cut = true },
				},
			}
			local d, c = Sdf.at(hill, 0, 0, 0)
			check.truthy(near(d, 5) and near(c, -5)) -- (in the tunnel)
			d, c = Sdf.at(hill, 0, 10, 0)
			check.truthy(near(d, -5) and near(c, 5)) -- (in the rock over it)
			table.insert(hill.shapes, { ball = { center = { 0, 0, 0 }, radius = 3 } })
			d, c = Sdf.at(hill, 0, 0, 0)
			check.truthy(d < 0 and c < 0) -- (a shape added after the cut fills it again: land, inside the cut)
			-- two cuts that meet: the later one's blend rounds the seam between them
			local two = {
				shapes = {
					{ ball = { center = { 0, 0, 0 }, radius = 10 }, cut = true },
					{ ball = { center = { 16, 0, 0 }, radius = 10 }, cut = true },
				},
			}
			local _, notch = Sdf.at(two, 8, 7, 0)
			check.truthy(notch > 0)
			two.shapes[2].blend = 8
			_, notch = Sdf.at(two, 8, 7, 0)
			check.truthy(notch < 0)
			local lo, hi = Sdf.bounds({ shapes = { { ball = { center = { 0, 10, 0 }, radius = 5 } } } })
			check.equal(`{lo[1]} {lo[2]} {lo[3]} {hi[1]} {hi[2]} {hi[3]}`, "-9 1 -9 9 19 9")
			lo, hi = Sdf.bounds({
				shapes = {
					{ ball = { center = { 0, 10, 0 }, radius = 5 }, blend = 6 },
					{ box = { center = { 40, 0, 0 }, size = { 10, 20, 30 } } },
					{ capsule = { from = { 0, 0, -50 }, to = { 0, 30, 0 }, radius = 2 }, cut = true },
				},
			})
			check.equal(`{lo[1]} {lo[2]} {lo[3]} {hi[1]} {hi[2]} {hi[3]}`, "-15 -14 -56 49 36 19")
			local fill, clear = Sdf.cell(-2, Sdf.FAR)
			check.equal(`{fill} {clear}`, "1 0")
			fill, clear = Sdf.cell(1, Sdf.FAR)
			check.equal(`{fill} {clear}`, "0.25 0")
			fill, clear = Sdf.cell(5, 0)
			check.equal(`{fill} {clear}`, "0 0.5")
			fill, clear = Sdf.cell(5, -2)
			check.equal(`{fill} {clear}`, "0 1")
			fill, clear = Sdf.cell(-1, Sdf.FAR)
			check.equal(`{fill} {clear}`, "0.75 0")
			fill, clear = Sdf.cell(5, -1)
			check.equal(`{fill} {clear}`, "0 0.75")
			-- the cells the game visits: the box carried out to the 4-stud grid
			check.equal(Sdf.cells({ shapes = { { ball = { center = { 0, 10, 0 }, radius = 5 } } } }), 6 * 5 * 6) -- (-12..12, 0..20)
			check.equal(Sdf.cells({ shapes = { { ball = { center = { 2, 10, 0 }, radius = 6 } } } }), 5 * 5 * 6) -- (-8..12, 0..20, -12..12)
		end)

		test.case(
			"the compiler: an sdf op is checked, kept in the terrain's order, and handed to the walk check",
			function()
				local function compile(terrain: any): ({ string }, any)
					local bp = { name = "T", scale = "r6", palette = {}, terrain = terrain, build = {} }
					local _, _, issues = World.compile(bp)
					local errors = {}
					for _, i in issues do
						if i.severity == "error" then
							table.insert(errors, i.message)
						end
					end
					return errors, World.terrainField(bp)
				end
				local ground = { ground = { center = { 0, 0, 0 }, size = { 200, 200 }, material = "Grass" } }
				local hill = { block = { center = { 0, 20, 0 }, size = { 40, 40, 200 }, material = "Rock" } }
				local errors, field = compile({ ground, hill, { sdf = SPEC } })
				check.equal(#errors, 0, table.concat(errors, " | "))
				-- (after the block it is cut out of, as written)
				check.equal(#field.solids, 2)
				check.equal(field.solids[1].kind, "block")
				check.equal(field.solids[2].kind, "sdf")
				check.equal(#field.solids[2].spec.shapes, 5)
				check.equal(field.solids[2].spec.material, "Rock")
				-- what is wrong with it is said, by its place in the terrain
				errors = compile({ ground, { sdf = { material = "Rock", shapes = {} } } })
				check.truthy(
					string.find(table.concat(errors, " | "), "one to 24 shapes", 1, true),
					table.concat(errors, " | ")
				)
				errors =
					compile({ ground, { sdf = { shapes = { { ball = { center = { 0, 0, 0 }, radius = 10 } } } } } })
				check.truthy(string.find(table.concat(errors, " | "), "sdf.material", 1, true))
				-- a ground listed AFTER an sdf: the game writes in order and would fill the caves again
				errors = compile({ { sdf = SPEC }, ground })
				check.truthy(
					string.find(table.concat(errors, " | "), 'a ground op after an "sdf" op (terrain[1])', 1, true),
					table.concat(errors, " | ")
				)
				errors = compile({ ground, { sdf = SPEC }, hill })
				check.equal(#errors, 0) -- (a block after it is written over it, in the game and in the check alike)
				-- all the sdf ops of a world together
				local big =
					{ material = "Rock", shapes = { { box = { center = { 0, 0, 0 }, size = { 300, 300, 300 } } } } }
				errors = compile({ ground, { sdf = big }, { sdf = big }, { sdf = big } })
				check.equal(#errors, 0)
				errors = compile({ ground, { sdf = big }, { sdf = big }, { sdf = big }, { sdf = big } })
				check.truthy(string.find(table.concat(errors, " | "), 'cells of "sdf" ops in all', 1, true))
				errors = compile({ ground, { cave = {} } })
				check.truthy(string.find(table.concat(errors, " | "), "cylinder | sdf | water", 1, true))
			end
		)

		test.case("what is wrong with an sdf op is said", function()
			local function wrong(spec: any, text: string)
				local problems = Sdf.problems(spec)
				check.truthy(#problems >= 1)
				check.truthy(string.find(table.concat(problems, " | "), text, 1, true), table.concat(problems, " | "))
			end
			local ball = { ball = { center = { 0, 0, 0 }, radius = 10 } }
			check.equal(#Sdf.problems({ material = "Rock", shapes = { ball } }), 0)
			wrong(5, "sdf is {")
			wrong({ shapes = { ball } }, "sdf.material")
			wrong({ material = "Rock" }, "one to 24 shapes")
			wrong({ material = "Rock", shapes = {} }, "one to 24 shapes")
			wrong({ material = "Rock", shapes = table.create(25, ball) }, "one to 24 shapes")
			wrong({ material = "Rock", shapes = { ball }, colour = 3 }, "sdf.colour")
			wrong({ material = "Rock", shapes = { 5 } }, "shapes[1] is")
			wrong({ material = "Rock", shapes = { { cut = true } } }, "ONE of ball, box, capsule")
			wrong({ material = "Rock", shapes = { { ball = ball.ball, box = {} } } }, "ONE of ball, box, capsule")
			wrong({ material = "Rock", shapes = { { ball = ball.ball, cone = 4 } } }, "shapes[1].cone")
			wrong({ material = "Rock", shapes = { { ball = ball.ball, cut = "yes" } } }, "shapes[1].cut")
			wrong({ material = "Rock", shapes = { { ball = ball.ball, blend = -1 } } }, "shapes[1].blend")
			wrong({ material = "Rock", shapes = { { ball = ball.ball, blend = 65 } } }, "shapes[1].blend")
			wrong({ material = "Rock", shapes = { { ball = { center = { 0, 0 }, radius = 10 } } } }, "shapes[1].ball")
			wrong({ material = "Rock", shapes = { { ball = { center = { 0, 0, 0 }, radius = 1 } } } }, "shapes[1].ball")
			wrong(
				{ material = "Rock", shapes = { { ball = { center = { 0, 0, 0 }, radius = 0 / 0 } } } },
				"shapes[1].ball"
			)
			wrong(
				{ material = "Rock", shapes = { { box = { center = { 0, 0, 0 }, size = { 10, 2, 10 } } } } },
				"shapes[1].box"
			)
			wrong(
				{ material = "Rock", shapes = { { box = { center = { 0, 0, 0 }, size = { 10, 10 } } } } },
				"shapes[1].box"
			)
			wrong(
				{ material = "Rock", shapes = { { box = { center = { 0, 0, 0 }, size = { 10, 8, 10 }, round = 5 } } } },
				"round is 0 to half its least side"
			)
			wrong(
				{ material = "Rock", shapes = { { capsule = { from = { 0, 0, 0 }, to = { 9, 9 }, radius = 3 } } } },
				"shapes[1].capsule"
			)
			wrong(
				{ material = "Rock", shapes = { { capsule = { from = { 0, 0, 0 }, to = { 9, 9, 9 }, radius = 300 } } } },
				"shapes[1].capsule"
			)
			-- a cut that does not open in 4-stud cells; land of water or of air; a shape far off the map
			local function shaped(shape: any): any
				return { material = "Rock", shapes = { shape } }
			end
			wrong(
				shaped({ ball = { center = { 0, 0, 0 }, radius = 3.9 }, cut = true }),
				"does not open in the game's 4-stud cells"
			)
			wrong(
				shaped({ capsule = { from = { 0, 0, 0 }, to = { 9, 0, 0 }, radius = 3 }, cut = true }),
				"does not open"
			)
			wrong(shaped({ box = { center = { 0, 0, 0 }, size = { 7, 20, 20 } }, cut = true }), "a cut 7 studs across")
			check.equal(#Sdf.problems(shaped({ ball = { center = { 0, 0, 0 }, radius = 4 }, cut = true })), 0)
			check.equal(#Sdf.problems(shaped({ box = { center = { 0, 0, 0 }, size = { 8, 20, 20 } }, cut = true })), 0)
			check.equal(#Sdf.problems(shaped({ ball = { center = { 0, 0, 0 }, radius = 2 } })), 0) -- (land may be thin)
			wrong({ material = "Water", shapes = { ball } }, 'sdf.material "Water"')
			wrong({ material = "Air", shapes = { ball } }, 'sdf.material "Air"')
			wrong({ material = "", shapes = { ball } }, "sdf.material")
			wrong(shaped({ ball = { center = { 16001, 0, 0 }, radius = 10 } }), "shapes[1].ball")
			wrong(shaped({ ball = { center = { 1e300, 0, 0 }, radius = 10 } }), "shapes[1].ball")
			wrong(shaped({ box = { center = { 0, 0, -16001 }, size = { 10, 10, 10 } } }), "shapes[1].box")
			wrong(shaped({ capsule = { from = { 0, 0, 0 }, to = { 0, 20000, 0 }, radius = 5 } }), "shapes[1].capsule")
			wrong(shaped({ ball = { center = { 0, 0, 0, 0 }, radius = 10 } }), "shapes[1].ball")
			wrong(shaped({ capsule = { from = { 0, 0, 0 }, to = { 9, 0, 0 }, radius = 1 } }), "shapes[1].capsule")
			wrong(shaped({ box = { center = { 0, 0, 0 }, size = { 10, 8, 10 }, round = -1 } }), "round is 0 to half")
			wrong(shaped({ box = { center = { 0, 0, 0 }, size = { 10, 8, 513 } } }), "shapes[1].box")
			wrong(shaped({ ball = { center = { 0, 0, 0 }, radius = 257 } }), "shapes[1].ball")
			-- every bad shape is said, not the first alone
			local both = Sdf.problems({
				material = "Rock",
				shapes = { { cut = true }, ball, { ball = { center = { 0, 0 }, radius = 10 } } },
			})
			check.equal(#both, 2)
			-- exactly 24 shapes is an op
			check.equal(#Sdf.problems({ material = "Rock", shapes = table.create(24, ball) }), 0)
			-- the cells are counted as the game visits them (carried out to the grid): a box of 308 at 1, 1, 1 is
			-- 80 cells a side
			wrong(shaped({ box = { center = { 1, 1, 1 }, size = { 308, 308, 308 } } }), "512000 cells of 4 studs")
			check.equal(#Sdf.problems(shaped({ box = { center = { 0, 0, 0 }, size = { 304, 304, 304 } } })), 0) -- (78 a side)
			-- too wide, too many cells
			wrong({
				material = "Rock",
				shapes = { ball, { ball = { center = { 600, 0, 0 }, radius = 10 } } },
			}, "over 512")
			wrong({
				material = "Rock",
				shapes = { { box = { center = { 0, 0, 0 }, size = { 500, 300, 500 } } } },
			}, "cells of 4 studs")
		end)
	end)
end

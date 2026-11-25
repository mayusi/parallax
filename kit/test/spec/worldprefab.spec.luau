-- worldprefab.spec.luau (kit) — A GROUP OF STEPS NAMED ONCE AND SET DOWN MANY TIMES (kit/lib/worldprefab.luau, the
-- "prefabs" of a blueprint and its "prefab" build step; the owner's method list: "Prefab-based assembly",
-- "Hierarchical instancing"). Held here: a placed prefab is the same thing moved (every part where the typed one
-- would stand after the shift and the turn), prefabs inside prefabs, what a prefab may hold, what a placement may
-- say.
-- Not claimed here: that a place built of prefabs looks right. That is a built world, looked at.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Decal = require("../../lib/worlddecal")
local LaneLocks = require("../../lib/lanelocks")
local Prefab = require("../../lib/worldprefab")
local World = require("../../lib/world")

local PALETTE = {
	wood = { material = "Wood", color = { 120, 90, 60 } },
	cloth = { material = "Fabric", color = { 150, 40, 40 } },
}

-- a market stall typed round the origin: a counter, two posts, an awning that leans (its own turn is not a step
-- turn: a part's "rot")
local STALL = {
	{ part = { name = "Counter", mat = "wood", size = { 8, 3, 2 }, pos = { 0, 1.5, 0 } } },
	{ part = { name = "PostL", mat = "wood", size = { 1, 8, 1 }, pos = { -3.5, 4, 2 } } },
	{ part = { name = "PostR", mat = "wood", size = { 1, 8, 1 }, pos = { 3.5, 4, 2 } } },
	{ part = { name = "Awning", mat = "cloth", size = { 9, 0.4, 5 }, pos = { 0, 8.2, 1 } } },
}

local function compile(bp: any): (any, { any }, { string }, { string }, any)
	bp.name = "T"
	bp.palette = PALETTE
	local model, parts, issues, extras = World.compile(bp, {
		meshes = {},
		decals = function(name: string): (any?, string?)
			return { name = name, kind = "leak", tint = { 46, 40, 33 } }, "rbxassetid://7"
		end,
	})
	local errors, warns = {}, {}
	for _, i in issues do
		if i.path ~= "spawn" then
			table.insert(if i.severity == "error" then errors else warns, `{i.path}: {i.message}`)
		end
	end
	return model, parts, errors, warns, extras
end

local function near(a: number, b: number): boolean
	return math.abs(a - b) < 1e-6
end

local function byName(parts: { any }, name: string): { any }
	local out = {}
	for _, p in parts do
		if p.name == name then
			table.insert(out, p)
		end
	end
	return out
end

-- the Models of the built world, by name
local function models(model: any): { [string]: any }
	local out = {}
	for _, child in model.Children or {} do
		out[child.Name] = child
	end
	return out
end

return function()
	test.suite("A group of steps named once and set down many times", function()
		test.case("a placed prefab is the same thing, moved", function()
			-- the stall typed as it stands, and the same stall as a prefab set down at the origin: the same parts
			local _, typed = compile({ build = STALL })
			local model, placed, errors, warns, extras = compile({
				prefabs = { Stall = STALL },
				build = { { prefab = { name = "Stall", at = { 0, 0, 0 } } } },
			})
			check.equal(#errors, 0, table.concat(errors, " | "))
			check.equal(#warns, 0, table.concat(warns, " | "))
			check.equal(#placed, #typed)
			for i, p in typed do
				local q = placed[i]
				check.equal(q.name, p.name)
				for a = 1, 3 do
					check.truthy(near(q.pos[a], p.pos[a]) and near(q.size[a], p.size[a]))
				end
				check.equal(q.axisAligned, true)
			end
			check.equal(extras.prefabs[1].prefab, "Stall")
			check.equal(extras.prefabs[1].name, "Stall_1")
			check.equal(extras.prefabs[1].steps, 4)
			-- each step's Model carries its placement's name
			local m = models(model)
			check.truthy(m["Stall_1.Counter"] ~= nil)
			check.truthy(m["Stall_1.Awning"] ~= nil)
			check.equal(m["Counter"], nil)

			-- shifted: every part where it was typed, plus "at"
			local _, moved = compile({
				prefabs = { Stall = STALL },
				build = { { prefab = { name = "Stall", at = { 100, 7, -40 } } } },
			})
			for i, p in typed do
				check.truthy(near(moved[i].pos[1], p.pos[1] + 100))
				check.truthy(near(moved[i].pos[2], p.pos[2] + 7))
				check.truthy(near(moved[i].pos[3], p.pos[3] - 40))
			end

			-- turned a quarter about its "at": where World's own turn puts each point, and the part turned with it
			local _, turned, terr = compile({
				prefabs = { Stall = STALL },
				build = { { prefab = { name = "Stall", at = { 100, 0, -40 }, turn = 90 } } },
			})
			check.equal(#terr, 0, table.concat(terr, " | "))
			for i, p in typed do
				local x, z = World.turnPoint(p.pos[1] + 100, p.pos[3] - 40, 100, -40, 90)
				check.truthy(near(turned[i].pos[1], x) and near(turned[i].pos[3], z), p.name)
				check.truthy(near(turned[i].pos[2], p.pos[2]))
				check.equal(turned[i].axisAligned, false)
				local m90 = World.turnMatrix(90)
				for a = 1, 3 do
					for b = 1, 3 do
						check.truthy(near(turned[i].rot[a][b], m90[a][b]))
					end
				end
			end
			-- (the left post, typed at x -3.5, z 2, is not where the right one is: a turn is no mirror)
			local l, r = byName(turned, "PostL")[1], byName(turned, "PostR")[1]
			check.truthy(not near(l.pos[3], r.pos[3]))
			-- the same as the stall typed with a step turn about the origin and shifted by hand
			local x, z = World.turnPoint(-3.5 + 100, 2 - 40, 100, -40, 90)
			check.truthy(near(l.pos[1], x) and near(l.pos[3], z))

			-- an odd angle
			local _, odd = compile({
				prefabs = { Stall = STALL },
				build = { { prefab = { name = "Stall", at = { 10, 0, 10 }, turn = 37 } } },
			})
			local ox, oz = World.turnPoint(3.5 + 10, 2 + 10, 10, 10, 37)
			local post = byName(odd, "PostR")[1]
			check.truthy(near(post.pos[1], ox) and near(post.pos[3], oz))
		end)

		test.case("many placements: each its own name, each its own place", function()
			local model, parts, errors, _, extras = compile({
				prefabs = { Stall = STALL },
				build = {
					{ prefab = { name = "Stall", at = { 0, 0, 0 } } },
					{ prefab = { name = "Stall", at = { 20, 0, 0 }, turn = 180 } },
					{ prefab = { name = "Stall", at = { 40, 0, 0 }, as = "Fishmonger" } },
					{ part = { name = "Well", mat = "wood", size = { 4, 3, 4 }, pos = { 20, 1.5, 20 } } },
				},
			})
			check.equal(#errors, 0, table.concat(errors, " | "))
			check.equal(#parts, 13)
			check.equal(#extras.prefabs, 3)
			local m = models(model)
			check.truthy(m["Stall_1.Counter"] ~= nil and m["Stall_2.Counter"] ~= nil and m["Fishmonger.Counter"] ~= nil)
			check.truthy(m["Well"] ~= nil) -- (a step that is no prefab's keeps its own name)
			local counters = byName(parts, "Counter")
			check.equal(#counters, 3)
			check.truthy(near(counters[1].pos[1], 0) and near(counters[2].pos[1], 20) and near(counters[3].pos[1], 40))
			-- the half-turned stall's posts stand on the other side of its counter
			local posts = byName(parts, "PostL")
			check.truthy(near(posts[1].pos[3], 2) and near(posts[2].pos[3], -2))
			check.truthy(near(posts[2].pos[1], 20 + 3.5))
			-- each placement's steps are copies of their own: none shares a table with the prefab or with another
			local one = Prefab.expand({ name = "Stall", at = { 0, 0, 0 } }, { Stall = STALL }, "p", "A") :: { any }
			local two = Prefab.expand({ name = "Stall", at = { 9, 0, 0 } }, { Stall = STALL }, "q", "B") :: { any }
			check.equal(#one, 4)
			check.truthy(one[1].step ~= STALL[1] and one[1].step.part ~= STALL[1].part)
			check.truthy(one[1].step.part ~= two[1].step.part and one[1].step.part.pos ~= two[1].step.part.pos)
			check.equal(one[1].step.part.name, "Counter")
			check.equal(one[1].step.part.pos[2], 1.5)
			check.equal(one[4].path, "p.Stall[4]")
			check.equal(two[2].prefix, "B")
			-- two placements of one name
			local _, _, twice = compile({
				prefabs = { Stall = STALL },
				build = {
					{ prefab = { name = "Stall", at = { 0, 0, 0 }, as = "A" } },
					{ prefab = { name = "Stall", at = { 20, 0, 0 }, as = "A" } },
				},
			})
			check.equal(#twice, 1)
			check.truthy(string.find(twice[1], 'two placements are called "A"', 1, true))
		end)

		test.case("prefabs inside prefabs: moved by the inner one, then by the outer", function()
			local prefabs = {
				Stall = STALL,
				Market = {
					{ prefab = { name = "Stall", at = { -10, 0, 0 } } },
					{ prefab = { name = "Stall", at = { 10, 0, 0 }, turn = 180 } },
					{ part = { name = "Well", mat = "wood", size = { 4, 3, 4 }, pos = { 0, 1.5, 12 } } },
				},
				Quarter = {
					{ prefab = { name = "Market", at = { 0, 0, -50 } } },
					{ prefab = { name = "Market", at = { 0, 2, 50 }, turn = 90, as = "South" } },
				},
			}
			local model, parts, errors, _, extras = compile({
				prefabs = prefabs,
				build = { { prefab = { name = "Quarter", at = { 1000, 0, 0 }, turn = 90 } } },
			})
			check.equal(#errors, 0, table.concat(errors, " | "))
			check.equal(#parts, 2 * (4 + 4 + 1))
			check.equal(extras.prefabs[1].steps, 18)
			local m = models(model)
			check.truthy(m["Quarter_1.Market_1.Stall_1.Counter"] ~= nil)
			check.truthy(m["Quarter_1.Market_1.Stall_2.Counter"] ~= nil)
			check.truthy(m["Quarter_1.South.Stall_1.PostL"] ~= nil)
			check.truthy(m["Quarter_1.South.Well"] ~= nil)
			-- one point followed by hand: the south market's second stall's left post
			-- typed (-3.5, 4, 2) -> the stall at (10, 0, 0) turned 180 -> the market at (0, 2, 50) turned 90 -> the
			-- quarter at (1000, 0, 0) turned 90
			local x, y, z = -3.5, 4, 2
			x, z = World.turnPoint(x + 10, z + 0, 10, 0, 180)
			x, y, z = x + 0, y + 2, z + 50
			x, z = World.turnPoint(x, z, 0, 50, 90)
			x, z = World.turnPoint(x + 1000, z + 0, 1000, 0, 90)
			local found = false
			for _, p in byName(parts, "PostL") do
				found = found or (near(p.pos[1], x) and near(p.pos[2], y) and near(p.pos[3], z))
			end
			check.truthy(found, "the post stands where the three moves put it")
			-- and the module's own arithmetic says the same
			local mx, my, mz, deg = Prefab.moved({
				{ dx = 10, dy = 0, dz = 0, deg = 180, x = 10, z = 0 },
				{ dx = 0, dy = 2, dz = 50, deg = 90, x = 0, z = 50 },
				{ dx = 1000, dy = 0, dz = 0, deg = 90, x = 1000, z = 0 },
			}, -3.5, 4, 2)
			check.truthy(near(mx, x) and near(my, y) and near(mz, z))
			check.equal(deg, 360)
			-- a part turned 360 in all stands square again
			local post: any = nil
			for _, p in byName(parts, "PostL") do
				if near(p.pos[1], x) and near(p.pos[3], z) then
					post = p
				end
			end
			check.truthy(near(post.rot[1][1], 1) and near(post.rot[3][3], 1) and near(post.rot[1][3], 0))
			-- the module's turn is the compiler's
			for _, c in
				{
					{ 3, 4, 1, 2, 90 },
					{ -7, 2, 0, 0, 37 },
					{ 5, 5, 5, 5, 180 },
					{ 1, 0, 0, 0, -90 },
					{ 2, 9, -3, 4, 271.5 },
				}
			do
				local ax, az = Prefab.turn(c[1], c[2], c[3], c[4], c[5])
				local bx, bz = World.turnPoint(c[1], c[2], c[3], c[4], c[5])
				check.truthy(near(ax, bx) and near(az, bz))
			end
		end)

		test.case("a step's own turn, and what it claims, move with it", function()
			-- stairs claim their rise and run (a scale claim the check reads): the claim moves with the stairs
			local prefabs = {
				Steps = {
					{
						stairs = {
							name = "Up",
							mat = "wood",
							start = { 0, 0, 0 },
							dir = "+Z",
							steps = 6,
							rise = 1,
							run = 1.5,
							width = 6,
						},
					},
					{
						part = {
							name = "Flag",
							mat = "cloth",
							size = { 1, 6, 1 },
							pos = { 5, 3, 0 },
							turn = 90,
							about = { 0, 0 },
						},
					},
				},
			}
			local _, plain, e1, _, x1 =
				compile({ prefabs = prefabs, build = { { prefab = { name = "Steps", at = { 0, 0, 0 } } } } })
			local _, moved, e2, _, x2 = compile({
				prefabs = prefabs,
				build = { { prefab = { name = "Steps", at = { 50, 3, 0 }, turn = 90 } } },
			})
			check.equal(#e1, 0, table.concat(e1, " | "))
			check.equal(#e2, 0, table.concat(e2, " | "))
			check.equal(#plain, #moved)
			for i, p in plain do
				local x, z = World.turnPoint(p.pos[1] + 50, p.pos[3], 50, 0, 90)
				check.truthy(
					near(moved[i].pos[1], x) and near(moved[i].pos[3], z) and near(moved[i].pos[2], p.pos[2] + 3),
					p.name
				)
			end
			-- the flag: its own quarter turn about the prefab's origin first (typed x 5 -> z -5), then the placement's
			local fx, fz = World.turnPoint(5, 0, 0, 0, 90)
			local flag = byName(plain, "Flag")[1]
			check.truthy(near(flag.pos[1], fx) and near(flag.pos[3], fz))
			check.truthy(#x1.fits >= 1)
			check.equal(#x1.fits, #x2.fits)
			for i, f in x1.fits do
				local g = x2.fits[i]
				check.equal(g.kind, f.kind)
				check.truthy(near((g.yaw or 0) - (f.yaw or 0), 90))
				if type(f.pos) == "table" then
					local x, z = World.turnPoint(f.pos[1] + 50, f.pos[3], 50, 0, 90)
					check.truthy(near(g.pos[1], x) and near(g.pos[3], z) and near(g.pos[2], f.pos[2] + 3))
				end
			end
		end)

		test.case("what a fresh reader got past the first rules", function()
			-- A DECAL IN A PREFAB lies on its prefab's own wall, wherever the prefab is set down and however it is
			-- turned by quarters (it was judged at the origin, where its wall no longer stood)
			local shrine = {
				{ part = { name = "Wall", mat = "wood", size = { 20, 12, 2 }, pos = { 0, 6, 1 } } },
				{ decal = { name = "Leak", at = { 0, 6, 0 }, size = { 3, 3 }, facing = "north" } },
			}
			for _, turn in { 0, 90, 180, 270, -90 } do
				local _, parts, errors = compile({
					prefabs = { Shrine = shrine },
					build = { { prefab = { name = "Shrine", at = { 100, 3, -40 }, turn = turn } } },
				})
				check.equal(#errors, 0, `turn {turn}: ` .. table.concat(errors, " | "))
				local decal = byName(parts, "Decal_Leak")[1]
				check.truthy(decal ~= nil, `turn {turn}`)
				-- it stands 0.055 off the face, on the side the wall's own face was turned to
				local x, z = World.turnPoint(100, -40 - 0.055, 100, -40, turn)
				check.truthy(near(decal.pos[1], x) and near(decal.pos[3], z) and near(decal.pos[2], 9), `turn {turn}`)
				check.equal(decal.axisAligned, true) -- (made where it stands: not turned again)
			end
			-- set down twice: two decals, no word of "one spot"
			local _, twice, twiceErr = compile({
				prefabs = { Shrine = shrine },
				build = {
					{ prefab = { name = "Shrine", at = { 0, 0, 0 } } },
					{ prefab = { name = "Shrine", at = { 60, 0, 0 } } },
				},
			})
			check.equal(#twiceErr, 0, table.concat(twiceErr, " | "))
			check.equal(#byName(twice, "Decal_Leak"), 2)
			-- a prefab's decal is not held up by a wall of the WORLD at the place it was typed
			local _, _, air = compile({
				prefabs = {
					Lone = { { decal = { name = "Leak", at = { 0, 6, 0 }, size = { 3, 3 }, facing = "north" } } },
				},
				build = {
					{ part = { name = "Wall", mat = "wood", size = { 20, 12, 2 }, pos = { 0, 6, 1 } } },
					{ prefab = { name = "Lone", at = { 100, 0, 0 } } },
				},
			})
			check.equal(#air, 1)
			check.truthy(string.find(air[1], "lies on nothing", 1, true))
			-- off the quarter turns no face stands square: said
			local _, _, askew = compile({
				prefabs = { Shrine = shrine },
				build = { { prefab = { name = "Shrine", at = { 0, 0, 0 }, turn = 45 } } },
			})
			check.truthy(string.find(table.concat(askew, " | "), "quarter turns only", 1, true))
			check.equal(Decal.facingOf(0, 0, -1), "north")
			check.equal(Decal.facingOf(1, 0, 0), "east")
			check.equal(Decal.facingOf(0, -1, 0), "down")
			check.equal(Decal.facingOf(1, 1, 0), nil)

			-- THE BUILD'S RULES COUNT WHAT IS IN PREFABS: the steps with every prefab opened
			local house =
				{ building = { name = "H", center = { 0, 0, 0 }, size = { 20, 20 }, floors = 1, mat = "wood" } }
			local bp = {
				name = "T",
				prefabs = {
					Home = { house },
					Row = {
						{ prefab = { name = "Home", at = { 0, 0, 0 } } },
						{ prefab = { name = "Home", at = { 30, 0, 0 } } },
					},
				},
				build = {
					{ prefab = { name = "Row", at = { 0, 0, 0 } } },
					{ prefab = { name = "Row", at = { 0, 0, 60 } } },
					{ prefab = { name = "Home", at = { 90, 0, 0 } } },
					{ part = { name = "P", mat = "wood", size = { 1, 1, 1 }, pos = { 0, 0, 0 } } },
					{ prefab = { name = "Nope", at = { 0, 0, 0 } } },
				},
			}
			local flat = Prefab.flat(bp)
			check.equal(#flat, 7) -- (five houses, the part, and the placement of no prefab left as it is)
			local houses = 0
			for _, step in flat do
				houses += if step.building then 1 else 0
			end
			check.equal(houses, 5)
			check.equal(Prefab.flat({ build = { house } })[1], house) -- (no prefabs: the build itself)
			check.equal(#Prefab.flat(nil), 0)
			check.equal((LaneLocks.typedHouses(bp)), 5) -- (the lock that asks a town of six typed houses counts them)
			local six = table.clone(bp)
			six.build = table.clone(bp.build)
			table.insert(six.build, { prefab = { name = "Home", at = { 150, 0, 0 } } })
			check.equal((LaneLocks.typedHouses(six)), 6)
			-- a prefab that holds itself does not hang the list
			check.truthy(#Prefab.flat({
				prefabs = { A = { { prefab = { name = "A", at = { 0, 0, 0 } } } } },
				build = { { prefab = { name = "A", at = { 0, 0, 0 } } } },
			}) >= 1)

			-- a sloped claim's own ground heights are lifted with its prefab
			local lane = {
				fit = {
					kind = "alley",
					name = "Lane",
					from = { 0, -10 },
					to = { 0, 10 },
					pos = { 0, 0, 0 },
					ground = { 0, 2 },
				},
			}
			local _, _, _, _, low =
				compile({ prefabs = { L = { lane } }, build = { { prefab = { name = "L", at = { 0, 0, 0 } } } } })
			local _, _, _, _, high =
				compile({ prefabs = { L = { lane } }, build = { { prefab = { name = "L", at = { 0, 5, 0 } } } } })
			if #low.fits > 0 and type(low.fits[1].ground) == "table" then
				check.equal(low.fits[1].ground[1], 0)
				check.equal(high.fits[1].ground[1], 5)
				check.equal(high.fits[1].ground[2], 7)
			else
				check.truthy(false, "the alley's claim did not come back with its ground")
			end
		end)

		test.case("what a prefab may hold and a placement may say", function()
			local function errorsOf(bp: any): string
				local _, _, errors = compile(bp)
				return table.concat(errors, " | ")
			end
			local function said(bp: any, text: string)
				local all = errorsOf(bp)
				check.truthy(string.find(all, text, 1, true), text .. " <- " .. all)
			end
			local place = { { prefab = { name = "Stall", at = { 0, 0, 0 } } } }
			said({ build = place }, "and it has none")
			said({ prefabs = { STALL }, build = place }, '"prefabs" is {')
			said({ prefabs = { ["a b"] = STALL }, build = {} }, "is no name")
			said({ prefabs = { Stall = {} }, build = {} }, "this has none")
			said({ prefabs = { Stall = "x" }, build = {} }, "this has none")
			said({ prefabs = { Stall = { { part = 5 } } }, build = {} }, "a step is one generator")
			said({ prefabs = { Stall = { { part = {}, wall = {} } } }, build = {} }, "a step is one generator")
			-- kinds that make more than parts cannot be moved
			for _, kind in
				{ "town", "path", "forest", "scatter", "tree", "dungeon", "cave", "tiles", "horizon", "peak", "city" }
			do
				said(
					{ prefabs = { Stall = { { [kind] = {} } } }, build = {} },
					`a "{kind}" step cannot stand in a prefab`
				)
			end
			said({
				prefabs = {
					Stall = {
						{
							part = {
								name = "P",
								mat = "wood",
								size = { 1, 1, 1 },
								pos = { 0, 0, 0 },
								ground = true,
							},
						},
					},
				},
				build = {},
			}, '"ground": true cannot be said in a prefab')
			-- a prefab that holds itself, at once or far down
			said(
				{ prefabs = { A = { { prefab = { name = "A", at = { 0, 0, 0 } } } } }, build = {} },
				"a prefab cannot hold itself"
			)
			said({
				prefabs = {
					A = { { prefab = { name = "B", at = { 0, 0, 0 } } } },
					B = { { prefab = { name = "C", at = { 0, 0, 0 } } } },
					C = { { prefab = { name = "A", at = { 0, 0, 0 } } } },
				},
				build = {},
			}, "a prefab cannot hold itself")
			said(
				{ prefabs = { A = { { prefab = { name = "Nope", at = { 0, 0, 0 } } } } }, build = {} },
				'no prefab "Nope"'
			)
			-- two placements in one prefab may not share a name, typed or made
			said({
				prefabs = {
					Stall = STALL,
					M = {
						{ prefab = { name = "Stall", at = { 0, 0, 0 }, as = "A" } },
						{ prefab = { name = "Stall", at = { 9, 0, 0 }, as = "A" } },
					},
				},
				build = {},
			}, 'two placements in this prefab are called "A"')
			said({
				prefabs = {
					Stall = STALL,
					M = {
						{ prefab = { name = "Stall", at = { 0, 0, 0 } } },
						{ prefab = { name = "Stall", at = { 9, 0, 0 }, as = "Stall_1" } },
					},
				},
				build = {},
			}, 'two placements in this prefab are called "Stall_1"')
			-- four deep is the most
			local function chain(n: number): any
				local prefabs: any = { P1 = STALL }
				for d = 2, n do
					prefabs[`P{d}`] = { { prefab = { name = `P{d - 1}`, at = { 1, 0, 0 } } } }
				end
				return prefabs
			end
			check.equal(
				errorsOf({ prefabs = chain(4), build = { { prefab = { name = "P4", at = { 0, 0, 0 } } } } }),
				""
			)
			said({ prefabs = chain(5), build = {} }, "prefabs stand 5 deep")
			-- a placement's words
			local good = { prefabs = { Stall = STALL } }
			local function placed(spec: any, text: string)
				said({ prefabs = good.prefabs, build = { { prefab = spec } } }, text)
			end
			placed({ name = "Nope", at = { 0, 0, 0 } }, 'no prefab "Nope"')
			placed({ name = 5, at = { 0, 0, 0 } }, '"name" is a prefab')
			placed({ name = "Stall" }, '"at" is [x, y, z]')
			placed({ name = "Stall", at = { 0, 0 } }, '"at" is [x, y, z]')
			placed({ name = "Stall", at = { 0, 0, 0, 0 } }, '"at" is [x, y, z]')
			placed({ name = "Stall", at = { 0, 1e7, 0 } }, "within a million studs")
			placed({ name = "Stall", at = { 0, 0, 0 }, turn = 1e9 }, "3600 at most")
			placed({ name = "Stall", at = { 0, 0 / 0, 0 } }, '"at" is [x, y, z]')
			placed({ name = "Stall", at = { 0, 0, 0 }, turn = "east" }, '"turn" is a number')
			placed({ name = "Stall", at = { 0, 0, 0 }, turn = math.huge }, '"turn" is a number')
			placed({ name = "Stall", at = { 0, 0, 0 }, as = "a b" }, '"as" is this placement')
			placed({ name = "Stall", at = { 0, 0, 0 }, scale = 2 }, '"scale" is not a word it knows')
			placed({ name = "Stall", at = { 0, 0, 0 }, ground = true }, '"ground" is not a word it knows')
			placed("Stall", "prefab needs {")
			-- 200 steps is the most one prefab holds
			local long = {}
			for k = 1, 201 do
				long[k] = { part = { name = "P", mat = "wood", size = { 1, 1, 1 }, pos = { k * 2, 0.5, 0 } } }
			end
			said({ prefabs = { Long = long }, build = {} }, "201 steps (a prefab holds 200 at most)")
			table.remove(long)
			check.equal(
				errorsOf({ prefabs = { Long = long }, build = { { prefab = { name = "Long", at = { 0, 0, 0 } } } } }),
				""
			)
			-- a blueprint with prefabs that are wrong builds none of them (no half thing)
			local _, parts = compile({ prefabs = { Stall = STALL, Bad = {} }, build = place })
			check.equal(#parts, 0)
			-- the kinds a prefab may hold are the turned ones, a decal and a spawn - not a city
			check.equal(World.IN_PREFAB.part, true)
			check.equal(World.IN_PREFAB.building, true)
			check.equal(World.IN_PREFAB.decal, true)
			check.equal(World.IN_PREFAB.spawn, true)
			check.equal(World.IN_PREFAB.city, nil)
			check.equal(World.IN_PREFAB.town, nil)
			check.equal(World.TURNABLE.city, true) -- (the list it was made from is as it was)
		end)
	end)
end

-- worldecosystem.spec.luau (kit) — A FOREST THAT GREW (kit/lib/worldecosystem.luau; the owner's method list:
-- "Ecosystem simulation"). The four rules are held one by one on small forests made for it, and the whole to what
-- such a simulation is for: the quick kind takes open ground first, the shade-bearing kind takes it from them.
-- Not claimed here: that a grown forest looks better than a scattered one. That is a built world, looked at.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Eco = require("../../lib/worldecosystem")
local LaneLocks = require("../../lib/lanelocks")
local World = require("../../lib/world")

local PALETTE = {
	bark = { material = "Wood", color = { 90, 70, 50 } },
	leaf = { material = "Grass", color = { 60, 110, 50 } },
}

local BIRCH =
	{ name = "birch", height = { 4, 22 }, crown = 14, years = 12, life = 45, shade = 0, seeds = 3, throw = 60 }
local OAK =
	{ name = "oak", height = { 4, 36 }, crown = 30, years = 50, life = 300, shade = 0.99, seeds = 1, throw = 40 }

local function kind(base: any, more: any): any
	local k = table.clone(base)
	for key, v in more do
		k[key] = v
	end
	return k
end

local function forest(more: any): any
	local f: any =
		{ name = "Wood", center = { 0, 0, 0 }, area = { 200, 160 }, seed = 3, trunk = "bark", leaves = "leaf" }
	for k, v in more do
		f[k] = v
	end
	return f
end

local function compile(f: any, opts: any?): (any, { any }, { string }, { string }, any)
	local model, parts, issues, extras =
		World.compile({ name = "T", scale = "r6", palette = PALETTE, build = { { forest = f } } }, opts)
	local errors, warns = {}, {}
	for _, i in issues do
		table.insert(if i.severity == "error" then errors else warns, i.message)
	end
	return model, parts, errors, warns, extras
end

local function names(parts: { any }): { [string]: number }
	local n: { [string]: number } = {}
	for _, p in parts do
		n[p.name] = (n[p.name] or 0) + 1
	end
	return n
end

-- which of two plants keeps the light from the other, by this file's own reading of the rule: the taller; of two
-- as tall the wider (of two alike neither, here: who came up first is not in what a forest hands back)
local function keeps(a: any, b: any): boolean
	if a.height ~= b.height then
		return a.height > b.height
	end
	return a.radius > b.radius
end

return function()
	test.suite("A forest that grew", function()
		test.case("what is wrong with an ecosystem is said", function()
			local function wrong(spec: any, text: string)
				local problems = Eco.problems(spec)
				check.truthy(#problems >= 1)
				check.truthy(string.find(table.concat(problems, " | "), text, 1, true), table.concat(problems, " | "))
			end
			check.equal(#Eco.problems({ species = { BIRCH } }), 0)
			check.equal(#Eco.problems({ years = 0, first = 0, species = { BIRCH, OAK } }), 0)
			check.equal(
				#Eco.problems({ years = 400, first = 200, species = { kind(BIRCH, { style = "pine", first = 3 }) } }),
				0
			)
			wrong(5, "an ecosystem is")
			wrong({ species = {} }, "one to six kinds")
			wrong({ species = { BIRCH, BIRCH, BIRCH, BIRCH, BIRCH, BIRCH, BIRCH } }, "one to six kinds")
			wrong({ years = 401, species = { BIRCH } }, "ecosystem.years")
			wrong({ years = 2.5, species = { BIRCH } }, "ecosystem.years")
			wrong({ first = -1, species = { BIRCH } }, "ecosystem.first")
			wrong({ yeers = 3, species = { BIRCH } }, "ecosystem.yeers")
			wrong({ species = { 5 } }, "ecosystem.species[1] is")
			wrong({ species = { BIRCH, kind(OAK, { name = "birch" }) } }, 'name "birch" is used twice')
			wrong({ species = { kind(BIRCH, { name = "" }) } }, "species[1].name")
			wrong({ species = { kind(BIRCH, { style = 4 }) } }, "species[1].style")
			wrong({ species = { kind(BIRCH, { style = "elm" }) } }, "one of the forest's tree styles: oak, dead, pine")
			wrong({ species = { kind(BIRCH, { meshes = {} }) } }, "species[1].meshes")
			wrong({ species = { kind(BIRCH, { meshes = { 5 } }) } }, "species[1].meshes")
			wrong({ species = { kind(BIRCH, { meshes = "oak_a" }) } }, "species[1].meshes")
			wrong({ species = { kind(BIRCH, { meshes = { "oak_a" }, style = "oak" }) } }, "a kind is built one way")
			-- a kind that claims less room than its trees take as built
			wrong({ species = { kind(BIRCH, { crown = 10 }) } }, "crown (10) is under half its grown height (22)")
			check.equal(#Eco.problems({ species = { kind(BIRCH, { crown = 11 }) } }), 0)
			check.equal(#Eco.problems({ species = { kind(BIRCH, { meshes = { "oak_a", "oak_b" } }) } }), 0)
			for _, style in Eco.STYLES do
				check.equal(#Eco.problems({ species = { kind(BIRCH, { style = style }) } }), 0)
			end
			wrong({ species = { kind(BIRCH, { height = { 1, 22 } }) } }, "species[1].height")
			wrong({ species = { kind(BIRCH, { height = { 4, 22, 30 } }) } }, "species[1].height")
			-- a seedling taller than 20 studs: two of them 3 studs apart would stand trunk in trunk
			wrong({ species = { kind(BIRCH, { height = { 21, 60 }, crown = 30 }) } }, "the seedling 2 to 20")
			check.equal(#Eco.problems({ species = { kind(BIRCH, { height = { 20, 60 }, crown = 30 }) } }), 0)
			wrong({ species = { kind(BIRCH, { height = { 22, 4 } }) } }, "species[1].height")
			wrong({ species = { kind(BIRCH, { height = 22 }) } }, "species[1].height")
			wrong({ species = { kind(BIRCH, { crown = 3 }) } }, "species[1].crown")
			wrong({ species = { kind(BIRCH, { crown = 121 }) } }, "species[1].crown")
			wrong({ species = { kind(BIRCH, { years = 0 }) } }, "species[1].years")
			wrong({ species = { kind(BIRCH, { life = 11 }) } }, "no less than its years to full size")
			wrong({ species = { kind(BIRCH, { shade = 1.1 }) } }, "species[1].shade")
			wrong({ species = { kind(BIRCH, { shade = -0.1 }) } }, "species[1].shade")
			wrong({ species = { kind(BIRCH, { seeds = 21 }) } }, "species[1].seeds")
			wrong({ species = { kind(BIRCH, { seeds = -1 }) } }, "species[1].seeds")
			wrong({ species = { kind(BIRCH, { throw = 2 }) } }, "species[1].throw")
			wrong({ species = { kind(BIRCH, { throw = 401 }) } }, "species[1].throw")
			wrong({ species = { kind(BIRCH, { first = 1.5 }) } }, "species[1].first")
			wrong({ species = { BIRCH, kind(OAK, { leaf = "green" }) } }, "species[2].leaf")
		end)

		test.case(
			"who keeps the light: the taller; of two as tall the wider; of two alike the first to come up",
			function()
				local function plant(height: number, radius: number, order: number): any
					return { height = height, radius = radius, order = order }
				end
				check.equal(Eco.shades(plant(30, 2, 9), plant(6, 20, 1)), true) -- (a tree over a wide bush)
				check.equal(Eco.shades(plant(6, 20, 1), plant(30, 2, 9)), false) -- (a bush shades no tree)
				check.equal(Eco.shades(plant(10, 5, 9), plant(10, 4, 1)), true)
				check.equal(Eco.shades(plant(10, 4, 1), plant(10, 5, 9)), false)
				check.equal(Eco.shades(plant(10, 5, 1), plant(10, 5, 2)), true)
				check.equal(Eco.shades(plant(10, 5, 2), plant(10, 5, 1)), false)
				-- in a forest: a low wide fern beside the oak does not wipe the oaks out (it did, when the wider crown
				-- shaded whatever its height)
				local FERN = {
					name = "fern",
					style = "fern",
					height = { 2, 6 },
					crown = 40,
					years = 5,
					life = 30,
					shade = 1,
					seeds = 2,
					throw = 30,
				}
				for seed = 1, 3 do
					local wood = Eco.run({ years = 200, species = { OAK, FERN } }, { 300, 240 }, seed)
					check.truthy(wood.census[200][1] >= 30, `{wood.census[200][1]} oaks among the ferns`)
					check.truthy(wood.census[200][2] >= 30)
					-- full-grown oaks stand with their stems under a fern's crown
					local under = 0
					for _, q in wood.plants do
						if q.kind == 1 and q.height > 20 then
							for _, f in wood.plants do
								if f.kind == 2 and (q.x - f.x) ^ 2 + (q.z - f.z) ^ 2 < f.radius ^ 2 then
									under += 1
									break
								end
							end
						end
					end
					check.truthy(under >= 3, `{under} oaks under ferns`)
				end
				-- two of one kind that come up in one year: both grow at one pace, so the one that came up first keeps
				-- the light and no two full-grown birches stand in each other's inner crown
				local wood = Eco.run({ years = 30, species = { BIRCH } }, { 200, 200 }, 2)
				local grown = 0
				for a, q in wood.plants do
					if q.age >= 12 then
						grown += 1
						for b = a + 1, #wood.plants do
							local r = wood.plants[b]
							if r.age >= 12 then
								check.truthy((q.x - r.x) ^ 2 + (q.z - r.z) ^ 2 >= (7 * Eco.ROOT) ^ 2)
							end
						end
					end
				end
				check.truthy(grown > 30)
			end
		)

		test.case("a plant's size is its age's: full width and height at its kind's years, no more after", function()
			local r, h = Eco.size(OAK, 0)
			check.equal(r, 0)
			check.equal(h, 4)
			r, h = Eco.size(OAK, 25)
			check.equal(r, 7.5)
			check.equal(h, 20)
			r, h = Eco.size(OAK, 50)
			check.equal(r, 15)
			check.equal(h, 36)
			r, h = Eco.size(OAK, 200)
			check.equal(r, 15)
			check.equal(h, 36)
		end)

		test.case("year 0 is the first seedlings; a kind that sets no seed grows old and is gone", function()
			local start = Eco.run(
				{ years = 0, first = 5, species = { BIRCH, kind(OAK, { first = 2 }) } },
				{ 300, 240 },
				3
			)
			check.equal(#start.plants, 7)
			local n = { 0, 0 }
			for _, p in start.plants do
				n[p.kind] += 1
				check.equal(p.age, 0)
				check.equal(p.radius, 0)
				check.equal(p.born, 0)
				check.equal(p.from, nil)
				check.equal(p.height, 4)
			end
			check.equal(n[1], 5)
			check.equal(n[2], 2)
			check.equal(start.census[0][1], 5)
			check.equal(start.census[0][2], 2)
			check.equal(start.years, 0)
			-- no seed: the six stand, each a year older a year, and at 45 they are still there; at 46 gone
			local barren = kind(BIRCH, { seeds = 0, crown = 4 })
			local old = Eco.run({ years = 45, species = { barren } }, { 400, 400 }, 3)
			check.equal(#old.plants, 6)
			for _, p in old.plants do
				check.equal(p.age, 45)
				check.equal(p.radius, 2)
				check.equal(p.height, 22)
			end
			check.equal(old.dead.old, 0)
			local gone = Eco.run({ years = 46, species = { barren } }, { 400, 400 }, 3)
			check.equal(#gone.plants, 0)
			check.equal(gone.dead.old, 6)
			check.equal(gone.census[46][1], 0)
			check.equal(gone.census[40][1], 6)
		end)

		test.case("what a grown forest is held to: places, ages, sizes, room for every stem", function()
			for seed = 1, 6 do
				local spec = { years = 120, species = { BIRCH, OAK } }
				local area = { 300, 240 }
				local wood = Eco.run(spec, area, seed)
				check.truthy(#wood.plants > 200)
				local n = { 0, 0 }
				local last = math.huge
				for _, p in wood.plants do
					local k = spec.species[p.kind]
					n[p.kind] += 1
					check.truthy(math.abs(p.x) <= 150 and math.abs(p.z) <= 120)
					check.truthy(p.age >= 0 and p.age <= k.life)
					check.equal(p.born + p.age, 120)
					local r, h = Eco.size(k, p.age)
					check.equal(p.radius, r)
					check.equal(p.height, h)
					check.truthy(p.age <= last) -- (the oldest first)
					last = p.age
					if p.born == 0 then
						check.equal(p.from, nil)
					else
						check.truthy(p.from > 0 and p.from <= k.throw)
					end
				end
				check.equal(wood.census[120][1], n[1])
				check.equal(wood.census[120][2], n[2])
				check.equal(wood.full, false)
				for a, p in wood.plants do
					for b = a + 1, #wood.plants do
						local q = wood.plants[b]
						local d = math.sqrt((p.x - q.x) ^ 2 + (p.z - q.z) ^ 2)
						check.truthy(d >= Eco.STEM, `two stems {d} studs apart`)
						local over, under = p, q
						if keeps(q, p) then
							over, under = q, p
						end
						if keeps(over, under) then
							-- no plant in the inner part of a crown that keeps the light from it, whatever its kind
							check.truthy(
								d >= over.radius * Eco.ROOT,
								`a plant {d} studs from a stem of radius {over.radius}`
							)
							-- and a kind that bears no shade stands under no such crown at all
							if spec.species[under.kind].shade == 0 then
								check.truthy(d >= over.radius, `a birch in shade: {d} under {over.radius}`)
							end
						end
					end
				end
				-- some of the shade-bearing kind DO stand in shade (or the rule above proves nothing of it)
				local under = 0
				for _, p in wood.plants do
					if p.kind == 2 then
						for _, q in wood.plants do
							if keeps(q, p) and (p.x - q.x) ^ 2 + (p.z - q.z) ^ 2 < q.radius ^ 2 then
								under += 1
								break
							end
						end
					end
				end
				check.truthy(under >= 3, `{under} oaks in shade`)
				-- and a tall tree is not shaded by a lower one: some birch stands with its stem under a lower oak's crown,
				-- and lives (a birch dies in any shade)
				local lesser = 0
				for _, p in wood.plants do
					if p.kind == 1 then
						for _, q in wood.plants do
							if
								q.height < p.height
								and q.radius > 0
								and (p.x - q.x) ^ 2 + (p.z - q.z) ^ 2 < q.radius ^ 2
							then
								lesser += 1
								break
							end
						end
					end
				end
				check.truthy(lesser >= 1, `{lesser} birch under a lesser crown`)
			end
		end)

		test.case("the same seed is the same forest; another seed another", function()
			local spec = { years = 60, species = { BIRCH, OAK } }
			local a, b, c =
				Eco.run(spec, { 200, 200 }, 7), Eco.run(spec, { 200, 200 }, 7), Eco.run(spec, { 200, 200 }, 8)
			check.equal(#a.plants, #b.plants)
			for i, p in a.plants do
				check.equal(p.x, b.plants[i].x)
				check.equal(p.z, b.plants[i].z)
				check.equal(p.kind, b.plants[i].kind)
				check.equal(p.age, b.plants[i].age)
			end
			check.truthy(#a.plants ~= #c.plants or a.plants[1].x ~= c.plants[1].x)
			-- the run does not change the spec it is given
			check.equal(spec.species[1].crown, 14)
			check.equal(spec.years, 60)
		end)

		test.case(
			"succession: the quick kind takes the open ground, the shade-bearing kind takes it from them",
			function()
				local took = 0
				for seed = 1, 8 do
					local wood = Eco.run({ years = 300, species = { BIRCH, OAK } }, { 300, 240 }, seed)
					local early, late = wood.census[30], wood.census[300]
					check.truthy(early[1] > early[2] * 20, `year 30: {early[1]} birch, {early[2]} oak`)
					-- the shade-bearing kind comes up under the quick one in every forest ...
					check.truthy(late[2] > early[2] * 30, `year 300: {late[2]} oak of {early[2]}`)
					check.truthy(
						late[1] < wood.census[60][1] * 0.6,
						`year 300: {late[1]} birch of {wood.census[60][1]}`
					)
					for y = 60, 240, 60 do
						check.truthy(wood.census[y + 60][2] > wood.census[y][2])
					end
					check.truthy(wood.dead.old > 100 and wood.dead.shade > 100 and wood.dead.crowd > 100)
					-- ... and has taken the ground from it in most (how far it gets in 300 years is the seed's)
					took += if late[2] > late[1] * 2 then 1 else 0
				end
				check.truthy(took >= 6, `{took} of 8`)
				-- without shade tolerance the oak never takes it: the same oak, dying in shade
				local never = Eco.run({ years = 300, species = { BIRCH, kind(OAK, { shade = 0 }) } }, { 300, 240 }, 1)
				local with = Eco.run({ years = 300, species = { BIRCH, OAK } }, { 300, 240 }, 1)
				check.truthy(with.census[300][2] > never.census[300][2] * 2)
			end
		)

		test.case("seeds fall within the kind's throw; the land's say is kept; a forest that fills up stops", function()
			local function mean(throw: number): number
				local wood = Eco.run({ years = 40, species = { kind(BIRCH, { throw = throw }) } }, { 600, 600 }, 5)
				local sum, n = 0, 0
				for _, p in wood.plants do
					if p.from then
						check.truthy(p.from <= throw)
						sum += p.from
						n += 1
					end
				end
				check.truthy(n > 50)
				return sum / n
			end
			check.truthy(mean(80) > mean(20) * 2)
			-- seeds fall evenly over the circle of the throw, not heaped at the stem: in open ground their mean
			-- distance is about two thirds of it (measured where nothing is in the way: one tree, its first seeding)
			local sum, n = 0, 0
			for seed = 1, 40 do
				local one = Eco.run(
					{ years = 12, first = 1, species = { kind(BIRCH, { seeds = 20, throw = 100 }) } },
					{ 2000, 2000 },
					seed,
					function(x: number, z: number)
						return x * x + z * z < 900 * 900
					end
				)
				for _, q in one.plants do
					if q.from then
						sum += q.from
						n += 1
					end
				end
			end
			check.truthy(n > 300)
			check.truthy(sum / n > 100 * 0.6 and sum / n < 100 * 0.72, `mean {sum / n} of a throw of 100`)
			-- the first seedlings: asked and set are handed back
			local few = Eco.run({ years = 0, first = 200, species = { BIRCH } }, { 20, 20 }, 1)
			check.equal(few.first.asked, 200)
			check.equal(few.first.set, #few.plants)
			check.truthy(few.first.set < 60)
			local all = Eco.run({ years = 0, first = 5, species = { BIRCH, OAK } }, { 300, 240 }, 1)
			check.equal(all.first.asked, 10)
			check.equal(all.first.set, 10)
			-- half a seed a year is a seed every other year, by chance: some come up; none from a kind that sets none
			local half = Eco.run({ years = 40, species = { kind(BIRCH, { seeds = 0.5 }) } }, { 400, 400 }, 5)
			local born = 0
			for _, p in half.plants do
				born += if p.from then 1 else 0
			end
			check.truthy(born > 10, `{born} born of half a seed a year`)
			local whole = Eco.run({ years = 40, species = { kind(BIRCH, { seeds = 1 }) } }, { 400, 400 }, 5)
			check.truthy(#whole.plants > #half.plants)
			-- no plant where the land says no: the east half is water
			local dry = Eco.run(
				{ years = 60, species = { BIRCH, OAK } },
				{ 300, 240 },
				2,
				function(x: number, _z: number)
					return x < 0
				end
			)
			check.truthy(#dry.plants > 100)
			for _, p in dry.plants do
				check.truthy(p.x < 0)
			end
			-- a kind that seeds wildly and bears all shade fills the forest to its most, and says so
			local weed = {
				name = "weed",
				height = { 2, 3 },
				crown = 4,
				years = 1,
				life = 400,
				shade = 1,
				seeds = 20,
				throw = 200,
			}
			local full = Eco.run({ years = 12, species = { weed } }, { 800, 800 }, 1)
			check.equal(full.full, true)
			check.equal(#full.plants, Eco.MOST)
		end)

		test.case(
			"the compiler: a forest's trees are the ones that grew, each of its kind's style and height",
			function()
				local eco = { years = 60, species = { kind(BIRCH, { style = "oak" }), kind(OAK, { style = "pine" }) } }
				local model, parts, errors, _, extras = compile(forest({ ecosystem = eco, center = { 100, 0, -50 } }))
				check.equal(#errors, 0, table.concat(errors, " | "))
				local grown = Eco.run(eco, { 200, 160 }, 3)
				local e = extras.ecosystems[1]
				check.equal(e.name, "Wood")
				check.equal(e.trees, #grown.plants)
				check.equal(e.years, 60)
				local stand = { 0, 0 }
				for _, p in grown.plants do
					stand[p.kind] += 1
				end
				check.equal(e.stand.birch, stand[1])
				check.equal(e.stand.oak, stand[2])
				check.truthy(stand[1] > 20 and stand[2] >= 6)
				check.equal(e.census[60][1], stand[1])
				check.equal(e.dead.old, grown.dead.old)
				-- both styles stand: broad crowns and needles; everything inside the forest's area (and a crown's reach)
				local n = names(parts)
				check.truthy(n.Canopy > 0 and n.Needles > 0 and n.Trunk >= e.trees)
				for _, p in parts do
					check.truthy(math.abs(p.pos[1] - 100) <= 100 + 30 and math.abs(p.pos[3] + 50) <= 80 + 30)
				end
				-- all of it in the model the game loads
				local held = 0
				for _, c in model.Children do
					if c.Name == "Wood" then
						held = #c.Children
					end
				end
				check.equal(held, #parts)
				-- one kind, one style: pines only have needles, oaks only crowns
				local _, pines =
					compile(forest({ ecosystem = { years = 40, species = { kind(BIRCH, { style = "pine" }) } } }))
				check.truthy(names(pines).Needles > 0)
				check.equal(names(pines).Canopy, nil)
				local _, oaks = compile(forest({ ecosystem = { years = 40, species = { BIRCH } } })) -- (no style said: oak)
				check.truthy(names(oaks).Canopy > 0)
				check.equal(names(oaks).Needles, nil)
				-- no tree taller than its kind grows: a forest of 22-stud birches has no part above 22 and a crown's lift
				local top = 0
				for _, p in oaks do
					top = math.max(top, p.pos[2] + p.size[2] / 2)
				end
				check.truthy(top > 12 and top <= 22 * 1.25, `top {top}`)
				-- a young forest is low: after 5 years no birch is over 11.5 studs (4 and five twelfths of the 18 it grows)
				local _, young = compile(forest({ ecosystem = { years = 5, species = { BIRCH } } }))
				local low = 0
				for _, p in young do
					low = math.max(low, p.pos[2] + p.size[2] / 2)
				end
				check.truthy(low > 4 and low <= 11.5 * 1.25, `top {low}`)
				-- the forest's seed is the ecosystem's; the same seed, the same parts
				local _, again = compile(forest({ ecosystem = { years = 40, species = { BIRCH } } }))
				check.equal(#again, #oaks)
				local _, other = compile(forest({ ecosystem = { years = 40, species = { BIRCH } }, seed = 4 }))
				check.truthy(#other ~= #oaks)
				-- trees keep off what the forest keeps off
				-- (a forest off the world's middle, a clearing off the forest's middle: the land's say is asked where the tree
				-- will stand, not where the simulation counts from)
				local off = { center = { 300, 0, -200 }, avoid = { { 340, -180, 50 } } }
				local _, _, _, _, clear =
					compile(forest(kind(off, { ecosystem = { years = 40, species = { BIRCH } } })))
				local _, _, _, _, full =
					compile(forest({ ecosystem = { years = 40, species = { BIRCH } }, center = off.center }))
				check.truthy(clear.ecosystems[1].trees < full.ecosystems[1].trees)
				local _, kept = compile(forest(kind(off, { ecosystem = { years = 40, species = { BIRCH } } })))
				local trunks = 0
				for _, q in kept do
					if q.name == "Trunk" then
						trunks += 1
						check.truthy((q.pos[1] - 340) ^ 2 + (q.pos[3] + 180) ^ 2 >= 46 ^ 2) -- (a trunk leans a little)
					end
				end
				check.truthy(trunks > 50)
				-- fewer first seedlings than asked is said
				local _, _, _, warns =
					compile(forest({ ecosystem = { years = 0, first = 200, species = { BIRCH } }, area = { 20, 20 } }))
				check.truthy(string.find(table.concat(warns, " | "), "first seedlings found a place", 1, true))
				local _, _, _, quiet = compile(forest({ ecosystem = { years = 0, first = 5, species = { BIRCH } } }))
				check.equal(string.find(table.concat(quiet, " | "), "first seedlings", 1, true), nil)
			end
		)

		test.case("the compiler: a kind of mesh trees stands as meshes, one of its list each", function()
			local reg = {
				tree_a = { kind = "tree", size = { 10, 30, 10 }, min = { -5, 0, -5 }, tris = 100, textured = true },
				tree_b = { kind = "tree", size = { 12, 30, 12 }, min = { -6, 0, -6 }, tris = 100, textured = true },
				fir_a = { kind = "tree", size = { 12, 30, 12 }, min = { -6, 0, -6 }, tris = 100, textured = true },
			}
			local eco = {
				years = 60,
				species = { kind(BIRCH, { meshes = { "tree_a", "tree_b" } }), kind(OAK, { meshes = { "fir_a" } }) },
			}
			local _, parts, errors, _, extras = compile(forest({ ecosystem = eco }), { meshes = reg })
			check.equal(#errors, 0, table.concat(errors, " | "))
			local n = names(parts)
			check.equal(n.KitMesh, extras.ecosystems[1].trees)
			check.equal(n.TrunkCollider, extras.ecosystems[1].trees)
			check.equal(n.Trunk, nil)
			local by: { [string]: number } = {}
			for _, p in parts do
				if p.name == "KitMesh" then
					by[p.mesh] = (by[p.mesh] or 0) + 1
				end
			end
			check.equal((by.tree_a or 0) + (by.tree_b or 0), extras.ecosystems[1].stand.birch)
			check.truthy(by.tree_a > 0 and by.tree_b > 0)
			check.equal(by.fir_a, extras.ecosystems[1].stand.oak)
		end)

		test.case("the compiler: what cannot be grown is said", function()
			local eco = { years = 40, species = { BIRCH } }
			local function wrong(more: any, text: string)
				local _, parts, errors = compile(forest(more))
				check.equal(#parts, 0)
				check.truthy(#errors >= 1)
				check.truthy(string.find(table.concat(errors, " | "), text, 1, true), table.concat(errors, " | "))
			end
			wrong({ ecosystem = { years = 40, species = {} } }, "one to six kinds")
			wrong({ ecosystem = { years = 40, species = { kind(BIRCH, { style = "elm" }) } } }, "tree styles")
			wrong({ ecosystem = eco, count = 30 }, 'a forest with an "ecosystem" has no "count"')
			wrong({ ecosystem = eco, density = { gap = 20 } }, 'has no "density"')
			wrong({ ecosystem = eco, gap = 4 }, 'has no "gap"')
			wrong({ ecosystem = eco, height = { 10, 20 } }, 'has no "height"')
			wrong({ ecosystem = eco, styles = { "oak" } }, 'has no "styles"')
			wrong({ ecosystem = eco, meshes = { "oak_a" } }, 'has no "meshes"')
			wrong({ ecosystem = eco, area = "big" }, '"area" is [width, depth]')
			wrong({ ecosystem = eco, area = { 200 } }, '"area" is [width, depth]')
			wrong({ ecosystem = eco, area = { -200, -160 } }, '"area" is [width, depth]')
			wrong({ ecosystem = eco, area = { 0, 0 } }, '"area" is [width, depth]')
			wrong({ ecosystem = eco, seed = "x" }, '"seed" is a number')
			wrong({ ecosystem = eco, seed = 1.5 }, '"seed" is a whole number')
			-- a density said false beside it is no density
			local _, parts, errors = compile(forest({ ecosystem = eco, density = false }))
			check.equal(#errors, 0)
			check.truthy(#parts > 100)
			-- a forest that fills up; a forest in which nothing is left standing
			local weed = {
				name = "weed",
				height = { 2, 3 },
				crown = 4,
				years = 1,
				life = 400,
				shade = 1,
				seeds = 20,
				throw = 200,
			}
			wrong({ ecosystem = { years = 12, species = { weed } }, area = { 800, 800 } }, "this forest fills up")
			wrong(
				{ ecosystem = { years = 60, species = { kind(BIRCH, { seeds = 0 }) } } },
				"nothing stands after 60 years"
			)
			-- "ecosystem": false is a forest as before
			local _, plain, none, _, extras = compile(forest({ ecosystem = false, count = 12 }))
			check.equal(#none, 0)
			check.truthy(#plain > 50)
			check.equal(#extras.ecosystems, 0)
		end)

		test.case("the lock: a mixed forest says how its kinds came to stand where they do", function()
			local function bp(forests: { any }): any
				local build = {}
				for _, f in forests do
					table.insert(build, { forest = f })
				end
				return { build = build }
			end
			local mixed = { name = "Wood", count = 40, styles = { "oak", "dead" } }
			check.equal(table.concat(LaneLocks.unsaidEcosystems(bp({ mixed })), ","), "Wood")
			check.equal(#LaneLocks.unsaidEcosystems(bp({ kind(mixed, { count = 39 }) })), 0)
			check.equal(#LaneLocks.unsaidEcosystems(bp({ kind(mixed, { styles = { "oak" } }) })), 0) -- (one kind)
			check.equal(#LaneLocks.unsaidEcosystems(bp({ kind(mixed, { ecosystem = false }) })), 0) -- (meant)
			check.equal(#LaneLocks.unsaidEcosystems(bp({ kind(mixed, { ecosystem = { years = 40 } }) })), 0)
			-- together: two small ones are asked as one large one would be; a forest with no name by its place
			local two = LaneLocks.unsaidEcosystems(
				bp({ kind(mixed, { count = 25 }), { count = 15, styles = { "oak", "pine" } } })
			)
			check.equal(table.concat(two, ","), "Wood,build[2]")
			-- mesh trees are kinds too; a forest by density counts as many (its count is not written)
			check.equal(#LaneLocks.unsaidEcosystems(bp({ { name = "M", count = 40, meshes = { "a", "b" } } })), 1)
			check.equal(
				#LaneLocks.unsaidEcosystems(bp({ { name = "D", density = { gap = 20 }, styles = { "oak", "dead" } } })),
				1
			)
			check.equal(#LaneLocks.unsaidEcosystems(bp({ { name = "T", styles = { "oak", "dead" } } })), 0) -- (10 unsaid)
			check.equal(#LaneLocks.unsaidEcosystems({}), 0)
			check.equal(#LaneLocks.unsaidEcosystems(nil), 0)
			-- a count below 0 takes nothing off the others
			local neg = { name = "Neg", count = -100, styles = { "oak", "pine" } }
			check.equal(
				table.concat(LaneLocks.unsaidEcosystems(bp({ neg, kind(mixed, { count = 60 }) })), ","),
				"Neg,Wood"
			)
			check.equal(
				#LaneLocks.unsaidDensities(bp({ { name = "Neg", count = -100 }, { name = "W", count = 60 } })),
				2
			)
			-- the same kind named twice is one kind; a forest of meshes is built of its meshes, whatever its styles say
			check.equal(#LaneLocks.unsaidEcosystems(bp({ { name = "O", count = 60, styles = { "oak", "oak" } } })), 0)
			check.equal(
				#LaneLocks.unsaidEcosystems(
					bp({ { name = "O", count = 60, styles = { "oak", "pine" }, meshes = { "a" } } })
				),
				0
			)
			check.equal(
				#LaneLocks.unsaidEcosystems(
					bp({ { name = "O", count = 60, styles = { "oak" }, meshes = { "a", "b" } } })
				),
				1
			)
			-- a mixed wood made by hand: two forests of one kind each, laid over each other
			local oaks = { name = "Oaks", center = { 0, 0, 0 }, area = { 200, 200 }, count = 30, styles = { "oak" } }
			local pines =
				{ name = "Pines", center = { 50, 0, 50 }, area = { 200, 200 }, count = 30, styles = { "pine" } }
			check.equal(table.concat(LaneLocks.unsaidEcosystems(bp({ oaks, pines })), ","), "Oaks,Pines")
			-- ... side by side they are two woods; the same kind over each other is one kind; one that says false
			check.equal(#LaneLocks.unsaidEcosystems(bp({ oaks, kind(pines, { center = { 200, 0, 0 } }) })), 0)
			check.equal(#LaneLocks.unsaidEcosystems(bp({ oaks, kind(pines, { center = { -200, 0, 0 } }) })), 0)
			check.equal(#LaneLocks.unsaidEcosystems(bp({ oaks, kind(pines, { center = { 0, 0, 200 } }) })), 0)
			check.equal(#LaneLocks.unsaidEcosystems(bp({ oaks, kind(pines, { center = { 0, 0, -200 } }) })), 0)
			check.equal(#LaneLocks.unsaidEcosystems(bp({ oaks, kind(pines, { styles = { "oak" } }) })), 0)
			check.equal(#LaneLocks.unsaidEcosystems(bp({ oaks, kind(pines, { ecosystem = false }) })), 0)
			check.equal(#LaneLocks.unsaidEcosystems(bp({ kind(oaks, { count = 19 }), kind(pines, { count = 20 }) })), 0)
			-- a grown forest is not asked for a density
			check.equal(
				#LaneLocks.unsaidDensities(
					bp({ { name = "G", ecosystem = { years = 40 } }, { name = "H", count = 60 } })
				),
				1
			)
			check.equal(#LaneLocks.unsaidDensities(bp({ { name = "G", ecosystem = false, count = 60 } })), 1)
			-- the fixture: two forests named, the one that says false and the one of one kind not
			local named = 0
			for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_ecosystem") do
				if string.find(line, "how their kinds came to stand", 1, true) then
					named += 1
					check.truthy(string.find(line, "MixedByChance: 2 forest(s)", 1, true), line)
					check.truthy(string.find(line, '"Wood", "Copse"', 1, true), line)
					check.equal(string.find(line, "Grove", 1, true), nil)
					check.equal(string.find(line, "Pines", 1, true), nil)
					check.truthy(string.find(line, '"ecosystem": false', 1, true))
				end
			end
			check.equal(named, 1)
		end)
	end)
end

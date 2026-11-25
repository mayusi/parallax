-- worldscatter.spec.luau (kit) — WHERE SCATTERED THINGS GO (kit/lib/worldscatter.luau; the owner's method list,
-- "Density map scattering" and "Poisson disk scattering"): a field that says how full each place is, and a sample
-- that keeps every piece its gap from the next, fills the area and follows the field.
-- Not claimed here: that a scattered place looks right. That is a built world, looked at.
local frk = require("../frk")
local test, check = frk.test, frk.check

local LaneLocks = require("../../lib/lanelocks")
local Scatter = require("../../lib/worldscatter")
local World = require("../../lib/world")

local PALETTE = { stone = { material = "Slate", color = { 90, 90, 90 } } }

-- a world of one scatter step: its Prop parts, the compile's errors
local function scattered(scatter: any, more: { any }?): ({ any }, { string })
	local build: { any } = {}
	for _, st in more or {} do
		table.insert(build, st)
	end
	scatter.name = scatter.name or "Stones"
	scatter.center = scatter.center or { 0, 0, 0 }
	scatter.area = scatter.area or { 200, 200 }
	scatter.part = scatter.part or { size = { 2, 2, 2 }, mat = "stone" }
	table.insert(build, { scatter = scatter })
	local _, parts, issues = World.compile({ name = "T", palette = PALETTE, build = build })
	local props, errors = {}, {}
	for _, q in parts do
		if q.name == "Prop" then
			table.insert(props, q)
		end
	end
	for _, i in issues do
		if i.severity == "error" then
			table.insert(errors, i.message)
		end
	end
	return props, errors
end

-- (the compiler's own generator: kit/lib/world.luau lcg)
local function lcg(seed: number): () -> number
	local state = seed % 2147483647
	return function()
		state = (state * 48271) % 2147483647
		return state / 2147483647
	end
end

local AREA = { 0, 0, 240, 240 }

-- the nearest other piece to each piece, and whether any two stand closer than the wider of their gaps
local function tooClose(pts: { { number } }): number
	local bad = 0
	for i = 1, #pts do
		for j = i + 1, #pts do
			local a, b = pts[i], pts[j]
			local need = math.max(a[3], b[3])
			if (a[1] - b[1]) ^ 2 + (a[2] - b[2]) ^ 2 < need * need - 1e-9 then
				bad += 1
			end
		end
	end
	return bad
end

local function inBox(pts: { { number } }, x0: number, x1: number, z0: number, z1: number): number
	local n = 0
	for _, p in pts do
		if p[1] >= x0 and p[1] < x1 and p[2] >= z0 and p[2] < z1 then
			n += 1
		end
	end
	return n
end

return function()
	test.suite("Scattering by a density field", function()
		test.case("what is wrong with a density is said", function()
			local function wrong(density: any, text: string)
				local problems = Scatter.problems(density)
				check.truthy(#problems >= 1)
				check.truthy(string.find(table.concat(problems, " | "), text, 1, true), table.concat(problems, " | "))
			end
			check.equal(#Scatter.problems({ gap = 6 }), 0)
			check.equal(#Scatter.problems({
				gap = 6,
				noise = { scale = 60, seed = 3, floor = 0.1 },
				spots = { { at = { 0, 0 }, radius = 40, weight = 0.5 } },
				away = { { at = { 10, 10 }, radius = 8 } },
				map = { origin = { -40, -40 }, cell = 20, rows = { "0139", "0259", "0009", "9999" } },
			}), 0)
			wrong(true, '"density" is {')
			wrong({}, "density.gap")
			wrong({ gap = 0 }, "density.gap")
			wrong({ gap = 6, gaps = 2 }, "density.gaps")
			wrong({ gap = 6, noise = { scale = 1 } }, "density.noise is")
			wrong({ gap = 6, noise = { scale = 40, floor = 1 } }, "density.noise.floor")
			wrong({ gap = 6, noise = { scale = 40, seed = 1.5 } }, "density.noise.seed")
			wrong({ gap = 6, spots = {} }, "density.spots is a list")
			wrong({ gap = 6, spots = { { at = { 0, 0 } } } }, "density.spots[1]")
			wrong({ gap = 6, spots = { { at = { 0, 0 }, radius = 10, weight = 2 } } }, "spots[1].weight")
			wrong({ gap = 6, away = { { at = { 0 }, radius = 10 } } }, "density.away[1]")
			wrong({ gap = 6, map = { origin = { 0, 0 }, cell = 8 } }, "density.map is")
			-- a typo inside is said (a "sead" was a seed of 1 without a word)
			wrong({ gap = 6, noise = { scale = 40, sead = 3 } }, "density.noise.sead")
			wrong({ gap = 6, spots = { { at = { 0, 0 }, radius = 10, wieght = 0.5 } } }, "density.spots[1].wieght")
			wrong({ gap = 6, away = { { at = { 0, 0 }, radius = 10, weight = 0.5 } } }, "density.away[1].weight")
			-- a seed the lattice cannot tell from another; more spots than a candidate should ask
			wrong({ gap = 6, noise = { scale = 40, seed = 70000 } }, "density.noise.seed")
			wrong({ gap = 6, noise = { scale = 40, seed = -1 } }, "density.noise.seed")
			check.equal(#Scatter.problems({ gap = 6, noise = { scale = 40, seed = 65535 } }), 0)
			local many = {}
			for i = 1, 65 do
				many[i] = { at = { i, 0 }, radius = 5 }
			end
			wrong({ gap = 6, spots = many }, "64 at most")
			wrong({ gap = 6, map = { origin = { 0, 0 }, cell = 8, rows = { "01a" } } }, "rows[1] is a string of digits")
			wrong({ gap = 6, map = { origin = { 0, 0 }, cell = 8, rows = { "012", "01" } } }, "every row the same")
			wrong({ gap = 6, map = { origin = { 0, 0 }, cell = 8, rows = { "000", "000" } } }, "0 everywhere")
		end)

		test.case("the field: full at a spot, nothing in a clearing, a painted grid read between its cells", function()
			local spot = Scatter.field({ gap = 6, spots = { { at = { 10, 20 }, radius = 40 } } })
			check.equal(spot(10, 20), 1)
			check.truthy(math.abs(spot(30, 20) - 0.5) < 1e-9) -- (half way out: half)
			check.equal(spot(50, 20), 0)
			check.equal(spot(10, 61), 0)
			check.truthy(spot(20, 20) > spot(30, 20) and spot(30, 20) > spot(45, 20))
			check.truthy(math.abs(spot(20, 20) - 0.84375) < 1e-9) -- (eased, not straight: a quarter out is 27/32)
			-- two spots: the fuller of the two, a weight caps one
			local two = Scatter.field({
				gap = 6,
				spots = { { at = { 0, 0 }, radius = 40 }, { at = { 100, 0 }, radius = 40, weight = 0.4 } },
			})
			check.equal(two(0, 0), 1)
			check.truthy(math.abs(two(100, 0) - 0.4) < 1e-9)
			check.equal(two(50, 0), 0)
			-- (where two spots lie over each other: the fuller one, not their sum)
			local over = Scatter.field({
				gap = 6,
				spots = { { at = { 0, 0 }, radius = 40, weight = 0.4 }, { at = { 0, 0 }, radius = 40, weight = 0.3 } },
			})
			check.truthy(math.abs(over(0, 0) - 0.4) < 1e-9)
			-- a clearing: nothing inside, back to full a third of its radius further out
			local away = Scatter.field({ gap = 6, away = { { at = { 0, 0 }, radius = 30 } } })
			check.equal(away(0, 0), 0)
			check.equal(away(29, 0), 0)
			check.truthy(math.abs(away(35, 0) - 0.5) < 1e-9)
			check.equal(away(40, 0), 1)
			check.equal(away(0, 90), 1)
			-- a painted grid: a cell's middle is its digit, between two middles it slopes, off the grid is nothing
			local map = Scatter.field({
				gap = 6,
				map = { origin = { 0, 0 }, cell = 10, rows = { "09", "90" } },
			})
			check.equal(map(5, 5), 0)
			check.equal(map(15, 5), 1)
			check.equal(map(5, 15), 1)
			check.equal(map(15, 15), 0)
			check.truthy(math.abs(map(10, 5) - 0.5) < 1e-9)
			check.truthy(math.abs(map(10, 10) - 0.5) < 1e-9)
			check.truthy(math.abs(map(5, 12.5) - 0.75) < 1e-9) -- (between two rows: three quarters of the way south)
			check.truthy(math.abs(map(12.5, 5) - 0.75) < 1e-9)
			check.equal(map(1, 15), 1) -- (the outer half of an edge cell: its own digit)
			check.equal(map(-1, 5), 0)
			check.equal(map(15, 21), 0)
			check.equal(map(21, 5), 0) -- (off the grid beside a full cell: still nothing)
			check.equal(map(5, 21), 0)
			-- they multiply
			local both = Scatter.field({
				gap = 6,
				spots = { { at = { 15, 5 }, radius = 20, weight = 0.5 } },
				map = { origin = { 0, 0 }, cell = 10, rows = { "09", "90" } },
			})
			check.truthy(math.abs(both(15, 5) - 0.5) < 1e-9)
			check.equal(both(5, 5), 0)
		end)

		test.case("noise: the same for the same seed, smooth, and it reaches both nothing and full", function()
			local a = Scatter.field({ gap = 6, noise = { scale = 50, seed = 4 } })
			local b = Scatter.field({ gap = 6, noise = { scale = 50, seed = 4 } })
			local c = Scatter.field({ gap = 6, noise = { scale = 50, seed = 5 } })
			local low, high, differs, steepest = 1, 0, 0, 0
			for x = -300, 300, 7 do
				for z = -300, 300, 7 do
					local v = a(x, z)
					check.truthy(v >= 0 and v <= 1)
					check.equal(v, b(x, z))
					differs += if math.abs(v - c(x, z)) > 0.05 then 1 else 0
					low, high = math.min(low, v), math.max(high, v)
					steepest = math.max(steepest, math.abs(a(x + 1, z) - v))
				end
			end
			check.equal(low, 0)
			check.equal(high, 1)
			check.truthy(differs > 2000) -- (another seed is another field)
			check.truthy(steepest < 0.12) -- (a stud moves it a little: clumps 50 studs across, not salt and pepper)
			-- a floor: never under it
			local floored = Scatter.field({ gap = 6, noise = { scale = 50, seed = 4, floor = 0.3 } })
			local least = 1
			for x = -300, 300, 7 do
				least = math.min(least, floored(x, 13))
			end
			check.truthy(least >= 0.3)
			-- (the floor lifts the whole field: floor + (1 - floor) x the noise, not a cut-off)
			for x = -300, 300, 7 do
				check.truthy(math.abs(floored(x, 13) - (0.3 + 0.7 * a(x, 13))) < 1e-9)
			end
			check.truthy(math.abs(least - 0.3) < 1e-9)
		end)

		test.case("the sample: no two pieces closer than their gap, all inside, the same for the same seed", function()
			local pts = Scatter.sample(AREA, { gap = 8 }, lcg(7))
			check.truthy(#pts > 300)
			check.equal(tooClose(pts), 0)
			for _, p in pts do
				check.truthy(p[1] >= -120 and p[1] <= 120 and p[2] >= -120 and p[2] <= 120)
				check.equal(p[3], 8)
			end
			local again = Scatter.sample(AREA, { gap = 8 }, lcg(7))
			check.equal(#again, #pts)
			check.equal(again[#again][1], pts[#pts][1])
			local other = Scatter.sample(AREA, { gap = 8 }, lcg(8))
			check.truthy(other[1][1] ~= pts[1][1])
		end)

		test.case("the area is FULL: nearly no place is left where one more piece would fit", function()
			local pts = Scatter.sample(AREA, { gap = 8 }, lcg(7))
			local probes, open = 0, 0
			for x = -116, 116, 4 do
				for z = -116, 116, 4 do
					probes += 1
					local near = false
					for _, p in pts do
						if (p[1] - x) ^ 2 + (p[2] - z) ^ 2 < 64 then
							near = true
							break
						end
					end
					open += if near then 0 else 1
				end
			end
			-- (a typed count of darts with 30 tries each left a fifth of such an area open)
			check.truthy(open / probes < 0.01)
			-- ... and the pieces cover what a full random spread does: near half the ground at half a gap each
			local cover = #pts * math.pi * 16 / (240 * 240)
			check.truthy(cover > 0.47 and cover < 0.6)
		end)

		test.case(
			"the count follows the field: half the field, about half the pieces; a sparse place thinned",
			function()
				-- a painted grid: the west third full, the middle third half, the east third a twentieth
				local density = {
					gap = 6,
					map = { origin = { -180, -120 }, cell = 120, rows = { "950", "950" } },
				}
				-- (cells' middles at x -120, 0, 120: sampled well inside each cell's flat half)
				local flat = {
					gap = 6,
					map = {
						origin = { -180, -120 },
						cell = 20,
						rows = table.create(12, "999999555555000000"),
					},
				}
				local pts = Scatter.sample({ 0, 0, 360, 240 }, flat, lcg(3))
				check.equal(tooClose(pts), 0)
				local full = inBox(pts, -170, -70, -110, 110)
				local half = inBox(pts, -50, 50, -110, 110)
				local none = inBox(pts, 70, 170, -110, 110)
				check.truthy(full > 250)
				check.truthy(half / full > 0.4 and half / full < 0.62)
				check.equal(none, 0)
				-- wider apart where it is half: sqrt(9 / 5) gaps
				for _, p in pts do
					if p[1] > -50 and p[1] < 50 then
						check.truthy(math.abs(p[3] - 6 * math.sqrt(9 / 5)) < 1e-6)
					end
				end
				-- a field of a fiftieth: the gap stops widening at 3 gaps and chance thins the rest
				local sparse = Scatter.sample(
					{ 0, 0, 400, 400 },
					{ gap = 6, spots = { { at = { 0, 0 }, radius = 100000, weight = 0.02 } } },
					lcg(5)
				)
				local dense = Scatter.sample({ 0, 0, 400, 400 }, { gap = 6 }, lcg(5))
				check.truthy(#sparse > 0)
				check.truthy(#sparse / #dense > 0.008 and #sparse / #dense < 0.04)
				check.equal(tooClose(sparse), 0)
				for _, p in sparse do
					check.equal(p[3], 18)
				end
				local _ = density
			end
		)

		test.case("a spot in a wide empty land is still filled; where nothing may stand, nothing does", function()
			-- (a candidate that lands in the clearing is no sign the spot is full: 99.7% of this area is empty)
			local pts = Scatter.sample(
				{ 0, 0, 2000, 2000 },
				{ gap = 6, spots = { { at = { 300, -200 }, radius = 60 } } },
				lcg(1)
			)
			check.truthy(#pts >= 40)
			for _, p in pts do
				check.truthy((p[1] - 300) ^ 2 + (p[2] + 200) ^ 2 < 3600)
			end
			-- (candidates are thrown at the spot's own box: it ends because the spot is full, not for want of tries)
			local _, how = Scatter.sample(
				{ 0, 0, 6000, 6000 },
				{ gap = 6, spots = { { at = { 300, -200 }, radius = 60 } } },
				lcg(1)
			)
			check.equal(how, nil)
			local wide = Scatter.sample(
				{ 0, 0, 6000, 6000 },
				{ gap = 6, spots = { { at = { 300, -200 }, radius = 60 } } },
				lcg(1)
			)
			check.equal(#wide, #pts) -- (the same spot in a land nine times the size: the same pieces)
			-- a painted grid that covers a corner of the area: thrown at the grid, not at the area
			local corner, ended = Scatter.sample(
				{ 0, 0, 6000, 6000 },
				{ gap = 6, map = { origin = { 1000, 1000 }, cell = 60, rows = { "99", "99" } } },
				lcg(1)
			)
			check.equal(ended, nil)
			check.truthy(#corner > 150)
			-- a spot outside the area: nothing, at once
			local nowhere = Scatter.sample(AREA, { gap = 6, spots = { { at = { 900, 900 }, radius = 30 } } }, lcg(1))
			check.equal(#nowhere, 0)
			-- the compiler's own word on a place (land, roads, water) is kept
			local dry = Scatter.sample(AREA, { gap = 8 }, lcg(7), function(x: number, _z: number): boolean
				return x < 0
			end)
			check.truthy(#dry > 120)
			for _, p in dry do
				check.truthy(p[1] < 0)
			end
		end)

		test.case("how a sample ended is said: over the most, or cut short", function()
			local pts, how = Scatter.sample({ 0, 0, 800, 800 }, { gap = 2 }, lcg(1))
			check.equal(how, "over")
			check.equal(#pts, 0) -- (nothing is handed back: it is an error, not a thin build)
			local _, fine = Scatter.sample(AREA, { gap = 8 }, lcg(1))
			check.equal(fine, nil)
			-- a thin field over a wide land that still comes to thousands (a fresh reader: it was built at a
			-- quarter of what the field says, because only the pieces left after thinning were counted)
			local thin, thinHow = Scatter.sample(
				{ 0, 0, 3000, 3000 },
				{ gap = 2, spots = { { at = { 0, 0 }, radius = 1000000, weight = 0.005 } } },
				lcg(1)
			)
			check.equal(thinHow, "over")
			check.equal(#thin, 0)
			-- ... the same thin field over a smaller land comes to under the most: built (what is counted is what
			-- the thinning keeps, not the many more it throws first)
			local few, fewHow = Scatter.sample(
				{ 0, 0, 1200, 1200 },
				{ gap = 2, spots = { { at = { 0, 0 }, radius = 1000000, weight = 0.005 } } },
				lcg(1)
			)
			check.truthy(fewHow ~= "over")
			check.truthy(#few > 500 and #few < Scatter.MOST)
			-- where nearly nothing may stand the tries run out before the strip is full: said, not passed off as full
			local strip, short = Scatter.sample(AREA, { gap = 8 }, lcg(7), function(x: number, _z: number): boolean
				return x < -119
			end)
			check.equal(short, "short")
			check.truthy(#strip > 10)
			-- ... and a candidate refused by its neighbours where nothing may stand is no sign the rest is full:
			-- a thin strip beside a full half is filled along its whole length
			local filled = Scatter.sample(
				{ 0, 0, 240, 240 },
				{ gap = 8 },
				lcg(3),
				function(x: number, _z: number): boolean
					return x < 0 or x > 112
				end
			)
			local inStrip = 0
			for _, q in filled do
				inStrip += if q[1] > 112 then 1 else 0
			end
			check.truthy(inStrip >= 20) -- (8 x 240 studs at gap 8: about 25 fit)
		end)

		test.case(
			"the compiler: a scatter with a density places what the field says, each piece its gap apart",
			function()
				local density = {
					gap = 6,
					spots = { { at = { -50, 0 }, radius = 45 } },
					away = { { at = { -50, 0 }, radius = 10 } },
				}
				local props, errors = scattered({ density = density, seed = 4 })
				check.equal(#errors, 0)
				check.truthy(#props >= 15)
				for i, a in props do
					-- inside the spot, outside the clearing
					local d = math.sqrt((a.pos[1] + 50) ^ 2 + a.pos[3] ^ 2)
					check.truthy(d < 45 and d >= 10)
					for j = i + 1, #props do
						local b = props[j]
						check.truthy((a.pos[1] - b.pos[1]) ^ 2 + (a.pos[3] - b.pos[3]) ^ 2 >= 36 - 1e-6)
					end
				end
				-- the same seed, the same stones; another seed, others
				local again = scattered({ density = density, seed = 4 })
				check.equal(#again, #props)
				check.equal(again[7].pos[1], props[7].pos[1])
				local other = scattered({ density = density, seed = 5 })
				check.truthy(other[1].pos[1] ~= props[1].pos[1])
				-- "avoid" is kept (the compiler's own word on a place)
				local kept = scattered({ density = { gap = 6 }, seed = 4, avoid = { { 0, 0, 60 } } })
				check.truthy(#kept > 200)
				for _, a in kept do
					check.truthy(a.pos[1] ^ 2 + a.pos[3] ^ 2 >= 3600 - 1e-6)
				end
			end
		)

		test.case("the compiler: what cannot be built is said", function()
			local function wrong(scatter: any, text: string)
				local props, errors = scattered(scatter)
				check.equal(#props, 0)
				check.equal(#errors >= 1, true)
				check.truthy(string.find(table.concat(errors, " | "), text, 1, true), table.concat(errors, " | "))
			end
			wrong({ density = { gap = 6 }, count = 30 }, 'has no "count"')
			wrong({ density = { gap = 6 }, gap = 20 }, "says its gap there")
			wrong({ density = { gap = 6, nois = { scale = 40 } } }, "density.nois")
			wrong({ density = true }, '"density" is {')
			-- two pieces at the least gap would stand in each other: each is turned any way round, so the gap is
			-- held to the widest piece's DIAGONAL (a fresh reader: held to its side, 491 pairs of 584 stood in
			-- each other), and of a size range to the larger end axis by axis
			wrong({ density = { gap = 2.8 } }, "under the widest piece's diagonal (2.83 studs") -- (2 x 2: 2.83)
			wrong(
				{ density = { gap = 6 }, part = { size = { { 1, 1, 8 }, { 6, 2, 3 } }, mat = "stone" } },
				"a piece 6 x 8"
			)
			wrong(
				{ density = { gap = 9.9 }, part = { size = { { 1, 1, 8 }, { 6, 2, 3 } }, mat = "stone" } },
				"diagonal (10 studs"
			)
			local turned, none = scattered({
				density = { gap = 10 },
				seed = 3,
				part = { size = { { 1, 1, 8 }, { 6, 2, 3 } }, mat = "stone" },
			})
			check.equal(#none, 0)
			check.truthy(#turned > 100)
			local sizes: { [number]: boolean } = {}
			for i, a in turned do
				sizes[math.floor(a.size[1] * 100)] = true
				for j = i + 1, #turned do
					local b = turned[j]
					-- (no two can touch however they are turned: their middles are a diagonal apart or more)
					local reach = (math.sqrt(a.size[1] ^ 2 + a.size[3] ^ 2) + math.sqrt(b.size[1] ^ 2 + b.size[3] ^ 2))
						/ 2
					check.truthy((a.pos[1] - b.pos[1]) ^ 2 + (a.pos[3] - b.pos[3]) ^ 2 >= reach * reach - 1e-6)
				end
			end
			local different = 0
			for _ in sizes do
				different += 1
			end
			check.truthy(different > 50) -- (each piece its own size out of the range)
			check.equal(#select(2, scattered({ density = { gap = 2.83 } })), 0)
			-- "density" is a scatter's and a forest's word: on another step it is said, not dropped
			local _, _, issues = World.compile({
				name = "T",
				palette = PALETTE,
				build = {
					{
						rocks = {
							name = "Crag",
							center = { 0, 0, 0 },
							area = { 60, 60 },
							count = 9,
							density = { gap = 6 },
						},
					},
				},
			})
			local said = false
			for _, i in issues do
				said = said
					or (
						i.severity == "error"
						and string.find(i.message, "a scatter's and a forest's word", 1, true) ~= nil
					)
			end
			check.truthy(said)
			-- thousands of pieces: a typo in the gap
			wrong({ density = { gap = 3 }, area = { 900, 900 } }, "over 4000 pieces")
			-- a field that is 0 wherever a piece may stand
			wrong(
				{ density = { gap = 6, spots = { { at = { 0, 0 }, radius = 30 } } }, avoid = { { 0, 0, 40 } } },
				"places nothing"
			)
			-- no density and no count is still the old error; "density": false is the even count
			wrong({}, "scatter count must be")
			local even, errors = scattered({ density = false, count = 25, seed = 2 })
			check.equal(#errors, 0)
			check.equal(#even, 25)
		end)

		test.case("the compiler: a scatter cut short is said (a warning), and built", function()
			-- (all but the corners of the area refused: the tries run out before the corners are full)
			local _, parts, issues = World.compile({
				name = "T",
				palette = PALETTE,
				build = {
					{
						scatter = {
							name = "Stones",
							center = { 0, 0, 0 },
							area = { 240, 240 },
							avoid = { { 0, 0, 166 } },
							density = { gap = 8 },
							part = { size = { 2, 2, 2 }, mat = "stone" },
						},
					},
				},
			})
			local said, props = false, 0
			for _, i in issues do
				check.truthy(i.severity ~= "error", i.message)
				said = said or (i.severity == "warn" and string.find(i.message, "cut short at", 1, true) ~= nil)
			end
			for _, q in parts do
				props += if q.name == "Prop" then 1 else 0
			end
			check.truthy(said)
			check.truthy(props >= 1)
			-- a scatter that fills its area says nothing of the kind
			local _, _, quiet = World.compile({
				name = "T",
				palette = PALETTE,
				build = {
					{
						scatter = {
							name = "Stones",
							center = { 0, 0, 0 },
							area = { 240, 240 },
							density = { gap = 8 },
							part = { size = { 2, 2, 2 }, mat = "stone" },
						},
					},
				},
			})
			for _, i in quiet do
				check.equal(string.find(i.message, "cut short", 1, true), nil)
			end
		end)

		test.case('the compiler: with "ground": true each piece stands on the land under it', function()
			local _, parts, issues = World.compile({
				name = "T",
				palette = PALETTE,
				terrain = { { ground = { center = { 0, 10, 0 }, size = { 256, 256 }, material = "Grass" } } },
				build = {
					{
						scatter = {
							name = "Stones",
							center = { 0, 0, 0 },
							area = { 120, 120 },
							ground = true,
							density = { gap = 8 },
							part = { size = { 2, 2, 2 }, mat = "stone" },
						},
					},
				},
			})
			for _, i in issues do
				check.truthy(i.severity ~= "error", i.message)
			end
			local n = 0
			for _, q in parts do
				if q.name == "Prop" then
					n += 1
					check.truthy(math.abs(q.pos[2] - 11) < 1e-6) -- (the land at 10, a piece 2 high standing on it)
				end
			end
			check.truthy(n > 80)
		end)

		-- a wood of mesh trees: one hidden trunk collider a tree (the meshes themselves are placed at runtime)
		local OAK = { oak = { kind = "tree", size = { 14, 30, 14 }, min = { -7, 0, -7 }, foliage = true } }
		local function wood(forest: any, terrain: any?): ({ any }, { string }, { string })
			forest.name = forest.name or "Wood"
			forest.center = forest.center or { 0, 0, 0 }
			forest.area = forest.area or { 300, 300 }
			forest.meshes = { "oak" }
			forest.trunk, forest.leaves = "stone", "stone"
			local _, parts, issues = World.compile(
				{ name = "T", palette = PALETTE, terrain = terrain, build = { { forest = forest } } },
				{ meshes = OAK }
			)
			local trunks, errors, warns = {}, {}, {}
			for _, q in parts do
				if q.name == "TrunkCollider" then
					table.insert(trunks, q)
				end
			end
			for _, i in issues do
				table.insert(if i.severity == "error" then errors else warns, i.message)
			end
			return trunks, errors, warns
		end

		test.case(
			"a forest by density: thick where the field is full, a glade where it says, each tree its gap apart",
			function()
				local density = {
					gap = 17,
					spots = { { at = { 0, 0 }, radius = 140 } },
					away = { { at = { 40, 0 }, radius = 30 } },
				}
				local trunks, errors = wood({ density = density, seed = 6, height = { 18, 26 } })
				check.equal(#errors, 0)
				check.truthy(#trunks >= 15)
				local inner, outer = 0, 0
				for i, a in trunks do
					local d = math.sqrt(a.pos[1] ^ 2 + a.pos[3] ^ 2)
					check.truthy(d < 140) -- (inside the wood's spot)
					check.truthy((a.pos[1] - 40) ^ 2 + a.pos[3] ^ 2 >= 900 - 1e-6) -- (none in the glade)
					inner += if d < 70 then 1 else 0
					outer += if d >= 99 then 1 else 0 -- (a ring of the same area as the inner disc)
					for j = i + 1, #trunks do
						local b = trunks[j]
						check.truthy((a.pos[1] - b.pos[1]) ^ 2 + (a.pos[3] - b.pos[3]) ^ 2 >= 289 - 1e-6)
					end
				end
				check.truthy(inner > outer * 2) -- (the wood thins toward its edge)
				-- each tree its own height out of the range (the collider is 0.6 of it)
				local heights: { [number]: boolean } = {}
				local n = 0
				for _, a in trunks do
					local H = a.size[1] / 0.6
					check.truthy(H >= 18 - 1e-6 and H <= 26 + 1e-6)
					if not heights[math.floor(H * 100)] then
						heights[math.floor(H * 100)] = true
						n += 1
					end
				end
				check.truthy(n > #trunks / 2)
				-- the same seed, the same wood
				local again = wood({ density = density, seed = 6, height = { 18, 26 } })
				check.equal(#again, #trunks)
				check.equal(again[5].pos[1], trunks[5].pos[1])
			end
		)

		test.case(
			"a forest by density stands on the land, keeps off what it is told to, and says what it cannot build",
			function()
				local land = { { ground = { center = { 0, 10, 0 }, size = { 512, 512 }, material = "Grass" } } }
				local trunks, errors = wood({
					density = { gap = 14 },
					area = { 200, 200 },
					ground = true,
					avoid = { { 0, 0, 50 } },
					height = { 20, 20 },
				}, land)
				check.equal(#errors, 0)
				check.truthy(#trunks > 60)
				for _, a in trunks do
					check.truthy(math.abs(a.pos[2] - (10 + 20 * 0.3)) < 1e-6) -- (its collider's middle: the land + 0.3 H)
					check.truthy(a.pos[1] ^ 2 + a.pos[3] ^ 2 >= 2500 - 1e-6)
				end
				local function wrong(forest: any, text: string)
					local built, errs = wood(forest)
					check.equal(#built, 0)
					check.truthy(#errs >= 1)
					check.truthy(string.find(table.concat(errs, " | "), text, 1, true), table.concat(errs, " | "))
				end
				wrong({ density = { gap = 17 }, count = 30, height = { 18, 26 } }, 'has no "count"')
				wrong({ density = { gap = 17 }, gap = 4, height = { 18, 26 } }, "says its gap there")
				wrong({ density = { gap = 19, noise = { scale = 60, sead = 2 } } }, "density.noise.sead")
				-- two crowns at the least gap: what two of the tallest keep by a count (half the tallest and 4)
				wrong({ density = { gap = 16.9 }, height = { 18, 26 } }, "(26 studs tall: half of it and 4, 17)")
				check.equal(#select(2, wood({ density = { gap = 17 }, height = { 18, 26 } })), 0)
				-- (a range written tallest first is the same range: a fresh reader got 30-stud trees 9 apart)
				wrong({ density = { gap = 16.9 }, height = { 26, 18 } }, "(26 studs tall: half of it and 4, 17)")
				-- a height that is no range is said (it crashed the compile)
				wrong({ density = { gap = 19 }, height = { 20 } }, '"height" is [lowest, tallest]')
				wrong({ count = 5, height = "tall" }, '"height" is [lowest, tallest]')
				wrong({ density = { gap = 19 }, area = { 2600, 2600 } }, "over 4000 trees")
				wrong(
					{ density = { gap = 19, spots = { { at = { 0, 0 }, radius = 30 } } }, avoid = { { 0, 0, 40 } } },
					"places nothing"
				)
				-- "density": false is the count, as before
				local counted, none = wood({ density = false, count = 12, seed = 2 })
				check.equal(#none, 0)
				check.equal(#counted, 12)
				-- cut short: said
				local _, _, warns = wood({ density = { gap = 19 }, area = { 240, 240 }, avoid = { { 0, 0, 166 } } })
				check.truthy(string.find(table.concat(warns, " | "), "cut short at", 1, true))
			end
		)

		test.case("what a density places is IN the model the game loads, under its step's name", function()
			-- (a fresh reader: the density way left the step loop early, before the step's group was made - the
			-- checks counted 132 stones and 2,772 tree parts, and the model had none of them)
			local function inModel(step: any, terrain: any?): (number, number)
				local model, parts, issues = World.compile({
					name = "T",
					palette = PALETTE,
					terrain = terrain,
					build = { step },
				})
				for _, i in issues do
					check.truthy(i.severity ~= "error", i.message)
				end
				local kind = next(step)
				local name = step[kind].name
				local held = 0
				local function count(node: any)
					for _, c in node.Children or {} do
						if c.ClassName == "Part" or c.ClassName == "MeshPart" or c.ClassName == "WedgePart" then
							held += 1
						end
						count(c)
					end
				end
				for _, c in model.Children do
					if c.Name == name then
						count(c)
					end
				end
				return #parts, held
			end
			for _, step in
				{
					{
						scatter = {
							name = "Stones",
							center = { 0, 0, 0 },
							area = { 100, 100 },
							density = { gap = 8 },
							part = { size = { 2, 2, 2 }, mat = "stone" },
						},
					},
					{
						scatter = {
							name = "Stones",
							center = { 0, 0, 0 },
							area = { 100, 100 },
							count = 20,
							part = { size = { 2, 2, 2 }, mat = "stone" },
						},
					},
					{
						forest = {
							name = "Wood",
							center = { 0, 0, 0 },
							area = { 120, 120 },
							density = { gap = 19 },
							trunk = "stone",
							leaves = "stone",
						},
					},
					{
						forest = {
							name = "Wood",
							center = { 0, 0, 0 },
							area = { 120, 120 },
							count = 8,
							trunk = "stone",
							leaves = "stone",
						},
					},
				} :: { any }
			do
				local made, held = inModel(step)
				check.truthy(made >= 8)
				check.equal(held, made)
			end
		end)

		test.case(
			"a forest of built trees by density: on the land, in its styles, some in the second canopy",
			function()
				local pal = {
					bark = { material = "Wood", color = { 90, 70, 50 } },
					leaf = { material = "Grass", color = { 60, 110, 50 } },
					gold = { material = "Grass", color = { 200, 150, 40 } },
				}
				-- (rolling land, 60 studs from its hollows to its tops: a tree not set on ITS ground is under it or in the air)
				local ROLLING = {
					center = { 0, 40, 0 },
					size = { 512, 512 },
					material = "Grass",
					noise = { amplitude = 30, scale = 120, seed = 2 },
				}
				local function built(density: any, count: number?): { any }
					local _, parts, issues = World.compile({
						name = "T",
						palette = pal,
						terrain = { { ground = ROLLING } },
						build = {
							{
								forest = {
									name = "Wood",
									center = { 0, 0, 0 },
									area = { 200, 200 },
									ground = true,
									height = { 18, 24 },
									styles = { "oak", "dead" },
									trunk = "bark",
									leaves = "leaf",
									leavesAlt = "gold",
									altShare = 0.5,
									density = density,
									count = count,
									seed = 3,
								},
							},
						},
					})
					for _, i in issues do
						check.truthy(i.severity ~= "error", i.message)
					end
					return parts
				end
				local function read(parts: { any }): (number, number, number, number)
					local lowest, green, golden, trunks = math.huge, 0, 0, 0
					for _, q in parts do
						if q.name == "Trunk" then
							trunks += 1
							lowest = math.min(lowest, q.pos[2] - q.size[2] / 2, q.pos[2] - q.size[1] / 2)
						elseif q.name == "Canopy" then
							green += if q.color[1] == 60 then 1 else 0
							golden += if q.color[1] == 200 then 1 else 0
						end
					end
					return lowest, green, golden, trunks
				end
				local low, green, golden, trunks = read(built({ gap = 16 }, nil))
				local lowC, greenC, goldenC = read(built(nil, 30))
				check.truthy(trunks > 60)
				check.truthy(green > 0 and golden > 0) -- (both canopies)
				check.truthy(greenC > 0 and goldenC > 0)
				local _ = low
				local _ = lowC
				-- every trunk piece stands on the land under it: its middle from the ground to a tree's height over it
				local lowest, highest = math.huge, -math.huge
				for _, q in built({ gap = 16 }, nil) do
					if q.name == "Trunk" then
						local ground = World.groundHeight(ROLLING, q.pos[1], q.pos[3])
						lowest, highest = math.min(lowest, ground), math.max(highest, ground)
						check.truthy(q.pos[2] >= ground - 3 and q.pos[2] <= ground + 26)
					end
				end
				check.truthy(highest - lowest > 20) -- (the wood does stand on rolling land)
			end
		)

		test.case("the lock: scatters that together come to 40 pieces say where their pieces go", function()
			local function bp(...: any): any
				local build = {}
				for _, scatter in { ... } do
					table.insert(build, { scatter = scatter })
				end
				return { build = build }
			end
			check.equal(#LaneLocks.unsaidDensities(bp({ name = "Stones", count = 40 })), 1)
			check.equal(LaneLocks.unsaidDensities(bp({ name = "Stones", count = 40 }))[1], "Stones")
			check.equal(#LaneLocks.unsaidDensities(bp({ name = "Stones", count = 39 })), 0)
			-- one scatter of 60 cut into two of 30 is asked the same
			check.equal(#LaneLocks.unsaidDensities(bp({ name = "A", count = 30 }, { name = "B", count = 30 })), 2)
			check.equal(#LaneLocks.unsaidDensities(bp({ name = "A", count = 30 }, { name = "B", count = 9 })), 0)
			-- what has said its word is not counted, and not named
			local mixed = LaneLocks.unsaidDensities(
				bp({ name = "A", count = 30 }, { name = "B", count = 400, density = false }, { name = "C", count = 12 })
			)
			check.equal(#mixed, 2)
			check.equal(mixed[1], "A")
			check.equal(mixed[2], "C")
			check.equal(#LaneLocks.unsaidDensities(bp({ name = "Stones", count = 400, density = false })), 0)
			check.equal(#LaneLocks.unsaidDensities(bp({ name = "Stones", density = { gap = 6 } })), 0)
			check.equal(#LaneLocks.unsaidDensities({}), 0)
			-- a forest is a scatter of trees (10 when it says no count), counted with the scatters
			local function trees(...: any): any
				local build = {}
				for _, forest in { ... } do
					table.insert(build, { forest = forest })
				end
				return { build = build }
			end
			check.equal(#LaneLocks.unsaidDensities(trees({ name = "Wood", count = 40 })), 1)
			check.equal(#LaneLocks.unsaidDensities(trees({ name = "Wood", count = 39 })), 0)
			check.equal(
				#LaneLocks.unsaidDensities(trees({ name = "A" }, { name = "B" }, { name = "C" }, { name = "D" })),
				4
			)
			check.equal(#LaneLocks.unsaidDensities(trees({ name = "A" }, { name = "B" }, { name = "C" })), 0)
			check.equal(#LaneLocks.unsaidDensities(trees({ name = "Wood", density = { gap = 14 } })), 0)
			check.equal(#LaneLocks.unsaidDensities(trees({ name = "Wood", count = 90, density = false })), 0)
			local both = {
				build = { { forest = { name = "Wood", count = 25 } }, { scatter = { name = "Stones", count = 15 } } },
			}
			check.equal(#LaneLocks.unsaidDensities(both), 2)
			local named = 0
			for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_scatter") do
				if string.find(line, "do not say where their pieces go", 1, true) then
					named += 1
					check.truthy(string.find(line, "EvenStones", 1, true))
					check.truthy(string.find(line, '"Boulders", "Pebbles"', 1, true)) -- (30 and 12: together 42)
					check.equal(string.find(line, "Cairns", 1, true), nil) -- ("density": false: it has said)
				end
			end
			check.equal(named, 1)
		end)
	end)
end

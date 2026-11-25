-- worldtownbend.spec.luau (kit) — a town's "bend" (kit/lib/worldtown.luau): the plan twisted round its square, each
-- block of houses moved and turned as ONE rigid piece, spread just far enough that no street is narrower than
-- planned. What the plan promises of a bent town, and what the compiler makes of one.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Town = require("../../lib/worldtown")
local World = require("../../lib/world")

local MATS = { street = "cobble", block = "pave", wall = "plaster", roof = "slate" }
local PALETTE = {
	cobble = { material = "Cobblestone", color = { 84, 82, 80 } },
	pave = { material = "Slate", color = { 98, 96, 94 } },
	plaster = { material = "Concrete", color = { 150, 140, 124 } },
	slate = { material = "Slate", color = { 58, 60, 68 } },
}
-- (three shapes of town the plan is used at: one gate, two, three)
local SHAPES = {
	{ area = { 256, 224 }, gates = { "S" } },
	{ area = { 320, 320 }, gates = { "S", "N" } },
	{ area = { 400, 320 }, gates = { "S", "E", "W" } },
}

local function spec(seed: number, shape: any, bend: number?, more: any?): any
	local s: any =
		{ center = { 0, 0, 0 }, area = shape.area, seed = seed, gates = shape.gates, mats = MATS, bend = bend }
	for k, v in more or {} do
		s[k] = v
	end
	return s
end

local function errorsOf(issues: { any }): string
	local out = {}
	for _, i in issues do
		if i.severity == "error" then
			table.insert(out, i.message)
		end
	end
	return table.concat(out, " | ")
end

local function near(a: number, b: number, eps: number?): boolean
	return math.abs(a - b) <= (eps or 1e-6)
end

local function rectQuad(r: any): { { number } }
	return { { r.x0, r.z0 }, { r.x1, r.z0 }, { r.x1, r.z1 }, { r.x0, r.z1 } }
end

local function rectsApart(a: any, b: any): number
	local dx = math.max(a.x0 - b.x1, b.x0 - a.x1, 0)
	local dz = math.max(a.z0 - b.z1, b.z0 - a.z1, 0)
	return math.sqrt(dx * dx + dz * dz)
end

local function side(q: { { number } }, i: number): number
	local a, b = q[i], q[i % 4 + 1]
	return math.sqrt((a[1] - b[1]) ^ 2 + (a[2] - b[2]) ^ 2)
end

-- every plan this spec walks: (plan, its straight twin, the shape, the seed, the bend)
local function eachBent(body: (any, any, any, number, number) -> ())
	for _, shape in SHAPES do
		for _, bend in { 3, 6, 8 } do
			for seed = 1, 6 do
				local bent = Town.plan(spec(seed, shape, bend))
				local straight = Town.plan(spec(seed, shape, nil))
				body(bent, straight, shape, seed, bend)
			end
		end
	end
end

return function()
	test.suite("Town bend: the geometry it stands on", function()
		test.case("its turn is the compiler's turn (one convention, never two)", function()
			for _, c in { { 10, 0, 0, 0, 90 }, { 7, 3, 2, 1, 37 }, { -4, 9, 5, 5, -120 } } do
				local ax, az = Town.turnPoint(c[1], c[2], c[3], c[4], c[5])
				local bx, bz = World.turnPoint(c[1], c[2], c[3], c[4], c[5])
				check.truthy(near(ax, bx, 1e-9) and near(az, bz, 1e-9))
			end
		end)

		test.case("how far apart two quads stand: touching and overlapping are 0", function()
			local a = rectQuad({ x0 = 0, x1 = 10, z0 = 0, z1 = 10 })
			check.truthy(near(Town.quadsApart(a, rectQuad({ x0 = 14, x1 = 20, z0 = 0, z1 = 10 })), 4))
			check.truthy(near(Town.quadsApart(a, rectQuad({ x0 = 13, x1 = 20, z0 = 14, z1 = 20 })), 5)) -- corner to corner
			check.equal(Town.quadsApart(a, rectQuad({ x0 = 10, x1 = 20, z0 = 0, z1 = 10 })), 0)
			check.equal(Town.quadsApart(a, rectQuad({ x0 = 5, x1 = 20, z0 = 5, z1 = 20 })), 0)
			check.equal(Town.quadsApart(a, rectQuad({ x0 = 2, x1 = 4, z0 = 2, z1 = 4 })), 0) -- one inside the other
			-- a square turned 45 degrees, its corner pointing at the first one's side
			local d = Town.quadOf({ x0 = 20, x1 = 30, z0 = 0, z1 = 10 }, 25, 5, 45)
			check.truthy(near(Town.quadsApart(a, d), 15 - math.sqrt(50), 1e-9))
			check.truthy(near(Town.quadsApart(d, a), 15 - math.sqrt(50), 1e-9))
		end)

		test.case("a rect moved as a rigid piece keeps its sides and its corner order", function()
			local r = { x0 = -10, x1 = 30, z0 = 4, z1 = 20 }
			local q = Town.quadOf(r, 100, -50, 33)
			check.truthy(
				near(side(q, 1), 40) and near(side(q, 2), 16) and near(side(q, 3), 40) and near(side(q, 4), 16)
			)
			check.truthy(near((q[1][1] + q[3][1]) / 2, 100) and near((q[1][2] + q[3][2]) / 2, -50))
			local same = Town.quadOf(r, 10, 12, 0)
			for i, c in rectQuad(r) do
				check.truthy(near(same[i][1], c[1]) and near(same[i][2], c[2]))
			end
		end)

		test.case("a line of sight crosses a house or it does not", function()
			local q = rectQuad({ x0 = 0, x1 = 10, z0 = 0, z1 = 10 })
			check.truthy(Town.segmentHits({ -5, 5 }, { 15, 5 }, q))
			check.truthy(Town.segmentHits({ 5, 5 }, { 50, 50 }, q)) -- starts inside
			check.truthy(Town.segmentHits({ -5, -4 }, { 4, 5 }, q)) -- clips a corner
			check.falsy(Town.segmentHits({ -5, 11 }, { 15, 11 }, q))
			check.falsy(Town.segmentHits({ -5, -5 }, { -1, 20 }, q))
			check.falsy(Town.segmentHits({ 20, 0 }, { 30, 10 }, q))
		end)
	end)

	test.suite("Town bend: what the plan promises", function()
		test.case('no "bend" and "bend": 0 are the straight town, to the last step', function()
			for _, shape in SHAPES do
				local a = Town.plan(spec(3, shape, nil))
				local b = Town.plan(spec(3, shape, 0))
				check.equal(a.bent, nil)
				check.equal(b.bent, nil)
				check.equal(b.bend, 0)
				local sa, sb = Town.steps(a, spec(3, shape, nil)), Town.steps(b, spec(3, shape, 0))
				check.equal(#sa, #sb)
				for i, st in sa do
					local ka, va = next(st)
					local kb, vb = next(sb[i])
					check.equal(ka, kb)
					check.equal(va.name, vb.name)
					check.equal(va.turn, nil)
					check.equal(vb.turn, nil)
					if va.center then
						check.equal(va.center[1], vb.center[1])
						check.equal(va.center[3], vb.center[3])
					end
				end
				local ra = Town.record("T", a)
				check.equal(ra.lots[1].quad, nil)
				check.equal(ra.streets[1].line, nil)
				check.equal(ra.bend, 0)
			end
		end)

		test.case('what "bend" refuses: a word, a negative, more than the most', function()
			check.equal(Town.BEND_MAX, 8)
			for _, bad in { "a lot", -1, 9, 12, 0 / 0, true } :: { any } do
				local plan = Town.plan(spec(1, SHAPES[1], bad))
				check.truthy(string.find(errorsOf(plan.issues), '"bend" is 0', 1, true))
				check.equal(plan.bent, nil)
			end
			check.equal(errorsOf(Town.plan(spec(1, SHAPES[1], 8)).issues), "")
		end)

		test.case(
			"a bent town is the SAME plan: same lots, same streets, same graph - only where they stand",
			function()
				eachBent(function(bent, straight)
					check.equal(errorsOf(bent.issues), "")
					check.equal(#bent.lots, #straight.lots)
					check.equal(#bent.blocks, #straight.blocks)
					check.equal(#bent.streets, #straight.streets)
					for i, lot in bent.lots do
						check.equal(lot.type, straight.lots[i].type)
						check.equal(lot.front, straight.lots[i].front)
						check.equal(lot.rect.x0, straight.lots[i].rect.x0)
					end
					local mb, ms = Town.measure(bent), Town.measure(straight)
					check.equal(mb.loops, ms.loops)
					check.equal(mb.deadEnds, ms.deadEnds)
					check.equal(mb.tees, ms.tees)
					check.equal(mb.crossings, ms.crossings)
					check.equal(mb.cutOff, ms.cutOff)
				end)
			end
		)

		test.case(
			"every block is one rigid piece: its lots keep their sizes and their places to one another",
			function()
				eachBent(function(bent)
					local first: { [number]: any } = {}
					for _, lot in bent.lots do
						local q = Town.lotQuad(bent, lot)
						local r = lot.rect
						check.truthy(near(side(q, 1), r.x1 - r.x0, 1e-6) and near(side(q, 2), r.z1 - r.z0, 1e-6))
						check.truthy(near(side(q, 3), r.x1 - r.x0, 1e-6) and near(side(q, 4), r.z1 - r.z0, 1e-6))
						-- (a right angle at its first corner: not a sheared lot)
						local ux, uz = q[2][1] - q[1][1], q[2][2] - q[1][2]
						local vx, vz = q[4][1] - q[1][1], q[4][2] - q[1][2]
						check.truthy(math.abs(ux * vx + uz * vz) < 1e-6)
						local other = first[lot.block]
						if other then
							local oq = Town.lotQuad(bent, other)
							local was = math.sqrt((r.x0 - other.rect.x0) ^ 2 + (r.z0 - other.rect.z0) ^ 2)
							local is = math.sqrt((q[1][1] - oq[1][1]) ^ 2 + (q[1][2] - oq[1][2]) ^ 2)
							check.truthy(near(was, is, 1e-6))
						else
							first[lot.block] = lot
						end
					end
				end)
			end
		)

		test.case(
			"NO street is narrower than planned: two blocks never stand closer than the plan set them, nor any two of their houses",
			function()
				-- (what is promised is the gap BETWEEN TWO BLOCKS, which is a street's width where their fronts face.
				-- Two houses that do not face - one far up the street from the other - may come nearer as their blocks
				-- turn, never nearer than that gap. My first case asked every pair of houses to keep its own distance:
				-- more than the plan promises, and false.)
				local pairs, wider = 0, 0
				eachBent(function(bent)
					local reach = 0
					for _, st in bent.streets do
						reach = math.max(reach, st.width)
					end
					local narrowest = math.huge
					for _, st in bent.streets do
						narrowest = math.min(narrowest, st.width)
					end
					for i = 1, #bent.blocks do
						for j = i + 1, #bent.blocks do
							local was = rectsApart(bent.blocks[i], bent.blocks[j])
							local is = Town.quadsApart(bent.bent.blocks[i].quad, bent.bent.blocks[j].quad)
							if was <= reach * 1.5 then
								if is < was - 1e-6 then
									error(`blocks {i} and {j} stood {was} apart and stand {is}`, 0)
								end
								pairs += 1
								wider += if is > was + 0.5 then 1 else 0
							else -- (blocks that were never neighbours do not become ones)
								check.truthy(is >= narrowest)
							end
						end
					end
					for i = 1, #bent.lots do
						for j = i + 1, #bent.lots do
							local a, b = bent.lots[i], bent.lots[j]
							local gap = rectsApart(bent.blocks[a.block], bent.blocks[b.block])
							if a.block ~= b.block and gap <= reach * 1.5 then
								local is = Town.quadsApart(Town.lotQuad(bent, a), Town.lotQuad(bent, b))
								if is < gap - 1e-6 then
									error(`{a.name} and {b.name} stand {is} apart across a {gap}-stud street`, 0)
								end
							end
						end
					end
				end)
				check.truthy(pairs > 400)
				check.truthy(wider > pairs / 4) -- (and many stand farther: streets that widen, the bend is real)
			end
		)

		test.case(
			"the blocks turn by different angles, the most about one and a half times the bend; the streets stay as wide as planned",
			function()
				eachBent(function(bent, _, _, _, bend)
					local lo, hi = math.huge, -math.huge
					for _, b in bent.bent.blocks do
						lo, hi = math.min(lo, b.turn), math.max(hi, b.turn)
						check.truthy(math.abs(b.turn) <= bend * 1.75)
					end
					check.truthy(hi - lo > bend * 0.2) -- (not the whole town turned as one: that would be no bend)
					-- settled: a street is its planned width at its narrowest - 2.2 studs over on average in the worst of
					-- these towns (the first version, one spread for all, left a 12-stud lane 21 wide: over 8)
					check.truthy(bent.bent.wider.mean >= -1e-6 and bent.bent.wider.mean <= 3)
					check.truthy(bent.bent.rounds < Town.BEND_ROUNDS)
				end)
			end
		)

		test.case("the same seed bends the same way; another seed may twist the other way", function()
			local a = Town.plan(spec(5, SHAPES[2], 8))
			local b = Town.plan(spec(5, SHAPES[2], 8))
			for bi, blk in a.bent.blocks do
				check.equal(blk.turn, b.bent.blocks[bi].turn)
				check.equal(blk.x, b.bent.blocks[bi].x)
			end
			local signs = {}
			for seed = 1, 12 do
				signs[Town.plan(spec(seed, SHAPES[2], 8)).bent.sign] = true
			end
			check.truthy(signs[1] and signs[-1])
		end)

		test.case("the walk is measured on the town as it stands; a bent street is not one long view", function()
			eachBent(function(bent, straight)
				local g = Town.graph(bent)
				for _, ed in g.edges do
					local a, b = g.nodes[ed.a], g.nodes[ed.b]
					check.truthy(near(ed.length, math.sqrt((a.px - b.px) ^ 2 + (a.pz - b.pz) ^ 2), 1e-9))
				end
				local mb, ms = Town.measure(bent), Town.measure(straight)
				-- (the same town, turned block by block: a gate's walk to the square is within a fifth of the straight one's)
				for i, w in mb.walks do
					check.truthy(w.studs >= ms.walks[i].studs * 0.9)
					check.truthy(w.studs <= ms.walks[i].studs * 1.2)
				end
				check.equal(mb.bend, bent.bend)
				check.truthy(mb.wider.mean >= -1e-6 and mb.wider.most >= mb.wider.mean)
				check.truthy(mb.vista.length > 20 and mb.vista.length <= ms.vista.length * 1.2)
			end)
		end)

		test.case(
			"the landmark still closes the gate's street: in view from the main gate, straight or bent",
			function()
				-- (measured over these towns, not designed for: a main street is 32 wide and the twist is gentle near the
				-- square, so the sight line stays inside the street)
				for _, shape in SHAPES do
					for seed = 1, 12 do
						for _, bend in { 0, 4, 8 } do
							local sight = Town.landmarkSight(Town.plan(spec(seed, shape, bend)))
							if sight == nil then
								error("no landmark or no main street", 0)
							end
							check.truthy(sight.fromGate)
							check.truthy(sight.share > 0.9)
						end
					end
				end
			end
		)

		test.case("a line of sight that a house stands in is said: the landmark's sight is no constant", function()
			local plan = Town.plan(spec(3, SHAPES[1], 8))
			local landmark = nil
			for _, lot in plan.lots do
				if lot.landmark then
					landmark = lot
				end
			end
			-- stand a house across the square in front of the landmark: every other lot's quad is asked, so move one
			local other = nil
			for _, lot in plan.lots do
				if lot ~= landmark and lot.block ~= landmark.block then
					other = lot
					break
				end
			end
			local real = Town.lotQuad
			local q = real(plan, landmark)
			local cx, cz = (q[1][1] + q[3][1]) / 2, (q[1][2] + q[3][2]) / 2
			local S = plan.square
			local sx, sz = (S.x0 + S.x1) / 2, (S.z0 + S.z1) / 2
			Town.lotQuad = function(p: any, lot: any)
				if lot == other then -- a wide slab between the square's middle and the landmark
					local mx, mz = (cx + sx) / 2, (cz + sz) / 2
					return { { mx - 60, mz - 2 }, { mx + 60, mz - 2 }, { mx + 60, mz + 2 }, { mx - 60, mz + 2 } }
				end
				return real(p, lot)
			end
			local ok, sight = pcall(Town.landmarkSight, plan)
			Town.lotQuad = real
			check.truthy(ok)
			check.falsy(sight.fromGate)
			check.truthy(sight.share < 0.5)
		end)
	end)

	test.suite("Town bend: cases a fresh reader broke", function()
		test.case("a BIG town settles: 170 blocks, and the towns that were refused at any bend", function()
			-- (the first cap of 400 rounds refused every 960 x 960 town and told the blueprint to "bend less")
			local big = Town.plan(spec(1, { area = { 960, 960 }, gates = { "S", "W" } }, 8))
			check.equal(errorsOf(big.issues), "")
			check.truthy(#big.blocks > 120)
			check.truthy(big.bent.rounds < Town.BEND_ROUNDS / 2)
			check.equal(errorsOf(Town.plan(spec(1, { area = { 960, 960 }, gates = { "S", "W" } }, 0.5)).issues), "")
			for _, bend in { 3, 6, 8 } do
				local plan = Town.plan(
					spec(12, { area = { 640, 640 }, gates = { "W", "N" } }, bend, { square = { size = { 48, 48 } } })
				)
				check.equal(errorsOf(plan.issues), "")
			end
			for seed = 1, 4 do
				check.equal(
					errorsOf(Town.plan(spec(seed, { area = { 800, 600 }, gates = { "N", "E" } }, 8)).issues),
					""
				)
			end
		end)

		test.case("a street's middle line does not jump, and never runs through a block", function()
			-- (it jumped up to 18 studs between two points half a stud apart, and at bend 12 ran through houses)
			local function deepIn(q: { { number } }, x: number, z: number): boolean
				local pos, neg = false, false
				for i = 1, 4 do
					local a, b = q[i], q[i % 4 + 1]
					local d = (b[1] - a[1]) * (z - a[2]) - (b[2] - a[2]) * (x - a[1])
					local len = math.sqrt((b[1] - a[1]) ^ 2 + (b[2] - a[2]) ^ 2)
					pos = pos or d / len > 0.5
					neg = neg or d / len < -0.5
				end
				return not (pos and neg)
			end
			local samples = 0
			for _, shape in SHAPES do
				for seed = 1, 4 do
					local plan = Town.plan(spec(seed, shape, 8))
					for _, st in plan.streets do
						local line = Town.streetLine(plan, st, 0.5)
						local wall = string.sub(st.name, 1, 11) == "Wall street"
						for i, pt in line do
							samples += 1
							if i > 1 then
								local step = math.sqrt((pt[1] - line[i - 1][1]) ^ 2 + (pt[2] - line[i - 1][2]) ^ 2)
								if step > (if wall then 4 else 2) then
									error(`{st.name} steps {step} studs between two points half a stud apart`, 0)
								end
							end
							for _, b in plan.bent.blocks do
								if deepIn(b.quad, pt[1], pt[2]) then
									error(`{st.name}'s middle line runs through a block`, 0)
								end
							end
						end
					end
				end
			end
			check.truthy(samples > 20000)
		end)

		test.case(
			'"how much wider" counts the blocks that face each other across a street, not corner to corner',
			function()
				-- (the page said "+10.7 at most" where the widest street was +2.2: the rest was a crossing's diagonal)
				for _, shape in SHAPES do
					for seed = 1, 6 do
						local plan = Town.plan(spec(seed, shape, 8))
						local most, sum, n = 0, 0, 0
						for i = 1, #plan.blocks do
							for j = i + 1, #plan.blocks do
								local a, b = plan.blocks[i], plan.blocks[j]
								local facing = (a.x0 < b.x1 and b.x0 < a.x1) or (a.z0 < b.z1 and b.z0 < a.z1)
								local was = rectsApart(a, b)
								if facing and was <= 48 then
									local e = Town.quadsApart(plan.bent.blocks[i].quad, plan.bent.blocks[j].quad) - was
									most, sum, n = math.max(most, e), sum + e, n + 1
								end
							end
						end
						check.truthy(near(plan.bent.wider.most, most, 1e-6))
						check.truthy(near(plan.bent.wider.mean, sum / n, 1e-6))
					end
				end
			end
		)

		test.case("no block stands in the square, whatever the square's size", function()
			-- (a turned block's corner stood 0.6 studs inside it: one rect drawn in for the whole square has round corners)
			for _, more in { {}, { square = { size = { 140, 120 } } }, { square = { size = { 48, 48 } } } } do
				for seed = 1, 6 do
					local plan = Town.plan(spec(seed, SHAPES[3], 8, more))
					check.equal(errorsOf(plan.issues), "")
					local S = plan.square
					for _, b in plan.bent.blocks do
						for _, c in b.quad do
							local inX = c[1] > S.x0 + 0.05 and c[1] < S.x1 - 0.05
							local inZ = c[2] > S.z0 + 0.05 and c[2] < S.z1 - 0.05
							if inX and inZ then
								error(`a block's corner stands in the square at ({c[1]}, {c[2]})`, 0)
							end
						end
					end
				end
			end
		end)

		test.case(
			"a bent town's longest view runs out of a gate when it reaches the street's open end, else it does not",
			function()
				-- (it was called "ends inside the town" for every bent town)
				local open, closed = 0, 0
				for _, shape in SHAPES do
					for seed = 1, 10 do
						local m = Town.measure(Town.plan(spec(seed, shape, 6)))
						if m.vista.closed then
							closed += 1
						else
							open += 1
						end
					end
				end
				check.truthy(open > 0)
				check.truthy(closed > 0)
			end
		)

		test.case("a plan with a fault of its own is not bent on top of it", function()
			local plan = Town.plan(spec(1, SHAPES[1], 8, { streets = { main = 30 } }))
			local errs = errorsOf(plan.issues)
			check.truthy(errs ~= "")
			check.equal(plan.bent, nil)
			check.falsy(string.find(errs, "did not settle", 1, true))
		end)

		test.case("neighbouring seeds are different towns: the square moves, the twist turns both ways", function()
			-- (the random source's first draw barely moved from seed to seed: every seed under a thousand had its
			-- square a tenth west of the middle and its first house in the second wall colour)
			local middles, count = {}, 0
			for seed = 1, 12 do
				local S = Town.plan(spec(seed, SHAPES[2], nil)).square
				local key = `{(S.x0 + S.x1) / 2}:{(S.z0 + S.z1) / 2}`
				if not middles[key] then
					middles[key] = true
					count += 1
				end
			end
			check.truthy(count >= 5)
			local alt, plain = 0, 0
			for seed = 1, 12 do
				local s2 = spec(seed, SHAPES[1], nil, {
					mats = {
						street = "cobble",
						block = "pave",
						wall = "plaster",
						wallAlt = "brick",
						roof = "slate",
					},
				})
				local _, first = next(Town.steps(Town.plan(s2), s2)[3])
				for _, st in Town.steps(Town.plan(s2), s2) do
					local kind, v = next(st)
					if kind == "building" then
						first = v
						break
					end
				end
				if first.mat == "brick" then
					alt += 1
				else
					plain += 1
				end
			end
			check.truthy(alt > 0 and plain > 0)
		end)
	end)

	test.suite("Town bend: the town sets its own spawn pads", function()
		-- (a bent town carries its gate away from any typed coordinate: the kit's own bent fixture had its typed
		-- spawns inside a wall the first time it was checked)
		local function inAnyLot(plan: any, x: number, z: number): boolean
			for _, lot in plan.lots do
				if Town.segmentHits({ x - 3, z - 3 }, { x + 3, z + 3 }, Town.lotQuad(plan, lot)) then
					return true
				end
				if Town.segmentHits({ x - 3, z + 3 }, { x + 3, z - 3 }, Town.lotQuad(plan, lot)) then
					return true
				end
			end
			return false
		end

		test.case(
			"the pads stand inside the main gate, on the street, clear of every house - straight or bent",
			function()
				for _, shape in SHAPES do
					for _, bend in { 0, 3, 6, 8 } do
						for seed = 1, 6 do
							local plan = Town.plan(spec(seed, shape, bend, {
								spawns = 4,
								mats = { street = "cobble", wall = "plaster", roof = "slate", spawn = "pad" },
							}))
							check.equal(errorsOf(plan.issues), "")
							local spots = Town.spawnSpots(plan, 4)
							check.equal(#spots, 4)
							local gate = nil
							for _, nd in Town.graph(plan).nodes do
								if nd.kind == "gate" and nd.name == `{plan.mainGate} gate` then
									gate = nd
								end
							end
							check.truthy(gate ~= nil)
							for _, sp in spots do
								check.falsy(inAnyLot(plan, sp[1], sp[2])) -- (a 6-stud pad's two diagonals cross no lot)
								local far = math.sqrt((sp[1] - gate.px) ^ 2 + (sp[2] - gate.pz) ^ 2)
								check.truthy(far > 6 and far < 32)
							end
							-- a pair stands 8 studs apart, across the street
							check.truthy(
								near(
									math.sqrt((spots[1][1] - spots[2][1]) ^ 2 + (spots[1][2] - spots[2][2]) ^ 2),
									8,
									1e-6
								)
							)
						end
					end
				end
			end
		)

		test.case("the town's steps carry them, and the compiler makes them spawns", function()
			local s = spec(3, SHAPES[1], 8, {
				spawns = 2,
				mats = { street = "cobble", block = "pave", wall = "plaster", roof = "slate", spawn = "pad" },
			})
			local palette = table.clone(PALETTE)
			palette.pad = { material = "Neon", color = { 80, 220, 120 } }
			local _, parts, issues =
				World.compile({ name = "T", palette = palette, scale = "r6", build = { { town = s } } })
			check.equal(errorsOf(issues), "")
			local spawns = 0
			for _, p in parts do
				if p.spawn then
					spawns += 1
				end
			end
			check.equal(spawns, 2)
			-- one pad stands on the line; none without the word
			check.equal(#Town.spawnSpots(Town.plan(s), 1), 1)
			local none = 0
			for _, st in Town.steps(Town.plan(spec(3, SHAPES[1], 8)), spec(3, SHAPES[1], 8)) do
				if next(st) == "spawn" then
					none += 1
				end
			end
			check.equal(none, 0)
		end)

		test.case('what "spawns" refuses: not a count, more than eight, no palette entry for the pads', function()
			for _, bad in { 0, 9, 2.5, "two", true } :: { any } do
				local plan = Town.plan(
					spec(
						1,
						SHAPES[1],
						8,
						{ spawns = bad, mats = { street = "cobble", wall = "plaster", roof = "slate", spawn = "pad" } }
					)
				)
				check.truthy(string.find(errorsOf(plan.issues), '"spawns" is how many spawn pads', 1, true))
			end
			local plan = Town.plan(spec(1, SHAPES[1], 8, { spawns = 2 }))
			check.truthy(string.find(errorsOf(plan.issues), '"spawns" needs mats.spawn', 1, true))
		end)
	end)

	test.suite("Town lamps: each where it has a reason", function()
		-- the owner on the District, 2026-10-28: "I hate the fact that you added a lamp everywhere". kit world check
		-- fails a world whose middle lamp has 3 or more others within 80 studs (kit/world/worldcheck.py lamp_density)
		local LAMP_MATS =
			{ street = "cobble", block = "pave", wall = "plaster", roof = "slate", lamp = "iron", lampLight = "glow" }
		local function crowd(spots: { any }): number
			local others = {}
			for i, a in spots do
				local n = 0
				for j, b in spots do
					if i ~= j and (a.x - b.x) ^ 2 + (a.z - b.z) ^ 2 <= 80 * 80 then
						n += 1
					end
				end
				table.insert(others, n)
			end
			table.sort(others)
			if #others == 0 then
				return 0
			end
			return if #others % 2 == 1
				then others[(#others + 1) / 2]
				else (others[#others / 2] + others[#others / 2 + 1]) / 2
		end

		test.case("a lamp at each gate, each mouth of the square and each crossing - and nowhere else", function()
			for _, shape in SHAPES do
				for _, bend in { 0, 8 } do
					for seed = 1, 8 do
						local plan = Town.plan(spec(seed, shape, bend, { lamps = true, mats = LAMP_MATS }))
						check.equal(errorsOf(plan.issues), "")
						local g = Town.graph(plan)
						local want = 0
						for i, nd in g.nodes do
							local mouth = false
							for _, ed in g.edges do
								mouth = mouth or (ed.a == g.square and ed.b == i) or (ed.b == g.square and ed.a == i)
							end
							if nd.kind == "gate" or mouth or (nd.kind == "junction" and nd.degree >= 4) then
								want += 1
							end
						end
						local spots = Town.lampSpots(plan)
						-- (one lamp where two reasons meet: never more lamps than reasons, never two within 24 studs)
						check.truthy(#spots <= want and #spots >= want - #shape.gates - 1)
						for a = 1, #spots do
							for b = a + 1, #spots do
								check.truthy((spots[a].x - spots[b].x) ^ 2 + (spots[a].z - spots[b].z) ^ 2 >= 24 * 24)
							end
						end
						check.truthy(#spots >= 4 and #spots <= 12)
						local gates = 0
						for _, sp in spots do
							check.truthy(sp.why == "gate" or sp.why == "mouth" or sp.why == "crossing")
							gates += if sp.why == "gate" then 1 else 0
							-- at the foot of a house corner, a stud and a half out: on no lot
							for _, lot in plan.lots do
								check.falsy(
									Town.segmentHits(
										{ sp.x - 0.3, sp.z },
										{ sp.x + 0.3, sp.z },
										Town.lotQuad(plan, lot)
									)
								)
							end
						end
						check.equal(gates, #shape.gates)
						-- the owner's own measure: the middle lamp has fewer than 3 others within 80 studs
						check.truthy(crowd(spots) < 3)
					end
				end
			end
		end)

		test.case("cases a fresh reader broke: a small square, a lamp on the junction, a mouth left dark", function()
			-- the town's own lamps failed the owner's gate where the square is small (its four mouths and a gate all
			-- within 80 studs): 6 lamps, the middle one with 3 others. Lamps are taken away until it passes.
			for _, gates in { { "S", "N" }, { "S" }, { "S", "E", "W", "N" } } do
				for seed = 1, 8 do
					local plan = Town.plan(spec(seed, { area = { 256, 224 }, gates = gates }, 0, {
						lamps = true,
						mats = LAMP_MATS,
						square = { size = { 48, 48 } },
					}))
					check.equal(errorsOf(plan.issues), "")
					local spots = Town.lampSpots(plan)
					check.truthy(#spots < 6 or crowd(spots) < 3)
					local lit = 0
					for _, sp in spots do
						lit += if sp.why == "gate" then 1 else 0
					end
					check.equal(lit, #gates) -- (never a gate's lamp that is taken away)
				end
			end
			-- a lamp stands at a house corner near its node, never ON the node (the middle of the street) and never
			-- far from it; (a copy of the rule with every lamp on its junction passed all four cases before)
			for _, shape in SHAPES do
				for seed = 1, 6 do
					local plan = Town.plan(spec(seed, shape, 8, { lamps = true, mats = LAMP_MATS }))
					for _, sp in Town.lampSpots(plan) do
						local toNode = math.sqrt((sp.x - sp.nodeX) ^ 2 + (sp.z - sp.nodeZ) ^ 2)
						check.truthy(toNode <= Town.LAMP_REACH) -- (the corner check below is what keeps it off the street's middle)
						local nearest = math.huge
						for _, lot in plan.lots do
							for _, c in Town.lotQuad(plan, lot) do
								nearest = math.min(nearest, math.sqrt((c[1] - sp.x) ^ 2 + (c[2] - sp.z) ^ 2))
							end
						end
						check.truthy(near(nearest, 1.5, 1e-6))
					end
				end
			end
			-- every mouth of a square of the usual size is lit: by its own lamp or one within a lamp's reach of it
			-- (139 mouths in 1,008 towns had none within 32 studs: their corner was another lamp's)
			for _, shape in SHAPES do
				for seed = 1, 6 do
					local plan = Town.plan(spec(seed, shape, 8, { lamps = true, mats = LAMP_MATS }))
					local g = Town.graph(plan)
					local spots = Town.lampSpots(plan)
					for i, nd in g.nodes do
						local mouth = false
						for _, ed in g.edges do
							mouth = mouth or (ed.a == g.square and ed.b == i) or (ed.b == g.square and ed.a == i)
						end
						if mouth then
							local best = math.huge
							for _, sp in spots do
								best = math.min(best, math.sqrt((sp.x - nd.px) ^ 2 + (sp.z - nd.pz) ^ 2))
							end
							check.truthy(best <= Town.LAMP_REACH)
						end
					end
				end
			end
			-- no lit head without a word for its colour
			local dark = Town.plan(
				spec(
					1,
					SHAPES[1],
					8,
					{ lamps = true, mats = { street = "cobble", wall = "plaster", roof = "slate", lamp = "iron" } }
				)
			)
			local warned = false
			for _, issue in dark.issues do
				warned = warned
					or (issue.severity == "warn" and string.find(issue.message, "mats.lampLight", 1, true) ~= nil)
			end
			check.truthy(warned)
			check.equal(errorsOf(dark.issues), "")
		end)

		test.case("no two lamps face each other across a street (card mkmc)", function()
			-- the lamps and the streets' claims as the town's own steps carry them: two lamps FACE when they stand
			-- on opposite sides of one claimed street within 3 studs of each other along it
			local function facing(s: any): (number, number, number)
				local lamps, claims = {}, {}
				for _, st in Town.steps(Town.plan(s), s) do
					local kind, v = next(st)
					if kind == "row" and v.item == "lamp" then
						table.insert(lamps, v.points[1])
					elseif kind == "fit" and v.kind == "street" and v.from and v.to then
						table.insert(claims, v)
					end
				end
				local n = 0
				for _, c in claims do
					local dx, dz = c.to[1] - c.from[1], c.to[2] - c.from[2]
					local len = math.sqrt(dx * dx + dz * dz)
					dx, dz = dx / len, dz / len
					local sides = {}
					for _, l in lamps do
						local along = (l[1] - c.from[1]) * dx + (l[2] - c.from[2]) * dz
						local across = (l[2] - c.from[2]) * dx - (l[1] - c.from[1]) * dz
						if along > -8 and along < len + 8 and math.abs(across) < 22 then
							table.insert(sides, { along, across })
						end
					end
					for i = 1, #sides do
						for j = i + 1, #sides do
							if sides[i][2] * sides[j][2] < 0 and math.abs(sides[i][1] - sides[j][1]) < 3 then
								n += 1
							end
						end
					end
				end
				return n, #lamps, #claims
			end
			local towns, lampsSeen, claimsSeen = 0, 0, 0
			local shapes = table.clone(SHAPES)
			table.insert(shapes, { area = { 288, 256 }, gates = { "E", "W" } })
			table.insert(shapes, { area = { 400, 320 }, gates = { "S", "E", "W", "N" } })
			for _, shape in shapes do
				for _, bend in { 0, 8 } do
					for seed = 1, 8 do
						local s = spec(seed, shape, bend, { lamps = true, mats = LAMP_MATS })
						local n, lamps, claims = facing(s)
						check.equal(n, 0)
						towns += 1
						lampsSeen += lamps
						claimsSeen += claims
					end
				end
			end
			check.truthy(towns == 80 and lampsSeen >= 400 and claimsSeen >= 120) -- (lamps and streets are really walked)
			-- the measure sees the fault: with a lamp's light reaching nowhere, the crossing just inside each gate
			-- sets its lamp across the street from the gate's own (what every gated town did before)
			local was = Town.LAMP_LIGHT
			Town.LAMP_LIGHT = 0
			local s = spec(3, { area = { 400, 320 }, gates = { "S", "E", "W" } }, 0, { lamps = true, mats = LAMP_MATS })
			local n, crossings = 0, 0
			local ok, err = pcall(function()
				n = facing(s)
				for _, sp in Town.lampSpots(Town.plan(s)) do
					crossings += if sp.why == "crossing" then 1 else 0
				end
			end)
			Town.LAMP_LIGHT = was -- (whatever happened: the next case reads the real reach)
			check.truthy(ok, err)
			check.equal(n, 3)
			check.equal(crossings, 3) -- (a crossing no lamp lights still gets its own)
			-- ... and lit, the crossing behind each gate has none: 3 gates + 4 mouths
			local lit = Town.lampSpots(Town.plan(s))
			for _, sp in lit do
				check.truthy(sp.why ~= "crossing")
			end
			check.equal(#lit, 7)
		end)

		test.case("a lamp at every junction WOULD be a lamp everywhere: why the rule stops at crossings", function()
			local worst = 0
			for seed = 1, 8 do
				local plan = Town.plan(spec(seed, SHAPES[2], 8))
				local all = {}
				for _, nd in Town.graph(plan).nodes do
					if nd.kind == "junction" or nd.kind == "gate" then
						table.insert(all, { x = nd.px, z = nd.pz })
					end
				end
				worst = math.max(worst, crowd(all))
			end
			check.truthy(worst >= 3)
		end)

		test.case("the town's steps carry them as single lamps, and the compiler lights them", function()
			local s = spec(3, SHAPES[1], 8, { lamps = true, mats = LAMP_MATS })
			local plan = Town.plan(s)
			local spots = Town.lampSpots(plan)
			local rows = 0
			for _, st in Town.steps(plan, s) do
				local kind, v = next(st)
				if kind == "row" then
					check.equal(v.item, "lamp")
					check.equal(#v.points, 2)
					check.equal(v.curve, false)
					rows += 1
				end
			end
			check.equal(rows, #spots)
			local palette = table.clone(PALETTE)
			palette.iron = { material = "Metal", color = { 40, 40, 44 } }
			palette.glow = { material = "Neon", color = { 255, 214, 160 } }
			local _, parts, issues =
				World.compile({ name = "T", palette = palette, scale = "r6", build = { { town = s } } })
			check.equal(errorsOf(issues), "")
			local heads, lit = {}, 0
			for _, p in parts do
				if p.name == "LampHead" then
					table.insert(heads, p)
					for _, c in p.children or {} do
						lit += if c.kind == "light" then 1 else 0
					end
				end
			end
			check.equal(#heads, #spots)
			check.equal(lit, #spots)
			-- each lit head hangs toward its junction: nearer to it than its own post's foot is
			for k, sp in spots do
				local head = heads[k]
				local toHead = (head.pos[1] - sp.x) * sp.toX + (head.pos[3] - sp.z) * sp.toZ
				check.truthy(toHead > 1)
			end
		end)

		test.case('no lamps without the word; what "lamps" refuses', function()
			local s = spec(3, SHAPES[1], 8)
			for _, st in Town.steps(Town.plan(s), s) do
				check.truthy(next(st) ~= "row")
			end
			for _, bad in { "yes", 1, {} } :: { any } do
				local plan = Town.plan(spec(1, SHAPES[1], 8, { lamps = bad, mats = LAMP_MATS }))
				check.truthy(string.find(errorsOf(plan.issues), '"lamps" is true', 1, true))
			end
			local plan = Town.plan(spec(1, SHAPES[1], 8, { lamps = true }))
			check.truthy(string.find(errorsOf(plan.issues), '"lamps": true needs mats.lamp', 1, true))
			check.equal(errorsOf(Town.plan(spec(1, SHAPES[1], 8, { lamps = false })).issues), "")
		end)
	end)

	test.suite("Town market: stalls on the square, what the square is for kept clear", function()
		local MARKET =
			{ street = "cobble", block = "pave", wall = "plaster", roof = "slate", stall = "timber", cloth = "cloth" }

		-- (the numbers are written out here, not read from Town: a rule set to 0 must fail a case)
		local function corners(sp: any): { { number } }
			return Town.quadOf({ x0 = sp.x - 4, x1 = sp.x + 4, z0 = sp.z - 2.5, z1 = sp.z + 2.5 }, sp.x, sp.z, sp.turn)
		end
		local function toSegment(p: { number }, a: { number }, b: { number }): number
			local dx, dz = b[1] - a[1], b[2] - a[2]
			local t = math.clamp(((p[1] - a[1]) * dx + (p[2] - a[2]) * dz) / math.max(dx * dx + dz * dz, 1e-9), 0, 1)
			return math.sqrt((p[1] - a[1] - t * dx) ^ 2 + (p[2] - a[2] - t * dz) ^ 2)
		end
		local MARKETS = {
			{ area = { 256, 224 }, gates = { "S" } },
			{ area = { 320, 320 }, gates = { "S", "N" } },
			{ area = { 400, 320 }, gates = { "S", "E", "W" } },
			{ area = { 320, 320 }, gates = { "E" } },
			{ area = { 400, 320 }, gates = { "W", "N" } },
			{ area = { 320, 400 }, gates = { "N", "E", "S", "W" } },
		}

		test.case(
			"every stall corner: 10 from the square's edge, 10 from the gate's view, 16 from a street's opening",
			function()
				local towns, stalls, dropped, places = 0, 0, 0, 0
				for _, shape in MARKETS do
					for _, bend in { 0, 8 } do
						for seed = 1, 8 do
							local plan = Town.plan(spec(seed, shape, bend, { market = true, mats = MARKET }))
							if errorsOf(plan.issues) ~= "" then
								-- (the one error allowed here: a square with no room for a market, said)
								check.truthy(string.find(errorsOf(plan.issues), "has room for", 1, true))
								continue
							end
							local S = plan.square
							local spots = Town.stallSpots(plan)
							check.truthy(#spots >= 2)
							local g = Town.graph(plan)
							-- the view AS BUILT: the main street's end on the square to the landmark's moved front
							local sight = Town.landmarkSight(plan)
							check.truthy(sight ~= nil and sight.fromGate)
							local line = Town.viewLine(plan)
							check.truthy(line ~= nil)
							local rec = Town.record("T", plan)
							check.equal(#rec.stalls, #spots)
							check.truthy(math.abs(rec.view.at[1] - line[2][1]) <= 1e-6)
							check.truthy(math.abs(rec.view.at[2] - line[2][2]) <= 1e-6)
							for i, sp in spots do
								check.truthy(math.abs(sp.turn) <= 6)
								check.truthy(math.abs(rec.stalls[i].x - sp.x) <= 1e-6)
								for _, c in corners(sp) do
									check.truthy(c[1] >= S.x0 + 10 - 1e-6 and c[1] <= S.x1 - 10 + 1e-6)
									check.truthy(c[2] >= S.z0 + 10 - 1e-6 and c[2] <= S.z1 - 10 + 1e-6)
									check.truthy(toSegment(c, line[1], line[2]) >= 10)
									for _, ed in g.edges do
										local nd = if ed.a == g.square
											then g.nodes[ed.b]
											elseif ed.b == g.square then g.nodes[ed.a]
											else nil
										if nd then
											-- the widest street whose strip holds this mouth: its opening is that wide
											local half = 0
											for _, st in plan.streets do
												local r = Town.strip(st)
												if
													nd.x >= r.x0 - 1
													and nd.x <= r.x1 + 1
													and nd.z >= r.z0 - 1
													and nd.z <= r.z1 + 1
												then
													half = math.max(half, st.width / 2)
												end
											end
											check.truthy(half >= 4)
											check.truthy(
												math.sqrt((nd.px - c[1]) ^ 2 + (nd.pz - c[2]) ^ 2) >= 16 + half
											)
										end
									end
								end
								for j = i + 1, #spots do
									check.truthy(Town.quadsApart(corners(sp), corners(spots[j])) >= 5) -- (a body walks between)
								end
							end
							-- a market has gaps: of the places the rows offer that break no rule, some are left out
							local xs, zs = {}, {}
							for _, sp in spots do
								xs[sp.x], zs[sp.z] = true, true
							end
							local nx, nz = 0, 0
							for _ in xs do
								nx += 1
							end
							for _ in zs do
								nz += 1
							end
							places += nx * nz
							dropped += nx * nz - #spots
							towns += 1
							stalls += #spots
						end
					end
				end
				check.truthy(towns >= 60) -- (most of the 96 towns hold a market)
				check.truthy(stalls >= towns * 3)
				check.truthy(dropped >= 1 and places > stalls)
			end
		)

		test.case("a square with no room for a market says so; the town then has no stalls", function()
			for _, square in { { 32, 32 }, { 40, 40 }, { 48, 48 } } do
				local s = spec(
					2,
					{ area = { 480, 480 }, gates = { "S", "N" } },
					0,
					{ market = true, mats = MARKET, square = { size = square } }
				)
				local plan = Town.plan(s)
				check.truthy(string.find(errorsOf(plan.issues), '"market": true, but this square', 1, true))
				check.equal(plan.market, false)
			end
		end)

		test.case(
			"the town's steps carry each stall as six parts; the compiler stands them where the plan says",
			function()
				local s = spec(3, MARKETS[2], 8, { market = true, mats = MARKET })
				local plan = Town.plan(s)
				check.equal(errorsOf(plan.issues), "")
				local spots = Town.stallSpots(plan)
				check.truthy(#spots >= 2)
				local parts, turned = 0, 0
				for _, st in Town.steps(plan, s) do
					local kind, v = next(st)
					if kind == "part" and string.sub(v.name, 1, 6) == "Stall " then
						parts += 1
						local sp = spots[tonumber(string.match(v.name, "^Stall (%d+)")) :: number]
						check.truthy(math.abs(v.about[1] - sp.x) <= 1e-9)
						check.truthy(math.abs(v.about[2] - sp.z) <= 1e-9)
						check.truthy(math.abs(v.turn - sp.turn) <= 1e-9)
						turned += if math.abs(sp.turn) > 0.5 then 1 else 0
					end
				end
				check.equal(parts, #spots * 6)
				check.truthy(turned >= 6) -- (a stall really turned: a sign or a pivot got wrong would show below)
				local palette = table.clone(PALETTE)
				palette.timber = { material = "Wood", color = { 96, 72, 48 } }
				palette.cloth = { material = "Fabric", color = { 150, 60, 50 } }
				local _, built, issues =
					World.compile({ name = "T", palette = palette, scale = "r6", build = { { town = s } } })
				check.equal(errorsOf(issues), "")
				local awnings, posts, counters = 0, 0, 0
				for _, p in built do
					local k = tonumber(string.match(p.name, "^Stall (%d+)"))
					if k then
						local sp = spots[k]
						local q = corners(sp)
						if string.find(p.name, "awning", 1, true) then
							awnings += 1
							check.falsy(p.collide) -- (a cloth roof nobody stands on)
							check.truthy(p.pos[2] - p.size[2] / 2 >= 8 - 1e-6) -- (clear over a body's head)
							check.truthy(math.abs(p.pos[1] - sp.x) <= 1e-6) -- (over the stall's middle)
							check.truthy(math.abs(p.pos[3] - sp.z) <= 1e-6)
						elseif string.find(p.name, "post", 1, true) then
							posts += 1
							-- each post stands just inside one corner of the stall AS TURNED (0.3 in on both sides)
							local nearest = math.huge
							for _, c in q do
								nearest = math.min(nearest, math.sqrt((c[1] - p.pos[1]) ^ 2 + (c[2] - p.pos[3]) ^ 2))
							end
							check.truthy(math.abs(nearest - (0.3 * math.sqrt(2))) <= 1e-4)
						else
							counters += 1
							check.truthy(math.sqrt((p.pos[1] - sp.x) ^ 2 + (p.pos[3] - sp.z) ^ 2) < 1.5)
						end
					end
				end
				check.equal(awnings, #spots)
				check.equal(posts, #spots * 4)
				check.equal(counters, #spots)
			end
		)

		test.case('no market without the word; what "market" refuses', function()
			local s = spec(3, SHAPES[1], 8)
			for _, st in Town.steps(Town.plan(s), s) do
				local kind, v = next(st)
				check.falsy(kind == "part" and string.sub(v.name, 1, 6) == "Stall ")
			end
			check.truthy(
				string.find(
					errorsOf(Town.plan(spec(1, SHAPES[1], 8, { market = "yes", mats = MARKET })).issues),
					'"market" is true',
					1,
					true
				)
			)
			check.truthy(
				string.find(
					errorsOf(Town.plan(spec(1, SHAPES[1], 8, { market = true })).issues),
					'"market": true needs mats.stall',
					1,
					true
				)
			)
			check.equal(errorsOf(Town.plan(spec(1, SHAPES[1], 8, { market = false })).issues), "")
		end)
	end)

	test.suite("Town yards: things in the yards a walker can enter, the way through kept", function()
		local DRESS =
			{ street = "cobble", block = "pave", wall = "plaster", roof = "slate", wood = "timber", cloth = "cloth" }
		local YARDS = {
			{ area = { 256, 224 }, gates = { "S" } },
			{ area = { 320, 320 }, gates = { "S", "N" } },
			{ area = { 400, 320 }, gates = { "S", "E", "W" } },
			{ area = { 480, 480 }, gates = { "N", "E", "S", "W" } },
			{ area = { 192, 160 }, gates = { "S" } }, -- (too small for a yard worth the name: says so)
		}
		-- (the numbers are written out here, not read from Town: a rule set to 0 must fail a case)
		local function overlap(a: any, b: any): boolean
			return a.x0 < b.x1 - 1e-6 and a.x1 > b.x0 + 1e-6 and a.z0 < b.z1 - 1e-6 and a.z1 > b.z0 + 1e-6
		end

		-- the yard's clear ground worked out HERE, by each house's front (not by the rule's own function)
		local function clearOf(plan: any, yd: any): any
			local r = yd.rect
			local c = { x0 = r.x0, x1 = r.x1, z0 = r.z0, z1 = r.z1 }
			for _, lot in plan.lots do
				if lot.block == yd.block and overlap(r, lot.rect) then
					local l = lot.rect
					if lot.front == "W" then
						c.x0 = math.max(c.x0, l.x1)
					elseif lot.front == "E" then
						c.x1 = math.min(c.x1, l.x0)
					elseif lot.front == "N" then
						c.z0 = math.max(c.z0, l.z1)
					else
						c.z1 = math.min(c.z1, l.z0)
					end
				end
			end
			return c
		end
		-- a house's back wall as built: half the plan's gap inside its lot's lines
		local function wallOf(plan: any, lot: any): any
			local i = plan.gap / 2
			return { x0 = lot.rect.x0 + i, x1 = lot.rect.x1 - i, z0 = lot.rect.z0 + i, z1 = lot.rect.z1 - i }
		end

		test.case(
			"a woodpile stands against a house's back WALL, a wash line runs wall to wall; ends and a way through stay clear",
			function()
				local towns, piles, lines, none, trimmed = 0, 0, 0, 0, 0
				for _, shape in YARDS do
					for _, trim in { false, true } do
						for seed = 1, 10 do
							local mats = table.clone(DRESS)
							mats.trim = if trim then "plaster" else nil
							local plan = Town.plan(spec(seed, shape, 0, { yards = true, mats = mats }))
							local errs = errorsOf(plan.issues)
							if errs ~= "" then
								-- (the one error allowed here: a town with no yard to dress, said)
								check.truthy(string.find(errs, '"yards": true, but this town has no yard', 1, true))
								check.equal(plan.yardDress, false)
								none += 1
								continue
							end
							towns += 1
							check.equal(plan.gap > 0, trim)
							local things = Town.yardThings(plan)
							check.truthy(#things >= 1)
							for i, th in things do
								local yd = plan.yards[th.yard]
								check.equal(yd.block, th.block)
								check.truthy(#yd.open >= 1 or yd.way ~= nil) -- (a yard with a way in: one nobody enters is never dressed)
								local c = clearOf(plan, yd)
								for _, lot in plan.lots do
									if lot.block == yd.block then
										check.falsy(overlap(c, lot.rect))
									end
								end
								local got = Town.yardClear(plan, yd)
								check.truthy(
									got ~= nil
										and got.x0 == c.x0
										and got.x1 == c.x1
										and got.z0 == c.z0
										and got.z1 == c.z1
								)
								local long0, long1 = if th.alongX then c.x0 else c.z0, if th.alongX then c.x1 else c.z1
								-- the two back walls' faces
								local a = (if th.alongX then c.z0 else c.x0) - plan.gap / 2
								local b = (if th.alongX then c.z1 else c.x1) + plan.gap / 2
								check.truthy(long1 - long0 >= b - a - plan.gap - 1e-6)
								check.truthy(b - a >= 10 - 1e-6) -- (ten studs between the back walls, or nothing)
								local at = if th.alongX then th.x else th.z
								local across = if th.alongX then th.z else th.x
								-- a house's back WALL stands on that side behind [t0, t1], its corner posts clear, `tall` high
								local function wallBehind(face: number, t0: number, t1: number, tall: number): boolean
									for _, lot in plan.lots do
										local w = wallOf(plan, lot)
										local w0, w1 =
											if th.alongX then w.x0 else w.z0, if th.alongX then w.x1 else w.z1
										local n0, n1 =
											if th.alongX then w.z0 else w.x0, if th.alongX then w.z1 else w.x1
										local clear = if trim then 1.5 else 0
										if
											lot.block == yd.block
											and (math.abs(n0 - face) < 1e-6 or math.abs(n1 - face) < 1e-6)
											and w0 + clear <= t0 + 1e-6
											and w1 - clear >= t1 - 1e-6
											and lot.floors * lot.floorHeight >= tall
										then
											return true
										end
									end
									return false
								end
								if th.kind == "pile" then
									piles += 1
									trimmed += if trim then 1 else 0
									local box = if th.alongX
										then { x0 = th.x - 2.5, x1 = th.x + 2.5, z0 = th.z - 1, z1 = th.z + 1 }
										else { x0 = th.x - 1, x1 = th.x + 1, z0 = th.z - 2.5, z1 = th.z + 2.5 }
									-- 8 studs from either gated end, in no house's walls
									check.truthy(at - 2.5 >= long0 + 8 - 1e-6 and at + 2.5 <= long1 - 8 + 1e-6)
									for _, lot in plan.lots do
										check.falsy(overlap(box, wallOf(plan, lot)))
									end
									-- against a WALL: a fifth of a stud from one, 7.8 studs or more of way left beside it
									local nearSide = math.min(across - 1 - a, b - (across + 1))
									local farSide = math.max(across - 1 - a, b - (across + 1))
									check.truthy(math.abs(nearSide - 0.2) < 1e-6)
									check.truthy(farSide >= 7.8 - 1e-6)
									check.truthy(
										wallBehind(if across - a < b - across then a else b, at - 2.5, at + 2.5, 3)
									)
								else
									lines += 1
									trimmed += if trim then 1 else 0
									check.equal(th.kind, "line")
									check.truthy(math.abs(th.span - (b - a)) < 1e-6) -- (from one back wall to the facing one)
									check.truthy(th.span <= 24 + 1e-6) -- (no cord across a court wider than 24 studs)
									check.truthy(math.abs(across - (a + b) / 2) < 1e-6)
									check.truthy(at >= long0 + 8 - 1e-6 and at <= long1 - 8 + 1e-6)
									-- a wall at BOTH its ends, tall enough to tie a line 10 studs up
									check.truthy(wallBehind(a, at - 0.5, at + 0.5, 11))
									check.truthy(wallBehind(b, at - 0.5, at + 0.5, 11))
									check.equal(#th.hang, 2)
									for _, f in th.hang do
										check.truthy(f * th.span >= 1.5 and (1 - f) * th.span >= 1.5) -- (a sheet clear of both walls)
									end
									check.truthy((th.hang[2] - th.hang[1]) * th.span >= 2.4) -- (two sheets, not one on the other)
								end
								-- two things of one yard keep apart along it (a pile is 5 long: 4 studs or more between)
								for j = i + 1, #things do
									local o = things[j]
									if o.yard == th.yard then
										check.truthy(math.abs((if th.alongX then o.x else o.z) - at) >= 9 - 1e-6)
									end
								end
							end
						end
					end
				end
				check.truthy(towns >= 40) -- (over half of the 80 towns have a yard to dress)
				check.truthy(none >= 1) -- (... and some have none, and say so)
				check.truthy(piles >= towns and lines >= towns)
				check.truthy(trimmed >= 40) -- (towns with trim - walls a stud inside the lots - are really walked)
			end
		)

		test.case("the yard's clear ground is cut by each house's front, on every yard of every block", function()
			local cut = 0
			for _, shape in YARDS do
				for _, lots in { false, { width = { 16, 16 }, depth = { 24, 32 } } } :: { any } do
					for seed = 1, 6 do
						local plan = Town.plan(spec(seed, shape, 0, { lots = lots or nil }))
						for _, yd in plan.yards do
							local c = clearOf(plan, yd)
							local got = Town.yardClear(plan, yd)
							if c.x1 - c.x0 < 1e-6 or c.z1 - c.z0 < 1e-6 then
								check.equal(got, nil)
							else
								check.truthy(
									got ~= nil
										and got.x0 == c.x0
										and got.x1 == c.x1
										and got.z0 == c.z0
										and got.z1 == c.z1
								)
								cut += if c.x0 ~= yd.rect.x0
										or c.x1 ~= yd.rect.x1
										or c.z0 ~= yd.rect.z0
										or c.z1 ~= yd.rect.z1
									then 1
									else 0
							end
						end
					end
				end
			end
			check.truthy(cut >= 20) -- (yards with a row inside their rect: the case the first rule got wrong)
		end)

		test.case(
			"the compiler stands each part where the plan says, at its size and height, turned with its block",
			function()
				local mats = table.clone(DRESS)
				mats.trim = "plaster"
				local s = spec(5, YARDS[2], 8, { yards = true, mats = mats })
				local plan = Town.plan(s)
				check.equal(errorsOf(plan.issues), "")
				check.truthy(plan.bent ~= nil)
				local built = Town.yardThingsBuilt(plan)
				local planned = Town.yardThings(plan)
				check.truthy(#built >= 2 and #built == #planned)
				local moved = 0
				for k, th in built do
					local px, pz = plan.bent.place(th.block, planned[k].x, planned[k].z)
					check.truthy(math.abs(th.x - px) < 1e-9 and math.abs(th.z - pz) < 1e-9)
					check.truthy(math.abs(th.turn - plan.bent.blocks[th.block].turn) < 1e-9)
					moved += if math.abs(th.x - planned[k].x) + math.abs(th.z - planned[k].z) > 0.5 then 1 else 0
				end
				check.truthy(moved >= 1) -- (the bend really moved one: a thing left at its planned place would show)
				-- every part of a thing is turned by its block's turn about the thing's own middle
				local stepped = 0
				for _, st in Town.steps(plan, s) do
					local kind, v = next(st)
					if kind == "part" and string.sub(v.name, 1, 5) == "Yard " then
						local th = built[tonumber(string.match(v.name, "^Yard (%d+)")) :: number]
						check.truthy(math.abs(v.turn - th.turn) < 1e-9 and math.abs(th.turn) > 0.1)
						check.truthy(math.abs(v.about[1] - th.x) < 1e-9 and math.abs(v.about[2] - th.z) < 1e-9)
						-- as typed, before the turn: along the yard and across it, by the yard's own lie
						local along, across =
							if th.alongX then v.size[1] else v.size[3], if th.alongX then v.size[3] else v.size[1]
						local dAcross = if th.alongX then v.pos[3] - th.z else v.pos[1] - th.x
						local dAlong = if th.alongX then v.pos[1] - th.x else v.pos[3] - th.z
						check.truthy(math.abs(dAlong) < 1e-9) -- (nothing of a thing stands off its place along the yard)
						local bottom, top = v.pos[2] - v.size[2] / 2, v.pos[2] + v.size[2] / 2
						local ground = plan.y + 0.4 -- (the block's pavement: a kerb of 0.4 over the street)
						if string.find(v.name, "washing", 1, true) then
							check.truthy(along < 0.2 and math.abs(across - 2.2) < 1e-9) -- (a sheet hangs IN the line's plane)
							check.truthy(math.abs(bottom - (ground + 8.05)) < 1e-6) -- (its hem over a body's head)
							check.truthy(math.abs(top - (ground + 9.95)) < 1e-6) -- (... and its top at the cord)
							check.truthy(math.abs(dAcross) <= th.span / 2 - 1.4)
						elseif string.find(v.name, "wash line", 1, true) then
							check.truthy(along < 0.2 and math.abs(across - th.span) < 1e-9) -- (ACROSS the yard, wall to wall)
							check.truthy(math.abs(v.pos[2] - (ground + 10)) < 1e-6)
							check.truthy(math.abs(dAcross) < 1e-9)
						elseif string.find(v.name, "cover", 1, true) then
							check.truthy(math.abs(along - 5.4) < 1e-9 and math.abs(across - 2.3) < 1e-9)
							check.truthy(math.abs(bottom - (ground + 2.6)) < 1e-6) -- (lying on the logs)
						else
							check.truthy(math.abs(along - 5) < 1e-9 and math.abs(across - 2) < 1e-9) -- (its length ALONG the wall)
							check.truthy(math.abs(bottom - ground) < 1e-6 and math.abs(top - (ground + 2.6)) < 1e-6)
							check.truthy(math.abs(dAcross) < 1e-9)
						end
						stepped += 1
					end
				end
				check.truthy(stepped >= 4)
				local rec = Town.record("T", plan)
				check.equal(#rec.yardThings, #built)
				check.truthy(math.abs(rec.yardThings[1].x - built[1].x) < 1e-9)
				local palette = table.clone(PALETTE)
				palette.timber = { material = "Wood", color = { 96, 72, 48 } }
				palette.cloth = { material = "Fabric", color = { 150, 60, 50 } }
				local _, parts, issues =
					World.compile({ name = "T", palette = palette, scale = "r6", build = { { town = s } } })
				check.equal(errorsOf(issues), "")
				local seen = { pile = 0, cover = 0, line = 0, washing = 0 }
				for _, p in parts do
					local k = tonumber(string.match(p.name, "^Yard (%d+)"))
					if k then
						local th = built[k]
						local d = math.sqrt((p.pos[1] - th.x) ^ 2 + (p.pos[3] - th.z) ^ 2)
						if string.find(p.name, "washing", 1, true) then
							seen.washing += 1
							check.falsy(p.collide)
							check.truthy(d <= th.span / 2 - 1.4 and d >= 0.5)
						elseif string.find(p.name, "wash line", 1, true) then
							seen.line += 1
							check.falsy(p.collide)
							check.truthy(d < 1e-6)
						elseif string.find(p.name, "cover", 1, true) then
							seen.cover += 1
							check.truthy(d < 1e-6)
						else
							seen.pile += 1
							check.truthy(d < 1e-6)
							check.truthy(p.collide ~= false) -- (a woodpile is in the way: a body walks round it)
						end
					end
				end
				local nPiles, nLines = 0, 0
				for _, th in built do
					nPiles += if th.kind == "pile" then 1 else 0
					nLines += if th.kind == "line" then 1 else 0
				end
				check.truthy(nPiles >= 1 and nLines >= 1)
				check.equal(seen.pile, nPiles)
				check.equal(seen.cover, nPiles)
				check.equal(seen.line, nLines)
				check.equal(seen.washing, nLines * 2)
			end
		)

		test.case("a shut yard is opened: one house on its quietest street gives way to a court with a gate", function()
			local ways, dressed, towns, ended, lone = 0, 0, 0, 0, 0
			local WALLS = table.clone(DRESS)
			WALLS.wallAlt = "brick"
			for _, shape in { YARDS[1], YARDS[2], YARDS[3], YARDS[4] } do
				for seed = 1, 8 do
					local s = spec(seed, shape, 8, { yards = true, mats = WALLS })
					local plan = Town.plan(s)
					local sBare = spec(seed, shape, 8, { yards = false, mats = WALLS })
					local bare = Town.plan(sBare)
					if errorsOf(plan.issues) ~= "" then
						-- (the one error allowed: no yard to dress, said - and then no house gave way)
						check.truthy(
							string.find(errorsOf(plan.issues), '"yards": true, but this town has no yard', 1, true)
						)
						continue
					end
					towns += 1
					local here = 0
					local byName = {}
					for _, lot in bare.lots do
						byName[lot.name] = lot
					end
					-- a street ends on this house's front (worked out here from the streets' own ends)
					local function endsOn(lot: any): boolean
						local l = lot.rect
						for _, st in bare.streets do
							for _, t in { st.from, st.to } do
								local ex, ez = if st.axis == "z" then st.at else t, if st.axis == "z" then t else st.at
								-- the point 1 stud inside the lot behind the middle of its front
								local fx, fz = (l.x0 + l.x1) / 2, (l.z0 + l.z1) / 2
								local nx, nz = 0, 0
								if lot.front == "N" then
									fz, nz = l.z0, -1
								elseif lot.front == "S" then
									fz, nz = l.z1, 1
								elseif lot.front == "W" then
									fx, nx = l.x0, -1
								else
									fx, nx = l.x1, 1
								end
								-- the street's end lies out in front of the lot, within 36 studs, on a line through its front
								local ahead = (ex - fx) * nx + (ez - fz) * nz
								local aside = math.abs((ex - fx) * nz) + math.abs((ez - fz) * nx)
								local alongFront = (st.axis == "z") == (nz ~= 0)
								local width = if nz ~= 0 then l.x1 - l.x0 else l.z1 - l.z0
								if alongFront and ahead >= -1e-6 and ahead <= 36 and aside < width / 2 - 1e-6 then
									return true
								end
							end
						end
						return false
					end
					for yi, yd in plan.yards do
						local way = yd.way
						if way then
							here += 1
							check.equal(#yd.open, 0) -- (a yard with a gated end needs no second way)
							-- the house that gave way: in the town with bare yards it stands there, in this one nothing does
							local was = byName[way.name]
							check.truthy(was ~= nil and was.rect.x0 == way.rect.x0 and was.rect.z1 == way.rect.z1)
							check.truthy(not was.corner and not was.landmark and not was.through)
							check.truthy(was.rank <= 3) -- (never a house on the square)
							check.falsy(endsOn(was)) -- (never the house that closes a street's view)
							for _, lot in plan.lots do
								check.falsy(overlap(lot.rect, way.rect))
							end
							-- the block keeps a front on that street: another house of it faces the same way
							local same = 0
							for _, lot in plan.lots do
								same += if lot.block == yd.block and lot.front == way.front then 1 else 0
							end
							check.truthy(same >= 1)
							-- (the yard's clear ground BEFORE the house gave way: the same yard of the town with bare yards)
							local c = clearOf(bare, bare.yards[yi])
							check.truthy(math.min(c.x1 - c.x0, c.z1 - c.z0) >= 10 - 1e-6)
							local r = way.rect
							local function backOn(lot: any): (boolean, number)
								local l = lot.rect
								if lot.front == "W" then
									return math.abs(l.x1 - c.x0) < 1e-6 and l.z0 >= c.z0 - 1e-6 and l.z1 <= c.z1 + 1e-6,
										math.abs((l.z0 + l.z1) / 2 - (c.z0 + c.z1) / 2)
								elseif lot.front == "E" then
									return math.abs(l.x0 - c.x1) < 1e-6 and l.z0 >= c.z0 - 1e-6 and l.z1 <= c.z1 + 1e-6,
										math.abs((l.z0 + l.z1) / 2 - (c.z0 + c.z1) / 2)
								elseif lot.front == "N" then
									return math.abs(l.z1 - c.z0) < 1e-6 and l.x0 >= c.x0 - 1e-6 and l.x1 <= c.x1 + 1e-6,
										math.abs((l.x0 + l.x1) / 2 - (c.x0 + c.x1) / 2)
								end
								return math.abs(l.z0 - c.z1) < 1e-6 and l.x0 >= c.x0 - 1e-6 and l.x1 <= c.x1 + 1e-6,
									math.abs((l.x0 + l.x1) / 2 - (c.x0 + c.x1) / 2)
							end
							local wasOn, wasOff = backOn(was)
							check.truthy(wasOn) -- (its whole back is on the yard's clear ground)
							-- the QUIETEST street, and on it the house nearest the middle: no other house that could have
							-- given way stands on a quieter street, or on as quiet a one nearer the middle
							local fronts = {}
							for _, lot in bare.lots do
								if lot.block == yd.block then
									fronts[lot.front] = (fronts[lot.front] or 0) + 1
								end
							end
							for _, lot in bare.lots do
								local on, off = backOn(lot)
								if
									lot.block == yd.block
									and on
									and not lot.corner
									and not lot.landmark
									and not lot.through
									and lot.rank <= 3
									and fronts[lot.front] >= 2
									and not endsOn(lot)
								then
									check.truthy(lot.rank > was.rank or (lot.rank == was.rank and off >= wasOff - 1e-6))
								end
							end
							-- the wall: ON THE STREET's line (half a stud inside the lot's front), as long as the house's
							-- front was, 10 studs high on the pavement, one gate in its middle
							local front = if way.front == "N" or way.front == "S" then r.x1 - r.x0 else r.z1 - r.z0
							local wall = nil
							for _, st in Town.steps(plan, s) do
								local kind, v = next(st)
								if kind == "wall" and v.name == `Yard way {yd.block}{way.front}` then
									wall = v
								end
							end
							check.truthy(wall ~= nil)
							check.equal(wall.height, 10)
							check.truthy(math.abs(wall.y - (plan.y + 0.4)) < 1e-9)
							check.equal(#wall.gaps, 1)
							check.truthy(math.abs(wall.gaps[1].at - front / 2) < 1e-6)
							check.truthy(wall.gaps[1].width >= 4.5 and wall.gaps[1].height >= 7.5) -- (the rig walks through)
							local sx, sz = (r.x0 + r.x1) / 2, (r.z0 + r.z1) / 2
							if way.front == "W" then
								sx = r.x0 + 0.5
							elseif way.front == "E" then
								sx = r.x1 - 0.5
							elseif way.front == "N" then
								sz = r.z0 + 0.5
							else
								sz = r.z1 - 0.5
							end
							local px, pz = plan.bent.place(yd.block, sx, sz)
							local mx, mz = (wall.from[1] + wall.to[1]) / 2, (wall.from[2] + wall.to[2]) / 2
							check.truthy(math.abs(px - mx) < 1e-6 and math.abs(pz - mz) < 1e-6)
							check.truthy(
								math.abs(
									math.sqrt((wall.to[1] - wall.from[1]) ^ 2 + (wall.to[2] - wall.from[2]) ^ 2) - front
								) < 1e-6
							)
							-- ... and the recorded gate is that middle
							local rec = nil
							for _, w in Town.yardWays(plan) do
								if w.yard == yi then
									rec = w
								end
							end
							check.truthy(rec ~= nil)
							check.truthy(math.abs(rec.gate.x - mx) < 1e-6 and math.abs(rec.gate.z - mz) < 1e-6)
							for _, th in Town.yardThings(plan) do
								dressed += if th.yard == yi then 1 else 0
							end
						end
					end
					-- houses the rule passed over, counted: the cases above are not empty words
					for _, lot in bare.lots do
						ended += if endsOn(lot) and lot.rank < 3 then 1 else 0
					end
					ways += here
					check.equal(#plan.lots, #bare.lots - here) -- (one house a way, no more)
					check.truthy(plan.frontage.built <= bare.frontage.built - here * 16 + 1e-6)
					-- every house that STAYS is the very house of the town with bare yards: storeys, type, wall
					local mats, matsBare = {}, {}
					for _, st in Town.steps(plan, s) do
						local kind, v = next(st)
						if kind == "building" then
							mats[v.name] = v.mat
						end
					end
					for _, st in Town.steps(bare, sBare) do
						local kind, v = next(st)
						if kind == "building" then
							matsBare[v.name] = v.mat
						end
					end
					local brick = 0
					for _, lot in plan.lots do
						local was = byName[lot.name]
						check.truthy(was ~= nil)
						check.equal(lot.floors, was.floors)
						check.equal(lot.floorHeight, was.floorHeight)
						check.equal(lot.type, was.type)
						check.equal(lot.landmark, was.landmark)
						check.equal(mats[lot.name], matsBare[lot.name])
						brick += if mats[lot.name] == "brick" then 1 else 0
					end
					check.truthy(brick >= 5) -- (the second wall material is really drawn: the draws are what is held)
					check.equal(#Town.record("T", plan).yardWays, here)
					-- a town with bare yards opens none, and records none
					for _, yd in bare.yards do
						check.equal(yd.way, nil)
						lone += 0
					end
					check.equal(Town.record("T", bare).yardWays, nil)
				end
			end
			check.truthy(towns >= 28) -- (nearly every one of the 32 towns)
			check.truthy(ways >= towns) -- (a way a town and more, on average)
			check.truthy(dressed >= ways / 2) -- (... and the opened yards get things: 91 in 134 of them when this was written)
			check.truthy(ended >= towns) -- (houses that close an alley's or a lane's view exist in these towns)
		end)

		test.case('"yards": true with no wood or cloth is an error and takes no house', function()
			local plan = Town.plan(spec(1, YARDS[2], 0, { yards = true }))
			check.truthy(string.find(errorsOf(plan.issues), '"yards": true needs mats.wood', 1, true))
			local bare = Town.plan(spec(1, YARDS[2], 0, { yards = false }))
			check.equal(#plan.lots, #bare.lots)
			for _, yd in plan.yards do
				check.equal(yd.way, nil)
			end
		end)

		test.case(
			"a wash line is tied to walls tall enough: between one-storey backs 9 studs high there is none",
			function()
				local plan = Town.plan(spec(6, YARDS[2], 0, { yards = true, mats = DRESS }))
				check.equal(errorsOf(plan.issues), "")
				local piles, lines = 0, 0
				for _, th in Town.yardThings(plan) do
					piles += if th.kind == "pile" then 1 else 0
					lines += if th.kind == "line" then 1 else 0
				end
				check.truthy(piles >= 1 and lines >= 1)
				for _, lot in plan.lots do
					lot.floors, lot.floorHeight = 1, 9
				end
				local lowPiles, lowLines = 0, 0
				for _, th in Town.yardThings(plan) do
					lowPiles += if th.kind == "pile" then 1 else 0
					lowLines += if th.kind == "line" then 1 else 0
				end
				check.equal(lowLines, 0) -- (a line 10 studs up would hang over the roofs)
				check.equal(lowPiles, piles) -- (a woodpile 2.8 high leans on any wall)
			end
		)

		test.case('no yard things without the word; what "yards" refuses', function()
			local s = spec(1, YARDS[2], 8)
			for _, st in Town.steps(Town.plan(s), s) do
				local kind, v = next(st)
				check.falsy(kind == "part" and string.sub(v.name, 1, 5) == "Yard ")
			end
			check.equal(Town.record("T", Town.plan(s)).yardThings, nil)
			check.truthy(
				string.find(
					errorsOf(Town.plan(spec(1, YARDS[2], 8, { yards = "yes", mats = DRESS })).issues),
					'"yards" is true',
					1,
					true
				)
			)
			check.truthy(
				string.find(
					errorsOf(Town.plan(spec(1, YARDS[2], 8, { yards = true })).issues),
					'"yards": true needs mats.wood',
					1,
					true
				)
			)
			check.equal(errorsOf(Town.plan(spec(1, YARDS[2], 8, { yards = false })).issues), "")
			-- mats.stall serves for the wood (a town with a market has it already)
			local both = {
				street = "cobble",
				block = "pave",
				wall = "plaster",
				roof = "slate",
				stall = "timber",
				cloth = "cloth",
			}
			check.equal(errorsOf(Town.plan(spec(1, YARDS[2], 8, { yards = true, mats = both })).issues), "")
		end)
	end)

	test.suite("Town bend: what the compiler makes of it", function()
		test.case(
			"every house, pavement and yard wall is laid where its block stands, turned by its block's turn",
			function()
				local s = spec(3, SHAPES[1], 8)
				local plan = Town.plan(s)
				local byName: { [string]: any } = {}
				for _, lot in plan.lots do
					byName[lot.name] = lot
				end
				local houses, blocks, claims = 0, 0, 0
				for _, st in Town.steps(plan, s) do
					local kind, v = next(st)
					if kind == "building" then
						local lot = byName[v.name]
						local q = Town.lotQuad(plan, lot)
						check.truthy(near(v.center[1], (q[1][1] + q[3][1]) / 2, 1e-6))
						check.truthy(near(v.center[3], (q[1][2] + q[3][2]) / 2, 1e-6))
						check.equal(v.turn, plan.bent.blocks[lot.block].turn)
						check.equal(v.about, nil) -- (about its own middle: the house is one rigid piece with its block)
						houses += 1
					elseif kind == "floor" and string.sub(v.name, 1, 6) == "Block " then
						local bi = tonumber(string.sub(v.name, 7)) :: number
						check.equal(v.turn, plan.bent.blocks[bi].turn)
						check.truthy(
							near(v.center[1], plan.bent.blocks[bi].x) and near(v.center[3], plan.bent.blocks[bi].z)
						)
						blocks += 1
					elseif kind == "fit" then
						-- a bent street claims its width piece by piece, each piece a short straight of its middle line
						check.truthy(v.kind == "street" or v.kind == "alley")
						local len = math.sqrt((v.to[1] - v.from[1]) ^ 2 + (v.to[2] - v.from[2]) ^ 2)
						check.truthy(len > 4 and len < 40)
						claims += 1
					end
				end
				check.equal(houses, #plan.lots)
				check.equal(blocks, #plan.blocks)
				check.truthy(claims > 12)
				-- the ground reaches under every block as it stands
				local _, ground = next(Town.steps(plan, s)[1])
				check.equal(ground.name, "Streets")
				for _, b in plan.bent.blocks do
					for _, c in b.quad do
						check.truthy(math.abs(c[1] - ground.center[1]) <= ground.size[1] / 2)
						check.truthy(math.abs(c[2] - ground.center[3]) <= ground.size[2] / 2)
					end
				end
			end
		)

		test.case(
			"a bent town compiles: every wall of a house is turned with it, its door claim stands on its front",
			function()
				local s = spec(3, SHAPES[1], 8)
				local plan = Town.plan(s)
				local _, parts, issues, extras =
					World.compile({ name = "T", palette = PALETTE, scale = "r6", build = { { town = s } } })
				check.equal(errorsOf(issues), "")
				check.truthy(#parts > 800)
				local turned = 0
				for _, p in parts do
					if not p.axisAligned then
						turned += 1
					end
				end
				check.truthy(turned > #parts * 0.8)
				local EDGE = { N = { 1, 2 }, E = { 2, 3 }, S = { 3, 4 }, W = { 4, 1 } }
				local byName: { [string]: any } = {}
				for _, lot in plan.lots do
					byName[lot.name] = lot
				end
				local doors = 0
				for _, f in extras.fits do
					local house = string.match(f.name or "", "^(.+) door$")
					if f.kind == "opening" and house and byName[house] then
						local lot = byName[house]
						local q = Town.lotQuad(plan, lot)
						local e = EDGE[lot.front]
						local a, b = q[e[1]], q[e[2]]
						-- how far the door's claim stands from its lot's front line (the wall's middle: half a wall in)
						local vx, vz = b[1] - a[1], b[2] - a[2]
						local len = math.sqrt(vx * vx + vz * vz)
						local off = math.abs((f.pos[1] - a[1]) * vz - (f.pos[3] - a[2]) * vx) / len
						check.truthy(off < 1.6)
						check.equal(f.yaw, plan.bent.blocks[lot.block].turn)
						doors += 1
					end
				end
				check.equal(doors, #plan.lots)
				check.equal(#extras.towns, 1)
				check.equal(extras.towns[1].bend, 8)
				check.truthy(extras.towns[1].lots[1].quad ~= nil)
				check.truthy(#extras.towns[1].streets[1].line >= 2)
			end
		)
	end)
end

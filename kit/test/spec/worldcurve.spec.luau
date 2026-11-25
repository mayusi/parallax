-- worldcurve.spec.luau (kit) — the smooth line through typed points (kit/lib/worldcurve.luau): held to the table of
-- cases its Python twin is held to (kit/test/fixtures/curve_cases.json, kit/test/python/test_world_curve.py), and to
-- its own properties.
local frk = require("../frk")
local test, check = frk.test, frk.check

local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Curve = require("../../lib/worldcurve")
local World = require("../../lib/world")

local PALETTE = { wall = { material = "Concrete", color = { 150, 140, 124 } } }
local CORNER = { { 0, 0 }, { 100, 0 }, { 100, 100 } }

local function compile(build: { any }): ({ any }, string)
	local _, parts, issues = World.compile({ name = "T", palette = PALETTE, build = build })
	local errs = {}
	for _, i in issues do
		if i.severity == "error" then
			table.insert(errs, `{i.path}: {i.message}`)
		end
	end
	return parts, table.concat(errs, " | ")
end

local function named(parts: { any }, name: string): { any }
	local out = {}
	for _, p in parts do
		if p.name == name then
			table.insert(out, p)
		end
	end
	return out
end

-- how far (x, z) is from a line of points
local function offLine(x: number, z: number, line: { { number } }): number
	local best = math.huge
	for i = 2, #line do
		local a, b = line[i - 1], line[i]
		local vx, vz = b[1] - a[1], b[2] - a[2]
		local t = math.clamp(((x - a[1]) * vx + (z - a[2]) * vz) / math.max(vx * vx + vz * vz, 1e-9), 0, 1)
		best = math.min(best, math.sqrt((x - a[1] - vx * t) ^ 2 + (z - a[2] - vz * t) ^ 2))
	end
	return best
end

local function near(a: number, b: number, eps: number?): boolean
	return math.abs(a - b) <= (eps or 1e-9)
end

local function samePoint(a: { number }, b: { number }): boolean
	if #a ~= #b then
		return false
	end
	for i = 1, #a do
		if not near(a[i], b[i]) then
			return false
		end
	end
	return true
end

local function worstJoint(line: { { number } }): number
	local worst = 0
	for i = 2, #line - 1 do
		worst = math.max(worst, Curve.turn(line[i - 1], line[i], line[i + 1]))
	end
	return worst
end

return function()
	test.suite("World curve: a smooth line through typed points", function()
		test.case("every case of the table it shares with the Python twin, number for number", function()
			local cases = serde.decode("json", fs.readFile("kit/test/fixtures/curve_cases.json")).cases
			check.truthy(#cases >= 10)
			for _, c in cases do
				local out =
					Curve.through(c.points, { closed = c.closed, step = c.step, maxTurn = c.maxTurn, least = c.least })
				check.equal(#out, #c.out)
				for i, p in out do
					if not samePoint(p, c.out[i]) then
						error(`{c.name}: point {i} differs from the table`, 0)
					end
				end
				check.truthy(near(Curve.sharpest(c.points), c.sharpest))
			end
		end)

		test.case("the line passes through every typed point in order and ends where it was typed to end", function()
			local seed = 12345
			local function rnd(): number
				seed = (seed * 48271) % 2147483647
				return seed / 2147483647
			end
			for _ = 1, 120 do
				local pts = {}
				for _ = 1, 3 + math.floor(rnd() * 6) do
					table.insert(pts, { rnd() * 600 - 300, rnd() * 600 - 300 })
				end
				local out = Curve.through(pts)
				local at = 1
				for _, p in pts do
					local hit = nil
					for k = at, #out do
						if samePoint(out[k], p) then
							hit = k
							break
						end
					end
					if not hit then
						error("a typed point is not on the line", 0)
					end
					at = hit :: number
				end
				check.truthy(samePoint(out[1], pts[1]))
				check.truthy(samePoint(out[#out], pts[#pts]))
			end
		end)

		test.case("a typed corner becomes many small turns; a ring closes with no corner at its seam", function()
			local corner = { { 0, 0 }, { 100, 0 }, { 100, 100 } }
			check.truthy(near(Curve.sharpest(corner), 90, 1e-6))
			local out = Curve.through(corner)
			check.truthy(#out > 15)
			check.truthy(worstJoint(out) <= 9)
			local ring = Curve.through({ { 100, 0 }, { 0, 100 }, { -100, 0 }, { 0, -100 } }, { closed = true })
			check.truthy(samePoint(ring[1], ring[#ring]))
			check.truthy(worstJoint(ring) <= 9)
			check.truthy(Curve.turn(ring[#ring - 1], ring[1], ring[2]) <= 9)
		end)

		test.case("no piece is longer than the step asked for, none shorter than the least", function()
			for _, step in { 6, 12, 30 } do
				local out = Curve.through({ { 0, 0 }, { 150, 40 }, { 320, -20 }, { 480, 60 } }, { step = step })
				for i = 2, #out do
					local d = math.sqrt((out[i][1] - out[i - 1][1]) ^ 2 + (out[i][2] - out[i - 1][2]) ^ 2)
					check.truthy(d <= step + 1e-6)
					check.truthy(d >= 1 - 1e-6)
				end
			end
		end)

		test.case("a tight corner turns as much a piece as its legs leave room for; options have a floor", function()
			-- (a fresh reader, 2026-11-13: "no joint turns more than maxTurn" was false on ordinary corners)
			local function worst(leg: number): number
				return worstJoint(Curve.through({ { 0, 0 }, { leg, 0 }, { leg, leg } }))
			end
			check.truthy(worst(100) <= 7)
			check.truthy(worst(40) <= 11)
			check.truthy(worst(20) <= 20)
			check.truthy(worst(10) <= 31)
			check.truthy(worst(10) > worst(40))
			local corner = { { 0, 0 }, { 100, 0 }, { 100, 100 } }
			check.truthy(#Curve.through(corner, { step = 0.001 }) < 1200)
			check.equal(#Curve.through(corner, { step = 0.001 }), #Curve.through(corner, { step = 0.5 }))
			local out = Curve.through(corner, { step = 5, least = 40 })
			for i = 2, #out do
				check.truthy(math.sqrt((out[i][1] - out[i - 1][1]) ^ 2 + (out[i][2] - out[i - 1][2]) ^ 2) <= 5 + 1e-6)
			end
			local long = Curve.through({ { 0, 0 }, { 1000, 100 }, { 2000, 0 } })
			for i = 2, #long do
				check.truthy(
					math.sqrt((long[i][1] - long[i - 1][1]) ^ 2 + (long[i][2] - long[i - 1][2]) ^ 2) <= 12 + 1e-6
				)
			end
		end)

		test.case("nothing to curve: one point, two points, a point typed twice", function()
			check.equal(#Curve.through({}), 0)
			check.equal(#Curve.through({ { 3, 4 } }), 1)
			check.equal(#Curve.through({ { 0, 0 }, { 50, 20 } }), 2)
			check.equal(#Curve.through({ { 0, 0 }, { 0, 0 }, { 9, 0 } }), 2)
			check.equal(Curve.sharpest({ { 0, 0 }, { 10, 0 }, { 20, 0 } }), 0)
			check.truthy(near(Curve.sharpest({ { 0, 0 }, { 10, 0 }, { 10, 0 }, { 10, 10 } }), 90, 1e-6))
		end)

		test.case("options typed as nonsense fall back to the defaults", function()
			local pts = { { 0, 0 }, { 80, 10 }, { 160, -10 } }
			local want = Curve.through(pts)
			for _, bad in { 0, -3, "wide", true } :: { any } do
				local got = Curve.through(pts, { step = bad, maxTurn = bad, least = bad })
				check.equal(#got, #want)
			end
			check.equal(#Curve.through(pts, nil), #want)
		end)
	end)

	test.suite("World curve: in the compiler", function()
		test.case("a curved path is many short pieces on the curve, with no square pads at its joints", function()
			local hard, e0 = compile({ { path = { points = CORNER, width = 10, mat = "wall" } } })
			check.equal(e0, "")
			check.equal(#named(hard, "Path"), 2)
			check.equal(#named(hard, "PathJoint"), 1)
			local soft, e1 = compile({ { path = { points = CORNER, width = 10, mat = "wall", curve = true } } })
			check.equal(e1, "")
			local line = Curve.through(CORNER)
			local pieces = named(soft, "Path")
			check.equal(#pieces, #line - 1)
			check.truthy(#pieces > 15)
			check.equal(#named(soft, "PathJoint"), 0)
			for _, p in pieces do
				check.truthy(offLine(p.pos[1], p.pos[3], line) < 0.05) -- (a piece's middle is a chord's middle)
				check.equal(p.size[3], 10)
			end
			-- it still starts and ends where it was typed to
			check.truthy(offLine(0, 0, line) < 1e-9 and offLine(100, 100, line) < 1e-9)
			-- two tops in one plane would flicker where the pieces lap: six in a row lie each at its own height
			for i = 1, #pieces - 5 do
				for j = i + 1, i + 5 do
					check.truthy(math.abs(pieces[i].pos[2] - pieces[j].pos[2]) > 0.009)
				end
			end
		end)

		test.case(
			"a curved path closes its rim at every joint, however sharp, and ends where it was typed to end",
			function()
				-- (a fresh reader: one lap for every joint left the rim open 0.6 studs at a 17-degree joint of a 30-wide
				-- road, and pushed the first and last piece 2.3 studs past the path's typed ends)
				for _, case in { { 40, 30 }, { 100, 12 }, { 20, 12 }, { 10, 8 } } do
					local leg, w = case[1], case[2]
					local typed = { { 0, 0 }, { leg, 0 }, { leg, leg } }
					local line = Curve.through(typed)
					local soft, e = compile({ { path = { points = typed, width = w, mat = "wall", curve = true } } })
					check.equal(e, "")
					local pieces = named(soft, "Path")
					check.equal(#pieces, #line - 1)
					for k, p in pieces do
						local a, b = line[k], line[k + 1]
						local len = math.sqrt((b[1] - a[1]) ^ 2 + (b[2] - a[2]) ^ 2)
						local ux, uz = (b[1] - a[1]) / len, (b[2] - a[2]) / len
						-- how far the piece runs before its first point and past its second, along itself
						local before = p.size[1] / 2 - ((p.pos[1] - a[1]) * ux + (p.pos[3] - a[2]) * uz)
						local past = p.size[1] / 2 - ((b[1] - p.pos[1]) * ux + (b[2] - p.pos[3]) * uz)
						local function need(i: number): number
							if i <= 1 or i >= #line then
								return 0
							end
							return w / 2 * math.tan(math.rad(Curve.turn(line[i - 1], line[i], line[i + 1])) / 2)
						end
						if k == 1 then
							check.truthy(math.abs(before) < 1e-6) -- (the typed start: not a hair past it)
						else
							check.truthy(before >= need(k) - 1e-6)
						end
						if k == #pieces then
							check.truthy(math.abs(past) < 1e-6)
						else
							check.truthy(past >= need(k + 1) - 1e-6)
						end
					end
				end
				-- curbs dip with their pieces: none shares a height with its neighbour
				local curbed = compile({
					{
						path = {
							points = { { 0, 0 }, { 40, 0 }, { 40, 40 } },
							width = 12,
							mat = "wall",
							curve = true,
							curb = { height = 0.6 },
						},
					},
				})
				local curbs = named(curbed, "Curb")
				check.truthy(#curbs > 20)
				for i = 1, #curbs - 2, 2 do
					check.truthy(math.abs(curbs[i].pos[2] - curbs[i + 2].pos[2]) > 0.009)
				end
			end
		)

		test.case(
			'"curve": false is a hard corner, the same as before; the blueprint\'s points are never written to',
			function()
				local spec = { points = CORNER, width = 10, mat = "wall", curve = false }
				local hard = compile({ { path = spec } })
				check.equal(#named(hard, "Path"), 2)
				check.equal(#named(hard, "PathJoint"), 1)
				local typed = { { 0, 0 }, { 100, 0 }, { 100, 100 } }
				local curved = { points = typed, width = 10, mat = "wall", curve = true }
				compile({ { path = curved } })
				check.equal(#typed, 3)
				check.equal(curved.points, typed)
				check.equal(curved.curve, true)
			end
		)

		test.case("a row and a palisade follow the curve: nothing stands on the typed corner's far side", function()
			local line = Curve.through(CORNER)
			local posts = compile({
				{
					row = {
						points = CORNER,
						every = 12,
						item = { size = { 1, 4, 1 }, mat = "wall" },
						mat = "wall",
						curve = true,
					},
				},
			})
			check.truthy(#posts > 10)
			for _, p in posts do
				check.truthy(offLine(p.pos[1], p.pos[3], line) < 0.05)
			end
			local logs, e = compile({ { palisade = { points = CORNER, height = 10, mat = "wall", curve = true } } })
			check.equal(e, "")
			check.truthy(#logs > 60)
			for _, p in logs do
				check.truthy(offLine(p.pos[1], p.pos[3], line) < 0.05)
			end
			-- without the curve the same posts stand on the two straight legs
			local straight = compile({
				{ row = { points = CORNER, every = 12, item = { size = { 1, 4, 1 }, mat = "wall" }, mat = "wall" } },
			})
			for _, p in straight do
				check.truthy(offLine(p.pos[1], p.pos[3], CORNER) < 0.05)
			end
		end)

		test.case(
			"a wall along points: a piece a pair of points, a gap cut where it falls, even across a joint",
			function()
				local function wall(more: any): ({ any }, string)
					local w: any =
						{ name = "Town wall", points = CORNER, y = 0, height = 10, thickness = 2, mat = "wall" }
					for k, v in more do
						w[k] = v
					end
					return compile({ { wall = w } })
				end
				local plain, e0 = wall({})
				check.equal(e0, "")
				check.equal(#named(plain, "Wall"), 2)
				-- a hard corner gets its post: a hair proud of both walls, on the joint, full height
				local posts = named(plain, "WallCorner")
				check.equal(#posts, 1)
				check.truthy(math.abs(posts[1].pos[1] - 100) < 1e-9 and math.abs(posts[1].pos[3]) < 1e-9)
				check.truthy(posts[1].size[1] > 2 and posts[1].size[1] < 2.1 and posts[1].size[2] > 10)
				-- a gate in the middle of the first leg: that leg is two pieces round it and a lintel over it
				local gated, e1 = wall({ gaps = { { at = 50, width = 6, height = 8 } } })
				check.equal(e1, "")
				check.equal(#named(gated, "Wall"), 3)
				check.equal(#named(gated, "Lintel"), 1)
				local lintel = named(gated, "Lintel")[1]
				check.truthy(math.abs(lintel.pos[1] - 50) < 0.2 and math.abs(lintel.pos[3]) < 1e-6)
				check.truthy(math.abs(lintel.size[1] - 6) < 1e-6)
				-- a gate ON the corner (100 studs along): 3 studs of it in each leg
				local corner, e2 = wall({ gaps = { { at = 100, width = 6, height = 8 } } })
				check.equal(e2, "")
				local lintels = named(corner, "Lintel")
				check.equal(#lintels, 2)
				check.truthy(math.abs(lintels[1].size[1] - 3) < 1e-6 and math.abs(lintels[2].size[1] - 3) < 1e-6)
				-- NOTHING stands in the gate: no sliver of wall at the joint, no corner post (a fresh reader found two
				-- 0.12-stud slices of full-height wall in it)
				check.equal(#named(corner, "WallCorner"), 0)
				check.equal(#named(corner, "Wall"), 2)
				for _, p in named(corner, "Wall") do
					check.truthy(p.size[1] > 90) -- (each leg's one long piece: 97 studs)
				end
				-- a gap past the line's end is refused with the line's length
				local _, e3 = wall({ gaps = { { at = 199, width = 6, height = 8 } } })
				check.truthy(string.find(e3, "gap must lie inside the wall's 200 studs of line", 1, true))
				-- curved: many pieces, every one on the curve, the gate still 6 studs wide in all
				local soft, e4 = wall({ curve = true, gaps = { { at = 50, width = 6, height = 8 } } })
				check.equal(e4, "")
				local line = Curve.through(CORNER)
				check.truthy(#named(soft, "Wall") >= #line - 1)
				local open = 0
				for _, l in named(soft, "Lintel") do
					open += l.size[1]
				end
				check.truthy(open >= 6 - 1e-6 and open < 6.2) -- (6 studs of gate, and the laps of the joints inside it)
				-- no fin of wall stands inside the gate: every piece of wall is a real piece
				for _, p in named(soft, "Wall") do
					check.truthy(p.size[1] > 0.5)
				end
				check.equal(#named(soft, "WallCorner"), 0) -- (a curve's joints are gentle: they lap, no posts)
				for _, p in named(soft, "Wall") do
					check.truthy(offLine(p.pos[1], p.pos[3], line) < 0.05)
					check.equal(p.size[2], 10)
					check.equal(p.size[3], 2)
				end
				-- a plain from / to wall is the wall it always was
				local old = compile({
					{ wall = { from = { 0, 0 }, to = { 50, 0 }, y = 0, height = 10, thickness = 2, mat = "wall" } },
				})
				check.equal(#old, 1)
				check.equal(old[1].size[1], 50)
			end
		)

		test.case("a ring closes: a curve told it is closed returns to its first point", function()
			local ring = { { 60, 0 }, { 0, 60 }, { -60, 0 }, { 0, -60 } }
			local logs, e =
				compile({ { palisade = { points = ring, height = 8, mat = "wall", curve = { closed = true } } } })
			check.equal(e, "")
			local farthest, nearest = 0, math.huge
			for _, p in logs do
				local r = math.sqrt(p.pos[1] ^ 2 + p.pos[3] ^ 2)
				farthest, nearest = math.max(farthest, r), math.min(nearest, r)
			end
			check.truthy(nearest > 52 and farthest < 66) -- (round: straight between the four points it dips to 42)
			-- a log stands in the last quarter too (between the fourth point and the first)
			local closing = 0
			for _, p in logs do
				if p.pos[1] > 5 and p.pos[3] < -5 then
					closing += 1
				end
			end
			check.truthy(closing > 10)
		end)

		test.case(
			"what a curve refuses: a step with no line, no points, a word that is not true or false, a bad point",
			function()
				local function refused(step: any, needle: string)
					local _, errs = compile({ step })
					if not string.find(errs, needle, 1, true) then
						error(`expected an error with "{needle}", got: {errs}`, 0)
					end
				end
				refused(
					{ building = { center = { 0, 0, 0 }, size = { 20, 20 }, mat = "wall", curve = true } },
					'a "building" step walks no line'
				)
				refused(
					{ wall = { from = { 0, 0 }, to = { 9, 0 }, height = 9, thickness = 1, mat = "wall", curve = true } },
					'"curve" needs "points"'
				)
				refused(
					{ path = { points = CORNER, width = 10, mat = "wall", curve = "yes" } },
					'"curve" is true, false or'
				)
				refused(
					{ path = { points = CORNER, width = 10, mat = "wall", curve = 1 } },
					'"curve" is true, false or'
				)
				-- a point typed wrongly is an error, never a crash - with a curve or without
				refused(
					{ path = { points = { { 0, 0 }, "x", { 5, 5 } }, width = 10, mat = "wall", curve = true } },
					"every point is [x, z]"
				)
				refused({ path = { points = { { 0, 0 }, { 5 } }, width = 10, mat = "wall" } }, "every point is [x, z]")
				refused(
					{ row = { points = { { 0, 0 }, { "a", 2 } }, item = "lamp", mat = "wall" } },
					"every point is [x, z]"
				)
				refused(
					{ wall = { points = { { 0, 0 } }, height = 9, thickness = 1, mat = "wall" } },
					"needs at least 2 points"
				)
				refused(
					{ wall = { points = { { 0, 0 }, { 0, 0 } }, height = 9, thickness = 1, mat = "wall" } },
					"two points that are apart"
				)
				-- a curved wall's short pieces would each start their own battlement
				refused({
					wall = {
						points = CORNER,
						height = 9,
						thickness = 2,
						mat = "wall",
						curve = true,
						crenels = true,
					},
				}, 'a curved wall takes no "crenels"')
			end
		)
	end)
end

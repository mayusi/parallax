-- worldturn.spec.luau (kit) — "turn" on a blueprint step (kit/lib/world.luau): everything the step made - its parts
-- and its scale claims - turned about a vertical line. A turned house is the SAME house standing at another angle.
local frk = require("../frk")
local test, check = frk.test, frk.check

local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Environment = require("../../lib/environment")
local World = require("../../lib/world")

local PALETTE = {
	wall = { material = "Concrete", color = { 150, 140, 124 } },
	slate = { material = "Slate", color = { 58, 60, 68 } },
	glass = { material = "Glass", color = { 150, 170, 190 } },
}

local function house(more: any?): any
	local b: any = {
		name = "House",
		center = { 40, 0, -20 },
		size = { 20, 28 },
		floors = 2,
		mat = "wall",
		roof = "gable",
		roofMat = "slate",
		glass = "glass",
		trim = "slate",
		stairs = true,
		door = { side = "S", width = 5, height = 8.5 },
	}
	for k, v in more or {} do
		b[k] = v
	end
	return b
end

local function compile(build: { any }): ({ any }, { any }, any)
	local _, parts, issues, extras = World.compile({ name = "T", palette = PALETTE, build = build })
	return parts, issues, extras
end

local function errorsOf(issues: { any }): string
	local out = {}
	for _, i in issues do
		if i.severity == "error" then
			table.insert(out, `{i.path}: {i.message}`)
		end
	end
	return table.concat(out, " | ")
end

local function near(a: number, b: number, eps: number?): boolean
	return math.abs(a - b) <= (eps or 1e-6)
end

-- a point turned the way the compiler says it turns one
local function turned(p: { number }, px: number, pz: number, deg: number): { number }
	local x, z = World.turnPoint(p[1], p[3], px, pz, deg)
	return { x, p[2], z }
end

-- the 8 corners of a part in the world
local function corners(p: any): { { number } }
	local out = {}
	for _, sx in { -1, 1 } do
		for _, sy in { -1, 1 } do
			for _, sz in { -1, 1 } do
				local l = { sx * p.size[1] / 2, sy * p.size[2] / 2, sz * p.size[3] / 2 }
				table.insert(out, {
					p.pos[1] + p.rot[1][1] * l[1] + p.rot[1][2] * l[2] + p.rot[1][3] * l[3],
					p.pos[2] + p.rot[2][1] * l[1] + p.rot[2][2] * l[2] + p.rot[2][3] * l[3],
					p.pos[3] + p.rot[3][1] * l[1] + p.rot[3][2] * l[2] + p.rot[3][3] * l[3],
				})
			end
		end
	end
	return out
end

return function()
	test.suite("World turn: a step on any angle", function()
		test.case("the turn is CFrame.Angles(0, yaw, 0): +X swings toward -Z, a quarter turn is exact", function()
			local x, z = World.turnPoint(10, 0, 0, 0, 90)
			check.equal(x, 0)
			check.equal(z, -10)
			local m = World.turnMatrix(90)
			check.equal(m[1][1], 0)
			check.equal(m[1][3], 1)
			check.equal(m[3][1], -1)
			check.equal(World.turnMatrix(180)[1][1], -1)
			check.equal(World.turnMatrix(-270)[1][3], 1)
			local a, b = World.turnPoint(7, 3, 2, 1, 360)
			check.truthy(near(a, 7) and near(b, 3))
			-- the same matrix the compiler's rotation gives for a yaw (one convention, never two)
			local r = World.rotation({ 0, 37, 0 })
			local t = World.turnMatrix(37)
			for i = 1, 3 do
				for j = 1, 3 do
					check.truthy(near(r[i][j], t[i][j], 1e-12))
				end
			end
		end)

		test.case("every corner of every part of a turned house is the plain house's corner, turned", function()
			local plain, issues0 = compile({ { building = house() } })
			check.equal(errorsOf(issues0), "")
			check.truthy(#plain > 40)
			for _, deg in { 30, 90, -45, 200 } do
				local got, issues = compile({ { building = house({ turn = deg }) } })
				check.equal(errorsOf(issues), "")
				check.equal(#got, #plain)
				for i, p in plain do
					local q = got[i]
					check.equal(q.name, p.name)
					for k = 1, 3 do
						check.equal(q.size[k], p.size[k])
					end
					local want, have = corners(p), corners(q)
					for c = 1, 8 do
						local w = turned(want[c], 40, -20, deg)
						if not (near(have[c][1], w[1]) and near(have[c][2], w[2]) and near(have[c][3], w[3])) then
							error(`turn {deg}: part {i} ({p.name}) corner {c} is not the plain one turned`, 0)
						end
					end
				end
			end
		end)

		test.case("no turn, a turn of 0 and a whole turn leave the house exactly as it was", function()
			local plain = compile({ { building = house() } })
			for _, deg in { 0, 360, -720 } do
				local got = compile({ { building = house({ turn = deg }) } })
				check.equal(#got, #plain)
				for i, p in plain do
					for k = 1, 3 do
						check.equal(got[i].pos[k], p.pos[k])
						for j = 1, 3 do
							check.equal(got[i].rot[k][j], p.rot[k][j])
						end
					end
					check.equal(got[i].axisAligned, p.axisAligned)
				end
			end
		end)

		test.case("a turned part is no longer called axis-aligned; a whole turn back is", function()
			local got = compile({ { building = house({ turn = 30 }) } })
			for _, p in got do
				check.falsy(p.axisAligned)
			end
			local plain = compile({ { building = house() } })
			local back = compile({ { building = house({ turn = 360 }) } })
			local some = false
			for i, p in plain do
				check.equal(back[i].axisAligned, p.axisAligned)
				some = some or p.axisAligned
			end
			check.truthy(some) -- (the plain house has axis-aligned parts for this to mean anything)
		end)

		test.case("a part under the land is dropped by where it WILL stand, not by where it was typed", function()
			-- (a fresh reader, 2026-11-13: the cull ran before the turn - a part typed under a hill and turned onto
			-- open ground vanished without a word, and one turned INTO the hill was kept)
			local valley = serde.decode("json", fs.readFile("kit/selftest/world/_selftest_valley.json"))
			local ground = nil
			for _, op in Environment.compile(valley).terrain do
				if op.kind == "ground" then
					ground = op.spec
				end
			end
			check.truthy(ground ~= nil)
			-- the land's highest and lowest spots on a coarse walk of the fixture
			local hi, lo = { 0, 0, -math.huge }, { 0, 0, math.huge }
			for x = -100, 100, 20 do -- (well inside the 256-stud map: off it there is no land to be under)
				for z = -100, 100, 20 do
					local h = World.groundHeight(ground, x, z)
					if h > hi[3] then
						hi = { x, z, h }
					end
					if h < lo[3] then
						lo = { x, z, h }
					end
				end
			end
			check.truthy(hi[3] - lo[3] > 12)
			local y = lo[3] + 4 -- over the low ground, deep under the high
			local mid = { (hi[1] + lo[1]) / 2, (hi[2] + lo[2]) / 2 }
			local function crate(at: { number }, turn: number?): number
				local bp = table.clone(valley)
				bp.build = {
					{
						part = {
							name = "Crate",
							size = { 3, 3, 3 },
							pos = { at[1], y, at[2] },
							mat = next(valley.palette),
							turn = turn,
							about = if turn then mid else nil,
						},
					},
				}
				local _, parts = World.compile(bp)
				local n = 0
				for _, p in parts do
					if p.name == "Crate" then
						n += 1
					end
				end
				return n
			end
			check.equal(crate(lo), 1) -- typed on the low ground: kept
			check.equal(crate(hi), 0) -- typed under the hill: dropped
			check.equal(crate(hi, 180), 1) -- typed under the hill, turned onto the low ground: KEPT
			check.equal(crate(lo, 180), 0) -- typed on the low ground, turned into the hill: dropped
		end)

		test.case("the scale claims turn with the house: same sizes, turned places, their yaw kept", function()
			local _, _, e0 = compile({ { building = house() } })
			local _, _, e1 = compile({ { building = house({ turn = 30 }) } })
			check.truthy(#e0.fits >= 3) -- (a ceiling a floor, the door, the stairs)
			check.equal(#e1.fits, #e0.fits)
			local door0, door1 = nil, nil
			for i, f in e0.fits do
				local g = e1.fits[i]
				check.equal(g.kind, f.kind)
				check.equal(g.name, f.name)
				check.equal(f.yaw, nil)
				check.equal(g.yaw, 30)
				local w = turned(f.pos, 40, -20, 30)
				check.truthy(near(g.pos[1], w[1]) and near(g.pos[2], w[2]) and near(g.pos[3], w[3]))
				if f.size then
					for k = 1, 3 do
						check.equal(g.size[k], f.size[k])
					end
				end
				if f.kind == "opening" then
					door0, door1 = f, g
				end
			end
			-- the door was on the south wall, 14 studs south of the centre: turned 30 it stands off both axes
			check.truthy(door0 ~= nil and door1 ~= nil)
			check.truthy(near(door0.pos[1], 40) and near(door0.pos[3], -6))
			check.truthy(near(door1.pos[1], 40 + 14 * math.sin(math.rad(30))))
			check.truthy(near(door1.pos[3], -20 + 14 * math.cos(math.rad(30))))
		end)

		test.case("only the turned step turns: its neighbours in the build list stay where they were typed", function()
			local other =
				{ part = { name = "Marker", size = { 2, 10, 2 }, pos = { -30, 5, 9 }, mat = "wall", fit = "rail" } }
			local alone, _, ea = compile({ other })
			for _, order in { "before", "after" } do
				local build = if order == "before"
					then { other, { building = house({ turn = 70 }) } }
					else { { building = house({ turn = 70 }) }, other }
				local got, issues, extras = compile(build)
				check.equal(errorsOf(issues), "")
				local post, postFit = nil, nil
				for _, p in got do
					if p.name == "Marker" then
						post = p
					end
				end
				for _, f in extras.fits do
					if f.name == "Marker" then
						postFit = f
					end
				end
				check.truthy(post ~= nil and postFit ~= nil)
				for k = 1, 3 do
					check.equal(post.pos[k], alone[1].pos[k])
					check.equal(postFit.pos[k], ea.fits[1].pos[k])
				end
				check.truthy(post.axisAligned)
				check.equal(postFit.yaw, nil)
			end
		end)

		test.case("the LAST step of a blueprint is turned before the gates read it", function()
			local got = compile({
				{ part = { name = "Slab", size = { 40, 1, 4 }, pos = { 0, 0.5, 0 }, mat = "wall", turn = 90 } },
			})
			check.equal(#got, 1)
			-- its long side now runs along Z
			local span = 0
			for _, c in corners(got[1]) do
				span = math.max(span, math.abs(c[3]))
			end
			check.truthy(near(span, 20))
		end)

		test.case('"about" is another point to turn round; a wall turns round its own middle', function()
			local got = compile({
				{
					part = {
						name = "P",
						size = { 2, 2, 2 },
						pos = { 10, 1, 0 },
						mat = "wall",
						turn = 90,
						about = { 0, 0 },
					},
				},
			})
			check.truthy(near(got[1].pos[1], 0) and near(got[1].pos[3], -10))
			local wall = function(turn: number?)
				return compile({
					{
						wall = {
							name = "W",
							from = { 0, 0 },
							to = { 20, 0 },
							y = 0,
							height = 10,
							thickness = 1,
							mat = "wall",
							turn = turn,
						},
					},
				})
			end
			local w0, w90 = wall(nil), wall(90)
			check.equal(#w0, 1)
			check.truthy(near(w90[1].pos[1], 10) and near(w90[1].pos[3], 0))
			local reach = 0
			for _, c in corners(w90[1]) do
				reach = math.max(reach, math.abs(c[3]))
			end
			check.truthy(near(reach, 10))
		end)

		test.case("a claim typed beside turned things turns with them", function()
			local _, issues, extras = compile({
				{
					fit = {
						kind = "alley",
						name = "Lane",
						pos = { 0, 0, 0 },
						from = { -30, 0 },
						to = { 30, 0 },
						turn = 90,
						about = { 0, 0 },
					},
				},
			})
			check.equal(errorsOf(issues), "")
			local f = extras.fits[1]
			check.truthy(near(f.from[1], 0) and near(f.from[2], 30))
			check.truthy(near(f.to[1], 0) and near(f.to[2], -30))
			check.equal(f.yaw, 90)
		end)

		test.case("the blueprint's own tables are never written to", function()
			local pos = { 10, 1, 0 }
			local spec =
				{ name = "P", size = { 2, 2, 2 }, pos = pos, mat = "wall", turn = 90, about = { 0, 0 }, fit = "rail" }
			compile({ { part = spec } })
			check.equal(pos[1], 10)
			check.equal(pos[3], 0)
			check.equal(spec.turn, 90)
		end)

		test.case(
			"what a turn refuses: not a number, a step that reads the land, a step set on the land, no point",
			function()
				local function refused(step: any, needle: string)
					local _, issues = compile({ step })
					local text = errorsOf(issues)
					if not string.find(text, needle, 1, true) then
						error(`expected an error with "{needle}", got: {text}`, 0)
					end
				end
				refused({ building = house({ turn = "east" }) }, '"turn" is a number of degrees')
				refused({ building = house({ turn = 0 / 0 }) }, '"turn" is a number of degrees')
				refused({ building = house({ turn = math.huge }) }, '"turn" is a number of degrees')
				refused(
					{ path = { name = "Road", points = { { 0, 0 }, { 50, 0 } }, width = 8, mat = "wall", turn = 20 } },
					'a "path" step is not turned'
				)
				refused({ building = house({ turn = 20, ground = true }) }, '"turn" and "ground": true together')
				refused({ building = house({ turn = 20, about = { "x", 3 } }) }, '"about" is the point')
				-- (every other point of a blueprint is [x, y, z]: three numbers here are refused, never read as x and z)
				refused({ building = house({ turn = 20, about = { 0, 5, 0 } }) }, '"about" is the point')
				refused({ building = house({ turn = 20, about = { 4 } }) }, '"about" is the point')
				-- stairs and a grid have no centre of their own: they turn round "about"
				refused({
					stairs = {
						start = { 0, 0, 0 },
						dir = "+X",
						steps = 4,
						rise = 1,
						run = 2,
						width = 6,
						mat = "wall",
						turn = 20,
					},
				}, "needs a point to turn round")
				-- a town is bent by its own "bend": a "turn" typed on it is an error, never ignored
				refused({
					town = {
						name = "Old Town",
						area = { 256, 224 },
						gates = { "S" },
						mats = { street = "wall", wall = "wall", roof = "wall" },
						turn = 30,
					},
				}, 'a town is not turned by "turn"')
				refused(
					{ spawn = { pos = { 0, 0, 0 }, mat = "wall", turn = 30 } },
					'a "spawn" step is not turned by "turn": type it where'
				)
				refused(
					{ part = { name = "P", size = { 2, 2, 2 }, mat = "wall", turn = 20 } },
					"needs a point to turn round"
				)
				for kind in World.TURNABLE do
					check.truthy(kind ~= "path" and kind ~= "forest" and kind ~= "scatter" and kind ~= "town")
				end
			end
		)
	end)
end

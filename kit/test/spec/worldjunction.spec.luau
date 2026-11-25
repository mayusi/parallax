-- worldjunction.spec.luau (kit) — WHERE ROADS ON THE LAND MEET (LIMITATIONS_FIXES_V4 5.1 / 13.5, card E8: "banked Y/T
-- road junctions"; kit/lib/worldjunction.luau). Before, a lane ending on a road laid its pieces over the road's: two
-- surfaces at two rolls, one standing out of the other, their tops in one plane over the overlap.
-- Held here on lands made by hand (level, and an 8-degree fall across the through road): a T and a Y each get ONE
-- round pad at the node, in the land's plane; no road piece lies inside the pad (every road is cut at its rim); the
-- piece at the rim lies at the pad's roll (within half a degree) and its end on the pad's plane; roads that do not
-- meet, a world laid before (World.ROAD_V3_BEFORE) and "junction": false get none. The pure finder and cutter are
-- held on their own (a T, a Y, a road passing through a disc whole, a cut end's corners inside the rim).
-- Not claimed: how a pad looks in Roblox (a Cylinder part, not yet seen in Studio).
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Junction = require("../../lib/worldjunction")
local World = require("../../lib/world")

local DIR = "build/selftest/worldjunction"
local N, STEP = 33, 4

local function land(name: string, h: (number, number) -> number): string
	if not fs.isDir(DIR) then
		fs.writeDir(DIR)
	end
	local heights = {}
	for ix = 0, N - 1 do
		for iz = 0, N - 1 do
			table.insert(heights, h(-64 + ix * STEP, -64 + iz * STEP))
		end
	end
	local path = `{DIR}/{name}.hm.json`
	fs.writeFile(path, serde.encode("json", { nx = N, nz = N, step = STEP, heights = heights }))
	return path
end

local function road(name: string, points: { { number } }, more: any?): any
	local r: any = { name = name, mat = "stone", width = 8, ground = true, curve = false, points = points }
	for k, v in more or {} do
		r[k] = v
	end
	return { path = r }
end

local function compile(source: string, steps: { any }, worldName: string?): ({ any }, any, { string })
	local _, parts, issues, info = World.compile({
		name = worldName or "J",
		palette = { stone = { material = "Cobblestone", color = { 120, 118, 112 } } },
		lighting = "noon",
		terrain = { { heightmap = { center = { 0, 0, 0 }, size = { 128, 128 }, source = source, material = "Grass" } } },
		build = steps,
	}, { meshes = {} })
	local errors = {}
	for _, i in issues do
		if i.severity == "error" and i.path ~= "spawn" then
			table.insert(errors, i.message)
		end
	end
	return parts, info, errors
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

-- the roll of a road piece: how far its Z column (its width) rises over a stud, as an angle
local function rollOf(p: any): number
	local zy = p.rot[2][3]
	return math.deg(math.asin(math.clamp(zy, -1, 1)))
end

-- a land falling 8 degrees toward +z (across a through road along x)
local function across8(_x: number, z: number): number
	return -z * math.tan(math.rad(8)) + 20
end

local T = {
	road("Main", { { -60, 0 }, { 60, 0 } }),
	road("Lane", { { 0, -56 }, { 0, 0 } }), -- (ends ON the main road: a T)
}

return function()
	test.suite("Where roads on the land meet: banked Y and T junctions", function()
		test.case("a T on a side slope gets one pad at the node, in the land's plane", function()
			local parts, info, errors = compile(land("t8", across8), T)
			check.truthy(#errors == 0, table.concat(errors, "; "))
			local pads = named(parts, "Junction")
			check.truthy(#pads == 1, `{#pads} pads`)
			local pad = pads[1]
			check.truthy(pad.shape == "Cylinder", `a {tostring(pad.shape)}`)
			check.truthy(
				math.abs(pad.pos[1]) < 0.3 and math.abs(pad.pos[3]) < 0.3,
				`the pad at {pad.pos[1]}, {pad.pos[3]}`
			)
			-- its axis (X) is the plane's normal: the land falls 8 degrees across z, so the normal leans 8 degrees
			local lean = math.deg(math.acos(math.clamp(pad.rot[2][1], -1, 1)))
			check.truthy(math.abs(lean - 8) < 0.5, `the pad leans {lean} degrees`)
			check.truthy(#info.junctions == 1 and info.junctions[1].kind == "T", "the record says one T")
			check.truthy(info.junctions[1].arms == 2, `{info.junctions[1].arms} arms (a lane end and the road through)`)
		end)

		test.case(
			"no road piece lies inside a pad: every road is cut at its rim, its corners inside the disc",
			function()
				local parts = compile(land("t8b", across8), T)
				local pad = named(parts, "Junction")[1]
				local r = pad.size[2] / 2
				local n = 0
				for _, p in parts do
					if p.name == "Road" then
						local d = math.sqrt(p.pos[1] ^ 2 + p.pos[3] ^ 2)
						check.truthy(
							d >= r - 2.5,
							`a road piece's middle {d} studs from the node, inside the {r}-stud pad`
						)
						n += 1
					end
				end
				check.truthy(n > 10, `{n} road pieces`)
				-- the lane's last piece reaches into the disc: its far end corners (half its width out) lie within the rim
				local nearest, best = nil, math.huge
				for _, p in parts do
					if p.name == "Road" and math.abs(p.pos[1]) < 1 then
						local d = math.abs(p.pos[3])
						if d < best then
							nearest, best = p, d
						end
					end
				end
				check.truthy(nearest ~= nil, "a lane piece by the pad")
				local tip = math.abs(nearest.pos[3]) - nearest.size[1] / 2
				check.truthy(
					math.sqrt(tip ^ 2 + 4 ^ 2) <= r + 0.05,
					`its end's corner {math.sqrt(tip ^ 2 + 16)} studs out, the rim {r}`
				)
			end
		)

		test.case("the piece at the rim lies at the pad's roll; one an ease away at the land's", function()
			local parts = compile(land("t8c", across8), T)
			-- the main road's pieces (along x) on the 8-degree fall across them: the land's roll is 8 (capped at 12)
			local atRim, far = nil, nil
			for _, p in parts do
				if p.name == "Road" and math.abs(p.pos[3]) < 0.5 then
					local d = math.abs(p.pos[1])
					if atRim == nil or d < math.abs(atRim.pos[1]) then
						atRim = p
					end
					if d > 40 and far == nil then
						far = p
					end
				end
			end
			check.truthy(atRim ~= nil and far ~= nil, "pieces of the main road")
			check.truthy(
				math.abs(math.abs(rollOf(far)) - 8) < 0.6,
				`far from the node it rolls {rollOf(far)} (the land's 8)`
			)
			-- the lane runs down the fall (along z): its pad roll is ~0 across it, its land roll 0 too; the main road's
			-- pad roll is the plane's 8 degrees - the same as the land's here, so ask the plane on a curved land below
			check.truthy(math.abs(math.abs(rollOf(atRim)) - 8) < 0.6, `at the rim it rolls {rollOf(atRim)}`)
		end)

		test.case("on a land that is not a plane the rim piece takes the PAD's roll, not the land's", function()
			-- a saddle: z falls one way west of the node, the other east; the plane that fits round the node is level
			local saddle = function(x: number, z: number): number
				return 20 + x * z * 0.004
			end
			local parts = compile(land("saddle", saddle), T)
			local pad = named(parts, "Junction")[1]
			check.truthy(pad ~= nil, "a pad")
			local r = pad.size[2] / 2
			local rimPiece, mid = nil, nil
			for _, p in parts do
				if p.name == "Road" and math.abs(p.pos[3]) < 0.5 and p.pos[1] > 0 then
					if rimPiece == nil or p.pos[1] < rimPiece.pos[1] then
						rimPiece = p
					end
					if p.pos[1] > r + Junction.EASE + 6 and (mid == nil or p.pos[1] < mid.pos[1]) then
						mid = p
					end
				end
			end
			check.truthy(rimPiece ~= nil and mid ~= nil, "pieces east of the node")
			-- the saddle's fall across the road at x: d/dz = 0.004 x; the plane round the node is level (roll 0)
			check.truthy(math.abs(rollOf(rimPiece)) < 0.5, `the rim piece rolls {rollOf(rimPiece)} (the pad's 0)`)
			local landRoll = math.deg(math.atan(0.004 * mid.pos[1]))
			check.truthy(
				math.abs(math.abs(rollOf(mid)) - landRoll) < 0.6,
				`past the ease it rolls {rollOf(mid)} (the land's {landRoll})`
			)
			-- the rim piece's top meets the pad's plane: its near end's height over the plane's within a tenth
			local tip = rimPiece.pos[1] - rimPiece.size[1] / 2 * rimPiece.rot[1][1]
			local topAt = rimPiece.pos[2]
				+ rimPiece.size[2] / 2 * rimPiece.rot[2][2]
				- (rimPiece.pos[1] - tip) * rimPiece.rot[2][1] / math.max(rimPiece.rot[1][1], 1e-6)
			check.truthy(math.abs(topAt - 20) < 0.15, `its end's top at {topAt}, the pad's plane at 20`)
		end)

		test.case("a Y: three roads ending at one spot get one pad, three arms", function()
			local parts, info = compile(
				land("y", function(_x, _z)
					return 10
				end),
				{
					road("A", { { -50, -40 }, { 0, 0 } }),
					road("B", { { 50, -40 }, { 0, 0 } }),
					road("C", { { 0, 56 }, { 0, 1 } }),
				}
			)
			local pads = named(parts, "Junction")
			check.truthy(#pads == 1, `{#pads} pads`)
			check.truthy(
				info.junctions[1].kind == "Y" and info.junctions[1].arms == 3,
				`{info.junctions[1].kind} of {info.junctions[1].arms}`
			)
			-- level land: the pad's top a lift over the roads' tops (10), no road top in its plane
			local top = pads[1].pos[2] + pads[1].size[1] / 2
			check.truthy(math.abs(top - (10 + Junction.LIFT)) < 0.01, `the pad's top at {top}`)
		end)

		test.case("on a crowned land the pad stands clear of the land all over its disc", function()
			-- a crown 2 studs high over 30 (the plane that fits it best lies under its middle)
			local crown = function(x: number, z: number): number
				return 20 + 2 * math.cos(math.min(math.sqrt(x * x + z * z) / 30, 1) * math.pi / 2)
			end
			local parts, info = compile(land("crown", crown), T)
			local pad = named(parts, "Junction")[1]
			check.truthy(pad ~= nil, "a pad")
			local top = pad.pos[2] + pad.size[1] / 2 * pad.rot[2][1]
			local r = pad.size[2] / 2
			for i = -4, 4 do
				for j = -4, 4 do
					local x, z = i / 4 * r, j / 4 * r
					if x * x + z * z <= r * r then
						-- (the pad is level here: the crown is round about the node)
						check.truthy(
							top >= crown(x, z) + Junction.LIFT - 0.03, -- (the bilinear land under a crown lies a hair under it)
							`the land at {x}, {z} ({crown(x, z)}) over the pad's top {top}`
						)
					end
				end
			end
			check.truthy(info.junctions[1].tilt < 0.5, `the pad tilts {info.junctions[1].tilt}`)
		end)

		test.case("roads that do not meet, a world laid before and junction false get no pad", function()
			local flat = land("flat", function(_x, _z)
				return 0
			end)
			local parts =
				compile(flat, { road("A", { { -60, -20 }, { 60, -20 } }), road("B", { { -60, 20 }, { 60, 20 } }) })
			check.truthy(#named(parts, "Junction") == 0, "two roads apart")
			World.ROAD_V3_BEFORE.SampleRegion = true -- (a project's built world: the kit ships the list empty)
			parts = compile(flat, T, "SampleRegion")
			check.truthy(#named(parts, "Junction") == 0, "a world laid before the junctions")
			parts = compile(flat, { T[1], road("Lane", { { 0, -56 }, { 0, 0 } }, { junction = false }) })
			check.truthy(#named(parts, "Junction") == 0, '"junction": false')
			parts = compile(flat, {
				road("Main", { { -60, 0 }, { 60, 0 } }, { junction = true }),
				road("Lane", { { 0, -56 }, { 0, 0 } }, { junction = true }),
			}, "SampleRegion")
			World.ROAD_V3_BEFORE.SampleRegion = nil
			check.truthy(#named(parts, "Junction") == 1, 'a world laid before says "junction": true')
		end)

		test.case("the finder: a T on the line, a Y of ends, nothing for a near miss", function()
			local nodes = Junction.find({
				{ id = 1, points = { { -50, 0 }, { 50, 0 } }, width = 8 },
				{ id = 2, points = { { 10, -40 }, { 10, 3 } }, width = 6 },
			})
			check.truthy(#nodes == 1 and nodes[1].kind == "T", "a T")
			check.truthy(
				math.abs(nodes[1].x - 10) < 1e-6 and math.abs(nodes[1].z) < 1e-6,
				`at {nodes[1].x}, {nodes[1].z}`
			)
			-- (past half the overlap of the 8- and 6-stud strips crossing square: half of sqrt(8^2 + 6^2), and a stud)
			check.truthy(math.abs(nodes[1].r - 6) < 1e-9, `radius {nodes[1].r}`)
			nodes = Junction.find({
				{ id = 1, points = { { -50, 0 }, { 50, 0 } }, width = 8 },
				{ id = 2, points = { { 10, -40 }, { 10, -6 } }, width = 6 },
			})
			check.truthy(#nodes == 0, "an end 6 studs from the line (half the width and half a stud is 4.5)")
		end)

		test.case("the cutter: a road through a disc is two runs, each cut end's corners inside the rim", function()
			local nd: any = { x = 0, z = 0, r = 6, kind = "T", arms = {} }
			local runs = Junction.cut({ { -30, 0 }, { 30, 0 } }, { nd }, 8)
			check.truthy(#runs == 2, `{#runs} runs`)
			local e1 = runs[1][#runs[1]]
			local e2 = runs[2][1]
			local s = Junction.sagitta(6, 8)
			check.truthy(
				math.abs(e1[1] + (6 - s)) < 1e-6 and math.abs(e2[1] - (6 - s)) < 1e-6,
				`cut at {e1[1]} and {e2[1]}`
			)
			check.truthy(math.sqrt((6 - s) ^ 2 + 16) <= 6 + 1e-9, "the corners of a cut end inside the rim")
			-- a lane that ends inside the disc: one run, cut at the rim
			runs = Junction.cut({ { 0, -30 }, { 0, 0 } }, { nd }, 8)
			check.truthy(#runs == 1 and math.abs(runs[1][#runs[1]][2] + (6 - s)) < 1e-6, "a lane cut at the rim")
			-- no node: the line whole
			check.truthy(#Junction.cut({ { 0, 0 }, { 5, 5 } }, {}, 8) == 1, "no node")
		end)
	end)
end

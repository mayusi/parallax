-- worldtownslope.spec.luau (kit) — a town on a slope (kit/lib/worldtown.luau, "A TOWN ON A SLOPE"): the ground one
-- hillside of tilted plates cut round the houses, each house level at its own door's height, everything else at the
-- ground's height where it stands. What the plan promises of it, and what the compiler makes of one.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Town = require("../../lib/worldtown")
local World = require("../../lib/world")

local MATS = {
	street = "cobble",
	square = "flag",
	block = "pave",
	wall = "plaster",
	roof = "slate",
	yard = "pave",
	stall = "timber",
	cloth = "cloth",
	lamp = "iron",
	lampLight = "glow",
	spawn = "spawn",
}
local PALETTE = {
	cobble = { material = "Cobblestone", color = { 84, 82, 80 } },
	flag = { material = "Slate", color = { 110, 104, 92 } },
	pave = { material = "Slate", color = { 98, 96, 94 } },
	plaster = { material = "Concrete", color = { 150, 140, 124 } },
	slate = { material = "Slate", color = { 58, 60, 68 } },
	timber = { material = "Wood", color = { 96, 72, 48 } },
	cloth = { material = "Fabric", color = { 150, 60, 50 } },
	iron = { material = "Metal", color = { 30, 30, 34 } },
	glow = { material = "Neon", color = { 255, 200, 140 } },
	spawn = { material = "Neon", color = { 120, 240, 200 } },
}
local SHAPES = {
	{ area = { 256, 224 }, gates = { "S" } },
	{ area = { 320, 320 }, gates = { "S", "N" } },
	{ area = { 400, 320 }, gates = { "S", "E", "W" } },
}
local SIDES = { "N", "E", "S", "W" }

local function spec(seed: number, shape: any, slope: any, more: any?): any
	local s: any = {
		center = { 0, 0, 0 },
		area = shape.area,
		seed = seed,
		gates = shape.gates,
		mats = MATS,
		bend = 0,
		slope = slope,
		market = true,
		yards = true,
		lamps = true,
		spawns = 2,
	}
	for k, v in more or {} do
		s[k] = v
	end
	-- (a town too small for a market or with no yard to dress says so: this spec then asks for none there - the
	-- same in the sloped town and its level twin, since the slope changes nothing of the plan)
	local probe = table.clone(s)
	probe.slope = false
	probe.bend = 0
	for _, i in Town.plan(probe).issues do
		if i.severity == "error" and string.find(i.message, '"yards": true, but', 1, true) then
			s.yards = false
		elseif i.severity == "error" and string.find(i.message, '"market": true, but', 1, true) then
			s.market = false
		end
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

-- the ground's height, worked out HERE (not by the rule's own function): 0 at the middle of the area, `rise` studs
-- higher every 100 studs toward the side named
local function ground(plan: any, slope: any, x: number, z: number): number
	local A = plan.area
	local cx, cz = (A.x0 + A.x1) / 2, (A.z0 + A.z1) / 2
	local g = slope.rise / 100
	if slope.toward == "N" then
		return g * (cz - z)
	elseif slope.toward == "S" then
		return g * (z - cz)
	elseif slope.toward == "E" then
		return g * (x - cx)
	end
	return g * (cx - x)
end

local function stepsOf(s: any): ({ any }, any)
	local plan = Town.plan(s)
	check.equal(errorsOf(plan.issues), "")
	return Town.steps(plan, s), plan
end

return function()
	test.suite("Town slope: the hillside", function()
		test.case("the ground is 0 at the middle and rises `rise` studs in 100 toward the side named", function()
			for _, side in SIDES do
				local slope = { rise = 4, toward = side }
				local plan = Town.plan(spec(1, SHAPES[2], slope))
				check.equal(errorsOf(plan.issues), "")
				check.truthy(near(Town.groundAt(plan, 0, 0), 0))
				local ux, uz = 0, 0
				if side == "N" then
					uz = -1
				elseif side == "S" then
					uz = 1
				elseif side == "E" then
					ux = 1
				else
					ux = -1
				end
				check.truthy(near(Town.groundAt(plan, 100 * ux, 100 * uz), 4))
				check.truthy(near(Town.groundAt(plan, -50 * ux, -50 * uz), -2))
				-- level across the hill
				check.truthy(near(Town.groundAt(plan, 70 * uz, 70 * ux), 0))
				for _, pt in { { 13, -77 }, { -120, 31 }, { 64, 150 } } do
					check.truthy(near(Town.groundAt(plan, pt[1], pt[2]), ground(plan, slope, pt[1], pt[2])))
				end
			end
			-- a level town's ground is 0 everywhere
			local flat = Town.plan(spec(1, SHAPES[2], false))
			check.equal(flat.slope, nil)
			check.equal(Town.groundAt(flat, 90, -120), 0)
		end)

		test.case('what "slope" refuses; a bent town on a slope is not built and says so', function()
			local function err(slope: any, more: any?): string
				return errorsOf(Town.plan(spec(1, SHAPES[1], slope, more)).issues)
			end
			for _, bad in
				{
					{ rise = 0, toward = "N" },
					{ rise = 7, toward = "N" },
					{ rise = -2, toward = "S" },
					{ rise = 3, toward = "up" },
					{ rise = "3", toward = "N" },
					{ toward = "N" },
					"yes",
					true,
					4,
				} :: { any }
			do
				check.truthy(string.find(err(bad), '"slope" is false (level ground) or', 1, true))
			end
			check.equal(err(false), "")
			check.equal(err(nil), "")
			check.equal(err({ rise = 6, toward = "W" }), "")
			check.equal(err({ rise = 0.5, toward = "E" }), "")
			check.truthy(
				string.find(
					err({ rise = 3, toward = "N" }, { bend = 6 }),
					"a bent town on a slope is not built yet",
					1,
					true
				)
			)
			check.equal(Town.plan(spec(1, SHAPES[1], { rise = 3, toward = "N" }, { bend = 6 })).slope, nil)
		end)

		test.case('"slope": false and no word at all build the very town the plan built before', function()
			local a = Town.steps(Town.plan(spec(2, SHAPES[2], false)), spec(2, SHAPES[2], false))
			local b = Town.steps(Town.plan(spec(2, SHAPES[2], nil)), spec(2, SHAPES[2], nil))
			check.equal(#a, #b)
			local floors, tilted = 0, 0
			for i, st in a do
				local kind, v = next(st)
				local kind2, v2 = next(b[i])
				check.equal(kind, kind2)
				check.equal(v.name, v2.name)
				floors += if kind == "floor" then 1 else 0
				tilted += if kind == "part" and v.rot ~= nil then 1 else 0
			end
			check.truthy(floors >= 3) -- (the streets' one floor, the square's, each block's pavement)
			check.equal(tilted, 0)
			check.equal(Town.record("T", Town.plan(spec(2, SHAPES[2], false))).slope, nil)
		end)
	end)

	test.suite("Town slope: the ground cut round the houses", function()
		test.case(
			"the plates overlap nowhere, leave every house's slab bare, and with the slabs fill the whole area",
			function()
				for si, shape in SHAPES do
					for seed = 1, 4 do
						-- (every other town with trim: its houses stand a stud inside their lots, the slab is smaller)
						local mats = table.clone(MATS)
						mats.trim = if seed % 2 == 0 then "plaster" else nil
						local plan = Town.plan(
							spec(seed, shape, { rise = 5, toward = SIDES[(seed + si) % 4 + 1] }, { mats = mats })
						)
						check.equal(errorsOf(plan.issues), "")
						check.equal(plan.gap > 0, seed % 2 == 0)
						local plates = Town.groundPlates(plan)
						local inset = (plan.gap + plan.wall) / 2
						local slabs, slabArea = {}, 0
						for _, lot in plan.lots do
							local r = lot.rect
							local sl = { x0 = r.x0 + inset, x1 = r.x1 - inset, z0 = r.z0 + inset, z1 = r.z1 - inset }
							table.insert(slabs, sl)
							slabArea += (sl.x1 - sl.x0) * (sl.z1 - sl.z0)
						end
						local function overlap(a: any, b: any): boolean
							return a.x0 < b.x1 - 1e-6
								and a.x1 > b.x0 + 1e-6
								and a.z0 < b.z1 - 1e-6
								and a.z1 > b.z0 + 1e-6
						end
						local area = 0
						local slivers = 0
						local classes = { street = 0, square = 0, block = 0 }
						for i, p in plates do
							local r = p.rect
							check.truthy(r.x1 > r.x0 and r.z1 > r.z0)
							check.truthy(r.x0 >= plan.area.x0 - 1e-6 and r.x1 <= plan.area.x1 + 1e-6)
							check.truthy(r.z0 >= plan.area.z0 - 1e-6 and r.z1 <= plan.area.z1 + 1e-6)
							area += (r.x1 - r.x0) * (r.z1 - r.z0)
							-- (a plate under a house's wall ends Town.INTO inside the walls' outer plane, card my7f: the sliver it
							-- leaves is counted here, and only an end exactly that far inside a house's outline is one)
							local w0, w1, n0, n1 = false, false, false, false
							for _, sl in slabs do
								local hw = plan.wall / 2
								local g = { x0 = sl.x0 - hw, x1 = sl.x1 + hw, z0 = sl.z0 - hw, z1 = sl.z1 + hw }
								local acrossZ = r.z0 < g.z1 and g.z0 < r.z1
								local acrossX = r.x0 < g.x1 and g.x0 < r.x1
								-- no plate ENDS in the walls' outer plane from inside it (the old ground did: Slate on the
								-- plinth's Brick in one plane, 220 flickering pairs in the selftest town)
								check.falsy(acrossZ and (near(r.x0, g.x0) or near(r.x1, g.x1)))
								check.falsy(acrossX and (near(r.z0, g.z0) or near(r.z1, g.z1)))
								w0 = w0 or (acrossZ and near(r.x0, g.x0 + Town.INTO))
								w1 = w1 or (acrossZ and near(r.x1, g.x1 - Town.INTO))
								n0 = n0 or (acrossX and near(r.z0, g.z0 + Town.INTO))
								n1 = n1 or (acrossX and near(r.z1, g.z1 - Town.INTO))
							end
							local px = (if w0 then Town.INTO else 0) + (if w1 then Town.INTO else 0)
							local pz = (if n0 then Town.INTO else 0) + (if n1 then Town.INTO else 0)
							slivers += (r.x1 - r.x0 + px) * (r.z1 - r.z0 + pz) - (r.x1 - r.x0) * (r.z1 - r.z0)
							classes[p.class] += 1
							for _, sl in slabs do
								check.falsy(overlap(r, sl))
							end
							for j = i + 1, #plates do
								check.falsy(overlap(r, plates[j].rect))
							end
							-- its class is what its middle stands on
							local cx, cz = (r.x0 + r.x1) / 2, (r.z0 + r.z1) / 2
							local inBlock = false
							for _, B in plan.blocks do
								inBlock = inBlock or (cx > B.x0 and cx < B.x1 and cz > B.z0 and cz < B.z1)
							end
							local S = plan.square
							local inSquare = cx > S.x0 and cx < S.x1 and cz > S.z0 and cz < S.z1
							check.equal(p.class, if inBlock then "block" elseif inSquare then "square" else "street")
						end
						local whole = (plan.area.x1 - plan.area.x0) * (plan.area.z1 - plan.area.z0)
						-- (no hole and no double ground anywhere, but the slivers under the walls)
						check.truthy(near(area + slabArea + slivers, whole, 1e-3))
						check.truthy(slivers >= 0 and slivers < 0.01 * whole) -- (none in a town whose houses stand in from their lots)
						check.truthy(classes.street >= 4 and classes.square >= 1 and classes.block >= #plan.blocks)
						check.truthy(#plates <= 6 * #plan.lots + 80) -- (joined: not one plate a cell)
					end
				end
			end
		)

		test.case(
			"every ground plate lies ON the hillside: tilted by the slope's angle, its top at the ground's height",
			function()
				for _, side in SIDES do
					local slope = { rise = 6, toward = side }
					local s = spec(3, SHAPES[2], slope)
					local steps, plan = stepsOf(s)
					local angle = math.deg(math.atan(0.06))
					local want = if side == "N"
						then { angle, 0, 0 }
						elseif side == "S" then { -angle, 0, 0 }
						elseif side == "E" then { 0, 0, angle }
						else { 0, 0, -angle }
					local plates = Town.groundPlates(plan)
					local n = 0
					for _, st in steps do
						local kind, v = next(st)
						check.falsy(kind == "floor") -- (no level floor is left under a town on a slope)
						if kind == "part" and v.name == "Floor" then
							n += 1
							local plate = plates[n]
							local r = plate.rect
							check.truthy(
								near(v.rot[1], want[1]) and near(v.rot[2], want[2]) and near(v.rot[3], want[3])
							)
							check.truthy(near(v.pos[1], (r.x0 + r.x1) / 2) and near(v.pos[3], (r.z0 + r.z1) / 2))
							-- its top, straight up from its middle, is the ground there (a kerb higher on a block)
							local cos = math.cos(math.rad(angle))
							local top = v.pos[2] + v.size[2] / 2 / cos
							local kerb = if plate.class == "block" then 0.4 else 0
							check.truthy(near(top, plan.y + kerb + ground(plan, slope, v.pos[1], v.pos[3])))
							-- as long down the slope as its plan length over the cosine: plates meet edge to edge
							local alongZ = side == "N" or side == "S"
							check.truthy(near(v.size[1], if alongZ then r.x1 - r.x0 else (r.x1 - r.x0) / cos))
							check.truthy(near(v.size[3], if alongZ then (r.z1 - r.z0) / cos else r.z1 - r.z0))
							check.equal(
								v.mat,
								if plate.class == "block"
									then "pave"
									elseif plate.class == "square" then "flag"
									else "cobble"
							)
						end
					end
					check.equal(n, #plates)
					-- ... and the compiler tilts them so: a plate's top face, a long way from its middle, is still the ground
					local _, parts, issues =
						World.compile({ name = "T", palette = PALETTE, scale = "r6", build = { { town = s } } })
					check.equal(errorsOf(issues), "")
					local seen = 0
					for _, p in parts do
						if p.name == "Floor" and math.max(p.size[1], p.size[3]) >= 40 and p.size[2] == 1 then
							seen += 1
							for _, f in { -0.45, 0.45 } do
								-- a point on the plate's top face, toward each end of its long side (its own frame, turned by rot)
								local lx, lz = 0, 0
								if p.size[1] >= p.size[3] then
									lx = f * p.size[1]
								else
									lz = f * p.size[3]
								end
								local ly = p.size[2] / 2
								local wx = p.pos[1] + p.rot[1][1] * lx + p.rot[1][2] * ly + p.rot[1][3] * lz
								local wy = p.pos[2] + p.rot[2][1] * lx + p.rot[2][2] * ly + p.rot[2][3] * lz
								local wz = p.pos[3] + p.rot[3][1] * lx + p.rot[3][2] * ly + p.rot[3][3] * lz
								check.truthy(near(wy, plan.y + ground(plan, slope, wx, wz), 1e-4))
							end
						end
					end
					check.truthy(seen >= 4)
				end
			end
		)
	end)

	test.suite("Town slope: the house's slab is where the ground was cut for it", function()
		test.case(
			"compiled, every house's ground slab fills its hole in the ground exactly - with trim and without, any kerb and sill",
			function()
				for _, more in { {}, { trim = true }, { kerb = 1, sill = 0.5 }, { trim = true, kerb = 0.8 } } :: { any } do
					local mats = table.clone(MATS)
					mats.trim = if more.trim then "plaster" else nil
					local slope = { rise = 6, toward = "N" }
					local s = spec(2, SHAPES[1], slope, { mats = mats, kerb = more.kerb, sill = more.sill })
					local plan = Town.plan(s)
					check.equal(errorsOf(plan.issues), "")
					local _, parts, issues =
						World.compile({ name = "T", palette = PALETTE, scale = "r6", build = { { town = s } } })
					check.equal(errorsOf(issues), "")
					local inset = (plan.gap + plan.wall) / 2
					local holes = {}
					for _, lot in plan.lots do
						local r = lot.rect
						holes[`{(r.x0 + r.x1) / 2}:{(r.z0 + r.z1) / 2}`] =
							{ w = r.x1 - r.x0 - 2 * inset, d = r.z1 - r.z0 - 2 * inset, lot = lot }
					end
					local slabs, plinths = 0, 0
					local bottomOf = {}
					for _, p in parts do
						if p.name == "Slab" and p.pos[2] < plan.y + 14 then
							local hole = holes[`{p.pos[1]}:{p.pos[3]}`]
							if
								hole
								and near( -- (the slab's top is World.GROUND_LIFT over its storey line: card my7f)
									p.pos[2]
										+ p.size[2] / 2
										- World.GROUND_LIFT
										- (s.kerb or 0.4)
										- (s.sill or 0.1)
										- plan.y,
									Town.groundAt(plan, Town.doorPoint(hole.lot)),
									1e-6
								)
							then
								slabs += 1
								-- the ground floor's slab is as wide and deep as the hole the ground leaves for it
								check.truthy(near(p.size[1], hole.w) and near(p.size[3], hole.d))
								bottomOf[`{p.pos[1]}:{p.pos[3]}`] = p.pos[2] - p.size[2] / 2
							end
						end
					end
					check.equal(slabs, #plan.lots)
					for _, p in parts do
						if string.sub(p.name, -7) == " plinth" then
							plinths += 1
							-- a plinth's top is the underside of its house's slab: no slit between them, no overlap
							check.truthy(near(p.pos[2] + p.size[2] / 2, bottomOf[`{p.pos[1]}:{p.pos[3]}`]))
						end
					end
					check.truthy(plinths >= 20)
				end
			end
		)
	end)

	test.suite("Town slope: what stands on the hillside", function()
		test.case(
			"each house stands level at its own door's ground; a plinth carries it where the ground falls away",
			function()
				local stepped, plinths, bare = 0, 0, 0
				for si, shape in SHAPES do
					for seed = 1, 3 do
						local slope = { rise = 6, toward = SIDES[(seed + si) % 4 + 1] }
						local s = spec(seed, shape, slope)
						local steps, plan = stepsOf(s)
						local flatSpec = spec(seed, shape, false)
						local flat = {}
						for _, st in Town.steps(Town.plan(flatSpec), flatSpec) do
							local kind, v = next(st)
							if kind == "building" then
								flat[v.name] = v
							end
						end
						local byName, plinthOf = {}, {}
						for _, lot in plan.lots do
							byName[lot.name] = lot
						end
						for _, st in steps do
							local kind, v = next(st)
							if kind == "part" and string.sub(v.name, -7) == " plinth" then
								plinthOf[string.sub(v.name, 1, -8)] = v
							end
						end
						local heights = {}
						for _, st in steps do
							local kind, v = next(st)
							if kind == "building" then
								local lot, was = byName[v.name], flat[v.name]
								check.truthy(lot ~= nil and was ~= nil)
								-- the same house in the same place, only higher or lower: by the ground at its front door
								local r = lot.rect
								local dx, dz = (r.x0 + r.x1) / 2, (r.z0 + r.z1) / 2
								if lot.front == "N" then
									dz = r.z0
								elseif lot.front == "S" then
									dz = r.z1
								elseif lot.front == "W" then
									dx = r.x0
								else
									dx = r.x1
								end
								local base = ground(plan, slope, dx, dz)
								check.truthy(near(v.center[1], was.center[1]) and near(v.center[3], was.center[3]))
								check.truthy(near(v.center[2], was.center[2] + base))
								check.equal(v.floors, was.floors)
								check.truthy(v.size[1] == was.size[1] and v.size[2] == was.size[2])
								check.equal(v.turn, nil) -- (a house stands upright: only the ground is tilted)
								heights[math.floor(base * 100 + 0.5)] = true
								-- at its door the street is half a stud under its floor, as in a level town: a body walks in
								local low = math.min(
									ground(plan, slope, r.x0, r.z0),
									ground(plan, slope, r.x1, r.z0),
									ground(plan, slope, r.x0, r.z1),
									ground(plan, slope, r.x1, r.z1)
								)
								local high = math.max(
									ground(plan, slope, r.x0, r.z0),
									ground(plan, slope, r.x1, r.z0),
									ground(plan, slope, r.x0, r.z1),
									ground(plan, slope, r.x1, r.z1)
								)
								local depth = if lot.front == "N" or lot.front == "S" then r.z1 - r.z0 else r.x1 - r.x0
								local width = if lot.front == "N" or lot.front == "S" then r.x1 - r.x0 else r.z1 - r.z0
								-- (never more hill against its walls than its depth, or half its width, climbs)
								check.truthy(high - base <= 0.06 * math.max(depth, width / 2) + 1e-6)
								local pl = plinthOf[v.name]
								if base - low > 0.05 then
									plinths += 1
									check.truthy(pl ~= nil)
									-- from under the lowest corner's ground up to the UNDERSIDE of the house's slab (a stud under its
									-- floor), in the walls' own planes: no gap under the house, nothing proud in the street
									check.truthy(near(pl.pos[2] + pl.size[2] / 2, v.center[2] - 1))
									check.truthy(near(pl.pos[2] - pl.size[2] / 2, plan.y + low - 0.6))
									check.truthy(
										near(pl.size[1], v.size[1] + plan.wall)
											and near(pl.size[3], v.size[2] + plan.wall)
									)
									check.truthy(near(pl.pos[1], v.center[1]) and near(pl.pos[3], v.center[3]))
									check.truthy(pl.size[1] <= r.x1 - r.x0 + 1e-6 and pl.size[3] <= r.z1 - r.z0 + 1e-6) -- (inside its lot)
								else
									bare += 1
									check.equal(pl, nil)
								end
							end
						end
						local levels = 0
						for _ in heights do
							levels += 1
						end
						stepped += levels
						check.truthy(levels >= 8) -- (houses step up the hill: many levels, not one)
					end
				end
				check.truthy(plinths >= 100 and bare >= 20) -- (both kinds are walked)
				check.truthy(stepped >= 9 * 8)
			end
		)

		test.case(
			"walls, lamps, stalls, yard things and spawn pads stand at the ground's height where they are",
			function()
				local walls, gates, lamps, stalls, things, pads = 0, 0, 0, 0, 0, 0
				for si, shape in SHAPES do
					for seed = 1, 3 do
						local slope = { rise = ({ 6, 3, 4.5 })[seed], toward = SIDES[(seed + si + 1) % 4 + 1] }
						local g = slope.rise / 100
						local s = spec(seed, shape, slope)
						local steps, plan = stepsOf(s)
						local flatSpec = spec(seed, shape, false)
						local flat = {}
						for _, st in Town.steps(Town.plan(flatSpec), flatSpec) do
							local kind, v = next(st)
							if kind ~= "floor" and kind ~= "fit" then
								flat[`{kind}:{v.name}:{if v.pos
									then `{v.pos[1]}:{v.pos[3]}:{v.size and v.size[2] or ""}`
									else ""}`] =
									v
							end
						end
						for _, st in steps do
							local kind, v = next(st)
							local was = flat[`{kind}:{v.name}:{if v.pos
								then `{v.pos[1]}:{v.pos[3]}:{v.size and v.size[2] or ""}`
								else ""}`]
							if kind == "wall" then
								walls += 1
								check.truthy(was ~= nil)
								local a = ground(plan, slope, v.from[1], v.from[2])
								local b = ground(plan, slope, v.to[1], v.to[2])
								-- it stands on its LOWER end and its top is level: as high over its upper end as it was
								check.truthy(near(v.y, was.y + math.min(a, b)))
								check.truthy(near(v.y + v.height, was.y + was.height + math.max(a, b)))
								local len = math.sqrt((v.to[1] - v.from[1]) ^ 2 + (v.to[2] - v.from[2]) ^ 2)
								for k, gate in v.gaps or {} do
									gates += 1
									-- the opening is as high over the ground where it stands as in a level town
									local at = a + (b - a) * gate.at / len
									check.truthy(near(v.y + gate.height, was.y + was.gaps[k].height + at))
									check.truthy(v.y + gate.height - (was.y + at) >= 8.5 - 1e-6)
								end
							elseif kind == "row" then
								lamps += 1
								check.truthy(was ~= nil)
								check.truthy(near(v.y, was.y + ground(plan, slope, v.points[1][1], v.points[1][2])))
							elseif kind == "spawn" then
								pads += 1
								check.truthy(was ~= nil)
								-- (level, on the ground under its lowest edge - 3 studs down the hill from its middle - a hair under)
								check.truthy(
									near(v.pos[2], was.pos[2] + ground(plan, slope, v.pos[1], v.pos[3]) - g * 3 - 0.05)
								)
							elseif kind == "part" and v.about ~= nil then
								check.truthy(was ~= nil)
								-- a thing of several parts stands level, all of it moved by one height: the ground at its
								-- middle less 0.3 (the fall of the hill over 5 studs), so that none of it floats
								local dh = ground(plan, slope, v.about[1], v.about[2]) - g * 5
								check.truthy(near(v.pos[2], was.pos[2] + dh))
								check.equal(v.rot, nil)
								stalls += if string.sub(v.name, 1, 6) == "Stall " then 1 else 0
								things += if string.sub(v.name, 1, 5) == "Yard " then 1 else 0
							end
						end
					end
				end
				check.truthy(walls >= 9 and gates >= 9 and lamps >= 30 and pads >= 18 and stalls >= 30 and things >= 9)
			end
		)

		test.case("a street's claim is the level town's own, with its floor's height at each end", function()
			local claims, climbing = 0, 0
			for si, shape in SHAPES do
				for _, side in SIDES do
					local slope = { rise = 6, toward = side }
					local s = spec(si, shape, slope)
					local steps, plan = stepsOf(s)
					local flatSpec = spec(si, shape, false)
					local whole = {}
					local n = 0
					for _, st in Town.steps(Town.plan(flatSpec), flatSpec) do
						local kind, v = next(st)
						if kind == "fit" then
							whole[v.name] = v
							n += 1
						end
					end
					local seen = 0
					for _, st in steps do
						local kind, v = next(st)
						if kind == "fit" then
							seen += 1
							claims += 1
							local was = whole[v.name]
							check.truthy(was ~= nil) -- (one claim a street, by its own name: no pieces)
							check.equal(v.kind, was.kind)
							check.truthy(near(v.from[1], was.from[1]) and near(v.from[2], was.from[2]))
							check.truthy(near(v.to[1], was.to[1]) and near(v.to[2], was.to[2]))
							-- its floor's height at each end, and at its middle
							local a = plan.y + ground(plan, slope, v.from[1], v.from[2])
							local b = plan.y + ground(plan, slope, v.to[1], v.to[2])
							check.equal(#v.ground, 2)
							check.truthy(near(v.ground[1], a) and near(v.ground[2], b))
							check.truthy(near(v.pos[1], was.pos[1]) and near(v.pos[3], was.pos[3]))
							check.truthy(near(v.pos[2], (a + b) / 2))
							check.equal(v.chain, nil)
							-- how the floor climbs across it: a stud to its left (the side (-(dz), dx) of from -> to)
							local dx, dz = v.to[1] - v.from[1], v.to[2] - v.from[2]
							local len = math.sqrt(dx * dx + dz * dz)
							local mx, mz = (v.from[1] + v.to[1]) / 2, (v.from[2] + v.to[2]) / 2
							local want = ground(plan, slope, mx - dz / len, mz + dx / len) - ground(plan, slope, mx, mz)
							check.truthy(near(v.cross, want))
							-- a street up the hill does not climb across itself, one across the hill climbs 6 in 100
							check.truthy(near(math.abs(v.cross), 0) or near(math.abs(v.cross), 0.06))
							check.truthy(near(math.abs(v.cross), 0.06) == (math.abs(a - b) < 1e-6))
							climbing += if math.abs(a - b) > 2 then 1 else 0
						end
					end
					check.equal(seen, n)
					-- a level town's claims say no "ground" at all
					for _, was in whole do
						check.equal(was.ground, nil)
					end
				end
			end
			check.truthy(claims >= 100 and climbing >= 30) -- (streets that climb over 2 studs are really walked)
		end)

		test.case("the town's record says how the land lies", function()
			local plan = Town.plan(spec(1, SHAPES[3], { rise = 4.5, toward = "E" }))
			local rec = Town.record("T", plan)
			check.equal(rec.slope.rise, 4.5)
			check.equal(rec.slope.toward, "E")
			check.truthy(near(rec.slope.drop, 0.045 * 400)) -- (from the lowest edge to the highest: 18 studs)
			local north = Town.record("T", Town.plan(spec(1, SHAPES[3], { rise = 2, toward = "N" })))
			check.truthy(near(north.slope.drop, 0.02 * 320))
		end)
	end)
end

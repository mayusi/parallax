-- worldcover.spec.luau (kit) — SNOW AND DUST ON WHAT IS BUILT (kit/lib/worldcover.luau, a world's "cover"; the owner's
-- method list: "Procedural snow / dust coverage"). Held here, by what lies at given places of given faces: snow where
-- the sky sees, dust under a roof, nothing under what stands on a face, in the land, or under a roof too high for a
-- room; a gable's two halves meeting over the ridge; mesh stand-ins, breakables, balls and tilts; a season's own
-- cover; the lock that asks a world under snow.
-- Not claimed here: how snow on a roof looks. That is a built world, looked at.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Cover = require("../../lib/worldcover")
local LaneLocks = require("../../lib/lanelocks")
local World = require("../../lib/world")

local PALETTE = {
	wood = { material = "Wood", color = { 110, 84, 60 } },
	stone = { material = "Slate", color = { 90, 88, 86 } },
}

local function compile(bp: any, opts: any?): ({ any }, { string }, { string }, any, any)
	bp.name = bp.name or "T"
	bp.palette = PALETTE
	local model, parts, issues, extras = World.compile(bp, opts or { meshes = {} })
	local errors, warns = {}, {}
	for _, i in issues do
		if i.path ~= "spawn" then
			table.insert(if i.severity == "error" then errors else warns, i.message)
		end
	end
	return parts, errors, warns, extras, model
end

local function near(a: number, b: number, e: number?): boolean
	return math.abs(a - b) < (e or 1e-6)
end

-- the slab (snow or dust) lying at (x, z) on the face whose top is at `top`: its kind, or nil
local function at(parts: { any }, x: number, z: number, top: number): string?
	local found: string? = nil
	for _, s in parts do
		if s.cover and not s.slope and near(s.pos[2], top + s.size[2] / 2, 0.05) then
			-- (the slab's own box, turned: is (x, its middle's height, z) inside it)
			local dx, dz = x - s.pos[1], z - s.pos[3]
			local inside = true
			for a = 1, 3 do
				local q = s.rot[1][a] * dx + s.rot[3][a] * dz
				inside = inside and math.abs(q) <= s.size[a] / 2 + 1e-6
			end
			if inside then
				check.equal(found, nil, `two slabs at {x}, {z}`)
				found = s.kind
			end
		end
	end
	return found
end

local function count(parts: { any }, kind: string): number
	local n = 0
	for _, s in parts do
		if s.cover and s.kind == kind then
			n += 1
		end
	end
	return n
end

local SNOW_DUST = { snow = { depth = 0.6 }, dust = { depth = 0.1 } }

-- a hut on a plaza: the plaza 60 x 60, a floor slab, four walls, a flat roof resting on them; a crate on the floor
local HUT = {
	{ part = { name = "Plaza", mat = "stone", size = { 60, 1, 60 }, pos = { 0, -0.5, 0 } } },
	{ part = { name = "Floor", mat = "stone", size = { 20, 1, 20 }, pos = { 0, 0.5, 0 } } },
	{ part = { name = "WallN", mat = "wood", size = { 20, 10, 1 }, pos = { 0, 6, -9.5 } } },
	{ part = { name = "WallS", mat = "wood", size = { 20, 10, 1 }, pos = { 0, 6, 9.5 } } },
	{ part = { name = "WallW", mat = "wood", size = { 1, 10, 18 }, pos = { -9.5, 6, 0 } } },
	{ part = { name = "WallE", mat = "wood", size = { 1, 10, 18 }, pos = { 9.5, 6, 0 } } },
	{ part = { name = "Roof", mat = "wood", size = { 22, 1, 22 }, pos = { 0, 11.5, 0 } } },
	{ part = { name = "Crate", mat = "wood", size = { 3, 3, 3 }, pos = { 3, 2.5, 3 } } },
}

return function()
	test.suite("Snow and dust on what is built", function()
		test.case("a hut on a plaza: snow under the sky, dust under the roof, nothing under what stands", function()
			local parts, errors, warns, extras = compile({ build = HUT, cover = SNOW_DUST })
			check.equal(#errors, 0, table.concat(errors, " | "))
			check.equal(#warns, 0, table.concat(warns, " | "))
			check.equal(at(parts, 0, 0, 12), "snow") -- (the roof)
			check.equal(at(parts, 10.9, -10.9, 12), "snow")
			check.equal(at(parts, 10.995, 0, 12), nil) -- (a hair in from the face's own edges)
			check.equal(at(parts, -10.995, 0, 12), nil)
			check.equal(at(parts, 0, -10.995, 12), nil)
			check.equal(at(parts, 0, 10.995, 12), nil)
			check.equal(at(parts, 25, 25, 0), "snow") -- (the plaza in the open)
			check.equal(at(parts, 0, 28, 0), "snow")
			-- the plaza under the hut: the floor slab stands on it - nothing there, neither snow nor dust
			check.equal(at(parts, 0, 0, 0), nil)
			check.equal(at(parts, 9.9, 0, 0), nil)
			-- (just outside the walls, under the roof's 1-stud overhang: roofed, 11 studs up - dust)
			check.equal(at(parts, 10.5, 0, 0), "dust")
			-- the floor inside: dust, but none under the crate or the walls
			check.equal(at(parts, -5, -5, 1), "dust")
			check.equal(at(parts, 3, 3, 1), nil)
			check.equal(at(parts, 0, -9.5, 1), nil)
			check.equal(at(parts, 3, 3, 4), "dust") -- (the crate's top, under the roof)
			-- the walls' tops: the roof rests on them - nothing
			check.equal(at(parts, 0, -9.5, 11), nil)
			-- snow is solid, dust untouched
			for _, s in parts do
				if s.cover then
					check.equal(s.collide, s.kind == "snow")
					if s.kind == "dust" then
						check.equal(s.query, false)
						check.equal(s.castShadow, false)
						check.equal(s.material, "Sand")
						check.truthy(near(s.size[2], 0.1))
						check.equal(s.transparency, 0.35)
					else
						check.equal(s.material, "Snow")
						check.truthy(near(s.size[2], 0.6))
					end
				end
			end
			check.truthy(extras.cover.snow >= 2 and extras.cover.dust >= 2)
			-- snow only, dust only, "above", false, none
			local p2 = compile({ build = HUT, cover = { snow = { depth = 1 } } })
			check.equal(count(p2, "dust"), 0)
			check.equal(at(p2, -5, -5, 1), nil)
			local p3 = compile({ build = HUT, cover = { dust = { depth = 0.2 } } })
			check.equal(count(p3, "snow"), 0)
			local p4 = compile({ build = HUT, cover = { snow = { depth = 0.6, above = 5 } } })
			check.equal(at(p4, 0, 0, 12), "snow")
			check.equal(at(p4, 25, 25, 0), nil)
			check.equal(count((compile({ build = HUT, cover = false })), "snow"), 0)
			local _, _, _, x6 = compile({ build = HUT })
			check.equal(x6.cover, nil)
		end)

		test.case("a face read cell by cell: eaves over half, a narrow roof, a high bridge, the land", function()
			local build = {
				-- an 8 x 8 step, eaves 7 studs over its north half: the south half snow, the north half dust
				{ part = { name = "Step", mat = "stone", size = { 8, 1, 8 }, pos = { 0, 0.5, 0 } } },
				{ part = { name = "Eaves", mat = "wood", size = { 8, 0.4, 4 }, pos = { 0, 8, -2 } } },
				-- a 16 x 16 floor with a 6 x 6 roof 6 studs over its middle: dust only under the roof
				{ part = { name = "Yard", mat = "stone", size = { 16, 1, 16 }, pos = { 40, 0.5, 0 } } },
				{ part = { name = "Shade", mat = "wood", size = { 6, 0.4, 6 }, pos = { 40, 7, 0 } } },
				-- squares under a bridge 100, 30 and 10 studs up
				{ part = { name = "SqA", mat = "stone", size = { 6, 1, 6 }, pos = { 80, 0.5, 0 } } },
				{ part = { name = "BridgeA", mat = "stone", size = { 8, 1, 8 }, pos = { 80, 101.5, 0 } } },
				{ part = { name = "SqB", mat = "stone", size = { 6, 1, 6 }, pos = { 100, 0.5, 0 } } },
				{ part = { name = "BridgeB", mat = "stone", size = { 8, 1, 8 }, pos = { 100, 31.5, 0 } } },
				{ part = { name = "SqC", mat = "stone", size = { 6, 1, 6 }, pos = { 120, 0.5, 0 } } },
				{ part = { name = "BridgeC", mat = "stone", size = { 8, 1, 8 }, pos = { 120, 11.5, 0 } } },
				-- a crate 14 studs from a beam turned 45 degrees (whose box round it would reach over the crate)
				{ part = { name = "Crate", mat = "wood", size = { 4, 4, 4 }, pos = { 160, 2, 0 } } },
				{
					part = {
						name = "Beam",
						mat = "wood",
						size = { 40, 1, 1 },
						pos = { 160, 12, 14 },
						rot = { 0, 45, 0 },
					},
				},
			}
			local parts, errors = compile({ build = build, cover = SNOW_DUST })
			check.equal(#errors, 0, table.concat(errors, " | "))
			check.equal(at(parts, 0, 3, 1), "snow")
			check.equal(at(parts, 0, -3, 1), "dust")
			check.equal(at(parts, 40, 0, 1), "dust")
			check.equal(at(parts, 40, 6, 1), "snow")
			check.equal(at(parts, 34, -7, 1), "snow")
			check.equal(at(parts, 80, 0, 1), "snow") -- (a bridge 100 up: open sky)
			check.equal(at(parts, 100, 0, 1), nil) -- (30 up: no snow under it, and no room - nothing)
			check.equal(at(parts, 120, 0, 1), "dust") -- (10 up: under a roof)
			check.equal(at(parts, 160, 0, 4), "snow") -- (the beam, by its own turned box, is not over the crate)
			-- a part under the land (a floor in a tunnel) takes nothing
			local tunnel = {
				terrain = { { ground = { center = { 0, 10, 0 }, size = { 100, 100 }, material = "Grass" } } },
				build = { { part = { name = "Deep", mat = "stone", size = { 6, 1, 6 }, pos = { 0, 0.5, 0 } } } },
				cover = SNOW_DUST,
			}
			check.equal(#(compile(tunnel)), 0) -- (a part wholly under the land is not built at all)
			-- a slab half in a hillside: its middle under the sky, its ends under the land
			local hill = {
				terrain = {
					{
						ground = {
							center = { 0, 10, 0 },
							size = { 100, 100 },
							material = "Grass",
							flat = { { center = { 0, 0 }, radius = 4, height = 0 } },
						},
					},
				},
				build = { { part = { name = "Ledge", mat = "stone", size = { 40, 1, 4 }, pos = { 0, 1.5, 0 } } } },
				cover = SNOW_DUST,
			}
			local hp, herr = compile(hill)
			check.equal(#herr, 0, table.concat(herr, " | "))
			check.equal(at(hp, 0, 0, 2), "snow")
			check.equal(at(hp, 18, 0, 2), nil)
			check.equal(at(hp, -18, 0, 2), nil)
		end)

		test.case("what takes nothing: stand-ins, breakables, loose parts, balls, tilts; what lies flush", function()
			local build = {
				{ part = { name = "Floor", mat = "stone", size = { 10, 1, 10 }, pos = { 0, 0.5, 0 } } },
				{ part = { name = "Ball", mat = "stone", size = { 4, 4, 4 }, pos = { 40, 2, 0 }, shape = "Ball" } },
				{ part = { name = "Drum", mat = "stone", size = { 4, 4, 4 }, pos = { 50, 2, 0 }, shape = "Cylinder" } },
				{ part = { name = "Tilt", mat = "stone", size = { 6, 1, 6 }, pos = { 60, 3, 0 }, rot = { 30, 0, 0 } } },
				{ part = { name = "Loose", mat = "wood", size = { 3, 3, 3 }, pos = { 70, 1.5, 0 }, physics = true } },
				-- two slabs lying flush and overlapping: one slab of snow where they overlap, never two
				{ part = { name = "SlabA", mat = "stone", size = { 8, 1, 4 }, pos = { 90, 0.5, 0 } } },
				{ part = { name = "SlabB", mat = "stone", size = { 8, 1, 4 }, pos = { 94, 0.5, 0 } } },
				-- two more lying flush on grids that do not line up (7 studs: cells of 1.75; 9 studs: 1.8)
				{ part = { name = "SlabC", mat = "stone", size = { 7, 1, 7 }, pos = { 120, 0.5, 0 } } },
				-- (D's cells are 1.8 wide from x 119.4: the one from 123.0 to 124.8 has its middle past C's edge at 123.5,
				-- so it takes snow, and its slab reaches half a stud back over C's)
				{ part = { name = "SlabD", mat = "stone", size = { 9, 1, 9 }, pos = { 123.9, 0.5, 1.3 } } },
				-- a backdrop high over a slab is no roof; a spawn pad takes nothing
				{ part = { name = "Open", mat = "stone", size = { 6, 1, 6 }, pos = { 150, 0.5, 0 } } },
				{ part = { name = "Far", mat = "stone", size = { 10, 1, 10 }, pos = { 150, 8, 0 }, backdrop = true } },
				{ spawn = { pos = { 170, 0, 0 } } },
			}
			local parts, errors, _, extras = compile({ build = build, cover = SNOW_DUST })
			check.equal(#errors, 0, table.concat(errors, " | "))
			check.equal(extras.cover.shapes, 3) -- (the ball, the drum, the tilt)
			check.equal(extras.cover.loose, 1)
			check.equal(at(parts, 92, 0, 1), "snow") -- (`at` fails on two slabs at one place)
			check.equal(at(parts, 70, 0, 3), nil)
			check.equal(at(parts, 150, 0, 1), "snow")
			check.equal(at(parts, 170, 0, 1), nil)
			-- the slabs of two flush faces never lie in one plane, where they overlap at all
			local flush = {}
			for _, q in parts do
				if q.cover and q.pos[1] > 115 and q.pos[1] < 130 then
					table.insert(flush, q)
				end
			end
			local overlapping = 0
			for i1 = 1, #flush do
				for i2 = i1 + 1, #flush do
					local a, b = flush[i1], flush[i2]
					local ox = math.min(a.pos[1] + a.size[1] / 2, b.pos[1] + b.size[1] / 2)
						- math.max(a.pos[1] - a.size[1] / 2, b.pos[1] - b.size[1] / 2)
					local oz = math.min(a.pos[3] + a.size[3] / 2, b.pos[3] + b.size[3] / 2)
						- math.max(a.pos[3] - a.size[3] / 2, b.pos[3] - b.size[3] / 2)
					if ox > 0.01 and oz > 0.01 then
						overlapping += 1
						check.truthy(math.abs(a.pos[2] - b.pos[2]) >= 0.01, "two overlapping slabs in one plane")
					end
				end
			end
			check.truthy(overlapping >= 1, "the scene has two slabs that overlap (else the check above holds nothing)")
			-- a plain seen-through part over the floor is no roof: snow
			local standing = table.clone(build)
			table.insert(standing, {
				part = { name = "Hall", mat = "wood", size = { 12, 6, 12 }, pos = { 0, 10, 0 }, transparency = 1 },
			})
			local sp, _, _, sx = compile({ build = standing, cover = SNOW_DUST })
			check.equal(at(sp, 0, 0, 1), "snow")
			check.equal(sx.cover.meshes, 0)
			-- the same part as a mesh's stand-in: it is the roof, and is not snowed on itself
			local plain = {}
			for _, q in sp do
				if not q.cover then
					local c = table.clone(q)
					if c.name == "Hall" then
						c.mesh = "hall_mesh"
					end
					table.insert(plain, c)
				end
			end
			local slabs, rec = Cover.lay(plain, SNOW_DUST)
			check.equal(rec.meshes, 1)
			check.equal(at(slabs, 0, 0, 1), "dust")
			check.equal(at(slabs, 0, 0, 13), nil)
			-- (a building's KitBlockout stand-ins too)
			for _, c in plain do
				if c.name == "Hall" then
					c.mesh = nil
					c.attributes = { KitBlockout = "b1" }
				end
			end
			local slabs2, rec2 = Cover.lay(plain, SNOW_DUST)
			check.equal(rec2.meshes, 1)
			check.equal(at(slabs2, 0, 0, 1), "dust")
			-- a breakable part: no slab (it would be left in the air when it breaks)
			local _, brec = Cover.lay({
				{
					name = "Pot",
					class = "Part",
					size = { 2, 2, 2 },
					pos = { 0, 1, 0 },
					rot = { { 1, 0, 0 }, { 0, 1, 0 }, { 0, 0, 1 } },
					transparency = 0,
					anchored = true,
					attributes = { KitBreakable = true },
				},
			}, SNOW_DUST)
			check.equal(brec.loose, 1)
			check.equal(brec.snow, 0)
		end)

		test.case("wedges: a ramp along its slope, a gable's halves meeting over the ridge", function()
			local build = {
				{ part = { name = "Ramp", mat = "stone", size = { 6, 4, 8 }, pos = { 0, 2, 0 }, shape = "Wedge" } },
				{ part = { name = "Steep", mat = "stone", size = { 6, 10, 4 }, pos = { 20, 5, 0 }, shape = "Wedge" } },
				-- a wedge whose low end lies under an awning lower than its top: read at the slope's own height
				{ part = { name = "Low", mat = "stone", size = { 6, 4, 8 }, pos = { 40, 2, 0 }, shape = "Wedge" } },
				{ part = { name = "Awning", mat = "wood", size = { 6, 0.2, 4 }, pos = { 40, 2.6, -2 } } },
				-- a wedge 8 wide and 10 deep (4 x 5 cells), 6 of its 20 cells under awnings: 70% open - no snow
				{ part = { name = "Seven", mat = "stone", size = { 8, 4, 10 }, pos = { 60, 2, 0 }, shape = "Wedge" } },
				{ part = { name = "AwnA", mat = "wood", size = { 8, 0.2, 2 }, pos = { 60, 3.1, -4 } } },
				{ part = { name = "AwnB", mat = "wood", size = { 4, 0.2, 2 }, pos = { 58, 3.1, -2 } } },
				-- the same wedge with 4 of its 20 cells under an awning: 80% open - snow
				{ part = { name = "Eight", mat = "stone", size = { 8, 4, 10 }, pos = { 140, 2, 0 }, shape = "Wedge" } },
				{ part = { name = "AwnC", mat = "wood", size = { 8, 0.2, 2 }, pos = { 140, 3.1, -4 } } },
				-- 55 degrees: snow slides off
				{
					part = {
						name = "FiftyFive",
						mat = "stone",
						size = { 6, 5.7, 4 },
						pos = { 80, 2.85, 0 },
						shape = "Wedge",
					},
				},
				-- a wedge tilted off the level
				{
					part = {
						name = "Tipped",
						mat = "stone",
						size = { 6, 4, 8 },
						pos = { 100, 4, 0 },
						shape = "Wedge",
						rot = { 20, 0, 0 },
					},
				},
			}
			local parts, errors, _, extras = compile({ build = build, cover = SNOW_DUST })
			check.equal(#errors, 0, table.concat(errors, " | "))
			local ramp, low = nil, nil
			for _, s in parts do
				if s.slope and near(s.pos[1], 0, 1) then
					ramp = s
				end
				if s.slope and near(s.pos[1], 40, 1) then
					low = s
				end
			end
			check.truthy(ramp ~= nil, "snow on the ramp")
			check.equal(low, nil)
			check.equal(extras.cover.shapes, 3) -- (the steep wedge, the 55-degree one, the tipped one)
			for _, s in parts do
				check.truthy(
					not (s.slope and (near(s.pos[1], 60, 2) or near(s.pos[1], 80, 2) or near(s.pos[1], 100, 2)))
				)
			end
			local eight = 0
			for _, s in parts do
				eight += if s.slope and near(s.pos[1], 140, 2) then 1 else 0
			end
			check.equal(eight, 1)
			-- a wedge whose top is over "above" and whose middle is under it takes snow
			local above = compile({
				build = {
					{ part = { name = "Ramp", mat = "stone", size = { 6, 4, 8 }, pos = { 0, 2, 0 }, shape = "Wedge" } },
				},
				cover = { snow = { depth = 0.6, above = 3 } },
			})
			local slabs = 0
			for _, s in above do
				slabs += if s.slope then 1 else 0
			end
			check.equal(slabs, 1)
			local L = math.sqrt(16 + 64)
			local extra = 0.6 * 4 / 8
			check.truthy(near(ramp.size[3], L + extra) and near(ramp.size[2], 0.6))
			check.truthy(near(ramp.rot[2][3], 4 / L) and near(ramp.rot[3][3], 8 / L)) -- (its z: up the slope)
			-- its underside's low end lies on the slope's low end
			local lowEnd = {
				ramp.pos[1] - ramp.rot[1][2] * 0.3 - ramp.rot[1][3] * ramp.size[3] / 2,
				ramp.pos[2] - ramp.rot[2][2] * 0.3 - ramp.rot[2][3] * ramp.size[3] / 2,
				ramp.pos[3] - ramp.rot[3][2] * 0.3 - ramp.rot[3][3] * ramp.size[3] / 2,
			}
			check.truthy(near(lowEnd[2], 0) and near(lowEnd[3], -4), `{lowEnd[2]} {lowEnd[3]}`)
			-- a gable roof from the building generator: both halves snowed, their top edges meeting over the ridge
			local house = {
				{
					building = {
						center = { 0, 0, 0 },
						size = { 20, 16 },
						floors = 1,
						floorHeight = 12,
						mat = "wood",
						roof = "gable",
						roofMat = "wood",
						door = { side = "S", width = 6, height = 9 },
					},
				},
			}
			local hp, he = compile({ build = house, cover = SNOW_DUST })
			check.equal(#he, 0, table.concat(he, " | "))
			local halves = {}
			for _, s in hp do
				if s.slope then
					table.insert(halves, s)
				end
			end
			check.equal(#halves, 2)
			-- the top far corner of each: the slab's +z end, +y side
			local function ridgeTop(s: any): { number }
				return {
					s.pos[1] + s.rot[1][2] * s.size[2] / 2 + s.rot[1][3] * s.size[3] / 2,
					s.pos[2] + s.rot[2][2] * s.size[2] / 2 + s.rot[2][3] * s.size[3] / 2,
					s.pos[3] + s.rot[3][2] * s.size[2] / 2 + s.rot[3][3] * s.size[3] / 2,
				}
			end
			local a, b = ridgeTop(halves[1]), ridgeTop(halves[2])
			check.truthy(near(a[2], b[2]) and near(a[3], b[3]), `{a[2]},{a[3]} against {b[2]},{b[3]}`)
			-- dust only: no slab on a slope
			for _, s in (compile({ build = house, cover = { dust = { depth = 0.1 } } })) do
				check.equal(s.slope, nil)
			end
		end)

		test.case("a season's own cover, the lock that asks a world under snow, and the words", function()
			local winter = {
				build = HUT,
				terrain = { { ground = { center = { 0, -1, 0 }, size = { 200, 200 }, material = "Grass" } } },
				seasons = { winter = { terrain = { Grass = "Snow" }, cover = { snow = { depth = 0.8 } } } },
				season = "winter",
			}
			local wp = compile(winter)
			check.equal(at(wp, 0, 0, 12), "snow")
			local summer = table.clone(winter)
			summer.season = false
			check.equal(count((compile(summer)), "snow"), 0)
			check.equal(LaneLocks.unsaidCover(winter), nil)
			-- a season's false is its answer ("bare, meant"), kept through the season
			local bare = table.clone(winter)
			bare.seasons = { winter = { terrain = { Grass = "Snow" }, cover = false } }
			check.equal(LaneLocks.unsaidCover(bare), nil)
			check.equal(count((compile(bare)), "snow"), 0)
			local mute = table.clone(winter)
			mute.seasons = { winter = { terrain = { Grass = "Snow" } } }
			check.equal(LaneLocks.unsaidCover(mute), "in its winter")
			-- snow land of every kind the lock reads
			local function asks(op: any): string?
				return LaneLocks.unsaidCover({ build = HUT, terrain = { op } })
			end
			check.equal(asks({ ground = { material = "Snow" } }), "as written")
			check.equal(asks({ ground = { material = "Glacier" } }), "as written")
			check.equal(asks({ ground = { material = "Grass", under = "Snow" } }), "as written")
			check.equal(
				asks({ ground = { material = "Grass", layers = { { material = "Snow", above = 30 } } } }),
				"as written"
			)
			check.equal(
				asks({ ground = { material = "Grass", patches = { { material = "Snow", above = 0.7 } } } }),
				"as written"
			)
			check.equal(asks({ heightmap = { material = "Grass", paint = { snow = "Snow" } } }), "as written")
			check.equal(asks({ ground = { material = "Grass" } }), nil)
			check.equal(LaneLocks.unsaidCover({ build = HUT, ambient = "snow" }), "as written")
			check.equal(
				LaneLocks.unsaidCover({
					build = HUT,
					weather = { cycle = { { ambient = "rain" }, { ambient = "snow" } } },
				}),
				"as written"
			)
			check.equal(LaneLocks.unsaidCover({ build = HUT, ambient = "snow", cover = false }), nil)
			check.equal(LaneLocks.unsaidCover({ build = HUT, ambient = "rain" }), nil)
			check.equal(LaneLocks.unsaidCover({ build = {}, ambient = "snow" }), nil)
			check.equal(LaneLocks.unsaidCover(nil), nil)
			local named = 0
			for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_cover") do
				if string.find(line, "does not say whether its roofs and ledges are snowed on", 1, true) then
					named += 1
					check.truthy(string.find(line, "SnowRoofsBare", 1, true))
				end
			end
			check.equal(named, 1)
			-- the words
			check.equal(#Cover.problems(false), 0)
			check.equal(#Cover.problems({ snow = { depth = 0.1 } }), 0)
			check.equal(#Cover.problems({ snow = { depth = 4, above = -20 }, dust = { depth = 0.5 } }), 0)
			check.equal(#Cover.problems({ dust = { depth = 0.02 } }), 0)
			local function said(spec: any, text: string)
				local all = table.concat(Cover.problems(spec), " | ")
				check.truthy(string.find(all, text, 1, true), text .. " <- " .. all)
			end
			said(true, '"cover" is {')
			said({}, 'say "snow", "dust" or both')
			said({ ash = {} }, '"ash" is not a word it knows')
			said({ snow = 0.5 }, '"snow" is {')
			said({ snow = { depth = 0.05 } }, "0.1 to 4 studs")
			said({ snow = { depth = 4.1 } }, "0.1 to 4 studs")
			said({ snow = { depth = 1, above = "high" } }, '"above" is the height')
			said({ snow = { depth = 1, deep = 2 } }, '"deep" is not a word it knows')
			said({ dust = { depth = 0.6 } }, "0.02 to 0.5 studs")
			said({ dust = { depth = 0.01 } }, "0.02 to 0.5 studs")
			said({ dust = "thin" }, '"dust" is {')
			local bad, errors = compile({ build = HUT, cover = { snow = { depth = 9 } } })
			check.equal(#errors, 1)
			check.equal(count(bad, "snow"), 0)
			-- the cap: past it, a word and the rest bare
			local keep = Cover.MOST
			Cover.MOST = 2
			local _, _, warns = compile({ build = HUT, cover = SNOW_DUST })
			Cover.MOST = keep
			check.truthy(string.find(table.concat(warns, " | "), "are left bare", 1, true))
			-- each slab goes with its part's own Model (the same streaming)
			local _, _, _, _, model = compile({ build = HUT, cover = SNOW_DUST })
			local roofModel: any = nil
			for _, child in model.Children do
				if child.Name == "Roof" then
					roofModel = child
				end
			end
			local snowInRoof = 0
			for _, c in roofModel.Children do
				if c.Name == "Snow" then
					snowInRoof += 1
				end
			end
			check.truthy(snowInRoof >= 1)
		end)
	end)
end

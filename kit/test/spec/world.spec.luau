-- world.spec.luau (kit) — the world compiler builds correct geometry and its gates catch real problems
-- without crying wolf.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local World = require("../../lib/world")

local PALETTE = { stone = { material = "Slate", color = { 90, 90, 90 } } }

local function bp(steps: { any }): any
	return { name = "T", palette = PALETTE, build = steps }
end

local function issues(steps: { any }): (string, string)
	local _, _, list = World.compile(bp(steps))
	local errors, warns = {}, {}
	for _, i in list do
		table.insert(if i.severity == "error" then errors else warns, i.message)
	end
	return table.concat(errors, "\n"), table.concat(warns, "\n")
end

return function()
	test.suite("World geometry", function()
		test.case("wall runs from -> to (local X along the wall)", function()
			local _, parts = World.compile(
				bp({ { wall = { from = { 0, 0 }, to = { 0, 10 }, height = 4, thickness = 1, mat = "stone" } } })
			)
			local p = parts[1]
			check.is_true(math.abs(p.pos[1]) < 1e-6 and math.abs(p.pos[3] - 5) < 1e-6)
			check.is_true(math.abs(p.size[1] - 10) < 1e-6)
			-- rotation column 1 = where local X points: must be +Z for a wall going toward +Z
			check.is_true(math.abs(p.rot[3][1] - 1) < 1e-6)
		end)
		test.case("wall gaps leave a doorway and a lintel", function()
			local _, parts = World.compile(bp({
				{
					wall = {
						from = { 0, 0 },
						to = { 20, 0 },
						height = 10,
						thickness = 1,
						mat = "stone",
						gaps = { { at = 10, width = 4, height = 7 } },
					},
				},
			}))
			check.equal(#parts, 3) -- left, lintel, right
		end)
		test.case("ring segments are tangent to the circle", function()
			local _, parts = World.compile(bp({
				{
					ring = {
						center = { 0, 0, 0 },
						radius = 30,
						height = 5,
						thickness = 1,
						segments = 12,
						mat = "stone",
					},
				},
			}))
			check.equal(#parts, 12)
			for _, p in parts do
				local rx, rz = p.pos[1] / 30, p.pos[3] / 30 -- radial direction
				local lx, lz = p.rot[1][1], p.rot[3][1] -- local X direction
				check.is_true(math.abs(rx * lx + rz * lz) < 1e-6)
			end
		end)
		test.case("ring gaps are spread evenly and never delete the ring (review finding)", function()
			local _, parts = World.compile(bp({
				{
					ring = {
						center = { 0, 0, 0 },
						radius = 10,
						height = 4,
						thickness = 2,
						segments = 4,
						gaps = 3,
						mat = "stone",
					},
				},
			}))
			check.equal(#parts, 1)
			local _, eight = World.compile(bp({
				{
					ring = {
						center = { 0, 0, 0 },
						radius = 10,
						height = 4,
						thickness = 2,
						segments = 8,
						gaps = 2,
						mat = "stone",
					},
				},
			}))
			check.equal(#eight, 6)
			local errors = issues({
				{
					ring = {
						center = { 0, 0, 0 },
						radius = 10,
						height = 4,
						thickness = 2,
						segments = 4,
						gaps = 4,
						mat = "stone",
					},
				},
			})
			check.is_true(string.find(errors, "removes the whole ring", 1, true) ~= nil)
		end)
		test.case("ring segments close the outer corners (review finding)", function()
			local R, t, n = 10, 4, 4
			local _, parts = World.compile(bp({
				{
					ring = {
						center = { 0, 0, 0 },
						radius = R,
						height = 4,
						thickness = t,
						segments = n,
						mat = "stone",
					},
				},
			}))
			-- outer corner of a regular n-gon at radius R + t/2 needs half-length (R + t/2) * tan(pi/n) ... the
			-- segment must at least reach the neighbour's outer edge: length >= 2 * (R + t/2) * sin(pi/n)
			check.is_true(parts[1].size[1] >= 2 * (R + t / 2) * math.sin(math.pi / n) - 1e-6)
		end)
		test.case("scatter count 0 is an error (review finding)", function()
			local errors = issues({
				{
					scatter = {
						center = { 0, 0, 0 },
						area = { 10, 10 },
						count = 0,
						part = { size = { 1, 1, 1 }, mat = "stone" },
					},
				},
			})
			check.is_true(string.find(errors, "count must be", 1, true) ~= nil)
		end)
		test.case("scatter is deterministic and overlap-free", function()
			local step = {
				scatter = {
					center = { 0, 0, 0 },
					area = { 60, 60 },
					count = 12,
					seed = 3,
					gap = 1,
					part = { size = { 4, 4, 4 }, mat = "stone" },
				},
			}
			local _, a = World.compile(bp({ step }))
			local _, b = World.compile(bp({ step }))
			check.equal(#a, 12)
			for i = 1, #a do
				check.equal(a[i].pos[1], b[i].pos[1])
				for j = i + 1, #a do
					local d = math.sqrt((a[i].pos[1] - a[j].pos[1]) ^ 2 + (a[i].pos[3] - a[j].pos[3]) ^ 2)
					check.is_true(d >= 4)
				end
			end
		end)
	end)

	test.suite("World gates", function()
		test.case("visible z-fighting is reported", function()
			local _, warns = issues({
				{ part = { name = "A", size = { 10, 2, 10 }, pos = { 0, 1, 0 }, mat = "stone" } },
				{ part = { name = "B", size = { 10, 2, 10 }, pos = { 4, 1, 0 }, mat = "stone" } },
			})
			check.is_true(string.find(warns, "z-fighting", 1, true) ~= nil)
		end)
		test.case("faces resting on a surface are not z-fighting", function()
			local _, warns = issues({
				{ floor = { center = { 0, 0, 0 }, size = { 50, 50 }, mat = "stone" } },
				{ part = { name = "A", size = { 2, 4, 2 }, pos = { 0, 2, 0 }, mat = "stone" } },
				{ part = { name = "B", size = { 4, 2, 4 }, pos = { 0, 1, 0 }, mat = "stone" } },
			})
			check.is_true(string.find(warns, "z-fighting", 1, true) == nil)
		end)
		test.case("a building's ground floor stands clear of the floor it is built on (card my7f)", function()
			-- GothicCourtyard: the houses' wooden ground slabs (tops at y = 0) lay in the plane of the court's slate
			-- floor (top at y = 0) and flickered in Roblox; the boards now stand GROUND_LIFT over the storey line, the
			-- slab's foot where it was (no slit for a plinth or the ground's cut), the floors above on their lines
			check.is_true(World.GROUND_LIFT >= 0.05) -- (kit world check's z-fighting band is 0.03 studs)
			local wood = { material = "WoodPlanks", color = { 120, 80, 50 } }
			local _, parts = World.compile({
				name = "T",
				palette = { stone = PALETTE.stone, wood = wood },
				build = {
					{ floor = { center = { 0, 0, 0 }, size = { 80, 80 }, mat = "stone" } },
					{
						building = {
							center = { 0, 0, 0 },
							size = { 20, 22 },
							floors = 2,
							floorHeight = 14,
							mat = "stone",
							slab = "wood",
							roof = "flat",
						},
					},
				},
			})
			local tops, ground = {}, nil
			for _, p in parts do
				if p.name == "Slab" then
					local top, foot = p.pos[2] + p.size[2] / 2, p.pos[2] - p.size[2] / 2
					table.insert(tops, top)
					if top < 7 then
						ground = { top = top, foot = foot, mat = p.material }
					end
				end
			end
			check.truthy(ground ~= nil)
			check.equal(ground.mat, "WoodPlanks")
			check.truthy(math.abs(ground.top - World.GROUND_LIFT) < 1e-9) -- (the court's floor top is 0)
			check.truthy(math.abs(ground.foot - -1) < 1e-9)
			for _, top in tops do -- the floor above, and the roof's slab, on their storey lines
				check.truthy(top < 7 or math.abs(top % 14) < 1e-9)
			end
		end)
		test.case(
			"lights that cast shadows near one another: over 16 a warning, over 24 an error (V3 stage F.2)",
			function()
				local function lamps(n: number, apart: number, shadows: boolean): (string, string)
					local steps = {}
					for k = 1, n do
						table.insert(steps, {
							part = {
								name = `Lamp{k}`,
								size = { 1, 1, 1 },
								pos = { (k - 1) * apart, 8, 0 },
								mat = "stone",
								collide = false,
								light = { range = 20, shadows = shadows },
							},
						})
					end
					return issues(steps)
				end
				local e, w = lamps(25, 4, true) -- (25 within 96 studs)
				check.truthy(string.find(e, "lights that cast shadows", 1, true) ~= nil)
				e, w = lamps(17, 4, true)
				check.equal(string.find(e, "lights that cast shadows", 1, true), nil)
				check.truthy(string.find(w, "lights that cast shadows", 1, true) ~= nil)
				e, w = lamps(16, 4, true)
				check.equal(string.find(e .. w, "lights that cast shadows", 1, true), nil)
				e, w = lamps(40, 60, true) -- (spread out: at most 5 within 120 studs of any one)
				check.equal(string.find(e .. w, "lights that cast shadows", 1, true), nil)
				e, w = lamps(40, 2, false) -- (no shadows: not counted)
				check.equal(string.find(e .. w, "lights that cast shadows", 1, true), nil)
			end
		)
		test.case("buried spawn, kill plane and unknown palette are errors", function()
			local errors = issues({
				{ part = { name = "Block", size = { 20, 20, 20 }, pos = { 0, 10, 0 }, mat = "stone" } },
				{ spawn = { pos = { 0, 0, 0 }, mat = "stone" } },
				{ part = { name = "Deep", size = { 2, 2, 2 }, pos = { 0, -900, 0 }, mat = "stone" } },
				{ part = { name = "X", size = { 1, 1, 1 }, pos = { 50, 1, 0 }, mat = "lava" } },
			})
			check.is_true(string.find(errors, "buried", 1, true) ~= nil)
			check.is_true(string.find(errors, "kill plane", 1, true) ~= nil)
			check.is_true(string.find(errors, "unknown palette", 1, true) ~= nil)
		end)
		test.case("the kit world template compiles without errors", function()
			local spec =
				serde.decode("json", string.gsub(fs.readFile("kit/templates/world.json"), "__NAME__", "Template"))
			local _, parts, list = World.compile(spec)
			local errors = 0
			for _, i in list do
				if i.severity == "error" then
					errors += 1
				end
			end
			check.equal(errors, 0)
			check.is_true(#parts > 50)
		end)
	end)

	test.suite("World generators v2", function()
		local function named(parts: { any }, name: string): { any }
			local out = {}
			for _, p in parts do
				if p.name == name then
					table.insert(out, p)
				end
			end
			return out
		end
		test.case("a room: four walls, a doorway open to the floor, a window with a sill", function()
			local _, parts = World.compile(bp({
				{
					room = {
						center = { 0, 0, 0 },
						size = { 20, 16 },
						height = 10,
						mat = "stone",
						openings = {
							{ side = "S", width = 6, height = 8 },
							{ side = "N", width = 4, height = 6, sill = 3 },
						},
					},
				},
			}))
			check.equal(#named(parts, "Sill"), 1) -- (the window's; a doorway has no sill)
			check.equal(#named(parts, "Lintel"), 2)
			check.is_true(#named(parts, "Wall") >= 6) -- (4 sides; two of them split by an opening)
		end)
		test.case(
			"a building with stairs: a flight per floor, a stairwell cut in the slab above, a hatch on a flat roof",
			function()
				local _, parts, list = World.compile(bp({
					{
						building = {
							center = { 0, 0, 0 },
							size = { 20, 30 },
							floors = 2,
							floorHeight = 12,
							mat = "stone",
							roof = "flat",
							stairs = true,
						},
					},
				}))
				for _, i in list do
					check.is_true(i.severity ~= "error")
				end
				check.equal(#named(parts, "Stair"), 24) -- (12 one-stud steps x 2 flights: floor 2 + the roof)
				check.is_true(#named(parts, "Slab") >= 1 + 4 + 4) -- (ground slab, then 4 pieces around each stairwell)
			end
		)
		test.case("a building too shallow for its stairs is an error", function()
			local _, errors = nil, ""
			errors = issues({
				{
					building = {
						center = { 0, 0, 0 },
						size = { 20, 10 },
						floors = 2,
						floorHeight = 12,
						mat = "stone",
						stairs = true,
					},
				},
			})
			check.is_true(string.find(errors, "stair run", 1, true) ~= nil)
		end)
		test.case("breakables carry their tags into the model", function()
			local model, parts = World.compile(bp({
				{
					breakable = {
						name = "Crate",
						size = { 4, 4, 4 },
						pos = { 0, 2, 0 },
						mat = "stone",
						health = 30,
					},
				},
			}))
			check.equal(parts[1].attributes.KitBreakable, true)
			check.equal(parts[1].attributes.KitHealth, 30)
			local text = serde.encode("json", model)
			check.is_true(string.find(text, "KitBreakable", 1, true) ~= nil)
		end)
		test.case("cover is half (3) or full (7) studs and keeps its gaps; a path has joints", function()
			local _, parts = World.compile(bp({
				{ cover = { center = { 0, 0, 0 }, area = { 80, 80 }, count = 6, seed = 2, mat = "stone" } },
				{ path = { points = { { 0, 0 }, { 30, 0 }, { 30, 30 } }, width = 8, mat = "stone" } },
			}))
			local covers = 0
			for _, p in parts do
				if p.name == "HalfCover" or p.name == "FullCover" then
					covers += 1
					check.is_true(p.size[2] == 3 or p.size[2] == 7)
				end
			end
			check.equal(covers, 6)
			check.equal(#named(parts, "PathJoint"), 1)
		end)
		test.case(
			"a heightmap terrain: samples ride in KitTerrain chunk modules under Roblox's Source cap, the attribute names them in order, they rejoin to the file's heights",
			function()
				local spec = serde.decode("json", fs.readFile("kit/selftest/world/_selftest_valley.json"))
				local model, _, list = World.compile(spec)
				for _, i in list do
					check.is_true(i.severity ~= "error")
				end
				local env = serde.decode("json", model.Properties.Attributes.Attributes.KitEnvironment.String)
				check.equal(env.terrain[1].kind, "ground")
				check.equal(env.terrain[1].spec.samples.heights, nil) -- (not in the attribute: too big)
				local names = env.terrain[1].spec.samples.modules
				check.is_true(type(names) == "table" and #names >= 1)
				local byName = {}
				for _, c in model.Children or {} do
					if c.ClassName == "ModuleScript" then
						byName[c.Name] = c.Properties.Source
					end
				end
				local joined = {}
				for k, name in names do
					check.equal(name, `KitTerrain1_{k}`)
					local src = byName[name]
					check.is_true(type(src) == "string" and string.sub(src, 1, 2) == "--")
					check.is_true(#src < 200000) -- (Roblox caps a string property near 200,000 characters)
					for v in string.gmatch(string.match(src, "return { (.*) }") or "", "[^,]+") do
						table.insert(joined, tonumber(v))
					end
				end
				local hmFile = serde.decode("json", fs.readFile("kit/selftest/world/terrain/_selftest_valley.hm.json"))
				check.equal(#joined, #hmFile.heights)
				check.equal(joined[1], hmFile.heights[1])
				check.equal(joined[#joined], hmFile.heights[#hmFile.heights])
				-- the analysis field samples the same heights: the grid corner = the file's first sample
				local hm = serde.decode("json", fs.readFile("kit/selftest/world/terrain/_selftest_valley.hm.json"))
				local field = World.terrainField(spec)
				check.is_true(math.abs(field.ground[1].heights[1] - hm.heights[1]) < 0.02)
			end
		)
		test.case("terrain chunks split across real boundaries and rejoin exactly, in order", function()
			local spec = serde.decode("json", fs.readFile("kit/selftest/world/_selftest_valley.json"))
			local saved = World.MODULE_CHARS
			World.MODULE_CHARS = 3000 -- (the valley fits one 100k chunk: force several)
			local ok, model = pcall(World.compile, spec)
			World.MODULE_CHARS = saved
			check.is_true(ok)
			local env = serde.decode("json", model.Properties.Attributes.Attributes.KitEnvironment.String)
			local names = env.terrain[1].spec.samples.modules
			check.is_true(#names >= 5)
			local byName = {}
			for _, c in model.Children or {} do
				if c.ClassName == "ModuleScript" then
					byName[c.Name] = c.Properties.Source
				end
			end
			local joined = {}
			for _, name in names do
				local src = byName[name]
				check.is_true(#src <= 3000 + 80) -- (the chunk limit plus its one-line header)
				for v in string.gmatch(string.match(src, "return { (.*) }") or "", "[^,]+") do
					table.insert(joined, tonumber(v))
				end
			end
			local hmFile = serde.decode("json", fs.readFile("kit/selftest/world/terrain/_selftest_valley.hm.json"))
			check.equal(#joined, #hmFile.heights)
			local same = true
			for i, v in hmFile.heights do
				if math.abs(joined[i] - v) > 1e-9 then
					same = false
				end
			end
			check.is_true(same) -- (every sample, in order: none lost or split at a boundary)
		end)
		test.case("a heightmap source that is not a heightmap is an error", function()
			local errors = issues({})
			local _, _, list = World.compile({
				name = "T",
				palette = PALETTE,
				build = {},
				terrain = {
					{
						heightmap = {
							center = { 0, 0, 0 },
							size = { 64, 64 },
							source = "kit.config.json",
							material = "Grass",
						},
					},
				},
			})
			for _, i in list do
				if i.severity == "error" then
					errors ..= i.message
				end
			end
			check.is_true(string.find(errors, "not a heightmap", 1, true) ~= nil)
		end)
		test.case("the battlegrounds arena starter compiles without errors", function()
			local spec = serde.decode("json", fs.readFile("kit/starter/worlds/BattlegroundsArena.json"))
			local _, parts, list = World.compile(spec)
			for _, i in list do
				check.is_true(i.severity ~= "error")
			end
			check.is_true(#parts > 100)
		end)
	end)
	test.suite("World ecology (painted roles)", function()
		-- a 3 x 3 painted ground 20 studs wide: rows of roles meadow / rock / sand along x
		local spec = {
			center = { 0, 0, 0 },
			size = { 20, 20 },
			samples = {
				nx = 3,
				nz = 3,
				heights = { 0, 0, 0, 0, 0, 0, 0, 0, 0 },
				splat = "000111222",
				roles = { "meadow", "rock", "sand" },
			},
		}
		test.case("roleAt reads the painted role of the nearest cell", function()
			check.equal(World.roleAt(spec, -10, 0), "meadow")
			check.equal(World.roleAt(spec, 0, 5), "rock")
			check.equal(World.roleAt(spec, 10, -10), "sand")
			check.equal(
				World.roleAt({ center = { 0, 0, 0 }, size = { 20, 20 }, samples = { nx = 3, nz = 3 } }, 0, 0),
				nil
			)
		end)
	end)
	test.suite("World acoustics (which parts let sound through)", function()
		test.case("non-colliding parts pass, roofs / panes still muffle, a spec decides outright", function()
			check.is_true(World.audioPass("Canopy", false, {}))
			check.is_true(World.audioPass("Rug", false, {}))
			check.is_false(World.audioPass("Wall", true, {}))
			check.is_false(World.audioPass("RoofN", false, {})) -- (a decorative roof still muffles the rain of sound)
			check.is_false(World.audioPass("Pane", false, {}))
			check.is_false(World.audioPass("KitMesh", false, {})) -- (placeholders decide by their mesh)
			check.is_true(World.audioPass("Wall", true, { audio = false }))
			check.is_false(World.audioPass("Mist", false, { audio = true }))
		end)
	end)
	test.suite("World ground contact", function()
		local function envOf(model: any): any
			local found = nil
			local function walk(n: any)
				local a = n.Properties and n.Properties.Attributes and n.Properties.Attributes.Attributes
				if a and a.KitEnvironment then
					found = serde.decode("json", a.KitEnvironment.String)
				end
				for _, c in n.Children or {} do
					walk(c)
				end
			end
			walk(model)
			return found
		end
		test.case(
			"a wall on the land gets a worn skirt of 4-stud cells; a floor slab and a floating part do not",
			function()
				local spec = {
					name = "T",
					palette = PALETTE,
					terrain = { { ground = { center = { 0, 10, 0 }, size = { 200, 200 }, material = "Grass" } } },
					contact = { material = "Ground" },
					build = {
						{ part = { name = "Wall", size = { 20, 10, 2 }, pos = { 0, 15, 0 }, mat = "stone" } },
						{ part = { name = "Slab", size = { 20, 1, 20 }, pos = { 50, 10.5, 50 }, mat = "stone" } },
						{ part = { name = "Lamp", size = { 2, 2, 2 }, pos = { -50, 60, -50 }, mat = "stone" } },
					},
				}
				local model = World.compile(spec)
				local env = envOf(model)
				check.not_nil(env)
				check.not_nil(env.contact)
				check.equal(env.contact.material, "Ground")
				local cells = env.contact.cells
				check.is_true(#cells >= 9 and #cells % 3 == 0)
				for i = 1, #cells - 2, 3 do
					check.is_true(math.abs(cells[i]) < 20 and math.abs(cells[i + 2]) < 20) -- (all round the wall only)
					check.equal(cells[i] % 4, 2) -- (on the terrain's 4-stud grid)
				end
			end
		)
		test.case('no "contact" in the blueprint: nothing is painted', function()
			local model = World.compile({
				name = "T",
				palette = PALETTE,
				terrain = { { ground = { center = { 0, 10, 0 }, size = { 200, 200 }, material = "Grass" } } },
				build = { { part = { name = "Wall", size = { 20, 10, 2 }, pos = { 0, 15, 0 }, mat = "stone" } } },
			})
			check.equal(envOf(model).contact, nil)
		end)
	end)
	test.suite("World streaming + LOD", function()
		test.case("a map-wide step splits into area Models with the far stand-in; a small one stays whole", function()
			local model = World.compile({
				name = "T",
				palette = PALETTE,
				streaming = { cell = 128 },
				build = {
					{ part = { name = "Hut", size = { 10, 10, 10 }, pos = { 0, 5, 0 }, mat = "stone" } },
					{
						grid = {
							name = "Posts",
							origin = { -300, 2, 0 },
							count = { 6, 1 },
							spacing = { 120, 10 },
							part = { size = { 2, 4, 2 }, mat = "stone" },
						},
					},
				},
			})
			local names, lod = {}, 0
			for _, c in (model :: any).Children do
				table.insert(names, c.Name)
				if c.Properties and c.Properties.LevelOfDetail == "StreamingMesh" then
					lod += 1
				end
			end
			local cells = 0
			for _, n in names do
				if string.find(n, "_c", 1, true) then
					cells += 1
				end
			end
			check.is_true(cells >= 4) -- (600 studs of posts in 128-stud cells)
			check.is_true(lod >= cells + 1)
		end)
	end)
	test.suite("World story dressing", function()
		test.case(
			"a camp, a battle aftermath and a lost cart each build their scene; an unknown story is named",
			function()
				local function names(kind: string): { [string]: number }
					local _, parts = World.compile({
						name = "T",
						palette = PALETTE,
						build = { { story = { kind = kind, center = { 0, 0, 0 }, seed = 2, mat = "stone" } } },
					})
					local out = {}
					for _, p in parts do
						out[p.name] = (out[p.name] or 0) + 1
					end
					return out
				end
				local camp = names("camp")
				check.equal(camp.RingStone, 10)
				check.equal(camp.Fire, 1)
				check.equal(camp.Tent, 2)
				local battle = names("battle")
				check.equal(battle.Blade, 7)
				check.equal(battle.Shield, 4)
				local cart = names("cart")
				check.equal(cart.Wheel, 4)
				check.equal(cart.CartBed, 1)
				local _, _, list = World.compile({
					name = "T",
					palette = PALETTE,
					build = { { story = { kind = "picnic", center = { 0, 0, 0 } } } },
				})
				local named = false
				for _, i in list do
					named = named or (i.severity == "error" and string.find(i.message, "story kind", 1, true) ~= nil)
				end
				check.is_true(named)
			end
		)
	end)
	test.suite("World R6 claims (the generators claim the sizes they build)", function()
		local function fitsOf(steps: { any }): { any }
			local _, _, _, extras = World.compile(bp(steps))
			return (extras and extras.fits) or {}
		end
		test.case("a building claims every floor's clear ceiling, its door and its stairs (not its windows)", function()
			local fits = fitsOf({
				{
					building = {
						name = "H",
						center = { 0, 0, 0 },
						size = { 24, 40 },
						floors = 2,
						floorHeight = 11,
						mat = "stone",
						stairs = true,
						roof = "flat",
						door = { side = "S", width = 6, height = 8.5 },
					},
				},
			})
			local kinds = {}
			for _, f in fits do
				kinds[f.kind] = (kinds[f.kind] or 0) + 1
				if f.kind == "ceiling" then
					-- (11 floor to floor: 10 under the next slab - a room a head too low - and 11 under the flat roof)
					check.equal(f.size[2], if string.find(f.name, "floor 1") then 10 else 11)
				end
			end
			check.equal(kinds.ceiling, 2)
			check.equal(kinds.opening, 1)
			check.equal(kinds.sill, nil) -- (windows are not claimed: clerestories, broken gaps)
			check.equal(kinds.step, 1)
		end)
		test.case(
			"the defaults sit on the R6 rig: 14 floor to floor, 3-stud bridge rails; a gable top floor claims none",
			function()
				local fits = fitsOf({
					{ building = { name = "D", center = { 0, 0, 0 }, size = { 24, 20 }, floors = 1, mat = "stone" } },
					{ bridge = { name = "B", from = { 40, 0 }, to = { 70, 0 }, y = 6, mat = "stone" } },
				})
				local seen = {}
				for _, f in fits do
					seen[f.kind] = f
				end
				check.equal(seen.ceiling.size[2], 14)
				check.equal(seen.rail.size[2], 3)
				local gable = fitsOf({
					{
						building = {
							name = "G",
							center = { 0, 0, 0 },
							size = { 24, 20 },
							floors = 1,
							roof = "gable",
							mat = "stone",
						},
					},
				})
				for _, f in gable do
					check.is_true(f.kind ~= "ceiling") -- (open to the ridge)
				end
			end
		)
		test.case(
			"a roofed room claims its ceiling and its doorways; a wide gap is an open side, not a door",
			function()
				local fits = fitsOf({
					{
						room = {
							name = "R",
							center = { 0, 0, 0 },
							size = { 30, 30 },
							height = 8,
							mat = "stone",
							roof = "stone",
							openings = { { side = "N", width = 4, height = 7 }, { side = "S", width = 16, height = 8 } },
						},
					},
				})
				local ceilings, openings = 0, {}
				for _, f in fits do
					if f.kind == "ceiling" then
						ceilings += 1
						check.equal(f.size[2], 8)
					elseif f.kind == "opening" then
						table.insert(openings, f)
					end
				end
				check.equal(ceilings, 1)
				check.equal(#openings, 1) -- (only the 4-wide doorway; the 16-wide gap is an open side)
				check.equal(openings[1].size[1], 4)
				local yard = fitsOf({
					{ room = { name = "Y", center = { 0, 0, 0 }, size = { 30, 30 }, height = 8, mat = "stone" } },
				})
				for _, f in yard do
					check.is_true(f.kind ~= "ceiling") -- (a roofless yard or ruin has no ceiling)
				end
			end
		)
	end)

	-- a building's "skin" (a whole-building mesh) wraps it only when its door and windows land on the building's
	-- gaps: a gap behind solid stone lets a player through a wall, stone over a gap shuts a doorway
	test.suite("World building skins (the gaps line up)", function()
		local reg = {
			footprint = { 22, 30 },
			floors = 4,
			floorHeight = 14,
			door = { side = "S", width = 5, height = 9 },
			windows = { every = 10, width = 3.4, height = 7, sill = 3.5, sides = { "S", "N" } },
		}
		local win = { every = 10, width = 3.4, height = 7, sill = 3.5, sides = { "S", "N" } }
		local door = { side = "S", width = 5, height = 9 }
		test.case(
			"a skin turns with its door: the front S lands on the door's side, every side turns with it",
			function()
				check.equal(World.skinSide(0, "S"), "S")
				check.equal(World.skinSide(90, "S"), "E")
				check.equal(World.skinSide(180, "S"), "N")
				check.equal(World.skinSide(270, "S"), "W")
				check.equal(World.skinSide(270, "N"), "E") -- (a west-facing house's back is its east side)
				check.equal(World.SKIN_YAW.W, 270)
			end
		)
		test.case(
			"the skin cut for this building fits it; a south-facing one, then the same skin turned west",
			function()
				local fits = World.skinProblem(reg, "h", { 22, 30 }, 4, 14, door, win, 0)
				check.is_true(fits == nil, fits or "")
				local westDoor = { side = "W", width = 5, height = 9 }
				local westWin = { every = 10, width = 3.4, height = 7, sill = 3.5, sides = { "W", "E" } }
				-- (turned 270: its 22-stud front runs along z, its 30-stud depth along x)
				local turned = World.skinProblem(reg, "h", { 30, 22 }, 4, 14, westDoor, westWin, 270)
				check.is_true(turned == nil, turned or "")
			end
		)
		test.case("a skin for another footprint, floors, door or window run is refused, naming the mismatch", function()
			local function says(msg: string?, needle: string)
				check.is_true(msg ~= nil and string.find(msg, needle, 1, true) ~= nil, msg or "(nil)")
			end
			says(World.skinProblem(reg, "h", { 24, 30 }, 4, 14, door, win, 0), "22 x 30")
			says(World.skinProblem(reg, "h", { 22, 30 }, 5, 14, door, win, 0), "floors")
			says(World.skinProblem(reg, "h", { 22, 30 }, 4, 14, { side = "S", width = 6, height = 9 }, win, 0), "door")
			says(
				World.skinProblem(
					reg,
					"h",
					{ 22, 30 },
					4,
					14,
					door,
					{ every = 12, width = 3.4, height = 7, sill = 3.5, sides = { "S", "N" } },
					0
				),
				"every"
			)
			-- windows on a side where the skin is solid stone: a gap behind it
			says(
				World.skinProblem(
					reg,
					"h",
					{ 22, 30 },
					4,
					14,
					door,
					{ every = 10, width = 3.4, height = 7, sill = 3.5 },
					0
				),
				"E side"
			)
			-- not turned with its door: the windows land on the wrong sides
			says(
				World.skinProblem(reg, "h", { 30, 22 }, 4, 14, { side = "W", width = 5, height = 9 }, win, 270),
				"side"
			)
			says(World.skinProblem(nil, "nope", { 22, 30 }, 4, 14, door, win, 0), "no world mesh")
			says(
				World.skinProblem({ size = { 1, 1, 1 } }, "rock", { 22, 30 }, 4, 14, door, win, 0),
				"not a building skin"
			)
		end)
	end)

	-- the room kinds a house's floors name (kit/lib/interior.luau Interior.KINDS; V3 stage D): a kind it does not
	-- know is an error - it furnished an empty room, said nowhere
	test.suite("World building interiors: room kinds", function()
		local function house(floors: { string }): any
			return {
				building = {
					name = "House",
					center = { 0, 0, 0 },
					size = { 24, 22 },
					floors = #floors,
					floorHeight = 14,
					thickness = 1,
					mat = "stone",
					stairs = #floors > 1,
					door = { side = "S", width = 5, height = 8.5 },
					interior = { floors = floors },
				},
			}
		end
		test.case("a kitchen, a study and a workshop are furnished; an unknown kind is said", function()
			local _, parts = World.compile(bp({ house({ "kitchen", "study", "workshop" }) }))
			local seen = {}
			for _, p in parts do
				seen[p.name] = true
			end
			check.is_true(seen.Oven == true and seen.Bookcase == true and seen.Workbench == true)
			local errors = issues({ house({ "pantry" }) })
			check.truthy(string.find(errors, 'no room kind "pantry"', 1, true) ~= nil, errors)
			check.equal(issues({ house({ "kitchen" }) }), "")
		end)
	end)
end

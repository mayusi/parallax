-- worldstages.spec.luau (kit) — THE WORLD'S ROUTE STAGES (LIMITATIONS_FIXES_V3.md stage A.2-A.3; the studio route's W1
-- "World Bible & Walked Greybox ... before meshes" and W2 "drive ONE 40x40 corner ... before scaling any full street").
-- Held here: the GREYBOX compile (World.compile's opts.greybox: kit world greybox) wears no skin or facade - the house
-- built plain, its walls seen - and puts a plain grey box of each mesh's own size where the mesh stood, the far ranges
-- as their wedges; and the LOCK (LaneLocks.worldStages): a new world dressed in meshes is held until its greybox has
-- the owner's yes, a new town until its corner has, a world that stood before the rule is not held, and a world of
-- primitives alone is held to neither. The bible and the stage tools: kit/test/python/test_world_stages.py.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local LaneLocks = require("../../lib/lanelocks")
local Locks = require("../../lib/locks")
local World = require("../../lib/world")

local PALETTE = { stone = { material = "Slate", color = { 90, 90, 90 } } }

local REG = {
	whole = {
		kind = "gothic_house",
		size = { 25, 40, 26 },
		min = { -12.5, 0, -13 },
		footprint = { 23, 24 },
		floors = 2,
		floorHeight = 14,
		windows = { every = 10, width = 4, height = 7, sill = 3.5, sides = { "S", "E", "N", "W" } },
		door = { side = "S", width = 5, height = 8.5 },
	},
	well = { kind = "gothic_well", size = { 6, 4, 6 }, min = { -3, 0, -3 } },
}

local function house(more: any?): any
	local b: any = {
		name = "House",
		center = { 0, 0, 0 },
		size = { 23, 24 },
		floors = 2,
		floorHeight = 14,
		thickness = 1,
		mat = "stone",
		door = { side = "S", width = 5, height = 8.5 },
		windows = { every = 10, width = 4, height = 7, sill = 3.5, sides = { "S", "E", "N", "W" } },
	}
	for k, v in more or {} do
		b[k] = v
	end
	return { building = b }
end

local function compile(steps: { any }, opts: any): ({ any }, { string })
	local _, parts, issues = World.compile({ name = "T", palette = PALETTE, scale = "r6", build = steps }, opts)
	local errors = {}
	for _, i in issues do
		if i.severity == "error" and i.path ~= "spawn" then
			table.insert(errors, i.message)
		end
	end
	return parts, errors
end

return function()
	test.suite("World greybox (kit world greybox)", function()
		test.case("no skin worn, the house plain and seen; a mesh is a grey box of its own size", function()
			local steps = {
				house({ skin = "whole" }),
				{ mesh = { name = "Well", mesh = "well", pos = { 40, 0, 0 }, mat = "stone" } },
			}
			local dressed = compile(steps, { meshes = REG })
			local grey, errors = compile(steps, { meshes = REG, greybox = true })
			check.equal(#errors, 0, table.concat(errors, " | "))
			local function count(parts: { any }): (number, number, number)
				local meshes, hidden, boxes = 0, 0, 0
				for _, p in parts do
					if p.mesh then
						meshes += 1
					elseif p.name == "Greybox" then
						boxes += 1
					elseif p.name == "Wall" and p.transparency == 1 then
						hidden += 1
					end
				end
				return meshes, hidden, boxes
			end
			local m0, h0 = count(dressed)
			check.truthy(m0 >= 2 and h0 > 0) -- (dressed: the skin and the well are meshes, the walls unseen)
			local m1, h1, b1 = count(grey)
			check.equal(m1, 0)
			check.equal(h1, 0)
			check.equal(b1, 1) -- (the well, as a box)
			for _, p in grey do
				if p.name == "Greybox" then
					check.truthy(math.abs(p.size[1] - 6) < 1e-6 and math.abs(p.size[2] - 4) < 1e-6)
					check.truthy(math.abs(p.pos[1] - 40) < 1e-6 and math.abs(p.pos[2] - 2) < 1e-6)
				end
			end
		end)
	end)

	test.suite("World route stages lock", function()
		test.case("what a world is held to: meshes ask for the greybox, a town for the corner", function()
			check.is_true(LaneLocks.dressedInMeshes({ build = { house({ skin = "whole" }) } }))
			check.is_true(LaneLocks.dressedInMeshes({ build = { { forest = { meshes = { "oak_a" } } } } }))
			check.is_true(LaneLocks.dressedInMeshes({ build = { { horizon = { hlod = "far_ring" } } } }))
			check.is_false(LaneLocks.dressedInMeshes({ build = { house() } }))
			check.is_true(LaneLocks.streetsOfHouses({ build = { { town = { center = { 0, 0, 0 } } } } }))
			check.is_false(LaneLocks.streetsOfHouses({ build = { house() } }))
			-- (a town dressed through its house types: "skins" puts a mesh on every house)
			check.is_true(LaneLocks.dressedInMeshes({ build = { { town = { skins = { "gc_house_a" } } } } }))
			check.is_true(LaneLocks.dressedInMeshes({ build = { { town = { skins = "gc_house" } } } }))
		end)

		test.case("a new world in meshes is held until its greybox is approved; one from before is not", function()
			local bp = {
				name = "Fresh",
				scale = "r6",
				build = { house({ skin = "whole" }), { town = { center = { 0, 0, 0 } } } },
			}
			local lines = LaneLocks.worldStages("assets/worlds/Fresh.json", "Fresh", bp, ".")
			local all = table.concat(lines, "\n")
			check.equal(#lines, 2)
			check.truthy(string.find(all, "walked greybox", 1, true) ~= nil, all)
			check.truthy(string.find(all, "lune run kit world greybox Fresh", 1, true) ~= nil, all)
			check.truthy(string.find(all, "40 x 40 corner", 1, true) ~= nil, all)
			check.truthy(string.find(all, "--stage corner", 1, true) ~= nil, all)
			-- a world of primitives alone, and one that stood before the rule: nothing asked
			check.equal(#LaneLocks.worldStages("assets/worlds/Plain.json", "Plain", { build = { house() } }, "."), 0)
			-- (a project lists its own older worlds: the kit ships the list empty)
			LaneLocks.STAGES_RULE_BEFORE["assets/worlds/oldcourt.json"] = true
			LaneLocks.STAGES_RULE_BEFORE["games/samplegame/assets/worlds/oldruins.json"] = true
			local court = #LaneLocks.worldStages("assets/worlds/OldCourt.json", "OldCourt", bp, ".")
			local ruins = #LaneLocks.worldStages("games/SampleGame/assets/worlds/OldRuins.json", "OldRuins", bp, ".")
			LaneLocks.STAGES_RULE_BEFORE["assets/worlds/oldcourt.json"] = nil
			LaneLocks.STAGES_RULE_BEFORE["games/samplegame/assets/worlds/oldruins.json"] = nil
			check.equal(court, 0)
			check.equal(ruins, 0)
		end)

		-- the owner's yes itself: approved as it is, the world passes; changed since, it is asked again. A fixture
		-- project under build/ (git-ignored) and a locks file of its own - never the project's board/locks.json
		test.case("approved as it is, a world passes; changed since, it is asked again", function()
			local root = "build/selftest/worldstages"
			for _, d in { "/assets/worlds/bible", "/build/worlds/look/Fresh.greybox" } do
				if not fs.isDir(root .. d) then
					fs.writeDir(root .. d)
				end
			end
			local bp = { name = "Fresh", scale = "r6", build = { house({ skin = "whole" }) } }
			local function write(path: string, v: any)
				fs.writeFile(root .. path, serde.encode("json", v))
			end
			write("/assets/worlds/Fresh.json", bp)
			write("/assets/worlds/bible/Fresh.json", {
				world = "Fresh",
				stud_m = 0.28,
				scale = "r6",
				regions = {
					{
						name = "Court",
						area = { -40, -40, 40, 40 },
						lamps = "square",
						fixtures = "a well in the middle, benches by the north wall",
					},
				},
				landmarks = { { name = "Tower", pos = { 0, 0, 60 } } },
			})
			write("/build/worlds/Fresh.json", {
				parts = {
					{
						name = "Spawn",
						spawn = true,
						pos = { 0, 0.5, 0 },
						size = { 6, 1, 6 },
						rot = { { 1, 0, 0 }, { 0, 1, 0 }, { 0, 0, 1 } },
					},
				},
			})
			fs.writeFile(root .. "/build/worlds/look/Fresh.greybox/eye_1.png", tostring(os.clock())) -- (new bytes: an empty file written empty again keeps its old time)
			local st = LaneLocks.worldStageState("Fresh", "greybox", root)
			check.is_true(st.ok, tostring(st.why))
			local real = Locks.FILE
			Locks.FILE = root .. "/locks.json"
			local ok, err = pcall(function()
				write("/locks.json", {
					stages = {
						world = {
							Fresh = { greybox = { by = "owner", words = "yes", id = st.id, date = "2026-11-19" } },
						},
					},
				})
				Locks.reset()
				local path = root .. "/assets/worlds/Fresh.json"
				check.equal(table.concat(LaneLocks.worldStages(path, "Fresh", bp, root), "\n"), "")
				-- the blueprint changes and the greybox is made again: another artefact, his yes was for the old one
				bp.build[1].building.floors = 3
				write("/assets/worlds/Fresh.json", bp)
				fs.writeFile(root .. "/build/worlds/look/Fresh.greybox/eye_1.png", tostring(os.clock())) -- (new bytes: an empty file written empty again keeps its old time)
				local lines = LaneLocks.worldStages(path, "Fresh", bp, root)
				check.equal(#lines, 1)
				check.truthy(string.find(lines[1], "changed since the owner approved it", 1, true) ~= nil, lines[1])
			end)
			Locks.FILE = real
			Locks.reset()
			check.is_true(ok, tostring(err))
		end)
	end)
end

-- worldpaint.spec.luau (kit) — a land may hold MORE THAN TEN painted roles (LIMITATIONS_FIXES_V3.md stage E.1).
-- kit world terrain wrote one decimal digit a cell: the compiler refused any other character ("not one digit per
-- cell"), and the snow lock looked a role up by its decimal number (role 11 as "10"). A role is now ONE CHARACTER a
-- cell, string.char(48 + role) - "0".."9" as before, then ":" ";" "<" ... (kit/world/terrain.py paint_encode;
-- the codec and rivers.py: kit/test/python/test_world_paint_roles.py).
local fs = require("@lune/fs")
local luau = require("@lune/luau")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Environment = require("../../lib/environment")
local LaneLocks = require("../../lib/lanelocks")
local World = require("../../lib/world")

local ROLES = { "meadow", "lush", "dirt", "mud", "rock", "cliff", "snow", "sand", "scree", "moss", "gravel", "ash" }
local DIR = "build/selftest/worldpaint"

-- a flat 8 x 8 land whose cells are painted `paint` (one character a cell, row by row of x)
local function land(name: string, roles: { string }, paint: string): string
	if not fs.isDir(DIR) then
		fs.writeDir(DIR)
	end
	local heights = {}
	for _ = 1, 64 do
		table.insert(heights, 0)
	end
	local path = `{DIR}/{name}.hm.json`
	fs.writeFile(
		path,
		serde.encode("json", { nx = 8, nz = 8, step = 4, heights = heights, roles = roles, paint = paint })
	)
	return path
end

local function op(source: string, paint: any?): any
	return {
		heightmap = { center = { 0, 0, 0 }, size = { 28, 28 }, source = source, paint = paint, material = "Grass" },
	}
end

local function errors(list: { any }): string
	local out = ""
	for _, i in list do
		if i.severity == "error" then
			out ..= i.message .. "\n"
		end
	end
	return out
end

return function()
	test.suite("World paint: one character a role", function()
		test.case("paintOff names the first cell that is no role of the land", function()
			check.equal(Environment.paintOff("0123456789", 10), nil)
			check.equal(Environment.paintOff("09:;<", 13), nil) -- (roles 10, 11, 12)
			check.equal(Environment.paintOff("09:;<", 12), 5) -- ("<" is role 12: a land of 12 roles has none)
			check.equal(Environment.paintOff("0/1", 2), 2) -- ("/" is under "0")
			check.equal(Environment.paintOff("", 3), nil)
		end)

		test.case("a land of 13 roles compiles: every cell its own role's material", function()
			local roles = table.clone(ROLES)
			table.insert(roles, "river")
			-- the 8 x 8 cells: x row 1 all "<" (river, role 12), row 2 all ";" (ash), the rest "0" (meadow)
			local paint = string.rep("<", 8) .. string.rep(";", 8) .. string.rep("0", 48)
			local src = land("Thirteen", roles, paint)
			local env, issues = Environment.compile({ name = "T", terrain = { op(src, { ash = "Basalt" }) } })
			check.equal(errors(issues), "")
			local g = (env :: any).terrain[1]
			check.equal(g.kind, "ground")
			local s = g.spec.samples
			check.equal(#s.palette, 13)
			check.equal(s.palette[13], "Water") -- (the river role's default material)
			check.equal(s.palette[12], "Basalt") -- (the op's own map, for the twelfth role)
			-- World.roleAt reads the same character a cell
			check.equal(World.roleAt(g.spec, -14, -14), "river")
			check.equal(World.roleAt(g.spec, -10, -14), "ash")
			check.equal(World.roleAt(g.spec, 14, 14), "meadow")
		end)

		test.case("the game's copy of the paint (ModuleScripts) reads back every role, the backslash too", function()
			-- (role 44 is string.char(92), a backslash: pasted into return "..." it began an escape and shifted every
			-- later cell - the fresh review, 2026-11-18)
			local roles, paint = {}, {}
			for r = 0, 78 do
				table.insert(roles, `role{r}`)
			end
			for k = 1, 64 do
				table.insert(paint, string.char(48 + ((k * 37 + (if k > 40 then 44 else 0)) % 79)))
			end
			paint[64] = "\\" -- (a chunk that ENDS on a backslash would not even load)
			paint[10] = "\\"
			local text = table.concat(paint)
			local src = land("All79", roles, text)
			local model = World.compile({
				name = "T",
				palette = { stone = { material = "Slate", color = { 90, 90, 90 } } },
				build = { { part = { name = "A", size = { 1, 1, 1 }, pos = { 0, 0.5, 0 }, mat = "stone" } } },
				terrain = { op(src) },
			})
			local found = {}
			local function walk(node: any)
				if type(node) ~= "table" then
					return
				end
				if type(node.Name) == "string" and string.sub(node.Name, 1, 15) == "KitTerrainPaint" then
					table.insert(found, node)
				end
				for _, c in node.Children or {} do
					walk(c)
				end
			end
			walk(model)
			check.truthy(#found >= 1)
			table.sort(found, function(a, b)
				return a.Name < b.Name
			end)
			local back = ""
			for _, m in found do
				back ..= (luau.load(m.Properties.Source) :: any)()
			end
			check.equal(back, text)
		end)

		test.case("a character that is no role of the land is an error, as a non-digit was", function()
			local src = land("Short", { "meadow", "lush" }, string.rep("0", 63) .. "2")
			local _, issues = Environment.compile({ name = "T", terrain = { op(src) } })
			check.truthy(string.find(errors(issues), "not one role per cell", 1, true) ~= nil)
		end)

		test.case("the snow lock finds snow painted as the eleventh role", function()
			local roles =
				{ "meadow", "lush", "dirt", "mud", "rock", "cliff", "sand", "scree", "moss", "gravel", "snow" }
			-- snow is role 10 (":"); no cell is "1" followed by "0", so the decimal look-up ("10") found nothing
			local src = land("Snowy", roles, string.rep(":", 8) .. string.rep("2", 56))
			local bp = {
				name = "T",
				build = { { part = { name = "A", size = { 1, 1, 1 }, pos = { 0, 0.5, 0 }, mat = "x" } } },
				terrain = { op(src) },
			}
			check.equal(LaneLocks.unsaidCover(bp), "as written")
			-- and a land with no snow cell is not under snow
			local bare = land("Bare", roles, string.rep("2", 64))
			bp.terrain = { op(bare) }
			check.equal(LaneLocks.unsaidCover(bp), nil)
		end)
	end)
end

-- worldhlod.spec.luau (kit) — THE FAR RANGES AS HLOD PROXIES (LIMITATIONS_FIXES_V3.md stage F.2: "batch far blocks
-- into <= 2k-tri HLOD proxy clusters replacing the cardboard wedges"). A horizon step that names its proxies
-- ("hlod": "<prefix>", four meshes <prefix>_1 .. _4 made by kit world meshes kind "hlod_ring") places them on the
-- ring's centre; its wedges are still built, unseen, as the proxies' stand-ins (the game shows them only while a proxy
-- is not there, as a skin's walls). Held: the four placed, each dressing the step; every wedge unseen and naming the
-- same dress; a missing quarter or one over World.HLOD_TRIS is an error; a step without "hlod" is as it was.
local frk = require("../frk")
local test, check = frk.test, frk.check

local World = require("../../lib/world")

local PALETTE = { rock = { material = "Slate", color = { 70, 72, 80 } } }

local function registry(tris: number, quarters: number): any
	local reg = {}
	for q = 1, quarters do
		reg[`far_{q}`] = {
			kind = "hlod_ring",
			tris = tris,
			-- (a quarter of a 1500-stud ring: from the centre out to its outer foot)
			size = { 1830, 480, 1830 },
			min = if q == 1 or q == 4 then { 0, 0, -1830 } else { -1830, 0, 0 },
			hlod = { quadrant = q, radius = 1500 },
		}
	end
	return reg
end

local function compile(horizon: any, reg: any): ({ any }, { string })
	local _, parts, issues = World.compile({
		name = "T",
		palette = PALETTE,
		build = { { horizon = horizon } },
	}, { meshes = reg })
	local errors = {}
	for _, i in issues do
		if i.severity == "error" and i.path ~= "spawn" then
			table.insert(errors, i.message)
		end
	end
	return parts, errors
end

local RING = { radius = 1500, count = 24, height = { 200, 500 }, mat = "rock", seed = 1 }

return function()
	test.suite("World horizon HLOD proxies", function()
		test.case("the four quarters dress the step; its wedges stand in for them, unseen", function()
			local spec = table.clone(RING)
			spec.hlod = "far"
			local parts, errors = compile(spec, registry(768, 4))
			check.equal(#errors, 0, table.concat(errors, " | "))
			local proxies, wedges, dress = 0, 0, nil
			for _, p in parts do
				local a = p.attributes or {}
				if p.mesh then
					proxies += 1
					check.is_true(p.backdrop == true)
					check.truthy(string.match(p.mesh, "^far_%d$") ~= nil)
					dress = dress or a.KitDress
					check.equal(a.KitDress, dress)
				elseif p.name == "Range" or p.name == "RangeCap" then
					wedges += 1
					check.equal(p.transparency, 1)
					check.truthy(type(a.KitBlockout) == "string")
				end
			end
			check.equal(proxies, 4)
			check.truthy(wedges > 40)
			check.truthy(type(dress) == "string")
			for _, p in parts do
				if p.name == "Range" then
					check.equal((p.attributes or {}).KitBlockout, dress)
				end
			end
		end)

		test.case("a missing quarter, or one over the budget, is said", function()
			local spec = table.clone(RING)
			spec.hlod = "far"
			local _, missing = compile(spec, registry(768, 3))
			check.truthy(string.find(table.concat(missing, " | "), 'no HLOD proxy "far_4"', 1, true) ~= nil)
			local _, heavy = compile(spec, registry(World.HLOD_TRIS + 1, 4))
			check.truthy(string.find(table.concat(heavy, " | "), "triangles", 1, true) ~= nil)
			-- made for another ring (1500) than this horizon's (900), or as the wrong quarter
			local small = table.clone(spec)
			small.radius = 900
			local _, other = compile(small, registry(768, 4))
			check.truthy(string.find(table.concat(other, " | "), "must match", 1, true) ~= nil)
			local swapped = registry(768, 4)
			swapped.far_2.hlod = { quadrant = 1, radius = 1500 }
			local _, wrong = compile(spec, swapped)
			check.truthy(string.find(table.concat(wrong, " | "), "far_2", 1, true) ~= nil)
		end)

		test.case('a horizon without "hlod" is its wedges, seen, as before', function()
			local parts, errors = compile(table.clone(RING), {})
			check.equal(#errors, 0, table.concat(errors, " | "))
			local seen = 0
			for _, p in parts do
				check.equal(p.mesh, nil)
				if p.name == "Range" then
					seen += 1
					check.equal(p.transparency, 0)
				end
			end
			check.truthy(seen > 40)
		end)
	end)
end

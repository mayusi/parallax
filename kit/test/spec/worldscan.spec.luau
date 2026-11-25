-- worldscan.spec.luau (kit) — A REAL THING, PHOTOGRAPHED, SET INTO A WORLD AT ITS REAL SIZE (kit world scan -> a
-- registry entry with "scan"; the owner's method list: "Photo-based environment reconstruction"). Held here: a
-- scanned mesh placed by a mesh step stands at its real height when none is given; a height far from it is refused
-- unless "resize": true; a height near it is taken; a scatter that sets it down far from its size is warned and one
-- near it is not; a mesh that was not scanned is never asked.
-- Not claimed here: that the scan looks like the thing (the audit page says what was seen).
local frk = require("../frk")
local test, check = frk.test, frk.check

local World = require("../../lib/world")

local PALETTE = { stone = { material = "Slate", color = { 90, 88, 86 } } }

-- the urn kit world scan brought in, as the importer writes a scan: an asset of one piece (its one material,
-- "scan"), both in studs and both stamped - 0.9 m tall = 3.214 studs, its foot at y 0
local SCAN = { metres = 0.9, axis = "height" }
local REG = {
	Urn = {
		kind = "import",
		parts = { "Urn__scan" },
		tris = 19000,
		size = { 2.811, 3.214, 2.679 },
		min = { -1.405, 0, -1.34 },
		scan = SCAN,
	},
	Urn__scan = {
		kind = "piece",
		tris = 19000,
		size = { 2.811, 3.214, 2.679 },
		min = { -1.405, 0, -1.34 },
		of = "Urn",
		scan = SCAN,
	},
	Rock = { kind = "mesh", tris = 900, size = { 1, 1, 1 }, min = { -0.5, 0, -0.5 } },
}

local function compile(build: { any }): ({ any }, { string }, { string })
	local bp = {
		name = "T",
		palette = PALETTE,
		terrain = { { ground = { center = { 0, 0, 0 }, size = { 120, 120 }, material = "Grass" } } },
		build = build,
	}
	local _, parts, issues = World.compile(bp, { meshes = REG })
	local errors, warns = {}, {}
	for _, i in issues do
		if i.path ~= "spawn" and i.path ~= "meshes" then
			table.insert(if i.severity == "error" then errors else warns, i.message)
		end
	end
	return parts, errors, warns
end

local function placed(parts: { any }, name: string): { any }
	local out = {}
	for _, p in parts do
		if p.mesh == name or (type(p.mesh) == "string" and string.sub(p.mesh, 1, #name + 2) == name .. "__") then
			table.insert(out, p)
		end
	end
	return out
end

local function times(list: { string }, word: string): number
	local n = 0
	for _, m in list do
		if string.find(m, word, 1, true) then
			n += 1
		end
	end
	return n
end

local function said(list: { string }, word: string): boolean
	return times(list, word) > 0
end

return function()
	test.suite("A scanned real thing keeps its real size", function()
		test.case("a scanned thing with no height stands at its real height", function()
			local parts, errors = compile({ { mesh = { mesh = "Urn", pos = { 4, 0, 6 }, mat = "stone" } } })
			check.equal(#errors, 0)
			local urn = placed(parts, "Urn")
			check.equal(#urn, 1)
			check.truthy(math.abs(urn[1].size[2] - 3.214) < 0.001)
			check.truthy(math.abs(urn[1].pos[2] - 3.214 / 2) < 0.001) -- its foot on the ground
		end)

		test.case("a height far from its size is refused; resize lets it; near it is taken", function()
			for _, h in { 8, 2, 4.1 } do
				local parts, errors =
					compile({ { mesh = { mesh = "Urn", pos = { 0, 0, 0 }, height = h, mat = "stone" } } })
				check.truthy(said(errors, "is a scanned real thing"))
				check.truthy(said(errors, "0.9 m along its height"))
				check.equal(#placed(parts, "Urn"), 0)
			end
			local parts, errors, warns =
				compile({ { mesh = { mesh = "Urn", pos = { 0, 0, 0 }, height = 8, resize = true, mat = "stone" } } })
			check.equal(#errors, 0)
			check.falsy(said(warns, "scanned"))
			check.truthy(math.abs(placed(parts, "Urn")[1].size[2] - 8) < 0.001)
			for _, h in { 3.9, 2.5 } do -- within a quarter of 3.214
				local p2, e2, w2 =
					compile({ { mesh = { mesh = "Urn", pos = { 0, 0, 0 }, height = h, mat = "stone" } } })
				check.equal(#e2, 0)
				check.falsy(said(w2, "scanned"))
				check.truthy(math.abs(placed(p2, "Urn")[1].size[2] - h) < 0.001)
			end
			-- its piece by its own name is held the same (no way round by naming the piece)
			local p3, e3 = compile({ { mesh = { mesh = "Urn__scan", pos = { 0, 0, 0 }, height = 20, mat = "stone" } } })
			check.truthy(said(e3, "is a scanned real thing"))
			check.equal(#placed(p3, "Urn"), 0)
		end)

		test.case("a scatter that sets a scanned thing far from its size is warned once, near it not", function()
			-- scatter sets a mesh 1.4 times its part's height: a part 2.3 tall -> 3.22 (near); 6 tall -> 8.4 (far);
			-- 1 tall -> 1.4 (far, the other way)
			local function scatter(h: number, count: number?)
				return {
					{
						scatter = {
							center = { 0, 0, 0 },
							area = { 40, 40 },
							count = count or 4,
							seed = 3,
							gap = 2,
							meshes = { "Urn" },
							part = { size = { 2, h, 2 }, mat = "stone" },
						},
					},
				}
			end
			local parts, errors, warns = compile(scatter(2.3))
			check.equal(#errors, 0)
			check.truthy(#placed(parts, "Urn") > 0)
			check.falsy(said(warns, "scanned"))
			parts, errors, warns = compile(scatter(6))
			check.equal(#errors, 0)
			check.truthy(said(warns, 'the scanned "Urn" is 3.2 studs tall'))
			parts, errors, warns = compile(scatter(1))
			check.equal(#errors, 0)
			check.truthy(said(warns, "is set 1.4 tall"))
			-- forty copies set too tall: ONE warning that counts them
			parts, errors, warns = compile(scatter(6, 40))
			local n = #placed(parts, "Urn")
			check.truthy(n > 4)
			check.equal(times(warns, 'the scanned "Urn"'), 1)
			check.truthy(said(warns, `in {n} places (the first here)`))
		end)

		test.case("a mesh that was not scanned is never asked", function()
			local parts, errors, warns =
				compile({ { mesh = { mesh = "Rock", pos = { 0, 0, 0 }, height = 40, mat = "stone" } } })
			check.equal(#errors, 0)
			check.falsy(said(warns, "scanned"))
			check.truthy(math.abs(placed(parts, "Rock")[1].size[2] - 40) < 0.001)
		end)
	end)
end

-- craterrefs.spec.luau (kit) — overlapping craters give the ground back only when the last of them heals
-- (src/kit/CraterRefs.luau; the V3 doc, VFX stage B: "craterRefs[cellKey] reference counting"). Before, each heal
-- wrote back the voxels IT read: the older heal filled the newer bowl in, the newer heal left the older bowl for good.
-- The replay runs both rules (the old snapshot and the counted cells) on a fake terrain line of cells.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local CraterRefs = require("../../../src/kit/CraterRefs")

-- a terrain line: cell x -> "ground" / "air"; a crater over cells a..b digs them
local function keysOf(a: number, b: number): { string }
	local out = {}
	for x = a, b do
		table.insert(out, CraterRefs.key(x, 0, 0))
	end
	return out
end

local function cellX(k: string): number
	return tonumber(string.match(k, "^(%-?%d+),")) :: number
end

return function()
	test.suite("CraterRefs", function()
		test.case("two overlapping craters, healed in either order: the ground comes back whole", function()
			for _, order in { { 1, 2 }, { 2, 1 } } do
				local ground: { [number]: string } = {}
				for x = 0, 9 do
					ground[x] = "ground"
				end
				local refs = CraterRefs.new()
				local craters = { keysOf(1, 5), keysOf(4, 8) }
				for _, keys in craters do
					CraterRefs.take(refs, keys, function(k)
						return { material = ground[cellX(k)], occupancy = 1 }
					end)
					for _, k in keys do
						ground[cellX(k)] = "air"
					end
				end
				-- the first heal gives back only what the other crater does not hold
				local first = CraterRefs.give(refs, craters[order[1]])
				for k, cell in first do
					ground[cellX(k)] = cell.material
				end
				for x = 4, 5 do
					check.equal(ground[x], "air") -- the overlap is still the other one's bowl
				end
				local second = CraterRefs.give(refs, craters[order[2]])
				for k, cell in second do
					ground[cellX(k)] = cell.material
				end
				for x = 0, 9 do
					check.equal(ground[x], "ground")
				end
				check.equal(CraterRefs.held(refs), 0)
			end
		end)

		test.case("the OLD rule (each heal writes its own snapshot) leaves a hole: the case this fixes", function()
			local ground: { [number]: string } = {}
			for x = 0, 9 do
				ground[x] = "ground"
			end
			local snaps = {}
			for i, range in { { 1, 5 }, { 4, 8 } } do
				local snap = {}
				for x = range[1], range[2] do
					snap[x] = ground[x]
					ground[x] = "air"
				end
				snaps[i] = snap
			end
			for _, i in { 1, 2 } do -- older first
				for x, m in snaps[i] do
					ground[x] = m
				end
			end
			check.equal(ground[4], "air") -- a bowl left for good after both healed
		end)

		test.case("a permanent crater keeps its cells; a healing one beside it never fills it in", function()
			local refs = CraterRefs.new()
			local read = function(_k)
				return { material = "ground", occupancy = 1 }
			end
			CraterRefs.take(refs, keysOf(0, 3), read) -- permanent: never given back
			local healing = keysOf(2, 6)
			CraterRefs.take(refs, healing, read)
			local back = CraterRefs.give(refs, healing)
			check.is_true(back[CraterRefs.key(2, 0, 0)] == nil and back[CraterRefs.key(3, 0, 0)] == nil)
			check.is_true(back[CraterRefs.key(4, 0, 0)] ~= nil)
			check.equal(CraterRefs.held(refs), 4)
		end)

		test.case("grid: every cell of a read, keyed by its place, with its place in the arrays", function()
			local keys, at = CraterRefs.grid(-2, 0, 5, 2, 1, 3)
			check.equal(#keys, 6)
			check.equal(keys[1], "-2,0,5")
			check.equal(keys[6], "-1,0,7")
			check.equal(at["-1,0,7"][1], 2)
			check.equal(at["-1,0,7"][3], 3)
		end)

		test.case("Crater.blast and the stage's crater layer both count their cells", function()
			local crater = fs.readFile("src/kit/Crater.luau")
			local stage = fs.readFile("src/kit/VfxStage.luau")
			check.is_true(string.find(crater, "CraterRefs.take(refs, keys", 1, true) ~= nil)
			check.is_true(string.find(crater, "CraterRefs.give(refs, keys)", 1, true) ~= nil)
			check.is_true(string.find(crater, "WriteVoxels(region, 4, before[1], before[2])", 1, true) == nil)
			check.is_true(string.find(stage, "CraterRefs.take(craterCells, keys", 1, true) ~= nil)
			check.is_true(string.find(stage, "CraterRefs.give(craterCells, saved.keys)", 1, true) ~= nil)
			check.is_true(string.find(stage, "saved.materials, saved.occupancies", 1, true) == nil)
		end)
	end)
end

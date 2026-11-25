-- vfxhighlight.spec.luau (kit) — the client's Highlight slots (src/kit/VfxHighlight.luau; the V3 doc, VFX stage B:
-- "a priority Highlight allocator"). The engine draws 31 Highlights a client at most; the runtime made one per layer,
-- per impact silhouette and per effect's outlines with no count, so a busy fight lost a fighter's rim to a far
-- spark's outline. The last case reads VfxStage's own source for its use of the slots.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local VfxHighlight = require("../../../src/kit/VfxHighlight")
local HERO, AMBIENT = VfxHighlight.HERO, VfxHighlight.AMBIENT

local function code(path: string): string
	local out = {}
	for line in string.gmatch(fs.readFile(path), "[^\n]+") do
		local cut = string.find(line, "--", 1, true)
		table.insert(out, if cut then string.sub(line, 1, cut - 1) else line)
	end
	return (string.gsub(table.concat(out, " "), "%s+", " "))
end

return function()
	test.suite("VfxHighlight", function()
		test.case("outlines may hold only what the heroes leave: 31 - 24 = 7", function()
			local slots = VfxHighlight.new()
			local granted = 0
			for i = 1, 20 do
				if slots:claim(`outline{i}`, AMBIENT) then
					granted += 1
				end
			end
			check.equal(granted, 7)
			-- a lower claim never takes another's slot
			local ok, lost = slots:claim("one more outline", AMBIENT)
			check.is_true(not ok and lost == nil)
			-- every hero still gets in: 24 of them beside the 7
			for i = 1, 24 do
				local got, took = slots:claim(`hero{i}`, HERO)
				check.is_true(got and took == nil)
			end
			check.equal(slots:count(), 31)
		end)

		test.case("a hero on a FULL client takes the oldest outline's slot and says which", function()
			local slots = VfxHighlight.new(4, 2) -- 4 slots, 2 kept for heroes
			check.is_true((slots:claim("o1", AMBIENT)))
			check.is_true((slots:claim("o2", AMBIENT)))
			check.is_true((slots:claim("h1", HERO)))
			check.is_true((slots:claim("h2", HERO)))
			local ok, lost = slots:claim("h3", HERO)
			check.is_true(ok)
			check.equal(lost, "o1")
			check.is_true(not slots:holds("o1"))
			-- the client full of heroes: the next hero is refused, no hero loses its rim to another
			local _, lost2 = slots:claim("h4", HERO)
			check.equal(lost2, "o2")
			local ok5, lost5 = slots:claim("h5", HERO)
			check.is_true(not ok5 and lost5 == nil)
			check.equal(slots:count(), 4)
		end)

		test.case("release gives the slot back; claiming while holding is a yes", function()
			local slots = VfxHighlight.new(2, 0)
			check.is_true((slots:claim("a", AMBIENT)))
			check.is_true((slots:claim("a", AMBIENT)))
			check.equal(slots:count(), 1)
			check.is_true((slots:claim("b", AMBIENT)))
			check.is_true(not (slots:claim("c", AMBIENT)))
			slots:release("a")
			slots:release("never held") -- nothing happens
			check.is_true((slots:claim("c", AMBIENT)))
		end)

		test.case("VfxStage turns every Highlight on through the slots, and gives each back", function()
			local stage = code("src/kit/VfxStage.luau")
			local function count(s: string): number
				local n, at = 0, 1
				while true do
					local i = string.find(stage, s, at, true)
					if not i then
						return n
					end
					n, at = n + 1, i + #s
				end
			end
			check.equal(count('Instance.new("Highlight")'), 3)
			check.equal(count("h.Enabled = true"), 0) -- none lit outside the slots
			check.is_true(count("lightUp(h, VfxHighlight.HERO, true)") >= 2) -- the aura layer, the impact frame
			check.is_true(count("lightUp(h, VfxHighlight.AMBIENT, true)") >= 1) -- the outlines
			check.is_true(count("highlightSlots:release(h)") >= 4)
		end)
	end)
end

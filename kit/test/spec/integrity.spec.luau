-- integrity.spec.luau (kit) — kit/lib/integrity.luau: the manifest lists only the files the kit installed
-- (writeOnly); an edit to one is "changed"; a file the kit did not install is "added" - except the few the kit writes
-- itself that change nothing it decides (a selftest build's parts sheet, Blender's .blend1). A custom rig is the kit's
-- only when it is named after the rig it holds and claims no shipped rig: a planted file saying "R6" would replace the
-- R6 the motion gates measure with, so it is named; so is a saliency calibration (it feeds a gate). The owner's grading
-- record is not fingerprinted at all.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Config = require("../../lib/config")
local Integrity = require("../../lib/integrity")

local function has(list: { string }, item: string): boolean
	return table.find(list, item) ~= nil
end

return function()
	test.suite("integrity: what the kit installed, and what it did not", function()
		test.case("a planted rig claiming R6 and a saliency calibration are named; a real custom rig is not", function()
			local root = Config.build(`selftest/integrity_spec_{math.floor(os.clock() * 1e6)}`)
			local function put(rel: string, text: string)
				Config.ensureDir(string.match(`{root}/{rel}`, "^(.*)/[^/]+$") :: string)
				fs.writeFile(`{root}/{rel}`, text)
			end
			put("kit/VERSION", "9.9.9\n")
			put("kit/anim/rigs/r6.json", serde.encode("json", { rig = "R6", parts = {} }))
			Integrity.writeOnly(root, { "kit/VERSION", "kit/anim/rigs/r6.json" })
			-- what a project and the kit write afterwards
			put("kit/anim/rigs/dragon.json", serde.encode("json", { rig = "Dragon" })) -- (kit anim rig --from)
			put("kit/anim/rigs/zr6.json", serde.encode("json", { rig = "R6" })) -- (planted: claims the shipped R6)
			put("kit/anim/rigs/wolf.json", serde.encode("json", { rig = "Dragon" })) -- (named after another rig)
			put("kit/ui/saliency_calib.json", "{}")
			put("kit/selftest/blender/_selftest_a.parts.md", "- Body\n")
			put("kit/grades.json", "{}")
			local d = Integrity.check(root) :: any
			fs.removeDir(root)
			check.truthy(d ~= nil)
			check.falsy(has(d.added, "kit/anim/rigs/dragon.json"))
			check.truthy(has(d.added, "kit/anim/rigs/zr6.json"))
			check.truthy(has(d.added, "kit/anim/rigs/wolf.json"))
			check.truthy(has(d.added, "kit/ui/saliency_calib.json"))
			check.falsy(has(d.added, "kit/selftest/blender/_selftest_a.parts.md"))
			check.falsy(has(d.added, "kit/grades.json")) -- (the grading record: never fingerprinted)
			check.equal(#d.changed, 0)
		end)

		test.case("an edit to a shipped rig is a change", function()
			local root = Config.build(`selftest/integrity_spec_edit_{math.floor(os.clock() * 1e6)}`)
			Config.ensureDir(root .. "/kit/anim/rigs")
			fs.writeFile(root .. "/kit/anim/rigs/r6.json", serde.encode("json", { rig = "R6", parts = {} }))
			Integrity.writeOnly(root, { "kit/anim/rigs/r6.json" })
			fs.writeFile(root .. "/kit/anim/rigs/r6.json", serde.encode("json", { rig = "R6", parts = { "Head" } }))
			local d = Integrity.check(root) :: any
			fs.removeDir(root)
			check.truthy(has(d.changed, "kit/anim/rigs/r6.json"))
		end)
	end)
end

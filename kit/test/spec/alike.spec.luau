-- alike.spec.luau (kit) — `kit alike` hands the vision tool the right call (2026-11-08, sprint 4: search by look;
-- the searching itself is tested in kit/test/python/test_alike.py with a stub embedder): index and dupes as they are,
-- a picture or a piece as `near`, a pick round as `round <Move>`, every flag passed on, and no index means no lines.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Alike = require("../../lib/alike")

local function joined(args: { string }, flags: { [string]: any }): string
	return table.concat(Alike.argv(args, flags), " ")
end

return function()
	test.suite("alike: search by look, the call to the vision tool", function()
		test.case("index, dupes, near, round and their flags", function()
			check.equal(joined({ "index" }, { lane = "vfx" }), "kit/vision/run.py alike index --lane vfx")
			check.equal(joined({ "dupes" }, { min = "0.985" }), "kit/vision/run.py alike dupes --min 0.985")
			check.equal(
				joined({ "build/ui/SgLoading.png" }, { lane = "ui", k = "3", as = "SgLoading", cached = true }),
				"kit/vision/run.py alike near build/ui/SgLoading.png --lane ui --k 3 --as SgLoading --cached"
			)
			check.equal(
				joined({ "round", "Roundhouse" }, { round = "4" }),
				"kit/vision/run.py alike round Roundhouse --round 4"
			)
			check.equal(
				joined({ "Roundhouse/r2/c5" }, { refs = true }),
				"kit/vision/run.py alike near Roundhouse/r2/c5 --refs"
			)
		end)

		test.case("no index: no lines, and the pick sheet's look step passes saying how to make one", function()
			local saved = Alike.INDEX
			Alike.INDEX = "kit/selftest/vault/_no_such_look_index.json"
			local ok, err = pcall(function()
				check.equal(Alike.lines("town_barrel", "3d", 3, true), nil)
				local step = Alike.roundStep("Roundhouse", nil)
				check.truthy(step.ok)
				check.truthy(string.find(step.result.summary, "kit alike index", 1, true))
			end)
			Alike.INDEX = saved
			if not ok then
				error(err)
			end
		end)
	end)
end

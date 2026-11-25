-- playtestbudget.spec.luau (kit) — the playtest probe's budget (kit/cmd/qa.luau Qa.budgetLine + kit/qa/harness.luau;
-- the V3 list's scene budget XP-08): kit.config.json's qa.perf becomes ONE harness line carrying the client's game
-- memory, the Highlight ceiling (the engine draws 31) and the shadow lights near the camera; a key a project leaves out
-- takes the kit's default; and the bundled smoke playtest still compiles with the new checks in it.
local luau = require("@lune/luau")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Qa = require("../../cmd/qa")

return function()
	test.suite("playtest budget: the scene ceilings a client can read", function()
		test.case("every key, and the kit's default for one left out", function()
			local line = Qa.budgetLine({ memoryMb = 900, instances = 1000, heartbeatMs = 16 })
			check.equal(
				line,
				"local BUDGET = { memoryMb = 900, instances = 1000, frameMs = 16, clientMemoryMb = 1100, "
					.. "highlights = 31, shadowLights = 16, shadowRadius = 120 }"
			)
			local own = Qa.budgetLine({ highlights = 20, shadowLights = 8, clientMemoryMb = 450 })
			check.truthy(string.find(own, "clientMemoryMb = 450, highlights = 20, shadowLights = 8", 1, true) ~= nil)
		end)
		test.case("the bundled smoke playtest carries the checks and compiles", function()
			local src, side, err = Qa.bundle("smoke")
			check.equal(err, nil)
			check.truthy(side == "Server" or side == "Client")
			check.truthy(string.find(src :: string, "\nlocal BUDGET = { memoryMb = ", 1, true) ~= nil)
			check.truthy(string.find(src :: string, "@kit:budget", 1, true) == nil) -- (the tagged line was swapped)
			for _, said in { "perf: Highlights on", "perf: shadow lights within", "perf: client game memory" } do
				check.truthy(string.find(src :: string, said, 1, true) ~= nil)
			end
			local ok, why = pcall(luau.compile, src :: string)
			check.truthy(ok, tostring(why))
		end)
	end)
end

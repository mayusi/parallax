-- loader.spec.luau — the game skeleton's pure parts: Loader.order (dependency order, unknown deps, cycles) and
-- Configs.coerce (a live value of the wrong type / non-finite / negative falls back to the code's value).
local frk = require("../frk")
local test, check = frk.test, frk.check

local Configs = require("../../../src/kit/Configs")
local Loader = require("../../../src/kit/Loader")

return function()
	test.suite("Loader.order", function()
		test.case("dependencies first, deterministic otherwise", function()
			local order = Loader.order({
				{ name = "CombatService", deps = { "DataService", "MatchService" } },
				{ name = "MatchService", deps = { "DataService" } },
				{ name = "DataService", deps = {} },
				{ name = "ShopService", deps = { "DataService" } },
			}) :: { string }
			check.equal(order[1], "DataService")
			check.is_true(
				(table.find(order, "MatchService") :: number) < (table.find(order, "CombatService") :: number)
			)
			check.equal(#order, 4)
		end)
		test.case("an unknown dependency is named", function()
			local order, err = Loader.order({ { name = "A", deps = { "Nope" } } })
			check.equal(order, nil)
			check.is_true(err ~= nil and string.find(err, '"Nope"', 1, true) ~= nil)
		end)
		test.case("a cycle is named in full", function()
			local _, err = Loader.order({
				{ name = "A", deps = { "B" } },
				{ name = "B", deps = { "C" } },
				{ name = "C", deps = { "A" } },
			})
			check.is_true(err ~= nil and string.find(err, "A -> B -> C -> A", 1, true) ~= nil)
		end)
	end)

	test.suite("Configs.coerce", function()
		test.case("a good live value wins; nil keeps the default", function()
			check.equal((Configs.coerce(10, 14)), 14)
			check.equal((Configs.coerce(10, nil)), 10)
			check.equal((Configs.coerce("easy", "hard")), "hard")
		end)
		test.case("wrong type, NaN, inf and a negative cooldown fall back with a reason", function()
			local v, why = Configs.coerce(10, "14")
			check.equal(v, 10)
			check.is_true(why ~= nil)
			check.equal((Configs.coerce(0.5, 0 / 0)), 0.5)
			check.equal((Configs.coerce(0.5, math.huge)), 0.5)
			check.equal((Configs.coerce(0.5, -1)), 0.5)
			check.equal((Configs.coerce(-3, -1)), -1)
		end)
	end)
end

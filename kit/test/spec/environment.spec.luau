-- environment.spec.luau — world lighting + terrain are validated at compile (applied at runtime by the kit).
local frk = require("../frk")
local test, check = frk.test, frk.check

local Environment = require("../../lib/environment")

return function()
	test.suite("Environment.compile", function()
		test.case("a preset name expands to full lighting; overrides win", function()
			local env = Environment.compile({ lighting = { preset = "storm", clockTime = 15 } })
			check.equal(env.lighting.clockTime, 15)
			check.equal(env.lighting.atmosphere.haze, Environment.LIGHTING.storm.atmosphere.haze)
		end)
		test.case("unknown presets, materials and ops are errors", function()
			local _, issues = Environment.compile({
				lighting = "sunny",
				terrain = {
					{ ground = { center = { 0, 0, 0 }, size = { 100, 100 }, material = "Lava" } },
					{ spiral = {} },
				},
			})
			local text = {}
			for _, i in issues do
				table.insert(text, i.message)
			end
			local all = table.concat(text, "\n")
			check.is_true(string.find(all, "unknown preset", 1, true) ~= nil)
			check.is_true(string.find(all, "terrain material", 1, true) ~= nil)
			check.is_true(string.find(all, "unknown terrain op", 1, true) ~= nil)
		end)
		test.case("a world with neither stays nil (nothing to apply)", function()
			local env, issues = Environment.compile({})
			check.equal(env, nil)
			check.equal(#issues, 0)
		end)
	end)
end

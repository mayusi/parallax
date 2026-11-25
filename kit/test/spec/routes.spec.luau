-- routes.spec.luau (kit) — the stage shortlists (kit/knowledge/routes.json): every department has stages, every
-- stage has a gate and at most Routes.MAX commands (mission 00 5.4: a model picks the right tool from a shortlist,
-- never from the wall), and `kit help --stage` lines carry the gate.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Routes = require("../../lib/routes")

return function()
	test.suite("routes: the stage shortlists", function()
		test.case("every department has at least one stage", function()
			local depts = Routes.depts()
			check.truthy(#depts >= 8)
			for _, d in depts do
				check.truthy(#Routes.stages(d) >= 1)
			end
		end)
		test.case("every stage has a gate and at most five commands", function()
			for _, d in Routes.depts() do
				for _, name in Routes.stages(d) do
					local s = Routes.stage(d, name)
					check.truthy(s ~= nil)
					if s then
						check.truthy(#s.commands >= 1)
						check.truthy(#s.commands <= Routes.MAX)
						check.truthy(s.gate ~= "")
					end
				end
			end
		end)
		test.case("the printed lines name the gate and never exceed the cap", function()
			local lines = Routes.lines("3d", Routes.stages("3d")[1])
			local text = table.concat(lines, "\n")
			check.truthy(string.find(text, "gate:", 1, true))
			local commands = 0
			for _, l in lines do
				-- the "next stage:" pointer is not one of the stage's commands
				if string.find(l, "lune run kit", 1, true) and not string.find(l, "next stage:", 1, true) then
					commands += 1
				end
			end
			check.truthy(commands >= 1 and commands <= Routes.MAX)
		end)
	end)
end

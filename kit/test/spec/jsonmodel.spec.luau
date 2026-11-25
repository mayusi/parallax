-- jsonmodel.spec.luau — generated models with fractions must not look stale (regression: the "serde drift" bug
-- that kept kit verify red in real projects: pretty file vs compact encoding rounded floats differently).
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local JsonModel = require("../../lib/jsonmodel")

return function()
	test.suite("JsonModel.same", function()
		test.case("a model with awkward floats matches the file it wrote", function()
			local model = {
				ClassName = "Frame",
				Properties = { BackgroundColor3 = { Color3 = { 0.4980392156862745, 231 / 255, 1 } } },
				Children = { { Name = "Ring", Properties = { X = 28.0737202661892, Y = math.sin(1.1) } } },
			}
			local written = serde.encode("json", model, true) .. "\n"
			check.is_true(JsonModel.same(written, model))
		end)
		test.case("a real change is still caught", function()
			local model = { Properties = { Size = 10 } }
			local written = serde.encode("json", model, true)
			model.Properties.Size = 11
			check.is_false(JsonModel.same(written, model))
		end)
	end)
end

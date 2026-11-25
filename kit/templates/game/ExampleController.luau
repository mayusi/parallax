-- ExampleController — the shape every __NAME__ controller follows: input in, feedback out, never an outcome.
local ExampleController = { deps = {} }

function ExampleController.start(_self)
	print("[ExampleController] client ready")
end

return ExampleController

-- __NAME__Client — the ONE client entry point of __NAME__: every controller is a ModuleScript in __NAME__Controllers
-- (same lifecycle as the services: deps / init / start). Controllers gather input and show feedback; they never
-- decide outcomes (the server does).
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Loader = require(ReplicatedStorage:WaitForChild("kit"):WaitForChild("Loader"))

Loader.run(script.Parent:WaitForChild("__NAME__Controllers"))

-- __NAME__Server — the ONE server entry point of __NAME__. Every service is a ModuleScript in __NAME__Services:
--   return { deps = { "DataService" }, init = function(self, services) end, start = function(self, services) end }
-- The kit Loader inits them in dependency order, then starts each in its own thread; errors name the service.
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Loader = require(ReplicatedStorage:WaitForChild("kit"):WaitForChild("Loader"))

Loader.run(script.Parent:WaitForChild("__NAME__Services"))
print("[__NAME__] server services online")

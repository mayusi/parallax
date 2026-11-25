-- ExampleService — the shape every __NAME__ service follows: declare deps, read tunables LIVE through Configs
-- (__NAME__Config holds the defaults; the Experience Configs dashboard can change them without a republish),
-- act on the server. Replace it with real services (kit new system <Name> gives the Rules + spec + remotes).
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Configs = require(ReplicatedStorage:WaitForChild("kit"):WaitForChild("Configs"))
local __NAME__Config = require(ReplicatedStorage:WaitForChild("Shared"):WaitForChild("__NAME__Config"))

local Tun = Configs.bind("__NAME__", __NAME__Config)

local ExampleService = { deps = { "DataService" } }

function ExampleService.start(_self, services: any)
	services.DataService.loaded:Connect(function(player: Player, data: { [string]: any })
		data.Coins = (data.Coins or 0) + Tun.STARTING_COINS
		print(`[ExampleService] {player.Name} has {data.Coins} coins (STARTING_COINS = {Tun.STARTING_COINS})`)
	end)
end

return ExampleService

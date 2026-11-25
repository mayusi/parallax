-- DataService — player data for __NAME__. With ProfileStore installed (`lune run kit add profilestore`: session-
-- locked saves, no lost or duplicated items) it saves for real; without it (a fresh project, a quick Studio test)
-- data lives in memory for the session and says so ONCE. Never write raw DataStore code beside it.
--   services.DataService.get(player) -> the player's data table (nil until loaded)
--   services.DataService.loaded:Connect(function(player, data) end)
local Players = game:GetService("Players")
local ServerScriptService = game:GetService("ServerScriptService")

local TEMPLATE = {
	Coins = 0,
}

local DataService = { deps = {} }

local store: any = nil
local profiles: { [Player]: any } = {}
local memory: { [Player]: { [string]: any } } = {}
local loadedEvent = Instance.new("BindableEvent")
DataService.loaded = loadedEvent.Event

function DataService.init(_self)
	local packages = ServerScriptService:FindFirstChild("ServerPackages")
	local module = packages and packages:FindFirstChild("ProfileStore")
	if module and module:IsA("ModuleScript") then
		local ProfileStore: any = require(module) :: any
		store = ProfileStore.New("__NAME__Data", TEMPLATE)
	else
		warn("[DataService] ProfileStore not installed: data is in MEMORY only (run: lune run kit add profilestore)")
	end
end

local function load(player: Player)
	if store then
		local profile = store:StartSessionAsync(`{player.UserId}`, {
			Cancel = function()
				return player.Parent ~= Players
			end,
		})
		if not profile then
			player:Kick("Your data could not be loaded — please rejoin.")
			return
		end
		profile:AddUserId(player.UserId)
		profile:Reconcile()
		profile.OnSessionEnd:Connect(function()
			profiles[player] = nil
			player:Kick("Your data session ended (joined elsewhere?) — please rejoin.")
		end)
		if player.Parent ~= Players then
			profile:EndSession()
			return
		end
		profiles[player] = profile
		loadedEvent:Fire(player, profile.Data)
	else
		memory[player] = table.clone(TEMPLATE)
		loadedEvent:Fire(player, memory[player])
	end
end

function DataService.get(player: Player): { [string]: any }?
	local profile = profiles[player]
	if profile then
		return profile.Data
	end
	return memory[player]
end

function DataService.start(_self)
	Players.PlayerAdded:Connect(load)
	for _, p in Players:GetPlayers() do
		task.spawn(load, p)
	end
	Players.PlayerRemoving:Connect(function(player: Player)
		local profile = profiles[player]
		if profile then
			profile:EndSession()
		end
		profiles[player] = nil
		memory[player] = nil
	end)
end

return DataService

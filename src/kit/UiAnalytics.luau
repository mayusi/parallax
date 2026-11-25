--!strict
-- UiAnalytics.luau — which step of a menu FLOW players reach (v7.12: a shop, a tutorial, a first-time path): real
-- players are the usability test. AnalyticsService only logs from the SERVER, so the client asks through one
-- RemoteEvent the server rate-limits and validates (every argument, against the funnels the server declared).
--
--   server:  UiAnalytics.start({ Shop = { "open", "tab", "item", "buy" }, Tutorial = { "move", "jump", "shop" } })
--   client:  Ui.funnel("Shop", 2)   -- (Ui requires nothing new: it fires the remote when the server made it)
--
-- Roblox allows 10 funnels per experience; a funnel's session id is fresh each time a player starts it (step 1).
local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Guard = require(script.Parent.Guard)
local RateLimit = require(script.Parent.RateLimit)

local UiAnalytics = {}

function UiAnalytics.start(funnels: { [string]: { string } })
	local names: { string } = {}
	for name, steps in funnels do
		assert(#steps >= 1, `UiAnalytics: funnel {name} has no steps`)
		table.insert(names, name)
	end
	assert(#names <= 10, "UiAnalytics: Roblox allows 10 funnels per experience")
	local remote = Instance.new("RemoteEvent")
	remote.Name = "KitUiFunnel"
	remote.Parent = ReplicatedStorage
	local limit = RateLimit.new(6, 2) -- (a burst of 6 steps, then 2 a second per player)
	local sessions: { [Player]: { [string]: string } } = {}
	Players.PlayerRemoving:Connect(function(p)
		sessions[p] = nil
		limit:forget(p.UserId)
	end)
	remote.OnServerEvent:Connect(function(player: Player, rawName: unknown, rawStep: unknown)
		if not limit:take(player.UserId, os.clock()) then
			return
		end
		local okName, name = Guard.oneOf(rawName, names)
		if not okName then
			return
		end
		local steps = funnels[name]
		local okStep, step = Guard.integer(rawStep, 1, #steps)
		if not okStep then
			return
		end
		local mine = sessions[player] or {}
		sessions[player] = mine
		if step == 1 or mine[name] == nil then
			mine[name] = HttpService:GenerateGUID(false)
		end
		pcall(function()
			game:GetService("AnalyticsService"):LogFunnelStepEvent(player, name, mine[name], step, steps[step])
		end)
	end)
	return remote
end

return UiAnalytics

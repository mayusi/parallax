-- __NAME__Service.server.luau — server authority for __NAME__. The client only ASKS; this decides.
-- Order for every request: enabled -> rate limit -> type-check every arg -> rules -> act -> reply.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Kit = ReplicatedStorage:WaitForChild("kit")
local Guard = require(Kit:WaitForChild("Guard"))
local RateLimit = require(Kit:WaitForChild("RateLimit"))
local Vfx = require(Kit:WaitForChild("Vfx"))
local __NAME__Config = require(Shared:WaitForChild("__NAME__Config"))
local __NAME__Rules = require(Shared:WaitForChild("__NAME__Rules"))

local function remote(name: string): RemoteEvent
	local existing = ReplicatedStorage:FindFirstChild(name)
	if existing and existing:IsA("RemoteEvent") then
		return existing
	end
	local created = Instance.new("RemoteEvent")
	created.Name = name
	created.Parent = ReplicatedStorage
	return created
end

local request = remote(__NAME__Config.REQUEST)
local reply = remote(__NAME__Config.REPLY)
local limit = RateLimit.new(__NAME__Config.BURST, __NAME__Config.REFILL_PER_SECOND)

request.OnServerEvent:Connect(function(player: Player, rawTarget: unknown, rawPower: unknown)
	if not __NAME__Config.ENABLED then
		return
	end
	if not limit:take(player.UserId, os.clock()) then
		reply:FireClient(player, false, "slow down")
		return
	end
	local okTarget, target = Guard.vector3(rawTarget)
	if not okTarget then
		return -- malformed packet: ignore silently, never echo exploit input back
	end
	local character = player.Character
	local root = character and character:FindFirstChild("HumanoidRootPart")
	if not root or not root:IsA("BasePart") then
		return
	end
	local ok, reason = __NAME__Rules.check(rawPower, (target - root.Position).Magnitude)
	if not ok then
		reply:FireClient(player, false, reason)
		return
	end

	-- The actual effect goes here. The server decides damage, currency, unlocks — never the client.
	Vfx.broadcast(__NAME__Config.VFX, target, 1)
	reply:FireClient(player, true, "ok")
end)

Players.PlayerRemoving:Connect(function(player: Player)
	limit:forget(player.UserId)
end)

print("[__NAME__] service online")

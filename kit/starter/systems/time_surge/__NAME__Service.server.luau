-- __NAME__Service.server.luau — server authority for __NAME__. The client only ASKS to activate; the server
-- checks the cooldown, applies the speed boost, and publishes the state as a player attribute so EVERY client
-- (including players who join mid-activation) renders the afterimages.
-- Order for every request: enabled -> rate limit -> (no args to validate) -> rules -> act -> publish.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Kit = ReplicatedStorage:WaitForChild("kit")
local RateLimit = require(Kit:WaitForChild("RateLimit"))
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
local limit = RateLimit.new(__NAME__Config.BURST, __NAME__Config.REFILL_PER_SECOND)
local states: { [Player]: __NAME__Rules.State } = {}
-- the boost we ADDED, on which humanoid: removed as a difference so other speed systems (slows, sprints, stuns)
-- that change WalkSpeed meanwhile keep their effect
local boosts: { [Player]: { humanoid: Humanoid, amount: number } } = {}

local function setActive(player: Player, active: boolean)
	player:SetAttribute(__NAME__Config.ATTRIBUTE, active)
end

local function removeBoost(player: Player)
	local b = boosts[player]
	boosts[player] = nil
	if b and b.humanoid.Parent then
		b.humanoid.WalkSpeed = math.max(0, b.humanoid.WalkSpeed - b.amount)
	end
end

local function finish(player: Player, startedAt: number)
	local state = states[player]
	-- only end THIS activation (a respawn or a newer activation may have replaced it)
	if not state or state.activeUntil ~= startedAt + __NAME__Config.DURATION then
		return
	end
	removeBoost(player)
	setActive(player, false)
end

request.OnServerEvent:Connect(function(player: Player)
	if not __NAME__Config.ENABLED then
		return
	end
	if not limit:take(player.UserId, os.clock()) then
		return
	end
	local character = player.Character
	local humanoid = character and character:FindFirstChildOfClass("Humanoid")
	if not humanoid or humanoid.Health <= 0 then
		return
	end
	local now = os.clock()
	local state = states[player] or __NAME__Rules.new()
	if not __NAME__Rules.canActivate(state, now) then
		return
	end
	states[player] = __NAME__Rules.activate(state, now)
	local amount = __NAME__Rules.boost(humanoid.WalkSpeed)
	humanoid.WalkSpeed += amount
	boosts[player] = { humanoid = humanoid, amount = amount }
	setActive(player, true)
	task.delay(__NAME__Config.DURATION, finish, player, now)
end)

local function watch(player: Player)
	setActive(player, false)
	player.CharacterAdded:Connect(function()
		-- a new character starts at its normal speed; any running mode ends (the cooldown is kept)
		local state = states[player]
		if state and __NAME__Rules.isActive(state, os.clock()) then
			state.activeUntil = os.clock()
		end
		boosts[player] = nil -- the old humanoid is gone with its boost
		setActive(player, false)
	end)
end

Players.PlayerAdded:Connect(watch)
for _, player in Players:GetPlayers() do
	watch(player)
end
Players.PlayerRemoving:Connect(function(player: Player)
	states[player] = nil
	boosts[player] = nil
	limit:forget(player.UserId)
end)

print("[__NAME__] service online")

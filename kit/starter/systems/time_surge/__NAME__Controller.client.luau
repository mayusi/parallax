-- __NAME__Controller.client.luau — input + visuals for __NAME__. Cosmetic only: it ASKS the server.
-- Everyone: while a player's attribute is on, the VFX preset rides their root (afterimages; the preset's grade is
-- "owner"-only, so only that player's screen changes). Owner only: other characters' animations slow down on
-- this screen (including ones that start during the mode), then go back to the speed they had.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Kit = ReplicatedStorage:WaitForChild("kit")
local Assets = require(Kit:WaitForChild("Assets"))
local Vfx = require(Kit:WaitForChild("Vfx"))
local __NAME__Config = require(Shared:WaitForChild("__NAME__Config"))

local player = Players.LocalPlayer
local request = ReplicatedStorage:WaitForChild(__NAME__Config.REQUEST) :: RemoteEvent
local key = (Enum.KeyCode :: any)[__NAME__Config.KEY]

local stops: { [Player]: () -> () } = {}

UserInputService.InputBegan:Connect(function(input: InputObject, processed: boolean)
	if processed or not __NAME__Config.ENABLED or input.KeyCode ~= key then
		return
	end
	request:FireServer()
end)

-- ---------------------------------------------------------------- the slowed world (owner's screen only)
local original: { [AnimationTrack]: number } = {} -- track -> the speed it had before we slowed it
local hooks: { RBXScriptConnection } = {}

local function slowTrack(track: AnimationTrack)
	if original[track] == nil then
		original[track] = track.Speed
		pcall(track.AdjustSpeed, track, track.Speed * __NAME__Config.WORLD_SLOW)
	end
end

local function slowCharacter(character: Model)
	local humanoid = character:FindFirstChildOfClass("Humanoid")
	local animator = humanoid and humanoid:FindFirstChildOfClass("Animator")
	if not animator then
		return
	end
	for _, track in animator:GetPlayingAnimationTracks() do
		slowTrack(track)
	end
	table.insert(hooks, animator.AnimationPlayed:Connect(slowTrack))
end

local function slowWorld(on: boolean)
	for _, c in hooks do
		c:Disconnect()
	end
	table.clear(hooks)
	if on then
		for _, other in Players:GetPlayers() do
			if other ~= player and other.Character then
				slowCharacter(other.Character)
			end
			if other ~= player then
				table.insert(hooks, other.CharacterAdded:Connect(slowCharacter))
			end
		end
	else
		for track, speed in original do
			pcall(track.AdjustSpeed, track, speed) -- the track may have ended or its owner left
		end
		table.clear(original)
	end
end

-- ---------------------------------------------------------------- state from the server (an attribute per player)
local function apply(who: Player)
	local active = who:GetAttribute(__NAME__Config.ATTRIBUTE) == true
	if stops[who] then
		stops[who]()
		stops[who] = nil
	end
	local root = who.Character and who.Character:FindFirstChild("HumanoidRootPart")
	if active and root and root:IsA("BasePart") then
		stops[who] = Vfx.attach(__NAME__Config.VFX, root)
		Assets.play(__NAME__Config.SOUND_ON, root.Position)
	end
	if who == player then
		slowWorld(active)
	end
end

local function watch(who: Player)
	who:GetAttributeChangedSignal(__NAME__Config.ATTRIBUTE):Connect(function()
		apply(who)
	end)
	if who:GetAttribute(__NAME__Config.ATTRIBUTE) == true then
		apply(who) -- joined while it was already running
	end
end

Players.PlayerAdded:Connect(watch)
for _, who in Players:GetPlayers() do
	watch(who)
end
Players.PlayerRemoving:Connect(function(who: Player)
	if stops[who] then
		stops[who]()
		stops[who] = nil
	end
end)

-- AnimRoot.client.luau (kit) — ROOT MOTION for the local player's character: one-shots with a root track (a dash, a
-- lunge, a roll) move the character along it, whoever started the clip (Moves plays player moves on the SERVER, but
-- the client owns the body). Nothing to call; see ReplicatedStorage.kit.Anim (Anim.watchRootMotion).
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Anim = require(ReplicatedStorage:WaitForChild("kit"):WaitForChild("Anim"))

local player = Players.LocalPlayer
local conn: RBXScriptConnection? = nil

local function bind(character: Model)
	if conn then
		conn:Disconnect()
	end
	conn = Anim.watchRootMotion(character)
end

if player.Character then
	task.spawn(bind, player.Character)
end
player.CharacterAdded:Connect(bind)

-- GHOSTS + SMEARS (AAA gaps v2 B6 / D12): this client draws them for EVERY player's character (drawn on the server
-- they arrived late and behind the arm)
-- GET-UPS (2026-11-14): a knocked-down player's limbs ease back from where the ragdoll left them, on this client (a
-- joint's pose does not travel between machines: the server's own blend is seen by nobody)
local ragdoll = ReplicatedStorage:WaitForChild("kit"):FindFirstChild("AnimRagdoll")
local Ragdoll = if ragdoll and ragdoll:IsA("ModuleScript") then require(ragdoll) :: any else nil

-- SECONDARY MOTION (2026-11-14): accessories sway on a spring, when the game asked for it (KitSecondary on the kit folder)
local kitFolder = ReplicatedStorage:WaitForChild("kit")
local secondary = kitFolder:FindFirstChild("AnimSecondary")
local Secondary = if secondary and secondary:IsA("ModuleScript") then require(secondary) :: any else nil

-- THE LAYERS' LIFECYCLE (2026-11-15, the owner's limitations list A-R01; the rule: kit.AnimLife, spec'd): every layer
-- this client runs for a character is one of a kind, stopped when the character is gone (a respawn, a leave, a
-- death), stood down while a ragdoll or a knockdown has the body, and brought back after.
-- WHAT THE GAME TURNS ON (attributes on ReplicatedStorage.kit, read when a character appears):
--   KitSecondary = true            accessories sway on a spring (kit.AnimSecondary)
--   KitFeet = true                 every character's feet meet the ground they are over (Anim.feet; with many
--                                  characters each is also tracked by kit.AnimCrowd: far ones are placed less often)
--   KitFeetTilt = degrees          ... and the pelvis may lean with the ground by that much
-- and on a CHARACTER:  KitMotionSet = "<Set>"   that character plays the motion set (Anim.motion) on the machine
--                                  that owns its body; the local player's own is steered by where the player pushes
-- A character that is not a player's (an NPC) gets the same layers when the game tags it "KitCharacter".
-- KitFeet / KitSecondary are read when a character appears: changed later, they take effect at its next spawn.
-- Written, never seen to move (Studio): see kit.AnimLife.
local AnimLife = require(kitFolder:WaitForChild("AnimLife"))
local crowdModule = kitFolder:FindFirstChild("AnimCrowd")
local Crowd = if crowdModule and crowdModule:IsA("ModuleScript") then require(crowdModule) :: any else nil
local life = AnimLife.new()

local CollectionService = game:GetService("CollectionService")
local watched: { [Model]: boolean } = setmetatable({}, { __mode = "k" }) :: any

local function effects(character: Model)
	if watched[character] then
		return -- (seen twice - Character set and CharacterAdded: one set of layers, one set of connections)
	end
	watched[character] = true
	-- THE END IS HOOKED FIRST (everything below may wait: a character destroyed meanwhile must still be let go)
	local gone = false
	local conns: { RBXScriptConnection } = {}
	local function over()
		if gone then
			return
		end
		gone = true
		for _, c in conns do
			c:Disconnect()
		end
		life:clear(character)
	end
	character.Destroying:Once(over)
	-- (out of the world but not destroyed - streamed out, hidden by the game: stood down, not forgotten)
	table.insert(
		conns,
		character.AncestryChanged:Connect(function()
			if character:IsDescendantOf(workspace) then
				life:resume(character, "out")
			else
				life:suspend(character, "out")
			end
		end)
	)
	-- the body's parts first: a layer started on a body without them does nothing for that whole life
	local hum = character:FindFirstChildOfClass("Humanoid") or character:WaitForChild("Humanoid", 10)
	local rootPart = character:FindFirstChild("HumanoidRootPart") or character:WaitForChild("HumanoidRootPart", 10)
	if gone or not hum or not hum:IsA("Humanoid") or not rootPart then
		return
	end
	if not character:IsDescendantOf(workspace) then
		life:suspend(character, "out")
	end
	-- INTERRUPTION: a ragdoll, a knockdown, the get-up after it or death takes the body from the animation. Two
	-- signs, because a state does not reach every machine: the Humanoid's state (the machine that owns the body) and
	-- its PlatformStand (a property: it is set by kit.AnimRagdoll.knock on the server and reaches every client)
	table.insert(
		conns,
		hum.StateChanged:Connect(function(_, new)
			if AnimLife.isDown(new.Name) then
				life:suspend(character, "down")
			else
				life:resume(character, "down")
			end
		end)
	)
	local function platform()
		if hum.PlatformStand then
			life:suspend(character, "platform")
		else
			-- (the get-up blend eases the limbs back for KitGetUpBlend seconds: the layers come back after it)
			local blend = character:GetAttribute("KitGetUpBlend")
			task.delay(if type(blend) == "number" and blend > 0 then blend else 0.3, function()
				if not gone and not hum.PlatformStand then
					life:resume(character, "platform")
				end
			end)
		end
	end
	table.insert(conns, hum:GetPropertyChangedSignal("PlatformStand"):Connect(platform))
	if AnimLife.isDown(hum:GetState().Name) then
		life:suspend(character, "down")
	end
	if hum.PlatformStand then
		life:suspend(character, "platform")
	end
	if Secondary and kitFolder:GetAttribute("KitSecondary") == true then
		life:start(character, "secondary", function()
			return Secondary.attach(character, {
				stiffness = kitFolder:GetAttribute("KitSecondaryStiffness"),
				damping = kitFolder:GetAttribute("KitSecondaryDamping"),
				gain = kitFolder:GetAttribute("KitSecondaryGain"),
				max = kitFolder:GetAttribute("KitSecondaryMax"),
			})
		end)
	end
	if Ragdoll then
		life:start(character, "getup", function()
			return Ragdoll.watch(character)
		end)
	end
	-- FOOT PLACEMENT, on every client for every character it shows: stood down while a ragdoll has the body
	if kitFolder:GetAttribute("KitFeet") == true then
		life:start(character, "feet", function()
			if Crowd then
				Crowd.track(character)
			end
			local tilt = kitFolder:GetAttribute("KitFeetTilt")
			local stop = Anim.feet(character, { limits = { tilt = if type(tilt) == "number" then tilt else nil } })
			return function()
				stop()
				if Crowd then
					Crowd.untrack(character)
				end
			end
		end, { suspends = true })
	end
	-- ADDITIVE LAYERS THE SERVER STARTED (V4 4.4 / 13.4.3, card txjy): a flinch or a breath laid over the clip is a
	-- joint pose, and joint poses do not travel - the server writes a cue on the character, every client plays it.
	-- (Not stood down for a ragdoll: it only listens - a cue missed while stood down would be lost - and a layer on
	-- a ragdolled body writes to motors the ragdoll has switched off)
	if Anim.watchAdditive then
		life:start(character, "additive", function()
			return Anim.watchAdditive(character)
		end)
	end
	-- A MOTION SET, only on the machine that OWNS the body (its tracks travel to the others by themselves: played
	-- here too, an observer would run a second copy against the first). The local player's own character, or a
	-- character this client made (not a player's: an NPC shown only here)
	local mine = character == player.Character or Players:GetPlayerFromCharacter(character) == nil
	local function motion()
		local set = character:GetAttribute("KitMotionSet")
		if mine and type(set) == "string" and set ~= "" then
			life:start(character, "motion", function()
				return Anim.motion(hum, set, { steer = if character == player.Character then true else nil })
			end, { suspends = true })
		else
			life:stop(character, "motion")
		end
	end
	motion()
	table.insert(conns, character:GetAttributeChangedSignal("KitMotionSet"):Connect(motion))
	-- (LAST: it may wait many seconds for the game's effect folders)
	life:start(character, "effects", function()
		local c = Anim.watchEffects(character)
		return if c
			then function()
				c:Disconnect()
			end
			else nil
	end)
end
local function watchPlayer(p: Player)
	if p.Character then
		task.spawn(effects, p.Character)
	end
	p.CharacterAdded:Connect(effects)
	p.CharacterRemoving:Connect(function(character)
		life:clear(character)
	end)
end
for _, p in Players:GetPlayers() do
	watchPlayer(p)
end
Players.PlayerAdded:Connect(watchPlayer)
-- CHARACTERS THAT ARE NOT PLAYERS' (an NPC, a crowd): the game tags them "KitCharacter" and they get the same layers
for _, npc in CollectionService:GetTagged("KitCharacter") do
	if npc:IsA("Model") then
		task.spawn(effects, npc)
	end
end
CollectionService:GetInstanceAddedSignal("KitCharacter"):Connect(function(npc)
	if npc:IsA("Model") then
		effects(npc)
	end
end)

-- GAME CUTSCENES (2026-10-24): every cutscene the server broadcasts (Cutscene.broadcast) plays here as a viewer - the
-- camera and the cinema bars, joined where it is - with nothing for the game to wire
local cutscene = ReplicatedStorage:WaitForChild("kit"):FindFirstChild("Cutscene")
if cutscene and cutscene:IsA("ModuleScript") then
	require(cutscene).listen()
end

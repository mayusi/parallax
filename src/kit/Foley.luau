--!strict
-- Foley.luau — footsteps and body foley on the client (AAA gap S4): a footfall at the stride the speed gives, on the
-- surface under the feet (Humanoid.FloorMaterial -> FoleyRules), walk or run; cloth every second step; a landing by
-- how fast the fall was. Sounds from the footsteps set (Assets: takes picked at random), played at the feet. The
-- character's own default running sound is muted (it would double every step).
--
--   require(ReplicatedStorage.kit.Foley).start()     -- once, in a LocalScript / client controller
--   .start({ surfaces = { Grass = "drygrass" } })  -- a game's own material -> surface (the set must make it)
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local Assets = require(script.Parent:WaitForChild("Assets"))
local Bus = require(script.Parent:WaitForChild("Bus"))
local FoleyRules = require(script.Parent:WaitForChild("FoleyRules"))

local Foley = {}

local function mute(character: Model)
	-- the default character sounds' running loop (classic Sound or the new AudioPlayer) - ours replaces it
	for _, d in character:GetDescendants() do
		if d.Name == "Running" and (d:IsA("Sound") or d.ClassName == "AudioPlayer") then
			pcall(function()
				(d :: any).Volume = 0
			end)
		end
	end
end

local function track(character: Model, surfaces: { [string]: unknown }?): RBXScriptConnection?
	local hum = character:WaitForChild("Humanoid", 10) :: Humanoid?
	local root = character:WaitForChild("HumanoidRootPart", 10) :: BasePart?
	if not hum or not root then
		return nil
	end
	task.delay(1, function()
		mute(character)
	end)
	local untilStep, steps, lastFall = 0, 0, 0
	hum.StateChanged:Connect(function(_, new)
		if new == Enum.HumanoidStateType.Landed then
			local name = FoleyRules.landSound(lastFall)
			if name then
				Assets.play(name, root.Position - Vector3.new(0, 2.5, 0), { Volume = 0.8 })
				Bus.shared:emit("Land", { sound = name, at = root.Position - Vector3.new(0, 2.5, 0) })
			end
		end
	end)
	return RunService.Heartbeat:Connect(function(dt: number)
		if not root.Parent then
			return
		end
		local v = root.AssemblyLinearVelocity
		if v.Y < 0 then
			lastFall = -v.Y
		elseif hum.FloorMaterial ~= Enum.Material.Air then
			lastFall = 0
		end
		local speed = Vector3.new(v.X, 0, v.Z).Magnitude
		local every = FoleyRules.interval(speed)
		if not every or hum.FloorMaterial == Enum.Material.Air then
			untilStep = 0
			return
		end
		untilStep -= dt
		if untilStep > 0 then
			return
		end
		untilStep = every
		local name = FoleyRules.stepSound(hum.FloorMaterial.Name, speed, surfaces)
		if name then
			local feet = root.Position - Vector3.new(0, 2.8, 0)
			Assets.play(name, feet, { Volume = 0.7, RollOffMaxDistance = 80 })
			Bus.shared:emit("Footstep", { sound = name, at = feet }) -- (local only: places that answer listen, kit EchoZones)
			steps += 1
			if steps % 2 == 0 then
				Assets.play("cloth_rustle", root.Position, { Volume = 0.4, RollOffMaxDistance = 40 })
			end
		end
	end)
end

-- the local player's character, now and after every respawn
function Foley.start(opts: { surfaces: { [string]: string }? }?)
	assert(RunService:IsClient(), "Foley.start is client-only (footsteps are presentation)")
	local player = Players.LocalPlayer
	local conn: RBXScriptConnection? = nil
	local function on(character: Model)
		if conn then
			conn:Disconnect()
		end
		conn = track(character, opts and opts.surfaces)
	end
	if player.Character then
		task.spawn(on, player.Character)
	end
	player.CharacterAdded:Connect(on)
end

return Foley

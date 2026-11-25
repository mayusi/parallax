--!strict
-- EchoZones.luau — places that answer the player, on the client: inside an echo zone each footstep / landing the
-- player makes (kit Foley emits them on the local event bus) comes back from deeper in, late, quieter, lower and
-- dark (an AudioEqualizer cuts the highs); after a walk there, when the player stops, one more step may come back that
-- they never took. Decisions: EchoRules (pure, tested). Data: the "echoes" list of src/shared/<World>Ambience.json
-- (deep = [x, height above the ground, z]). On the Audio API: each answer is a spatial kit Sfx voice on the "sfx" bus
-- (PARALLAX_FINAL_CLOSURE_SPEC Step 6).
--
--   local EchoZones = require(ReplicatedStorage.kit.EchoZones)
--   local stop = EchoZones.start(require(ReplicatedStorage.Shared.SampleRegionAmbience).echoes)
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local Bus = require(script.Parent:WaitForChild("Bus"))
local EchoRules = require(script.Parent:WaitForChild("EchoRules"))

local EchoZones = {}

-- the deep point's y is a height above the ground (the data does not know the terrain): terrain only, water ignored
local function groundY(x: number, z: number): number
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Include
	params.FilterDescendantsInstances = { workspace.Terrain }
	params.IgnoreWater = true
	local hit = workspace:Raycast(Vector3.new(x, 2000, z), Vector3.new(0, -4000, 0), params)
	return if hit then hit.Position.Y else 0
end

local SfxVoice: any = nil -- kit Sfx, required on the first answer (EchoZones loads before it in some games)
local function answer(sound: string, zn: any)
	local r = EchoRules.repeatOf(zn)
	task.delay(r.delay, function()
		if SfxVoice == nil then
			local m = script.Parent:FindFirstChild("Sfx")
			local ok, mod = false, nil
			if m then
				ok, mod = pcall(require, m)
			end
			SfxVoice = if ok then mod else false
		end
		if not SfxVoice then
			return
		end
		SfxVoice.voice(sound, {
			bus = "sfx",
			at = Vector3.new(r.at[1], groundY(r.at[1], r.at[3]) + r.at[2], r.at[3]),
			volume = 0.7 * r.volume,
			pitch = r.speed,
			near = 10,
			range = 160,
			eq = { high = -24, mid = -6, low = 0 }, -- from deep in the stone: the highs gone
		})
	end)
end

function EchoZones.start(zones: any): () -> ()
	assert(RunService:IsClient(), "EchoZones.start is client-only (sound is presentation)")
	if type(zones) ~= "table" or #zones == 0 then
		return function() end
	end
	local state = EchoRules.new()
	local lastZone: any = nil
	local rng = Random.new()
	local offStep = Bus.on("Footstep", function(e)
		if type(e) ~= "table" or typeof(e.at) ~= "Vector3" or type(e.sound) ~= "string" then
			return
		end
		local zn = EchoRules.zoneAt(zones, e.at.X, e.at.Y, e.at.Z)
		if zn then
			answer(e.sound, zn)
			EchoRules.step(state, Workspace:GetServerTimeNow(), e.sound)
			lastZone = zn
		end
	end)
	local offLand = Bus.on("Land", function(e)
		if type(e) == "table" and typeof(e.at) == "Vector3" and type(e.sound) == "string" then
			local zn = EchoRules.zoneAt(zones, e.at.X, e.at.Y, e.at.Z)
			if zn then
				answer(e.sound, zn)
			end
		end
	end)
	-- the room's reverb follows the camera (the ears are on it: kit Sfx's listeners): a zone's "reverb" name re-tunes the
	-- pooled AudioReverb of kit Sfx, leaving it goes dry (EchoRules.reverbSwitch keeps a zone's edge from flapping)
	local Sfx: any = nil
	local sfxModule = script.Parent:FindFirstChild("Sfx")
	if sfxModule and sfxModule:IsA("ModuleScript") then
		local okSfx, mod = pcall(require, sfxModule)
		if okSfx then
			Sfx = mod
		end
	end
	local roomReverb: string? = nil
	local lastSwitch = -1e9
	local conn = RunService.Heartbeat:Connect(function()
		local cam = Workspace.CurrentCamera
		if Sfx and cam then
			local p = cam.CFrame.Position
			local wanted = EchoRules.reverbAt(zones, p.X, p.Y, p.Z)
			local now = Workspace:GetServerTimeNow()
			if EchoRules.reverbSwitch(roomReverb, wanted, now, lastSwitch, 0.5) then
				roomReverb, lastSwitch = wanted, now
				Sfx.reverb(wanted)
			end
		end
		if lastZone then
			local phantom = EchoRules.due(state, lastZone, Workspace:GetServerTimeNow(), rng:NextNumber())
			if phantom then -- the step they did not take: one stride after the last echo, straight from the deep point
				local zn = table.clone(lastZone :: any) :: any
				zn.delay = 0.05
				answer(phantom, zn)
			end
		end
	end)
	return function()
		offStep()
		offLand()
		conn:Disconnect()
		if Sfx and roomReverb then
			Sfx.reverb(nil)
		end
	end
end

return EchoZones

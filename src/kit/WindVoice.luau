--!strict
-- WindVoice.luau — the castle's voice on the client: one looped tonal-wind sound per voice point (battlement runs,
-- tower tops), placed on the ground under each point + its height, swelling with Workspace.GlobalWind (the
-- WorldClock's one wind), louder where the wind grazes across the opening, only the nearest few sounding. The data is
-- the "voices" block of src/shared/<World>Ambience.json (`kit sfx ambience <World>`); the decisions are
-- WindVoiceRules (pure, tested). On the Audio API: every voice is a looped spatial kit Sfx voice on the "ambience" bus
-- (PARALLAX_FINAL_CLOSURE_SPEC Step 6; its roll-off is linear from `near` to `range`, the Audio API's distance curve, where
-- the old Sound used InverseTapered). A missing sound id is skipped after Sfx's one-time warning.
--
--   local WindVoice = require(ReplicatedStorage.kit.WindVoice)
--   local stop = WindVoice.start(require(ReplicatedStorage.Shared.SampleRegionAmbience).voices)
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local Sfx = require(script.Parent:WaitForChild("Sfx"))
local WindVoiceRules = require(script.Parent:WaitForChild("WindVoiceRules"))

local WindVoice = {}

WindVoice.TICK = 0.2
WindVoice.SMOOTH = 2.0 -- seconds a voice takes to follow the wind (a whistle swells, it does not switch)

local function listener(): Vector3?
	local ch = Players.LocalPlayer and Players.LocalPlayer.Character
	local root = ch and ch:FindFirstChild("HumanoidRootPart") :: BasePart?
	if root then
		return root.Position
	end
	local cam = Workspace.CurrentCamera
	return if cam then cam.Focus.Position else nil
end

local function groundY(x: number, z: number): number
	local params = RaycastParams.new() -- (terrain only: a ray landing on the wall top would lift the voice twice)
	params.FilterType = Enum.RaycastFilterType.Include
	params.FilterDescendantsInstances = { Workspace.Terrain }
	params.IgnoreWater = true -- (a tower standing in a lake: the ground is the lake bed, not its surface)
	local hit = Workspace:Raycast(Vector3.new(x, 2000, z), Vector3.new(0, -4000, 0), params)
	return if hit then hit.Position.Y else 0
end

function WindVoice.start(spec: any): () -> ()
	assert(RunService:IsClient(), "WindVoice.start is client-only (sound is presentation)")
	if type(spec) ~= "table" or type(spec.points) ~= "table" or type(spec.sound) ~= "string" then
		return function() end
	end
	local folder = Instance.new("Folder")
	folder.Name = "KitWindVoice"
	folder.Parent = Workspace
	local voices: { [number]: any } = {} -- point -> Sfx voice handle
	local levels: { [number]: number } = {}
	local anchors: { [number]: Attachment } = {}
	local holder = Instance.new("Part")
	holder.Name = "Voices"
	holder.Anchored, holder.CanCollide, holder.CanQuery, holder.CanTouch = true, false, false, false
	holder.Transparency = 1
	holder.Size = Vector3.new(1, 1, 1)
	holder.CFrame = CFrame.new()
	holder.Parent = folder
	local failed: { [number]: boolean } = {}
	local function voice(i: number): any
		if voices[i] or failed[i] then
			return voices[i]
		end
		local p = spec.points[i]
		local a = Instance.new("Attachment")
		a.WorldPosition = Vector3.new(p.x, groundY(p.x, p.z) + (tonumber(p.h) or 20), p.z)
		a.Parent = holder
		local v = Sfx.voice(spec.sound, {
			bus = "ambience",
			at = a,
			looped = true,
			volume = 0,
			near = tonumber(spec.near) or 18,
			range = tonumber(spec.range) or 260,
			timePosition = (i * 3.7) % 16, -- (voices out of phase: never one big unison pulse)
		})
		if not v then -- (no uploaded id: tried once, not every tick)
			a:Destroy()
			failed[i] = true
			return nil
		end
		anchors[i], voices[i], levels[i] = a, v, 0
		return v
	end
	local acc = 0
	local conn = RunService.Heartbeat:Connect(function(dt: number)
		acc += dt
		if acc < WindVoice.TICK then
			return
		end
		local step = acc
		acc = 0
		local at = listener()
		if not at then
			return
		end
		local w = Workspace.GlobalWind
		local level = WindVoiceRules.level(w.Magnitude, spec)
		local want = {}
		for _, i in WindVoiceRules.pick(spec.points, at.X, at.Z, spec.max, spec.range) do
			want[i] = true
			voice(i)
		end
		local k = math.clamp(step / WindVoice.SMOOTH, 0, 1)
		for i, v in voices do
			local p = spec.points[i]
			local target = if want[i]
				then WindVoiceRules.volume(
					level,
					WindVoiceRules.exposure(w.X, w.Z, tonumber(p.nx) or 0, tonumber(p.nz) or 0),
					spec
				)
				else 0
			levels[i] += (target - levels[i]) * k
			v.setVolume(levels[i])
			v.setPitch(WindVoiceRules.pitch(level))
			if not want[i] and levels[i] < 0.005 then -- (out of range and faded: free the voice)
				v.stop()
				anchors[i]:Destroy()
				voices[i], anchors[i], levels[i] = nil, nil, nil
			end
		end
	end)
	return function()
		conn:Disconnect()
		for _, v in voices do
			v.stop()
		end
		folder:Destroy()
	end
end

return WindVoice

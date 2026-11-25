--!strict
-- GustEvents.luau — rare one-shots the wind causes, on the client: each rule names a sound and a place; when the
-- world's wind gusts (GustRules: a rise above its own recent average, rising edge, cooldown, chance) the sound plays
-- there - optionally MUFFLED as if heard through water (an AudioEqualizer cuts the highs: the drowned bell). Data: the
-- "gusts" list of src/shared/<World>Ambience.json (`kit sfx ambience <World>`). On the Audio API (a spatial kit Sfx
-- voice on the "ambience" bus: PARALLAX_FINAL_CLOSURE_SPEC Step 6), timed on the game's one clock
-- (Workspace:GetServerTimeNow, as kit Moves times every hit - not this client's os.clock).
--
--   local GustEvents = require(ReplicatedStorage.kit.GustEvents)
--   local stop = GustEvents.start(require(ReplicatedStorage.Shared.SampleRegionAmbience).gusts)
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local GustRules = require(script.Parent:WaitForChild("GustRules"))
local Sfx = require(script.Parent:WaitForChild("Sfx"))

local GustEvents = {}

GustEvents.TICK = 0.25

local function groundY(x: number, z: number): number
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Include
	params.FilterDescendantsInstances = { Workspace.Terrain }
	params.IgnoreWater = true -- (a tower standing in a lake: the ground is the lake bed, not its surface)
	local hit = Workspace:Raycast(Vector3.new(x, 2000, z), Vector3.new(0, -4000, 0), params)
	return if hit then hit.Position.Y else 0
end

function GustEvents.start(rules: any): () -> ()
	assert(RunService:IsClient(), "GustEvents.start is client-only (sound is presentation)")
	if type(rules) ~= "table" or #rules == 0 then
		return function() end
	end
	local state = GustRules.new()
	local rng = Random.new()
	local acc = 0
	local conn = RunService.Heartbeat:Connect(function(dt: number)
		acc += dt
		if acc < GustEvents.TICK then
			return
		end
		local step = acc
		acc = 0
		local speed = Workspace.GlobalWind.Magnitude
		GustRules.track(state, speed, step, 20)
		local now = Workspace:GetServerTimeNow()
		for i, rule in rules do
			if
				type(rule) == "table"
				and type(rule.sound) == "string"
				and GustRules.fires(state, i, rule, speed, now, rng:NextNumber())
			then
				local x, z = tonumber(rule.x) or 0, tonumber(rule.z) or 0
				local pos = Vector3.new(x, groundY(x, z) + (tonumber(rule.h) or 0), z)
				Sfx.voice(rule.sound, {
					bus = "ambience",
					at = pos,
					volume = tonumber(rule.volume) or 0.6,
					near = tonumber(rule.near) or 25,
					range = tonumber(rule.range) or 300,
					pitch = tonumber(rule.pitch) or 1,
					-- heard through water: the highs and most of the mids gone
					eq = if rule.muffle then { high = -40, mid = -14, low = 2 } else nil,
				})
			end
		end
	end)
	return function()
		conn:Disconnect()
	end
end

return GustEvents

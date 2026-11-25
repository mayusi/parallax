--!strict
-- Ambience.luau — a world's ambience on the client: the beds (looped, 2D) crossfade with where the listener stands, and
-- scatter one-shots (birds, crows, a far bell) play at places around the listener, more often where their kinds are.
-- The data is the world's src/shared/<World>Ambience.json (`kit sfx ambience <World>` - zones from the blueprint);
-- the decisions are AmbienceRules (pure, tested). On the Audio API (PARALLAX_FINAL_CLOSURE_SPEC Step 6): beds are looped
-- 2D kit Sfx voices on the "ambience" bus, scatter one-shots spatial voices on it (the bus's fader, snapshots and the
-- duck under a hit apply). A missing id is skipped after Sfx's one-time warning, so a world plays (silently) before
-- its sounds are uploaded.
--
--   local Ambience = require(ReplicatedStorage.kit.Ambience)
--   local stop = Ambience.start(require(ReplicatedStorage.Shared.SampleRegionAmbience))
local Lighting = game:GetService("Lighting")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local AmbienceRules = require(script.Parent:WaitForChild("AmbienceRules"))
local Sfx = require(script.Parent:WaitForChild("Sfx"))

local Ambience = {}

Ambience.TICK = 0.2 -- seconds between listener checks
Ambience.CROSSFADE = 1.5 -- seconds a bed takes to reach its new volume

local function listener(): Vector3?
	local ch = Players.LocalPlayer and Players.LocalPlayer.Character
	local root = ch and ch:FindFirstChild("HumanoidRootPart") :: BasePart?
	if root then
		return root.Position
	end
	local cam = Workspace.CurrentCamera
	return if cam then cam.Focus.Position else nil
end

-- start the ambience; returns the function that stops it (and removes its sounds)
function Ambience.start(spec: any): () -> ()
	assert(RunService:IsClient(), "Ambience.start is client-only (ambience is presentation)")
	local beds: { [string]: any } = {} -- bed -> Sfx voice handle
	local levels: { [string]: number } = {}
	for _, bed in (if type(spec) == "table" and type(spec.beds) == "table" then spec.beds else {}) :: { [string]: any } do
		if type(bed) == "string" and not beds[bed] then
			local v = Sfx.voice(bed, { bus = "ambience", looped = true, volume = 0 })
			if v then
				beds[bed] = v
				levels[bed] = 0
			end
		end
	end
	local rng = Random.new()
	local scatter: { any } = if type(spec) == "table" and type(spec.scatter) == "table" then spec.scatter else {}
	local due: { number } = {}
	local now0 = Workspace:GetServerTimeNow()
	for i, rule in scatter do
		due[i] = AmbienceRules.nextAt(rule, now0, rng:NextNumber())
	end
	local acc = 0
	local conn = RunService.Heartbeat:Connect(function(dt: number)
		acc += dt
		if acc < Ambience.TICK then
			return
		end
		local step = acc
		acc = 0
		local at = listener()
		if not at then
			return
		end
		-- the world's one clock and one wind (kit WorldClock) shape the ambience too
		local gw = Workspace.GlobalWind.Magnitude
		local hour, wind = Lighting.ClockTime, if gw > 0 then gw else nil -- (no wind blowing: the beds as authored)
		local targets = AmbienceRules.beds(spec, at.X, at.Z, wind)
		local k = math.clamp(step / Ambience.CROSSFADE, 0, 1)
		for bed, v in beds do
			local target = targets[bed] or 0
			levels[bed] += (target - levels[bed]) * k
			v.setVolume(levels[bed])
		end
		local here = AmbienceRules.presence(spec, at.X, at.Z)
		local now = Workspace:GetServerTimeNow()
		for i, rule in scatter do
			if due[i] and now >= due[i] then
				due[i] = AmbienceRules.nextAt(rule, now, rng:NextNumber())
				if rng:NextNumber() < AmbienceRules.chance(rule, here, hour) then
					local dx, dy, dz = AmbienceRules.offset(rule, rng:NextNumber(), rng:NextNumber(), rng:NextNumber())
					Sfx.voice(rule.sound, {
						bus = "ambience",
						at = at + Vector3.new(dx, dy, dz),
						volume = if type(rule.volume) == "number" then rule.volume else 0.5,
						near = 20,
						range = 400,
					})
				end
			end
		end
	end)
	return function()
		conn:Disconnect()
		for _, v in beds do
			v.stop()
		end
	end
end

return Ambience

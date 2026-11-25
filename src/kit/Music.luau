--!strict
-- Music.luau — adaptive music on the client (AAA gap S5): every stem loops from the same instant (they stay in
-- sync), each faded by the INTENSITY (MusicRules.stems); gameplay events on the kit Bus bump it, it decays on its
-- own; stingers fire on the next beat. On the Audio API (PARALLAX_FINAL_CLOSURE_SPEC Step 6): every stem is a looped
-- kit Sfx voice on the "music" bus - its fader, the player's music slider and the sidechain duck under sfx + voice
-- apply. A sound with no uploaded id is skipped after Sfx's one-time warning.
--
--   require(ReplicatedStorage.kit.Music).start(require(ReplicatedStorage.Shared.DojoMusic))
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local Bus = require(script.Parent:WaitForChild("Bus"))
local MusicRules = require(script.Parent:WaitForChild("MusicRules"))
local Sfx = require(script.Parent:WaitForChild("Sfx"))

local Music = {}

Music.FADE = 1.2 -- seconds a stem takes to reach its new volume

function Music.start(spec: any): () -> ()
	assert(RunService:IsClient(), "Music.start is client-only (music is presentation)")
	Bus.start()
	local stems: { [string]: any } = {} -- name -> Sfx voice handle
	local levels: { [string]: number } = {}
	for _, s in (if type(spec) == "table" and type(spec.stems) == "table" then spec.stems else {}) :: { any } do
		if type(s) == "table" and type(s.sound) == "string" and not stems[s.sound] then
			local v = Sfx.voice(s.sound, { bus = "music", looped = true, volume = 0, autoplay = false })
			if v then
				stems[s.sound] = v
				levels[s.sound] = 0
			end
		end
	end
	-- one instant for all: the stems never drift apart
	for _, v in stems do
		v.play()
	end
	local start = Workspace:GetServerTimeNow()
	local intensity = 0
	local stops: { () -> () } = {}
	for event in (if type(spec) == "table" and type(spec.bumps) == "table" then spec.bumps else {}) :: { [string]: any } do
		table.insert(
			stops,
			Bus.on(event, function()
				intensity = MusicRules.bump(spec, intensity, event)
			end)
		)
	end
	for event, name in
		(if type(spec) == "table" and type(spec.stingers) == "table" then spec.stingers else {}) :: { [string]: any }
	do
		if type(name) == "string" then
			table.insert(
				stops,
				Bus.on(event, function()
					local now = Workspace:GetServerTimeNow()
					task.delay(math.max(0, MusicRules.nextBeat(spec, start, now) - now), function()
						Sfx.voice(name, { bus = "music", volume = 0.8 })
					end)
				end)
			)
		end
	end
	local conn = RunService.Heartbeat:Connect(function(dt: number)
		intensity = MusicRules.decay(spec, intensity, dt)
		local targets = MusicRules.stems(spec, intensity)
		local k = math.clamp(dt / Music.FADE, 0, 1)
		for name, v in stems do
			levels[name] += ((targets[name] or 0) - levels[name]) * k
			v.setVolume(levels[name])
		end
	end)
	return function()
		conn:Disconnect()
		for _, stop in stops do
			stop()
		end
		for _, v in stems do
			v.stop()
		end
	end
end

return Music

-- Ambient.client.luau (kit) — a world's weather around the player: a world blueprint's "ambient" ("snow" | "ash" |
-- "leaves" | "embers" | "rain" | "sand") hangs one small emitter above the camera on THIS client (dense where you
-- look, cheap; a map-wide emitter would be sparse and heavy). The kit world compiler writes it into KitEnvironment.
-- A world with a "weather" CYCLE (WeatherRules.luau) gets one emitter for each weather it ever shows; how hard each
-- falls is read off the SERVER's clock twice a second, so every player stands in the same weather and nothing is
-- sent (the light and the air are the server's: WorldClock). This script runs only in Roblox: the rules it plays
-- are tested (kit/test/spec/worldweather.spec.luau), what it looks like is not.
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local SMOKE = "rbxasset://textures/particles/smoke_main.dds"
local SPARK = "rbxasset://textures/particles/sparkles_main.dds"

local function seq(points: { { number } }): NumberSequence
	local keys = {}
	for _, p in points do
		table.insert(keys, NumberSequenceKeypoint.new(p[1], p[2]))
	end
	return NumberSequence.new(keys)
end

local PRESETS: { [string]: { [string]: any } } = {
	snow = {
		Texture = SMOKE,
		Rate = 140,
		Lifetime = NumberRange.new(8, 12),
		Speed = NumberRange.new(5, 8),
		Acceleration = Vector3.new(1.2, 0, 0.5),
		RotSpeed = NumberRange.new(-60, 60),
		Size = seq({ { 0, 0.3 }, { 1, 0.24 } }),
		Transparency = seq({ { 0, 0.2 }, { 0.85, 0.3 }, { 1, 1 } }),
		Color = ColorSequence.new(Color3.new(1, 1, 1)),
		LightInfluence = 0.8,
	},
	ash = {
		Texture = SMOKE,
		Rate = 90,
		Lifetime = NumberRange.new(9, 14),
		Speed = NumberRange.new(2, 4),
		Acceleration = Vector3.new(0.8, -0.4, 0.3),
		RotSpeed = NumberRange.new(-90, 90),
		Size = seq({ { 0, 0.22 }, { 1, 0.16 } }),
		Transparency = seq({ { 0, 0.3 }, { 1, 1 } }),
		Color = ColorSequence.new(Color3.fromRGB(70, 66, 62)),
		LightInfluence = 1,
	},
	leaves = {
		Texture = SPARK,
		Rate = 30,
		Lifetime = NumberRange.new(9, 14),
		Speed = NumberRange.new(1, 3),
		Acceleration = Vector3.new(1, -1, 0.4),
		RotSpeed = NumberRange.new(-120, 120),
		Size = seq({ { 0, 0.35 }, { 1, 0.25 } }),
		Transparency = seq({ { 0, 0.1 }, { 0.85, 0.3 }, { 1, 1 } }),
		Color = ColorSequence.new(Color3.fromRGB(255, 200, 90)),
		LightEmission = 0.6,
		LightInfluence = 0.4,
	},
	rain = { -- a night downpour: fast thin streaks
		Texture = SPARK,
		Rate = 420,
		Lifetime = NumberRange.new(0.9, 1.3),
		Speed = NumberRange.new(70, 90),
		Acceleration = Vector3.new(2, 0, 1),
		Size = seq({ { 0, 0.09 }, { 1, 0.09 } }),
		Transparency = seq({ { 0, 0.45 }, { 1, 0.7 } }),
		Color = ColorSequence.new(Color3.fromRGB(190, 210, 255)),
		LightEmission = 0.3,
		LightInfluence = 0.7,
		Squash = seq({ { 0, -3 }, { 1, -3 } }),
	},
	sand = { -- drifting sand blown low across the dunes
		Texture = SMOKE,
		Rate = 120,
		Lifetime = NumberRange.new(4, 7),
		Speed = NumberRange.new(10, 16),
		Acceleration = Vector3.new(6, 0, 2),
		RotSpeed = NumberRange.new(-40, 40),
		Size = seq({ { 0, 0.18 }, { 1, 0.12 } }),
		Transparency = seq({ { 0, 0.35 }, { 1, 1 } }),
		Color = ColorSequence.new(Color3.fromRGB(232, 176, 112)),
		LightInfluence = 1,
	},
	embers = {
		Texture = SPARK,
		Rate = 40,
		Lifetime = NumberRange.new(3, 6),
		Speed = NumberRange.new(2, 5),
		Acceleration = Vector3.new(0.5, 3, 0.2),
		Size = seq({ { 0, 0.18 }, { 1, 0 } }),
		Transparency = seq({ { 0, 0.1 }, { 1, 1 } }),
		Color = ColorSequence.new(Color3.fromRGB(255, 120, 40)),
		LightEmission = 1,
		LightInfluence = 0,
	},
}

local function decoded(d: Instance): any
	local json = d:GetAttribute("KitEnvironment")
	if type(json) ~= "string" then
		return nil
	end
	local ok, env = pcall(function()
		return HttpService:JSONDecode(json)
	end)
	return if ok and type(env) == "table" then env else nil
end

-- the world's environment (the world may still be streaming in: look again for a while before giving up)
local function environmentOf(): any
	local root = Workspace:WaitForChild("KitWorld", 30)
	if not root then
		return nil
	end
	for _ = 1, 31 do
		for _, d in root:GetDescendants() do
			local env = decoded(d)
			if env then
				return env
			end
		end
		task.wait(2)
	end
	return nil
end

local holders: { [string]: BasePart } = {}
local emitters: { [string]: ParticleEmitter } = {}

local function hang(kind: string)
	local preset = PRESETS[kind]
	if not preset or emitters[kind] then
		return
	end
	local holder = Instance.new("Part")
	holder.Name = "KitAmbient"
	holder.Anchored, holder.CanCollide, holder.CanQuery, holder.CanTouch = true, false, false, false
	holder.Transparency = 1
	holder.Size = Vector3.new(110, 1, 110)
	local emitter = Instance.new("ParticleEmitter")
	emitter.EmissionDirection = if kind == "embers"
		then Enum.NormalId.Top
		elseif kind == "sand" then Enum.NormalId.Right -- blown along the ground, not falling
		else Enum.NormalId.Bottom
	emitter.Shape = Enum.ParticleEmitterShape.Box
	for k, v in preset do
		(emitter :: any)[k] = v
	end
	emitter.Parent = holder
	holder.Parent = Workspace -- (a LocalScript's part: this client only)
	holders[kind], emitters[kind] = holder, emitter
end

local env = environmentOf()
if not env then
	return
end
local weather = if type(env.weather) == "table" then env.weather else nil
local Rules = if weather
	then require(ReplicatedStorage:WaitForChild("kit"):WaitForChild("WeatherRules")) :: any
	else nil
if weather then
	for _, kind in Rules.kinds(weather) do
		hang(kind)
		emitters[kind].Rate = 0 -- (nothing falls until the cycle says so)
	end
elseif type(env.ambient) == "string" then
	hang(env.ambient)
end

RunService.RenderStepped:Connect(function()
	local cam = Workspace.CurrentCamera
	local p = cam.CFrame.Position + cam.CFrame.LookVector * 30
	for kind, holder in holders do
		holder.CFrame = CFrame.new(
			p.X,
			cam.CFrame.Position.Y + (if kind == "embers" then -6 elseif kind == "sand" then -3 else 34),
			p.Z
		)
	end
end)

if not weather then
	return
end
-- THE CYCLE: how hard each weather falls at this second of the server's clock
while true do
	local air = Rules.air(Rules.at(weather, Workspace:GetServerTimeNow()))
	for kind, emitter in emitters do
		emitter.Rate = PRESETS[kind].Rate * (air.fall[kind] or 0)
	end
	task.wait(0.5)
end

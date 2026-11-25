--!strict
-- WorldClock.luau — the world's time of day and wind on the server (AAA gaps W8 / W9): Lighting.ClockTime runs the
-- day, the lighting blends between the day's keys (WorldClockRules.at, applied by Environment.lighting), and
-- Workspace.GlobalWind blows (terrain grass and wind-affected particles move with it; the ambience reads it).
-- Lighting and Workspace replicate, so clients see the same sky and the same wind.
-- A world's WEATHER CYCLE (env.weather; WeatherRules) closes the air in and takes light on top of whatever the
-- lighting or the time of day asks for at that moment; it is read off Workspace:GetServerTimeNow(), the clock each
-- client reads for what falls round its camera (client/Ambient.client.luau).
--
--   WorldClock.start(env, Environment.lighting)    -- env.day / env.wind / env.weather from kit world
--                                                      (Environment.apply calls it)
local Lighting = game:GetService("Lighting")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local SkyRules = require(script.Parent:WaitForChild("SkyRules"))
local WeatherRules = require(script.Parent:WaitForChild("WeatherRules"))
local WorldClockRules = require(script.Parent:WaitForChild("WorldClockRules"))

local WorldClock = {}

WorldClock.TICK = 0.5 -- seconds between updates (a day of 20 minutes moves 0.01 h per tick)

-- `light` applies one lighting key (Environment.lighting: passed in, so the two modules never require each other)
function WorldClock.start(env: any, light: (any) -> ()): () -> ()
	assert(RunService:IsServer(), "WorldClock.start is server-only (the sky and the wind replicate)")
	local day, wind = env and env.day, env and env.wind
	local weather = env and env.weather
	-- what Lighting holds before any weather (the world's own lighting is already applied: Environment.apply)
	local atmosphere = Lighting:FindFirstChildOfClass("Atmosphere")
	local own = {
		brightness = Lighting.Brightness,
		density = if atmosphere then atmosphere.Density else 0,
		haze = if atmosphere then atmosphere.Haze else 0,
		fogs = if weather then WeatherRules.fogs(weather) else false,
	}
	if weather and own.fogs and not atmosphere then
		-- (a place with no Atmosphere and a weather that closes the air in: one is made, clear until it does)
		local made = Instance.new("Atmosphere")
		made.Name = "KitAtmosphere"
		made.Density, made.Haze = 0, 0
		made.Parent = Lighting
	end
	-- THE WEATHER writes three numbers and nothing else - Brightness, the Atmosphere's Density and Haze - from what
	-- the lighting or the time of day asks for at that moment (`key`: nil with no time of day). Whichever
	-- Atmosphere the place has is the one moved: none is replaced.
	local function blow(key: any)
		local air = WeatherRules.air(WeatherRules.at(weather, Workspace:GetServerTimeNow()))
		local look = WeatherRules.look(air, WeatherRules.base(key, own))
		Lighting.Brightness = look.brightness
		local atm = Lighting:FindFirstChildOfClass("Atmosphere")
		if atm then
			atm.Density, atm.Haze = look.density, look.haze
		end
	end
	local t0, acc = os.clock(), WorldClock.TICK
	local conn = RunService.Heartbeat:Connect(function(dt: number)
		acc += dt
		if acc < WorldClock.TICK then
			return
		end
		acc = 0
		local s = os.clock() - t0
		if day then
			local hour = WorldClockRules.hourAt(day, s)
			Lighting.ClockTime = hour
			-- (a sky of the kit's own has its sun drawn in it: turned again so that it stays over the light)
			local box = Lighting:FindFirstChild(SkyRules.NAME)
			local drawn = if box then box:GetAttribute(SkyRules.DRAWN) else nil
			if box and type(drawn) == "number" then
				local sun = Lighting:GetSunDirection()
				local turn = SkyRules.turn(drawn, sun.X, sun.Y, sun.Z)
				if turn then
					(box :: any).SkyboxOrientation = Vector3.new(0, turn, 0)
				end
			end
			local key = WorldClockRules.at(day, hour)
			if key then
				light(key)
			end
			if weather then
				blow(key) -- (after the key, in the same step: clients get the one final value)
			end
		elseif weather then
			blow(nil)
		end
		if wind then
			local x, z, speed = WorldClockRules.wind(wind, s)
			Workspace.GlobalWind = Vector3.new(x * speed, 0, z * speed)
		end
	end)
	return function()
		conn:Disconnect()
	end
end

return WorldClock

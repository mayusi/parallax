--!strict
-- worldlight.luau (kit) - W5, A WORLD'S LIGHT PASS (LIMITATIONS_FIXES_V4 5.1 / 5.4 / 13.5: "ship W5 kit world light
-- (LightingStyle.Realistic, <= 16 shadow lights)"; card ut7p: GothicCourtyard at night was pitch black outside its
-- three lamps, its 52 lights every one Shadows = false).
--
-- Two things, both pure:
--   * Light.PRESETS: five night-city looks for Roblox's Realistic lighting style (Lighting.LightingStyle =
--     Realistic, Technology Future): a moonlit night, a dusk, a fog, a storm night, a dawn. Each one is a whole
--     Environment lighting table (clock, ambient, exposure, atmosphere, grade, bloom, clouds) - the moon or the low
--     sun gives the streets a readable floor of light, the lamps give the pools.
--   * Light.pick: WHICH lamps cast shadows. Every shadow light renders the scene again; the engine budget (the V4
--     law of budget honesty: <= 16 shadow lights within 120 studs, qa.perf.shadowLights) is held by construction:
--     the brightest and widest lamps first (a lamp's reach: brightness x range), a lamp skipped while one already
--     chosen stands within half their ranges (two lamps a pace apart throw one shadow), and none taken that would
--     put more than `most` shadow lights within `reach` studs of any shadow light. -> the chosen indices.
-- What it does NOT know: what the player sees (a lamp behind a wall still counts), and how the presets read in
-- Studio - that is the owner's eye (kit world light writes the scratch copy that is walked).
local Light = {}

Light.MOST = 16 -- shadow lights within REACH studs of any shadow light (World.SHADOW_WARN)
Light.REACH = 120 -- studs across the ground (World.SHADOW_REACH)

-- (lightingStyle: Roblox's Lighting.LightingStyle; prioritizeQuality: Lighting.PrioritizeLightingQuality)
Light.PRESETS = {
	-- a clear night under a high moon: cold blue floor of light on the stone, the lamps warm, black sky with stars
	gothic_moonlit = {
		lightingStyle = "Realistic",
		prioritizeQuality = true,
		clockTime = 0.2,
		brightness = 1.6,
		ambient = { 26, 30, 44 },
		outdoorAmbient = { 58, 66, 92 },
		exposure = 0.35,
		atmosphere = {
			density = 0.32,
			offset = 0.08,
			color = { 70, 80, 110 },
			decay = { 34, 38, 58 },
			glare = 0,
			haze = 1.2,
		},
		bloom = { intensity = 0.9, size = 28, threshold = 1.1 },
		sunRays = { intensity = 0, spread = 0.5 },
		colorCorrection = { contrast = 0.14, saturation = -0.12, tint = { 206, 218, 255 } },
		clouds = { cover = 0.35, density = 0.45, color = { 64, 70, 88 } },
	},
	-- the last of the day: a low red sun behind the roofs, the lamps just lit
	gothic_dusk = {
		lightingStyle = "Realistic",
		prioritizeQuality = true,
		clockTime = 18.2,
		brightness = 2.2,
		ambient = { 40, 34, 44 },
		outdoorAmbient = { 104, 86, 96 },
		exposure = 0.1,
		atmosphere = {
			density = 0.4,
			offset = 0.18,
			color = { 182, 132, 118 },
			decay = { 96, 58, 70 },
			glare = 0.4,
			haze = 2.2,
		},
		bloom = { intensity = 0.8, size = 30, threshold = 1.15 },
		sunRays = { intensity = 0.12, spread = 0.7 },
		colorCorrection = { contrast = 0.12, saturation = -0.04, tint = { 255, 236, 226 } },
		clouds = { cover = 0.55, density = 0.6, color = { 180, 130, 130 } },
	},
	-- a night fog: the far streets gone, every lamp a halo, close stone still readable
	gothic_fog = {
		lightingStyle = "Realistic",
		prioritizeQuality = true,
		clockTime = 23.4,
		brightness = 1.2,
		ambient = { 34, 36, 42 },
		outdoorAmbient = { 74, 78, 88 },
		exposure = 0.4,
		atmosphere = {
			density = 0.62,
			offset = 0.0,
			color = { 96, 100, 110 },
			decay = { 60, 62, 70 },
			glare = 0,
			haze = 2.6,
		},
		bloom = { intensity = 1.1, size = 36, threshold = 1.0 },
		sunRays = { intensity = 0, spread = 0.5 },
		colorCorrection = { contrast = 0.08, saturation = -0.2, tint = { 224, 228, 240 } },
		clouds = { cover = 0.8, density = 0.7, color = { 70, 72, 80 } },
	},
	-- a storm night: low heavy cloud, a green-grey cast, the lamps the only warmth
	gothic_storm = {
		lightingStyle = "Realistic",
		prioritizeQuality = true,
		clockTime = 21.5,
		brightness = 1.0,
		ambient = { 28, 32, 34 },
		outdoorAmbient = { 60, 70, 72 },
		exposure = 0.3,
		atmosphere = {
			density = 0.48,
			offset = 0.12,
			color = { 78, 92, 92 },
			decay = { 42, 50, 52 },
			glare = 0,
			haze = 1.8,
		},
		bloom = { intensity = 1.0, size = 30, threshold = 1.05 },
		sunRays = { intensity = 0, spread = 0.5 },
		colorCorrection = { contrast = 0.18, saturation = -0.18, tint = { 214, 230, 226 } },
		clouds = { cover = 0.95, density = 0.85, color = { 50, 56, 58 } },
	},
	-- before sunrise: a pale cold sky over still-dark streets, the lamps fading
	gothic_dawn = {
		lightingStyle = "Realistic",
		prioritizeQuality = true,
		clockTime = 6.1,
		brightness = 1.8,
		ambient = { 38, 40, 50 },
		outdoorAmbient = { 96, 102, 120 },
		exposure = 0.15,
		atmosphere = {
			density = 0.42,
			offset = 0.2,
			color = { 150, 156, 176 },
			decay = { 110, 96, 104 },
			glare = 0.2,
			haze = 2.4,
		},
		bloom = { intensity = 0.7, size = 28, threshold = 1.2 },
		sunRays = { intensity = 0.08, spread = 0.6 },
		colorCorrection = { contrast = 0.1, saturation = -0.08, tint = { 236, 238, 255 } },
		clouds = { cover = 0.5, density = 0.55, color = { 170, 168, 182 } },
	},
}
Light.NAMES = { "gothic_moonlit", "gothic_dusk", "gothic_fog", "gothic_storm", "gothic_dawn" }

export type Lamp = { x: number, z: number, range: number, brightness: number }

-- the lamps that cast shadows: indices into `lamps`, in the order they were chosen
function Light.pick(lamps: { Lamp }, most: number?, reach: number?): { number }
	local m = most or Light.MOST
	local r2 = (reach or Light.REACH) ^ 2
	local order = {}
	for i = 1, #lamps do
		table.insert(order, i)
	end
	local function score(l: Lamp): number
		return math.max(0, l.brightness) * math.max(0, l.range)
	end
	table.sort(order, function(a, b)
		local sa, sb = score(lamps[a]), score(lamps[b])
		if math.abs(sa - sb) > 1e-9 then
			return sa > sb
		end
		return a < b
	end)
	local chosen: { number } = {}
	local count: { [number]: number } = {} -- (shadow lights within reach of each chosen one, itself counted)
	for _, i in order do
		local a = lamps[i]
		if score(a) <= 0 then
			continue
		end
		local ok, near = true, 1
		for _, j in chosen do
			local b = lamps[j]
			local d2 = (a.x - b.x) ^ 2 + (a.z - b.z) ^ 2
			if d2 < (0.5 * math.min(a.range, b.range)) ^ 2 then
				ok = false -- (one shadow already falls from here)
				break
			end
			if d2 <= r2 then
				near += 1
				if count[j] + 1 > m then
					ok = false
					break
				end
			end
		end
		if ok and near <= m then
			for _, j in chosen do
				local b = lamps[j]
				if (a.x - b.x) ^ 2 + (a.z - b.z) ^ 2 <= r2 then
					count[j] += 1
				end
			end
			count[i] = near
			table.insert(chosen, i)
		end
	end
	return chosen
end

-- the most shadow lights within reach of any one of them (the budget's own measure: World's shadow check)
function Light.worst(lamps: { Lamp }, chosen: { number }, reach: number?): number
	local r2 = (reach or Light.REACH) ^ 2
	local worst = 0
	for _, i in chosen do
		local n = 0
		for _, j in chosen do
			if (lamps[i].x - lamps[j].x) ^ 2 + (lamps[i].z - lamps[j].z) ^ 2 <= r2 then
				n += 1
			end
		end
		worst = math.max(worst, n)
	end
	return worst
end

return Light

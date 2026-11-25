-- environment.luau — a world's LIGHTING and TERRAIN (pure; validated at compile, applied at runtime).
-- Rojo cannot carry Terrain or Lighting effects inside a model, so `kit world` stores them on the world model
-- (attribute KitEnvironment = JSON) and the kit's Environment runtime applies them when the server starts
-- (and in edit mode: require(ReplicatedStorage.kit.Environment).applyAll() — see the world skill).
--
-- "lighting": "golden" | "noon" | "overcast" | "storm" | "night" | "scifi_dusk"
--             or { "preset": "storm", "clockTime": 15.5, "atmosphere": {...}, "colorCorrection": {...}, ... }
-- "terrain": [ op, ... ]  (positions in studs; terrain is 4-stud voxels)
--   { "ground": { "center": [x, y, z] (y = the surface height), "size": [w, d], "material": "Grass",
--                 "under": "Rock", "depth": 24, "noise": { "amplitude": 6, "scale": 90, "seed": 7 },
--                 "patches": [ { "material": "Ground", "above": 0.55 } ],      noise value 0..1 > above -> patch
--                 "flat": [ { "center": [x, z], "radius": 40, "height": 0 } ] } }   level pads for buildings
--   { "block": { "center": [x, y, z], "size": [x, y, z], "material": "Rock" } }
--   { "ball": { "center": [x, y, z], "radius": 12, "material": "Rock" } }       (boulders, hills)
--   { "cylinder": { "center": [x, y, z], "radius": 8, "height": 20, "material": "Rock" } }   (pillars, mesas)
--   { "sdf": { "material": "Rock", "shapes": [ { "ball" | "box" | "capsule": {...}, "cut"?: true, "blend"?: studs } ] } }
--     (caves, overhangs, arches: shapes joined and cut out of each other AND out of the land before it - after the
--     ground in the list. src/kit/SdfRules.luau)
--   { "water": { "center": [x, y, z], "size": [x, y, z] } }
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Config = require("./config")
local Sdf = require("../../src/kit/SdfRules")
local WorldLight = require("./worldlight")

local Environment = {}

export type Issue = { path: string, message: string, severity: string }

Environment.MATERIALS = {
	Grass = true,
	LeafyGrass = true,
	Ground = true,
	Mud = true,
	Sand = true,
	Sandstone = true,
	Rock = true,
	Slate = true,
	Basalt = true,
	Limestone = true,
	CrackedLava = true,
	Snow = true,
	Glacier = true,
	Ice = true,
	Salt = true,
	Asphalt = true,
	Concrete = true,
	Pavement = true,
	Cobblestone = true,
	Brick = true,
	WoodPlanks = true,
	Water = true,
	Air = true,
}

-- art-directed presets (Future lighting + atmosphere + grade + clouds). Colours are 0..255.
Environment.LIGHTING = {
	-- a jungle morning (Uncharted): humid green-gold haze, god rays through the canopy, saturated greens
	jungle = {
		clockTime = 9.6,
		brightness = 2.5,
		ambient = { 48, 60, 40 },
		outdoorAmbient = { 108, 130, 92 },
		exposure = 0.15,
		geographicLatitude = 8,
		atmosphere = {
			density = 0.5,
			offset = 0.28,
			color = { 182, 200, 156 },
			decay = { 120, 140, 96 },
			glare = 0.35,
			haze = 2.8,
		},
		bloom = { intensity = 0.8, size = 30, threshold = 1.1 },
		sunRays = { intensity = 0.26, spread = 0.85 },
		colorCorrection = { contrast = 0.12, saturation = 0.12, tint = { 240, 255, 232 } },
		clouds = { cover = 0.5, density = 0.5, color = { 236, 244, 230 } },
	},
	-- a neon city at night (anime battlegrounds): deep blue-violet dark, wet streets, neon carries the light
	neon_night = {
		clockTime = 23.4,
		brightness = 0.9,
		ambient = { 54, 46, 84 },
		outdoorAmbient = { 92, 84, 140 },
		exposure = 0.6,
		atmosphere = {
			density = 0.4,
			offset = 0.1,
			color = { 78, 62, 120 },
			decay = { 60, 40, 96 },
			glare = 0.1,
			haze = 1.8,
		},
		bloom = { intensity = 1.2, size = 36, threshold = 0.9 },
		sunRays = { intensity = 0.02, spread = 0.4 },
		colorCorrection = { contrast = 0.18, saturation = 0.2, tint = { 236, 230, 255 } },
		clouds = { cover = 0.6, density = 0.5, color = { 120, 100, 160 } },
	},
	-- a desert at the end of the day (Journey): a low copper sun, warm haze, glowing sand, strong bloom
	desert = {
		clockTime = 17.3,
		brightness = 3.2,
		ambient = { 70, 52, 40 },
		outdoorAmbient = { 160, 118, 86 },
		exposure = 0.2,
		geographicLatitude = 28,
		atmosphere = {
			density = 0.36,
			offset = 0.3,
			color = { 238, 182, 128 },
			decay = { 186, 112, 74 },
			glare = 0.7,
			haze = 2.6,
		},
		bloom = { intensity = 1.0, size = 40, threshold = 1.0 },
		sunRays = { intensity = 0.2, spread = 0.8 },
		colorCorrection = { contrast = 0.14, saturation = 0.12, tint = { 255, 236, 214 } },
		clouds = { cover = 0.35, density = 0.4, color = { 255, 214, 176 } },
	},
	-- a northern hold in winter: a low pale sun, blue skylight, cold haze, high thin clouds
	frost = {
		clockTime = 14.2,
		brightness = 2.2,
		ambient = { 40, 48, 62 },
		outdoorAmbient = { 104, 122, 150 },
		exposure = 0.1,
		geographicLatitude = 62,
		atmosphere = {
			density = 0.38,
			offset = 0.25,
			color = { 196, 212, 230 },
			decay = { 112, 128, 156 },
			glare = 0.25,
			haze = 2.0,
		},
		bloom = { intensity = 0.6, size = 30, threshold = 1.2 },
		sunRays = { intensity = 0.08, spread = 0.6 },
		colorCorrection = { contrast = 0.1, saturation = -0.12, tint = { 232, 240, 255 } },
		clouds = { cover = 0.55, density = 0.45, color = { 232, 238, 248 } },
	},
	-- the Lands Between at golden hour: a low warm sun, thick golden haze swallowing the distance (aerial
	-- perspective is the look), strong bloom so gold and Neon glow, soft sun rays, a warm desaturated grade
	erdtree = {
		clockTime = 16.6,
		brightness = 2.8,
		ambient = { 58, 50, 44 },
		outdoorAmbient = { 138, 118, 92 },
		exposure = 0.15,
		atmosphere = {
			density = 0.42,
			offset = 0.32,
			color = { 236, 196, 140 },
			decay = { 150, 112, 82 },
			glare = 0.55,
			haze = 2.3,
		},
		bloom = { intensity = 0.9, size = 36, threshold = 1.05 },
		sunRays = { intensity = 0.16, spread = 0.75 },
		colorCorrection = { contrast = 0.12, saturation = -0.06, tint = { 255, 240, 214 } },
		clouds = { cover = 0.62, density = 0.55, color = { 255, 226, 190 } },
	},
	golden = {
		clockTime = 17.2,
		brightness = 2.5,
		ambient = { 46, 40, 48 },
		outdoorAmbient = { 125, 108, 98 },
		exposure = 0.1,
		atmosphere = {
			density = 0.35,
			offset = 0.25,
			color = { 255, 212, 172 },
			decay = { 122, 82, 72 },
			glare = 0.4,
			haze = 1.8,
		},
		bloom = { intensity = 0.6, size = 30, threshold = 1.3 },
		sunRays = { intensity = 0.12, spread = 0.6 },
		colorCorrection = { contrast = 0.08, saturation = 0.12, tint = { 255, 246, 236 } },
		clouds = { cover = 0.55, density = 0.6, color = { 255, 232, 212 } },
	},
	noon = {
		clockTime = 13,
		brightness = 3,
		ambient = { 40, 44, 52 },
		outdoorAmbient = { 128, 132, 140 },
		exposure = 0,
		atmosphere = {
			density = 0.25,
			offset = 0.2,
			color = { 199, 215, 235 },
			decay = { 106, 112, 125 },
			glare = 0.2,
			haze = 0.8,
		},
		bloom = { intensity = 0.4, size = 24, threshold = 1.5 },
		sunRays = { intensity = 0.08, spread = 0.5 },
		colorCorrection = { contrast = 0.05, saturation = 0.08, tint = { 255, 255, 255 } },
		clouds = { cover = 0.5, density = 0.55, color = { 255, 255, 255 } },
	},
	overcast = {
		clockTime = 14,
		brightness = 1.6,
		ambient = { 60, 62, 66 },
		outdoorAmbient = { 120, 122, 126 },
		exposure = 0.1,
		atmosphere = {
			density = 0.45,
			offset = 0.1,
			color = { 182, 186, 192 },
			decay = { 110, 112, 118 },
			glare = 0,
			haze = 2.5,
		},
		bloom = { intensity = 0.3, size = 24, threshold = 1.6 },
		sunRays = { intensity = 0, spread = 0.5 },
		colorCorrection = { contrast = 0.06, saturation = -0.15, tint = { 245, 248, 255 } },
		clouds = { cover = 0.9, density = 0.8, color = { 150, 152, 158 } },
	},
	storm = {
		clockTime = 16,
		brightness = 1.3,
		ambient = { 38, 42, 52 },
		outdoorAmbient = { 92, 98, 112 },
		exposure = 0.15,
		atmosphere = {
			density = 0.48,
			offset = 0.15,
			color = { 122, 132, 148 },
			decay = { 58, 64, 80 },
			glare = 0.1,
			haze = 2.8,
		},
		bloom = { intensity = 0.8, size = 34, threshold = 1.2 },
		sunRays = { intensity = 0.05, spread = 0.5 },
		colorCorrection = { contrast = 0.12, saturation = -0.22, tint = { 212, 222, 238 } },
		clouds = { cover = 0.95, density = 0.95, color = { 72, 77, 88 } },
	},
	night = {
		clockTime = 0.5,
		brightness = 1,
		ambient = { 22, 26, 42 },
		outdoorAmbient = { 44, 54, 84 },
		exposure = 0.2,
		atmosphere = {
			density = 0.3,
			offset = 0.1,
			color = { 62, 72, 102 },
			decay = { 30, 34, 52 },
			glare = 0,
			haze = 1,
		},
		bloom = { intensity = 1, size = 30, threshold = 1 },
		sunRays = { intensity = 0, spread = 0.5 },
		colorCorrection = { contrast = 0.1, saturation = -0.05, tint = { 202, 216, 255 } },
		clouds = { cover = 0.4, density = 0.5, color = { 62, 67, 82 } },
	},
	scifi_dusk = {
		clockTime = 18.3,
		brightness = 2,
		ambient = { 42, 34, 60 },
		outdoorAmbient = { 110, 92, 140 },
		exposure = 0.1,
		atmosphere = {
			density = 0.38,
			offset = 0.2,
			color = { 172, 150, 222 },
			decay = { 92, 60, 142 },
			glare = 0.5,
			haze = 2,
		},
		bloom = { intensity = 0.9, size = 32, threshold = 1.15 },
		sunRays = { intensity = 0.15, spread = 0.7 },
		colorCorrection = { contrast = 0.1, saturation = 0.2, tint = { 236, 230, 255 } },
		clouds = { cover = 0.6, density = 0.65, color = { 202, 172, 232 } },
	},
}

-- W5's five night-city presets for Roblox's Realistic lighting style (kit/lib/worldlight.luau: gothic_moonlit,
-- gothic_dusk, gothic_fog, gothic_storm, gothic_dawn) are presets like any other: "lighting": "gothic_fog"
for name, preset in WorldLight.PRESETS do
	Environment.LIGHTING[name] = preset
end
-- the lighting styles Roblox has (Lighting.LightingStyle)
Environment.STYLES = { Realistic = true, Soft = true }

local function merge(base: any, over: any): any
	if type(base) ~= "table" or type(over) ~= "table" then
		return if over ~= nil then over else base
	end
	local out = table.clone(base)
	for k, v in over do
		out[k] = merge(base[k], v)
	end
	return out
end

local function vec(v: any, n: number): boolean
	if type(v) ~= "table" or #v ~= n then
		return false
	end
	for _, x in v do
		if type(x) ~= "number" then
			return false
		end
	end
	return true
end

-- -> (environment table ready for the runtime | nil, issues)
-- a flat pad: { center: [x, z], radius, height? } (anything else is reported and never sampled)
function Environment.validPad(f: any): boolean
	return type(f) == "table"
		and type(f.center) == "table"
		and type(f.center[1]) == "number"
		and type(f.center[2]) == "number"
		and type(f.radius) == "number"
		and (f.height == nil or type(f.height) == "number")
end

-- is this what kit/world/terrain.py records of a climate it painted by (its five numbers)? An empty table, or one
-- written by hand with words missing, is no record
function Environment.climateRecord(c: any): boolean
	if type(c) ~= "table" then
		return false
	end
	for _, k in { "wind", "rain", "sea", "lapse", "shade" } do
		if type(c[k]) ~= "number" then
			return false
		end
	end
	return true
end

-- is this what kit/world/terrain.py records of an aerial picture it painted by (kit world terrain --imagery): the
-- picture's file and its box of four numbers? A word, or a table with the box missing, is no record
function Environment.imageryRecord(m: any): boolean
	if type(m) ~= "table" or type(m.file) ~= "string" or m.file == "" or type(m.bbox) ~= "table" or #m.bbox ~= 4 then
		return false
	end
	for _, v in m.bbox do
		if type(v) ~= "number" or v ~= v then
			return false
		end
	end
	return true
end

-- a land's painted roles are ONE CHARACTER A CELL (kit/world/terrain.py paint_encode: role i is string.char(48 + i),
-- "0" .. "9" then ":", ";" ... up to "~"): -> the first cell (1-based) whose character is not one of the `roles`
-- roles of the land, or nil when every cell names one
function Environment.paintOff(paint: string, roles: number): number?
	local top = 47 + roles
	for i = 1, #paint do
		local b = string.byte(paint, i)
		if b < 48 or b > top then
			return i
		end
	end
	return nil
end

-- the painter's material for each role of a painted heightmap op, before its own "paint" map (a season swaps
-- these: kit/lib/worldseason.luau)
function Environment.paintDefaults(spec: any): { [string]: string }
	return {
		meadow = spec.material or "Grass",
		lush = "LeafyGrass",
		dirt = "Ground",
		mud = "Mud",
		rock = spec.rock or "Rock",
		cliff = "Slate",
		snow = "Snow",
		sand = "Sand",
		scree = "Ground",
		river = "Water", -- (kit world rivers: the carved valleys' beds, filled)
	}
end

-- A SKY OF THE KIT'S OWN (kit world sky <Name> -> build/skies/<Name>.sky.json + six pictures; kit upload ->
-- ids.skies.<Name>.<SkyboxFt ...>): what is known of a sky by its name -> record (the .sky.json, nil = not made),
-- ids ({ SkyboxFt = id, ... }, nil = not uploaded). Replaced by the kit's own specs (no files read there).
Environment.FACES = { "SkyboxBk", "SkyboxDn", "SkyboxFt", "SkyboxLf", "SkyboxRt", "SkyboxUp" }
function Environment.readSky(name: string): (any?, any?)
	local record, ids = nil, nil
	local file = `{Config.build("skies")}/{name}.sky.json`
	if fs.isFile(file) then
		local ok, data = pcall(serde.decode, "json" :: any, fs.readFile(file))
		record = if ok and type(data) == "table" then data else false -- (false: there, and unreadable)
	end
	local ip = Config.path("ids")
	if ip and fs.isFile(ip) then
		local ok, all = pcall(serde.decode, "json" :: any, fs.readFile(ip))
		if ok and type(all) == "table" and type(all.skies) == "table" and type(all.skies[name]) == "table" then
			ids = all.skies[name]
		end
	end
	return record, ids
end

function Environment.compile(bp: any): (any?, { Issue })
	local issues: { Issue } = {}
	local function err(path: string, message: string)
		table.insert(issues, { path = path, message = message, severity = "error" })
	end
	local env: { [string]: any } = {}
	local fixedSky: string? = nil -- (the world's sky has far ridges painted in it: it is not turned to the light)
	if bp.lighting ~= nil then
		local l = bp.lighting
		local preset = if type(l) == "string" then l else (type(l) == "table" and l.preset) or nil
		local base = {}
		if preset ~= nil then
			if not Environment.LIGHTING[preset] then
				err(
					"lighting",
					`unknown preset "{tostring(preset)}" — erdtree | golden | noon | overcast | storm | night | scifi_dusk | gothic_moonlit | gothic_dusk | gothic_fog | gothic_storm | gothic_dawn`
				)
			else
				base = Environment.LIGHTING[preset]
			end
		end
		env.lighting = if type(l) == "table" then merge(base, l) else base
		env.lighting.preset = nil
		local style = env.lighting.lightingStyle
		if style ~= nil and (type(style) ~= "string" or not Environment.STYLES[style]) then
			err(
				"lighting.lightingStyle",
				`lightingStyle is "Realistic" or "Soft" (Roblox's Lighting.LightingStyle; got {tostring(style)})`
			)
		end
		local ct = env.lighting.clockTime
		if ct ~= nil and (type(ct) ~= "number" or ct < 0 or ct >= 24) then
			err("lighting.clockTime", "clockTime is 0..24 (hours)")
		end
		-- "sky": "<Name>" - six pictures of the kit's own round the world in place of Roblox's default sky
		local sky = env.lighting.sky
		if sky ~= nil then
			env.lighting.sky = nil
			if type(sky) ~= "string" or not string.match(sky, "^[%w_]+$") then
				err("lighting.sky", "sky is the name of a sky made by: lune run kit world sky <Name>")
			else
				local record, ids = Environment.readSky(sky)
				fixedSky = if type(record) == "table" and record.fixed == true then sky else nil
				local v = if type(record) == "table" and type(record.sun) == "table" then record.sun.vector else nil
				local whole = type(v) == "table" and #v == 3
				for k = 1, 3 do
					whole = whole and type(v[k]) == "number" and v[k] == v[k] and math.abs(v[k]) <= 1
				end
				if record == nil then
					err(
						"lighting.sky",
						`no sky "{sky}" - make it: lune run kit world sky {sky} --sun <elevation>,<azimuth>`
					)
				elseif
					not whole
					or math.abs(v[1] ^ 2 + v[2] ^ 2 + v[3] ^ 2 - 1) > 0.01
					or (record.fixed ~= nil and type(record.fixed) ~= "boolean")
				then
					err(
						"lighting.sky",
						`the sky "{sky}" has no record that can be read (its .sky.json is damaged, or says no sun) - make it again: lune run kit world sky {sky} --sun <elevation>,<azimuth>`
					)
				else
					local faces: { [string]: string } = {}
					local missing: { string } = {}
					for _, face in Environment.FACES do
						-- (an id is a whole number over 0, or that number as a string, bare or after rbxassetid://:
						-- nothing else is dug out of what stands there)
						local id = if type(ids) == "table" then ids[face] else nil
						local digits: string? = nil
						if type(id) == "number" and id > 0 and id % 1 == 0 and id < 2 ^ 53 then
							digits = string.format("%d", id)
						elseif type(id) == "string" then
							digits = string.match(id, "^rbxassetid://(%d+)$") or string.match(id, "^(%d+)$")
							if digits and tonumber(digits) == 0 then
								digits = nil
							end
						end
						if digits then
							faces[face] = `rbxassetid://{digits}`
						else
							table.insert(missing, face)
						end
					end
					if #missing > 0 then
						-- (a picture is in a game only when it is uploaded: said, and Roblox's own sky stays)
						table.insert(issues, {
							path = "lighting.sky",
							message = `the sky "{sky}" is not uploaded ({#missing} of 6 pictures have no id: {table.concat(
								missing,
								", "
							)}): Roblox shows its own default sky until its six pictures are uploaded and their ids stand in the project's ids file as skies.{sky}.SkyboxFt ... (kit upload does not take skies yet)`,
							severity = "warn",
						})
					else
						env.lighting.sky = {
							name = sky,
							faces = faces,
							sun = { record.sun.vector[1], record.sun.vector[2], record.sun.vector[3] },
							-- (a sky with far ridges painted in it is not turned to the light in the game: mountains
							-- do not wheel round the horizon with the hour - kit world sky --ridges, SkyRules.drawn)
							fixed = if record.fixed == true then true else nil,
						}
					end
				end
			end
		end
	end
	-- the TIME OF DAY (AAA gap W9): { length = seconds per day, start = hour, keys = { { hour, preset? | lighting
	-- fields }, ... } } - a key may name a lighting preset; resolved here, sorted by hour, each preset's own clockTime
	-- dropped (the clock runs the hour: kit WorldClock)
	if bp.day ~= nil then
		local d = bp.day
		if fixedSky then -- (said whether or not the sky is uploaded yet)
			table.insert(issues, {
				path = "lighting.sky",
				message = `the sky "{fixedSky}" has far ridges painted in it and is not turned to the light: through the day its drawn sun stays where it was rendered while the world's light moves (a sky without --ridges is turned with the clock)`,
				severity = "warn",
			})
		end
		if type(d) ~= "table" or type(d.keys) ~= "table" or #d.keys == 0 then
			err("day", 'day needs "keys": [{ "hour": 6, "preset": "golden" }, ...]')
		else
			local keys = {}
			for i, k in d.keys do
				if type(k) ~= "table" or type(k.hour) ~= "number" or k.hour < 0 or k.hour >= 24 then
					err(`day.keys[{i}]`, "each key needs an hour 0..24")
					continue
				end
				if k.sky ~= nil then
					err(`day.keys[{i}].sky`, "a world has one sky (lighting.sky): a key of the day cannot change it")
					continue
				end
				local base = {}
				if k.preset ~= nil then
					if not Environment.LIGHTING[k.preset] then
						err(`day.keys[{i}].preset`, `unknown preset "{tostring(k.preset)}"`)
					else
						base = Environment.LIGHTING[k.preset]
					end
				end
				local key = merge(base, k)
				key.preset, key.clockTime = nil, nil
				table.insert(keys, key)
			end
			table.sort(keys, function(a, b)
				return a.hour < b.hour
			end)
			if type(d.length) ~= "nil" and (type(d.length) ~= "number" or d.length < 60) then
				err("day.length", "length is the seconds of one day (>= 60)")
			end
			env.day = { length = d.length or 1200, start = d.start or 9, keys = keys }
		end
	end
	-- ONE WIND (AAA gap W8): { direction = degrees (0 = +Z), speed = [low, high] studs/s, period = s } -> GlobalWind
	if bp.wind ~= nil then
		local w = bp.wind
		if
			type(w) ~= "table"
			or type(w.speed) ~= "table"
			or type(w.speed[1]) ~= "number"
			or type(w.speed[2]) ~= "number"
			or w.speed[1] < 0
			or w.speed[2] < w.speed[1]
		then
			err("wind", 'wind needs "speed": [low, high] studs/s (0 <= low <= high)')
		else
			env.wind = { direction = w.direction or 0, speed = w.speed, period = w.period or 40 }
		end
	end
	if bp.terrain ~= nil then
		if type(bp.terrain) ~= "table" then
			err("terrain", "terrain is a list of ops: ground | heightmap | block | ball | cylinder | water")
			return env, issues
		end
		env.terrain = {}
		local cells = 0
		local backdropCells = 0
		local sdfAt: number? = nil -- (the first sdf op's place in the list)
		local sdfCells = 0
		for i, op in bp.terrain do
			local path = `terrain[{i}]`
			local kind, spec = next(op)
			-- (the game writes the ops in the order they are listed: a ground written after an sdf fills its
			-- caves again and wipes what it built near the ground. kit world check fills the ground first)
			if sdfAt and (kind == "ground" or kind == "heightmap") then
				err(
					path,
					`a {kind} op after an "sdf" op (terrain[{sdfAt}]): the game writes them in order and the ground would fill the caves again - list the sdf after the ground`
				)
			end
			if type(spec) ~= "table" then
				err(path, "each op is { kind: {...} } — ground | block | ball | cylinder | water")
				continue
			end
			local mat = spec.material or (if kind == "water" then "Water" else nil)
			if kind ~= "water" and not Environment.MATERIALS[mat] then
				err(
					path .. ".material",
					`terrain material "{tostring(mat)}" — Grass, Ground, Rock, Sand, Mud, Snow, Basalt, ...`
				)
			end
			if kind == "ground" then
				if not vec(spec.center, 3) or not vec(spec.size, 2) then
					err(path, "ground needs center [x, y, z] (y = surface height) and size [w, d]")
					continue
				end
				if spec.size[1] > 2048 or spec.size[2] > 2048 then
					err(path .. ".size", "ground is at most 2048 x 2048 studs")
				end
				if spec.under ~= nil and not Environment.MATERIALS[spec.under] then
					err(path .. ".under", `unknown terrain material "{tostring(spec.under)}"`)
				end
				for j, patch in spec.patches or {} do
					if not Environment.MATERIALS[patch.material] then
						err(`{path}.patches[{j}]`, `unknown terrain material "{tostring(patch.material)}"`)
					end
				end
				if spec.flat ~= nil and type(spec.flat) ~= "table" then
					err(`{path}.flat`, "flat is a list of pads: [{ center: [x, z], radius, height? }]")
				end
				for j, f in if type(spec.flat) == "table" then spec.flat else {} do
					if not Environment.validPad(f) then
						err(`{path}.flat[{j}]`, "a flat pad is { center: [x, z], radius, height? }")
					end
				end
				cells += (spec.size[1] / 4) * (spec.size[2] / 4)
			elseif kind == "heightmap" then
				local pads = {} -- (a pad without a centre crashed the compiler in groundHeight: reported, never used)
				if spec.flat ~= nil and type(spec.flat) ~= "table" then
					err(`{path}.flat`, "flat is a list of pads: [{ center: [x, z], radius, height? }]")
				end
				for j, f in if type(spec.flat) == "table" then spec.flat else {} do
					if not Environment.validPad(f) then
						err(`{path}.flat[{j}]`, "a flat pad is { center: [x, z], radius, height? }")
					else
						table.insert(pads, f)
					end
				end
				-- a heightmap made by `kit world terrain` (kit/world/terrain.py: noise / a picture + erosion) becomes a
				-- GROUND op with samples: the runtime, kit world check and kit world look all read the same heights
				if not vec(spec.center, 3) or not vec(spec.size, 2) or type(spec.source) ~= "string" then
					err(path, 'heightmap needs center [x, y, z], size [w, d] and "source": "<file>.hm.json"')
					continue
				end
				local okRead, raw = pcall(fs.readFile, Config.resolve(spec.source))
				local okJson, hm = false, nil
				if okRead then
					okJson, hm = pcall(serde.decode, "json" :: any, raw)
				end
				if
					not okJson
					or type(hm) ~= "table"
					or type(hm.heights) ~= "table"
					or #hm.heights ~= (hm.nx or 0) * (hm.nz or 0)
				then
					err(
						path .. ".source",
						`{spec.source}: not a heightmap (make one: lune run kit world terrain <Name>)`
					)
					continue
				end
				if spec.rock ~= nil and not Environment.MATERIALS[spec.rock] then
					err(path .. ".rock", `unknown terrain material "{tostring(spec.rock)}"`)
				end
				-- material layers, later ones win: { material, minHeight?, maxHeight?, minSlope?, maxSlope? }
				-- (heights above the op's centre, slopes in degrees): mud in the hollows, ash on the heights...
				for j, l in spec.layers or {} do
					if type(l) ~= "table" or not Environment.MATERIALS[l.material] then
						err(
							`{path}.layers[{j}]`,
							`a layer needs a terrain material (got {tostring(type(l) == "table" and l.material)})`
						)
					end
				end
				-- the painted surface (kit world terrain: what the erosion says each cell is made of) -> a material per
				-- role; "paint": { "<role>": "<Material>" } remaps, "paint": false turns it off (then layers + rock)
				local splat, palette = nil, nil
				-- (an op that already paints with "layers" keeps them unless it asks for the painter: "paint": true)
				local wantPaint = spec.paint ~= false and (spec.paint ~= nil or spec.layers == nil)
				if
					wantPaint
					and type(hm.paint) == "string"
					and type(hm.roles) == "table"
					and (#hm.paint ~= hm.nx * hm.nz or Environment.paintOff(hm.paint, #hm.roles) ~= nil)
				then
					err(
						`{path}.source`,
						`{spec.source}: its paint is not one role per cell — re-run kit world terrain`
					)
					wantPaint = false
				end
				if wantPaint and type(hm.paint) == "string" and type(hm.roles) == "table" then
					local defaults = Environment.paintDefaults(spec)
					palette = {}
					for j, role in hm.roles do
						local m = (type(spec.paint) == "table" and spec.paint[role]) or defaults[role] or "Grass"
						if not Environment.MATERIALS[m] then
							err(`{path}.paint.{role}`, `unknown terrain material "{tostring(m)}"`)
							m = "Grass"
						end
						palette[j] = m
					end
					splat = hm.paint
				end
				if spec.climate ~= nil and spec.climate ~= false then
					err(
						`{path}.climate`,
						`a land's climate is made with the land (lune run kit world terrain <Name> --climate "wind=270,rain=0.6,sea=0.8"): here the op says only "climate": false (painted without one, meant)`
					)
				end
				if spec.backdrop then -- scenery land: its own allowance (the runtime writes only its surface band)
					backdropCells += (spec.size[1] / 4) * (spec.size[2] / 4)
				else
					cells += (spec.size[1] / 4) * (spec.size[2] / 4)
				end
				table.insert(env.terrain, {
					kind = "ground",
					spec = {
						center = spec.center,
						size = spec.size,
						material = spec.material,
						under = spec.under,
						rock = spec.rock,
						rockSlope = spec.rockSlope or 38,
						layers = spec.layers,
						flat = pads,
						backdrop = spec.backdrop, -- scenery land (far mountains): kit world check skips it
						-- a PAINTED land's climate (kit/world/terrain.py --climate: biomes by moisture and temperature):
						-- true = the painter read one; false = the op says none was meant; nil = unsaid (the build's
						-- lock asks: kit/lib/lanelocks.luau LaneLocks.unsaidClimates)
						source = spec.source,
						-- (painted by an aerial picture of the place - kit world terrain --imagery - is an answer too:
						-- what covers the land was read off the land itself)
						climate = if splat == nil
							then nil
							elseif Environment.climateRecord(hm.climate) then true
							elseif Environment.imageryRecord(hm.imagery) then true
							elseif spec.climate == false then false
							else nil,
						-- columns are solid down to this Y (default: the backdrop's base, set below): a map whose
						-- edges stand above a lower far ring is not a slab over a void
						floor = spec.floor,
						samples = {
							nx = hm.nx,
							nz = hm.nz,
							heights = hm.heights,
							splat = splat,
							palette = palette,
							-- the painted ROLE names per splat digit (generators read them: forest / scatter "roles")
							roles = if splat then hm.roles else nil,
						},
					},
				})
				continue
			elseif kind == "block" or kind == "water" then
				if not vec(spec.center, 3) or not vec(spec.size, 3) then
					err(path, `{kind} needs center [x, y, z] and size [x, y, z]`)
				end
			elseif kind == "ball" then
				if not vec(spec.center, 3) or type(spec.radius) ~= "number" then
					err(path, "ball needs center [x, y, z] and radius")
				end
			elseif kind == "cylinder" then
				if not vec(spec.center, 3) or type(spec.radius) ~= "number" or type(spec.height) ~= "number" then
					err(path, "cylinder needs center [x, y, z], radius and height")
				end
			elseif kind == "sdf" then
				-- LAND AS A SIGNED DISTANCE (src/kit/SdfRules.luau): caves, overhangs, arches - shapes joined and
				-- cut out of each other, and out of the land that was there
				local wrong = Sdf.problems(spec)
				for _, p in wrong do
					err(path, p)
				end
				if #wrong > 0 then
					continue
				end
				sdfAt = sdfAt or i
				sdfCells += Sdf.cells(spec)
			else
				err(
					path,
					`unknown terrain op "{tostring(kind)}" — ground | heightmap | block | ball | cylinder | sdf | water`
				)
				continue
			end
			table.insert(env.terrain, { kind = kind, spec = spec })
		end
		if sdfCells > Sdf.CELLS * 3 then
			err(
				"terrain",
				`{sdfCells} cells of "sdf" ops in all - keep it under {Sdf.CELLS * 3} (the game writes them all when the place starts: about a second and three quarters a 400,000 cells, measured)`
			)
		end
		if cells > 250000 then
			err("terrain", `{math.floor(cells)} ground columns — keep it under 250k (about 2000 x 2000 studs)`)
		end
		if backdropCells > 270000 then
			err(
				"terrain",
				`{math.floor(backdropCells)} backdrop ground columns — keep it under 270k (one 2048 x 2048 ring)`
			)
		end
	end
	-- terrain material colours (Terrain:SetMaterialColor) and the water's look: the world's palette on the terrain
	if bp.terrainColors ~= nil then
		if type(bp.terrainColors) ~= "table" then
			err("terrainColors", "terrainColors is { Grass: [r, g, b], Rock: [...] }")
		else
			for m, c in bp.terrainColors do
				if not Environment.MATERIALS[m] then
					err(`terrainColors.{m}`, `unknown terrain material "{m}"`)
				elseif not vec(c, 3) then
					err(`terrainColors.{m}`, "a colour is [r, g, b] 0..255")
				end
			end
			env.terrainColors = bp.terrainColors
		end
	end
	if bp.water ~= nil then
		if type(bp.water) ~= "table" then
			err("water", "water is { color: [r, g, b], transparency, waveSize, waveSpeed, reflectance }")
		else
			env.water = bp.water
		end
	end
	-- a playable ground over a lower far ring: its columns reach down to the ring's base, so no hollow opens under
	-- the map's edges (each tile used to stop `depth` under its own lowest point: a 24-stud slab over a void)
	if env.terrain then
		local base: number? = nil
		for _, op in env.terrain do
			if op.kind == "ground" and op.spec.backdrop and op.spec.center then
				base = math.min(base or math.huge, op.spec.center[2])
			end
		end
		if base then
			for _, op in env.terrain do
				if op.kind == "ground" and not op.spec.backdrop and op.spec.floor == nil then
					op.spec.floor = base
				end
			end
		end
	end
	if next(env) == nil then
		return nil, issues
	end
	return env, issues
end

return Environment

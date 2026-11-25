-- calib_states.luau - the Lighting states the Roblox-look rig is fitted to (kit/tools/studio_calibrate.py): run ONCE
-- per batch through the Studio tools (Edit, a kit scratch place, never saved) with the calibration sphere stood by its
-- load.luau and `studio_calibrate.py watch` running. For each state it sets Lighting (everything else held at a plain
-- base: no sky light, no colour shift, no exposure), lets the light land, and runs the sphere's shot.luau from a camera
-- at right angles to the sun (the lit half and the shaded half both in view), waiting out its on-screen walk.
-- Lighting is put back as it was at the end. Returns a JSON list: each state's name and the look its shot read.
local given = (... :: any) or {}
local BASE_URL: string = given.base -- the calibration sphere's server (its shot.luau)
local STATES: { { name: string, set: { [string]: any } } } = given.states
local WALK = 10.5 -- s: a shot's on-screen walk (model_shot.luau: 1 + 3 + 1 + 3 + 1, and a margin)

local Http = game:GetService("HttpService")
local L = game:GetService("Lighting")
local KEYS = {
	"Brightness",
	"ClockTime",
	"ExposureCompensation",
	"EnvironmentDiffuseScale",
	"EnvironmentSpecularScale",
	"ShadowSoftness",
	"Ambient",
	"OutdoorAmbient",
	"ColorShift_Top",
	"ColorShift_Bottom",
}
local BASE = {
	Brightness = 0,
	ClockTime = 14,
	ExposureCompensation = 0,
	EnvironmentDiffuseScale = 0,
	EnvironmentSpecularScale = 0,
	ShadowSoftness = 0.5,
	Ambient = Color3.new(0, 0, 0),
	OutdoorAmbient = Color3.new(0, 0, 0),
	ColorShift_Top = Color3.new(0, 0, 0),
	ColorShift_Bottom = Color3.new(0, 0, 0),
}
local was = {}
for _, k in KEYS do
	was[k] = (L :: any)[k]
end
local shot = loadstring(Http:GetAsync(BASE_URL .. "/shot.luau", true)) :: any
local out = {}
local ok, err = pcall(function()
	for _, state in STATES do
		for _, k in KEYS do
			local v = state.set[k]
			if v == nil then
				v = BASE[k]
			elseif type(v) == "table" then
				v = Color3.fromRGB(v[1], v[2], v[3])
			end
			(L :: any)[k] = v
		end
		task.wait(1.5) -- (the light lands over a few frames)
		-- the camera at right angles to the sun, level with the sphere's middle
		local sun = L:GetSunDirection()
		local flat = Vector3.new(sun.X, 0, sun.Z)
		flat = if flat.Magnitude > 1e-3 then flat.Unit else Vector3.new(1, 0, 0)
		local side = Vector3.new(-flat.Z, 0, flat.X)
		local look = shot({ eye = side * 7 + Vector3.new(0, 1, 0), target = Vector3.zero })
		table.insert(out, { name = state.name, look = Http:JSONDecode(look) })
		task.wait(WALK)
	end
end)
for _, k in KEYS do
	(L :: any)[k] = was[k]
end
if not ok then
	return `FAILED: {err}`
end
return Http:JSONEncode(out)

-- model_shot.luau - one SHOT of a model kit/studio/model_load.luau stood in a kit scratch place (kit/tools/studio_model.py
-- shot_script writes a copy with its settings; a session runs it ONCE through the Studio tools, Edit, while
-- `python kit/tools/studio_model.py shot --match <place> <dir>` watches the window; nothing is saved).
--
-- It puts the camera where it is told, returns at once what Roblox's Lighting IS (the values kit/blender/rbx_lookdev
-- light_rig takes, the sun and moon directions, the camera, where the model stands) - the session saves that line as
-- <dir>/look.json - and then, in the background, says each step ON SCREEN (the script cannot call out to the
-- watcher): MAGENTA over the whole 3D view (where the view is), the view with the model (held), CYAN, the view with
-- the model taken away (held: what is behind it, so the watcher can tell the model's own pixels), YELLOW (the end);
-- the model is put back and the cover removed.
-- (every setting pack fills is inside a STRING: a formatter leaves a string's text alone)
local given = (... :: any) or {}
local function numbers(text: string): { number }
	local out = {}
	for _, x in string.split(text, ",") do
		table.insert(out, tonumber(x) :: number)
	end
	return out
end
local TAG = given.tag or "{{TAG}}"
local EYE: Vector3 = given.eye or Vector3.new(table.unpack(numbers("{{EYE}}"))) -- (from the model's origin, studs)
local TARGET: Vector3 = given.target or Vector3.new(table.unpack(numbers("{{TARGET}}")))
local FOV: number = given.fov or tonumber("{{FOV}}") :: number
local HOLD, FLASH = tonumber("{{HOLD}}") :: number, tonumber("{{FLASH}}") :: number

local model = workspace:FindFirstChild(TAG)
if not model then
	return `REFUSED: no {TAG} in Workspace (run its load.luau first)`
end
local origin = model:GetAttribute("KitStudioAt")
local place: CFrame = if typeof(origin) == "CFrame" then origin else CFrame.identity
-- the eye and target are in the MODEL's frame (a model stood turned is shot from its own front)
local CAMERA = CFrame.lookAt(place * EYE, place * TARGET, place.UpVector)
local L = game:GetService("Lighting")
local cam = workspace.CurrentCamera
cam.CameraType = Enum.CameraType.Scriptable
cam.FieldOfView = FOV
cam.CFrame = CAMERA
pcall(function()
	game:GetService("Selection"):Set({})
end)
local function c3(c: Color3)
	return { math.round(c.R * 255), math.round(c.G * 255), math.round(c.B * 255) }
end
local function v3(v: Vector3)
	return { v.X, v.Y, v.Z }
end
local kids = {}
for _, k in L:GetChildren() do
	table.insert(kids, k.ClassName)
end
local look = {
	model = model:GetAttribute("KitStudioModel"),
	Brightness = L.Brightness,
	ClockTime = L.ClockTime,
	ExposureCompensation = L.ExposureCompensation,
	EnvironmentDiffuseScale = L.EnvironmentDiffuseScale,
	EnvironmentSpecularScale = L.EnvironmentSpecularScale,
	ShadowSoftness = L.ShadowSoftness,
	Ambient = c3(L.Ambient),
	OutdoorAmbient = c3(L.OutdoorAmbient),
	ColorShift_Top = c3(L.ColorShift_Top),
	ColorShift_Bottom = c3(L.ColorShift_Bottom),
	-- the sun and moon in the MODEL's frame too (the twin lights the model unturned; a model turned about up is lit
	-- from the same side as in Studio - one tipped off upright is not: the sky's gradient stays the world's)
	SunDirection = v3(place:VectorToObjectSpace(L:GetSunDirection())),
	MoonDirection = v3(place:VectorToObjectSpace(L:GetMoonDirection())),
	lighting_children = kids,
	-- the camera in the MODEL's frame (the twin renders the model at its own origin, unturned)
	camera = {
		space = "model",
		position = v3(place:PointToObjectSpace(CAMERA.Position)),
		look = v3(place:VectorToObjectSpace(CAMERA.LookVector)),
		up = v3(place:VectorToObjectSpace(CAMERA.UpVector)),
		fov = FOV,
		viewport = { cam.ViewportSize.X, cam.ViewportSize.Y },
	},
	at = v3(place.Position),
}
task.spawn(function()
	local CG = game:GetService("CoreGui")
	local old = CG:FindFirstChild("KitStudioModelShot")
	if old then
		old:Destroy()
	end
	local gui = Instance.new("ScreenGui")
	gui.Name, gui.DisplayOrder, gui.IgnoreGuiInset = "KitStudioModelShot", 2147483647, true
	local cover = Instance.new("Frame")
	cover.Size, cover.BorderSizePixel = UDim2.fromScale(1, 1), 0
	cover.Parent = gui
	local parent = model.Parent
	local ok, err = pcall(function()
		gui.Parent = CG
		local function flash(colour: Color3)
			cover.BackgroundColor3 = colour
			cover.Visible = true
			task.wait(FLASH)
			cover.Visible = false
		end
		flash(Color3.fromRGB(255, 0, 255))
		task.wait(HOLD)
		flash(Color3.fromRGB(0, 255, 255))
		model.Parent = nil
		task.wait(HOLD)
		flash(Color3.fromRGB(255, 255, 0))
	end)
	model.Parent = parent
	gui:Destroy()
	if not ok then
		warn(`[model_shot] {err}`)
	end
end)
return game:GetService("HttpService"):JSONEncode(look)

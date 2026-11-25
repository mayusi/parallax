-- UiMotion.client.luau (kit) — plays the motion of every kit screen: hover / press / loop attributes on each node,
-- the spec's per-viewport scale and the ENTER choreography (delays, container stagger) of each ScreenGui the
-- moment it is enabled. Nothing to call; see ReplicatedStorage.kit.Ui.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Ui = require(ReplicatedStorage:WaitForChild("kit"):WaitForChild("Ui"))

local gui = Players.LocalPlayer:WaitForChild("PlayerGui")
Ui.clientBound = true -- (this script owns the enters of every kit screen the moment it is enabled: Ui.show defers)

local function bindScreen(screen: ScreenGui)
	screen:SetAttribute("Kit_Bound", true) -- (Ui.show leaves the enters to this script: they play once)
	for _, d in screen:GetDescendants() do
		Ui.bind(d)
	end
	screen.DescendantAdded:Connect(function(d)
		task.defer(Ui.bind, d) -- attributes are set right after the instance appears
	end)
	Ui.gamepad(screen) -- (focus piece, d-pad neighbours, firstFocus, pad glyphs)
	if screen.Enabled then
		-- (already on: its art first, up to 3 s, so it does not pop in piece by piece as assets stream)
		task.spawn(function()
			Ui.preload(screen, 3)
			Ui.scale(screen)
			Ui.reveal(screen)
		end)
	else
		task.spawn(Ui.preload, screen) -- (off: fetched in the background, ready when it is shown)
	end
	screen:GetPropertyChangedSignal("Enabled"):Connect(function()
		if screen.Enabled then
			Ui.scale(screen)
			Ui.reveal(screen)
		end
		Ui.backdrop(screen, screen.Enabled) -- (a menu with a "backdrop" blurs the world while it is open)
	end)
	if screen.Enabled then
		Ui.backdrop(screen, true)
	end
	local camera = workspace.CurrentCamera
	if camera then
		local sized = camera:GetPropertyChangedSignal("ViewportSize"):Connect(function()
			if screen.Enabled then
				Ui.scale(screen)
			end
		end)
		screen.Destroying:Once(function()
			sized:Disconnect()
		end)
	end
end

for _, s in gui:GetChildren() do
	if s:IsA("ScreenGui") and s:GetAttribute("Kit_Kind") ~= nil then
		bindScreen(s)
	end
end
gui.ChildAdded:Connect(function(s)
	if s:IsA("ScreenGui") then
		local screen: ScreenGui = s
		task.defer(function()
			if screen:GetAttribute("Kit_Kind") ~= nil then
				bindScreen(screen)
			end
		end)
	end
end)

-- VfxClient.client.luau (kit) — plays VFX the server broadcasts (Vfx.broadcast). Cosmetic only.
-- The event carries the server's clock: one that arrives late starts that far in, one whose effect is already over
-- is not played (VfxNet.phase: the rule).
-- The server makes the remote on its FIRST broadcast (Vfx.luau), so a place that never plays an effect has none:
-- the client listens for it to appear instead of waiting on it (an endless WaitForChild is a console error in every
-- playtest of a game without effects - Phase 0, 2026-11-17).
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local Vfx = require(ReplicatedStorage:WaitForChild("kit"):WaitForChild("Vfx"))
local VfxNet = require(ReplicatedStorage:WaitForChild("kit"):WaitForChild("VfxNet"))

local function onEvent(name: unknown, where: unknown, scale: unknown, target: unknown, sent: unknown)
	if type(name) ~= "string" or not Vfx.has(name) then
		return
	end
	local kind = typeof(where)
	if kind ~= "Vector3" and kind ~= "CFrame" then
		return
	end
	local s = if type(scale) == "number" then math.clamp(scale, 0.1, 10) else 1
	local t = if typeof(target) == "Vector3" then target :: Vector3 else nil
	local what, late = VfxNet.phase(sent, Workspace:GetServerTimeNow(), Vfx.realLengthOf(name))
	if what == "drop" then
		return -- it is over: playing it now would show it after what it belonged to
	end
	Vfx.play(name, where :: any, s, nil, t, if what == "late" then late else nil)
end

local watch: RBXScriptConnection? = nil
local function hook(child: Instance)
	if child.Name ~= Vfx.REMOTE_NAME or not child:IsA("RemoteEvent") then
		return
	end
	if watch then
		watch:Disconnect() -- (found: stop listening)
		watch = nil
	end
	local remote = child :: RemoteEvent
	remote.OnClientEvent:Connect(onEvent)
end

local found = ReplicatedStorage:FindFirstChild(Vfx.REMOTE_NAME)
if found and found:IsA("RemoteEvent") then
	hook(found)
else
	watch = ReplicatedStorage.ChildAdded:Connect(hook)
end

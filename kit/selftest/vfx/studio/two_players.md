# Two observers, a cold start, a server-made preset: ONE Studio session, a local server with two players (F-R03, F-R08)

Studio can start a local server with two player windows from a script: `StudioTestService:ExecuteMultiplayerTestAsync(2, args)`
(run in the Edit datamodel; it returns what the server gives `StudioTestService:EndTest(...)`). So the whole proof is
three scripts put into the kit's own scratch place (`build/vfx/studio/scratch.project.json`, never a game's place;
nothing saved, nothing uploaded) and one call. Run 2026-11-15, twice, with the same answers (below).

What it proves: who of TWO players is sent a broadcast; one who walks into reach while it lasts; a preset the SERVER
makes after both joined; an impact asked for on a client's first frame (before the kit has replicated); where an
effect stands against a RUNNING attacker on their own screen and on the other player's.
What it does not: real network delay (a local server has none), more than two players, a phone.

## 1. In Edit: put the three scripts in (once)

```lua
local RS = game:GetService("ReplicatedStorage")
local RF = game:GetService("ReplicatedFirst")
local SSS = game:GetService("ServerScriptService")
local SPS = game:GetService("StarterPlayer").StarterPlayerScripts
for _, p in { RS, RF, SSS, SPS } do
	for _, c in p:GetChildren() do
		if c.Name:sub(1, 8) == "KitProbe" then c:Destroy() end
	end
end
local ev = Instance.new("RemoteEvent"); ev.Name = "KitProbe"; ev.Parent = RS

-- COLD START: an impact asked for from a client's first frame (a copy of VfxImpact in ReplicatedFirst)
local first = Instance.new("LocalScript"); first.Name = "KitProbeFirst"
local imp = RS.kit.VfxImpact:Clone(); imp.Name = "VfxImpact"; imp.Parent = first
first.Source = [[
local RS = game:GetService("ReplicatedStorage")
local t0 = os.clock()
local VfxImpact = require(script.VfxImpact)
VfxImpact.configure({ preset = "black_flash" }) -- (a version 3 preset with no mesh layer)
VfxImpact.RETRY_EVERY = 0.05
local out = { kitThere = RS:FindFirstChild("kit") ~= nil, presetsThere = RS:FindFirstChild("VfxPresets") ~= nil }
out.firstReady = VfxImpact.ready()
out.firstPlay = VfxImpact.play("Stone", Vector3.new(0, 3, 0), Vector3.yAxis)
while not VfxImpact.ready() and os.clock() - t0 < 60 do task.wait() end
out.readyAfter = os.clock() - t0
local cam = workspace.CurrentCamera
local at = if cam then cam.CFrame.Position + cam.CFrame.LookVector * 20 else Vector3.new(0, 3, 0)
out.playWhenReady = VfxImpact.play("Stone", at, Vector3.yAxis)
RS:WaitForChild("KitProbe"):FireServer("cold", out)
]]
first.Parent = RF

-- EVERY CLIENT: what arrives, how late, whether it built anything, where it stands against the attacker
local client = Instance.new("LocalScript"); client.Name = "KitProbeClient"
client.Source = [[
local RS = game:GetService("ReplicatedStorage")
local Players = game:GetService("Players")
local probe = RS:WaitForChild("KitProbe")
local Vfx = require(RS:WaitForChild("kit"):WaitForChild("Vfx"))
local remote = RS:WaitForChild(Vfx.REMOTE_NAME)
local function things()
	local n = 0
	for _, d in workspace:GetDescendants() do
		if d:IsA("MeshPart") or d:IsA("ParticleEmitter") or d:IsA("Beam") or d:IsA("PointLight") then n += 1 end
	end
	return n
end
remote.OnClientEvent:Connect(function(name, where, _scale, _target, sent)
	local out = { name = name, late = workspace:GetServerTimeNow() - (sent or 0), has = Vfx.has(name), before = things() }
	local a = Players:GetPlayerByUserId(workspace:GetAttribute("KitProbeA") or 0)
	local root = a and a.Character and a.Character:FindFirstChild("HumanoidRootPart")
	local pos = if typeof(where) == "CFrame" then where.Position else where
	if root and typeof(pos) == "Vector3" then
		out.dz = pos.Z - root.Position.Z -- (the attacker runs along +Z: under 0 = the effect is BEHIND them here)
	end
	local t0, most, firstAt = os.clock(), out.before, nil
	while os.clock() - t0 < 1.5 do
		local n = things()
		if n > out.before and not firstAt then firstAt = os.clock() - t0 end
		most = math.max(most, n)
		task.wait(0.03)
	end
	out.after, out.firstAt = most, firstAt
	probe:FireServer("got", out)
end)
probe:FireServer("listening", {})
]]
client.Parent = SPS

-- THE SERVER: places the two players, broadcasts, gathers what the clients say, ends the test with it
local server = Instance.new("Script"); server.Name = "KitProbeServer"
server.Source = [[
local RS = game:GetService("ReplicatedStorage")
local Players = game:GetService("Players")
local STS = game:GetService("StudioTestService")
local args = STS:GetTestArgs()
if type(args) ~= "table" or not args.probe then return end
local Vfx = require(RS.kit.Vfx)
local NAME = "getsuga_tensho_v2" -- 3.6 s; its rule reach is under 1000 studs
local out = { reports = {}, sent = {}, cold = {} }
local label, listening = "boot", {}
RS.KitProbe.OnServerEvent:Connect(function(player, what, data)
	if what == "listening" then listening[player] = true return end
	if what == "cold" then out.cold[player.Name] = data return end
	data.who = player.Name; data.label = label -- (a report comes 1.5 s after its event: read `name` and `late` too)
	table.insert(out.reports, data)
end)
local ok, why = pcall(function()
	local t0 = os.clock()
	while #Players:GetPlayers() < 2 and os.clock() - t0 < 90 do task.wait(0.2) end
	local ps = Players:GetPlayers()
	assert(#ps >= 2, "two players never joined")
	local A, B = ps[1], ps[2]
	out.A, out.B = A.Name, B.Name
	workspace:SetAttribute("KitProbeA", A.UserId)
	local roots = {}
	for _, p in { A, B } do
		roots[p] = (p.Character or p.CharacterAdded:Wait()):WaitForChild("HumanoidRootPart")
	end
	while not (listening[A] and listening[B]) and os.clock() - t0 < 120 do task.wait(0.2) end
	task.wait(2)
	local function stand(p, x, z)
		roots[p].Anchored = true
		roots[p].Parent:PivotTo(CFrame.new(x, 5, z or 0))
	end
	local L, O = Vfx.realLengthOf(NAME), Vector3.new(0, 3, 0)
	label = "1 A near, B far"
	stand(A, 40); stand(B, 5000); task.wait(0.5)
	out.sent[label] = Vfx.broadcast(NAME, O)
	task.wait(1.0)
	label = "2 B walks in 1.0 s later"
	stand(B, 40, 20)
	task.wait(L + 0.8)
	label = "3 both near"
	out.sent[label] = Vfx.broadcast(NAME, O)
	task.wait(L + 0.8)
	label = "4 both far, reach = false"
	stand(A, 5000); stand(B, 5200); task.wait(0.5)
	out.sent[label] = Vfx.broadcast(NAME, O, 1, nil, { reach = false })
	task.wait(L + 0.8)
	label = "5 both far, the rule"
	out.sent[label] = Vfx.broadcast(NAME, O)
	task.wait(L + 0.8)
	label = "6 a preset made on the server just now"
	stand(A, 40); stand(B, 40, 20); task.wait(0.5)
	local late = RS.VfxPresets[NAME]:Clone(); late.Name = "kitprobe_late"; late.Parent = RS.VfxPresets
	out.sent[label] = Vfx.broadcast("kitprobe_late", O)
	task.wait(L + 0.8)
	label = "7 the attacker runs"
	stand(B, 40, 60)
	roots[A].Parent:PivotTo(CFrame.new(60, 5, -150)); roots[A].Anchored = false
	task.wait(0.5)
	roots[A].Parent:FindFirstChildOfClass("Humanoid"):MoveTo(Vector3.new(60, 3, 400))
	task.wait(2.0)
	out.serverSpeed = roots[A].AssemblyLinearVelocity.Magnitude
	out.sent[label] = Vfx.broadcast(NAME, roots[A].Position)
	task.wait(L + 0.8)
end)
out.ok, out.why = ok, (not ok) and tostring(why) or nil
STS:EndTest(game:GetService("HttpService"):JSONEncode(out))
]]
server.Parent = SSS
return "scripts in"
```

## 2. In Edit: start it (it takes about a minute; ask for `shared.kitTwo` afterwards)

```lua
shared.kitTwo = nil
task.spawn(function()
	local sts = game:GetService("StudioTestService")
	shared.kitTwo = { pcall(function() return sts:ExecuteMultiplayerTestAsync(2, { probe = true }) end) }
end)
return "started"
```

## What must come back (and what came back, 2026-11-15, both runs)

- `sent`: 1 (one near, one far), 2 (both near), 2 (`reach = false`), **0** (both far, by the rule), 2 (the server-made
  preset), 2 (the attacker runs). As measured.
- The far player gets NOTHING at the first send; moved into reach 1.0 s later it gets ONE event, late by 1.0 to 1.7 s
  (measured 1.59 and 1.40 s), and builds something soon after (0.16 s; 23 things, against about 45 for a whole play:
  only what is left of the effect). The near player gets exactly one event for that broadcast.
- Both near: both get it (0.06 to 0.2 s after the send on a local server) and both build (first thing 0.07 to 0.15 s).
- The server-made preset: `has = true` on both clients and both build it.
- `cold`, each client: `kitThere = false`, `firstReady = false`, `firstPlay = false` on the first frame; ready after
  0.88 to 1.14 s; `playWhenReady = true`.
- The attacker runs (16 studs a second; the effect is sent to where the SERVER has them): on the attacker's own
  screen the effect stands 4.1 studs behind them (`dz` -4.12, -4.06), on the other player's 1.0 to 1.2 studs behind
  (-1.19, -0.99). With no network delay; with one, both grow. An effect that must stay ON a runner is an attach
  effect or one played on a target part, not a broadcast at a place.
- A second event for one broadcast on one client, an event for the far player at the first send, or a `sent` that
  differs from the above is a fault in `Vfx.broadcast` / `VfxNet.newcomers`.

## One client more (ordinary play): a critical layer, a source destroyed

Run the same day with three made presets (ModuleScripts made in Edit under `ReplicatedStorage.VfxPresets`: rings of
`material = "Neon"`, `color = { 1, 0.9, 0.6 }`) and a LocalScript that counts the effect's MeshParts:
- 10 plain mesh layers and 4 marked `critical = true`, under `VfxMesh.setBudget({ max = 12, reserve = 4 })`: 12 in
  use (8 plain, the 4 critical), 2 plain turned away (`stats().refused = 2`); all gone after the effect.
- an attach effect whose part is destroyed 0.7 s in: its 2 meshes are gone 1.2 s later, nothing warned or thrown, the
  stop function still runs.
- a stage whose anchor part (`"point": "@blade"`) is destroyed 0.7 s in: both meshes play on to the end, nothing
  warned or thrown, the stage finishes.
A made preset's colour must be a palette name of its own or `[r, g, b]`: `"white"` with no palette is refused.

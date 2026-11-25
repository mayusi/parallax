-- harness.luau — prepended to every playtest scenario by `kit playtest bundle`. Runs INSIDE Roblox (Studio play
-- mode) via the Studio MCP tool execute_luau, and RETURNS one JSON string the agent saves with `kit playtest record`.
-- Lines tagged @kit: are rewritten by the bundler (scenario name, perf budget, scenario source).
local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local Stats = game:GetService("Stats")

local SCENARIO = "smoke" -- @kit:name
-- (the kit's defaults; the bundler swaps the tagged line below for one line of kit.config.json's qa.perf)
local DEFAULT_BUDGET = {
	memoryMb = 1500,
	instances = 60000,
	frameMs = 20,
	clientMemoryMb = 1100,
	highlights = 31,
	shadowLights = 16,
	shadowRadius = 120,
}
local BUDGET = DEFAULT_BUDGET -- @kit:budget

local result = {
	scenario = SCENARIO,
	side = if RunService:IsServer() then "Server" else "Client",
	checks = {},
	errors = {},
	perf = {},
	status = "pass",
}

local t = {}

-- every red line in the console is a failure (a playtest never passes over a script error): errors already in the
-- log since the play session started + errors raised while the scenario runs. Studio's own and plugins' are not
-- the game's.
local LogService = game:GetService("LogService")
local consoleErrors: { string } = {}
-- (matched whatever the case: a 2-player test's server logs Studio's own "Unable to load plugin icon: ..." as an
-- error, and the arena playtest failed on it - Studio 2026-11-21, tests/playtest/kit_integration_arena; a test client's
-- Roblox start-up script (Script Context.StarterScript, one of the CoreScripts) logged one of its own the same day)
local function gameError(msg: string): boolean
	local low = string.lower(msg)
	for _, noise in { "plugin", "coregui", "corepackages", "corescript", "starterscript", "studioservice" } do
		if string.find(low, noise, 1, true) then
			return false
		end
	end
	return true
end
pcall(function()
	for _, entry in LogService:GetLogHistory() do
		if entry.messageType == Enum.MessageType.MessageError and gameError(entry.message) then
			table.insert(consoleErrors, entry.message)
		end
	end
end)
local logConn = LogService.MessageOut:Connect(function(msg: string, kind: Enum.MessageType)
	if kind == Enum.MessageType.MessageError and gameError(msg) then
		table.insert(consoleErrors, msg)
	end
end)

-- record a check; returns cond so scenarios can branch. `fix` = what to do if it fails (shown as next_action).
function t.check(name: string, cond: any, detail: any?, fix: string?): boolean
	local ok = cond and true or false
	table.insert(
		result.checks,
		{ name = name, ok = ok, detail = if detail ~= nil then tostring(detail) else nil, fix = fix }
	)
	if not ok then
		result.status = "fail"
	end
	return ok
end

function t.wait(seconds: number)
	task.wait(seconds)
end

-- poll fn() until truthy or timeout; returns the value (or nil)
function t.waitFor(fn: () -> any, timeout: number?): any
	local deadline = os.clock() + (timeout or 10)
	while os.clock() < deadline do
		local ok, v = pcall(fn)
		if ok and v then
			return v
		end
		task.wait(0.1)
	end
	return nil
end

-- the first player with a spawned character (server) or the LocalPlayer (client)
function t.player(timeout: number?): Player?
	return t.waitFor(function()
		local p = if RunService:IsClient() then Players.LocalPlayer else Players:GetPlayers()[1]
		if p and p.Character and p.Character:FindFirstChildOfClass("Humanoid") then
			return p
		end
		return nil
	end, timeout or 15)
end

function t.find(path: string): Instance?
	local node: Instance = game
	for part in string.gmatch(path, "[^%.]+") do
		local child = node:FindFirstChild(part)
		if not child then
			return nil
		end
		node = child
	end
	return node
end

-- what the client's scene holds now: Highlights turned on (in the workspace and the player's own GUI, where the
-- engine draws them) and shadow-casting lights turned on within `radius` studs of the camera
local function sceneNow(radius: number): { highlights: number, shadowLights: number }
	local out = { highlights = 0, shadowLights = 0 }
	local cam = workspace.CurrentCamera
	local at = if cam then cam.CFrame.Position else Vector3.zero
	local roots: { Instance } = { workspace }
	local player = Players.LocalPlayer
	local gui = player and player:FindFirstChildOfClass("PlayerGui")
	if gui then
		table.insert(roots, gui)
	end
	for _, root in roots do
		for _, d in root:GetDescendants() do
			if d:IsA("Highlight") and d.Enabled then
				out.highlights += 1
			elseif root == workspace and d:IsA("Light") and d.Enabled and d.Shadows then
				local host = d.Parent
				local pos = if host and host:IsA("BasePart")
					then host.Position
					elseif host and host:IsA("Attachment") then host.WorldPosition
					else nil
				if pos and (pos - at).Magnitude <= radius then
					out.shadowLights += 1
				end
			end
		end
	end
	return out
end

local function perf()
	-- In Studio the process total includes the editor, the edit DataModel and every plugin's Lua heap (measured:
	-- ~3.4 GB on a small test place, LuaHeap ~1 GB of it plugins). Gate on what the GAME owns there; in a live
	-- server the total is the game, so it stays the measure.
	local total = Stats:GetTotalMemoryUsageMb()
	local mem = total
	if RunService:IsStudio() then
		mem = 0
		for _, tag in
			{
				"Instances",
				"BaseParts",
				"PhysicsCollision",
				"PhysicsParts",
				"GraphicsSolidModels",
				"GraphicsMeshParts",
				"GraphicsParticles",
				"GraphicsParts",
				"GraphicsSpatialHash",
				"GraphicsTerrain",
				"GraphicsTexture",
				"GraphicsTextureCharacter",
				"Sounds",
				"StreamingSounds",
				"TerrainVoxels",
				"Gui",
				"Animation",
				"Navigation",
			}
		do
			local ok, v = pcall(function()
				return Stats:GetMemoryUsageMbForTag((Enum.DeveloperMemoryTag :: any)[tag])
			end)
			if ok then
				mem += v
			end
		end
	end
	local instances = #workspace:GetDescendants()
	-- the WORK a frame costs (the engine's own counter), on the server and the client alike. A client's drawn frame
	-- rate is NOT it: Studio draws a window that is not in front about 6 times a second (measured 2026-11-17: 6
	-- frames = 167 ms each while the frame's work was 0.09 ms), so three client playtests failed on Studio's
	-- background throttle, not on the game. The drawn rate is still measured and reported beside it.
	local heartbeatMs = 0
	local ok, v = pcall(function()
		return Stats.HeartbeatTimeMs
	end)
	heartbeatMs = if ok then v else 0
	local renderFps: number? = nil
	if not RunService:IsServer() then
		local frames, start = 0, os.clock()
		local conn = RunService.RenderStepped:Connect(function()
			frames += 1
		end)
		task.wait(1)
		conn:Disconnect()
		renderFps = math.floor(frames / math.max(os.clock() - start, 1e-3) + 0.5)
	end
	result.perf = {
		memoryMb = math.floor(mem),
		processMb = math.floor(total),
		workspaceInstances = instances,
		frameMs = math.floor(heartbeatMs * 10) / 10,
		renderFps = renderFps,
		-- (a window in the background draws ~6 fps: the drawn rate says nothing about the game there)
		renderThrottled = if renderFps then renderFps < 20 and heartbeatMs < 5 else nil,
	}
	local budgetFix = "find the growth (instances not cleaned up?) or raise qa.perf in kit.config.json if intended"
	t.check(`perf: game memory {math.floor(mem)} MB <= {BUDGET.memoryMb}`, mem <= BUDGET.memoryMb, nil, budgetFix)
	t.check(
		`perf: workspace instances {instances} <= {BUDGET.instances}`,
		instances <= BUDGET.instances,
		nil,
		budgetFix
	)
	t.check(
		`perf: frame work {result.perf.frameMs} ms <= {BUDGET.frameMs}{if renderFps
			then ` (drawn {renderFps} fps{if result.perf.renderThrottled then ": Studio's background window" else ""})`
			else ""}`,
		heartbeatMs <= BUDGET.frameMs,
		nil,
		budgetFix
	)
	if RunService:IsServer() then
		return
	end
	-- the scene budget a CLIENT can read (the V3 list, XP-08): its game memory against the PC ceiling, the Highlights
	-- turned on (the engine draws 31: the rest are silently not drawn) and the shadow-casting lights near the camera
	-- (each one renders the scene again; the world lane's own check warns at the same 16 inside 120 studs)
	t.check(
		`perf: client game memory {math.floor(mem)} MB <= {BUDGET.clientMemoryMb}`,
		mem <= BUDGET.clientMemoryMb,
		nil,
		budgetFix
	)
	local scene = sceneNow(BUDGET.shadowRadius)
	result.perf.highlights = scene.highlights
	result.perf.shadowLights = scene.shadowLights
	t.check(
		`perf: Highlights on {scene.highlights} <= {BUDGET.highlights}`,
		scene.highlights <= BUDGET.highlights,
		nil,
		"the engine draws 31 Highlights on a client: the rest vanish without a word - give the lesser ones up "
			.. "(VfxHighlight claims a slot by priority) or raise qa.perf.highlights only if Roblox raised its limit"
	)
	t.check(
		`perf: shadow lights within {BUDGET.shadowRadius} studs {scene.shadowLights} <= {BUDGET.shadowLights}`,
		scene.shadowLights <= BUDGET.shadowLights,
		nil,
		"turn Shadows off on the small or far lights (a lamp's fill light, a candle) - keep it on the few that "
			.. "shape the scene"
	)
end

local scenario = (function(): any
	return nil -- @kit:scenario
end)()

local ok, err = pcall(scenario, t)
if not ok then
	table.insert(result.errors, tostring(err))
	result.status = "fail"
end
local okPerf, perfErr = pcall(perf)
if not okPerf then
	table.insert(result.errors, "perf probe: " .. tostring(perfErr))
end
task.wait(0.2) -- (errors raised by the scenario's last actions reach the log a frame later)
logConn:Disconnect()
result.console = { errors = { table.unpack(consoleErrors, 1, math.min(#consoleErrors, 10)) }, count = #consoleErrors }
t.check(
	`console: no script errors ({#consoleErrors})`,
	#consoleErrors == 0,
	consoleErrors[1],
	"read the first error (its script and line are in the message) and fix it — a playtest never passes over a red console"
)
return HttpService:JSONEncode(result)

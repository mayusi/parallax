--!nocheck
-- booth.luau — the UI booth, run INSIDE Roblox Studio (edit mode, the kit's scratch place) through the shared capture
-- bridge (kit/tools/studio_capture.py, card 4s96): `lune run kit ui booth <Screen>` writes the run's script
-- (<Screen>.studio.luau, the job inside it) and this file is installed once into ServerStorage.KitStudioBridge.UiBooth.
-- A screen judged in the REAL engine: real fonts, real plates, real motion. Nothing is fetched: the screen is a COPY
-- of the place's own (StarterGui.<Screen>, built by Rojo from src/ui/<Screen>.model.json) and the runtime a fresh copy
-- of the place's src/kit (ReplicatedStorage.kit.Ui); a place older than the repo is NAMED in the answer. The copy is
-- shown in StarterGui (Studio draws StarterGui in the viewport in edit mode) and its arrival played by the same
-- runtime the game uses; the capture (python kit/vfx/capture.py studio --clip ...) reads the window:
--   arrival  a MOVING walk: the go colour leaves the 3D view on the very frame Ui.show starts the choreography; the
--            capture times its reads from there and keeps the one closest to each moment
--   reel     (job.states = a reel's exported states: python kit/ui/reel.py <Screen> --states t,t,...) a HELD walk:
--            each moment's node states set on the engine's instances behind its signal colour, then held still
-- The answer is ONE JSON line, returned by the run (or kept for <Screen>.collect.luau when the run is long). Nothing
-- is uploaded; nothing in the place outside the copy and ReplicatedStorage.KitUiBooth is touched, and both go at the end.
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local StarterGui = game:GetService("StarterGui")
local Workspace = game:GetService("Workspace")

local Bridge = require(script.Parent:WaitForChild("Bridge")) -- kit/studio/capture_bridge.luau

local LONG = 40 -- s: a run expected to last longer answers "started" at once (one Studio tool call is not longer)

local function answer(t: { [string]: any }): string
	t.schema = 1
	return Bridge.encode(t)
end

-- reel mode: the moments' node states, applied to the screen's instances
local function reelApply(gui: Instance, Ui: any)
	local designed: { [Instance]: { [string]: any } } = {}
	local function remember(inst: Instance)
		if designed[inst] then
			return designed[inst]
		end
		local d: { [string]: any } = {}
		if inst:IsA("GuiObject") then
			d.Position = inst.Position
			d.BackgroundTransparency = inst.BackgroundTransparency
		end
		if inst:IsA("ImageLabel") or inst:IsA("ImageButton") then
			d.ImageTransparency = (inst :: ImageLabel).ImageTransparency
		end
		if inst:IsA("TextLabel") or inst:IsA("TextButton") then
			d.TextTransparency = (inst :: TextLabel).TextTransparency
		end
		designed[inst] = d
		return d
	end
	local function at(path: string): Instance?
		local node: Instance? = gui
		for part in string.gmatch(path, "[^%.]+") do
			node = node and node:FindFirstChild(part)
		end
		return node
	end
	local function alpha(inst: Instance, k: number)
		for _, d in { inst, table.unpack(inst:GetDescendants()) } do
			local base0 = remember(d)
			if d:IsA("GuiObject") then
				(d :: any).BackgroundTransparency = 1 - (1 - base0.BackgroundTransparency) * k
			end
			if base0.ImageTransparency ~= nil then
				(d :: any).ImageTransparency = 1 - (1 - base0.ImageTransparency) * k
			end
			if base0.TextTransparency ~= nil then
				(d :: any).TextTransparency = 1 - (1 - base0.TextTransparency) * k
			end
		end
	end
	return function(nodes: { [string]: any })
		for path, st in nodes do
			local inst = at(path)
			if not (inst and inst:IsA("GuiObject")) then
				continue
			end
			local g = inst :: GuiObject
			local d0 = remember(g)
			if st.Size then
				local u = st.Size.UDim2
				g.Size = UDim2.new(u[1][1], u[1][2], u[2][1], u[2][2])
			end
			if st.Visible ~= nil then
				g.Visible = st.Visible
			end
			if st.Rotation then
				g.Rotation = st.Rotation
			end
			if st.dx or st.dy then
				g.Position = d0.Position + UDim2.fromOffset(st.dx or 0, st.dy or 0)
			else
				g.Position = d0.Position
			end
			if st.scale then
				local s = g:FindFirstChild("KitReelScale") or Instance.new("UIScale")
				s.Name = "KitReelScale"
				(s :: UIScale).Scale = st.scale
				s.Parent = g
			end
			if st.alpha then
				alpha(g, st.alpha)
			end
			if st.text and g:IsA("TextLabel") then
				(g :: TextLabel).Text = st.text
			end
			if st.number then
				Ui.number(g, st.number)
			end
		end
	end
end

local function run(jobText: string): string
	local job = Bridge.decode(jobText)
	local name = job.screen
	local key = job.key or "ui_booth"
	if type(name) ~= "string" or name == "" then
		return answer({
			status = "fail",
			summary = "the job names no screen",
			next_action = "lune run kit ui booth <Screen>",
		})
	end
	if job.states ~= nil and type(job.states) ~= "table" then
		return answer({
			status = "fail",
			summary = "reel mode: the job's states must be inside it (the reel's exported states)",
			next_action = "python kit/ui/reel.py <Screen> --states t,t,... then lune run kit ui booth <Screen>",
		})
	end
	local stale = Bridge.staleWords(
		Bridge.staleKit(ReplicatedStorage:FindFirstChild("kit"), job.kitPrints),
		Bridge.staleScreens(job.screenPrints)
	)
	local folder = ReplicatedStorage:FindFirstChild("KitUiBooth")
	if folder then
		folder:Destroy()
	end
	folder = Instance.new("Folder")
	folder.Name = "KitUiBooth"
	folder.Parent = ReplicatedStorage
	local kit = Bridge.freshKit(folder)
	if not (kit and kit:FindFirstChild("Ui")) then
		folder:Destroy()
		return answer({
			status = "fail",
			summary = "this place holds no ReplicatedStorage.kit.Ui: it is not the kit's scratch place",
			next_action = "build and open it: lune run kit playtest place (KitPlaytestScratch)",
		})
	end
	local Ui = require(kit:FindFirstChild("Ui"))
	-- the screen, a copy of the place's own in StarterGui, hidden until the clock starts
	local gui, why = Bridge.copyScreen(name, name, StarterGui)
	if not gui then
		folder:Destroy()
		return answer({ status = "fail", summary = why, next_action = "lune run kit playtest place --game none" })
	end
	gui.Enabled = false
	local capture = if type(job.capture) == "table" then job.capture else {}
	local flash, hold = capture.flash or 0.6, capture.hold or 1.0
	local settle = if job.settle then job.settle else 0.6
	local reel = job.states
	local moments = if reel then {} else (job.moments or { 0.0, 0.15, 0.4, 1.0, 2.0 })
	table.sort(moments)
	local seconds = if reel
		then 8 + settle + 2 * flash + #reel.moments * ((job.hold or 0.15) + flash + hold)
		else 8 + settle + 3 * flash + (moments[#moments] or 0) + 0.5
	seconds = math.ceil(seconds)
	local base = {
		key = key,
		screen = name,
		mode = if reel then "reel" else "arrival",
		view = if reel then "reel" else "engine",
		moments = moments,
		instances = #gui:GetDescendants(),
		viewport = { Workspace.CurrentCamera.ViewportSize.X, Workspace.CurrentCamera.ViewportSize.Y },
		stale_words = stale,
	}

	local function body(): string
		local grabs = {}
		local asked = 0
		local sig = Bridge.signal({ flash = flash })
		local ok, err = pcall(function()
			if reel then
				local apply = reelApply(gui, Ui)
				gui.Enabled = true -- (shown first: Ui.preload WARMS hidden pictures only on a screen being drawn)
				asked = if Ui.preload then Ui.preload(gui, 8) else 0
				task.wait(settle)
				sig.start()
				for i, m in reel.moments do
					sig.next(i) -- (the moment's state is set behind its colour)
					apply(m.nodes)
					task.wait(if job.hold then job.hold else 0.15) -- (how long the state is held before the picture)
					RunService.RenderStepped:Wait()
					sig.hide()
					table.insert(grabs, { k = i, view = "reel", i = i, t = m.t })
					task.wait(hold)
				end
			else
				-- the screen's art fetched first, as the game's client does (Ui.preload): a fixed wait let the first
				-- picture show the pieces streaming in one by one; then a short settle for fonts
				asked = if Ui.preload then Ui.preload(gui, 8) else 0
				task.wait(settle)
				sig.start()
				sig.next(1) -- the go colour: it leaves on the frame the arrival starts
				sig.hide()
				Ui.show(gui, true) -- the arrival choreography, by the game's own runtime
				task.wait((moments[#moments] or 0) + 0.4)
			end
		end)
		sig.finish()
		-- (Studio is shared with the other lanes: leave the place as it was found)
		gui:Destroy()
		folder:Destroy()
		local final = table.clone(base)
		final.preloaded = asked
		final.grabs = grabs
		final.status = if ok then "pass" else "fail"
		final.summary = if ok
			then `{name}: {base.mode} signalled ({if reel
				then #grabs .. " held moment(s)"
				else #moments .. " moment(s) to cut from the motion"}), {asked} picture(s) preloaded` .. (if stale
				then "; " .. stale
				else "")
			else `{name}: the booth stopped: {tostring(err)}`
		if not ok then
			final.error = tostring(err)
		end
		return Bridge.store(key, answer(final))
	end

	if seconds <= LONG then
		return body()
	end
	Bridge.store(key, answer({ status = "running", summary = `ui booth {name} still running (about {seconds} s)` }))
	task.spawn(body)
	local started = table.clone(base)
	started.status = "started"
	started.seconds = seconds
	started.collect = job.collect
	started.summary = `{name}: {base.mode}, about {seconds} s` .. (if stale then "; " .. stale else "")
	started.next_action =
		`wait about {seconds} s, then run {job.collect or "the run's .collect.luau"} and save its line as the capture asks`
	return answer(started)
end

return { run = run }

-- capture_bridge.luau - the Studio side of the kit's shared capture bridge (kit/tools/studio_capture.py, card 4s96).
-- A script the Studio tools run (execute_luau, the Edit datamodel) cannot call a local server, so the kit's
-- harnesses (the VFX booth, the UI booth, the UI playtest, the v6 proof) talk to the capture by what is ON SCREEN
-- and by what the call RETURNS:
--   * a plain colour over the whole 3D view: magenta = a walk starts, one of six colours = picture k is coming (its
--     number in sixes: k = 1 shows NEXTS[1]), cyan = over. The capture reads the place's own window;
--   * the run's answer is ONE JSON line: returned by the run itself, or kept here (Bridge.store) and returned by the
--     run's .collect.luau once a long run is over.
-- It also says when the PLACE is older than the repo: the generated run carries the repo's fingerprints of the
-- src/kit modules and screens it uses; a place built before they changed shows the old ones (named in the answer).
-- Installed with the harnesses into ServerStorage.KitStudioBridge by a run's .install.luau; nothing else is touched.
local CoreGui = game:GetService("CoreGui")
local HttpService = game:GetService("HttpService") -- (JSON only: nothing here calls out)
local RunService = game:GetService("RunService")

local Bridge = {}

Bridge.START = Color3.fromRGB(255, 0, 255)
Bridge.DRAWN = 8 -- the least frames a start / end colour is drawn for (Bridge.signal's hold)
Bridge.END = Color3.fromRGB(0, 255, 255)
Bridge.NEXTS = {
	Color3.fromRGB(255, 255, 0),
	Color3.fromRGB(0, 255, 0),
	Color3.fromRGB(0, 0, 255),
	Color3.fromRGB(255, 128, 0),
	Color3.fromRGB(128, 0, 255),
	Color3.fromRGB(0, 128, 255),
}

function Bridge.decode(text: string): any
	return HttpService:JSONDecode(text)
end

function Bridge.encode(value: any): string
	return HttpService:JSONEncode(value)
end

-- FNV-1a (32 bit) of a text's bytes, carriage returns left out -> 8 hex digits (studio_capture.fingerprint)
function Bridge.fingerprint(text: string): string
	local h = 2166136261
	local n = #text
	local i = 1
	while i <= n do
		local j = math.min(i + 4095, n)
		for _, b in { string.byte(text, i, j) } do
			if b ~= 13 then
				h = bit32.bxor(h, b)
				-- h * 16777619 (= 2^24 + 403) mod 2^32, kept exact: the shift wraps, h * 403 stays below 2^41
				h = (bit32.lshift(h, 24) + h * 403) % 4294967296
			end
		end
		i = j + 1
	end
	return string.format("%08x", h)
end

-- an instance tree's shape -> "<instances>:<fingerprint of every Class:Name, sorted>" (studio_capture.tree_print)
function Bridge.treePrint(root: Instance): string
	local names = { root.ClassName .. ":" }
	for _, d in root:GetDescendants() do
		table.insert(names, d.ClassName .. ":" .. d.Name)
	end
	table.sort(names)
	return #names .. ":" .. Bridge.fingerprint(table.concat(names, "\n"))
end

-- the place's src/kit modules (ReplicatedStorage.kit) that are not the repo's -> their names
function Bridge.staleKit(kit: Instance?, prints: { [string]: string }?): { string }
	local stale = {}
	for name, want in prints or {} do
		local m = kit and kit:FindFirstChild(name)
		if not (m and m:IsA("ModuleScript")) then
			table.insert(stale, name .. " (missing)")
		elseif Bridge.fingerprint((m :: any).Source) ~= want then
			table.insert(stale, name)
		end
	end
	table.sort(stale)
	return stale
end

-- a screen the place holds (StarterGui.<path>, "/" between levels) -> it, or nil
function Bridge.screen(path: string): Instance?
	local node: Instance? = game:GetService("StarterGui")
	for part in string.gmatch(path, "[^/]+") do
		node = node and node:FindFirstChild(part)
	end
	return node
end

-- a COPY of a screen the place holds, named `as`, under `parent` -> it, or nil and why (the place's own is untouched)
function Bridge.copyScreen(path: string, as: string, parent: Instance): (Instance?, string?)
	local node = Bridge.screen(path)
	if not node then
		return nil,
			`this place has no StarterGui.{string.gsub(path, "/", ".")} (src/ui/{path}.model.json): rebuild the scratch place (lune run kit playtest place) after compiling it, and reopen it`
	end
	local copy = node:Clone()
	copy.Name = as
	copy.Parent = parent
	return copy, nil
end

-- a fresh COPY of the place's src/kit (ReplicatedStorage.kit) under `parent`: require caches a module's first result
-- per Studio session, a copy is new each run (and its modules find each other, as in the game)
function Bridge.freshKit(parent: Instance): Instance?
	local kit = game:GetService("ReplicatedStorage"):FindFirstChild("kit")
	if not kit then
		return nil
	end
	local copy = kit:Clone()
	copy.Parent = parent
	return copy
end

-- the screens of `prints` the place holds a DIFFERENT shape of -> their names (a missing one is said too)
function Bridge.staleScreens(prints: { [string]: string }?): { string }
	local stale = {}
	for path, want in prints or {} do
		local node = Bridge.screen(path)
		if not node then
			table.insert(stale, path .. " (missing)")
		elseif Bridge.treePrint(node) ~= want then
			table.insert(stale, path)
		end
	end
	table.sort(stale)
	return stale
end

-- what a stale place means, in words (nil when nothing is stale)
function Bridge.staleWords(kit: { string }, screens: { string }): string?
	if #kit == 0 and #screens == 0 then
		return nil
	end
	local parts = {}
	if #kit > 0 then
		table.insert(parts, "src/kit " .. table.concat(kit, ", "))
	end
	if #screens > 0 then
		table.insert(parts, "screens " .. table.concat(screens, ", "))
	end
	return "the place is OLDER than the repo ("
		.. table.concat(parts, "; ")
		.. "): this run used the place's copies; rebuild it (lune run kit playtest place) and reopen it"
end

-- the run's answer kept for its .collect.luau (ServerStorage.KitStudioBridge.Results.<key>)
function Bridge.store(key: string, answer: any): string
	local text = if type(answer) == "string" then answer else Bridge.encode(answer)
	local holder = script.Parent
	local results = holder:FindFirstChild("Results")
	if not results then
		results = Instance.new("Folder")
		results.Name = "Results"
		results.Parent = holder
	end
	local sv = results:FindFirstChild(key) or Instance.new("StringValue")
	sv.Name = key;
	(sv :: StringValue).Value = text
	sv.Parent = results
	return text
end

export type Signal = {
	show: (colour: Color3) -> (),
	hide: () -> (),
	start: () -> (),
	next: (k: number) -> (),
	finish: () -> (),
}

-- the signal cover over the 3D view (a CoreGui ScreenGui drawn above everything else there). timing: { flash = s }:
-- the least time a colour stays up (the capture reads the window a few times a second: a shorter one can be missed)
function Bridge.signal(timing: { [string]: any }?): Signal
	local flashT = (timing and timing.flash) or 0.6
	local old = CoreGui:FindFirstChild("KitCaptureSignal")
	if old then
		old:Destroy()
	end
	local gui = Instance.new("ScreenGui")
	gui.Name, gui.DisplayOrder, gui.IgnoreGuiInset = "KitCaptureSignal", 2147483647, true
	local cover = Instance.new("Frame")
	cover.Size, cover.BorderSizePixel, cover.Visible = UDim2.fromScale(1, 1), 0, false
	cover.Parent = gui
	gui.Parent = CoreGui
	local shownAt = os.clock()
	local s = {}
	-- a colour over the view (it stays up until hide or the next colour)
	function s.show(colour: Color3)
		cover.BackgroundColor3 = colour
		cover.Visible = true
		shownAt = os.clock()
	end
	-- the view uncovered, once the colour has been up for the flash time (the caller's next line runs on the very
	-- frame the view shows: a moving walk starts its motion there)
	function s.hide()
		local left = flashT - (os.clock() - shownAt)
		if cover.Visible and left > 0 then
			task.wait(left)
		end
		cover.Visible = false
	end
	-- a colour held for the flash time AND for at least DRAWN frames really drawn: a run started by a Studio tool
	-- call shows its START while Studio is still busy with that call, so 0.6 s of clock can pass with no frame drawn
	-- and the capture never sees it (the VFX booth, 2026-11-21: every later colour read, the START never)
	local function hold(colour: Color3)
		s.show(colour)
		local drawn = 0
		local conn = RunService.RenderStepped:Connect(function()
			drawn += 1
		end)
		local t0 = os.clock()
		while os.clock() - t0 < flashT or (drawn < Bridge.DRAWN and os.clock() - t0 < 10) do
			task.wait()
		end
		conn:Disconnect()
	end
	-- the walk starts (the capture also learns where the 3D view is)
	function s.start()
		hold(Bridge.START)
	end
	-- picture k (1, 2, ...) is coming: its colour stays up while the caller draws the picture's view behind it
	function s.next(k: number)
		s.show(Bridge.NEXTS[(k - 1) % #Bridge.NEXTS + 1])
	end
	function s.finish()
		if gui.Parent then
			pcall(function()
				hold(Bridge.END)
			end)
			gui:Destroy()
		end
	end
	return s :: any
end

return Bridge

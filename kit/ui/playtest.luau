--!nocheck
-- playtest.luau — the kit Ui RUNTIME exercised in the real engine (mission 03, 5.5), run INSIDE Roblox Studio (edit
-- mode, the kit's scratch place) through the shared capture bridge (kit/tools/studio_capture.py, card 4s96):
--   python kit/tools/studio_capture.py snippet ui_playtest --out build/ui/playtest/<Screen> --set screen=<Screen>
--          [--set bar=<path>] [--set text=<path>]
-- writes the run's script (the job inside it); this file is installed once into ServerStorage.KitStudioBridge. It
-- takes a COPY of the place's own screen (StarterGui.<Screen>, built by Rojo from src/ui/<Screen>.model.json), drives
-- it through a fresh copy of the place's runtime (ReplicatedStorage.kit.Ui; a place older than the repo is NAMED in
-- the report) and asserts what the engine reports — the state a player's screen would be in, not a picture of it:
--   bar      Ui.bar drops the fill at once, the ghost HOLDS then drains to it; the fill keeps its designed height
--   text     Ui.text sets a label's words
--   number   Ui.number lays out a digit set: shorter / longer texts, cells left to right, extra cells hidden
--   flipbook Ui.flipbook steps the frames and stops on the last (loop off)
--   preload  Ui.preload counts the screen's pictures
-- Then it removes everything it built (Studio is shared with the other lanes) and RETURNS a JSON report (the
-- execute_luau call's own answer: nothing is sent anywhere).
-- Module form: { run(jobJson) -> JSON text } (job: screen, bar, text).
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local StarterGui = game:GetService("StarterGui")

local function near(a: number, b: number, tol: number): boolean
	return math.abs(a - b) <= tol
end

local function find(root: Instance, path: string): Instance?
	local node = root
	for part in string.gmatch(path, "[^%.]+") do
		node = node and node:FindFirstChild(part)
	end
	return node
end

local Bridge = require(script.Parent:WaitForChild("Bridge")) -- kit/studio/capture_bridge.luau

local function run(jobText: string): string
	local job = Bridge.decode(jobText)
	local screen, barPath, textPath = job.screen, job.bar, job.text
	local results = {}
	local function check(name: string, ok: boolean, detail: string)
		table.insert(results, { check = name, ok = ok, detail = detail })
	end
	local stale = Bridge.staleWords(
		Bridge.staleKit(ReplicatedStorage:FindFirstChild("kit"), job.kitPrints),
		Bridge.staleScreens(job.screenPrints)
	)
	-- the runtime: a fresh copy of the place's src/kit; the screen: a copy of the place's own
	local holder = Instance.new("Folder")
	holder.Name = "KitUiPlaytest"
	holder.Parent = ReplicatedStorage
	local kit = Bridge.freshKit(holder)
	local gui, why = Bridge.copyScreen(tostring(screen), tostring(screen) .. "_Playtest", StarterGui)
	if not (kit and kit:FindFirstChild("Ui") and gui) then
		if gui then
			gui:Destroy()
		end
		holder:Destroy()
		return Bridge.encode({
			schema = 1,
			screen = screen,
			status = "fail",
			summary = `ui playtest {screen}: {why or "this place holds no ReplicatedStorage.kit.Ui (not the kit's scratch place)"}`,
			checks = {},
		})
	end
	local Ui = require(kit:FindFirstChild("Ui"))
	gui.Enabled = true

	local ok, err = pcall(function()
		-- bar + ghost
		local bar = barPath and find(gui, barPath)
		if bar then
			local fill, ghost = bar:FindFirstChild("Fill"), bar:FindFirstChild("Ghost")
			local fillY = fill and fill.Size.Y
			local ghost0 = ghost and ghost.Size.X.Scale
			Ui.bar(bar, 0.5)
			task.wait(0.3)
			check(
				"bar: the fill drops at once",
				fill ~= nil and near(fill.Size.X.Scale, 0.5, 0.02),
				`fill x {fill and fill.Size.X.Scale}`
			)
			check(
				"bar: the fill keeps its designed height",
				fill ~= nil and fill.Size.Y == fillY,
				`fill y {fill and tostring(fill.Size.Y)} vs designed {tostring(fillY)}`
			)
			if ghost then
				check(
					"bar: the ghost holds",
					near(ghost.Size.X.Scale, ghost0, 0.03),
					`ghost x {ghost.Size.X.Scale} (was {ghost0})`
				)
				task.wait(1.0)
				check(
					"bar: the ghost drains to the value",
					near(ghost.Size.X.Scale, 0.5, 0.03),
					`ghost x {ghost.Size.X.Scale}`
				)
			end
		else
			check("bar", false, `no bar at {tostring(barPath)}`)
		end
		-- text
		local label = textPath and find(gui, textPath)
		if label and label:IsA("TextLabel") then
			Ui.text(label, "54")
			task.wait(0.1)
			check("text: Ui.text sets the words", label.Text == "54", `text "{label.Text}"`)
		end
		-- a digit set, built the way the compiler lays one out (4 cells of 30 px, advance 24 px)
		local num = Instance.new("Frame")
		num.Name = "NumProbe"
		num.Size = UDim2.fromOffset(120, 40)
		num.BackgroundTransparency = 1
		num:SetAttribute("Kit_DigitIds", "1=rbxassetid://1;2=rbxassetid://2;3=rbxassetid://3")
		num:SetAttribute("Kit_DigitCell", 24)
		num:SetAttribute("Kit_DigitWidth", 30)
		num:SetAttribute("Kit_DigitAlign", "left")
		local c1 = Instance.new("ImageLabel")
		c1.Name = "C1"
		c1.Size = UDim2.new(0, 30, 1, 0)
		c1.Parent = num
		num.Parent = gui
		Ui.number(num, "123")
		local c2, c3 = num:FindFirstChild("C2"), num:FindFirstChild("C3")
		check(
			"number: three cells, left to right on the advance",
			c2 ~= nil
				and c3 ~= nil
				and c2.Position.X.Offset - c1.Position.X.Offset == 24
				and c3.Image == "rbxassetid://3",
			`C1 {c1.Position.X.Offset}, C2 {c2 and c2.Position.X.Offset}, C3 image {c3 and c3.Image}`
		)
		Ui.number(num, "1")
		check(
			"number: a shorter text hides the extra cells",
			c2 ~= nil and c2.Visible == false,
			`C2 visible {c2 and tostring(c2.Visible)}`
		)
		-- a flipbook (the compiler's Kit_Flip): three frames at 20 fps, played once
		local flip = Instance.new("ImageLabel")
		flip.Name = "FlipProbe"
		flip:SetAttribute("Kit_Flip", "rbxassetid://11;rbxassetid://12;rbxassetid://13")
		flip:SetAttribute("Kit_FlipFps", 20)
		flip:SetAttribute("Kit_FlipLoop", false)
		flip.Parent = gui
		Ui.flipbook(flip)
		task.wait(0.05)
		local early = flip.Image
		task.wait(0.4)
		check(
			"flipbook: it plays and stops on the last frame",
			early ~= "" and flip.Image == "rbxassetid://13",
			`at 0.05 s {early}, at 0.45 s {flip.Image}`
		)
		-- preload
		local n = Ui.preload(gui, 2)
		check("preload: the screen's pictures are asked for", n > 0, `{n} picture(s)`)
	end)
	if not ok then
		check("the playtest ran", false, tostring(err))
	end
	gui:Destroy()
	holder:Destroy()
	local passed = 0
	for _, r in results do
		if r.ok then
			passed += 1
		end
	end
	return Bridge.encode({
		schema = 1,
		screen = screen,
		status = if passed == #results then "pass" else "fail",
		summary = `ui playtest {screen}: {passed}/{#results} runtime check(s) pass in the engine`
			.. (if stale then "; " .. stale else ""),
		checks = results,
		stale_words = stale,
	})
end

return { run = run }

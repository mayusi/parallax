--!nocheck
-- proof_v6.luau — the v6 UI runtime exercised in the REAL engine (UI v7.0), run INSIDE Roblox Studio (edit mode, the
-- kit's scratch place) through the shared capture bridge (kit/tools/studio_capture.py, card 4s96):
--   python kit/tools/studio_capture.py snippet ui_proof_v6 --out build/ui/proof_v6
-- writes the run's script; this file is installed once into ServerStorage.KitStudioBridge. It takes COPIES of the
-- place's own compiled screens (StarterGui.<Screen>, built by Rojo from src/ui) and drives them through a fresh copy of
-- the place's runtime (ReplicatedStorage.kit.Ui; a place older than the repo is NAMED in the report), then asserts
-- what the engine reports:
--   fx        RushHud: Ui.fx moves the neck's shimmer band; the rank's ping grows; SMASH!'s split copies exist
--   states    SimShop: Ui.setState "locked" swaps the plate + words and stops the button; nil restores both
--   gamepad   SimShop: the focus piece on every button, the tab row's wrap link, firstFocus resolvable
--   path      FieldHud: Ui.path builds Path2Ds with control points (and an outline under the line)
--   burst     RushHud: Ui.burst flies sprites in a KitBursts layer, and they are pooled after their life
--   world     RiffDamage: Ui.attach mounts a billboard on a part; Ui.floater flies a number and clears itself
--   go        SimHud -> SimShop: Ui.go's shared flyer lands and is removed; the target shows again
--   styles    a StyleSheet copied from the place's src/ui/styles/sim takes its rules' properties (Ui.styles)
-- It removes everything it built (Studio is shared) and RETURNS a JSON report (the execute_luau call's own answer).
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local StarterGui = game:GetService("StarterGui")
local Workspace = game:GetService("Workspace")

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
	local results = {}
	local function check(name: string, ok: boolean, detail: string)
		table.insert(results, { check = name, ok = ok == true, detail = detail })
	end
	local stale = Bridge.staleWords(
		Bridge.staleKit(ReplicatedStorage:FindFirstChild("kit"), job.kitPrints),
		Bridge.staleScreens(job.screenPrints)
	)
	local holder = Instance.new("Folder")
	holder.Name = "KitUiProofV6"
	holder.Parent = ReplicatedStorage
	local kit = Bridge.freshKit(holder)
	if not (kit and kit:FindFirstChild("Ui")) then
		holder:Destroy()
		return Bridge.encode({
			passed = 0,
			total = 1,
			results = {
				{
					check = "the place holds ReplicatedStorage.kit.Ui",
					ok = false,
					detail = "not the kit's scratch place",
				},
			},
		})
	end
	local Ui = require(kit:FindFirstChild("Ui"))
	local built: { Instance } = {}
	local function screen(name: string): Instance
		local gui = assert(Bridge.copyScreen(name, name .. "_ProofV6", StarterGui))
		pcall(function()
			gui.Enabled = true
		end)
		table.insert(built, gui)
		for _, d in gui:GetDescendants() do
			Ui.bind(d)
		end
		return gui
	end

	local ok, err = pcall(function()
		-- fx (RushHud)
		local rush = screen("RushHud")
		local band = find(rush, "Hud.Health.Neck.Fx_Shimmer.Band")
		local o0 = band and band.Offset.X
		task.wait(0.7)
		local o1 = band and band.Offset.X
		check("fx: the shimmer band sweeps", band ~= nil and o0 ~= o1, `offset {tostring(o0)} -> {tostring(o1)}`)
		local grow = find(rush, "Hud.Rank.Ring.Fx_Ping.Grow")
		local s0 = grow and grow.Scale
		task.wait(0.15)
		check(
			"fx: the ping grows",
			grow ~= nil and grow.Scale ~= s0,
			`scale {tostring(s0)} -> {tostring(grow and grow.Scale)}`
		)
		check(
			"fx: SMASH! has its split layers",
			find(rush, "Hud.Callout.Word.Fx_SplitA") ~= nil and find(rush, "Hud.Callout.Word.Fx_SplitC") ~= nil,
			"Fx_SplitA / Fx_SplitC"
		)

		-- burst (RushHud callout)
		local callout = find(rush, "Hud.Callout")
		if callout then
			callout.Visible = true
			Ui.burst(callout, "smash")
			task.wait(0.1)
			local layer = rush:FindFirstChild("KitBursts")
			local flying = 0
			for _, c in (layer and layer:GetChildren() or {}) do
				if c:IsA("ImageLabel") and c.Visible then
					flying += 1
				end
			end
			check("burst: sprites fly", flying > 0, `{flying} visible sprite(s)`)
			task.wait(0.7)
			local still = 0
			for _, c in (layer and layer:GetChildren() or {}) do
				if c:IsA("ImageLabel") and c.Visible then
					still += 1
				end
			end
			check("burst: sprites pooled after their life", still == 0, `{still} still visible`)
		end

		-- states + gamepad (SimShop)
		local shop = screen("SimShop")
		local buy = find(shop, "Shop.Window.Grid.Pack1.Buy")
		local label = buy and buy:FindFirstChild("Label")
		local plate = buy and buy:FindFirstChild("Plate")
		local text0 = label and label.Text
		local img0 = plate and plate.Image
		Ui.setState(buy, "locked")
		task.wait(0.2)
		check(
			"states: locked swaps the words",
			label ~= nil and label.Text == "LOCKED",
			`text {tostring(label and label.Text)}`
		)
		check(
			"states: locked swaps the plate",
			plate ~= nil and plate.Image ~= img0,
			`image {tostring(plate and plate.Image)}`
		)
		check(
			"states: locked stops the button",
			buy ~= nil and (buy :: any).Interactable == false,
			`Interactable {tostring(buy and (buy :: any).Interactable)}`
		)
		Ui.setState(buy, nil)
		task.wait(0.2)
		check(
			"states: idle restores the words",
			label ~= nil and label.Text == text0,
			`text {tostring(label and label.Text)}`
		)
		check("states: idle restores the plate", plate ~= nil and plate.Image == img0, "plate image back")
		Ui.gamepad(shop)
		local close = find(shop, "Shop.Window.Close")
		check(
			"gamepad: buttons wear the focus piece",
			close ~= nil and close.SelectionImageObject ~= nil,
			`SelectionImageObject {tostring(close and close.SelectionImageObject)}`
		)
		local passes, featured = find(shop, "Shop.Window.Tabs.TabPasses"), find(shop, "Shop.Window.Tabs.TabFeatured")
		check(
			"gamepad: the tab row wraps",
			passes ~= nil and passes.NextSelectionRight == featured,
			`NextSelectionRight {tostring(passes and passes.NextSelectionRight)}`
		)

		-- path (FieldHud)
		local field = screen("FieldHud")
		local outline
		for _, d in field:GetDescendants() do
			if d.Name == "Outline" and d:GetAttribute("Kit_Path") then
				outline = d
				break
			end
		end
		local line = outline and outline:FindFirstChild("KitPath")
		local under = outline and outline:FindFirstChild("KitPathOutline")
		local n = 0
		pcall(function()
			n = #line:GetControlPoints()
		end)
		check(
			"path: a Path2D with control points",
			line ~= nil and line.ClassName == "Path2D" and n >= 10,
			`{n} points`
		)
		check(
			"path: the outline under the line",
			under ~= nil and line ~= nil and line.ZIndex > under.ZIndex,
			"z order"
		)

		-- world (RiffDamage)
		local tmpl = screen("RiffDamage")
		local part = Instance.new("Part")
		part.Anchored = true
		part.Position = Vector3.new(0, 50, 0)
		part.Parent = Workspace
		table.insert(built, part)
		local mounted = Ui.attach(tmpl, part)
		if mounted then
			table.insert(built, mounted)
		end
		check(
			"world: Ui.attach mounts the billboard on the part",
			mounted ~= nil and mounted:IsA("BillboardGui") and mounted.Adornee == part,
			`{tostring(mounted)} adornee {tostring(mounted and mounted.Adornee)}`
		)
		local fl = Ui.floater(tmpl, Vector3.new(0, 60, 0), "999", 2, 0.5)
		local val = fl and fl:FindFirstChild("Value", true)
		check(
			"world: Ui.floater sets its number",
			val ~= nil and val.Text == "999",
			`text {tostring(val and val.Text)}`
		)
		task.wait(0.7)
		check("world: the floater clears itself", fl == nil or fl.Parent == nil, `parent {tostring(fl and fl.Parent)}`)

		-- go (SimHud -> SimShop, the shared cart)
		local hud = screen("SimHud")
		local shop2 = screen("SimShop")
		local a = find(hud, "Hud.Menu.Shop.Icon")
		local b = find(shop2, "Shop.Window.Title.Icon")
		Ui.go(hud, shop2, { transition = "shared", shared = { a, b }, seconds = 0.3 })
		task.wait(0.15)
		local flying = false
		for _, g in StarterGui:GetChildren() do
			if g.Name == "KitFlowLayer" then
				flying = true
			end
		end
		task.wait(0.6)
		local left = false
		for _, g in StarterGui:GetChildren() do
			if g.Name == "KitFlowLayer" then
				left = true
			end
		end
		check("go: the shared piece flies on a layer", flying, "KitFlowLayer during the flight")
		check(
			"go: the layer is removed and the target shows",
			not left and b ~= nil and b.Visible,
			`b visible {tostring(b and b.Visible)}`
		)

		-- styles (sim)
		local sheet, whyNot = Bridge.copyScreen("styles/sim", "sim", ReplicatedStorage)
		if sheet then
			table.insert(built, sheet)
			Ui.styles()
			local rule = sheet:FindFirstChild("Primary")
			local props = {}
			pcall(function()
				props = rule:GetProperties()
			end)
			check(
				"styles: a rule takes its properties",
				props.BackgroundColor3 ~= nil,
				`Primary BackgroundColor3 {tostring(props.BackgroundColor3)}`
			)
		else
			check("styles: the place holds the sheet", false, tostring(whyNot))
		end
	end)
	if not ok then
		check("the proof ran to the end", false, tostring(err))
	end
	for _, b in built do
		pcall(function()
			b:Destroy()
		end)
	end
	for _, g in StarterGui:GetChildren() do
		if g.Name == "KitFlowLayer" then
			g:Destroy()
		end
	end
	holder:Destroy()
	local passed = 0
	for _, r in results do
		if r.ok then
			passed += 1
		end
	end
	return Bridge.encode({ passed = passed, total = #results, results = results, stale_words = stale })
end

return { run = run }

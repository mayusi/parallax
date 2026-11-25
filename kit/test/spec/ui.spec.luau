-- ui.spec.luau (kit) — the UI compiler compiles the starter screens and its gate bites.
-- Project screens are compiled + drift-checked by `lune run kit ui` / `kit verify`.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local UI = require("../../lib/ui")

local function messages(spec: any): (string, string)
	local _, issues = UI.compile(spec)
	local errors, warns = {}, {}
	for _, issue in issues do
		table.insert(if issue.severity == "error" then errors else warns, issue.message)
	end
	return table.concat(errors, "\n"), table.concat(warns, "\n")
end

local function screen(children: { any }): any
	return {
		name = "T",
		theme = { bg = "#101218", text = "#f0f2f5", dim = "#1a1c22" },
		root = { type = "panel", name = "Root", color = "bg", children = children },
	}
end

return function()
	test.suite("starter screens compile", function()
		-- the examples' identity packs travel with them (kit/starter/ui/identities)
		local identities = {}
		if fs.isDir("kit/starter/ui/identities") then
			for _, f in fs.readDir("kit/starter/ui/identities") do
				if string.sub(f, -5) == ".json" then
					identities[string.sub(f, 1, -6)] =
						serde.decode("json", fs.readFile("kit/starter/ui/identities/" .. f))
				end
			end
		end
		for _, file in fs.readDir("kit/starter/ui") do
			if string.sub(file, -5) ~= ".json" then
				continue -- identities/ and art/ travel with the examples
			end
			local spec = serde.decode("json", fs.readFile("kit/starter/ui/" .. file))
			test.case(`{spec.name} compiles without errors`, function()
				local _, issues = UI.compile(spec, nil, nil, identities)
				local errors = {}
				for _, issue in issues do
					if issue.severity == "error" then
						table.insert(errors, issue.message)
					end
				end
				check.equal(table.concat(errors, "\n"), "")
			end)
		end
	end)

	test.suite("UI positions", function()
		test.case('"100%-24" hugs the far edge with a pixel margin', function()
			local model = UI.compile({
				name = "Edge",
				root = { type = "panel", name = "R", pos = { 24, "100% - 24" }, anchor = "bottomleft" },
			})
			local pos = model.Children[1].Properties.Position.UDim2
			check.equal(pos[1][1], 0)
			check.equal(pos[1][2], 24)
			check.equal(pos[2][1], 1)
			check.equal(pos[2][2], -24)
		end)
	end)

	test.suite("UI gate rejects bad screens", function()
		test.case("unreadable text contrast is an error", function()
			local errors = messages(screen({ { type = "label", name = "L", text = "hi", textColor = "dim" } }))
			check.is_true(string.find(errors, "contrast", 1, true) ~= nil)
		end)
		test.case('"ground" names the art a text sits on: its contrast is measured against it', function()
			local label = { type = "label", name = "L", text = "hi", textColor = "text" }
			local onArt = messages(screen({ { type = "panel", name = "P", ground = "text", children = { label } } }))
			check.is_true(string.find(onArt, "contrast", 1, true) ~= nil)
			local plain = messages(screen({ { type = "panel", name = "P", children = { label } } }))
			check.is_true(string.find(plain, "contrast", 1, true) == nil)
		end)
		test.case('a "number" node composes its text from a digit set and can be the focus', function()
			local model, issues = UI.compile({
				name = "Num",
				focus = "Speed",
				root = {
					type = "panel",
					name = "R",
					size = { 400, 200 },
					children = {
						{
							type = "number",
							name = "Speed",
							digits = "neon/spd",
							aspect = 0.5,
							text = "182",
							size = { 150, 100 },
						},
					},
				},
			})
			for _, issue in issues do
				check.is_true(issue.severity ~= "error" or string.find(issue.message, "focus", 1, true) == nil)
			end
			local speed = model.Children[1].Children[1]
			check.equal(speed.ClassName, "Frame")
			check.equal(#speed.Children, 3)
			check.equal(speed.Children[2].Properties.Attributes.Attributes.KitArt.String, "neon/spd_8")
			check.equal(speed.Properties.Attributes.Attributes.Kit_Number.String, "182")
		end)
		test.case('a "flipbook" puts every frame on the picture for Ui.flipbook; bad ones are errors', function()
			local art = {
				["witch/smear_000"] = { size = 64 },
				["witch/smear_001"] = { size = 64 },
				["witch/smear_002"] = { size = 64 },
			}
			local ids = {
				ui = {
					["witch/smear_000"] = "rbxassetid://10",
					["witch/smear_001"] = "rbxassetid://11",
					["witch/smear_002"] = "rbxassetid://12",
				},
			}
			local function said(issues: { any }, needle: string): boolean
				for _, it in issues do
					if it.severity == "error" and string.find(it.message, needle, 1, true) then
						return true
					end
				end
				return false
			end
			local function flip(fb: any)
				return UI.compile({
					name = "F",
					root = {
						type = "panel",
						name = "R",
						size = { 400, 200 },
						children = { { type = "image", name = "Card", flipbook = fb, size = { 64, 64 } } },
					},
				}, ids, art)
			end
			local model, issues = flip({ frames = "witch/smear_{k:3}", count = 3, fps = 24, loop = false })
			check.is_true(not said(issues, ""))
			local card = model.Children[1].Children[1]
			local a = card.Properties.Attributes.Attributes
			check.equal(a.Kit_Flip.String, "rbxassetid://10;rbxassetid://11;rbxassetid://12")
			check.equal(a.Kit_FlipFps.Float64, 24)
			check.equal(a.Kit_FlipLoop.Bool, false)
			check.equal(card.Properties.Image, "rbxassetid://10") -- (the first frame shows before it plays)
			local _, bad = flip({ frames = "witch/smear_{k:3}", count = 3, fps = 0 })
			check.is_true(said(bad, "fps must be 1..60"))
			local _, missing = flip({ frames = "witch/nope_{k}", count = 2 })
			check.is_true(said(missing, 'unknown art "witch/nope_0"'))
		end)
		test.case('"fx" builds runtime UI materials (glint layers, gradients, Kit_Fx); bad ones are errors', function()
			local art =
				{ ["riff/neck"] = { size = 64 }, ["riff/neck__glint"] = { size = 64 }, ["riff/bare"] = { size = 64 } }
			local ids = { ui = { ["riff/neck"] = "rbxassetid://20", ["riff/neck__glint"] = "rbxassetid://21" } }
			local function said(issues: { any }, needle: string): boolean
				for _, it in issues do
					if it.severity == "error" and string.find(it.message, needle, 1, true) then
						return true
					end
				end
				return false
			end
			local function fx(node: any)
				return UI.compile({
					name = "X",
					root = { type = "panel", name = "R", size = { 400, 200 }, children = { node } },
				}, ids, art)
			end
			local function kid(inst: any, name: string): any
				for _, c in inst.Children or {} do
					if c.Name == name then
						return c
					end
				end
				return nil
			end
			local model, issues = fx({
				type = "image",
				name = "Neck",
				image = "art:riff/neck",
				size = { 64, 64 },
				fx = {
					{ kind = "shimmer", period = 3, color = "#ffffff" },
					{ kind = "ping" },
					{ kind = "burn_in", dur = 0.5 },
					{ kind = "split", px = 6 },
				},
			})
			check.is_true(not said(issues, ""))
			local neck = model.Children[1].Children[1]
			local shim = kid(neck, "Fx_Shimmer")
			check.is_true(shim ~= nil)
			check.equal(shim.Properties.Image, "rbxassetid://21") -- (the white glint, not the picture)
			check.equal(kid(shim, "Band").ClassName, "UIGradient")
			check.equal(kid(shim, "Band").Properties.Offset.Vector2[1], -1) -- (invisible at rest)
			check.equal(kid(kid(neck, "Fx_Ping"), "Grow").ClassName, "UIScale")
			check.equal(kid(neck, "Fx_Burn").Properties.Offset.Vector2[1], 1) -- (shown at rest)
			check.is_true(kid(neck, "Fx_SplitA") ~= nil and kid(neck, "Fx_SplitB") ~= nil)
			check.equal(kid(neck, "Fx_SplitC").Properties.Image, "rbxassetid://20") -- (the piece itself, on top of its ghosts)
			local enc = neck.Properties.Attributes.Attributes.Kit_Fx.String
			check.is_true(string.find(enc, "shimmer:", 1, true) ~= nil and string.find(enc, "period=3", 1, true) ~= nil)
			check.is_true(string.find(enc, "split:", 1, true) ~= nil)
			local fm, fi =
				fx({ type = "label", name = "F", text = "HOLO", size = { 120, 40 }, fx = { { kind = "flicker" } } })
			check.is_true(not said(fi, ""))
			check.equal(kid(fm.Children[1].Children[1], "Fx_Flicker").ClassName, "UIGradient") -- (dips without touching the node)
			check.is_true(said(
				select(
					2,
					fx({
						type = "label",
						name = "F",
						text = "HOLO",
						size = { 120, 40 },
						fx = { { kind = "flicker" }, { kind = "burn_in" } },
					})
				),
				"pick one"
			))
			-- text gets a text copy; no glint needed
			local tm, ti =
				fx({ type = "label", name = "T", text = "SMASH", size = { 200, 60 }, fx = { { kind = "shimmer" } } })
			check.is_true(not said(ti, ""))
			check.equal(kid(tm.Children[1].Children[1], "Fx_Shimmer").ClassName, "TextLabel")
			-- errors: an unknown kind, a value out of range, an unknown key, a picture with no glint, burn_in on a gradient
			check.is_true(
				said(
					select(
						2,
						fx({ type = "label", name = "T", text = "A", size = { 99, 40 }, fx = { { kind = "wobble" } } })
					),
					'unknown fx "wobble"'
				)
			)
			check.is_true(said(
				select(
					2,
					fx({
						type = "label",
						name = "T",
						text = "A",
						size = { 99, 40 },
						fx = { { kind = "ping", scale = 9 } },
					})
				),
				"ping.scale must be"
			))
			check.is_true(said(
				select(
					2,
					fx({
						type = "label",
						name = "T",
						text = "A",
						size = { 99, 40 },
						fx = { { kind = "ping", speed = 2 } },
					})
				),
				'ping has no "speed"'
			))
			check.is_true(said(
				select(
					2,
					fx({
						type = "image",
						name = "B",
						image = "art:riff/bare",
						size = { 64, 64 },
						fx = { { kind = "shimmer" } },
					})
				),
				'no glint "riff/bare__glint"'
			))
			check.is_true(said(
				select(
					2,
					fx({
						type = "panel",
						name = "P",
						size = { 99, 40 },
						gradient = "auto",
						color = "#334455",
						fx = { { kind = "burn_in" } },
					})
				),
				"one UIGradient per node"
			))
		end)
		test.case(
			'"states" compile every designed look; bad ones are errors; a hero screen warns on bare buttons',
			function()
				local art = { ["sim/pill_panel"] = { size = 64 } }
				local ids = { ui = { ["sim/pill_panel"] = "rbxassetid://30" } }
				local function said(issues: { any }, needle: string, sev: string?): boolean
					for _, it in issues do
						if it.severity == (sev or "error") and string.find(it.message, needle, 1, true) then
							return true
						end
					end
					return false
				end
				local function compileOne(btn: any, quality: string?)
					return UI.compile({
						name = "B",
						quality = quality,
						root = { type = "panel", name = "R", size = { 400, 200 }, children = { btn } },
					}, ids, art)
				end
				local model, issues = compileOne({
					type = "button",
					name = "Buy",
					text = "BUY",
					size = { 160, 56 },
					states = {
						hover = { textColor = "#ffc93c" },
						disabled = { image = "art:sim/pill_panel", imageAlpha = 0.4, text = "SOLD" },
					},
				})
				check.is_true(not said(issues, ""))
				local a = model.Children[1].Children[1].Properties.Attributes.Attributes
				check.equal(a.Kit_States.String, "hover,disabled")
				check.equal(a.Kit_S_hover.String, "textColor=#ffc93c")
				check.is_true(string.find(a.Kit_S_disabled.String, "image=rbxassetid://30", 1, true) ~= nil)
				check.is_true(string.find(a.Kit_S_disabled.String, "art=sim/pill_panel", 1, true) ~= nil)
				check.is_true(string.find(a.Kit_S_disabled.String, "text=SOLD", 1, true) ~= nil)
				local function bad(states: any): { any }
					local _, iss =
						compileOne({ type = "button", name = "X", text = "X", size = { 160, 56 }, states = states })
					return iss
				end
				check.is_true(said(bad({ wobble = { color = "#ffffff" } }), 'unknown state "wobble"'))
				check.is_true(said(bad({ hover = { scale = 2 } }), 'not "scale"'))
				check.is_true(said(bad({ hover = { imageAlpha = 3 } }), "imageAlpha must be a number 0..1"))
				check.is_true(said(bad({ hover = { text = "a;b" } }), "text must be a string without"))
				local _, hero = compileOne({ type = "button", name = "Y", text = "Y", size = { 160, 56 } }, "hero")
				check.is_true(said(hero, 'button(s) with no "states"', "warn"))
			end
		)
		test.case(
			"gamepad: nav links, firstFocus, the focus piece and pad glyphs compile; bad ones are errors",
			function()
				local art = { ["sim/frame_line"] = { size = 64, slice = { 20, 20, 44, 44 } }, keycap = { size = 64 } }
				local ids = { ui = { ["sim/frame_line"] = "rbxassetid://40", keycap = "rbxassetid://41" } }
				local identities = {
					sim = {
						tokens = {},
						fonts = { font = "FredokaOne", titleFont = "LuckiestGuy", monoFont = "FredokaOne" },
					},
				}
				local function said(issues: { any }, needle: string, sev: string?): boolean
					for _, it in issues do
						if it.severity == (sev or "error") and string.find(it.message, needle, 1, true) then
							return true
						end
					end
					return false
				end
				local function compileOne(extra: any, kids: { any })
					local spec = {
						name = "G",
						root = { type = "panel", name = "R", size = { 400, 200 }, children = kids },
					}
					for k, v in extra do
						spec[k] = v
					end
					return UI.compile(spec, ids, art, identities)
				end
				local a = { type = "button", name = "A", text = "A", size = { 120, 50 }, nav = { right = "R.B" } }
				local b = { type = "button", name = "B", text = "B", size = { 120, 50 }, pos = { 200, 0 } }
				local hint = { type = "keyhint", name = "Hint", key = "E", text = "Use", glyph = { pad = "ButtonX" } }
				local model, issues = compileOne({ firstFocus = "R.A", identity = "sim" }, { a, b, hint })
				check.is_true(not said(issues, ""))
				local sa = model.Properties.Attributes.Attributes
				check.equal(sa.Kit_FirstFocus.String, "R.A")
				check.equal(sa.Kit_FocusArt.String, "rbxassetid://40") -- (the identity's outline, not the blue box)
				check.equal(sa.Kit_FocusSlice.String, "20,20,44,44")
				local root = model.Children[1]
				check.equal(root.Children[1].Properties.Attributes.Attributes.Kit_NavRight.String, "R.B")
				check.equal(root.Children[3].Properties.Attributes.Attributes.Kit_GlyphPad.String, "ButtonX")
				check.equal(root.Children[3].Properties.Attributes.Attributes.Kit_GlyphTouch.String, "hide")
				local function with(extra: any, kids: { any }): { any }
					local _, iss = compileOne(extra, kids)
					return iss
				end
				check.is_true(
					said(
						with(
							{},
							{ { type = "button", name = "A", text = "A", size = { 99, 40 }, nav = { up = "R.Nope" } } }
						),
						'no node "R.Nope"'
					)
				)
				check.is_true(said(
					with({}, {
						{ type = "button", name = "A", text = "A", size = { 99, 40 }, nav = { up = "R.T" } },
						{ type = "label", name = "T", text = "t", size = { 99, 40 } },
					}),
					"the d-pad only lands on buttons"
				))
				check.is_true(said(
					with({}, {
						{
							type = "button",
							name = "A",
							text = "A",
							size = { 99, 40 },
							nav = { sideways = "R.A" },
						},
					}),
					"nav keys: up | down | left | right"
				))
				check.is_true(said(with({ firstFocus = "R.Zip" }, { a, b }), "firstFocus must name a button"))
				check.is_true(
					said(
						with(
							{},
							{ { type = "keyhint", name = "H", key = "E", text = "x", glyph = { pad = "ButtonZ" } } }
						),
						"pad is a gamepad KeyCode"
					)
				)
				check.is_true(said(with({ quality = "hero" }, { a, b }), 'no "firstFocus"', "warn"))
			end
		)
		test.case(
			'a "path" compiles to a vector line (Kit_Path shares, stroke colour, outline, draw-on); bad ones are errors',
			function()
				local function said(issues: { any }, needle: string): boolean
					for _, it in issues do
						if it.severity == "error" and string.find(it.message, needle, 1, true) then
							return true
						end
					end
					return false
				end
				local function one(node: any)
					return UI.compile({
						name = "P",
						root = { type = "panel", name = "R", size = { 400, 200 }, children = { node } },
					})
				end
				local model, issues = one({
					type = "path",
					name = "Line",
					size = { 200, 100 },
					points = { { 0, 0 }, { 100, 50 }, { 200, 100 } },
					color = "#ff0000",
					thickness = 3,
					outline = { color = "#000000", px = 2 },
					draw = { dur = 0.5, delay = 0.1 },
				})
				check.is_true(not said(issues, ""))
				local line = model.Children[1].Children[1]
				local a = line.Properties.Attributes.Attributes
				check.equal(a.Kit_Path.String, "0.0000,0.0000;0.5000,0.5000;1.0000,1.0000") -- (shares of the box)
				check.equal(a.Kit_PathColor.String, "#ff0000")
				check.equal(a.Kit_PathOutline.String, "#000000,2")
				check.equal(a.Kit_PathDraw.String, "0.5,0.1")
				check.equal(line.Properties.BackgroundTransparency, 1) -- (its colour is the stroke, not a fill)
				local arc =
					one({ type = "path", name = "Arc", size = { 100, 100 }, arc = { from = 0, to = 90, r = 0.5 } })
				local pts = arc.Children[1].Children[1].Properties.Attributes.Attributes.Kit_Path.String
				check.is_true(string.sub(pts, 1, 13) == "1.0000,0.5000") -- (0 degrees = the right edge)
				check.is_true(
					said(
						select(
							2,
							one({ type = "path", name = "X", size = { "50%", 10 }, points = { { 0, 0 }, { 1, 1 } } })
						),
						"a path needs a size in pixels"
					)
				)
				check.is_true(
					said(
						select(2, one({ type = "path", name = "X", size = { 10, 10 }, points = { { 0, 0 } } })),
						'a path needs "points"'
					)
				)
				check.is_true(said(
					select(
						2,
						one({
							type = "path",
							name = "X",
							size = { 10, 10 },
							points = { { 0, 0 }, { 1, 1 } },
							thickness = 99,
						})
					),
					"thickness is pixels"
				))
			end
		)
		test.case("burst presets compile onto the screen; a node's burst names one; bad ones are errors", function()
			local art = { spark = { size = 64 } }
			local ids = { ui = { spark = "rbxassetid://50" } }
			local function said(issues: { any }, needle: string): boolean
				for _, it in issues do
					if it.severity == "error" and string.find(it.message, needle, 1, true) then
						return true
					end
				end
				return false
			end
			local function compileOne(bursts: any, node: any)
				return UI.compile({
					name = "U",
					bursts = bursts,
					root = { type = "panel", name = "R", size = { 400, 200 }, children = { node } },
				}, ids, art)
			end
			local pop = { sprite = "art:spark", count = 12, speed = { 100, 300 }, colors = { "#ff0000" } }
			local label = { type = "label", name = "Pop", text = "POP", size = { 99, 40 }, burst = "pop" }
			local model, issues = compileOne({ pop = pop }, label)
			check.is_true(not said(issues, ""))
			local enc = model.Properties.Attributes.Attributes.Kit_Burst_pop.String
			check.is_true(string.find(enc, "sprite=rbxassetid://50", 1, true) ~= nil)
			check.is_true(
				string.find(enc, "count=12", 1, true) ~= nil and string.find(enc, "speed=100,300", 1, true) ~= nil
			)
			check.is_true(string.find(enc, "colors=#ff0000", 1, true) ~= nil)
			local a = model.Children[1].Children[1].Properties.Attributes.Attributes
			check.equal(a.Kit_BurstPreset.String, "pop")
			check.equal(a.Kit_BurstOn.String, "show")
			check.is_true(
				said(
					select(
						2,
						compileOne(
							{ pop = pop },
							{ type = "label", name = "P", text = "P", size = { 99, 40 }, burst = "nope" }
						)
					),
					'no burst preset "nope"'
				)
			)
			check.is_true(said(select(2, compileOne({ pop = { count = 999 } }, label)), "count must be a number"))
			check.is_true(said(select(2, compileOne({ pop = { speed = { 5, 1 } } }, label)), "speed is [low, high]"))
			check.is_true(said(select(2, compileOne({ pop = { wobble = 1 } }, label)), 'a burst has no "wobble"'))
		end)
		test.case('"space": "world" compiles a BillboardGui / SurfaceGui template; bad ones are errors', function()
			local function said(issues: { any }, needle: string): boolean
				for _, it in issues do
					if it.severity == "error" and string.find(it.message, needle, 1, true) then
						return true
					end
				end
				return false
			end
			local function world(w: any, size: any?)
				return UI.compile({
					name = "W",
					space = "world",
					world = w,
					root = { type = "panel", name = "R", size = size or { 240, 70 } },
				})
			end
			local bb, issues =
				world({ kind = "billboard", offset = { 0, 3, 0 }, distance = { near = 10, far = 100, min = 0.5 } })
			check.is_true(not said(issues, ""))
			check.equal(bb.ClassName, "BillboardGui")
			check.equal(bb.Properties.Size.UDim2[1][2], 240) -- (the root's pixels are the canvas)
			check.equal(bb.Properties.StudsOffset.Vector3[2], 3)
			check.equal(bb.Properties.Attributes.Attributes.Kit_DistMin.Float64, 0.5)
			local sg = world({ kind = "surface", face = "Top" })
			check.equal(sg.ClassName, "SurfaceGui")
			check.equal(sg.Properties.Face, "Top")
			check.equal(sg.Properties.CanvasSize.Vector2[2], 70)
			check.is_true(said(select(2, world({ kind = "hologram" })), 'kind is "billboard" or "surface"'))
			check.is_true(said(select(2, world({ distance = { near = 50, far = 10, min = 0.5 } })), "distance:"))
			check.is_true(said(select(2, world({}, { "100%", 70 })), "needs a pixel size"))
			check.is_true(said(select(2, world({ kind = "surface", face = "Inside" })), "face is Front"))
		end)
		test.case("a state told by hue alone warns (XAG 103); a lightness step does not", function()
			local function warned(issues: { any }): boolean
				for _, it in issues do
					if it.severity == "warn" and string.find(it.message, "HUE alone", 1, true) then
						return true
					end
				end
				return false
			end
			local function btn(idle: string, sel: string)
				local _, issues = UI.compile({
					name = "H",
					root = {
						type = "panel",
						name = "R",
						size = { 400, 200 },
						children = {
							{
								type = "button",
								name = "B",
								text = "B",
								size = { 160, 56 },
								textColor = idle,
								states = { selected = { textColor = sel } },
							},
						},
					},
				})
				return issues
			end
			check.is_true(warned(btn("#ff0000", "#009900"))) -- (red / green at one lightness)
			check.is_true(not warned(btn("#ffffff", "#333333"))) -- (a lightness step)
		end)
		test.case(
			"an atlased piece shows its uploaded sheet through ImageRect; a swapped picture keeps its own",
			function()
				local art = {
					["zz/icon"] = { size = 64, atlas = { "atlas_0", 2, 70, 64, 64 } },
					["zz/frame0"] = { size = 64, atlas = { "atlas_0", 70, 2, 64, 64 } },
					["zz/atlas_0"] = { size = 1024 },
				}
				local ids = {
					ui = {
						["zz/icon"] = "rbxassetid://61",
						["zz/frame0"] = "rbxassetid://62",
						["zz/atlas_0"] = "rbxassetid://60",
					},
				}
				local model = UI.compile({
					name = "A",
					root = {
						type = "panel",
						name = "R",
						size = { 400, 200 },
						children = {
							{ type = "image", name = "Icon", image = "art:zz/icon", size = { 64, 64 } },
							{
								type = "image",
								name = "Flip",
								flipbook = { frames = { "zz/frame0" }, fps = 12 },
								size = { 64, 64 },
							},
						},
					},
				}, ids, art)
				local icon, flip = model.Children[1].Children[1], model.Children[1].Children[2]
				check.equal(icon.Properties.Image, "rbxassetid://60") -- (the sheet)
				check.equal(icon.Properties.ImageRectOffset.Vector2[2], 70)
				check.equal(icon.Properties.ImageRectSize.Vector2[1], 64)
				check.equal(flip.Properties.Image, "rbxassetid://62") -- (a flipbook swaps its picture: its own upload)
				check.equal(flip.Properties.ImageRectSize, nil)
				check.equal(model.Properties.Attributes.Attributes.Kit_Atlased.Float64, 1)
			end
		)
		test.case('"sounds" name Sfx events per moment, checked against the catalog', function()
			local events = { UiClick = true, UiHover = true }
			local function said(issues: { any }, needle: string): boolean
				for _, it in issues do
					if it.severity == "error" and string.find(it.message, needle, 1, true) then
						return true
					end
				end
				return false
			end
			local function one(sounds: any)
				return UI.compile({
					name = "S",
					root = {
						type = "panel",
						name = "R",
						size = { 400, 200 },
						children = { { type = "button", name = "B", text = "B", size = { 160, 56 }, sounds = sounds } },
					},
				}, nil, nil, nil, events)
			end
			local model, issues = one({ hover = "UiHover", press = "UiClick" })
			check.is_true(not said(issues, ""))
			local a = model.Children[1].Children[1].Properties.Attributes.Attributes
			check.equal(a.Kit_Snd_hover.String, "UiHover")
			check.equal(a.Kit_Snd_press.String, "UiClick")
			check.is_true(said(select(2, one({ press = "Boom" })), 'no Sfx event "Boom"'))
			check.is_true(said(select(2, one({ wiggle = "UiClick" })), "sound moments:"))
		end)
		test.case("a viewport showcase: light direction and drag-to-turn compile; bad ones are errors", function()
			local function said(issues: { any }, needle: string): boolean
				for _, it in issues do
					if it.severity == "error" and string.find(it.message, needle, 1, true) then
						return true
					end
				end
				return false
			end
			local function vp(extra: any)
				local node: any = { type = "viewport", name = "Show", model = "Sword", size = { 300, 300 }, spin = 0.4 }
				for k, v in extra do
					node[k] = v
				end
				return UI.compile({
					name = "V",
					root = { type = "panel", name = "R", size = { 400, 400 }, children = { node } },
				})
			end
			local model, issues = vp({ lightDirection = { -1, -1, -0.5 }, drag = true })
			check.is_true(not said(issues, ""))
			local show = model.Children[1].Children[1]
			check.equal(show.ClassName, "ViewportFrame")
			check.equal(show.Properties.LightDirection.Vector3[3], -0.5)
			check.equal(show.Properties.Attributes.Attributes.Kit_ModelDrag.Bool, true)
			check.is_true(said(select(2, vp({ lightDirection = { 1, 2 } })), "lightDirection is [x, y, z]"))
			check.is_true(said(select(2, vp({ drag = "yes" })), "drag is true"))
		end)
		test.case('a menu "backdrop" compiles onto the screen; bad keys and ranges are errors', function()
			local function said(issues: { any }, needle: string): boolean
				for _, it in issues do
					if it.severity == "error" and string.find(it.message, needle, 1, true) then
						return true
					end
				end
				return false
			end
			local function menu(backdrop: any)
				return UI.compile({
					name = "M",
					backdrop = backdrop,
					root = { type = "panel", name = "R", size = { 400, 200 } },
				})
			end
			local model, issues = menu({ blur = 24, darken = 0.5 })
			check.is_true(not said(issues, ""))
			local b = model.Properties.Attributes.Attributes.Kit_Backdrop.String
			check.is_true(string.find(b, "blur=24", 1, true) ~= nil and string.find(b, "sat=-0.4", 1, true) ~= nil)
			check.is_true(said(select(2, menu({ blur = 99 })), "blur must be a number"))
			check.is_true(said(select(2, menu({ glow = 1 })), "backdrop keys:"))
		end)
		test.case(
			"a glyphs label sets any text in a bitmap font: proportional, kerned, wrapped; the map rides on it",
			function()
				local font = {
					cell = { 100, 100 },
					ink = { A = { 0.1, 0.8 }, V = { 0.1, 0.8 }, la = { 0.2, 0.5 } },
					space = 0.3,
					track = 0,
					kern = { AV = -0.2 },
					codes = { A = "A", V = "V", a = "la" },
				}
				local art = {
					["zz/f__font"] = { font = font },
					["zz/f_A"] = { size = 100, atlas = { "atlas_0", 2, 2, 100, 100 } },
					["zz/f_V"] = { size = 100 },
					["zz/f_la"] = { size = 100 },
					["zz/atlas_0"] = { size = 1024 },
				}
				local ids = {
					ui = {
						["zz/f_A"] = "rbxassetid://1",
						["zz/f_V"] = "rbxassetid://2",
						["zz/f_la"] = "rbxassetid://3",
						["zz/atlas_0"] = "rbxassetid://9",
					},
				}
				local function one(text: string, w: number)
					return UI.compile({
						name = "T",
						root = {
							type = "panel",
							name = "R",
							size = { 600, 400 },
							children = {
								{
									type = "label",
									name = "Words",
									glyphs = "zz/f",
									text = text,
									size = { w, 200 },
									lineHeight = 100,
								},
							},
						},
					}, ids, art)
				end
				local model, issues = one("AV a", 600)
				for _, it in issues do
					check.is_true(it.severity ~= "error")
				end
				local words = model.Children[1].Children[1]
				local a = words.Properties.Attributes.Attributes
				check.equal(a.Kit_GText.String, "AV a")
				check.is_true(string.find(a.Kit_GIds.String, "A=rbxassetid://9@2,2,100,100", 1, true) ~= nil) -- (an atlased glyph: sheet + rect)
				check.is_true(string.find(a.Kit_GKern.String, "AV=-0.2", 1, true) ~= nil)
				local g1, g2 = words.Children[1], words.Children[2]
				-- A advances its ink (80) + kern (-20) = 60; V's ink starts 10 in: drawn at 60 - 10 = 50
				check.equal(g2.Properties.Position.UDim2[1][2] - g1.Properties.Position.UDim2[1][2], 60)
				check.equal(#words.Children, 3) -- (the space is an advance, not a picture)
				local wrapped = one("AV AV AV", 220).Children[1].Children[1]
				local lastY = wrapped.Children[#wrapped.Children].Properties.Position.UDim2[2][2]
				check.is_true(lastY >= 100) -- (wrapped onto a second line)
				local _, bad = UI.compile({
					name = "T",
					root = {
						type = "panel",
						name = "R",
						size = { 600, 400 },
						children = { { type = "label", name = "W", glyphs = "zz/none", text = "A", size = { 99, 40 } } },
					},
				}, ids, art)
				local said = false
				for _, it in bad do
					said = said
						or (it.severity == "error" and string.find(it.message, "no bitmap font", 1, true) ~= nil)
				end
				check.is_true(said)
			end
		)
		test.case("HUD systems compile: a world marker, a compass bar, a directional damage ring", function()
			local model, issues = UI.compile({
				name = "H",
				root = {
					type = "panel",
					name = "R",
					size = { "100%", "100%" },
					children = {
						{ type = "marker", name = "Goal" },
						{ type = "compass", name = "Compass", size = { 600, 44 }, degrees = 180 },
						{ type = "damage", name = "Hurt", size = { 300, 300 } },
					},
				},
			})
			for _, it in issues do
				check.is_true(it.severity ~= "error")
			end
			local function kid(inst: any, name: string): any
				for _, c in inst.Children or {} do
					if c.Name == name then
						return c
					end
				end
				return nil
			end
			local root = model.Children[1]
			local goal, compass, hurt = kid(root, "Goal"), kid(root, "Compass"), kid(root, "Hurt")
			check.equal(goal.Properties.Attributes.Attributes.Kit_Marker.String, "ellipse")
			check.is_true(kid(kid(goal, "Pivot"), "Arrow").Properties.Attributes.Attributes.Kit_Path ~= nil) -- (a vector arrow)
			check.equal(compass.Properties.ClipsDescendants, true)
			check.equal(compass.Properties.Attributes.Attributes.Kit_Compass.Float64, 600 / 180)
			check.is_true(kid(kid(compass, "Strip"), "L360").Properties.Text == "N") -- (north at the strip's centre)
			check.equal(kid(hurt, "Wedge").Properties.Visible, false)
		end)
		test.case('menu systems compile: a toast queue, a tooltip, a node\'s "tip" with compare lines', function()
			local model, issues = UI.compile({
				name = "Mn",
				root = {
					type = "panel",
					name = "R",
					size = { "100%", "100%" },
					children = {
						{ type = "toasts", name = "Toasts", max = 2 },
						{ type = "tooltip", name = "Tooltip" },
						{
							type = "button",
							name = "Sword",
							text = "Sword",
							size = { 160, 56 },
							tip = { title = "Iron Sword", lines = { "+12 ATK", "-3 SPD" } },
						},
					},
				},
			})
			for _, it in issues do
				check.is_true(it.severity ~= "error")
			end
			local kids = {}
			for _, c in model.Children[1].Children do
				kids[c.Name] = c
			end
			check.equal(kids.Toasts.Properties.Attributes.Attributes.Kit_Toasts.Float64, 2)
			check.equal(kids.Tooltip.Properties.Attributes.Attributes.Kit_Tooltip.Bool, true)
			local a = kids.Sword.Properties.Attributes.Attributes
			check.equal(a.Kit_Tip.String, "Iron Sword")
			check.equal(a.Kit_TipLines.String, "+12 ATK" .. string.char(10) .. "-3 SPD")
		end)
		test.case('"haptic" pulses on the sound moments; "console" marks a TV screen; bad ones are errors', function()
			local function one(extra: any, node: any)
				local spec: any =
					{ name = "Hp", root = { type = "panel", name = "R", size = { 400, 200 }, children = { node } } }
				for k, v in extra do
					spec[k] = v
				end
				return UI.compile(spec)
			end
			local btn =
				{ type = "button", name = "Buy", text = "Buy", size = { 160, 56 }, haptic = { press = "heavy" } }
			local model, issues = one({ console = true }, btn)
			for _, it in issues do
				check.is_true(it.severity ~= "error")
			end
			check.equal(model.Children[1].Children[1].Properties.Attributes.Attributes.Kit_Hap_press.String, "heavy")
			check.equal(model.Properties.Attributes.Attributes.Kit_Console.Bool, true)
			local _, bad = one(
				{},
				{ type = "button", name = "B", text = "B", size = { 160, 56 }, haptic = { press = "buzz" } }
			)
			local said = false
			for _, it in bad do
				said = said or (it.severity == "error" and string.find(it.message, "haptic moments", 1, true) ~= nil)
			end
			check.is_true(said)
		end)
		test.case(
			"typography: sizes too close warn on a hero screen; a counter in a proportional face warns",
			function()
				local function warned(issues: { any }, needle: string): boolean
					for _, it in issues do
						if it.severity == "warn" and string.find(it.message, needle, 1, true) then
							return true
						end
					end
					return false
				end
				local _, issues = UI.compile({
					name = "Ty",
					quality = "hero",
					root = {
						type = "panel",
						name = "R",
						size = { 600, 400 },
						children = {
							{ type = "label", name = "A", text = "Title", textSize = 40, size = { 300, 50 } },
							{
								type = "label",
								name = "B",
								text = "Sub",
								textSize = 19,
								size = { 300, 30 },
								pos = { 0, 60 },
							},
							{
								type = "label",
								name = "C",
								text = "Body",
								textSize = 18,
								size = { 300, 30 },
								pos = { 0, 100 },
							},
							{
								type = "counter",
								name = "Gold",
								value = 120,
								font = "Bangers",
								textSize = 28,
								size = { 200, 40 },
								pos = { 0, 140 },
							},
						},
					},
				})
				check.is_true(warned(issues, "type sizes too close"))
				check.is_true(warned(issues, "jitters as it counts"))
			end
		)
		test.case('a screen carries its budget; "bind" names a store key; a bad key is an error', function()
			local model, issues = UI.compile({
				name = "Bd",
				root = {
					type = "panel",
					name = "R",
					size = { 400, 200 },
					children = {
						{
							type = "label",
							name = "Coins",
							text = "0",
							textSize = 24,
							bind = "player.coins",
							size = { 200, 40 },
						},
					},
				},
			})
			for _, it in issues do
				check.is_true(it.severity ~= "error")
			end
			check.is_true(
				string.find(model.Properties.Attributes.Attributes.Kit_Budget.String, "instances=", 1, true) ~= nil
			)
			check.equal(model.Children[1].Children[1].Properties.Attributes.Attributes.Kit_Bind.String, "player.coins")
			local _, bad = UI.compile({
				name = "Bd",
				root = {
					type = "panel",
					name = "R",
					size = { 400, 200 },
					children = { { type = "label", name = "L", text = "x", size = { 99, 40 }, bind = "a b" } },
				},
			})
			local said = false
			for _, it in bad do
				said = said or (it.severity == "error" and string.find(it.message, "bind:", 1, true) ~= nil)
			end
			check.is_true(said)
		end)
		test.case('"nativeShadow" emits the engine\'s UIShadow (shape or text) with whole-pixel geometry', function()
			local function shadowed(ns: any)
				return UI.compile({
					name = "S",
					root = {
						type = "panel",
						name = "R",
						size = { 400, 200 },
						children = {
							{ type = "label", name = "T", text = "HI", size = { 200, 60 }, nativeShadow = ns },
						},
					},
				})
			end
			local model, issues = shadowed({ blur = 10.4, offset = { 2, 5 }, alpha = 0.5, text = true })
			for _, it in issues do
				check.is_true(it.severity ~= "error" or string.find(it.message, "nativeShadow", 1, true) == nil)
			end
			local label = model.Children[1].Children[1]
			local sh = nil
			for _, c in label.Children or {} do
				if c.ClassName == "UIShadow" then
					sh = c
				end
			end
			check.truthy(sh)
			if sh then
				check.equal(sh.Properties.BlurRadius.UDim[2], 10)
				check.equal(sh.Properties.Offset.UDim2[2][2], 5)
				check.equal(sh.Properties.Mode, "Text")
				check.equal(sh.Properties.Transparency, 0.5)
			end
			local _, bad = shadowed({ alpha = 2 })
			local found = false
			for _, it in bad do
				found = found or (it.severity == "error" and string.find(it.message, "nativeShadow", 1, true) ~= nil)
			end
			check.is_true(found)
		end)
		test.case('a number node\'s "narrow" glyph takes a share of the advance (no "46 , 959")', function()
			local model = UI.compile({
				name = "N",
				root = {
					type = "panel",
					name = "R",
					size = { 400, 200 },
					children = {
						{
							type = "number",
							name = "S",
							digits = "riff/score",
							charset = "0123456789,",
							aspect = 0.5,
							narrow = { [","] = 0.4 },
							text = "4,9",
							size = { 200, 100 },
							align = "left",
						},
					},
				},
			})
			local s = model.Children[1].Children[1]
			local function x(i: number): number
				return s.Children[i].Properties.Position.UDim2[1][2]
			end
			-- cell 50 px, advance 50; the comma's slot is 20: the 9 sits 50 + 20 = 70 px after the 4, not 100
			check.equal(x(3) - x(1), 70)
			check.equal(s.Properties.Attributes.Attributes.Kit_DigitNarrow.String, "u44=0.4")
		end)
		test.case("small touch target is a warning", function()
			local _, warns =
				messages(screen({ { type = "button", name = "B", text = "Go", size = { 100, 30 }, color = "bg" } }))
			check.is_true(string.find(warns, "44px", 1, true) ~= nil)
		end)
		test.case("duplicate sibling names are an error", function()
			local errors = messages(screen({
				{ type = "label", name = "Same", text = "a" },
				{ type = "label", name = "Same", text = "b" },
			}))
			check.is_true(string.find(errors, "duplicate", 1, true) ~= nil)
		end)
		test.case("bad sizes, types and colors are errors", function()
			local errors = messages(screen({
				{ type = "panel", name = "P", size = { "wide", 10 } },
				{ type = "slider", name = "S" },
				{ type = "panel", name = "C", color = "chartreuse" },
			}))
			check.is_true(string.find(errors, "pixels", 1, true) ~= nil)
			check.is_true(string.find(errors, "type must be", 1, true) ~= nil)
			check.is_true(string.find(errors, "not a theme name", 1, true) ~= nil)
		end)
		test.case("new element types validate their fields", function()
			local errors = messages(screen({
				{ type = "bar", name = "Hp", value = 1.5, color = "bg" },
				{ type = "panel", name = "Inv", layout = { grid = { "wide" } } },
				{ type = "panel", name = "Card", aspect = -1 },
				{ type = "imagebutton", name = "Icon" },
			}))
			check.is_true(string.find(errors, "bar value", 1, true) ~= nil)
			check.is_true(string.find(errors, "grid must be", 1, true) ~= nil)
			check.is_true(string.find(errors, "aspect must be", 1, true) ~= nil)
			check.is_true(string.find(errors, "image nodes need", 1, true) ~= nil)
		end)
		test.case("contrast math matches WCAG", function()
			check.is_true(math.abs(UI.contrast({ 0, 0, 0 }, { 1, 1, 1 }) - 21) < 0.01)
			check.is_true(math.abs(UI.contrast({ 1, 1, 1 }, { 1, 1, 1 }) - 1) < 0.01)
		end)
	end)

	test.suite("UI design system (skins, styles, components, art, motion)", function()
		local function find(inst: any, name: string): any
			if inst.Name == name then
				return inst
			end
			for _, c in inst.Children or {} do
				local hit = find(c, name)
				if hit then
					return hit
				end
			end
			return nil
		end
		test.case("a styled card is lit: gradient + stroke + corner from the skin", function()
			local model = UI.compile({
				name = "S",
				skin = "scifi",
				root = { type = "panel", name = "Card", style = "card", size = { 300, 120 } },
			})
			local card = model.Children[1]
			check.is_true(find(card, "Gradient") ~= nil)
			check.is_true(find(card, "Stroke") ~= nil)
			check.equal(find(card, "Corner").Properties.CornerRadius.UDim[2], UI.SKINS.scifi.radius.m)
		end)
		test.case("a big flat panel warns; the same panel with a style does not", function()
			local _, flat = messages({
				name = "F",
				skin = "clean",
				root = { type = "panel", name = "P", color = "panel", size = { 400, 200 } },
			})
			check.is_true(string.find(flat, "flat panel", 1, true) ~= nil)
			local _, styled = messages({
				name = "F",
				skin = "clean",
				root = { type = "panel", name = "P", style = "card", size = { 400, 200 } },
			})
			check.equal(string.find(styled, "flat panel", 1, true), nil)
		end)
		test.case("a ring component fills clockwise: half-gradient rotations follow the value", function()
			local model = UI.compile({
				name = "R",
				skin = "scifi",
				root = { type = "ring", name = "Cd", size = 64, value = 0.75 },
			})
			local ring = model.Children[1]
			local right = find(find(ring, "Right"), "Gradient")
			local left = find(find(ring, "Left"), "Gradient")
			check.equal(right.Properties.Rotation, 180)
			check.equal(left.Properties.Rotation, 270)
		end)
		test.case("kit art resolves from ids; missing art warns, unknown art errors", function()
			local art = { ring = { size = 256 }, keycap = { size = 128, slice = { 30, 30, 98, 90 } } }
			local spec = {
				name = "A",
				skin = "scifi",
				root = { type = "image", name = "I", image = "art:ring", size = { 64, 64 } },
			}
			local model = UI.compile(spec, { ui = { ring = "rbxassetid://5" } }, art)
			check.equal(model.Children[1].Properties.Image, "rbxassetid://5")
			local _, w = UI.compile(spec, {}, art)
			check.is_true(string.find(w[1].message, "not uploaded", 1, true) ~= nil)
			local errs = messages({ name = "A", root = { type = "image", name = "I", image = "art:nope" } })
			check.equal(errs, "") -- no art table given: cannot judge
			local _, issues = UI.compile(
				{ name = "A", root = { type = "image", name = "I", image = "art:nope" } },
				{},
				art
			)
			check.equal(issues[1].severity, "error")
		end)
		test.case("text on a tinted key cap is judged against the cap, not the card behind", function()
			local errors = messages({
				name = "K",
				skin = "scifi",
				root = {
					type = "panel",
					name = "Card",
					style = "card",
					size = { 300, 80 },
					children = { { type = "keyhint", name = "Fire", key = "LMB", text = "Fire" } },
				},
			})
			check.equal(errors, "")
		end)
		test.case("motion and slots become attributes and positions", function()
			local model = UI.compile({
				name = "M",
				skin = "clean",
				root = {
					type = "button",
					name = "Go",
					style = "primary",
					text = "GO",
					size = { 160, 48 },
					slot = "bottomRight",
				},
			})
			local b = model.Children[1]
			check.equal(b.Properties.Attributes.Attributes.Motion_hover.String, "lift")
			check.equal(b.Properties.Position.UDim2[1][1], 1)
			check.equal(b.Properties.AnchorPoint.Vector2[1], 1)
		end)
		test.case("tiny text is an error, small text a warning", function()
			local errors, warns = messages(screen({
				{ type = "label", name = "A", text = "x", textSize = 10, color = "bg" },
				{ type = "label", name = "B", text = "y", textSize = 13, color = "bg" },
			}))
			check.is_true(string.find(errors, "unreadable on a phone", 1, true) ~= nil)
			check.is_true(string.find(warns, "hard to read", 1, true) ~= nil)
		end)
	end)

	-- identity-first (v2): the look is decided in assets/ui/identities/<name>.json before any screen
	local IDENTITY = {
		souls = {
			name = "souls",
			tokens = {
				bg = "#0b0a09",
				panel = "#14110e",
				accent = "#c9b06a",
				text = "#e6dac0",
				muted = "#9c9076",
				hp = "#8e1b14",
				ghost = "#d9c07a",
			},
			fonts = { font = "Garamond", titleFont = "Garamond", monoFont = "Garamond" },
			radius = { s = 0, m = 0, l = 2 },
			roles = {
				death = { size = 96, font = "titleFont", color = "danger" },
				script = { size = 36, font = "Fondamento" },
			},
			motion = { enter = { type = "fade", duration = 0.9, ease = "sine" }, stagger = 0.08 },
		},
	}
	local ART = {
		["souls/frame"] = { size = 192, slice = { 64, 64, 128, 128 } },
		["souls/cap"] = { size = 48 },
		["souls/grain"] = { size = 256 },
		["souls/divider"] = { size = { 512, 24 } },
		["souls/torn"] = { size = { 240, 120 } }, -- (the Persona-type cutouts every identity gets drawn)
		["souls/torn_black"] = { size = { 240, 120 } },
		["souls/w_new_game"] = { size = { 600, 150 }, file = true },
		ring = { size = 256 },
	}
	local function findIn(inst: any, name: string): any
		if inst.Name == name then
			return inst
		end
		for _, c in inst.Children or {} do
			local hit = findIn(c, name)
			if hit then
				return hit
			end
		end
		return nil
	end
	local function souls(root: any, extra: any?): (any, { any })
		local spec = { name = "T", identity = "souls", root = root }
		for k, v in extra or {} do
			spec[k] = v
		end
		return UI.compile(spec, {}, ART, IDENTITY)
	end
	local function errorsOf(issues: { any }): number
		local n = 0
		for _, i in issues do
			if i.severity == "error" then
				n += 1
			end
		end
		return n
	end
	local function says(issues: { any }, needle: string, severity: string?): boolean
		for _, i in issues do
			if string.find(i.message, needle, 1, true) and (severity == nil or i.severity == severity) then
				return true
			end
		end
		return false
	end

	test.suite("UI identity packs", function()
		test.case("an identity sets tokens, fonts, radii and roles; its name rides on the ScreenGui", function()
			local model, issues = souls({
				type = "panel",
				name = "P",
				color = "panel",
				size = { 300, 100 },
				children = { { type = "label", name = "T", text = "YOU DIED", role = "death" } },
			})
			check.equal(errorsOf(issues), 0)
			local attrs = model.Properties.Attributes.Attributes
			check.equal(attrs.Kit_accent.String, "#c9b06a")
			check.equal(attrs.Kit_Identity.String, "souls")
			check.equal(attrs.Kit_Font.String, "Garamond")
			local t = findIn(model, "T")
			check.equal(t.Properties.Font, "Garamond")
			check.equal(t.Properties.TextSize, 96)
			check.equal(t.Properties.TextColor3.Color3[1] > 0.6, true) -- danger red from the default tokens
		end)
		test.case("ransom lettering: every glyph its own cutout, sizes and leans vary, some inverted", function()
			local model, issues = souls({
				type = "label",
				name = "Word",
				text = "SKILL",
				textSize = 40,
				ransom = true,
			})
			check.equal(errorsOf(issues), 0)
			local word = findIn(model, "Word")
			check.equal(word.Properties.Attributes.Attributes.Kit_Ransom.Bool, true)
			-- the runtime rebuilds a ransom word from the recipe: the seed and which glyphs are inverted travel with it
			check.equal(word.Properties.Attributes.Attributes.Kit_RansomSeed ~= nil, true)
			local g2 = findIn(word, "G2") -- (pattern 2 is inverted: a paper scrap, ink letter)
			check.equal(g2.Properties.Attributes.Attributes.Kit_Inverted.Bool, true)
			local row = findIn(word, "Glyphs")
			local sizes, plates, rots = {}, 0, 0
			for _, g in row.Children do
				if g.ClassName == "TextLabel" then
					sizes[g.Properties.TextSize] = true
					if (g.Properties.Rotation or 0) ~= 0 then
						rots += 1
					end
					for _, c in g.Children or {} do
						if c.Name == "Plate" then
							plates += 1
						end
					end
				end
			end
			local distinct = 0
			for _ in sizes do
				distinct += 1
			end
			check.equal(distinct > 1, true) -- sizes vary
			check.equal(plates, 5) -- every letter has its cutout
			check.equal(rots, 5) -- every letter leans
		end)
		test.case(
			"composition gates: level, lonely blocks and an accent wash warn against the identity's measured rules",
			function()
				local ident = table.clone(IDENTITY.souls)
				ident.rules = { lean_min = 4, lean_share = 0.6, overlap = true, accent_share = { 0.1, 0.3 } }
				local _, issues = UI.compile({
					name = "G",
					identity = "souls",
					quality = "hero",
					kind = "menu",
					focus = "Root.A.T",
					root = {
						type = "panel",
						name = "Root",
						size = { "100%", "100%" },
						children = {
							{
								type = "panel",
								name = "A",
								color = "accent",
								size = { 1920, 900 },
								pos = { 0, 0 },
								children = { { type = "label", name = "T", text = "X", role = "title" } },
							},
							{ type = "panel", name = "B", color = "panel", size = { 300, 100 }, pos = { 1500, 950 } },
							{ type = "panel", name = "C", color = "panel", size = { 300, 100 }, pos = { 100, 950 } },
						},
					},
				}, nil, ART, { souls = ident })
				local msgs = {}
				for _, i in issues do
					if string.find(i.message, "composition:", 1, true) then
						table.insert(msgs, i.message)
					end
				end
				local text = table.concat(msgs, " | ")
				check.equal(string.find(text, "lean", 1, true) ~= nil, true) -- nothing leans
				check.equal(string.find(text, "touch nothing", 1, true) ~= nil, true) -- B and C sit alone
				check.equal(string.find(text, "background, not the accent", 1, true) ~= nil, true) -- 80% accent vs 10-30%
			end
		)
		test.case("lettering: a label becomes its baked word art, sized from the piece, the text kept", function()
			local model, issues = souls({
				type = "label",
				name = "Logo",
				text = "New Game!",
				lettering = { scale = 0.5 },
			})
			check.equal(errorsOf(issues), 0)
			local logo = findIn(model, "Logo")
			check.equal(logo.ClassName, "ImageLabel")
			check.equal(logo.Properties.Attributes.Attributes.Kit_Text.String, "New Game!")
			check.equal(logo.Properties.Size.UDim2[1][2], 300) -- 600 x 0.5
			check.equal(logo.Properties.Attributes.Attributes.KitArt.String, "souls/w_new_game")
		end)
		test.case("lettering: a button keeps its decorations under the word", function()
			local model, issues = souls({
				type = "button",
				name = "Go",
				text = "NEW GAME",
				lettering = true,
				children = {
					{ type = "plate", name = "Splash", plate = "torn_black", size = { "100%", "100%" }, z = 3 },
				},
			})
			check.equal(errorsOf(issues), 0)
			local go = findIn(model, "Go")
			local word, splash = findIn(go, "Word"), findIn(go, "Splash")
			check.equal(word ~= nil and splash ~= nil, true)
			check.equal(word.Properties.ZIndex > splash.Properties.ZIndex, true)
		end)
		test.case("at.phone.scale shrinks a panel and everything inside it", function()
			local model, issues = souls({
				type = "panel",
				name = "Menu",
				size = { 400, 200 },
				pos = { 20, 20 },
				at = { phone = { scale = 0.5 } },
				children = { { type = "panel", name = "Item", size = { 100, 40 }, pos = { 60, 80 } } },
			})
			check.equal(errorsOf(issues), 0)
			local menu, item = findIn(model, "Menu"), findIn(model, "Item")
			check.equal(menu.Properties.Attributes.Attributes.Kit_At_phone.String, "Size=0,200,0,100")
			check.equal(item.Properties.Attributes.Attributes.Kit_At_phone.String, "Position=0,30,0,40|Size=0,50,0,20")
		end)
		test.case("at.scale scales a label's text with its box", function()
			local model, issues = souls({
				type = "panel",
				name = "Box",
				size = { 400, 100 },
				at = { phone = { scale = 0.5 } },
				children = { { type = "label", name = "L", text = "HELLO", textSize = 30, size = { 200, 40 } } },
			})
			check.equal(errorsOf(issues), 0)
			local l = findIn(model, "L")
			check.equal(
				string.find(l.Properties.Attributes.Attributes.Kit_At_phone.String, "TextSize=15", 1, true) ~= nil,
				true
			)
		end)
		test.case("fractional pixel offsets compile to whole pixels (Rojo refuses a fractional UDim)", function()
			local model, issues = souls({
				type = "panel",
				name = "Row",
				size = { 200.4, 40 },
				pos = { 10.6, 0 },
				layout = { dir = "horizontal", gap = 2.6 },
				children = { { type = "panel", name = "A", size = { 10, 10 } } },
			})
			check.equal(errorsOf(issues), 0)
			local row = findIn(model, "Row")
			check.equal(row.Properties.Size.UDim2[1][2], 200)
			check.equal(row.Properties.Position.UDim2[1][2], 11)
			check.equal(findIn(row, "Layout").Properties.Padding.UDim[2], 3)
		end)
		test.case(
			"the centre gate measures only screen-spanning parents: 50% of a minimap is not the screen centre",
			function()
				local _, issues = souls({
					type = "panel",
					name = "Map",
					size = { 240, 240 },
					pos = { 20, 20 },
					children = {
						{
							type = "panel",
							name = "Me",
							size = { 60, 60 },
							pos = { "50%", "50%" },
							anchor = "center",
							color = "text",
						},
					},
				}, { kind = "hud" })
				local blocked = false
				for _, i in issues do
					if string.find(i.message or "", "blocks the action", 1, true) then
						blocked = true
					end
				end
				check.equal(blocked, false)
			end
		)
		test.case("plateColor tints a label's / button's plate (an ink strip under paper type)", function()
			local model, issues = souls({
				type = "button",
				name = "Go",
				text = "GO",
				textColor = "bg",
				plate = "torn",
				plateColor = "text",
				size = { 200, 60 },
			})
			check.equal(errorsOf(issues), 0)
			local plate = findIn(findIn(model, "Go"), "Plate")
			check.equal(plate ~= nil, true)
			check.equal(plate.Properties.ImageColor3 ~= nil, true)
		end)
		test.case("stacked: a phrase becomes a stair of word cutouts, alternating ink / paper, each leaning", function()
			local model, issues = souls({
				type = "label",
				name = "Shout",
				text = "DONT LOOK AT ME",
				textSize = 40,
				stacked = true,
			})
			check.equal(errorsOf(issues), 0)
			local shout = findIn(model, "Shout")
			check.equal(shout.Properties.Attributes.Attributes.Kit_Stacked.Bool, true)
			local w1, w2 = findIn(shout, "W1"), findIn(shout, "W2")
			check.equal(w1 ~= nil and w2 ~= nil, true)
			check.equal(w1.Properties.Rotation ~= w2.Properties.Rotation, true)
			check.equal(findIn(w1, "Plate") ~= nil, true) -- its own cutout
			check.equal(w2.Properties.Position.UDim2[2][2] > w1.Properties.Position.UDim2[2][2], true) -- stepping down
		end)
		test.case("a role's font may be a face name, not only an identity font key", function()
			-- (a 'script' role on Fondamento fell back to the body face for a day: theme["Fondamento"] is nil)
			local model, issues = souls({
				type = "panel",
				name = "P",
				color = "panel",
				size = { 300, 100 },
				children = { { type = "label", name = "S", text = "Stylish", role = "script" } },
			})
			check.equal(errorsOf(issues), 0)
			local t = findIn(model, "S")
			check.equal(t.Properties.Font, "Fondamento")
			check.equal(t.Properties.TextSize, 36)
		end)
		test.case("an unknown identity is an error; a hero screen without one is an error", function()
			local _, a = UI.compile(
				{ name = "X", identity = "nope", root = { type = "panel", name = "P" } },
				{},
				ART,
				IDENTITY
			)
			check.is_true(says(a, "unknown identity", "error"))
			local _, b = UI.compile(
				{ name = "X", quality = "hero", root = { type = "panel", name = "P" } },
				{},
				ART,
				IDENTITY
			)
			check.is_true(says(b, 'needs an "identity"', "error"))
		end)
		test.case("the habit face under an identity warns; every Enum.Font is accepted", function()
			local _, issues = souls({ type = "label", name = "L", text = "x", font = "GothamBold", color = "panel" })
			check.is_true(says(issues, "habit face", "warn"))
			local _, ok = souls({ type = "label", name = "L", text = "x", font = "GrenzeGotisch", color = "panel" })
			check.is_true(not says(ok, "unknown font"))
			check.is_true(UI.FONTS.Merriweather and UI.FONTS.SpecialElite and UI.FONTS.BuilderSansBold)
		end)
	end)

	test.suite("UI plates, textures, tracking, counters, stats, bars (v2 nodes)", function()
		test.case("a plate is the identity's 9-slice art; a texture tiles; a divider is a plate", function()
			local model, issues = souls({
				type = "panel",
				name = "P",
				size = { 400, 200 },
				children = {
					{ type = "plate", name = "Frame", plate = "frame" },
					{ type = "texture", name = "Grain", strength = 0.3, color = "shadow" },
					{ type = "divider", name = "Rule" },
				},
			})
			check.equal(errorsOf(issues), 0)
			local frame = findIn(model, "Frame")
			check.equal(frame.ClassName, "ImageLabel")
			check.equal(frame.Properties.Attributes.Attributes.KitArt.String, "souls/frame")
			check.equal(frame.Properties.ScaleType, "Slice")
			check.equal(frame.Properties.SliceCenter.Rect[1][1], 64)
			local grain = findIn(model, "Grain")
			check.equal(grain.Properties.ScaleType, "Tile")
			check.equal(grain.Properties.BackgroundTransparency, 1) -- "color" tints the grain, it is not a black sheet
			check.equal(grain.Properties.ImageColor3.Color3[1], 0)
			check.equal(grain.Properties.TileSize.UDim2[1][2], 256)
			check.is_true(math.abs(grain.Properties.ImageTransparency - 0.7) < 1e-6)
			check.equal(findIn(model, "Rule").Properties.Attributes.Attributes.KitArt.String, "souls/divider")
		end)
		test.case("an unknown plate is an error that names the identity", function()
			local _, issues = souls({ type = "plate", name = "X", plate = "nope" })
			check.is_true(says(issues, 'unknown art "souls/nope"', "error"))
		end)
		test.case("tracking sets letters apart: one auto-sized label per glyph in a centred horizontal list", function()
			local model, issues = souls({
				type = "label",
				name = "Died",
				text = "YOU DIED",
				role = "death",
				tracking = 0.3,
				textOutline = "shadow",
			})
			check.equal(errorsOf(issues), 0)
			local died = findIn(model, "Died")
			check.equal(died.ClassName, "Frame")
			check.equal(died.Properties.Attributes.Attributes.Kit_Tracking.Float64, 0.3)
			check.equal(died.Properties.Attributes.Attributes.Kit_Text.String, "YOU DIED")
			local row = findIn(died, "Glyphs") -- (the glyph row is its own frame: the label's plate / stroke stay outside it)
			check.equal(row.ClassName, "Frame")
			local glyphs, spaces = 0, 0
			for _, c in row.Children do
				if c.ClassName == "TextLabel" then
					if c.Properties.AutomaticSize == "X" then
						glyphs += 1
					else
						spaces += 1
					end
				end
			end
			check.equal(glyphs, 7)
			check.equal(spaces, 1)
			check.equal(died.Properties.Attributes.Attributes.Kit_TextColor.String, "#e05a3c") -- danger, resolved
			check.equal(died.Properties.Attributes.Attributes.Kit_TextOutline.String, "#000000")
			local layout = findIn(died, "Layout")
			check.equal(layout.Properties.FillDirection, "Horizontal")
			check.equal(layout.Properties.HorizontalAlignment, "Center")
			check.equal(layout.Properties.Padding.UDim[2], 29) -- 96 * 0.3
		end)
		test.case(
			"a counter formats its number and carries it for Ui.counter; a stat row has Name + Value (+ Delta)",
			function()
				local model, issues = souls({
					type = "panel",
					name = "P",
					color = "panel",
					size = { 300, 200 },
					children = {
						{ type = "counter", name = "Souls", value = 14352 },
						{ type = "stat", name = "Vigor", label = "Vigor", value = 27, delta = "+1" },
					},
				})
				check.equal(errorsOf(issues), 0)
				local c = findIn(model, "Souls")
				check.equal(c.Properties.Text, "14,352")
				check.equal(c.Properties.Attributes.Attributes.Kit_Counter.Float64, 14352)
				check.equal(c.Properties.TextSize, 40) -- role number (the default roles)
				local v = findIn(model, "Vigor")
				check.equal(findIn(v, "Name").Properties.Text, "Vigor")
				check.equal(findIn(v, "Value").Properties.Text, "27")
				check.equal(findIn(v, "Delta").Properties.Text, "+1")
				check.equal(UI.formatNumber(999), "999")
				check.equal(UI.formatNumber(1234567), "1,234,567")
			end
		)
		test.case("a bar with a ghost trail and caps: Ghost behind Fill, CapL / CapR plates at the ends", function()
			local model, issues = souls({
				type = "bar",
				name = "Hp",
				size = { 400, 10 },
				value = 0.6,
				fill = "hp",
				ghost = true,
				caps = true,
				color = "panel",
			})
			check.equal(errorsOf(issues), 0)
			local bar = findIn(model, "Hp")
			check.equal(bar.Properties.Attributes.Attributes.Kit_Ghost.Bool, true)
			check.equal(findIn(findIn(bar, "Fill"), "Core").ClassName, "Frame") -- the lit hairline along the top
			local plain =
				souls({ type = "bar", name = "B", size = { 100, 8 }, value = 0.5, core = false, color = "panel" })
			check.equal(findIn(findIn(plain, "B"), "Core"), nil)
			local order = {}
			for _, c in bar.Children do
				table.insert(order, c.Name)
			end
			check.is_true(table.find(order, "Ghost") < table.find(order, "Fill"))
			check.equal(findIn(bar, "CapL").Properties.Attributes.Attributes.KitArt.String, "souls/cap")
			check.equal(findIn(bar, "CapR").Properties.Rotation, 180)
		end)
	end)

	test.suite("UI v3 chunky nodes (shadow, rarity, short counters, track bars)", function()
		local SIM = {
			sim = {
				name = "sim",
				tokens = {
					bg = "#0f1b36",
					panel = "#fff8ea",
					line = "#1b2a4a",
					accent = "#ffc93c",
					text = "#ffffff",
					shadow = "#0b1220",
					good = "#4cd964",
					rarity_common = "#9aa5b1",
					rarity_epic = "#b26bff",
				},
				fonts = { font = "FredokaOne", titleFont = "LuckiestGuy", monoFont = "FredokaOne" },
				radius = { s = 12, m = 18, l = 26 },
				shape = { shadow = 5 },
				motion = { enter = { type = "bounce", duration = 0.5, ease = "elastic" }, stagger = 0.05 },
			},
		}
		local SIM_ART = {
			["sim/bubble_good"] = { size = 192, slice = { 60, 60, 132, 132 } },
			["sim/card_epic"] = { size = { 192, 256 }, slice = { 40, 72, 152, 216 } },
			["sim/track_chunky"] = { size = { 192, 48 }, slice = { 40, 0, 152, 48 } },
			["sim/pill_accent"] = { size = { 192, 96 }, slice = { 60, 0, 132, 96 } },
		}
		local function sim(root: any): (any, { any })
			return UI.compile({ name = "T", identity = "sim", root = root }, {}, SIM_ART, SIM)
		end
		test.case("shadow: a dark offset copy of the plate sits under it (ZIndex 0, the identity's offset)", function()
			local model, issues = sim({
				type = "button",
				name = "Shop",
				text = "SHOP",
				textOutline = "line", -- (white on the green plate: the plate is the contrast ground)
				size = { 96, 96 },
				plate = "bubble_good",
				shadow = true,
			})
			check.equal(errorsOf(issues), 0)
			local shadow = findIn(model, "Shadow")
			check.equal(shadow.ClassName, "ImageLabel")
			check.equal(shadow.Properties.Attributes.Attributes.KitArt.String, "sim/bubble_good")
			check.equal(shadow.Properties.ZIndex, 0)
			check.equal(shadow.Properties.Position.UDim2[2][2], 5) -- shape.shadow
			check.is_true(shadow.Properties.ImageColor3.Color3[1] < 0.1) -- the shadow token, dark
			check.is_true(math.abs(shadow.Properties.ImageTransparency - 0.5) < 1e-6)
			check.equal(findIn(model, "Plate").ClassName, "ImageLabel")
			local _, bad = sim({ type = "button", name = "B", text = "x", size = { 96, 96 }, shadow = true })
			check.is_true(says(bad, "give the node a plate first", "error"))
			local _, far =
				sim({ type = "button", name = "B", text = "x", size = { 96, 96 }, plate = "bubble_good", shadow = 99 })
			check.is_true(says(far, "shadow: true", "error"))
		end)
		test.case("rarity: the card_<tier> plate and a Kit_Rarity attribute; an unknown tier is an error", function()
			local model, issues = sim({ type = "panel", name = "Card", size = { 160, 212 }, rarity = "epic" })
			check.equal(errorsOf(issues), 0)
			check.equal(findIn(model, "Plate").Properties.Attributes.Attributes.KitArt.String, "sim/card_epic")
			check.equal(findIn(model, "Card").Properties.Attributes.Attributes.Kit_Rarity.String, "epic")
			local _, bad = sim({ type = "panel", name = "Card", size = { 160, 212 }, rarity = "divine" })
			check.is_true(says(bad, 'no token "rarity_divine"', "error"))
			-- a plate node too: { type: "plate", rarity: "epic" } is the card_epic piece
			local pm, pi = sim({ type = "plate", name = "Card", size = { 160, 212 }, rarity = "epic" })
			check.equal(errorsOf(pi), 0)
			check.equal(findIn(pm, "Card").Properties.Attributes.Attributes.KitArt.String, "sim/card_epic")
			check.equal(findIn(pm, "Card").Properties.Attributes.Attributes.Kit_Rarity.String, "epic")
			-- a panel with a plate and a shadow: Shadow then Plate, then the panel's own children
			local cm, ci = sim({
				type = "panel",
				name = "Bubble",
				size = { 96, 96 },
				plate = "bubble_good",
				shadow = 4,
				children = { { type = "label", name = "Txt", text = "SHOP", textColor = "line" } },
			})
			check.equal(errorsOf(ci), 0)
			local kids = findIn(cm, "Bubble").Children
			check.equal(kids[1].Name, "Shadow")
			check.equal(kids[1].Properties.Position.UDim2[2][2], 4)
			check.equal(kids[2].Name, "Plate")
			check.equal(findIn(cm, "Txt").ClassName, "TextLabel")
		end)
		test.case(
			"counter format short: 1.2K / 3.4M, carried for the runtime; an unknown format is an error",
			function()
				check.equal(UI.formatNumber(999, nil, true), "999")
				check.equal(UI.formatNumber(1234, nil, true), "1.2K")
				check.equal(UI.formatNumber(3400000, nil, true), "3.4M")
				check.equal(UI.formatNumber(120000, nil, true), "120K")
				check.equal(UI.formatNumber(1000, nil, true), "1K")
				check.equal(UI.formatNumber(-2500, nil, true), "-2.5K")
				check.equal(UI.formatNumber(7e9, nil, true), "7B")
				local model, issues =
					sim({ type = "counter", name = "Coins", value = 1234567, format = "short", size = { 200, 40 } })
				check.equal(errorsOf(issues), 0)
				local c = findIn(model, "Coins")
				check.equal(c.Properties.Text, "1.2M")
				check.equal(c.Properties.Attributes.Attributes.Kit_CounterFormat.String, "short")
				local _, bad =
					sim({ type = "counter", name = "Coins", value = 1, format = "roman", size = { 200, 40 } })
				check.is_true(says(bad, "counter format", "error"))
			end
		)
		test.case(
			"a bar with track + fillGloss: the Track plate is the ground (bar transparent), Gloss in the Fill",
			function()
				local model, issues = sim({
					type = "bar",
					name = "Xp",
					size = { 300, 28 },
					value = 0.4,
					fill = "good",
					track = true,
					fillGloss = true,
					radius = 14,
				})
				check.equal(errorsOf(issues), 0)
				local bar = findIn(model, "Xp")
				check.equal(bar.Properties.BackgroundTransparency, 1)
				local track = findIn(model, "Track")
				check.equal(track.Properties.Attributes.Attributes.KitArt.String, "sim/track_chunky")
				check.equal(track.Properties.ZIndex, 0)
				local gloss = findIn(findIn(model, "Fill"), "Gloss")
				check.is_true(gloss ~= nil)
				check.is_true(math.abs(gloss.Properties.Size.UDim2[2][1] - 0.42) < 1e-6)
			end
		)
		test.case(
			"identity minimums: text, buttons and icons under the measured floors are warnings that name the floor",
			function()
				local FLOORS = table.clone(SIM)
				FLOORS.sim = table.clone(SIM.sim)
				FLOORS.sim.minimums = { text = 16, button = 56, icon = 40 }
				local _, issues = UI.compile({
					name = "T",
					identity = "sim",
					root = {
						type = "imagebutton",
						name = "Shop",
						size = { 48, 48 },
						plate = "bubble_good",
						children = {
							{
								type = "image",
								name = "Icon",
								image = "art:sim/icon_cart",
								fit = "fit",
								size = { 30, 30 },
							},
							{
								type = "label",
								name = "Txt",
								text = "SHOP",
								textSize = 14,
								textColor = "line",
								size = { "100%", 20 },
							},
							{ type = "button", name = "B", text = "ok", textColor = "line", size = { 100, 50 } },
						},
					},
				}, {}, {
					["sim/bubble_good"] = { size = 192, slice = { 60, 60, 132, 132 } },
					["sim/icon_cart"] = { size = 256 },
				}, FLOORS)
				check.equal(errorsOf(issues), 0)
				check.is_true(says(issues, "under the identity's floor of 16", "warn"))
				check.is_true(says(issues, "icon is 30px — the identity's floor is 40px", "warn"))
				check.is_true(says(issues, "button is 48px tall — the identity's floor is 56px", "warn"))
				check.is_true(says(issues, "button is 50px tall — the identity's floor is 56px", "warn"))
				-- no floors declared: no such warnings
				local _, plain = UI.compile({
					name = "T",
					identity = "sim",
					root = {
						type = "label",
						name = "Txt",
						text = "x",
						textSize = 14,
						textColor = "line",
						size = { 100, 20 },
					},
				}, {}, {}, SIM)
				check.is_true(not says(plain, "identity's floor", "warn"))
				local badId = table.clone(SIM.sim)
				badId.minimums = { text = "big" }
				local _, bad = UI.compile(
					{ name = "T", identity = "sim", root = { type = "panel", name = "P" } },
					{},
					{},
					{ sim = badId }
				)
				check.is_true(says(bad, "minimums: { text = px, button = px, icon = px }", "error"))
			end
		)
		test.case(
			"focus: the node the eye lands on must be the biggest text; a hero screen without one is warned",
			function()
				-- (a PROP screen: on a hero screen a typed focus is an error of its own — the hero_typed_glyph case)
				local function focusScreen(focus: any, big: number, quality: string?)
					return UI.compile({
						name = "T",
						identity = "sim",
						quality = quality or "prop",
						focus = focus,
						root = {
							type = "panel",
							name = "Root",
							size = { 400, 200 },
							color = "panel",
							children = {
								{
									type = "label",
									name = "Coins",
									text = "12.4K",
									textSize = 40,
									textColor = "line",
									size = { 200, 50 },
								},
								{
									type = "label",
									name = "Hint",
									text = "tap",
									textSize = big,
									textColor = "line",
									size = { 200, 50 },
								},
								{
									type = "label",
									name = "Title",
									text = "SHOP",
									tracking = 0.2,
									textSize = 30,
									textColor = "line",
									size = { 200, 50 },
								},
							},
						},
					}, {}, {}, SIM)
				end
				local model, ok = focusScreen("Root.Coins", 20)
				check.equal(errorsOf(ok), 0)
				check.is_true(not says(ok, "the eye lands on", "warn"))
				check.equal(model.Properties.Attributes.Attributes.Kit_Focus.String, "Root.Coins")
				local _, loud = focusScreen("Root.Coins", 48)
				check.is_true(
					says(loud, "the eye lands on T.Root.Hint (48px), not on the focus Root.Coins (40px)", "warn")
				)
				local _, tracked = focusScreen("Root.Title", 20) -- a tracked label counts as one text at its size
				check.is_true(
					says(tracked, "the eye lands on T.Root.Coins (40px), not on the focus Root.Title (30px)", "warn")
				)
				local _, missing = focusScreen("Root.Nope", 20)
				check.is_true(says(missing, 'focus "Root.Nope" is not a text or image node', "error"))
				local _, none = focusScreen(nil, 20, "hero")
				check.is_true(says(none, "a hero screen names what the eye lands on first", "warn"))
			end
		)
		test.case(
			"hero_typed_glyph: a hero screen's hero piece as a typed font glyph is an error; lettered, a digit set, or the identity's evidence is not",
			function()
				local function heroScreen(node: any, ident: any?)
					return UI.compile(
						{
							name = "T",
							identity = "sim",
							quality = "hero",
							focus = "Root.Title",
							root = {
								type = "panel",
								name = "Root",
								size = { 400, 200 },
								color = "panel",
								children = { node },
							},
						},
						{},
						{ ["sim/w_shop"] = { size = { 200, 60 } }, ["sim/dg_0"] = { size = { 60, 80 } } },
						ident or SIM
					)
				end
				local typed = {
					type = "label",
					name = "Title",
					text = "SHOP",
					textSize = 40,
					textColor = "line",
					size = { 200, 50 },
				}
				local _, bad = heroScreen(typed)
				check.is_true(says(bad, "the hero piece Root.Title is a typed font glyph", "error"))
				local lettered = { type = "label", name = "Title", text = "SHOP", lettering = true, size = { 200, 60 } }
				local _, good = heroScreen(lettered)
				check.is_true(not says(good, "is a typed font glyph"))
				local number =
					{ type = "number", name = "Title", digits = "sim/dg", aspect = 0.75, text = "0", size = { 60, 80 } }
				local _, digits = heroScreen(number)
				check.is_true(not says(digits, "is a typed font glyph"))
				-- the one exception names one of the identity's own listed references (a realistic HUD's typed readout)
				local proven = table.clone(SIM)
				proven.sim = table.clone(SIM.sim)
				proven.sim.references = { { image = "assets/ui/refs/sim/still.jpg" } }
				proven.sim.typed_hero_evidence = "assets/ui/refs/sim/still.jpg: the real HUD sets it in plain type"
				local _, waived = heroScreen(typed, proven)
				check.is_true(not says(waived, "is a typed font glyph"))
				proven.sim.typed_hero_evidence = "assets/ui/refs/other.jpg: not one of its references"
				local _, unproven = heroScreen(typed, proven)
				check.is_true(says(unproven, "is a typed font glyph", "error"))
				-- (review 2026-10-16) an empty reference image waives nothing
				proven.sim.references = { { image = "" } }
				local _, empty = heroScreen(typed, proven)
				check.is_true(says(empty, "is a typed font glyph", "error"))
				-- a lettered BUTTON as the hero is art (its word is a child picture), not a typed glyph
				local button = { type = "button", name = "Title", text = "SHOP", lettering = true, size = { 200, 60 } }
				local _, btn = heroScreen(button)
				check.is_true(not says(btn, "is a typed font glyph"))
				-- the EXACT node: an image elsewhere named Title does not excuse the typed Root.Title
				local _, suffix = UI.compile({
					name = "T",
					identity = "sim",
					quality = "aaa",
					focus = "Root.Title",
					root = {
						type = "panel",
						name = "Root",
						size = { 400, 200 },
						color = "panel",
						children = {
							typed,
							{
								type = "panel",
								name = "Box",
								size = { 100, 100 },
								children = {
									{ type = "image", name = "Title", image = "art:sim/w_shop", size = { 50, 50 } },
								},
							},
						},
					},
				}, {}, { ["sim/w_shop"] = { size = { 200, 60 } } }, SIM)
				check.is_true(says(suffix, "the hero piece Root.Title is a typed font glyph", "error"))
			end
		)
		test.case(
			"bounce enters and float / wobble loops are motion kinds; the identity's bounce is the default",
			function()
				local model, issues = sim({
					type = "panel",
					name = "P",
					size = { 100, 100 },
					color = "panel",
					motion = { enter = { type = "bounce" }, loop = { type = "float", speed = 1.5 } },
					children = {
						{
							type = "label",
							name = "L",
							text = "x",
							textColor = "line",
							motion = { loop = { type = "wobble" } },
						},
					},
				})
				check.equal(errorsOf(issues), 0)
				local a = findIn(model, "P").Properties.Attributes.Attributes
				check.equal(a.Motion_enter.String, "bounce")
				check.equal(a.Motion_loop.String, "float")
				check.equal(findIn(model, "L").Properties.Attributes.Attributes.Motion_loop.String, "wobble")
			end
		)
	end)

	test.suite("UI motion v2 (choreography attributes) and the AI-tell gates", function()
		test.case(
			"an enter word takes the identity's timing; a choreography overrides it; a stagger marks the container",
			function()
				local model, issues = souls({
					type = "panel",
					name = "Menu",
					color = "panel",
					size = { 300, 300 },
					motion = { stagger = 0.06 },
					children = {
						{ type = "label", name = "A", text = "a", motion = { enter = "fade" } },
						{
							type = "label",
							name = "B",
							text = "b",
							motion = {
								enter = { type = "slam", delay = 0.4, duration = 0.5, ease = "back" },
								loop = { type = "glint", speed = 2 },
							},
						},
					},
				})
				check.equal(errorsOf(issues), 0)
				local a = findIn(model, "A").Properties.Attributes.Attributes
				check.equal(a.Motion_enter.String, "fade")
				check.equal(a.Motion_enter_duration.Float64, 0.9)
				check.equal(a.Motion_enter_ease.String, "sine")
				local b = findIn(model, "B").Properties.Attributes.Attributes
				check.equal(b.Motion_enter.String, "slam")
				check.equal(b.Motion_enter_delay.Float64, 0.4)
				check.equal(b.Motion_enter_ease.String, "back")
				check.equal(b.Motion_loop.String, "glint")
				check.equal(b.Motion_loop_speed.Float64, 2)
				check.equal(findIn(model, "Menu").Properties.Attributes.Attributes.Motion_stagger.Float64, 0.06)
			end
		)
		test.case("unknown enters, eases and motion keys are errors", function()
			local _, issues = souls({
				type = "label",
				name = "L",
				text = "x",
				color = "panel",
				motion = { enter = "teleport", wiggle = true },
			})
			check.is_true(says(issues, "enter: fade | rise", "error"))
			check.is_true(says(issues, "motion keys", "error"))
			local _, e = souls({
				type = "label",
				name = "L",
				text = "x",
				color = "panel",
				motion = { enter = { type = "fade", ease = "bouncy" } },
			})
			check.is_true(says(e, "ease:", "error"))
		end)
		test.case("the AI tells: indigo accent, one radius everywhere, a menu entering all at once", function()
			local _, indigo = UI.compile({
				name = "I",
				theme = { accent = "#6c5ce7", bg = "#ffffff", text = "#111111", panel = "#eeeeee" },
				root = { type = "panel", name = "P", color = "panel", size = { 100, 100 } },
			})
			check.is_true(says(indigo, "indigo", "warn"))
			local _, radii = UI.compile({
				name = "R",
				skin = "clean",
				root = {
					type = "panel",
					name = "P",
					color = "panel",
					size = { 400, 400 },
					children = {
						{ type = "panel", name = "A", color = "panel2", size = { 100, 40 }, radius = 12 },
						{ type = "panel", name = "B", color = "panel2", size = { 100, 40 }, radius = 12 },
						{ type = "panel", name = "C", color = "panel2", size = { 100, 40 }, radius = 12 },
						{ type = "panel", name = "D", color = "panel2", size = { 100, 40 }, radius = 12 },
					},
				},
			})
			check.is_true(says(radii, "one radius on everything", "warn"))
			local _, allAtOnce = souls({
				type = "panel",
				name = "P",
				color = "panel",
				size = { 400, 400 },
				children = {
					{ type = "label", name = "A", text = "a", motion = { enter = "fade" } },
					{ type = "label", name = "B", text = "b", motion = { enter = "fade" } },
					{ type = "label", name = "C", text = "c", motion = { enter = "fade" } },
				},
			})
			check.is_true(says(allAtOnce, "same instant", "warn"))
			local _, staggered = souls({
				type = "panel",
				name = "P",
				color = "panel",
				size = { 400, 400 },
				motion = { stagger = 0.08 },
				children = {
					{ type = "label", name = "A", text = "a", motion = { enter = "fade" } },
					{ type = "label", name = "B", text = "b", motion = { enter = "fade" } },
					{ type = "label", name = "C", text = "c", motion = { enter = "fade" } },
				},
			})
			check.is_true(not says(staggered, "same instant"))
		end)
		test.case("an identity's uploaded art keeps its folder in ids.ui (art:souls/frame)", function()
			local AssetIds = require("../../lib/assetids")
			local kind, logical = AssetIds.classify("build/ui/art/souls/frame.png")
			check.equal(kind, "ui")
			check.equal(logical, "souls/frame")
			local k2, l2 = AssetIds.classify("build/ui/art/ring.png")
			check.equal(k2, "ui")
			check.equal(l2, "ring")
			local model = UI.compile(
				{ name = "T", identity = "souls", root = { type = "plate", name = "F", plate = "frame" } },
				{ ui = { ["souls/frame"] = "rbxassetid://77" } },
				ART,
				IDENTITY
			)
			check.equal(findIn(model, "F").Properties.Image, "rbxassetid://77")
		end)
		test.case("a tracked button stays a button; left-aligned tracking justifies the run to the start", function()
			local model, issues = souls({
				type = "panel",
				name = "P",
				color = "panel",
				size = { 400, 200 },
				children = {
					{
						type = "button",
						name = "Start",
						text = "START",
						tracking = 0.2,
						textSize = 20,
						motion = { hover = "glow" },
					},
					{ type = "label", name = "L", text = "LEFT", tracking = 0.2, textSize = 20, align = "left" },
					{ type = "label", name = "R", text = "RIGHT", tracking = 0.2, textSize = 20, align = "right" },
				},
			})
			check.equal(errorsOf(issues), 0)
			local start = findIn(model, "Start")
			check.equal(start.ClassName, "TextButton")
			check.equal(start.Properties.Text, "")
			check.equal(start.Properties.Attributes.Attributes.Motion_hover.String, "glow")
			check.equal(findIn(findIn(model, "L"), "Layout").Properties.HorizontalAlignment, "Left")
			check.equal(findIn(findIn(model, "R"), "Layout").Properties.HorizontalAlignment, "Right")
		end)
		test.case("a tracked button with a plate and a style keeps them outside the glyph row", function()
			local model, issues = souls({
				type = "button",
				name = "Go",
				text = "GO",
				tracking = 0.2,
				textSize = 20,
				plate = "frame", -- (the test art table knows souls/frame)
				stroke = "line",
				size = { 200, 48 },
			})
			check.equal(errorsOf(issues), 0)
			local go = findIn(model, "Go")
			check.equal(go.ClassName, "TextButton")
			local names = {}
			for _, c in go.Children do
				names[c.Name] = c.ClassName
			end
			check.equal(names.Plate, "ImageLabel")
			check.equal(names.Label, "TextLabel")
			check.equal(names.Stroke, "UIStroke")
			check.equal(names.Glyphs, "Frame")
			check.equal(names.Layout, nil) -- the list lives in Glyphs, so Plate / Label are not swept into it
			check.equal(findIn(findIn(go, "Glyphs"), "Layout").ClassName, "UIListLayout")
		end)
		test.case(
			"a plate under an identity falls back to the kit's own piece; a real stagger disarms the gate",
			function()
				local model, issues = souls({ type = "plate", name = "R", plate = "ring", size = { 64, 64 } })
				check.equal(errorsOf(issues), 0)
				check.equal(findIn(model, "R").Properties.Attributes.Attributes.KitArt.String, "ring")
				local _, staggered = souls({
					type = "panel",
					name = "P",
					color = "panel",
					size = { 400, 400 },
					motion = { stagger = 0.08 },
					children = {
						{ type = "label", name = "A", text = "a", motion = { enter = "fade" } },
						{ type = "label", name = "B", text = "b", motion = { enter = "fade" } },
						{ type = "label", name = "C", text = "c", motion = { enter = "fade" } },
					},
				})
				check.is_true(not says(staggered, "same instant"))
				local _, unrelated = souls({
					type = "panel",
					name = "P",
					color = "panel",
					size = { 400, 400 },
					children = {
						{ type = "panel", name = "Elsewhere", size = { 10, 10 }, motion = { stagger = 0.08 } },
						{ type = "label", name = "A", text = "a", motion = { enter = "fade" } },
						{ type = "label", name = "B", text = "b", motion = { enter = "fade" } },
						{ type = "label", name = "C", text = "c", motion = { enter = "fade" } },
					},
				})
				check.is_true(says(unrelated, "same instant", "warn")) -- a stagger elsewhere does not excuse these
				local _, fromKey = souls({
					type = "label",
					name = "L",
					text = "x",
					color = "panel",
					motion = { enter = { type = "rise", from = "left" } },
				})
				check.is_true(says(fromKey, "enter keys", "error"))
			end
		)
		test.case("viewport, autosize, justify and the per-viewport scale compile to what the runtime reads", function()
			local model, issues = souls({
				type = "panel",
				name = "P",
				color = "panel",
				size = { 400, 300 },
				layout = { dir = "vertical", gap = 4, align = "center", justify = "end" },
				children = {
					{ type = "viewport", name = "Gun", model = "glock17", spin = 0.4, size = { 200, 200 } },
					{ type = "label", name = "Auto", text = "fits", autosize = "xy", size = { 0, 0 } },
				},
			}, { scale = { phone = 0.7, tablet = 0.9 } })
			check.equal(errorsOf(issues), 0)
			local vp = findIn(model, "Gun")
			check.equal(vp.ClassName, "ViewportFrame")
			check.equal(vp.Properties.Attributes.Attributes.Kit_Model.String, "glock17")
			check.equal(vp.Properties.Attributes.Attributes.Kit_ModelSpin.Float64, 0.4)
			check.equal(findIn(model, "Auto").Properties.AutomaticSize, "XY")
			check.equal(findIn(findIn(model, "P"), "Layout").Properties.VerticalAlignment, "Bottom")
			local attrs = model.Properties.Attributes.Attributes
			check.equal(attrs.Kit_Scale_phone.Float64, 0.7)
			check.equal(attrs.Kit_Scale_tablet.Float64, 0.9)
			local _, bad = souls({ type = "panel", name = "P" }, { scale = { tv = 2 } })
			check.is_true(says(bad, "scale keys", "error"))
		end)
		test.case(
			"a stagger of zero does not disarm the all-at-once gate; a style's radius is not the spec's",
			function()
				local _, zero = souls({
					type = "panel",
					name = "P",
					color = "panel",
					size = { 400, 400 },
					motion = { stagger = 0 },
					children = {
						{ type = "label", name = "A", text = "a", motion = { enter = "fade" } },
						{ type = "label", name = "B", text = "b", motion = { enter = "fade" } },
						{ type = "label", name = "C", text = "c", motion = { enter = "fade" } },
					},
				})
				check.is_true(says(zero, "same instant", "warn"))
				local _, styled = UI.compile({
					name = "R",
					skin = "clean",
					root = {
						type = "panel",
						name = "P",
						color = "panel",
						size = { 400, 400 },
						children = {
							{ type = "panel", name = "A", style = "card", size = { 100, 40 } },
							{ type = "panel", name = "B", style = "card", size = { 100, 40 } },
							{ type = "button", name = "C", style = "primary", text = "c", size = { 100, 44 } },
							{ type = "button", name = "D", style = "secondary", text = "d", size = { 100, 44 } },
						},
					},
				})
				check.is_true(not says(styled, "one radius on everything"))
			end
		)
		test.case("at: a phone override compiles to the attribute the runtime and the preview apply", function()
			local model, issues = souls({
				type = "panel",
				name = "P",
				color = "panel",
				size = { 400, 300 },
				children = {
					{
						type = "label",
						name = "L",
						text = "x",
						textSize = 24,
						size = { 200, 40 },
						at = {
							phone = {
								size = { "100%", 32 },
								pos = { 0, "100%-32" },
								textSize = 18,
								visible = true,
								anchor = "bottomleft",
							},
							tablet = { visible = false },
						},
					},
				},
			})
			check.equal(errorsOf(issues), 0)
			local a = findIn(model, "L").Properties.Attributes.Attributes
			check.equal(a.Kit_At_phone.String, "Anchor=0,1|Position=0,0,1,-32|Size=1,0,0,32|TextSize=18|Visible=true")
			check.equal(a.Kit_At_tablet.String, "Visible=false")
			local _, bad = souls({
				type = "label",
				name = "L",
				text = "x",
				color = "panel",
				at = { tv = { size = { 1, 1 } }, phone = { radius = 4 } },
			})
			check.is_true(says(bad, "at keys", "error"))
			check.is_true(says(bad, "at overrides", "error"))
		end)
		test.case("insets choose the ScreenGui's safe area; bad values error", function()
			local model = souls({ type = "panel", name = "P" }, { insets = "core" })
			check.equal(model.Properties.ScreenInsets, "CoreUISafeInsets")
			check.equal(model.Properties.IgnoreGuiInset, nil) -- (the legacy alias is not written: it would race)
			local _, issues = souls({ type = "panel", name = "P" }, { insets = "everywhere" })
			check.is_true(says(issues, "insets must be", "error"))
		end)
	end)

	test.suite("v7 layout + access gates (LIMITATIONS_FIXES_V4 UI-X)", function()
		local function compiled(spec: any): (any, string, string)
			local model, issues = UI.compile(spec)
			local errors, warns = {}, {}
			for _, issue in issues do
				table.insert(if issue.severity == "error" then errors else warns, issue.path .. ": " .. issue.message)
			end
			return model, table.concat(errors, " | "), table.concat(warns, " | ")
		end
		local function find(inst: any, class: string): any
			if type(inst) ~= "table" then
				return nil
			end
			if inst.ClassName == class then
				return inst
			end
			for _, c in inst.Children or {} do
				local f = find(c, class)
				if f then
					return f
				end
			end
			return nil
		end
		local function row(children: { any }, layout: any?): any
			return screen({
				{
					type = "panel",
					name = "Row",
					size = { 600, 60 },
					layout = layout or { dir = "horizontal", flex = "between", lineAlign = "center", wrap = true },
					children = children,
				},
			})
		end
		test.case("a list's flex and line alignment compile onto its UIListLayout", function()
			local model, errors = compiled(row({ { type = "panel", name = "A", size = { 80, 40 } } }))
			check.equal(errors, "")
			local l = find(model, "UIListLayout")
			check.equal(l and l.Properties.HorizontalFlex, "SpaceBetween")
			check.equal(l and l.Properties.ItemLineAlignment, "Center")
			check.equal(l and l.Properties.Wraps, true)
			local v = find(compiled(row({}, { dir = "vertical", flex = "fill" })), "UIListLayout")
			check.equal(v and v.Properties.VerticalFlex, "Fill")
		end)
		test.case("a flex item in a list becomes a UIFlexItem", function()
			local model, errors = compiled(row({
				{ type = "panel", name = "A", size = { 80, 40 }, flex = "grow" },
				{ type = "panel", name = "B", size = { 80, 40 }, flex = { grow = 2, shrink = 1, align = "stretch" } },
			}))
			check.equal(errors, "")
			local a = find(model, "UIFlexItem")
			check.equal(a and a.Properties.FlexMode, "Grow")
			local rowNode = find(model, "UIListLayout") and model.Children[1].Children[1]
			local b = nil
			for _, c in rowNode.Children do
				if c.Name == "B" then
					b = find(c, "UIFlexItem")
				end
			end
			check.equal(b and b.Properties.FlexMode, "Custom")
			check.equal(b and b.Properties.GrowRatio, 2)
			check.equal(b and b.Properties.ItemLineAlignment, "Stretch")
		end)
		test.case("flex where the engine ignores it is an error", function()
			local _, noList = compiled(screen({ { type = "panel", name = "A", size = { 80, 40 }, flex = "grow" } }))
			check.is_true(string.find(noList, "a flex item needs a parent with a list", 1, true) ~= nil)
			local _, inGrid =
				compiled(row({ { type = "panel", name = "A", flex = "fill" } }, { grid = { 40, 40 }, flex = "fill" }))
			check.is_true(string.find(inGrid, "flex / lineAlign are a LIST's", 1, true) ~= nil)
			check.is_true(string.find(inGrid, "a flex item needs a parent with a list", 1, true) ~= nil)
			local _, bad = compiled(
				row({ { type = "panel", name = "A", flex = { grow = -1 } } }, { dir = "horizontal", flex = "wobbly" })
			)
			check.is_true(string.find(bad, "flex grow / shrink are numbers", 1, true) ~= nil)
			check.is_true(string.find(bad, "flex: fill | between", 1, true) ~= nil)
		end)
		local function named(inst: any, name: string): any
			if type(inst) ~= "table" then
				return nil
			end
			if inst.Name == name then
				return inst
			end
			for _, c in inst.Children or {} do
				local f = named(c, name)
				if f then
					return f
				end
			end
			return nil
		end
		test.case("focus: a frame's cursor group and its edges compile onto it (gamepad / keyboard)", function()
			local model, errors = compiled(screen({
				{
					type = "panel",
					name = "Menu",
					size = { 300, 200 },
					focus = { group = true, edge = { up = "stop", left = "stop", right = "stop", down = "escape" } },
				},
			}))
			check.equal(errors, "")
			local menu = named(model, "Menu")
			check.equal(menu.Properties.SelectionGroup, true)
			check.equal(menu.Properties.SelectionBehaviorUp, "Stop")
			check.equal(menu.Properties.SelectionBehaviorLeft, "Stop")
			check.equal(menu.Properties.SelectionBehaviorRight, "Stop")
			check.equal(menu.Properties.SelectionBehaviorDown, "Escape")
			local all = compiled(screen({ { type = "panel", name = "M", focus = { edge = "stop" } } }))
			check.equal(named(all, "M").Properties.SelectionBehaviorDown, "Stop")
			check.equal(named(all, "M").Properties.SelectionGroup, nil)
			local _, bad = compiled(
				screen({ { type = "panel", name = "M", focus = { group = "yes", edge = { up = "wander" } } } })
			)
			check.is_true(string.find(bad, "focus.group is true or false", 1, true) ~= nil)
			check.is_true(string.find(bad, 'focus edge up: "stop" | "escape"', 1, true) ~= nil)
			local _, notTable = compiled(screen({ { type = "panel", name = "M", focus = "group" } }))
			check.is_true(string.find(notTable, "focus: {", 1, true) ~= nil)
		end)
		test.case("localize: false keeps a name or a number from machine translation (AutoLocalize)", function()
			local model, errors = compiled(screen({
				{ type = "label", name = "Coins", text = "1250", size = { 120, 40 }, localize = false },
				{ type = "label", name = "Title", text = "Shop", size = { 120, 40 } },
			}))
			check.equal(errors, "")
			check.equal(named(model, "Coins").Properties.AutoLocalize, false)
			check.equal(named(model, "Title").Properties.AutoLocalize, nil) -- (the engine's default: translated)
			local _, bad = compiled(screen({ { type = "label", name = "L", text = "x", localize = "no" } }))
			check.is_true(string.find(bad, "localize is true or false", 1, true) ~= nil)
		end)
		test.case("preferredText: the text follows the player's size and must fit its box at Largest", function()
			local fits = screen({
				{ type = "label", name = "L", text = "HP", textSize = 20, size = { 200, 40 }, preferredText = true },
			})
			local model, errors = compiled(fits)
			check.equal(errors, "")
			local label = find(model, "TextLabel")
			check.equal(label and label.Properties.Attributes.Attributes.Kit_PreferredText.Bool, true)
			local _, clips = compiled(screen({
				{ type = "label", name = "L", text = "HP", textSize = 20, size = { 200, 24 }, preferredText = true },
			}))
			check.is_true(
				string.find(clips, "needs 36px at the player's Largest text size but its box is 24px", 1, true) ~= nil
			)
			local spec = screen({ { type = "label", name = "L", text = "HP", textSize = 20, size = { 200, 24 } } })
			spec.preferredText = true -- (the whole screen opts in)
			local _, whole = compiled(spec)
			check.is_true(string.find(whole, "would clip", 1, true) ~= nil)
			local _, grows = compiled(screen({
				{
					type = "label",
					name = "L",
					text = "HP",
					textSize = 20,
					size = { 200, 24 },
					autosize = "y",
					preferredText = true,
				},
			}))
			check.equal(grows, "")
			local _, off =
				compiled(screen({ { type = "label", name = "L", text = "HP", textSize = 20, size = { 200, 24 } } }))
			check.equal(off, "") -- (not opted in: not judged)
		end)
		test.case("WCAG 1.4.11: a bar's fill against its track under 3:1 is named (a warning)", function()
			local function bar(fill: string, track: string): any
				return screen({
					{ type = "bar", name = "Hp", size = { 300, 12 }, color = track, fill = fill, value = 0.5 },
				})
			end
			local _, errors, warns = compiled(bar("dim", "bg"))
			check.is_true(string.find(warns, "WCAG 1.4.11", 1, true) ~= nil)
			check.is_true(string.find(errors, "1.4.11", 1, true) == nil)
			local _, _, okWarns = compiled(bar("text", "bg"))
			check.is_true(string.find(okWarns, "1.4.11", 1, true) == nil)
			local grad = screen({
				{
					type = "bar",
					name = "Hp",
					size = { 300, 12 },
					color = "bg",
					fill = "text",
					fillGradient = { "text", "dim" },
				},
			})
			local _, _, gradWarns = compiled(grad)
			check.is_true(string.find(gradWarns, "1.4.11", 1, true) ~= nil) -- (the dark end is the fill's leading edge)
		end)
	end)

	test.suite("Combat Feedback Kit components (LIMITATIONS_FIXES_V4 UI-X 13.6)", function()
		local function combatErrors(children: { any }): string
			local _, issues = UI.compile(screen(children))
			local out = {}
			for _, issue in issues do
				if issue.severity == "error" then
					table.insert(out, issue.path .. ": " .. issue.message)
				end
			end
			return table.concat(out, " | ")
		end
		local function byName(inst: any, name: string): any
			if type(inst) ~= "table" then
				return nil
			end
			if inst.Name == name then
				return inst
			end
			for _, c in inst.Children or {} do
				local f = byName(c, name)
				if f then
					return f
				end
			end
			return nil
		end
		local function attrs(inst: any): { [string]: any }
			local out = {}
			for k, v in ((inst.Properties.Attributes or {}).Attributes or {}) do
				local _, val = next(v)
				out[k] = val
			end
			return out
		end
		test.case("a streak ladder compiles to a hidden banner template + its rules as attributes", function()
			local model, issues = UI.compile(screen({
				{
					type = "ladder",
					name = "Streak",
					rungs = { "Double", "Triple" },
					killWindow = 4,
					max = 2,
					hitStep = 5,
				},
			}))
			for _, issue in issues do
				check.is_true(issue.severity ~= "error")
			end
			local streak = byName(model, "Streak")
			check.not_nil(streak)
			local a = attrs(streak)
			check.equal(a.Kit_Ladder, 2)
			check.equal(a.Kit_LadderRungs, "Double|Triple")
			check.equal(a.Kit_LadderKillWindow, 4)
			check.equal(a.Kit_LadderHitStep, 5)
			local banner = byName(streak, "Banner")
			check.not_nil(banner)
			check.equal(banner.Properties.Visible, false)
			check.not_nil(byName(banner, "Label"))
			check.not_nil(byName(banner, "Count"))
		end)
		test.case("a ladder the runtime cannot honour is an error (an empty rung, a 0 s window, 9 banners)", function()
			local e =
				combatErrors({ { type = "ladder", name = "S", rungs = { "Double", "" }, killWindow = 0, max = 9 } })
			check.is_true(string.find(e, "Root.S.rungs", 1, true) ~= nil)
			check.is_true(string.find(e, "Root.S.killWindow", 1, true) ~= nil)
			check.is_true(string.find(e, "Root.S.max", 1, true) ~= nil)
			check.equal(combatErrors({ { type = "ladder", name = "S" } }), "") -- (the defaults work)
			check.is_true(
				string.find(combatErrors({ { type = "ladder", name = "S", hitStep = 1 } }), "hitStep", 1, true) ~= nil
			)
		end)
		test.case("a pinned marker that would hang off the edge, or have no room on a phone, is an error", function()
			check.is_true(
				string.find(
					combatErrors({ { type = "marker", name = "M", size = 44, margin = 12 } }),
					"hangs off",
					1,
					true
				) ~= nil
			)
			check.is_true(
				string.find(
					combatErrors({ { type = "marker", name = "M", margin = 200 } }),
					"nowhere to travel",
					1,
					true
				) ~= nil
			)
			check.equal(combatErrors({ { type = "marker", name = "M", size = 44, margin = 56 } }), "")
			check.equal(combatErrors({ { type = "marker", name = "M" } }), "")
		end)
		test.case("a compare tooltip can be dragged (Kit_TooltipDrag); drag must be a boolean", function()
			local model = UI.compile(screen({ { type = "tooltip", name = "Tip", drag = true } }))
			check.equal(attrs(byName(model, "Tip")).Kit_TooltipDrag, true)
			local plain = UI.compile(screen({ { type = "tooltip", name = "Tip" } }))
			check.equal(attrs(byName(plain, "Tip")).Kit_TooltipDrag, nil)
			check.is_true(
				string.find(combatErrors({ { type = "tooltip", name = "Tip", drag = "yes" } }), "drag", 1, true) ~= nil
			)
		end)
	end)

	-- LIMITATIONS_FIXES_V4 UI-X 6.4 / 13.6: the VRAM guard (no CanvasGroup inside another, none left allocated while
	-- hidden) and WCAG 2.3.1 at compile time (no fx / loop that can flash more than 3 times in one second)
	test.suite("VRAM guard + photosensitivity (LIMITATIONS_FIXES_V4 UI-X 6.4)", function()
		local function has(text: string, needle: string): boolean
			return string.find(text, needle, 1, true) ~= nil
		end
		local function byName(inst: any, name: string): any
			if type(inst) ~= "table" then
				return nil
			end
			if inst.Name == name then
				return inst
			end
			for _, c in inst.Children or {} do
				local f = byName(c, name)
				if f then
					return f
				end
			end
			return nil
		end
		test.case(
			"a CanvasGroup inside a CanvasGroup is an error, a hit marker in one too; side by side is fine",
			function()
				local errs = messages(screen({
					{
						type = "canvas",
						name = "Card",
						size = { 300, 200 },
						children = { { type = "canvas", name = "Inner", size = { 100, 100 } } },
					},
				}))
				check.is_true(has(errs, "a CanvasGroup inside the CanvasGroup T.Root.Card"))
				local errs2 = messages(screen({
					{
						type = "canvas",
						name = "Card",
						size = { 300, 200 },
						children = { { type = "hitmarker", name = "Hit" } },
					},
				}))
				check.is_true(has(errs2, "a CanvasGroup inside the CanvasGroup"))
				-- deeper still: a panel between them does not hide it
				local errs3 = messages(screen({
					{
						type = "canvas",
						name = "Card",
						size = { 300, 200 },
						children = {
							{
								type = "panel",
								name = "Mid",
								size = { 200, 100 },
								children = { { type = "canvas", name = "Deep", size = { 50, 50 } } },
							},
						},
					},
				}))
				check.is_true(has(errs3, "a CanvasGroup inside the CanvasGroup T.Root.Card"))
				local ok = messages(screen({
					{ type = "canvas", name = "A", size = { 100, 100 } },
					{ type = "canvas", name = "B", size = { 100, 100 } },
					{ type = "hitmarker", name = "Hit" },
				}))
				check.is_false(has(ok, "CanvasGroup"))
			end
		)
		test.case(
			"the rule counts compiled instances (UI.canvasProblems) and flags a hidden one still allocated",
			function()
				local tree = {
					ClassName = "CanvasGroup",
					Name = "A",
					Properties = {},
					Children = {
						{
							ClassName = "Frame",
							Name = "F",
							Properties = {},
							Children = {
								{
									ClassName = "CanvasGroup",
									Name = "B",
									Properties = { GroupTransparency = 1 },
									Children = {},
								},
							},
						},
					},
				}
				local nested, idle = UI.canvasProblems(tree, "S.A")
				check.equal(#nested, 1)
				check.equal(nested[1].path, "S.A.F.B")
				check.equal(nested[1].inside, "S.A")
				check.equal(#idle, 1)
				check.equal(idle[1], "S.A.F.B")
				local _, idle2 = UI.canvasProblems({
					ClassName = "CanvasGroup",
					Name = "H",
					Properties = { GroupTransparency = 1, Visible = false },
					Children = {},
				}, "S.H")
				check.equal(#idle2, 0)
				-- a canvas hidden by its alpha alone warns; the hit marker compiles hidden for real (Visible false)
				local _, warns =
					messages(screen({ { type = "canvas", name = "Fader", size = { 100, 100 }, groupAlpha = 1 } }))
				check.is_true(has(warns, "keeps its texture in video memory"))
				local model = UI.compile(screen({ { type = "hitmarker", name = "Hit" } }))
				check.equal(byName(model, "Hit").Properties.Visible, false)
			end
		)
		test.case("an fx that can flash more than 3 times a second is an error; the same fx slower passes", function()
			local function fxErrors(fx: { any }): string
				return (messages(screen({ { type = "label", name = "L", text = "HIT", size = { 200, 50 }, fx = fx } })))
			end
			check.is_true(has(fxErrors({ { kind = "shimmer", period = 0.3 } }), "shimmer can flash 4 times"))
			check.is_true(has(fxErrors({ { kind = "ping", period = 0.3 } }), "ping can flash 4 times"))
			check.is_true(has(fxErrors({ { kind = "split", every = 0.3, dur = 0.03 } }), "split can flash 5 times"))
			check.is_true(has(fxErrors({ { kind = "flicker", dur = 0.35 } }), "flicker can flash 6 times"))
			check.is_false(has(fxErrors({ { kind = "shimmer", period = 0.5 } }), "can flash"))
			check.is_false(has(fxErrors({ { kind = "split", every = 0.4, dur = 0.1 } }), "can flash")) -- (3: allowed)
			check.is_false(has(fxErrors({ { kind = "flicker" } }), "can flash")) -- (the default dur 0.2: 3 dips)
			check.is_false(has(fxErrors({ { kind = "burn_in" } }), "can flash"))
		end)
		test.case("the counts follow the runtime's schedule (UI.flashCount / UI.loopFlashCount)", function()
			check.equal(UI.flashCount("shimmer", { period = 0.34 }), 3)
			check.equal(UI.flashCount("ping", { period = 1 }), 2)
			check.equal(UI.flashCount("split", { every = 0.4, dur = 0.1 }), 3)
			check.equal(UI.flashCount("flicker", { every = 3.5, dur = 0.2 }), 3)
			check.equal(UI.flashCount("flicker", { every = 0.3, dur = 2 }), 15) -- (30 fps re-rolls: at most 15)
			check.equal(UI.flashCount("burn_in", { dur = 0.6 }), 0)
			check.equal(UI.loopFlashCount("glint", 0.7), 1)
			check.equal(UI.loopFlashCount("glint", 12), 5)
			check.equal(UI.loopFlashCount("pulse", 50), 0) -- (a scale loop: no lit-dark swing)
		end)
		test.case("a glint loop too fast is an error at its motion.loop", function()
			local errs = messages(screen({
				{
					type = "button",
					name = "Go",
					text = "GO",
					size = { 160, 56 },
					motion = { loop = { type = "glint", speed = 12 } },
				},
			}))
			check.is_true(has(errs, "a glint loop at speed 12 flashes 5 times"))
			local ok = messages(screen({
				{
					type = "button",
					name = "Go",
					text = "GO",
					size = { 160, 56 },
					motion = { loop = { type = "glint", speed = 0.7 } },
				},
			}))
			check.is_false(has(ok, "flashes"))
		end)
	end)

	-- LIMITATIONS_FIXES_V4 UI-X 6.4 step 4 (kit ui motion-ref): an identity whose motion was MEASURED from the source
	-- game's footage is held to it - typed taste that strays is an error
	test.suite("motion measured, not typed (kit ui motion-ref)", function()
		local measured = { clip = "menu.mp4", duration = 0.42, ease = "cubic", stagger = 0.08 }
		local function idErrors(motion: any): string
			local spec = screen({ { type = "label", name = "L", text = "GO", size = { 100, 30 } } })
			spec.identity = "m"
			local _, issues = UI.compile(spec, nil, nil, { m = { name = "m", motion = motion } })
			local out = {}
			for _, i in issues do
				if i.severity == "error" then
					table.insert(out, i.path .. " " .. i.message)
				end
			end
			return table.concat(out, "\n")
		end
		test.case(
			"duration, stagger and overshoot off the measurement are errors; the measured numbers pass",
			function()
				local errs = idErrors({
					enter = { type = "slam", duration = 0.18, ease = "back" },
					stagger = 0.03,
					measured = measured,
				})
				check.is_true(string.find(errs, "identity:m.motion.enter.duration", 1, true) ~= nil)
				check.is_true(string.find(errs, "identity:m.motion.stagger", 1, true) ~= nil)
				check.is_true(string.find(errs, "settles without one", 1, true) ~= nil)
				check.equal(
					idErrors({
						enter = { type = "fade", duration = 0.4, ease = "quad" },
						stagger = 0.08,
						measured = measured,
					}),
					""
				)
				-- within 25% (0.105 s) passes, past it fails; a measured overshoot needs back / elastic
				check.equal(idErrors({ enter = { duration = 0.52 }, measured = measured }), "")
				check.is_true(idErrors({ enter = { duration = 0.53 }, measured = measured }) ~= "")
				local back = table.clone(measured)
				back.ease = "back"
				check.is_true(
					string.find(idErrors({ enter = { ease = "quad" }, measured = back }), "overshoots", 1, true) ~= nil
				)
				check.equal(idErrors({ enter = { ease = "elastic" }, measured = back }), "")
			end
		)
		test.case("no measurement: typed motion is not judged; a broken measurement is an error", function()
			check.equal(idErrors({ enter = { type = "slam", duration = 0.18, ease = "back" }, stagger = 0.03 }), "")
			check.is_true(
				string.find(idErrors({ measured = { duration = 0.4 } }), "motion-ref --identity", 1, true) ~= nil
			)
		end)
	end)
end

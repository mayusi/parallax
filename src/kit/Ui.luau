-- Ui (ReplicatedStorage.kit.Ui) — drive kit screens from gameplay code. CLIENT ONLY (PlayerGui).
--   Ui.find("RpgHud", "Hud.Vitals.Hp")    -> the node at that path (nil if missing) — paths = spec names
--   Ui.bar(node, 0.4)                       -> a "bar" fills to 40%; its Ghost (ghost: true) follows late on damage
--   Ui.ring(node, 0.4)                      -> a "ring" component fills to 40% clockwise from the top
--   Ui.flash(node)                          -> a "hitmarker" (or any CanvasGroup) pops in and fades out
--   Ui.setReduceFlashing(true)              -> a player setting: split / flicker / ping stay still (WCAG 2.3.1)
--   Ui.backdrop(screen, open)               -> the world behind a menu blurs / darkens (the spec's "backdrop")
--   Ui.write(node, "any words")             -> a "glyphs" label sets text in the identity's own lettering
--   Ui.track / Ui.hurt / Ui.fly             -> world markers pinned to the edge, damage arcs, coins into a counter
--   Ui.waypoint / Ui.damageArc / Ui.streakLadder / Ui.compare -> the Combat Feedback Kit (rules: UiCombat)
--   Ui.toast / Ui.modal / Ui.back / Ui.loading / Ui.coach  -> queues, the back stack, loading, tutorial spotlights
--   Ui.chat(screen) / Ui.core({health=false}) -> Roblox chat in the identity; hide CoreGui the game replaces
--   Ui.wipe / Ui.setTextScale / Ui.setHighContrast -> branded wipes, player text size, high contrast
--   Ui.set / Ui.get / Ui.list                -> data binding ("bind" key) and virtual lists (only visible rows exist)
--   Ui.fx(node, kind?)                      -> runtime UI materials (shimmer, ping, burn_in, split, flicker)
--   Ui.path(node, share?)                   -> a "path" node's vector line (Path2D), drawn to a share of its length
--   Ui.burst(node, "preset")                -> UI particles: pooled sprites fly out of the node (identity presets)
--   Ui.attach(template, part) / Ui.floater(template, pos, text)  -> world-space UI ("space": "world" specs)
--   Ui.styles() / Ui.link(gui, "sim")        -> the identity's StyleSheet (kit ui style) on hand-made screens
--   Ui.go(from, to, {transition="shared", shared={a, b}})  -> a flow step; the shared piece flies between screens
--   Ui.gamepad(screen)                      -> focus piece, d-pad nav, firstFocus, pad glyphs (UiMotion calls it)
--   Ui.setState(node, "disabled"|nil)       -> a control's designed state (its spec "states"); Ui.getState
--   Ui.punch(node)                          -> a quick scale bump (ready! / +1 / value changed)
--   Ui.text(label, "READY", "good")         -> set text (+ a skin colour name or Color3) with a punch; a tracked
--                                              label (tracking: 0.3) rebuilds its glyphs
--   Ui.counter(node, 14352 [, seconds])     -> a "counter" rolls to the number (separators kept)
--   Ui.push(feed, "You hit Dummy", Color3)  -> a "feed" component gets a new line (oldest drops, lines fade out)
--   Ui.show(screenGui, true)                -> enable + play the ENTER choreography (delays, container stagger);
--                                              false = fade out, then disable
--   Ui.transition(fromGui, toGui)           -> one screen out, the next in
--   Ui.reveal(node)                         -> replay the enter choreography of a node and everything under it
--   Ui.spring(obj, "Size", target [, frequency, damping]) -> a damped spring on any numeric / UDim2 / Vector2 /
--                                              Color3 property (frequency in Hz, damping 1 = critical, < 1 pops)
--   Ui.scale(screenGui)                     -> applies the spec's "scale": {"phone": 0.72} as a UIScale on the root
-- The motion attributes the compiler writes ("motion": {...} in a spec) are played by Ui.bind / Ui.show — the
-- kit's UiMotion client script binds every kit screen automatically; you never call those yourself.
local GuiService = game:GetService("GuiService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")

-- the Combat Feedback Kit's pure rules (waypoints, damage bearings, the 3-flashes-a-second gate, the streak ladder,
-- compare lines): specced in Lune by kit/test/spec/uicombat.spec.luau
local UiCombat = require(script.Parent:WaitForChild("UiCombat"))
-- where a StyleQuery and its "@Name" rules must sit for the engine to apply them (Ui.styles / Ui.link)
local UiStyleRules = require(script.Parent:WaitForChild("UiStyleRules"))

-- the player's Reduced Motion setting (native, 2026): enters become a short fade, loops stay still (WCAG 2.3.3)
local function reducedMotion(): boolean
	local ok, on = pcall(function()
		return (GuiService :: any).ReducedMotionEnabled
	end)
	return ok and on == true
end

local Ui = {}
Ui.clientBound = false -- the UiMotion client sets it: then flipping a screen's Enabled plays its enters, not Ui.show
Ui.forceViewport = nil :: string? -- "phone" | "tablet" | "desktop": Ui.scale pretends (QA of the "at" reflows)

local QUICK = TweenInfo.new(0.12, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)
local SMOOTH = TweenInfo.new(0.25, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)
local POP = TweenInfo.new(0.3, Enum.EasingStyle.Back, Enum.EasingDirection.Out)

local EASE = {
	quad = Enum.EasingStyle.Quad,
	sine = Enum.EasingStyle.Sine,
	back = Enum.EasingStyle.Back,
	expo = Enum.EasingStyle.Exponential,
	linear = Enum.EasingStyle.Linear,
	elastic = Enum.EasingStyle.Elastic,
}

local function info(duration: number, ease: string?, delay: number?): TweenInfo
	return TweenInfo.new(
		duration,
		EASE[ease or "quad"] or Enum.EasingStyle.Quad,
		Enum.EasingDirection.Out,
		0,
		false,
		delay or 0
	)
end

local function scaler(gui: GuiObject): UIScale
	local found = gui:FindFirstChild("KitScale")
	if found and found:IsA("UIScale") then
		return found
	end
	local s = Instance.new("UIScale")
	s.Name = "KitScale"
	s.Parent = gui
	return s
end

local function num(inst: Instance, key: string, default: number): number
	local v = inst:GetAttribute(key)
	return if type(v) == "number" then v else default
end

-- what each drawn thing looked like AS DESIGNED (its transparencies): fades restore it, and a glyph rebuild in the
-- middle of a fade starts the new glyphs from it, not from the half-faded template
local originals: { [Instance]: { [string]: number } } = setmetatable({}, { __mode = "k" }) :: any
-- where each node lives as designed (position, size): an enter always lands there, however often it replays
local homes: { [GuiObject]: { pos: UDim2, size: UDim2 } } = setmetatable({}, { __mode = "k" }) :: any
-- one count per screen: a show(false) then show(true) inside the fade-out must not disable the shown screen
local showGen: { [ScreenGui]: number } = setmetatable({}, { __mode = "k" }) :: any
-- until when a node's enter is in flight: a replay inside that window keeps the remembered home, a later one
-- re-reads it (game code may have moved or resized the node on purpose since)
local playingUntil: { [GuiObject]: number } = setmetatable({}, { __mode = "k" }) :: any

-- ------------------------------------------------------------------ find / colours
function Ui.find(screen: string, path: string): GuiObject?
	local player = Players.LocalPlayer
	local gui = player and player:FindFirstChildOfClass("PlayerGui")
	local node: Instance? = gui and gui:FindFirstChild(screen)
	for part in string.gmatch(path, "[^%.]+") do
		node = node and node:FindFirstChild(part)
	end
	return if node and node:IsA("GuiObject") then node else nil
end

local function colorOf(node: Instance, c: any): Color3?
	if typeof(c) == "Color3" then
		return c
	end
	if type(c) == "string" then
		-- skin / identity colours ride on the ScreenGui as Kit_<token> attributes (written by the compiler)
		local screen = node:FindFirstAncestorOfClass("ScreenGui")
		local hex = screen and screen:GetAttribute("Kit_" .. c)
		if type(hex) == "string" then
			return Color3.fromHex(hex)
		end
	end
	return nil
end

-- ------------------------------------------------------------------ springs (frequency + damping, like spr)
type Spring = {
	obj: Instance,
	prop: string,
	pos: { number },
	vel: { number },
	target: { number },
	kind: string,
	f: number,
	z: number,
}
local springs: { [Instance]: { [string]: Spring } } = setmetatable({}, { __mode = "k" }) :: any
local springLoop: RBXScriptConnection? = nil

local function unpackValue(v: any): ({ number }, string)
	local t = typeof(v)
	if t == "number" then
		return { v }, "number"
	elseif t == "UDim2" then
		return { v.X.Scale, v.X.Offset, v.Y.Scale, v.Y.Offset }, "UDim2"
	elseif t == "Vector2" then
		return { v.X, v.Y }, "Vector2"
	elseif t == "Vector3" then
		return { v.X, v.Y, v.Z }, "Vector3"
	elseif t == "Color3" then
		return { v.R, v.G, v.B }, "Color3"
	elseif t == "UDim" then
		return { v.Scale, v.Offset }, "UDim"
	end
	error(`Ui.spring: cannot animate a {t}`)
end

local function packValue(n: { number }, kind: string): any
	if kind == "number" then
		return n[1]
	elseif kind == "UDim2" then
		return UDim2.new(n[1], n[2], n[3], n[4])
	elseif kind == "Vector2" then
		return Vector2.new(n[1], n[2])
	elseif kind == "Vector3" then
		return Vector3.new(n[1], n[2], n[3])
	elseif kind == "Color3" then
		return Color3.new(math.clamp(n[1], 0, 1), math.clamp(n[2], 0, 1), math.clamp(n[3], 0, 1))
	end
	return UDim.new(n[1], n[2])
end

local function stepSprings(dt: number)
	local h = math.min(dt, 1 / 30)
	local any = false
	for obj, props in springs do
		for prop, s in props do
			local w = 2 * math.pi * s.f
			local done = true
			for i, x in s.pos do
				-- semi-implicit Euler on x'' = -w² (x - target) - 2 z w x'
				local a = -w * w * (x - s.target[i]) - 2 * s.z * w * s.vel[i]
				s.vel[i] += a * h
				s.pos[i] = x + s.vel[i] * h
				if math.abs(s.pos[i] - s.target[i]) > 1e-3 or math.abs(s.vel[i]) > 1e-3 then
					done = false
				end
			end
			if done then
				for i in s.pos do
					s.pos[i] = s.target[i]
					s.vel[i] = 0
				end
				props[prop] = nil
			else
				any = true
			end
			if obj.Parent then
				(obj :: any)[prop] = packValue(s.pos, s.kind)
			else
				props[prop] = nil
			end
		end
		if next(props) == nil then
			springs[obj] = nil
		end
	end
	if not any and springLoop then
		springLoop:Disconnect()
		springLoop = nil
	end
end

function Ui.spring(obj: Instance, prop: string, target: any, frequency: number?, damping: number?)
	local tgt, kind = unpackValue(target)
	local props = springs[obj]
	if not props then
		props = {}
		springs[obj] = props
	end
	local s = props[prop]
	if not s then
		local cur = unpackValue((obj :: any)[prop])
		local vel = table.create(#cur, 0)
		s = {
			obj = obj,
			prop = prop,
			pos = cur,
			vel = vel,
			target = tgt,
			kind = kind,
			f = frequency or 4,
			z = damping or 1,
		}
		props[prop] = s
	else
		s.target = tgt
		s.f = frequency or s.f
		s.z = damping or s.z
	end
	if not springLoop then
		springLoop = RunService.Heartbeat:Connect(stepSprings)
	end
end

-- ------------------------------------------------------------------ values: bars, rings, counters, text, feed
function Ui.bar(node: GuiObject?, value: number)
	local fill = node and node:FindFirstChild("Fill")
	if not (fill and fill:IsA("GuiObject")) then
		return
	end
	local v = math.clamp(value, 0, 1)
	local was = fill.Size.X.Scale
	TweenService:Create(fill, QUICK, { Size = UDim2.fromScale(v, 1) }):Play()
	local ghost = node and node:FindFirstChild("Ghost")
	if ghost and ghost:IsA("GuiObject") then
		if v < was then
			-- damage: the pale trail holds, then drains to the new value
			task.delay(0.45, function()
				if ghost.Parent then
					TweenService:Create(
						ghost,
						TweenInfo.new(0.5, Enum.EasingStyle.Sine, Enum.EasingDirection.In),
						{ Size = UDim2.fromScale(v, 1) }
					):Play()
				end
			end)
		else
			ghost.Size = UDim2.fromScale(v, 1)
		end
	end
end

function Ui.ring(node: GuiObject?, value: number)
	if not node then
		return
	end
	local a = math.clamp(value, 0, 1) * 360
	local halves: { [string]: number } = { Right = math.clamp(a, 0, 180), Left = math.clamp(a, 180, 360) }
	for name, rot in halves do
		local half = node:FindFirstChild(name)
		local arc = half and half:FindFirstChild("Arc")
		local grad = arc and arc:FindFirstChildOfClass("UIGradient")
		if grad then
			grad.Rotation = rot
		end
	end
	node:SetAttribute("KitRing", value)
end

-- a hit confirm flashes at most three times a second (WCAG 2.3.1, V4 UI-X 13.6): a faster stream of hits keeps the
-- marker LIT (no pop, its fade pushed back) instead of strobing it. (The rule is UiCombat.limiter, specced in Lune.)
local flashGates: { [GuiObject]: UiCombat.Limiter } = setmetatable({}, { __mode = "k" }) :: any
local flashToken: { [GuiObject]: number } = setmetatable({}, { __mode = "k" }) :: any
local flashFade: { [GuiObject]: Tween } = setmetatable({}, { __mode = "k" }) :: any

function Ui.flash(node: GuiObject?, hold: number?)
	if not node then
		return
	end
	if node:IsA("CanvasGroup") then
		local gate = flashGates[node]
		if not gate then
			gate = UiCombat.limiter(3, 1)
			flashGates[node] = gate
		end
		local fresh = gate:allow(os.clock())
		local token = (flashToken[node] or 0) + 1
		flashToken[node] = token
		local fading = flashFade[node]
		if fading then
			fading:Cancel()
		end
		-- (a hidden marker is compiled Visible = false so its texture is freed: drawn only while it shows)
		node.Visible = true
		node.GroupTransparency = 0
		if fresh then
			local s = scaler(node)
			s.Scale = 1.35
			TweenService:Create(s, QUICK, { Scale = 1 }):Play()
		end
		task.delay(hold or 0.08, function()
			if flashToken[node] == token then
				local fade = TweenService:Create(node, TweenInfo.new(0.22), { GroupTransparency = 1 })
				flashFade[node] = fade
				fade.Completed:Once(function(state: Enum.PlaybackState)
					if state == Enum.PlaybackState.Completed and flashToken[node] == token then
						node.Visible = false -- (faded out: hidden for real, the CanvasGroup's texture released)
					end
				end)
				fade:Play()
			end
		end)
	else
		node.Visible = true
		task.delay(hold or 0.25, function()
			node.Visible = false
		end)
	end
end

function Ui.punch(node: GuiObject?, amount: number?)
	if not node then
		return
	end
	local s = scaler(node)
	s.Scale = 1 + (amount or 0.12)
	TweenService:Create(s, POP, { Scale = 1 }):Play()
end

local function formatNumber(v: number, sep: string, short: boolean?): string
	if short then
		-- 1234 -> "1.2K", 3400000 -> "3.4M" (the simulator convention: the number must fit a pill)
		local a = math.abs(v)
		local sign = if v < 0 then "-" else ""
		local steps: { { n: number, s: string } } =
			{ { n = 1e12, s = "T" }, { n = 1e9, s = "B" }, { n = 1e6, s = "M" }, { n = 1e3, s = "K" } }
		for _, step in steps do
			if a >= step.n then
				local n = a / step.n
				local text = if n >= 100 then tostring(math.floor(n + 0.5)) else string.format("%.1f", n)
				text = string.gsub(text, "%.0$", "")
				return `{sign}{text}{step.s}`
			end
		end
		return `{sign}{math.floor(a + 0.5)}`
	end
	local s = tostring(math.floor(math.abs(v) + 0.5))
	local out = string.reverse((string.gsub(string.reverse(s), "(%d%d%d)", "%1" .. sep)))
	if string.sub(out, 1, 1) == sep then
		out = string.sub(out, 2)
	end
	return (if v < 0 then "-" else "") .. out
end

-- a tracked label (letters set apart) is a Frame of glyph labels: rebuild them from the first glyph
local function glyphHost(frame: GuiObject): GuiObject
	local row = frame:FindFirstChild("Glyphs") -- (the compiler keeps the glyph row in its own frame)
	return if row and row:IsA("GuiObject") then row else frame
end

-- the ransom patterns: the same as the compiler's (kit/lib/ui.luau trackedLabel) — a word always cuts the same way
local RANSOM_SIZES = { 1.0, 0.84, 1.22, 0.92, 1.14, 0.8, 1.3, 1.0, 0.88, 1.18 }
local RANSOM_ROTS = { -8, 6, -3, 10, -11, 4, -6, 9, -2, 7 }
local RANSOM_INVERTS = { false, true, false, false, true, false, true, false, false, true }
local RANSOM_LOWERS = { false, false, true, false, true, false, false, true, false, false }

-- ransom lettering: every glyph its own cutout (an ink scrap with a paper letter, or a paper scrap with an ink
-- letter). Rebuilt from two templates — the first plain and the first inverted glyph — so a new word keeps the
-- cutouts' plates, colours and fonts; a word with only one kind of glyph reuses that kind for both.
local function reransom(
	frame: GuiObject,
	host: GuiObject,
	text: string,
	templates: { plain: TextLabel?, inverted: TextLabel? }
)
	local size = num(frame, "Kit_TextSize", 18)
	local seed = num(frame, "Kit_RansomSeed", 0)
	local i = 0
	for _, cp in utf8.codes(text) do
		i += 1
		local ch = utf8.char(cp)
		local k = ((i + seed - 1) % #RANSOM_SIZES) + 1
		local gs = math.floor(size * RANSOM_SIZES[k] + 0.5)
		local inverted = RANSOM_INVERTS[k] and ch ~= " "
		local tpl = if inverted
			then (templates.inverted or templates.plain)
			else (templates.plain or templates.inverted)
		if not tpl then
			return
		end
		local g = tpl:Clone()
		g.Name = `G{i}`
		g.LayoutOrder = i
		if ch == " " then
			g.Text = ""
			g.Rotation = 0
			g.Size = UDim2.fromOffset(math.floor(size * 0.3 + 0.5), math.floor(gs * 1.52 + 0.5))
			local plate = g:FindFirstChild("Plate")
			if plate then
				plate:Destroy()
			end
		else
			g.Text = if RANSOM_LOWERS[k] then string.lower(ch) else ch
			g.TextSize = gs
			g.Rotation = RANSOM_ROTS[k]
			g.Size = UDim2.fromOffset(math.floor(gs * 0.8 + 0.5), math.floor(gs * 1.52 + 0.5))
		end
		g.Parent = host
	end
	frame:SetAttribute("Kit_Text", text)
end

local function retrack(frame: GuiObject, text: string)
	local host = glyphHost(frame)
	local template: TextLabel? = nil
	local look: { [string]: number }? = nil
	local strokeLook: { [string]: number }? = nil
	local ransom = frame:GetAttribute("Kit_Ransom") == true
	local templates: { plain: TextLabel?, inverted: TextLabel? } = {}
	for _, c in host:GetChildren() do
		if c:IsA("TextLabel") and string.match(c.Name, "^G%d+$") then
			if ransom and c.Text ~= "" then
				if c:GetAttribute("Kit_Inverted") == true then
					templates.inverted = templates.inverted or c:Clone()
				else
					templates.plain = templates.plain or c:Clone()
				end
			end
			if not template then
				template = c:Clone()
				look = originals[c] -- (the glyph may be mid-fade: its designed look, not its current one)
				local st = c:FindFirstChildOfClass("UIStroke")
				strokeLook = if st then originals[st] else nil
			end
			c:Destroy()
		end
	end
	if ransom and (templates.plain or templates.inverted) then
		return reransom(frame, host, text, templates)
	end
	if not template then
		-- a tracked label that started empty has no glyph to copy: build one from the recipe the compiler left
		local t = Instance.new("TextLabel")
		t.BackgroundTransparency = 1
		t.TextSize = num(frame, "Kit_TextSize", 18)
		local face = frame:GetAttribute("Kit_Font")
		if type(face) == "string" then
			for _, item in Enum.Font:GetEnumItems() do
				if item.Name == face then
					t.Font = item :: Enum.Font
					break
				end
			end
		end
		local tc = frame:GetAttribute("Kit_TextColor")
		t.TextColor3 = if type(tc) == "string" and string.sub(tc, 1, 1) == "#"
			then Color3.fromHex(tc)
			else colorOf(frame, tc) or Color3.new(1, 1, 1)
		local oc = frame:GetAttribute("Kit_TextOutline")
		if type(oc) == "string" and string.sub(oc, 1, 1) == "#" then
			local stroke = Instance.new("UIStroke")
			stroke.Name = "TextOutline"
			stroke.Color = Color3.fromHex(oc)
			stroke.Thickness = num(frame, "Kit_TextOutlineWidth", 1.5)
			stroke.Transparency = 0.25
			stroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Contextual
			stroke.Parent = t
		end
		template = t
	end
	local tpl: TextLabel = template :: TextLabel
	local size = num(frame, "Kit_TextSize", tpl.TextSize)
	local i = 0
	for _, cp in utf8.codes(text) do
		i += 1
		local ch = utf8.char(cp)
		local g = tpl:Clone()
		local anyG: any = g
		if look then
			for p, v in look do
				anyG[p] = v
			end
		end
		local gst: any = g:FindFirstChildOfClass("UIStroke")
		if gst and strokeLook then
			for p, v in strokeLook do
				gst[p] = v
			end
		end
		g.Name = `G{i}`
		g.LayoutOrder = i
		if ch == " " then
			g.Text = ""
			g.AutomaticSize = Enum.AutomaticSize.None
			g.Size = UDim2.fromOffset(math.floor(size * 0.3 + 0.5), math.floor(size * 1.3 + 0.5))
		else
			g.Text = ch
			g.AutomaticSize = Enum.AutomaticSize.X
			g.Size = UDim2.fromOffset(0, math.floor(size * 1.3 + 0.5))
		end
		g.Parent = host
	end
	frame:SetAttribute("Kit_Text", text)
end

function Ui.text(node: GuiObject?, text: string, color: any?)
	if not node then
		return
	end
	if node:GetAttribute("Kit_Tracking") ~= nil then
		if node:GetAttribute("Kit_Text") ~= text then
			retrack(node, text)
			Ui.punch(node, 0.06)
		end
		local c = colorOf(node, color)
		if c then
			for _, g in glyphHost(node):GetChildren() do
				if g:IsA("TextLabel") then
					g.TextColor3 = c
				end
			end
		end
		return
	end
	-- gradient / plate-backed buttons and labels keep their text in a child "Label" (see the compiler)
	local inner = node:FindFirstChild("Label")
	local target: Instance? = if inner and inner:IsA("TextLabel") then inner else node
	if target and (target:IsA("TextLabel") or target:IsA("TextButton")) then
		local label = target :: TextLabel
		if label.Text ~= text then
			label.Text = text
			Ui.punch(label, 0.08)
		end
		local c = colorOf(label, color)
		if c then
			label.TextColor3 = c
		end
	end
end

local counters: { [Instance]: RBXScriptConnection } = {}

function Ui.counter(node: GuiObject?, value: number, seconds: number?)
	if not (node and node:IsA("TextLabel")) then
		return
	end
	local label = node :: TextLabel
	local from = num(label, "Kit_Counter", 0)
	local prefix = label:GetAttribute("Kit_CounterPrefix") or ""
	local suffix = label:GetAttribute("Kit_CounterSuffix") or ""
	local sep = label:GetAttribute("Kit_CounterSep") or ","
	local short = label:GetAttribute("Kit_CounterFormat") == "short"
	if counters[label] then
		counters[label]:Disconnect()
	end
	local dur = seconds or 0.8
	local t0 = os.clock()
	label:SetAttribute("Kit_Counter", value)
	counters[label] = RunService.Heartbeat:Connect(function()
		local k = math.clamp((os.clock() - t0) / dur, 0, 1)
		local e = 1 - (1 - k) ^ 3
		label.Text = tostring(prefix)
			.. formatNumber(from + (value - from) * e, tostring(sep), short)
			.. tostring(suffix)
		if k >= 1 then
			counters[label]:Disconnect()
			counters[label] = nil
			Ui.punch(label, 0.06)
		end
	end)
end

-- a number drawn from a DIGIT SET (the compiler's "number" node): one image cell per character, each glyph's id from
-- the frame's Kit_DigitIds — cells are added (cloned from C1) or hidden as the length changes, laid out by Kit_DigitAlign
function Ui.number(node: GuiObject?, text: string)
	if not node then
		return
	end
	local ids: { [string]: string } = {}
	for pair in string.gmatch(tostring(node:GetAttribute("Kit_DigitIds") or ""), "[^;]+") do
		local k, v = string.match(pair, "^(.-)=(.*)$")
		if k and v then
			ids[k] = v
		end
	end
	local template = node:FindFirstChild("C1")
	if not (template and template:IsA("ImageLabel")) then
		return
	end
	local cw = num(node, "Kit_DigitCell", 24) -- (the advance; a cell is Kit_DigitWidth wide, centred in its slot)
	local width = num(node, "Kit_DigitWidth", cw)
	-- the attributes are DESKTOP pixels; a phone / tablet "at.scale" resizes the cells, so the advance follows the
	-- live cell width (the digits landed 2x apart and past the frame on a phone — audit 2026-10-16)
	local live = (template :: ImageLabel).Size.X.Offset
	if width > 0 and live > 0 and math.abs(live - width) > 0.5 then
		cw = cw * live / width
		width = live
	end
	local narrow: { [string]: number } = {}
	for pair in string.gmatch(tostring(node:GetAttribute("Kit_DigitNarrow") or ""), "[^;]+") do
		local k, v = string.match(pair, "^(.-)=(.*)$")
		if k and v and tonumber(v) then
			narrow[k] = tonumber(v) :: number
		end
	end
	local function codeOf(ch: string): string
		return if string.match(ch, "^%w$") then ch else `u{string.byte(ch)}`
	end
	local function advOf(ch: string): number
		return math.floor(cw * (narrow[codeOf(ch)] or 1) + 0.5)
	end
	local align = tostring(node:GetAttribute("Kit_DigitAlign") or "center")
	local n = #text
	local total = 0
	for j = 1, n do
		total += advOf(string.sub(text, j, j))
	end
	local slot = 0
	local i = 1
	while true do
		local cell = node:FindFirstChild(`C{i}`) :: ImageLabel?
		if i > n and not cell then
			break
		end
		if i <= n then
			if not cell then
				local c = (template :: ImageLabel):Clone()
				c.Name = `C{i}`
				c.Parent = node
				cell = c
			end
			local ch = string.sub(text, i, i)
			local code = if string.match(ch, "^%w$") then ch else `u{string.byte(ch)}`
			local a = advOf(ch)
			local x = math.floor(slot + (a - width) / 2 + 0.5) -- (each cell centred in its own slot, rounded like the compiler)
			slot += a
			local cellX = cell :: ImageLabel
			cellX.Image = ids[code] or ""
			cellX.Visible = true
			if align == "right" then
				cellX.Position = UDim2.new(1, -(total - x), 0, 0)
			elseif align == "left" then
				cellX.Position = UDim2.fromOffset(x, 0)
			else
				cellX.Position = UDim2.new(0.5, x - total / 2, 0, 0)
			end
		elseif cell then
			cell.Visible = false
		end
		i += 1
	end
	node:SetAttribute("Kit_Number", text)
end

-- a flipbook (the compiler's "flipbook" key: Kit_Flip = every frame's uploaded id): the picture steps through its
-- frames at Kit_FlipFps — a smear card's swap, a spun logo, a drip growing. Plays once (Kit_FlipLoop false) or loops;
-- returns a stop function. Calling it again on a playing node restarts it.
local flipping: { [Instance]: number } = setmetatable({}, { __mode = "k" }) :: any

function Ui.flipbook(node: GuiObject?, fps: number?, loop: boolean?): () -> ()
	local function noop() end
	if not (node and (node:IsA("ImageLabel") or node:IsA("ImageButton"))) then
		return noop
	end
	local frames: { string } = {}
	for id in string.gmatch(tostring(node:GetAttribute("Kit_Flip") or ""), "[^;]+") do
		table.insert(frames, id)
	end
	if #frames == 0 then
		return noop
	end
	local rate = fps or num(node, "Kit_FlipFps", 12)
	local loops = if loop ~= nil then loop else node:GetAttribute("Kit_FlipLoop") ~= false
	local token = (flipping[node] or 0) + 1
	flipping[node] = token
	local img = node :: ImageLabel
	task.spawn(function()
		local t0 = os.clock()
		while flipping[node] == token and node.Parent do
			local k = math.floor((os.clock() - t0) * rate)
			if not loops and k >= #frames then
				img.Image = frames[#frames]
				break
			end
			img.Image = frames[(k % #frames) + 1]
			task.wait(1 / math.max(1, rate))
		end
	end)
	return function()
		if flipping[node] == token then
			flipping[node] = nil
		end
	end
end

-- runtime UI materials (the compiler's "fx" key: Kit_Fx = "kind:k=v,...;..." + the Fx_* children it built):
-- shimmer (a light band sweeps the glint), ping (an echo grows and fades), burn_in (a lit wipe reveals the piece,
-- once), split (two tinted copies jump apart in short glitches), flicker (the piece dips in random bursts).
-- Ui.fx(node) starts every fx the node carries (Ui.bind does it for you); Ui.fx(node, "burn_in") plays one again.
-- Returns a stop function. Reduced motion: loops stay still and a burn_in shows the piece at once.
local fxRunning: { [Instance]: { [string]: number } } = setmetatable({}, { __mode = "k" }) :: any

local function fxParams(node: Instance): { { kind: string, v: { [string]: number } } }
	local out = {}
	for item in string.gmatch(tostring(node:GetAttribute("Kit_Fx") or ""), "[^;]+") do
		local kind, rest = string.match(item, "^([%w_]+):(.*)$")
		if kind then
			local v: { [string]: number } = {}
			for k, x in string.gmatch(rest or "", "([%w_]+)=([%-%d%.e]+)") do
				v[k] = tonumber(x) or 0
			end
			table.insert(out, { kind = kind, v = v })
		end
	end
	return out
end

local function fxAlpha(inst: Instance?, value: number?): number
	if not inst then
		return 1
	end
	local prop = if inst:IsA("ImageLabel") or inst:IsA("ImageButton")
		then "ImageTransparency"
		elseif inst:IsA("TextLabel") or inst:IsA("TextButton") then "TextTransparency"
		else "BackgroundTransparency"
	if value ~= nil then
		(inst :: any)[prop] = value
		return value
	end
	return (inst :: any)[prop]
end

local function fxShown(node: GuiObject): boolean
	local screen = node:FindFirstAncestorWhichIsA("LayerCollector")
	return node.Visible and (screen == nil or screen.Enabled)
end

local function fxTween(inst: Instance, seconds: number, goal: { [string]: any }, style: Enum.EasingStyle?)
	local tw = TweenService:Create(
		inst,
		TweenInfo.new(seconds, style or Enum.EasingStyle.Sine, Enum.EasingDirection.InOut),
		goal
	)
	tw:Play()
	return tw
end

-- REDUCE FLASHING (a player's setting; WCAG 2.3.1): the fx that flash — split, flicker, ping — stay still while it
-- is on (a shimmer sweep and a burn-in reveal are not flashes). Set it from the game's settings menu.
local reduceFlashing = false
function Ui.setReduceFlashing(on: boolean)
	reduceFlashing = on == true
end

local FLASHING = { split = true, flicker = true, ping = true }

function Ui.fx(node: GuiObject?, only: string?): () -> ()
	local function noop() end
	if not node then
		return noop
	end
	local list = fxParams(node)
	if #list == 0 then
		return noop
	end
	local running = fxRunning[node] or {}
	fxRunning[node] = running
	local still = reducedMotion()
	local mine: { [string]: number } = {}
	local function alive(kind: string, token: number): boolean
		return running[kind] == token and node.Parent ~= nil
	end
	for _, e in list do
		local kind, v = e.kind, e.v
		if only and kind ~= only then
			continue
		end
		if reduceFlashing and FLASHING[kind] then
			continue -- (the player asked for no flashing)
		end
		local token = (running[kind] or 0) + 1
		running[kind] = token
		mine[kind] = token
		if kind == "shimmer" then
			local layer = node:FindFirstChild("Fx_Shimmer")
			local band = layer and layer:FindFirstChild("Band")
			if band and band:IsA("UIGradient") and not still then
				task.spawn(function()
					task.wait(v.delay or 0)
					while alive(kind, token) do
						band.Offset = Vector2.new(-1, 0)
						fxTween(band, (v.period or 2.6) * 0.45, { Offset = Vector2.new(1, 0) })
						task.wait(v.period or 2.6)
					end
				end)
			end
		elseif kind == "ping" then
			local layer = node:FindFirstChild("Fx_Ping")
			local grow = layer and layer:FindFirstChildOfClass("UIScale")
			if layer and grow and not still then
				task.spawn(function()
					task.wait(v.delay or 0)
					while alive(kind, token) do
						grow.Scale = 1
						fxAlpha(layer, 1 - (v.alpha or 0.6))
						local secs = (v.period or 1.6) * 0.6
						fxTween(grow, secs, { Scale = v.scale or 1.12 }, Enum.EasingStyle.Quad)
						local tProp = if layer:IsA("ImageLabel")
							then "ImageTransparency"
							elseif layer:IsA("TextLabel") then "TextTransparency"
							else "BackgroundTransparency"
						fxTween(layer, secs, { [tProp] = 1 }, Enum.EasingStyle.Quad)
						task.wait(v.period or 1.6)
					end
				end)
			end
		elseif kind == "burn_in" then
			local grad = node:FindFirstChild("Fx_Burn")
			local edge = node:FindFirstChild("Fx_BurnEdge")
			local band = edge and edge:FindFirstChild("Band")
			if grad and grad:IsA("UIGradient") then
				if still then
					grad.Offset = Vector2.new(1, 0)
					fxAlpha(edge, 1)
				else
					grad.Offset = Vector2.new(-1, 0)
					if band and band:IsA("UIGradient") then
						band.Offset = Vector2.new(-1, 0)
					end
					task.spawn(function()
						task.wait(v.delay or 0)
						if not alive(kind, token) then
							return
						end
						local dur = v.dur or 0.6
						fxAlpha(edge, 0)
						fxTween(grad, dur, { Offset = Vector2.new(1, 0) }, Enum.EasingStyle.Quad)
						if band then
							fxTween(band, dur, { Offset = Vector2.new(1, 0) }, Enum.EasingStyle.Quad)
						end
						task.wait(dur)
						if edge then
							fxTween(edge, 0.15, {
								[if edge:IsA("ImageLabel")
									then "ImageTransparency"
									elseif edge:IsA("TextLabel") then "TextTransparency"
									else "BackgroundTransparency"] = 1,
							})
						end
					end)
				end
			end
		elseif kind == "split" then
			local a, b = node:FindFirstChild("Fx_SplitA"), node:FindFirstChild("Fx_SplitB")
			if a and b and not still then
				task.spawn(function()
					while alive(kind, token) do
						task.wait((v.every or 3) * (0.7 + math.random() * 0.6))
						if not alive(kind, token) then
							break
						end
						if not fxShown(node) then
							continue -- (a closed screen or a hidden node: no burst, and nothing a fade could catch mid-way)
						end
						-- the piece's COPY on top of the two ghosts for the burst (synced first: a number or a flipbook
						-- may have changed since the screen was built); it covers the node exactly, so the node itself
						-- is never touched (a fade remembering its transparency mid-burst would keep it hidden)
						local c = node:FindFirstChild("Fx_SplitC")
						local own = fxAlpha(node)
						if c then
							if c:IsA("ImageLabel") and (node:IsA("ImageLabel") or node:IsA("ImageButton")) then
								c.Image = (node :: ImageLabel).Image
								c.ImageColor3 = (node :: ImageLabel).ImageColor3
							elseif c:IsA("TextLabel") and (node:IsA("TextLabel") or node:IsA("TextButton")) then
								c.Text = (node :: TextLabel).Text
								c.TextColor3 = (node :: TextLabel).TextColor3
							end
							fxAlpha(c, own)
						end
						local t0 = os.clock()
						while os.clock() - t0 < (v.dur or 0.14) do
							local px = v.px or 4
							local j = math.random(-1, 1);
							(a :: GuiObject).Position = UDim2.fromOffset(px + j, math.random(-1, 1));
							(b :: GuiObject).Position = UDim2.fromOffset(-px - j, math.random(-1, 1))
							fxAlpha(a, 1 - (v.alpha or 0.55))
							fxAlpha(b, 1 - (v.alpha or 0.55))
							task.wait(1 / 30)
						end
						fxAlpha(a, 1)
						fxAlpha(b, 1)
						if c then
							fxAlpha(c, 1)
						end
					end
				end)
			end
		elseif kind == "flicker" then
			-- the dips ride on a UIGradient of their own (it multiplies): the node's transparency is never written, so
			-- a fade that remembers it mid-dip cannot keep the node dimmed
			local grad = node:FindFirstChild("Fx_Flicker")
			if not still and grad and grad:IsA("UIGradient") then
				task.spawn(function()
					while alive(kind, token) do
						task.wait((v.every or 3.5) * (0.6 + math.random() * 0.8))
						if not alive(kind, token) then
							break
						end
						if not fxShown(node) then
							continue
						end
						local t0 = os.clock()
						while os.clock() - t0 < (v.dur or 0.35) do
							grad.Transparency = NumberSequence.new(if math.random() < 0.5 then v.depth or 0.4 else 0)
							task.wait(1 / 30)
						end
						grad.Transparency = NumberSequence.new(0)
					end
				end)
			end
		end
	end
	return function()
		for kind, token in mine do
			if running[kind] == token then
				running[kind] = nil
			end
		end
	end
end

-- UI SOUND (the compiler's "sounds": Kit_Snd_<moment> = an Sfx event): fired on the frame its moment lands — a hover,
-- a press, the ENTER when its motion settles (delay + 80% of its duration), a show when the node turns visible, a
-- state when Ui.setState sets it. Plays through ReplicatedStorage.kit.Sfx (the SFX lane's runtime); silent without it.
local sfxModule: any = nil
local function uiSound(gui: Instance, moment: string)
	local hap = gui:GetAttribute("Kit_Hap_" .. moment)
	if type(hap) == "string" and Ui.haptic then
		Ui.haptic(hap)
	end
	local event = gui:GetAttribute("Kit_Snd_" .. moment)
	if type(event) ~= "string" then
		return
	end
	if sfxModule == nil then
		local kit = ReplicatedStorage:FindFirstChild("kit")
		local m = kit and kit:FindFirstChild("Sfx")
		local ok, mod = pcall(function()
			return if m and m:IsA("ModuleScript") then require(m) :: any else false
		end)
		sfxModule = if ok then mod else false
	end
	if sfxModule and type(sfxModule.play) == "function" then
		pcall(sfxModule.play, event)
	end
end

local function bindSounds(gui: GuiObject)
	if gui:GetAttribute("Kit_Snd_hover") ~= nil or gui:GetAttribute("Kit_Hap_hover") ~= nil then
		gui.MouseEnter:Connect(function()
			uiSound(gui, "hover")
		end)
	end
	if
		(gui:GetAttribute("Kit_Snd_press") ~= nil or gui:GetAttribute("Kit_Hap_press") ~= nil) and gui:IsA("GuiButton")
	then
		(gui :: GuiButton).Activated:Connect(function()
			uiSound(gui, "press")
		end)
	end
	if gui:GetAttribute("Kit_Snd_show") ~= nil then
		gui:GetPropertyChangedSignal("Visible"):Connect(function()
			if gui.Visible then
				uiSound(gui, "show")
			end
		end)
	end
	if gui:GetAttribute("Kit_Snd_enter") ~= nil then
		local screen = gui:FindFirstAncestorWhichIsA("LayerCollector")
		local function landed()
			local d = num(gui, "Motion_enter_delay", 0) + 0.8 * num(gui, "Motion_enter_duration", 0)
			task.delay(d, uiSound, gui, "enter")
		end
		if screen then
			if screen.Enabled then
				landed()
			end
			screen:GetPropertyChangedSignal("Enabled"):Connect(function()
				if screen.Enabled then
					landed()
				end
			end)
		end
	end
end

-- HAPTICS + FUNNELS (v7.12): Ui.haptic("light" | "heavy") pulses a gamepad / phone motor (only where supported);
-- a spec's "haptic": {"press": "light", "selected": "heavy"} fires with the sound moments. Ui.funnel("Shop", 2) tells
-- the server (kit.UiAnalytics, validated + rate-limited) which step of a menu flow the player reached.
function Ui.haptic(kind: string?)
	local HapticService = game:GetService("HapticService")
	local strong = kind == "heavy"
	for _, input in { Enum.UserInputType.Gamepad1, Enum.UserInputType.Touch } do
		local ok, supported = pcall(HapticService.IsVibrationSupported, HapticService, input)
		if ok and supported then
			local motor = if strong then Enum.VibrationMotor.Large else Enum.VibrationMotor.Small
			local okM, has = pcall(HapticService.IsMotorSupported, HapticService, input, motor)
			if okM and has then
				pcall(HapticService.SetMotor, HapticService, input, motor, if strong then 0.8 else 0.35)
				task.delay(if strong then 0.12 else 0.05, function()
					pcall(HapticService.SetMotor, HapticService, input, motor, 0)
				end)
			end
		end
	end
end

function Ui.funnel(name: string, step: number)
	local remote = ReplicatedStorage:FindFirstChild("KitUiFunnel")
	if remote and remote:IsA("RemoteEvent") then
		remote:FireServer(name, step)
	end
end

-- control STATES (the compiler's "states" key: Kit_States + Kit_S_<state> = "prop=value;..."): Ui.setState(node,
-- "disabled") moves the control to that state's look (colours and alphas tween, a picture or a text swaps), nil goes
-- back to idle. selected / disabled / locked / new are STICKY: hover and pressed (wired by Ui.bind) wait under them;
-- disabled and locked also stop the button (Interactable). Ui.getState(node) -> the sticky state or nil.
local stateBase: { [Instance]: { [string]: any } } = setmetatable({}, { __mode = "k" }) :: any
local stateSticky: { [Instance]: string } = setmetatable({}, { __mode = "k" }) :: any
local STICKY = { selected = true, disabled = true, locked = true, new = true }

local function stateOverrides(node: Instance, state: string?): { [string]: string }
	local out = {}
	if not state then
		return out
	end
	for pair in string.gmatch(tostring(node:GetAttribute("Kit_S_" .. state) or ""), "[^;]+") do
		local k, v = string.match(pair, "^([%w_]+)=(.*)$")
		if k and v then
			out[k] = v
		end
	end
	return out
end

local function hexColor(s: string): Color3?
	local r, g, b = string.match(s, "^#(%x%x)(%x%x)(%x%x)$")
	if not r then
		return nil
	end
	return Color3.fromRGB(tonumber(r, 16) :: number, tonumber(g, 16) :: number, tonumber(b, 16) :: number)
end

local stateText: { [Instance]: boolean } = setmetatable({}, { __mode = "k" }) :: any

-- the control's parts a state changes: its picture (a plate-backed control's Plate) and its words (its Label)
local function stateParts(node: GuiObject): (GuiObject, GuiObject)
	-- a plate-backed control's picture is its Plate child: imageColor / imageAlpha / image go there
	local pic: GuiObject = node
	if not (node:IsA("ImageLabel") or node:IsA("ImageButton")) then
		local plate = node:FindFirstChild("Plate")
		if plate and plate:IsA("ImageLabel") then
			pic = plate
		end
	end
	-- ...and its words are its Label child (the button's own Text is empty)
	local words: GuiObject = node
	if
		(node:IsA("TextButton") or node:IsA("ImageButton"))
		and (not node:IsA("TextButton") or (node :: TextButton).Text == "")
	then
		local label = node:FindFirstChild("Label")
		if label and label:IsA("TextLabel") then
			words = label
		end
	end
	return pic, words
end

-- the IDLE look, taken once — at bind (Ui.bind runs before any enter fades the screen in), so a state set while the
-- screen is still invisible never records "invisible" as idle
local function stateSnapshot(node: GuiObject): { [string]: any }
	local pic, words = stateParts(node)
	local base: { [string]: any } = stateBase[node] or {}
	if next(base) == nil then
		base = { BackgroundColor3 = node.BackgroundColor3, BackgroundTransparency = node.BackgroundTransparency }
		if words:IsA("TextLabel") or words:IsA("TextButton") then
			local tl = words :: TextLabel
			base.TextColor3, base.TextTransparency, base.Text = tl.TextColor3, tl.TextTransparency, tl.Text
		end
		if pic:IsA("ImageLabel") or pic:IsA("ImageButton") then
			local im = pic :: ImageLabel
			base.ImageColor3, base.ImageTransparency, base.Image = im.ImageColor3, im.ImageTransparency, im.Image
		end
		local stroke = node:FindFirstChildOfClass("UIStroke")
		if stroke then
			base.StrokeColor = stroke.Color
		end
		stateBase[node] = base
	end
	return base
end

local function applyState(node: GuiObject, state: string?)
	local pic, words = stateParts(node)
	local base = stateSnapshot(node)
	local o = stateOverrides(node, state)
	local goal: { [string]: any } =
		{ BackgroundColor3 = base.BackgroundColor3, BackgroundTransparency = base.BackgroundTransparency }
	if o.color then
		goal.BackgroundColor3 = hexColor(o.color) or goal.BackgroundColor3
	end
	if o.transparency then
		goal.BackgroundTransparency = tonumber(o.transparency) or goal.BackgroundTransparency
	end
	local wordGoal: { [string]: any } = {}
	if base.TextColor3 ~= nil then
		wordGoal.TextColor3 = if o.textColor then hexColor(o.textColor) or base.TextColor3 else base.TextColor3
		wordGoal.TextTransparency = if o.textAlpha
			then tonumber(o.textAlpha) or base.TextTransparency
			else base.TextTransparency
		-- the words: a state's text replaces them, leaving it puts back the words that were there (game code may
		-- have changed them since bind: "Buy 250"), never the bind-time text
		local tl = words :: TextLabel
		if o.text then
			if not stateText[node] then
				base.Text = tl.Text
			end
			tl.Text = o.text
			stateText[node] = true
		elseif stateText[node] then
			tl.Text = base.Text
			stateText[node] = nil
		end
	end
	local picGoal: { [string]: any } = {}
	if base.ImageColor3 ~= nil then
		picGoal.ImageColor3 = if o.imageColor then hexColor(o.imageColor) or base.ImageColor3 else base.ImageColor3
		picGoal.ImageTransparency = if o.imageAlpha
			then tonumber(o.imageAlpha) or base.ImageTransparency
			else base.ImageTransparency;
		(pic :: ImageLabel).Image = if o.image and o.image ~= "" then o.image else base.Image
	end
	local secs = if reducedMotion() then 0 else 0.12
	local stateInfo = TweenInfo.new(secs, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)
	for target, g in { [pic] = picGoal, [words] = wordGoal } do
		if target == node then
			for k, v in g do
				goal[k] = v
			end
		elseif next(g) then
			TweenService:Create(target, stateInfo, g):Play()
		end
	end
	TweenService:Create(node, stateInfo, goal):Play()
	local stroke = node:FindFirstChildOfClass("UIStroke")
	if stroke and base.StrokeColor then
		local sc = if o.strokeColor then hexColor(o.strokeColor) or base.StrokeColor else base.StrokeColor
		TweenService:Create(stroke, TweenInfo.new(secs), { Color = sc }):Play()
	end
	if node:IsA("GuiButton") then
		local blocked = state == "disabled" or state == "locked"
		pcall(function()
			(node :: any).Interactable = not blocked
		end)
		node.AutoButtonColor = false
	end
end

function Ui.setState(node: GuiObject?, state: string?)
	if not node then
		return
	end
	if state ~= nil and node:GetAttribute("Kit_S_" .. state) == nil then
		warn(`Ui.setState: {node:GetFullName()} has no "{state}" state (its spec's "states")`)
		return
	end
	if state == nil or STICKY[state] then
		stateSticky[node] = state :: any
	end
	applyState(node, state)
	if state then
		uiSound(node, state) -- (its state's sound, as it lands)
	end
end

function Ui.getState(node: GuiObject?): string?
	return node and stateSticky[node] or nil
end

-- hover / pressed under the sticky state (Ui.bind wires them for a control that has them)
local function bindStates(gui: GuiObject)
	stateSnapshot(gui) -- (idle as designed, before any enter)
	local list = tostring(gui:GetAttribute("Kit_States") or "")
	local function has(s: string): boolean
		return string.find("," .. list .. ",", "," .. s .. ",", 1, true) ~= nil
	end
	local function rest()
		applyState(gui, stateSticky[gui])
	end
	if has("hover") then
		gui.MouseEnter:Connect(function()
			if not stateSticky[gui] then
				applyState(gui, "hover")
			end
		end)
		gui.MouseLeave:Connect(rest)
	end
	if has("pressed") and gui:IsA("GuiButton") then
		gui.MouseButton1Down:Connect(function()
			if not stateSticky[gui] then
				applyState(gui, "pressed")
			end
		end)
		gui.MouseButton1Up:Connect(function()
			if not stateSticky[gui] then
				applyState(gui, if has("hover") then "hover" else nil)
			end
		end)
		if not has("hover") then
			gui.MouseLeave:Connect(rest) -- (press, drag off, release elsewhere: pressed must not stick)
		end
	end
end

-- GAMEPAD / CONSOLE for a kit screen (the compiler's nav, glyph, firstFocus and focus piece): every button wears the
-- identity's focus piece as its SelectionImageObject (not the engine's blue box), "nav" overrides become the d-pad
-- neighbours, key hints swap their keycap for the pad button's picture while a pad is in use (and hide on touch),
-- and when the screen is enabled with a pad the selection lands on firstFocus. UiMotion calls it for every screen.
local UserInputService = game:GetService("UserInputService")
local padScreens: { [ScreenGui]: boolean } = setmetatable({}, { __mode = "k" }) :: any

local function padActive(): boolean
	local last = UserInputService:GetLastInputType()
	return string.sub(last.Name, 1, 7) == "Gamepad"
end

local function touchActive(): boolean
	return UserInputService:GetLastInputType() == Enum.UserInputType.Touch
end

local function byPath(screen: ScreenGui, path: string): Instance?
	local at: Instance? = screen
	for part in string.gmatch(path, "[^%.]+") do
		at = at and at:FindFirstChild(part)
	end
	return at
end

local function glyphs(screen: ScreenGui)
	local pad, touch = padActive(), touchActive()
	for _, d in screen:GetDescendants() do
		local key = d:GetAttribute("Kit_GlyphPad")
		if type(key) ~= "string" or not d:IsA("GuiObject") then
			continue
		end
		local hint = d :: GuiObject
		local img = if hint:IsA("ImageLabel") then hint else hint:FindFirstChild("Key")
		if img and img:IsA("ImageLabel") then
			local cap = img :: ImageLabel
			if cap:GetAttribute("Kit_GlyphCap") == nil then
				cap:SetAttribute("Kit_GlyphCap", cap.Image) -- (the keycap as designed, restored off the pad)
				cap:SetAttribute("Kit_GlyphCapColor", cap.ImageColor3)
			end
			local text = cap:FindFirstChild("KeyText")
			local code = (Enum.KeyCode :: any)[key]
			local padImage = if pad and code then UserInputService:GetImageForKeyCode(code) else ""
			if pad and padImage ~= "" then
				cap.Image = padImage
				cap.ImageColor3 = Color3.new(1, 1, 1)
				if text and text:IsA("GuiObject") then
					text.Visible = false
				end
			else
				cap.Image = tostring(cap:GetAttribute("Kit_GlyphCap") or cap.Image)
				local tint = cap:GetAttribute("Kit_GlyphCapColor")
				if typeof(tint) == "Color3" then
					cap.ImageColor3 = tint
				end
				if text and text:IsA("GuiObject") then
					text.Visible = true
				end
			end
		end
		-- on touch a "hide" hint goes away; off touch it comes back only if WE hid it (a hint the game hid stays hidden)
		if touch and hint:GetAttribute("Kit_GlyphTouch") == "hide" then
			if hint.Visible then
				hint:SetAttribute("Kit_GlyphHidden", true)
				hint.Visible = false
			end
		elseif hint:GetAttribute("Kit_GlyphHidden") then
			hint:SetAttribute("Kit_GlyphHidden", nil)
			hint.Visible = true
		end
	end
end

function Ui.gamepad(screen: ScreenGui)
	if padScreens[screen] then
		return
	end
	padScreens[screen] = true
	-- the identity's focus piece as every button's selection
	local art = screen:GetAttribute("Kit_FocusArt")
	local piece: ImageLabel? = nil
	if type(art) == "string" and art ~= "" then
		local p = Instance.new("ImageLabel")
		p.Name = "KitFocus"
		p.BackgroundTransparency = 1
		p.Image = art
		p.Size = UDim2.new(1, 14, 1, 14)
		p.Position = UDim2.fromOffset(-7, -7)
		local sl = tostring(screen:GetAttribute("Kit_FocusSlice") or "")
		local a, b, c, d = string.match(sl, "^(%-?%d+),(%-?%d+),(%-?%d+),(%-?%d+)$")
		if a then
			p.ScaleType = Enum.ScaleType.Slice
			p.SliceCenter =
				Rect.new(tonumber(a) :: number, tonumber(b) :: number, tonumber(c) :: number, tonumber(d) :: number)
		end
		piece = p
	end
	for _, d in screen:GetDescendants() do
		if d:IsA("GuiButton") and piece then
			d.SelectionImageObject = piece
		end
		if d:IsA("GuiObject") then
			for _, dir in { "Up", "Down", "Left", "Right" } do
				local to = d:GetAttribute("Kit_Nav" .. dir)
				local target = type(to) == "string" and byPath(screen, to) or nil
				if target and target:IsA("GuiObject") then
					(d :: any)["NextSelection" .. dir] = target
				end
			end
		end
	end
	if piece then
		screen.DescendantAdded:Connect(function(d)
			if d:IsA("GuiButton") then
				d.SelectionImageObject = piece -- (a button the game adds later wears the focus piece too)
			end
		end)
	end
	local function land()
		local first = screen:GetAttribute("Kit_FirstFocus")
		local target = type(first) == "string" and byPath(screen, first) or nil
		if screen.Enabled and padActive() and target and target:IsA("GuiObject") and target.Visible then
			GuiService.SelectedObject = target
		end
	end
	glyphs(screen)
	land()
	screen:GetPropertyChangedSignal("Enabled"):Connect(land)
	local changed = UserInputService.LastInputTypeChanged:Connect(function()
		glyphs(screen)
		if padActive() and GuiService.SelectedObject == nil then
			land()
		end
	end)
	screen.Destroying:Once(function()
		changed:Disconnect()
	end)
end

-- VECTOR lines (the compiler's "path" node: Kit_Path = "x,y;..." as shares of the node's box + Kit_Path*): Ui.path
-- builds the node's Path2D (its control points are set by method; a smooth path is sampled as a Catmull-Rom curve,
-- like the preview draws it) and Ui.path(node, 0.4) shows the first 40% of its length — the draw-on a "draw" key
-- plays when the screen is bound (instant under reduced motion).
local function pathPoints(node: Instance): { Vector2 }
	local pts: { Vector2 } = {}
	for x, y in string.gmatch(tostring(node:GetAttribute("Kit_Path") or ""), "(%-?[%d%.]+),(%-?[%d%.]+)") do
		table.insert(pts, Vector2.new(tonumber(x) :: number, tonumber(y) :: number))
	end
	if node:GetAttribute("Kit_PathSmooth") ~= false and #pts >= 3 then
		local dense: { Vector2 } = {}
		for i = 1, #pts - 1 do
			local p0, p1, p2, p3 = pts[math.max(1, i - 1)], pts[i], pts[i + 1], pts[math.min(#pts, i + 2)]
			for s = 0, 11 do
				local t = s / 12
				local t2, t3 = t * t, t * t * t
				table.insert(
					dense,
					(p1 * 2 + (p2 - p0) * t + (p0 * 2 - p1 * 5 + p2 * 4 - p3) * t2 + (p1 * 3 - p0 - p2 * 3 + p3) * t3)
						* 0.5
				)
			end
		end
		table.insert(dense, pts[#pts])
		return dense
	end
	return pts
end

function Ui.path(node: GuiObject?, share: number?)
	if not node or node:GetAttribute("Kit_Path") == nil then
		return
	end
	local pts = pathPoints(node)
	if #pts < 2 then
		return
	end
	-- an outline first (under the line): a darker, wider copy of the same stroke
	local oc, opx = string.match(tostring(node:GetAttribute("Kit_PathOutline") or ""), "^(#%x+),([%d%.]+)$")
	local under = node:FindFirstChild("KitPathOutline") :: Path2D?
	if oc and not under then
		local made = Instance.new("Path2D")
		made.Name = "KitPathOutline"
		made.Parent = node
		under = made
	end
	local p2 = node:FindFirstChild("KitPath") :: Path2D?
	if not p2 then
		local made = Instance.new("Path2D")
		made.Name = "KitPath"
		made.Parent = node
		p2 = made
	end
	local line = p2 :: Path2D
	local hex = tostring(node:GetAttribute("Kit_PathColor") or "#ffffff")
	local r, g, b = string.match(hex, "^#(%x%x)(%x%x)(%x%x)$")
	if r then
		line.Color3 = Color3.fromRGB(tonumber(r, 16) :: number, tonumber(g, 16) :: number, tonumber(b, 16) :: number)
	end
	line.Thickness = num(node, "Kit_PathThickness", 4)
	line.ZIndex = node.ZIndex
	local k = math.clamp(share or 1, 0, 1)
	-- the first k of the length: whole segments, then the last one cut where the share ends
	local total = 0
	for i = 2, #pts do
		total += (pts[i] - pts[i - 1]).Magnitude
	end
	local want, run = total * k, 0
	local shown: { Vector2 } = { pts[1] }
	for i = 2, #pts do
		local seg = (pts[i] - pts[i - 1]).Magnitude
		if run + seg >= want then
			local f = if seg > 0 then (want - run) / seg else 0
			table.insert(shown, pts[i - 1]:Lerp(pts[i], f))
			break
		end
		run += seg
		table.insert(shown, pts[i])
	end
	local controls = {}
	for _, p in shown do
		table.insert(controls, Path2DControlPoint.new(UDim2.fromScale(p.X, p.Y)))
	end
	line.Closed = k >= 1 and node:GetAttribute("Kit_PathClosed") == true
	line:SetControlPoints(controls)
	if under and oc then
		local ur, ug, ub = string.match(oc, "^#(%x%x)(%x%x)(%x%x)$")
		if ur then
			under.Color3 =
				Color3.fromRGB(tonumber(ur, 16) :: number, tonumber(ug, 16) :: number, tonumber(ub, 16) :: number)
		end
		under.Thickness = line.Thickness + 2 * (tonumber(opx) or 2)
		under.ZIndex = node.ZIndex
		line.ZIndex = node.ZIndex + 1 -- (the line over its outline)
		under.Closed = line.Closed
		under:SetControlPoints(controls)
	end
end

-- runs fn every time the node's screen OPENS (Enabled) while the node shows, and when the node turns visible: a
-- moment the player must SEE (a burn-in, a draw-on, a burst) plays then, not at bind while the screen is still shut
local function onOpen(gui: GuiObject, fn: () -> ())
	local screen = gui:FindFirstAncestorWhichIsA("LayerCollector")
	if screen then
		screen:GetPropertyChangedSignal("Enabled"):Connect(function()
			if screen.Enabled and gui.Visible then
				fn()
			end
		end)
	end
	gui:GetPropertyChangedSignal("Visible"):Connect(function()
		if gui.Visible and (screen == nil or screen.Enabled) then
			fn()
		end
	end)
end

local function bindPath(gui: GuiObject)
	local draw = tostring(gui:GetAttribute("Kit_PathDraw") or "")
	local dur, delay = string.match(draw, "^([%d%.]+),([%d%.]+)$")
	if not dur or reducedMotion() then
		Ui.path(gui, 1)
		return
	end
	local d, w = tonumber(dur) :: number, tonumber(delay) :: number
	local playing = 0
	local function play()
		playing += 1
		local me = playing
		Ui.path(gui, 0)
		task.spawn(function()
			task.wait(w)
			local t0 = os.clock()
			while gui.Parent and playing == me do
				local k = math.clamp((os.clock() - t0) / d, 0, 1)
				Ui.path(gui, 1 - (1 - k) * (1 - k)) -- (quad out: the stroke races in and settles)
				if k >= 1 then
					break
				end
				RunService.Heartbeat:Wait()
			end
		end)
	end
	if fxShown(gui) then
		play()
	else
		Ui.path(gui, 0) -- (shut: drawn when it opens)
	end
	onOpen(gui, play)
end

-- UI PARTICLES (the compiler's burst presets: the screen's Kit_Burst_<name> = "sprite=..;count=..;..."): Ui.burst(node,
-- "smash") flies pooled sprites out of the node's centre — each with its own angle in the spread, speed, size, colour
-- and spin, falling by gravity, fading and shrinking over its life (the reel draws the same flight: kit/ui/reel.py
-- burst_frame). A node's "burst" key fires it when the node shows. Off under reduced motion (pure decoration).
local burstPools: { [LayerCollector]: { ImageLabel } } = setmetatable({}, { __mode = "k" }) :: any

local function burstPreset(screen: LayerCollector, name: string): { [string]: string }?
	local raw = screen:GetAttribute("Kit_Burst_" .. name)
	if type(raw) ~= "string" then
		return nil
	end
	local out = {}
	for pair in string.gmatch(raw, "[^;]+") do
		local k, v = string.match(pair, "^([%w_]+)=(.*)$")
		if k and v then
			out[k] = v
		end
	end
	return out
end

local function pairOf(s: string?, a: number, b: number): (number, number)
	local x, y = string.match(s or "", "^(%-?[%d%.]+),(%-?[%d%.]+)$")
	return tonumber(x) or a, tonumber(y) or b
end

function Ui.burst(node: GuiObject?, preset: string?)
	if not node or reducedMotion() then
		return
	end
	local screen = node:FindFirstAncestorWhichIsA("LayerCollector") -- (a screen, or a world billboard / surface)
	local name = preset or tostring(node:GetAttribute("Kit_BurstPreset") or "")
	local p = screen and burstPreset(screen, name)
	if not (screen and p) then
		warn(`Ui.burst: no burst preset "{name}" on {node:GetFullName()} (the identity's or the screen's "bursts")`)
		return
	end
	local layer = screen:FindFirstChild("KitBursts") :: Frame?
	if not layer then
		local made = Instance.new("Frame")
		made.Name = "KitBursts"
		made.BackgroundTransparency = 1
		made.Size = UDim2.fromScale(1, 1)
		made.ZIndex = 100
		made.Parent = screen
		layer = made
	end
	local host = layer :: Frame
	local pool = burstPools[screen] or {}
	burstPools[screen] = pool
	local count = math.floor(tonumber(p.count) or 14)
	local life = tonumber(p.life) or 0.6
	local s0, s1 = pairOf(p.speed, 220, 520)
	local z0, z1 = pairOf(p.size, 12, 30)
	local spread, angle = tonumber(p.spread) or 360, tonumber(p.angle) or -90
	local gravity, spin = tonumber(p.gravity) or 900, tonumber(p.spin) or 180
	local fade, shrink = p.fade ~= "0", p.shrink ~= "0"
	local colors: { Color3 } = {}
	for hex in string.gmatch(p.colors or "", "#%x%x%x%x%x%x") do
		table.insert(colors, Color3.fromHex(hex))
	end
	if #colors == 0 then
		colors = { Color3.new(1, 1, 1) }
	end
	local origin = node.AbsolutePosition + node.AbsoluteSize / 2 - host.AbsolutePosition
	local parts = {}
	for _ = 1, count do
		local img = table.remove(pool)
		if not img then
			local made = Instance.new("ImageLabel")
			made.BackgroundTransparency = 1
			made.AnchorPoint = Vector2.new(0.5, 0.5)
			made.ZIndex = 100
			img = made
		end
		local im = img :: ImageLabel
		im.Image = p.sprite or ""
		im.ImageColor3 = colors[math.random(1, #colors)]
		im.ImageTransparency = 0
		im.Visible = true
		im.Parent = host
		local a = math.rad(angle + spread * (math.random() - 0.5))
		local spd = s0 + (s1 - s0) * math.random()
		table.insert(parts, {
			img = im,
			v = Vector2.new(math.cos(a), math.sin(a)) * spd,
			size = z0 + (z1 - z0) * math.random(),
			rot = math.random() * 360,
			spin = spin * (math.random() * 2 - 1),
		})
	end
	local t0 = os.clock()
	local conn: RBXScriptConnection
	conn = RunService.Heartbeat:Connect(function()
		local t = os.clock() - t0
		local k = math.clamp(t / life, 0, 1)
		for _, q in parts do
			local pos = origin + q.v * t + Vector2.new(0, 0.5 * gravity * t * t)
			local sz = q.size * (if shrink then 1 - 0.7 * k else 1)
			q.img.Position = UDim2.fromOffset(pos.X, pos.Y)
			q.img.Size = UDim2.fromOffset(sz, sz)
			q.img.Rotation = q.rot + q.spin * t
			q.img.ImageTransparency = if fade then k else 0
		end
		if k >= 1 then
			conn:Disconnect()
			for _, q in parts do
				q.img.Visible = false
				table.insert(pool, q.img)
			end
		end
	end)
end

local function bindBurst(gui: GuiObject)
	if gui:GetAttribute("Kit_BurstOn") ~= "show" then
		return
	end
	local function fire()
		local d = num(gui, "Kit_BurstDelay", 0)
		task.delay(d, function()
			if gui.Visible then
				Ui.burst(gui)
			end
		end)
	end
	if fxShown(gui) then
		fire()
	end
	onOpen(gui, fire)
end

-- WORLD-SPACE UI (a spec's "space": "world": the compiled template is a BillboardGui or a SurfaceGui in StarterGui):
-- Ui.attach(template, part) mounts a copy over / on a part (its motion bound like a screen's; a billboard with a
-- "distance" key shrinks between near and far), Ui.floater(template, position, text) flies a damage number / a
-- pickup word up from a point and clears it. Both return the mounted copy.
local function liveCopy(template: Instance): LayerCollector?
	local name = template.Name
	local gui = Players.LocalPlayer and Players.LocalPlayer:FindFirstChildOfClass("PlayerGui")
	local src = template
	-- (StarterGui's template has been copied into PlayerGui by the engine: clone that one, it is the same)
	if gui and gui:FindFirstChild(name) and gui:FindFirstChild(name) ~= template then
		src = gui:FindFirstChild(name) :: Instance
	end
	local copy = src:Clone()
	if not copy:IsA("LayerCollector") then
		copy:Destroy()
		return nil
	end
	return copy :: LayerCollector
end

function Ui.attach(template: Instance?, adornee: Instance?): LayerCollector?
	if not template or not adornee then
		return nil
	end
	local copy = liveCopy(template)
	if not copy then
		warn(`Ui.attach: {template:GetFullName()} is not a world screen (a spec with "space": "world")`)
		return nil
	end
	local gui = Players.LocalPlayer and Players.LocalPlayer:FindFirstChildOfClass("PlayerGui");
	(copy :: any).Adornee = adornee
	copy.Enabled = true
	copy.Parent = gui or adornee
	for _, d in copy:GetDescendants() do
		Ui.bind(d)
	end
	local near, far, low =
		copy:GetAttribute("Kit_DistNear"), copy:GetAttribute("Kit_DistFar"), copy:GetAttribute("Kit_DistMin")
	local root = copy:FindFirstChildWhichIsA("GuiObject")
	if type(near) == "number" and type(far) == "number" and type(low) == "number" and root then
		local s = root:FindFirstChild("KitDistance") :: UIScale?
		if not s then
			local made = Instance.new("UIScale")
			made.Name = "KitDistance"
			made.Parent = root
			s = made
		end
		local sc = s :: UIScale
		local conn
		conn = RunService.RenderStepped:Connect(function()
			if not copy.Parent then
				conn:Disconnect()
				return
			end
			local cam = workspace.CurrentCamera
			local at: Vector3? = if adornee:IsA("BasePart")
				then adornee.Position
				elseif adornee:IsA("Attachment") then adornee.WorldPosition
				elseif adornee:IsA("Model") then adornee:GetPivot().Position
				else nil
			if cam and at then
				local k = math.clamp(((cam.CFrame.Position - at).Magnitude - near) / (far - near), 0, 1)
				sc.Scale = 1 - (1 - low) * k
			end
		end)
	end
	return copy
end

function Ui.floater(template: Instance?, at: Vector3, text: string?, rise: number?, life: number?): LayerCollector?
	if not template then
		return nil
	end
	local anchor = Instance.new("Attachment")
	anchor.Name = "KitFloater"
	anchor.WorldPosition = at
	anchor.Parent = workspace.Terrain
	local copy = Ui.attach(template, anchor)
	if not copy then
		anchor:Destroy()
		return nil
	end
	if text ~= nil then
		local value = copy:FindFirstChild("Value", true)
		if not (value and value:IsA("TextLabel")) then
			value = copy:FindFirstChildWhichIsA("TextLabel", true)
		end
		if value and value:IsA("TextLabel") then
			value.Text = text
		end
	end
	local secs = life or 0.9
	if copy:IsA("BillboardGui") and not reducedMotion() then
		local up = copy.StudsOffset + Vector3.new(0, rise or 2.5, 0)
		TweenService:Create(copy, TweenInfo.new(secs, Enum.EasingStyle.Quad, Enum.EasingDirection.Out), {
			StudsOffset = up,
		}):Play()
	end
	task.delay(secs * 0.55, function()
		for _, d in copy:GetDescendants() do
			if d:IsA("TextLabel") then
				TweenService:Create(d, TweenInfo.new(secs * 0.45), { TextTransparency = 1, TextStrokeTransparency = 1 })
					:Play()
			elseif d:IsA("ImageLabel") then
				TweenService:Create(d, TweenInfo.new(secs * 0.45), { ImageTransparency = 1 }):Play()
			elseif d:IsA("UIStroke") then
				TweenService:Create(d, TweenInfo.new(secs * 0.45), { Transparency = 1 }):Play()
			end
		end
	end)
	task.delay(secs + 0.05, function()
		copy:Destroy()
		anchor:Destroy()
	end)
	return copy
end

-- STYLESHEETS (kit ui style <identity> -> src/ui/styles/<identity>.model.json: the identity's tokens as attributes +
-- StyleRules): a rule's properties and transition are set by method, so they ride in Kit_Props / Kit_Transition and
-- Ui.styles() applies them once. Ui.link(gui, "sim") makes a HAND-MADE ScreenGui wear the identity (its pieces tagged
-- KitTitle / KitPanel / KitPrimary / KitMuted get those rules). Values: "$token" (a sheet attribute), numbers, booleans,
-- {"Enum": "Font", "Name": ...}, {"UDim": [scale, offset]}.
local HttpService = game:GetService("HttpService")
local styled: { [Instance]: boolean } = setmetatable({}, { __mode = "k" }) :: any

local function styleSheets(): { Instance }
	local out = {}
	local roots: { Instance? } = {
		Players.LocalPlayer and Players.LocalPlayer:FindFirstChildOfClass("PlayerGui"),
		game:GetService("StarterGui"),
		ReplicatedStorage,
	}
	for _, root in roots do
		if root then
			for _, d in root:GetDescendants() do
				if d.ClassName == "StyleSheet" and d:GetAttribute("Kit_Style") ~= nil then
					table.insert(out, d)
				end
			end
		end
	end
	return out
end

local function styleValue(v: any): any
	if type(v) == "table" then
		if v.Enum and v.Name then
			local ok, item = pcall(function()
				return (Enum :: any)[v.Enum][v.Name]
			end)
			return if ok then item else nil
		elseif v.UDim then
			return UDim.new(v.UDim[1] or 0, v.UDim[2] or 0)
		end
		return nil
	end
	return v
end

-- a StyleQuery's conditions ride in Kit_Conditions (kit ui style writes them; the engine sets them by method)
local function applyConditions(q: Instance)
	local rawC = q:GetAttribute("Kit_Conditions")
	local okC, cond = pcall(HttpService.JSONDecode, HttpService, tostring(rawC or ""))
	if okC and type(cond) == "table" then
		local set: { [string]: any } = {}
		for k, v in cond do
			if (k == "MinSize" or k == "MaxSize") and type(v) == "table" then
				set[k] = Vector2.new(tonumber(v[1]) or 0, tonumber(v[2]) or 0)
			elseif k == "AspectRatioRange" and type(v) == "table" then
				set[k] = NumberRange.new(tonumber(v[1]) or 0, tonumber(v[2]) or 0)
			elseif k == "PreferredInput" and type(v) == "string" then
				local okE, item = pcall(function()
					return (Enum :: any).PreferredInput[v]
				end)
				set[k] = if okE then item else nil
			end
		end
		pcall(function()
			(q :: any):SetConditions(set)
		end)
	end
end

function Ui.styles()
	for _, sheet in styleSheets() do
		if styled[sheet] then
			continue
		end
		styled[sheet] = true
		-- breakpoints (v7, kit ui style "queries"): the sheet's own copies get their conditions too (Ui.link places a
		-- copy of each under the root it links: only there does the engine evaluate it - UiStyleRules)
		for _, q in sheet:GetChildren() do
			if q.ClassName == "StyleQuery" then
				applyConditions(q)
			end
		end
		-- every rule, the ones nested under a "@Query" rule too
		for _, rule in sheet:GetDescendants() do
			if rule.ClassName ~= "StyleRule" then
				continue
			end
			-- under "@Query" a bare selector reaches nothing (the query selects the styled root): ">> <selector>"
			local parent = rule.Parent
			if parent and parent.ClassName == "StyleRule" then
				pcall(function()
					local r = rule :: any
					r.Selector = UiStyleRules.scoped((parent :: any).Selector, r.Selector)
				end)
			end
			local raw = rule:GetAttribute("Kit_Props")
			if type(raw) == "string" then
				local ok, props = pcall(HttpService.JSONDecode, HttpService, raw)
				if ok and type(props) == "table" then
					local clean = {}
					for k, v in props do
						clean[k] = styleValue(v)
					end
					pcall(function()
						(rule :: any):SetProperties(clean)
					end)
				end
			end
			local tr = rule:GetAttribute("Kit_Transition")
			local secs, style, dir = string.match(tostring(tr or ""), "^([%d%.]+),(%a+),(%a+)$")
			if secs then
				local okE, es = pcall(function()
					return (Enum.EasingStyle :: any)[style]
				end)
				local okD, ed = pcall(function()
					return (Enum.EasingDirection :: any)[dir]
				end)
				local transition = TweenInfo.new(
					tonumber(secs) :: number,
					if okE and es then es else Enum.EasingStyle.Quad,
					if okD and ed then ed else Enum.EasingDirection.Out
				)
				pcall(function()
					(rule :: any):SetDefaultPropertyTransition(transition)
				end)
			end
		end
	end
end

function Ui.link(gui: Instance?, identity: string): Instance?
	if not gui then
		return nil
	end
	Ui.styles()
	for _, sheet in styleSheets() do
		if sheet:GetAttribute("Kit_Style") == identity then
			local link: any = gui:FindFirstChild("KitStyle") or Instance.new("StyleLink")
			link.Name = "KitStyle"
			(link :: any).StyleSheet = sheet
			link.Parent = gui
			-- each breakpoint query is evaluated only UNDER the styled root (measured 2026-11-20, card 7bgq): a copy of
			-- it goes there, named as its "@Name" rule selects it
			local kids, has = {}, {}
			for _, c in sheet:GetChildren() do
				table.insert(kids, { className = c.ClassName, name = c.Name })
			end
			for _, c in gui:GetChildren() do
				has[c.Name] = true
			end
			for _, qname in UiStyleRules.queriesToPlace(kids, has) do
				local q = sheet:FindFirstChild(qname)
				if q then
					local copy = q:Clone()
					copy:SetAttribute("Kit_QueryOf", sheet:GetFullName())
					applyConditions(copy)
					copy.Parent = gui
				end
			end
			return link
		end
	end
	warn(`Ui.link: no StyleSheet for "{identity}" (lune run kit ui style {identity})`)
	return nil
end

-- MENU BACKDROPS (the compiler's "backdrop": Kit_Backdrop on the screen): while a menu is open the world behind it
-- blurs, darkens and loses colour (Lighting BlurEffect + ColorCorrectionEffect, tweened); closing tweens it back. With
-- several menus open the strongest wins; the last one closing clears it. UiMotion calls it on Enabled changes.
local backdropOpen: { [Instance]: { blur: number, darken: number, sat: number, sec: number } } = {}

local function backdropApply(sec: number)
	local Lighting = game:GetService("Lighting")
	local blur, darken, sat = 0, 0, 0
	for screen, b in backdropOpen do
		if screen.Parent == nil then
			backdropOpen[screen] = nil
		else
			blur, darken, sat = math.max(blur, b.blur), math.max(darken, b.darken), math.min(sat, b.sat)
		end
	end
	local fx = Lighting:FindFirstChild("KitBackdropBlur") :: BlurEffect?
	local cc = Lighting:FindFirstChild("KitBackdropGrade") :: ColorCorrectionEffect?
	if not fx then
		local made = Instance.new("BlurEffect")
		made.Name = "KitBackdropBlur"
		made.Size = 0
		made.Parent = Lighting
		fx = made
	end
	if not cc then
		local made = Instance.new("ColorCorrectionEffect")
		made.Name = "KitBackdropGrade"
		made.Parent = Lighting
		cc = made
	end
	local secs = if reducedMotion() then 0 else sec
	local tween = TweenInfo.new(secs, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)
	TweenService:Create(fx :: BlurEffect, tween, { Size = blur }):Play()
	TweenService:Create(cc :: ColorCorrectionEffect, tween, { Brightness = -darken, Saturation = sat }):Play()
end

function Ui.backdrop(screen: Instance?, open: boolean)
	if not screen then
		return
	end
	local raw = tostring(screen:GetAttribute("Kit_Backdrop") or "")
	if raw == "" then
		return
	end
	local v: { [string]: number } = {}
	for k, x in string.gmatch(raw, "(%a+)=([%-%d%.]+)") do
		v[k] = tonumber(x) :: number
	end
	if open then
		backdropOpen[screen] =
			{ blur = v.blur or 18, darken = v.darken or 0.35, sat = v.sat or -0.4, sec = v.sec or 0.25 }
	else
		backdropOpen[screen] = nil
	end
	backdropApply(v.sec or 0.25)
end

-- BITMAP-FONT TEXT (the compiler's "glyphs" labels: Kit_GIds / Kit_GInk / Kit_GKern / Kit_GCell): Ui.write(node, text)
-- sets ANY words in the identity's lettering — the same rules as the compiler: each glyph's measured ink, tracking,
-- the face's kerning, word wrap inside the node, its alignment. A glyph set may live in an atlas sheet (id@x,y,w,h).
-- "glyphFx" (Kit_GFx) keeps a per-glyph wave / shake running, or pops the glyphs in one after another on a write.
type GlyphFont = {
	ids: { [string]: { id: string, rect: { number }? } },
	ink: { [string]: { number } },
	kern: { [string]: number },
	cellW: number,
	cellH: number,
	lineH: number,
	track: number,
	space: number,
	align: string,
}
local glyphFonts: { [Instance]: GlyphFont } = setmetatable({}, { __mode = "k" }) :: any

local function glyphCode(ch: string): string
	if string.match(ch, "%l") then
		return "l" .. ch -- (a font's lowercase files are l<letter>: Windows names ignore case)
	elseif string.match(ch, "%w") then
		return ch
	end
	return `u{string.byte(ch)}`
end

local function glyphFont(node: Instance): GlyphFont?
	if glyphFonts[node] then
		return glyphFonts[node]
	end
	local cell = tostring(node:GetAttribute("Kit_GCell") or "")
	local cw, chh, lh, tr, sp = string.match(cell, "^([%d%.]+),([%d%.]+),([%d%.]+),([%-%d%.]+),([%d%.]+)$")
	if not cw then
		return nil
	end
	local f: GlyphFont = {
		ids = {},
		ink = {},
		kern = {},
		cellW = tonumber(cw) :: number,
		cellH = tonumber(chh) :: number,
		lineH = tonumber(lh) :: number,
		track = tonumber(tr) :: number,
		space = tonumber(sp) :: number,
		align = tostring(node:GetAttribute("Kit_GAlign") or "left"),
	}
	for code, id, rest in string.gmatch(tostring(node:GetAttribute("Kit_GIds") or ""), "([%w]+)=([^@;]+)@?([^;]*)") do
		local rect = nil
		local x, y, w, h = string.match(rest or "", "^(%d+),(%d+),(%d+),(%d+)$")
		if x then
			rect = { tonumber(x) :: number, tonumber(y) :: number, tonumber(w) :: number, tonumber(h) :: number }
		end
		f.ids[code :: string] = { id = id :: string, rect = rect }
	end
	for code, l, w in string.gmatch(tostring(node:GetAttribute("Kit_GInk") or ""), "([%w]+)=([%d%.]+),([%d%.]+)") do
		f.ink[code] = { tonumber(l) :: number, tonumber(w) :: number }
	end
	for pair, v in string.gmatch(tostring(node:GetAttribute("Kit_GKern") or ""), "([^;=]+)=([%-%d%.]+)") do
		f.kern[pair] = tonumber(v) :: number
	end
	glyphFonts[node] = f
	return f
end

local glyphFxToken: { [Instance]: number } = setmetatable({}, { __mode = "k" }) :: any

function Ui.write(node: GuiObject?, text: string)
	if not node then
		return
	end
	local f = glyphFont(node)
	if not f then
		warn(`Ui.write: {node:GetFullName()} is not a glyph-text label (its spec's "glyphs")`)
		return
	end
	local k = f.lineH / f.cellH
	local w = node.Size.X.Offset > 0 and node.Size.X.Offset or node.AbsoluteSize.X
	local function adv(ch: string, nxt: string): number
		if ch == " " then
			return f.space
		end
		local i = f.ink[glyphCode(ch)]
		local a = (if i then i[2] * f.cellW else f.cellW * 0.5) + f.track
		local kk = f.kern[ch .. nxt]
		if kk then
			a += kk * f.cellH
		end
		return a
	end
	local lines: { string } = {}
	local cur = ""
	for word in string.gmatch(text, "%S+") do
		local try = if cur == "" then word else cur .. " " .. word
		local width = 0
		for i = 1, #try do
			width += adv(string.sub(try, i, i), string.sub(try, i + 1, i + 1))
		end
		if width * k > w and cur ~= "" then
			table.insert(lines, cur)
			cur = word
		else
			cur = try
		end
	end
	if cur ~= "" then
		table.insert(lines, cur)
	end
	local cells: { ImageLabel } = {}
	for _, c in node:GetChildren() do
		if c:IsA("ImageLabel") and string.match(c.Name, "^G%d+$") then
			cells[tonumber(string.sub(c.Name, 2)) :: number] = c
		end
	end
	local used = 0
	for li, line in lines do
		local width = 0
		for i = 1, #line do
			width += adv(string.sub(line, i, i), string.sub(line, i + 1, i + 1))
		end
		width = (width - f.track) * k
		local pen = if f.align == "center" then (w - width) / 2 elseif f.align == "right" then w - width else 0
		for i = 1, #line do
			local ch = string.sub(line, i, i)
			local code = glyphCode(ch)
			local g = f.ids[code]
			if ch ~= " " and g then
				used += 1
				local cell = cells[used]
				if not cell then
					local made = Instance.new("ImageLabel")
					made.Name = `G{used}`
					made.BackgroundTransparency = 1
					made.ZIndex = node.ZIndex
					made.Parent = node
					cell = made
					cells[used] = made
				end
				local im = cell :: ImageLabel
				local ink = f.ink[code]
				local left = if ink then ink[1] * f.cellW else 0
				im.Image = g.id
				if g.rect then
					im.ImageRectOffset = Vector2.new(g.rect[1], g.rect[2])
					im.ImageRectSize = Vector2.new(g.rect[3], g.rect[4])
				else
					im.ImageRectSize = Vector2.zero
				end
				im.ScaleType = Enum.ScaleType.Stretch
				im.Size = UDim2.fromOffset(math.floor(f.cellW * k + 0.5), math.floor(f.lineH + 0.5))
				im.Position = UDim2.fromOffset(math.floor(pen - left * k + 0.5), math.floor((li - 1) * f.lineH + 0.5))
				im:SetAttribute("Kit_GHome", im.Position)
				im.Visible = true
			end
			pen += adv(ch, string.sub(line, i + 1, i + 1)) * k
		end
	end
	for i, c in cells do
		if i > used then
			c.Visible = false
		end
	end
	node:SetAttribute("Kit_GText", text)
	-- a pop: the glyphs arrive one after another (Kit_GFx "pop")
	local gfx = tostring(node:GetAttribute("Kit_GFx") or "")
	if string.sub(gfx, 1, 4) == "pop:" and not reducedMotion() then
		for i = 1, used do
			local c = cells[i]
			local s = c:FindFirstChildOfClass("UIScale") or Instance.new("UIScale")
			s.Parent = c
			s.Scale = 0
			task.delay(0.03 * (i - 1), function()
				TweenService
					:Create(s, TweenInfo.new(0.22, Enum.EasingStyle.Back, Enum.EasingDirection.Out), { Scale = 1 })
					:Play()
			end)
		end
	end
end

local function bindGlyphFx(gui: GuiObject)
	local gfx = tostring(gui:GetAttribute("Kit_GFx") or "")
	local kind, rest = string.match(gfx, "^(%a+):(.*)$")
	if not kind or kind == "pop" or reducedMotion() then
		return
	end
	local amp = tonumber(string.match(rest or "", "amp=([%d%.]+)")) or 4
	local speed = tonumber(string.match(rest or "", "speed=([%d%.]+)")) or 2
	local token = (glyphFxToken[gui] or 0) + 1
	glyphFxToken[gui] = token
	task.spawn(function()
		local t0 = os.clock()
		while gui.Parent and glyphFxToken[gui] == token do
			local t = os.clock() - t0
			for _, c in gui:GetChildren() do
				local home = c:GetAttribute("Kit_GHome")
				if c:IsA("ImageLabel") and c.Visible then
					if typeof(home) ~= "UDim2" then
						home = c.Position
						c:SetAttribute("Kit_GHome", home)
					end
					local i = tonumber(string.sub(c.Name, 2)) or 0
					local dy = if kind == "wave"
						then math.sin((t * speed + i * 0.12) * math.pi * 2) * amp
						else (math.random() * 2 - 1) * amp
					local dx = if kind == "shake" then (math.random() * 2 - 1) * amp else 0
					c.Position = (home :: UDim2) + UDim2.fromOffset(dx, dy)
				end
			end
			task.wait(if kind == "shake" then 1 / 30 else 1 / 60)
		end
	end)
end

-- HUD SYSTEMS (v7.8): world-tracking markers, the compass bar, directional damage and reward flights.
--   Ui.track(marker, target)        the "marker" sits over its target while seen; off screen (or BEHIND the camera:
--                                   the classic bug flips it to the wrong side) it pins to the screen edge on an
--                                   ellipse / rectangle inset by Kit_MarkerMargin, its arrow turned toward the
--                                   target; markers pinned to the same edge push apart; the Dist label counts studs
--   compass bars                    bound by Ui.bind: the strip slides with the camera's heading
--   Ui.hurt(damage, from)           a red arc toward whoever hit you, fading over ~1 s
--   Ui.fly(from, to, opts)          coins / gems fly on arcs from a node (or a screen point) into a counter; each
--                                   arrival punches it and calls opts.onEach(i) (add the value there)
--   (V4 UI-X 13.6, the Combat Feedback Kit: its rules are UiCombat, pure and specced in Lune)
--   Ui.waypoint(marker, target)     = Ui.track
--   Ui.damageArc(damage, from)      = Ui.hurt + a haptic pulse; new arcs past 3 a second re-aim the newest instead
--   Ui.streakLadder(ladder, kind)   a "ladder" node: "hit" | "crit" | "kill" | "reset" -> spring-stacked banners
--   Ui.compare(item, worn, cand, o) a "tip" node's compare lines (good / bad by the stat, lower-is-better aware)
local tracked: { [GuiObject]: Instance | Vector3 } = setmetatable({}, { __mode = "k" }) :: any
local trackConn: RBXScriptConnection? = nil

local function targetPos(t: Instance | Vector3): Vector3?
	if typeof(t) == "Vector3" then
		return t :: Vector3
	end
	local inst = t :: Instance
	if inst.Parent == nil then
		return nil
	end
	if inst:IsA("BasePart") then
		return inst.Position
	elseif inst:IsA("Model") then
		return inst:GetPivot().Position
	elseif inst:IsA("Attachment") then
		return inst.WorldPosition
	end
	return nil
end

local function trackStep()
	local cam = workspace.CurrentCamera
	if not cam then
		return
	end
	local vs = cam.ViewportSize
	local pinned: { { node: GuiObject, pos: Vector2, edge: string } } = {}
	for node, target in tracked do
		local at = targetPos(target)
		if node.Parent == nil or at == nil then
			tracked[node] = nil
			continue
		end
		local parent = node.Parent :: GuiObject
		-- (the parent's corner, AbsolutePosition: a ScreenGui has one too - it is where the inset puts it)
		local origin = if parent:IsA("GuiBase2d") then parent.AbsolutePosition else Vector2.zero
		local inset = GuiService:GetGuiInset()
		local margin = num(node, "Kit_MarkerMargin", 56)
		local pivot = node:FindFirstChild("Pivot") :: GuiObject?
		local dist = node:FindFirstChild("Dist")
		if dist and dist:IsA("TextLabel") then
			dist.Text = `{math.floor((cam.CFrame.Position - at).Magnitude + 0.5)} m`
		end
		-- the rules work in camera space (UiCombat.waypoint): continuous behind the camera and on its own plane, where a
		-- projected point divides by ~0 and flips edges. FieldOfView is vertical, so the focal length is in pixels of Y
		local lp = cam.CFrame:PointToObjectSpace(at)
		local focal = (vs.Y / 2) / math.tan(math.rad(cam.FieldOfView) / 2)
		local shape = if node:GetAttribute("Kit_Marker") == "rect" then "rect" else "ellipse"
		local wp = UiCombat.waypoint(lp.X, lp.Y, lp.Z, vs.X, vs.Y, focal, margin, shape)
		local pos = Vector2.new(wp.x, wp.y)
		if pivot then
			pivot.Visible = not wp.onScreen
			if not wp.onScreen then
				pivot.Rotation = wp.angle
			end
		end
		if not wp.onScreen then
			table.insert(pinned, { node = node, pos = pos, edge = wp.edge or "bottom" })
		end
		local ox, oy = UiCombat.placeIn(pos.X, pos.Y, origin.X, origin.Y, inset.X, inset.Y)
		node.Position = UDim2.fromOffset(ox, oy)
	end
	-- markers pinned to one edge push apart along it (their labels must not stack)
	table.sort(pinned, function(a, b)
		return if a.edge == b.edge
			then (if a.edge == "left" or a.edge == "right" then a.pos.Y < b.pos.Y else a.pos.X < b.pos.X)
			else a.edge < b.edge
	end)
	for i = 2, #pinned do
		local a, b = pinned[i - 1], pinned[i]
		if a.edge == b.edge then
			local vertical = a.edge == "left" or a.edge == "right"
			local gap = if vertical then b.node.AbsoluteSize.Y else b.node.AbsoluteSize.X
			local da = if vertical then b.pos.Y - a.pos.Y else b.pos.X - a.pos.X
			if da < gap then
				local shift = gap - da
				b.pos += if vertical then Vector2.new(0, shift) else Vector2.new(shift, 0)
				b.node.Position += if vertical then UDim2.fromOffset(0, shift) else UDim2.fromOffset(shift, 0)
			end
		end
	end
end

function Ui.track(marker: GuiObject?, target: (Instance | Vector3)?)
	if not marker then
		return
	end
	if target == nil then
		tracked[marker] = nil
		return
	end
	marker.AnchorPoint = Vector2.new(0.5, 0.5)
	tracked[marker] = target :: Instance | Vector3
	if not trackConn then
		trackConn = RunService.RenderStepped:Connect(trackStep)
	end
end

local function bindCompass(bar: GuiObject)
	local strip = bar:FindFirstChild("Strip") :: GuiObject?
	local ppd = num(bar, "Kit_Compass", 0)
	if not strip or ppd <= 0 then
		return
	end
	local conn
	conn = RunService.RenderStepped:Connect(function()
		if bar.Parent == nil then
			conn:Disconnect()
			return
		end
		local cam = workspace.CurrentCamera
		if not cam then
			return
		end
		local look = cam.CFrame.LookVector
		-- heading: 0 = north (-Z), 90 = east (+X), clockwise
		local heading = math.deg(math.atan2(look.X, -look.Z)) % 360
		strip.Position = UDim2.fromOffset(bar.Size.X.Offset / 2 - ppd * (360 + heading), 0)
	end)
end

local hurtGates: { [GuiObject]: UiCombat.Limiter } = setmetatable({}, { __mode = "k" }) :: any
local hurtNewest: { [GuiObject]: GuiObject } = setmetatable({}, { __mode = "k" }) :: any

function Ui.hurt(damage: GuiObject?, from: Vector3)
	if not damage then
		return
	end
	local wedge = damage:FindFirstChild("Wedge") :: GuiObject?
	local cam = workspace.CurrentCamera
	if not wedge or not cam then
		return
	end
	-- the attacker's bearing relative to where the camera looks (0 = ahead = the top of the screen, +90 = right; a
	-- GuiObject's Rotation is clockwise). (Before V4 UI-X the arc took -bearing: a hit from the right lit the LEFT.)
	local cp, look = cam.CFrame.Position, cam.CFrame.LookVector
	local bearing = UiCombat.bearing(from.X, from.Z, cp.X, cp.Z, look.X, look.Z)
	if bearing == nil then
		return
	end
	-- three flashes a second at most (WCAG 2.3.1): past that, the newest arc turns toward the new attacker instead
	local gate = hurtGates[damage]
	if not gate then
		gate = UiCombat.limiter(3, 1)
		hurtGates[damage] = gate
	end
	if not gate:allow(os.clock()) then
		local newest = hurtNewest[damage]
		if newest and newest.Parent then
			newest.Rotation = bearing
		end
		return
	end
	local copy = wedge:Clone()
	copy.Name = "Hurt"
	copy.Visible = true
	copy.Rotation = bearing
	copy.Parent = damage
	hurtNewest[damage] = copy
	local arc = copy:FindFirstChild("Arc")
	if arc then
		Ui.path(arc :: GuiObject, 1)
	end
	task.delay(0.25, function()
		local secs = if reducedMotion() then 0.2 else 0.8
		for _, d in copy:GetDescendants() do
			if d:IsA("Path2D") then
				local c0 = d.Color3
				local t0 = os.clock()
				task.spawn(function()
					while d.Parent and os.clock() - t0 < secs do
						local k = (os.clock() - t0) / secs
						d.Color3 = c0:Lerp(Color3.new(0, 0, 0), k * 0.6)
						d.Thickness = math.max(1, d.Thickness * (1 - 0.04))
						RunService.Heartbeat:Wait()
					end
				end)
			end
		end
		task.delay(secs, function()
			copy:Destroy()
		end)
	end)
end

-- the Combat Feedback Kit's names (V4 UI-X 13.6)
Ui.waypoint = Ui.track

function Ui.damageArc(damage: GuiObject?, from: Vector3)
	Ui.hurt(damage, from)
	Ui.haptic()
end

-- THE STREAK LADDER: a "ladder" node's banners. Ui.streakLadder(node, "kill") -> the event UiCombat recorded (nil for
-- "reset" / an unknown kind). The newest banner springs in at the top, the older ones spring down a row; past the
-- node's Kit_Ladder (max) the oldest goes; each fades after ~2.5 s.
local ladders: { [GuiObject]: UiCombat.Ladder } = setmetatable({}, { __mode = "k" }) :: any
local ladderGates: { [GuiObject]: UiCombat.Limiter } = setmetatable({}, { __mode = "k" }) :: any

function Ui.streakLadder(node: GuiObject?, kind: string): UiCombat.LadderEvent?
	if not node then
		return nil
	end
	local state = ladders[node]
	if not state then
		local rungs = {}
		for r in string.gmatch(tostring(node:GetAttribute("Kit_LadderRungs") or ""), "[^|]+") do
			table.insert(rungs, r)
		end
		state = UiCombat.ladder({
			rungs = rungs,
			killWindow = node:GetAttribute("Kit_LadderKillWindow"),
			hitWindow = node:GetAttribute("Kit_LadderHitWindow"),
			hitStep = node:GetAttribute("Kit_LadderHitStep"),
			killLabel = node:GetAttribute("Kit_LadderKill"),
			critLabel = node:GetAttribute("Kit_LadderCrit"),
		})
		ladders[node] = state
		ladderGates[node] = UiCombat.limiter(3, 1)
	end
	local ev = state:record(kind, os.clock())
	local template = node:FindFirstChild("Banner") :: GuiObject?
	if not ev or not ev.banner or not template then
		return ev
	end
	local max = math.clamp(num(node, "Kit_Ladder", 3), 1, 6)
	local rowH = template.Size.Y.Offset + 6
	local live: { GuiObject } = {}
	for _, c in node:GetChildren() do
		if c.Name == "KitBanner" and c:IsA("GuiObject") then
			table.insert(live, c)
		end
	end
	table.sort(live, function(a, b)
		return (a:GetAttribute("Kit_At") or 0) > (b:GetAttribute("Kit_At") or 0)
	end)
	-- a chain climbing faster than three banners a second updates the top banner instead of stacking a new one
	-- (WCAG 2.3.1: a banner popping in is a flash)
	local top = live[1]
	local fresh = (ladderGates[node] :: UiCombat.Limiter):allow(os.clock()) or #live == 0
	local banner: GuiObject
	if fresh then
		banner = template:Clone()
		banner.Name = "KitBanner"
		banner.Visible = true
		banner.Position = UDim2.fromOffset(0, -rowH)
		banner.Parent = node
		table.insert(live, 1, banner)
	else
		banner = top :: GuiObject
	end
	banner:SetAttribute("Kit_At", os.clock())
	local label = banner:FindFirstChild("Label")
	local count = banner:FindFirstChild("Count")
	if label and label:IsA("TextLabel") then
		label.Text = ev.label
	end
	if count and count:IsA("TextLabel") then
		count.Text = if ev.kind == "kill" and ev.count >= 2 then `x{ev.count}` else ""
	end
	for i, b in live do
		if i > max then
			b:Destroy()
		else
			Ui.spring(b, "Position", UDim2.fromOffset(0, (i - 1) * rowH), 4, 0.7)
		end
	end
	if fresh then
		Ui.punch(banner, 0.18)
		if ev.kind == "kill" then
			Ui.haptic(if ev.count >= 2 then "heavy" else nil)
		end
		local stamp = banner:GetAttribute("Kit_At")
		task.delay(2.5, function()
			if banner.Parent and banner:GetAttribute("Kit_At") == stamp then
				local last: Tween? = nil
				for _, d in banner:GetDescendants() do
					if d:IsA("TextLabel") then
						last = TweenService:Create(d, SMOOTH, { TextTransparency = 1, TextStrokeTransparency = 1 })
					elseif d:IsA("ImageLabel") then
						last = TweenService:Create(d, SMOOTH, { ImageTransparency = 1 })
					elseif d:IsA("UIStroke") then
						last = TweenService:Create(d, SMOOTH, { Transparency = 1 })
					else
						last = nil
					end
					if last then
						last:Play()
					end
				end
				TweenService:Create(banner, SMOOTH, { BackgroundTransparency = 1 }):Play()
				task.delay(0.3, function()
					banner:Destroy()
				end)
			end
		end)
	end
	return ev
end

-- a COMPARE TOOLTIP: what the item under the cursor would change against what is worn. Writes the tipped node's
-- Kit_TipLines (the tooltip colours each line by its tone, so a shorter reload reads good); opts = { lowerBetter =
-- {Reload = true}, units = {Reload = "s"}, order = {...}, title = "..." }. -> the rows
function Ui.compare(
	item: GuiObject?,
	worn: { [string]: number },
	candidate: { [string]: number },
	opts: { [string]: any }?
): { UiCombat.CompareRow }
	local rows = UiCombat.compare(worn, candidate, opts)
	if item then
		item:SetAttribute("Kit_TipLines", UiCombat.tipLines(rows))
		if opts and type(opts.title) == "string" then
			item:SetAttribute("Kit_Tip", opts.title)
		elseif item:GetAttribute("Kit_Tip") == nil then
			item:SetAttribute("Kit_Tip", item.Name)
		end
	end
	return rows
end

function Ui.fly(from: GuiObject | Vector2, to: GuiObject?, opts: { [string]: any }?)
	if not to then
		return
	end
	local o: { [string]: any } = opts or {}
	local screen = to:FindFirstAncestorWhichIsA("LayerCollector")
	if not screen then
		return
	end
	local count = math.clamp(tonumber(o.count) or 8, 1, 40)
	local secs = tonumber(o.seconds) or 0.6
	local image = o.image
	local tint = o.color
	if type(o.preset) == "string" then -- (a burst preset's sprite and colours: the identity's own coin)
		local raw = tostring(screen:GetAttribute("Kit_Burst_" .. o.preset) or "")
		image = image or string.match(raw, "sprite=([^;]+)")
		local hex = string.match(raw, "colors=(#%x%x%x%x%x%x)")
		if hex and not tint then
			tint = Color3.fromHex(hex)
		end
	end
	local start = if typeof(from) == "Vector2"
		then from :: Vector2
		else (from :: GuiObject).AbsolutePosition + (from :: GuiObject).AbsoluteSize / 2
	local finish = to.AbsolutePosition + to.AbsoluteSize / 2
	local layer = Instance.new("Frame")
	layer.Name = "KitFly"
	layer.BackgroundTransparency = 1
	layer.Size = UDim2.fromScale(1, 1)
	layer.ZIndex = 120
	layer.Parent = screen
	local origin = layer.AbsolutePosition
	local size = tonumber(o.size) or 28
	for i = 1, count do
		task.delay((i - 1) * 0.05, function()
			local sp = Instance.new("ImageLabel")
			sp.BackgroundTransparency = 1
			sp.AnchorPoint = Vector2.new(0.5, 0.5)
			sp.Size = UDim2.fromOffset(size, size)
			sp.Image = image or ""
			if tint then
				sp.ImageColor3 = tint
			end
			sp.ZIndex = 120
			sp.Parent = layer
			local jitter = Vector2.new((math.random() - 0.5) * 120, (math.random() - 0.5) * 80)
			local p0, p2 = start - origin, finish - origin
			local p1 = (p0 + p2) / 2 + jitter + Vector2.new(0, -160)
			local t0 = os.clock()
			local dur = if reducedMotion() then 0.05 else secs
			while sp.Parent and os.clock() - t0 < dur do
				local k = (os.clock() - t0) / dur
				local e = k * k * (3 - 2 * k)
				local p = (1 - e) ^ 2 * p0 + 2 * (1 - e) * e * p1 + e * e * p2
				sp.Position = UDim2.fromOffset(p.X, p.Y)
				RunService.Heartbeat:Wait()
			end
			sp:Destroy()
			if type(o.onEach) == "function" then
				task.spawn(o.onEach, i)
			end
			if Ui.punch then
				pcall(Ui.punch, to)
			end
			if i == count then
				task.delay(0.1, function()
					layer:Destroy()
				end)
			end
		end)
	end
end

-- MENU SYSTEMS (v7.9):
--   Ui.toast(toasts, "Saved!", kind?)   the "toasts" component's queue: at most Kit_Toasts on screen, the rest wait;
--                                       each slides in, holds ~2.4 s, slides out; kind colours its text (good / danger)
--   Ui.modal(screen) / Ui.back()        a STACK of open modal screens: Back (Escape, gamepad B) always closes the top
--   tooltips                            a node with "tip" shows the screen's "tooltip" beside it on hover / selection;
--                                       compare lines "+12 ATK" / "-3 DEF" turn good / danger by their sign
--   Ui.loading(screen, assets, tips?)   preloads (a "Progress" bar's fill, a "Tip" label cycling tips), at least 1.2 s
--   Ui.coach(steps, screen)             a FIRST-TIME tutorial: a spotlight cut-out on one element, one line, "2 of 4",
--                                       Skip; each step advances when its element is pressed (or on a tap)
local toastQueues: { [Instance]: { busy: number, wait: { { text: string, kind: string? } } } } = setmetatable(
	{},
	{ __mode = "k" }
) :: any

local function tokenColor(node: Instance, kind: string?): Color3?
	local screen = node:FindFirstAncestorWhichIsA("LayerCollector")
	local hex = screen and kind and screen:GetAttribute("Kit_" .. kind)
	if type(hex) == "string" and string.match(hex, "^#%x%x%x%x%x%x$") then
		return Color3.fromHex(hex)
	end
	return nil
end

function Ui.toast(toasts: GuiObject?, text: string, kind: string?)
	if not toasts then
		return
	end
	local template = toasts:FindFirstChild("Toast") :: GuiObject?
	if not template then
		return
	end
	local q = toastQueues[toasts] or { busy = 0, wait = {} }
	toastQueues[toasts] = q
	local max = num(toasts, "Kit_Toasts", 3)
	if q.busy >= max then
		table.insert(q.wait, { text = text, kind = kind })
		return
	end
	q.busy += 1
	local t = template:Clone()
	t.Name = "Live"
	t.Visible = true
	local slot = q.busy - 1
	local h = template.AbsoluteSize.Y > 0 and template.AbsoluteSize.Y or template.Size.Y.Offset
	t.Position = UDim2.new(1, 40, 0, slot * (h + 8))
	t.Parent = toasts
	local label = t:FindFirstChild("Label")
	if label and label:IsA("TextLabel") then
		label.Text = text
		label.TextColor3 = tokenColor(toasts, kind) or label.TextColor3
	end
	local secs = if reducedMotion() then 0 else 0.22
	TweenService:Create(t, TweenInfo.new(secs, Enum.EasingStyle.Quad, Enum.EasingDirection.Out), {
		Position = UDim2.fromOffset(0, slot * (h + 8)),
	}):Play()
	task.delay(2.4, function()
		TweenService:Create(t, TweenInfo.new(secs, Enum.EasingStyle.Quad, Enum.EasingDirection.In), {
			Position = UDim2.new(1, 40, 0, slot * (h + 8)),
		}):Play()
		task.wait(secs)
		t:Destroy()
		q.busy -= 1
		local nxt = table.remove(q.wait, 1)
		if nxt then
			Ui.toast(toasts, nxt.text, nxt.kind)
		end
	end)
end

local modalStack: { ScreenGui } = {}
local backBound = false

function Ui.back(): boolean
	local top = table.remove(modalStack)
	if top then
		Ui.show(top, false)
		return true
	end
	return false
end

function Ui.modal(screen: ScreenGui?)
	if not screen then
		return
	end
	table.insert(modalStack, screen)
	Ui.show(screen, true)
	if not backBound then
		backBound = true
		local CAS = game:GetService("ContextActionService")
		CAS:BindActionAtPriority("KitUiBack", function(_, state)
			if state ~= Enum.UserInputState.Begin then
				return Enum.ContextActionResult.Pass
			end
			return if Ui.back() then Enum.ContextActionResult.Sink else Enum.ContextActionResult.Pass
		end, false, 3000, Enum.KeyCode.Escape, Enum.KeyCode.ButtonB)
	end
end

local function bindTip(gui: GuiObject)
	local screen = gui:FindFirstAncestorWhichIsA("LayerCollector")
	local function tooltip(): GuiObject?
		if not screen then
			return nil
		end
		for _, d in screen:GetDescendants() do
			if d:GetAttribute("Kit_Tooltip") and d:IsA("GuiObject") then
				return d
			end
		end
		return nil
	end
	local function show()
		local tip = tooltip()
		if not tip then
			return
		end
		local title = tip:FindFirstChild("Title")
		local body = tip:FindFirstChild("Body")
		if title and title:IsA("TextLabel") then
			title.Text = tostring(gui:GetAttribute("Kit_Tip") or "")
		end
		if body and body:IsA("TextLabel") then
			local good = tostring(screen and screen:GetAttribute("Kit_good") or "#7fc98a")
			local bad = tostring(screen and screen:GetAttribute("Kit_danger") or "#d9483b")
			local out = {}
			for raw in string.gmatch(tostring(gui:GetAttribute("Kit_TipLines") or ""), "[^\n]+") do
				-- a line's tone: Ui.compare's "good:" / "bad:" prefix (a shorter reload is good), else its sign
				local tone, line = UiCombat.lineTone(raw)
				if tone == "good" then
					table.insert(out, `<font color="{good}">{line}</font>`)
				elseif tone == "bad" then
					table.insert(out, `<font color="{bad}">{line}</font>`)
				else
					table.insert(out, line)
				end
			end
			body.RichText = true
			body.Text = table.concat(out, "<br/>")
		end
		local parent = tip.Parent :: GuiObject
		local origin = if parent:IsA("GuiObject") then parent.AbsolutePosition else Vector2.zero
		local at = gui.AbsolutePosition + Vector2.new(gui.AbsoluteSize.X + 12, 0) - origin
		if tip:GetAttribute("Kit_TipHeld") ~= true then
			tip.AnchorPoint = Vector2.zero
			tip.Position = UDim2.fromOffset(at.X, at.Y)
		end
		tip.Visible = true
		-- a draggable compare tooltip (spec "drag": true): a UIDragDetector, made once; while the player holds or has
		-- pulled it aside it stays (held), until the next item's hover leaves it again
		if tip:GetAttribute("Kit_TooltipDrag") == true and not tip:FindFirstChildWhichIsA("UIDragDetector") then
			local okD, made = pcall(Instance.new, "UIDragDetector")
			if okD then
				local drag = made :: UIDragDetector
				drag.Parent = tip
				drag.DragStart:Connect(function()
					tip:SetAttribute("Kit_TipHeld", true)
				end)
				tip.MouseEnter:Connect(function()
					tip:SetAttribute("Kit_TipOver", true)
				end)
				tip.MouseLeave:Connect(function()
					tip:SetAttribute("Kit_TipOver", false)
					task.delay(0.2, function()
						if tip:GetAttribute("Kit_TipOver") ~= true then
							tip:SetAttribute("Kit_TipHeld", false)
							tip.Visible = false
						end
					end)
				end)
			end
		end
	end
	local function hide()
		local tip = tooltip()
		if not tip then
			return
		end
		if tip:GetAttribute("Kit_TooltipDrag") == true then
			-- a grace moment to reach the tooltip; a held one stays until the pointer leaves it
			task.delay(0.2, function()
				if tip:GetAttribute("Kit_TipOver") == true then
					return
				end
				if tip:GetAttribute("Kit_TipHeld") == true then
					tip:SetAttribute("Kit_TipHeld", false)
				end
				tip.Visible = false
			end)
			return
		end
		tip.Visible = false
	end
	gui.MouseEnter:Connect(show)
	gui.MouseLeave:Connect(hide)
	gui.SelectionGained:Connect(show)
	gui.SelectionLost:Connect(hide)
end

function Ui.loading(screen: ScreenGui?, assets: { any }?, tips: { string }?, onDone: (() -> ())?)
	if not screen then
		return
	end
	local ContentProvider = game:GetService("ContentProvider")
	Ui.show(screen, true)
	local bar, tipLabel
	for _, d in screen:GetDescendants() do
		if d.Name == "Progress" and d:IsA("GuiObject") then
			bar = d
		elseif d.Name == "Tip" and d:IsA("TextLabel") then
			tipLabel = d
		end
	end
	task.spawn(function()
		local t0 = os.clock()
		local list: { any } = assets or {}
		local done = 0
		local tipIndex = 0
		local function nextTip()
			if tipLabel and tips and #tips > 0 then
				tipIndex = tipIndex % #tips + 1
				tipLabel.Text = tips[tipIndex]
			end
		end
		nextTip()
		for i, a in list do
			pcall(function()
				ContentProvider:PreloadAsync({ a })
			end)
			done = i
			if bar then
				Ui.bar(bar, done / math.max(1, #list))
			end
			if i % 6 == 0 then
				nextTip()
			end
		end
		while os.clock() - t0 < 1.2 do
			task.wait(0.1)
		end
		if bar then
			Ui.bar(bar, 1)
		end
		task.wait(0.25)
		Ui.show(screen, false)
		if onDone then
			onDone()
		end
	end)
end

function Ui.coach(steps: { { target: GuiObject, text: string } }, screen: ScreenGui?)
	if #steps == 0 then
		return
	end
	local host = screen or steps[1].target:FindFirstAncestorWhichIsA("ScreenGui")
	if not host then
		return
	end
	local layer = Instance.new("ScreenGui")
	layer.Name = "KitCoach"
	layer.DisplayOrder = 900
	layer.IgnoreGuiInset = true
	layer.ResetOnSpawn = false
	layer.Parent = host.Parent
	local dims: { Frame } = {}
	for i = 1, 4 do
		local f = Instance.new("Frame")
		f.BackgroundColor3 = Color3.new(0, 0, 0)
		f.BackgroundTransparency = 0.45
		f.BorderSizePixel = 0
		f.Name = `Dim{i}`
		f.Parent = layer
		dims[i] = f
	end
	local ring = Instance.new("Frame")
	ring.BackgroundTransparency = 1
	ring.Name = "Ring"
	local stroke = Instance.new("UIStroke")
	stroke.Thickness = 3
	stroke.Color = tokenColor(host, "accent") or Color3.new(1, 1, 1)
	stroke.Parent = ring
	local corner = Instance.new("UICorner")
	corner.CornerRadius = UDim.new(0, 10)
	corner.Parent = ring
	ring.Parent = layer
	local caption = Instance.new("TextLabel")
	caption.BackgroundTransparency = 1
	caption.TextColor3 = Color3.new(1, 1, 1)
	caption.TextStrokeTransparency = 0.3
	caption.TextSize = 22
	caption.Size = UDim2.fromOffset(420, 60)
	caption.TextWrapped = true
	caption.Parent = layer
	local counter = caption:Clone()
	counter.TextSize = 16
	counter.Size = UDim2.fromOffset(120, 24)
	counter.Parent = layer
	local skip = Instance.new("TextButton")
	skip.Text = "Skip"
	skip.TextSize = 18
	skip.TextColor3 = Color3.new(1, 1, 1)
	skip.BackgroundTransparency = 0.6
	skip.BackgroundColor3 = Color3.new(0, 0, 0)
	skip.Size = UDim2.fromOffset(90, 40)
	skip.AnchorPoint = Vector2.new(1, 1)
	skip.Position = UDim2.new(1, -24, 1, -24)
	skip.Parent = layer
	local index = 0
	local conns: { RBXScriptConnection } = {}
	local function finish()
		for _, c in conns do
			c:Disconnect()
		end
		layer:Destroy()
	end
	local nextStep: () -> ()
	nextStep = function()
		for _, c in conns do
			c:Disconnect()
		end
		table.clear(conns)
		index += 1
		local step = steps[index]
		if not step or not step.target.Parent then
			finish()
			return
		end
		local p, s = step.target.AbsolutePosition, step.target.AbsoluteSize
		local pad = 8
		local x0, y0, x1, y1 = p.X - pad, p.Y - pad, p.X + s.X + pad, p.Y + s.Y + pad
		-- four dim panels around the cut-out (the element stays bright and pressable)
		dims[1].Position, dims[1].Size = UDim2.fromOffset(0, 0), UDim2.new(1, 0, 0, y0)
		dims[2].Position, dims[2].Size = UDim2.fromOffset(0, y1), UDim2.new(1, 0, 1, -y1)
		dims[3].Position, dims[3].Size = UDim2.fromOffset(0, y0), UDim2.fromOffset(x0, y1 - y0)
		dims[4].Position, dims[4].Size = UDim2.fromOffset(x1, y0), UDim2.new(1, -x1, 0, y1 - y0)
		ring.Position, ring.Size = UDim2.fromOffset(x0, y0), UDim2.fromOffset(x1 - x0, y1 - y0)
		caption.Text = step.text
		local below = y1 + 70 < layer.AbsoluteSize.Y
		caption.Position = UDim2.fromOffset(math.max(12, x0), if below then y1 + 10 else y0 - 70)
		counter.Text = `{index} of {#steps}`
		counter.Position = UDim2.fromOffset(math.max(12, x0), if below then y1 + 70 else y0 - 96)
		if step.target:IsA("GuiButton") then
			table.insert(conns, (step.target :: GuiButton).Activated:Connect(nextStep))
		else
			table.insert(
				conns,
				game:GetService("UserInputService").InputBegan:Connect(function(input)
					if
						input.UserInputType == Enum.UserInputType.MouseButton1
						or input.UserInputType == Enum.UserInputType.Touch
					then
						nextStep()
					end
				end)
			)
		end
	end
	skip.Activated:Connect(finish)
	nextStep()
end

-- ROBLOX'S OWN UI in the identity (v7.10): the chat (TextChatService's window, input bar and bubbles) takes a kit screen's
-- tokens (Kit_panel / Kit_text / Kit_muted / Kit_accent and its Kit_Font), and Ui.core hides the Roblox pieces the
-- game replaces with its own (health, backpack, player list, emotes) — retried until the CoreGui is ready.
--   Ui.chat(screen)                      the chat wears that screen's identity
--   Ui.core({health = false, backpack = false, playerList = false})
local function tokenOf(screen: Instance, name: string, fallback: Color3): Color3
	local hex = screen:GetAttribute("Kit_" .. name)
	if type(hex) == "string" and string.match(hex, "^#%x%x%x%x%x%x$") then
		return Color3.fromHex(hex)
	end
	return fallback
end

function Ui.chat(screen: Instance?)
	if not screen then
		return
	end
	local TextChatService = game:GetService("TextChatService")
	local panel = tokenOf(screen, "panel", Color3.fromRGB(20, 20, 24))
	local text = tokenOf(screen, "text", Color3.new(1, 1, 1))
	local muted = tokenOf(screen, "muted", Color3.fromRGB(160, 160, 170))
	local face: Font? = nil
	local fontName = screen:GetAttribute("Kit_Font")
	if type(fontName) == "string" then
		pcall(function()
			face = Font.fromEnum((Enum.Font :: any)[fontName])
		end)
	end
	local function style(inst: Instance?, props: { [string]: any })
		if not inst then
			return
		end
		for k, v in props do
			pcall(function()
				(inst :: any)[k] = v
			end)
		end
		if face then
			pcall(function()
				(inst :: any).FontFace = face
			end)
		end
	end
	style(TextChatService:FindFirstChildOfClass("ChatWindowConfiguration"), {
		BackgroundColor3 = panel,
		BackgroundTransparency = 0.25,
		TextColor3 = text,
		TextStrokeTransparency = 0.6,
	})
	style(TextChatService:FindFirstChildOfClass("ChatInputBarConfiguration"), {
		BackgroundColor3 = panel,
		BackgroundTransparency = 0.15,
		TextColor3 = text,
		PlaceholderColor3 = muted,
	})
	style(TextChatService:FindFirstChildOfClass("BubbleChatConfiguration"), {
		BackgroundColor3 = panel,
		BackgroundTransparency = 0.1,
		TextColor3 = text,
		TailVisible = true,
	})
end

function Ui.core(show: { [string]: boolean })
	local StarterGui = game:GetService("StarterGui")
	local map = {
		health = Enum.CoreGuiType.Health,
		backpack = Enum.CoreGuiType.Backpack,
		playerList = Enum.CoreGuiType.PlayerList,
		emotes = Enum.CoreGuiType.EmotesMenu,
		chat = Enum.CoreGuiType.Chat,
	}
	task.spawn(function()
		for key, on in show do
			local kind = map[key]
			if kind then
				for _ = 1, 20 do -- (the CoreGui may not be ready in the first frames)
					if pcall(StarterGui.SetCoreGuiEnabled, StarterGui, kind, on) then
						break
					end
					task.wait(0.25)
				end
			end
		end
	end)
end

-- TRANSITIONS + PLAYER SETTINGS (v7.14):
--   Ui.wipe("shutter" | "slash" | "blinds", {color, seconds, onCovered})   a full-screen branded wipe: it COVERS the
--       screen, calls onCovered (swap screens, teleport, load) while covered, then uncovers. Colour: a kit screen's
--       accent token unless given.
--   Ui.setTextScale(1.25)    every kit text scaled from its designed size (a player's "text size" setting)
--   Ui.setHighContrast(true) every kit text gets a solid dark outline (XAG high-contrast); false puts the design back
local function kitTexts(): { TextLabel }
	local out = {}
	local gui = Players.LocalPlayer and Players.LocalPlayer:FindFirstChildOfClass("PlayerGui")
	if not gui then
		return out
	end
	for _, screen in gui:GetChildren() do
		if screen:IsA("LayerCollector") and screen:GetAttribute("Kit_Kind") ~= nil then
			for _, d in screen:GetDescendants() do
				if d:IsA("TextLabel") or d:IsA("TextButton") then
					table.insert(out, d :: any)
				end
			end
		end
	end
	return out
end

function Ui.setTextScale(k: number)
	local scale = math.clamp(k, 0.75, 2)
	for _, t in kitTexts() do
		local designed = t:GetAttribute("Kit_DesignTextSize")
		if type(designed) ~= "number" then
			designed = t.TextSize
			t:SetAttribute("Kit_DesignTextSize", designed)
		end
		t.TextSize = math.floor((designed :: number) * scale + 0.5)
	end
end

function Ui.setHighContrast(on: boolean)
	for _, t in kitTexts() do
		if on then
			if t:GetAttribute("Kit_DesignStroke") == nil then
				t:SetAttribute("Kit_DesignStroke", t.TextStrokeTransparency)
			end
			t.TextStrokeColor3 = Color3.new(0, 0, 0)
			t.TextStrokeTransparency = 0
		else
			local designed = t:GetAttribute("Kit_DesignStroke")
			if type(designed) == "number" then
				t.TextStrokeTransparency = designed
			end
		end
	end
end

function Ui.wipe(kind: string, opts: { [string]: any }?)
	local o: { [string]: any } = opts or {}
	local gui = Players.LocalPlayer and Players.LocalPlayer:FindFirstChildOfClass("PlayerGui")
	if not gui then
		if type(o.onCovered) == "function" then
			o.onCovered()
		end
		return
	end
	local color: Color3 = o.color or Color3.fromRGB(10, 10, 14)
	if not o.color then
		for _, screen in gui:GetChildren() do
			local hex = screen:GetAttribute("Kit_accent")
			if type(hex) == "string" and string.match(hex, "^#%x%x%x%x%x%x$") then
				color = Color3.fromHex(hex)
				break
			end
		end
	end
	local secs = if reducedMotion() then 0.05 else (tonumber(o.seconds) or 0.32)
	local layer = Instance.new("ScreenGui")
	layer.Name = "KitWipe"
	layer.DisplayOrder = 2000
	layer.IgnoreGuiInset = true
	layer.ResetOnSpawn = false
	layer.Parent = gui
	local pieces: { { frame: Frame, shut: UDim2, open: UDim2 } } = {}
	local function piece(size: UDim2, open: UDim2, shut: UDim2, rot: number?)
		local f = Instance.new("Frame")
		f.BorderSizePixel = 0
		f.BackgroundColor3 = color
		f.Size = size
		f.Position = open
		f.AnchorPoint = Vector2.new(0.5, 0.5)
		f.Rotation = rot or 0
		f.Parent = layer
		table.insert(pieces, { frame = f, shut = shut, open = open })
	end
	if kind == "slash" then
		piece(UDim2.fromScale(2.2, 1.6), UDim2.fromScale(-1.2, 0.5), UDim2.fromScale(0.5, 0.5), -14)
	elseif kind == "blinds" then
		for i = 0, 7 do
			local y = (i + 0.5) / 8
			piece(UDim2.fromScale(1.02, 0), UDim2.fromScale(0.5, y), UDim2.fromScale(0.5, y))
		end
	else -- shutter
		piece(UDim2.fromScale(1.02, 0.52), UDim2.fromScale(0.5, -0.27), UDim2.fromScale(0.5, 0.25))
		piece(UDim2.fromScale(1.02, 0.52), UDim2.fromScale(0.5, 1.27), UDim2.fromScale(0.5, 0.75))
	end
	local inInfo = TweenInfo.new(secs, Enum.EasingStyle.Quad, Enum.EasingDirection.In)
	local outInfo = TweenInfo.new(secs, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)
	for i, p in pieces do
		local goal: { [string]: any } = { Position = p.shut }
		if kind == "blinds" then
			goal = { Size = UDim2.fromScale(1.02, 1 / 8 + 0.004) }
		end
		task.delay(if kind == "blinds" then (i - 1) * 0.02 else 0, function()
			TweenService:Create(p.frame, inInfo, goal):Play()
		end)
	end
	task.delay(secs + (if kind == "blinds" then 0.16 else 0) + 0.02, function()
		if type(o.onCovered) == "function" then
			pcall(o.onCovered)
		end
		task.wait(0.06)
		for _, p in pieces do
			local goal: { [string]: any } = if kind == "slash"
				then { Position = UDim2.fromScale(2.2, 0.5) }
				elseif kind == "blinds" then { Size = UDim2.fromScale(1.02, 0) }
				else { Position = p.open }
			TweenService:Create(p.frame, outInfo, goal):Play()
		end
		task.delay(secs + 0.05, function()
			layer:Destroy()
		end)
	end)
end

-- DATA BINDING + LONG LISTS (v7.15):
--   Ui.set("coins", 1250) / Ui.get("coins")   a client store; every node with "bind": "coins" follows it — a counter
--                                             rolls, a bar takes 0..1, a digit-set number or glyph text re-sets, a label's
--                                             text changes (numbers formatted). A node bound later gets the current value.
--   Ui.list(scroll, items, render, rowHeight)  a VIRTUAL list: only the rows in view exist (a pool recycled as it
--                                             scrolls) — inventories, leaderboards, shops with hundreds of entries.
--                                             render(row: GuiObject, item, index) fills a row; the first child of
--                                             `scroll` is the row template (hidden).
local store: { [string]: any } = {}
local bindings: { [string]: { GuiObject } } = {}

local function applyBound(node: GuiObject, value: any)
	if node:GetAttribute("Kit_Counter") ~= nil and type(value) == "number" then
		Ui.counter(node, value)
	elseif node:GetAttribute("Kit_DigitIds") ~= nil then
		Ui.number(node, tostring(value))
	elseif node:GetAttribute("Kit_GSet") ~= nil then
		Ui.write(node, tostring(value))
	elseif node:FindFirstChild("Fill") and type(value) == "number" then
		Ui.bar(node, math.clamp(value, 0, 1))
	elseif node:IsA("TextLabel") or node:IsA("TextButton") then
		(node :: TextLabel).Text = if type(value) == "number" then formatNumber(value, ",", false) else tostring(value)
	end
end

function Ui.set(key: string, value: any)
	store[key] = value
	local list = bindings[key]
	if not list then
		return
	end
	for i = #list, 1, -1 do
		local node = list[i]
		if node.Parent == nil then
			table.remove(list, i)
		else
			applyBound(node, value)
		end
	end
end

function Ui.get(key: string): any
	return store[key]
end

-- PREFERRED TEXT SIZE (v7, accessibility): a node compiled with "preferredText" (Kit_PreferredText) draws its text at
-- the designed size times the player's own setting (GuiService.PreferredTextSize: Medium .. Largest; UiTextRules, the
-- same factors the compiler checked the box against) and follows the setting live. The designed size is kept in
-- Kit_TextBase so a re-scale never compounds.
local UiTextRules = require(script.Parent:WaitForChild("UiTextRules"))
local prefTexts: { [GuiObject]: boolean } = setmetatable({}, { __mode = "k" }) :: any
local prefWatching = false

local function preferredSetting(): any
	local ok, v = pcall(function()
		return (GuiService :: any).PreferredTextSize
	end)
	return if ok then v else nil
end

local function applyPreferred(gui: GuiObject)
	local base = gui:GetAttribute("Kit_TextBase")
	if type(base) ~= "number" then
		base = (gui :: any).TextSize
		gui:SetAttribute("Kit_TextBase", base)
	end
	pcall(function()
		(gui :: any).TextSize = UiTextRules.scaled(base :: number, preferredSetting())
	end)
end

function Ui.preferredText(gui: GuiObject)
	if not (gui:IsA("TextLabel") or gui:IsA("TextButton") or gui:IsA("TextBox")) then
		return
	end
	prefTexts[gui] = true
	applyPreferred(gui)
	if not prefWatching then
		prefWatching = true
		pcall(function()
			GuiService:GetPropertyChangedSignal("PreferredTextSize" :: any):Connect(function()
				for g in prefTexts do
					if g.Parent then
						applyPreferred(g)
					end
				end
			end)
		end)
	end
end

local function bindData(gui: GuiObject)
	local key = gui:GetAttribute("Kit_Bind")
	if type(key) ~= "string" then
		return
	end
	local list = bindings[key] or {}
	bindings[key] = list
	table.insert(list, gui)
	if store[key] ~= nil then
		applyBound(gui, store[key])
	end
end

function Ui.list(scroll: ScrollingFrame?, items: { any }, render: (GuiObject, any, number) -> (), rowHeight: number?)
	if not scroll then
		return
	end
	local template = scroll:FindFirstChild("Row") :: GuiObject?
	if not template then
		for _, c in scroll:GetChildren() do
			if c:IsA("GuiObject") then
				template = c
				break
			end
		end
	end
	if not template then
		warn(`Ui.list: {scroll:GetFullName()} has no row template (its first child)`)
		return
	end
	local row = template :: GuiObject
	row.Visible = false
	local h = rowHeight or (row.AbsoluteSize.Y > 0 and row.AbsoluteSize.Y or row.Size.Y.Offset)
	scroll.CanvasSize = UDim2.fromOffset(0, h * #items)
	local pool: { GuiObject } = {}
	for _, c in scroll:GetChildren() do
		if c:IsA("GuiObject") and c.Name == "KitRow" then
			table.insert(pool, c)
		end
	end
	local function refresh()
		local top = scroll.CanvasPosition.Y
		local first = math.max(1, math.floor(top / h) + 1)
		local count = math.ceil(scroll.AbsoluteSize.Y / h) + 2
		for i = 1, count do
			local idx = first + i - 1
			local r = pool[i]
			if not r then
				local made = row:Clone()
				made.Name = "KitRow"
				made.Parent = scroll
				pool[i] = made
				r = made
			end
			local item = items[idx]
			if item ~= nil then
				r.Visible = true
				r.Position = UDim2.fromOffset(0, (idx - 1) * h)
				if r:GetAttribute("Kit_ListIndex") ~= idx then
					r:SetAttribute("Kit_ListIndex", idx)
					render(r, item, idx)
				end
			else
				r.Visible = false
			end
		end
		for i = count + 1, #pool do
			pool[i].Visible = false
		end
	end
	scroll:GetPropertyChangedSignal("CanvasPosition"):Connect(refresh)
	scroll:GetPropertyChangedSignal("AbsoluteSize"):Connect(refresh)
	refresh()
end

function Ui.push(feed: GuiObject?, text: string, color: Color3?)
	if not feed then
		return
	end
	local line = Instance.new("TextLabel")
	line.Name = "Line"
	line.BackgroundTransparency = 1
	line.Size = UDim2.new(1, 0, 0, 22)
	local screen = feed:FindFirstAncestorOfClass("ScreenGui")
	local face = screen and screen:GetAttribute("Kit_Font")
	line.Font = Enum.Font.GothamBold
	if type(face) == "string" then
		for _, item in Enum.Font:GetEnumItems() do
			if item.Name == face then
				line.Font = item :: Enum.Font
				break
			end
		end
	end
	line.TextSize = 16
	line.TextXAlignment = Enum.TextXAlignment.Left
	line.TextColor3 = color or Color3.new(1, 1, 1)
	line.RichText = true
	line.Text = text
	line.LayoutOrder = -math.floor(os.clock() * 1000) % 1e9
	local stroke = Instance.new("UIStroke")
	stroke.Transparency = 0.35
	stroke.Parent = line
	line.TextTransparency = 1
	line.Parent = feed
	TweenService:Create(line, QUICK, { TextTransparency = 0 }):Play()
	local max = feed:GetAttribute("KitFeedMax")
	local lines = {}
	for _, c in feed:GetChildren() do
		if c.Name == "Line" then
			table.insert(lines, c)
		end
	end
	table.sort(lines, function(x, y)
		return (x :: GuiObject).LayoutOrder < (y :: GuiObject).LayoutOrder
	end)
	for i = (if type(max) == "number" then max else 5) + 1, #lines do
		lines[i]:Destroy()
	end
	task.delay(5, function()
		if line.Parent then
			local t = TweenService:Create(line, SMOOTH, { TextTransparency = 1 })
			t.Completed:Once(function()
				line:Destroy()
			end)
			t:Play()
		end
	end)
end

-- ------------------------------------------------------------------ fades: every drawn thing under a node
local FADE_PROPS = {
	TextLabel = { "TextTransparency", "TextStrokeTransparency", "BackgroundTransparency" },
	TextButton = { "TextTransparency", "TextStrokeTransparency", "BackgroundTransparency" },
	TextBox = { "TextTransparency", "BackgroundTransparency" },
	ImageLabel = { "ImageTransparency", "BackgroundTransparency" },
	ImageButton = { "ImageTransparency", "BackgroundTransparency" },
	Frame = { "BackgroundTransparency" },
	ScrollingFrame = { "BackgroundTransparency" },
	ViewportFrame = { "ImageTransparency", "BackgroundTransparency" },
	UIStroke = { "Transparency" },
}

local function remember(inst: Instance): { [string]: number }?
	local props = FADE_PROPS[inst.ClassName]
	if not props then
		return nil
	end
	local saved: { [string]: number } = originals[inst]
	if saved == nil then
		local fresh: { [string]: number } = {}
		for _, p in props do
			fresh[p] = (inst :: any)[p]
		end
		originals[inst] = fresh
		saved = fresh
	end
	return saved
end

-- alpha 0 = fully hidden, 1 = as designed; tweened when `ti` is given, else set
local function fadeTree(root: Instance, alpha: number, ti: TweenInfo?)
	if root:IsA("CanvasGroup") then
		local goal = { GroupTransparency = 1 - alpha }
		if ti then
			TweenService:Create(root, ti, goal):Play()
		else
			root.GroupTransparency = goal.GroupTransparency
		end
		return
	end
	local list = root:GetDescendants()
	table.insert(list, 1, root)
	for _, inst in list do
		local saved = remember(inst)
		if saved then
			local goal = {}
			for p, orig in saved do
				goal[p] = 1 - (1 - orig) * alpha
			end
			if ti then
				TweenService:Create(inst, ti, goal):Play()
			else
				for p, v in goal do
					(inst :: any)[p] = v
				end
			end
		end
	end
end

-- ------------------------------------------------------------------ motion: enters, loops, hover, press
local function playEnter(gui: GuiObject, extraDelay: number?)
	local kind = gui:GetAttribute("Motion_enter")
	if type(kind) ~= "string" then
		return
	end
	local delay = num(gui, "Motion_enter_delay", 0) + (extraDelay or 0)
	local duration = num(gui, "Motion_enter_duration", 0.35)
	local ease = gui:GetAttribute("Motion_enter_ease")
	if reducedMotion() then
		kind, duration = "fade", math.min(duration, 0.2) -- (nothing slides, scales or bounces)
	end
	local ti = info(duration, if type(ease) == "string" then ease else "quad", delay)
	local s = scaler(gui)
	-- where the node LIVES as designed: remembered while an enter is in flight, so a replay (a screen shown twice,
	-- a re-enabled screen) still lands home instead of drifting another 24 px or wiping to nothing; once the enter
	-- has settled the live values are the designed ones again (game code may have moved the node since)
	local now = os.clock()
	local existing = homes[gui]
	local busy = playingUntil[gui]
	local home: { pos: UDim2, size: UDim2 }
	if existing and busy and now <= busy then
		home = existing
	else
		home = { pos = gui.Position, size = gui.Size }
		homes[gui] = home
	end
	playingUntil[gui] = now + delay + duration
	if kind == "fade" then
		fadeTree(gui, 0)
		fadeTree(gui, 1, ti)
	elseif kind == "rise" or kind == "drop" or kind == "sweep" then
		local dx, dy = 0, 0
		if kind == "rise" then
			dy = 24
		elseif kind == "drop" then
			dy = -24
		else
			dx = -48
		end
		gui.Position = home.pos + UDim2.fromOffset(dx, dy)
		fadeTree(gui, 0)
		fadeTree(gui, 1, info(duration * 0.7, "sine", delay))
		TweenService:Create(gui, ti, { Position = home.pos }):Play()
	elseif kind == "pop" then
		s.Scale = 0.85
		fadeTree(gui, 0)
		fadeTree(gui, 1, info(duration * 0.5, "quad", delay))
		TweenService:Create(s, info(duration, if type(ease) == "string" then ease else "back", delay), { Scale = 1 })
			:Play()
	elseif kind == "bounce" then
		-- the simulator pop: from small, overshooting past home and settling (elastic unless the spec says)
		s.Scale = 0.6
		fadeTree(gui, 0)
		fadeTree(gui, 1, info(duration * 0.3, "quad", delay))
		TweenService:Create(s, info(duration, if type(ease) == "string" then ease else "elastic", delay), { Scale = 1 })
			:Play()
	elseif kind == "slam" then
		s.Scale = 1.4
		fadeTree(gui, 0)
		fadeTree(gui, 1, info(duration * 0.6, "quad", delay))
		TweenService:Create(s, ti, { Scale = 1 }):Play()
	elseif kind == "swell" then
		s.Scale = 0.96
		fadeTree(gui, 0)
		fadeTree(gui, 1, ti)
		TweenService:Create(s, info(duration, "sine", delay), { Scale = 1.04 }):Play()
	elseif kind == "wipe" then
		local size = home.size
		gui.Size = UDim2.new(0, 0, size.Y.Scale, size.Y.Offset)
		TweenService:Create(gui, ti, { Size = size }):Play()
	elseif kind == "typewriter" then
		local target: Instance = gui:FindFirstChild("Label") or gui
		if target:IsA("TextLabel") or target:IsA("TextButton") then
			local label = target :: TextLabel
			local n = utf8.len(label.Text) or #label.Text
			label.MaxVisibleGraphemes = 0
			local tween = TweenService:Create(label, info(duration, "linear", delay), { MaxVisibleGraphemes = n })
			tween.Completed:Once(function(state: Enum.PlaybackState)
				if state == Enum.PlaybackState.Completed then
					label.MaxVisibleGraphemes = -1 -- (a later, longer Ui.text must not stay cut off)
				end
			end)
			tween:Play()
		end
	end
end

-- the choreography under a node: children with an enter under a staggered container arrive in order
local function playTree(root: Instance, carried: number)
	local stagger = num(root, "Motion_stagger", 0)
	local i = 0
	-- in LayoutOrder (the compiler numbers siblings; GetChildren order is not promised), as the strips are drawn
	local kids = {}
	for _, child in root:GetChildren() do
		if child:IsA("GuiObject") then
			table.insert(kids, child)
		end
	end
	table.sort(kids, function(a, b)
		return a.LayoutOrder < b.LayoutOrder
	end)
	for _, child in kids do
		if child:IsA("GuiObject") then
			local extra = carried
			if child:GetAttribute("Motion_enter") ~= nil then
				if stagger > 0 then
					extra += i * stagger
					i += 1
				end
				playEnter(child, extra)
			end
			playTree(child, 0)
		end
	end
end

function Ui.reveal(node: Instance)
	if node:IsA("GuiObject") and node:GetAttribute("Motion_enter") ~= nil then
		playEnter(node, 0)
	end
	playTree(node, 0)
end

local loops: { [Instance]: RBXScriptConnection } = setmetatable({}, { __mode = "k" }) :: any

local function playLoop(gui: GuiObject)
	local kind = gui:GetAttribute("Motion_loop")
	if type(kind) ~= "string" or reducedMotion() then
		return
	end
	local speed = num(gui, "Motion_loop_speed", 1)
	local s = scaler(gui)
	if kind == "pulse" then
		TweenService:Create(
			s,
			TweenInfo.new(0.8 / speed, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1, true),
			{ Scale = 1.06 }
		):Play()
	elseif kind == "breathe" then
		TweenService:Create(
			s,
			TweenInfo.new(2.4 / speed, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1, true),
			{ Scale = 1.03 }
		):Play()
	elseif kind == "blink" then
		TweenService:Create(
			s,
			TweenInfo.new(0.5 / speed, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1, true),
			{ Scale = 0.96 }
		):Play()
	elseif kind == "spin" then
		TweenService:Create(
			gui,
			TweenInfo.new(2 / speed, Enum.EasingStyle.Linear, Enum.EasingDirection.In, -1),
			{ Rotation = gui.Rotation + 360 }
		):Play()
	elseif kind == "float" then
		-- a pet, an egg, a gift hovering: up and down 6 px, forever
		local home = gui.Position
		gui.Position = home + UDim2.fromOffset(0, 3)
		TweenService:Create(
			gui,
			TweenInfo.new(1.6 / speed, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1, true),
			{ Position = home - UDim2.fromOffset(0, 3) }
		):Play()
	elseif kind == "wobble" then
		-- a notification, a "NEW!" tag rocking: +-6 degrees
		local base = gui.Rotation
		gui.Rotation = base - 6
		TweenService:Create(
			gui,
			TweenInfo.new(0.9 / speed, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1, true),
			{ Rotation = base + 6 }
		):Play()
	elseif kind == "sweep" then
		local grad = gui:FindFirstChildOfClass("UIGradient")
		if grad then
			grad.Offset = Vector2.new(-1, 0)
			TweenService:Create(
				grad,
				TweenInfo.new(2.5 / speed, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1),
				{ Offset = Vector2.new(1, 0) }
			):Play()
		end
	elseif kind == "flicker" then
		-- firelight: a soft random jitter of the drawn alpha (embers, candles, a cursed glow); ends with the gui
		local t = 0
		gui.Destroying:Once(function()
			if loops[gui] then
				loops[gui]:Disconnect()
				loops[gui] = nil
			end
		end)
		loops[gui] = RunService.Heartbeat:Connect(function(dt: number)
			t += dt * speed
			local a = 0.86 + 0.14 * math.noise(t * 3.1, 0.5) + 0.06 * math.noise(t * 11, 2.5)
			fadeTree(gui, math.clamp(a, 0.5, 1))
		end)
	elseif kind == "glint" then
		task.spawn(function()
			while gui.Parent do
				task.wait(3 / speed)
				if gui.Parent then
					local stroke = gui:FindFirstChildOfClass("UIStroke")
					if stroke then
						local base = stroke.Transparency
						stroke.Transparency = 0
						TweenService:Create(stroke, TweenInfo.new(0.6, Enum.EasingStyle.Sine), { Transparency = base })
							:Play()
					else
						Ui.punch(gui, 0.04)
					end
				end
			end
		end)
	end
end

local bound = setmetatable({}, { __mode = "k" })
local canvasWarned: { [Instance]: boolean } = setmetatable({}, { __mode = "k" }) :: any

function Ui.bind(gui: Instance)
	if bound[gui] or not gui:IsA("GuiObject") then
		return
	end
	-- VRAM (V4 UI-X 6.4): the compiler refuses a CanvasGroup inside another; one a game script nests is said here,
	-- once (each renders its whole tree into a texture of its own: the inner tree drawn twice)
	if gui:IsA("CanvasGroup") and not canvasWarned[gui] then
		local outer = gui:FindFirstAncestorWhichIsA("CanvasGroup")
		if outer then
			canvasWarned[gui] = true
			warn(
				`[kit Ui] {gui:GetFullName()} is a CanvasGroup inside the CanvasGroup {outer:GetFullName()}: two textures, the inner tree drawn twice - make one a Frame`
			)
		end
	end
	local hover, press, loop =
		gui:GetAttribute("Motion_hover"), gui:GetAttribute("Motion_press"), gui:GetAttribute("Motion_loop")
	local hasEnter = gui:GetAttribute("Motion_enter") ~= nil
	local model = gui:GetAttribute("Kit_Model")
	local flip = gui:GetAttribute("Kit_Flip") ~= nil and gui:GetAttribute("Kit_FlipPlay") ~= "manual"
	local fx = gui:GetAttribute("Kit_Fx") ~= nil
	local states = gui:GetAttribute("Kit_States") ~= nil
	local vector = gui:GetAttribute("Kit_Path") ~= nil
	local burst = gui:GetAttribute("Kit_BurstOn") ~= nil
	local glyphMotion = gui:GetAttribute("Kit_GFx") ~= nil
	local compass = gui:GetAttribute("Kit_Compass") ~= nil
	local tipped = gui:GetAttribute("Kit_Tip") ~= nil
	local dataBound = gui:GetAttribute("Kit_Bind") ~= nil
	local preferred = gui:GetAttribute("Kit_PreferredText") == true
	local sounds = gui:GetAttribute("Kit_Snd_hover") ~= nil
		or gui:GetAttribute("Kit_Snd_press") ~= nil
		or gui:GetAttribute("Kit_Snd_show") ~= nil
		or gui:GetAttribute("Kit_Snd_enter") ~= nil
		or gui:GetAttribute("Kit_Hap_press") ~= nil
		or gui:GetAttribute("Kit_Hap_hover") ~= nil
	if
		not (
			hover
			or press
			or loop
			or hasEnter
			or flip
			or fx
			or states
			or vector
			or burst
			or glyphMotion
			or compass
			or tipped
			or dataBound
			or preferred
			or sounds
			or (type(model) == "string" and model ~= "")
		)
	then
		return
	end
	if preferred then
		Ui.preferredText(gui) -- (its text follows the player's own text size)
	end
	if vector then
		bindPath(gui :: GuiObject) -- (its Path2D built; a "draw" key strokes it on)
	end
	if burst then
		bindBurst(gui :: GuiObject) -- (its particle burst flies when it shows)
	end
	if glyphMotion then
		bindGlyphFx(gui :: GuiObject) -- (a glyph-text label's wave / shake)
	end
	if compass then
		bindCompass(gui :: GuiObject) -- (the strip follows the camera's heading)
	end
	if tipped then
		bindTip(gui :: GuiObject) -- (its tooltip on hover / gamepad selection)
	end
	if dataBound then
		bindData(gui :: GuiObject) -- (it follows Ui.set of its key)
	end
	if sounds then
		bindSounds(gui :: GuiObject) -- (hover / press / show / the enter as it lands)
	end
	if states then
		bindStates(gui :: GuiObject) -- (hover / pressed looks, under a sticky selected / disabled / locked / new)
	end
	if flip then
		Ui.flipbook(gui :: GuiObject) -- ("play": "auto": it runs from the moment the screen is bound)
	end
	if fx then
		Ui.fx(gui :: GuiObject) -- (shimmer / ping / split / flicker loop from here; a burn_in plays once)
		if string.find(tostring(gui:GetAttribute("Kit_Fx")), "burn_in:", 1, true) then
			onOpen(gui :: GuiObject, function()
				Ui.fx(gui :: GuiObject, "burn_in") -- (again each time the screen opens: the player sees it)
			end)
		end
	end
	bound[gui] = true
	local s = scaler(gui)
	local stroke = gui:FindFirstChildOfClass("UIStroke")
	local strokeBase = stroke and stroke.Transparency
	local plate = gui:FindFirstChild("Plate")
	local plateBase = if plate and plate:IsA("ImageLabel") then plate.ImageTransparency else nil
	if hover then
		gui.MouseEnter:Connect(function()
			if hover == "glow" and stroke then
				TweenService:Create(stroke, QUICK, { Transparency = 0 }):Play()
			end
			if (hover == "glow" or hover == "brighten") and plate and plate:IsA("ImageLabel") then
				TweenService:Create(plate, SMOOTH, { ImageTransparency = 0 }):Play()
			end
			local target = if hover == "grow" then 1.08 elseif hover == "lift" then 1.04 else 1.015
			Ui.spring(s, "Scale", target, 6, 0.7)
		end)
		gui.MouseLeave:Connect(function()
			if stroke and strokeBase then
				TweenService:Create(stroke, QUICK, { Transparency = strokeBase }):Play()
			end
			if plate and plate:IsA("ImageLabel") and plateBase then
				TweenService:Create(plate, SMOOTH, { ImageTransparency = plateBase }):Play()
			end
			Ui.spring(s, "Scale", 1, 6, 0.9)
		end)
	end
	if press and gui:IsA("GuiButton") then
		gui.MouseButton1Down:Connect(function()
			Ui.spring(s, "Scale", if press == "flash" then 0.97 else 0.94, 10, 1)
			if press == "flash" and stroke then
				stroke.Transparency = 0
			end
		end)
		gui.MouseButton1Up:Connect(function()
			Ui.spring(s, "Scale", 1, 5, 0.55)
			if press == "flash" and stroke and strokeBase then
				TweenService:Create(stroke, SMOOTH, { Transparency = strokeBase }):Play()
			end
		end)
	end
	if loop then
		playLoop(gui)
	end
	if gui:IsA("ViewportFrame") and type(model) == "string" and model ~= "" then
		Ui.model(gui, model)
	end
	if hasEnter then
		gui:GetPropertyChangedSignal("Visible"):Connect(function()
			if (gui :: GuiObject).Visible and gui:GetAttribute("Kit_NoEnter") == nil then
				playEnter(gui :: GuiObject, 0)
			end
		end)
	end
end

-- ------------------------------------------------------------------ screens: scale, show, transition, 3D
local VIEWPORTS: { { name: string, below: number } } =
	{ { name = "phone", below = 900 }, { name = "tablet", below = 1300 } }

-- "at" overrides (the compiler's Kit_At_<viewport> attributes): the designed values are kept the first time, put
-- back when the viewport changes, then the viewport's own size / position / text size / visibility applied
local atDesigned: { [GuiObject]: { [string]: any } } = setmetatable({}, { __mode = "k" }) :: any
local atApplied: { [GuiObject]: { [string]: any } } = setmetatable({}, { __mode = "k" }) :: any

local function parseAt(text: string): { [string]: any }
	local out: { [string]: any } = {}
	for item in string.gmatch(text, "[^|]+") do
		local key, val = string.match(item, "^(%w+)=(.*)$")
		if not key or not val then
			continue
		end
		if key == "Size" or key == "Position" then
			local a, b, c, d = string.match(val, "^([^,]+),([^,]+),([^,]+),([^,]+)$")
			if a then
				out[key] = UDim2.new(tonumber(a) or 0, tonumber(b) or 0, tonumber(c) or 0, tonumber(d) or 0)
			end
		elseif key == "TextSize" then
			out.TextSize = tonumber(val)
		elseif key == "Visible" then
			out.Visible = val == "true"
		elseif key == "Anchor" then
			local a, b = string.match(val, "^([^,]+),([^,]+)$")
			if a then
				out.AnchorPoint = Vector2.new(tonumber(a) or 0, tonumber(b) or 0)
			end
		end
	end
	return out
end

local function applyAt(screen: ScreenGui, label: string)
	for _, d in screen:GetDescendants() do
		if not d:IsA("GuiObject") then
			continue
		end
		local has = false
		for _, vp in { "phone", "tablet", "desktop" } do
			if d:GetAttribute("Kit_At_" .. vp) ~= nil then
				has = true
				break
			end
		end
		if not has then
			continue
		end
		local designed: { [string]: any } = atDesigned[d]
		if designed == nil then
			local fresh: { [string]: any } =
				{ Size = d.Size, Position = d.Position, Visible = d.Visible, AnchorPoint = d.AnchorPoint }
			if d:IsA("TextLabel") or d:IsA("TextButton") or d:IsA("TextBox") then
				fresh.TextSize = (d :: TextLabel).TextSize
			end
			atDesigned[d] = fresh
			designed = fresh
		end
		-- only the properties some viewport's override names are the kit's to set; one the GAME changed since the kit
		-- last set it (a node it hid) becomes the designed value — showing a screen no longer brings back what the game
		-- hid (audit 2026-10-16)
		local anyD: any = d
		local touched: { [string]: boolean } = {}
		for _, vp in { "phone", "tablet", "desktop" } do
			local o = d:GetAttribute("Kit_At_" .. vp)
			if type(o) == "string" then
				for k in parseAt(o) do
					touched[k] = true
				end
			end
		end
		local last = atApplied[d]
		if last then
			for k, v in last do
				if anyD[k] ~= v then
					designed[k] = anyD[k]
				end
			end
		end
		local target: { [string]: any } = {}
		for k in touched do
			target[k] = designed[k]
		end
		local over = d:GetAttribute("Kit_At_" .. label)
		if type(over) == "string" then
			for k, v in parseAt(over) do
				target[k] = v
			end
		end
		local applied: { [string]: any } = {}
		for k, v in target do
			if v ~= nil and (k ~= "TextSize" or d:IsA("TextLabel") or d:IsA("TextButton") or d:IsA("TextBox")) then
				anyD[k] = v
				applied[k] = v
			end
		end
		atApplied[d] = applied
		homes[d] = nil -- (the next enter reads the viewport's home)
	end
end

function Ui.scale(screen: ScreenGui)
	local camera = workspace.CurrentCamera
	if not camera then
		return
	end
	local width = camera.ViewportSize.X
	local label = "desktop"
	for _, v in VIEWPORTS do
		if width < v.below then
			label = v.name
			break
		end
	end
	local forced = Ui.forceViewport
	if forced == "phone" or forced == "tablet" or forced == "desktop" then
		label = forced -- (QA in Studio: see the phone layout at any window size)
	end
	local s = screen:GetAttribute("Kit_Scale_" .. label)
	local root = screen:FindFirstChildWhichIsA("GuiObject")
	if not root then
		return
	end
	local scale = if type(s) == "number" then s else 1
	-- the desktop layout is authored at 1920 x 1080: a smaller desktop window (a 1366 x 768 laptop, a docked Studio
	-- view) gets it scaled down to FIT instead of clipped off the bottom (ui_storybook: Arcade5Menu's last row sat at
	-- y 718 in a 661 px view). At 1080p and above nothing changes
	if label == "desktop" and type(s) ~= "number" then
		local vs = camera.ViewportSize
		if vs.X > 0 and vs.Y > 0 then
			scale = math.min(1, vs.X / 1920, vs.Y / 1080)
		end
	end
	local found = root:FindFirstChild("KitViewportScale")
	local ui: UIScale
	if found and found:IsA("UIScale") then
		ui = found
	else
		ui = Instance.new("UIScale")
		ui.Name = "KitViewportScale"
		ui.Parent = root
	end
	ui.Scale = scale
	applyAt(screen, label)
	-- a full-screen root sized 1/s under a UIScale s still covers the screen; its pixel offsets shrink
	local wasFull = root.Size.X.Scale > 0.99 and root.Size.Y.Scale > 0.99
	local prev = homes[root]
	if wasFull or (prev and prev.size.X.Scale > 0.99 and prev.size.Y.Scale > 0.99) then
		root.Size = UDim2.fromScale(1 / scale, 1 / scale)
		if prev then
			prev.size = root.Size -- (a root that wipes in lands on the new size)
		end
	end
end

-- every picture a screen can show — its images, a number's glyph cells (Kit_DigitIds), a flipbook's frames
-- (Kit_Flip) — fetched before the screen is seen. The engine streams assets in as they arrive, and the booth's first
-- capture showed StriveDuel popping in piece by piece (text at 0 s, words 0.8 s, blades 1.6 s). Yields up to
-- `timeout` seconds (default 5); returns how many were asked for.
local preloaded: { [Instance]: boolean } = setmetatable({}, { __mode = "k" }) :: any

function Ui.preload(screen: Instance, timeout: number?): number
	if preloaded[screen] then
		return 0
	end
	preloaded[screen] = true
	local ids: { string } = {}
	local seen: { [string]: boolean } = {}
	local function add(id: any)
		if type(id) == "string" and id ~= "" and not seen[id] then
			seen[id] = true
			table.insert(ids, id)
		end
	end
	for _, d in screen:GetDescendants() do
		if d:IsA("ImageLabel") or d:IsA("ImageButton") then
			add((d :: ImageLabel).Image)
		end
		for pair in string.gmatch(tostring(d:GetAttribute("Kit_DigitIds") or ""), "[^;]+") do
			add(string.match(pair, "^.-=(.*)$"))
		end
		for id in string.gmatch(tostring(d:GetAttribute("Kit_Flip") or ""), "[^;]+") do
			add(id)
		end
	end
	if #ids == 0 then
		return 0
	end
	local ContentProvider = game:GetService("ContentProvider")
	local done = false
	task.spawn(function()
		pcall(function()
			ContentProvider:PreloadAsync(ids)
		end)
		done = true
	end)
	local t0 = os.clock()
	while not done and os.clock() - t0 < (timeout or 5) do
		task.wait(0.05)
	end
	-- WARM the hidden pictures: a fetched image the engine has never drawn appears 0.15-0.6 s after it is first made
	-- visible (measured in the booth 2026-10-16: LET'S ROCK landed a beat late). On a shown screen, each hidden image
	-- is drawn for two frames at 0.99 transparency (invisible to the player), then put back as it was.
	if screen:IsA("ScreenGui") and screen.Enabled then
		local warmed: { { inst: GuiObject, visible: boolean, alpha: number, hidden: { GuiObject } } } = {}
		for _, d in screen:GetDescendants() do
			if (d:IsA("ImageLabel") or d:IsA("ImageButton")) and (d :: ImageLabel).Image ~= "" then
				local hidden: { GuiObject } = {}
				local node: Instance? = d
				while node and node ~= screen do
					if node:IsA("GuiObject") and not node.Visible then
						table.insert(hidden, node)
					end
					node = node.Parent
				end
				if #hidden > 0 then
					local img = d :: ImageLabel
					table.insert(warmed, {
						inst = img :: GuiObject,
						visible = img.Visible,
						alpha = img.ImageTransparency,
						hidden = hidden,
					})
				end
			end
		end
		local opened: { [GuiObject]: boolean } = {}
		for _, w in warmed do
			(w.inst :: ImageLabel).ImageTransparency = 0.99
			for _, h in w.hidden do
				if opened[h] == nil then -- (recorded once: a second picture under it must not record the opened state)
					opened[h] = h.Visible
					h.Visible = true
				end
			end
		end
		if #warmed > 0 then
			local RunServiceLocal = game:GetService("RunService")
			RunServiceLocal.RenderStepped:Wait()
			RunServiceLocal.RenderStepped:Wait()
			for _, w in warmed do
				(w.inst :: ImageLabel).ImageTransparency = w.alpha
			end
			for h, was in opened do
				h.Visible = was
			end
		end
	end
	return #ids
end

function Ui.show(screen: ScreenGui, on: boolean)
	showGen[screen] = (showGen[screen] or 0) + 1
	local gen = showGen[screen]
	if on then
		if screen.Enabled then
			-- shown while still shown (or inside its own fade-out): bring everything back and replay the choreography
			-- (a tween, not a set: it cancels the fade-out's tweens still in flight on nodes that get no enter)
			for _, d in screen:GetChildren() do
				if d:IsA("GuiObject") then
					fadeTree(d, 1, QUICK)
				end
			end
			Ui.scale(screen)
			playTree(screen, 0)
			return
		end
		-- with the UiMotion client running, flipping Enabled is what plays the enters (once, there, not twice here);
		-- without it (a server-side test, a place with no client script) this call plays them
		screen.Enabled = true
		if not Ui.clientBound then
			Ui.scale(screen)
			playTree(screen, 0)
		end
	else
		for _, d in screen:GetChildren() do
			if d:IsA("GuiObject") then
				fadeTree(d, 0, SMOOTH)
			end
		end
		task.delay(0.25, function()
			if showGen[screen] ~= gen then
				return -- shown again in the meantime: leave it
			end
			screen.Enabled = false
			for _, d in screen:GetChildren() do
				if d:IsA("GuiObject") then
					fadeTree(d, 1)
				end
			end
		end)
	end
end

function Ui.transition(from: ScreenGui?, to: ScreenGui?)
	if from then
		Ui.show(from, false)
	end
	if to then
		task.delay(if from then 0.25 else 0, function()
			Ui.show(to, true)
		end)
	end
end

-- FLOWS (kit ui flow films assets/ui/flows/<Flow>.json): Ui.go(from, to, {transition = "fade" | "push" | "shared",
-- shared = {a, b}, seconds = 0.5}) moves the player between screens the way the flow says. "shared": a copy of piece
-- `a` (on the screen being left) is THROWN on an arc into the place of piece `b` (on the screen arriving), which
-- shows only when it lands — one object travelling, not two screens swapping. Reduced motion: a plain swap.
local goToken: { [GuiObject]: number } = setmetatable({}, { __mode = "k" }) :: any
local goHome: { [GuiObject]: boolean } = setmetatable({}, { __mode = "k" }) :: any

function Ui.go(from: ScreenGui?, to: ScreenGui?, opts: { [string]: any }?)
	local o: { [string]: any } = opts or {}
	local secs = tonumber(o.seconds) or 0.5
	local shared = o.shared
	local a: GuiObject? = shared and shared[1]
	local b: GuiObject? = shared and shared[2]
	if o.transition ~= "shared" or reducedMotion() or not (a and b and to) then
		Ui.transition(from, to)
		return
	end
	local layer = Instance.new("ScreenGui")
	layer.Name = "KitFlowLayer"
	layer.DisplayOrder = 1000
	layer.ScreenInsets = (to :: ScreenGui).ScreenInsets -- (the same frame of reference as the screens it flies between)
	layer.ResetOnSpawn = false
	layer.Parent = (to :: ScreenGui).Parent
	local flyer = (a :: GuiObject):Clone()
	for _, s0 in flyer:GetDescendants() do
		if s0:IsA("LuaSourceContainer") then
			s0:Destroy()
		end
	end
	local a0, s0 = (a :: GuiObject).AbsolutePosition, (a :: GuiObject).AbsoluteSize
	flyer.AnchorPoint = Vector2.zero
	flyer.Rotation = 0
	flyer.Position = UDim2.fromOffset(a0.X, a0.Y)
	flyer.Size = UDim2.fromOffset(s0.X, s0.Y)
	flyer.Parent = layer
	goToken[b :: GuiObject] = (goToken[b :: GuiObject] or 0) + 1
	local myToken = goToken[b :: GuiObject]
	if goHome[b :: GuiObject] == nil then
		goHome[b :: GuiObject] = (b :: GuiObject).Visible -- (its designed visibility: a second quick Ui.go keeps it)
	end
	local bVisible = goHome[b :: GuiObject] :: boolean
	if from then
		Ui.show(from, false)
	end
	Ui.show(to, true)
	local target = b :: GuiObject
	target:SetAttribute("Kit_NoEnter", true) -- (hidden + shown again here is not an entrance to replay)
	target.Visible = false
	task.spawn(function()
		RunService.Heartbeat:Wait() -- (the arriving screen laid out: b's place is known)
		local b0, bs = (b :: GuiObject).AbsolutePosition, (b :: GuiObject).AbsoluteSize
		local t0 = os.clock()
		while true do
			local k = math.clamp((os.clock() - t0) / secs, 0, 1)
			local e = 1 - (1 - k) ^ 3
			local p = a0:Lerp(b0, e) - Vector2.new(0, math.sin(math.pi * e) * 120)
			local sz = s0:Lerp(bs, e)
			flyer.Position = UDim2.fromOffset(p.X, p.Y)
			flyer.Size = UDim2.fromOffset(sz.X, sz.Y)
			if k >= 1 then
				break
			end
			RunService.Heartbeat:Wait()
		end
		layer:Destroy()
		if goToken[b :: GuiObject] ~= myToken then
			return -- (a newer Ui.go owns b now)
		end
		goHome[b :: GuiObject] = nil
		(b :: GuiObject).Visible = bVisible
		task.defer(function()
			(b :: GuiObject):SetAttribute("Kit_NoEnter", nil)
		end)
	end)
end

-- a kit model (ReplicatedStorage.KitModels.<name>) inside a viewport node, lit, slowly turning when spin > 0
function Ui.model(viewport: ViewportFrame, name: string)
	local models = ReplicatedStorage:FindFirstChild("KitModels")
	local source = models and models:FindFirstChild(name)
	if not source then
		return
	end
	for _, c in viewport:GetChildren() do
		if c:IsA("Model") or c:IsA("BasePart") or c:IsA("Camera") then
			c:Destroy()
		end
	end
	local clone = source:Clone()
	clone.Parent = viewport
	local cf, size
	if clone:IsA("Model") then
		cf, size = clone:GetBoundingBox()
	else
		cf, size = (clone :: BasePart).CFrame, (clone :: BasePart).Size
	end
	local camera = Instance.new("Camera")
	camera.FieldOfView = 30
	local dist = size.Magnitude * 1.9
	camera.CFrame = CFrame.new(cf.Position + Vector3.new(0.6, 0.35, 1).Unit * dist, cf.Position)
	camera.Parent = viewport
	viewport.CurrentCamera = camera
	local spin = num(viewport, "Kit_ModelSpin", 0)
	if loops[viewport] then
		loops[viewport]:Disconnect() -- (a model swapped in twice spins once)
		loops[viewport] = nil
	end
	viewport.Destroying:Once(function()
		if loops[viewport] then
			loops[viewport]:Disconnect()
			loops[viewport] = nil
		end
	end)
	local angle, held, heldFrom = 0, false, 0
	local function aim()
		camera.CFrame =
			CFrame.new(cf.Position + (CFrame.Angles(0, angle, 0) * Vector3.new(0.6, 0.35, 1)).Unit * dist, cf.Position)
	end
	-- "drag": the player turns it (a UIDragDetector reporting a custom offset: the viewport itself stays put)
	local oldTurn = viewport:FindFirstChild("KitTurn")
	if oldTurn then
		oldTurn:Destroy() -- (a swapped-in model: the old detector drove the old camera)
	end
	if viewport:GetAttribute("Kit_ModelDrag") == true then
		local det = Instance.new("UIDragDetector")
		det.Name = "KitTurn"
		det.ResponseStyle = Enum.UIDragDetectorResponseStyle.CustomOffset
		det.Parent = viewport
		local fromX = 0
		det.DragStart:Connect(function()
			held, heldFrom, fromX = true, angle, det.DragUDim2.X.Offset -- (the turn is the change since THIS drag began)
		end)
		det.DragContinue:Connect(function()
			angle = heldFrom - math.rad((det.DragUDim2.X.Offset - fromX) * 0.6)
			aim()
		end)
		det.DragEnd:Connect(function()
			held = false
		end)
	end
	if spin > 0 then
		loops[viewport] = RunService.Heartbeat:Connect(function(dt: number)
			if not held then
				angle += dt * spin
				aim()
			end
		end)
	end
end

-- ---------------------------------------------------------------- focus, flex, localization at run time (UI-X Step 7)
-- What kit/lib/ui.luau compiles from a spec ("focus", "flex", "localize"), for a screen made or changed in code.
local EDGES = { stop = Enum.SelectionBehavior.Stop, escape = Enum.SelectionBehavior.Escape }

-- Ui.focusGroup(frame, edge?) -> frame: the gamepad / keyboard cursor stays among `frame`'s children while it is inside
-- (SelectionGroup); edge = "stop" | "escape" for all four sides, or { up = ..., down = ..., left = ..., right = ... }
function Ui.focusGroup(frame: GuiObject, edge: (string | { [string]: string })?): GuiObject
	frame.SelectionGroup = true
	local target: any = frame -- (SelectionBehaviorUp / Down / Left / Right, set by name)
	for _, side in { "Up", "Down", "Left", "Right" } do
		local want = if type(edge) == "table" then edge[string.lower(side)] else edge
		if want ~= nil then
			local e = EDGES[want :: string]
			assert(e, `Ui.focusGroup: edge {side} is "stop" or "escape", not {tostring(want)}`)
			target["SelectionBehavior" .. side] = e
		end
	end
	return frame
end

-- Ui.wrap(layout, on?) -> layout: a UIListLayout whose items run onto the next line when the line is full (Wraps) -
-- a row of chips, cards or slots that reflows from phone to desktop instead of overflowing
function Ui.wrap(layout: UIListLayout, on: boolean?): UIListLayout
	layout.Wraps = on ~= false
	return layout
end

-- Ui.flex(item, mode) -> UIFlexItem: `item` grows / shrinks in its parent's list (a UIListLayout sibling). mode:
-- "grow" | "shrink" | "fill" | { grow = 2, shrink = 1, align = "start" | "center" | "end" | "stretch" | "auto" }
local FLEX_ALIGN = {
	start = Enum.ItemLineAlignment.Start,
	center = Enum.ItemLineAlignment.Center,
	["end"] = Enum.ItemLineAlignment.End,
	stretch = Enum.ItemLineAlignment.Stretch,
	auto = Enum.ItemLineAlignment.Automatic,
}
function Ui.flex(item: GuiObject, mode: string | { [string]: any }): UIFlexItem
	local f = item:FindFirstChildOfClass("UIFlexItem") or Instance.new("UIFlexItem")
	if mode == "grow" then
		f.FlexMode = Enum.UIFlexMode.Grow
	elseif mode == "shrink" then
		f.FlexMode = Enum.UIFlexMode.Shrink
	elseif mode == "fill" then
		f.FlexMode = Enum.UIFlexMode.Fill
	elseif type(mode) == "table" then
		f.FlexMode = Enum.UIFlexMode.Custom
		f.GrowRatio = math.max(0, tonumber(mode.grow) or 0)
		f.ShrinkRatio = math.max(0, tonumber(mode.shrink) or 0)
		if mode.align ~= nil then
			local a = FLEX_ALIGN[mode.align]
			assert(a, `Ui.flex: align is start | center | end | stretch | auto, not {tostring(mode.align)}`)
			f.ItemLineAlignment = a
		end
	else
		error(`Ui.flex: mode is "grow" | "shrink" | "fill" | a table, not {tostring(mode)}`)
	end
	f.Parent = item
	return f
end

-- Ui.localize(root, on) -> root: whether `root` and what it holds are machine-translated (AutoLocalize; on by default)
-- - off for a player's name, a number, a code
function Ui.localize(root: GuiObject | LayerCollector, on: boolean): Instance
	(root :: any).AutoLocalize = on
	return root
end

return Ui

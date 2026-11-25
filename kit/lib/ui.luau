-- ui.luau — compile assets/ui/<Name>.json (high-level screen spec) into a Rojo model (src/ui/<Name>.model.json).
-- Pure Luau (runs in Lune). Good game UI is not "rectangles with text": it is a design system (a skin), lit
-- surfaces (gradients + strokes), conventions (where HUD things go), ready components, real art and motion.
-- This compiler carries all of that so any model can produce it.
--
-- {
--   "name": "Hud", "enabled": true, "kind": "hud" | "menu" (inferred: HUD components present -> hud),
--   "skin": "scifi" | "clean" | "military" | "cartoon",           design tokens (colours, fonts, radii) — pick one
--   "theme": { "accent": "#ff8a3d", ... },                          override any token (colours by name below)
--   "root": node
-- }
-- node = {
--   "type": panel | label | button | image | imagebutton | scroll | bar | input | canvas   (canvas = CanvasGroup)
--         | crosshair | hitmarker | ring | scope | keyhint | ammo | feed | vignette       (components, see below)
--   "name": "Unique",
--   "slot": "topLeft|top|topRight|left|center|right|bottomLeft|bottom|bottomRight"   (HUD conventions: anchor +
--           safe margins in one word; topLeft clears the Roblox menu buttons) — OR "size"/"pos"/"anchor":
--   "size": [w, h], "pos": [x, y]   numbers = pixels, "50%" = of the parent, "100%-24" = far edge minus 24 px
--   "anchor": center|top|bottom|left|right|topleft|topright|bottomleft|bottomright
--   "style": "card" | "glass" | "primary" | "secondary" | "chip" | "ghost"   (lit, finished looks from the skin)
--   "color": token|#hex (background), "transparency": 0..1, "gradient": {"from","to","rot"} | "auto" (lit panel)
--   "radius": px | "s"|"m"|"l"|"pill", "stroke": token|#hex, "strokeWidth": 1.5, "strokeAlpha": 0..1,
--   "strokeGradient": [c1, c2] (glowing edge), "padding": 12,
--   "layout": { "dir": "vertical|horizontal", "gap": 8, "align": "center|start|end" } | { "grid": [w, h], "gap": 8 },
--   "aspect": 1.5, "rotation": deg, "z": zindex, "clip": true, "visible": false,
--   "focus": {"group": true, "edge": "stop"|"escape"|{"up": ..}} (the pad cursor in this frame), "localize": false,
--   text: "text", "textSize": 18, "font": GothamBold..., "textColor": token, "align": left|center|right,
--         "rich": true (<b>, <font color="#..">), "textOutline": token|#hex (+ "textOutlineWidth": 2),
--         "textGradient": [c1, c2], "role": "title" | "body" | "hint" (sizes + fonts from the skin)
--   image: "image": "art:ring" (kit art, kit/ui/art.py) | "rbxassetid://..", "imageColor": token, "imageAlpha": 0..1,
--          "fit": "fit|crop|stretch", "slice": [l, t, r, b] (9-slice; art pieces bring their own)
--   bar: "value": 0..1, "fill": token, "fillGradient": [c1, c2]
--   "motion": { "hover": "lift|grow|glow", "press": "sink", "enter": "fade|rise|pop", "loop": "pulse|spin|blink" }
--             (attributes read by the kit's UiMotion client: no code needed)
--   "attributes": { "Key": value },  "children": [ node ... ]
--   "lettering": true | {size, seed, scale, name, style, caps, outline, rim_px, shadow, shadow_color, wobble, ...}
--          (label / button) the text is display lettering baked by the `kit ui` words step (kit/ui/words.py) into
--          art:<identity>/w_<slug>, the identity's "lettering" block as defaults; the text stays as Kit_Text
--   "at": { "phone": { "scale": 0.5, "size", "pos", "anchor", "textSize", "visible" }, "tablet": {...} }
--          scale shrinks the node AND everything inside it on that viewport (baked art keeps desktop pixels)
-- }
-- Components: crosshair {style: cross|dot|chevron, size, gap, thickness} · hitmarker {size} (hidden; Ui.flash) ·
--   ring {size, value, thickness} (radial cooldown; Ui.ring(node, v)) · scope {reticleColor} (full-screen sniper
--   scope: lens mask + mil-dot reticle + black sides; children go on top) · keyhint {key, text} ·
--   ammo {value, reserve} · feed {max} (kill feed / toasts; Ui.push(feed, text)) · vignette {alpha}
-- Checks: names, types, fonts, colours, WCAG contrast (error < 3, warn < 4.5), touch targets ≥ 44 px, text sizes,
--   flat panels (a big solid fill with no gradient/stroke/image), type hierarchy (one title clearly bigger),
--   things blocking the screen centre on a HUD, art not uploaded yet.
-- LIMITATIONS_FIXES_V4 UI-X (v7 layout + access): "layout": {"flex": "fill|between|around|evenly", "lineAlign":
--   "start|center|end|stretch"} on a list -> UIListLayout HorizontalFlex / VerticalFlex + ItemLineAlignment;
--   "flex": "grow|shrink|fill" | {"grow": 2, "shrink": 1, "align": "center"} on a child of a list -> UIFlexItem
--   (a flex item with no list layout above it, or inside a grid, is an error: the engine ignores it);
--   "preferredText": true (a node, or the whole spec) -> the text follows the player's own text size
--   (GuiService.PreferredTextSize, kit Ui scales it; UiTextRules) and must still fit its box at Largest (an error);
--   WCAG 1.4.11 non-text contrast: a bar's fill against its track under 3:1 is a warning (a genre's dark meter may
--   be meant: the owner's eye decides; text under 3:1 stays the error above).
local UiTextRules = require("../../src/kit/UiTextRules")

local UI = {}

export type Issue = { path: string, message: string, severity: string }

local TYPES = {
	panel = "Frame",
	label = "TextLabel",
	button = "TextButton",
	image = "ImageLabel",
	scroll = "ScrollingFrame",
	bar = "Frame", -- the node is the track; child "Fill" scales with "value" (0..1)
	input = "TextBox",
	imagebutton = "ImageButton",
	canvas = "CanvasGroup",
	viewport = "ViewportFrame", -- a 3D model inside the screen (Kit_Model names it; the Ui runtime fills it)
	path = "Frame", -- a vector line (Path2D, built by the Ui runtime from Kit_Path)
}
-- identity-made nodes (resolved inside compile: they need the identity's plates) and label variants
local PLATE_TYPES = { plate = true, divider = true, texture = true }
local COMPONENTS = {
	crosshair = true,
	hitmarker = true,
	ring = true,
	scope = true,
	keyhint = true,
	marker = true,
	compass = true,
	damage = true,
	toasts = true,
	tooltip = true,
	ammo = true,
	feed = true,
	vignette = true,
	ladder = true,
}
local TYPE_LIST = "panel | label | button | image | imagebutton | scroll | bar | input | canvas | viewport | path | plate | "
	.. "divider | texture | counter | stat | crosshair | hitmarker | ring | scope | keyhint | ammo | feed | vignette | marker | compass | damage | toasts | tooltip | ladder"
-- every Enum.Font the engine ships (the preview draws each with its real face or its nearest free twin: kit/ui/fonts.json)
local FONTS = {}
for _, f in
	{
		"Legacy",
		"Arial",
		"ArialBold",
		"SourceSans",
		"SourceSansBold",
		"SourceSansLight",
		"SourceSansItalic",
		"SourceSansSemibold",
		"Bodoni",
		"Garamond",
		"Cartoon",
		"Code",
		"Highway",
		"SciFi",
		"Arcade",
		"Fantasy",
		"Antique",
		"Gotham",
		"GothamMedium",
		"GothamBold",
		"GothamBlack",
		"AmaticSC",
		"Bangers",
		"Creepster",
		"DenkOne",
		"Fondamento",
		"FredokaOne",
		"GrenzeGotisch",
		"IndieFlower",
		"JosefinSans",
		"Jura",
		"Kalam",
		"LuckiestGuy",
		"Merriweather",
		"Michroma",
		"Nunito",
		"Oswald",
		"PatrickHand",
		"PermanentMarker",
		"Roboto",
		"RobotoCondensed",
		"RobotoMono",
		"Sarpanch",
		"SpecialElite",
		"TitilliumWeb",
		"Ubuntu",
		"BuilderSans",
		"BuilderSansMedium",
		"BuilderSansBold",
		"BuilderSansExtraBold",
		"Arimo",
		"ArimoBold",
	}
do
	FONTS[f] = true
end
UI.FONTS = FONTS
-- the faces a model reaches for by habit: fine without an identity, a warning under one (the identity chose its type)
local DEFAULT_FACES = {
	Gotham = true,
	GothamMedium = true,
	GothamBold = true,
	GothamBlack = true,
	Arial = true,
	ArialBold = true,
	SourceSans = true,
	SourceSansBold = true,
	Roboto = true,
	BuilderSans = true,
	BuilderSansBold = true,
}
-- how a screen enters, lives and reacts (motion v2: choreographed, played by src/kit/Ui.luau)
local ENTERS = {
	fade = true,
	rise = true,
	pop = true,
	bounce = true,
	slam = true,
	swell = true,
	drop = true,
	wipe = true,
	sweep = true,
	typewriter = true,
}
local LOOPS = {
	pulse = true,
	spin = true,
	blink = true,
	breathe = true,
	flicker = true,
	sweep = true,
	glint = true,
	float = true,
	wobble = true,
}
local EASES = { quad = true, sine = true, back = true, expo = true, linear = true, elastic = true }
local ANCHORS = {
	topleft = { 0, 0 },
	top = { 0.5, 0 },
	topright = { 1, 0 },
	left = { 0, 0.5 },
	center = { 0.5, 0.5 },
	right = { 1, 0.5 },
	bottomleft = { 0, 1 },
	bottom = { 0.5, 1 },
	bottomright = { 1, 1 },
}
-- HUD conventions (shooters, simulators): where each kind of information lives. Margins keep clear of screen
-- edges; topLeft starts below the Roblox menu/chat buttons (260x58 px).
local M = 24
UI.SLOTS = {
	topLeft = { anchor = "topleft", pos = { M, 72 } },
	top = { anchor = "top", pos = { "50%", M } },
	topRight = { anchor = "topright", pos = { `100%-{M}`, M } },
	left = { anchor = "left", pos = { M, "50%" } },
	center = { anchor = "center", pos = { "50%", "50%" } },
	right = { anchor = "right", pos = { `100%-{M}`, "50%" } },
	bottomLeft = { anchor = "bottomleft", pos = { M, `100%-{M}` } },
	bottom = { anchor = "bottom", pos = { "50%", `100%-{M}` } },
	bottomRight = { anchor = "bottomright", pos = { `100%-{M}`, `100%-{M}` } },
}

-- design systems: every colour/font/radius a screen needs, chosen together (contrast-checked)
UI.SKINS = {
	scifi = {
		bg = "#0a0e14",
		panel = "#121a24",
		panel2 = "#0c121a",
		line = "#2a3a4c",
		accent = "#4fd8ff",
		accent2 = "#1f8fd6",
		text = "#eaf6ff",
		muted = "#8fa3b8",
		danger = "#ff4d5e",
		good = "#5cf2a0",
		warn = "#ffb547",
		shadow = "#000000",
		font = "GothamBold",
		titleFont = "Michroma",
		monoFont = "RobotoMono",
		radius = { s = 4, m = 6, l = 10 },
	},
	clean = {
		bg = "#101318",
		panel = "#1c212b",
		panel2 = "#151a22",
		line = "#2c3442",
		accent = "#6c8cff",
		accent2 = "#4a63d8",
		text = "#f3f5f9",
		muted = "#9aa4b5",
		danger = "#ff5c6c",
		good = "#4fd18b",
		warn = "#f5b640",
		shadow = "#000000",
		font = "GothamMedium",
		titleFont = "GothamBlack",
		monoFont = "RobotoMono",
		radius = { s = 6, m = 10, l = 16 },
	},
	military = {
		bg = "#0e0f0c",
		panel = "#1b1d17",
		panel2 = "#141510",
		line = "#3a3d30",
		accent = "#d8c27a",
		accent2 = "#a8954f",
		text = "#eeeadb",
		muted = "#a39f8c",
		danger = "#e05a3c",
		good = "#9ccf6a",
		warn = "#e8a83a",
		shadow = "#000000",
		font = "GothamBold",
		titleFont = "Oswald",
		monoFont = "RobotoMono",
		radius = { s = 2, m = 3, l = 5 },
	},
	cartoon = {
		bg = "#1d1340",
		panel = "#3b2a8a",
		panel2 = "#2a1d66",
		line = "#ffffff",
		accent = "#ffd23f",
		accent2 = "#ff9f1c",
		text = "#ffffff",
		muted = "#d9d2ff",
		danger = "#ff4f6d",
		good = "#4ef28a",
		warn = "#ffb020",
		shadow = "#120a2e",
		font = "FredokaOne",
		titleFont = "LuckiestGuy",
		monoFont = "FredokaOne",
		radius = { s = 10, m = 16, l = 24 },
	},
}
-- roles: the type scale (title clearly bigger than body; hints ≥ 14 so phones can read them)
local ROLES = {
	title = { size = 28, font = "titleFont" },
	heading = { size = 20, font = "titleFont" },
	body = { size = 18, font = "font" },
	hint = { size = 14, font = "font", color = "muted" },
	number = { size = 40, font = "titleFont" },
}

-- styles: finished looks, so nobody hand-mixes a flat rectangle
local STYLES = {
	card = { color = "panel", gradient = "auto", stroke = "line", strokeWidth = 1.5, radius = "m", padding = 16 },
	glass = { color = "bg", transparency = 0.35, stroke = "line", strokeWidth = 1, strokeAlpha = 0.2, radius = "m" },
	primary = {
		color = "accent",
		gradient = { from = "accent", to = "accent2", rot = 90 },
		textColor = "bg",
		radius = "m",
		motion = { hover = "lift", press = "sink" },
	},
	secondary = {
		color = "panel",
		gradient = "auto",
		stroke = "accent",
		strokeAlpha = 0.45,
		textColor = "text",
		radius = "m",
		motion = { hover = "glow", press = "sink" },
	},
	chip = { color = "panel2", stroke = "line", radius = "pill", padding = 6 },
	ghost = { stroke = "line", strokeAlpha = 0.3, radius = "m" },
}

local function hex(s: string): { number }?
	local r, g, b = string.match(s, "^#(%x%x)(%x%x)(%x%x)$")
	if not r then
		return nil
	end
	return { tonumber(r, 16) / 255, tonumber(g, 16) / 255, tonumber(b, 16) / 255 }
end

-- WCAG relative luminance + contrast ratio (1..21)
local function luminance(c: { number }): number
	local function ch(v: number): number
		return if v <= 0.03928 then v / 12.92 else ((v + 0.055) / 1.055) ^ 2.4
	end
	return 0.2126 * ch(c[1]) + 0.7152 * ch(c[2]) + 0.0722 * ch(c[3])
end

function UI.contrast(a: { number }, b: { number }): number
	local la, lb = luminance(a), luminance(b)
	return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05)
end

-- "50%" -> {0.5, 0}; 120 -> {0, 120}; "100%-24" -> {1, -24} (hug an edge with a pixel margin)
local function axis(v: any): { number }?
	if type(v) == "number" then
		return { 0, v }
	end
	if type(v) == "string" then
		local pct, off = string.match(v, "^(%-?[%d%.]+)%%%s*([%+%-]%s*[%d%.]+)$")
		if pct then
			return { tonumber(pct) / 100, tonumber((string.gsub(off, "%s", ""))) }
		end
		pct = tonumber(string.match(v, "^(%-?[%d%.]+)%%$"))
		if pct then
			return { pct / 100, 0 }
		end
	end
	return nil
end

local function lighten(c: { number }, k: number): { number }
	return { math.min(1, c[1] + (1 - c[1]) * k), math.min(1, c[2] + (1 - c[2]) * k), math.min(1, c[3] + (1 - c[3]) * k) }
end

local function darken(c: { number }, k: number): { number }
	return { c[1] * (1 - k), c[2] * (1 - k), c[3] * (1 - k) }
end

local function colorSeq(a: { number }, b: { number }): any
	return { ColorSequence = { keypoints = { { time = 0, color = a }, { time = 1, color = b } } } }
end

-- ------------------------------------------------------------------ components -> plain nodes
local function bar(name: string, size: { any }, pos: { any }, color: string, rot: number?): any
	return { type = "panel", name = name, size = size, pos = pos, anchor = "center", color = color, rotation = rot }
end

-- a Combat Feedback Kit component that cannot work as written (V4 UI-X 13.6) -> { {field, message} }: a pinned marker
-- whose margin is under its own half-size hangs off the screen edge; a margin of half a phone's height (390 px) leaves
-- the pin nowhere to travel; a ladder's rungs / windows / stack that the runtime cannot honour
function UI.componentProblems(n: any): { { string } }
	local out: { { string } } = {}
	if type(n) ~= "table" then
		return out
	end
	if n.type == "marker" then
		local s = if type(n.size) == "table" then n.size[1] else (n.size or 44)
		local m = n.margin
		if m ~= nil then
			if type(m) ~= "number" then
				table.insert(
					out,
					{ "margin", "margin is the pixels a pinned marker keeps from the screen edge (a number)" }
				)
			elseif type(s) == "number" and m < s then
				table.insert(out, {
					"margin",
					`a pinned marker hangs off the screen edge: margin {m} px is under its own half-size {s} px (the pin and its arrow); use margin >= {s}`,
				})
			elseif m >= 195 then
				table.insert(out, {
					"margin",
					`margin {m} px leaves the pinned marker nowhere to travel on a phone (390 px tall: half is 195)`,
				})
			end
		end
	elseif n.type == "ladder" then
		if n.rungs ~= nil then
			local ok = type(n.rungs) == "table" and #n.rungs >= 1 and #n.rungs <= 12
			if ok then
				for _, r in n.rungs do
					if type(r) ~= "string" or string.match(r, "^%s*$") then
						ok = false
					end
				end
			end
			if not ok then
				table.insert(out, {
					"rungs",
					'rungs are 1-12 words for 2, 3 ... kills in a chain (the identity\'s own: ["Double", "Triple"]), none empty',
				})
			end
		end
		local max = n.max
		if max ~= nil and (type(max) ~= "number" or max ~= math.floor(max) or max < 1 or max > 6) then
			table.insert(out, { "max", "max is how many banners stack at once: a whole number 1-6" })
		end
		for _, k in { "killWindow", "hitWindow" } do
			local v = n[k]
			if v ~= nil and (type(v) ~= "number" or v < 0.5 or v > 10) then
				table.insert(out, { k, `{k} is the seconds a chain stays open: 0.5-10` })
			end
		end
		local step = n.hitStep
		if step ~= nil and (type(step) ~= "number" or step ~= math.floor(step) or step < 2) then
			table.insert(out, { "hitStep", "hitStep is a whole number >= 2 (a combo banner every hitStep hits)" })
		end
	elseif n.type == "tooltip" then
		if n.drag ~= nil and type(n.drag) ~= "boolean" then
			table.insert(out, { "drag", "drag is true (the player can pull a held tooltip aside) or false" })
		end
	end
	return out
end

local function expand(n: any): any
	local out = UI._expand(n)
	out.kit = true -- built by the kit: taste checks (flat fill, centre blocking) do not apply inside
	return out
end

function UI._expand(n: any): any
	local t = n.type
	if t == "crosshair" then
		local s, gap, th = n.size or 10, n.gap or 6, n.thickness or 2
		local color = n.color or "text"
		local style = n.style or "cross"
		local box = (s + gap) * 2 + 4
		local kids = {}
		if style == "cross" or style == "chevron" then
			local r = s / 2 + gap
			table.insert(kids, bar("Top", { th, s }, { "50%", `50%-{r}` }, color))
			table.insert(kids, bar("Bottom", { th, s }, { "50%", `50%+{r}` }, color))
			table.insert(kids, bar("Left", { s, th }, { `50%-{r}`, "50%" }, color))
			table.insert(kids, bar("Right", { s, th }, { `50%+{r}`, "50%" }, color))
		end
		table.insert(kids, {
			type = "panel",
			name = "Dot",
			size = { th + 1, th + 1 },
			pos = { "50%", "50%" },
			anchor = "center",
			color = color,
			radius = "pill",
		})
		for _, k in kids do
			k.stroke = "shadow"
			k.strokeWidth = 1
			k.strokeAlpha = 0.5
		end
		return {
			type = "panel",
			name = n.name,
			slot = n.slot or "center",
			size = { box, box },
			children = kids,
			attributes = n.attributes,
			z = n.z,
		}
	elseif t == "marker" then
		-- an OFF-SCREEN / WAYPOINT marker (v7.8): over its target while seen, pinned to the screen edge with an arrow
		-- toward it when not (behind the camera too); Ui.track(node, target) drives it. Pin + arrow + distance
		local s = if type(n.size) == "table" then n.size[1] else (n.size or 44)
		local color = n.color or "accent"
		local pin = if n.icon
			then {
				type = "image",
				name = "Pin",
				image = n.icon,
				fit = "fit",
				size = { s, s },
				pos = { "50%", "50%" },
				anchor = "center",
				z = 3,
			}
			else {
				type = "path",
				name = "Pin",
				size = { s, s },
				pos = { "50%", "50%" },
				anchor = "center",
				closed = true,
				smooth = false,
				points = { { s / 2, 2 }, { s - 2, s / 2 }, { s / 2, s - 2 }, { 2, s / 2 } },
				color = color,
				thickness = 4,
				outline = { color = "shadow", px = 1.5 },
				z = 3,
			}
		return {
			type = "panel",
			name = n.name,
			slot = n.slot,
			pos = n.pos or { "50%", "50%" },
			anchor = "center",
			size = { s * 2, s * 2 + 24 },
			children = {
				pin,
				{
					type = "panel",
					name = "Pivot",
					size = { s * 2, s * 2 },
					pos = { "50%", s },
					anchor = "center",
					visible = false, -- (shown while the target is off screen; Ui.track turns it toward the target)
					children = {
						{
							type = "path",
							name = "Arrow",
							size = { s * 0.6, s * 0.36 },
							pos = { "50%", 0 },
							anchor = "top",
							smooth = false,
							points = { { 0, s * 0.36 }, { s * 0.3, 0 }, { s * 0.6, s * 0.36 } },
							color = color,
							thickness = 4,
							outline = { color = "shadow", px = 1.5 },
						},
					},
				},
				{
					type = "label",
					name = "Dist",
					text = n.text or "120 m",
					textSize = n.textSize or 16,
					textColor = n.textColor or "text",
					textOutline = "shadow",
					size = { s * 2, 22 },
					pos = { 0, s * 2 },
					align = "center",
				},
			},
			attributes = {
				Kit_Marker = n.shape or "ellipse",
				Kit_MarkerMargin = n.margin or 56,
			},
		}
	elseif t == "compass" then
		-- a COMPASS BAR (v7.8): a strip of ticks + bearings sliding under a centre notch as the camera turns
		-- (Ui.bind drives it); "degrees" = the arc the bar shows
		local size = n.size or { 600, 44 }
		local w, h = size[1], size[2]
		local degrees = n.degrees or 180
		local ppd = w / degrees
		local color = n.color or "text"
		local kids = {}
		local names =
			{ [0] = "N", [45] = "NE", [90] = "E", [135] = "SE", [180] = "S", [225] = "SW", [270] = "W", [315] = "NW" }
		for d = -360, 360, 15 do
			local x = (d + 360) * ppd
			local bearing = d % 360
			local label = names[bearing]
			if label then
				table.insert(kids, {
					type = "label",
					name = `L{d + 360}`,
					text = label,
					textSize = if #label == 1 then 18 else 14,
					textColor = if bearing == 0 then (n.northColor or "accent") else color,
					textOutline = "shadow",
					size = { 40, 20 },
					pos = { x - 20, 2 },
					align = "center",
				})
			else
				table.insert(kids, bar(`T{d + 360}`, { 2, h * 0.28 }, { x, h * 0.62 }, color))
			end
		end
		return {
			type = "panel",
			name = n.name,
			slot = n.slot or "top",
			pos = n.pos,
			anchor = n.anchor,
			size = size,
			clip = true,
			children = {
				{
					type = "panel",
					name = "Strip",
					size = { ppd * 720, h },
					pos = { w / 2 - ppd * 360, 0 },
					children = kids,
				},
				bar("Notch", { 3, h * 0.45 }, { "50%", h * 0.78 }, n.notchColor or "accent"),
			},
			attributes = { Kit_Compass = ppd },
		}
	elseif t == "damage" then
		-- DIRECTIONAL DAMAGE (v7.8): a red arc toward whoever hit you; Ui.hurt(node, attackerPosition) clones and fades it
		local s = if type(n.size) == "table" then n.size[1] else (n.size or 300)
		return {
			type = "panel",
			name = n.name,
			slot = n.slot or "center",
			size = { s, s },
			children = {
				{
					type = "panel",
					name = "Wedge",
					size = { s, s },
					pos = { "50%", "50%" },
					anchor = "center",
					visible = false,
					children = {
						{
							type = "path",
							name = "Arc",
							size = { s, s },
							arc = { from = -112, to = -68, r = 0.47 },
							color = n.color or "danger",
							thickness = n.thickness or 10,
							outline = { color = "shadow", px = 2 },
						},
					},
				},
			},
			attributes = { Kit_Damage = true },
		}
	elseif t == "toasts" then
		-- a TOAST QUEUE (v7.9): Ui.toast(node, "Saved!", "good") shows one at a time (up to "max" stacked), the rest wait
		local size = n.size or { 360, 220 }
		return {
			type = "panel",
			name = n.name,
			slot = n.slot or "topRight",
			pos = n.pos,
			anchor = n.anchor,
			size = size,
			children = {
				{
					type = "panel",
					name = "Toast",
					style = n.style or "card",
					size = { size[1], 56 },
					visible = false,
					children = {
						{
							type = "label",
							name = "Label",
							text = "Toast",
							textSize = 18,
							textColor = "text",
							size = { "100%-24", "100%" },
							pos = { 12, 0 },
							align = "left",
						},
					},
				},
			},
			attributes = { Kit_Toasts = n.max or 3 },
		}
	elseif t == "tooltip" then
		-- a TOOLTIP (v7.9): shown beside any node with a "tip" (hover / gamepad selection); a compare line "+12 ATK" /
		-- "-3 DEF" turns good / danger by its sign
		return {
			type = "panel",
			name = n.name or "Tooltip",
			style = n.style or "card",
			size = n.size or { 280, 120 },
			visible = false,
			z = 50,
			children = {
				{
					type = "label",
					name = "Title",
					text = "Item",
					textSize = 22,
					textColor = "text",
					size = { "100%-20", 30 },
					pos = { 10, 8 },
					align = "left",
				},
				{
					type = "label",
					name = "Body",
					text = "+12 ATK",
					textSize = 18,
					textColor = "muted",
					rich = true,
					size = { "100%-20", "100%-46" },
					pos = { 10, 40 },
					align = "left",
				},
			},
			-- "drag": true (V4 UI-X compare tooltips): a UIDragDetector lets the player pull a held tooltip aside
			attributes = { Kit_Tooltip = true, Kit_TooltipDrag = if n.drag == true then true else nil },
		}
	elseif t == "ladder" then
		-- THE STREAK LADDER (V4 UI-X 13.6, the Combat Feedback Kit): Ui.streakLadder(node, "hit" | "crit" | "kill" |
		-- "reset") - kills inside "killWindow" climb "rungs" (the identity's own words for 2, 3 ... kills), hits chain a
		-- combo (a banner every "hitStep"), a crit is always a banner; banners stack on springs, newest on top, "max" kept
		local size = n.size or { 360, 180 }
		local bh = n.bannerHeight or 44
		local rungs: { string } = {}
		if type(n.rungs) == "table" then
			for _, r in n.rungs do
				if type(r) == "string" then
					table.insert(rungs, r)
				end
			end
		end
		local ts = n.textSize or 24
		return {
			type = "panel",
			name = n.name,
			slot = n.slot or "topRight",
			pos = n.pos,
			anchor = n.anchor,
			size = size,
			children = {
				{
					type = "panel",
					name = "Banner",
					style = n.style or "card",
					size = { size[1], bh },
					visible = false,
					children = {
						{
							type = "label",
							name = "Label",
							text = if type(rungs[1]) == "string" then rungs[1] else "Kill",
							textSize = ts,
							textColor = n.textColor or "text",
							size = { "100%-96", "100%" },
							pos = { 12, 0 },
							align = "left",
						},
						{
							type = "label",
							name = "Count",
							text = "x2",
							textSize = ts,
							textColor = n.countColor or "accent",
							size = { 72, "100%" },
							pos = { "100%-84", 0 },
							align = "right",
						},
					},
				},
			},
			attributes = {
				Kit_Ladder = n.max or 3,
				Kit_LadderRungs = table.concat(rungs, "|"),
				Kit_LadderKillWindow = n.killWindow or 4.5,
				Kit_LadderHitWindow = n.hitWindow or 2,
				Kit_LadderHitStep = n.hitStep or 10,
				Kit_LadderKill = n.killLabel,
				Kit_LadderCrit = n.critLabel,
			},
		}
	elseif t == "hitmarker" then
		local s = n.size or 12
		local d = s * 0.75
		local color = n.color or "text"
		return {
			type = "canvas",
			name = n.name,
			slot = n.slot or "center",
			size = { s * 4, s * 4 },
			groupAlpha = 1, -- hidden until Ui.flash(node)
			visible = false, -- (and not drawn: Ui.flash shows it, then hides it again - its texture freed meanwhile)
			children = {
				bar("A", { s, 2 }, { `50%-{d}`, `50%-{d}` }, color, 45),
				bar("B", { s, 2 }, { `50%+{d}`, `50%-{d}` }, color, -45),
				bar("C", { s, 2 }, { `50%-{d}`, `50%+{d}` }, color, -45),
				bar("D", { s, 2 }, { `50%+{d}`, `50%+{d}` }, color, 45),
			},
			attributes = n.attributes,
		}
	elseif t == "ring" then
		local size = n.size or 64
		local value = math.clamp(n.value or 1, 0, 1)
		local a = value * 360
		local color = n.color or "accent"
		local function half(name: string, x: string, imgX: string, rot: number): any
			return {
				type = "panel",
				name = name,
				size = { "50%", "100%" },
				pos = { x, 0 },
				clip = true,
				children = {
					{
						type = "image",
						name = "Arc",
						image = "art:ring",
						imageColor = color,
						size = { "200%", "100%" },
						pos = { imgX, 0 },
						halfGradient = rot,
					},
				},
			}
		end
		local kids = {
			{
				type = "image",
				name = "Track",
				image = "art:ring",
				imageColor = n.track or "panel2",
				imageAlpha = 0.2,
				size = { "100%", "100%" },
			},
			half("Right", "50%", "-100%", math.clamp(a, 0, 180)),
			half("Left", 0, 0, math.clamp(a, 180, 360)),
		}
		for _, c in n.children or {} do
			table.insert(kids, c)
		end
		return {
			type = "panel",
			name = n.name,
			slot = n.slot,
			size = { size, size },
			pos = n.pos,
			anchor = n.anchor,
			aspect = 1,
			children = kids,
			attributes = { KitRing = value },
			motion = n.motion,
		}
	elseif t == "scope" then
		-- the lens is a square as tall as the screen (aspect 1); the black sides hang off its edges, so wide
		-- screens are covered without ever darkening the lens itself
		local kids: { any } = {
			{
				type = "panel",
				name = "Lens",
				size = { "100%", "100%" },
				pos = { "50%", "50%" },
				anchor = "center",
				aspect = 1,
				children = {
					{
						type = "panel",
						name = "SideL",
						size = { "500%", "100%" },
						anchor = "right",
						pos = { 0, "50%" },
						color = "#000000",
					},
					{
						type = "panel",
						name = "SideR",
						size = { "500%", "100%" },
						anchor = "left",
						pos = { "100%", "50%" },
						color = "#000000",
					},
					{
						type = "image",
						name = "Reticle",
						image = "art:reticle",
						imageColor = n.reticleColor or "#000000",
						size = { "100%", "100%" },
					},
					{
						type = "image",
						name = "Mask",
						image = "art:scope_mask",
						imageColor = "#000000",
						size = { "100%", "100%" },
					},
				},
			},
		}
		for _, c in n.children or {} do
			table.insert(kids, c)
		end
		return { type = "panel", name = n.name, size = { "100%", "100%" }, children = kids, visible = n.visible }
	elseif t == "keyhint" then
		local keyW = math.max(32, #(n.key or "E") * 11 + 16)
		local textW = math.max(40, #(n.text or "") * 9 + 10)
		return {
			type = "panel",
			name = n.name,
			slot = n.slot,
			pos = n.pos,
			anchor = n.anchor,
			size = n.size or { keyW + 8 + textW, 32 },
			glyph = n.glyph, -- (a pad button's picture replaces the cap while a gamepad is in use)
			layout = { dir = "horizontal", gap = 8, align = "center" },
			children = {
				{
					type = "image",
					name = "Key",
					image = "art:keycap",
					-- the kit's white cap is tinted; an identity's finished cap ("identity") is shown as drawn
					imageColor = if n.keyColor == "identity" then nil else (n.keyColor or "text"),
					size = { keyW, 30 },
					children = {
						{
							type = "label",
							name = "KeyText",
							text = n.key or "E",
							textSize = 14,
							textColor = n.keyTextColor or "bg",
							size = { "100%", "88%" },
						},
					},
				},
				{
					type = "label",
					name = "Text",
					text = n.text or "",
					role = "hint",
					size = { textW, 30 },
					align = "left",
					textOutline = "shadow",
				},
			},
		}
	elseif t == "ammo" then
		return {
			type = "panel",
			name = n.name,
			slot = n.slot or "bottomRight",
			pos = n.pos,
			anchor = n.anchor,
			size = n.size or { 200, 64 },
			layout = { dir = "horizontal", gap = 6, align = "end" },
			children = {
				{
					type = "label",
					name = "Count",
					text = tostring(n.value or 30),
					role = "number",
					size = { 110, 56 },
					align = "right",
					textOutline = "shadow",
				},
				{
					type = "label",
					name = "Reserve",
					text = "/ " .. tostring(n.reserve or 90),
					role = "hint",
					size = { 70, 44 },
					align = "left",
					textOutline = "shadow",
				},
			},
		}
	elseif t == "feed" then
		return {
			type = "panel",
			name = n.name,
			slot = n.slot or "topLeft",
			pos = n.pos,
			anchor = n.anchor,
			size = n.size or { 320, 200 },
			layout = { dir = "vertical", gap = 4, align = "start" },
			attributes = { KitFeedMax = n.max or 5 },
			children = n.children,
		}
	elseif t == "vignette" then
		return {
			type = "image",
			name = n.name,
			size = { "100%", "100%" },
			image = "art:vignette",
			imageColor = n.color or "#000000",
			imageAlpha = n.alpha or 0.35,
			fit = "stretch",
			visible = n.visible,
		}
	end
	return n
end

-- ------------------------------------------------------------------ compile
-- a colour's hue (0..360) and saturation (0..1): the "indigo default" gate reads them
local function hsv(c: { number }): (number, number)
	local r, g, b = c[1], c[2], c[3]
	local mx, mn = math.max(r, g, b), math.min(r, g, b)
	local d = mx - mn
	local s = if mx > 0 then d / mx else 0
	if d == 0 then
		return 0, s
	end
	local h
	if mx == r then
		h = (g - b) / d % 6
	elseif mx == g then
		h = (b - r) / d + 2
	else
		h = (r - g) / d + 4
	end
	return h * 60, s
end

-- "14352" -> "14,352" (counters: souls, score, gold); short: 1234 -> "1.2K", 3400000 -> "3.4M" (simulators)
function UI.formatNumber(v: number, sep: string?, short: boolean?): string
	if short then
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
	local out = string.reverse((string.gsub(string.reverse(s), "(%d%d%d)", "%1" .. (sep or ","))))
	if string.sub(out, 1, 1) == (sep or ",") then
		out = string.sub(out, 2)
	end
	return (if v < 0 then "-" else "") .. out
end

-- PHOTOSENSITIVITY (WCAG 2.3.1, LIMITATIONS_FIXES_V4 UI-X 6.4 step 4: flash.py's "<= 3 flashes a second", here at
-- compile time): the most flashes an fx / a loop can make in ANY one second, counted from the Ui runtime's own schedule
-- (src/kit/Ui.luau Ui.fx / playLoop), worst case. Events at least `gap` seconds apart fit floor(1 / gap) + 1 times in
-- one second. The kit holds it at <= 3 whatever the node's size (the runtime cannot know how big a billboard is drawn;
-- Ui.flash caps hit confirms the same way):
--   shimmer / ping  one pass of the band / one echo per `period`               -> gap = period
--   split           ghosts shown + taken away per burst, bursts every*0.7..1.3 apart (+ the burst) -> gap = 0.7*every + dur
--   flicker         the dip re-rolled every 1/30 s for `dur` (up to ceil(30*dur / 2) dips a burst), bursts
--                   every*0.6..1.4 apart (+ the burst)                         -> bursts x dips
--   glint (loop)    the stroke lit once every 3 / speed s                      -> gap = 3 / speed
-- burn_in plays once; pulse / breathe / blink / spin / float / wobble / sweep move or scale a piece (no lit-dark
-- swing); the "flicker" LOOP is a soft noise jitter of the alpha (0.86 +- 0.14 noise): what it shows is counted on the
-- film by kit/ui/flash.py (kit ui reel), not here.
UI.FLASH_LIMIT = 3
local function eventsPerSecond(gap: number): number
	if gap <= 0 then
		return math.huge
	end
	return math.floor(1 / gap + 1e-9) + 1
end
function UI.flashCount(kind: string, v: { [string]: number }): (number, string?)
	if kind == "shimmer" or kind == "ping" then
		return eventsPerSecond(v.period or 0), "a longer period (>= 0.34 s)"
	elseif kind == "split" then
		return eventsPerSecond(0.7 * (v.every or 0) + (v.dur or 0)),
			"a longer every (the runtime waits 0.7..1.3 x every)"
	elseif kind == "flicker" then
		local dips = math.ceil(math.ceil(30 * (v.dur or 0) - 1e-9) / 2)
		local bursts = eventsPerSecond(0.6 * (v.every or 0) + (v.dur or 0))
		return math.min(15, bursts * math.max(1, dips)),
			"a shorter dur (<= 0.2 s: at most 3 dips a burst) or a longer every"
	end
	return 0, nil
end
function UI.loopFlashCount(kind: string, speed: number): number
	if kind == "glint" then
		return eventsPerSecond(3 / math.max(speed, 1e-6))
	end
	return 0
end

-- VRAM (LIMITATIONS_FIXES_V4 UI-X 6.4 / 13.6): a CanvasGroup draws its whole subtree into an off-screen texture of its
-- own, so one inside another renders the inner tree twice (two textures, the inner one blurred by the outer's
-- resample) -> the compiled instance paths of every CanvasGroup with a CanvasGroup above it, and of every CanvasGroup
-- that is hidden only by GroupTransparency 1 while Visible (its texture stays allocated: hide it with Visible = false).
-- tree = a compiled node ({ClassName, Name, Properties, Children}); also what Ui.bind checks at runtime
function UI.canvasProblems(tree: any, path: string?): ({ { path: string, inside: string } }, { string })
	local nested, idle = {}, {}
	local function walk(n: any, at: string, outer: string?)
		if type(n) ~= "table" then
			return
		end
		local here = outer
		if n.ClassName == "CanvasGroup" then
			local p = n.Properties or {}
			if outer then
				table.insert(nested, { path = at, inside = outer })
			else
				here = at
			end
			if (tonumber(p.GroupTransparency) or 0) >= 0.99 and p.Visible ~= false then
				table.insert(idle, at)
			end
		end
		for _, c in n.Children or {} do
			walk(c, `{at}.{tostring(c.Name)}`, here)
		end
	end
	walk(tree, path or tostring(tree and tree.Name))
	return nested, idle
end

-- ids: assets/ids.json (art:<name> -> ids.ui.<name>); art: kit/ui art.json ({name: {size, slice}}, identity plates
-- under "<identity>/<plate>"); identities: {name -> assets/ui/identities/<name>.json} — all optional
function UI.compile(
	spec: any,
	ids: any?,
	art: any?,
	identities: any?,
	events: { [string]: boolean }?
): (any?, { Issue })
	local issues: { Issue } = {}
	local function err(path: string, message: string)
		table.insert(issues, { path = path, message = message, severity = "error" })
	end
	local function warn(path: string, message: string)
		table.insert(issues, { path = path, message = message, severity = "warn" })
	end
	if type(spec) ~= "table" or type(spec.name) ~= "string" or type(spec.root) ~= "table" then
		err("spec", 'needs "name" (string) and "root" (node)')
		return nil, issues
	end
	local skinName = spec.skin
	if skinName ~= nil and not UI.SKINS[skinName] then
		err("spec.skin", `unknown skin "{tostring(skinName)}" — use scifi | clean | military | cartoon`)
	end
	-- an IDENTITY is the game's whole look decided before any screen: tokens, type, radii, plates, motion, bans
	local identity: any = nil
	if spec.identity ~= nil then
		identity = type(identities) == "table" and identities[spec.identity] or nil
		if not identity then
			err(
				"spec.identity",
				`unknown identity "{tostring(spec.identity)}" — assets/ui/identities/<name>.json (lune run kit ui identities)`
			)
		end
	end
	local quality = spec.quality or "prop"
	if quality ~= "prop" and quality ~= "hero" and quality ~= "aaa" then
		err("spec.quality", "quality must be prop | hero | aaa")
	elseif quality ~= "prop" and not spec.identity then
		err(
			"spec.identity",
			`a {quality} screen needs an "identity" — the look is decided before the screen, not per node`
		)
	end
	-- a neutral base so every standard token name exists (danger, good, warn, muted...); a skin, then the identity,
	-- then the spec's theme each override it
	local theme: { [string]: any } = {
		bg = "#101318",
		panel = "#1c212b",
		panel2 = "#151a22",
		line = "#2c3442",
		accent = "#d8c27a",
		accent2 = "#a8954f",
		text = "#f3f5f9",
		muted = "#9aa4b5",
		danger = "#e05a3c",
		good = "#6fbf5a",
		warn = "#e8a83a",
		shadow = "#000000",
	}
	for k, v in (skinName and UI.SKINS[skinName]) or {} do
		theme[k] = v
	end
	if identity then
		for k, v in identity.tokens or {} do
			theme[k] = v
		end
		for k, v in identity.fonts or {} do
			theme[k] = v
		end
		if identity.radius then
			theme.radius = identity.radius
		end
	end
	for k, v in spec.theme or {} do
		theme[k] = v
	end
	local radii = theme.radius or { s = 4, m = 8, l = 14 }
	local roles: { [string]: any } = table.clone(ROLES)
	for k, v in (identity and identity.roles) or {} do
		roles[k] = if type(v) == "table" then v else roles[k]
	end
	local idMotion = (identity and identity.motion) or {}
	-- MOTION MEASURED, NOT TYPED (LIMITATIONS_FIXES_V4 UI-X 6.4 step 4, `kit ui motion-ref`): once an identity's motion
	-- carries "measured" (written by `kit ui motion-ref <clip> --identity <file>` from the source game's own footage),
	-- its typed enter duration and stagger are held to that measurement (within 25%, at least 0.05 s / 0.02 s) and
	-- an overshoot it measured stays an overshoot (back / elastic) - and none where it measured none
	local measured = idMotion.measured
	if measured ~= nil then
		local idName = tostring(spec.identity)
		if
			type(measured) ~= "table"
			or type(measured.clip) ~= "string"
			or type(measured.duration) ~= "number"
			or type(measured.stagger) ~= "number"
		then
			err(
				`identity:{idName}.motion.measured`,
				'measured is {"clip", "duration", "ease", "stagger"} as kit ui motion-ref --identity writes it'
			)
		else
			local enter = if type(idMotion.enter) == "table" then idMotion.enter else {}
			local d, s = tonumber(enter.duration), tonumber(idMotion.stagger)
			local dTol = math.max(0.05, 0.25 * measured.duration)
			local sTol = math.max(0.02, 0.25 * measured.stagger)
			local dSaid, sSaid = string.format("%.2f", dTol), string.format("%.2f", sTol)
			if d and math.abs(d - measured.duration) > dTol + 1e-9 then
				err(
					`identity:{idName}.motion.enter.duration`,
					`{d} s, but {measured.clip} measured {measured.duration} s (motion-ref; within {dSaid} s) - use the measured number, or measure again`
				)
			end
			if s and math.abs(s - measured.stagger) > sTol + 1e-9 then
				err(
					`identity:{idName}.motion.stagger`,
					`{s} s between enters, but {measured.clip} measured {measured.stagger} s (motion-ref; within {sSaid} s)`
				)
			end
			local overshoots = enter.ease == "back" or enter.ease == "elastic"
			if type(enter.ease) == "string" and type(measured.ease) == "string" then
				if measured.ease == "back" and not overshoots then
					err(
						`identity:{idName}.motion.enter.ease`,
						`"{enter.ease}" settles straight, but {measured.clip} overshoots (measured "back"): back or elastic`
					)
				elseif measured.ease ~= "back" and overshoots then
					err(
						`identity:{idName}.motion.enter.ease`,
						`"{enter.ease}" overshoots, but {measured.clip} settles without one (measured "{measured.ease}")`
					)
				end
			end
		end
	end
	-- "minimums": the identity's scale floors, measured from its references (a simulator reads from across the
	-- room: text 16+, buttons 56+, icons 40+). Under a floor is a warning that names the floor — the judges' first
	-- complaint about every undersized pack was "everything is tiny"; the floor catches it before a judge does.
	local minimums: { [string]: number } = {}
	for k, v in (identity and identity.minimums) or {} do
		if (k == "text" or k == "button" or k == "icon") and type(v) == "number" and v > 0 then
			minimums[k] = v
		else
			err(`identity.minimums.{tostring(k)}`, "minimums: { text = px, button = px, icon = px } (numbers > 0)")
		end
	end
	local missingArt: { [string]: boolean } = {}
	local textSizes: { number } = {}
	local textNodes: { { path: string, size: number, typed: boolean? } } = {} -- (every non-internal text, for the focus gate; typed = a font glyph, not lettered art)
	local imageNodes: { string } = {} -- (every non-internal image: a rendered logotype can be the focus too)
	local numberNodes: { string } = {} -- (a digit-set number may be the focus: a frame of glyph cells)
	local centerBlockers: { string } = {}
	-- arcade-ban: component types seen during traversal (type -> first path that used it)
	-- checked at the end against identity.banned_components (a list of component type strings).
	-- Also: every node's (path, name) pair so name-substring matches can be checked at the end.
	local seenComponents: { [string]: string } = {}
	local seenNodeNames: { { path: string, name: string } } = {}
	-- the composition gates (identity "rules": what six judge pairs repeated — level blocks, isolated blocks, the
	-- accent everywhere, the hero not the biggest): the top blocks' rects and leans at 1920x1080, the accent's
	-- painted area, every image's area
	local topBlocks: { { path: string, x0: number, y0: number, x1: number, y1: number, rot: number, full: boolean } } =
		{}
	local accentArea = 0
	local imageAreas: { { path: string, area: number } } = {}
	local radiiUsed: { number } = {}
	local enterDelays: { number } = {}
	local parentStagger = 0 -- (> 0 while the children of a staggered container compile: they arrive in order)
	local parentList = false -- (true while the children of a node with a LIST layout compile: a flex item's home)
	-- "at": {"phone": {"scale": 0.55}} on a node shrinks it AND everything inside it on that viewport (absolute
	-- sizes / offsets times the product of every scale above): baked art (lettering, renders) keeps its desktop pixels,
	-- so a group of it needs one scale, not a size per piece
	local parentAtScale: { [string]: number } = {}
	-- true while every ancestor spans the screen: only then are a node's % positions screen fractions (the centre gate)
	local parentScreenSpan = true

	local function color(path: string, v: any): { number }?
		if v == nil then
			return nil
		end
		local resolved = if type(v) == "string" and theme[v] then theme[v] else v
		local c = type(resolved) == "string" and hex(resolved) or nil
		if not c then
			err(path, `color "{tostring(v)}" is not a theme name or #rrggbb`)
		end
		return c
	end

	local function radius(path: string, v: any): number?
		if v == nil then
			return nil
		end
		if v == "pill" then
			return 999
		end
		if type(v) == "string" then
			local r = radii[v]
			if not r then
				err(path, 'radius must be pixels or "s" | "m" | "l" | "pill"')
			end
			return r
		end
		return v
	end

	local function udim2(path: string, v: any, default: { any }): any
		local pair = v or default
		if type(pair) ~= "table" or #pair ~= 2 then
			err(path, 'must be [x, y] — numbers are pixels, "50%" is a fraction of the parent')
			return nil
		end
		local x, y = axis(pair[1]), axis(pair[2])
		if not x or not y then
			err(path, 'each value must be a number (pixels), "N%" or "N%-px" / "N%+px"')
			return nil
		end
		-- offsets are whole pixels (Rojo refuses a fractional UDim offset and fails the whole build)
		x[2] = math.floor(x[2] + 0.5)
		y[2] = math.floor(y[2] + 0.5)
		return { UDim2 = { x, y } }
	end

	local function image(path: string, v: any): (string, string?)
		if type(v) ~= "string" then
			err(path, 'image nodes need "image": "art:<name>" (kit art) or "rbxassetid://..."')
			return "", nil
		end
		local artName = string.match(v, "^art:([%w_/]+)$")
		if artName then
			-- the identity's own version of a kit piece wins (its keycap, vignette, ring, glow...)
			if
				spec.identity
				and art
				and not string.find(artName, "/", 1, true)
				and art[`{spec.identity}/{artName}`]
			then
				artName = `{spec.identity}/{artName}`
			end
			if art and not art[artName] then
				err(
					path,
					`unknown art "{artName}" — kit art: ring, disc, glow, vignette, scope_mask, reticle, panel, panel_line, corner, keycap, gradient_v, stripes; identity plates: "<identity>/<plate>" (kit ui art draws them from assets/ui/identities/<identity>.json)`
				)
			end
			local id = ids and ids.ui and ids.ui[artName]
			if type(id) ~= "string" then
				missingArt[artName] = true
				return "", artName
			end
			return id, artName
		end
		return v, nil
	end

	-- plate / divider / texture: a piece of the identity's drawn art (kit ui art) as an image node
	local function plateNode(raw: any, path: string): any
		local n = table.clone(raw)
		local plate = raw.plate
			or (if type(raw.rarity) == "string" then `card_{raw.rarity}` else nil)
			or (
				if raw.type == "divider"
					then "divider"
					elseif raw.type == "texture" then (raw.texture or "grain")
					else nil
			)
		if raw.rarity ~= nil then
			if type(raw.rarity) ~= "string" or not theme[`rarity_{raw.rarity}`] then
				err(
					path .. ".rarity",
					`rarity "{tostring(raw.rarity)}": the identity has no token "rarity_{tostring(raw.rarity)}" (common | uncommon | rare | epic | legendary | mythic)`
				)
			else
				n.attributes = table.clone(raw.attributes or {})
				n.attributes.Kit_Rarity = raw.rarity
			end
			n.rarity = nil
		end
		if type(plate) ~= "string" then
			err(
				path .. ".plate",
				'a plate node names the identity plate it shows: "plate": "frame" (kit ui art draws them)'
			)
			plate = ""
		end
		n.type = "image"
		if string.sub(plate, 1, 4) == "art:" then
			n.image = plate
		elseif
			not string.find(plate, "/", 1, true)
			and spec.identity
			and (not art or art[`{spec.identity}/{plate}`] or not art[plate])
		then
			n.image = `art:{spec.identity}/{plate}` -- the identity's piece (or its error when neither exists)
		else
			n.image = "art:" .. plate -- "<identity>/<plate>" as given, the kit's own piece, or no identity at all
		end
		n.plate, n.texture = nil, nil
		-- a plate / texture is an image: "color" tints it, it never paints a background behind it
		n.imageColor = raw.color or raw.imageColor
		n.color, n.transparency, n.gradient = nil, nil, nil
		if raw.type == "texture" then
			n.fit = "tile"
			n.size = raw.size or { "100%", "100%" }
			n.imageAlpha = 1 - math.clamp(raw.strength or 0.15, 0, 1)
		elseif raw.type == "divider" then
			n.size = raw.size or { "100%", 12 }
		end
		n.kit = true
		return n
	end

	-- "tracking": letters set apart (YOU DIED): a horizontal list of one auto-sized label per glyph. The engine has no
	-- letter-spacing; this is how it is done. Ui.text(node, "...") rebuilds the glyphs; the attributes carry the recipe.
	local function trackedLabel(raw: any): any
		local role = raw.role and roles[raw.role]
		local size = raw.textSize or (role and role.size) or 18
		local tracking = raw.tracking
		local gap = math.floor(size * tracking + 0.5)
		local kids = {}
		local text = tostring(raw.text or "")
		local i = 0
		-- the ransom patterns (deterministic: the same word always cuts the same way; "ransom_seed" shifts them)
		local ransom = raw.ransom == true
		local seed = tonumber(raw.ransom_seed) or 0
		local sizes = { 1.0, 0.84, 1.22, 0.92, 1.14, 0.8, 1.3, 1.0, 0.88, 1.18 }
		local rots = { -8, 6, -3, 10, -11, 4, -6, 9, -2, 7 }
		local inverts = { false, true, false, false, true, false, true, false, false, true }
		local lowers = { false, false, true, false, true, false, false, true, false, false }
		for _, cp in utf8.codes(text) do
			i += 1
			local ch = utf8.char(cp)
			local k = ((i + seed - 1) % #sizes) + 1
			local glyphSize = if ransom then math.floor(size * sizes[k] + 0.5) else size
			local shown = ch
			if ransom and lowers[k] and ch ~= " " then
				shown = string.lower(ch)
			end
			local inverted = ransom and inverts[k] and ch ~= " "
			table.insert(kids, {
				type = "label",
				name = `G{i}`,
				text = if ch == " " then "" else shown,
				-- a ransom glyph is a cutout with its own box (a plate cannot autosize): ~0.74 em for a heavy display face
				size = {
					if ch == " "
						then math.floor(size * 0.3 + 0.5)
						elseif ransom then math.floor(glyphSize * 0.8 + 0.5)
						else 0,
					if ransom then math.floor(glyphSize * 1.52 + 0.5) else math.floor(glyphSize * 1.3 + 0.5),
				},
				autosize = if ch == " " or ransom then nil else "x",
				textSize = glyphSize,
				font = raw.font,
				role = raw.role,
				-- a ransom glyph is a cutout: paper letter on an ink scrap, or an ink letter on a paper scrap
				plate = if ransom and ch ~= " " then (if inverted then "torn" else "torn_black") else nil,
				padding = if ransom and ch ~= " " then math.floor(glyphSize * 0.12 + 0.5) else nil,
				rotation = if ransom and ch ~= " " then rots[k] else nil,
				textColor = if ransom then (if inverted then "bg" else "text") else raw.textColor,
				textOutline = if ransom then nil else raw.textOutline,
				textOutlineWidth = if ransom then nil else raw.textOutlineWidth,
				textGradient = raw.textGradient,
				attributes = if inverted then { Kit_Inverted = true } else nil,
				kit = true,
			})
		end
		-- the recipe the runtime rebuilds glyphs from (Ui.text): resolved colours as hex, the outline too
		local function hexOf(v: any, fallback: string): string
			local c = color("tracked", v)
			if not c then
				return fallback
			end
			return string.format(
				"#%02x%02x%02x",
				math.floor(c[1] * 255 + 0.5),
				math.floor(c[2] * 255 + 0.5),
				math.floor(c[3] * 255 + 0.5)
			)
		end
		local attrs: { [string]: any } = {
			Kit_Tracking = tracking,
			Kit_Ransom = if ransom then true else nil,
			Kit_RansomSeed = if ransom then seed else nil,
			Kit_Text = text,
			Kit_TextSize = size,
			Kit_Font = raw.font or (role and (theme[role.font] or role.font)) or theme.font or "GothamMedium",
			Kit_TextColor = hexOf(raw.textColor or (role and role.color) or "text", "#ffffff"),
		}
		if raw.textOutline then
			attrs.Kit_TextOutline = hexOf(raw.textOutline, "#000000")
			attrs.Kit_TextOutlineWidth = raw.textOutlineWidth or 1.5
		end
		for k, v in raw.attributes or {} do
			attrs[k] = v
		end
		-- the glyph row lives in its own frame: the container keeps its plate / Label / stroke / corner as
		-- ordinary children, nothing of theirs is swept into the list
		local glyphs = {
			type = "panel",
			name = "Glyphs",
			size = { "100%", "100%" },
			layout = {
				dir = "horizontal",
				gap = gap,
				align = "center",
				justify = ({ left = "start", center = "center", right = "end" })[raw.align or "center"] or "center",
			},
			children = kids,
			kit = true,
		}
		return {
			-- a tracked BUTTON stays a button (its own text empty, the glyphs on top): hover / press / clicks work
			type = if raw.type == "button" then "button" else "panel",
			text = if raw.type == "button" then "" else nil,
			plate = raw.plate,
			style = raw.style,
			name = raw.name,
			size = raw.size or { "100%", math.floor(size * 1.4 + 0.5) },
			pos = raw.pos,
			anchor = raw.anchor,
			slot = raw.slot,
			z = raw.z,
			visible = raw.visible,
			rotation = raw.rotation,
			motion = raw.motion,
			color = raw.color,
			transparency = raw.transparency,
			gradient = raw.gradient,
			stroke = raw.stroke,
			strokeWidth = raw.strokeWidth,
			strokeAlpha = raw.strokeAlpha,
			strokeGradient = raw.strokeGradient,
			radius = raw.radius,
			padding = raw.padding,
			aspect = raw.aspect,
			clip = raw.clip,
			attributes = attrs,
			children = { glyphs },
			kit = true,
		}
	end

	-- "counter": a number that rolls (souls, score): the label shows it formatted; Ui.counter(node, v) rolls to v
	local function counterNode(raw: any, path: string): any
		local n = table.clone(raw)
		n.type = "label"
		n.role = raw.role or "number"
		local v = raw.value or 0
		local short = raw.format == "short"
		if raw.format ~= nil and raw.format ~= "short" and raw.format ~= "full" then
			err(path .. ".format", 'counter format: "full" (14,352) | "short" (14.4K)')
		end
		n.text = (raw.prefix or "") .. UI.formatNumber(v, raw.separator, short) .. (raw.suffix or "")
		n.attributes = table.clone(raw.attributes or {})
		n.attributes.Kit_Counter = v
		n.attributes.Kit_CounterPrefix = raw.prefix or ""
		n.attributes.Kit_CounterSuffix = raw.suffix or ""
		n.attributes.Kit_CounterSep = raw.separator or ","
		n.attributes.Kit_CounterFormat = if short then "short" else "full"
		-- TABULAR FIGURES (v7.13): a counter that rolls in a proportional face jitters (a 1 is narrower than an 8)
		local MONO = { Code = true, RobotoMono = true, Ubuntu = false }
		if type(raw.font) == "string" and not MONO[raw.font] then
			warn(
				path,
				`a rolling counter in {raw.font} (proportional digits) jitters as it counts — use a digit-set "number", a monospaced face (RobotoMono, Code), or the identity's monoFont`
			)
		end
		n.value, n.prefix, n.suffix, n.separator, n.format = nil, nil, nil, nil, nil
		return n
	end

	-- "number": a number drawn from a DIGIT SET (kit ui letter --glyphs: one baseline, one monospace cell) — a frame of
	-- image cells, one per character of "text"; every glyph's uploaded id rides on the frame (Kit_DigitIds) so game code
	-- can show any number with Ui.number(node, "182") without a typed label
	local function glyphCode(c: string): string
		if string.match(c, "^%w$") then
			return c
		end
		return `u{string.byte(c)}`
	end
	-- BITMAP-FONT TEXT (v7.5): a label with "glyphs": "<identity>/<set>" (kit/ui/font.py) is set in the identity's own
	-- lettering — any text, proportionally: each glyph's measured ink, the set's tracking, the face's own kerning, word
	-- wrap inside the box, "align" left / center / right. The glyph map (ids, with atlas rects) rides on the node so
	-- Ui.write(node, "new words") sets new text in game; the preview draws the laid-out glyphs.
	local function glyphTextNode(raw: any, path: string): any
		local set = raw.glyphs
		local meta = type(set) == "string" and art and art[set .. "__font"] or nil
		local fm = meta and meta.font
		if type(fm) ~= "table" then
			err(
				path .. ".glyphs",
				`no bitmap font "{tostring(set)}" (python kit/ui/font.py {tostring(set)} --font <face>, then lune run kit ui)`
			)
			return { type = "panel", name = raw.name, size = raw.size, pos = raw.pos, anchor = raw.anchor }
		end
		local size = raw.size
		local w = type(size) == "table" and tonumber(size[1]) or nil
		local h = type(size) == "table" and tonumber(size[2]) or nil
		if not w or not h then
			err(path .. ".size", "a glyph-text label needs a pixel size [w, h] (its lines wrap inside w)")
			w, h = 200, 40
		end
		local cellW, cellH = fm.cell[1], fm.cell[2]
		local lineH = tonumber(raw.lineHeight) or (raw.textSize and tonumber(raw.textSize) * 1.25) or h
		local k = lineH / cellH
		local track = (tonumber(raw.tracking) or fm.track or 0.05) * cellH
		local spaceW = (fm.space or 0.28) * cellH
		local codes = fm.codes or {}
		local ink = fm.ink or {}
		local kern = fm.kern or {}
		local text = tostring(raw.text or "")
		-- the glyph map: code=id[@x,y,w,h] (an atlased glyph shows its sheet through a rect)
		local mapParts, inkParts = {}, {}
		for _, code in codes do
			local nm = `{set}_{code}`
			local id = image(`{path}.glyphs`, "art:" .. nm)
			local at = art and art[nm] and art[nm].atlas
			local ident = string.match(set, "^([%w_]+)/")
			local sid = type(at) == "table" and ids and ids.ui and ids.ui[`{ident}/{at[1]}`] or nil
			if type(sid) == "string" then
				table.insert(mapParts, `{code}={sid}@{at[2]},{at[3]},{at[4]},{at[5]}`)
			else
				table.insert(mapParts, `{code}={id}`)
			end
			local i = ink[code]
			if type(i) == "table" then
				table.insert(inkParts, `{code}={i[1]},{i[2]}`)
			end
		end
		table.sort(mapParts)
		table.sort(inkParts)
		local kernParts = {}
		for pair, v in kern do
			table.insert(kernParts, `{pair}={v}`)
		end
		table.sort(kernParts)
		-- lay out the text (the same rules as Ui.write)
		local function adv(ch: string, nxt: string?): number
			if ch == " " then
				return spaceW
			end
			local i = ink[codes[ch] or ""]
			local a = (if type(i) == "table" then i[2] * cellW else cellW * 0.5) + track
			if nxt and kern[ch .. nxt] then
				a += kern[ch .. nxt] * cellH
			end
			return a
		end
		local lines: { string } = {}
		local cur = ""
		for word in string.gmatch(text, "%S+") do
			local try = if cur == "" then word else cur .. " " .. word
			local width = 0
			for idx = 1, #try do
				width += adv(string.sub(try, idx, idx), string.sub(try, idx + 1, idx + 1))
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
		local kids = {}
		local align = raw.align or "left"
		for li, line in lines do
			local width = 0
			for idx = 1, #line do
				width += adv(string.sub(line, idx, idx), string.sub(line, idx + 1, idx + 1))
			end
			width = (width - track) * k
			local pen = if align == "center" then (w - width) / 2 elseif align == "right" then w - width else 0
			for idx = 1, #line do
				local ch = string.sub(line, idx, idx)
				local code = codes[ch]
				if ch ~= " " and code then
					local i = ink[code]
					local left = if type(i) == "table" then i[1] * cellW else 0
					table.insert(kids, {
						type = "image",
						name = `G{#kids + 1}`,
						image = `art:{set}_{code}`,
						fit = "stretch",
						size = { math.floor(cellW * k + 0.5), math.floor(lineH + 0.5) },
						pos = { math.floor(pen - left * k + 0.5), math.floor((li - 1) * lineH + 0.5) },
						z = raw.z,
					})
				end
				pen += adv(ch, string.sub(line, idx + 1, idx + 1)) * k
			end
		end
		if #lines * lineH > h + 1 then
			err(
				path .. ".text",
				`the text needs {#lines} line(s) ({math.floor(#lines * lineH)}px) in a {h}px box: enlarge it or shorten the text`
			)
		end
		local attrs = {
			Kit_GSet = set,
			Kit_GText = text,
			Kit_GIds = table.concat(mapParts, ";"),
			Kit_GInk = table.concat(inkParts, ";"),
			Kit_GKern = table.concat(kernParts, ";"),
			Kit_GCell = `{cellW},{cellH},{lineH},{track},{spaceW}`,
			Kit_GAlign = align,
		}
		-- "glyphFx": a per-glyph effect Ui.write keeps playing — {"kind": "wave" | "shake" | "pop", "amp": px, "speed": hz}
		if raw.glyphFx ~= nil then
			local g = raw.glyphFx
			local kinds = { wave = true, shake = true, pop = true }
			if type(g) ~= "table" or not kinds[g.kind] then
				err(path .. ".glyphFx", 'glyphFx: {"kind": "wave" | "shake" | "pop", "amp": 4, "speed": 2}')
			else
				local amp, speed = tonumber(g.amp) or 4, tonumber(g.speed) or 2
				if amp < 0 or amp > 60 or speed <= 0 or speed > 20 then
					err(path .. ".glyphFx", "amp is 0..60 px, speed 0..20 per second")
				else
					attrs.Kit_GFx = `{g.kind}:amp={amp},speed={speed}`
				end
			end
		end
		if raw.attributes then
			for ak, av in raw.attributes do
				attrs[ak] = av
			end
		end
		return {
			type = "panel",
			name = raw.name,
			size = raw.size,
			pos = raw.pos,
			anchor = raw.anchor,
			z = raw.z,
			motion = raw.motion,
			rotation = raw.rotation,
			visible = raw.visible,
			attributes = attrs,
			children = kids,
			kit = true,
		}
	end

	local function numberNode(raw: any, path: string): any
		table.insert(numberNodes, path)
		local digits = raw.digits
		local text = tostring(raw.text or "")
		local size = raw.size
		if type(digits) ~= "string" or not string.find(digits, "/", 1, true) then
			err(
				path .. ".digits",
				'a number node names its digit set: "digits": "<identity>/<piece>" (kit ui letter --glyphs)'
			)
			digits = "missing/digits"
		end
		local h = if type(size) == "table" then size[2] else nil
		if type(h) ~= "number" then
			err(path .. ".size", "a number node needs a pixel height (size [w, h]): the cells are h tall")
			h = 40
		end
		local aspect = tonumber(raw.aspect) or 0.62
		local cw = math.floor(h * aspect + 0.5)
		local charset = raw.charset or "0123456789"
		if text == "" then
			err(
				path .. ".text",
				'a number node needs its widest "text" ("888"): the cells are laid out for it and Ui.number clones them'
			)
		end
		local glyphIds = {}
		for i = 1, #charset do
			local c = string.sub(charset, i, i)
			local id = image(path .. ".digits", `art:{digits}_{glyphCode(c)}`)
			table.insert(glyphIds, `{glyphCode(c)}={id}`)
		end
		-- "pitch": the advance as a share of the cell (0.5..1.2; default 1): a glyph's cell carries its outline and
		-- shadow, so chunky digits read spaced ("+ 1 2 5") at 1 — at 0.8 the cells overlap and the digits sit close
		local pitch = tonumber(raw.pitch) or 1
		if pitch < 0.5 or pitch > 1.2 then
			err(path .. ".pitch", "pitch is the digit advance as a share of the cell: 0.5 .. 1.2 (1 = touching cells)")
			pitch = 1
		end
		local adv = math.max(1, math.floor(cw * pitch + 0.5))
		-- "narrow": {",": 0.4} — a character's advance as a share of the digits' (a comma in a monospace cell read
		-- "46 , 959": RushHud's verifier, 2026-10-16); each cell centres in its own slot
		local narrow: { [string]: number } = {}
		local narrowAttr = {}
		if type(raw.narrow) == "table" then
			for ch, k in raw.narrow do
				local kk = tonumber(k)
				if type(ch) ~= "string" or #ch ~= 1 or not kk or kk <= 0 or kk > 1.5 then
					err(path .. ".narrow", 'narrow: {"<one character>": share of the advance, 0..1.5} — {",": 0.4}')
				else
					narrow[ch] = kk
					table.insert(narrowAttr, `{glyphCode(ch)}={kk}`)
				end
			end
		end
		local function advOf(ch: string): number
			return math.floor(adv * (narrow[ch] or 1) + 0.5)
		end
		local total = 0
		for i = 1, #text do
			total += advOf(string.sub(text, i, i))
		end
		local align = raw.align or "center"
		local kids = {}
		local slot = 0
		for i = 1, #text do
			local c = string.sub(text, i, i)
			if not string.find(charset, c, 1, true) then
				err(path .. ".text", `"{c}" is not in the digit set's charset "{charset}"`)
			end
			local a = advOf(c)
			local x = slot + (a - cw) / 2
			slot += a
			local pos
			if align == "right" then
				pos = { `100%-{total - x}`, 0 }
			elseif align == "left" then
				pos = { x, 0 }
			else
				local off = x - total / 2
				pos = { if off < 0 then `50%-{-off}` else `50%+{off}`, 0 }
			end
			table.insert(kids, {
				type = "image",
				name = `C{i}`,
				image = `art:{digits}_{glyphCode(c)}`,
				fit = "fit",
				size = { cw, "100%" },
				pos = pos,
				kit = true,
			})
		end
		local attrs = table.clone(raw.attributes or {})
		attrs.Kit_Number = text
		attrs.Kit_Digits = digits
		attrs.Kit_DigitIds = table.concat(glyphIds, ";")
		attrs.Kit_DigitCell = adv
		attrs.Kit_DigitWidth = cw
		if #narrowAttr > 0 then
			attrs.Kit_DigitNarrow = table.concat(narrowAttr, ";")
		end
		attrs.Kit_DigitAlign = align
		return {
			type = "panel",
			name = raw.name,
			size = size,
			pos = raw.pos,
			anchor = raw.anchor,
			rotation = raw.rotation,
			z = raw.z,
			at = raw.at,
			visible = raw.visible,
			motion = raw.motion,
			children = kids,
			attributes = attrs,
		}
	end

	-- "stat": a status-screen row — name left, value right (+ "delta": a change shown beside it)
	local function statNode(raw: any): any
		local h = raw.height or 30
		local kids = {
			{
				type = "label",
				name = "Name",
				text = raw.label or raw.name,
				role = raw.role or "body",
				textSize = raw.textSize,
				textColor = raw.textColor,
				size = { "62%", h },
				pos = { 0, 0 },
				align = "left",
				textOutline = raw.textOutline,
				kit = true,
			},
			{
				type = "label",
				name = "Value",
				text = tostring(raw.value or ""),
				role = raw.valueRole or raw.role or "body",
				font = raw.valueFont,
				textSize = raw.valueSize or raw.textSize,
				textColor = raw.valueColor or raw.textColor,
				size = { raw.valueWidth or "38%", h },
				pos = { "100%", 0 },
				anchor = "topright",
				align = "right",
				textOutline = raw.textOutline,
				kit = true,
			},
		}
		if raw.plate then
			table.insert(
				kids,
				1,
				{ type = "plate", name = "Plate", plate = raw.plate, size = { "100%", "100%" }, kit = true }
			)
			if raw.shadow then
				table.insert(kids, 1, {
					type = "plate",
					name = "Shadow",
					plate = raw.plate,
					size = { "100%", "100%" },
					pos = { 0, if type(raw.shadow) == "number" then raw.shadow else 6 },
					color = "shadow",
					imageAlpha = 0.5,
					z = 0,
					kit = true,
				})
			end
		end
		if raw.delta ~= nil then
			kids[#kids].size = { "24%", h }
			table.insert(kids, {
				type = "label",
				name = "Delta",
				text = tostring(raw.delta),
				role = raw.valueRole or raw.role or "body",
				textColor = raw.deltaColor or "good",
				size = { "14%", h },
				pos = { "100%", 0 },
				anchor = "topright",
				align = "right",
				textOutline = raw.textOutline,
				kit = true,
			})
			kids[#kids - 1].pos = { "86%", 0 }
		end
		return {
			type = "panel",
			name = raw.name,
			size = raw.size or { "100%", h },
			pos = raw.pos,
			anchor = raw.anchor,
			color = raw.color,
			transparency = raw.transparency,
			motion = raw.motion,
			attributes = { Kit_Stat = raw.label or raw.name },
			children = kids,
			kit = true,
		}
	end

	-- GAMEPAD / CONSOLE: "nav" on a control overrides the engine's d-pad neighbours ({"up": "<path>", "down", "left",
	-- "right"} — paths from the screen's root, like "focus"); "glyph" on a key hint swaps its keycap for the gamepad
	-- button's picture when a pad is in use ({"pad": "ButtonX", "touch": "hide"}); the screen's "firstFocus" is where
	-- the pad lands when it opens; its focus piece (the screen's / identity's "focusPiece", else the identity's
	-- frame_line outline) replaces the engine's blue selection box. Ui.gamepad(screen) wires it all (Ui.bind does).
	local NAV_DIRS = { up = "Up", down = "Down", left = "Left", right = "Right" }
	local PAD_KEYS: { [string]: boolean } = {}
	for _, k in
		{
			"ButtonA",
			"ButtonB",
			"ButtonX",
			"ButtonY",
			"ButtonL1",
			"ButtonR1",
			"ButtonL2",
			"ButtonR2",
			"ButtonL3",
			"ButtonR3",
			"ButtonStart",
			"ButtonSelect",
			"DPadUp",
			"DPadDown",
			"DPadLeft",
			"DPadRight",
			"Thumbstick1",
			"Thumbstick2",
		}
	do
		PAD_KEYS[k] = true
	end
	local navNodes: { [string]: string } = {} -- root-relative path -> class
	local interactive: { string } = {}
	local pendingNav: { { at: string, to: string } } = {}

	local function navBlock(n: any, path: string, attrs: any)
		if type(n.nav) ~= "table" then
			err(path .. ".nav", 'nav: {"up": "<path from the root>", "down": ..., "left": ..., "right": ...}')
			return
		end
		for k, v in n.nav do
			local dir = NAV_DIRS[k]
			if not dir then
				err(`{path}.nav.{tostring(k)}`, "nav keys: up | down | left | right")
			elseif type(v) ~= "string" then
				err(`{path}.nav.{k}`, `nav.{k} is a node path from the screen's root ("Shop.Window.Tabs.TabCoins")`)
			else
				attrs["Kit_Nav" .. dir] = v
				table.insert(pendingNav, { at = `{path}.nav.{k}`, to = v })
			end
		end
	end

	local function glyphBlock(n: any, path: string, attrs: any)
		local g = n.glyph
		if type(g) ~= "table" or type(g.pad) ~= "string" or not PAD_KEYS[g.pad] then
			err(
				path .. ".glyph",
				'glyph: {"pad": "ButtonX", "touch": "hide" | "show"} — pad is a gamepad KeyCode (ButtonA, ButtonX, ButtonL1, DPadUp, ...)'
			)
			return
		end
		if g.touch ~= nil and g.touch ~= "hide" and g.touch ~= "show" then
			err(path .. ".glyph.touch", 'touch is "hide" (no keys on a phone) or "show"')
		end
		attrs.Kit_GlyphPad = g.pad
		attrs.Kit_GlyphTouch = g.touch or "hide"
	end

	-- "states": how a control looks in each of its states — a pro screen designs them all, not just idle:
	--   {"hover": {...}, "pressed": {...}, "selected": {...}, "disabled": {...}, "locked": {...}, "new": {...}}
	-- each an override of: color textColor imageColor strokeColor (theme names or #rrggbb), transparency textAlpha
	-- imageAlpha (0..1), image ("art:<identity>/<piece>": a swapped picture), text. Compiled to Kit_States +
	-- Kit_S_<state> ("prop=value;..."); Ui.setState(node, state) applies one (hover / pressed are wired by Ui.bind;
	-- disabled / locked also stop the button); the preview draws every state side by side (<Screen>.states.png).
	local STATE_NAMES = { "hover", "pressed", "selected", "disabled", "locked", "new" }
	local STATE_KEYS: { [string]: string } = {
		color = "color",
		textColor = "color",
		imageColor = "color",
		strokeColor = "color",
		transparency = "alpha",
		textAlpha = "alpha",
		imageAlpha = "alpha",
		image = "art",
		text = "text",
	}
	local function toHex(c: { number }): string
		return string.format(
			"#%02x%02x%02x",
			math.floor(c[1] * 255 + 0.5),
			math.floor(c[2] * 255 + 0.5),
			math.floor(c[3] * 255 + 0.5)
		)
	end
	-- XAG 103: a state told by HUE alone is lost on a colour-blind player — simulate protanopia / deuteranopia
	-- (Machado 2009, severity 1, linear RGB) and compare: no lightness step and no visible change = a warning
	local CVD_M = {
		{ { 0.152286, 1.052583, -0.204868 }, { 0.114503, 0.786281, 0.099216 }, { -0.003882, -0.048116, 1.051998 } },
		{ { 0.367322, 0.860646, -0.227968 }, { 0.280085, 0.672501, 0.047413 }, { -0.011820, 0.042940, 0.968881 } },
	}
	local function lin(v: number): number
		return if v <= 0.04045 then v / 12.92 else ((v + 0.055) / 1.055) ^ 2.4
	end
	local function hueOnly(a: { number }, b: { number }): boolean
		local la, lb = luminance(a), luminance(b)
		local ratio = (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05)
		if ratio >= 1.25 then
			return false -- (a lightness step: everyone sees it)
		end
		local function enc(v: number): number
			v = math.clamp(v, 0, 1)
			return if v <= 0.0031308 then v * 12.92 else 1.055 * v ^ (1 / 2.4) - 0.055
		end
		for _, m in CVD_M do
			local d = 0
			for row = 1, 3 do
				local va = m[row][1] * lin(a[1]) + m[row][2] * lin(a[2]) + m[row][3] * lin(a[3])
				local vb = m[row][1] * lin(b[1]) + m[row][2] * lin(b[2]) + m[row][3] * lin(b[3])
				d += (enc(va) - enc(vb)) ^ 2
			end
			if math.sqrt(d) < 0.2 then -- (as seen: red / green at one lightness both turn olive, ~0.16 apart)
				return true
			end
		end
		return false
	end
	local statedButtons = 0
	local bareButtons = 0

	local function statesBlock(n: any, path: string, attrs: any)
		local st = n.states
		if type(st) ~= "table" or #st > 0 then
			err(path .. ".states", 'states: {"hover": {"color": "accent"}, "disabled": {"imageAlpha": 0.6}, ...}')
			return
		end
		local known: { [string]: boolean } = {}
		for _, s in STATE_NAMES do
			known[s] = true
		end
		local names: { string } = {}
		for _, s in STATE_NAMES do
			local over = st[s]
			if over == nil then
				continue
			end
			table.insert(names, s)
			if type(over) ~= "table" then
				err(`{path}.states.{s}`, `{s}: an object of overrides (color, textColor, imageColor, ...)`)
				continue
			end
			local parts: { string } = {}
			local keys: { string } = {}
			for k in over do
				table.insert(keys, k)
			end
			table.sort(keys)
			for _, k in keys do
				local v = over[k]
				local kind = STATE_KEYS[k]
				local at = `{path}.states.{s}.{k}`
				if not kind then
					err(
						at,
						`a state overrides color textColor imageColor strokeColor transparency textAlpha imageAlpha image text (not "{k}")`
					)
				elseif kind == "color" then
					local c = color(at, v)
					if c then
						table.insert(parts, `{k}={toHex(c)}`)
						local base = if k == "textColor"
							then color(at, n.textColor or (if theme.text then "text" else "#ffffff"))
							elseif k == "color" then (if n.color then color(at, n.color) else nil)
							elseif k == "imageColor" then { 1, 1, 1 }
							else nil
						if base and hueOnly(base, c) then
							warn(
								at,
								`idle and "{s}" differ by HUE alone — a protanope / deuteranope sees no change (XAG 103): add a lightness step, a picture swap or a shape`
							)
						end
					end
				elseif kind == "alpha" then
					if type(v) ~= "number" or v < 0 or v > 1 then
						err(at, `{k} must be a number 0..1`)
					else
						table.insert(parts, `{k}={v}`)
					end
				elseif kind == "art" then
					local id, nm = image(at, v)
					table.insert(parts, `image={id}`)
					if nm then
						table.insert(parts, `art={nm}`)
					end
				elseif kind == "text" then
					if type(v) ~= "string" or string.find(v, "[;=]") then
						err(at, "text must be a string without ; or =")
					else
						table.insert(parts, `text={v}`)
					end
				end
			end
			attrs["Kit_S_" .. s] = table.concat(parts, ";")
		end
		for k in st do
			if not known[k] then
				err(`{path}.states.{k}`, `unknown state "{tostring(k)}" — {table.concat(STATE_NAMES, " | ")}`)
			end
		end
		if #names > 0 then
			attrs.Kit_States = table.concat(names, ",")
		end
	end

	-- "path": a VECTOR line (Roblox Path2D): crisp at any size, no upload, can draw itself on. A dial's arc, a rule, a
	-- speed line, an underline, a frame —
	--   {"type": "path", "name": "Arc", "size": [400, 400], "points": [[x, y], ...] (px in the node's box) |
	--    "arc": {"from": 200, "to": 340, "r": 0.46} (degrees, 0 = right, clockwise; r = share of the box's short side),
	--    "color": "accent", "thickness": 6, "smooth": true, "closed": false, "draw": {"dur": 0.6, "delay": 0.2},
	--    "outline": {"color": "shadow", "px": 2}}
	-- Compiled to Kit_Path ("x,y;..." as shares of the box) + Kit_Path*; Ui.path builds the Path2D at bind (its
	-- control points are set by method, not a property), the preview and the reel draw the same curve.
	local function pathBlock(n: any, path: string, attrs: any)
		local w = type(n.size) == "table" and tonumber(n.size[1]) or nil
		local h = type(n.size) == "table" and tonumber(n.size[2]) or nil
		if not w or not h or w <= 0 or h <= 0 then
			err(path .. ".size", "a path needs a size in pixels ([w, h]): its points are drawn in that box")
			return
		end
		local pts: { { number } } = {}
		if type(n.arc) == "table" then
			local a0, a1 = tonumber(n.arc.from), tonumber(n.arc.to)
			local r = tonumber(n.arc.r) or 0.45
			if not a0 or not a1 or r <= 0 or r > 1 then
				err(
					path .. ".arc",
					'arc: {"from": 200, "to": 340, "r": 0.46} (degrees clockwise from the right; r 0..1)'
				)
				return
			end
			local steps = math.max(8, math.floor(math.abs(a1 - a0) / 7.5))
			local rr = r * math.min(w, h)
			for i = 0, steps do
				local t = math.rad(a0 + (a1 - a0) * i / steps)
				table.insert(pts, { w / 2 + rr * math.cos(t), h / 2 + rr * math.sin(t) })
			end
		elseif type(n.points) == "table" and #n.points >= 2 then
			for i, p in n.points do
				if type(p) ~= "table" or type(p[1]) ~= "number" or type(p[2]) ~= "number" then
					err(`{path}.points[{i}]`, "a point is [x, y] in pixels of the path's box")
					return
				end
				table.insert(pts, { p[1], p[2] })
			end
		else
			err(path, 'a path needs "points": [[x, y], ...] (2 or more) or an "arc"')
			return
		end
		local enc = {}
		for _, p in pts do
			table.insert(enc, string.format("%.4f,%.4f", p[1] / w, p[2] / h))
		end
		attrs.Kit_Path = table.concat(enc, ";")
		local c = color(path .. ".color", n.color or (if theme.accent then "accent" else "#ffffff")) or { 1, 1, 1 }
		attrs.Kit_PathColor = toHex(c)
		local th = n.thickness or 4
		if type(th) ~= "number" or th <= 0 or th > 60 then
			err(path .. ".thickness", "thickness is pixels, 0..60")
			th = 4
		end
		attrs.Kit_PathThickness = th
		-- "outline": {"color": "shadow", "px": 2}: a darker, wider stroke under the line (a HUD line over any world)
		if n.outline ~= nil then
			local o = n.outline
			local oc = type(o) == "table" and color(path .. ".outline.color", o.color or "shadow") or nil
			local px = type(o) == "table" and tonumber(o.px) or nil
			if not oc or not px or px <= 0 or px > 20 then
				err(
					path .. ".outline",
					'outline: {"color": "shadow", "px": 2} — a darker stroke px wider on each side'
				)
			else
				attrs.Kit_PathOutline = `{toHex(oc)},{px}`
			end
		end
		attrs.Kit_PathSmooth = n.smooth ~= false
		attrs.Kit_PathClosed = n.closed == true
		if n.draw ~= nil then
			local d = n.draw
			local dur = type(d) == "table" and tonumber(d.dur) or nil
			if not dur or dur <= 0 or dur > 10 then
				err(
					path .. ".draw",
					'draw: {"dur": 0.6, "delay": 0} — the line draws itself on when the screen shows'
				)
			else
				attrs.Kit_PathDraw = `{dur},{tonumber(d.delay) or 0}`
			end
		end
	end

	-- UI PARTICLES: burst presets live on the identity (or the screen): "bursts": {"smash": {"sprite":
	-- "art:riff/burst", "count": 14, "life": 0.6, "speed": [220, 520], "spread": 360, "angle": -90, "gravity": 900,
	-- "size": [12, 30], "spin": 240, "colors": ["accent", "#ffffff"], "fade": true, "shrink": true}} — sprites are pooled
	-- ImageLabels Ui.burst flies over the screen (Roblox has no 2D particles). A node's "burst": {"preset": "smash",
	-- "on": "show" | "manual", "delay": 0} fires one when the node shows. The reel draws the same flight.
	local BURST_NUM: { [string]: { number } } = {
		count = { 1, 80, 14 },
		life = { 0.05, 5, 0.6 },
		spread = { 0, 360, 360 },
		angle = { -360, 360, -90 },
		gravity = { -4000, 4000, 900 },
		spin = { -2000, 2000, 180 },
	}
	local BURST_PAIR: { [string]: { number } } = { speed = { 0, 4000, 220, 520 }, size = { 1, 400, 12, 30 } }

	local function burstPreset(at: string, b: any): string?
		if type(b) ~= "table" then
			err(at, 'a burst preset: {"sprite": "art:<identity>/<piece>", "count": 14, "life": 0.6, ...}')
			return nil
		end
		local parts: { string } = {}
		local sprite = b.sprite or "art:disc"
		local id, nm = image(at .. ".sprite", sprite)
		table.insert(parts, `sprite={id}`)
		if nm then
			table.insert(parts, `art={nm}`)
		end
		for k, r in BURST_NUM do
			local v = b[k]
			if v == nil then
				v = r[3]
			elseif type(v) ~= "number" or v < r[1] or v > r[2] then
				err(`{at}.{k}`, `{k} must be a number {r[1]}..{r[2]}`)
				v = r[3]
			end
			table.insert(parts, `{k}={v}`)
		end
		for k, r in BURST_PAIR do
			local v = b[k]
			local lo, hi = r[3], r[4]
			if v ~= nil then
				if
					type(v) ~= "table"
					or type(v[1]) ~= "number"
					or type(v[2]) ~= "number"
					or v[1] < r[1]
					or v[2] > r[2]
					or v[1] > v[2]
				then
					err(`{at}.{k}`, `{k} is [low, high] within {r[1]}..{r[2]}`)
				else
					lo, hi = v[1], v[2]
				end
			end
			table.insert(parts, `{k}={lo},{hi}`)
		end
		local cols: { string } = {}
		for i, c in (if type(b.colors) == "table" then b.colors else { "#ffffff" }) do
			local rgb = color(`{at}.colors[{i}]`, c)
			if rgb then
				table.insert(cols, toHex(rgb))
			end
		end
		table.insert(parts, `colors={table.concat(cols, ",")}`)
		table.insert(parts, `fade={if b.fade == false then 0 else 1}`)
		table.insert(parts, `shrink={if b.shrink == false then 0 else 1}`)
		for k in b do
			if
				not BURST_NUM[k]
				and not BURST_PAIR[k]
				and k ~= "sprite"
				and k ~= "colors"
				and k ~= "fade"
				and k ~= "shrink"
			then
				err(`{at}.{k}`, `a burst has no "{tostring(k)}"`)
			end
		end
		return table.concat(parts, ";")
	end

	-- "sounds": the Sfx EVENTS a control plays (the SFX lane makes them: assets/sounds/_events.json) — {"hover":
	-- "UiHover", "press": "UiClick", "enter": "MenuOpen", "show": "Pop", "selected": "UiConfirm", "disabled": "UiError"}.
	-- Ui fires each on the frame its moment LANDS (the enter when its motion settles, a state when it is set): the
	-- grammar — confirm rises, cancel falls, hover near silent, big moments richer — is the sound set's to keep.
	local SOUND_KEYS: { [string]: boolean } = {
		hover = true,
		press = true,
		enter = true,
		show = true,
		selected = true,
		disabled = true,
		locked = true,
		new = true,
	}
	local function soundsBlock(n: any, path: string, attrs: any)
		if type(n.sounds) ~= "table" then
			err(path .. ".sounds", 'sounds: {"hover": "UiHover", "press": "UiClick", ...} (Sfx event names)')
			return
		end
		for k, v in n.sounds do
			local at = `{path}.sounds.{tostring(k)}`
			if not SOUND_KEYS[k] then
				err(at, "sound moments: hover | press | enter | show | selected | disabled | locked | new")
			elseif type(v) ~= "string" or v == "" then
				err(at, "a sound is an Sfx event name (assets/sounds/_events.json)")
			elseif events and not events[v] then
				err(at, `no Sfx event "{v}" in assets/sounds/_events.json (lune run kit sfx catalog lists them)`)
			else
				attrs["Kit_Snd_" .. k] = v
			end
		end
	end

	local burstNames: { [string]: boolean } = {}
	local pendingBursts: { { at: string, preset: string } } = {}

	local function burstBlock(n: any, path: string, attrs: any)
		local b = n.burst
		local preset = if type(b) == "string" then b elseif type(b) == "table" then b.preset else nil
		if type(preset) ~= "string" then
			err(path .. ".burst", 'burst: "<preset>" or {"preset": "smash", "on": "show" | "manual", "delay": 0}')
			return
		end
		local on = if type(b) == "table" and b.on ~= nil then b.on else "show"
		if on ~= "show" and on ~= "manual" then
			err(path .. ".burst.on", 'on is "show" (fires when the node shows) or "manual" (Ui.burst in code)')
		end
		attrs.Kit_BurstPreset = preset
		attrs.Kit_BurstOn = on
		attrs.Kit_BurstDelay = if type(b) == "table" and type(b.delay) == "number" then b.delay else 0
		table.insert(pendingBursts, { at = path .. ".burst", preset = preset })
	end

	-- "fx": RUNTIME UI MATERIALS (Roblox has no UI shaders; each is built from engine pieces the Ui runtime drives):
	--   shimmer  a light band sweeping across the piece (a white GLINT copy of the picture + a moving UIGradient)
	--   ping     an echo of the piece that grows and fades (a "ready" pulse, a new-item call)
	--   burn_in  the piece revealed by a soft wipe with a lit edge, once, when the screen shows it
	--   split    a glitch: two tinted copies jump apart for a few frames (chromatic split)
	--   flicker  a hologram flicker: the piece dips in short random bursts
	-- [{"kind": "shimmer", "period": 2.6, "width": 0.16, "alpha": 0.6, "angle": 20, "color": "line"}, ...]
	-- A picture's glint is drawn by the plates step (<piece>__glint, uploaded like any art). The runtime reads
	-- Kit_Fx ("kind:k=v,k=v;..."); the reel draws the same children (kit/ui/reel.py), so preview == game.
	local FX: { [string]: { [string]: { number } } } = {
		shimmer = {
			period = { 0.3, 20, 2.6 },
			width = { 0.02, 0.6, 0.16 },
			alpha = { 0.05, 1, 0.6 },
			angle = { -90, 90, 20 },
			delay = { 0, 20, 0 },
		},
		ping = { period = { 0.3, 20, 1.6 }, scale = { 1.01, 2, 1.12 }, alpha = { 0.05, 1, 0.6 }, delay = { 0, 20, 0 } },
		burn_in = {
			dur = { 0.1, 4, 0.6 },
			soft = { 0.01, 0.4, 0.08 },
			angle = { -90, 90, 0 },
			delay = { 0, 10, 0 },
		},
		split = { px = { 1, 30, 4 }, every = { 0.3, 30, 3 }, dur = { 0.03, 1, 0.14 }, alpha = { 0.05, 1, 0.55 } },
		-- (dur 0.2 by default: a burst re-rolls its dip every 1/30 s, and 0.2 s is the most that keeps it at 3 flashes
		-- a second - UI.flashCount; the 0.35 it had could strobe 6 times, and no screen used it)
		flicker = { every = { 0.3, 30, 3.5 }, dur = { 0.05, 2, 0.2 }, depth = { 0.05, 1, 0.4 } },
	}
	local FX_COLOURS = { shimmer = { "color" }, ping = { "color" }, burn_in = { "edge" }, split = { "colors" } }
	local FX_LIST = "shimmer | ping | burn_in | split | flicker"

	local function seqAlpha(points: { { number } }): any
		local kp = {}
		for _, p in points do
			table.insert(kp, { time = p[1], value = p[2], envelope = 0 })
		end
		return { NumberSequence = { keypoints = kp } }
	end

	-- a copy of the node for an fx layer: a white glint of its picture, its text, or its fill
	local function fxCopy(
		name: string,
		path: string,
		class: string,
		props: any,
		attrs: any,
		tint: { number },
		alpha: number
	): any?
		local p: any = {
			Size = { UDim2 = { { 1, 0 }, { 1, 0 } } },
			Position = { UDim2 = { { 0, 0 }, { 0, 0 } } },
			BackgroundTransparency = 1,
			ZIndex = props.ZIndex,
		}
		local cls = class
		if class == "ImageLabel" or class == "ImageButton" then
			local artName = attrs.KitArt
			if type(artName) ~= "string" then
				err(
					path .. ".fx",
					`{name}: a picture's fx needs an "art:<identity>/<piece>" image (its glint is drawn from it)`
				)
				return nil
			end
			local gname = artName .. "__glint"
			if art and not art[gname] then
				err(
					path .. ".fx",
					`{name}: no glint "{gname}" — the plates step draws one for every identity piece a spec gives a {name} (kit art and plate nodes have none): run lune run kit ui`
				)
				return nil
			end
			local gid = image(path .. ".fx", "art:" .. gname)
			cls = "ImageLabel"
			p.Image = gid
			p.Attributes = { Attributes = { KitArt = { String = gname } } } -- (the preview and the vault find it by name)
			p.ImageColor3 = { Color3 = tint }
			p.ImageTransparency = alpha
			for _, k in { "ScaleType", "SliceCenter", "TileSize" } do
				if props[k] ~= nil then
					p[k] = props[k]
				end
			end
			return {
				Name = name,
				ClassName = cls,
				Properties = p,
			}
		elseif class == "TextLabel" or class == "TextButton" then
			cls = "TextLabel"
			for _, k in
				{
					"Text",
					"Font",
					"FontFace",
					"TextSize",
					"TextScaled",
					"TextWrapped",
					"TextXAlignment",
					"TextYAlignment",
					"RichText",
					"LineHeight",
				}
			do
				if props[k] ~= nil then
					p[k] = props[k]
				end
			end
			p.TextColor3 = { Color3 = tint }
			p.TextTransparency = alpha
			return { Name = name, ClassName = cls, Properties = p }
		elseif class == "Frame" or class == "CanvasGroup" then
			cls = "Frame"
			p.BackgroundColor3 = { Color3 = tint }
			p.BackgroundTransparency = alpha
			return { Name = name, ClassName = cls, Properties = p }
		end
		err(path .. ".fx", `{name}: fx works on pictures, text and panels (not a {class})`)
		return nil
	end

	local function fxBlock(n: any, path: string, class: string, props: any, attrs: any, children: { any })
		if type(n.fx) ~= "table" or #n.fx == 0 then
			err(path .. ".fx", `fx: a list of effects [{"{"}"kind": "shimmer"{"}"}] — kinds: {FX_LIST}`)
			return
		end
		-- burn_in and flicker each drive a UIGradient on the node: one UIGradient per node
		local gradFx = 0
		for _, e in n.fx do
			if type(e) == "table" and (e.kind == "burn_in" or e.kind == "flicker") then
				gradFx += 1
			end
		end
		local ownGrad = false
		for _, c in children do
			if c.ClassName == "UIGradient" then
				ownGrad = true
			end
		end
		if gradFx > 0 and ownGrad then
			err(
				path .. ".fx",
				"burn_in / flicker drive the node's own UIGradient: drop its gradient (one UIGradient per node)"
			)
		elseif gradFx > 1 then
			err(path .. ".fx", "burn_in and flicker both need the node's one UIGradient: pick one")
		end
		local enc: { string } = {}
		local seenKinds: { [string]: boolean } = {}
		for i, e in n.fx do
			local at = `{path}.fx[{i}]`
			local kind = type(e) == "table" and e.kind or nil
			local def = kind and FX[kind]
			if not def then
				err(at, `unknown fx "{tostring(kind)}" — kinds: {FX_LIST}`)
				continue
			end
			if seenKinds[kind] then
				err(at, `fx "{kind}" twice on one node`)
				continue
			end
			seenKinds[kind] = true
			local v: { [string]: number } = {}
			local allowed: { [string]: boolean } = { kind = true }
			for k, range in def do
				allowed[k] = true
				local x = e[k]
				if x == nil then
					v[k] = range[3]
				elseif type(x) ~= "number" or x < range[1] or x > range[2] then
					err(`{at}.{k}`, `{kind}.{k} must be a number {range[1]}..{range[2]}`)
					v[k] = range[3]
				else
					v[k] = x
				end
			end
			for _, ck in FX_COLOURS[kind] or {} do
				allowed[ck] = true
			end
			for k in e do
				if not allowed[k] then
					err(`{at}.{k}`, `{kind} has no "{k}"`)
				end
			end
			local flashes, knob = UI.flashCount(kind, v)
			if flashes > UI.FLASH_LIMIT then
				err(
					at,
					`{kind} can flash {flashes} times in one second (WCAG 2.3.1 photosensitivity: at most {UI.FLASH_LIMIT}, the kit holds it at any size) - {knob}`
				)
			end
			local parts = {}
			local keys = {}
			for k in v do
				table.insert(keys, k)
			end
			table.sort(keys)
			for _, k in keys do
				table.insert(parts, `{k}={v[k]}`)
			end
			table.insert(enc, kind .. ":" .. table.concat(parts, ","))
			if kind == "shimmer" then
				local tint = color(at .. ".color", e.color or (if theme.line then "line" else "#ffffff")) or { 1, 1, 1 }
				local layer = fxCopy("Fx_Shimmer", path, class, props, attrs, tint, 0)
				if layer then
					local w, a = v.width, v.alpha
					layer.Children = {
						{
							Name = "Band",
							ClassName = "UIGradient",
							Properties = {
								Rotation = v.angle,
								Offset = { Vector2 = { -1, 0 } }, -- (at rest the band waits off the piece: invisible)
								Transparency = seqAlpha({
									{ 0, 1 },
									{ math.max(0.001, 0.5 - w / 2), 1 },
									{ 0.5, 1 - a },
									{ math.min(0.999, 0.5 + w / 2), 1 },
									{ 1, 1 },
								}),
							},
						},
					}
					table.insert(children, layer)
				end
			elseif kind == "ping" then
				local tint = color(at .. ".color", e.color or (if theme.accent then "accent" else "#ffffff"))
					or { 1, 1, 1 }
				local layer = fxCopy("Fx_Ping", path, class, props, attrs, tint, 1) -- (hidden at rest)
				if layer then
					layer.Children = { { Name = "Grow", ClassName = "UIScale", Properties = { Scale = 1 } } }
					table.insert(children, layer)
				end
			elseif kind == "burn_in" then
				local s = v.soft
				table.insert(children, {
					Name = "Fx_Burn",
					ClassName = "UIGradient",
					Properties = {
						Rotation = v.angle,
						Offset = { Vector2 = { 1, 0 } }, -- (at rest: fully shown; the runtime plays it from -1)
						Transparency = seqAlpha({ { 0, 0 }, { 0.5 - s, 0 }, { 0.5 + s, 1 }, { 1, 1 } }),
					},
				})
				if e.edge ~= "none" then
					local tint = color(at .. ".edge", e.edge or (if theme.accent then "accent" else "#ffffff"))
						or { 1, 1, 1 }
					local layer = fxCopy("Fx_BurnEdge", path, class, props, attrs, tint, 1)
					if layer then
						layer.Children = {
							{
								Name = "Band",
								ClassName = "UIGradient",
								Properties = {
									Rotation = v.angle,
									Offset = { Vector2 = { 1, 0 } },
									Transparency = seqAlpha({
										{ 0, 1 },
										{ 0.5 - s * 2, 1 },
										{ 0.5, 0 },
										{ 0.5 + s * 0.5, 1 },
										{ 1, 1 },
									}),
								},
							},
						}
						table.insert(children, layer)
					end
				end
			elseif kind == "flicker" then
				table.insert(children, {
					Name = "Fx_Flicker",
					ClassName = "UIGradient",
					Properties = { Transparency = seqAlpha({ { 0, 0 }, { 1, 0 } }) }, -- (clear at rest)
				})
			elseif kind == "split" then
				local cols = type(e.colors) == "table" and e.colors or { "#ff2a6d", "#2de2e6" }
				for j, nm in { "Fx_SplitA", "Fx_SplitB" } do
					local tint = color(`{at}.colors[{j}]`, cols[j] or "#ffffff") or { 1, 1, 1 }
					local layer = fxCopy(nm, path, class, props, attrs, tint, 1)
					if layer then
						table.insert(children, layer)
					end
				end
				-- the piece ITSELF on top of its two tinted ghosts (children draw over their parent: during a glitch the
				-- runtime hides the node's own picture and shows this copy, so the split reads as colour fringes, not a wash)
				if class == "ImageLabel" or class == "ImageButton" then
					local p: any = {
						Size = { UDim2 = { { 1, 0 }, { 1, 0 } } },
						Position = { UDim2 = { { 0, 0 }, { 0, 0 } } },
						BackgroundTransparency = 1,
						ZIndex = props.ZIndex,
						Image = props.Image,
						ImageColor3 = props.ImageColor3,
						ImageTransparency = 1,
					}
					for _, k in { "ScaleType", "SliceCenter", "TileSize" } do
						if props[k] ~= nil then
							p[k] = props[k]
						end
					end
					if type(attrs.KitArt) == "string" then
						p.Attributes = { Attributes = { KitArt = { String = attrs.KitArt } } }
					end
					table.insert(children, { Name = "Fx_SplitC", ClassName = "ImageLabel", Properties = p })
				else
					local own = (props.TextColor3 or props.BackgroundColor3 or {}).Color3 or { 1, 1, 1 }
					local layer = fxCopy("Fx_SplitC", path, class, props, attrs, own, 1)
					if layer then
						table.insert(children, layer)
					end
				end
			end
		end
		if #enc > 0 then
			attrs.Kit_Fx = table.concat(enc, ";")
		end
	end

	local function node(raw: any, path: string, parentBg: { number }?, inLayout: boolean, internal: boolean): any
		if type(raw) ~= "table" then
			err(path, "node must be an object")
			return nil
		end
		-- authored = the screen's own node (a user plate is marked kit after expansion so taste checks skip it, but
		-- composition counts it: the accent FIELD is usually a plate)
		local authored = not internal and raw.kit ~= true
		-- record (path, name) for every node so the arcade-ban name-substring check can run at the end.
		-- Use the node's OWN path (parent path .. "." .. name) so the error points at the offending node.
		local nodeSelfPath = if type(raw.name) == "string" and raw.name ~= "" then path .. "." .. raw.name else path
		if type(raw.name) == "string" and raw.name ~= "" then
			table.insert(seenNodeNames, { path = nodeSelfPath, name = raw.name })
		end
		-- record every node's type for the arcade-ban check (the original type, before expand rewrites it): a banned
		-- word may name a HUD component (crosshair, feed ...) or a base type - an identity that bans "plates" bans the
		-- plate node (FieldHud_v1's two corner shades were plates). The node's own path, so the error points at it
		if type(raw.type) == "string" and not seenComponents[raw.type] then
			seenComponents[raw.type] = nodeSelfPath
		end
		if COMPONENTS[raw.type] then
			if raw.type == "keyhint" and spec.identity and art and art[`{spec.identity}/keycap`] then
				-- the identity drew its own key cap: show it as is, the letter in the identity's accent
				raw = table.clone(raw)
				raw.keyColor = raw.keyColor or "identity"
				raw.keyTextColor = raw.keyTextColor or "accent"
			end
			for _, p in UI.componentProblems(raw) do
				err(nodeSelfPath .. "." .. p[1], p[2])
			end
			raw = expand(raw)
		elseif PLATE_TYPES[raw.type] then
			raw = plateNode(raw, path .. "." .. tostring(raw.name))
		elseif raw.type == "counter" then
			raw = counterNode(raw, path .. "." .. tostring(raw.name))
		elseif raw.type == "label" and raw.glyphs ~= nil then
			raw = glyphTextNode(raw, path .. "." .. tostring(raw.name))
		elseif raw.type == "number" then
			raw = numberNode(raw, path .. "." .. tostring(raw.name))
		elseif raw.type == "stat" then
			raw = statNode(raw)
		end
		-- "lettering": the text is display lettering baked by kit/ui/words.py (the `kit ui` words step) into
		-- art:<identity>/w_<slug> — a label becomes that picture, a button carries it as its "Word" child; the text
		-- stays on the node as Kit_Text for game code. Size: the spec's, else the piece's own pixels x lettering.scale
		if
			(raw.type == "label" or raw.type == "button")
			and raw.lettering ~= nil
			and raw.lettering ~= false
			and type(raw.text) == "string"
		then
			local opts = if type(raw.lettering) == "table" then raw.lettering else {}
			local name = opts.name
			if type(name) ~= "string" then
				local s = string.gsub(string.lower(raw.text), "[^%w]+", "_")
				s = string.gsub(s, "^_+", "")
				s = string.gsub(s, "_+$", "")
				name = "w_" .. (if s == "" then "word" else string.sub(s, 1, 40))
			end
			if not spec.identity then
				err(path .. ".lettering", `lettering needs the screen's "identity" (the words are baked into its art)`)
			end
			local key = `{spec.identity or "kit"}/{name}`
			local meta = if art then art[key] else nil
			local size = raw.size
			if size == nil then
				local k = tonumber(opts.scale) or 1
				if type(meta) == "table" and type(meta.size) == "table" then
					size = { math.floor(meta.size[1] * k + 0.5), math.floor(meta.size[2] * k + 0.5) }
				elseif type(meta) == "table" and type(meta.size) == "number" then
					size = { math.floor(meta.size * k + 0.5), math.floor(meta.size * k + 0.5) }
				else
					-- (no art index at all = a plain compile that cannot see art: like every other art check, it does
					-- not fail; with an index, a missing word is an error)
					if art then
						err(
							path .. ".lettering",
							`no lettering art "{key}" yet — run lune run kit ui (its words step bakes it)`
						)
					end
					size = { 200, 60 }
				end
			end
			-- the type gates see the word at its drawn size (cap height ~ 0.6 of the piece's height)
			if type(size) == "table" and type(size[2]) == "number" then
				local drawn = math.floor(size[2] * 0.6 + 0.5)
				table.insert(textSizes, drawn)
				table.insert(textNodes, { path = path .. "." .. tostring(raw.name), size = drawn })
			end
			local attrs = table.clone(raw.attributes or {})
			attrs.Kit_Text = raw.text
			local nraw = table.clone(raw)
			nraw.lettering, nraw.textSize, nraw.role, nraw.font, nraw.textColor = nil, nil, nil, nil, nil
			nraw.size = size
			nraw.attributes = attrs
			if raw.type == "label" then
				nraw.type = "image"
				nraw.text = nil
				nraw.image = "art:" .. key
				nraw.fit = "fit"
			else
				nraw.text = ""
				-- the button's own decorations (a splash, a marker) first, the word LAST and above them: a splash
				-- drawn after the word covered it (the selected SKILL, 2026-10-11)
				local kids = {}
				local top = 2
				for _, c in raw.children or {} do
					table.insert(kids, c)
					if type(c) == "table" and type(c.z) == "number" and c.z >= top then
						top = c.z + 1
					end
				end
				table.insert(kids, {
					type = "image",
					name = "Word",
					image = "art:" .. key,
					fit = "fit",
					size = { "100%", "100%" },
					pos = { 0, 0 },
					z = top,
					kit = true,
				})
				nraw.children = kids
			end
			raw = nraw
		end
		if (raw.type == "label" or raw.type == "button") and raw.stacked and type(raw.text) == "string" then
			local role = raw.role and roles[raw.role]
			local size = raw.textSize or (role and role.size) or 18
			local words = {}
			for w in string.gmatch(raw.text, "%S+") do
				table.insert(words, w)
			end
			local leans = { -7, 5, -9, 3, -6, 8, -4 }
			local step = tonumber(raw.stack_step) or math.floor(size * 0.55 + 0.5)
			local kids = {}
			for i, w in words do
				local inverted = i % 2 == 0
				table.insert(kids, {
					type = "label",
					name = `W{i}`,
					text = w,
					role = raw.role,
					font = raw.font,
					textSize = size,
					textColor = if inverted then "bg" else "text",
					plate = if inverted then "torn" else "torn_black",
					padding = math.floor(size * 0.3 + 0.5),
					rotation = leans[((i - 1) % #leans) + 1],
					align = "center",
					size = { math.floor(#w * size * 0.62 + size * 0.9 + 0.5), math.floor(size * 1.45 + 0.5) },
					pos = { (i - 1) * step, (i - 1) * math.floor(size * 1.15 + 0.5) },
					ransom = raw.ransom,
					ransom_seed = (tonumber(raw.ransom_seed) or 0) + i * 3,
					kit = true,
				})
			end
			local widest = 0
			for i, w in words do
				widest = math.max(widest, (i - 1) * step + math.floor(#w * size * 0.62 + size * 0.9 + 0.5))
			end
			raw = {
				type = if raw.type == "button" then "button" else "panel",
				text = if raw.type == "button" then "" else nil,
				name = raw.name,
				size = raw.size or { widest, #words * math.floor(size * 1.15 + 0.5) + math.floor(size * 0.3 + 0.5) },
				pos = raw.pos,
				anchor = raw.anchor,
				slot = raw.slot,
				z = raw.z,
				rotation = raw.rotation,
				motion = raw.motion,
				visible = raw.visible,
				attributes = { Kit_Stacked = true, Kit_Text = raw.text },
				children = kids,
				kit = true,
			}
		end
		if (raw.type == "label" or raw.type == "button") and raw.ransom and raw.tracking == nil then
			raw.tracking = 0.02 -- ransom letters sit tight, their cutouts touching
		end
		if (raw.type == "label" or raw.type == "button") and raw.tracking ~= nil then
			if type(raw.tracking) ~= "number" or raw.tracking < 0 or raw.tracking > 2 then
				err(
					path .. "." .. tostring(raw.name) .. ".tracking",
					"tracking is letter-spacing in ems: 0.05 (tight) .. 0.5 (spaced caps)"
				)
			else
				local trRole = raw.role and roles[raw.role]
				table.insert(textNodes, {
					path = path .. "." .. tostring(raw.name),
					size = raw.textSize or (trRole and trRole.size) or 18,
					typed = true,
				})
				raw = trackedLabel(raw)
			end
		end
		internal = internal or raw.kit == true
		-- a style fills in what the node did not say
		local n = raw
		if raw.style ~= nil then
			local st = STYLES[raw.style]
			if not st then
				err(path .. ".style", "style must be card | glass | primary | secondary | chip | ghost")
			else
				n = table.clone(raw)
				for k, v in st do
					if n[k] == nil then
						n[k] = v
					end
				end
			end
		end
		-- "rarity": an item card in its tier — the identity's card_<tier> plate and a Kit_Rarity attribute (scripts
		-- and the runtime read it); the identity must define the rarity_<tier> token
		if n.rarity ~= nil then
			local tok = `rarity_{tostring(n.rarity)}`
			if type(n.rarity) ~= "string" or not theme[tok] then
				err(
					path .. ".rarity",
					`rarity "{tostring(n.rarity)}": the identity has no token "{tok}" (common | uncommon | rare | epic | legendary | mythic)`
				)
			else
				n = table.clone(n)
				n.plate = n.plate or `card_{n.rarity}`
				n.attributes = table.clone(n.attributes or {})
				n.attributes.Kit_Rarity = n.rarity
			end
		end
		if n.shadow ~= nil then
			if not n.plate then
				err(path .. ".shadow", "shadow is a dark offset copy of the node's plate: give the node a plate first")
			elseif n.shadow ~= true and (type(n.shadow) ~= "number" or n.shadow < 1 or n.shadow > 24) then
				err(path .. ".shadow", "shadow: true (the identity's offset) | 1..24 (px down)")
			end
		end
		local class = TYPES[n.type]
		if not class then
			err(path .. ".type", "type must be " .. TYPE_LIST)
			return nil
		end
		if type(n.name) ~= "string" or not string.match(n.name, "^[%a_][%w_]*$") then
			err(path .. ".name", "every node needs a name (letters, digits, _) — scripts find it by name")
			return nil
		end
		path = path .. "." .. n.name
		local props: { [string]: any } = {}
		local attrs: { [string]: any } = {}
		local slot = n.slot and UI.SLOTS[n.slot]
		if n.slot ~= nil and not slot then
			err(
				path .. ".slot",
				"slot must be topLeft | top | topRight | left | center | right | bottomLeft | bottom | bottomRight"
			)
		end
		if slot and inLayout then
			warn(path .. ".slot", "a slot inside a layout is ignored — the layout places it")
		end
		local size = udim2(path .. ".size", n.size, { "100%", "100%" })
		props.Size = size
		props.Position = udim2(path .. ".pos", n.pos or (slot and slot.pos), { 0, 0 })
		local anchor = ANCHORS[n.anchor or (slot and slot.anchor) or "topleft"]
		if not anchor then
			err(path .. ".anchor", "anchor must be center | top | bottom | left | right | topleft | ... ")
		else
			props.AnchorPoint = { Vector2 = anchor }
		end
		if n.visible == false then
			props.Visible = false
		end
		if n.rotation then
			props.Rotation = n.rotation
		end
		if n.z then
			props.ZIndex = n.z
		end
		if n.clip then
			props.ClipsDescendants = true
		end
		-- "focus" (UI-X, PARALLAX_FINAL_CLOSURE_SPEC Step 7): how the gamepad / keyboard cursor treats this frame
		-- ("nav" names a control's neighbours; this is the frame's own rule). {"group": true} keeps the cursor among
		-- its children while it is inside (SelectionGroup); "edge": "stop" (the cursor stays at the edge) | "escape"
		-- (it may leave), for all four sides or {"up": ..., "down": ..., "left": ..., "right": ...}. A menu that traps
		-- or loses the pad cursor is the console player's first bug
		if n.focus ~= nil then
			local v = n.focus
			if type(v) ~= "table" then
				err(
					path .. ".focus",
					'focus: {"group": true, "edge": "stop" | "escape" | {"up": ..., "down": ..., ...}}'
				)
			else
				if v.group ~= nil and type(v.group) ~= "boolean" then
					err(path .. ".focus.group", "focus.group is true or false")
				elseif v.group then
					props.SelectionGroup = true
				end
				local ways = { stop = "Stop", escape = "Escape" }
				local edge = v.edge
				if edge ~= nil and type(edge) ~= "string" and type(edge) ~= "table" then
					err(
						path .. ".focus.edge",
						'focus.edge: "stop" | "escape" | {"up": ..., "down": ..., "left": ..., "right": ...}'
					)
					edge = nil
				end
				for _, side in { "up", "down", "left", "right" } do
					local b = if type(edge) == "table" then edge[side] else edge
					if b ~= nil then
						local e = ways[b]
						if not e then
							err(path .. ".focus.edge." .. side, `focus edge {side}: "stop" | "escape"`)
						else
							props["SelectionBehavior" .. string.upper(string.sub(side, 1, 1)) .. string.sub(side, 2)] =
								e
						end
					end
				end
			end
		end
		-- "localize": false (UI-X Step 7) - this node and what it holds are NOT machine-translated (AutoLocalize): a
		-- player's name, a number, a code; on by default as the engine has it
		if n.localize ~= nil then
			if type(n.localize) ~= "boolean" then
				err(
					path .. ".localize",
					"localize is true or false (false: names, numbers, codes are never translated)"
				)
			elseif n.localize == false then
				props.AutoLocalize = false
			end
		end
		if n.autosize then
			local a = ({ x = "X", y = "Y", xy = "XY" })[n.autosize]
			if not a then
				err(path .. ".autosize", "autosize must be x | y | xy (the engine sizes it to its content)")
			else
				props.AutomaticSize = a
			end
		end
		if class == "CanvasGroup" and n.groupAlpha then
			props.GroupTransparency = n.groupAlpha
		end
		if n.type == "path" then
			pathBlock(n, path, attrs)
		end
		if class == "ViewportFrame" then
			attrs.Kit_Model = n.model or ""
			attrs.Kit_ModelSpin = n.spin or 0
			props.BackgroundTransparency = 1
			props.LightColor = { Color3 = color(path .. ".lightColor", n.lightColor or "text") or { 1, 1, 1 } }
			props.Ambient = { Color3 = color(path .. ".ambient", n.ambient or "muted") or { 0.5, 0.5, 0.5 } }
			-- a LIT showcase (v6.14): "lightDirection": [x, y, z] (the key light falls along it), "drag": true (the
			-- player turns the model with a UIDragDetector; its spin pauses while held)
			if n.lightDirection ~= nil then
				local d = n.lightDirection
				if
					type(d) ~= "table"
					or #d ~= 3
					or type(d[1]) ~= "number"
					or type(d[2]) ~= "number"
					or type(d[3]) ~= "number"
				then
					err(
						path .. ".lightDirection",
						"lightDirection is [x, y, z] (the way the key light falls: [-1, -1, -1])"
					)
				else
					props.LightDirection = { Vector3 = d }
				end
			end
			if n.drag ~= nil then
				if type(n.drag) ~= "boolean" then
					err(path .. ".drag", "drag is true (the player turns the model) or false")
				elseif n.drag then
					attrs.Kit_ModelDrag = true
				end
			end
		end

		-- (a path's "color" is its STROKE, never a fill behind it)
		local bg = if n.type == "path" then nil else color(path .. ".color", n.color)
		if bg then
			props.BackgroundColor3 = { Color3 = bg }
			props.BackgroundTransparency = n.transparency or 0
		else
			props.BackgroundTransparency = 1 -- (a button too: the engine's grey default is never a design)
		end
		props.BorderSizePixel = 0
		local effectiveBg = bg or parentBg
		-- a plate's colour is the ground its text sits on (contrast): "<kind>_<token>" is that token's colour
		-- (bubble_good: green), any other piece the identity shape's fill (a card, a frame: the panel colour)
		if type(n.plate) == "string" and not bg then
			local tok = string.match(n.plate, "_(%w+)$")
			local c = if tok and type(theme[tok]) == "string" then hex(theme[tok]) else nil
			-- "plateColor": the plate's tint IS the ground (an ink strip under paper type, an accent splash)
			if n.plateColor ~= nil then
				c = color(path .. ".plateColor", n.plateColor) or c
			end
			-- the INK pieces (torn_black: a paper cutout's dark under-layer, a ransom glyph's dark scrap) ground
			-- their text on the identity's line colour, not on its paper fill
			if
				not c
				and (n.plate == "torn_black" or n.plate == "cut_black")
				and identity
				and identity.shape
				and type(identity.shape.line) == "string"
			then
				c = hex(identity.shape.line)
			end
			if not c and identity and identity.shape and type(identity.shape.fill) == "string" then
				c = hex(identity.shape.fill)
			end
			if c then
				effectiveBg = c
			end
		end
		-- "ground": the colour of the ART this node's text sits on (a drawn card, a painted plate): contrast is
		-- measured against it — a menu over a full-screen picture is not text over the game world
		if n.ground ~= nil and not bg then
			local gc = color(path .. ".ground", n.ground)
			if gc then
				effectiveBg = gc
			end
		end
		local children = {}
		local bgGradient = false

		-- lit surfaces: a gradient on the background ("auto" = the colour, lighter at the top)
		local gradient = n.gradient
		if gradient ~= nil then
			local from, to, rot
			if gradient == "auto" then
				if bg then
					from, to, rot = lighten(bg, 0.12), darken(bg, 0.12), 90
				end
			elseif type(gradient) == "table" then
				from = color(path .. ".gradient.from", gradient.from)
				to = color(path .. ".gradient.to", gradient.to)
				rot = gradient.rot or 90
			else
				err(path .. ".gradient", 'gradient must be "auto" or {"from": c, "to": c, "rot": 90}')
			end
			if from and to then
				-- UIGradient multiplies the background colour: paint the background white, let the gradient colour it
				if bg then
					props.BackgroundColor3 = { Color3 = { 1, 1, 1 } }
				end
				table.insert(children, {
					Name = "Gradient",
					ClassName = "UIGradient",
					Properties = { Color = colorSeq(from, to), Rotation = rot },
				})
				bgGradient = true
			end
		elseif bg and class == "Frame" and n.type == "panel" and not internal then
			local sz = size and size.UDim2
			local big = sz and ((sz[1][1] > 0.2 or sz[1][2] >= 160) and (sz[2][1] > 0.1 or sz[2][2] >= 60))
			local fullScreen = sz and sz[1][1] >= 0.95 and sz[2][1] >= 0.95 -- a scrim/dimmer, not a panel
			if big and not fullScreen and (n.transparency or 0) < 0.5 and not n.stroke then
				warn(
					path,
					'a flat panel (solid fill, no gradient/stroke) reads as a 2014 rectangle — add "style": "card" or "gradient": "auto"'
				)
			end
		end

		if class == "TextLabel" or class == "TextButton" or class == "TextBox" then
			local role = n.role and roles[n.role]
			if n.role ~= nil and not role then
				err(
					path .. ".role",
					"role must be title | heading | body | hint | number"
						.. (if identity then " (or one the identity adds)" else "")
				)
			end
			if class == "TextBox" then
				props.PlaceholderText = n.placeholder or ""
				props.ClearTextOnFocus = false
				n.text = n.text or ""
			end
			if type(n.text) ~= "string" then
				err(path .. ".text", "labels and buttons need text")
			end
			props.Text = n.text or ""
			local textSize = n.textSize or (role and role.size) or 18
			if type(textSize) ~= "number" or textSize < 8 or textSize > 240 then
				err(
					path .. ".textSize",
					"textSize must be 8..240 (over 100 draws TextScaled in its box: the engine caps TextSize at 100)"
				)
			elseif textSize < 12 then
				err(path .. ".textSize", `textSize {textSize} is unreadable on a phone — 14 is the floor for hints`)
			elseif textSize < 14 then
				warn(path .. ".textSize", `textSize {textSize} is hard to read on a phone — use ≥ 14`)
			elseif not internal and minimums.text and textSize < minimums.text then
				warn(
					path .. ".textSize",
					`textSize {textSize} is under the identity's floor of {minimums.text} (measured from its references: it must read from across the room)`
				)
			end
			if not internal then
				table.insert(textSizes, textSize) -- (a tracked label's glyphs are one text, not eight)
				-- (a lettered button keeps an empty Text with its word as art: not a typed glyph)
				table.insert(textNodes, { path = path, size = textSize, typed = (n.text or "") ~= "" })
			end
			if textSize > 100 then
				-- a rank letter, a death word: the engine's TextSize stops at 100, so the box carries the size and
				-- the text scales to it (the preview reads Kit_TextSize for the face it draws)
				props.TextScaled = true
				props.TextSize = 100
				attrs.Kit_TextSize = textSize
			else
				props.TextSize = textSize
			end
			-- "preferredText" (v7, accessibility): the text follows the player's own text size (GuiService.
			-- PreferredTextSize; kit Ui scales it live) - so it must still fit its box at the LARGEST setting
			local pref = if n.preferredText ~= nil then n.preferredText else spec.preferredText
			if pref ~= nil and type(pref) ~= "boolean" then
				err(path .. ".preferredText", "preferredText: true | false")
			elseif pref == true and type(textSize) == "number" and textSize <= 100 then
				attrs.Kit_PreferredText = true
				local hs = size and size.UDim2 and size.UDim2[2]
				local grows = n.autosize == "y" or n.autosize == "xy"
				local boxH = if hs and hs[1] == 0 and type(hs[2]) == "number" and not grows then hs[2] else nil
				local ok, need = UiTextRules.fits(textSize, boxH, tonumber(n.lines))
				if not ok then
					err(
						path .. ".preferredText",
						`text {textSize}px needs {math.ceil(need)}px at the player's Largest text size but its box is {boxH}px tall - it would clip: make the box taller (or "lines"), scale it, or let it grow ("autosize": "y")`
					)
				end
			end
			-- a role's font is an identity font key ("titleFont") or a face name ("Fondamento"): both resolve
			local font = n.font or (role and (theme[role.font] or role.font)) or theme.font or "GothamMedium"
			if not FONTS[font] then
				err(
					path .. ".font",
					`unknown font "{tostring(font)}" — an Enum.Font name (Garamond, Merriweather, Oswald, Michroma, Bangers, GrenzeGotisch...)`
				)
			end
			if identity and n.font and DEFAULT_FACES[n.font] and not internal then
				warn(
					path .. ".font",
					`{n.font} is the habit face, not the identity's — its type is {theme.font} / {theme.titleFont}; use "role" or one of those`
				)
			end
			props.Font = font
			local tc = color(path .. ".textColor", n.textColor or (role and role.color) or "text") or { 1, 1, 1 }
			props.TextColor3 = { Color3 = tc }
			props.TextWrapped = true
			if n.align then
				local x = ({ left = "Left", center = "Center", right = "Right" })[n.align]
				if not x then
					err(path .. ".align", "align must be left | center | right")
				end
				props.TextXAlignment = x
			end
			if n.rich then
				props.RichText = true
			end
			if n.textOutline then
				local oc = color(path .. ".textOutline", n.textOutline)
				if oc then
					table.insert(children, {
						Name = "TextOutline",
						ClassName = "UIStroke",
						Properties = {
							Color = { Color3 = oc },
							Thickness = n.textOutlineWidth or 1.5,
							Transparency = 0.25,
							ApplyStrokeMode = "Contextual",
						},
					})
				end
			end
			if n.textGradient then
				local a = color(path .. ".textGradient", n.textGradient[1])
				local b = color(path .. ".textGradient", n.textGradient[2])
				if a and b then
					props.TextColor3 = { Color3 = { 1, 1, 1 } }
					table.insert(children, {
						Name = "TextGradient",
						ClassName = "UIGradient",
						Properties = { Color = colorSeq(a, b), Rotation = 90 },
					})
				end
			end
			if effectiveBg and not n.textOutline then
				local ratio = UI.contrast(tc, effectiveBg)
				local shown = math.floor(ratio * 10) / 10
				if ratio < 3 then
					err(path, `text contrast {shown}:1 is unreadable (need ≥ 4.5) — change textColor or color`)
				elseif ratio < 4.5 then
					warn(path, `text contrast {shown}:1 is below 4.5 (hard to read on phones)`)
				end
			elseif not effectiveBg and not n.textOutline and not internal then
				warn(
					path,
					'text over the game world with no background: add "textOutline": "shadow" so it reads on any scene'
				)
			end
			if class == "TextButton" or class == "TextBox" then
				props.AutoButtonColor = if class == "TextButton" then not n.motion else nil
				local h = size and size.UDim2 and size.UDim2[2]
				if h and h[1] == 0 and h[2] < 44 then
					warn(path, `button is {h[2]}px tall — touch targets should be ≥ 44px`)
				elseif h and h[1] == 0 and minimums.button and h[2] < minimums.button then
					warn(path, `button is {h[2]}px tall — the identity's floor is {minimums.button}px`)
				end
			end
			-- "plate": the identity's drawn piece behind a button / label (the selected row's highlight, a ribbon)
			if n.plate and class ~= "TextBox" then
				-- "shadow": the same piece, dark, a few px down and under the plate (the sticker look)
				if n.shadow then
					local px = if type(n.shadow) == "number"
						then n.shadow
						else (identity and identity.shape and tonumber(identity.shape.shadow)) or 6
					local shadowKid = node({
						type = "plate",
						name = "Shadow",
						plate = n.plate,
						size = { "100%", "100%" },
						pos = { 0, px },
						color = "shadow",
						imageAlpha = 0.5,
						z = 0,
						kit = true,
					}, path, effectiveBg, false, true)
					if shadowKid then
						table.insert(children, shadowKid)
					end
				end
				local plateKid = node({
					type = "plate",
					name = "Plate",
					plate = n.plate,
					color = n.plateColor,
					size = { "100%", "100%" },
					kit = true,
				}, path, effectiveBg, false, true)
				if plateKid then
					table.insert(children, plateKid)
				end
			end
			-- a UIGradient tints EVERYTHING its parent draws, text included (that is how gradient text works):
			-- so a gradient-backed button/label carries its text in a child "Label" the gradient cannot reach;
			-- a plate-backed one too (children draw over their parent's own text)
			if (bgGradient or n.plate) and class ~= "TextBox" then
				local labelProps: { [string]: any } = {
					Size = { UDim2 = { { 1, 0 }, { 1, 0 } } },
					BackgroundTransparency = 1,
					Text = props.Text,
					TextSize = props.TextSize,
					Font = props.Font,
					TextColor3 = props.TextColor3,
					TextWrapped = true,
					TextXAlignment = props.TextXAlignment,
					RichText = props.RichText,
				}
				local labelKids, keep = {}, {}
				for _, c in children do
					if c.Name == "TextOutline" or c.Name == "TextGradient" then
						table.insert(labelKids, c)
					else
						table.insert(keep, c)
					end
				end
				children = keep
				props.Text = ""
				table.insert(children, {
					Name = "Label",
					ClassName = "TextLabel",
					Properties = labelProps,
					Children = if #labelKids > 0 then labelKids else nil,
				})
			end
		elseif class == "ImageButton" and n.image == nil and n.plate then
			-- a plate-backed imagebutton: the plate child is its whole look (a bubble button with an icon inside)
			props.Image = ""
			props.BackgroundTransparency = 1
			local h = size and size.UDim2 and size.UDim2[2]
			if h and h[1] == 0 and h[2] < 44 then
				warn(path, `button is {h[2]}px tall — touch targets should be ≥ 44px`)
			elseif h and h[1] == 0 and minimums.button and h[2] < minimums.button then
				warn(path, `button is {h[2]}px tall — the identity's floor is {minimums.button}px`)
			end
		elseif class == "ImageLabel" or class == "ImageButton" then
			-- (a flipbook names its own first frame: no "image" needed)
			local id, artName = "", nil
			if not (n.image == nil and type(n.flipbook) == "table") then
				id, artName = image(path .. ".image", n.image)
			end
			props.Image = id
			if not internal then
				table.insert(imageNodes, path)
			end
			if artName then
				attrs.KitArt = artName
				if minimums.icon and string.find(artName, "/icon_", 1, true) then
					local sz = size and size.UDim2
					local px = if sz and sz[1][1] == 0 then sz[1][2] else nil
					if px and px < minimums.icon then
						warn(path .. ".size", `icon is {px}px — the identity's floor is {minimums.icon}px`)
					end
				end
				local meta = art and art[artName]
				if meta and meta.slice and n.fit == nil then
					props.ScaleType = "Slice"
					local s = meta.slice
					props.SliceCenter = { Rect = { { s[1], s[2] }, { s[3], s[4] } } }
				end
			end
			-- "flipbook": a frame sequence the picture plays in game (Ui.flipbook) — a smear card's swap, a spun
			-- logo, a growing drip: {"frames": "<id>/<p>_{k}" | ["<id>/<a>", ...], "count": n, "fps": 12,
			-- "loop": true, "play": "auto" | "manual"}; every frame's uploaded id rides on the node (Kit_Flip)
			if n.flipbook ~= nil then
				local fb = n.flipbook
				local names: { string } = {}
				if type(fb) ~= "table" then
					err(path .. ".flipbook", 'flipbook: {"frames": "<id>/<piece>_{k}", "count": n, "fps": 12}')
				elseif type(fb.frames) == "table" then
					for _, f in fb.frames do
						table.insert(names, tostring(f))
					end
				elseif type(fb.frames) == "string" and type(fb.count) == "number" and fb.count >= 1 then
					local pad = string.match(fb.frames, "{k:(%d+)}")
					for k = 0, math.floor(fb.count) - 1 do
						local ks = if pad then string.format(`%0{pad}d`, k) else tostring(k)
						local nm = string.gsub(fb.frames, "{k:?%d*}", ks)
						table.insert(names, nm)
					end
				else
					err(
						path .. ".flipbook.frames",
						'frames: a pattern with "{k}" (or "{k:3}" for 000) and a "count", or a list of art names'
					)
				end
				local fps = tonumber(type(fb) == "table" and fb.fps or nil) or 12
				if fps <= 0 or fps > 60 then
					err(path .. ".flipbook.fps", "fps must be 1..60")
					fps = 12
				end
				local play = type(fb) == "table" and fb.play or "auto"
				if play ~= "auto" and play ~= "manual" then
					err(
						path .. ".flipbook.play",
						'play is "auto" (starts when bound) or "manual" (Ui.flipbook in code)'
					)
				end
				local flipIds = {}
				for i, nm in names do
					local fid = image(`{path}.flipbook.frames[{i}]`, "art:" .. nm)
					table.insert(flipIds, fid)
				end
				if #names > 0 then
					if n.image == nil then
						local fid, fname = image(path .. ".flipbook", "art:" .. names[1])
						props.Image = fid
						attrs.KitArt = fname
					end
					attrs.Kit_Flip = table.concat(flipIds, ";")
					attrs.Kit_FlipArt = table.concat(names, ";")
					attrs.Kit_FlipFps = fps
					attrs.Kit_FlipLoop = not (type(fb) == "table" and fb.loop == false)
					attrs.Kit_FlipPlay = play
				end
			end
			if n.slice then
				props.ScaleType = "Slice"
				props.SliceCenter = { Rect = { { n.slice[1], n.slice[2] }, { n.slice[3], n.slice[4] } } }
			end
			if n.fit then
				local st = ({ fit = "Fit", crop = "Crop", stretch = "Stretch", tile = "Tile" })[n.fit]
				if not st then
					err(path .. ".fit", "fit must be fit | crop | stretch | tile")
				end
				props.ScaleType = st
				if st == "Tile" then
					local meta = artName and art and art[artName]
					local t = n.tile or (meta and meta.size) or 128
					props.TileSize = { UDim2 = { { 0, t }, { 0, t } } }
				end
			end
			if n.imageColor then
				local ic = color(path .. ".imageColor", n.imageColor)
				if ic then
					props.ImageColor3 = { Color3 = ic }
					if (n.imageAlpha or 0) < 0.5 then
						effectiveBg = ic -- text on a tinted image (a key cap, a badge) sits on that colour
					end
				end
			end
			if n.imageAlpha then
				props.ImageTransparency = n.imageAlpha
			end
			if n.halfGradient then
				-- radial-fill half (ring component): opaque half, rotated to reveal the arc
				table.insert(children, {
					Name = "Gradient",
					ClassName = "UIGradient",
					Properties = {
						Rotation = n.halfGradient,
						Transparency = {
							NumberSequence = {
								keypoints = {
									{ time = 0, value = 0, envelope = 0 },
									{ time = 0.499, value = 0, envelope = 0 },
									{ time = 0.5, value = 1, envelope = 0 },
									{ time = 1, value = 1, envelope = 0 },
								},
							},
						},
					},
				})
			end
			if class == "ImageButton" then
				local h = size and size.UDim2 and size.UDim2[2]
				if h and h[1] == 0 and h[2] < 44 then
					warn(path, `button is {h[2]}px tall — touch targets should be ≥ 44px`)
				elseif h and h[1] == 0 and minimums.button and h[2] < minimums.button then
					warn(path, `button is {h[2]}px tall — the identity's floor is {minimums.button}px`)
				end
			end
		elseif class == "ScrollingFrame" then
			props.ScrollBarThickness = 6
			props.AutomaticCanvasSize = "Y"
			props.CanvasSize = { UDim2 = { { 0, 0 }, { 0, 0 } } }
		end

		-- "plate" on a panel or an imagebutton: the identity's drawn piece (a bubble, a card) IS the node; "shadow"
		-- puts its dark copy under it. The children draw over the plate (it is inserted first, ZIndex 1 like them).
		if n.plate and ((class == "Frame" and n.type == "panel") or class == "ImageButton") then
			if n.shadow then
				local px = if type(n.shadow) == "number"
					then n.shadow
					else (identity and identity.shape and tonumber(identity.shape.shadow)) or 6
				local shadowKid = node({
					type = "plate",
					name = "Shadow",
					plate = n.plate,
					size = { "100%", "100%" },
					pos = { 0, px },
					color = "shadow",
					imageAlpha = 0.5,
					z = 0,
					kit = true,
				}, path, effectiveBg, false, true)
				if shadowKid then
					table.insert(children, shadowKid)
				end
			end
			local plateKid = node({
				type = "plate",
				name = "Plate",
				plate = n.plate,
				color = n.plateColor,
				size = { "100%", "100%" },
				kit = true,
			}, path, effectiveBg, false, true)
			if plateKid then
				table.insert(children, plateKid)
			end
		end
		if n.type == "bar" then
			local value = n.value or 1
			if type(value) ~= "number" or value < 0 or value > 1 then
				err(path .. ".value", "bar value must be 0..1 (scripts update it: Ui.bar(node, v))")
				value = 1
			end
			local fill = color(path .. ".fill", n.fill or "accent") or { 1, 1, 1 }
			local fillChildren = {}
			local r = radius(path .. ".radius", n.radius)
			if r then
				table.insert(fillChildren, {
					Name = "Corner",
					ClassName = "UICorner",
					Properties = { CornerRadius = { UDim = { 0, math.floor(r + 0.5) } } },
				})
			end
			local fg = n.fillGradient
			if fg then
				local a, b = color(path .. ".fillGradient", fg[1]), color(path .. ".fillGradient", fg[2])
				if a and b then
					fill = { 1, 1, 1 }
					table.insert(fillChildren, {
						Name = "Gradient",
						ClassName = "UIGradient",
						Properties = { Color = colorSeq(a, b) },
					})
				end
			end
			-- WCAG 1.4.11 NON-TEXT CONTRAST: a meter is read by its fill against its track - under 3:1 the player cannot
			-- read how full it is (a drawn track is art: not measured here; a see-through track is a blend: not either)
			if not n.track then
				local track = if bg and (n.transparency or 0) < 0.5 then bg elseif not bg then parentBg else nil
				local ends: { { number }? } = if fg
					then { color(path .. ".fillGradient", fg[1]), color(path .. ".fillGradient", fg[2]) }
					else { fill }
				if track then
					local worst = math.huge
					for _, c in ends do
						if c then
							worst = math.min(worst, UI.contrast(c, track))
						end
					end
					if worst < 3 then
						-- a WARNING, like text between 3 and 4.5: a dark-red meter on near-black is a genre's look (the
						-- souls starter's own HP reads 2.1:1 and reads in play by its frame), so the gate names it, the
						-- owner's eye decides
						warn(
							path .. ".fill",
							`bar fill against its track is {math.floor(worst * 10) / 10}:1 - under the 3:1 a meter needs (WCAG 1.4.11 non-text contrast): darken the track, brighten the fill, or give it a frame`
						)
					end
				end
			end
			-- "ghost": the damage trail — a second fill behind the real one that follows it late (Souls, fighting games)
			if n.ghost then
				local gc = color(path .. ".ghostColor", n.ghostColor or "warn") or { 1, 0.8, 0.3 }
				attrs.Kit_Ghost = true
				table.insert(children, {
					Name = "Ghost",
					ClassName = "Frame",
					Properties = {
						Size = { UDim2 = { { value, 0 }, { 1, 0 } } },
						BackgroundColor3 = { Color3 = gc },
						BorderSizePixel = 0,
					},
					Children = if r then { fillChildren[1] } else nil,
				})
			end
			-- "fillGloss": the candy look — the top half of the fill lit white (simulators, casual)
			if n.fillGloss then
				table.insert(fillChildren, {
					Name = "Gloss",
					ClassName = "Frame",
					Properties = {
						Size = { UDim2 = { { 1, 0 }, { 0.42, 0 } } },
						BackgroundColor3 = { Color3 = { 1, 1, 1 } },
						BackgroundTransparency = 0.68,
						BorderSizePixel = 0,
					},
					Children = if r then { fillChildren[1] } else nil,
				})
			end
			-- "track": the identity's drawn track (9-slice) is the bar's ground; the bar's own colour goes away
			if n.track then
				local trackKid = node({
					type = "plate",
					name = "Track",
					plate = if type(n.track) == "string" then n.track else "track_chunky",
					size = { "100%", "100%" },
					z = 0,
					kit = true,
				}, path, effectiveBg, false, true)
				if trackKid then
					table.insert(children, trackKid)
					props.BackgroundTransparency = 1
				end
			end
			-- a lit core: a brighter hairline along the top of the fill, so the bar reads as a lit strip, not a flat
			-- rectangle ("core": false turns it off)
			if n.core ~= false then
				local base = if fg then color(path .. ".fillGradient", fg[1]) else fill
				table.insert(fillChildren, {
					Name = "Core",
					ClassName = "Frame",
					Properties = {
						Size = { UDim2 = { { 1, 0 }, { 0, 2 } } },
						Position = { UDim2 = { { 0, 0 }, { 0, 0 } } },
						BackgroundColor3 = { Color3 = lighten(base or fill, 0.45) },
						BackgroundTransparency = 0.25,
						BorderSizePixel = 0,
					},
				})
			end
			table.insert(children, {
				Name = "Fill",
				ClassName = "Frame",
				Properties = {
					Size = { UDim2 = { { value, 0 }, { 1, 0 } } },
					BackgroundColor3 = { Color3 = fill },
					BorderSizePixel = 0,
				},
				Children = if #fillChildren > 0 then fillChildren else nil,
			})
			-- "caps": the identity's end pieces on both ends (ornamental bar ends)
			if n.caps then
				local capPlate = if type(n.caps) == "string" then n.caps else "cap"
				local capSize = n.capSize or 22
				local kids = table.clone(n.children or {})
				table.insert(kids, 1, {
					type = "plate",
					name = "CapL",
					plate = capPlate,
					size = { capSize, capSize },
					pos = { 0, "50%" },
					anchor = "right",
					z = 2,
				})
				table.insert(kids, 2, {
					type = "plate",
					name = "CapR",
					plate = capPlate,
					size = { capSize, capSize },
					pos = { "100%", "50%" },
					anchor = "left",
					rotation = 180,
					z = 2,
				})
				n = table.clone(n)
				n.children = kids
			end
		end
		if n.aspect ~= nil then
			if type(n.aspect) ~= "number" or n.aspect <= 0 then
				err(path .. ".aspect", "aspect must be width/height > 0 (e.g. 1.5)")
			else
				table.insert(children, {
					Name = "Aspect",
					ClassName = "UIAspectRatioConstraint",
					Properties = { AspectRatio = n.aspect },
				})
			end
		end
		local r = radius(path .. ".radius", n.radius)
		if r then
			if not internal and r < 999 and raw.radius ~= nil then
				table.insert(radiiUsed, r) -- (a radius the spec chose; a style's default is the kit's choice)
			end
			table.insert(children, {
				Name = "Corner",
				ClassName = "UICorner",
				Properties = { CornerRadius = { UDim = { 0, math.floor(r + 0.5) } } },
			})
		end
		if n.stroke then
			local sc = color(path .. ".stroke", n.stroke)
			if sc then
				local strokeKids = nil
				if n.strokeGradient then
					local a = color(path .. ".strokeGradient", n.strokeGradient[1])
					local b = color(path .. ".strokeGradient", n.strokeGradient[2])
					if a and b then
						sc = { 1, 1, 1 }
						strokeKids = {
							{
								Name = "Gradient",
								ClassName = "UIGradient",
								Properties = { Color = colorSeq(a, b), Rotation = 45 },
							},
						}
					end
				end
				table.insert(children, {
					Name = "Stroke",
					ClassName = "UIStroke",
					Properties = {
						Color = { Color3 = sc },
						Thickness = n.strokeWidth or 1.5,
						Transparency = n.strokeAlpha or 0,
						ApplyStrokeMode = "Border",
					},
					Children = strokeKids,
				})
			end
		end
		-- "nativeShadow": the ENGINE's drop shadow (UIShadow, 2026) instead of a drawn shadow plate — true, or
		-- {blur = px, offset = {x, y}, spread = px, color = token|#hex, alpha = 0..1 (opacity), text = true (from the
		-- glyphs, a native text shadow)}; compared against the drawn plate in the booth before an identity adopts it
		if n.nativeShadow ~= nil and n.nativeShadow ~= false then
			local ns = if type(n.nativeShadow) == "table" then n.nativeShadow else {}
			local off = if type(ns.offset) == "table" then ns.offset else { 0, 6 }
			local blur = tonumber(ns.blur) or 12
			local spread = tonumber(ns.spread) or 0
			local alpha = tonumber(ns.alpha) or 0.55
			if blur < 0 or alpha < 0 or alpha > 1 or type(off[1]) ~= "number" or type(off[2]) ~= "number" then
				err(
					path .. ".nativeShadow",
					"nativeShadow: {blur = px >= 0, offset = {x, y} px, spread = px, color, alpha = 0..1 (opacity), text = true}"
				)
			end
			local shColor = if ns.color ~= nil then color(path .. ".nativeShadow.color", ns.color) else nil
			table.insert(children, {
				Name = "Shadow",
				ClassName = "UIShadow",
				Properties = {
					BlurRadius = { UDim = { 0, math.floor(blur + 0.5) } },
					Offset = { UDim2 = { { 0, math.floor(off[1] + 0.5) }, { 0, math.floor(off[2] + 0.5) } } },
					Spread = { UDim2 = { { 0, math.floor(spread + 0.5) }, { 0, math.floor(spread + 0.5) } } },
					Color = { Color3 = shColor or { 0, 0, 0 } },
					Transparency = 1 - alpha,
					Mode = if ns.text == true then "Text" else "Shape",
				},
			})
		end
		if n.padding then
			local p = { UDim = { 0, math.floor((tonumber(n.padding) or 0) + 0.5) } } -- (a UDim offset is whole pixels: Rojo refuses 2.6)
			table.insert(children, {
				Name = "Padding",
				ClassName = "UIPadding",
				Properties = { PaddingTop = p, PaddingBottom = p, PaddingLeft = p, PaddingRight = p },
			})
		end
		local hasLayout = n.layout ~= nil
		if n.layout and n.layout.grid then
			local g = n.layout.grid
			if n.layout.flex ~= nil or n.layout.lineAlign ~= nil then
				err(
					path .. ".layout.flex",
					"flex / lineAlign are a LIST's (UIListLayout): a grid's cells keep their size"
				)
			end
			if type(g) ~= "table" or type(g[1]) ~= "number" or type(g[2]) ~= "number" then
				err(path .. ".layout.grid", "grid must be [cellWidth, cellHeight] in pixels")
			else
				table.insert(children, {
					Name = "Layout",
					ClassName = "UIGridLayout",
					Properties = {
						CellSize = { UDim2 = { { 0, g[1] }, { 0, g[2] } } },
						CellPadding = {
							UDim2 = {
								{ 0, math.floor((n.layout.gap or 8) + 0.5) },
								{ 0, math.floor((n.layout.gap or 8) + 0.5) },
							},
						},
						SortOrder = "LayoutOrder",
						HorizontalAlignment = "Center",
					},
				})
			end
		elseif n.layout then
			local l = n.layout
			local dir = if l.dir == "horizontal" then "Horizontal" else "Vertical"
			local alignMap = {
				center = "Center",
				start = if dir == "Vertical" then "Left" else "Top",
				["end"] = if dir == "Vertical" then "Right" else "Bottom",
			}
			local align = alignMap[l.align or "center"]
			if not align then
				err(path .. ".layout.align", "align must be center | start | end")
			end
			local layoutProps: { [string]: any } = {
				FillDirection = dir,
				Padding = { UDim = { 0, math.floor((l.gap or 8) + 0.5) } }, -- (whole pixels: a fractional gap broke the Rojo build)
				SortOrder = "LayoutOrder",
			}
			-- "justify": where the run of children sits along the list's own axis (start | center | end)
			local justifyMap = {
				center = "Center",
				start = if dir == "Vertical" then "Top" else "Left",
				["end"] = if dir == "Vertical" then "Bottom" else "Right",
			}
			local justify = l.justify and justifyMap[l.justify]
			if l.justify ~= nil and not justify then
				err(path .. ".layout.justify", "justify must be center | start | end")
			end
			if dir == "Vertical" then
				layoutProps.HorizontalAlignment = align or "Center"
				layoutProps.VerticalAlignment = justify or "Top"
			else
				layoutProps.VerticalAlignment = align or "Center"
				layoutProps.HorizontalAlignment = justify or (if l.align == "end" then "Right" else "Left")
			end
			if l.wrap then
				layoutProps.Wraps = true
			end
			-- FLEX (v7): how the list spends spare room along its own axis, and how items sit across a wrapped line
			if l.flex ~= nil then
				local flexMap = {
					fill = "Fill",
					between = "SpaceBetween",
					around = "SpaceAround",
					evenly = "SpaceEvenly",
					none = "None",
				}
				local f = flexMap[l.flex]
				if not f then
					err(path .. ".layout.flex", "flex: fill | between | around | evenly | none")
				elseif dir == "Horizontal" then
					layoutProps.HorizontalFlex = f
				else
					layoutProps.VerticalFlex = f
				end
			end
			if l.lineAlign ~= nil then
				local la = ({
					start = "Start",
					center = "Center",
					["end"] = "End",
					stretch = "Stretch",
					auto = "Automatic",
				})[l.lineAlign]
				if not la then
					err(path .. ".layout.lineAlign", "lineAlign: start | center | end | stretch | auto")
				else
					layoutProps.ItemLineAlignment = la
				end
			end
			table.insert(children, { Name = "Layout", ClassName = "UIListLayout", Properties = layoutProps })
		end
		-- motion v2: "enter" and "loop" are a word or a choreography {type, delay, duration, ease} (+ stagger);
		-- an identity's motion.enter fills in what the node did not say; "stagger" on a container spaces its children
		if n.motion ~= nil then
			if type(n.motion) ~= "table" then
				err(
					path .. ".motion",
					'motion must be {"hover": "lift|grow|glow", "press": "sink", "enter": "fade" | {"type": "slam", "delay": 0.2, "duration": 0.6, "ease": "back"}, "loop": "pulse", "stagger": 0.06}'
				)
			else
				local m = n.motion
				local hover = { lift = true, grow = true, glow = true, brighten = true, none = true }
				if m.hover ~= nil then
					if not hover[m.hover] then
						err(path .. ".motion.hover", "hover: lift | grow | glow | brighten | none")
					elseif m.hover ~= "none" then
						attrs.Motion_hover = m.hover
					end
				end
				if m.press ~= nil then
					if m.press ~= "sink" and m.press ~= "flash" then
						err(path .. ".motion.press", "press: sink | flash")
					else
						attrs.Motion_press = m.press
					end
				end
				if m.enter ~= nil then
					local e = if type(m.enter) == "string" then { type = m.enter } else m.enter
					if type(e) ~= "table" or not ENTERS[e.type] then
						err(
							path .. ".motion.enter",
							"enter: fade | rise | pop | slam | swell | drop | wipe | sweep | typewriter (a word, or {type, delay, duration, ease})"
						)
					else
						for k in e do
							if k ~= "type" and k ~= "delay" and k ~= "duration" and k ~= "ease" then
								err(path .. ".motion.enter." .. tostring(k), "enter keys: type, delay, duration, ease")
							end
						end
						local def = if type(idMotion.enter) == "table" then idMotion.enter else {}
						attrs.Motion_enter = e.type
						attrs.Motion_enter_delay = e.delay or def.delay or 0
						attrs.Motion_enter_duration = e.duration or def.duration or 0.35
						local ease = e.ease or def.ease or "quad"
						if not EASES[ease] then
							err(path .. ".motion.enter.ease", "ease: quad | sine | back | expo | linear | elastic")
						end
						attrs.Motion_enter_ease = ease
						if parentStagger <= 0 then
							table.insert(enterDelays, attrs.Motion_enter_delay)
						end
					end
				end
				if m.loop ~= nil then
					local lp = if type(m.loop) == "string" then { type = m.loop } else m.loop
					if type(lp) ~= "table" or not LOOPS[lp.type] then
						err(
							path .. ".motion.loop",
							"loop: pulse | spin | blink | breathe | flicker | sweep | glint (a word, or {type, speed})"
						)
					else
						attrs.Motion_loop = lp.type
						attrs.Motion_loop_speed = lp.speed or 1
						local flashes = UI.loopFlashCount(lp.type, tonumber(lp.speed) or 1)
						if flashes > UI.FLASH_LIMIT then
							err(
								path .. ".motion.loop",
								`a {lp.type} loop at speed {tostring(lp.speed)} flashes {flashes} times in one second (WCAG 2.3.1 photosensitivity: at most {UI.FLASH_LIMIT}) - a lower speed`
							)
						end
					end
				end
				if m.stagger ~= nil then
					if type(m.stagger) ~= "number" or m.stagger < 0 or m.stagger > 1 then
						err(path .. ".motion.stagger", "stagger: seconds between each child's enter (0.03 .. 0.2)")
					else
						attrs.Motion_stagger = m.stagger
					end
				end
				for k in m do
					if k ~= "hover" and k ~= "press" and k ~= "enter" and k ~= "loop" and k ~= "stagger" then
						err(path .. ".motion." .. tostring(k), "motion keys: hover, press, enter, loop, stagger")
					end
				end
			end
		end
		for k, v in n.attributes or {} do
			attrs[k] = v
		end
		-- "at": a different size / position / text size / visibility per viewport — the phone reflow. The runtime
		-- (Ui.scale) and the preview apply the override of the viewport they are on; the attribute carries it as
		-- "Size=sx,ox,sy,oy|Position=...|TextSize=n|Visible=false|Anchor=ax,ay"
		local scaledAt: { [string]: { string } } = {}
		local myAtScale: { [string]: number } = table.clone(parentAtScale)
		if type(n.at) == "table" then
			for vp, over in n.at do
				if type(over) == "table" and over.scale ~= nil then
					if type(over.scale) ~= "number" or over.scale <= 0 or over.scale > 2 then
						err(`{path}.at.{vp}.scale`, "scale must be a number in (0, 2]")
					else
						myAtScale[vp] = (myAtScale[vp] or 1) * over.scale
					end
				end
			end
		end
		do
			-- the inherited / own scale as Size + Position overrides (an explicit size / pos at that viewport wins)
			local base = if size then size.UDim2 else nil
			local basePos = if props.Position then props.Position.UDim2 else nil
			for vp, k in myAtScale do
				if k ~= 1 and (base or basePos) then
					local over = if type(n.at) == "table" and type(n.at[vp]) == "table" then n.at[vp] else {}
					local parts = {}
					if base and over.size == nil then
						table.insert(
							parts,
							`Size={base[1][1]},{math.floor(base[1][2] * k + 0.5)},{base[2][1]},{math.floor(
								base[2][2] * k + 0.5
							)}`
						)
					end
					if basePos and over.pos == nil and parentAtScale[vp] ~= nil and parentAtScale[vp] ~= 1 then
						local pk = parentAtScale[vp]
						table.insert(
							parts,
							`Position={basePos[1][1]},{math.floor(basePos[1][2] * pk + 0.5)},{basePos[2][1]},{math.floor(
								basePos[2][2] * pk + 0.5
							)}`
						)
					end
					-- text scales with its box (a scaled group's labels overflowed their shrunken boxes otherwise)
					if over.textSize == nil and type(n.text) == "string" and n.text ~= "" then
						local role = if type(n.role) == "string" then roles[n.role] else nil
						local ts = tonumber(n.textSize) or (if role then tonumber(role.size) else nil)
						if ts then
							ts = math.min(ts, 100) -- (the engine's TextSize ceiling: scale what is drawn)
							table.insert(parts, `TextSize={math.max(8, math.floor(ts * k + 0.5))}`)
						end
					end
					if #parts > 0 then
						scaledAt[vp] = parts
					end
				end
			end
		end
		if n.at ~= nil then
			if type(n.at) ~= "table" then
				err(
					path .. ".at",
					'at must be {"phone": {"size": [...], "pos": [...], "textSize": n, "visible": false}, "tablet": {...}}'
				)
			else
				for vp, over in n.at do
					if vp ~= "phone" and vp ~= "tablet" and vp ~= "desktop" or type(over) ~= "table" then
						err(path .. ".at." .. tostring(vp), "at keys: phone | tablet | desktop, each an object")
					else
						local parts = {}
						for k, v in over do
							if k == "size" or k == "pos" then
								local u = udim2(`{path}.at.{vp}.{k}`, v, { 0, 0 })
								if u then
									local a, b = u.UDim2[1], u.UDim2[2]
									table.insert(
										parts,
										`{if k == "size" then "Size" else "Position"}={a[1]},{a[2]},{b[1]},{b[2]}`
									)
								end
							elseif k == "textSize" then
								if type(v) ~= "number" or v < 8 or v > 100 then
									err(
										`{path}.at.{vp}.textSize`,
										"textSize must be 8..100 (an at-override cannot scale)"
									)
								else
									table.insert(parts, `TextSize={v}`)
								end
							elseif k == "scale" then
								continue -- (applied above as Size / Position / TextSize, and passed down to the children)
							elseif k == "visible" then
								table.insert(parts, `Visible={if v then "true" else "false"}`)
							elseif k == "anchor" then
								local a = ANCHORS[v]
								if not a then
									err(
										`{path}.at.{vp}.anchor`,
										"anchor must be center | top | bottom | left | right | topleft | ..."
									)
								else
									table.insert(parts, `Anchor={a[1]},{a[2]}`)
								end
							else
								err(
									`{path}.at.{vp}.{tostring(k)}`,
									"at overrides: size, pos, scale, textSize, visible, anchor"
								)
							end
						end
						for _, sp in scaledAt[vp] or {} do
							table.insert(parts, sp)
						end
						scaledAt[vp] = nil
						if #parts > 0 then
							table.sort(parts) -- (a stable string: the same spec compiles to the same model)
							attrs["Kit_At_" .. vp] = table.concat(parts, "|")
						end
					end
				end
			end
		end
		-- a HUD element covering the middle of the screen blocks the action
		if
			parentScreenSpan
			and not inLayout
			and not internal
			and bg
			and (n.transparency or 0) < 0.6
			and size
			and props.Position
		then
			local s, p = size.UDim2, props.Position.UDim2
			local w = s[1][1] + s[1][2] / 1280
			local h = s[2][1] + s[2][2] / 720
			local ax = anchor and anchor[1] or 0
			local ay = anchor and anchor[2] or 0
			local x0 = p[1][1] + p[1][2] / 1280 - ax * w
			local y0 = p[2][1] + p[2][2] / 720 - ay * h
			if w < 0.95 and h < 0.95 and x0 < 0.6 and x0 + w > 0.4 and y0 < 0.6 and y0 + h > 0.4 then
				table.insert(centerBlockers, path)
			end
		end
		-- composition: a top block = a child of the root (two dots in its path) with a size; measured at 1920x1080
		do
			local _, dots = string.gsub(path, "%.", "")
			if size and props.Position and authored then
				local s, p = size.UDim2, props.Position.UDim2
				local wpx = s[1][1] * 1920 + s[1][2]
				local hpx = s[2][1] * 1080 + s[2][2]
				local ax = anchor and anchor[1] or 0
				local ay = anchor and anchor[2] or 0
				local x0 = p[1][1] * 1920 + p[1][2] - ax * wpx
				local y0 = p[2][1] * 1080 + p[2][2] - ay * hpx
				if dots == 2 and wpx > 0 and hpx > 0 then
					table.insert(topBlocks, {
						path = path,
						x0 = x0,
						y0 = y0,
						x1 = x0 + wpx,
						y1 = y0 + hpx,
						rot = tonumber(n.rotation) or 0,
						full = wpx >= 1920 * 0.9 and hpx >= 1080 * 0.9,
					})
				end
				local painted = n.imageColor or n.color
				if
					s[1][1] == 0
					and s[2][1] == 0
					and type(painted) == "string"
					and theme.accent
					and (painted == "accent" or painted == theme.accent)
				then
					-- the box clipped to the screen, weighed by the piece's painted share (a torn wedge is not its box)
					local cx0, cy0 = math.max(0, x0), math.max(0, y0)
					local cx1, cy1 = math.min(1920, x0 + wpx), math.min(1080, y0 + hpx)
					local meta = if n.image and art then art[string.sub(n.image, 5)] else nil
					local share = if type(meta) == "table" and type(meta.opaque) == "number" then meta.opaque else 1
					if cx1 > cx0 and cy1 > cy0 then
						accentArea += (cx1 - cx0) * (cy1 - cy0) * share
					end
				end
				if n.image and s[1][1] == 0 and s[2][1] == 0 then
					-- a PICTURE = a file piece (a photo through ink, a logotype, a traced crest), weighed by its painted
					-- share; a tinted plate is a field or a strip, never the hero
					local meta = if art then art[string.sub(n.image, 5)] else nil
					if type(meta) == "table" and meta.file then
						local share = if type(meta.opaque) == "number" then meta.opaque else 1
						table.insert(imageAreas, { path = path, area = wpx * hpx * share })
					end
				end
			end
		end
		for vp, parts in scaledAt do
			table.sort(parts)
			attrs["Kit_At_" .. vp] = table.concat(parts, "|")
		end
		local savedAtScale = parentAtScale
		parentAtScale = myAtScale
		local savedSpan = parentScreenSpan
		do
			local sz = if size then size.UDim2 else nil
			parentScreenSpan = parentScreenSpan
				and (
					sz == nil
					or (sz[1][1] >= 0.95 and sz[2][1] >= 0.95 and math.abs(sz[1][2]) < 40 and math.abs(sz[2][2]) < 40)
				)
		end
		local seen: { [string]: boolean } = {}
		local savedStagger = parentStagger
		parentStagger = if type(n.motion) == "table" and type(n.motion.stagger) == "number" then n.motion.stagger else 0
		local savedList = parentList
		parentList = type(n.layout) == "table" and n.layout.grid == nil
		for i, child in n.children or {} do
			if type(child) == "table" and type(child.name) == "string" then
				if seen[child.name] then
					err(`{path}.{child.name}`, "duplicate sibling name — scripts could grab the wrong one")
				end
				seen[child.name] = true
			end
			local compiled = node(child, path, effectiveBg, hasLayout, internal)
			if compiled then
				compiled.Properties.LayoutOrder = i
				table.insert(children, compiled)
			end
		end
		parentStagger = savedStagger
		parentList = savedList
		parentAtScale = savedAtScale
		parentScreenSpan = savedSpan
		if n.fx ~= nil then
			fxBlock(n, path, class, props, attrs, children)
		end
		if n.states ~= nil then
			statesBlock(n, path, attrs)
		end
		do
			local rel = string.sub(path, #spec.name + 2)
			navNodes[rel] = class
			if (class == "TextButton" or class == "ImageButton") and not internal then
				table.insert(interactive, rel)
			end
		end
		if n.nav ~= nil then
			navBlock(n, path, attrs)
		end
		if n.glyph ~= nil then
			glyphBlock(n, path, attrs)
		end
		if n.burst ~= nil then
			burstBlock(n, path, attrs)
		end
		if n.sounds ~= nil then
			soundsBlock(n, path, attrs)
		end
		if n.flex ~= nil then
			-- "flex" (v7): this node grows / shrinks in its parent's LIST (UIFlexItem); anywhere else the engine ignores
			-- it, so it is an error, not a silent no-op
			local f = n.flex
			local fp: { [string]: any }? = nil
			if not parentList then
				err(
					path .. ".flex",
					'a flex item needs a parent with a list "layout" (not a grid, not none): UIFlexItem works only there'
				)
			elseif f == "grow" or f == "shrink" or f == "fill" then
				fp = { FlexMode = ({ grow = "Grow", shrink = "Shrink", fill = "Fill" })[f] }
			elseif type(f) == "table" then
				local g, s = f.grow or 0, f.shrink or 0
				if type(g) ~= "number" or type(s) ~= "number" or g < 0 or s < 0 or g ~= g or s ~= s then
					err(path .. ".flex", "flex grow / shrink are numbers >= 0")
				else
					local custom: { [string]: any } = { FlexMode = "Custom", GrowRatio = g, ShrinkRatio = s }
					fp = custom
					if f.align ~= nil then
						local la = ({
							start = "Start",
							center = "Center",
							["end"] = "End",
							stretch = "Stretch",
							auto = "Automatic",
						})[f.align]
						if not la then
							err(path .. ".flex.align", "flex align: start | center | end | stretch | auto")
						else
							custom.ItemLineAlignment = la
						end
					end
				end
			else
				err(path .. ".flex", 'flex: "grow" | "shrink" | "fill" | {"grow": 2, "shrink": 1, "align": "center"}')
			end
			if fp then
				table.insert(children, { Name = "Flex", ClassName = "UIFlexItem", Properties = fp })
			end
		end
		if n.bind ~= nil then
			-- "bind": "coins" (v7.15) — the node follows a value in the client store: Ui.set("coins", 1250) updates every
			-- bound label (text), counter (rolls), bar (0..1), digit-set number and glyph text
			if type(n.bind) ~= "string" or not string.match(n.bind, "^[%w_%.]+$") then
				err(path .. ".bind", 'bind: "<key>" (letters, digits, _ and . : "player.coins")')
			else
				attrs.Kit_Bind = n.bind
			end
		end
		if n.haptic ~= nil then
			-- "haptic": {"press": "light", "selected": "heavy"} — a motor pulse on the same moments as "sounds" (v7.12)
			if type(n.haptic) ~= "table" then
				err(path .. ".haptic", 'haptic: {"press": "light" | "heavy", "selected": ...}')
			else
				for k, v in n.haptic do
					if not SOUND_KEYS[k] or (v ~= "light" and v ~= "heavy") then
						err(
							`{path}.haptic.{tostring(k)}`,
							"haptic moments: hover | press | enter | show | a state; values light | heavy"
						)
					else
						attrs["Kit_Hap_" .. k] = v
					end
				end
			end
		end
		if n.tip ~= nil then
			-- "tip": the words a tooltip shows for this node — "text" or {"title": "...", "lines": ["+12 ATK", "-3 DEF"]}
			if type(n.tip) == "string" then
				attrs.Kit_Tip = n.tip
			elseif type(n.tip) == "table" and type(n.tip.title) == "string" then
				attrs.Kit_Tip = n.tip.title
				if type(n.tip.lines) == "table" then
					attrs.Kit_TipLines = table.concat(n.tip.lines, string.char(10))
				end
			else
				err(path .. ".tip", 'tip: "text" or {"title": "...", "lines": ["+12 ATK", "-3 DEF"]}')
			end
		end
		if (class == "TextButton" or class == "ImageButton") and not internal and not n.kit then
			if n.states ~= nil then
				statedButtons += 1
			else
				bareButtons += 1
			end
		end
		if next(attrs) then
			local typed = {}
			for k, v in attrs do
				typed[k] = if type(v) == "number"
					then { Float64 = v }
					elseif type(v) == "boolean" then { Bool = v }
					else { String = tostring(v) }
			end
			props.Attributes = { Attributes = typed }
		end
		-- an empty Luau table serializes as {} (object); Rojo needs Children to be an array, so omit it when empty
		return {
			Name = n.name,
			ClassName = class,
			Properties = props,
			Children = if #children > 0 then children else nil,
		}
	end

	local root = node(spec.root, spec.name, nil, false, false)
	-- VRAM: no CanvasGroup inside another, and none left allocated while hidden (UI.canvasProblems)
	if root then
		local nested, idle = UI.canvasProblems(root, `{spec.name}.{tostring(root.Name)}`)
		for _, c in nested do
			err(
				c.path,
				`a CanvasGroup inside the CanvasGroup {c.inside}: each one renders its whole tree into a texture of its own (the inner tree drawn twice, blurred, twice the video memory) - make it a panel, or move it out`
			)
		end
		for _, at in idle do
			warn(
				at,
				'a CanvasGroup hidden only by groupAlpha 1 keeps its texture in video memory - give it "visible": false and show it when it is used'
			)
		end
	end
	for name in missingArt do
		warn(spec.name, `art "{name}" is not uploaded yet (shows blank in game) — run: lune run kit upload`)
	end
	-- gamepad: every nav target is a control on this screen; a hero menu says where the pad lands
	for _, pn in pendingNav do
		local cls = navNodes[pn.to]
		if not cls then
			err(
				pn.at,
				`no node "{pn.to}" on this screen (paths start at the root: "{spec.root and spec.root.name or "Root"}.…")`
			)
		elseif cls ~= "TextButton" and cls ~= "ImageButton" then
			err(pn.at, `"{pn.to}" is a {cls}: the d-pad only lands on buttons`)
		end
	end
	if spec.firstFocus ~= nil then
		local cls = type(spec.firstFocus) == "string" and navNodes[spec.firstFocus] or nil
		if cls ~= "TextButton" and cls ~= "ImageButton" then
			err("spec.firstFocus", `firstFocus must name a button on this screen (got "{tostring(spec.firstFocus)}")`)
		end
	elseif (quality == "hero" or quality == "aaa") and #interactive >= 2 then
		warn(
			spec.name,
			`{#interactive} buttons and no "firstFocus" — a gamepad player opens the screen with nothing selected: name the main action`
		)
	end
	-- a hero screen designs every control's states, not just idle (the state sheet: build/ui/<Screen>.states.png)
	if (quality == "hero" or quality == "aaa") and bareButtons > 0 then
		warn(
			spec.name,
			`{bareButtons} button(s) with no "states" ({statedButtons} with) — a hero screen designs hover / pressed / selected / disabled for every control (they show in <Screen>.states.png)`
		)
	end
	if #textSizes >= 3 then
		table.sort(textSizes)
		if textSizes[#textSizes] < textSizes[1] * 1.3 then
			warn(
				spec.name,
				`no type hierarchy: every text is {textSizes[1]}–{textSizes[#textSizes]}px — give the most important thing a "role": "title" or "number"`
			)
		end
	end
	-- TYPE SCALE (v7.13): two sizes closer than ~12% read as one level that missed — on a hero screen every step of
	-- the scale should be a clear step (a ratio >= 1.2 is the usual minimum) or the same size
	if (quality == "hero" or quality == "aaa") and #textSizes >= 2 then
		local uniq: { number } = {}
		for _, v in textSizes do
			if uniq[#uniq] ~= v then
				table.insert(uniq, v)
			end
		end
		local close: { string } = {}
		for i = 2, #uniq do
			if uniq[i] / uniq[i - 1] < 1.12 then
				table.insert(close, `{uniq[i - 1]}/{uniq[i]}px`)
			end
		end
		if #close > 0 then
			warn(
				spec.name,
				`type sizes too close to read as two levels: {table.concat(close, ", ")} — make each step >= 1.2x or use one size`
			)
		end
	end
	-- "focus": the node the eye must land on first (the number, the title, the selected row). A hero screen names
	-- it; the compiler checks it is the biggest text on the screen (a judge's "hierarchy" score, measured early).
	if spec.focus ~= nil then
		if type(spec.focus) ~= "string" or spec.focus == "" then
			err("spec.focus", 'focus names the node the eye lands on first: "focus": "Hud.Coins.Value"')
		else
			local focusNode: { path: string, size: number, typed: boolean? }? = nil
			for _, t in textNodes do
				if t.path == spec.focus or string.sub(t.path, -(#spec.focus + 1)) == "." .. spec.focus then
					focusNode = t
				end
			end
			local focusImage = false
			for _, ip in imageNodes do
				if ip == spec.focus or string.sub(ip, -(#spec.focus + 1)) == "." .. spec.focus then
					focusImage = true
				end
			end
			for _, np in numberNodes do -- a digit-set number: the number IS the thing the eye lands on
				if np == spec.focus or string.sub(np, -(#spec.focus + 1)) == "." .. spec.focus then
					focusImage = true
				end
			end
			-- a rendered piece (kit ui render) as the focus: the eye lands on art, no text to out-size it
			if not focusImage and not focusNode then
				err(
					"spec.focus",
					`focus "{spec.focus}" is not a text or image node of this screen (paths: {spec.name}.<Root>.<Child>...)`
				)
			elseif focusNode and not focusImage then
				local biggest = focusNode
				for _, t in textNodes do
					if t.size > biggest.size then
						biggest = t
					end
				end
				if biggest ~= focusNode and biggest.size > focusNode.size then
					warn(
						spec.name,
						`the eye lands on {biggest.path} ({biggest.size}px), not on the focus {spec.focus} ({focusNode.size}px) — make the focus the biggest text or quieten the rest`
					)
				end
			end
		end
	elseif quality ~= "prop" then
		warn(
			"spec.focus",
			'a hero screen names what the eye lands on first: "focus": "<Root>.<Node>" (the compiler checks it is the biggest text)'
		)
	end
	-- a hero screen made only of font glyphs and tinted plates reads as generated, whatever its gates say (the
	-- owner's verdict on every such HUD was "AI slop"): the hero pieces are rendered or traced art
	if quality == "hero" and #imageNodes == 0 then
		warn(
			spec.name,
			"a hero screen with no art: every piece is a font glyph or a tinted plate — render the hero pieces (lune run kit ui render <identity>/<piece>: text, ring, gauge, gem items) or trace them from a real still (kit ui trace) and use them as art:<identity>/<piece>"
		)
	end
	-- the hero piece itself (spec.hero, else the focus) as a TYPED font glyph with a tint is an error on a hero
	-- screen: four PIL / typed rounds plateaued and the owner called each one AI slop; the medium is the fix —
	-- letter it ("lettering"), render it (kit ui render), or draw its digits ("type": "number" with a digit set)
	local heroPiece = if type(spec.hero) == "string" then spec.hero else spec.focus
	if (quality == "hero" or quality == "aaa") and type(heroPiece) == "string" and heroPiece ~= "" then
		-- (the EXACT node: a suffix match let an image B.Title excuse a typed A.Title — review 2026-10-16)
		local function named(p: string): boolean
			return p == heroPiece or p == `{spec.name}.{heroPiece}`
		end
		local isArt = false
		for _, ip in imageNodes do
			isArt = isArt or named(ip)
		end
		for _, np in numberNodes do
			isArt = isArt or named(np)
		end
		-- the one exception carries evidence: an identity whose REAL game sets its hero readout in plain type (a
		-- realistic HUD's ammo count) says so with one of its own listed references —
		-- identity.typed_hero_evidence = "<a references image path>: <what the still shows>"
		local typedOk = false
		if identity and type(identity.typed_hero_evidence) == "string" and type(identity.references) == "table" then
			for _, r in identity.references do
				-- ("<image>: <words>": an empty image matched every evidence string — review 2026-10-16)
				if
					type(r) == "table"
					and type(r.image) == "string"
					and r.image ~= ""
					and string.find(identity.typed_hero_evidence, r.image .. ":", 1, true) == 1
				then
					typedOk = true
				end
			end
		end
		if not isArt and not typedOk then
			for _, t in textNodes do
				if t.typed and named(t.path) then
					err(
						"spec." .. (if type(spec.hero) == "string" then "hero" else "focus"),
						`the hero piece {heroPiece} is a typed font glyph — on a hero screen it is made as art: "lettering" (kit ui letter), a rendered piece (kit ui render <identity>/<piece>) or a digit-set number ("type": "number"); type only the small numbers that change`
					)
					break
				end
			end
		end
	end
	-- only a HUD has an "action" to block (menus live in the middle on purpose): "kind": "hud" | "menu", or
	-- inferred — a screen with HUD components (crosshair, hitmarker, ammo, feed, ring) is a HUD
	local kind = spec.kind
	if kind == nil then
		local function hasHud(n: any): boolean
			if type(n) ~= "table" then
				return false
			end
			if
				n.type == "crosshair"
				or n.type == "hitmarker"
				or n.type == "ammo"
				or n.type == "feed"
				or n.type == "ring"
			then
				return true
			end
			for _, c in n.children or {} do
				if hasHud(c) then
					return true
				end
			end
			return false
		end
		kind = if hasHud(spec.root) then "hud" else "menu"
	end
	for _, p in if kind == "hud" then centerBlockers else {} do
		warn(p, "a solid element in the middle of the screen blocks the action — use a slot (bottom, bottomRight...)")
	end
	-- ARCADE-BAN (owner verdict FieldHud_v1 1/10 2026-10-12: "AI slop, I asked realistic"):
	-- an identity that lists "banned_components" (a list of component type strings, e.g. ["crosshair","ammo"])
	-- must not hold any of those components — a realistic HUD reports only what the player cannot feel; the
	-- arcade checklist (crosshair, minimap/compass, ammo counter, kill feed, scope) is the absence in a realist game.
	-- Two checks: (1) component TYPE — the original type before expand rewrites it; (2) node NAME — a panel named
	-- "Minimap" on an identity that bans "minimap" is the same violation even if the type is "panel".
	-- Name matching is a case-insensitive substring of each banned word inside one of the node name's words (it
	-- never reaches across a camel hump, an underscore or a digit change).
	-- The error always points at the offending node's own path, not its parent's.
	-- New screens: compile error. Existing (grandfathered) screens: warn only (the caller is responsible for
	-- building a grandfather list from the real screen scan; identities set "banned_components_grandfather"
	-- to ["ScreenName", ...] to suppress the error on those names).
	if identity and type(identity.banned_components) == "table" then
		local banned: { [string]: boolean } = {}
		for _, t in identity.banned_components do
			if type(t) == "string" then
				banned[t] = true
			end
		end
		local grandfather: { [string]: boolean } = {}
		for _, n in
			(type(identity.banned_components_grandfather) == "table" and identity.banned_components_grandfather) or {}
		do
			if type(n) == "string" then
				grandfather[n] = true
			end
		end
		local grandfathered = grandfather[spec.name or ""] == true
		-- (1) type-based check: the component type is itself a banned word
		for compType, firstPath in seenComponents do
			if banned[compType] then
				local msg =
					`banned_component "{compType}" at {firstPath}: the identity "{tostring(spec.identity)}" bans this component (realistic HUDs report only what the player cannot feel — the arcade checklist is the absence)`
				if grandfathered then
					warn(firstPath, msg)
				else
					err(firstPath, msg)
				end
			end
		end
		-- (2) name-based check: a node whose name contains a banned word (case-insensitive substring) inside ONE of the
		-- name's words - a word starts at a camel hump, after a run of capitals, after _ / - / a space, at a digit
		-- change - so "map" is in "Minimap" and "KillFeed" holds "feed", but "hp" is not in "FlashPrompt" or
		-- "HealthPips" (a 2-letter ban would otherwise hit every name with an h before a capital P)
		local function wordStarts(name: string): { [number]: boolean }
			local starts: { [number]: boolean } = { [1] = true }
			for i = 2, #name do
				local a, b, c = string.sub(name, i - 1, i - 1), string.sub(name, i, i), string.sub(name, i + 1, i + 1)
				local upper = string.match(b, "%u") ~= nil
				if
					(upper and string.match(a, "[%l%d]"))
					or (upper and string.match(a, "%u") and string.match(c, "%l"))
					or (string.match(b, "%w") and not string.match(a, "%w"))
					or (string.match(b, "%d") and string.match(a, "%a"))
					or (string.match(b, "%a") and string.match(a, "%d"))
				then
					starts[i] = true
				end
			end
			return starts
		end
		local function banHit(name: string, word: string): boolean
			local lname, lword = string.lower(name), string.lower(word)
			if lword == "" then
				return false
			end
			local starts = wordStarts(name)
			local init = 1
			while true do
				local s, e = string.find(lname, lword, init, true)
				if not s or not e then
					return false
				end
				local crosses = false
				for k = s + 1, e do
					if starts[k] then
						crosses = true
						break
					end
				end
				if not crosses then
					return true
				end
				init = s + 1
			end
		end
		for _, entry in seenNodeNames do
			for word in banned do
				if banHit(entry.name, word) then
					local msg =
						`banned_component "{word}" at {entry.path}: node name "{entry.name}" contains a banned word — the identity "{tostring(
							spec.identity
						)}" bans this component (realistic HUDs report only what the player cannot feel — the arcade checklist is the absence)`
					if grandfathered then
						warn(entry.path, msg)
					else
						err(entry.path, msg)
					end
					break
				end
			end
		end
	end
	-- the composition gates: measured against the identity's own "rules" (identity_from writes them from the stills)
	local rules = identity and identity.rules
	if type(rules) == "table" and quality ~= "prop" then
		local blocks = {}
		for _, b in topBlocks do
			if not b.full then
				table.insert(blocks, b)
			end
		end
		local leanMin = tonumber(rules.lean_min)
		if leanMin and #blocks > 0 then
			local leaning = 0
			for _, b in blocks do
				if math.abs(b.rot) >= leanMin then
					leaning += 1
				end
			end
			local want = tonumber(rules.lean_share) or 0.6
			if leaning / #blocks < want then
				warn(
					spec.name,
					`composition: {leaning} of {#blocks} top blocks lean {leanMin}° or more (the identity's rule: {math.floor(
						want * 100
					)}% do — "nothing level"); rotate the level ones`
				)
			end
		end
		if rules.overlap and #blocks > 1 then
			local alone = {}
			for i, b in blocks do
				local touches = false
				for j, o in blocks do
					if i ~= j and b.x0 < o.x1 and o.x0 < b.x1 and b.y0 < o.y1 and o.y0 < b.y1 then
						touches = true
					end
				end
				if not touches then
					table.insert(alone, b.path)
				end
			end
			if #alone > 0 then
				warn(
					spec.name,
					`composition: {#alone} top block(s) touch nothing ({table.concat(alone, ", ")}) — the identity's rule: every block overlaps a neighbour ("nothing alone")`
				)
			end
		end
		if type(rules.accent_share) == "table" and theme.accent then
			local share = math.min(1, accentArea / (1920 * 1080))
			local lo, hi = tonumber(rules.accent_share[1]) or 0, tonumber(rules.accent_share[2]) or 1
			if share < lo or share > hi then
				warn(
					spec.name,
					`composition: the accent paints about {math.floor(share * 100)}% of the screen (absolute-px nodes); the references measure {math.floor(
						lo * 100
					)}-{math.floor(hi * 100)}% — {if share > hi
						then "it is the background, not the accent: cut the field back"
						else "it is too shy: give the hero its field"}`
				)
			end
		end
		-- the hero piece: "hero" (a title's character) when the spec names one, else the focus
		local heroPath = if type(spec.hero) == "string" then spec.hero else spec.focus
		if rules.hero_biggest and type(heroPath) == "string" and #imageAreas > 1 then
			local heroArea, biggest = nil, imageAreas[1]
			local function isHero(p: string): boolean
				return p == heroPath or string.sub(p, -(#heroPath + 1)) == "." .. heroPath
			end
			for _, ia in imageAreas do
				if isHero(ia.path) then
					heroArea = ia.area
				end
				if ia.area > biggest.area then
					biggest = ia
				end
			end
			if heroArea and biggest.area > heroArea * 1.15 and not isHero(biggest.path) then
				warn(
					spec.name,
					`composition: the biggest picture (painted area) is {biggest.path}, not the hero {heroPath} — the identity's rule: the hero piece is the biggest (name "hero" in the spec if the focus is not the hero)`
				)
			elseif not heroArea and type(spec.hero) == "string" then
				warn(spec.name, `composition: "hero": "{spec.hero}" is not a picture of this screen`)
			end
		end
	end
	-- the AI tells: what a generated UI reaches for when nobody decided the look (each one measurable)
	local accent = type(theme.accent) == "string" and hex(theme.accent) or nil
	if accent then
		local h, s = hsv(accent)
		-- an identity that says WHERE it sampled its accent (one of its own listed references) chose it from data,
		-- not from habit: identity.accent_evidence = "<a references image path>: <what was measured>"
		local sampled = false
		if identity and type(identity.accent_evidence) == "string" and type(identity.references) == "table" then
			for _, r in identity.references do
				local img = if type(r) == "table" then r.image else r
				if type(img) == "string" and string.find(identity.accent_evidence, img, 1, true) then
					sampled = true
				end
			end
		end
		if h >= 235 and h <= 290 and s > 0.35 and not sampled then
			warn(
				spec.name,
				`accent {theme.accent} is the indigo / purple every generated UI reaches for — take the palette from the references (identity "tokens"), not from habit`
			)
		end
	end
	if #radiiUsed >= 4 then
		local same = true
		for _, r in radiiUsed do
			if r ~= radiiUsed[1] then
				same = false
			end
		end
		if same and radiiUsed[1] >= 6 then
			warn(
				spec.name,
				`every corner is {radiiUsed[1]}px: one radius on everything is the template look — vary it by role (cards vs chips vs buttons) or use the identity's plates`
			)
		end
	end
	if kind == "menu" and #enterDelays >= 3 then
		local same = true
		for _, d in enterDelays do
			if d ~= enterDelays[1] then
				same = false
			end
		end
		if same then
			warn(
				spec.name,
				`{#enterDelays} things enter at the same instant — a choreographed menu arrives in order: "motion": \{"stagger": 0.06\} on their container, or a "delay" each`
			)
		end
	end
	-- the skin's colours travel with the screen, so code can say Ui.text(label, "READY", "good")
	local tokens: { [string]: any } = {}
	for k, v in theme do
		if type(v) == "string" and hex(v) then
			tokens["Kit_" .. k] = { String = v }
		end
	end
	tokens.Kit_Font = { String = tostring(theme.font or "GothamMedium") }
	tokens.Kit_TitleFont = { String = tostring(theme.titleFont or theme.font or "GothamBold") }
	tokens.Kit_Kind = { String = kind }
	tokens.Kit_Quality = { String = quality }
	if type(spec.focus) == "string" then
		tokens.Kit_Focus = { String = spec.focus }
	end
	if type(spec.firstFocus) == "string" then
		tokens.Kit_FirstFocus = { String = spec.firstFocus }
	end
	-- "console": true (v7.11): the preview checks the TV's title-safe 90% and 24 px text for this screen
	if spec.console ~= nil then
		if type(spec.console) ~= "boolean" then
			err("spec.console", "console is true (a screen players read on a TV) or false")
		elseif spec.console then
			tokens.Kit_Console = { Bool = true }
		end
	end
	-- "backdrop" (v7.4): the WORLD behind a menu blurs, darkens and loses colour while the screen is open (a AAA pause /
	-- inventory staple): {"blur": 18, "darken": 0.35, "saturation": -0.4, "seconds": 0.25} — Ui.backdrop plays it
	if spec.backdrop ~= nil then
		local b = spec.backdrop
		if type(b) ~= "table" then
			err("spec.backdrop", 'backdrop: {"blur": 18, "darken": 0.35, "saturation": -0.4, "seconds": 0.25}')
		else
			local function n(k: string, lo: number, hi: number, dflt: number): number
				local v = b[k]
				if v == nil then
					return dflt
				end
				if type(v) ~= "number" or v < lo or v > hi then
					err(`spec.backdrop.{k}`, `{k} must be a number {lo}..{hi}`)
					return dflt
				end
				return v
			end
			for k in b do
				if k ~= "blur" and k ~= "darken" and k ~= "saturation" and k ~= "seconds" then
					err(`spec.backdrop.{tostring(k)}`, "backdrop keys: blur | darken | saturation | seconds")
				end
			end
			tokens.Kit_Backdrop = {
				String = `blur={n("blur", 0, 56, 18)},darken={n("darken", 0, 1, 0.35)},sat={n(
					"saturation",
					-1,
					1,
					-0.4
				)},sec={n("seconds", 0, 2, 0.25)}`,
			}
		end
	end
	-- burst presets: the identity's, then the screen's (a screen's own wins)
	do
		local presets: { [string]: any } = {}
		for _, src in { identity and identity.bursts, spec.bursts } do
			if src ~= nil and type(src) ~= "table" then
				err("bursts", 'bursts: {"<name>": {preset}, ...}')
			elseif src then
				for name, b in src do
					presets[name] = b
				end
			end
		end
		for name, b in presets do
			if type(name) ~= "string" or not string.match(name, "^[%w_]+$") then
				err("bursts", `a burst name is letters, digits and _ (not "{tostring(name)}")`)
				continue
			end
			local enc = burstPreset(`bursts.{name}`, b)
			if enc then
				tokens["Kit_Burst_" .. name] = { String = enc }
				burstNames[name] = true
			end
		end
		for _, pb in pendingBursts do
			if not burstNames[pb.preset] then
				err(pb.at, `no burst preset "{pb.preset}" — the identity's or the screen's "bursts"`)
			end
		end
	end
	-- the focus piece the gamepad's selection wears (else the engine's blue box)
	do
		local fp = spec.focusPiece or (identity and identity.focusPiece) or nil
		-- (default: the identity's drawn OUTLINE — a selection must read as a ring, a band hides under the button)
		for _, plate in { "frame_line", "highlight" } do
			if fp == nil and spec.identity and art and art[`{spec.identity}/{plate}`] then
				fp = `art:{spec.identity}/{plate}`
			end
		end
		if fp ~= nil then
			local id, nm = image("spec.focusPiece", fp)
			tokens.Kit_FocusArt = { String = id }
			if nm then
				tokens.Kit_FocusArtName = { String = nm }
				local meta = art and art[nm]
				local sl = meta and meta.slice
				if type(sl) == "table" and #sl == 4 then
					tokens.Kit_FocusSlice = { String = `{sl[1]},{sl[2]},{sl[3]},{sl[4]}` }
				end
			end
		elseif #interactive >= 1 and (quality == "hero" or quality == "aaa") then
			warn(
				spec.name,
				'no focus piece — a gamepad selection shows the engine blue box: give the identity a "focusPiece" (or a frame_line plate)'
			)
		end
	end
	if spec.identity then
		tokens.Kit_Identity = { String = tostring(spec.identity) }
		if identity and type(identity.world) == "string" then
			tokens.Kit_World = { String = identity.world } -- (the preview draws the world the identity describes)
		end
	end
	-- where the screen may draw: "core" keeps clear of the Roblox buttons + notch, "device" (default) only the notch,
	-- "none" draws under everything (a backdrop), "topbar" fits beside the buttons
	local insets = ({
		core = "CoreUISafeInsets",
		device = "DeviceSafeInsets",
		none = "None",
		topbar = "TopbarSafeInsets",
	})[spec.insets or "device"]
	if not insets then
		err("spec.insets", "insets must be core | device | none | topbar")
		insets = "DeviceSafeInsets"
	end
	tokens.Kit_Insets = { String = insets }
	-- "scale": {"phone": 0.72, "tablet": 0.88}: the Ui runtime sizes the root 1/s and puts a UIScale s on it, so
	-- every pixel offset shrinks on small screens (the preview draws the phone/tablet sheets the same way)
	if spec.scale ~= nil then
		if type(spec.scale) ~= "table" then
			err("spec.scale", 'scale must be {"phone": 0.72, "tablet": 0.88} (1 = unscaled)')
		else
			for k, v in spec.scale do
				if (k ~= "phone" and k ~= "tablet" and k ~= "desktop") or type(v) ~= "number" or v <= 0.3 or v > 2 then
					err("spec.scale." .. tostring(k), "scale keys: phone | tablet | desktop, values 0.3 .. 2")
				else
					tokens["Kit_Scale_" .. k] = { Float64 = v }
				end
			end
		end
	end
	-- ATLASES (v6.8): a picture whose piece sits in its identity's atlas sheet (kit/ui/atlas.py, packed by the plates
	-- step) shows the uploaded SHEET through ImageRectOffset / ImageRectSize — fewer textures to stream and batch.
	-- Never for a picture the runtime swaps (a flipbook, a digit cell, a state's picture), a 9-slice or a tile: those
	-- keep their own upload. The preview still draws the piece itself (KitArt), so nothing looks different.
	local atlased = 0
	local function attrOf(inst: any, key: string): any
		local a = inst.Properties and inst.Properties.Attributes and inst.Properties.Attributes.Attributes
		local v = a and a[key]
		return v and (v.String or v.Float64 or v.Bool)
	end
	local function atlasWalk(inst: any, parent: any?, parentSwapped: boolean)
		local p = inst.Properties
		local swapped = false
		if p and (inst.ClassName == "ImageLabel" or inst.ClassName == "ImageButton") then
			local nm = attrOf(inst, "KitArt")
			local meta = type(nm) == "string" and art and art[nm] or nil
			local at = meta and meta.atlas
			-- (a split's copy of a swapped picture is synced to it at run time; a pad-glyph keycap gets the pad
			-- button's picture: both keep their own upload too)
			swapped = (inst.Name == "Fx_SplitC" and parentSwapped)
				or (parent ~= nil and attrOf(parent, "Kit_GlyphPad") ~= nil)
				or attrOf(inst, "Kit_Flip") ~= nil
				or (parent ~= nil and attrOf(parent, "Kit_DigitIds") ~= nil)
				or (function()
					-- (a state's picture swap lands on the node itself, or on the Plate of a plate-backed control)
					for _, holder in { inst, if inst.Name == "Plate" then parent else nil } do
						for _, s0 in STATE_NAMES do
							local st = holder and attrOf(holder, "Kit_S_" .. s0)
							if type(st) == "string" and string.find(st, "image=", 1, true) then
								return true
							end
						end
					end
					return false
				end)()
			local scale = p.ScaleType
			if
				type(at) == "table"
				and #at == 5
				and not swapped
				and scale ~= "Slice"
				and scale ~= "Tile"
				and not p.ImageRectSize
			then
				local ident = string.match(nm, "^([%w_]+)/")
				local sheetName = if ident then `{ident}/{at[1]}` else at[1]
				local sid = ids and ids.ui and ids.ui[sheetName]
				if type(sid) == "string" then
					p.Image = sid
					p.ImageRectOffset = { Vector2 = { at[2], at[3] } }
					p.ImageRectSize = { Vector2 = { at[4], at[5] } }
					p.Attributes.Attributes.Kit_Atlas = { String = sheetName }
					atlased += 1
				end
			end
		end
		for _, c in inst.Children or {} do
			atlasWalk(c, inst, swapped)
		end
	end
	if root then
		atlasWalk(root, nil, false)
	end
	if atlased > 0 then
		tokens.Kit_Atlased = { Float64 = atlased }
	end
	-- BUDGETS (v7.15): what a screen costs a phone — every instance is laid out and drawn, every distinct picture is a
	-- texture to stream; a hero screen warns past the line (atlased pictures share one texture per sheet)
	do
		local count, images = 0, {}
		local function walkBudget(inst: any)
			count += 1
			local p = inst.Properties
			if p and type(p.Image) == "string" and p.Image ~= "" then
				images[p.Image] = true
			end
			for _, c in inst.Children or {} do
				walkBudget(c)
			end
		end
		if root then
			walkBudget(root)
		end
		local nImages = 0
		for _ in images do
			nImages += 1
		end
		tokens.Kit_Budget = { String = `instances={count},images={nImages}` }
		if (quality == "hero" or quality == "aaa") and (count > 1500 or nImages > 80) then
			warn(
				spec.name,
				`budget: {count} instances and {nImages} distinct pictures (a phone's line: 1500 / 80) — fold repeats into a "list", pictures into the atlas`
			)
		end
	end
	-- WORLD-SPACE UI: "space": "world" + "world": {"kind": "billboard" | "surface", ...} makes the root a BillboardGui
	-- (a nameplate, a damage number, an objective marker over a part: "offset": [0, 3, 0] studs, "maxDistance",
	-- "onTop", "distance": {"near": 20, "far": 120, "min": 0.55} — it shrinks and fades between near and far) or a
	-- SurfaceGui (a screen ON a part: "face": "Front", "light": 1). The root's pixel size is the canvas. In game it is
	-- a template: Ui.attach(template, part) mounts a copy, Ui.floater(template, position, text) flies a damage number.
	if spec.space ~= nil and spec.space ~= "screen" and spec.space ~= "world" then
		err("spec.space", 'space is "screen" (default) or "world"')
	end
	if spec.space == "world" then
		local w = if type(spec.world) == "table" then spec.world else {}
		if spec.world ~= nil and type(spec.world) ~= "table" then
			err("spec.world", 'world: {"kind": "billboard" | "surface", ...}')
		end
		local wk = w.kind or "billboard"
		local rs = spec.root and spec.root.size
		local cw = type(rs) == "table" and tonumber(rs[1]) or nil
		local ch = type(rs) == "table" and tonumber(rs[2]) or nil
		if not cw or not ch then
			err("spec.root.size", "a world screen's root needs a pixel size ([w, h]): it is the canvas")
			cw, ch = 200, 60
		end
		tokens.Kit_Space = { String = wk }
		local props: any = {
			Attributes = { Attributes = tokens },
			Enabled = spec.enabled ~= false,
			ResetOnSpawn = false,
			ZIndexBehavior = "Sibling",
			AlwaysOnTop = w.onTop == true,
		}
		local cls = "BillboardGui"
		if wk == "billboard" then
			local off = w.offset or { 0, 3, 0 }
			if type(off) ~= "table" or #off ~= 3 then
				err("spec.world.offset", "offset is [x, y, z] studs above the part")
				off = { 0, 3, 0 }
			end
			props.Size = { UDim2 = { { 0, cw }, { 0, ch } } }
			props.StudsOffset = { Vector3 = off }
			props.MaxDistance = tonumber(w.maxDistance) or 150
			props.LightInfluence = 0
			props.ClipsDescendants = false
			if w.distance ~= nil then
				local d = w.distance
				local near, far, low = tonumber(d.near), tonumber(d.far), tonumber(d.min)
				if type(d) ~= "table" or not near or not far or not low or near >= far or low <= 0 or low > 1 then
					err(
						"spec.world.distance",
						'distance: {"near": 20, "far": 120, "min": 0.55} (studs; the scale at far)'
					)
				else
					tokens.Kit_DistNear = { Float64 = near }
					tokens.Kit_DistFar = { Float64 = far }
					tokens.Kit_DistMin = { Float64 = low }
				end
			end
		elseif wk == "surface" then
			cls = "SurfaceGui"
			local faces = { Front = true, Back = true, Left = true, Right = true, Top = true, Bottom = true }
			local face = w.face or "Front"
			if not faces[face] then
				err("spec.world.face", "face is Front | Back | Left | Right | Top | Bottom")
				face = "Front"
			end
			props.Face = face
			props.SizingMode = "FixedSize"
			props.CanvasSize = { Vector2 = { cw, ch } }
			props.LightInfluence = tonumber(w.light) or 1
		else
			err("spec.world.kind", 'kind is "billboard" or "surface"')
		end
		return { ClassName = cls, Properties = props, Children = if root then { root } else {} }, issues
	end
	local model = {
		ClassName = "ScreenGui",
		Properties = {
			Attributes = { Attributes = tokens },
			Enabled = spec.enabled ~= false, -- "enabled": false ships the screen hidden until a script shows it
			ResetOnSpawn = false,
			ScreenInsets = insets, -- (the one property; IgnoreGuiInset is its legacy alias and would race it)
			ZIndexBehavior = "Sibling",
		},
		Children = if root then { root } else {},
	}
	return model, issues
end

return UI

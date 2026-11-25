-- ui_hudsize.spec.luau — the game-code HUD size check (kit/lib/hudsize.luau). Fault: the owner's sg_hud5 3/10
-- (2026-10-29, "what the hell, I told you not this small"): Sample Game's HUD is game code that sized itself at
-- runtime (R2: every block at 0.58 of its 1080p design) where no spec or compile saw it. The REAL R2 file is the
-- selftest's bad example (kit/selftest/ui/hud_size); these pin what reading a HUD's own code must get right.
-- Run with: lune run kit/test/run kit
local frk = require("../frk")
local test, check = frk.test, frk.check

local HudSize = require("../../lib/hudsize")

-- a small HUD shaped like ChamberHud: a block helper keeping its blocks in self.corners, a resize from the screen
local TEMPLATE = [[
local Hud = {}
-- corner("Ghost", Vector2.new(5, 5), 1) is only a comment, never a block
local SIZE_W, SIZE_H = 600, 300
local function new(class, props, parent)
	return Instance.new(class)
end
function Hud:create()
	local gui = new("ScreenGui", { Name = "Hud" }, nil)
	%PRE%
	self.corners = {}
	local function corner(name, size, k)
		local f = new("Frame", { Name = name, Size = UDim2.fromOffset(size.X, size.Y) }, gui)
		table.insert(self.corners, { frame = f, scale = new("UIScale", { Scale = 1 }, f), k = k or 1 })
		return f
	end
	corner("Left", Vector2.new(SIZE_W, SIZE_H), 0.8)
	local W = 400
	corner("Right", Vector2.new(W, 200))
	local W = self.width -- (not a value: the call above keeps 400)
	local s = "corner(\"Quoted\", Vector2.new(1, 1))"
	local SCALE = %SCALE%
	local function rescale()
		local sz = %SIZE%
		local s = SCALE * sz.Y / 1080
		for _, c in self.corners do
			c.scale.Scale = s * c.k
		end
	end
	rescale()
	gui:GetPropertyChangedSignal("AbsoluteSize"):Connect(rescale)
end
return Hud
]]

local function hud(scale: string, size: string?, pre: string?): string
	local src = string.gsub(TEMPLATE, "%%SCALE%%", scale)
	src = string.gsub(src, "%%SIZE%%", size or "gui.AbsoluteSize")
	src = string.gsub(src, "%%PRE%%", pre or "")
	return src
end

local function contract(blocks: { [string]: any }?, floor: number?): { [string]: any }
	return {
		hud = "TestHud",
		block = "corner",
		resize = "rescale",
		floor = floor or 0.8,
		frames = { { 1920, 1080 }, { 1280, 720 } },
		reference = {
			frame = { 1920, 1080 },
			follows = "height",
			source = "spec",
			blocks = blocks or { Left = { size = { 480, 240 } }, Right = { size = { 400, 200 } } },
		},
	}
end

local function has(s: string, needle: string): boolean
	return string.find(s, needle, 1, true) ~= nil
end

-- `old` replaced by `new`, once, as plain text (the variants below; fails loudly when the template changed)
local function replace(s: string, old: string, new: string): string
	local a, b = string.find(s, old, 1, true)
	assert(a and b, "template text not found: " .. old)
	return string.sub(s, 1, a - 1) .. new .. string.sub(s, b + 1)
end

return function()
	test.suite("game-code HUD size (sg_hud5 3/10 owner verdict)", function()
		test.case("a HUD at its reference size passes at every frame", function()
			local r = HudSize.check(contract(), hud("1.0"), "spec")
			check.is_true(r.ok, "expected a pass: " .. r.summary)
			check.is_true(#r.blocks == 4, "2 blocks x 2 frames measured")
		end)

		test.case("the same HUD at 0.58 fails, naming each block and its ratio", function()
			local r = HudSize.check(contract(), hud("0.58"), "spec")
			check.is_true(not r.ok, "a HUD at 0.58 of its reference must fail")
			check.is_true(has(r.summary, "hud size"), r.summary)
			check.is_true(has(r.summary, "Left 278x139 px at 1920x1080 = 0.58"), r.summary)
			check.is_true(has(r.summary, "Right"), r.summary)
		end)

		test.case("a size just under the floor fails and never reads as the floor", function()
			local r = HudSize.check(contract(), hud("0.7985"), "spec")
			check.is_true(not r.ok, "0.7985 is under a floor of 0.8")
			check.is_true(has(r.summary, "= 0.79 of"), "shown cut down, not rounded up: " .. r.summary)
		end)

		test.case("a call in a comment or a string is not a block", function()
			local measured = HudSize.measure(hud("1.0"), "corner", "rescale", { { 1920, 1080 } })
			check.is_true(measured ~= nil, "measured")
			local blocks = (measured :: any)["1920x1080"]
			check.is_true(blocks.Ghost == nil, "the commented call made no block")
			check.is_true(blocks.Quoted == nil, "the quoted call made no block")
			check.is_true(blocks.Left ~= nil and blocks.Right ~= nil, "the two real blocks are measured")
		end)

		test.case("the nearest value before a call is used; a later non-value is skipped", function()
			local measured = HudSize.measure(hud("1.0"), "corner", "rescale", { { 1920, 1080 } })
			local right = (measured :: any)["1920x1080"].Right
			check.is_true(right.design[1] == 400 and right.design[2] == 200, "Right is 400x200 by its own W")
		end)

		test.case("a block the reference names but the code never makes fails as not measured", function()
			local r = HudSize.check(
				contract({ Left = { size = { 480, 240 } }, Gone = { size = { 100, 100 } } }),
				hud("1.0"),
				"spec"
			)
			check.is_true(not r.ok, "a missing block must fail")
			check.is_true(has(r.summary, "not measured: Gone"), r.summary)
		end)

		test.case("a resize that crashes before it scales fails, never passes on the made-with scale", function()
			-- SCALE is no value (nil + 1 does not evaluate): the resize throws before any UIScale is set
			local r = HudSize.check(contract(), hud("nil + 1"), "spec")
			check.is_true(not r.ok, "an unmeasured HUD must fail")
			check.is_true(has(r.summary, "not measured"), r.summary)
		end)

		test.case("a HUD sized from the camera (local cam = workspace.CurrentCamera) is measured", function()
			local src = hud("0.58", "cam.ViewportSize", "local cam = workspace.CurrentCamera")
			local r = HudSize.check(contract(), src, "spec")
			check.is_true(not r.ok and has(r.summary, "= 0.58 of"), r.summary)
			local ok =
				HudSize.check(contract(), hud("1.0", "cam.ViewportSize", "local cam = workspace.CurrentCamera"), "spec")
			check.is_true(ok.ok, ok.summary)
		end)

		test.case("a malformed contract is refused, not passed", function()
			local r = HudSize.check(contract(nil, 1.5), hud("1.0"), "spec")
			check.is_true(not r.ok and has(r.summary, "contract is not usable"), r.summary)
			local r2 = HudSize.check(contract({}), hud("1.0"), "spec")
			check.is_true(not r2.ok and has(r2.summary, "reference.blocks"), r2.summary)
		end)

		-- the fresh review of card qfab: four ways a too-small HUD read as a pass
		test.case("a resize that returns early leaves nothing measured (never the made-with scale)", function()
			local src = replace(
				hud("0.58"),
				"local function rescale()\n",
				"local function rescale()\n\t\tif not self.ready then return end\n"
			)
			local r = HudSize.check(contract(), src, "spec")
			check.is_true(not r.ok and has(r.summary, "not measured"), r.summary)
			-- a guard on the HUD's own screen still runs (the stub HUD has its gui)
			local guarded = replace(
				hud("0.58"),
				"local function rescale()\n",
				"local function rescale()\n\t\tif not self.gui then return end\n"
			)
			local g = HudSize.check(contract(), guarded, "spec")
			check.is_true(not g.ok and has(g.summary, "= 0.58 of"), g.summary)
		end)

		test.case("a resize that crashes after scaling the blocks leaves nothing measured", function()
			-- (a whole-screen UIScale the check cannot see, shrunk after the blocks: the crash hides it)
			local src = replace(
				hud("1.0"),
				"\t\tend\n\tend\n\trescale()",
				"\t\tend\n\t\tself.rootScale.Scale = 0.58\n\tend\n\trescale()"
			)
			local r = HudSize.check(contract(), src, "spec")
			check.is_true(not r.ok and has(r.summary, "not measured"), r.summary)
			check.is_true(has(r.summary, "the resize stopped"), "the crash is named: " .. r.summary)
		end)

		test.case("a scale the code reassigns is no constant: never read as its declared value", function()
			local src = replace(
				hud("1.0"),
				"\tlocal function rescale()",
				"\tif self.compact ~= false then\n\t\tSCALE = 0.58\n\tend\n\tlocal function rescale()"
			)
			local r = HudSize.check(contract(), src, "spec")
			check.is_true(not r.ok, "a reassigned SCALE must not pass as 1.0: " .. r.summary)
			local compound =
				replace(hud("1.0"), "\tlocal function rescale()", "\tSCALE *= 0.58\n\tlocal function rescale()")
			local c = HudSize.check(contract(), compound, "spec")
			check.is_true(not c.ok, "SCALE *= 0.58 must not pass as 1.0: " .. c.summary)
		end)

		test.case("a value declared inside another function is not the one the resize reads", function()
			-- the module says 0.58; an unrelated method before create() declares its own SCALE = 1.0
			local src = replace(hud("0.58"), "\tlocal SCALE = 0.58\n", "")
			src = replace(
				src,
				"local Hud = {}\n",
				"local Hud = {}\nlocal SCALE = 0.58\nfunction Hud:other()\n\tlocal SCALE = 1.0\n\treturn SCALE\nend\n"
			)
			local r = HudSize.check(contract(), src, "spec")
			check.is_true(not r.ok and has(r.summary, "= 0.58 of"), r.summary)
		end)

		test.case("two resize functions of one name fail as ambiguous", function()
			local src = replace(
				hud("1.0"),
				"return Hud\n",
				"function Hud:other()\n\tlocal function rescale() end\nend\nreturn Hud\n"
			)
			local r = HudSize.check(contract(), src, "spec")
			check.is_true(not r.ok and has(r.summary, "2 times"), r.summary)
		end)

		test.case("a helper or resize the code does not have is named in the failure", function()
			local c = contract()
			c.resize = "relayout"
			local r = HudSize.check(c, hud("1.0"), "spec")
			check.is_true(not r.ok and has(r.summary, 'no "local function relayout("'), r.summary)
		end)
	end)
end

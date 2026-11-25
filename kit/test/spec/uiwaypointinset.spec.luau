-- uiwaypointinset.spec.luau — a waypoint marker lands on its target on EVERY screen, inset kept or ignored
-- (UiCombat.placeIn, used by src/kit/Ui's Ui.track / Ui.waypoint). The numbers are Studio's own, measured 2026-11-20
-- (tests/playtest/ui_combat_kit): GuiService:GetGuiInset() = (0, 58); a ScreenGui that ignores the inset (or has
-- ScreenInsets None) has AbsolutePosition (0, -58), one with CoreUISafeInsets (0, 0). Taken as AbsolutePosition alone,
-- the marker on the safe screen sat 57 px under its target.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local C = require("../../../src/kit/UiCombat")

return function()
	test.suite("UiCombat.placeIn: the marker's offset in its parent (V4 UI-X 13.6)", function()
		test.case("a viewport point lands on itself whatever the screen's inset", function()
			-- a screen that ignores the inset: its corner is the viewport's
			local x, y = C.placeIn(700, 330, 0, -58, 0, 58)
			check.equal(x, 700)
			check.equal(y, 330)
			-- a screen that keeps the inset: its corner is 58 px down, so the offset is 58 less
			x, y = C.placeIn(700, 330, 0, 0, 0, 58)
			check.equal(x, 700)
			check.equal(y, 272)
			-- a frame inside it at (40, 100) of the safe area
			x, y = C.placeIn(700, 330, 40, 100, 0, 58)
			check.equal(x, 660)
			check.equal(y, 172)
		end)
		test.case("Ui.track places by it, from the parent's AbsolutePosition (a ScreenGui's too)", function()
			local src = fs.readFile("src/kit/Ui.luau")
			check.is_true(
				string.find(src, "UiCombat.placeIn(pos.X, pos.Y, origin.X, origin.Y, inset.X, inset.Y)", 1, true) ~= nil
			)
			check.is_true(string.find(src, 'if parent:IsA("GuiBase2d") then parent.AbsolutePosition', 1, true) ~= nil)
		end)
	end)
end

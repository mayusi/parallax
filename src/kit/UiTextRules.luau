--!strict
-- UiTextRules.luau — the PURE half of text that honours the player's own text size (GuiService.PreferredTextSize,
-- the accessibility setting: Medium | Large | Larger | Largest). Shared by the compiler (kit/lib/ui.luau: a text that
-- opts in must still fit its box at Largest) and the runtime (kit Ui: it scales the text when the setting changes),
-- so the two never disagree. Tested headless in kit/test/spec/uitext.spec.luau.
--
-- The steps: Roblox publishes the setting, not a multiplier; these are Android's font-scale steps (1.0, 1.15, 1.3,
-- and 1.5 for its largest accessibility size) - a text at Largest is half again as tall.
local UiTextRules = {}

UiTextRules.FACTOR = { Medium = 1, Large = 1.15, Larger = 1.3, Largest = 1.5 }
UiTextRules.LARGEST = "Largest"
UiTextRules.LINE = 1.2 -- a line's height over its text size (the engine's default line height, plus its descent)
UiTextRules.MAX = 100 -- the engine caps TextSize at 100

-- the setting's name ("Large", or an EnumItem whose Name is one) -> its factor; unknown / nil -> 1
function UiTextRules.factor(setting: unknown): number
	local name = if type(setting) == "string"
		then setting
		elseif typeof(setting) == "EnumItem" then (setting :: any).Name
		else nil
	return if name and UiTextRules.FACTOR[name] then UiTextRules.FACTOR[name] else 1
end

-- the text size to draw: the designed size times the setting's factor, whole pixels, at most the engine's cap
function UiTextRules.scaled(base: number, setting: unknown): number
	if type(base) ~= "number" or base ~= base or base <= 0 then
		return base
	end
	return math.min(UiTextRules.MAX, math.floor(base * UiTextRules.factor(setting) + 0.5))
end

-- does a text of `textSize` still fit a box `boxHeight` px tall at the LARGEST setting, `lines` lines of it?
-- -> ok, the height it needs there. A box with no fixed pixel height (scaled, automatic) is not judged: ok.
function UiTextRules.fits(textSize: number, boxHeight: number?, lines: number?): (boolean, number)
	local need = UiTextRules.scaled(textSize, UiTextRules.LARGEST) * UiTextRules.LINE * math.max(1, lines or 1)
	if type(boxHeight) ~= "number" or boxHeight <= 0 then
		return true, need
	end
	return need <= boxHeight + 0.5, need
end

return UiTextRules

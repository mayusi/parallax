--!strict
-- UiStyleRules.luau — how the kit's exported StyleSheet must be laid out for the engine to apply it (pure; specced in
-- Lune by kit/test/spec/uistyle.spec.luau). Measured in Studio 2026-11-20 (tests/playtest/ui_style_query, card 7bgq):
--   * a StyleQuery is evaluated only when it sits UNDER the styled GuiObject (inside a StyleSheet, under a rule or
--     under the StyleLink it never turns active) -> Ui.link places a copy of each query under the linked root;
--   * a "@Name" rule selects that styled GuiObject itself, so the rules nested under it reach its labels only through a
--     child / descendant combinator ("> X" / ">> X"); a bare ".KitTitle" under "@Name" matches nothing.
local UiStyleRules = {}

-- the selector a rule nested under `parent` must carry: under a "@Query" rule a selector with no leading combinator
-- becomes ">> <selector>" (every descendant of the styled root); anything else is left as written
function UiStyleRules.scoped(parent: string?, selector: string): string
	if type(parent) ~= "string" or string.sub(parent, 1, 1) ~= "@" then
		return selector
	end
	local s = string.match(selector, "^%s*(.-)%s*$") or selector
	if s == "" or string.sub(s, 1, 1) == ">" then
		return selector
	end
	return ">> " .. s
end

-- which of a sheet's children Ui.link copies UNDER the root it styles: every StyleQuery (by name; the "@Name" rule
-- selects the query of that name), except one the root already holds. children = { {className, name} }
function UiStyleRules.queriesToPlace(
	children: { { className: string, name: string } },
	rootHas: { [string]: boolean }
): { string }
	local out: { string } = {}
	for _, c in children do
		if c.className == "StyleQuery" and not rootHas[c.name] then
			table.insert(out, c.name)
		end
	end
	return out
end

return UiStyleRules

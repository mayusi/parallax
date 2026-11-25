-- uistyle.spec.luau — UiStyleRules (src/kit): the layout the engine needs for the kit's StyleQuery breakpoints (card
-- 7bgq, measured in Studio 2026-11-20): the rules under a "@Query" rule reach the styled root's labels only through a
-- descendant combinator.
local frk = require("../frk")
local test, check = frk.test, frk.check

local R = require("../../../src/kit/UiStyleRules")

return function()
	test.suite("UiStyleRules: a query's rules reach the labels", function()
		test.case("under a @Query rule a bare selector becomes a descendant selector", function()
			check.equal(R.scoped("@Wide", ".KitTitle"), ">> .KitTitle")
			check.equal(R.scoped("@Phone", "  TextLabel "), ">> TextLabel")
			check.equal(R.scoped("@Phone", "#Hp"), ">> #Hp")
		end)
		test.case("a selector that already names its combinator, or a rule not under a query, is left alone", function()
			check.equal(R.scoped("@Wide", "> .KitTitle"), "> .KitTitle")
			check.equal(R.scoped("@Wide", ">> .KitTitle"), ">> .KitTitle")
			check.equal(R.scoped(".KitPanel", ".KitTitle"), ".KitTitle")
			check.equal(R.scoped(nil, ".KitTitle"), ".KitTitle")
			check.equal(R.scoped("@Wide", ""), "")
		end)
		test.case(
			"every query in the sheet is placed under the styled root (the engine ignores it in the sheet)",
			function()
				-- kit ui style's export: the queries sit IN the sheet beside their "@Name" rules
				local kids = {
					{ className = "StyleRule", name = "Panel" },
					{ className = "StyleQuery", name = "Phone" },
					{ className = "StyleRule", name = "AtPhone" },
					{ className = "StyleQuery", name = "Pad" },
				}
				local placed = R.queriesToPlace(kids, {})
				check.equal(#placed, 2)
				check.equal(placed[1], "Phone")
				check.equal(placed[2], "Pad")
				-- linked twice (or a hand-made query already there): never a second copy
				local again = R.queriesToPlace(kids, { Phone = true, KitStyle = true })
				check.equal(#again, 1)
				check.equal(again[1], "Pad")
				check.equal(#R.queriesToPlace({ { className = "StyleRule", name = "X" } }, {}), 0)
			end
		)
	end)
end

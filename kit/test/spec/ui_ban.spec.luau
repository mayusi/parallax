-- ui_ban.spec.luau — owner-verdict bad-example gates: arcade components in a realistic screen.
-- Fault: FieldHud_v1 1/10 2026-10-12 "AI slop, I asked realistic" — the full arcade checklist
-- (crosshair, ammo counter, kill feed, minimap/compass) on a screen for a realistic game.
-- Check: identity.banned_components lists types that must not appear on the screen.
-- Run with: lune run kit/test/run kit
local frk = require("../frk")
local test, check = frk.test, frk.check

local UI = require("../../lib/ui")

-- a minimal tactical identity that bans crosshair and ammo
local TACTICAL_ID = {
	name = "tactical",
	fonts = { font = "RobotoCondensed" },
	shape = {
		line = "#000000",
		fill = "#0a0c0e",
		fill_alpha = 0.5,
		width = 1,
		corner = "square",
		glow = "#f0f0ec",
		grain = 0.0,
		gloss = 0.0,
		shade = 0.0,
		shadow = 0,
		buttons = { "accent" },
	},
	bans = { "crosshair: realistic shooters show only a small dot or nothing" },
	banned_components = { "crosshair", "ammo", "compass", "scope", "feed" },
	minimums = { text = 14, button = 44, icon = 20 },
	references = {
		{ game = "selftest", screen = "selftest only", image = "kit/selftest/ui/arcade_in_realistic/refs/dummy.png" },
	},
}

local function hasIssue(issues: { any }, severity: string, needle: string): boolean
	for _, issue in issues do
		if issue.severity == severity and string.find(issue.message, needle, 1, true) then
			return true
		end
	end
	return false
end

return function()
	test.suite("arcade-ban gate (FieldHud_v1 1/10 owner verdict)", function()
		test.case("crosshair on a tactical identity is a compile error", function()
			local _, issues = UI.compile({
				name = "BadHud",
				identity = "tactical",
				quality = "hero",
				kind = "hud",
				focus = "BadHud.Reticle",
				root = {
					type = "panel",
					name = "Root",
					size = { 1920, 1080 },
					children = {
						{ type = "crosshair", name = "Reticle", style = "cross", size = 24, slot = "center" },
					},
				},
			}, nil, nil, { tactical = TACTICAL_ID })
			check.is_true(
				hasIssue(issues, "error", "banned_component"),
				"expected banned_component error for crosshair"
			)
			check.is_true(hasIssue(issues, "error", "crosshair"), "error should name the component type")
		end)

		test.case("ammo counter on a tactical identity is a compile error", function()
			local _, issues = UI.compile({
				name = "BadHud2",
				identity = "tactical",
				quality = "hero",
				kind = "hud",
				focus = "BadHud2.AmmoBlock",
				root = {
					type = "panel",
					name = "Root",
					size = { 1920, 1080 },
					children = {
						{ type = "ammo", name = "AmmoBlock", value = 30, reserve = 90, slot = "bottomRight" },
					},
				},
			}, nil, nil, { tactical = TACTICAL_ID })
			check.is_true(hasIssue(issues, "error", "banned_component"), "expected banned_component error for ammo")
			check.is_true(hasIssue(issues, "error", "ammo"), "error should name the component type")
		end)

		test.case("both crosshair and ammo on a tactical identity produce two errors", function()
			local _, issues = UI.compile({
				name = "BadHud3",
				identity = "tactical",
				quality = "hero",
				kind = "hud",
				focus = "BadHud3.AmmoBlock",
				root = {
					type = "panel",
					name = "Root",
					size = { 1920, 1080 },
					children = {
						{ type = "crosshair", name = "Reticle", style = "cross", size = 24, slot = "center" },
						{ type = "ammo", name = "AmmoBlock", value = 30, reserve = 90, slot = "bottomRight" },
					},
				},
			}, nil, nil, { tactical = TACTICAL_ID })
			local count = 0
			for _, issue in issues do
				if issue.severity == "error" and string.find(issue.message, "banned_component", 1, true) then
					count += 1
				end
			end
			check.is_true(count >= 2, `expected >= 2 banned_component errors, got {count}`)
		end)

		test.case("screen with no banned components on tactical identity compiles cleanly", function()
			local _, issues = UI.compile({
				name = "GoodHud",
				identity = "tactical",
				quality = "hero",
				kind = "hud",
				focus = "GoodHud.HealthBar",
				root = {
					type = "panel",
					name = "Root",
					size = { 1920, 1080 },
					children = {
						{
							type = "bar",
							name = "HealthBar",
							value = 0.8,
							fill = "danger",
							size = { 160, 6 },
							slot = "bottomLeft",
						},
					},
				},
			}, nil, nil, { tactical = TACTICAL_ID })
			check.is_true(
				not hasIssue(issues, "error", "banned_component"),
				"good screen must not have banned_component errors"
			)
		end)

		test.case("grandfathered screen gets warn, not error", function()
			local id_with_grandfather = {
				name = "tactical",
				fonts = TACTICAL_ID.fonts,
				shape = TACTICAL_ID.shape,
				bans = TACTICAL_ID.bans,
				banned_components = { "crosshair" },
				banned_components_grandfather = { "LegacyScreen" },
				minimums = TACTICAL_ID.minimums,
				references = TACTICAL_ID.references,
			}
			local _, issues = UI.compile({
				name = "LegacyScreen",
				identity = "tactical",
				quality = "hero",
				kind = "hud",
				focus = "LegacyScreen.Reticle",
				root = {
					type = "panel",
					name = "Root",
					size = { 1920, 1080 },
					children = {
						{ type = "crosshair", name = "Reticle", style = "cross", size = 24, slot = "center" },
					},
				},
			}, nil, nil, { tactical = id_with_grandfather })
			check.is_true(
				hasIssue(issues, "warn", "banned_component"),
				"grandfathered screen should produce a warning, not an error"
			)
			check.is_true(
				not hasIssue(issues, "error", "banned_component"),
				"grandfathered screen must not produce an error"
			)
		end)

		test.case("identity with no banned_components: no ban errors regardless of components used", function()
			local _, issues = UI.compile(
				{
					name = "AnyHud",
					identity = "plain",
					quality = "hero",
					kind = "hud",
					focus = "AnyHud.Reticle",
					root = {
						type = "panel",
						name = "Root",
						size = { 1920, 1080 },
						children = {
							{ type = "crosshair", name = "Reticle", style = "cross", size = 24, slot = "center" },
						},
					},
				},
				nil,
				nil,
				{
					plain = {
						name = "plain",
						fonts = { font = "RobotoCondensed" },
						shape = {
							line = "#000000",
							fill = "#0a0c0e",
							fill_alpha = 0.5,
							width = 1,
							corner = "square",
							glow = "#f0f0ec",
							grain = 0.0,
							gloss = 0.0,
							shade = 0.0,
							shadow = 0,
							buttons = { "accent" },
						},
						bans = { "nothing" },
						minimums = { text = 14, button = 44, icon = 20 },
						references = {
							{
								game = "selftest",
								screen = "selftest only",
								image = "kit/selftest/ui/arcade_in_realistic/refs/dummy.png",
							},
						},
					},
				}
			)
			check.is_true(
				not hasIssue(issues, "error", "banned_component"),
				"identity without banned_components must not produce ban errors"
			)
		end)

		-- (2a) name-based matching: a plain panel whose name contains a banned word is an error
		test.case("panel named 'Minimap' on an identity that bans 'minimap' is a compile error", function()
			local _, issues = UI.compile({
				name = "NameBanHud",
				identity = "tactical",
				quality = "hero",
				kind = "hud",
				focus = "NameBanHud.Root",
				root = {
					type = "panel",
					name = "Root",
					size = { 1920, 1080 },
					children = {
						-- "compass" is in TACTICAL_ID.banned_components; a panel named "Compass" must trigger it
						{
							type = "panel",
							name = "Compass",
							size = { 100, 100 },
							slot = "topLeft",
						},
					},
				},
			}, nil, nil, { tactical = TACTICAL_ID })
			check.is_true(
				hasIssue(issues, "error", "banned_component"),
				"panel named 'Compass' should trigger banned_component error"
			)
			check.is_true(hasIssue(issues, "error", "compass"), "error should mention the banned word 'compass'")
		end)

		-- (2a) name-based matching: case-insensitive substring — "KillFeed" contains "feed"
		test.case("panel named 'KillFeed' on an identity that bans 'feed' is a compile error", function()
			local _, issues = UI.compile({
				name = "FeedNameHud",
				identity = "tactical",
				quality = "hero",
				kind = "hud",
				focus = "FeedNameHud.Root",
				root = {
					type = "panel",
					name = "Root",
					size = { 1920, 1080 },
					children = {
						{
							type = "label",
							name = "KillFeed",
							text = "Player eliminated",
							size = { 300, 20 },
							slot = "topRight",
						},
					},
				},
			}, nil, nil, { tactical = TACTICAL_ID })
			check.is_true(
				hasIssue(issues, "error", "banned_component"),
				"label named 'KillFeed' should trigger banned_component error"
			)
			check.is_true(hasIssue(issues, "error", "feed"), "error should mention the banned word 'feed'")
		end)

		-- (2b) the error path points at the offending node's own path, not its parent
		test.case("banned_component error path points at the offending node, not its parent", function()
			local _, issues = UI.compile({
				name = "PathCheckHud",
				identity = "tactical",
				quality = "hero",
				kind = "hud",
				focus = "PathCheckHud.Root",
				root = {
					type = "panel",
					name = "Root",
					size = { 1920, 1080 },
					children = {
						{
							type = "crosshair",
							name = "Reticle",
							style = "cross",
							size = 24,
							slot = "center",
						},
					},
				},
			}, nil, nil, { tactical = TACTICAL_ID })
			-- The error path must name the crosshair node itself, not "Root" or the screen name
			local found = false
			for _, issue in issues do
				if issue.severity == "error" and string.find(issue.message, "banned_component", 1, true) then
					-- path must end with "Reticle" (the node's own name), not "Root"
					if string.find(issue.path or "", "Reticle", 1, true) then
						found = true
					end
				end
			end
			check.is_true(
				found,
				"banned_component error must point at the offending node's path (Reticle), not its parent"
			)
		end)

		-- card qfab: the field identity bans "plate" from its own prose (bans[0]: no plates); FieldHud_v1's two corner
		-- shades were plate nodes named ShadeBR / ShadeBL - only the TYPE says what they are
		test.case("a banned word that names a base type (plate) fails a plate node whatever its name", function()
			local id = table.clone(TACTICAL_ID)
			id.banned_components = { "plate" }
			local _, issues = UI.compile({
				name = "PlateHud",
				identity = "tactical",
				quality = "prop",
				kind = "hud",
				root = {
					type = "panel",
					name = "Root",
					size = { 1920, 1080 },
					children = {
						{ type = "plate", name = "ShadeBR", size = { 900, 420 }, slot = "bottomRight" },
					},
				},
			}, nil, nil, { tactical = id })
			local found = false
			for _, issue in issues do
				if
					issue.severity == "error"
					and string.find(issue.message, 'banned_component "plate"', 1, true)
					and string.find(issue.path or "", "ShadeBR", 1, true)
				then
					found = true
				end
			end
			check.is_true(found, "a plate node named ShadeBR must fail an identity that bans plate, at its own path")
		end)

		-- card qfab (fresh review): the field identity bans "hp" (the owner's FieldHud_v1 verdict: no HP number); a
		-- substring reaching across two words of a name hit FlashPrompt and HealthPips - a ban sits inside ONE word
		test.case("a banned word inside one word of a name fails; one reaching across two words does not", function()
			local id = table.clone(TACTICAL_ID)
			id.banned_components = { "hp", "map" }
			local function bannedAt(nodeName: string): boolean
				local _, issues = UI.compile({
					name = "WordHud",
					identity = "tactical",
					quality = "prop",
					kind = "hud",
					root = {
						type = "panel",
						name = "Root",
						size = { 1920, 1080 },
						children = {
							{ type = "label", name = nodeName, text = "x", size = { 120, 24 }, slot = "bottomLeft" },
						},
					},
				}, nil, nil, { tactical = id })
				return hasIssue(issues, "error", "banned_component")
			end
			check.is_true(bannedAt("Hp"), "Hp is an HP number")
			check.is_true(bannedAt("HpBar"), "HpBar holds the word Hp")
			check.is_true(bannedAt("HPBar"), "HPBar holds the word HP")
			check.is_true(bannedAt("Minimap"), "map inside the one word Minimap")
			check.is_true(not bannedAt("FlashPrompt"), "flasH|Prompt: hp reaches across two words")
			check.is_true(not bannedAt("HealthPips"), "healtH|Pips: hp reaches across two words")
		end)
	end)
end

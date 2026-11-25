-- moderation.spec.luau (kit) — the moderation gate's WORDS half holds the words Roblox moderation acts on (blood decals,
-- *flesh* sound titles) wherever they sit in a name, and leaves ordinary names alone (stable is not stab, gutter is
-- not gut). The IMAGES half is proven by `kit selftest` (its drawn pool and splatter held, a fire puff passed).
local frk = require("../frk")
local test, check = frk.test, frk.check

local Moderation = require("../../lib/moderation")

local function held(text: string): boolean
	return #Moderation.terms(text) > 0
end

return function()
	test.suite("Moderation: the words that held the 2026-10-29 uploads", function()
		test.case("blood decals and flesh sounds are held, however they are spelled", function()
			check.is_true(held("blood_pool_03.png"))
			check.is_true(held("BloodSplat2.png"))
			check.is_true(held("gt-bloodsplatter"))
			check.is_true(held("impact_flesh_light.ogg"))
			check.is_true(held("slashFleshHeavy"))
			check.is_true(held("GORE_burst"))
		end)
		test.case("the word is named", function()
			local t = Moderation.terms("Game-impact_flesh_heavy")
			check.equal(#t, 1)
			check.equal(t[1], "flesh")
		end)
		test.case("stems inside one word are caught", function()
			check.is_true(held("decapitated_head"))
			check.is_true(held("dismemberFx"))
		end)
		test.case("other things moderation flags are held too", function()
			check.is_true(held("nsfw_poster"))
			check.is_true(held("nazi_flag"))
			check.is_true(held("drug_bag"))
		end)
	end)
	test.suite("Moderation: ordinary names pass", function()
		test.case("words that only contain a banned word are not it", function()
			check.is_true(not held("stable_door.png")) -- stab
			check.is_true(not held("gutter_pipe.fbx")) -- gut
			check.is_true(not held("method_board")) -- meth
			check.is_true(not held("gorgeous_banner")) -- gore
			check.is_true(not held("Sussex_cottage")) -- sex
		end)
		test.case("the kit's own effect and sound names pass", function()
			check.is_true(not held("ul_explosion_light.png"))
			check.is_true(not held("impact_body_light.ogg"))
			check.is_true(not held("hellfire_impact"))
			check.is_true(not held("coat_hero_game_Coat_color.png"))
		end)
	end)
end

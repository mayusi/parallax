-- games.spec.luau (kit) — several games in one checkout never collide: every game serves Rojo on its own port (never
-- the root's 34872, never another game's), and switching the shared active game is refused while another session may
-- still be working in the last one.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Game = require("../../cmd/game")

return function()
	test.suite("games: one Rojo port each, no silent switch", function()
		test.case("every game in this checkout has its own port, and a new one gets the next free port", function()
			check.equal(#Game.portProblems(), 0)
			local ports = Game.ports()
			local used = { [ports.root] = true }
			for _, p in ports.games do
				check.falsy(used[p]) -- unique
				used[p] = true
			end
			local free = Game.freePort()
			check.falsy(used[free])
			check.truthy(free >= Game.FIRST_PORT)
		end)

		test.case(
			"a game's moves name the clips and effects its sync mirrors (reactions and cue presets too)",
			function()
				local clips, effects = Game.piecesOf({
					{
						anim = "Katana1Kesa",
						vfx = { { frame = 4, preset = "katana_water_slash" } },
						onHit = { vfx = "hit_sparks", reaction = "KatanaHitReaction", sfx = "SwordHit" },
					},
					{ anim = "BgM11", onHit = {} },
					"not a move",
				})
				check.truthy(clips.Katana1Kesa and clips.KatanaHitReaction and clips.BgM11)
				check.truthy(effects.katana_water_slash and effects.hit_sparks)
				check.falsy(effects.SwordHit) -- a sound is not an effect (sound ids sync on their own)
				-- a move SET's parry names clips too (the defender's parry, the attacker's stagger)
				local setClips = Game.piecesOf({}, { { parry = { anim = "KatanaKaeshi", stagger = "KatanaStagger" } } })
				check.truthy(setClips.KatanaKaeshi and setClips.KatanaStagger)
			end
		)

		test.case("a switch to another game is refused for three hours unless --switch", function()
			local now = 1000000
			check.equal(Game.switchBlocked(nil, "SampleDojo", now - 60, now, false), nil) -- nothing active
			check.equal(Game.switchBlocked("SampleDojo", "SampleDojo", now - 60, now, false), nil) -- the same game
			local why = Game.switchBlocked("SampleDojo", "SampleDunes", now - 600, now, false)
			check.truthy(why and string.find(why, "SampleDojo was made active 10 min ago", 1, true))
			check.equal(Game.switchBlocked("SampleDojo", "SampleDunes", now - 600, now, true), nil) -- --switch
			check.equal(Game.switchBlocked("SampleDojo", "SampleDunes", now - Game.SWITCH_GUARD * 60, now, false), nil)
		end)

		test.case(
			"a game gets the project's sound ids (its Foley is not silent), never over a sound it made itself",
			function()
				local game = { theme = "rbxassetid://1", boot_step_grass_light = "rbxassetid://old" }
				local project = {
					boot_step_grass_light = "rbxassetid://new",
					land_heavy = "rbxassetid://3",
					theme = "rbxassetid://9",
				}
				local merged, changed = Game.mergeSoundIds(game, project, { theme = true })
				check.equal(merged.boot_step_grass_light, "rbxassetid://new") -- a re-upload reaches the game
				check.equal(merged.land_heavy, "rbxassetid://3")
				check.equal(merged.theme, "rbxassetid://1") -- the game's own upload stays
				check.equal(changed, 2)
				check.equal(game.boot_step_grass_light, "rbxassetid://old") -- (pure: the input is untouched)
				local _, again = Game.mergeSoundIds(merged, project, { theme = true })
				check.equal(again, 0)
			end
		)
	end)
end

-- vfxdailies.spec.luau (kit) — a recorded play ends by naming a folder of frames to LOOK at, whatever the dailies
-- step did (kit/lib/vfxdailies.luau; the VFX studio-route plan, V0).
local frk = require("../frk")
local test, check = frk.test, frk.check

local VfxDailies = require("../../lib/vfxdailies")

local function endsWith(s: string, tail: string): boolean
	return string.sub(s, -#tail) == tail
end

return function()
	test.suite("VfxDailies (the last word of a recorded play)", function()
		test.case("dailies made: the play's summary carries them and ends with their LOOK folder", function()
			local summary, next = VfxDailies.playReport("vfx play: ember recorded", "LOOK at the mp4", {
				status = "pass",
				summary = "dailies ember: 3 beat(s), 18 strip(s) at 640 px a frame. 1 key: it arrives: the scene in one frame, ours over 0.07 s. LOOK: build/vfx/dailies/ember/",
				next_action = "open build/vfx/dailies/ember/beat1_01.png onward at full size",
			}, "ember")
			check.is_true(endsWith(summary, "LOOK: build/vfx/dailies/ember/"))
			check.is_true(string.find(summary, "vfx play: ember recorded. dailies ember: 3 beat(s)", 1, true) ~= nil)
			check.equal(next, "open build/vfx/dailies/ember/beat1_01.png onward at full size")
		end)

		test.case("dailies FAILED but made pictures (a blank recording): its own words and folder stand", function()
			local summary = VfxDailies.playReport("vfx play: ember recorded", "LOOK at the mp4", {
				status = "fail",
				summary = "dailies ember: ours never lights up in any beat - a blank recording. LOOK: build/vfx/dailies/ember/",
			}, "ember")
			check.is_true(string.find(summary, "ours never lights up", 1, true) ~= nil)
			check.is_true(endsWith(summary, "LOOK: build/vfx/dailies/ember/"))
		end)

		test.case(
			"no dailies (no recording found, or the step crashed): the recorded frames are named instead",
			function()
				local summary, next = VfxDailies.playReport("vfx play: ember recorded", "LOOK at the mp4", {
					status = "fail",
					summary = "dailies ember: no recording build/vfx/booth/ember_play_hero.mp4",
				}, "ember")
				check.is_true(string.find(summary, "No dailies (dailies ember: no recording", 1, true) ~= nil)
				check.is_true(endsWith(summary, "LOOK: build/vfx/booth/ember_play/"))
				check.is_true(string.find(next, "lune run kit vfx dailies ember", 1, true) ~= nil)
				local crashed =
					VfxDailies.playReport("vfx play: ember_blockout recorded", "LOOK at the mp4", nil, "ember_blockout")
				check.is_true(string.find(crashed, "No dailies (the dailies step crashed)", 1, true) ~= nil)
				check.is_true(endsWith(crashed, "LOOK: build/vfx/booth/ember_blockout_play/"))
			end
		)
	end)
end

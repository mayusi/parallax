-- animasks.spec.luau — what a move ASKS survives the owner's Blender edit (kit/cmd/anim.luau AnimCmd.blendAsks; the
-- owner's V3 list anim stage F.1, card r66z: "a pose edited in Blender loses its match ask"): an edited .blend keeps
-- its own motion, timing and markers, and the pose file's asks that are not motion are carried onto its clip.
local frk = require("../frk")
local test, check = frk.test, frk.check

local AnimCmd = require("../../cmd/anim")

return function()
	test.suite("the asks of a posed move through its Blender edit (AnimCmd.blendAsks)", function()
		test.case("match, hands, slides, contact, on_blade, target and upper ride onto the baked clip", function()
			local pose = {
				match = { pose = true },
				hands = "two",
				slides = { ["Right Leg"] = { { 0.1, 0.3 } } },
				contact = { { a = "weapon", b = "Torso" } },
				on_blade = { left = true },
				target = { 0, 0, -4 },
				upper = true,
				events = { { name = "Hit", t = 0.2 } },
				beats = { cut = { 0.1, 0.3 } },
				priority = "Action",
			}
			local clip = AnimCmd.blendAsks({ events = { { name = "Hit", t = 0.25 } }, priority = "Movement" }, pose)
			for _, k in AnimCmd.ASKS do
				check.truthy(clip[k] == pose[k])
			end
			-- the edit's own motion and timing stay its own: its markers, its priority, no beats taken from the keys
			check.equal(clip.events[1].t, 0.25)
			check.equal(clip.priority, "Movement")
			check.equal(clip.beats, nil)
		end)
		test.case("what the edited clip says itself wins; no pose file changes nothing", function()
			local clip = AnimCmd.blendAsks({ hands = "right" }, { hands = "two", match = { pose = true } })
			check.equal(clip.hands, "right")
			check.truthy(clip.match ~= nil)
			local bare = AnimCmd.blendAsks({ name = "X" }, nil)
			check.equal(bare.match, nil)
		end)
	end)
end

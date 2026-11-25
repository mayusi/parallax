-- animsaid.spec.luau — WHAT A SOURCE SAYS RIDES ON ITS CLIP (2026-11-15): a keyframe spec's hands, target, contacts and
-- finish are carried onto the clip it compiles to and through the fold to R6, where the build's gates read them
-- (kit/anim/in_hand.py, contact.py, collide.py, finish.py); a move's are merged onto its route's clip by the build.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local Anim = require("../../lib/anim")

local function spec(more: { [string]: any }): any
	local s: { [string]: any } = {
		name = "SpecSaid",
		rig = "R6",
		fps = 30,
		keys = {
			{ t = 0, pose = { Torso = { 0, 0, 0 }, ["Right Arm"] = { 0, 0, 0 } } },
			{ t = 0.5, pose = { Torso = { 0, 20, 0 }, ["Right Arm"] = { 90, 0, 0 } } },
		},
		events = { { name = "Hit", t = 0.4 } },
	}
	for k, v in more do
		s[k] = v
	end
	return s
end

return function()
	test.suite("what a source says rides on its clip", function()
		test.case("a keyframe spec: its hands, target, contacts and finish reach the R6 clip the gates read", function()
			local contact = { { a = "Right Arm", b = "Torso" } }
			local finish = { velocity = { max_deg_s = 2000 } }
			local slides = { { foot = "both", from = 0.1, to = 0.3, kind = "skid" } }
			local said = { hands = "two", target = { 0, 0, -4 }, contact = contact, finish = finish, slides = slides }
			local clip = Anim.clipFromSpec(spec(said), {}) :: any
			check.truthy(
				clip.hands == "two" and clip.target == said.target and clip.contact == contact and clip.finish == finish
			)
			local r6 = Anim.foldToR6(clip) :: any
			check.truthy(r6.rig == "R6" and r6.hands == "two" and r6.target == said.target)
			check.truthy(r6.contact == contact and r6.finish == finish)
			check.truthy(clip.slides == slides and r6.slides == slides)
			-- unsaid: nothing is made up
			local plain = Anim.foldToR6(Anim.clipFromSpec(spec({}), {}) :: any) :: any
			check.truthy(
				plain.hands == nil
					and plain.target == nil
					and plain.contact == nil
					and plain.finish == nil
					and plain.slides == nil
			)
		end)
		test.case("a move, a gait, an import: the build merges the same words from the source file", function()
			local build = fs.readFile("kit/cmd/anim.luau")
			check.truthy(
				string.find(build, '"target",\n\t\t\t"contact",\n\t\t\t"hands",\n\t\t\t"slides",\n', 1, true) ~= nil
			)
			local strike = fs.readFile("kit/anim/strike.py")
			-- (+ "on_blade", 2026-11-18: a hand said to hold the blade, kit/anim/in_hand.py - the V3 list's stage C.2)
			check.truthy(
				string.find(strike, 'for said in ("target", "contact", "hands", "slides", "on_blade"):', 1, true) ~= nil
			)
		end)
	end)
end

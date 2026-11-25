-- animcue.spec.luau — THE ADDITIVE EVERY CLIENT SEES (LIMITATIONS_FIXES_V4 4.4 / 13.4.3, card txjy): a layer the
-- server starts is written as a cue on the character and each client's watcher plays it from where it is by now.
-- The cue's rules (AnimRules.cueName / additiveCue / stopCue / readCue) and the wiring that carries them; the layer
-- itself on a watching client: tests/playtest/anim_additive_cue.luau (Studio).
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local R = require("../../../src/kit/AnimRules")

return function()
	test.suite("the additive every client sees (V4 13.4.3, txjy)", function()
		test.case(
			"a cue says when the layer began, its weight, speed and loop; a watcher reads how far in it is",
			function()
				local v = R.additiveCue(100.25, 0.5, 2, true) :: string
				check.equal(v, "100.2500;0.5000;2.0000;1")
				local c: any = R.readCue(v, 101)
				check.truthy(math.abs(c.at - 0.75) < 1e-6)
				check.equal(c.weight, 0.5)
				check.equal(c.speed, 2)
				check.equal(c.loop, true)
				-- a watcher that reads it before its start (the clocks a hair apart): from the start, not before it
				local early: any = R.readCue(v, 100)
				check.equal(early.at, 0)
			end
		)

		test.case("the stop cue stops it; a weight and a speed out of bounds are held to them", function()
			check.equal(R.readCue(R.stopCue(12), 13), "stop")
			local c: any = R.readCue(R.additiveCue(0, 7, 50, false), 0)
			check.equal(c.weight, 1)
			check.equal(c.speed, 10)
			check.equal(c.loop, false)
		end)

		test.case("what is not a cue plays nothing", function()
			for _, bad in { nil, 5, "", "1;2;3", "a;b;c;d", "1;1;1;2", "nan;1;1;0", "1;1;1;0;9", string.rep("1", 90) } do
				check.truthy(R.readCue(bad, 10) == nil)
			end
			check.truthy(R.additiveCue(0 / 0, 1, 1, false) == nil)
			check.truthy(R.additiveCue(1, 1, 0, false) == nil)
			check.truthy(R.additiveCue(1, 1, -1, false) == nil)
			check.truthy(R.readCue("1;1;1;0", 0 / 0) == nil)
		end)

		test.case("a cue is an attribute: a clip's name of letters, digits and _ only", function()
			check.equal(R.cueName("Flinch"), "KitAdd_Flinch")
			check.equal(R.cueName("Breath_2"), "KitAdd_Breath_2")
			for _, bad in { "", "has space", "a.b", "slash/x", string.rep("x", 91), 7, nil } do
				check.truthy(R.cueName(bad) == nil)
			end
		end)

		test.case(
			"the server writes the cue and every client's watcher plays it, observing a body it does not own",
			function()
				local anim = fs.readFile("src/kit/Anim.luau")
				for _, line in
					{
						"local cue = if RunService:IsServer() then AnimRules.cueName(clip) else nil",
						"character:SetAttribute(cue, value)",
						"character:SetAttribute(cue, AnimRules.stopCue(workspace:GetServerTimeNow()))",
						"if not owns(character) and not o.observe then",
						"function Anim.watchAdditive(character: Model): () -> ()",
						"{ weight = c.weight, speed = c.speed, loop = c.loop, at = c.at, observe = true }",
					}
				do
					check.truthy(string.find(anim, line, 1, true) ~= nil)
				end
				local client = fs.readFile("src/kit/client/AnimRoot.client.luau")
				check.truthy(string.find(client, "return Anim.watchAdditive(character)", 1, true) ~= nil)
			end
		)
	end)
end

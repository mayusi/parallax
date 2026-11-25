-- animsweep.spec.luau — THE BODY AS A ROOT TRAVEL SWEEPS IT (LIMITATIONS_FIXES_V4 4.4 / 13.4.3): Anim.applyRoot casts a
-- box the torso's own width and depth (workspace:Blockcast), not the 0.9-stud ball that was narrower than the
-- shoulders; the box keeps a step under 2.5 studs the Humanoid's to climb and reaches the head's top.
-- (The cast itself in the engine: tests/playtest/anim_root_blockcast.luau.)
local frk = require("../frk")
local test, check = frk.test, frk.check

local AnimWarp = require("../../../src/kit/AnimWarp")
local fs = require("@lune/fs")

return function()
	test.suite("the swept body of a root travel (V4 13.4.3)", function()
		test.case("an R6 torso: 2 wide, 1 deep, from 2.6 over the floor to the head's top", function()
			local s = AnimWarp.sweepBox(2, 1)
			check.equal(s.size[1], 2)
			check.equal(s.size[3], 1)
			local rootOverFloor = 3 -- (an R6 root rides 3 studs over the floor)
			local bottom = rootOverFloor + s.up - s.size[2] / 2
			local top = rootOverFloor + s.up + s.size[2] / 2
			check.truthy(math.abs(bottom - 2.6) < 1e-9) -- a step under 2.5 studs is not in its way
			check.truthy(math.abs(top - 5) < 1e-9) -- the head's top (torso 2 + head 1 over the hips at 2)
			check.truthy(s.size[1] / 2 > 0.9) -- wider than the ball it replaced: a post 0.95 off the line is met
			check.truthy(s.probe[1] < s.size[1] and s.probe[3] < s.size[3] and s.probe[2] == s.size[2])
		end)

		test.case("a body that is not R6 sizes its own box; numbers that are not sizes fall back to R6's", function()
			local wide = AnimWarp.sweepBox(4, 2)
			check.equal(wide.size[1], 4)
			check.equal(wide.size[3], 2)
			for _, bad in { { 0 / 0, 1 }, { -2, 1 }, { math.huge, 1 }, { 0, 0 } } do
				local s = AnimWarp.sweepBox(bad[1], bad[2])
				check.equal(s.size[1], 2)
				check.truthy(s.size[3] == 1 or bad[2] == 1)
			end
			local none = AnimWarp.sweepBox(nil, nil)
			check.equal(none.size[1], 2)
			check.equal(none.size[3], 1)
		end)

		test.case("the game's root update casts that box, turned the way the body faces", function()
			local anim = fs.readFile("src/kit/Anim.luau")
			for _, line in
				{
					"local shape = AnimWarp.sweepBox(",
					"workspace:Blockcast(CFrame.new(ax, yb, az) * facing, SIZE, dir.Unit * (len + extra), params)",
					"workspace:GetPartBoundsInBox(CFrame.new(bx, yb, bz) * facing, BOX_PROBE, over)",
					"local facing = CFrame.Angles(0, yawOf(rootPart.CFrame), 0)",
				}
			do
				check.truthy(string.find(anim, line, 1, true) ~= nil)
			end
		end)
	end)
end

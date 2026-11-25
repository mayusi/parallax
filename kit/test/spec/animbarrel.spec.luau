-- animbarrel.spec.luau — THE BARREL AT REST follows the look (LIMITATIONS_FIXES_V4 4.4 / 13.4.3: idle barrel pitch /
-- yaw beside Anim.lookAt): AnimLayers.barrelTurn says how far to turn the holding shoulder so the barrel the clip holds
-- points at the target - clamped to an arm's reach, nothing for a target behind, nothing on numbers that are not.
-- (src/kit/AnimAim.barrel lays it on the shoulder while the body is idle: proven in Studio, the anim_barrel_aim
-- playtest.)
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local AnimLayers = require("../../../src/kit/AnimLayers")

local function near(a: number, b: number, tol: number?): boolean
	return math.abs(a - b) <= (tol or 1e-6)
end

-- the direction of yaw / pitch (radians) in the torso's frame (-Z ahead, +Y up; yaw + = to the left)
local function dirOf(yaw: number, pitch: number): (number, number, number)
	return -math.sin(yaw) * math.cos(pitch), math.sin(pitch), -math.cos(yaw) * math.cos(pitch)
end

return function()
	test.suite("the barrel at rest follows the look (V4 13.4.3)", function()
		test.case("a barrel held straight ahead turns by the target's own yaw and pitch", function()
			for _, c in { { 20, 0 }, { -30, 10 }, { 0, -25 }, { 12, 30 } } do
				local tx, ty, tz = dirOf(math.rad(c[1]), math.rad(c[2]))
				local yaw, pitch = AnimLayers.barrelTurn(0, 0, -1, tx * 40, ty * 40, tz * 40)
				check.truthy(near(math.deg(yaw), c[1], 1e-6))
				check.truthy(near(math.deg(pitch), c[2], 1e-6))
			end
		end)

		test.case("a barrel the clip already holds aside turns only by what is left, the short way round", function()
			local bx, by, bz = dirOf(math.rad(170), math.rad(5))
			local tx, ty, tz = dirOf(math.rad(-175), math.rad(5))
			local yaw, pitch = AnimLayers.barrelTurn(bx, by, bz, tx, ty, tz, 90, 40)
			check.truthy(near(math.deg(yaw), 15, 1e-6)) -- (across the half turn: +15, not -345)
			check.truthy(near(pitch, 0, 1e-9))
		end)

		test.case("an arm is turned no further than its reach; a target behind is let go", function()
			local tx, ty, tz = dirOf(math.rad(50), math.rad(60))
			local yaw, pitch = AnimLayers.barrelTurn(0, 0, -1, tx, ty, tz, 35, 40)
			check.truthy(near(math.deg(yaw), 35 * AnimLayers.lookWeight(math.rad(50), 35), 1e-6))
			check.truthy(math.deg(pitch) <= 40 + 1e-9)
			local bx2, by2, bz2 = dirOf(math.rad(150), 0)
			local y2, p2 = AnimLayers.barrelTurn(0, 0, -1, bx2, by2, bz2, 35, 40) -- (150 deg: past reach + give)
			check.truthy(y2 == 0 and p2 == 0)
		end)

		test.case("numbers that are not numbers turn nothing", function()
			for _, bad in { 0 / 0, math.huge, -math.huge } do
				local y, p = AnimLayers.barrelTurn(bad, 0, -1, 0, 0, -1)
				check.truthy(y == 0 and p == 0)
				y, p = AnimLayers.barrelTurn(0, 0, -1, 1, bad, -1)
				check.truthy(y == 0 and p == 0)
			end
		end)

		test.case(
			"AnimAim.barrel lays it on the holding shoulder, on the joints' one record, only while idle",
			function()
				local aim = fs.readFile("src/kit/AnimAim.luau")
				for _, line in
					{
						"yaw, pitch = AnimLayers.barrelTurn(dir.X, dir.Y, dir.Z, to.X, to.Y, to.Z, opts.maxYaw, opts.maxPitch)",
						"local was = AnimLayers.stackBase(stack, shoulder.Transform, frame, sameCF, joined)",
						"AnimLayers.stackWrite(stack, cf)",
						"local back = AnimLayers.stackRelease(AnimLayers.stackOf(m), m.Transform, sameCF)",
						"if tr.Priority.Value >= Enum.AnimationPriority.Action.Value and tr.WeightCurrent > 0.05 then",
					}
				do
					check.truthy(string.find(aim, line, 1, true) ~= nil)
				end
			end
		)
	end)
end

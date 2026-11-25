-- animgrip.spec.luau — the sword as its own joint (src/kit/AnimGrip, board m39b): the Handle Transform puts the weapon
-- exactly where the clip wants it, for any arm frame, and the identity Transform is Roblox's own RightGrip hold.
local frk = require("../frk")
local test, check = frk.test, frk.check

local AnimGrip = require("../../../src/kit/AnimGrip")

local function rotX(deg: number, t: { number }): { { number } }
	local c, s = math.cos(math.rad(deg)), math.sin(math.rad(deg))
	return { { 1, 0, 0, t[1] }, { 0, c, -s, t[2] }, { 0, s, c, t[3] }, { 0, 0, 0, 1 } }
end

local function rotY(deg: number, t: { number }): { { number } }
	local c, s = math.cos(math.rad(deg)), math.sin(math.rad(deg))
	return { { c, 0, s, t[1] }, { 0, 1, 0, t[2] }, { -s, 0, c, t[3] }, { 0, 0, 0, 1 } }
end

local function maxDiff(a: { { number } }, b: { { number } }): number
	local m = 0
	for i = 1, 4 do
		for j = 1, 4 do
			m = math.max(m, math.abs(a[i][j] - b[i][j]))
		end
	end
	return m
end

return function()
	test.suite("AnimGrip (the sword as its own joint)", function()
		test.case("transform then place reproduces the weapon frame for any arm", function()
			local arm = AnimGrip.mul(rotY(35, { 1.5, 0.2, -0.3 }), rotX(-70, { 0, 0, 0 }))
			local handle = AnimGrip.mul(rotX(20, { 1.9, -0.8, -1.4 }), rotY(-60, { 0, 0, 0 }))
			local T = AnimGrip.transform(arm, handle)
			check.truthy(maxDiff(AnimGrip.place(arm, T), handle) < 1e-9)
		end)
		test.case("the identity Transform is Roblox's RightGrip hold (one stud down the arm)", function()
			local arm = rotY(0, { 1.5, 0, 0 })
			local held = AnimGrip.place(arm, rotX(0, { 0, 0, 0 }))
			check.truthy(
				math.abs(held[1][4] - 1.5) < 1e-9 and math.abs(held[2][4] + 1) < 1e-9 and math.abs(held[3][4]) < 1e-9
			)
		end)
		test.case("inv undoes a rigid frame", function()
			local m = AnimGrip.mul(rotY(80, { 3, -2, 1 }), rotX(33, { 0, 0, 0 }))
			check.truthy(maxDiff(AnimGrip.mul(m, AnimGrip.inv(m)), rotX(0, { 0, 0, 0 })) < 1e-9)
		end)
	end)
end

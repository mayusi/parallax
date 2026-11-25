-- animroothold.spec.luau — THE ROOT'S OWN TURN through a get-up (LIMITATIONS_FIXES_V4 4.4 / 13.4.3): GettingUp stands
-- the root up in a few frames and the body, rigid on it, snapped upright with it. AnimRules.rootHold gives the root
-- joint that turn back and lets it go over the blend: the body is where the ragdoll left it at 0, upright at T, and
-- never turns faster than the eased blend lets it - however fast the root itself stands up.
local frk = require("../frk")
local test, check = frk.test, frk.check

local R = require("../../../src/kit/AnimRules")

local function turn(axis: { number }, deg: number): { number }
	local l = math.sqrt(axis[1] ^ 2 + axis[2] ^ 2 + axis[3] ^ 2)
	local h = math.rad(deg) / 2
	return { axis[1] / l * math.sin(h), axis[2] / l * math.sin(h), axis[3] / l * math.sin(h), math.cos(h) }
end

local function mul(a: { number }, b: { number }): { number }
	return {
		a[4] * b[1] + a[1] * b[4] + a[2] * b[3] - a[3] * b[2],
		a[4] * b[2] - a[1] * b[3] + a[2] * b[4] + a[3] * b[1],
		a[4] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[4],
		a[4] * b[4] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3],
	}
end

-- the angle between two turns, degrees
local function apart(a: { number }, b: { number }): number
	local d = math.abs(a[1] * b[1] + a[2] * b[2] + a[3] * b[3] + a[4] * b[4])
	return math.deg(2 * math.acos(math.min(1, d)))
end

return function()
	test.suite("the root's own turn through a get-up (V4 13.4.3)", function()
		test.case("the body lies where the ragdoll left it at 0 and stands with its root at the end", function()
			local lying, up = turn({ 1, 0, 0 }, -90), { 0, 0, 0, 1 }
			-- the root already stood up (GettingUp's few frames): the hold gives all of it back at 0
			check.truthy(apart(mul(up, R.rootHold(lying, up, 0.35, 0)), lying) < 1e-6)
			check.truthy(apart(R.rootHold(lying, up, 0.35, 0.35), { 0, 0, 0, 1 }) < 1e-6)
			check.truthy(apart(R.rootHold(lying, up, 0.35, 5), { 0, 0, 0, 1 }) < 1e-6)
			-- a root that never turned: nothing is laid on the joint
			check.truthy(apart(R.rootHold(lying, lying, 0.35, 0.1), { 0, 0, 0, 1 }) < 1e-6)
			-- a blend of 0: the root's turn is the body's at once
			check.truthy(apart(R.rootHold(lying, up, 0, 0), { 0, 0, 0, 1 }) < 1e-6)
		end)

		test.case(
			"a root that snaps up in 3 frames: the body rises over the blend, never faster than it allows",
			function()
				local lying = turn({ 1, 0, 0.3 }, -95)
				local T, fps = 0.35, 60
				local prev: { number }? = nil
				local fastest, bare = 0, 0
				local prevRoot: { number }? = nil
				for i = 0, math.ceil(T * fps) + 6 do
					local t = i / fps
					local share = math.min(1, i / 3) -- (GettingUp: lying to upright in 3 frames)
					local root = turn({ 1, 0, 0.3 }, -95 * (1 - share)) -- (the root's own path: lying -> upright)
					local world = mul(root, R.rootHold(lying, root, T, t))
					if prev then
						fastest = math.max(fastest, apart(prev, world))
					end
					if prevRoot then
						bare = math.max(bare, apart(prevRoot, root))
					end
					prev, prevRoot = world, root
					if i == 0 then
						check.truthy(apart(world, lying) < 1e-6)
					end
				end
				check.truthy(apart(prev :: any, { 0, 0, 0, 1 }) < 1e-6) -- upright at the end
				check.truthy(bare > 30) -- (without the hold: over 30 degrees in a frame)
				-- with it: at most the eased blend's own peak - 95 deg over 21 frames, 1.875 times the mean speed
				check.truthy(fastest < 95 / (T * fps) * 1.875 + 0.5)
			end
		)

		test.case("numbers that are not numbers lay nothing on the joint", function()
			local q = R.rootHold({ 0 / 0, 0, 0, 1 }, { 0, 0, 0, 1 }, 0.35, 0.1)
			check.truthy(q[1] == q[1] and q[4] == q[4])
			local z = R.rootHold(turn({ 1, 0, 0 }, 90), { 0, 0, 0, 1 }, 0 / 0, 0.1)
			check.truthy(apart(z, { 0, 0, 0, 1 }) < 1e-6)
		end)
	end)
end

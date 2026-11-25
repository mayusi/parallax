-- animsecondary.spec.luau — SECONDARY MOTION's rule, whole (the owner's method lists, 2026-11-14: secondary motion
-- simulation, spring-based animation): src/kit/AnimLayers.swing (one spring) and sway (one frame of an accessory, what
-- src/kit/AnimSecondary runs): where it settles, how stiffness and damping change it, that the frame rate does not,
-- the limits, and what a stalled frame does.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local L = require("../../../src/kit/AnimLayers")

local function near(a: number, b: number, tol: number?): boolean
	return math.abs(a - b) <= (tol or 1e-9)
end

-- a spring held under a steady push for `seconds`, stepped at `fps`
local function held(accel: number, seconds: number, fps: number, k: number?, z: number?): { x: number, v: number }
	local s = { x = 0, v = 0 }
	for _ = 1, math.floor(seconds * fps + 0.5) do
		s = L.swing(s, accel, 1 / fps, k, z)
	end
	return s
end

return function()
	test.suite("secondary motion: one spring", function()
		test.case("under a steady push it settles where the spring balances it: -push / stiffness", function()
			local s = held(30, 4, 60)
			check.truthy(near(s.x, -30 / 60, 1e-4) and math.abs(s.v) < 1e-4)
			local stiff = held(30, 4, 60, 240)
			check.truthy(near(stiff.x, -30 / 240, 1e-4)) -- four times as stiff: a quarter of the lag
			check.truthy(near(held(-30, 4, 60).x, 30 / 60, 1e-4)) -- pushed the other way: the other way
		end)
		test.case("damping decides the wobble: none at 1, more the lower it is", function()
			local function overshoot(z: number): number
				local s, worst = { x = 0, v = 0 }, 0
				for _ = 1, 600 do
					s = L.swing(s, 30, 1 / 120, 60, z)
					worst = math.min(worst, s.x)
				end
				return -worst - 0.5 -- how far past its resting place (0.5) it swung
			end
			check.truthy(overshoot(1) < 1e-3) -- critically damped: it arrives and stays
			check.truthy(overshoot(0.45) > 0.05 and overshoot(0.2) > overshoot(0.45))
		end)
		test.case("the frame rate barely changes the motion", function()
			-- a steady push: 30, 60 and 240 frames a second step the same 240 sub-steps; 144 does not divide them
			local a, b, c = held(30, 0.5, 30), held(30, 0.5, 60), held(30, 0.5, 240)
			check.truthy(near(a.x, c.x, 1e-9) and near(b.x, c.x, 1e-9) and near(held(30, 0.5, 144).x, c.x, 2e-3))
			-- a push that changes every frame (the real case) is held for the whole frame: measured 2026-11-14, 30 frames a
			-- second end 0.04 from where 240 put it, 60 end 0.02 from it - the slower the frame, the further
			local function shaken(fps: number): number
				local s = { x = 0, v = 0 }
				for i = 1, fps do
					s = L.swing(s, 30 * math.sin(i / fps * 12), 1 / fps)
				end
				return s.x
			end
			local d30, d60 = math.abs(shaken(30) - shaken(240)), math.abs(shaken(60) - shaken(240))
			check.truthy(d30 < 0.06 and d60 < d30)
			local one = L.swing({ x = 0, v = 0 }, 30, 0.1) -- one long frame is stepped inside as many short ones
			check.truthy(near(one.x, held(30, 0.1, 240).x, 1e-6))
		end)
		test.case("numbers that are not a stiffness or a damping fall back to the kit's own", function()
			local own = L.swing({ x = 0, v = 0 }, 30, 0.05)
			for _, bad in { 0, -5, 0 / 0 } do
				check.truthy(near(L.swing({ x = 0, v = 0 }, 30, 0.05, bad, nil).x, own.x))
			end
			check.truthy(near(L.swing({ x = 0, v = 0 }, 30, 0.05, nil, -1).x, own.x))
			check.truthy(near(L.swing({ x = 0, v = 0 }, 30, 0.05, nil, 0 / 0).x, own.x))
			check.truthy(near(L.swing({ x = 0, v = 0 }, 30, 0.05, "60" :: any, "soft" :: any).x, own.x)) -- an attribute typed as text
		end)
		test.case("a stiffness or a damping no spring stepped this way can take is held to one it can", function()
			for _, kz in { { 60, 50 }, { 1e6, 0.45 }, { 1e6, 50 } } do -- (damping 50 used to blow the spring up)
				local s = { x = 0, v = 0 }
				for _ = 1, 600 do
					s = L.swing(s, 30, 1 / 60, kz[1], kz[2])
					check.truthy(s.x == s.x and math.abs(s.x) < 10)
				end
			end
			check.truthy(near(held(30, 6, 60, 60, 50).x, held(30, 6, 60, 60, 2).x, 1e-9)) -- damping 50 is damping 2
		end)
	end)

	test.suite("secondary motion by kind: limits on the body's side, a held push, tiers (AN-31)", function()
		test.case(
			"each kind of accessory has its own spring and limits; what sits on the face does not sway",
			function()
				local hair, cape, hat =
					L.swayClass("Hair") :: L.SwayClass,
					L.swayClass("Back") :: L.SwayClass,
					L.swayClass("Hat") :: L.SwayClass
				check.is_true(cape.away > hair.away and hair.away > hat.away) -- a cape swings widest, a hat least
				check.is_true(cape.stiffness < hair.stiffness and hair.stiffness < hat.stiffness)
				check.is_true(cape.into < 5 and hair.into < 5) -- toward the body: small
				check.is_true((L.swayClass("Waist") :: L.SwayClass).hip == true)
				for _, rigid in { "Face", "Eyebrow", "Eyelash", "Shirt", "Pants", "LeftShoe" } do
					check.is_true(L.swayClass(rigid) == nil)
				end
				-- a kind the kit has not met, or none: the smallest that still moves
				check.is_true(L.swayClass("Unknown") == hat and L.swayClass(nil) == hat and L.swayClass("Tail") == hat)
			end
		)
		test.case("a cape swings off the back freely and INTO it hardly at all", function()
			local cape = L.swayClass("Back") :: L.SwayClass
			local off = L.swayLimit(math.rad(-60), 0, cape) -- (the hanging end going backward, away from the body)
			local into = L.swayLimit(math.rad(60), 0, cape) -- (... forward, into the back)
			check.is_true(near(off, -math.rad(35)) and near(into, math.rad(2)))
			local x, z = L.swayLimit(math.rad(-10), math.rad(5), cape) -- inside the limits: as it is
			check.is_true(near(x, -math.rad(10)) and near(z, math.rad(5)))
			local _, side = L.swayLimit(0, math.rad(40), cape)
			check.is_true(near(side, math.rad(15)))
			-- numbers that are none are no tilt
			x, z = L.swayLimit(0 / 0, 0 / 0, cape)
			check.is_true(x == 0 and z == 0)
		end)
		test.case("a sheath cannot swing into the leg it hangs beside, whichever hip", function()
			local sheath = L.swayClass("Waist") :: L.SwayClass
			-- on the RIGHT hip the hanging end may go right (out) and hardly left (into the leg)
			local _, out = L.swayLimit(0, math.rad(30), sheath, 1)
			local _, inward = L.swayLimit(0, math.rad(-30), sheath, 1)
			check.is_true(near(out, math.rad(12)) and near(inward, -math.rad(3)))
			-- on the LEFT hip the other way round
			_, out = L.swayLimit(0, math.rad(-30), sheath, -1)
			_, inward = L.swayLimit(0, math.rad(30), sheath, -1)
			check.is_true(near(out, -math.rad(12)) and near(inward, math.rad(3)))
			-- worn in the middle (a tail of a belt): either way
			local _, mid = L.swayLimit(0, math.rad(-30), sheath, 0)
			check.is_true(near(mid, -math.rad(12)))
			-- a hair accessory off-centre is not a hip accessory
			local _, hair = L.swayLimit(0, math.rad(-30), L.swayClass("Hair") :: L.SwayClass, 1)
			check.is_true(near(hair, -math.rad(12)))
		end)
		test.case("a hanging accessory tips the other way from one that stands up", function()
			-- (Studio: a cape went FORWARD as the body sped up ahead - the tilt is a hat's)
			local rx, rz = L.swayHang(0.2, -0.1, true)
			check.is_true(rx == -0.2 and rz == 0.1)
			rx, rz = L.swayHang(0.2, -0.1, false)
			check.is_true(rx == 0.2 and rz == -0.1)
			-- the body speeds up AHEAD (-Z): the spring's tilt is + (a hat's top goes back); a cape's hanging end must go BACK (-)
			local sx, sz = { x = 0, v = 0 }, { x = 0, v = 0 }
			local tilt = 0
			for _ = 1, 30 do
				sx, sz, tilt = L.sway(sx, sz, 0, -120, 1 / 60, { max = 1000 })
			end
			check.is_true(tilt > 0)
			local cape = L.swayClass("Back") :: L.SwayClass
			local hung = L.swayLimit((L.swayHang(tilt, 0, true)), 0, cape)
			check.is_true(hung < 0) -- the hanging end lags behind, off the back: free
		end)
		test.case("a piece that hangs in FRONT of the body is held on its other side", function()
			-- (the one review: a necklace swung into the chest unheld, and was held at 2 degrees swinging off it)
			local front = L.swayClass("Front") :: L.SwayClass
			local offBody = L.swayLimit(math.rad(30), 0, front, 0, nil, true) -- (the hanging end going ahead, off the chest)
			local intoBody = L.swayLimit(math.rad(-30), 0, front, 0, nil, true) -- (... back, into the chest)
			check.is_true(near(offBody, math.rad(front.away)) and near(intoBody, -math.rad(front.into)))
			-- the same class worn behind: the other way round
			offBody = L.swayLimit(math.rad(-30), 0, front, 0, nil, false)
			intoBody = L.swayLimit(math.rad(30), 0, front, 0, nil, false)
			check.is_true(near(offBody, -math.rad(front.away)) and near(intoBody, math.rad(front.into)))
		end)
		test.case("a game's cap holds every limit", function()
			local cape = L.swayClass("Back") :: L.SwayClass
			local x, z = L.swayLimit(math.rad(-60), math.rad(60), cape, 0, 5)
			check.is_true(near(x, -math.rad(5)) and near(z, math.rad(5)))
			x = L.swayLimit(math.rad(60), 0, cape, 0, 5)
			check.is_true(near(x, math.rad(2))) -- (the class's own limit is smaller: it stands)
			x, z = L.swayLimit(math.rad(-60), math.rad(60), cape, 0, 0)
			check.is_true(x == 0 and z == 0)
		end)
		test.case("a teleport's push is held to what a body can give, its direction kept", function()
			local ax, az = L.swayPush(30, -40)
			check.is_true(ax == 30 and az == -40) -- (a hard stop: as it is)
			ax, az = L.swayPush(30000, -40000) -- (a teleport: 50,000 studs a second squared for a frame)
			check.is_true(near(math.sqrt(ax * ax + az * az), L.SWAY_PUSH, 1e-6) and near(ax / az, -0.75, 1e-9))
			ax, az = L.swayPush(0 / 0, 5)
			check.is_true(ax == 0 and az == 0)
			ax, az = L.swayPush(math.huge, 0) -- (without end: no push, never a NaN left in the eased push)
			check.is_true(ax == 0 and az == 0)
			ax, az = L.swayPush(3, -math.huge)
			check.is_true(ax == 0 and az == 0)
			ax, az = L.swayPush(1000, 0, 50)
			check.is_true(near(ax, 50) and az == 0)
			-- ... and so a cape through a teleport stays inside its limits and is still again within a second and a half
			local cape = L.swayClass("Back") :: L.SwayClass
			local sx, sz = { x = 0, v = 0 }, { x = 0, v = 0 }
			local spring = { stiffness = cape.stiffness, damping = cape.damping, gain = cape.gain, max = 1000 }
			local worst = 0
			for i = 1, 90 do
				local px, pz = L.swayPush(if i == 1 then 60000 else 0, if i == 1 then 60000 else 0)
				local rx, rz
				sx, sz, rx, rz = L.sway(sx, sz, px, pz, 1 / 60, spring)
				rx, rz = L.swayLimit(rx, rz, cape)
				worst = math.max(worst, math.abs(rx), math.abs(rz))
				if i == 90 then
					check.is_true(math.abs(rx) < math.rad(0.5) and math.abs(rz) < math.rad(0.5))
				end
			end
			check.is_true(worst <= math.rad(cape.away) + 1e-9 and worst > 0)
		end)
		test.case("near the camera every frame, further off every other, beyond that not at all", function()
			check.is_true(L.swayTier(10) == 1 and L.swayTier(L.SWAY_NEAR) == 1)
			check.is_true(L.swayTier(L.SWAY_NEAR + 1) == L.SWAY_EVERY and L.swayTier(L.SWAY_FAR) == L.SWAY_EVERY)
			check.is_true(L.swayTier(L.SWAY_FAR + 1) == 0 and L.swayTier(5000) == 0)
			check.is_true(L.swayTier(nil) == 1 and L.swayTier(0 / 0) == 1) -- (no camera: as if near)
			check.is_true(L.swayTier(30, 20, 60) == L.SWAY_EVERY and L.swayTier(70, 20, 60) == 0) -- a game's own distances
			-- stepped every other frame with the time summed, a spring ends where the every-frame one does
			local a, b = { x = 0, v = 0 }, { x = 0, v = 0 }
			for i = 1, 120 do
				a = L.swing(a, 30, 1 / 60, 50, 0.45)
				if i % 2 == 0 then
					b = L.swing(b, 30, 2 / 60, 50, 0.45)
				end
			end
			check.is_true(near(a.x, b.x, 1e-3))
		end)
	end)

	test.suite("secondary motion: one frame of an accessory", function()
		local rest = { x = 0, v = 0 }
		test.case(
			"speeding up and braking tip it opposite ways; a push to the side tips it sideways, as far",
			function()
				-- Roblox axes: forward is -Z. The body accelerates forward: az < 0.
				local _, _, rx, rz = L.sway(rest, rest, 0, -200, 1 / 60)
				check.truthy(rx > 0 and rz == 0)
				local _, _, rx2 = L.sway(rest, rest, 0, 200, 1 / 60) -- it brakes
				check.truthy(near(rx2, -rx))
				local _, _, rx3, rz3 = L.sway(rest, rest, 200, 0, 1 / 60) -- it accelerates to its right
				check.truthy(rx3 == 0 and rz3 > 0 and near(rz3, rx))
			end
		)
		test.case("the tilt never passes its limit, and the spring behind it keeps its own state", function()
			local sx, sz = rest, rest
			local rx, rz = 0, 0
			for _ = 1, 120 do
				sx, sz, rx, rz = L.sway(sx, sz, 4000, -4000, 1 / 60) -- a violent, lasting push
			end
			check.truthy(near(rx, math.rad(25)) and near(rz, math.rad(25))) -- held at 25 degrees
			check.truthy(sx.x > math.rad(25)) -- (the spring itself went further: the limit is on what is shown)
			local _, _, small = L.sway(sx, sz, 4000, -4000, 1 / 60, { max = 5 })
			check.truthy(near(small, math.rad(5)))
			local _, _, none = L.sway(sx, sz, 4000, -4000, 1 / 60, { max = -3 })
			check.equal(none, 0) -- a limit below 0 is 0
		end)
		test.case("a stalled frame, or a time that is not one, moves nothing", function()
			local sx = { x = 0.1, v = 0.5 }
			for _, dt in { 0, -1, 0.5, 0 / 0 } do
				local nx, nz, rx = L.sway(sx, rest, 0, -5000, dt)
				check.truthy(nx.x == 0.1 and nx.v == 0.5 and nz.x == 0 and near(rx, 0.1))
			end
			local nx = L.sway(sx, rest, 0 / 0, 0, 1 / 60)
			check.truthy(nx.x == 0.1)
		end)
		test.case("gain scales the push; the game's options reach the spring", function()
			local _, _, a = L.sway(rest, rest, 0, -200, 1 / 60)
			local _, _, b = L.sway(rest, rest, 0, -200, 1 / 60, { gain = 0.04 })
			check.truthy(near(b, 2 * a, 1e-9))
			local _, _, soft = L.sway(rest, rest, 0, -200, 0.1, { stiffness = 20 })
			local _, _, hard = L.sway(rest, rest, 0, -200, 0.1, { stiffness = 400 })
			check.truthy(soft > hard) -- a soft spring lags further in the same time
		end)
		test.case(
			"the tilt is put on the body's side of an accessory's weld, whichever part the engine made Part0",
			function()
				-- a hat welded under the Head (Part0 = Head, Part1 = Handle): the body's side is C0
				check.equal(L.weldSide(false, true, true, false), "C0")
				-- the engine's AccessoryWeld under the Handle (Part0 = Handle, Part1 = Head): the body's side is C1
				check.equal(L.weldSide(true, false, false, true), "C1")
				-- a weld inside one accessory (handle to a decoration), two accessories welded together, two body parts:
				-- none hangs a handle on the body - not swayed (seen swayed twice before the one review, 2026-11-15)
				check.truthy(L.weldSide(true, false, false, false) == nil)
				check.truthy(L.weldSide(true, true, false, false) == nil)
				check.truthy(L.weldSide(false, false, true, true) == nil)
				check.truthy(L.weldSide(false, false, false, false) == nil)
			end
		)
		test.case("the runtime still carries the calls", function()
			local sec = fs.readFile("src/kit/AnimSecondary.luau")
			check.truthy(
				string.find(sec, "AnimLayers.sway(s.sx, s.sz, smoothed.X, smoothed.Z, step, s.spring)", 1, true) ~= nil
			)
			check.truthy(
				string.find(sec, "rx, rz = AnimLayers.swayLimit(rx, rz, s.class, s.hip, o.max, s.front)", 1, true)
					~= nil
			)
			check.truthy(string.find(sec, "local px, pz = AnimLayers.swayPush(a.X, a.Z)", 1, true) ~= nil)
			check.truthy(
				string.find(sec, "hip = if math.abs(middle.X) < 0.25 then 0 else math.sign(middle.X),", 1, true) ~= nil
			)
			check.truthy(string.find(sec, "front = middle.Z < -0.3,", 1, true) ~= nil)
			check.truthy(
				string.find(sec, "CFrame.new(s.base.Position) * CFrame.Angles(rx, 0, rz) * s.base.Rotation", 1, true)
					~= nil
			)
			check.truthy(string.find(sec, "local class = AnimLayers.swayClass(kind)", 1, true) ~= nil)
			check.truthy(string.find(sec, "if frame % every ~= 0 then", 1, true) ~= nil)
			check.truthy(string.find(sec, "rx, rz = AnimLayers.swayHang(rx, rz, s.hangs)", 1, true) ~= nil)
			check.truthy(
				string.find(sec, "local cam = if RunService:IsClient() then workspace.CurrentCamera else nil", 1, true)
					~= nil
			)
			check.truthy(string.find(sec, "task.defer(take, w)", 1, true) ~= nil)
			check.truthy(
				string.find(
					sec,
					"AnimLayers.weldSide(handleOf(w.Part0), handleOf(w.Part1), bodyPart(w.Part0), bodyPart(w.Part1))",
					1,
					true
				) ~= nil
			)
			check.truthy(string.find(sec, 'if s.side == "C0" then', 1, true) ~= nil)
			check.truthy(string.find(sec, "if character.Parent == nil or not rootPart.Parent then", 1, true) ~= nil)
			local client = fs.readFile("src/kit/client/AnimRoot.client.luau")
			check.truthy(string.find(client, 'kitFolder:GetAttribute("KitSecondary") == true', 1, true) ~= nil)
			check.truthy(string.find(client, "Secondary.attach(character, {", 1, true) ~= nil)
		end)
	end)
end

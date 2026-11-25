-- uicombat.spec.luau — the Combat Feedback Kit's rules (src/kit/UiCombat, LIMITATIONS_FIXES_V4 UI-X 13.6): waypoint
-- markers that never jump edges when the target swings behind the camera, a damage arc on the attacker's side (not
-- its mirror), at most three flashes a second (WCAG 2.3.1), the hit / crit / kill ladder, and compare tooltips.
local frk = require("../frk")
local test, check = frk.test, frk.check

local C = require("../../../src/kit/UiCombat")

local W, H = 1920, 1080
local FOCAL = (H / 2) / math.tan(math.rad(70) / 2) -- Roblox's default 70 degree vertical field of view
local MARGIN = 56

-- a target `dist` studs away at yaw `deg` (0 = ahead, 90 = right) and height `up` against a camera pitched down by
-- `pitch` degrees, in camera space (looking down -Z)
local function camSpace(deg: number, dist: number, up: number, pitch: number): (number, number, number)
	local a = math.rad(deg)
	local wx, wy, wz = math.sin(a) * dist, up, -math.cos(a) * dist
	local p = math.rad(pitch)
	-- rotate the world point into a camera pitched down by p (about +X)
	local y = wy * math.cos(p) - wz * math.sin(p)
	local z = wy * math.sin(p) + wz * math.cos(p)
	return wx, y, z
end

local function near(a: number, b: number, eps: number?): boolean
	return math.abs(a - b) <= (eps or 1e-6)
end

return function()
	test.suite("UiCombat: waypoint markers", function()
		test.case("a target in front and inside the margin box sits on its projection", function()
			local p = C.waypoint(0, 0, -20, W, H, FOCAL, MARGIN, "ellipse")
			check.is_true(p.onScreen)
			check.is_true(near(p.x, W / 2) and near(p.y, H / 2))
			local q = C.waypoint(2, 1, -20, W, H, FOCAL, MARGIN)
			check.is_true(q.onScreen)
			check.is_true(near(q.x, W / 2 + FOCAL * 2 / 20) and near(q.y, H / 2 - FOCAL * 1 / 20))
		end)
		test.case("off screen it pins onto the inset ellipse / rectangle, never outside the margin", function()
			for deg = 0, 359, 7 do
				for _, shape in { "ellipse", "rect" } do
					local lx, ly, lz = camSpace(deg, 50, -3, 15)
					local p = C.waypoint(lx, ly, lz, W, H, FOCAL, MARGIN, shape)
					check.is_true(p.x >= MARGIN - 1e-6 and p.x <= W - MARGIN + 1e-6)
					check.is_true(p.y >= MARGIN - 1e-6 and p.y <= H - MARGIN + 1e-6)
					if not p.onScreen and shape == "ellipse" then
						local ex, ey = (p.x - W / 2) / (W / 2 - MARGIN), (p.y - H / 2) / (H / 2 - MARGIN)
						check.is_true(near(ex * ex + ey * ey, 1, 1e-6))
					end
				end
			end
		end)
		test.case("turning a full circle, the marker never jumps across the screen (behind the camera too)", function()
			for _, up in { -6, 0, 4 } do
				local last: any = nil
				for step = 0, 720 do
					local deg = step * 0.5
					local lx, ly, lz = camSpace(deg, 40, up, 12)
					local p = C.waypoint(lx, ly, lz, W, H, FOCAL, MARGIN, "ellipse")
					if last then
						local jump = math.sqrt((p.x - last.x) ^ 2 + (p.y - last.y) ^ 2)
						-- half a degree of turn moves a pinned marker a few pixels; an edge flip moves it ~1000
						check.is_true(jump < 160)
					end
					last = p
				end
			end
		end)
		test.case("a target behind and below reads at the bottom; level with the camera plane stays finite", function()
			local lx, ly, lz = camSpace(180, 30, -4, 15)
			local p = C.waypoint(lx, ly, lz, W, H, FOCAL, MARGIN)
			check.is_true(p.behind)
			check.equal(p.edge, "bottom")
			check.is_true(p.y > H / 2)
			-- on the camera's own plane (lz = 0) the projection divides by zero: the marker still pins to the side
			local side = C.waypoint(10, 0, 0, W, H, FOCAL, MARGIN)
			check.is_false(side.onScreen)
			check.equal(side.edge, "right")
			check.is_true(near(side.x, W - MARGIN) and near(side.y, H / 2))
			local tiny = C.waypoint(3, 0.5, -1e-7, W, H, FOCAL, MARGIN)
			check.is_true(tiny.x == tiny.x and tiny.y == tiny.y and tiny.x <= W - MARGIN + 1e-6)
			-- straight behind: the bottom edge
			local back = C.waypoint(0, 0, 10, W, H, FOCAL, MARGIN)
			check.equal(back.edge, "bottom")
		end)
		test.case("the arrow points at the target: right = 90, down = 180, left = 270, up = 0", function()
			check.is_true(near(C.waypoint(10, 0, 0, W, H, FOCAL, MARGIN).angle, 90))
			check.is_true(near(C.waypoint(0, -10, 0, W, H, FOCAL, MARGIN).angle, 180))
			check.is_true(near(C.waypoint(-10, 0, 0, W, H, FOCAL, MARGIN).angle % 360, 270))
			check.is_true(near(C.waypoint(0, 10, 0, W, H, FOCAL, MARGIN).angle % 360, 0))
		end)
	end)

	test.suite("UiCombat: damage arcs", function()
		test.case("the attacker's bearing: ahead 0, right +90, left -90, behind 180 (a clockwise Rotation)", function()
			-- the camera at the origin looking down -Z (its right is +X)
			check.is_true(near(C.bearing(0, -10, 0, 0, 0, -1) :: number, 0))
			check.is_true(near(C.bearing(10, 0, 0, 0, 0, -1) :: number, 90))
			check.is_true(near(C.bearing(-10, 0, 0, 0, 0, -1) :: number, -90))
			check.is_true(near(math.abs(C.bearing(0, 10, 0, 0, 0, -1) :: number), 180))
			-- looking down +X, a hit from +Z is on the right
			check.is_true(near(C.bearing(0, 10, 0, 0, 1, 0) :: number, 90))
			check.equal(C.bearing(0, 0, 0, 0, 0, -1), nil)
		end)
	end)

	test.suite("UiCombat: three flashes a second (WCAG 2.3.1)", function()
		test.case("a fourth flash inside one second is refused; the window slides", function()
			local g = C.limiter()
			check.is_true(g:allow(0))
			check.is_true(g:allow(0.1))
			check.is_true(g:allow(0.2))
			check.is_false(g:allow(0.3))
			check.is_false(g:allow(0.99))
			check.is_true(g:allow(1.05))
		end)
		test.case("a 20 Hz hit stream never shows more than 3 flashes in any second", function()
			local g = C.limiter(3, 1)
			local shown: { number } = {}
			for i = 0, 199 do
				local t = i * 0.05
				if g:allow(t) then
					table.insert(shown, t)
				end
			end
			for i = 1, #shown do
				local n = 0
				for j = i, #shown do
					if shown[j] - shown[i] < 1 then
						n += 1
					end
				end
				check.is_true(n <= 3)
			end
			check.is_true(#shown >= 25) -- (it still confirms hits: about three a second over ten seconds)
		end)
	end)

	test.suite("UiCombat: the streak ladder", function()
		test.case("kills inside the window climb the rungs; a gap or a death starts again", function()
			local l = C.ladder({ rungs = { "Double", "Triple" }, killWindow = 4 })
			local e1 = l:record("kill", 0) :: any
			check.equal(e1.label, "Kill")
			check.is_true(e1.banner)
			check.equal((l:record("kill", 3) :: any).label, "Double")
			check.equal((l:record("kill", 6.5) :: any).label, "Triple")
			local e4 = l:record("kill", 9) :: any
			check.equal(e4.label, "Triple x4")
			check.equal(e4.rung, 2)
			check.equal((l:record("kill", 20) :: any).count, 1) -- (11 s later: a new chain)
			l:record("reset", 20.5)
			check.equal((l:record("kill", 21) :: any).count, 1)
		end)
		test.case("hits chain a combo, a banner on each milestone; a crit is always a banner", function()
			local l = C.ladder({ hitStep = 5, hitWindow = 1 })
			local banners = 0
			for i = 1, 10 do
				local e = l:record("hit", i * 0.5) :: any
				if e.banner then
					banners += 1
				end
			end
			check.equal(banners, 2)
			local c = l:record("crit", 5.2) :: any
			check.equal(c.count, 11)
			check.is_true(c.banner)
			check.equal(c.label, "Crit x11")
			check.equal((l:record("hit", 9) :: any).count, 1) -- (a gap over the window)
			check.equal(l:record("wave", 9), nil)
		end)
	end)

	test.suite("UiCombat: compare tooltips", function()
		test.case("the candidate against what is worn: signs, lower-is-better, units, missing stats", function()
			local rows = C.compare(
				{ ATK = 40, DEF = 12, Reload = 2.5 },
				{ ATK = 52, DEF = 9, Reload = 2.1, Crit = 5 },
				{ lowerBetter = { Reload = true }, units = { Reload = "s", Crit = "%" } }
			)
			local by: { [string]: any } = {}
			for _, r in rows do
				by[r.stat] = r
			end
			check.equal(by.ATK.text, "+12 ATK")
			check.equal(by.ATK.tone, "good")
			check.equal(by.DEF.text, "-3 DEF")
			check.equal(by.DEF.tone, "bad")
			check.equal(by.Reload.text, "-0.4s Reload")
			check.equal(by.Reload.tone, "good") -- (a shorter reload is better)
			check.equal(by.Crit.text, "+5% Crit")
			check.equal(rows[1].stat, "ATK") -- (by name when no order is given)
			local same = C.compare({ ATK = 1 }, { ATK = 1 })
			check.equal(same[1].tone, "same")
			check.equal(C.tipLines(rows), "good:+12 ATK\ngood:+5% Crit\nbad:-3 DEF\ngood:-0.4s Reload")
		end)
		test.case("a tip line's tone: an explicit prefix, else its sign", function()
			local t1, s1 = C.lineTone("good:-0.4s Reload")
			check.equal(t1, "good")
			check.equal(s1, "-0.4s Reload")
			check.equal((C.lineTone("+12 ATK")), "good")
			check.equal((C.lineTone("-3 DEF")), "bad")
			local t4, s4 = C.lineTone("Range: far")
			check.equal(t4, "same")
			check.equal(s4, "Range: far")
		end)
	end)
end

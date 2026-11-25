-- vfxvictim.spec.luau (kit) — F2 the victim's reaction and F1b the bounce's own burst (LIMITATIONS_FIXES_V4 §3.4 step
-- 3; src/kit/VfxVictim.luau, src/kit/VfxBounce.luau). What is proven: NO BLOOD - a blood-red spark colour is never
-- drawn (warm white instead), a white or a blue one is kept; the rim flash is solid on its first frame and fades; the
-- hitstop tremor alternates sides every frame, dies away and ends where it started; sparks fly along the cut's normal
-- (a zero or NaN normal: straight up); a bounce throws nothing under its landing speed, all its sparks at three times
-- it, and stops at the layer's max; the browser player's copy of the bounce rule gives THE SAME numbers (run in node);
-- the validator refuses a bad onBounce; and VfxImpact / VfxStage are read for their use of these rules.
local frk = require("../frk")
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")
local test, check = frk.test, frk.check

local VfxBounce = require("../../../src/kit/VfxBounce")
local VfxValidate3 = require("../../../src/kit/VfxValidate3")
local VfxVictim = require("../../../src/kit/VfxVictim")

local function code(path: string): string
	return (string.gsub(fs.readFile(path), "%s+", " "))
end

return function()
	test.suite("VfxVictim (F2)", function()
		test.case("no blood: a blood-red spark colour is never drawn", function()
			for _, red in { { 200, 10, 10 }, { 140, 0, 0 }, { 255, 40, 30 }, { 120, 30, 25 } } do
				local c, refused = VfxVictim.sparkColor(red)
				check.is_true(refused)
				check.equal(c[1], VfxVictim.SPARK[1])
				check.equal(c[2], VfxVictim.SPARK[2])
			end
			for _, ok in { { 255, 255, 255 }, { 120, 200, 255 }, { 255, 220, 120 }, { 255, 160, 60 } } do
				local c, refused = VfxVictim.sparkColor(ok)
				check.is_true(not refused)
				check.equal(c[1], ok[1])
			end
			local c = VfxVictim.sparkColor(nil)
			check.equal(c[3], VfxVictim.SPARK[3])
		end)

		test.case("the rim flash: solid on its first frame, then fading; harder hits last longer", function()
			local f = VfxVictim.flash(1)
			check.equal(f[1], 0)
			for i = 2, #f do
				check.is_true(f[i] > f[i - 1] - 1e-9)
			end
			check.is_true(#VfxVictim.flash(10) > #VfxVictim.flash(0))
		end)

		test.case("the tremor alternates sides every frame, dies away and ends where it started", function()
			local t = VfxVictim.tremor(8, 3)
			check.equal(#t, 8)
			for i = 1, 6 do
				check.is_true(t[i] * t[i + 1] < 0)
				check.is_true(math.abs(t[i + 1]) <= math.abs(t[i]) + 1e-9)
			end
			check.equal(t[8], 0)
			check.equal(#VfxVictim.tremor(0 / 0, 1), 0)
			check.is_true(math.abs(VfxVictim.tremor(6, 10)[1]) > math.abs(VfxVictim.tremor(6, 0)[1]))
		end)

		test.case("sparks: along the cut's normal, more for a harder hit, never past the cap", function()
			local d = VfxVictim.sparkDirection({ 0, 0, 5 })
			check.equal(d[3], 1)
			local up = VfxVictim.sparkDirection({ 0 / 0, 0, 0 })
			check.equal(up[2], 1)
			check.is_true(VfxVictim.sparkCount(8) > VfxVictim.sparkCount(1))
			check.is_true(VfxVictim.sparkCount(1e9) <= VfxVictim.MAX_SPARKS)
			check.equal(VfxVictim.power(0 / 0), 1)
		end)

		test.case("VfxImpact.onVictimHit uses these rules: a HERO slot, an Emit burst, the no-blood colour", function()
			local src = code("src/kit/VfxImpact.luau")
			check.is_true(string.find(src, "function VfxImpact.onVictimHit(", 1, true) ~= nil)
			check.is_true(string.find(src, "VfxVictim.sparkColor(", 1, true) ~= nil)
			check.is_true(string.find(src, "VfxVictim.tremor(", 1, true) ~= nil)
			check.is_true(string.find(src, "slots:claim(h, 2)", 1, true) ~= nil)
			check.is_true(string.find(src, "em:Emit(VfxVictim.sparkCount(p))", 1, true) ~= nil)
			check.is_true(string.find(src, "slots:release(h)", 1, true) ~= nil)
		end)
	end)

	test.suite("VfxBounce (F1b)", function()
		local spec = { count = 6, min = 5, max = 3 }
		test.case("a bounce throws nothing under its landing speed, all at three times it, stops at max", function()
			check.equal(VfxBounce.burst(spec, 4.9, 0), 0)
			check.equal(VfxBounce.burst(spec, 5, 0), 2) -- just over: a third of them
			check.equal(VfxBounce.burst(spec, 15, 0), 6)
			check.equal(VfxBounce.burst(spec, 500, 0), 6)
			check.equal(VfxBounce.burst(spec, 15, 3), 0) -- the layer's max used
			check.equal(VfxBounce.burst(spec, 0 / 0, 0), 0)
			check.equal(VfxBounce.burst({ count = 1, min = 0 }, 0, 0), 1)
		end)

		test.case("contact: the floor rule both players used, plus the landing speed", function()
			local hit, y, vy, land = VfxBounce.contact(-0.5, -10, 0, 0.4)
			check.is_true(hit)
			check.equal(y, 0)
			check.equal(vy, 4)
			check.equal(land, 10)
			local miss = VfxBounce.contact(0.5, -10, 0, 0.4)
			check.is_true(not miss)
		end)

		test.case("the browser player's copy of the rule gives the same numbers (node)", function()
			local js = fs.readFile("kit/vfx/player/player.js")
			local a = string.find(js, "function bounceBurst(", 1, true)
			check.is_true(a ~= nil)
			local b = string.find(js, "\nclass SwarmLayer", a, true)
			local fn = string.sub(js, a, b)
			local cases = {}
			for _, s in { spec, { count = 12, min = 0.5, max = 200 }, { count = 1 }, {} } do
				for _, land in { 0, 0.4, 1, 4.99, 5, 7.5, 12, 15, 40, 1000 } do
					for _, used in { 0, 2, 3, 24, 199 } do
						table.insert(cases, { s = s, land = land, used = used, want = VfxBounce.burst(s, land, used) })
					end
				end
			end
			local script = fn
				.. "\nconst cases = "
				.. serde.encode("json", cases)
				.. ";\nlet bad = 0; for (const c of cases) { const got = bounceBurst(c.s, c.land, c.used); if (got !== c.want) { bad++; console.log(JSON.stringify(c), got); } }\nconsole.log('MISMATCH ' + bad + ' of ' + cases.length);"
			fs.writeFile("build/vfxbounce_parity.js", script)
			local r = process.exec("node", { "build/vfxbounce_parity.js" })
			fs.removeFile("build/vfxbounce_parity.js")
			check.is_true(r.ok)
			check.is_true(string.find(r.stdout, "MISMATCH 0 of", 1, true) ~= nil)
		end)

		test.case("the validator refuses a bad onBounce and passes a good one", function()
			local function preset(ob: any): any
				return {
					version = 3,
					duration = 1,
					layers = {
						{
							kind = "swarm",
							name = "balls",
							count = 10,
							gravity = 30,
							floor = { y = 0, bounce = 0.4, onBounce = ob },
						},
					},
				}
			end
			local function errors(ob: any): { string }
				local out = {}
				for _, i in VfxValidate3.preset("t", preset(ob), {}) do
					if i.severity == "error" and string.find(i.path, "onBounce", 1, true) then
						table.insert(out, i.message)
					end
				end
				return out
			end
			check.equal(#errors({ count = 4, min = 6, max = 20, speed = { 4, 9 }, color = { 255, 230, 180 } }), 0)
			check.is_true(#errors({ count = 40 }) > 0)
			check.is_true(#errors({ speed = { 9, 4 } }) > 0)
			check.is_true(#errors({ colour = { 1, 2, 3 } }) > 0) -- a typo is never ignored
			check.is_true(#errors("sparks") > 0)
		end)

		test.case("VfxStage's swarm throws the burst through these rules (one emitter, Emit)", function()
			local src = code("src/kit/VfxStage.luau")
			check.is_true(string.find(src, "VfxBounce.contact(pos.Y, v.Y, fy, floor.bounce)", 1, true) ~= nil)
			check.is_true(string.find(src, "VfxBounce.burst(onBounce, land / scale, subUsed)", 1, true) ~= nil)
			check.is_true(string.find(src, "subEm:Emit(n)", 1, true) ~= nil)
		end)
	end)
end

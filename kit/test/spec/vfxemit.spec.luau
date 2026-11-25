-- vfxemit.spec.luau (kit) — the low-graphics guard (src/kit/VfxEmit.luau; LIMITATIONS_FIXES_V4 3.4 step 3: "Roblox
-- throttles continuous ParticleEmitter.Rate by 50-80% at QualityLevel <= 3, hero anime beats MUST trigger via explicit
-- Emit(N) bursts"). The rules run here; the last case reads VfxStage's own source for its use of them.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local VfxEmit = require("../../../src/kit/VfxEmit")

local function code(path: string): string
	local out = {}
	for line in string.gmatch(fs.readFile(path), "[^\n]+") do
		local cut = string.find(line, "--", 1, true)
		table.insert(out, if cut then string.sub(line, 1, cut - 1) else line)
	end
	return (string.gsub(table.concat(out, " "), "%s+", " "))
end

-- a rate thrown by the guard over `life` seconds at `fps` frames a second (the stage's updater: each frame pays the
-- time since the last, the fraction carried) -> how many particles
local function thrown(rate: number, life: number, fps: number): number
	local total, carry, paid = 0, 0, 0
	local t = 0
	while paid < life - 1e-9 do
		t += 1 / fps
		local upTo = math.min(t, life)
		local n
		n, carry = VfxEmit.step(rate, upTo - paid, carry)
		total += n
		paid = upTo
	end
	return total
end

return function()
	test.suite("VfxEmit", function()
		test.case("the guard is on at a low level and at Automatic; off at 4 and up; a forced answer wins", function()
			for level = 0, 3 do
				check.is_true(VfxEmit.guarded(level))
			end
			for level = 4, 10 do
				check.is_true(not VfxEmit.guarded(level))
			end
			check.is_true(not VfxEmit.guarded(1, false))
			check.is_true(VfxEmit.guarded(10, true))
		end)

		test.case("the graphics level from the setting: Automatic / nothing / junk read as 0", function()
			check.equal(VfxEmit.levelOf({ Value = 0 }), 0) -- Enum.SavedQualitySetting.Automatic
			check.equal(VfxEmit.levelOf({ Value = 3 }), 3)
			check.equal(VfxEmit.levelOf(7), 7)
			check.equal(VfxEmit.levelOf(nil), 0)
			check.equal(VfxEmit.levelOf("high"), 0)
			check.equal(VfxEmit.levelOf(0 / 0), 0)
			check.equal(VfxEmit.levelOf(42), 10)
		end)

		test.case("it throws what the Rate gives at full quality, at any frame rate (the fraction carried)", function()
			for _, fps in { 30, 60, 144, 240 } do
				for _, case in { { 26, 0.37 }, { 18, 0.7 }, { 3, 2.0 }, { 120, 0.05 } } do
					local want = case[1] * case[2]
					local got = thrown(case[1], case[2], fps)
					check.is_true(
						math.abs(got - want) <= 1,
						`{case[1]}/s over {case[2]} s at {fps} fps: {got}, wants {want}`
					)
				end
			end
		end)

		test.case(
			"a paused clock owes nothing; a hitch owes at most MAX_STEP's worth; nonsense owes nothing",
			function()
				local n, c = VfxEmit.step(30, 0, 0.4)
				check.equal(n, 0)
				check.equal(c, 0.4)
				n, c = VfxEmit.step(40, 3.0, 0) -- a 3 s hitch
				check.equal(n, math.floor(40 * VfxEmit.MAX_STEP))
				check.is_true(c >= 0 and c < 1)
				check.equal((VfxEmit.step(0 / 0, 0.1, 0)), 0)
				check.equal((VfxEmit.step(10, 0 / 0, 0)), 0)
				check.equal((VfxEmit.step(-5, 0.1, 0)), 0)
			end
		)

		test.case("VfxStage throws a sprite's rate itself under the guard (the Rate is set only without it)", function()
			local stage = code("src/kit/VfxStage.luau")
			local function has(s: string): boolean
				return string.find(stage, s, 1, true) ~= nil
			end
			check.is_true(has('local VfxEmit = require("./VfxEmit")'))
			check.is_true(has("local emitGuard = VfxEmit.guarded("))
			check.is_true(has("SavedQualityLevel"))
			check.is_true(has("if rate > 0 and emitGuard then"))
			check.is_true(has("n, carry = VfxEmit.step(rate, upTo - from, carry)"))
			check.is_true(has("main:Emit(n)"))
			-- the Rate path is the ELSE of the guard: the guard's branch never sets a Rate
			local guardAt = string.find(stage, "if rate > 0 and emitGuard then", 1, true) :: number
			local elseAt = string.find(stage, "elseif rate > 0 then", guardAt, true) :: number
			local rateAt = string.find(stage, "main.Rate = rate", guardAt, true) :: number
			check.is_true(elseAt ~= nil and rateAt ~= nil and rateAt > elseAt)
		end)
	end)
end

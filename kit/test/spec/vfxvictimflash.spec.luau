-- vfxvictimflash.spec.luau — the victim's rim flash draws its SOLID frame first, whatever hitch came before it
-- (src/kit/VfxImpact.onVictimHit, F2). Found in Studio 2026-11-20 by tests/playtest/vfx_sequence_victim: the flash
-- and the tremor step a 60 fps clock in RenderStepped, and counting the first callback's dt - the hit's own hitch (the
-- call, the burst, a first use that loads the stage) - skipped frame 1: the first flash drawn was 0.75 transparent.
-- (Its own file: it needs only src/kit, so `kit bug` can replant the fault against it.)
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local VfxVictim = require("../../../src/kit/VfxVictim")

local function code(path: string): string
	return (string.gsub(fs.readFile(path), "%s+", " "))
end

return function()
	test.suite("VfxImpact.onVictimHit's flash clock (F2)", function()
		test.case("the flash's first frame drawn is the solid one, whatever hitch came before it", function()
			-- (the flash and the tremor step on a 60 fps clock in RenderStepped; counting the first callback's dt - the
			-- hit's own hitch - skipped frame 1: the first flash Studio drew was 0.75 transparent, 2026-11-20)
			local src = code("src/kit/VfxImpact.luau")
			local at = string.find(src, "conn = RunService.RenderStepped:Connect(function(dt: number)", 1, true)
			check.is_true(at ~= nil)
			local body = string.sub(src, at or 1, (at or 1) + 900)
			check.is_true(string.find(body, "if drawn then acc += dt end drawn = true", 1, true) ~= nil)
			check.is_true(string.find(body, "Connect(function(dt: number) acc += dt", 1, true) == nil)
			-- the clock as written: a first callback 3 frames late still draws frame 1, then counts on
			local flash = VfxVictim.flash(1)
			local frame, acc, drawn, shown = 0, 0, false, {}
			for _, dt in { 0.05, 1 / 60, 1 / 60, 1 / 60 } do
				if drawn then
					acc += dt
				end
				drawn = true
				local f = math.floor(acc * 60 + 1e-6)
				if not (f == frame and frame > 0) then
					frame = math.max(f, 1)
					table.insert(shown, flash[frame] or 1)
				end
			end
			check.equal(shown[1], 0)
		end)
	end)
end

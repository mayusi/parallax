-- vfxlegacy.spec.luau (kit) — the four legacy preset keys are errors on a NEW piece (kit/lib/vfxlegacy.luau; the V3
-- doc, VFX stage A.1). The validator's warning for each becomes an error unless the preset was there on 2026-11-18
-- (kit/vfx/legacy_keys.json); errors, other warnings and the frozen presets are left as they are.
local frk = require("../frk")
local fs = require("@lune/fs")
local serde = require("@lune/serde")
local test, check = frk.test, frk.check

local VfxLegacy = require("../../lib/vfxlegacy")
local VfxValidate = require("../../../src/kit/VfxValidate")

local function warnOf(path: string): any
	return { severity = "warn", path = path, message = "m" }
end

return function()
	test.suite("VFX legacy keys (the V3 doc, A.1)", function()
		test.case("each of the four becomes an error on a piece that is not frozen", function()
			local frozen = { ["assets/effects/old"] = true }
			for _, key in VfxLegacy.KEYS do
				local issue = warnOf(`x.layers[2](a).{key}`)
				local refusal = VfxLegacy.refusal("assets/effects", "new", issue, frozen)
				check.is_true(
					refusal ~= nil and string.find(refusal :: string, "made after 2026-11-18", 1, true) ~= nil
				)
				check.is_true(VfxLegacy.refusal("assets/effects", "old", issue, frozen) == nil) -- frozen: still a warning
				-- the same name in ANOTHER folder (a game's) is another piece
				check.is_true(VfxLegacy.refusal("games/Duel/assets/effects", "old", issue, frozen) ~= nil)
			end
		end)

		test.case("other warnings, errors and look-alike paths are left alone", function()
			local none = {}
			check.is_true(VfxLegacy.refusal("d", "n", warnOf("x.layers[1].spread"), none) == nil)
			check.is_true(VfxLegacy.refusal("d", "n", warnOf("x.layers[1].fovPunch"), none) == nil)
			check.is_true(VfxLegacy.refusal("d", "n", warnOf("x.layers[1].erode"), none) == nil)
			-- (an orientation ERROR - an unknown value - is the validator's own, never re-worded here)
			check.is_true(
				VfxLegacy.refusal("d", "n", { severity = "error", path = "x.orientation", message = "m" }, none) == nil
			)
			check.is_true(VfxLegacy.refusal("d", "n", "not an issue", none) == nil)
		end)

		test.case("a missing or broken frozen list freezes nothing", function()
			check.is_true(next(VfxLegacy.frozen("kit/test/fixtures/no_such_legacy_keys.json")) == nil)
			local frozen = VfxLegacy.frozen()
			check.is_true(frozen["kit/starter/vfx/hellfire_impact"] == true) -- a starter of that day
			check.is_true(frozen["assets/effects/nuke_v4"] == true)
			check.is_true(frozen["kit/selftest/vfx/legacy/new_legacy"] == nil) -- the gate's own bad fixture is new
		end)

		test.case(
			"the validator still WARNS on each (the gate reads its warnings, it adds no rule of its own)",
			function()
				local preset = serde.decode("json", fs.readFile("kit/selftest/vfx/legacy/new_legacy.json"))
				local textures = serde.decode("json", fs.readFile("kit/selftest/vfx/legacy/_textures.json"))
				local seen = {}
				for _, issue in VfxValidate.preset("new_legacy", preset, textures, {}) do
					local key = VfxLegacy.key(issue.path)
					if key and issue.severity ~= "error" then
						seen[key] = true
					end
				end
				for _, key in VfxLegacy.KEYS do
					check.is_true(seen[key] == true)
				end
			end
		)
	end)
end

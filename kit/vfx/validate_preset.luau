--!strict
-- validate_preset.luau (kit) — the kit's own preset rules (src/kit/VfxValidate: what `kit vfx play` checks before it
-- plays anything) for preset FILES that are not in a project's effects folder. `kit vfx animatic` makes its blocking
-- preset in build/ and runs this on it before anything is recorded, and before a record is written over a recording
-- that is already there (--no-record never starts the player, so nothing else would check it).
--
--     lune run kit/vfx/validate_preset.luau <preset.json> [<preset.json> ...]
--
-- Prints one JSON line: { "<path>": ["<where in the preset>: <what is wrong>", ...], ... } - the validator's ERRORS
-- for each file, an empty list when the player takes it. A file that cannot be read as JSON is an error of its own.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local VfxValidate = require("../../src/kit/VfxValidate")

local out: { [string]: { string } } = {}
for _, path in process.args do
	local errors: { string } = {}
	local ok, preset = pcall(function(): any
		return serde.decode("json", fs.readFile(path))
	end)
	if not ok or type(preset) ~= "table" then
		table.insert(errors, "not a preset that can be read (JSON)")
	else
		for _, issue in VfxValidate.preset("preset", preset, {}, nil) do
			if issue.severity == "error" then
				table.insert(errors, `{issue.path}: {issue.message}`)
			end
		end
	end
	out[path] = errors
end
print(serde.encode("json", out))

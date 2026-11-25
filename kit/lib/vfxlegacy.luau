-- vfxlegacy.luau (kit) — the four legacy preset keys are ERRORS on a new piece (the V3 doc, VFX stage A.1).
--
-- src/kit/VfxValidate3.luau WARNS on four things a v3 preset carries that the stage and the player never play the way
-- the preset reads: a sprite's `spreadAngle` (the cone key is `spread`), a fov layer's `fov` (the stage reads
-- `delta`), a shake's `frequency` (a fixed rate) and a big camera-facing card standing on the ground (it tilts back).
-- Warnings, so the judged looks of the presets that carry them do not change by themselves. A piece made AFTER
-- 2026-11-18 has no such look to keep: the build turns those four warnings into errors for it. The presets of that
-- day are in kit/vfx/legacy_keys.json ("frozen", by the folder/name key the preset step sees); `kit vfx migrate`
-- (kit/vfx/legacy.py) fixes them, one named preset at a time.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local VfxLegacy = {}

VfxLegacy.KEYS = { "spreadAngle", "fov", "frequency", "orientation" }
VfxLegacy.FILE = "kit/vfx/legacy_keys.json"

-- the legacy key an issue path ends in ("layers[3].spreadAngle" -> "spreadAngle"), or nil
function VfxLegacy.key(path: string): string?
	for _, k in VfxLegacy.KEYS do
		if string.sub(path, -#k - 1) == "." .. k then
			return k
		end
	end
	return nil
end

-- the frozen folder/name keys; a missing or broken list freezes NOTHING (never a quiet way round the gate)
function VfxLegacy.frozen(file: string?): { [string]: boolean }
	local out: { [string]: boolean } = {}
	local path = file or VfxLegacy.FILE
	if not fs.isFile(path) then
		return out
	end
	local ok, data = pcall(serde.decode, "json" :: any, fs.readFile(path))
	if ok and type(data) == "table" and type(data.frozen) == "table" then
		for _, k in data.frozen :: { any } do
			if type(k) == "string" then
				out[k] = true
			end
		end
	end
	return out
end

-- an issue of the validator for the preset <dir>/<name> -> the error it becomes, or nil (it stays as it is)
function VfxLegacy.refusal(dir: string, name: string, issue: any, frozen: { [string]: boolean }): string?
	if type(issue) ~= "table" or issue.severity == "error" or type(issue.path) ~= "string" then
		return nil
	end
	local key = VfxLegacy.key(issue.path)
	if key == nil or frozen[`{dir}/{name}`] then
		return nil
	end
	return `{issue.message} - a piece made after 2026-11-18 may not carry it (fix it, or lune run kit vfx migrate {name} --apply)`
end

return VfxLegacy

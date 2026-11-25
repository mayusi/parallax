-- starters.luau (kit) — a kit starter as `kit init` seeded it into a project.
--
-- `kit init` copies the kit's starter effects (kit/starter/vfx) into a new project's effects folder. While a copy's
-- text is still one the kit shipped (line endings aside) it is the KIT's piece: made and judged where the kit is made,
-- and checked there by kit selftest. The making gates of the VFX presets step (scene breakdown, methods, stage locks,
-- the legacy keys as errors; the VFX vault in kit/vfx/vault.py) hold the pieces made in the project, and the first
-- edit of a starter makes it one. The validator's own errors (does it play) hold every preset, starters included.
--
-- What decides is the kit's RECORD (kit/vfx/starters.json: the sha256 of every text each starter shipped with), never
-- the project's kit/starter/ copy: that folder is not fingerprinted (promote and upgrades add to it), while the record
-- is kit-owned like the gates' own code (kit/lib/integrity.luau; the guard lets only a kit-lane session edit kit/) and
-- is written only in the kit's home (python kit/vfx/starters.py --write; `kit promote vfx` runs it).
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Starters = {}

Starters.RECORD = "kit/vfx/starters.json"

export type Record = { [string]: { [string]: boolean } }

local function lf(s: string): string
	return (string.gsub(s, "\r\n", "\n"))
end

-- the sha256 of a text as the record keeps it (line endings read as LF)
function Starters.sha(text: string): string
	return serde.hash("sha256", lf(text))
end

-- the record as { ["effect/<name>"] = { [sha256] = true } }; a missing or broken record knows nothing (never a quiet
-- way round a gate)
function Starters.load(path: string?): Record
	local out: Record = {}
	local ok, data = pcall(function()
		return serde.decode("json", fs.readFile(path or Starters.RECORD))
	end)
	if not ok or type(data) ~= "table" or type(data.pieces) ~= "table" then
		return out
	end
	for key, shas in data.pieces :: { [any]: any } do
		if type(key) == "string" and type(shas) == "table" then
			local base = string.match(key, "^([^#]+)") or key
			local set = out[base] or {}
			for _, s in shas do
				if type(s) == "string" then
					set[s] = true
				end
			end
			out[base] = set
		end
	end
	return out
end

-- is <dir>/<file> (a preset) still the text of the kit's starter effect of that name? `record`: Starters.load()'s
-- table (read once per run; default: the kit's record). Only a plain file name is looked up.
function Starters.untouchedVfx(dir: string, file: string, record: Record?): boolean
	if string.find(file, "[/\\]") or string.sub(file, -5) ~= ".json" then
		return false
	end
	local path = `{dir}/{file}`
	if not fs.isFile(path) then
		return false
	end
	local shas = (record or Starters.load())["effect/" .. string.sub(file, 1, -6)]
	return shas ~= nil and shas[Starters.sha(fs.readFile(path))] == true
end

return Starters

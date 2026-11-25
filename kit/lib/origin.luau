-- origin.luau — what put a project's kit files there last, and so where an edited one is restored from:
--   "release"  kit/UPSTREAM.json without source = "clone": only `upgrade` writes one (every install and update from
--              a clone records source = "clone"), so the files are that GitHub release's - `upgrade --force --tag
--              <installed_tag>` puts them back, whatever kit/HOME still names (source = "file": a release file,
--              `upgrade --from <it>`)
--   "home"     otherwise, kit/HOME names a kit home that is there: `kit sync` (an update from that home)
--   "clone"    a kit from a clone whose kit/HOME is gone or points nowhere (a 3.0.0 kit keeps no record: a kit/HOME
--              that points nowhere says the same): `update <project>` from a clone of the kit - never the release
--              route, which may not hold the clone's files
--   "none"     no kit/HOME and no readable record: the kit's own home
-- `kit sync` asks first whether there is a home to update from at all (Origin.home); an update never takes a project
-- back to an older kit (Origin.laterVersion, kit/cmd/setup.luau).
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Origin = {}

local function prefix(base: string?): string
	return if base and base ~= "" then base .. "/" else ""
end

-- the kit home kit/HOME names when that home is there, else "" (base: the project root; default = here)
function Origin.home(base: string?): string
	local file = prefix(base) .. "kit/HOME"
	if fs.isFile(file) then
		local h = string.gsub(string.gsub(fs.readFile(file), "%s+$", ""), "/+$", "")
		if h ~= "" and fs.isDir(h .. "/kit") then
			return h
		end
	end
	return ""
end

-- kit/UPSTREAM.json, or nil when it is missing or unreadable
function Origin.record(base: string?): { [string]: any }?
	local ok, data = pcall(function()
		return serde.decode("json", fs.readFile(prefix(base) .. "kit/UPSTREAM.json"))
	end)
	return if ok and type(data) == "table" then data else nil
end

function Origin.of(base: string?): string
	local record = Origin.record(base)
	if record and record.source ~= "clone" then
		return "release"
	end
	if Origin.home(base) ~= "" then
		return "home"
	end
	if record or fs.isFile(prefix(base) .. "kit/HOME") then
		return "clone"
	end
	return "none"
end

-- is release tag `a` ("v3.1.0") a later version than `b`? (major.minor.patch, numerically - v10 is after v9; a tag
-- either side that cannot be read as one = no)
function Origin.laterVersion(a: string, b: string): boolean
	local a1, a2, a3 = string.match(a, "^v?(%d+)%.(%d+)%.(%d+)")
	local b1, b2, b3 = string.match(b, "^v?(%d+)%.(%d+)%.(%d+)")
	if not (a1 and b1) then
		return false
	end
	local x = { tonumber(a1) :: number, tonumber(a2) :: number, tonumber(a3) :: number }
	local y = { tonumber(b1) :: number, tonumber(b2) :: number, tonumber(b3) :: number }
	for i = 1, 3 do
		if x[i] ~= y[i] then
			return x[i] > y[i]
		end
	end
	return false
end

return Origin

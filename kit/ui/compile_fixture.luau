-- compile_fixture.luau — run UI.compile on a single spec file + an identities folder;
-- print one JSON line (status / summary / next_action) and exit non-zero on errors.
-- Used by the qa.luau selftest to exercise compile-level checks without touching Config.path("ui").
--
--   lune run kit/ui/compile_fixture <path/to/Spec.json> --identities <path/to/identities>
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local UI = require("../lib/ui")

local args = process.args
local specPath: string? = nil
local identitiesDir: string? = nil
local i = 1
while i <= #args do
	if args[i] == "--identities" and args[i + 1] then
		identitiesDir = args[i + 1]
		i += 2
	elseif not specPath then
		specPath = args[i]
		i += 1
	else
		i += 1
	end
end

if not specPath or not fs.isFile(specPath) then
	print(serde.encode("json", {
		schema = 1,
		status = "fail",
		summary = `no spec file: {tostring(specPath)}`,
		next_action = "pass a path to a .json screen spec",
	}))
	process.exit(1)
end

local ok, spec = pcall(serde.decode, "json" :: any, fs.readFile(specPath :: string))
if not ok or type(spec) ~= "table" then
	print(serde.encode("json", {
		schema = 1,
		status = "fail",
		summary = `cannot parse {tostring(specPath)}: {tostring(spec)}`,
		next_action = "fix the JSON",
	}))
	process.exit(1)
end

local identities: { [string]: any } = {}
if identitiesDir and fs.isDir(identitiesDir :: string) then
	for _, f in fs.readDir(identitiesDir :: string) do
		if string.sub(f, -5) == ".json" then
			local ok2, id = pcall(serde.decode, "json" :: any, fs.readFile(`{identitiesDir}/{f}`))
			if ok2 and type(id) == "table" and type(id.name) == "string" then
				identities[id.name] = id
			end
		end
	end
end

local _, issues = UI.compile(spec, nil, nil, identities)
local errors, warns = {}, {}
for _, issue in issues do
	if issue.severity == "error" then
		table.insert(errors, `[{issue.path}] {issue.message}`)
	else
		table.insert(warns, `[{issue.path}] {issue.message}`)
	end
end

if #errors > 0 then
	print(serde.encode("json", {
		schema = 1,
		status = "fail",
		summary = table.concat(errors, " | "),
		next_action = "fix the compile errors above",
	}))
	process.exit(1)
end

print(serde.encode("json", {
	schema = 1,
	status = "pass",
	summary = `{spec.name or "?"}: compiled ({#warns} warn(s))`,
	next_action = "look at the preview",
}))
process.exit(0)

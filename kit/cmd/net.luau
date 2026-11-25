-- net.luau — `kit net`: network schemas (assets/net/<System>.net.json) -> generated, validated remotes
-- (src/net/<System>Net.luau = ReplicatedStorage.Net.<System>Net). Pure generator + rules: kit/lib/net.luau.
-- `kit net --check` (run by kit verify) fails when a generated file is missing or drifted from its schema.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Config = require("../lib/config")
local NetLib = require("../lib/net")
local Run = require("../lib/run")

local NetCmd = {}

local function dirs(): (string, string)
	return Config.path("net"), Config.path("netOut")
end

-- compile every schema; write = true writes src/net, false only compares (drift)
function NetCmd.step(write: boolean, schemaDir: string?, outDir: string?): Run.Step
	local inDir, defaultOut = dirs()
	inDir = schemaDir or inDir
	local out = outDir or defaultOut
	if not fs.isDir(inDir) then
		return Run.step("net", true, "", { summary = `no schemas ({inDir}/ is empty): nothing to generate` })
	end
	local problems, made, drift = {}, {}, {}
	for _, file in fs.readDir(inDir) do
		if string.sub(file, -9) ~= ".net.json" then
			continue
		end
		local path = `{inDir}/{file}`
		local ok, schema = pcall(serde.decode, "json" :: any, fs.readFile(path))
		if not ok then
			table.insert(problems, `{path}: invalid JSON`)
			continue
		end
		local src, issues = NetLib.compile(schema, path)
		for _, i in issues do
			table.insert(problems, `{path}: {i.path}: {i.message}`)
		end
		if src then
			local target = `{out}/{schema.system}Net.luau`
			if write then
				Config.ensureDir(out)
				fs.writeFile(target, src)
			elseif not fs.isFile(target) or (string.gsub(fs.readFile(target), "\r\n", "\n")) ~= src then
				table.insert(drift, target)
			end
			table.insert(made, target)
		end
	end
	if #problems > 0 then
		return Run.step("net", false, table.concat(problems, "\n"), {
			status = "fail",
			summary = `{#problems} schema problem(s): {table.concat(problems, " | ")}`,
			next_action = `fix {problems[1]}`,
		})
	end
	if #drift > 0 then
		return Run.step("net", false, table.concat(drift, "\n"), {
			status = "fail",
			summary = `{#drift} generated file(s) out of date: {table.concat(drift, ", ")}`,
			next_action = `{drift[1]} is stale or edited by hand — run: lune run kit net`,
		})
	end
	return Run.step("net", true, table.concat(made, "\n"), {
		summary = `{#made} schema(s) -> {out}/` .. (if write then " (written)" else " (up to date)"),
		next_action = if #made > 0
			then `use it: local Net = require(ReplicatedStorage.Net.<System>Net); Net.<Remote>.on / .fire`
			else nil,
	})
end

function NetCmd.register(Cli: any)
	Cli.command(
		"code",
		"net",
		"net [--check]",
		"network schemas assets/net/<System>.net.json -> generated remotes src/net/<System>Net.luau: every client argument rate-limited + Guard-checked before your handler",
		function(rawArgs)
			local check = table.find(rawArgs, "--check") ~= nil
			local step = NetCmd.step(not check)
			local r = step.result or {}
			return Run.report(
				"net",
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
				`net: {r.summary or step.tail}`,
				r.next_action or "none — proceed"
			)
		end
	)
end

return NetCmd

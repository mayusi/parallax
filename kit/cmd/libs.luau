-- libs.luau — `kit add <name>`: install a VETTED library from kit/catalog.json (pinned versions only).
-- wally packages: pinned line in wally.toml -> wally install -> scan the downloaded source for backdoor patterns
-- (any hit: the install is undone) -> Rojo mappings for Packages/ServerPackages. rokit tools: pinned line in
-- rokit.toml -> rokit install. Anything not in the catalog must be vetted first (kit-vet skill + VETLOG.md).
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Config = require("../lib/config")
local Run = require("../lib/run")

local C = Run.CODES
local Libs = {}

local RED_FLAGS = {
	{ "require%s*%(%s*%d+", "require(<asset id>) loads code from the internet at runtime" },
	{ "loadstring%s*%(", "loadstring runs strings as code" },
	{ "getfenv%s*%(", "getfenv/setfenv tamper with environments (obfuscation sign)" },
	{ "setfenv%s*%(", "getfenv/setfenv tamper with environments (obfuscation sign)" },
}

function Libs.catalog(): { [string]: any }
	local path = "kit/catalog.json"
	return if fs.isFile(path) then serde.decode("json", fs.readFile(path)) else {}
end

-- every .lua/.luau file under dir -> list of "file: reason"
function Libs.scan(dir: string): { string }
	local hits = {}
	local function walk(d: string)
		for _, name in fs.readDir(d) do
			local p = `{d}/{name}`
			if fs.isDir(p) then
				walk(p)
			elseif string.match(name, "%.luau?$") then
				local text = fs.readFile(p)
				for _, flag in RED_FLAGS do
					if string.find(text, flag[1]) then
						table.insert(hits, `{p}: {flag[2]}`)
					end
				end
			end
		end
	end
	if fs.isDir(dir) then
		walk(dir)
	end
	return hits
end

-- insert `line` under [section] in a TOML file (creates the section when missing); false if the key exists
local function tomlAdd(path: string, section: string, key: string, line: string): boolean
	local text = if fs.isFile(path) then fs.readFile(path) else ""
	for existing in string.gmatch(text, "[^\n]+") do
		if string.match(existing, "^%s*" .. key .. "%s*=") then
			return false
		end
	end
	local header = `[{section}]`
	local s, e = string.find(text, header, 1, true)
	if s then
		text = string.sub(text, 1, e) .. "\n" .. line .. string.sub(text, e + 1)
	else
		text = string.gsub(text, "%s*$", "") .. `\n\n{header}\n{line}\n`
	end
	fs.writeFile(path, text)
	return true
end

local function ensureRojoPackages(changed: { string })
	local path = Config.load().rojo
	if not fs.isFile(path) then
		return
	end
	local project = serde.decode("json", fs.readFile(path))
	local tree = project.tree
	local touched = false
	if fs.isDir("Packages") then
		tree.ReplicatedStorage = tree.ReplicatedStorage or { ["$className"] = "ReplicatedStorage" }
		if not tree.ReplicatedStorage.Packages then
			tree.ReplicatedStorage.Packages = { ["$path"] = "Packages" }
			touched = true
		end
	end
	if fs.isDir("ServerPackages") then
		tree.ServerScriptService = tree.ServerScriptService or { ["$className"] = "ServerScriptService" }
		if not tree.ServerScriptService.ServerPackages then
			tree.ServerScriptService.ServerPackages = { ["$path"] = "ServerPackages" }
			touched = true
		end
	end
	if touched then
		fs.writeFile(path, serde.encode("json", project, true) .. "\n")
		table.insert(changed, path)
	end
end

function Libs.register(Cli: any)
	Cli.command(
		"code",
		"add",
		"add [name]",
		"install a vetted library (pinned) — no name lists the catalog",
		function(args)
			local catalog = Libs.catalog()
			local name = args[1]
			if not name then
				local names = {}
				for k, v in catalog do
					if type(v) == "table" then
						table.insert(names, k)
					end
				end
				table.sort(names)
				for _, k in names do
					local v = catalog[k]
					print(`  {k} ({v.wally or v.rokit}, {v.license}) — {v.about}`)
				end
				return Run.report(
					"add",
					{},
					C.PASS,
					`add: {#names} vetted libraries`,
					"lune run kit add <name>   (anything else: vet it first — kit-vet skill, VETLOG.md)"
				)
			end
			local entry = catalog[name]
			if type(entry) ~= "table" then
				return Run.report(
					"add",
					{},
					C.USAGE,
					`add: "{name}" is not in the vetted catalog`,
					"vet it first (kit-vet skill: two sources, license, maintainer, source read, VETLOG.md row), then add it to kit/catalog.json"
				)
			end
			local changed = {}
			if entry.rokit then
				local added = tomlAdd("rokit.toml", "tools", entry.alias, `{entry.alias} = "{entry.rokit}"`)
				-- trust exactly this vetted author/tool (never a blanket --no-trust-check), then install
				local tool = string.match(entry.rokit, "^([^@]+)")
				Run.spawn("rokit trust", Run.tool("rokit"), { "trust", tool }, true)
				local step = Run.spawn("rokit install", Run.tool("rokit"), { "install" }, true)
				if not step.ok then
					return Run.report(
						"add",
						{ step },
						C.TOOLCHAIN,
						`add: rokit install failed for {name}`,
						"run: rokit install"
					)
				end
				return Run.report(
					"add",
					{ step },
					C.PASS,
					`add: {name} {if added then "installed" else "already listed"} ({entry.rokit})`,
					"use it:\n" .. entry.usage
				)
			end
			local section = if entry.realm == "server" then "server-dependencies" else "dependencies"
			local before = fs.readFile("wally.toml")
			local added = tomlAdd("wally.toml", section, entry.alias, `{entry.alias} = "{entry.wally}"`)
			local step = Run.spawn("wally install", Run.tool("wally"), { "install" }, true)
			if not step.ok then
				fs.writeFile("wally.toml", before)
				return Run.report(
					"add",
					{ step },
					C.TOOLCHAIN,
					`add: wally install failed for {name} (wally.toml restored)`,
					"check your network, then retry"
				)
			end
			-- the downloaded source must be clean, every time (a pinned version can't change, but trust nothing)
			local scope, pkg = string.match(entry.wally, "^([^/]+)/([^@]+)@(.+)$")
			local hits = {}
			for _, root in { "Packages/_Index", "ServerPackages/_Index" } do
				if fs.isDir(root) then
					for _, dir in fs.readDir(root) do
						if scope and string.find(string.lower(dir), string.lower(`{scope}_{pkg}`), 1, true) then
							for _, h in Libs.scan(`{root}/{dir}`) do
								table.insert(hits, h)
							end
						end
					end
				end
			end
			if #hits > 0 then
				fs.writeFile("wally.toml", before)
				Run.spawn("wally install", Run.tool("wally"), { "install" }, true)
				return Run.report(
					"add",
					{ step },
					C.CONTENT,
					`add: {name} REJECTED — {#hits} red flag(s): {hits[1]}`,
					"do not use this package; report it. wally.toml restored and packages reinstalled without it"
				)
			end
			ensureRojoPackages(changed)
			return Run.report(
				"add",
				{ step },
				C.PASS,
				`add: {name} {if added then "installed" else "already listed"} ({entry.wally}), source scan clean{if #changed
						> 0
					then ", Rojo mapping added"
					else ""}`,
				"use it:\n"
					.. entry.usage
					.. "\n(rojo serve running? restart it: wally rebuilt Packages/, which stops Rojo's live sync)"
			)
		end
	)
end

return Libs

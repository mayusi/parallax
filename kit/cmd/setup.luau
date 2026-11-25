-- setup.luau — make ANY Roblox project kit-ready (init), connect an AI client to the kit's MCP server (connect), keep
-- the git hooks and connected clients in step (harness), install/update the kit into other projects, check the
-- toolchain, and record uploaded asset ids.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local AssetIds = require("../lib/assetids")
local Board = require("../lib/board")
local Config = require("../lib/config")
local Harness = require("../lib/harness")
local Integrity = require("../lib/integrity")
local Library = require("../lib/library")
local Origin = require("../lib/origin")
local Run = require("../lib/run")
local VaultMerge = require("../lib/vaultmerge")

local C = Run.CODES

local TOOLS = {
	rojo = "rojo-rbx/rojo@7.7.1",
	wally = "UpliftGames/wally@0.3.2",
	selene = "Kampfkarren/selene@0.32.0",
	stylua = "JohnnyMorganz/stylua@2.5.2",
	lune = "lune-org/lune@0.10.5",
	["luau-lsp"] = "JohnnyMorganz/luau-lsp@1.70.1",
}
local GITIGNORE = {
	"build/",
	".verify/",
	"sourcemap.json",
	"DevPackages/",
	"Packages/",
	"ServerPackages/",
	"*.rbxl",
	"*.rbxlx",
	"__pycache__/",
	"_scratch/",
}
local BRIEF = [[# Project brief

<!-- Every model reads the first lines of this file in `kit status`. Keep it short and current. -->

**Game:** (one sentence — what is it, who is it for)
**Pillars:** (3 words that every feature must serve)
**Current milestone:** (what "done" looks like for the next playable build)
**Out of scope for now:** (what NOT to build yet)
]]

-- never copied into another project: a private asset's graded render stays on the machine (and project) it was made in
-- (kit/.source marks THE KIT'S OWN REPO: a project that got it would skip its own project checks)
local NEVER_COPIED = { "kit/anchors/private", "kit/.source" }
-- the grading record (kit/cmd/learn.luau canonical()): a project linked to a kit home holds a SNAPSHOT of the home's,
-- refreshed by every install / update; a project that graded on its own (no kit home, or a home elsewhere) holds its
-- own record, which the update replaces - so a copy of each of its own files that differs is kept first (below)
local GRADING_FILES = { "kit/grades.json", "kit/pairs.json", "kit/weights.json", "kit/anchors/anchors.json" }

local function copyTree(src: string, dst: string, overwrite: boolean, changed: { string })
	local norm = string.gsub(src, "\\", "/")
	for _, private in NEVER_COPIED do
		if norm == private then
			return
		end
	end
	if fs.isDir(src) then
		Config.ensureDir(dst)
		for _, name in fs.readDir(src) do
			copyTree(src .. "/" .. name, dst .. "/" .. name, overwrite, changed)
		end
	elseif overwrite and string.find(norm, VaultMerge.PREFIX, 1, true) then
		-- the knowledge vault: the project's own record is never wiped by an update (kit/lib/vaultmerge.luau)
		local at = string.find(norm, VaultMerge.PREFIX, 1, true) :: number
		if VaultMerge.copy(src, dst, string.sub(norm, at + #VaultMerge.PREFIX)) then
			table.insert(changed, dst)
		end
	elseif overwrite or not fs.isFile(dst) then
		local data = fs.readFile(src)
		if not fs.isFile(dst) or fs.readFile(dst) ~= data then
			fs.writeFile(dst, data)
			table.insert(changed, dst)
		end
	end
end

local function isEmptyDir(path: string): boolean
	if not fs.isDir(path) then
		return true
	end
	for _, name in fs.readDir(path) do
		if name ~= ".gitkeep" then
			return false
		end
	end
	return true
end

local function ensureLines(path: string, lines: { string }, header: string, changed: { string })
	local cur = if fs.isFile(path) then fs.readFile(path) else ""
	local missing = {}
	for _, l in lines do
		local found = false
		for existing in string.gmatch(cur, "[^\r\n]+") do
			if existing == l then
				found = true
				break
			end
		end
		if not found then
			table.insert(missing, l)
		end
	end
	if #missing > 0 then
		local sep = if cur == "" or string.sub(cur, -1) == "\n" then "" else "\n"
		fs.writeFile(path, cur .. sep .. header .. "\n" .. table.concat(missing, "\n") .. "\n")
		table.insert(changed, path)
	end
end

local function patchRojo(changed: { string }, notes: { string })
	local cfg = Config.load()
	local path = cfg.rojo
	if not fs.isFile(path) then
		-- empty folder: start from the standard layout (the kit mappings are added just below)
		local P = cfg.paths
		local fresh = {
			name = cfg.name,
			tree = {
				["$className"] = "DataModel",
				ReplicatedStorage = { ["$className"] = "ReplicatedStorage", Shared = { ["$path"] = P.shared } },
				ServerScriptService = { ["$className"] = "ServerScriptService", ["$path"] = P.server },
				StarterPlayer = {
					["$className"] = "StarterPlayer",
					StarterPlayerScripts = { ["$className"] = "StarterPlayerScripts", ["$path"] = P.client },
				},
				Workspace = { ["$className"] = "Workspace" },
			},
		}
		fs.writeFile(path, serde.encode("json", fresh, true) .. "\n")
		table.insert(changed, path)
		local main = P.server .. "/Main.server.luau"
		if not fs.isFile(main) then
			Config.ensureDir(P.server)
			fs.writeFile(
				main,
				'-- Main.server.luau — server entrypoint. Add systems with: lune run kit new system <Name>\nprint("[Server] online")\n'
			)
			table.insert(changed, main)
		end
	end
	local proj = serde.decode("json", fs.readFile(path))
	local tree = proj.tree
	local dirty = false
	local function node(parent: any, name: string, className: string?): any
		if parent[name] == nil then
			parent[name] = if className then { ["$className"] = className } else {}
			dirty = true
		end
		return parent[name]
	end
	local rs = node(tree, "ReplicatedStorage", "ReplicatedStorage")
	if not rs.kit then
		rs.kit = { ["$path"] = "src/kit" }
		dirty = true
	end
	if not rs.VfxPresets then
		rs.VfxPresets = { ["$path"] = cfg.paths.vfx }
		dirty = true
	end
	if not rs.KitAnimations then
		rs.KitAnimations = { ["$path"] = cfg.paths.animOut }
		dirty = true
	end
	if not rs.KitModels then
		rs.KitModels = { ["$path"] = cfg.paths.modelOut }
		dirty = true
	end
	if not fs.isDir(cfg.paths.modelOut) then
		-- Rojo refuses a mapping to a missing folder; .gitkeep keeps it in fresh clones (Rojo ignores the file)
		Config.ensureDir(cfg.paths.modelOut)
		fs.writeFile(cfg.paths.modelOut .. "/.gitkeep", "")
		table.insert(changed, cfg.paths.modelOut .. "/")
	end
	if not rs.AssetIds then
		rs.AssetIds = { ["$path"] = "assets/ids.json" }
		dirty = true
	end
	-- sound events for ReplicatedStorage.kit.Sfx (Rojo refuses a mapping to a missing file: start an empty one)
	local events = cfg.paths.sounds .. "/_events.json"
	if not fs.isFile(events) then
		Config.ensureDir(cfg.paths.sounds)
		fs.writeFile(events, '{\n "maxVoices": 32,\n "buses": {},\n "snapshots": {},\n "events": {}\n}\n')
		table.insert(changed, events)
	end
	if not rs.SfxEvents then
		rs.SfxEvents = { ["$path"] = events }
		dirty = true
	end
	-- generated remotes (kit net: assets/net/*.net.json -> src/net) as ReplicatedStorage.Net
	if not fs.isDir("src/net") then
		Config.ensureDir("src/net")
		fs.writeFile("src/net/.gitkeep", "")
		table.insert(changed, "src/net/")
	end
	if not rs.Net then
		rs.Net = { ["$path"] = "src/net" }
		dirty = true
	end
	-- movesets (kit move: assets/moves -> src/moves) as ReplicatedStorage.KitMoves
	if not fs.isDir("src/moves") then
		Config.ensureDir("src/moves")
		fs.writeFile("src/moves/.gitkeep", "")
		table.insert(changed, "src/moves/")
	end
	if not rs.KitMoves then
		rs.KitMoves = { ["$path"] = "src/moves" }
		dirty = true
	end
	local ws = node(tree, "Workspace", "Workspace")
	if not ws.KitWorld then
		ws.KitWorld = { ["$path"] = cfg.paths.worldOut }
		dirty = true
	end
	local sp = node(tree, "StarterPlayer", "StarterPlayer")
	local sps = node(sp, "StarterPlayerScripts", "StarterPlayerScripts")
	if not sps.KitClient then
		sps.KitClient = { ["$path"] = "src/kit/client" }
		dirty = true
	end
	-- kit server scripts (world environment: terrain + lighting)
	local sss = node(tree, "ServerScriptService", "ServerScriptService")
	if not sss.KitServer then
		sss.KitServer = { ["$path"] = "src/kit/server" }
		dirty = true
	end
	-- Future lighting (the world presets are tuned for it; scripts may not be allowed to set Technology)
	local lighting = node(tree, "Lighting", "Lighting")
	lighting["$properties"] = lighting["$properties"] or {}
	if lighting["$properties"].Technology == nil then
		lighting["$properties"].Technology = "Future"
		dirty = true
	end
	local sg = node(tree, "StarterGui", "StarterGui")
	if sg["$path"] == nil and sg.KitScreens == nil then
		sg["$path"] = cfg.paths.uiOut
		dirty = true
	elseif sg["$path"] ~= cfg.paths.uiOut and sg.KitScreens == nil then
		sg.KitScreens = { ["$path"] = cfg.paths.uiOut }
		dirty = true
		table.insert(notes, `StarterGui already mapped — kit screens go under StarterGui.KitScreens`)
	end
	if dirty then
		fs.writeFile(path, serde.encode("json", proj, true) .. "\n")
		table.insert(changed, path)
	end
end

local function init(args: { string }): number
	local _, flags = Run.parseFlags(args)
	local changed, notes = {}, {}
	-- 1. config
	if not fs.isFile(Config.FILE) then
		local name = flags.name or string.match(process.cwd, "([^/\\]+)[/\\]?$") or "RobloxGame"
		local cfg = { name = name, rojo = Config.DEFAULTS.rojo, paths = Config.DEFAULTS.paths, qa = Config.DEFAULTS.qa }
		fs.writeFile(Config.FILE, serde.encode("json", cfg, true) .. "\n")
		table.insert(changed, Config.FILE)
	end
	local P = Config.load().paths
	-- 2. folders
	for _, key in
		{
			"models",
			"sounds",
			"textures",
			"vfx",
			"ui",
			"uiOut",
			"worlds",
			"worldOut",
			"anims",
			"animOut",
			"modelOut",
			"tests",
			"playtests",
			"shared",
			"server",
			"client",
		}
	do
		if not fs.isDir(P[key]) then
			Config.ensureDir(P[key])
			table.insert(changed, P[key] .. "/")
		end
	end
	for _, sub in { "tasks", "handoffs", "decisions", "journal" } do
		local d = Board.dir(sub)
		if not fs.isDir(d) then
			Config.ensureDir(d)
			fs.writeFile(d .. "/.gitkeep", "")
			table.insert(changed, d .. "/")
		end
	end
	if not fs.isFile(Board.dir("BRIEF.md")) then
		fs.writeFile(Board.dir("BRIEF.md"), BRIEF)
		table.insert(changed, Board.dir("BRIEF.md"))
	end
	-- 3. starter libraries (only into EMPTY folders — never mixes with your content)
	local seededVfx = false
	if not flags["no-starter"] then
		for key, starter in
			{
				sounds = "kit/starter/sounds",
				textures = "kit/starter/textures",
				vfx = "kit/starter/vfx",
				models = "kit/starter/models",
			}
		do
			if isEmptyDir(P[key]) then
				if key == "vfx" then -- the examples, not their packed dependencies (unpacked below, into their homes)
					Config.ensureDir(P.vfx)
					for _, f in fs.readDir(starter) do
						if f ~= "_deps" then
							copyTree(starter .. "/" .. f, P.vfx .. "/" .. f, false, changed)
						end
					end
					seededVfx = true
				else
					copyTree(starter, P[key], false, changed)
				end
			end
		end
	end
	if not fs.isFile("assets/ids.json") then
		Config.ensureDir("assets")
		fs.writeFile("assets/ids.json", '{\n  "sounds": {},\n  "models": {},\n  "textures": {},\n  "images": {}\n}\n')
		table.insert(changed, "assets/ids.json")
	end
	if not fs.isFile(P.vfx .. "/_textures.json") then
		copyTree("kit/starter/vfx/_textures.json", P.vfx .. "/_textures.json", false, changed)
	end
	-- the seeded effect examples bring their parts / textures / uploaded ids (after the base textures are in)
	if seededVfx and fs.isDir("kit/starter/vfx/_deps") then
		for _, ex in fs.readDir("kit/starter/vfx/_deps") do
			for _, w in Library.installVfx("kit/starter", ex, { vfx = P.vfx, textures = P.textures }) do
				table.insert(changed, w)
			end
		end
	end
	-- 4. Rojo mappings for the kit runtime, presets and generated screens
	patchRojo(changed, notes)
	-- 5. toolchain + lint config
	local rokit = if fs.isFile("rokit.toml") then fs.readFile("rokit.toml") else "[tools]\n"
	-- parse existing keys line by line (plain compare: "-" in "luau-lsp" is a pattern operator)
	local present = {}
	for line in string.gmatch(rokit, "[^\r\n]+") do
		local key = string.match(line, '^%s*"?([%w_%-]+)"?%s*=')
		if key then
			present[key] = true
		end
	end
	local addTools = {}
	for tool, spec in TOOLS do
		if not present[tool] then
			table.insert(addTools, (if string.find(tool, "-") then `"{tool}"` else tool) .. ` = "{spec}"`)
		end
	end
	if #addTools > 0 then
		table.sort(addTools)
		fs.writeFile("rokit.toml", string.gsub(rokit, "%s*$", "") .. "\n" .. table.concat(addTools, "\n") .. "\n")
		table.insert(changed, "rokit.toml")
	end
	if not fs.isFile("wally.toml") then
		local pkg = string.lower(string.gsub(Config.load().name, "[^%w]", ""))
		fs.writeFile(
			"wally.toml",
			`[package]\nname = "local/{pkg}"\nversion = "0.1.0"\nregistry = "https://github.com/UpliftGames/wally-index"\nrealm = "shared"\nprivate = true\n\n[dependencies]\n\n[server-dependencies]\n\n[dev-dependencies]\nFrktest = "itsfrank/frktest@0.0.2"\n`
		)
		table.insert(changed, "wally.toml")
	elseif not string.find(fs.readFile("wally.toml"), "frktest", 1, true) then
		table.insert(
			notes,
			'add to wally.toml [dev-dependencies]: Frktest = "itsfrank/frktest@0.0.2", then: wally install'
		)
	end
	local luaurc = if fs.isFile(".luaurc")
		then serde.decode("json", fs.readFile(".luaurc"))
		else { languageMode = "strict" }
	luaurc.aliases = luaurc.aliases or {}
	if luaurc.aliases.kit ~= "./kit" then
		luaurc.aliases.kit = "./kit"
		fs.writeFile(".luaurc", serde.encode("json", luaurc, true) .. "\n")
		table.insert(changed, ".luaurc")
	end
	if not fs.isFile("selene.toml") then
		fs.writeFile(
			"selene.toml",
			'std = "roblox"\nexclude = ["DevPackages/**", "Packages/**", "ServerPackages/**", "build/**", "kit/types/**", "_scratch/**", ".claude/**"]\n'
		)
		table.insert(changed, "selene.toml")
	else
		-- generated playtest bundles live in build/: never lint them
		local selene = fs.readFile("selene.toml")
		-- the downloaded Roblox definitions are declarations, not code: never lint them either
		if not string.find(selene, "_scratch/**", 1, true) then
			selene = string.gsub(selene, "exclude%s*=%s*%[", 'exclude = ["_scratch/**", ', 1)
			fs.writeFile("selene.toml", selene)
			table.insert(changed, "selene.toml")
		end
		-- an agent harness's git worktrees (.claude/worktrees/*) are whole copies of the project: never lint them
		if not string.find(selene, ".claude/**", 1, true) then
			selene = string.gsub(selene, "exclude%s*=%s*%[", 'exclude = [".claude/**", ', 1)
			fs.writeFile("selene.toml", selene)
			table.insert(changed, "selene.toml")
		end
		if not string.find(selene, "kit/types/**", 1, true) then
			selene = string.gsub(selene, "exclude%s*=%s*%[", 'exclude = ["kit/types/**", ', 1)
			fs.writeFile("selene.toml", selene)
			table.insert(changed, "selene.toml")
		end
		if not string.find(selene, "build/**", 1, true) then
			local patched, n = string.gsub(selene, "exclude%s*=%s*%[", 'exclude = ["build/**", ', 1)
			if n == 0 then
				patched = string.gsub(selene, "%s*$", "") .. '\nexclude = ["build/**"]\n'
			end
			fs.writeFile("selene.toml", patched)
			table.insert(changed, "selene.toml")
		end
	end
	if not fs.isFile("stylua.toml") then
		fs.writeFile(
			"stylua.toml",
			'syntax = "Luau"\ncolumn_width = 120\nline_endings = "Unix"\nindent_type = "Tabs"\nindent_width = 4\nquote_style = "AutoPreferDouble"\ncall_parentheses = "Always"\n\n[sort_requires]\nenabled = true\n'
		)
		table.insert(changed, "stylua.toml")
	end
	ensureLines(
		".styluaignore",
		{ "DevPackages/", "Packages/", "ServerPackages/", "build/", "kit/types/", "_scratch/" },
		"# kit",
		changed
	)
	ensureLines(".gitignore", GITIGNORE, "# kit (generated)", changed)
	-- 6. the git hooks + the connected AI clients (what an older kit wrote for every client is removed)
	local hChanged, hNotes = Harness.sync()
	for _, c in hChanged do
		table.insert(changed, c)
	end
	for _, n in hNotes do
		table.insert(notes, n)
	end
	Board.journal(
		Board.agent(flags.as),
		"kit init" .. (if #changed > 0 then ` ({#changed} change(s))` else " (no changes)")
	)
	for _, c in changed do
		print("  + " .. c)
	end
	for _, n in notes do
		print("  ! " .. n)
	end
	local needInstall = not fs.isDir("DevPackages")
	local connectHint = if #Harness.connected() == 0
		then "; connect your AI client: lune run parallax connect <client>"
		else ""
	return Run.report(
		"init",
		{},
		C.PASS,
		`init: {#changed} change(s)` .. (if #notes > 0 then `, {#notes} note(s)` else ""),
		if needInstall
			then "run: rokit install; wally install; then: lune run kit doctor" .. connectHint
			else "run: lune run kit doctor, then fill board/BRIEF.md and lune run kit status" .. connectHint
	)
end

return function(Cli: any, _Steps: any)
	Run.parseFlags = Cli.parse

	Cli.command(
		"start",
		"init",
		"init [--name Game] [--no-starter]",
		"make THIS project kit-ready (idempotent: only adds what's missing)",
		init
	)

	Cli.command(
		"kit",
		"harness",
		"harness [--check]",
		"keep the git hooks (lane fence, commit gate) and every CONNECTED AI client's MCP config + guard hooks in step, and remove what older kits wrote for every client (instruction files, rule files, skill copies); --check changes nothing and fails when any is out of step",
		function(rawArgs)
			if table.find(rawArgs or {}, "--check") then
				local stale = Harness.check()
				for _, c in stale do
					print("  ~ " .. c)
				end
				return Run.report(
					"harness",
					{},
					if #stale == 0 then C.PASS else C.CONTENT,
					if #stale == 0
						then "harness --check: the git hooks and every connected client's config are in step"
						else `harness --check: {#stale} managed file(s) out of step or legacy left behind`,
					if #stale == 0 then "none - proceed" else "lune run parallax harness (then commit what it wrote)"
				)
			end
			local changed, notes = Harness.sync()
			for _, c in changed do
				print("  + " .. c)
			end
			for _, n in notes do
				print("  ! " .. n)
			end
			return Run.report(
				"harness",
				{},
				C.PASS,
				`harness: {#changed} file(s) updated`,
				if #Harness.connected() == 0
					then "connect your AI client: lune run parallax connect <client>"
					else "none - proceed (commit a connected client's config only if your team should share it)"
			)
		end
	)

	Cli.command(
		"start",
		"connect",
		"connect [<client>[,<client>...]] [--remove]",
		"connect an AI client to the kit's MCP server: claude, cursor, vscode, gemini, roo or opencode get their project config (+ the guard's hooks where the client runs hooks); codex, windsurf, cline and claude-desktop print the block for their global config; no client = the list and what is connected; --remove takes the kit's entry out again",
		function(rawArgs)
			local pos, flags = Cli.parse(rawArgs)
			-- (`--remove claude` reads "claude" as the flag's value: it is a client name all the same)
			local remove = flags.remove ~= nil
			if type(flags.remove) == "string" then
				table.insert(pos, 1, flags.remove)
			end
			flags.remove = remove
			local wanted = {}
			for _, a in pos do
				for name in string.gmatch(string.lower(a), "[^,%s]+") do
					table.insert(wanted, name)
				end
			end
			if #wanted == 0 then
				local connected = Harness.connected()
				for _, name in Harness.CLIENT_ORDER do
					local c = Harness.CLIENTS[name]
					local where = c.file or `global: {c.global}`
					local mark = if table.find(connected, name) then "connected" else "-"
					print(string.format("  %-15s %-38s %-10s %s", name, c.label, mark, where))
				end
				return Run.report(
					"connect",
					{},
					C.PASS,
					`connect: {#connected} client(s) connected`
						.. (if #connected > 0 then ` ({table.concat(connected, ", ")})` else ""),
					"lune run parallax connect <client>   (e.g. claude; several: claude,cursor)"
				)
			end
			for _, name in wanted do
				if not Harness.CLIENTS[name] then
					return Run.report(
						"connect",
						{},
						C.USAGE,
						`connect: unknown client {name}`,
						`one of: {table.concat(Harness.CLIENT_ORDER, ", ")}`
					)
				end
			end
			local written, printed = {}, {}
			for _, name in wanted do
				local c = Harness.CLIENTS[name]
				if c.global then
					print(
						if flags.remove
							then `  {c.label}: remove this block from {c.global} (the kit never writes that file)`
							else `  {c.label}: add this to {c.global}`
					)
					print("")
					for line in string.gmatch(Harness.globalSnippet(name), "[^\n]+") do
						print("    " .. line)
					end
					print("")
					table.insert(printed, name)
				else
					local changed, problem
					if flags.remove then
						changed = Harness.disconnect(name)
					else
						changed, problem = Harness.connect(name)
					end
					if problem then
						return Run.report(
							"connect",
							{},
							C.USAGE,
							`connect {name}: {problem}`,
							"fix it, then run the same command"
						)
					end
					for _, p in changed do
						print("  " .. (if flags.remove then "- " else "+ ") .. p)
						table.insert(written, p)
					end
					if #changed == 0 then
						print(`  = {c.label}: {if flags.remove then "not connected" else "already connected, in step"}`)
					end
				end
			end
			Board.journal(
				Board.agent(flags.as),
				`kit connect {table.concat(wanted, ",")}{if flags.remove then " --remove" else ""} ({#written} file(s))`
			)
			return Run.report(
				"connect",
				{},
				C.PASS,
				if flags.remove
					then `connect --remove: {#written} file(s) changed`
					else `connect: {#written} file(s) written` .. (if #printed > 0
						then `; {#printed} global block(s) printed to paste`
						else ""),
				if flags.remove
					then "none - proceed"
					else "restart the client in this folder (approve the parallax server if it asks), then call parallax_start with your lane and the request"
			)
		end
	)

	Cli.command(
		"start",
		"doctor",
		"doctor",
		"check every tool the pipeline uses (and what each missing one blocks), and the HARDWARE TIER this machine reaches (0 zero-GPU core .. 4 full 3D generation) with what the next tier needs; only a Tier 0 gap fails",
		function()
			-- TIER 0 (the release blueprint's Part III: any PC, no GPU): the only tools whose absence fails doctor
			local checks: { { any } } = {
				{ "rojo", { "--version" }, "build + Studio sync" },
				{ "lune", { "--version" }, "the kit itself" },
				{ "selene", { "--version" }, "lint gate" },
				{ "stylua", { "--version" }, "format gate" },
				{ "wally", { "--version" }, "packages (frktest for tests)" },
				{ "luau-lsp", { "--version" }, "type gate" },
				{
					"python",
					{
						"-c",
						"import numpy, scipy, PIL, matplotlib, pytest; print('numpy+scipy+pillow+matplotlib+pytest ok')",
					},
					"the kit's Python tools and tests (pip install numpy scipy pillow matplotlib pytest)",
				},
				{ "ffmpeg", { "-hide_banner", "-version" }, "sfx OGG encode + audio gate" },
				{ "node", { "--version" }, "the VFX player's checks (selftest)" },
			}
			local steps, missing = {}, {}
			for _, c in checks do
				local tool = tostring(c[1])
				local step = Run.spawn(tool, Run.tool(tool), c[2] :: { string })
				table.insert(steps, step)
				if not step.ok then
					table.insert(missing, `{tool} ({c[3]})`)
				end
			end
			-- the departments' own tools: one row each — present / missing — and what a missing one BLOCKS, so a
			-- session reads at arrival which stages of its route it cannot run (a missing one never fails doctor
			-- by itself: it is a department gap, listed under its department in the summary)
			local python = Run.tool("python")
			local function pyMod(mod: string): { string }
				return { "-c", `import {mod}` }
			end
			local function fileCheck(path: string): { string }
				return { "-c", `import os, sys; sys.exit(0 if os.path.exists(r'{path}') else 1)` }
			end
			local home = process.env.USERPROFILE or process.env.HOME or ""
			local departments: { { any } } = {
				{
					"3d",
					"blender",
					Run.tool("blender"),
					{ "-b", "--factory-startup", "--version" },
					"every build, render, fit, judge",
				},
				{
					"3d",
					"cad env (build123d)",
					Run.tool("cad"),
					pyMod("build123d"),
					"kit cad check (`kit tools setup cad`)",
				},
				{
					"3d",
					"mitsuba env",
					Run.tool("mitsuba"),
					pyMod("mitsuba"),
					"differentiable fits (`kit tools setup mitsuba`)",
				},
				{
					"3d",
					"trellis2 env",
					Run.tool("trellis2"),
					pyMod("torch"),
					"kit gen / gen parts / gen views (kit/gen/README.md)",
				},
				{
					"3d",
					"vision weights",
					python,
					fileCheck(`{home}/.cache/roblox-kit/models/sam2.1-hiera-small`),
					"kit trace / vision cutout (kit vision setup)",
				},
				{ "3d", "torch (vision)", python, pyMod("torch"), "kit trace, refs find, vision (pip torch)" },
				{
					"vfx",
					"blender",
					Run.tool("blender"),
					{ "-b", "--factory-startup", "--version" },
					"fx textures, mesh shells, impact plates",
				},
				{
					"vfx",
					"numpy + scipy + pillow",
					python,
					pyMod("numpy, scipy, PIL"),
					"vfx validator, previews, calibrate",
				},
				{
					"vfx",
					"ffmpeg",
					Run.tool("ffmpeg"),
					{ "-hide_banner", "-version" },
					"breakdown frames, play --record",
				},
				{
					"sfx",
					"ffmpeg",
					Run.tool("ffmpeg"),
					{ "-hide_banner", "-version" },
					"OGG encode, the audio gate, sfx av",
				},
				{
					"sfx",
					"numpy + scipy + matplotlib",
					python,
					pyMod("numpy, scipy, matplotlib"),
					"kit sfx synth, sheet, match",
				},
				{ "ui", "pillow + numpy", python, pyMod("PIL, numpy"), "kit ui previews, render, judge" },
				{ "ui", "vtracer", python, pyMod("vtracer"), "kit vision vectorize (`kit tools setup kit-python`)" },
				{
					"ui",
					"blender",
					Run.tool("blender"),
					{ "-b", "--factory-startup", "--version" },
					"kit ui render (3D plates, chrome, glass)",
				},
				{
					"world",
					"blender",
					Run.tool("blender"),
					{ "-b", "--factory-startup", "--version" },
					"kit world look / terrain",
				},
				{ "world", "numpy + pillow", python, pyMod("numpy, PIL"), "world check images, heightmaps" },
				{
					"anim",
					"blender",
					Run.tool("blender"),
					{ "-b", "--factory-startup", "--version" },
					"kit anim (bakes off the owner's rig)",
				},
				{ "anim", "numpy + torch", python, pyMod("numpy, torch"), "kit anim fit / pose space / motion model" },
				{
					"anim",
					"user R6 IK rig (optional: PARALLAX_R6_RIG or assets/rigs/R6_IK.blend)",
					python,
					fileCheck(process.env.PARALLAX_R6_RIG or "assets/rigs/R6_IK.blend"),
					"every R6 bake + look",
				},
				{
					"code",
					"rojo + wally + selene + stylua + luau-lsp",
					"",
					{},
					"build, packages, lint, format, types (above)",
				},
				{
					"qa",
					-- (Roblox Studio and its MCP server ship for Windows and macOS only: on Linux the row says so)
					if process.os == "linux"
						then "Studio MCP bridge (unavailable: Studio runs on Windows / macOS)"
						else "Studio MCP bridge",
					python,
					fileCheck(
						if process.os == "macos"
							then "/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP"
							else `{process.env.LOCALAPPDATA or ""}/Roblox/mcp.bat`
					),
					"playtests, booth captures, uploads (needs Studio open)",
				},
			}
			local deptRows, deptMissing = {}, {}
			local have: { [string]: boolean } = {} -- (by label: the tier below reads them, nothing runs twice)
			for _, d in departments do
				local dept, label, blocks = tostring(d[1]), tostring(d[2]), tostring(d[5])
				local program, argv = d[3] :: string, d[4] :: { string }
				local ok = true
				if program ~= "" then
					if have[label] ~= nil then
						ok = have[label]
					else
						local s = Run.spawn(`{dept}: {label}`, program, argv, true)
						ok = s.ok
					end
				end
				have[label] = ok
				table.insert(
					deptRows,
					string.format("  %-6s %-36s %-8s %s", dept, label, if ok then "ok" else "MISSING", blocks)
				)
				if not ok then
					deptMissing[dept] = (deptMissing[dept] or 0) + 1
				end
			end
			print("  departments (tool · present · what a missing one blocks):")
			for _, r in deptRows do
				print(r)
			end
			local deptSummary = {}
			for _, dept in { "3d", "vfx", "sfx", "ui", "world", "anim", "qa" } do
				if deptMissing[dept] then
					table.insert(deptSummary, `{dept} ({deptMissing[dept]} missing)`)
				end
			end
			if #deptSummary > 0 then
				print(
					"  ! departments with gaps: "
						.. table.concat(deptSummary, ", ")
						.. " — their blocked stages are listed above"
				)
			end
			-- THE HARDWARE TIER this machine reaches: each tier needs every one below it; a missing higher tier never
			-- fails doctor - it is what that tier would unlock, said with the command that adds it
			local function visionTier(tier: string): boolean
				local s = Run.spawn(
					`vision tier {tier}`,
					python,
					{ "kit/vision/setup.py", "--check", "--quick", "--tier", tier },
					true
				)
				return s.ok
			end
			local gpuMiB = 0
			local gpu =
				Run.spawn("gpu", "nvidia-smi", { "--query-gpu=memory.total", "--format=csv,noheader,nounits" }, true)
			if gpu.ok then
				for n in string.gmatch(gpu.tail or "", "(%d+)") do
					gpuMiB = math.max(gpuMiB, tonumber(n) or 0)
				end
			end
			-- (tier N is TIER_NAMES[N + 1]: tiers count from 0)
			local TIER_NAMES = {
				"zero-GPU core",
				"DCC & CAD",
				"lightweight vision core",
				"local VLM & diffusion",
				"full 3D generation",
			}
			local tierNeeds = {
				{
					{ have["blender"] == true, "Blender 5.2 (blender.org; or set BLENDER to blender.exe)" },
					{ have["vtracer"] == true, "lune run parallax tools setup kit-python" },
					{ have["cad env (build123d)"] == true, "lune run parallax tools setup cad" },
					{ have["mitsuba env"] == true, "lune run parallax tools setup mitsuba" },
				},
				{ { visionTier("core"), "lune run parallax vision setup   (the core models, ~2.4 GB)" } },
				{
					{
						gpuMiB >= 12000,
						`an NVIDIA GPU with 12 GB (found {if gpuMiB > 0 then `{gpuMiB} MiB` else "none"})`,
					},
					{ visionTier("vision"), "lune run parallax vision setup --tier vision   (~44.6 GB more)" },
				},
				{
					{ visionTier("gen"), "lune run parallax vision setup --tier gen   (~24.5 GB more)" },
					{ have["trellis2 env"] == true, "the 3D generators' environment (kit/gen/README.md)" },
				},
			}
			local tier, nextNeeds = 0, {}
			for i, needs in tierNeeds do
				local short = {}
				for _, n in needs do
					if not n[1] then
						table.insert(short, n[2])
					end
				end
				if #short > 0 then
					nextNeeds = short
					break
				end
				tier = i
			end
			print(`  machine tier: {tier} ({TIER_NAMES[tier + 1]})`)
			if tier < 4 then
				print(`  next: Tier {tier + 1} ({TIER_NAMES[tier + 2]}) needs: {table.concat(nextNeeds, "; ")}`)
			end
			-- the engine this project targets (docs/ENGINES.md): only one with emitters can build anything
			local engine, engineWhy = Config.engine()
			print(`  engine: {engine or "(none)"}`)
			local extra = {}
			if not engine then
				table.insert(missing, engineWhy :: string)
			end
			if not fs.isDir("DevPackages/_Index") then
				table.insert(missing, "DevPackages (run: wally install)")
			end
			if not fs.isFile("kit/types/globalTypes.d.luau") then
				table.insert(
					extra,
					"type gate is SKIPPED: no kit/types/globalTypes.d.luau. To enable: vet + download the Roblox definitions published by luau-lsp (github.com/JohnnyMorganz/luau-lsp), record it in VETLOG.md, save as kit/types/globalTypes.d.luau."
				)
			end
			for _, e in extra do
				print("  ! " .. e)
			end
			if #missing > 0 then
				return Run.report(
					"doctor",
					steps,
					C.TOOLCHAIN,
					"doctor: missing " .. table.concat(missing, ", "),
					"install them (rokit install / wally install / pip / winget) — vet first, record in VETLOG.md"
				)
			end
			return Run.report(
				"doctor",
				steps,
				C.PASS,
				`doctor: Tier 0 toolchain present; machine tier {tier} ({TIER_NAMES[tier + 1]})`
					.. (if #extra > 0 then " (type gate skipped)" else ""),
				if tier < 4
					then `lune run kit status   (Tier {tier + 1} needs: {nextNeeds[1]})`
					else "lune run kit status"
			)
		end
	)

	Cli.command(
		"kit",
		"install",
		"install <path-to-project> [--update]",
		"copy the kit into another project, then run its init",
		function(args)
			local pos, flags = Cli.parse(args)
			-- (a switch that took the path as its value - `--force ../MyGame` - gives it back)
			for _, switch in { "update", "force" } do
				if type(flags[switch]) == "string" then
					table.insert(pos, 1, flags[switch])
					flags[switch] = true
				end
			end
			local target = pos[1]
			if not target then
				return Run.report(
					"install",
					{},
					C.USAGE,
					"install: which folder?",
					"lune run kit install ../MyGame   (created if missing; an existing Rojo project is fine)"
				)
			end
			if not fs.isDir(target) then
				if flags.update then
					return Run.report("install", {}, C.USAGE, `update: {target} does not exist`, "check the path")
				end
				fs.writeDir(target)
			end
			-- a kit HOME (its own kit, no kit/HOME pointing elsewhere) is never installed over: its grades, weights, anchors
			-- and lessons are every project's — install goes from the home INTO projects, never back
			-- (a kit source repo - kit/.source - is a home whatever else it has; a project installed from a GitHub release
			-- carries kit/UPSTREAM.json instead of kit/HOME and may be updated)
			local isHome = fs.isFile(target .. "/kit/.source")
				or (not fs.isFile(target .. "/kit/HOME") and not fs.isFile(target .. "/kit/UPSTREAM.json"))
			if fs.isFile(target .. "/kit/init.luau") and isHome then
				return Run.report(
					"install",
					{},
					C.USAGE,
					`install: {target} is a kit HOME (it has its own kit and no kit/HOME) — a home is never installed over`,
					"install from the home into a project: (in the home) lune run kit install <project> --update"
				)
			end
			-- an install never quietly takes a project BACK: one that holds a later kit than this one (upgraded to a newer
			-- release, or updated from a newer clone) is refused unless --force - this older copy would replace it
			if not flags.force then
				local theirs = Origin.record(target)
				local ours = if fs.isFile("kit/VERSION")
					then "v" .. string.gsub(fs.readFile("kit/VERSION"), "%s+", "")
					else ""
				if
					theirs
					and type(theirs.installed_tag) == "string"
					and Origin.laterVersion(theirs.installed_tag, ours)
				then
					return Run.report(
						"install",
						{},
						C.USAGE,
						`install: {target} holds Parallax {theirs.installed_tag}, later than this kit ({ours}) — this would take it back`,
						`git pull the kit it updates from ({process.cwd}) and run it again; or in the project: lune run parallax upgrade (the GitHub release); to install this older kit anyway, run it again with --force`
					)
				end
			end
			local changed = {}
			-- a project that graded on its own (no kit home here, or one elsewhere: its kit/HOME is not this folder) holds
			-- its own grading record, and the copy below gives it this home's: each of its own files that differs is
			-- kept first in board/grading-kept-<UTC time>/ - never lost (a project linked to this home holds a
			-- snapshot of it, refreshed as before)
			do
				local here = string.lower(string.gsub(string.gsub(process.cwd, "\\", "/"), "/+$", ""))
				local theirs = if fs.isFile(target .. "/kit/HOME")
					then string.lower(
						string.gsub(
							string.gsub(string.gsub(fs.readFile(target .. "/kit/HOME"), "%s+$", ""), "\\", "/"),
							"/+$",
							""
						)
					)
					else ""
				if theirs ~= here then
					local stamp = os.date("!%Y%m%d-%H%M%SZ")
					-- (the record's files, and every anchor picture the home's copy would write over: a graded render
					-- the project made under a name the home also has)
					local toKeep = table.clone(GRADING_FILES)
					if fs.isDir(target .. "/kit/anchors") then
						for _, f in fs.readDir(target .. "/kit/anchors") do
							local rel = "kit/anchors/" .. f
							if
								rel ~= "kit/anchors/anchors.json"
								and fs.isFile(target .. "/" .. rel)
								and fs.isFile(rel)
							then
								table.insert(toKeep, rel)
							end
						end
					end
					for _, rel in toKeep do
						local own = target .. "/" .. rel
						if fs.isFile(own) and (not fs.isFile(rel) or fs.readFile(own) ~= fs.readFile(rel)) then
							local keep = `{target}/board/grading-kept-{stamp}/{rel}`
							Config.ensureDir(string.match(keep, "^(.*)/[^/]+$") :: string)
							fs.writeFile(keep, fs.readFile(own))
							print(`[kept] this project's own {rel} -> board/grading-kept-{stamp}/{rel}`)
						end
					end
				end
			end
			-- kit-owned: replaced wholesale (local definitions file kept)
			copyTree("kit", target .. "/kit", true, changed)
			copyTree("src/kit", target .. "/src/kit", true, changed)
			-- the brand entry point (`lune run parallax <command>`, which the README and every harness file name): kit-owned
			-- (kit/lib/integrity.luau ROOTS), so an update refreshes it like kit/
			if fs.isFile("parallax.luau") then
				copyTree("parallax.luau", target .. "/parallax.luau", true, changed)
			end
			-- remember the home: `kit lesson` / `kit promote` there write back here, `kit sync` pulls from here
			local home = string.gsub(string.gsub(process.cwd, "\\", "/"), "/+$", "")
			fs.writeFile(target .. "/kit/HOME", home .. "\n")
			-- UPSTREAM.json says where this kit came from - here: a local clone (its VERSION, its commit) - and lets
			-- `kit upgrade` work from GitHub later. Written on EVERY install / update: a project first installed from a
			-- release and since updated from a clone holds the clone's files, and a record still naming the release
			-- would send a restore to that older release (a downgrade). `upgrade` writes the release's own record. The
			-- kit's own repo never gets one (it is refused as a target above, and kit/.source is never copied).
			do
				local okOld, old = pcall(function()
					return serde.decode("json", fs.readFile(target .. "/kit/UPSTREAM.json"))
				end)
				local prev = if okOld and type(old) == "table" then old else {}
				local kitVersion = if fs.isFile("kit/VERSION")
					then string.gsub(fs.readFile("kit/VERSION"), "%s+", "")
					else "0.0.0"
				-- (from a clone: the kit may be ahead of the release its VERSION names - `upgrade --check` says so)
				local okHead, head = pcall(process.exec, "git", { "rev-parse", "HEAD" })
				local upstreamData = {
					schema = 1,
					repo = if type(prev.repo) == "string" then prev.repo else "mayusi/parallax",
					channel = if type(prev.channel) == "string" then prev.channel else "stable",
					installed_tag = "v" .. kitVersion,
					installed_sha256 = "",
					updated_at = os.date("!%Y-%m-%dT%H:%M:%SZ"),
					source = "clone",
					source_commit = if okHead and head.ok then string.gsub(head.stdout, "%s+", "") else "",
				}
				fs.writeFile(target .. "/kit/UPSTREAM.json", serde.encode("json", upstreamData, true) .. "\n")
			end
			-- fingerprint exactly the kit files this install / update copied in (the home's own, never a file the
			-- project added under kit/): `kit status` there flags any later edit, and an upgrade removes only these
			local shipped: { string } = {}
			for rel in Integrity.scan() do
				table.insert(shipped, rel)
			end
			Integrity.writeOnly(target, shipped)
			local initArgs = { "run", "kit", "init" }
			if flags.update then
				table.insert(initArgs, "--no-starter")
			end
			local ok, r = pcall(process.exec, Run.tool("lune"), initArgs, { cwd = target })
			if not ok or not r.ok then
				return Run.report(
					"install",
					{},
					C.TOOLCHAIN,
					"install: copied kit, but init failed in the target",
					`cd {target}; rokit install; lune run kit init   ({if ok then r.stdout .. r.stderr else tostring(r)})`
				)
			end
			print(r.stdout)
			-- the data the kit's modules read at fixed paths - the animation calibration (assets/animations/calibration:
			-- the kit's measured defaults), the R6 rig's bone data (assets/rigs/R6_IK.rig.json, kit/anim/r6_rig_model.py)
			-- and the pro effect norms (`kit vfx refs norms`): seeded where the checkout has it, a project's own copies
			-- kept. AFTER init: init puts its starter libraries only into EMPTY folders, and the norms file under
			-- assets/effects made that folder look used (a new project got none of the starter effects)
			local seeded = {
				"assets/animations/calibration",
				"assets/rigs",
				"assets/effects/refs_measured/_roblox_pro_norms.json",
			}
			for _, data in seeded do
				if fs.isDir(data) then
					copyTree(data, target .. "/" .. data, false, changed)
				elseif fs.isFile(data) then
					Config.ensureDir(target .. "/" .. (string.match(data, "^(.*)/[^/]*$") :: string))
					copyTree(data, target .. "/" .. data, false, changed)
				end
			end
			-- the quality locks: the pieces a project already has are grandfathered the first time the locks reach it
			-- (board/locks.json), so only pieces made from now on need their quality step and the owner's verdict
			if not fs.isFile(target .. "/board/locks.json") then
				local okG, g = pcall(
					process.exec,
					Run.tool("python"),
					{ "kit/scripts/locks_grandfather.py" },
					{ cwd = target }
				)
				print(
					if okG and g.ok
						then `[ok] quality locks: {string.gsub(g.stdout, "%s+$", "")}`
						else `[FAIL] quality locks: python kit/scripts/locks_grandfather.py in {target} ({if okG
							then g.stderr
							else tostring(g)})`
				)
			end
			-- finish the setup IN the target so a person has nothing left to remember: tools, packages, git
			local function inTarget(label: string, program: string, argv: { string }): boolean
				local okRun, res = pcall(process.exec, program, argv, { cwd = target })
				local good = okRun and res.ok
				print(`[{if good then "ok" else "FAIL"}] {label}`)
				if not good then
					print(if okRun then res.stdout .. res.stderr else tostring(res))
				end
				return good
			end
			local toolsOk =
				inTarget("rokit install (lune, rojo, wally, selene, stylua, luau-lsp)", "rokit", { "install" })
			-- `wally install` deletes and recreates Packages/ — a running `rojo serve` watching it crashes. So an
			-- update only installs packages when they are missing (`kit add` installs, and says to restart Rojo).
			local havePackages = fs.isDir(target .. "/DevPackages") or fs.isDir(target .. "/Packages")
			local packagesOk = toolsOk
				and (
					(flags.update and havePackages)
					or inTarget("wally install (packages)", Run.tool("wally"), { "install" })
				)
			if not fs.isDir(target .. "/.git") then
				inTarget("git init", "git", { "init" })
			end
			-- the git hooks (lane fence + commit gate) need the repository: `init` ran before `git init` above, so the
			-- harness runs again now that it exists
			inTarget("git hooks (lane fence + commit gate)", Run.tool("lune"), { "run", "kit", "harness" })
			if not (toolsOk and packagesOk) then
				return Run.report(
					"install",
					{},
					C.TOOLCHAIN,
					`install: kit copied to {target}, but {if toolsOk then "wally install" else "rokit install"} failed`,
					`cd {target}; rokit install; wally install   (then: lune run kit doctor)`
				)
			end
			return Run.report(
				"install",
				{},
				C.PASS,
				`install: {#changed} kit file(s) written to {target}; tools + packages installed; ready`,
				-- (one commit across every lane: the lane fence lets it through with the word `cross`)
				`cd {target}; git add -A; git commit -m "{if flags.update
					then "Update Parallax"
					else "Start from Parallax"} (cross)"; lune run parallax doctor; lune run parallax connect <your AI client>   (then open your AI there and call parallax_start)`
			)
		end
	)

	Cli.command(
		"kit",
		"update",
		"update <path-to-project> [--force]",
		"refresh the kit in another project (kit-owned files only)",
		function(args)
			local pos, flags = Cli.parse(args)
			if type(flags.force) == "string" then
				table.insert(pos, 1, flags.force)
			end
			local forward = { pos[1] or "", "--update" }
			if flags.force then
				table.insert(forward, "--force")
			end
			return Cli.run("install", forward)
		end
	)

	Cli.command("kit", "version", "version", "kit version", function()
		local v = if fs.isFile("kit/VERSION") then string.gsub(fs.readFile("kit/VERSION"), "%s+$", "") else "?"
		return Run.report("version", {}, C.PASS, "kit " .. v, "none")
	end)

	Cli.command(
		"start",
		"asset-id",
		"asset-id <built file> <rbxassetid://N | N>",
		"record an uploaded asset's id (assets/ids.json; textures → vfx registry)",
		function(args)
			local file, id = args[1], args[2]
			if not file or not id then
				return Run.report(
					"asset-id",
					{},
					C.USAGE,
					"asset-id: needs a file and an id",
					"lune run kit asset-id build/textures/smoke.png rbxassetid://1234567"
				)
			end
			if string.match(id, "^%d+$") then
				id = "rbxassetid://" .. id
			end
			if not string.match(id, "^rbxassetid://%d+$") then
				return Run.report(
					"asset-id",
					{},
					C.USAGE,
					`asset-id: "{id}" is not an asset id`,
					"copy the number from the Studio Asset Manager / Creator Dashboard"
				)
			end
			local recorded = AssetIds.record(file, id)
			local kind, logical = AssetIds.classify(file)
			Board.journal(Board.agent(nil), `uploaded {file} → {id}`)
			return Run.report(
				"asset-id",
				{},
				C.PASS,
				`asset-id: {recorded}`,
				`commit assets/ids.json — in game: ReplicatedStorage.kit.Assets.id("{kind}", "{logical}")`
			)
		end
	)
end

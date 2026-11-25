-- harness.luau — Parallax is an MCP tool. Its server (kit/mcp/server.py) carries the rules (kit/harness/AGENTS.parallax.md,
-- sent to every client as the server's instructions) and every lane's recipe (parallax_skill: the skill page with its
-- lane's case table), and refuses pipeline work without a session - whatever AI client is on the other end. This module
-- keeps the rest in step, from ONE source each:
--   * the git hooks every clone gets: the lane fence (commit-msg) and the commit gate (pre-commit);
--   * the AI clients this project CONNECTED (`lune run parallax connect <client>`): that client's MCP config and, where
--     the client runs hooks (Claude Code, Gemini CLI), the guard's hooks (kit/scripts/parallax_guard.py). Nothing is
--     written for a client nobody connected: no instruction files, no skill copies, no configs for every tool;
--   * LEGACY CLEANUP: what older kits wrote for EVERY client - the AGENTS.md / CLAUDE.md / GEMINI.md / Copilot blocks, the
--     Cursor / Windsurf / Roo / Cline rule files and the four skill-folder copies - is removed. Only the kit's own files
--     and the text between the kit's markers go: anything you wrote yourself stays.
--   * Harness.sync({ dry = true }) changes NOTHING and lists what is out of step: `parallax harness --check`.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Config = require("./config")

local Harness = {}

local BEGIN_ANY = "<!-- kit:begin" -- (any version of the kit's opening marker)
local END = "<!-- kit:end -->"
local SERVER = "parallax"
local LEGACY_SERVER = "roblox-kit"
Harness.SERVER = SERVER
Harness.SOURCE = "kit/harness/AGENTS.parallax.md"
-- (Claude Code's hooks: the script found from CLAUDE_PROJECT_DIR by python itself - no shell expansion to trust, any
-- working folder - and a missing script is exit 0, never python's own exit 2, which would read as BLOCK everything)
Harness.CLAUDE_GUARD =
	[[python -c "import os,runpy,sys;p=os.path.join(os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd(),'kit','scripts','parallax_guard.py');sys.argv=[p]+sys.argv[1:];os.path.isfile(p) or sys.exit(0);runpy.run_path(p,run_name='__main__')"]]
-- (Gemini CLI's hooks: the same runner, the project from GEMINI_PROJECT_DIR else the working folder - a relative
-- script path run from another folder would be python's exit 2, which reads as BLOCK for every write and shell call)
Harness.GEMINI_GUARD =
	[[python -c "import os,runpy,sys;p=os.path.join(os.environ.get('GEMINI_PROJECT_DIR') or os.getcwd(),'kit','scripts','parallax_guard.py');sys.argv=[p]+sys.argv[1:];os.path.isfile(p) or sys.exit(0);runpy.run_path(p,run_name='__main__')"]]

-- the AI clients `parallax connect` knows. `file`: the project-level MCP config it reads (written by connect, kept in
-- step by every sync while it holds the kit's server); `global`: the client reads only a config outside the project,
-- so connect prints the block to paste there (with this project's absolute path) and writes nothing
Harness.CLIENTS = {
	claude = { label = "Claude Code", file = ".mcp.json", hooks = true },
	cursor = { label = "Cursor", file = ".cursor/mcp.json" },
	vscode = { label = "VS Code (GitHub Copilot agent mode)", file = ".vscode/mcp.json" },
	gemini = { label = "Gemini CLI", file = ".gemini/settings.json", hooks = true },
	roo = { label = "Roo Code", file = ".roo/mcp.json" },
	opencode = { label = "OpenCode", file = "opencode.json" },
	codex = { label = "Codex CLI", global = "~/.codex/config.toml" },
	windsurf = { label = "Windsurf", global = "~/.codeium/windsurf/mcp_config.json" },
	cline = { label = "Cline", global = "Cline's MCP settings (MCP Servers -> Configure MCP Servers)" },
	["claude-desktop"] = {
		label = "Claude Desktop",
		global = if process.os == "windows"
			then "%APPDATA%/Claude/claude_desktop_config.json"
			elseif process.os == "macos" then "~/Library/Application Support/Claude/claude_desktop_config.json"
			else "~/.config/Claude/claude_desktop_config.json",
	},
}
Harness.CLIENT_ORDER =
	{ "claude", "cursor", "vscode", "gemini", "roo", "opencode", "codex", "windsurf", "cline", "claude-desktop" }

-- what older kits wrote for every client, removed by every sync (the kit's own files and blocks only)
Harness.LEGACY_FILES = {
	".cursor/rules/parallax.mdc",
	".cursor/rules/parallax-pipeline.mdc",
	".windsurf/rules/parallax.md",
	".roo/rules/parallax.md",
	".clinerules/parallax.md",
	".cursor/rules/kit.mdc",
	".windsurf/rules/kit.md",
	".roo/rules/kit.md",
	".clinerules/kit.md",
}
Harness.LEGACY_BLOCKS = { "AGENTS.md", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md", ".clinerules" }
Harness.SKILL_DIRS = { ".claude/skills", ".opencode/skills", ".agents/skills", ".cursor/skills" }
-- (folders left empty by the cleanup are removed too - only when empty)
local LEGACY_DIRS = {
	".cursor/rules",
	".windsurf/rules",
	".windsurf",
	".roo/rules",
	".roo",
	".clinerules",
	".claude/skills",
	".claude",
	".opencode/skills",
	".opencode",
	".agents/skills",
	".agents",
	".cursor/skills",
	".cursor",
	".github",
}

-- the run's state: dry = record only (the --check)
local dry = false

local function write(path: string, text: string, changed: { string })
	if fs.isFile(path) and fs.readFile(path) == text then
		return
	end
	if not dry then
		local parent = string.match(path, "^(.*)/[^/]+$")
		if parent then
			Config.ensureDir(parent)
		end
		fs.writeFile(path, text)
	end
	table.insert(changed, path)
end

local function remove(path: string, changed: { string })
	if fs.isFile(path) then
		if not dry then
			fs.removeFile(path)
		end
		table.insert(changed, `{path} (removed)`)
	elseif fs.isDir(path) then
		if not dry then
			fs.removeDir(path)
		end
		table.insert(changed, `{path} (removed)`)
	end
end

local function readJson(path: string): (boolean, any)
	if not fs.isFile(path) then
		return true, nil
	end
	local ok, d = pcall(serde.decode, "json" :: any, fs.readFile(path))
	if not ok or type(d) ~= "table" then
		return false, nil
	end
	return true, d
end

local function mergeJson(path: string, mutate: (any) -> (), changed: { string })
	local ok, data = readJson(path)
	if not ok then
		print(`[harness] skipped {path}: not valid JSON (fix it, then re-run parallax harness)`)
		return
	end
	data = data or {}
	local before = serde.encode("json", data)
	mutate(data)
	if serde.encode("json", data) ~= before or not fs.isFile(path) then
		write(path, serde.encode("json", data, true) .. "\n", changed)
	end
end

-- nothing left in a config but empty tables and a schema line: the kit's entry was all it held
local function emptyJson(d: any): boolean
	for k, v in d do
		if k ~= "$schema" and not (type(v) == "table" and next(v) == nil) then
			return false
		end
	end
	return true
end

-- take the kit's entries out of a JSON config; the file goes when nothing else is left in it
local function pruneJson(path: string, mutate: (any) -> (), changed: { string })
	local ok, data = readJson(path)
	if not ok or data == nil then
		return
	end
	local before = serde.encode("json", data)
	mutate(data)
	if emptyJson(data) then
		remove(path, changed)
	elseif serde.encode("json", data) ~= before then
		write(path, serde.encode("json", data, true) .. "\n", changed)
	end
end

-- the Python this machine has, probed once: "python" on Windows; elsewhere python3 first (many Linux / macOS machines
-- have no bare `python`), then python. The hook commands and the MCP launch are written with it, so a client's config
-- names a Python that exists HERE (connect runs on the machine that will use it)
local pythonName: string? = nil
function Harness.python(): string
	if pythonName then
		return pythonName :: string
	end
	if process.os == "windows" then
		pythonName = "python"
	else
		pythonName = "python"
		for _, candidate in { "python3", "python" } do
			local ok, res = pcall(process.exec, candidate, { "--version" })
			if ok and res.ok then
				pythonName = candidate
				break
			end
		end
	end
	return pythonName :: string
end

function Harness.mcpCommand(): (string, { string })
	if process.os == "windows" then
		-- Python stdio on Windows is most reliable launched through cmd /c
		return "cmd", { "/c", "python", "kit/mcp/server.py" }
	end
	return Harness.python(), { "kit/mcp/server.py" }
end

-- this project's absolute root, forward slashes, no trailing slash (for the clients that read a GLOBAL config)
function Harness.projectRoot(): string
	local root = string.gsub(process.cwd, "\\", "/")
	root = string.gsub(root, "/+$", "")
	return root
end

-- the server launch for a global config: the absolute path, because such a client starts it from its own folder
function Harness.mcpCommandAbsolute(): (string, { string })
	local script = Harness.projectRoot() .. "/kit/mcp/server.py"
	if process.os == "windows" then
		return "cmd", { "/c", "python", script }
	end
	return Harness.python(), { script }
end

local FENCE_MARK = "# kit lane fence (managed by `lune run kit harness`)"
Harness.FENCE_HOOK = table.concat({
	"#!/bin/sh",
	FENCE_MARK,
	"# refuses (in enforce mode) a commit that changes two lanes' own files; see kit/knowledge/lanes.json",
	"[ -f kit/scripts/lane_fence.py ] || exit 0",
	"PY=python; command -v python >/dev/null 2>&1 || PY=python3",
	'command -v "$PY" >/dev/null 2>&1 || exit 0',
	'"$PY" kit/scripts/lane_fence.py --commit-msg "$1"',
	"",
}, "\n")

-- the hooks folder every worktree of this repository shares; nil outside a git checkout
local function hooksDir(): string?
	local ok, res = pcall(process.exec, "git", { "rev-parse", "--git-common-dir" })
	if not ok or not res.ok then
		return nil
	end
	local common = string.gsub(res.stdout, "%s+$", "")
	return if common ~= "" then common .. "/hooks" else nil
end

local function installHook(file: string, mark: string, body: string, changed: { string }, notes: { string })
	local dir = hooksDir()
	if not dir then
		return
	end
	local path = dir .. "/" .. file
	if fs.isFile(path) then
		local cur = fs.readFile(path)
		if not string.find(cur, mark, 1, true) then
			table.insert(notes, `{path} is your own hook: the kit's was NOT installed`)
			return
		end
		if cur == body then
			return
		end
	elseif dry then
		-- (a clone that never ran `lune run parallax harness` has no kit hooks: hooks live in each clone and are never
		-- committed, so the check names a kit hook only once it is installed and stale - a fresh clone and CI pass)
		return
	end
	if not dry then
		Config.ensureDir(dir)
		fs.writeFile(path, body)
	end
	table.insert(changed, path)
end

function Harness.installFence(changed: { string }, notes: { string })
	if fs.isFile("kit/scripts/lane_fence.py") then
		installHook("commit-msg", FENCE_MARK, Harness.FENCE_HOOK, changed, notes)
	end
end

-- the commit gate: a commit whose staged files fail the format check / selene / a Python compile, or a case's
-- anti-pattern, or a stale connected client, is refused (kit/scripts/precommit.py -> parallax_guard.py --hook pre-commit)
local GATE_MARK = "# kit commit gate (managed by `lune run kit harness`)"
Harness.GATE_HOOK = table.concat({
	"#!/bin/sh",
	GATE_MARK,
	"# refuses a commit whose staged Luau fails stylua / selene, whose staged Python does not compile, or that",
	"# breaks a case contract / leaves the harness files stale (kit/scripts/parallax_guard.py --hook pre-commit)",
	"[ -f kit/scripts/precommit.py ] || exit 0",
	"PY=python; command -v python >/dev/null 2>&1 || PY=python3",
	'command -v "$PY" >/dev/null 2>&1 || exit 0',
	'"$PY" kit/scripts/precommit.py',
	"",
}, "\n")

function Harness.installGate(changed: { string }, notes: { string })
	if fs.isFile("kit/scripts/precommit.py") then
		installHook("pre-commit", GATE_MARK, Harness.GATE_HOOK, changed, notes)
	end
end

-- the Claude Code hooks (§2.4): the guard before every write / shell call, after every write, and at the stop
function Harness.claudeHooks(): any
	local function hook(kind: string): any
		-- (by the project's absolute path: a session whose working folder left the root would otherwise run a missing
		-- script, and python's exit 2 reads as BLOCK for every tool call)
		-- (the Python that exists on this machine: python3 where there is no bare python)
		local guard = string.gsub(Harness.CLAUDE_GUARD, "^python ", Harness.python() .. " ", 1)
		return { type = "command", command = `{guard} --hook {kind}`, timeout = 10 }
	end
	return {
		PreToolUse = {
			{
				matcher = "Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell|mcp__parallax__.*",
				hooks = { hook("pre-tool") },
			},
		},
		PostToolUse = { { matcher = "Write|Edit|MultiEdit|NotebookEdit", hooks = { hook("post-tool") } } },
		Stop = { { hooks = { hook("stop") } } },
	}
end

-- the Gemini CLI hooks: the same guard as BeforeTool / AfterTool (its own schema: matcher + command hooks)
function Harness.geminiHooks(): any
	local function hook(kind: string): any
		local guard = string.gsub(Harness.GEMINI_GUARD, "^python ", Harness.python() .. " ", 1)
		return { type = "command", command = `{guard} --hook {kind}`, timeout = 10000 }
	end
	return {
		BeforeTool = { { matcher = "write_file|replace|run_shell_command", hooks = { hook("pre-tool") } } },
		AfterTool = { { matcher = "write_file|replace", hooks = { hook("post-tool") } } },
	}
end

-- is this hook entry ours (so a re-sync replaces it and never stacks a second copy)?
local function ours(entry: any): boolean
	for _, h in (type(entry) == "table" and entry.hooks or {}) :: { any } do
		if
			type(h) == "table"
			and type(h.command) == "string"
			and string.find(h.command, "parallax_guard.py", 1, true)
		then
			return true
		end
	end
	return false
end

-- the same guard hook, the launcher word aside, when the existing one's launcher works HERE (a settings file shared
-- between machines - `python` on one, `python3` on another - is not rewritten on each); any other difference is not
local function sameHookCommand(old: any, fresh: any): boolean
	if type(old) ~= "string" or type(fresh) ~= "string" then
		return false
	end
	if old == fresh then
		return true
	end
	local word, rest = string.match(old, "^(%S+)%s(.*)$")
	local _, freshRest = string.match(fresh, "^(%S+)%s(.*)$")
	return word ~= nil and rest == freshRest and Harness.launcherHere(word)
end

local function sameHookEntry(a: any, b: any): boolean
	if type(a) ~= "table" or type(b) ~= "table" or a.matcher ~= b.matcher then
		return false
	end
	local ah, bh = a.hooks, b.hooks
	if type(ah) ~= "table" or type(bh) ~= "table" or #ah ~= #bh then
		return false
	end
	for i, h in bh do
		local o = ah[i]
		if
			type(o) ~= "table"
			or o.type ~= h.type
			or o.timeout ~= h.timeout
			or not sameHookCommand(o.command, h.command)
		then
			return false
		end
		for k in o do
			if k ~= "type" and k ~= "timeout" and k ~= "command" then
				return false
			end
		end
	end
	for k in a do
		if k ~= "matcher" and k ~= "hooks" then
			return false
		end
	end
	return true
end

local function mergeHooks(d: any, hooks: any)
	d.hooks = d.hooks or {}
	for event, entries in hooks do
		local kept, mine = {}, {}
		for _, e in (d.hooks[event] or {}) :: { any } do
			table.insert(if ours(e) then mine else kept, e)
		end
		local same = #mine == #entries
		for i, e in entries do
			same = same and sameHookEntry(mine[i], e)
		end
		for _, e in (if same then mine else entries) :: { any } do
			table.insert(kept, e)
		end
		d.hooks[event] = kept
	end
end

local function stripHooks(d: any)
	if type(d.hooks) ~= "table" then
		return
	end
	for event, entries in d.hooks do
		local kept = {}
		for _, e in (if type(entries) == "table" then entries else {}) :: { any } do
			if not ours(e) then
				table.insert(kept, e)
			end
		end
		d.hooks[event] = if #kept > 0 then kept else nil
	end
	if next(d.hooks) == nil then
		d.hooks = nil
	end
end

-- a lane's CASE-ROUTING TABLE from kit/knowledge/cases/<lane>.json (markdown, a few lines per case)
local SKILL_LANE = {
	["parallax-3d"] = "3d",
	["parallax-vfx"] = "vfx",
	["parallax-anim"] = "anim",
	["parallax-world"] = "world",
	["parallax-ui"] = "ui",
	["parallax-sfx"] = "sfx",
	["parallax-systems"] = "code",
	["parallax-qa"] = "qa",
}

function Harness.caseTable(lane: string): string?
	local path = `kit/knowledge/cases/{lane}.json`
	if not fs.isFile(path) then
		return nil
	end
	local ok, reg = pcall(serde.decode, "json" :: any, fs.readFile(path))
	if not ok or type(reg) ~= "table" or type(reg.cases) ~= "table" then
		return nil
	end
	local lines = {
		`## Case routing ({lane}) — generated from kit/knowledge/cases/{lane}.json; never edit here`,
		"",
		`Find the case first: \`lune run parallax case {lane} "<the request>"\` (or \`parallax start {lane} --prompt "..."\`).`,
		"",
		"| case | when | floor (first steps) | forbidden |",
		"|---|---|---|---|",
	}
	for _, c in reg.cases :: { any } do
		local floor = {}
		for i, t in (c.required_tools_ordered or {}) :: { any } do
			if i > 3 then
				table.insert(floor, "…")
				break
			end
			table.insert(floor, tostring(t))
		end
		local bad = {}
		for _, f in (c.forbidden_tools or {}) :: { any } do
			table.insert(bad, if type(f) == "table" then `{f.id or ""} {f.pattern or ""}` else tostring(f))
		end
		local row = string.format(
			"| `%s` | %s | %s | %s |",
			tostring(c.case_id),
			string.gsub(tostring(c.label or ""), "|", "/"),
			string.gsub(table.concat(floor, " -> "), "|", "/"),
			string.gsub(if #bad > 0 then table.concat(bad, ", ") else "—", "|", "/")
		)
		table.insert(lines, row)
	end
	table.insert(lines, "")
	table.insert(
		lines,
		'Full capability, case-matched: the floor is the minimum, extra non-forbidden tools are always allowed; an edge-case skip is `--skip-tool <tool> --why "<reason>"` (logged).'
	)
	return table.concat(lines, "\n")
end

-- a lane's full recipe as every client gets it (parallax_skill / `parallax skill`): its frontmatter, then the page's
-- title, then the lane's case table, then the rest of the page
function Harness.skillCopy(name: string): string
	local text = fs.readFile(`kit/skills/{name}/SKILL.md`)
	local lane = SKILL_LANE[name]
	local tableText = lane and Harness.caseTable(lane)
	if not tableText then
		return text
	end
	local front, body = string.match(text, "^(%-%-%-\r?\n.-\r?\n%-%-%-\r?\n)(.*)$")
	if not front then
		return tableText .. "\n\n" .. text
	end
	-- after the page's own "# title" line when it opens with one (a client that shortens a long description shows the
	-- body's first line: the title must stay first)
	local title, rest = string.match(body :: string, "^(%s*# [^\r\n]*\r?\n)(.*)$")
	if title then
		return front .. title .. "\n" .. tableText .. "\n\n" .. rest
	end
	return front .. "\n" .. tableText .. "\n\n" .. (body :: string)
end

-- the kit's server entry in one client's config (nil when that config does not hold it)
local function entryOf(name: string, data: any): any
	if type(data) ~= "table" then
		return nil
	end
	local key = if name == "vscode" then "servers" elseif name == "opencode" then "mcp" else "mcpServers"
	local servers = data[key]
	return if type(servers) == "table" then servers[SERVER] else nil
end

-- the project-level clients whose config holds the kit's server (in CLIENT_ORDER)
function Harness.connected(): { string }
	local out = {}
	for _, name in Harness.CLIENT_ORDER do
		local c = Harness.CLIENTS[name]
		if c.file then
			local ok, data = readJson(c.file)
			if ok and entryOf(name, data) ~= nil then
				table.insert(out, name)
			end
		end
	end
	return out
end

-- The Python launchers that start the kit on THIS machine: Windows `python` / `py` (never `python3`, often only the
-- Store's stub there); elsewhere `python3` / `python`, each only if it runs here. A config one machine wrote and
-- another shares is kept while its launcher works on this one, and rewritten when it cannot (`cmd` off Windows).
local SERVER_SCRIPT = "kit/mcp/server.py"
local launchers: { [string]: boolean }? = nil
local function launcherHere(word: any): boolean
	if launchers == nil then
		local found: { [string]: boolean } = {}
		if process.os == "windows" then
			found = { python = true, ["python.exe"] = true, py = true }
		else
			for _, candidate in { "python3", "python" } do
				local ok, res = pcall(process.exec, candidate, { "--version" })
				if ok and res.ok then
					found[candidate] = true
				end
			end
		end
		launchers = found
	end
	return type(word) == "string" and (launchers :: { [string]: boolean })[string.lower(word)] == true
end
Harness.launcherHere = launcherHere

-- The kit's server entry is the KIT's: exactly its launch and nothing else. Any other key on it could change what runs
-- or whether it runs - an env var can switch the gate off (PARALLAX_ENFORCE) or pick another program (KIT_BLENDER), a
-- URL or `type` can point the name elsewhere, `disabled` keeps the server down - so none is kept: an entry that is not
-- exactly the kit's launch is replaced whole. (Settings of your own belong in your shell's environment, which the
-- client passes to the server, or in an entry of your own under another name.)

-- is an existing entry EXACTLY the kit's own launch of this project's server, in this client's own shape (OpenCode: a
-- command array; the others: a command string + args), by a launcher that works here - `<py> kit/mcp/server.py` or
-- (Windows) `cmd /c <py> kit/mcp/server.py` - with no other key but the client's own `type` (and OpenCode's
-- `enabled = true`)?
local function launchesServer(name: string, old: any): boolean
	if type(old) ~= "table" then
		return false
	end
	local want = if name == "vscode" then "stdio" elseif name == "opencode" then "local" else nil
	for k, v in old do
		if k == "command" or k == "args" then
			continue
		elseif k == "type" then
			if v ~= (want or "stdio") then
				return false
			end
		elseif k == "enabled" and name == "opencode" then
			if v ~= true then
				return false
			end
		else
			return false
		end
	end
	local w: { any } = {}
	if name == "opencode" then
		if type(old.command) ~= "table" or old.args ~= nil then
			return false
		end
		w = old.command
	else
		if type(old.command) ~= "string" or type(old.args) ~= "table" then
			return false
		end
		w = { old.command }
		for _, a in old.args do
			table.insert(w, a)
		end
	end
	if #w == 2 then
		return launcherHere(w[1]) and w[2] == SERVER_SCRIPT
	end
	if #w == 4 and process.os == "windows" then
		return type(w[1]) == "string"
			and string.lower(w[1]) == "cmd"
			and type(w[2]) == "string"
			and string.lower(w[2]) == "/c"
			and launcherHere(w[3])
			and w[4] == SERVER_SCRIPT
	end
	return false
end

-- the kit's server entry for one client: kept as it is when it is already exactly the kit's launch (a config shared
-- between machines is not rewritten on each one - only a key the kit's entry has and it lacks is added), else the
-- kit's own entry, whole
local function serverEntry(name: string, old: any, fresh: { [string]: any }): { [string]: any }
	if launchesServer(name, old) then
		for k, v in fresh do
			if old[k] == nil then
				old[k] = v
			end
		end
		return old
	end
	return fresh
end

-- a client's list of servers it keeps off, without the kit's (nil when nothing is left of it)
local function withoutServer(list: any): any
	if type(list) ~= "table" then
		return list
	end
	local out = {}
	for _, s in list do
		if s ~= SERVER and s ~= LEGACY_SERVER then
			table.insert(out, s)
		end
	end
	return if #out > 0 then out else nil
end

-- write (or refresh) one project-level client: its MCP entry, and its guard hooks when it runs hooks
local function clientWrite(name: string, changed: { string })
	local c = Harness.CLIENTS[name]
	local command, args = Harness.mcpCommand()
	if name == "vscode" then
		mergeJson(c.file, function(d)
			d.servers = d.servers or {}
			d.servers[LEGACY_SERVER] = nil
			d.servers[SERVER] = serverEntry(name, d.servers[SERVER], { type = "stdio", command = command, args = args })
		end, changed)
	elseif name == "opencode" then
		mergeJson(c.file, function(d)
			d["$schema"] = d["$schema"] or "https://opencode.ai/config.json"
			d.mcp = d.mcp or {}
			d.mcp[LEGACY_SERVER] = nil
			local full = { command }
			for _, a in args do
				table.insert(full, a)
			end
			d.mcp[SERVER] = serverEntry(name, d.mcp[SERVER], { type = "local", command = full, enabled = true })
		end, changed)
	else
		mergeJson(c.file, function(d)
			d.mcpServers = d.mcpServers or {}
			d.mcpServers[LEGACY_SERVER] = nil
			d.mcpServers[SERVER] = serverEntry(name, d.mcpServers[SERVER], { command = command, args = args })
			if name == "gemini" then
				-- (the settings that would keep the kit's server off, beside its entry: never kept)
				d.excludeMCPServers = withoutServer(d.excludeMCPServers)
				if type(d.mcp) == "table" then
					d.mcp.excluded = withoutServer(d.mcp.excluded)
				end
				mergeHooks(d, Harness.geminiHooks())
			end
		end, changed)
	end
	if name == "claude" then
		-- Claude Code: approve the kit's server in the PROJECT's settings and install the guard's hooks (§2.4); the
		-- settings that would keep the server or the guard off (disabledMcpjsonServers naming it, disableAllHooks) go
		mergeJson(".claude/settings.json", function(d)
			local servers = {}
			for _, s in (d.enabledMcpjsonServers or {}) :: { any } do
				if s ~= LEGACY_SERVER and s ~= SERVER then
					table.insert(servers, s)
				end
			end
			table.insert(servers, SERVER)
			d.enabledMcpjsonServers = servers
			d.disabledMcpjsonServers = withoutServer(d.disabledMcpjsonServers)
			if d.disableAllHooks == true then
				d.disableAllHooks = nil
			end
			mergeHooks(d, Harness.claudeHooks())
		end, changed)
	end
end

-- take one project-level client's kit entry (and the guard's hooks) out; a config left empty is removed
local function clientRemove(name: string, changed: { string })
	local c = Harness.CLIENTS[name]
	local key = if name == "vscode" then "servers" elseif name == "opencode" then "mcp" else "mcpServers"
	pruneJson(c.file, function(d)
		if type(d[key]) == "table" then
			d[key][SERVER] = nil
			d[key][LEGACY_SERVER] = nil
		end
		if name == "gemini" then
			stripHooks(d)
		end
	end, changed)
	if name == "claude" then
		pruneJson(".claude/settings.json", function(d)
			local servers = {}
			for _, s in (d.enabledMcpjsonServers or {}) :: { any } do
				if s ~= LEGACY_SERVER and s ~= SERVER then
					table.insert(servers, s)
				end
			end
			d.enabledMcpjsonServers = if #servers > 0 then servers else nil
			stripHooks(d)
		end, changed)
	end
	-- the client's own folder, when that config was all it held
	if not dry then
		for _, d in { ".cursor", ".vscode", ".gemini", ".roo", ".claude" } do
			if fs.isDir(d) and #fs.readDir(d) == 0 then
				fs.removeDir(d)
			end
		end
	end
end

-- the block to paste into a GLOBAL client's config (absolute path: such a client starts the server from its own folder)
function Harness.globalSnippet(name: string): string
	local command, args = Harness.mcpCommandAbsolute()
	if name == "codex" then
		local quoted = {}
		for _, a in args do
			table.insert(quoted, `"{a}"`)
		end
		return `[mcp_servers.{SERVER}]\ncommand = "{command}"\nargs = [{table.concat(quoted, ", ")}]\n`
	end
	return serde.encode("json", { mcpServers = { [SERVER] = { command = command, args = args } } }, true) .. "\n"
end

-- the comment an older kit wrote under its title, pointing at its block
local KIT_COMMENT = "<!-- Project-specific notes for every AI agent go above or below the kit block. -->"

-- cut the kit's block (and the kit's own comment line) out of an instruction file, keeping everything else exactly -
-- its line endings too. The file goes only when nothing is left but the title an older kit wrote at its top.
local function stripBlock(path: string, changed: { string })
	if not fs.isFile(path) then
		return
	end
	local cur = fs.readFile(path)
	local a = string.find(cur, BEGIN_ANY, 1, true)
	local _, b = string.find(cur, END, 1, true)
	if not (a and b and b > a) then
		return
	end
	local eol = if string.find(cur, "\r\n", 1, true) then "\r\n" else "\n"
	local rest = string.sub(cur, 1, a - 1) .. string.sub(cur, b + 1)
	local c1, c2 = string.find(rest, KIT_COMMENT, 1, true)
	if c1 and c2 then
		local after = c2 + 1
		if string.sub(rest, after, after + 1) == "\r\n" then
			after += 2
		elseif string.sub(rest, after, after) == "\n" then
			after += 1
		end
		rest = string.sub(rest, 1, c1 - 1) .. string.sub(rest, after)
	end
	local probe = string.gsub(rest, "^%s*# %u+%.md — [^\r\n]*", "")
	if string.match(probe, "^%s*$") then
		remove(path, changed)
		return
	end
	local text = string.gsub(string.gsub(rest, "^%s+", ""), "%s+$", "")
	local three, two = eol .. eol .. eol, eol .. eol
	while string.find(text, three, 1, true) do
		text = string.gsub(text, three, two)
	end
	write(path, text .. eol, changed)
end

-- one skill folder an older kit filled: the SKILL.md copies its manifest lists go (a file you added beside one stays;
-- the folder goes only once empty), then the manifest -> was a manifest there?
local function cleanSkillDir(dir: string, changed: { string }): boolean
	local managed, found = {}, false
	for _, mf in { dir .. "/.parallax-managed", dir .. "/.kit-managed" } do
		if fs.isFile(mf) then
			found = true
			for line in string.gmatch(fs.readFile(mf), "[^\r\n]+") do
				-- (a plain skill name only: never a path, never "." or "..")
				if string.match(line, "^[%w][%w_%-]*$") then
					table.insert(managed, line)
				end
			end
			remove(mf, changed)
		end
	end
	for _, name in managed do
		local folder = `{dir}/{name}`
		if fs.isFile(folder .. "/SKILL.md") then
			remove(folder .. "/SKILL.md", changed)
			if not dry and fs.isDir(folder) and #fs.readDir(folder) == 0 then
				fs.removeDir(folder)
			end
		end
	end
	return found
end

-- the AI client running this very command, when it says so in the environment: Claude Code sets CLAUDECODE=1 and
-- Gemini CLI GEMINI_CLI=1 for the commands they run. (A field, so a spec can stand in for the environment.)
function Harness.runningClient(): string?
	if process.env.CLAUDECODE == "1" then
		return "claude"
	elseif process.env.GEMINI_CLI == "1" then
		return "gemini"
	end
	return nil
end

-- what an older kit wrote for EVERY client: its rule files, its blocks in instruction files, its skill copies (only the
-- SKILL.md it wrote - a file you added in that folder stays), and the kit's entry in every client's MCP config (it
-- wrote them all; a client you use is connected again with `parallax connect <client>`). The client running the
-- upgrade keeps its entry and hooks (refreshed by the sync), so the session doing it keeps its server and its guard.
-- -> (was any of it there?, the client kept)
local function legacyCleanup(changed: { string }): (boolean, string?)
	local found = false
	for _, old in Harness.LEGACY_FILES do
		if fs.isFile(old) then
			found = true
			remove(old, changed)
		end
	end
	for _, path in Harness.LEGACY_BLOCKS do
		local before = #changed
		stripBlock(path, changed)
		found = found or #changed > before
	end
	for _, dir in Harness.SKILL_DIRS do
		found = cleanSkillDir(dir, changed) or found
	end
	local kept: string? = nil
	if found then
		local running = Harness.runningClient()
		if running and table.find(Harness.connected(), running) then
			kept = running
		end
		for _, name in Harness.CLIENT_ORDER do
			if Harness.CLIENTS[name].file and name ~= kept then
				clientRemove(name, changed)
			end
		end
	end
	if not dry then
		for _, d in LEGACY_DIRS do
			if fs.isDir(d) and #fs.readDir(d) == 0 then
				fs.removeDir(d)
			end
		end
	end
	return found, kept
end

-- sync (opts.dry: change nothing, return what is out of step) -> (changed, notes)
function Harness.sync(opts: { dry: boolean? }?): ({ string }, { string })
	dry = (opts and opts.dry) == true
	local changed, notes = {}, {}
	local ok, err = pcall(function()
		local legacy, kept = legacyCleanup(changed)
		if legacy then
			table.insert(
				notes,
				"removed what an older kit wrote for every AI client (rules, skill copies, every client's MCP entry)"
					.. (if kept
						then `; kept {Harness.CLIENTS[kept].label}'s (it runs this command): connect any other client you use`
						else ": connect the one you use again")
					.. " - lune run parallax connect <client>"
			)
		end
		-- git hooks: the lane fence (commit-msg) and the commit gate (pre-commit)
		Harness.installFence(changed, notes)
		Harness.installGate(changed, notes)
		-- the connected clients' MCP entries and hooks, refreshed (a moved server or a changed guard reaches them)
		local connected = Harness.connected()
		for _, name in connected do
			clientWrite(name, changed)
		end
		if #connected == 0 then
			table.insert(
				notes,
				"no AI client connected: lune run parallax connect <client> (claude, cursor, vscode, gemini, roo, opencode; codex, windsurf, cline and claude-desktop print the block for their global config)"
			)
		end
	end)
	dry = false
	if not ok then
		error(err, 0)
	end
	return changed, notes
end

-- an older kit's block cut out of one instruction file (the file goes when nothing of yours is left) -> the paths changed
function Harness.stripBlock(path: string): { string }
	local changed = {}
	stripBlock(path, changed)
	return changed
end

-- an older kit's skill copies out of one skill folder (its manifest's SKILL.md files only) -> the paths changed
function Harness.cleanSkillDir(dir: string): { string }
	local changed = {}
	cleanSkillDir(dir, changed)
	return changed
end

-- `parallax connect <client>`: write (or refresh) that client's config, and make sure the git hooks are in -> the paths
-- written, or nothing + why (a config that is not valid JSON is never overwritten)
function Harness.connect(name: string): ({ string }, string?)
	local files = { Harness.CLIENTS[name].file :: string }
	if name == "claude" then
		table.insert(files, ".claude/settings.json")
	end
	for _, f in files do
		local ok = readJson(f)
		if not ok then
			return {}, `{f} is not valid JSON: fix it (or move it away), then connect again`
		end
	end
	local changed, notes = {}, {}
	clientWrite(name, changed)
	Harness.installFence(changed, notes)
	Harness.installGate(changed, notes)
	return changed, nil
end

-- `parallax connect <client> --remove`: the kit's entry and hooks out of that client's config -> the paths changed
function Harness.disconnect(name: string): { string }
	local changed = {}
	clientRemove(name, changed)
	return changed
end

-- `parallax harness --check`: what a sync would change (nothing written) -> the out-of-step paths
function Harness.check(): { string }
	local changed = Harness.sync({ dry = true })
	return changed
end

return Harness

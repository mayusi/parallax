-- enforcer.luau — the CLI KERNEL GATE (PARALLAX_ENFORCEMENT_AND_ROUTING_SPEC §2.3 layer 2, §5.1 step 5): every
-- command passes Enforcer.before(name, args) first (kit/init.luau sets Cli.before to it). It
--   a. shows the department's vault page when it is due (kit/lib/vaultgate.luau, never blocks);
--   b. refuses a MUTATING pipeline command (new, asset, make, cad, gen, vfx, anim, world, ui, sfx, move, net, optimize,
--      upload) without a fresh session token .verify/parallax_session.json + its PROMPT-X sha (written by
--      `parallax start <lane> --prompt "..."` / `parallax prompt compile`), or whose lane the session does not cover;
--   c. refuses a HEAVY build of a named piece without assets/plans/<piece>.plan.json (§3.3: the tools chosen per part /
--      beat from the lane's capability menu once the refs were seen), a plan whose tools the case forbids, or one
--      missing a v4 upgrade tool that EXISTS on disk (an unbuilt one never blocks);
--   d. refuses a command whose own words name a route its case forbids (forbidden_tools patterns).
-- Never gated: the bootstrap + read-only allowlist (prompt, start, case, help, status, verify, selftest, prove, ...),
-- `asset all`, a look-up subcommand (help, list, find, --check), and children of a governance command (kit verify /
-- selftest / prove spawn kit commands: PARALLAX_EXEMPT travels to them through Run.spawn). Escape hatches, both
-- logged into the session: --maintenance "<why>" (no session needed) and --skip-tool <tool> --why "<why>".
-- PARALLAX_ENFORCE (or KIT_ENFORCE) = enforce (default) | audit (say it, run anyway) | off.
local DateTime = require("@lune/datetime")
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Config = require("./config")
local VaultGate = require("./vaultgate")

local Enforcer = {}

Enforcer.CODE = 6 -- Run.CODES.CONTENT: a content gate refused (kept here so the spec needs no Run)
-- the session token (PARALLAX_SESSION_FILE / KIT_SESSION_FILE override it: specs, a second checkout)
Enforcer.SESSION = process.env.PARALLAX_SESSION_FILE or process.env.KIT_SESSION_FILE or ".verify/parallax_session.json"
Enforcer.PLANS = "assets/plans"
Enforcer.TTL = 4 * 3600

-- the bootstrap + read-only + governance allowlist (§2.2): never gated, so a session can always be started
Enforcer.ALLOW = {}
for _, n in
	{
		"prompt",
		"start",
		"case",
		"kickoff",
		"game",
		"help",
		"status",
		"doctor",
		"verify",
		"selftest",
		"prove",
		"harness",
		"connect",
		"plan",
		"task",
		"handoff",
		"decide",
		"log",
		"lesson",
		"lessons",
		"verdict",
		"approve",
		"audit",
		"board",
		"review",
		"docs",
		"tools",
		"library",
		"vault",
		"examples",
		"skill",
		"version",
		"checks",
		"upgrade",
	}
do
	Enforcer.ALLOW[n] = true
end

-- the mutating pipeline commands (§2.3 layer 2) and their lane (nil = the session's own)
Enforcer.MUTATING = {
	new = false,
	asset = "3d",
	make = "3d",
	cad = "3d",
	gen = "3d",
	optimize = "3d",
	vfx = "vfx",
	anim = "anim",
	world = "world",
	ui = "ui",
	sfx = "sfx",
	move = "code",
	net = "code",
	upload = false,
}
-- kit new <kind> -> its lane
Enforcer.NEW_KIND = {
	asset = "3d",
	vfx = "vfx",
	anim = "anim",
	world = "world",
	screen = "ui",
	sound = "sfx",
	system = "code",
	game = "code",
	playtest = "qa",
}
-- a subcommand that only looks things up
Enforcer.LOOKUP = {
	help = true,
	list = true,
	find = true,
	catalog = true,
	methods = true,
	cost = true,
	status = true,
	["--status"] = true,
	["--check"] = true,
	["--list"] = true,
}
-- kit gen's own subcommands (the piece is the word after them)
Enforcer.GEN_SUBS = { texture = true, omni = true, parts = true, views = true, ["mv-shape"] = true, paint = true }
-- a HEAVY build of a named piece: its input file decides that the word is a piece, not a subcommand
Enforcer.HEAVY = {
	asset = function(n: string): boolean
		return fs.isFile(`{Config.root()}assets/models/build_{n}.py`)
	end,
	make = function(_n: string): boolean
		return true
	end,
	gen = function(n: string): boolean
		return not Enforcer.LOOKUP[n] and not Enforcer.GEN_SUBS[n]
	end,
	vfx = function(n: string): boolean
		return fs.isFile(`{Config.root()}assets/effects/{n}.json`)
	end,
	anim = function(n: string): boolean
		return fs.isFile(`{Config.root()}assets/animations/{n}.json`)
	end,
	world = function(n: string): boolean
		return fs.isFile(`{Config.root()}assets/worlds/{n}.json`)
	end,
	sfx = function(n: string): boolean
		return fs.isFile(`{Config.root()}assets/sounds/{n}.json`)
	end,
}

function Enforcer.mode(): string
	local m = process.env.PARALLAX_ENFORCE or process.env.KIT_ENFORCE
	if m == "audit" or m == "off" then
		return m
	end
	return "enforce"
end

local function norm(s: string): string
	return (string.gsub(string.lower(s), "[^%w]+", "_"))
end

local function readJson(path: string): any?
	if not fs.isFile(path) then
		return nil
	end
	local ok, v = pcall(serde.decode, "json" :: any, fs.readFile(path))
	return if ok and type(v) == "table" then v else nil
end

-- the checkout's branch from .git/HEAD (nil when unknown)
function Enforcer.branch(): string?
	local head = ".git/HEAD"
	if fs.isFile(".git") then
		local gd = string.match(fs.readFile(".git"), "gitdir:%s*(%S+)")
		head = if gd then `{gd}/HEAD` else head
	end
	if not fs.isFile(head) then
		return nil
	end
	local ref = string.gsub(fs.readFile(head), "%s+$", "")
	local b = string.match(ref, "^ref:.*/([^/]+)$")
	return b or "HEAD"
end

local function iso(t: string?): number?
	if type(t) ~= "string" then
		return nil
	end
	local ok, d = pcall(DateTime.fromIsoDate, t)
	return if ok and d then d.unixTimestamp else nil
end

-- PROMPT-X keeps every compiled packet by its sha (kit/prompt/evolve.py save_packet): a token names a real one
Enforcer.PACKETS = "build/prompt/packets"
function Enforcer.packetMatches(sha: string): boolean
	if not string.match(sha, "^[0-9a-f]+$") or #sha < 6 then
		return false
	end
	local p = readJson(`{Enforcer.PACKETS}/{sha}.json`)
	local text = p and p.orchestrator_prompt
	return type(text) == "string" and string.sub(serde.hash("sha1", text), 1, #sha) == sha
end

-- the exempt marker children of a governance command carry: a nonce this process minted and filed in
-- .verify/parallax_exempt.json (a shell that types PARALLAX_EXEMPT=1 holds no filed nonce: it is gated as before)
Enforcer.EXEMPT_FILE = ".verify/parallax_exempt.json"
Enforcer.EXEMPT_TTL = 24 * 3600
function Enforcer.mintExempt()
	if type(process.env.PARALLAX_EXEMPT) == "string" and Enforcer.exempt() then
		return -- (a governance command run by another one keeps its parent's token)
	end
	local nonce = serde.hash("sha256", `{DateTime.now().unixTimestampMillis}-{math.random()}-{os.clock()}`)
	local now = DateTime.now().unixTimestamp
	local list = {}
	for _, e in ((readJson(Enforcer.EXEMPT_FILE) or {}).tokens or {}) :: { any } do
		if type(e) == "table" and type(e.at) == "number" and now - e.at < Enforcer.EXEMPT_TTL then
			table.insert(list, e)
		end
	end
	table.insert(list, { nonce = nonce, at = now })
	while #list > 50 do
		table.remove(list, 1)
	end
	pcall(fs.writeDir, ".verify")
	pcall(fs.writeFile, Enforcer.EXEMPT_FILE, serde.encode("json", { schema = 1, tokens = list }, true))
	process.env.PARALLAX_EXEMPT = nonce
end
function Enforcer.exempt(): boolean
	local v = process.env.PARALLAX_EXEMPT
	if type(v) ~= "string" or #v < 32 then
		return false
	end
	local now = DateTime.now().unixTimestamp
	for _, e in ((readJson(Enforcer.EXEMPT_FILE) or {}).tokens or {}) :: { any } do
		if type(e) == "table" and e.nonce == v and type(e.at) == "number" and now - e.at < Enforcer.EXEMPT_TTL then
			return true
		end
	end
	return false
end

-- the session token and why it is not fresh -> (session?, problems)
function Enforcer.session(): (any?, { string })
	local s = readJson(Enforcer.SESSION)
	if not s then
		return nil, { "no .verify/parallax_session.json" }
	end
	local out = {}
	local started = iso(s.started_at)
	if not started then
		table.insert(out, "no started_at")
	elseif DateTime.now().unixTimestamp - started > (tonumber(s.ttl_seconds) or Enforcer.TTL) then
		table.insert(out, "expired (older than its ttl)")
	end
	if type(s.prompt_sha) ~= "string" or s.prompt_sha == "" then
		table.insert(out, "no prompt_sha")
	elseif not Enforcer.packetMatches(s.prompt_sha) then
		table.insert(out, `prompt_sha {s.prompt_sha} names no compiled PROMPT-X packet (a hand-written token)`)
	end
	local b = Enforcer.branch()
	if type(s.branch) == "string" and b and s.branch ~= b then
		table.insert(out, `made on branch {s.branch}, the checkout is on {b}`)
	end
	local g = Config.game()
	local sg = if type(s.game) == "string" and s.game ~= "" then s.game else nil
	if sg ~= g then
		table.insert(out, `made for game {sg or "none"}, the active game is {g or "none"}`)
	end
	return s, out
end

-- the lanes a session covers (its lane, its contracts' lanes; parallax / kit cover every lane)
function Enforcer.covers(s: any, lane: string?): boolean
	if lane == nil then
		return true
	end
	if s.lane == "parallax" or s.lane == "kit" or s.lane == lane then
		return true
	end
	for _, c in (s.case_contracts or {}) :: { any } do
		if c.lane == lane then
			return true
		end
	end
	for _, l in (s.lanes or {}) :: { any } do
		if l == lane or (l == "systems" and (lane == "code" or lane == "qa")) then
			return true
		end
	end
	return false
end

function Enforcer.contractFor(s: any?, lane: string?): any?
	for _, c in ((s and s.case_contracts) or {}) :: { any } do
		if lane == nil or c.lane == lane then
			return c
		end
	end
	return nil
end

-- the case's registry entry (kit/knowledge/cases/<lane>.json)
function Enforcer.case(caseId: string?): any?
	if type(caseId) ~= "string" then
		return nil
	end
	local lane = string.match(caseId, "^([^:]+):")
	local reg = lane and readJson(`kit/knowledge/cases/{lane}.json`)
	for _, c in ((reg and reg.cases) or {}) :: { any } do
		if c.case_id == caseId then
			return c
		end
	end
	return nil
end

local function forbiddenPatterns(contract: any?, case: any?): { string }
	local out = {}
	for _, f in ((contract and contract.forbidden_tools) or {}) :: { any } do
		table.insert(out, if type(f) == "table" then (f.pattern or f.id or "") else tostring(f))
	end
	for _, f in ((case and case.forbidden_tools) or {}) :: { any } do
		local p = if type(f) == "table" then (f.pattern or "") else tostring(f)
		if not table.find(out, p) then
			table.insert(out, p)
		end
	end
	return out
end

-- a tool's words name a forbidden route? -> the pattern
function Enforcer.forbids(text: string, patterns: { string }): string?
	local n = norm(text)
	for _, p in patterns do
		if p ~= "" and string.find(n, norm(p), 1, true) then
			return p
		end
	end
	return nil
end

-- take a flag (and its value) out of args -> its value (true when it has none), nil when absent
local function take(args: { string }, flag: string, valued: boolean): (string | boolean)?
	for i = #args, 1, -1 do
		if args[i] == flag then
			local v: string | boolean = true
			if valued then
				local nxt = args[i + 1]
				-- (a flag is never a hatch's value: `--maintenance --dry-run` keeps --dry-run and has no reason)
				if nxt ~= nil and string.sub(nxt, 1, 2) ~= "--" then
					v = nxt
					table.remove(args, i + 1)
				else
					v = ""
				end
			end
			table.remove(args, i)
			return v
		end
	end
	return nil
end

local function logTo(field: string, entry: any)
	local s = readJson(Enforcer.SESSION)
	if not s then
		return
	end
	local list = s[field] or {}
	table.insert(list, entry)
	s[field] = list
	fs.writeFile(Enforcer.SESSION, serde.encode("json", s, true))
end

-- the piece's plan -> (plan?, problems)
function Enforcer.plan(piece: string, lane: string?, skipped: { string }): (any?, { string })
	local path = `{Config.root()}{Enforcer.PLANS}/{piece}.plan.json`
	local p = readJson(path)
	if not p then
		return nil, { `no {path}` }
	end
	local out = {}
	if p.schema ~= 1 then
		table.insert(out, "schema must be 1")
	end
	if p.piece ~= piece then
		table.insert(out, `piece {tostring(p.piece)} is not {piece}`)
	end
	if lane and p.lane ~= lane then
		table.insert(out, `lane {tostring(p.lane)} is not {lane}`)
	end
	if type(p.revision) ~= "number" or p.revision < 1 then
		table.insert(out, "revision must be a number >= 1")
	end
	if type(p.part_or_beat_tools) ~= "table" or #p.part_or_beat_tools == 0 then
		table.insert(out, "part_or_beat_tools is empty (one row per part / beat: target, tools, why)")
	end
	if type(p.considered_and_skipped) ~= "table" then
		table.insert(out, "considered_and_skipped is missing (what of the menu was not needed, and why)")
	end
	if type(p.escalations) ~= "table" then
		table.insert(out, "escalations is missing ([] until a target is escalated)")
	end
	local case = Enforcer.case(p.case_id)
	if not case then
		table.insert(out, `case_id {tostring(p.case_id)} is not in kit/knowledge/cases/{lane or "?"}.json`)
	end
	local tools = {}
	for _, row in (if type(p.part_or_beat_tools) == "table" then p.part_or_beat_tools else {}) :: { any } do
		if type(row) ~= "table" or type(row.target) ~= "string" or type(row.tools) ~= "table" or #row.tools == 0 then
			table.insert(out, "a part_or_beat_tools row needs a target and tools")
			continue
		end
		for _, t in row.tools :: { any } do
			table.insert(tools, tostring(t))
		end
	end
	for _, e in (if type(p.escalations) == "table" then p.escalations else {}) :: { any } do
		for _, t in ((type(e) == "table" and e.tools) or {}) :: { any } do
			table.insert(tools, tostring(t))
		end
	end
	local banned = forbiddenPatterns(nil, case)
	for _, t in tools do
		local hit = Enforcer.forbids(t, banned)
		if hit then
			table.insert(out, `tool {t} is a route the case forbids ({hit})`)
		end
	end
	-- a v4 upgrade tool is mandatory only once it exists on disk (an unbuilt one never blocks P0)
	for _, u in ((case and case.v4_upgrade_tools) or {}) :: { any } do
		local upath = if type(u) == "table" then u.path else u
		if type(upath) == "string" and fs.isFile(upath) then
			local stem = string.match(upath, "([^/\\]+)%.%w+$") or upath
			local named = table.find(skipped, stem) or table.find(skipped, upath)
			for _, t in tools do
				if string.find(norm(t), norm(stem), 1, true) then
					named = 1
				end
			end
			if not named then
				table.insert(
					out,
					`the case's upgrade tool {upath} exists: the plan must use it (or --skip-tool {stem} --why "...")`
				)
			end
		end
	end
	return p, out
end

local function refuse(lines: { string }, nextAction: string): number?
	local mode = Enforcer.mode()
	for _, l in lines do
		print(`[parallax] {l}`)
	end
	print(`summary: REFUSED by the Parallax gate{if mode == "audit" then " (audit mode: running anyway)" else ""}`)
	print(`next_action: {nextAction}`)
	return if mode == "audit" then nil else Enforcer.CODE
end

-- the command's lane (nil = any lane the session has)
function Enforcer.laneOf(name: string, args: { string }): string?
	if name == "new" then
		return Enforcer.NEW_KIND[args[1] or ""]
	end
	local l = Enforcer.MUTATING[name]
	return if type(l) == "string" then l else nil
end

-- the gate (Cli.before): nil = run the command; a number = refused with that exit code
function Enforcer.check(name: string, args: { string }): number?
	if Enforcer.mode() == "off" or Enforcer.exempt() then
		return nil
	end
	if Enforcer.ALLOW[name] then
		-- (its own children - kit verify's gates, selftest's fixtures - run under it, never gated: Run.spawn passes the
		-- token it mints here)
		Enforcer.mintExempt()
		return nil
	end
	if Enforcer.MUTATING[name] == nil then
		return nil -- not a pipeline mutation (lint, test, refs, trace, ...): its args are its own (kit decide --why)
	end
	-- the escape hatches come out of a GATED command's args (that command never sees them)
	local maint = take(args, "--maintenance", true)
	local skipTool = take(args, "--skip-tool", true)
	local why = take(args, "--why", true)
	local sub = args[1]
	if (name == "asset" and sub == "all") or (sub and Enforcer.LOOKUP[sub]) then
		return nil
	end
	local now = DateTime.now():toIsoDate()
	if type(skipTool) == "string" then
		if type(why) ~= "string" or string.gsub(why, "%s", "") == "" then
			return refuse(
				{ `--skip-tool {skipTool} needs a reason: --why "<why this tool would hurt this piece>"` },
				`add --why "<reason>" (it is logged for the owner's review)`
			)
		end
	end
	if type(maint) == "string" or maint == true then
		local reason = if type(maint) == "string" then maint else ""
		if string.gsub(reason, "%s", "") == "" then
			return refuse(
				{ '--maintenance needs a reason: --maintenance "<why this is not pipeline work>"' },
				'add the reason: --maintenance "<why>"'
			)
		end
		logTo("maintenance", { at = now, command = name, args = args, why = reason })
		return nil
	end
	local lane = Enforcer.laneOf(name, args)
	local s, problems = Enforcer.session()
	local g = Config.game()
	local unlock = `lune run parallax start {lane or "<lane>"} --prompt "<the owner's request>" --game {g or "none"}`
	if #problems > 0 then
		return refuse({
			`{name} is pipeline work: it needs a Parallax session (PROMPT-X compiled for this request)`,
			`the session: {table.concat(problems, "; ")}`,
		}, unlock)
	end
	if not Enforcer.covers(s, lane) then
		return refuse({ `the session is for lane {tostring(s.lane)}; {name} is {lane} work` }, unlock)
	end
	local skipped = {}
	for _, e in (s.skipped_tools or {}) :: { any } do
		if type(e) == "table" and type(e.tool) == "string" then
			table.insert(skipped, e.tool)
		end
	end
	if type(skipTool) == "string" then
		table.insert(skipped, skipTool)
		logTo("skipped_tools", { at = now, command = name, tool = skipTool, why = why })
	end
	-- d. the command's own words against the case's forbidden routes
	local contract = Enforcer.contractFor(s, lane)
	local banned = forbiddenPatterns(contract, contract and Enforcer.case(contract.case_id))
	local hit = Enforcer.forbids(name .. " " .. table.concat(args, " "), banned)
	if hit and not table.find(skipped, hit) then
		return refuse(
			{ `{name} names {hit}: case {contract.case_id} forbids it (a graveyard route for this case)` },
			`take the case's route: lune run parallax case {lane or contract.lane} "<the request>"`
		)
	end
	-- c. a heavy build of a named piece needs its plan
	local heavy = Enforcer.HEAVY[name]
	local piece = if name == "gen" then args[1] else args[1]
	if heavy and type(piece) == "string" and string.sub(piece, 1, 2) ~= "--" and heavy(piece) then
		local _, planProblems = Enforcer.plan(piece, lane, skipped)
		if #planProblems > 0 then
			return refuse(
				{
					`{name} {piece} is a heavy build: it needs {Config.root()}{Enforcer.PLANS}/{piece}.plan.json first (tools per part / beat from the {lane} capability menu, after the refs)`,
					`the plan: {table.concat(planProblems, "; ")}`,
				},
				`lune run parallax case {lane} "<the request>" (the menu), then write {Enforcer.PLANS}/{piece}.plan.json`
			)
		end
	end
	return nil
end

-- after a command: a passing `verify` and a written `handoff` are stamped on the session (the Stop hook then stays
-- quiet: kit/scripts/parallax_guard.py --hook stop reminds only dirty, unproven, un-handed-off work)
function Enforcer.after(name: string, code: number)
	if code ~= 0 or (name ~= "verify" and name ~= "handoff" and name ~= "prove") then
		return
	end
	local s = readJson(Enforcer.SESSION)
	if not s then
		return
	end
	s[if name == "handoff" then "handoff_written_at" else "verify_passed_at"] = DateTime.now():toIsoDate()
	pcall(fs.writeFile, Enforcer.SESSION, serde.encode("json", s, true))
end

-- Cli.before: the vault page first (never blocks), then the gate
function Enforcer.before(name: string, args: { string }): number?
	pcall(VaultGate.before, name, args)
	return Enforcer.check(name, args)
end

return Enforcer

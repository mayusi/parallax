-- qa.luau — QA tester pipeline: security audit, gate self-test, and Studio playtests driven through Studio MCP.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Audit = require("../lib/audit")
local Board = require("../lib/board")
local Config = require("../lib/config")
local Mcp = require("../lib/mcp")
local Moderation = require("../lib/moderation")
local PlaytestPlace = require("../lib/playtestplace")
local Run = require("../lib/run")
local SelftestCache = require("../lib/selftestcache")
local task = require("@lune/task")

local C = Run.CODES
local Qa = {}

-- ---------------------------------------------------------------- audit
local function luauFiles(dir: string, out: { string })
	if not fs.isDir(dir) then
		return
	end
	for _, name in fs.readDir(dir) do
		local path = dir .. "/" .. name
		if fs.isDir(path) then
			if name ~= "Packages" and name ~= "DevPackages" and name ~= "node_modules" then
				luauFiles(path, out)
			end
		elseif string.match(name, "%.luau?$") then
			table.insert(out, path)
		end
	end
end

function Qa.scanAll(): { Audit.Finding }
	local files = {}
	luauFiles(Config.path("source"), files)
	table.sort(files)
	local ignore = {}
	for _, entry in Config.load().qa.auditIgnore or {} do
		ignore[entry] = true
	end
	local findings = {}
	for _, file in files do
		local isClient = string.find(file, "%.client%.luau?$") ~= nil
		for _, f in Audit.scan(file, fs.readFile(file), not isClient) do
			if not ignore[file] and not ignore[`{file}:{f.line}`] and not ignore[`{file}:{f.rule}`] then
				table.insert(findings, f)
			end
		end
	end
	return findings
end

function Qa.auditStep(): Run.Step
	local findings = Qa.scanAll()
	local errors, warns, lines = 0, 0, {}
	for _, f in findings do
		if f.severity == "error" then
			errors += 1
		else
			warns += 1
		end
		table.insert(lines, `[{f.severity}] {f.file}:{f.line} {f.rule}: {f.message} — fix: {f.fix}`)
	end
	local first
	for _, f in findings do
		if f.severity == "error" then
			first = f
			break
		end
	end
	return Run.step("audit", errors == 0, table.concat(lines, "\n"), {
		summary = `{errors} security error(s), {warns} warning(s)`,
		next_action = if first
			then `{first.file}:{first.line} {first.message} — {first.fix} (accepted risk? add "{first.file}:{first.line}" to qa.auditIgnore in kit.config.json)`
			else nil,
		findings = findings,
	})
end

-- ---------------------------------------------------------------- playtest
local function scenarios(): { [string]: string }
	local out = { smoke = "kit/qa/smoke.luau" }
	local dir = Config.path("playtests")
	if fs.isDir(dir) then
		for _, f in fs.readDir(dir) do
			local n = string.match(f, "^(.+)%.luau$")
			if n then
				out[n] = dir .. "/" .. f
			end
		end
	end
	return out
end

-- the harness's BUDGET line from kit.config.json's qa.perf (a key a project's config leaves out: the kit's default)
function Qa.budgetLine(b: any): string
	local function n(v: any, default: number): number
		return if type(v) == "number" then v else default
	end
	return string.format(
		"local BUDGET = { memoryMb = %s, instances = %s, frameMs = %s, clientMemoryMb = %s, highlights = %s, "
			.. "shadowLights = %s, shadowRadius = %s }",
		tostring(n(b.memoryMb, 1500)),
		tostring(n(b.instances, 60000)),
		tostring(n(b.heartbeatMs, 20)),
		tostring(n(b.clientMemoryMb, 1100)),
		tostring(n(b.highlights, 31)),
		tostring(n(b.shadowLights, 16)),
		tostring(n(b.shadowRadius, 120))
	)
end

function Qa.bundle(name: string): (string?, string?, string?)
	local path = scenarios()[name]
	if not path then
		return nil, nil, `no scenario "{name}" (kit built-in: smoke; yours: {Config.path("playtests")}/<name>.luau)`
	end
	local src = fs.readFile(path)
	local side = string.match(src, "^%-%- runs on: (%a+)") or "Server"
	if side ~= "Server" and side ~= "Client" then
		return nil, nil, `{path}: first line must be "-- runs on: Server" or "-- runs on: Client"`
	end
	local b = Config.load().qa.perf
	local harness = fs.readFile("kit/qa/harness.luau")
	local out = {}
	for line in string.gmatch(harness .. "\n", "([^\n]*)\n") do
		if string.find(line, "-- @kit:name", 1, true) then
			table.insert(out, `local SCENARIO = "{name}"`)
		elseif string.find(line, "-- @kit:budget", 1, true) then
			table.insert(out, Qa.budgetLine(b))
		elseif string.find(line, "-- @kit:scenario", 1, true) then
			table.insert(out, src)
		else
			table.insert(out, line)
		end
	end
	return table.concat(out, "\n"), side, nil
end

-- `kit playtest run <name>`: the kit drives Studio itself through StudioMCP.exe (kit/lib/mcp.luau): bundle the
-- scenario, find THIS game's Studio (a shared Studio running another place is never touched: --studio <id> names
-- one), start play, run the scenario in its datamodel, read the console, stop, write build/playtests/<name>/
-- {result.json, console.log}, and grade it like `record` — any console error OR warning fails, with its line.
function Qa.run(name: string?, args: { string }): number
	local function fail(msg: string, nxt: string): number
		return Run.report("playtest", {}, C.PLAYTEST, `playtest run: {msg}`, nxt)
	end
	if not name then
		return Run.report("playtest", {}, C.USAGE, "playtest run: needs a scenario name", "lune run kit playtest list")
	end
	local code, side, err = Qa.bundle(name)
	if not code or not side then
		return fail(tostring(err), "lune run kit playtest list")
	end
	local studio, cerr = Mcp.connect()
	if not studio then
		return fail(tostring(cerr), "open Roblox Studio (its MCP server ships with it)")
	end
	local function done(n: number): number
		studio:close()
		return n
	end
	local okL, list = studio:call("list_roblox_studios", {}, 20)
	local okJ, found = pcall(serde.decode, "json" :: any, list)
	local studios = if okL and okJ and type(found) == "table" then found.studios or {} else {}
	local wanted = nil
	for i, a in args do
		if a == "--studio" then
			wanted = args[i + 1]
		end
	end
	local game = Config.game()
	local pick = nil
	for _, st in studios do
		if
			(wanted and st.id == wanted)
			or (not wanted and game and string.find(string.lower(st.name or ""), string.lower(game), 1, true))
		then
			pick = st
		end
	end
	if not pick then
		local names = {}
		for _, st in studios do
			table.insert(names, `{st.name} ({st.id})`)
		end
		return done(
			fail(
				`no Studio open on {game or "this game"} (open: {if #names > 0
					then table.concat(names, ", ")
					else "none"})`,
				`build the place: lune run kit playtest place (the project + its fixtures), open it in Studio, then pass --studio <id> (or rojo serve the project + connect Studio)`
			)
		)
	end
	local id = pick.id
	local _, state = studio:call("get_studio_state", { studio_id = id }, 20)
	if string.find(string.lower(state), "play", 1, true) and not string.find(string.lower(state), "edit", 1, true) then
		return done(fail(`{pick.name} is already in play (someone else's run?)`, "stop it in Studio, then run again"))
	end
	local okS, sres = studio:call("start_stop_play", { is_start = true, studio_id = id }, 60)
	if not okS then
		return done(fail(`could not start play: {sres}`, "check Studio"))
	end
	-- wait for the datamodel the scenario runs in
	local ready = false
	for _ = 1, 30 do
		local _, st = studio:call("get_studio_state", { studio_id = id }, 10)
		if string.find(st, side, 1, true) then
			ready = true
			break
		end
		task.wait(1)
	end
	local result, console = "", ""
	if ready then
		local _, r = studio:call("execute_luau", { code = code, datamodel_type = side, studio_id = id }, 180)
		result = r
	end
	local _, con = studio:call("get_console_output", { studio_id = id }, 30)
	console = con
	studio:call("start_stop_play", { is_start = false, studio_id = id }, 60)
	studio:close()
	local dir = `{Config.build("playtests")}/{name}`
	Config.ensureDir(dir)
	fs.writeFile(`{dir}/console.log`, console)
	if not ready then
		return fail(`the {side} datamodel never appeared`, `read {dir}/console.log`)
	end
	-- the scenario's own JSON, with the console's problems added: any error or warning fails the run
	local raw = string.gsub(result, "^%s+", "")
	if string.sub(raw, 1, 1) == '"' then
		local okU, unq = pcall(serde.decode, "json" :: any, raw)
		raw = if okU then unq else raw
	end
	local okR, res = pcall(serde.decode, "json" :: any, raw)
	if not okR or type(res) ~= "table" then
		res = { checks = {}, errors = { `the scenario returned no result: {string.sub(result, 1, 300)}` } }
	end
	res.errors = res.errors or {}
	local errs, warns = Mcp.consoleProblems(console)
	for _, e in errs do
		table.insert(res.errors, "console error: " .. e)
	end
	for _, w in warns do
		table.insert(res.errors, "console warning: " .. w)
	end
	res.console = { errors = #errs, warnings = #warns, file = `{dir}/console.log` }
	fs.writeFile(`{dir}/result.json`, serde.encode("json", res, true))
	return Qa.playtest({ "record", name, `{dir}/result.json` })
end

-- the accept ratchet for every kind but 3D (kit/qa/accept.luau): `kit accept <kind> <name> ["words"] [--lower]`
function Qa.accept(rawArgs: { string }): number
	local Accept = require("../qa/accept")
	local Owner = require("../lib/owner")
	local kind, name = rawArgs[1], rawArgs[2]
	local words, lower = {}, false
	for i = 3, #rawArgs do
		if rawArgs[i] == "--lower" then
			lower = true
		else
			table.insert(words, rawArgs[i])
		end
	end
	-- a system's floor is its game's; every other piece lives in the active game (or the project)
	local root = if kind == "system" then `games/{name}/` else Config.root()
	local ok, summary, nextAction = Accept.accept(
		kind,
		name,
		root,
		table.concat(words, " "),
		lower,
		Accept.worldCheck(Run.tool("python")),
		Owner.confirm
	)
	if ok then
		Board.journal(Board.agent(nil), summary)
	end
	return Run.report("accept", {}, if ok then C.PASS else C.USAGE, summary, nextAction)
end

-- verify: every accepted floor (project + every game) re-measured; one below its floor past tolerance fails
function Qa.floorsStep(): Run.Step
	local Accept = require("../qa/accept")
	local ok, lines, summary = Accept.checkAll(Accept.worldCheck(Run.tool("python")))
	return Run.step("floors", ok, table.concat(lines, "\n"), {
		summary = summary,
		next_action = if ok
			then nil
			else "a piece measures below the floor the owner accepted: fix the build (never the floor); only the owner lowers one (kit accept <kind> <name> --lower)",
	})
end

-- verify: size / shape guards on every game's code (WARNINGS: a long service, a long function, a require cycle)
function Qa.shapeStep(): Run.Step
	local Shape = require("../qa/shape")
	local findings = Shape.scanAll()
	local detail = {}
	for i = 1, math.min(#findings, 12) do
		local f = findings[i]
		table.insert(detail, `{f.path}:{f.line}: {f.message}`)
	end
	return Run.step("shape", true, table.concat(detail, "\n"), {
		summary = if #findings == 0
			then "every game's services <= 600 lines, functions <= 80, no require cycles"
			else `{#findings} shape warning(s)`,
		next_action = if #findings == 0 then nil else `improve: {detail[1]}`,
	})
end

function Qa.register(Cli: any, Content: any)
	Cli.command("qa", "audit", "audit", "security audit of every remote handler + backdoor patterns in src/", function()
		local step = Qa.auditStep()
		print(step.tail)
		-- THE MODERATION GATE over what the next `kit upload` would send (kit/lib/moderation.luau: blood and gore get the uploading account moderated):
		-- a held file is said here, as a warning - `kit upload` is where it is STOPPED (nothing held ever leaves)
		local items = Moderation.pending()
		local verdicts, err = Moderation.screen(items)
		local held = {}
		for _, v in verdicts or {} do
			if v.held then
				table.insert(held, `{v.file}: {table.concat(v.why, "; ")}`)
				print(`[warn] moderation: {v.file} would be HELD by kit upload: {table.concat(v.why, "; ")}`)
			end
		end
		if not verdicts then
			print(`[warn] moderation: could not screen the next upload ({err})`)
		end
		local said = if not verdicts
			then "; moderation: not screened"
			elseif #held > 0 then `; moderation: {#held} of {#items} file(s) the next upload would send are HELD`
			else `; moderation: {#items} pending file(s) clean`
		return Run.chain("audit", {
			function()
				return step
			end,
		}, function()
			return C.LINT
		end, `audit: {step.result.summary}{said}`)
	end)

	Cli.command(
		"qa",
		"playtest",
		"playtest list|place|bundle <name>|run <name> [--studio <id>]|record <name> <file>",
		"in-engine scenarios run through Studio MCP (any harness)",
		function(args)
			return Qa.playtest(args)
		end
	)
	Qa.playtest = function(args)
		local sub, name = args[1], args[2]
		if sub == "place" then
			-- the place a playtest runs in: the game's project + the playtests' fixtures (kit/lib/playtestplace.luau)
			local step, place = PlaytestPlace.build()
			return Run.report(
				"playtest",
				{ step },
				if step.ok then C.PASS else C.PLAYTEST,
				if step.ok then step.result.summary else `playtest place: {step.tail}`,
				if step.ok
					then `open {place} in Roblox Studio as its own window (RobloxStudioBeta.exe "<its full path>"), then: lune run kit playtest run <name> --studio <its id>`
					else "read the rojo output above"
			)
		end
		if sub == "list" or sub == nil then
			local names = {}
			for n, p in scenarios() do
				table.insert(names, `{n} ({p})`)
			end
			table.sort(names)
			print(table.concat(names, "\n"))
			return Run.report("playtest", {}, C.PASS, `{#names} scenario(s)`, "lune run kit playtest bundle <name>")
		end
		if sub == "bundle" then
			if not name then
				return Run.report(
					"playtest",
					{},
					C.USAGE,
					"playtest bundle: needs a scenario name",
					"lune run kit playtest bundle smoke"
				)
			end
			local code, side, err = Qa.bundle(name)
			if not code then
				return Run.report("playtest", {}, C.USAGE, "playtest: " .. tostring(err), "lune run kit playtest list")
			end
			local dir = Config.build("playtest")
			Config.ensureDir(dir)
			local file = `{dir}/{name}.luau`
			fs.writeFile(file, code :: string)
			print(`bundled {file} ({#(code :: string)} bytes, runs on {side})\n`)
			print("Run it with the Roblox Studio MCP tools (Studio open, Rojo synced):")
			print("  1. start_stop_play  is_start=true")
			print(`  2. execute_luau     datamodel_type="{side}"  code=<the full contents of {file}>`)
			print(`  3. save the JSON string it returns to {dir}/{name}.result.json`)
			print("  4. start_stop_play  is_start=false")
			print(`  5. lune run kit playtest record {name} {dir}/{name}.result.json`)
			print("  (also skim get_console_output for errors while it runs)\n")
			return Run.report(
				"playtest",
				{},
				C.PASS,
				`playtest {name} bundled for the {side} datamodel`,
				`run steps 1-5 above, then: lune run kit playtest record {name} {dir}/{name}.result.json`
			)
		end
		if sub == "run" then
			return Qa.run(name, args)
		end
		if sub == "record" then
			local file = args[3]
			if not name or not file or not fs.isFile(file) then
				return Run.report(
					"playtest",
					{},
					C.USAGE,
					"playtest record: needs a name and the saved result file",
					`lune run kit playtest record smoke {Config.build("playtest")}/smoke.result.json`
				)
			end
			local raw = fs.readFile(file)
			raw = string.gsub(raw, "^%s+", "")
			-- tolerate the MCP tool wrapping the JSON string in quotes
			if string.sub(raw, 1, 1) == '"' then
				local okUnq, unq = pcall(serde.decode, "json" :: any, raw)
				raw = if okUnq then unq else raw
			end
			local ok, result = pcall(serde.decode, "json" :: any, raw)
			if not ok or type(result) ~= "table" or not result.checks then
				return Run.report(
					`playtest-{name}`,
					{},
					C.USAGE,
					"playtest record: file is not a playtest result",
					"save exactly the string execute_luau returned"
				)
			end
			local failed, firstFix = {}, nil
			for _, c in result.checks do
				if not c.ok then
					table.insert(failed, c.name .. (if c.detail then ` ({c.detail})` else ""))
					firstFix = firstFix or (if c.fix then `{c.name} → {c.fix}` else nil)
				end
			end
			for _, e in result.errors or {} do
				table.insert(failed, "error: " .. e)
			end
			local passed = #failed == 0
			local lines = {}
			for _, c in result.checks do
				table.insert(lines, `[{if c.ok then "ok" else "FAIL"}] {c.name}`)
			end
			print(table.concat(lines, "\n"))
			Board.journal(
				Board.agent(nil),
				`playtest {name}: {if passed then "pass" else "FAIL"} ({#result.checks} checks)`
			)
			-- the result reaches the QA lane's record (2026-11-08, sprint 4: it stayed in build/): one note per playtest
			local okChecks = 0
			for _, c in result.checks do
				okChecks += if c.ok then 1 else 0
			end
			local okNote, notePath =
				pcall(require("../lib/playtests").record, name, passed, okChecks, #result.checks, failed, result.perf)
			if okNote then
				print(`playtest {name}: its vault note - {notePath}`)
			end
			-- a FAILURE is the start of a regression case (LIMITATIONS_FIXES_V4 8.3: "emitting ready kit bug scaffolds on
			-- failure"): once the fault is fixed, `kit bug` keeps it - proven by planting it back - in tests/regressions.json
			if not passed then
				local what = string.gsub(string.sub(tostring(failed[1] or "a check failed"), 1, 90), '"', "'")
				print(
					`playtest {name}: once it is fixed, keep it as a regression case - lune run kit bug "playtest {name}: {what}" `
						.. "--spec tests/<the spec that now catches it>.spec.luau --module src/shared/<the module fixed>.luau "
						.. `--line "<a unique piece of the fixed line>" --from "<as it is now>" --to "<the bug>" --found-by "kit playtest {name}"`
				)
			end
			local step = Run.step(
				`playtest {name}`,
				passed,
				table.concat(failed, "\n"),
				{ summary = `{#result.checks} check(s), {#failed} failed`, perf = result.perf }
			)
			return Run.report(
				`playtest-{name}`,
				{ step },
				if passed then C.PASS else C.PLAYTEST,
				`playtest {name}: {#result.checks - #failed}/{#result.checks} checks pass`
					.. (
						if result.perf and result.perf.memoryMb
							then ` · {result.perf.memoryMb} MB · {result.perf.frameMs} ms/frame`
							else ""
					),
				if passed then "none — proceed" else "fix: " .. (firstFix or failed[1])
			)
		end
		return Run.report("playtest", {}, C.USAGE, `playtest: unknown subcommand "{sub}"`, "lune run kit playtest list")
	end

	-- ---------------------------------------------------------------- selftest: prove every gate bites
	-- needles: every one must appear in the verdict summary, so the fixture is caught for the RIGHT reason
	local function expectFail(label: string, make: () -> Run.Step, needles: { string }?): () -> Run.Step
		return function()
			Run.expectingFailure = true
			local step = make()
			Run.expectingFailure = false
			local caught = not step.ok and step.exit ~= 127 and step.result ~= nil and step.result.status == "fail"
			for _, needle in needles or {} do
				caught = caught and string.find(tostring(step.result.summary), needle, 1, true) ~= nil
			end
			print(
				if caught
					then `[caught] {label}: {step.result.summary}`
					else `[MISSED] {label} — the gate accepted a bad fixture`
			)
			return {
				name = label,
				cmd = step.cmd,
				exit = if caught then 0 else 1,
				ok = caught,
				tail = if caught
					then "caught: " .. tostring(step.result.summary)
					else "GATE DID NOT CATCH IT: " .. step.tail,
				result = if caught
					then nil
					else {
						next_action = `the {label} gate let a bad fixture through — fix the gate, never the fixture`,
					},
			}
		end
	end

	-- a build that must STOP on a mistake in its script (no verdict: the script raised): caught when it failed and
	-- its last lines say why
	local function expectStop(label: string, make: () -> Run.Step, needles: { string }): () -> Run.Step
		return function()
			Run.expectingFailure = true
			local step = make()
			Run.expectingFailure = false
			-- (a build that crashed carries a result with no status: only its next_action - Run.content)
			local caught = not step.ok and step.exit ~= 127 and (step.result == nil or step.result.status == nil)
			for _, needle in needles do
				caught = caught and string.find(tostring(step.tail), needle, 1, true) ~= nil
			end
			print(if caught then `[caught] {label}` else `[MISSED] {label} - the build did not stop, or not for this`)
			return {
				name = label,
				cmd = step.cmd,
				exit = if caught then 0 else 1,
				ok = caught,
				tail = if caught then "caught: the build stopped" else "THE BUILD DID NOT STOP FOR IT: " .. step.tail,
				result = if caught
					then nil
					else {
						next_action = `{label}: the build must stop and say why - fix the build, never the fixture`,
					},
			}
		end
	end

	-- a lock's answer as a step whose summary IS the problem (so a needle can ask for the reason, not only the name)
	local function lockStep(name: string, problem: string?): Run.Step
		return Run.step(name, problem == nil, problem or "", {
			status = if problem then "fail" else "pass",
			summary = problem or "the quality steps hold",
			next_action = problem or "none — proceed",
		})
	end

	-- the 3D STAGE approvals on a copy of the fixture project (kit/selftest/sheet -> build/selftest/stages): its model
	-- sheet drawn there and the owner's yes for THAT sheet in a locks file of the fixture's own. `mode` "full" = a
	-- baked build (it also needs the blockout's approval), "geo" = a shape round (it does not)
	local function stageFixture(mode: string): Run.Step
		local process = require("@lune/process")
		local LaneLocks = require("../lib/lanelocks")
		local Locks = require("../lib/locks")
		local proj = Config.build("selftest/stages")
		if fs.isDir(proj) then
			fs.removeDir(proj)
		end
		fs.writeDir(Config.build("selftest"))
		fs.copy("kit/selftest/sheet", proj, true)
		local models = proj .. "/assets/models"
		process.exec(Run.tool("python"), { "kit/tools/sheet.py", "sheetgun", "--root", proj })
		local sheet = LaneLocks.stageState("sheetgun", "sheet", models)
		if not sheet.ok then
			return lockStep(
				`stage approvals {mode} (selftest)`,
				`the fixture's own sheet could not be drawn: {sheet.why}`
			)
		end
		local yes = { by = "owner", words = "the fixture's own yes", date = "2026-11-11" }
		local real = Locks.FILE
		Locks.FILE = proj .. "/locks.json"
		fs.writeFile(
			Locks.FILE,
			serde.encode("json", {
				grandfathered = {},
				approvals = { ["3d"] = { sheetgun = yes } },
				waivers = {
					["3d"] = { sheetgun = { by = "owner", words = "a fixture", steps = { "study", "verdict" } } },
				},
				stages = {
					["3d"] = {
						sheetgun = { sheet = { by = "owner", words = "yes", date = "2026-11-11", id = sheet.id } },
					},
				},
			})
		)
		Locks.reset()
		local ok, problem = pcall(LaneLocks.asset, "sheetgun", nil, models, nil, mode)
		Locks.FILE = real
		Locks.reset()
		return lockStep(
			`stage approvals {mode} (selftest)`,
			if ok then problem else `the lock crashed: {tostring(problem)}`
		)
	end

	-- the deep per-part gates WARN on props (they fail hero/aaa builds): pass or fail, the verdict must NAME each
	-- defect — the fixture is caught for the right reason, whatever else is wrong with a test box
	local function expectFlag(label: string, make: () -> Run.Step, needles: { string }): () -> Run.Step
		return function()
			Run.expectingFailure = true
			local step = make()
			Run.expectingFailure = false
			local summary = if step.result then tostring(step.result.summary) else ""
			local missing = {}
			for _, needle in needles do
				if not string.find(summary, needle, 1, true) then
					table.insert(missing, needle)
				end
			end
			local caught = step.exit ~= 127 and step.result ~= nil and #missing == 0
			print(
				if caught
					then `[caught] {label}: {table.concat(needles, ", ")}`
					else `[MISSED] {label} — not named: {table.concat(missing, ", ")}`
			)
			return {
				name = label,
				cmd = step.cmd,
				exit = if caught then 0 else 1,
				ok = caught,
				tail = if caught
					then "caught: " .. table.concat(needles, ", ")
					else "GATE DID NOT NAME: " .. table.concat(missing, ", ") .. " — " .. (if summary ~= ""
						then summary
						else step.tail),
				result = if caught
					then nil
					else {
						next_action = `the {label} gate let a bad fixture through — fix the gate, never the fixture`,
					},
			}
		end
	end

	-- a CORRECT fixture must pass and must NOT be flagged: a check that flags a correct model is as broken as one that
	-- misses a wrong one
	local function expectClean(label: string, make: () -> Run.Step, forbidden: { string }): () -> Run.Step
		return function()
			Run.expectingFailure = true
			local step = make()
			Run.expectingFailure = false
			local summary = if step.result then tostring(step.result.summary) else ""
			local found = {}
			for _, needle in forbidden do
				if string.find(summary, needle, 1, true) then
					table.insert(found, needle)
				end
			end
			local clean = step.ok and step.result ~= nil and #found == 0
			print(
				if clean
					then `[ok] {label}: {summary}`
					else `[MISSED] {label} — flagged a correct fixture: {table.concat(found, ", ")} {summary}`
			)
			return {
				name = label,
				cmd = step.cmd,
				exit = if clean then 0 else 1,
				ok = clean,
				tail = if clean then "clean: " .. summary else "FLAGGED A CORRECT FIXTURE: " .. summary,
				result = if clean
					then nil
					else {
						next_action = `the {label} check flags a CORRECT fixture — fix the check, never the fixture`,
					},
			}
		end
	end

	-- the SCORE must rank fixtures the way an artist would: `better` above every one of `worse` (taste can be tested:
	-- real boards above the same box carved with grooves, above the same boards in flat paint)
	local function expectOrder(label: string, better: () -> Run.Step, worse: { () -> Run.Step }): () -> Run.Step
		return function()
			local function score(make: () -> Run.Step): (number?, Run.Step)
				Run.expectingFailure = true
				local step = make()
				Run.expectingFailure = false
				local q = step.result and step.result.facts and step.result.facts.quality
				return (if q and type(q.score) == "number" then q.score else nil), step
			end
			local top, topStep = score(better)
			local lines, wrong = {}, {}
			for _, make in worse do
				local s, step = score(make)
				local name = step.name
				table.insert(lines, `{name} {s or "?"}`)
				if top == nil or s == nil or s >= top then
					table.insert(wrong, name)
				end
			end
			local ok = top ~= nil and #wrong == 0
			local said = `{topStep.name} {top or "?"} > {table.concat(lines, ", ")}`
			print(if ok then `[ok] {label}: {said}` else `[MISSED] {label} — {said}`)
			return {
				name = label,
				cmd = topStep.cmd,
				exit = if ok then 0 else 1,
				ok = ok,
				tail = if ok then "ranked: " .. said else "RANKED WRONG: " .. said,
				result = if ok
					then nil
					else {
						next_action = `the score ranks {table.concat(wrong, ", ")} at or above {topStep.name} — fix the score (rbx_quality), never the fixtures`,
					},
			}
		end
	end

	-- a CORRECT detail must not be named as a defect, whatever else the fixture is judged for (a wooden ladder's wide
	-- openings are not see-through slits): the build must run, and none of `forbidden` may appear in its summary
	local function expectSpared(label: string, make: () -> Run.Step, forbidden: { string }): () -> Run.Step
		return function()
			Run.expectingFailure = true
			local step = make()
			Run.expectingFailure = false
			local summary = if step.result then tostring(step.result.summary) else ""
			local found = {}
			for _, needle in forbidden do
				if string.find(summary, needle, 1, true) then
					table.insert(found, needle)
				end
			end
			-- the build must have RUN and judged (its own JSON verdict carries a status): a crash names nothing either
			local judged = step.exit ~= 127 and step.result ~= nil and step.result.status ~= nil
			local spared = judged and #found == 0
			print(
				if spared
					then `[ok] {label}: not named {table.concat(forbidden, ", ")}`
					else if not judged
						then `[MISSED] {label} — the fixture never produced a verdict (crashed?): {step.tail}`
						else `[MISSED] {label} — named a correct detail: {table.concat(found, ", ")} {summary}`
			)
			return {
				name = label,
				cmd = step.cmd,
				exit = if spared then 0 else 1,
				ok = spared,
				tail = if spared
					then "spared: " .. table.concat(forbidden, ", ")
					else "NAMED A CORRECT DETAIL: " .. summary,
				result = if spared
					then nil
					else {
						next_action = `the {label} check names a CORRECT fixture — fix the check, never the fixture`,
					},
			}
		end
	end

	-- what the score SEES must be right, not only its total: measure `fact` (facts.quality.measures) of `high` must exceed
	-- the same measure of `low` by `margin` (flat paint reads EMPTY where the same boards with grain do not)
	local function expectMore(
		label: string,
		high: () -> Run.Step,
		low: () -> Run.Step,
		fact: string,
		margin: number
	): () -> Run.Step
		return function()
			local function measure(make: () -> Run.Step): (number?, Run.Step)
				Run.expectingFailure = true
				local step = make()
				Run.expectingFailure = false
				local q = step.result and step.result.facts and step.result.facts.quality
				local v = q and q.measures and q.measures[fact]
				return (if type(v) == "number" then v else nil), step
			end
			local hi, hiStep = measure(high)
			local lo, loStep = measure(low)
			local ok = hi ~= nil and lo ~= nil and hi >= lo + margin
			local said = `{fact}: {hiStep.name} {hi or "?"} vs {loStep.name} {lo or "?"} (needs +{margin})`
			print(if ok then `[ok] {label}: {said}` else `[MISSED] {label} — {said}`)
			return {
				name = label,
				cmd = hiStep.cmd,
				exit = if ok then 0 else 1,
				ok = ok,
				tail = if ok then "measured: " .. said else "MEASURED WRONG: " .. said,
				result = if ok
					then nil
					else {
						next_action = `the score measures {fact} wrong ({said}) — fix the measure (rbx_quality / rbx_image), never the fixtures`,
					},
			}
		end
	end

	-- a sloppy-but-legal fixture must PASS and still name every warning in its summary
	local function expectWarn(label: string, make: () -> Run.Step, needles: { string }): () -> Run.Step
		return function()
			Run.expectingFailure = true
			local step = make()
			Run.expectingFailure = false
			local summary = if step.result then tostring(step.result.summary) else step.tail
			local missing = {}
			for _, needle in needles do
				if not string.find(summary, needle, 1, true) then
					table.insert(missing, needle)
				end
			end
			local caught = step.ok and #missing == 0
			print(
				if caught
					then `[caught] {label}: {summary}`
					else `[MISSED] {label} — not warned: {table.concat(missing, ", ")}`
			)
			return {
				name = label,
				cmd = step.cmd,
				exit = if caught then 0 else 1,
				ok = caught,
				tail = if caught then "caught: " .. summary else "WARNINGS MISSING: " .. table.concat(missing, ", "),
				result = if caught
					then nil
					else {
						next_action = `the {label} check let a sloppy fixture through — fix the check, never the fixture`,
					},
			}
		end
	end

	-- every case the helpers above make carries its LABEL (its first word names its lane: "3d ...", "vfx ...") for
	-- `kit selftest --lane / --changed` and the content-hash cache (kit/lib/selftestcache.luau)
	local caseLabel: { [any]: string } = setmetatable({}, { __mode = "k" }) :: any
	local function labelling(helper: any): any
		return function(label: string, ...)
			local fn = helper(label, ...)
			caseLabel[fn] = label
			return fn
		end
	end
	expectFail = labelling(expectFail)
	expectStop = labelling(expectStop)
	expectFlag = labelling(expectFlag)
	expectClean = labelling(expectClean)
	expectOrder = labelling(expectOrder)
	expectSpared = labelling(expectSpared)
	expectMore = labelling(expectMore)
	expectWarn = labelling(expectWarn)

	Cli.command(
		"qa",
		"selftest",
		"selftest [--lane <3d|vfx|anim|world|ui|sfx|kit>[,...]] [--changed] [--no-cache | --cache]",
		"feed every content gate a bad fixture; pass = all were caught (--lane / --changed: only those lanes' cases; a case green at the same inputs is reused from .verify/selftest_cache.json unless --no-cache - the cold proof; off by default in a linked worktree such as kit prove's sandbox)",
		function(selftestArgs)
			-- a fixture is built ONCE per selftest run: several checks read the same build (the planks are ranked, flagged
			-- and measured), and a rebuild would only repeat the same deterministic result
			local fixtureBuilds: { [string]: Run.Step } = {}
			local function fixture(name: string): () -> Run.Step
				return function()
					if not fixtureBuilds[name] then
						-- the fixtures that find a piece's traces by name write them where a build looks for them,
						-- assets/models/ - which a fresh clone of the kit (git keeps no empty folder) has not made yet
						Config.ensureDir("assets/models")
						fixtureBuilds[name] =
							Content.blenderStep(name, `kit/selftest/blender/build_{name}.py`, { "--no-preview" })
					end
					return fixtureBuilds[name]
				end
			end
			-- a master fixture built as its GAME version (kit optimize: --optimize, an optional --budget=)
			local function optimized(name: string, extra: { string }?): () -> Run.Step
				local key = name .. " --optimize " .. table.concat(extra or {}, " ")
				return function()
					-- (its maps are the MASTER's, transferred: the master fixture is built first — for its files; its own
					-- verdict is not this check's, and a master that never got made fails the game build by name)
					fixture(name)()
					if not fixtureBuilds[key] then
						local args = { "--no-preview", "--optimize" }
						for _, a in extra or {} do
							table.insert(args, a)
						end
						fixtureBuilds[key] = Content.blenderStep(key, `kit/selftest/blender/build_{name}.py`, args)
					end
					return fixtureBuilds[key]
				end
			end
			-- a fixture built AGAIN with only its wear numbers changed (--more-dirt): the first build's passes are kept
			-- beside its bake cache, the second must read them (the first is built first - for its passes; its own
			-- verdict is not this check's)
			local function moreDirt(name: string): () -> Run.Step
				local key = name .. " --more-dirt"
				return function()
					fixture(name)()
					if not fixtureBuilds[key] then
						fixtureBuilds[key] = Content.blenderStep(
							key,
							`kit/selftest/blender/build_{name}.py`,
							{ "--no-preview", "--more-dirt" }
						)
					end
					return fixtureBuilds[key]
				end
			end
			-- game_fidelity on a real master and its game version (the skull: kit optimize human_skull): the transferred
			-- maps must pass, the old re-derived maps (swapped onto the same game mesh) must be caught. Without both
			-- builds the selftest SAYS it skipped them
			-- the car rim's S1 (kit/selftest/blender/game_fidelity/rim_s1: its low, its high, the low's colour + normal
			-- maps): againstHigh = the low against its own high (the high-and-low route: must FAIL up close), else the
			-- low against itself (must PASS: nothing parts)
			local function rimS1(againstHigh: boolean): () -> Run.Step
				return function(): Run.Step
					local dir = "kit/selftest/blender/game_fidelity/rim_s1"
					local label = if againstHigh
						then "game_fidelity car_wheel_rim S1 against its high"
						else "game_fidelity car_wheel_rim S1 against itself"
					local argv = {
						"-b",
						"--factory-startup",
						`{dir}/car_wheel_rim.blend`,
						"-P",
						"kit/blender/game_fidelity.py",
						"--",
						if againstHigh then `{dir}/car_wheel_rim_high.blend` else `{dir}/car_wheel_rim.blend`,
						`{Config.build("renders")}/car_wheel_rim_s1.fidelity{if againstHigh then "" else ".self"}`,
						"--mm",
						"280",
						"--master-own-colour", -- (both: the close-up pass GATES - a pass faulting identical pictures fails)
					}
					return Run.content(label, Run.tool("blender"), argv)
				end
			end
			local function gameFidelity(swap: { string }?): () -> Run.Step
				return function(): Run.Step
					-- the skull is the kit home's reference build: the active game's copy when it has one, else the
					-- project root's (an active game moves Config.build under games/<Name>/, where no skull is built)
					local function skull(file: string): string
						local p = `{Config.build("models")}/{file}`
						return if fs.isFile(p) then p else `{Config.DEFAULTS.paths.build}/models/{file}`
					end
					local master, game = skull("human_skull.blend"), skull("human_skull_game.blend")
					local label = if swap
						then "game_fidelity (V0 maps swapped in)"
						else "game_fidelity human_skull_game"
					if not (fs.isFile(master) and fs.isFile(game)) then
						print(
							`[skipped] 3d {label}: no skull master + game build (lune run kit asset human_skull; lune run kit optimize human_skull)`
						)
						return { name = label, cmd = "", exit = 0, ok = true, tail = "skipped: no skull builds" }
					end
					local argv = {
						"-b",
						"--factory-startup",
						game,
						"-P",
						"kit/blender/game_fidelity.py",
						"--",
						master,
						`{Config.build("renders")}/human_skull_game.fidelity{if swap then ".v0" else ""}`,
					}
					if swap then
						table.insert(argv, "--swap")
						for _, a in swap do
							table.insert(argv, a)
						end
					end
					return Run.content(label, Run.tool("blender"), argv)
				end
			end
			-- the hand-written hero rule (the owner, 2026-11-11, kit card 38a9: "Yes, allow them" - it replaced his 2026-10-09
			-- kit-make-only refusal and the KIT_HAND_BUILD switch): a hero / aaa script kit make did not write BUILDS at its tier
			-- when it passes every hero check, and any hero check it fails REFUSES it - a judgement it declares off included (no
			-- waiver). A script that names no quality= builds at its brief's tier ("Yes, turn them on")
			local handHero = "kit/selftest/blender/build_hand_hero.py"
			local function ruleStep(label: string, ok: boolean, step: Run.Step, why: string): Run.Step
				print(if ok then `[ok] {label}` else `[MISSED] {label} — {why}`)
				return {
					name = label,
					cmd = step.cmd,
					exit = if ok then 0 else 1,
					ok = ok,
					tail = if ok then "as the rule says" else why .. ": " .. tostring(step.tail),
					result = if ok
						then nil
						else {
							next_action = `the hand-written hero rule is wrong ({why}) — fix rbx.Asset, never the fixture`,
						},
				}
			end
			local handHeroRefused = expectFail(
				"3d hand-written hero: a hero check it fails refuses it (no waiver: it declares stage_gate=False)",
				fixture("hand_hero_waiver"),
				{ "design.declared", "stage_gate=False" }
			)
			local function handHeroBuilds(): Run.Step
				Run.expectingFailure = true
				local step = fixture("hand_hero_ok")()
				Run.expectingFailure = false
				local r = step.result
				local tier = r and r.facts and r.facts.tier
				local built = r ~= nil
					and r.status == "pass"
					and tier ~= nil
					and tier.tier == "hero"
					and tier.hand_hero == true
					and string.find(tostring(tier.from), "brief", 1, true) ~= nil
				return ruleStep(
					"3d hand-written hero: one that passes every hero check builds, at the hero tier its brief names",
					built,
					step,
					"not built at hero from its brief (or refused)"
				)
			end
			local function handOptimized(): Run.Step
				Run.expectingFailure = true
				Run.content(
					"hand_hero master",
					Run.tool("blender"),
					{ "-b", "--factory-startup", "--python-exit-code", "2", "-P", handHero, "--", "--no-preview" },
					{ KIT_BUILD = Config.path("build") }
				)
				local game = Content.blenderStep("hand_hero --optimize", handHero, { "--no-preview", "--optimize" })
				Run.expectingFailure = false
				local through = game.result ~= nil and game.result.asset == "selftest_hand_hero_game"
				return ruleStep(
					"3d hand-written hero: kit optimize of its built master makes the game version",
					through,
					game,
					"the game version was refused or crashed"
				)
			end
			-- the internal-lines check needs the vetted vision models (kit vision setup): with them, its fixture must
			-- be caught; without them the selftest SAYS it skipped it (never a silent pass)
			Run.expectingFailure = true
			local visionReady =
				Run.content("vision probe", Run.tool("python"), { "kit/vision/setup.py", "teed", "--check" }).ok
			Run.expectingFailure = false
			-- code CAD (a.cad) needs the cad env (lune run kit tools setup cad): with it, its fixtures run; without it the
			-- selftest SAYS it skipped them
			Run.expectingFailure = true
			local cadReady =
				Run.content("cad probe", Run.tool("python"), { "kit/tools/tools.py", "setup", "cad", "--check" }).ok
			Run.expectingFailure = false
			local function cadSkipped(label: string): () -> Run.Step
				return function(): Run.Step
					print(`[skipped] {label}: the cad env is not set up (lune run kit tools setup cad)`)
					return { name = label, cmd = "", exit = 0, ok = true, tail = "skipped: the cad env is not set up" }
				end
			end
			-- the skull's game_fidelity cases need its master + game builds (gameFidelity above skips its own steps
			-- without them): its bad-fixture case skips the same way, never reported as a gate that let one through
			local function skullBuilt(): boolean
				for _, file in { "human_skull.blend", "human_skull_game.blend" } do
					if
						not (
							fs.isFile(`{Config.build("models")}/{file}`)
							or fs.isFile(`{Config.DEFAULTS.paths.build}/models/{file}`)
						)
					then
						return false
					end
				end
				return true
			end
			-- build a lines fixture, then its lines step (the build alone never checks lines); with `quality`, the same
			-- input is judged as that tier (the fixture itself stays a prop: no hero side effects)
			local function linesStep(fixtureName: string, asset: string, quality: string?): Run.Step
				local input = `{Config.build("renders")}/{asset}_ref_side_lines.json`
				if fs.isFile(input) then
					fs.removeFile(input)
				end
				local built =
					Content.blenderStep(fixtureName, `kit/selftest/blender/build_{fixtureName}.py`, { "--no-preview" })
				if not fs.isFile(input) then
					return built -- no lines input: the reference check never ran (that is a failure of its own)
				end
				if quality then
					local info = serde.decode("json", fs.readFile(input))
					info.quality = quality
					input = `{Config.build("renders")}/{asset}_{quality}_lines.json`
					fs.writeFile(input, serde.encode("json", info))
				end
				return Run.content("lines", Run.tool("python"), { "kit/vision/lines.py", input })
			end
			local function skipped(label: string, say: boolean): () -> Run.Step
				return function(): Run.Step
					if say then
						print(`[skipped] {label}: the vision models are not set up (lune run kit vision setup)`)
					end
					return { name = label, cmd = "", exit = 0, ok = true, tail = "skipped: kit vision not set up" }
				end
			end
			local linesMissing = if visionReady
				then expectFlag("3d internal-lines gate (groove, seam, slot the silhouette cannot see)", function()
					return linesStep("missing_lines", "_selftest_lines")
				end, { "missing lines" })
				else skipped("3d internal-lines gate", true)
			local linesAaa = if visionReady
				then expectFail("3d internal-lines gate fails an aaa build that lacks them", function()
					return linesStep("missing_lines", "_selftest_lines", "aaa")
				end, { "below the aaa bar" })
				else skipped("3d internal-lines aaa bar", false)
			local linesClean = if visionReady
				then expectClean("3d internal-lines gate passes a model that HAS them", function()
					return linesStep("matching_lines", "_selftest_lines_ok")
				end, { "missing lines" })
				else skipped("3d internal-lines clean pass", false)
			local passSummary = if visionReady
				then "selftest: every gate caught its bad fixture"
				else "selftest: every gate caught its bad fixture (internal-lines gate SKIPPED: kit vision not set up)"
			return SelftestCache.chain(selftestArgs, caseLabel, passSummary, {
				-- (error forms "<scope>.<check>=": a gate downgraded to a warning would only be NAMED, and must not pass here)
				expectFail("blender gate", fixture("bad_asset"), { "main.tris=", "main.manifold=" }),
				expectFail("3d floating-part gate", fixture("floating"), { "design.floating_parts=" }),
				expectFail("3d size-vs-design gate", fixture("wrong_size"), { "design.size_vs_target=" }),
				expectFail(
					"3d inside-out gate (mirror copies stay clean)",
					fixture("inside_out"),
					{ "design.inside_out=['Lid']" }
				),
				expectFail(
					"3d stated-intention gate (a false a.expect)",
					fixture("broken_expect"),
					{ "design.expect:Lid=" }
				),
				-- the deep per-part checks (rbx_inspect / rbx_mech): one fixture each, measured defects
				expectFlag("3d sliver gate (a 0.5 mm skin on a solid block)", fixture("sliver"), { "slivers" }),
				expectSpared(
					"3d sliver gate spares a pointed blade (a feather, a sword tip: converging edges, not a shelf)",
					fixture("blade_tip"),
					{ "slivers" }
				),
				expectSpared(
					'3d a MASTER (stage="master") is not capped at 20k triangles a mesh (kit optimize makes the game mesh)',
					fixture("master_uncapped"),
					{ ".tris=" } -- (named as a failure: "main.tris=..."; a passing summary lists "<n> tris" per mesh)
				),
				expectSpared(
					"3d a carve leaves no micro faces (clamped bevels where a pointed bar's tips meet its curved band)",
					fixture("bevel_tip"),
					{ "degenerate_faces", "manifold" }
				),
				expectSpared(
					"3d a zone's split planes leave no micro faces (planes a hair beside a fan of thin triangles' tip)",
					fixture("zone_split"),
					{ "degenerate_faces", "manifold" }
				),
				-- THE SEAM CHECK on a model built for real (card 7cka): a ball whose soot was laid across the MAP shows a
				-- line at every UV seam - its 1,228 short seam edges judged along their seam lines; laid on the model,
				-- the same soot meets itself
				expectFlag(
					"3d seams: soot laid by a noise across the map steps at every UV seam - the seam check names it",
					fixture("seams_line"),
					{ "show a step beyond the texture's own" }
				),
				expectSpared(
					"3d seams: the same soot laid by a noise on the model meets itself across every seam",
					fixture("seams_meet"),
					{ "show a step beyond" }
				),
				-- THE HYBRID ROUTE (LIMITATIONS_FIXES_V4 3D-X: kit/gen/hybrid_fabricate.py): a generated part on a game
				-- mesh is retopologised into quads with its dense skin as its high; the same part as decimated soup is named
				expectFlag(
					"3d hybrid: a generated part imported as decimated triangle soup - generated_topology names it",
					fixture("hybrid_soup"),
					{ "generated_topology" }
				),
				expectSpared(
					"3d hybrid: the part retopologised (Instant Meshes quads) with its skin as its high - not named",
					fixture("hybrid_ok"),
					{ "generated_topology" }
				),
				-- R6 CLOTHES TO THE STANDARD (a.r6_wear, rbx_r6wear): under 4k triangles, quads, watertight, clear of
				-- the block - the Hero way (a round dense soup tube round the square torso) is named; a quad-loft shell is not
				expectFlag(
					"3d r6 clothes: a round dense soup tube round the torso - over budget, not quads, the block pokes through",
					fixture("r6wear_soup"),
					{ "r6_tris", "r6_quads", "r6_clearance" }
				),
				expectSpared(
					"3d r6 clothes: a quad-loft shell 0.035 studs off the torso, 0.022 at its corners, 3,000 triangles",
					fixture("r6wear_ok"),
					{ "r6_tris", "r6_quads", "r6_closed", "r6_clearance" }
				),
				expectSpared(
					"3d a MASTER keeps its floaters as real geometry (high-quality detail: the rivets its spec names)",
					fixture("master_floaters"),
					{ "spec_parts" }
				),
				expectSpared(
					"3d a GAME build's baked floaters still count as the spec's parts (baked, not missing)",
					fixture("game_floaters"),
					{ "spec_parts" }
				),
				expectSpared(
					"3d a MASTER's fine recesses are its detail, not wasted triangles (the game version bakes them)",
					fixture("master_fine_cut"),
					{ "tiny_cuts" }
				),
				expectFlag(
					"3d brief: a model built without asking the owner what it is for is named",
					fixture("brief_missing"),
					{ "brief" }
				),
				expectSpared(
					"3d brief: a model whose brief the owner answered",
					fixture("brief_answered"),
					{ "brief" }
				),
				expectFlag(
					"3d brief: a hero feature with no route, and one only a far picture shows (1.4 px/mm), are named",
					fixture("brief_no_route"),
					{ "routes", "coverage" }
				),
				-- silhouette first: a hero build below its traced bar is a blockout — one next step, detail deferred
				expectFail(
					"3d stage gate: a hero build below its silhouette bar fails on the outline, detail deferred",
					fixture("stage_blockout"),
					{ "design.stage=", "deferred until the silhouette is right" }
				),
				expectSpared(
					"3d stage gate: the reference check it carries is not reported twice",
					fixture("stage_blockout"),
					{ "design.reference_side=" }
				),
				expectSpared(
					"3d stage gate: a hero build at its silhouette bar is past the blockout",
					fixture("stage_outline_ok"),
					{ "design.stage=", "silhouette first", "deferred until" }
				),
				-- the owner, 2026-11-12 (kit card a3xx): "Yes, make it fail" - a hero build with NO traced view registered
				-- has its outline measured against nothing; the gate used to read that as "unmeasured" and let it pass
				-- (the Gjallarhorn's lower rear stayed misread for 7 rounds)
				expectFail(
					"3d stage gate: a hero build with no traced view fails - its outline is measured against nothing",
					fixture("stage_unmeasured"),
					{ "design.stage=unmeasured: no traced view registered" }
				),
				expectFlag(
					"3d real size: a chair built 1.8x real size, its size target as wrong, is named (Infinigen's ranges)",
					fixture("real_size_off"),
					{ "size_plausible" }
				),
				expectSpared("3d real size: a chair at real size", fixture("real_size_ok"), { "size_plausible" }),
				expectFlag(
					'3d reference sizes: a bracket half the reference\'s height is measured and named (spec "ref")',
					fixture("ref_size_off"),
					{ "ref_sizes" }
				),
				expectSpared(
					"3d reference sizes: parts at the reference's size and place (frames lined up, a knob below the foot)",
					fixture("ref_size_ok"),
					{ "ref_sizes" }
				),
				expectFlag(
					'3d reference sizes: a spec "ref" to a mask kit trace judged doubtful (it filled its box) is named',
					fixture("ref_doubtful"),
					{ "ref_sizes_doubtful" }
				),
				expectFlag(
					"3d view gaps: a model 25% too wide for its FRONT view is measured edge to edge in mm and named",
					fixture("view_gaps_front"),
					{ "view_gaps_front" }
				),
				expectSpared(
					"3d view gaps: a model matching its side, front, back and top traces (a lug on one side: each view turned right)",
					fixture("view_gaps_ok"),
					{ "view_gaps" }
				),
				expectFlag(
					"3d faceting: a hero barrel of 12 sides (its facets 0.68 mm off the true circle) is named",
					fixture("faceting_off"),
					{ "faceting" }
				),
				expectSpared(
					"3d faceting: the same barrel of 64 sides (0.02 mm off: smooth to the eye)",
					fixture("faceting_ok"),
					{ "faceting" }
				),
				expectFlag(
					"3d texel bar: a hero slab on a 256 map (a fifth of one texel a screen pixel where it is judged) is named",
					fixture("map_short"),
					{ "texel_bar" }
				),
				expectFlag(
					"3d map by need: a hero master of four square metres with no size named bakes a 4096 map, and says so",
					fixture("map_need"),
					{ "maps by need: main 4096" }
				),
				expectFlag(
					"3d packed by shape: a plate of many parts gets its islands placed by their shape, the small ones in the gaps (more of its map used than Blender's packer gave), and says so",
					fixture("pack_tight"),
					{ "packed by shape: main" }
				),
				expectSpared(
					"3d packed by shape: a plain tile (two equal squares: half the map is the most any packer gets) claims no gain",
					fixture("pack_cube"),
					{ "packed by shape" }
				),
				expectFlag(
					"3d passes kept: a build that changes only its materials' wear numbers (more chips, grime, dust) reads its last bake's passes - no unwrap, no Cycles - and says so",
					moreDirt("relayer"),
					{ "passes kept: main" }
				),
				expectSpared(
					"3d passes kept: a first bake has no passes to read",
					fixture("pack_tight"),
					{ "passes kept" }
				),
				expectFlag(
					"3d layers: a material's own layers (rust where its paint chipped and in its cavities, soot low down) are laid, changed without a render pass, and said with what each covered",
					moreDirt("layers"),
					{ "layers: main paint rust ", "soot ", "steel blueing ", "passes kept: main" }
				),
				expectSpared(
					"3d layers: a model whose materials have no layers names none",
					fixture("relayer"),
					{ "layers:" }
				),
				expectFlag(
					"3d repeat: one tooth, post, stud, peg and fin modelled - a row, a ring, a path, a grid and both sides made, and said",
					fixture("repeat"),
					{
						"repeats: Fin x4 (row x4), Peg x9 (row x3 in row x3), Post x8 (ring x8), Stud x9 (path x9), Tooth x12 (row x12)",
					}
				),
				expectSpared("3d repeat: a model with no repeated part names none", fixture("relayer"), { "repeats:" }),
				expectFlag(
					"3d deform: a horn built straight then tapered, twisted and bent on both sides, a strap laid onto a barrel - made, and said",
					fixture("deform"),
					{ "deformed: Horn (taper 0.15, twist 120, bend 70), Strap (onto Body)" }
				),
				expectSpared(
					"3d deform: a model with no deformed part names none",
					fixture("relayer"),
					{ "deformed:" }
				),
				expectFlag(
					"3d sweep: a horn to a point, a mitred rail, a twisted rope ring and a strap swept along their paths - made, and said",
					fixture("sweep"),
					{ "swept: Horn, Rail, Ring, Strap" }
				),
				expectSpared("3d sweep: a model with no swept part names none", fixture("relayer"), { "swept:" }),
				expectFlag(
					"3d scatter: one shingle and one rivet modelled - twelve laid down a roof's slope clear of each other and of its edge, twenty-four stood on a dome, and said",
					fixture("strew"),
					{ "repeats: Rivet x24 (scatter on Dome x24), Shingle x12 (scatter on Roof x12)" }
				),
				expectFlag(
					"3d box modelling: a crate cut from ONE box - its lid inset and sunk, two cuts, a boss pushed out, a panel sunk, rounded last - on two mirrored feet, and said",
					fixture("poly"),
					{ "modelled: Crate (inset +Y, loop x2, push, inset, round 0.02), Foot (inset +X, round 0.012)" }
				),
				expectSpared(
					"3d box modelling: a model none of it was used on names none",
					fixture("relayer"),
					{ "modelled:" }
				),
				expectFlag(
					"3d smoothing: a pod cut from ONE box and smoothed soft but for its foot, a case whose every hard edge is only softened - made, and said",
					fixture("smooth"),
					{ "modelled: Case (inset +Y, smooth x2), Pod (loop x2, push, smooth x2)" }
				),
				-- A MASK THE AUTHOR PLACES (the owner's method lists: texture painting, masks, material masks, material
				-- blending; stage S3): a layer goes where a rule or a picture says, not only where the mesh does
				expectFlag(
					"3d placed mask: a gold stripe by a rule and a rust stain by a picture, each laid by a layer that names it - built, and said",
					fixture("mask"),
					{ "stain on 4% of main", "stripe on 11% of main", 'gold on the mask "stripe" 100% -> 1' }
				),
				expectStop(
					"3d placed mask: a layer naming a mask nobody placed stops the build by the mask's name",
					fixture("mask_unplaced"),
					{ 'no a.mask("stain"', "the model's masks: stripe" }
				),
				-- SEAMS THE AUTHOR PLACES, A CAGE THE SCRIPT SETS (the owner's method lists: seam placement, bake cages,
				-- artifact cleanup; stage S3b)
				expectFlag(
					"3d placed seams: a handle cut down its back and at its caps - laid as three pieces, and said",
					fixture("seam_placed"),
					{ "placed seams: Handle 3 piece(s)" }
				),
				expectSpared(
					"3d placed seams: that handle's pieces lie flat (seam_placed holds)",
					fixture("seam_placed"),
					{ "seam_placed" }
				),
				expectFail(
					"3d placed seams: a tube nobody cut open cannot lie flat",
					fixture("seam_placed_uncut"),
					{ "seam_placed" }
				),
				expectStop(
					"3d placed seams: a rule that cuts no edge of its part stops the build",
					fixture("seam_placed_nowhere"),
					{ 'a.seams("Handle"): the rule cut no edge of the part' }
				),
				expectFlag(
					"3d bake cage: the group's cage and one part's own, set by the script - taken, and said",
					fixture("bake_cage"),
					{ "cage set: main 2 mm, LugA 3 mm" }
				),
				expectSpared(
					"3d bake cage: cages that reach their high are not held, and no ray misses",
					fixture("bake_cage"),
					{ "bake_cage", "bake_misses" }
				),
				expectFail(
					"3d bake cage: a part's cage under what its high needs",
					fixture("bake_cage_shallow"),
					{ "bake_cage", "LugA 0.02 mm" }
				),
				-- VERTEX PAINT (the owner's method lists: vertex colours, vertex-painted blending; stage S4)
				expectFlag(
					"3d vertex paint: a post dark at its foot by a rule on the point - in the colour map, in the file, and said",
					fixture("paint"),
					{ "painted: main (Post: 0.25 to 1.00)" }
				),
				expectSpared(
					"3d vertex paint: the paint is found again in the exported file",
					fixture("paint"),
					{ "export_read_back" }
				),
				-- THE TOPOLOGY OF A BUILT MODEL (the owner's method lists: edge flow, polygon distribution, internal and
				-- hidden faces, flat shading; stage T)
				expectFlag(
					"3d topology: faces no eye can reach are taken out (a.drop_hidden), and said",
					fixture("topology"),
					{ "hidden faces dropped: main 15" }
				),
				expectSpared(
					"3d topology: with them out, none is left unseen and the drum is flat as asked",
					fixture("topology"),
					{ "hidden_faces", "shading", "manifold" }
				),
				expectWarn(
					"3d topology: left in, the faces no eye can reach are said",
					fixture("topology_kept"),
					{ "hidden_faces" }
				),
				expectFail(
					"3d topology: a part asked flat and shaded round",
					fixture("topology_round"),
					{ "shading", "Drum flat: 20% flat" }
				),
				expectWarn(
					"3d topology: triangles spent on nothing, needles and a pole",
					fixture("topology_poor"),
					{ "polygon_waste", "needles", "poles" }
				),
				-- SURFACES THAT REPEAT, A STYLISED LOOK (the owner's method lists: seamless / tileable, stylised shading;
				-- stage X)
				expectFlag(
					"3d tile: a square of one finish that repeats both ways - built, and said",
					fixture("tile"),
					{ "tile: 8 studs a tile, repeats both ways" }
				),
				expectFail(
					"3d tile: maps that get lighter left to right do not repeat",
					fixture("tile_ramp"),
					{ "tile_seam" }
				),
				expectFlag(
					"3d stylised: the light painted into the colour in three flat tones, and said",
					fixture("tile_ball"),
					{ "stylised: main all in 3 flat tones (lit " }
				),
				expectFail(
					"3d stylised: a painted light that never reached the colour map",
					fixture("tile_unlit"),
					{ "stylised", "the painted light in the colour map" }
				),
				expectStop(
					"3d stylised: a metal material cannot carry a painted light - the build stops",
					fixture("tile_metal"),
					{ 'stylise: the material "clay" is metal' }
				),
				-- SEE-THROUGH BY DEGREES (the owner's method lists: transparency; stage X)
				expectFlag(
					"3d fade: a pane clear at its foot and solid at its top - the degrees in its map, and said",
					fixture("fade"),
					{ "faded: Pane 50% clear over" }
				),
				expectFail(
					"3d fade: a fade that leaves everything solid",
					fixture("fade_solid"),
					{ "cutout", "the fade takes nothing", "fade_grades" }
				),
				expectSpared(
					"3d fade: a faded master's game version keeps its colour (kit optimize bakes it solid)",
					optimized("fade_master"),
					{ "game_fidelity", "optimize_loss" }
				),
				-- THE GAME'S SETTINGS A SCRIPT SAYS (the owner's method lists: physics materials, impostors; stage O)
				expectFlag(
					"3d game settings: a tyre that grips and bounces, a model with Roblox's far stand-in - in the manifest, and said",
					fixture("game_settings"),
					{ "game: tyre elasticity 0.6 friction 1.6, far StreamingMesh" }
				),
				expectStop(
					"3d game settings: a physics material for a group the asset has not stops the build",
					fixture("game_settings_nogroup"),
					{ 'physics: no group "tire"', "main, tyre" }
				),
				-- WHAT A MODEL COSTS TO DRAW, PAST ITS TRIANGLES (the owner's method lists: draw calls, overdraw; stage O)
				expectWarn(
					"3d draws: six solid groups that never move apart, eight panes in a row",
					fixture("batch"),
					{ "draw_calls", "overdraw" }
				),
				expectSpared(
					"3d draws: a block and one pane are not said",
					fixture("batch_fine"),
					{ "draw_calls", "overdraw" }
				),
				-- A PART BROKEN BEFOREHAND (the owner's method lists: destructible preparation; stage O)
				expectFlag(
					"3d fracture: a crate broken into five pieces that fit - the whole kept, the pieces added, and said",
					fixture("fracture"),
					{ "broken beforehand: Crate in 5 pieces" }
				),
				expectSpared(
					"3d fracture: the pieces add up to the crate and none is said hidden",
					fixture("fracture"),
					{ "fracture", "hidden_faces", "manifold" }
				),
				expectStop(
					"3d fracture: a part that is not a closed solid cannot be broken - the build stops",
					fixture("fracture_open"),
					{ 'fracture: "Crate" is not one closed solid' }
				),
				-- HAIR, FUR, CLOTH (the owner's method lists: hair and fur grooming, hair cards, particle-based geometry,
				-- cloth simulation, simulation baking, clothing folds and seams; stage H)
				expectFlag(
					"3d hair: forty locks scattered over a scalp, swept back - built, and said",
					fixture("hair"),
					{ "Lock x40 (scatter on Scalp x40)" }
				),
				expectStop(
					"3d hair: a lock of one segment stops the build",
					fixture("hair_thin"),
					{ "lock: segments=1 - a whole number from 2 to 8" }
				),
				expectFlag(
					"3d cloth: a cover dropped on a table by simulation and frozen - it rests on it, and said",
					fixture("cloth"),
					{ "cloth laid: Cover over Table" }
				),
				expectFail(
					"3d cloth: a cover dropped beside the table never comes to rest on it",
					fixture("cloth_missed"),
					{ "design.cloth", "0% of it rests on Table" }
				),
				-- A MODEL'S OWN RIG, SOLVED (the owner's method lists: IK, constraints, skeletons and hierarchy; stage R)
				expectFlag(
					"3d rig: an arm of two hinges with two named places for its tip - solved, and said",
					fixture("rig"),
					{ "chains: Arm (Shoulder > Elbow; 2 of 2 poses met)" }
				),
				expectFail(
					"3d rig: a place nine studs away from a four-stud arm",
					fixture("rig_far"),
					{ "design.reach", "1 of 2 poses met" }
				),
				expectStop(
					"3d rig: a chain listed tip first stops the build",
					fixture("rig_order"),
					{ "list the joints from the base outward" }
				),
				-- (stage P: a solved pose checked with the WHOLE model posed together - each joint alone is clear)
				expectFail(
					"3d rig: a pose that swings the arm out and folds the forearm down through a bollard - each joint clear alone, caught together",
					fixture("rig_fold"),
					{ "reach_clear", "Arm / down", "Fore into Bollard" }
				),
				expectSpared(
					"3d rig: the arm's own solved poses clear the base and post - reach_clear spares it",
					fixture("rig"),
					{ "reach_clear" }
				),
				-- KITS AND EXOTIC SURFACES (the owner's method lists: NURBS, kitbashing, metaball, glTF; stage K). The
				-- lender is the topology fixture, built above
				expectFlag(
					"3d kits: a surface drawn by a control net, balls that flow into one skin, a part lent by another build, a .glb beside the FBX - built, and said",
					function(): Run.Step
						fixture("topology")() -- (the lender: built first, for its saved build - its verdict is not this check's)
						return fixture("kits")()
					end,
					{ "kit: 1 drawn by a net, 1 blob(s), 1 lent by another build, a .glb a group" }
				),
				expectStop(
					"3d kits: a control net folded over itself stops the build",
					fixture("kits_fold"),
					{ "its net folds the surface over itself" }
				),
				expectStop(
					"3d kits: a build the owner never approved lends no geometry",
					fixture("kits_unloved"),
					{ "may not lend its geometry" }
				),
				-- TRIM SHEETS AND A KIT OF MODULES (the owner's method lists: trim sheets, trim sheet UV mapping,
				-- seamless textures, modular construction, modular snapping; stage S2; his limitations D-R07). The
				-- sheet is built FIRST: the walls take their bands from its manifest
				expectFlag(
					"3d trim sheet: four bands at one scale, baked and made to repeat along their length - built, and said",
					fixture("trim_sheet"),
					{ "trim sheet: 4 bands over 8 studs, repeats along its length" }
				),
				expectFlag(
					"3d trim: a wall module laid into the sheet bakes nothing, takes the sheet's sharpness and snaps to its grid - said",
					fixture("trim_wall"),
					{ "trim: main on _selftest_trim_sheet (64 px a stud)", "module: 2 x 1 cells" }
				),
				expectFail(
					"3d trim: a module half a stud off its grid fails module_grid, and a panel in a band far too low is named",
					fixture("trim_wall_off"),
					{ "module_grid", "7.5 studs along x", "trim_fit" }
				),
				-- THE CONVENTIONS on the way into the engine (the owner's method lists: naming conventions, pivot
				-- placement, normal map convention, import settings): checked by code, no longer only written down
				expectFlag(
					"3d conventions: a group and a material named against the rule, a model built off its origin - each flagged by name",
					fixture("conventions_off"),
					{ "naming", "pivot" }
				),
				expectSpared(
					"3d conventions: a model named and placed by the rule is not flagged, and its exported files read back right",
					fixture("fidelity"),
					{ "naming", "pivot", "export_read_back", "normal_convention" }
				),
				-- A NAMED OPENING (the owner's limitations page, D-R12): a.open_way names a way that must stay open; the
				-- build looks down it on the parts and on what it exports
				expectFlag(
					"3d named opening: a bore and a port named in a turned frame, looked down on the parts and the export - open, and said",
					fixture("open_way"),
					{ "openings: 2 open" }
				),
				expectFail(
					"3d named opening: a plug left in the bore - the build fails open_ways by the opening's name and the plug's",
					fixture("open_way_plugged"),
					{ "open_ways", "Bore: 15 of its 15", "Plug" }
				),
				expectFail(
					"3d named opening: a fine bore the game version's retopology closes - that build fails open_ways (open as modelled, closed as exported)",
					optimized("open_way_fine", { "--budget=400", "--retopo" }),
					{ "open_ways", "FineBore" }
				),
				-- (D-R12, the rest: a repair is STEERED by the name - a hole a named way passes through is never capped)
				expectFlag(
					"3d named opening: a bin's torn floor is capped and its named mouth left open by the repair - said",
					fixture("repair_named"),
					{ "repaired: Bin (1 hole capped, left open as named: Mouth)", "openings: 1 open" }
				),
				expectFail(
					"3d named opening: the same bin left a sheet - its mouth is still not filled, and openings says what gives the wall its back",
					fixture("repair_named_thin"),
					{ "openings", "left open as named: Mouth" }
				),
				-- A PLACE THE GAME VERSION MUST KEEP (the owner's limitations page, D-R08: "protect important features and
				-- moving interfaces"): the decimator spares it, and the build measures there
				expectFlag(
					"3d protected place: fine grooves named with a.protect survive the reduction to 1000 triangles - said",
					optimized("protect", { "--budget=1000" }),
					{ "protected: 1 of 1 places kept" }
				),
				expectFail(
					"3d protected place: the same grooves only measured, the decimator not steered - lost, and failed by the place's name",
					optimized("protect_watched", { "--budget=1000" }),
					{ "protected", "Grooves: the game version lies" }
				),
				-- THE REFERENCES, SOLVED TOGETHER (the owner's limitations page, D-R01): every statement about the overall
				-- sizes is one claim; each is held out against the others
				expectFlag(
					"3d references: a drawing's two sizes and two photos' proportions - solved together, they agree, and said",
					fixture("agree"),
					{ "references: 4 statements agree" }
				),
				expectFail(
					"3d references: a second photo of another proportion - reference_agree fails the build and names that photo with what the others say",
					fixture("agree_odd"),
					{ "reference_agree", "another side photo says height is 0.33 of the length" }
				),
				expectFlag(
					"3d references: references that agree and a bar built a fifth too tall - reference_fit says both proportions",
					fixture("agree_tall"),
					{ "reference_fit", "the build leaves them" }
				),
				-- SOCKETS AND MATES (the owner's limitations page, D-R04): a named place on a part, two of them said to
				-- meet; measured on the parts as built
				expectFlag(
					"3d sockets: a well named on a body, a peg placed by it and mated with a fit - held, and said",
					fixture("mates"),
					{ "sockets: 2 on their parts, 1 of 1 mates held" }
				),
				expectFail(
					"3d sockets: a body grown half a stud without its socket - mates names the socket and how far off its part it lies",
					fixture("mates_grown"),
					{ "mates", 'Well: it lies 0.5 studs off "Body"' }
				),
				expectFail(
					"3d sockets: a peg wider than its well does not go in",
					fixture("mates_fat"),
					{ "mates", "does not go into 0.5" }
				),
				expectFail(
					"3d sockets: a peg moved aside by hand - the mate says how far apart the two are",
					fixture("mates_apart"),
					{ "mates", "they are 0.4 studs apart" }
				),
				-- THE MAP ACROSS ITS SEAMS (the owner's method lists, "texture seam checks"; stage G4): after the bake the
				-- colour map is read on both sides of every seam that runs over smooth surface
				expectFlag(
					"3d seams: a baked ball's colour map meets itself across its seams - judged, and said",
					fixture("fidelity"),
					{ "seams: ball meet (" }
				),
				expectClean("3d seams: that build raises no seam warning", fixture("fidelity"), { "show a step" }),
				-- THE GAME'S SETTINGS of a mesh (the owner's method lists: collision meshes, primitive colliders, convex
				-- hulls, LOD setup; stages G1 and G2; his limitations page D-R09): the collision shape and the level of
				-- detail are chosen by rule for every exported mesh and carried to the model file
				expectFlag(
					"3d game settings: a crate, a ball, a bowl, two doorways and two sunk blocks each get their own collision shape and level of detail - built, and said",
					fixture("fidelity"),
					{
						"in game: arch PreciseConvexDecomposition / Automatic",
						"ball Hull / Automatic",
						"bowl Default",
						"gate PreciseConvexDecomposition",
						"main Box",
						"pile Box",
					}
				),
				expectClean(
					"3d game settings: that build passes - the rule's own choices raise no collision fault",
					fixture("fidelity"),
					{ "collision" }
				),
				expectFail(
					"3d game settings: a hull declared on the arch would shut its doorway - the build fails collision by name",
					fixture("fidelity_closed"),
					{ "arch.collision=Hull" }
				),
				-- CUT-OUTS (the owner's method lists, "alpha clipping"; stage S1): a part's outline cut by its colour
				-- map's alpha - the geometry stays a plain sheet, the map says where it shows
				expectFlag(
					"3d cut-out: a grille's bars and a leaf's outline cut by a rule, a round sign by a picture - built, and said",
					fixture("cutout"),
					{ "cut out: Grille 5", ", Leaf 3", ", Sign 3" }
				),
				expectClean(
					"3d cut-out: that build passes - every cut takes some of its part and leaves some",
					fixture("cutout"),
					{ "cutout", "openings" }
				),
				expectSpared("3d cut-out: a model with none says none", fixture("relayer"), { "cut out:" }),
				-- TWO-SIDED surfaces (the owner's method lists, "two-sided" faces; stage S1): a sheet of faces with no
				-- thickness gets its back as real faces a hair behind it - a closed solid in any engine
				expectFlag(
					"3d two-sided: a banner and two leaves, each ONE sheet of faces given its back - built as closed solids, and said",
					fixture("two_sided"),
					{ "two-sided: Banner, Frond" }
				),
				expectClean(
					"3d two-sided: that build passes - no opening, nothing inside out",
					fixture("two_sided"),
					{ "openings", "inside_out" }
				),
				expectSpared(
					"3d two-sided: a model with no such sheet says none",
					fixture("relayer"),
					{ "two-sided:" }
				),
				-- REPAIR and the OPENINGS check (the owner's method lists, "non-manifold cleanup"; stage M7): a part
				-- that is not a closed solid is closed where a repair is right (a seam welded, a flat hole capped)
				-- and said; what no repair closes fails the build by NAME and kind, where `manifold` only counts
				expectFlag(
					"3d repair: a bin and a pipe listed open are closed by a.repair, a box of six loose faces by the build's own weld - built, and said",
					fixture("repair"),
					{ "repaired: Bin (1 hole capped), Pipe (2 holes capped), Shell (16 seam points welded)" }
				),
				expectFail(
					"3d openings: a sheet of faces with no thickness fails by name, with what it is",
					fixture("open"),
					{ "design.openings", "Sheet: 1 border of a surface with no thickness" }
				),
				expectFlag(
					"3d openings: a curved rim the build filled with a patch is said and warned, not silent",
					fixture("open"),
					{ "repaired: Torn (1 opening filled by the build)", "patched" }
				),
				expectSpared(
					"3d repair: a model of closed parts says none",
					fixture("relayer"),
					{ "repaired:", "design.openings" }
				),
				-- THE MAP'S OWN CHECK (the owner's method lists, "UV overlap ... stretching checks"; stage M7): faces
				-- lying on each other on the map by accident, and texels pulled long over the surface
				expectFail("3d map check: two faces given one piece of the map (uv_overlap)", function()
					return Run.content(
						"map check (selftest)",
						Run.tool("python"),
						{ "kit/selftest/uvcheck/run.py", "crossed" }
					)
				end, { "of Crossed's map is painted twice", "2 faces lie on each other" }),
				expectSpared(
					"3d map check: a copy the unwrap's own record lays on its original is meant, not said",
					function()
						return Run.content(
							"map check (selftest)",
							Run.tool("python"),
							{ "kit/selftest/uvcheck/run.py", "stacked" }
						)
					end,
					{ "is painted twice", "longer than wide" }
				),
				expectFail(
					"3d map check: two faces on the very same place that no record calls copies (a front on its back)",
					function()
						return Run.content(
							"map check (selftest)",
							Run.tool("python"),
							{ "kit/selftest/uvcheck/run.py", "piled" }
						)
					end,
					{ "of Piled's map is painted twice" }
				),
				expectSpared("3d map check: a real build checks its map (its verdict carries it)", function()
					return Run.content(
						"map check (selftest)",
						Run.tool("python"),
						{ "kit/selftest/uvcheck/run.py", "built" }
					)
				end, { "never checked its map", "gave no verdict" }),
				expectFail(
					"3d map check: a face four times as long as its square piece of map (uv_stretch)",
					function()
						return Run.content(
							"map check (selftest)",
							Run.tool("python"),
							{ "kit/selftest/uvcheck/run.py", "long" }
						)
					end,
					{ "of Long's surface has texels 4x longer than wide" }
				),
				expectSpared("3d map check: two faces each with its own piece of the map", function()
					return Run.content(
						"map check (selftest)",
						Run.tool("python"),
						{ "kit/selftest/uvcheck/run.py", "apart" }
					)
				end, { "is painted twice", "longer than wide" }),
				-- THE MODERATION GATE (blood and gore get the uploading account moderated; kit/tools/mod_gate.py): a drawn
				-- blood pool and a splatter are held before any upload, a fire puff's colours are not blood
				expectFail("moderation gate: a drawn blood pool is held before upload", function()
					return Run.content(
						"moderation (selftest)",
						Run.tool("python"),
						{ "kit/selftest/moderation/run.py", "pool" }
					)
				end, { "held: pool.png", "blood-red" }),
				expectFail("moderation gate: a drawn blood splatter is held before upload", function()
					return Run.content(
						"moderation (selftest)",
						Run.tool("python"),
						{ "kit/selftest/moderation/run.py", "splat" }
					)
				end, { "held: splat.png", "blood-red" }),
				expectSpared("moderation gate: a fire puff is not blood", function()
					return Run.content(
						"moderation (selftest)",
						Run.tool("python"),
						{ "kit/selftest/moderation/run.py", "ember" }
					)
				end, { "held:" }),
				-- THE METHODS LOCK (the owner, 2026-11-13: "every method i mentioned ... implmented into each pipeline
				-- and enforced in the terms of being used"): a NEW piece's parts plan names the builder call of every
				-- coded part, and its build is held to that plan; a piece that existed before is not held
				expectFail(
					"3d methods lock: a new piece's plan with twelve teeth typed as boxes, a horn from a box and a bare 'code' (kit plan holds the brief)",
					function()
						return Run.content(
							"methods lock (selftest)",
							Run.tool("python"),
							{ "kit/selftest/methods/run.py", "typed" }
						)
					end,
					{ "Teeth x12: many alike", "Horn: long and curved", "Grip: code, but no METHOD" }
				),
				expectSpared("3d methods lock: the same plan with its methods named is not held", function()
					return Run.content(
						"methods lock (selftest)",
						Run.tool("python"),
						{ "kit/selftest/methods/run.py", "planned" }
					)
				end, { "holds the brief", "never asked" }),
				expectSpared("3d methods lock: a piece that existed before the lock is not held", function()
					return Run.content(
						"methods lock (selftest)",
						Run.tool("python"),
						{ "kit/selftest/methods/run.py", "old" }
					)
				end, { "holds the brief", "as if it were new" }),
				expectFail(
					"3d methods lock: the real build of a model that types its planned repeats one by one beside a token repeat of two",
					function()
						return Run.content(
							"methods lock (selftest)",
							Run.tool("python"),
							{ "kit/selftest/methods/run.py", "build" }
						)
					end,
					{
						"2 planned parts name repeat (Bolts x5, Fence) and the build used it on 1",
						"Bolts x5: its plan says x5 by repeat",
						"5 parts are ONE shape typed 5 times",
						"4 parts are ONE shape typed 4 times",
					}
				),
				expectSpared(
					"3d methods lock: the real build of the same model made with a.repeat is not refused",
					function()
						return Run.content(
							"methods lock (selftest)",
							Run.tool("python"),
							{ "kit/selftest/methods/run.py", "built" }
						)
					end,
					{ "is refused", "never asked" }
				),
				-- the model sheet's COLOUR PLAN on copies of the fixture project: with its parts' measured colours (a pack
				-- written into the copy: the fixture itself has none) every colour has its role and share; without
				-- them the colours are sampled off the picture and get NO role (bands of shading are not parts)
				expectFlag(
					"3d model sheet: its colour plan says each measured part colour's role and share and the value family that leads",
					function()
						local proj = Config.build("selftest/colourplan")
						if fs.isDir(proj) then
							fs.removeDir(proj)
						end
						fs.writeDir(Config.build("selftest"))
						fs.copy("kit/selftest/sheet", proj, true)
						fs.writeFile(
							proj .. "/assets/models/sheetgun.pack.json",
							serde.encode("json", {
								colours = {
									body = { srgb = { 46, 48, 56 } },
									barrel = { srgb = { 140, 145, 153 } },
									strip = { srgb = { 26, 204, 242 } },
									grip = { srgb = { 31, 31, 33 } },
								},
							})
						)
						return Run.content(
							"sheet colour plan (selftest)",
							Run.tool("python"),
							{ "kit/tools/sheet.py", "sheetgun", "--root", proj }
						)
					end,
					{
						"colours: main body 5",
						", second barrel 2",
						", second grip 1",
						", accent strip ",
						"; values: dark leads ",
					}
				),
				expectSpared("3d model sheet: colours sampled off the picture get no role", function()
					local proj = Config.build("selftest/colourplan_sampled")
					if fs.isDir(proj) then
						fs.removeDir(proj)
					end
					fs.writeDir(Config.build("selftest"))
					fs.copy("kit/selftest/sheet", proj, true)
					return Run.content(
						"sheet colour plan, sampled (selftest)",
						Run.tool("python"),
						{ "kit/tools/sheet.py", "sheetgun", "--root", proj }
					)
				end, { "colours: main", ", second ", ", accent " }),
				expectSpared(
					"3d texel bar: that master on the map sized by its need is sharp enough (at 2048 it could not be)",
					fixture("map_need"),
					{ "texel_bar" }
				),
				expectFlag(
					"3d wrap-around: a grip built as a box where its reference's slices are round (kit refs measure levels) is named",
					fixture("section_boxy"),
					{ "section_match" }
				),
				expectSpared(
					"3d wrap-around: the grip lofted through its reference's own measured slices (loft_sections(from_levels(...)))",
					fixture("section_wrapped"),
					{ "section_match" }
				),
				expectFlag(
					"3d bevels: a hero part with every hard edge left sharp is named",
					fixture("sharp_edges_off"),
					{ "sharp_edges" }
				),
				expectSpared(
					"3d bevels: a bevelled part, and a CAD part whose fillet OpenCASCADE refused (bevelled on the mesh instead)",
					fixture("sharp_edges_ok"),
					{ "sharp_edges" }
				),
				expectFlag(
					"3d bevels: a frame bevelled 75% passes the default bar but not what real frames do (a.learned_from: 94%)",
					fixture("sharp_edges_learned"),
					{ "sharp_edges" }
				),
				expectFlag(
					"3d down to the screws: a real M4 screw (cad_parts, ISO 4762) sunk into a solid block with no hole is named",
					fixture("fastener_seat_buried"),
					{ "fastener_seat" }
				),
				expectSpared(
					"3d down to the screws: the same screw in a hole cut at its ISO 273 clearance size",
					fixture("fastener_seat_ok"),
					{ "fastener_seat" }
				),
				expectSpared(
					"3d library reference: a model matched against a REFERENCE MODEL's side and front views (kit refs measure of a staged model: its backdrop and tool left out)",
					fixture("library_match_ok"),
					{ "reference_side", "reference_front" }
				),
				expectFlag(
					"3d library reference: a model missing the grip its reference model has is named",
					fixture("library_match_off"),
					{ "reference_side" }
				),
				expectSpared(
					"3d mirrored reference: views drawn the right way round are never called flipped",
					fixture("view_gaps_ok"),
					{ "_mirrored" }
				),
				expectFlag(
					"3d local windows, tall view: a chunk missing from one side of a column seen end-on is named",
					fixture("tall_local_off"),
					{ "reference_front_local" }
				),
				expectSpared(
					"3d local windows, tall view: 0.3 mm a side on a 30 mm column seen end-on is no regional fault",
					fixture("tall_local_ok"),
					{ "reference_front_local", "reference_front" }
				),
				expectFlag(
					"3d auto reference: a hero build with a traced view and no trace_match is still matched (and fails)",
					fixture("auto_ref_off"),
					{ "reference_side_local" }
				),
				expectFlag(
					"3d auto reference: two traces of one view, neither named, is named (say which is the reference)",
					fixture("auto_ref_two"),
					{ "references_auto_side" }
				),
				expectSpared(
					"3d auto reference: a matching trace found by name, a wrong one excluded with its reason",
					fixture("auto_ref_ok"),
					{
						"reference_side",
						"reference_side_local",
						"reference_top",
						"references_auto_side",
						"references_auto_top",
					}
				),
				expectFlag(
					"3d mirrored reference: a chart drawn as a mirror image (front and top) is named, not chased",
					fixture("ref_mirrored"),
					{ "reference_front_mirrored", "reference_top_mirrored" }
				),
				expectFlag(
					"3d colour match: a front half green where the reference's colour (its lighting taken out) is blue is named",
					fixture("colour_off"),
					{ "colour_match" }
				),
				expectSpared(
					"3d colour match: a model in its reference's colours, region by region",
					fixture("colour_ok"),
					{ "colour_match" }
				),
				expectFlag(
					"3d colour match, FRONT view: the model's right side green where the front picture shows it blue is named",
					fixture("colour_front_off"),
					{ "colour_match" }
				),
				expectSpared(
					"3d colour match, FRONT view: the right colours on the right sides (the model's right on the picture's left)",
					fixture("colour_front_ok"),
					{ "colour_match" }
				),
				expectFlag(
					"3d colour match, TOP view: the model's right side green where the top picture shows it blue is named",
					fixture("colour_top_off"),
					{ "colour_match" }
				),
				expectSpared(
					"3d colour match, TOP view: the right colours (its front on the right, the model's left at the top)",
					fixture("colour_top_ok"),
					{ "colour_match" }
				),
				expectSpared(
					"3d projection: a block painted with its side picture (seen from that camera it IS the picture) and a slanted decal straightened onto its top",
					fixture("project_ok"),
					{ "projection_" }
				),
				expectFlag(
					"3d projection: a picture that moved since it was traced (its object 40 px off the trace's frame) is named",
					fixture("project_misaligned"),
					{ "projection_alignment" }
				),
				expectSpared(
					"3d projection, detail mode: a studio-lit picture gives its engraving lines (and their relief), never its light, shadow or colour (each material's mean within 4/255)",
					fixture("project_detail"),
					{ "projection_" }
				),
				expectSpared(
					"3d relief: ornaments from a relief height field (a dome, a bust) are sound and at their asked size",
					fixture("relief_ok"),
					{
						"manifold",
						"wire_edges",
						"loose_verts",
						"degenerate_faces",
						"floating_parts",
						"inside_out",
						"size_vs_target",
					}
				),
				expectSpared(
					"3d take-apart: the bar slid out, THEN the lid lifted — every step clear, every part off — is not named",
					fixture("strip_ok"),
					{ "disassembly" }
				),
				expectFlag(
					"3d take-apart: the lid lifted first runs into the bar lying across it — named, with the pair",
					fixture("strip_blocked"),
					{ "disassembly" }
				),
				expectFlag(
					"3d take-apart: a part never taken off (the lid) is named",
					fixture("strip_incomplete"),
					{ "disassembly" }
				),
				expectSpared(
					"3d take-apart: a RUBBER sleeve stretched off over a lip squeezes past it (soft), is not named",
					fixture("strip_soft"),
					{ "disassembly" }
				),
				expectFlag(
					"3d take-apart: the same sleeve in STEEL jams on the lip — named",
					fixture("strip_soft_steel"),
					{ "disassembly" }
				),
				expectSpared(
					"3d take-apart: a flap held under a keeper TURNS out about its edge, then slides — clear, not named",
					fixture("strip_turn"),
					{ "disassembly" }
				),
				expectFlag(
					"3d take-apart: the same flap lifted straight up runs into the keeper — named",
					fixture("strip_turn_straight"),
					{ "disassembly" }
				),
				expectSpared(
					"3d per-part match: a part built where its traced outline is (the handle under the body) is not named",
					fixture("part_match_ok"),
					{ "part_match_side" }
				),
				expectFlag(
					"3d per-part match: a part built in the wrong place and size is named, though the whole outline overlaps",
					fixture("part_match_off"),
					{ "part_match_side" }
				),
				expectSpared(
					"3d per-part match: an earlier render's 16-bit PNG output (a projection leaked it) does not scramble the part ids — the right handle is not named",
					fixture("part_match_depth16"),
					{ "part_match_side" }
				),
				expectSpared(
					"3d per-part match: a feature boxed out with dont_care (a fin the picture lacks) does not shift the fit — the right handle is not named",
					fixture("part_match_dontcare"),
					{ "part_match_side" }
				),
				expectSpared(
					"3d per-part match: an outline-only part ('handle!') with a window the picture's part lacks is not named",
					fixture("part_match_outline"),
					{ "part_match_side" }
				),
				expectSpared(
					"3d trace_match pose=: a picture with the lid OPEN matches the model posed open (pose={Lid: min})",
					fixture("pose_match_ok"),
					{ "reference_side" }
				),
				expectFlag(
					"3d trace_match pose=: the same picture measured against the model at rest (lid shut) is named",
					fixture("pose_match_off"),
					{ "reference_side" }
				),
				if cadReady
					then expectSpared(
						"3d code CAD (a.cad): a filleted, bored, chamfered receiver at its hand-worked volume, a revolved barrel from a code file, mirrored grips — closed solids, clean meshes",
						fixture("cad_ok"),
						{
							"cad_solid",
							"manifold",
							"wire_edges",
							"loose_verts",
							"degenerate_faces",
							"inside_out",
							"floating_parts",
						}
					)
					else cadSkipped("3d code CAD (a.cad), the good parts"),
				if cadReady
					then expectFlag(
						"3d code CAD (a.cad): a surface handed over as a part (a sketch never extruded) is named",
						fixture("cad_open"),
						{ "cad_solid" }
					)
					else cadSkipped("3d code CAD (a.cad), a surface as a part"),
				expectSpared(
					"3d kit optimize: a dense master's game version keeps its surface (within the loss tolerance and the budget)",
					optimized("optimize_dense"),
					{ "optimize_loss", ".tris=", "manifold", "degenerate_faces" }
				),
				expectFlag(
					"3d kit optimize: a game version starved of triangles is caught (the loss is measured, never assumed)",
					optimized("optimize_dense", { "--budget=60" }),
					{ "optimize_loss" }
				),
				expectFlag(
					"3d kit optimize: a 2048 master's game version keeps its one 2048 map (Roblox was seen keeping it: no 1024 map, no cut)",
					optimized("optimize_maps"),
					{ "game maps: main 2048 " }
				),
				gameFidelity(nil),
				if skullBuilt()
					then expectFail(
						"3d game_fidelity: the old re-derived game maps (experiment 2's V0) on the skull's game mesh are caught",
						gameFidelity({
							"color=kit/selftest/blender/game_fidelity/v0_human_skull_game_color.png",
							"normal=kit/selftest/blender/game_fidelity/v0_human_skull_game_normal.png",
						}),
						{ "game_fidelity", "FAIL" }
					)
					else gameFidelity({ "skipped" }),
				-- the car rim's S1 game version (the owner, 2026-11-10: "Yes, fix it first" - a sawtoothed lip, a slit
				-- where a spoke meets it, a lumpy bore, threads only painted on): it PASSED the 512 px numbers, so the
				-- close-up pass must catch it, always; and the same version against itself shows nothing up close
				rimS1(false),
				expectFail(
					"3d game_fidelity up close: the car rim's S1 game version (sawtoothed lip, slit, lumpy bore, painted threads) is caught",
					rimS1(true),
					{ "game_fidelity", "FAIL (close-up)" }
				),
				handHeroRefused,
				handHeroBuilds,
				handOptimized,
				expectMore(
					'3d an ENGRAVED surface is seen (pattern="engraved": its grooves shade like relief, never an empty plate)',
					fixture("plate_engraved"),
					fixture("plate_plain"),
					"crease_density",
					0.25
				),
				expectFlag("3d fastener gate (a pin across open air)", fixture("loose_pin"), { "fastener_support" }),
				expectFlag("3d plate gate (half a plate in the air)", fixture("overhang_plate"), { "plate_support" }),
				expectSpared(
					"3d plate gate spares plates seated on their host (the kit's own plate, flush, sunk 1 mm)",
					fixture("plate_seated"),
					{ "plate_support" }
				),
				expectSpared(
					"3d seated details stay on a curved host (a.seat: letters and a badge round a drum)",
					fixture("text_seated"),
					{ "floating_parts", "plate_support" }
				),
				expectFlag("3d marking gate (letters off the edge)", fixture("bad_marking"), { "marking_placement" }),
				expectFlag("3d clear-path gate (a barrel never bored)", fixture("filled_bore"), { "clear:Bore" }),
				expectFlag(
					"3d visibility gate (an internal spring you can see)",
					fixture("visible_internal"),
					{ "part_visibility" }
				),
				expectFlag(
					"3d design-spec gates (missing, detached, standing off, undescribed)",
					fixture("spec_mismatch"),
					{ "spec_parts", "spec_attach", "attach_gaps", "spec_undocumented" }
				),
				expectFlag("3d mechanism gate (a slide buried in its frame)", fixture("jammed_slide"), { "mechanism" }),
				-- THE WHOLE TRAVEL (the owner's limitations page, D-R05): a joint is posed at stops set from how far its
				-- group moves and how deep it is, never five whatever the travel
				expectFlag(
					"3d mechanism gate (a pin standing BETWEEN the old five stops of a runner's travel)",
					fixture("travel_pin"),
					{ "mechanism", "Runner into Pin" }
				),
				expectSpared(
					"3d mechanism gate spares the same runner with the pin beside its path",
					fixture("travel_clear"),
					{ "mechanism" }
				),
				expectFlag(
					"3d mechanism gate (a runner that left the seats it rested on, into a pin of the same body between the stops)",
					fixture("travel_seated"),
					{ "mechanism", "Runner in Pin" }
				),
				expectSpared(
					"3d mechanism gate: a slide racking into its recoil SPRING compresses it (soft), is not named",
					fixture("slide_spring"),
					{ "mechanism" }
				),
				expectFlag(
					"3d mechanism gate: the same slide racking into a solid STOP is a jam — named",
					fixture("slide_spring_steel"),
					{ "mechanism" }
				),
				expectFlag(
					"3d mechanism gate (a lid swinging through a wall: caught in its TRAVEL, the parts NAMED)",
					fixture("lid_into_wall"),
					{ "mechanism", "Lid in Wall" }
				),
				expectFlag(
					"3d mechanism gate (a part lifted THROUGH a closed cover: caught mid-travel)",
					fixture("sequence_missing"),
					{ "mechanism" }
				),
				expectSpared(
					"3d mechanism gate checks a SEQUENCE as one (after=: the cover slides off, then the insert lifts out)",
					fixture("sequence_ok"),
					{ "mechanism" }
				),
				expectSpared(
					"3d mechanism gate spares a slide clear in its slot beside a shared seam (two blocks, one face)",
					fixture("seam_clear"),
					{ "mechanism" }
				),
				expectFlag(
					"3d action cycle gate (a pin let down into a turning wheel's path: each joint clear ALONE, caught together)",
					fixture("cycle_pin_in_path"),
					{ "mechanism_cycle" }
				),
				expectSpared(
					"3d action cycle gate spares the same wheel and pin TIMED (the pin comes down after the lug has passed)",
					fixture("cycle_pin_timed"),
					{ "mechanism_cycle" }
				),
				-- (his D-R05, the rest: the cycle's poses are picked by how far the parts move, never by a count of frames)
				expectFail(
					"3d action cycle: a wheel swung half round in two frames, through a pin only in the way while both move - caught between the frames",
					fixture("cycle_fast_pin"),
					{ "mechanism_cycle", "'pin' drives into 'wheel'" }
				),
				expectSpared(
					"3d action cycle: the same swing with the pin held up is not flagged",
					fixture("cycle_fast_clear"),
					{ "mechanism_cycle" }
				),
				-- A MODEL'S OWN MOTION IN THE GAME (the owner's method lists: keyframes, curves, loops, animation export;
				-- stage G3): each action cycle is written as the table the game plays; a loop must close
				expectSpared(
					"3d action cycle in the game: a looped cycle that ends where it began is written for the game and not flagged",
					fixture("cycle_loop"),
					{ "cycle_loop", "mechanism_cycle" }
				),
				expectFail(
					"3d action cycle in the game: a cycle said to loop that ends half a turn away fails cycle_loop by the joint's name",
					fixture("cycle_loop_jump"),
					{ "cycle_loop", "Wheel ends at 180" }
				),
				-- the owner on the revolver's build 4 (2026-11-11): "imagine you actually try to shoot it with that type of
				-- trigger" - its shot swung the trigger 4 mm toward the muzzle (+8 degrees about +X turns a blade forward)
				expectFlag(
					"3d mechanism gate (a trigger pushed toward the MUZZLE at full travel, as the revolver's build 4 fired)",
					fixture("trigger_pushed"),
					{ "mechanism", "toward the MUZZLE" }
				),
				expectSpared(
					"3d mechanism gate spares the same trigger pulled back toward the grip",
					fixture("trigger_pulled"),
					{ "toward the MUZZLE" }
				),
				expectFlag(
					"3d graveyard G9 (the Gjallarhorn's round-3 line: a hero's panels traced by colour off a lit render)",
					function()
						return Run.content(
							"graveyard G9",
							Run.tool("python"),
							{ "kit/selftest/refs/check_graveyard_rows.py", "--rule", "G9" }
						)
					end,
					-- only a REAL refusal says these: the check's pass line carries the rule's id too ("graveyard (G9): ...")
					{ "G9 refuses", "Pearl panels -> G9" }
				),
				expectSpared(
					"3d graveyard G9 spares a redrawn panel and gold trim traced by colour (Scarborough Fair, 9/10)",
					function()
						return Run.content(
							"graveyard G9 clean",
							Run.tool("python"),
							{ "kit/selftest/refs/check_graveyard_rows.py", "--rule", "G9", "--clean" }
						)
					end,
					{ "G9 refuses", "-> G9" }
				),
				expectFlag(
					"3d graveyard G10 (the revolver's build-4 line: a hero trigger extruded from its outline, 5 mm thick)",
					function()
						return Run.content(
							"graveyard G10",
							Run.tool("python"),
							{ "kit/selftest/refs/check_graveyard_rows.py", "--rule", "G10" }
						)
					end,
					{ "G10 refuses", "Trigger and trigger guard -> G10" }
				),
				expectSpared(
					"3d graveyard G10 spares a trigger inflated from the photo, its sections crowned",
					function()
						return Run.content(
							"graveyard G10 clean",
							Run.tool("python"),
							{ "kit/selftest/refs/check_graveyard_rows.py", "--rule", "G10", "--clean" }
						)
					end,
					{ "G10 refuses", "-> G10" }
				),
				-- the owner on the revolver's build 4 (2026-11-11): "is some of the body not fully filled in?" - its side
				-- view against the photo's trace: IoU 0.936, and a 116 mm2 wedge open behind the trigger (the real masks)
				expectFlag(
					"3d silhouette holes (the revolver's build 4: a see-through wedge behind the trigger the photo shows solid)",
					function()
						return Run.content("silhouette holes", Run.tool("python"), {
							"kit/tools/silhouette_holes.py",
							"--ref",
							"kit/selftest/refs/revolver_b4_side_ref.png",
							"--model",
							"kit/selftest/refs/revolver_b4_side_model.png",
							"--mm-per-px",
							"0.25",
						})
					end,
					{ "silhouette_holes", "x 68.8-87.8 mm" }
				),
				expectSpared("3d silhouette holes spares the photo's outline against itself", function()
					return Run.content("silhouette holes clean", Run.tool("python"), {
						"kit/tools/silhouette_holes.py",
						"--ref",
						"kit/selftest/refs/revolver_b4_side_ref.png",
						"--model",
						"kit/selftest/refs/revolver_b4_side_ref.png",
						"--mm-per-px",
						"0.25",
					})
				end, { "hole(s)" }),
				linesMissing,
				linesAaa,
				linesClean,
				-- taste: noise never beats craft; see-through slats and grooves carved into wood are named
				expectOrder(
					"3d noise never beats craft (real boards above carved grooves and above flat paint)",
					fixture("plank_grained"),
					{
						fixture("plank_grooved"),
						fixture("plank_combed"),
						fixture("plank_carved_sly"),
						fixture("plank_comb_fused"),
						fixture("plank_fused_nub"),
						fixture("plank_floater_seams"),
						fixture("plank_hidden_wood"),
						fixture("plank_metal_carved"),
						fixture("plank_recess_grooves"),
						fixture("plank_flat"),
					}
				),
				expectFlag(
					"3d wood-carving gate (grooves carved into planks)",
					fixture("plank_grooved"),
					{ "wood_grooves" }
				),
				expectFlag(
					"3d wood-carving gate counts what is carved (one comb cutter, many grooves)",
					fixture("plank_combed"),
					{ "wood_grooves" }
				),
				expectFlag(
					"3d wood-carving gate sees a cut in the part's own material (combs that scrape the surface)",
					fixture("plank_carved_sly"),
					{ "wood_grooves" }
				),
				-- (its warning would fire either way: one groove-shaped cut names it — what proves the tracing is the COUNT)
				expectMore(
					"3d wood-carving gate traces every material of a cutter (a comb fused of a spine and steel teeth: 28 grooves)",
					fixture("plank_comb_fused"),
					fixture("plank_grained"),
					"carved_grooves",
					20
				),
				expectFlag(
					"3d wood-carving gate finds wood per face (a block fused into a steel nub, then grooved)",
					fixture("plank_fused_nub"),
					{ "wood_grooves" }
				),
				expectFlag(
					"3d wood-carving gate sees seams baked on wood (floater lines draw the grooves into the maps)",
					fixture("plank_floater_seams"),
					{ "wood_grooves" }
				),
				expectMore(
					"3d wood-carving gate sees grooves cut into an earlier recess (its floor is carved wood)",
					fixture("plank_recess_grooves"),
					fixture("plank_grained"),
					"carved_grooves",
					15
				),
				expectSpared(
					"3d stencils are not seams (a.text on wood is a marking, never a baked line)",
					fixture("plank_stencils"),
					{ "wood_grooves" }
				),
				expectMore(
					"3d carving cannot carve a model below the wooden line (the walls cut into wood are the wood's own)",
					fixture("plank_grained"),
					fixture("plank_metal_carved"),
					"craft",
					0.1
				),
				expectMore(
					"3d carving is measured on the wood that is seen (hidden internal sheets do not water it down)",
					fixture("plank_hidden_wood"),
					fixture("plank_grained"),
					"carved_share",
					0.08
				),
				expectFlag(
					"3d cut-through gate (a saw slot splits a board in two)",
					fixture("cut_through"),
					{ "cut_through" }
				),
				expectFlag(
					"3d tiny-cut warning (pin holes cut instead of baked)",
					fixture("tiny_cuts"),
					{ "tiny_cuts" }
				),
				expectSpared(
					"3d cut-through spares a split by design (a.cut(..., through=True))",
					fixture("cut_through_ok"),
					{ "cut_through" }
				),
				expectClean(
					"refs measure keeps the front on the right (an X-long wedge, back short, front tall)",
					function()
						local out = Config.build("selftest/refs")
						pcall(fs.removeFile, out .. "/_selftest_wedge.measure.json") -- (never a previous run's answer)
						local measured = Content.blenderStep("measure wedge", "kit/refs/measure.py", {
							"kit/selftest/refs/wedge_x.obj",
							"--name",
							"_selftest_wedge",
							"--out",
							out,
						})
						if not measured.ok then
							return measured
						end
						return Run.content(
							"measure wedge check",
							Run.tool("python"),
							{ "kit/selftest/refs/check_measure.py", out .. "/_selftest_wedge.measure.json" }
						)
					end,
					{ "MIRRORED" }
				),
				expectFlag(
					'3d material names keep their promise ("gold" that is grey plastic, "brass" that is no metal)',
					fixture("fake_gold"),
					{ "material_values" }
				),
				expectFlag(
					"3d physically based values: a metal at 60 sRGB and half a metal (a dark gun finish is a coating) are named",
					fixture("pbr_dark_metal"),
					{ "pbr_values" }
				),
				expectSpared(
					"3d physically based values: finishes and measured materials (a satin cloth, a stylised opt-out)",
					fixture("pbr_ok"),
					{ "pbr_values" }
				),
				expectSpared(
					"3d the asset's pack: a part built ONLY from pack values (traced mm profile, sourced size, measured colour) builds and is judged",
					fixture("pack_reads"),
					{ "manifold", "floating", "pbr_values", "material_values" }
				),
				expectFlag(
					"3d roughness variation: a big panel at one roughness (measured on the baked map) is named",
					fixture("rough_flat"),
					{ "roughness_variation" }
				),
				expectSpared(
					"3d roughness variation: the same panel worn, grimy and coated varies at every scale",
					fixture("rough_varied"),
					{ "roughness_variation" }
				),
				expectFlag(
					"3d dark finishes: two big dark materials 7 sRGB apart (the Glock's 'same blue-navy') are named",
					fixture("dark_alike"),
					{ "dark_finishes" }
				),
				expectSpared(
					"3d dark finishes: the same block with the owner-rated frame / slide step reads apart",
					fixture("dark_apart"),
					{ "dark_finishes" }
				),
				expectSpared(
					"3d sculpt: a sculpted bust (blends, strokes, carves, creases, ridged hide, a loft taken in as clay) is one closed, clean part",
					fixture("sculpt_bust"),
					{ "sculpt_detail", "manifold", "degenerate_faces", "open_parts" }
				),
				expectFlag(
					"3d sculpt: a crease thinner than the sculpt's voxels is named (the meshing cannot keep it)",
					fixture("sculpt_thin"),
					{ "sculpt_detail" }
				),
				expectSpared(
					"3d sculpt texels: a ridged sculpt's UVs follow its form — its 10 mm end-grain rings get 4+ px of map",
					fixture("sculpt_texels"),
					{ "pattern_resolution" }
				),
				expectFlag(
					"3d sculpt texels: 2 mm rings on the same map are under 4 px — named (they would bake to mottling)",
					fixture("sculpt_texels_fine"),
					{ "pattern_resolution" }
				),
				expectSpared(
					"3d looks: a shelf of real surface recipes with a life (vary, dust, end grain rings) builds physically based",
					fixture("looks_shelf"),
					{ "pbr_values", "material_values", "dark_finishes" }
				),
				expectFlag(
					"3d see-through gate (slats with gaps, nothing behind)",
					fixture("slatted_lid"),
					{ "see_through" }
				),
				expectSpared(
					"3d see-through spares real openings (a wooden ladder)",
					fixture("wood_ladder"),
					{ "see_through" }
				),
				expectMore(
					"3d empty sees texture (flat paint reads empty, the same boards with grain do not)",
					fixture("plank_flat"),
					fixture("plank_grained"),
					"empty_share",
					0.1
				),
				-- the ratchet is REPORT-ONLY (a warning: the score never blocks a build), but it must still be named
				expectFlag("3d ratchet (worse than the accepted build)", fixture("ratchet"), { "ratchet" }),
				expectFlag(
					"3d ratchet: a floor measured by other code vouches only for its own script",
					fixture("ratchet_stale"),
					{ "ratchet" }
				),
				expectFlag(
					"3d ratchet: an empty floor record is a broken floor (it is named, never vanishes)",
					fixture("ratchet_empty"),
					{ "ratchet" }
				),
				-- the presentation studio must not lie about colour (everything the owner and the judges look at)
				expectClean("3d studio is honest (a chart of known albedos renders true)", function()
					return Content.blenderStep("studio chart", "kit/selftest/blender/build_studio_chart.py", {})
				end, { "LYING" }),
				expectFail("3d studio check catches a lying studio (the old AgX at 0 EV)", function()
					return Content.blenderStep(
						"studio chart (lie)",
						"kit/selftest/blender/build_studio_chart.py",
						{ "--lie" }
					)
				end, { "LYING" }),
				-- sloppy work is named: under the quality bar (report-only: a warning) AND every taste problem
				expectFlag(
					"3d quality bar + taste warnings",
					fixture("sloppy"),
					{ "quality", "hidden_parts", "palette", "detail", "symmetry" }
				),
				expectFail("vfx cut-off gate (smoke outlives the preset)", function()
					return Content.vfxPreviewStep(
						{ "cut_off" },
						"kit/selftest/vfx/preview",
						Config.build("selftest/vfx")
					)
				end, { "cut_off" }),
				expectFail(
					"vfx v3 gate (cut-off layer, unknown texture / point, sheet-less flipbook, flipbook-less sheet, ignored key)",
					function()
						return Content.vfxPresetsStep("kit/selftest/vfx/v3")
					end,
					{ "cut off", "unknown texture", "unknown point", "not a sheet", "add a flipbook", "did you mean" }
				),
				expectFail(
					"vfx stage locks on a NEW scene piece (its set's timing animatic and its style sheet, the owner's yes as they are now)",
					function()
						return Content.vfxPresetsStep("kit/selftest/vfx/stages")
					end,
					{
						"stages: the timing animatic of stage_probe",
						"stages: the style sheet of new_staged",
						"--stage style",
					}
				),
				expectFail(
					"vfx legacy keys on a NEW piece (spreadAngle, fov, frequency, a tilting ground card: errors after 2026-11-18)",
					function()
						return Content.vfxPresetsStep("kit/selftest/vfx/legacy")
					end,
					{
						"spreadAngle",
						"legacy `fov`",
						"legacy `frequency`",
						"FacingCameraWorldUp",
						"made after 2026-11-18",
					}
				),
				expectFail("vfx library rule (an effect made but not saved in the vault)", function()
					return Run.content("vfx vault", Run.tool("python"), {
						"kit/vfx/vault.py",
						"check",
						"--effects",
						"kit/selftest/vfx/vault/effects",
						"--textures",
						"kit/selftest/vfx/vault/textures",
						"--build",
						Config.build("selftest/vfx_vault_build"),
						"--out",
						Config.build("selftest/vfx_vault_empty"),
					})
				end, { "missing", "unsaved_spark" }),
				function() -- and a good v3 preset (every layer kind) still passes it
					return Content.vfxPresetsStep("kit/selftest/vfx/v3_good")
				end,
				expectFail("vfx scene-breakdown gate (no frames, no build: no scene / a half breakdown)", function()
					return Content.vfxPresetsStep("kit/selftest/vfx/scene")
				end, {
					"preset_without_beats: scene: no scene breakdown",
					"preset_half_breakdown: scene: no beat sheet",
					"no measured colours",
					"preset_unapproved_chart: scene: chart not approved",
				}),
				expectFail(
					"vfx quality locks (a model's own chart approval / our own build renders as scene frames)",
					function()
						return Content.vfxPresetsStep("kit/selftest/vfx/scene")
					end,
					{
						"preset_model_chart: scene: chart approved by",
						"preset_build_frames: scene: measured colours",
						"our own build renders",
					}
				),
				-- the ORIGINAL route (2026-11-10, R-vfx-5): a director brief alone built the eight originals the owner rated
				-- 4-6 on 2026-10-24; a new original needs REAL frames (a refs set) held to a scene's breakdown + his chart
				expectFail(
					"vfx original route (a brief alone / real frames with no owner chart / a half breakdown)",
					function()
						return Content.vfxPresetsStep("kit/selftest/vfx/scene_original")
					end,
					{
						"preset_original_no_refs: scene: an original needs REAL frames too",
						"preset_original_unapproved: scene: chart not approved",
						"preset_original_half: scene: no beat sheet",
					}
				),
				function(): Run.Step -- and an original WITH real frames + the owner's chart builds (the lock is not a wall)
					-- under the fixture's own go-ahead for originals (synthetic, like its chart's approval), never the
					-- project's board/locks.json: a fresh project's empty board proves the same thing
					local Locks = require("../lib/locks")
					fs.writeDir(Config.build("selftest"))
					local real = Locks.FILE
					Locks.FILE = Config.build("selftest") .. "/original_locks.json"
					local yes = { by = "owner", words = "the fixture's own yes", date = "2026-11-10" }
					fs.writeFile(
						Locks.FILE,
						serde.encode(
							"json",
							{ grandfathered = {}, approvals = { vfx = { originals = yes } }, waivers = {} }
						)
					)
					Locks.reset()
					local ok, step = pcall(Content.vfxPresetsStep, "kit/selftest/vfx/scene_original_good")
					Locks.FILE = real
					Locks.reset()
					if not ok then
						error(step)
					end
					return step
				end,
				expectFlag("vfx rule 7 (a loved effect's look on another source is named a RE-SKIN)", function()
					return Run.content("vfx refs norms (rule 7)", Run.tool("python"), {
						"kit/vfx/refs.py",
						"norms",
						"reskin_named",
						"--effects",
						"kit/selftest/vfx/reskin/effects",
						"--verdicts",
						"kit/selftest/vfx/reskin/verdicts.json",
						"--measured",
						"kit/selftest/vfx/reskin/refs_measured",
					})
				end, { "RE-SKIN of gloria" }),
				expectFlag("vfx rule 7 (the same look the owner ASKED for passes, quoted in beats.md)", function()
					return Run.content("vfx refs norms (rule 7, asked)", Run.tool("python"), {
						"kit/vfx/refs.py",
						"norms",
						"asked_for",
						"--effects",
						"kit/selftest/vfx/reskin/effects",
						"--verdicts",
						"kit/selftest/vfx/reskin/verdicts.json",
						"--measured",
						"kit/selftest/vfx/reskin/refs_measured",
					})
				end, { "the owner asked for it" }),
				-- the owner's Rasengan, 2.0/10 (2026-10-15: untextured Neon ribbons read as PLASTIC), a bad example forever
				-- (card b6m2): the director's untextured-neon-mesh rule must name a Neon share and a Neon volume, and
				-- pass a few accent rings
				expectFlag(
					"vfx director rule untextured-neon-mesh (5 of 7 meshes untextured Neon: plastic)",
					function()
						return Run.content("vfx director lint (neon share)", Run.tool("python"), {
							"kit/vfx/director.py",
							"lint",
							"kit/selftest/vfx/neon_plastic/bad_neon_share.json",
						})
					end,
					{ "untextured-neon-mesh", "untextured Neon" }
				),
				expectFlag("vfx director rule untextured-neon-mesh (an untextured Neon sphere: a volume)", function()
					return Run.content("vfx director lint (neon volume)", Run.tool("python"), {
						"kit/vfx/director.py",
						"lint",
						"kit/selftest/vfx/neon_plastic/bad_neon_volume.json",
					})
				end, { "untextured-neon-mesh", "sphere" }),
				function(): Run.Step -- (a few untextured accent rings among textured meshes hold every taste rule)
					return Run.content("vfx director lint (neon accents)", Run.tool("python"), {
						"kit/vfx/director.py",
						"lint",
						"kit/selftest/vfx/neon_plastic/good_neon_accents.json",
					})
				end,
				-- a mesh with no material IS Neon (VfxStage's default): the rule read only an explicit "Neon" (2026-11-10)
				expectFlag("vfx director rule untextured-neon-mesh (the same ribbons, Neon by default)", function()
					return Run.content("vfx director lint (implicit neon)", Run.tool("python"), {
						"kit/vfx/director.py",
						"lint",
						"kit/selftest/vfx/neon_plastic/bad_neon_implicit.json",
					})
				end, { "untextured-neon-mesh", "5 of 7" }),
				-- the owner's NAMED VFX faults (2026-11-10), each on the REAL piece AS HE JUDGED IT (the version current at
				-- his verdict, kit/selftest/vfx/owner_faults/README.md): every rule and gate passed all eight originals he
				-- rated 4-6 on 2026-10-24 - seam passed 10 of 10 recording checks. The loved twin of each must still pass
				expectFail(
					"vfx recording gate frames_on_screen (seam 6/10: 'Bad impact frames' - re-framed over a speck)",
					function()
						return Run.content("vfx gate replay (seam)", Run.tool("node"), {
							"kit/vfx/gate_replay.cjs",
							"kit/selftest/vfx/owner_faults/seam/metrics.json",
							"kit/selftest/vfx/owner_faults/seam/expanded.json",
							"--checks",
							"frames_on_screen",
						})
					end,
					{ "frames_on_screen", "1.32" }
				),
				expectFail("vfx recording gate frames_on_screen (sandfall 6/10: 'Bad impact frames')", function()
					return Run.content("vfx gate replay (sandfall)", Run.tool("node"), {
						"kit/vfx/gate_replay.cjs",
						"kit/selftest/vfx/owner_faults/sandfall/metrics.json",
						"kit/selftest/vfx/owner_faults/sandfall/expanded.json",
						"--checks",
						"frames_on_screen",
					})
				end, { "frames_on_screen", "2.4" }),
				expectFail(
					"vfx recording gate frames_on_screen (quicksilver 6/10: 'Impact frames very low quality')",
					function()
						return Run.content("vfx gate replay (quicksilver)", Run.tool("node"), {
							"kit/vfx/gate_replay.cjs",
							"kit/selftest/vfx/owner_faults/quicksilver/metrics.json",
							"kit/selftest/vfx/owner_faults/quicksilver/expanded.json",
							"--checks",
							"frames_on_screen",
						})
					end,
					{ "frames_on_screen", '"0.6: 0.005"' }
				),
				expectFail(
					"vfx recording gate frames_on_screen (noctiluca 6/10: 'The impact franes are bad')",
					function()
						return Run.content("vfx gate replay (noctiluca)", Run.tool("node"), {
							"kit/vfx/gate_replay.cjs",
							"kit/selftest/vfx/owner_faults/noctiluca/metrics.json",
							"kit/selftest/vfx/owner_faults/noctiluca/expanded.json",
							"--checks",
							"frames_on_screen",
						})
					end,
					{ "frames_on_screen", '"0.6: 0"' }
				),
				function(): Run.Step -- starblade round 6 (9.5): re-framed frames over a strike filling the shot hold
					return Run.content("vfx gate replay (starblade r6)", Run.tool("node"), {
						"kit/vfx/gate_replay.cjs",
						"kit/selftest/vfx/owner_faults/starblade/metrics.json",
						"kit/selftest/vfx/owner_faults/starblade/expanded.json",
						"--checks",
						"frames_on_screen",
					})
				end,
				function(): Run.Step -- sumi_seal (praised): a closeup over a strike at 0.058 of the shot holds
					return Run.content("vfx gate replay (sumi_seal)", Run.tool("node"), {
						"kit/vfx/gate_replay.cjs",
						"kit/selftest/vfx/owner_faults/sumi_seal/metrics.json",
						"kit/selftest/vfx/owner_faults/sumi_seal/expanded.json",
						"--checks",
						"frames_on_screen",
					})
				end,
				expectFlag(
					"vfx director rule lit-puff-swarm (quenchstrike 6/10: 'The Effects like Smoke looks horrible')",
					function()
						return Run.content("vfx director lint (quenchstrike as judged)", Run.tool("python"), {
							"kit/vfx/director.py",
							"lint",
							"kit/selftest/vfx/owner_faults/quenchstrike/preset.json",
						})
					end,
					{ "lit-puff-swarm", "steam_column", "steam_skirt" }
				),
				expectFlag("vfx director rule lit-puff-swarm (nuke_v3: 'the smoke looks bad around')", function()
					return Run.content("vfx director lint (nuke_v3 as judged)", Run.tool("python"), {
						"kit/vfx/director.py",
						"lint",
						"kit/selftest/vfx/owner_faults/nuke_v3/preset.json",
					})
				end, { "lit-puff-swarm", "surge_0" }),
				function(): Run.Step -- nuke_v4 (8.7): the same mushroom with ONE simulated surge card holds every taste rule
					return Run.content("vfx director lint (nuke_v4 as judged)", Run.tool("python"), {
						"kit/vfx/director.py",
						"lint",
						"kit/selftest/vfx/owner_faults/nuke_v4/preset.json",
					})
				end,
				expectFlag(
					"vfx director rule untextured-solid-mesh (quicksilver 6/10: 'Meshs ... very low quality')",
					function()
						return Run.content("vfx director lint (quicksilver as judged)", Run.tool("python"), {
							"kit/vfx/director.py",
							"lint",
							"kit/selftest/vfx/owner_faults/quicksilver/preset.json",
						})
					end,
					{ "untextured-solid-mesh", "8 of 8", "SmoothPlastic" }
				),
				-- every taste rule with evidence catches the piece it was made from (a HOLLOW rule fails: 2026-10-24's
				-- few-giant-puffs had been narrowed until it no longer fired on quenchstrike)
				function(): Run.Step
					return Run.content("vfx director calibrate (evidence)", Run.tool("python"), {
						"kit/vfx/director.py",
						"calibrate",
						"--evidence-only",
					})
				end,
				-- the owner's REDO of flame_arc_keybeat (2026-11-10), both faults on the real piece as he judged it:
				-- SCOPE ("you're saying Flame Arc dance, so you're saying dance, the whole thing basically") - one beat
				-- of five named as the whole technique; QUALITY ("It's not there with ... what I'm seeing from the scene") -
				-- its test frame against the scene's key frame (numbers only; the scene's frames stay private)
				expectFail("vfx scope (one beat of Flame Arc shown under the whole technique's name)", function()
					return Content.vfxPresetsStep("kit/selftest/vfx/scope")
				end, {
					"preset_flame_arc_keybeat: scene: scope:",
					"name no beat",
					"preset_flame_arc_tagged: scene: scope: builds beat(s) 1 of 5",
				}),
				function(): Run.Step -- and one beat named for that beat (flame_arc_dance_arc) builds
					return Content.vfxPresetsStep("kit/selftest/vfx/scope_good")
				end,
				expectFail("vfx keyread (flame_arc_keybeat's test frame short of the scene's key frame)", function()
					return Run.content("vfx keyread (flame_arc_keybeat)", Run.tool("python"), {
						"kit/vfx/keyread.py",
						"--scene-numbers",
						"kit/selftest/vfx/owner_faults/flame_arc_keybeat/flame_arc_set.keyread.json",
						"--frame",
						"kit/selftest/vfx/owner_faults/flame_arc_keybeat/key_frame.png",
					})
				end, { "short of the scene's key frame", "coverage", "pieces" }),
				function(): Run.Step -- nuke_v4 (8.7) beside its real test footage holds
					return Run.content("vfx keyread (nuke_v4)", Run.tool("python"), {
						"kit/vfx/keyread.py",
						"--scene-numbers",
						"kit/selftest/vfx/owner_faults/nuke_v4/nuke_set.keyread.json",
						"--frame",
						"kit/selftest/vfx/owner_faults/nuke_v4/key_frame.png",
					})
				end,
				-- the chart approval is the owner's OWN look at THIS chart (2026-11-11, the owner on flame_arc, REDO:
				-- "Are you even using the VFX pipeline properly?"): the piece he judged, on its chart's "owner blanket
				-- approval" (an agent's label), and on a chart re-timed after his approval, are both named; the same piece on
				-- a chart he approved himself builds
				expectFail(
					"vfx chart owner (flame_arc on a blanket approval an agent wrote; a chart re-timed after his approval)",
					function()
						return Content.vfxPresetsStep("kit/selftest/vfx/chart_owner")
					end,
					{
						"preset_flame_arc: scene: chart approval is not the owner's own look",
						"preset_flame_arc_retimed: scene: the chart changed since the owner approved it",
					}
				),
				function(): Run.Step
					return Content.vfxPresetsStep("kit/selftest/vfx/chart_owner_good")
				end,
				-- dailies (the VFX studio-route plan, V0, 2026-11-12): a made recording beside a made scene through the
				-- real command. The good case must SAY each known difference (the scene's fire is there in one frame, on
				-- twos, and stays; ours grows, freezes four frames, goes), end with LOOK: <folder> and make strips a
				-- reader gets at full size; a recording that shows nothing must FAIL the dailies - laid beside a scene
				-- it would otherwise look like a page that was made
				function(): Run.Step
					return Run.content(
						"vfx dailies (made clips: ours beside the scene, frame by frame)",
						Run.tool("python"),
						{ "kit/selftest/vfx/dailies/run.py", "good" }
					)
				end,
				expectFail("vfx dailies (a recording that shows nothing)", function()
					return Run.content(
						"vfx dailies (blank)",
						Run.tool("python"),
						{ "kit/selftest/vfx/dailies/run.py", "blank" }
					)
				end, { "ours never lights up" }),
				-- the style sheet (the VFX studio-route plan, V1, 2026-11-12) on a made project: both beats must come out
				-- as pairs a reader gets at full size, with an id that holds for the preset and is another once the
				-- preset is edited; a recording that shows nothing is NOT a sheet the owner can approve
				function(): Run.Step
					return Run.content(
						"vfx stylesheet (made project: every beat a pair, its id follows the preset)",
						Run.tool("python"),
						{ "kit/selftest/vfx/stylesheet/run.py", "good" }
					)
				end,
				expectFail("vfx stylesheet (a beat that never lights up)", function()
					return Run.content(
						"vfx stylesheet (blank)",
						Run.tool("python"),
						{ "kit/selftest/vfx/stylesheet/run.py", "blank" }
					)
				end, { "not a sheet he can approve", "ours never lights up" }),
				-- the timing animatic (the VFX studio-route plan, V2, 2026-11-12) on a made project, no browser (its
				-- recordings are made from the plan itself, frame by frame as the player's recorder makes them): the
				-- animatic must pass its own check of its recording - every beat hits where the plan says, at the
				-- plan's share - with its video and beat pages, an effect on its timing passing, an id that is another
				-- once the chart is re-timed, and the old plan's recording then REFUSED (never given a new record); and
				-- a built effect whose beat arrives THREE FRAMES LATE against the animatic must be named (the plan's
				-- done-when). The made project holds no approval of the owner's, and the summary must say so: it is
				-- "its animatic", never "its approved motion"
				function(): Run.Step
					return Run.content(
						"vfx animatic (made project: it hits where its plan says, its id follows the chart)",
						Run.tool("python"),
						{ "kit/selftest/vfx/animatic/run.py", "good" }
					)
				end,
				expectFail("vfx animatic (an effect three frames late against its animatic)", function()
					return Run.content(
						"vfx animatic (late)",
						Run.tool("python"),
						{ "kit/selftest/vfx/animatic/run.py", "late" }
					)
				end, { "drifts from its animatic (which the owner has not approved yet)", "3 of its frames" }),
				-- SHOCKWAVE DISTORTION, BAKED (the VFX methods audit, stage 30): the comp's "shock" starter by the real command
				-- - its ring bends the picture where it is, on its own radius, and nothing anywhere else; the packer packs
				-- it; the gate takes it (the row stays partly: its own sheet, not the scene behind it). A ring with nothing
				-- to bend, and one stronger than its width allows, must be refused
				function(): Run.Step
					return Run.content(
						"vfx shock (a ring that bends the picture where it is and nowhere else)",
						Run.tool("python"),
						{ "kit/selftest/vfx/shock/run.py", "good" }
					)
				end,
				expectFail("vfx shock (a ring with nothing to bend)", function()
					return Run.content(
						"vfx shock (flat)",
						Run.tool("python"),
						{ "kit/selftest/vfx/shock/run.py", "flat" }
					)
				end, { "bends = " }),
				expectFail("vfx shock (a ring stronger than its width allows)", function()
					return Run.content(
						"vfx shock (fold)",
						Run.tool("python"),
						{ "kit/selftest/vfx/shock/run.py", "fold" }
					)
				end, { "three tenths of its" }),
				-- SOLID BLOCKING FOR THE ANIMATIC (the owner's limitations file, F-R07; the VFX methods audit, stage 29): a
				-- made chart's pillar and slab through the animatic's own plan - seen, on the ground and touching from
				-- three angles, a ball covering what a pinhole camera says, real shapes in the preset, a chart of cards
				-- keeping its id; a solid hidden behind another, and one outside every picture, must be refused
				function(): Run.Step
					return Run.content(
						"vfx blocking (solid beats seen from the gameplay angles; a chart of cards keeps its id)",
						Run.tool("python"),
						{ "kit/selftest/vfx/blocking/run.py", "good" }
					)
				end,
				expectFail("vfx blocking (a solid hidden behind another)", function()
					return Run.content(
						"vfx blocking (hidden)",
						Run.tool("python"),
						{ "kit/selftest/vfx/blocking/run.py", "hidden" }
					)
				end, { "is hidden behind" }),
				expectFail("vfx blocking (a solid outside every picture)", function()
					return Run.content(
						"vfx blocking (outside)",
						Run.tool("python"),
						{ "kit/selftest/vfx/blocking/run.py", "outside" }
					)
				end, { "none of it is in the picture" }),
				-- FLOW (stage 38): a solid that MOVES over its beat is looked at at its start, middle and end from every
				-- angle and drawn by rays (the sheet, the film); one that flies out of the picture must be refused
				function(): Run.Step
					return Run.content(
						"vfx blocking (a moving solid: its flow from three angles, the sheet and the film drawn)",
						Run.tool("python"),
						{ "kit/selftest/vfx/blocking/run.py", "flow" }
					)
				end,
				expectFail("vfx blocking (a solid that flies out of the picture)", function()
					return Run.content(
						"vfx blocking (leaves)",
						Run.tool("python"),
						{ "kit/selftest/vfx/blocking/run.py", "leaves" }
					)
				end, { "of its way along", "beat shot" }),
				-- the trace (the VFX methods audit, 2026-11-13, stage 1) on a made scene whose every outline is known
				-- (kit/selftest/vfx/trace/made.py), through the real command: six drawings on twos must come back as
				-- curves within 3 % of the TRUE flame, in its two flat tones (never the anti-aliased rim between them),
				-- with the one cut-out and the one sharp tip of every drawing; and a wall in the fire's hue band is NOT a
				-- drawing - curves taken from it would look like a result
				function(): Run.Step
					return Run.content(
						"vfx trace (made scene: six drawings on twos as curves, tones, cut-out, tip)",
						Run.tool("python"),
						{ "kit/selftest/vfx/trace/run.py", "good" }
					)
				end,
				expectFail("vfx trace (a wall in the hue band is not a drawing)", function()
					return Run.content(
						"vfx trace (flood)",
						Run.tool("python"),
						{ "kit/selftest/vfx/trace/run.py", "flood" }
					)
				end, { "nothing to trace", "a flash or a background, not a drawing" }),
				-- the ink (the same audit, stage 2): the made flame traced, then inked through the real command into a
				-- made project folder - every drawing's cell must show the TRUE flame through the ink's own window, every
				-- in-between must lie between its two drawings with its tip still a point, the kit's sheet packer must
				-- pass the sheet with the flame's colours, and with the frames gone the build step must ink the same
				-- cells again; two drawings that are not the same pieces and barely overlap must be REFUSED an
				-- in-between (a blend, not a drawing) and leave no spec and no frames
				function(): Run.Step
					return Run.content(
						"vfx ink (made flame: drawings and in-betweens as cells, packed, inked again)",
						Run.tool("python"),
						{ "kit/selftest/vfx/ink/run.py", "good" }
					)
				end,
				expectFail("vfx ink (an in-between of drawings that barely overlap)", function()
					return Run.content(
						"vfx ink (split)",
						Run.tool("python"),
						{ "kit/selftest/vfx/ink/run.py", "split" }
					)
				end, { "barely overlap" }),
				-- the five sakuga grammars (LIMITATIONS_FIXES_V4 3.4 step 2): the made flame's traced numbers drive all
				-- five through the real ink command; the flame is the contract's 1024 x 1024 sheet with empty 2 px
				-- gutters and a glow mask; a sheet spoiled in its gutter and its mip padding is refused
				function(): Run.Step
					return Run.content(
						"vfx inkgrammar (five sakuga grammars from a trace's numbers)",
						Run.tool("python"),
						{ "kit/selftest/vfx/inkgrammar/run.py", "good" }
					)
				end,
				expectFail("vfx inkgrammar (a sheet drawn into its gutter, unpadded)", function()
					return Run.content(
						"vfx inkgrammar (bad)",
						Run.tool("python"),
						{ "kit/selftest/vfx/inkgrammar/run.py", "bad" }
					)
				end, { "gutter" }),
				-- V5 + B4 (LIMITATIONS_FIXES_V4 3.4 step 3): a plate baked by the real plate command, the V5 template
				-- pointed at it, checked by the GAME's sequence rules; a sequence with no 1-frame impact beat is refused
				function(): Run.Step
					return Run.content(
						"vfx sequence (V5 template + a baked B4 plate, checked by the game's rules)",
						Run.tool("python"),
						{ "kit/selftest/vfx/sequence/run.py", "good" }
					)
				end,
				expectFail("vfx sequence (no 1-frame impact beat, one reveal cut)", function()
					return Run.content(
						"vfx sequence (bad)",
						Run.tool("python"),
						{ "kit/selftest/vfx/sequence/run.py", "bad" }
					)
				end, { "IMPACT beat" }),
				-- G2, the 2-fighter scene (LIMITATIONS_FIXES_V4 3.4 step 1 / 11 Phase 2): the kit's REAL scene file (what
				-- the browser player and the Studio booth build) passes the real checker, a strike on its victim anchors
				-- passes; a 32-stud arena with the victim turned away and a camera cutting a fighter out, and a preset
				-- naming an anchor the scene lacks, are refused - each fault named
				function(): Run.Step
					return Run.content(
						"vfx duel (the G2 2-fighter scene file + a strike on its anchors)",
						Run.tool("python"),
						{ "kit/selftest/vfx/duel/run.py", "good" }
					)
				end,
				expectFail("vfx duel (32-stud arena, victim turned, fighter cut out, no anchor)", function()
					return Run.content("vfx duel (bad)", Run.tool("python"), { "kit/selftest/vfx/duel/run.py", "bad" })
				end, {
					"24 studs square",
					"victim: does not face the attacker",
					"not whole in the frame",
					"@victimKnee: not an anchor of scene g2",
				}),
				-- B4's "drawn" plate (LIMITATIONS_FIXES_V4 13.3.4: "halftone / kanji / drawn impact sheets"): baked by the
				-- real plate command, every check passes; a held cell and one-width ruled spokes are refused (boil, taper)
				function(): Run.Step
					return Run.content(
						"vfx drawn (a drawn impact plate, baked and checked)",
						Run.tool("python"),
						{ "kit/selftest/vfx/drawn/run.py", "good" }
					)
				end,
				expectFail("vfx drawn (a held cell, ruled one-width spokes)", function()
					return Run.content(
						"vfx drawn (bad)",
						Run.tool("python"),
						{ "kit/selftest/vfx/drawn/run.py", "bad" }
					)
				end, { "boil", "taper" }),
				-- gpusim's hero profile (LIMITATIONS_FIXES_V4 3.4 step 4: "256^3-384^3 (vorticity >= 2)"): --new writes a
				-- hero sim, a spec with no profile keeps its own params (old bakes byte for byte); a "hero" taken back to
				-- 128 cells / vorticity 0.7 is refused before anything is simulated
				function(): Run.Step
					return Run.content(
						"vfx gpusim (a new sim on the hero profile)",
						Run.tool("python"),
						{ "kit/selftest/vfx/gpusim/run.py", "good" }
					)
				end,
				expectFail("vfx gpusim (a hero sim at 128 cells, vorticity 0.7)", function()
					return Run.content(
						"vfx gpusim (bad)",
						Run.tool("python"),
						{ "kit/selftest/vfx/gpusim/run.py", "bad" }
					)
				end, { "256..384 cells a side", "vorticity is 2.0 or more" }),
				-- the judging skies (LIMITATIONS_FIXES_V4 13.3.1): a measurement per sky takes only recordings made under
				-- that sky (kit vfx booth / play --sky); night recordings asked for as day, or one not saying its sky,
				-- are refused and nothing is written
				function(): Run.Step
					return Run.content(
						"vfx sky (booth and player recorded under the asked sky)",
						Run.tool("python"),
						{ "kit/selftest/vfx/sky/run.py", "good" }
					)
				end,
				expectFail("vfx sky (night recordings asked for as day)", function()
					return Run.content("vfx sky (bad)", Run.tool("python"), { "kit/selftest/vfx/sky/run.py", "bad" })
				end, { "recorded under night, not day", "does not say its sky" }),
				-- the METHOD gate (the owner, 2026-11-13: every method of his list "enforced in the terms of being used"):
				-- a preset built from a scene is held to its chart's method plan. Twelve presets it must refuse, each for
				-- its own reason - no plan; a planned method used only by ANOTHER beat's layer; a beat whose words say
				-- "flame" with hand-drawn neither used nor left out with a reason; a method the owner saw on the chart
				-- he approved, dropped since; a reason for leaving one out that he never saw; a method the kit has not
				-- built; hand-drawn planned over a sheet that is an imported one under an inked name; every layer tagged
				-- with a beat the chart does not have; the inked layer muted (in the file, never played); the inked
				-- layer fully transparent (played, drawing nothing); a chart whose plan a MODEL approved; a reason
				-- rewritten after the owner read it
				expectFail("vfx methods (twelve presets off their chart's method plan)", function()
					return Content.vfxPresetsStep("kit/selftest/vfx/methods")
				end, {
					'preset_methods_noplan: methods: beat 0 ("glint") names no method',
					'preset_methods_unused: methods: beat 1 plans "UV scrolling / panning" and nothing that plays in that beat uses it',
					'preset_methods_ask: methods: beat 1 ("crescent of flame") shows "flame"',
					'preset_methods_dropped: methods: beat 1: "Hand-drawn effects animation" was on the chart the owner approved and is gone from the plan',
					'preset_methods_unseen: methods: beat 2: leaving out "Hand-drawn effects animation" is not on the chart the owner approved',
					'preset_methods_missing: methods: beat 0: "A made method the kit has not built" is not built in the kit yet',
					'preset_methods_fakeink: methods: beat 1 plans "Hand-drawn effects animation" and nothing that plays in that beat uses it',
					"preset_methods_stray: methods: 4 layer(s) name a beat the chart does not have",
					'preset_methods_muted: methods: beat 1 plans "Hand-drawn effects animation" and nothing that plays in that beat uses it',
					'preset_methods_dead: methods: beat 1 plans "Hand-drawn effects animation" and nothing that plays in that beat uses it',
					'preset_methods_model: methods: beat 2: leaving out "Hand-drawn effects animation" needs the OWNER',
					'preset_methods_rewritten: methods: beat 2: the reason for leaving out "Hand-drawn effects animation" is not the one the owner read',
				}),
				function(): Run.Step -- and the piece that uses what its chart plans, the embers' reason seen by him, builds
					return Content.vfxPresetsStep("kit/selftest/vfx/methods_good")
				end,
				-- the DISSOLVE THE GAME SHOWS (the VFX methods audit, stage 3: a mesh's erode writes vertex alpha, which
				-- the engine ignores - what breaks up in the player pops off in the game). A made texture baked by the
				-- real command: cell 0 IS the texture, the last cell is empty, nothing comes back, every cell removes its
				-- share of the area, the middle cell is in pieces, the burning edge sits on the front, every cell still
				-- tiles; the kit's packer packs it with the texture's colours; the build step bakes it again when its
				-- frames are gone or its source changed, and leaves it alone when it is current
				function(): Run.Step
					return Run.content(
						"vfx dissolve (a made texture: whole to nothing in pieces, packed, baked again when stale)",
						Run.tool("python"),
						{ "kit/selftest/vfx/dissolve/run.py", "good" }
					)
				end,
				-- an even fade is NOT a break-up: refused, and nothing left behind
				expectFail("vfx dissolve (an even fade passed off as a break-up)", function()
					return Run.content(
						"vfx dissolve (fade)",
						Run.tool("python"),
						{ "kit/selftest/vfx/dissolve/run.py", "fade" }
					)
				end, { "an even fade" }),
				-- the cell a mesh's sheet shows, asked of the GAME's own function (the text of sheetFrame in
				-- src/kit/VfxStage.luau, run by lune) and of the PLAYER's (player.js, run by node) over one sweep of lives,
				-- windows ("over"), sheet sizes and looping clocks: both must give the cell worked out by hand
				function(): Run.Step
					return Run.content(
						"vfx dissolve (the game and the player show the same cell)",
						Run.tool("python"),
						{ "kit/selftest/vfx/dissolve/run.py", "parity" }
					)
				end,
				-- AN OBJECT BROKEN INTO ITS OWN PIECES (the VFX methods audit, stage 5): a made slab cut by the real command -
				-- convex pieces that make up the slab with no gap and no overlap, the nearest to the blow leaving first and
				-- fastest, all flying away from it
				function(): Run.Step
					return Run.content(
						"vfx fracture (a made slab: pieces that make it up, pushed away from the blow)",
						Run.tool("python"),
						{ "kit/selftest/vfx/fracture/run.py", "good" }
					)
				end,
				expectFail("vfx fracture (a slab with a piece missing)", function()
					return Run.content(
						"vfx fracture (gap)",
						Run.tool("python"),
						{ "kit/selftest/vfx/fracture/run.py", "gap" }
					)
				end, { "do not make up the slab" }),
				-- one piece's solid, asked of the GAME's shape (the text of `piece` in src/kit/VfxMesh.luau, run by lune) and
				-- of the PLAYER's (player.js, run by node): the same points and the same texture places, and a closed prism
				function(): Run.Step
					return Run.content(
						"vfx fracture (the game and the player build the same piece)",
						Run.tool("python"),
						{ "kit/selftest/vfx/fracture/run.py", "parity" }
					)
				end,
				-- A LENS FLARE THAT BEHAVES LIKE ONE (the VFX methods audit, stage 6): the flare's marks for lights across and
				-- off the screen - the glow on the light, every ghost on the line through the middle, both sides of it,
				-- nothing for a light off the screen; its three pictures are what they are said to be
				function(): Run.Step
					return Run.content(
						"vfx flare (marks on the line through the light and the middle; its pictures)",
						Run.tool("python"),
						{ "kit/selftest/vfx/flare/run.py", "good" }
					)
				end,
				expectFail("vfx flare (a ghost off the line)", function()
					return Run.content(
						"vfx flare (stray)",
						Run.tool("python"),
						{ "kit/selftest/vfx/flare/run.py", "stray" }
					)
				end, { "on the line from the light through the middle" }),
				-- the marks asked of the GAME's function (the text of flareMarks in src/kit/VfxStage.luau, run by lune), of
				-- the PLAYER's (player.js, run by node) and of the rule (kit/vfx/flare.py): the same marks from all three
				function(): Run.Step
					return Run.content(
						"vfx flare (the game, the player and the rule place the same marks)",
						Run.tool("python"),
						{ "kit/selftest/vfx/flare/run.py", "parity" }
					)
				end,
				-- A LINE WHERE THE PICTURE STEPS (the VFX methods audit, stage 9): a made two-tone disc packed by the real
				-- packer with post.edges - a line round it AND down the border of its tones, none inside a flat tone, none
				-- outside; with keep false the lines alone
				function(): Run.Step
					return Run.content(
						"vfx edges (a made disc of two tones: its silhouette and the border of its tones are lines)",
						Run.tool("python"),
						{ "kit/selftest/vfx/edges/run.py", "good" }
					)
				end,
				expectFail("vfx edges (a soft glow that asks for edges)", function()
					return Run.content(
						"vfx edges (soft)",
						Run.tool("python"),
						{ "kit/selftest/vfx/edges/run.py", "soft" }
					)
				end, { "found no edge" }),
				-- PIECES THAT COME TO REST (the VFX methods audit, stage 10): a made slab's pieces flown by the real command -
				-- every one at rest lying flat before the fade, the same at 30 and 144 frames a second
				function(): Run.Step
					return Run.content(
						"vfx settle (a made slab's pieces all come to rest lying flat before the fade)",
						Run.tool("python"),
						{ "kit/selftest/vfx/settle/run.py", "good" }
					)
				end,
				expectFail("vfx settle (a life too short for the pieces to land)", function()
					return Run.content(
						"vfx settle (late)",
						Run.tool("python"),
						{ "kit/selftest/vfx/settle/run.py", "late" }
					)
				end, { "still moving" }),
				-- PIECES THAT MEET (the VFX methods audit, stage 23): the same plan flown the OLD way, every piece by itself -
				-- they end lying in each other, and the check must say so
				expectFail("vfx settle (pieces that pass through each other end lying in each other)", function()
					return Run.content(
						"vfx settle (through)",
						Run.tool("python"),
						{ "kit/selftest/vfx/settle/run.py", "through" }
					)
				end, { "lies_apart" }),
				-- the flight asked step by step of the GAME's rule (the text of debrisStep in src/kit/VfxStage.luau, run by
				-- lune), of the PLAYER's (player.js, run by node) and of kit/vfx/settle.py: the same eleven numbers each step
				function(): Run.Step
					return Run.content(
						"vfx settle (the game, the player and the rule fly the same flight)",
						Run.tool("python"),
						{ "kit/selftest/vfx/settle/run.py", "parity" }
					)
				end,
				-- AN AUTHORED VECTOR FIELD (the VFX methods audit, stage 11): the four starters made by the real command - each
				-- passes its checks and does what it is said to (a wind carries, a vortex turns, a path leads, a fountain lifts)
				function(): Run.Step
					return Run.content(
						"vfx field (the four starters: a wind carries, a vortex turns, a path leads, a fountain lifts)",
						Run.tool("python"),
						{ "kit/selftest/vfx/field/run.py", "good" }
					)
				end,
				expectFail("vfx field (a field whose air stands still in its bounds)", function()
					return Run.content(
						"vfx field (still)",
						Run.tool("python"),
						{ "kit/selftest/vfx/field/run.py", "still" }
					)
				end, { "stands still" }),
				-- the velocity asked of the GAME's rule (the text of fieldAt in src/kit/VfxStage.luau, run by lune), of the
				-- PLAYER's (player.js, run by node) and of kit/vfx/field.py: the same three numbers at 1,000 places
				function(): Run.Step
					return Run.content(
						"vfx field (the game, the player and the rule give the same velocity)",
						Run.tool("python"),
						{ "kit/selftest/vfx/field/run.py", "parity" }
					)
				end,
				-- COLOURS PULLED APART AT THE RIM (the VFX methods audit, stage 12): a made white disc packed by the real packer
				-- with post.aberration - red past its rim, blue short of it, a white middle, a fringe that widens with the disc
				function(): Run.Step
					return Run.content(
						"vfx aberration (a made white disc: red past its rim, blue short of it, a white middle)",
						Run.tool("python"),
						{ "kit/selftest/vfx/aberration/run.py", "good" }
					)
				end,
				expectFail("vfx aberration (an amount that parts the colours by half a pixel)", function()
					return Run.content(
						"vfx aberration (faint)",
						Run.tool("python"),
						{ "kit/selftest/vfx/aberration/run.py", "faint" }
					)
				end, { "under a pixel" }),
				-- A SIZE THE CAMERA DOES NOT SHRINK (the VFX methods audit, stage 13): forced perspective's rule - with keep 1
				-- a layer is as large on the screen as at its ref, a part keep sits between the lens and held, never past min / max
				function(): Run.Step
					return Run.content(
						"vfx forced (keep 1 holds a layer's size on the screen; min and max hold the multiplier)",
						Run.tool("python"),
						{ "kit/selftest/vfx/forced/run.py", "good" }
					)
				end,
				expectFail("vfx forced (a block that does nothing)", function()
					return Run.content(
						"vfx forced (off)",
						Run.tool("python"),
						{ "kit/selftest/vfx/forced/run.py", "off" }
					)
				end, { "does nothing" }),
				-- the multiplier asked of the GAME's rule (the text of forcedScale in src/kit/VfxStage.luau, run by lune), of
				-- the PLAYER's (player.js, run by node) and of kit/vfx/forced.py: the same number in 600 cases
				function(): Run.Step
					return Run.content(
						"vfx forced (the game, the player and the rule give the same multiplier)",
						Run.tool("python"),
						{ "kit/selftest/vfx/forced/run.py", "parity" }
					)
				end,
				-- CLOTH, SIMULATED AND BAKED (the VFX methods audit, stage 15): three sheets baked by the real command (a
				-- banner, a flag that loops, a sheet let go flat) - each held edge stays, no link stretches, the wind pushes
				-- the sheet the way it blows, the loop's ends meet, and the method gate takes the bakes and no other file
				function(): Run.Step
					return Run.content(
						"vfx cloth (a banner, a looping flag, a sheet let go: held, unstretched, blown the wind's way)",
						Run.tool("python"),
						{ "kit/selftest/vfx/cloth/run.py", "good" }
					)
				end,
				expectFail("vfx cloth (a sheet in no wind)", function()
					return Run.content(
						"vfx cloth (still)",
						Run.tool("python"),
						{ "kit/selftest/vfx/cloth/run.py", "still" }
					)
				end, { "hangs still" }),
				expectFail("vfx cloth (a bake whose frames were pulled apart by hand)", function()
					return Run.content(
						"vfx cloth (torn)",
						Run.tool("python"),
						{ "kit/selftest/vfx/cloth/run.py", "torn" }
					)
				end, { "the gate refuses" }),
				-- A SOFT BODY, SIMULATED AND BAKED (the VFX methods audit, stage 16): a dropped ball and a thrown one baked by
				-- the real command - each falls as a thing falls, lands flatter AND wider, keeps its volume, stays closed and
				-- on the floor; the dropped one does not roll; the method gate takes the bakes and no other file
				function(): Run.Step
					return Run.content(
						"vfx soft (a dropped ball and a thrown one: flatter and wider where they land, their volume kept)",
						Run.tool("python"),
						{ "kit/selftest/vfx/soft/run.py", "good" }
					)
				end,
				expectFail("vfx soft (a ball that never lands in its frames)", function()
					return Run.content(
						"vfx soft (rigid)",
						Run.tool("python"),
						{ "kit/selftest/vfx/soft/run.py", "rigid" }
					)
				end, { "a rigid ball" }),
				expectFail("vfx soft (a bake whose seam was pulled open by hand)", function()
					return Run.content(
						"vfx soft (open)",
						Run.tool("python"),
						{ "kit/selftest/vfx/soft/run.py", "open" }
					)
				end, { "the gate refuses" }),
				-- SAND, SIMULATED AND BAKED (the VFX methods audit, stage 17): a pillar let go and a pour baked by the real
				-- command - the pillar ends a round heap at its angle of repose with all its sand, steeper sand stands higher,
				-- the pour holds what was poured; the method gate takes the bakes and no other file
				function(): Run.Step
					return Run.content(
						"vfx sand (a pillar slumps to its angle of repose with all its sand; a pour holds what was poured)",
						Run.tool("python"),
						{ "kit/selftest/vfx/sand/run.py", "good" }
					)
				end,
				expectFail("vfx sand (a pillar too low to slide)", function()
					return Run.content(
						"vfx sand (flat)",
						Run.tool("python"),
						{ "kit/selftest/vfx/sand/run.py", "flat" }
					)
				end, { "the sand moves" }),
				expectFail("vfx sand (a bake with sand from nowhere)", function()
					return Run.content(
						"vfx sand (made)",
						Run.tool("python"),
						{ "kit/selftest/vfx/sand/run.py", "made" }
					)
				end, { "no sand is made or lost" }),
				-- A POINT CLOUD (the VFX methods audit, stage 18): the five starters and a cloud sampled from a made picture
				-- of a letter - its points lie on the letter's strokes; a swarm flown by the rule is whole within 8 / pull
				-- seconds at three frame rates and never passes its points; the gate takes a swarm that gathers
				function(): Run.Step
					return Run.content(
						"vfx points (a letter's cloud lies on its strokes; a swarm gathers into it and never passes it)",
						Run.tool("python"),
						{ "kit/selftest/vfx/points/run.py", "good" }
					)
				end,
				expectFail("vfx points (thirty points in one corner)", function()
					return Run.content(
						"vfx points (clump)",
						Run.tool("python"),
						{ "kit/selftest/vfx/points/run.py", "clump" }
					)
				end, { "not a clump" }),
				-- the new speed asked of the GAME's rule (the text of cloudPull in src/kit/VfxStage.luau, run by lune), of
				-- the PLAYER's (player.js, run by node) and of kit/vfx/points.py: the same number in 2,000 cases
				function(): Run.Step
					return Run.content(
						"vfx points (the game, the player and the rule give the same speed)",
						Run.tool("python"),
						{ "kit/selftest/vfx/points/run.py", "parity" }
					)
				end,
				-- HAIR AND FUR, SIMULATED AND BAKED (the VFX methods audit, stage 19): a tossed head of hair, a swaying fringe that
				-- loops and a fringe in the wind, baked by the real command - no strand stretches, the roots ride their body,
				-- the tips lag and overshoot the turn, the hair lies outside its head; the gate takes the bakes
				function(): Run.Step
					return Run.content(
						"vfx hair (a toss, a looping sway, a wind: strands keep their length and swing on their roots)",
						Run.tool("python"),
						{ "kit/selftest/vfx/hair/run.py", "good" }
					)
				end,
				expectFail("vfx hair (nothing moves it)", function()
					return Run.content(
						"vfx hair (still)",
						Run.tool("python"),
						{ "kit/selftest/vfx/hair/run.py", "still" }
					)
				end, { "the hair moves" }),
				expectFail("vfx hair (a bake turned into one stiff piece by hand)", function()
					return Run.content(
						"vfx hair (stiff)",
						Run.tool("python"),
						{ "kit/selftest/vfx/hair/run.py", "stiff" }
					)
				end, { "one stiff piece" }),
				-- MOTION VECTORS (the VFX methods audit, stage 20): a made disc that crosses its cell in four frames, packed by
				-- the real packer with post.inbetween - the grid is FULL, each cell between is ONE disc part of the way (nearer
				-- the true disc than a cross-fade by far), a cell on a rendered frame is that frame
				function(): Run.Step
					return Run.content(
						"vfx inbetween (a made disc crossing its cell: each in-between is one disc, part of the way)",
						Run.tool("python"),
						{ "kit/selftest/vfx/inbetween/run.py", "good" }
					)
				end,
				expectFail("vfx inbetween (a picture that only fades)", function()
					return Run.content(
						"vfx inbetween (fade)",
						Run.tool("python"),
						{ "kit/selftest/vfx/inbetween/run.py", "fade" }
					)
				end, { "over the whole sheet" }),
				expectFail("vfx inbetween (a spark that jumps while the rest drifts)", function()
					return Run.content(
						"vfx inbetween (far)",
						Run.tool("python"),
						{ "kit/selftest/vfx/inbetween/run.py", "far" }
					)
				end, { "a part of the picture is not followed" }),
				-- NODE-BASED COMPOSITING (the VFX methods audit, stage 21): the starter graph baked by the real command - a core
				-- that is the same in every frame and a halo that one noise tears and another bends, joined (what one stack
				-- cannot say); it is no single node's picture and the packer packs it
				function(): Run.Step
					return Run.content(
						"vfx graph (a steady core and a torn, bent halo joined: no one stack's picture)",
						Run.tool("python"),
						{ "kit/selftest/vfx/graph/run.py", "good" }
					)
				end,
				expectFail("vfx graph (a node multiplied by nothing)", function()
					return Run.content(
						"vfx graph (idle)",
						Run.tool("python"),
						{ "kit/selftest/vfx/graph/run.py", "idle" }
					)
				end, { "do nothing" }),
				expectFail("vfx graph (two nodes that read each other)", function()
					return Run.content(
						"vfx graph (ring)",
						Run.tool("python"),
						{ "kit/selftest/vfx/graph/run.py", "ring" }
					)
				end, { "goes round in a ring" }),
				-- GEOMETRY NODES, BAKED (the VFX methods audit, stage 22): a ripple and a scatter baked by the real command
				-- through Blender - the ripple's height is the tree's own formula at every point, the scatter's quads are
				-- square, stay put and grow in order of distance; the gate takes the bakes (skipped where there is no Blender)
				function(): Run.Step
					return Run.content(
						"vfx geonodes (a ripple that is its tree's formula; a scatter whose quads grow as the front comes)",
						Run.tool("python"),
						{ "kit/selftest/vfx/geonodes/run.py", "good" }
					)
				end,
				expectFail("vfx geonodes (a scatter cut off before its front comes)", function()
					return Run.content(
						"vfx geonodes (early)",
						Run.tool("python"),
						{ "kit/selftest/vfx/geonodes/run.py", "early" }
					)
				end, { "the mesh moves" }),
				expectFail("vfx geonodes (a ripple whose grid was slid by hand)", function()
					return Run.content(
						"vfx geonodes (slid)",
						Run.tool("python"),
						{ "kit/selftest/vfx/geonodes/run.py", "slid" }
					)
				end, { "the gate refuses" }),
				-- WATER AS A HEIGHT FIELD (the VFX methods audit, stage 24): five recipes baked by the real command - a dam's
				-- shelf and bore are Stoker's exact solution on the BAKED mesh, a looped slosh's ends meet, no water is made
				-- or lost; the gate takes waves as Wave simulation and a dam / a surge as Shallow-water, not the other way
				function(): Run.Step
					return Run.content(
						"vfx water (a dam's break is Stoker's; waves and shallow water each prove their own method)",
						Run.tool("python"),
						{ "kit/selftest/vfx/water/run.py", "good" }
					)
				end,
				expectFail("vfx water (a drop whose heights were changed by hand)", function()
					return Run.content(
						"vfx water (edited)",
						Run.tool("python"),
						{ "kit/selftest/vfx/water/run.py", "edited" }
					)
				end, { "the gate refuses" }),
				expectFail("vfx water (waves that pass a place faster than the frames can show)", function()
					return Run.content(
						"vfx water (fast)",
						Run.tool("python"),
						{ "kit/selftest/vfx/water/run.py", "fast" }
					)
				end, { "flip from frame to frame" }),
				-- LIQUID (the VFX methods audit, stage 25): a dam solved by FLIP and a drop by the particle fluid, by the real
				-- command - a pool stays still, a body falls as gravity says, the grid keeps its volume, no liquid is made or
				-- lost, the energy does not rise; the packer packs the sheet; the gate takes each solver for its own method
				function(): Run.Step
					return Run.content(
						"vfx liquid (FLIP and a particle fluid hold their physics; each proves its own method)",
						Run.tool("python"),
						{ "kit/selftest/vfx/liquid/run.py", "good" }
					)
				end,
				expectFail("vfx liquid (a block so tall its run-up leaves the picture)", function()
					return Run.content(
						"vfx liquid (tall)",
						Run.tool("python"),
						{ "kit/selftest/vfx/liquid/run.py", "tall" }
					)
				end, { "under the top of its cell" }),
				expectFail("vfx liquid (a sheet the packer cannot take)", function()
					return Run.content(
						"vfx liquid (odd)",
						Run.tool("python"),
						{ "kit/selftest/vfx/liquid/run.py", "odd" }
					)
				end, { "256, 512 or 1024" }),
				-- FOLLOWING THE CAMERA (the VFX methods audit, stage 7): a made shot whose camera pans and zooms by a known
				-- amount - the tracker gives every frame's place in the first frame's picture to under 0.3 px and says
				-- the move as it is, calls a standing camera standing, does not guess on a flat night, and with --track the
				-- trace reads the flame as six drawings on twos, each the size a standing camera gives
				function(): Run.Step
					return Run.content(
						"vfx track (a made pan and zoom followed; the trace on twos with --track)",
						Run.tool("python"),
						{ "kit/selftest/vfx/track/run.py", "good" }
					)
				end,
				-- the same moving shot traced WITHOUT --track would read every frame as a new drawing: refused
				expectFail("vfx trace (a shot whose camera moves, traced as it is)", function()
					return Run.content(
						"vfx track (moving)",
						Run.tool("python"),
						{ "kit/selftest/vfx/track/run.py", "moving" }
					)
				end, { "the camera pans", "every frame would read as a new drawing" }),
				-- SURFACE LOOKS IN SECONDS (the VFX methods audit, stage 4): a ring whose noise pans and whose lookup is
				-- warped, through a colour ramp, baked by the real command in under 5 s - the ring is where its radius
				-- says, the loop comes back to its first frame, every colour is on the ramp, nothing touches the cell's
				-- edge, the kit's packer passes it, and a changed spec is baked again
				function(): Run.Step
					return Run.content(
						"vfx comp (a made ring: where its radius says, looping, on its ramp, packed)",
						Run.tool("python"),
						{ "kit/selftest/vfx/comp/run.py", "good" }
					)
				end,
				-- sixteen copies of one picture are NOT a look that moves: refused, no frames left behind
				expectFail("vfx comp (a look in which nothing pans)", function()
					return Run.content(
						"vfx comp (still)",
						Run.tool("python"),
						{ "kit/selftest/vfx/comp/run.py", "still" }
					)
				end, { "two frames show the same picture" }),
				-- the method gate holds a new piece to it: a mesh that still uses erode is refused (it shows in the
				-- player only), and so is a "dissolve" planned over a mesh that plays no dissolve sheet through a surface
				expectFail("vfx methods (a mesh's erode on a new piece; a dissolve planned and not baked)", function()
					return Content.vfxPresetsStep("kit/selftest/vfx/dissolve_gate")
				end, {
					'preset_dissolve_erode: methods: 1 layer(s) (arc_ring): a mesh\'s "erode" shows in the browser player only',
					'preset_dissolve_unbaked: methods: beat 1 plans "Dissolve effects" and nothing that plays in that beat uses it',
				}),
				function(): Run.Step -- and a ring that plays its baked sheet through a surface inside "over" builds
					return Content.vfxPresetsStep("kit/selftest/vfx/dissolve_gate_good")
				end,
				-- the review page (the 3D studio-route plan, H8, 2026-11-12) on the fixture piece (kit/selftest/sheet, a
				-- copy with a locks file of its own): a sheet approved BY A CLICK must be the owner's record for that
				-- sheet's id, read back as approved, with the project's own board/locks.json untouched; and a write
				-- WITHOUT the page's token must be refused - a page that took it would let any local page approve
				function(): Run.Step
					return Run.content(
						"review page (a click's approval is the record the lock reads)",
						Run.tool("python"),
						{ "kit/selftest/review/run.py", "approve" }
					)
				end,
				expectFail("review page (a write without the page's token)", function()
					return Run.content(
						"review page (no token)",
						Run.tool("python"),
						{ "kit/selftest/review/run.py", "notoken" }
					)
				end, { "without the page's token was refused" }),
				-- the VFX side of the page, on a made effect with a locks file of its own (a second review,
				-- 2026-11-12: the page and its commands read different folders, and a yes to a style sheet was bound
				-- to the preset, not to the pictures): the chart must be approved in the folder the page read, for
				-- the plan it showed, and the style record must name the pictures he saw; and after the same preset
				-- is recorded and drawn AGAIN, a click for the old pictures must be refused
				function(): Run.Step
					return Run.content(
						"review page (an effect's chart and style sheet: a yes is for what the page showed)",
						Run.tool("python"),
						{ "kit/selftest/review/run.py", "effect" }
					)
				end,
				expectFail("review page (a click for a style sheet's OLD pictures)", function()
					return Run.content(
						"review page (redrawn)",
						Run.tool("python"),
						{ "kit/selftest/review/run.py", "redrawn" }
					)
				end, { "pictures that are no longer there was refused" }),
				expectWarn("ui layout eyes (panel off screen, button under the top bar)", function()
					return Content.uiPreviewStep(nil, "kit/selftest/ui", Config.build("selftest/ui"))
				end, { "offscreen", "topbar" }),
				-- the hero route's first lock: two HUD stills at 960x540 must hold every later stage (the source is the
				-- ceiling: the character-action gauges plateaued on a 760x940 sheet)
				expectFail("ui plan refs lock (refs_too_small: stills under 1080p)", function()
					local fx = "kit/selftest/ui/refs_too_small"
					return Run.content("ui plan (selftest)", Run.tool("python"), {
						"kit/ui/plan.py",
						"RefsTooSmall",
						"--specs",
						fx,
						"--refs",
						fx .. "/refs",
						"--models",
						Config.build("selftest/ui_plan_models"),
						"--ui",
						Config.build("selftest/ui_plan"),
						"--verify",
						Config.build("selftest/ui_plan/none.json"),
					})
				end, { "at refs (later stages locked)", "0 at >= 1080p" }),
				-- the owner's FieldHud_v1 1/10 (2026-10-12): a realistic screen given an arcade HUD - the identity's banned
				-- components (crosshair, ammo, compass ...) fail the compile; the same screen without them passes
				expectFail("ui arcade-ban (FieldHud_v1 1/10: a crosshair + ammo on a tactical identity)", function()
					local fx = "kit/selftest/ui/arcade_in_realistic"
					return Run.spawn("ui arcade-ban (selftest)", Run.tool("lune"), {
						"run",
						"kit/ui/compile_fixture",
						fx .. "/ArcadeInRealistic.json",
						"--identities",
						fx .. "/identities",
					}, true)
				end, { "banned_component", "crosshair" }),
				function() -- and the same identity with only a bar passes it
					local fx = "kit/selftest/ui/arcade_in_realistic"
					return Run.spawn("ui arcade-ban control (selftest)", Run.tool("lune"), {
						"run",
						"kit/ui/compile_fixture",
						fx .. "/ArcadeInRealistic_Good.json",
						"--identities",
						fx .. "/identities",
					}, true)
				end,
				-- the REAL FieldHud_v1 (1/10, 2026-10-12) on the owner's own realistic identity, a bad example forever:
				-- its minimap, kill feed, HP number and round count were plain panels and labels, so only the words he
				-- chose for field.json's banned_components (card qfab, 2026-11-10) can catch them - by name, and its
				-- plate shades by type; the screen he approved after it (v2, "OK great") must still compile
				expectFail("ui arcade-ban (FieldHud_v1 1/10: the real screen on the field identity)", function()
					local fx = "kit/selftest/ui/field_v1"
					return Run.spawn("ui arcade-ban FieldHud_v1 (selftest)", Run.tool("lune"), {
						"run",
						"kit/ui/compile_fixture",
						fx .. "/FieldHud_v1.json",
						"--identities",
						fx .. "/identities",
					}, true)
				end, {
					"banned_component",
					"FieldHud.Hud.Map",
					"FieldHud.Hud.Feed",
					"FieldHud.Hud.Vitals.Hp",
					"FieldHud.Hud.Ammo.Rounds",
					"FieldHud.Hud.Ammo.Reserve",
					"FieldHud.Hud.ShadeBR",
				}),
				function() -- and FieldHud v2, the screen the owner approved, compiles on the same identity
					local fx = "kit/selftest/ui/field_v1"
					return Run.spawn("ui arcade-ban FieldHud_v2 control (selftest)", Run.tool("lune"), {
						"run",
						"kit/ui/compile_fixture",
						fx .. "/FieldHud_v2.json",
						"--identities",
						fx .. "/identities",
					}, true)
				end,
				-- the owner's sg_hud5 3/10 (2026-10-29: "what the hell, I told you not this small"), a bad example
				-- forever: Sample Game's HUD is game code that sizes itself at runtime - R2 put `HUD_SCALE, MIN_SCALE,
				-- MARGIN = 0.58, 0.3, 30` in ChamberHud's rescale(), and no spec, compile or gauge ever saw it. The REAL
				-- R2 file, its own corner() calls and rescale() run at 1920x1080 and three desktop sizes, against the
				-- sizes the owner approved (2026-11-04: "Size is right"), must fail; the file he approved must pass
				expectFail(
					"ui hud size (sg_hud5 3/10: the R2 ChamberHud, every block at 0.58 of its design)",
					function()
						local fx = "kit/selftest/ui/hud_size"
						return Run.spawn("ui hud size (selftest)", Run.tool("lune"), {
							"run",
							"kit/ui/hudsize",
							fx .. "/ChamberHud.json",
							"--code",
							fx .. "/ChamberHud_R2.luau.txt",
						}, true)
					end,
					{ "hud size", "Ammo 325x232 px at 1920x1080 = 0.58", "Vitals" }
				),
				function() -- and the HUD the owner approved for size passes it
					local fx = "kit/selftest/ui/hud_size"
					return Run.spawn("ui hud size control (selftest)", Run.tool("lune"), {
						"run",
						"kit/ui/hudsize",
						fx .. "/ChamberHud.json",
						"--code",
						fx .. "/ChamberHud_approved.luau.txt",
					}, true)
				end,
				-- LIMITATIONS_FIXES_V4 UI-X (v7 layout + access): a flex item with no list above it, flex on a grid, a
				-- text that clips at the player's Largest text size and unreadable text contrast fail the compile; the
				-- same pieces done right pass
				expectFail(
					"ui v7 gates (flex nowhere, flex on a grid, clips at Largest text, contrast 1:1)",
					function()
						return Run.spawn("ui v7 gates (selftest)", Run.tool("lune"), {
							"run",
							"kit/ui/compile_fixture",
							"kit/selftest/ui/v7_access/V7Bad.json",
						}, true)
					end,
					{
						"a flex item needs a parent with a list",
						"a grid's cells keep their size",
						"at the player's Largest text size",
						"text contrast 1:1",
					}
				),
				function() -- and the control compiles
					return Run.spawn("ui v7 gates control (selftest)", Run.tool("lune"), {
						"run",
						"kit/ui/compile_fixture",
						"kit/selftest/ui/v7_access/V7Good.json",
					}, true)
				end,
				-- breakpoints the engine would ignore silently (a condition it does not take, min over max, no rules)
				-- refuse the style export; good queries export
				expectFail("ui style queries (an unknown condition, an impossible size, no rules)", function()
					return Run.content("ui style queries (selftest)", Run.tool("python"), {
						"kit/ui/style.py",
						"bad_queries",
						"--ui",
						"kit/selftest/ui/style_queries",
						"--out",
						Config.build("selftest/ui_style"),
					})
				end, { "is not a StyleQuery condition", "can never be active", "styles nothing" }),
				function() -- and the control exports
					return Run.content("ui style queries control (selftest)", Run.tool("python"), {
						"kit/ui/style.py",
						"good_queries",
						"--ui",
						"kit/selftest/ui/style_queries",
						"--out",
						Config.build("selftest/ui_style"),
					})
				end,
				-- LIMITATIONS_FIXES_V4 UI-X 13.6 (the Combat Feedback Kit): a waypoint marker whose margin is under its
				-- own half-size (the pinned pin hangs off the edge) and a streak ladder the runtime cannot honour (an
				-- empty rung, a 0 s kill window, 9 banners) fail the compile; the same pieces done right pass
				expectFail("ui combat kit (a marker off the edge, an empty rung, a 0 s window, 9 banners)", function()
					return Run.spawn("ui combat kit (selftest)", Run.tool("lune"), {
						"run",
						"kit/ui/compile_fixture",
						"kit/selftest/ui/combat_kit/CombatBad.json",
					}, true)
				end, { "hangs off the screen edge", "none empty", "a chain stays open", "how many banners stack" }),
				function() -- and the control compiles
					return Run.spawn("ui combat kit control (selftest)", Run.tool("lune"), {
						"run",
						"kit/ui/compile_fixture",
						"kit/selftest/ui/combat_kit/CombatGood.json",
					}, true)
				end,
				-- LIMITATIONS_FIXES_V4 UI-X 6.4 step 4 (UEyes / UIGaze): a HUD whose focus (the ammo) is dim while a loud
				-- banner takes the first look fails the saliency gate (< 85% of first looks); the focus made loud passes
				expectFail("ui saliency (the focus loses the first look to a banner)", function()
					local fx = "kit/selftest/ui/saliency"
					return Run.content("ui saliency (selftest)", Run.tool("python"), {
						"kit/ui/saliency.py",
						"check",
						"--frame",
						fx .. "/SalBad.png",
						"--boxes",
						fx .. "/SalBad.boxes.json",
						"--focus",
						"Hud.Ammo",
					})
				end, { "of first looks land on Hud.Ammo", "the eye took Hud.Banner" }),
				function() -- and the control passes
					local fx = "kit/selftest/ui/saliency"
					return Run.content("ui saliency control (selftest)", Run.tool("python"), {
						"kit/ui/saliency.py",
						"check",
						"--frame",
						fx .. "/SalGood.png",
						"--boxes",
						fx .. "/SalGood.boxes.json",
						"--focus",
						"Hud.Ammo",
					})
				end,
				-- LIMITATIONS_FIXES_V4 UI-X 6.4 step 4 (align.py, the 1-3 px anti-slop lint): a menu column whose buttons
				-- drift 2 px and whose gaps are 10 and 13 px is caught on the engine's layout (nothing drawn); kit verify
				-- runs the same check over every screen as a warning with the count
				expectFail("ui align (a column 2 px off and unevenly spaced)", function()
					return Run.content("ui align (selftest)", Run.tool("python"), {
						"kit/ui/align.py",
						"check",
						"--models",
						"kit/selftest/ui/align/bad",
						"--fail",
					})
				end, { "1 of 1 screen(s) have 1-3 px near-misses", "2 edge(s)", "1 uneven gap(s)" }),
				expectWarn("ui align as kit verify runs it (a warning with the count)", function()
					return Run.content("ui align (selftest)", Run.tool("python"), {
						"kit/ui/align.py",
						"check",
						"--models",
						"kit/selftest/ui/align/bad",
					})
				end, { "1 of 1 screen(s) have 1-3 px near-misses", "WARNING" }),
				function() -- and the column lined up exactly passes, even with --fail
					return Run.content("ui align control (selftest)", Run.tool("python"), {
						"kit/ui/align.py",
						"check",
						"--models",
						"kit/selftest/ui/align/good",
						"--fail",
					})
				end,
				-- V4 UI-X 6.4 / 13.6, the VRAM guard + WCAG 2.3.1 at compile time: a CanvasGroup inside a CanvasGroup (a
				-- hit marker in a fading card too) and fx / loops that can flash more than 3 times a second fail the
				-- compile; the same screen done right passes
				expectFail(
					"ui vram + flashes (nested CanvasGroups, a 4/s shimmer, a 5/s split, a 5/s glint)",
					function()
						return Run.spawn("ui vram + flashes (selftest)", Run.tool("lune"), {
							"run",
							"kit/ui/compile_fixture",
							"kit/selftest/ui/vram_flash/VramFlashBad.json",
						}, true)
					end,
					{
						"a CanvasGroup inside the CanvasGroup VramFlashBad.Root.Card",
						"VramFlashBad.Root.Card.Hit",
						"shimmer can flash 4 times in one second",
						"split can flash 5 times in one second",
						"a glint loop at speed 12 flashes 5 times",
					}
				),
				function() -- and the control compiles
					return Run.spawn("ui vram + flashes control (selftest)", Run.tool("lune"), {
						"run",
						"kit/ui/compile_fixture",
						"kit/selftest/ui/vram_flash/VramFlashGood.json",
					}, true)
				end,
				-- V4 UI-X 6.4 step 4 (kit ui motion-ref): an identity whose motion was measured from the source game's
				-- clip (0.42 s, cubic, 0.08 s apart) but typed from taste (0.18 s back slams, 0.03 s apart) fails the
				-- compile; the motion built from the measurement passes
				expectFail("ui motion-ref (typed motion off its measured clip)", function()
					local fx = "kit/selftest/ui/motion_ref"
					return Run.spawn("ui motion-ref (selftest)", Run.tool("lune"), {
						"run",
						"kit/ui/compile_fixture",
						fx .. "/MotionRefBad.json",
						"--identities",
						fx .. "/identities",
					}, true)
				end, {
					"identity:mref_bad.motion.enter.duration",
					"identity:mref_bad.motion.stagger",
					"settles without one",
				}),
				function() -- and the control compiles
					local fx = "kit/selftest/ui/motion_ref"
					return Run.spawn("ui motion-ref control (selftest)", Run.tool("lune"), {
						"run",
						"kit/ui/compile_fixture",
						fx .. "/MotionRefGood.json",
						"--identities",
						fx .. "/identities",
					}, true)
				end,
				-- the lane quality locks (kit/lib/lanelocks.luau): a sound / set / asset / world made after the locks
				-- that skipped its quality step is refused by its build command and by kit verify
				expectFail("sfx quality lock (a new sound and a new set with no owner-chosen reference)", function()
					local LaneLocks = require("../lib/lanelocks")
					return LaneLocks.report(
						"sfx lock (selftest)",
						LaneLocks.sfx(nil, nil, "kit/selftest/locks/sounds"),
						""
					)
				end, { "new_sound", "new_set" }),
				expectFail(
					"3d quality lock (an unapproved hero brief / no brief at all / no reference study)",
					function()
						local LaneLocks = require("../lib/lanelocks")
						return LaneLocks.report("3d lock (selftest)", LaneLocks.assets("kit/selftest/locks/models"), "")
					end,
					{ "new_hero", "no_brief", "no_study" }
				),
				-- the 3D STAGE approvals (the owner, 2026-11-11: "A concept sheet we really need ... block[out]
				-- approval"). The MODEL SHEET refuses hero features nobody can model from their pictures ...
				expectFail("3d model sheet (hero features with no picture, no box, under 2 px per mm)", function()
					return Run.content("model sheet (selftest)", Run.tool("python"), {
						"kit/tools/sheet.py",
						"nocallout",
						"--root",
						"kit/selftest/sheet",
						"--out",
						Config.build("selftest/sheet") .. "/nocallout.sheet.png",
					})
				end, { "sheet nocallout: 3 problem(s)", "wolf crest: no picture" }),
				function() -- ... and draws the one whose features all have a picture box, a size and enough pixels
					return Run.content("model sheet control (selftest)", Run.tool("python"), {
						"kit/tools/sheet.py",
						"sheetgun",
						"--root",
						"kit/selftest/sheet",
						"--out",
						Config.build("selftest/sheet") .. "/sheetgun.sheet.png",
					})
				end,
				-- a hero piece with a build script and no model sheet is refused before any shape
				expectFail("3d model sheet lock (a hero piece shaped before the owner saw a sheet)", function()
					local LaneLocks = require("../lib/lanelocks")
					return lockStep(
						"model sheet lock (selftest)",
						-- ("geo": as kit asset --geo asks it - the cheapest build there is still needs the sheet)
						LaneLocks.asset("nosheet", nil, "kit/selftest/sheet/assets/models", nil, "geo")
					)
				end, { "nosheet", "model sheet" }),
				-- with its sheet approved, the BAKED build still waits for the blockout's approval ...
				expectFail("3d blockout lock (a baked build before the owner approved the blockout)", function()
					return stageFixture("full")
				end, { "sheetgun", "needs its blockout" }),
				function() -- ... and the shape round stays free: a blockout is made of shape rounds
					return stageFixture("geo")
				end,
				function() -- the blockout round keeps its clay views (a shape round WITH pictures: seconds, no bake) ...
					return Content.blenderStep(
						"blockout round (selftest)",
						"kit/selftest/sheet/assets/models/build_sheetgun.py",
						{ "--geo", "--blockout" }
					)
				end,
				function() -- ... and the blockout sheet is drawn from them
					return Run.content("blockout sheet (selftest)", Run.tool("python"), {
						"kit/tools/blockout.py",
						"sheetgun",
						"--root",
						"kit/selftest/sheet",
						"--build",
						Config.path("build"),
						"--out",
						Config.build("selftest/sheet") .. "/sheetgun.blockout.png",
					})
				end,
				expectFail("world quality lock (one still, no measured REFS.md)", function()
					local LaneLocks = require("../lib/lanelocks")
					return LaneLocks.report(
						"world lock (selftest)",
						LaneLocks.world(nil, "kit/selftest/locks/worlds"),
						""
					)
				end, { "NewWorld" }),
				-- enforced learning, rule 2 (board/plans/archive/2026-11-09-enforced-learning-plan.md): a new piece of a content lane
				-- answers the lessons ranked for it before it counts as made
				expectFail("lessons lock (a new vfx piece that never answered its lessons)", function()
					local LaneLocks = require("../lib/lanelocks")
					return LaneLocks.report(
						"lessons lock (selftest)",
						LaneLocks.lessons("vfx", "kit/selftest/locks/lessons/"),
						""
					)
				end, { "new_effect" }),
				expectFail("verdict lock (three new pieces the owner never scored hold kit new)", function()
					local LaneLocks = require("../lib/lanelocks")
					local open = LaneLocks.unscored("vfx", { "kit/selftest/locks/open/" })
					local problems = if #open >= LaneLocks.OPEN_CAP then open else {}
					return LaneLocks.report("verdict lock (selftest)", problems, "")
				end, { "open_one", "open_three", "open_two" }),
				-- the quality lock behind kit ui / kit verify: a screen made after the locks compiles only on real stills
				expectFail("ui refs lock (a new screen on stills under 1080p)", function()
					local fx = "kit/selftest/ui/refs_too_small"
					return Run.content("ui refs lock (selftest)", Run.tool("python"), {
						"kit/ui/refs_lock.py",
						"RefsTooSmall",
						"--specs",
						fx,
						"--refs",
						fx .. "/refs",
					})
				end, { "0/1 new screen(s) built on real references" }),
				expectFail("texture gate", function()
					return Content.texturesStep({ "--check", "kit/selftest/vfx/_selftest_bad.png" })
				end),
				expectFail("audio gate", function()
					local out = Config.build("selftest/audio")
					local render = Content.synthStep({ "all" }, "kit/selftest/audio", out)
					if not render.ok then
						return render
					end
					return Content.audioCheckStep(out)
				end),
				expectFail("sfx set gates (a role that lies, identical takes, one family 10 LU apart)", function()
					return Run.content("sfx set (selftest)", Run.tool("python"), {
						"kit/audio/sets.py",
						"all",
						"--sets",
						"kit/selftest/audio/sets",
						"--out",
						Config.build("selftest/audio_sets"),
					})
				end, { 'is a "sub"', "takes sound alike", "LU apart" }),
				-- the owner's verdict on the synth-only sword set (2026-10-13: "pure synth is audio slop"), a bad example
				-- forever (card b6m2): a set with no real recording in any member fails
				expectFail("sfx set gates (pure synth: no real recording in any member)", function()
					return Run.content("sfx set (synth-only selftest)", Run.tool("python"), {
						"kit/audio/sets.py",
						"_selftest_synth_only_set",
						"--sets",
						"kit/selftest/audio/synth_only",
						"--out",
						Config.build("selftest/audio_sets"),
					})
				end, { "pure synth" }),
				expectFail("world check (a pit you can never leave = a TRAP)", function()
					return require("./world").checkStep("kit/selftest/world/_selftest_trap.json")
				end, { "TRAP" }),
				function() -- and the same map with ledges out and steps up passes it
					return require("./world").checkStep("kit/selftest/world/_selftest_trap_fixed.json")
				end,
				-- card my7f (GothicCourtyard in Studio, 2026-11-12): a house's wooden floor in the plane of the court's
				-- slate floor flickered (stone in one capture, planks in the next) and every gate passed it
				expectFail(
					"world check (z-fighting: a wooden floor in the plane of the court's stone floor)",
					function()
						return require("./world").checkStep("kit/selftest/world/_selftest_zfight.json")
					end,
					{ "z-fighting:" }
				),
				expectClean( -- and a house the building generator stands on the same court (its boards lifted) passes it
					"world check (a house on the court floor: its ground floor clear of the court's plane)",
					function()
						return require("./world").checkStep("kit/selftest/world/_selftest_zfight_fixed.json")
					end,
					{ "z-fighting" }
				),
				-- LIMITATIONS_FIXES_V4 5.1 (card my7f: "z-fighting misses ceilings"): an oak beam's underside in the plane
				-- of the plaster ceiling over the court flickers over the player's head; undersides were never measured
				expectFail("world check (z-fighting: a beam's underside in the ceiling's plane)", function()
					return require("./world").checkStep("kit/selftest/world/_selftest_zceil.json")
				end, { "z-fighting:", "underside" }),
				expectClean( -- and the beam hung 0.08 studs under the ceiling passes it
					"world check (a beam hung 0.08 studs under the ceiling)",
					function()
						return require("./world").checkStep("kit/selftest/world/_selftest_zceil_fixed.json")
					end,
					{ "z-fighting" }
				),
				-- LIMITATIONS_FIXES_V4 5.1 ("ribbon river meshes -> --sink"): a bowl's rivers with no --sink in its recipe
				-- run into a closed hollow where a lake would stand; the same bowl with a sink in its middle drains
				expectFail("world ribbons (rivers into a closed hollow: no sink)", function()
					return Run.content("world ribbons (pit selftest)", Run.tool("python"), {
						"kit/world/ribbons.py",
						"kit/selftest/world/terrain/_selftest_ribbon_pit.hm.json",
						"--out",
						Config.build("selftest/ribbons_pit"),
					})
				end, { "into a pit" }),
				function() -- and with the sink every river drains into it
					return Run.content("world ribbons (sink selftest)", Run.tool("python"), {
						"kit/world/ribbons.py",
						"kit/selftest/world/terrain/_selftest_ribbon_sink.hm.json",
						"--out",
						Config.build("selftest/ribbons_sink"),
					})
				end,
				-- LIMITATIONS_FIXES_V3.md stage C: "0 floating plinths, >= 7 st clear footpath" - street lamps typed over
				-- the square float, a bench in the middle of a lane leaves 3.5 studs either side
				expectFail("world check (street fixtures: a row of lamps typed over the square floats)", function()
					return require("./world").checkStep("kit/selftest/world/_selftest_fixtures.json")
				end, { "fixture:" }),
				expectFail("world check (a footpath: a bench in the middle of a 10-stud lane)", function()
					return require("./world").checkStep("kit/selftest/world/_selftest_footpath.json")
				end, { "footpath:" }),
				expectClean( -- and the lamps on the square, the bench at the lane's edge (7.1 studs clear), pass it
					"world check (street fixtures: lamps on the square, the bench at the lane's edge)",
					function()
						return require("./world").checkStep("kit/selftest/world/_selftest_fixtures_fixed.json")
					end,
					{ "fixture:", "footpath:" }
				),
				expectFail(
					"world check (the r6 scale sheet: all 6 of a steep stair, barn door, low rail, tight alley, tall ceiling, short run wall)",
					function()
						return require("./world").checkStep("kit/selftest/world/_selftest_scale.json")
					end,
					{ "6 error(s)", "does not fit the r6 rig" }
				),
				function() -- and the same pieces at the sheet's numbers pass it
					return require("./world").checkStep("kit/selftest/world/_selftest_scale_fixed.json")
				end,
				-- the owner's 6/10 on 2026-10-29 ("some things are not ... to perfectly fit my R6 rig": Vaelmouth's
				-- 11-stud storeys and 1.3-stud rails), rebuilt with the kit's generators, which claim their own ceilings,
				-- doorways, stairs and rails: a room a head too low and a rail at the knee must fail the r6 sheet
				expectFail(
					"world check (the r6 sheet on what generators make: Vaelmouth's rooms a head too low, its rails at the knee)",
					function()
						return require("./world").checkStep("kit/selftest/world/_selftest_vaelmouth.json")
					end,
					{ "5 error(s)", "does not fit the r6 rig", "ceiling", "h 10" } -- (5: four ceilings + the knee rail)
				),
				expectClean( -- and the same street at 14-stud storeys and 3-stud rails passes it
					"world check (Vaelmouth's street at 14-stud storeys and 3-stud rails fits the r6 sheet)",
					function()
						return require("./world").checkStep("kit/selftest/world/_selftest_vaelmouth_fixed.json")
					end,
					{ "does not fit the r6 rig" }
				),
				-- the owner on the District (2026-10-28): "I hate the fact that you added a lamp everywhere" - the street
				-- the row generator's old default made (a lamp every 24 studs, both sides) must fail
				expectFail("world check (design: a lamp everywhere, the row generator's old 24-stud lamps)", function()
					return require("./world").checkStep("kit/selftest/world/_selftest_lamps.json")
				end, { "design:", "a lamp everywhere" }),
				expectClean( -- and the same street with lamps 90 studs apart (the new default) passes it
					"world check (the same street, lit on both sides 90 studs apart, is not a lamp everywhere)",
					function()
						return require("./world").checkStep("kit/selftest/world/_selftest_lamps_fixed.json")
					end,
					{ "a lamp everywhere" }
				),
				-- the TOWN PLAN generator (kit/lib/worldtown.luau, 2026-11-13; the owner on the District: "the city does
				-- not feel or look like a genuine proper open world"): a generated town is held to the same check as a
				-- typed one - with lanes 4 studs wide it must fail the R6 sheet, each lane MEASURED between its walls ...
				expectFail(
					"world check (a generated town with lanes 4 studs wide: the r6 sheet measures every one)",
					function()
						return require("./world").checkStep("kit/selftest/world/_selftest_town_tight.json")
					end,
					{ "scale:", "w 4.0 (wants 8.0..)" }
				),
				-- ... the same town at its own widths passes (walked from the gate, every door and storey to the rig) ...
				function()
					return require("./world").checkStep("kit/selftest/world/_selftest_town.json")
				end,
				-- ... and its plan is drawn from above (kit world town: the page a layout is read by)
				function()
					local steps = require("./world").town("kit/selftest/world/_selftest_town.json")
					return steps[#steps]
				end,
				-- ... and a town that names no skins is refused a kit of house meshes (kit world town --kit), told what to add
				expectFail("world town kit (a town with no skins has no kit of houses to make)", function()
					return (
						require("./world").townKit(
							"kit/selftest/world/_selftest_town.json",
							Config.build("selftest") .. "/town_kit.json"
						)
					)
				end, { '"skins"' }),
				-- ENFORCED (the owner, 2026-11-13: every method "implmented into each pipeline and enforced in the terms of
				-- being used"): a place of houses is laid out by the town plan. The build's lock names 12 houses typed one
				-- by one, and a "city" grid (only the layout lines are reported here: the fixtures have no references
				-- either) ...
				expectFail("world layout lock (12 houses typed one by one; a city grid: no town step)", function()
					local LaneLocks = require("../lib/lanelocks")
					local lines = {}
					for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_layout") do
						if string.find(line, 'one "town" step in', 1, true) then
							table.insert(lines, line)
						end
					end
					return LaneLocks.report("world layout lock (selftest)", lines, "")
				end, { "TypedTown", "GridTown" }),
				-- ... a road and a row of posts that turn a right angle at a typed point and do not say "curve": true or
				-- false hold the build too (the smooth line through typed points: kit/lib/worldcurve.luau) ...
				expectFail(
					"world bend lock (a road that turns a hard corner and does not say how it bends)",
					function()
						local LaneLocks = require("../lib/lanelocks")
						local lines = {}
						for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_bends") do
							if string.find(line, "do not say how they bend", 1, true) then
								table.insert(lines, line)
							end
						end
						return LaneLocks.report("world bend lock (selftest)", lines, "")
					end,
					{ "KinkedRoad" }
				),
				-- ... and a town that says neither "bend": <degrees> nor "bend": 0 holds it as well ...
				expectFail("world bend lock (a town that does not say how its streets run)", function()
					local LaneLocks = require("../lib/lanelocks")
					local lines = {}
					for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_bends") do
						if string.find(line, "do not say how their streets run", 1, true) then
							table.insert(lines, line)
						end
					end
					return LaneLocks.report("world town bend lock (selftest)", lines, "")
				end, { "UnsaidTown" }),
				-- ... and land 2,048 studs across with no "streaming" block (Roblox brings a place in to 1,024) ...
				expectFail(
					"world streaming lock (a world past 1,024 studs that does not say how it streams)",
					function()
						local LaneLocks = require("../lib/lanelocks")
						local lines = {}
						for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_reach") do
							if string.find(line, "does not say how it streams", 1, true) then
								table.insert(lines, line)
							end
						end
						return LaneLocks.report("world streaming lock (selftest)", lines, "")
					end,
					{ "WideLand" }
				),
				-- ... and a house big enough for two rooms that does not say "rooms": true or false ...
				expectFail("world rooms lock (a house that does not say whether it has rooms inside)", function()
					local LaneLocks = require("../lib/lanelocks")
					local lines = {}
					for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_rooms") do
						if string.find(line, "do not say whether they have rooms inside", 1, true) then
							table.insert(lines, line)
						end
					end
					return LaneLocks.report("world rooms lock (selftest)", lines, "")
				end, { "BareHouse" }),
				-- ... and a world prepared for streaming whose game's project does not turn streaming on ...
				expectFail(
					'world streaming switch lock ("streaming" in the blueprint, StreamingEnabled off in the project)',
					function()
						local LaneLocks = require("../lib/lanelocks")
						local lines = {}
						for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_switch") do
							if string.find(line, "does not turn streaming on", 1, true) then
								table.insert(lines, line)
							end
						end
						return LaneLocks.report("world streaming switch lock (selftest)", lines, "")
					end,
					{ "StreamsOff" }
				),
				-- ... and a town that does not say how its land lies ...
				expectFail("world slope lock (a town that does not say whether it lies on a slope)", function()
					local LaneLocks = require("../lib/lanelocks")
					local lines = {}
					for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_slope") do
						if string.find(line, "do not say how their land lies", 1, true) then
							table.insert(lines, line)
						end
					end
					return LaneLocks.report("world slope lock (selftest)", lines, "")
				end, { "UnsaidGround" }),
				-- ... and a world that streams and does not say how its players move, or moves them faster than the
				-- game keeps ground loaded, or leaves a landmark's streaming unsaid (the owner's W-R03) ...
				expectFail(
					"world loading intent (a world that streams and does not say how fast its players move)",
					function()
						local LaneLocks = require("../lib/lanelocks")
						local lines = {}
						for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_intent") do
							if string.find(line, "does not say how fast its players move", 1, true) then
								table.insert(lines, line)
							end
						end
						return LaneLocks.report("world loading intent (selftest)", lines, "")
					end,
					{ "UnsaidSpeed" }
				),
				expectFail("world loading intent (players faster than the ground the game keeps loaded)", function()
					local LaneLocks = require("../lib/lanelocks")
					local lines = {}
					for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_intent_fast") do
						if string.find(line, "StreamingMinRadius", 1, true) then
							table.insert(lines, line)
						end
					end
					return LaneLocks.report("world loading intent, radius (selftest)", lines, "")
				end, { "FastRider" }),
				expectFail("world loading intent (a landmark that does not say whether it streams out)", function()
					local LaneLocks = require("../lib/lanelocks")
					local lines = {}
					for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_intent_mark") do
						if string.find(line, "do not say whether they stream out", 1, true) then
							table.insert(lines, line)
						end
					end
					return LaneLocks.report("world loading intent, landmark (selftest)", lines, "")
				end, { "UnsaidMark" }),
				expectFail("world loading intent (a long drop whose landing is not named)", function()
					local LaneLocks = require("../lib/lanelocks")
					local lines = {}
					for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_intent_fall") do
						if string.find(line, "its players drop", 1, true) then
							table.insert(lines, line)
						end
					end
					return LaneLocks.report("world loading intent, drop (selftest)", lines, "")
				end, { "LongDrop" }),
				expectFail("world loading intent (a target radius under what its players need)", function()
					local LaneLocks = require("../lib/lanelocks")
					local lines = {}
					for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_intent_target") do
						if string.find(line, "StreamingTargetRadius", 1, true) then
							table.insert(lines, line)
						end
					end
					return LaneLocks.report("world loading intent, target (selftest)", lines, "")
				end, { "Flyer" }),
				-- ... and a town with house meshes that does not say how its houses are made ...
				expectFail(
					"world facade lock (a town with skins that does not say whether a grammar makes its houses)",
					function()
						local LaneLocks = require("../lib/lanelocks")
						local lines = {}
						for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_facade") do
							if string.find(line, "do not say how their houses are made", 1, true) then
								table.insert(lines, line)
							end
						end
						return LaneLocks.report("world facade lock (selftest)", lines, "")
					end,
					{ "UnsaidFronts" }
				),
				-- ... and a world with a weather that does not say whether it ever changes ...
				expectFail(
					"world weather lock (a world with an ambient that does not say whether it changes)",
					function()
						local LaneLocks = require("../lib/lanelocks")
						local lines = {}
						for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_weather") do
							if string.find(line, "does not say whether it ever changes", 1, true) then
								table.insert(lines, line)
							end
						end
						return LaneLocks.report("world weather lock (selftest)", lines, "")
					end,
					{ "SnowForEver" }
				),
				-- ... and a world under snow that does not say whether its roofs and ledges are snowed on ...
				expectFail(
					"world cover lock (a world under snow that does not say whether what it builds is snowed on)",
					function()
						local LaneLocks = require("../lib/lanelocks")
						local lines = {}
						for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_cover") do
							if
								string.find(line, "does not say whether its roofs and ledges are snowed on", 1, true)
							then
								table.insert(lines, line)
							end
						end
						return LaneLocks.report("world cover lock (selftest)", lines, "")
					end,
					{ "SnowRoofsBare" }
				),
				-- ... and a world whose weather closes the air in that does not say where the fog lies low ...
				expectFail(
					"world fog lock (a world whose weather closes the air in that does not say where the fog lies low)",
					function()
						local LaneLocks = require("../lib/lanelocks")
						local lines = {}
						for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_fog") do
							if string.find(line, "does not say where the fog lies low", 1, true) then
								table.insert(lines, line)
							end
						end
						return LaneLocks.report("world fog lock (selftest)", lines, "")
					end,
					{ "FogUnsaid" }
				),
				-- ... and a world with seasons that does not say which one it is built in ...
				expectFail(
					"world season lock (a world with seasons that does not say which one it is built in)",
					function()
						local LaneLocks = require("../lib/lanelocks")
						local lines = {}
						for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_season") do
							if string.find(line, "does not say which one it is built in", 1, true) then
								table.insert(lines, line)
							end
						end
						return LaneLocks.report("world season lock (selftest)", lines, "")
					end,
					{ "NoSeasonSaid" }
				),
				-- ... and a large scatter that does not say where its pieces go ...
				expectFail(
					"world scatter lock (scatters of 40 pieces or more together with no density word)",
					function()
						local LaneLocks = require("../lib/lanelocks")
						local lines = {}
						for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_scatter") do
							if string.find(line, "do not say where their pieces go", 1, true) then
								table.insert(lines, line)
							end
						end
						return LaneLocks.report("world scatter lock (selftest)", lines, "")
					end,
					{ "EvenStones" }
				),
				-- ... and a mixed forest that does not say how its kinds came to stand where they do ...
				expectFail(
					"world ecosystem lock (forests of two or more kinds, 40 trees or more, with no word)",
					function()
						local LaneLocks = require("../lib/lanelocks")
						local lines = {}
						for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_ecosystem") do
							if string.find(line, "how their kinds came to stand", 1, true) then
								table.insert(lines, line)
							end
						end
						return LaneLocks.report("world ecosystem lock (selftest)", lines, "")
					end,
					{ "MixedByChance" }
				),
				-- ... and a long road across the land that does not say how its way was found ...
				expectFail(
					"world route lock (a road across the land, 200 studs or more, typed by hand with no word)",
					function()
						local LaneLocks = require("../lib/lanelocks")
						local lines = {}
						for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_route") do
							if string.find(line, "do not say how their way was found", 1, true) then
								table.insert(lines, line)
							end
						end
						return LaneLocks.report("world route lock (selftest)", lines, "")
					end,
					{ "RoadByEye" }
				),
				-- ... and a painted land that does not say what climate painted it ...
				expectFail("world climate lock (a painted land with no climate and no word)", function()
					local LaneLocks = require("../lib/lanelocks")
					local lines = {}
					for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_climate") do
						if string.find(line, "do not say what climate painted them", 1, true) then
							table.insert(lines, line)
						end
					end
					return LaneLocks.report("world climate lock (selftest)", lines, "")
				end, { "NoClimateSaid" }),
				-- ... and six rooms typed one by one where a dungeon is laid out by rule ...
				expectFail("world rooms lock (six rooms typed one by one, no dungeon step and no word)", function()
					local LaneLocks = require("../lib/lanelocks")
					local lines = {}
					for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_rooms_typed") do
						if string.find(line, "rooms typed one by one", 1, true) then
							table.insert(lines, line)
						end
					end
					return LaneLocks.report("world rooms lock (selftest)", lines, "")
				end, { "CellsByHand" }),
				-- ... and a town that does not say whether its yards are dressed ...
				expectFail("world yards lock (a town that does not say whether its yards are dressed)", function()
					local LaneLocks = require("../lib/lanelocks")
					local lines = {}
					for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_yards") do
						if string.find(line, "do not say whether their yards are dressed", 1, true) then
							table.insert(lines, line)
						end
					end
					return LaneLocks.report("world yards lock (selftest)", lines, "")
				end, { "BareYards" }),
				-- ... and a town that does not say whether its square holds a market ...
				expectFail("world market lock (a town that does not say whether its square holds a market)", function()
					local LaneLocks = require("../lib/lanelocks")
					local lines = {}
					for _, line in LaneLocks.world(nil, "kit/selftest/locks/worlds_market") do
						if string.find(line, "do not say whether their square holds a market", 1, true) then
							table.insert(lines, line)
						end
					end
					return LaneLocks.report("world market lock (selftest)", lines, "")
				end, { "BareSquare" }),
				-- ... kit world check fails a "city" step (a regular grid of box blocks: the layout the plan replaces) ...
				expectFail('world check (design: a "city" grid of box blocks, not a town by plan)', function()
					return require("./world").checkStep("kit/selftest/world/_selftest_city_grid.json")
				end, { "design:", '"city" step "GridBlocks"' }),
				-- ... and a build of a world with a town ends on the town's plan page (its LOOK line), read from the
				-- blueprint: the page is drawn anew (the old one is removed first), a world with no town has no line
				function()
					local page = Config.build("worlds") .. "/town/SelftestTown_Town.png"
					if fs.isFile(page) then
						fs.removeFile(page)
					end
					local lines = require("./world").townLooks({
						"kit/selftest/world/_selftest_city_grid.json",
						"kit/selftest/world/_selftest_town.json",
					})
					local line = lines[1] or ""
					local ok = #lines == 1
						and string.sub(line, 1, 6) == "LOOK: "
						and string.find(line, "town from above (SelftestTown: 60 house(s)", 1, true) ~= nil
						and fs.isFile(page)
					return Run.step("world build ends on the town's plan page", ok, line, {
						status = if ok then "pass" else "fail",
						summary = if ok then "1 LOOK line, the page drawn anew" else `no plan page line: {line}`,
						next_action = if ok then "carry on" else "kit/cmd/world.luau WorldCmd.townLooks",
					})
				end,
				-- a BENT town ("bend": 8 - every block of houses moved and turned as one piece): its lanes are measured
				-- across themselves on the houses' own turned walls. With lanes 4 studs wide it fails the r6 sheet ...
				expectFail(
					"world check (a bent town with lanes 4 studs wide: every bent lane is measured across itself)",
					function()
						return require("./world").checkStep("kit/selftest/world/_selftest_town_bent_tight.json")
					end,
					{ "scale:", "(wants 8.0..)" }
				),
				-- ... and the fixture town bent 8 degrees passes: every street as wide as planned, every door reached,
				-- with the town's own 5 lamps and spawn pads in it. (This case does NOT measure the lamps' crowd: the
				-- fixture is exempt from the design gate and 5 lamps are under the gate's 6 - the spec does that:
				-- kit/test/spec/worldtownbend.spec.luau, "Town lamps")
				function()
					return require("./world").checkStep("kit/selftest/world/_selftest_town_bent.json")
				end,
				-- a town on a SLOPE ("slope": 6 studs in 100 toward the north): tilted ground cut round the houses, each
				-- house level at its own door, a market, dressed yards and lamps on the hillside - every door still
				-- reached, every street still as wide as the sheet asks (each claimed piece by piece over its own ground)
				function()
					return require("./world").checkStep("kit/selftest/world/_selftest_town_slope.json")
				end,
				-- a bent town with its YARDS dressed ("yards": true): woodpiles and wash lines standing in the yards with
				-- a gate, and every door still reached, every lane still as wide as the sheet asks
				function()
					return require("./world").checkStep("kit/selftest/world/_selftest_town_yards.json")
				end,
				-- a house cut into ROOMS by rule ("rooms": true, kit/lib/worldrooms.luau): a spawn outside its front door
				-- and one in its far corner room must reach each other through the rooms' own doorways
				function()
					return require("./world").checkStep("kit/selftest/world/_selftest_rooms.json")
				end,
				-- a lane on NEITHER axis (two walls turned 40 degrees by "turn", their claim turned with them): measured on
				-- the parts themselves. The voxel march along one world axis read this 6-stud lane as about 7.8 ...
				expectFail(
					"world check (a slanted lane 6 studs wide: the r6 sheet measures it across, not along an axis)",
					function()
						return require("./world").checkStep("kit/selftest/world/_selftest_turned_lane.json")
					end,
					{ "scale:", "w 6.0 (wants 8.0..)" }
				),
				-- ... and the same lane at 8 studs fits
				function()
					return require("./world").checkStep("kit/selftest/world/_selftest_turned_lane_fixed.json")
				end,
				-- the world's EYES (2026-11-12; the owner on an unlabelled frame: "I don't know what I'm exactly looking
				-- at"): kit world studio on a fixture with no Studio walk still makes one three-pane page a station, and
				-- its Studio pane says why it is empty ...
				-- (five stations: its two spawns, the view it names, back from its objective, from above)
				function()
					return require("./world").studioStep("kit/selftest/world/_selftest_look.json", false, 5)
				end,
				-- ... and a Studio capture planted from ANOTHER build is thrown away, never laid under this build's shots
				function()
					return require("./world").studioStep("kit/selftest/world/_selftest_look.json", true, 5)
				end,
				-- the owner's showcase worlds x5 (2026-10-14): trees, rocks and buildings left as primitive parts
				expectFail("world check (design: forest / rocks / buildings made of primitive parts only)", function()
					return require("./world").checkStep("kit/selftest/world/_selftest_primitive.json")
				end, { "design:" }), -- (the same map with mesh skins passes: kit/test/python/test_world_design.py)
				-- the owner's SampleRegion terrain v1 (2026-10-14, "the quality of the terrain is horrid"): land from noise +
				-- thermal erosion alone. A ROUTE gate (rivers or real land, proved by re-making the heightmap), never a
				-- look gate: the ACTUAL v1 heightmap (commit 7d4e0796) must fail it
				expectFail(
					"world check (design: the rejected SampleRegion v1 terrain, made without rivers or real elevation)",
					function()
						return require("./world").checkStep("kit/selftest/world/_selftest_terrain_v1.json")
					end,
					{ "design:", "without rivers or real elevation", "SampleRegion_terrain_v1" }
				),
				-- a river route written into a heightmap's recipe is PROVED, never trusted: a no-river terrain claiming it
				expectFail(
					"world check (design: a river route claimed in the recipe that terrain.py does not re-make)",
					function()
						return require("./world").checkStep("kit/selftest/world/_selftest_terrain_forged.json")
					end,
					{ "design:", "do not come from that recipe" }
				),
				function() -- and the same small land truly made on the river route (terrain.py re-makes it) passes
					return require("./world").checkStep("kit/selftest/world/_selftest_terrain_rivers.json")
				end,
				expectFail("fuzz (a rules function that throws on hostile input instead of answering)", function()
					return Run.spawn(
						"fuzz (selftest)",
						Run.tool("lune"),
						{ "run", "kit/test/fuzz", "kit/selftest/systems/Crashy.luau" },
						true
					)
				end, { "1 function(s) crash", "Crashy.luau check(" }),
				function() -- and its sturdy twin (type + NaN + inf checked first) passes
					local step = Run.spawn(
						"fuzz (selftest, sturdy)",
						Run.tool("lune"),
						{ "run", "kit/test/fuzz", "kit/selftest/systems/Sturdy.luau" },
						true
					)
					return step
				end,
				expectFail("net schema (a client number with no range, a request with no rate limit)", function()
					return require("./net").step(false, "kit/selftest/net/bad", Config.build("selftest/net_bad"))
				end, { '"min" and "max"', "rate" }),
				expectFail("net drift (a generated remote with one Guard check deleted by hand)", function()
					-- generated fresh into build/, then one Guard line deleted (a broken .luau never lives in the repo:
					-- selene lints everything)
					local NetCmd = require("./net")
					local out = Config.build("selftest/net_drift")
					local made = NetCmd.step(true, "kit/selftest/net/drift", out)
					if not made.ok then
						return made
					end
					local file = out .. "/StrikeNet.luau"
					local src = fs.readFile(file)
					local cut = string.gsub(src, "\n[^\n]*Guard%.number%(a2, 0, 1%)[^\n]*", "", 1)
					fs.writeFile(file, cut)
					return NetCmd.step(false, "kit/selftest/net/drift", out)
				end, { "out of date" }),
				expectFail(
					"anim pop gate (a 150 degree one-frame snap)",
					Content.animFixture("_selftest_pop"),
					{ "pops" }
				),
				expectFail(
					"anim foot-slide gate (the body drifts on planted feet)",
					Content.animFixture("_selftest_slide"),
					{ "foot slide" }
				),
				expectFail(
					"anim loop-seam gate (a loop that ends 40 degrees away)",
					Content.animFixture("_selftest_seam"),
					{ "loop seam" }
				),
				-- the owner's rejected weapon switches (slow motion: the arms peak at 973 deg/s) - a switch is a snap
				expectFail(
					"anim switch-speed gate (a weapon switch whose arms barely move)",
					Content.animFixture("_selftest_switch_slow"),
					{ "switch arm speed" }
				),
				-- the owner's NAMED faults (kit/anim/owner_faults.py, 2026-11-10: "The animation really needs a lot of
				-- work"), each on a REAL clip he rejected for it, kept verbatim in kit/selftest/anim/faults/rejected - a
				-- weapon candidate with one never reaches him (proc_candidates.gate): DTDrillSpin4 (1/10, 11-04: the
				-- blade flops 42 deg off its plane, the legs wrung 178 deg round under the spin), GreatswordSideCut v1
				-- (1/10, 10-17: the hand in a 2.2-stud box, the legs straight), a Swift swing v2 (11-04: 'leg work
				-- is horrible' - the crouch only a dip); the cuts whose legs and arms he loved must still pass
				expectFail(
					"anim owner faults (DTDrillSpin4 1/10: the blade flops, the legs twist under the spin)",
					function()
						return Run.content("anim owner faults", Run.tool("python"), {
							"kit/anim/owner_faults.py",
							"check",
							"kit/selftest/anim/faults/rejected/DTDrillSpin4.move.json",
						})
					end,
					{ "blade flops", "legs twist" }
				),
				expectFail("anim owner faults (GreatswordSideCut v1 1/10: stilts, an arm-only cut)", function()
					return Run.content("anim owner faults", Run.tool("python"), {
						"kit/anim/owner_faults.py",
						"check",
						"kit/selftest/anim/faults/rejected/GreatswordSideCut_v1.move.json",
					})
				end, { "stilts", "arm-only" }),
				expectFail("anim owner faults (a Swift swing v2, 'leg work is horrible': stilts)", function()
					return Run.content("anim owner faults", Run.tool("python"), {
						"kit/anim/owner_faults.py",
						"check",
						"kit/selftest/anim/faults/rejected/SwordTrickArmsWide.move.json",
					})
				end, { "stilts" }),
				function() -- and the cuts he loved, legs and arms (GsCombo1-4, Katana1-3), pass every one
					local loved = "kit/selftest/anim/faults/loved/"
					return Run.content("anim owner faults: the loved cuts pass (selftest)", Run.tool("python"), {
						"kit/anim/owner_faults.py",
						"check",
						loved .. "GsCombo1SideLeft.move.json",
						loved .. "GsCombo2SideRight.move.json",
						loved .. "GsCombo3Overhead.move.json",
						loved .. "GsCombo4Underhip.move.json",
						loved .. "Katana1Kesa.move.json",
						loved .. "Katana2GyakuKesa.move.json",
						loved .. "Katana3Makko.move.json",
					})
				end,
				-- BLOCKING THE OWNER APPROVES FROM A PICTURE (kit/anim/blocking.py, the animation studio route's A2,
				-- 2026-11-13), on a cut he loved (read only; a changed pose is a copy in the run's own folder): the
				-- whole round must hold - six poses held at the move's timing, his note on pose 3 open while the pose
				-- stands and answered once it turned 15 degrees, his yes holding for exactly those poses - and the
				-- three ways it must say NO: a note not answered, a pose changed after his yes, a yes that is not his
				function()
					return Run.content(
						"anim blocking (the loved kesa: held poses, a note open then answered, his yes holds)",
						Run.tool("python"),
						{ "kit/selftest/anim/blocking/run.py", "good" }
					)
				end,
				expectFail("anim blocking (the owner's note on a pose that was left as he saw it)", function()
					return Run.content(
						"anim blocking (open note)",
						Run.tool("python"),
						{ "kit/selftest/anim/blocking/run.py", "open" }
					)
				end, { "not answered", "pose 3", "as he saw it" }),
				expectFail("anim blocking (a key pose turned 15 degrees after the owner's yes)", function()
					return Run.content(
						"anim blocking (stale yes)",
						Run.tool("python"),
						{ "kit/selftest/anim/blocking/run.py", "stale" }
					)
				end, { "stale", "another blocking", "pose 3: Right Arm turned" }),
				expectFail("anim blocking (a yes nobody said was the owner's)", function()
					return Run.content(
						"anim blocking (a proposal)",
						Run.tool("python"),
						{ "kit/selftest/anim/blocking/run.py", "proposal" }
					)
				end, { "only the owner approves" }),
				-- THE FINISHED CLIP HELD TO THE POSES HE APPROVED (kit/anim/blocking.py kept, the studio route's A4): the
				-- clip built from the approved keys keeps all six poses (and a move without his yes is held to nothing);
				-- the clip of the same move with pose 3's key turned 15 degrees after his yes must be named
				function()
					return Run.content(
						"anim kept (a clip rebuilt from the approved keys keeps every pose)",
						Run.tool("python"),
						{ "kit/selftest/anim/blocking/run.py", "kept" }
					)
				end,
				expectFail("anim kept (a finished clip whose pose 3 is 15 degrees off the approved one)", function()
					return Run.content(
						"anim kept (drift)",
						Run.tool("python"),
						{ "kit/selftest/anim/blocking/run.py", "drift" }
					)
				end, {
					"DRIFTS from the blocking the owner approved",
					"on 1 of 6 pose(s) - pose 3",
					"deg from the pose he approved",
				}),
				-- POSES FIRST, MOTION AFTER (kit/anim/blocking.py lock; the owner 2026-11-13: every method "enforced in
				-- the terms of being used"): a move made after the rule is held until his yes to its key poses as they
				-- are (a record typed by hand is no yes), a move on the frozen list of those made before it is never
				-- asked; and a move nobody showed him must not be made
				function()
					return Run.content(
						"anim blocking lock (held until his yes, again when a pose changed; a typed record frees nothing)",
						Run.tool("python"),
						{ "kit/selftest/anim/blocking/run.py", "lock" }
					)
				end,
				expectFail("anim blocking lock (a new move whose key poses the owner was never shown)", function()
					return Run.content(
						"anim blocking lock (a new move)",
						Run.tool("python"),
						{ "kit/selftest/anim/blocking/run.py", "locked" }
					)
				end, { "STOP - a NEW move", "do not have the owner's yes", "Poses first, motion after" }),
				-- THE ATTACK SET'S DESIGN PAGE (kit/anim/set_design.py, the studio route's A1): the loved katana string as
				-- a design is whole, has no cousins and its keys are its design, and its move waits for the owner's yes
				-- to the design; the same string with its third attack a re-make of the first must name the COUSINS;
				-- a move of a set whose design he never approved must not be made
				function()
					return Run.content(
						"anim design (the loved katana string: whole, no cousins, its move waits for his yes)",
						Run.tool("python"),
						{ "kit/selftest/anim/design/run.py", "good" }
					)
				end,
				expectFail("anim design (a set whose third attack is its first cut made again)", function()
					return Run.content(
						"anim design (cousins)",
						Run.tool("python"),
						{ "kit/selftest/anim/design/run.py", "cousins" }
					)
				end, {
					"attack 1 (Katana1Kesa) and attack 3 (KesaAgain) are COUSINS",
					"their blades run 0.2 studs apart",
				}),
				expectFail(
					"anim design (a string linked by pose whose first attack does not end where the next starts)",
					function()
						return Run.content(
							"anim design (a broken link)",
							Run.tool("python"),
							{ "kit/selftest/anim/design/run.py", "broken" }
						)
					end,
					{
						"the string BREAKS: attack 1 (Katana1Kesa) ends 14",
						"linked by pose",
					}
				),
				expectFail("anim design (a move of a set whose design the owner never approved)", function()
					return Run.content(
						"anim design (no yes to the design)",
						Run.tool("python"),
						{ "kit/selftest/anim/design/run.py", "undesigned" }
					)
				end, {
					"STOP - a NEW move of a set whose design does not have the owner's yes",
					"The set first, then its moves",
				}),
				-- A HAND-POSED FILE blocked and locked (kit/anim/blocking.py, source and lock kind "pose", 2026-11-14):
				-- its keys are held as its poses, the move waits for the owner's yes to that sheet and is held again
				-- when the file changes; a posed move nobody showed him must not be built
				function()
					return Run.content(
						"anim posed (a posed file's keys held; held until his yes, again when the file changed)",
						Run.tool("python"),
						{ "kit/selftest/anim/posed/run.py", "good" }
					)
				end,
				expectFail("anim posed (a hand-posed move whose key poses the owner was never shown)", function()
					return Run.content(
						"anim posed (a new posed move)",
						Run.tool("python"),
						{ "kit/selftest/anim/posed/run.py", "locked" }
					)
				end, { "STOP - a NEW move", "do not have the owner's yes" }),
				-- A PROP's RIG FROM DATA, its clips held to its joints (kit/anim/prop_rig.py, in the build's motion gates;
				-- the owner's method lists 2026-11-13: object animation): a chest made of a base, a hinged lid, a
				-- sliding tray and a fixed handle becomes a rig the kit's own FK opens about its hinge; a clip that
				-- swings the lid through its stop must fail the motion gates, naming the part
				function()
					return Run.content(
						"anim prop (a chest's rig from data; its lid opens about its hinge, its tray slides)",
						Run.tool("python"),
						{ "kit/selftest/anim/prop/run.py", "good" }
					)
				end,
				expectFail("anim prop (a lid swung 30 degrees through its stop)", function()
					return Run.content(
						"anim prop (through the stop)",
						Run.tool("python"),
						{ "kit/selftest/anim/prop/run.py", "torn" }
					)
				end, { "Lid turns to 140 deg; its hinge runs 0 to 110", "as its joint allows" }),
				-- A PROP'S CLIP THE WHOLE WAY (kit/anim/prop_rig.py go, `kit anim prop`): the chest's prop file and a
				-- keyframe spec through the kit's own compiler to the KeyframeSequence model the game plays, the clip
				-- held to the joints in between; a spec that swings the lid through its stop must leave NO model
				function()
					return Run.content(
						"anim prop (a prop's spec the whole way to the model the game plays)",
						Run.tool("python"),
						{ "kit/selftest/anim/prop/run.py", "whole" }
					)
				end,
				expectFail("anim prop (a spec that breaks a joint leaves no model)", function()
					return Run.content(
						"anim prop (a spec through the stop)",
						Run.tool("python"),
						{ "kit/selftest/anim/prop/run.py", "spec" }
					)
				end, { "1 of 1 clip(s) NOT built", "Lid turns to 140 deg; its hinge runs 0 to 110" }),
				-- CLEAN-UP (kit/anim/cleanup.py, the `plant` op of a derive recipe; the owner's method lists: motion
				-- capture cleanup): a loved cut given a skate is planted back to its own feet by the build's own
				-- reading; ten studs of travel are not taken for a skate
				function()
					return Run.content(
						"anim cleanup (feet that skate are held where they stood)",
						Run.tool("python"),
						{ "kit/selftest/anim/cleanup/run.py", "good" }
					)
				end,
				expectFail("anim cleanup (travel is not skate)", function()
					return Run.content(
						"anim cleanup (ten studs of travel)",
						Run.tool("python"),
						{ "kit/selftest/anim/cleanup/run.py", "travel" }
					)
				end, { "that is travel, not skate", "max_shift" }),
				-- POSE, DISTANCE AND MOTION MATCHING (kit/anim/match_tables.py bakes the tables, src/kit/AnimMatch.luau
				-- matches in the game; the owner's method lists): the game's matcher gives the build's answers on the
				-- loved cuts; a body that steps back on its way gives no distance table
				function()
					return Run.content(
						"anim match (the game's matcher answers as the build does)",
						Run.tool("python"),
						{ "kit/selftest/anim/match/run.py", "same" }
					)
				end,
				expectFail("anim match (a body that steps back gives no distance table)", function()
					return Run.content(
						"anim match (a step back on the way to the stop)",
						Run.tool("python"),
						{ "kit/selftest/anim/match/run.py", "back" }
					)
				end, { "no table", "the body travels back", "one distance would mean two frames" }),
				-- A MOTION SET (kit/anim/match_tables.py set; `kit anim` bakes assets/animations/motion/<Set>.motion.json
				-- into the game for src/kit/Anim.motion): its database, the game's own step held to the build's; a set
				-- that names a clip nobody built gives no database
				function()
					return Run.content(
						"anim motion set (a database, and the game's step on it)",
						Run.tool("python"),
						{ "kit/selftest/anim/match/run.py", "set" }
					)
				end,
				expectFail("anim motion set (it names a clip that is not built)", function()
					return Run.content(
						"anim motion set (a clip nobody built)",
						Run.tool("python"),
						{ "kit/selftest/anim/match/run.py", "unbuilt" }
					)
				end, { "no table", "names the clip Katana4Ghost, which this build did not make" }),
				-- A DRIVER (kit/anim/drivers.py, the `drive` op of a derive recipe; the owner's method lists: driver /
				-- expression-driven animation): the head given half the torso's turn on the loved cut; the sword arm
				-- driven by the torso would take the hand off the weapon and is refused
				function()
					return Run.content(
						"anim driver (the head follows the torso by a rule)",
						Run.tool("python"),
						{ "kit/selftest/anim/drive/run.py", "good" }
					)
				end,
				expectFail("anim driver (a driven sword arm lets go of the weapon)", function()
					return Run.content(
						"anim driver (the sword arm driven by the torso)",
						Run.tool("python"),
						{ "kit/selftest/anim/drive/run.py", "arm" }
					)
				end, { "takes a hand off the weapon", "the blade is not driven" }),
				-- A PROP THE 3D LANE BUILT (kit/anim/prop_rig.py from_model, `kit anim prop <asset> --model`): a built
				-- model's manifest gives the rig of the model the game spawns, its spec goes the whole way; a moving
				-- part hung on a part that does not move is carried through it (V3 Stage D, 2026-11-17: it was
				-- refused before); a moving part hung on a part the model does not have is refused, named
				function()
					return Run.content(
						"anim prop (a built model's joints: its spec the whole way)",
						Run.tool("python"),
						{ "kit/selftest/anim/prop/run.py", "model" }
					)
				end,
				function()
					return Run.content(
						"anim prop (a bolt hung on the fixed post: carried through it)",
						Run.tool("python"),
						{ "kit/selftest/anim/prop/run.py", "carried" }
					)
				end,
				expectFail("anim prop (a moving part hung on a part the model does not have)", function()
					return Run.content(
						"anim prop (a bolt hung on a ghost)",
						Run.tool("python"),
						{ "kit/selftest/anim/prop/run.py", "orphan" }
					)
				end, { "is not a prop the kit can rig", "hangs on 'ghost', which is not a part of the model" }),
				-- THE WEAPON IN A HAND AT EVERY FRAME (kit/anim/in_hand.py, in the build's motion gates; the owner's method
				-- lists 2026-11-13: attachment sockets): the loved kesa holds its sword at every frame, and so does the
				-- same clip with a toss it declares; the same clip with the sword lifted off the hands for five frames
				-- and no toss declared must fail the motion gates, naming the frames
				function()
					return Run.content(
						"anim in-hand (a loved cut holds its sword; a declared toss is meant)",
						Run.tool("python"),
						{ "kit/selftest/anim/hand/run.py", "good" }
					)
				end,
				expectFail("anim in-hand (a sword out of both hands for five frames, no toss declared)", function()
					return Run.content(
						"anim in-hand (a loose weapon)",
						Run.tool("python"),
						{ "kit/selftest/anim/hand/run.py", "loose" }
					)
				end, { "the weapon is in NO hand for 5 frame(s)", "with no toss or draw declared", "frames 10-14" }),
				-- NOTHING PASSES THROUGH THE BODY (kit/anim/collide.py, in the build's motion gates; the owner's limitations
				-- list 2026-11-15, A-R05): nothing goes through the loved kesa's body, and the same clip with an arm in the
				-- chest and that contact declared is not failed for it; the arm in the chest with no contact declared
				-- must fail the motion gates, naming the part and the frame
				function()
					return Run.content(
						"anim pass-through (a loved cut is clear; a declared contact is meant)",
						Run.tool("python"),
						{ "kit/selftest/anim/collide/run.py", "good" }
					)
				end,
				expectFail("anim pass-through (an arm swung into the chest, no contact declared)", function()
					return Run.content(
						"anim pass-through (a hand in the chest)",
						Run.tool("python"),
						{ "kit/selftest/anim/collide/run.py", "through" }
					)
				end, { "Right Arm: a hand goes into the Torso by 0.50 studs", "at frame 10", "at most 0.35" }),
				-- WHERE A STRIKE MEETS ITS TARGET (kit/anim/contact.py, in the build's motion gates; the owner's limitations
				-- list 2026-11-15, A-R06): the loved overhead's authored Hit is where its blade meets the target, and the
				-- same Hit moved by its author to the blade's fastest frame is said, not failed; that Hit placed there by
				-- the BUILD (the old speed-peak inference) must fail the motion gates, naming both frames
				function()
					return Run.content(
						"anim contact (an authored Hit is where the blade meets the target)",
						Run.tool("python"),
						{ "kit/selftest/anim/contact/run.py", "good" }
					)
				end,
				expectFail(
					"anim contact (a Hit the build placed at the fastest frame, before the blade arrives)",
					function()
						return Run.content(
							"anim contact (an inferred Hit off the contact)",
							Run.tool("python"),
							{ "kit/selftest/anim/contact/run.py", "early" }
						)
					end,
					{
						"Hit is at frame 24 and the weapon meets the target at frame 29",
						"5 frame(s) later",
						"author it",
					}
				),
				-- A PATH DRAWN FOR THE BLADE (kit/anim/blade_path.py, in the build's motion gates; the owner's method lists
				-- 2026-11-13: motion path animation): the loved kesa passes through ten points drawn off its own blade
				-- path and a move that draws none is held to nothing; the clip of the move with two keys' grip raised a
				-- stud leaves the drawn line and must fail the motion gates, naming the point
				function()
					return Run.content(
						"anim path (a loved cut passes through the points drawn for its blade)",
						Run.tool("python"),
						{ "kit/selftest/anim/path/run.py", "good" }
					)
				end,
				expectFail("anim path (a blade pulled a stud off the line drawn for it)", function()
					return Run.content(
						"anim path (off the line)",
						Run.tool("python"),
						{ "kit/selftest/anim/path/run.py", "off" }
					)
				end, { "the blade of SelftestPathOff MISSES", "of the 10 point(s) drawn for it", "(0.5 allowed)" }),
				-- THE TIMING CHART (kit/anim/timing_chart.py; the owner's method lists 2026-11-13: a file no command ran,
				-- now `kit anim timing` and a page of every sheet): the loved kesa charted against its own move reads
				-- what the move says (the frames between the keys span the clip, the Hit on the fastest frame, an
				-- uneven cut); charted against ANOTHER move's keys it must not be drawn and must say so
				function()
					return Run.content(
						"anim timing (the loved kesa's chart reads its own move: key gaps, the Hit, the spacing)",
						Run.tool("python"),
						{ "kit/selftest/anim/timing/run.py", "good" }
					)
				end,
				expectFail("anim timing (a clip charted against a move it was not built from)", function()
					return Run.content(
						"anim timing (wrong move)",
						Run.tool("python"),
						{ "kit/selftest/anim/timing/run.py", "wrong" }
					)
				end, { "the chart is NOT drawn", "this clip was not built from this move file" }),
				expectFail("anim dossier gate (a new clip with no move dossier is never built)", function()
					return Run.content(
						"anim dossier gate",
						Run.tool("python"),
						{ "kit/anim/proc_dossier.py", "gate", "SelftestNoDossier=_selftest_no_dossier" }
					)
				end, { "without a complete move dossier" }),
				-- PROMPT-X (LIMITATIONS_FIXES_V4 13.7, the six mandatory traps): the worked example compiles in shape and
				-- budget for all four models with its grounding, and the 10 real failed owner prompts each carry their
				-- guardrail; a FLUX prompt keeping "no fire", a codex prompt keeping a step-by-step script, an unpruned
				-- local render, an unhydrated packet, a wholesale playbook rewrite and templates stripped of their
				-- hard-won rules must each be refused
				function()
					return Run.content(
						"prompt-x (four profiles, budgets, grounding, 10/10 historical prompts guarded)",
						Run.tool("python"),
						{ "kit/selftest/prompt/run.py", "good" }
					)
				end,
				expectFail("prompt-x negative word leak (a FLUX.2 prompt that kept 'no fire')", function()
					return Run.content("prompt leak", Run.tool("python"), { "kit/selftest/prompt/run.py", "leak" })
				end, { "negative word leak" }),
				expectFail("prompt-x model drift (a codex prompt that kept a think-step-by-step script)", function()
					return Run.content("prompt cot", Run.tool("python"), { "kit/selftest/prompt/run.py", "cot" })
				end, { "chain-of-thought script" }),
				expectFail("prompt-x token budget (a six-lane ask rendered for the local model unpruned)", function()
					return Run.content("prompt budget", Run.tool("python"), { "kit/selftest/prompt/run.py", "budget" })
				end, { "over budget" }),
				expectFail("prompt-x grounding (a packet whose repo grounding was never hydrated)", function()
					return Run.content(
						"prompt grounding",
						Run.tool("python"),
						{ "kit/selftest/prompt/run.py", "grounding" }
					)
				end, { "missing repo grounding" }),
				expectFail("prompt-x context collapse (evolve handed a wholesale playbook rewrite)", function()
					return Run.content(
						"prompt collapse",
						Run.tool("python"),
						{ "kit/selftest/prompt/run.py", "collapse" }
					)
				end, { "context collapse" }),
				expectFail("prompt-x historical replay (lane templates stripped of their hard-won rules)", function()
					return Run.content("prompt replay", Run.tool("python"), { "kit/selftest/prompt/run.py", "replay" })
				end, { "historical replay MISSED" }),
				-- PROMPT-X Phase 2 (V4 11 Phase 2 item 5): the parts libraries' cards, the API's exact signatures and a
				-- per-case held-out benchmark - a packet compiled without the Parts RAG, one whose API lost its
				-- signatures and a delta that trades one held-out case for another must each be refused
				expectFail("prompt-x parts (a packet compiled with the Parts RAG skipped)", function()
					return Run.content("prompt parts", Run.tool("python"), { "kit/selftest/prompt/run.py", "parts" })
				end, { "missing repo grounding: parts" }),
				expectFail("prompt-x docs (API names without their Luau signatures)", function()
					return Run.content("prompt docs", Run.tool("python"), { "kit/selftest/prompt/run.py", "docs" })
				end, { "API signature missing" }),
				expectFail("prompt-x held-out regression (a delta trading one benchmark case for another)", function()
					return Run.content(
						"prompt regress",
						Run.tool("python"),
						{ "kit/selftest/prompt/run.py", "regress" }
					)
				end, { "held-out regression" }),
				function()
					local tests = Run.spawn(
						"kit specs (incl. audit + vfx + ui negatives)",
						Run.tool("lune"),
						{ "run", "kit/test/run", "kit" }
					)
					return tests
				end,
			}, function()
				return C.CONTENT
			end)
		end
	)
end

return Qa

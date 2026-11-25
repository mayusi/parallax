-- run.luau — shared step runner + verdict writer for every kit command.
-- Every command ends in ONE verdict file: .verify/<name>.json with status, summary, next_action, steps.
-- Exit codes (the contract): 0 pass · 1 lint/format · 2 unit · 3 build/sync · 4 playtest
--                            5 toolchain missing · 6 content gate (asset/audio/vfx/ui spec failed) · 7 usage
-- Programs run via process.exec(program, args) — argument array, no shell, so no injection surface.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")
local task = require("@lune/task")

local VisionWorker = require("./visionworker")

local Run = {}

Run.CODES = { PASS = 0, LINT = 1, UNIT = 2, BUILD = 3, PLAYTEST = 4, TOOLCHAIN = 5, CONTENT = 6, USAGE = 7 }

-- called by Run.report on a failure that is not a usage error or a missing tool (kit doctor answers that, not a
-- lesson): (report file, summary, the failing steps' tails), after the failing tails and before the summary lines.
-- kit/init.luau points it at kit/lib/failhints.luau; nil in specs and plain library use.
Run.onFail = nil :: ((string, string, string) -> ())?
-- where Run.report's lines go (a spec reads them; print everywhere else)
Run.out = (print :: any) :: (...any) -> ()

export type Step = {
	name: string,
	cmd: string,
	exit: number,
	ok: boolean,
	tail: string,
	result: any?,
	seconds: number?, -- (wall time: a spawned step's own, else the time Run.chain waited for it)
}

-- a duration a person reads: "45s", "38m 12s"
function Run.clock(seconds: number): string
	local s = math.floor(seconds + 0.5)
	return if s >= 60 then `{s // 60}m {s % 60}s` else `{s}s`
end

local function tail(text: string, count: number): string
	local lines = string.split(text, "\n")
	while #lines > 0 and string.gsub(lines[#lines], "%s", "") == "" do
		table.remove(lines)
	end
	local out = table.concat({ table.unpack(lines, math.max(1, #lines - count + 1), #lines) }, "\n")
	-- a tool's progress bars can print bytes that are not UTF-8 (a code page's block characters): the JSON report
	-- cannot hold them (serde stops: "invalid type: byte array") — such bytes become "?"
	if utf8.len(out) == nil then
		out = string.gsub(out, "[\128-\255]", "?")
	end
	return out
end

-- Last stdout line starting with `{` is parsed as the step's machine result (validate.py, synth.py, ...).
local function lastJson(text: string): any?
	local lines = string.split(text, "\n")
	for i = #lines, 1, -1 do
		local line = string.gsub(lines[i], "\r$", "")
		if string.sub(line, 1, 1) == "{" then
			local ok, decoded = pcall(serde.decode, "json" :: any, line)
			if ok then
				return decoded
			end
		end
	end
	return nil
end

-- Resolve a tool: env override first (BLENDER, PYTHON), then known install paths, then PATH.
local pythonExe: string? = nil -- (Run.tool on POSIX: python or python3, probed once)

function Run.tool(name: string): string
	local env = process.env[string.upper(name)]
	if env and env ~= "" then
		return env
	end
	-- environments' pythons (kit/gen/README.md): trellis2 (TRELLIS.2 + the phase B vision models), omni
	-- (Hunyuan3D-Omni), hunyuan3d2 (Hunyuan3D-2 mv shape + Paint), diffusers (DiffusionLight-Turbo, FLUX.2 klein), partcrafter (PartCrafter), mitsuba (Mitsuba 3, differentiable rendering), cad (build123d + OpenCASCADE) — the last two
	-- made by `kit tools setup`
	local envs = {
		trellis2 = "trellis2",
		omni = "hunyuan3d-omni",
		hunyuan3d2 = "hunyuan3d2",
		diffusers = "diffusers",
		partcrafter = "partcrafter",
		mitsuba = "mitsuba",
		cad = "cad",
	}
	if envs[name] then
		local home = process.env.USERPROFILE or process.env.HOME or ""
		for _, candidate in
			{
				`{home}/.cache/roblox-kit/envs/{envs[name]}/Scripts/python.exe`,
				`{home}/.cache/roblox-kit/envs/{envs[name]}/bin/python`,
			}
		do
			if fs.isFile(candidate) then
				return candidate
			end
		end
	end
	if name == "python" and process.os ~= "windows" then
		-- (a POSIX machine may have only python3: probed once, python first)
		if pythonExe == nil then
			local ok = pcall(function()
				return process.exec("python", { "--version" })
			end)
			pythonExe = if ok then "python" else "python3"
		end
		return pythonExe :: string
	end
	if name == "blender" then
		-- the same order as kit/blender_path.py (the Python tools run the same Blender): KIT_BLENDER / BLENDER, then
		-- the OS's install folders (newest version first, compared as numbers), then a bare "blender" (returned below)
		-- that the OS finds on the PATH - after the install folders, so an old Blender on the PATH never wins
		for _, var in { "KIT_BLENDER", "BLENDER" } do
			local v = process.env[var]
			if v and v ~= "" and fs.isFile(v) then
				return v
			end
		end
		local found = Run.blenderInstalled()
		if found then
			return found
		end
	end
	return name
end

-- the numbers in a folder name, for comparing versions ("Blender 5.10" after "Blender 5.2")
local function versionOf(dir: string): { number }
	local out = {}
	for n in string.gmatch(dir, "%d+") do
		table.insert(out, tonumber(n) :: number)
	end
	return out
end

local function newer(a: { number }, b: { number }): boolean
	for i = 1, math.max(#a, #b) do
		local x, y = a[i] or -1, b[i] or -1
		if x ~= y then
			return x > y
		end
	end
	return false
end

-- the newest <base>/<dir>/<exe> whose dir matches `pattern` (or nil); `caseless`: the match ignores case (Windows,
-- where a folder name's case does not matter). A tie (the same numbers) goes to the plainer name - the shorter, then
-- the first in order ("Blender 5.2" before "Blender 5.2 Alpha") - the same rule as kit/blender_path.py
local function newestIn(base: string, pattern: string, exe: string, caseless: boolean?): string?
	if not fs.isDir(base) then
		return nil
	end
	local best, bestVer, bestName = nil, {}, ""
	for _, dir in fs.readDir(base) do
		local path = `{base}/{dir}/{exe}`
		local name = string.lower(dir)
		if string.match(if caseless then name else dir, pattern) and fs.isFile(path) then
			local ver = versionOf(dir)
			local tie = not newer(ver, bestVer) and not newer(bestVer, ver)
			if
				best == nil
				or newer(ver, bestVer)
				or (tie and (#name < #bestName or (#name == #bestName and name < bestName)))
			then
				best, bestVer, bestName = path, ver, name
			end
		end
	end
	return best
end

-- Blender in the OS's usual install folders (kit/blender_path.py _os_scan): Windows Program Files, then the per-user
-- Programs folder; macOS /Applications, then ~/Applications; Linux /usr/bin, /usr/local/bin, /snap/bin, then /opt
function Run.blenderInstalled(): string?
	if process.os == "windows" then
		local localData = process.env.LOCALAPPDATA or ((process.env.USERPROFILE or "") .. "/AppData/Local")
		for _, base in { "C:/Program Files/Blender Foundation", localData .. "/Programs/Blender Foundation" } do
			local hit = newestIn(base, "^blender ", "blender.exe", true)
			if hit then
				return hit
			end
		end
		return nil
	end
	local home = process.env.HOME or ""
	local candidates = if process.os == "macos"
		then {
			"/Applications/Blender.app/Contents/MacOS/Blender",
			home .. "/Applications/Blender.app/Contents/MacOS/Blender",
		}
		else { "/usr/bin/blender", "/usr/local/bin/blender", "/snap/bin/blender" }
	for _, candidate in candidates do
		if fs.isFile(candidate) then
			return candidate
		end
	end
	if process.os ~= "macos" then
		return newestIn("/opt", "^blender", "blender")
	end
	return nil
end

function Run.spawn(name: string, program: string, args: { string }, quiet: boolean?, env: { [string]: string }?): Step
	local cmd = program .. " " .. table.concat(args, " ")
	-- the active game always travels to the child (a variable written to process.env at runtime is NOT inherited
	-- by process.exec: `kit test --game SampleDojo` ran the kit's specs but never the SampleDojo's)
	local childEnv: { [string]: string } = table.clone(env or {})
	-- (both names: a PARALLAX_GAME inherited from the shell must not outrank the --game this command ran with)
	local game = process.env.PARALLAX_GAME or process.env.KIT_GAME
	if childEnv.KIT_GAME == nil and type(game) == "string" and game ~= "" then
		childEnv.KIT_GAME = game
		childEnv.PARALLAX_GAME = game
	end
	-- children of a governance command (kit verify / selftest / prove, PARALLAX spec §2.2) are never gated by the
	-- Parallax CLI gate: the nonce kit/lib/enforcer.luau minted travels to them (a runtime process.env write is not
	-- inherited), and only a filed nonce counts
	local exempt = process.env.PARALLAX_EXEMPT
	if childEnv.PARALLAX_EXEMPT == nil and type(exempt) == "string" and #exempt >= 32 then
		childEnv.PARALLAX_EXEMPT = exempt
	end
	-- REPRODUCIBLE PYTHON: one hash seed for every kit child (unless the shell set its own). Python randomises the
	-- order of a set of strings per process, so a tie broken by set order came out different run to run: the same
	-- clip's metrics named Right Arm, Left Arm or Blade as a Hit's striker for seeds 1..8 (kit/anim/clip.py metrics,
	-- `for e in set(strikers) | {lead}`; found by the A5 serial-vs-parallel parity check, 2026-11-22)
	if childEnv.PYTHONHASHSEED == nil and process.env.PYTHONHASHSEED == nil then
		childEnv.PYTHONHASHSEED = "0"
	end
	local t0 = os.clock()
	local ok, result = pcall(process.exec, program, args, if next(childEnv) then { env = childEnv } else nil)
	local seconds = os.clock() - t0
	if not ok then
		return {
			name = name,
			cmd = cmd,
			exit = 127,
			ok = false,
			tail = "spawn failed (missing binary? run: lune run kit doctor): " .. tostring(result),
			seconds = seconds,
		}
	end
	local out = (result.stdout or "") .. "\n" .. (result.stderr or "")
	local step: Step = {
		name = name,
		cmd = cmd,
		exit = result.code,
		ok = result.ok and result.code == 0,
		tail = tail(out, 20),
		result = lastJson(result.stdout or ""),
		seconds = seconds,
	}
	if not quiet then
		-- (its time on the line: the owner, 2026-11-23, could not tell what an hour of kit verify was spent on)
		print(`[{step.ok and "ok" or "FAIL"}] {name}{if seconds >= 1 then ` ({Run.clock(seconds)})` else ""}`)
	end
	return step
end

-- Write .verify/<file>.json, print summary + next_action (the only lines weak models need), return code.
function Run.report(file: string, steps: { Step }, code: number, summary: string, nextAction: string): number
	local report = {
		schema = 2,
		status = code == Run.CODES.PASS and "pass" or "fail",
		exit = code,
		summary = summary,
		next_action = nextAction,
		steps = steps,
	}
	if not fs.isDir(".verify") then
		fs.writeDir(".verify")
	end
	fs.writeFile(`.verify/{file}.json`, serde.encode("json", report, true))
	if code ~= Run.CODES.PASS then
		local tails = {}
		for _, step in steps do
			if not step.ok then
				Run.out(`--- {step.name}: {step.cmd}\n{step.tail}`)
				table.insert(tails, step.tail or "")
			end
		end
		-- a failure (never a usage error or a missing tool) shows the lessons that match its words
		-- (kit/lib/failhints.luau, set by kit/init.luau); a hint that breaks never breaks the report
		if Run.onFail and code ~= Run.CODES.USAGE and code ~= Run.CODES.TOOLCHAIN then
			pcall(Run.onFail :: any, file, summary, table.concat(tails, "\n"))
		end
	end
	Run.out(`summary: {summary}`)
	Run.out(`next_action: {nextAction}`)
	Run.out(`verdict: .verify/{file}.json`)
	return code
end

-- a program of a heavy GPU environment (the generators, the big vision / diffusion models: kit/gen/README.md; and
-- Blender, whose bakes and renders use the card too)
function Run.heavyGpu(program: string): boolean
	for _, envName in { "trellis2", "omni", "hunyuan3d2", "partcrafter", "diffusers", "blender" } do
		if program == Run.tool(envName) then
			return true
		end
	end
	return false
end

-- A `kit/vision/run.py` step answered by a RUNNING warm vision worker (kit/vision/serve.py: its models loaded once —
-- measured 7.2x faster over 10 calls, pixel-identical output) instead of a fresh python that loads its model again;
-- nil when none runs (or it was stale / went away): the caller runs the step cold, exactly as before.
function Run.warmVision(name: string, program: string, args: { string }, env: { [string]: string }?): Step?
	if args[1] ~= "kit/vision/run.py" or env ~= nil or program ~= Run.tool("python") then
		return nil
	end
	local r = VisionWorker.run({ table.unpack(args, 2) })
	if not r or type(r.output) ~= "string" then
		return nil
	end
	return {
		name = name,
		cmd = `{program} {table.concat(args, " ")} (warm vision worker, {r.seconds} s)`,
		exit = r.exit or 1,
		ok = r.exit == 0,
		tail = tail(r.output .. "\n" .. (if type(r.stderr) == "string" then r.stderr else ""), 20),
		result = lastJson(r.output), -- (stdout's verdict line, as a cold run's)
	}
end

-- Content gates (asset/audio/vfx/ui): the program must exit 0 AND print a JSON line with status "pass".
-- No JSON line means the script crashed — the traceback is in the step tail.
-- What a script REFUSED, when argparse turned its arguments down (exit 2, "<prog>: error: ..." under its usage) -> the
-- error's words, or nil (a real crash). A sub-command's parser names itself with the sub-command ("direct.py board:
-- error: ..."): the 2026-11-19 `ui direct board` with no name was still called a crash.
function Run.refused(exit: number?, said: string?): string?
	if exit ~= 2 then
		return nil
	end
	return string.match(said or "", "[%w_%.%-]+%.py[%w_%- ]*: error: ([^\r\n]+)")
end

function Run.content(name: string, program: string, args: { string }, env: { [string]: string }?): Step
	local step = Run.warmVision(name, program, args, env)
	if not step then
		if Run.heavyGpu(program) then
			-- a generator / a big vision model needs the whole card (12 GB: two big jobs spill into shared memory
			-- and crawl): a running warm vision worker drops its models first, and loads them again on its next call
			VisionWorker.free()
		end
		step = Run.spawn(name, program, args, true, env)
	end
	local verdictOk = step.result ~= nil and step.result.status == "pass"
	if step.exit ~= 127 then
		step.ok = step.ok and verdictOk
	end
	if step.result == nil and step.exit ~= 127 then
		-- a script that refused its ARGUMENTS (argparse: exit 2, "error: ..." under its usage) did not crash: say what
		-- it refused (the 2026-10-26 `ui direct` record called a stray date argument a crash)
		local refused = Run.refused(step.exit, step.tail)
		step.result = if refused
			then {
				summary = `{name}: wrong arguments - {refused}`,
				next_action = `{name}: check the command's arguments (lune run kit help --all)`,
			}
			else {
				next_action = `{name} crashed before its verdict — read the error/traceback above and fix the script`,
			}
	end
	if not Run.expectingFailure and not Run.quietThreads[coroutine.running()] then
		print(
			`[{step.ok and "ok" or "FAIL"}] {name}{step.result and step.result.summary and (": " .. step.result.summary) or ""}`
		)
	end
	return step
end

-- Set by `kit selftest`: fixtures are SUPPOSED to fail there, so per-step [FAIL] lines would mislead.
Run.expectingFailure = false
-- threads whose steps print no [ok] / [FAIL] line (kit selftest --jobs: the lanes run at once, and one lane's
-- expectFail must not silence - or un-silence - another's; weak keys: a finished thread leaves)
Run.quietThreads = setmetatable({}, { __mode = "k" }) :: { [thread]: boolean }

-- A step that STARTS when the chain starts and is joined at its own place in the plan (its result keeps its slot, so
-- the report is in the declared order). For a long step that shares nothing with the steps before it: kit verify's
-- Python lane (~47 min, a GPU queue) used to start only after layout, format, selene, types and the Luau specs
-- (PARALLAX_FINAL_CLOSURE_SPEC A3, 2026-11-22). `Run.background(make)` goes in a Run.chain plan like any step.
-- Its `.start` placed EARLIER in the same plan starts it there instead (no step in the report): kit verify starts the
-- Python lane once the quick lint gates pass and joins it LAST, so the content gates run beside it (the owner,
-- 2026-11-23: "speed it up with more cores"). A chain that stops at a failure first WAITS for every lane it started:
-- one left running would share its folders with the next run (two photoscans in one work folder).
function Run.background(make: () -> Step): any
	local lane = { background = true, make = make, started = false, done = false, joined = false, step = nil }
	lane.start = { startLane = lane }
	return lane
end

local function startLane(lane: any)
	if lane.started then
		return
	end
	lane.started = true
	task.spawn(function()
		local t0 = os.clock()
		local okMake, made = pcall(lane.make)
		local step: Step = if okMake
			then made
			else Run.step("(a background step that crashed)", false, tostring(made), { summary = tostring(made) })
		if step.seconds == nil then
			step.seconds = os.clock() - t0
		end
		lane.step = step
		lane.done = true
	end)
end

local function joinLane(lane: any): Step
	startLane(lane)
	while not lane.done do
		task.wait(0.25)
	end
	lane.joined = true
	return lane.step :: Step
end

-- `makes` run up to `jobs` at a time from the moment this is called (a step whose `kindOf(i)` names a kind in `slots`
-- also takes one of that kind's slots: Blender 4, ...), and the steps handed back - in the SAME order - each wait for
-- their own result: a Run.chain over them reports exactly what a serial chain does, in the same order. For steps that
-- share nothing but the machine (kit anim's base sources, each writing its own clip: PARALLAX_FINAL_CLOSURE_SPEC A5).
function Run.parallel(
	makes: { () -> Step },
	jobs: number,
	kindOf: ((number) -> string?)?,
	slots: { [string]: number }?,
	lazy: boolean?
): { () -> Step }
	-- (lazy: the batch starts when a chain REACHES its first step - after every step before it, as serially)
	local results: { [number]: Step } = {}
	local queue: { number } = {}
	for i = 1, #makes do
		table.insert(queue, i)
	end
	local free: { [string]: number } = table.clone(slots or {})
	local function take(): number?
		for qi, i in queue do
			local kind = if kindOf then kindOf(i) else nil
			if kind == nil or free[kind] == nil or free[kind] > 0 then
				table.remove(queue, qi)
				if kind ~= nil and free[kind] ~= nil then
					free[kind] -= 1
				end
				return i
			end
		end
		return nil
	end
	local started = false
	local function start()
		if started then
			return
		end
		started = true
		for _ = 1, math.max(1, math.min(jobs, #makes)) do
			task.spawn(function()
				while #queue > 0 do
					local i = take()
					if i == nil then
						task.wait(0.05) -- (every free worker waits for a slot of the kind left)
						continue
					end
					local ok, step = pcall(makes[i])
					results[i] = if ok
						then step
						else Run.step("(a step that crashed)", false, tostring(step), { summary = tostring(step) })
					local kind = if kindOf then kindOf(i) else nil
					if kind ~= nil and free[kind] ~= nil then
						free[kind] += 1
					end
				end
			end)
		end
	end
	if not lazy then
		start()
	end
	local out: { () -> Step } = {}
	for i = 1, #makes do
		out[i] = function(): Step
			start()
			while results[i] == nil do
				task.wait(0.05)
			end
			return results[i]
		end
	end
	return out
end

-- Run steps in order, stop at the first failure. `codeFor` maps a failing step to its exit code.
-- A failing step's JSON result may carry its own next_action; it wins over the generic hint.
-- `opts.continue` (kit verify --continue, owner 2026-11-20): a failed step does not stop the chain - every step runs
-- and the report names EVERY failure (the first one's code and fix lead); without it the first failure stops it.
function Run.chain(
	file: string,
	plan: { () -> Step },
	codeFor: (Step) -> number,
	passSummary: string,
	opts: { continue: boolean? }?
): number
	local steps: { Step } = {}
	local keepGoing = opts ~= nil and opts.continue == true
	local failures: { { step: Step, code: number, hint: string } } = {}
	local chainStarted = os.clock()
	-- the background steps (Run.background) start now - or at their `.start` further down the plan - and each is
	-- joined where it stands in the plan
	local lanes: { any } = {}
	local placed: { [any]: boolean } = {}
	for _, entry in plan :: { any } do
		if type(entry) == "table" and entry.startLane ~= nil then
			placed[entry.startLane] = true
		end
	end
	for _, entry in plan :: { any } do
		if type(entry) == "table" and entry.background == true then
			table.insert(lanes, entry)
			if not placed[entry] then
				startLane(entry)
			end
		end
	end
	-- each step's time on the report, and the slowest named on one line before the summary
	local function timeLine()
		local timed = {}
		for _, s in steps do
			if type(s.seconds) == "number" and s.seconds >= 1 then
				table.insert(timed, s)
			end
		end
		table.sort(timed, function(a, b)
			return (a.seconds :: number) > (b.seconds :: number)
		end)
		local top = {}
		for i = 1, math.min(5, #timed) do
			table.insert(top, `{timed[i].name} {Run.clock(timed[i].seconds :: number)}`)
		end
		Run.out(
			`time: {Run.clock(os.clock() - chainStarted)}{if #top > 0
				then " - slowest: " .. table.concat(top, ", ")
				else ""}`
		)
	end
	for _, entry in plan :: { any } do
		if type(entry) == "table" and entry.startLane ~= nil then
			startLane(entry.startLane)
			continue
		end
		local make: () -> Step = entry
		if type(entry) == "table" and entry.background == true then
			make = function(): Step
				return joinLane(entry)
			end
		end
		local t0 = os.clock()
		local step: Step
		if keepGoing then -- (a step that crashes is one more red; the rest still run)
			local okMake, made = pcall(make)
			step = if okMake
				then made
				else Run.step("(a step that crashed)", false, tostring(made), { summary = tostring(made) })
		else
			step = make()
		end
		if step.seconds == nil then
			step.seconds = os.clock() - t0
		end
		table.insert(steps, step)
		if not step.ok then
			local code = step.exit == 127 and Run.CODES.TOOLCHAIN or codeFor(step)
			local hint = step.result and step.result.next_action
			-- a tool without a JSON verdict often still prints its fix ("... — run: wally install"): surface it
			local printed = type(step.tail) == "string" and string.match(step.tail, "run: ([^\n]+)")
			if not hint and printed then
				hint = "run: " .. printed
			end
			hint = hint or `fix the {step.name} output above, then re-run the same kit command`
			if not keepGoing then
				-- a lane still running is waited for, never left running beside the next run - and its result is in
				-- this report too (one red it found is one fewer run to find it)
				for _, lane in lanes do
					if lane.started and not lane.joined then
						if not lane.done then
							Run.out(`(waiting for a step running beside the chain to finish before the report)`)
						end
						table.insert(steps, joinLane(lane))
					end
				end
				timeLine()
				return Run.report(file, steps, code, `{file}: {step.name} failed`, hint)
			end
			table.insert(failures, { step = step, code = code, hint = hint })
		end
	end
	timeLine()
	if #failures > 0 then
		local names, hints = {}, {}
		for _, f in failures do
			table.insert(names, f.step.name)
			table.insert(hints, `[{f.step.name}] {f.hint}`)
		end
		Run.out(`--- {#failures} failed step(s) (--continue: every step was run):`)
		for _, h in hints do
			Run.out(`  {h}`)
		end
		return Run.report(
			file,
			steps,
			failures[1].code,
			`{file}: {#failures} step(s) failed: {table.concat(names, ", ")}`,
			table.concat(hints, "   |   ")
		)
	end
	-- a passing step can still point at the next improvement (design warnings, "look at the sheet"): surface it
	-- "improve ..." from any step; "look at ..." only from the last step (the command's own product)
	local nextAction = "none — proceed"
	for i, step in steps do
		local hint = step.result and step.result.next_action
		if
			type(hint) == "string"
			and (string.find(hint, "^improve") or (i == #steps and string.find(hint, "^look at")))
		then
			nextAction = `[{step.name}] {hint}`
			break
		end
	end
	local only = #steps == 1 and steps[1].result and steps[1].result.summary
	return Run.report(
		file,
		steps,
		Run.CODES.PASS,
		if type(only) == "string" then `{passSummary} — {only}` else passSummary,
		nextAction
	)
end

-- An in-process step (no subprocess): for checks the kit runs itself in Luau.
function Run.step(name: string, ok: boolean, detail: string, result: any?): Step
	if not Run.expectingFailure and not Run.quietThreads[coroutine.running()] then
		local summary = result and result.summary
		print(`[{ok and "ok" or "FAIL"}] {name}{summary and (": " .. summary) or ""}`)
	end
	return { name = name, cmd = "(in-process)", exit = ok and 0 or 1, ok = ok, tail = detail, result = result }
end

return Run

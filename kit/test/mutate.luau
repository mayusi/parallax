-- mutate.luau — MUTATION TESTING: do the specs actually catch bugs? (the owner: "gates are not quality" — a green
-- spec count says nothing about whether the specs would notice a real mistake).
-- Usage: lune run kit/test/mutate [<src/shared/Module.luau> ...] [--max 80]   (normally: lune run kit mutate [Name])
--        lune run kit/test/mutate --regressions [<file.json>]   (the recorded bugs; default tests/regressions.json)
-- For each module: plants ONE small bug at a time (< <-> <=, > <-> >=, == <-> ~=, and <-> or, drops a `not`,
-- true <-> false, a number n -> n + 1) in a COPY of the project (build/mutate/w: src/shared + tests + the frktest
-- harness; the real files are never touched), runs the project specs there, and counts a mutant KILLED when a spec
-- fails. Survivors are bugs nobody would notice: each one names the line and the change — write the spec case
-- that would catch it. Prints one JSON line: {status, summary, next_action, score, modules:[{module, killed,
-- total, survivors}]}. status fails only when the specs do not pass on the unmutated copy.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Audit = require("../lib/audit")

local WORK = "build/mutate/w"
-- a game's own folders when one is active ("games/<Name>/"; the kit passes it), else the project's
local GR = process.env.KIT_GAME_ROOT or ""

local function copyDir(from: string, to: string)
	fs.writeDir(to)
	for _, name in fs.readDir(from) do
		local a, b = from .. "/" .. name, to .. "/" .. name
		if fs.isDir(a) then
			copyDir(a, b)
		else
			fs.writeFile(b, fs.readFile(a))
		end
	end
end

local RUNNER = [[
local fs = require("@lune/fs")
local process = require("@lune/process")
local frk = require("./kit/test/frk")
local function collect(dir, out)
	if not fs.isDir(dir) then return end
	local names = fs.readDir(dir)
	table.sort(names)
	for _, n in names do
		local p = dir .. "/" .. n
		if fs.isDir(p) then collect(p, out) elseif string.sub(n, -10) == ".spec.luau" then table.insert(out, p) end
	end
end
local specs = {}
collect("tests", specs)
collect("kit/test/spec", specs) -- (only the kit specs a recorded case names are copied here)
for _, p in specs do (require :: any)("./" .. string.sub(p, 1, -6))() end
process.exit(if frk.frktest.run() then 0 else 1)
]]

local function setup()
	if fs.isDir(WORK) then
		fs.removeDir(WORK)
	end
	fs.writeDir(WORK)
	fs.writeFile(WORK .. "/.luaurc", fs.readFile(".luaurc"))
	copyDir("DevPackages", WORK .. "/DevPackages")
	copyDir(GR .. "src/shared", WORK .. "/src/shared")
	if fs.isDir("src/kit") then -- shared modules require ../kit/<Module>
		copyDir("src/kit", WORK .. "/src/kit")
	end
	if fs.isDir(GR .. "tests") then
		copyDir(GR .. "tests", WORK .. "/tests")
	end
	fs.writeDir(WORK .. "/kit/test")
	fs.writeFile(WORK .. "/kit/test/frk.luau", fs.readFile("kit/test/frk.luau"))
	fs.writeFile(WORK .. "/run.luau", RUNNER)
end

local function runSpecs(): boolean
	local r = process.exec("lune", { "run", "run.luau" }, { cwd = WORK })
	return r.ok
end

-- positions in CODE (not strings / comments) where a mutation applies
type Mutant = { pos: number, len: number, to: string, label: string }
local OPS: { { pat: string, to: string } } = {
	{ pat = "<=", to = "<" },
	{ pat = ">=", to = ">" },
	{ pat = "==", to = "~=" },
	{ pat = "~=", to = "==" },
}
local function mutants(src: string): { Mutant }
	local code = Audit.strip(src)
	local out: { Mutant } = {}
	local i = 1
	while i <= #code do
		local two = string.sub(code, i, i + 1)
		local one = string.sub(code, i, i)
		local done = false
		for _, op in OPS do
			if two == op.pat then
				table.insert(out, { pos = i, len = 2, to = op.to, label = `{op.pat} -> {op.to}` })
				i += 2
				done = true
				break
			end
		end
		if not done then
			local prev = if i > 1 then string.sub(code, i - 1, i - 1) else " "
			local nxt = string.sub(code, i + 1, i + 1)
			if (one == "<" or one == ">") and nxt ~= "=" and prev ~= "<" and prev ~= ">" and nxt ~= one then
				table.insert(out, { pos = i, len = 1, to = one .. "=", label = `{one} -> {one}=` })
			else
				local word = string.match(code, "^[%a_][%w_]*", i)
				if word and not string.match(prev, "[%w_%.:]") then
					if word == "and" then
						table.insert(out, { pos = i, len = 3, to = "or", label = "and -> or" })
					elseif word == "or" then
						table.insert(out, { pos = i, len = 2, to = "and", label = "or -> and" })
					elseif word == "not" then
						table.insert(out, { pos = i, len = 4, to = "", label = "drop `not`" })
					elseif word == "true" then
						table.insert(out, { pos = i, len = 4, to = "false", label = "true -> false" })
					elseif word == "false" then
						table.insert(out, { pos = i, len = 5, to = "true", label = "false -> true" })
					end
					i += #word
					continue
				end
				local num = string.match(code, "^%d+%.?%d*", i)
				if num and not string.match(prev, "[%w_%.]") then
					local n = tonumber(num)
					if n then
						table.insert(out, { pos = i, len = #num, to = tostring(n + 1), label = `{num} -> {n + 1}` })
					end
					i += #num
					continue
				end
			end
			i += 1
		end
	end
	return out
end

local function lineOf(src: string, pos: number): number
	local _, n = string.gsub(string.sub(src, 1, pos), "\n", "")
	return n + 1
end

-- A module that is only DATA (local T = {}, T.NAME = <a literal>, return T): its "mutants" are tuning changes, not bugs
-- a spec could catch without pinning every value (StrikeConfig: 0/12 - each a number + 1). Reported as skipped, with
-- that reason, and kept out of the score (PARALLAX_FINAL_CLOSURE_SPEC Step 13 (a)); a module with any logic is mutated.
local function dataOnly(src: string): boolean
	local code = Audit.strip(src)
	local name: string? = nil
	local lines = 0
	for raw in string.gmatch(code, "[^\n]+") do
		local line = string.gsub(string.gsub(raw, "^%s+", ""), "%s+$", "")
		if line ~= "" then
			lines += 1
			local decl = string.match(line, "^local%s+([%a_][%w_]*)%s*=%s*{%s*}$")
			if decl and name == nil then
				name = decl
			elseif name and string.match(line, "^" .. name .. "%.[%a_][%w_]*%s*=%s*(.+)$") then
				local rhs = string.match(line, "=%s*(.+)$") :: string
				-- a literal: a number, a (stripped) string, true / false / nil - no operator, call or name
				if
					not (
						string.match(rhs, "^%-?%d+%.?%d*$")
						or string.match(rhs, '^"%s*"$')
						or string.match(rhs, "^'%s*'$")
						or rhs == "true"
						or rhs == "false"
						or rhs == "nil"
					)
				then
					return false
				end
			elseif not (name and string.match(line, "^return%s+" .. name .. "$")) then
				return false -- (returning the table is the module's end; anything else is logic)
			end
		end
	end
	return name ~= nil and lines > 1
end

-- the kit specs that test a pure kit rules module (src/kit/<X>Rules.luau): the ones that require it and nothing but frk
-- and src/kit (they run in the copy as they run here)
local function kitSpecsOf(module: string): { string }
	local out = {}
	local dir = "kit/test/spec"
	if not fs.isDir(dir) then
		return out
	end
	for _, f in fs.readDir(dir) do
		if string.sub(f, -10) == ".spec.luau" then
			local text = fs.readFile(dir .. "/" .. f)
			if string.find(text, `src/kit/{module}"`, 1, true) then
				local ok = true
				for req in string.gmatch(text, 'require%("([^"]+)"%)') do
					if
						req ~= "../frk"
						and not string.match(req, "^%.%./%.%./%.%./src/kit/")
						and string.sub(req, 1, 1) ~= "@"
					then
						ok = false
					end
				end
				if ok then
					table.insert(out, f)
				end
			end
		end
	end
	table.sort(out)
	return out
end

-- ---------------------------------------------------------------- main
local targets, maxPer = {}, 80
local regressions: string? = nil
local args = process.args
local k = 1
while k <= #args do
	if args[k] == "--max" then
		maxPer = tonumber(args[k + 1]) or maxPer
		k += 2
	elseif args[k] == "--rules" then
		-- the kit's pure rules modules too (src/kit/*Rules.luau, tested by kit/test/spec)
		for _, f in fs.readDir("src/kit") do
			if string.match(f, "Rules%.luau$") then
				table.insert(targets, "src/kit/" .. f)
			end
		end
		k += 1
	elseif args[k] == "--regressions" then
		-- an optional file after the flag; default: the project's tests/regressions.json
		local nxt = args[k + 1]
		if nxt and string.sub(nxt, -5) == ".json" then
			regressions = nxt
			k += 2
		else
			regressions = GR .. "tests/regressions.json"
			k += 1
		end
	else
		table.insert(targets, args[k])
		k += 1
	end
end
local hasShared = false
for _, t in targets do
	if string.find(t, "src/shared/", 1, true) then
		hasShared = true
	end
end
if (#targets == 0 or (not hasShared and process.args[1] == "--rules")) and fs.isDir(GR .. "src/shared") then
	for _, f in fs.readDir(GR .. "src/shared") do
		if string.sub(f, -5) == ".luau" then
			table.insert(targets, GR .. "src/shared/" .. f)
		end
	end
	table.sort(targets)
end

setup()
local copiedSpecs = 0
for _, t in targets do
	local rules = string.match(string.gsub(t, "\\", "/"), "^src/kit/([%w_]+Rules)%.luau$")
	if rules then
		fs.writeDir(WORK .. "/kit/test/spec")
		for _, f in kitSpecsOf(rules) do
			if not fs.isFile(WORK .. "/kit/test/spec/" .. f) then
				local text = fs.readFile("kit/test/spec/" .. f)
				fs.writeFile(WORK .. "/kit/test/spec/" .. f, text)
				copiedSpecs += 1
				-- the project data the spec reads by path (foley.spec: assets/sounds/sets/footsteps.json; vfxsequence.spec:
				-- assets/effects/sequences): copied as it is, so the copy's specs pass unmutated as they pass here
				for data in string.gmatch(text, '"(assets/[%w_%-%./]+)"') do
					local to = WORK .. "/" .. data
					local parent = string.match(to, "^(.*)/[^/]+$")
					if parent and not fs.isDir(parent) then
						fs.writeDir(parent)
					end
					if fs.isFile(data) and not fs.isFile(to) then
						fs.writeFile(to, fs.readFile(data))
					elseif fs.isDir(data) and not fs.isDir(to) then
						copyDir(data, to)
					end
				end
			end
		end
	end
end
if not runSpecs() then
	print(serde.encode("json", {
		status = "fail",
		summary = "the project specs fail on the UNMUTATED copy — mutation testing needs a green baseline",
		next_action = "run: lune run kit test project, fix the failing spec, then re-run",
	}))
	process.exit(1)
end

-- the REGRESSION CORPUS (mission 06 5.7): every bug a run once found is replanted exactly; the specs must kill
-- each one, forever. A case: {id, found_by, spec, module, line, from, to} — `line` is a unique piece of the line,
-- `from` -> `to` the planted change in it. A case whose line moved or vanished is STALE (fix the case, not the code).
if regressions then
	local file = regressions :: string
	local cases = if fs.isFile(file) then serde.decode("json", fs.readFile(file)) else nil
	if type(cases) ~= "table" or type(cases.cases) ~= "table" or #cases.cases == 0 then
		print(serde.encode("json", {
			status = "fail",
			summary = `no regression corpus at {file}`,
			next_action = `write {file}: {"{"}"cases": [{"{"}id, found_by, spec, module, line, from, to{"}"}]{"}"} — one per bug a fuzz / mutate / playtest run found`,
		}))
		process.exit(1)
	end
	-- a case on a KIT module is proven by the kit's own spec (kit/test/spec/<x>.spec.luau): that file is copied into the
	-- sandbox beside the project's tests/ (it requires ../frk and ../../../src/kit/<Module>, both there). Before
	-- 2026-11-19 only tests/ ran, so no bug in a src/kit module could be recorded (LIMITATIONS_FIXES_V4 Phase 0: "seed
	-- tests/regressions.json"). The sandbox must be GREEN with nothing planted, or every bug would read as caught.
	for _, c in cases.cases do
		local spec = tostring(c.spec)
		if string.sub(spec, 1, 14) == "kit/test/spec/" and fs.isFile(spec) then
			fs.writeDir(WORK .. "/kit/test/spec")
			fs.writeFile(WORK .. "/" .. spec, fs.readFile(spec))
		end
	end
	if not runSpecs() then
		print(serde.encode("json", {
			status = "fail",
			summary = "regressions: the specs fail in the sandbox with NO bug planted - a kill would prove nothing",
			next_action = "run the named specs on their own (lune run kit test); a kit spec that needs more than ../frk "
				.. "and src/kit cannot prove a case here",
		}))
		process.exit(1)
	end
	local results, survived, stale = {}, {}, {}
	for _, c in cases.cases do
		local id = tostring(c.id)
		local full = GR .. tostring(c.module)
		local bad: string? = nil
		if type(c.line) ~= "string" or type(c.from) ~= "string" or type(c.to) ~= "string" then
			bad = "the case needs line, from and to (strings)"
		elseif not fs.isFile(full) then
			bad = `no module {c.module}`
		elseif type(c.spec) ~= "string" or not fs.isFile(GR .. c.spec) then
			bad = `no spec file {c.spec}`
		end
		local src = if bad then "" else fs.readFile(full)
		local mutated: string? = nil
		if not bad then
			local lines = string.split(src, "\n")
			local hit: number? = nil
			for n, text in lines do
				if string.find(text, c.line, 1, true) then
					if hit then
						bad = `"{c.line}" is on more than one line of {c.module}`
						break
					end
					hit = n
				end
			end
			if not bad and not hit then
				bad = `"{c.line}" is no longer in {c.module}`
			elseif not bad then
				local text = lines[hit :: number]
				local a, b = string.find(text, c.from, 1, true)
				if not a then
					bad = `"{c.from}" is not on the line "{c.line}"`
				else
					lines[hit :: number] = string.sub(text, 1, a - 1) .. c.to .. string.sub(text, (b :: number) + 1)
					mutated = table.concat(lines, "\n")
				end
			end
		end
		if bad then
			table.insert(stale, { id = id, problem = bad })
			print(`  STALE {id}: {bad}`)
			continue
		end
		local rel = string.gsub(full, "\\", "/")
		rel = if GR ~= "" and string.sub(rel, 1, #GR) == GR then string.sub(rel, #GR + 1) else rel
		local copy = WORK .. "/" .. rel
		fs.writeFile(copy, mutated :: string)
		local killed = not runSpecs()
		fs.writeFile(copy, src)
		table.insert(results, { id = id, killed = killed })
		if killed then
			print(`  KILLED {id} ({c.module}: {c.from} -> {c.to})`)
		else
			table.insert(survived, id)
			print(
				`  SURVIVED {id} ({c.module}: {c.from} -> {c.to}) — the bug {c.found_by or "a run"} found is back unnoticed`
			)
		end
	end
	local ok = #survived == 0 and #stale == 0
	print(serde.encode("json", {
		status = if ok then "pass" else "fail",
		summary = `regressions: {#results - #survived}/{#results} recorded bugs killed by the specs`
			.. (if #stale > 0 then `, {#stale} stale case(s)` else ""),
		next_action = if #survived > 0
			then `restore the spec that kills regression {survived[1]} (see tests/REGRESSIONS.md) — never delete the case`
			elseif #stale > 0 then `update the stale case {stale[1].id}: {stale[1].problem}`
			else "none — proceed",
		cases = results,
		stale = stale,
	}))
	process.exit(if ok then 0 else 1)
end

local report, killedAll, totalAll = {}, 0, 0
for _, path in targets do
	local full = string.gsub(path, "\\", "/")
	local rel = if GR ~= "" and string.sub(full, 1, #GR) == GR then string.sub(full, #GR + 1) else full
	local isRules = string.match(rel, "^src/kit/[%w_]+Rules%.luau$") ~= nil
	if (string.sub(rel, 1, 11) ~= "src/shared/" and not isRules) or not fs.isFile(full) then
		table.insert(report, {
			module = rel,
			error = "only pure src/shared modules and src/kit/*Rules.luau can be mutation-tested",
		})
		continue
	end
	local src = fs.readFile(full)
	if dataOnly(src) then
		table.insert(report, {
			module = rel,
			skipped = "pure data (constant assignments only): a value's change is tuning, not a bug a spec catches",
		})
		print(`  {rel}: skipped - pure data (no logic to mutate)`)
		continue
	end
	if isRules and #kitSpecsOf(string.match(rel, "([%w_]+)%.luau$") :: string) == 0 then
		table.insert(report, { module = rel, error = "no kit spec tests it on its own (frk + src/kit only)" })
		continue
	end
	local list = mutants(src)
	-- spread the budget over the file when there are more mutants than --max
	local chosen = {}
	local stride = math.max(1, #list / maxPer)
	local at = 1
	while at <= #list and #chosen < maxPer do
		table.insert(chosen, list[math.floor(at)])
		at += stride
	end
	local copy = WORK .. "/" .. rel
	local killed, survivors = 0, {}
	for _, m in chosen do
		local mutated = string.sub(src, 1, m.pos - 1) .. m.to .. string.sub(src, m.pos + m.len)
		fs.writeFile(copy, mutated)
		if runSpecs() then
			local line = lineOf(src, m.pos)
			local text = string.gsub(string.split(src, "\n")[line] or "", "^%s+", "")
			table.insert(survivors, { line = line, change = m.label, code = string.sub(text, 1, 100) })
		else
			killed += 1
		end
	end
	fs.writeFile(copy, src)
	killedAll += killed
	totalAll += #chosen
	table.insert(report, { module = rel, killed = killed, total = #chosen, survivors = survivors })
	print(`  {rel}: {killed}/{#chosen} mutants killed`)
	for _, s in survivors do
		print(`    SURVIVED line {s.line} ({s.change}): {s.code}`)
	end
end

local score = if totalAll > 0 then killedAll / totalAll else 1
local first = nil
for _, r in report do
	if r.survivors and #r.survivors > 0 then
		first = r
		break
	end
end
print(serde.encode("json", {
	status = "pass",
	summary = `{killedAll}/{totalAll} planted bugs caught by the specs ({math.floor(score * 100)} %)`,
	next_action = if first
		then `improve: write a spec case that catches {first.module} line {first.survivors[1].line} ({first.survivors[1].change}): {first.survivors[1].code}`
		else "none — proceed",
	score = score,
	modules = report,
}))

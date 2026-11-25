-- run.luau — headless test runner: kit specs (kit/test/spec) + project specs (kit.config.json paths.tests, default
-- tests/), every **/*.spec.luau. Each spec returns `function()` registering frktest suites.
-- Exit 1 on any failure, 5 if frktest is missing (run: wally install). Usually run via: lune run kit test
--
-- EVERY SPEC FILE IN ITS OWN PROCESS, SEVERAL AT ONCE (the owner, 2026-11-23: "speed it up with more cores"): the
-- specs ran in ONE lune process on one core - ~38 min of a 2026-11-23 kit verify. Now `--jobs` workers (default:
-- cores - 2, at most 12; PARALLAX_SPEC_JOBS) each run one spec file at a time in its own process, longest first
-- (each file's last time is kept in .verify/spec_timings.json; an unknown file counts 10 s). A file that fails beside
-- the others is run AGAIN, ALONE, after the pool, and only that run counts (as the Python lane: kit/test/python/run.py),
-- so every failure this prints has been seen on its own.
--   lune run kit/test/run [kit|project] [--jobs N]   (--jobs 1: every spec in this one process, as before)
--   lune run kit/test/run --spec <path>              one spec file (what each worker runs)
local fs = require("@lune/fs")
local process = require("@lune/process")

local Config = require("../lib/config")

if not fs.isDir("DevPackages/_Index") then
	print("[tests] frktest missing — run: wally install")
	process.exit(5)
end

local function collect(dir: string, out: { string })
	if not fs.isDir(dir) then
		return
	end
	local names = fs.readDir(dir)
	table.sort(names)
	for _, name in names do
		local path = dir .. "/" .. name
		if fs.isDir(path) then
			collect(path, out)
		elseif string.sub(name, -10) == ".spec.luau" then
			table.insert(out, path)
		end
	end
end

local only: string? = nil -- "kit" | "project" | nil (both)
local one: string? = nil
local jobs: number? = nil
do
	local args = process.args
	local i = 1
	while i <= #args do
		local a = args[i]
		if a == "--spec" then
			one = args[i + 1]
			i += 1
		elseif a == "--jobs" then
			jobs = tonumber(args[i + 1])
			i += 1
		elseif only == nil then
			only = a
		end
		i += 1
	end
end

-- every spec of `specs` in THIS process, under frktest (a worker's one file, or --jobs 1)
local function runHere(specs: { string })
	local frk = require("./frk")
	local reporter =
		require("../../DevPackages/_Index/itsfrank_frktest@0.0.2/frktest/src/reporters/lune_console_reporter")
	for _, path in specs do
		-- paths are project-root relative; require is relative to this file (kit/test/)
		local register = (require :: any)("../../" .. string.sub(path, 1, -6))
		register()
	end
	print(`[tests] {#specs} spec file(s)`)
	reporter.init()
	if not frk.frktest.run() then
		process.exit(1)
	end
end

if one then
	runHere({ one })
	return
end

local specs = {}
if only ~= "project" then
	collect("kit/test/spec", specs)
end
if only ~= "kit" then
	collect(Config.path("tests"), specs)
end

if jobs == nil then
	jobs = tonumber(process.env.PARALLAX_SPEC_JOBS or "")
end
if jobs == nil then
	local cores = tonumber(process.env.NUMBER_OF_PROCESSORS or "") or 4
	jobs = math.clamp(cores - 2, 1, 12)
end
local workers = math.max(1, math.floor(jobs :: number))
if workers == 1 or #specs <= 1 then
	runHere(specs)
	return
end

local serde = require("@lune/serde")
local task = require("@lune/task")

local TIMINGS = ".verify/spec_timings.json"
local timings: { [string]: number } = {}
if fs.isFile(TIMINGS) then
	local ok, t = pcall(serde.decode, "json" :: any, fs.readFile(TIMINGS))
	if ok and type(t) == "table" then
		timings = t
	end
end

local function clock(seconds: number): string
	local s = math.floor(seconds + 0.5)
	return if s >= 60 then `{s // 60}m {s % 60}s` else `{s}s`
end

type Result = { ok: boolean, seconds: number, ran: number, passed: number, failed: number, out: string }

-- one spec file in its own lune process (its environment inherited: KIT_GAME, PYTHONHASHSEED, ...)
local function runOne(path: string): Result
	local t0 = os.clock()
	local okExec, r = pcall(process.exec, process.env.LUNE or "lune", { "run", "kit/test/run", "--spec", path })
	local seconds = os.clock() - t0
	if not okExec then
		return { ok = false, seconds = seconds, ran = 0, passed = 0, failed = 0, out = `spawn failed: {r}` }
	end
	-- (the console reporter colours its words: the counts are read with the colours taken out)
	local out = string.gsub((r.stdout or "") .. "\n" .. (r.stderr or ""), "\27%[[%d;]*m", "")
	local ran = tonumber(string.match(out, "Tests Ran: (%d+)")) or 0
	local passed = tonumber(string.match(out, "Passed: (%d+)")) or 0
	local failed = tonumber(string.match(out, "Failed: (%d+)")) or 0
	-- a pass is exit 0 AND a summary line: a file that died before frktest ran (a require error) is a failure
	local ok = r.ok and r.code == 0 and string.find(out, "Tests Ran:", 1, true) ~= nil
	return { ok = ok, seconds = seconds, ran = ran, passed = passed, failed = failed, out = out }
end

-- longest first (the report stays in name order)
local order = table.clone(specs)
table.sort(order, function(a, b)
	local ta, tb = timings[a] or 10, timings[b] or 10
	if ta ~= tb then
		return ta > tb
	end
	return a < b
end)

local started = os.clock()
local results: { [string]: Result } = {}
local done = 0
local nextIndex = 1
for _ = 1, math.min(workers, #order) do
	task.spawn(function()
		while nextIndex <= #order do
			local path = order[nextIndex]
			nextIndex += 1
			results[path] = runOne(path)
			done += 1
		end
	end)
end
while done < #order do
	task.wait(0.1)
end

-- the lone runs: a file that failed beside the others, again on its own, and only that run counts
local collided = {}
for _, path in specs do
	if not results[path].ok then
		local alone = runOne(path)
		if alone.ok then
			table.insert(collided, path)
		end
		results[path] = alone
	end
end
local wall = os.clock() - started

local ran, passed, failed, serial = 0, 0, 0, 0
local broken = {}
for _, path in specs do
	local r = results[path]
	ran += r.ran
	passed += r.passed
	failed += r.failed
	serial += r.seconds
	if not r.ok then
		table.insert(broken, path)
		local lines = string.split(r.out, "\n")
		local from = math.max(1, #lines - 120)
		print(`--- {path} ({clock(r.seconds)}):`)
		print(table.concat({ table.unpack(lines, from, #lines) }, "\n"))
	end
end

-- each file's time for the next run's order (a full run only: a filtered one keeps the rest)
for _, path in specs do
	timings[path] = math.floor(results[path].seconds * 10 + 0.5) / 10
end
pcall(function()
	if not fs.isDir(".verify") then
		fs.writeDir(".verify")
	end
	fs.writeFile(TIMINGS, serde.encode("json", timings, true))
end)

local slow = table.clone(specs)
table.sort(slow, function(a, b)
	return results[a].seconds > results[b].seconds
end)
local top = {}
for i = 1, math.min(5, #slow) do
	local name = string.match(slow[i], "([^/]+)%.spec%.luau$") or slow[i]
	table.insert(top, `{name} {clock(results[slow[i]].seconds)}`)
end
print(
	`[tests] {#specs} spec file(s), {math.min(workers, #specs)} at a time: {ran} test(s), {passed} passed, {failed} failed, {#broken} file(s) red - {clock(
		wall
	)} (one after another: {clock(serial)})`
)
print(`[tests] slowest: {table.concat(top, ", ")}`)
if #collided > 0 then
	print(`[tests] failed beside the others, passed alone (a collision, not a failure): {table.concat(collided, ", ")}`)
end
if #broken > 0 then
	print(`[tests] red: {table.concat(broken, ", ")}`)
	process.exit(1)
end

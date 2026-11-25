-- selftestcache.luau — `kit selftest`'s fast paths (owner 2026-11-20: "--lane <dept> / --changed + a content-hash cache
-- (.verify/selftest_cache.json, busted on kit/lib/ changes, with --no-cache for cold proofs) so untouched fixtures
-- don't cold-boot Blender repeatedly").
--   * every case is labelled by the helper that made it (kit/cmd/qa.luau); its label's first word names its lane
--     ("3d ...", "blender ...", "vfx ...", "anim ...", "world ...", "ui ...", "sfx ..." / "audio ..."), any other
--     word is the "kit" lane. A case with no label (the specs run) always runs.
--   * --lane 3d,vfx runs only those lanes' cases; --changed runs only the lanes the working tree changed against HEAD
--     (kit/scripts/selftest_inputs.py --changed: a change to a common file is every lane).
--   * THE CACHE: a case that passed is recorded with its lane's input key (kit/scripts/selftest_inputs.py: the
--     content of the common kit files + the lane's own folders + the lanes it reads); a later run with the same key
--     reuses it and says so ([cached]). A failed case is never reused. On by default in a primary checkout; OFF in a
--     linked worktree (kit prove's sandbox is one: its proof stays cold) and with --no-cache; --cache forces it on.
--     Every run, cached or cold, records what passed.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")
local task = require("@lune/task")

local Run = require("./run")

local Cache = {}
Cache.FILE = ".verify/selftest_cache.json"

local LANE = {
	["3d"] = "3d",
	blender = "3d",
	texture = "3d",
	refs = "3d",
	vfx = "vfx",
	anim = "anim",
	world = "world",
	ui = "ui",
	sfx = "sfx",
	audio = "sfx",
	-- PROMPT-X's cases ("prompt-x ...": the label's first word) - kit/prompt, kit/selftest/prompt
	prompt = "prompt",
	kit = "kit",
}
Cache.LANES = { "3d", "vfx", "anim", "world", "ui", "sfx", "prompt", "kit" }

function Cache.laneOf(label: string): string
	local first = string.lower(string.match(label, "^%s*([%w]+)") or "")
	return LANE[first] or "kit"
end

-- the flags -> { lanes = set or nil, cache = bool, bad = message or nil }
function Cache.options(
	args: { string }?,
	primary: boolean
): { lanes: { [string]: boolean }?, cache: boolean, bad: string?, changed: boolean, jobs: number }
	local envJobs = tonumber(process.env.PARALLAX_SELFTEST_JOBS or "")
	local opts = {
		lanes = nil :: { [string]: boolean }?,
		cache = primary,
		bad = nil :: string?,
		changed = false,
		-- (8 lanes at once by default: validated 2026-11-22 - a cold --jobs 8 run gave all 564 steps the same outcome as
		-- a cold serial run, every caught verdict word for word but its temp folder ids; 1507 s against 2217 s)
		jobs = if envJobs and envJobs >= 1 then math.floor(envJobs) else 8,
	}
	local list = args or {}
	local i = 1
	while i <= #list do
		local a = list[i]
		if a == "--no-cache" then
			opts.cache = false
		elseif a == "--cache" then
			opts.cache = true
		elseif a == "--changed" then
			opts.changed = true
		elseif a == "--jobs" or string.sub(a, 1, 7) == "--jobs=" then
			local value = if a == "--jobs" then list[i + 1] else string.sub(a, 8)
			if a == "--jobs" then
				i += 1
			end
			local n = tonumber(value or "")
			if not n or n < 1 then
				opts.bad = "--jobs needs a number of lanes at once: --jobs 4 (1 = one case at a time)"
			else
				opts.jobs = math.floor(n)
			end
		elseif a == "--lane" or string.sub(a, 1, 7) == "--lane=" then
			local value = if a == "--lane" then list[i + 1] else string.sub(a, 8)
			if a == "--lane" then
				i += 1
			end
			opts.lanes = opts.lanes or {}
			for name in string.gmatch(value or "", "[^,%s]+") do
				local lane = LANE[string.lower(name)]
				if not lane then
					opts.bad = `no such lane "{name}" (lanes: {table.concat(Cache.LANES, ", ")})`
				else
					(opts.lanes :: any)[lane] = true
				end
			end
			if next(opts.lanes :: any) == nil and not opts.bad then
				opts.bad = "--lane needs a lane: --lane 3d (or --lane 3d,vfx)"
			end
		end
		i += 1
	end
	return opts
end

local function python(args: { string }): any
	local s = Run.spawn("selftest inputs", Run.tool("python"), args, true)
	if s.ok and type(s.result) == "table" then
		return s.result
	end
	return nil
end

-- a primary checkout keeps its .git as a folder; a linked worktree (kit prove's sandbox, a session's worktree) as a file
function Cache.primary(): boolean
	return fs.isDir(".git")
end

local function load(): { cases: { [string]: string } }
	if fs.isFile(Cache.FILE) then
		local ok, data = pcall(serde.decode, "json", fs.readFile(Cache.FILE))
		if ok and type(data) == "table" and data.version == 1 and type(data.cases) == "table" then
			return data
		end
	end
	return { version = 1, cases = {}, learned = {} } :: any
end

local function save(data: any)
	if not fs.isDir(".verify") then
		fs.writeDir(".verify")
	end
	fs.writeFile(Cache.FILE, serde.encode("json", data, true))
end

-- the selftest's chain with its fast paths: `plan` as kit/cmd/qa.luau wrote it, `labels` = case -> label
function Cache.chain(
	args: { string }?,
	labels: { [any]: string },
	passSummary: string,
	plan: { () -> Run.Step },
	codeFor: (Run.Step) -> number
): number
	local opts = Cache.options(args, Cache.primary())
	if opts.bad then
		return Run.report("selftest", {}, Run.CODES.USAGE, `selftest: {opts.bad}`, "lune run kit selftest --help")
	end
	if opts.changed then
		local r = python({ "kit/scripts/selftest_inputs.py", "--changed" })
		opts.lanes = opts.lanes or {}
		for _, lane in (r and r.changed) or Cache.LANES do
			(opts.lanes :: any)[lane] = true
		end
		if next(opts.lanes :: any) == nil then
			print("[ok] selftest --changed: the working tree changes no lane's inputs - nothing to run")
			return Run.report(
				"selftest",
				{},
				Run.CODES.PASS,
				"selftest --changed: nothing changed against HEAD (no case run)",
				"none — proceed"
			)
		end
	end
	local inputs = python({ "kit/scripts/selftest_inputs.py" })
	local keys: { [string]: string } = if inputs and type(inputs.lanes) == "table" then inputs.lanes else {}
	local stored = load()
	-- a case written inline (no helper, no label) is known by WHERE kit/cmd/qa.luau defines it; its name and lane are
	-- learned the first time it runs and kept while qa.luau is the same text (an edit there forgets them all)
	local qa = "kit/cmd/qa.luau"
	local source = if fs.isFile(qa) then serde.hash("sha256", (string.gsub(fs.readFile(qa), "\r\n", "\n"))) else ""
	if stored.source ~= source or type(stored.learned) ~= "table" then
		stored.source = source
		stored.learned = {}
	end
	local seen: { [string]: number } = {}
	local stats = { ran = 0, cached = 0, other = 0 }
	local wrapped = {}
	local laneOfCase: { string? } = {} -- (the lane a case belongs to, for --jobs: nil = not known before it runs)
	local dirty = 0
	local function flush(force: boolean?)
		-- (every 10 cases and once at the end - not after every case: 228 full JSON writes per cold run)
		dirty += 1
		if force or dirty >= 10 then
			dirty = 0
			pcall(save, stored)
		end
	end
	for _, fn in plan do
		local label = labels[fn]
		local inline = label == nil
		local base = label or `@qa.luau:{debug.info(fn, "l") or "?"}`
		-- (two cases may share a label, or a helper's line: each is its own entry)
		seen[base] = (seen[base] or 0) + 1
		local id = if seen[base] == 1 then base else `{base} #{seen[base]}`
		local learnt = if inline then stored.learned[id] else nil
		local lane: string? = if inline then (learnt and learnt.lane) else Cache.laneOf(label :: string)
		local name = label or (learnt and learnt.name) or id
		table.insert(laneOfCase, lane)
		table.insert(wrapped, function(): Run.Step
			if lane == nil then -- (an inline case never run at this qa.luau: run it, learn what it is)
				stats.ran += 1
				local step = fn()
				local found = Cache.laneOf(tostring(step.name))
				stored.learned[id] = { name = step.name, lane = found }
				local key = keys[found]
				stored.cases[id] = if step.ok and key ~= nil then key else nil
				flush()
				return step
			end
			if opts.lanes and not (opts.lanes :: any)[lane] then
				stats.other += 1
				return {
					name = name,
					cmd = "(another lane)",
					exit = 0,
					ok = true,
					tail = "not run: another lane",
				} :: any
			end
			local key = keys[lane :: string]
			if opts.cache and key ~= nil and stored.cases[id] == key then
				stats.cached += 1
				print(`[cached] {name}`)
				return {
					name = name,
					cmd = "(cache)",
					exit = 0,
					ok = true,
					tail = "green at these same inputs (.verify/selftest_cache.json)",
				} :: any
			end
			stats.ran += 1
			local step = fn()
			stored.cases[id] = if step.ok and key ~= nil then key else nil
			if inline then -- (what it is called now: its lane cannot change while qa.luau does not)
				stored.learned[id] = { name = step.name, lane = lane }
			end
			flush() -- (every 10 cases, and at the end: a run that is stopped keeps most of what it proved)
			return step
		end)
	end
	-- the run's own account, last: how much of it was RUN (a cached or lane-limited pass is not a cold proof)
	table.insert(wrapped, function()
		local partial = stats.cached > 0 or stats.other > 0
		return Run.step("selftest cases", true, "", {
			summary = `{stats.ran} run, {stats.cached} reused from the cache (green at the same inputs), {stats.other} in other lanes`
				.. if partial then " - a cold proof: lune run kit selftest --no-cache" else "",
		})
	end)
	local said = passSummary
	if opts.lanes then
		local names = {}
		for lane in opts.lanes :: any do
			table.insert(names, lane)
		end
		table.sort(names)
		said = `{passSummary} (lanes: {table.concat(names, ", ")})`
	end
	if opts.cache then
		said ..= " (cases green at the same inputs reused: --no-cache for a cold proof)"
	end
	local planned = wrapped
	if opts.jobs > 1 then
		planned = Cache.lanesAtOnce(wrapped, laneOfCase, opts.jobs, stats)
		said ..= ` ({opts.jobs} lanes at once; a case that failed beside the others was run again alone)`
	end
	local code = Run.chain("selftest", planned, codeFor, said)
	pcall(save, stored)
	return code
end

-- --jobs N (PARALLAX_FINAL_CLOSURE_SPEC A2, 2026-11-22): the LANES run at once, N at a time, each lane's cases one
-- after another in the order kit/cmd/qa.luau declares them (a lane's cases share its fixture folders); the "kit" cases
-- and every case whose lane is not known yet run alone after the lanes, one at a time (they may read anything). A
-- case that fails beside the others is run AGAIN, ALONE, once every lane is done, and only that run counts. The plan
-- handed back is the same cases in the same order: Run.chain reports them exactly as a serial run does.
function Cache.lanesAtOnce(
	wrapped: { () -> Run.Step },
	laneOfCase: { string? },
	jobs: number,
	stats: { [string]: number }
): { () -> Run.Step }
	local groups: { [string]: { number } } = {}
	local names: { string } = {}
	local last = #wrapped -- (the run's own account, appended after the cases, stays last and serial)
	for i = 1, last - 1 do
		local lane = laneOfCase[i]
		if lane ~= nil and lane ~= "kit" then
			if not groups[lane] then
				groups[lane] = {}
				table.insert(names, lane)
			end
			table.insert(groups[lane], i)
		end
	end
	local results: { [number]: Run.Step } = {}
	local workers = 0
	for w = 1, math.min(jobs, #names) do
		local _ = w
		workers += 1
		task.spawn(function()
			Run.quietThreads[coroutine.running()] = true
			while #names > 0 do
				local lane = table.remove(names, 1) :: string
				for _, i in groups[lane] do
					local ok, step = pcall(wrapped[i])
					results[i] = if ok
						then step
						else Run.step("(a case that crashed)", false, tostring(step), { summary = tostring(step) })
				end
			end
			Run.quietThreads[coroutine.running()] = nil
			workers -= 1
		end)
	end
	local function lanesDone()
		while workers > 0 do
			task.wait(0.1)
		end
	end
	local planned: { () -> Run.Step } = {}
	for i, fn in wrapped do
		local lane = laneOfCase[i]
		if i == last or lane == nil or lane == "kit" then
			planned[i] = function(): Run.Step
				lanesDone()
				return fn()
			end
		else
			planned[i] = function(): Run.Step
				while results[i] == nil do
					task.wait(0.1)
				end
				local step = results[i]
				if not step.ok then
					lanesDone()
					stats.ran -= 1 -- (the lone run counts it again)
					local alone = fn()
					if alone.ok then
						alone.tail = (alone.tail or "")
							.. " (failed beside the other lanes, passed alone: a collision, not a failure)"
					end
					return alone
				end
				return step
			end
		end
	end
	return planned
end

return Cache

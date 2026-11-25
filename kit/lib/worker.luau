-- worker.luau — a PERSISTENT Blender for many builds in a row (kit/blender/worker.py): `kit watch` builds through it
-- without paying Blender's start-up every time (measured on a plank fixture: 7.6 s per warm build vs 11.1 s fresh,
-- identical verdicts). The worker lives as long as the command that started it (Lune ends its children on exit) or
-- until it has been idle for `idle` seconds; it refuses work and asks for a restart when the kit's code changed.
local fs = require("@lune/fs")
local net = require("@lune/net")
local process = require("@lune/process")
local serde = require("@lune/serde")
local task = require("@lune/task")

local Config = require("./config")
local Run = require("./run")

local Worker = {}

-- spawned: this command started the worker (only its starter stops it: another command may be using it)
export type Handle = { port: number, token: string, pid: number, spawned: boolean? }

local function statePath(): string
	return Config.path("build") .. "/worker.json"
end

local function readState(): Handle?
	if not fs.isFile(statePath()) then
		return nil
	end
	local ok, s = pcall(serde.decode, "json" :: any, fs.readFile(statePath()))
	if ok and type(s) == "table" and type(s.port) == "number" and type(s.token) == "string" then
		return s :: any
	end
	return nil
end

-- answers, and is not on its way out (a retiring worker answers 503)
local function alive(h: Handle): boolean
	local ok, res = pcall(net.request, { url = `http://127.0.0.1:{h.port}/ping`, method = "GET" } :: any)
	return ok and res.ok
end

-- a running worker for this project (a fresh one when none answers) -> (handle, nil) or (nil, why)
function Worker.start(idle: number?): (Handle?, string?)
	local h = readState()
	if h and alive(h) then
		return h, nil
	end
	if fs.isFile(statePath()) then
		pcall(fs.removeFile, statePath())
	end
	local ok, err = pcall(process.create, Run.tool("blender"), {
		"-b",
		"--factory-startup",
		"--python-exit-code",
		"2",
		"-P",
		"kit/blender/worker.py",
		"--",
		"--idle",
		tostring(idle or 900),
	}, { env = { KIT_BUILD = Config.path("build") } } :: any)
	if not ok then
		return nil, `could not start Blender ({Run.tool("blender")}): {err}`
	end
	local started = os.time()
	while os.time() - started < 90 do
		task.wait(0.25)
		h = readState()
		if h and alive(h) then
			h.spawned = true
			return h, nil
		end
	end
	return nil, `the Blender worker did not answer within 90 s — read {Config.path("build")}/worker.log`
end

-- the build's own JSON verdict line (the last one it printed), or nil when it crashed before printing one
function Worker.verdict(output: string): any?
	local found = nil
	for line in string.gmatch(output, "[^\r\n]+") do
		if string.sub(line, 1, 1) == "{" and string.find(line, '"schema"', 1, true) then
			local ok, v = pcall(serde.decode, "json" :: any, line)
			if ok then
				found = v
			end
		end
	end
	return found
end

-- one build through the worker, exactly as `blender -b --factory-startup -P <script> -- <args>` would run it
-- -> { exit, output, seconds, verdict } | { restart = true } (the kit changed: start a fresh worker) | { error }
function Worker.build(h: Handle, script: string, args: { string }): any
	local headers = { ["X-Kit-Token"] = h.token, ["Content-Type"] = "application/json" }
	local body = serde.encode("json", { script = script, args = args, env = { KIT_BUILD = Config.path("build") } })
	local ok, res = pcall(
		net.request,
		{ url = `http://127.0.0.1:{h.port}/build`, method = "POST", headers = headers, body = body } :: any
	)
	if not ok or not res.ok then
		return { error = `the worker refused the build ({if ok then res.statusCode .. " " .. res.body else res})` }
	end
	local job = serde.decode("json", res.body)
	if job.restart then
		return { restart = true }
	end
	while true do
		task.wait(0.1)
		local ok2, r = pcall(
			net.request,
			{ url = `http://127.0.0.1:{h.port}/result/{job.job}`, method = "GET", headers = headers } :: any
		)
		if not ok2 or not r.ok then
			return { error = "the worker went away during the build (read build/worker.log)" }
		end
		local d = serde.decode("json", r.body)
		if d.done then
			d.verdict = Worker.verdict(d.output or "")
			return d
		end
	end
end

-- stop the worker — only one this command started (another command may be building through a shared one)
function Worker.stop(h: Handle)
	if not h.spawned then
		return
	end
	pcall(
		net.request,
		{
			url = `http://127.0.0.1:{h.port}/quit`,
			method = "POST",
			headers = { ["X-Kit-Token"] = h.token },
			body = "{}",
		} :: any
	)
end

return Worker

-- visionworker.luau — the WARM vision worker's client (kit/vision/serve.py): kit/vision/run.py's models loaded once
-- and kept, so a cut-out, a mask, a rank or a look-alike score is answered in-process instead of by a fresh Python that
-- loads its model again. Run.content routes every `kit/vision/run.py` step through it WHEN ONE ANSWERS (started by
-- `kit vision serve`; the runners of the next phase — kit gather — will start one for their own duration through
-- `start`); with none, the call runs cold exactly as before. A worker never starts by itself: it holds GPU memory a
-- build's renders or a generator may need.
local fs = require("@lune/fs")
local net = require("@lune/net")
local process = require("@lune/process")
local serde = require("@lune/serde")
local task = require("@lune/task")

local Config = require("./config")

local VisionWorker = {}

export type Handle = { port: number, token: string, pid: number, spawned: boolean? }

local function statePath(): string
	return Config.path("build") .. "/vision_worker.json"
end

local function readState(): Handle?
	if not fs.isFile(statePath()) then
		return nil
	end
	local okRead, text = pcall(fs.readFile, statePath())
	if not okRead then
		return nil
	end
	local ok, s = pcall(serde.decode, "json" :: any, text)
	if ok and type(s) == "table" and type(s.port) == "number" and type(s.token) == "string" then
		return s :: any
	end
	return nil
end

-- the worker's /ping answer — only when it IS the worker the state file names (a vision worker, that pid: a port
-- reused by another server is no worker); a dead or foreign answer deletes the stale state file, so later calls run
-- cold at once instead of knocking on a dead port every time
function VisionWorker.status(): any?
	local h = readState()
	if not h then
		return nil
	end
	local ok, res = pcall(net.request, { url = `http://127.0.0.1:{h.port}/ping`, method = "GET" } :: any)
	local ok2, d = false, nil
	if ok and res.ok then
		ok2, d = pcall(serde.decode, "json" :: any, res.body)
	end
	if ok2 and type(d) == "table" and d.kind == "vision" and d.pid == h.pid then
		return d
	end
	if not (ok and res.statusCode == 503) then -- (503: retiring — its own file goes with it)
		local now = readState()
		if now and now.pid == h.pid and now.port == h.port then
			pcall(fs.removeFile, statePath())
		end
	end
	return nil
end

-- a running worker, or nil (never starts one: see `start`)
function VisionWorker.find(): Handle?
	local h = readState()
	if h and VisionWorker.status() then
		return h
	end
	return nil
end

-- start a worker as THIS command's child (the Blender worker's pattern): it lives as long as the command that started
-- it — a runner (kit gather) keeps its models warm for its whole run. To keep one across separate commands, run
-- `kit vision serve` in its own terminal (it stays in the foreground), or from a plain shell: python kit/vision/serve.py
-- --detach (Lune ends every process it started — a detached grandchild too — when its command exits)
function VisionWorker.start(python: string, idle: number?): (Handle?, string?)
	local h = VisionWorker.find()
	if h then
		return h, nil
	end
	if fs.isFile(statePath()) then
		pcall(fs.removeFile, statePath())
	end
	local ok, err = pcall(
		process.create,
		python,
		{ "kit/vision/serve.py", "--idle", tostring(idle or 1200) },
		{ env = { KIT_BUILD = Config.path("build") } } :: any
	)
	if not ok then
		return nil, `could not start the vision worker ({python}): {err}`
	end
	local wall = os.time()
	while os.time() - wall < 60 do
		task.wait(0.25)
		h = VisionWorker.find()
		if h then
			h.spawned = true
			return h, nil
		end
	end
	return nil, `the vision worker did not answer within 60 s — read {Config.path("build")}/vision_worker.log`
end

local function post(h: Handle, path: string, body: any, deadline: number?): any?
	local headers = { ["X-Kit-Token"] = h.token, ["Content-Type"] = "application/json" }
	local ok, res = pcall(
		net.request,
		{
			url = `http://127.0.0.1:{h.port}{path}`,
			method = "POST",
			headers = headers,
			body = serde.encode("json", body),
		} :: any
	)
	if not ok or not res.ok then
		return nil
	end
	local okJob, job = pcall(serde.decode, "json" :: any, res.body)
	if not okJob or type(job) ~= "table" or job.restart or not job.job then
		return nil
	end
	local started = os.time() -- (wall seconds: os.clock is CPU time, idle while waiting)
	while true do
		task.wait(0.05)
		if os.time() - started > (deadline or 600) then
			local now = readState()
			if now and now.pid == h.pid then
				pcall(fs.removeFile, statePath()) -- (a worker that never answers is treated as gone)
			end
			return nil
		end
		local ok2, r = pcall(
			net.request,
			{ url = `http://127.0.0.1:{h.port}/result/{job.job}`, method = "GET", headers = headers } :: any
		)
		if not ok2 or not r.ok then
			return nil
		end
		local okD, d = pcall(serde.decode, "json" :: any, r.body)
		if not okD or type(d) ~= "table" then
			return nil
		end
		if d.done then
			return if d.crashed then nil else d -- (a crashed call runs cold; the worker retired)
		end
	end
end

-- one `kit/vision/run.py <argv>` through a running worker -> { exit, output, seconds } | nil (none answers, it was
-- stale, it went away: the caller runs the call cold)
function VisionWorker.run(argv: { string }): any?
	local h = VisionWorker.find()
	if not h then
		return nil
	end
	return post(h, "/run", { argv = argv }, 600)
end

-- give the GPU back (a generator needs the whole card): the worker drops its models, loads them again on the next call
function VisionWorker.free(): boolean
	local h = VisionWorker.find()
	return h ~= nil and post(h, "/free", {}, 60) ~= nil -- (a running call finishes first: up to a minute)
end

function VisionWorker.stop(): boolean
	local h = readState()
	if not h then
		return false
	end
	if not VisionWorker.status() then
		return false -- (none, or a stale file: nothing to stop)
	end
	local ok, res = pcall(
		net.request,
		{
			url = `http://127.0.0.1:{h.port}/quit`,
			method = "POST",
			headers = { ["X-Kit-Token"] = h.token },
			body = "{}",
		} :: any
	)
	return ok and res.ok
end

return VisionWorker

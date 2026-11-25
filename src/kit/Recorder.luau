--!strict
-- Recorder.luau — the FLIGHT RECORDER (mission 06, idea 14): the last remote calls the server received, kept in a
-- ring buffer, written out the moment any error is logged. A bug report then carries what the clients just sent.
-- The generated Net modules (kit net) record every client->server call: "ok", "limited" (rate limit) or
-- "rejected <arg>" (Guard), with a SHORT summary of each argument (hostile input stays short: strings are cut, tables
-- are counted, never walked). Pure: Recorder.watch takes the ScriptContext it listens to (the first record() on a
-- server connects it by itself), so the kit's specs run it outside Roblox.
local Recorder = {}

Recorder.CAPACITY = 64
Recorder.DUMP_GAP = 1 -- seconds between two dumps (an error in a loop must not flood the output)

export type Entry = { t: number, remote: string, user: number, verdict: string, args: string }

local buffer: { Entry } = {}
local head = 0
local count = 0
local watched = false
local lastDump = -math.huge

-- one argument as a short string, whatever a client sent
function Recorder.summarize(v: unknown): string
	local t = typeof(v)
	if t == "number" then
		local n = v :: number
		if n ~= n then
			return "nan"
		end
		return string.format("%.4g", n)
	elseif t == "string" then
		local s = v :: string
		if #s > 24 then
			return string.format("%q", string.sub(s, 1, 24)) .. `..(+{#s - 24})`
		end
		return string.format("%q", s)
	elseif t == "table" then
		local n = 0
		for _ in v :: { [any]: any } do
			n += 1
			if n > 999 then
				break
			end
		end
		return `table({if n > 999 then "999+" else tostring(n)})`
	elseif t == "nil" or t == "boolean" then
		return tostring(v)
	end
	return t
end

function Recorder.record(remote: string, user: number, verdict: string, ...: unknown)
	local parts = {}
	for i = 1, math.min(select("#", ...), 8) do
		table.insert(parts, Recorder.summarize((select(i, ...))))
	end
	if select("#", ...) > 8 then
		table.insert(parts, `+{select("#", ...) - 8} more`)
	end
	head = head % Recorder.CAPACITY + 1
	buffer[head] = { t = os.clock(), remote = remote, user = user, verdict = verdict, args = table.concat(parts, ", ") }
	count = math.min(count + 1, Recorder.CAPACITY)
	if not watched then
		watched = true
		-- on a Roblox server the recorder listens by itself; outside Roblox (the kit's specs) there is no `game`
		local ok, sc = pcall(function()
			return (game :: any):GetService("ScriptContext")
		end)
		local ok2, isServer = pcall(function()
			return (game :: any):GetService("RunService"):IsServer()
		end)
		if ok and ok2 and isServer and sc then
			Recorder.watch(sc, warn)
		end
	end
end

-- the buffer, oldest first
function Recorder.list(): { Entry }
	local out = {}
	for i = count - 1, 0, -1 do
		local at = ((head - 1 - i) % Recorder.CAPACITY) + 1
		table.insert(out, buffer[at])
	end
	return out
end

function Recorder.clear()
	buffer = {}
	head, count = 0, 0
end

-- the buffer as lines, newest last, each with its age in seconds
function Recorder.dump(now: number?): string
	local at = now or os.clock()
	local lines = { `[Recorder] the last {count} remote call(s), oldest first:` }
	for _, e in Recorder.list() do
		table.insert(lines, string.format("  -%.2fs %s user %d %s (%s)", at - e.t, e.remote, e.user, e.verdict, e.args))
	end
	return table.concat(lines, "\n")
end

-- write the buffer out on every logged error (at most once per DUMP_GAP seconds); `out` is warn in Roblox
function Recorder.watch(scriptContext: any, out: (string) -> ()): any
	return scriptContext.Error:Connect(function(message: string)
		local now = os.clock()
		if now - lastDump < Recorder.DUMP_GAP or count == 0 then
			return
		end
		lastDump = now
		out(`[Recorder] error: {message}\n{Recorder.dump(now)}`)
	end)
end

return Recorder

-- net.luau — NETWORK SCHEMAS -> generated, validated remotes (pure: schema in, Luau source out; tested headless).
-- assets/net/<System>.net.json:
-- { "system": "Strike",
--   "remotes": {
--     "Request": { "dir": "toServer", "rate": [5, 2],
--                  "args": [ { "name": "target", "type": "vector3", "max": 500 },
--                            { "name": "power", "type": "number", "min": 0, "max": 1 } ] },
--     "Reply":   { "dir": "toClient",
--                  "args": [ { "name": "ok", "type": "boolean" }, { "name": "reason", "type": "string", "max": 64 } ] } } }
-- Types: number {min,max} · integer {min,max} · string {max} · enum {values} · boolean · vector3 {max = magnitude}.
-- Generated src/net/<System>Net.luau (ReplicatedStorage.Net.<System>Net):
--   toServer  client: Net.Request.fire(target, power)
--             server: Net.Request.on(function(player, target: Vector3, power: number) ... end)
--               -> the wrapper rate-limits per player, Guard-checks EVERY argument (a bad packet is dropped silently)
--                  and only then calls the handler with typed values: validation cannot be forgotten.
--   toClient  server: Net.Reply.fire(player, ...) / fireAll(...) / fireExcept(player, ...)
--             client: Net.Reply.on(function(ok: boolean, reason: string) ... end)   (checked on arrival too)
local Net = {}

export type Issue = { path: string, message: string }

local TYPES = { number = true, integer = true, string = true, enum = true, boolean = true, vector3 = true }
local LUAU = {
	number = "number",
	integer = "number",
	string = "string",
	enum = "string",
	boolean = "boolean",
	vector3 = "Vector3",
}

-- Luau keywords, and the names the generated code uses itself: an argument / remote with one of these names would
-- not compile ("Net.end") or would shadow the generator's own locals (an arg "p" made fireExcept send a Player)
local RESERVED = {}
for _, w in
	string.split(
		"and break do else elseif end false for function if in local nil not or repeat return then true until while continue export type typeof",
		" "
	)
do
	RESERVED[w] = true
end
for _, w in
	string.split(
		"_ player p api ev limit handler Players ReplicatedStorage RunService Kit Guard RateLimit IS_SERVER FOLDER folder remote Net",
		" "
	)
do
	RESERVED[w] = true
end

local function stringList(v: any): boolean
	if type(v) ~= "table" or #v == 0 then
		return false
	end
	for _, s in v do
		if type(s) ~= "string" or #s > 100 then
			return false
		end
	end
	return true
end

local function ident(s: any): boolean
	return type(s) == "string" and string.match(s, "^[%a_][%w_]*$") ~= nil and not RESERVED[s]
end

local function num(v: any): boolean
	return type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge
end

local function lit(v: any): string
	if type(v) == "string" then
		return string.format("%q", v)
	end
	return tostring(v)
end

-- the Guard check for one argument: lines that set v<i> or return
local function guardLines(arg: any, i: number, indent: string, before: string?): { string }
	local a, v, ok = `a{i}`, `v{i}`, `ok{i}`
	local t = arg.type
	local call
	if t == "number" then
		call = `Guard.number({a}, {lit(arg.min or -1e9)}, {lit(arg.max or 1e9)})`
	elseif t == "integer" then
		call = `Guard.integer({a}, {lit(arg.min or -2147483648)}, {lit(arg.max or 2147483647)})`
	elseif t == "string" then
		call = `Guard.string({a}, {lit(arg.max or 200)})`
	elseif t == "enum" then
		local vals = {}
		for _, s in arg.values do
			table.insert(vals, lit(s))
		end
		call = `Guard.oneOf({a}, \{ {table.concat(vals, ", ")} \})`
	elseif t == "boolean" then
		call = `Guard.boolean({a})`
	else
		call = `Guard.vector3({a})`
	end
	-- `before`: a line run before a rejection returns (the server's flight recorder)
	local out = { `{indent}local {ok}, {v} = {call}`, `{indent}if not {ok} then` }
	if before then
		table.insert(out, `{indent}\t{before}`)
	end
	table.insert(out, `{indent}\treturn`)
	table.insert(out, `{indent}end`)
	if t == "vector3" and num(arg.max) then
		table.insert(out, `{indent}if ({v} :: Vector3).Magnitude > {lit(arg.max)} then`)
		if before then
			table.insert(out, `{indent}\t{before}`)
		end
		table.insert(out, `{indent}\treturn`)
		table.insert(out, `{indent}end`)
	end
	return out
end

function Net.validate(schema: any, file: string?): { Issue }
	local issues: { Issue } = {}
	local function bad(path: string, message: string)
		table.insert(issues, { path = path, message = message })
	end
	if type(schema) ~= "table" then
		bad(file or "schema", "a schema is a JSON object")
		return issues
	end
	if not ident(schema.system) then
		bad("system", '"system" must be a Luau identifier (the system\'s PascalName)')
	end
	if type(schema.remotes) ~= "table" or next(schema.remotes) == nil then
		bad("remotes", '"remotes" must name at least one remote')
		return issues
	end
	for name, r in schema.remotes do
		local p = `remotes.{name}`
		if not ident(name) then
			bad(p, "a remote name must be a Luau identifier, not a keyword or a name the generated code uses")
		end
		if type(r) ~= "table" then
			bad(p, "a remote is an object")
			continue
		end
		if r.dir ~= "toServer" and r.dir ~= "toClient" then
			bad(p .. ".dir", '"dir" is "toServer" (client asks) or "toClient" (server tells)')
		end
		if r.dir == "toServer" then
			local rate = r.rate
			if
				type(rate) ~= "table"
				or not num(rate[1])
				or not num(rate[2])
				or rate[1] < 1
				or rate[2] <= 0
				or rate[1] > 200 -- (a limit of 1e12 is no limit)
				or rate[2] > 60
			then
				bad(
					p .. ".rate",
					'a toServer remote needs "rate": [burst 1..200, refillPerSecond up to 60] (every client request is rate-limited)'
				)
			end
		end
		local seen = {}
		for i, arg in r.args or {} do
			local ap = `{p}.args[{i}]`
			if type(arg) ~= "table" or not ident(arg.name) then
				bad(
					ap,
					`each argument needs a "name": an identifier, not a keyword or a generated name ({tostring(
						type(arg) == "table" and arg.name
					)})`
				)
				continue
			end
			if seen[arg.name] then
				bad(ap, `duplicate argument "{arg.name}"`)
			end
			seen[arg.name] = true
			-- whatever the direction: a bound that is given must be a finite number (a {} or inf went straight into
			-- the generated Guard call and did not compile)
			for _, key in { "min", "max" } do
				if arg[key] ~= nil and not num(arg[key]) then
					bad(ap, `"{arg.name}": "{key}" must be a finite number (got {tostring(arg[key])})`)
				end
			end
			if num(arg.min) and num(arg.max) and arg.min > arg.max then
				bad(ap, `"{arg.name}": "min" is above "max"`)
			end
			if not TYPES[arg.type] then
				bad(
					ap .. ".type",
					`type must be number | integer | string | enum | boolean | vector3 (got {tostring(arg.type)})`
				)
			elseif (arg.type == "number" or arg.type == "integer") and r.dir == "toServer" then
				if not num(arg.min) or not num(arg.max) or arg.min > arg.max then
					bad(ap, `"{arg.name}": a client-sent number needs "min" and "max" (never trust the client's range)`)
				end
			elseif
				arg.type == "string"
				and r.dir == "toServer"
				and (not num(arg.max) or arg.max < 1 or arg.max > 10000)
			then
				bad(ap, `"{arg.name}": a client-sent string needs "max" length (1..10000)`)
			elseif arg.type == "enum" and not stringList(arg.values) then
				bad(ap, `"{arg.name}": an enum needs "values": ["a", "b"] (strings of at most 100 characters)`)
			elseif arg.type == "vector3" and r.dir == "toServer" and not num(arg.max) then
				bad(
					ap,
					`"{arg.name}": a client-sent vector3 needs "max" (magnitude) — positions far outside the map are exploits`
				)
			end
		end
	end
	return issues
end

function Net.compile(schema: any, source: string?): (string?, { Issue })
	local issues = Net.validate(schema, source)
	if #issues > 0 then
		return nil, issues
	end
	local sys = schema.system
	local names = {}
	for name in schema.remotes do
		table.insert(names, name)
	end
	table.sort(names)
	local L = {}
	local function w(s: string)
		table.insert(L, s)
	end
	w("--!strict")
	-- (the schema's FILE name only: a path would make the same schema generate differently from another folder)
	local from = if source then string.match(source, "([^/\\]+)$") or source else "a schema"
	w(`-- {sys}Net — GENERATED by \`lune run kit net\` from assets/net/{from}. Do not edit: change the schema and`)
	w("-- re-run. Every client->server argument is rate-limited and Guard-checked HERE before your handler sees it.")
	w('local Players = game:GetService("Players")')
	w('local ReplicatedStorage = game:GetService("ReplicatedStorage")')
	w('local RunService = game:GetService("RunService")')
	w("")
	w('local Kit = ReplicatedStorage:WaitForChild("kit")')
	w('local Guard = require(Kit:WaitForChild("Guard"))')
	w('local RateLimit = require(Kit:WaitForChild("RateLimit"))')
	w('local Recorder = require(Kit:WaitForChild("Recorder"))')
	w("")
	w("local IS_SERVER = RunService:IsServer()")
	w(`local FOLDER = "Net_{sys}"`)
	w("")
	w("local function folder(): Instance")
	w("\tif IS_SERVER then")
	w("\t\tlocal existing = ReplicatedStorage:FindFirstChild(FOLDER)")
	w("\t\tif existing then")
	w("\t\t\treturn existing")
	w("\t\tend")
	w('\t\tlocal f = Instance.new("Folder")')
	w("\t\tf.Name = FOLDER")
	w("\t\tf.Parent = ReplicatedStorage")
	w("\t\treturn f")
	w("\tend")
	w("\treturn ReplicatedStorage:WaitForChild(FOLDER)")
	w("end")
	w("")
	w("local function remote(name: string): RemoteEvent")
	w("\tlocal f = folder()")
	w("\tif IS_SERVER then")
	w("\t\tlocal existing = f:FindFirstChild(name)")
	w('\t\tif existing and existing:IsA("RemoteEvent") then')
	w("\t\t\treturn existing")
	w("\t\tend")
	w('\t\tlocal r = Instance.new("RemoteEvent")')
	w("\t\tr.Name = name")
	w("\t\tr.Parent = f")
	w("\t\treturn r")
	w("\tend")
	w("\treturn f:WaitForChild(name) :: RemoteEvent")
	w("end")
	w("")
	w("local Net = {}")
	for _, name in names do
		local r = schema.remotes[name]
		local args = r.args or {}
		local typed, plain, raw, vals = {}, {}, {}, {}
		for i, a in args do
			table.insert(typed, `{a.name}: {LUAU[a.type]}`)
			table.insert(plain, a.name)
			table.insert(raw, `a{i}: unknown`)
			table.insert(vals, `v{i}`)
		end
		local describe = {}
		for _, a in args do
			table.insert(describe, `{a.name}: {a.type}`)
		end
		w("")
		w(`-- {name}: {r.dir} ({table.concat(describe, ", ")})`)
		w("do")
		w(`\tlocal ev = remote("{name}")`)
		w(`\tlocal api = \{}`)
		if r.dir == "toServer" then
			w(`\tlocal limit = RateLimit.new({lit(r.rate[1])}, {lit(r.rate[2])})`)
			w(`\tfunction api.fire({table.concat(typed, ", ")})`)
			w(`\t\tev:FireServer({table.concat(plain, ", ")})`)
			w("\tend")
			local sig = "player: Player" .. (if #typed > 0 then ", " .. table.concat(typed, ", ") else "")
			w(`\tfunction api.on(handler: ({sig}) -> ())`)
			w(`\t\tassert(IS_SERVER, "{sys}Net.{name}.on is server-only")`)
			local params = "player: Player" .. (if #raw > 0 then ", " .. table.concat(raw, ", ") else "")
			w(`\t\tev.OnServerEvent:Connect(function({params})`)
			-- the flight recorder (src/kit/Recorder): every call, its verdict, a short summary of what the client sent
			local tag = `"{sys}.{name}"`
			local sent = ""
			for i = 1, #args do
				sent ..= `, a{i}`
			end
			w("\t\t\tif not limit:take(player.UserId, os.clock()) then")
			w(`\t\t\t\tRecorder.record({tag}, player.UserId, "limited")`)
			w("\t\t\t\treturn")
			w("\t\t\tend")
			for i, a in args do
				local before = `Recorder.record({tag}, player.UserId, "rejected {a.name}"{sent})`
				for _, line in guardLines(a, i, "\t\t\t", before) do
					w(line)
				end
			end
			w(`\t\t\tRecorder.record({tag}, player.UserId, "ok"{sent})`)
			w(`\t\t\thandler(player{if #vals > 0 then ", " .. table.concat(vals, ", ") else ""})`)
			w("\t\tend)")
			w("\t\tPlayers.PlayerRemoving:Connect(function(p: Player)")
			w("\t\t\tlimit:forget(p.UserId)")
			w("\t\tend)")
			w("\tend")
		else
			local typedP = "player: Player" .. (if #typed > 0 then ", " .. table.concat(typed, ", ") else "")
			local pass = if #plain > 0 then ", " .. table.concat(plain, ", ") else ""
			w(`\tfunction api.fire({typedP})`)
			w(`\t\tev:FireClient(player{pass})`)
			w("\tend")
			w(`\tfunction api.fireAll({table.concat(typed, ", ")})`)
			w(`\t\tev:FireAllClients({table.concat(plain, ", ")})`)
			w("\tend")
			w(`\tfunction api.fireExcept({typedP})`)
			w("\t\tfor _, p in Players:GetPlayers() do")
			w("\t\t\tif p ~= player then")
			w(`\t\t\t\tev:FireClient(p{pass})`)
			w("\t\t\tend")
			w("\t\tend")
			w("\tend")
			w(`\tfunction api.on(handler: ({table.concat(typed, ", ")}) -> ())`)
			w(`\t\tassert(not IS_SERVER, "{sys}Net.{name}.on is client-only")`)
			w(`\t\tev.OnClientEvent:Connect(function({table.concat(raw, ", ")})`)
			for i, a in args do
				for _, line in guardLines(a, i, "\t\t\t") do
					w(line)
				end
			end
			w(`\t\t\thandler({table.concat(vals, ", ")})`)
			w("\t\tend)")
			w("\tend")
		end
		w(`\tNet.{name} = api`)
		w("end")
	end
	w("")
	w("return Net")
	return table.concat(L, "\n") .. "\n", {}
end

return Net

-- audit.luau — static security audit of Roblox Luau source (pure: text in, findings out).
-- Errors (fail `kit verify`):
--   remote-arg      a client-supplied OnServerEvent/OnServerInvoke argument is used without validation
--   invoke-client   server calls RemoteFunction:InvokeClient (a client can hang that server thread forever)
--   loadstring      dynamic code execution
--   require-id      require(<number>) — loads a Creator Store module by id: the classic free-model backdoor
-- Warnings:
--   no-rate-limit   a remote handler has no rate limit / cooldown
--   fire-all-loop   FireAllClients inside a loop (network flood)
--   fenv            getfenv/setfenv (obfuscation / sandbox escapes)
-- An argument counts as validated when it is passed to typeof()/type(), a Guard.* call, a function whose name
-- contains check/validate/guard/sanitize/clamp/rules, or compared to itself (NaN check).
local Audit = {}

export type Finding = { file: string, line: number, rule: string, severity: string, message: string, fix: string }

-- Replace strings and comments with spaces (newlines kept) so keyword scanning can't be fooled by text.
function Audit.strip(src: string): string
	local out = table.create(#src)
	local i, n = 1, #src
	local function blank(a: number, b: number)
		for k = a, b do
			local ch = string.sub(src, k, k)
			table.insert(out, if ch == "\n" then "\n" else " ")
		end
	end
	while i <= n do
		local two = string.sub(src, i, i + 1)
		local ch = string.sub(src, i, i)
		if two == "--" then
			local eq = string.match(src, "^%[(=*)%[", i + 2)
			local stop
			if eq then
				local close = "]" .. eq .. "]"
				local _, e = string.find(src, close, i + 4 + #eq, true)
				stop = e or n
			else
				stop = (string.find(src, "\n", i, true) or (n + 1)) - 1
			end
			blank(i, stop)
			i = stop + 1
		elseif ch == "[" and string.match(src, "^%[=*%[", i) then
			local eq = string.match(src, "^%[(=*)%[", i)
			local _, e = string.find(src, "]" .. eq .. "]", i + 2 + #eq, true)
			local stop = e or n
			blank(i, stop)
			i = stop + 1
		elseif ch == '"' or ch == "'" or ch == "`" then
			local j = i + 1
			while j <= n do
				local c = string.sub(src, j, j)
				if c == "\\" then
					j += 2
				elseif c == ch or (c == "\n" and ch ~= "`") then
					break
				else
					j += 1
				end
			end
			-- keep the quotes so `"x"` stays a token boundary, blank the inside
			table.insert(out, ch)
			blank(i + 1, j - 1)
			if j <= n then
				table.insert(out, string.sub(src, j, j))
			end
			i = j + 1
		else
			table.insert(out, ch)
			i += 1
		end
	end
	return table.concat(out)
end

-- text carries one extra leading newline (see Audit.scan), so the newline count IS the 1-based line number
local function lineAt(text: string, pos: number): number
	local _, count = string.gsub(string.sub(text, 1, pos), "\n", "")
	return math.max(1, count)
end

-- Given the position right after a `function` keyword, return the index of its matching `end`.
local OPEN = { ["function"] = true, ["do"] = true, ["then"] = true, ["repeat"] = true }
local CLOSE = { ["end"] = true, ["until"] = true }
function Audit.blockEnd(text: string, from: number): number?
	local depth = 1
	local skipThen = false
	local pos = from
	while true do
		local s, e, word = string.find(text, "([%a_][%w_]*)", pos)
		if not s then
			return nil
		end
		local before = if s > 1 then string.sub(text, s - 1, s - 1) else ""
		if before ~= "." and before ~= ":" then
			if word == "elseif" then
				skipThen = true
			elseif word == "then" and skipThen then
				skipThen = false
			elseif OPEN[word] then
				depth += 1
			elseif CLOSE[word] then
				depth -= 1
				if depth == 0 then
					return s
				end
			end
		end
		pos = (e :: number) + 1
	end
end

local function escape(s: string): string
	return (string.gsub(s, "[%^%$%(%)%%%.%[%]%*%+%-%?]", "%%%0"))
end

local VALIDATOR_NAME = "[%w_%.:]*[Cc][Hh][Ee][Cc][Kk]"

local function validated(body: string, param: string): boolean
	local p = escape(param)
	local patterns = {
		"typeof%s*%(%s*" .. p .. "%s*%)",
		"type%s*%(%s*" .. p .. "%s*%)",
		"Guard%s*%.%s*[%w_]+%s*%(%s*" .. p .. "[%s,%)]",
		p .. "%s*~=%s*" .. p .. "[^%w_]",
	}
	for _, pat in patterns do
		if string.find(body, pat) then
			return true
		end
	end
	-- passed to a checking function: check/validate/guard/sanitize/clamp/rules in the callee name
	for callee, argList in string.gmatch(body, "([%w_%.:]+)%s*(%b())") do
		local lower = string.lower(callee)
		if
			string.find(lower, "check")
			or string.find(lower, "valid")
			or string.find(lower, "guard")
			or string.find(lower, "sanitiz")
			or string.find(lower, "clamp")
			or string.find(lower, "rules")
		then
			if string.find(argList, "[%(,]%s*" .. p .. "%s*[,%)]") then
				return true
			end
		end
	end
	return false
end
local _ = VALIDATOR_NAME

local function used(body: string, param: string): boolean
	return string.find(body, "[^%w_%.]" .. escape(param) .. "[^%w_]") ~= nil
end

local RATE_HINTS =
	{ "RateLimit", ":take%(", "os%.clock", "tick%(", "os%.time", "[Cc]ooldown", "canHit", "[Tt]hrottle", "[Dd]ebounce" }

function Audit.scan(file: string, src: string, isServer: boolean): { Finding }
	local findings: { Finding } = {}
	-- leading newline: every "not preceded by an identifier char" pattern also matches at the top of the file
	local text = "\n" .. Audit.strip(src)
	local function add(pos: number, rule: string, severity: string, message: string, fix: string)
		table.insert(findings, {
			file = file,
			line = lineAt(text, pos),
			rule = rule,
			severity = severity,
			message = message,
			fix = fix,
		})
	end

	-- remote handlers: X.OnServerEvent:Connect(function(player, a, b) ... end) and OnServerInvoke = function(...)
	local pos = 1
	while true do
		local s, e, kind = string.find(text, "(OnServer[EI][vn][%a]+)", pos)
		if not s then
			break
		end
		pos = (e :: number) + 1
		if kind ~= "OnServerEvent" and kind ~= "OnServerInvoke" then
			continue
		end
		-- the handler function: inline `function(...)` right after, or a named local function
		local fs_, fe, params = string.find(text, "^[%s:]*Connect%s*%(%s*function%s*(%b())", pos)
		if not fs_ then
			fs_, fe, params = string.find(text, "^%s*=%s*function%s*(%b())", pos)
		end
		local bodyStart, bodyEnd
		if fs_ then
			bodyStart = (fe :: number) + 1
			bodyEnd = Audit.blockEnd(text, bodyStart)
		else
			local named = string.match(text, "^[%s:]*Connect%s*%(%s*([%a_][%w_]*)%s*%)", pos)
				or string.match(text, "^%s*=%s*([%a_][%w_]*)", pos)
			if named then
				local ds, de, p2 = string.find(text, "function%s+" .. escape(named) .. "%s*(%b())")
				if ds then
					params = p2
					bodyStart = (de :: number) + 1
					bodyEnd = Audit.blockEnd(text, bodyStart)
				end
			end
		end
		if not params or not bodyStart or not bodyEnd then
			add(
				s,
				"remote-arg",
				"warn",
				`{kind} handler could not be analysed`,
				"use an inline function or a local named function"
			)
			continue
		end
		local body = string.sub(text, bodyStart, bodyEnd)
		local names = {}
		for piece in string.gmatch(string.sub(params, 2, -2), "[^,]+") do
			local name = string.match(piece, "^%s*([%a_][%w_]*)") or string.match(piece, "^%s*(%.%.%.)")
			if name then
				table.insert(names, name)
			end
		end
		for i = 2, #names do -- names[1] is the Player Roblox passes; everything after comes from the client
			local param = names[i]
			if param ~= "_" and param ~= "..." and used(body, param) and not validated(body, param) then
				add(
					s,
					"remote-arg",
					"error",
					`{kind}: client argument "{param}" is used without validation`,
					`check it first: local ok, v = Guard.number({param}, min, max) (or typeof/type) — never trust the client`
				)
			end
		end
		if string.find(params, "%.%.%.") and string.find(body, "%.%.%.") then
			add(
				s,
				"remote-arg",
				"error",
				`{kind}: varargs from the client are forwarded unchecked`,
				"name each argument and validate it"
			)
		end
		local limited = false
		for _, hint in RATE_HINTS do
			if string.find(body, hint) then
				limited = true
				break
			end
		end
		if not limited then
			add(
				s,
				"no-rate-limit",
				"warn",
				`{kind} handler has no rate limit or cooldown`,
				"add: if not limit:take(player.UserId, os.clock()) then return end (kit RateLimit)"
			)
		end
	end

	if isServer then
		local ps = string.find(text, ":%s*InvokeClient%s*%(")
		if ps then
			add(
				ps,
				"invoke-client",
				"error",
				"server calls InvokeClient",
				"use a RemoteEvent round-trip instead; a client can hang this thread forever"
			)
		end
	end
	local ls = string.find(text, "[^%w_%.]loadstring%s*%(")
	if ls then
		add(ls, "loadstring", "error", "loadstring executes dynamic code", "remove it")
	end
	for rs in string.gmatch(text, "()[^%w_%.]require%s*%(%s*%d+%s*%)") do
		add(
			rs :: number,
			"require-id",
			"error",
			"require(<asset id>) loads remote code — the classic free-model backdoor",
			"delete it; vendor the module into the repo after reading it"
		)
	end
	local fe2 = string.find(text, "[^%w_%.][gs]etfenv%s*%(")
	if fe2 then
		add(
			fe2,
			"fenv",
			"warn",
			"getfenv/setfenv: obfuscation or sandbox tricks",
			"remove unless you wrote it and know why"
		)
	end
	-- FireAllClients inside a for/while loop body
	for loopStart in string.gmatch(text, "()[^%w_]for[^%w_]") do
		local doS, doE = string.find(text, "[^%w_]do[^%w_]", loopStart :: number)
		if doS then
			local stop = Audit.blockEnd(text, doE :: number)
			if stop and string.find(string.sub(text, doE :: number, stop), ":%s*FireAllClients%s*%(") then
				add(
					loopStart :: number,
					"fire-all-loop",
					"warn",
					"FireAllClients inside a loop",
					"batch the data into one FireAllClients call"
				)
			end
		end
	end
	return findings
end

return Audit

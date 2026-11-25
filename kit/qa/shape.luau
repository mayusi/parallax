-- shape.luau — size / shape guards for gameplay code (mission 06, idea 13): WARNINGS in kit verify, never failures.
--   a service (a *.server.luau or a *Service* module) over 600 lines -> split it by responsibility
--   a function over 80 lines -> extract the steps
--   a cycle of requires between a game's own modules -> a module that needs both belongs below them
-- Scans every game's src/ (games/<Name>/src) except its kit runtime copy (src/kit: the kit's own, checked by its specs).
-- Strings and comments never count (Audit.strip keeps positions, so names are read from the source at the same place).
local fs = require("@lune/fs")

local Audit = require("../lib/audit")

local Shape = {}

Shape.SERVICE_LINES = 600
Shape.FUNCTION_LINES = 80

export type Finding = { path: string, line: number, kind: string, message: string }

local function lineAt(starts: { number }, pos: number): number
	local lo, hi = 1, #starts
	while lo < hi do
		local mid = (lo + hi + 1) // 2
		if starts[mid] <= pos then
			lo = mid
		else
			hi = mid - 1
		end
	end
	return lo
end

-- every function's (start line, end line, name) by counting blocks in the stripped code
function Shape.functions(src: string): { { first: number, last: number, name: string } }
	local code = Audit.strip(src)
	local starts = { 1 }
	for i = 1, #code do
		if string.byte(code, i) == 10 then
			table.insert(starts, i + 1)
		end
	end
	local out, stack = {}, {}
	local skipThen = 0
	local pos = 1
	while true do
		local a, b, word = string.find(code, "([%a_][%w_]*)", pos)
		if not a then
			break
		end
		local prev = if a > 1 then string.sub(code, a - 1, a - 1) else " "
		pos = (b :: number) + 1
		if prev == "." or prev == ":" then
			continue -- a field (t.end is not a keyword here)
		end
		if word == "function" then
			local name = string.match(code, "^%s*([%w_%.:]+)", pos) or "(anonymous)"
			table.insert(stack, { kind = "function", line = lineAt(starts, a :: number), name = name })
		elseif word == "elseif" then
			skipThen += 1
		elseif word == "then" then
			if skipThen > 0 then
				skipThen -= 1
			else
				table.insert(stack, { kind = "block" })
			end
		elseif word == "do" or word == "repeat" then
			table.insert(stack, { kind = "block" })
		elseif word == "end" or word == "until" then
			local top = table.remove(stack)
			if top and top.kind == "function" then
				table.insert(out, { first = top.line, last = lineAt(starts, a :: number), name = top.name })
			end
		end
	end
	return out
end

-- the module names a source requires (the last name inside each require(...): WaitForChild("X"), script.Parent.X)
function Shape.requires(src: string): { string }
	local code = Audit.strip(src)
	local out, pos = {}, 1
	while true do
		local a, b = string.find(code, "require%s*%(", pos)
		if not a then
			break
		end
		-- the matching close paren, counted in the stripped code
		local depth, i = 1, (b :: number) + 1
		while i <= #code and depth > 0 do
			local ch = string.sub(code, i, i)
			if ch == "(" then
				depth += 1
			elseif ch == ")" then
				depth -= 1
			end
			i += 1
		end
		local inside = string.sub(src, (b :: number) + 1, i - 2)
		local name = nil
		for q in string.gmatch(inside, "[\"']([%w_]+)[\"']") do
			name = q
		end
		if not name then
			for id in string.gmatch(inside, "([%a_][%w_]*)") do
				name = id
			end
		end
		if name then
			table.insert(out, name)
		end
		pos = i
	end
	return out
end

local function luauFiles(dir: string, out: { string })
	if not fs.isDir(dir) then
		return
	end
	local names = fs.readDir(dir)
	table.sort(names)
	for _, n in names do
		local p = dir .. "/" .. n
		if fs.isDir(p) then
			if n ~= "kit" then
				luauFiles(p, out)
			end
		elseif string.sub(n, -5) == ".luau" then
			table.insert(out, p)
		end
	end
end

local function moduleName(path: string): string
	local base = string.match(path, "([^/]+)%.luau$") or path
	local noServer = string.gsub(base, "%.server$", "")
	local name = string.gsub(noServer, "%.client$", "")
	return name
end

-- one source tree (a game's src): every finding
function Shape.scanDir(dir: string): { Finding }
	local files = {}
	luauFiles(dir, files)
	local findings: { Finding } = {}
	local graph: { [string]: { string } } = {}
	local pathOf: { [string]: string } = {}
	for _, path in files do
		local src = fs.readFile(path)
		local name = moduleName(path)
		pathOf[name] = path
		local _, lines = string.gsub(src, "\n", "")
		lines += 1
		local service = string.find(path, "%.server%.luau$") ~= nil or string.find(name, "Service") ~= nil
		if service and lines > Shape.SERVICE_LINES then
			table.insert(findings, {
				path = path,
				line = 1,
				kind = "service",
				message = `{lines} lines (> {Shape.SERVICE_LINES}): split it by responsibility`,
			})
		end
		for _, f in Shape.functions(src) do
			local n = f.last - f.first + 1
			if n > Shape.FUNCTION_LINES then
				table.insert(findings, {
					path = path,
					line = f.first,
					kind = "function",
					message = `function {f.name} is {n} lines (> {Shape.FUNCTION_LINES}): extract its steps`,
				})
			end
		end
		graph[name] = Shape.requires(src)
	end
	-- cycles among this tree's own modules (a require of a name outside it is the kit's or Roblox's)
	local state: { [string]: number } = {}
	local reported: { [string]: boolean } = {}
	local function visit(n: string, trail: { string })
		state[n] = 1
		table.insert(trail, n)
		for _, m in graph[n] or {} do
			if graph[m] then
				if state[m] == 1 then
					local at = table.find(trail, m) :: number
					local cycle = { table.unpack(trail, at) }
					table.insert(cycle, m)
					local key = table.concat(cycle, ">")
					if not reported[key] then
						reported[key] = true
						table.insert(findings, {
							path = pathOf[m],
							line = 1,
							kind = "cycle",
							message = `require cycle {table.concat(cycle, " -> ")}: move what both need into a module below them`,
						})
					end
				elseif not state[m] then
					visit(m, trail)
				end
			end
		end
		table.remove(trail)
		state[n] = 2
	end
	local names = {}
	for n in graph do
		table.insert(names, n)
	end
	table.sort(names)
	for _, n in names do
		if not state[n] then
			visit(n, {})
		end
	end
	return findings
end

-- every game's src
function Shape.scanAll(): { Finding }
	local out = {}
	if not fs.isDir("games") then
		return out
	end
	local games = fs.readDir("games")
	table.sort(games)
	for _, g in games do
		local src = `games/{g}/src`
		if string.sub(g, 1, 1) ~= "." and fs.isDir(src) then
			for _, f in Shape.scanDir(src) do
				table.insert(out, f)
			end
		end
	end
	return out
end

return Shape

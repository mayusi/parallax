-- fuzz.luau — throw HOSTILE input at every exported function of the pure shared modules (src/shared/*.luau) and
-- report the ones that CRASH (a Rules function must answer "no", never throw: a thrown error inside a remote handler
-- kills that request and spams the server log — and some crash paths skip the cleanup after them).
-- Usage: lune run kit/test/fuzz [<module.luau> ...]   (normally: lune run kit fuzz [<Name> ...])
-- For each function (arity from debug.info): every argument position gets every hostile value while the others
-- hold an ordinary 1; plus a call with no arguments. Crashes = errors. A function that answers TRUE to NaN / inf /
-- a wrong type in a position = a warning ("accepted"): Rules that let NaN through are how exploits get in.
-- Prints one JSON line: {status, summary, next_action, crashes, accepted, modules}.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local NAN = 0 / 0
local deep: any = {}
do
	local t = deep
	for _ = 1, 300 do
		t.next = {}
		t = t.next
	end
end
local cyclic: any = {}
cyclic.self = cyclic

local HOSTILE: { { label: string, value: any, nonfinite: boolean? } } = {
	{ label = "NaN", value = NAN, nonfinite = true },
	{ label = "inf", value = math.huge, nonfinite = true },
	{ label = "-inf", value = -math.huge, nonfinite = true },
	{ label = "-0", value = -0 },
	{ label = "1e308", value = 1e308 },
	{ label = "-1e308", value = -1e308 },
	{ label = "2^53+1", value = 2 ^ 53 + 1 },
	{ label = "0.5", value = 0.5 },
	{ label = "-1", value = -1 },
	{ label = "nil", value = nil, nonfinite = true },
	{ label = "true", value = true, nonfinite = true },
	{ label = '""', value = "", nonfinite = true },
	{ label = "100k string", value = string.rep("x", 100000), nonfinite = true },
	{ label = '"\\0"', value = "\0", nonfinite = true },
	{ label = '"1"', value = "1", nonfinite = true },
	{ label = "{}", value = {}, nonfinite = true },
	{ label = "{1,2,3}", value = { 1, 2, 3 }, nonfinite = true },
	{ label = "300-deep table", value = deep, nonfinite = true },
	{ label = "cyclic table", value = cyclic, nonfinite = true },
	{ label = "{X=NaN,Y=1,Z=1}", value = { X = NAN, Y = 1, Z = 1 }, nonfinite = true },
	{ label = "function", value = function() end, nonfinite = true },
}

local function modulesFrom(args: { string }): { string }
	if #args > 0 then
		return args
	end
	local out = {}
	local shared = (process.env.KIT_GAME_ROOT or "") .. "src/shared"
	if fs.isDir(shared) then
		for _, f in fs.readDir(shared) do
			if string.sub(f, -5) == ".luau" then
				table.insert(out, shared .. "/" .. f)
			end
		end
	end
	table.sort(out)
	return out
end

local crashes, accepted, modules = {}, {}, {}
local calls = 0
local safeYes = 0 -- (a declared fail-safe function's yes to hostile input: its refusal)
for _, path in modulesFrom(process.args) do
	local ok, mod = pcall(function()
		return (require :: any)("../../" .. string.sub(path, 1, -6))
	end)
	if not ok or type(mod) ~= "table" then
		table.insert(modules, { module = path, loaded = false, error = tostring(mod) })
		continue
	end
	-- FAIL-SAFE TRUE, declared (LIMITATIONS_FIXES_V4 8.3): a function whose TRUE is the refusing answer - "is the round
	-- over?" says yes to a round that is not a round - is named in its module by a comment line
	-- `-- fuzz: safe-true isOver, isDead`; its yes to hostile input is that refusal, counted apart, never a warning
	local safeTrue: { [string]: boolean } = {}
	local okSrc, src = pcall(fs.readFile, path)
	if okSrc then
		for list in string.gmatch(src, "%-%-%s*fuzz:%s*safe%-true%s+([%w_, ]+)") do
			for fname in string.gmatch(list, "[%w_]+") do
				safeTrue[fname] = true
			end
		end
	end
	local fns = 0
	local names = {}
	for k in mod do
		table.insert(names, k)
	end
	table.sort(names)
	for _, name in names do
		local fn = mod[name]
		if type(fn) ~= "function" then
			continue
		end
		fns += 1
		local arity = debug.info(fn, "a")
		arity = math.clamp(arity or 0, 0, 6)
		local function try(args: { any }, n: number, label: string, h: any)
			calls += 1
			local results = table.pack(pcall(fn, table.unpack(args, 1, n)))
			if not results[1] then
				table.insert(crashes, {
					module = path,
					fn = name,
					input = label,
					error = string.sub(tostring(results[2]), 1, 160),
				})
			elseif h and h.nonfinite and results[2] == true then
				if safeTrue[name] then
					safeYes += 1
				else
					table.insert(accepted, { module = path, fn = name, input = label })
				end
			end
		end
		try({}, 0, "no arguments", nil)
		for pos = 1, arity do
			for _, h in HOSTILE do
				local args = table.create(arity, 1)
				args[pos] = h.value
				try(args, arity, `arg {pos} = {h.label}`, h)
			end
		end
	end
	table.insert(modules, { module = path, loaded = true, functions = fns })
end

-- one line per function for the crash list (the first input that broke it)
local seen, firsts = {}, {}
for _, c in crashes do
	local key = c.module .. ":" .. c.fn
	if not seen[key] then
		seen[key] = true
		table.insert(firsts, c)
		print(`  CRASH {c.module} {c.fn}({c.input}): {c.error}`)
	end
end
local seenA = {}
for _, a in accepted do
	local key = a.module .. ":" .. a.fn
	if not seenA[key] then
		seenA[key] = true
		print(`  warn  {a.module} {a.fn} answered TRUE to {a.input}`)
	end
end
local status = if #firsts > 0 then "fail" else "pass"
print(serde.encode("json", {
	status = status,
	summary = `{#modules} module(s), {calls} hostile call(s): {#firsts} function(s) crash`
		.. (if safeYes > 0 then ` ({safeYes} refusal(s) by declared fail-safe functions)` else "")
		.. (if #firsts > 0 then ` — {firsts[1].module} {firsts[1].fn}({firsts[1].input}): {firsts[1].error}` else ""),
	next_action = if #firsts > 0
		then `make {firsts[1].fn} answer instead of throwing: check type(x) == "number" and x == x (NaN) and math.abs(x) ~= math.huge first, return false + a reason`
		elseif
			next(seenA) ~= nil
		then `improve: a Rules function said yes to NaN / inf / a wrong type — reject it (see the warn lines)`
		else "none — proceed",
	crashes = firsts,
	accepted = accepted,
	modules = modules,
}))
process.exit(if status == "pass" then 0 else 1)

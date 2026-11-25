-- hudsize.luau — a HUD written as GAME CODE, measured on screen against the size its reference sets (the owner's
-- sg_hud5 3/10, 2026-10-29: "what the hell, I told you not this small").
--
-- Sample Game's HUD is not a kit screen: ChamberHud.luau sizes itself at RUNTIME from the screen. Round R2 put
-- `local HUD_SCALE, MIN_SCALE, MARGIN = 0.58, 0.3, 30` in its rescale(): every block at 0.58 of its 1080p design.
-- No spec, compile, gauge or preview ever saw it (card b6m2 dropped a gauge-size floor as hollow for exactly that
-- reason: the HUD never ran through kit/ui/gauge.py). This runs the HUD's OWN code instead:
--   1. the HUD's block helper (ChamberHud: `local function corner(name, anchor, size, inset, k)`), every call of it
--      in the file, then its resize function (`local function rescale()`) at each frame - each cut out of the file
--      where it stands (Luau's own compiler says where it ends) and run on stub instances. A block = a frame with a
--      UIScale in it; its size on screen = the frame's design size x the UIScale its resize gave it (x any scaled
--      ancestor's);
--   2. every block the reference names, against the reference's measured size (at the reference frame; at another
--      frame scaled with the screen's height when the reference says the HUD follows the height): under
--      floor x reference = FAIL.
-- What it cannot see: art made smaller inside an unchanged frame, a block the reference does not name, a HUD that
-- sizes itself without a UIScale (a block the reference names and the code never scales fails as "not measured").
--
-- The contract (a game-code HUD's size record): <root>assets/ui/huds/<Hud>.json
--   {
--     "hud": "ChamberHud",
--     "code": "<the HUD's .luau: absolute, or relative to the project root>",
--     "block": "corner", "resize": "rescale",     the HUD's own block helper and resize function (local functions)
--     "floor": 0.8, "floor_why": "<the owner's verdicts it comes from>",
--     "frames": [[1920, 1080], [1366, 768]],      where to measure (default: the reference frame)
--     "reference": {
--       "frame": [1920, 1080], "follows": "height" | "none",
--       "source": "<the still / sheet measured and the owner's words on it>",
--       "blocks": { "<frame Name>": { "size": [w, h], "ink": "<what the reference measured inside it>" } }
--     }
--   }
local fs = require("@lune/fs")
local luau = require("@lune/luau")
local serde = require("@lune/serde")

local HudSize = {}

-- ---------------------------------------------------------------------------------------------- reading the code

-- which bytes of `src` are CODE (not a comment, not a string): a name inside a comment is never a call
function HudSize.codeMask(src: string): { boolean }
	local n = #src
	local mask = table.create(n, true)
	local function mark(a: number, b: number)
		for k = a, math.min(b, n) do
			mask[k] = false
		end
	end
	local i = 1
	while i <= n do
		local c = string.sub(src, i, i)
		if c == "-" and string.sub(src, i + 1, i + 1) == "-" then
			local eq = string.match(src, "^%[(=*)%[", i + 2)
			if eq then -- --[[ a long comment ]] / --[==[ ... ]==]
				local _, e = string.find(src, "]" .. eq .. "]", i + 4 + #eq, true)
				mark(i, e or n)
				i = (e or n) + 1
			else -- -- a line comment
				local e = string.find(src, "\n", i, true) or (n + 1)
				mark(i, e - 1)
				i = e
			end
		elseif c == '"' or c == "'" or c == "`" then
			local j = i + 1
			while j <= n do
				local d = string.sub(src, j, j)
				if d == "\\" then
					j += 2
				elseif d == c or (d == "\n" and c ~= "`") then
					break
				else
					j += 1
				end
			end
			mark(i, j)
			i = j + 1
		elseif c == "[" and string.match(src, "^%[=*%[", i) then -- [[ a long string ]]
			local eq = string.match(src, "^%[(=*)%[", i) :: string
			local _, e = string.find(src, "]" .. eq .. "]", i + 2 + #eq, true)
			mark(i, e or n)
			i = (e or n) + 1
		else
			i += 1
		end
	end
	return mask
end

local function isWord(src: string, s: number, e: number): boolean
	return not string.match(string.sub(src, s - 1, s - 1), "[%w_]")
		and not string.match(string.sub(src, e + 1, e + 1), "[%w_]")
end

-- every start of `word` as a whole word in code, from `init`
local function wordsFrom(src: string, mask: { boolean }, word: string, init: number): { number }
	local out = {}
	while true do
		local s, e = string.find(src, word, init, true)
		if not s or not e then
			break
		end
		if mask[s] and isWord(src, s, e) then
			table.insert(out, s)
		end
		init = e + 1
	end
	return out
end

local function compiles(text: string): boolean
	return (pcall(luau.compile, text))
end

-- the text of `local function <name>(...) ... end` (or `local <name> = function(...) ... end`), where it starts, and
-- how many such definitions the code has (two = ambiguous: the check cannot know which one runs). The text runs from
-- its first byte to the first `end` at which it compiles on its own (an earlier `end` closes an inner block, so the
-- text before it never compiles)
function HudSize.definition(src: string, mask: { boolean }, name: string): (string?, number?, number)
	local starts: { { s: number, e: number } } = {}
	for _, pattern in { `local%s+function%s+{name}%s*%(`, `local%s+{name}%s*=%s*function%s*%(` } do
		local init = 1
		while true do
			local s, e = string.find(src, pattern, init)
			if not s or not e then
				break
			end
			if mask[s] and isWord(src, s, s + 4) then
				table.insert(starts, { s = s, e = e })
			end
			init = e + 1
		end
	end
	if #starts ~= 1 then
		return nil, if starts[1] then starts[1].s else nil, #starts
	end
	local s, e = starts[1].s, starts[1].e
	for _, at in wordsFrom(src, mask, "end", e + 1) do
		local text = string.sub(src, s, at + 2)
		if compiles(text) then
			return text, s, 1
		end
	end
	return nil, s, 1 -- (it never closes: the file does not compile)
end

-- every call `<name>(...)` in code that is not its definition, nor a field or method of something else: its text and
-- where it stands (the text ends at the first `)` that makes `return <text>` compile)
function HudSize.calls(src: string, mask: { boolean }, name: string): { { text: string, at: number } }
	local out = {}
	for _, s in wordsFrom(src, mask, name, 1) do
		local before = string.match(string.sub(src, math.max(1, s - 40), s - 1), "([^%s]*)%s*$") or ""
		local open = string.match(src, "^%s*()%(", s + #name)
		if
			open
			and mask[open :: number]
			and not string.match(before, "[%.:]$")
			and not string.match(before, "function$")
		then
			local init = open :: number
			while true do
				local p = string.find(src, ")", init, true)
				if not p then
					break
				end
				if mask[p] then
					local text = string.sub(src, s, p)
					if compiles("return " .. text) then
						table.insert(out, { text = text, at = s })
						break
					end
				end
				init = p + 1
			end
		end
	end
	return out
end

-- which top-level function each byte is in (0 = the module's own scope): a function that starts at column 0 (`function
-- Hud:create(`, `local function x(`) runs to the next `end` at column 0 - how HUD code is laid out. A value declared
-- inside one function is not seen from another
function HudSize.scopes(src: string): (number) -> number
	local ranges: { { a: number, b: number } } = {}
	local at, open = 1, nil :: number?
	for line in string.gmatch(src .. "\n", "([^\n]*)\n") do
		if not open and (string.match(line, "^function[%s%(]") or string.match(line, "^local%s+function%s")) then
			open = at
		elseif open and string.match(line, "^end[%s%),;]*$") then
			table.insert(ranges, { a = open :: number, b = at + #line })
			open = nil
		end
		at += #line + 1
	end
	return function(pos: number): number
		for i, r in ranges do
			if pos >= r.a and pos <= r.b then
				return i
			end
		end
		return 0
	end
end

-- the names the code ASSIGNS anywhere outside their `local` declaration (`HUD_SCALE = 0.58` in an if or a callback,
-- `s *= 0.5`): their declared value is not what runs, so they are no constants (a table key `{ W = 1, H = 2 }` and a
-- field `x.W = 1` are not assignments of W)
function HudSize.reassigned(src: string, mask: { boolean }): { [string]: boolean }
	-- the innermost open bracket at every code byte, and the code byte before each one (comments and spaces skipped)
	local inner: { string? } = {}
	local prevCode: { string } = {}
	local stack: { string } = {}
	local last = ""
	for i = 1, #src do
		local c = string.sub(src, i, i)
		inner[i] = stack[#stack]
		prevCode[i] = last
		if mask[i] then
			if c == "{" or c == "(" or c == "[" then
				table.insert(stack, c)
			elseif c == "}" or c == ")" or c == "]" then
				table.remove(stack)
			end
			if not string.match(c, "%s") then
				last = c
			end
		end
	end
	local out: { [string]: boolean } = {}
	local init = 1
	while true do
		local s, e, name = string.find(src, "([%a_][%w_]*)", init)
		if not s or not e then
			break
		end
		init = e + 1
		if not mask[s] or string.match(string.sub(src, s - 1, s - 1), "[%w_%.:]") then
			continue
		end
		-- a key of a table constructor: directly inside braces, first in the constructor or after a separator (a
		-- function body inside the braces or inside a call's parentheses is code, and its `W = 1` an assignment)
		if inner[s] == "{" and (prevCode[s] == "{" or prevCode[s] == "," or prevCode[s] == ";") then
			continue
		end
		-- `=` or a compound `+= -= *= /= //= %= ^= ..=`, never `==`
		local _, opEnd, op = string.find(src, "^%s*([%+%-%*/%%%^%.]*)=", e + 1)
		local assigns = false
		if opEnd and string.sub(src, opEnd + 1, opEnd + 1) ~= "=" then
			assigns = op == ""
				or op == "+"
				or op == "-"
				or op == "*"
				or op == "/"
				or op == "//"
				or op == "%"
				or op == "^"
				or op == ".."
		end
		if not assigns then
			-- one name of `a, b = ...`: the statement's first name list ends in `=`
			local rest = string.match(src, "^%s*,%s*[%a_][%w_%s,]*()=[^=]", e + 1)
			assigns = rest ~= nil
		end
		if assigns then
			-- a declaration (`local a, b =`, `for i =`) is not a reassignment
			local lineStart = (string.find(string.sub(src, 1, s), "\n[^\n]*$") or 0) + 1
			local before = string.sub(src, lineStart, s - 1)
			local declared = string.match(before, "local%s+[%a_][%w_%s,]*$")
				or string.match(before, "^%s*local%s+$")
				or string.match(before, "for%s+[%a_][%w_%s,]*$")
				or string.match(before, "for%s+$")
			if not declared then
				out[name :: string] = true
			end
		end
	end
	return out
end

-- the plain values the code names - `local VW, VH = 1000, 470`, `local DT_VERTICAL = true`,
-- `local HUD_SCALE, MIN_SCALE, MARGIN = 0.58, 0.3, 30` - numbers and booleans, by where they are declared and in which
-- top-level function (the nearest one before a use, in the same function or the module, wins; `local W = self.armsW`
-- is not a value and is skipped; a name the code reassigns anywhere is no constant at all)
function HudSize.constants(src: string, mask: { boolean }): { { at: number, name: string, value: any, scope: number } }
	local out: { { at: number, name: string, value: any, scope: number } } = {}
	local scopeOf = HudSize.scopes(src)
	local reassigned = HudSize.reassigned(src, mask)
	local function envOf(): { [string]: any }
		local env: { [string]: any } = { math = math }
		for _, c in out do
			env[c.name] = c.value
		end
		return env
	end
	local at = 1
	for line in string.gmatch(src .. "\n", "([^\n]*)\n") do
		local lineAt = at
		at += #line + 1
		local lead, names, rhsAt = string.match(line, "^(%s*)local%s+([%a_][%w_%s,]*)=()")
		if not lead or not mask[lineAt + #lead] or string.sub(line, rhsAt :: number, rhsAt :: number) == "=" then
			continue
		end
		-- the right side up to the first byte that is not code (a trailing comment)
		local rhsEnd = #line
		for k = rhsAt :: number, #line do
			if not mask[lineAt + k - 1] then
				rhsEnd = k - 1
				break
			end
		end
		local rhs = string.match(string.sub(line, rhsAt :: number, rhsEnd), "^%s*(.-)%s*$") or ""
		if rhs == "" then
			continue
		end
		local okLoad, chunk = pcall(luau.load, "return " .. rhs, { environment = envOf(), debugName = "constant" })
		if not okLoad then
			continue
		end
		local okRun, values = pcall(function()
			return table.pack((chunk :: any)())
		end)
		if not okRun then
			continue
		end
		local i = 0
		for nameText in string.gmatch(names :: string, "[%a_][%w_]*") do
			i += 1
			local v = (values :: any)[i]
			if (type(v) == "number" or type(v) == "boolean") and not reassigned[nameText] then
				table.insert(out, { at = lineAt, name = nameText, value = v, scope = scopeOf(lineAt) })
			end
		end
	end
	return out
end

-- ---------------------------------------------------------------------------------------------- the stub world

local V2 = {}
V2.__index = V2
local function v2(x: number?, y: number?): any
	return setmetatable({ X = x or 0, Y = y or 0 }, V2)
end
V2.__add = function(a, b)
	return v2(a.X + b.X, a.Y + b.Y)
end
V2.__sub = function(a, b)
	return v2(a.X - b.X, a.Y - b.Y)
end
V2.__mul = function(a, b)
	if type(a) == "number" then
		return v2(a * b.X, a * b.Y)
	elseif type(b) == "number" then
		return v2(a.X * b, a.Y * b)
	end
	return v2(a.X * b.X, a.Y * b.Y)
end
V2.__div = function(a, b)
	if type(b) == "number" then
		return v2(a.X / b, a.Y / b)
	end
	return v2(a.X / b.X, a.Y / b.Y)
end
V2.__unm = function(a)
	return v2(-a.X, -a.Y)
end

local function udim(s: number?, o: number?): any
	return { Scale = s or 0, Offset = o or 0 }
end
local function udim2(xs: number?, xo: number?, ys: number?, yo: number?): any
	local x, y = udim(xs, xo), udim(ys, yo)
	return { X = x, Y = y, Width = x, Height = y }
end

local SIGNAL = {
	Connect = function()
		return { Disconnect = function() end }
	end,
	Once = function()
		return { Disconnect = function() end }
	end,
}

-- an instance: properties in a backing table, so every write is seen (the resize's UIScale.Scale writes)
local function makeWorld()
	local world = { made = {} :: { any }, backing = {} :: { [any]: any }, written = {} :: { [any]: boolean } }
	local function instance(class: string, props: { [any]: any }?, parent: any?): any
		local backing: { [any]: any } = { ClassName = class, Name = class, Parent = parent }
		for k, v in props or {} do
			backing[k] = v
		end
		local inst
		inst = setmetatable({}, {
			__index = function(_, k)
				local v = backing[k]
				if v ~= nil then
					return v
				elseif k == "GetPropertyChangedSignal" or k == "GetAttributeChangedSignal" then
					return function()
						return SIGNAL
					end
				elseif k == "GetAttribute" or k == "FindFirstChild" or k == "FindFirstChildOfClass" then
					return function()
						return nil
					end
				elseif k == "IsA" then
					return function(_, c)
						return backing.ClassName == c
					end
				end
				return nil
			end,
			__newindex = function(_, k, v)
				backing[k] = v
				if k == "Scale" then
					world.written[inst] = true
				end
			end,
		})
		world.backing[inst] = backing
		table.insert(world.made, inst)
		return inst
	end
	world.instance = instance
	world.gui = instance("ScreenGui", { Name = "HudSizeProbe", AbsoluteSize = v2(1920, 1080) })
	world.camera = instance("Camera", { ViewportSize = v2(1920, 1080) })
	-- the HUD's own object: its screen as `self.gui` (a resize guarded by `if not self.gui then return end` runs)
	world.self = { gui = world.gui }
	world.player = {
		GetAttribute = function()
			return nil -- the player's own settings at their defaults (a HudScale setting = 1)
		end,
		GetAttributeChangedSignal = function()
			return SIGNAL
		end,
		WaitForChild = function()
			return instance("PlayerGui")
		end,
	}
	return world
end

local function permissiveEnum(): any
	return setmetatable({}, {
		__index = function(_, kind)
			return setmetatable({}, {
				__index = function(_, item)
					return `Enum.{kind}.{item}`
				end,
			})
		end,
	})
end

-- the names the HUD's own code reads, in a sandbox: the stubs, the shared world, the constants declared before `at`
local function envAt(
	world: any,
	constants: { { at: number, name: string, value: any, scope: number } },
	at: number,
	scope: number
): { [string]: any }
	local env: { [string]: any } = {
		math = math,
		string = string,
		table = table,
		tonumber = tonumber,
		tostring = tostring,
		type = type,
		typeof = function(v: any): string
			if type(v) == "table" and getmetatable(v) == V2 then
				return "Vector2"
			end
			return type(v)
		end,
		pairs = pairs,
		ipairs = ipairs,
		next = next,
		select = select,
		unpack = table.unpack,
		pcall = pcall,
		error = error,
		assert = assert,
		print = function() end,
		warn = function() end,
		Vector2 = {
			new = v2,
			zero = v2(0, 0),
			one = v2(1, 1),
		},
		UDim = { new = udim },
		UDim2 = {
			new = udim2,
			fromOffset = function(x: number?, y: number?)
				return udim2(0, x, 0, y)
			end,
			fromScale = function(x: number?, y: number?)
				return udim2(x, 0, y, 0)
			end,
		},
		Instance = {
			new = function(class: string, parent: any?)
				return world.instance(class, nil, parent)
			end,
		},
		Enum = permissiveEnum(),
		new = world.instance, -- (the HUD's own `new(class, props, parent)` helper)
		gui = world.gui,
		self = world.self,
		Players = { LocalPlayer = world.player },
		workspace = { CurrentCamera = world.camera },
		task = {
			spawn = function() end,
			defer = function() end,
			delay = function() end,
			wait = function()
				return 0
			end,
		},
	}
	for _, c in constants do
		-- declared before the use, in the module's own scope or in the use's own top-level function
		if c.at < at and (c.scope == 0 or c.scope == scope) then
			env[c.name] = c.value
		end
	end
	return env
end

local function load(text: string, env: { [string]: any }, debugName: string): (any, string?)
	local ok, fn = pcall(luau.load, text, { environment = env, debugName = debugName })
	if not ok then
		return nil, tostring(fn)
	end
	return fn, nil
end

local function lineOf(src: string, at: number): number
	local _, count = string.gsub(string.sub(src, 1, at), "\n", "")
	return count + 1
end

local function firstLine(err: any): string
	return (string.match(tostring(err), "^[^\n]*") or tostring(err))
end

-- ---------------------------------------------------------------------------------------------- measuring

export type Measured = { name: string, design: { number }, scale: number, size: { number }, written: boolean }

-- run the HUD's block helper, every call of it and its resize at each frame; returns per frame "WxH" the blocks
-- by name, or an error (the code could not be read or run), plus notes
function HudSize.measure(
	src: string,
	blockName: string,
	resizeName: string,
	frames: { { number } }
): ({ [string]: { [string]: Measured } }?, string?, { string })
	src = string.gsub(src, "\r\n", "\n") :: string
	local notes: { string } = {}
	local mask = HudSize.codeMask(src)
	local constants = HudSize.constants(src, mask)
	local scopeOf = HudSize.scopes(src)
	local world = makeWorld()
	-- the screen's other doors, kept in a local as HUD code does (`local cam = workspace.CurrentCamera` - a HUD sized
	-- from the camera's ViewportSize; `local player = Players.LocalPlayer`): the same stubs, by where they are named
	for _, alias in
		{
			{ "local%s+([%a_][%w_]*)%s*=%s*workspace%.CurrentCamera%f[^%w_]", world.camera },
			{ "local%s+([%a_][%w_]*)%s*=%s*game%.Workspace%.CurrentCamera%f[^%w_]", world.camera },
			{ "local%s+([%a_][%w_]*)%s*=%s*Players%.LocalPlayer%f[^%w_:]", world.player },
		}
	do
		local init = 1
		while true do
			local s, e, name = string.find(src, alias[1], init)
			if not s or not e then
				break
			end
			if mask[s] then
				table.insert(constants, { at = s, name = name, value = alias[2], scope = scopeOf(s) })
			end
			init = e + 1
		end
	end
	table.sort(constants, function(a, b)
		return a.at < b.at
	end)
	local function defError(kind: string, name: string, field: string, at: number?, count: number): string
		if count > 1 then
			return `the code defines "local function {name}(" {count} times: the check cannot tell which {kind} runs - give the HUD's one a name of its own and put it in the contract ("{field}")`
		elseif at then
			return `its {kind} "{name}" (line {lineOf(src, at)}) never closes: the file does not compile`
		end
		return `no "local function {name}(" in the code: name the HUD's {kind} in the contract ("{field}")`
	end

	local helperText, helperAt, helperCount = HudSize.definition(src, mask, blockName)
	if not helperText or not helperAt then
		return nil, defError("block helper", blockName, "block", helperAt, helperCount), notes
	end
	-- the lists the helper keeps its blocks in (`table.insert(self.corners, ...)`): made empty, as the HUD makes them
	for _, pattern in { "table%.insert%(%s*self%.([%a_][%w_]*)", "#self%.([%a_][%w_]*)" } do
		for field in string.gmatch(helperText, pattern) do
			world.self[field] = world.self[field] or {}
		end
	end
	local helperFn, helperErr =
		load(`{helperText}\nreturn {blockName}`, envAt(world, constants, helperAt, scopeOf(helperAt)), blockName)
	if not helperFn then
		return nil, `its block helper "{blockName}" does not load: {firstLine(helperErr)}`, notes
	end
	local okHelper, helper = pcall(helperFn)
	if not okHelper then
		return nil, `its block helper "{blockName}" does not load: {firstLine(helper)}`, notes
	end

	local calls = HudSize.calls(src, mask, blockName)
	if #calls == 0 then
		return nil, `the code never calls its block helper "{blockName}"`, notes
	end
	for _, call in calls do
		local env = envAt(world, constants, call.at, scopeOf(call.at))
		env[blockName] = helper
		local fn, err = load("return " .. call.text, env, `{blockName} call`)
		local okCall, callErr = false, err
		if fn then
			okCall, callErr = pcall(fn)
		end
		if not okCall then
			local label = string.match(call.text, '^[%w_]+%(%s*"([^"]*)"') or call.text
			table.insert(
				notes,
				`the block "{label}" (line {lineOf(src, call.at)}) could not be made: {firstLine(callErr)}`
			)
		end
	end

	local resizeText, resizeAt, resizeCount = HudSize.definition(src, mask, resizeName)
	if not resizeText or not resizeAt then
		return nil, defError("resize function", resizeName, "resize", resizeAt, resizeCount), notes
	end
	local resizeFn, resizeErr =
		load(`{resizeText}\nreturn {resizeName}`, envAt(world, constants, resizeAt, scopeOf(resizeAt)), resizeName)
	if not resizeFn then
		return nil, `its resize "{resizeName}" does not load: {firstLine(resizeErr)}`, notes
	end
	local okResize, resize = pcall(resizeFn)
	if not okResize then
		return nil, `its resize "{resizeName}" does not load: {firstLine(resize)}`, notes
	end

	-- every UIScale the helper made, its frame, and each frame's own scale as made (a block the resize never touches
	-- keeps it)
	local scales: { any } = {}
	local initial: { [any]: any } = {}
	local scaleOf: { [any]: any } = {} -- frame -> its UIScale
	for _, inst in world.made do
		local b = world.backing[inst]
		if b.ClassName == "UIScale" then
			table.insert(scales, inst)
			initial[inst] = b.Scale
			if b.Parent then
				scaleOf[b.Parent] = inst
			end
		end
	end
	if #scales == 0 then
		return nil, `its block helper "{blockName}" made no frame with a UIScale: nothing to measure`, notes
	end

	local out: { [string]: { [string]: Measured } } = {}
	for _, frame in frames do
		local w, h = frame[1], frame[2]
		local key = `{w}x{h}`
		world.backing[world.gui].AbsoluteSize = v2(w, h)
		world.backing[world.camera].ViewportSize = v2(w, h)
		world.written = {}
		for _, sc in scales do
			world.backing[sc].Scale = initial[sc]
		end
		local okRun, runErr = pcall(resize)
		if not okRun then
			-- whatever it was about to do after the crash (a shrink of the whole screen?) is unknown: nothing measured
			table.insert(notes, `{key}: the resize stopped: {firstLine(runErr)}`)
		elseif next(world.written) == nil then
			table.insert(
				notes,
				`{key}: the resize returned before it scaled any block (an early return on something the check cannot know?)`
			)
		end
		local blocks: { [string]: Measured } = {}
		for _, sc in scales do
			local frameInst = world.backing[sc].Parent
			local fb = world.backing[frameInst]
			if not fb then
				continue
			end
			local size = fb.Size
			local dw = if type(size) == "table" and type(size.X) == "table" then tonumber(size.X.Offset) or 0 else 0
			local dh = if type(size) == "table" and type(size.Y) == "table" then tonumber(size.Y.Offset) or 0 else 0
			-- the block's scale on screen: its own UIScale x every scaled ancestor's
			local s, node = 1, frameInst
			while node do
				local own = scaleOf[node]
				if own then
					s *= tonumber(world.backing[own].Scale) or 1
				end
				local nb = world.backing[node]
				node = nb and nb.Parent
			end
			local name = tostring(fb.Name)
			local m: Measured = {
				name = name,
				design = { dw, dh },
				scale = s,
				size = { dw * s, dh * s },
				-- measured only when the resize set this block's own scale in this frame and ran to its end: an early
				-- return or a crash leaves the scale it was made with, which says nothing about the screen
				written = okRun and world.written[sc] == true,
			}
			local had = blocks[name]
			if had then
				-- two blocks of one name (two branches of the code): the smaller one is the one measured
				if key == `{frames[1][1]}x{frames[1][2]}` then
					table.insert(notes, `two blocks are named "{name}": the smaller one on screen is measured`)
				end
				if m.size[1] * m.size[2] < had.size[1] * had.size[2] then
					blocks[name] = m
				end
			else
				blocks[name] = m
			end
		end
		out[key] = blocks
	end
	return out, nil, notes
end

-- ---------------------------------------------------------------------------------------------- the check

export type Result = {
	ok: boolean,
	summary: string,
	next_action: string?,
	blocks: { any },
	notes: { string },
}

local function r2(x: number): number
	return math.floor(x * 100 + 0.5) / 100
end

-- a ratio shown cut down to 2 places, never rounded up (a 0.7985 under a floor of 0.8 must not read "0.80")
local function cut(x: number): string
	return string.format("%.2f", math.floor(x * 100 + 1e-6) / 100)
end

local function px(v: { number }): string
	return `{math.floor(v[1] + 0.5)}x{math.floor(v[2] + 0.5)}`
end

local function isPair(v: any): boolean
	return type(v) == "table" and type(v[1]) == "number" and type(v[2]) == "number" and v[1] > 0 and v[2] > 0
end

-- the contract's problems (empty = well formed)
function HudSize.validate(contract: any): { string }
	local problems = {}
	if type(contract) ~= "table" then
		return { "the contract is not a JSON object" }
	end
	for _, field in { "block", "resize" } do
		if type(contract[field]) ~= "string" or not string.match(contract[field], "^[%a_][%w_]*$") then
			table.insert(problems, `"{field}": the name of the HUD's own local function`)
		end
	end
	if type(contract.floor) ~= "number" or contract.floor <= 0 or contract.floor > 1 then
		table.insert(problems, `"floor": a number in (0, 1] (a block draws at >= floor x its reference)`)
	end
	local ref = contract.reference
	if type(ref) ~= "table" or type(ref.blocks) ~= "table" or next(ref.blocks) == nil then
		table.insert(problems, `"reference.blocks": the reference's measured size of each block, by its frame name`)
	else
		for name, b in ref.blocks do
			if type(b) ~= "table" or not isPair(b.size) then
				table.insert(problems, `"reference.blocks.{name}.size": [w, h] in px at the reference frame`)
			end
		end
		if ref.frame ~= nil and not isPair(ref.frame) then
			table.insert(problems, `"reference.frame": [w, h] (default [1920, 1080])`)
		end
		if ref.follows ~= nil and ref.follows ~= "height" and ref.follows ~= "none" then
			table.insert(problems, `"reference.follows": "height" or "none"`)
		end
		if type(ref.source) ~= "string" or ref.source == "" then
			table.insert(problems, `"reference.source": the still / sheet measured and the owner's words on it`)
		end
	end
	if contract.frames ~= nil then
		if type(contract.frames) ~= "table" or #contract.frames == 0 then
			table.insert(problems, `"frames": a list of [w, h]`)
		else
			for i, f in contract.frames do
				if not isPair(f) then
					table.insert(problems, `"frames[{i}]": [w, h]`)
				end
			end
		end
	end
	return problems
end

-- check the HUD's code `src` against its contract; `where` names the code in the messages
function HudSize.check(contract: any, src: string, where: string): Result
	local problems = HudSize.validate(contract)
	local hud = if type(contract) == "table" and type(contract.hud) == "string" then contract.hud else "the HUD"
	if #problems > 0 then
		return {
			ok = false,
			summary = `hud size: {hud}'s contract is not usable - {table.concat(problems, "; ")}`,
			next_action = "fix the contract (kit/lib/hudsize.luau names every field)",
			blocks = {},
			notes = {},
		}
	end
	local ref = contract.reference
	local refFrame = ref.frame or { 1920, 1080 }
	local frames = contract.frames or { refFrame }
	local measured, err, notes = HudSize.measure(src, contract.block, contract.resize, frames)
	if not measured then
		return {
			ok = false,
			summary = `hud size: {hud} could not be measured from {where} - {err}`,
			next_action = `point the contract at the HUD's code and its own helper / resize names, or fix the code`,
			blocks = {},
			notes = notes,
		}
	end
	local rows, missing = {}, {}
	local worst: { [string]: any } = {} -- each block's smallest failing measure
	local under = 0
	local names = {}
	for name in ref.blocks do
		table.insert(names, name)
	end
	table.sort(names)
	for _, frame in frames do
		local key = `{frame[1]}x{frame[2]}`
		local k = if ref.follows == "none" then 1 else frame[2] / refFrame[2]
		for _, name in names do
			local want = ref.blocks[name].size
			local got = measured[key][name]
			if not got or not got.written then
				table.insert(missing, `{name} at {key}`)
				continue
			end
			local expected = { want[1] * k, want[2] * k }
			local ratio = math.min(got.size[1] / expected[1], got.size[2] / expected[2])
			local row = {
				block = name,
				frame = key,
				design = got.design,
				scale = r2(got.scale),
				size = { r2(got.size[1]), r2(got.size[2]) },
				reference = { r2(expected[1]), r2(expected[2]) },
				ratio = tonumber(cut(ratio)),
				ok = ratio >= contract.floor - 1e-9,
			}
			table.insert(rows, row)
			if not row.ok then
				under += 1
				if not worst[name] or ratio < worst[name].ratio then
					worst[name] = { ratio = ratio, size = got.size, expected = expected, key = key }
				end
			end
		end
	end
	local bad = {}
	for _, name in names do
		local w = worst[name]
		if w then
			table.insert(bad, `{name} {px(w.size)} px at {w.key} = {cut(w.ratio)} of its reference {px(w.expected)}`)
		end
	end
	if #missing > 0 then
		local made = {}
		for name in measured[`{frames[1][1]}x{frames[1][2]}`] or {} do
			table.insert(made, name)
		end
		table.sort(made)
		return {
			ok = false,
			summary = `hud size: {hud} - not measured: {table.concat(missing, ", ")} (the code's scaled blocks: {if #made
					> 0
				then table.concat(made, ", ")
				else "none"}){if #notes > 0 then " - " .. notes[1] else ""}`,
			next_action = `a block the reference names must be made by "{contract.block}" and scaled by "{contract.resize}" in {where}; renamed? re-measure the reference with the owner`,
			blocks = rows,
			notes = notes,
		}
	end
	if #bad > 0 then
		return {
			ok = false,
			summary = `hud size: {hud} draws too small on screen - {table.concat(bad, "; ")} ({under} of {#rows} block measures under the floor {contract.floor}; reference: {ref.source})`,
			next_action = `make every block >= {contract.floor} x its reference in {where} ({contract.resize}); a smaller HUD only on the owner's words, then re-measure the reference`,
			blocks = rows,
			notes = notes,
		}
	end
	local least = 1e9
	for _, row in rows do
		least = math.min(least, row.ratio)
	end
	return {
		ok = true,
		summary = `{hud}: every block >= {contract.floor} x its reference on screen ({#names} block(s) x {#frames} frame(s); the smallest at {cut(
			least
		)})`,
		next_action = nil,
		blocks = rows,
		notes = notes,
	}
end

-- ---------------------------------------------------------------------------------------------- the contracts

-- every HUD size contract in the project root and every games/<Name>/: <root>assets/ui/huds/*.json
function HudSize.contracts(): { string }
	local roots = { "" }
	if fs.isDir("games") then
		for _, g in fs.readDir("games") do
			if fs.isDir(`games/{g}`) then
				table.insert(roots, `games/{g}/`)
			end
		end
	end
	local out = {}
	for _, root in roots do
		local dir = `{root}assets/ui/huds`
		if fs.isDir(dir) then
			for _, f in fs.readDir(dir) do
				if string.sub(f, -5) == ".json" then
					table.insert(out, `{dir}/{f}`)
				end
			end
		end
	end
	table.sort(out)
	return out
end

-- read a contract and the code it names (`codeOverride` replaces it: a selftest's frozen file) and check them
function HudSize.run(contractPath: string, codeOverride: string?): Result
	local okRead, contract = pcall(function()
		return serde.decode("json", fs.readFile(contractPath))
	end)
	if not okRead then
		return {
			ok = false,
			summary = `hud size: cannot read the contract {contractPath}: {firstLine(contract)}`,
			next_action = "fix the JSON",
			blocks = {},
			notes = {},
		}
	end
	local code = codeOverride or (type(contract) == "table" and contract.code) or nil
	if type(code) ~= "string" or code == "" then
		return {
			ok = false,
			summary = `hud size: {contractPath} names no "code" (the HUD's .luau)`,
			next_action = `add "code": the path of the HUD's game code`,
			blocks = {},
			notes = {},
		}
	end
	if not fs.isFile(code) then
		return {
			ok = false,
			summary = `hud size: the HUD's code is not at {code} (named by {contractPath})`,
			next_action = "point the contract's \"code\" at the HUD's file (the game's own code may live outside this repo)",
			blocks = {},
			notes = {},
		}
	end
	return HudSize.check(contract, fs.readFile(code), code)
end

return HudSize

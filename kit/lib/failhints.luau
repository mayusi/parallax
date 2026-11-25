--!strict
-- failhints.luau — the lessons that match a failure, printed under it (2026-11-08, sprint 3: "lessons when a gate
-- fails"). A gate that fails names its problem in words; the failing lane's lessons ranked by those words
-- (kit/lib/vault.luau Vault.rank) show the two that match best - at the moment they are needed, not only at
-- kit start. A failure that keeps coming back asks every third time for the lesson that fixes it.
-- The words every failure says ("gate", "failed", "check", "error") match every lesson that mentions a gate: they are
-- left out of the query, and a generic summary ("<report>: <step> failed", Run.chain) is told apart by the end of the
-- failing output, which says WHAT failed.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Vault = require("./vault")

local FailHints = {}

-- the report file's first word -> the lane whose lessons answer it (a report no lane owns gets no hint)
FailHints.LANE_OF = {
	anim = "anim",
	vfx = "vfx",
	ui = "ui",
	world = "world",
	asset = "3d",
	models = "3d",
	cad = "3d",
	refs = "3d",
	study = "3d",
	sheet = "3d",
	sharpen = "3d",
	blockout = "3d",
	gen = "3d",
	grade = "3d",
	geo = "3d",
	optimize = "3d",
	judge = "3d",
	audio = "sfx",
	sfx = "sfx",
	sound = "sfx",
	playtest = "qa",
	system = "code",
	systems = "code",
	fuzz = "code",
	mutate = "code",
	net = "code",
}
FailHints.MIN_HITS = 2 -- a lesson must share two of the failure's words: one shared word is chance
FailHints.MIN_RELEVANCE = 0.5 -- and match at least half as well as the best lesson does
FailHints.SHOW = 2
FailHints.REPEAT = 3 -- every third time the same failure comes back, ask for its lesson
FailHints.FILE = ".verify/failures.json"
FailHints.KEEP = 300

-- what every gate failure says, as Vault.words spells it (lower case, a plural's "s" off), a traceback's own words
-- ("Traceback (most recent call last)", "raise ... Exception") and a JSON verdict's keys: no lesson is about these
FailHints.NOISE = {} :: { [string]: boolean }
for w in
	string.gmatch(
		[[fail failed failing failure gate check checked error exit code step output above fix fixe fixed rerun
command warning problem verify verified report json summary next action line file python luau traceback stderr
stdout result expected got test passed pass none true false nil null value see recent call last raise raised
exception stack status http]],
		"%S+"
	)
do
	FailHints.NOISE[w] = true
end

function FailHints.lane(file: string): string?
	local head = string.lower(string.match(file, "^(%a+)") or file)
	return FailHints.LANE_OF[head]
end

-- "<report>: <step> failed" (Run.chain's summary) names the step, not the problem
function FailHints.generic(summary: string): boolean
	return string.match(summary, "^[^:]+: [^:]+ failed$") ~= nil
end

-- the failing output without WHERE the code ran: a traceback's frame lines (Python 'File "...", line N', Lune
-- "Script '...', Line N", "[Stack Begin]"), an error's place ('[string "..."]:N:', "path:N:"; its message kept) and
-- absolute paths (a user's folders matched lessons through "user", "download", "local", "lib")
function FailHints.clean(text: string): string
	local out = {}
	for line in string.gmatch(string.gsub(text, "\r\n", "\n") .. "\n", "([^\n]*)\n") do
		if
			not string.match(line, '^%s*File ".-", line %d+')
			and not string.match(line, "^%s*Traceback %(")
			and not string.match(line, "^%s*%[Stack ")
			and not string.match(line, "^%s*Script '.-', Line %d+")
		then
			local l = string.gsub(line, '%[string ".-"%]:%d+:', " ")
			l = string.gsub(l, "[^%s\"'%(%)%[%]]+:%d+:", " ")
			l = string.gsub(l, "%a:[\\/][^%s\"']*", " ")
			l = string.gsub(l, "/%a/[^%s\"']*", " ")
			table.insert(out, l)
		end
	end
	return table.concat(out, "\n")
end

local function norm(s: string): string
	s = string.lower(s)
	s = string.gsub(s, "%S*%d%S*", "#") -- a number, a time, a hash, a temp name: one token
	s = string.gsub(s, "%s+", " ")
	return s
end

-- the last "summary" a JSON verdict in the output gives (the failing tool's own words for its problem), or nil
local function jsonSummary(text: string): string?
	local found: string? = nil
	for s in string.gmatch(text, '"summary"%s*:%s*"(.-[^\\])"') do
		found = s
	end
	return found
end

-- a failure's identity across runs: its words with the numbers taken out ("0.84 < 0.9" and "0.86 < 0.9" are one);
-- a generic summary adds WHAT failed - the failing tool's own JSON summary when it printed one (its fixed next_action
-- after it says nothing), else the end of its output
function FailHints.signature(file: string, summary: string, tails: string?): string
	local s = string.sub(norm(summary), 1, 160)
	if FailHints.generic(summary) then
		local raw = FailHints.clean(tails or "")
		local js = jsonSummary(raw)
		if js then
			s ..= "|" .. string.sub(norm(js), 1, 200)
		else
			local t = norm(raw)
			s ..= "|" .. string.sub(t, math.max(1, #t - 239))
		end
	end
	return `{file}|{s}`
end

-- the words to rank the lane's lessons by: the problem (the "world check:" lead-in names the command) and the end of
-- the failing output, without the words every failure says and without the lane's own name (every lesson of the
-- world lane says "world")
function FailHints.query(summary: string, tails: string?, dept: string?): string
	local problem = string.gsub(summary, "^[%w%s%-]+:%s*", "", 1)
	local t = FailHints.clean(tails or "")
	local keep = {}
	for _, w in Vault.words(problem .. " " .. string.sub(t, math.max(1, #t - 799))) do
		if not FailHints.NOISE[w] and w ~= dept then
			table.insert(keep, w)
		end
	end
	return table.concat(keep, " ")
end

-- how many times this failure was seen (this one included); the store keeps the KEEP most recently seen
local function count(key: string): number
	local store: { [string]: any } = {}
	if fs.isFile(FailHints.FILE) then
		local ok, j = pcall(serde.decode, "json" :: any, fs.readFile(FailHints.FILE))
		if ok and type(j) == "table" then
			store = j
		end
	end
	local prev = store[key]
	local n = ((if type(prev) == "table" then tonumber(prev.n) else tonumber(prev)) or 0) + 1
	store[key] = { n = n, at = os.time() }
	local keys = {}
	for k in store do
		if k ~= key then
			table.insert(keys, k)
		end
	end
	if #keys >= FailHints.KEEP then
		local function at(k: string): number
			local v = store[k]
			return if type(v) == "table" then tonumber(v.at) or 0 else 0
		end
		table.sort(keys, function(a, b)
			return at(a) < at(b)
		end)
		for i = 1, #keys - FailHints.KEEP + 1 do
			store[keys[i]] = nil
		end
	end
	pcall(fs.writeFile, FailHints.FILE, serde.encode("json", store, true))
	return n
end

function FailHints.lines(file: string, summary: string, tails: string?): { string }
	local dept = FailHints.lane(file)
	-- a report ABOUT the lessons (kit world lessons: answers missing) is answered by its own sheet, not by more lessons
	if not dept or string.find(file, "lessons", 1, true) then
		return {}
	end
	local out = {}
	local query = FailHints.query(summary, tails, dept)
	local ok, ranked = pcall(Vault.rank, dept, query, { today = Vault.today() })
	if query ~= "" and ok and type(ranked) == "table" then
		local counts = Vault.lessonCounts()
		for _, r in ranked :: { Vault.Ranked } do
			if #out >= FailHints.SHOW + 1 then
				break
			end
			-- relevance is scaled to the best match: a second lesson far below the first is noise, not a hint
			if r.relevance >= FailHints.MIN_RELEVANCE and r.hits >= FailHints.MIN_HITS and r.evidence > -1 then
				if #out == 0 then
					table.insert(
						out,
						`--- lessons that match this failure ({dept}; kit lessons {dept} <words> for more):`
					)
				end
				table.insert(out, "  " .. Vault.rankedLine(r, counts, false, 220))
			end
		end
	end
	local n = count(FailHints.signature(file, summary, tails))
	if n >= FailHints.REPEAT and n % FailHints.REPEAT == 0 then
		table.insert(
			out,
			`--- this failure came back {n} times: write what fixes it once, so the next session meets it here: lune run kit lesson {dept} "<what fixes it>" --gist "<the fix in one line>"`
		)
	end
	return out
end

return FailHints

--!strict
-- answers.luau — a lane answers its lessons BEFORE it builds (2026-11-08, sprint 3: the world pilot of the 3D study's
-- lesson gate, kit/tools/study.py). The lessons ranked for the piece (kit/lib/vault.luau Vault.rank) become a sheet;
-- the session answers each lesson to answer (the first MUST that share at least MIN_HITS of the piece's words) -
-- "- <id>: how this piece applies it" or "- skip <id>: why it does not apply", at least WORDS words; check() names what
-- is missing; record() keeps the applied ones as NAMED citations, so the owner's verdict on the piece credits or
-- blames each at full weight (and the replay test gets real labels). The format is the 3D study's, so one session
-- reads both the same way.
-- The lessons to answer and the text that passed live in board/answers.json, outside the sheet: deleting a comment
-- from the sheet drops no lesson, and the plan (kit/world/plan.py) reads "done" only for the very text that passed
-- here - one check, in one place.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Vault = require("./vault")

local Answers = {}

Answers.MUST = 5
Answers.SHOW = 8
Answers.WORDS = 6
Answers.MIN_HITS = 2 -- a lesson to answer shares two of the piece's words: one is chance, none is only its date
Answers.RECORD = nil :: string? -- a spec points it at a temp file

local ID = "(L%-[%w]+%-%x+)"

function Answers.recordPath(): string
	return Answers.RECORD or "board/answers.json"
end

-- a sheet's key in the record: its project-relative path, "/" separated (kit/world/plan.py builds the same)
function Answers.key(path: string): string
	local k = string.gsub(path, "\\", "/")
	k = string.gsub(k, "^%./", "")
	return k
end

local function loadRecord(): { [string]: any }
	local p = Answers.recordPath()
	if fs.isFile(p) then
		local ok, j = pcall(serde.decode, "json" :: any, fs.readFile(p))
		if ok and type(j) == "table" then
			return j
		end
	end
	return {}
end

local function saveRecord(all: { [string]: any })
	local p = Answers.recordPath()
	local dir = string.match(p, "^(.*)/[^/]*$")
	if dir and dir ~= "" and not fs.isDir(dir) then
		fs.writeDir(dir)
	end
	fs.writeFile(p, serde.encode("json", all, true) .. "\n")
end

-- the record of one sheet: { dept, piece, must, answered = <digest of the text that passed>, applied, skipped, date }
function Answers.entry(path: string): { [string]: any }?
	local e = loadRecord()[Answers.key(path)]
	return if type(e) == "table" then e else nil
end

local function wordCount(s: string): number
	local n = 0
	for _ in string.gmatch(s, "%S+") do
		n += 1
	end
	return n
end

local function oneLine(s: string, max: number): string
	local t = string.gsub(string.gsub(s, "%-%-+>", "->"), "%s+", " ")
	t = string.gsub(t, "^ ", "")
	if (utf8.len(t) or #t) > max then
		t = string.sub(t, 1, (utf8.offset(t, max - 2) or max - 2) - 1) .. "..."
	end
	return t
end

-- the sheet for a piece: the lessons ranked for it by its own words (a flagged lesson never, one sharing no word
-- never); the first MUST sharing MIN_HITS words are the ones to answer, the rest optional.
-- -> the text, every listed id, the ids to answer
function Answers.sheet(
	dept: string,
	piece: string,
	command: string,
	today: string?,
	routeWords: string?
): (string, { string }, { string })
	local family = require("./families").ofPiece(dept, piece)
	local query = Vault.queryFor(dept, piece)
	if routeWords and routeWords ~= "" then -- (the piece's route: the lessons about how it is made rank in too)
		query ..= " " .. routeWords
	end
	local ranked = Vault.rank(dept, query, { today = today or Vault.today(), family = family })
	local must: { Vault.Ranked }, optional: { Vault.Ranked } = {}, {}
	for _, r in ranked do
		if r.evidence > -1 and r.hits >= 1 then
			if r.hits >= Answers.MIN_HITS and #must < Answers.MUST then
				table.insert(must, r)
			elseif #optional < Answers.SHOW then
				table.insert(optional, r)
			end
		end
	end
	while #must + #optional > Answers.SHOW and #optional > 0 do
		table.remove(optional)
	end
	local lines = {
		`# {piece} - the {dept} lessons, answered before building ({command})`,
		"",
		"## Lessons applied",
		"",
		if #must > 0
			then `(the vault's {dept} lessons ranked for this piece by its own words. Answer each ANSWER lesson ({#must}): \`- <id>: how this piece applies it\`, or \`- skip <id>: why it does not apply\` (at least {Answers.WORDS} words each); an optional one may be applied the same way. {command} checks them and records the applied ones on this piece: the owner's verdict on it credits or flags each)`
			else `(no {dept} lesson shares {Answers.MIN_HITS} words with this piece's own words. Apply an optional one (\`- <id>: how this piece applies it\`), or say why none applies: \`- none: <why>\` (at least {Answers.WORDS} words). {command} checks it)`,
		"",
	}
	local ids, mustIds = {}, {}
	for _, r in must do
		table.insert(ids, r.id)
		table.insert(mustIds, r.id)
		table.insert(lines, `<!-- ANSWER {r.id}: {oneLine(Vault.gist(r.note), 220)} -->`)
	end
	for _, r in optional do
		table.insert(ids, r.id)
		table.insert(lines, `<!-- optional {r.id}: {oneLine(Vault.gist(r.note), 220)} -->`)
	end
	table.insert(lines, "")
	for _, id in mustIds do
		table.insert(lines, `- {id}: <answer>`)
	end
	if #mustIds == 0 then
		table.insert(lines, "- none: <why no lesson of this lane applies to this piece>")
	end
	return table.concat(lines, "\n") .. "\n", ids, mustIds
end

-- a new sheet: its lessons to answer go in the record (and any answer of an older sheet at that path goes out)
function Answers.start(path: string, dept: string, piece: string, must: { string }, route: { string }?)
	local all = loadRecord()
	all[Answers.key(path)] = { dept = dept, piece = piece, must = must, date = Vault.today(), route = route }
	saveRecord(all)
end

-- a text as compared for copies: lower case, only its letters and digits
local function norm(s: string): string
	local t = string.gsub(string.lower(s), "[^%w]+", " ")
	return (string.gsub(string.gsub(t, "^ +", ""), " +$", ""))
end

export type Checked = { problems: { string }, must: { string }, applied: { string }, skipped: { string } }

-- `path`: the sheet's path - its lessons to answer come from the record too, never only from the sheet's comments
function Answers.check(text: string, dept: string, path: string?): Checked
	local live: { [string]: boolean } = {}
	local gistOf: { [string]: string } = {}
	local retired = Vault.supersededSet()
	for _, n in Vault.notes(dept, "lessons") do
		if not retired[string.lower(n.rel)] then
			live[Vault.lessonId(n)] = true
			gistOf[Vault.lessonId(n)] = Vault.gist(n)
		end
	end
	local counts = Vault.lessonCounts()
	-- the lessons to answer: the record's and any ANSWER comment's; one retired since needs no answer
	local must: { string } = {}
	local mustSet: { [string]: boolean } = {}
	local function want(id: any)
		if type(id) == "string" and live[id] and not mustSet[id] then
			mustSet[id] = true
			table.insert(must, id)
		end
	end
	-- a rerouted sheet: its answers for an earlier route sit under "## Earlier answers", kept to read - never counted,
	-- and an answer copied from them word for word does not count either (say how the NEW route applies it)
	local earlier: { [string]: { [string]: boolean } } = {}
	local cut = string.find(text, "\n## Earlier answers", 1, true)
	if cut then
		for line in string.gmatch(string.sub(text, cut + 1) .. "\n", "([^\n]*)\n") do
			local id, said = string.match(line, "^%s*%-%s*" .. ID .. "%s*:%s*(.*)$")
			if not id then
				id, said = string.match(line, "^%s*%-%s*[Ss]kip%s+" .. ID .. "%s*:%s*(.*)$")
			end
			if id and said then
				earlier[id] = earlier[id] or {}
				earlier[id][norm(said)] = true
			end
		end
		text = string.sub(text, 1, cut)
	end
	local function copied(id: string, said: string): boolean
		return earlier[id] ~= nil and earlier[id][norm(said)] == true
	end
	local e = if path then Answers.entry(path) else nil
	if e and type(e.must) == "table" then
		for _, id in e.must do
			want(id)
		end
	end
	for id in string.gmatch(text, "<!%-%-%s*ANSWER%s+" .. ID) do
		want(id)
	end
	local problems, applied, skipped, answered = {}, {}, {}, {}
	local named: { [string]: boolean } = {} -- a lesson already named in a problem: one message per lesson
	local noneSaid = false
	for line in string.gmatch(string.gsub(text, "\r\n", "\n") .. "\n", "([^\n]*)\n") do
		local sid, why = string.match(line, "^%s*%-%s*[Ss]kip%s+" .. ID .. "%s*:%s*(.*)$")
		if sid then
			if wordCount(why) < Answers.WORDS or string.find(why, "<answer>", 1, true) then
				named[sid] = true
				table.insert(
					problems,
					`skip {sid} needs why it does not apply to this piece (>= {Answers.WORDS} words)`
				)
			elseif copied(sid, why) then
				named[sid] = true
				table.insert(
					problems,
					`skip {sid} repeats its answer for the earlier route word for word: say why it does not apply to the NEW route`
				)
			else
				answered[sid] = true
				table.insert(skipped, sid)
			end
		else
			local id, how = string.match(line, "^%s*%-%s*" .. ID .. "%s*:%s*(.*)$")
			if id then
				local k = counts[id]
				if not live[id] then
					named[id] = true
					table.insert(problems, `{id} is no live {dept} lesson (retired, or a typo)`)
				elseif k and k.flagged then
					named[id] = true
					table.insert(
						problems,
						`{id} is flagged (the owner's verdicts went against the pieces it was used on): skip it with why, or apply another`
					)
				elseif wordCount(how) < Answers.WORDS or string.find(how, "<answer>", 1, true) then
					named[id] = true
					table.insert(problems, `{id} needs how this piece applies it (>= {Answers.WORDS} words)`)
				elseif copied(id, how) then
					named[id] = true
					table.insert(
						problems,
						`{id} repeats its answer for the earlier route word for word: say how the NEW route applies it`
					)
				else
					answered[id] = true
					table.insert(applied, id)
				end
			end
			local none = string.match(line, "^%s*%-%s*[Nn]one%s*:%s*(.*)$")
			if none and wordCount(none) >= Answers.WORDS and not string.find(none, "<", 1, true) then
				noneSaid = true
			end
		end
	end
	for _, id in must do
		if not answered[id] and not named[id] then
			table.insert(
				problems,
				`{id} is not answered yet ("{oneLine(gistOf[id] or "", 120)}"): apply it, or skip it with a reason`
			)
		end
	end
	if #must == 0 and #applied == 0 and #skipped == 0 and not noneSaid then
		table.insert(problems, "no lesson answered: answer the sheet, or write `- none: <why none applies>`")
	end
	return { problems = problems, must = must, applied = applied, skipped = skipped }
end

-- the sheet passed check(): the record keeps this text's digest (the plan reads "done" for this text only)
function Answers.passed(path: string, dept: string, piece: string, text: string, r: Checked)
	local all = loadRecord()
	local key = Answers.key(path)
	local e = if type(all[key]) == "table" then all[key] else {}
	local digest = Vault.digest(text)
	if e.answered == digest then
		return
	end
	e.dept, e.piece = dept, piece
	e.must = r.must
	e.answered = digest
	e.applied, e.skipped = r.applied, r.skipped
	e.date = Vault.today()
	all[key] = e
	saveRecord(all)
end

-- the applied lessons as NAMED citations on the piece - once per set of answers (checking again adds nothing)
function Answers.record(dept: string, piece: string, applied: { string }, by: string?): boolean
	local kind = Vault.KIND_OF_DEPT[dept]
	if not kind or #applied == 0 then
		return false
	end
	local want = table.clone(applied)
	table.sort(want)
	local key = table.concat(want, ",")
	for _, c in Vault.citations() do
		if
			type(c) == "table"
			and c.dept == dept
			and string.lower(tostring(c.name or "")) == string.lower(piece)
			and not c.served
			and type(c.lessons) == "table"
		then
			local have = table.clone(c.lessons)
			table.sort(have)
			if table.concat(have, ",") == key then
				return false
			end
		end
	end
	return (Vault.cite(kind, piece, applied, by))
end

return Answers

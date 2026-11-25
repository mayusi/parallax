-- vault.luau — the kit's knowledge VAULT: Obsidian-compatible markdown (YAML frontmatter + [[wikilinks]], no plugin
-- syntax) the kit WRITES and every harness reads. One note per lesson, one note per owner verdict, a graveyard of
-- rejected routes and a golden set per department; `kit status` / `kit new` print a department's page within a
-- token budget. The owner opens the folder in Obsidian as a viewer; the kit never depends on Obsidian.
--   kit/knowledge/vault/<dept>/{index.md, lessons/, verdicts/, graveyard.md, golden.md}   + shared/
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Config = require("./config")

local Vault = {}

Vault.ROOT = "kit/knowledge/vault"

-- departments = the kit's lesson areas (kit/cmd/learn.luau Learn.AREAS) + shared
Vault.DEPTS = { "3d", "vfx", "sfx", "ui", "world", "anim", "code", "qa", "kit", "shared" }
Vault.TITLES = {
	["3d"] = "3D models",
	vfx = "VFX",
	sfx = "sound",
	ui = "UI",
	world = "world",
	anim = "animation",
	code = "systems (gameplay code)",
	qa = "QA",
	kit = "the kit itself",
	shared = "shared infrastructure",
}
-- `kit verdict <kind>` -> the department; aliases the owner uses in words
Vault.DEPT_OF_KIND = {
	asset = "3d",
	model = "3d",
	vfx = "vfx",
	effect = "vfx",
	screen = "ui",
	ui = "ui",
	sound = "sfx",
	sfx = "sfx",
	world = "world",
	anim = "anim",
	animation = "anim",
	system = "code",
	systems = "code",
	code = "code",
	playtest = "qa",
	qa = "qa",
	kit = "kit",
}
Vault.ALIAS = { sound = "sfx", systems = "code", ["3D"] = "3d", animation = "anim" }
-- the newest live rules a short page (kit start) shows; the rest are named with the --full command
Vault.RULES_SHORT = 6
-- characters of the department's record (its LAST VERDICTS header and first rows) a short page keeps in its budget:
-- fewer rules are shown before the record is cut (Vault.page)
Vault.RECORD_ROOM = 400

-- is this verdict the OWNER's own judgement? Yes unless a model inferred it - except a WORD the owner gave (the anim
-- lane's "loved" / "horrible": the word is theirs, only its number is mapped), which counts as theirs
function Vault.ownersOwn(front: { [string]: any }): boolean
	return front.source ~= "inferred" or (type(front.word) == "string" and front.word ~= "")
end

-- the owner's Keep / Redo: a DIRECTION without a number (the owner, 2026-11-08: "Keep / Redo has no number, is never
-- averaged, and never counts toward golden"). For crediting lessons Keep counts as a success and Redo as a failure.
Vault.DIRECTIONS = { keep = 1, redo = -1 } :: { [string]: number }

function Vault.direction(front: { [string]: any }): string?
	local d = front.direction
	return if type(d) == "string" and Vault.DIRECTIONS[d] then d else nil
end

-- what a verdict says about the piece: 1 a success (7+ or Keep), -1 a failure (3 or less or Redo), 0 counted with no
-- credit either way (4-6), nil when it judges nothing (words with neither a number nor a direction)
function Vault.polarity(front: { [string]: any }): number?
	local s = tonumber(front.score)
	if s then
		return if s >= 7 then 1 elseif s <= 3 then -1 else 0
	end
	local d = Vault.direction(front)
	return if d then Vault.DIRECTIONS[d] else nil
end

-- how a verdict reads in a list: "7.5/10", "Keep", "Redo" or "(no number)"
function Vault.said(front: { [string]: any }): string
	if front.score ~= nil then
		return `{front.score}/10`
	end
	local d = Vault.direction(front)
	return if d == "keep" then "Keep" elseif d == "redo" then "Redo" else "(no number)"
end

export type Front = { [string]: any }
export type Note = { path: string, rel: string, front: Front, body: string }

function Vault.dept(name: string?): string?
	if not name then
		return nil
	end
	local d = Vault.ALIAS[name] or Vault.DEPT_OF_KIND[name] or name
	return if table.find(Vault.DEPTS, d) then d else nil
end

function Vault.dir(dept: string, sub: string?): string
	return `{Vault.ROOT}/{dept}` .. (if sub then "/" .. sub else "")
end

function Vault.exists(): boolean
	return fs.isDir(Vault.ROOT)
end

-- ------------------------------------------------------------ slugs, dates, tokens
function Vault.slug(text: string): string
	local s = string.lower(text)
	s = string.gsub(s, "[^%w]+", "-")
	s = string.gsub(s, "^%-+", "")
	s = string.gsub(s, "%-+$", "")
	return if s == "" then "note" else string.sub(s, 1, 48)
end

function Vault.today(): string
	return os.date("!%Y-%m-%d")
end

-- a cheap token estimate (chars / 4): the budget is a ceiling, not a measurement
function Vault.tokens(text: string): number
	return math.ceil(#text / 4)
end

-- ------------------------------------------------------------ frontmatter
local function yamlScalar(v: any): string
	if type(v) == "number" then
		return tostring(v)
	elseif type(v) == "boolean" then
		return if v then "true" else "false"
	end
	local s = tostring(v)
	-- quote everything that is not a plain word so YAML never misreads a colon or a quote
	if string.match(s, "^[%w%-_%.]+$") then
		return s
	end
	s = string.gsub(s, "\\", "\\\\")
	s = string.gsub(s, '"', '\\"')
	s = string.gsub(s, "\n", " ")
	return `"{s}"`
end

-- fixed key order so notes diff cleanly; unknown keys after, sorted
local ORDER = {
	"kind",
	"area",
	"name",
	"score",
	"date",
	"build",
	"by",
	"source",
	"quoted_from",
	"vs",
	"supersedes",
	"superseded_by",
	"superseded_why",
	"tags",
	"links",
}

function Vault.frontmatter(front: Front): string
	local lines = { "---" }
	local done = {}
	local function emit(k: string)
		local v = front[k]
		if v == nil then
			return
		end
		if type(v) == "table" then
			local items = {}
			for _, item in v do
				table.insert(items, yamlScalar(item))
			end
			table.insert(lines, `{k}: [{table.concat(items, ", ")}]`)
		else
			table.insert(lines, `{k}: {yamlScalar(v)}`)
		end
		done[k] = true
	end
	for _, k in ORDER do
		emit(k)
	end
	local rest = {}
	for k in front do
		if not done[k] then
			table.insert(rest, k)
		end
	end
	table.sort(rest)
	for _, k in rest do
		emit(k)
	end
	table.insert(lines, "---")
	return table.concat(lines, "\n")
end

-- (front, body) or (nil, why)
function Vault.parse(text: string): (Front?, string)
	text = string.gsub(text, "\r\n", "\n")
	if string.sub(text, 1, 4) ~= "---\n" then
		return nil, "no frontmatter (the note must start with ---)"
	end
	local close = string.find(text, "\n---\n", 4, true)
	local last = false
	if not close then
		close = string.find(text, "\n---$", 4)
		last = true
	end
	if not close then
		return nil, "frontmatter never closes (a second --- line)"
	end
	local yaml = string.sub(text, 5, close)
	local body = if last then "" else string.gsub(string.sub(text, close + 5), "^\n+", "")
	local ok, front = pcall(serde.decode, "yaml" :: any, yaml)
	if not ok or type(front) ~= "table" then
		return nil, "frontmatter is not YAML: " .. tostring(front)
	end
	return front, body
end

-- ------------------------------------------------------------ writing
local function ensureDir(path: string)
	Config.ensureDir(path)
end

-- a unique path: <dir>/<slug>.md, then <slug>-2.md, -3.md ...
function Vault.unique(dir: string, slug: string): string
	local path = `{dir}/{slug}.md`
	local n = 2
	while fs.isFile(path) do
		path = `{dir}/{slug}-{n}.md`
		n += 1
	end
	return path
end

function Vault.write(path: string, front: Front, body: string): string
	local parent = string.match(path, "^(.*)/[^/]+$")
	if parent then
		ensureDir(parent)
	end
	local text = Vault.frontmatter(front) .. "\n\n" .. string.gsub(body, "%s+$", "") .. "\n"
	fs.writeFile(path, text)
	return path
end

-- a note under <dept>/<sub>/ (lessons, verdicts); returns its path
function Vault.note(dept: string, sub: string, slug: string, front: Front, body: string): string
	front.area = front.area or dept
	front.kind = front.kind or string.sub(sub, 1, -2)
	front.date = front.date or Vault.today()
	front.links = front.links or { `[[{dept}/index]]` }
	local path = Vault.unique(Vault.dir(dept, sub), slug)
	return Vault.write(path, front, body)
end

-- append one markdown table row to a department table file (graveyard.md / golden.md), creating it with its header
function Vault.row(dept: string, file: string, header: string, cells: { string })
	local path = Vault.dir(dept, file)
	ensureDir(Vault.dir(dept))
	local text = if fs.isFile(path) then fs.readFile(path) else header
	if string.sub(text, -1) ~= "\n" then
		text ..= "\n"
	end
	local safe = {}
	for _, c in cells do
		table.insert(safe, (string.gsub(string.gsub(tostring(c), "|", "/"), "\n", " ")))
	end
	fs.writeFile(path, text .. "| " .. table.concat(safe, " | ") .. " |\n")
end

Vault.GRAVEYARD_HEADER = "# Graveyard — routes that failed; do not retry without the owner's words\n\n"
	.. "| tried | when | result | the owner's words | do not retry because | link |\n|---|---|---|---|---|---|\n"
Vault.GOLDEN_HEADER = "# Golden set — what the owner loved (≥ 7) and what decided it\n\n"
	.. "| piece | score | when | the owner's words | the measurable feature that decided it | link |\n|---|---|---|---|---|---|\n"

-- ------------------------------------------------------------ reading
local function walk(dir: string, out: { string })
	if not fs.isDir(dir) then
		return
	end
	local names = fs.readDir(dir)
	table.sort(names)
	for _, name in names do
		local p = dir .. "/" .. name
		-- Obsidian's own folders (.obsidian, .trash) and the vault's helper folders (_templates, _inbox-drafts)
		-- are not notes
		local helper = string.sub(name, 1, 1) == "." or string.sub(name, 1, 1) == "_"
		if fs.isDir(p) and not helper then
			walk(p, out)
		elseif string.sub(name, -3) == ".md" then
			table.insert(out, p)
		end
	end
end

function Vault.files(dept: string?, sub: string?): { string }
	local out = {}
	walk(if dept then Vault.dir(dept, sub) else Vault.ROOT, out)
	return out
end

function Vault.read(path: string): (Note?, string?)
	if not fs.isFile(path) then
		return nil, "missing"
	end
	local front, body = Vault.parse(fs.readFile(path))
	if not front then
		return nil, body
	end
	local rel = string.sub(path, #Vault.ROOT + 2, -4)
	return { path = path, rel = rel, front = front, body = body }, nil
end

-- notes under <dept>/<sub>, newest date first (ties: newest file name last)
function Vault.notes(dept: string, sub: string): { Note }
	local out = {}
	for _, p in Vault.files(dept, sub) do
		local note = Vault.read(p)
		if note then
			table.insert(out, note)
		end
	end
	table.sort(out, function(a, b)
		local da, db = tostring(a.front.date or ""), tostring(b.front.date or "")
		if da ~= db then
			return da > db
		end
		return a.path > b.path
	end)
	return out
end

-- a lesson note as the one-line form the rest of the kit prints ("- date (by, project): text")
function Vault.lessonLine(note: Note): string
	local f = note.front
	local text = string.gsub(note.body, "%s+", " ")
	text = string.gsub(string.gsub(text, "^%s+", ""), "%s+$", "")
	return `- {f.date or "?"} ({f.by or "?"}, {f.project or "kit"}): {text}`
end

-- ------------------------------------------------------------ lesson ids, citations and counters (the plan's C1)
-- every lesson has a short stable id from its file name (L-<dept>-<6 hex>); a session names the lessons it used on a
-- piece (kit lesson used <ids> --piece <kind> <name> -> board/citations.json); the owner's later verdict on that
-- piece credits each cited lesson: helpful at 7 or more, harmful at 3 or less. Counted live from the citations and
-- the verdicts, so a verdict from any route (kit verdict, the inbox, a lane's own store) counts. A lesson is only
-- FLAGGED, never retired by itself: three or more citations with harmful ahead of helpful by two or more.
function Vault.lessonId(note: Note): string
	local base = string.match(note.rel, "([^/]+)$") or note.rel
	local h = 5381
	for i = 1, #base do
		h = (h * 33 + string.byte(base, i)) % 4294967296
	end
	local dept = string.match(note.rel, "^([^/]+)/") or tostring(note.front.area or "x")
	return `L-{dept}-{string.format("%06x", h % 16777216)}`
end

-- a text's identity: djb2 over its bytes with line ends as "\n" (kit/world/plan.py's digest() is the same in Python;
-- one changed byte anywhere changes it, where a length or the ends would not)
function Vault.digest(text: string): string
	local s = string.gsub(text, "\r\n", "\n")
	local h = 5381
	for i = 1, #s do
		h = (h * 33 + string.byte(s, i)) % 4294967296
	end
	return string.format("%08x", h)
end

Vault.CITATIONS = nil :: string? -- a spec points it at a temp file
function Vault.citationsPath(): string
	-- the project root's board, whatever game is active: a lesson's counts never split across games
	return Vault.CITATIONS or "board/citations.json"
end

function Vault.citations(): { any }
	local path = Vault.citationsPath()
	if not fs.isFile(path) then
		return {}
	end
	local ok, data = pcall(serde.decode, "json" :: any, fs.readFile(path))
	return if ok and type(data) == "table" then data else {}
end

-- record that a session used these lessons on a piece (its owner verdict later credits them)
function Vault.cite(kind: string, name: string, ids: { string }, by: string?, served: boolean?): (boolean, string?)
	local dept = Vault.dept(kind)
	if not dept then
		return false, `unknown kind "{kind}" (asset|vfx|screen|sound|world|anim|system|playtest|kit)`
	end
	local list = Vault.citations()
	table.insert(list, {
		date = Vault.today(),
		at = os.time(),
		dept = dept,
		kind = kind,
		name = name,
		lessons = ids,
		by = by,
		served = if served then true else nil,
	})
	local path = Vault.citationsPath()
	local parent = string.match(path, "^(.*)/[^/]+$")
	if parent and not fs.isDir(parent) then
		fs.writeDir(parent)
	end
	fs.writeFile(path, serde.encode("json", list, true) .. "\n")
	return true, nil
end

local function citeKey(name: string): string
	return (string.gsub(string.lower(name), "[^%w]", ""))
end

-- the kit SHOWED these lessons for a piece (kit start / kit help --stage --for, kit study --new): recorded
-- as a served citation so the owner's verdict on the piece credits or blames them without anyone typing
-- `kit lesson used`. Only the ids not already served for this piece since its last owner verdict are written (a
-- session that runs kit start ten times on one piece is one piece of evidence). -> the ids written.
function Vault.serve(kind: string, name: string, ids: { string }, by: string?): { string }
	local dept = Vault.dept(kind)
	if not dept or name == "" or #ids == 0 then
		return {}
	end
	local key = citeKey(name)
	-- the newest owner verdict on the piece: a lesson shown again after it is new evidence for the next round
	local since = ""
	for _, v in Vault.verdicts(dept) do
		if Vault.ownersOwn(v.front) and citeKey(tostring(v.front.name or "")) == key then
			since = tostring(v.front.date or "")
			break
		end
	end
	local had: { [string]: boolean } = {}
	for _, c in Vault.citations() do
		if
			type(c) == "table"
			and c.dept == dept
			and citeKey(tostring(c.name or "")) == key
			and tostring(c.date or "") >= since
			and type(c.lessons) == "table"
		then
			for _, id in c.lessons do
				had[id] = true
			end
		end
	end
	local fresh = {}
	for _, id in ids do
		if not had[id] then
			table.insert(fresh, id)
		end
	end
	if #fresh > 0 then
		Vault.cite(kind, name, fresh, by, true)
	end
	return fresh
end

-- the lessons a verdict on this piece credits (or blames): exactly as Vault.lessonCounts counts them - each citation
-- of the piece goes to the owner's newest verdict written after it; those that go to THIS verdict (`rel`, the one just
-- recorded; else the piece's newest) -> named ids, shown ids
function Vault.creditedOn(kind: string, name: string, rel: string?): ({ string }, { string })
	local dept = Vault.dept(kind)
	if not dept then
		return {}, {}
	end
	local key = citeKey(name)
	local mine: { Note } = {}
	for _, v in Vault.verdicts(dept) do -- newest first
		if
			Vault.ownersOwn(v.front)
			and citeKey(tostring(v.front.name or "")) == key
			and Vault.polarity(v.front) ~= nil
		then
			table.insert(mine, v)
		end
	end
	local target = rel or (mine[1] and mine[1].rel)
	local named, shown, seen = {}, {}, {}
	for _, c in Vault.citations() do
		if
			type(c) == "table"
			and c.dept == dept
			and citeKey(tostring(c.name or "")) == key
			and type(c.lessons) == "table"
		then
			local hit: Note? = nil
			for _, v in mine do
				if Vault.after(v, tostring(c.date or ""), tonumber(c.at)) then
					hit = v
					break
				end
			end
			if hit and hit.rel == target then
				for _, id in c.lessons do
					local k = id .. (if c.served then "s" else "n")
					if not seen[k] then
						seen[k] = true
						table.insert(if c.served then shown else named, id)
					end
				end
			end
		end
	end
	return named, shown
end

-- ------------------------------------------------------------ the replay eval (kit vault eval)
-- Did the ranking put the lessons that MATTERED in front of the session? A case is a piece whose lessons a session
-- NAMED as applied (kit lesson used, a study's "Lessons applied" ids): replayed as of that day (only the lessons that
-- existed then), the old order (newest first) and the new one (Vault.rank for the piece's own words) are each scored
-- by recall@k - the share of the named lessons in their top k. Served rows are no label: they are the ranker's own.
export type EvalCase = { dept: string, name: string, before: string, ids: { string }, source: string }

-- the folders whose <asset>.study.md files are read as cases (nil: assets/models + every game's assets/models)
Vault.STUDY_ROOTS = nil :: { string }? -- a spec points it at a temp folder

local function studyDirs(): { string }
	if Vault.STUDY_ROOTS then
		return Vault.STUDY_ROOTS
	end
	local dirs = { "assets/models" }
	if fs.isDir("games") then
		for _, g in fs.readDir("games") do
			if fs.isDir(`games/{g}/assets/models`) then
				table.insert(dirs, `games/{g}/assets/models`)
			end
		end
	end
	return dirs
end

local function studyCases(): { EvalCase }
	local out = {}
	for _, dir in studyDirs() do
		if fs.isDir(dir) then
			for _, f in fs.readDir(dir) do
				local name = string.match(f, "^(.+)%.study%.md$")
				if name then
					local path = `{dir}/{f}`
					local text = string.gsub(fs.readFile(path), "\r\n", "\n")
					local section = string.match(text, "\n## Lessons applied%s*\n(.-)\n## ")
						or string.match(text, "\n## Lessons applied%s*\n(.*)$")
						or ""
					local ids = {}
					for id in string.gmatch(section, "\n?%- (L%-3d%-%x+):") do
						table.insert(ids, id)
					end
					if #ids > 0 then
						local ok, meta = pcall(fs.metadata, path)
						local before = if ok and meta.modifiedAt
							then string.sub(meta.modifiedAt:toIsoDate(), 1, 10)
							else Vault.today()
						table.insert(out, { dept = "3d", name = name, before = before, ids = ids, source = "study" })
					end
				end
			end
		end
	end
	return out
end

function Vault.evalCases(dept: string?): { EvalCase }
	local cases, seen = {}, {}
	for _, c in Vault.citations() do
		if
			type(c) == "table"
			and not c.served
			and type(c.lessons) == "table"
			and (not dept or c.dept == dept)
			and type(c.name) == "string"
		then
			local ids = {}
			for _, id in c.lessons do
				if string.match(id, "^L%-") then -- a rule (R-...) is no lesson the stage list ranks
					table.insert(ids, id)
				end
			end
			local key = `{c.dept}/{citeKey(c.name)}`
			if #ids > 0 and not seen[key] then
				seen[key] = true
				table.insert(
					cases,
					{ dept = c.dept, name = c.name, before = tostring(c.date or ""), ids = ids, source = "named" }
				)
			end
		end
	end
	if not dept or dept == "3d" then
		for _, c in studyCases() do
			local key = `3d/{citeKey(c.name)}`
			if not seen[key] then
				seen[key] = true
				table.insert(cases, c)
			end
		end
	end
	return cases
end

export type EvalRow = { case: EvalCase, old: number, new: number, fam: number, family: string?, found: number }

-- "2026-11-03" -> "2026-11-02"
local function dayBefore(date: string): string
	local y, m, d = string.match(date, "^(%d%d%d%d)%-(%d%d)%-(%d%d)")
	if not y then
		return date
	end
	local t =
		os.time({ year = tonumber(y) :: number, month = tonumber(m) :: number, day = tonumber(d) :: number, hour = 12 })
	return os.date("!%Y-%m-%d", t - 86400) :: string
end

-- -> one row per case (recall@k of the old and the new order) and the means
function Vault.eval(dept: string?, k: number?): ({ EvalRow }, number?, number?, number?)
	local K = k or 6
	local rows: { EvalRow } = {}
	local so, sn, sf = 0, 0, 0
	local Routes = require("./routes") -- (lazy: routes requires this module)
	local Families = require("./families") -- (lazy too: families requires this module)
	for _, c in Vault.evalCases(dept) do
		-- as of the day BEFORE the piece was cited: a lesson written that day is often about this very piece
		local asOf = dayBefore(c.before)
		-- the named lessons that existed then (a later or retired one cannot be ranked by either order)
		local live = {}
		for _, id in c.ids do
			local n = Vault.lessonById(id)
			if n and tostring(n.front.date or "") <= asOf then
				live[id] = true
			end
		end
		local want = 0
		for _ in live do
			want += 1
		end
		if want > 0 then
			-- a session reads lessons STAGE BY STAGE (kit help --stage): a named lesson is found when it is in the
			-- top k of a stage it belongs to, in each order
			local words = Routes.words(c.dept)
			local query = Vault.queryFor(c.dept, c.name)
			-- the third order (sprint 5): the same ranking preferring the piece's family (kit/lib/families.luau)
			local family = Families.ofPiece(c.dept, c.name)
			local gotOld, gotNew, gotFam = {}, {}, {}
			for _, stage in Routes.stages(c.dept) do
				local all = Vault.rank(c.dept, query, { before = asOf, stage = stage, stageWords = words })
				local ranked = Vault.pick(all, K, query ~= "") -- exactly what kit help --stage shows
				local byFam = if family
					then Vault.pick(
						Vault.rank(c.dept, query, { before = asOf, stage = stage, stageWords = words, family = family }),
						K,
						query ~= ""
					)
					else ranked
				for _, r in byFam do
					gotFam[r.id] = true
				end
				local newest = table.clone(all)
				-- the old order: newest first by date alone (what kit help --stage printed before the ranking)
				table.sort(newest, function(a, b)
					local da, db = tostring(a.note.front.date or ""), tostring(b.note.front.date or "")
					if da ~= db then
						return da > db
					end
					return a.note.rel > b.note.rel
				end)
				for _, r in ranked do
					gotNew[r.id] = true
				end
				for i = 1, math.min(K, #newest) do
					gotOld[newest[i].id] = true
				end
			end
			local o, nw, fm = 0, 0, 0
			for id in live do
				o += if gotOld[id] then 1 else 0
				nw += if gotNew[id] then 1 else 0
				fm += if gotFam[id] then 1 else 0
			end
			o /= want
			nw /= want
			fm /= want
			so += o
			sn += nw
			sf += fm
			table.insert(rows, { case = c, old = o, new = nw, fam = fm, family = family, found = want })
		end
	end
	if #rows == 0 then
		return rows, nil, nil, nil
	end
	return rows, so / #rows, sn / #rows, sf / #rows
end

-- the lesson kind of a department ("3d" -> "asset"): what a served citation is filed under
Vault.KIND_OF_DEPT = {
	["3d"] = "asset",
	vfx = "vfx",
	ui = "screen",
	sfx = "sound",
	world = "world",
	anim = "anim",
	code = "system",
	qa = "playtest",
	kit = "kit",
}

-- an owner ask that JUDGES shown work, filed once as the owner's words in its lane's vault (2026-11-08: "the city
-- looks horrible" was filed as a task and never reached the world vault): a verdict note "ask-<card id>" with no
-- number and no direction - never averaged, never golden, never credits a lesson; the distil and the page read it
function Vault.askFiled(dept: string, id: string): boolean
	return Vault.KIND_OF_DEPT[dept] ~= nil and #Vault.verdicts(dept, `ask-{id}`) > 0
end

function Vault.fileAsk(dept: string, id: string, text: string, date: string?): string?
	local kind = Vault.KIND_OF_DEPT[dept]
	if not kind or Vault.askFiled(dept, id) then
		return nil
	end
	local path = Vault.record({
		kind = kind,
		name = `ask-{id}`,
		words = `{text}\n\n(the owner's words, from board ask {id})`,
		tags = { "owner-ask" },
		date = date,
	})
	return path
end

-- { [lesson id] = { cites, helpful, harmful, flagged } } from every citation and the owner's verdicts after it
-- A citation row with `served = true` is a lesson the kit SHOWED for the piece (ranked for it by kit start / kit help
-- --stage --for, kit study --new) rather than one a session named: it counts in served / servedHelpful /
-- servedHarmful, at half the weight of a named one when a lesson is flagged or ranked.
function Vault.lessonCounts(): {
	[string]: {
		cites: number,
		helpful: number,
		harmful: number,
		flagged: boolean,
		served: number,
		servedHelpful: number,
		servedHarmful: number,
	},
}
	local counts = {}
	local verdictsOf: { [string]: { Note } } = {}
	-- one count per lesson per (piece, verdict): citing a lesson on three rebuilds of one piece that got ONE score is
	-- one piece of evidence, not three
	local seen: { [string]: boolean } = {}
	for _, c in Vault.citations() do
		if type(c) == "table" and type(c.lessons) == "table" and type(c.dept) == "string" then
			verdictsOf[c.dept] = verdictsOf[c.dept] or Vault.verdicts(c.dept)
			-- the owner's newest verdict on this piece written AFTER the lessons were cited
			local hit: Note? = nil
			for _, v in verdictsOf[c.dept] do -- newest first
				if
					Vault.ownersOwn(v.front)
					and citeKey(tostring(v.front.name or "")) == citeKey(tostring(c.name or ""))
					and Vault.polarity(v.front) ~= nil
					and Vault.after(v, tostring(c.date or ""), tonumber(c.at))
				then
					hit = v
					break
				end
			end
			-- 1 success (7+ / Keep), -1 failure (3 or less / Redo), 0 neither, nil no verdict yet
			local pol = if hit then Vault.polarity(hit.front) else nil
			local served = c.served == true
			for _, id in c.lessons do
				local key = `{id}|{citeKey(tostring(c.name or ""))}|{if hit then hit.rel else "waiting"}|{if served
					then "s"
					else "c"}`
				if not seen[key] then
					seen[key] = true
					local k = counts[id]
						or {
							cites = 0,
							helpful = 0,
							harmful = 0,
							flagged = false,
							served = 0,
							servedHelpful = 0,
							servedHarmful = 0,
						}
					if served then
						k.served += 1
						if pol == 1 then
							k.servedHelpful += 1
						elseif pol == -1 then
							k.servedHarmful += 1
						end
					else
						k.cites += 1
						if pol == 1 then
							k.helpful += 1
						elseif pol == -1 then
							k.harmful += 1
						end
					end
					-- a shown lesson weighs half a named one: flagged at 3+ weighted uses with harmful ahead by 2+
					local uses = k.cites + 0.5 * k.served
					local against = (k.harmful + 0.5 * k.servedHarmful) - (k.helpful + 0.5 * k.servedHelpful)
					k.flagged = uses >= 3 and against >= 2
					counts[id] = k
				end
			end
		end
	end
	return counts
end

-- the loved piece of a department closest to a new piece's name (the plan's B6): golden rows scored by shared words
-- (snake_case and PascalCase split), the newest on a tie; with no shared word, the newest loved piece (the bar).
-- Returns the row's cells { piece, score, date, words, feature, link } and how many words matched.
local function nameWords(text: string): { [string]: boolean }
	local spaced = string.gsub(string.gsub(text, "(%l)(%u)", "%1 %2"), "[_%-%.]", " ")
	local out = {}
	for w in string.gmatch(string.lower(spaced), "%a%a%a+") do
		out[w] = true
	end
	return out
end

function Vault.nearestGolden(dept: string, name: string): ({ string }?, number)
	local rows = {}
	for _, r in Vault.rows(Vault.dir(dept, "golden.md")) do
		if tonumber(r[2]) then -- a row still waiting for the owner's number is no bar yet
			table.insert(rows, r)
		end
	end
	if #rows == 0 then
		return nil, 0
	end
	local want = nameWords(name)
	local best, bestN = rows[#rows], 0
	for _, r in rows do
		local have = nameWords(table.concat(r, " "))
		local n = 0
		for w in want do
			if have[w] then
				n += 1
			end
		end
		if n >= bestN and n > 0 then
			best, bestN = r, n
		end
	end
	return best, bestN
end

-- ------------------------------------------------------------ before/after pairs and the gardener (C5, C8)
-- a PAIR is a piece the owner scored low and later scored at least two points higher: the strongest teaching data
-- (what turned a no into a yes). Owner verdicts only (an inferred one is not the owner's).
export type Pair = { name: string, low: Note, high: Note }

function Vault.pairs(dept: string): { Pair }
	local byPiece: { [string]: { Note } } = {}
	for _, v in Vault.verdicts(dept) do
		if Vault.ownersOwn(v.front) and tonumber(v.front.score) and v.front.name then
			local k = citeKey(tostring(v.front.name))
			byPiece[k] = byPiece[k] or {}
			table.insert(byPiece[k], v)
		end
	end
	local out: { Pair } = {}
	for _, list in byPiece do
		-- oldest first; the same day by file time (read BEFORE sorting: fs.metadata yields, and a sort's comparator
		-- cannot yield - inside it every time would read as 0)
		local at: { [string]: number } = {}
		for _, n in list do
			at[n.path] = Vault.noteTime(n)
		end
		table.sort(list, function(a, b)
			if tostring(a.front.date) ~= tostring(b.front.date) then
				return tostring(a.front.date) < tostring(b.front.date)
			end
			return (at[a.path] or 0) < (at[b.path] or 0)
		end)
		local low: Note? = nil
		for _, v in list do
			local s = tonumber(v.front.score) :: number
			if not low or s < (tonumber(low.front.score) :: number) then
				low = v
			elseif
				s >= (tonumber(low.front.score) :: number) + 2
				and Vault.after(v, tostring(low.front.date), Vault.noteTime(low))
			then
				table.insert(out, { name = tostring(v.front.name), low = low, high = v })
				low = nil -- the next pair starts after this yes
			end
		end
	end
	table.sort(out, function(a, b)
		return tostring(a.high.front.date) > tostring(b.high.front.date)
	end)
	return out
end

-- write each pair as a note (<dept>/pairs/<piece>--<date of the yes>.md) once; returns the paths written
function Vault.writePairs(dept: string): { string }
	local written = {}
	for _, p in Vault.pairs(dept) do
		local slug = `{Vault.slug(p.name)}--{p.high.front.date}`
		local path = Vault.dir(dept, `pairs/{slug}.md`)
		if not fs.isFile(path) then
			local function said(n: Note): string
				return (string.gsub(string.gsub(n.body, "%s+", " "), "^%s*(.-)%s*$", "%1"))
			end
			local body = table.concat({
				`# {p.name}: {p.low.front.score}/10 -> {p.high.front.score}/10`,
				"",
				`- Before ({p.low.front.date}, [[{p.low.rel}]]): {said(p.low)}`,
				`- After ({p.high.front.date}, [[{p.high.rel}]]): {said(p.high)}`,
				`- What changed between the builds: {if p.low.front.build or p.high.front.build
					then tostring(p.low.front.build or "?") .. " -> " .. tostring(p.high.front.build or "?")
					else "(no build ids recorded: read both notes; the after note's 'What decided it' names the change)"}`,
			}, "\n")
			ensureDir(Vault.dir(dept, "pairs"))
			Vault.write(path, {
				kind = "pair",
				area = dept,
				name = p.name,
				date = p.high.front.date,
				links = { `[[{dept}/index]]`, `[[{p.low.rel}]]`, `[[{p.high.rel}]]` },
			}, body)
			table.insert(written, path)
		end
	end
	return written
end

local function contentWords(text: string): { [string]: boolean }
	local out = {}
	for w in string.gmatch(string.lower(text), "%a%a%a%a+") do
		out[w] = true
	end
	return out
end

-- the gardener (on demand; nothing is deleted): near-duplicate live lessons (most of their words shared), lessons and
-- rules the owner's verdicts flagged harmful, and new pairs written. Each line proposes the command that would act.
-- near-duplicate live lessons (60%+ of their words shared), newer first in each pair; read-only (kit start counts
-- them, kit vault garden proposes the supersede)
function Vault.nearDuplicates(dept: string): { { newer: Note, older: Note, share: number } }
	local out = {}
	local retired = Vault.supersededSet()
	local live = {}
	for _, n in Vault.notes(dept, "lessons") do
		if not retired[string.lower(n.rel)] then
			table.insert(live, { note = n, words = contentWords(n.body) })
		end
	end
	for i = 1, #live do
		for j = i + 1, #live do
			local a, b = live[i].words, live[j].words
			local both, either = 0, 0
			for w in a do
				either += 1
				if b[w] then
					both += 1
				end
			end
			for w in b do
				if not a[w] then
					either += 1
				end
			end
			if either >= 8 and both / either >= 0.6 then
				-- notes are newest first: i is the newer one
				table.insert(out, { newer = live[i].note, older = live[j].note, share = both / either })
			end
		end
	end
	return out
end

function Vault.garden(dept: string): { string }
	local lines = {}
	local retired = Vault.supersededSet()
	local live = {}
	for _, n in Vault.notes(dept, "lessons") do
		if not retired[string.lower(n.rel)] then
			table.insert(live, { note = n })
		end
	end
	for _, p in Vault.nearDuplicates(dept) do
		table.insert(
			lines,
			`near-duplicate lessons ({math.floor(p.share * 100)}% shared): lune run kit vault supersede {p.newer.rel} {p.older.rel} --why "same lesson"`
		)
	end
	local counts = Vault.lessonCounts()
	for _, l in live do
		local id = Vault.lessonId(l.note)
		if counts[id] and counts[id].flagged then
			table.insert(
				lines,
				`FLAGGED harmful {id} (+{counts[id].helpful}/-{counts[id].harmful}): {l.note.rel} - retire it if the verdicts are its fault: lune run kit vault supersede <the lesson that replaces it> {l.note.rel} --why "..."`
			)
		end
	end
	for _, r in Vault.rules(dept) do
		if not r.retired and counts[r.id] and counts[r.id].flagged then
			table.insert(
				lines,
				`FLAGGED harmful {r.id} (+{counts[r.id].helpful}/-{counts[r.id].harmful}): lune run kit vault distil {dept} --retire "{r.id}: <the verdicts against it>"`
			)
		end
	end
	for _, p in Vault.writePairs(dept) do
		table.insert(lines, `new pair (a no that became a yes): {p}`)
	end
	return lines
end

-- adoption: of the owner's verdicts dated on or after `since`, how many fell on a piece whose lessons were cited
-- (the loop only learns when sessions cite; kit status reports the share)
function Vault.adoption(since: string): (number, number)
	local cited: { [string]: boolean } = {}
	for _, c in Vault.citations() do
		if type(c) == "table" and c.dept and c.name then
			cited[`{c.dept}/{citeKey(tostring(c.name))}`] = true
		end
	end
	local total, hit = 0, 0
	for _, v in Vault.verdicts() do
		if Vault.ownersOwn(v.front) and tostring(v.front.date or "") >= since and v.front.name then
			total += 1
			if cited[`{v.front.area}/{citeKey(tostring(v.front.name))}`] then
				hit += 1
			end
		end
	end
	return hit, total
end

-- the lesson line with its id and counters in front: "- [L-3d-a1b2c3 +2/-0] 2026-10-16 (by, project): text"
function Vault.lessonLineWithId(note: Note, counts: { [string]: any }?): string
	local id = Vault.lessonId(note)
	local k = counts and counts[id]
	local tag = if k then `{id} +{k.helpful}/-{k.harmful}{if k.flagged then " FLAGGED harmful" else ""}` else id
	return `- [{tag}] ` .. string.sub(Vault.lessonLine(note), 3)
end

-- the department's LIVE lessons, oldest first (a lesson another note supersedes is left out: Vault.supersede)
function Vault.lessons(dept: string): { string }
	local lines = {}
	local notes = Vault.notes(dept, "lessons")
	local retired = Vault.supersededSet()
	for i = #notes, 1, -1 do -- oldest first, like kit/lessons
		if not retired[string.lower(notes[i].rel)] then
			table.insert(lines, Vault.lessonLine(notes[i]))
		end
	end
	return lines
end

-- does `text` name `word` at the START of a word (any case)? "uv" finds "UV maps", never "fluvial"
local function namesWord(low: string, word: string): boolean
	local w = string.lower(word)
	local at = 1
	while true do
		local s = string.find(low, w, at, true)
		if not s then
			return false
		end
		if s == 1 or not string.match(string.sub(low, s - 1, s - 1), "[%w]") then
			return true
		end
		at = s + 1
	end
end

-- the stages a lesson note belongs to: a hand tag in its frontmatter (`stages: [surface]`, from `kit lesson ...
-- --stage surface`) wins; otherwise every stage whose words the lesson names (kit/knowledge/routes.json "words")
function Vault.lessonStages(note: Note, stageWords: { [string]: { string } }): { string }
	local tagged = note.front.stages or note.front.stage
	if type(tagged) == "string" then
		tagged = { tagged }
	end
	if type(tagged) == "table" and #tagged > 0 then
		local out = {}
		for _, s in tagged do
			table.insert(out, tostring(s))
		end
		return out
	end
	-- scored, not "any word": a long lesson names half the route in passing. Each stage word found counts 1, or 2
	-- when it is in the lesson's opening (lessons lead with their topic); the lesson belongs to its best stage and
	-- to a second one only when that scores almost as high
	local low = string.lower(note.body)
	local head = string.sub(low, 1, 160)
	local scored = {}
	for stage, words in stageWords do
		local s = 0
		for _, w in words do
			if namesWord(head, w) then
				s += 2
			elseif namesWord(low, w) then
				s += 1
			end
		end
		if s > 0 then
			table.insert(scored, { stage = stage, s = s })
		end
	end
	table.sort(scored, function(a, b)
		if a.s ~= b.s then
			return a.s > b.s
		end
		return a.stage < b.stage
	end)
	local out = {}
	for i, e in scored do
		if i == 1 or (i == 2 and e.s >= scored[1].s * 0.8) then
			table.insert(out, e.stage)
		end
	end
	return out
end

-- a stage's lessons, newest first, as lesson lines (superseded ones left out)
-- `withIds`: each line opens with the lesson's id and counters (kit start / kit help --stage: what a session cites)
function Vault.stageLessons(
	dept: string,
	stage: string,
	stageWords: { [string]: { string } },
	withIds: boolean?
): { string }
	local lines = {}
	local retired = Vault.supersededSet()
	local counts = if withIds then Vault.lessonCounts() else nil
	for _, n in Vault.notes(dept, "lessons") do
		if not retired[string.lower(n.rel)] and table.find(Vault.lessonStages(n, stageWords), stage) then
			table.insert(lines, if withIds then Vault.lessonLineWithId(n, counts) else Vault.lessonLine(n))
		end
	end
	return lines
end

-- ------------------------------------------------------------ retrieval by RELEVANCE (2026-11-07)
-- The stage list used to be the NEWEST lessons: a session texturing a gun read the last props lane's delft and
-- tablecloth notes while the gunmetal lesson of two weeks before never showed. Now every list a session reads is
-- ranked against what it is building (the piece it names, else its lane's top card): BM25 over the lesson's words,
-- then the owner's verdicts on the pieces it was cited / shown on, then a little recency; a lesson from another
-- game ranks lower and says so. The same tokenizer as kit/tools/study.py (its words()), so both sides agree.
Vault.STOP = {}
for w in
	string.gmatch(
		[[the a an and or of to in on at for with from by as is are be it its this that these those not no
into onto over under than then them they their there here when where what which who how why all any each every
one two three more most less much many some such only own same other very can will would should could must may
just also but if so do does did done has have had was were been being use used using make made our your his her
owner kit build built model asset part look looks real new now said answer lune run]],
		"%S+"
	)
do
	Vault.STOP[w] = true
end

-- a text's search words: camelCase and snake_case split, lower case, 3+ letters, stop words out, a plural's "s" off
function Vault.words(text: string): { string }
	local spaced = string.gsub(string.gsub(text or "", "(%l)(%u)", "%1 %2"), "_", " ")
	local out = {}
	for w in string.gmatch(string.lower(spaced), "[a-z][a-z0-9]+") do
		if #w >= 3 and not Vault.STOP[w] then
			if #w > 4 and string.sub(w, -1) == "s" and string.sub(w, -2) ~= "ss" then
				w = string.sub(w, 1, -2)
			end
			table.insert(out, w)
		end
	end
	return out
end

export type Hit = { doc: any, score: number, hits: number }

-- BM25 (k1 1.2, b 0.75) of `query` against each doc's text; -> every doc sharing a word, best first, with how many
-- distinct query words it holds
function Vault.bm25(query: string, docs: { any }, textOf: (any) -> string): { Hit }
	local q, qset = {}, {}
	for _, w in Vault.words(query) do
		if not qset[w] then
			qset[w] = true
			table.insert(q, w)
		end
	end
	if #q == 0 or #docs == 0 then
		return {}
	end
	local tfs, lens, df, total = {}, {}, {}, 0
	for i, d in docs do
		local tf, n = {}, 0
		for _, w in Vault.words(textOf(d)) do
			tf[w] = (tf[w] or 0) + 1
			n += 1
		end
		tfs[i], lens[i] = tf, n
		total += n
		for w in tf do
			df[w] = (df[w] or 0) + 1
		end
	end
	local N, avg = #docs, math.max(1, total / #docs)
	local out: { Hit } = {}
	for i, d in docs do
		local s, hits = 0, 0
		for _, w in q do
			local tf = tfs[i][w]
			if tf then
				hits += 1
				local idf = math.log(1 + (N - df[w] + 0.5) / (df[w] + 0.5))
				s += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * lens[i] / avg))
			end
		end
		if s > 0 then
			table.insert(out, { doc = d, score = s, hits = hits })
		end
	end
	table.sort(out, function(a, b)
		return a.score > b.score
	end)
	return out
end

-- a lesson's one-line gist: its own `gist:` (kit lesson --gist), else its first sentence, at most 160 characters
function Vault.gist(note: Note): string
	local g = note.front.gist
	local text = if type(g) == "string" and g ~= "" then g else string.gsub(note.body, "%s+", " ")
	text = string.gsub(string.gsub(text, "^%s+", ""), "%s+$", "")
	if not (type(g) == "string" and g ~= "") then
		-- the first sentence: up to ". " / "; " / "! " after 40 characters (an abbreviation like "e.g." is too early)
		local cut = nil
		local at = 40
		while true do
			local s = string.find(text, "[%.;!]%s", at)
			if not s then
				break
			end
			cut = s
			break
		end
		if cut then
			text = string.sub(text, 1, cut)
		end
	end
	if (utf8.len(text) or #text) > 160 then
		text = string.sub(text, 1, (utf8.offset(text, 158) or 158) - 1) .. "..."
	end
	return text
end

-- days between two YYYY-MM-DD dates (b - a), or nil
local function daysBetween(a: string, b: string): number?
	local function day(d: string): number?
		local y, m, dd = string.match(d, "^(%d%d%d%d)%-(%d%d)%-(%d%d)")
		if not y then
			return nil
		end
		return os.time({
			year = tonumber(y) :: number,
			month = tonumber(m) :: number,
			day = tonumber(dd) :: number,
			hour = 12,
		}) / 86400
	end
	local da, db = day(a), day(b)
	return if da and db then math.floor(db - da + 0.5) else nil
end

-- the projects whose lessons count as the kit's own (a lesson written in the kit's home, not inside one game)
Vault.HOME_PROJECTS = { Parallax = true, kit = true }

-- is <name> a real game folder of this project (games/<name>): only such a game's lessons are "another game's"
function Vault.isGame(name: string): boolean
	return fs.isDir(`games/{name}`)
end
Vault.OTHER_GAME = 0.6 -- a lesson another game wrote ranks at this share of its score

export type Ranked = {
	note: Note,
	id: string,
	score: number,
	relevance: number, -- 0..1 of the best match in this list (0 = no shared word)
	hits: number,
	evidence: number, -- -1..1 from the owner's verdicts on the pieces it was cited / shown on (-1 = flagged)
	otherGame: string?, -- the game the lesson came from, when it is not this one
	family: string?, -- the lesson's family, when the ranking was for a piece of a known family
}

-- the department's live lessons ranked for `query` (a piece's name + brief words, a card's title, a search):
-- relevance first (BM25, scaled 0..1 against the best), then the owner's verdicts on the pieces each was cited or
-- shown on (+-0.15), then recency (+0.1 for today, fading over ~a month); a lesson from another game x0.6.
-- opts.stage keeps the lessons of one stage of the route (opts.stageWords: Routes.words(dept)); opts.before keeps
-- the ones dated on or before a day (the replay eval); opts.game = the active game (Config.game() when nil).
-- With an empty query the order is the evidence, then the date: the old newest-first, minus the flagged ones.
function Vault.rank(
	dept: string,
	query: string?,
	opts: {
		stage: string?,
		stageWords: { [string]: { string } }?,
		before: string?,
		game: string?,
		today: string?,
		family: string?, -- the piece's family (kit/lib/families.luau): its lessons rank higher, another family's lower
	}?
): { Ranked }
	local o = opts or {}
	local Families = if o.family then require("./families") else nil
	local retired = Vault.supersededSet()
	local pool: { Note } = {}
	for _, n in Vault.notes(dept, "lessons") do
		local date = tostring(n.front.date or "")
		if
			not retired[string.lower(n.rel)]
			and (not o.stage or table.find(Vault.lessonStages(n, o.stageWords or {}), o.stage) ~= nil)
			and (not o.before or date <= o.before)
		then
			table.insert(pool, n)
		end
	end
	local rel: { [Note]: Hit } = {}
	local best = 0
	for _, h in
		Vault.bm25(query or "", pool, function(n: Note): string
			return tostring(n.front.gist or "") .. " " .. n.body
		end)
	do
		rel[h.doc] = h
		best = math.max(best, h.score)
	end
	local counts = Vault.lessonCounts()
	local today = o.today or o.before or Vault.today()
	local game = if o.game ~= nil then o.game else Config.game()
	local out: { Ranked } = {}
	for _, n in pool do
		local id = Vault.lessonId(n)
		local h = rel[n]
		local relevance = if h and best > 0 then h.score / best else 0
		-- (a replay, opts.before, knows nothing the owner said after that day: no counters)
		local k = if o.before then nil else counts[id]
		local evidence = 0
		if k then
			local net = (k.helpful - k.harmful) + 0.5 * ((k.servedHelpful or 0) - (k.servedHarmful or 0))
			evidence = math.clamp(net, -2, 2) / 2
			if k.flagged then
				evidence = -1
			end
		end
		local age = daysBetween(tostring(n.front.date or ""), today) or 365
		local recency = 0.1 / (1 + math.max(0, age) / 30)
		local score = relevance + 0.15 * evidence + recency
		-- the piece's family first: a gun's "barrel" lesson stops ranking for a wine barrel (sprint 5, proposal 12)
		local fam = if Families then Families.ofLesson(dept, n) else nil
		if Families and fam == o.family then
			score += Families.BOOST
		elseif Families and fam then
			score -= (1 - Families.OTHER) * math.abs(score) -- always lower (a flagged lesson's score can be below 0)
		end
		local project = tostring(n.front.project or "")
		local other = nil
		-- (only a real other game of this project: an installed project's own lessons carry its own name, no game)
		if project ~= "" and not Vault.HOME_PROJECTS[project] and project ~= game and Vault.isGame(project) then
			other = project
			score -= (1 - Vault.OTHER_GAME) * math.abs(score) -- always lower (a flagged lesson can score below 0)
		end
		table.insert(out, {
			note = n,
			id = id,
			score = score,
			relevance = relevance,
			hits = if h then h.hits else 0,
			evidence = evidence,
			otherGame = other,
			family = fam,
		})
	end
	table.sort(out, function(a, b)
		if a.score ~= b.score then
			return a.score > b.score
		end
		return a.note.rel > b.note.rel
	end)
	return out
end

-- the n lessons a stage list SHOWS: the best n - fresh by rank, then the `fresh` newest not already in (a recent
-- tool fact - "kit optimize caps maps at 1024" - matters to every piece and names none of its words; the replay of
-- the town_avenue_lamp case, 2026-11-07, found all four lessons its session used were such facts). No query: the
-- ranked order already is best-proven + newest.
Vault.FRESH = 2
function Vault.pick(ranked: { Ranked }, n: number, hasQuery: boolean): { Ranked }
	if not hasQuery or #ranked <= n then
		return table.move(ranked, 1, math.min(n, #ranked), 1, {})
	end
	local fresh = math.min(Vault.FRESH, math.floor(n / 3)) -- (a third at most: a list of 1-2 is all by rank)
	local out, taken = {}, {}
	for i = 1, n - fresh do
		table.insert(out, ranked[i])
		taken[ranked[i]] = true
	end
	local byDate = table.clone(ranked)
	table.sort(byDate, function(a, b)
		local da, db = tostring(a.note.front.date or ""), tostring(b.note.front.date or "")
		if da ~= db then
			return da > db
		end
		return a.note.rel > b.note.rel
	end)
	for _, r in byDate do
		if #out >= n then
			break
		end
		if not taken[r] and r.evidence >= 0 then
			table.insert(out, r)
			taken[r] = true
		end
	end
	return out
end

-- a ranked lesson as printed: in full (`full`, up to Vault.LESSON_MAX characters) or as its gist; "lune run kit"
-- inside a lesson is shortened to "kit" (it is a lesson, not one of the stage's commands)
function Vault.rankedLine(r: Ranked, counts: { [string]: any }?, full: boolean, maxChars: number?): string
	local cap = maxChars or Vault.LESSON_MAX
	local k = counts and counts[r.id]
	local tag = r.id
	if k then
		tag ..= ` +{k.helpful}/-{k.harmful}`
		if (k.served or 0) > 0 then
			tag ..= ` shown {k.served}x +{k.servedHelpful or 0}/-{k.servedHarmful or 0}`
		end
		if k.flagged then
			tag ..= " FLAGGED harmful"
		end
	end
	local f = r.note.front
	local where = tostring(f.project or "kit")
	if r.otherGame then
		where ..= " - another game"
	end
	local text
	if full then
		text = string.gsub(string.gsub(r.note.body, "%s+", " "), "^ ", "")
		if (utf8.len(text) or #text) > cap then
			text = string.sub(text, 1, (utf8.offset(text, cap - 2) or cap - 2) - 1) .. "..."
		end
	else
		text = Vault.gist(r.note)
	end
	text = string.gsub(text, "lune run kit ", "kit ")
	return `- [{tag}] {f.date or "?"} ({where}): {text}`
end

-- the longest lesson `kit lesson` takes (characters): a longer one is two lessons. The vault's longest was 1,010
-- (2026-11-07); printed whole, a lesson must fit the stage's share of the start budget.
Vault.LESSON_MAX = 1200

-- the words a named piece is known by, for ranking: its name (split) twice, then its own brief / direction where the
-- lane keeps one (3D: assets/models/<piece>.brief.md - what, style, hero features, parts; anim: the direction page),
-- in the active game first, then the project root. A name with no such file is ranked by its name alone.
function Vault.queryFor(dept: string, piece: string): string
	local parts = { piece, piece }
	local game = Config.game()
	local roots = if game then { `games/{game}/`, "" } else { "" }
	local files: { string } = {}
	if dept == "3d" then
		files = { `assets/models/{piece}.brief.md` }
	elseif dept == "anim" then
		files = { `assets/animations/direction/{piece}.md` }
	elseif dept == "world" then
		-- a world's own words: its blueprint's about line and objectives (every world has a blueprint; a name alone
		-- matches nothing and leaves the ranking to the lessons' dates), then its brief and its direction doc
		files = { `assets/worlds/{piece}.brief.md`, `assets/worlds/direction/{piece}.md` }
		for _, r in roots do
			local path = `{r}assets/worlds/{piece}.json`
			if fs.isFile(path) then
				local ok, bp = pcall(serde.decode, "json" :: any, fs.readFile(path))
				if ok and type(bp) == "table" then
					for _, key in { "_about", "about", "title", "pitch" } do
						if type(bp[key]) == "string" then
							table.insert(parts, bp[key])
						end
					end
					for _, o in (if type(bp.objectives) == "table" then bp.objectives else {}) :: { any } do
						if type(o) == "table" and type(o.name) == "string" then
							table.insert(parts, o.name)
						end
					end
				end
				break
			end
		end
	end
	-- (enforced learning, rule 2: board/plans/archive/2026-11-09-enforced-learning-plan.md) a vfx / ui / sfx piece's own words:
	-- its file's describing fields, and a vfx original's director brief - a name alone ranks the lessons by date
	if dept == "vfx" or dept == "ui" or dept == "sfx" then
		local where = if dept == "vfx" then "assets/effects" elseif dept == "ui" then "assets/ui" else "assets/sounds"
		if dept == "vfx" then
			table.insert(files, `assets/effects/briefs/{piece}.md`)
		end
		for _, r in roots do
			local path = `{r}{where}/{piece}.json`
			if fs.isFile(path) then
				local ok, js = pcall(serde.decode, "json" :: any, fs.readFile(path))
				if ok and type(js) == "table" then
					for _, k in { "_about", "about", "title", "what", "description", "lore", "pitch" } do
						if type(js[k]) == "string" then
							table.insert(parts, js[k])
						end
					end
				end
				break
			end
		end
	end
	for _, f in files do
		for _, r in roots do
			local path = r .. f
			if fs.isFile(path) then
				local text = string.gsub(fs.readFile(path), "\r\n", "\n")
				-- the answered lines only: a template's "<answer>" and HTML comments say nothing about the piece
				text = string.gsub(text, "<!%-%-.-%-%->", " ")
				if dept == "3d" then
					-- a brief's own fields (kit/tools/study.py's query_of): what it IS twice, its style / function /
					-- moving parts, each hero feature's and each planned part's name - never the owner's quotes and
					-- the governor's notes around them (a 4,000-character brief ranked by its asides)
					local field: string? = nil
					for line in string.gmatch(text .. "\n", "([^\n]*)\n") do
						if not string.find(line, "<answer>", 1, true) then
							local key, val = string.match(line, "^%-%s*([%w ]+):%s*(.*)$")
							if key then
								field = string.lower(key)
								if field == "what" then
									table.insert(parts, val)
									table.insert(parts, val)
								elseif field == "style" or field == "function" or field == "moving parts" then
									table.insert(parts, val)
								end
							elseif field == "what" and string.match(line, "^%s+%S") then
								table.insert(parts, line) -- the what line's continuation
							elseif
								(field == "hero features" or field == "parts plan")
								and string.match(line, "^%s*%d+%.")
							then
								table.insert(parts, string.match(line, "^%s*%d+%.%s*([^|]*)") or "")
							end
						end
					end
				else
					for line in string.gmatch(text, "[^\n]+") do
						if not string.find(line, "<answer>", 1, true) then
							table.insert(parts, line)
						end
					end
				end
				break
			end
		end
	end
	local q = table.concat(parts, " ")
	return if #q > 4000 then string.sub(q, 1, 4000) else q
end

-- the past pieces closest to `query` with the owner's verdict: the newest verdict per piece (the owner's own or read
-- from their words), plus graveyard routes that are no single piece; BM25 over the piece's name, the owner's words,
-- its tags and what decided it. -> up to k lines "score/10 name (date, loved|middling|failed): words [[link]]".
-- `core`: the piece's own name - a similar piece shares one of its words (a tester bed is near a box bed, not near
-- every "hero" row the brief's other words touch)
Vault.SIMILAR_WORDS = 2
function Vault.similar(dept: string, query: string, k: number?, core: string?): { string }
	local need: { [string]: boolean }? = nil
	if core and core ~= "" then
		need = {}
		for _, w in Vault.words(core) do
			(need :: any)[w] = true
		end
	end
	local docs = {}
	local seen: { [string]: boolean } = {}
	for _, v in Vault.verdicts(dept) do -- newest first: the newest verdict per piece speaks for it
		local key = citeKey(tostring(v.front.name or ""))
		if key ~= "" and not seen[key] then
			seen[key] = true
			local tags = if type(v.front.tags) == "table" then table.concat(v.front.tags, " ") else ""
			table.insert(docs, {
				text = `{v.front.name} {v.front.name} {tags} {v.body}`,
				name = tostring(v.front.name),
				score = tonumber(v.front.score),
				direction = Vault.direction(v.front),
				date = tostring(v.front.date or "?"),
				words = v.body,
				link = v.rel,
				route = false,
			})
		end
	end
	for _, r in Vault.rows(Vault.dir(dept, "graveyard.md")) do
		-- a row whose link is no verdict: a route that failed in research or across pieces
		local piece = r[1] or ""
		if piece ~= "" and not seen[citeKey(piece)] and not string.find(r[6] or "", "/verdicts/", 1, true) then
			table.insert(docs, {
				text = table.concat(r, " "),
				name = piece,
				score = nil,
				date = r[2] or "?",
				words = `{r[3] or ""}: {r[4] or ""} - {r[5] or ""}`,
				link = r[6] or "",
				route = true,
			})
		end
	end
	local out = {}
	for _, h in
		Vault.bm25(query, docs, function(d: any): string
			return d.text
		end)
	do
		if #out >= (k or 3) then
			break
		end
		-- one shared word is chance ("hero", "game"), not a similar piece: two at least (kit/tools/study.py's
		-- FAMILY_WORDS); nothing that close -> nothing shown
		if h.hits < Vault.SIMILAR_WORDS then
			continue
		end
		local d = h.doc
		if need and next(need) then
			local named = false
			for _, w in Vault.words(d.text) do
				if need[w] then
					named = true
					break
				end
			end
			if not named then
				continue
			end
		end
		local mood = if d.route
			then "failed route"
			elseif d.score == nil and d.direction == "keep" then "kept"
			elseif d.score == nil and d.direction == "redo" then "sent back"
			elseif d.score == nil then "no number"
			elseif d.score >= 7 then "loved"
			elseif d.score <= 3 then "failed"
			else "middling"
		local words = string.gsub(string.gsub(d.words, "%s+", " "), "^ ", "")
		if (utf8.len(words) or #words) > 140 then
			words = string.sub(words, 1, (utf8.offset(words, 138) or 138) - 1) .. "..."
		end
		local num = if d.score ~= nil
			then `{d.score}/10 `
			elseif d.direction == "keep" then "Keep "
			elseif d.direction == "redo" then "Redo "
			else ""
		table.insert(
			out,
			`- {num}{d.name} ({d.date}, {mood}): {words}{if d.link ~= ""
					and not string.find(d.link, "[[", 1, true)
				then " [[" .. d.link .. "]]"
				elseif d.link ~= "" then " " .. d.link
				else ""}`
		)
	end
	return out
end

-- a lesson note by its id (L-<dept>-<hex>), or nil
function Vault.lessonById(id: string): Note?
	local dept = string.match(id, "^L%-([^%-]+)%-%x+$")
	if not dept then
		return nil
	end
	for _, n in Vault.notes(dept, "lessons") do
		if Vault.lessonId(n) == id then
			return n
		end
	end
	return nil
end

-- verdicts of a department (or every department), newest first; `name` filters
function Vault.verdicts(dept: string?, name: string?): { Note }
	local out = {}
	for _, d in if dept then { dept } else Vault.DEPTS do
		for _, n in Vault.notes(d, "verdicts") do
			if not name or tostring(n.front.name) == name then
				table.insert(out, n)
			end
		end
	end
	-- newest first; the same day (this owner often scores a piece twice in a day) by the time written into the note,
	-- else the file name's sequence (<piece>--<date>-2 came after <piece>--<date>), else the file time (read BEFORE
	-- sorting: fs.metadata yields and a comparator cannot)
	local at: { [string]: number } = {}
	for _, n in out do
		at[n.path] = Vault.noteTime(n)
	end
	table.sort(out, function(a, b)
		local da, db = tostring(a.front.date or ""), tostring(b.front.date or "")
		if da ~= db then
			return da > db
		end
		local ta, tb = tonumber(a.front.time), tonumber(b.front.time)
		if ta and tb and ta ~= tb then
			return ta > tb
		end
		local sa, sb = Vault.noteSeq(a), Vault.noteSeq(b)
		if sa.piece == sb.piece and sa.n ~= sb.n then
			return sa.n > sb.n
		end
		return (at[a.path] or 0) > (at[b.path] or 0)
	end)
	return out
end

-- a verdict note's file-name sequence: "x/verdicts/barrel--2026-10-17-3" -> { piece = "barrel--2026-10-17", n = 3 }
-- (the first note of a piece on a day has no suffix: n = 1). Never changes when the note is edited or checked out.
function Vault.noteSeq(n: Note): { piece: string, n: number }
	local base = string.match(n.rel, "([^/]+)$") or n.rel
	local piece, seq = string.match(base, "^(.-%-%-%d%d%d%d%-%d%d%-%d%d)%-(%d+)$")
	if piece then
		return { piece = piece, n = tonumber(seq) :: number }
	end
	return { piece = base, n = 1 }
end

-- when a note was written: the `time` the kit wrote into it (unix seconds), else its file time (0 when unknown).
-- A file time moves when the note is edited or checked out, so new notes carry `time`.
function Vault.noteTime(n: Note): number
	local t = tonumber(n.front.time)
	if t then
		return t
	end
	local ok, meta = pcall(fs.metadata, n.path)
	if ok and meta and meta.modifiedAt then
		return meta.modifiedAt.unixTimestamp
	end
	return 0
end

-- does verdict `v` come AFTER a moment (a date, plus a unix time within that day)? A later day always does; the same
-- day only when the note was written at or after `at`
function Vault.after(v: Note, date: string, at: number?): boolean
	local d = tostring(v.front.date or "")
	if d ~= date then
		return d > date
	end
	return Vault.noteTime(v) >= (at or 0) -- (file times are whole seconds: the same second counts as after)
end

-- the newest owner verdict (score 0-10) for a piece, or nil; `ownerOnly` skips an inferred one (a score a model read
-- into the owner's words) and any record not by the owner (the quality locks: promote takes only the owner's own)
function Vault.scoreOf(kind: string, name: string, ownerOnly: boolean?): (number?, Note?)
	local dept = Vault.dept(kind)
	if not dept then
		return nil, nil
	end
	for _, n in Vault.verdicts(dept, name) do
		local s = tonumber(n.front.score)
		if
			ownerOnly
			and (
				not Vault.ownersOwn(n.front)
				or not string.match(string.lower(tostring(n.front.by or "owner")), "^%s*owner")
			)
		then
			s = nil
		end
		if s then
			return s, n
		end
	end
	return nil, nil
end

-- ------------------------------------------------------------ links + health
-- every [[target]] in a note; a target is a vault-relative path without .md ("3d/index", "3d/verdicts/x"), or a
-- bare note name that exists anywhere in the vault (Obsidian's shortest-path rule)
function Vault.links(text: string): { string }
	local out = {}
	for link in string.gmatch(text, "%[%[([^%]|#]+)[|#]?[^%]]*%]%]") do
		table.insert(out, (string.gsub(link, "%s+$", "")))
	end
	return out
end

function Vault.resolve(link: string, names: { [string]: boolean }): boolean
	local target = string.gsub(link, "%.md$", "")
	if fs.isFile(`{Vault.ROOT}/{target}.md`) or fs.isDir(`{Vault.ROOT}/{target}`) then
		return true -- a note, or a folder link ([[3d/lessons|folder]])
	end
	return names[string.lower(string.match(target, "([^/]+)$") or target)] == true
end

export type Problem = { path: string, problem: string }

-- the health check `kit verify` runs: frontmatter present and well formed (area, kind, date), links resolve,
-- every department has an index
function Vault.check(): { Problem }
	local problems: { Problem } = {}
	if not Vault.exists() then
		return problems -- a project without a vault is fine (kit install makes one)
	end
	local names: { [string]: boolean } = {}
	local files = Vault.files()
	for _, p in files do
		names[string.lower(string.match(p, "([^/]+)%.md$") or "")] = true
	end
	-- every department folder (the known ones and any the owner adds) has an index; a note's area is its folder
	local folders = {}
	for _, name in fs.readDir(Vault.ROOT) do
		local helper = string.sub(name, 1, 1) == "." or string.sub(name, 1, 1) == "_"
		if fs.isDir(`{Vault.ROOT}/{name}`) and not helper then
			table.insert(folders, name)
		end
	end
	table.sort(folders)
	for _, dept in folders do
		if not fs.isFile(Vault.dir(dept, "index.md")) then
			table.insert(problems, { path = Vault.dir(dept), problem = "no index.md (run: lune run kit vault index)" })
		end
	end
	for _, p in files do
		local text = fs.readFile(p)
		local isNote = string.find(p, "/lessons/", 1, true) or string.find(p, "/verdicts/", 1, true)
		-- an EMPTY note is Obsidian's "New note" left untitled in a folder: nothing to read, nothing broken
		if isNote and not string.match(text, "^%s*$") then
			local front, why = Vault.parse(text)
			if not front then
				table.insert(problems, { path = p, problem = why })
			else
				for _, key in { "area", "kind", "date" } do
					if front[key] == nil then
						table.insert(problems, { path = p, problem = `frontmatter has no "{key}"` })
					end
				end
				local folder = string.match(p, "^" .. string.gsub(Vault.ROOT, "%p", "%%%0") .. "/([^/]+)/")
				if front.area and folder and tostring(front.area) ~= folder then
					table.insert(
						problems,
						{ path = p, problem = `area "{front.area}" does not match its folder "{folder}"` }
					)
				end
				if front.kind == "verdict" then
					local s = tonumber(front.score)
					if front.score ~= nil and (not s or s < 0 or s > 10) then
						table.insert(problems, { path = p, problem = `score must be 0-10 (got {front.score})` })
					end
					if front.direction ~= nil and not Vault.direction(front) then
						table.insert(
							problems,
							{ path = p, problem = `direction must be keep or redo (got {front.direction})` }
						)
					end
				end
			end
		end
		for _, link in Vault.links(text) do
			if not Vault.resolve(link, names) then
				table.insert(problems, { path = p, problem = `dangling link [[{link}]]` })
			end
		end
	end
	return problems
end

-- ------------------------------------------------------------ the department page
local function firstLines(path: string, n: number): { string }
	if not fs.isFile(path) then
		return {}
	end
	local out = {}
	for line in string.gmatch(string.gsub(fs.readFile(path), "\r\n", "\n"), "[^\n]*") do
		if #out >= n then
			break
		end
		if line ~= "" then
			table.insert(out, line)
		end
	end
	return out
end

local function tableRows(path: string, n: number): { string }
	local rows = {}
	if not fs.isFile(path) then
		return rows
	end
	local all = {}
	for line in string.gmatch(string.gsub(fs.readFile(path), "\r\n", "\n"), "[^\n]+") do
		if
			string.sub(line, 1, 2) == "| "
			and not string.match(line, "^| ?%-%-")
			and not string.match(line, "^| tried")
			and not string.match(line, "^| piece")
		then
			table.insert(all, line)
		end
	end
	-- NEWEST FIRST by the date written in the row (seed rows were appended late; a row without a date counts as
	-- oldest; ties keep the later row first), so a page cut by its budget loses the oldest rows, never yesterday's
	local order = {}
	for i, line in all do
		table.insert(order, { i = i, date = string.match(line, "%d%d%d%d%-%d%d%-%d%d") or "" })
	end
	table.sort(order, function(a, b)
		if a.date ~= b.date then
			return a.date > b.date
		end
		return a.i > b.i
	end)
	for k = 1, math.min(n, #order) do
		table.insert(rows, all[order[k].i])
	end
	return rows
end

-- one page line per row: a long row is clipped so a few never crowd out the rest
local function clip(line: string, n: number): string
	local len = utf8.len(line)
	if len and len > n then
		return string.sub(line, 1, (utf8.offset(line, n - 2) or n - 2) - 1) .. "..."
	end
	return line
end

-- counts for the compact "all departments" block
function Vault.counts(dept: string): { lessons: number, verdicts: number, golden: number, graveyard: number }
	return {
		lessons = #Vault.files(dept, "lessons"),
		verdicts = #Vault.files(dept, "verdicts"),
		golden = #tableRows(Vault.dir(dept, "golden.md"), 1000),
		graveyard = #tableRows(Vault.dir(dept, "graveyard.md"), 1000),
	}
end

-- the page a model reads before building: index (its hand-written top), the golden set, the graveyard, the last
-- verdicts — cut to the token budget (the output says how much was cut; --full = everything)
-- the owner's standing orders for a department (<dept>/orders.md: one "- " line each, typed in Obsidian or filed from
-- the inbox as "- rule <dept> <words>"); a line the owner struck through (~~...~~) is withdrawn. `withSource` keeps
-- each line's trailing "(the owner, <date>; memory ...)" note (the file keeps it either way; the pages drop it)
function Vault.orders(dept: string, withSource: boolean?): { string }
	local path = Vault.dir(dept, "orders.md")
	if not fs.isFile(path) then
		return {}
	end
	local raw = fs.readFile(path)
	local front, body = Vault.parse(raw)
	if not front then
		body = raw -- typed in Obsidian without its properties block: the lines still count
	end
	local out = {}
	for line in string.gmatch(string.gsub(body, "\r\n", "\n"), "[^\n]+") do
		local o = string.match(line, "^%s*[-*]%s+(.+)$")
		if o and not string.match(o, "^~~.*~~") then
			o = string.gsub(o, "%s+$", "")
			if not withSource then
				o = string.gsub(o, "%s*%(the owner[^%)]*%)$", "")
			end
			table.insert(out, o)
		end
	end
	return out
end

-- (rulesCap: how many newest rules a short page shows - set by the page itself when the rules would push the record
-- past the budget; callers leave it out)
function Vault.page(dept: string, budget: number?, skipOrders: boolean?, rulesCap: number?): string
	local parts = {}
	local title = Vault.TITLES[dept] or dept
	table.insert(
		parts,
		`-- {dept} ({title}) — kit/knowledge/vault/{dept}/ (full page: lune run kit vault page {dept} --full)`
	)
	-- the owner's standing orders come first: the page is trimmed from its end, so they are never cut
	local orders = if skipOrders then {} else Vault.orders(dept)
	if #orders > 0 then
		table.insert(parts, "  STANDING ORDERS (the owner's; every session of this lane obeys them):")
		for _, o in orders do
			table.insert(parts, "    - " .. o)
		end
	end
	local idx = firstLines(Vault.dir(dept, "index.md"), 40)
	if #idx > 0 then
		for _, l in idx do
			-- the index's "Last handoff:" is the newest handoff of ANY lane: on a department's page it would point a
			-- session at another lane's work (kit start prints the lane's own; kit status the newest overall)
			if
				string.sub(l, 1, 2) ~= "# "
				and not string.match(l, "^<!%-%-")
				and not string.match(l, "^Last handoff:")
			then
				table.insert(parts, "  " .. l)
			end
		end
	else
		table.insert(parts, "  (no index yet: lune run kit vault index " .. dept .. ")")
	end
	-- the department's latest distilled rules (distil.md's last "## date" section): a model reads 3 rules before
	-- hundreds of lessons
	local distilPath = Vault.dir(dept, "distil.md")
	local live = {}
	for _, r in Vault.rules(dept) do
		if not r.retired then
			table.insert(live, r)
		end
	end
	if #live > 0 then
		local counts = Vault.lessonCounts()
		table.insert(
			parts,
			`  RULES (live, {dept}/rules.md; hypotheses until the owner's next verdict; cite with kit lesson used R-...):`
		)
		-- a short page (kit start) shows the NEWEST rules, tighter, and names the rest: an uncapped list grew past the
		-- whole start budget and pushed the owner's verdicts, golden set and graveyard off the page (3d / vfx / anim,
		-- 2026-10-29: start.spec's page check went red on the committed tree)
		local short = budget ~= nil and budget < 2500
		local cap = if short then (rulesCap or Vault.RULES_SHORT) else #live
		local textClip = if short then 160 else 240
		local first = math.max(1, #live - cap + 1)
		if first > 1 then
			table.insert(parts, `    ... {first - 1} older live rule(s): lune run kit vault page {dept} --full`)
		end
		for i = first, #live do
			local r = live[i]
			local k = counts[r.id]
			local tag = if k then ` +{k.helpful}/-{k.harmful}{if k.flagged then " FLAGGED harmful" else ""}` else ""
			local text = if #r.text > textClip then string.sub(r.text, 1, textClip - 3) .. "..." else r.text
			table.insert(parts, `    {r.id}{tag}: {text}`)
		end
	elseif fs.isFile(distilPath) then
		local text = string.gsub(fs.readFile(distilPath), "\r\n", "\n")
		-- the LAST "## YYYY-MM-DD" section: find each heading's start, keep the text from the final one on
		local last = nil
		local at = 1
		while true do
			local s = string.find(text, "\n## %d%d%d%d%-%d%d%-%d%d", at)
			if not s then
				break
			end
			last = string.sub(text, s + 1)
			at = s + 1
		end
		if last then
			local date = string.match(last, "^## (%d%d%d%d%-%d%d%-%d%d)") or "?"
			table.insert(parts, `  RULES (distilled {date}; hypotheses until the owner's next verdict):`)
			for line in string.gmatch(last, "[^\n]+") do
				local rule = string.match(line, "^%d+%.%s+(.+)$")
				if rule then
					if #rule > 240 then
						rule = string.sub(rule, 1, 237) .. "..."
					end
					table.insert(parts, "   - " .. rule)
				end
			end
		end
	end
	-- the owner's newest verdicts come right after the rules: the freshest signal must survive the budget cut
	local verdicts = Vault.verdicts(dept)
	if #verdicts > 0 then
		table.insert(parts, "  LAST VERDICTS (the owner's, newest first):")
		for i = 1, math.min(3, #verdicts) do
			local f = verdicts[i].front
			local words = string.gsub(verdicts[i].body, "%s+", " ")
			if #words > 160 then
				words = string.sub(words, 1, 157) .. "..."
			end
			table.insert(parts, `   {f.date or "?"} {f.name or "?"}: {Vault.said(f)} — {words}`)
		end
	end
	-- a short page (kit start, the lane gate) keeps BOTH the newest loved pieces and the newest failed routes in view:
	-- fewer, tighter rows of each instead of a long golden list that pushes the graveyard off the page
	local tight = budget ~= nil and budget < 2500
	local rowClip = if tight then 150 else 200
	local golden = tableRows(Vault.dir(dept, "golden.md"), if tight then 4 else 8)
	if #golden > 0 then
		table.insert(parts, "  GOLDEN (loved, newest first; copy the feature, never the look):")
		for _, r in golden do
			table.insert(parts, "   " .. clip(r, rowClip))
		end
	end
	local grave = tableRows(Vault.dir(dept, "graveyard.md"), if tight then 5 else 10)
	if #grave > 0 then
		table.insert(parts, "  GRAVEYARD (newest first; do not retry without the owner's words):")
		for _, r in grave do
			table.insert(parts, "   " .. clip(r, rowClip))
		end
	end
	local text = table.concat(parts, "\n")
	local limit = (budget or 1500) * 4
	-- a short page whose rules push the department's record (the owner's verdicts, golden set, graveyard) past the
	-- budget shows one rule fewer, down to the newest one: the record is the owner's own words and the rules a
	-- reading of them, one command away (2026-11-20: the 3D distil took its live rules from 3 to 6, the start sheet's
	-- page lost LAST VERDICTS and start.spec went red)
	if budget ~= nil and budget < 2500 and #live > 1 and #text > limit then
		local at: number? = nil
		for _, mark in { "LAST VERDICTS", "GOLDEN", "GRAVEYARD" } do
			local s = string.find(text, mark, 1, true)
			if s and (at == nil or s < (at :: number)) then
				at = s
			end
		end
		local shown = math.min(rulesCap or Vault.RULES_SHORT, #live)
		if at ~= nil and (at :: number) + Vault.RECORD_ROOM > limit and shown > 1 then
			return Vault.page(dept, budget, skipOrders, shown - 1)
		end
	end
	if #text > limit then
		-- the cut note counts against the budget too: a trimmed page is never over it
		local function note(n: number): string
			return `\n  ... ({n} chars cut by the vault budget: lune run kit vault page {dept} --full, or raise vault.budget in kit.config.json)`
		end
		local keep = math.max(0, limit - #note(#text))
		text = string.sub(text, 1, keep) .. note(#text - keep)
	end
	return text
end

-- ------------------------------------------------------------ the index (an auto block the kit refreshes)
local AUTO_OPEN, AUTO_CLOSE = "<!-- kit:auto -->", "<!-- /kit:auto -->"

function Vault.indexText(dept: string, lastHandoff: string?): string
	local c = Vault.counts(dept)
	local lines = {
		AUTO_OPEN,
		`Lessons: {c.lessons}{if fs.isDir(Vault.dir(dept, "lessons")) then ` ([[{dept}/lessons|folder]])` else ""} · Verdicts: {c.verdicts} · Golden: {c.golden}{if fs.isFile(
				Vault.dir(dept, "golden.md")
			)
			then ` ([[{dept}/golden]])`
			else ""} · Graveyard: {c.graveyard}{if fs.isFile(Vault.dir(dept, "graveyard.md"))
			then ` ([[{dept}/graveyard]])`
			else ""}`,
	}
	if lastHandoff then
		table.insert(lines, `Last handoff: {lastHandoff}`)
	end
	table.insert(lines, `Refreshed {Vault.today()} by \`kit vault index\`.`)
	table.insert(lines, AUTO_CLOSE)
	return table.concat(lines, "\n")
end

function Vault.refreshIndex(dept: string, lastHandoff: string?): string
	local path = Vault.dir(dept, "index.md")
	ensureDir(Vault.dir(dept))
	local auto = Vault.indexText(dept, lastHandoff)
	local text
	if fs.isFile(path) then
		text = string.gsub(fs.readFile(path), "\r\n", "\n")
		local a = string.find(text, AUTO_OPEN, 1, true)
		local b = string.find(text, AUTO_CLOSE, 1, true)
		if a and b then
			text = string.sub(text, 1, a - 1) .. auto .. string.sub(text, b + #AUTO_CLOSE)
		else
			text = text .. "\n" .. auto .. "\n"
		end
	else
		text = `# {Vault.TITLES[dept] or dept} — the department's page\n\n`
			.. "<!-- Hand-written part: the route in five lines, the owner's rules, what to read next. The kit keeps the block below. -->\n\n"
			.. auto
			.. "\n"
	end
	fs.writeFile(path, text)
	return path
end

-- ------------------------------------------------------------ the record
-- the written verdict: the note + its golden / graveyard row. Every kit command that takes the owner's verdict
-- (grade, ui judge --owner, vfx vault verdict, anim verdict, sfx listen) calls this so there is ONE record.
function Vault.record(
	opts: {
		kind: string,
		name: string,
		score: number?,
		words: string,
		tags: { string }?,
		vs: string?,
		build: string?,
		feature: string?,
		inferred: boolean?,
		quotedFrom: string?,
		date: string?,
		by: string?,
		route: string?, -- what was tried, for a rejection: the graveyard row names the route, not just the piece
		direction: string?, -- the owner's Keep / Redo instead of a number (never averaged, never golden / graveyard)
		judged: string?, -- vault-relative copy of what the owner looked at (kit/tools/judged.py)
		judgedFrom: string?, -- the file it was copied from
		look: string?, -- "seen" / "missing": the session's own look at this version (enforced learning, rule 3)
	}
): (string?, string?)
	local dept = Vault.dept(opts.kind)
	if not dept then
		return nil, `unknown kind "{opts.kind}" (asset|vfx|screen|sound|world|anim|system|playtest|kit)`
	end
	if opts.direction ~= nil and not Vault.DIRECTIONS[opts.direction] then
		return nil, `direction must be keep or redo (got "{opts.direction}")`
	end
	if opts.direction ~= nil and opts.score ~= nil then
		return nil, "a verdict carries a number OR a Keep / Redo, not both"
	end
	local date = opts.date or Vault.today()
	local front: Front = {
		kind = "verdict",
		area = dept,
		name = opts.name,
		score = opts.score,
		direction = opts.direction,
		judged = opts.judged,
		judged_from = opts.judgedFrom,
		look = opts.look,
		date = date,
		build = opts.build,
		by = opts.by or "owner",
		source = if opts.inferred then "inferred" elseif opts.quotedFrom then "quoted" else "owner",
		time = os.time(), -- orders this verdict within its day (a file time moves on edits and checkouts)
		quoted_from = opts.quotedFrom,
		vs = opts.vs,
		tags = if opts.tags and #opts.tags > 0 then opts.tags else nil,
		links = { `[[{dept}/index]]`, `[[{dept}/golden]]`, `[[{dept}/graveyard]]` },
	}
	local body = opts.words
	if opts.feature and opts.feature ~= "" then
		body ..= `\n\nWhat decided it: {opts.feature}`
	end
	if opts.route and opts.route ~= "" then
		body ..= `\n\nThe route that failed: {opts.route}`
	end
	if opts.judged and opts.judged ~= "" then
		-- plain text, not a [[link]]: the vault's link check resolves notes, and this is an image or a sound
		body ..= `\n\nWhat the owner judged: kit/knowledge/vault/{opts.judged}`
	end
	local path = Vault.note(dept, "verdicts", `{Vault.slug(opts.name)}--{date}`, front, body)
	local link = `[[{string.sub(path, #Vault.ROOT + 2, -4)}]]`
	if opts.score and opts.score >= 7 then
		Vault.row(dept, "golden.md", Vault.GOLDEN_HEADER, {
			opts.name,
			tostring(opts.score),
			date,
			opts.words,
			opts.feature or "",
			link,
		})
	elseif opts.score and opts.score <= 3 then
		Vault.row(dept, "graveyard.md", Vault.GRAVEYARD_HEADER, {
			if opts.route and opts.route ~= "" then `{opts.name}: {opts.route}` else opts.name,
			date,
			`rejected ({opts.score}/10)`,
			opts.words,
			opts.feature or "the owner's words above",
			link,
		})
	end
	return path, nil
end

-- ------------------------------------------------------------ calibration: do judge scores track the owner?
-- per department: pieces with BOTH a judge score (the kit's own stores) and an owner verdict -> n, Spearman rank
-- correlation, mean absolute error on the 0-10 scale. Leave-one-out is meaningless under n ~ 10; the honest line is
-- n + rank + error, and "too few" below n = 4.
local function judgeScores(): { [string]: { [string]: number } }
	local out: { [string]: { [string]: number } } = { ui = {}, ["3d"] = {}, vfx = {}, anim = {} }
	-- UI: assets/ui/<Screen>.judge.json score (0-100)
	local uiDir = Config.path("ui")
	if fs.isDir(uiDir) then
		for _, f in fs.readDir(uiDir) do
			local screen = string.match(f, "^(.+)%.judge%.json$")
			if screen then
				local ok, j = pcall(serde.decode, "json" :: any, fs.readFile(`{uiDir}/{f}`))
				if ok and type(j) == "table" and tonumber(j.score) then
					out.ui[screen] = tonumber(j.score) :: number / 10
				end
			end
		end
	end
	-- 3D: .verify/judge-<asset>.json summary "judge: <asset> NN.N/100"
	if fs.isDir(".verify") then
		for _, f in fs.readDir(".verify") do
			local asset = string.match(f, "^judge%-(.+)%.json$")
			if asset then
				local ok, j = pcall(serde.decode, "json" :: any, fs.readFile(".verify/" .. f))
				local s = ok and type(j) == "table" and string.match(tostring(j.summary or ""), "(%d+%.?%d*)/100")
				if s then
					out["3d"][asset] = tonumber(s) :: number / 10
				end
			end
		end
	end
	return out
end

local function spearman(pairs: { { number } }): number?
	local n = #pairs
	if n < 2 then
		return nil
	end
	local function ranks(idx: number): { number }
		local order = {}
		for i = 1, n do
			order[i] = i
		end
		table.sort(order, function(a, b)
			return pairs[a][idx] < pairs[b][idx]
		end)
		local r = {}
		local i = 1
		while i <= n do
			local j = i
			while j < n and pairs[order[j + 1]][idx] == pairs[order[i]][idx] do
				j += 1
			end
			for k = i, j do
				r[order[k]] = (i + j) / 2
			end
			i = j + 1
		end
		return r
	end
	local ra, rb = ranks(1), ranks(2)
	local ma, mb = 0, 0
	for i = 1, n do
		ma += ra[i]
		mb += rb[i]
	end
	ma /= n
	mb /= n
	local num, da, db = 0, 0, 0
	for i = 1, n do
		num += (ra[i] - ma) * (rb[i] - mb)
		da += (ra[i] - ma) ^ 2
		db += (rb[i] - mb) ^ 2
	end
	if da == 0 or db == 0 then
		return nil
	end
	return num / math.sqrt(da * db)
end

function Vault.calibration(): { string }
	local lines = {}
	local judged = judgeScores()
	for _, dept in { "3d", "vfx", "ui", "anim", "sfx", "world", "code" } do
		local pairs = {}
		for name, js in judged[dept] or {} do
			local s = Vault.scoreOf(dept, name)
			if s then
				table.insert(pairs, { js, s })
			end
		end
		local n = #pairs
		if n == 0 then
			table.insert(lines, `{dept}: no piece has both a judge score and an owner verdict yet`)
		elseif n < 4 then
			table.insert(lines, `{dept}: n={n} — too few to say (need 4+)`)
		else
			local err = 0
			for _, p in pairs do
				err += math.abs(p[1] - p[2])
			end
			local rho = spearman(pairs)
			table.insert(
				lines,
				`{dept}: n={n} rank {if rho then string.format("%.2f", rho) else "n/a"} mean error {string.format(
					"%.1f",
					err / n
				)}/10 — {if rho and rho >= 0.6
					then "judges track the owner"
					else "judges do NOT track the owner: use them for bugs, not the bar"}`
			)
		end
	end
	return lines
end

-- ------------------------------------------------------------ supersedes: what replaced what
-- A note may say `supersedes: ["[[3d/lessons/<old>]]"]` (and the old one `superseded_by: "[[...]]"`): the newer
-- lesson or verdict replaces the older one. Superseded LESSONS drop out of `kit lessons` and the department page
-- (the record keeps them; Obsidian shows both and the link between them). Verdicts are history: never hidden.
local function linkTargets(v: any): { string }
	local out = {}
	local items = if type(v) == "table" then v elseif type(v) == "string" then { v } else {}
	for _, item in items do
		local t = string.match(tostring(item), "%[%[([^%]|#]+)") or tostring(item)
		table.insert(out, (string.gsub(string.gsub(t, "%.md$", ""), "^%s+", "")))
	end
	return out
end

-- every note named in some note's `supersedes` (vault-relative path without .md, lowercased)
function Vault.supersededSet(): { [string]: boolean }
	local set: { [string]: boolean } = {}
	for _, p in Vault.files() do
		local note = Vault.read(p)
		if note and note.front.supersedes ~= nil then
			for _, t in linkTargets(note.front.supersedes) do
				set[string.lower(t)] = true
			end
		end
		if note and note.front.superseded_by ~= nil then
			set[string.lower(note.rel)] = true
		end
	end
	return set
end

-- the body texts of a department's superseded lessons (whitespace-collapsed), for filtering one-line views
function Vault.retiredLessonTexts(dept: string): { [string]: boolean }
	local set = Vault.supersededSet()
	local texts: { [string]: boolean } = {}
	for _, n in Vault.notes(dept, "lessons") do
		if set[string.lower(n.rel)] then
			local t = string.gsub(string.gsub(string.gsub(n.body, "%s+", " "), "^%s+", ""), "%s+$", "")
			texts[t] = true
		end
	end
	return texts
end

-- find a note by vault-relative path ("3d/lessons/x") or bare file name ("x"); nil when none or ambiguous
function Vault.findNote(ref: string): Note?
	local target = string.lower((string.gsub(string.gsub(ref, "%.md$", ""), "^%[%[(.-)%]%]$", "%1")))
	local hit: Note? = nil
	for _, p in Vault.files() do
		local note = Vault.read(p)
		if note then
			local rel = string.lower(note.rel)
			local base = string.match(rel, "([^/]+)$") or rel
			if rel == target or base == target then
				if hit then
					return nil -- two notes share that name: say the path
				end
				hit = note
			end
		end
	end
	return hit
end

-- record that `newer` supersedes `older` (both notes; the frontmatter of each gains its side of the link)
function Vault.supersede(newerRef: string, olderRef: string, why: string?): (boolean, string)
	local newer, older = Vault.findNote(newerRef), Vault.findNote(olderRef)
	if not newer then
		return false, `no single note "{newerRef}" (give its path, e.g. 3d/lessons/<name>)`
	end
	if not older then
		return false, `no single note "{olderRef}" (give its path, e.g. 3d/lessons/<name>)`
	end
	if newer.path == older.path then
		return false, "a note cannot supersede itself"
	end
	local list = linkTargets(newer.front.supersedes)
	local olderLink = `[[{older.rel}]]`
	local present = false
	for _, t in list do
		if string.lower(t) == string.lower(older.rel) then
			present = true
		end
	end
	local links = {}
	for _, t in list do
		table.insert(links, `[[{t}]]`)
	end
	if not present then
		table.insert(links, olderLink)
	end
	newer.front.supersedes = links
	Vault.write(newer.path, newer.front, newer.body)
	older.front.superseded_by = `[[{newer.rel}]]`
	if why and why ~= "" then
		older.front.superseded_why = why
	end
	Vault.write(older.path, older.front, older.body)
	return true, `{newer.rel} supersedes {older.rel}`
end

-- ------------------------------------------------------------ related: the graph, walked deterministically
-- The notes linked to a note (its links out and its backlinks in), and theirs one hop further, as one line each —
-- the knowledge-graph view a model needs ("what else touches this"), with no database and no model call. The index,
-- golden and graveyard pages every note links to are hubs: they are named once, never expanded (they would pull
-- in the whole department).
local HUB = { index = true, golden = true, graveyard = true, distil = true, readme = true }

export type Related = { rel: string, hop: number, title: string, via: string }

function Vault.related(ref: string, hops: number?, limit: number?): ({ Related }, string?)
	local start = Vault.findNote(ref)
	if not start then
		return {}, `no single note "{ref}" (give its path, e.g. 3d/lessons/<name>)`
	end
	-- the link graph, both directions, between notes (folders / hubs skipped as targets to expand)
	-- every markdown file is a node, with or without frontmatter (index, golden and graveyard pages have none)
	local byRel: { [string]: { path: string, rel: string, front: Front, body: string } } = {}
	local out: { [string]: { string } } = {}
	local inbound: { [string]: { string } } = {}
	local byBase: { [string]: string } = {}
	for _, p in Vault.files() do
		local relPath = string.sub(p, #Vault.ROOT + 2, -4)
		local n = Vault.read(p)
		local text = string.gsub(fs.readFile(p), "\r\n", "\n")
		local node = if n then n else { path = p, rel = relPath, front = {}, body = text }
		byRel[string.lower(relPath)] = node
		byBase[string.lower(string.match(relPath, "([^/]+)$") or relPath)] = string.lower(relPath)
	end
	for rel, n in byRel do
		local text = fs.readFile(n.path)
		for _, l in Vault.links(text) do
			local t = string.lower((string.gsub(l, "%.md$", "")))
			local target = if byRel[t] then t else byBase[string.match(t, "([^/]+)$") or t]
			if target and target ~= rel then
				out[rel] = out[rel] or {}
				table.insert(out[rel], target)
				inbound[target] = inbound[target] or {}
				table.insert(inbound[target], rel)
			end
		end
	end
	local function isHub(rel: string): boolean
		return HUB[string.match(rel, "([^/]+)$") or rel] == true
	end
	-- implicit edges the notes rarely spell out as links: the same piece (`name:`) judged again, and lessons /
	-- decisions that mention the piece by name (names of 5+ characters, so "x" or "sword" stays out)
	local startRel = string.lower(start.rel)
	local pieceName = start.front.name and string.lower(tostring(start.front.name)) or nil
	if pieceName then
		local plain = string.gsub(pieceName, "%p", "%%%0")
		for rel, n in byRel do
			if rel ~= startRel then
				local samePiece = n.front.name and string.lower(tostring(n.front.name)) == pieceName
				local isText = string.find(rel, "/lessons/", 1, true) or string.find(rel, "/decisions/", 1, true)
				local mentions = isText and #pieceName >= 5 and string.find(string.lower(n.body), plain) ~= nil
				if samePiece or mentions then
					out[startRel] = out[startRel] or {}
					table.insert(out[startRel], rel)
				end
			end
		end
	end
	local maxHops, maxN = hops or 2, limit or 25
	local seen: { [string]: boolean } = { [string.lower(start.rel)] = true }
	local result: { Related } = {}
	local frontier = { string.lower(start.rel) }
	for hop = 1, maxHops do
		local nextFrontier = {}
		for _, rel in frontier do
			if hop > 1 and isHub(rel) then
				continue
			end
			for dir, list in { ["links to"] = out[rel] or {}, ["linked from"] = inbound[rel] or {} } do
				for _, other in list do
					if not seen[other] and #result < maxN then
						seen[other] = true
						local n = byRel[other]
						local first = n
								and (string.match(n.body, "^#+%s*([^\n]+)") or string.match(n.body, "^([^\n]+)"))
							or ""
						local title = if n and n.front.name then tostring(n.front.name) .. ": " .. first else first
						title = string.gsub(title, "%s+", " ")
						if #title > 110 then
							title = string.sub(title, 1, 107) .. "..."
						end
						table.insert(result, { rel = other, hop = hop, title = title, via = `{dir} {rel}` })
						if not isHub(other) then
							table.insert(nextFrontier, other)
						end
					end
				end
			end
		end
		frontier = nextFrontier
	end
	table.sort(result, function(a, b)
		if a.hop ~= b.hop then
			return a.hop < b.hop
		end
		return a.rel < b.rel
	end)
	return result, nil
end

-- a words search: every note whose text (body + name) holds ALL the words, verdicts first, decisions next, then the
-- rest — newest first inside each group. The body's first 100 characters (whitespace collapsed) is the title.
function Vault.search(words: { string }, limit: number?): { Related }
	if #words == 0 then
		return {}
	end
	local needles = {}
	for _, w in words do
		table.insert(needles, string.lower(w))
	end
	local found = {}
	for _, p in Vault.files() do
		local note = Vault.read(p)
		if note then
			local text = string.lower(note.body .. " " .. tostring(note.front.name or ""))
			local all = true
			for _, w in needles do
				if not string.find(text, w, 1, true) then
					all = false
					break
				end
			end
			if all then
				table.insert(found, note)
			end
		end
	end
	local function rank(kind: any): number
		if kind == "verdict" then
			return 1
		elseif kind == "decision" then
			return 2
		end
		return 3
	end
	table.sort(found, function(a, b)
		local ra, rb = rank(a.front.kind), rank(b.front.kind)
		if ra ~= rb then
			return ra < rb
		end
		local da, db = tostring(a.front.date or ""), tostring(b.front.date or "")
		if da ~= db then
			return da > db
		end
		return a.rel < b.rel
	end)
	local out: { Related } = {}
	for i = 1, math.min(#found, limit or 25) do
		local note = found[i]
		local title = string.gsub(string.gsub(note.body, "%s+", " "), "^ ", "")
		local chars = utf8.len(title)
		if chars == nil then
			title = string.sub(title, 1, 100) -- invalid UTF-8: the byte cut is all we can trust
		elseif chars > 100 then
			title = string.sub(title, 1, utf8.offset(title, 101) - 1)
		end
		table.insert(out, { rel = note.rel, hop = 0, title = title, via = "words" })
	end
	return out
end

-- the token cost of each department's page: printed as-is (within the budget) and in full, so growth is visible
function Vault.tokenMeter(budget: number?): { { dept: string, shown: number, full: number, cut: boolean } }
	local rows = {}
	for _, d in Vault.DEPTS do
		if fs.isDir(Vault.dir(d)) then
			local shown = Vault.tokens(Vault.page(d, budget))
			local full = Vault.tokens(Vault.page(d, 1e9))
			table.insert(rows, { dept = d, shown = shown, full = full, cut = full > shown })
		end
	end
	return rows
end

-- ------------------------------------------------------------ is the vault behind the lanes' own stores?
-- Each lane keeps its own record (a UI screen's judge file, library/vfx/verdicts.json, a sound's .verdict.json,
-- the anim book, kit/lessons). kit/scripts/vault_migrate.py files them into the vault and stamps each store's sync
-- time in .verify/vault_sync.json. A store file modified after its stamp = the vault may be missing what it holds.
-- File times only: no python, no parsing, milliseconds (a full dry-run sync takes ~5 s, too slow for kit status).
Vault.STORE_FILES = {
	lessons = { dir = "kit/lessons", suffix = ".md" },
	ui = { dir = "assets/ui", suffix = ".judge.json" },
	vfx = { file = "library/vfx/verdicts.json" },
	anim = { file = "assets/animations/verdicts.json" },
	sfx = { dir = "assets/sounds", suffix = ".verdict.json" },
}

local function mtime(path: string): number
	local ok, meta = pcall(fs.metadata, path)
	if ok and meta and meta.modifiedAt then
		return meta.modifiedAt.unixTimestamp
	end
	return 0
end

export type Behind = { store: string, files: number, never: boolean }

function Vault.behind(stampPath: string?): { Behind }
	local out: { Behind } = {}
	local path = stampPath or ".verify/vault_sync.json"
	local stamps: { [string]: number } = {}
	if fs.isFile(path) then
		local ok, decoded = pcall(serde.decode, "json" :: any, fs.readFile(path))
		if ok and type(decoded) == "table" then
			stamps = decoded
		end
	end
	local order = { "lessons", "ui", "vfx", "anim", "sfx" }
	for _, store in order do
		local spec = Vault.STORE_FILES[store]
		local files = {}
		if spec.file and fs.isFile(spec.file) then
			table.insert(files, spec.file)
		elseif spec.dir and fs.isDir(spec.dir) then
			for _, f in fs.readDir(spec.dir) do
				if string.sub(f, -#spec.suffix) == spec.suffix then
					table.insert(files, `{spec.dir}/{f}`)
				end
			end
		end
		local stamp = tonumber(stamps[store])
		local n = 0
		for _, f in files do
			if not stamp or mtime(f) > stamp + 1 then
				n += 1
			end
		end
		if n > 0 then
			table.insert(out, { store = store, files = n, never = stamp == nil })
		end
	end
	return out
end

-- the lane stores a department's verdicts live in before the vault files them (the stores Vault.behind checks)
Vault.STORES_OF = { ui = { "ui" }, vfx = { "vfx" }, anim = { "anim" }, sfx = { "sfx" } }

-- catch the vault up by itself (no "remember to run kit vault sync"): the stores that are behind their last sync
-- (limited to `stores` when given; lessons always ride along) and the owner's inbox are filed now by
-- kit/scripts/vault_migrate.py (~0.3 s). Returns what was filed (store names, "inbox") and whether the sync ran clean.
function Vault.catchUp(stores: { string }?): ({ string }, boolean)
	local want: { [string]: boolean }? = nil
	if stores then
		want = { lessons = true }
		for _, s in stores do
			(want :: { [string]: boolean })[s] = true
		end
	end
	local only = {}
	for _, b in Vault.behind() do
		if not want or want[b.store] then
			table.insert(only, b.store)
		end
	end
	if Vault.inboxPending() > 0 then
		table.insert(only, "inbox")
	end
	if #only == 0 then
		return {}, true
	end
	local process = require("@lune/process")
	local Run = require("./run")
	local ok, r =
		pcall(process.exec, Run.tool("python"), { "kit/scripts/vault_migrate.py", "--only", table.concat(only, ",") })
	-- what is no longer behind is what got filed (another session holding the sync lock files nothing: still behind)
	local still: { [string]: boolean } = {}
	for _, b in Vault.behind() do
		still[b.store] = true
	end
	if Vault.inboxPending() > 0 then
		still.inbox = true
	end
	local filed = {}
	for _, s in only do
		if not still[s] then
			table.insert(filed, s)
		end
	end
	return filed, ok and r.ok and #filed == #only
end

-- lines the owner wrote under "## New" in the vault's inbox.md that no sync has filed yet (a line a sync could not
-- read carries "<- not filed:" and is counted apart)
function Vault.inboxPending(): (number, number)
	local path = `{Vault.ROOT}/inbox.md`
	if not fs.isFile(path) then
		return 0, 0
	end
	local text = string.gsub(fs.readFile(path), "\r\n", "\n")
	local newPart = string.match(text, "## New\n(.-)\n## Filed") or string.match(text, "## New\n(.*)$") or ""
	local pending, unreadable = 0, 0
	for line in string.gmatch(newPart, "[^\n]+") do
		if string.match(line, "^%s*%- ") then
			if string.find(line, "<- not filed:", 1, true) then
				unreadable += 1
			else
				pending += 1
			end
		end
	end
	return pending, unreadable
end

-- ------------------------------------------------------------ the weekly audit (warnings, never a gate)
-- the cells of every data row of a department table (golden.md / graveyard.md), header + separator skipped
function Vault.rows(path: string): { { string } }
	local rows = {}
	if not fs.isFile(path) then
		return rows
	end
	local first = true
	for line in string.gmatch(string.gsub(fs.readFile(path), "\r\n", "\n"), "[^\n]+") do
		if string.sub(line, 1, 2) == "| " and not string.match(line, "^| ?%-%-") then
			if first then
				first = false -- the header row
			else
				local cells = {}
				for cell in string.gmatch(string.sub(line, 2), "([^|]*)|") do
					table.insert(cells, (string.gsub(string.gsub(cell, "^%s+", ""), "%s+$", "")))
				end
				table.insert(rows, cells)
			end
		end
	end
	return rows
end

export type Warning = { dept: string, where: string, warning: string }

-- what `kit vault check` lists under "weekly": a golden row whose piece was rejected LATER (stale: the golden set
-- would still sell the route), a golden row without a verdict link (nothing backs it), a graveyard row with no
-- "do not retry because" (a grave without a reason gets re-dug), a verdict note with no words (a number is not
-- a verdict). None fails verify: they need a human's eyes, not a fix by the next model.
function Vault.audit(): { Warning }
	local out: { Warning } = {}
	if not Vault.exists() then
		return out
	end
	local names: { [string]: boolean } = {}
	local shared: { [string]: number } = {} -- how many notes carry each file name
	for _, p in Vault.files() do
		local base = string.lower(string.match(p, "([^/]+)%.md$") or "")
		names[base] = true
		shared[base] = (shared[base] or 0) + 1
	end
	-- a bare link to a name several notes carry ([[golden]]: every lane has one) opens whichever Obsidian finds first -
	-- maybe another lane's page; the check resolves it by name alone, so it passed (2026-11-08, sprint 4). A warning,
	-- never a failure: a link the owner writes in Obsidian must not turn kit verify red
	local rootPat = "^" .. string.gsub(Vault.ROOT, "%p", "%%%0") .. "/([^/]+)/"
	for _, p in Vault.files() do
		for _, link in Vault.links(fs.readFile(p)) do
			local target = string.lower(string.gsub(link, "%.md$", ""))
			if not string.find(target, "/", 1, true) and (shared[target] or 0) > 1 then
				table.insert(out, {
					dept = string.match(p, rootPat) or "?",
					where = p,
					warning = `the link [[{link}]] names {shared[target]} notes of that name: write the lane, [[<lane>/{link}]]`,
				})
			end
		end
	end
	for _, dept in Vault.DEPTS do
		local verdicts = Vault.verdicts(dept)
		-- a piece rejected AGAIN in the last week: what route the second round took, and why the graveyard row did
		-- not stop it, is the question for the next session of that lane
		for _, r in Vault.repeats(dept).all do
			if r.recent then
				table.insert(out, {
					dept = dept,
					where = `{dept}/verdicts ({r.name})`,
					warning = `{r.name} rejected again on {r.date} ({r.score}/10), first rejected {r.first}: did the graveyard row name the route that failed?`,
				})
			end
		end
		for _, row in Vault.rows(Vault.dir(dept, "golden.md")) do
			local piece, score, when, link = row[1], tonumber(row[2]), row[3] or "", row[6] or ""
			if link == "" or not Vault.resolve((string.match(link, "%[%[([^%]|]+)") or link), names) then
				table.insert(out, {
					dept = dept,
					where = `{dept}/golden.md`,
					warning = `golden row "{piece}" has no verdict note behind it`,
				})
			end
			for _, v in verdicts do
				-- a later rejection: 3 or less, or the owner's Redo
				if
					tostring(v.front.name) == piece
					and Vault.polarity(v.front) == -1
					and tostring(v.front.date or "") > when
				then
					table.insert(out, {
						dept = dept,
						where = `{dept}/golden.md`,
						warning = `golden row "{piece}" ({score or "?"}/10, {when}) is STALE: rejected {if v.front.score
								~= nil
							then Vault.said(v.front)
							else "with a Redo"} on {v.front.date} — move it to the graveyard or add the owner's words`,
					})
					break
				end
			end
		end
		for _, row in Vault.rows(Vault.dir(dept, "graveyard.md")) do
			local tried, why, link = row[1], row[5] or "", row[6] or ""
			if why == "" or why == "the owner's words above" and (row[4] or "") == "" then
				table.insert(out, {
					dept = dept,
					where = `{dept}/graveyard.md`,
					warning = `graveyard row "{tried}" says nothing about WHY — a grave without a reason gets re-dug`,
				})
			end
			if link == "" then
				table.insert(out, {
					dept = dept,
					where = `{dept}/graveyard.md`,
					warning = `graveyard row "{tried}" has no source (a verdict note, a plan, a handoff)`,
				})
			end
		end
		for _, v in verdicts do
			if string.gsub(v.body, "%s+", "") == "" then
				table.insert(
					out,
					{ dept = dept, where = v.rel, warning = "a verdict with no words (a number is not a verdict)" }
				)
			end
		end
	end
	return out
end

-- ------------------------------------------------------------ distil: verdicts + lessons since the last distil
local function dateOnly(v: any): string
	return string.match(tostring(v or ""), "^%d%d%d%d%-%d%d%-%d%d") or ""
end

-- the date of the last "## YYYY-MM-DD" heading in <dept>/distil.md (nil: never distilled)
function Vault.lastDistil(dept: string): string?
	local path = Vault.dir(dept, "distil.md")
	if not fs.isFile(path) then
		return nil
	end
	local last
	for d, rest in string.gmatch(string.gsub(fs.readFile(path), "\r\n", "\n"), "\n## (%d%d%d%d%-%d%d%-%d%d)([^\n]*)") do
		-- a "rule changes" entry (--edit / --retire) is history, not a distil: it never moves the window
		if not string.find(rest, "rule changes", 1, true) then
			last = d
		end
	end
	return last
end

-- the unix time of the last real distil within its day (written into its heading as "· at <unix>"; 0 for older
-- distils, which then count their whole day): the window's edge for distilDue and the packet
function Vault.distilTime(dept: string): number
	local path = Vault.dir(dept, "distil.md")
	if not fs.isFile(path) then
		return 0
	end
	local at = 0
	for rest in string.gmatch(string.gsub(fs.readFile(path), "\r\n", "\n"), "\n## %d%d%d%d%-%d%d%-%d%d([^\n]*)") do
		if not string.find(rest, "rule changes", 1, true) then
			at = tonumber(string.match(rest, "· at (%d+)")) or 0
		end
	end
	return at
end

-- ------------------------------------------------------------ learning owed (board/plans/archive/2026-11-09-enforced-learning-plan.md, rule 1)
-- the owner, 2026-11-09: "whenever any AI is using that pipeline, is actually making sure to learn lesson ... So never
-- skips anything". Every owner verdict written at or after LEARN_FROM (the rule's rollout; older ones are grandfathered)
-- owes its lane what it taught: the lessons it gave (`learned: [L-...]`, kit lesson ... --verdict) or why it taught
-- nothing new (`learned: "none - <why>"`, kit verdict learned). Words with neither a number nor a direction (an owner
-- ask) judge nothing and owe nothing. Until it is paid, kit new and kit handoff refuse in that lane.
Vault.LEARN_FROM = 1794246000 :: number -- (2026-11-09, ~21:40 local: the rollout)
Vault.LEARN_WHY_WORDS = 6

-- a reason a session gives instead of a lesson, a look or a rule: at least LEARN_WHY_WORDS words, four of them real
-- distinct words of three letters or more ("x x x x x x" says nothing)
function Vault.reasonOk(why: string?): boolean
	if type(why) ~= "string" then
		return false
	end
	local n, real, seen = 0, 0, {}
	for w in string.gmatch(why, "%S+") do
		n += 1
		local word = string.lower(string.match(w, "%a%a%a+") or "")
		if word ~= "" and not seen[word] then
			seen[word] = true
			real += 1
		end
	end
	return n >= Vault.LEARN_WHY_WORDS and real >= 4
end

-- written since the rollout, by the `time` the kit writes into every new verdict - never the file's time: a clone,
-- a sync, a checkout or an editor rewrites an old note's file and must not turn a grandfathered verdict into a debt
function Vault.writtenSince(v: Note): boolean
	return (tonumber(v.front.time) or 0) >= Vault.LEARN_FROM
end

function Vault.learned(front: { [string]: any }): boolean
	local l = front.learned
	if type(l) == "table" then
		return #l > 0
	end
	return type(l) == "string" and l ~= ""
end

-- the department's verdicts that still owe their lesson, newest first
function Vault.owedLearning(dept: string?): { Note }
	local out = {}
	for _, v in Vault.verdicts(dept) do
		if
			Vault.ownersOwn(v.front)
			and Vault.polarity(v.front) ~= nil
			and not Vault.learned(v.front)
			and Vault.writtenSince(v)
		then
			table.insert(out, v)
		end
	end
	return out
end

-- enforced learning, rule 3: a verdict on a piece the session had not looked at (`look: missing`, kit verdict) owes
-- that look until it is taken (`looked: <date>`, kit verdict looked) or why it could not be (`looked: "none - <why>"`)
function Vault.owedLook(dept: string?): { Note }
	local out = {}
	for _, v in Vault.verdicts(dept) do
		local f = v.front
		local paid = (type(f.looked) == "string" and f.looked ~= "")
		if Vault.ownersOwn(f) and f.look == "missing" and not paid and Vault.writtenSince(v) then
			table.insert(out, v)
		end
	end
	return out
end

-- a lane's kind for its commands (kit verdict <kind> ...)
Vault.KIND_OF_DEPT =
	{ ["3d"] = "asset", vfx = "vfx", ui = "screen", sfx = "sound", world = "world", anim = "anim" } :: {
		[string]: string,
	}

-- the refusal kit new / kit handoff print while a lane owes learning: one line per verdict, then how to pay it
function Vault.owedLines(dept: string): { string }
	local lines = {}
	for _, v in Vault.owedLearning(dept) do
		local f = v.front
		local said = if f.score ~= nil then `{f.score}/10` else tostring(Vault.direction(f) or "?")
		table.insert(lines, `{f.date} {f.name} {said} ({v.rel}): its lesson is owed`)
	end
	local kind = Vault.KIND_OF_DEPT[dept] or dept
	for _, v in Vault.owedLook(dept) do
		local f = v.front
		table.insert(
			lines,
			`{f.date} {f.name} ({v.rel}): shown without the session's own look - take the lane's look, then lune run kit verdict looked {kind} {f.name}`
		)
	end
	return lines
end

-- pay a verdict's look: the look was taken (today), or why it could not be -> (ok, why not)
function Vault.markLooked(v: Note, why: string?): (boolean, string?)
	local ok, text = pcall(fs.readFile, v.path)
	if not ok then
		return false, `cannot read {v.rel}`
	end
	local front, body = Vault.parse(text)
	if not front then
		return false, body
	end
	if why then
		if not Vault.reasonOk(why) then
			return false,
				`say why the look could not be taken in at least {Vault.LEARN_WHY_WORDS} words (four real ones)`
		end
		front.looked = "none - " .. why
	else
		front.looked = Vault.today()
	end
	Vault.write(v.path, front, body)
	return true, nil
end

-- pay a verdict's learning: the ids of the lessons it taught, or why it taught nothing new -> (ok, why not)
function Vault.markLearned(v: Note, ids: { string }?, why: string?): (boolean, string?)
	local ok, text = pcall(fs.readFile, v.path)
	if not ok then
		return false, `cannot read {v.rel}`
	end
	local front, body = Vault.parse(text)
	if not front then
		return false, body
	end
	if ids and #ids > 0 then
		local have: { string } = if type(front.learned) == "table" then front.learned else {}
		for _, id in ids do
			if not table.find(have, id) then
				table.insert(have, id)
			end
		end
		front.learned = have
	elseif type(why) == "string" then
		if not Vault.reasonOk(why) then
			return false, `say why it taught nothing new in at least {Vault.LEARN_WHY_WORDS} words (four real ones)`
		end
		front.learned = "none - " .. why
	else
		return false, "give the lesson ids it taught, or why it taught nothing new"
	end
	Vault.write(v.path, front, body)
	return true, nil
end

-- a department's distil is DUE once Vault.DISTIL_EVERY owner verdicts (inferred ones do not count) landed after its
-- last distil: returns how many landed and the command, or nil when it is not due (the plan's C6; shown by kit start
-- and kit status so nobody has to remember it)
Vault.DISTIL_EVERY = 5
function Vault.distilDue(dept: string): (number?, string?)
	local since = Vault.lastDistil(dept) or ""
	-- the distil's own time within its day: a verdict later that day counts
	local at = Vault.distilTime(dept)
	local n = 0
	for _, v in Vault.verdicts(dept) do
		if Vault.ownersOwn(v.front) and (since == "" or Vault.after(v, since, at)) then
			n += 1
		end
	end
	if n < Vault.DISTIL_EVERY then
		return nil, nil
	end
	return n, `lune run kit vault distil {dept}`
end

export type Packet = { since: string?, verdicts: { Note }, lessons: { Note }, lines: { string } }

-- the packet a model distils rules FROM: every verdict and lesson of the department dated after `since` (the
-- last distil by default), oldest first, with the golden / graveyard rows added meanwhile. The kit never writes
-- the rules itself — a rule is a model's reading of the owner's words, recorded with `--rule` and the sources.
function Vault.distil(dept: string, since: string?): Packet
	local from = since or Vault.lastDistil(dept) or ""
	local at = if since then math.huge else Vault.distilTime(dept)
	local verdicts, lessons = {}, {}
	for _, v in Vault.verdicts(dept) do
		-- the window distilDue counts: after the last distil's day, or that day after its time
		if
			dateOnly(v.front.date) > from or (from ~= "" and dateOnly(v.front.date) == from and Vault.noteTime(v) >= at)
		then
			table.insert(verdicts, v)
		end
	end
	for _, l in Vault.notes(dept, "lessons") do
		if dateOnly(l.front.date) > from then
			table.insert(lessons, l)
		end
	end
	local function oldestFirst(a: Note, b: Note): boolean
		return dateOnly(a.front.date) < dateOnly(b.front.date)
	end
	table.sort(verdicts, oldestFirst)
	table.sort(lessons, oldestFirst)
	local lines = {
		`-- distil {dept}: {#verdicts} verdict(s) + {#lessons} lesson(s) since {if from == ""
			then "the beginning"
			else from}`,
	}
	if #verdicts > 0 then
		table.insert(lines, "  VERDICTS (oldest first; the owner's words are the data, the score is the index):")
		for _, v in verdicts do
			local f = v.front
			local body = string.gsub(v.body, "%s+", " ")
			if #body > 220 then
				body = string.sub(body, 1, 217) .. "..."
			end
			table.insert(
				lines,
				`   {f.date} {f.name}: {Vault.said(f)}{if f.source and f.source ~= "owner"
					then " [" .. tostring(f.source) .. "]"
					else ""} — {body}  [[{v.rel}]]`
			)
		end
	end
	if #lessons > 0 then
		table.insert(lines, "  LESSONS (oldest first):")
		for _, l in lessons do
			local body = string.gsub(l.body, "%s+", " ")
			if #body > 200 then
				body = string.sub(body, 1, 197) .. "..."
			end
			table.insert(lines, `   {l.front.date}: {body}  [[{l.rel}]]`)
		end
	end
	-- a no that became a yes since the last distil: what changed is the rule worth writing
	local improved = {}
	for _, pr in Vault.pairs(dept) do
		if tostring(pr.high.front.date) > from then
			table.insert(improved, pr)
		end
	end
	if #improved > 0 then
		table.insert(lines, "  IMPROVED (the owner scored it low, then 2+ points higher - what changed between them):")
		for _, pr in improved do
			table.insert(
				lines,
				`   {pr.name}: {pr.low.front.score} ({pr.low.front.date}) -> {pr.high.front.score} ({pr.high.front.date})  [[{pr.low.rel}]] -> [[{pr.high.rel}]]`
			)
		end
	end
	if #verdicts == 0 and #lessons == 0 then
		table.insert(lines, "  nothing new since the last distil — no rule to propose")
	else
		table.insert(
			lines,
			"  PROPOSE three rules a model could FOLLOW next time (each names the verdicts it comes from), then:"
		)
		table.insert(
			lines,
			`    lune run kit vault distil {dept} --rule "<rule 1>" --rule "<rule 2>" --rule "<rule 3>" --as "<you>"`
		)
		table.insert(
			lines,
			'  A rule the owner has not confirmed is a hypothesis: write it as one ("when X, the owner said Y").'
		)
	end
	return { since = if from == "" then nil else from, verdicts = verdicts, lessons = lessons, lines = lines }
end

-- append a distil entry: the rules, the sources, the window. <dept>/distil.md is the department's rulebook over time.
-- ------------------------------------------------------------ live rules that accumulate (the plan's C2)
-- <dept>/rules.md holds the department's LIVE rules, one per line with a stable id: a distil adds, edits or retires
-- single rules instead of writing a new set over the old one (rewriting loses the rules that still hold). distil.md
-- stays the history of each distil. A retired rule stays in the file, struck through, with the reason.
export type Rule = { id: string, text: string, date: string, retired: string? }

function Vault.rulesPath(dept: string): string
	return Vault.dir(dept, "rules.md")
end

local function lastDistilRules(dept: string): ({ string }, string?)
	local path = Vault.dir(dept, "distil.md")
	if not fs.isFile(path) then
		return {}, nil
	end
	local text = string.gsub(fs.readFile(path), "\r\n", "\n")
	local last, at = nil, 1
	while true do
		local s = string.find(text, "\n## %d%d%d%d%-%d%d%-%d%d", at)
		if not s then
			break
		end
		local heading = string.match(text, "^[^\n]*", s + 1) or ""
		-- (a "no new rule" distil closes its window but has no rules to show: the latest rules are the section before)
		if not string.find(heading, "rule changes", 1, true) and not string.find(heading, "no new rule", 1, true) then
			last = string.sub(text, s + 1)
		end
		at = s + 1
	end
	local out = {}
	if last then
		for line in string.gmatch(last, "[^\n]+") do
			local rule = string.match(line, "^%d+%.%s+(.+)$")
			if rule then
				table.insert(out, rule)
			end
		end
	end
	return out, if last then string.match(last, "^## (%d%d%d%d%-%d%d%-%d%d)") else nil
end

-- every rule in rules.md (live and retired), in file order; empty when the file is missing
function Vault.rules(dept: string): { Rule }
	local path = Vault.rulesPath(dept)
	if not fs.isFile(path) then
		return {}
	end
	local out: { Rule } = {}
	for line in string.gmatch(string.gsub(fs.readFile(path), "\r\n", "\n"), "[^\n]+") do
		local id, date, text = string.match(line, "^%- (R%-[%w]+%-%d+) %((%d%d%d%d%-%d%d%-%d%d)%): (.+)$")
		if id then
			table.insert(out, { id = id, date = date, text = text })
		else
			-- struck through: retired (by a distil, "(retired <date>: why)", or by hand in Obsidian with no reason)
			local rid, rdate, rtext, tail =
				string.match(line, "^%- ~~(R%-[%w]+%-%d+) %((%d%d%d%d%-%d%d%-%d%d)%): (.-)~~%s*(.*)$")
			if rid then
				local why = string.match(tail, "^%(retired (.+)%)$") or "struck through by hand"
				table.insert(out, { id = rid, date = rdate, text = rtext, retired = why })
			end
		end
	end
	return out
end

function Vault.ruleById(id: string): Rule?
	local dept = string.match(id, "^R%-([^%-]+)%-%d+$")
	if not dept then
		return nil
	end
	for _, r in Vault.rules(dept) do
		if r.id == id then
			return r
		end
	end
	return nil
end

-- the generated head of rules.md (writeRules' own lines): anything else in the file is someone's and is kept
local function rulesHead(dept: string): { string }
	return {
		`# {Vault.TITLES[dept] or dept} — live rules`,
		"Each rule is a model's reading of the owner's verdicts (a hypothesis until the next verdict). A distil adds,",
		`edits or retires ONE rule at a time (lune run kit vault distil {dept} --rule / --edit / --retire); a retired`,
		"rule stays here, struck through, with the reason. Sessions cite the rules they follow like lessons",
		"(kit lesson used R-...), and the owner's verdicts count for or against them.",
		"## Kept as written (lines the kit cannot read as a rule; put them in the rule form to make them count)",
	}
end

local function writeRules(dept: string, rules: { Rule })
	-- lines typed into rules.md (in Obsidian) that are not in the rule form are kept, never dropped
	local kept = {}
	local path = Vault.rulesPath(dept)
	if fs.isFile(path) then
		local front, body = Vault.parse(fs.readFile(path))
		local head = {}
		for _, h in rulesHead(dept) do
			head[h] = true
		end
		for line in string.gmatch(if front then body else "", "[^\n]+") do
			local rule = string.match(line, "^%- (R%-[%w]+%-%d+) %(%d%d%d%d%-%d%d%-%d%d%): ")
				or string.match(line, "^%- ~~(R%-[%w]+%-%d+) %(")
			if not rule and not head[line] and string.match(line, "%S") then
				table.insert(kept, line)
			end
		end
	end
	local lines = {
		Vault.frontmatter({ kind = "rules", area = dept, date = Vault.today(), links = { `[[{dept}/index]]` } }),
		"",
		`# {Vault.TITLES[dept] or dept} — live rules`,
		"",
		"Each rule is a model's reading of the owner's verdicts (a hypothesis until the next verdict). A distil adds,",
		`edits or retires ONE rule at a time (lune run kit vault distil {dept} --rule / --edit / --retire); a retired`,
		"rule stays here, struck through, with the reason. Sessions cite the rules they follow like lessons",
		"(kit lesson used R-...), and the owner's verdicts count for or against them.",
		"",
	}
	for _, r in rules do
		if r.retired then
			table.insert(lines, `- ~~{r.id} ({r.date}): {r.text}~~ (retired {r.retired})`)
		else
			table.insert(lines, `- {r.id} ({r.date}): {r.text}`)
		end
	end
	if #kept > 0 then
		table.insert(lines, "")
		table.insert(lines, rulesHead(dept)[6])
		table.insert(lines, "")
		for _, k in kept do
			table.insert(lines, k)
		end
	end
	ensureDir(Vault.dir(dept))
	fs.writeFile(Vault.rulesPath(dept), table.concat(lines, "\n") .. "\n")
end

-- write rules.md from the last distil's rules when the department has none yet (kit vault distil does it on its first
-- change; this lets the ids exist before that). Returns how many rules it wrote (0 = already there or nothing to seed).
function Vault.seedRules(dept: string): number
	if fs.isFile(Vault.rulesPath(dept)) then
		return 0
	end
	local seed, date = lastDistilRules(dept)
	if #seed == 0 then
		return 0
	end
	local rules: { Rule } = {}
	for i, t in seed do
		table.insert(rules, { id = `R-{dept}-{i}`, date = date or Vault.today(), text = t })
	end
	writeRules(dept, rules)
	return #rules
end

-- one change to the live rules: "add" (text), "edit" (id + text) or "retire" (id + why). The first change seeds the
-- file with the last distil's rules. Returns the rule's id, or nil + why.
function Vault.ruleChange(dept: string, op: string, id: string?, text: string): (string?, string?)
	local rules = Vault.rules(dept)
	if #rules == 0 and not fs.isFile(Vault.rulesPath(dept)) then
		local seed, date = lastDistilRules(dept)
		for i, t in seed do
			table.insert(rules, { id = `R-{dept}-{i}`, date = date or Vault.today(), text = t })
		end
	end
	local clean = string.gsub(string.gsub(text, "%s+", " "), "^%s*(.-)%s*$", "%1")
	if clean == "" then
		return nil, "the rule's words are empty"
	end
	if op == "add" then
		-- the same words as a live rule ARE that rule (a distil that re-adds a surviving rule keeps one copy)
		for _, r in rules do
			if not r.retired and string.lower(r.text) == string.lower(clean) then
				return r.id, nil
			end
		end
		local n = 0
		for _, r in rules do
			n = math.max(n, tonumber(string.match(r.id, "(%d+)$")) or 0)
		end
		local newId = `R-{dept}-{n + 1}`
		table.insert(rules, { id = newId, date = Vault.today(), text = clean })
		writeRules(dept, rules)
		return newId, nil
	end
	for _, r in rules do
		if r.id == id then
			if r.retired then
				return nil, `{id} is already retired`
			end
			if op == "edit" then
				r.text = clean
				r.date = Vault.today()
			elseif op == "retire" then
				r.retired = `{Vault.today()}: {clean}`
			else
				return nil, `unknown change "{op}"`
			end
			writeRules(dept, rules)
			return r.id, nil
		end
	end
	return nil, `no live rule {id or "?"} in {Vault.rulesPath(dept)}`
end

-- record rule changes (edit / retire) in distil.md's history: a distil that only fixed rules is still a distil
function Vault.logRuleChanges(dept: string, changes: { string }, by: string?): string
	local path = Vault.dir(dept, "distil.md")
	local text = if fs.isFile(path)
		then string.gsub(fs.readFile(path), "\r\n", "\n")
		else `# {Vault.TITLES[dept] or dept} — distilled rules\n`
	local lines = { "", `## {Vault.today()} — rule changes{if by then " · by " .. by else ""}`, "" }
	for _, c in changes do
		table.insert(lines, `- {c}`)
	end
	ensureDir(Vault.dir(dept))
	fs.writeFile(path, string.gsub(text, "%s+$", "") .. "\n" .. table.concat(lines, "\n") .. "\n")
	return path
end

function Vault.writeDistil(dept: string, rules: { string }, packet: Packet, by: string?, none: string?): string
	-- the live list first (it seeds from the PREVIOUS distil, so the rules that still hold survive), then the history
	for _, r in rules do
		Vault.ruleChange(dept, "add", nil, r)
	end
	local path = Vault.dir(dept, "distil.md")
	ensureDir(Vault.dir(dept))
	local text = if fs.isFile(path)
		then string.gsub(fs.readFile(path), "\r\n", "\n")
		else `# {Vault.TITLES[dept] or dept} — distilled rules (each from the owner's verdicts of its window)\n\nA rule here is a model's reading of the owner's words; the owner's next verdict confirms or kills it.\n`
	local sources = {}
	for _, v in packet.verdicts do
		table.insert(sources, `[[{v.rel}]]`)
	end
	for _, l in packet.lessons do
		table.insert(sources, `[[{l.rel}]]`)
	end
	local lines = {
		"",
		`## {Vault.today()} — {#packet.verdicts} verdict(s) + {#packet.lessons} lesson(s) since {packet.since or "the beginning"} · at {os.time()}{if by
			then " · by " .. by
			else ""}{if none then " · no new rule" else ""}`,
		"",
	}
	-- (enforced learning, rule 4) a distil that read its window and found no new rule says why: it still closes the window
	if none then
		table.insert(lines, `No new rule: {none}`)
	end
	for i, r in rules do
		table.insert(lines, `{i}. {r}`)
	end
	if #sources > 0 then
		table.insert(lines, "")
		table.insert(lines, "Sources: " .. table.concat(sources, " · "))
	end
	fs.writeFile(path, string.gsub(text, "%s+$", "") .. "\n" .. table.concat(lines, "\n") .. "\n")
	return path
end

-- ------------------------------------------------------------ the verdict trend
-- days since 1970-01-01 for a YYYY-MM-DD string (civil-from-days, no os.time: the date is the owner's, not local)
local function dayNumber(date: string): number?
	local y, m, d = string.match(date, "^(%d%d%d%d)%-(%d%d)%-(%d%d)")
	if not y then
		return nil
	end
	local yy, mm, dd = tonumber(y) :: number, tonumber(m) :: number, tonumber(d) :: number
	if mm <= 2 then
		yy -= 1
	end
	local era = math.floor(yy / 400)
	local yoe = yy - era * 400
	local doy = math.floor((153 * (mm + (if mm > 2 then -3 else 9)) + 2) / 5) + dd - 1
	local doe = yoe * 365 + math.floor(yoe / 4) - math.floor(yoe / 100) + doy
	return era * 146097 + doe - 719468
end

local function mean(xs: { number }): number?
	if #xs == 0 then
		return nil
	end
	local s = 0
	for _, x in xs do
		s += x
	end
	return s / #xs
end

local function fmt1(x: number?): string
	return if x == nil then "—" else string.format("%.1f", x)
end

-- per department: n, the mean, the last 7 days against the 7 before, the best piece, and every piece with
-- two or more scored verdicts as a trajectory (4.6 -> 4.9 -> 8.5). The owner's OWN numbers make the mean, the last
-- 7 days, the best and the trajectories; numbers a model guessed from the owner's words are counted apart with their
-- own mean (2026-11-08: half the vault's numbers were guesses, and mixing them hid the real trend). Keep / Redo and
-- words-only notes are counted, never averaged. This is a report, never a target.
function Vault.trend(dept: string?, today: string?): { string }
	local lines = {}
	local now = dayNumber(today or Vault.today()) or 0
	for _, d in if dept then { dept } else Vault.DEPTS do
		local all = Vault.verdicts(d)
		if #all > 0 then
			local scored, recent, before, byPiece = {}, {}, {}, {}
			local guessed: { number } = {}
			local best, bestNote = nil, nil
			local keeps, redos, wordsOnly, guessedOther = 0, 0, 0, 0
			for i = #all, 1, -1 do -- oldest first
				local v = all[i]
				local s = tonumber(v.front.score)
				local dir = Vault.direction(v.front)
				if s and not Vault.ownersOwn(v.front) then
					table.insert(guessed, s)
				elseif not s and not Vault.ownersOwn(v.front) then
					guessedOther += 1 -- a guessed Keep / Redo / words: never the owner's
				elseif not s then
					if dir == "keep" then
						keeps += 1
					elseif dir == "redo" then
						redos += 1
					else
						wordsOnly += 1
					end
				end
				if s and Vault.ownersOwn(v.front) then
					table.insert(scored, s)
					local day = dayNumber(dateOnly(v.front.date))
					if day then
						if now - day < 7 then
							table.insert(recent, s)
						elseif now - day < 14 then
							table.insert(before, s)
						end
					end
					local name = tostring(v.front.name)
					byPiece[name] = byPiece[name] or {}
					table.insert(byPiece[name], s)
					if best == nil or s > best then
						best, bestNote = s, v
					end
				end
			end
			local m, r, b, g = mean(scored), mean(recent), mean(before), mean(guessed)
			local delta = if r and b then string.format(" (%+.1f vs the 7 d before)", r - b) else ""
			local extra = {}
			if keeps + redos > 0 then
				table.insert(extra, `{keeps} Keep / {redos} Redo`)
			end
			if wordsOnly > 0 then
				table.insert(extra, `{wordsOnly} words only`)
			end
			if guessedOther > 0 then
				table.insert(extra, `{guessedOther} guessed with no number`)
			end
			table.insert(
				lines,
				`{d}: {#all} verdict(s), {#scored + #guessed} scored ({#scored} the owner's own, {#guessed} guessed from their words{if #extra
						> 0
					then ", " .. table.concat(extra, ", ")
					else ""}) · mean {fmt1(m)}{if #guessed > 0 then ` (guessed {fmt1(g)})` else ""} · last 7 d: {#recent} at {fmt1(
					r
				)}{delta} · best: {if bestNote
					then `{bestNote.front.name} {fmt1(best)} ({dateOnly(bestNote.front.date)})`
					else "—"}{(function()
					local clause = Vault.repeatsClause(d, today)
					return if clause then " · " .. clause else ""
				end)()}{Vault.learningClause(d)}`
			)
			local names = {}
			for name, xs in byPiece do
				if #xs >= 2 then
					table.insert(names, name)
				end
			end
			table.sort(names)
			for _, name in names do
				local xs = byPiece[name]
				local parts = {}
				for _, x in xs do
					table.insert(parts, fmt1(x))
				end
				local arrow = if xs[#xs] > xs[1] then "up" elseif xs[#xs] < xs[1] then "DOWN" else "flat"
				table.insert(lines, `   {name}: {table.concat(parts, " -> ")} ({arrow})`)
			end
		end
	end
	if not dept or dept == "ui" then
		local gap = Vault.judgeGapLine()
		if gap then
			table.insert(lines, gap)
		end
	end
	if #lines == 0 then
		table.insert(lines, 'no verdicts recorded yet (lune run kit verdict <kind> <name> <0-10> "<words>")')
	end
	return lines
end

-- how far the fresh UI judges sit from the owner's eye (kit/ui/judge.py keeps owner.gap beside the owner's score in
-- <Screen>.judge.json - 2026-11-08, sprint 4: printed, never stored; an older record's gap is its median minus the
-- owner's score): the median gap over every screen the owner scored. nil without one
Vault.JUDGE_ROOTS = nil :: { string }? -- a spec points it at a temp folder
function Vault.judgeGapLine(): string?
	local roots = Vault.JUDGE_ROOTS or { "assets/ui" }
	if not Vault.JUDGE_ROOTS and fs.isDir("games") then
		for _, g in fs.readDir("games") do
			if fs.isDir(`games/{g}/assets/ui`) then
				table.insert(roots, `games/{g}/assets/ui`)
			end
		end
	end
	local gaps, named, other = {}, {}, 0
	for _, root in roots do
		for _, f in (if fs.isDir(root) then fs.readDir(root) else {}) do
			if string.sub(f, -11) == ".judge.json" then
				local ok, j = pcall(serde.decode, "json" :: any, fs.readFile(`{root}/{f}`))
				local o = if ok and type(j) == "table" and type(j.owner) == "table" then j.owner else nil
				-- the gap stored when the owner scored (same build then), else the record's median against the
				-- owner's score only when both are of ONE build: another build's judges measured other pixels
				local same = o and o.model_sha256 ~= nil and o.model_sha256 == j.model_sha256
				local g = o
					and (tonumber(o.gap) or (same and tonumber(j.score) and tonumber(o.score) and j.score - o.score))
				if g then
					table.insert(gaps, g)
					table.insert(named, `{string.sub(f, 1, -12)} {o.judges_median or j.score} vs {o.score}`)
				elseif o and tonumber(o.score) then
					other += 1
				end
			end
		end
	end
	if #gaps == 0 then
		return if other > 0
			then `ui: {other} screen(s) the owner scored were judged on another build - no judges' gap to compare yet (judge the scored build: kit ui judge)`
			else nil
	end
	table.sort(gaps)
	local mid = if #gaps % 2 == 1 then gaps[(#gaps + 1) // 2] else (gaps[#gaps // 2] + gaps[#gaps // 2 + 1]) / 2
	return `ui: the fresh judges sit {if mid < 0 then "under" else "over"} the owner by a median {math.abs(mid)} on {#gaps} screen(s) ({table.concat(
		named,
		", ",
		1,
		math.min(3, #named)
	)}) - a judge's number is not the owner's eye{if other > 0
		then `; {other} more scored on another build, not compared`
		else ""}`
end

-- ------------------------------------------------------------ rejected again
-- the vault's own scoreboard: a piece the owner rejected (≤ 3) that the owner had ALREADY rejected on an earlier day. Each
-- one is a round the graveyard should have prevented (or a new route that failed the same way). Names compare
-- without case and without a "(...)" note. A report, never a target.
export type Repeat = { name: string, date: string, first: string, score: number, recent: boolean }

local function pieceKey(name: any): string
	local s = string.lower(tostring(name or ""))
	s = string.gsub(s, "%s*%b()", "")
	return (string.gsub(string.gsub(s, "^%s+", ""), "%s+$", ""))
end

function Vault.repeats(dept: string, today: string?): { all: { Repeat }, rejected: number, recent: number }
	local now = dayNumber(today or Vault.today()) or 0
	local firstRejected: { [string]: string } = {}
	local out: { Repeat } = {}
	local rejected, recent = 0, 0
	local list = Vault.verdicts(dept)
	for i = #list, 1, -1 do -- oldest first
		local f = list[i].front
		local s = tonumber(f.score)
		local date = dateOnly(f.date)
		-- the owner's own rejections only: a number a model guessed from their words is not the owner rejecting
		if s and s <= 3 and date ~= "" and Vault.ownersOwn(f) then
			rejected += 1
			local key = pieceKey(f.name)
			local first = firstRejected[key]
			if first and first < date then
				local day = dayNumber(date)
				local isRecent = day ~= nil and now - day < 7
				table.insert(out, { name = tostring(f.name), date = date, first = first, score = s, recent = isRecent })
				if isRecent then
					recent += 1
				end
			elseif not first then
				firstRejected[key] = date
			end
		end
	end
	return { all = out, rejected = rejected, recent = recent }
end

-- ------------------------------------------------------------ already covered
-- how often the owner rejected something a lesson ALREADY covered (2026-11-08: leg and arm complaints kept coming
-- after lessons on them existed). Each distinct low verdict of the owner's own (3 or less, or Redo; one quote filed on
-- several pieces counts once) against the lessons written on an EARLIER day: covered when one shares at least
-- COVER_WORDS of its search words. Words, not meaning: a rough report, never a target.
Vault.COVER_WORDS = 3

function Vault.covered(dept: string): { low: number, covered: number }
	local lessons = Vault.notes(dept, "lessons")
	local seen: { [string]: boolean } = {}
	local low, covered = 0, 0
	for _, v in Vault.verdicts(dept) do
		if Vault.ownersOwn(v.front) and Vault.polarity(v.front) == -1 then
			local key = string.sub(string.lower((string.gsub(v.body, "%s+", " "))), 1, 300)
			if not seen[key] then
				seen[key] = true
				low += 1
				local date = dateOnly(v.front.date)
				local before = {}
				for _, l in lessons do
					if dateOnly(l.front.date) < date then
						table.insert(before, l)
					end
				end
				local hits = Vault.bm25(v.body, before, function(l: any): string
					return l.body
				end)
				if hits[1] and hits[1].hits >= Vault.COVER_WORDS then
					covered += 1
				end
			end
		end
	end
	return { low = low, covered = covered }
end

-- the learning clauses of the trend line: how many rejections a lesson already covered, and (animation) whether the
-- kit's own warnings were on the candidates the owner rejected (kit checks validate anim -> .verify/checks-anim.json)
function Vault.learningClause(dept: string): string
	local out = ""
	local c = Vault.covered(dept)
	if c.low > 0 then
		out ..= ` · a lesson already covered {c.covered} of {c.low} rejection(s)`
	end
	-- the lane's checks from the owner's words (kit/checks/checks.py): how many, by status (proposed reports only)
	local checksFile = Vault.dir(dept, "checks.json")
	if fs.isFile(checksFile) then
		local okc, cj = pcall(serde.decode, "json" :: any, fs.readFile(checksFile))
		if okc and type(cj) == "table" and type(cj.checks) == "table" and #cj.checks > 0 then
			local byStatus: { [string]: number } = {}
			for _, chk in cj.checks do
				local s = if type(chk) == "table" and type(chk.status) == "string" then chk.status else "proposed"
				byStatus[s] = (byStatus[s] or 0) + 1
			end
			local parts = {}
			for s, n in byStatus do
				table.insert(parts, `{n} {s}`)
			end
			table.sort(parts)
			out ..= ` · checks from the owner's words: {table.concat(parts, ", ")}`
		end
	end
	local file = `.verify/checks-{dept}.json`
	if fs.isFile(file) then
		local ok, j = pcall(serde.decode, "json" :: any, fs.readFile(file))
		if ok and type(j) == "table" and tonumber(j.rejected_candidates) and j.rejected_candidates > 0 then
			-- beside the share of ALL shown candidates: warnings on every candidate tell rejected from kept apart by nothing
			out ..= ` · kit warnings on {j.rejected_warned} of {j.rejected_candidates} rejected candidates and on {j.shown_warned or "?"} of {j.shown_candidates or "?"} shown ({j.picked_measured or 0} picks measured)`
		end
	end
	return out
end

-- one clause for the trend line: "rejected again: 2 of 9 rejections (barrel, extinguisher)"
function Vault.repeatsClause(dept: string, today: string?): string?
	local r = Vault.repeats(dept, today)
	if r.rejected == 0 then
		return nil
	end
	local names, seen = {}, {}
	for k = #r.all, 1, -1 do -- newest first
		local key = pieceKey(r.all[k].name)
		if not seen[key] and #names < 3 then
			seen[key] = true
			table.insert(names, r.all[k].name)
		end
	end
	return `rejected again: {#r.all} of {r.rejected} rejection(s){if r.recent > 0
		then `, {r.recent} in the last 7 d`
		else ""}{if #names > 0 then " (" .. table.concat(names, ", ") .. ")" else ""}`
end

return Vault

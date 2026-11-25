--!strict
-- families.luau — family playbooks (2026-11-08, sprint 5: proposal 12 of
-- board/plans/archive/2026-11-08-pipeline-rag-learning-research.md): a lesson and a piece get a family (firearm, furniture,
-- slash, aura, hud, sword, gun...) from kit/knowledge/families.json, and lesson ranking prefers the piece's family - a
-- gun's "barrel" lesson stops ranking for a wine barrel. A lesson's family is its own `family:` field, else the family
-- its headline names, else BODY_HITS different words of one family in its body (a clear winner: a lesson about
-- everything stays general); a piece's family comes from its name, then its own field (an animation dossier's
-- category, a UI spec's kind), then its brief's words.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Vault = require("./vault")

local Families = {}

Families.FILE = "kit/knowledge/families.json"
Families.BOOST = 0.1 -- a lesson of the piece's family ranks this much higher (relevance is 0..1)
Families.OTHER = 0.85 -- a lesson of ANOTHER family of the lane keeps this share of its score (no family: untouched)

local cache: { [string]: any }? = nil

function Families.data(): { [string]: any }
	if cache then
		return cache
	end
	local out: { [string]: any } = {}
	if fs.isFile(Families.FILE) then
		local ok, j = pcall(serde.decode, "json" :: any, fs.readFile(Families.FILE))
		if ok and type(j) == "table" then
			out = j
		end
	end
	cache = out
	return out
end

local lessonMemo: { [string]: string | boolean } = {}

-- a spec points the module at its own families (the lessons' families are read again too)
function Families.reset(file: string?)
	Families.FILE = file or "kit/knowledge/families.json"
	cache = nil
	table.clear(lessonMemo)
end

-- a text's words as the families name them: camelCase, capital runs (DTBlade: "dt blade") and snake_case split, lower
-- case, 3+ letters, a plural off from 4 letters ("runs", "guns"; "slashes", "punches", "boxes", "glasses" lose "es")
-- - and NO stop words: the lessons' search drops "run", a family word
function Families.words(text: string): { string }
	local spaced = string.gsub(string.gsub(text or "", "(%l)(%u)", "%1 %2"), "(%u)(%u%l)", "%1 %2")
	spaced = string.gsub(spaced, "_", " ")
	local out = {}
	for w in string.gmatch(string.lower(spaced), "[a-z][a-z0-9]+") do
		-- a numbered name is its word ("glock17" is a glock, "spoke2" a spoke: the family is in the letters - the
		-- spec's "from its name" held only through a private brief, t6rx); a code of mixed letters and digits stays
		local lettersOnly = string.match(w, "^(%a%a%a+)%d+$")
		if lettersOnly then
			w = lettersOnly
		end
		if #w >= 3 then
			local stem = string.sub(w, 1, -3)
			if
				#w >= 5
				and string.sub(w, -2) == "es"
				and (
					string.sub(stem, -2) == "sh"
					or string.sub(stem, -2) == "ch"
					or string.sub(stem, -1) == "x"
					or string.sub(stem, -2) == "ss"
				)
			then
				w = stem
			elseif #w >= 4 and string.sub(w, -1) == "s" and string.sub(w, -2) ~= "ss" then
				w = string.sub(w, 1, -2)
			end
			table.insert(out, w)
		end
	end
	return out
end

-- the lane's families -> { family = { word = true } }
local function lanes(dept: string): { [string]: { [string]: boolean } }
	local out: { [string]: { [string]: boolean } } = {}
	local fams = Families.data()[dept]
	if type(fams) == "table" then
		for fam, words in fams do
			if type(words) == "table" then
				local set: { [string]: boolean } = {}
				for _, w in words do
					set[tostring(w)] = true
				end
				out[fam] = set
			end
		end
	end
	return out
end

function Families.names(dept: string): { string }
	local out = {}
	for fam in lanes(dept) do
		table.insert(out, fam)
	end
	table.sort(out)
	return out
end

-- the family a text names with the most DISTINCT words -> family or nil (fewer than `min` of them, or a tie): one word
-- said three times ("barrel", "barrel", "barrel") is one word
function Families.ofText(dept: string, text: string, min: number?): string?
	local fams = lanes(dept)
	local hits: { [string]: number } = {}
	local seen: { [string]: boolean } = {}
	for _, w in Families.words(text) do
		if not seen[w] then
			seen[w] = true
			for fam, set in fams do
				if set[w] then
					hits[fam] = (hits[fam] or 0) + 1
				end
			end
		end
	end
	local best, bestN, second = nil, 0, 0
	for fam, n in hits do
		if n > bestN then
			best, bestN, second = fam, n, bestN
		elseif n > second then
			second = n
		end
	end
	if not best or bestN < (min or 1) or bestN == second then
		return nil
	end
	return best
end

Families.HEAD_HITS = 2 -- a headline names its family with two different words (one is often incidental: the "arch" of
-- a dental_arch, the "wall" of a mesh); "(the Glock, 2026-10-10)" in brackets is where it was learned, never what it is
-- about: bracketed text is left out of the headline. A wrong family lowers a lesson, none leaves it as it was
Families.BODY_HITS = 3 -- with no family in its headline, a lesson's body names it with three different words

-- a lesson's family: its own `family:` (a family of its lane), else the family its HEADLINE names (its gist, else its
-- first sentence - a lesson about guns says so up front), else BODY_HITS different words of one family in its body.
-- A lesson that only mentions a gun or a coat on the way (a references lesson, a retopology lesson) stays general
function Families.ofLesson(dept: string, note: Vault.Note): string?
	local key = `{dept}|{note.rel}|{#note.body}|{tostring(note.front.family)}|{tostring(note.front.gist)}`
	local m = lessonMemo[key]
	if m ~= nil then
		return if m == false then nil else m :: string
	end
	local own = note.front.family
	local fam: string? = nil
	if type(own) == "string" and lanes(dept)[own] then
		fam = own
	else
		local body = string.gsub(note.body, "^%s*#[^\n]*\n", "")
		-- the headline: the gist, else the first sentence (a point followed by a space or a line end: "~0.5" is no end)
		local first = string.match(body, "^%s*(.-)%.%s") or string.match(body, "^%s*([^\n]+)") or ""
		local head = if type(note.front.gist) == "string" and note.front.gist ~= "" then note.front.gist else first
		head = string.sub(string.gsub(head, "%b()", " "), 1, 200)
		fam = Families.ofText(dept, head, Families.HEAD_HITS) or Families.ofText(dept, body, Families.BODY_HITS)
	end
	lessonMemo[key] = fam or false
	return fam
end

local function snake(name: string): string
	local s = string.gsub(name, "(%l)(%u)", "%1_%2")
	s = string.gsub(s, "(%u)(%u%l)", "%1_%2")
	return string.lower(s)
end

-- an animation dossier's category -> the family (combat is split by the piece's words: sword or unarmed)
Families.ANIM_CATEGORY =
	{ gun = "gun", locomotion = "locomotion", reaction = "reaction", idle = "idle" } :: { [string]: string }

-- a piece's family: its NAME first (town_tester_bed: a tester and a bed; GunTrick: a gun move, though its dossier says
-- idle), then its own field (an animation dossier's category, a UI spec's kind), then its brief's words
-- (Vault.queryFor) - a long brief names several families (a bed's cloth hangings, a house's wall) and ties
function Families.ofPiece(dept: string, piece: string): string?
	if piece == "" then
		return nil
	end
	local Config = require("./config")
	local game = Config.game()
	local roots = if game then { `games/{game}/`, "" } else { "" }
	local text = piece
	local byName = Families.ofText(dept, piece, 1)
	if byName then
		return byName
	end
	if dept == "anim" then
		for _, r in roots do
			local p = `{r}assets/animations/dossiers/{snake(piece)}.json`
			if fs.isFile(p) then
				local ok, j = pcall(serde.decode, "json" :: any, fs.readFile(p))
				local cat = if ok and type(j) == "table" then j.category else nil
				if type(cat) == "string" then
					if Families.ANIM_CATEGORY[cat] then
						return Families.ANIM_CATEGORY[cat]
					end
					text ..= " " .. tostring(j.move or j.name or "") .. " " .. tostring(j.about or "")
				end
				break
			end
		end
	elseif dept == "ui" then
		for _, r in roots do
			local p = `{r}assets/ui/{piece}.json`
			if fs.isFile(p) then
				local ok, j = pcall(serde.decode, "json" :: any, fs.readFile(p))
				local kind = if ok and type(j) == "table" then j.kind else nil
				if type(kind) == "string" and lanes(dept)[kind] then
					return kind
				end
				break
			end
		end
	end
	return Families.ofText(dept, text, 1) or Families.ofText(dept, Vault.queryFor(dept, piece), 1)
end

-- a family's playbook: its lessons (the owner's evidence on each first, then newest), the golden and graveyard rows of
-- its pieces, and the live rules that name its words -> printable lines. No family: every family with its counts
function Families.playbook(dept: string, family: string?): { string }
	local out = {}
	local fams = lanes(dept)
	local retired = Vault.supersededSet()
	local lessons: { [string]: { Vault.Note } } = {}
	local general = 0
	for _, n in Vault.notes(dept, "lessons") do
		if not retired[string.lower(n.rel)] then
			local f = Families.ofLesson(dept, n)
			if f then
				lessons[f] = lessons[f] or {}
				table.insert(lessons[f], n)
			else
				general += 1
			end
		end
	end
	local function rowsOf(file: string, fam: string): { string }
		local got = {}
		for _, cells in Vault.rows(Vault.dir(dept, file)) do
			local piece = string.match(cells[1] or "", "[%w_%-/]+") or ""
			if piece ~= "" and Families.ofText(dept, piece, 1) == fam then
				table.insert(got, table.concat(cells, " | "))
			end
		end
		return got
	end
	if not family then
		for _, fam in Families.names(dept) do
			table.insert(
				out,
				`{fam}: {#(lessons[fam] or {})} lesson(s), {#rowsOf("golden.md", fam)} golden, {#rowsOf(
					"graveyard.md",
					fam
				)} graveyard`
			)
		end
		table.insert(out, `general (no family): {general} lesson(s)`)
		return out
	end
	if not fams[family] then
		return { `no {dept} family "{family}" ({table.concat(Families.names(dept), ", ")})` }
	end
	local counts = Vault.lessonCounts()
	local list = table.clone(lessons[family] or {})
	local function ev(n: Vault.Note): number
		local k = counts[Vault.lessonId(n)]
		return if k then (k.helpful - k.harmful) else 0
	end
	table.sort(list, function(a, b)
		if ev(a) ~= ev(b) then
			return ev(a) > ev(b)
		end
		return tostring(a.front.date or "") > tostring(b.front.date or "")
	end)
	table.insert(out, `## {dept} / {family}: {#list} lesson(s) (the owner's evidence first, then newest)`)
	for i = 1, math.min(12, #list) do
		local n = list[i]
		table.insert(
			out,
			`- [{Vault.lessonId(n)}] {n.front.date or "?"}: {string.sub(string.gsub(Vault.gist(n), "%s+", " "), 1, 160)}`
		)
	end
	for _, file in { "golden.md", "graveyard.md" } do
		local rows = rowsOf(file, family)
		table.insert(out, `## {file} rows of this family: {#rows}`)
		for i = 1, math.min(6, #rows) do
			table.insert(out, "- " .. string.sub(rows[i], 1, 200))
		end
	end
	local named = {}
	for _, r in Vault.rules(dept) do
		if not r.retired and Families.ofText(dept, r.text, 1) == family then
			table.insert(named, `- {r.id}: {string.sub(r.text, 1, 180)}`)
		end
	end
	table.insert(out, `## live rules naming it: {#named}`)
	for _, l in named do
		table.insert(out, l)
	end
	return out
end

return Families

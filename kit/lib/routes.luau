-- routes.luau — every department's route as STAGES with at most five commands each (kit/knowledge/routes.json).
-- `kit help --stage <dept>:<stage>` and `kit status` print the shortlist for the stage you are in: a model picks
-- the right tool far more often from five than from the whole wall (`kit help --all`).
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Routes = {}

Routes.FILE = "kit/knowledge/routes.json"
Routes.MAX = 5

local cached: any = nil

function Routes.load(): any
	if cached then
		return cached
	end
	if not fs.isFile(Routes.FILE) then
		cached = {}
		return cached
	end
	local ok, data = pcall(serde.decode, "json" :: any, fs.readFile(Routes.FILE))
	cached = if ok and type(data) == "table" then data else {}
	return cached
end

function Routes.depts(): { string }
	local out = {}
	for k, v in Routes.load() do
		if type(v) == "table" and type(v.stages) == "table" then
			table.insert(out, k)
		end
	end
	table.sort(out)
	return out
end

function Routes.stages(dept: string): { string }
	local d = Routes.load()[dept]
	return if d and type(d.stages) == "table" then d.stages else {}
end

export type Stage = { gate: string, commands: { string } }

-- the stage's shortlist (never more than Routes.MAX commands, whatever the file says) and its gate
function Routes.stage(dept: string, stage: string): Stage?
	local d = Routes.load()[dept]
	local s = d and d[stage]
	if type(s) ~= "table" then
		return nil
	end
	local commands = {}
	for i = 1, math.min(Routes.MAX, #(s.commands or {})) do
		table.insert(commands, s.commands[i])
	end
	return { gate = tostring(s.gate or ""), commands = commands }
end

-- the lines `kit help --stage` prints
local function clip(text: string, n: number): string
	text = string.gsub(text, "%s+", " ")
	if (utf8.len(text) or #text) <= n then
		return text
	end
	return string.sub(text, 1, (utf8.offset(text, n - 2) or n - 2) - 1) .. "..."
end

-- is one word a PIECE (shown lessons are recorded on it) or just a search word ("rust")? A piece is named like one
-- (snake_case, PascalCase, a digit) or has its own file: a 3D brief / study, an anim direction page, a verdict
function Routes.isPiece(dept: string, word: string): boolean
	if string.find(word, "_") or string.find(word, "%d") or string.find(word, "%l%u") then
		return true
	end
	local Vault = require("./vault")
	local Config = require("./config")
	local game = Config.game()
	for _, root in if game then { `games/{game}/`, "" } else { "" } do
		for _, f in
			{
				`assets/models/{word}.brief.md`,
				`assets/models/{word}.study.md`,
				`assets/animations/direction/{word}.md`,
			}
		do
			if fs.isFile(root .. f) then
				return true
			end
		end
	end
	return #Vault.verdicts(dept, word) > 0
end

-- `--for <piece|"words">` read: one word is a PIECE (its name + its own brief rank the lessons, and what is shown is
-- recorded on it: Vault.serve); several words are a search. -> query, how the header names it, the piece or nil
function Routes.forFlag(dept: string, given: any): (string?, string?, string?)
	if type(given) ~= "string" or given == "" then
		return nil, nil, nil
	end
	if not string.find(given, "%s") and Routes.isPiece(dept, given) then
		local Vault = require("./vault")
		return Vault.queryFor(dept, given), `the piece {given}`, given
	end
	return given, `"{clip(given, 70)}"`, nil
end

-- opts.query: what the session is building (a piece's name + brief words, a card's title, words); opts.about: how
-- the header names it. Returns the lines and the ids of the lessons shown (a caller with a piece records them:
-- Vault.serve).
function Routes.lines(
	dept: string,
	stage: string,
	opts: {
		query: string?,
		about: string?,
		piece: string?,
		full: number?,
		fullChars: number?,
		count: number?,
		looks: boolean?, -- false: no look neighbours (kit alike) under the closest past pieces
	}?
): ({ string }, { string })
	local s = Routes.stage(dept, stage)
	local out, shownIds = {}, {}
	local o = opts or {}
	if not s then
		local stages = Routes.stages(dept)
		if #stages == 0 then
			table.insert(out, `no route for "{dept}" (departments: {table.concat(Routes.depts(), ", ")})`)
		else
			table.insert(out, `no stage "{stage}" for {dept} — stages: {table.concat(stages, " -> ")}`)
		end
		return out, shownIds
	end
	local stages = Routes.stages(dept)
	local idx = table.find(stages, stage) or 0
	table.insert(out, `== {dept}: stage {idx}/{#stages} "{stage}"  (route: {table.concat(stages, " -> ")})`)
	table.insert(out, `   gate: {s.gate}`)
	for _, c in s.commands do
		table.insert(out, `   {c}`)
	end
	-- the lessons of THIS stage ranked for what is being built (Vault.rank): the best FULL in full, the rest as their
	-- gist. With nothing named, the best-proven and newest first, and the header says how to name the piece.
	local Vault = require("./vault")
	if Vault.exists() then
		local query = o.query or ""
		-- the piece's family (kit/lib/families.luau): its own lessons first, another family's lower
		local family = if o.piece and o.piece ~= "" then require("./families").ofPiece(dept, o.piece) else nil
		local ranked = Vault.rank(dept, query, { stage = stage, stageWords = Routes.words(dept), family = family })
		if #ranked > 0 then
			local n = math.min(o.count or Routes.LESSONS, #ranked)
			local fullN = o.full or Routes.FULL
			local counts = Vault.lessonCounts()
			table.insert(
				out,
				if query ~= ""
					then `   lessons ranked for {o.about or ('"' .. clip(query, 60) .. '"')}{if family
						then ` (family: {family})`
						else ""} (best {n} of {#ranked}, {math.min(fullN, n)} in full; cite: kit lesson used <ids> --piece <kind> <name>):`
					else `   lessons (none named: best-proven + newest {n} of {#ranked}; rank for yours: --for <piece>):`
			)
			-- the best by rank, then the newest few (Vault.pick): a recent tool fact names no word of the piece
			for i, r in Vault.pick(ranked, n, query ~= "") do
				table.insert(out, "     " .. Vault.rankedLine(r, counts, i <= fullN, o.fullChars))
				table.insert(shownIds, r.id)
			end
			if #ranked > n then
				table.insert(out, `     ... more: lune run kit lessons {dept} --stage {stage} <words>`)
			end
		end
		-- the closest past pieces with the owner's number and words (loved, middling or failed): what this piece is
		-- measured against before it is built
		if query ~= "" then
			local similar = Vault.similar(dept, query, Routes.SIMILAR, o.piece)
			if #similar > 0 then
				table.insert(
					out,
					"   closest past pieces (the owner's verdicts; copy what was loved, never a failed route):"
				)
				for _, l in similar do
					table.insert(out, "     " .. l)
				end
			end
		end
		-- the past pieces that LOOK closest, when this piece already has a picture in the look index (kit alike:
		-- the index's own vectors only, no model is loaded; nothing without an index)
		if o.piece and o.piece ~= "" and o.looks ~= false then
			local looks = require("./alike").lines(o.piece, dept, Routes.SIMILAR, true)
			if looks then
				table.insert(out, "   looks closest (kit alike; the owner's verdicts - this piece keeps its own look):")
				for _, l in looks do
					table.insert(out, "     " .. l)
				end
			end
		end
	end
	local nextStage = stages[idx + 1]
	if nextStage then
		table.insert(out, `   next stage: lune run kit help --stage {dept}:{nextStage}`)
	end
	return out, shownIds
end

-- how many of a stage's lessons `kit help --stage` prints, how many of them in full, and how many past pieces
Routes.LESSONS = 6
Routes.FULL = 2
Routes.SIMILAR = 3

-- every stage's words: { [stage]: { word } } (a lesson naming one belongs to that stage)
function Routes.words(dept: string): { [string]: { string } }
	local out = {}
	local d = Routes.load()[dept]
	for _, s in Routes.stages(dept) do
		local st = d and d[s]
		if type(st) == "table" and type(st.words) == "table" then
			out[s] = st.words
		end
	end
	return out
end

return Routes

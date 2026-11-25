-- retrieval.spec.luau (kit) — the vault's lessons are retrieved by RELEVANCE to what is being built (2026-11-07):
-- the ranking beats newest-first on a piece's words, a lesson from another game ranks lower and says so, the stage
-- list keeps two slots for the newest (a tool fact names no word of the piece), the lessons SHOWN for a named piece
-- are recorded and the owner's verdict credits them at half weight, a rejection names its route, the closest past
-- pieces share a word of the piece's name, and the replay eval scores both orders on the pieces whose lessons a
-- session named.
local fs = require("@lune/fs")
local scheduler = require("@lune/task")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Vault = require("../../lib/vault")

local TMP = "kit/selftest/vault/_tmp_retrieval"

local function lesson(file: string, date: string, body: string, extra: string?)
	fs.writeFile(
		`{TMP}/3d/lessons/{file}.md`,
		`---\nkind: lesson\narea: 3d\ndate: {date}\nstages: [surface]\n{extra or ""}---\n\n{body}\n`
	)
end

-- a fresh temp vault (3d lessons + verdicts) and a temp citations file around `body`
local function withVault(body: () -> ())
	if fs.isDir(TMP) then
		fs.removeDir(TMP)
	end
	fs.writeDir(TMP .. "/3d/lessons")
	fs.writeDir(TMP .. "/3d/verdicts")
	lesson("delft", "2026-11-04", "Painted delft ware on turned pots: paint the pattern as a picture per pot.")
	lesson(
		"gunmetal",
		"2026-10-10",
		"Gunmetal slide finish: a blued steel slide needs a value step from the polymer frame or both read as one mass."
	)
	lesson("granite", "2026-10-01", "Granite scans for weathered stone: use the speckle, not the colour.")
	lesson(
		"othergame",
		"2026-11-05",
		"Gunmetal slide finish in that game: a blued steel slide under a polymer frame.",
		"project: SampleOtherGame\n"
	)
	local savedRoot, savedCites, savedStudies = Vault.ROOT, Vault.CITATIONS, Vault.STUDY_ROOTS
	local savedIsGame = Vault.isGame
	-- (the other game is a fixture: no games/ folder is made, so specs running beside this one see none)
	Vault.isGame = function(name: string): boolean
		return name == "SampleOtherGame"
	end
	Vault.ROOT = TMP
	Vault.CITATIONS = TMP .. "/citations.json"
	Vault.STUDY_ROOTS = { TMP .. "/models" } -- (the repo's own studies are no fixture: they change as lanes work)
	local ok, err = pcall(body)
	Vault.ROOT, Vault.CITATIONS, Vault.STUDY_ROOTS = savedRoot, savedCites, savedStudies
	Vault.isGame = savedIsGame
	fs.removeDir(TMP)
	if not ok then
		error(err)
	end
end

local OPTS = { stage = "surface", stageWords = {}, game = "ThisGame", today = "2026-11-06" }

local function idOf(file: string): string
	for _, n in Vault.notes("3d", "lessons") do
		if string.find(n.rel, file, 1, true) then
			return Vault.lessonId(n)
		end
	end
	error("no lesson " .. file)
end

local function firstFile(list: { Vault.Ranked }): string
	return string.match(list[1].note.rel, "([^/]+)$") :: string
end

return function()
	test.suite("vault retrieval: relevance, not the date", function()
		test.case("the search words split names, drop stop words and a plural's s", function()
			local w = table.concat(Vault.words("BulletHoles on the slide_rails"), " ")
			check.equal(w, "bullet hole slide rail")
		end)

		test.case("a piece's words rank the relevant lesson first; nothing named keeps newest first", function()
			withVault(function()
				-- nothing named: the newest home lesson leads (the other game's is newer but ranks x0.6)
				check.equal(firstFile(Vault.rank("3d", "", OPTS)), "delft")
				-- the piece's words: the gunmetal lesson, two weeks older, comes first; the delft one has no shared word
				local ranked = Vault.rank("3d", "gunmetal pistol slide finish", OPTS)
				check.equal(firstFile(ranked), "gunmetal")
				-- (relevance is against the best BM25 in the list: the other game's shorter lesson scores higher
				-- before its x0.6, so the home lesson's is high, not 1)
				check.truthy(ranked[1].relevance > 0.5)
				for _, r in ranked do
					if string.find(r.note.rel, "delft", 1, true) then
						check.equal(r.relevance, 0)
					end
				end
			end)
		end)

		test.case("a lesson another game wrote ranks lower and is labelled", function()
			withVault(function()
				local ranked = Vault.rank("3d", "gunmetal slide finish", OPTS)
				local home, other = nil, nil
				for i, r in ranked do
					if string.find(r.note.rel, "othergame", 1, true) then
						other = i
						check.equal(r.otherGame, "SampleOtherGame")
						check.truthy(string.find(Vault.rankedLine(r, nil, false), "another game", 1, true))
					elseif string.find(r.note.rel, "gunmetal", 1, true) then
						home = i
						check.equal(r.otherGame, nil)
					end
				end
				check.truthy(home and other and home < other)
				-- in its own game it is a home lesson
				local mine = Vault.rank("3d", "gunmetal slide finish", {
					stage = "surface",
					stageWords = {},
					game = "SampleOtherGame",
					today = "2026-11-06",
				})
				for _, r in mine do
					if string.find(r.note.rel, "othergame", 1, true) then
						check.equal(r.otherGame, nil)
					end
				end
			end)
		end)

		test.case(
			"the stage list keeps the newest for its last slots (a tool fact names no word of the piece)",
			function()
				-- eight lessons in rank order a..h; the newest by date are g, h and a flagged one, f
				local function r(name: string, date: string, evidence: number?): any
					return {
						note = { rel = "3d/lessons/" .. name, front = { date = date }, body = "", path = "" },
						id = name,
						score = 0,
						relevance = 0,
						hits = 0,
						evidence = evidence or 0,
					}
				end
				local ranked = {
					r("a", "2026-10-01"),
					r("b", "2026-10-02"),
					r("c", "2026-10-03"),
					r("d", "2026-10-04"),
					r("e", "2026-10-05"),
					r("f", "2026-11-09", -1),
					r("g", "2026-11-08"),
					r("h", "2026-11-07"),
				}
				local ids = {}
				for _, x in Vault.pick(ranked, 6, true) do
					table.insert(ids, x.id)
				end
				-- the best four by rank, then the two newest not in - never the flagged one
				check.equal(table.concat(ids, ","), "a,b,c,d,g,h")
				-- a short list is all by rank (a third at most is kept for the newest)
				ids = {}
				for _, x in Vault.pick(ranked, 2, true) do
					table.insert(ids, x.id)
				end
				check.equal(table.concat(ids, ","), "a,b")
				-- no query: the ranked order as it is
				check.equal(#Vault.pick(ranked, 3, false), 3)
				check.equal(Vault.pick(ranked, 3, false)[3].id, "c")
			end
		)

		test.case("a gist is the lesson's own --gist, else its first sentence, at most 160 characters", function()
			withVault(function()
				lesson(
					"gisted",
					"2026-11-01",
					string.rep("long words here ", 30),
					'gist: "Bake the colour buffer in sRGB."\n'
				)
				for _, n in Vault.notes("3d", "lessons") do
					if string.find(n.rel, "gisted", 1, true) then
						check.equal(Vault.gist(n), "Bake the colour buffer in sRGB.")
					elseif string.find(n.rel, "gunmetal", 1, true) then
						check.equal(
							Vault.gist(n),
							"Gunmetal slide finish: a blued steel slide needs a value step from the polymer frame or both read as one mass."
						)
					end
				end
				lesson("runon", "2026-11-02", string.rep("x", 400))
				for _, n in Vault.notes("3d", "lessons") do
					if string.find(n.rel, "runon", 1, true) then
						check.truthy(#Vault.gist(n) <= 160 + 3)
					end
				end
			end)
		end)
	end)

	test.suite("vault retrieval: what is shown is counted", function()
		test.case(
			"lessons shown for a piece are recorded once; the owner's verdict credits them at half weight",
			function()
				withVault(function()
					local g, d = idOf("gunmetal"), idOf("delft")
					check.equal(#Vault.serve("asset", "pistol", { g, d }, "t"), 2)
					-- shown again before any verdict: nothing new to record
					check.equal(#Vault.serve("asset", "pistol", { g, d }, "t"), 0)
					-- a NAMED citation too (kit lesson used)
					Vault.cite("asset", "pistol", { g }, "t")
					local path = Vault.record({ kind = "asset", name = "pistol", score = 8, words = "great finish" })
					check.truthy(path)
					local c = Vault.lessonCounts()
					check.equal(c[g].helpful, 1)
					check.equal(c[g].servedHelpful, 1)
					check.equal(c[d].helpful, 0)
					check.equal(c[d].served, 1)
					check.equal(c[d].servedHelpful, 1)
					local named, shown = Vault.creditedOn("asset", "pistol")
					check.equal(#named, 1)
					check.equal(#shown, 2)
					-- the line a session reads carries both counts
					for _, r in Vault.rank("3d", "", OPTS) do
						if r.id == d then
							check.truthy(string.find(Vault.rankedLine(r, c, false), "shown 1x +1/-0", 1, true))
							check.truthy(r.evidence > 0)
						end
					end
				end)
			end
		)

		test.case("a shown lesson is flagged only on the weight of several failures (half a named one)", function()
			withVault(function()
				local d = idOf("delft")
				for i = 1, 6 do
					Vault.serve("asset", `piece{i}`, { d }, "t")
					Vault.record({ kind = "asset", name = `piece{i}`, score = 1, words = "bad", route = "typed shells" })
					if i == 6 then
						check.truthy(Vault.lessonCounts()[d].flagged) -- 3 weighted uses, 3 against
					elseif i == 3 or i == 5 then
						check.falsy(Vault.lessonCounts()[d].flagged) -- 1.5, then 2.5 weighted uses: under 3
					end
				end
				-- a flagged lesson is never one of the newest slots
				for _, r in Vault.rank("3d", "granite", OPTS) do
					if r.id == d then
						check.equal(r.evidence, -1)
					end
				end
			end)
		end)

		test.case(
			"the verdict's printout credits exactly what the counters count (an older citation, two verdicts)",
			function()
				withVault(function()
					local g = idOf("gunmetal")
					-- cited, then a verdict, then a second one: as in Vault.lessonCounts, the citation's credit goes to
					-- the piece's NEWEST verdict after it - each printout names it, the counters hold it once
					Vault.cite("asset", "lamp", { g }, "t")
					local p1 = Vault.record({ kind = "asset", name = "lamp", score = 8, words = "good" }) :: string
					local named, shown = Vault.creditedOn("asset", "lamp", string.sub(p1, #Vault.ROOT + 2, -4))
					check.equal(#named, 1)
					check.equal(#shown, 0)
					scheduler.wait(1.1)
					local p2 = Vault.record({ kind = "asset", name = "lamp", score = 9, words = "better" }) :: string
					named = Vault.creditedOn("asset", "lamp", string.sub(p2, #Vault.ROOT + 2, -4))
					check.equal(#named, 1) -- the 9 now scores the cited lesson
					local c = Vault.lessonCounts()[g]
					check.equal(c.helpful, 1) -- one piece of evidence, not two
					check.equal(c.cites, 1)
				end)
			end
		)

		test.case("one word is a piece only when it is named like one or has its own file", function()
			local Routes = require("../../lib/routes")
			check.falsy(Routes.isPiece("3d", "rust"))
			check.truthy(Routes.isPiece("3d", "town_tester_bed"))
			check.truthy(Routes.isPiece("anim", "DTDrillSpin"))
			check.truthy(Routes.isPiece("3d", "m1911"))
			local q, _about, piece = Routes.forFlag("3d", "rust")
			check.equal(q, "rust")
			check.equal(piece, nil) -- a search: nothing is recorded
			q, _about, piece = Routes.forFlag("3d", "gunmetal slide finish")
			check.equal(piece, nil)
		end)

		test.case("a project's own lessons are never 'another game' (only a real game folder is)", function()
			withVault(function()
				lesson(
					"installed",
					"2026-11-06",
					"Gunmetal slide finish in an installed project.",
					"project: SomeProject\n"
				)
				for _, r in Vault.rank("3d", "gunmetal", OPTS) do
					if string.find(r.note.rel, "installed", 1, true) then
						check.equal(r.otherGame, nil)
					end
				end
			end)
		end)

		test.case("a rejection names the route that failed in the graveyard", function()
			withVault(function()
				Vault.record({
					kind = "asset",
					name = "barrel",
					score = 1,
					words = "horrible",
					route = "round-body + colour-band route",
				})
				local rows = Vault.rows(Vault.dir("3d", "graveyard.md"))
				check.equal(rows[#rows][1], "barrel: round-body + colour-band route")
				local v = Vault.verdicts("3d", "barrel")[1]
				check.truthy(string.find(v.body, "The route that failed: round-body", 1, true))
			end)
		end)
	end)

	test.suite("vault retrieval: past pieces and the replay", function()
		test.case("the closest past pieces share a word of the piece's name and carry the owner's words", function()
			withVault(function()
				Vault.record({ kind = "asset", name = "wine_barrel", score = 9, words = "amazing barrel oak staves" })
				Vault.record({
					kind = "asset",
					name = "street_lamp",
					score = 2,
					words = "horrible lamp colour",
					route = "colour bands on a generated body",
				})
				local near = Vault.similar("3d", "oak barrel staves hoops", 3, "oak_barrel")
				check.equal(#near, 1)
				check.truthy(string.find(near[1], "9/10 wine_barrel", 1, true))
				check.truthy(string.find(near[1], "loved", 1, true))
				-- the lamp shares no word of "oak_barrel": not shown however its words match
				check.equal(#Vault.similar("3d", "horrible lamp colour", 3, "oak_barrel"), 0)
				-- one shared word is chance, not a similar piece
				check.equal(#Vault.similar("3d", "lamp", 3), 0)
				local lamp = Vault.similar("3d", "street lamp gas lantern", 3)
				check.truthy(string.find(lamp[1], "2/10 street_lamp", 1, true))
				check.truthy(string.find(lamp[1], "failed", 1, true))
			end)
		end)

		test.case(
			"the replay scores both orders on a piece whose lessons a session named, as of the day before",
			function()
				withVault(function()
					-- the session named the OLD gunmetal lesson on 2026-11-06; ranked for "pistol slide gunmetal" it is
					-- in front, newest-first (stage list of 6 here holds all four: k = 1 makes the difference visible)
					fs.writeFile(
						Vault.CITATIONS :: string,
						`[\{"date":"2026-11-06","at":1,"dept":"3d","kind":"asset","name":"gunmetal_slide","lessons":["{idOf(
							"gunmetal"
						)}"]\}]`
					)
					local rows, old, new = Vault.eval("3d", 1)
					check.equal(#rows, 1)
					check.equal(rows[1].found, 1)
					check.equal(old, 0) -- newest first: othergame (11-05) leads the stage
					check.equal(new, 1) -- ranked for the piece's name: gunmetal leads
					-- a served row is no label (it is the ranker's own output)
					fs.writeFile(
						Vault.CITATIONS :: string,
						`[\{"date":"2026-11-06","at":1,"dept":"3d","kind":"asset","name":"x","served":true,"lessons":["{idOf(
							"gunmetal"
						)}"]\}]`
					)
					check.equal(#Vault.evalCases("3d"), 0)
					-- a study's "Lessons applied" ids are a case of their own (the session that read them named them)
					fs.writeDir(TMP .. "/models")
					fs.writeFile(
						`{TMP}/models/delft_pot.study.md`,
						`# delft_pot\n\n## Lessons applied\n- {idOf("delft")}: applied - the pattern painted per pot\n\n## Notes\n`
					)
					local cases = Vault.evalCases("3d")
					check.equal(#cases, 1)
					check.equal(cases[1].source, "study")
					check.equal(cases[1].name, "delft_pot")
					check.equal(cases[1].ids[1], idOf("delft"))
				end)
			end
		)
	end)
end

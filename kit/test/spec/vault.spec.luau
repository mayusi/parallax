-- vault.spec.luau (kit) — the knowledge vault: frontmatter round-trips, verdict scores clamp to 0-10, the health
-- check CATCHES the bad fixtures (no frontmatter, a dangling link, a score on the wrong scale) and passes the good
-- one, and a department page stays inside its token budget.
local fs = require("@lune/fs")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Vault = require("../../lib/vault")

local FIXTURES = "kit/selftest/vault"

local function withRoot(root: string, body: () -> ())
	local saved = Vault.ROOT
	Vault.ROOT = root
	local ok, err = pcall(body)
	Vault.ROOT = saved
	if not ok then
		error(err)
	end
end

local function problemsNaming(problems: { Vault.Problem }, needle: string): number
	local n = 0
	for _, p in problems do
		if string.find(p.path, needle, 1, true) then
			n += 1
		end
	end
	return n
end

return function()
	test.suite("vault: frontmatter", function()
		test.case("writes YAML the parser reads back (quotes, colons, lists)", function()
			local front = {
				kind = "verdict",
				area = "ui",
				name = 'A: b "c"',
				score = 9.2,
				date = "2026-10-16",
				tags = { "x", "y z" },
			}
			local text = Vault.frontmatter(front) .. "\n\nbody\n"
			local parsed, body = Vault.parse(text)
			check.truthy(parsed)
			if parsed then
				check.equal(parsed.name, 'A: b "c"')
				check.equal(parsed.score, 9.2)
				check.equal(parsed.tags[2], "y z")
			end
			check.equal(body, "body\n")
		end)
		test.case("a note without frontmatter is refused with a reason", function()
			local parsed, why = Vault.parse("# just a heading\n\ntext\n")
			check.falsy(parsed)
			check.truthy(string.find(why, "frontmatter", 1, true))
		end)
	end)

	test.suite("vault: the health check", function()
		test.case("catches the bad fixtures and names each one", function()
			withRoot(FIXTURES, function()
				local problems = Vault.check()
				check.equal(problemsNaming(problems, "no-frontmatter.md"), 1)
				check.equal(problemsNaming(problems, "dangling-link.md") >= 1, true)
				check.equal(problemsNaming(problems, "score-out-of-range.md"), 1)
				-- the bad department has no index either
				check.equal(problemsNaming(problems, "vault/bad:") + problemsNaming(problems, "vault/bad") >= 1, true)
				-- and the good fixture is clean
				check.equal(problemsNaming(problems, "/good/"), 0)
			end)
		end)
		test.case("a missing index is a problem; a folder link resolves", function()
			withRoot(FIXTURES, function()
				local problems = Vault.check()
				local indexProblem = 0
				for _, p in problems do
					if string.find(p.problem, "no index.md", 1, true) and string.find(p.path, "bad", 1, true) then
						indexProblem += 1
					end
				end
				check.equal(indexProblem, 1)
				check.equal(Vault.resolve("good/lessons", {}), true)
				check.equal(Vault.resolve("good/nothing", {}), false)
			end)
		end)
	end)

	test.suite("vault: pages and lessons", function()
		test.case("the department page respects its budget and says what was cut", function()
			withRoot(FIXTURES, function()
				local page = Vault.page("good", 10) -- 10 tokens ~ 40 chars
				check.truthy(#page <= 40 + 200)
				check.truthy(string.find(page, "cut by the vault budget", 1, true))
			end)
		end)
		test.case("a trimmed page, cut note included, is never over its budget", function()
			withRoot(FIXTURES, function()
				local full = Vault.page("good", 100000)
				check.truthy(#full > 160) -- the fixture page is longer than the budget below
				local page = Vault.page("good", 40) -- 40 tokens = 160 chars, room for the cut note
				check.truthy(#page <= 160)
				check.truthy(string.find(page, "cut by the vault budget", 1, true))
			end)
		end)
		test.case("golden and graveyard rows print newest first, and an empty untitled note is no problem", function()
			local tmp = "kit/selftest/vault/_tmp_page"
			if fs.isDir(tmp) then
				fs.removeDir(tmp)
			end
			fs.writeDir(tmp .. "/x/verdicts")
			fs.writeFile(tmp .. "/x/index.md", "---\narea: x\nkind: index\ndate: 2026-10-18\n---\n\n# x\n")
			fs.writeFile(
				tmp .. "/x/graveyard.md",
				"# g\n\n| tried | date |\n|---|---|\n| seeded late | 2026-10-01 |\n| newest | 2026-10-17 |\n| middle | 2026-10-09 |\n| seed row two | 2026-09-30 |\n"
			)
			fs.writeFile(tmp .. "/x/verdicts/Untitled.md", "")
			local ok, err = pcall(function()
				withRoot(tmp, function()
					local page = Vault.page("x", 100000)
					local a = string.find(page, "newest", 1, true)
					local b = string.find(page, "middle", 1, true)
					local c = string.find(page, "seeded late", 1, true)
					check.truthy(a and b and c and a < b and b < c)
					check.equal(problemsNaming(Vault.check(), "Untitled"), 0)
				end)
			end)
			fs.removeDir(tmp)
			if not ok then
				error(err)
			end
		end)
		test.case("a lesson's stage: a hand tag wins, else its best-scoring stage words", function()
			local words = { surface = { "texture", "uv", "colour" }, shape = { "bevel", "cad" }, judge = { "judge" } }
			local function note(body: string, front: any?): any
				return { front = front or {}, body = body, rel = "x", path = "x" }
			end
			check.equal(
				table.concat(Vault.lessonStages(note("UV seams show on a texture", nil), words), ","),
				"surface"
			)
			-- "uv" only at the start of a word: "fluvial" is not a UV lesson
			check.equal(#Vault.lessonStages(note("fluvial erosion", nil), words), 0)
			-- the opening counts double: a bevel lesson that mentions a texture later is a shape lesson
			check.equal(
				table.concat(Vault.lessonStages(note("Bevel every CAD edge; the texture comes later", nil), words), ","),
				"shape"
			)
			check.equal(
				table.concat(Vault.lessonStages(note("UV seams on a texture", { stages = { "judge" } }), words), ","),
				"judge"
			)
		end)
		test.case("every stage of every route has its words", function()
			local Routes = require("../../lib/routes")
			for _, d in Routes.depts() do
				local w = Routes.words(d)
				for _, s in Routes.stages(d) do
					check.truthy(w[s] and #w[s] > 0)
				end
			end
		end)
		test.case("a piece rejected again on a later day is counted; the first rejection is not", function()
			local tmp = "kit/selftest/vault/_tmp_repeats"
			if fs.isDir(tmp) then
				fs.removeDir(tmp)
			end
			fs.writeDir(tmp .. "/x/verdicts")
			local function v(file: string, name: string, score: number, date: string)
				fs.writeFile(
					`{tmp}/x/verdicts/{file}.md`,
					`---\nkind: verdict\narea: x\nname: {name}\nscore: {score}\ndate: {date}\n---\n\nwords\n`
				)
			end
			v("a", "barrel", 1, "2026-10-16")
			v("b", "Barrel (batch 3)", 2, "2026-10-17")
			v("c", "lamp", 1, "2026-10-17")
			v("d", "lamp", 1, "2026-10-17") -- the same day: one round, not a repeat
			v("e", "chest", 8, "2026-10-17")
			local ok, err = pcall(function()
				withRoot(tmp, function()
					local r = Vault.repeats("x", "2026-10-18")
					check.equal(r.rejected, 4)
					check.equal(#r.all, 1)
					check.equal(r.all[1].first, "2026-10-16")
					check.equal(r.recent, 1)
				end)
			end)
			fs.removeDir(tmp)
			if not ok then
				error(err)
			end
		end)
		test.case(
			"standing orders: one per line, a struck-through one withdrawn, the source note dropped on pages",
			function()
				local tmp = "kit/selftest/vault/_tmp_orders"
				if fs.isDir(tmp) then
					fs.removeDir(tmp)
				end
				fs.writeDir(tmp .. "/x")
				fs.writeFile(
					`{tmp}/x/orders.md`,
					"---\nkind: orders\narea: x\ndate: 2026-10-21\n---\n\n# x\n\nintro text\n\n"
						.. "- keep the hybrid (the owner, 2026-10-14; memory a-note)\n"
						.. "- ~~an old order~~\n"
						.. "* typed with a star\n"
				)
				local ok, err = pcall(function()
					withRoot(tmp, function()
						local o = Vault.orders("x")
						check.equal(#o, 2)
						check.equal(o[1], "keep the hybrid")
						check.equal(o[2], "typed with a star")
						check.equal(
							Vault.orders("x", true)[1],
							"keep the hybrid (the owner, 2026-10-14; memory a-note)"
						)
						check.equal(#Vault.orders("nothing"), 0)
						-- the page opens with them (trimmed from its end, so never cut)
						local page = Vault.page("x", 300)
						check.truthy(string.find(page, "STANDING ORDERS", 1, true))
						check.falsy(Vault.page("x", 300, true):find("STANDING ORDERS", 1, true))
					end)
				end)
				fs.removeDir(tmp)
				if not ok then
					error(err)
				end
			end
		)
		test.case(
			"cited lessons are credited by the owner's later verdict on the piece; three harmful flag one",
			function()
				local tmp = "kit/selftest/vault/_tmp_cites"
				if fs.isDir(tmp) then
					fs.removeDir(tmp)
				end
				fs.writeDir(tmp .. "/3d/lessons")
				fs.writeDir(tmp .. "/3d/verdicts")
				local function lesson(file: string)
					fs.writeFile(
						`{tmp}/3d/lessons/{file}.md`,
						`---\nkind: lesson\narea: x\ndate: 2026-10-01\nby: t\n---\n\n{file} text\n`
					)
				end
				local function verdict(file: string, name: string, score: number, date: string, source: string?)
					fs.writeFile(
						`{tmp}/3d/verdicts/{file}.md`,
						`---\nkind: verdict\narea: x\nname: {name}\nscore: {score}\ndate: {date}\nsource: {source or "owner"}\n---\n\nw\n`
					)
				end
				lesson("good-one")
				lesson("bad-one")
				local savedCites = Vault.CITATIONS
				Vault.CITATIONS = tmp .. "/citations.json"
				local ok, err = pcall(function()
					withRoot(tmp, function()
						local ids = {}
						for _, n in Vault.notes("3d", "lessons") do
							ids[string.match(n.rel, "([^/]+)$")] = Vault.lessonId(n)
						end
						local good = ids["good-one"]
						local bad = ids["bad-one"]
						check.truthy(string.match(good, "^L%-3d%-%x%x%x%x%x%x$"))
						check.equal(Vault.lessonById(good).rel, "3d/lessons/good-one")
						-- cite both on a crate the owner later loved, and the bad one on three rejected pieces
						local _, e = Vault.cite("asset", "Wood Crate", { good, bad }, "t")
						check.equal(e, nil)
						for _, piece in { "lamp", "barrel", "chest" } do
							Vault.cite("asset", piece, { bad }, "t")
						end
						local today = Vault.today()
						verdict("crate", "wood_crate", 8, today) -- another spelling of the same piece
						verdict("lamp", "lamp", 2, today)
						verdict("barrel", "barrel", 1, today)
						verdict("chest", "chest", 3, today)
						verdict("old", "lamp", 9, "2000-01-01") -- before the citation: ignored
						local c = Vault.lessonCounts()
						check.equal(c[good].cites, 1)
						check.equal(c[good].helpful, 1)
						check.equal(c[bad].cites, 4)
						check.equal(c[bad].helpful, 1)
						check.equal(c[bad].harmful, 3)
						check.truthy(c[bad].flagged)
						check.falsy(c[good].flagged)
						-- an inferred verdict is not the owner's: it credits nothing
						Vault.cite("asset", "stool", { good }, "t")
						verdict("stool", "stool", 9, today, "inferred")
						check.equal(Vault.lessonCounts()[good].helpful, 1)
						check.truthy(
							string.find(
								Vault.lessonLineWithId(Vault.lessonById(bad) :: any, c),
								"FLAGGED harmful",
								1,
								true
							)
						)
					end)
				end)
				Vault.CITATIONS = savedCites
				fs.removeDir(tmp)
				if not ok then
					error(err)
				end
			end
		)
		test.case(
			"two distils in a row keep the first one's surviving rules; edit and retire touch one rule",
			function()
				local tmp = "kit/selftest/vault/_tmp_rules"
				if fs.isDir(tmp) then
					fs.removeDir(tmp)
				end
				fs.writeDir(tmp .. "/3d")
				-- an older distil written before live rules existed: its rules seed the live list
				fs.writeFile(
					`{tmp}/3d/distil.md`,
					"# 3d\n\n## 2026-10-01 — 3 verdict(s)\n\n1. old rule one\n2. old rule two\n"
				)
				local ok, err = pcall(function()
					withRoot(tmp, function()
						local empty = { since = nil, verdicts = {}, lessons = {}, lines = {} }
						Vault.writeDistil("3d", { "first distil rule" }, empty)
						Vault.writeDistil("3d", { "second distil rule" }, empty)
						local texts = {}
						for _, r in Vault.rules("3d") do
							texts[r.id] = r.text
						end
						check.equal(texts["R-3d-1"], "old rule one")
						check.equal(texts["R-3d-2"], "old rule two")
						check.equal(texts["R-3d-3"], "first distil rule") -- survived the second distil
						check.equal(texts["R-3d-4"], "second distil rule")
						-- one edit, one retirement; ids never move
						check.equal(Vault.ruleChange("3d", "edit", "R-3d-2", "old rule two, sharpened"), "R-3d-2")
						check.equal(
							Vault.ruleChange("3d", "retire", "R-3d-1", "the barrel verdict killed it"),
							"R-3d-1"
						)
						local _, why = Vault.ruleChange("3d", "retire", "R-3d-1", "again")
						check.truthy(why and string.find(why, "already retired", 1, true))
						local byId = {}
						for _, r in Vault.rules("3d") do
							byId[r.id] = r
						end
						check.equal(byId["R-3d-2"].text, "old rule two, sharpened")
						check.truthy(byId["R-3d-1"].retired and string.find(byId["R-3d-1"].retired, "barrel", 1, true))
						check.equal(Vault.ruleById("R-3d-4").text, "second distil rule")
						-- a line typed into rules.md by hand survives the next rewrite; re-adding a live rule is that rule
						fs.writeFile(
							`{tmp}/3d/rules.md`,
							fs.readFile(`{tmp}/3d/rules.md`) .. "- my own note about bevels\n"
						)
						check.equal(Vault.ruleChange("3d", "add", nil, "second distil rule"), "R-3d-4")
						check.truthy(
							string.find(fs.readFile(`{tmp}/3d/rules.md`), "- my own note about bevels", 1, true)
						)
						check.equal(#Vault.rules("3d"), 4)
						-- the page shows the live rules only
						local page = Vault.page("3d", 2000)
						check.truthy(string.find(page, "R-3d-3: first distil rule", 1, true))
						check.falsy(string.find(page, "old rule one", 1, true))
					end)
				end)
				fs.removeDir(tmp)
				if not ok then
					error(err)
				end
			end
		)
		test.case(
			"credit is fair: only verdicts after the citation, one count per piece and verdict, same-day pairs",
			function()
				local task = require("@lune/task")
				local tmp = "kit/selftest/vault/_tmp_fair"
				if fs.isDir(tmp) then
					fs.removeDir(tmp)
				end
				fs.writeDir(tmp .. "/3d/lessons")
				fs.writeDir(tmp .. "/3d/verdicts")
				fs.writeFile(`{tmp}/3d/lessons/l.md`, "---\nkind: lesson\narea: 3d\ndate: 2026-10-01\n---\n\nl text\n")
				local today = Vault.today()
				local function v(file: string, name: string, score: number)
					fs.writeFile(
						`{tmp}/3d/verdicts/{file}.md`,
						`---\nkind: verdict\narea: 3d\nname: {name}\nscore: {score}\ndate: {today}\nsource: owner\n---\n\nw\n`
					)
				end
				local savedCites = Vault.CITATIONS
				Vault.CITATIONS = tmp .. "/citations.json"
				local ok, err = pcall(function()
					withRoot(tmp, function()
						local id = Vault.lessonId(Vault.notes("3d", "lessons")[1])
						-- the morning's 2 came BEFORE the lessons were cited for the rebuild: it blames nobody
						v("lamp-morning", "lamp", 2)
						task.wait(1.1)
						Vault.cite("asset", "lamp", { id }, "t")
						local c = Vault.lessonCounts()[id]
						check.equal(c.harmful, 0)
						-- three citations on three rebuilds of one piece, then ONE score: one piece of evidence
						Vault.cite("asset", "lamp", { id }, "t")
						Vault.cite("asset", "lamp", { id }, "t")
						task.wait(1.1)
						v("lamp-evening", "lamp", 1)
						c = Vault.lessonCounts()[id]
						check.equal(c.harmful, 1)
						check.equal(c.cites, 1)
						check.falsy(c.flagged)
						-- a 3 and then a 9 on the same day are a pair
						v("crate-a", "crate", 3)
						task.wait(1.1)
						v("crate-b", "crate", 9)
						local found = false
						for _, p in Vault.pairs("3d") do
							if p.name == "crate" and p.low.front.score == 3 and p.high.front.score == 9 then
								found = true
							end
						end
						check.truthy(found)
					end)
				end)
				Vault.CITATIONS = savedCites
				fs.removeDir(tmp)
				if not ok then
					error(err)
				end
			end
		)
		test.case("a no that became a yes writes one pair note; the gardener lists near-duplicate lessons", function()
			local tmp = "kit/selftest/vault/_tmp_garden"
			if fs.isDir(tmp) then
				fs.removeDir(tmp)
			end
			fs.writeDir(tmp .. "/3d/verdicts")
			fs.writeDir(tmp .. "/3d/lessons")
			local function v(file: string, name: string, score: number, date: string, source: string?)
				fs.writeFile(
					`{tmp}/3d/verdicts/{file}.md`,
					`---\nkind: verdict\narea: 3d\nname: {name}\nscore: {score}\ndate: {date}\nsource: {source or "owner"}\n---\n\nwords {file}\n`
				)
			end
			v("crate-a", "crate", 2, "2026-10-01")
			v("crate-b", "Crate", 8, "2026-10-03") -- a yes after a no: a pair
			v("lamp-a", "lamp", 5, "2026-10-01")
			v("lamp-b", "lamp", 6, "2026-10-02") -- one point: no pair
			v("stool-a", "stool", 1, "2026-10-01")
			v("stool-b", "stool", 9, "2026-10-02", "inferred") -- a model's score: no pair
			local same = "bevel every visible edge of a hard surface prop before baking its maps so highlights catch"
			fs.writeFile(
				`{tmp}/3d/lessons/2026-10-02-a.md`,
				`---\nkind: lesson\narea: 3d\ndate: 2026-10-02\n---\n\n{same}\n`
			)
			fs.writeFile(
				`{tmp}/3d/lessons/2026-10-05-b.md`,
				`---\nkind: lesson\narea: 3d\ndate: 2026-10-05\n---\n\n{same} nicely\n`
			)
			local ok, err = pcall(function()
				withRoot(tmp, function()
					local pairs_ = Vault.pairs("3d")
					check.equal(#pairs_, 1)
					check.equal(pairs_[1].low.front.score, 2)
					check.equal(pairs_[1].high.front.score, 8)
					local items = Vault.garden("3d")
					local dup, pair = 0, 0
					for _, l in items do
						if string.find(l, "near-duplicate", 1, true) then
							dup += 1
						end
						if string.find(l, "new pair", 1, true) then
							pair += 1
						end
					end
					check.equal(dup, 1)
					check.equal(pair, 1)
					check.truthy(fs.isFile(`{tmp}/3d/pairs/crate--2026-10-03.md`))
					-- once written, a pair is not written again
					check.equal(#Vault.writePairs("3d"), 0)
					fs.writeFile(`{tmp}/3d/index.md`, "---\nkind: index\narea: 3d\ndate: 2026-10-01\n---\n\n# 3d\n")
					check.equal(problemsNaming(Vault.check(), "pairs"), 0) -- the pair note's frontmatter and links hold
				end)
			end)
			fs.removeDir(tmp)
			if not ok then
				error(err)
			end
		end)
		test.case("kit new's nearest loved piece: shared words win, else the newest scored one", function()
			local tmp = "kit/selftest/vault/_tmp_near"
			if fs.isDir(tmp) then
				fs.removeDir(tmp)
			end
			fs.writeDir(tmp .. "/3d")
			fs.writeFile(
				`{tmp}/3d/golden.md`,
				"# golden\n\n| Piece | Score | Date | Words | Feature | Link |\n|---|---|---|---|---|---|\n"
					.. "| wine_barrel | 9 | 2026-10-10 | lovely | staves | |\n"
					.. "| street_lamp | 8 | 2026-10-12 | good | glass | |\n"
					.. "| waiting_piece | | 2026-10-13 | (awaits) | | |\n"
			)
			local ok, err = pcall(function()
				withRoot(tmp, function()
					local r, n = Vault.nearestGolden("3d", "oak_barrel")
					check.equal(r and r[1], "wine_barrel")
					check.equal(n, 1)
					local r2, n2 = Vault.nearestGolden("3d", "SpaceCrate")
					check.equal(r2 and r2[1], "street_lamp") -- no shared word: the newest SCORED loved piece
					check.equal(n2, 0)
					check.equal(Vault.nearestGolden("vfx", "anything"), nil)
				end)
			end)
			fs.removeDir(tmp)
			if not ok then
				error(err)
			end
		end)
		test.case(
			"the distil window: same-day verdicts after it count, a retire never resets it, struck rules stay",
			function()
				local tmp = "kit/selftest/vault/_tmp_window"
				if fs.isDir(tmp) then
					fs.removeDir(tmp)
				end
				fs.writeDir(tmp .. "/3d/verdicts")
				fs.writeFile(
					`{tmp}/3d/distil.md`,
					"# 3d\n\n## 2026-10-10 — 3 verdict(s) + 0 lesson(s) since x · at 1000\n\n1. a rule\n"
				)
				local function v(file: string, name: string, time: number)
					fs.writeFile(
						`{tmp}/3d/verdicts/{file}.md`,
						`---\nkind: verdict\narea: 3d\nname: {name}\nscore: 5\ndate: 2026-10-10\nsource: owner\ntime: {time}\n---\n\nw\n`
					)
				end
				v("before", "early", 500) -- the same day, before the distil: already distilled
				for i = 1, 5 do
					v(`p{i}`, `piece{i}`, 2000 + i)
				end
				local ok, err = pcall(function()
					withRoot(tmp, function()
						check.equal(Vault.distilDue("3d"), 5)
						check.equal(#Vault.distil("3d").verdicts, 5) -- the packet holds what the count counted
						-- a retire is history, not a distil: the window stays and the five are still due
						Vault.logRuleChanges("3d", { "retired R-3d-1: wrong" }, "t")
						check.equal(Vault.lastDistil("3d"), "2026-10-10")
						check.equal(Vault.distilDue("3d"), 5)
						-- same day, same piece: the written time orders them, not the file time
						v("x--2026-10-10", "twice", 20)
						v("x--2026-10-10-2", "twice", 10)
						local newest = Vault.verdicts("3d", "twice")[1]
						check.equal(newest.front.time, 20)
						-- a rule struck through by hand reads as retired and survives the next rewrite
						fs.writeFile(
							`{tmp}/3d/rules.md`,
							"---\nkind: rules\narea: 3d\ndate: 2026-10-10\n---\n\n- ~~R-3d-1 (2026-10-01): a rule~~\n"
						)
						local r = Vault.ruleById("R-3d-1")
						check.truthy(r and r.retired == "struck through by hand")
						check.equal(Vault.ruleChange("3d", "add", nil, "a new rule"), "R-3d-2") -- the id is never reused
						check.truthy(Vault.ruleById("R-3d-1") and Vault.ruleById("R-3d-1").retired)
					end)
				end)
				fs.removeDir(tmp)
				if not ok then
					error(err)
				end
			end
		)
		test.case("a distil is due after five owner verdicts since the last one; inferred ones do not count", function()
			local tmp = "kit/selftest/vault/_tmp_distil_due"
			if fs.isDir(tmp) then
				fs.removeDir(tmp)
			end
			fs.writeDir(tmp .. "/x/verdicts")
			fs.writeFile(
				`{tmp}/x/distil.md`,
				"---\nkind: distil\narea: x\ndate: 2026-10-10\n---\n\n# distil\n\n## 2026-10-10\n\n- a rule\n"
			)
			local function v(file: string, date: string, source: string)
				fs.writeFile(
					`{tmp}/x/verdicts/{file}.md`,
					`---\nkind: verdict\narea: x\nname: {file}\nscore: 5\ndate: {date}\nsource: {source}\n---\n\nwords\n`
				)
			end
			v("old", "2026-10-09", "owner") -- before the last distil
			for i = 1, 4 do
				v(`p{i}`, "2026-10-12", "owner")
			end
			v("guess", "2026-10-12", "inferred")
			local ok, err = pcall(function()
				withRoot(tmp, function()
					check.equal(Vault.distilDue("x"), nil) -- four owner verdicts: not yet
					v("p5", "2026-10-13", "quoted") -- the owner's quoted words count
					local n, cmd = Vault.distilDue("x")
					check.equal(n, 5)
					check.truthy(cmd and string.find(cmd, "kit vault distil x", 1, true))
				end)
			end)
			fs.removeDir(tmp)
			if not ok then
				error(err)
			end
		end)
		test.case("lesson lines carry date, author and the text with no trailing space", function()
			withRoot(FIXTURES, function()
				local lines = Vault.lessons("good")
				check.equal(#lines, 1)
				check.truthy(string.find(lines[1], "^%- 2026%-10%-16 %(selftest, kit%): A well%-formed lesson"))
				check.falsy(string.find(lines[1], "%s$"))
			end)
		end)
		test.case("a score of 85 is refused by the record (0-10 only)", function()
			if fs.isDir(Vault.ROOT) then
				-- the real vault is not touched by the spec: only the parser's rule is asserted
				local parsed = Vault.parse("---\nkind: verdict\narea: ui\nscore: 85\ndate: 2026-10-16\n---\n\nx\n")
				check.truthy(parsed)
			end
			withRoot(FIXTURES, function()
				local problems = Vault.check()
				local scale = 0
				for _, p in problems do
					if string.find(p.problem, "score must be 0-10", 1, true) then
						scale += 1
					end
				end
				check.equal(scale, 1)
			end)
		end)
		test.case("a words search: no words is an empty list, and every hit says it came from the words", function()
			withRoot(FIXTURES, function()
				check.equal(#Vault.search({}, 10), 0)
				for _, r in Vault.search({ "frontmatter" }, 10) do
					check.equal(r.via, "words")
				end
			end)
		end)
	end)

	test.suite("vault: the weekly audit, distil and trend", function()
		local AUDIT = FIXTURES .. "/audit"
		test.case("the audit flags a stale golden row, an orphan golden row and a grave without a reason", function()
			withRoot(AUDIT, function()
				check.equal(#Vault.check(), 0) -- the fixture is well formed: these are warnings, never gate failures
				local warnings = Vault.audit()
				local stale, orphan, why, source = 0, 0, 0, 0
				for _, w in warnings do
					if string.find(w.warning, "STALE", 1, true) then
						stale += 1
					elseif string.find(w.warning, "no verdict note behind it", 1, true) then
						orphan += 1
					elseif string.find(w.warning, "nothing about WHY", 1, true) then
						why += 1
					elseif string.find(w.warning, "has no source", 1, true) then
						source += 1
					end
				end
				check.equal(stale, 1) -- widget: golden 8 on 10-10, rejected 2 on 10-12
				check.equal(orphan, 1) -- orphan: no link
				check.equal(why, 1)
				check.equal(source, 1)
			end)
		end)
		test.case(
			"distil packets the verdicts after a date, oldest first, and writes the rules with their sources",
			function()
				withRoot(AUDIT, function()
					local all = Vault.distil("3d")
					check.equal(#all.verdicts, 2)
					check.equal(tostring(all.verdicts[1].front.date), "2026-10-10")
					local since = Vault.distil("3d", "2026-10-11")
					check.equal(#since.verdicts, 1)
					check.truthy(string.find(table.concat(since.lines, "\n"), "PROPOSE three rules", 1, true))
				end)
				local tmp = "kit/selftest/vault/_distil_tmp"
				if fs.isDir(tmp) then
					fs.removeDir(tmp)
				end
				fs.writeDir(tmp)
				fs.writeDir(tmp .. "/3d")
				withRoot(tmp, function()
					local path = Vault.writeDistil(
						"3d",
						{ "when the bevel goes, the owner's score goes with it" },
						{ since = nil, verdicts = {}, lessons = {}, lines = {} },
						"selftest"
					)
					check.truthy(fs.isFile(path))
					check.truthy(string.find(fs.readFile(path), "1. when the bevel goes", 1, true))
					check.equal(Vault.lastDistil("3d"), Vault.today())
				end)
				fs.removeDir(tmp)
			end
		)
		test.case("the inbox counts the owner's unfiled lines apart from the unreadable ones", function()
			withRoot(AUDIT, function()
				local pending, unreadable = Vault.inboxPending()
				check.equal(pending, 1)
				check.equal(unreadable, 1)
				check.equal(#Vault.check(), 0) -- an inbox with lines is not a broken note
			end)
		end)
		test.case("behind: a missing stamp file means never synced; a stamp in the future means in step", function()
			local missing = Vault.behind("kit/selftest/vault/_no_such_stamp.json")
			local lessons = nil
			for _, b in missing do
				if b.store == "lessons" then
					lessons = b
				end
			end
			check.truthy(lessons ~= nil and lessons.never == true and lessons.files > 0)
			local tmp = "kit/selftest/vault/_stamp_tmp.json"
			fs.writeFile(tmp, '{"lessons": 1e12, "ui": 1e12, "vfx": 1e12, "anim": 1e12, "sfx": 1e12}')
			check.equal(#Vault.behind(tmp), 0)
			fs.removeFile(tmp)
		end)
		test.case("the trend reports a piece's trajectory and the window means", function()
			withRoot(AUDIT, function()
				-- seen from 10-18: the 10-12 rejection is inside the last 7 days, the 10-10 praise in the 7 before
				local lines = table.concat(Vault.trend("3d", "2026-10-18"), "\n")
				check.truthy(string.find(lines, "2 verdict(s), 2 scored", 1, true))
				check.truthy(string.find(lines, "widget: 8.0 -> 2.0 (DOWN)", 1, true))
				check.truthy(string.find(lines, "last 7 d: 1 at 2.0 (-6.0 vs the 7 d before)", 1, true))
			end)
		end)
	end)

	test.suite("vault: supersedes, retired lessons, related notes, rules on the page", function()
		local TMP = "kit/selftest/vault/_graph_tmp"
		local function build()
			if fs.isDir(TMP) then
				fs.removeDir(TMP)
			end
			for _, d in { TMP, TMP .. "/3d", TMP .. "/3d/lessons", TMP .. "/3d/verdicts" } do
				fs.writeDir(d)
			end
			fs.writeFile(TMP .. "/3d/index.md", "# 3D\n\nthe route\n")
			local function note(path: string, front: string, body: string)
				fs.writeFile(TMP .. "/" .. path, "---\n" .. front .. "\n---\n\n" .. body .. "\n")
			end
			note(
				"3d/lessons/old-bevel.md",
				'kind: lesson\narea: 3d\ndate: 2026-10-01\nby: t\nlinks: ["[[3d/index]]"]',
				"Bevel hero edges only."
			)
			note(
				"3d/lessons/new-bevel.md",
				'kind: lesson\narea: 3d\ndate: 2026-10-10\nby: t\nlinks: ["[[3d/index]]"]',
				"Bevel every edge; the glock widget showed why."
			)
			note(
				"3d/verdicts/glock-widget--2026-10-09.md",
				'kind: verdict\narea: 3d\nname: glock widget\nscore: 5\ndate: 2026-10-09\nsource: owner\nlinks: ["[[3d/index]]"]',
				"ok"
			)
			note(
				"3d/verdicts/glock-widget--2026-10-12.md",
				'kind: verdict\narea: 3d\nname: glock widget\nscore: 8\ndate: 2026-10-12\nsource: owner\nlinks: ["[[3d/index]]"]',
				"better"
			)
			fs.writeFile(
				TMP .. "/3d/distil.md",
				"# 3D rules\n\n## 2026-10-01 — old\n\n1. an old rule\n\n## 2026-10-15 — new\n\n1. measure first\n2. texture before detail\n"
			)
		end
		test.case("a superseded lesson leaves kit lessons; both notes carry their side of the link", function()
			build()
			withRoot(TMP, function()
				check.equal(#Vault.lessons("3d"), 2)
				local ok, msg = Vault.supersede("3d/lessons/new-bevel", "old-bevel", "every edge now")
				check.truthy(ok)
				check.truthy(string.find(msg, "supersedes", 1, true))
				local lines = Vault.lessons("3d")
				check.equal(#lines, 1)
				check.truthy(string.find(lines[1], "Bevel every edge", 1, true))
				local old = Vault.findNote("3d/lessons/old-bevel")
				check.truthy(old and string.find(tostring(old.front.superseded_by), "new-bevel", 1, true))
				check.equal(#Vault.check(), 0) -- the new link fields resolve
				local bad = Vault.supersede("3d/lessons/new-bevel", "3d/lessons/new-bevel")
				check.falsy(bad)
			end)
			fs.removeDir(TMP)
		end)
		test.case("related finds the hub, the same piece judged again, and lessons naming the piece", function()
			build()
			withRoot(TMP, function()
				local list, err = Vault.related("3d/verdicts/glock-widget--2026-10-09", 1)
				check.equal(err, nil)
				local rels = {}
				for _, r in list do
					rels[r.rel] = true
				end
				check.truthy(rels["3d/index"])
				check.truthy(rels["3d/verdicts/glock-widget--2026-10-12"])
				check.truthy(rels["3d/lessons/new-bevel"])
				check.falsy(rels["3d/lessons/old-bevel"])
				local _, missing = Vault.related("no-such-note")
				check.truthy(missing ~= nil)
			end)
			fs.removeDir(TMP)
		end)
		test.case("the page carries the LATEST distilled rules only", function()
			build()
			withRoot(TMP, function()
				local page = Vault.page("3d", 1e9)
				check.truthy(string.find(page, "RULES (distilled 2026-10-15", 1, true))
				check.truthy(string.find(page, "texture before detail", 1, true))
				check.falsy(string.find(page, "an old rule", 1, true))
			end)
			fs.removeDir(TMP)
		end)
	end)
end

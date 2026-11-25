-- answers.spec.luau (kit) — a lane answers its lessons before it builds (2026-11-08, sprint 3: the world pilot of the
-- 3D study's lesson gate): the sheet lists the lessons ranked for the piece with the first ones to answer, check() names
-- what is missing (an unanswered lesson, a thin answer, a typo'd id), and the applied ones are recorded on the piece as
-- named citations once - checking the same answers again adds nothing.
local fs = require("@lune/fs")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Answers = require("../../lib/answers")
local Vault = require("../../lib/vault")

local TMP = "kit/selftest/vault/_tmp_answers"

local function withVault(body: () -> ())
	if fs.isDir(TMP) then
		fs.removeDir(TMP)
	end
	fs.writeDir(TMP .. "/world/lessons")
	fs.writeFile(
		`{TMP}/world/lessons/rivers.md`,
		"---\nkind: lesson\narea: world\ndate: 2026-10-14\n---\n\nRiver valley terrain reads as real when the rivers carve the valley before any dressing.\n"
	)
	fs.writeFile(
		`{TMP}/world/lessons/lamps.md`,
		"---\nkind: lesson\narea: world\ndate: 2026-10-28\n---\n\nStreet lamps: one per corner, never a lamp on every wall.\n"
	)
	local savedRoot, savedCites = Vault.ROOT, Vault.CITATIONS
	Vault.ROOT = TMP
	Vault.CITATIONS = TMP .. "/citations.json"
	local ok, err = pcall(body)
	Vault.ROOT, Vault.CITATIONS = savedRoot, savedCites
	fs.removeDir(TMP)
	if not ok then
		error(err)
	end
end

local function idOf(file: string): string
	for _, n in Vault.notes("world", "lessons") do
		if string.find(n.rel, file, 1, true) then
			return Vault.lessonId(n)
		end
	end
	error("no lesson " .. file)
end

return function()
	test.suite("answers: a piece made a new way answers its lessons again (card b6m2)", function()
		test.case("a rerouted sheet: its earlier answers never count, and one copied from them is refused", function()
			withVault(function()
				local r = idOf("rivers")
				local said = "the valleys are carved by the river painter before any dressing"
				local text =
					`## Lessons applied\n\n<!-- ANSWER {r}: rivers -->\n\n- {r}: <answer>\n\n## Earlier answers (route: none, before 2026-11-10)\n\n- {r}: {said}\n`
				local open = Answers.check(text, "world")
				check.truthy(
					string.find(table.concat(open.problems, "\n"), `{r} needs how this piece applies it`, 1, true)
				)
				local copied = Answers.check((string.gsub(text, "<answer>", said, 1)), "world")
				check.truthy(
					string.find(
						table.concat(copied.problems, "\n"),
						"repeats its answer for the earlier route",
						1,
						true
					)
				)
				local fresh = Answers.check(
					(
						string.gsub(
							text,
							"<answer>",
							"the new terrain route carves its rivers first, then the valley floor",
							1
						)
					),
					"world"
				)
				check.equal(#fresh.problems, 0)
				check.equal(fresh.applied[1], r)
			end)
		end)

		test.case("the record keeps the route its answers are written for", function()
			withVault(function()
				local saved = Answers.RECORD
				Answers.RECORD = TMP .. "/answers.json"
				local ok, err = pcall(function()
					local path = TMP .. "/RiverValley.lessons.md"
					Answers.start(path, "world", "RiverValley", { idOf("rivers") }, { "terrain" })
					local e: any = Answers.entry(path)
					check.equal(e.route[1], "terrain")
				end)
				Answers.RECORD = saved
				if not ok then
					error(err)
				end
			end)
		end)

		test.case("a route's own words rank its lessons in", function()
			withVault(function()
				local _, _, none = Answers.sheet("world", "Zzqx", "cmd")
				check.equal(#none, 0)
				local _, _, must =
					Answers.sheet("world", "Zzqx", "cmd", nil, "terrain heightmap ridges rivers erosion valley")
				check.equal(must[1], idOf("rivers"))
			end)
		end)
	end)

	test.suite("answers: the lessons answered before building", function()
		test.case("the sheet ranks the piece's lessons and asks for the first ones, the best match first", function()
			withVault(function()
				local text, ids = Answers.sheet("world", "RiverValley", "lune run kit world lessons RiverValley")
				check.equal(ids[1], idOf("rivers"))
				check.truthy(string.find(text, `<!-- ANSWER {idOf("rivers")}`, 1, true))
				check.truthy(string.find(text, `- {idOf("rivers")}: <answer>`, 1, true))
				check.truthy(string.find(text, "## Lessons applied", 1, true))
			end)
		end)

		test.case("an unanswered lesson, a thin answer or an unknown id is named; good answers pass", function()
			withVault(function()
				local r, l = idOf("rivers"), idOf("lamps")
				local head = `<!-- ANSWER {r}: rivers -->\n<!-- ANSWER {l}: lamps -->\n`
				local open = Answers.check(head .. `- {r}: <answer>\n`, "world")
				check.equal(#open.problems, 2) -- r still the placeholder, l missing
				local thin = Answers.check(head .. `- {r}: yes we did\n- skip {l}: no lamps\n`, "world")
				check.equal(#thin.problems, 2)
				local typo =
					Answers.check(head .. "- L-world-ffffff: this lesson id does not exist anywhere\n", "world")
				check.truthy(string.find(table.concat(typo.problems, "\n"), "no live world lesson", 1, true))
				local good = Answers.check(
					head
						.. `- {r}: the valleys are carved by the river painter before any dressing\n- skip {l}: this canyon world has no streets and no lamps at all\n`,
					"world"
				)
				check.equal(#good.problems, 0)
				check.equal(good.applied[1], r)
				check.equal(good.skipped[1], l)
			end)
		end)

		test.case("the applied lessons are recorded on the piece once, as named citations", function()
			withVault(function()
				local r = idOf("rivers")
				check.truthy(Answers.record("world", "RiverValley", { r }))
				check.falsy(Answers.record("world", "RiverValley", { r })) -- the same answers checked again
				local cites = Vault.citations()
				check.equal(#cites, 1)
				check.equal(cites[1].dept, "world")
				check.falsy(cites[1].served) -- named: full weight when the owner's verdict comes
				local named = Vault.creditedOn("world", "RiverValley")
				check.equal(#named, 0) -- no verdict yet: nothing credited
			end)
		end)

		test.case("a lesson to answer shares two of the piece's words; recency alone lists nothing", function()
			withVault(function()
				local _, ids, must = Answers.sheet("world", "RiverValley", "cmd")
				check.equal(#must, 1)
				check.equal(must[1], idOf("rivers"))
				check.equal(#ids, 1) -- the lamps share no word: not listed at all
				local text, none, noMust = Answers.sheet("world", "Zzqx", "cmd")
				check.equal(#none, 0)
				check.equal(#noMust, 0)
				check.truthy(string.find(text, "- none: <why", 1, true))
			end)
		end)

		test.case("deleting the ANSWER comment drops no lesson: the record keeps what was asked", function()
			withVault(function()
				local saved = Answers.RECORD
				Answers.RECORD = TMP .. "/answers.json"
				local ok, err = pcall(function()
					local r = idOf("rivers")
					local path = TMP .. "/RiverValley.lessons.md"
					Answers.start(path, "world", "RiverValley", { r })
					local stripped =
						"## Lessons applied\n\n- none: this valley world has nothing the lessons talk about\n"
					check.equal(#Answers.check(stripped, "world").problems, 0) -- the sheet alone would pass
					local held = Answers.check(stripped, "world", path)
					check.truthy(string.find(table.concat(held.problems, "\n"), `{r} is not answered yet`, 1, true))
				end)
				Answers.RECORD = saved
				if not ok then
					error(err)
				end
			end)
		end)

		test.case("a flagged lesson cannot be applied, only skipped with why", function()
			withVault(function()
				local r = idOf("rivers")
				local savedCounts = Vault.lessonCounts
				Vault.lessonCounts = function()
					return { [r] = { cites = 3, helpful = 0, harmful = 3, flagged = true } }
				end :: any
				local ok, err = pcall(function()
					local text =
						`<!-- ANSWER {r}: rivers -->\n- {r}: the valleys are carved by the river painter first\n`
					local res = Answers.check(text, "world")
					check.truthy(string.find(table.concat(res.problems, "\n"), `{r} is flagged`, 1, true))
					check.equal(#res.problems, 1)
					local skip = Answers.check(
						`<!-- ANSWER {r}: rivers -->\n- skip {r}: the owner rejected every world built this way\n`,
						"world"
					)
					check.equal(#skip.problems, 0)
				end)
				Vault.lessonCounts = savedCounts
				if not ok then
					error(err)
				end
			end)
		end)

		test.case("the record keeps the digest of the text that passed, written once", function()
			withVault(function()
				local saved = Answers.RECORD
				Answers.RECORD = TMP .. "/answers.json"
				local ok, err = pcall(function()
					local r = idOf("rivers")
					local path = TMP .. "/RiverValley.lessons.md"
					local text =
						`<!-- ANSWER {r}: rivers -->\n- {r}: the valleys are carved by the river painter first\n`
					local res = Answers.check(text, "world", path)
					check.equal(#res.problems, 0)
					Answers.passed(path, "world", "RiverValley", text, res)
					local e = Answers.entry(path) or {}
					check.equal(e.answered, Vault.digest(text))
					check.equal(e.must[1], r)
					local before = fs.readFile(Answers.RECORD :: string)
					Answers.passed(path, "world", "RiverValley", text, res)
					check.equal(fs.readFile(Answers.RECORD :: string), before)
					-- the digest is the one kit/world/plan.py computes (test_world_lessons.py pins the same values)
					check.equal(Vault.digest("abc\n"), "7c93edf5")
					check.equal(Vault.digest("a\r\nb"), Vault.digest("a\nb"))
					check.equal(Vault.digest("café ✓\n"), "3abb63b6")
				end)
				Answers.RECORD = saved
				if not ok then
					error(err)
				end
			end)
		end)

		test.case("'- None:' counts as none; an unanswered lesson is named with its gist", function()
			withVault(function()
				check.equal(
					#Answers.check("- None: this valley world has nothing the lessons talk about\n", "world").problems,
					0
				)
				local r = idOf("rivers")
				local res = Answers.check(`<!-- ANSWER {r}: rivers -->\n`, "world")
				check.truthy(string.find(res.problems[1] or "", "rivers carve the valley", 1, true))
			end)
		end)
	end)
end

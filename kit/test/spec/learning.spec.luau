-- learning.spec.luau (kit) — enforced learning, rule 1 (board/plans/archive/2026-11-09-enforced-learning-plan.md): every owner
-- verdict written since the rule's rollout owes its lane what it taught (the lessons it gave, or why it taught nothing
-- new); words with neither a number nor a direction owe nothing, an older verdict is grandfathered, a guessed verdict
-- is no owner's, and paying it (lesson ids, or "none - why" in at least LEARN_WHY_WORDS words) clears it.
local fs = require("@lune/fs")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Vault = require("../../lib/vault")

local TMP = "kit/selftest/vault/_tmp_learning"

local function verdict(file: string, front: string)
	fs.writeFile(
		`{TMP}/3d/verdicts/{file}.md`,
		`---\nkind: verdict\narea: 3d\n{front}---\n\nthe owner's words for {file}\n`
	)
end

local function withVault(body: () -> ())
	if fs.isDir(TMP) then
		fs.removeDir(TMP)
	end
	fs.writeDir(TMP .. "/3d/verdicts")
	fs.writeDir(TMP .. "/3d/lessons")
	local after, before = Vault.LEARN_FROM + 60, Vault.LEARN_FROM - 60
	verdict("owed--2026-11-10", `name: owed\nscore: 4\ndate: 2026-11-10\nsource: owner\ntime: {after}\n`)
	verdict("keep--2026-11-10", `name: keep\ndirection: keep\ndate: 2026-11-10\nsource: owner\ntime: {after + 1}\n`)
	verdict("words--2026-11-10", `name: words\ndate: 2026-11-10\nsource: owner\ntime: {after + 2}\n`)
	verdict("old--2026-11-09", `name: old\nscore: 2\ndate: 2026-11-09\nsource: owner\ntime: {before}\n`)
	verdict(
		"paid--2026-11-10",
		`name: paid\nscore: 9\ndate: 2026-11-10\nsource: owner\ntime: {after + 3}\nlearned: [L-3d-000001]\n`
	)
	verdict("guess--2026-11-10", `name: guess\nscore: 6\ndate: 2026-11-10\nsource: inferred\ntime: {after + 4}\n`)
	local savedRoot = Vault.ROOT
	Vault.ROOT = TMP
	local ok, err = pcall(body)
	Vault.ROOT = savedRoot
	fs.removeDir(TMP)
	if not ok then
		error(err)
	end
end

local function names(list: { Vault.Note }): string
	local out = {}
	for _, v in list do
		table.insert(out, tostring(v.front.name))
	end
	table.sort(out)
	return table.concat(out, ",")
end

return function()
	test.suite("enforced learning: every owner verdict owes its lesson", function()
		test.case(
			"a scored or kept verdict since the rollout owes; words, old, paid and guessed ones do not",
			function()
				withVault(function()
					check.equal(names(Vault.owedLearning("3d")), "keep,owed")
					local lines = Vault.owedLines("3d")
					check.equal(#lines, 2)
					check.truthy(string.find(table.concat(lines, "\n"), "owed 4/10", 1, true))
					check.truthy(string.find(table.concat(lines, "\n"), "keep keep", 1, true))
					check.equal(#Vault.owedLearning("vfx"), 0)
				end)
			end
		)
		test.case("paying with a reason needs its words; paying with ids keeps them once", function()
			withVault(function()
				local owed = Vault.owedLearning("3d")
				local target: Vault.Note? = nil
				for _, v in owed do
					if v.front.name == "owed" then
						target = v
					end
				end
				assert(target, "the owed verdict")
				local ok, err = Vault.markLearned(target, nil, "nothing new here")
				check.falsy(ok)
				check.truthy(string.find(err or "", "at least", 1, true))
				ok = Vault.markLearned(target, nil, "it repeated what the last verdict on this piece already taught")
				check.truthy(ok)
				check.equal(names(Vault.owedLearning("3d")), "keep")
				local front = Vault.parse(fs.readFile(target.path))
				assert(front, "the paid note parses")
				check.equal(string.sub(tostring(front.learned), 1, 7), "none - ")
				-- ids: added once, the note keeps them as a list
				local keep = Vault.owedLearning("3d")[1]
				check.truthy(Vault.markLearned(keep, { "L-3d-0000aa", "L-3d-0000aa" }, nil))
				local kf = Vault.parse(fs.readFile(keep.path))
				assert(kf, "the kept note parses")
				check.equal(#(kf.learned :: { string }), 1)
				check.equal(#Vault.owedLearning("3d"), 0)
				check.equal(#Vault.owedLines("3d"), 0)
			end)
		end)
		test.case("a distil that finds no new rule still closes its window, and says why", function()
			withVault(function()
				-- ten owner verdicts before today: the lane is twice past its distil (kit handoff refuses at 10)
				for i = 1, 10 do
					verdict(`p{i}--2026-11-08`, `name: p{i}\nscore: 7\ndate: 2026-11-08\nsource: owner\ntime: 100\n`)
				end
				local due = Vault.distilDue("3d")
				check.truthy(due ~= nil and due >= 2 * Vault.DISTIL_EVERY)
				local path = Vault.writeDistil(
					"3d",
					{},
					Vault.distil("3d"),
					"spec",
					"the verdicts confirm the live rules about clean finishes"
				)
				check.equal(Vault.distilDue("3d"), nil)
				local text = fs.readFile(path)
				check.truthy(string.find(text, "· no new rule", 1, true))
				check.truthy(string.find(text, "No new rule: the verdicts confirm", 1, true))
			end)
		end)
		test.case("a verdict shown without the session's look owes it; looking (or why not) pays it", function()
			withVault(function()
				local t = Vault.LEARN_FROM + 120
				verdict(
					"unseen--2026-11-10",
					`name: unseen\nscore: 8\ndate: 2026-11-10\nsource: owner\ntime: {t}\nlook: missing\nlearned: [L-3d-0000bb]\n`
				)
				verdict(
					"seen--2026-11-10",
					`name: seen\nscore: 8\ndate: 2026-11-10\nsource: owner\ntime: {t + 1}\nlook: seen\nlearned: [L-3d-0000cc]\n`
				)
				check.equal(names(Vault.owedLook("3d")), "unseen")
				local text = table.concat(Vault.owedLines("3d"), "\n")
				check.truthy(string.find(text, "shown without the session's own look", 1, true))
				check.truthy(string.find(text, "kit verdict looked asset unseen", 1, true))
				local v = Vault.owedLook("3d")[1]
				local ok = Vault.markLooked(v, "too short")
				check.falsy(ok)
				check.truthy(Vault.markLooked(v, nil))
				check.equal(#Vault.owedLook("3d"), 0)
				local front = Vault.parse(fs.readFile(v.path))
				assert(front, "the looked note parses")
				check.equal(front.looked, Vault.today())
			end)
		end)
		test.case(
			"a note with no written time is grandfathered, whatever its file's time; filler is no reason",
			function()
				withVault(function()
					-- (a clone, a sync or a checkout rewrites an old note's file: only the time the kit wrote counts)
					verdict("notime--2026-11-10", "name: notime\nscore: 5\ndate: 2026-11-10\nsource: owner\n")
					check.equal(names(Vault.owedLearning("3d")), "keep,owed")
					check.falsy(Vault.reasonOk("x x x x x x"))
					check.falsy(Vault.reasonOk("it it it it it it"))
					check.truthy(Vault.reasonOk("the verdict repeats what the last lesson already said"))
					local v = Vault.owedLearning("3d")[1]
					local ok = Vault.markLearned(v, nil, "x x x x x x")
					check.falsy(ok)
				end)
			end
		)
		test.case("a hand-written lessons sheet does not pass until kit answer has ranked and checked it", function()
			local LaneLocks = require("../../lib/lanelocks")
			local Answers = require("../../lib/answers")
			local root = "kit/selftest/vault/_tmp_learning_sheet/"
			if fs.isDir(root) then
				fs.removeDir(root)
			end
			fs.writeDir(root .. "assets/effects")
			fs.writeFile(root .. "assets/effects/handmade.json", '{ "name": "handmade" }\n')
			local sheet = root .. "assets/effects/handmade.lessons.md"
			local text =
				"# handmade\n\n## Lessons applied\n\n- none: no lesson of this lane applies to this test piece\n"
			fs.writeFile(sheet, text)
			local savedRecord = Answers.RECORD
			Answers.RECORD = root .. "answers.json"
			local ok, err = pcall(function()
				local first = LaneLocks.lessons("vfx", root)
				check.equal(#first, 1)
				check.truthy(string.find(first[1], "not made by kit answer", 1, true))
				-- ranked (the record holds its lessons to answer) and checked as it reads now: it passes
				Answers.start(sheet, "vfx", "handmade", {})
				local r = Answers.check(text, "vfx", sheet)
				check.equal(#r.problems, 0)
				check.truthy(string.find(LaneLocks.lessons("vfx", root)[1] or "", "never checked", 1, true))
				Answers.passed(sheet, "vfx", "handmade", text, r)
				check.equal(#LaneLocks.lessons("vfx", root), 0)
			end)
			Answers.RECORD = savedRecord
			fs.removeDir(root)
			if not ok then
				error(err)
			end
		end)
		test.case("nothing to pay with is refused", function()
			withVault(function()
				local v = Vault.owedLearning("3d")[1]
				local ok, err = Vault.markLearned(v, {}, nil)
				check.falsy(ok)
				check.truthy(string.find(err or "", "lesson ids", 1, true))
			end)
		end)
	end)
end

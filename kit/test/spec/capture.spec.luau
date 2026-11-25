-- capture.spec.luau (kit) — what the owner says is captured, and the owner's own numbers are told apart from guesses
-- (2026-11-08, the owner: "Yes, start"): a Keep / Redo is a direction without a number (never averaged, never golden
-- or graveyard) that still credits or blames the lessons on the piece; the trend's mean, last 7 days and best are
-- the owner's own numbers, guesses counted apart; a verdict can carry what the owner looked at.
local fs = require("@lune/fs")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Board = require("../../lib/board")
local Vault = require("../../lib/vault")

local TMP = "kit/selftest/vault/_tmp_capture"

local function withVault(body: () -> ())
	if fs.isDir(TMP) then
		fs.removeDir(TMP)
	end
	fs.writeDir(TMP .. "/3d/lessons")
	fs.writeDir(TMP .. "/3d/verdicts")
	fs.writeFile(
		`{TMP}/3d/lessons/gunmetal.md`,
		"---\nkind: lesson\narea: 3d\ndate: 2026-10-10\nstages: [surface]\n---\n\nGunmetal slide finish: a value step from the frame.\n"
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

local function lessonId(): string
	for _, n in Vault.notes("3d", "lessons") do
		return Vault.lessonId(n)
	end
	error("no lesson")
end

return function()
	test.suite("capture: Keep / Redo is a direction without a number", function()
		test.case("polarity reads a number or a direction, and nothing else", function()
			check.equal(Vault.polarity({ score = 8 }), 1)
			check.equal(Vault.polarity({ score = 5 }), 0)
			check.equal(Vault.polarity({ score = 2 }), -1)
			check.equal(Vault.polarity({ direction = "keep" }), 1)
			check.equal(Vault.polarity({ direction = "redo" }), -1)
			check.equal(Vault.polarity({ direction = "maybe" }), nil)
			check.equal(Vault.polarity({}), nil)
		end)

		test.case("a Keep or a Redo is recorded with no number and no golden or graveyard row", function()
			withVault(function()
				local keep =
					Vault.record({ kind = "asset", name = "lamp", direction = "keep", words = "Good, keep going" })
				check.truthy(keep)
				local redo =
					Vault.record({ kind = "asset", name = "crate", direction = "redo", words = "colour is off" })
				check.truthy(redo)
				local notes = Vault.verdicts("3d")
				check.equal(#notes, 2)
				for _, n in notes do
					check.equal(n.front.score, nil)
					check.truthy(Vault.direction(n.front))
				end
				check.falsy(fs.isFile(TMP .. "/3d/golden.md"))
				check.falsy(fs.isFile(TMP .. "/3d/graveyard.md"))
			end)
		end)

		test.case("a number and a direction together, or a direction other than keep / redo, is refused", function()
			withVault(function()
				local p1, e1 = Vault.record({ kind = "asset", name = "x", score = 8, direction = "keep", words = "w" })
				check.falsy(p1)
				check.truthy(string.find(e1 :: string, "not both", 1, true))
				local p2, e2 = Vault.record({ kind = "asset", name = "x", direction = "meh", words = "w" })
				check.falsy(p2)
				check.truthy(string.find(e2 :: string, "keep or redo", 1, true))
			end)
		end)

		test.case("a Keep credits the lessons shown for the piece; a Redo blames the ones named", function()
			withVault(function()
				local id = lessonId()
				Vault.serve("asset", "lamp", { id }, "t")
				Vault.record({ kind = "asset", name = "lamp", direction = "keep", words = "Keep" })
				Vault.cite("asset", "crate", { id }, "t")
				Vault.record({ kind = "asset", name = "crate", direction = "redo", words = "Redo" })
				local c = Vault.lessonCounts()[id]
				check.equal(c.servedHelpful, 1)
				check.equal(c.harmful, 1)
				local named, served = Vault.creditedOn("asset", "crate")
				check.equal(#named, 1)
				check.equal(#served, 0)
			end)
		end)
	end)

	test.suite("capture: an ask finds its lane and, when it judges work, the lane's vault", function()
		test.case("a lane is read from the words; a tie or no lane word stays unrouted", function()
			check.equal((Board.guessArea("the city looks horrible, buildings you cannot climb")), "world")
			check.equal((Board.guessArea("Sword animations: I never see the full swing")), "anim")
			check.equal((Board.guessArea("when I spam M1 the camera locks on")), "code")
			check.equal((Board.guessArea("fix the fitting for boots and pants")), "3d")
			check.equal((Board.guessArea("the settings menu please")), "ui")
			-- a short token stands alone: "build" is no UI word, "m10" no M1
			check.equal((Board.guessArea("build the m10 thing")), nil)
			check.equal((Board.guessArea("make it nicer")), nil)
			check.equal((Board.guessArea("the slash sound")), nil) -- anim 1, sfx 1: a tie stays unrouted
		end)

		test.case("judging words tell a verdict from a request", function()
			check.truthy(Board.judgesWork("the city looks horrible"))
			check.truthy(Board.judgesWork("the menu bullets I like alot but they have a weird shadow"))
			check.truthy(Board.judgesWork("it doesnt look like a genuine open world"))
			check.truthy(Board.judgesWork("pieces just glitching out"))
			check.falsy(Board.judgesWork("updating the settings menu please"))
			check.falsy(Board.judgesWork("the auto-lock shouldn't be the case")) -- a bug report, not a verdict
		end)

		test.case("a word inside another word is no match (the 2026-11-08 review)", function()
			check.falsy(Board.judgesWork("add flame trails"))
			check.falsy(Board.judgesWork("a dumbbell prop"))
			check.equal((Board.guessArea("write the description")), nil)
			check.equal((Board.guessArea("a restaurant interior")), nil)
			check.equal((Board.guessArea("firearms on the wall")), nil)
			check.equal((Board.guessArea("what is the purpose")), nil)
			-- a plural or -es ending still counts
			check.equal((Board.guessArea("the buildings and the houses")), "world")
			check.equal((Board.guessArea("more slashes")), "anim")
		end)

		test.case("a card's whole words come from its goal, not its 110-character title", function()
			local long = string.rep("the sword animations look weird and I never see the full swing ", 3)
			local t = Board.loose("ask", long, "anim", nil)
			check.truthy(#t.title <= 110)
			local whole = string.gsub(string.gsub(long, "%s+", " "), "^ ", "")
			check.equal(Board.looseText(t), whole)
			check.truthy(#Board.looseText(t) > 110)
			local u = Board.loose("unsure", "the hilt may be 10% too long", "3d", "abcd")
			check.equal(Board.looseText(u), "the hilt may be 10% too long")
		end)

		test.case("a card id is not words; a judging ask is filed once in its lane's vault, with no number", function()
			local tmp = ".verify/_capture_spec_board"
			if fs.isDir(tmp) then
				fs.removeDir(tmp)
			end
			fs.writeDir(tmp .. "/tasks")
			local savedDir = Board.dir
			Board.dir = function(sub: string?): string
				return if sub then `{tmp}/{sub}` else tmp
			end
			local ok, err = pcall(function()
				local t = Board.loose("ask", "the city looks horrible", "world", nil)
				t.file = Board.dir("tasks") .. `/{t.id}-x.md`
				Board.save(t)
				check.equal(Board.bareId(t.id), t.id)
				check.equal(Board.bareId(` {t.id} `), t.id)
				check.equal(Board.bareId("zzzz"), nil) -- four letters, but no such card
				check.equal(Board.bareId(`{t.id} is wrong`), nil)
				withVault(function()
					fs.writeDir(TMP .. "/world/verdicts")
					local path = Vault.fileAsk("world", t.id, "the city looks horrible", "2026-10-30")
					check.truthy(path)
					check.equal(Vault.fileAsk("world", t.id, "the city looks horrible", "2026-10-30"), nil) -- once
					local n = Vault.verdicts("world")[1]
					check.equal(n.front.name, `ask-{t.id}`)
					check.equal(n.front.score, nil)
					check.equal(Vault.polarity(n.front), nil) -- words: never averaged, never credits a lesson
					check.truthy(Vault.ownersOwn(n.front))
					check.equal(Vault.fileAsk("design", t.id, "x", nil), nil) -- no vault for that area
				end)
			end)
			Board.dir = savedDir
			fs.removeDir(tmp)
			if not ok then
				error(err)
			end
		end)
	end)

	test.suite("capture: the owner's own numbers, guesses apart", function()
		test.case("the trend's mean is the owner's numbers only; guesses, Keep / Redo and words are counted", function()
			withVault(function()
				Vault.record({ kind = "asset", name = "a", score = 2, words = "bad", route = "typed shells" })
				Vault.record({ kind = "asset", name = "b", score = 4, words = "meh" })
				Vault.record({ kind = "asset", name = "c", score = 9, words = "read from a handoff", inferred = true })
				Vault.record({ kind = "asset", name = "d", direction = "keep", words = "Keep" })
				Vault.record({ kind = "asset", name = "e", direction = "redo", words = "Redo" })
				-- a GUESSED Keep is never the owner's Keep
				Vault.record({ kind = "asset", name = "f", direction = "keep", words = "seems fine", inferred = true })
				local line = Vault.trend("3d")[1]
				check.truthy(string.find(line, "1 guessed with no number", 1, true))
				check.equal(Vault.said({ direction = "redo" }), "Redo")
				check.equal(Vault.said({ score = 7.5 }), "7.5/10")
				check.truthy(
					string.find(line, "6 verdict(s), 3 scored (2 the owner's own, 1 guessed from their words", 1, true)
				)
				check.truthy(string.find(line, "1 Keep / 1 Redo", 1, true))
				check.truthy(string.find(line, "mean 3.0 (guessed 9.0)", 1, true))
				-- the best piece is the owner's own best, never the guessed 9
				check.truthy(string.find(line, "best: b 4.0", 1, true))
			end)
		end)

		test.case("a rejection a lesson already covered is counted once, the owner's own only", function()
			withVault(function()
				-- the gunmetal lesson (2026-10-10) shares its words with a later rejection
				Vault.record({
					kind = "asset",
					name = "pistol",
					score = 2,
					words = "the gunmetal slide finish has no value step from the frame",
					date = "2026-10-20",
				})
				-- the same quote filed on a second piece counts once
				Vault.record({
					kind = "asset",
					name = "pistol2",
					score = 2,
					words = "the gunmetal slide finish has no value step from the frame",
					date = "2026-10-20",
				})
				-- a guessed number is never the owner rejecting; a rejection no lesson covered
				Vault.record({ kind = "asset", name = "x", score = 1, words = "gunmetal slide value", inferred = true })
				Vault.record({
					kind = "asset",
					name = "crate",
					direction = "redo",
					words = "the planks warp",
					date = "2026-10-21",
				})
				local c = Vault.covered("3d")
				check.equal(c.low, 2)
				check.equal(c.covered, 1)
				check.truthy(string.find(Vault.learningClause("3d"), "covered 1 of 2 rejection(s)", 1, true))
			end)
		end)

		test.case("a verdict can say what the owner judged (a vault path, not a note link)", function()
			withVault(function()
				local path = Vault.record({
					kind = "asset",
					name = "lamp",
					score = 8,
					words = "lovely",
					judged = "3d/judged/0123456789abcdef.jpg",
					judgedFrom = "build/renders/lamp.png",
				})
				local text = fs.readFile(path :: string)
				local front = Vault.verdicts("3d")[1].front
				check.equal(front.judged, "3d/judged/0123456789abcdef.jpg")
				check.equal(front.judged_from, "build/renders/lamp.png")
				check.truthy(
					string.find(
						text,
						"What the owner judged: kit/knowledge/vault/3d/judged/0123456789abcdef.jpg",
						1,
						true
					)
				)
				check.falsy(string.find(text, "[[3d/judged", 1, true))
			end)
		end)
	end)
end

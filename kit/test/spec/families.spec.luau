-- families.spec.luau (kit) — family playbooks (2026-11-08, sprint 5: proposal 12): a lesson's family is its own field,
-- else its words (two DIFFERENT words of one family, a clear winner); a piece's family is its own field, else its name,
-- else its brief; ranking lifts the piece's family, lowers another family of the lane and leaves a general lesson alone;
-- the playbook lists a family's lessons.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Families = require("../../lib/families")
local Vault = require("../../lib/vault")

local TMP = "kit/selftest/vault/_tmp_families"

local function lesson(file: string, body: string, extra: string?)
	fs.writeFile(
		`{TMP}/3d/lessons/{file}.md`,
		`---\nkind: lesson\narea: 3d\ndate: 2026-11-01\n{extra or ""}---\n\n{body}\n`
	)
end

local function withVault(body: () -> ())
	if fs.isDir(TMP) then
		fs.removeDir(TMP)
	end
	fs.writeDir(TMP .. "/3d/lessons")
	fs.writeFile(
		TMP .. "/families.json",
		serde.encode("json", {
			["3d"] = {
				firearm = { "pistol", "trigger", "magazine", "glock" },
				furniture = { "table", "chair", "bed", "tester" },
				container = { "cask", "keg", "jug" },
			},
		})
	)
	local savedRoot = Vault.ROOT
	Vault.ROOT = TMP
	Families.reset(TMP .. "/families.json")
	local ok, err = pcall(body)
	Vault.ROOT = savedRoot
	Families.reset()
	fs.removeDir(TMP)
	if not ok then
		error(err)
	end
end

return function()
	test.suite("families: lessons and pieces get a family, ranking prefers the piece's", function()
		test.case("a family is named by different words; one word repeated is not enough; ties stay general", function()
			withVault(function()
				check.equal(Families.ofText("3d", "the pistol trigger pulls back", 2), "firearm")
				check.equal(Families.ofText("3d", "pistol pistol pistol", 2), nil) -- one word, three times
				check.equal(Families.ofText("3d", "a pistol beside a chair", 1), nil) -- a tie
				check.equal(Families.ofText("3d", "a cask on a table beside a jug", 1), "container")
			end)
		end)

		test.case(
			"a lesson's own family wins; else its words decide; a lesson about everything stays general",
			function()
				withVault(function()
					lesson("a", "The pistol trigger and the magazine release are separate parts.")
					lesson("b", "Every board its own part.", "family: furniture\n")
					lesson("c", "Look at the hero render every iteration.")
					local fam = {}
					for _, n in Vault.notes("3d", "lessons") do
						fam[string.match(n.rel, "([^/]+)$") or n.rel] = Families.ofLesson("3d", n) or "general"
					end
					check.equal(fam["a.md"] or fam["a"], "firearm")
					check.equal(fam["b.md"] or fam["b"], "furniture")
					check.equal(fam["c.md"] or fam["c"], "general")
				end)
			end
		)

		test.case("family words keep the lessons' stop words and fold short plurals ('runs' is 'run')", function()
			withVault(function()
				check.truthy(table.find(Families.words("SwiftRuns and two guns"), "run") ~= nil)
				check.truthy(table.find(Families.words("SwiftRuns and two guns"), "gun") ~= nil)
				check.truthy(table.find(Families.words("the glass case"), "glass") ~= nil) -- "ss" stays
				local w = Families.words("DTBlade slashes punches bases boxes glasses")
				for _, want in { "blade", "slash", "punch", "base", "box", "glass" } do
					check.truthy(table.find(w, want) ~= nil)
				end
			end)
		end)

		test.case("a headline naming a family once, with a body that does not, stays general", function()
			withVault(function()
				lesson("prov", "References first, per part (the glock, 2026-10-09). Every part gets its own picture.")
				lesson(
					"deep",
					"Part masks for measuring. The pistol frame, the trigger bar and the magazine well each."
				)
				local fam = {}
				for _, n in Vault.notes("3d", "lessons") do
					fam[string.match(n.rel, "([^/]+)$") or n.rel] = Families.ofLesson("3d", n) or "general"
				end
				check.equal(fam["prov.md"] or fam["prov"], "general") -- where it was learned, not what it is about
				check.equal(fam["deep.md"] or fam["deep"], "firearm") -- three different gun words in its body
			end)
		end)

		test.case("the headline: brackets are where it was learned; a decimal point does not end it", function()
			withVault(function()
				lesson("brk", "Measure first (the pistol trigger bench, 2026-10-09). Then build.")
				lesson("dec", "A 0.5 m pistol trigger guard needs its own pass. Nothing else here.")
				local fam = {}
				for _, n in Vault.notes("3d", "lessons") do
					fam[string.match(n.rel, "([^/]+)$") or n.rel] = Families.ofLesson("3d", n) or "general"
				end
				check.equal(fam["brk.md"] or fam["brk"], "general") -- the gun words sit inside the brackets
				check.equal(fam["dec.md"] or fam["dec"], "firearm") -- "0.5" is no sentence end: pistol + trigger
			end)
		end)

		test.case("a piece's family comes from its name before its brief", function()
			withVault(function()
				check.equal(Families.ofPiece("3d", "town_tester_bed"), "furniture")
				-- a name that says nothing ("glock17": digits on the word) falls back to the piece's brief: the
				-- spec writes its own (glock17's brief is git-excluded, so a proof of the committed tree failed
				-- here - the owner's V3 list, kit hygiene)
				local brief = "assets/models/zzspec_sidearm17.brief.md"
				-- (the kit's own repo has no assets/: make the folder for the fixture, and take away only what was made)
				local madeAssets, madeModels = not fs.isDir("assets"), not fs.isDir("assets/models")
				if madeModels then
					fs.writeDir("assets/models")
				end
				fs.writeFile(brief, "# zzspec_sidearm17\n\n- what: a compact pistol, its trigger and magazine\n")
				local ok, err = pcall(function()
					check.equal(Families.ofPiece("3d", "zzspec_sidearm17"), "firearm")
				end)
				fs.removeFile(brief)
				if madeAssets then
					fs.removeDir("assets")
				elseif madeModels then
					fs.removeDir("assets/models")
				end
				if not ok then
					error(err, 0)
				end
				check.equal(Families.ofPiece("3d", "zzqx_unknown"), nil)
			end)
		end)

		test.case("ranking lifts the piece's family and lowers another; a general lesson keeps its place", function()
			withVault(function()
				lesson("gun", "Turn the barrel before it slides out: the pistol trigger group and magazine follow.")
				lesson("cask", "A barrel built from staves: the cask hoops and the keg lid are their own parts.")
				lesson("any", "A barrel needs its own parts, each measured.")
				-- the two lessons equally relevant by words (barrel + hoops, barrel + trigger): the piece's family decides
				-- (a gentle preference, +0.1 / x0.85 - never an override of relevance), a general lesson keeps its score
				local function place(family: string?): { [string]: { pos: number, score: number } }
					local out = {}
					local ranked = Vault.rank("3d", "barrel hoops trigger", { today = "2026-11-08", family = family })
					for i, r in ranked do
						for _, key in { "gun", "cask", "any" } do
							if string.find(r.note.rel, key, 1, true) then
								out[key] = { pos = i, score = r.score }
							end
						end
					end
					return out
				end
				local plainAt, asCask, asGun = place(nil), place("container"), place("firearm")
				check.truthy(asCask.cask.pos < asCask.gun.pos)
				check.truthy(asGun.gun.pos < asGun.cask.pos)
				check.equal(asGun.any.score, plainAt.any.score)
				check.equal(asCask.any.score, plainAt.any.score)
				local plain = Vault.rank("3d", "barrel parts", { today = "2026-11-08" })
				for _, r in plain do
					check.equal(r.family, nil) -- no piece family: nothing changes, nothing labelled
				end
			end)
		end)

		test.case("the playbook lists a family's lessons and every family's counts", function()
			withVault(function()
				lesson("a", "The pistol trigger and the magazine release are separate parts.")
				lesson("c", "Look at the hero render every iteration.")
				local all = table.concat(Families.playbook("3d", nil), "\n")
				check.truthy(string.find(all, "firearm: 1 lesson(s)", 1, true))
				check.truthy(string.find(all, "general (no family): 1 lesson(s)", 1, true))
				local one = table.concat(Families.playbook("3d", "firearm"), "\n")
				check.truthy(string.find(one, "3d / firearm: 1 lesson(s)", 1, true))
				check.truthy(string.find(table.concat(Families.playbook("3d", "nope"), "\n"), "no 3d family", 1, true))
			end)
		end)
	end)
end

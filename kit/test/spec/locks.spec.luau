-- locks.spec.luau (kit) — the shared rules every lane's quality lock uses (board/locks.json): only the
-- OWNER's approval counts, our own build output is never a real source, and pieces made before the locks are exempt.
local fs = require("@lune/fs")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Locks = require("../../lib/locks")

return function()
	test.suite("locks: the shared quality rules", function()
		test.case("an approval counts only when it is the OWNER's", function()
			check.truthy(Locks.isOwner({ by = "owner" }))
			check.truthy(Locks.isOwner({ by = "owner blanket approval 2026-10-16" }))
			check.truthy(Locks.isOwner({ by = "Owner" }))
			check.truthy(Locks.isOwner({ by = "  Owner blanket  " })) -- trimming
			check.falsy(Locks.isOwner({ who = "model", by = "local-coder@cli" }))
			check.falsy(Locks.isOwner({ who = "model", by = "owner" }))
			check.falsy(Locks.isOwner({ by = "model-proposed" }))
			check.falsy(Locks.isOwner({}))
			check.falsy(Locks.isOwner(nil))
			check.falsy(Locks.isOwner("owner"))
		end)

		test.case("a path in our own build output is never a real source", function()
			check.truthy(Locks.isBuildPath("build/vfx/x.png"))
			check.truthy(Locks.isBuildPath("games/OtherGame/build/vfx/refs/a.png"))
			check.truthy(Locks.isBuildPath(".\\build\\x.png"))
			check.falsy(Locks.isBuildPath("assets/effects/refs/flame_arc/f_00.png"))
			check.falsy(Locks.isBuildPath("games/SampleDojo/assets/x.png"))
		end)

		test.case("the locks file loads with both maps and paths normalize", function()
			Locks.reset()
			local data = Locks.load()
			check.truthy(type(data) == "table")
			check.truthy(type(data.grandfathered) == "table")
			check.truthy(type(data.waivers) == "table")
			check.equal(Locks.normal(".\\build\\x.png"), "build/x.png")
		end)

		test.case("a build render is caught however its path is spelled (review 2026-10-21)", function()
			check.truthy(Locks.isBuildPath("Build/x.png")) -- the same folder on Windows
			check.truthy(Locks.isBuildPath("assets/../build/x.png"))
			check.truthy(Locks.isBuildPath("../Parallax-verify/build/vfx/a.png")) -- a sandbox worktree's build
			check.truthy(Locks.isBuildPath("games/OtherGame/Build/vfx/a.png"))
			check.falsy(Locks.isBuildPath("assets/effects/refs/flame_arc/building_00.png"))
			check.equal(Locks.normal("assets/./effects/../ui/x.json"), "assets/ui/x.json")
		end)

		test.case("grandfathering ignores case, as Windows file names do", function()
			Locks.reset()
			if fs.isFile("assets/ui/RpgHud.json") then
				check.truthy(Locks.grandfathered("ui", "assets/ui/rpghud.json"))
			end
		end)

		test.case("an absolute path inside the project reads as project-relative", function()
			local process = require("@lune/process")
			check.equal(Locks.normal(process.cwd .. "/build/vfx/a.png"), "build/vfx/a.png")
			check.truthy(Locks.isBuildPath(process.cwd .. "\\games\\OtherGame\\build\\vfx\\a.png"))
		end)

		test.case("approvals and waivers count only when they are the owner's; a waiver can name its steps", function()
			local real = Locks.FILE
			local tmp = ".verify/locks-spec.json"
			fs.writeFile(
				tmp,
				[[{"grandfathered": {}, "approvals": {"vfx": {"Mine": {"by": "owner", "words": "go"},
				"Theirs": {"who": "model", "by": "owner"}}}, "waivers": {"sfx": {"Hum": {"by": "owner",
				"steps": ["refs"]}, "All": {"by": "owner blanket"}, "Fake": {"by": "model-proposed"}}}}]]
			)
			Locks.FILE = tmp
			Locks.reset()
			local ok, err = pcall(function()
				check.truthy(Locks.approval("vfx", "Mine"))
				check.falsy(Locks.approval("vfx", "Theirs"))
				check.falsy(Locks.approval("vfx", "Nobody"))
				check.falsy(Locks.approval("ui", "Mine"))
				check.truthy(Locks.waiver("sfx", "Hum", "refs"))
				check.falsy(Locks.waiver("sfx", "Hum", "verdict"))
				check.truthy(Locks.waiver("sfx", "All", "verdict"))
				check.falsy(Locks.waiver("sfx", "Fake"))
			end)
			Locks.FILE = real
			Locks.reset()
			fs.removeFile(tmp)
			if not ok then
				error(err, 0)
			end
		end)

		-- the owner, 2026-11-11: "A concept sheet we really need ... block[out] approval" - his yes to ONE stage's
		-- artefact (the model sheet, the blockout) is its own record, with the id of what he saw
		test.case(
			"a stage approval is the owner's own record for that piece and stage, with the artefact's id",
			function()
				local real = Locks.FILE
				local tmp = ".verify/locks-spec-stages.json"
				fs.writeFile(
					tmp,
					[[{"grandfathered": {"3d-stages": ["assets/models/build_old.py"]}, "stages": {"3d": {
				"sword": {"sheet": {"by": "owner", "words": "yes", "id": "abc"},
				          "blockout": {"by": "model-proposed", "words": "looks fine", "id": "b1"}},
				"gun": {"sheet": {"who": "model", "by": "owner", "id": "x"}}}}}]]
				)
				Locks.FILE = tmp
				Locks.reset()
				local ok, err = pcall(function()
					local rec = Locks.stage("3d", "sword", "sheet")
					check.truthy(rec)
					check.equal(rec.id, "abc")
					check.falsy(Locks.stage("3d", "sword", "blockout")) -- (a model's own yes is nobody's)
					check.falsy(Locks.stage("3d", "gun", "sheet"))
					check.falsy(Locks.stage("3d", "nobody", "sheet"))
					check.falsy(Locks.stage("vfx", "sword", "sheet"))
					check.falsy(Locks.approval("3d", "sword")) -- (a stage's yes is not the brief's)
					-- a piece that predates the stage approvals is exempt; a spec's own locks file is never frozen
					check.truthy(Locks.stagesExempt("assets/models/build_old.py"))
					check.truthy(Locks.stagesExempt("ASSETS\\models\\build_old.py"))
					check.falsy(Locks.stagesExempt("assets/models/build_new.py"))
				end)
				Locks.FILE = real
				Locks.reset()
				fs.removeFile(tmp)
				if not ok then
					error(err, 0)
				end
			end
		)

		-- the owner, 2026-11-13: "every method i mentioned ... enforced in the terms of being used" - the methods
		-- lock holds new pieces only: a script on its grandfathered list is exempt
		test.case("a piece that predates the methods lock is exempt, a new one is held", function()
			local real = Locks.FILE
			local tmp = ".verify/locks-spec-methods.json"
			fs.writeFile(tmp, [[{"grandfathered": {"3d-methods": ["assets/models/build_old.py"]}}]])
			Locks.FILE = tmp
			Locks.reset()
			local ok, err = pcall(function()
				check.truthy(Locks.methodsExempt("assets/models/build_old.py"))
				check.truthy(Locks.methodsExempt("ASSETS\\models\\build_old.py"))
				check.falsy(Locks.methodsExempt("assets/models/build_new.py"))
				check.falsy(Locks.load().methods_lock) -- (a spec's own locks file is never frozen)
			end)
			Locks.FILE = real
			Locks.reset()
			fs.removeFile(tmp)
			if not ok then
				error(err, 0)
			end
		end)

		-- the list is frozen ONCE, by whichever of kit new asset / kit plan / kit asset runs first; everything else
		-- in the record stays as it was
		test.case("the methods lock's list is frozen once and the other records are kept", function()
			local real = Locks.FILE
			local tmp = ".verify/locks-spec-freeze.json"
			fs.writeFile(
				tmp,
				[[{"grandfathered": {"3d-study": ["assets/models/build_old.py"]}, "approvals": {"3d": {"Hat": {"by": "owner", "words": "yes"}}}}]]
			)
			Locks.FILE = tmp
			Locks.reset()
			local ok, err = pcall(function()
				check.truthy(Locks.freezeMethods())
				Locks.reset()
				local data = Locks.load()
				check.equal(type(data.grandfathered["3d-methods"]), "table")
				check.equal(type(data.methods_lock), "string")
				check.equal(data.grandfathered["3d-study"][1], "assets/models/build_old.py")
				check.equal(data.approvals["3d"].Hat.words, "yes")
				check.falsy(Locks.freezeMethods()) -- (once: a second call changes nothing)
			end)
			Locks.FILE = real
			Locks.reset()
			fs.removeFile(tmp)
			if not ok then
				error(err, 0)
			end
		end)

		-- card 988z: the study and stage lists are frozen like the methods list (once, keeping every other record), so
		-- kit new asset can freeze all three BEFORE it writes a new piece's script
		test.case("the study and stage lists are frozen once each and the other records are kept", function()
			local real = Locks.FILE
			local tmp = ".verify/locks-spec-freeze-all.json"
			fs.writeFile(
				tmp,
				[[{"grandfathered": {"3d-methods": ["assets/models/build_old.py"]}, "approvals": {"3d": {"Hat": {"by": "owner", "words": "yes"}}}}]]
			)
			Locks.FILE = tmp
			Locks.reset()
			local ok, err = pcall(function()
				check.truthy(Locks.freezeStudy())
				check.truthy(Locks.freezeStages())
				check.falsy(Locks.freezeMethods()) -- (already frozen: kept as it was)
				Locks.reset()
				local data = Locks.load()
				check.equal(type(data.grandfathered["3d-study"]), "table")
				check.equal(type(data.grandfathered["3d-stages"]), "table")
				check.equal(type(data.study_lock), "string")
				check.equal(type(data.stages_lock), "string")
				check.equal(data.grandfathered["3d-methods"][1], "assets/models/build_old.py")
				check.equal(data.approvals["3d"].Hat.words, "yes")
				check.falsy(Locks.freezeStudy()) -- (once each)
				check.falsy(Locks.freezeStages())
				Locks.freezeAll() -- (a spec's own locks file is never frozen by it: only board/locks.json is)
			end)
			Locks.FILE = real
			Locks.reset()
			fs.removeFile(tmp)
			if not ok then
				error(err, 0)
			end
		end)

		test.case("pieces made before the locks are exempt; unknown pieces are not", function()
			Locks.reset()
			if fs.isFile("assets/ui/RpgHud.json") then
				check.truthy(Locks.grandfathered("ui", "assets/ui/RpgHud.json"))
			end
			check.falsy(Locks.grandfathered("ui", "assets/ui/NoSuchScreen.json"))
		end)

		-- the owner, 2026-11-10: "Yes, per game" - a game's unscored pieces never hold the kit home's (or another game's)
		-- next piece: the cap counts the project the piece sits in
		test.case("the verdict cap is per project: a piece's project is its games/<Name>/ or the kit home", function()
			local LaneLocks = require("../../lib/lanelocks")
			check.equal(LaneLocks.projectOf("games/SampleShowcase/assets/models/a.py"), "games/SampleShowcase/")
			check.equal(LaneLocks.projectOf(".\\games\\SampleGame\\assets\\models\\a.py"), "games/SampleGame/")
			check.equal(LaneLocks.projectOf("./assets/models/a.py"), "")
			check.equal(LaneLocks.projectOf("assets/models/a.py"), "")
		end)
	end)
end

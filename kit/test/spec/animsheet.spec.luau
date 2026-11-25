-- animsheet.spec.luau — a move's SHEET (kit anim sheet, the animation studio route's A0: its key poses large on the
-- owner's rig beside their reference frames, kit/anim/pose_sheet.py): when a sheet is fresh or stale against what it
-- was made from, and the `LOOK: <folder> ...` lines an animation build ends with (AnimCmd.buildLooks). The pictures
-- themselves are proven in kit/test/python/test_anim_pose_sheet.py.
local frk = require("../frk")
local fs = require("@lune/fs")
local serde = require("@lune/serde")
local test, check = frk.test, frk.check

local AnimCmd = require("../../cmd/anim")

local DIR = ".verify/_spec_animsheet"
local RIG = `{DIR}/rig.blend`

local function has(text: string?, part: string): boolean
	return type(text) == "string" and string.find(text, part, 1, true) ~= nil
end

return function()
	test.suite("kit anim: a move's sheet and the LOOK lines a build ends with", function()
		-- (the cases run after this body: each makes its own fixture folder; the last one puts everything back)
		local realDir, realSheet, realCap = AnimCmd.sheetDir, AnimCmd.sheet, AnimCmd.BUILD_LOOKS
		local rendered: { string } = {}
		local function fixture()
			if fs.isDir(DIR) then
				fs.removeDir(DIR)
			end
			fs.writeDir(DIR)
			fs.writeFile(RIG, "a rig")
			rendered = {}
			AnimCmd.BUILD_LOOKS = realCap;
			(AnimCmd :: any).sheetDir = function(name: string): string
				return `{DIR}/{name}.sheet`
			end
			(AnimCmd :: any).sheet = function(name: string): (boolean, any, { any })
				table.insert(rendered, name)
				if name == "Broken" then
					return false, { summary = "the rig does not reproduce the clip" }, {}
				end
				return true, { look = `LOOK: {DIR}/{name}.sheet/ - pose_sheet.png (fresh from the rig)` }, {}
			end
		end
		-- a sheet as kit/anim/pose_sheet.py leaves it: look.json with its LOOK line, the files it was made from and
		-- one hash over them
		local function sheetOf(name: string, clipText: string, extra: { [string]: any }?): string
			local clip = `{DIR}/{name}.clip.json`
			fs.writeFile(clip, clipText)
			fs.writeDir(`{DIR}/{name}.sheet`)
			local look: { [string]: any } = {
				look = `LOOK: {DIR}/{name}.sheet/ - pose_sheet.png (3 key pose(s))`,
				inputs = { clip },
				inputs_sha256 = serde.hash("sha256", clipText),
			}
			for k, v in extra or {} do
				look[k] = v
			end
			fs.writeFile(`{DIR}/{name}.sheet/look.json`, serde.encode("json", look))
			return clip
		end

		test.case("a move with no sheet has none", function()
			fixture()
			local state, line = AnimCmd.sheetState("Nope")
			check.equal(state, "none")
			check.equal(line, nil)
		end)
		test.case("a sheet is fresh while what it was made from is unchanged, and keeps its LOOK line", function()
			fixture()
			sheetOf("Cut", '{"name": "Cut"}')
			local state, line = AnimCmd.sheetState("Cut")
			check.equal(state, "fresh")
			check.truthy(has(line, "Cut.sheet/ - pose_sheet.png"))
		end)
		test.case("a changed clip makes its sheet stale; a clip that is gone too", function()
			fixture()
			local clip = sheetOf("Cut", '{"name": "Cut"}')
			fs.writeFile(clip, '{"name": "Cut", "moved": true}')
			check.equal((AnimCmd.sheetState("Cut")), "stale")
			fs.removeFile(clip)
			check.equal((AnimCmd.sheetState("Cut")), "stale")
		end)
		test.case("a sheet that does not say what it was made from is stale", function()
			fixture()
			fs.writeDir(`{DIR}/Old.sheet`)
			fs.writeFile(`{DIR}/Old.sheet/look.json`, serde.encode("json", { look = "LOOK: an older sheet" }))
			local state, line = AnimCmd.sheetState("Old")
			check.equal(state, "stale")
			check.equal(line, "LOOK: an older sheet")
		end)
		test.case("a reference frame's footage that arrives or leaves makes the sheet stale", function()
			fixture()
			local footage = `{DIR}/wind.mp4`
			sheetOf("Cut", "{}", { reference_files = { [footage] = false } })
			check.equal((AnimCmd.sheetState("Cut")), "fresh") -- (named by the dossier, not on this machine: as drawn)
			fs.writeFile(footage, "frames")
			check.equal((AnimCmd.sheetState("Cut")), "stale") -- (it arrived: the pane that said "no frame" is wrong)
			sheetOf("Cut", "{}", { reference_files = { [footage] = true } })
			check.equal((AnimCmd.sheetState("Cut")), "fresh")
			fs.removeFile(footage)
			check.equal((AnimCmd.sheetState("Cut")), "stale")
		end)
		test.case(
			"a build of every clip renders nothing: it names the stale sheets and counts the current ones",
			function()
				fixture()
				sheetOf("Fresh", "{}")
				fs.writeFile(sheetOf("Moved", "{}"), '{"changed": 1}')
				local lines = AnimCmd.buildLooks({ "Fresh", "Fresh_R15", "Moved", "Never" }, false, false, RIG)
				check.equal(#rendered, 0)
				check.equal(#lines, 2)
				check.truthy(has(lines[1], "Moved changed since its sheet was made: lune run kit anim sheet Moved"))
				check.truthy(has(lines[2], "3 clip(s) built")) -- (the _R15 twin of a clip is the same move)
				check.truthy(has(lines[2], "1 have a current sheet"))
				for _, line in lines do
					check.equal(string.sub(line, 1, 6), "LOOK: ")
				end
			end
		)
		test.case("a build that names its moves renders each changed one and says which it rendered", function()
			fixture()
			sheetOf("Fresh", "{}")
			fs.writeFile(sheetOf("Moved", "{}"), '{"changed": 1}')
			local lines = AnimCmd.buildLooks({ "Moved", "Fresh", "Never", "Never_R15" }, true, false, RIG)
			check.equal(#lines, 3)
			check.equal(table.concat(rendered, ","), "Moved,Never") -- (the unchanged one is not rendered again)
			check.truthy(has(lines[1], "[Fresh: unchanged since this sheet]"))
			check.truthy(has(lines[2], "(fresh from the rig) [Moved: rendered by this build]"))
			check.truthy(has(lines[3], "[Never: rendered by this build]"))
		end)
		test.case("a sheet that fails never fails the build: its line says why and how to make it", function()
			fixture()
			local lines = AnimCmd.buildLooks({ "Broken" }, true, false, RIG)
			check.equal(#lines, 1)
			check.truthy(has(lines[1], "NOT rendered for Broken (the rig does not reproduce the clip)"))
			check.truthy(has(lines[1], "lune run kit anim sheet Broken"))
		end)
		test.case("a build renders BUILD_LOOKS sheets by itself and names the rest", function()
			fixture()
			AnimCmd.BUILD_LOOKS = 1
			local lines = AnimCmd.buildLooks({ "A", "B" }, true, false, RIG)
			check.equal(table.concat(rendered, ","), "A")
			check.truthy(has(lines[2], "B is not rendered (this build rendered 1 sheets already)"))
		end)
		test.case("--no-look renders nothing and says the sheets are from before the build, or not made", function()
			fixture()
			sheetOf("Fresh", "{}")
			fs.writeFile(sheetOf("Moved", "{}"), '{"changed": 1}')
			local lines = AnimCmd.buildLooks({ "Fresh", "Moved", "Never" }, true, true, RIG)
			check.equal(#rendered, 0)
			check.truthy(has(lines[1], "[Fresh: unchanged since this sheet]"))
			check.truthy(has(lines[2], "Moved was built and its sheet is from BEFORE this build (--no-look)"))
			check.truthy(has(lines[3], "Never was built and its sheet is not made (--no-look)"))
		end)
		test.case("a move the owner approved no blocking of is held to nothing by the build", function()
			-- (A4, AnimCmd.keptStep: only a move with a blocking record AND a built clip is checked against the poses
			-- he approved; every move made before the stage builds exactly as it did. What the check says of a clip
			-- that drifted is proven in kit/test/python/test_anim_kept.py and by kit selftest)
			check.equal(AnimCmd.keptStep("NoSuchMoveOfTheSpec"), nil)
			check.equal(AnimCmd.keptStep("NoSuchMoveOfTheSpec", `{DIR}/none.clip.json`), nil)
		end)
		test.case("the lock reads only moves made after the rule, and stops one nobody showed the owner", function()
			-- (POSES FIRST, AnimCmd.lockPairs + blockingLock -> kit/anim/blocking.py lock: a strike move or a sword
			-- pick made after the rule is not made unless the owner's yes stands for its key poses; a move on the
			-- frozen list (assets/animations/blocks/_before_blocking.json) is never asked, so an existing project
			-- builds as before. The states are proven in kit/test/python/test_anim_blocking_lock.py; here: the
			-- build's own wiring, read only)
			local loved = "kit/selftest/anim/faults/loved/Katana1Kesa.move.json"
			local before = AnimCmd.beforeBlocking()
			local old: string? = next(before)
			local sources: { any } = {
				{ name = "NoSuchMoveOfTheSpec", move = loved },
				{ name = "NoSuchPoseOfTheSpec", pose = `{DIR}/x.pose.json` },
				{ name = "NoSuchPickOfTheSpec", dossier = `{DIR}/none.dossier.json` },
			}
			if old then -- (a project that froze its list: a move on it is never read, whatever its file)
				table.insert(sources, { name = old, move = loved })
			end
			local pairs = AnimCmd.lockPairs(sources)
			check.equal(#pairs, 2) -- (a pick with no spec names no dossier; a posed file is asked by its own file)
			check.equal(pairs[1], `NoSuchMoveOfTheSpec=move={loved}`)
			check.equal(pairs[2], `NoSuchPoseOfTheSpec=pose={DIR}/x.pose.json`)
			pairs = { pairs[1] }
			check.equal(AnimCmd.blockingLock({}), nil)
			check.equal(AnimCmd.designLock({}), nil)
			local stop = AnimCmd.blockingLock(pairs)
			check.truthy(stop ~= nil)
			if stop then
				check.truthy(has(stop.summary, "anim NoSuchMoveOfTheSpec: STOP - a NEW move"))
				check.truthy(has(stop.summary, "Poses first, motion after"))
				check.truthy(
					has(stop.next_action, `lune run kit anim block NoSuchMoveOfTheSpec --sheet --move {loved}`)
				)
			end
		end)
		test.case("a project without the owner's rig is told so in one line; and everything is put back", function()
			fixture()
			local lines = AnimCmd.buildLooks({ "A" }, true, false, `{DIR}/no_rig.blend`)
			check.equal(#lines, 1)
			check.truthy(has(lines[1], "this project has no"))
			check.equal(#rendered, 0);
			(AnimCmd :: any).sheetDir = realDir;
			(AnimCmd :: any).sheet = realSheet
			AnimCmd.BUILD_LOOKS = realCap
			fs.removeDir(DIR)
		end)
	end)
end

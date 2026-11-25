-- kickoff.spec.luau (kit) — one brief across lanes becomes one task per lane: each task carries the whole brief in the
-- owner's words and its own part, the code task waits for the animation task (moves take their frames from it), and
-- every lane's `kit start` lists its task. Runs on a throwaway board folder, never the real board.
local fs = require("@lune/fs")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Board = require("../../lib/board")
local Kickoff = require("../../cmd/kickoff")({ command = function() end })
local Start = require("../../cmd/start")({ command = function() end })

return function()
	test.suite("kickoff: one brief, one task per lane", function()
		test.case(
			"each named lane gets its task with the whole brief; code depends on anim; kit start lists it",
			function()
				local tmp = ".verify/_kickoff_spec"
				if fs.isDir(tmp) then
					fs.removeDir(tmp)
				end
				fs.writeDir(tmp)
				local savedDir = Board.dir
				Board.dir = function(sub: string?): string
					return if sub then `{tmp}/{sub}` else tmp
				end
				local ok, err = pcall(function()
					local brief = "A katana moveset: four quick slashes then a rising finisher, water on every slash"
					local ids, briefPath = Kickoff.create("KatanaMoveset", brief, {
						anim = "four slashes + a rising finisher",
						vfx = "water trails on each slash, a splash on the finisher",
						sfx = "swings and water hits",
						code = "the five moves and the combo",
					}, "p1", "spec")
					check.truthy(ids.anim and ids.vfx and ids.sfx and ids.code)
					check.equal(ids.ui, nil) -- a lane the brief did not name gets no task
					check.truthy(fs.isFile(briefPath))
					check.truthy(string.find(fs.readFile(briefPath), brief, 1, true))
					local byArea = {}
					for _, t in Board.tasks() do
						byArea[t.area] = t
					end
					for _, lane in { "anim", "vfx", "sfx", "code" } do
						local t = byArea[lane]
						check.truthy(t, lane)
						check.truthy(string.find(t.body, brief, 1, true)) -- the whole brief, in the owner's words
						check.truthy(string.find(t.body, "## Done when", 1, true))
						check.truthy(table.find(t.labels, "kickoff:KatanaMoveset"))
					end
					check.truthy(table.find(byArea.code.depends, ids.anim)) -- moves wait for the animation
					check.truthy(string.find(byArea.vfx.body, "water trails on each slash", 1, true))
					-- each lane's kit start shows its own task
					local listed = table.concat(Start.tasks("vfx", 5), "\n")
					check.truthy(string.find(listed, ids.vfx, 1, true))
				end)
				Board.dir = savedDir
				fs.removeDir(tmp)
				if not ok then
					error(err)
				end
			end
		)
	end)
end

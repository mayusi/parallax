-- failhints.spec.luau (kit) — a gate that fails shows the lessons that match its words (2026-11-08, sprint 3): the
-- failing report's lane is read from its name, its lessons ranked by the failure's words show the ones that match well,
-- a report no lane owns shows nothing, and a failure that keeps coming back asks for its lesson every third time.
local fs = require("@lune/fs")

local frk = require("../frk")
local test, check = frk.test, frk.check

local FailHints = require("../../lib/failhints")
local Vault = require("../../lib/vault")

local TMP = "kit/selftest/vault/_tmp_failhints"

local function withVault(body: () -> ())
	if fs.isDir(TMP) then
		fs.removeDir(TMP)
	end
	fs.writeDir(TMP .. "/world/lessons")
	fs.writeFile(
		`{TMP}/world/lessons/rivers.md`,
		"---\nkind: lesson\narea: world\ndate: 2026-10-14\n---\n\nTerrain that reads as real comes from rivers carving the valleys, not noise: run the river painter.\n"
	)
	fs.writeFile(
		`{TMP}/world/lessons/lamps.md`,
		"---\nkind: lesson\narea: world\ndate: 2026-10-28\n---\n\nStreet lamps: one per corner, never a lamp on every wall.\n"
	)
	local savedRoot, savedCites, savedFile = Vault.ROOT, Vault.CITATIONS, FailHints.FILE
	Vault.ROOT = TMP
	Vault.CITATIONS = TMP .. "/citations.json"
	FailHints.FILE = TMP .. "/failures.json"
	local ok, err = pcall(body)
	Vault.ROOT, Vault.CITATIONS, FailHints.FILE = savedRoot, savedCites, savedFile
	fs.removeDir(TMP)
	if not ok then
		error(err)
	end
end

return function()
	test.suite("failure hints: the lessons that match a failing gate", function()
		test.case("the lane comes from the report's name; a report no lane owns has none", function()
			check.equal(FailHints.lane("world-check"), "world")
			check.equal(FailHints.lane("asset-glock17"), "3d")
			check.equal(FailHints.lane("anim"), "anim")
			check.equal(FailHints.lane("checks"), nil)
			check.equal(FailHints.lane("verify"), nil)
		end)

		test.case("the lesson that shares the failure's words shows; the unrelated one does not", function()
			withVault(function()
				local lines = FailHints.lines(
					"world-check",
					"world check: the terrain reads like noise, no rivers in the valleys",
					""
				)
				local text = table.concat(lines, "\n")
				check.truthy(string.find(text, "lessons that match this failure (world", 1, true))
				check.truthy(string.find(text, "rivers carving the valleys", 1, true))
				check.falsy(string.find(text, "Street lamps", 1, true))
			end)
		end)

		test.case("a report no lane owns prints nothing and counts nothing", function()
			withVault(function()
				check.equal(#FailHints.lines("checks", "checks: the terrain reads like noise", ""), 0)
				check.falsy(fs.isFile(FailHints.FILE))
			end)
		end)

		test.case("the same failure, numbers aside, asks for its lesson every third time", function()
			withVault(function()
				local function asks(summary: string): boolean
					local text = table.concat(FailHints.lines("asset-x", summary, ""), "\n")
					return string.find(text, "came back", 1, true) ~= nil
				end
				check.falsy(asks("asset: trace_match 0.84 < 0.9 on the side view"))
				check.falsy(asks("asset: trace_match 0.86 < 0.9 on the side view"))
				check.truthy(asks("asset: trace_match 0.81 < 0.9 on the side view"))
				check.falsy(asks("asset: trace_match 0.83 < 0.9 on the side view"))
				check.equal(FailHints.signature("a", "x 0.84 < 0.9"), FailHints.signature("a", "x 0.86 < 0.9"))
			end)
		end)

		test.case("one step's generic failure is told apart by its output; the same output counts", function()
			withVault(function()
				local function asks(tail: string): boolean
					local text =
						table.concat(FailHints.lines("anim-gate", "anim-gate: pick_warnings failed", tail), "\n")
					return string.find(text, "came back", 1, true) ~= nil
				end
				check.falsy(asks("limb range 8/8 outside the loved catalog"))
				check.falsy(asks("ModuleNotFoundError: No module named cv2"))
				check.falsy(asks("the booth recording is missing for round 3"))
				check.falsy(asks("limb range 8/8 outside the loved catalog"))
				check.truthy(asks("limb range 7/8 outside the loved catalog"))
			end)
		end)

		test.case("a report about the lessons sheet itself gets no lessons and no count", function()
			withVault(function()
				local lines = FailHints.lines(
					"world-lessons",
					"world lessons RiverValley: 2 to answer before building",
					"the terrain reads like noise, no rivers in the valleys"
				)
				check.equal(#lines, 0)
				check.falsy(fs.isFile(FailHints.FILE))
			end)
		end)

		test.case("the words every failure says match no lesson", function()
			withVault(function()
				fs.writeFile(
					`{TMP}/world/lessons/gates.md`,
					"---\nkind: lesson\narea: world\ndate: 2026-11-01\n---\n\nWhen a gate check fails with an error, read the output above and fix the step it names.\n"
				)
				check.equal(FailHints.query("world-check: build failed", "error: the check failed at step 3"), "")
				check.equal(
					#FailHints.lines(
						"world-check",
						"world-check: build failed",
						"error: the check failed at step 3, see the output above"
					),
					0
				)
			end)
		end)

		test.case(
			"the hint prints after the failing output and before the summary; usage and missing tools get none",
			function()
				local Run = require("../../lib/run")
				local savedHook, savedOut = Run.onFail, Run.out
				local lines: { string } = {}
				Run.out = function(...: any)
					table.insert(lines, table.concat({ ... } :: { any }, " "))
				end
				Run.onFail = function(file: string, summary: string, tails: string)
					Run.out(`HINT {file}|{summary}|{tails}`)
				end
				local step = { name = "stepname", cmd = "tool x", exit = 1, ok = false, tail = "the failing tail" }
				local ok, err = pcall(function()
					local function index(prefix: string): number?
						for i, l in lines do
							if string.sub(l, 1, #prefix) == prefix then
								return i
							end
						end
						return nil
					end
					Run.report("zz-spec-hint", { step }, Run.CODES.CONTENT, "zz: it broke", "fix it")
					local t, h, s, n = index("--- stepname"), index("HINT "), index("summary: "), index("next_action: ")
					check.truthy(t and h and s and n and t < h and h < s and s < n)
					check.equal(lines[h or 0], "HINT zz-spec-hint|zz: it broke|the failing tail")
					for _, code in { Run.CODES.USAGE, Run.CODES.TOOLCHAIN, Run.CODES.PASS } do
						table.clear(lines)
						Run.report("zz-spec-hint", { step }, code, "zz: again", "x")
						check.equal(index("HINT "), nil)
					end
				end)
				Run.onFail, Run.out = savedHook, savedOut
				if fs.isFile(".verify/zz-spec-hint.json") then
					fs.removeFile(".verify/zz-spec-hint.json")
				end
				if not ok then
					error(err)
				end
			end
		)

		test.case("a traceback's frames, places and paths are not the failure's words", function()
			local py =
				"Traceback (most recent call last):\n  File \"C:\\Users\\DevUser\\Projects\\MyGame\\kit\\world\\dress.py\", line 12, in <module>\n    main()\nKeyError: 'river_width'"
			local q = FailHints.query("world: world dress failed", py, "world")
			check.falsy(string.find(q, "devuser", 1, true))
			check.falsy(string.find(q, "projects", 1, true))
			check.falsy(string.find(q, "world", 1, true)) -- the lane's own name matches every lesson of the lane
			check.truthy(string.find(q, "river", 1, true))
			local lune =
				"[string \"kit/world/dress\"]:40: attempt to index nil with 'piers'\n[Stack Begin]\n    Script 'kit/world/dress', Line 40 - function build\n[Stack End]"
			local q2 = FailHints.query("world: world dress failed", lune, "world")
			for _, w in { "script", "string", "begin", "function" } do
				check.falsy(string.find(q2, w, 1, true))
			end
			check.truthy(string.find(q2, "pier", 1, true))
			check.falsy(
				string.find(FailHints.clean("see /c/Users/DevUser/x.py and C:/Users/DevUser/y.py"), "DevUser", 1, true)
			)
		end)

		test.case("a step's JSON summary tells two failures apart behind one long fixed next_action", function()
			local long = string.rep("then re-run the same kit command and read the sheet again ", 6)
			local function verdict(summary: string): string
				return '{"status": "fail", "summary": "' .. summary .. '", "next_action": "' .. long .. '"}'
			end
			local sig = function(tail: string): string
				return FailHints.signature("world", "world: world check failed", tail)
			end
			check.truthy(sig(verdict("a river crosses the spawn")) ~= sig(verdict("a gap jump too long for R6")))
			check.equal(sig(verdict("3 piers too close")), sig(verdict("4 piers too close")))
		end)
	end)
end

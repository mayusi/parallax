-- loops.spec.luau (kit) — records that were written and never read, now read (2026-11-08, sprint 4: proposal 13 of
-- board/plans/archive/2026-11-08-pipeline-rag-learning-research.md): the UI judges' gap from the owner's eye reaches
-- kit verdict trend - stored beside the owner's score, or the median minus the owner's score on an older record.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Vault = require("../../lib/vault")

local TMP = "kit/selftest/vault/_tmp_loops"

local function withDir(body: () -> ())
	if fs.isDir(TMP) then
		fs.removeDir(TMP)
	end
	fs.writeDir(TMP .. "/ui")
	local saved = Vault.JUDGE_ROOTS
	Vault.JUDGE_ROOTS = { TMP .. "/ui" }
	local ok, err = pcall(body)
	Vault.JUDGE_ROOTS = saved
	fs.removeDir(TMP)
	if not ok then
		error(err)
	end
end

return function()
	test.suite("loops: the UI judges' gap from the owner's eye", function()
		test.case("no scored screen, no line; only one build's judges and owner are compared", function()
			withDir(function()
				local function judged(name: string, rec: { [string]: any })
					fs.writeFile(`{TMP}/ui/{name}.judge.json`, serde.encode("json", rec))
				end
				judged("Plain", { score = 60, model_sha256 = "p" })
				check.equal(Vault.judgeGapLine(), nil) -- judged, never scored by the owner
				judged("Old", { score = 50, model_sha256 = "b3", owner = { score = 90, model_sha256 = "b0" } })
				check.truthy(
					string.find(
						Vault.judgeGapLine() or "",
						"1 screen(s) the owner scored were judged on another build",
						1,
						true
					)
				)
				judged(
					"Gauge",
					{ score = 50, model_sha256 = "x", owner = { score = 85, gap = -35, judges_median = 50 } }
				)
				judged("Title", { score = 47, model_sha256 = "b1", owner = { score = 92, model_sha256 = "b1" } })
				judged("Hud", { score = 61, model_sha256 = "b2", owner = { score = 80, model_sha256 = "b2" } })
				local line = Vault.judgeGapLine() or ""
				check.truthy(string.find(line, "under the owner by a median 35 on 3 screen(s)", 1, true))
				check.truthy(string.find(line, "1 more scored on another build, not compared", 1, true))
			end)
		end)
	end)

	test.suite("loops: a bare link to a name several lanes share is a weekly warning", function()
		test.case("[[golden]] warns (it may open another lane's page); [[anim/golden]] does not", function()
			if fs.isDir(TMP) then
				fs.removeDir(TMP)
			end
			for _, lane in { "anim", "vfx" } do
				fs.writeDir(`{TMP}/{lane}`)
				fs.writeFile(`{TMP}/{lane}/golden.md`, "# golden\n")
			end
			fs.writeFile(`{TMP}/anim/notes.md`, "see [[golden]] and [[anim/golden]] and [[notes]]\n")
			local saved = Vault.ROOT
			Vault.ROOT = TMP
			local ok, err = pcall(function()
				local hits = {}
				for _, w in Vault.audit() do
					if string.find(w.warning, "names 2 notes", 1, true) then
						table.insert(hits, w)
					end
				end
				check.equal(#hits, 1)
				check.equal(hits[1].dept, "anim")
				check.truthy(string.find(hits[1].warning, "[[<lane>/golden]]", 1, true))
			end)
			Vault.ROOT = saved
			fs.removeDir(TMP)
			if not ok then
				error(err)
			end
		end)
	end)

	test.suite("loops: the regression corpus (kit bug)", function()
		test.case("one planted change is filed once; two different bugs never share an id", function()
			local R = require("../../lib/regressions")
			local cases = { { id = "dash-cooldown", module = "m", line = "l", from = "<", to = "<=" } }
			local id, filed = R.place(cases, { id = "", module = "m", line = "l", from = "<", to = "<=" }, "other")
			check.equal(id, "dash-cooldown")
			check.truthy(filed)
			local id2, filed2 =
				R.place(cases, { id = "", module = "m", line = "l2", from = "<", to = "<=" }, "dash-cooldown")
			check.equal(id2, "dash-cooldown-2")
			check.equal(filed2, nil)
		end)

		test.case("kit bug refuses without its fields, before anything runs", function()
			local Run = require("../../lib/run")
			local handlers: { [string]: (any) -> number } = {}
			require("../../cmd/systems")({
				command = function(_g: string, name: string, _u: string, _a: string, run: (any) -> number)
					handlers[name] = run
				end,
			})
			local savedOut = Run.out
			Run.out = function() end
			local ok, code = pcall(handlers.bug, { "dash ignores its cooldown", "--spec", "tests/x.spec.luau" })
			Run.out = savedOut
			if fs.isFile(".verify/bug.json") then
				fs.removeFile(".verify/bug.json")
			end
			check.truthy(ok)
			check.equal(code, Run.CODES.USAGE)
		end)
	end)

	test.suite("loops: playtest results reach the QA record", function()
		test.case("one note per playtest: status now, what failed, the last runs newest first", function()
			local Playtests = require("../../lib/playtests")
			if fs.isDir(TMP) then
				fs.removeDir(TMP)
			end
			fs.writeDir(TMP)
			local savedRoot, savedKeep = Vault.ROOT, Playtests.KEEP
			Vault.ROOT, Playtests.KEEP = TMP, 3
			local ok, err = pcall(function()
				check.equal(#Playtests.failing(), 0)
				Playtests.record("smoke", true, 4, 4, {}, { memoryMb = 210, frameMs = 16.2 })
				local path = Playtests.record("smoke", false, 3, 4, { "dash cooldown (0.4 s, wanted 0.5)" })
				local text = fs.readFile(path)
				check.truthy(string.find(text, "status: fail", 1, true))
				check.truthy(string.find(text, "dash cooldown (0.4 s, wanted 0.5)", 1, true))
				check.truthy(string.find(text, "FAIL 3/4\n  - ", 1, true)) -- the newest run first
				check.truthy(string.find(text, "pass 4/4 · 210 MB · 16.2 ms/frame", 1, true))
				local failing = Playtests.failing()
				check.equal(#failing, 1)
				check.truthy(
					string.find(failing[1], "smoke", 1, true) and string.find(failing[1], "dash cooldown", 1, true)
				)
				for _ = 1, 4 do
					Playtests.record("smoke", true, 4, 4, {})
				end
				local runs = 0
				for _ in string.gmatch(fs.readFile(path), "\n  %- %d%d%d%d%-") do
					runs += 1
				end
				check.equal(runs, 3) -- the last KEEP runs only
				check.equal(#Playtests.failing(), 0) -- passing again: off the list
			end)
			Vault.ROOT, Playtests.KEEP = savedRoot, savedKeep
			fs.removeDir(TMP)
			if not ok then
				error(err)
			end
		end)
	end)
end

-- boardweb.spec.luau (kit) — the data behind `kit board`: every board read from the same task files the CLI writes,
-- cards that know the pipeline, and the owner's writes held to the CLI's rules (a reason to block, drop or close early).
local fs = require("@lune/fs")
local process = require("@lune/process")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Board = require("../../lib/board")
local BoardWeb = require("../../lib/boardweb")

local TASK = [[---
id: %s
title: %s
status: %s
priority: p1
area: 3d
owner: %s
claimed_at: "%s"
created: "2026-10-01T00:00:00Z"
updated: "%s"
depends: [%s]
labels: []
---

## Goal
Build the crate_small prop from its references.

## Done when
- [x] the brief answered
- [ ] the owner rated it 7+

## Notes
- 2026-10-01T00:00:00Z **claude-code**: created
]]

local function fixture(): string
	local base = (process.env.TEMP or process.env.TMPDIR or "/tmp") .. "/kit-boardweb-spec-" .. tostring(os.time())
	local root = string.gsub(base, "\\", "/") .. "/"
	for _, d in { "board/tasks", "games/Arena/board/tasks", "games/NoBoard/src", "assets/models", "build/renders" } do
		fs.writeDir(root .. d)
	end
	fs.writeFile(root .. "kit.config.json", '{"name": "Fixture"}')
	fs.writeFile(root .. "board/BRIEF.md", "# Fixture\n\nMilestone: the first playable\n")
	fs.writeFile(root .. "assets/models/build_crate_small.py", "# x\n")
	fs.writeFile(root .. "build/renders/crate_small.png", "png")
	local old = "2026-01-01T00:00:00Z"
	fs.writeFile(
		root .. "board/tasks/aaaa-crate.md",
		string.format(TASK, "aaaa", "crate_small prop", "doing", "claude-code", old, old, "bbbb")
	)
	fs.writeFile(
		root .. "board/tasks/bbbb-dep.md",
		string.format(TASK, "bbbb", "the references", "todo", "", "", "", "")
	)
	fs.writeFile(root .. "board/tasks/cccc-odd.md", string.format(TASK, "cccc", "odd status", "ready", "", "", "", ""))
	return root
end

return function()
	test.suite("boardweb: the local Trello over the task files", function()
		local root = fixture()
		BoardWeb.ROOT = root

		test.case("every board: the project's and each game's that has one", function()
			local keys = {}
			for _, b in BoardWeb.boards() do
				table.insert(keys, b.key)
			end
			check.equal(table.concat(keys, ","), "root,Arena")
			check.equal(BoardWeb.board("root").name, "Fixture")
			check.equal(BoardWeb.board("Arena").dir, "games/Arena/board")
			check.equal(BoardWeb.board("../board"), nil)
		end)

		test.case("a card knows its claim, what it waits on, its progress, notes and the pieces it names", function()
			local r = BoardWeb.read(BoardWeb.board("root"))
			check.equal(r.brief.milestone, "the first playable")
			local byId = {}
			for _, c in r.tasks do
				byId[c.id] = c
			end
			local c = byId.aaaa
			check.is_true(c.stale)
			check.equal(#c.waiting, 1)
			check.equal(c.waiting[1].id, "bbbb")
			check.equal(c.done, 1)
			check.equal(c.total, 2)
			check.equal(c.notes[1].who, "claude-code")
			check.equal(c.goal, "Build the crate_small prop from its references.")
			check.equal(#c.related, 1)
			check.equal(c.related[1].kind, "asset")
			check.equal(c.related[1].preview, "build/renders/crate_small.png")
			-- an unknown status shows in To do, its real value kept
			check.equal(byId.cccc.status, "todo")
			check.equal(byId.cccc.rawStatus, "ready")
		end)

		test.case("a claim untouched over a day goes back to To do with a note naming its holder", function()
			local b = BoardWeb.board("root")
			local dry = Board.releaseStale(BoardWeb.tasks(b), "spec", true)
			check.equal(#dry, 1)
			check.equal(dry[1].id, "aaaa")
			check.equal(dry[1].owner, "claude-code")
			local t = Board.parse(fs.readFile(root .. "board/tasks/aaaa-crate.md"), "x") :: Board.Task
			check.equal(t.status, "doing") -- a dry run writes nothing
			check.is_true((BoardWeb.act(b, { action = "sweep" })))
			t = Board.parse(fs.readFile(root .. "board/tasks/aaaa-crate.md"), "x") :: Board.Task
			check.equal(t.status, "todo")
			check.equal(t.owner, "")
			check.truthy(string.find(t.body, "released a stale claim: claude-code left it untouched", 1, true))
			-- a fresh claim is left alone; a second sweep finds nothing
			check.equal(#Board.releaseStale(BoardWeb.tasks(b), "spec", true), 0)
		end)

		test.case("a loose end (the owner's ask, a doubt, a redo) keeps the words whole and shows its kind", function()
			local long = string.rep("make the guard pose read from the back, ", 4) .. "100% clear"
			local t = Board.loose("ask", long, "anim", "aaaa")
			check.equal(t.labels[1], "owner-ask")
			check.equal(t.priority, "p1")
			check.is_true(#t.title <= 110)
			check.truthy(string.find(t.body, 'The owner asked: "' .. long .. '"', 1, true))
			check.truthy(string.find(t.body, "About card aaaa.", 1, true))
			local b = BoardWeb.board("root")
			local ok, _, id = BoardWeb.act(b, {
				action = "create",
				kind = "unsure",
				title = "hilt length",
				goal = "the hilt may be 10% long",
				area = "3d",
			})
			check.is_true(ok)
			local byId = {}
			for _, c in BoardWeb.read(b).tasks do
				byId[c.id] = c
			end
			check.equal(byId[id].kind, "unsure")
			check.equal(byId[id].goal, "Not sure: the hilt may be 10% long")
			local ends = Board.looseEnds(BoardWeb.tasks(b))
			check.equal(#ends.unsure, 1)
			check.equal(#ends.ask, 0)
			check.is_true((BoardWeb.act(b, { action = "move", id = id, status = "dropped", reason = "settled" })))
			check.equal(#Board.looseEnds(BoardWeb.tasks(b)).unsure, 0) -- a closed one is no longer loose
		end)

		test.case("the background board stays off when the owner turned it off", function()
			check.truthy(BoardWeb.autoOff({ board_auto = false }))
			local url, why = BoardWeb.ensure(nil, { board_auto = false })
			check.equal(url, nil)
			check.truthy(string.find(why, "^off"))
		end)

		test.case("moves hold the CLI's rules and record the owner", function()
			local b = BoardWeb.board("root")
			local ok, msg = BoardWeb.act(b, { action = "move", id = "bbbb", status = "blocked" })
			check.is_false(ok)
			check.truthy(string.find(msg, "reason", 1, true))
			ok, msg = BoardWeb.act(b, { action = "move", id = "aaaa", status = "done" })
			check.is_false(ok)
			check.truthy(string.find(msg, "1 done-when item", 1, true))
			ok = BoardWeb.act(b, { action = "move", id = "bbbb", status = "doing" })
			check.is_true(ok)
			local t = Board.parse(fs.readFile(root .. "board/tasks/bbbb-dep.md"), "x") :: Board.Task
			check.equal(t.status, "doing")
			check.equal(t.owner, BoardWeb.WHO)
			check.truthy(string.find(t.body, "moved todo -> doing", 1, true))
			ok = BoardWeb.act(b, { action = "move", id = "bbbb", status = "todo" })
			t = Board.parse(fs.readFile(root .. "board/tasks/bbbb-dep.md"), "x") :: Board.Task
			check.equal(t.owner, "")
			ok = BoardWeb.act(b, { action = "move", id = "aaaa", status = "done", reason = "proved in the playtest" })
			check.is_true(ok)
		end)

		test.case("done-when items tick and untick; a bad item, id or column is refused", function()
			local b = BoardWeb.board("root")
			check.is_true((BoardWeb.act(b, { action = "check", id = "bbbb", n = 2, done = true })))
			local t = Board.parse(fs.readFile(root .. "board/tasks/bbbb-dep.md"), "x") :: Board.Task
			check.equal(Board.checklist(t)[2].done, true)
			check.is_true((BoardWeb.act(b, { action = "check", id = "bbbb", n = 1, done = false })))
			t = Board.parse(fs.readFile(root .. "board/tasks/bbbb-dep.md"), "x") :: Board.Task
			check.equal(Board.checklist(t)[1].done, false)
			check.is_false((BoardWeb.act(b, { action = "check", id = "bbbb", n = 9 })))
			check.is_false((BoardWeb.act(b, { action = "move", id = "../x", status = "done" })))
			check.is_false((BoardWeb.act(b, { action = "move", id = "bbbb", status = "shipped" })))
			check.is_false((BoardWeb.act(b, { action = "nuke", id = "bbbb" })))
			check.is_false((BoardWeb.act(b, { action = "note", id = "bbbb", text = "  " })))
		end)

		test.case("a new card lands in To do with its checklist, one-line title and a safe lane", function()
			local b = BoardWeb.board("Arena")
			local ok, _, id = BoardWeb.act(b, {
				action = "create",
				title = "Boss arena\nlighting pass",
				area = "../../etc",
				priority = "p0",
				done = { "the owner walked it", "", "lit at dusk" },
			})
			check.is_true(ok)
			local list = BoardWeb.tasks(b)
			check.equal(#list, 1)
			local t = list[1]
			check.equal(t.id, id)
			check.equal(t.title, "Boss arena lighting pass")
			check.equal(t.area, "other")
			check.equal(t.priority, "p0")
			check.equal(t.status, "todo")
			check.equal(#Board.checklist(t), 2)
			check.truthy(string.find(t.file, "games/Arena/board/tasks/", 1, true))
		end)

		test.case("cleanup", function()
			BoardWeb.ROOT = ""
			fs.removeDir(string.sub(root, 1, -2))
			check.is_true(true)
		end)
	end)
end

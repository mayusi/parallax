-- work.luau — the work board commands. These are what make a model / harness switch lossless:
-- every arriving model runs `kit status`, every leaving model runs `kit handoff`.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Board = require("../lib/board")
local Config = require("../lib/config")
local Integrity = require("../lib/integrity")
local Origin = require("../lib/origin")
local Run = require("../lib/run")
local Vault = require("../lib/vault")

local C = Run.CODES

local function usage(file: string, msg: string, example: string): number
	return Run.report(file, {}, C.USAGE, msg, "run: " .. example)
end

local function oneOf(v: string, list: { string }): boolean
	return table.find(list, v) ~= nil
end

local function git(args: { string }): string
	local ok, r = pcall(process.exec, "git", args)
	if ok and r.ok then
		return (string.gsub(r.stdout, "%s+$", ""))
	end
	return ""
end

-- Quality gates only: board/scaffold/setup commands also write verdicts, but a refused `task claim` is not a
-- failing gate and must never become the next action.
local GATE_PREFIXES = {
	"verify",
	"test",
	"lint",
	"build",
	"audit",
	"selftest",
	"doctor",
	"asset",
	"validate",
	"calibrate",
	"sfx",
	"audio-check",
	"vfx",
	"ui",
	"playtest",
}
local function isGate(name: string): boolean
	for _, p in GATE_PREFIXES do
		if name == p or string.sub(name, 1, #p + 1) == p .. "-" then
			return true
		end
	end
	return false
end

-- latest verdict of every quality gate, newest first
local function verdicts(): { any }
	local out = {}
	if not fs.isDir(".verify") then
		return out
	end
	for _, name in fs.readDir(".verify") do
		if string.sub(name, -5) == ".json" then
			local ok, v = pcall(serde.decode, "json" :: any, fs.readFile(".verify/" .. name))
			if ok and type(v) == "table" and v.status and isGate(string.sub(name, 1, -6)) then
				local meta = fs.metadata(".verify/" .. name)
				table.insert(out, {
					name = string.sub(name, 1, -6),
					status = v.status,
					summary = v.summary,
					next_action = v.next_action,
					at = meta.modifiedAt and meta.modifiedAt.unixTimestamp or 0,
				})
			end
		end
	end
	table.sort(out, function(a, b)
		return a.at > b.at
	end)
	return out
end

-- an owner ask that judges shown work, filed once as the owner's words in its lane's vault: a verdict note named
-- ask-<card id> with no number and no direction (never averaged, never golden, never credits a lesson; the distil
-- and the lane's page read it). nil when it does not judge work, has no lane with a vault, or was filed before.
local function askFiled(area: string, t: Board.Task): boolean
	return Vault.askFiled(area, t.id)
end

-- `lane`: the vault the words go to - the lane given or read from the words when the ask is written; for an older
-- card, the lane its WORDS point to (a card filed under code that judges an animation goes to anim; a tie, nowhere)
local function fileAskWords(t: Board.Task, text: string, lane: string?): string?
	if not lane or not Board.judgesWork(text) then
		return nil
	end
	return Vault.fileAsk(lane, t.id, text, string.match(tostring(t.created or ""), "^(%d%d%d%d%-%d%d%-%d%d)"))
end

local function line(t: Board.Task): string
	local owner = if t.owner ~= "" then `  @{t.owner}` else ""
	local stale = if Board.isStale(t) then "  [STALE claim — may be taken with --steal]" else ""
	local cl = Board.checklist(t)
	local progress = ""
	if #cl > 0 then
		local done = 0
		for _, c in cl do
			if c.done then
				done += 1
			end
		end
		progress = `  ({done}/{#cl})`
	end
	return `  {t.id}  {t.priority} {t.area}  {t.title}{progress}{owner}{stale}`
end

return function(Cli: any)
	-- ------------------------------------------------------------ status: the arriving model's briefing
	Cli.command(
		"start",
		"status",
		"status [--as who] [--dept <area>] [--json]",
		"BRIEFING: project, board, last handoff, failing gates, your department's page (the vault), next step",
		function(args)
			local _, flags = Cli.parse(args)
			local me = Board.agent(flags.as)
			local cfg = Config.load()
			local tasks = Board.tasks()
			local byId = {}
			for _, t in tasks do
				byId[t.id] = t
			end
			local groups = { doing = {}, ready = {}, waiting = {}, blocked = {}, review = {} }
			local counts = {}
			for _, t in tasks do
				counts[t.status] = (counts[t.status] or 0) + 1
				if t.status == "doing" then
					table.insert(groups.doing, t)
				elseif t.status == "todo" then
					table.insert(if Board.ready(t, byId) then groups.ready else groups.waiting, t)
				elseif t.status == "blocked" then
					table.insert(groups.blocked, t)
				elseif t.status == "review" then
					table.insert(groups.review, t)
				end
			end
			local handoff = Board.latest("handoffs")
			local vs = verdicts()
			local failing, reports = {}, {}
			for _, v in vs do
				if v.status == "fail" then
					-- a per-item verdict ("asset-x", "judge-x", "optimize-x") is a REPORT below its bar: the bar is the
					-- owner's. A pipeline gate (no item in its name) failing is what blocks work.
					table.insert(if string.find(v.name, "-", 1, true) then reports else failing, v)
				end
			end
			local mine = {}
			for _, t in groups.doing do
				if t.owner == me then
					table.insert(mine, t)
				end
			end

			-- kit files edited or deleted in this project (an AI "fixing" a gate is the usual cause), and files ADDED
			-- under kit/ that the kit never installed: no kit file, but one there can still change what the kit runs (a
			-- module a kit script imports by name, a spec the runner picks up) - so it is named too, with the one
			-- remedy that clears it (move it out or delete it: no command "restores" a file the kit never had)
			local integrity = Integrity.check()
			local tampered, added = {}, {}
			if integrity then
				for _, p in integrity.changed do
					table.insert(tampered, p .. " (edited)")
				end
				for _, p in integrity.missing do
					table.insert(tampered, p .. " (deleted)")
				end
				for _, p in integrity.added do
					table.insert(added, p)
				end
			end
			-- (the kit's own files come back from what put them here last - kit/lib/origin.luau: a GitHub release, from
			-- that release - an upgrade to the same one, forced (--allow-dirty: the edit being undone is itself an
			-- uncommitted change), even when kit/HOME still names the clone it was first installed from; the kit home,
			-- with `sync`, when that home is really there; a kit from a clone, from a clone - a release of the same
			-- number may not hold the clone's files)
			local origin = Origin.of()
			local record = Origin.record()
			local tag = if record and type(record.installed_tag) == "string" then record.installed_tag else nil
			local fromFile = record ~= nil and record.source == "file"
			local restoreHint = if origin == "home"
				then "lune run kit sync"
				elseif
					origin == "release"
					and tag
					and fromFile
				then `lune run parallax upgrade --from <the release file it came from> --force --allow-dirty   (or, if {tag} is published: --tag {tag})`
				elseif origin == "release" and tag then `lune run parallax upgrade --force --allow-dirty --tag {tag}`
				else "lune run parallax update <this game>   (in a clone of the kit)"

			-- the single next step, in priority order (a file the kit did not install comes after a failing gate: one the
			-- kit writes itself that this list does not know must never hide a red gate)
			local nextAction: string
			if not fs.isDir(Board.dir()) then
				nextAction = "no board yet — run: lune run kit init"
			elseif #tampered > 0 then
				local more = if #tampered > 1 then ` +{#tampered - 1} more` else ""
				nextAction =
					`kit-owned files were changed here ({tampered[1]}{more}) — never edit kit/ or src/kit/; restore them: {restoreHint}`
			elseif #failing > 0 then
				nextAction = `a gate is failing ({failing[1].name}): {failing[1].next_action or "re-run it"}`
			elseif #added > 0 then
				local more = if #added > 1 then ` +{#added - 1} more` else ""
				nextAction =
					`files the kit did not install are among its own (kit/, src/kit/: {added[1]}{more}) — one there can change what the kit runs: move yours out, delete the rest`
			elseif #mine > 0 then
				nextAction = `continue your task {mine[1].id}: lune run kit task show {mine[1].id}`
			elseif #groups.ready > 0 then
				nextAction = `claim the top ready task: lune run kit task claim {groups.ready[1].id} --as "{me}"`
			elseif #groups.doing > 0 then
				nextAction = `all ready work is claimed — check stale claims or ask the human what's next`
			else
				nextAction =
					'board is empty — add work: lune run kit task add "title" --area code --done "observable check"'
			end

			if flags.json then
				print(serde.encode("json", {
					project = cfg.name,
					you = me,
					counts = counts,
					doing = groups.doing,
					ready = groups.ready,
					blocked = groups.blocked,
					review = groups.review,
					handoff = handoff,
					failing = failing,
					next_action = nextAction,
				}))
				return C.PASS
			end

			print(`== {cfg.name} — you are "{me}" (pass --as "<model>@<harness>" on board commands)`)
			-- GAMES: which game this session works in (everything made lands in its folder)
			local Game = require("./game")
			local games = Game.list()
			if cfg.game then
				print(
					`\n-- GAME: {cfg.game} — every command reads and writes games/{cfg.game}/ (its brief: games/{cfg.game}/GAME.md)`
				)
			else
				print(
					`\n-- GAME: none active — games: {if #games > 0 then table.concat(games, ", ") else "(none yet)"}`
				)
				print(
					"  making a game? lune run kit game new <Name> FIRST (all its work lands in games/<Name>/); working on one: kit game use <Name>"
				)
			end
			if Config.missingGame then
				print(`  ! the active game "{Config.missingGame}" has no folder — kit game use <Name> | none`)
			end
			local brief = if cfg.game and fs.isFile(`games/{cfg.game}/GAME.md`)
				then `games/{cfg.game}/GAME.md`
				else Board.dir("BRIEF.md")
			if fs.isFile(brief) then
				local text = fs.readFile(brief)
				local lines = string.split(text, "\n")
				print("\n-- brief (" .. brief .. ")")
				for i = 1, math.min(#lines, 14) do
					print("  " .. lines[i])
				end
			end
			local function section(title: string, list: { Board.Task }, limit: number)
				if #list == 0 then
					return
				end
				print(`\n-- {title} ({#list})`)
				for i = 1, math.min(#list, limit) do
					print(line(list[i]))
				end
				if #list > limit then
					print(`  ... {#list - limit} more: lune run kit task list`)
				end
			end
			section("IN PROGRESS", groups.doing, 10)
			section("READY (deps done, by priority)", groups.ready, 8)
			section("REVIEW", groups.review, 5)
			section("BLOCKED", groups.blocked, 5)
			section("WAITING ON DEPENDENCIES", groups.waiting, 5)
			if handoff then
				print("\n-- last handoff: " .. handoff)
				local lines = string.split(fs.readFile(handoff), "\n")
				for i = 1, math.min(#lines, 18) do
					print("  " .. lines[i])
				end
			end
			if #tampered > 0 then
				print(`\n-- KIT FILES CHANGED ({#tampered}) — restore with: {restoreHint}`)
				for i = 1, math.min(#tampered, 8) do
					print("  " .. tampered[i])
				end
			end
			if #added > 0 then
				print(
					`\n-- files among the kit's own (kit/, src/kit/) that the kit did not install ({#added}): your own, or ones an older kit left behind - upgrades keep them; move your game's out, delete the rest`
				)
				for i = 1, math.min(#added, 8) do
					print("  " .. added[i])
				end
			end
			if #vs > 0 then
				print("\n-- gates (latest verdicts; per-item reports below their bar are counted apart)")
				local shown = 0
				for _, v in vs do
					if not string.find(v.name, "-", 1, true) then
						print(`  [{v.status}] {v.name}: {v.summary or ""}`)
						shown += 1
						if shown >= 8 then
							break
						end
					end
				end
				if #reports > 0 then
					print(
						`  reports below their bar: {#reports} (the owner's eye is the bar; kit vault prune-verdicts retires stale ones)`
					)
				end
			end
			-- THE VAULT: what every department learned, the owner's verdicts, the graveyard and the golden set
			if Vault.exists() then
				local vbudget = (cfg.vault and tonumber(cfg.vault.budget)) or 1500
				-- the owner's inbox (inbox.md, written in Obsidian): file every new line now, so the pages below
				-- already carry the owner's latest words
				local pending, unreadable = Vault.inboxPending()
				if pending > 0 then
					local step = Run.spawn(
						"vault inbox",
						Run.tool("python"),
						{ "kit/scripts/vault_migrate.py", "--only", "inbox" },
						true
					)
					local stillPending, stillUnreadable = Vault.inboxPending()
					print(
						`\n-- the owner's inbox: {pending - stillPending} verdict(s) filed into the vault{if step.ok
							then ""
							else " (the sync failed: lune run kit vault sync)"}{if stillUnreadable > 0
							then `; {stillUnreadable} line(s) could not be read (see inbox.md)`
							else ""}`
					)
				elseif unreadable > 0 then
					print(
						`\n-- the owner's inbox: {unreadable} line(s) could not be read — kit/knowledge/vault/inbox.md`
					)
				end
				-- the lanes' own stores (VFX/SFX/anim verdict files, lessons) are filed into the vault here by themselves
				local filed, clean = Vault.catchUp()
				if #filed > 0 then
					print(
						`\n-- the vault caught up by itself: {table.concat(filed, ", ")} filed{if clean
							then ""
							else " (the sync failed: lune run kit vault sync)"} — commit kit/knowledge/vault`
					)
				end
				-- learning that is due: a distil per department after DISTIL_EVERY owner verdicts, the vault's audit
				local due = {}
				for _, d in { "3d", "vfx", "ui", "anim", "world", "sfx", "code", "qa", "kit" } do
					local n = Vault.distilDue(d)
					if n then
						table.insert(due, `{d} ({n} verdicts)`)
					end
				end
				if #due > 0 then
					print(
						`\n-- distil due: {table.concat(due, ", ")} — lune run kit vault distil <dept> (the lane's own session does it)`
					)
				end
				-- is the loop used? the owner's verdicts of the last 14 days on pieces whose lessons were cited
				local since = os.date("!%Y-%m-%d", os.time() - 14 * 86400) :: string
				local hit, total = Vault.adoption(since)
				if total > 0 then
					print(
						`\n-- lessons cited on {hit} of the owner's {total} verdict(s) since {since} — cite yours: lune run kit lesson used <id,...> --piece <kind> <name>`
					)
				end
				local okA, warnings = pcall(Vault.audit)
				if okA and #warnings > 0 then
					print(
						`\n-- vault audit: {#warnings} open note(s) (rejected-again rows without the failed route, rows without a source) — lune run kit vault check`
					)
				end
				-- still behind? (only when the sync above failed)
				local behind = Vault.behind()
				if #behind > 0 then
					local parts = {}
					for _, b in behind do
						table.insert(parts, `{b.store} ({b.files} file(s){if b.never then ", never synced" else ""})`)
					end
					print(
						`\n-- vault BEHIND its stores: {table.concat(parts, ", ")} — lune run kit vault sync, then commit kit/knowledge/vault`
					)
				end
				-- Obsidian opened on the PROJECT ROOT (its settings folder there, used in the last week) indexes every
				-- markdown file in the project and none of the vault's settings (graph colours, drafts folder, ignores)
				local rootWs = ".obsidian/workspace.json"
				if fs.isFile(rootWs) then
					local meta = fs.metadata(rootWs)
					local at = meta.modifiedAt and meta.modifiedAt.unixTimestamp or 0
					if os.time() - at < 7 * 86400 then
						print(
							"\n-- Obsidian is open on the PROJECT ROOT: open the folder kit/knowledge/vault as the vault instead (its settings live there)"
						)
					end
				end
				print("\n-- departments (kit/knowledge/vault — read your department's page before building)")
				for _, d in Vault.DEPTS do
					if d ~= "shared" and fs.isDir(Vault.dir(d)) then
						local c = Vault.counts(d)
						local last = Vault.verdicts(d)[1]
						local lastText = if last
							then ` · last verdict {last.front.date} {last.front.name}{if last.front.score ~= nil
								then " " .. tostring(last.front.score) .. "/10"
								elseif Vault.direction(last.front) == "keep" then " Keep"
								elseif Vault.direction(last.front) == "redo" then " Redo"
								else ""}`
							else ""
						print(
							`  {d}: {c.lessons} lessons · {c.verdicts} verdicts · golden {c.golden} · graveyard {c.graveyard}{lastText}`
						)
						-- the trend in one line (mean, the last 7 days against the 7 before): a report, never a target
						if c.verdicts > 0 then
							local t = Vault.trend(d)[1]
							local tail = string.match(t or "", "· (mean .*)$")
							if tail then
								print(`     {tail}`)
							end
						end
					end
				end
				-- do the kit's own judges track the owner? (n, rank correlation, mean error per department)
				for _, l in Vault.calibration() do
					if not string.find(l, "no piece has both", 1, true) then
						print("  judges vs the owner — " .. l)
					end
				end
				-- the page: --dept, else the department of your task in progress
				local dept = Vault.dept(if type(flags.dept) == "string" then flags.dept else nil)
				if not dept and #mine > 0 then
					dept = Vault.dept(mine[1].area)
				end
				if dept and fs.isDir(Vault.dir(dept)) then
					print("")
					print(Vault.page(dept, vbudget))
					local Routes = require("../lib/routes")
					local stages = Routes.stages(dept)
					if #stages > 0 then
						print(
							`  route ({dept}): {table.concat(stages, " -> ")} — the stage's five commands: lune run kit help --stage {dept}:<stage>`
						)
					end
				else
					print(
						"  load your lane (boot sheet, stage, tasks, handoff, page): lune run kit start <3d|vfx|sfx|ui|world|anim|code|qa|kit>"
					)
				end
				-- what awaits the owner (the missions' pending queues)
				local pendingDir = "board/plans/missions/pending"
				if fs.isDir(pendingDir) then
					local waiting = {}
					for _, f in fs.readDir(pendingDir) do
						if string.sub(f, -3) == ".md" and f ~= "README.md" then
							-- a section the owner answered ("- answer ...") or that opens no question ("## note") is
							-- not waiting; only the open ones count
							local n = 0
							local text = "\n" .. string.gsub(fs.readFile(`{pendingDir}/{f}`), "\r\n", "\n") .. "\n## "
							local starts = {}
							local at = string.find(text, "\n## ", 1, true)
							while at do
								table.insert(starts, at)
								at = string.find(text, "\n## ", at + 1, true)
							end
							for i = 1, #starts - 1 do
								local block = string.sub(text, starts[i] + 4, starts[i + 1])
								if not string.match(block, "^note") and not string.find(block, "\n%- answer") then
									n += 1
								end
							end
							if n > 0 then
								table.insert(waiting, `{string.sub(f, 1, -4)} ({n})`)
							end
						end
					end
					if #waiting > 0 then
						print(
							`\n-- awaiting the OWNER: {table.concat(waiting, ", ")} — board/plans/missions/pending/`
						)
					end
				end
			end
			local branch = git({ "rev-parse", "--abbrev-ref", "HEAD" })
			if branch ~= "" then
				local dirty = git({ "status", "--porcelain" })
				local n = if dirty == "" then 0 else #string.split(dirty, "\n")
				print(`\n-- git: {branch}, {n} uncommitted change(s), last: {git({ "log", "-1", "--format=%h %s" })}`)
			end
			-- the COMMITTED tree's last proof (kit prove: verify + selftest in a sandbox worktree of a commit)
			if fs.isFile(".verify/prove.last.json") then
				local okP, pv = pcall(serde.decode, "json" :: any, fs.readFile(".verify/prove.last.json"))
				if okP and type(pv) == "table" then
					local short = string.sub(tostring(pv.sha or ""), 1, 8)
					local v, st = pv.verify or {}, pv.selftest or {}
					if v.ok and st.ok then
						print(
							`-- committed tree: proven GREEN at {short} on {pv.when}{if st.ran
								then " (verify + selftest)"
								else " (verify)"} — lune run kit prove`
						)
					else
						print(
							`-- committed tree: RED at {short} on {pv.when} — {if not v.ok
								then v.failing or v.summary
								else st.summary} (lune run kit prove)`
						)
					end
				end
			else
				print(
					"-- committed tree: never proven — lune run kit prove (verify + selftest of HEAD in a sandbox worktree)"
				)
			end
			print("")
			return Run.report(
				"status",
				{},
				C.PASS,
				`status: {#groups.doing} in progress, {#groups.ready} ready, {#groups.blocked} blocked, {#failing} failing gate(s)`,
				nextAction
			)
		end
	)

	-- ------------------------------------------------------------ task
	Cli.command(
		"work",
		"task",
		'task add|list|show|claim|note|check|done|block|review|drop|release|sweep [--dry] | task ask|unsure|rework "text" [--on <card>] [--area] | task route [--apply] | task resume',
		"the board: one markdown file per task in board/tasks",
		function(args)
			local sub = args[1]
			local pos, flags = Cli.parse({ table.unpack(args, 2) })
			local me = Board.agent(flags.as)

			if sub == "add" then
				local title = pos[1]
				if not title then
					return usage(
						"task",
						"task add: needs a title",
						'lune run kit task add "Dash ability" --area code --priority p1 --done "dash covers 12 studs"'
					)
				end
				local area = flags.area or "code"
				local priority = flags.priority or "p2"
				if not oneOf(area, Board.AREAS) then
					return usage("task", `task add: area must be {table.concat(Board.AREAS, "|")}`, "--area code")
				end
				if not string.match(priority, "^p[0-3]$") then
					return usage("task", "task add: priority must be p0 (urgent) .. p3 (someday)", "--priority p1")
				end
				local id = Board.newId()
				local done = flags.list.done or {}
				local body = "\n## Goal\n" .. (flags.goal or title) .. "\n\n## Done when\n"
				if #done == 0 then
					body ..= "- [ ] (add observable checks: a command that passes, a behaviour you can see)\n"
				end
				for _, d in done do
					body ..= `- [ ] {d}\n`
				end
				local t: any = {
					id = id,
					title = title,
					status = "todo",
					priority = priority,
					area = area,
					owner = "",
					claimed_at = "",
					created = Board.now(),
					updated = "",
					depends = flags.list.depends or {},
					labels = flags.list.label or {},
					body = body,
					file = Board.dir("tasks") .. `/{id}-{Board.slug(title)}.md`,
				}
				Board.note(t, me, "created")
				Board.save(t)
				Board.journal(me, `added task {id} "{title}"`)
				return Run.report(
					"task",
					{},
					C.PASS,
					`task {id} added: {title}`,
					`claim it when you start: lune run kit task claim {id} --as "{me}"`
				)
			end

			if sub == "list" then
				local tasks = Board.tasks()
				local shown = {}
				for _, t in tasks do
					local statusOk = if flags.status
						then t.status == flags.status
						else (t.status ~= "done" and t.status ~= "dropped")
					if flags.all then
						statusOk = true
					end
					local areaOk = not flags.area or t.area == flags.area
					local mineOk = not flags.mine or t.owner == me
					local kindOk = not flags.kind or Board.kindOf(t) == flags.kind
					if statusOk and areaOk and mineOk and kindOk then
						table.insert(shown, t)
					end
				end
				if flags.json then
					print(serde.encode("json", shown))
					return C.PASS
				end
				for _, t in shown do
					print(`[{t.status}]` .. line(t))
				end
				return Run.report(
					"task",
					{},
					C.PASS,
					`task list: {#shown} task(s)`,
					"details: lune run kit task show <id>"
				)
			end

			-- a loose end, written down the moment it appears: the owner's words, a doubt, a redo
			if Board.KINDS[sub] then
				local text = pos[1]
				local examples = {
					ask = 'lune run kit task ask "<the owner\'s own words>" --area ui',
					unsure = 'lune run kit task unsure "the hilt may be 10% too long - no measured ref" --on <card>',
					rework = 'lune run kit task rework "the run cycle\'s arms are stiff" --area anim',
				}
				if not text or not string.find(text, "%S") then
					return usage("task", `task {sub}: say what, in one line`, examples[sub])
				end
				-- a card id is not words (2026-11-08: four cards were titled "2u8p" / "yygy"): point at it with --on
				local bare = Board.bareId(text)
				if bare then
					return usage(
						"task",
						`task {sub}: "{bare}" is a card's id, not words - say what, and point at the card with --on {bare}`,
						examples[sub]
					)
				end
				local on = if type(flags.on) == "string" then Board.find(flags.on) else nil
				if flags.on and not on then
					return usage("task", `task {sub}: no card {flags.on}`, "lune run kit task list")
				end
				local area = flags.area or (if on then on.area else nil)
				local routedBy: { string }? = nil
				if not area then
					-- no lane given: read it from the words (a tie or no lane word stays "other")
					local guess, words = Board.guessArea(text)
					area = guess or "other"
					routedBy = if guess then words else nil
				end
				if not oneOf(area, Board.AREAS) then
					return usage("task", `task {sub}: area must be {table.concat(Board.AREAS, "|")}`, examples[sub])
				end
				local t = Board.loose(sub, text, area, if on then on.id else nil)
				t.file = Board.dir("tasks") .. `/{t.id}-{Board.slug(t.title)}.md`
				Board.note(t, me, "created")
				Board.save(t)
				if on then
					Board.note(on, me, `{Board.KINDS[sub].label} card {t.id}: {t.title}`)
					Board.save(on)
				end
				Board.journal(me, `{Board.KINDS[sub].label} {t.id} "{t.title}"`)
				-- an ask that JUDGES shown work is also the owner's words for that lane's vault (no number: never
				-- averaged, never golden; the distil and the lane's page read it)
				local filed = if sub == "ask" then fileAskWords(t, text, area) else nil
				return Run.report(
					"task",
					{},
					C.PASS,
					`task {t.id} added ({Board.KINDS[sub].label}): {t.title}{if routedBy
						then ` (routed to {area} by: {table.concat(routedBy, ", ")})`
						else ""}{if filed then ` (+ the owner's words in the {area} vault)` else ""}`,
					"carry on; it waits on the board (lune run kit task resume lists every loose end)"
				)
			end

			-- every open loose end still in "other": its lane read from its words, and the asks that judge shown work
			-- filed as the owner's words in that lane's vault; --apply writes, otherwise it only shows (2026-11-08)
			if sub == "route" then
				local apply = flags.apply == true
				local moved, filed, stay, junk = 0, 0, 0, {}
				local filedIds: { string } = {}
				for _, t in Board.tasks() do
					local kind = Board.kindOf(t)
					if kind and t.status ~= "done" then
						-- the card's whole words (its title is cut at 110 characters)
						local text = Board.looseText(t)
						if Board.bareId(text) then
							table.insert(junk, t.id)
						else
							local guess, words = Board.guessArea(text)
							if t.area == "other" then
								if guess then
									moved += 1
									print(`  {t.id} -> {guess} ({table.concat(words, ", ")}): {t.title}`)
									if apply then
										t.area = guess
										Board.note(t, me, `routed to {guess} by its words: {table.concat(words, ", ")}`)
										Board.save(t)
									end
								else
									stay += 1
								end
							end
							-- the words go to the lane they point to, whatever lane the card sits in
							if kind == "ask" and guess and Board.judgesWork(text) and Vault.KIND_OF_DEPT[guess] then
								if apply then
									if fileAskWords(t, text, guess) then
										filed += 1
										table.insert(filedIds, `{t.id}>{guess}`)
									end
								elseif not askFiled(guess, t) then
									filed += 1
									table.insert(filedIds, `{t.id}>{guess}`)
								end
							end
						end
					end
				end
				if #filedIds > 0 then
					print(`  asks that judge shown work -> the lane's vault: {table.concat(filedIds, ", ")}`)
				end
				if #junk > 0 then
					print(`  titled with a bare card id (not words; close or reword them): {table.concat(junk, ", ")}`)
				end
				return Run.report(
					"task",
					{},
					C.PASS,
					`task route: {moved} loose end(s) {if apply then "routed" else "would move"} out of "other", {stay} stay (no clear lane), {filed} judging ask(s) {if apply
						then "filed"
						else "to file"} in their lane's vault, {#junk} titled with a bare id{if apply
						then ""
						else " (nothing written)"}`,
					if apply
						then "commit board/ and kit/knowledge/vault"
						else "lune run kit task route --apply writes it"
				)
			end

			-- where was I: what this session holds, then every loose end, so a model that lost track picks up the thread
			if sub == "resume" then
				local tasks = Board.tasks()
				local harness = string.match(me, "@(.+)$") or me
				local mine, kin = {}, {}
				for _, t in tasks do
					if (t.status == "doing" or t.status == "review") and t.owner ~= "" then
						if t.owner == me then
							table.insert(mine, t)
						elseif (string.match(t.owner, "@(.+)$") or t.owner) == harness then
							table.insert(kin, t)
						end
					end
				end
				local function show(t: Board.Task, detail: boolean)
					print(`  [{t.status}]` .. line(t))
					if not detail then
						return
					end
					local open = {}
					for _, c in Board.checklist(t) do
						if not c.done then
							table.insert(open, c.text)
						end
					end
					for i = 1, math.min(3, #open) do
						print(`      to do: {open[i]}`)
					end
					local notes = {}
					for n in string.gmatch(t.body, "\n%- %d%d%d%d%-[^\n]+") do
						table.insert(notes, string.sub(n, 2))
					end
					for i = math.max(1, #notes - 1), #notes do
						print(`      last: {string.sub(notes[i], 3, 220)}`)
					end
				end
				print(`YOU HOLD ({me}):` .. (if #mine == 0 then " nothing" else ""))
				for _, t in mine do
					show(t, true)
				end
				if #kin > 0 then
					print(
						`HELD BY OTHER {harness} SESSIONS (yours before you lost track? check the notes before taking one):`
					)
					for _, t in kin do
						show(t, false)
					end
				end
				local ends = Board.looseEnds(tasks)
				local heads = {
					ask = "OWNER ASKS NOT DONE (the owner's own words; never let one drop)",
					unsure = "NOT SURE (settle with the owner or a test)",
					rework = "TO REWORK",
				}
				for _, k in Board.KIND_ORDER do
					if #ends[k] > 0 then
						print(`{heads[k]}: {#ends[k]}`)
						for _, t in ends[k] do
							local age = Board.hoursSince(t.created)
							local never = t.status == "todo" and not string.find(t.body, "claimed", 1, true)
							print(
								`  [{t.status}]{line(t)}  ({if age then math.floor(age / 24) else "?"} d{if never
									then ", never started"
									else ""})`
							)
						end
					end
				end
				local total = #ends.ask + #ends.unsure + #ends.rework
				return Run.report(
					"task",
					{},
					C.PASS,
					`task resume: you hold {#mine}; {#ends.ask} owner ask(s) open, {#ends.unsure} unsure, {#ends.rework} to rework`,
					if #mine > 0
						then `continue {mine[1].id}: lune run kit task show {mine[1].id}`
						elseif
							#ends.ask > 0
						then `the oldest owner ask: lune run kit task claim {ends.ask[1].id} --as "{me}"`
						elseif total > 0 then "claim a loose end, or: lune run kit status"
						else "lune run kit status"
				)
			end

			if sub == "sweep" then
				local swept = Board.releaseStale(Board.tasks(), me, flags.dry == true)
				for _, s in swept do
					print(`  {s.id}  {s.title}  ({s.owner}, untouched {s.hours} h)`)
				end
				if #swept > 0 and not flags.dry then
					Board.journal(me, `released {#swept} stale claim(s)`)
				end
				return Run.report(
					"task",
					{},
					C.PASS,
					if flags.dry
						then `task sweep: {#swept} claim(s) untouched over {Board.STALE_HOURS} h (dry run)`
						else `task sweep: released {#swept} stale claim(s) back to todo`,
					if #swept > 0 then "lune run kit status" else "none"
				)
			end

			local id = pos[1]
			if not sub or not id then
				return usage(
					"task",
					"task: need a subcommand and an id",
					'lune run kit task show <id>   (or: task add "title")'
				)
			end
			local t = Board.find(id)
			if not t then
				return usage("task", `task {id}: not found`, "lune run kit task list")
			end
			local task = t :: Board.Task

			if sub == "show" then
				print(fs.readFile(task.file))
				return Run.report(
					"task",
					{},
					C.PASS,
					`task {task.id}: {task.status} — {task.title}`,
					if task.status == "todo"
						then `claim it: lune run kit task claim {task.id} --as "{me}"`
						else "work it, then: lune run kit task done " .. task.id
				)
			elseif sub == "claim" then
				if task.status == "doing" and task.owner ~= me and not Board.isStale(task) and not flags.steal then
					return usage(
						"task",
						`task {task.id} is claimed by {task.owner}`,
						`pick another (kit status), or if they're gone: kit task claim {task.id} --steal --as "{me}"`
					)
				end
				if task.status == "done" or task.status == "dropped" then
					return usage("task", `task {task.id} is {task.status}`, "lune run kit status")
				end
				local prev = task.owner
				task.status = "doing"
				task.owner = me
				task.claimed_at = Board.now()
				Board.note(
					task,
					me,
					if prev ~= "" and prev ~= me then `claimed (taken over from {prev})` else "claimed"
				)
				Board.save(task)
				Board.journal(me, `claimed {task.id} "{task.title}"`)
				return Run.report(
					"task",
					{},
					C.PASS,
					`task {task.id} claimed by {me}`,
					`read it: lune run kit task show {task.id} — log progress with: kit task note {task.id} "..."`
				)
			elseif sub == "note" then
				local text = pos[2]
				if not text then
					return usage(
						"task",
						"task note: needs text",
						`lune run kit task note {task.id} "what changed / what you found"`
					)
				end
				Board.note(task, me, text)
				Board.save(task)
				return Run.report("task", {}, C.PASS, `note added to {task.id}`, "continue")
			elseif sub == "check" then
				local n = tonumber(pos[2])
				if not n or not Board.tick(task, n) then
					return usage(
						"task",
						"task check: needs the number of a Done-when item",
						`lune run kit task check {task.id} 1`
					)
				end
				Board.note(task, me, `checked done-when item {n}`)
				Board.save(task)
				return Run.report(
					"task",
					{},
					C.PASS,
					`task {task.id}: item {n} checked`,
					"next item, or: lune run kit task done " .. task.id
				)
			elseif sub == "done" or sub == "review" then
				local cl = Board.checklist(task)
				local open = 0
				for _, c in cl do
					if not c.done then
						open += 1
					end
				end
				local verify = if fs.isFile(".verify/verify.json")
					then serde.decode("json", fs.readFile(".verify/verify.json"))
					else nil
				if not flags.force then
					if open > 0 then
						return usage(
							"task",
							`task {task.id}: {open} done-when item(s) unchecked`,
							`prove each, then: kit task check {task.id} <n> (or --force with a reason note)`
						)
					end
					if task.area ~= "design" and (not verify or verify.status ~= "pass") then
						return usage(
							"task",
							"task done: last `kit verify` is not green",
							"lune run kit verify   (then mark done)"
						)
					end
				end
				task.status = sub
				Board.note(
					task,
					me,
					(if sub == "done" then "done" else "ready for review")
						.. (if flags.evidence then ": " .. flags.evidence else "")
				)
				Board.save(task)
				Board.journal(me, `{sub} {task.id} "{task.title}"`)
				return Run.report(
					"task",
					{},
					C.PASS,
					`task {task.id} → {sub}`,
					"commit your work, then: lune run kit status"
				)
			elseif sub == "block" or sub == "drop" then
				local reason = pos[2]
				if not reason then
					return usage("task", `task {sub}: needs a reason`, `lune run kit task {sub} {task.id} "why"`)
				end
				task.status = if sub == "block" then "blocked" else "dropped"
				Board.note(task, me, `{task.status}: {reason}`)
				Board.save(task)
				Board.journal(me, `{task.status} {task.id}: {reason}`)
				return Run.report("task", {}, C.PASS, `task {task.id} → {task.status}`, "lune run kit status")
			elseif sub == "release" or sub == "unblock" then
				task.status = "todo"
				task.owner = ""
				task.claimed_at = ""
				Board.note(task, me, sub .. (if pos[2] then ": " .. pos[2] else ""))
				Board.save(task)
				return Run.report("task", {}, C.PASS, `task {task.id} → todo`, "lune run kit status")
			end
			return usage("task", `task: unknown subcommand "{sub}"`, "lune run kit task list")
		end
	)

	-- ------------------------------------------------------------ handoff: the leaving model's last act
	Cli.command(
		"work",
		"handoff",
		'handoff "what I did" [--lane <dept>] [--next "..."] [--warn "..."] [--as who]',
		"END OF SESSION: write a handoff the next model reads (--lane: which department's session this was)",
		function(args)
			local pos, flags = Cli.parse(args)
			local me = Board.agent(flags.as)
			local summary = pos[1]
			if not summary then
				return usage(
					"handoff",
					"handoff: needs a summary",
					'lune run kit handoff "added dash system, tests green" --lane code --next "tune dash VFX" --warn "Studio not playtested"'
				)
			end
			local mine = {}
			local areas: { [string]: number } = {}
			for _, t in Board.tasks() do
				if t.owner == me and (t.status == "doing" or t.status == "review" or t.status == "blocked") then
					table.insert(mine, `- {t.id} [{t.status}] {t.title}`)
					areas[t.area] = (areas[t.area] or 0) + 1
				end
			end
			-- the lane this session worked in: --lane, else the one area all of its open tasks share. `kit start <dept>`
			-- shows the newest handoff of ITS lane, so the next session of that lane picks up from here
			local lane = if type(flags.lane) == "string" then Vault.dept(flags.lane) else nil
			if flags.lane ~= nil and not lane then
				return usage(
					"handoff",
					`handoff: unknown lane "{flags.lane}"`,
					'lune run kit handoff "..." --lane <3d|vfx|ui|anim|world|sfx|code|qa|kit>'
				)
			end
			if not lane then
				local only, count = nil, 0
				for a in areas do
					only, count = a, count + 1
				end
				lane = if count == 1 then Vault.dept(if only == "design" then "world" else only) else nil
			end
			-- enforced learning (board/plans/archive/2026-11-09-enforced-learning-plan.md, rules 1, 3, 4): what the session's
			-- lane owes - a verdict's lesson, a look not taken, a distil twice past due. The handoff is still WRITTEN (the
			-- session's notes are never lost) and carries the debts; the command then fails, and kit start / kit new hold
			-- the next session of the lane to them first
			local debts: { string } = {}
			local debtNext = ""
			if lane then
				for _, l in Vault.owedLines(lane) do
					table.insert(debts, l)
				end
				if #debts > 0 then
					debtNext =
						`lune run kit lesson {lane} "<what it taught>" --verdict <name> / kit verdict learned|looked <kind> <name>`
				end
				local dueN = Vault.distilDue(lane)
				if dueN and dueN >= 2 * Vault.DISTIL_EVERY then
					table.insert(
						debts,
						`the {lane} lane is {dueN} owner verdicts past its last distil (the limit is {2 * Vault.DISTIL_EVERY})`
					)
					debtNext = if debtNext ~= "" then debtNext .. "; " else ""
					debtNext ..= `lune run kit vault distil {lane}, then --rule "<rule>" or --none "<why no new rule>"`
				end
			else
				-- no lane named or found: the debts of every lane are someone's - the session says which lane is its own
				local owing = {}
				for _, d in Vault.DEPTS do
					local dueN = Vault.distilDue(d)
					if #Vault.owedLines(d) > 0 or (dueN and dueN >= 2 * Vault.DISTIL_EVERY) then
						table.insert(owing, d)
					end
				end
				if #owing > 0 then
					return Run.report(
						"handoff",
						{},
						C.USAGE,
						`handoff: name the lane this session worked in - {table.concat(owing, ", ")} owe learning (nothing written)`,
						`lune run kit handoff "{summary}" --lane <{table.concat(Vault.DEPTS, "|")}> ...`
					)
				end
			end
			local vs = verdicts()
			local gates = {}
			for i = 1, math.min(#vs, 6) do
				table.insert(gates, `- [{vs[i].status}] {vs[i].name}: {vs[i].summary or ""}`)
			end
			local nexts = flags.list.next or {}
			local warns = flags.list.warn or {}
			local text = `# Handoff — {Board.now()} — {me}\n\n## Summary\n{summary}\n`
			if lane then
				text ..= `\n## Lane\n{lane}\n`
			end
			text ..= "\n## My open tasks\n" .. (if #mine > 0 then table.concat(mine, "\n") else "- (none)") .. "\n"
			text ..= "\n## Next steps\n" .. (if #nexts > 0
				then "- " .. table.concat(nexts, "\n- ")
				else "- (see kit status)") .. "\n"
			if #warns > 0 then
				text ..= "\n## Watch out\n- " .. table.concat(warns, "\n- ") .. "\n"
			end
			if #debts > 0 then
				text ..= `\n## Owed by the {lane} lane (pay these first)\n- ` .. table.concat(debts, "\n- ") .. "\n"
			end
			text ..= "\n## Gates at handoff\n" .. (if #gates > 0 then table.concat(gates, "\n") else "- (none run)") .. "\n"
			local commit = git({ "log", "-1", "--format=%h %s" })
			if commit ~= "" then
				local dirty = git({ "status", "--porcelain" })
				text ..= `\n## Git\n- last commit: {commit}\n- uncommitted changes: {if dirty == ""
					then 0
					else #string.split(dirty, "\n")}\n`
			end
			Config.ensureDir(Board.dir("handoffs"))
			local path = Board.dir("handoffs") .. `/{Board.stamp()}-{Board.slug(me)}.md`
			fs.writeFile(path, text)
			Board.journal(me, "handoff: " .. summary)
			-- the vault's department indexes carry the last handoff (their auto block), so a model opening the
			-- folder in Obsidian sees where the project stands without the board
			if Vault.exists() then
				for _, d in Vault.DEPTS do
					if fs.isDir(Vault.dir(d)) then
						Vault.refreshIndex(d, path)
					end
				end
			end
			if #debts > 0 then
				for _, l in debts do
					print(`  {l}`)
				end
				return Run.report(
					"handoff",
					{},
					C.CONTENT,
					`handoff written: {path} - but the {lane} lane owes {#debts} thing(s) from the owner's verdicts: pay them (the next session of the lane must first)`,
					debtNext
				)
			end
			return Run.report(
				"handoff",
				{},
				C.PASS,
				"handoff written: " .. path,
				"commit board/ (and kit/knowledge/vault) with your work so the next model sees it"
			)
		end
	)

	-- ------------------------------------------------------------ decide: durable decision records
	Cli.command(
		"work",
		"decide",
		'decide "title" --decision "..." --why "..." [--rejected "..."] [--area <dept>]',
		"record a design decision (board/decisions + the vault's <dept>/decisions/)",
		function(args)
			local pos, flags = Cli.parse(args)
			local me = Board.agent(flags.as)
			local title = pos[1]
			if not title or not flags.decision or not flags.why then
				return usage(
					"decide",
					"decide: needs a title, --decision and --why",
					'lune run kit decide "Use ProfileStore for saves" --decision "..." --why "..." --rejected "DataStore2: unmaintained"'
				)
			end
			local rejected = flags.list.rejected or {}
			local text =
				`# {title}\n\n- date: {Board.today()}\n- by: {me}\n\n## Decision\n{flags.decision}\n\n## Why\n{flags.why}\n`
			if #rejected > 0 then
				text ..= "\n## Rejected\n- " .. table.concat(rejected, "\n- ") .. "\n"
			end
			Config.ensureDir(Board.dir("decisions"))
			local path = Board.dir("decisions") .. `/{Board.stamp()}-{Board.slug(title)}.md`
			fs.writeFile(path, text)
			Board.journal(me, "decided: " .. title)
			-- the same decision as a vault note (<dept>/decisions/), so the department page's folder holds it:
			-- --area names the department (default kit; a game-design choice: --area code)
			local noted = ""
			if Vault.exists() then
				local dept = Vault.dept(if type(flags.area) == "string" then flags.area else "kit") or "kit"
				local body = `## Decision\n{flags.decision}\n\n## Why\n{flags.why}\n`
				if #rejected > 0 then
					body ..= "\n## Rejected\n- " .. table.concat(rejected, "\n- ") .. "\n"
				end
				local note = Vault.note(dept, "decisions", `{Board.today()}-{Board.slug(title)}`, {
					kind = "decision",
					area = dept,
					name = title,
					by = me,
					source = "kit decide",
					board = path,
				}, body)
				noted = ` + {note}`
			end
			return Run.report("decide", {}, C.PASS, "decision recorded: " .. path .. noted, "none — proceed")
		end
	)

	Cli.command("work", "log", 'log "message" [--as who]', "one-line entry in today's journal", function(args)
		local pos, flags = Cli.parse(args)
		if not pos[1] then
			return usage("log", "log: needs a message", 'lune run kit log "found that X"')
		end
		Board.journal(Board.agent(flags.as), pos[1])
		return Run.report("log", {}, C.PASS, "logged", "none — proceed")
	end)
end

-- boardweb.luau — the data behind `kit board` (the owner, 2026-10-28: "our own version of Trello ... even better ... when
-- I'm working on a game we launch and start using it"). Every board the project has — the project root's board/ and
-- each games/<Name>/board/ — read from the SAME markdown task files the CLI and every model write (kit/lib/board.luau),
-- so the web board, `kit task` and a model editing a file by hand are one source of truth. Better than a Trello card:
-- each card knows the pipeline — its claim and how stale it is, what it waits on, its done-when progress, and the
-- pieces it names (a 3D asset, an effect, a screen, a world, a sound, a move) with their preview and the owner's last
-- verdict. Writes (move, check, note, new card, priority) go through Board.parse / serialize / note and record the
-- owner as who did it; the same rules as the CLI hold (a reason to block, drop, or close with open done-when items).
local fs = require("@lune/fs")
local net = require("@lune/net")
local process = require("@lune/process")
local scheduler = require("@lune/task")
local serde = require("@lune/serde")

local Board = require("./board")
local Config = require("./config")
local Vault = require("./vault")

local BoardWeb = {}

BoardWeb.WHO = "owner (board)"
BoardWeb.MAX_TEXT = 2000
BoardWeb.ROOT = "" -- the project folder every path below hangs off (a spec points it at a fixture)

export type BoardRef = { key: string, name: string, base: string, dir: string }

local function path(rel: string): string
	return BoardWeb.ROOT .. rel
end

-- the project root's board and every game's: { key, name, base (the content root: "" or "games/<Name>/"), dir }
function BoardWeb.boards(): { BoardRef }
	local out: { BoardRef } = {}
	local name = "Project"
	-- (parallax.config.json first, kit.config.json the fallback: PARALLAX spec §5.1 8)
	local cfgFile = if fs.isFile(path("parallax.config.json")) then "parallax.config.json" else "kit.config.json"
	if fs.isFile(path(cfgFile)) then
		local ok, cfg = pcall(serde.decode, "json" :: any, fs.readFile(path(cfgFile)))
		if ok and type(cfg) == "table" and type(cfg.name) == "string" then
			name = cfg.name
		end
	end
	if fs.isDir(path("board/tasks")) then
		table.insert(out, { key = "root", name = name, base = "", dir = "board" })
	end
	if fs.isDir(path("games")) then
		local games = fs.readDir(path("games"))
		table.sort(games)
		for _, g in games do
			if string.match(g, "^[%w_%-]+$") and fs.isDir(path(`games/{g}/board`)) then
				table.insert(out, { key = g, name = g, base = `games/{g}/`, dir = `games/{g}/board` })
			end
		end
	end
	return out
end

function BoardWeb.board(key: string?): BoardRef?
	for _, b in BoardWeb.boards() do
		if b.key == key then
			return b
		end
	end
	return nil
end

local function taskFiles(b: BoardRef): { string }
	local dir = path(b.dir .. "/tasks")
	local out = {}
	if fs.isDir(dir) then
		for _, n in fs.readDir(dir) do
			if string.sub(n, -3) == ".md" then
				table.insert(out, dir .. "/" .. n)
			end
		end
	end
	table.sort(out)
	return out
end

function BoardWeb.tasks(b: BoardRef): { Board.Task }
	local out = {}
	for _, p in taskFiles(b) do
		local t = Board.parse(fs.readFile(p), p)
		if t and t.id ~= "" then
			table.insert(out, t)
		end
	end
	return out
end

local function find(b: BoardRef, id: string): Board.Task?
	for _, t in BoardWeb.tasks(b) do
		if t.id == id then
			return t
		end
	end
	return nil
end

-- a change stamp for one board (the page polls it: a model's edit shows up without a reload)
function BoardWeb.stamp(b: BoardRef): string
	local files = taskFiles(b)
	local sum = 0
	for _, p in files do
		local ok, meta = pcall(fs.metadata, p)
		if ok and meta.modifiedAt then
			sum += meta.modifiedAt.unixTimestamp
		end
	end
	return `{#files}:{sum}`
end

-- ------------------------------------------------------------ reading a card
local function section(body: string, title: string): string
	local text = string.gsub(body, "\r\n", "\n") .. "\n## "
	local s = string.match(text, "## " .. title .. "%s*\n(.-)\n## ")
	return string.gsub(string.gsub(s or "", "^%s+", ""), "%s+$", "")
end

local function notes(body: string): { any }
	local out = {}
	for at, who, text in string.gmatch(section(body, "Notes") .. "\n", "%- (%S+) %*%*(.-)%*%*: ([^\n]*)\n") do
		table.insert(out, { at = at, who = who, text = text })
	end
	return out
end

-- the pieces a project holds, by lowercased name: { kind, name, dept, preview? } (built once per read)
local KINDS = {
	{ kind = "asset", dept = "3d", dir = "assets/models", pattern = "^build_(.+)%.py$" },
	{ kind = "vfx", dept = "vfx", dir = "assets/effects", pattern = "^([^_].*)%.json$" },
	{ kind = "screen", dept = "ui", dir = "assets/ui", pattern = "^([^_].*)%.json$" },
	{ kind = "world", dept = "world", dir = "assets/worlds", pattern = "^([^_].*)%.json$" },
	{ kind = "sound", dept = "sfx", dir = "assets/sounds", pattern = "^([^_].*)%.json$" },
	{ kind = "anim", dept = "anim", dir = "assets/animations/dossiers", pattern = "^(.+)%.json$" },
}

local function pieces(b: BoardRef): { [string]: { any } }
	local index: { [string]: { any } } = {}
	for _, k in KINDS do
		local dir = path(b.base .. k.dir)
		if fs.isDir(dir) then
			for _, f in fs.readDir(dir) do
				local n = string.match(f, k.pattern)
				if n and #n >= 4 then
					local key = string.lower(n)
					index[key] = index[key] or {}
					local preview = if k.kind == "asset" then `{b.base}build/renders/{n}.png` else nil
					table.insert(index[key], {
						kind = k.kind,
						dept = k.dept,
						name = n,
						preview = if preview and fs.isFile(path(preview)) then preview else nil,
					})
				end
			end
		end
	end
	return index
end

-- the owner's newest verdict per (dept, name), read once per board read
local function verdictsFor(depts: { [string]: boolean }): { [string]: any }
	local out = {}
	if not Vault.exists() then
		return out
	end
	for dept in depts do
		for _, v in Vault.verdicts(dept) do -- newest first
			local n = string.lower(tostring(v.front.name or ""))
			local key = `{dept}|{n}`
			-- a number or the owner's Keep / Redo (said: "8/10", "Keep", "Redo"; low: a rejection either way)
			if n ~= "" and out[key] == nil and Vault.ownersOwn(v.front) and Vault.polarity(v.front) ~= nil then
				out[key] = {
					score = tonumber(v.front.score),
					said = Vault.said(v.front),
					low = Vault.polarity(v.front) == -1,
					date = v.front.date,
					words = string.sub(v.body, 1, 160),
				}
			end
		end
	end
	return out
end

local function related(t: Board.Task, index: { [string]: { any } }): { any }
	local out, seen = {}, {}
	local text = t.title .. " " .. table.concat(t.labels, " ") .. " " .. section(t.body, "Goal")
	for word in string.gmatch(text, "[%w_]+") do
		local hits = index[string.lower(word)]
		if hits and not seen[string.lower(word)] then
			seen[string.lower(word)] = true
			for _, h in hits do
				table.insert(out, h)
			end
		end
	end
	return out
end

-- one task as the page's card
function BoardWeb.card(t: Board.Task, byId: { [string]: Board.Task }, index: { [string]: { any } }): any
	local items = Board.checklist(t)
	local done = 0
	for _, c in items do
		if c.done then
			done += 1
		end
	end
	local waiting = {}
	for _, dep in t.depends do
		local d = byId[dep]
		if d and d.status ~= "done" and d.status ~= "dropped" then
			table.insert(waiting, { id = d.id, title = d.title, status = d.status })
		end
	end
	local since = if t.status == "doing"
		then Board.hoursSince(if t.updated ~= "" then t.updated else t.claimed_at)
		else nil
	return {
		id = t.id,
		title = t.title,
		status = if table.find(Board.STATUSES, t.status) then t.status else "todo",
		rawStatus = t.status,
		priority = t.priority,
		area = t.area,
		owner = t.owner,
		claimed_at = t.claimed_at,
		created = t.created,
		updated = t.updated,
		depends = t.depends,
		labels = t.labels,
		kind = Board.kindOf(t),
		stale = Board.isStale(t),
		hours = since,
		goal = section(t.body, "Goal"),
		items = items,
		done = done,
		total = #items,
		notes = notes(t.body),
		waiting = waiting,
		related = related(t, index),
	}
end

local function brief(b: BoardRef): any
	local p = path(b.dir .. "/BRIEF.md")
	if not fs.isFile(p) then
		return nil
	end
	local text = fs.readFile(p)
	return {
		title = string.match(text, "#%s*([^\n]+)"),
		milestone = string.match(text, "[Mm]ilestone[^\n]*:%s*([^\n]+)")
			or string.match(text, "##%s*[Mm]ilestone[^\n]*\n+([^\n]+)"),
	}
end

-- everything the page shows for one board
function BoardWeb.read(b: BoardRef): any
	local list = BoardWeb.tasks(b)
	local byId = {}
	for _, t in list do
		byId[t.id] = t
	end
	local index = pieces(b)
	local cards, depts = {}, {}
	for _, t in list do
		local c = BoardWeb.card(t, byId, index)
		for _, r in c.related do
			depts[r.dept] = true
		end
		table.insert(cards, c)
	end
	local verdicts = verdictsFor(depts)
	for _, c in cards do
		for _, r in c.related do
			r.verdict = verdicts[`{r.dept}|{string.lower(r.name)}`]
		end
	end
	return { key = b.key, name = b.name, brief = brief(b), stamp = BoardWeb.stamp(b), tasks = cards }
end

-- ------------------------------------------------------------ writing (the owner, from the page)
local function clean(s: any, max: number?): string?
	if type(s) ~= "string" then
		return nil
	end
	s = string.gsub(string.gsub(s, "[%c]+", " "), "^%s+", "")
	s = string.gsub(s, "%s+$", "")
	if s == "" then
		return nil
	end
	return string.sub(s, 1, max or BoardWeb.MAX_TEXT)
end

local function setItem(t: Board.Task, index: number, done: boolean): boolean
	local n, changed = 0, false
	t.body = string.gsub(t.body, "%- %[([ xX])%] ([^\n]+)", function(mark, text)
		n += 1
		if n == index then
			changed = true
			return (if done then "- [x] " else "- [ ] ") .. text
		end
		return "- [" .. mark .. "] " .. text
	end)
	return changed
end

local function newId(b: BoardRef): string
	for _ = 1, 50 do
		local id = Board.newId()
		if not find(b, id) then
			return id
		end
	end
	error("could not allocate a task id")
end

-- apply one action -> (ok, message, card id?)
function BoardWeb.act(b: BoardRef, a: any): (boolean, string, string?)
	if type(a) ~= "table" or type(a.action) ~= "string" then
		return false, "no action"
	end
	if a.action == "create" then
		local title = clean(a.title, 120)
		if not title then
			return false, "a new card needs a title"
		end
		local area = if type(a.area) == "string" and table.find(Board.AREAS, a.area) then a.area else "other"
		-- a loose end (the owner's ask, a doubt, a redo): its kind's label, goal and done-when
		if type(a.kind) == "string" and Board.KINDS[a.kind] then
			local t = Board.loose(a.kind, clean(a.goal, 2000) or title, area)
			t.id = newId(b)
			t.title = title
			if type(a.priority) == "string" and string.match(a.priority, "^p[0-3]$") then
				t.priority = a.priority
			end
			t.file = path(`{b.dir}/tasks/{t.id}-{Board.slug(title)}.md`)
			Board.note(t, BoardWeb.WHO, "created")
			Board.save(t)
			return true, `created {t.id} ({Board.KINDS[a.kind].label})`, t.id
		end
		local prio = if type(a.priority) == "string" and string.match(a.priority, "^p[0-3]$") then a.priority else "p2"
		local id = newId(b)
		local lines = { "", "## Goal", clean(a.goal) or title, "", "## Done when" }
		local any = false
		if type(a.done) == "table" then
			for _, d in a.done do
				local item = clean(d, 300)
				if item then
					table.insert(lines, "- [ ] " .. item)
					any = true
				end
			end
		end
		if not any then
			table.insert(lines, "- [ ] " .. title)
		end
		local t: any = {
			id = id,
			title = title,
			status = "todo",
			priority = prio,
			area = area,
			owner = "",
			claimed_at = "",
			created = Board.now(),
			updated = "",
			depends = {},
			labels = {},
			body = table.concat(lines, "\n") .. "\n",
			file = path(`{b.dir}/tasks/{id}-{Board.slug(title)}.md`),
		}
		Board.note(t, BoardWeb.WHO, "created")
		Board.save(t)
		return true, `created {id}`, id
	end
	if a.action == "sweep" then
		local swept = Board.releaseStale(BoardWeb.tasks(b), BoardWeb.WHO)
		return true, `released {#swept} stale claim(s)`
	end
	local id = if type(a.id) == "string" then string.lower(a.id) else ""
	if not string.match(id, "^[%w]+$") or #id > 12 then
		return false, "a card id"
	end
	local t = find(b, id)
	if not t then
		return false, `no card {id} on {b.name}`
	end
	local task = t :: Board.Task
	if a.action == "move" then
		local to = a.status
		if type(to) ~= "string" or not table.find(Board.STATUSES, to) then
			return false, "unknown column"
		end
		local reason = clean(a.reason, 500)
		if (to == "blocked" or to == "dropped") and not reason then
			return false, `{to} needs a reason`
		end
		if to == "done" or to == "review" then
			local open = 0
			for _, c in Board.checklist(task) do
				if not c.done then
					open += 1
				end
			end
			if open > 0 and not reason then
				return false, `{open} done-when item(s) still open: give a reason to close it anyway`
			end
		end
		local from = task.status
		task.status = to
		if to == "todo" then
			task.owner, task.claimed_at = "", ""
		elseif to == "doing" and from ~= "doing" then
			task.owner, task.claimed_at = BoardWeb.WHO, Board.now()
		end
		Board.note(task, BoardWeb.WHO, `moved {from} -> {to}` .. (if reason then `: {reason}` else ""))
		Board.save(task)
		return true, `{id}: {from} -> {to}`, id
	elseif a.action == "check" then
		local n = tonumber(a.n)
		if not n or not setItem(task, math.floor(n), a.done ~= false) then
			return false, "no such done-when item"
		end
		Board.note(
			task,
			BoardWeb.WHO,
			`{if a.done ~= false then "checked" else "unchecked"} done-when item {math.floor(n)}`
		)
		Board.save(task)
		return true, `{id}: item {math.floor(n)}`, id
	elseif a.action == "note" then
		local text = clean(a.text)
		if not text then
			return false, "an empty note"
		end
		Board.note(task, BoardWeb.WHO, text)
		Board.save(task)
		return true, `{id}: note added`, id
	elseif a.action == "priority" then
		if type(a.priority) ~= "string" or not string.match(a.priority, "^p[0-3]$") then
			return false, "priority is p0..p3"
		end
		task.priority = a.priority
		Board.note(task, BoardWeb.WHO, `priority -> {a.priority}`)
		Board.save(task)
		return true, `{id}: {a.priority}`, id
	end
	return false, `unknown action {a.action}`
end

-- ------------------------------------------------------------ the board in the background
-- (the owner, 2026-10-28: "when I open a session and I'm working on a game, we launch and start using it"): kit start
-- and kit game use make sure the board is serving; it runs hidden, one per machine, and outlives the session that
-- started it. build/board.json holds { port, pid } of the one this started, so `kit board stop` can end it.
BoardWeb.PORT = 8790
BoardWeb.STATE = "build/board.json"

-- is a kit board answering on this port?
function BoardWeb.running(port: number): boolean
	local ok, res = pcall(net.request, { url = `http://127.0.0.1:{port}/api/boards`, method = "GET" } :: any)
	if not ok or not res.ok then
		return false
	end
	local okJ, data = pcall(serde.decode, "json" :: any, res.body)
	return okJ and type(data) == "table" and type(data.boards) == "table"
end

-- off when the owner said so (KIT_NO_BOARD=1 or kit.config.json "board_auto": false) or in CI
function BoardWeb.autoOff(cfg: any): string?
	if (process.env.KIT_NO_BOARD or "") ~= "" and process.env.KIT_NO_BOARD ~= "0" then
		return "KIT_NO_BOARD is set"
	end
	if (process.env.CI or "") ~= "" then
		return "CI"
	end
	if type(cfg) == "table" and cfg.board_auto == false then
		return 'kit.config.json "board_auto": false'
	end
	return nil
end

local function openBrowser(url: string)
	if process.os == "windows" then
		pcall(process.exec, "cmd", { "/c", "start", "", url })
	elseif process.os == "macos" then
		pcall(process.exec, "open", { url })
	else
		pcall(process.exec, "xdg-open", { url })
	end
end

-- the board's url, serving it in the background first when nothing answers (and then opening it in the browser,
-- once: a session's later kit start finds it running and only names the url) -> (url?, "running"|"started"|why)
function BoardWeb.ensure(game: string?, cfg: any): (string?, string)
	local off = BoardWeb.autoOff(cfg)
	if off then
		return nil, `off ({off})`
	end
	if #BoardWeb.boards() == 0 then
		return nil, "no board here"
	end
	local port = BoardWeb.PORT
	local url = `http://127.0.0.1:{port}/` .. (if game then `?board={game}` else "")
	if BoardWeb.running(port) then
		return url, "running"
	end
	local lune = process.env.LUNE or "lune"
	local pid = ""
	if process.os == "windows" then
		fs.writeDir("build")
		-- through WMI, not Start-Process: lune runs under rokit's shim, whose job object kills every process this one
		-- starts when it exits (the board died with kit start); WMI's service creates it outside that job, with no
		-- window and none of this call's pipes. cmd writes the log; its pid is the tree `kit board stop` ends
		local cmd = string.format(
			"$si = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0}; "
				.. "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{"
				.. 'CommandLine=\'cmd /c ""%s" run kit board --no-open --port %d > build\\board.log 2>&1"\'; '
				.. "CurrentDirectory='%s'; ProcessStartupInformation=$si}; "
				.. "if ($r.ReturnValue -ne 0) { exit 1 }; $r.ProcessId",
			(string.gsub(lune, "'", "''")),
			port,
			(string.gsub(process.cwd, "'", "''"))
		)
		local ok, r = pcall(process.exec, "powershell", { "-NoProfile", "-NonInteractive", "-Command", cmd })
		if not ok or not r.ok then
			return nil, "could not start it: " .. (if ok then string.sub(r.stderr, 1, 200) else tostring(r))
		end
		pid = string.match(r.stdout, "%d+") or ""
	else
		fs.writeDir("build")
		local ok, r = pcall(process.exec, "sh", {
			"-c",
			`nohup "{lune}" run kit board --no-open --port {port} > build/board.log 2>&1 & echo $!`,
		})
		if not ok or not r.ok then
			return nil, "could not start it"
		end
		pid = string.match(r.stdout, "%d+") or ""
	end
	-- it answers within a second or two; a slow first start still serves, the url is right either way
	local up = false
	for _ = 1, 40 do
		if BoardWeb.running(port) then
			up = true
			break
		end
		scheduler.wait(0.25)
	end
	if not up then
		return nil, "it did not answer within 10 s (read build/board.log)"
	end
	pcall(fs.writeFile, BoardWeb.STATE, serde.encode("json", { port = port, pid = tonumber(pid) or 0 }))
	openBrowser(url)
	return url, "started"
end

-- a session arriving (kit start, kit game use): the board in scope sheds its stale claims, then the board is up ->
-- the lines to print
function BoardWeb.arrive(who: string): { string }
	local lines = {}
	local swept = Board.releaseStale(Board.tasks(), who)
	if #swept > 0 then
		local ids = {}
		for _, s in swept do
			table.insert(ids, `{s.id} ({s.owner}, {s.hours} h)`)
		end
		table.insert(
			lines,
			`-- released {#swept} stale claim(s) back to To do (untouched over {Board.STALE_HOURS} h): {table.concat(
				ids,
				", "
			)}`
		)
	end
	local okC, cfg = pcall(Config.load)
	local url, state = BoardWeb.ensure(Config.game(), if okC then cfg else nil)
	if url then
		table.insert(
			lines,
			`-- the board: {url}{if state == "started"
				then "  (started in the background and opened; kit board stop ends it)"
				else ""}`
		)
	elseif not string.find(state, "^off") and state ~= "no board here" then
		table.insert(lines, `-- the board did not start: {state}`)
	end
	return lines
end

-- end the background board this machine started -> (ok, message)
function BoardWeb.stop(): (boolean, string)
	if not fs.isFile(BoardWeb.STATE) then
		return false, "no background board recorded (one started by hand stops with Ctrl+C in its window)"
	end
	local ok, st = pcall(serde.decode, "json" :: any, fs.readFile(BoardWeb.STATE))
	local pid = if ok and type(st) == "table" then tonumber(st.pid) else nil
	pcall(fs.removeFile, BoardWeb.STATE)
	if not pid or pid <= 0 then
		return false, "the record has no process id"
	end
	local r
	if process.os == "windows" then
		ok, r = pcall(process.exec, "taskkill", { "/PID", tostring(pid), "/T", "/F" })
	else
		ok, r = pcall(process.exec, "kill", { tostring(pid) })
	end
	return ok and r.ok, if ok and r.ok then `stopped the board (pid {pid})` else `pid {pid} was not running`
end

return BoardWeb

-- board.luau — the shared work board. Plain markdown in board/ so ANY model in ANY harness can read/write it,
-- with or without this CLI, and git merges it like code.
--   board/BRIEF.md                    what the game is + current milestone (read first)
--   board/tasks/<id>-<slug>.md        one task per file: frontmatter + Goal / Done when / Notes
--   board/handoffs/<stamp>-<who>.md   end-of-session handoffs (newest = what the next model reads)
--   board/decisions/<stamp>-<slug>.md decision records (decision / why / rejected)
--   board/journal/<date>.md           dated one-line log
-- Task file frontmatter (between --- lines), one `key: value` per line, lists as [a, b]:
--   id, title, status (todo|doing|blocked|review|done|dropped), priority (p0..p3), area, owner,
--   claimed_at, created, updated, depends, labels
local DateTime = require("@lune/datetime")
local fs = require("@lune/fs")
local process = require("@lune/process")

local Config = require("./config")

local Board = {}

Board.STATUSES = { "todo", "doing", "blocked", "review", "done", "dropped" }
Board.AREAS = { "code", "3d", "vfx", "sfx", "ui", "qa", "anim", "world", "kit", "design", "other" }
Board.STALE_HOURS = 24
local FIELDS =
	{ "id", "title", "status", "priority", "area", "owner", "claimed_at", "created", "updated", "depends", "labels" }
local LISTS = { depends = true, labels = true }

export type Task = {
	id: string,
	title: string,
	status: string,
	priority: string,
	area: string,
	owner: string,
	claimed_at: string,
	created: string,
	updated: string,
	depends: { string },
	labels: { string },
	body: string,
	file: string,
}

function Board.dir(sub: string?): string
	local root = Config.path("board")
	return if sub then root .. "/" .. sub else root
end

function Board.now(): string
	-- second precision, UTC: 2026-10-04T07:12:33Z (readable, sortable, parseable by DateTime.fromIsoDate)
	return string.sub(DateTime.now():toIsoDate(), 1, 19) .. "Z"
end

function Board.today(): string
	return string.sub(Board.now(), 1, 10)
end

function Board.hoursSince(iso: string): number?
	if iso == nil or iso == "" then
		return nil
	end
	local ok, t = pcall(DateTime.fromIsoDate, iso)
	if not ok then
		return nil
	end
	return (DateTime.now().unixTimestamp - t.unixTimestamp) / 3600
end

-- Who is acting. Pass --as "<model>@<harness>" (e.g. "sonnet-4.6@claude-code"); env KIT_AGENT also works.
function Board.agent(flagValue: string?): string
	if flagValue and flagValue ~= "" then
		return flagValue
	end
	local env = process.env
	if env.KIT_AGENT and env.KIT_AGENT ~= "" then
		return env.KIT_AGENT
	end
	if env.CLAUDECODE then
		return "claude-code"
	end
	if env.CODEX_SANDBOX or env.CODEX_HOME then
		return "codex"
	end
	if env.CURSOR_TRACE_ID then
		return "cursor"
	end
	if env.GEMINI_CLI then
		return "gemini-cli"
	end
	return "agent"
end

function Board.slug(text: string): string
	local s = string.lower(text)
	s = string.gsub(s, "[^%w]+", "-")
	s = string.gsub(s, "^-+", "")
	s = string.gsub(s, "-+$", "")
	return string.sub(s, 1, 40)
end

local ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789" -- no 0/o/1/l/i: easy to read back and type
function Board.newId(): string
	-- math.randomseed proved unreliable here (two sessions produced identical ids), so hash real entropy instead:
	-- wall-clock ms + CPU clock + a heap address (differs per process) through FNV-1a, then base-31 digits.
	local seed = `{DateTime.now().unixTimestampMillis}|{os.clock()}|{tostring({})}`
	for attempt = 1, 50 do
		local h = 2166136261
		for i = 1, #seed do
			h = bit32.bxor(h, string.byte(seed, i))
			h = (h * 16777619) % 4294967296
		end
		h = bit32.bxor(h, attempt * 2654435761 % 4294967296)
		local id = ""
		for _ = 1, 4 do
			local k = h % #ALPHABET
			h = (h - k) // #ALPHABET
			id ..= string.sub(ALPHABET, k + 1, k + 1)
		end
		if not Board.find(id) then
			return id
		end
	end
	error("could not allocate a task id")
end

-- ---------------------------------------------------------------- parse / write
local function parseValue(key: string, raw: string): any
	raw = string.gsub(raw, "^%s+", "")
	raw = string.gsub(raw, "%s+$", "")
	if LISTS[key] then
		local inner = string.match(raw, "^%[(.*)%]$") or raw
		local out = {}
		for item in string.gmatch(inner, "[^,]+") do
			item = string.gsub(string.gsub(item, "^%s+", ""), "%s+$", "")
			item = string.gsub(item, '^"(.*)"$', "%1")
			if item ~= "" then
				table.insert(out, item)
			end
		end
		return out
	end
	return (string.gsub(raw, '^"(.*)"$', "%1"))
end

function Board.parse(text: string, file: string): Task?
	text = string.gsub(text, "\r\n", "\n")
	local head, body = string.match(text, "^%-%-%-\n(.-)\n%-%-%-\n?(.*)$")
	if not head then
		return nil
	end
	local t: any = { body = body or "", file = file, depends = {}, labels = {} }
	for line in string.gmatch(head .. "\n", "([^\n]*)\n") do
		local key, value = string.match(line, "^([%w_]+):%s*(.*)$")
		if key then
			t[key] = parseValue(key, value)
		end
	end
	for _, f in FIELDS do
		if t[f] == nil then
			t[f] = if LISTS[f] then {} else ""
		end
	end
	return t
end

function Board.serialize(t: Task): string
	local lines = { "---" }
	for _, f in FIELDS do
		local v: any = (t :: any)[f]
		if LISTS[f] then
			table.insert(lines, `{f}: [{table.concat(v or {}, ", ")}]`)
		else
			local s = tostring(v or "")
			if string.find(s, ":") or string.find(s, "#") then
				s = '"' .. string.gsub(s, '"', "'") .. '"'
			end
			table.insert(lines, `{f}: {s}`)
		end
	end
	table.insert(lines, "---")
	return table.concat(lines, "\n") .. "\n" .. t.body
end

function Board.tasks(): { Task }
	local dir = Board.dir("tasks")
	local out = {}
	if not fs.isDir(dir) then
		return out
	end
	for _, name in fs.readDir(dir) do
		if string.sub(name, -3) == ".md" then
			local path = dir .. "/" .. name
			local t = Board.parse(fs.readFile(path), path)
			if t and t.id ~= "" then
				table.insert(out, t)
			end
		end
	end
	table.sort(out, function(a, b)
		if a.priority ~= b.priority then
			return a.priority < b.priority
		end
		return a.created < b.created
	end)
	return out
end

function Board.find(id: string): Task?
	id = string.lower(id)
	for _, t in Board.tasks() do
		if t.id == id then
			return t
		end
	end
	return nil
end

function Board.save(t: Task)
	t.updated = Board.now()
	Config.ensureDir(Board.dir("tasks"))
	fs.writeFile(t.file, Board.serialize(t))
end

function Board.note(t: Task, who: string, text: string)
	local line = `- {Board.now()} **{who}**: {text}`
	if string.find(t.body, "## Notes", 1, true) then
		t.body = string.gsub(t.body, "%s*$", "") .. "\n" .. line .. "\n"
	else
		t.body = string.gsub(t.body, "%s*$", "") .. "\n\n## Notes\n" .. line .. "\n"
	end
end

-- Done-when checklist items: "- [ ] text" / "- [x] text"
function Board.checklist(t: Task): { { done: boolean, text: string } }
	local out = {}
	for mark, text in string.gmatch(t.body, "%- %[([ xX])%] ([^\n]+)") do
		table.insert(out, { done = mark ~= " ", text = text })
	end
	return out
end

function Board.tick(t: Task, index: number): boolean
	local n = 0
	local changed = false
	t.body = string.gsub(t.body, "%- %[([ xX])%] ([^\n]+)", function(mark, text)
		n += 1
		if n == index then
			changed = true
			return "- [x] " .. text
		end
		return "- [" .. mark .. "] " .. text
	end)
	return changed
end

function Board.ready(t: Task, byId: { [string]: Task }): boolean
	if t.status ~= "todo" then
		return false
	end
	for _, dep in t.depends do
		local d = byId[dep]
		if d and d.status ~= "done" and d.status ~= "dropped" then
			return false
		end
	end
	return true
end

function Board.isStale(t: Task): boolean
	if t.status ~= "doing" then
		return false
	end
	local h = Board.hoursSince(if t.updated ~= "" then t.updated else t.claimed_at)
	return h ~= nil and h > Board.STALE_HOURS
end

-- a claim nobody has touched for a day holds a card hostage (39 of 131 on 2026-10-28): put each back in To do, the
-- holder and how long it sat named in a note, so the next session can pick it up and the holder sees why on return.
-- dry = only list them. -> { { id, title, owner, hours } }
function Board.releaseStale(tasks: { Task }, who: string, dry: boolean?): { any }
	local out = {}
	for _, t in tasks do
		if Board.isStale(t) then
			local h = math.floor(Board.hoursSince(if t.updated ~= "" then t.updated else t.claimed_at) or 0)
			table.insert(out, { id = t.id, title = t.title, owner = t.owner, hours = h })
			if not dry then
				local holder = if t.owner ~= "" then t.owner else "nobody"
				t.status, t.owner, t.claimed_at = "todo", "", ""
				Board.note(t, who, `released a stale claim: {holder} left it untouched {h} h`)
				Board.save(t)
			end
		end
	end
	return out
end

-- the loose ends a model writes down the moment they appear, so a session that ends, forgets or loses track can find
-- them again (the owner, 2026-10-28: "if it ever loses track it can go back ... things it's not 100% sure of, things it
-- thinks should be reworked, or things I mentioned should be reworked that it never worked on"). Each is a card with a
-- label: the owner's words, a doubt, a redo.
Board.KINDS = {
	ask = {
		label = "owner-ask",
		priority = "p1",
		goal = 'The owner asked: "%s"',
		done = "done the way the owner asked, and shown to the owner",
	},
	unsure = {
		label = "unsure",
		priority = "p2",
		goal = "Not sure: %s",
		done = "settled: the owner answered or a test proved it, and the answer is in a note",
	},
	rework = {
		label = "rework",
		priority = "p2",
		goal = "Should be reworked: %s",
		done = "redone, and checked against what was wrong",
	},
}
Board.KIND_ORDER = { "ask", "unsure", "rework" }

-- which lane a loose end belongs to, read from its words (2026-11-08: 28 of 45 owner asks sat in "other", where no
-- lane looks). Plain words per lane, counted once each; the lane with the most wins only when it is ahead of the
-- next - a tie, or no word at all, stays "other" (a wrong guess hides an ask; "other" at least shows it as unrouted).
Board.AREA_WORDS = {
	world = {
		"city",
		"town",
		"building",
		"terrain",
		"open world",
		"house",
		"district",
		"region",
		"kingdom",
		"forest",
		"river",
		"cave",
		"dungeon",
		"island",
		"climb",
		"street",
		"the ground",
	},
	anim = {
		"animation",
		"animate",
		"slash",
		"swing",
		"pose",
		"legs",
		"arms",
		"twirl",
		"combo",
		"moveset",
		"walking",
		"running",
		"stance",
		"footwork",
	},
	vfx = { "vfx", "effect", "particle", "bullet hole", "blood", "aura", "explosion", "smoke", "impact frame" },
	ui = { "ui", "menu", "hud", "button", "settings", "font", "icon", "banner", "logo" },
	sfx = { "sound", "sfx", "audio", "music", "voice", "ambience" },
	code = {
		"bug",
		"script",
		"camera",
		"aiming",
		"auto-lock",
		"lock-on",
		"hitbox",
		"server",
		"m1",
		"spam",
		"spamming",
		"mechanic",
		"first person",
		"pov",
		"head movement",
		"push-up",
	},
	["3d"] = {
		"3d",
		"model",
		"mesh",
		"texture",
		"clothes",
		"clothing",
		"outfit",
		"boots",
		"pants",
		"collar",
		"zipper",
		"armour",
		"armor",
		"fitting",
	},
}

-- a word or phrase standing alone in the text: "lame" is not "flame", "arms" not "firearms", "script" not
-- "description" (the 2026-11-08 review); a plural or an -es ending still counts ("buildings", "slashes")
function Board.hasWord(low: string, token: string): boolean
	local esc = string.gsub(token, "[%^%$%(%)%%%.%[%]%*%+%-%?]", "%%%0")
	local first, last = string.sub(token, 1, 1), string.sub(token, -1)
	local pre = if string.match(first, "%w") then "%f[%w]" else ""
	local post = if string.match(last, "%w") then "e?s?%f[%W]" else ""
	return string.find(low, pre .. esc .. post) ~= nil
end

function Board.guessArea(text: string): (string?, { string })
	local low = " " .. string.lower(text) .. " "
	local best, bestN, second = nil, 0, 0
	local why: { [string]: { string } } = {}
	for area, words in Board.AREA_WORDS do
		local hits = {}
		for _, w in words do
			if Board.hasWord(low, w) then
				table.insert(hits, w)
			end
		end
		why[area] = hits
		if #hits > bestN then
			second, best, bestN = bestN, area, #hits
		elseif #hits > second then
			second = #hits
		end
	end
	if not best or bestN == second then
		return nil, {}
	end
	return best, why[best]
end

-- does an ask JUDGE work that was shown (rather than only ask for something)? Then the owner's words are also a
-- verdict-like note for that lane's vault - "the city looks horrible" was filed as a task and never reached it.
Board.JUDGING_WORDS = {
	"horrible",
	"trash",
	"so bad",
	"all bad",
	"looks bad",
	"look bad",
	"looks weird",
	"looks dumb",
	"looks off",
	"looks wrong",
	"looks ugly",
	"looks good",
	"looks great",
	"looks amazing",
	"looks nice",
	"looks lame",
	"look nice",
	"ugly",
	"isnt correct",
	"isn't correct",
	"not correct",
	"glitch",
	"glitching",
	"dumb",
	"weird",
	"lame",
	"love it",
	"love this",
	"love them",
	"i like",
	"amazing",
	"impressive",
	"/10",
	"out of 10",
	"look like",
	"looks like",
	"doesnt look",
	"doesn't look",
	"dosent look",
	"does not look",
	"does not feel",
	"dont like",
	"don't like",
	"not good",
	"badly",
	"broken",
	"stupid",
	"glitchy",
	"low quality",
	"too small",
	"too big",
	"need proper work",
	"isnt that big",
}

function Board.judgesWork(text: string): boolean
	local low = " " .. string.lower(text) .. " "
	for _, w in Board.JUDGING_WORDS do
		if Board.hasWord(low, w) then
			return true
		end
	end
	return false
end

-- the whole words of a loose-end card: its title is cut at 110 characters, the "## Goal" line keeps them all
-- (without the kind's lead-in: 'The owner asked: "..."', "Not sure: ", "Should be reworked: ")
function Board.looseText(t: Task): string
	local goal = string.match(t.body or "", "## Goal\r?\n([^\r\n]*)")
	if not goal or goal == "" then
		return t.title
	end
	local quoted = string.match(goal, '^The owner asked: "(.*)"%s*$')
	if quoted then
		return quoted
	end
	return string.match(goal, "^Not sure: (.*)$") or string.match(goal, "^Should be reworked: (.*)$") or goal
end

-- a loose end whose words are only a card id ("2u8p"): a slip that made a card out of a reference
function Board.bareId(text: string): string?
	local id = string.match(text, "^%s*([%l%d][%l%d][%l%d][%l%d])%s*$")
	if id and Board.find(id) then
		return id
	end
	return nil
end

function Board.kindOf(t: Task): string?
	for _, k in Board.KIND_ORDER do
		if table.find(t.labels, Board.KINDS[k].label) then
			return k
		end
	end
	return nil
end

-- a loose-end card (not saved; the caller sets file): its words kept whole in the goal, the title a short cut of them
function Board.loose(kind: string, text: string, area: string, on: string?): any
	local k = Board.KINDS[kind]
	text = string.gsub(string.gsub(text, "%s+", " "), "^ ", "")
	local title = if #text > 110 then string.sub(text, 1, 107) .. "..." else text
	local goal = string.format(k.goal, text)
	if on then
		goal ..= `\nAbout card {on}.`
	end
	return {
		id = Board.newId(),
		title = title,
		status = "todo",
		priority = k.priority,
		area = area,
		owner = "",
		claimed_at = "",
		created = Board.now(),
		updated = "",
		depends = {},
		labels = { k.label },
		body = `\n## Goal\n{goal}\n\n## Done when\n- [ ] {k.done}\n`,
		file = "",
	}
end

-- every open loose end by kind, oldest first -> { ask = {Task}, unsure = {Task}, rework = {Task} }
function Board.looseEnds(tasks: { Task }): { [string]: { Task } }
	local out = { ask = {}, unsure = {}, rework = {} }
	for _, t in tasks do
		local k = Board.kindOf(t)
		if k and t.status ~= "done" and t.status ~= "dropped" then
			table.insert(out[k], t)
		end
	end
	for _, list in out do
		table.sort(list, function(a, b)
			return a.created < b.created
		end)
	end
	return out
end

function Board.journal(who: string, text: string)
	Config.ensureDir(Board.dir("journal"))
	local path = Board.dir("journal") .. "/" .. Board.today() .. ".md"
	local existing = if fs.isFile(path) then fs.readFile(path) else `# Journal {Board.today()}\n\n`
	fs.writeFile(path, existing .. `- {string.sub(Board.now(), 12, 16)} **{who}**: {text}\n`)
end

function Board.latest(sub: string): string?
	local dir = Board.dir(sub)
	if not fs.isDir(dir) then
		return nil
	end
	local names = {}
	for _, n in fs.readDir(dir) do
		if string.sub(n, -3) == ".md" then
			table.insert(names, n)
		end
	end
	table.sort(names)
	return if #names > 0 then dir .. "/" .. names[#names] else nil
end

function Board.stamp(): string
	-- sortable + filename-safe: 2026-10-04T0712Z
	local iso = Board.now()
	return string.sub(iso, 1, 10) .. "T" .. string.sub(iso, 12, 13) .. string.sub(iso, 15, 16) .. "Z"
end

return Board

-- start.luau — `kit start <dept>`: ONE command that loads a lane in any harness, with any model. It prints, within one
-- token budget (vault.start_budget), exactly what that department's session needs and nothing about the others:
--   the lane's boot sheet (kit/knowledge/vault/<dept>/boot.md: the boot line, how the lane works, its own rules),
--   the stage shortlist with that stage's lessons, the lane's open tasks, its last handoff, and its vault page
--   (rules, the owner's last verdicts, the golden set, the graveyard) cut to what the budget leaves.
-- The shared rules (kit/harness/AGENTS.parallax.md, the MCP server's instructions) are a short router to here.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Board = require("../lib/board")
local Config = require("../lib/config")
local Harness = require("../lib/harness")
local Routes = require("../lib/routes")
local Run = require("../lib/run")
local Vault = require("../lib/vault")

local C = Run.CODES
local Start = {}

Start.TIDY_DAYS = 7

local function dayOf(date: string): number?
	local y, m, d = string.match(date, "^(%d%d%d%d)%-(%d%d)%-(%d%d)")
	if not y then
		return nil
	end
	return math.floor(
		os.time({ year = tonumber(y) :: number, month = tonumber(m) :: number, day = tonumber(d) :: number, hour = 12 })
			/ 86400
	)
end

-- the WEEKLY tidy (sprint 3: "a weekly tidy runs at the first kit start of the week"): the lane's garden proposals
-- (near-duplicate and flagged lessons, pairs) and its record warnings (kit vault check: stale golden rows, graves
-- without a route or a source), offered as kit start's next step at most once every TIDY_DAYS days per lane. The
-- stamp (.verify/tidy-<dept>.json) is read FIRST: garden + audit read the whole vault, so they run once a week, not
-- at every kit start. nil when it was looked at this week or there is nothing to tidy.
function Start.tidy(dept: string, today: string?): string?
	local stamp = `.verify/tidy-{dept}.json`
	local now = today or Vault.today()
	if fs.isFile(stamp) then
		local ok, j = pcall(serde.decode, "json" :: any, fs.readFile(stamp))
		local last = if ok and type(j) == "table" then dayOf(tostring(j.checked or j.offered or "")) else nil
		local current = dayOf(now)
		if last and current and current - last < Start.TIDY_DAYS then
			return nil
		end
	end
	local garden = #Vault.garden(dept)
	local warnings = 0
	for _, w in Vault.audit() do
		if w.dept == dept then
			warnings += 1
		end
	end
	if not fs.isDir(".verify") then
		fs.writeDir(".verify")
	end
	fs.writeFile(stamp, serde.encode("json", { checked = now, garden = garden, warnings = warnings }, true))
	if garden + warnings == 0 then
		return nil
	end
	return `the weekly tidy ({garden} garden proposal(s), {warnings} record warning(s)): lune run kit vault garden {dept}, then lune run kit vault check, then lune run kit alike index (the look index: new pictures) - act on what is this lane's (once a week)`
end

-- the owner's own before -> after (kit vault garden writes <dept>/pairs/: one piece that went from a low score to a
-- high one, both verdicts linked - 2026-11-08, sprint 4: written, never shown): the pair that fits the piece named,
-- else the newest. One line: what turned a rejection around is worth opening before building
function Start.pairLine(dept: string, piece: string?): string?
	local notes = Vault.notes(dept, "pairs")
	if #notes == 0 then
		return nil
	end
	local want: { [string]: boolean } = {}
	for _, w in Vault.words(piece or "") do
		want[w] = true
	end
	local best: Vault.Note? = nil
	local bestKey = ""
	for _, n in notes do
		local shared = 0
		for _, w in Vault.words(tostring(n.front.name or "")) do
			if want[w] then
				shared += 1
			end
		end
		local key = string.format("%03d%s", shared, tostring(n.front.date or ""))
		if not best or key > bestKey then
			best, bestKey = n, key
		end
	end
	local b = best :: Vault.Note
	local turn = string.match(b.body, "#[^\n]-:%s*([%d%.]+/10%s*%->%s*[%d%.]+/10)") or "low -> high"
	local file = if string.sub(b.rel, -3) == ".md" then b.rel else b.rel .. ".md"
	return `- {b.front.name or "?"} {turn} ({b.front.date or "?"}): what changed - kit/knowledge/vault/{file}`
end

-- the owner's ear as the SFX booth measures it (kit/audio/booth.py writes kit/knowledge/sfx_taste.json after every
-- verdict - 2026-11-08, sprint 4: written, never read): its leanings, or how many scored verdicts it still needs
Start.TASTE = "kit/knowledge/sfx_taste.json"
function Start.tasteLine(dept: string): string?
	if dept ~= "sfx" or not fs.isFile(Start.TASTE) then
		return nil
	end
	local ok, j = pcall(serde.decode, "json" :: any, fs.readFile(Start.TASTE))
	if not ok or type(j) ~= "table" then
		return nil
	end
	local leans = {}
	for _, l in (if type(j.leans) == "table" then j.leans else {}) :: { any } do
		if type(l) == "table" and l.trait then
			table.insert(leans, `{l.trait}: {l.owner_prefers or "?"} (r {l.r or "?"})`)
		end
	end
	if #leans > 0 then
		return `- the owner's ear leans {table.concat(leans, "; ")} - {j.verdicts or "?"} scored verdicts ({Start.TASTE})`
	end
	return `- {j.note or `{j.verdicts or 0} scored verdict(s)`} ({Start.TASTE}; it grows with every kit sfx listen verdict)`
end

-- the lane's taste model (kit/vision/taste.py writes <dept>/taste.json: the owner's own scores, tested leave-one-out;
-- 2026-11-08, sprint 5): on and how far it agrees with the owner, or why it is off
function Start.tasteModelLine(dept: string): string?
	local path = Vault.dir(dept, "taste.json")
	if not fs.isFile(path) then
		return nil
	end
	local ok, j = pcall(serde.decode, "json" :: any, fs.readFile(path))
	if not ok or type(j) ~= "table" then
		return nil
	end
	if j.off then
		return `- taste model: switched off by the owner (kit taste on {dept})`
	end
	if j.enabled and tonumber(j.pairwise) then
		return `- taste model: orders candidates - agrees with the owner on {math.floor(j.pairwise * 100 + 0.5)}% of pairs (leave-one-out, {j.n} scored pieces; kit taste off {dept})`
	end
	return `- taste model: off - {j.why or "not trained"} (it re-tests after every verdict)`
end

Start.DEPTS = { "3d", "vfx", "ui", "anim", "world", "sfx", "code", "qa", "kit" }

-- board task areas per lane (world tasks were filed as "design" before the world lane had its own name)
local AREAS: { [string]: { string } } = { world = { "world", "design" } }

local function tokens(s: string): number
	return math.ceil(#s / 4)
end

local function clip(line: string, n: number): string
	local len = utf8.len(line)
	if len and len > n then
		return string.sub(line, 1, (utf8.offset(line, n - 2) or n - 2) - 1) .. "..."
	end
	return line
end

-- the boot sheet's body (frontmatter dropped), or nil
function Start.boot(dept: string): string?
	local path = Vault.dir(dept, "boot.md")
	if not fs.isFile(path) then
		return nil
	end
	local front, body = Vault.parse(fs.readFile(path))
	if not front then
		return nil
	end
	return (string.gsub(string.gsub(body, "\r\n", "\n"), "%s+$", ""))
end

-- the lane's open tasks (doing / review / ready / blocked), by priority
function Start.tasks(dept: string, n: number): { string }
	local areas = AREAS[dept] or { dept }
	local out = {}
	for _, t in Board.tasks() do
		if
			table.find(areas, t.area)
			and (t.status == "doing" or t.status == "todo" or t.status == "review" or t.status == "blocked")
		then
			local who = if t.owner and t.owner ~= "" then ` @{t.owner}` else ""
			table.insert(out, clip(`  {t.id}  {t.priority}  [{t.status}] {t.title}{who}`, 160))
			if #out >= n then
				break
			end
		end
	end
	return out
end

-- does `text` name the lane (its key or its title word as a whole word)?
-- the words a handoff summary uses for each lane ("Systems/sound lane round 2: ..." is code AND sfx)
local LANE_WORDS: { [string]: { string } } = {
	["3d"] = { "3d" },
	vfx = { "vfx" },
	ui = { "ui" },
	anim = { "anim", "animation", "animations" },
	world = { "world", "worlds" },
	sfx = { "sfx", "sound", "sounds" },
	code = { "code", "systems", "system" },
	qa = { "qa" },
	kit = { "kit" },
}

local function mentions(text: string, dept: string): boolean
	local low = string.lower(text)
	for _, w in LANE_WORDS[dept] or { dept } do
		local at = 1
		while true do
			local s, e = string.find(low, w, at, true)
			if not s then
				break
			end
			local before = if s > 1 then string.sub(low, s - 1, s - 1) else " "
			local after = string.sub(low, e + 1, e + 1)
			if not string.match(before, "[%w]") and not string.match(after, "[%w]") then
				return true
			end
			at = s + 1
		end
	end
	return false
end

-- does a handoff's text belong to this lane? Only clear signals count: its "## Lane" line (kit handoff --lane), or a
-- summary OPENING with the lane ("VFX: ..."). A passing mention, or a task the author still held, is NOT enough
-- (stale claims made the kit session's handoffs look like 3D, world and systems ones): showing another lane's handoff
-- would send this session into that lane's work
function Start.claims(text: string, dept: string): boolean
	text = string.gsub(text, "\r\n", "\n")
	local summary = string.match(text, "## Summary\n+([^\n]+)") or ""
	if summary == "" then
		return false
	end
	-- a handoff that names its lane is decided by that alone
	local named = string.match(text, "\n## Lane\n(%S+)")
	if named then
		return named == dept
	end
	local opener = string.match(summary, "^([^:]+):") or ""
	-- "kit world cliffs: ..." is the WORLD lane's: the kit lane claims an opener only when it names no other lane
	local claimed = #opener <= 30 and mentions(opener, dept)
	if claimed and dept == "kit" then
		for _, other in Start.DEPTS do
			if other ~= "kit" and mentions(opener, other) then
				return false
			end
		end
	end
	return claimed
end

-- the newest handoff that names this lane: its path and summary line
function Start.handoff(dept: string): (string?, string?)
	local dir = Board.dir("handoffs")
	if not fs.isDir(dir) then
		return nil, nil
	end
	local names = {}
	for _, n in fs.readDir(dir) do
		if string.sub(n, -3) == ".md" then
			table.insert(names, n)
		end
	end
	table.sort(names)
	for i = #names, math.max(1, #names - 80), -1 do
		local path = `{dir}/{names[i]}`
		local text = string.gsub(fs.readFile(path), "\r\n", "\n")
		if Start.claims(text, dept) then
			return path, clip(string.match(text, "## Summary\n+([^\n]+)") or "", 300)
		end
	end
	return nil, nil
end

-- the whole start text; `stage` defaults to the route's first stage
Start.ORDERS_SHOWN = 15

-- each content lane's quality locks (2026-10-21; enforced by the build commands and kit verify, see kit/lib/locks.luau
-- and kit/lib/lanelocks.luau): what a NEW piece needs before it builds, and the exact command that records it
Start.LOCKS = {
	vfx = {
		"Scene breakdown first: kit vfx breakdown <set> --clip <the real scene>, a beat sheet with >= 3 timed beats, a lore brief (>= 3 facts) and colours measured from >= 4 DISTINCT real scene frames (our own build/ renders never count).",
		'Beat chart approved by the owner: show build/vfx/charts/<set>.png, then lune run kit vfx chart <set> --approve "<their words>" --by owner (or kit approve vfx <set> ...). Record their score too: kit verdict vfx <set> <0-10> "<words>" --tag chart.',
		"The METHOD PLAN on that chart first: lune run kit vfx methods --set <set> - each beat names the methods of his list it is made with (--beat N --use id,id). The build refuses a piece off its plan.",
	},
	ui = {
		"A new screen compiles only on >= 2 real stills of its type (hud / menu:<screen>) at >= 1080p: lune run kit ui refs <identity> ... (kit ui plan <Screen> shows the refs stage); the owner may waive it: --waive refs.",
	},
	sfx = {
		'A new sound or set needs the reference recording the OWNER picked (kit sfx find "<words>", kit sfx listen <name> --ref <file>): record their pick with kit approve sfx <name> "<their words naming it>" --by owner; synth-only by their choice: --waive refs.',
	},
	["3d"] = {
		"A new asset starts from its brief (assets/models/<name>.brief.md: what, quality, hero features); a hero / aaa / complex one needs the owner's approval of that brief (and its reference sheet) before kit asset / kit make build it.",
	},
	world = {
		"A new world is built beside >= 6 real reference stills (the owner's picks) in assets/worlds/refs/<Name>/ plus a measured REFS.md (lune run kit world refs <Name>); the owner may waive it: --waive refs.",
		'A place of houses is laid out by its PLAN: one "town" step (lune run kit world town <Name> draws its streets, lots, landmark and the walk from every gate: read that page before dressing anything), its house meshes made from the plan (kit world town <Name> --kit, then kit world meshes --set town_<Name>). The build refuses 12 or more houses typed one by one (the owner may waive it: --waive layout); kit world check fails a "city" grid and a town with no "skins".',
		'A road, row, palisade or wall along points that turns a hard corner says how it bends: "curve": true (a smooth line through its points) or "curve": false (meant); any step stands at any angle with "turn": <degrees>. A town says how its streets run: "bend": <3 to 8 degrees> (its blocks of houses turned round the square) or "bend": 0 (straight, meant); a bent town sets its own spawn pads with "spawns": 2.',
	},
	anim = {
		"A new move dossier is schema 2 with MEASURED evidence (a source with numbers, real_s timings on every moving phase): lune run kit anim dossier footage <move> <clip>; the owner may waive it: --waive evidence.",
	},
}

-- how many of the owner's newest verdict lines kit start prints when a distil is due
Start.DUE_WORDS = 3
-- the best-ranked lesson's text in kit start, at most (kit help --stage prints the top two whole)
Start.FULL_CHARS = 450

-- the lane's top open card (one in progress first, else the first ready one): what an unnamed session ranks for
function Start.topCard(dept: string): Board.Task?
	local areas = AREAS[dept] or { dept }
	local first: Board.Task? = nil
	for _, t in Board.tasks() do
		if table.find(areas, t.area) then
			if t.status == "doing" then
				return t
			end
			if not first and t.status == "todo" then
				first = t
			end
		end
	end
	return first
end

-- what the lessons are ranked for: opts.forPiece (`--for`), else the lane's top card's title and goal
-- -> query, how the header names it, the piece (nil for words or a card)
function Start.focus(dept: string, given: any): (string?, string?, string?)
	local q, about, piece = Routes.forFlag(dept, given)
	if q then
		return q, about, piece
	end
	local card = Start.topCard(dept)
	if card then
		local goal = string.match(card.body or "", "## Goal%s*\n(.-)\n##") or ""
		return `{card.title} {goal}`, `the card {card.id} ("{clip(card.title, 50)}")`, nil
	end
	return nil, nil, nil
end

function Start.text(
	dept: string,
	stage: string?,
	budget: number?,
	focus: { query: string?, about: string?, piece: string? }?
): (string, { [string]: boolean }, { string })
	local limit = budget or (Config.load().vault or {}).start_budget or 2500
	local shownIds: { string } = {}
	local blocks: { [string]: boolean } = {}
	local parts = {}
	local function add(s: string)
		table.insert(parts, s)
	end
	add(`== {dept} lane ({Vault.TITLES[dept] or dept}) — loaded by lune run kit start {dept}`)
	-- where every command of this session reads and writes (games/.active is shared by every session in the checkout)
	local game = Config.game()
	add(
		if game
			then `== working in: games/{game}/ (this command's game: --game, else the active one). The owner named another game? Add --game <Name> to EVERY command of this session yourself (never kit game use: other sessions share the active game); games + Rojo ports: lune run kit game list`
			else "== working in: the project root (no active game). The owner named a game? Add --game <Name> to EVERY command of this session yourself (a new game: lune run kit game new <Name>, which picks its own Rojo port); games + ports: lune run kit game list"
	)
	-- the owner's standing orders before anything else: never cut, obeyed by every session of the lane
	local orders = Vault.orders(dept)
	local shared = if dept == "shared" then {} else Vault.orders("shared")
	if #orders + #shared > 0 then
		add(
			`## Standing orders (the owner's; obey every one - kit/knowledge/vault/{dept}/orders.md + shared/orders.md)`
		)
		-- at most ORDERS_SHOWN lines so the owner's verdicts below always fit; the rest are named, never hidden silently
		local shown = 0
		for _, o in shared do -- the every-lane orders first: they are never the ones cut
			if shown < Start.ORDERS_SHOWN then
				add(`- (every lane) {o}`)
				shown += 1
			end
		end
		for _, o in orders do
			if shown < Start.ORDERS_SHOWN then
				add(`- {o}`)
				shown += 1
			end
		end
		if #orders + #shared > shown then
			add(
				`- ... {#orders + #shared - shown} more: read kit/knowledge/vault/{dept}/orders.md (more than {Start.ORDERS_SHOWN} orders crowd the page: ask the owner which to merge)`
			)
		end
		add("")
		blocks.orders = true
	end
	local boot = Start.boot(dept)
	if boot then
		add(boot)
		blocks.boot = true
	else
		add(`(no boot sheet: kit/knowledge/vault/{dept}/boot.md)`)
	end
	local lock = Start.LOCKS[dept]
	if lock then
		add("")
		add("## Quality locks (the build refuses a NEW piece until these are done; older pieces are exempt)")
		for _, l in lock do
			add(`- {l}`)
		end
		add(
			`- The owner's go-ahead or waiver, recorded ONLY when they gave it: lune run kit approve {dept} <name> "<their words>" --by owner [--waive <step>]; without --by owner it is a proposal no lock accepts.`
		)
		add(
			`- Verdict cap: at most {require("../lib/lanelocks").OPEN_CAP} new pieces of this lane without the owner's score, per project (the kit home and each game count apart); kit new and the build refuse the next one. Waiting: lune run kit verdict pending {dept}.`
		)
		blocks.locks = true
	end
	-- enforced learning (board/plans/archive/2026-11-09-enforced-learning-plan.md, rule 1): an owner verdict of this lane that
	-- has not taught its lesson is the session's FIRST job - kit new and kit handoff refuse until it is paid
	-- (where the owed items and the Due block's quoted words sit in `parts`: given up first for the department's record;
	-- their headings - the job and its command - always stay)
	local dueQuote: { number } = {}
	local owed = Vault.owedLines(dept)
	if #owed > 0 then
		add("")
		add(
			`## Owed: {#owed} thing(s) from the owner's verdicts (a lesson to learn, a look not taken) - FIRST job, kit new and kit handoff refuse until each is paid: lune run kit lesson {dept} "<what it taught>" --verdict <name> (or kit verdict learned <kind> <name> none "<why>"); the list: lune run kit verdict owed {dept}`
		)
		for i = 1, math.min(3, #owed) do
			add(`  {clip(owed[i], 140)}`)
			table.insert(dueQuote, #parts)
		end
		if #owed > 3 then
			add(`  ... {#owed - 3} more: lune run kit verdict owed {dept}`)
			table.insert(dueQuote, #parts)
		end
		blocks.owed = true
	end
	-- learning that is due now (nobody has to remember it)
	local dueN, dueCmd = Vault.distilDue(dept)
	if dueN then
		add("")
		add(
			`## Due: {dueN} owner verdicts since the last distil - FIRST job: {dueCmd} (then --rule / --edit / --retire, or --none "<why no new rule>"; kit handoff refuses at {2 * Vault.DISTIL_EVERY})`
		)
		-- the owner's newest words of the packet, here: the reminder alone was skipped for weeks (anim 37, vfx 17)
		local packet = Vault.distil(dept)
		local from = math.max(1, #packet.verdicts - Start.DUE_WORDS + 1)
		if from > 1 then
			add(`  ... {from - 1} older in the packet; the newest {Start.DUE_WORDS}:`)
			table.insert(dueQuote, #parts)
		end
		for i = from, #packet.verdicts do
			local f = packet.verdicts[i].front
			local said = if f.score ~= nil
				then f.score .. "/10"
				elseif Vault.direction(f) == "keep" then "Keep"
				elseif Vault.direction(f) == "redo" then "Redo"
				else "words"
			add(
				clip(
					`  {f.date} {f.name}: {said} - {(string.gsub(
						string.gsub(packet.verdicts[i].body, "%(the owner's words, from board ask %w+%)", ""),
						"%s+",
						" "
					))}`,
					140
				)
			)
			table.insert(dueQuote, #parts)
		end
		blocks.due = true
	end
	local stages = Routes.stages(dept)
	local at = stage or stages[1]
	if at then
		add("")
		add(
			`## Stage (the route: {table.concat(stages, " -> ")}; another stage: lune run kit start {dept} --stage <stage>)`
		)
		-- inside the start budget: the best lesson in full (clipped), the rest as gists - the owner's verdicts, golden
		-- set and graveyard on the page below must still fit (start.spec)
		local f = focus or {}
		local lines, shown = Routes.lines(
			dept,
			at,
			-- (a lane with a distil due does that first: its lessons are gists until the rules are written)
			{
				query = f.query,
				about = f.about,
				piece = f.piece,
				full = if dueN then 0 else 1,
				count = if dueN then 4 else nil,
				fullChars = Start.FULL_CHARS,
			}
		)
		shownIds = shown
		for _, l in lines do
			add(l)
		end
		blocks.stage = true
	end
	-- what the owner's own record says outside the lessons: a low piece turned high, and (SFX) their measured ear
	local pair, taste = Start.pairLine(dept, (focus or {}).piece), Start.tasteLine(dept)
	local model = Start.tasteModelLine(dept)
	if pair or taste or model then
		add("## What turned the owner around / the owner's ear")
		for _, l in { pair, taste, model } :: { string? } do
			if l then
				add(l)
			end
		end
		blocks.record = true
	end
	-- the QA lane: the playtests failing now (kit playtest run/record keeps one vault note per playtest)
	if dept == "qa" then
		local failing = require("../lib/playtests").failing()
		if #failing > 0 then
			add(`## Playtests failing now ({#failing}; kit/knowledge/vault/qa/playtests/)`)
			for i = 1, math.min(3, #failing) do
				add(`- {failing[i]}`)
			end
		end
	end
	if Start.SKILL[dept] then
		add("")
		add(`## The lane's full recipe: lune run kit skill {dept} (kit/skills/{Start.SKILL[dept]}/SKILL.md)`)
	end
	local tasks = Start.tasks(dept, 5)
	add("")
	add("## Open tasks of this lane (claim one: lune run kit task claim <id> --as <model@harness>)")
	if #tasks > 0 then
		for _, l in tasks do
			add(l)
		end
		blocks.tasks = true
	else
		add("  (none open: lune run kit task add ... or ask the owner)")
	end
	local hpath, hsum = Start.handoff(dept)
	add("")
	add("## Last handoff that names this lane")
	if hpath then
		add(`  {hpath}`)
		add(`  {hsum}`)
		blocks.handoff = true
	else
		add(`  (none names this lane yet: end your session with lune run kit handoff "..." --lane {dept})`)
	end
	add("")
	add("## The department's record (the vault page: rules, the owner's last verdicts, golden set, graveyard)")
	local function record(p: string): boolean
		return string.find(p, "LAST VERDICTS", 1, true) ~= nil
			or string.find(p, "GOLDEN", 1, true) ~= nil
			or string.find(p, "GRAVEYARD", 1, true) ~= nil
	end
	local used = tokens(table.concat(parts, "\n"))
	local pageBudget = math.max(250, limit - used - 40)
	local page = Vault.page(dept, pageBudget, true) -- (its standing orders are printed first, above)
	if not record(page) and #dueQuote > 0 then
		-- a full lane (the 3D lane, 2026-11-09: 665 tokens left, its record starts at ~700): the Due block keeps its
		-- header (the job) and gives up its quoted words, which the page's own LAST VERDICTS shows newest first,
		-- rather than the page losing the department's record
		for i = #dueQuote, 1, -1 do
			table.remove(parts, dueQuote[i])
		end
		table.insert(
			parts,
			dueQuote[1],
			`  (the list: lune run kit verdict owed {dept}; the owner's newest words: LAST VERDICTS below)`
		)
		used = tokens(table.concat(parts, "\n"))
		pageBudget = math.max(250, limit - used - 40)
		page = Vault.page(dept, pageBudget, true)
	end
	if not record(page) and (#tasks > 0 or hsum) then
		-- still no room (the 3D lane, 2026-11-11: 684 tokens left, its record past RULES never printed): the open tasks
		-- fold into one pointer and the last handoff keeps its path - the department's record comes first; the tasks
		-- are one command away and the handoff file holds its own summary
		local fold: { [string]: boolean } = {}
		for _, l in tasks do
			fold[l] = true
		end
		if hsum then
			fold[`  {hsum}`] = true
		end
		for i = #parts, 1, -1 do
			if fold[parts[i]] then
				table.remove(parts, i)
			end
		end
		if #tasks > 0 then
			for i, l in parts do
				if string.find(l, "## Open tasks of this lane", 1, true) == 1 then
					table.insert(parts, i + 1, `  (the open tasks: lune run kit status --dept {dept})`)
					break
				end
			end
		end
		used = tokens(table.concat(parts, "\n"))
		pageBudget = math.max(250, limit - used - 40)
		page = Vault.page(dept, pageBudget, true)
	end
	add(page)
	blocks.page = record(page)
	return table.concat(parts, "\n"), blocks, shownIds
end

-- each lane's full recipe (a skill page): harnesses without a skills folder (Gemini, Windsurf, Roo, Cline, Copilot, a
-- bare model with a shell) read it with `kit skill <lane>`
Start.SKILL = {
	["3d"] = "parallax-3d",
	vfx = "parallax-vfx",
	ui = "parallax-ui",
	anim = "parallax-anim",
	world = "parallax-world",
	sfx = "parallax-sfx",
	code = "parallax-systems",
	qa = "parallax-qa",
	kit = "parallax-work",
	parallax = "parallax-work",
}

-- a pre-Parallax skill name (roblox-3d, kit-work, ...) -> its parallax-* page (zero-breakage brand shim, §5.1 8)
function Start.skillName(name: string): string
	local mapped = Start.SKILL[name]
	if mapped then
		return mapped
	end
	local rest = string.match(name, "^roblox%-(.+)$") or string.match(name, "^kit%-(.+)$")
	return if rest then `parallax-{rest}` else name
end

-- the skill page's text without its frontmatter, with its lane's case table (the recipe every client gets from
-- parallax_skill / `parallax skill`), or nil + why
function Start.skill(name: string): (string?, string?)
	local skill = Start.skillName(name)
	local path = `kit/skills/{skill}/SKILL.md`
	if not fs.isFile(path) then
		return nil, `no skill page {path}`
	end
	local text = string.gsub(Harness.skillCopy(skill), "\r\n", "\n")
	text = string.gsub(text, "^%-%-%-\n.-\n%-%-%-\n+", "")
	return text, nil
end

return function(Cli: any)
	Cli.command(
		"start",
		"skill",
		"skill <lane|skill name>",
		"print a lane's full recipe (its skill page) for any harness or model; kit skill lists them",
		function(rawArgs)
			local args = Cli.parse(rawArgs)
			if not args[1] then
				local names = {}
				for _, file in fs.readDir("kit/skills") do
					if fs.isFile(`kit/skills/{file}/SKILL.md`) then
						table.insert(names, file)
					end
				end
				table.sort(names)
				print(
					"  lanes: " .. table.concat(Start.DEPTS, ", ") .. "    skill pages: " .. table.concat(names, ", ")
				)
				return Run.report(
					"skill",
					{},
					C.PASS,
					`skill: {#names} skill page(s)`,
					"lune run kit skill <your lane>"
				)
			end
			local text, why = Start.skill(args[1])
			if not text then
				return Run.report("skill", {}, C.USAGE, `skill: {why}`, "lune run kit skill   (lists them)")
			end
			print(text)
			return Run.report(
				"skill",
				{},
				C.PASS,
				`skill: {Start.SKILL[args[1]] or args[1]} (~{tokens(text)} tokens)`,
				`start the lane if you have not: lune run kit start {if Start.SKILL[args[1]] then args[1] else "<lane>"}`
			)
		end
	)
	Cli.command(
		"start",
		"start",
		'start <3d|vfx|ui|anim|world|sfx|code|qa|kit> [--stage <stage>] [--for <piece|"words">] [--prompt "<the owner\'s words>" [--model M]]',
		"load ONE lane: its boot sheet, rules, stage shortlist + the lessons ranked for your piece (--for, else the lane's top card), open tasks, last handoff and vault page; --prompt compiles the owner's words with PROMPT-X, this lane leading",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			local dept = Vault.dept(args[1]) or args[1]
			if not dept or not table.find(Start.DEPTS, dept) then
				return Run.report(
					"start",
					{},
					C.USAGE,
					"start: name the lane",
					`lune run kit start <{table.concat(Start.DEPTS, "|")}>`
				)
			end
			local stage = if type(flags.stage) == "string" then flags.stage else nil
			if flags.stage ~= nil and (not stage or not table.find(Routes.stages(dept), stage)) then
				return Run.report(
					"start",
					{},
					C.USAGE,
					`start: "{stage}" is not a {dept} stage ({table.concat(Routes.stages(dept), ", ")})`,
					`lune run kit start {dept}`
				)
			end
			-- the owner's newest verdicts (this lane's own store, lessons, the inbox) reach the page before it prints
			local filed, clean = Vault.catchUp(Vault.STORES_OF[dept] or {})
			if #filed > 0 then
				print(
					`-- the vault caught up: {table.concat(filed, ", ")} filed{if clean
						then ""
						else " (the sync failed: lune run kit vault sync)"}; commit kit/knowledge/vault with your work`
				)
			end
			-- the stage's lessons ranked for the piece named (--for), else for the lane's top card
			local query, about, piece = Start.focus(dept, flags["for"])
			local text, _blocks, shown = Start.text(dept, stage, nil, { query = query, about = about, piece = piece })
			print(text)
			if piece and #shown > 0 and Vault.KIND_OF_DEPT[dept] then
				local fresh = Vault.serve(Vault.KIND_OF_DEPT[dept], piece, shown, Board.agent(flags.as))
				if #fresh > 0 then
					print(
						`-- recorded: {#fresh} lesson(s) shown for {piece} (the owner's verdict on it credits or blames them; commit {Vault.citationsPath()})`
					)
				end
			end
			-- the page was just printed: the department page hook need not repeat it this window
			pcall(function()
				require("../lib/vaultgate").due(dept, (Config.load().vault or {}).reshow_minutes or 120)
			end)
			-- stale claims go back to To do and the board is serving (kit/lib/boardweb.luau)
			for _, l in require("../lib/boardweb").arrive("kit start") do
				print(l)
			end
			-- the lane's lessons that say the same thing twice (each one shown twice crowds out a third)
			local dupes = Vault.nearDuplicates(dept)
			if #dupes > 0 then
				print(
					`-- tidy: {#dupes} pair(s) of near-duplicate {dept} lessons - merge them: lune run kit vault garden {dept}`
				)
			end
			-- the loose ends: the owner's asks first (this lane's before the rest), so none is forgotten between sessions
			local ends = Board.looseEnds(Board.tasks())
			if #ends.ask + #ends.unsure + #ends.rework > 0 then
				print(
					`-- loose ends: {#ends.ask} owner ask(s) not done, {#ends.unsure} unsure, {#ends.rework} to rework (lune run kit task resume)`
				)
				local asks, rest = {}, {}
				for _, t in ends.ask do
					table.insert(if t.area == dept then asks else rest, t)
				end
				table.move(rest, 1, #rest, #asks + 1, asks)
				for i = 1, math.min(3, #asks) do
					print(`   owner asked [{asks[i].area}] {asks[i].id}: {asks[i].title}`)
				end
			end
			-- --prompt "<the owner's words>": PROMPT-X compiles them with this lane leading (LIMITATIONS_FIXES_V4 9.5)
			if type(flags.prompt) == "string" then
				local pargv = { "kit/prompt/cli.py", "compile", flags.prompt, "--lane", dept }
				-- --for <piece> (one word): the packet is the piece's, so the owner's later verdict on it reaches its
				-- <piece>.plan.json through PROMPT-X evolve (PARALLAX spec §3.3 stage 3)
				if type(flags["for"]) == "string" and string.match(flags["for"], "^[%w_%-]+$") then
					table.insert(pargv, "--piece")
					table.insert(pargv, flags["for"])
				end
				if type(flags.model) == "string" then
					table.insert(pargv, "--model")
					table.insert(pargv, flags.model)
				end
				local ps = Run.spawn("prompt compile", Run.tool("python"), pargv, true)
				local pr = ps.result or {}
				print(`-- PROMPT-X: {tostring(pr.summary or "the compiler gave no verdict")}`)
				for _, line in (if type(pr.lines) == "table" then pr.lines else {}) :: { any } do
					print("   " .. tostring(line))
				end
				if pr.packet_path then
					print(
						`   the compiled prompt: {pr.packet_path} (orchestrator_prompt); lune run kit prompt compile ... --full prints it`
					)
				end
			end
			local tasks = Start.tasks(dept, 1)
			-- a due distil comes before new work: the owner's verdicts become rules while they are fresh; with none
			-- due, the weekly tidy (at most once a week)
			local dueN, dueCmd = Vault.distilDue(dept)
			local tidy = if dueN then nil else Start.tidy(dept)
			local claim = if #tasks > 0
				then `lune run kit task claim {string.match(tasks[1], "^%s*(%S+)")} --as <model@harness>`
				else nil
			local after = `(then {claim or "claim your task"})`
			return Run.report(
				"start",
				{},
				C.PASS,
				`start: the {dept} lane is loaded (~{tokens(text)} tokens){if dueN
					then ` - a distil is due ({dueN} owner verdicts)`
					else ""}`,
				if dueN and dueCmd
					then `{dueCmd} {after}`
					elseif tidy then `{tidy} {after}`
					elseif claim then `claim a task or continue yours: {claim}`
					else `lune run kit help --stage {dept}:{stage or Routes.stages(dept)[1] or "work"}`
			)
		end
	)
	return Start
end

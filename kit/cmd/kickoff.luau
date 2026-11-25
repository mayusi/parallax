-- kickoff.luau — `kit kickoff <Name> "<the owner's brief>" --anim "..." --vfx "..." --sfx "..." --code "..." ...`:
-- ONE brief that spans several lanes (a moveset: animations + effects + sounds + moves) becomes one board task per
-- lane, so every lane's session finds its part in `kit start <lane>` without being told again. Each task carries the
-- WHOLE brief in the owner's words plus that lane's own part, so a lane works alone (departments stay separate: no
-- shared file is built across lanes; the tasks only name each other's ids for coordination). The owner's words are
-- kept as a record in board/briefs/<Name>.md.
local fs = require("@lune/fs")

local Board = require("../lib/board")
local Config = require("../lib/config")
local Run = require("../lib/run")

local C = Run.CODES
local Kickoff = {}

-- the lanes a brief can name, in the order they usually hand work on (moves take their frames from the animation)
Kickoff.LANES = { "anim", "vfx", "sfx", "3d", "ui", "world", "code", "qa" }

-- what "done" means for each lane's part (every lane: the owner scored its pieces; the lane's own gate passed)
local DONE: { [string]: { string } } = {
	anim = {
		"the move dossier is schema 2 with measured evidence and each clip passes kit anim (its gates)",
		'the owner scored each clip: lune run kit anim verdict <Name> <word> "<their words>"',
	},
	vfx = {
		'each effect\'s scene breakdown and beat chart are approved by the owner (kit vfx chart <set> --approve "..." --by owner)',
		'the owner scored each effect in the player: lune run kit vfx vault verdict <effect> "<words>" --score N',
	},
	sfx = {
		'each sound is built on the reference the owner picked (kit approve sfx <name> "..." --by owner) and passes kit sfx',
		"the owner scored each sound in the booth: lune run kit sfx listen <name>",
	},
	["3d"] = {
		'each asset\'s brief is approved by the owner (kit approve 3d <name> "..." --by owner) and kit asset passes',
		'the owner scored each asset: lune run kit verdict asset <name> <0-10> "<words>"',
	},
	ui = {
		"each screen is built on >= 2 real stills of its type and kit ui passes",
		'the owner scored each screen: lune run kit ui judge <Screen> --owner <score> "<words>"',
	},
	world = {
		"the world has >= 6 real reference stills + REFS.md and kit world check passes",
		'the owner scored the world: lune run kit verdict world <Name> <0-10> "<words>"',
	},
	code = {
		"lune run kit move names nothing missing (every animation, sound and effect the moves point at exists in the game)",
		"kit verify passes and a playtest in Studio shows no console error",
	},
	qa = { "kit audit passes and the playtests of this brief pass in Studio with no console error" },
}

local function short(text: string, n: number): string
	local t = string.gsub(text, "%s+", " ")
	if #t > n then
		return string.sub(t, 1, n - 3) .. "..."
	end
	return t
end

-- create the tasks (and the brief record); returns { lane = task id } and the brief's path
function Kickoff.create(
	name: string,
	brief: string,
	parts: { [string]: string },
	priority: string,
	who: string
): ({ [string]: string }, string)
	local ids: { [string]: string } = {}
	local order = {}
	for _, lane in Kickoff.LANES do
		if parts[lane] then
			ids[lane] = Board.newId()
			table.insert(order, lane)
		end
	end
	local briefPath = Board.dir("briefs") .. `/{Board.slug(name)}.md`
	local others = {}
	for _, lane in order do
		table.insert(others, `{lane} {ids[lane]}`)
	end
	for _, lane in order do
		local body = table.concat({
			"",
			"## Goal",
			`{name} - the {lane} part: {parts[lane]}`,
			"",
			"## The owner's brief (whole, in their words)",
			brief,
			"",
			`## The other lanes on {name} (their own tasks; never edit their files)`,
			table.concat(others, " · "),
			`The brief's record: {briefPath}`,
			"",
			"## Done when",
		}, "\n") .. "\n"
		for _, d in DONE[lane] or {} do
			body ..= `- [ ] {d}\n`
		end
		local depends = {}
		if lane == "code" and ids.anim then
			table.insert(depends, ids.anim) -- moves take their frames from the animation's measured phases
		end
		local t: any = {
			id = ids[lane],
			title = `{name} - {lane}: {short(parts[lane], 60)}`,
			status = "todo",
			priority = priority,
			area = lane,
			owner = "",
			claimed_at = "",
			created = Board.now(),
			updated = "",
			depends = depends,
			labels = { `kickoff:{name}` },
			body = body,
			file = Board.dir("tasks") .. `/{ids[lane]}-{Board.slug(name .. " " .. lane)}.md`,
		}
		Board.note(t, who, `created by kit kickoff {name}`)
		Board.save(t)
	end
	local lines = {
		`# {name} - the brief`,
		"",
		`- date: {Board.today()}`,
		`- by: {who} (from the owner's words)`,
		`- tasks: {table.concat(others, " · ")}`,
		"",
		"## The owner's brief",
		"",
		brief,
		"",
		"## Each lane's part",
		"",
	}
	for _, lane in order do
		table.insert(lines, `- **{lane}** ({ids[lane]}): {parts[lane]}`)
	end
	Config.ensureDir(Board.dir("briefs"))
	fs.writeFile(briefPath, table.concat(lines, "\n") .. "\n")
	Board.journal(who, `kickoff {name}: {table.concat(others, ", ")}`)
	return ids, briefPath
end

return function(Cli: any)
	Cli.command(
		"work",
		"kickoff",
		'kickoff <Name> "<the owner\'s brief>" --anim "<its part>" --vfx "..." --sfx "..." --code "..." [--3d|--ui|--world|--qa "..."] [--priority p1] [--game <Name>]',
		"ONE brief across lanes (a moveset: anim + vfx + sfx + moves) -> one task per lane, each with the whole brief and its own part; every lane's kit start shows it",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			local name, brief = args[1], args[2]
			local parts: { [string]: string } = {}
			local n = 0
			for _, lane in Kickoff.LANES do
				if type(flags[lane]) == "string" and flags[lane] ~= "" then
					parts[lane] = flags[lane]
					n += 1
				end
			end
			if not name or not brief or brief == "" or n == 0 then
				return Run.report(
					"kickoff",
					{},
					C.USAGE,
					"kickoff: name it, give the owner's brief, and each lane's part",
					'lune run kit kickoff KatanaMoveset "<the owner\'s brief>" --anim "4 slashes + a finisher" --vfx "water trails on each slash" --sfx "swings + hits" --code "the moves + the combo"'
				)
			end
			local priority = if type(flags.priority) == "string" then flags.priority else "p1"
			if not string.match(priority, "^p[0-3]$") then
				return Run.report("kickoff", {}, C.USAGE, "kickoff: priority must be p0 .. p3", "--priority p1")
			end
			local who = Board.agent(flags.as)
			local ids, briefPath = Kickoff.create(name, brief, parts, priority, who)
			local list = {}
			for _, lane in Kickoff.LANES do
				if ids[lane] then
					print(`  {lane}  task {ids[lane]}  -> a {lane} session: lune run kit start {lane}`)
					table.insert(list, `{lane} {ids[lane]}`)
				end
			end
			local gameFlag = if Config.game() then ` --game {Config.game()}` else ""
			return Run.report(
				"kickoff",
				{},
				C.PASS,
				`kickoff {name}: {n} lane task(s) ({table.concat(list, ", ")}); the brief: {briefPath}`,
				`open one session per lane and start it: lune run kit start <lane>{gameFlag} (its open tasks show its part); commit {briefPath} and the tasks`
			)
		end
	)
	return Kickoff
end

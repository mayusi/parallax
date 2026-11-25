-- approve.luau — `kit approve <lane> <name> "<the owner's words>" --by owner [--waive <step,...>]`: the ONE place the
-- owner's go-ahead for a new piece is written (board/locks.json). Every lane's build command refuses a new piece whose
-- quality step (scene chart, real references, brief, evidence, verdict) has no owner record; a model may PROPOSE
-- (no --by owner: recorded as model-proposed, which no lock accepts), never approve its own work.
-- `--stage <step>` (3d: sheet, blockout; vfx: style, animatic) records his yes to ONE stage's artefact - the model
-- sheet, the blockout, an effect's style sheet, a scene set's timing animatic (the name is then the SET's) - with
-- the artefact's id as he saw it and, where it names them, the pictures (and the video) he
-- saw ("drawn"): the lock asks again when either changed (LaneLocks.holds). An artefact that does not exist, is out
-- of date or still has a problem cannot be approved: there is nothing true to show him yet.
-- `--expect <step:id:drawn>`: record only if the artefact is STILL the one named (kit review's page sends what it
-- showed; between its look and this command the artefact may have been drawn again).
-- `--locks <file>` with `--models <dir>` / `--effects <dir>`: a FIXTURE project's piece, recorded in that project's
-- own locks file (the kit's tests) - never the project's own record under another spelling (Locks.useFixture).
local Config = require("../lib/config")
local Locks = require("../lib/locks")
local Run = require("../lib/run")

local C = Run.CODES

local LANES = { "3d", "vfx", "ui", "anim", "world", "sfx" }

-- the steps a waiver may name, per lane ("verdict" = the open-pieces cap in kit new)
local STEPS: { [string]: { string } } = {
	vfx = { "chart", "frames", "verdict", "methods", "style", "animatic" }, -- (methods: the method gate, kit/vfx/methods.py; style / animatic: the stage locks)
	ui = { "refs", "verdict" },
	sfx = { "refs", "verdict" },
	-- methods: the methods lock (a new piece's plan names each coded part's builder call; kit/blender/rbx_plan.py)
	["3d"] = { "brief", "study", "verdict", "sheet", "blockout", "methods" },
	world = { "refs", "verdict", "layout", "streaming" },
	anim = { "evidence", "verdict" },
}

-- the stages whose artefact the owner approves one by one (`--stage`), per lane
local STAGES: { [string]: { string } } = {
	["3d"] = { "sheet", "blockout" },
	-- style: every beat's look, ours beside the scene's (kit vfx stylesheet <effect>; the VFX studio-route plan, V1)
	-- animatic: a scene SET's motion in flat shapes at the chart's timing (kit vfx animatic <set>; V2) - the name
	-- given with it is the set's
	vfx = { "style", "animatic" },
	-- blocking: a move's key poses held large (kit anim block <Move> --sheet); design: an attack set's page (kit anim
	-- design <Set>) - recorded where the lane's own --approve writes them (AnimCmd.stageApprove; card rpdz)
	anim = { "blocking", "design" },
	-- greybox: the world with no mesh, walked with him (kit world greybox <Name>; V3 W1); corner: one 40 x 40 corner at
	-- full size, his 7 or more (kit world corner <Name> --at <station>; V3 W2)
	world = { "greybox", "corner" },
}

-- the command that makes a stage's artefact, to name in a refusal
local function makes(lane: string, step: string, name: string): string
	return if lane == "vfx" and step == "animatic"
		then `lune run kit vfx animatic {name}`
		elseif lane == "vfx" then `lune run kit vfx stylesheet {name}`
		elseif lane == "anim" and step == "blocking" then `lune run kit anim block {name} --sheet`
		elseif lane == "anim" then `lune run kit anim design {name}`
		elseif lane == "world" and step == "corner" then `lune run kit world corner {name} --at <station>`
		elseif lane == "world" then `lune run kit world greybox {name}`
		else `lune run kit {step} {name}`
end

local function today(): string
	return os.date("%Y-%m-%d") :: string
end

local function list(lane: string?): number
	local data = Locks.load()
	local n = 0
	for _, key in { "approvals", "waivers", "proposals" } do
		local records = data[key]
		if type(records) == "table" then
			for l, byLane in records do
				if (not lane or l == lane) and type(byLane) == "table" then
					for name, rec in byLane do
						n += 1
						local state = if Locks.isOwner(rec) then "owner" else "PENDING (not the owner's)"
						local steps = if type(rec.steps) == "table" then ` steps={table.concat(rec.steps, ",")}` else ""
						print(`  {key}  {l}/{name}  [{state}]{steps}  "{rec.words or ""}"  {rec.date or ""}`)
					end
				end
			end
		end
	end
	-- the stage approvals (--stage): one record per piece and stage, with the artefact's id he saw
	local stages = data.stages
	if type(stages) == "table" then
		for l, byLane in stages do
			if (not lane or l == lane) and type(byLane) == "table" then
				for name, steps in byLane do
					if type(steps) == "table" then
						for step, rec in steps do
							n += 1
							local state = if Locks.isOwner(rec) then "owner" else "PENDING (not the owner's)"
							print(
								`  stages  {l}/{name}  [{state}] stage={step} id={tostring(rec.id)}  "{rec.words or ""}"  {rec.date or ""}`
							)
						end
					end
				end
			end
		end
	end
	return n
end

return function(Cli: any)
	Cli.command(
		"work",
		"approve",
		'approve <lane> <name> "<the owner\'s words>" --by owner [--waive <step,...> | --stage <sheet|blockout|style|animatic|blocking|design> [--id <id>] [--expect <step:id:drawn>]] | approve list [<lane>]',
		"record the OWNER's go-ahead (or a waiver of one step) for a new piece; --stage: his yes to ONE stage's artefact as it is now (3d: the model sheet, the blockout; vfx: an effect's style sheet, a scene set's timing animatic - asked again when it changes or is made again); --expect: only if it is still the one that was looked at; the lane locks accept nothing else",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			if args[1] == "list" then
				local n = list(args[2])
				return Run.report(
					"approve",
					{},
					C.PASS,
					`approve: {n} record(s){if args[2] then " in " .. args[2] else ""}`,
					'record one only when the owner said it: lune run kit approve <lane> <name> "<their words>" --by owner'
				)
			end
			local lane, name, words = args[1], args[2], args[3]
			if not lane or not table.find(LANES, lane) or not name or not words or words == "" then
				return Run.report(
					"approve",
					{},
					C.USAGE,
					`approve: name the lane ({table.concat(LANES, "|")}), the piece and the owner's own words`,
					'lune run kit approve vfx FlameArcSlash "approved, go" --by owner'
				)
			end
			local by = if flags.by == "owner" then "owner" else "model-proposed"
			local rec: any = { by = by, words = words, date = today() }
			-- how the record was made, when not typed: kit review's page says "review-page" (a click, not a session)
			if type(flags.via) == "string" then
				rec.via = flags.via
			end
			-- --locks <file>: a FIXTURE project's own record (the kit's tests, kit review on a fixture). Whatever this
			-- command records then lands there, never in the project's board/locks.json
			if type(flags.locks) == "string" then
				local why = Locks.useFixture(flags.locks)
				if why then
					return Run.report(
						"approve",
						{},
						C.USAGE,
						`approve: {why}`,
						`lune run kit approve {lane} {name} "<their words>" --by owner`
					)
				end
			end
			local key = "approvals"
			if flags.stage ~= nil then
				-- ONE stage's artefact (3d: the model sheet, the blockout), approved as it is now
				local steps = STAGES[lane]
				local step = flags.stage
				if type(step) ~= "string" or not steps or not table.find(steps, step) or flags.waive ~= nil then
					return Run.report(
						"approve",
						{},
						C.USAGE,
						if steps
							then `approve: --stage names one of {lane}'s stages ({table.concat(steps, ", ")}), without --waive`
							else `approve: the {lane} lane has no stage approvals (3d: sheet, blockout; vfx: style, animatic; anim: blocking, design)`,
						`lune run kit approve {if steps then lane else "3d"} {name} "<their words>" --by owner --stage {if steps
							then steps[1]
							else "sheet"}`
					)
				end
				if lane == "anim" then
					-- the animation lane keeps these records itself (its blocking and design files, which its locks read): his
					-- yes goes there, held to the id of the sheet or page he saw (--id), never a proposal
					if by ~= "owner" or type(flags.id) ~= "string" or flags.id == "" then
						return Run.report(
							"approve",
							{},
							C.USAGE,
							`approve: an animation {step} is approved only by the owner, for the id on what he saw: --by owner --id <id>`,
							`{makes(lane, step :: string, name)}, show it, then: lune run kit approve anim {name} "<their words>" --by owner --stage {step} --id <id>`
						)
					end
					local AnimCmd = require("./anim")
					local s = AnimCmd.stageApprove(step :: string, name, words, by, flags.id :: string)
					local said = if s.result and type(s.result.summary) == "string" then s.result.summary else s.tail
					return Run.report(
						"approve",
						{ s },
						if s.ok then C.PASS else C.CONTENT,
						if s.ok
							then `approve: anim/{name} {step} {flags.id} recorded as the owner's ("{words}")`
							else `approve: anim/{name} {step}: nothing recorded - {said}`,
						if s.ok
							then `commit its record with the move; it holds while the {step} stays as he saw it`
							else `{makes(lane, step :: string, name)}, look at it, show the owner, then record their words`
					)
				end
				-- (--models <folder> / --effects <folder>: a FIXTURE project's piece, as kit review --models --locks
				-- shows it, recorded in that project's own locks file (--locks <file>, above). Refused while the
				-- record is the project's own: another folder's sheet id written there would read as "changed")
				local models = if type(flags.models) == "string" then flags.models else nil
				if models and not Locks.fixture then
					return Run.report(
						"approve",
						{},
						C.USAGE,
						"approve: --models is for a fixture project's piece with a locks file of its own (--models <dir> --locks <file>)",
						`lune run kit approve {lane} {name} "<their words>" --by owner --stage {step}`
					)
				end
				local LaneLocks = require("../lib/lanelocks")
				-- an effect is the ACTIVE project's (the folder kit vfx stylesheet draws from): another folder's
				-- preset must never be recorded under this project's name
				local effects = Config.path("vfx")
				if lane == "vfx" and type(flags.effects) == "string" and not Locks.fixture then
					if string.lower(Locks.normal(flags.effects)) ~= string.lower(Locks.normal(effects)) then
						return Run.report(
							"approve",
							{},
							C.USAGE,
							`approve: --effects {flags.effects} is not this project's effects folder ({effects}); another game's piece: --game <Name>`,
							`lune run kit approve vfx {name} "<their words>" --by owner --stage {step}`
						)
					end
				elseif lane == "vfx" and type(flags.effects) == "string" then
					effects = flags.effects
				end
				local art = if lane == "vfx"
					then LaneLocks.vfxStageState(name, step :: string, effects)
					elseif lane == "world" then LaneLocks.worldStageState(name, step :: string)
					else LaneLocks.stageState(name, step :: string, models)
				if not art.ok then
					return Run.report(
						"approve",
						{},
						C.CONTENT,
						`approve: {lane}/{name} has no {step} he can approve - {art.why}`,
						`{makes(lane, step :: string, name)}, LOOK at it, show the owner, then record their words`
					)
				end
				-- a yes is for what was LOOKED AT: a caller that knows what that was says so (--expect: kit review's
				-- page sends what it showed), and an artefact that changed between the look and this command is refused
				local now = `{step}:{tostring(art.id or "")}:{tostring((art :: any).drawn or "")}`
				if type(flags.expect) == "string" and flags.expect ~= now then
					return Run.report(
						"approve",
						{},
						C.CONTENT,
						`approve: {lane}/{name}'s {step} is not the one that was looked at (it changed since): nothing recorded`,
						`look at it again as it is now, then approve`
					)
				end
				rec.id = art.id
				rec.stage = step
				if (art :: any).drawn ~= nil then
					rec.drawn = (art :: any).drawn -- (the pictures he saw: the same id drawn again is asked again)
				end
				Locks.reset() -- (the file as it is NOW: a record another session wrote meanwhile is kept)
				local data = Locks.load()
				local into = if by == "owner" then "stages" else "proposals"
				data[into] = if type(data[into]) == "table" then data[into] else {}
				data[into][lane] = if type(data[into][lane]) == "table" then data[into][lane] else {}
				if by == "owner" then
					local byName = data.stages[lane][name]
					data.stages[lane][name] = if type(byName) == "table" then byName else {}
					data.stages[lane][name][step] = rec
				else -- (a proposal lives in its own table: it never reads as the owner's record)
					rec.kind = "stages"
					data.proposals[lane][`{name}@{step}`] = rec
				end
				Locks.save(data)
				if by ~= "owner" then
					return Run.report(
						"approve",
						{},
						C.PASS,
						`approve: {lane}/{name} {step} PROPOSED (model-proposed: no lock accepts it)`,
						`show {art.png or step} to the owner; when they approve, record their words: lune run kit approve {lane} {name} "<their words>" --by owner --stage {step}`
					)
				end
				return Run.report(
					"approve",
					{},
					C.PASS,
					`approve: {lane}/{name} {step} {tostring(art.id)} recorded as the owner's ("{words}")`,
					`commit board/locks.json with the piece; it holds while the {step} stays as he saw it`
				)
			end
			if flags.waive ~= nil then
				if type(flags.waive) ~= "string" then
					return Run.report(
						"approve",
						{},
						C.USAGE,
						`approve: --waive needs the step(s) ({table.concat(STEPS[lane], ",")})`,
						`lune run kit approve {lane} {name} "<their words>" --by owner --waive {STEPS[lane][1]}`
					)
				end
				local steps = string.split(flags.waive :: string, ",")
				for _, step in steps do
					if not table.find(STEPS[lane], step) then
						return Run.report(
							"approve",
							{},
							C.USAGE,
							`approve: "{step}" is not a {lane} step ({table.concat(STEPS[lane], ", ")})`,
							`lune run kit approve {lane} {name} "<their words>" --by owner --waive {STEPS[lane][1]}`
						)
					end
				end
				rec.steps = steps
				key = "waivers"
			end
			local what = if key == "waivers" then `waiver of {table.concat(rec.steps, ",")}` else "approval"
			-- a proposal lives in its own table: it never replaces (or reads as) the owner's record
			if by ~= "owner" then
				rec.kind = key
				key = "proposals"
			end
			local data = Locks.load()
			data[key] = if type(data[key]) == "table" then data[key] else {}
			data[key][lane] = if type(data[key][lane]) == "table" then data[key][lane] else {}
			local old = data[key][lane][name]
			-- a second owner waiver adds its steps to the first (--waive verdict keeps an earlier refs waiver)
			if key == "waivers" and Locks.isOwner(old) and type(old.steps) == "table" then
				for _, step in old.steps do
					if not table.find(rec.steps, step) then
						table.insert(rec.steps, step)
					end
				end
				table.sort(rec.steps)
			end
			data[key][lane][name] = rec
			Locks.save(data)
			if by ~= "owner" then
				return Run.report(
					"approve",
					{},
					C.PASS,
					`approve: {lane}/{name} {what} PROPOSED (model-proposed: no lock accepts it)`,
					`show it to the owner; when they approve, record their words: lune run kit approve {lane} {name} "<their words>" --by owner`
				)
			end
			return Run.report(
				"approve",
				{},
				C.PASS,
				`approve: {lane}/{name} {what} recorded as the owner's ("{words}")`,
				`commit board/locks.json with the piece, then run its build command`
			)
		end
	)
end

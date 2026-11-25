-- vault.luau — the knowledge vault commands (kit/lib/vault.luau holds the format and the reads).
--   kit verdict <kind> <name> <0-10 | 0-100 | keep | redo> "<the owner's words>" [--shown <file>] [--tag a,b]
--               [--vs <other>] [--build <id>] [--feature "<what decided it>"] [--inferred] [--quoted-from "<where>"]
--               [--date YYYY-MM-DD] [--as who]
--               ONE record of the owner's verdicts, for every kind; ≥ 7 lands in the golden set, ≤ 3 in the graveyard;
--               Keep / Redo is a direction without a number (never averaged, never golden / graveyard); --shown keeps
--               a small copy of what the owner looked at beside the note (kit/tools/judged.py)
--   kit verdict list [kind] [name] [--n 20]       the record, newest first
--   kit vault check                              the health gate (frontmatter, links, indexes) — inside kit verify
--   kit vault page <dept> [--full] [--budget N]  the department page a model reads before building
--   kit vault index [dept]                       refresh every department's auto block (counts, last handoff)
--   kit vault grave <dept> "<tried>" --result "..." --words "<owner>" --why "<do not retry because>" [--link x]
--   kit vault golden <dept> <piece> --score N --words "<owner>" --feature "<what decided it>" [--link x]
--   kit vault prune-verdicts [--dry-run]          retire .verify verdict files whose input is gone (reports, not gates)
--   kit vault calibrate                          how each department's judge scores track the owner's verdicts
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Board = require("../lib/board")
local Cli = require("../lib/cli")
local Config = require("../lib/config")
local Directors = require("../lib/directors")
local Parts = require("../lib/parts")
local Run = require("../lib/run")
local Vault = require("../lib/vault")

local C = Run.CODES

local function usage(file: string, msg: string, example: string): number
	return Run.report(file, {}, C.USAGE, msg, example)
end

local function split(csv: string?): { string }
	local out = {}
	if type(csv) == "string" then
		for part in string.gmatch(csv, "[^,]+") do
			local t = string.gsub(string.gsub(part, "^%s+", ""), "%s+$", "")
			if t ~= "" then
				table.insert(out, t)
			end
		end
	end
	return out
end

-- 0-10 (one decimal); a 0-100 grade is read as /10 (the owner grades 3D on 100)
local function score10(raw: string?): number?
	local n = tonumber(raw)
	if not n or n < 0 or n > 100 then
		return nil
	end
	if n > 10 then
		n = n / 10
	end
	return math.floor(n * 10 + 0.5) / 10
end

local function words(n: Vault.Note, max: number): string
	local w = string.gsub(n.body, "%s+", " ")
	w = string.gsub(w, "^%s+", "")
	if #w > max then
		w = string.sub(w, 1, max - 3) .. "..."
	end
	return w
end

local function budget(): number
	local cfg = Config.load()
	local b = cfg.vault and tonumber(cfg.vault.budget)
	return b or 1500
end

local record = Vault.record

local VaultCmd = {}
VaultCmd.record = record

-- ------------------------------------------------------------ .verify hygiene (reports vs gates)
-- a verdict file is STALE when the thing it judged no longer exists (a probe's build script, a tournament candidate
-- preset) or the run was a usage error; retiring it keeps `kit status` honest. Content verdicts below a bar are
-- REPORTS (the bar is the owner's), never gate failures.
local function verdictInput(name: string): (string?, string?)
	local kind, rest = string.match(name, "^([%w_]+)%-(.+)$")
	if not kind then
		return nil, nil
	end
	if kind == "asset" or kind == "optimize" or kind == "showcase" then
		local asset = string.gsub(rest, "^geo%-", "")
		return `{Config.path("models")}/build_{asset}.py`, asset
	elseif kind == "vfx" then
		return `{Config.path("vfx")}/{rest}.json`, rest
	elseif kind == "ui" then
		return `{Config.path("ui")}/{rest}.json`, rest
	elseif kind == "sfx" then
		return `{Config.path("sounds")}/{rest}.json`, rest
	elseif kind == "anim" then
		return `{Config.path("anims")}/{rest}.json`, rest
	elseif kind == "judge" then
		return `{Config.path("models")}/build_{rest}.py`, rest
	end
	return nil, nil
end

function VaultCmd.pruneVerdicts(dryRun: boolean): ({ { file: string, why: string } }, number)
	local retired = {}
	local kept = 0
	if not fs.isDir(".verify") then
		return retired, 0
	end
	for _, file in fs.readDir(".verify") do
		if string.sub(file, -5) == ".json" then
			local name = string.sub(file, 1, -6)
			local okJson, v = pcall(serde.decode, "json" :: any, fs.readFile(".verify/" .. file))
			local why: string? = nil
			if okJson and type(v) == "table" then
				local input = verdictInput(name)
				if input and not fs.isFile(input) then
					why = `its input is gone ({input})`
				elseif v.exit == C.USAGE then
					why = "a usage error, not a gate result"
				elseif string.sub(name, 1, 1) == "_" or string.find(name, "%-_") or string.find(name, "%-tmp") then
					why = "a probe / temporary run"
				end
			end
			if why then
				table.insert(retired, { file = file, why = why })
				if not dryRun then
					Config.ensureDir(".verify/retired")
					fs.writeFile(".verify/retired/" .. file, fs.readFile(".verify/" .. file))
					fs.removeFile(".verify/" .. file)
				end
			else
				kept += 1
			end
		end
	end
	if not dryRun and #retired > 0 then
		local log = {}
		for _, r in retired do
			table.insert(log, `{Vault.today()} {r.file}: {r.why}`)
		end
		local path = ".verify/retired/REASONS.txt"
		local prev = if fs.isFile(path) then fs.readFile(path) else ""
		fs.writeFile(path, prev .. table.concat(log, "\n") .. "\n")
	end
	return retired, kept
end

local calibration = Vault.calibration
VaultCmd.calibration = calibration

-- ------------------------------------------------------------ commands
return function(Cli_: any)
	Cli_.command(
		"work",
		"verdict",
		'verdict <kind> <name> <0-10 | keep | redo> "<owner\'s words>" [--shown <picture or sound the owner saw>] [--route "what failed" (needed at 3 or less)] [--tag a,b] [--vs <other>] [--build <id>] [--feature "..."] [--inferred] [--quoted-from "..."] | verdict list [kind] [name] | verdict trend [kind] | verdict pending [lane]',
		"ONE record of the OWNER's verdicts for every kind (the only quality signal); ≥ 7 -> the golden set, ≤ 3 -> the graveyard",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			if args[1] == "trend" then
				local dept = Vault.dept(args[2])
				if args[2] and not dept then
					return usage("verdict", `verdict trend: unknown kind "{args[2]}"`, "lune run kit verdict trend 3d")
				end
				for _, l in Vault.trend(dept) do
					print("  " .. l)
				end
				return Run.report(
					"verdict",
					{},
					C.PASS,
					"verdict trend: see the lines above (a report, never a target)",
					"a department whose trend is flat for a week needs a route change, not another round"
				)
			end
			-- what waits for the owner's NUMBER: new pieces with no owner score (the verdict cap counts them) and pieces
			-- whose newest verdict a model inferred from the owner's words (the plan's C7: more scores from the owner)
			if args[1] == "pending" then
				local SCORE: { [string]: { string } } = {
					["3d"] = {
						"asset",
						'lune run kit rate make <round> <asset> (a grading page), or kit verdict asset <name> <0-10> "<words>"',
					},
					vfx = { "vfx", 'lune run kit vfx vault verdict <effect> "<words>" --score <0-10>' },
					ui = { "screen", 'lune run kit ui judge <Screen> --owner <score> "<words>"' },
					sfx = { "sound", "lune run kit sfx listen <name> (the listening booth)" },
					anim = {
						"anim",
						'lune run kit anim verdict <Name> <word> "<why>" (or kit verdict anim <Name> <0-10> "<words>")',
					},
					world = { "world", 'lune run kit verdict world <Name> <0-10> "<words>"' },
				}
				local depts = {}
				local only = Vault.dept(args[2])
				if args[2] and (not only or not SCORE[only]) then
					return usage(
						"verdict",
						`verdict pending: "{args[2]}" is not a content lane`,
						"lune run kit verdict pending vfx"
					)
				end
				for _, d in { "3d", "vfx", "ui", "sfx", "anim", "world" } do
					if not only or only == d then
						table.insert(depts, d)
					end
				end
				local LaneLocks = require("../lib/lanelocks")
				local total = 0
				for _, d in depts do
					local open = LaneLocks.unscored(d, { Config.root() }) -- (this project's: the cap is per game)
					-- the newest verdict per piece; listed when it was inferred
					local newest: { [string]: any } = {}
					for _, v in Vault.verdicts(d) do -- newest first
						local key = string.lower(tostring(v.front.name or ""))
						if key ~= "" and newest[key] == nil then
							newest[key] = v
						end
					end
					local guessed = {}
					for _, v in newest do
						if not Vault.ownersOwn(v.front) then
							table.insert(guessed, `{v.front.name} ({v.front.score}/10 read from the owner's words)`)
						end
					end
					table.sort(guessed)
					if #open + #guessed > 0 then
						print(`  {d}  ({SCORE[d][2]})`)
						if #open > 0 then
							print(
								`    new, no owner score ({#open}/{LaneLocks.OPEN_CAP} of the cap): {table.concat(
									open,
									", "
								)}`
							)
						end
						if #guessed > 0 then
							local shown = {}
							for i = 1, math.min(8, #guessed) do
								table.insert(shown, guessed[i])
							end
							print(
								`    a model's score only ({#guessed}): {table.concat(shown, "; ")}{if #guessed > 8
									then "; ..."
									else ""}`
							)
						end
					end
					total += #open + #guessed
				end
				return Run.report(
					"verdict",
					{},
					C.PASS,
					`verdict pending: {total} piece(s) wait for the owner's own number{if only
						then " in " .. only
						else ""}`,
					if total > 0
						then "show the owner the newest ones; record their number with the lane's command above"
						else "nothing waits for the owner's score"
				)
			end
			-- enforced learning (board/plans/archive/2026-11-09-enforced-learning-plan.md, rule 1): what each lane's verdicts owe
			if args[1] == "owed" then
				local dept = Vault.dept(args[2])
				if args[2] and not dept then
					return usage("verdict", `verdict owed: unknown lane "{args[2]}"`, "lune run kit verdict owed 3d")
				end
				local total = 0
				for _, d in if dept then { dept } else Vault.DEPTS do
					for _, line in Vault.owedLines(d) do
						print(`  {d}: {line}`)
						total += 1
					end
				end
				return Run.report(
					"verdict",
					{},
					C.PASS,
					`verdict owed: {total} verdict(s) owe their lesson{if dept then " in " .. dept else ""}`,
					if total > 0
						then 'pay each: lune run kit lesson <lane> "<what it taught>" --verdict <name>, or lune run kit verdict learned <kind> <name> none "<why it taught nothing new>"'
						else "nothing owed"
				)
			end
			if args[1] == "learned" then
				local kind, name = args[2], args[3]
				local dept = Vault.dept(kind)
				local rest = { table.unpack(args, 4) }
				local why = if rest[1] == "none" then table.concat(rest, " ", 2) else nil
				local ids = {}
				if not why then
					for _, a in rest do
						for id in string.gmatch(a, "[^,%s]+") do
							table.insert(ids, id)
						end
					end
				end
				if not dept or not name or (not why and #ids == 0) then
					return usage(
						"verdict",
						"verdict learned: needs <kind> <name> and the lesson ids it taught, or none and why it taught nothing new",
						'lune run kit verdict learned asset car_wheel_rim L-3d-7a7b24,L-3d-f74da4  |  ... none "<why, at least 6 words>"'
					)
				end
				-- every verdict on the piece that still owes (one lesson can be what each taught), else its newest verdict
				-- (a grandfathered one may be paid too)
				local targets: { Vault.Note } = {}
				for _, v in Vault.owedLearning(dept) do
					if string.lower(tostring(v.front.name)) == string.lower(name) then
						table.insert(targets, v)
					end
				end
				if #targets == 0 then
					local newestOne = Vault.verdicts(dept, name)[1]
					if newestOne then
						table.insert(targets, newestOne)
					end
				end
				if #targets == 0 then
					return usage(
						"verdict",
						`verdict learned: no verdict on {name} in {dept}`,
						`lune run kit verdict list {kind}`
					)
				end
				-- a lesson pays only what it can have been taught by the verdict: one of this lane, written on or after it
				local latest = ""
				for _, v in targets do
					local d = tostring(v.front.date or "")
					if d > latest then
						latest = d
					end
				end
				for _, id in ids do
					local lesson = Vault.lessonById(id)
					if not lesson then
						return usage(
							"verdict",
							`verdict learned: no lesson has the id {id}`,
							`lune run kit lessons {dept}`
						)
					end
					local ldept = string.match(id, "^L%-([^%-]+)%-")
					if ldept ~= dept then
						return usage(
							"verdict",
							`verdict learned: {id} is a {ldept} lesson - a {dept} verdict is paid with what it taught its own lane`,
							`lune run kit lesson {dept} "<what it taught>" --verdict {name}`
						)
					end
					if tostring(lesson.front.date or "") < latest then
						return usage(
							"verdict",
							`verdict learned: {id} was written {lesson.front.date}, before the verdict ({latest}) - it cannot be what the verdict taught`,
							`lune run kit lesson {dept} "<what it taught>" --verdict {name}`
						)
					end
				end
				for _, target in targets do
					local ok, err = Vault.markLearned(target, if why then nil else ids, why)
					if not ok then
						return usage(
							"verdict",
							`verdict learned: {err}`,
							'lune run kit verdict learned <kind> <name> none "<why>"'
						)
					end
				end
				local left = #Vault.owedLearning(dept)
				return Run.report(
					"verdict",
					{},
					C.PASS,
					`verdict learned: {#targets} verdict(s) on {name} - {if why
						then "nothing new: " .. why
						else table.concat(ids, ", ")}; {left} still owed in {dept}`,
					"commit kit/knowledge/vault"
				)
			end
			-- enforced learning, rule 3: pay a look a verdict owes - the lane's look of the piece's current version now
			-- exists, or --none says why it could not be taken
			if args[1] == "looked" then
				local kind, name = args[2], args[3]
				local dept = Vault.dept(kind)
				if not dept or not name then
					return usage(
						"verdict",
						"verdict looked: needs <kind> <name>",
						'lune run kit verdict looked asset car_wheel_rim  |  ... --none "<why the look could not be taken>"'
					)
				end
				local target: Vault.Note? = nil
				for _, v in Vault.owedLook(dept) do
					if string.lower(tostring(v.front.name)) == string.lower(name) then
						target = v
						break
					end
				end
				if not target then
					return Run.report(
						"verdict",
						{},
						C.PASS,
						`verdict looked: no verdict on {name} owes a look`,
						`lune run kit verdict owed {dept}`
					)
				end
				local why = if type(flags.none) == "string" then flags.none else nil
				if not why then
					local problem, cmd = require("../lib/lanelocks").lookProblem(kind, name)
					if problem then
						return Run.report(
							"verdict",
							{},
							C.CONTENT,
							`verdict looked: {problem} - take the look first`,
							`{cmd}, then lune run kit verdict looked {kind} {name}`
						)
					end
				end
				local ok, err = Vault.markLooked(target, why)
				if not ok then
					return usage(
						"verdict",
						`verdict looked: {err}`,
						'lune run kit verdict looked <kind> <name> --none "<why>"'
					)
				end
				return Run.report(
					"verdict",
					{},
					C.PASS,
					`verdict looked: {target.rel} - {if why then "no look: " .. why else "looked"}; {#Vault.owedLook(
						dept
					)} look(s) still owed in {dept}`,
					"commit kit/knowledge/vault"
				)
			end
			if args[1] == "list" then
				local dept = Vault.dept(args[2])
				if args[2] and not dept then
					return usage("verdict", `verdict list: unknown kind "{args[2]}"`, "lune run kit verdict list asset")
				end
				local list = Vault.verdicts(dept, args[3])
				local n = tonumber(flags.n) or 20
				for i = 1, math.min(n, #list) do
					local f = list[i].front
					print(
						`  {f.date or "?"}  {f.area}  {f.name}  {if f.score ~= nil
							then f.score .. "/10"
							elseif Vault.direction(f) == "keep" then "Keep"
							elseif Vault.direction(f) == "redo" then "Redo"
							else "(no number)"}{if f.source ~= "owner" then " [" .. tostring(f.source) .. "]" else ""}  — {words(
							list[i],
							140
						)}`
					)
				end
				return Run.report(
					"verdict",
					{},
					C.PASS,
					`verdict list: {#list} verdict(s){if dept then " for " .. dept else ""}{if args[3]
						then " on " .. args[3]
						else ""}`,
					"the owner's eye is the bar: build toward the golden set, never a graveyard route"
				)
			end
			local kind, name, rawScore = args[1], args[2], args[3]
			local text = table.concat(args, " ", 4)
			-- the owner's Keep / Redo in place of a number (2026-11-08): a direction, never averaged, never golden or
			-- graveyard; it still credits or blames the lessons named or shown for the piece
			local lowered = if rawScore then string.lower(rawScore) else nil
			local direction = if lowered and Vault.DIRECTIONS[lowered] then lowered else nil
			local score = if direction then nil else score10(rawScore)
			if not kind or not name or not (score or direction) or text == "" then
				return usage(
					"verdict",
					"verdict: needs <kind> <name> <0-10 | keep | redo> and the owner's words",
					'lune run kit verdict screen Arcade5Title 9.2 "GENUINELY AMAZED BY HOW WELL MADE THAT IS" --tag persona,lettering'
				)
			end
			local label = if score then `{score}/10` elseif direction == "keep" then "Keep" else "Redo"
			-- what the owner looked at, kept beside the note: one small copy per source file (kit/tools/judged.py)
			local judged: string? = nil
			local shown = if type(flags.shown) == "string" and flags.shown ~= "" then flags.shown else nil
			if shown then
				local dept = Vault.dept(kind)
				if not dept then
					return usage(
						"verdict",
						`verdict: unknown kind "{kind}"`,
						'lune run kit verdict anim Name keep "..."'
					)
				end
				local step =
					Run.spawn("judged", Run.tool("python"), { "kit/tools/judged.py", shown, Vault.dir(dept) }, true)
				local r = step.result or {}
				if not step.ok or type(r.rel) ~= "string" then
					return usage(
						"verdict",
						`verdict: --shown {shown}: {r.error or step.tail}`,
						"pass the picture (png/jpg/webp/gif) or sound (wav/ogg/mp3/flac) the owner was shown"
					)
				end
				judged = r.rel
			end
			-- a rejection names the ROUTE that failed (how it was made: the method, the generator, the look), so the
			-- graveyard row stops the next session retrying it; a row that names only the piece stops nothing
			-- (never refused for it: the owner's verdict is recorded whatever - kit/ui/rate.py and kit/grading/round.py
			-- call this without a route - and the missing route is asked for after)
			local route = if type(flags.route) == "string" and flags.route ~= "" then flags.route else nil
			local routeMissing = score ~= nil and score <= 3 and not route
			-- enforced learning, rule 3: did the session LOOK at this version with the lane's own look tool before the
			-- owner judged it? Recorded either way (never refused: the owner's words always land); a missing look is owed
			local lookProblem, lookCmd, lookKnown = require("../lib/lanelocks").lookProblem(kind, name)
			local path, err = record({
				look = if lookProblem then "missing" elseif lookKnown then "seen" else nil,
				kind = kind,
				name = name,
				score = score,
				direction = direction,
				judged = judged,
				judgedFrom = shown,
				words = text,
				tags = split(flags.tag),
				vs = if type(flags.vs) == "string" then flags.vs else nil,
				build = if type(flags.build) == "string" then flags.build else nil,
				feature = if type(flags.feature) == "string" then flags.feature else nil,
				inferred = flags.inferred == true,
				quotedFrom = if type(flags["quoted-from"]) == "string" then flags["quoted-from"] else nil,
				date = if type(flags.date) == "string" then flags.date else nil,
				by = if type(flags.as) == "string" then flags.as else nil,
				route = route,
			})
			if not path then
				return usage("verdict", `verdict: {err}`, 'lune run kit verdict asset hydrant 8 "..."')
			end
			Board.journal(Board.agent(flags.as), `verdict {kind} {name} {label}: {string.sub(text, 1, 80)}`)
			-- the learning loop, visible: the lessons named or shown for this piece now carry this verdict
			local named, served = Vault.creditedOn(kind, name, string.sub(path, #Vault.ROOT + 2, -4))
			if #named + #served > 0 then
				local pol = if score
					then (if score >= 7 then 1 elseif score <= 3 then -1 else 0)
					else Vault.DIRECTIONS[direction :: string]
				local verb = if pol == 1
					then "credited as helpful"
					elseif pol == -1 then "blamed as harmful"
					else "counted (no credit: 4-6)"
				print(
					`  lessons on {name}: {#named} named + {#served} shown - {verb} (kit vault garden flags the ones that keep failing)`
				)
			else
				print(
					`  no lesson was named or shown for {name}: the loop learns nothing from this verdict (next time: kit start <lane> --for {name})`
				)
			end
			-- what learns from this verdict BY ITSELF (sprint 3): the lane's director profile and its checks; the
			-- lane's parts library credits the cards the piece's parts sheet built from (P0 of the parts libraries)
			local vdept = Vault.dept(kind)
			for _, line in
				{
					Directors.relearn(vdept, if vdept then Vault.dir(vdept) else nil),
					Directors.retest(vdept, if vdept then Vault.dir(vdept) else nil),
					Directors.retaste(vdept),
					Parts.credit(vdept, name),
				}
			do
				print(`  {line}`)
			end
			-- enforced learning (rule 1): this verdict owes its lane a lesson; kit new and kit handoff refuse until paid
			local owes = false
			if vdept then
				local function norm(p: string): string
					return (string.gsub(p, "\\", "/"))
				end
				for _, v in Vault.owedLearning(vdept) do
					if norm(v.path) == norm(path) then
						owes = true
						break
					end
				end
			end
			if lookProblem then
				print(
					`  shown without the session's own look ({lookProblem}): it owes the {vdept} lane that look - {lookCmd}, then lune run kit verdict looked {kind} {name} (or --none "<why it could not be taken>")`
				)
			end
			if owes then
				print(
					`  this verdict owes the {vdept} lane its lesson: lune run kit lesson {vdept} "<what it taught>" --verdict {name}  (or, when it taught nothing new: lune run kit verdict learned {kind} {name} none "<why>")`
				)
			end
			return Run.report(
				"verdict",
				{},
				C.PASS,
				`verdict: {kind} {name} {label} recorded -> {path}{if score and score >= 7
					then " (+ golden)"
					elseif score and score <= 3 then " (+ graveyard)"
					else ""}{if judged then " (+ what the owner judged: " .. judged .. ")" else ""}{if routeMissing
					then " - the graveyard row names no route"
					else ""}`,
				if owes
					then `learn from it before anything else: lune run kit lesson {vdept} "<what it taught>" --verdict {name}{if routeMissing
						then " - then name the failed route: lune run kit vault grave"
						else ""}; commit kit/knowledge/vault`
					elseif
						routeMissing
					then `name the route that failed so no session retries it: lune run kit vault grave {Vault.dept(
						kind
					) or kind} "{name}: <how it was made - the method / look that failed>" --result "rejected ({score}/10)" --why "<the owner's reason>"; commit kit/knowledge/vault`
					elseif
						not judged
					then `next time add --shown <the picture or sound the owner saw> so the kit keeps what was judged; commit kit/knowledge/vault`
					else "commit kit/knowledge/vault; every department reads it in kit status / kit new"
			)
		end
	)

	-- the owner's recurring words as CHECKS on the work, kept honest by the owner's verdicts (2026-11-08, sprint 2: "your
	-- complaints turned into checks per lane"): kit/knowledge/vault/<lane>/checks.json + kit/checks/checks.py. A check's
	-- status comes from evidence only (proposed reports, validated may gate - stricter only -, retired stops); for the
	-- animation lane, validate also replays the gates' warnings measure by measure (kit/anim/check_validate.py).
	Cli_.command(
		"kit",
		"checks",
		"checks list|run|validate <lane> [target] [--dry]   (target - anim: <Move>/round_K, vfx: <effect>)",
		"the owner's recurring words as checks on the work: list them, run them on a piece, or test them against the owner's verdicts (status by evidence; a gate tightens only where it is proven)",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			local sub, lane = args[1], Vault.dept(args[2])
			if
				not (sub == "list" or sub == "run" or sub == "validate")
				or not lane
				or (sub == "run" and not args[3])
			then
				return usage(
					"checks",
					"checks: list|run|validate <lane> [target]",
					"lune run kit checks run anim DTDrillSpin/round_3"
				)
			end
			local argv = { "kit/checks/checks.py", sub, lane }
			if sub == "run" then
				table.insert(argv, args[3])
			end
			if flags.dry then
				table.insert(argv, "--dry")
			end
			local step = Run.spawn(`checks {sub} {lane}`, Run.tool("python"), argv, true)
			local r = step.result or {}
			for _, line in (if type(r.lines) == "table" then r.lines else {}) do
				print(line)
			end
			local steps = { step }
			-- the animation gates' warnings, measure by measure (sprint 1)
			local warn = nil
			if sub == "validate" and lane == "anim" and step.ok then
				local w = Run.spawn(
					"checks: the anim warnings",
					Run.tool("python"),
					if flags.dry then { "kit/anim/check_validate.py", "--dry" } else { "kit/anim/check_validate.py" },
					true
				)
				table.insert(steps, w)
				warn = w.result
				for line in string.gmatch(w.tail or "", "[^\n]+") do
					if string.sub(line, 1, 2) == "  " then
						print(line)
					end
				end
			end
			if not step.ok then
				return Run.report(
					"checks",
					steps,
					C.CONTENT,
					`checks {sub} {lane}: {r.error or "failed"}`,
					"read the error above"
				)
			end
			local summary
			if sub == "list" then
				summary = `checks list {lane}: {r.checks or 0} check(s) from the owner's words`
			elseif sub == "run" then
				local failed = if type(r.failed) == "table" then r.failed else {}
				summary = `checks run {lane} {args[3]}: {#failed} failing ({if #failed > 0
					then table.concat(failed, ", ")
					else "none"}), {r.measured or 0} measured`
			else
				local parts = {}
				for status, n in (if type(r.status) == "table" then r.status else {}) do
					table.insert(parts, `{n} {status}`)
				end
				table.sort(parts)
				summary =
					`checks validate {lane}: {if #parts > 0 then table.concat(parts, ", ") else "no checks"}{if warn
						then ` · the anim warnings: {warn.rejected_warned or 0} of {warn.rejected_candidates or 0} rejected and {warn.shown_warned or 0} of {warn.shown_candidates or 0} shown candidates, {warn.picked_measured or 0} picks measured`
						else ""}{if flags.dry
						then " (dry: nothing written)"
						elseif r.written == false then " (nothing changed: checks.json left as it was)"
						else ""}`
			end
			-- a step that failed (the anim warnings report too) is never reported as a pass
			local allOk = true
			for _, s in steps do
				if not s.ok then
					allOk = false
				end
			end
			return Run.report(
				"checks",
				steps,
				if allOk then C.PASS else C.CONTENT,
				if allOk then summary else summary .. " - a step failed (read above)",
				if sub == "validate" and not flags.dry
					then `commit kit/knowledge/vault/{lane}/checks.json; a proposed check reports, only a validated one may become a gate (stricter only)`
					elseif
						sub == "run"
					then "show the failing checks with the piece; they report, a proposed check never blocks"
					else `keep them honest: lune run kit checks validate {lane}`
			)
		end
	)

	Cli_.command(
		"kit",
		"vault",
		'vault check | page <dept> [--full] [--budget N] | index [dept] | grave <dept> "<tried>" --result --words --why | golden <dept> <piece> --score --words --feature | distil <dept> [--since D] [--rule "..."] [--edit "R-<dept>-<n>: ..."] [--retire "R-<dept>-<n>: why"] | sync [--dry-run] | prune-verdicts [--dry-run] | calibrate | garden [dept]',
		"the knowledge VAULT (kit/knowledge/vault: lessons, verdicts, graveyard, golden set per department) — health, pages, rows",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			local sub = args[1]
			if sub == "check" then
				local problems = Vault.check()
				for i = 1, math.min(#problems, 30) do
					print(`  {problems[i].path}: {problems[i].problem}`)
				end
				-- the weekly audit: warnings for a human's eyes (stale golden rows, graves without a reason or a
				-- source, verdicts without words); never a gate
				local warnings = Vault.audit()
				if #warnings > 0 then
					print(`  weekly ({#warnings} warning(s), not a gate):`)
					for i = 1, math.min(#warnings, 30) do
						print(`   ! {warnings[i].where}: {warnings[i].warning}`)
					end
				end
				-- the token meter: what each department's page costs a model as printed (within vault.budget) and
				-- in full, so growth shows before it hurts
				local meterParts = {}
				for _, m in Vault.tokenMeter(budget()) do
					table.insert(meterParts, `{m.dept} {m.shown}{if m.cut then string.format("/%d", m.full) else ""}`)
				end
				print(`  page tokens (shown{" /full when cut"}, budget {budget()}): {table.concat(meterParts, " · ")}`)
				local ok = #problems == 0
				return Run.report(
					"vault",
					{ Run.step("vault", ok, "", { summary = `{#problems} problem(s), {#warnings} warning(s)` }) },
					if ok then C.PASS else C.CONTENT,
					if ok
						then `vault: {#Vault.files()} note(s) healthy{if #warnings > 0
							then `, {#warnings} weekly warning(s)`
							else ""}`
						else `vault: {#problems} problem(s)`,
					if not ok
						then "fix the notes named above (frontmatter: area/kind/date; links must resolve)"
						elseif
							#warnings > 0
						then "show the weekly warnings to the owner (stale golden rows need their words)"
						else "none — proceed"
				)
			elseif sub == "garden" then
				-- the gardener: near-duplicate lessons, lessons / rules the verdicts flagged harmful, new before/after
				-- pairs (written as notes); it proposes, never deletes
				local depts = {}
				if args[2] then
					local d = Vault.dept(args[2])
					if not d then
						return usage(
							"vault",
							`vault garden: unknown department "{args[2]}"`,
							"lune run kit vault garden 3d"
						)
					end
					table.insert(depts, d)
				else
					depts = Vault.DEPTS
				end
				local n = 0
				for _, d in depts do
					local items = Vault.garden(d)
					if #items > 0 then
						print(`  {d}:`)
						for _, line in items do
							print(`    - {line}`)
						end
					end
					n += #items
				end
				return Run.report(
					"vault",
					{},
					C.PASS,
					`vault garden: {n} item(s){if args[2] then " in " .. args[2] else ""} (nothing deleted)`,
					if n > 0
						then "confirm each proposal (or leave it) with the command shown; commit kit/knowledge/vault"
						else "the record is tidy"
				)
			elseif sub == "playbook" then
				-- kit vault playbook <lane> [<family>] (sprint 5, family playbooks): a family's lessons, golden and graveyard
				-- pieces and rules - or, with no family, every family of the lane with its counts
				local lane = Vault.dept(args[2])
				if not lane then
					return Run.report(
						"vault",
						{},
						C.USAGE,
						"vault playbook: which lane?",
						"lune run kit vault playbook 3d firearm"
					)
				end
				for _, l in require("../lib/families").playbook(lane, args[3]) do
					print("  " .. l)
				end
				return Run.report(
					"vault",
					{},
					C.PASS,
					`vault playbook {lane}{if args[3] then " " .. args[3] else ""}: printed above (families: kit/knowledge/families.json)`,
					if args[3]
						then "read it before building a piece of this family; a lesson's own family: kit lesson ... --family <f>"
						else `lune run kit vault playbook {lane} <family>`
				)
			elseif sub == "eval" then
				-- kit vault eval [dept] [--k 6]: replay the pieces whose lessons a session named; did each order put
				-- them in front of it? (a report on the retrieval, never a gate: the owner's verdicts are the bar)
				local dept = nil
				if args[2] then
					dept = Vault.dept(args[2])
					if not dept then
						return usage(
							"vault",
							`vault eval: unknown department "{args[2]}"`,
							"lune run kit vault eval 3d"
						)
					end
				end
				local k = tonumber(flags.k) or 6
				local rows, old, new, fam = Vault.eval(dept, k)
				for _, r in rows do
					print(
						string.format(
							"  %-4s %-28s %s  %d named  newest-first %3d%%  ranked %3d%%  +family %3d%% (%s)  (%s)",
							r.case.dept,
							r.case.name,
							r.case.before,
							r.found,
							math.floor(r.old * 100 + 0.5),
							math.floor(r.new * 100 + 0.5),
							math.floor(r.fam * 100 + 0.5),
							r.family or "none",
							r.case.source
						)
					)
				end
				if not old then
					return Run.report(
						"vault",
						{},
						C.PASS,
						`vault eval: no piece has named lessons{if dept then " in " .. dept else ""} yet - nothing to replay`,
						"cite what you use (kit lesson used <ids> --piece <kind> <name>); every named piece becomes a case"
					)
				end
				return Run.report(
					"vault",
					{},
					C.PASS,
					string.format(
						"vault eval: %d piece(s) replayed - the named lessons in the top %d: newest-first %d%%, ranked %d%%, ranked + the piece's family %d%%%s",
						#rows,
						k,
						math.floor((old :: number) * 100 + 0.5),
						math.floor((new :: number) * 100 + 0.5),
						math.floor((fam :: number) * 100 + 0.5),
						if #rows < 10 then " (fewer than 10 cases: a direction, not a measurement)" else ""
					),
					"a study's lessons were picked from a word-ranked list (it favours the ranking); `named` cases are the fair ones - they grow with every kit lesson used"
				)
			elseif sub == "supersede" then
				-- kit vault supersede <newer note> <older note> [--why "..."]: the newer lesson / verdict replaces the
				-- older one; a superseded lesson drops out of kit lessons and the page (the record keeps it)
				local newer, older = args[2], args[3]
				if not newer or not older then
					return usage(
						"vault",
						'vault supersede: needs <newer note> <older note> [--why "..."]',
						'lune run kit vault supersede 3d/lessons/2026-10-16-bevel-every-edge 3d/lessons/2026-10-08-bevel-hero-only --why "the owner asked for every edge"'
					)
				end
				local ok, msg = Vault.supersede(newer, older, if type(flags.why) == "string" then flags.why else nil)
				return Run.report(
					"vault",
					{},
					if ok then C.PASS else C.USAGE,
					`vault supersede: {msg}`,
					if ok then "commit kit/knowledge/vault" else "name each note by its vault path"
				)
			elseif sub == "related" then
				-- kit vault related <note> [--hops 2] [--limit 25]: the notes linked to it, out and in, one line each
				-- kit vault related --words <w1> [w2 ...] [--limit N]: every note whose text holds ALL the words
				if flags.words ~= nil then
					local terms = {}
					if type(flags.words) == "string" then
						table.insert(terms, flags.words)
					end
					for i = 2, #args do
						table.insert(terms, args[i])
					end
					if #terms == 0 then
						return usage(
							"vault",
							"vault related: --words needs at least one word",
							"lune run kit vault related --words barrel"
						)
					end
					local list = Vault.search(terms, tonumber(flags.limit) or 25)
					for _, r in list do
						print(`  {r.rel} — {r.title}`)
					end
					return Run.report(
						"vault",
						{},
						C.PASS,
						`vault related: {#list} note(s) naming "{table.concat(terms, " ")}"`,
						"open the ones that matter: lune run kit vault page <dept>, or the file itself"
					)
				end
				local ref = args[2]
				if not ref then
					return usage(
						"vault",
						"vault related: needs a note",
						"lune run kit vault related ui/verdicts/witchgauge--2026-10-11"
					)
				end
				local list, err = Vault.related(ref, tonumber(flags.hops) or 2, tonumber(flags.limit) or 25)
				if err then
					return usage("vault", `vault related: {err}`, "lune run kit vault related <dept>/<folder>/<note>")
				end
				for _, r in list do
					print(`  {r.hop} {r.rel} — {r.title}`)
				end
				return Run.report(
					"vault",
					{},
					C.PASS,
					`vault related: {#list} note(s) within {tonumber(flags.hops) or 2} hop(s) of {ref}`,
					"open the ones that matter: lune run kit vault page <dept>, or the file itself"
				)
			elseif sub == "distil" then
				local dept = Vault.dept(args[2])
				if not dept then
					return usage(
						"vault",
						"vault distil: needs a department",
						`lune run kit vault distil 3d   ({table.concat(Vault.DEPTS, "|")})`
					)
				end
				-- one change to the live rules (rules.md): --edit "R-<dept>-<n>: new words", --retire "R-<dept>-<n>: why"
				for _, op in { "edit", "retire" } do
					local given = (flags.list and flags.list[op])
						or (if type(flags[op]) == "string" then { flags[op] } else nil)
					if given and #given > 0 then
						local done = {}
						for _, g in given do
							local id, said = string.match(g, "^%s*(R%-[%w]+%-%d+)%s*:%s*(.+)$")
							if not id then
								return usage(
									"vault",
									`vault distil --{op}: write it as "R-{dept}-<n>: <words>"`,
									`lune run kit vault distil {dept} --{op} "R-{dept}-1: {if op == "edit"
										then "the rule's new words"
										else "why it no longer holds (the verdict that killed it)"}"`
								)
							end
							local ok, why = Vault.ruleChange(dept, op, id, said)
							if not ok then
								return usage("vault", `vault distil --{op}: {why}`, `see {Vault.rulesPath(dept)}`)
							end
							table.insert(done, `{op == "edit" and "edited" or "retired"} {id}: {said}`)
						end
						Vault.logRuleChanges(dept, done, if type(flags.as) == "string" then flags.as else nil)
						local relearned = Directors.relearn(dept, Vault.dir(dept))
						if relearned then
							print(`  {relearned}`)
						end
						return Run.report(
							"vault",
							{},
							C.PASS,
							`vault distil: {#done} rule change(s) in {Vault.rulesPath(dept)} (logged in distil.md)`,
							"commit kit/knowledge/vault"
						)
					end
				end
				local since = if type(flags.since) == "string" then flags.since else nil
				local packet = Vault.distil(dept, since)
				local rules = (flags.list and flags.list.rule)
					or (if type(flags.rule) == "string" then { flags.rule } else nil)
				if rules and #rules > 0 then
					local path =
						Vault.writeDistil(dept, rules, packet, if type(flags.as) == "string" then flags.as else nil)
					local relearned = Directors.relearn(dept, Vault.dir(dept))
					if relearned then
						print(`  {relearned}`)
					end
					return Run.report(
						"vault",
						{},
						C.PASS,
						`vault distil: {#rules} rule(s) added to the live rules ({Vault.rulesPath(dept)}; history in {path}) from {#packet.verdicts} verdict(s) + {#packet.lessons} lesson(s)`,
						`a rule a later verdict kills: lune run kit vault distil {dept} --retire "R-{dept}-<n>: why"; commit kit/knowledge/vault`
					)
				end
				-- (enforced learning, rule 4) a window read whole that holds no new rule closes with why: the verdicts
				-- confirm the live rules - a distil never has to invent a rule to count
				local none = if type(flags.none) == "string" then flags.none else nil
				if none then
					if not Vault.reasonOk(none) then
						return usage(
							"vault",
							`vault distil --none: say why the window holds no new rule in at least {Vault.LEARN_WHY_WORDS} words (four real ones)`,
							`lune run kit vault distil {dept} --none "<why: the verdicts confirm R-{dept}-<n>, ...>"`
						)
					end
					if #packet.verdicts + #packet.lessons == 0 then
						return usage("vault", "vault distil --none: nothing landed since the last distil", "proceed")
					end
					local path =
						Vault.writeDistil(dept, {}, packet, if type(flags.as) == "string" then flags.as else nil, none)
					return Run.report(
						"vault",
						{},
						C.PASS,
						`vault distil: {dept} read {#packet.verdicts} verdict(s) + {#packet.lessons} lesson(s) - no new rule; the window is closed in {path}`,
						"commit kit/knowledge/vault"
					)
				end
				for _, l in packet.lines do
					print(l)
				end
				return Run.report(
					"vault",
					{},
					C.PASS,
					`vault distil: {dept} packet — {#packet.verdicts} verdict(s) + {#packet.lessons} lesson(s) since {packet.since or "the beginning"}`,
					if #packet.verdicts + #packet.lessons == 0
						then "nothing to distil — proceed"
						else `read the packet and the live rules (kit vault page {dept}), then add what is new (--rule "..."), fix what changed (--edit "R-{dept}-<n>: ..."), retire what a verdict killed (--retire "R-{dept}-<n>: why")`
				)
			elseif sub == "page" then
				local dept = Vault.dept(args[2])
				if not dept then
					return usage(
						"vault",
						"vault page: needs a department",
						`lune run kit vault page 3d   ({table.concat(Vault.DEPTS, "|")})`
					)
				end
				print(Vault.page(dept, if flags.full then 1e9 else tonumber(flags.budget) or budget()))
				return Run.report(
					"vault",
					{},
					C.PASS,
					`vault page: {dept}`,
					"read it before building; the golden set and the graveyard outrank your memory"
				)
			elseif sub == "index" then
				local depts = if args[2] then { Vault.dept(args[2]) } else Vault.DEPTS
				local handoff = Board.latest("handoffs")
				local done = {}
				for _, d in depts do
					if d and fs.isDir(Vault.dir(d)) then
						table.insert(done, Vault.refreshIndex(d, handoff))
					end
				end
				return Run.report("vault", {}, C.PASS, `vault index: {#done} refreshed`, "commit kit/knowledge/vault")
			elseif sub == "grave" then
				local dept = Vault.dept(args[2])
				local tried = args[3]
				if not dept or not tried or type(flags.why) ~= "string" then
					return usage(
						"vault",
						'vault grave: needs <dept> "<tried>" --result "..." --words "<owner>" --why "<do not retry because>"',
						'lune run kit vault grave 3d "whole-object generator for a hero pistol" --result "0-8/10 across 8 candidates" --words "both models are horrible" --why "slab sides, no 3D form; use per-part generation + a reference mesh"'
					)
				end
				Vault.row(dept, "graveyard.md", Vault.GRAVEYARD_HEADER, {
					tried,
					if type(flags.date) == "string" then flags.date else Vault.today(),
					if type(flags.result) == "string" then flags.result else "rejected",
					if type(flags.words) == "string" then flags.words else "",
					flags.why,
					if type(flags.link) == "string" then flags.link else "",
				})
				return Run.report(
					"vault",
					{},
					C.PASS,
					`vault grave: {dept} row added`,
					"kit status prints the graveyard before any build"
				)
			elseif sub == "golden" then
				local dept = Vault.dept(args[2])
				local piece = args[3]
				if not dept or not piece or type(flags.words) ~= "string" then
					return usage(
						"vault",
						'vault golden: needs <dept> <piece> --score N --words "<owner>" --feature "<what decided it>"',
						'lune run kit vault golden ui WitchGauge --score 8.5 --words "GENUINELY IMPRESSED" --feature "rendered chrome troughs + glass cells following the bowed holder"'
					)
				end
				Vault.row(dept, "golden.md", Vault.GOLDEN_HEADER, {
					piece,
					if flags.score then tostring(score10(flags.score) or flags.score) else "",
					if type(flags.date) == "string" then flags.date else Vault.today(),
					flags.words,
					if type(flags.feature) == "string" then flags.feature else "",
					if type(flags.link) == "string" then flags.link else "",
				})
				return Run.report(
					"vault",
					{},
					C.PASS,
					`vault golden: {dept} row added`,
					"kit new prints the golden set for its kind"
				)
			elseif sub == "sync" then
				-- the stores other commands still write on their own (the sfx booth's <name>.verdict.json, the anim
				-- book's verdicts.json, a UI judge's owner block, kit/lessons) pulled into the vault; idempotent, so
				-- it runs at any time (kit status asks for it when a store is newer than the vault)
				local step = Run.spawn(
					"vault sync",
					Run.tool("python"),
					{ "kit/scripts/vault_migrate.py", table.unpack(if flags["dry-run"] then { "--dry-run" } else {}) },
					true
				)
				local r = step.result or {}
				return Run.report(
					"vault",
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					if step.ok
						then `vault sync: {r.verdicts or 0} verdict(s), {r.lessons or 0} lesson(s), {r.rows or 0} row(s) pulled in ({r.skipped or 0} already there){if flags["dry-run"]
							then " (dry run)"
							else ""}`
						else "vault sync failed",
					if step.ok then "lune run kit vault check; commit kit/knowledge/vault" else "read the error above"
				)
			elseif sub == "prune-verdicts" then
				local dry = flags["dry-run"] == true
				local retired, kept = VaultCmd.pruneVerdicts(dry)
				for i = 1, math.min(#retired, 40) do
					print(`  {if dry then "would retire" else "retired"} {retired[i].file}: {retired[i].why}`)
				end
				return Run.report(
					"vault",
					{},
					C.PASS,
					`vault prune-verdicts: {#retired} retired{if dry then " (dry run)" else ""}, {kept} kept`,
					if dry
						then "run it without --dry-run to move them to .verify/retired/"
						else "kit status now counts only live gates"
				)
			elseif sub == "calibrate" then
				for _, l in calibration() do
					print("  " .. l)
				end
				return Run.report(
					"vault",
					{},
					C.PASS,
					"vault calibrate: see the lines above",
					"a judge that does not track the owner finds bugs, never the bar"
				)
			end
			return usage(
				"vault",
				"vault: unknown subcommand",
				"lune run kit vault check | page <dept> | index | grave | golden | distil <dept> | sync | prune-verdicts | calibrate"
			)
		end
	)
	return VaultCmd
end

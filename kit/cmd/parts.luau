--!strict
-- parts.luau — `kit parts <lane> ...`: the PARTS LIBRARIES (board/plans/archive/2026-11-09-parts-libraries-plan.md, P0; the
-- owner, card ned6: "each pipeline will kind of be different ... push this beyond the limits"). Each lane files its past
-- parts under KINDS of part (a turned band, copies round a circle, a planted foot, a shockwave ring, a health bar ...)
-- with the code that made them, the lessons and the owner's verdicts and words; a new piece is looked up PART BY PART,
-- by kind, across objects (the engine: kit/tools/parts.py; each lane's adapter next to its own tools):
--   kit parts <lane> kinds [--kind K]               the vocabulary and the evidence each kind has
--   kit parts <lane> index                          rebuild the lane's index (build/parts/<lane>/, git-ignored)
--   kit parts <lane> find "<words>" [--kind K] [--type part,recipe,lesson] [--k N]
--   kit parts <lane> plan <piece> [--brief "<words>"] [--dry] [--check]   the answer sheet: at most 8 parts asked
--   kit parts <lane> label [--merge a|b --as WHO] [--disagreements]       the blind labelled set (two labellers)
--   kit parts <lane> eval [--k N] [--rerank]        every method on the labelled set, with its number of cases
--   kit parts <lane> health                         upkeep: empty kinds, unkinded parts, duplicates, stale recipes
--   kit parts <lane> credit <piece>                 what the owner's verdicts on a piece credited (kit verdict runs it)
--   kit parts <lane> look-allow <piece> --from <past piece> "<the owner's words>" --by owner
-- The look is never handed over unless the owner allowed that piece to reuse that past piece's look (look-allow: its own
-- record, separate from kit approve).
local Cli = require("../lib/cli")
local Parts = require("../lib/parts")
local Run = require("../lib/run")

local VALUED = { "k", "kind", "type", "brief", "as", "merge", "pool", "from", "by", "root" }
local SWITCHES = { "dry", "check", "rerank", "plain", "disagreements", "force" }

return function(Cli_: any)
	Cli_.command(
		"work",
		"parts",
		'parts <lane> kinds | index | find "<words>" [--kind K] [--type T] [--k N] | plan <piece> [--brief "<words>"] [--dry] [--check] | label [--merge a|b --as WHO] [--disagreements] | eval [--k N] [--rerank] | health | credit <piece> | look-allow <piece> --from <past piece> "<words>" --by owner',
		"the parts libraries: each lane's past PARTS filed by kind (the code that made them, the lessons, the owner's verdicts and words), looked up part by part for a new piece with an answer sheet of at most 8 parts; mechanics only unless the owner allowed a look reuse; labelled sets and baselines (eval)",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			local lane, sub = Parts.lane(args[1]), args[2]
			if not lane or not sub then
				return Run.report(
					"parts",
					{},
					Run.CODES.USAGE,
					`parts: <{table.concat(Parts.LANES, "|")}> <kinds|index|find|plan|label|eval|health|credit|look-allow>`,
					"lune run kit parts 3d kinds"
				)
			end
			-- the "today" baseline: the lesson ranking a session gets now, for the lane's fixed questions
			if (sub == "label" and not flags.merge and not flags.disagreements) or sub == "eval" then
				local k = tonumber(flags.pool or flags.k) or 5
				Parts.writeToday(lane, math.max(1, math.floor(k)))
			end
			local argv = { "kit/tools/parts.py" }
			for _, a in args do
				table.insert(argv, a)
			end
			for _, f in VALUED do
				if type(flags[f]) == "string" then
					table.insert(argv, "--" .. f)
					table.insert(argv, flags[f])
				end
			end
			for _, f in SWITCHES do
				if flags[f] then
					table.insert(argv, "--" .. f)
				end
			end
			local step = Run.content(`parts {lane} {sub}`, Run.tool("python"), argv)
			local r = step.result or {}
			for _, line in (if type(r.lines) == "table" then r.lines else {}) :: { any } do
				print("  " .. tostring(line))
			end
			local code = if step.ok
				then Run.CODES.PASS
				elseif step.result then Run.CODES.CONTENT
				else Run.CODES.TOOLCHAIN
			return Run.report(
				"parts",
				{ step },
				code,
				tostring(r.summary or `parts {lane} {sub}: the engine gave no verdict`),
				tostring(r.next_action or "read the error above")
			)
		end
	)
end

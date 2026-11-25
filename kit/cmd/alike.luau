--!strict
-- alike.luau — `kit alike`: search by LOOK (2026-11-08, sprint 4: proposal 8 of
-- board/plans/archive/2026-11-08-pipeline-rag-learning-research.md; kit/vision/alike.py). Every picture of our past pieces and
-- every reference, embedded once with the pinned SigLIP 2 in a local index (build/look/, git-ignored):
--   kit alike index [--lane L]                       embed what is new (by content); a second run embeds nothing
--   kit alike <picture | piece> [--lane L] [--k N]   the past pieces that LOOK closest, each with the owner's verdict
--   kit alike dupes [--lane L] [--min 0.985]         the same reference filed more than once
-- ("kit look" is the 3D lane's close-up command: kit/cmd/look.luau.)
local Alike = require("../lib/alike")
local Cli = require("../lib/cli")
local Run = require("../lib/run")

local Command = {}

function Command.register(Cli_: typeof(Cli))
	Cli_.command(
		"work",
		"alike",
		"alike index [--lane L] | alike <picture | piece> [--lane L] [--k N] [--refs] | alike dupes [--lane L] [--min 0.985]",
		"search by look: the past pieces that LOOK closest to a picture or a piece, each with the owner's verdict on it (SigLIP 2, local index build/look/), and the same reference filed twice",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			local sub = args[1]
			if not sub then
				return Run.report(
					"alike",
					{},
					Run.CODES.USAGE,
					"alike: index | <picture | piece> | dupes",
					"lune run kit alike index, then: lune run kit alike <picture | piece>"
				)
			end
			local step = Run.content(`alike {sub}`, Run.tool("python"), Alike.argv(args, flags))
			local r = step.result or {}
			for _, line in (if type(r.lines) == "table" then r.lines else {}) :: { any } do
				print("  " .. tostring(line))
			end
			local code = if step.ok
				then Run.CODES.PASS
				elseif step.result then Run.CODES.CONTENT
				else Run.CODES.TOOLCHAIN
			return Run.report(
				"alike",
				{ step },
				code,
				tostring(r.summary or `alike {sub}: the vision tool gave no verdict`),
				tostring(r.next_action or "lune run kit vision doctor")
			)
		end
	)
	-- the taste model per lane (kit/vision/taste.py; 2026-11-08, sprint 5): the owner's own scores, leave-one-out
	Cli_.command(
		"work",
		"taste",
		"taste train <lane> | taste order <lane> <Move/rK | picture | piece ...> | taste off|on <lane>",
		"a taste model per lane from the owner's OWN scores (never a guess): tested leave-one-out, on only with 20+ scored pieces ordering pairs the owner's way 60%+; it only orders candidates, the owner can switch it off",
		function(rawArgs)
			local args = Cli.parse(rawArgs)
			local sub, lane = args[1], args[2]
			if not sub or not lane then
				return Run.report(
					"taste",
					{},
					Run.CODES.USAGE,
					"taste: train <lane> | order <lane> <Move/rK ...> | off|on <lane>",
					"lune run kit taste train anim"
				)
			end
			local step = Run.content(
				`taste {sub} {lane}`,
				Run.tool("python"),
				{ "kit/vision/run.py", "taste", table.unpack(args) }
			)
			local r = step.result or {}
			for _, line in (if type(r.lines) == "table" then r.lines else {}) :: { any } do
				print("  " .. tostring(line))
			end
			local code = if step.ok
				then Run.CODES.PASS
				elseif step.result then Run.CODES.CONTENT
				else Run.CODES.TOOLCHAIN
			return Run.report(
				"taste",
				{ step },
				code,
				tostring(r.summary or `taste {sub}: the vision tool gave no verdict`),
				tostring(r.next_action or "lune run kit vision doctor")
			)
		end
	)
end

return Command

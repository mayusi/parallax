-- pack.luau — `kit pack <asset> ...`: the asset's PACK (kit/tools/pack.py), the one file every 3D module's result lands
-- in and the build reads from (`pk = a.pack()` in a build script): what the asset HAS, found by scanning (traces + mm
-- profiles, reference models, generated drafts, colour pictures, fitted proportions), and what was CHOSEN (the object
-- and its real length, sizes with their sources, each part's measured colour, the time each stage took).
local Run = require("../lib/run")

return function(Cli: any)
	Cli.command(
		"3d",
		"pack",
		'pack <asset> | pack <asset> object "<name>" [--length dims:<id> | <mm>] [--category <kind>] | pack <asset> size <part.dim> <mm | dims:<id>> [--source <url>] | pack <asset> colours --trace <trace> [--albedo <file.npz>] | pack <asset> time <stage> <seconds>',
		"the asset's PACK: every module's result in one place for the build to read (pk = a.pack(): pk.size, pk.profile, pk.colour, pk.levels, pk.draft) — refresh + show, set the object and its real length, a sourced size, each traced part's measured colour, a stage's time",
		function(rawArgs)
			local step = Run.content("pack", Run.tool("python"), { "kit/tools/pack.py", table.unpack(rawArgs) })
			local r = step.result or {}
			return Run.report(
				"pack",
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.USAGE,
				r.summary or "pack: crashed",
				r.next_action or "read the error above"
			)
		end
	)
end

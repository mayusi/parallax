-- rate.luau — `kit rate`: the OWNER grading page (kit/grading/round.py + kit/grading/page). The owner's verdict is the
-- only quality signal: a round of built assets in a local 3D viewer (orbit, views, clay / wire, compare, R6 scale, each
-- asset's own reference photos), a 0-10 score and words per model, saved as the owner clicks; `import` records every
-- score through `kit verdict asset` (one record: >= 7 golden, <= 3 graveyard). 127.0.0.1 only — a private design is
-- shown on this machine, never uploaded.
--   kit rate make <round> <asset> [<asset> ...]   blind GLBs + references -> build/grading/<round>/
--   kit rate serve <round>                        the page on http://127.0.0.1:8796 (foreground: its own terminal)
--   kit rate import <round>                       the owner's scores + words -> kit verdict asset
--   kit rate list                                 the rounds and how many are scored
local process = require("@lune/process")

local Run = require("../lib/run")

return function(Cli: any)
	Cli.command(
		"3d",
		"rate",
		"rate make <round> <asset> ... | serve <round> | import <round> | list",
		"the OWNER grading page: a round of built models in a local 3D viewer beside their reference photos, a 0-10 score and words per model in seconds; import records them through kit verdict (the only quality signal)",
		function(rawArgs)
			local sub = rawArgs[1]
			if sub == "serve" then
				local rnd = rawArgs[2]
				if not rnd then
					return Run.report(
						"rate",
						{},
						Run.CODES.USAGE,
						"rate serve: needs a round",
						"lune run kit rate list"
					)
				end
				-- FOREGROUND: the page lives as long as this command — run it in its own terminal (or the background)
				print(`rate: the owner grading page for {rnd} — http://127.0.0.1:8796/ (Ctrl+C to stop)`)
				local ok, res = pcall(process.exec, Run.tool("python"), { "kit/grading/page/server.py", rnd })
				if not ok or not res.ok then
					return Run.report(
						"rate",
						{},
						Run.CODES.TOOLCHAIN,
						`rate serve: the page stopped ({if ok then res.stderr or res.code else res})`,
						`lune run kit rate make {rnd} <asset> ... first`
					)
				end
				return Run.report(
					"rate",
					{},
					Run.CODES.PASS,
					"rate serve: the page stopped",
					`lune run kit rate import {rnd}`
				)
			end
			local step = Run.content("rate", Run.tool("python"), { "kit/grading/round.py", table.unpack(rawArgs) })
			local r = step.result or {}
			return Run.report(
				"rate",
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.USAGE,
				r.summary or "rate: crashed",
				r.next_action or "read the error above"
			)
		end
	)
end

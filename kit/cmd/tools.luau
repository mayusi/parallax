-- tools.luau — the kit's pinned tools (owner-approved, VETLOG.md): vtracer, Real-ESRGAN (spandrel), Mitsuba 3,
-- build123d. Wheels pinned with their sha256 in kit/tools/pins/<env>.txt.
--   kit tools doctor [--deep]                          each tool ready / missing, with the command that fixes it
--   kit tools setup [kit-python|mitsuba|cad] [--check]  install exactly the pinned wheels (no deps, hashes required)
local Run = require("../lib/run")

return function(Cli: any)
	Cli.command(
		"kit",
		"tools",
		"tools doctor [--deep] | tools setup [kit-python|mitsuba|cad] [--check]",
		"pinned tools (vectorize, upscale, mitsuba, cad): ready or missing + the fix; --deep tests each one",
		function(rawArgs)
			local step = Run.content("tools", Run.tool("python"), { "kit/tools/tools.py", table.unpack(rawArgs) })
			local r = step.result or {}
			for _, t in r.tools or {} do -- (from the verdict itself: a step's printed tail keeps only its last lines)
				print(string.format("  %-10s %-8s %s", t.name, string.upper(t.status), t.detail))
				if t.fix ~= "" then
					print(string.format("  %-10s %-8s fix: %s", "", "", t.fix))
				end
			end
			return Run.report(
				"tools",
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.TOOLCHAIN,
				r.summary or "tools: crashed",
				r.next_action or "read the error above"
			)
		end
	)
	Cli.command(
		"kit",
		"cad",
		"cad check <asset> [--only Part,Part] [--jobs n] [--no-fillet] [--look] [--zoom cx,cy,cz,size]",
		"every a.cad part of an asset, no Blender: closed solid, volume, open edges, reduced fillets, or the CAD error with its line, each part's fillet_mm run as the build runs it (minutes; --no-fillet: the shape only, seconds) — fix CAD here, build when all are ok",
		function(rawArgs)
			local sub = rawArgs[1]
			if sub ~= "check" then
				return Run.report(
					"cad",
					{},
					Run.CODES.USAGE,
					"cad: needs check",
					"lune run kit cad check <asset> [--only Part,Part]"
				)
			end
			local step =
				Run.content("cad check", Run.tool("python"), { "kit/tools/cad_check.py", table.unpack(rawArgs, 2) })
			local r = step.result or {}
			return Run.report(
				"cad",
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
				r.summary or "cad check: crashed",
				r.next_action or "read the error above"
			)
		end
	)
end

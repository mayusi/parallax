-- family.luau — `kit family <name>`: A FAMILY OF MODULES THAT SNAP, checked as one (kit/tools/family.py,
-- kit/blender/rbx_family.py). Every built asset that called a.module(grid, family="<name>") carries the cut its
-- mesh leaves on each gridded side; this gives each side-cell shape a connector, says which meet face to face with
-- no seam, FAILS on a seam (two sides that almost meet: a wall a little thicker, a lip a little off) and writes the
-- family table <build>/families/<name>.json the world builder and the game snap by.
local Run = require("../lib/run")

return function(Cli: any)
	Cli.command(
		"3d",
		"family",
		"family <name> [--build <dir>]",
		"a family of modules that snap (a.module(grid, family=)): which sides meet with no seam, which almost meet (a seam: fails), and the family table the game snaps by",
		function(rawArgs)
			local step = Run.content("family", Run.tool("python"), { "kit/tools/family.py", table.unpack(rawArgs) })
			local r = step.result or {}
			return Run.report(
				"family",
				{ step },
				if step.ok and r.status == "pass"
					then Run.CODES.PASS
					elseif r.status == "usage" then Run.CODES.USAGE
					else Run.CODES.CONTENT,
				r.summary or "family: crashed",
				r.next_action or "read the error above"
			)
		end
	)
end

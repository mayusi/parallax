-- design.luau — `kit design`: CREATIVE DIRECTION for 3D pieces (kit/tools/design.py; the owner, 2026-10-25: "work
-- on originality ... a creative director and creative direction in the pipeline"). An original piece is decided
-- before it is built: its direction doc (3 directions, a concept sheet each, the owner's pick), the MAKER's design
-- language it carries, a silhouette exploration, a concept sheet the 3D route builds from, a director's review.
--   kit design direction <Piece> [--new]   assets/models/direction/<Piece>.md (kit/direction.py, lane 3d)
--   kit design maker <Maker> [--new]       assets/models/makers/<Maker>.md: shapes, motif, edges, materials, bans
--   kit design explore <Piece> [--n 12]    silhouettes per direction (local FLUX.2), measured, the pick board
--   kit design review <Piece> --asset <a>  the director's fix list for a build against its direction
local Run = require("../lib/run")

return function(Cli: any)
	Cli.command(
		"3d",
		"design",
		"design direction <Piece> [--new] | design maker <Maker> [--new] | design explore <Piece> [--n 12] | design review <Piece> --asset <name>",
		"creative direction for original 3D pieces: the direction doc (3 directions + a concept sheet each, the owner's pick), the maker's design language, a silhouette exploration (quality-diversity grid, readable at 32 px, original vs our past pieces) and the director's review of the build",
		function(rawArgs)
			local step = Run.content("design", Run.tool("python"), { "kit/tools/design.py", table.unpack(rawArgs) })
			local r = step.result or {}
			return Run.report(
				"design",
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.USAGE,
				r.summary or "design: crashed",
				r.next_action or "read the error above"
			)
		end
	)
end

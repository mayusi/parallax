-- look.luau — `kit look`: judge a built asset's DETAIL where it shows (kit/tools/look.py + kit/blender/look_closeup.py).
--   kit look closeup <asset> --part <name[,name]> [--view three-quarter|front|back|side|left|top|below]
--   kit look closeup <asset> --box cx,cy,cz,size
-- The owner judges close-ups ("the lines on the blades"): a part framed at hero distance from the build's manifest
-- (every part's box, written before the join), lit by the studio HDRI + key / fill / rim, rendered in Cycles.
--   kit look details <asset> --part <word> [--details <file>] [--picture <path>]: the shot list's details side by side,
--     the reference's crop beside the build's (an orthographic render registered on the picture's silhouette)
--   kit look zebra <asset> --part <word> [--view side|left|front|top]: glossy grey under striped light (dents show)
--   kit look edges <asset> --part <word> --picture <path> --trace <t> --length-mm L [--parts <parts.json>]: every
--     edge's round measured on the build and the reference, part by part (red: the build sharper), next round_mm
--   kit look silhouette <asset> --part <word> --picture <path> --box x0,y0,x1,y1 --view front|back|top|bottom|side|left
--     [--scale-by height|length]: the build's outline from that view on the reference's, widths per row in mm
--   kit look sheet <asset> [--game <Name>]: the presentation sheet (3D crafts plan S0): your view (forest HDRI), the
--     Roblox look (kit/blender/rbx_lookdev.py, day + as read), clay, wireframe, texel checker, every texture set's maps
local Run = require("../lib/run")

return function(Cli: any)
	Cli.command(
		"3d",
		"look",
		"look closeup <asset> --part <name[,name]> [--view three-quarter|front|side|top] | look closeup <asset> --box cx,cy,cz,size | look lookdev <asset> | look details <asset> --part <word> [--details <file>] | look zebra <asset> --part <word> [--view left] | look edges <asset> --part <word> --picture <path> --trace <t> --length-mm L [--parts <parts.json>] | look silhouette <asset> --part <word> --picture <path> --box x0,y0,x1,y1 --view front|back|top|bottom | look sheet <asset> [--game <Name>]",
		"a built asset's detail at hero distance: one part (or a box) framed from the build's manifest and rendered in Cycles - judge the detail where it shows; details: every shot-list detail beside the reference's; zebra: dents and wavy faces under striped light; edges: every edge's round against the reference's, part by part, with the next round_mm; silhouette: the outline from a view against the reference's, widths in mm per row; sheet: the presentation sheet - your own view (forest), the Roblox look (day + as read), clay, wireframe, texel checker and every texture set's maps",
		function(rawArgs)
			local step = Run.content("look", Run.tool("python"), { "kit/tools/look.py", table.unpack(rawArgs) })
			local r = step.result or {}
			return Run.report(
				"look",
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.USAGE,
				r.summary or "look: crashed",
				r.next_action or "read the error above"
			)
		end
	)
end

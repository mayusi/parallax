-- sharpen.luau — `kit sharpen <part.glb> --about "<what it is>"`: a generated part's soft surface made SHARP.
-- A 3D generator's shape is sound and its surface is soft (no feather ridges, no fur, a smeared colour map); a local
-- image model draws exactly that detail, as a picture. The loop that joins them, view after view (kit/gen/
-- sharpen_math.py has the arithmetic, kit/gen/sharpen_part.py the Blender side):
--   render the part as it is now -> redraw that render sharp (kit vision plate --from: the redraw keeps the layout)
--   -> project the redraw back through the same camera into the part's own colour map
-- then the maps a game material needs (colour, roughness, a normal map) and a closed skin, written to <part>.sharp.glb.
-- First run, the Gjallarhorn's wolf (2026-11-12): six views, about 55 s each; the owner on that route's first part:
-- "Wow, I'm actually kind of amazed".
--   kit sharpen <part.glb> --about "an aged bronze wolf's head with layered feathered wings"
--     --detail "<what must be crisp>"   e.g. "every feather with a central ridge and fine barb lines; carved fur"
--     --face <yaw>      the camera yaw that sees it face-on (TRELLIS.2: 0, the default; Pixal3D: 180)
--     --fold            first lay a splayed pair of wings straight back (a generator fans them out in a V)
--     --flare 1.6       with --fold: move the wings out to the width of what they lie on, the head keeping its own
--                       (a head-and-wings is generated as narrow as its head; stretching the whole part to reach
--                       round a housing made the wolf's face 1.59 times too broad)
--     --drop x0,x1,a0,a1,z0,z1  with --fold (or --fit-only): FIRST cut a box of the part away and cap the cut, in
--                       fractions of its own box (across, along from the nose, up): a stray rod, strut or stand
--                       the generator added (the heel wolf's rod along its top, read off the picture's back edge)
--     --tail 2.2        with --fold (or --fit-only): what lies behind the head made that many times as long
--                       (--tail-from 0.36 --tail-to 0.52: where it eases in). A generated head is about as long as
--                       its wings; the nose wolf's was nearly twice its chart's for the same overall length
--     --level 0.68      with --fold (or --fit-only): bring the body behind the head to ONE width, a share of its
--                       length (--level-from 0.33 --level-to 0.50: where it eases in). A head-and-wings generated
--                       as one solid piece is a wedge; on flat flanks its front half sinks in and its tail stands off
--     --metal gold      carry the sharpened light and dark onto gold instead of the redraws' own colour
--     --views a,b,c     which views, in order (default: side_left, front, side_right, front_left, front_right, top)
--     --voxel 0.0042    the new skin's cell, a share of the part's longest side (the wolf: 624,752 triangles; 0.006
--                       gives about half); --keep-skin: the part is already one clean surface
--     --keep-open "a>b@w"  an opening that must stay OPEN through the new skin (a bore, a strap's slot, a sight
--                       line: a voxel remesh shuts what is under about two voxels across) - from point a to b in
--                       fractions of the part's box (x,y,z), w across (a share of its longest side); several: ";"
--     --normal 1.0      the normal map's strength (it is the colour's light and dark, not a measured height)
--     --out <file.glb>  default: <part>.sharp.glb beside the part
--   kit sharpen <part>.sharp.glb --fit-only [--flare ..] [--snout ..] [--nod ..] [--faces 160000] --out <second>.glb
--     an ALREADY sharpened part fitted again, its maps kept, in seconds: a second, smaller copy for another place on
--     the model (the launcher's second wolf on its stock: narrower host, less flare, fewer triangles)
-- It cannot fix a shape: a redraw of a muddy head is a sharp muddy head. Look at the SHAPE from every view first.
local fs = require("@lune/fs")

local Config = require("../lib/config")
local Run = require("../lib/run")

local SCRIPT = "kit/gen/sharpen_part.py"
-- (kit/gen/sharpen_math.py VIEWS, kept in step: the view's name and how the redraw's prompt says it)
local SEEN = {
	side_left = "seen from its left side",
	front = "seen from the front, facing the camera",
	side_right = "seen from its right side",
	front_left = "seen from the front left",
	front_right = "seen from the front right",
	top = "seen from above",
}
local ORDER = { "side_left", "front", "side_right", "front_left", "front_right", "top" }

return function(Cli: any)
	Cli.command(
		"3d",
		"sharpen",
		'sharpen <part.glb> --about "<what it is>" [--detail "<what must be crisp>"] [--face <yaw>] [--fold [--drop x0,x1,a0,a1,z0,z1] [--flare 1.6] [--tail 2.2] [--level 0.68] [--snout 1.15] [--nod 18]] [--metal gold] [--views a,b,c] [--voxel 0.0042] [--keep-skin] [--keep-open "x0,y0,z0>x1,y1,z1@w; ..."] [--normal 1.0] [--out <file.glb>]  |  sharpen <part>.sharp.glb --fit-only [--flare ..] [--snout ..] [--nod ..] [--faces <n>] --out <second>.glb',
		"a generated part's soft surface made SHARP: view after view, render the part as it is, redraw that render sharp with the local image model (the redraw keeps the layout), project it back into the part's own colour map; then colour / roughness / normal maps and a closed skin -> <part>.sharp.glb (a.import_mesh with no mat= keeps them). --fold lays a splayed pair of wings straight back first. It cannot fix a shape: look at the shape from every view first",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			local src = args[1]
			if not src or not fs.isFile(src) or not string.match(string.lower(src), "%.glb$") then
				return Run.report(
					"sharpen",
					{},
					Run.CODES.USAGE,
					"sharpen: needs a generated part (a .glb with its own colour map)",
					'lune run kit sharpen assets/models/<name>.gen.glb --about "<what it is>"'
				)
			end
			local stemOf = string.match(src, "([^/\\]+)%.[gG][lL][bB]$") or "part"
			local function fits(extra: { string }): { string }
				for _, key in
					{
						"flare",
						"tail",
						"tail-from",
						"tail-to",
						"level",
						"level-from",
						"level-to",
						"snout",
						"nod",
						"faces",
						"keep",
						"drop",
					}
				do
					if flags[key] ~= nil then
						table.insert(extra, "--" .. key)
						table.insert(extra, tostring(flags[key]))
					end
				end
				return extra
			end
			if flags["fit-only"] then
				local fitted = if type(flags.out) == "string"
					then flags.out
					else (string.gsub(src, "%.[gG][lL][bB]$", "")) .. ".fit.glb"
				return Run.chain(`sharpen-fit-{stemOf}`, {
					function()
						return require("./content").blenderStep("sharpen fit", SCRIPT, fits({ "fold", src, fitted }))
					end,
				}, function()
					return Run.CODES.CONTENT
				end, `sharpen fit: {fitted}`)
			end
			if type(flags.about) ~= "string" or #flags.about < 4 then
				return Run.report(
					"sharpen",
					{},
					Run.CODES.USAGE,
					"sharpen: say what the part is (--about): the image model redraws what it is told it sees",
					`lune run kit sharpen {src} --about "an aged bronze wolf's head with layered feathered wings"`
				)
			end
			local views = ORDER
			if type(flags.views) == "string" then
				views = {}
				for name in string.gmatch(flags.views, "[^,%s]+") do
					if not SEEN[name] then
						return Run.report(
							"sharpen",
							{},
							Run.CODES.USAGE,
							`sharpen: no view "{name}"`,
							"one of " .. table.concat(ORDER, ", ")
						)
					end
					table.insert(views, name)
				end
			end
			local stem = string.match(src, "([^/\\]+)%.[gG][lL][bB]$") or "part"
			local work = Config.build("gen") .. "/sharpen_" .. stem
			local out = if type(flags.out) == "string"
				then flags.out
				else (string.gsub(src, "%.[gG][lL][bB]$", "")) .. ".sharp.glb"
			local Content = require("./content")
			local detail = if type(flags.detail) == "string" then flags.detail .. ". " else ""
			local plan: { () -> Run.Step } = {}
			local part = src
			if flags.fold then
				local folded = work .. "/folded.glb"
				table.insert(plan, function()
					return Content.blenderStep("sharpen fold", SCRIPT, fits({ "fold", src, folded }))
				end)
				part = folded
			end
			table.insert(plan, function()
				local extra = { "prep", part, work }
				for _, key in { "face", "voxel" } do
					if flags[key] ~= nil then
						table.insert(extra, "--" .. key)
						table.insert(extra, tostring(flags[key]))
					end
				end
				if flags["keep-skin"] then
					table.insert(extra, "--keep-skin")
				end
				-- openings that must stay open through the new skin (a bore, a strap's slot): "a>b@w; c>d@w"
				if type(flags["keep-open"]) == "string" then
					for way in string.gmatch(flags["keep-open"], "[^;]+") do
						table.insert(extra, "--keep-open")
						table.insert(extra, (string.gsub(way, "%s", "")))
					end
				end
				return Content.blenderStep("sharpen prep", SCRIPT, extra)
			end)
			for _, view in views do
				table.insert(plan, function()
					return Content.blenderStep(`sharpen render {view}`, SCRIPT, { "render", work, view })
				end)
				table.insert(plan, function()
					local prompt = `The same sculpted object, exactly the same shape, pose and layout: {flags.about}, {SEEN[view]}, `
						.. `as a sharp, highly detailed studio photograph. {detail}Polished highlights on the raised edges, `
						.. "dark patina in the recesses. Plain dark grey background, soft even light, no text."
					return Run.content(`sharpen redraw {view}`, Run.tool("diffusers"), {
						"kit/gen/vision3.py",
						"plate",
						prompt,
						"--from",
						`{work}/{view}_in.png`,
						"--n",
						"1",
						"--steps",
						"4",
						"-o",
						`{work}/redraw_{view}`,
					})
				end)
				table.insert(plan, function()
					return Content.blenderStep(`sharpen project {view}`, SCRIPT, {
						"project",
						work,
						view,
						`{work}/redraw_{view}/plate_001.png`,
						"--match",
						`{work}/redraw_{views[1]}/plate_001.png`,
					})
				end)
			end
			table.insert(plan, function()
				local extra = { "final", work, out }
				if type(flags.metal) == "string" then
					table.insert(extra, "--metal")
					table.insert(extra, flags.metal)
				end
				if flags.normal ~= nil then
					table.insert(extra, "--normal")
					table.insert(extra, tostring(flags.normal))
				end
				return Content.blenderStep("sharpen final", SCRIPT, extra)
			end)
			return Run.chain(`sharpen-{stem}`, plan, function()
				return Run.CODES.CONTENT
			end, `sharpen: {out} ({#views} view(s))`)
		end
	)
end

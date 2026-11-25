-- refs.luau — references: find FREE licensed pictures of an object, rank them for tracing, pick one with its
-- attribution. Every model should start from real, licensed references — and keep their licences.
--   kit refs find "<object>" [--n 16] [--licenses cc0,pdm,by,by-sa]   Openverse + Wikimedia Commons -> build/refs/<slug>
--   kit refs expand "<idea>" [--also "a, b"] [--fetch N]               an idea -> real names, their family, sizes, models
--   kit refs dims find|add|wikipedia|wikidata|model "<object> [part]"  real dimensions with sources; conflicts flagged
--   kit refs colour <picture> [--neutral x0,y0,x1,y1] [--sample name=box]  is it colour-graded? balanced samples
--   kit refs rank <folder> [--what "<object>"] [--not "<a, b>"]       which way each looks + how cleanly it cuts out (--not: what it must not be - a museum piece, a car - sinks)
--   kit refs pick <folder> <#> --as <asset>_<view>                      -> refs/<asset>_<view>.<ext> + refs/SOURCES.md
--   kit refs patent <D-number>                                          a design patent's drawings, split into figures
--   kit refs measure <model.glb|fbx|obj> --name <name> [--stations 24] [--length-mm L] [--only a,b] [--skip a,b]
--        [--frame N] [--front min] [--views all] [--cut L0..L1,H0..H1]   a 3D reference -> sizes (mm), every part's size, loft sections,
--        and side / front / top outlines with no camera error (assets/models/<name>_<view>.trace.json); a staged
--        model's backdrop is left out, an animated one is measured at its most-assembled frame; --views: its shaded
--        square views (side-left / side-right / top / front / rear) at 6 px/mm -> build/refs/<name>_<view>_view.png;
--        --cut: the sizes without a box (mm from the rear / from the bottom) — a published size over a protrusion
--   kit refs views <asset>                                              the traced views on one mm scale, part sizes
--   kit refs sections <asset> --ref <library id|glb> [--ref-only a,b] [--flip] [--at d1,..] [--along x1,..]
--        the build's cross-sections over the reference model's, measured apart station by station (mm)
--   kit refs coverage <asset>                                           pixels per mm for each hero feature (brief)
--        in each picture that shows it; under 2 px/mm at best: ask the owner for a close-up
local Config = require("../lib/config")
local Run = require("../lib/run")

-- Blender measures the model (sizes, sections, silhouettes); each silhouette then becomes a smooth-curve trace
local function measure(rest: { string }): Run.Step
	local step = Run.content("refs measure", Run.tool("blender"), {
		"-b",
		"--factory-startup",
		"--python-exit-code",
		"2",
		"-P",
		"kit/refs/measure.py",
		"--",
		table.unpack(rest),
	}, { KIT_BUILD = Config.path("build") })
	local name = nil
	for i, a in rest do
		if a == "--name" then
			name = rest[i + 1]
		end
	end
	if not (step.ok and step.result and step.result.masks and name) then
		return step
	end
	local traced = {}
	for _, view in { "side", "front", "top" } do
		local mask = step.result.masks[view]
		if mask then
			local t = Run.content(
				`trace {name}_{view}`,
				Run.tool("python"),
				{ "kit/blender/trace.py", mask, "--name", `{name}_{view}`, "--front", "right", "--ortho" }
			)
			if not t.ok then
				return t
			end
			table.insert(traced, `assets/models/{name}_{view}.trace.json`)
		end
	end
	step.result.summary = `{step.result.summary}; traced {table.concat(traced, ", ")}`
	step.result.next_action = "LOOK at build/refs/"
		.. name
		.. "_side_mask.png first: its front must point RIGHT (else re-run with --front min) and only the object may"
		.. " show (else --skip <words>; every part and what was left out: refs/"
		.. name
		.. '.measure.json); then build from it: a.carve(side=..., top=..., front=...) with rbx_trace.smooth(rbx_trace.load("'
		.. name
		.. '_side")) and the others, or a.loft(...) through the sections in refs/'
		.. name
		.. ".measure.json; check it with Asset(reference=...) on the same traces"
	return step
end

return function(Cli: any)
	Cli.command(
		"3d",
		"refs",
		'refs find "<object>" | refs expand "<idea>" [--also "a, b"] [--fetch N] | refs dims find|add|wikipedia|wikidata|model "<object> [part]" | refs colour <picture> [--neutral box] [--sample name=box] | refs patent <D-number | utility digits> | refs profiles <trace.json> --anchor <part> --length-mm <mm> [--top-mm <h>] | refs crop <trace.json> --f <f0>..<f1> --h <h0>..<h1> [--parts a,b] | refs rank <folder> [--what "<object>"] [--not "museum piece, car"] | refs pick <folder> <#> --as <name> | refs measure <model> --name <name> [--length-mm L] [--only a,b] [--views all] | refs hull <turntable folder> --length-mm L --name <name> [--cols 24 --rows 5 --side-col 6 --front left] | refs rectify <photo trace> --to <calibrated trace> [--level <part>] | refs views <asset> | refs coverage <asset> | refs parts <asset> [--similar "<object>"] | refs outline <model> --name <name> [--length-mm L] | refs detail <picture> --box x0,y0,x1,y1 --name <name> (--hue lo-hi | --dark t | --point x,y) [--trace <t> --length-mm L] | refs inlays <picture> --name <name> --hue lo-hi [--trace <trace.json> --length-mm L] [--box ..] [--exclude ..] [--split-y px] [--centrelines] [--min-len px] | refs inventory <picture> --name <asset> [--what "<object>"] [--trace <t> --length-mm L] [--parts "hammer,trigger"] [--passes details|parts|none] [--masks] | refs redraw <file.json> [--piece 0] [--tol 0.15] [--mirror x,0] | refs frames <video> --name <name> [--fps 2] [--max 60] | refs read <picture> [--box ..] | refs font <picture> "<text>" [--box ..] | refs edges <picture> --name <asset> --trace <t> --length-mm L [--parts <parts.json>]',
		"free licensed references: search pictures (CC0 / public domain / CC BY / BY-SA only), rank, pick with attribution; measure 3D models; carve a maker's 360-degree turntable into a measured visual hull (hull); take a photo's perspective out of its trace against a calibrated outline (rectify); tie an asset's traced views together (one mm scale, cross-checks, stations, part sizes); pixels per mm for each hero feature in each picture (coverage); a trace's parts as millimetre profiles to build FROM (profiles); LOOK at traced parts on their picture with a mm grid (crop); every part family without a reference picture, and the searches that find one — the object's part, then a similar object's (parts)",
		function(rawArgs)
			local sub = rawArgs[1]
			local rest = { table.unpack(rawArgs, 2) }
			local step: Run.Step
			if sub == "find" then
				step = Run.content("refs find", Run.tool("python"), { "kit/refs/find.py", table.unpack(rest) })
			elseif sub == "rank" then
				step = Run.content("refs rank", Run.tool("python"), { "kit/vision/run.py", "rank", table.unpack(rest) })
			elseif sub == "patent" then
				step = Run.content("refs patent", Run.tool("python"), { "kit/refs/patent.py", table.unpack(rest) })
			elseif sub == "crop" then
				-- one mm window of a traced picture with a grid and the named parts' outlines (see a wrong mask)
				step = Run.content("refs crop", Run.tool("python"), { "kit/refs/crop.py", table.unpack(rest) })
			elseif sub == "profiles" then
				-- a trace's segmented parts as mm profiles in the build script's own frame (one part anchors the scale)
				step = Run.content("refs profiles", Run.tool("python"), { "kit/refs/profiles.py", table.unpack(rest) })
			elseif sub == "pick" then
				step = Run.content("refs pick", Run.tool("python"), { "kit/refs/pick.py", table.unpack(rest) })
			elseif sub == "measure" then
				step = measure(rest)
			elseif sub == "hull" then
				-- a maker's 360-degree turntable carved into a MEASURED visual hull: the camera found from the photos,
				-- the size from the published length, the height / widths measured; square ortho views no camera takes
				step = Run.content("refs hull", Run.tool("python"), { "kit/refs/hull.py", table.unpack(rest) })
			elseif sub == "rectify" then
				-- a photo's trace laid onto a CALIBRATED outline of the same view (a turntable hull, a model's square
				-- view): the photo's perspective found as one projective map and taken out of every outline and part
				step = Run.content("refs rectify", Run.tool("python"), { "kit/refs/rectify.py", table.unpack(rest) })
			elseif sub == "sections" then
				-- the build's CROSS-SECTIONS over a reference model's at the same stations, measured apart: a shape
				-- wrong from the front or inside (a solid where it is hollow) that no side view shows
				step = Run.content("refs sections", Run.tool("python"), { "kit/refs/sections.py", table.unpack(rest) })
			elseif sub == "views" then
				step = Run.content("refs views", Run.tool("python"), { "kit/refs/views.py", table.unpack(rest) })
			elseif sub == "detail" then
				-- ONE small part traced at sub-pixel precision: cropped, upscaled 4x (Real-ESRGAN), segmented, traced
				step = Run.content("refs detail", Run.tool("python"), { "kit/refs/detail.py", table.unpack(rest) })
			elseif sub == "inventory" then
				-- EVERY small detail of a picture listed + boxed (a local vision-language model) and graded by the
				-- pixels it gets: the shot list (ok / upscale / close-up) and a crop sheet to LOOK at
				step =
					Run.content("refs inventory", Run.tool("python"), { "kit/refs/inventory.py", table.unpack(rest) })
			elseif sub == "read" or sub == "font" then
				-- engraved / printed TEXT: read by the local vision-language model; its font found by render-and-compare
				step = Run.content(`refs {sub}`, Run.tool("python"), { "kit/refs/font.py", sub, table.unpack(rest) })
			elseif sub == "edges" then
				-- how ROUND every edge of a picture is (the ramp across it, calibrated in Blender): per part, round_mm
				step = Run.content("refs edges", Run.tool("python"), { "kit/refs/edges.py", table.unpack(rest) })
			elseif sub == "frames" then
				-- a VIDEO (turntable, model viewer, inspect) as references: sharp, different frames only
				step = Run.content("refs frames", Run.tool("python"), { "kit/refs/frames.py", table.unpack(rest) })
			elseif sub == "redraw" then
				-- a traced outline REDRAWN as true lines + arcs (equal radii, optional mirror): clean edges that fillet
				step = Run.content("refs redraw", Run.tool("python"), { "kit/refs/redraw.py", table.unpack(rest) })
			elseif sub == "inlays" then
				-- a view's COLOURED TRIM (gold inlays, a script logo, chrome bands) as millimetre polygons to build from
				step = Run.content("refs inlays", Run.tool("python"), { "kit/refs/inlays.py", table.unpack(rest) })
			elseif sub == "outline" then
				-- a reference model's PARTS as exact outlines (mm, openings, thickness) to extrude in a.cad
				step = Run.content("refs outline", Run.tool("python"), { "kit/refs/outline.py", table.unpack(rest) })
			elseif sub == "parts" then
				-- every part family of the review without a reference picture on disk (a hero build fails on it), and the
				-- searches to run: the object's own part, then the closest similar object's
				step = Run.content("refs parts", Run.tool("python"), { "kit/refs/parts.py", table.unpack(rest) })
				for _, row in (step.result and step.result.rows or {}) :: { string } do
					print(row)
				end
			elseif sub == "expand" then
				-- an IDEA -> real names (Wikidata: the idea's words + each hit's family; the builder's own with --also),
				-- their sizes and their licensed 3D models (Sketchfab); --fetch N downloads the best of the top N
				step = Run.content("refs expand", Run.tool("python"), { "kit/refs/expand.py", table.unpack(rest) })
				for _, row in (step.result and step.result.rows or {}) :: { string } do
					print(row)
				end
			elseif sub == "colour" or sub == "color" then
				-- is a reference picture COLOUR-GRADED? measured on a neutral surface (--neutral box, else the least
				-- colourful mid-tones), balanced, samples given raw and balanced (a graded render read black as navy)
				step = Run.content("refs colour", Run.tool("python"), { "kit/refs/colour.py", table.unpack(rest) })
				for _, row in (step.result and step.result.rows or {}) :: { string } do
					print(row)
				end
			elseif sub == "dims" then
				-- REAL dimensions with their sources (Wikipedia / Wikidata / a dissected model / a published one added by
				-- hand), disagreements flagged; a part's answer cites a row: ref: dims:<id>
				step = Run.content("refs dims", Run.tool("python"), { "kit/refs/dims.py", table.unpack(rest) })
				for _, row in (step.result and step.result.rows or {}) :: { string } do
					print(row)
				end
			elseif sub == "coverage" then
				-- pixels per mm for each hero feature in each picture that shows it (the table is the product)
				step = Run.content("refs coverage", Run.tool("python"), { "kit/refs/coverage.py", table.unpack(rest) })
				for _, row in (step.result and step.result.table or {}) :: { string } do
					print(row)
				end
			else
				return Run.report(
					"refs",
					{},
					Run.CODES.USAGE,
					"refs: needs find | expand | dims | colour | patent | profiles | crop | rank | pick | measure | hull | rectify | views | coverage | parts | detail | inlays | inventory | redraw | frames | read | font | edges",
					'lune run kit refs find "treasure chest"'
				)
			end
			local r = step.result or {}
			return Run.report(
				"refs",
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
				r.summary or `refs {sub}: crashed`,
				r.next_action or "read the error above"
			)
		end
	)
end

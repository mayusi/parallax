-- materials.luau — REAL materials: the measured albedo / metalness / roughness of 86 materials (physicallybased.info,
-- CC0, vetted in VETLOG.md) to build with instead of guessing colours:
--   kit materials [query]          the list (or what matches: "chrome", "rubber", "metal"), with the values
--   kit materials --sheet          every one on a sphere as a build gets it, named -> build/materials/sheet.png
--   kit materials --looks --sheet [--life used|new|light|heavy]  every look built, baked and named on a block
--                                  -> build/materials/looks/sheet.png
--   kit materials --looks [query]  LOOKS: real surfaces' whole recipes (values, scan, pattern, variation, source):
--                                  a.material("stock", **rbx.look("walnut_wood"), life="used")
--   kit materials --scans          the SCANNED surfaces this machine has (ambientCG, CC0): id, real tile size, tags
--   kit materials --fetch <ids>    fetch more (a DOWNLOAD: the owner's OK on the exact ids first; VETLOG.md row)
-- In a build script:  a.material("brass", **rbx.real("Brass"), wear=0.3)
local Run = require("../lib/run")

return function(Cli: any)
	Cli.command(
		"3d",
		"materials",
		"materials [query] | materials --sheet | materials --looks [query] | materials --scans | materials --fetch <ids> | materials --tones <photo> [--mask <png>]",
		"measured real materials (albedo, metalness, roughness) to build with: a.material(name, **rbx.real(...))",
		function(rawArgs)
			if rawArgs[1] == "--sheet" then
				-- every material on a sphere as a build gets it (rbx.real), named: choose by LOOKING
				local render = Run.content(
					"materials sheet",
					Run.tool("blender"),
					{ "-b", "--factory-startup", "--python-exit-code", "2", "-P", "kit/blender/material_sheet.py" }
				)
				local named = if render.ok
					then Run.content("materials labels", Run.tool("python"), { "kit/blender/material_labels.py" })
					else render
				local r = named.result or {}
				return Run.report(
					"materials",
					{ render, named },
					if render.ok and named.ok then Run.CODES.PASS else Run.CODES.CONTENT,
					r.summary or "materials --sheet: crashed",
					r.next_action or "read the error above"
				)
			end
			if rawArgs[1] == "--looks" and rawArgs[2] == "--sheet" then
				-- every look on a bevelled block, BUILT AND BAKED (scan, pattern, variation, a used life): choose by LOOKING
				local render = Run.content("looks sheet", Run.tool("blender"), {
					"-b",
					"--factory-startup",
					"--python-exit-code",
					"2",
					"-P",
					"kit/blender/looks_sheet.py",
					"--",
					"--no-preview",
					table.unpack(rawArgs, 3),
				})
				local named = if render.ok
					then Run.content(
						"looks labels",
						Run.tool("python"),
						{ "kit/blender/material_labels.py", "build/materials/looks/sheet.json" }
					)
					else render
				return Run.report(
					"materials",
					{ render, named },
					if render.ok and named.ok then Run.CODES.PASS else Run.CODES.CONTENT,
					if render.ok and named.ok
						then "looks sheet: every look built, baked and named -> build/materials/looks/sheet.png"
						else "materials --looks --sheet: failed",
					if render.ok and named.ok
						then 'LOOK at build/materials/looks/sheet.png; build with a.material("<name>", **rbx.look("<look>"), life=...)'
						else "read the error above"
				)
			end
			if rawArgs[1] == "--scans" or rawArgs[1] == "--fetch" then
				-- the SCANNED surfaces (ambientCG, CC0) a.material(..., scan=) reads; --fetch is a DOWNLOAD: the owner
				-- approves the exact ids first, and the fetch is logged in VETLOG.md
				local sc =
					Run.content("materials scans", Run.tool("python"), { "kit/tools/scans.py", table.unpack(rawArgs) })
				local sr = sc.result or {}
				for _, s in sr.scans or {} do
					print(
						string.format(
							"  %-14s %-10s %s%s",
							s.id,
							if s.tile_cm then `{s.tile_cm[1]}x{s.tile_cm[2]} cm` else "~1 m",
							table.concat(s.tags or {}, " "),
							if s.present then "" else "  (MAPS MISSING)"
						)
					)
				end
				return Run.report(
					"materials",
					{ sc },
					if sc.ok then Run.CODES.PASS else Run.CODES.USAGE,
					sr.summary or "materials --scans: crashed",
					sr.next_action or "read the error above"
				)
			end
			if rawArgs[1] == "--tones" then
				-- a material's colours MEASURED from a real photo (an albedo is best): base, cavity, edge, grime tone
				local tn = Run.content(
					"materials tones",
					Run.tool("python"),
					{ "kit/tools/tones.py", table.unpack(rawArgs, 2) }
				)
				local tr = tn.result or {}
				return Run.report(
					"materials",
					{ tn },
					if tn.ok then Run.CODES.PASS else Run.CODES.USAGE,
					tr.summary or "materials --tones: crashed",
					tr.next_action or "kit materials --tones <photo> [--mask <cutout.png>]"
				)
			end
			if rawArgs[1] == "--looks" then
				local lk = Run.content(
					"materials looks",
					Run.tool("python"),
					{ "kit/blender/rbx_looks.py", table.unpack(rawArgs, 2) }
				)
				local lr = lk.result or {}
				for _, m in lr.looks or {} do
					print(
						string.format(
							"  %-18s (%.3f, %.3f, %.3f) metal %d rough %.2f%s%s  %s",
							m.name,
							m.color[1],
							m.color[2],
							m.color[3],
							m.metal,
							m.rough,
							if m.scan then "  scan " .. m.scan else "",
							if m.pattern then "  pattern " .. m.pattern else "",
							m.about
						)
					)
				end
				return Run.report(
					"materials",
					{ lk },
					if lk.ok then Run.CODES.PASS else Run.CODES.USAGE,
					lr.summary or "materials --looks: crashed",
					lr.next_action or "read the error above"
				)
			end
			local step =
				Run.content("materials", Run.tool("python"), { "kit/blender/rbx_materials.py", table.unpack(rawArgs) })
			local r = step.result or {}
			for _, m in r.materials or {} do -- (from the verdict itself: a step's printed tail keeps only its last lines)
				print(
					string.format(
						"  %-22s color (%.3f, %.3f, %.3f)  metal %d  rough %.2f  [%s]",
						m.name,
						m.color[1],
						m.color[2],
						m.color[3],
						m.metal,
						m.rough,
						m.category or ""
					)
				)
			end
			return Run.report(
				"materials",
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.USAGE,
				r.summary or "materials: crashed",
				r.next_action or "read the error above"
			)
		end
	)
end

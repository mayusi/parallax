-- library.luau — REFERENCE MODELS: detailed 3D models of a real object to measure and trace from (every side, every
-- cross-section, every part — what no photo gives). Licensed CC0 / CC BY / BY-SA only; downloads vetted (glTF only,
-- safe unzip, header checks, size caps — kit/refs/library.py); stored in ~/.cache/roblox-kit/library (never shipped).
--   kit library find "<object>" [--n 12] [--licenses cc0,by,by-sa] [--min-faces 20000]   Sketchfab, no account
--   kit library get <sketchfab uid>                      needs SKETCHFAB_API_TOKEN in the environment (the owner's)
--   kit library get --url <.glb | .zip> --license cc0 --title "<what>"     a direct CC0 file (Smithsonian 3D scans)
--   kit library inspect <uid | model> --name <name> [--length-mm L | --height-mm H] [--front min] [--part <words>]   LOOK INSIDE it:
--        every part alone (own size, volume, through-holes, kind, material, what it touches), the take-apart order of
--        an assembly animation, the parts sheet + an exploded view (kit/refs/inspect_model.py + inspect_sheet.py)
-- and: kit refs measure <model> --name <name> --length-mm <real length>  (the outside: loft sections, outlines)
local Config = require("../lib/config")
local Run = require("../lib/run")

local function inspect(rawArgs: { string }): (Run.Step, { Run.Step })
	local rest = table.move(rawArgs, 2, #rawArgs, 1, {})
	if rest[1] == nil or string.sub(rest[1], 1, 2) == "--" then -- (said here, before Blender starts for nothing)
		local step = Run.step("library inspect", false, "", {
			summary = "library inspect: needs a model - a library uid (kit library get) or a .glb / .gltf path",
			next_action = "lune run kit library inspect <uid|model.glb> --name <name>",
		});
		-- (a call with no model is a USAGE error, not a failed piece: exit 7 like a bare `kit library`, so the
		--  ledger's library.json does not read as broken content - LIMITATIONS_FIXES_V4 Phase 0)
		(step :: any).usage = true
		return step, { step }
	end
	local look = Run.content("library inspect", Run.tool("blender"), {
		"-b",
		"--factory-startup",
		"--python-exit-code",
		"2",
		"-P",
		"kit/refs/inspect_model.py",
		"--",
		table.unpack(rest),
	}, { KIT_BUILD = Config.path("build") })
	if not (look.ok and look.result and look.result.inspect) then
		return look, { look }
	end
	local sheet =
		Run.content("inspect sheets", Run.tool("python"), { "kit/refs/inspect_sheet.py", look.result.inspect })
	if not sheet.ok then
		return sheet, { look, sheet }
	end
	for _, row in (sheet.result.rows or {}) :: { string } do
		print(row)
	end
	look.result.summary = `{look.result.summary}; sheets: {table.concat(sheet.result.sheets or {}, ", ")}`
	look.result.next_action = sheet.result.next_action
	return look, { look, sheet }
end

return function(Cli: any)
	Cli.command(
		"3d",
		"library",
		'library find "<object>" [--n 12] [--min-faces N] | library get <sketchfab uid> | library get --url <glb|zip> --license cc0 --title "<what>" | library inspect <uid|model> --name <name> [--length-mm L] [--front min] [--part <words>]',
		"reference MODELS: find and download detailed, licensed 3D models of a real object (Sketchfab CC library; Smithsonian CC0 scans) to measure and trace from — every side and cross-section a photo cannot give; downloads vetted (glTF only, safe unzip, header + size checks); INSPECT one inside: every part alone (own size, volume, through-holes, kind, material, contacts), an animation's take-apart order, a parts sheet + exploded view",
		function(rawArgs)
			local sub = rawArgs[1]
			if sub ~= "find" and sub ~= "get" and sub ~= "inspect" then
				return Run.report(
					"library",
					{},
					Run.CODES.USAGE,
					"library: needs find | get | inspect",
					'lune run kit library find "colt 1911"'
				)
			end
			local step, steps
			if sub == "inspect" then
				step, steps = inspect(rawArgs)
			else
				step =
					Run.content(`library {sub}`, Run.tool("python"), { "kit/refs/library.py", table.unpack(rawArgs) })
				steps = { step }
				for _, row in (step.result and step.result.rows or {}) :: { string } do
					print(row)
				end
			end
			local r = step.result or {}
			return Run.report(
				"library",
				steps,
				if step.ok then Run.CODES.PASS elseif (step :: any).usage then Run.CODES.USAGE else Run.CODES.CONTENT,
				r.summary or `library {sub}: crashed`,
				r.next_action or "read the error above"
			)
		end
	)
end

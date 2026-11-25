-- sheet.luau — the two cheap things the owner approves before a 3D piece is detailed (the owner, 2026-11-11: "A concept
-- sheet we really need ... block[out] approval"; a studio signs the model sheet and the blockout before any detail):
--   kit sheet <asset>      the MODEL SHEET (kit/tools/sheet.py): the traced views with the hero features boxed, a large
--                          callout per hero feature (its picture box, route, size, pixels per mm), the palette, the
--                          scale, the parts plan -> assets/models/<asset>.sheet.png. Refused while a hero feature
--                          cannot be modelled from its pictures (no picture, no box, no size, under 2 px per mm).
--   kit blockout <asset>   the BLOCKOUT (kit/tools/blockout.py): the shape round's build (seconds, no bake) with its
--                          clay views, then one page -> assets/models/<asset>.blockout.png: each traced view's
--                          reference beside the model in clay from the same camera and its overlap, six clay views,
--                          the scale beside an R6 character. The proportions, before any detail is paid for.
-- The owner's yes: kit approve 3d <asset> "<their words>" --by owner --stage sheet | blockout. kit asset refuses a new
-- complex / hero / aaa piece without the sheet's, and its baked build without the blockout's (kit/lib/lanelocks.luau).
local fs = require("@lune/fs")

local Config = require("../lib/config")
local Locks = require("../lib/locks")
local Run = require("../lib/run")

-- the project folder the active models folder belongs to ("." = the kit's home)
local function projectRoot(): string
	local root = string.gsub(string.gsub(Config.path("models"), "\\", "/"), "/?assets/models/?$", "")
	return if root == "" then "." else root
end

-- the python tool of a stage, with the flags both stages share
local function toolArgs(tool: string, asset: string, flags: any): { string }
	local pyArgs = { tool, asset, "--root", if type(flags.root) == "string" then flags.root else projectRoot() }
	if flags.check then
		table.insert(pyArgs, "--check")
	end
	if type(flags.out) == "string" then
		table.insert(pyArgs, "--out")
		table.insert(pyArgs, flags.out)
	end
	return pyArgs
end

local function finish(label: string, steps: { Run.Step }, last: Run.Step): number
	local r = last.result or {}
	return Run.report(
		label,
		steps,
		if last.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		r.summary or `{label}: crashed`,
		r.next_action or "read the error above"
	)
end

return function(Cli: any)
	Cli.command(
		"3d",
		"sheet",
		"sheet <asset> [--check] [--out <file.png>]",
		'the MODEL SHEET the owner approves before any shape: the traced views with the hero features boxed, a large callout per hero feature (picture box, route, size, px per mm), the palette, the scale and the parts plan -> assets/models/<asset>.sheet.png; refused while a hero feature has no picture box, no size or under 2 px per mm. His yes: kit approve 3d <asset> "<words>" --by owner --stage sheet (asked again when the sheet changes)',
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			if not args[1] then
				return Run.report(
					"sheet",
					{},
					Run.CODES.USAGE,
					"sheet: needs an asset name",
					"lune run kit sheet <asset>"
				)
			end
			-- (the stage approvals' grandfathered list is frozen on its first run: a piece under way is never stopped)
			Locks.stagesExempt("")
			local step = Run.content("sheet", Run.tool("python"), toolArgs("kit/tools/sheet.py", args[1], flags))
			return finish("sheet", { step }, step)
		end
	)
	Cli.command(
		"3d",
		"blockout",
		"blockout <asset> [--again] [--check] [--out <file.png>]",
		'the BLOCKOUT the owner approves before any detail or bake: runs the shape round (seconds, no bake) with its clay views, then draws one page -> assets/models/<asset>.blockout.png: each traced view\'s reference beside the model in clay from the same camera with the overlap, six clay views, the scale beside an R6 character. His yes: kit approve 3d <asset> "<words>" --by owner --stage blockout; kit asset refuses the baked build of a new complex / hero / aaa piece without it. --again: draw it again over one he approved (it then needs his word again)',
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			local name = args[1]
			if not name then
				return Run.report(
					"blockout",
					{},
					Run.CODES.USAGE,
					"blockout: needs an asset name",
					"lune run kit blockout <asset>"
				)
			end
			Locks.stagesExempt("")
			if flags.check then
				local step = Run.content("blockout", Run.tool("python"), toolArgs("kit/tools/blockout.py", name, flags))
				return finish("blockout", { step }, step)
			end
			local dir = Config.path("models")
			local script = `{dir}/build_{name}.py`
			if not fs.isFile(script) then
				return Run.report(
					"blockout",
					{},
					Run.CODES.CONTENT,
					`blockout: {script} does not exist`,
					`write it as a BLOCKOUT first: each part as its simplest solid at the model sheet's proportions, one a.trace_match per traced view (lune run kit plan {name})`
				)
			end
			local LaneLocks = require("../lib/lanelocks")
			-- his yes is for THE blockout he saw: drawing it again makes another one
			local approved = Locks.stage("3d", name, "blockout")
			if approved and not flags.again and type(flags.out) ~= "string" then
				local kept = LaneLocks.stageState(name, "blockout")
				if kept.id == approved.id then
					return Run.report(
						"blockout",
						{},
						Run.CODES.CONTENT,
						`blockout: the owner approved this blockout ({tostring(approved.date)}: "{tostring(
							approved.words
						)}") - drawing it again replaces what they approved`,
						`to show them a new one: lune run kit blockout {name} --again (then their word again); to look at the shape without touching it: lune run kit asset {name} --geo`
					)
				end
			end
			-- the same quality steps as any shape round (brief, study, the model sheet), then the clock and the route
			local locked = LaneLocks.asset(name, nil, nil, nil, "geo")
			if locked then
				return Run.report(
					"blockout",
					{},
					Run.CODES.CONTENT,
					`blockout: {name} skipped a quality step (brief / reference study / model sheet)`,
					locked
				)
			end
			local Content = require("./content")
			local stop = Content.prebuild(name, dir)
			if stop then
				return Run.report("blockout", {}, Run.CODES.CONTENT, stop.summary, stop.next_action)
			end
			-- the shape round: no bake, no export - and the clay views the sheet is made of
			local build = Content.blenderStep(`blockout round {name}`, script, { "--geo", "--blockout" })
			local facts = if type(build.result) == "table" then build.result.facts else nil
			if type(facts) ~= "table" or type(facts.geo_views) ~= "table" then
				return Run.report(
					"blockout",
					{ build },
					Run.CODES.CONTENT,
					`blockout: the shape round of {name} kept no pictures ({if build.result
						then tostring(build.result.summary)
						else "it crashed before its verdict"})`,
					`lune run kit asset {name} --geo   (fix what stops the build, then lune run kit blockout {name})`
				)
			end
			local pyArgs = toolArgs("kit/tools/blockout.py", name, flags)
			table.insert(pyArgs, "--build")
			table.insert(pyArgs, Config.path("build"))
			local step = Run.content("blockout", Run.tool("python"), pyArgs)
			-- (the round's own verdict is shown as it is, and is not the blockout's: a blockout fails detail checks by
			-- design - only its picture is asked of it here; its failing checks are the shape stage's)
			return finish("blockout", { build, step }, step)
		end
	)
end

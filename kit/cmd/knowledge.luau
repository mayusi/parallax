-- knowledge.luau — the kit LEARNS from the reference models it dissects (kit library inspect): what real models of a
-- category do (bevel sizes, texture density, seam habits, baked detail, roughness, wear), kept as ranges with their
-- sources in kit/learned/<category>.json (kit/refs/learn.py), read by builds (rbx.learned) and checks.
--   kit learn <refs/<name>.inspect.json | name> --category firearm [--roles "Trigger1=hammer, ..."]
--   kit learn remove <name> --category firearm
--   kit learned show <category> [--group role:slide]
--   kit learned compare <refs/<asset>.inspect.json | name> --category firearm     a build against real models
local Run = require("../lib/run")

local function inspection(arg: string?): string?
	if arg == nil then
		return nil
	end
	if string.sub(arg, -5) == ".json" then
		return arg
	end
	return `refs/{arg}.inspect.json`
end

local function run(label: string, args: { string })
	local step = Run.content(label, Run.tool("python"), args)
	for _, row in (step.result and step.result.rows or {}) :: { string } do
		print(row)
	end
	local r = step.result or {}
	return Run.report(
		label,
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		r.summary or `{label}: crashed`,
		r.next_action or "read the error above"
	)
end

return function(Cli: any)
	Cli.command(
		"3d",
		"learn",
		'learn <inspection | name> --category <c> [--roles "Part=role, ..."] | learn remove <name> --category <c>',
		"add a dissected reference model (kit library inspect) to the kit's knowledge of a category: every part's bevels, texture density, seams, baked detail, roughness and wear as ranges with their sources — each model counts once; --roles fixes part names that lie",
		function(rawArgs)
			if rawArgs[1] == "remove" then
				return run("learn", { "kit/refs/learn.py", table.unpack(rawArgs) })
			end
			local path = inspection(rawArgs[1])
			if path == nil then
				return Run.report(
					"learn",
					{},
					Run.CODES.USAGE,
					"learn: needs an inspection",
					"lune run kit learn colt1911_asm --category firearm"
				)
			end
			return run("learn", { "kit/refs/learn.py", "add", path, table.unpack(rawArgs, 2) })
		end
	)
	Cli.command(
		"3d",
		"learned",
		"learned show <category> [--group role:slide] | learned compare <inspection | name> --category <c>",
		"what the kit has learned about a category from real models (typical / low / high, how many models), or a build compared with it — its biggest gaps first",
		function(rawArgs)
			local sub = rawArgs[1]
			if sub == "show" then
				return run("learned", { "kit/refs/learn.py", "show", table.unpack(rawArgs, 2) })
			elseif sub == "compare" then
				local path = inspection(rawArgs[2])
				return run("learned", { "kit/refs/learn.py", "compare", path or "", table.unpack(rawArgs, 3) })
			end
			return Run.report(
				"learned",
				{},
				Run.CODES.USAGE,
				"learned: needs show | compare",
				"lune run kit learned show firearm"
			)
		end
	)
end

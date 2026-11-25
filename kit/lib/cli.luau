-- cli.luau — command registry + help + dispatch for `lune run kit <command> [args]`.
local Run = require("./run")

local Cli = {}

export type Handler = ({ string }) -> number
type Command = { name: string, usage: string, about: string, group: string, run: Handler }

local commands: { [string]: Command } = {}
local order: { string } = {}
local GROUPS = { "start", "work", "code", "3d", "vfx", "sfx", "ui", "qa", "kit" }
local GROUP_TITLES = {
	start = "Start here",
	work = "Work board (survives model / harness switches)",
	code = "Code + systems",
	["3d"] = "3D models",
	vfx = "VFX",
	sfx = "Sound",
	ui = "UI",
	qa = "QA",
	kit = "Kit maintenance",
}

function Cli.command(group: string, name: string, usage: string, about: string, run: Handler)
	assert(GROUP_TITLES[group], "unknown group " .. group)
	commands[name] = { name = name, usage = usage, about = about, group = group, run = run }
	table.insert(order, name)
end

-- "--key value" pairs, "--flag" booleans, everything else positional. Repeated keys collect into a list
-- (flags.list["done"] = {...}); flags[key] holds the LAST value.
function Cli.parse(args: { string }): ({ string }, { [string]: any })
	local pos, flags = {}, { list = {} }
	local i = 1
	while i <= #args do
		local a = args[i]
		local key = string.match(a, "^%-%-([%w%-_]+)$")
		if key then
			local nextArg = args[i + 1]
			if nextArg ~= nil and string.sub(nextArg, 1, 2) ~= "--" then
				flags[key] = nextArg
				flags.list[key] = flags.list[key] or {}
				table.insert(flags.list[key], nextArg)
				i += 2
			else
				flags[key] = true
				i += 1
			end
		else
			table.insert(pos, a)
			i += 1
		end
	end
	return pos, flags
end

function Cli.has(name: string): boolean
	return commands[name] ~= nil
end

function Cli.run(name: string, args: { string }): number
	return commands[name].run(args)
end

-- `kit help` = the short way in (start + work + one line per department with its stages); `kit help --all` = every
-- command (the wall); `kit help --stage <dept>:<stage>` = the <= 5 commands of one stage and its gate. A model
-- picks the right tool far more often from a shortlist than from seventy sub-commands.
function Cli.help(args: { string }?): number
	local Routes = require("./routes")
	local _, flags = Cli.parse(args or {})
	if type(flags.stage) == "string" then
		local dept, stage = string.match(flags.stage, "^([%w]+):([%w%-]+)$")
		if not dept then
			print(
				'usage: lune run kit help --stage <dept>:<stage> [--for <piece|"words">]   e.g. 3d:gather, ui:pieces, anim:dossier'
			)
			return Run.CODES.USAGE
		end
		-- --for: the lessons ranked for the piece (or words); a piece's shown lessons are recorded on it
		local query, about, piece = Routes.forFlag(dept, flags["for"])
		local lines, shown = Routes.lines(dept, stage, { query = query, about = about, piece = piece })
		for _, line in lines do
			print(line)
		end
		if piece and #shown > 0 then
			local Vault = require("./vault")
			local kind = Vault.KIND_OF_DEPT[dept]
			if kind then
				local fresh = Vault.serve(kind, piece, shown, if type(flags.as) == "string" then flags.as else nil)
				if #fresh > 0 then
					print(
						`   (recorded: {#fresh} lesson(s) shown for {piece} - the owner's verdict on it credits or blames them; commit {Vault.citationsPath()})`
					)
				end
			end
		end
		return Run.CODES.PASS
	end
	print("usage: lune run kit <command> [args]      (every command prints summary: + next_action:)\n")
	if not flags.all then
		for _, group in { "start", "work" } do
			local lines = {}
			for _, name in order do
				local c = commands[name]
				if c.group == group then
					table.insert(lines, string.format("  %-40s %s", c.usage, c.about))
				end
			end
			print(GROUP_TITLES[group])
			print(table.concat(lines, "\n"))
			print("")
		end
		print(
			"Departments — one stage at a time (lune run kit help --stage <dept>:<stage>; the whole wall: kit help --all)"
		)
		for _, dept in Routes.depts() do
			print(string.format("  %-6s %s", dept, table.concat(Routes.stages(dept), " -> ")))
		end
		print("")
		print(
			"Exit codes: 0 pass · 1 lint · 2 tests · 3 build · 4 playtest · 5 toolchain · 6 content gate · 7 usage"
		)
		return Run.CODES.PASS
	end
	for _, group in GROUPS do
		local lines = {}
		for _, name in order do
			local c = commands[name]
			if c.group == group then
				table.insert(lines, string.format("  %-40s %s", c.usage, c.about))
			end
		end
		if #lines > 0 then
			print(GROUP_TITLES[group])
			print(table.concat(lines, "\n"))
			print("")
		end
	end
	print(
		"Exit codes: 0 pass · 1 lint · 2 tests · 3 build · 4 playtest · 5 toolchain · 6 content gate · 7 usage"
	)
	return Run.CODES.PASS
end

function Cli.dispatch(argv: { string }): number
	local name = argv[1] or "help"
	if name == "help" or name == "--help" or name == "-h" then
		return Cli.help({ table.unpack(argv, 2) })
	end
	local cmd = commands[name]
	if not cmd then
		print(`[kit] unknown command "{name}"\n`)
		Cli.help()
		return Run.CODES.USAGE
	end
	local args = { table.unpack(argv, 2) }
	-- `--help` / `-h` on ANY command shows its usage and never runs it (2026-10-16: `kit upload --help` started a
	-- real full upload of every lane's queue)
	for _, a in args do
		if a == "--help" or a == "-h" then
			print(`  {cmd.usage}`)
			print(`  {cmd.about}`)
			print(`summary: help for {name} (nothing was run)`)
			print(`next_action: run it without --help: lune run kit {cmd.usage}`)
			return Run.CODES.PASS
		end
	end
	-- a hook every command passes through first (kit/init.luau sets it: kit/lib/enforcer.luau - the department's
	-- vault page, then the Parallax gate: a session + PROMPT-X before a mutating pipeline command, a <piece>.plan.json
	-- before a heavy build, the case contract). It may REFUSE: a non-zero exit code returned is the command's answer
	-- and cmd.run never starts (PARALLAX spec §5.1 step 5: it was pcall'ed with its value dropped, so it could not
	-- block). A hook that CRASHES never blocks: the crash is said and the command runs.
	if Cli.before then
		local ok, code = pcall(Cli.before, name, args)
		if not ok then
			print(`[kit] the command gate crashed (the command runs): {code}`)
		elseif type(code) == "number" and code ~= 0 then
			return code
		end
	end
	return cmd.run(args)
end

-- set by kit/init.luau; called with (commandName, args) before every command runs: nil / 0 = run it, any other
-- number = refused with that exit code (it may also take its own flags out of args: --maintenance, --skip-tool)
Cli.before = nil :: ((string, { string }) -> number?)?

return Cli

-- systems.luau — proof tools for gameplay code beyond "the specs are green" (board/plans/archive/2026-10-12-systems-pipeline-v2.md):
--   kit fuzz [<Name|path> ...]    hostile input at every pure shared function: crashes fail, "yes to NaN" warns
--   kit mutate [<Name|path> ...]  plant one small bug at a time in a copy; survivors = bugs the specs miss
--   kit mutate --regressions      replant every bug a run once found (tests/regressions.json); a survivor fails
local Config = require("../lib/config")
local Run = require("../lib/run")
local fs = require("@lune/fs")

local function paths(args: { string }): { string }
	local out = {}
	for i, a in args do
		-- flags and paths pass through, and so does a flag's value (`--max 40`: 40 was taken for a module name,
		-- src/shared/40.luau, so the cap fell back to its default); a bare Name means src/shared/<Name>.luau
		local isPath = string.sub(a, 1, 2) == "--"
			or string.find(a, "[/\\]") ~= nil
			or string.sub(a, -5) == ".luau"
			or (i > 1 and args[i - 1] == "--max")
		local p = `{Config.path("shared")}/{a}.luau`
		if not isPath and not fs.isFile(p) and fs.isFile(`{Config.path("shared")}/{a}Rules.luau`) then
			p = `{Config.path("shared")}/{a}Rules.luau` -- a system's name means its rules
		end
		table.insert(out, if isPath then a else p)
	end
	if #args == 0 and Config.root() ~= "" and fs.isDir(Config.path("shared")) then
		-- a game: its own shared modules (the tools default to the project's src/shared)
		for _, f in fs.readDir(Config.path("shared")) do
			if string.sub(f, -5) == ".luau" then
				table.insert(out, `{Config.path("shared")}/{f}`)
			end
		end
		table.sort(out)
	end
	return out
end

local function tool(name: string, script: string, args: { string }, file: string): number
	local step = Run.spawn(name, Run.tool("lune"), { "run", script, table.unpack(paths(args)) }, true, {
		KIT_GAME_ROOT = Config.root(),
	})
	-- the tool's own lines (crashes / survivors) are the evidence: show them before the verdict
	for line in string.gmatch(step.tail or "", "[^\n]+") do
		if string.find(line, "^%s+[A-Z]") or string.find(line, "^%s+src/") then
			print(line)
		end
	end
	local r = step.result or {}
	local ok = r.status == "pass"
	step.ok = ok
	return Run.report(
		file,
		{ step },
		if ok then Run.CODES.PASS else Run.CODES.UNIT,
		`{name}: {r.summary or "crashed"}`,
		r.next_action or "read the output above"
	)
end

return function(Cli: any)
	Cli.command(
		"code",
		"fuzz",
		"fuzz [<Name|path> ...]",
		"hostile input (NaN, inf, huge strings, wrong types, cyclic tables) at every function of src/shared modules: a crash fails, saying yes to NaN warns",
		function(args)
			return tool("fuzz", "kit/test/fuzz", args, "fuzz")
		end
	)
	Cli.command(
		"code",
		"mutate",
		"mutate [<Name|path> ...] [--max 80] | mutate --regressions [<file.json>]",
		"mutation testing: plant one bug at a time in a copy of src/shared, run the specs — survivors are bugs your specs would never notice; --regressions replants every recorded bug (tests/regressions.json) and fails if one survives",
		function(args)
			return tool("mutate", "kit/test/mutate", args, "mutate")
		end
	)
	-- every bug becomes a spec case AND a mutation case (the QA recipe; 2026-11-08, sprint 4: tests/regressions.json
	-- was read by kit mutate --regressions, kit accept and the game plan, and nothing wrote it). A case is PROVEN
	-- before it is kept: the bug planted back into a copy must make the specs fail - a bug they miss is refused
	Cli.command(
		"code",
		"bug",
		'bug "<what>" --spec <tests/x.spec.luau> --module <src/shared/X.luau> --line "<a unique piece of the line>" --from "<as it is now>" --to "<the bug>" [--found-by "<who or what>"]',
		"record a fixed bug as a regression case (tests/regressions.json) - kept only when the specs fail with it planted back",
		function(rawArgs)
			local serde = require("@lune/serde")
			local CliLib = require("../lib/cli")
			local Vault = require("../lib/vault")
			local args, flags = CliLib.parse(rawArgs)
			local what = args[1]
			local missing = {}
			for _, key in { "spec", "module", "line", "from", "to" } do
				if type(flags[key]) ~= "string" or flags[key] == "" then
					table.insert(missing, "--" .. key)
				end
			end
			if not what or #missing > 0 then
				return Run.report(
					"bug",
					{},
					Run.CODES.USAGE,
					`bug: needs "<what>"{if #missing > 0 then " and " .. table.concat(missing, ", ") else ""}`,
					'lune run kit bug "dash ignores its cooldown" --spec tests/combat.spec.luau --module src/shared/CombatRules.luau --line "now - last < cooldown" --from "<" --to "<="'
				)
			end
			local corpus = Config.path("tests") .. "/regressions.json"
			local data = { cases = {} } :: any
			if fs.isFile(corpus) then
				local ok, j = pcall(serde.decode, "json" :: any, fs.readFile(corpus))
				if not ok or type(j) ~= "table" or type(j.cases) ~= "table" then
					return Run.report(
						"bug",
						{},
						Run.CODES.CONTENT,
						`bug: {corpus} is not a regression corpus ({"{"}"cases": [...]{"}"})`,
						`fix {corpus} by hand, then run kit bug again`
					)
				end
				data = j
			end
			-- the same planted change is filed once; another bug whose words begin the same gets its own id
			local id, filed = require("../lib/regressions").place(
				data.cases,
				{ id = "", module = flags.module, line = flags.line, from = flags.from, to = flags.to },
				string.sub(Vault.slug(what), 1, 48)
			)
			if filed then
				return Run.report(
					"bug",
					{},
					Run.CODES.PASS,
					`bug {id}: this change is already in the corpus ({corpus})`,
					"none - kit mutate --regressions replants it every run"
				)
			end
			local case = {
				id = id,
				what = what,
				found_by = if type(flags["found-by"]) == "string" then flags["found-by"] else "a session",
				date = Vault.today(),
				spec = flags.spec,
				module = flags.module,
				line = flags.line,
				from = flags.from,
				to = flags.to,
			}
			-- the proof: this case alone through the mutation runner (a copy of the project; the real files untouched)
			local probeDir = Config.build("mutate")
			if not fs.isDir(probeDir) then
				fs.writeDir(probeDir)
			end
			local probe = `{probeDir}/bug-{id}.json`
			fs.writeFile(probe, serde.encode("json", { cases = { case } }, true))
			local step = Run.spawn(
				"bug: the specs against the planted bug",
				Run.tool("lune"),
				{ "run", "kit/test/mutate", "--regressions", probe },
				true,
				{ KIT_GAME_ROOT = Config.root() }
			)
			pcall(fs.removeFile, probe)
			for line in string.gmatch(step.tail or "", "[^\n]+") do
				if string.find(line, "^%s+[A-Z]") then
					print(line)
				end
			end
			local r = step.result or {}
			if r.status ~= "pass" then
				step.ok = false
				return Run.report(
					"bug",
					{ step },
					Run.CODES.CONTENT,
					`bug {id}: not recorded - {r.summary or "the specs did not fail with the bug planted back"}`,
					-- a stale case (no such module, line or token) is fixed in the case, not with a spec: the runner says how
					if type(r.stale) == "table" and #r.stale > 0
						then tostring(r.next_action or "fix the case's module / line / from, then run kit bug again")
						else "write the spec case that fails with this bug (the planted change), then run kit bug again"
				)
			end
			table.insert(data.cases, case)
			fs.writeFile(corpus, serde.encode("json", data, true) .. "\n")
			return Run.report(
				"bug",
				{ step },
				Run.CODES.PASS,
				`bug {id}: recorded - the specs fail with it planted back ({#data.cases} case(s) in {corpus})`,
				`commit {corpus} with the spec; kit mutate --regressions replants every case, kit accept counts them`
			)
		end
	)
end

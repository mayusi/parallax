-- make.luau — `kit make <name> "<object>" [--tier prop|complex|hero]`: ONE command that makes a 3D model by running
-- every stage of the pipeline itself (kit/tools/make.py) inside the owner's hard time budget — 10 minutes for a prop,
-- 30 complex, 60 hero: know the object, gather its photos and reference models, generate base shapes from every
-- generator, a tournament against the photos, fit, surface, mechanism, look + judge. The kit runs the modules, not
-- the builder; the report says which ran and why any did not.
local Config = require("../lib/config")
local Run = require("../lib/run")
local fs = require("@lune/fs")
local serde = require("@lune/serde")

return function(Cli: any)
	Cli.command(
		"3d",
		"make",
		'make <name> "<object>" [--tier prop|complex|hero] [--private] [--photos | --concept] [--use <candidate>] [--fresh] [--no-gen]',
		"MAKE a model: every stage of the 3D pipeline run by the kit itself inside a hard time budget (prop 10 min, complex 30, hero 60) — a real object's photos (its dossier, else found) or, for a generic one, a concept sheet of ONE design; reference models gathered and graded, base shapes from every generator, a tournament against the views, fit, surface, look — report in build/make/<name>/",
		function(rawArgs)
			-- the quality lock: a complex / hero model made after the locks starts from the owner-approved brief
			local pos, flags = Cli.parse(rawArgs)
			if pos[1] and not string.match(pos[1], "^%-") then
				-- no --tier: the brief's quality line decides (a hero brief stays hero); no brief yet: make's own default
				local tier = if type(flags.tier) == "string" then flags.tier else nil
				-- ("make": kit make gathers the references itself AFTER this door, so the model sheet and the blockout
				-- cannot be asked for here: kit/tools/make.py stops for each once it has drawn it - kit make-gate below)
				local locked = require("../lib/lanelocks").asset(pos[1], tier, nil, "prop", "make")
				if locked then
					return Run.report(
						"make",
						{},
						Run.CODES.CONTENT,
						`make: {pos[1]} skipped its brief (quality lock)`,
						locked
					)
				end
			end
			local step = Run.content("make", Run.tool("python"), { "kit/tools/make.py", table.unpack(rawArgs) })
			local r = step.result or {}
			return Run.report(
				"make",
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
				r.summary or "make: crashed",
				r.next_action or "read the error above"
			)
		end
	)
	-- KIT MAKE'S TWO STOPS (his limitations review, 2026-11-17: "halt kit make automatically at --stage sheet and
	-- --stage blockout for complex / hero / aaa briefs"): kit/tools/make.py asks this after it drew the model sheet
	-- (before any generator runs) and after it drew the blockout (before the bake) - the same question kit asset asks
	-- of a piece built by hand (LaneLocks.stageProblem: drawn, still true, approved by the owner, unchanged since)
	Cli.command(
		"3d",
		"make-gate",
		"make-gate <name> <sheet|blockout> [--tier complex|hero|aaa]",
		"kit make's stop: has the owner approved this piece's model sheet / blockout as it is now?",
		function(rawArgs)
			local pos, flags = Cli.parse(rawArgs)
			local name, step = pos[1], pos[2]
			if not name or (step ~= "sheet" and step ~= "blockout") then
				return Run.report(
					"make-gate",
					{},
					Run.CODES.USAGE,
					"make-gate: needs <name> and sheet or blockout",
					"lune run kit make-gate <name> sheet"
				)
			end
			local tier = if type(flags.tier) == "string" then flags.tier else "complex"
			local problem = require("../lib/lanelocks").stageProblem(name, tier, step, Config.path("models"))
			if problem then
				return Run.report("make-gate", {}, Run.CODES.CONTENT, `make-gate: STOP - {problem}`, problem)
			end
			return Run.report(
				"make-gate",
				{},
				Run.CODES.PASS,
				`make-gate: the owner approved {name}'s {step} as it is now`,
				`lune run kit make {name} ... (it goes on past the {step})`
			)
		end
	)
	-- A TRIM SHEET BUILT AGAIN under the models laid into it (card fczy: "a stale user of a rebuilt sheet is recorded
	-- (sheet_build) but no command checks it"): every built model's groups laid into a sheet, their UVs on the bands
	-- of the sheet's build they were laid on - held against the sheet's build now
	Cli.command(
		"3d",
		"trim-stale",
		"trim-stale [--dir <build models folder>]",
		"the models laid into a trim sheet that has been built again since (their UVs may sit on its old bands)",
		function(rawArgs)
			local _pos, flags = Cli.parse(rawArgs)
			local dir = if type(flags.dir) == "string" then flags.dir else Config.build("models")
			local stale, users, sheets = {}, 0, {}
			if fs.isDir(dir) then
				local names = fs.readDir(dir)
				table.sort(names)
				for _, f in names do
					if string.sub(f, -14) == ".manifest.json" then
						local ok, man = pcall(function()
							return serde.decode("json", fs.readFile(`{dir}/{f}`))
						end)
						for g, grp in (ok and type(man) == "table" and man.groups or {}) :: any do
							local t = type(grp) == "table" and grp.trim or nil
							if type(t) == "table" and t.sheet then
								users += 1
								local now = sheets[t.sheet]
								if now == nil then
									local okS, sm = pcall(function()
										return serde.decode("json", fs.readFile(`{dir}/{t.sheet}.manifest.json`))
									end)
									now = okS and type(sm) == "table" and sm.build_id or false
									sheets[t.sheet] = now
								end
								if not now then
									table.insert(
										stale,
										`{string.sub(f, 1, -15)} ({g}): its sheet {t.sheet} is not built`
									)
								elseif t.sheet_build ~= now then
									table.insert(
										stale,
										`{string.sub(f, 1, -15)} ({g}): laid on {t.sheet}'s build {t.sheet_build or "?"}, the sheet is {now} now`
									)
								end
							end
						end
					end
				end
			end
			if #stale > 0 then
				return Run.report(
					"trim-stale",
					{},
					Run.CODES.CONTENT,
					`trim-stale: {#stale} of {users} laid group(s) sit on an older build of their sheet - {table.concat(
						stale,
						"; "
					)}`,
					"build each of those models again (lune run kit asset <name>): its faces are laid into the sheet's bands as they are now"
				)
			end
			return Run.report(
				"trim-stale",
				{},
				Run.CODES.PASS,
				`trim-stale: every one of {users} group(s) laid into a trim sheet sits on its sheet's build now`,
				"none"
			)
		end
	)
end

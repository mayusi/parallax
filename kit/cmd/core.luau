-- core.luau — code gates: format, lint, types, tests, build, and `verify` (all of them, in order).
local fs = require("@lune/fs")

local Config = require("../lib/config")
local Run = require("../lib/run")

local C = Run.CODES
local Core = {}

-- Roblox type definitions for luau-lsp. Not shipped (vet + download first): `kit doctor` explains how to add it.
Core.DEFINITIONS = "kit/types/globalTypes.d.luau"

local function rojoProject(): string
	return Config.load().rojo
end

function Core.steps(): any
	local Steps = {}
	function Steps.styluaCheck(): Run.Step
		local step = Run.spawn("format check", Run.tool("stylua"), { "--check", "." })
		if not step.ok and step.exit ~= 127 then
			step.result = { next_action = "run: lune run kit format   (auto-fixes formatting), then re-run" }
		end
		return step
	end
	function Steps.styluaWrite(): Run.Step
		return Run.spawn("format", Run.tool("stylua"), { "." })
	end
	function Steps.selene(): Run.Step
		return Run.spawn("selene", Run.tool("selene"), { "." })
	end
	function Steps.tests(): Run.Step
		return Run.spawn("tests", Run.tool("lune"), { "run", "kit/test/run" })
	end
	function Steps.pytests(): Run.Step
		-- the kit's pure Python (optimiser, grain axis, ...): unit tests, skipped with a note when numpy is absent
		return Run.spawn("python tests", Run.tool("python"), { "kit/test/python/run.py" })
	end
	function Steps.sourcemap(): Run.Step
		if Config.game() then
			require("./game").syncKit(Config.game() :: string)
		end
		-- absolute paths: a game's project (games/<Name>/default.project.json) writes its paths relative to its own
		-- folder, and luau-lsp reads them from the root - every require in the game turned "unsupported path"
		return Run.spawn(
			"rojo sourcemap",
			Run.tool("rojo"),
			{ "sourcemap", rojoProject(), "--absolute", "--output", "sourcemap.json" }
		)
	end
	function Steps.build(): Run.Step
		Config.ensureDir(Config.path("build"))
		if Config.game() then -- a game carries its own copy of the kit runtime: bring it up to date first
			require("./game").syncKit(Config.game() :: string)
		end
		return Run.spawn("rojo build", Run.tool("rojo"), { "build", rojoProject(), "-o", Config.build("place.rbxlx") })
	end
	function Steps.types(): Run.Step
		if not fs.isFile(Core.DEFINITIONS) then
			return Run.step("types", true, "", {
				summary = "SKIPPED — no Roblox definitions (see `lune run kit doctor`)",
			})
		end
		local s = Steps.sourcemap()
		if not s.ok then
			return s
		end
		local args = {
			"analyze",
			"--platform",
			"roblox",
			"--definitions",
			"@roblox=" .. Core.DEFINITIONS,
			"--sourcemap",
			"sourcemap.json",
			"--ignore",
			"**/DevPackages/**",
			"--ignore",
			"**/Packages/**",
		}
		for _, glob in Config.load().qa.typesIgnore or {} do
			table.insert(args, "--ignore")
			table.insert(args, glob)
		end
		table.insert(args, Config.path("source"))
		return Run.spawn("types", Run.tool("luau-lsp"), args)
	end
	return Steps
end

function Core.codeFor(step: Run.Step): number
	local n = step.name
	if n == "format check" or n == "format" or n == "selene" or n == "types" or n == "audit" then
		return C.LINT
	elseif n == "tests" or n == "python tests" then
		return C.UNIT
	elseif n == "rojo build" or n == "rojo sourcemap" then
		return C.BUILD
	end
	return C.CONTENT
end

function Core.register(Cli: any, Steps: any, Content: any, Qa: any)
	Cli.command(
		"code",
		"verify",
		"verify [--continue]",
		"THE gate: format → selene → types → tests → vfx (+ library/vfx) → ui (+ library/ui) → world → moves → contract → anim → models → audit → build, the Python tests running beside them from types on (--continue: run every gate and name every red, not only the first)",
		function(args)
			local keepGoing = false
			for _, a in args or {} do
				if a == "--continue" or a == "--all" then
					keepGoing = true
				end
			end
			-- the Python lane (~35-47 min: its GPU files queue on the one card) STARTS once the quick lint gates pass and
			-- is joined LAST: the Luau specs and every content gate run beside it (it used to be joined after the specs,
			-- and nothing after it started until it ended - the owner, 2026-11-23: "speed it up with more cores")
			local pythonLane = Run.background(Steps.pytests)
			return Run.chain("verify", {
				-- GAMES: no gameplay code at the project root; every game laid out the same way
				function()
					return require("./game").layoutStep()
				end,
				Steps.styluaCheck,
				Steps.selene,
				Steps.types,
				pythonLane.start,
				Steps.tests,
				Content.vfxPresetsStep,
				function()
					return Content.vfxPreviewStep()
				end,
				function()
					return (Content.uiCompile(false))
				end,
				-- a HUD written as game code, at its reference size on screen (the owner's sg_hud5 3/10: "not this small")
				function()
					return Content.uiHudSizeStep()
				end,
				-- 1-3 px near-misses on every compiled screen (kit/ui/align.py; a warning with the count, V4 UI-X 6.4)
				function()
					return Content.uiAlignStep()
				end,
				-- the git hooks and every connected AI client's MCP config + guard hooks are in step with the kit, and
				-- nothing an older kit wrote for every client is left behind (parallax harness --check)
				function()
					local stale = require("../lib/harness").check()
					return Run.step("harness", #stale == 0, table.concat(stale, "\n"), {
						summary = if #stale == 0
							then "every managed harness file is in step"
							else `{#stale} managed harness file(s) out of step`,
						next_action = if #stale == 0
							then nil
							else "lune run parallax harness, then commit what it wrote",
					})
				end,
				-- the quality locks with no gate of their own: new sounds, assets and worlds (kit/lib/lanelocks.luau)
				function()
					return require("../lib/lanelocks").step()
				end,
				-- the UI library rule: everything the UI pipeline makes is saved (library/ui), never lost
				Content.uiVaultCheckStep,
				-- the VFX library rule: everything the VFX pipeline makes is saved (library/vfx), never lost
				Content.vfxVaultCheckStep,
				-- the knowledge vault (kit/knowledge/vault): frontmatter on every note, links that resolve, an index per
				-- department — a note nobody can read teaches nobody
				function()
					local Vault = require("../lib/vault")
					local problems = Vault.check()
					local detail = {}
					for i = 1, math.min(#problems, 20) do
						table.insert(detail, `{problems[i].path}: {problems[i].problem}`)
					end
					return Run.step("vault", #problems == 0, table.concat(detail, "\n"), {
						summary = if #problems == 0
							then `{#Vault.files()} note(s) healthy`
							else `{#problems} problem(s)`,
						next_action = if #problems == 0
							then nil
							else "fix the notes named above (frontmatter: area/kind/date; links must resolve): lune run kit vault check",
					})
				end,
				-- the ONE verdict record is complete: every owner verdict and lesson a lane recorded in its own store
				-- (UI judge files, library/vfx, sound booth files, the anim book, kit/lessons, the owner's inbox) is
				-- in the vault. A dry-run sync counts what a sync WOULD write: content, not file times, so a fresh
				-- checkout with no sync stamps is judged on what it holds
				function()
					local s = Run.spawn(
						"vault in step",
						Run.tool("python"),
						{ "kit/scripts/vault_migrate.py", "--dry-run" },
						true
					)
					local r = s.result or {}
					if not s.ok or type(r) ~= "table" or r.dry_run ~= true then
						return Run.step("vault in step", false, s.tail or "", {
							summary = "the vault sync dry run crashed",
							next_action = "python kit/scripts/vault_migrate.py --dry-run (read the error)",
						})
					end
					-- (`pending`: the migrator's own count of everything it would file - the number its --check, CI and
					-- upgrade read too; an older migrator without it: the counts it always printed)
					local missing = tonumber(r.pending)
						or (
							(tonumber(r.verdicts) or 0)
							+ (tonumber(r.lessons) or 0)
							+ (tonumber(r.rows) or 0)
							+ (tonumber(r.refs) or 0)
							+ (tonumber(r.inbox) or 0)
							+ (tonumber(r.decisions) or 0)
						)
					return Run.step("vault in step", missing == 0, "", {
						summary = if missing == 0
							then "every lane's verdicts and lessons are in the vault"
							else `the vault is BEHIND: {r.verdicts or 0} verdict(s), {r.lessons or 0} lesson(s), {r.rows or 0} row(s), {r.refs or 0} ref page(s), {r.decisions or 0} decision(s), {r.inbox or 0} inbox line(s) not filed`,
						next_action = if missing == 0
							then nil
							else "lune run kit vault sync, then commit kit/knowledge/vault",
					})
				end,
				function()
					return (Content.worldCompile(false))
				end,
				-- generated remotes (src/net) must match their schemas (assets/net): a hand edit is a hole
				function()
					return require("./net").step(false)
				end,
				-- generated movesets (src/moves) must match assets/moves + the anims they read their frames from
				function()
					return require("./moves").step(false)
				end,
				-- a hero weapon's cross-lane contract (assets/contracts): model, moves, VFX cue, sounds, UI and packet
				-- still bind what was signed - a lane that changes one breaks the others silently (V4 §10 item 1)
				function()
					return require("./contract").step(
						Config.root() .. "assets/contracts",
						nil,
						{ emptyOk = true, unbuiltOk = true }
					)
				end,
				function()
					return (Content.animCompile(false))
				end,
				function()
					return (Content.modelsCompile(false))
				end,
				Qa.auditStep,
				-- the accept ratchet: every floor the owner accepted (any kind, any game) still holds
				Qa.floorsStep,
				-- size / shape guards on gameplay code (warnings only)
				Qa.shapeStep,
				-- (no second sourcemap: Steps.types made sourcemap.json and no gate between changes what it maps)
				Steps.build,
				pythonLane,
			}, Core.codeFor, "verify: all gates green", { continue = keepGoing })
		end
	)
	Cli.command(
		"code",
		"test",
		"test [kit|project]",
		"run every *.spec.luau (kit + project) under frktest",
		function(args)
			local runArgs = { "run", "kit/test/run" }
			if args[1] then
				table.insert(runArgs, args[1])
			end
			return Run.chain("test", {
				function()
					local step = Run.spawn("tests", Run.tool("lune"), runArgs)
					print(step.tail)
					return step
				end,
			}, Core.codeFor, "test: all specs pass")
		end
	)
	Cli.command("code", "format", "format", "auto-format all Luau (stylua)", function()
		return Run.chain("format", { Steps.styluaWrite }, Core.codeFor, "format: done")
	end)
	Cli.command("code", "lint", "lint", "format check + selene + types", function()
		return Run.chain("lint", { Steps.styluaCheck, Steps.selene, Steps.types }, Core.codeFor, "lint: clean")
	end)
	Cli.command("code", "build", "build", "rojo sourcemap + build/place.rbxlx", function()
		return Run.chain(
			"build",
			{ Steps.sourcemap, Steps.build },
			Core.codeFor,
			`build: {Config.build("place.rbxlx")}`
		)
	end)
end

return Core

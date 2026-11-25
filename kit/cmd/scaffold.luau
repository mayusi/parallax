-- scaffold.luau — `kit new <kind> <name>`: never start from a blank file. Every scaffold passes its gate as created.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Config = require("../lib/config")
local Learn = require("./learn")
local Library = require("../lib/library")
local Run = require("../lib/run")
local Vault = require("../lib/vault")

local C = Run.CODES

type Scaffold = {
	pattern: string,
	files: (string) -> { { from: string, to: string } },
	extra: ((string) -> { { from: string, to: string } })?,
	next: (string) -> string,
}

local function scaffolds(): { [string]: Scaffold }
	local P = Config.load().paths
	local snake = "^[a-z][a-z0-9_]*$"
	local pascal = "^[A-Z][A-Za-z0-9]*$"
	return {
		system = {
			pattern = pascal,
			files = function(n)
				return {
					{ from = "kit/templates/system/__NAME__Config.luau", to = `{P.shared}/{n}Config.luau` },
					{ from = "kit/templates/system/__NAME__Rules.luau", to = `{P.shared}/{n}Rules.luau` },
					{
						from = "kit/templates/system/__NAME__Service.server.luau",
						to = `{P.server}/{n}Service.server.luau`,
					},
					{
						from = "kit/templates/system/__NAME__Controller.client.luau",
						to = `{P.client}/{n}Controller.client.luau`,
					},
					{ from = "kit/templates/system/__name__.spec.luau", to = `{P.tests}/{string.lower(n)}.spec.luau` },
				}
			end,
			next = function(n)
				return `edit {P.shared}/{n}Rules.luau (+ its spec) and the effect block in {P.server}/{n}Service.server.luau, then: lune run kit verify`
			end,
		},
		-- the game skeleton: one server + one client entry point, services / controllers run by the kit Loader
		-- (deps, init, start), player data (ProfileStore when installed), tunables read live through Configs
		game = {
			pattern = pascal,
			files = function(n)
				return {
					{ from = "kit/templates/game/__NAME__Server.server.luau", to = `{P.server}/{n}Server.server.luau` },
					{ from = "kit/templates/game/DataService.luau", to = `{P.server}/{n}Services/DataService.luau` },
					{
						from = "kit/templates/game/ExampleService.luau",
						to = `{P.server}/{n}Services/ExampleService.luau`,
					},
					{ from = "kit/templates/game/__NAME__Client.client.luau", to = `{P.client}/{n}Client.client.luau` },
					{
						from = "kit/templates/game/ExampleController.luau",
						to = `{P.client}/{n}Controllers/ExampleController.luau`,
					},
					{ from = "kit/templates/game/__NAME__Config.luau", to = `{P.shared}/{n}Config.luau` },
				}
			end,
			next = function(n)
				return `add services to {P.server}/{n}Services (deps / init / start), systems with kit new system <Name>, `
					.. `remotes with assets/net/<System>.net.json + kit net; saves: lune run kit add profilestore; then: lune run kit verify`
			end,
		},
		asset = {
			pattern = snake,
			files = function(n)
				return { { from = "kit/templates/asset.py", to = `{P.models}/build_{n}.py` } }
			end,
			-- written from the template even with --from: every model starts by asking the owner what it is FOR
			extra = function(n)
				return { { from = "kit/templates/asset.brief.md", to = `{P.models}/{n}.brief.md` } }
			end,
			next = function(n)
				return `ASK THE OWNER the questions in {P.models}/{n}.brief.md first (end goal, quality and its bar, `
					.. `style, how players see it, the hero features and how each gets made, moving parts, extras, `
					.. `references, ownership, the parts plan: how each part gets made) and write their answers there; then follow `
					.. `the stages in order — lune run kit plan {n} (each stage done / to do + its exact commands: gather every `
					.. `reference, a generated 3D draft, then shape, surface, mechanism, look and judge)`
			end,
		},
		sound = {
			pattern = snake,
			files = function(n)
				return { { from = "kit/templates/sound.json", to = `{P.sounds}/{n}.json` } }
			end,
			next = function(n)
				return `edit {P.sounds}/{n}.json (recipe shape: top of kit/audio/synth.py), then: lune run kit sfx {n}`
			end,
		},
		vfx = {
			pattern = snake,
			files = function(n, flags)
				if flags and flags.part then -- a reusable sub-effect (assets/effects/parts/<n>.json; presets `use` it)
					return { { from = "kit/templates/vfx_part.json", to = `{P.vfx}/parts/{n}.json` } }
				end
				return { { from = "kit/templates/vfx.json", to = `{P.vfx}/{n}.json` } }
			end,
			next = function(n, flags)
				if flags and flags.part then
					return `edit {P.vfx}/parts/{n}.json (palette, points, beats, layers), check: lune run kit vfx; use it: "use": [\{ "part": "{n}", "at": "hit", "as": "{n}", "point": "ground" \}]`
				end
				return `edit {P.vfx}/{n}.json (rules: src/kit/VfxValidate.luau), run: lune run kit vfx, play it: Vfx.broadcast("{n}", position)`
			end,
		},
		screen = {
			pattern = pascal,
			files = function(n)
				return { { from = "kit/templates/screen.json", to = `{P.ui}/{n}.json` } }
			end,
			next = function(n)
				return `edit {P.ui}/{n}.json (shape: top of kit/lib/ui.luau), then: lune run kit ui`
			end,
		},
		world = {
			pattern = pascal,
			files = function(n)
				return { { from = "kit/templates/world.json", to = `{P.worlds}/{n}.json` } }
			end,
			-- written from the template even with --from: every world starts by asking the owner what it is
			extra = function(n)
				return { { from = "kit/templates/world.brief.md", to = `{P.worlds}/{n}.brief.md` } }
			end,
			next = function(n)
				return `ASK THE OWNER the questions in {P.worlds}/{n}.brief.md first (source, landmarks, routes, scale), then edit {P.worlds}/{n}.json (generators: the parallax-world skill), check: lune run kit world check {n}, look: lune run kit world web {n}`
			end,
		},
		anim = {
			pattern = pascal,
			files = function(n)
				return { { from = "kit/templates/anim.json", to = `{P.anims}/{n}.json` } }
			end,
			next = function(n)
				return `edit {P.anims}/{n}.json (character-space rotations: top of kit/lib/anim.luau), then: lune run kit anim`
			end,
		},
		playtest = {
			pattern = snake,
			files = function(n)
				return { { from = "kit/templates/playtest.luau", to = `{P.playtests}/{n}.luau` } }
			end,
			next = function(n)
				return `write the checks in {P.playtests}/{n}.luau, then: lune run kit playtest bundle {n}`
			end,
		},
	}
end

return function(Cli: any)
	Cli.command(
		"start",
		"new",
		"new <game|system|asset|sound|vfx|screen|world|anim|playtest> <name> [--from <example>] [--part]",

		"scaffold from a template, or from a proven example (`kit examples` lists them)",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			local kind, name = args[1], args[2]
			local all = scaffolds()
			local kinds = {}
			for k in all do
				table.insert(kinds, k)
			end
			table.sort(kinds)
			local sc = kind and all[kind]
			if not sc or not name then
				return Run.report(
					"new",
					{},
					C.USAGE,
					"new: need a kind and a name",
					`lune run kit new <{table.concat(kinds, "|")}> <name>`
				)
			end
			if not string.match(name, sc.pattern) then
				local hint = if sc.pattern == "^[A-Z][A-Za-z0-9]*$"
					then "PascalCase, e.g. Dash"
					else "snake_case, e.g. crate_small"
				return Run.report("new", {}, C.USAGE, `new: bad {kind} name "{name}"`, `use {hint}`)
			end
			-- the verdict lock (the quality locks, 2026-10-21): at most LaneLocks.OPEN_CAP pieces per lane the owner
			-- has not scored; the next one waits until they look
			local lane = require("../lib/vault").DEPT_OF_KIND[kind]
			if lane then
				local LaneLocks = require("../lib/lanelocks")
				local open = LaneLocks.unscored(lane, { Config.root() }) -- (this project's: the cap is per game)
				-- a piece the owner let past the verdict lock (kit approve <lane> <name> ... --waive verdict) is not held
				-- by the cap - the same rule as vfx director new (2026-10-27: sg_holster's recorded waiver was ignored)
				local waived = require("../lib/locks").waiver(lane, name, "verdict") ~= nil
				if #open >= LaneLocks.OPEN_CAP and not waived then
					return Run.report(
						"new",
						{},
						C.CONTENT,
						`new: the {lane} lane has {#open} pieces the owner has not scored ({table.concat(open, ", ")}) - the cap is {LaneLocks.OPEN_CAP} (quality lock)`,
						`show the owner {open[1]} and record their verdict: lune run kit verdict {kind} {open[1]} <0-10> "<their words>"`
					)
				end
				-- enforced learning (board/plans/archive/2026-11-09-enforced-learning-plan.md, rule 1): a new piece waits until
				-- every owner verdict of the lane has taught its lesson
				local owed = Vault.owedLines(lane)
				if #owed > 0 then
					for _, l in owed do
						print(`  {l}`)
					end
					return Run.report(
						"new",
						{},
						C.CONTENT,
						`new: the {lane} lane owes {#owed} thing(s) from the owner's verdicts (a lesson to learn, a look not taken) - pay them before starting {name}`,
						`lune run kit lesson {lane} "<what it taught>" --verdict <name>, or lune run kit verdict learned {kind} <name> none "<why it taught nothing new>"`
					)
				end
				-- the nearest LOVED piece of this lane: what the owner already scored 7+ that is closest to this one
				-- (its mechanics are reusable; its look is not - every piece takes its look from its own source)
				local row, matched = require("../lib/vault").nearestGolden(lane, name)
				if row and type(flags.from) ~= "string" then
					print(
						`-- the nearest loved {lane} piece{if matched > 0
							then ""
							else " (no shared words: the newest loved one, the bar)"}: {row[1]} ({row[2]}/10, {row[3]}): "{row[4]}"{if row[5]
								and row[5] ~= ""
							then " - what decided it: " .. row[5]
							else ""}`
					)
					print(
						`   reuse its mechanics, never its look: lune run kit examples {kind} lists what can be a --from start`
					)
				end
			end
			-- a game is a FOLDER: games/<Name>/, made and made active here, so everything after lands inside it
			local Game = require("./game")
			if kind == "game" and Config.game() ~= name then
				local made = Game.create(name)
				if not made.ok then
					return Run.report("new", { made }, C.CONTENT, `new game: {made.tail}`, "read the reason above")
				end
				-- --no-activate: work in it for THIS command only (a shared checkout: other sessions keep their game)
				if flags["no-activate"] then
					Config.setGame(name)
				else
					Game.activate(name)
				end
				all = scaffolds()
				sc = all[kind]
			elseif (kind == "system" or kind == "playtest") and Game.forced() and not flags.kit then
				return Run.report(
					"new",
					{},
					C.USAGE,
					`new {kind}: gameplay code belongs to a game, and no game is active`,
					`which game? lune run kit game new <Name> (a new one) or kit game use <Name> (lune run kit game list), then re-run; a kit example at the root: add --kit`
				)
			end
			if kind == "asset" then -- (the study, stage and methods lists are frozen BEFORE this piece's script exists)
				require("../lib/locks").freezeAll()
			end
			local files = sc.files(name, flags)
			local example = flags.from
			if example then
				local src = Library.path(kind, example)
				local folder = Library.KINDS[kind] and Library.KINDS[kind].folder
				if not src or (#files ~= 1 and not folder) then
					local names = {}
					for _, e in Library.list(kind) do
						table.insert(names, e.name)
					end
					return Run.report(
						"new",
						{},
						C.USAGE,
						`new: no {kind} example "{example}"`,
						if #names > 0
							then `pick one of: {table.concat(names, ", ")} (lune run kit examples {kind})`
							else `there are no {kind} examples yet — start from the template (drop --from)`
					)
				end
				if folder then
					-- same template file names as kit/templates, taken from the example's folder instead
					for _, f in files do
						f.from = `{src}/{string.match(f.from, "([^/]+)$")}`
					end
				else
					files = { { from = src, to = files[1].to } }
				end
			end
			if sc.extra then
				for _, f in sc.extra(name) do
					table.insert(files, f)
				end
			end
			-- a screen example brings its identity pack + that identity's art along, copied raw and only when the
			-- project lacks them (an existing identity is the project's own decision)
			local raw = {}
			if kind == "screen" and example then
				local P = Config.load().paths
				local okSpec, spec = pcall(serde.decode, "json" :: any, fs.readFile(files[1].from))
				local id = if okSpec and type(spec) == "table" then spec.identity else nil
				if type(id) == "string" then
					local starter = Library.starter()
					local idFrom, idTo = `{starter}/ui/identities/{id}.json`, `{P.ui}/identities/{id}.json`
					if fs.isFile(idFrom) and not fs.isFile(idTo) then
						table.insert(raw, { from = idFrom, to = idTo })
					end
					local artDir = `{starter}/ui/art/{id}`
					if fs.isDir(artDir) then
						for _, f in fs.readDir(artDir) do
							local to = `{P.ui}/art/{id}/{f}`
							local keep = string.sub(f, -4) == ".png"
								or string.sub(f, -5) == ".json"
								or string.sub(f, -3) == ".md"
							if keep and not fs.isFile(to) then
								table.insert(raw, { from = `{artDir}/{f}`, to = to })
							end
						end
					end
					local refsFrom, refsTo = `{starter}/ui/refs/{id}/REFS.md`, `{P.ui}/refs/{id}/REFS.md`
					if fs.isFile(refsFrom) and not fs.isFile(refsTo) then
						table.insert(raw, { from = refsFrom, to = refsTo })
					end
				end
				-- a gauge example: its .gauge.json comes along under the NEW name (kit ui gauge <Name> regenerates the screen)
				local gaugeFrom = `{Library.starter()}/ui/gauges/{example}.gauge.json`
				if fs.isFile(gaugeFrom) and not fs.isFile(`{P.ui}/{name}.gauge.json`) then
					table.insert(raw, { from = gaugeFrom, to = `{P.ui}/{name}.gauge.json` })
				end
				-- an animated example's reel comes along too (its node paths are the example's: rename them if you rename nodes)
				local reelFrom = `{Library.starter()}/ui/reels/{example}.reel.json`
				if fs.isFile(reelFrom) and not fs.isFile(`{P.ui}/{name}.reel.json`) then
					table.insert(raw, { from = reelFrom, to = `{P.ui}/{name}.reel.json` })
				end
				-- the example's PROCESS page (how it was made: stills, pieces by route, rounds, the owner's words) — the
				-- thing to copy; the look stays the example's own
				local procFrom = `{Library.starter()}/ui/process/{example}.md`
				if fs.isFile(procFrom) and not fs.isFile(`{P.ui}/{name}.process.md`) then
					table.insert(raw, { from = procFrom, to = `{P.ui}/{name}.process.md` })
				end
			end
			-- an effect example brings its parts and textures (and their uploaded ids) along, only what the project lacks
			local registryAdd: { [string]: any } = {}
			if kind == "vfx" and example then
				local P = Config.load().paths
				local copies, reg =
					Library.unpackVfx(Library.starter(), example, { vfx = P.vfx, textures = P.textures })
				for _, c in copies do
					table.insert(raw, c)
				end
				registryAdd = reg
			end
			for _, f in files do
				if fs.isFile(f.to) then
					return Run.report(
						"new",
						{},
						C.USAGE,
						`new: {f.to} already exists`,
						"pick another name or edit the existing file"
					)
				end
			end
			local created, luau = {}, {}
			for _, f in files do
				local parent = string.match(f.to, "^(.*)/[^/]+$")
				if parent then
					Config.ensureDir(parent)
				end
				local text = fs.readFile(f.from)
				if example and not (Library.KINDS[kind] and Library.KINDS[kind].folder) then
					text = Library.renamed(text, example, name)
				end
				text = string.gsub(text, "__NAME__", name)
				text = string.gsub(text, "__name__", string.lower(name))
				fs.writeFile(f.to, text)
				table.insert(created, f.to)
				if string.sub(f.to, -5) == ".luau" then
					table.insert(luau, f.to)
				end
				print("[new] " .. f.to)
			end
			for _, f in raw do
				local parent = string.match(f.to, "^(.*)/[^/]+$")
				if parent then
					Config.ensureDir(parent)
				end
				local body = fs.readFile(f.from)
				if kind == "vfx" then -- an imported texture's spec points at the picture that came with it
					body = string.gsub(body, "__DEPS__/textures/", Config.load().paths.textures .. "/_library/")
				end
				fs.writeFile(f.to, body)
				table.insert(created, f.to)
				print(
					"[new] "
						.. f.to
						.. (if kind == "vfx" then " (the example's part / texture)" else " (the example's identity)")
				)
			end
			if next(registryAdd) ~= nil then -- the textures' uploaded ids, for the ones this project lacks
				local regPath = Config.load().paths.vfx .. "/_textures.json"
				local okReg, reg =
					pcall(serde.decode, "json" :: any, if fs.isFile(regPath) then fs.readFile(regPath) else "{}")
				reg = if okReg and type(reg) == "table" then reg else {}
				local added = 0
				for k, v in registryAdd do
					if reg[k] == nil then
						reg[k] = v
						added += 1
					end
				end
				if added > 0 then
					fs.writeFile(regPath, serde.encode("json", reg, true))
					print(`[new] {regPath}: {added} uploaded texture id(s) from the example`)
				end
			end
			-- the name changes require sort order, so format what we generated
			if #luau > 0 then
				Run.spawn("stylua", Run.tool("stylua"), luau, true)
			end
			-- what earlier sessions learned about this kind of work, right when it matters: the department's page
			-- (the golden set, the graveyard, the owner's last verdicts) within the vault budget, then the lessons
			local area = Learn.AREA_OF[kind]
			local dept = Vault.dept(area)
			if dept and Vault.exists() and fs.isDir(Vault.dir(dept)) then
				local cfg = Config.load()
				print(Vault.page(dept, (cfg.vault and tonumber(cfg.vault.budget)) or 1500))
			end
			local lessons = if area then Learn.lessons(area) else {}
			if #lessons > 0 then
				print(`-- lessons for {area} (lune run kit lessons {area}):`)
				for i = math.max(1, #lessons - 9), #lessons do
					print("  " .. lessons[i])
				end
			end
			local examples = if example then {} else Library.list(kind)
			if #examples > 0 then
				local names = {}
				for _, e in examples do
					table.insert(names, e.name)
				end
				print(`-- proven {kind} examples to borrow techniques from: {table.concat(names, ", ")}`)
			end
			return Run.report(
				"new",
				{},
				C.PASS,
				"new: created " .. table.concat(created, ", ") .. (if example then ` (from example {example})` else ""),
				sc.next(name, flags)
			)
		end
	)

	Cli.command(
		"start",
		"examples",
		"examples [asset|sound|vfx|screen|world|anim]",
		"list the proven examples you can start from (kit new <kind> <name> --from <example>)",
		function(args)
			local kinds = {}
			if args[1] then
				if not Library.KINDS[args[1]] then
					return Run.report(
						"examples",
						{},
						C.USAGE,
						`examples: unknown kind "{args[1]}"`,
						"lune run kit examples"
					)
				end
				kinds = { args[1] }
			else
				for k in Library.KINDS do
					table.insert(kinds, k)
				end
				table.sort(kinds)
			end
			local total = 0
			for _, k in kinds do
				local list = Library.list(k)
				-- the owner's score beside each example (the vault's record); unrated ones last, marked
				local scored = {}
				for _, e in list do
					local s = if Vault.exists() then Vault.scoreOf(k, e.name) else nil
					table.insert(scored, { name = e.name, about = e.about, score = s })
				end
				table.sort(scored, function(a, b)
					if (a.score ~= nil) ~= (b.score ~= nil) then
						return a.score ~= nil
					end
					if a.score ~= nil and b.score ~= nil and a.score ~= b.score then
						return a.score > b.score
					end
					return a.name < b.name
				end)
				print(`-- {k} ({#list})`)
				for _, e in scored do
					local tag = if e.score ~= nil
						then `  [owner {e.score}/10]`
						else "  [unrated — the owner has not scored it]"
					print(`  {e.name}{tag}{if e.about ~= "" then "  — " .. e.about else ""}`)
				end
				total += #list
			end
			return Run.report(
				"examples",
				{},
				C.PASS,
				`examples: {total} across {#kinds} kind(s)`,
				"start from one: lune run kit new <kind> <name> --from <example>   (read it first — it shows the technique)"
			)
		end
	)
end

-- config.luau — where things live in THIS project. Defaults below; override any of them in kit.config.json
-- (project-owned, created by `lune run kit init`). Every kit command runs from the project root.
--
-- GAMES: a project holds its games in games/<Name>/ (each a whole game: src, assets, tests, board, docs, its own Rojo
-- project). While a game is ACTIVE every path below resolves INSIDE it, so every pipeline's work lands in that game's
-- folder without any command knowing. The active game: `--game <Name>` on any command > env KIT_GAME > games/.active
-- (`kit game use <Name>`). No active game = the project root (the kit's home: kit examples, pipeline work).
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Config = {}

Config.FILE = "kit.config.json"
-- the Parallax brand (PARALLAX spec §5.1 step 8, R1): parallax.config.json is read first, kit.config.json is the
-- fallback (zero breakage: a project with only kit.config.json works as before)
Config.FILES = { "parallax.config.json", "kit.config.json" }

-- an environment setting: PARALLAX_<name> first, then KIT_<name> (the old name keeps working)
function Config.env(name: string): string?
	for _, k in { "PARALLAX_" .. name, "KIT_" .. name } do
		local v = process.env[k]
		if v ~= nil and v ~= "" then
			return v
		end
	end
	return nil
end

-- write a setting under both names, so a child reading either sees this one (never a stale PARALLAX_ over a new KIT_)
function Config.setEnv(name: string, value: string?)
	process.env["PARALLAX_" .. name] = value
	process.env["KIT_" .. name] = value
end

-- the config file in a folder ("" = the project root): parallax.config.json, else kit.config.json
function Config.fileIn(dir: string): string
	for _, f in Config.FILES do
		if fs.isFile(dir .. f) then
			return dir .. f
		end
	end
	return dir .. Config.FILE
end

-- the game engine a project targets (docs/ENGINES.md: the engine-agnostic core + one emitter set per engine). Only
-- "roblox" has emitters today; the others are the roadmap's next targets, named so a project can say which it means.
Config.ENGINES = { roblox = true }
Config.PLANNED_ENGINES = { godot = true, unreal = true, unity = true }

Config.DEFAULTS = {
	name = "RobloxGame",
	engine = "roblox",
	rojo = "default.project.json",
	paths = {
		models = "assets/models", -- build_<name>.py Blender scripts (one per asset)
		sounds = "assets/sounds", -- <name>.json synth recipes
		textures = "assets/textures", -- <name>.json particle texture specs
		vfx = "assets/effects", -- <name>.json VFX presets + _textures.json (Rojo: ReplicatedStorage.VfxPresets)
		ui = "assets/ui", -- <Name>.json screen specs
		worlds = "assets/worlds", -- <Name>.json level blueprints
		anims = "assets/animations", -- <Name>.json keyframe specs
		animOut = "src/animations", -- generated KeyframeSequences (Rojo: ReplicatedStorage.KitAnimations)
		worldOut = "src/world", -- generated levels (Rojo: Workspace.KitWorld)
		modelOut = "src/models", -- generated 3D spawn data (Rojo: ReplicatedStorage.KitModels; Models.spawn)
		uiOut = "src/ui", -- generated screens (Rojo: StarterGui)
		tests = "tests", -- project specs: tests/**/*.spec.luau
		playtests = "tests/playtest", -- Studio scenario scripts (kit qa playtest)
		build = "build", -- every generated product (git-ignored)
		board = "board", -- the shared work board (tasks, handoffs, decisions, journal)
		source = "src", -- Luau scanned by the QA audit
		shared = "src/shared", -- pure modules (Rojo: ReplicatedStorage.Shared) — `kit new system` writes here
		server = "src/server", -- server Scripts
		client = "src/client", -- client LocalScripts
		ids = "assets/ids.json", -- uploaded asset ids (Rojo: ReplicatedStorage.AssetIds)
		uploads = "assets/uploads.json", -- the upload ledger
		net = "assets/net", -- <System>.net.json remote schemas
		netOut = "src/net", -- generated remotes (Rojo: ReplicatedStorage.Net)
		moves = "assets/moves", -- <Move>.json + sets
		movesOut = "src/moves", -- generated movesets (Rojo: ReplicatedStorage.KitMoves)
		terrain = "assets/worlds/terrain", -- heightmaps (kit world terrain)
		docs = "docs", -- design notes (a game's GAME.md sits beside them)
	},
	qa = {
		-- performance budget checked by the playtest perf probe
		-- (the V3 list's scene budget, XP-08, the parts a playtest can read in the engine: a client's game memory, the
		--  Highlights drawn - the engine draws 31 - and the shadow-casting lights near the camera)
		perf = {
			memoryMb = 1500,
			instances = 60000,
			heartbeatMs = 20,
			clientMemoryMb = 1100,
			highlights = 31,
			shadowLights = 16,
			shadowRadius = 120,
		},
		-- extra places allowed to fire remotes without Guard (e.g. legacy code you have accepted)
		auditIgnore = {},
		typesIgnore = {}, -- globs the type gate skips (e.g. legacy scripts you will not fix yet) — keep it short
	},
	-- gate profiles (`--profile <name>`): what kit verify / kit prove leave out. The kit ships core EMPTY: a project
	-- lists its own private games (exclude_games: folders under games/), the move dossiers its anim gate should skip
	-- (exclude_dossiers) and the words PROMPT-X must never hand to the kit's prompts (exclude_patterns: regexes, any
	-- case; kit/prompt/route.py) in its own parallax.config.json / kit.config.json
	profiles = {
		core = {
			exclude_games = {},
			exclude_dossiers = {},
			exclude_patterns = {},
		},
	},
	-- `kit upload`: who owns uploaded assets ("user:<id>" | "group:<id>") and the experience that may use them
	-- (audio only plays in experiences it is granted to). No key needed: the Roblox Studio MCP sends the files; an
	-- optional headless key is read from env ROBLOX_API_KEY only, never from here.
	upload = { creator = "", universe = nil },
	-- the knowledge vault (kit/knowledge/vault): how much of a department's page `kit status` / `kit new` print
	vault = { budget = 1500, reshow_minutes = 120, start_budget = 3200 },
}

local function merge(base: any, over: any): any
	if type(base) ~= "table" or type(over) ~= "table" then
		return if over ~= nil then over else base
	end
	local out = table.clone(base)
	for k, v in over do
		out[k] = merge(base[k], v)
	end
	return out
end

local cached: any = nil

Config.GAMES = "games"
Config.ACTIVE = "games/.active"
local forced: string? = nil -- from --game on the command line
Config.missingGame = nil :: string? -- an active game whose folder does not exist (status says so)

local function trim(s: string): string
	return (string.gsub(s, "^%s*(.-)%s*$", "%1"))
end

-- the active game's name (nil = the project root). "none" anywhere clears it.
function Config.game(): string?
	local name = forced
	if name == nil then
		local env = Config.env("GAME")
		if env ~= nil and env ~= "" then
			name = env
		elseif fs.isFile(Config.ACTIVE) then
			name = trim(fs.readFile(Config.ACTIVE))
		end
	end
	if name == nil or name == "" or name == "none" then
		return nil
	end
	if not fs.isDir(`{Config.GAMES}/{name}`) then
		Config.missingGame = name
		return nil
	end
	return name
end

-- the folder every path is relative to: "" (project root) or "games/<Name>/"
function Config.root(): string
	local g = Config.game()
	return if g then `{Config.GAMES}/{g}/` else ""
end

function Config.setGame(name: string?)
	forced = name
	cached = nil
	-- child processes (the test runner, fuzz, python tools that call back) work in the same game
	Config.setEnv("GAME", name or "none")
end

-- the gate PROFILE: `--profile core` on any command (or env KIT_PROFILE=core) leaves the games a project lists in
-- profiles.core.exclude_games out of what kit verify / kit prove walk. nil = every project (the default: nothing is
-- hidden unless asked)
function Config.profile(): string?
	local p = Config.env("PROFILE")
	return if p ~= nil and p ~= "" and p ~= "all" then p else nil
end

-- the games the active profile leaves out -> { [name]: true }
function Config.excludedGames(): { [string]: boolean }
	local out = {}
	local p = Config.profile()
	if p == nil then
		return out
	end
	local prof = (Config.load().profiles or {})[p]
	if type(prof) ~= "table" then
		error(`--profile {p}: no such profile in kit.config.json "profiles" (the kit has: core)`)
	end
	for _, g in prof.exclude_games or {} do
		out[tostring(g)] = true
	end
	return out
end

-- the move dossiers the active profile leaves out -> { [dossier]: true } (kit anim's dossier gate skips their moves)
function Config.excludedDossiers(): { [string]: boolean }
	local out = {}
	local p = Config.profile()
	local prof = if p then (Config.load().profiles or {})[p] else nil
	if type(prof) == "table" then
		for _, d in prof.exclude_dossiers or {} do
			out[tostring(d)] = true
		end
	end
	return out
end

-- strip `--game <Name>` and `--profile <name>` from the command line (init.luau calls this before anything reads the
-- config); both reach child processes through the environment
function Config.applyArgs(argv: { string }): { string }
	local out = {}
	local i = 1
	while i <= #argv do
		if argv[i] == "--game" then
			Config.setGame(argv[i + 1] or "none")
			i += 2
		elseif argv[i] == "--profile" then
			Config.setEnv("PROFILE", argv[i + 1] or "all")
			i += 2
		else
			table.insert(out, argv[i])
			i += 1
		end
	end
	return out
end

local function readJson(path: string): any
	if not fs.isFile(path) then
		return {}
	end
	local ok, decoded = pcall(serde.decode, "json" :: any, fs.readFile(path))
	if not ok then
		error(`{path} is not valid JSON: {decoded}`)
	end
	return decoded
end

function Config.load(): any
	if cached then
		return cached
	end
	local cfg = merge(Config.DEFAULTS, readJson(Config.fileIn("")))
	local root = Config.root()
	if root ~= "" then
		-- a game: its own kit.config.json over the project's, and every path inside its folder
		cfg = merge(cfg, readJson(Config.fileIn(root)))
		cfg.game = Config.game()
		cfg.rojo = root .. (cfg.rojo or "default.project.json")
		local paths = {}
		for k, v in cfg.paths do
			paths[k] = if string.sub(v, 1, 1) == "/" or string.find(v, "^%a:") then v else root .. v
		end
		cfg.paths = paths
	end
	cached = cfg
	return cached
end

-- the engine this project targets, or nil + why when the kit has no emitters for it yet (docs/ENGINES.md)
function Config.engine(): (string?, string?)
	local e = string.lower(tostring(Config.load().engine or "roblox"))
	if Config.ENGINES[e] then
		return e, nil
	end
	if Config.PLANNED_ENGINES[e] then
		return nil,
			`engine "{e}" is on the roadmap (docs/ENGINES.md), not built yet: only "roblox" has emitters today - set "engine": "roblox" in kit.config.json`
	end
	return nil, `unknown engine "{e}" in kit.config.json: "roblox" (today), or one of the planned godot, unreal, unity`
end

-- a path written inside a blueprint / recipe ("assets/worlds/terrain/X.hm.json"): the active game's copy when it has
-- one, else the project's
function Config.resolve(rel: string): string
	local root = Config.root()
	if root ~= "" and (fs.isFile(root .. rel) or fs.isDir(root .. rel)) then
		return root .. rel
	end
	return rel
end

function Config.path(key: string): string
	return Config.load().paths[key]
end

function Config.build(sub: string): string
	return Config.load().paths.build .. "/" .. sub
end

function Config.isKitSource(): boolean
	-- the kit's own repo carries kit/VERSION + kit/manifest.json; installed copies do too, so check the marker
	return fs.isFile("kit/.source")
end

function Config.ensureDir(path: string)
	local parts = string.split(path, "/")
	local cur = ""
	for _, part in parts do
		cur = if cur == "" then part else cur .. "/" .. part
		if cur ~= "" and cur ~= "." and not fs.isDir(cur) then
			fs.writeDir(cur)
		end
	end
end

return Config

-- game.luau — GAMES: every game lives in its own folder, games/<Name>/, and every kit command works inside the
-- ACTIVE game (lib/config.luau routes every path). Making a game? `kit game new <Name>` FIRST — then all the work
-- (scripts, assets, worlds, sounds, UI, tests, tasks, notes) lands in that folder, organised the same way every time.
--
--   kit game new <Name>        make games/<Name>/ (brief, layout, Rojo project, kit runtime) and make it active
--   kit game use <Name>|none   switch the active game (games/.active; per command: --game <Name>; env KIT_GAME)
--   kit game [list]            the games, and which one is active
--   kit game check [<Name>]    its layout, the brief's open questions, the kit runtime synced, the place builds
--   kit game sync [<Name>]     copy the kit runtime (src/kit) into the game (git-ignored there; never edit it)
local DateTime = require("@lune/datetime")
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Config = require("../lib/config")
local Run = require("../lib/run")

local C = Run.CODES

local Game = {}

local GAMES = Config.GAMES
local LEGACY = `{GAMES}/legacy-root.json`

-- the folders every game has (generated ones keep a .gitkeep so Rojo can map them in a fresh clone)
local DIRS = {
	"src/server",
	"src/client",
	"src/shared",
	"src/net",
	"src/moves",
	"src/world",
	"src/ui",
	"src/animations",
	"src/models",
	"assets/net",
	"assets/moves/sets",
	"assets/worlds/terrain",
	"assets/sounds",
	"assets/effects",
	"assets/ui",
	"assets/animations",
	"assets/models",
	"tests/playtest",
	"board/tasks",
	"board/handoffs",
	"board/journal",
	"board/decisions",
	"docs",
}
local FILES = { "GAME.md", "README.md", "kit.config.json", "default.project.json", ".gitignore" }

local function dir(name: string): string
	return `{GAMES}/{name}`
end

-- the kit's home and any project that keeps games/: gameplay code must go into a game, never the root
function Game.forced(): boolean
	return Config.root() == "" and (Config.isKitSource() or fs.isDir(GAMES))
end

function Game.list(): { string }
	local out = {}
	if fs.isDir(GAMES) then
		for _, n in fs.readDir(GAMES) do
			if fs.isFile(`{dir(n)}/GAME.md`) then
				table.insert(out, n)
			end
		end
	end
	table.sort(out)
	return out
end

local function today(): string
	return string.sub(DateTime.now():toIsoDate(), 1, 10)
end

local function template(file: string, name: string): string
	local s = fs.readFile(`kit/templates/game/{file}`)
	s = string.gsub(s, "__NAME__", name)
	s = string.gsub(s, "__DATE__", today())
	return s
end

-- the game's Rojo project (paths relative to the game's folder; the kit runtime is its own synced copy)
-- ------------------------------------------------------------ Rojo ports: one per game, never shared
-- Rojo serves on 34872 unless the project file says otherwise; two games (or a game and the root project) served at
-- once on one port collide, and Studio's Rojo plugin connects to whichever answers. Every game keeps its OWN
-- servePort in its default.project.json, the lowest free one from 34873 up, chosen once and never moved.
Game.ROOT_PORT = 34872
Game.FIRST_PORT = 34873

local function readProject(path: string): any?
	if not fs.isFile(path) then
		return nil
	end
	local ok, d = pcall(serde.decode, "json" :: any, fs.readFile(path))
	return if ok and type(d) == "table" then d else nil
end

-- { root = port, games = { [name] = port or nil } } as the project files say
function Game.ports(): { root: number, games: { [string]: number? } }
	local rootProject = readProject("default.project.json")
	local out = { root = (rootProject and tonumber(rootProject.servePort)) or Game.ROOT_PORT, games = {} }
	for _, g in Game.list() do
		local p = readProject(`{dir(g)}/default.project.json`)
		out.games[g] = p and tonumber(p.servePort) or nil
	end
	return out
end

-- the lowest port from FIRST_PORT up that no project file in this checkout uses
function Game.freePort(): number
	local used: { [number]: boolean } = {}
	local ports = Game.ports()
	used[ports.root] = true
	for _, p in ports.games do
		used[p] = true
	end
	local port = Game.FIRST_PORT
	while used[port] do
		port += 1
	end
	return port
end

-- games whose port is missing or shared with the root / another game (layout gate + kit game ports --fix)
function Game.portProblems(): { { game: string, why: string } }
	local ports = Game.ports()
	local seen: { [number]: string } = { [ports.root] = "the root project" }
	local out = {}
	local names = Game.list()
	table.sort(names)
	for _, g in names do
		local p = ports.games[g]
		if not p then
			table.insert(out, { game = g, why = "no servePort (Rojo would use 34872, the root's)" })
		elseif seen[p] then
			table.insert(out, { game = g, why = `servePort {p} is also {seen[p]}'s` })
		else
			seen[p] = g
		end
	end
	return out
end

-- give a game its own port in its project file (other keys untouched); returns the port
function Game.assignPort(name: string): number
	local path = `{dir(name)}/default.project.json`
	local port = Game.freePort()
	local text = if fs.isFile(path) then fs.readFile(path) else nil
	-- one line changed, the rest of the file exactly as written (a re-encode would reorder every key)
	if text and string.find(text, '"servePort"%s*:%s*%d+') then
		text = string.gsub(text, '("servePort"%s*:%s*)%d+', "%1" .. port, 1)
	elseif text and string.find(text, '\n(%s*)"name"%s*:%s*"[^"]*",') then
		text = string.gsub(text, '\n(%s*)("name"%s*:%s*"[^"]*",)', `\n%1%2\n%1"servePort": {port},`, 1)
	else
		local p = readProject(path) or { name = name }
		p.servePort = port
		text = serde.encode("json", p, true) .. "\n"
	end
	fs.writeFile(path, text)
	return port
end

-- games/.active is ONE file for every session in this checkout: switching it moves every session that relies on it.
-- A switch to a DIFFERENT game within SWITCH_GUARD minutes of the last one is refused unless --switch is given (a
-- session working in another game passes --game <Name> per command instead). Returns why, or nil when allowed.
Game.SWITCH_GUARD = 180
function Game.switchBlocked(current: string?, name: string, activeAt: number, now: number, force: boolean): string?
	if not current or current == name or force then
		return nil
	end
	local mins = math.floor((now - activeAt) / 60)
	if mins >= Game.SWITCH_GUARD then
		return nil
	end
	return `{current} was made active {mins} min ago - another session may be working in it; switching would move that session into {name} too`
end

local function project(name: string): any
	return {
		name = name,
		servePort = Game.freePort(),
		tree = {
			["$className"] = "DataModel",
			ReplicatedStorage = {
				["$className"] = "ReplicatedStorage",
				kit = { ["$path"] = "src/kit" },
				Shared = { ["$path"] = "src/shared" },
				Net = { ["$path"] = "src/net" },
				KitMoves = { ["$path"] = "src/moves" },
				KitAnimations = { ["$path"] = "src/animations" },
				KitModels = { ["$path"] = "src/models" },
				VfxPresets = { ["$path"] = "assets/effects" },
				AssetIds = { ["$path"] = "assets/ids.json" },
				SfxEvents = { ["$path"] = "assets/sounds/_events.json" },
			},
			ServerScriptService = {
				["$className"] = "ServerScriptService",
				["$path"] = "src/server",
				KitServer = { ["$path"] = "src/kit/server" },
			},
			StarterPlayer = {
				["$className"] = "StarterPlayer",
				StarterPlayerScripts = {
					["$className"] = "StarterPlayerScripts",
					["$path"] = "src/client",
					KitClient = { ["$path"] = "src/kit/client" },
				},
			},
			StarterGui = { ["$className"] = "StarterGui", ["$path"] = "src/ui" },
			Workspace = { ["$className"] = "Workspace", KitWorld = { ["$path"] = "src/world" } },
			Lighting = { ["$className"] = "Lighting", ["$properties"] = { Technology = "Future" } },
		},
	}
end

-- copy src/kit into the game when anything differs; -> files written
function Game.syncKit(name: string): number
	local written = 0
	local function copy(from: string, to: string)
		if not fs.isDir(to) then
			Config.ensureDir(to)
		end
		for _, n in fs.readDir(from) do
			local a, b = `{from}/{n}`, `{to}/{n}`
			if fs.isDir(a) then
				copy(a, b)
			else
				local src = fs.readFile(a)
				if not fs.isFile(b) or fs.readFile(b) ~= src then
					fs.writeFile(b, src)
					written += 1
				end
			end
		end
		-- files the kit no longer has go too (it is a mirror, never edited)
		for _, n in fs.readDir(to) do
			if not fs.isFile(`{from}/{n}`) and not fs.isDir(`{from}/{n}`) then
				if fs.isDir(`{to}/{n}`) then
					fs.removeDir(`{to}/{n}`)
				else
					fs.removeFile(`{to}/{n}`)
				end
				written += 1
			end
		end
	end
	copy("src/kit", `{dir(name)}/src/kit`)
	written += Game.syncSoundIds(name)
	written += Game.mirrorPieces(name) -- the clips and effects the game's moves name
	return written
end

-- The project's sound sets (assets/sounds/sets: footsteps, combat, ...) render and upload once at the project root;
-- a game's runtime reads ITS OWN assets/ids.json, so without this mirror Foley / Sfx in every game had no ids (silent
-- in Studio). Pure: every project sound id lands in the game's sounds, except names the game uploaded itself (`owned`:
-- the game's own ledger) — those stay the game's. Returns the merged sounds and how many changed.
function Game.mergeSoundIds(
	gameSounds: { [string]: string },
	projectSounds: { [string]: string },
	owned: { [string]: boolean }
): ({ [string]: string }, number)
	local out, changed = table.clone(gameSounds), 0
	for n, id in projectSounds do
		if not owned[n] and out[n] ~= id then
			out[n] = id
			changed += 1
		end
	end
	return out, changed
end

function Game.syncSoundIds(name: string): number
	local mine, root = `{dir(name)}/assets/ids.json`, "assets/ids.json"
	if not fs.isFile(mine) or not fs.isFile(root) then
		return 0
	end
	local okG, ids = pcall(serde.decode, "json" :: any, fs.readFile(mine))
	local okR, proj = pcall(serde.decode, "json" :: any, fs.readFile(root))
	if not okG or not okR or type(ids) ~= "table" or type(proj) ~= "table" or type(proj.sounds) ~= "table" then
		return 0
	end
	local owned: { [string]: boolean } = {}
	-- the game's own sounds are the members of its own sets (games/<Name>/assets/sounds/sets): never overwritten,
	-- uploaded yet or not (a game with no ledger lost its own ids to the project's of the same name)
	local setsDir = `{dir(name)}/assets/sounds/sets`
	if fs.isDir(setsDir) then
		for _, f in fs.readDir(setsDir) do
			if string.match(f, "%.json$") then
				local ok, set = pcall(serde.decode, "json" :: any, fs.readFile(`{setsDir}/{f}`))
				if ok and type(set) == "table" and type(set.members) == "table" then
					for member in set.members do
						for _, base in { member, `{member}_light`, `{member}_medium`, `{member}_heavy` } do
							owned[base] = true
							for take = 2, 8 do -- (the takes: <name>_2 ...)
								owned[`{base}_{take}`] = true
							end
						end
					end
				end
			end
		end
	end
	local ledger = `{dir(name)}/assets/uploads.json`
	if fs.isFile(ledger) then
		local ok, l = pcall(serde.decode, "json" :: any, fs.readFile(ledger))
		if ok and type(l) == "table" then
			for file in l do
				local stem = string.match(file, "([^/]+)%.ogg$")
				if stem then
					owned[stem] = true
				end
			end
		end
	end
	local merged, changed = Game.mergeSoundIds(ids.sounds or {}, proj.sounds, owned)
	if changed > 0 then
		ids.sounds = merged
		fs.writeFile(mine, serde.encode("json", ids, true) .. "\n")
	end
	return changed
end

-- ------------------------------------------------------------ clips + effects a game's moves name (the mirror)
-- The anim lane builds every clip at the project root (assets/animations -> src/animations + Meta) and the vfx lane
-- every effect (assets/effects), one source of truth each. A game's runtime reads only ITS OWN folders, so a game's
-- moves named clips and effects it did not have: silent in Studio. On every sync the kit mirrors exactly what the
-- game's moves name: the clips (with their name variants - the hit-reaction matrix is picked by name), their Meta
-- entries and uploaded ids, the effect presets with the parts, textures, meshes and impact frames they use. A piece
-- the game made itself is never overwritten (games/<Name>/kit.mirror.json lists what the kit copied).

-- the clip and effect names a game's moves (and its move SETS: a set's parry = { anim, stagger } names clips)
-- point at (pure: the move and set tables in, two name sets out)
function Game.piecesOf(moves: { any }, sets: { any }?): ({ [string]: boolean }, { [string]: boolean })
	local clips, effects = {}, {}
	local function add(set: { [string]: boolean }, v: any)
		if type(v) == "string" and v ~= "" then
			set[v] = true
		end
	end
	for _, mv in moves do
		if type(mv) == "table" then
			add(clips, mv.anim)
			local onHit = if type(mv.onHit) == "table" then mv.onHit else {}
			add(clips, onHit.reaction)
			add(effects, onHit.vfx)
			for _, cue in (if type(mv.vfx) == "table" then mv.vfx else {}) :: { any } do
				add(effects, type(cue) == "table" and cue.preset)
			end
		end
	end
	for _, set in sets or {} do
		local parry = if type(set) == "table" and type(set.parry) == "table" then set.parry else {}
		add(clips, parry.anim)
		add(clips, parry.stagger)
	end
	return clips, effects
end

-- every value a preset (or part) names under these keys, walked through the whole table
local function namedIn(data: any, key: string, out: { [string]: boolean })
	if type(data) ~= "table" then
		return
	end
	for k, v in data do
		if k == key and type(v) == "string" and v ~= "" then
			out[v] = true
		elseif type(v) == "table" then
			namedIn(v, key, out)
		end
	end
end

local function readJsonFile(path: string): any?
	if not fs.isFile(path) then
		return nil
	end
	local ok, d = pcall(serde.decode, "json" :: any, fs.readFile(path))
	return if ok then d else nil
end

-- Meta.luau is JSON wrapped in a Luau line (kit anim writes it): read / write that JSON
local META_HEAD =
	'-- generated by `lune run kit anim` (in a game: mirrored by kit game sync): every clip\'s metadata for the runtime (Anim.locomotion, Feel). Never edit.\nreturn game:GetService("HttpService"):JSONDecode([==['
local function readMeta(path: string): { [string]: any }
	if not fs.isFile(path) then
		return {}
	end
	local body = string.match(fs.readFile(path), "%[==%[(.*)%]==%]")
	local ok, d = pcall(serde.decode, "json" :: any, body or "")
	return if ok and type(d) == "table" then d else {}
end

function Game.mirrorPieces(name: string): number
	local root = dir(name)
	local moves = {}
	local movesDir = `{root}/assets/moves`
	if fs.isDir(movesDir) then
		for _, f in fs.readDir(movesDir) do
			if string.sub(f, -5) == ".json" then
				table.insert(moves, readJsonFile(`{movesDir}/{f}`))
			end
		end
	end
	local sets = {}
	local setsDir = `{movesDir}/sets`
	if fs.isDir(setsDir) then
		for _, f in fs.readDir(setsDir) do
			if string.sub(f, -5) == ".json" then
				table.insert(sets, readJsonFile(`{setsDir}/{f}`))
			end
		end
	end
	local clips, effects = Game.piecesOf(moves, sets)
	if next(clips) == nil and next(effects) == nil then
		return 0
	end
	local ledgerPath = `{root}/kit.mirror.json`
	local ledger = readJsonFile(ledgerPath) or {}
	for _, k in { "clips", "effects", "parts", "frames", "textures", "meshes", "animIds" } do
		ledger[k] = if type(ledger[k]) == "table" then ledger[k] else {}
	end
	local written = 0
	-- copy one file unless the game made its own (present, and not something the kit mirrored before)
	local function mirror(from: string, to: string, kind: string, key: string)
		if not fs.isFile(from) then
			return false
		end
		if fs.isFile(to) and not ledger[kind][key] then
			return false -- the game's own piece
		end
		local data = fs.readFile(from)
		if not fs.isFile(to) or fs.readFile(to) ~= data then
			Config.ensureDir((string.match(to, "^(.*)/[^/]+$")) :: string)
			fs.writeFile(to, data)
			written += 1
		end
		ledger[kind][key] = true
		return true
	end
	-- clips: the named clip and its name variants (KatanaHitReaction -> KatanaHitReactionFrontHeavy ...)
	local mirrored: { string } = {}
	if fs.isDir("src/animations") then
		for _, f in fs.readDir("src/animations") do
			local stem = string.match(f, "^(.+)%.model%.json$")
			if stem then
				for clip in clips do
					if string.sub(stem, 1, #clip) == clip then
						if mirror(`src/animations/{f}`, `{root}/src/animations/{f}`, "clips", stem) then
							table.insert(mirrored, stem)
						end
						break
					end
				end
			end
		end
	end
	if #mirrored > 0 then
		local projectMeta = readMeta("src/animations/Meta.luau")
		local gamePath = `{root}/src/animations/Meta.luau`
		local gameMeta = readMeta(gamePath)
		local before = serde.encode("json", gameMeta)
		for _, stem in mirrored do
			if projectMeta[stem] ~= nil then
				gameMeta[stem] = projectMeta[stem] -- (the game's own clips keep their own entries)
			end
		end
		if serde.encode("json", gameMeta) ~= before or not fs.isFile(gamePath) then
			fs.writeFile(gamePath, META_HEAD .. serde.encode("json", gameMeta, true) .. "]==])\n")
			written += 1
		end
		-- uploaded clip ids (the runtime prefers an uploaded clip), never over an id the game set itself
		local projectIds = readJsonFile("assets/ids.json")
		local idsPath = `{root}/assets/ids.json`
		local gameIds = readJsonFile(idsPath)
		if type(projectIds) == "table" and type(projectIds.animations) == "table" and type(gameIds) == "table" then
			gameIds.animations = if type(gameIds.animations) == "table" then gameIds.animations else {}
			local changed = 0
			for _, stem in mirrored do
				local id = projectIds.animations[stem]
				if
					id
					and (gameIds.animations[stem] == nil or ledger.animIds[stem])
					and gameIds.animations[stem] ~= id
				then
					gameIds.animations[stem] = id
					ledger.animIds[stem] = true
					changed += 1
				end
			end
			if changed > 0 then
				fs.writeFile(idsPath, serde.encode("json", gameIds, true) .. "\n")
				written += changed
			end
		end
	end
	-- effects: the preset, the parts it uses (and theirs), its impact frames, then the textures and meshes they name
	local textures, meshes, parts = {}, {}, {}
	local function walk(data: any)
		namedIn(data, "texture", textures)
		namedIn(data, "mesh", meshes)
		local p = {}
		namedIn(data, "part", p)
		for part in p do
			if not parts[part] then
				parts[part] = true
				local src = `assets/effects/parts/{part}.json`
				mirror(src, `{root}/assets/effects/parts/{part}.json`, "parts", part)
				walk(readJsonFile(src))
			end
		end
	end
	for effect in effects do
		local src = `assets/effects/{effect}.json`
		if mirror(src, `{root}/assets/effects/{effect}.json`, "effects", effect) then
			mirror(
				`assets/effects/frames/{effect}.json`,
				`{root}/assets/effects/frames/{effect}.json`,
				"frames",
				effect
			)
			walk(readJsonFile(src))
		end
	end
	-- the registries the Vfx runtime reads from the game's own effects folder (it waits for _textures)
	for _, reg in { { "_textures.json", textures, "textures" }, { "_meshes.json", meshes, "meshes" } } do
		local file, names, kind = reg[1] :: string, reg[2] :: { [string]: boolean }, reg[3] :: string
		local fromProject = readJsonFile(`assets/effects/{file}`)
		local gamePath = `{root}/assets/effects/{file}`
		if
			type(fromProject) == "table" and (next(names) ~= nil or (file == "_textures.json" and next(effects) ~= nil))
		then
			local game = readJsonFile(gamePath) or {}
			local before = serde.encode("json", game)
			if game._help == nil and fromProject._help ~= nil then
				game._help = fromProject._help
			end
			for n in names do
				if fromProject[n] ~= nil and (game[n] == nil or ledger[kind][n]) then
					game[n] = fromProject[n]
					ledger[kind][n] = true
				end
			end
			if serde.encode("json", game) ~= before or not fs.isFile(gamePath) then
				Config.ensureDir(`{root}/assets/effects`)
				fs.writeFile(gamePath, serde.encode("json", game, true) .. "\n")
				written += 1
			end
		end
	end
	if written > 0 then
		fs.writeFile(ledgerPath, serde.encode("json", ledger, true) .. "\n")
	end
	return written
end

function Game.create(name: string): Run.Step
	if not string.match(name, "^[A-Z][A-Za-z0-9]*$") then
		return Run.step(
			"game new",
			false,
			`"{name}" is not a PascalCase name`,
			{ next_action = "e.g. kit game new RpgArena" }
		)
	end
	local root = dir(name)
	if fs.isFile(`{root}/GAME.md`) then
		return Run.step("game new", true, root, { summary = `{name} already exists — made it active` })
	end
	for _, d in DIRS do
		Config.ensureDir(`{root}/{d}`)
	end
	for _, d in { "src/net", "src/moves", "src/world", "src/ui", "src/animations", "src/models", "assets/effects" } do
		fs.writeFile(`{root}/{d}/.gitkeep`, "")
	end
	-- EVERY folder the layout gate requires keeps a placeholder while empty: git does not keep empty folders, so a
	-- fresh clone (or kit prove's sandbox) would miss assets/ui, assets/animations, assets/models and fail the gate
	for _, d in DIRS do
		if #fs.readDir(`{root}/{d}`) == 0 then
			fs.writeFile(`{root}/{d}/.gitkeep`, "")
		end
	end
	fs.writeFile(`{root}/GAME.md`, template("GAME.md", name))
	fs.writeFile(`{root}/README.md`, template("README.md", name))
	fs.writeFile(`{root}/kit.config.json`, serde.encode("json", { name = name }, true) .. "\n")
	fs.writeFile(`{root}/default.project.json`, serde.encode("json", project(name), true) .. "\n")
	fs.writeFile(
		`{root}/.gitignore`,
		"# generated: the place, previews, checks\nbuild/\n# the kit runtime, synced from the project (kit game sync) — never edit\nsrc/kit/\n"
	)
	fs.writeFile(
		`{root}/assets/ids.json`,
		'{\n  "sounds": {},\n  "models": {},\n  "textures": {},\n  "images": {}\n}\n'
	)
	fs.writeFile(
		`{root}/assets/sounds/_events.json`,
		'{\n "maxVoices": 32,\n "buses": {},\n "snapshots": {},\n "events": {}\n}\n'
	)
	Game.syncKit(name)
	return Run.step("game new", true, root, { summary = `{root}/ made (brief, layout, Rojo project, kit runtime)` })
end

function Game.activate(name: string?)
	Config.ensureDir(GAMES)
	fs.writeFile(Config.ACTIVE, (name or "none") .. "\n")
	Config.setGame(name)
end

-- the brief's open questions
local function todos(name: string): { string }
	local out = {}
	local p = `{dir(name)}/GAME.md`
	if not fs.isFile(p) then
		return out
	end
	local section = "?"
	for line in string.gmatch(fs.readFile(p), "[^\n]+") do
		local h = string.match(line, "^## (.+)")
		if h then
			section = h
		elseif string.find(line, "^TODO") then
			table.insert(out, section)
		end
	end
	return out
end

-- layout problems of one game (missing folders / files)
local function layoutProblems(name: string): { string }
	local out = {}
	for _, f in FILES do
		if not fs.isFile(`{dir(name)}/{f}`) then
			table.insert(out, `{name}: no {f}`)
		end
	end
	for _, d in DIRS do
		if not fs.isDir(`{dir(name)}/{d}`) then
			table.insert(out, `{name}: no {d}/`)
		end
	end
	return out
end

-- every file under the root's gameplay folders (src/server, src/client, src/shared)
local function rootGameplay(): { string }
	local out = {}
	local function walk(p: string)
		if not fs.isDir(p) then
			return
		end
		for _, n in fs.readDir(p) do
			local q = `{p}/{n}`
			if fs.isDir(q) then
				walk(q)
			elseif n ~= ".gitkeep" then
				table.insert(out, q)
			end
		end
	end
	for _, d in { "src/server", "src/client", "src/shared" } do
		walk(d)
	end
	table.sort(out)
	return out
end

-- THE gate (kit verify): no new gameplay code at the project root, every game laid out the same way
function Game.layoutStep(): Run.Step
	local problems, notes = {}, {}
	-- (whatever game is active: the root's own gameplay folders are checked by their literal paths)
	if Config.isKitSource() or fs.isDir(GAMES) then
		local now = rootGameplay()
		if not fs.isFile(LEGACY) and not Config.isKitSource() then
			-- first run (a project): what is at the root today is accepted as it is (the owner's scratch); nothing new joins it.
			-- The record is written even for an empty root: without it every later run would be a first run again and
			-- accept whatever had reached the root since (the kit's own repo, marked by kit/.source, never writes one)
			Config.ensureDir(GAMES)
			fs.writeFile(LEGACY, serde.encode("json", { accepted = now }, true) .. "\n")
			table.insert(notes, `{#now} existing root file(s) recorded in {LEGACY}`)
		else
			-- (the kit's own repo grandfathers nothing: no LEGACY there means no root gameplay file is ever accepted)
			local ok, legacy = false, nil
			if fs.isFile(LEGACY) then
				ok, legacy = pcall(serde.decode, "json" :: any, fs.readFile(LEGACY))
			end
			local accepted = {}
			for _, f in (ok and legacy.accepted) or {} do
				accepted[f] = true
			end
			for _, f in now do
				if not accepted[f] then
					table.insert(
						problems,
						`{f} is gameplay code at the project root — it belongs to a game: games/<Name>/{string.sub(
							f,
							1
						)}`
					)
				end
			end
		end
	end
	local games = if Config.game() then { Config.game() :: string } else Game.list()
	-- every game serves on its own Rojo port (two on one port collide and Studio connects to the wrong one)
	for _, pr in Game.portProblems() do
		table.insert(problems, `{pr.game}: {pr.why} - lune run kit game ports --fix`)
	end
	for _, g in games do
		for _, p in layoutProblems(g) do
			table.insert(problems, p)
		end
		local open = todos(g)
		if #open > 0 then
			table.insert(notes, `{g}: the brief has {#open} open question(s) ({table.concat(open, ", ")})`)
		end
	end
	local ok = #problems == 0
	local summary = if ok
		then `{#games} game(s) laid out, no gameplay code at the root{if #notes > 0
			then " — " .. table.concat(notes, "; ")
			else ""}`
		else `{#problems} problem(s): {problems[1]}`
	return Run.step("games layout", ok, table.concat(problems, "\n"), {
		status = if ok then "pass" else "fail",
		summary = summary,
		next_action = if ok
			then nil
			else "move it into its game (kit game new <Name> / kit game use <Name>, then re-create it there), or make games/<Name>/ whole again: kit game check <Name>",
	})
end

local function checkCmd(name: string?): number
	name = name or Config.game()
	if not name then
		return Run.report(
			"game-check",
			{},
			C.USAGE,
			"game check: which game?",
			"lune run kit game check <Name>  (kit game list)"
		)
	end
	if not fs.isFile(`{dir(name)}/GAME.md`) then
		return Run.report("game-check", {}, C.USAGE, `game check: no game {name}`, "lune run kit game list")
	end
	local steps = {}
	local problems = layoutProblems(name)
	table.insert(
		steps,
		Run.step("layout", #problems == 0, table.concat(problems, "\n"), {
			summary = if #problems == 0 then "every folder and file in place" else problems[1],
		})
	)
	local synced = Game.syncKit(name)
	table.insert(
		steps,
		Run.step("kit runtime", true, "", {
			summary = if synced > 0 then `{synced} file(s) synced from src/kit` else "src/kit in sync",
		})
	)
	Config.ensureDir(`{dir(name)}/build`)
	table.insert(
		steps,
		Run.spawn(
			"rojo build",
			Run.tool("rojo"),
			{ "build", `{dir(name)}/default.project.json`, "-o", `{dir(name)}/build/place.rbxlx` },
			true
		)
	)
	local open = todos(name)
	local ok = #problems == 0 and steps[3].ok
	local summary =
		`game check {name}: {if ok then "laid out and builds" else "NOT whole"}; the brief has {#open} open question(s)`
	local nxt = if not ok
		then (problems[1] or "read the rojo build output above")
		elseif
			#open > 0
		then `ASK THE OWNER about: {table.concat(open, ", ")} — write the answers in {dir(name)}/GAME.md`
		else `work in it: kit status (the game's board), kit new system <Name>, kit new world <Name>, ... then kit verify`
	return Run.report("game-check", steps, if ok then C.PASS else C.CONTENT, summary, nxt)
end

function Game.register(Cli: any)
	Cli.command(
		"start",
		"game",
		"game [list] | new <Name> [--no-activate] | use <Name>|none [--switch] | ports [--fix] | check [<Name>] | sync [<Name>] | plan [<Name>]",
		"GAMES: each game is a folder games/<Name>/ (brief, src, assets, tests, board, docs, Rojo project); every command works inside the active one. Making a game? kit game new <Name> FIRST",
		function(args)
			local sub = args[1] or "list"
			if sub == "list" then
				local games = Game.list()
				local active = Config.game()
				local lines = {}
				for _, g in games do
					table.insert(
						lines,
						`  {if g == active then "*" else " "} {g}  ({dir(g)}/)  rojo port {Game.ports().games[g] or "NONE - kit game ports --fix"}  {#todos(
							g
						)} open question(s) in GAME.md`
					)
				end
				print(if #lines > 0 then table.concat(lines, "\n") else "  (no games yet)")
				if Config.missingGame then
					print(`  ! the active game "{Config.missingGame}" has no folder — kit game use <Name> | none`)
				end
				return Run.report(
					"game",
					{},
					C.PASS,
					`game: {#games} game(s); active: {active or "none (the project root)"}`,
					if active
						then `everything you make lands in {dir(active)}/ — kit status shows its board`
						else "making a game? lune run kit game new <Name> FIRST; working on one: kit game use <Name>"
				)
			elseif sub == "ports" then
				-- every game's own Rojo port (and the root's); --fix gives a game with none, or a shared one, its own
				local fix = table.find(args, "--fix") ~= nil
				local fixed = {}
				if fix then
					for _, pr in Game.portProblems() do
						table.insert(fixed, `{pr.game} -> {Game.assignPort(pr.game)}`)
					end
				end
				local ports = Game.ports()
				print(`  root project  rojo serve default.project.json  -> localhost:{ports.root}`)
				local names = Game.list()
				table.sort(names)
				for _, g in names do
					print(`  {g}  rojo serve {dir(g)}/default.project.json  -> localhost:{ports.games[g] or "?"}`)
				end
				local left = Game.portProblems()
				for _, pr in left do
					print(`  ! {pr.game}: {pr.why}`)
				end
				return Run.report(
					"game",
					{},
					if #left == 0 then C.PASS else C.CONTENT,
					if #left == 0
						then `game ports: every game has its own Rojo port{if #fixed > 0
							then " (" .. table.concat(fixed, ", ") .. ")"
							else ""}`
						else `game ports: {#left} game(s) share or lack a port`,
					if #left == 0
						then "serve one game: rojo serve games/<Name>/default.project.json, then point Studio's Rojo plugin at its port"
						else "lune run kit game ports --fix"
				)
			elseif sub == "new" then
				local name = args[2]
				if not name then
					return Run.report(
						"game",
						{},
						C.USAGE,
						"game new: which name?",
						"lune run kit game new <PascalName>"
					)
				end
				-- the same as `kit new game <Name>`: the folder, then the skeleton (server, client, services, config)
				return Cli.dispatch({ "new", "game", name, table.unpack(args, 3) })
			elseif sub == "use" then
				local name = args[2]
				if not name then
					return Run.report("game", {}, C.USAGE, "game use: which game?", "lune run kit game use <Name>|none")
				end
				if name == "none" then
					Game.activate(nil)
					return Run.report(
						"game",
						{},
						C.PASS,
						"game: none active — commands work at the project root",
						"none"
					)
				end
				if not fs.isFile(`{dir(name)}/GAME.md`) then
					return Run.report(
						"game",
						{},
						C.USAGE,
						`game use: no game {name}`,
						`make it: lune run kit game new {name}  (or kit game list)`
					)
				end
				-- games/.active is ONE file for every session in this checkout: switching it moves every session that
				-- relies on it. A recent switch to a DIFFERENT game is refused without --switch (use --game per command)
				local current = Config.game()
				local okM, meta = pcall(fs.metadata, Config.ACTIVE)
				local at = if okM and meta and meta.modifiedAt then meta.modifiedAt.unixTimestamp else 0
				local blocked = Game.switchBlocked(current, name, at, os.time(), table.find(args, "--switch") ~= nil)
				if blocked then
					return Run.report(
						"game",
						{},
						C.USAGE,
						`game use: {blocked}`,
						`work in {name} without moving anyone: add --game {name} to each command (lune run kit status --game {name}); or, if no other session is in {current}: lune run kit game use {name} --switch`
					)
				end
				Game.activate(name)
				local synced = Game.syncKit(name)
				for _, l in require("../lib/boardweb").arrive("kit game use") do
					print(l)
				end
				return Run.report(
					"game",
					{},
					C.PASS,
					`game: {name} is active — every command now reads and writes {dir(name)}/{if synced > 0
						then ` ({synced} kit runtime file(s) synced)`
						else ""}`,
					`lune run kit status  (the game's board and brief). Rojo: rojo serve {dir(name)}/default.project.json -> localhost:{Game.ports().games[name] or "?"} (kit game ports). games/.active is shared by every session in this checkout; another session working elsewhere passes --game <Name>`
				)
			elseif sub == "plan" then
				-- ONE game's route stage by stage (kit/systems/gameplan.py): brief -> world -> systems -> net -> moves ->
				-- playtests -> accept; the first stage not done gets its commands
				local name = args[2] or Config.game()
				if not name or not fs.isDir(dir(name)) then
					return Run.report("game", {}, C.USAGE, "game plan: which game?", "lune run kit game plan <Name>")
				end
				local step = Run.content("game plan", Run.tool("python"), { "kit/systems/gameplan.py", name })
				local r = step.result or {}
				for i, st in r.stages or {} do
					print(
						string.format(
							"  %d %-40s %-8s %s",
							i,
							st.title,
							string.upper(st.status),
							if #(st.missing or {}) > 0 then "- " .. table.concat(st.missing, "; ") else ""
						)
					)
				end
				for _, st in r.stages or {} do
					if st.key == r.next then
						print("")
						print(`  next: {st.title}`)
						for _, c in st.commands do
							print(`    {c}`)
						end
					end
				end
				return Run.report(
					"game-plan",
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or "game plan: crashed",
					r.next_action or "read the error above"
				)
			elseif sub == "check" then
				return checkCmd(args[2])
			elseif sub == "sync" then
				local name = args[2] or Config.game()
				if not name or not fs.isDir(dir(name)) then
					return Run.report("game", {}, C.USAGE, "game sync: which game?", "lune run kit game sync <Name>")
				end
				local n = Game.syncKit(name)
				return Run.report(
					"game",
					{},
					C.PASS,
					`game sync {name}: {n} file(s) synced (the kit runtime, the project's sound ids, and the clips + effects its moves name)`,
					"none"
				)
			end
			return Run.report(
				"game",
				{},
				C.USAGE,
				`game: unknown sub-command "{sub}"`,
				"lune run kit game list | new | use | check | sync"
			)
		end
	)
end

return Game

-- moves.luau — `kit move [<Set>]`: moves as data (assets/moves/<Name>.json + assets/moves/sets/<Set>.json) are
-- resolved, validated and measured; build/moves/<Set>.json + a MOVE SHEET (kit/systems/movesheet.py) per set.
--   "frames": "from_anim" takes startup / active / recovery from the anim lane's MEASURED phases
--   (build/animations/<anim>.metrics.json: anticipation / action / recovery), widened to "active_min" frames
--   (default 3: a 1-frame hitbox does not survive network play) around the measured action.
-- A set: { "name": "BgFists", "health": 100, "moves": ["BgM1_1", ...], "combo": ["BgM1_1", "BgM1_2", ...] }
-- Gates (errors): MovesRules.validate (ghost hitboxes, huge boxes, bad cancel windows, unknown cancels), an anim
-- that does not exist, a combo link that is not a cancel. Measured: on-block advantage per move, the combo's
-- damage with scaling, hits to kill, the combo's time.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Config = require("../lib/config")
local MovesRules = require("../../src/kit/MovesRules")
local Run = require("../lib/run")

-- (inside the active game when one is: init.luau applies --game before any command module loads)
local MOVES = Config.path("moves")
local OUT = Config.path("movesOut") -- generated: ReplicatedStorage.KitMoves (never edit; change assets/moves and re-run)

local MovesCmd = {}

local function readJson(path: string): any?
	if not fs.isFile(path) then
		return nil
	end
	local ok, v = pcall(serde.decode, "json" :: any, fs.readFile(path))
	return if ok then v else nil
end

-- resolve "from_anim" frames from the anim lane's measured phases (read-only: build/animations/<anim>.metrics.json)
local function resolveFrames(move: any, problems: { string })
	if move.frames ~= "from_anim" then
		return
	end
	-- the game's own measured anim first, else the project's (a game CONSUMES the anim lane's work by reference:
	-- read-only, never copied)
	local m = readJson(`{Config.build("animations")}/{move.anim}.metrics.json`)
		or readJson(`build/animations/{move.anim}.metrics.json`)
	if not m or type(m.phases) ~= "table" then
		table.insert(
			problems,
			`{move.name}: "from_anim" but no measured anim build/animations/{tostring(move.anim)}.metrics.json (run: lune run kit anim {tostring(
				move.anim
			)})`
		)
		move.frames = { fps = 60, startup = 0, active = 1, recovery = 0 }
		return
	end
	local fps = m.fps or 60
	local a0, a1 = m.phases.action[1], m.phases.action[2]
	local activeMin = move.active_min or 3
	local active = math.max(activeMin, a1 - a0)
	local startup = math.max(0, a0 - math.floor((active - (a1 - a0)) / 2))
	local total = m.frames or (m.phases.recovery[2] + 1)
	move.frames = { fps = fps, startup = startup, active = active, recovery = math.max(0, total - startup - active) }
	-- hitboxes written without frames cover the whole active window
	for _, hb in move.hitboxes or {} do
		if hb.frames == nil then
			hb.frames = { startup, startup + active - 1 }
		end
	end
	move._from_anim = { action = { a0, a1 }, fastest = m.fastest }
end

-- ------------------------------------------------------------ what a move names must exist (the lanes' handoff)
-- A move is where the lanes meet by NAME: its animation (anim lane), its sound events (sfx lane) and its effects
-- (vfx lane). A name nothing answers to is silent in game, so every one is checked where this game's runtime reads it;
-- a piece that exists only at the project root is named as such (the game does not have it yet).
local function animExists(dir: string, name: string): boolean
	if fs.isDir(dir) then
		for _, f in fs.readDir(dir) do
			if f == `{name}.json` or string.sub(f, 1, #name + 1) == `{name}.` then
				return true
			end
		end
	end
	return false
end

local eventCache: { [string]: { [string]: boolean } } = {}
local function soundEvents(path: string): { [string]: boolean }
	if eventCache[path] then
		return eventCache[path]
	end
	local set: { [string]: boolean } = {}
	local d = readJson(path)
	if d and type(d.events) == "table" then
		for name in d.events do
			set[string.lower(name)] = true
		end
	end
	eventCache[path] = set
	return set
end

-- a missing reference in words, or nil; `where` = this game's folder and the project root (the same when no game)
local function missing(kind: string, name: string): string?
	local gameRoot = Config.root()
	local function has(root: string): boolean
		if kind == "anim" then
			return animExists(root .. "assets/animations", name) or animExists(root .. "src/animations", name)
		elseif kind == "sound" then
			return soundEvents(root .. "assets/sounds/_events.json")[string.lower(name)] == true
		else
			return fs.isFile(`{root}assets/effects/{name}.json`)
		end
	end
	if has(gameRoot) then
		return nil
	end
	local what = if kind == "anim"
		then `animation "{name}" (assets/animations/{name}.json - the anim lane: kit anim new {name})`
		elseif kind == "sound" then `sound event "{name}" (assets/sounds/_events.json - the sfx lane)`
		else `effect "{name}" (assets/effects/{name}.json - the vfx lane: kit new vfx {name})`
	if gameRoot ~= "" and has("") then
		return `{what} exists in the project but not in this game ({gameRoot})`
	end
	return `no {what}`
end

local function references(move: any, missingRefs: { string })
	local function check(kind: string, name: any, where: string)
		if type(name) == "string" and name ~= "" then
			local why = missing(kind, name)
			if why then
				table.insert(missingRefs, `{move.name}: {where} names {why}`)
			end
		end
	end
	check("anim", move.anim, "anim")
	for i, cue in (if type(move.sfx) == "table" then move.sfx else {}) :: { any } do
		check("sound", type(cue) == "table" and cue.event, `sfx {i}`)
	end
	for i, cue in (if type(move.vfx) == "table" then move.vfx else {}) :: { any } do
		check("effect", type(cue) == "table" and cue.preset, `vfx {i}`)
	end
	local onHit = if type(move.onHit) == "table" then move.onHit else {}
	check("sound", onHit.sfx, "onHit.sfx")
	check("effect", onHit.vfx, "onHit.vfx")
	check("anim", onHit.reaction, "onHit.reaction")
end

-- the names one move gives that nothing answers to (kit move prints them; the spec checks them)
function MovesCmd.missingReferences(move: any): { string }
	local out = {}
	references(move, out)
	return out
end

local function comboSim(set: any, moves: { [string]: any }): any
	local chain = set.combo or {}
	local total, time, hits = 0, 0, {}
	for i, name in chain do
		local mv = moves[name]
		if not mv then
			continue
		end
		local o = MovesRules.resolve(mv, { now = 0 }, i)
		total += o.damage
		local tl = MovesRules.timeline(mv)
		-- time to the next move: cancel at the earliest frame of the window (or the whole move)
		local nextName = chain[i + 1]
		local frames = tl.total
		if nextName and type(mv.cancel) == "table" and table.find(mv.cancel.into or {}, nextName) then
			frames = mv.cancel.from
		end
		time += frames / tl.fps
		table.insert(hits, { move = name, damage = math.floor(o.damage * 100 + 0.5) / 100 })
	end
	local health = set.health or 100
	return {
		damage = math.floor(total * 100 + 0.5) / 100,
		seconds = math.floor(time * 1000 + 0.5) / 1000,
		combos_to_kill = if total > 0 then math.ceil(health / total) else nil,
		hits = hits,
	}
end

local function compileSet(setPath: string): (boolean, any, { string }, any, { string })
	local problems: { string } = {}
	local missingRefs: { string } = {} -- names nothing answers to (reported, not blocking)
	local set = readJson(setPath)
	if not set or type(set.moves) ~= "table" then
		return false, nil, { `{setPath}: a set needs "moves": [names]` }, nil
	end
	local moves: { [string]: any } = {}
	local names: { [string]: boolean } = {}
	for _, n in set.moves do
		names[n] = true
	end
	for _, n in set.moves do
		local mv = readJson(`{MOVES}/{n}.json`)
		if not mv then
			table.insert(problems, `move "{n}": no {MOVES}/{n}.json`)
			continue
		end
		mv.name = mv.name or n
		resolveFrames(mv, problems)
		references(mv, missingRefs)
		for _, issue in MovesRules.validate(mv, names) do
			table.insert(problems, `{n}: {issue}`)
		end
		moves[n] = mv
	end
	for i = 1, #(set.combo or {}) - 1 do
		local a, b = set.combo[i], set.combo[i + 1]
		local mv = moves[a]
		if mv and not (type(mv.cancel) == "table" and table.find(mv.cancel.into or {}, b)) then
			table.insert(problems, `combo: {a} -> {b} is not a cancel of {a} (add "{b}" to its cancel.into)`)
		end
	end
	local out = { name = set.name, health = set.health or 100, moves = {}, combo = set.combo or {} }
	for _, n in set.moves do
		local mv = moves[n]
		if mv then
			local tl = MovesRules.timeline(mv)
			table.insert(out.moves, {
				name = n,
				anim = mv.anim,
				timeline = tl,
				hitboxes = mv.hitboxes or {},
				cancel = mv.cancel,
				damage = mv.damage or 0,
				on_block = MovesRules.onBlock(mv),
				block = mv.block or "blockable",
				vfx = mv.vfx,
				sfx = mv.sfx,
				from_anim = mv._from_anim,
			})
		end
	end
	out.combo_sim = comboSim(set, moves)
	-- what the game runs (ReplicatedStorage.KitMoves.<Set>): every move resolved (frames from the anim), as data
	local runtime = { name = set.name, health = set.health or 100, combo = set.combo or {}, moves = {} }
	-- the set's PARRY on screen ({ anim = <the defender's deflect clip>, stagger = <the attacker's> }: Moves plays them
	-- when a parry lands; the anim lane's KatanaKaeshi, 2026-10-24)
	if type(set.parry) == "table" then
		runtime.parry = set.parry
		for _, key in { "anim", "stagger" } do -- the clips a parry plays must exist like any move's
			local clip = set.parry[key]
			local why = if type(clip) == "string" and clip ~= "" then missing("anim", clip) else nil
			if why then
				table.insert(missingRefs, `set parry.{key} names {why}`)
			end
		end
	end
	for n, mv in moves do
		local copy = table.clone(mv)
		copy._from_anim = nil
		runtime.moves[n] = copy
	end
	return #problems == 0, out, problems, runtime, missingRefs
end

-- compile every set; write = false only checks src/moves is up to date (kit verify)
function MovesCmd.step(write: boolean): Run.Step
	local setDir = `{MOVES}/sets`
	if not fs.isDir(setDir) then
		return Run.step("moves", true, "", { summary = "no movesets (assets/moves/sets is empty)" })
	end
	local problems, drift, made = {}, {}, 0
	for _, f in fs.readDir(setDir) do
		if string.sub(f, -5) ~= ".json" then
			continue
		end
		local name = string.gsub(f, "%.json$", "")
		local ok, _, probs, runtime = compileSet(`{setDir}/{f}`)
		for _, p in probs do
			table.insert(problems, `{name}: {p}`)
		end
		if ok and runtime then
			local target = `{OUT}/{name}.json`
			local text = serde.encode("json", runtime, true)
			if write then
				Config.ensureDir(OUT)
				fs.writeFile(target, text)
			-- (line endings normalised: autocrlf checks a .json out as CRLF, which is not drift)
			elseif not fs.isFile(target) or (string.gsub(fs.readFile(target), "\r\n", "\n")) ~= text then
				table.insert(drift, target)
			end
			made += 1
		end
	end
	if #problems > 0 then
		return Run.step("moves", false, table.concat(problems, "\n"), {
			status = "fail",
			summary = `{#problems} move problem(s): {problems[1]}`,
			next_action = `fix {problems[1]}`,
		})
	end
	if #drift > 0 then
		return Run.step("moves", false, table.concat(drift, "\n"), {
			status = "fail",
			summary = `{#drift} generated moveset(s) out of date: {table.concat(drift, ", ")}`,
			next_action = "run: lune run kit move",
		})
	end
	return Run.step(
		"moves",
		true,
		"",
		{ summary = `{made} moveset(s) {if write then "written to" else "up to date in"} {OUT}` }
	)
end

function MovesCmd.register(Cli: any)
	Cli.command(
		"code",
		"move",
		"move [<Set>]",
		"moves as data: assets/moves/*.json + sets — frames from the anim's measured phases, validated (ghost hitboxes, cancels, combo links), on-block advantage, combo damage + time-to-kill -> build/moves/<Set>.png",
		function(args)
			local setDir = `{MOVES}/sets`
			if not fs.isDir(setDir) then
				return Run.report(
					"move",
					{},
					Run.CODES.USAGE,
					"move: no sets",
					`create {setDir}/<Set>.json ("moves": [...], "combo": [...]) and {MOVES}/<Move>.json (shape: src/kit/MovesRules.luau)`
				)
			end
			local steps = {}
			local allOk = true
			local firstProblem = nil
			local missingAll, firstMissing = 0, nil
			Config.ensureDir(Config.build("moves"))
			for _, f in fs.readDir(setDir) do
				local name = string.gsub(f, "%.json$", "")
				if string.sub(f, -5) ~= ".json" or (args[1] and args[1] ~= name) then
					continue
				end
				local ok, out, problems, runtime, missingRefs = compileSet(`{setDir}/{f}`)
				if ok and runtime then
					Config.ensureDir(OUT)
					fs.writeFile(`{OUT}/{name}.json`, serde.encode("json", runtime, true))
				end
				for _, p in problems do
					print("  ERROR " .. p)
				end
				-- a name nothing answers to plays as silence in game: loud, and the command fails, but the move data
				-- is still written so the code lane keeps working while another lane makes the piece
				for _, m in missingRefs do
					print("  MISSING " .. m)
				end
				missingAll += #missingRefs
				firstMissing = firstMissing or missingRefs[1]
				firstProblem = firstProblem or problems[1]
				allOk = allOk and ok
				if out then
					local path = `{Config.build("moves")}/{name}.json`
					fs.writeFile(path, serde.encode("json", out, true))
					local sheet =
						Run.content(`move sheet {name}`, Run.tool("python"), { "kit/systems/movesheet.py", path })
					table.insert(steps, sheet)
					if out.combo_sim then
						print(
							`  {name}: combo {#out.combo} hits = {out.combo_sim.damage} damage in {out.combo_sim.seconds} s; {out.combo_sim.combos_to_kill} combo(s) to kill {out.health} HP`
						)
					end
				end
			end
			if not allOk then
				return Run.report("move", steps, Run.CODES.CONTENT, `move: {firstProblem}`, `fix: {firstProblem}`)
			end
			if missingAll > 0 then
				return Run.report(
					"move",
					steps,
					Run.CODES.CONTENT,
					`move: {#steps} set(s) valid, but {missingAll} name(s) nothing answers to - those moves play silent in game`,
					`the lane that owns each piece makes it (or bring it into this game): {firstMissing}`
				)
			end
			return Run.report(
				"move",
				steps,
				Run.CODES.PASS,
				`move: {#steps} set(s) valid, every animation, sound and effect they name exists — sheets in {Config.build(
					"moves"
				)}`,
				`look at {Config.build("moves")}/<Set>.png`
			)
		end
	)
end

return MovesCmd

--!strict
-- contract.luau — `kit contract ...`: the CROSS-LANE CONTRACT of a hero weapon (LIMITATIONS_FIXES_V4 §10 item 1 /
-- §13.8 item 1): assets/contracts/<hero>.json binds the built model (its files' SHA-256, sockets, length at 1 stud =
-- 0.28 m), the move set's authored Hit / Cancel / Hitstop frames, the VFX it plays, the sound events swing / hit /
-- parry, the UI trigger and the PROMPT-X packet. Every value is READ from its lane's own files, never typed; any
-- hash change, moved frame, lost socket or sound with no recipe fails `check` by name ("any hash change invalidates
-- downstream builds cleanly"). The rules are kit/lib/contract.luau (pure, kit/test/spec/contract.spec.luau).
--
--   kit contract new <hero> --model <asset | path.manifest.json> --moves <set | path.json> [--from <Game>]
--                    [--vfx <preset | sequence>] [--ui <screen>] [--packet <sha | path>] [--dir <folder>] [--force]
--       --from <Game>: the move set, its clips, effects and sounds live in games/<Game>/ (never Sample Game)
--   kit contract check [<hero>] [--dir <folder>]    re-reads every source; fails by name on any drift
--   kit contract list [--dir <folder>]
-- (default folder: assets/contracts of the active project; kit/selftest/contract/{good,bad} are the self-test's)
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Cli = require("../lib/cli")
local Config = require("../lib/config")
local Contract = require("../lib/contract")
local Run = require("../lib/run")

local ContractCmd = {}

local TEXT = { json = true, luau = true, lua = true, md = true, py = true, txt = true }

local function sha256(path: string): string
	if not fs.isFile(path) then
		return Contract.MISSING
	end
	local bytes = fs.readFile(path)
	local ext = string.match(path, "%.([%w]+)$")
	if ext and TEXT[string.lower(ext)] then
		-- a checkout with core.autocrlf writes CRLF: the same file hashes the same everywhere
		bytes = (string.gsub(bytes, "\r\n", "\n"))
	end
	return serde.hash("sha256", bytes)
end

local function hashString(s: string): string
	return serde.hash("sha256", s)
end

local function readJson(path: string): any?
	if not fs.isFile(path) then
		return nil
	end
	local ok, v = pcall(serde.decode, "json" :: any, fs.readFile(path))
	return if ok then v else nil
end

local function dirOf(path: string): string
	return string.match(path, "^(.*)/[^/]*$") or ""
end

-- `rel` inside the content root (a game's folder) when it has one, else the project's
local function inRoot(root: string, rel: string): string?
	if root ~= "" and fs.isFile(root .. rel) then
		return root .. rel
	end
	if fs.isFile(rel) then
		return rel
	end
	return nil
end

-- a project's private games (profiles.core.exclude_games in its kit.config.json) are never read by kit contract
local function guardGame(path: string?): string?
	if not path then
		return nil
	end
	-- the path as segments ("a/./b/../c" -> "a/c"), lower case, either slash: a game is matched as a whole folder name
	-- ("minigames/<name>" is not it; "games/Other/../<name>" is)
	local parts = {}
	for seg in string.gmatch(string.lower((string.gsub(path, "\\", "/"))), "[^/]+") do
		if seg == ".." then
			table.remove(parts)
		elseif seg ~= "." then
			table.insert(parts, seg)
		end
	end
	local p = "/" .. table.concat(parts, "/") .. "/"
	local core = (Config.load().profiles or {}).core or {}
	for _, g in core.exclude_games or {} do
		local name = tostring(g)
		local low = string.lower(name)
		if p == "/" .. low .. "/" or string.find(p, "/games/" .. low .. "/", 1, true) then
			return `kit contract never reads {name} (games/{name}, profiles.core.exclude_games): pick a hero outside it`
		end
	end
	return nil
end

-- the default kit scale: rbx_transfer.MM_PER_STUD (the 3D lane's own constant), read, not typed here
local function defaultMmPerStud(): (number, string)
	local src = "kit/blender/rbx_transfer.py"
	if fs.isFile(src) then
		local n = tonumber(string.match(fs.readFile(src), "\nMM_PER_STUD%s*=%s*([%d%.]+)"))
		if n then
			return n, `{src} MM_PER_STUD (no real_scale on the model)`
		end
	end
	return 0, `{src}: MM_PER_STUD not found`
end

-- every mm_per_stud the 3D build recorded (facts.cad[*].mm_per_stud: the scale each CAD part was built at; a
-- real_scale model's own) -> one value and where it was read; parts that disagree give the odd one (it fails 0.28)
local function findMm(manifest: any): (number?, string?)
	local found: { { v: number, at: string } } = {}
	local function walk(t: any, at: string)
		if type(t) ~= "table" then
			return
		end
		if type(t.mm_per_stud) == "number" then
			table.insert(found, { v = t.mm_per_stud, at = at .. ".mm_per_stud" })
		end
		-- in a fixed order (the source line is compared by check: it must read the same every time)
		for i = 1, #t do
			walk(t[i], `{at}[{i}]`)
		end
		local keys = {}
		for k in t do
			if type(k) == "string" then
				table.insert(keys, k)
			end
		end
		table.sort(keys)
		for _, k in keys do
			walk(t[k], `{at}.{k}`)
		end
	end
	walk(manifest, "manifest")
	if #found == 0 then
		return nil, nil
	end
	for _, f in found do
		if f.v ~= found[1].v then
			return f.v, `{f.at} disagrees with {found[1].at} ({found[1].v})`
		end
	end
	return found[1].v, `{found[1].at} (and {#found - 1} more alike)`
end

local function madeSounds(dirs: { string }): ({ [string]: boolean }?, string?)
	local args = { "kit/tools/contract_sounds.py" }
	for _, d in dirs do
		table.insert(args, d)
	end
	local step = Run.spawn("contract sounds", Run.tool("python"), args, true)
	local r = step.result
	if not step.ok or type(r) ~= "table" or type(r.names) ~= "table" then
		return nil, if type(r) == "table" then tostring(r.summary) else step.tail
	end
	local made = {}
	for _, n in r.names :: { any } do
		made[tostring(n)] = true
	end
	return made, nil
end

-- every source the contract binds, read into kit/lib/contract.luau's Inputs; madeWith = the resolved arguments
function ContractCmd.gather(hero: string, madeWith: { [string]: any }): (any?, string?)
	-- the model ----------------------------------------------------------------------------------------------
	local manifestPath = tostring(madeWith.model)
	local refused = guardGame(manifestPath) or guardGame(madeWith.moves) or guardGame(madeWith.from)
	if refused then
		return nil, refused
	end
	local manifest = readJson(manifestPath)
	if type(manifest) ~= "table" then
		return nil, `no built model manifest at {manifestPath} (build the model first: kit asset <name>)`
	end
	local asset = tostring(manifest.asset or string.match(manifestPath, "([^/]+)%.manifest%.json$"))
	local files = {}
	for _, g in (if type(manifest.groups) == "table" then manifest.groups else {}) :: { [string]: any } do
		if type(g) == "table" then
			if type(g.fbx) == "string" then
				files[g.fbx] = sha256(g.fbx)
			end
			for _, p in (if type(g.textures) == "table" then g.textures else {}) :: { [string]: any } do
				if type(p) == "string" then
					files[p] = sha256(p)
				end
			end
		end
	end
	if next(files) == nil then
		return nil, `{manifestPath} names no model file (groups[*].fbx)`
	end
	local mm, mmAt = findMm(manifest)
	local mmSource = `{manifestPath} {tostring(mmAt)}`
	if not mm then
		mm, mmSource = defaultMmPerStud()
	end

	-- the move set and its content root ------------------------------------------------------------------------
	local setPath = tostring(madeWith.moves)
	local set = readJson(setPath)
	if type(set) ~= "table" or type(set.moves) ~= "table" then
		return nil, `no compiled move set at {setPath} (kit moves build first)`
	end
	local root = string.match(setPath, "^(.-)src/moves/[^/]+$") or ""
	local moveFiles = {}
	local clips = {}
	local cues = {}
	local function clip(anim: string)
		local c = { files = {}, sword = nil :: any }
		for _, rel in { `assets/animations/{anim}.move.json`, `src/animations/{anim}.model.json` } do
			local p = inRoot(root, rel)
			if p then
				c.files[p] = sha256(p)
				if string.sub(rel, -10) == ".move.json" then
					local mj = readJson(p)
					c.sword = if type(mj) == "table" then mj.sword else nil
				end
			end
		end
		clips[anim] = c
	end
	local function preset(name: string): any
		local seq = inRoot(root, `assets/effects/sequences/{name}.seq.json`)
		if seq then
			return { kind = "sequence", path = seq, sha = sha256(seq) }
		end
		local p = inRoot(root, `assets/effects/{name}.json`)
		if p then
			return { kind = "preset", path = p, sha = sha256(p) }
		end
		return false
	end
	for name, m in set.moves :: { [string]: any } do
		local mp = inRoot(root, `assets/moves/{name}.json`)
		moveFiles[name] = if mp then { path = mp, sha = sha256(mp) } else false
		if type(m) == "table" then
			if type(m.anim) == "string" then
				clip(m.anim)
			end
			for _, v in (if type(m.vfx) == "table" then m.vfx else {}) :: { any } do
				if type(v) == "table" and type(v.preset) == "string" then
					cues[v.preset] = preset(v.preset)
				end
			end
		end
	end
	if type(set.parry) == "table" and type(set.parry.anim) == "string" then
		clip(set.parry.anim)
	end

	local vfx: any = nil
	if type(madeWith.vfx) == "string" then
		local where = preset(madeWith.vfx)
		vfx = if where then { name = madeWith.vfx, kind = where.kind, path = where.path, sha = where.sha } else false
	end

	-- the sounds: the catalogue beside the set, the names its recipes and sets make, the parry's event
	local sfx: any = false
	local catalogPath = inRoot(root, "assets/sounds/_events.json")
	if catalogPath then
		local cat = readJson(catalogPath)
		-- the recipes and sets beside the catalogue, then the project's own (a game's events play the kit
		-- project's sound sets: the SampleDojo's SwordSwing is made by assets/sounds/sets/sword_combat.json) - the same
		-- game-first, project-second rule as every other source here
		local dirs = {}
		for _, d in { dirOf(catalogPath), "assets/sounds" } do
			if fs.isDir(d) and not table.find(dirs, d) then
				table.insert(dirs, d)
			end
		end
		local made, err = madeSounds(dirs)
		if not made then
			return nil, `the sounds in {table.concat(dirs, ", ")} could not be listed: {tostring(err)}`
		end
		sfx = {
			path = catalogPath,
			sha = sha256(catalogPath),
			events = if type(cat) == "table" and type(cat.events) == "table" then cat.events else {},
			made = made,
		}
	end
	local parryEvent = nil
	if type(set.parry) == "table" then
		if type(set.parry.sfx) == "string" then
			parryEvent = { event = set.parry.sfx, source = `{setPath} parry.sfx` }
		else
			-- the runtime plays the parry's sound itself (Moves.luau: Sfx.broadcast("<event>", pos) on a landed parry)
			local rt = inRoot(root, "src/kit/Moves.luau")
			if rt then
				local ev = string.match(fs.readFile(rt), 'broadcast%("([%w_]*[Pp]arry[%w_]*)"')
				if ev then
					-- the label names the kit's runtime, not where it was read: a game's src/kit is a generated sync
					-- of it (gitignored: games/*/src/kit/), so a fresh checkout (kit prove's sandbox) reads
					-- src/kit/Moves.luau and a label of games/<Game>/src/kit/... drifted on nothing but the place
					local label = string.gsub(rt, "^games/[^/]+/src/kit/", "src/kit/")
					parryEvent = { event = ev, source = `{label} (broadcast on a landed parry)` }
				end
			end
		end
	end

	-- the UI screen, the PROMPT-X packet, the uploaded id ------------------------------------------------------
	local ui: any = nil
	if type(madeWith.ui) == "string" then
		local p = inRoot(root, `assets/ui/{madeWith.ui}.json`) or inRoot(root, `assets/ui/screens/{madeWith.ui}.json`)
		ui = if p then { name = madeWith.ui, path = p, sha = sha256(p) } else false
	end
	local packet, packetReason = nil, nil
	if type(madeWith.packet) == "string" then
		local p = madeWith.packet
		if not fs.isFile(p) then
			p = Config.build(`prompt/packets/{madeWith.packet}.json`)
		end
		if fs.isFile(p) then
			packet = { path = p, sha256 = sha256(p) }
		else
			packetReason = `--packet {madeWith.packet}: no such packet`
		end
	else
		local dir = Config.build("prompt/packets")
		local named = {}
		if fs.isDir(dir) then
			local names = fs.readDir(dir)
			table.sort(names)
			for _, f in names do
				if string.sub(f, -5) == ".json" then
					local pk = readJson(`{dir}/{f}`)
					if type(pk) == "table" and (pk.piece == asset or pk.piece == hero) then
						table.insert(named, `{dir}/{f}`)
					end
				end
			end
		end
		if #named == 1 then
			packet = { path = named[1], sha256 = sha256(named[1]) }
		elseif #named > 1 then
			packetReason = `{#named} PROMPT-X packets name {asset}: pick one with --packet <sha>`
		else
			packetReason =
				`no PROMPT-X packet in {dir} names {if hero == asset then asset else `{asset} or {hero}`} (kit prompt compile ... --piece {asset} writes one)`
		end
	end
	local assetId, assetIdReason = nil, nil
	for _, idsPath in { inRoot(root, "assets/ids.json"), "assets/ids.json" } do
		local ids = idsPath and readJson(idsPath)
		if type(ids) == "table" and type(ids.models) == "table" and ids.models[asset] ~= nil then
			assetId = tostring(ids.models[asset])
			break
		end
	end
	if not assetId then
		assetIdReason = `not uploaded: assets/ids.json models has no {asset} (an upload is the owner's: kit upload)`
	end

	return {
		hero = hero,
		madeWith = madeWith,
		model = {
			asset = asset,
			manifestPath = manifestPath,
			manifest = manifest,
			files = files,
			mmPerStud = mm,
			mmPerStudSource = mmSource,
		},
		set = { path = setPath, sha = sha256(setPath), data = set },
		moveFiles = moveFiles,
		clips = clips,
		vfx = vfx,
		cues = cues,
		sfx = sfx,
		parryEvent = parryEvent,
		ui = ui,
		packet = packet,
		packetReason = packetReason,
		assetId = assetId,
		assetIdReason = assetIdReason,
	},
		nil
end

local function defaultDir(): string
	return Config.root() .. "assets/contracts"
end

local function heroes(dir: string): { string }
	local out = {}
	if fs.isDir(dir) then
		for _, f in fs.readDir(dir) do
			if string.sub(f, -5) == ".json" then
				table.insert(out, string.sub(f, 1, -6))
			end
		end
	end
	table.sort(out)
	return out
end

-- check every contract in `dir` (or one hero): the step the self-test and `kit contract check` share
-- opts.emptyOk: no contract in `dir` passes (kit verify on a project with none yet); opts.unbuiltOk: a contract whose
-- model files are ALL absent (build/ is git-ignored: a fresh checkout or a kit prove sandbox has none) is skipped
-- and named, never passed as checked
function ContractCmd.step(dir: string, only: string?, opts: { emptyOk: boolean?, unbuiltOk: boolean? }?): Run.Step
	local o = opts or {}
	local names = if only then { only } else heroes(dir)
	if #names == 0 and o.emptyOk then
		return Run.step("contract", true, "", {
			status = "pass",
			summary = `contract check: no contract in {dir} yet`,
			next_action = "none",
		})
	end
	if #names == 0 then
		return Run.step("contract", false, `no contract in {dir}`, {
			status = "fail",
			summary = `contract check: no contract in {dir}`,
			next_action = "lune run kit contract new <hero> --model <asset> --moves <set> [--from <Game>] --game none",
		})
	end
	local lines, failed, warned, skipped = {}, {}, 0, 0
	local firstFix: string? = nil
	for _, hero in names do
		local path = `{dir}/{hero}.json`
		local stored = readJson(path)
		if type(stored) ~= "table" then
			table.insert(failed, `{hero}: {path} is missing or not JSON`)
			continue
		end
		if o.unbuiltOk and type(stored.model) == "table" and type(stored.model.files) == "table" then
			local built = false
			for p in stored.model.files do
				built = built or fs.isFile(p)
			end
			if not built then
				skipped += 1
				table.insert(lines, `[skip] {hero}: its model is not built in this checkout (build/ is git-ignored)`)
				continue
			end
		end
		local inp, err = ContractCmd.gather(hero, if type(stored.madeWith) == "table" then stored.madeWith else {})
		local problems = if inp
			then Contract.check(stored, Contract.build(inp, hashString))
			else { `sources {tostring(err)}` }
		if #problems == 0 then
			table.insert(
				lines,
				`[ok] {hero}: model {tostring(stored.model and stored.model.asset)} {string.sub(
					tostring(stored.modelSha256),
					1,
					12
				)}, set {tostring(stored.animSet and stored.animSet.name)}, hit frame {tostring(
					stored.movesTimeline and stored.movesTimeline.hitFrame
				)}`
			)
		else
			table.insert(lines, `[FAIL] {hero}: {#problems} problem(s)`)
			for _, p in problems do
				table.insert(lines, `    {hero} {p}`)
			end
			table.insert(failed, `{hero} {problems[1]}`)
			if not firstFix then
				local mw = stored.madeWith or {}
				local args = `--model {tostring(mw.model)} --moves {tostring(mw.moves)}`
				for _, k in { "vfx", "ui", "packet" } do
					if type(mw[k]) == "string" then
						args ..= ` --{k} {mw[k]}`
					end
				end
				firstFix =
					`a lane changed what {hero} binds: rebuild or re-check what reads it, then re-sign only after looking: lune run kit contract new {hero} {args} --dir {dir} --force --game none`
			end
		end
		for _, w in Contract.warnings(stored) do
			warned += 1
			table.insert(lines, `    {hero} warn: {w}`)
		end
	end
	local ok = #failed == 0
	local summary = if ok
		then `contract check: {#names - skipped} contract(s) match their sources{if skipped > 0
			then `, {skipped} not built here`
			else ""}{if warned > 0 then ` ({warned} warning(s))` else ""}`
		else `contract check: {#failed} of {#names} drifted - {failed[1]}`
	return Run.step("contract", ok, table.concat(lines, "\n"), {
		status = if ok then "pass" else "fail",
		summary = summary,
		next_action = if ok then "none - proceed" else firstFix or "read the problems above",
		lines = lines,
	})
end

local function resolveArgs(flags: { [string]: any }): ({ [string]: any }?, string?)
	if type(flags.model) ~= "string" or type(flags.moves) ~= "string" then
		return nil, "contract new needs --model <asset | manifest> and --moves <set | path>"
	end
	local from = if type(flags.from) == "string" then flags.from else nil
	local refused = guardGame(from)
	if refused then
		return nil, refused
	end
	if from and not fs.isDir(`games/{from}`) then
		return nil, `--from {from}: no games/{from}`
	end
	local root = if from then `games/{from}/` else Config.root()
	local model = flags.model
	if not fs.isFile(model) then
		model = Config.build(`models/{model}.manifest.json`)
	end
	local moves = flags.moves
	if not fs.isFile(moves) then
		moves = `{root}src/moves/{moves}.json`
	end
	return {
		model = model,
		moves = moves,
		from = from,
		vfx = if type(flags.vfx) == "string" then flags.vfx else nil,
		ui = if type(flags.ui) == "string" then flags.ui else nil,
		packet = if type(flags.packet) == "string" then flags.packet else nil,
	},
		nil
end

local USAGE =
	"contract new <hero> --model <asset|manifest> --moves <set|path> [--from <Game>] [--vfx <preset>] [--ui <screen>] [--packet <sha>] [--force] | check [<hero>] | list   [--dir <folder>]"

function ContractCmd.register(Cli_: any)
	Cli_.command(
		"work",
		"contract",
		USAGE,
		"the cross-lane contract of a hero weapon (assets/contracts/<hero>.json): model hash + sockets at 1 stud = 0.28 m, the move set's Hit / Cancel / Hitstop frames, VFX, swing / hit / parry sounds, UI trigger, PROMPT-X packet - read from the sources; check fails by name on any drift",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			local sub = args[1]
			local dir = if type(flags.dir) == "string" then flags.dir else defaultDir()
			if sub == "check" then
				local step = ContractCmd.step(dir, args[2])
				if step.ok then
					print(step.tail) -- (a failing step's lines are printed by Run.report)
				end
				local r = step.result
				return Run.report(
					"contract",
					{ step },
					if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
					r.summary,
					r.next_action
				)
			elseif sub == "list" then
				local names = heroes(dir)
				for _, hero in names do
					local c = readJson(`{dir}/{hero}.json`) or {}
					print(
						`  {hero}: model {tostring(c.model and c.model.asset)}, set {tostring(
							c.animSet and c.animSet.name
						)} ({tostring(c.animSet and c.animSet.file)}), modelSha256 {string.sub(
							tostring(c.modelSha256),
							1,
							12
						)}`
					)
				end
				return Run.report(
					"contract",
					{},
					Run.CODES.PASS,
					`contract list: {#names} contract(s) in {dir}`,
					if #names > 0
						then "lune run kit contract check --game none"
						else "lune run kit contract new <hero> --model <asset> --moves <set> --game none"
				)
			elseif sub == "new" and type(args[2]) == "string" then
				local hero = args[2]
				local path = `{dir}/{hero}.json`
				if fs.isFile(path) and not flags.force then
					return Run.report(
						"contract",
						{},
						Run.CODES.USAGE,
						`contract new: {path} exists (re-signing a contract invalidates what was built on it)`,
						`lune run kit contract check {hero} --game none (or add --force after looking at what changed)`
					)
				end
				local madeWith, err = resolveArgs(flags)
				local inp, gerr = nil, nil
				if madeWith then
					inp, gerr = ContractCmd.gather(hero, madeWith)
				end
				if not inp then
					return Run.report(
						"contract",
						{},
						if madeWith then Run.CODES.CONTENT else Run.CODES.USAGE,
						`contract new: {tostring(err or gerr)}`,
						"lune run kit help --all (kit contract)"
					)
				end
				local c = Contract.build(inp, hashString)
				local problems = Contract.validate(c)
				if #problems > 0 then
					for _, p in problems do
						print(`  {hero} {p}`)
					end
					return Run.report(
						"contract",
						{},
						Run.CODES.CONTENT,
						`contract new: {#problems} problem(s) in the sources - {problems[1]}`,
						"fix the lane that owns it (a sound with no recipe: kit sfx catalog; a missing file: build it), then run this again"
					)
				end
				Config.ensureDir(dir)
				fs.writeFile(path, Contract.encode(c))
				local nulls = {}
				for k in c.whyNull do
					table.insert(nulls, k)
				end
				table.sort(nulls)
				for _, k in nulls do
					print(`  null {k}: {c.whyNull[k]}`)
				end
				for _, w in Contract.warnings(c) do
					print(`  warn: {w}`)
				end
				return Run.report(
					"contract",
					{},
					Run.CODES.PASS,
					`contract new: {path} written (model {c.model.asset} {string.sub(c.modelSha256, 1, 12)}, hit frame {tostring(
						c.movesTimeline.hitFrame
					)}, {#nulls} field(s) null with a reason)`,
					`lune run kit contract check {hero} --game none`
				)
			end
			return Run.report("contract", {}, Run.CODES.USAGE, "contract: new | check | list", "lune run kit " .. USAGE)
		end
	)
end

return ContractCmd

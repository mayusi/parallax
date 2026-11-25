-- lanelocks.luau — the quality locks of the lanes whose build commands are thin (sfx, 3d, world, anim) and the verdict
-- cap: a piece made after the locks (board/locks.json lists the older ones) builds only when its quality step is done
-- or the OWNER waived it.
--   sfx   a new sound or set needs the owner's chosen reference (kit approve sfx <name> "<their words>" --by owner),
--         or their synth-only waiver (--waive refs)
--   3d    a new asset needs its brief (assets/models/<name>.brief.md); a hero / aaa / complex one needs the owner's
--         approval of it (kit approve 3d <name> ...), or their waiver (--waive brief); and its reference study
--         (assets/models/<name>.study.md passing kit study: every reference read, our version decided, the lessons
--         it applies cited) unless it predates the study lock (grandfathered["3d-study"]), is a kit make prop, or
--         the owner waived it (--waive study)
--   world a new world needs >= 6 real stills + a measured REFS.md in <worlds>/refs/<Name>/ (the world plan's refs
--         stage), or the owner's waiver (--waive refs)
--   anim  a new move dossier is schema 2 (measured evidence; kit/anim/proc_dossier.py refuses it at the build too)
--   cap   a lane holds at most OPEN_CAP new pieces the owner has not scored IN EACH PROJECT (the kit home and every
--         games/<Name> count apart - the owner, 2026-11-10: "Yes, per game"): kit new refuses the next one, the build
--         commands refuse a new piece past it, and kit verify fails above it
-- The vfx (scene gate) and ui (refs lock in the compile) locks live in their own gates. The checks list the SAME files
-- the builders take (a name the builder renders is never skipped here). Each returns the problems (empty = passes;
-- `root` = one content folder, e.g. a selftest fixture); LaneLocks.step() runs them all, in the project root and
-- every games/<Name>/, for kit verify.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Config = require("./config")
local Locks = require("./locks")
local Run = require("./run")
local Season = require("./worldseason")
local Stream = require("./worldstream")
-- (every rule below that walks a blueprint's steps walks Prefab.flat(bp): the steps with its prefabs opened, so that
-- nothing is hidden from a rule by being put in a prefab; a step's number in a message is then its place in that
-- list, which is the blueprint's own "build" number only when it has no prefabs)
local Prefab = require("./worldprefab")

local LaneLocks = {}

LaneLocks.OPEN_CAP = 3

-- the project root and every games/<Name>/ (each lays out its content the same way) - but a game the active profile
-- leaves out (`--profile core`: the games a project lists in profiles.core.exclude_games) is not walked
function LaneLocks.roots(): { string }
	local roots = { "" }
	local skip = Config.excludedGames()
	if fs.isDir("games") then
		for _, g in fs.readDir("games") do
			if fs.isDir(`games/{g}`) and not skip[g] then
				table.insert(roots, `games/{g}/`)
			end
		end
	end
	return roots
end

-- the stems of <dir>/*.json that `keep` accepts, sorted
local function listing(dir: string, keep: (string) -> boolean): { string }
	local out = {}
	if fs.isDir(dir) then
		for _, file in fs.readDir(dir) do
			local stem = string.match(file, "^(.+)%.json$")
			if stem and fs.isFile(`{dir}/{file}`) and keep(stem) then
				table.insert(out, stem)
			end
		end
	end
	table.sort(out)
	return out
end

local function explicit(names: { string }?): boolean
	return names ~= nil and #names > 0 and table.find(names, "all") == nil
end

-- (path, name) of each piece to check: the named ones exactly as the builder resolves them (a name, or a path to a
-- .json file), else what the builder takes for "all"
local function pieces(dir: string, names: { string }?, keepAll: (string) -> boolean): { { string } }
	local out = {}
	if explicit(names) then
		for _, n in names :: { string } do
			if string.sub(n, -5) == ".json" and fs.isFile(n) then
				table.insert(out, { n, (string.match(n, "([^/\\]+)%.json$")) or n })
			else
				table.insert(out, { `{dir}/{n}.json`, n })
			end
		end
	else
		for _, n in listing(dir, keepAll) do
			table.insert(out, { `{dir}/{n}.json`, n })
		end
	end
	return out
end

-- ------------------------------------------------------------ the verdict cap
-- a piece's name as verdicts spell it in any case or separator (KatanaKesa = katana_kesa)
local function key(name: string): string
	return (string.gsub(string.lower(name), "[^%w]", ""))
end

-- each lane's pieces: (folder under a project root, Lua pattern -> the piece's name); the same files its builder takes
local PIECES: { [string]: { { string } } } = {
	ui = { { "assets/ui", "^([^%.]+)%.json$" } }, -- the compiler skips dotted files (<Name>.judge.json)
	sfx = { { "assets/sounds", "^([^%._][^%.]*)%.json$" }, { "assets/sounds/sets", "^(.+)%.json$" } },
	["3d"] = { { "assets/models", "^build_(.+)%.py$" } },
	world = { { "assets/worlds", "^(.+)%.json$" } },
	anim = { { "assets/animations/dossiers", "^([^_].*)%.json$" } },
	vfx = { { "assets/effects", "^([^_].*)%.json$" } },
}

local scoredCache: { [string]: { [string]: boolean } } = {}

-- the normalized names of the lane's pieces with an OWNER verdict (an inferred one is not the owner's)
local function scored(lane: string): { [string]: boolean }
	if scoredCache[lane] then
		return scoredCache[lane]
	end
	local Vault = require("./vault")
	local set: { [string]: boolean } = {}
	for _, n in Vault.verdicts(lane) do
		if Vault.ownersOwn(n.front) and Locks.isOwner({ by = n.front.by or "owner" }) and n.front.name then
			set[key(tostring(n.front.name))] = true
		end
	end
	scoredCache[lane] = set
	return set
end

-- the lane's pieces made after the locks with no owner verdict, nor their waiver of the verdict step;
-- `projectRoots` = the folders to scan (default: the project root + every games/<Name>)
function LaneLocks.unscored(lane: string, projectRoots: { string }?): { string }
	local out = {}
	for _, root in projectRoots or LaneLocks.roots() do
		for _, spec in PIECES[lane] or {} do
			local dir = root .. spec[1]
			if fs.isDir(dir) then
				for _, file in fs.readDir(dir) do
					local n = string.match(file, spec[2])
					if
						n
						and not Locks.grandfathered(lane, `{dir}/{file}`)
						and not scored(lane)[key(n)]
						and not Locks.waiver(lane, n, "verdict")
					then
						table.insert(out, n)
					end
				end
			end
		end
	end
	table.sort(out)
	return out
end

-- the project a path sits in: "games/<Name>/", or "" for the kit home - each project holds its own verdict cap
function LaneLocks.projectOf(path: string): string
	local p = string.gsub(string.gsub(path, "\\", "/"), "^%./", "")
	local g = string.match(p, "^games/([^/]+)/")
	return if g then `games/{g}/` else ""
end

-- a NEW piece past the cap: its project's lane already holds OPEN_CAP other new pieces the owner has not scored
function LaneLocks.cap(lane: string, name: string, path: string): string?
	if Locks.grandfathered(lane, path) or scored(lane)[key(name)] or Locks.waiver(lane, name, "verdict") then
		return nil
	end
	local others = {}
	for _, n in LaneLocks.unscored(lane, { LaneLocks.projectOf(path) }) do
		if key(n) ~= key(name) then
			table.insert(others, n)
		end
	end
	if #others < LaneLocks.OPEN_CAP then
		return nil
	end
	return `{name}: the {lane} lane already holds {#others} new pieces the owner has not scored ({table.concat(
		others,
		", "
	)}) - the cap is {LaneLocks.OPEN_CAP}: show them {others[1]}, record their verdict (lune run kit verdict <kind> {others[1]} <0-10> "<their words>"), then build the next`
end

-- ------------------------------------------------------------ sfx
-- sounds (<sounds>/<name>.json) and sets (<setsDir or sounds/sets>/<set>.json); `names` limits the check (nil = all),
-- `only` to one kind ("sounds" | "sets"; nil = both)
function LaneLocks.sfx(names: { string }?, only: string?, root: string?, setsDir: string?): { string }
	local dir = root or Config.path("sounds")
	local problems = {}
	local function check(path: string, n: string, what: string)
		if Locks.grandfathered("sfx", path) then
			return
		end
		if not (Locks.approval("sfx", n) or Locks.waiver("sfx", n, "refs")) then
			table.insert(
				problems,
				`{n}: no owner-chosen reference for this new {what} - play the candidates to the owner (kit sfx find "<words>", kit sfx listen {n} --ref <file>); their pick: lune run kit approve sfx {n} "<their words naming the reference>" --by owner (synth-only by their choice: --waive refs)`
			)
		end
		if explicit(names) then -- a build of this piece: the verdict cap applies too
			local over = LaneLocks.cap("sfx", n, path)
			if over then
				table.insert(problems, over)
			end
		end
	end
	if only ~= "sets" then
		-- synth.py's "all": recipes only (not _events.json, verdicts or <name>.<x>.json copies)
		for _, p in
			pieces(dir, names, function(stem)
				return string.sub(stem, 1, 1) ~= "_" and not string.find(stem, ".", 1, true)
			end)
		do
			check(p[1], p[2], "sound")
		end
	end
	if only ~= "sounds" then
		-- sets.py's "all": every *.json in the sets folder
		for _, p in
			pieces(setsDir or (dir .. "/sets"), names, function()
				return true
			end)
		do
			check(p[1], p[2], "set")
		end
	end
	return problems
end

-- ------------------------------------------------------------ 3d
-- the "- quality: ..." line of a brief: hero / aaa / complex, "prop", "unanswered" (the template's "<answer>" is still
-- there: its options list names every tier, so it must not read as one), or nil when the line is missing
local function briefTier(text: string): string?
	for line in string.gmatch(text, "[^\n]+") do
		local q = string.match(line, "^%s*%-%s*quality:%s*(.*)$")
		if q then
			q = string.lower(q)
			if string.find(q, "<answer>", 1, true) then
				return "unanswered"
			end
			for _, tier in { "aaa", "hero", "complex" } do
				if string.find(q, tier, 1, true) then
					return tier
				end
			end
			return "prop"
		end
	end
	return nil
end

-- the tools behind the 3D stage approvals: each answers `--check` with one JSON line {exists, id, stale, problems, png}
local STAGE_TOOLS: { [string]: string } = { sheet = "kit/tools/sheet.py", blockout = "kit/tools/blockout.py" }
local STAGE_NAMES: { [string]: string } = { sheet = "model sheet", blockout = "blockout" }

-- the project folder a models folder belongs to ("" = the kit's home, "games/<Name>" a game)
local function projectRootOf(dir: string): string
	local root = string.gsub(string.gsub(dir, "\\", "/"), "/?assets/models/?$", "")
	return if root == "" then "." else root
end

-- a stage's artefact as it is now (the model sheet, the blockout) -> { ok (it exists, is current and has no
-- problem), id (the kept artefact's), why (when not ok), png }: what `kit approve --stage` records and the lock compares
function LaneLocks.stageState(
	name: string,
	step: string,
	dir: string?
): { ok: boolean, id: string?, why: string?, png: string? }
	local tool = STAGE_TOOLS[step]
	if not tool or not fs.isFile(tool) then
		return { ok = false, why = `no tool for the {step} stage` }
	end
	local models = dir or Config.path("models")
	local res = process.exec(Run.tool("python"), { tool, name, "--root", projectRootOf(models), "--check" })
	local line = string.match(string.gsub(res.stdout, "\r", ""), "([^\n]+)%s*$") or ""
	local ok, v = pcall(serde.decode, "json" :: any, line)
	if not ok or type(v) ~= "table" then
		return { ok = false, why = `the {step} check crashed (python {tool} {name} --check)` }
	end
	local png = if type(v.png) == "string" then `{models}/{string.match(v.png, "([^/]+)$") or v.png}` else nil
	if v.exists ~= true then
		return { ok = false, why = `no {STAGE_NAMES[step]} yet`, png = png }
	end
	if v.stale == true then
		return {
			ok = false,
			id = v.id,
			png = png,
			why = `the {STAGE_NAMES[step]} is older than what it shows (the brief, a picture, a trace or the shape changed)`,
		}
	end
	if type(v.problems) == "table" and #v.problems > 0 then
		return {
			ok = false,
			id = v.id,
			png = png,
			why = `the {STAGE_NAMES[step]} has {#v.problems} problem(s): {tostring(v.problems[1])}`,
		}
	end
	return { ok = true, id = v.id, png = png }
end

-- the VFX stages the owner approves one by one, each drawn and checked by its own tool (`--check` answers with the
-- same JSON line as the 3D ones): the STYLE SHEET - every beat's look, ours beside the scene's (kit/vfx/stylesheet.py;
-- the VFX studio-route plan, V1). Its id is a hash of the preset, the set and the chart's plan, so the lock can read
-- it again on any machine; the sheet itself (it holds the scene's frames) lives in build/ and is drawn per machine.
-- The TIMING ANIMATIC (kit/vfx/animatic.py; V2) is a stage of a scene SET - it is made before any effect exists:
-- `name` is then the set's name. Its id is a hash of its plan (every beat's time, length, hold, arrival, going,
-- rhythm, share, shape); what he looks at is a video and the beat pages ("shown").
local VFX_STAGE_TOOLS: { [string]: string } = { style = "kit/vfx/stylesheet.py", animatic = "kit/vfx/animatic.py" }
local VFX_STAGE_NAMES: { [string]: string } = { style = "style sheet", animatic = "timing animatic" }

-- what a VFX stage tool says it shows -> the names a page may show, and how many it may not:
--   files   the pair pictures "drawn" is the hash of, in order: plain file names only (a page shows exactly these);
--   shown   what "drawn" is the hash of when it is more than a folder's pictures (the animatic: its video, then its
--           beat pages): paths in the ACTIVE game's (else the project's) own build/vfx only - Config.build("vfx"),
--           where the stage tools write (card t6rx) - plainly spelled, in order;
--   hidden  how many names were left out. A stage with one is not one he can approve: the hash covers a file he
--           never saw (a review, 2026-11-12: a left-out name was dropped without a word)
function LaneLocks.showable(theirFiles: any, theirShown: any): ({ string }, { string }, number)
	local files: { string }, shown: { string }, hidden = {}, {}, 0
	for _, f in (if type(theirFiles) == "table" then theirFiles else {}) :: { any } do
		if type(f) == "string" and string.find(f, "^[%w_%-]+%.png$") then
			table.insert(files, f)
		else
			hidden += 1
		end
	end
	local prefix = Config.build("vfx") .. "/"
	for _, f in (if type(theirShown) == "table" then theirShown else {}) :: { any } do
		if
			type(f) == "string"
			and string.sub(f, 1, #prefix) == prefix
			and string.find(string.sub(f, #prefix + 1), "^[%w_%-/]+%.%w+$")
			and not string.find(f, "//", 1, true)
			and (string.sub(f, -4) == ".png" or string.sub(f, -4) == ".mp4")
		then
			table.insert(shown, f)
		else
			hidden += 1
		end
	end
	return files, shown, hidden
end

function LaneLocks.vfxStageState(
	name: string,
	step: string,
	effects: string?
): {
	ok: boolean,
	id: string?,
	why: string?,
	png: string?,
	drawn: string?,
	exists: boolean?,
	stale: boolean?,
	files: { string }?,
	shown: { string }?,
}
	local tool = VFX_STAGE_TOOLS[step]
	if not tool or not fs.isFile(tool) then
		return { ok = false, why = `no tool for the {step} stage` }
	end
	local args = { tool, name, "--check" }
	if effects then
		table.insert(args, "--effects")
		table.insert(args, effects)
	end
	local res = process.exec(Run.tool("python"), args)
	local line = string.match(string.gsub(res.stdout, "\r", ""), "([^\n]+)%s*$") or ""
	local ok, v = pcall(serde.decode, "json" :: any, line)
	if not ok or type(v) ~= "table" then
		return { ok = false, why = `the {step} check crashed (python {tool} {name} --check)` }
	end
	local what = VFX_STAGE_NAMES[step]
	local png = if type(v.png) == "string" then v.png else nil
	local id = if type(v.id) == "string" then v.id else nil
	-- drawn: the pictures themselves as they are on this machine (nil when no sheet is drawn here). His yes is for
	-- the pictures he saw: the same id drawn again from a new recording is another "drawn"
	local drawn = if type(v.drawn) == "string" then v.drawn else nil
	local files, shown, hidden = LaneLocks.showable(v.files, v.shown)
	if v.exists ~= true then
		local first = if type(v.problems) == "table" and v.problems[1] then `: {tostring(v.problems[1])}` else ""
		return { ok = false, id = id, why = `no {what} drawn on this machine yet{first}`, png = png, exists = false }
	end
	if v.stale == true then
		return {
			ok = false,
			id = id,
			png = png,
			drawn = drawn,
			exists = true,
			stale = true,
			files = files,
			shown = shown,
			why = `the {what} here is out of date - {if type(v.why) == "string" and v.why ~= ""
				then v.why
				else "it was drawn from another preset or recording than the ones here now"}`,
		}
	end
	if type(v.problems) == "table" and #v.problems > 0 then
		return {
			ok = false,
			id = id,
			png = png,
			drawn = drawn,
			exists = true,
			files = files,
			shown = shown,
			why = `the {what} has {#v.problems} problem(s): {tostring(v.problems[1])}`,
		}
	end
	if hidden > 0 then
		-- "drawn" is the hash of EVERY file the tool names: one the page cannot show is one he never saw
		return {
			ok = false,
			id = id,
			png = png,
			drawn = drawn,
			exists = true,
			files = files,
			shown = shown,
			why = `{hidden} file(s) of the {what} cannot be shown (a name outside {Config.build("vfx")}, or not a picture or a video): his yes would be for something he did not see`,
		}
	end
	return { ok = true, id = id, png = png, drawn = drawn, exists = true, files = files, shown = shown }
end

-- does the owner's stage record still hold for the artefact as it is NOW? Its id (what it was made from) and, for an
-- artefact that names its pictures ("drawn": a style sheet), the pictures he saw: the same id drawn again from a new
-- recording shows other pictures, and a record that names none cannot say which he saw. The ONE comparison: the 3D
-- build lock below, kit review's page (kit/lib/review.luau) and any lock on a VFX stage use it.
function LaneLocks.holds(rec: any, art: any): boolean
	if type(rec) ~= "table" or type(art) ~= "table" or rec.id ~= art.id then
		return false
	end
	return art.drawn == nil or rec.drawn == art.drawn
end

-- one stage approval of a new complex / hero / aaa piece -> the problem, or nil when the owner approved the artefact
-- as it is now (or waived the step)
local function stageProblem(name: string, t: string, step: string, dir: string): string?
	if Locks.waiver("3d", name, step) then
		return nil
	end
	local what = STAGE_NAMES[step]
	local make = `lune run kit {step} {name}`
	local yes = `lune run kit approve 3d {name} "<their words>" --by owner --stage {step}`
	local st = LaneLocks.stageState(name, step, dir)
	if not st.ok then
		return `{name}: a new {t} asset needs its {what} - {st.why}: {make}, LOOK at it, then show the owner; their yes: {yes}`
	end
	local rec = Locks.stage("3d", name, step)
	if not rec then
		return `{name}: the owner has not approved the {what} - show them {st.png or what}; their yes: {yes}`
	end
	if not LaneLocks.holds(rec, st) then
		return `{name}: the {what} changed since the owner approved it ({tostring(rec.date)}) - show them {st.png or what} again; their yes: {yes}`
	end
	return nil
end

-- (kit make's own two stops ask the same question of the piece it is making: kit make-gate)
LaneLocks.stageProblem = stageProblem

-- a build script kit make wrote says so on its first line (kit/blender/rbx.py _made_by_kit_make reads the same)
local function madeByKitMake(script: string): boolean
	if not fs.isFile(script) then
		return false
	end
	local first = string.match(fs.readFile(script), "^[^\n]*") or ""
	return string.find(first, "MADE BY kit make", 1, true) ~= nil
end

-- the STAGE approvals alone, for every command that BUILDS a piece (kit asset, kit watch, kit fit, kit optimize, kit
-- blockout): `mode` "geo" = a shape round (the model sheet's approval), "full" = a baked build (the blockout's too).
-- nil (kit verify) and "make" (kit make's own builds of the script it wrote, or its door before any script) ask
-- for none. `tier` nil = read from the piece's brief. -> the problem, or nil
function LaneLocks.stages(name: string, tier: string?, dir: string?, mode: string?): string?
	local models = dir or Config.path("models")
	local script = `{models}/build_{name}.py`
	if mode == "make" and (madeByKitMake(script) or not fs.isFile(script)) then
		return nil
	end
	if mode ~= "geo" and mode ~= "full" and mode ~= "make" then
		return nil
	end
	local t = tier
	if not t then
		local briefPath = `{models}/{name}.brief.md`
		t = if fs.isFile(briefPath) then briefTier(fs.readFile(briefPath)) or "prop" else nil
	end
	if not (t == "complex" or t == "hero" or t == "aaa") then
		return nil
	end
	if Locks.grandfathered("3d", script) or Locks.stagesExempt(script) then
		return nil
	end
	local sheet = stageProblem(name, t :: string, "sheet", models)
	if sheet then
		return sheet
	end
	if mode ~= "geo" and fs.isFile(STAGE_TOOLS.blockout) then
		return stageProblem(name, t :: string, "blockout", models)
	end
	return nil
end

-- one asset by name; `tier` (kit make --tier) wins over the brief's quality line; `noBrief` = the tier to assume when
-- there is no brief yet (kit make writes a prop's brief itself) - without it a missing brief is refused; `mode` =
-- "geo" for a shape round, "full" for a baked build (kit asset without --geo): only a BUILD is asked for the stage
-- approvals - any build for the model sheet's, a baked one for the blockout's too. kit verify (nil) never is: a
-- piece waiting for the owner's yes must not turn the shared gate red for every session. "make" = kit make's own
-- door, before it has gathered anything: no stage approval can exist yet. The brief and study steps are asked always.
function LaneLocks.asset(name: string, tier: string?, root: string?, noBrief: string?, mode: string?): string?
	local dir = root or Config.path("models")
	local script = `{dir}/build_{name}.py`
	if Locks.grandfathered("3d", script) then
		return nil
	end
	local problems = {}
	local stageTier: string? = nil -- (the tier the stage approvals are asked for: read even when the brief step is waived)
	do
		local briefPath = `{dir}/{name}.brief.md`
		local brief = if fs.isFile(briefPath) then fs.readFile(briefPath) else nil
		stageTier = tier or (brief and briefTier(brief)) or (if brief then "prop" else noBrief)
	end
	if not Locks.waiver("3d", name, "brief") then
		local briefPath = `{dir}/{name}.brief.md`
		local brief = if fs.isFile(briefPath) then fs.readFile(briefPath) else nil
		local t = tier or (brief and briefTier(brief)) or (if brief then "prop" else noBrief)
		if not t then
			table.insert(
				problems,
				`{name}: no brief - a new asset starts from its brief ({briefPath}: what, quality, hero features; lune run kit plan {name} shows the brief stage)`
			)
		elseif t == "unanswered" then
			table.insert(
				problems,
				`{name}: the brief's quality line is still unanswered - ask the owner (prop 55 / hero 75 / aaa 88) and write it in {briefPath} (lune run kit plan {name} shows the brief stage)`
			)
		elseif t ~= "prop" and not Locks.approval("3d", name) then
			local write = if brief
				then ""
				else ` - write it first (what, quality, hero features, the parts plan; lune run kit plan {name} shows the brief stage)`
			table.insert(
				problems,
				`{name}: a new {t} asset needs the owner's approval of its brief{write} - show them {briefPath} (and its reference sheet); their yes: lune run kit approve 3d {name} "<their words>" --by owner`
			)
		end
	end
	-- the reference study (kit study): every reference read, our version decided, the lessons it applies cited. A kit
	-- make prop is exempt (its gather and tournament measure the references); the owner may waive it (--waive study)
	if not Locks.waiver("3d", name, "study") and not Locks.studyExempt(script) then
		local briefPath = `{dir}/{name}.brief.md`
		local brief = if fs.isFile(briefPath) then fs.readFile(briefPath) else ""
		local studyPath = `{dir}/{name}.study.md`
		-- (a kit make brief is exempt: kit make measures its references in its own gather and tournament)
		local kitMake = string.find(brief, "^%s*<!%-%- written by kit make") ~= nil
		if not kitMake and not fs.isFile(studyPath) then
			table.insert(
				problems,
				`{name}: no reference study ({studyPath}) - read every gathered reference and decide our own version before the shape: lune run kit study {name} --new`
			)
		elseif not kitMake then
			local projectRoot = string.gsub(string.gsub(dir, "\\", "/"), "/?assets/models/?$", "")
			local res = process.exec(
				Run.tool("python"),
				{ "kit/tools/study.py", name, "--root", if projectRoot == "" then "." else projectRoot }
			)
			if not res.ok then
				local line = string.match(res.stdout, "([^\n]+)%s*$") or ""
				local ok, v = pcall(serde.decode, "json" :: any, line)
				local why = if ok
						and type(v) == "table"
						and type(v.summary) == "string"
					then v.summary
					else "the study check crashed"
				table.insert(problems, `{name}: {why} (lune run kit study {name})`)
			end
		end
	end
	-- the STAGE approvals (the owner, 2026-11-11: "A concept sheet we really need ... block[out] approval"): a complex /
	-- hero / aaa piece made after them builds only from a model sheet he approved (its views, a callout per hero
	-- feature, its colours: kit sheet), and is baked only after he approved its blockout (kit blockout: seconds, no
	-- bake). Each approval holds for the artefact's id: one that changed needs his word again.
	local stages = LaneLocks.stages(name, stageTier, dir, mode)
	if stages then
		table.insert(problems, stages)
	end
	if not root then
		local over = LaneLocks.cap("3d", name, script)
		if over then
			table.insert(problems, over)
		end
	end
	return if #problems > 0 then table.concat(problems, "; ") else nil
end

-- every build script in a models folder (the cap is a verify-wide check, not per asset here)
function LaneLocks.assets(root: string?): { string }
	local problems = {}
	local dir = root or Config.path("models")
	if fs.isDir(dir) then
		for _, file in fs.readDir(dir) do
			local n = string.match(file, "^build_(.+)%.py$")
			if n then
				local p = LaneLocks.asset(n, nil, dir)
				if p then
					table.insert(problems, p)
				end
			end
		end
	end
	return problems
end

-- ------------------------------------------------------------ world
local STILL = { png = true, jpg = true, jpeg = true, webp = true }

-- blueprints (<worlds>/<Name>.json: every *.json, as the compiler takes them); `names` limits the check (nil = all)
-- worlds that existed before the rig rule (a world made after it names its rig sheet) and are not grandfathered for the
-- other locks: exempt from it by path (lower case). The kit ships none; a project grandfathers its own (Locks.grandfathered)
local RIG_RULE_BEFORE: { [string]: boolean } = {}

-- THE ROUTE STAGES (LIMITATIONS_FIXES_V3.md stage A.2-A.3; the studio route's W1 and W2): a NEW world is dressed in
-- meshes (a skin, a facade, a mesh step, a forest of meshes, far proxies) only after the owner walked its GREYBOX and
-- said yes (kit world greybox <Name>; kit approve world <Name> "<his words>" --by owner --stage greybox), and a new
-- town or street of houses is built out only after ONE 40 x 40 CORNER of it had his 7 or more (kit world corner <Name>
-- --at <station>; --stage corner). Each yes is for the artefact as it was (kit/world/stages.py: its id); changed, it
-- is asked again. The worlds that stood before this rule were exempt by path in the author's own project; the kit
-- ships none, so every world is held to it. The owner may waive a stage for one world (--waive greybox / corner).
local STAGES_RULE_BEFORE: { [string]: boolean } = {}
LaneLocks.STAGES_RULE_BEFORE = STAGES_RULE_BEFORE

-- does a blueprint dress anything in meshes (a skin, a facade, a "mesh" / "meshes" / "hlod" anywhere in its steps)
function LaneLocks.dressedInMeshes(bp: any): boolean
	local function walk(v: any, depth: number): boolean
		if type(v) ~= "table" or depth > 12 then
			return false
		end
		for k, x in v do
			-- ("skins": a town's house types - kit/lib/worldtown.luau puts one on every house; a fresh review found a town
			-- dressed that way not held)
			if
				(k == "skin" or k == "skins" or k == "facade" or k == "mesh" or k == "hlod")
				and type(x) == "string"
				and x ~= ""
			then
				return true
			end
			if (k == "meshes" or k == "skins") and type(x) == "table" and next(x) ~= nil then
				return true
			end
			if walk(x, depth + 1) then
				return true
			end
		end
		return false
	end
	return type(bp) == "table" and walk(bp.build, 0)
end

-- is a blueprint a town or a street of houses (a "town" step, or LAYOUT_TYPED houses typed one by one)
function LaneLocks.streetsOfHouses(bp: any): boolean
	if type(bp) ~= "table" or type(bp.build) ~= "table" then
		return false
	end
	for _, st in bp.build do
		if type(st) == "table" and st.town ~= nil then
			return true
		end
	end
	local typed = LaneLocks.typedHouses(bp)
	return typed >= LaneLocks.LAYOUT_TYPED
end

-- the project a worlds folder belongs to ("." = the kit's home, "games/<Name>" a game): its compiled worlds are in
-- <project>/build/worlds (a game's paths, its build folder too, live inside its own folder: Config.load)
function LaneLocks.worldsRoot(dir: string?): string
	local root = string.gsub(string.gsub(dir or Config.path("worlds"), "\\", "/"), "/?assets/worlds/?$", "")
	return if root == "" then "." else root
end

-- a world stage's artefact as it is now (kit/world/stages.py --check, in the world's own project: `root`, default
-- the active one) -> { ok, id, why, png }
function LaneLocks.worldStageState(name: string, step: string, root: string?): any
	local res = process.exec(Run.tool("python"), {
		"kit/world/stages.py",
		name,
		"--stage",
		step,
		"--check",
		"--root",
		root or LaneLocks.worldsRoot(),
	})
	local line = string.match(string.gsub(res.stdout, "\r", ""), "([^\n]+)%s*$") or ""
	local ok, v = pcall(serde.decode, "json" :: any, line)
	if not ok or type(v) ~= "table" then
		return {
			ok = false,
			why = `the {step} check crashed (python kit/world/stages.py {name} --stage {step} --check)`,
		}
	end
	local what = if step == "greybox" then "walked greybox" else "40 x 40 corner"
	if v.exists ~= true then
		return { ok = false, id = v.id, why = `no {what} yet`, png = v.png }
	end
	if v.stale == true then
		return { ok = false, id = v.id, png = v.png, why = `the {what} is older than the blueprint it shows` }
	end
	if type(v.problems) == "table" and #v.problems > 0 then
		return {
			ok = false,
			id = v.id,
			png = v.png,
			why = `the {what} has {#v.problems} problem(s): {tostring(v.problems[1])}`,
		}
	end
	return { ok = true, id = v.id, png = v.png }
end

-- the route stages a world is held to -> its problems (empty = passes)
function LaneLocks.worldStages(path: string, n: string, bp: any, root: string): { string }
	local out = {}
	if STAGES_RULE_BEFORE[string.lower(Locks.normal(path))] then
		return out
	end
	local asks: { { string } } = {}
	if LaneLocks.dressedInMeshes(bp) then
		table.insert(asks, {
			"greybox",
			"a new world is dressed in meshes only after its walked greybox",
			`lune run kit world greybox {n}`,
		})
	end
	if LaneLocks.streetsOfHouses(bp) then
		table.insert(asks, {
			"corner",
			"a new town is built out only after ONE 40 x 40 corner of it had the owner's 7 or more",
			`lune run kit world corner {n} --at <station>`,
		})
	end
	for _, a in asks do
		local step = a[1]
		if not Locks.waiver("world", n, step) then
			local yes = `lune run kit approve world {n} "<his words>" --by owner --stage {step}`
			local st = LaneLocks.worldStageState(n, step, root)
			if not st.ok then
				table.insert(out, `{n}: {a[2]} - {st.why}: {a[3]}, LOOK at it, show the owner; his yes: {yes}`)
			else
				local rec = Locks.stage("world", n, step)
				if not rec then
					table.insert(
						out,
						`{n}: {a[2]} - the owner has not approved it: show him {st.png or step}; his yes: {yes}`
					)
				elseif not LaneLocks.holds(rec, st) then
					table.insert(
						out,
						`{n}: {a[2]} - it changed since the owner approved it ({tostring(rec.date)}): show him {st.png or step} again; his yes: {yes}`
					)
				end
			end
		end
	end
	return out
end

-- the LAYOUT rule (2026-11-13; the owner's method list: "Procedural city generation", "Graph-based generation",
-- "Landmark-based layout", "Sightline-based layout", "Loop-based level layouts", and his order that every method be
-- "enforced in the terms of being used"): a place of a dozen houses is a town, and a town is laid out by its PLAN -
-- one "town" step (kit/lib/worldtown.luau: streets as a graph round a closed square, terraced lots, the landmark on
-- the gate's line of sight) - never typed house by house, and never a "city" step (a regular grid of box blocks: the
-- layout the plan replaces). Counted as typed houses: the blueprint's own "building" steps and its "mesh" steps
-- that place a whole-house mesh (the mesh registry's kind "gothic_house") - a town's own houses are not typed.
-- The owner may waive it for one world (--waive layout). GothicCourtyard, his kept court of 9 typed houses, is under
-- the count. NOT counted (a known way round, board card): "room" steps - until rooms have a generator of their
-- own, a typed room is also how an interior is made.
LaneLocks.LAYOUT_TYPED = 12

-- the names of the whole-house meshes in a mesh registry (build/worldmeshes/meshes.json), or of this project's
function LaneLocks.houseMeshes(registry: any?): { [string]: boolean }
	local reg = registry
	if reg == nil then
		local ok, read = pcall(function()
			return serde.decode("json" :: any, fs.readFile(Config.build("worldmeshes") .. "/meshes.json"))
		end)
		reg = if ok then read else nil
	end
	local houses = {}
	if type(reg) == "table" then
		for name, entry in reg do
			if type(entry) == "table" and entry.kind == "gothic_house" then
				houses[name] = true
			end
		end
	end
	return houses
end

-- (how many houses the blueprint types one by one, how many "city" steps it has)
function LaneLocks.typedHouses(bp: any, registry: any?): (number, number)
	local n, cities = 0, 0
	if type(bp) == "table" and type(bp.build) == "table" then
		local houses: { [string]: boolean }? = nil
		for _, step in Prefab.flat(bp) do
			if type(step) ~= "table" then
				continue
			end
			if type(step.building) == "table" then
				n += 1
			end
			if type(step.mesh) == "table" and type(step.mesh.mesh) == "string" then
				houses = houses or LaneLocks.houseMeshes(registry)
				if (houses :: any)[step.mesh.mesh] then
					n += 1
				end
			end
			if step.city ~= nil then
				cities += 1
			end
		end
	end
	return n, cities
end

-- the BEND rule (2026-11-13; the owner's method list: "Spline-based roads", "Spline-based paths", "Spline-based
-- fences and walls"): a line of typed points - a road (path), a row of posts or lamps, a palisade, a wall along
-- points - that turns more than BEND_KINK degrees at a typed point says how it bends: "curve": true (the smooth line
-- through its points, kit/lib/worldcurve.luau) or "curve": false (a hard corner, meant: a street corner, a fence's
-- post). Until a blueprint says, the build does not guess. No waiver: the word is the blueprint's own.
LaneLocks.BEND_KINK = 20
local BENDS = { "path", "row", "palisade", "wall" }

-- the steps of a blueprint whose line turns a hard corner and says nothing: { "<kind> <name> (<degrees> degrees)" }
function LaneLocks.unsaidBends(bp: any): { string }
	local out = {}
	if type(bp) ~= "table" or type(bp.build) ~= "table" then
		return out
	end
	for i, step in Prefab.flat(bp) do
		if type(step) ~= "table" then
			continue
		end
		for _, kind in BENDS do
			local spec = step[kind]
			if type(spec) ~= "table" or type(spec.points) ~= "table" or spec.curve ~= nil then
				continue
			end
			local pts = {}
			for _, pt in spec.points do
				if type(pt) == "table" and type(pt[1]) == "number" and type(pt[2]) == "number" then
					table.insert(pts, { pt[1], pt[2] })
				end
			end
			local sharp = require("./worldcurve").sharpest(pts)
			if sharp > LaneLocks.BEND_KINK then
				local name = if type(spec.name) == "string" then spec.name else `build[{i}]`
				table.insert(out, `{kind} "{name}" ({math.floor(sharp + 0.5)} degrees)`)
			end
		end
	end
	return out
end

-- the STREAMING rule (2026-11-14; the owner's method list: "World streaming", "World partitioning", "Hierarchical
-- LOD", "Distance culling"): Roblox streams a place in round each player to StreamingTargetRadius, 1,024 studs
-- unless a place says otherwise. A world whose PLAYED part - everything but its far scenery - reaches farther than
-- that across says how it is prepared for streaming: "streaming": { "cell": 256 } in its blueprint. What that does
-- (kit/lib/world.luau, "STREAMING + LOD"): every step becomes a Model with the engine's far stand-in
-- (LevelOfDetail = StreamingMesh), a step whose parts spread wider than a cell is cut into one Model a cell, and
-- the far scenery stays in as one Model that never streams out. The land itself is Roblox terrain: the engine
-- streams it by itself once StreamingEnabled is on in the game's project. That switch is the game's, not the
-- world's - so a world that says how it streams is held to it: LaneLocks.streamSwitch reads the game's project file
-- (Rojo: Workspace "$properties": { "StreamingEnabled": true }). With the switch off Roblox sends every player the
-- whole place, the cells never stream and the far stand-ins never show: the blueprint's "streaming" does nothing.
-- The reach is MEASURED on what the compiler builds (its parts' own boxes and the land's, far scenery left out):
-- the first version read the blueprint's numbers and missed every generator that has no centre and size (a grid
-- 1,564 studs across read as 0), and counted a far ring of mountains that never streams - a fresh reader, 2026-11-14.
LaneLocks.STREAM_REACH = 1024

-- is streaming turned on in a game's Rojo project file? -> "on" | "off" (the file is there and does not turn it
-- on) | "missing" (no such file) | "unread" (not JSON, or no tree)
function LaneLocks.streamSwitch(project: string): string
	if not fs.isFile(project) then
		return "missing"
	end
	local ok, doc = pcall(function()
		return serde.decode("json" :: any, fs.readFile(project))
	end)
	if not ok or type(doc) ~= "table" or type(doc.tree) ~= "table" then
		return "unread"
	end
	local ws = doc.tree.Workspace
	local props = if type(ws) == "table" then ws["$properties"] else nil
	local v = if type(props) == "table" then props.StreamingEnabled else nil
	-- (Rojo's two ways to write a boolean property: true, or the explicit { "Bool": true })
	if type(v) == "table" then
		v = v.Bool
	end
	return if v == true then "on" else "off"
end

-- what a game's Rojo project says of streaming (nil = the file cannot be read): { min = StreamingMinRadius
-- (Roblox's own 64 when it says none), target = StreamingTargetRadius (1,024), pause = StreamingIntegrityMode is
-- PauseOutsideLoadedArea }. Rojo writes a number plain or as { "Int32": n } / { "Float32": n }, an enum as its
-- name or { "Enum": n }
function LaneLocks.streamProps(project: string): any
	if not fs.isFile(project) then
		return nil
	end
	local ok, doc = pcall(function()
		return serde.decode("json" :: any, fs.readFile(project))
	end)
	if not ok or type(doc) ~= "table" or type(doc.tree) ~= "table" then
		return nil
	end
	local ws = doc.tree.Workspace
	local props = if type(ws) == "table" and type(ws["$properties"]) == "table" then ws["$properties"] else {}
	local function num(v: any, default: number): number
		if type(v) == "table" then
			v = v.Int32 or v.Float32 or v.Int64 or v.Float64
		end
		return if type(v) == "number" and v > 0 then v else default
	end
	local mode = props.StreamingIntegrityMode
	if type(mode) == "table" then
		mode = if mode.Enum == 3 then "PauseOutsideLoadedArea" else "other"
	end
	return {
		min = num(props.StreamingMinRadius, Stream.MIN_RADIUS),
		target = num(props.StreamingTargetRadius, 1024),
		pause = mode == "PauseOutsideLoadedArea",
	}
end

function LaneLocks.streamRadius(project: string): number?
	local props = LaneLocks.streamProps(project)
	return if props then props.min else nil
end

-- the landmarks of a world that streams which do not say whether they stream out: a step typed "landmark": true
-- is steered by from afar - "stream": "always" keeps it loaded for every player, "stream": "area" lets it come and
-- go with its place (meant)
function LaneLocks.unsaidLandmarks(bp: any): { string }
	local out = {}
	if type(bp) ~= "table" or type(bp.build) ~= "table" then
		return out
	end
	local function said(word: any): boolean
		return word ~= nil and (Stream.mode(word)) ~= nil
	end
	for i, step in Prefab.flat(bp) do
		if type(step) == "table" then
			local kind, spec = next(step)
			if type(spec) ~= "table" then
				continue
			end
			if kind == "town" then
				-- a town's landmark house (it always has one) says it in "landmark": { "stream": ... }
				local lm = if type(spec.landmark) == "table" then spec.landmark else {}
				if not said(lm.stream) then
					table.insert(
						out,
						(if type(spec.name) == "string" then spec.name else `build[{i}].town`) .. "'s landmark"
					)
				end
				continue
			end
			-- typed a landmark, or one by the compiler's own rule (kit/lib/world.luau: a tree 150 studs or taller,
			-- a tower 60, a building of three storeys) unless it says "landmark": false; a peak is far scenery
			-- and never streams out anyway
			local auto = spec.landmark ~= false
				and (
					(kind == "tree" and (tonumber(spec.height) or 0) >= 150)
					or (kind == "tower" and (tonumber(spec.height) or 0) >= 60)
					or (kind == "building" and (tonumber(spec.floors) or 0) >= 3)
				)
			if (spec.landmark == true or auto) and not said(spec.stream) then
				table.insert(out, if type(spec.name) == "string" then spec.name else `build[{i}].{tostring(kind)}`)
			end
		end
	end
	return out
end

-- the project file a world's streaming switch is read from, and whether a file that is not there is a fault:
--   * the caller names it (kit verify: each root's own project file) - a missing file is a fault;
--   * no name and no folder (the build: the active game's worlds) - the game's project file from kit.config.json
--     ("rojo", default.project.json) - a missing file is a fault;
--   * a folder only (a fixture folder in a test) - its own default.project.json, and none at all asks nothing.
function LaneLocks.projectFor(root: string?, project: string?): (string, boolean)
	if project then
		return project, true
	elseif root then
		return `{root}/default.project.json`, false
	end
	return Config.load().rojo, true
end

-- how far a blueprint's PLAYED world reaches across, in studs (the larger of its extent along x and along z);
-- 0 for a blueprint that does not compile (its own errors stop the build)
function LaneLocks.reach(bp: any): number
	if type(bp) ~= "table" or type(bp.name) ~= "string" or type(bp.build) ~= "table" then
		return 0
	end
	local World = require("./world")
	local ok, _, parts = pcall(World.compile, bp)
	if not ok or type(parts) ~= "table" then
		return 0
	end
	local x0, x1, z0, z1 = math.huge, -math.huge, math.huge, -math.huge
	for _, part in parts do
		if not part.backdrop then
			local r, sz = part.rot, part.size
			local ex = (math.abs(r[1][1]) * sz[1] + math.abs(r[1][2]) * sz[2] + math.abs(r[1][3]) * sz[3]) / 2
			local ez = (math.abs(r[3][1]) * sz[1] + math.abs(r[3][2]) * sz[2] + math.abs(r[3][3]) * sz[3]) / 2
			x0, x1 = math.min(x0, part.pos[1] - ex), math.max(x1, part.pos[1] + ex)
			z0, z1 = math.min(z0, part.pos[3] - ez), math.max(z1, part.pos[3] + ez)
		end
	end
	local okEnv, env = pcall(require("./environment").compile, bp)
	if okEnv and type(env) == "table" and type(env.terrain) == "table" then
		for _, op in env.terrain do
			-- (every piece of land with a place and a size: a ground's size is [w, d], a block's [x, y, z])
			local g = op.spec
			if type(g) == "table" and not g.backdrop and type(g.center) == "table" and type(g.size) == "table" then
				local w, d = g.size[1], if #g.size >= 3 then g.size[3] else g.size[2]
				if type(w) == "number" and type(d) == "number" and type(g.center[1]) == "number" then
					local cz = if #g.center >= 3 then g.center[3] else g.center[2]
					x0, x1 = math.min(x0, g.center[1] - w / 2), math.max(x1, g.center[1] + w / 2)
					z0, z1 = math.min(z0, cz - d / 2), math.max(z1, cz + d / 2)
				end
			end
		end
	end
	-- (a heightmap whose file the compile could not open from here - a game's own path - is still land of the size
	-- the blueprint types for it)
	if type(bp.terrain) == "table" then
		for _, entry in bp.terrain do
			local hm = if type(entry) == "table" then entry.heightmap else nil
			if type(hm) == "table" and not hm.backdrop and type(hm.center) == "table" and type(hm.size) == "table" then
				local cx, cz, w, d = hm.center[1], hm.center[3], hm.size[1], hm.size[2]
				if type(cx) == "number" and type(cz) == "number" and type(w) == "number" and type(d) == "number" then
					x0, x1 = math.min(x0, cx - w / 2), math.max(x1, cx + w / 2)
					z0, z1 = math.min(z0, cz - d / 2), math.max(z1, cz + d / 2)
				end
			end
		end
	end
	if x0 > x1 then
		return 0
	end
	return math.max(x1 - x0, z1 - z0)
end

-- does a blueprint's "streaming" block do anything? (an empty table, a cell of a hundred thousand studs with the
-- far stand-ins turned off, a word: none of these prepares a world)
function LaneLocks.streams(bp: any): boolean
	local st = if type(bp) == "table" then bp.streaming else nil
	if type(st) ~= "table" then
		return false
	end
	local cell = st.cell
	return type(cell) == "number" and cell >= 64 and cell <= 512 and st.lod ~= false
end

-- the ROOMS rule (2026-11-14; the owner's method list: "Procedural floor plan generation", "Room-and-corridor
-- generation"): a house big enough to hold two rooms says whether its floors are cut into rooms - "rooms": true
-- (kit/lib/worldrooms.luau: partitions with a doorway each, every room reached from every other, the stair hall kept
-- clear) or "rooms": false (one open room a floor, meant: a hall, a barn, a shell nobody enters). A typed building
-- whose longer side is ROOMS_FROM studs or more, and a town (its houses take "house": { "rooms": ... }).
LaneLocks.ROOMS_FROM = 20
-- the worlds that stood before this rule and are in no grandfathered list: left as they are (GothicCourtyard is the
-- owner's kept piece of 2026-11-11, its nine houses one room a floor)
local ROOMS_RULE_BEFORE = {
	["assets/worlds/gothiccourtyard.json"] = true,
}

function LaneLocks.unsaidRooms(bp: any): { string }
	local out = {}
	if type(bp) ~= "table" or type(bp.build) ~= "table" then
		return out
	end
	for i, step in Prefab.flat(bp) do
		if type(step) ~= "table" then
			continue
		end
		local b = step.building
		-- (said = true, false or a table of options; "no", 0 and null say nothing)
		local function said(v: any): boolean
			return type(v) == "boolean" or type(v) == "table"
		end
		if type(b) == "table" and not said(b.rooms) and type(b.size) == "table" then
			local w, d = b.size[1], b.size[2]
			if type(w) == "number" and type(d) == "number" and math.max(w, d) >= LaneLocks.ROOMS_FROM then
				table.insert(out, `building "{if type(b.name) == "string" then b.name else `build[{i}]`}"`)
			end
		end
		local t = step.town
		if type(t) == "table" and not (type(t.house) == "table" and said(t.house.rooms)) then
			table.insert(out, `town "{if type(t.name) == "string" then t.name else `build[{i}]`}" (its "house")`)
		end
	end
	return out
end

-- ... a TOWN says whether its square holds a market: "market": true (stalls set out by rule, the gate's view and
-- the streets' mouths kept clear: kit/lib/worldtown.luau Town.stallSpots) or "market": false (an empty square, meant)
function LaneLocks.unsaidMarkets(bp: any): { string }
	local out = {}
	if type(bp) ~= "table" or type(bp.build) ~= "table" then
		return out
	end
	for i, step in Prefab.flat(bp) do
		if type(step) == "table" and type(step.town) == "table" and type(step.town.market) ~= "boolean" then
			table.insert(out, if type(step.town.name) == "string" then step.town.name else `build[{i}]`)
		end
	end
	return out
end

-- ... a TOWN says how its land lies: "slope": { "rise", "toward" } (a hillside: tilted ground cut round the houses,
-- each house level at its own door - kit/lib/worldtown.luau, A TOWN ON A SLOPE) or "slope": false (level ground, meant)
function LaneLocks.unsaidSlopes(bp: any): { string }
	local out = {}
	if type(bp) ~= "table" or type(bp.build) ~= "table" then
		return out
	end
	for i, step in Prefab.flat(bp) do
		if type(step) == "table" and type(step.town) == "table" then
			local v = step.town.slope
			if v ~= false and type(v) ~= "table" then
				table.insert(out, if type(step.town.name) == "string" then step.town.name else `build[{i}]`)
			end
		end
	end
	return out
end

-- ... a town with house meshes ("skins") says HOW its houses are made: "facade": true (put together from modules by a
-- grammar, about 8 meshes a town: kit/lib/worldfacade.luau) or "facade": false (one whole mesh a house type, meant)
function LaneLocks.unsaidFacades(bp: any): { string }
	local out = {}
	if type(bp) ~= "table" or type(bp.build) ~= "table" then
		return out
	end
	for i, step in Prefab.flat(bp) do
		if type(step) == "table" and type(step.town) == "table" then
			local t = step.town
			if type(t.skins) == "string" and t.skins ~= "" and type(t.facade) ~= "boolean" then
				table.insert(out, if type(t.name) == "string" then t.name else `build[{i}]`)
			end
		end
	end
	return out
end

-- ... a world with a WEATHER says whether it ever changes: "weather": { "cycle": [...] } (src/kit/WeatherRules.luau:
-- the weathers in turn, the same for every player) or "weather": false (the one "ambient" for ever, meant). True for
-- a world that has an "ambient" and says neither:
function LaneLocks.unsaidWeather(bp: any): boolean
	return type(bp) == "table" and bp.ambient ~= nil and bp.weather == nil
end

-- ... the same asked of the world as written and of every one of its seasons (a season may bring its own
-- "ambient": kit/lib/worldseason.luau). The first that says neither: { where = "as written" | "in its <season>",
-- ambient }, or nil
function LaneLocks.unsaidWeatherIn(bp: any): any
	if type(bp) ~= "table" then
		return nil
	end
	if LaneLocks.unsaidWeather(bp) then
		return { where = "as written", ambient = tostring(bp.ambient) }
	end
	for _, name in Season.names(bp) do
		local seen = Season.apply(bp, name)
		if seen ~= bp and LaneLocks.unsaidWeather(seen) then
			return { where = `in its {name}`, ambient = tostring(seen.ambient) }
		end
	end
	return nil
end

-- ... a large SCATTER or FOREST says where its pieces go: "density": { "gap", "noise" | "spots" | "away" | "map" } (how full
-- each place is: kit/lib/worldscatter.luau) or "density": false (an even count over the whole area, meant). The
-- names of the scatter steps that say neither, when TOGETHER they come to LaneLocks.SCATTER_ASKED pieces or more
-- (one scatter of 60 cut into two of 30 is asked the same):
LaneLocks.SCATTER_ASKED = 40
function LaneLocks.unsaidDensities(bp: any): { string }
	local out = {}
	if type(bp) ~= "table" or type(bp.build) ~= "table" then
		return out
	end
	local together = 0
	for i, step in Prefab.flat(bp) do
		-- (a forest is a scatter of trees: its count is 10 when it says none)
		local s = if type(step) == "table" then step.scatter or step.forest else nil
		-- (a grown forest - "ecosystem" - has no density to say: where its trees stand comes out of its years)
		if type(s) == "table" and s.density == nil and type(s.ecosystem) ~= "table" then
			-- (a count below 0 places nothing and takes nothing off the others)
			together += if type(s.count) == "number" then math.max(0, s.count) elseif step.forest then 10 else 0
			table.insert(out, if type(s.name) == "string" then s.name else `build[{i}]`)
		end
	end
	return if together >= LaneLocks.SCATTER_ASKED then out else {}
end

-- ... a MIXED FOREST says how its kinds came to stand where they do: "ecosystem": { "years", "species": [...] } (the
-- trees grow, seed, shade each other out and die: kit/lib/worldecosystem.luau) or "ecosystem": false (its kinds mixed
-- by chance, meant). The names of the "forest" steps of two or more kinds of tree ("styles" or "meshes") that say
-- neither, when TOGETHER they come to LaneLocks.FOREST_ASKED trees or more (a forest by "density" counts as that
-- many: its count is not written):
LaneLocks.FOREST_ASKED = 40
function LaneLocks.unsaidEcosystems(bp: any): { string }
	local out = {}
	if type(bp) ~= "table" or type(bp.build) ~= "table" then
		return out
	end
	-- the forests that say nothing, each with the kinds of tree it is built of (its meshes when it has them: a
	-- forest of meshes is built of those, whatever its styles say; the same name twice is one kind) and its box
	local woods: { any } = {}
	for i, step in Prefab.flat(bp) do
		local s = if type(step) == "table" then step.forest else nil
		if type(s) == "table" and s.ecosystem == nil then
			local kinds: { [string]: boolean } = {}
			local list = if type(s.meshes) == "table"
				then s.meshes
				elseif type(s.styles) == "table" then s.styles
				else { "oak" }
			local n = 0
			for _, k in list do
				if type(k) == "string" and not kinds[k] then
					kinds[k] = true
					n += 1
				end
			end
			local c, a = s.center, s.area
			local boxed = type(c) == "table"
				and type(a) == "table"
				and type(c[1]) == "number"
				and type(c[3]) == "number"
				and type(a[1]) == "number"
				and type(a[2]) == "number"
			table.insert(woods, {
				name = if type(s.name) == "string" then s.name else `build[{i}]`,
				kinds = kinds,
				n = n,
				trees = if type(s.density) == "table"
					then LaneLocks.FOREST_ASKED
					elseif type(s.count) == "number" then math.max(0, s.count)
					else 10,
				box = if boxed then { c[1] - a[1] / 2, c[3] - a[2] / 2, c[1] + a[1] / 2, c[3] + a[2] / 2 } else nil,
				mixed = n >= 2,
			})
		end
	end
	-- two forests of different kinds laid over each other are one mixed wood, made by hand
	for a = 1, #woods do
		for b = a + 1, #woods do
			local p, q = woods[a], woods[b]
			if
				p.box
				and q.box
				and p.box[1] < q.box[3]
				and q.box[1] < p.box[3]
				and p.box[2] < q.box[4]
				and q.box[2] < p.box[4]
			then
				local differ = false
				for k in p.kinds do
					differ = differ or not q.kinds[k]
				end
				for k in q.kinds do
					differ = differ or not p.kinds[k]
				end
				if differ then
					p.mixed, q.mixed = true, true
				end
			end
		end
	end
	local together = 0
	for _, w in woods do
		if w.mixed then
			together += w.trees
			table.insert(out, w.name)
		end
	end
	return if together >= LaneLocks.FOREST_ASKED then out else {}
end

-- ... a long ROAD ACROSS THE LAND says how its way was found: "route": { "from", "to", "grade" } (it finds its own
-- way over the ground, within a grade: kit/lib/worldroute.luau) or "route": false (its points typed by hand, meant).
-- The names of the "path" steps with "ground": true that say neither, when their typed points TOGETHER run
-- LaneLocks.ROAD_ASKED studs or more (one road cut into two short ones is asked the same):
LaneLocks.ROAD_ASKED = 200
function LaneLocks.unsaidRoutes(bp: any): { string }
	local out = {}
	local together = 0
	if type(bp) ~= "table" or type(bp.build) ~= "table" then
		return out
	end
	for i, step in Prefab.flat(bp) do
		local s = if type(step) == "table" then step.path else nil
		if type(s) == "table" and s.ground == true and s.route == nil and type(s.points) == "table" then
			local length = 0
			for k = 2, #s.points do
				local a, b = s.points[k - 1], s.points[k]
				if
					type(a) == "table"
					and type(b) == "table"
					and type(a[1]) == "number"
					and type(a[2]) == "number"
					and type(b[1]) == "number"
					and type(b[2]) == "number"
				then
					length += math.sqrt((b[1] - a[1]) ^ 2 + (b[2] - a[2]) ^ 2)
				end
			end
			together += length
			table.insert(out, if type(s.name) == "string" then s.name else `build[{i}]`)
		end
	end
	return if together >= LaneLocks.ROAD_ASKED then out else {}
end

-- ... a PAINTED LAND says what climate painted it: its terrain was made with one (kit world terrain --climate: wet
-- and dry sides of a ridge, a snowline that sits lower on a north face) or its heightmap op says "climate": false
-- (painted by slope, water and height alone, meant). The sources of the painted heightmaps that say neither:
function LaneLocks.unsaidClimates(bp: any): { string }
	local out = {}
	if type(bp) ~= "table" or type(bp.terrain) ~= "table" then
		return out
	end
	local okEnv, env = pcall(require("./environment").compile, bp)
	if not okEnv or type(env) ~= "table" or type(env.terrain) ~= "table" then
		return out
	end
	for _, op in env.terrain do
		local g = op.spec
		if
			type(g) == "table"
			and not g.backdrop
			and type(g.samples) == "table"
			and g.samples.splat ~= nil
			and g.climate == nil
		then
			table.insert(out, tostring(g.source))
		end
	end
	return out
end

-- ... ROOMS typed one by one: a place of LaneLocks.ROOMS_TYPED "room" steps or more is a dungeon, and a dungeon is
-- laid out by rule ("dungeon": kit/lib/worlddungeon.luau - rooms set down, joined by corridors, every room reached
-- by construction) - or the blueprint says "dungeon": false at its top (these rooms are typed by hand, meant).
-- A dungeon step elsewhere in the blueprint excuses nothing (a fresh reader: a tiny dungeon far away let any
-- number of typed rooms through). -> how many "room" steps it has when it does not say so (0 = nothing to ask)
LaneLocks.ROOMS_TYPED = 6
function LaneLocks.typedRooms(bp: any): number
	if type(bp) ~= "table" or type(bp.build) ~= "table" or bp.dungeon == false then
		return 0
	end
	local rooms = 0
	for _, step in Prefab.flat(bp) do
		if type(step) == "table" then
			rooms += if type(step.room) == "table" then 1 else 0
		end
	end
	return if rooms >= LaneLocks.ROOMS_TYPED then rooms else 0
end

-- ... a world UNDER SNOW says whether its roofs and ledges are snowed on too: "cover": { "snow": { "depth" } }
-- (kit/lib/worldcover.luau) or "cover": false (bare, meant). Under snow = its land is snow or glacier, or snow falls
-- (its "ambient", or a weather of its cycle). Asked of the world as written and of every season; the first that
-- says neither and builds anything: "as written" | "in its <season>", or nil
local function snowy(bp: any): boolean
	if bp.ambient == "snow" then
		return true
	end
	if type(bp.weather) == "table" and type(bp.weather.cycle) == "table" then
		for _, w in bp.weather.cycle do
			if type(w) == "table" and w.ambient == "snow" then
				return true
			end
		end
	end
	local function white(m: any): boolean
		return m == "Snow" or m == "Glacier"
	end
	for _, op in (if type(bp.terrain) == "table" then bp.terrain else {}) :: { any } do
		if type(op) == "table" then
			for _, spec in op do
				if type(spec) == "table" then
					-- its own material, what lies under it, its layers, its patches, the painter's materials
					if white(spec.material) or white(spec.under) or white(spec.rock) then
						return true
					end
					for _, list in { spec.layers, spec.patches } do
						for _, l in (if type(list) == "table" then list else {}) :: { any } do
							if type(l) == "table" and white(l.material) then
								return true
							end
						end
					end
					if type(spec.paint) == "table" then
						for _, m in spec.paint do
							if white(m) then
								return true
							end
						end
					end
					-- a painted land whose painter laid snow (kit/world/terrain.py: the role "snow")
					if type(spec.source) == "string" and spec.paint ~= false and fs.isFile(spec.source) then
						local ok, hm = pcall(serde.decode, "json" :: any, fs.readFile(spec.source))
						if ok and type(hm) == "table" and type(hm.roles) == "table" and type(hm.paint) == "string" then
							for r, role in hm.roles do
								-- (one character a cell: role r is string.char(47 + r), kit/world/terrain.py paint_encode)
								if role == "snow" and string.find(hm.paint, string.char(47 + r), 1, true) then
									return true
								end
							end
						end
					end
				end
			end
		end
	end
	return false
end
function LaneLocks.unsaidCover(bp: any): string?
	if type(bp) ~= "table" or type(bp.build) ~= "table" or #bp.build == 0 then
		return nil
	end
	if snowy(bp) and bp.cover == nil then
		return "as written"
	end
	for _, name in Season.names(bp) do
		local seen = Season.apply(bp, name)
		if seen ~= bp and snowy(seen) and seen.cover == nil then
			return `in its {name}`
		end
	end
	return nil
end

-- ... a world whose WEATHER CLOSES THE AIR IN (a stage of its cycle with "fog" of LaneLocks.FOG_LOW or more, as
-- written or in any season) and that has land says where the fog lies low: a "fog" step (kit/lib/worldfog.luau:
-- sheets over low ground, water or hollows - Roblox's Atmosphere is one haze by distance, never by height) or
-- "fog": false at the blueprint's top (the haze alone, meant). -> where it was found unsaid, or nil
LaneLocks.FOG_LOW = 0.5
local function foggy(bp: any): boolean
	local w = bp.weather
	if type(w) ~= "table" or type(w.cycle) ~= "table" then
		return false
	end
	for _, st in w.cycle do
		if type(st) == "table" and type(st.fog) == "number" and st.fog >= LaneLocks.FOG_LOW then
			return true
		end
	end
	return false
end
function LaneLocks.unsaidFog(bp: any): string?
	if type(bp) ~= "table" or type(bp.terrain) ~= "table" or bp.fog == false then
		return nil
	end
	local land = false
	for _, op in bp.terrain do
		if type(op) == "table" and (op.ground ~= nil or op.heightmap ~= nil) then
			land = true
		end
	end
	if not land then
		return nil
	end
	-- (each version of the world is read for itself: a season may leave the fog step out - "skip" - or bring its
	-- own thick weather)
	local function laid(b: any): boolean
		for _, step in Prefab.flat(b) do
			if type(step) == "table" and step.fog ~= nil then
				return true
			end
		end
		return false
	end
	if foggy(bp) and not laid(bp) then
		return "as written"
	end
	for _, name in Season.names(bp) do
		local seen = Season.apply(bp, name)
		if seen ~= bp and seen.fog ~= false and foggy(seen) and not laid(seen) then
			return `in its {name}`
		end
	end
	return nil
end

-- ... a world with SEASONS says which one it is built in: "season": "<name>" or "season": false (as written)
-- (kit/lib/worldseason.luau). True for a world that has "seasons" and says neither:
function LaneLocks.unsaidSeason(bp: any): boolean
	return type(bp) == "table" and bp.seasons ~= nil and bp.season == nil
end

-- ... a TOWN says whether its yards are dressed: "yards": true (woodpiles and wash lines by rule, only in the yards a
-- walker can enter: kit/lib/worldtown.luau Town.yardThings) or "yards": false (bare yards, meant)
function LaneLocks.unsaidYards(bp: any): { string }
	local out = {}
	if type(bp) ~= "table" or type(bp.build) ~= "table" then
		return out
	end
	for i, step in Prefab.flat(bp) do
		if type(step) == "table" and type(step.town) == "table" and type(step.town.yards) ~= "boolean" then
			table.insert(out, if type(step.town.name) == "string" then step.town.name else `build[{i}]`)
		end
	end
	return out
end

-- ... and a TOWN says how its streets run: "bend": <degrees> (kit/lib/worldtown.luau: the plan twisted round its
-- square, each block of houses moved and turned as one piece - streets that curve and funnel, houses at many
-- angles) or "bend": 0 (straight streets on two axes, meant). The names of the town steps that say neither:
function LaneLocks.unsaidTownBends(bp: any): { string }
	local out = {}
	if type(bp) ~= "table" or type(bp.build) ~= "table" then
		return out
	end
	for i, step in Prefab.flat(bp) do
		if type(step) == "table" and type(step.town) == "table" and step.town.bend == nil then
			table.insert(out, if type(step.town.name) == "string" then step.town.name else `build[{i}]`)
		end
	end
	return out
end

function LaneLocks.world(names: { string }?, root: string?, projectFile: string?): { string }
	local dir = root or Config.path("worlds")
	local problems = {}
	for _, p in
		pieces(dir, names, function()
			return true
		end)
	do
		local path, n = p[1], p[2]
		if not Locks.grandfathered("world", path) and not Locks.waiver("world", n, "refs") then
			local refs = `{dir}/refs/{n}`
			local stills = 0
			if fs.isDir(refs) then
				for _, file in fs.readDir(refs) do
					local ext = string.match(string.lower(file), "%.(%w+)$")
					if ext and STILL[ext] then
						stills += 1
					end
				end
			end
			local measured = fs.isFile(`{refs}/REFS.md`)
			if stills < 6 or not measured then
				table.insert(
					problems,
					`{n}: a new world is built beside real references - {stills} still(s) in {refs}/ (needs >= 6, the owner's picks){if measured
						then ""
						else " and no measured REFS.md"}: put them there, then lune run kit world refs {n}`
				)
			end
		end
		-- the owner's rig (2026-10-29 "some things are not ... to perfectly fit my R6 rig"): a new world names its
		-- rig's scale sheet, so kit world check holds every ceiling, doorway, stair and rail its generators claim
		-- the route stages (W1 greybox, W2 corner)
		if not Locks.grandfathered("world", path) then
			local okBp, bp = pcall(function()
				return serde.decode("json" :: any, fs.readFile(path))
			end)
			if okBp and type(bp) == "table" then
				for _, line in LaneLocks.worldStages(path, n, bp, LaneLocks.worldsRoot(dir)) do
					table.insert(problems, line)
				end
			end
		end
		if not Locks.grandfathered("world", path) and not RIG_RULE_BEFORE[string.lower(Locks.normal(path))] then
			local okBp, bp = pcall(function()
				return serde.decode("json" :: any, fs.readFile(path))
			end)
			if okBp and type(bp) == "table" and (type(bp.scale) ~= "string" or bp.scale == "") then
				table.insert(
					problems,
					`{n}: a new world names its rig's scale sheet - add "scale": "r6" to {path} (kit world check then holds every ceiling, doorway, stair and rail its generators build to the R6 rig)`
				)
			end
		end
		if not Locks.grandfathered("world", path) and not Locks.waiver("world", n, "layout") then
			local okBp, bp = pcall(function()
				return serde.decode("json" :: any, fs.readFile(path))
			end)
			local typed, cities = 0, 0
			if okBp then
				typed, cities = LaneLocks.typedHouses(bp)
			end
			local how =
				`one "town" step in {path} (center, area, gates, mats, skins: kit/skills/parallax-world/reference/05-town-plan.md; with it there, lune run kit world town {n} draws the plan). The owner may waive it: lune run kit approve world {n} "<their words>" --by owner --waive layout`
			if typed >= LaneLocks.LAYOUT_TYPED then
				table.insert(
					problems,
					`{n}: {typed} houses typed one by one ("building" steps and house meshes) - a place of {LaneLocks.LAYOUT_TYPED} or more is a town, and a town is laid out by its plan: {how}`
				)
			end
			if cities > 0 then
				table.insert(
					problems,
					`{n}: {cities} "city" step(s) - a regular grid of box blocks is the layout the town plan replaces (streets round a closed square, terraced lots, the landmark closing the gate street): {how}`
				)
			end
		end
		if not Locks.grandfathered("world", path) then
			local okBp, bp = pcall(function()
				return serde.decode("json" :: any, fs.readFile(path))
			end)
			-- (measured by compiling: only for a world that does not already say how it streams, and never for one the
			-- owner waived: lune run kit approve world <Name> "<words>" --by owner --waive streaming)
			if okBp and not LaneLocks.streams(bp) and not Locks.waiver("world", n, "streaming") then
				local reach = LaneLocks.reach(bp)
				if reach > LaneLocks.STREAM_REACH then
					table.insert(
						problems,
						`{n}: its played world reaches {math.floor(reach + 0.5)} studs across (far scenery left out) and does not say how it streams - Roblox brings a place in round each player to {LaneLocks.STREAM_REACH} studs. Add "streaming": \{ "cell": 256 } to {path} (a cell of 64 to 512 studs: every step becomes a Model with the engine's far stand-in, a step wider than a cell is cut by cells, the far scenery stays in), and turn StreamingEnabled on in the game's project file (Workspace's properties: the build checks it once the world says how it streams; the kit does not write it). The owner may waive it: --waive streaming`
					)
				end
			end
			-- a world that says how it streams needs the game's own switch: its project file turns streaming on
			-- (LaneLocks.projectFor says which file). The owner may waive it - streaming turned on some other way: a
			-- meta file, the place itself in Studio - with the same waiver as the reach rule's: --waive streaming
			if okBp and LaneLocks.streams(bp) and not Locks.waiver("world", n, "streaming") then
				local project, must = LaneLocks.projectFor(root, projectFile)
				local switch = LaneLocks.streamSwitch(project)
				if switch == "off" or switch == "unread" or (switch == "missing" and must) then
					local why = if switch == "off"
						then "no StreamingEnabled"
						elseif
							switch == "missing"
						then 'no such file - is "rojo" in kit.config.json the game\'s project file?'
						else "not a Rojo project"
					table.insert(
						problems,
						`{n}: it is prepared for streaming ("streaming" in {path}) but the game's project does not turn streaming on ({project}: {why}) - without it Roblox sends every player the whole place and the cells and far stand-ins do nothing; in the project's tree: "Workspace": \{ "$properties": \{ "StreamingEnabled": true } } (the project file is the game's: ask its owner before changing it; turned on some other way, the owner may waive it: --waive streaming)`
					)
				end
			end
			-- LOADING INTENT (kit/lib/worldstream.luau; the owner's W-R03): a world that streams says how fast its
			-- players move, the game keeps that much ground loaded round each of them, and its landmarks say
			-- whether they stream out. The same waiver: --waive streaming
			-- (asked of ANY "streaming" block: one with "lod": false or a cell past 512 does not pass the reach rule
			-- above, but the compiler still packs it and makes its Persistent / Atomic models and its arrivals)
			if okBp and type(bp.streaming) == "table" and not Locks.waiver("world", n, "streaming") then
				local intent, wrong = Stream.intent(bp.streaming)
				if intent.speed == nil and #wrong == 0 then
					table.insert(
						problems,
						`{n}: it streams but does not say how fast its players move - give "streaming": \{ "speed": <studs a second: {Stream.WALK} on foot, more for a mount, a cart or a dash> } (and "fall": <the highest drop they take, studs>) in {path}: Roblox loads a place by distance alone, and the game's streaming radii are held to what that speed needs`
					)
				elseif intent.speed ~= nil then
					local project = LaneLocks.projectFor(root, projectFile)
					local props = LaneLocks.streamProps(project)
					-- (with the switch off or no project the line above already says so: nothing is held to radii
					-- of a place that does not stream)
					if props ~= nil and LaneLocks.streamSwitch(project) == "on" then
						local need, target = Stream.need(intent), Stream.target(intent)
						if props.min < need then
							table.insert(
								problems,
								`{n}: its players move {intent.speed} studs a second ("streaming" in {path}): {Stream.LEAD} s of their way is {need} studs, but the game's project keeps {props.min} round each player ({project}: StreamingMinRadius) - set "StreamingMinRadius": {need} in its Workspace "$properties" (the project file is the game's: the kit does not write it). Roblox's own page recommends 64 and says more costs every player memory: for a few fast stretches name "arrivals" and ask for them ahead instead (WorldStream.ahead)`
							)
						end
						if props.target < target then
							table.insert(
								problems,
								`{n}: its players need {need} studs kept loaded and the game's project streams in to {props.target} ({project}: StreamingTargetRadius) - set it to {target} or more: a target at the minimum leaves no buffer (Roblox's streaming page)`
							)
						end
						if intent.speed > Stream.WALK and not props.pause then
							table.insert(
								problems,
								`{n}: its players move faster than a walk ({intent.speed} studs a second) and the game's project does not pause a player who outruns the loaded ground ({project}) - set "StreamingIntegrityMode": "PauseOutsideLoadedArea" in its Workspace "$properties": it is the engine's own guard against falling through ground that has not arrived`
							)
						end
						local arrivals = Stream.arrivals(bp.streaming)
						if intent.fall > props.min and #arrivals == 0 then
							table.insert(
								problems,
								`{n}: its players drop {intent.fall} studs ("streaming.fall" in {path}) and the game keeps {props.min} studs round them loaded: the landing is not there when they step off - name each landing in "streaming": \{ "arrivals": [ \{ "name", "pos" } ] } and call WorldStream.ahead(player, name) at the top of the drop`
							)
						end
					end
				end
				local marks = LaneLocks.unsaidLandmarks(bp)
				if #marks > 0 then
					table.insert(
						problems,
						`{n}: {#marks} landmark(s) do not say whether they stream out: "{table.concat(marks, '", "')}" - give each "stream": "always" (steered by from across the map: Roblox never streams it out; a few parts only) or "stream": "area" (it comes and goes with its place, meant) in {path}; a town says it of its landmark house: "landmark": \{ "stream": "always" }; a tall step that is no landmark says "landmark": false`
					)
				end
			end
			local bare = if okBp and not ROOMS_RULE_BEFORE[string.lower(Locks.normal(path))]
				then LaneLocks.unsaidRooms(bp)
				else {}
			if #bare > 0 then
				table.insert(
					problems,
					`{n}: {#bare} house(s) do not say whether they have rooms inside: {table.concat(bare, ", ")} - give each "rooms": true (its floors cut into rooms by rule: partitions with a doorway each, the stair hall kept clear) or "rooms": false (one open room a floor, meant) in {path}; a town takes it in "house": \{ "rooms": true }`
				)
			end
			local unlevelled = if okBp then LaneLocks.unsaidSlopes(bp) else {}
			if #unlevelled > 0 then
				table.insert(
					problems,
					`{n}: {#unlevelled} town(s) do not say how their land lies: "{table.concat(unlevelled, '", "')}" - give each "slope": \{ "rise": <studs in 100, up to 6>, "toward": "N" | "E" | "S" | "W" } (a hillside: the houses step up it) or "slope": false (level ground, meant) in {path}`
				)
			end
			local unfronted = if okBp then LaneLocks.unsaidFacades(bp) else {}
			if #unfronted > 0 then
				table.insert(
					problems,
					`{n}: {#unfronted} town(s) with house meshes do not say how their houses are made: "{table.concat(
						unfronted,
						'", "'
					)}" - give each "facade": true (every house put together from modules by rule: 5 meshes a storey height and 3 for the town, houses of one type differ) or "facade": false (one whole mesh a house type: 30 to 65 meshes a town, meant) in {path}`
				)
			end
			-- (asked of the world as written AND in each of its seasons: a winter may bring its own "ambient")
			local snowed = if okBp and not Locks.grandfathered("world", path)
				then LaneLocks.unsaidWeatherIn(bp)
				else nil
			if snowed then
				table.insert(
					problems,
					`{n}: {snowed.where} it has a weather ("ambient": "{snowed.ambient}") and does not say whether it ever changes - say "weather": false (that one weather for ever, meant) or take "ambient" out and give the weathers in turn: "weather": \{ "cycle": [ \{ "ambient": "clear", "minutes": 10 }, \{ "ambient": "{snowed.ambient}", "minutes": 6, "fog": 0.4, "dim": 0.2 } ], "change": 40 } in {path} (every player sees the same weather at the same moment)`
				)
			end
			local even = if okBp and not Locks.grandfathered("world", path) then LaneLocks.unsaidDensities(bp) else {}
			if #even > 0 then
				table.insert(
					problems,
					`{n}: {#even} scatter(s) and forest(s), together {LaneLocks.SCATTER_ASKED} pieces or more, do not say where their pieces go: "{table.concat(
						even,
						'", "'
					)}" - give each "density": \{ "gap": <studs between two pieces>, "noise": \{ "scale": 60 } } (clumps and clearings; or "spots", "away", a painted "map"; no "count": it comes out of the gap and the field) or "density": false (that many pieces evenly over the whole area, meant) in {path}`
				)
			end
			local mixed = if okBp and not Locks.grandfathered("world", path) then LaneLocks.unsaidEcosystems(bp) else {}
			if #mixed > 0 then
				table.insert(
					problems,
					`{n}: {#mixed} forest(s) of two or more kinds of tree, together {LaneLocks.FOREST_ASKED} trees or more, do not say how their kinds came to stand where they do: "{table.concat(
						mixed,
						'", "'
					)}" - give each "ecosystem": \{ "years": 80, "species": [ \{ "name", "style", "height": [4, 30], "crown", "years", "life", "shade", "seeds", "throw" } ] } (the trees grow, seed, shade each other out and die: kit/lib/worldecosystem.luau; no "count", "styles" or "height" beside it) or "ecosystem": false (its kinds mixed by chance, meant) in {path}`
				)
			end
			local byHand = if okBp and not Locks.grandfathered("world", path) then LaneLocks.unsaidRoutes(bp) else {}
			if #byHand > 0 then
				table.insert(
					problems,
					`{n}: {#byHand} road(s) across the land, together {LaneLocks.ROAD_ASKED} studs or more, do not say how their way was found: "{table.concat(
						byHand,
						'", "'
					)}" - give each "route": \{ "from": [x, z], "to": [x, z], "grade": 0.25 } in place of its "points" (the road finds its own way over the ground, never steeper than the grade, round the water) or "route": false (its points typed by hand, meant) in {path}`
				)
			end
			local unweathered = if okBp and not Locks.grandfathered("world", path)
				then LaneLocks.unsaidClimates(bp)
				else {}
			if #unweathered > 0 then
				table.insert(
					problems,
					`{n}: {#unweathered} painted land(s) do not say what climate painted them: {table.concat(
						unweathered,
						", "
					)} - make the terrain again with a climate (lune run kit world terrain <Name> --climate "wind=270,rain=0.6,sea=0.8": the windward side of a ridge wet, its lee dry, snow lower on a north face) or say "climate": false on its heightmap op (painted by slope, water and height alone, meant) in {path}`
				)
			end
			local roomsTyped = if okBp and not Locks.grandfathered("world", path) then LaneLocks.typedRooms(bp) else 0
			if roomsTyped > 0 then
				table.insert(
					problems,
					`{n}: {roomsTyped} rooms typed one by one ("room" steps) - a place of {LaneLocks.ROOMS_TYPED} rooms or more is laid out by rule: one "dungeon": \{ "center", "area", "rooms", "mat", "floor" } step (rooms set down and joined by corridors, every room reached by construction), or say "dungeon": false at the blueprint's top (typed by hand, meant) in {path}`
				)
			end
			local snowBare = if okBp and not Locks.grandfathered("world", path) then LaneLocks.unsaidCover(bp) else nil
			if snowBare then
				table.insert(
					problems,
					`{n}: it lies under snow ({snowBare}) and does not say whether its roofs and ledges are snowed on - say "cover": \{ "snow": \{ "depth": 0.6 } } (snow on every top face the sky sees; "dust" too: on floors under a roof) or "cover": false (bare, meant) in {path}`
				)
			end
			local fogUnsaid = if okBp and not Locks.grandfathered("world", path) then LaneLocks.unsaidFog(bp) else nil
			if fogUnsaid then
				table.insert(
					problems,
					`{n}: its weather closes the air in ({fogUnsaid}: fog {LaneLocks.FOG_LOW} or more) and it does not say where the fog lies low - Roblox's haze is by distance only; add a step to its "build": \{ "fog": \{ "over": "low", "below": <height>, "mat": "<palette>" } } (or "over": "water" / "hollows"), or say "fog": false at the blueprint's top (the haze alone, meant) in {path}`
				)
			end
			if okBp and LaneLocks.unsaidSeason(bp) then
				local seasonNames = Season.names(bp)
				table.insert(
					problems,
					`{n}: it has seasons ({table.concat(seasonNames, ", ")}) and does not say which one it is built in - say "season": "<one of them>" or "season": false (the world as written) in {path}`
				)
			end
			local yardless = if okBp then LaneLocks.unsaidYards(bp) else {}
			if #yardless > 0 then
				table.insert(
					problems,
					`{n}: {#yardless} town(s) do not say whether their yards are dressed: "{table.concat(
						yardless,
						'", "'
					)}" - give each "yards": true (woodpiles and wash lines set out by rule in the yards a walker can enter; mats.wood and mats.cloth) or "yards": false (bare yards, meant) in {path}`
				)
			end
			local squares = if okBp then LaneLocks.unsaidMarkets(bp) else {}
			if #squares > 0 then
				table.insert(
					problems,
					`{n}: {#squares} town(s) do not say whether their square holds a market: "{table.concat(
						squares,
						'", "'
					)}" - give each "market": true (stalls set out by rule on the square, the gate's view and the streets' mouths kept clear; mats.stall and mats.cloth) or "market": false (an empty square, meant) in {path}`
				)
			end
			local towns = if okBp then LaneLocks.unsaidTownBends(bp) else {}
			if #towns > 0 then
				table.insert(
					problems,
					`{n}: {#towns} town(s) do not say how their streets run: "{table.concat(towns, '", "')}" - give each "bend": <3 to 8 degrees> (the plan twisted round its square: streets that curve and funnel, every block of houses turned with them; lune run kit world town {n} draws it) or "bend": 0 (straight streets on two axes, meant) in {path}`
				)
			end
			local bends = if okBp then LaneLocks.unsaidBends(bp) else {}
			if #bends > 0 then
				table.insert(
					problems,
					`{n}: {#bends} line(s) of points turn a hard corner and do not say how they bend: {table.concat(
						bends,
						", "
					)} - give each "curve": true (a smooth line through its points: a road, a fence, a row that bends) or "curve": false (a hard corner, meant) in {path}`
				)
			end
		end
		-- enforced learning, rule 2: a new world answers its lessons sheet before it is built (and in kit verify)
		local unanswered = LaneLocks.lessonProblem("world", dir, path, n)
		if unanswered then
			table.insert(problems, unanswered)
		end
		if not root then -- a build (kit world): the verdict cap applies too
			local over = LaneLocks.cap("world", n, path)
			if over then
				table.insert(problems, over)
			end
		end
	end
	return problems
end

-- ------------------------------------------------------------ anim
-- move dossiers made after the locks are schema 2 (the build refuses them in proc_dossier.py; verify shows them early)
function LaneLocks.dossiers(dir: string): { string }
	local problems = {}
	for _, n in
		listing(dir, function(stem)
			return string.sub(stem, 1, 1) ~= "_"
		end)
	do
		local path = `{dir}/{n}.json`
		if not Locks.grandfathered("anim", path) and not Locks.waiver("anim", n, "evidence") then
			local ok, d = pcall(serde.decode, "json" :: any, fs.readFile(path))
			local schema = if ok and type(d) == "table" then tonumber(d.schema) or 1 else 1
			if schema < 2 then
				table.insert(
					problems,
					`{n}: a dossier made after the locks is schema 2 with measured evidence ({path}; lune run kit anim dossier footage {n} <clip>)`
				)
			end
		end
	end
	return problems
end

-- ------------------------------------------------------------ lessons answered (enforced learning, rule 2)
-- board/plans/archive/2026-11-09-enforced-learning-plan.md: every new piece of a content lane answers the vault lessons ranked
-- for it before it counts as made - <the piece's folder>/<name>.lessons.md, the sheet world piloted (kit/lib/answers.luau;
-- 3D answers them in its study). The pieces that exist the first time this runs are its grandfathered list
-- (`grandfathered["<lane>-lessons"]`, frozen once, as the 3D study lock was): nothing under way is stopped half-made.
LaneLocks.LESSON_LANES = { "vfx", "ui", "anim", "sfx", "world" }

local function lessonsKey(lane: string): string
	return lane .. "-lessons"
end

-- every piece file of a lane under the project roots: the list a first run freezes
local function pieceFiles(lane: string): { string }
	local out = {}
	for _, root in LaneLocks.roots() do
		for _, spec in PIECES[lane] or {} do
			local dir = root .. spec[1]
			if fs.isDir(dir) then
				for _, file in fs.readDir(dir) do
					if string.match(file, spec[2]) then
						table.insert(out, Locks.normal(`{dir}/{file}`))
					end
				end
			end
		end
	end
	table.sort(out)
	return out
end

-- true when this piece predates the lessons lock; the first call in a project with a locks file freezes the lane's list
function LaneLocks.lessonsExempt(lane: string, path: string): boolean
	if Locks.FILE == "board/locks.json" and fs.isFile(Locks.FILE) then
		local g = Locks.load().grandfathered
		if type(g) ~= "table" or g[lessonsKey(lane)] == nil then
			Locks.reset() -- (re-read right before the write: another session may have approved something since)
			local data = Locks.load()
			if type(data.grandfathered) ~= "table" then
				data.grandfathered = {}
			end
			data.grandfathered[lessonsKey(lane)] = pieceFiles(lane)
			data.lessons_lock = data.lessons_lock or os.date("!%Y-%m-%d")
			Locks.save(data)
		end
	end
	return Locks.grandfathered(lessonsKey(lane), path)
end

-- a piece's lessons sheet: beside its file
function LaneLocks.sheetPath(dir: string, name: string): string
	return `{dir}/{name}.lessons.md`
end

-- the folder that holds a lane's piece `name` (the project root and every games/<Name>/), or nil
function LaneLocks.pieceDir(lane: string, name: string): string?
	for _, root in LaneLocks.roots() do
		for _, spec in PIECES[lane] or {} do
			local dir = root .. spec[1]
			if fs.isDir(dir) then
				for _, file in fs.readDir(dir) do
					local n = string.match(file, spec[2])
					if n and string.lower(n) == string.lower(name) then -- (as the debts match names: in any case)
						return dir
					end
				end
			end
		end
	end
	return nil
end

-- one piece's lessons problem (nil when answered, grandfathered or waived)
function LaneLocks.lessonProblem(lane: string, dir: string, path: string, n: string): string?
	if LaneLocks.lessonsExempt(lane, path) or Locks.waiver(lane, n, "lessons") then
		return nil
	end
	local sheet = LaneLocks.sheetPath(dir, n)
	local why: string? = nil
	if not fs.isFile(sheet) then
		why = "its lessons sheet is missing"
	else
		-- only a sheet kit answer ranked (its lessons to answer are on record) and checked as it reads NOW passes: a
		-- hand-written sheet with no record ranks nothing, and unchecked answers record nothing on the piece
		local Answers = require("./answers")
		local text = fs.readFile(sheet)
		local entry = Answers.entry(sheet)
		if not entry then
			why = "its lessons sheet was not made by kit answer (no ranked lessons on record)"
		else
			local r = Answers.check(text, lane, sheet)
			if #r.problems > 0 then
				why = `{#r.problems} of its lessons unanswered ({r.problems[1]})`
			elseif entry.answered ~= require("./vault").digest(text) then
				why =
					"its answers were never checked as they read now (kit answer records the applied lessons on the piece)"
			end
		end
	end
	if not why then
		return nil
	end
	return `{n}: {why} - a new {lane} piece answers the lessons ranked for it before it counts as made: lune run kit answer {lane} {n}`
end

-- the lane's new pieces under one project root (`root` ends in "/" or is "") whose lessons are not answered (world's
-- are checked by LaneLocks.world, at its build and in kit verify)
function LaneLocks.lessons(lane: string, root: string?): { string }
	local problems = {}
	for _, spec in PIECES[lane] or {} do
		local dir = (root or "") .. spec[1]
		if fs.isDir(dir) then
			for _, file in fs.readDir(dir) do
				local n = string.match(file, spec[2])
				if n then
					local p = LaneLocks.lessonProblem(lane, dir, `{dir}/{file}`, n)
					if p then
						table.insert(problems, p)
					end
				end
			end
		end
	end
	return problems
end

-- ------------------------------------------------------------ look before showing (enforced learning, rule 3)
-- board/plans/archive/2026-11-09-enforced-learning-plan.md: the owner's verdict on a piece expects the session to have LOOKED
-- at that very version with the lane's own look tool (the car rim, 2026-11-09: "if u keep missing spots like this and
-- i gotta keep checking its dumb man"). The verdict is always recorded (kit/ui/rate.py and the grading rounds record
-- through kit verdict too); a missing look is marked on it and owed, like its lesson (kit/lib/vault.luau).

-- a file's modified time in seconds (nil when it does not exist)
local function mtime(path: string): number?
	local ok, meta = pcall(fs.metadata, path)
	if ok and meta and meta.exists and meta.modifiedAt then
		return meta.modifiedAt.unixTimestamp
	end
	return nil
end

-- the newest of a set of files' times (nil when none exists)
local function newest(paths: { string }): number?
	local best: number? = nil
	for _, p in paths do
		local t = mtime(p)
		if t and (not best or t > best) then
			best = t
		end
	end
	return best
end

-- the build folder that goes with a piece's folder: games/<Name>/build/ for a game's piece, else build/
local function buildRootOf(dir: string): string
	local game = string.match(dir, "^games/([^/]+)/")
	return if game then `games/{game}/build/` else "build/"
end

-- the 3D look record (kit look sheet) names the build it rendered: the saved .blend and manifest, by size and time
local function sheetOfBuild(record: string, blend: string, manifest: string): boolean
	local ok, rec = pcall(serde.decode, "json" :: any, fs.readFile(record))
	if not ok or type(rec) ~= "table" or type(rec.build) ~= "table" then
		return false
	end
	for which, path in { blend = blend, manifest = manifest } do
		local stamp = rec.build[which]
		local okm, meta = pcall(fs.metadata, path)
		if type(stamp) ~= "table" or not okm or not meta or not meta.exists or not meta.modifiedAt then
			return false
		end
		local okr, text = pcall(fs.readFile, path)
		local size = if okr then #text else -1
		local stampSec = (tonumber(stamp.mtime_ns) or 0) / 1e9
		if tonumber(stamp.size) ~= size or math.abs(stampSec - meta.modifiedAt.unixTimestamp) > 2 then
			return false
		end
	end
	return true
end

-- what the session has not looked at for a piece's CURRENT version, with the look command; nil when looked (or when
-- the kit cannot tell: no such piece in its lane, or a kind with no look tool)
function LaneLocks.lookProblem(kind: string, name: string): (string?, string?, boolean)
	local Vault = require("./vault")
	local dept = Vault.dept(kind)
	if dept == "3d" then
		local dir = LaneLocks.pieceDir("3d", name)
		if not dir then
			return nil, nil, false
		end
		local b = buildRootOf(dir)
		local blend, manifest = `{b}models/{name}.blend`, `{b}models/{name}.manifest.json`
		local record = `{b}renders/{name}_sheet.json`
		local cmd = `lune run kit look sheet {name}`
		if not fs.isFile(blend) or not fs.isFile(manifest) then
			return nil, nil, false -- (no saved build: nothing the owner saw came from kit asset)
		end
		if not fs.isFile(record) then
			return `no look sheet of {name}'s build ({record})`, cmd, true
		end
		if not sheetOfBuild(record, blend, manifest) then
			return `{name}'s look sheet is of an older build`, cmd, true
		end
		return nil, nil, true
	end
	local looks: { [string]: { any } } = {
		-- lane = { the look outputs under the build root (relative), the command, extra sources under the build root }
		ui = { {}, `lune run kit ui look {name} "<what you saw>"`, { `ui/{name}.png` } },
		vfx = {
			{ `vfx/booth/{name}_play.metrics.json`, `vfx/{name}.png` },
			`lune run kit vfx play {name} --record`,
			{},
		},
		anim = {
			-- (kit anim look --rig R6 writes <name>.r6.look.*: the older looks; the lane's look since 2026-11-12 is its
			-- SHEET - the key poses large, the strips, the timing chart - whose record is <name>.sheet/look.json: it
			-- counts too, so a sheet looked at is no look still owed (card u8d6; the owner's V3 list, anim stage A.2))
			{
				`animations/{name}.sheet/look.json`,
				`animations/{name}.look.gif`,
				`animations/{name}.look.png`,
				`animations/{name}.r6.look.gif`,
				`animations/{name}.r6.look.png`,
			},
			`lune run kit anim sheet {name}`,
			{ `animations/{name}.clip.json`, `animations/{name}.r6.clip.json` },
		},
		-- (a sound set's sheet is set_<name>.png: kit/audio/sets.py)
		sfx = { { `sounds/sheets/{name}.png`, `sounds/sheets/set_{name}.png` }, `lune run kit sfx sheet {name}`, {} },
		world = { { `worlds/look/{name}.png` }, `lune run kit world look {name}`, {} },
	}
	local spec = if dept then looks[dept] else nil
	if not spec or not dept then
		return nil, nil, false
	end
	local dir: string? = nil
	local b: string? = nil
	local sources: { string } = {}
	if dept == "anim" then
		-- an animation is judged by its CLIP's name (its looks carry it; dossiers are named for the move): a name with no
		-- built clip - a dossier alone - is no version the kit can match a look to
		for _, root in LaneLocks.roots() do
			for _, clip in { `{root}build/animations/{name}.clip.json`, `{root}build/animations/{name}.r6.clip.json` } do
				if fs.isFile(clip) then
					b = root .. "build/"
				end
			end
			if b then
				break
			end
		end
	else
		dir = LaneLocks.pieceDir(dept, name)
		if dir then
			b = buildRootOf(dir)
			table.insert(sources, `{dir}/{name}.json`)
		end
	end
	if not b then
		return nil, nil, false
	end
	for _, rel in spec[3] do
		table.insert(sources, b .. rel)
	end
	local outputs = {}
	if dept == "ui" then
		table.insert(outputs, `{dir}/{name}.look.json`) -- (kit/ui/judge.py writes it beside the screen's spec)
	end
	for _, rel in spec[1] do
		table.insert(outputs, b .. rel)
	end
	local seen, made = newest(outputs), newest(sources)
	if not seen then
		return `no {dept} look of {name} yet`, spec[2], true
	end
	if made and seen < made then
		return `{name} changed after its last {dept} look`, spec[2], true
	end
	return nil, nil, true
end

-- one lock's problems as a gate step (the summary names every refused piece, so the selftest can read them)
function LaneLocks.report(name: string, problems: { string }, passSummary: string): Run.Step
	local names = {}
	for _, p in problems do
		table.insert(names, string.match(p, "^([^:]+):") or p)
	end
	return Run.step(name, #problems == 0, table.concat(problems, "\n"), {
		status = if #problems == 0 then "pass" else "fail",
		summary = if #problems == 0
			then passSummary
			else `{#problems} new piece(s) skipped a quality step: {table.concat(names, ", ")}`,
		next_action = problems[1],
	})
end

-- kit verify: the lane locks with no gate of their own, in the project root and every games/<Name>/, and the cap
function LaneLocks.step(): Run.Step
	local problems = {}
	local function add(list: { string })
		for _, p in list do
			table.insert(problems, p)
		end
	end
	for _, root in LaneLocks.roots() do
		add(LaneLocks.sfx(nil, nil, root .. "assets/sounds"))
		add(LaneLocks.assets(root .. "assets/models"))
		-- (each root's own project file: without naming it the streaming switch was never read by kit verify - the
		-- world folder has no project file of its own, and a folder's missing file asks nothing)
		add(LaneLocks.world(nil, root .. "assets/worlds", root .. "default.project.json"))
		add(LaneLocks.dossiers(root .. "assets/animations/dossiers"))
		for _, lane in LaneLocks.LESSON_LANES do
			if lane ~= "world" then -- (LaneLocks.world above checks a world's lessons)
				add(LaneLocks.lessons(lane, root))
			end
		end
	end
	for lane in PIECES do -- (the cap is per project: the kit home and each game count apart)
		for _, root in LaneLocks.roots() do
			local open = LaneLocks.unscored(lane, { root })
			if #open > LaneLocks.OPEN_CAP then
				table.insert(
					problems,
					`{lane} lane{if root == "" then "" else ` ({root})`}: {#open} new pieces the owner has not scored ({table.concat(
						open,
						", "
					)}) - the cap is {LaneLocks.OPEN_CAP}: show them and record their verdicts (lune run kit verdict ...) before building more`
				)
			end
		end
	end
	return LaneLocks.report(
		"quality locks",
		problems,
		"every new sound, asset, world and dossier has its quality step (or the owner's waiver); every lane within its verdict cap"
	)
end

return LaneLocks

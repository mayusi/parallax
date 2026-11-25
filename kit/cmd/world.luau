-- world.luau — the world pipeline's sub-commands (`kit world <sub> ...`); `kit world` itself (compile every blueprint
-- into src/world + the top-down map + build) stays in content.luau and hands the words listed here to this module.
-- The plan and the ideas behind them: board/plans/archive/2026-10-12-world-pipeline-v2.md.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Config = require("../lib/config")
local Environment = require("../lib/environment")
local Facade = require("../lib/worldfacade")
local Run = require("../lib/run")
local Town = require("../lib/worldtown")
local World = require("../lib/world")

local WorldCmd = {}

type Sub = { usage: string, about: string, run: ({ string }) -> number }

-- a blueprint by name (assets/worlds/<Name>.json) or by path -> build/worlds/<name>.json (flat parts + terrain +
-- objectives + zones + player + checks). Never writes src/world: checking is not building.
-- opts (optional): World.compile's (greybox = true: kit world greybox), and suffix: written as <name><suffix>.json
function WorldCmd.flatten(target: string, opts: any?): (Run.Step, string?)
	local path = if fs.isFile(target) then target else `{Config.path("worlds")}/{target}.json`
	if not fs.isFile(path) then
		return Run.step("world flatten", false, `no blueprint {path}`, {
			next_action = `create it: lune run kit new world {target}`,
		}),
			nil
	end
	local ok, bp = pcall(serde.decode, "json" :: any, fs.readFile(path))
	if not ok then
		return Run.step("world flatten", false, `{path}: invalid JSON`, { next_action = `fix the JSON in {path}` }), nil
	end
	local _, parts, issues, extras = World.compile(bp, opts)
	for _, issue in issues do
		if issue.severity == "error" then
			return Run.step("world flatten", false, `{issue.path}: {issue.message}`, {
				next_action = `fix {path}: {issue.path}: {issue.message}`,
			}),
				nil
		end
	end
	local flat = {}
	for _, p in parts do
		table.insert(flat, {
			name = p.name,
			size = p.size,
			pos = p.pos,
			rot = p.rot,
			color = p.color,
			transparency = p.transparency,
			shape = p.shape,
			spawn = p.spawn,
			class = p.class,
			collide = p.collide,
			material = p.material,
			backdrop = p.backdrop,
			mesh = p.mesh,
			meshCollide = p.meshCollide,
			children = p.children,
		})
	end
	Config.ensureDir(Config.build("worlds"))
	local out = Config.build("worlds")
		.. `/{bp.name}{if opts and type(opts.suffix) == "string" then opts.suffix else ""}.json`
	fs.writeFile(
		out,
		serde.encode("json", {
			name = bp.name,
			blueprint = path, -- (kit world check reads the blueprint's own design: worldcheck design_lint)
			parts = flat,
			terrain = World.terrainField(World.inSeason(bp), nil, extras and extras.bedsOf),
			season = if type(bp.season) == "string" then bp.season else nil, -- (the season this build is of)
			-- (the compiled lighting: kit world look lights its eye-level renders with it)
			lighting = (Environment.compile(World.inSeason(bp)) or {}).lighting,
			terrainColors = World.inSeason(bp).terrainColors,
			scans = bp.scans, -- (the viewer's per-world scan choice: { "<Material>": "<ambientCG id>" })
			paints = extras and extras.paints,
			landmarks = extras and extras.landmarks, -- (landmark guidance: kit world check)
			fits = extras and extras.fits, -- (the scale claims: kit world check holds them to the rig's sheet)
			-- (each "town" step's plan: streets, blocks, lots, the street graph's measures - kit world town draws it)
			towns = extras and extras.towns,
			scale = bp.scale, -- the sheet's name ("r6"): set, every claim must fit
			ambient = World.inSeason(bp).ambient,
			water = bp.water,
			objectives = bp.objectives,
			-- plain-word labels on the eye-level renders (kit world look: "labels": [{ "at": [x, y, z], "text" }]) - the
			-- owner, 2026-11-11, on an unlabelled frame: "I don't know what I'm exactly looking at"
			labels = bp.labels,
			-- named camera views kit world look also renders ("views": [{ "name", "at": [x, y, z], "target": [x, y, z] }]):
			-- what the spawns cannot show - inside a house you walk into
			views = bp.views,
			zones = bp.zones,
			player = bp.player,
			checks = bp.checks,
		})
	)
	-- (a decal that is not uploaded is left out of the built world: said here too, where warnings are not printed)
	local waiting = 0
	for _, d in (type(extras) == "table" and extras.decals) or {} do
		waiting += d.waiting
	end
	local left = if waiting > 0 then `; {waiting} decal(s) LEFT OUT: not uploaded` else ""
	return Run.step("world flatten", true, out, { summary = `{bp.name}: {#flat} part(s){left}` }), out
end

-- flatten + check as ONE step (selftest fixtures and kit verify use it)
function WorldCmd.checkStep(target: string): Run.Step
	local flat, out = WorldCmd.flatten(target)
	if not out then
		return flat
	end
	return Run.content(`world check {target}`, Run.tool("python"), { "kit/world/worldcheck.py", out :: string })
end

-- the look's size: every station 1920 x 1080 (960 x 540 until 2026-11-12, and 520 px wide on the sheet a session
-- judged from: board/plans/archive/2026-11-11-world-studio-route-plan.md, W0)
WorldCmd.LOOK_RES = "1920x1080"

-- where a world's reference stills (and their pairing with its stations: stations.json) live
function WorldCmd.refsDir(name: string): string
	return `{Config.path("worlds")}/refs/{name}`
end

-- the world's STATIONS rendered in Blender (kit/world/look_blender.py: every spawn behind the rig, the blueprint's
-- views, at each objective, from above - and stations.json, their cameras in Roblox's axes), labelled, and laid out
-- (kit/world/worldlook.py: ONE PAGE PER STATION beside its reference still + the index sheet).
-- -> (the steps, ok, the layout's verdict { summary, next_action, look, pages, ... }, the look folder, the name)
function WorldCmd.look(target: string, opts: any?): ({ Run.Step }, boolean, any, string?, string?)
	local flat, out = WorldCmd.flatten(target, opts)
	if not out then
		return { flat }, false, { summary = flat.tail, next_action = "fix the blueprint" }, nil, nil
	end
	local name = string.match(out :: string, "([^/]+)%.json$") :: string
	local dir = Config.build("worlds") .. "/look/" .. name
	local render = Run.content("world look (Blender)", Run.tool("blender"), {
		"-b",
		"--factory-startup",
		"--python-exit-code",
		"2",
		"-P",
		"kit/world/look_blender.py",
		"--",
		out :: string,
		dir,
		"--res",
		WorldCmd.LOOK_RES,
	})
	if not render.ok then
		return { flat, render },
			false,
			{ summary = "the render failed", next_action = "read the Blender output above" },
			dir,
			name
	end
	-- the blueprint's plain-word labels drawn on every shot (kit/world/frame_labels.py; the unlabelled one stays as
	-- <shot>.raw.png)
	local steps = { flat, render }
	for _, f in fs.readDir(dir) do
		local shot = string.match(f, "^(.+)%.labels%.json$") -- (every shot: the eyes and the establishing view)
		if shot then
			table.insert(
				steps,
				Run.content(
					`world look labels {shot}`,
					Run.tool("python"),
					{ "kit/world/frame_labels.py", `{dir}/{shot}.png`, `{dir}/{f}` }
				)
			)
		end
	end
	local sheet = Run.content("world look pages + sheet", Run.tool("python"), {
		"kit/world/worldlook.py",
		dir,
		name,
		"--refs",
		WorldCmd.refsDir(if opts and opts.base then opts.base else name),
	})
	table.insert(steps, sheet)
	return steps, sheet.ok, sheet.result or {}, dir, name
end

-- THE WORLD'S ROUTE STAGES (LIMITATIONS_FIXES_V3.md stage A.2-A.3: W1 the bible and the walked greybox, W2 one 40 x 40
-- corner): what the owner approves before a world is dressed in meshes and before it is scaled to whole streets
-- (kit approve world <Name> "<his words>" --by owner --stage greybox | corner; the lock: LaneLocks.worldStages)
local function bibleCmd(args: { string }): number
	local name = args[1]
	if not name then
		return Run.report(
			"world-bible",
			{},
			Run.CODES.USAGE,
			"world bible: which world?",
			"lune run kit world bible <Name>"
		)
	end
	local call = { "kit/world/bible.py", name, "--worlds", Config.path("worlds"), "--build", Config.build("worlds") }
	if table.find(args, "--write") then
		table.insert(call, "--write")
	end
	local step = Run.content("world bible", Run.tool("python"), call)
	local r = step.result or {}
	for _, problem in r.problems or {} do
		print("  " .. problem)
	end
	return Run.report(
		"world-bible",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world bible: {r.summary or "crashed"}`,
		r.next_action or "read the error above"
	)
end

local function greyboxCmd(args: { string }): number
	local name = args[1]
	if not name then
		return Run.report(
			"world-greybox",
			{},
			Run.CODES.USAGE,
			"world greybox: which world?",
			"lune run kit world greybox <Name>"
		)
	end
	-- the world WITH its meshes first (the bible's sightlines are read on it), then with none
	local built = WorldCmd.flatten(name)
	local bible = Run.content(
		"world bible",
		Run.tool("python"),
		{ "kit/world/bible.py", name, "--worlds", Config.path("worlds"), "--build", Config.build("worlds") }
	)
	if not built.ok then
		return Run.report(
			"world-greybox",
			{ built },
			Run.CODES.CONTENT,
			`world greybox: {name} does not compile - {built.tail}`,
			(built.result and built.result.next_action) or "fix the blueprint"
		)
	end
	local steps, ok, r = WorldCmd.look(name, { greybox = true, suffix = ".greybox", base = name })
	table.insert(steps, 1, built)
	table.insert(steps, 2, bible)
	local dir = `{Config.build("worlds")}/look/{name}.greybox`
	return Run.report(
		"world-greybox",
		steps,
		if ok and bible.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		if bible.ok
			then `world greybox: {name} with no mesh, at its stations - {r.summary or "rendered"}`
			else `world greybox: rendered, but the bible does not pass - {(bible.result or {}).summary or bible.tail}`,
		if bible.ok
			then `LOOK at {dir}/pages (the R6 rig in each frame), walk it in Studio with the owner (kit world studio {name}); his yes: lune run kit approve world {name} "<his words>" --by owner --stage greybox`
			else ((bible.result or {}).next_action or `lune run kit world bible {name}`)
	)
end

local function cornerCmd(args: { string }): number
	local name, at = args[1], nil
	for i, a in args do
		if a == "--at" then
			at = args[i + 1]
		end
	end
	if not name or not at then
		return Run.report(
			"world-corner",
			{},
			Run.CODES.USAGE,
			"world corner: which world, and at which station?",
			"lune run kit world corner <Name> --at <station> (the station names: build/worlds/look/<Name>/stations.json)"
		)
	end
	local step = Run.content("world corner (Blender)", Run.tool("python"), {
		"kit/world/corner.py",
		name,
		"--at",
		at,
		"--blender",
		Run.tool("blender"),
		"--build",
		Config.build("worlds"),
	})
	local r = step.result or {}
	return Run.report(
		"world-corner",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world corner: {r.summary or "crashed"}`,
		r.next_action or "read the error above"
	)
end

local function lookCmd(args: { string }): number
	local target = args[1]
	if not target then
		return Run.report(
			"world-look",
			{},
			Run.CODES.USAGE,
			"world look: which world?",
			"lune run kit world look <Name>"
		)
	end
	local steps, ok, r = WorldCmd.look(target)
	return Run.report(
		"world-look",
		steps,
		if ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world look: {r.summary or "no sheet"}`,
		r.next_action or "read the error above"
	)
end

-- how many worlds ONE build looks at by itself (each is a Blender run of about a minute); the rest are named
WorldCmd.BUILD_LOOKS = 2

-- when a file was last written (ms; 0: no such file)
function WorldCmd.mtime(path: string): number
	local ok, meta = pcall(fs.metadata, path)
	if ok and meta and meta.exists and meta.modifiedAt then
		return meta.modifiedAt.unixTimestampMillis
	end
	return 0
end

-- `file` was written before `than` was (both there): pictures older than the blueprint they show
function WorldCmd.olderThan(file: string, than: string): boolean
	return fs.isFile(file) and fs.isFile(than) and WorldCmd.mtime(file) < WorldCmd.mtime(than)
end

-- the lines a world build ends with (kit world): `LOOK: <folder> - what is in it`, one per world. A world this build
-- CHANGED is rendered here and now (the first BUILD_LOOKS of them: its stations beside their references, full size),
-- so no session builds a world and reads only its gates; an unchanged world's line points at the pictures it has,
-- or says it has none. A look that fails never fails the build: its line says why.
-- `changed`: the worlds whose compiled model this build wrote differently; `skip`: no render (--no-look).
function WorldCmd.buildLooks(names: { string }, changed: { string }, skip: boolean?): { string }
	local lines, kept = {}, {}
	local isChanged = {}
	for _, n in changed do
		isChanged[n] = true
	end
	-- a blueprint newer than its pictures is a change too: its views, labels and objectives are not in the compiled
	-- model, so the build itself cannot see them move
	for _, n in names do
		if
			WorldCmd.olderThan(`{Config.build("worlds")}/look/{n}/stations.json`, `{Config.path("worlds")}/{n}.json`)
		then
			isChanged[n] = true
		end
	end
	local rendered = 0
	local sorted = table.clone(names)
	table.sort(sorted)
	for _, n in sorted do
		local dir = Config.build("worlds") .. "/look/" .. n
		local pages = dir .. "/pages"
		local have = 0
		if fs.isDir(pages) then
			for _, f in fs.readDir(pages) do
				if string.sub(f, -4) == ".png" then
					have += 1
				end
			end
		end
		if isChanged[n] and not skip and rendered < WorldCmd.BUILD_LOOKS then
			rendered += 1
			local _, ok, r = WorldCmd.look(n)
			if ok and type(r.look) == "string" then
				table.insert(lines, `{r.look} [{n}: rendered by this build]`)
			else
				table.insert(
					lines,
					`LOOK: {dir}/ - NOT rendered for {n} ({r.summary or "the look failed"}): lune run kit world look {n}`
				)
			end
		elseif isChanged[n] then
			local state = if have > 0 then "from BEFORE the change" else "not made"
			table.insert(
				lines,
				`LOOK: {dir}/ - {n} changed since its pictures were made (they are {state}): lune run kit world look {n}`
			)
		elseif have > 0 then
			table.insert(
				kept,
				`LOOK: {pages}/ - {have} station page(s) of {n} (unchanged in this build), each its reference still above ours at full size`
			)
		end
	end
	for i = 1, math.min(#kept, 3) do -- (a project of thirty worlds: the changed ones first, three of the rest)
		table.insert(lines, kept[i])
	end
	for _, line in WorldCmd.townLooks(sorted) do
		table.insert(lines, line)
	end
	if #kept > 3 then
		table.insert(lines, `LOOK: {Config.build("worlds")}/look/ - and {#kept - 3} more world(s) with station pages`)
	end
	if #lines == 0 then
		table.insert(
			lines,
			`LOOK: {Config.build("worlds")}/ - only the top-down maps (<name>.png) of {#names} world(s); no eye-level look yet: lune run kit world look <Name>`
		)
	end
	return lines
end

-- a world with a "town" step ends its build on the town's PLAN PAGE too (kit/world/townplan.py): the streets, lots,
-- landmark and the walk from every gate, from above - the page a layout is read by, drawn at every build so no session
-- dresses a town it has not seen laid out. Read from the BLUEPRINT (a town step in its build list), never from a
-- compiled file: the build's own writer (kit/cmd/content.luau) and kit world check's (flatten, above) write that file
-- differently, and a line that hung on one of them was silent in every plain build (a fresh reader, 2026-11-13).
-- `targets`: world names or blueprint paths. At most TOWN_LOOKS pages a build (each compiles its world once more);
-- the rest are named. A page that fails never fails the build: its line says why.
WorldCmd.TOWN_LOOKS = 4

function WorldCmd.hasTown(path: string): boolean
	local ok, bp = pcall(function()
		return serde.decode("json" :: any, fs.readFile(path))
	end)
	if not ok or type(bp) ~= "table" or type(bp.build) ~= "table" then
		return false
	end
	for _, step in bp.build do
		if type(step) == "table" and type(step.town) == "table" then
			return true
		end
	end
	return false
end

function WorldCmd.townLooks(targets: { string }): { string }
	local lines, more = {}, {}
	local drawn = 0
	for _, t in targets do
		local path = if fs.isFile(t) then t else `{Config.path("worlds")}/{t}.json`
		if not fs.isFile(path) or not WorldCmd.hasTown(path) then
			continue
		end
		if drawn >= WorldCmd.TOWN_LOOKS then
			table.insert(more, t)
			continue
		end
		drawn += 1
		local was = Run.expectingFailure
		Run.expectingFailure = true -- (its steps are not the build's: only the LOOK line is printed)
		local okTown, steps, _, summary = pcall(WorldCmd.town, t)
		Run.expectingFailure = was
		local last = if okTown and type(steps) == "table" then steps[#steps] else nil
		local r = if last then last.result or {} else {}
		if last and last.ok and type(r.pages) == "table" and #r.pages > 0 then
			table.insert(
				lines,
				`LOOK: {r.pages[1]} - the plan of {t}'s town from above ({r.summary or "streets, lots, the landmark, the walk from every gate"}): read it before dressing`
			)
		else
			table.insert(
				lines,
				`LOOK: the plan page of {t}'s town was NOT drawn ({if okTown then tostring(summary) else tostring(steps)}): lune run kit world town {t}`
			)
		end
	end
	if #more > 0 then
		table.insert(
			lines,
			`LOOK: {#more} more town(s) have no plan page from this build ({table.concat(more, ", ")}): lune run kit world town <Name>`
		)
	end
	return lines
end

-- a world's SCRATCH PLACE for Roblox Studio (kit/lib/world.luau World.scratchModel / scratchProject): the world alone,
-- its hidden blockout shown as plain parts where a mesh skin would stand (nothing is uploaded), the kit's runtime
-- and a marker; built by rojo -> build/worlds/studio/<Name>/KitWorldScratch_<Name>.rbxlx. Never saved back, never
-- uploaded. `stationsPath`: the look's stations.json - the place's BUILD KEY is a digest of the world and those
-- stations (what a Studio capture is OF). -> (the step, the place file, the folder, the build key)
function WorldCmd.scratchPlace(bpPath: string, name: string, stationsPath: string?): (Run.Step, string, string, string)
	local dir = Config.build("worlds") .. "/studio/" .. name
	local place = `{dir}/{World.scratchName(name)}.rbxlx`
	local ok, bp = pcall(serde.decode, "json" :: any, fs.readFile(bpPath))
	if not ok then
		return Run.step("world scratch place", false, `{bpPath}: invalid JSON`, {
			next_action = `fix the JSON in {bpPath}`,
		}),
			place,
			dir,
			""
	end
	local model = World.compile(bp)
	if not model then
		return Run.step("world scratch place", false, `{bpPath} does not compile`, {
			next_action = `lune run kit world check {name}`,
		}),
			place,
			dir,
			""
	end
	Config.ensureDir(dir)
	local scratch, shown, skins = World.scratchModel(model)
	local modelText = serde.encode("json", scratch, true)
	fs.writeFile(`{dir}/{name}.model.json`, modelText)
	local key = serde.hash(
		"sha256",
		modelText .. (if stationsPath and fs.isFile(stationsPath) then fs.readFile(stationsPath) else "")
	)
	-- the kit's runtime as the project file sees it (a game carries its own copy; else the kit home's)
	local kitDir = if fs.isDir(Config.root() .. "src/kit")
		then Config.root() .. "src/kit"
		else (if fs.isDir("src/kit") then "src/kit" else nil)
	local up = string.rep("../", #string.split(dir, "/"))
	fs.writeFile(
		`{dir}/scratch.project.json`,
		serde.encode("json", World.scratchProject(name, if kitDir then up .. kitDir else nil, key), true)
	)
	local build = Run.spawn(
		"rojo build (the scratch place)",
		Run.tool("rojo"),
		{ "build", `{dir}/scratch.project.json`, "-o", place },
		true
	)
	if not build.ok then
		build.result = { next_action = "read the rojo output above (lune run kit doctor checks the tool)" }
		return build, place, dir, key
	end
	return Run.step("world scratch place", true, place, {
		summary = `{place}: {shown} hidden blockout part(s) shown as plain parts, {skins} mesh skin(s) not shown (nothing is uploaded)`,
		shown = shown,
		skins = skins,
	}),
		place,
		dir,
		key
end

-- what a Studio capture is OF: the scratch world and its stations as they stood when it was taken (<shots>/of.txt,
-- written after a capture). A capture of anything else is thrown away - an old Studio pane under a new Blender shot
-- would be a false pair, and nothing on the page could tell. -> how many old pictures went
function WorldCmd.dropStaleCapture(shots: string, key: string): number
	if not fs.isDir(shots) then
		return 0
	end
	local had = if fs.isFile(`{shots}/of.txt`) then fs.readFile(`{shots}/of.txt`) else ""
	if had == key then
		return 0
	end
	local gone = 0
	for _, f in fs.readDir(shots) do
		if string.sub(f, -4) == ".png" then
			fs.removeFile(`{shots}/{f}`)
			gone += 1
		elseif f == "capture.json" or f == "of.txt" then
			fs.removeFile(`{shots}/{f}`)
		end
	end
	return gone
end

-- kit world studio <Name>: the SAME stations as the Blender look, captured in Roblox Studio in the world's scratch
-- place, each laid under its reference still and its Blender shot: three panes a station (kit/world/lookpages.py).
-- The picture is taken by this command (kit/world/studio_shots.py reads the scratch place's own window); the camera
-- is moved by a script the session runs ONCE through the Studio tools (execute_luau): a kit command cannot reach
-- into Studio, and Studio's script cannot call out (its HTTP allowlist), so the script signals each station with a
-- plain colour over the 3D view. So: once without --capture (the place, the script, pages whose third pane says why
-- it is empty), and once with it, started BEFORE the script runs.
function WorldCmd.studio(args: { string }): ({ Run.Step }, number, string, string, any)
	local target = args[1]
	if not target or string.sub(target, 1, 2) == "--" then
		return {},
			Run.CODES.USAGE,
			"world studio: which world?",
			"lune run kit world studio <Name> [--capture] [--render] [--wait <seconds>]",
			nil
	end
	local wait: string? = nil
	local flags = {}
	for i = 2, #args do
		if args[i] == "--wait" and args[i + 1] then
			wait = args[i + 1]
		else
			flags[args[i]] = true
		end
	end
	local flat, out = WorldCmd.flatten(target)
	if not out then
		return { flat }, Run.CODES.CONTENT, `world studio: {flat.tail}`, "fix the blueprint", nil
	end
	local name = string.match(out :: string, "([^/]+)%.json$") :: string
	local bpPath = if fs.isFile(target) then target else `{Config.path("worlds")}/{target}.json`
	local lookDir = Config.build("worlds") .. "/look/" .. name
	local stationsPath = lookDir .. "/stations.json"
	local steps: { Run.Step } = { flat }
	-- 1. the stations: the Blender look, rendered again when the blueprint is newer than it (or --render)
	local fresh = not flags["--render"]
		and fs.isFile(stationsPath)
		and WorldCmd.mtime(stationsPath) >= WorldCmd.mtime(bpPath)
	if fresh then
		local okS, st = pcall(serde.decode, "json" :: any, fs.readFile(stationsPath))
		local res = if okS and type(st) == "table" and type(st.res) == "table" then `{st.res[1]}x{st.res[2]}` else ""
		fresh = res == WorldCmd.LOOK_RES
	end
	if fresh then
		print(`-- the Blender look in {lookDir} is newer than the blueprint: kept (--render makes it again)`)
	else
		local lookSteps, ok, r = WorldCmd.look(target)
		for i = 2, #lookSteps do -- (its first step is the flatten above)
			table.insert(steps, lookSteps[i])
		end
		if not ok then
			return steps,
				Run.CODES.CONTENT,
				`world studio: the Blender look failed ({r.summary or "no stations"})`,
				r.next_action or "read the error above",
				nil
		end
	end
	local okS, st = pcall(serde.decode, "json" :: any, fs.readFile(stationsPath))
	local stationNames = {}
	if okS and type(st) == "table" then
		for _, s in st.stations or {} do
			table.insert(stationNames, tostring(s.name))
		end
	end
	-- 2. the scratch place, and the script that walks it
	local placeStep, place, dir, key = WorldCmd.scratchPlace(bpPath, name, stationsPath)
	table.insert(steps, placeStep)
	if not placeStep.ok then
		return steps,
			Run.CODES.BUILD,
			"world studio: the scratch place did not build",
			(placeStep.result and placeStep.result.next_action) or "read the output above",
			nil
	end
	local script = `{dir}/capture.luau`
	local snippet = Run.content("world studio capture script", Run.tool("python"), {
		"kit/world/studio_shots.py",
		"snippet",
		stationsPath,
		script,
		"--world",
		name,
		"--build",
		key,
	})
	table.insert(steps, snippet)
	if not snippet.ok then
		return steps,
			Run.CODES.CONTENT,
			"world studio: no capture script",
			(snippet.result and snippet.result.next_action) or "read the error above",
			nil
	end
	local shots = `{dir}/shots`
	local match = World.scratchName(name)
	-- a capture of the world as it WAS is thrown away before anything is laid out
	local stale = WorldCmd.dropStaleCapture(shots, key)
	local howTo =
		`open {place} in Roblox Studio as its own window (RobloxStudioBeta.exe "<its full path>"; another place's Studio is never touched) and wait until the Studio tools list it, start \`lune run kit world studio {name} --capture\` in the background, then run {script} ONCE through the Studio tools (execute_luau, the Edit datamodel, that window's studio_id); close that window afterwards without saving`
	-- 3. the capture: wait for the script's walk (the session runs it in Studio while this waits)
	local why: string? = nil
	if flags["--capture"] then
		-- (as long as the walk takes - what the script itself says - and three minutes for the session to start it)
		local walk = if snippet.result and type(snippet.result.seconds) == "number" then snippet.result.seconds else 60
		wait = wait or tostring(walk + 180)
		print(
			`-- watching the scratch place's window for up to {wait} s (the walk takes about {walk} s): run {script} ONCE through the Studio tools there NOW`
		)
		local capture = Run.content("world studio capture (Roblox Studio)", Run.tool("python"), {
			"kit/world/studio_shots.py",
			"watch",
			shots,
			"--match",
			match,
			"--world",
			name,
			"--stations",
			table.concat(stationNames, ","),
			"--wait",
			wait :: string,
		})
		capture.ok = true -- (a walk that did not happen is not a failed command: the pages say why, in words)
		table.insert(steps, capture)
		why = capture.result and capture.result.why
		if fs.isFile(`{shots}/capture.json`) then
			fs.writeFile(`{shots}/of.txt`, key)
		end
	else
		-- no capture asked: say what Studio is doing, so an empty pane gives its real reason
		local seen = Run.spawn(
			"studio windows",
			Run.tool("python"),
			{ "kit/world/studio_shots.py", "windows", "--match", match },
			true
		)
		local r = seen.result or {}
		if not fs.isFile(`{shots}/capture.json`) then
			why = if r.open
				then "the scratch place is open in Roblox Studio but no capture was run"
				else (if type(r.why) == "string" then r.why else "no capture was run")
			if stale > 0 then
				why =
					`the world or its stations changed after the last Studio capture ({stale} old picture(s) thrown away); {why}`
			end
		end
	end
	-- 4. the pages: reference, Blender, Studio
	local argv = { "kit/world/lookpages.py", lookDir, name, "--refs", WorldCmd.refsDir(name), "--studio", dir }
	if why then
		table.insert(argv, "--studio-why")
		table.insert(argv, why)
	end
	local pages = Run.content("world studio pages", Run.tool("python"), argv)
	table.insert(steps, pages)
	local r = pages.result or {}
	local captured = if type(r.captured) == "number" then r.captured else 0
	local all = pages.ok and captured == #stationNames and #stationNames > 0
	return steps,
		if pages.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world studio: {r.summary or "no pages"}{if why then ` - Studio pane: {why}` else ""}`,
		if not pages.ok
			then (r.next_action or "read the error above")
			elseif all then tostring(r.look)
			else `{tostring(r.look)}; to capture Studio: {howTo}`,
		r
end

local function studioCmd(args: { string }): number
	local steps, code, summary, nextAction = WorldCmd.studio(args)
	return Run.report("world-studio", steps, code, summary, nextAction)
end

-- `kit world studio` on a fixture as ONE step (kit selftest): with no Studio walk the pages must still be made, three
-- panes a station, the Studio pane saying why it is empty - and a capture planted from another build (`plant`)
-- must be thrown away, never shown; `stations`: how many stations the fixture has (a page each). ok only when all
-- of that holds.
function WorldCmd.studioStep(target: string, plant: boolean?, stations: number?): Run.Step
	local planted = 0
	if plant then
		local name = string.match(target, "([^/]+)%.json$") or target
		local okB, bp = pcall(serde.decode, "json" :: any, fs.readFile(target))
		if okB and type(bp) == "table" and type(bp.name) == "string" then
			name = bp.name
		end
		local shots = Config.build("worlds") .. "/studio/" .. name .. "/shots"
		Config.ensureDir(shots)
		fs.writeFile(shots .. "/eye_1.png", "a capture of another build")
		fs.writeFile(shots .. "/capture.json", "{}")
		fs.writeFile(shots .. "/of.txt", "another build")
		planted = 1
	end
	local steps, code, summary, nextAction, r = WorldCmd.studio({ target })
	local problems = {}
	if code ~= Run.CODES.PASS then
		table.insert(problems, summary)
	else
		if type(r) ~= "table" or type(r.pages) ~= "table" or #r.pages == 0 then
			table.insert(problems, "no pages")
		else
			for _, p in r.pages do
				if not fs.isFile(p) then
					table.insert(problems, `{p} is missing`)
				end
			end
			if stations and #r.pages ~= stations then
				table.insert(problems, `{#r.pages} station page(s), the fixture has {stations} stations`)
			end
			if r.captured ~= 0 then
				table.insert(problems, `{tostring(r.captured)} Studio pane(s) shown with no capture of this build`)
			end
			if type(r.look) ~= "string" or string.sub(r.look, 1, 6) ~= "LOOK: " then
				table.insert(problems, "no LOOK line")
			end
		end
		if not string.find(summary, "Studio pane: ", 1, true) then
			table.insert(problems, "an empty Studio pane gives no reason")
		end
		if planted > 0 and not string.find(summary, "changed after the last Studio capture", 1, true) then
			table.insert(problems, "a capture of another build was not thrown away")
		end
	end
	local ok = #problems == 0
	return {
		name = `world studio {target}`,
		cmd = "(in-process)",
		exit = if ok then 0 else 1,
		ok = ok,
		tail = if ok then summary else table.concat(problems, "; "),
		result = {
			status = if ok then "pass" else "fail",
			summary = if ok then summary else table.concat(problems, "; "),
			next_action = if ok then nextAction else "fix kit world studio (kit/cmd/world.luau), never the fixture",
			steps = #steps,
		},
	}
end

local function terrainCmd(args: { string }): number
	local name = args[1]
	if not name or string.sub(name, 1, 2) == "--" then
		return Run.report(
			"world-terrain",
			{},
			Run.CODES.USAGE,
			"world terrain: which world?",
			"lune run kit world terrain <Name> [--size 512 --seed 3 --relief 60 --erosion 60000 --from <image> --flat x,z,r --stamp kind,x,z,radius,height --climate wind=270,rain=0.6]"
		)
	end
	local out = `{Config.path("terrain")}/{name}.hm.json`
	local pass = table.pack(table.unpack(args, 2))
	for i = 1, pass.n - 1 do -- (file flags are written as the game sees them: relative to games/<Name>/)
		if pass[i] == "--design" or pass[i] == "--from" or pass[i] == "--imagery" then
			pass[i + 1] = Config.resolve(pass[i + 1])
		end
	end
	local step =
		Run.content("world terrain", Run.tool("python"), { "kit/world/terrain.py", out, table.unpack(pass, 1, pass.n) })
	local r = step.result or {}
	return Run.report(
		"world-terrain",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world terrain: {r.summary or "crashed"}`,
		r.next_action or "read the error above"
	)
end

local function webCmd(args: { string }): number
	local target = args[1]
	if not target then
		return Run.report("world-web", {}, Run.CODES.USAGE, "world web: which world?", "lune run kit world web <Name>")
	end
	local flat, out = WorldCmd.flatten(target)
	if not out then
		return Run.report("world-web", { flat }, Run.CODES.CONTENT, `world web: {flat.tail}`, "fix the blueprint")
	end
	local name = string.match(out :: string, "([^/]+)%.json$") :: string
	local page = Config.build("worlds") .. `/web/{name}.html`
	local step = Run.content("world web", Run.tool("python"), { "kit/world/web.py", out :: string, page })
	local r = step.result or {}
	return Run.report(
		"world-web",
		{ flat, step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world web: {r.summary or "crashed"}`,
		r.next_action or "read the error above"
	)
end

local function shotsCmd(args: { string }): number
	local target = args[1]
	if not target then
		return Run.report(
			"world-shots",
			{},
			Run.CODES.USAGE,
			"world shots: which world?",
			"lune run kit world shots <Name>"
		)
	end
	local flat, out = WorldCmd.flatten(target)
	if not out then
		return Run.report("world-shots", { flat }, Run.CODES.CONTENT, `world shots: {flat.tail}`, "fix the blueprint")
	end
	local name = string.match(out :: string, "([^/]+)%.json$") :: string
	local page = Config.build("worlds") .. `/web/{name}.html`
	local web = Run.content("world web", Run.tool("python"), { "kit/world/web.py", out :: string, page })
	if not web.ok then
		return Run.report(
			"world-shots",
			{ flat, web },
			Run.CODES.CONTENT,
			"world shots: the page failed",
			"read the output above"
		)
	end
	local shots = Run.content(
		"world shots",
		Run.tool("python"),
		{ "kit/world/shots.py", page, Config.build("worlds") .. `/shots/{name}` }
	)
	local r = shots.result or {}
	return Run.report(
		"world-shots",
		{ flat, web, shots },
		if shots.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world shots: {r.summary or "crashed"}`,
		r.next_action or "read the error above"
	)
end

local function galleryCmd(_args: { string }): number
	local step = Run.content("world gallery", Run.tool("python"), { "kit/world/gallery.py", "build/worlds/gallery" })
	local r = step.result or {}
	return Run.report(
		"world-gallery",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world gallery: {r.summary or "crashed"}`,
		r.next_action or "read the error above"
	)
end

-- A SKY OF THE KIT'S OWN: six square pictures rendered in Blender (kit/world/sky_blender.py) -> build/skies/
local function skyCmd(args: { string }): number
	local USE =
		"lune run kit world sky <Name> [--sun <elevation>,<azimuth>] [--clouds 0..1] [--seed n] [--size 256|512|1024] [--ridges 0..3] [--ridge-height 2..25]"
	local name = args[1]
	if not name or not string.match(name, "^[%w_]+$") then
		return Run.report("world-sky", {}, Run.CODES.USAGE, "world sky: which sky? (its name: letters, digits, _)", USE)
	end
	local out = Config.build("skies")
	Config.ensureDir(out)
	local run: { string } = {
		"-b",
		"--factory-startup",
		"--python-exit-code",
		"2",
		"-P",
		"kit/world/sky_blender.py",
		"--",
		out,
		"--name",
		name,
	}
	for i = 2, #args do
		if args[i] == "--name" then -- (the sky's name is the first word: a second one would make another sky)
			return Run.report(
				"world-sky",
				{},
				Run.CODES.USAGE,
				"world sky: the sky's name is the first word, not --name",
				USE
			)
		end
		table.insert(run, args[i])
	end
	local step = Run.content(`sky {name}`, Run.tool("blender"), run)
	return Run.report(
		"world-sky",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		if step.ok then `world sky: {name}: six pictures -> {out}` else `world sky: {name} was not made`,
		if step.ok
			then `LOOK at {out}/{name}_ft.png and the five others; name it in the world's lighting: "sky": "{name}" - it is in a game only once the six are uploaded`
			else "read the step's last line above"
	)
end

-- A DECAL'S PICTURE (kit/world/decals.py): a leak, a stain, a crack, moss or soot made by rule, its border clear
-- -> build/decals/<Name>.png + <Name>.decal.json; a world's "decal" step lays it (kit/lib/worlddecal.luau)
local function decalCmd(args: { string }): number
	local USE =
		"lune run kit world decal <Name> --kind leak|stain|crack|moss|soot [--seed n] [--size 256|512|1024] [--tint r,g,b]"
	local name = args[1]
	if not name or not string.match(name, "^[%w_]+$") then
		return Run.report(
			"world-decal",
			{},
			Run.CODES.USAGE,
			"world decal: which decal? (its name: letters, digits, _)",
			USE
		)
	end
	local out = Config.build("decals")
	Config.ensureDir(out)
	local run: { string } = { "kit/world/decals.py", "make", out, "--name", name }
	for i = 2, #args do
		if args[i] == "--name" then -- (the decal's name is the first word: a second one would make another decal)
			return Run.report(
				"world-decal",
				{},
				Run.CODES.USAGE,
				"world decal: the decal's name is the first word, not --name",
				USE
			)
		end
		table.insert(run, args[i])
	end
	local step = Run.content(`decal {name}`, Run.tool("python"), run)
	local r = step.result or {}
	return Run.report(
		"world-decal",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world decal: {r.summary or "crashed"}`,
		if step.ok
			then `LOOK at {out}/{name}.png; lay it in a world with a "decal" build step ("name": "{name}", "at", "size", "facing") - it is in a game only once it is uploaded`
			else (r.next_action or "read the error above")
	)
end

-- POINTS OVER A MESH'S SURFACE, by Geometry Nodes (kit/world/gnscatter_blender.py): the mesh kit world meshes made
-- -> build/worldmeshes/<mesh>.on.<name>.json; a mesh step sets things down on them ("on": { "points": "<name>" })
local function scatterOnCmd(args: { string }): number
	local USE =
		"lune run kit world scatter-on <mesh> --as <name> --gap <studs> [--facing up|side|down|any] [--steep 0.5] [--seed 1] [--most 400]"
	local mesh = args[1]
	if not mesh or string.sub(mesh, 1, 2) == "--" then
		return Run.report("world-scatter-on", {}, Run.CODES.USAGE, "world scatter-on: which mesh?", USE)
	end
	local name: string? = nil
	local pass: { string } = {}
	local i = 2
	while i <= #args do
		if args[i] == "--as" then
			name = args[i + 1]
			i += 2
		else
			table.insert(pass, args[i])
			i += 1
		end
	end
	if not string.match(mesh, "^[%w_%-]+$") then
		return Run.report(
			"world-scatter-on",
			{},
			Run.CODES.USAGE,
			`world scatter-on: "{mesh}" is no mesh's name (letters, digits, _ and -; no path)`,
			USE
		)
	end
	if not name or not string.match(name, "^[%w_]+$") then
		return Run.report(
			"world-scatter-on",
			{},
			Run.CODES.USAGE,
			"world scatter-on: --as <name> says what the points are called (letters, digits, _)",
			USE
		)
	end
	local out = Config.build("worldmeshes")
	local source = `{out}/{mesh}.mesh.json`
	if not fs.isFile(source) then
		return Run.report(
			"world-scatter-on",
			{},
			Run.CODES.USAGE,
			`world scatter-on: no world mesh "{mesh}" in {out}`,
			"make it first: lune run kit world meshes"
		)
	end
	local target = `{out}/{mesh}.on.{name}.json`
	local run: { string } = {
		"-b",
		"--factory-startup",
		"--python-exit-code",
		"2",
		"-P",
		"kit/world/gnscatter_blender.py",
		"--",
		source,
		target,
	}
	for _, word in pass do
		table.insert(run, word)
	end
	local step = Run.content(`scatter-on {mesh}`, Run.tool("blender"), run)
	return Run.report(
		"world-scatter-on",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		if step.ok
			then `world scatter-on: points "{name}" on {mesh} -> {target}`
			else `world scatter-on: no points made on {mesh}`,
		if step.ok
			then `name them in the mesh's step: "on": \{ "points": "{name}", "part": \{ "size": [1, 0.4, 1], "mat": "<palette>" } }`
			else "read the step's last line above"
	)
end

-- every recipe in assets/worlds/meshes/*.json -> build/worldmeshes/ (one Blender process per asset: re-initialising
-- the renderer in one process crashed the GPU driver here)
local function meshesCmd(args: { string }): number
	local dir = Config.path("worlds") .. "/meshes"
	if not fs.isDir(dir) then
		return Run.report(
			"world-meshes",
			{},
			Run.CODES.USAGE,
			`world meshes: no recipes in {dir}`,
			`write {dir}/<set>.json: [\{ "name": "oak_a", "kind": "tree", ... \}] (kinds: kit/world/meshes_blender.py)`
		)
	end
	-- [<name>] = that one recipe; --set <file name without .json> = that recipe list only (a town's kit of houses:
	-- kit world town <Name> --kit writes town_<Name>.json)
	local only: string?, set: string? = nil, nil
	do
		local k = 1
		while k <= #args do
			if args[k] == "--set" then
				local value = args[k + 1]
				if not value or string.sub(value, 1, 2) == "--" then
					-- (with no name every list would be built: a town's 30 meshes asked for, the whole folder made)
					return Run.report(
						"world-meshes",
						{},
						Run.CODES.USAGE,
						"world meshes: --set needs a recipe list's name",
						`lune run kit world meshes --set <list> (a file {dir}/<list>.json)`
					)
				end
				set = value
				k += 2
			else
				if string.sub(args[k], 1, 2) ~= "--" then
					only = only or args[k]
				end
				k += 1
			end
		end
	end
	local out = Config.build("worldmeshes")
	Config.ensureDir(out)
	local steps, made = {}, 0
	for _, f in fs.readDir(dir) do
		if string.sub(f, -5) == ".json" and (not set or f == set .. ".json") then
			local ok, recipes = pcall(serde.decode, "json" :: any, fs.readFile(`{dir}/{f}`))
			if not ok or type(recipes) ~= "table" then
				table.insert(steps, Run.step(`recipes {f}`, false, "not a JSON list of recipes", {}))
				continue
			end
			for _, r in recipes do
				if only and r.name ~= only then
					continue
				end
				local step = Run.content(`mesh {r.name}`, Run.tool("blender"), {
					"-b",
					"--factory-startup",
					"--python-exit-code",
					"2",
					"-P",
					"kit/world/meshes_blender.py",
					"--",
					`{dir}/{f}`,
					out,
					"--only",
					r.name,
					-- (the world meshes already uploaded: a tree among them is not asked how its wood grows)
					"--ids",
					Config.path("ids"),
				})
				table.insert(steps, step)
				if step.ok then
					made += 1
				end
			end
		end
	end
	if set and #steps == 0 then
		-- (a list that is not there, or holds no recipe of that name, is not "0 made, all well")
		return Run.report(
			"world-meshes",
			{},
			Run.CODES.USAGE,
			`world meshes: no recipe to make in {dir}/{set}.json{if only then ` named "{only}"` else ""}`,
			`the lists are {dir}/*.json; a town's is written by: lune run kit world town <Name> --kit`
		)
	end
	local failed = #steps - made
	return Run.report(
		"world-meshes",
		steps,
		if failed == 0 then Run.CODES.PASS else Run.CODES.CONTENT,
		`world meshes: {made} made{if failed > 0 then `, {failed} failed` else ""} -> {out}`,
		if failed == 0
			then `LOOK at {out}/<name>.preview.png; then lune run kit upload (meshes + atlases) and lune run kit world (placeholders get their ids)`
			else "read the failing step above"
	)
end

-- vetted downloaded models (glTF: Poly Haven scans, Quaternius, ...) -> world meshes: every list in
-- <worlds>/imports/<set>.json (kit/world/import_blender.py: split sets, decimate to fit, real PNG textures)
-- REAL land: a bounding box of USGS 3DEP elevation (public domain, VETLOG) -> <terrain>/<Name>.dem.tif + .json;
-- a design then says "dem": { "file": "<Name>.dem.tif", "vexag": 1, "blur": 1 } (kit/world/dem.py)
-- water in the carved valleys (AAA gap W6): the heightmap's biggest drainage painted as the "river" role (-> Water)
-- a DIRECTION / MOOD frame from the kit's real pieces (kit/world/frame_blender.py): a scene JSON -> a GPU render
local function frameCmd(args: { string }): number
	local scenePath = args[1]
	if not scenePath or not fs.isFile(scenePath) then
		return Run.report(
			"world-frame",
			{},
			Run.CODES.USAGE,
			"world frame: which scene?",
			"lune run kit world frame <worlds>/direction/<Piece>_<X>.frame.json [--out <png>] [--samples 96]"
		)
	end
	local out = string.gsub(scenePath, "%.frame%.json$", ".png")
	local outIx = table.find(args, "--out")
	if outIx and args[outIx + 1] then
		out = args[outIx + 1]
	end
	local sIx = table.find(args, "--samples")
	local samples = if sIx and args[sIx + 1] then args[sIx + 1] else "96"
	local step = Run.content("world frame", Run.tool("blender"), {
		"-b",
		"--factory-startup",
		"--python-exit-code",
		"2",
		"-P",
		"kit/world/frame_blender.py",
		"--",
		scenePath,
		out,
		samples,
	})
	local r = step.result or {}
	-- the scene's plain-word labels on the render (kit/world/frame_labels.py; the unlabelled one stays as .raw.png):
	-- the owner on an unlabelled test frame, 2026-11-11: "I don't know what I'm exactly looking at"
	local labelsPath = string.gsub(out, "%.png$", "") .. ".labels.json"
	if step.ok and fs.isFile(labelsPath) then
		local tags =
			Run.content("world frame labels", Run.tool("python"), { "kit/world/frame_labels.py", out, labelsPath })
		local t = tags.result or {}
		return Run.report(
			"world-frame",
			{ step, tags },
			if tags.ok then Run.CODES.PASS else Run.CODES.CONTENT,
			`world frame: {r.summary or "crashed"}; {t.summary or "the labels failed"}`,
			t.next_action or "read the error above"
		)
	end
	return Run.report(
		"world-frame",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world frame: {r.summary or "crashed"}`,
		r.next_action or "read the error above"
	)
end

-- the world's COLOUR SCRIPT (kit/world/colorscript.py): every place's mood in journey order (value, warmth, palette)
local function colorscriptCmd(args: { string }): number
	local game = Config.game()
	if not game then
		return Run.report(
			"world-colorscript",
			{},
			Run.CODES.USAGE,
			"world colorscript: which game?",
			"lune run kit world colorscript --game <Name> [--order A,B,C]"
		)
	end
	local argv = { "kit/world/colorscript.py", game :: string }
	for _, a in args do
		table.insert(argv, a)
	end
	local step = Run.content("world colorscript", Run.tool("python"), argv)
	local r = step.result or {}
	return Run.report(
		"world-colorscript",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world colorscript: {r.summary or "crashed"}`,
		r.next_action or "read the error above"
	)
end

-- the owner's REVIEW BOARD of this game's world directions (kit/direction_page.py): one page, frames side by side
local function boardCmd(_args: { string }): number
	local game = Config.game()
	if not game then
		return Run.report(
			"world-board",
			{},
			Run.CODES.USAGE,
			"world board: which game?",
			"lune run kit world board --game <Name>"
		)
	end
	local step =
		Run.content("world board", Run.tool("python"), { "kit/direction_page.py", game :: string, "--lane", "world" })
	local r = step.result or {}
	return Run.report(
		"world-board",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world board: {r.summary or "crashed"}`,
		r.next_action or "read the error above"
	)
end

-- DIRECTION before an original piece of the world (kit/direction.py): <worlds>/direction/<Piece>.md with its frames
local function directionCmd(args: { string }): number
	local name = args[1]
	if not name or string.sub(name, 1, 2) == "--" then
		return Run.report(
			"world-direction",
			{},
			Run.CODES.USAGE,
			"world direction: which piece?",
			"lune run kit world direction <Piece> [--new]"
		)
	end
	local doc = `{Config.path("worlds")}/direction/{name}.md`
	local step = Run.content("world direction", Run.tool("python"), {
		"kit/direction.py",
		if table.find(args, "--new") then "new" else "check",
		doc,
		"--lane",
		"world",
		"--name",
		name,
	})
	local r = step.result or {}
	return Run.report(
		"world-direction",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world direction: {r.summary or "crashed"}`,
		r.next_action or "read the error above"
	)
end

local function riversCmd(args: { string }): number
	local name = args[1]
	if not name or string.sub(name, 1, 2) == "--" then
		return Run.report(
			"world-rivers",
			{},
			Run.CODES.USAGE,
			"world rivers: which world?",
			"lune run kit world rivers <Name> [--share 0.012] [--wide 0.0025]"
		)
	end
	local hm = `{Config.path("terrain")}/{name}.hm.json`
	if not fs.isFile(hm) then
		return Run.report(
			"world-rivers",
			{},
			Run.CODES.USAGE,
			`world rivers: no heightmap {hm}`,
			`make the terrain first: lune run kit world terrain {name}`
		)
	end
	local wantRibbons = table.find(args, "--ribbons") ~= nil
	local passOn = {}
	for i = 2, #args do
		if args[i] ~= "--ribbons" then
			table.insert(passOn, args[i])
		end
	end
	local step = Run.content("world rivers", Run.tool("python"), { "kit/world/rivers.py", hm, table.unpack(passOn) })
	if step.ok and wantRibbons then
		-- the rivers as RIBBON meshes that drain into the land's --sink basins (kit/world/ribbons.py; V4 5.1): a
		-- river through a closed hollow no sink drains fails here
		local rstep = Run.content("world ribbons", Run.tool("python"), { "kit/world/ribbons.py", hm })
		local rr = rstep.result or {}
		return Run.report(
			"world-rivers",
			{ step, rstep },
			if rstep.ok then Run.CODES.PASS else Run.CODES.CONTENT,
			`world rivers: {(step.result or {}).summary or "painted"}; ribbons: {rr.summary or "crashed"}`,
			rr.next_action or "read the error above"
		)
	end
	local r = step.result or {}
	return Run.report(
		"world-rivers",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world rivers: {r.summary or "crashed"}`,
		r.next_action or "read the error above"
	)
end

-- W5 (LIMITATIONS_FIXES_V4 5.4 step 4): a world in one of the five Realistic night-city presets with its shadow
-- lamps picked under the budget (kit/lib/worldlight.luau) -> a scratch copy of its blueprint (build/worlds/light/)
-- compiled to build/worlds/<Name>_light.json; the blueprint itself is never written
local function lightCmd(args: { string }): number
	local WorldLight = require("../lib/worldlight")
	local name = args[1]
	local preset, most = "gothic_moonlit", WorldLight.MOST
	for i = 2, #args do
		if args[i] == "--preset" and args[i + 1] then
			preset = args[i + 1]
		elseif args[i] == "--most" and args[i + 1] then
			most = tonumber(args[i + 1]) or -1
		end
	end
	local usage = `lune run kit world light <Name> [--preset {table.concat(WorldLight.NAMES, "|")}] [--most 16]`
	if not name or string.sub(name, 1, 2) == "--" then
		return Run.report("world-light", {}, Run.CODES.USAGE, "world light: which world?", usage)
	end
	if not WorldLight.PRESETS[preset] then
		return Run.report("world-light", {}, Run.CODES.USAGE, `world light: no preset "{preset}"`, usage)
	end
	local src = if fs.isFile(name) then name else `{Config.path("worlds")}/{name}.json`
	if not fs.isFile(src) then
		return Run.report("world-light", {}, Run.CODES.USAGE, `world light: no blueprint {src}`, usage)
	end
	local ok, bp = pcall(serde.decode, "json" :: any, fs.readFile(src))
	if not ok or type(bp) ~= "table" then
		return Run.report("world-light", {}, Run.CODES.USAGE, `world light: {src} is not JSON`, `fix {src}`)
	end
	-- (the world's own overrides of its light - a sky, a clock - give way to the preset's whole look)
	bp.lighting = if type(bp.lighting) == "table" and bp.lighting.sky
		then { preset = preset, sky = bp.lighting.sky }
		else preset
	bp.shadows = { most = most }
	local dir = Config.build("worlds/light")
	if not fs.isDir(dir) then
		fs.writeDir(dir)
	end
	local copy = `{dir}/{bp.name or "World"}.{preset}.json`
	fs.writeFile(copy, serde.encode("json", bp, true))
	local step, out = WorldCmd.flatten(copy, { suffix = "_light" })
	if not step.ok or not out then
		return Run.report(
			"world-light",
			{ step },
			Run.CODES.CONTENT,
			`world light: {step.summary}`,
			step.next_action or "read the error above"
		)
	end
	local flat = serde.decode("json", fs.readFile(out))
	local lamps, chosen = {}, {}
	for _, p in flat.parts or {} do
		for _, c in p.children or {} do
			if c.kind == "light" and type(c.spec) == "table" then
				table.insert(
					lamps,
					{ x = p.pos[1], z = p.pos[3], range = c.spec.range or 16, brightness = c.spec.brightness or 2 }
				)
				if c.spec.shadows == true then
					table.insert(chosen, #lamps)
				end
			end
		end
	end
	local worst = WorldLight.worst(lamps, chosen, World.SHADOW_REACH)
	local good = worst <= most and (#lamps == 0 or #chosen > 0)
	return Run.report(
		"world-light",
		{ step },
		if good then Run.CODES.PASS else Run.CODES.CONTENT,
		`world light: {bp.name} in {preset} (LightingStyle Realistic): {#chosen} of {#lamps} lamps cast shadows, at most {worst} within {World.SHADOW_REACH} studs of one (the budget {most}) -> {out}`,
		if good
			then `LOOK in Studio (the owner judges the light): load {out}'s world in a scratch place with the preset, walk it at night; the other presets: {table.concat(
				WorldLight.NAMES,
				", "
			)}`
			else 'lower --most or give lamps "shadows": false'
	)
end

local function demCmd(args: { string }): number
	local name = args[1]
	if not name or string.sub(name, 1, 2) == "--" then
		return Run.report(
			"world-dem",
			{},
			Run.CODES.USAGE,
			"world dem: which name?",
			"lune run kit world dem <Name> --bbox lon0,lat0,lon1,lat1 [--size 512]"
		)
	end
	local out = `{Config.path("terrain")}/{name}.dem.tif`
	Config.ensureDir(Config.path("terrain"))
	local step = Run.content(
		"world dem",
		Run.tool("python"),
		{ "kit/world/dem.py", "fetch", "--out", out, table.unpack(args, 2) }
	)
	local r = step.result or {}
	return Run.report(
		"world-dem",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world dem: {r.summary or "crashed"}`,
		r.next_action or "read the error above"
	)
end

-- REAL GROUND COVER: an aerial picture of a box (USDA NAIP through the USGS National Map, public domain: VETLOG.md)
-- -> <terrain>/<Name>.img.png + its sidecar; kit world terrain <Name> ... --imagery reads it as the painter's roles
local function imageryCmd(args: { string }): number
	local name = args[1]
	if not name or string.sub(name, 1, 2) == "--" then
		return Run.report(
			"world-imagery",
			{},
			Run.CODES.USAGE,
			"world imagery: which name?",
			"lune run kit world imagery <Name> --bbox lon0,lat0,lon1,lat1 [--size 512]  (the same box as its kit world dem)"
		)
	end
	local out = `{Config.path("terrain")}/{name}.img.png`
	Config.ensureDir(Config.path("terrain"))
	local step = Run.content(
		"world imagery",
		Run.tool("python"),
		{ "kit/world/imagery.py", "fetch", "--out", out, table.unpack(args, 2) }
	)
	local r = step.result or {}
	return Run.report(
		"world-imagery",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world imagery: {r.summary or "crashed"}`,
		r.next_action or "read the error above"
	)
end

-- a REAL thing photographed -> a world mesh at its real size (the 3D lane's photogrammetry route, kit/tools/photoscan.py,
-- read from the main checkout when this one has none)
local function scanCmd(args: { string }): number
	local name = args[1]
	if not name or string.sub(name, 1, 2) == "--" then
		return Run.report(
			"world-scan",
			{},
			Run.CODES.USAGE,
			"world scan: which name?",
			"lune run kit world scan <Name> --from <photos folder> --size <metres> [--axis height|length|width] [--quality low|medium|high]"
		)
	end
	local argv = { "kit/world/scan_world.py", table.unpack(args) }
	-- (the folders from the kit's config: the active game's build when one is active - where the compiler and kit upload
	-- read world meshes)
	for _, extra in
		{
			"--meshes",
			Config.build("worldmeshes"),
			"--scans",
			Config.build("worldscans"),
			"--work",
			`{Config.build("scan")}/{name}`,
		}
	do
		table.insert(argv, extra)
	end
	local step = Run.content("world scan", Run.tool("python"), argv)
	local r = step.result or {}
	return Run.report(
		"world-scan",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world {r.summary or "scan: crashed"}`,
		r.next_action or "read the error above"
	)
end

-- the scans as Roblox MaterialVariant maps: build/terrainmaps/<scan>__<color|normal|roughness>.png + terrainmaps.json
-- (kit upload -> ids.terrainmaps; kit world then writes the variants into MaterialService)
local function materialsCmd(args: { string }): number
	local step = Run.content(
		"world materials",
		Run.tool("python"),
		{ "kit/world/terrainmaps.py", Config.build("terrainmaps"), table.unpack(args, 1) }
	)
	local r = step.result or {}
	return Run.report(
		"world-materials",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world materials: {r.summary or "crashed"}`,
		r.next_action or "read the error above"
	)
end

-- ONE world's route, stage by stage, from the game's own files (kit/world/plan.py): refs -> terrain -> materials ->
-- meshes -> dressing -> check -> look -> studio -> verdict; the first stage not done gets its commands
-- the world's REFERENCES measured (kit/world/refs.py): <worlds>/refs/<Name>/*.png|jpg -> REFS.md + the identity
-- <worlds>/identities/<name>.json; --vs <render> = one difference + one edit against it (no score)
local function refsCmd(args: { string }): number
	local name = args[1]
	if not name or string.sub(name, 1, 2) == "--" then
		return Run.report(
			"world-refs",
			{},
			Run.CODES.USAGE,
			"world refs: which world?",
			"lune run kit world refs <Name> [--vs <render.png>]"
		)
	end
	local dir = `{Config.path("worlds")}/refs/{name}`
	local ident = `{Config.path("worlds")}/identities/{string.lower(name)}.json`
	local argv = { "kit/world/refs.py", dir, ident, "--name", name }
	for i, a in args do
		if a == "--vs" and args[i + 1] then
			argv = { "kit/world/refs.py", "--vs", Config.resolve(args[i + 1]), ident }
		end
	end
	local step = Run.content("world refs", Run.tool("python"), argv)
	local r = step.result or {}
	return Run.report(
		"world-refs",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world refs: {r.summary or "crashed"}`,
		r.next_action or "read the error above"
	)
end

-- the world's lessons ANSWERED before it is built (2026-11-08, sprint 3: the world pilot of the 3D study's lesson
-- gate; the world lane had no study step, so its lessons were shown and never answered or credited):
-- <worlds>/<Name>.lessons.md holds the lessons ranked for the world (kit/lib/answers.luau); each of the first five is
-- applied (how) or skipped (why); answered, the applied ones are recorded on the world as named citations.
local function lessonsCmd(args: { string }): number
	local Answers = require("../lib/answers")
	local name = args[1]
	if not name or string.sub(name, 1, 2) == "--" then
		return Run.report(
			"world-lessons",
			{},
			Run.CODES.USAGE,
			"world lessons: which world?",
			"lune run kit world lessons <Name> [--show]"
		)
	end
	local command = `lune run kit world lessons {name}`
	local path = `{Config.path("worlds")}/{name}.lessons.md`
	local show = table.find(args, "--show") ~= nil
	if show or not fs.isFile(path) then
		local text, ids, must = Answers.sheet("world", name, command)
		for line in string.gmatch(text, "[^\n]+") do
			if string.find(line, "<!-- ANSWER", 1, true) or (show and string.find(line, "<!-- optional", 1, true)) then
				print("  " .. string.gsub(string.gsub(line, "^<!%-%- ", ""), " %-%->$", ""))
			end
		end
		if show then
			return Run.report(
				"world-lessons",
				{},
				Run.CODES.PASS,
				`world lessons {name}: {#ids} lesson(s) ranked for it (shown; nothing written)`,
				command
			)
		end
		fs.writeFile(path, text)
		Answers.start(path, "world", name, must)
		return Run.report(
			"world-lessons",
			{},
			Run.CODES.PASS,
			`world lessons {name}: the sheet of {#ids} ranked lesson(s), {#must} to answer -> {path}`,
			if #must > 0
				then `answer each of the {#must} ANSWER lessons in {path} ("- <id>: how this world applies it" or "- skip <id>: why not", 6+ words), then: {command}`
				else `no lesson shares two words with this world: apply an optional one or write "- none: <why>" in {path}, then: {command}`
		)
	end
	-- a sheet with no record (written by hand, before the record, or its record lost): its lessons to answer are
	-- ranked again now and kept - never only what the sheet's own comments still say
	if not Answers.entry(path) then
		local _, _, must = Answers.sheet("world", name, command)
		Answers.start(path, "world", name, must)
		print(`  no record of this sheet's lessons: {#must} ranked again now and kept in board/answers.json`)
	end
	local sheet = fs.readFile(path)
	local r = Answers.check(sheet, "world", path)
	if #r.problems > 0 then
		for _, p in r.problems do
			print(`  {p}`)
		end
		return Run.report(
			"world-lessons",
			{},
			Run.CODES.CONTENT,
			`world lessons {name}: {#r.problems} to answer before building`,
			`answer them in {path}, then: {command}`
		)
	end
	local recorded = Answers.record("world", name, r.applied)
	Answers.passed(path, "world", name, sheet, r)
	return Run.report(
		"world-lessons",
		{},
		Run.CODES.PASS,
		`world lessons {name}: {#r.applied} applied, {#r.skipped} skipped{if recorded
			then ` - the applied ones recorded on {name} (the owner's verdict on it credits or flags each)`
			else ""}`,
		`build the world (lune run kit world plan {name}); commit {path}, board/answers.json and board/citations.json`
	)
end

local function planCmd(args: { string }): number
	local name = args[1]
	if not name then
		return Run.report(
			"world-plan",
			{},
			Run.CODES.USAGE,
			"world plan: which world?",
			"lune run kit world plan <Name>"
		)
	end
	-- the world's family (kit/lib/families.luau) decides whether past house layouts are examples for it
	local family = require("../lib/families").ofPiece("world", name)
	local argv = { "kit/world/plan.py", name }
	if family then
		table.insert(argv, "--family")
		table.insert(argv, family)
	end
	local step = Run.content("world plan", Run.tool("python"), argv)
	local r = step.result or {}
	for i, st in r.stages or {} do
		print(
			string.format(
				"  %d %-36s %-8s %s",
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
	-- the past house layouts that share this world's words (examples, never a template: sprint 5, proposal 11)
	if type(r.examples) == "table" and #r.examples > 0 then
		print("")
		print("  past layouts to read before planning interiors (the world lane's own; its own plan stays its own):")
		for _, e in r.examples do
			print(`    {e}`)
		end
	end
	return Run.report(
		"world-plan",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`{r.summary or "world plan: crashed"}`,
		r.next_action or "read the error above"
	)
end

local function importCmd(args: { string }): number
	local dir = Config.path("worlds") .. "/imports"
	if not fs.isDir(dir) then
		return Run.report(
			"world-import",
			{},
			Run.CODES.USAGE,
			`world import: no lists in {dir}`,
			`write {dir}/<set>.json: [\{ "name": "ph_boulder", "file": "<vetted>.gltf", "maxTris": 20000 \}] (VETLOG first)`
		)
	end
	local only = args[1]
	local out = Config.build("worldmeshes")
	Config.ensureDir(out)
	local steps, made = {}, 0
	for _, f in fs.readDir(dir) do
		if string.sub(f, -5) == ".json" and (not only or f == only .. ".json") then
			local step = Run.content(`import {f}`, Run.tool("blender"), {
				"-b",
				"--factory-startup",
				"--python-exit-code",
				"2",
				"-P",
				"kit/world/import_blender.py",
				"--",
				`{dir}/{f}`,
				out,
			})
			table.insert(steps, step)
			if step.ok then
				made += 1
			end
		end
	end
	local failed = #steps - made
	return Run.report(
		"world-import",
		steps,
		if failed == 0 and made > 0 then Run.CODES.PASS else Run.CODES.CONTENT,
		`world import: {made} list(s) imported{if failed > 0 then `, {failed} failed` else ""} -> {out}`,
		if failed == 0
			then 'use the names in forest / tree / scatter "meshes"; then lune run kit upload and lune run kit world'
			else "read the failing step above"
	)
end

-- kit world town <Name|blueprint.json>: the plan of every "town" step from above (kit/world/townplan.py), one
-- labelled page a town - what a session and the owner READ a layout by before anything is dressed
function WorldCmd.town(target: string): ({ Run.Step }, number, string, string)
	local flat, out = WorldCmd.flatten(target)
	if not out then
		return { flat },
			Run.CODES.CONTENT,
			`world town: {flat.tail}`,
			flat.result and flat.result.next_action or "fix the blueprint"
	end
	local step = Run.content(
		"world town",
		Run.tool("python"),
		{ "kit/world/townplan.py", out :: string, "--out", Config.build("worlds") .. "/town" }
	)
	local r = step.result or {}
	return { flat, step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world town: {r.summary or "crashed"}`,
		r.next_action or "read the error above"
end

-- kit world town <Name> --kit [--out <file.json>]: the KIT OF HOUSES a skinned town needs - one mesh recipe per
-- house type (kit world meshes kind "gothic_house"), cut for exactly the building the plan makes of that type, so
-- the compiler's skin check passes for every house. Read from the blueprint itself (a skinned town does not compile
-- until its meshes exist). Writes <worlds>/meshes/town_<World>.json; a town is changed in its blueprint, never there.
function WorldCmd.townKit(target: string, outPath: string?, meshesDir: string?): (Run.Step, string?)
	local path = if fs.isFile(target) then target else `{Config.path("worlds")}/{target}.json`
	if not fs.isFile(path) then
		return Run.step("world town kit", false, `no blueprint {path}`, {
			next_action = `create it: lune run kit new world {target}`,
		}),
			nil
	end
	local ok, bp = pcall(serde.decode, "json" :: any, fs.readFile(path))
	if not ok or type(bp) ~= "table" or type(bp.build) ~= "table" then
		return Run.step("world town kit", false, `{path}: not a blueprint`, { next_action = `fix the JSON in {path}` }),
			nil
	end
	local function refuse(message: string): (Run.Step, string?)
		return Run.step("world town kit", false, message, {
			status = "fail",
			summary = message,
			next_action = `fix {path}: {message}`,
		}),
			nil
	end
	if type(bp.name) ~= "string" or bp.name == "" then
		return refuse(`{path}: the blueprint has no "name" (the list is written as town_<name>.json)`)
	end
	local recipes: { any }, byName: { [string]: string } = {}, {}
	local towns, houses = 0, 0
	for i, step in bp.build do
		local kind, spec = next(step)
		if kind == "town" and type(spec) == "table" then
			local plan = Town.plan(spec)
			for _, issue in plan.issues do
				if issue.severity == "error" then
					return refuse(`build[{i}].town: {issue.message}`)
				end
			end
			local list, problem = Town.kit(plan, spec)
			if problem then
				return refuse(`build[{i}].town: {problem}`)
			end
			for _, r in list do
				local text = serde.encode("json", r)
				if byName[r.name] == nil then
					byName[r.name] = text
					table.insert(recipes, r)
				elseif byName[r.name] ~= text then
					-- (two towns, one prefix, the same type name for two different houses)
					return refuse(
						`build[{i}].town: the mesh "{r.name}" is already another town's, cut differently - give each town its own "skins" prefix`
					)
				end
			end
			towns += 1
			houses += #plan.lots
		end
	end
	if towns == 0 then
		return refuse(`{bp.name}: no "town" step in this world`)
	end
	local meshes = meshesDir or `{Config.path("worlds")}/meshes` -- (the lists kit world meshes reads)
	local own = `{meshes}/town_{bp.name}.json`
	local out = (string.gsub(outPath or own, "\\", "/"))
	-- every mesh lands in ONE registry by its name (build/worldmeshes/meshes.json): a name another world's list
	-- already cuts differently would be overwritten by whichever is made last
	if fs.isDir(meshes) then
		for _, f in fs.readDir(meshes) do
			local other = `{meshes}/{f}`
			if string.sub(f, -5) == ".json" and other ~= own and other ~= out then
				local okList, list = pcall(serde.decode, "json" :: any, fs.readFile(other))
				for _, r in if okList and type(list) == "table" then list else {} do
					if type(r) == "table" and byName[r.name] ~= nil and byName[r.name] ~= serde.encode("json", r) then
						return refuse(
							`the mesh "{r.name}" is already in {other}, cut differently - give this town another "skins" prefix`
						)
					end
				end
			end
		end
	end
	local dir = string.match(out, "^(.*)/[^/]+$")
	if dir then
		Config.ensureDir(dir)
	end
	fs.writeFile(out, serde.encode("json", recipes, true))
	local modules = 0
	for _, r in recipes do
		modules += if r.kind == "gothic_module" then 1 else 0
	end
	-- (a town with "facade": true needs modules, a handful for all its houses; one without, a mesh a house type)
	local what = if modules == #recipes
		then `{modules} facade module recipe(s)`
		elseif modules > 0 then `{#recipes - modules} house mesh and {modules} facade module recipe(s)`
		else `{#recipes} house mesh recipe(s)`
	local summary = `{bp.name}: {what} for {houses} house(s) in {towns} town(s) -> {out}`
	return Run.step("world town kit", true, out, {
		summary = summary,
		next_action = if out == own
			then `make them (about 7 s a mesh): lune run kit world meshes --set town_{bp.name}; then lune run kit world town {target} and lune run kit world look {target}`
			else `kit world meshes reads {meshes}/*.json only: copy {out} there as town_{bp.name}.json, then lune run kit world meshes --set town_{bp.name}`,
	}),
		out
end

-- kit world facade <Name> [--kit w3]: the FACADE MODULES a world's own "building" steps ask for - every building with
-- "facade": "<prefix>" (not a town's: kit world town --kit makes those), its storey heights, door and window gap read
-- from the buildings themselves (Facade.kit), so the compiler's Facade.problem passes for every house. One list a
-- prefix: <worlds>/meshes/<prefix>.json (then kit world meshes --set <prefix>). --kit w3: cut from the W3 modular
-- kit on its two shared trim sheets (kit/world/modkit_facade.py), a quoin a storey height with them.
function WorldCmd.facadeKit(target: string, kitName: string?, meshesDir: string?): Run.Step
	local path = if fs.isFile(target) then target else `{Config.path("worlds")}/{target}.json`
	local function refuse(message: string): Run.Step
		return Run.step("world facade", false, message, {
			status = "fail",
			summary = message,
			next_action = `fix {path}: {message}`,
		})
	end
	if not fs.isFile(path) then
		return refuse(`no blueprint {path}`)
	end
	if kitName ~= nil and not Facade.KITS[kitName] then
		return refuse(`no facade kit "{kitName}" (the kits: w3)`)
	end
	local ok, bp = pcall(serde.decode, "json" :: any, fs.readFile(path))
	if not ok or type(bp) ~= "table" or type(bp.build) ~= "table" then
		return refuse(`{path}: not a blueprint`)
	end
	-- the houses of each prefix: their storey heights; their door and window must be ONE size (one module a kind)
	local looks: { [string]: any } = {}
	local order: { string } = {}
	for i, step in bp.build do
		local b = if type(step) == "table" then step.building else nil
		if type(b) ~= "table" or type(b.facade) ~= "string" or b.facade == "" then
			continue
		end
		local fh = b.floorHeight or 14
		local win = b.windows or { width = 4, height = 8, sill = 3.5 } -- (the compiler's own defaults)
		local gap = { width = win.width or 4, height = (win.sill or 3.5) + (win.height or 5), sill = win.sill or 3.5 }
		local door = if type(b.door) == "table"
			then { width = b.door.width or 6, height = b.door.height or 8.5 }
			else { width = 6, height = 8.5 }
		local thick = (b.thickness or 1) + 0.2 -- (a module stands a hair proud of the wall it dresses, as a town's)
		local look = looks[b.facade]
		if not look then
			look = { prefix = b.facade, floorHeights = {}, thickness = thick, door = door, window = gap, kit = kitName }
			looks[b.facade] = look
			table.insert(order, b.facade)
		else
			-- (one prefix is one wall thickness too: a thicker house's invisible collision wall would stand proud of
			-- the stone it is dressed in - you would bump into nothing you can see)
			if math.abs(look.thickness - thick) > 0.05 then
				return refuse(
					`build[{i}].building "{b.name}": its wall thickness is {thick - 0.2}, another "{b.facade}" house's {look.thickness - 0.2} - one prefix is one kit: give it its own "facade" prefix`
				)
			end
			for _, pair in { { look.door, door, "door" }, { look.window, gap, "window" } } do
				for k, v in pair[2] do
					if math.abs(pair[1][k] - v) > 0.05 then
						return refuse(
							`build[{i}].building "{b.name}": its {pair[3]} {k} is {v}, another "{b.facade}" house's {pair[1][k]} - one prefix is one kit: give it its own "facade" prefix`
						)
					end
				end
			end
		end
		if not table.find(look.floorHeights, fh) then
			table.insert(look.floorHeights, fh)
		end
	end
	if #order == 0 then
		return refuse(`{bp.name or path}: no building wears a "facade"`)
	end
	local meshes = meshesDir or `{Config.path("worlds")}/meshes`
	Config.ensureDir(meshes)
	local written, count = {}, 0
	for _, prefix in order do
		local recipes = Facade.kit(looks[prefix])
		local own = `{meshes}/{prefix}.json`
		-- (one registry by name: a list elsewhere cutting one of these names differently would be overwritten)
		for _, f in fs.readDir(meshes) do
			local other = `{meshes}/{f}`
			if string.sub(f, -5) == ".json" and other ~= own then
				local okList, list = pcall(serde.decode, "json" :: any, fs.readFile(other))
				for _, r in if okList and type(list) == "table" then list else {} do
					for _, mine in recipes do
						if type(r) == "table" and r.name == mine.name then
							return refuse(
								`the mesh "{mine.name}" is already in {other} - give these houses another "facade" prefix`
							)
						end
					end
				end
			end
		end
		fs.writeFile(own, serde.encode("json", recipes, true))
		table.insert(written, prefix)
		count += #recipes
	end
	return Run.step("world facade", true, table.concat(written, ", "), {
		summary = `{bp.name or path}: {count} facade module recipe(s){if kitName then ` (kit {kitName})` else ""} for {#written} prefix(es) -> {meshes}/{table.concat(
			written,
			".json, "
		)}.json`,
		next_action = `make them: lune run kit world meshes --set {written[1]}; then lune run kit world and lune run kit world check {bp.name or target}`,
	})
end

local function facadeCmd(args: { string }): number
	local target = args[1]
	if not target or string.sub(target, 1, 2) == "--" then
		return Run.report(
			"world-facade",
			{},
			Run.CODES.USAGE,
			"world facade: which world?",
			"lune run kit world facade <Name> [--kit w3]"
		)
	end
	local at = table.find(args, "--kit")
	local kitName = if at then args[at + 1] else nil
	if at and (not kitName or string.sub(kitName, 1, 2) == "--") then
		return Run.report("world-facade", {}, Run.CODES.USAGE, "world facade: --kit needs a kit's name", "--kit w3")
	end
	local step = WorldCmd.facadeKit(target, kitName)
	local r = step.result or {}
	return Run.report(
		"world-facade",
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		`world facade: {r.summary or step.tail}`,
		r.next_action or "read the error above"
	)
end

local function townCmd(args: { string }): number
	local target = args[1]
	if not target or string.sub(target, 1, 2) == "--" then
		return Run.report(
			"world-town",
			{},
			Run.CODES.USAGE,
			"world town: which world?",
			"lune run kit world town <Name> [--kit [--out <file.json>]]"
		)
	end
	if table.find(args, "--kit") then
		local at = table.find(args, "--out")
		local outPath: string? = nil
		if at then
			outPath = args[at + 1]
			if not outPath or string.sub(outPath, 1, 2) == "--" then
				return Run.report(
					"world-town",
					{},
					Run.CODES.USAGE,
					"world town: --out needs a file path",
					"lune run kit world town <Name> --kit [--out <file.json>]"
				)
			end
		end
		local step = WorldCmd.townKit(target, outPath)
		local r = step.result or {}
		return Run.report(
			"world-town",
			{ step },
			if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
			`world town: {r.summary or step.tail}`,
			r.next_action or "read the error above"
		)
	end
	local steps, code, summary, nextAction = WorldCmd.town(target)
	return Run.report("world-town", steps, code, summary, nextAction)
end

local SUBS: { [string]: Sub } = {
	town = {
		usage = "world town <Name|blueprint.json> [--kit [--out <file.json>]]",
		about = "the PLAN of a world's town steps from above (build/worlds/town/<World>_<Town>.png): a square entered at its corners, streets by name and width, every lot shaded by its storeys with its door, each gate's walk to the square in seconds, the landmark on the main gate's line of sight, T-junctions / crossings / dead ends, the layout's numbers and the kit of house types to make meshes for. Read it BEFORE dressing anything; the numbers are for reading, never a score. --kit writes the town's KIT OF HOUSES instead: one mesh recipe per house type (<worlds>/meshes/town_<World>.json; then kit world meshes --set town_<World>), each cut for exactly the house the plan makes, so a town with skins wears real meshes",
		run = townCmd,
	},
	refs = {
		usage = "world refs <Name> [--vs <render.png>]",
		about = "measure the world's reference stills (assets/worlds/refs/<Name>/: horizon line, value structure, haze, saturation, palette) -> REFS.md + the world identity; --vs a render = ONE difference + ONE edit against it (no score)",
		run = refsCmd,
	},
	lessons = {
		usage = "world lessons <Name> [--show]",
		about = "the world's lessons ANSWERED before building: a sheet of the lessons ranked for it (<worlds>/<Name>.lessons.md); apply or skip each of the first five with a reason; answered, the applied ones are recorded on the world (the owner's verdict credits or flags each). --show prints the ranking only",
		run = lessonsCmd,
	},
	facade = {
		usage = "world facade <Name|blueprint.json> [--kit w3]",
		about = 'the FACADE MODULES a world\'s own "building" steps wear ("facade": "<prefix>"): one recipe list a prefix (<worlds>/meshes/<prefix>.json), each module cut for exactly the storey height, door and window gap those houses have (kit/lib/worldfacade.luau Facade.kit). --kit w3 cuts them from the W3 modular kit on its two shared trim sheets (a SurfaceAppearance each; a quoin a storey height). Then kit world meshes --set <prefix>',
		run = facadeCmd,
	},
	plan = {
		usage = "world plan <Name>",
		about = "ONE world's route stage by stage from its own files - refs, terrain (real land), materials, meshes, dressing, check, look, studio, the owner's verdict: done / partly / to do, what is missing, the next stage's commands (<= 5)",
		run = planCmd,
	},
	materials = {
		usage = "world materials [--materials Grass,Rock,...]",
		about = "the scans (ambientCG 1K) as Roblox MaterialVariant maps (color / normal / roughness, 1024 PNG) -> build/terrainmaps; kit upload, then kit world writes the variants into MaterialService and the runtime overrides the painted materials with them",
		run = materialsCmd,
	},
	colorscript = {
		usage = "world colorscript [--game <Name>] [--order A,B,C]",
		about = "the world's COLOUR SCRIPT (an art director's tool): each place's picked (or recommended) frame in journey order with its palette, value and warmth curves; names neighbours with no change of mood",
		run = colorscriptCmd,
	},
	board = {
		usage = "world board [--game <Name>]",
		about = "the owner's REVIEW BOARD: every world direction doc of the game as one page (the one idea, three frames side by side, axes, pillars, bans, the pick) -> games/<Name>/build/direction/; publish it and record the owner's picks",
		run = boardCmd,
	},
	frame = {
		usage = "world frame <scene.frame.json> [--out <png>] [--samples 96]",
		about = "a DIRECTION / MOOD frame from the kit's REAL pieces (wall / tower / roof / root recipes + props) with the direction's light: designed sky, key + bounce, haze, a horizon landmark, motes, the camera low on the approach -> a GPU render beside the direction doc",
		run = frameCmd,
	},
	direction = {
		usage = "world direction <Piece> [--new]",
		about = "DIRECTION before an original piece (a castle, a region, a landmark): intent, the one idea, >= 6 references from more than one medium (take / leave), 3 pillars, bans, 3 directions each with a rendered frame -> <worlds>/direction/<Piece>.md; draft -> ready (show the owner the frames) -> picked (build to it)",
		run = directionCmd,
	},
	light = {
		usage = "world light <Name> [--preset gothic_moonlit|gothic_dusk|gothic_fog|gothic_storm|gothic_dawn] [--most 16]",
		about = "W5 LIGHT PASS: the world in one of five night-city presets for Roblox's Realistic lighting style (Future, moon or low sun as the floor of light) with its shadow lamps PICKED under the budget (the brightest, widest first, none a pace from another, at most --most within 120 studs of one) -> a scratch copy compiled to build/worlds/<Name>_light.json; the blueprint is never written. The owner judges it in Studio",
		run = lightCmd,
	},
	rivers = {
		usage = "world rivers <Name> [--share 0.012] [--wide 0.0025] [--ribbons]",
		about = 'WATER in the valleys the rivers carved: D8 drainage over the heightmap; the cells where the most water gathers are painted as the "river" role (Water), the biggest widened, specks dropped -> the heightmap + a river map (run it once after kit world terrain)',
		run = riversCmd,
	},
	imagery = {
		usage = "world imagery <Name> --bbox lon0,lat0,lon1,lat1 [--size 512]",
		about = "REAL ground cover: a USDA NAIP aerial picture (public domain) of a box -> assets/worlds/terrain/<Name>.img.png, read as the painter's roles (green = meadow, dark green = lush, grey = rock, brown = dirt ...); kit world terrain <Name> --design <its dem design> --imagery <file> paints the real land by it. A read of colour, not a land-cover map",
		run = imageryCmd,
	},
	scan = {
		usage = "world scan <Name> --from <photos folder> --size <metres> [--axis height|length|width] [--quality low|medium|high]",
		about = "a REAL thing photographed all round (a rock, a statue, a well, a stump) -> a world mesh AT ITS REAL SIZE: the 3D lane's photogrammetry route (COLMAP: checked, levelled, metric, textured) makes it, the world's importer brings it in (decimated to a MeshPart's limit), its sizes in studs (0.28 m a stud) -> build/worldmeshes; a mesh / rocks / scatter step places it. --size is a size you know of the real thing: photos alone have none",
		run = scanCmd,
	},
	dem = {
		usage = "world dem <Name> --bbox lon0,lat0,lon1,lat1 [--size 512]",
		about = 'REAL land: USGS 3DEP elevation (public domain) for a box -> assets/worlds/terrain/<Name>.dem.tif; a terrain design\'s "dem" uses it as its base (slopes true, refined by the rivers / erosion / painter)',
		run = demCmd,
	},
	import = {
		usage = "world import [<set>]",
		about = "vetted downloaded glTF models (Poly Haven scans, Quaternius, ...) -> world meshes: sets split, scans decimated to a MeshPart's limit, textures as PNG",
		run = importCmd,
	},
	sky = {
		usage = "world sky <Name> [--sun <elevation>,<azimuth>] [--clouds 0..1] [--seed n] [--size 256|512|1024]",
		about = 'a sky of the kit\'s own: six square pictures of one physical sky (the sun where asked, clouds by noise) rendered in Blender, one for each face of Roblox\'s sky cube as measured in Studio -> build/skies/<Name>_ft.png ... + <Name>.sky.json; a world\'s lighting names it ("sky": "<Name>"); in a game once uploaded',
		run = skyCmd,
	},
	decal = {
		usage = "world decal <Name> --kind leak|stain|crack|moss|soot [--seed n] [--size 256|512|1024] [--tint r,g,b]",
		about = "A DECAL'S PICTURE made by rule (a leak under a ledge, a stain, a crack, moss, soot), its border clear so that no square shows -> build/decals/<Name>.png; a world's \"decal\" build step lays it on a wall or a floor (one where said, or many along a wall), and refuses one that lies on nothing. In a game only once uploaded (no blood: a tint that reads as blood is refused)",
		run = decalCmd,
	},
	["scatter-on"] = {
		usage = "world scatter-on <mesh> --as <name> --gap <studs> [--facing up|side|down|any] [--steep 0.5] [--seed 1] [--most 400]",
		about = 'points over a world mesh\'s SURFACE by Geometry Nodes in Blender (Poisson disk: none closer than the gap; only the faces that face up, sideways or down) -> build/worldmeshes/<mesh>.on.<name>.json; a mesh step sets a part on each ("on": { "points": "<name>", "part": { "size", "mat" } }): moss on ledges, ivy on a wall',
		run = scatterOnCmd,
	},
	meshes = {
		usage = "world meshes [<name>] [--set <recipe list>]",
		about = 'a world\'s REAL meshes from recipes (assets/worlds/meshes/*.json): trees (branches + leaf cards + a bark / leaf atlas), rocks, cliffs, castle wall modules (modelled ashlar + a stone atlas, tiling), made in Blender -> build/worldmeshes (FBX for Roblox, arrays for the viewer, previews); forest / tree / scatter steps use them with "meshes" / "mesh"',
		run = meshesCmd,
	},
	gallery = {
		usage = "world gallery",
		about = "every world (each game's, and the project's own) in one page: a card per world — its eye-level shot, its pitch, its parts — opening its web viewer -> build/worlds/gallery/ (publish index.html as an Artifact with its files)",
		run = galleryCmd,
	},
	shots = {
		usage = "world shots <Name|blueprint.json>",
		about = "the web viewer rendered headless (Edge / Chrome): overview, from above, eye level at every grace / spawn, close to every objective -> build/worlds/shots/<name>.png (a contact sheet) in about a minute",
		run = shotsCmd,
	},
	web = {
		usage = "world web <Name|blueprint.json>",
		about = "the world as ONE self-contained web page: three.js + the kit's own shaders (terrain layers, materials, water, sky, fog, shadows, bloom, grass, particles), orbit / fly / walk, a map and the places -> build/worlds/web/<name>.html (publishable as an Artifact)",
		run = webCmd,
	},
	terrain = {
		usage = "world terrain <Name> [--size --seed --relief --erosion --thermal --from <image> --flat x,z,r --stamp kind,x,z,radius,height[,turn][,worked] --climate wind=..,rain=..]",
		about = 'a heightmap: fractal noise or a picture (a DEM, a painted sketch) + thermal + hydraulic erosion -> assets/worlds/terrain/<Name>.hm.json + a shaded relief to look at; use it as a "heightmap" terrain op',
		run = terrainCmd,
	},
	bible = {
		usage = "world bible <Name> [--write]",
		about = "the world's BIBLE (<worlds>/<Name>.bible.json: 1 stud = 0.28 m, its region cards - area, lamp rule, fixtures in words - and its landmarks) checked, each landmark SEEN from every spawn; --write: a starter from the blueprint (V3 W1)",
		run = bibleCmd,
	},
	greybox = {
		usage = "world greybox <Name>",
		about = "the world with NO mesh (skins and facades not worn, every mesh a grey box of its size) at its stations with the R6 rig -> build/worlds/look/<Name>.greybox/; walked with the owner, his yes is --stage greybox: a new world is dressed in meshes only after it (V3 W1)",
		run = greyboxCmd,
	},
	corner = {
		usage = "world corner <Name> --at <station>",
		about = "the world framed on ONE 40 x 40 stud corner at a station, at full size (from the station's eye, and three-quarter from above; the rest of the built world stays in frame as it is) -> build/worlds/corner/<Name>/; the owner's 7+ is --stage corner: a new town / street of houses is built out only after it (V3 W2)",
		run = cornerCmd,
	},
	look = {
		usage = "world look <Name|blueprint.json>",
		about = "the world's STATIONS at 1920 x 1080: Blender renders what the player sees at every spawn (Roblox's camera behind the R6 rig), the blueprint's views, the view back from each objective and an establishing shot, lit by the world's lighting and labelled -> ONE PAGE PER STATION, its reference still above ours at the same framing (build/worlds/look/<name>/pages/; which still: <worlds>/refs/<Name>/stations.json) + the index sheet build/worlds/look/<name>.png",
		run = lookCmd,
	},
	studio = {
		usage = "world studio <Name|blueprint.json> [--capture] [--render] [--wait <seconds>]",
		about = "the SAME stations in ROBLOX STUDIO, in Roblox's own light: makes the world's scratch place (build/worlds/studio/<Name>/KitWorldScratch_<Name>.rbxlx, built by rojo: the world alone, nothing saved, nothing uploaded - so plain parts and light, no meshes) and the capture script (capture.luau, run through the Studio tools in that place only); --capture waits for the script's walk and takes each picture from that place's own window -> three panes a station: reference, Blender, Studio (build/worlds/studio/<Name>/pages/). A pane with no capture says why",
		run = studioCmd,
	},
	check = {
		usage = "world check <Name|blueprint.json>",
		about = "prove it PLAYS: R6 reachability (walk / climb / drop / gap-jump), traps, spawn fairness, exposure, sightlines, camera clearance, knockback room -> build/worlds/checks/<name>.png",
		run = function(args)
			local target = args[1]
			if not target then
				return Run.report(
					"world-check",
					{},
					Run.CODES.USAGE,
					"world check: which world?",
					"lune run kit world check <Name>"
				)
			end
			local flat, out = WorldCmd.flatten(target)
			if not out then
				return Run.report(
					"world-check",
					{ flat },
					Run.CODES.CONTENT,
					`world check: {flat.tail}`,
					flat.result and flat.result.next_action or "fix the blueprint"
				)
			end
			local step = Run.content("world check", Run.tool("python"), { "kit/world/worldcheck.py", out :: string })
			local r = step.result or {}
			for _, e in r.errors or {} do
				print("  ERROR " .. e)
			end
			for _, w in r.warnings or {} do
				print("  warn  " .. w)
			end
			return Run.report(
				"world-check",
				{ flat, step },
				if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
				`world check: {r.summary or "crashed"}`,
				r.next_action or "read the error above"
			)
		end,
	},
}

function WorldCmd.has(word: string?): boolean
	return word ~= nil and SUBS[word] ~= nil
end

function WorldCmd.run(args: { string }): number
	local sub = SUBS[args[1]]
	return sub.run({ table.unpack(args, 2) })
end

function WorldCmd.add(name: string, sub: Sub)
	SUBS[name] = sub
end

return WorldCmd

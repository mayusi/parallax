-- content.luau — 3D, sound, VFX and UI pipelines. Paths come from kit.config.json (Config.path).
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")
local stdio = require("@lune/stdio")

local Config = require("../lib/config")
local JsonModel = require("../lib/jsonmodel")
local Judge = require("./judge")
local Locks = require("../lib/locks")
local Models = require("../lib/models")
local Prebuild = require("../lib/prebuild")
local Run = require("../lib/run")
local Starters = require("../lib/starters")
local UI = require("../lib/ui")
local VfxCompose = require("../../src/kit/VfxCompose")
local VfxLegacy = require("../lib/vfxlegacy")
local VfxValidate = require("../../src/kit/VfxValidate")

-- version-3 composition (beats / use / variants) expands before anything validates, plays or bundles; parts come
-- from assets/effects/parts/<name>.json. Issues come back in the validator's shape (prepend them).
local function partLoader(dir: string): (string) -> any?
	return function(partName: string): any?
		local path = `{dir}/parts/{partName}.json`
		if not fs.isFile(path) then
			return nil
		end
		local ok, part = pcall(serde.decode, "json" :: any, fs.readFile(path))
		return if ok then part else nil
	end
end

local function expandPreset(preset: any, variant: string?): (any, { any })
	if type(preset) ~= "table" or preset.version ~= 3 then
		return preset, {}
	end
	return VfxCompose.expand(preset, { variant = variant, parts = partLoader(Config.path("vfx")) })
end

local function flagValue(rest: { string }, flag: string): string?
	for i, a in rest do
		if a == flag and rest[i + 1] and string.sub(rest[i + 1], 1, 2) ~= "--" then
			return rest[i + 1]
		end
	end
	return nil
end

local C = Run.CODES
local Content = {}

-- the Studio scripts of one booth run, through the shared capture bridge (kit/tools/studio_capture.py snippet, card
-- 4s96: no network - the script signals with colours over the 3D view and RETURNS its answer) -> the tool's JSON
-- answer ({ files = { run, install, collect } }), or nil and why
local function studioSnippets(harness: string, jobPath: string, base: string): (any?, string?)
	local res = process.exec(
		Run.tool("python"),
		{ "kit/tools/studio_capture.py", "snippet", harness, "--job", jobPath, "--out", base }
	)
	local lines = string.split(string.gsub(res.stdout, "\r", ""), "\n")
	local last = #lines
	while last > 0 and not string.match(lines[last], "%S") do
		last -= 1
	end
	local ok, v = pcall(serde.decode, "json" :: any, if last > 0 then lines[last] else "")
	if res.ok and ok and type(v) == "table" and v.status == "pass" then
		return v, nil
	end
	return nil,
		if ok and type(v) == "table" then tostring(v.summary) else (res.stderr ~= "" and res.stderr or res.stdout)
end

-- the steps a booth run prints: the capture first, then the Studio scripts, then the answer saved for the capture
local function studioSteps(capture: string, files: any, resultPath: string, look: string)
	print(`1. capture (background, FIRST):  {capture}`)
	print(`2. Studio (MCP execute_luau, datamodel Edit, the kit's scratch place only, never saved): run {files.run}`)
	print(
		`   - it answers status "install" when the place lacks this harness: run {files.install} ONCE, then step 2 again`
	)
	print(`   - it answers status "started" (a long run) with its seconds: once they passed, run {files.collect}`)
	print(`3. save the last answer line (one JSON line) as {resultPath}: the capture names the pictures and exits`)
	print(`4. {look}`)
end

local function content(_step: Run.Step): number
	return C.CONTENT
end

local function sameModel(path: string, model: any): boolean
	return JsonModel.same(fs.readFile(path), model)
end

local function listNames(dir: string, pattern: string): { string }
	local out = {}
	if fs.isDir(dir) then
		for _, f in fs.readDir(dir) do
			local n = string.match(f, pattern)
			if n then
				table.insert(out, n)
			end
		end
	end
	table.sort(out)
	return out
end

-- ---------------------------------------------------------------- 3D -> game (what Models.spawn reads)
-- build/models/<asset>.manifest.json + assets/ids.json -> src/models/<asset>.model.json (ReplicatedStorage.KitModels).
-- write=false: verify — a stale file fails; assets not uploaded yet only warn (they spawn as grey stand-ins).
function Content.modelsCompile(write: boolean): (Run.Step, { string })
	local dir, outDir = Config.build("models"), Config.path("modelOut")
	local ids = if fs.isFile(Config.path("ids")) then serde.decode("json", fs.readFile(Config.path("ids"))) else {}
	local names, drift, missing = {}, {}, {}
	if fs.isDir(dir) then
		for _, file in fs.readDir(dir) do
			local asset = string.match(file, "^(.+)%.manifest%.json$")
			-- only assets that still have a build script (selftest fixtures, scratch builds and deleted assets don't)
			if not asset or not fs.isFile(`{Config.path("models")}/build_{asset}.py`) then
				continue
			end
			local ok, manifest = pcall(serde.decode, "json" :: any, fs.readFile(`{dir}/{file}`))
			if not ok then
				continue
			end
			if Models.unshipped(manifest) then
				-- a PRIVATE asset or a MASTER (Models.unshipped) never enters the game: any file it left there goes
				if write then
					pcall(fs.removeFile, `{outDir}/{asset}.model.json`)
				end
				continue
			end
			local model, gaps = Models.compile(asset, manifest, ids)
			for _, g in gaps do
				table.insert(missing, g)
			end
			local path = `{outDir}/{asset}.model.json`
			if write then
				Config.ensureDir(outDir)
				if not fs.isFile(path) or not sameModel(path, model) then
					fs.writeFile(path, serde.encode("json", model, true) .. "\n")
				end
			elseif not fs.isFile(path) or not sameModel(path, model) then
				table.insert(drift, path)
			end
			table.insert(names, asset)
		end
	end
	table.sort(names)
	local next_action = nil
	-- hero / aaa: an independent judge's verdict for the current build, at or above the bar (kit judge)
	local judged = if write then {} else Judge.problems()
	if #drift > 0 then
		next_action = `{drift[1]} is out of date with its build — run: lune run kit models`
	elseif #judged > 0 then
		next_action = judged[1] .. (if #judged > 1 then ` (+{#judged - 1} more)` else "")
	elseif #missing > 0 then
		next_action =
			`{#missing} built file(s) are not on Roblox yet (first: {missing[1]}) — run: lune run kit upload`
	end
	return Run.step(
		if write then "models compile" else "models up to date",
		#drift == 0 and #judged == 0,
		if #missing > 0 then "not uploaded yet: " .. table.concat(missing, ", ") else "",
		{
			summary = `{#names} model(s)` .. (if #drift > 0 then `, {#drift} stale` else "") .. (if #missing > 0
				then `, {#missing} file(s) not uploaded`
				else ""),
			next_action = next_action,
		}
	),
		names
end

-- ---------------------------------------------------------------- 3D (Blender headless)
function Content.blenderStep(label: string, script: string, extra: { string }): Run.Step
	local args = { "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--" }
	for _, a in extra do
		table.insert(args, a)
	end
	return Run.content(label, Run.tool("blender"), args, { KIT_BUILD = Config.path("build") })
end

-- Asked before every build of a 3D piece (kit asset, kit optimize: kit/tools/plan.py --prebuild): no build past the
-- piece's time budget - only the owner's words reopen it (the car rim's rework, 2026-11-10: 26 builds in 4.5 hours on
-- a 10-minute clock that only kit plan read) - and none on a route its study's lessons were not answered for (kit
-- study <piece> --reroute asks each again). -> nil to build, or the refusal { summary, next_action }
function Content.prebuild(name: string, dir: string, noClock: boolean?): { summary: string, next_action: string }?
	local projectRoot = string.gsub(string.gsub(dir, "\\", "/"), "/?assets/models/?$", "")
	local rootArg = if projectRoot == "" then "." else projectRoot
	Locks.freezeAll() -- (the study, stage and methods lists are frozen by the first build too, not only by kit plan)
	local argv = { "kit/tools/plan.py", name, "--prebuild", "--root", rootArg }
	if noClock then -- (kit asset all: a maintenance rebuild of every piece reads no clock; the route check holds)
		table.insert(argv, "--no-clock")
	end
	local res = process.exec(Run.tool("python"), argv)
	local lines = string.split(string.gsub(res.stdout, "\r", ""), "\n")
	local last = #lines
	while last > 0 and not string.match(lines[last], "%S") do
		last -= 1
	end
	local ok, v = pcall(serde.decode, "json" :: any, if last > 0 then lines[last] else "")
	for i = 1, last - 1 do -- (what it says: a clock started, a fresh attempt - or why it stops)
		print(lines[i])
	end
	if res.ok and ok and type(v) == "table" and v.status == "pass" then
		return nil
	end
	if ok and type(v) == "table" and v.status == "fail" then
		return { summary = tostring(v.summary), next_action = tostring(v.next_action) }
	end
	-- (the check itself broke: never build blind past it - its own error says why)
	local err = string.match(res.stderr, "([^\n]+)%s*$") or "no output"
	return {
		summary = `asset {name}: the budget and route check crashed ({err})`,
		next_action = `python kit/tools/plan.py {name} --prebuild --root {rootArg}`,
	}
end

-- every lane but 3D asks the same before a build (kit/lib/prebuild.luau: the clock, the route, a rerouted sheet's
-- answers): Content.laneHeld(lane, name) -> the refusal's exit code, or nil to build
Content.lanePrebuild = Prebuild.lane
Content.laneHeld = Prebuild.held
Content.laneHeldAll = Prebuild.heldAll -- (a rebuild of every piece in a lane folder)

-- `kit gen texture <asset> --image <picture>`: the asset's LAST FULL BUILD (build/models/<asset>.blend; one group with
-- --group) exported in its own space (kit/blender/texture_export.py), painted by TRELLIS.2 from the picture
-- (kit/gen/trellis2_texture.py; the picture's own transparency, else BiRefNet's cut-out) -> assets/models/<asset>.tex.glb
-- + .tex.json. The build script bakes it on: a.texture_from("<asset>.tex.glb") (kit/gen/README.md)
function Content.genTexture(n: string?, flags: { [string]: any }): number
	local image = flags.image
	if not n or type(image) ~= "string" or not fs.isFile(image) then
		return Run.report(
			"gen-texture",
			{},
			C.USAGE,
			"gen texture: needs an asset and --image <picture>",
			"lune run kit gen texture <asset> --image refs/<asset>.png [--group <group>] [--turn <degrees>]"
		)
	end
	local blend = `{Config.build("models")}/{n}.blend`
	if not fs.isFile(blend) then
		return Run.report(
			`gen-texture-{n}`,
			{},
			C.CONTENT,
			`gen texture: {n} has no full build to paint`,
			`build it first: lune run kit asset {n}   (a master: paint the master; kit optimize carries it to the game version)`
		)
	end
	local work = Config.build("gen")
	if not fs.isDir(work) then
		fs.writeDir(work)
	end
	local group = if type(flags.group) == "string" then flags.group else nil
	local stem = if group then `{n}_{group}` else n
	local cut, rgba = `{work}/{stem}_tex_cut.png`, `{work}/{stem}_tex_cut_rgba.png`
	local mesh = `{work}/{stem}_tex_src.ply`
	local out = `{Config.path("models")}/{stem}.tex.glb`
	local export = {
		"-b",
		"--factory-startup",
		blend,
		"--python-exit-code",
		"2",
		"-P",
		"kit/blender/texture_export.py",
		"--",
		n,
		mesh,
	}
	if group then
		table.insert(export, "--group")
		table.insert(export, group)
	end
	local paint = { "kit/gen/trellis2_texture.py", mesh, image, out, "--cutout", rgba }
	for _, k in { "seed", "texture", "turn", "steps" } do
		if flags[k] ~= nil and flags[k] ~= true then
			table.insert(paint, `--{k}`)
			table.insert(paint, tostring(flags[k]))
		end
	end
	return Run.chain(
		`gen-texture-{stem}`,
		{
			function()
				return Run.content(
					`cutout {stem}`,
					Run.tool("python"),
					{ "kit/vision/run.py", "cutout", image, "--rgba", "-o", cut }
				)
			end,
			function()
				return Run.content(`export {stem}`, Run.tool("blender"), export, { KIT_BUILD = Config.path("build") })
			end,
			function()
				return Run.content(`trellis2 texture {stem}`, Run.tool("trellis2"), paint)
			end,
		},
		content,
		`gen texture: {out} — bake it onto {n}: a.texture_from("{stem}.tex.glb") in its build script, then lune run kit asset {n}`
	)
end

-- ---------------------------------------------------------------- audio
function Content.synthStep(names: { string }, recipes: string?, out: string?): Run.Step
	local args =
		{ "kit/audio/synth.py", "--recipes", recipes or Config.path("sounds"), "--out", out or Config.build("sounds") }
	for _, n in names do
		table.insert(args, n)
	end
	return Run.content("synth " .. table.concat(names, " "), Run.tool("python"), args)
end

function Content.audioCheckStep(target: string): Run.Step
	return Run.content("audio-check " .. target, Run.tool("python"), { "kit/audio/check.py", target })
end

-- ---------------------------------------------------------------- vfx
function Content.texturesStep(args: { string }): Run.Step
	local full = { "kit/vfx/textures.py" }
	if args[1] ~= "--check" then
		for _, a in { "--specs", Config.path("textures"), "--out", Config.build("textures") } do
			table.insert(full, a)
		end
	end
	for _, a in args do
		table.insert(full, a)
	end
	return Run.content("textures " .. table.concat(args, " "), Run.tool("python"), full)
end

-- volumetric flipbooks: assets/textures/*.json with "engine": "blender" -> Blender (only when the spec changed)
function Content.flipbooksStep(): Run.Step?
	local dir = Config.path("textures")
	local any = false
	for _, n in listNames(dir, "^(.+)%.json$") do
		local ok, spec = pcall(serde.decode, "json" :: any, fs.readFile(`{dir}/{n}.json`))
		if ok and type(spec) == "table" and spec.engine == "blender" then
			any = true
			break
		end
	end
	if not any then
		return nil
	end
	return Content.blenderStep("flipbooks", "kit/vfx/flipbook.py", {
		"--specs",
		dir,
		"--out",
		Config.build("textures"),
		"--registry",
		Config.path("vfx") .. "/_textures.json",
	})
end

-- Blender-made VFX elements: assets/textures/*.json with "engine": "fx" -> kit/vfx/fxlab.py renders each recipe's
-- frames for real (Cycles GPU; only specs newer than their frames) -> kit/vfx/fxfinish.py adds glow, maps the hot
-- core to white, makes alpha, packs the Roblox sheet and registers it in _textures.json (+ _fx_review.png to LOOK at)
local function fxSpecs(): boolean
	local dir = Config.path("textures")
	for _, n in listNames(dir, "^(.+)%.json$") do
		local ok, spec = pcall(serde.decode, "json" :: any, fs.readFile(`{dir}/{n}.json`))
		if ok and type(spec) == "table" and spec.engine == "fx" then
			return true
		end
	end
	return false
end

-- GPU sims (assets/textures/*.json with a "gpu_smoke" / "gpu_fire" recipe): kit/vfx/gpusim.py simulates + renders them
-- on the GPU (PyTorch + CUDA; seconds, not Mantaflow's minutes a frame) into the same build/fxlab frames fxfinish packs
local function gpuSpecs(): boolean
	local dir = Config.path("textures")
	for _, n in listNames(dir, "^(.+)%.json$") do
		local ok, spec = pcall(serde.decode, "json" :: any, fs.readFile(`{dir}/{n}.json`))
		if
			ok
			and type(spec) == "table"
			and type(spec.recipe) == "string"
			and string.sub(spec.recipe, 1, 4) == "gpu_"
		then
			return true
		end
	end
	return false
end

function Content.gpuSimStep(): Run.Step?
	if not gpuSpecs() then
		return nil
	end
	return Run.content("gpu sims", Run.tool("python"), {
		"kit/vfx/gpusim.py",
		"--specs",
		Config.path("textures"),
		"--out",
		Config.build("fxlab"),
	})
end

-- inked sheets (assets/textures/*.json with recipe "ink"): kit/vfx/ink.py draws a scene's traced drawings again into
-- the same build/fxlab frames fxfinish packs (numpy; only specs whose frames are missing or older than the spec)
local function inkSpecs(): boolean
	local dir = Config.path("textures")
	for _, n in listNames(dir, "^(.+)%.json$") do
		local ok, spec = pcall(serde.decode, "json" :: any, fs.readFile(`{dir}/{n}.json`))
		if ok and type(spec) == "table" and spec.engine == "fx" and spec.recipe == "ink" then
			return true
		end
	end
	return false
end

function Content.inkStep(): Run.Step?
	if not inkSpecs() then
		return nil
	end
	return Run.content("ink sheets", Run.tool("python"), {
		"kit/vfx/ink.py",
		"--specs",
		Config.path("textures"),
		"--out",
		Config.build("fxlab"),
		"--kept-dir",
		Config.path("vfx") .. "/refs_measured",
	})
end

-- dissolve sheets (assets/textures/*.json with recipe "dissolve"): kit/vfx/dissolve.py bakes a built fx texture
-- breaking up, then packs and registers its own sheets (numpy; a sheet is baked only when its frames are missing,
-- older than its spec, or baked from a source texture that changed). It runs AFTER the packer's general pass, which
-- leaves these sheets alone (--skip-derived): the source it reads is then the one of THIS run (run before the packer
-- it baked from the source as it was one run earlier and said "current" - a review, 2026-11-13)
local function dissolveSpecs(): boolean
	local dir = Config.path("textures")
	for _, n in listNames(dir, "^(.+)%.json$") do
		local ok, spec = pcall(serde.decode, "json" :: any, fs.readFile(`{dir}/{n}.json`))
		if ok and type(spec) == "table" and spec.engine == "fx" and spec.recipe == "dissolve" then
			return true
		end
	end
	return false
end

function Content.dissolveStep(): Run.Step?
	if not dissolveSpecs() then
		return nil
	end
	return Run.content("dissolve sheets", Run.tool("python"), {
		"kit/vfx/dissolve.py",
		"--specs",
		Config.path("textures"),
		"--out",
		Config.build("fxlab"),
		"--textures-dir",
		Config.build("textures"),
		"--pack",
		"kit/vfx/fxfinish.py",
		"--registry",
		Config.path("vfx") .. "/_textures.json",
	})
end

-- comp sheets (assets/textures/*.json with recipe "comp"): kit/vfx/comp.py evaluates a short stack into the same
-- build/fxlab frames fxfinish packs (numpy, well under a second a sheet; only specs whose frames are stale). A PLAIN
-- stack is baked before the packer, which packs it like every sheet; a stack that MAPS a built texture ("source") is
-- baked after the packer's general pass - its source is then the one of this run - and packed by its own step,
-- before the dissolve step (a mapped skin can be a dissolve's source)
local function compSpecs(mapped: boolean): boolean
	local dir = Config.path("textures")
	for _, n in listNames(dir, "^(.+)%.json$") do
		local ok, spec = pcall(serde.decode, "json" :: any, fs.readFile(`{dir}/{n}.json`))
		if ok and type(spec) == "table" and spec.engine == "fx" and spec.recipe == "comp" then
			local has = type(spec.comp) == "table" and spec.comp.source ~= nil
			if has == mapped then
				return true
			end
		end
	end
	return false
end

-- liquid sheets (assets/textures/*.json with recipe "liquid"): kit/vfx/liquid.py solves a liquid (FLIP, or a
-- particle fluid) seen from the side and draws it into the same build/fxlab frames fxfinish packs (numpy; only specs
-- whose frames are stale; a few seconds a sheet, a particle fluid about half a minute)
local function liquidSpecs(): boolean
	local dir = Config.path("textures")
	for _, n in listNames(dir, "^(.+)%.json$") do
		local ok, spec = pcall(serde.decode, "json" :: any, fs.readFile(`{dir}/{n}.json`))
		if ok and type(spec) == "table" and spec.engine == "fx" and spec.recipe == "liquid" then
			return true
		end
	end
	return false
end

function Content.liquidStep(): Run.Step?
	if not liquidSpecs() then
		return nil
	end
	return Run.content("liquid sheets", Run.tool("python"), {
		"kit/vfx/liquid.py",
		"--specs",
		Config.path("textures"),
		"--out",
		Config.build("fxlab"),
	})
end

function Content.compStep(mapped: boolean): Run.Step?
	if not compSpecs(mapped) then
		return nil
	end
	local argv = {
		"kit/vfx/comp.py",
		"--specs",
		Config.path("textures"),
		"--out",
		Config.build("fxlab"),
		"--textures-dir",
		Config.build("textures"),
	}
	if mapped then
		for _, a in
			{ "--mapped", "--pack", "kit/vfx/fxfinish.py", "--registry", Config.path("vfx") .. "/_textures.json" }
		do
			table.insert(argv, a)
		end
	else
		table.insert(argv, "--plain")
	end
	return Run.content(if mapped then "comp sheets (mapped)" else "comp sheets", Run.tool("python"), argv)
end

function Content.fxRenderStep(): Run.Step?
	if not fxSpecs() then
		return nil
	end
	return Content.blenderStep("fx renders", "kit/vfx/fxlab.py", {
		"--specs",
		Config.path("textures"),
		"--out",
		Config.build("fxlab"),
	})
end

function Content.fxFinishStep(): Run.Step?
	if not fxSpecs() then
		return nil
	end
	return Run.content("fx finish", Run.tool("python"), {
		"kit/vfx/fxfinish.py",
		"--skip-derived", -- (a sheet baked FROM a packed texture - a dissolve - is baked and packed by its own step, next)
		"--specs",
		Config.path("textures"),
		"--frames",
		Config.build("fxlab"),
		"--out",
		Config.build("textures"),
		"--registry",
		Config.path("vfx") .. "/_textures.json",
	})
end

-- `kit vfx play <name> [--views cine,player] [--record] [--port 47811]`: the browser player (kit/vfx/player) — the
-- preset at full frame rate in any browser with a scrub bar, layer mutes and live metrics; `--record` renders every
-- frame at 24 fps to build/vfx/booth/<name>_play_<view>.mp4 + <name>_play.metrics.json (open the printed URL; the
-- page records itself and the server exits). Builds build/vfx/play/<name>.json (preset + texture / sound urls +
-- views) and serves it from the kit's local capture server.
-- kit vfx expand <name> [--variant v]: the expanded preset (beats / use / variants applied) as JSON on stdout — what
-- the game, the booth and the player receive; diff two of them to prove a refactor onto parts changed nothing
-- the scene gate, defined further down (assigned after it): vfxExpand --check uses it
local sceneGateFwd: ((string, string, any, { [string]: boolean }) -> { string })? = nil
local methodsGateFwd: ((string, string, any) -> { string })? = nil

function Content.vfxExpand(name: string?, rest: { string }): number
	if not name then
		return Run.report(
			"vfx",
			{},
			C.USAGE,
			"vfx expand: needs a preset name",
			"lune run kit vfx expand <name> [--variant v]"
		)
	end
	local path = `{Config.path("vfx")}/{name}.json`
	if not fs.isFile(path) then
		return Run.report("vfx", {}, C.USAGE, `vfx expand: no preset {path}`, "lune run kit new vfx <name>")
	end
	local preset, issues = expandPreset(serde.decode("json", fs.readFile(path)), flagValue(rest, "--variant"))
	-- --check: the gate's own checks on this ONE preset, in a second (kit vfx director round runs it before recording):
	-- the validator on the preset AND every variant, the scene gate (an original's brief + the owner's go-ahead), and a
	-- part validated as a part (review 2026-10-24: the first version checked the base preset only and no scene)
	if table.find(rest, "--check") then
		local dir = Config.path("vfx")
		local registry = serde.decode("json", fs.readFile(dir .. "/_textures.json"))
		local meshesPath = dir .. "/_meshes.json"
		local meshes = if fs.isFile(meshesPath) then serde.decode("json", fs.readFile(meshesPath)) else {}
		local raw = serde.decode("json", fs.readFile(path))
		local function addErrors(list: { any }, label: string?)
			for _, issue in list do
				if issue.severity == "error" then
					table.insert(
						issues,
						if label then { path = `{label}: {issue.path}`, message = issue.message } else issue
					)
				end
			end
		end
		if string.sub(name, 1, 6) == "parts/" then
			addErrors(VfxValidate.preset(name, VfxCompose.partAsPreset(raw), registry, meshes))
		else
			addErrors(VfxValidate.preset(name, preset, registry, meshes))
			for _, v in VfxCompose.variants(raw) do
				local ex, compose = expandPreset(raw, v)
				addErrors(compose, `{name}@{v}`)
				addErrors(VfxValidate.preset(`{name}@{v}`, ex, registry, meshes), `{name}@{v}`)
			end
			local grandfathered = {}
			if fs.isFile("kit/vfx/scene_gate.json") then
				for _, n in serde.decode("json", fs.readFile("kit/vfx/scene_gate.json")).grandfathered do
					grandfathered[n] = true
				end
			end
			if sceneGateFwd then
				for _, problem in sceneGateFwd(dir, name, raw, grandfathered) do
					table.insert(issues, { path = "scene", message = problem, severity = "error" })
				end
			end
			if methodsGateFwd then
				for _, problem in methodsGateFwd(dir, name, raw) do
					table.insert(issues, { path = "methods", message = problem, severity = "error" })
				end
			end
		end
	end
	for _, issue in issues do
		stdio.ewrite(`{issue.path}: {issue.message}\n`)
	end
	stdio.write(serde.encode("json", preset, true) .. "\n")
	return if #issues == 0 then 0 else 1
end

-- kit vfx judge <name> [--record verdict.json]: the packet for a FRESH judge (sheets, metrics, the owner's reference
-- frames from assets/effects/refs/<name>/, PROMPT.md with the rubric) -> build/judge/vfx/<name>; --record validates
-- the judge's verdict and keeps it as assets/effects/judge/<name>.json tied to the sheets it saw
function Content.vfxJudge(name: string?, rest: { string }): number
	if not name then
		return Run.report(
			"vfx",
			{},
			C.USAGE,
			"vfx judge: name the preset",
			"lune run kit vfx judge <name> [--record verdict.json]"
		)
	end
	local record = flagValue(rest, "--record")
	local packet = `{Config.build("judge")}/vfx/{name}`
	local args = if record
		then {
			"kit/vfx/judge.py",
			"record",
			"--name",
			name,
			"--packet",
			packet,
			"--verdict",
			record,
			"--effects",
			Config.path("vfx"),
		}
		else {
			"kit/vfx/judge.py",
			"packet",
			"--name",
			name,
			"--out",
			packet,
			"--booth",
			Config.build("vfx") .. "/booth",
			"--effects",
			Config.path("vfx"),
			"--refs",
			Config.path("vfx") .. "/refs",
		}
	local step = Run.content(if record then "vfx judge record" else "vfx judge packet", Run.tool("python"), args)
	local r = step.result or {}
	return Run.report(
		"vfx",
		{ step },
		if step.ok then C.PASS else C.CONTENT,
		r.summary or "vfx judge: crashed",
		r.next_action or "read the error above"
	)
end

-- the scene a preset plays in (booth.scene): nil / "bare" = no scene file (the default arena / none), a name = the
-- scene file kit/vfx/scenes/<name>.json both renderers build from - G2, the 2-fighter arena (LIMITATIONS_FIXES_V4 3.4
-- step 1; checked by kit/vfx/duel.py) -> (the scene, why it cannot be used)
local function vfxScene(sceneName: any): (any?, string?)
	if sceneName == nil or sceneName == "bare" then
		return nil, nil
	end
	if type(sceneName) ~= "string" or not string.match(sceneName, "^[a-z][a-z0-9_]*$") then
		return nil, `booth.scene {tostring(sceneName)}: "bare" or a scene name (kit/vfx/scenes/<name>.json)`
	end
	local path = `kit/vfx/scenes/{sceneName}.json`
	if not fs.isFile(path) then
		return nil, `booth.scene "{sceneName}": no scene file {path}`
	end
	local ok, scene = pcall(serde.decode, "json", fs.readFile(path))
	if not ok or type(scene) ~= "table" or type(scene.fighters) ~= "table" then
		return nil, `booth.scene "{sceneName}": {path} is not a scene (no fighters)`
	end
	return scene, nil
end

-- the kit's CALIBRATION PROBES (kit/vfx/probes/<name>.json): version-3 presets that are measuring instruments, not
-- pieces - G2's g2_duel, the set the player and the Studio booth both record under each judging sky so
-- kit/vfx/calibrate.py can fit CAL from data (LIMITATIONS_FIXES_V4 3.4 step 1 / 13.3.1). They live with the kit, OUT
-- of the effects folder, so the quality locks (scene breakdown, lessons sheet, the verdict cap) and the library never
-- see them as a new unjudged piece - while a real new preset in the effects folder is still refused. kit vfx play and
-- kit vfx booth find a name in the effects folder first, then here -> (the path, is it a probe)
local VFX_PROBES = "kit/vfx/probes"
local function vfxPresetPath(name: string): (string, boolean)
	local path = `{Config.path("vfx")}/{name}.json`
	if fs.isFile(path) then
		return path, false
	end
	local probe = `{VFX_PROBES}/{name}.json`
	if string.match(name, "^[a-z][a-z0-9_]*$") and fs.isFile(probe) then
		return probe, true
	end
	return path, false
end
Content.vfxPresetPath = vfxPresetPath

-- the four judging skies, the player's names (kit/vfx/player/player.js SKIES) and the Studio booth's (kit/vfx/booth.luau
-- SKIES): `--sky` on kit vfx play and kit vfx booth, so kit/vfx/calibrate.py measures one against the other under each
-- (LIMITATIONS_FIXES_V4 13.3.1) -> (the sky: given, else the preset's booth.sky, else night; why it cannot be used)
local VFX_SKIES = { "night", "day", "overcast", "sunset" }
local function vfxSky(given: any, preset: any): (string, string?)
	local sky = given
	if sky == nil and type(preset) == "table" and type(preset.booth) == "table" then
		sky = preset.booth.sky
	end
	if sky == nil then
		return "night", nil
	end
	if type(sky) ~= "string" or not table.find(VFX_SKIES, sky) then
		return "night", `sky "{tostring(sky)}" is not a judging sky ({table.concat(VFX_SKIES, " | ")})`
	end
	return sky, nil
end

function Content.vfxPlay(name: string?, rest: { string }): number
	if not name then
		return Run.report("vfx", {}, C.USAGE, "vfx play: needs a preset name", "lune run kit vfx play <name>")
	end
	-- --animatic: the timing animatic of a scene SET (kit vfx animatic <set> made it: a generated preset of flat
	-- shapes in build/, never in the effects folder). Its run is <set>_animatic: its own bundle and recordings
	local animatic = table.find(rest, "--animatic") ~= nil
	-- --kept <folder>: the fracture plans, fields and point clouds a preset names are read from that folder's
	-- fractures/, fields/, points/ instead of the effects folder's (a made preset of the kit's own proofs, played
	-- from build/ with --animatic: its kept files are never put into a project's assets)
	local keptRoot = flagValue(rest, "--kept") or Config.path("vfx")
	local path = if animatic then `{Config.build("vfx")}/animatic/{name}.json` else vfxPresetPath(name)
	if not fs.isFile(path) then
		return Run.report(
			"vfx",
			{},
			C.USAGE,
			`vfx play: no {if animatic then "animatic" else "preset"} {path}`,
			if animatic then `lune run kit vfx animatic {name}` else "lune run kit new vfx <name>"
		)
	end
	local preset = serde.decode("json", fs.readFile(path))
	if preset.version ~= 3 then
		return Run.report(
			"vfx",
			{},
			C.USAGE,
			`vfx play: {name} is a version {preset.version or 1} preset`,
			"version 3 presets only"
		)
	end
	local registry = serde.decode("json", fs.readFile(Config.path("vfx") .. "/_textures.json"))
	local variant = flagValue(rest, "--variant")
	-- an evolve variant in the PLAYER (mission 02-vfx v2: the player is the studio): <round>/<k> ->
	-- build/vfx/evolve/<name>/round_<round>/v<k>.json, an overlay merged over the preset's own before it expands
	local evolveSpec = flagValue(rest, "--evolve")
	local evolveTag: string? = nil
	if evolveSpec then
		local r, k = string.match(evolveSpec, "^(%d+)/(%d+)$")
		local overlayPath = `{Config.build("vfx")}/evolve/{name}/round_{r or "?"}/v{k or "?"}.json`
		if not (r and k and fs.isFile(overlayPath)) then
			return Run.report(
				"vfx",
				{},
				C.USAGE,
				`vfx play: no evolve overlay {overlayPath}`,
				`lune run kit vfx evolve {name} (then --evolve <round>/<k>)`
			)
		end
		local e = serde.decode("json", fs.readFile(overlayPath))
		local base = if type(preset.overlay) == "table" then preset.overlay else {}
		local mute = {}
		for _, list in { base.mute or {}, e.mute or {} } do
			for _, m in list do
				table.insert(mute, m)
			end
		end
		preset.overlay = {
			time = (base.time or 1) * (e.time or 1),
			scale = (base.scale or 1) * (e.scale or 1),
			saturate = (base.saturate or 0) + (e.saturate or 0),
			mute = mute,
		}
		evolveTag = `evo{r}v{k}`
	end
	-- --with a,b: other presets played on the same clock (the pros judge effects together, in the fight - a hero hit
	-- must read over the others); each joins as a part ("with_<name>.<layer>"), expanded first
	local withList = flagValue(rest, "--with")
	local blockout = table.find(rest, "--blockout") ~= nil
	local composeIssues
	if withList then
		local withParts = {}
		preset.use = if type(preset.use) == "table" then preset.use else {}
		for _, other in string.split(withList, ",") do
			local opath = `{Config.path("vfx")}/{other}.json`
			if not fs.isFile(opath) then
				return Run.report(
					"vfx",
					{},
					C.USAGE,
					`vfx play: --with {other}: no preset {opath}`,
					"name an existing preset"
				)
			end
			local o = expandPreset(serde.decode("json", fs.readFile(opath)), nil)
			withParts[`__with_{other}`] = o
			preset.duration = math.max(preset.duration or 0, o.duration or 0)
			table.insert(preset.use, { part = `__with_{other}`, at = 0, as = `with_{other}` })
		end
		local fromDisk = partLoader(Config.path("vfx"))
		preset, composeIssues = VfxCompose.expand(preset, {
			variant = variant,
			parts = function(n: string): any?
				return withParts[n] or fromDisk(n)
			end,
		})
	else
		preset, composeIssues = expandPreset(preset, variant)
	end
	if variant then
		name ..= "@" .. variant
	end
	local presetName = string.gsub(name, "@.*$", "")
	if evolveTag then
		name ..= "_" .. evolveTag -- its own bundle + recording: build/vfx/booth/<name>_evoRvK_play_<view>.mp4
	end
	-- a blockout / --with run gets its own bundle + recordings: it never overwrites the effect's real ones
	if blockout then
		name ..= "_blockout"
		evolveTag = evolveTag or "blockout"
	end
	if animatic then
		name ..= "_animatic"
		evolveTag = evolveTag or "animatic"
	end
	if withList then
		name ..= "_with_" .. string.gsub(withList, ",", "_")
		evolveTag = evolveTag or "with"
	end
	local errors = {}
	for _, list in { composeIssues, VfxValidate.preset(name, preset, registry, nil) } do
		for _, issue in list do
			if issue.severity == "error" then
				table.insert(errors, `{issue.path}: {issue.message}`)
			end
		end
	end
	if #errors > 0 then
		return Run.report("vfx", {}, C.CONTENT, `vfx play: {#errors} preset error(s)`, errors[1])
	end
	local textures = {}
	for key, entry in registry do
		-- kit textures are built into the PROJECT's build/textures (fxfinish; the record server serves /textures/ from there),
		-- a game's own into its build/textures (2026-11-10: with a game active only the game's folder was read, so every kit
		-- texture of a game's preset was left out of the bundle and its layers drew nothing in the player)
		if
			type(entry) == "table"
			and (fs.isFile(`build/textures/{key}.png`) or fs.isFile(`{Config.build("textures")}/{key}.png`))
		then
			textures[key] = { url = `/textures/{key}.png`, grid = entry.grid or 1 }
		end
	end
	local sounds = {}
	if fs.isDir(Config.build("sounds")) then
		for _, f in fs.readDir(Config.build("sounds")) do
			if string.sub(f, -4) == ".ogg" then
				sounds[string.sub(f, 1, -5)] = `/sounds/{f}`
			end
		end
	end
	local views = {}
	if fs.isFile("kit/vfx/views.json") then
		for k, v in serde.decode("json", fs.readFile("kit/vfx/views.json")) do
			if string.sub(k, 1, 1) ~= "_" then
				views[k] = v
			end
		end
	end
	local booth = preset.booth or {}
	-- the scene's own cameras sit under the preset's (G2: duel / hero / victim / cine on the two fighters)
	local scene, sceneWhy = vfxScene(booth.scene)
	if sceneWhy then
		return Run.report(
			"vfx",
			{},
			C.CONTENT,
			`vfx play: {sceneWhy}`,
			'booth.scene: "bare" or a kit/vfx/scenes name (g2)'
		)
	end
	for k, v in (if scene then scene.views else nil) or {} do
		views[k] = v
	end
	for k, v in booth.viewDefs or {} do
		views[k] = v
	end
	local flags = {}
	local i = 1
	while i <= #rest do
		if string.sub(rest[i], 1, 2) == "--" then
			local key = string.sub(rest[i], 3)
			local value = rest[i + 1]
			if value and string.sub(value, 1, 2) ~= "--" then
				flags[key] = value
				i += 2
			else
				flags[key] = true
				i += 1
			end
		else
			i += 1
		end
	end
	-- --sky <sky>: the judging sky this play is lit by (the preset's booth.sky otherwise); the player reports it in its
	-- metrics, so a recording is calibrated against the booth under the SAME sky (kit/vfx/calibrate.py --sky)
	local sky, skyWhy = vfxSky(if flags.sky == true then "" else flags.sky, preset)
	if skyWhy then
		return Run.report("vfx", {}, C.USAGE, `vfx play: {skyWhy}`, `--sky {table.concat(VFX_SKIES, "|")}`)
	end
	if flags.sky ~= nil then
		local b = table.clone(preset.booth or {})
		b.sky = sky
		preset.booth = b
	end
	local dir = Config.build("vfx") .. "/play"
	Config.ensureDir(dir)
	-- the MEASURED calibration of the player against the Studio booth (kit/vfx/calibrate.py fit ->
	-- assets/effects/_calibrated.json; LIMITATIONS_FIXES_V4 Phase 1 item 3): player.js lays it over its hand-set CAL
	local calPath = `{Config.path("vfx")}/_calibrated.json`
	local calibration = nil
	if fs.isFile(calPath) then
		local okCal, cal = pcall(serde.decode, "json", fs.readFile(calPath))
		calibration = if okCal and type(cal) == "table" then cal else nil
	end
	local bundle = {
		name = name,
		preset = preset,
		textures = textures,
		sounds = sounds,
		views = views,
		motion = booth.motion,
		blockout = if blockout then true else nil,
		calibration = calibration,
		scene = scene, -- the scene the player builds (nil: its default arena)
		sky = sky, -- the judging sky it is lit by (preset.booth.sky carries it to the player; --sky set it there)
	}
	-- fracture plans the preset's debris layers fly ("pieces"): they ride in the bundle too
	for _, el in preset.layers or {} do
		if type(el) == "table" and el.kind == "debris" and type(el.pieces) == "string" then
			local fp = `{keptRoot}/fractures/{el.pieces}.json`
			if not string.match(el.pieces, "^[a-z][a-z0-9_]*$") or not fs.isFile(fp) then
				return Run.report(
					"vfx",
					{},
					C.CONTENT,
					`vfx play: no fracture plan {fp}`,
					`lune run kit vfx fracture {el.pieces} --size w,d[,h]`
				)
			end
			bundle.fractures = bundle.fractures or {}
			bundle.fractures[el.pieces] = serde.decode("json", fs.readFile(fp))
			-- a "rest" layer's pieces are FLOWN with the layer's own life, gravity, speed and height before it is shown
			-- (kit vfx settle: the rule the game and the player run): one whose pieces are still moving when the fade
			-- starts is SAID here - only a piece on a method plan was held to it, and nothing else in the build flew it.
			-- A warning: the play goes on, so the fault can be looked at
			if el.rest == true then
				local settleArgs = { "kit/vfx/settle.py", el.pieces, "--plans-dir", `{keptRoot}/fractures` }
				for flag, value in
					{
						["--life"] = el.life,
						["--gravity"] = el.gravity,
						["--speed"] = el.speed,
						["--height"] = if type(el.point) == "table" then el.point[2] else nil,
					} :: { [string]: any }
				do
					-- (a speed of 0 is a speed: the slab does not move - the game and the player push nothing)
					if type(value) == "number" and (value > 0 or (flag == "--speed" and value == 0)) then
						table.insert(settleArgs, flag)
						table.insert(settleArgs, tostring(value))
					end
				end
				local settled = Run.content("vfx settle", Run.tool("python"), settleArgs)
				if not settled.ok then
					print(
						`warning: layer "{tostring(el.name)}" - kit vfx settle: {if settled.result
							then tostring(settled.result.summary)
							else "kit vfx settle did not run"}`
					)
				end
			end
		end
		-- authored vector fields the preset's swarm layers follow ("field": { name }): they ride in the bundle too
		if
			type(el) == "table"
			and el.kind == "swarm"
			and type(el.field) == "table"
			and type(el.field.name) == "string"
		then
			local fp = `{keptRoot}/fields/{el.field.name}.json`
			if not string.match(el.field.name, "^[a-z][a-z0-9_]*$") or not fs.isFile(fp) then
				return Run.report(
					"vfx",
					{},
					C.CONTENT,
					`vfx play: no field {fp}`,
					`lune run kit vfx field {el.field.name} --new vortex`
				)
			end
			local okField, fieldData = pcall(serde.decode, "json" :: any, fs.readFile(fp))
			if
				not okField
				or type(fieldData) ~= "table"
				or type(fieldData.elements) ~= "table"
				or #fieldData.elements == 0
			then
				return Run.report(
					"vfx",
					{},
					C.CONTENT,
					`vfx play: {fp} is not a field (no elements)`,
					`lune run kit vfx field {el.field.name} (it says what is wrong with the file)`
				)
			end
			bundle.fields = bundle.fields or {}
			bundle.fields[el.field.name] = fieldData
			-- its OWN checks too (kit vfx field: the air moves, stays under its top speed, carries specks) - only the method gate ran them, so a hand-edited file
			-- that was never run through the command reached the player and the game unchecked (a review leftover).
			-- A warning: the play goes on, so the fault can be looked at
			do
				local own = Run.content("vfx field check", Run.tool("python"), {
					"kit/vfx/field.py",
					el.field.name,
					"--out-dir",
					`{keptRoot}/fields`,
					"--look-dir",
					Config.build("vfx") .. "/field",
				})
				if not own.ok then
					print(
						`warning: layer "{tostring(el.name)}" - its field fails its own checks: {if own.result
							then tostring(own.result.summary)
							else `kit vfx field did not finish (exit {tostring(own.exit)})`}`
					)
				end
			end
		end
		-- point clouds the preset's swarm layers gather into ("cloud": { name }): they ride in the bundle too
		if
			type(el) == "table"
			and el.kind == "swarm"
			and type(el.cloud) == "table"
			and type(el.cloud.name) == "string"
		then
			local cp = `{keptRoot}/points/{el.cloud.name}.json`
			local okCloud, cloudData = false, nil :: any
			if string.match(el.cloud.name, "^[a-z][a-z0-9_]*$") and fs.isFile(cp) then
				okCloud, cloudData = pcall(serde.decode, "json" :: any, fs.readFile(cp))
			end
			if
				not okCloud
				or type(cloudData) ~= "table"
				or type(cloudData.points) ~= "table"
				or #cloudData.points < 8
				or #cloudData.points > 150
			then
				return Run.report(
					"vfx",
					{},
					C.CONTENT,
					`vfx play: no point cloud {cp}`,
					`lune run kit vfx points {el.cloud.name} --new ring   (or --picture <png>)`
				)
			end
			for _, pt in cloudData.points :: { any } do -- (a point that is not three numbers plays as NaN in the player)
				if
					type(pt) ~= "table"
					or type(pt[1]) ~= "number"
					or type(pt[2]) ~= "number"
					or type(pt[3]) ~= "number"
				then
					return Run.report(
						"vfx",
						{},
						C.CONTENT,
						`vfx play: {cp} has a point that is not [x, y, z]`,
						`lune run kit vfx points {el.cloud.name} (it says what is wrong with the file)`
					)
				end
			end
			bundle.points = bundle.points or {}
			bundle.points[el.cloud.name] = cloudData
			-- its OWN checks too (kit vfx points: a figure, not a clump or a line, that its particles reach) - only the method gate ran them, so a hand-edited file
			-- that was never run through the command reached the player and the game unchecked (a review leftover).
			-- A warning: the play goes on, so the fault can be looked at
			do
				local own = Run.content("vfx points check", Run.tool("python"), {
					"kit/vfx/points.py",
					el.cloud.name,
					"--out-dir",
					`{keptRoot}/points`,
					"--look-dir",
					Config.build("vfx") .. "/points",
				})
				if not own.ok then
					print(
						`warning: layer "{tostring(el.name)}" - its point cloud fails its own checks: {if own.result
							then tostring(own.result.summary)
							else `kit vfx points did not finish (exit {tostring(own.exit)})`}`
					)
				end
			end
		end
	end
	-- mesh sequences the preset plays (shape "seq"): their baked frames ride in the bundle
	for _, el in preset.layers or {} do
		if
			type(el) == "table"
			and el.shape == "seq"
			and type(el.params) == "table"
			and type(el.params.seq) == "string"
		then
			local sp = `{Config.path("vfx")}/seq/{el.params.seq}.json`
			if fs.isFile(sp) then
				bundle.seq = bundle.seq or {}
				bundle.seq[el.params.seq] = serde.decode("json", fs.readFile(sp))
			else
				return Run.report(
					"vfx",
					{},
					C.CONTENT,
					`vfx play: no mesh sequence {sp}`,
					`python kit/vfx/meshseq.py {el.params.seq} --recipe billow`
				)
			end
		end
	end
	fs.writeFile(`{dir}/{name}.json`, serde.encode("json", bundle, true) .. "\n")
	-- every variant is bundled beside the base so the viewer can switch between them on one clock
	if not variant and not evolveTag then
		local raw = serde.decode("json", fs.readFile(path))
		for _, v in VfxCompose.variants(raw) do
			local expandedV, issuesV = expandPreset(raw, v)
			if #VfxValidate.errors(issuesV) == 0 then
				local b2 = {
					name = `{name}@{v}`,
					preset = expandedV,
					textures = textures,
					sounds = sounds,
					views = views,
					motion = booth.motion,
					seq = bundle.seq,
					fractures = bundle.fractures,
					fields = bundle.fields,
					points = bundle.points,
				}
				-- a variant that names a kept file of its OWN (another plan, field or cloud than the base preset's) carried
				-- the base's only: its layer then flew nothing in the player. Read as it is (its own command checked it)
				local function also(folder: string, kept: string?)
					local bag: any = b2
					local have = bag[folder]
					if
						type(kept) ~= "string"
						or not string.match(kept, "^[a-z][a-z0-9_]*$")
						or (have and have[kept])
					then
						return
					end
					local fp = `{keptRoot}/{folder}/{kept}.json`
					if not fs.isFile(fp) then
						print(
							`warning: variant {v} names {folder}/{kept}.json, which is not there: its layer flies nothing`
						)
					end
					if fs.isFile(fp) then
						local okKept, data = pcall(serde.decode, "json" :: any, fs.readFile(fp))
						if okKept and type(data) == "table" then
							local copy = if have then table.clone(have) else {}
							copy[kept] = data
							bag[folder] = copy
						end
					end
				end
				for _, el in expandedV.layers or {} do
					if type(el) == "table" then
						if el.kind == "debris" then
							also("fractures", el.pieces)
						elseif el.kind == "swarm" then
							also("fields", if type(el.field) == "table" then el.field.name else nil)
							also("points", if type(el.cloud) == "table" then el.cloud.name else nil)
						end
					end
				end
				fs.writeFile(`{dir}/{name}@{v}.json`, serde.encode("json", b2, true) .. "\n")
			end
		end
	end
	local port = tostring(flags.port or 47811)
	local viewList = if type(flags.views) == "string" then flags.views else "cine"
	local url = `http://127.0.0.1:{port}/lib/index.html?name={name}&view={string.split(viewList, ",")[1]}`
	-- --detail Low | Medium | High: the effect as that detail level plays it (src/kit/VfxBudget: the layers a level drops
	-- are not drawn, the ones it cuts emit their share) - to LOOK at a tier beside the whole effect
	local detail = if flags.detail == "Low"
			or flags.detail == "Medium"
			or flags.detail == "High"
		then flags.detail
		else nil
	if flags.detail ~= nil and detail == nil then
		return Run.report(
			"vfx",
			{},
			C.USAGE,
			"vfx play: --detail is Low, Medium or High",
			"lune run kit vfx play <name> --detail Low"
		)
	end
	-- (a level is to LOOK at: frames baked or a film recorded at a cut level would become what every level shows)
	if detail and (flags.frames or flags.record) then
		return Run.report(
			"vfx",
			{},
			C.USAGE,
			"vfx play: --detail is for looking; --frames and --record take the whole effect",
			"run it without --detail"
		)
	end
	if detail then
		url ..= `&detail={detail}`
	end
	if flags.frames then -- bake: the page draws every impact frame layer once per view and posts it; frames.py registers them
		url ..= `&frames=1&views={viewList}`
	elseif flags.record then
		url ..= `&record=1&views={viewList}&fps={tostring(flags.fps or 24)}`
	end
	print(`player: {url}`)
	print(`serving (Ctrl-C to stop{if flags.record then "; exits by itself when the page has recorded" else ""})`)
	local step = Run.content("vfx play server", Run.tool("python"), {
		"kit/vfx/capture.py",
		"serve",
		"--name",
		`{name}_play`,
		"--preset",
		-- the hot-reload watcher re-expands the file on disk (an animatic has none in the effects folder: its own
		-- run name, so nothing of that name is watched)
		if animatic then name elseif evolveTag then presetName else name,
		"--port",
		port,
		"--focus",
		"0",
		-- (the hot reload reads kept files again from the folder this play read them from)
		"--kept",
		keptRoot,
	})
	if flags.frames then
		local bake =
			Run.content("vfx frames", Run.tool("python"), { "kit/vfx/frames.py", name, string.split(viewList, ",")[1] })
		local saved = Content.vfxVaultStep()
		return Run.report(
			"vfx",
			{ step, bake, saved },
			if bake.ok and saved.ok then C.PASS else C.CONTENT,
			if bake.ok then `vfx frames: {name} baked` else `vfx frames: {name} not baked`,
			if bake.ok
				then "lune run kit vfx (finish + register the frame plates), then kit upload --only frame_"
					.. name
					.. "_ when the game needs them"
				else "read the step above"
		)
	end
	-- the recording is something the pipeline made: into the library with the effect (the owner's rule)
	local saved = if step.ok and flags.record and not animatic then Content.vfxVaultStep() else nil
	local steps = if saved then { step, saved } else { step }
	local summary = if step.ok then `vfx play: {name} recorded` else `vfx play: {name} served (no recording)`
	local nextAction = if step.ok
		then "LOOK at build/vfx/booth/" .. name .. "_play_<view>.mp4 and read " .. name .. "_play.metrics.json"
		else `open {url}`
	-- dailies (the VFX studio-route plan, V0, 2026-11-12): every recorded play is laid beside its scene frame by
	-- frame, every frame large, and the summary ENDS with `LOOK: <folder>` - a session read contact sheets of
	-- thumbnails and never the motion, and had to think of asking for more. The dailies never change the play's
	-- pass / fail: a recording with no scene beside it still shows its own frames.
	if step.ok and flags.record and not animatic then -- (kit vfx animatic lays its own recording beside the scene)
		local firstView = string.split(viewList, ",")[1]
		local dailies = Run.content("vfx dailies", Run.tool("python"), {
			"kit/vfx/dailies.py",
			presetName,
			"--run",
			name,
			"--view",
			firstView,
			"--effects",
			Config.path("vfx"),
		})
		table.insert(steps, dailies)
		summary, nextAction = require("../lib/vfxdailies").playReport(summary, nextAction, dailies.result, name)
	end
	-- the picture on the sound (the V3 doc, VFX stage E.3: "<= +-1 frame visual peak vs SFX transient"): every
	-- recorded play of an effect with sound layers is held to it; one with none (or none built) says "unchecked"
	local timing = nil
	if step.ok and flags.record and not animatic then
		timing = Run.content("vfx timing", Run.tool("python"), {
			"kit/vfx/timing.py",
			presetName,
			"--run",
			name,
			"--view",
			string.split(viewList, ",")[1],
		})
		table.insert(steps, timing)
		-- "unchecked" (no sound layer, or none built) is not a failure (timing.py exits 0 on it), but a step is ok
		-- only on "pass": every soundless effect's recorded play reported CONTENT, "OFF its sound" (found on G2)
		if not timing.ok and timing.result and timing.result.status == "unchecked" then
			timing.ok = true
		end
		if not timing.ok then
			summary ..= " - the picture is OFF its sound (kit vfx timing: more than one frame)"
		end
	end
	return Run.report(
		"vfx",
		steps,
		if step.ok and (saved == nil or saved.ok) and (timing == nil or timing.ok) then C.PASS else C.CONTENT,
		summary,
		nextAction
	)
end

-- `kit vfx booth <name> [--match <place>]`: a version-3 preset judged in the REAL engine. Writes the booth job (views,
-- moments, time scale, the preset and what it uses) and the run's Studio scripts (kit/tools/studio_capture.py: the
-- job inside them, kit/vfx/booth.luau installed once into the place), and prints the steps: the capture
-- (kit/vfx/capture.py studio, reading the scratch place's window), the Studio script, its answer saved for the
-- capture; the result is build/vfx/booth/<name>_all.png (+ one sheet per camera view).
function Content.vfxBooth(name: string?, rest: { string }): number
	if not name then
		return Run.report("vfx", {}, C.USAGE, "vfx booth: needs a preset name", "lune run kit vfx booth <name>")
	end
	local path = vfxPresetPath(name)
	if not fs.isFile(path) then
		return Run.report("vfx", {}, C.USAGE, `vfx booth: no preset {path}`, "lune run kit new vfx <name>")
	end
	local preset = serde.decode("json", fs.readFile(path))
	if preset.version ~= 3 then
		return Run.report(
			"vfx",
			{},
			C.USAGE,
			`vfx booth: {name} is a version {preset.version or 1} preset`,
			`version 1/2 presets preview with: lune run kit vfx {name}`
		)
	end
	local registry = serde.decode("json", fs.readFile(Config.path("vfx") .. "/_textures.json"))
	local composeIssues
	preset, composeIssues = expandPreset(preset, flagValue(rest, "--variant"))
	local errors = {}
	for _, list in { composeIssues, VfxValidate.preset(name, preset, registry, nil) } do
		for _, issue in list do
			if issue.severity == "error" then
				table.insert(errors, `{issue.path}: {issue.message}`)
			end
		end
	end
	if #errors > 0 then
		return Run.report("vfx", {}, C.CONTENT, `vfx booth: {#errors} preset error(s)`, errors[1])
	end
	local missing, seen = {}, {}
	for _, el in preset.layers do
		local key = el.texture
		if key and not seen[key] then
			seen[key] = true
			local e = registry[key]
			if type(e) == "table" and (e.id == nil or e.id == "") then
				table.insert(missing, key)
			end
		end
	end
	local job: { [string]: any } = { timeScale = 0.5, settle = 0.45, variant = flagValue(rest, "--variant") }
	local i = 1
	while i <= #rest do
		local flag, value = rest[i], rest[i + 1]
		if flag == "--views" and value then
			job.views = string.split(value, ",")
			for _, v in job.views do
				if not string.match(v, "^[%w_%-]+$") or #v > 40 then
					return Run.report(
						"vfx",
						{},
						C.USAGE,
						`vfx booth: view name "{v}"`,
						"view names: letters, digits, _ and - (player, side, hero, or a viewDefs name)"
					)
				end
			end
		elseif flag == "--moments" and value then
			local ts = {}
			for _, t in string.split(value, ",") do
				local n = tonumber(t)
				if n then
					table.insert(ts, n)
				end
			end
			job.moments = ts
		elseif flag == "--sky" and value then
			job.sky = value -- one of the player's four judging skies (checked below)
		elseif flag == "--clock" and value then
			job.clock = tonumber(value)
		elseif flag == "--mute" and value then
			job.mute = {} -- layer names, or prefixes ending in * (beam_*): skipped this run
			for _, m in string.split(value, ",") do
				local layer = string.match(m, "^%s*(.-)%s*$")
				if layer and layer ~= "" then
					table.insert(job.mute, layer)
				end
			end
		elseif flag == "--timescale" and value then
			job.timeScale = tonumber(value)
		elseif flag == "--stage" and value then
			-- the presentation (mission 02-vfx 5.8): assets/effects/stages/<value>.json = { actor, post, ground } merged
			-- into the job - the R6 rig on a real clip, the source's grade, a reacting ground; the preset stays as it is
			local stagePath = `{Config.path("vfx")}/stages/{value}.json`
			if not fs.isFile(stagePath) then
				return Run.report(
					"vfx",
					{},
					C.USAGE,
					`vfx booth: no stage {stagePath}`,
					"write it: { actor, post, ground }"
				)
			end
			local st = serde.decode("json", fs.readFile(stagePath))
			for _, key in { "actor", "post", "ground" } do
				job[key] = st[key]
			end
			if type(st.viewDefs) == "table" then -- the stage's own cameras (a close view on the rig)
				job.viewDefs = st.viewDefs
			end
			if type(st.actor) == "table" and not fs.isFile(`src/animations/{st.actor.clip}.model.json`) then
				return Run.report(
					"vfx",
					{},
					C.USAGE,
					`vfx booth: stage {value}: no compiled clip src/animations/{st.actor.clip}.model.json`,
					"the anim lane's clip: lune run kit anim <Clip>"
				)
			end
			job.stageName = value
		elseif flag == "--evolve" and value then
			-- an evolve variant (kit vfx evolve, mission 02-vfx 5.6): <round>/<k> -> build/vfx/evolve/<name>/round_<round>/v<k>.json,
			-- an overlay (time / scale / saturate / mute) the booth plays over the preset - the preset is never edited
			local r, k = string.match(value, "^(%d+)/(%d+)$")
			local overlayPath = `{Config.build("vfx")}/evolve/{name}/round_{r or "?"}/v{k or "?"}.json`
			if not (r and k and fs.isFile(overlayPath)) then
				return Run.report(
					"vfx",
					{},
					C.USAGE,
					`vfx booth: no evolve overlay {overlayPath}`,
					`lune run kit vfx evolve {name} (then --evolve <round>/<k>)`
				)
			end
			job.evolve = serde.decode("json", fs.readFile(overlayPath))
			job.evolveName = `evo{r}v{k}`
		elseif flag == "--surface" and value then
			-- an engine experiment, this run only: every textured mesh layer drawn as a SurfaceAppearance (texture alpha
			-- + glow, the measured route; vault vfx/refs/engine-facts) at this emissive strength - compare with a plain run
			job.surface = tonumber(value)
		end
		i += 2
	end
	-- the light: --sky, else the preset's booth.sky (what the player judges it under), else night (booth.luau SKIES)
	local sky, skyWhy = vfxSky(job.sky, preset)
	if skyWhy then
		return Run.report("vfx", {}, C.USAGE, `vfx booth: {skyWhy}`, `--sky {table.concat(VFX_SKIES, "|")}`)
	end
	job.sky = sky
	local dir = Config.build("vfx") .. "/booth"
	Config.ensureDir(dir)
	local runName = name
		.. (if job.stageName then `_{job.stageName}` else "")
		.. (if job.evolveName then `_{job.evolveName}` else "")
		.. (if job.surface then "_surface" else "")
	-- everything the Studio side plays travels INSIDE the run's script (Studio cannot fetch it): the preset as written
	-- (the place's VfxCompose expands it there, after an evolve overlay), the parts it uses, the textures it names and
	-- the camera views (kit/vfx/views.json under the stage's / the job's own)
	local presetDoc = serde.decode("json", fs.readFile(path))
	local loadPart, usedParts = partLoader(Config.path("vfx")), {}
	VfxCompose.expand(serde.decode("json", fs.readFile(path)), {
		variant = job.variant,
		parts = function(partName: string): any?
			local p = loadPart(partName)
			if p ~= nil then
				usedParts[partName] = p
			end
			return p
		end,
	})
	local named = {}
	local function textureKeys(v: any)
		if type(v) == "string" and type(registry[v]) == "table" then
			named[v] = registry[v]
		elseif type(v) == "table" then
			for _, x in v do
				textureKeys(x)
			end
		end
	end
	textureKeys(preset)
	local views = {}
	if fs.isFile("kit/vfx/views.json") then
		for k, v in serde.decode("json", fs.readFile("kit/vfx/views.json")) do
			if string.sub(k, 1, 1) ~= "_" then
				views[k] = v
			end
		end
	end
	-- the scene the preset plays in (booth.scene, G2: the 2-fighter arena): the booth builds the SAME layout the
	-- player does from it, its cameras under the stage's / the job's own
	local scene, sceneWhy = vfxScene((presetDoc.booth or {}).scene)
	if sceneWhy then
		return Run.report(
			"vfx",
			{},
			C.CONTENT,
			`vfx booth: {sceneWhy}`,
			'booth.scene: "bare" or a kit/vfx/scenes name (g2)'
		)
	end
	for k, v in (if scene then scene.views else nil) or {} do
		views[k] = v
	end
	for k, v in job.viewDefs or {} do
		views[k] = v
	end
	job.scene = scene
	job.viewDefs, job.name, job.preset = views, name, name
	job.presetDoc, job.parts, job.textures = presetDoc, usedParts, named
	local jobPath = `{dir}/{runName}.job.json`
	fs.writeFile(jobPath, serde.encode("json", job, true) .. "\n")
	local made, why = studioSnippets("vfx_booth", jobPath, `{dir}/{runName}`)
	if not made then
		return Run.report(
			"vfx",
			{},
			C.CONTENT,
			`vfx booth: the Studio script was not written: {why}`,
			"python kit/tools/studio_capture.py snippet vfx_booth --job "
				.. jobPath
				.. " --out "
				.. dir
				.. "/"
				.. runName
		)
	end
	local match = flagValue(rest, "--match") or "KitPlaytestScratch"
	studioSteps(
		`python kit/vfx/capture.py studio --name {runName} --job {jobPath} --match {match} --out {dir} --crop 0.03,0.06,0.04,0`,
		made.files,
		`{dir}/{runName}.result.json`,
		`when the capture exits: LOOK at {dir}/{runName}_all.png (every camera view, every moment)`
	)
	return Run.report(
		"vfx",
		{},
		C.PASS,
		`vfx booth: {name} ready ({#preset.layers} layers)`
			.. (if #missing > 0 then `; NOT uploaded yet: {table.concat(missing, ", ")}` else ""),
		if #missing > 0
			then `upload first (else they play as stand-ins): lune run kit upload --only build/textures/{missing[1]}.png`
			else "run steps 1 + 2 above, then look at the sheet"
	)
end

-- effect meshes: assets/effects/meshes/*.json -> Blender -> build/vfxmeshes/<name>.fbx/.obj + _meshes.json registry
function Content.vfxMeshesStep(): Run.Step?
	local specs = Config.path("vfx") .. "/meshes"
	if not fs.isDir(specs) or #listNames(specs, "^(.+)%.json$") == 0 then
		return nil
	end
	return Content.blenderStep("vfx meshes", "kit/vfx/meshes.py", {
		"--specs",
		specs,
		"--out",
		Config.build("vfxmeshes"),
		"--registry",
		Config.path("vfx") .. "/_meshes.json",
	})
end

-- simulate presets -> build/vfx/<name>.png frame strips + measured visible_until / peak particles (cut-off gate)
function Content.vfxPreviewStep(names: { string }?, presets: string?, out: string?): Run.Step
	if presets == nil and Config.isKitSource() and not fs.isDir(Config.path("vfx")) then
		return Run.step("vfx preview", true, "", { summary = "SKIPPED - kit-source repo (no project assets/effects)" })
	end
	local args = {
		"kit/vfx/preview.py",
		"--presets",
		presets or Config.path("vfx"),
		"--textures",
		Config.build("textures"),
		"--out",
		out or Config.build("vfx"),
	}
	for _, n in names or {} do
		table.insert(args, n)
	end
	return Run.content("vfx preview", Run.tool("python"), args)
end

-- validate every project preset + the texture registry (in-process, same validator the game runs)
-- the VFX library (kit/vfx/vault.py): the owner's rule (2026-10-12) — everything the VFX pipeline makes is saved,
-- packaged by part and named properly, in library/vfx (effects with their previews, recordings, verdicts and every
-- earlier version; every part, texture, mesh). `kit vfx` and `kit vfx play --record` save; `kit verify` runs the check
local function vfxVaultArgs(cmd: string): { string }
	return {
		"kit/vfx/vault.py",
		cmd,
		"--effects",
		Config.path("vfx"),
		"--textures",
		Config.path("textures"),
		"--build",
		Config.path("build"),
	}
end

function Content.vfxVaultStep(): Run.Step
	return Run.content("vfx vault", Run.tool("python"), vfxVaultArgs("save"))
end

function Content.vfxVaultCheckStep(): Run.Step
	return Run.content("vfx vault", Run.tool("python"), vfxVaultArgs("check"))
end

-- the VFX route's tools (mission 02-vfx): `kit vfx <tool> ...` runs the script with the rest of the arguments
local VFX_ROUTE_TOOLS: { [string]: string } = {
	breakdown = "kit/vfx/breakdown.py",
	chart = "kit/vfx/chart.py",
	evolve = "kit/vfx/evolve.py",
	cost = "kit/vfx/cost.py",
	surfaces = "kit/vfx/surfaces.py",
	bar = "kit/vfx/bar.py bar", -- "<script> <its sub-command>"
	measure = "kit/vfx/bar.py measure",
	timing = "kit/vfx/timing.py", -- does the picture land on the sound (onsets vs the player recording)
	style = "kit/vfx/style.py", -- does the preset speak its game's VFX style guide (assets/effects/styles)
	director = "kit/vfx/director.py", -- the creative director: learn / coverage / new / check / review (originals)
	swarm = "kit/vfx/swarmsim.py", -- a swarm layer's mass over time without recording (the player's maths in numpy)
	keyread = "kit/vfx/keyread.py", -- the test frame beside the scene's key frame: coverage, light, layers, detail, pieces
	-- dailies (the VFX studio-route plan, V0): the recording beside its scene FRAME BY FRAME, every frame 640 px or
	-- more, the two light curves over each other; `kit vfx play --record` runs it by itself (Content.vfxPlay)
	dailies = "kit/vfx/dailies.py",
	-- the style sheet (V1): every beat's look, ours beside the scene's, on one page the owner approves
	-- (`kit approve vfx <effect> ... --stage style`). Not "style": that name is the style-guide check above
	stylesheet = "kit/vfx/stylesheet.py",
	-- the timing animatic (V2): a scene set's motion in flat shapes at the chart's timing, recorded in the player
	-- and laid beside the scene - approved before the look is built (`kit approve vfx <set> ... --stage animatic`)
	animatic = "kit/vfx/animatic.py",
	-- the trace (the owner's VFX method list, 2026-11-13: hand-drawn effects, rotoscoping; the plan's V3, its trace
	-- half): a beat's frames at the clip's own rate -> the scene's DRAWINGS as outline curves, flat tones and holds
	-- (curves and numbers kept, never a frame); the LOOK pictures lay each trace on its frame
	trace = "kit/vfx/shapetrace.py",
	-- ink (the same audit, stage 2; the plan's V3, its ink half): a trace's drawings drawn again at the size Roblox
	-- shows - one cell a drawing, in-betweens point to point - into the frames fxfinish packs + a recipe "ink" spec
	ink = "kit/vfx/ink.py",
	-- V5 (LIMITATIONS_FIXES_V4 3.4 step 3): a choreographed multi-shot sequence (assets/effects/sequences/<n>.seq.json)
	-- checked by the game's own rules (src/kit/VfxSequenceRules.luau) and drawn as a 60 fps timeline; --new: the template
	sequence = "kit/vfx/sequence.py",
	-- B4: an impact plate a ScreenGui steps through on the hit (halftone burst / concentration lines / a brush-written
	-- kanji) baked into a 1024 x 1024 flipbook + its spec (assets/effects/plates) - src/kit/VfxPlate.luau plays it
	plate = "kit/vfx/plates.py",
	-- the owner's 104 VFX methods (kit/vfx/methods.json): the list, one method (how, its tool, what proves it is
	-- used), and a scene's METHOD PLAN - which methods each beat of its chart is made with (kit vfx methods --set
	-- <set> [--beat N --use id,id --not id="why"]). The method gate below holds a preset to that plan
	methods = "kit/vfx/methods.py",
	-- the four LEGACY KEYS the v3 stage never plays as a preset reads them (spreadAngle, fov, frequency, a tilting
	-- ground card): what each preset carries, and --apply <name> ... rewrites them (a judged piece only with the
	-- owner's words, --judged "<them>"). A piece made after 2026-11-18 may not carry them (kit/lib/vfxlegacy.luau)
	migrate = "kit/vfx/legacy.py",
	-- ONE simulated cloud seen from a ring of 8 to 16 angles: the view_variant specs gpusim renders with the sim, and
	-- the sprite's "views" table (kit vfx impostor <sim> --angles 8; the V3 doc, E.1)
	impostor = "kit/vfx/impostor.py",
	-- a DISSOLVE THE GAME SHOWS (the VFX methods audit, stage 3): a texture breaking up over the cells of a sheet
	-- (kit vfx dissolve <key> --from <texture key | plain>), played on a mesh through its surface inside
	-- "flipbook.over" - a mesh's own "erode" writes vertex alpha, which the engine ignores
	dissolve = "kit/vfx/dissolve.py",
	-- SURFACE LOOKS IN SECONDS (the VFX methods audit, stage 4; the studio-route plan's V4): a short stack - a signed
	-- distance shape, a noise that pans, a UV distortion, an erosion, a colour ramp, a halftone - baked straight into a
	-- sheet (kit vfx comp <key> [--new ring|skin|blobs|branches|map|graph]); Blender stays for real light and simulations
	comp = "kit/vfx/comp.py",
	-- FOLLOWING THE CAMERA (the VFX methods audit, stage 7): the move a shot's background shares, frame by frame
	-- (kit vfx track <set> --beat N) - a pan makes every frame differ from the last, and the trace then reads every
	-- frame as a new drawing. kit vfx trace measures it itself and refuses a moving camera without --track
	track = "kit/vfx/track.py",
	-- AN OBJECT BROKEN INTO ITS OWN PIECES (the VFX methods audit, stage 5): a slab cut into the convex pieces it
	-- breaks into, each with the push the blow gives it (kit vfx fracture <name> --size w,d[,h]); a debris layer
	-- flies them ("pieces": "<name>")
	fracture = "kit/vfx/fracture.py",
	-- A LENS FLARE THAT BEHAVES LIKE ONE (the VFX methods audit, stage 6): where a flare's glow, streak and ghosts
	-- fall for a light at a place of the screen, drawn for the eye (kit vfx flare --light x,y); the lens layer's
	-- "flare" block places the same marks every frame in the game and in the player
	flare = "kit/vfx/flare.py",
	-- PIECES THAT COME TO REST (the VFX methods audit, stage 10): a fracture plan's pieces flown by the debris
	-- layer's "rest" rule - when the last one lies still, and whether that is before the layer's fade
	-- (kit vfx settle <plan> --life s)
	settle = "kit/vfx/settle.py",
	-- AN AUTHORED VECTOR FIELD (the VFX methods audit, stage 11): where the air goes, said as a wind, a vortex, a
	-- point and a drawn path (kit vfx field <name> [--new vortex]); a swarm layer follows it ("field": { name })
	field = "kit/vfx/field.py",
	-- FORCED PERSPECTIVE (the VFX methods audit, stage 13): what a mesh layer's "forced" block does to its size at
	-- each distance from the camera (kit vfx forced --ref 40 --keep 1)
	forced = "kit/vfx/forced.py",
	-- CLOTH, SIMULATED AND BAKED (the VFX methods audit, stage 15): a sheet held along an edge in a gusting wind,
	-- baked into a mesh sequence a mesh layer replays (kit vfx cloth <name> --pin top|left|corners --wind x,y,z)
	cloth = "kit/vfx/cloth.py",
	-- A SOFT BODY, SIMULATED AND BAKED (the VFX methods audit, stage 16): a ball of jelly dropped or thrown onto a
	-- floor, baked into a mesh sequence (kit vfx soft <name> --drop 6 --soft 0.6)
	soft = "kit/vfx/soft.py",
	-- SAND, SIMULATED AND BAKED (the VFX methods audit, stage 17): a pillar of sand that slumps to its angle of
	-- repose, or a pour that builds a cone, baked into a mesh sequence (kit vfx sand <name> --mode slump|pour)
	sand = "kit/vfx/sand.py",
	-- A POINT CLOUD (the VFX methods audit, stage 18): a shape said as points - a figure, or a picture's own bright
	-- pixels - that a swarm's particles gather into (kit vfx points <name> --new ring | --picture <png>)
	points = "kit/vfx/points.py",
	-- HAIR AND FUR, SIMULATED AND BAKED (the VFX methods audit, stage 19): strands rooted on a head or a line, swung by
	-- a toss or a sway, baked as ribbons into a mesh sequence of strips (kit vfx hair <name> --root cap|line --move toss)
	hair = "kit/vfx/hair.py",
	-- GEOMETRY NODES, BAKED (the VFX methods audit, stage 22): a mesh Blender's Geometry Nodes build and move (a
	-- ripple, a scatter of instanced quads), run headless and baked into a mesh sequence (kit vfx geonodes <name>)
	geonodes = "kit/vfx/geonodes.py",
	-- WATER AS A HEIGHT FIELD (the VFX methods audit, stage 24): the wave equation (a drop, rain, a slosh) and the
	-- shallow-water equations (a dam, a surge) solved and baked into a mesh sequence (kit vfx water <name> --recipe ...);
	-- never matched to a real scene
	water = "kit/vfx/water.py",
	-- LIQUID, SIMULATED AND BAKED INTO A FLIPBOOK (the VFX methods audit, stage 25): a liquid seen from the side, solved
	-- by FLIP or as a particle fluid, its foam and spray read off the solve (kit vfx liquid <key> --solver flip|pbf
	-- --scene dam|drop|slosh); never matched to a real scene
	liquid = "kit/vfx/liquid.py",
}

-- the scene-breakdown gate (mission 02-vfx 5.1): no frames, no build. A preset declares "scene": { set, colours? }
-- and the set must hold a beat table with scene times, the lore brief (>= 3 facts) and colours measured from >= 4
-- scene frames. Presets that existed before the gate (kit/vfx/scene_gate.json, frozen) are exempt while they declare
-- no scene. Returns the problems (empty = passes).
-- the originals made before an original needed real frames (kit/vfx/scene_gate.json original_refs, frozen 2026-11-10)
local originalsBeforeRefs: { [string]: boolean }? = nil
local function originalBeforeRefs(name: string): boolean
	if originalsBeforeRefs == nil then
		local set: { [string]: boolean } = {}
		local ok, gate = pcall(function()
			return serde.decode("json", fs.readFile("kit/vfx/scene_gate.json"))
		end)
		if ok and type(gate) == "table" and type(gate.original_refs) == "table" then
			for _, n in (gate.original_refs.grandfathered or {}) :: { any } do
				if type(n) == "string" then
					set[n] = true
				end
			end
		end
		originalsBeforeRefs = set
	end
	return (originalsBeforeRefs :: { [string]: boolean })[name] == true
end

-- the pieces made before a piece had to say its SCOPE (kit/vfx/scene_gate.json scope, frozen 2026-11-11)
local scopeBeforeSet: { [string]: boolean }? = nil
local function scopeBefore(name: string): boolean
	if scopeBeforeSet == nil then
		local set: { [string]: boolean } = {}
		local ok, gate = pcall(function()
			return serde.decode("json", fs.readFile("kit/vfx/scene_gate.json"))
		end)
		if ok and type(gate) == "table" and type(gate.scope) == "table" then
			for _, n in (gate.scope.grandfathered or {}) :: { any } do
				if type(n) == "string" then
					set[n] = true
				end
			end
		end
		scopeBeforeSet = set
	end
	return (scopeBeforeSet :: { [string]: boolean })[name] == true
end

-- the pieces built before a chart approval had to be the owner's OWN look at the chart (kit/vfx/scene_gate.json
-- chart_owner, frozen 2026-11-11): their charts carry the 2026-10-16 blanket approval an agent wrote onto them
local chartOwnerBeforeSet: { [string]: boolean }? = nil
local function chartOwnerBefore(name: string): boolean
	if chartOwnerBeforeSet == nil then
		local set: { [string]: boolean } = {}
		local ok, gate = pcall(function()
			return serde.decode("json", fs.readFile("kit/vfx/scene_gate.json"))
		end)
		if ok and type(gate) == "table" and type(gate.chart_owner) == "table" then
			for _, n in (gate.chart_owner.grandfathered or {}) :: { any } do
				if type(n) == "string" then
					set[n] = true
				end
			end
		end
		chartOwnerBeforeSet = set
	end
	return (chartOwnerBeforeSet :: { [string]: boolean })[name] == true
end

-- the chart's plan as one comparable line - the duration, then each beat's t, len, hold and key - the same text
-- kit/vfx/chart.py plan_key() writes into "approved": {"plan"} when the owner approves (a re-timed chart is another chart)
local chartPlanKey = require("../lib/chartplan") -- (ONE reading, shared with kit review: kit/lib/chartplan.luau)

-- the SCOPE of a piece built from a scene (2026-11-11, the owner on flame_arc_keybeat, REDO: "you're saying
-- Flame Arc dance, so you're saying dance, the whole thing basically"): a new piece from a breakdown of >= 2 beats
-- says which beats it builds - every layer carries "beat" (its beat's number in the set's chart) - and either builds
-- them ALL or is named for the beat(s) it is (flame_arc_dance_arc), never for the whole technique. Returns the problems
local function sceneScope(dir: string, name: string, preset: any, set: string): { string }
	if scopeBefore(name) or type(preset) ~= "table" or type(preset.layers) ~= "table" then
		return {}
	end
	local okC, chart = pcall(function()
		return serde.decode("json", fs.readFile(`{dir}/refs_measured/{set}.chart.json`))
	end)
	if not okC or type(chart) ~= "table" or type(chart.beats) ~= "table" then
		return {}
	end
	local ids: { string }, slugs: { [string]: string } = {}, {}
	for _, b in chart.beats :: { any } do
		local label = tostring(b.beat or "")
		local id = string.match(label, "^%s*(%d+)")
		if id then
			table.insert(ids, id)
			-- the beat's own name: its words without the number and the filler ("1 key the dance arc" -> "dance_arc")
			local words = {}
			for w in string.gmatch(string.lower((string.gsub(label, "^%s*%d+%s*", ""))), "%a+") do
				if w ~= "key" and w ~= "the" and w ~= "a" and w ~= "an" and w ~= "of" then
					table.insert(words, w)
				end
			end
			slugs[id] = table.concat(words, "_")
		end
	end
	if #ids < 2 then
		return {}
	end
	local covered: { [string]: boolean }, untagged = {}, 0
	for _, l in preset.layers :: { any } do
		if l.beat == nil then
			untagged += 1
		else
			covered[tostring(l.beat)] = true
		end
	end
	if untagged > 0 then
		return {
			`scope: {untagged} layer(s) name no beat - each layer says which of {set}'s {#ids} beats it builds ("beat": {ids[1]}-{ids[#ids]}); then build them all or name the piece for its beat(s) (the owner, 2026-11-10: "you're saying Flame Arc dance ... the whole thing")`,
		}
	end
	local have, missing = {}, {}
	for _, id in ids do
		table.insert(if covered[id] then have else missing, id)
	end
	if #missing > 0 then
		for _, id in have do
			local slug = slugs[id]
			if slug and slug ~= "" and not string.find(string.lower(name), slug, 1, true) then
				return {
					`scope: builds beat(s) {table.concat(have, ", ")} of {#ids} but is not named for them - build beat(s) {table.concat(
						missing,
						", "
					)} too, or name it for what it is (..._{slug})`,
				}
			end
		end
	end
	return {}
end

local function sceneGate(dir: string, name: string, preset: any, grandfathered: { [string]: boolean }): { string }
	local scene = preset.scene
	if scene == nil then
		if grandfathered[name] then
			return {}
		end
		return {
			`no scene breakdown: a new preset is built FROM its scene - declare "scene": \{ "set": "<refs set>" \} after lune run kit vfx breakdown <set> --clip <file>`,
		}
	end
	-- an ORIGINAL effect has no source scene (owner, 2026-10-24: "original ideas ... a creative director"): it is
	-- built from the director's concept brief instead (kit vfx director new / check), under the owner's go-ahead for
	-- originals (kit approve vfx originals "<their words>" --by owner)
	if type(scene) == "table" and scene.original ~= nil then
		if type(scene.original) ~= "string" or scene.original == "" then
			return { `scene.original must name a director brief (assets/effects/briefs/<name>.md)` }
		end
		local problems = {}
		if not Locks.approval("vfx", "originals") then
			table.insert(
				problems,
				`original effects need the owner's go-ahead: kit approve vfx originals "<their words>" --by owner`
			)
		end
		local briefPath = `{dir}/briefs/{scene.original}.md`
		if not fs.isFile(briefPath) then
			table.insert(
				problems,
				`no director brief {briefPath} (lune run kit vfx director new {scene.original} --idea "...")`
			)
			return problems
		end
		local brief = fs.readFile(briefPath)
		for _, section in
			{
				"Concept",
				"Shape language",
				"Palette",
				"Beats",
				"Techniques",
				"Impact style",
				"Dissipation",
				"It is NOT",
			}
		do
			-- the section's body (up to the next "## "): more than the template's "<...>" placeholder (review 2026-10-24:
			-- an unfilled `director new` template passed)
			local body = string.match(brief, `\n## {section}%s*\n(.-)\n## `)
				or string.match(brief, `\n## {section}%s*\n(.*)$`)
			if body ~= nil and #string.gsub(string.gsub(body, "<[^>]*>", ""), "%s", "") < 10 then
				table.insert(problems, `brief {briefPath}: "## {section}" is still the template placeholder`)
			end
			if not string.find(brief, `\n## {section}%s*\n`) then
				table.insert(
					problems,
					`brief {briefPath}: no "## {section}" section (lune run kit vfx director check {scene.original})`
				)
			end
		end
		local rows = 0
		for line in string.gmatch(brief, "[^\n]+") do
			if string.sub(line, 1, 1) == "|" and string.find(line, "|%s*[%d%.]+%s*%-?%s*[%d%.]*%s*s%s*|%s*[^|%s]") then
				rows += 1
			end
		end
		if rows < 3 then
			table.insert(problems, `brief {briefPath}: {rows} timed beat row(s), needs >= 3`)
		end
		-- an original needs REAL frames too (2026-11-10, R-vfx-5): the eight originals of 2026-10-24 were built from a
		-- text brief with no footage and no chart and scored 4-6 ("not bad but not impressive ... the quality degraded
		-- alot"); every 8+ was built beat by beat from real frames (starblade 9.5 from its scene, nuke_v4 8.7 from real
		-- test footage). Beside the brief, "set" names a refs set of REAL frames - footage of the phenomenon, or a scene of
		-- its kind - held to a scene's breakdown: beat sheet, lore, measured colours and the OWNER's chart (his look at
		-- ONE test frame before the whole piece). The originals made before this lock are exempt (kit/vfx/scene_gate.json
		-- original_refs.grandfathered, frozen: adding a name to it is loosening the gate)
		if scene.set ~= nil then
			for _, problem in
				sceneGate(dir, name, { scene = { set = scene.set, colours = scene.colours } }, grandfathered)
			do
				table.insert(problems, problem)
			end
			for _, problem in sceneScope(dir, name, preset, scene.set) do
				table.insert(problems, problem)
			end
		elseif not originalBeforeRefs(name) then
			table.insert(
				problems,
				`an original needs REAL frames too: declare "set": "<refs set>" beside "original" - real footage of the phenomenon (or a scene of its kind), broken down like a scene's (lune run kit vfx breakdown <set> --clip <file>, refs lore, refs measure), then the owner approves its chart`
			)
		end
		return problems
	end
	if type(scene) ~= "table" or type(scene.set) ~= "string" or scene.set == "" then
		return {
			`scene must be \{ "set": "<refs set>", "colours": "<measured file>" \} or \{ "original": "<director brief>" \}`,
		}
	end
	local m = dir .. "/refs_measured/"
	local set = scene.set
	local problems = {}
	local beatsPath = `{m}{set}.beats.md`
	if not fs.isFile(beatsPath) then
		table.insert(problems, `no beat sheet {beatsPath} (lune run kit vfx breakdown {set} --clip <file>)`)
	else
		local rows = 0
		for line in string.gmatch(fs.readFile(beatsPath), "[^\n]+") do
			-- a table row whose scene-time cell reads like "17.5-21 s" / "0.4 s" AND whose next cell (what is on
			-- screen) is filled: a breakdown skeleton nobody looked at does not count
			if string.sub(line, 1, 1) == "|" and string.find(line, "|%s*[%d%.]+%s*%-?%s*[%d%.]*%s*s%s*|%s*[^|%s]") then
				rows += 1
			end
		end
		if rows < 3 then
			table.insert(problems, `beat sheet {beatsPath}: {rows} beat row(s) with a scene time, needs >= 3`)
		end
	end
	-- the chart is approved before the build (mission 02-vfx 5.2) and only the OWNER's approval counts (the quality
	-- locks, 2026-10-21): a model's own --approve is recorded as model-proposed and refused here
	local chartPath = `{m}{set}.chart.json`
	local okC, chart = pcall(function()
		return serde.decode("json", fs.readFile(chartPath))
	end)
	-- the owner may let a preset skip its chart: kit approve vfx <name> "<their words>" --by owner --waive chart
	-- (a waived chart skips only these three; the brief, lore and frames checks below still apply)
	local chartWaived = Locks.waiver("vfx", name, "chart") ~= nil
	if not chartWaived and (not okC or type(chart) ~= "table") then
		table.insert(problems, `no beat chart {chartPath} (lune run kit vfx chart {set}, then the owner approves it)`)
	elseif
		not chartWaived
		and (type(chart.approved) ~= "table" or type(chart.approved.words) ~= "string" or chart.approved.words == "")
	then
		table.insert(
			problems,
			`chart not approved: {chartPath} (show build/vfx/charts/{set}.png; when the owner approves: lune run kit vfx chart {set} --approve "<the owner's words>" --by owner)`
		)
	elseif
		not chartWaived
		and not Locks.isOwner(chart.approved)
		and not Locks.approval("vfx", set) -- kit approve vfx <set> or <preset>
		and not Locks.approval("vfx", name)
	then
		table.insert(
			problems,
			`chart approved by "{tostring(chart.approved.by)}", not the owner: {chartPath} (show build/vfx/charts/{set}.png to the owner; their approval: lune run kit vfx chart {set} --approve "<the owner's words>" --by owner)`
		)
	elseif
		-- (2026-11-11, the owner on flame_arc, REDO: "Are you even using the VFX pipeline properly?") an approval
		-- counts only as his OWN look at this chart: `by` "owner" exactly (kit vfx chart --approve ... --by owner) or his
		-- approval in board/locks.json. The 2026-10-16 blanket approval was written onto charts by an agent as "owner
		-- blanket approval 2026-10-16" ("the owner has not looked at this chart"); the "owner..." prefix above let two
		-- REDO pieces through on it
		not chartWaived
		and not Locks.approval("vfx", set)
		and not Locks.approval("vfx", name)
		and not chartOwnerBefore(name)
		and string.lower((string.gsub(tostring(chart.approved.by), "^%s*(.-)%s*$", "%1"))) ~= "owner"
	then
		table.insert(
			problems,
			`chart approval is not the owner's own look at this chart: by "{tostring(chart.approved.by)}" ({chartPath}; show him build/vfx/charts/{set}.png with its test frame; his approval: lune run kit vfx chart {set} --approve "<his words>" --by owner)`
		)
	elseif
		-- an approval holds the plan he saw (chart.py writes it): beats re-timed or another key beat after it is a chart
		-- he never saw (2026-11-11: flame_arc_set re-timed 2.2 -> 3.4 s by an agent, its approval kept)
		not chartWaived
		and type(chart.approved.plan) == "string"
		and chart.approved.plan ~= chartPlanKey(chart)
	then
		table.insert(
			problems,
			`the chart changed since the owner approved it: {chartPath} is now {chartPlanKey(chart)}, he approved {chart.approved.plan} (show him build/vfx/charts/{set}.png again)`
		)
	end
	if not fs.isFile(`{m}{set}.brief.md`) then
		table.insert(
			problems,
			`no lore brief {m}{set}.brief.md (lune run kit vfx refs lore {set} ... then refs brief {set})`
		)
	end
	local lorePath = `{m}{set}.lore.json`
	local okLore, lore = pcall(function()
		return serde.decode("json", fs.readFile(lorePath))
	end)
	if not okLore or type(lore) ~= "table" or type(lore.facts) ~= "table" or #lore.facts < 3 then
		table.insert(problems, `lore {lorePath}: needs >= 3 quoted facts`)
	end
	local colours = if type(scene.colours) == "string" then scene.colours else set
	local measuredPath = `{m}{colours}.json`
	local okM, measured = pcall(function()
		return serde.decode("json", fs.readFile(measuredPath))
	end)
	if not okM or type(measured) ~= "table" or type(measured.bands) ~= "table" then
		table.insert(
			problems,
			`no measured colours {measuredPath} (lune run kit vfx refs measure {colours} on the scene frames)`
		)
	elseif Locks.waiver("vfx", name, "frames") == nil then
		-- a frame from the project's own build output is a render of OUR work, never the scene (the quality locks)
		-- distinct frames only: four copies of one name are one frame
		local real, ours, seen = 0, 0, {}
		for _, frame in (if type(measured.from) == "table" then measured.from else {}) :: { any } do
			local id = if type(frame) == "string" then string.lower(Locks.normal(frame)) else ""
			if id == "" or seen[id] then
				continue
			end
			seen[id] = true
			if Locks.isBuildPath(frame) then
				ours += 1
			else
				real += 1
			end
		end
		if real < 4 then
			local why = if ours > 0 then ` ({ours} more are our own build renders, which never count)` else ""
			table.insert(
				problems,
				`measured colours {measuredPath}: from {real} real scene frame(s){why}, needs >= 4 (lune run kit vfx breakdown {set} --clip <the real scene>, then refs measure {colours})`
			)
		end
	end
	for _, problem in sceneScope(dir, name, preset, set) do
		table.insert(problems, problem)
	end
	return problems
end
sceneGateFwd = sceneGate

-- the METHOD gate (2026-11-13, the owner: "every method i mentioned for each pipeline keep going up until they are all
-- mastered and implmented into each pipeline and enforced in the terms of being used"): a preset built from a scene
-- is held to its chart's METHOD PLAN - every beat it builds names the methods of his list it is made with, a layer of
-- that beat proves each one is used (kit/vfx/methods.json holds each method's proof), a beat whose own words call
-- for a method the kit makes the scene's way uses it or says why not where he reads it (the chart he approves), and
-- nothing he saw there is dropped afterwards. kit/vfx/methods.py --gate does the reading. The pieces that existed
-- before this gate are exempt (kit/vfx/scene_gate.json methods.grandfathered, frozen); the owner may waive it for
-- one piece: kit approve vfx <name> "<their words>" --by owner --waive methods. Returns the problems
local methodsBeforeSet: { [string]: boolean }? = nil
local function methodsBefore(dir: string, name: string): boolean
	if methodsBeforeSet == nil then
		local set: { [string]: boolean } = {}
		local ok, gate = pcall(function()
			return serde.decode("json", fs.readFile("kit/vfx/scene_gate.json"))
		end)
		if ok and type(gate) == "table" and type(gate.methods) == "table" then
			for _, n in (gate.methods.grandfathered or {}) :: { any } do
				if type(n) == "string" then
					set[n] = true
				end
			end
		end
		methodsBeforeSet = set
	end
	-- a piece is exempt by its FOLDER and its name ("assets/effects/vortex"): the same name in another game, or
	-- a new piece named like one of the kit's fixtures ("preset"), is not
	local folder = string.gsub(string.gsub(dir, "\\", "/"), "/+$", "")
	return (methodsBeforeSet :: { [string]: boolean })[`{folder}/{name}`] == true
end

local function methodsGate(dir: string, name: string, raw: any): { string }
	if type(raw) ~= "table" or type(raw.scene) ~= "table" or type(raw.scene.set) ~= "string" or raw.scene.set == "" then
		return {} -- (a preset with no scene set is the scene gate's to refuse)
	end
	if methodsBefore(dir, name) then
		return {}
	end
	-- the owner's waiver lets a piece off its METHOD PLAN; what the game does not show (the register's "refused": a
	-- measured engine fact) is not a plan and stays refused
	local waived = Locks.waiver("vfx", name, "methods") ~= nil
	-- a fixture folder brings its own texture specs (<dir>/textures); a project's are its textures folder
	local argv = {
		"kit/vfx/methods.py",
		"--gate",
		"--effects",
		dir,
		"--name",
		name,
		"--textures",
		if fs.isDir(dir .. "/textures") then dir .. "/textures" else Config.path("textures"),
	}
	-- the preset AS IT PLAYS, and every variant as it plays: a muted layer is gone from the expansion, a part's
	-- layers are in it (the gate proves a method from what plays, never from a layer that only sits in the file)
	local plays: { any } = { false }
	for _, v in VfxCompose.variants(raw) do
		table.insert(plays, v)
	end
	local tmpDir = Config.build("vfx") .. "/methods"
	Config.ensureDir(tmpDir)
	for _, v in plays do
		local variant: string? = if v then v else nil
		local okE, expanded = pcall(expandPreset, raw, variant)
		if not okE or type(expanded) ~= "table" then
			return { `the method gate could not expand the preset{if variant then ` (variant {variant})` else ""}` }
		end
		local label = if variant then (string.gsub(variant, "[^%w_%-]", "_")) else ""
		local tmp =
			`{tmpDir}/{(string.gsub(name, "[^%w_%-]", "_"))}{if variant then "@" .. label else ""}.expanded.json`
		fs.writeFile(tmp, serde.encode("json", expanded))
		table.insert(argv, "--expanded")
		table.insert(argv, `{label}={tmp}`)
	end
	if waived then
		table.insert(argv, "--refused-only")
	end
	local okRun, res = pcall(process.exec, Run.tool("python"), argv)
	if not okRun then
		-- (python itself could not be started: never build blind past the gate)
		return { `the method gate did not run (python could not be started: {tostring(res)})` }
	end
	local lines = string.split(string.gsub(res.stdout, "\r", ""), "\n")
	local last = #lines
	while last > 0 and not string.match(lines[last], "%S") do
		last -= 1
	end
	local ok, v = pcall(serde.decode, "json" :: any, if last > 0 then lines[last] else "")
	if not res.ok or not ok or type(v) ~= "table" or type(v.problems) ~= "table" then
		-- (the check itself broke: never build blind past it - its own error says why)
		local err = string.match(res.stderr, "([^\n]+)%s*$") or "no output"
		return { `the method gate did not run (kit/vfx/methods.py --gate): {err}` }
	end
	local problems: { string } = {}
	for _, problem in v.problems :: { any } do
		table.insert(problems, tostring(problem))
	end
	return problems
end
methodsGateFwd = methodsGate

-- THE STAGE LOCKS (the V3 doc, VFX stage G.3: "require --stage style, --stage animatic"): a piece built from its
-- scene goes to the look only after the owner approved its set's TIMING ANIMATIC (V2: the motion in flat shapes beside
-- the scene) and its STYLE SHEET (V1: every beat's look beside the scene's), each AS IT IS NOW (LaneLocks.holds: the
-- artefact he saw, not one drawn again since) - or waived by him (kit approve vfx <name> ... --waive style|animatic).
-- Both were pages to read and nothing stopped a build without them. Pieces that existed on 2026-11-18 are exempt
-- (kit/vfx/legacy_keys.json "frozen"). -> the problems, empty when it may build
local function stagesGate(dir: string, name: string, raw: any, frozen: { [string]: boolean }): { string }
	if type(raw) ~= "table" or type(raw.scene) ~= "table" or type(raw.scene.set) ~= "string" or raw.scene.set == "" then
		return {} -- (a preset with no scene set is the scene gate's to refuse)
	end
	if frozen[`{dir}/{name}`] then
		return {}
	end
	local LaneLocks = require("../lib/lanelocks")
	local problems: { string } = {}
	for _, want in { { raw.scene.set, "animatic", "timing animatic" }, { name, "style", "style sheet" } } do
		local key, step, what = want[1], want[2], want[3]
		if Locks.waiver("vfx", name, step) == nil and Locks.waiver("vfx", key, step) == nil then
			local art = LaneLocks.vfxStageState(key, step, dir)
			if not LaneLocks.holds(Locks.stage("vfx", key, step), art) then
				table.insert(
					problems,
					`the {what} of {key} is not the owner's yes as it is now ({art.why or "approved, then made again"}): `
						.. `make it (lune run kit vfx {if step == "style" then "stylesheet" else "animatic"} {key}), show it (lune run kit review {name}), `
						.. `then only with his words: lune run kit approve vfx {key} "<his words>" --by owner --stage {step}`
				)
			end
		end
	end
	return problems
end

function Content.vfxPresetsStep(presetDir: string?): Run.Step
	local dir = presetDir or Config.path("vfx")
	local grandfathered: { [string]: boolean } = {}
	if presetDir == nil and fs.isFile("kit/vfx/scene_gate.json") then
		for _, n in serde.decode("json", fs.readFile("kit/vfx/scene_gate.json")).grandfathered do
			grandfathered[n] = true
		end
	end
	local registryPath = dir .. "/_textures.json"
	if presetDir == nil and Config.isKitSource() and not fs.isFile(registryPath) then
		-- (the kit's own repo has no project effects: the kit's presets are checked by kit selftest)
		return Run.step("vfx presets", true, "", { summary = "SKIPPED - kit-source repo (no project assets/effects)" })
	end
	if not fs.isFile(registryPath) then
		return Run.step("vfx presets", false, `missing {registryPath}`, {
			next_action = `create it: lune run kit init (or copy kit/starter/vfx/_textures.json to {dir}/)`,
		})
	end
	local textures = serde.decode("json", fs.readFile(registryPath))
	local meshesPath = dir .. "/_meshes.json"
	local meshes = if fs.isFile(meshesPath) then serde.decode("json", fs.readFile(meshesPath)) else {}
	local errors, warns, count, starters = {}, {}, 0, 0
	-- the four legacy keys are errors on a piece made after 2026-11-18 (kit/lib/vfxlegacy.luau; the V3 doc, A.1)
	local legacyFrozen = VfxLegacy.frozen()
	-- the kit's record of its starter texts (kit/vfx/starters.json), read once: only the project's own effects use it
	local starterRecord = if presetDir == nil then Starters.load() else nil
	for _, file in fs.readDir(dir) do
		if string.sub(file, -5) == ".json" and string.sub(file, 1, 1) ~= "_" then
			count += 1
			local name = string.sub(file, 1, -6)
			local ok, preset = pcall(serde.decode, "json" :: any, fs.readFile(dir .. "/" .. file))
			if not ok then
				table.insert(errors, `{name}: invalid JSON`)
				continue
			end
			-- an untouched kit starter in the project is the kit's piece: the making gates hold it from its first edit
			-- (kit/lib/starters.luau); the validator's errors below hold it as they hold every preset
			local starter = starterRecord ~= nil and Starters.untouchedVfx(dir, file, starterRecord)
			if starter then
				starters += 1
			end
			-- the project's effects always; a fixture dir only when it carries its own refs_measured
			if (presetDir == nil or fs.isDir(dir .. "/refs_measured")) and not starter then
				for _, problem in sceneGate(dir, name, preset, grandfathered) do
					table.insert(errors, `{name}: scene: {problem}`)
				end
				for _, problem in methodsGate(dir, name, preset) do
					table.insert(errors, `{name}: methods: {problem}`)
				end
				for _, problem in stagesGate(dir, name, preset, legacyFrozen) do
					table.insert(errors, `{name}: stages: {problem}`)
				end
			end
			-- a composed preset is checked expanded, and once per variant ("<name>@<variant>")
			local variants: { any } = { false } -- false = the preset itself ({ nil } would be an EMPTY table)
			for _, v in VfxCompose.variants(preset) do
				table.insert(variants, v)
			end
			for _, v in variants do
				local variant: string? = if v then v else nil
				local label = if variant then `{name}@{variant}` else name
				local expanded, composeIssues = expandPreset(preset, variant)
				for _, list in { composeIssues, VfxValidate.preset(label, expanded, textures, meshes) } do
					for _, issue in list do
						local legacy = if starter then nil else VfxLegacy.refusal(dir, name, issue, legacyFrozen)
						if legacy then
							table.insert(errors, `{label}: {issue.path}: {legacy}`)
						else
							table.insert(
								if issue.severity == "error" then errors else warns,
								`{label}: {issue.path}: {issue.message}`
							)
						end
					end
				end
			end
		end
	end
	-- parts (reusable sub-effects) validate on their own, as a stand-alone preset
	if fs.isDir(dir .. "/parts") then
		for _, file in fs.readDir(dir .. "/parts") do
			if string.sub(file, -5) == ".json" then
				count += 1
				local name = "parts/" .. string.sub(file, 1, -6)
				local ok, part = pcall(serde.decode, "json" :: any, fs.readFile(dir .. "/parts/" .. file))
				if not ok then
					table.insert(errors, `{name}: invalid JSON`)
					continue
				end
				for _, issue in VfxValidate.preset(name, VfxCompose.partAsPreset(part), textures, meshes) do
					table.insert(
						if issue.severity == "error" then errors else warns,
						`{name}: {issue.path}: {issue.message}`
					)
				end
			end
		end
	end
	for key, entry in textures do
		if
			presetDir == nil
			and type(entry) == "table"
			and not fs.isFile(`{Config.path("textures")}/{key}.json`)
			and (entry.id == nil or entry.id == "")
		then
			table.insert(errors, `_textures.{key}: no spec {Config.path("textures")}/{key}.json and no uploaded id`)
		end
	end
	local tail = table.concat(errors, "\n") .. (if #warns > 0 then "\nwarnings:\n" .. table.concat(warns, "\n") else "")
	return Run.step("vfx presets", #errors == 0, tail, {
		status = if #errors == 0 then "pass" else "fail",
		summary = `{count} preset(s)` .. (if starters > 0
			then ` ({starters} untouched kit starter(s): the making gates hold them once edited)`
			else "") .. `, {#errors} error(s), {#warns} warning(s)` .. (if #errors > 0
			then ": " .. table.concat(errors, "; ")
			else ""),
		next_action = if #errors > 0 then errors[1] else nil,
	})
end

-- ---------------------------------------------------------------- ui
-- lay out compiled screens like the engine and draw them at phone/tablet/desktop -> build/ui/<Name>.png
function Content.uiPreviewStep(names: { string }?, models: string?, out: string?, motion: boolean?): Run.Step
	local args = { "kit/ui/preview.py", "--models", models or Config.path("uiOut"), "--out", out or Config.build("ui") }
	if motion then
		table.insert(args, "--motion")
	end
	for _, n in names or {} do
		table.insert(args, n)
	end
	return Run.content("ui preview", Run.tool("python"), args)
end

-- the kit's UI art (kit/ui/art.py): drawn once per project into build/ui/art, uploaded by kit upload
function Content.uiArtStep(): Run.Step
	return Run.content("ui art", Run.tool("python"), { "kit/ui/art.py", "--out", Config.build("ui") .. "/art" })
end

-- the vault (kit/ui/vault.py): the owner's rule (2026-10-12) — everything the UI pipeline makes is saved, packaged
-- by part and named properly, in library/ui (screens with their parts, previews, reels and verdicts; every identity's
-- pieces). `kit ui` and every piece command save; `kit verify` runs the check (missing or stale = the gate fails)
function Content.uiVaultStep(): Run.Step
	return Run.content("ui vault", Run.tool("python"), {
		"kit/ui/vault.py",
		"save",
		"--ui",
		Config.path("ui"),
		"--models",
		Config.path("uiOut"),
		"--build",
		Config.build("ui"),
	})
end

function Content.uiVaultCheckStep(): Run.Step
	return Run.content("ui vault", Run.tool("python"), {
		"kit/ui/vault.py",
		"check",
		"--ui",
		Config.path("ui"),
		"--models",
		Config.path("uiOut"),
		"--build",
		Config.build("ui"),
	})
end

-- a HUD written as GAME CODE sizes itself at runtime, where no spec or compile sees it: its size on screen against
-- the size its reference sets (kit/lib/hudsize.luau; the owner's sg_hud5 3/10, 2026-10-29: "what the hell, I told
-- you not this small"). Every contract in the root and every game (<root>assets/ui/huds/*.json), or the given ones
function Content.uiHudSizeStep(only: { string }?): Run.Step
	local HudSize = require("../lib/hudsize")
	local contracts = only or HudSize.contracts()
	if #contracts == 0 then
		return Run.step("ui hud size", true, "", { summary = "no game-code HUD (no <root>assets/ui/huds/*.json)" })
	end
	local lines, failed = {}, {}
	for _, path in contracts do
		local r = HudSize.run(path)
		table.insert(lines, `{if r.ok then "[ok]" else "[FAIL]"} {path}: {r.summary}`)
		if not r.ok then
			table.insert(failed, { path = path, r = r })
		end
	end
	return Run.step("ui hud size", #failed == 0, table.concat(lines, "\n"), {
		summary = if #failed == 0
			then `{#contracts} game-code HUD(s) at their reference size on screen`
			else failed[1].r.summary,
		next_action = if #failed == 0
			then nil
			else `{failed[1].r.next_action} (contract: {failed[1].path}; lune run kit ui hudsize)`,
	})
end

-- the ALIGNMENT gate (LIMITATIONS_FIXES_V4 UI-X 6.4 step 4: kit/ui/align.py, the 1-3 px anti-slop lint): every
-- compiled screen laid out at desktop like the engine (no drawing), its near-misses - edges / centres 1-3 px apart,
-- gaps 1-4 px uneven - counted. A WARNING with the count (the step passes): most sit on screens the owner judges,
-- where a 2 px step can be a hand-set offset he liked; `align.py check <Screen> --fail` makes them a failure
function Content.uiAlignStep(only: { string }?): Run.Step
	local args = { "kit/ui/align.py", "check", "--models", Config.path("uiOut") }
	for _, n in only or {} do
		table.insert(args, n)
	end
	return Run.content("ui align", Run.tool("python"), args)
end

-- the lettering step (kit/ui/words.py): every "lettering" label / button baked into its identity's art BEFORE the
-- plates step copies that art — a screen author writes text and gets display lettering
function Content.uiWordsStep(): Run.Step
	return Run.content(
		"ui words",
		Run.tool("python"),
		{ "kit/ui/words.py", "--ui", Config.path("ui"), "--art", Config.path("ui") .. "/art" }
	)
end

-- every identity's plates (kit/ui/plates.py: frames, slots, caps, dividers, bands... in ITS shape language)
-- -> build/ui/art/<identity>/, uploaded as ids.ui["<identity>/<plate>"]
function Content.uiPlatesStep(names: { string }?): Run.Step
	local args = {
		"kit/ui/plates.py",
		"--identities",
		Config.path("ui") .. "/identities",
		"--out",
		Config.build("ui") .. "/art",
	}
	for _, n in names or {} do
		table.insert(args, n)
	end
	return Run.content("ui plates", Run.tool("python"), args)
end

-- the real faces behind the fonts the screens name (kit/ui/fonts.py: Google Fonts, vetted + pinned) so the preview
-- draws what the player sees; offline it keeps what is cached and says so
function Content.uiFontsStep(): Run.Step
	return Run.content(
		"ui fonts",
		Run.tool("python"),
		{ "kit/ui/fonts.py", "fetch", "--ui", Config.path("ui"), "--models", Config.path("uiOut") }
	)
end

-- the art manifest: the kit's pieces + every identity's plates under "<identity>/<plate>"
local function uiArtMeta(): any
	local dir = Config.build("ui") .. "/art"
	local path = dir .. "/art.json"
	local meta: any = if fs.isFile(path) then serde.decode("json", fs.readFile(path)) else nil
	if fs.isDir(dir) then
		for _, sub in fs.readDir(dir) do
			local p = `{dir}/{sub}/art.json`
			if fs.isDir(`{dir}/{sub}`) and fs.isFile(p) then
				meta = meta or {}
				for k, v in serde.decode("json", fs.readFile(p)) do
					meta[`{sub}/{k}`] = v
				end
			end
		end
	end
	return meta
end

-- assets/ui/identities/<name>.json -> {name: identity}; a broken file is reported, not skipped silently
function Content.uiIdentities(): ({ [string]: any }, { string })
	local dir = Config.path("ui") .. "/identities"
	local out, problems = {}, {}
	if fs.isDir(dir) then
		for _, f in fs.readDir(dir) do
			if string.sub(f, -5) == ".json" then
				local name = string.sub(f, 1, -6)
				local ok, id = pcall(serde.decode, "json" :: any, fs.readFile(`{dir}/{f}`))
				if not string.match(name, "^[%w_]+$") then
					-- the name becomes "art:<identity>/<plate>" and an upload id key: letters, digits, _ only
					table.insert(
						problems,
						`identities/{f}: an identity's file name is letters, digits and _ (not "{name}")`
					)
				elseif ok and type(id) == "table" then
					out[name] = id
				else
					table.insert(problems, `identities/{f}: invalid JSON`)
				end
			end
		end
	end
	return out, problems
end

function Content.uiCompile(write: boolean, refsRoot: string?): (Run.Step, { string })
	local specDir, outDir = Config.path("ui"), Config.path("uiOut")
	local names, problems, errors, drift = {}, {}, 0, {}
	local fresh: { string } = {} -- screens made after the quality locks, with no owner waiver of the refs step
	local held: { [string]: { path: string, encoded: string } } = {}
	local ids = if fs.isFile(Config.path("ids")) then serde.decode("json", fs.readFile(Config.path("ids"))) else {}
	local art = uiArtMeta()
	local identities, idProblems = Content.uiIdentities()
	for _, p in idProblems do
		errors += 1
		table.insert(problems, p)
	end
	-- the Sfx events a screen's "sounds" may name (the SFX lane's catalog)
	local events: { [string]: boolean }? = nil
	local eventsPath = Config.path("sounds") .. "/_events.json"
	if fs.isFile(eventsPath) then
		local okE, ev = pcall(serde.decode, "json" :: any, fs.readFile(eventsPath))
		if okE and type(ev) == "table" and type(ev.events) == "table" then
			events = {}
			for name in ev.events do
				(events :: any)[name] = true
			end
		end
	end
	if fs.isDir(specDir) then
		for _, file in fs.readDir(specDir) do
			-- a screen is <Name>.json; <Name>.judge.json (a recorded verdict) and any other dotted file are not
			if string.sub(file, -5) ~= ".json" or string.find(string.sub(file, 1, -6), ".", 1, true) then
				continue
			end
			local ok, spec = pcall(serde.decode, "json" :: any, fs.readFile(specDir .. "/" .. file))
			if not ok then
				errors += 1
				table.insert(problems, `{file}: invalid JSON`)
				continue
			end
			local model, issues = UI.compile(spec, ids, art, identities, events)
			for _, issue in issues do
				if issue.severity == "error" then
					errors += 1
				end
				table.insert(problems, `[{issue.severity}] {issue.path}: {issue.message}`)
			end
			-- the quality lock (2026-10-21): a screen made after the locks is built on real references
			local stem = string.sub(file, 1, -6)
			if
				not Locks.grandfathered("ui", `{specDir}/{file}`)
				and not Locks.waiver("ui", spec.name or stem, "refs")
			then
				table.insert(fresh, stem)
			end
			if model and spec.name then
				local path = `{outDir}/{spec.name}.model.json`
				local encoded = serde.encode("json", model, true)
				if write and fresh[#fresh] == stem then
					held[stem] = { path = path, encoded = encoded } -- written only when its refs lock passes
				elseif write then
					Config.ensureDir(outDir)
					fs.writeFile(path, encoded)
				elseif not fs.isFile(path) or not sameModel(path, model) then
					table.insert(drift, path)
				end
				table.insert(names, spec.name)
			end
		end
	end
	if #fresh > 0 then
		local args = { "kit/ui/refs_lock.py", "--specs", specDir }
		if refsRoot then
			table.insert(args, "--refs")
			table.insert(args, refsRoot)
		end
		for _, n in fresh do
			table.insert(args, n)
		end
		local lock = Run.spawn("ui refs lock", Run.tool("python"), args, true)
		local screens = if lock.result and type(lock.result.screens) == "table" then lock.result.screens else nil
		if not screens then
			errors += 1
			table.insert(problems, `[error] ui refs lock: kit/ui/refs_lock.py gave no verdict: {lock.tail}`)
		else
			for _, n in fresh do
				local r = screens[n]
				if r and r.ok and held[n] then
					Config.ensureDir(outDir)
					fs.writeFile(held[n].path, held[n].encoded)
				end
				if not r or not r.ok then
					errors += 1
					table.insert(
						problems,
						`[error] {n}: refs lock: a new screen is built on >= 2 real stills of its type at >= 1080p ({if r
							then r.detail
							else "no verdict"}) - {if r and r.todo ~= ""
							then r.todo
							else "lune run kit ui plan " .. n}; or the owner waives it: lune run kit approve ui {n} "<their words>" --by owner --waive refs`
					)
				end
			end
		end
	end
	local ok = errors == 0 and #drift == 0
	local next_action = nil
	if errors > 0 then
		next_action = problems[1]
	elseif #drift > 0 then
		next_action = `{drift[1]} is out of date with its spec — run: lune run kit ui`
	end
	return Run.step(if write then "ui compile" else "ui up to date", ok, table.concat(problems, "\n"), {
		summary = `{#names} screen(s)` .. (if #drift > 0 then `, {#drift} stale` else ""),
		next_action = next_action,
	}),
		names
end

-- Load the BUILT place and check every compiled node really became an instance.
function Content.uiInspect(names: { string }, place: string): Run.Step
	local roblox = require("@lune/roblox")
	local missing = {}
	local ok, err = pcall(function()
		local game = roblox.deserializePlace(fs.readFile(place))
		local starterGui = game:GetService("StarterGui")
		for _, name in names do
			local spec = serde.decode("json", fs.readFile(`{Config.path("uiOut")}/{name}.model.json`))
			local gui = starterGui:FindFirstChild(name)
			if not gui then
				table.insert(
					missing,
					`StarterGui.{name} (is {Config.path("uiOut")} mapped to StarterGui in the Rojo project?)`
				)
				continue
			end
			local function walk(nodeSpec: any, inst: any, path: string)
				for _, child in nodeSpec.Children or {} do
					local found = inst:FindFirstChild(child.Name)
					if not found or found.ClassName ~= child.ClassName then
						table.insert(missing, `{path}.{child.Name} ({child.ClassName})`)
					else
						walk(child, found, `{path}.{child.Name}`)
					end
				end
			end
			walk(spec, gui, name)
		end
	end)
	local good = ok and #missing == 0
	return Run.step(`ui inspect {place}`, good, if ok then table.concat(missing, "\n") else tostring(err), {
		summary = if good then `{#names} screen(s) present` else nil,
		next_action = if good then nil else (missing[1] or tostring(err)),
	})
end

-- ---------------------------------------------------------------- kit gen: Hunyuan3D-2 (kit/gen/hunyuan_run.py)
-- Pictures OF one object, level: front = from in front of it (Roblox -Z), left = from ITS left side (-X), back,
-- right = from its right side (+X). Each is cut out (BiRefNet) first, as for TRELLIS.2.
local GEN_VIEWS = { "front", "left", "back", "right" }

local function genOpts(argv: { string }, flags: { [string]: any }, keys: { string })
	for _, k in keys do
		if flags[k] ~= nil and flags[k] ~= true then
			table.insert(argv, `--{k}`)
			table.insert(argv, tostring(flags[k]))
		end
	end
end

local function genMvShape(pos: { string }, flags: { [string]: any }): number
	local n = pos[2]
	local given = {}
	for _, v in GEN_VIEWS do
		if type(flags[v]) == "string" then
			given[v] = flags[v]
		end
	end
	if not n or not given.front then
		return Run.report(
			"gen",
			{},
			C.USAGE,
			"gen mv-shape: needs a name and at least --front <picture>",
			"lune run kit gen mv-shape <name> --front <pic> --left <pic> --back <pic> --right <pic>"
				.. "   (left = seen from the object's own left side: kit/gen/README.md)"
		)
	end
	for v, p in given do
		if not fs.isFile(p) then
			return Run.report("gen", {}, C.USAGE, `gen mv-shape: no picture at {p} (--{v})`, "check the path")
		end
	end
	local work = Config.build("gen")
	if not fs.isDir(work) then
		fs.writeDir(work)
	end
	local out = `{Config.path("models")}/{n}.gen.glb`
	local plan = {}
	local shape = { "kit/gen/hunyuan_run.py", "shape", out }
	for _, v in GEN_VIEWS do
		local p = given[v]
		if p then
			local cut = `{work}/{n}_{v}_cut.png`
			table.insert(plan, function()
				return Run.content(
					`cutout {n} {v}`,
					Run.tool("python"),
					{ "kit/vision/run.py", "cutout", p, "--rgba", "-o", cut }
				)
			end)
			table.insert(shape, `--{v}`)
			table.insert(shape, `{work}/{n}_{v}_cut_rgba.png`)
		end
	end
	genOpts(shape, flags, { "seed", "steps", "octree", "guidance", "model" })
	table.insert(plan, function()
		return Run.content(`hunyuan shape {n}`, Run.tool("hunyuan3d2"), shape)
	end)
	return Run.chain(
		`gen-{n}`,
		plan,
		content,
		`gen mv-shape: {out} (Roblox frame: front -Z; a PRIVATE experiment: Hunyuan licence) — try it in a MASTER `
			.. `build script: a.import_mesh("Body", "{out}", height=...)`
	)
end

local function genPaint(pos: { string }, flags: { [string]: any }): number
	local target, image = pos[2], flags.image
	if not target or type(image) ~= "string" or not fs.isFile(image) then
		return Run.report(
			"gen",
			{},
			C.USAGE,
			"gen paint: needs an asset (or a mesh file) and --image <picture>",
			"lune run kit gen paint <asset | mesh.glb> --image refs/<name>_front.png"
				.. "   (the picture shows it from the FRONT: kit/gen/README.md)"
		)
	end
	local src = target
	if not fs.isFile(target) then
		src = `{Config.build("models")}/{target}.blend` -- the FULL build, never the upload FBX (pre-turned for Roblox)
		if not fs.isFile(src) then
			return Run.report(
				`gen-paint-{target}`,
				{},
				C.CONTENT,
				`gen paint: {target} is neither a mesh file nor a built asset`,
				`build it first: lune run kit asset {target}   (or pass a .glb / .obj / .fbx path)`
			)
		end
	end
	local base = string.match(target, "([^/\\]+)$") or target
	local n = if type(flags.out) == "string" then flags.out else (string.match(base, "^([^.]+)") or base)
	local work = Config.build("gen")
	if not fs.isDir(work) then
		fs.writeDir(work)
	end
	local cut, prepared = `{work}/{n}_paint_cut.png`, `{work}/{n}_paint_in.glb`
	local out = `{Config.path("models")}/{n}.paint.glb`
	local prep =
		{ "-b", "--factory-startup", "--python-exit-code", "2", "-P", "kit/gen/hunyuan_prep.py", "--", src, prepared }
	genOpts(prep, flags, { "faces" })
	local paint = {
		"kit/gen/hunyuan_run.py",
		"paint",
		prepared,
		`{work}/{n}_paint_cut_rgba.png`,
		out,
		"--sheet",
		`{work}/{n}_paint_views.png`,
	}
	genOpts(paint, flags, { "seed", "texture" })
	return Run.chain(
		`gen-paint-{n}`,
		{
			function()
				return Run.content(
					`cutout {n}`,
					Run.tool("python"),
					{ "kit/vision/run.py", "cutout", image, "--rgba", "-o", cut }
				)
			end,
			function()
				return Run.content(`paint prep {n}`, Run.tool("blender"), prep)
			end,
			function()
				return Run.content(`hunyuan paint {n}`, Run.tool("hunyuan3d2"), paint)
			end,
		},
		content,
		`gen paint: {out} — the input mesh in its own frame with a painted base-colour map (a PRIVATE experiment: `
			.. "Hunyuan licence); carry it onto the kit's atlas in the build script"
	)
end

-- `kit gen parts <name> --image <picture> --parts <n>`: PartCrafter (kit/gen/partcrafter_run.py) — the picture is cut
-- out (BiRefNet), then the object is generated as n separate meshes, one GLB each (a.import_mesh takes one mesh).
local function genParts(n: string?, flags: { [string]: any }): number
	local image = flags.image
	local count = tonumber(flags.parts)
	if not n or type(image) ~= "string" or not fs.isFile(image) or not count or count < 1 or count > 16 then
		return Run.report(
			"gen",
			{},
			C.USAGE,
			"gen parts: needs a name, --image <picture> and --parts <1-16>",
			"lune run kit gen parts <name> --image refs/<name>_front.png --parts 4   (a sword: blade, guard, grip, pommel)"
		)
	end
	local work = Config.build("gen")
	if not fs.isDir(work) then
		fs.writeDir(work)
	end
	local cut, rgba = `{work}/{n}_cut.png`, `{work}/{n}_cut_rgba.png`
	local stem = `{Config.path("models")}/{n}`
	local gen = { "kit/gen/partcrafter_run.py", rgba, stem, "--parts", tostring(math.floor(count)) }
	for _, k in { "seed", "tokens", "steps", "guidance" } do
		if flags[k] ~= nil then
			table.insert(gen, `--{k}`)
			table.insert(gen, tostring(flags[k]))
		end
	end
	return Run.chain(`gen-parts-{n}`, {
		function()
			return Run.content(
				`cutout {n}`,
				Run.tool("python"),
				{ "kit/vision/run.py", "cutout", image, "--rgba", "-o", cut }
			)
		end,
		function()
			return Run.content(`partcrafter {n}`, Run.tool("partcrafter"), gen)
		end,
	}, content, `gen parts: {stem}.part1..{math.floor(count)}.glb — the import lines are in {stem}.parts.json`)
end

function Content.register(Cli: any, Steps: any)
	-- ---------------------------------------------------------------- 3D
	Cli.command(
		"3d",
		"asset",
		"asset <name|all> [--geo [--only <part words>]] [--fast] [--rebake] [--schematic] [--inspect <Part>]",
		"build assets/models/build_<name>.py → FBX + PBR maps + gates + labelled 6-view sheet (+ part close-up) + the views to LOOK at (build/judge/<name>/: six views and a reference | model pair per hero feature); --geo = shapes + every geometry/mechanism/reference check in seconds, no bake, with shaded views in build/judge/<name>/geo/; unchanged groups reuse their maps (--rebake: bake all); --schematic: also render the take-apart / line-art views kit schematic draws from",
		function(args)
			local pos, flags = Cli.parse(args)
			local dir = Config.path("models")
			local names = listNames(dir, "^build_(.+)%.py$")
			local target = pos[1]
			if not target then
				print("assets: " .. (if #names > 0 then table.concat(names, ", ") else "(none yet)"))
				return Run.report(
					"asset",
					{},
					C.USAGE,
					"asset: no name given",
					"run: lune run kit asset <name>   (new one: lune run kit new asset <name>)"
				)
			end
			local list = if target == "all" then names else { target }
			local plan = {}
			local refused: { string } = {} -- (kit asset all: the pieces its clock or route check held back)
			for _, n in list do
				local script = `{dir}/build_{n}.py`
				if not fs.isFile(script) then
					return Run.report(
						`asset-{n}`,
						{},
						C.CONTENT,
						`asset: {script} does not exist`,
						`create it: lune run kit new asset {n}`
					)
				end
				-- the quality lock: an asset made after the locks builds from its brief (a hero one: the owner-approved brief)
				-- and its reference study (every reference read, our version decided, the lessons cited: kit study)
				-- (a baked build also needs the blockout's approval: a shape round, --geo, never does; kit make's own
				-- builds of the script it wrote - it sets KIT_MAKE - are let through: it gathers and builds in one run)
				local locked = require("../lib/lanelocks").asset(
					n,
					nil,
					nil,
					nil,
					if process.env.KIT_MAKE == "1" then "make" elseif flags.geo then "geo" else "full"
				)
				if locked then
					return Run.report(
						`asset-{n}`,
						{},
						C.CONTENT,
						`asset: {n} skipped a quality step (brief / reference study / model sheet / blockout)`,
						locked
					)
				end
				-- the clock and the route: no build past the piece's budget, none on a route its lessons were not
				-- answered for (kit asset all asks each piece just before ITS build, below: a queued piece's clock is
				-- never started - nor its one fresh attempt spent - by a run that never reaches it)
				if target ~= "all" then
					local stop = Content.prebuild(n, dir)
					if stop then
						return Run.report(`asset-{n}`, {}, C.CONTENT, stop.summary, stop.next_action)
					end
				end
				local extra = if flags.fast then { "--no-preview" } else {}
				if flags.geo then
					table.insert(extra, "--geo")
				end
				if flags.rebake then
					table.insert(extra, "--rebake")
				end
				if flags.schematic then
					-- the take-apart / line-art views (kit schematic): asked for, not rendered by every build (they
					-- were 1,017 of one hero's 1,224 seconds on a round that changed its colour)
					table.insert(extra, "--schematic")
				end
				if type(flags.inspect) == "string" then
					table.insert(extra, "--inspect=" .. flags.inspect)
				end
				-- H3 (his limitations review): a shape round of some parts alone, in seconds (rbx.py _keep_only)
				if type(flags.only) == "string" then
					if not flags.geo then
						return Run.report(
							`asset-{n}`,
							{},
							C.USAGE,
							"asset: --only <part> is for a shape round (a full build exports the whole model)",
							`lune run kit asset {n} --geo --only {flags.only}`
						)
					end
					table.insert(extra, "--only")
					table.insert(extra, flags.only)
				end
				table.insert(plan, function(): Run.Step
					if target == "all" then
						local stop = Content.prebuild(n, dir, true)
						if stop then -- (the others still build; this one waits on its lessons)
							print(`[skipped] {stop.summary} - {stop.next_action}`)
							table.insert(refused, n)
							return {
								name = `asset {n}`,
								cmd = "",
								exit = 0,
								ok = true,
								tail = `skipped: {stop.summary}`,
							}
						end
					end
					-- the internal-lines inputs are written by THIS build's reference check: never compare stale ones
					local views = { "side", "front", "back", "top" }
					for _, view in views do
						local old = `{Config.build("renders")}/{n}_ref_{view}_lines.json`
						if fs.isFile(old) then
							fs.removeFile(old)
						end
					end
					local built = Content.blenderStep(`asset {n}`, script, extra)
					-- STYLE (kit/vision/style.py): a model that declares style images (Asset(style=[...])) - how close its
					-- look and silhouette come to them -> <name>_style.png. A report, never a gate — read before the
					-- labels are drawn on the sheet, and whatever the lines gate says
					local manifest = `{Config.build("models")}/{n}.manifest.json`
					if not flags.geo and not flags.fast and fs.isFile(manifest) then
						local okM, m = pcall(serde.decode, "json" :: any, fs.readFile(manifest))
						if okM and type(m) == "table" and m.facts and m.facts.style_refs then
							Run.content(`style {n}`, Run.tool("python"), { "kit/vision/style.py", manifest })
						end
					end
					if not flags.fast and not flags.geo then
						-- part names + the reference comparison onto the sheet (system python: Blender's has no
						-- PIL) — EVEN when the build failed its quality bar: that is exactly when the picture is needed
						Run.content(
							`labels {n}`,
							Run.tool("python"),
							{ "kit/blender/labels.py", `{Config.build("renders")}/{n}.png` }
						)
					end
					-- the per-part review sheets (every part family, in context + isolated); a --geo check composes
					-- only the families the review is asking about (<name>_parts_todo.png)
					local index = `{Config.build("renders")}/parts/{n}/index.json`
					if not flags.fast and fs.isFile(index) then
						local sheetArgs = { "kit/blender/partsheet.py", index }
						if flags.geo then
							table.insert(sheetArgs, "--todo-only")
						end
						Run.content(`parts {n}`, Run.tool("python"), sheetArgs)
					end
					-- INTERNAL LINES (kit/vision/lines.py, the vetted offline edge model): the reference photo's
					-- seams / plate edges / slots vs the shaded model's, inside the silhouette. Fails hero/aaa builds
					-- missing half the reference's lines; skips (and says so) when kit vision is not set up
					for _, view in views do
						local input = `{Config.build("renders")}/{n}_ref_{view}_lines.json`
						if fs.isFile(input) then
							local lines =
								Run.content(`lines {n} {view}`, Run.tool("python"), { "kit/vision/lines.py", input })
							-- PERCEPTUAL (kit/vision/perceive.py): the same frame through SigLIP 2 (the whole look) and DINOv2
							-- (where the model departs from the picture) -> <name>_perceptual_<view>.png. A report, never a
							-- gate — made even when the lines gate fails (that is when it shows most)
							if not flags.geo then
								Run.content(
									`perceptual {n} {view}`,
									Run.tool("python"),
									{ "kit/vision/perceive.py", input }
								)
							end
							if built.ok and not lines.ok then
								return lines
							end
						end
					end
					return built
				end)
			end
			if target == "all" then -- (every piece held back is no pass: nothing was built)
				table.insert(plan, function(): Run.Step
					if #list > 0 and #refused == #list then
						return {
							name = "asset all",
							cmd = "",
							exit = 1,
							ok = false,
							tail = "every piece was held back",
							result = {
								status = "fail",
								summary = `asset all: every piece was held back by its clock or its route check`,
								next_action = `show the owner what there is (the [skipped] lines above); only his words reopen a clock: lune run kit plan <name> --extend <minutes> "<his words>"`,
							},
						}
					end
					local held = if #refused > 0 then `held back: {table.concat(refused, ", ")}` else "none held back"
					return { name = "asset all", cmd = "", exit = 0, ok = true, tail = held }
				end)
			end
			if not flags.geo then -- a geometry check exports nothing: the game's models stay the last full build
				table.insert(plan, function()
					return (Content.modelsCompile(true))
				end)
			end
			local chainName = if target == "all" then "asset-all" else `asset-{target}`
			if flags.geo then
				chainName = if target == "all" then "asset-geo-all" else `asset-geo-{target}` -- never overwrites the full verdict
			end
			local built = if target == "all"
				then "built + gated (a piece its route check held back says [skipped] above)"
				else `{#list} built + gated`
			return Run.chain(
				chainName,
				plan,
				content,
				`asset: {built} — look at {Config.build("renders")}/<name>.png`
			)
		end
	)

	Cli.command(
		"3d",
		"optimize",
		"optimize <name> [--budget <triangles>] [--retopo [group,group]]",
		"make the GAME version of a master (Asset(stage=\"master\")): <name>_game — every mesh cut to the tier's triangle budget with the master's full detail baked onto it, then measured against the master: how far its surface moved, and the reference's silhouette / lines / look side by side",
		function(args)
			local pos, flags = Cli.parse(args)
			local n = pos[1]
			if not n then
				return Run.report(
					"optimize",
					{},
					C.USAGE,
					"optimize: no name given",
					'lune run kit optimize <name>   (a master: rbx.Asset(..., stage="master"), built first)'
				)
			end
			local script = `{Config.path("models")}/build_{n}.py`
			if not fs.isFile(script) then
				return Run.report(
					`optimize-{n}`,
					{},
					C.CONTENT,
					`optimize: {script} does not exist`,
					`create it: lune run kit new asset {n}`
				)
			end
			local function facts(model: string): any
				local ok, m = pcall(function()
					return serde.decode("json" :: any, fs.readFile(`{Config.build("models")}/{model}.manifest.json`))
				end)
				return if ok and type(m) == "table" then m else nil
			end
			local master = facts(n)
			if not master or master.stage ~= "master" then
				return Run.report(
					`optimize-{n}`,
					{},
					C.CONTENT,
					`optimize: {n} has no master build`,
					`make it a master (rbx.Asset(..., stage="master")), build it (lune run kit asset {n}), then optimize`
				)
			end
			-- (a game version is a build of the piece too: its clock and its route hold here as in kit asset, and so
			-- do the owner's stage approvals - a baked build)
			local staged = require("../lib/lanelocks").stages(n, nil, nil, "full")
			if staged then
				return Run.report(
					`optimize-{n}`,
					{},
					C.CONTENT,
					`optimize: {n} skipped a stage approval (model sheet / blockout)`,
					staged
				)
			end
			local stop = Content.prebuild(n, Config.path("models"))
			if stop then
				return Run.report(`optimize-{n}`, {}, C.CONTENT, stop.summary, stop.next_action)
			end
			local game = `{n}_game`
			local extra = { "--optimize" }
			if flags.budget then
				table.insert(extra, `--budget={flags.budget}`)
			end
			if flags.retopo == true then -- QuadriFlow (Blender's own remesher) on every group, or the named ones
				table.insert(extra, "--retopo")
			elseif type(flags.retopo) == "string" then
				table.insert(extra, `--retopo={flags.retopo}`)
			end
			local plan = {
				function()
					local old = `{Config.build("renders")}/{game}_ref_side_lines.json` -- (written by THIS build only)
					if fs.isFile(old) then
						fs.removeFile(old)
					end
					return Content.blenderStep(`optimize {n}`, script, extra)
				end,
				function()
					return Run.content(
						`labels {game}`,
						Run.tool("python"),
						{ "kit/blender/labels.py", `{Config.build("renders")}/{game}.png` }
					)
				end,
				function()
					-- the master and its game version through the SAME reference checks, side by side: the loss the
					-- player would see (silhouette IoU, the reference's inside lines found, the whole look)
					local function measure(model: string): { [string]: number? }
						local m = facts(model)
						local out: { [string]: number? } = {}
						for _, r in (m and m.facts and m.facts.references or {}) :: { any } do
							if r.view == "side" then
								out.iou = r.iou
							end
						end
						local input = `{Config.build("renders")}/{model}_ref_side_lines.json`
						if fs.isFile(input) then
							local l =
								Run.content(`lines {model} side`, Run.tool("python"), { "kit/vision/lines.py", input })
							local p = Run.content(
								`perceptual {model} side`,
								Run.tool("python"),
								{ "kit/vision/perceive.py", input }
							)
							out.lines = l.result and l.result.lines and l.result.lines.recall
							out.look = p.result and p.result.perceptual and p.result.perceptual.similarity
						end
						return out
					end
					local a, b = measure(n), measure(game)
					local rows, lost = {}, {}
					for _, k in
						{
							{ "iou", "silhouette IoU", 0.01 },
							{ "lines", "reference lines found", 0.05 },
							{ "look", "looks like the reference", 0.03 },
						}
					do
						local key, label, allowed = k[1] :: string, k[2] :: string, k[3] :: number
						local x, y = a[key], b[key]
						if type(x) == "number" and type(y) == "number" then
							table.insert(
								rows,
								string.format("%s: master %.3f -> game %.3f (%+.3f)", label, x, y, y - x)
							)
							if y < x - allowed then
								table.insert(lost, string.format("%s %.3f -> %.3f", label, x, y))
							end
						else
							table.insert(rows, `{label}: not measured (master {tostring(x)}, game {tostring(y)})`)
						end
					end
					local g = facts(game)
					local opt = g and g.facts and g.facts.optimize
					if opt and opt.summary then
						table.insert(rows, 1, opt.summary)
					end
					local ok = #lost == 0
					return Run.step(`compare {n} -> {game}`, ok, table.concat(rows, "\n"), {
						summary = table.concat(rows, "; "),
						next_action = if ok
							then `look at {Config.build("renders")}/{game}.png beside {n}.png — the game version is {game}`
							else `the game version loses what the player sees ({table.concat(lost, "; ")}) — give it more triangles: lune run kit optimize {n} --budget <more>`,
					})
				end,
			}
			if not master.private then
				table.insert(plan, function()
					return (Content.modelsCompile(true))
				end)
			end
			return Run.chain(
				`optimize-{n}`,
				plan,
				content,
				`optimize: {game} made from the master {n} — look at {Config.build("renders")}/{game}.png`
			)
		end
	)

	Cli.command(
		"3d",
		"showcase",
		"showcase <name> [--frames <n>] [--samples <n>]",
		"present a built model: a turntable and every mechanism moving in order (a reload sequence too) under the studio light -> build/showcase/<name>/ poster.png, turntable.gif, mechanism.gif",
		function(args)
			local pos, flags = Cli.parse(args)
			local n = pos[1]
			if not n then
				return Run.report(
					"showcase",
					{},
					C.USAGE,
					"showcase: no name given",
					"lune run kit showcase <name>   (after a full build: lune run kit asset <name>)"
				)
			end
			local blend = `{Config.build("models")}/{n}.blend`
			if not fs.isFile(blend) then
				return Run.report(
					`showcase-{n}`,
					{},
					C.CONTENT,
					`showcase: {n} has no full build`,
					`build it first: lune run kit asset {n}   (a master's game version: lune run kit optimize <master>)`
				)
			end
			local blender = {
				"-b",
				"--factory-startup",
				blend,
				"--python-exit-code",
				"2",
				"-P",
				"kit/blender/showcase.py",
				"--",
				n,
			}
			if flags.frames then
				table.insert(blender, `--frames={flags.frames}`)
			end
			if flags.samples then
				table.insert(blender, `--samples={flags.samples}`)
			end
			local out = Config.build(`showcase/{n}`)
			return Run.chain(`showcase-{n}`, {
				function()
					return Run.content(
						`showcase {n}`,
						Run.tool("blender"),
						blender,
						{ KIT_BUILD = Config.path("build") }
					)
				end,
				function()
					return Run.content(`showcase pack {n}`, Run.tool("python"), { "kit/blender/showcase_pack.py", out })
				end,
			}, content, `showcase: {out}/ — poster.png, turntable.gif, mechanism.gif`)
		end
	)

	-- kit gen omni: Hunyuan3D-Omni — the picture's shape, held to a control: a kit build's blockout (sampled as
	-- points, voxels or its box), a point cloud / voxel file, or a box. kit/gen/omni_run.py, kit/gen/README.md.
	local function genOmni(pos: { string }, flags: { [string]: any }): number
		local n, image, from = pos[2], flags.image, flags["from-asset"]
		local usage = "lune run kit gen omni <name> --image <picture> --from-asset <asset> [--group <g>] "
			.. "[--control point|voxel|bbox]   (or --points <file> | --voxels <file> | --bbox x,y,z)"
		if not n or type(image) ~= "string" or not fs.isFile(image) then
			return Run.report("gen-omni", {}, C.USAGE, "gen omni: needs a name and --image <picture>", usage)
		end
		local bbox = flags.bbox
		if type(bbox) == "string" and not string.find(bbox, "[,x]") and tonumber(pos[3]) and tonumber(pos[4]) then
			bbox = `{bbox},{pos[3]},{pos[4]}` -- `--bbox 4 3 2` as well as `--bbox 4,3,2`
		end
		local given = 0
		for _, v in { from, flags.points, flags.voxels, bbox } do
			given += if type(v) == "string" then 1 else 0
		end
		if given ~= 1 then
			return Run.report("gen-omni", {}, C.USAGE, "gen omni: give exactly ONE control", usage)
		end
		local work = Config.build("gen")
		if not fs.isDir(work) then
			fs.writeDir(work)
		end
		local cut, rgba = `{work}/{n}_cut.png`, `{work}/{n}_cut_rgba.png`
		local out = `{Config.path("models")}/{n}.gen.glb`
		local omni = { "kit/gen/omni_run.py", rgba, out }
		local plan = {
			function()
				return Run.content(
					`cutout {n}`,
					Run.tool("python"),
					{ "kit/vision/run.py", "cutout", image, "--rgba", "-o", cut }
				)
			end,
		}
		if type(from) == "string" then
			local blend = `{Config.build("models")}/{from}.blend`
			if not fs.isFile(blend) then
				return Run.report(
					`gen-omni-{n}`,
					{},
					C.CONTENT,
					`gen omni: {from} has no build to steer by`,
					`build it first: lune run kit asset {from}`
				)
			end
			local npz = `{work}/{n}_blockout.npz`
			local blender = { "-b", "--factory-startup", blend, "--python-exit-code", "2", "-P" }
			for _, a in { "kit/gen/omni_blockout.py", "--", from, npz } do
				table.insert(blender, a)
			end
			if type(flags.group) == "string" then
				table.insert(blender, "--group")
				table.insert(blender, flags.group)
			end
			table.insert(plan, function()
				return Run.content(`blockout {from}`, Run.tool("blender"), blender)
			end)
			table.insert(omni, "--blockout")
			table.insert(omni, npz)
			if type(flags.control) == "string" then
				table.insert(omni, "--control")
				table.insert(omni, flags.control)
			end
		elseif type(bbox) == "string" then
			table.insert(omni, "--bbox")
			table.insert(omni, bbox)
		else
			local k = if type(flags.points) == "string" then "points" else "voxels"
			table.insert(omni, `--{k}`)
			table.insert(omni, flags[k])
		end
		for _, k in { "seed", "steps", "guidance", "octree" } do
			if flags[k] ~= nil then
				table.insert(omni, `--{k}`)
				table.insert(omni, tostring(flags[k]))
			end
		end
		table.insert(plan, function()
			return Run.content(`omni {n}`, Run.tool("omni"), omni)
		end)
		return Run.chain(
			`gen-omni-{n}`,
			plan,
			content,
			`gen omni: {out} — import it in a MASTER build script with the line in {n}.gen.json ("import")`
		)
	end

	-- `gen views`: 2-4 posed views of one object -> Pixal3D multi-view (kit/gen/pixal3d_run.py, kit/gen/views_rig.py)
	local function genViews(n: string?, flags: { [string]: any }): number
		local views = flags.list.view or {}
		local usage =
			"lune run kit gen views <name> --view side=<rgba.png> --view front=<rgba.png> [--view back=<rgba.png>] [--view top=<rgba.png>] [--ortho] [--flip side] [--seed 7]"
		if not n or #views < 2 then
			return Run.report(
				"gen",
				{},
				C.USAGE,
				"gen views: needs a name and at least two --view <view>=<picture>",
				usage
			)
		end
		local out = `{Config.path("models")}/{n}.gen.glb`
		local cmd = { "kit/gen/pixal3d_run.py", out, "--work", Config.build(`gen/{n}_views`) }
		for _, v in views do
			local view, path = string.match(v, "^(%a+)=(.+)$")
			local known = view == "front" or view == "side" or view == "back" or view == "top"
			if not known or not fs.isFile(path) then
				return Run.report(
					"gen",
					{},
					C.USAGE,
					`gen views: --view {v} is not <front|side|back|top>=<an existing picture>`,
					usage
				)
			end
			table.insert(cmd, "--view")
			table.insert(cmd, v)
		end
		for _, f in flags.list.flip or {} do
			table.insert(cmd, "--flip")
			table.insert(cmd, f)
		end
		if flags.ortho ~= nil then
			table.insert(cmd, "--ortho")
		end
		if flags.resume ~= nil then -- export the shape the last run saved (build/gen/<name>_views/generated.pt)
			table.insert(cmd, "--resume")
		end
		for _, k in { "seed", "faces", "texture", "fov", "remesh" } do
			if flags[k] ~= nil then
				table.insert(cmd, `--{k}`)
				table.insert(cmd, tostring(flags[k]))
			end
		end
		return Run.chain(
			`gen-views-{n}`,
			{
				function()
					return Run.content(`pixal3d {n}`, Run.tool("trellis2"), cmd)
				end,
			},
			content,
			`gen views: {out} — import it in a MASTER build script: a.import_mesh("Body", "{out}", height=...)`
		)
	end

	Cli.command(
		"3d",
		"gen",
		"gen <name> --image <picture> [--seed <n>] [--faces <n>] [--texture <n>] [--res 512|1024] | gen texture <asset> --image <picture> [--group <g>] [--turn <deg>] [--seed <n>] | gen omni <name> --image <picture> --from-asset <asset> [--group <g>] [--control point|voxel|bbox] | gen parts <name> --image <picture> --parts <1-16> [--seed <n>] | gen mv-shape <name> --front <pic> [--left <pic>] [--back <pic>] [--right <pic>] [--model turbo|full] [--seed <n>] | gen paint <asset | mesh> --image <picture> [--out <name>] [--faces <n>] [--seed <n>] | gen views <name> --view side=<rgba.png> --view front=<rgba.png> [--view back=<rgba.png>] [--view top=<rgba.png>] [--ortho] [--flip <view>] [--seed <n>]",
		"generate a high-detail, textured mesh from ONE picture on this PC (TRELLIS.2, offline; the picture is cut out first) -> assets/models/<name>.gen.glb + .gen.json; import it in a MASTER build script: a.import_mesh(...), then kit optimize. `gen texture`: paint an asset's OWN last build from a picture -> assets/models/<asset>.tex.glb + .tex.json; bake it on: a.texture_from(...). `gen parts`: the object as SEPARATE part meshes (PartCrafter, untextured) -> assets/models/<name>.part<k>.glb + .parts.glb + .parts.json (with the import lines). `gen mv-shape`: a shape from up to 4 views of the object (Hunyuan3D-2mv; private assets only) -> <name>.gen.glb. `gen paint`: a texture for an existing asset or mesh from one picture (Hunyuan3D-2 Delight + Paint; private assets only) -> <name>.paint.glb in the input's frame. `gen views`: from 2-4 cut-out views of one object (a reference chart's side/front/back/top; --ortho for drawings) with Pixal3D (MIT), the shape lined up with every view",
		function(args)
			local pos, flags = Cli.parse(args)
			if pos[1] == "texture" then
				return Content.genTexture(pos[2], flags)
			elseif pos[1] == "omni" then
				return genOmni(pos, flags)
			elseif pos[1] == "parts" then
				return genParts(pos[2], flags)
			elseif pos[1] == "mv-shape" then
				return genMvShape(pos, flags)
			elseif pos[1] == "paint" then
				return genPaint(pos, flags)
			elseif pos[1] == "views" then
				return genViews(pos[2], flags)
			end
			local n, image = pos[1], flags.image
			if not n or type(image) ~= "string" or not fs.isFile(image) then
				return Run.report(
					"gen",
					{},
					C.USAGE,
					"gen: needs a name and --image <picture>",
					"lune run kit gen <name> --image refs/<name>_front.png   (one object, a plain background: kit/gen/README.md)"
				)
			end
			local work = Config.build("gen")
			if not fs.isDir(work) then
				fs.writeDir(work)
			end
			local cut, rgba = `{work}/{n}_cut.png`, `{work}/{n}_cut_rgba.png`
			local out = `{Config.path("models")}/{n}.gen.glb`
			local gen = { "kit/gen/trellis2_run.py", rgba, out }
			for _, k in { "seed", "faces", "texture", "res" } do
				if flags[k] ~= nil then
					table.insert(gen, `--{k}`)
					table.insert(gen, tostring(flags[k]))
				end
			end
			return Run.chain(`gen-{n}`, {
				function()
					return Run.content(
						`cutout {n}`,
						Run.tool("python"),
						{ "kit/vision/run.py", "cutout", image, "--rgba", "-o", cut }
					)
				end,
				function()
					return Run.content(`trellis2 {n}`, Run.tool("trellis2"), gen)
				end,
			}, content, `gen: {out} — import it in a MASTER build script: a.import_mesh("Body", "{out}", height=...)`)
		end
	)

	Cli.command(
		"3d",
		"models",
		"models",
		"rebuild src/models/*.model.json from the built assets + their uploaded ids (kit asset/upload do this too)",
		function()
			return Run.chain("models", {
				function()
					return (Content.modelsCompile(true))
				end,
			}, content, 'models: KitModels up to date — spawn one with Models.spawn("<asset>")')
		end
	)

	Cli.command(
		"3d",
		"validate",
		"validate <file.fbx|.blend>",
		"run the Roblox mesh gate on any model file (downloads, hand-made)",
		function(args)
			if not args[1] then
				return Run.report(
					"validate",
					{},
					C.USAGE,
					"validate: no file given",
					"run: lune run kit validate path/to/model.fbx"
				)
			end
			return Run.chain("validate", {
				function()
					return Content.blenderStep("validate " .. args[1], "kit/blender/validate.py", { args[1] })
				end,
			}, content, "validate: " .. args[1] .. " passes the Roblox gate")
		end
	)

	Cli.command(
		"3d",
		"calibrate",
		"calibrate",
		"build the axis/scale calibration FBX (import once in Studio)",
		function()
			return Run.chain(
				"calibrate",
				{
					function()
						return Content.blenderStep("calibration", "kit/blender/calibration.py", {})
					end,
				},
				content,
				`calibrate: import {Config.build("models")}/calibration.fbx in Studio — expect 4x4x4 studs, red arrow = front (-Z)`
			)
		end
	)

	-- ---------------------------------------------------------------- sound
	Cli.command(
		"sfx",
		"sfx",
		"sfx <name|all>  |  sfx <sheet|set|listen|av|match|find|index|identity|modal|mix|catalog> ...",
		"render assets/sounds/<name>.json → OGG + audio gate + numeric ears; the sub-commands (kit/cmd/sfx.luau) are the rest of the SFX pipeline",
		function(args)
			local SfxSub = require("./sfx")
			if SfxSub.has(args[1]) then
				return SfxSub.run(args)
			end
			local target = args[1] or "all"
			local dir = Config.path("sounds")
			if target ~= "all" and not fs.isFile(`{dir}/{target}.json`) then
				return Run.report(
					`sfx-{target}`,
					{},
					C.CONTENT,
					`sfx: no recipe {dir}/{target}.json`,
					`create it: lune run kit new sound {target}   (existing: {table.concat(
						listNames(dir, "^(.+)%.json$"),
						", "
					)})`
				)
			end
			local out = Config.build("sounds")
			-- its clock and route (kit/lib/prebuild.luau); every sound: the ones past their budget or made a new way
			local held = if target ~= "all" then Content.laneHeld("sfx", target) else Content.laneHeldAll("sfx", dir)
			if held then
				return held
			end
			return Run.chain(if target == "all" then "sfx-all" else `sfx-{target}`, {
				function() -- the quality lock: a sound made after the locks renders on the owner's chosen reference
					local LaneLocks = require("../lib/lanelocks")
					return LaneLocks.report(
						"sfx quality lock",
						LaneLocks.sfx({ target }, "sounds"),
						"every new sound has the owner's reference"
					)
				end,
				function()
					return Content.synthStep({ target })
				end,
				function()
					return Content.audioCheckStep(if target == "all" then out else `{out}/{target}.ogg`)
				end,
			}, content, `sfx: {target} rendered + gated — read the ears in .verify/sfx-{target}.json`)
		end
	)

	Cli.command(
		"sfx",
		"audio-check",
		"audio-check <file|dir>",
		"Roblox audio gate + numeric ears on any sound file",
		function(args)
			local target = args[1] or Config.build("sounds")
			return Run.chain("audio-check", {
				function()
					return Content.audioCheckStep(target)
				end,
			}, content, "audio-check: " .. target .. " passes")
		end
	)

	-- ---------------------------------------------------------------- vfx
	Cli.command(
		"vfx",
		"vfx",
		'vfx [name ...] | vfx breakdown <set> --clip <file> [--fps 2] | vfx breakdown <set> --dense [--beat N] | vfx chart <set> [--key N] [--test <png|mp4@s>] | vfx bar <style> <clip> [--from s --to s] [--approved] | vfx measure <name> --vs-bar <style> | vfx evolve <name> [--sheet | --pick K "<words>"] | vfx cost <name> | vfx play <name> [--record] [--variant v] | vfx dailies <name> [--view v] [--beat N] [--frames 12] | vfx stylesheet <name> [--view v] | vfx fracture <name> --size w,d[,h] [--shape slab|disc] [--pieces 14] [--impact x,z] | vfx flare [--light x,y] [--ghosts 5] [--streak 0.6] [--squeeze 1.6] | vfx settle <plan> [--life 2.5] [--gravity 120] [--speed 30] | vfx field <name> [--new vortex|wind|fountain|path] | vfx forced [--ref 40] [--keep 1] [--at 10,40,160] | vfx comp <key> [--new ring|skin|blobs|branches|map] | vfx dissolve <key> --from <texture key|plain> [--cells 16] [--pattern patches|dither] [--soft 0.08] [--edge 0.06 --edge-color r,g,b] | vfx methods [<words> | --set <set> [--beat N --use id,id --not id="why"]] | vfx migrate [<name> ...] [--apply] [--judged "<owner words>"] | vfx impostor <sim> [--angles 8..16] [--light side] | vfx track <set> [--beat N] [--window a,b] | vfx trace <set> [--track] [--beat N] [--tones 3] [--box x0,y0,x1,y1] [--window a,b] | vfx ink <key> --from <trace.json> [--drawings a-b] [--cell 256] [--between 1] [--register beat|drawing] | vfx booth <name> | vfx judge <name> [--record f] | vfx refs <name> <url|file>... | vfx import <dir> --prefix p | vfx expand <name> | vfx vault [check | list | find "<words>" | get <effect> --as <new> | verdict <effect> "<words>" [--score N]]',
		"Blender fx renders + finish, textures + gate, validate every preset, simulate v1/v2 into frame strips; `vfx booth` captures a v3 preset in the real engine; `vfx play` serves the browser player (full frame rate, metrics; --record = mp4 + metrics gate)",
		function(args)
			if args[1] == "booth" then
				-- a capture of the preset as it is (a look): its clock starts only if it changed - kit/lib/prebuild.luau
				local held = Content.laneHeld("vfx", args[2], true)
				if held then
					return held
				end
				return Content.vfxBooth(args[2], { table.unpack(args, 3) })
			end
			if args[1] == "vault" then
				-- the VFX library: `vfx vault` (save) | check | list | find "<words>" | get <effect> --as <new> | verdict
				local sub = args[2] or "save"
				local vargs = vfxVaultArgs(sub)
				for k = 3, #args do
					table.insert(vargs, args[k])
				end
				local step = Run.content("vfx vault", Run.tool("python"), vargs)
				local r = step.result or {}
				return Run.report(
					"vfx",
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or "vfx vault: crashed",
					r.next_action or "read the error above"
				)
			end
			if args[1] == "play" then
				local held = Content.laneHeld("vfx", args[2], true) -- (a look: its route holds, no clock)
				if held then
					return held
				end
				return Content.vfxPlay(args[2], { table.unpack(args, 3) })
			elseif args[1] == "expand" then
				return Content.vfxExpand(args[2], { table.unpack(args, 3) })
			elseif args[1] == "judge" then
				return Content.vfxJudge(args[2], { table.unpack(args, 3) })
			elseif VFX_ROUTE_TOOLS[args[1]] then
				if args[1] == "evolve" then -- (a round of variants is a build: its clock and route first)
					local held = Content.laneHeld("vfx", args[2])
					if held then
						return held
					end
				end
				-- the verdict lock (kit new's, 2026-10-21) on the director's way in too: a NEW original waits while the lane
				-- holds OPEN_CAP pieces the owner has not scored (2026-10-24: firewhirl was briefed and built over it)
				if args[1] == "director" and args[2] == "new" then
					local LaneLocks = require("../lib/lanelocks")
					local open = LaneLocks.unscored("vfx", { Config.root() }) -- (this project's: the cap is per game)
					-- a brief not built yet is an open piece too (review 2026-10-24: briefs a, b, c all passed at 2 open)
					if fs.isDir("assets/effects/briefs") then
						for _, f in fs.readDir("assets/effects/briefs") do
							local n = string.match(f, "^(.+)%.md$")
							-- a waived brief (the owner let it past the verdict lock) holds no slot, as LaneLocks.unscored skips waivers
							if
								n
								and not fs.isFile(`assets/effects/{n}.json`)
								and not table.find(open, n)
								and Locks.waiver("vfx", n, "verdict") == nil
							then
								table.insert(open, n)
							end
						end
					end
					local waived = args[3] ~= nil and Locks.waiver("vfx", args[3], "verdict") ~= nil
					if #open >= LaneLocks.OPEN_CAP and not table.find(open, args[3] or "") and not waived then
						return Run.report(
							"vfx",
							{},
							C.CONTENT,
							`vfx director new: the vfx lane has {#open} pieces the owner has not scored ({table.concat(
								open,
								", "
							)}) - the cap is {LaneLocks.OPEN_CAP} (quality lock)`,
							`show the owner {open[1]} and record their verdict: lune run kit verdict vfx {open[1]} <0-10> "<their words>"`
						)
					end
					-- enforced learning (board/plans/archive/2026-11-09-enforced-learning-plan.md, rules 1 and 3): a new original
					-- waits, as in kit new, until the lane's owner verdicts have taught their lessons and had their looks
					local owed = require("../lib/vault").owedLines("vfx")
					if #owed > 0 then
						for _, l in owed do
							print(`  {l}`)
						end
						return Run.report(
							"vfx",
							{},
							C.CONTENT,
							`vfx director new: the vfx lane owes {#owed} thing(s) from the owner's verdicts (a lesson to learn, a look not taken) - pay them before starting a new piece`,
							`lune run kit lesson vfx "<what it taught>" --verdict <name> / kit verdict learned|looked <kind> <name>`
						)
					end
				end
				-- the route's own tools (mission 02-vfx): kit vfx breakdown / chart / ... -> kit/vfx/<tool>.py
				local toolArgs = string.split(VFX_ROUTE_TOOLS[args[1]], " ")
				-- the tools that read a PRESET read the active project's (a game's when one is active): the folder
				-- kit review and kit approve --stage style read too, so a sheet drawn here is the one they check. It
				-- goes right after the effect's name: at the end, a flag the caller left without a value took it for
				-- its own and the sheet was drawn from another folder (a review, 2026-11-12)
				local named = args[2] ~= nil and string.sub(args[2], 1, 2) ~= "--"
				-- (cost reads a preset's kept files - a fracture plan, a field - from the same folder: without it a game's
				-- plan was looked for in the project's root and said "not counted")
				local own = (
					args[1] == "stylesheet"
					or args[1] == "dailies"
					or args[1] == "animatic"
					or args[1] == "cost"
				)
					and named
					and not table.find(args, "--effects")
				for k = 2, #args do
					table.insert(toolArgs, args[k])
					if k == 2 and own then
						table.insert(toolArgs, "--effects")
						table.insert(toolArgs, Config.path("vfx"))
					end
				end
				if args[1] == "ink" then
					-- its spec and frames go where the build step reads them, and a kept trace is the project's
					-- own (a game's folders when one is active)
					for _, pair in
						{
							{ "--specs-dir", Config.path("textures") },
							{ "--frames-dir", Config.build("fxlab") },
							{ "--kept-dir", Config.path("vfx") .. "/refs_measured" },
						}
					do
						if not table.find(args, pair[1]) then
							table.insert(toolArgs, pair[1])
							table.insert(toolArgs, pair[2])
						end
					end
				end
				if args[1] == "points" and not table.find(args, "--out-dir") then
					-- the cloud goes beside the project's presets (VfxPresets.points.<name> in the game)
					table.insert(toolArgs, "--out-dir")
					table.insert(toolArgs, Config.path("vfx") .. "/points")
				end
				if
					(
						args[1] == "cloth"
						or args[1] == "soft"
						or args[1] == "sand"
						or args[1] == "hair"
						or args[1] == "geonodes"
						or args[1] == "water"
					) and not table.find(args, "--out-dir")
				then
					-- a baked simulation is a mesh sequence of the project's (VfxPresets.seq.<name> in the game)
					table.insert(toolArgs, "--out-dir")
					table.insert(toolArgs, Config.path("vfx") .. "/seq")
				end
				if args[1] == "field" and not table.find(args, "--out-dir") then
					-- the field goes beside the project's presets (VfxPresets.fields.<name> in the game)
					table.insert(toolArgs, "--out-dir")
					table.insert(toolArgs, Config.path("vfx") .. "/fields")
				end
				if args[1] == "settle" and not table.find(args, "--plans-dir") then
					table.insert(toolArgs, "--plans-dir")
					table.insert(toolArgs, Config.path("vfx") .. "/fractures")
				end
				if args[1] == "fracture" and not table.find(args, "--out-dir") then
					-- the plan goes beside the project's presets (VfxPresets.fractures.<name> in the game)
					table.insert(toolArgs, "--out-dir")
					table.insert(toolArgs, Config.path("vfx") .. "/fractures")
				end
				if args[1] == "comp" then
					-- its spec, the built textures a mapped stack reads and the frames it writes are the project's own
					for _, pair in
						{
							{ "--textures-dir", Config.build("textures") },
							{ "--specs-dir", Config.path("textures") },
							{ "--frames-dir", Config.build("fxlab") },
						}
					do
						if not table.find(args, pair[1]) then
							table.insert(toolArgs, pair[1])
							table.insert(toolArgs, pair[2])
						end
					end
				end
				if args[1] == "liquid" then
					-- the spec and the frames it writes are the project's own
					for _, pair in
						{ { "--specs-dir", Config.path("textures") }, { "--frames-dir", Config.build("fxlab") } }
					do
						if not table.find(args, pair[1]) then
							table.insert(toolArgs, pair[1])
							table.insert(toolArgs, pair[2])
						end
					end
				end
				if args[1] == "dissolve" then
					-- the built textures it reads and the spec and frames it writes are the project's own
					for _, pair in
						{
							{ "--textures-dir", Config.build("textures") },
							{ "--specs-dir", Config.path("textures") },
							{ "--frames-dir", Config.build("fxlab") },
						}
					do
						if not table.find(args, pair[1]) then
							table.insert(toolArgs, pair[1])
							table.insert(toolArgs, pair[2])
						end
					end
				end
				if args[1] == "methods" then
					-- a scene's plan is read and written beside the project's presets (a game's when one is active)
					for _, pair in { { "--effects", Config.path("vfx") }, { "--textures", Config.path("textures") } } do
						if not table.find(args, pair[1]) then
							table.insert(toolArgs, pair[1])
							table.insert(toolArgs, pair[2])
						end
					end
					-- its answer IS what it prints (the list, a method, a scene's plan): every line is shown, then
					-- its verdict (a step keeps only the last lines of a tool's output)
					local res = process.exec(Run.tool("python"), toolArgs)
					local lines = string.split((string.gsub(res.stdout, "\r", "")), "\n")
					local last = #lines
					while last > 0 and not string.match(lines[last], "%S") do
						last -= 1
					end
					for i = 1, last - 1 do
						print(lines[i])
					end
					local okV, v = pcall(serde.decode, "json" :: any, if last > 0 then lines[last] else "")
					if not okV or type(v) ~= "table" or type(v.summary) ~= "string" then
						local err = string.match(res.stderr, "([^\n]+)%s*$") or "no output"
						return Run.report("vfx", {}, C.CONTENT, `vfx methods: crashed: {err}`, "read the error above")
					end
					return Run.report(
						"vfx",
						{},
						if res.ok and (v.status == "pass" or v.status == "warn") then C.PASS else C.CONTENT,
						v.summary,
						tostring(v.next_action or "none")
					)
				end
				local step = Run.content(`vfx {args[1]}`, Run.tool("python"), toolArgs)
				local r = step.result or {}
				return Run.report(
					"vfx",
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or `vfx {args[1]}: crashed`,
					r.next_action or "read the error above"
				)
			elseif args[1] == "refs" or args[1] == "import" then
				-- kit vfx refs <preset> <url|file|dir>... (stills into assets/effects/refs/<preset>, sources logged)
				-- kit vfx import <dir> --prefix <p> --pack "<name>" (a vetted sprite pack -> texture specs)
				local script = if args[1] == "refs" then "kit/vfx/refs.py" else "kit/vfx/import_pack.py"
				local step = Run.content(`vfx {args[1]}`, Run.tool("python"), { script, table.unpack(args, 2) })
				local r = step.result or {}
				return Run.report(
					"vfx",
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or `vfx {args[1]}: crashed`,
					r.next_action or "read the error above"
				)
			end
			-- every preset is rebuilt (the named ones previewed): each named one's clock and route, then the lane's
			for _, n in args do
				local held = Content.laneHeld("vfx", n)
				if held then
					return held
				end
			end
			local heldAll = Content.laneHeldAll("vfx", Config.path("vfx"))
			if heldAll then
				return heldAll
			end
			return Run.chain("vfx", {
				function()
					return Content.gpuSimStep() or Run.step("gpu sims", true, "no gpu sim specs", nil)
				end,
				function()
					return Content.inkStep() or Run.step("ink sheets", true, "no ink specs", nil)
				end,
				function()
					return Content.compStep(false) or Run.step("comp sheets", true, "no comp specs", nil)
				end,
				function()
					return Content.liquidStep() or Run.step("liquid sheets", true, "no liquid specs", nil)
				end,
				function()
					return Content.fxRenderStep() or Run.step("fx renders", true, "no fx specs", nil)
				end,
				function()
					return Content.fxFinishStep() or Run.step("fx finish", true, "no fx specs", nil)
				end,
				function()
					return Content.compStep(true) or Run.step("comp sheets (mapped)", true, "no mapped comp specs", nil)
				end,
				function()
					return Content.dissolveStep() or Run.step("dissolve sheets", true, "no dissolve specs", nil)
				end,
				function()
					return Content.flipbooksStep() or Run.step("flipbooks", true, "no blender flipbooks", nil)
				end,
				function()
					return Content.texturesStep({ "all" })
				end,
				function() -- the texture library sheet: pick an existing element before rendering a new one
					return Run.content("fx library", Run.tool("python"), {
						"kit/vfx/library.py",
						"--registry",
						Config.path("vfx") .. "/_textures.json",
						"--specs",
						Config.path("textures"),
						"--effects",
						Config.path("vfx"),
						"--out",
						Config.build("textures"),
					})
				end,
				function()
					return Content.vfxMeshesStep() or Run.step("vfx meshes", true, "no mesh specs", nil)
				end,
				Content.vfxPresetsStep,
				function() -- the SurfaceAppearance templates a live game clones (a script cannot set the maps)
					return Run.content("vfx surfaces", Run.tool("python"), { "kit/vfx/surfaces.py" })
				end,
				function()
					return Content.vfxPreviewStep(args)
				end,
				function() -- what a named effect's fresh preview LOOKS like among the past pieces (kit alike: a report)
					return require("../lib/alike").previewStep("vfx", args, Config.build("vfx"))
				end,
				-- the owner's rule: everything made is saved, packaged by part, in library/vfx
				Content.vfxVaultStep,
			}, content, `vfx: presets valid + previews in {Config.build("vfx")}, saved in library/vfx — look at them`)
		end
	)

	-- ---------------------------------------------------------------- ui
	Cli.command(
		"ui",
		"ui",
		'ui [<Screen ...>] [--motion] | fonts | identities | plan <Screen> | look <Screen> "<seen>" | judge <Screen ...> [--record v.json] [--owner <score> "<words>"] | reel <Screen> | booth <Screen> | refs <identity> "<game>" "<words>" | measure <still> | read <still> [--crops] [--draft <Screen>] | read motion <clip> | read type <crop> | spin <id>/<piece> [--material gold] | icon find "<words>" | icon make <id>/<piece> --icon <name> | read rank <folder> "<what>" | identity <id> --from refs | ink <id>/<piece> --from <picture> [--mode ink|cel|icon] | letter <id>/<piece> --text ... [--style persona] | smear <id>/<piece> --from <picture> [--split] | render <id>/<piece> | trace <id>/<piece> --from <still> | gauge <Screen> | find "<words>" | bundle <Screen> | hudsize [<Hud>]',
		"fonts → kit art → lettering (\"lettering\" words baked) → every identity's plates → compile assets/ui/*.json (gates) → build → built-place check → phone/tablet/desktop previews (--motion: the arrival strip). The hero route (parallax-ui skill): refs + measure → identity → pieces (ink a real picture, letter, render, trace) → assemble → look → judge (two fresh judges; --owner keeps the owner's verdict as an anchor) → promote. reel = gameplay motion as a GIF from <Screen>.reel.json; booth = the screen in Studio; find = the proven-piece bank; plan = the stage board",
		function(rawArgs)
			local sub = rawArgs[1]
			-- each subcommand keeps its own record (.verify/ui-<sub>.json): .verify/ui.json is the build gate alone - a
			-- plan or judge writing there showed the gate red in kit status and wiped the build notes the plan reads
			local rec = if type(sub) == "string" and sub ~= "" then `ui-{sub}` else "ui"
			if sub == "booth" then
				-- `kit ui booth <Screen> [--moments 0,0.15,0.4,1,2] [--job <reel job.json>] [--match <place>]`: the screen
				-- judged in the REAL engine — the scratch place's own copy of it, its arrival played by the game's own Ui
				-- runtime and read from Studio's window at every moment through the shared capture bridge
				-- (kit/tools/studio_capture.py; kit/vfx/capture.py studio). Result: build/ui/booth/<Screen>_engine.png
				local name = rawArgs[2]
				if type(name) ~= "string" or name == "" or string.sub(name, 1, 2) == "--" then
					return Run.report(
						rec,
						{},
						C.USAGE,
						"ui booth: needs a screen name",
						"lune run kit ui booth <Screen>"
					)
				end
				local model = `{Config.path("uiOut")}/{name}.model.json`
				if not fs.isFile(model) then
					return Run.report(rec, {}, C.USAGE, `ui booth: no compiled model at {model}`, "lune run kit ui")
				end
				local job: { [string]: any } = { screen = name, moments = { 0, 0.15, 0.4, 1, 2 }, settle = 0.6 }
				local i = 3
				while i <= #rawArgs do
					local flag, v = rawArgs[i], rawArgs[i + 1]
					if flag == "--moments" and v then
						local ts = {}
						for _, t in string.split(v, ",") do
							local n = tonumber(t)
							if n then
								table.insert(ts, n)
							end
						end
						job.moments = ts
					elseif flag == "--settle" and v then
						job.settle = tonumber(v)
					end
					i += 2
				end
				local dir = Config.build("ui") .. "/booth"
				Config.ensureDir(dir)
				local runName = name
				local given = flagValue(rawArgs, "--job") -- a prepared job (a reel's states: kit/ui/reel.py --states)
				if given then
					if not fs.isFile(given) then
						return Run.report(
							rec,
							{},
							C.USAGE,
							`ui booth: no job {given}`,
							"python kit/ui/reel.py <Screen> --states t,t,..."
						)
					end
					job = serde.decode("json", fs.readFile(given))
					job.screen = job.screen or name
					runName = string.match(given, "([^/\\]+)%.job%.json$")
						or string.match(given, "([^/\\]+)%.json$")
						or name
				end
				local jobPath = `{dir}/{runName}.job.json`
				if given ~= jobPath then
					fs.writeFile(jobPath, serde.encode("json", job, true) .. "\n")
				end
				local made, why = studioSnippets("ui_booth", jobPath, `{dir}/{runName}`)
				if not made then
					return Run.report(
						rec,
						{},
						C.CONTENT,
						`ui booth: the Studio script was not written: {why}`,
						"python kit/tools/studio_capture.py snippet ui_booth --job "
							.. jobPath
							.. " --out "
							.. dir
							.. "/"
							.. runName
					)
				end
				local match = flagValue(rawArgs, "--match") or "KitPlaytestScratch"
				studioSteps(
					`python kit/vfx/capture.py studio --name {runName} --job {jobPath} --match {match} --out {dir} --crop 0,0,0,0`,
					made.files,
					`{dir}/{runName}.result.json`,
					`when the capture exits: LOOK at {dir}/{runName}_{if job.states then "reel" else "engine"}.png (the engine's own frames at every moment); the owner's one-key rating: python kit/ui/rate.py {name}`
				)
				return Run.report(
					rec,
					{},
					C.PASS,
					`ui booth: {name} ready ({if job.states then #job.states.moments else #job.moments} moments)`,
					"run steps 1 + 2 above, then look at the sheet; the screen is the scratch place's own copy (rebuild the place after compiling it: lune run kit playtest place); art not uploaded yet shows blank in the engine (lune run kit upload)"
				)
			end
			if sub == "bundle" then
				-- a compiled screen as a Studio script: run it through the Studio MCP (execute_luau) to see the screen in
				-- the engine — real fonts, real gradients, the motion when played — before anything uploads
				local name = rawArgs[2]
				local model = name and `{Config.path("uiOut")}/{name}.model.json`
				if not model or not fs.isFile(model) then
					return Run.report(
						rec,
						{},
						C.CONTENT,
						`ui bundle: no compiled screen {tostring(name)}`,
						"lune run kit ui   (then: lune run kit ui bundle <Screen>)"
					)
				end
				local builder = fs.readFile("kit/ui/studio_builder.luau")
				local json = fs.readFile(model)
				local out = Config.build("ui") .. `/{name}.studio.luau`
				Config.ensureDir(Config.build("ui"))
				local script = string.gsub(builder, "__NAME__", name)
				script = string.gsub(script, "__JSON__", function()
					return json
				end)
				fs.writeFile(out, script)
				return Run.report(
					rec,
					{},
					C.PASS,
					`ui bundle: {out} ({#script} bytes)`,
					`run its contents in Roblox Studio through the Studio MCP (execute_luau, datamodel Edit); it replaces StarterGui.{name} in the open place without saving; then screen_capture`
				)
			end
			if sub == "render" then
				-- a UI piece RENDERED in Blender (chrome logotypes, lit plates): assets/ui/art/<identity>/<name>.render.json
				-- -> assets/ui/art/<identity>/<name>.png (kit ui takes it in as art:<identity>/<name>)
				local target = rawArgs[2]
				if type(target) ~= "string" or not string.find(target, "/", 1, true) then
					return Run.report(
						rec,
						{},
						C.USAGE,
						"ui render: name the piece as <identity>/<name>",
						"lune run kit ui render action/rank_sss   (its spec: assets/ui/art/action/rank_sss.render.json)"
					)
				end
				local specPath = `{Config.path("ui")}/art/{target}.render.json`
				local outPath = `{Config.path("ui")}/art/{target}.png`
				if not fs.isFile(specPath) then
					return Run.report(
						rec,
						{},
						C.USAGE,
						`ui render: no spec at {specPath}`,
						"write it (the shape: top of kit/ui/render.py), then run again"
					)
				end
				local step = Content.blenderStep(
					`ui render {target}`,
					"kit/ui/render.py",
					{ "--spec", specPath, "--out", outPath }
				)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step, Content.uiVaultStep() }, -- (the rule: everything made is saved to library/ui)
					if step.ok then C.PASS else C.CONTENT,
					r.summary or `ui render {target}: Blender failed`,
					r.next_action or "read the Blender output above"
				)
			end
			if sub == "trace" then
				-- a piece traced from a reference picture: crop at 1:1, upscale, cut out, (a gauge: blank the cells,
				-- anchor the wells). kit/ui/trace.py takes the rest of the arguments as given.
				local target = rawArgs[2]
				if type(target) ~= "string" or not string.find(target, "/", 1, true) then
					return Run.report(
						rec,
						{},
						C.USAGE,
						'ui trace: name the piece as <identity>/<name>, then --from <picture> --box x,y,w,h [--x 4] [--cutout] [--gauge] [--repaint "..."]',
						"lune run kit ui trace action/emblem_gear --from assets/ui/refs/action/styles_sheet.png --box 30,13,172,172 --cutout"
					)
				end
				local args = { "kit/ui/trace.py", "--art", `{Config.path("ui")}/art` }
				for i = 2, #rawArgs do
					table.insert(args, rawArgs[i])
				end
				local step = Run.content(`ui trace {target}`, Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step, Content.uiVaultStep() }, -- (the rule: everything made is saved to library/ui)
					if step.ok then C.PASS else C.CONTENT,
					r.summary or `ui trace {target}: crashed`,
					r.next_action or "read the error above"
				)
			end
			if sub == "refs" then
				-- reference gathering as one command: real stills of a game's screen type from the Steam store API,
				-- a Fandom wiki's MediaWiki API and the owner's drop folder, into refs/<identity>/candidates with a
				-- contact sheet; --keep promotes the chosen ones and writes their REFS.md lines. No gated page is bypassed.
				local ident = rawArgs[2]
				-- (--index / --tag <file>=<kind> / --waive "<owner words>": the stills as data, no game or words needed)
				local manifest = rawArgs[3] == "--index" or rawArgs[3] == "--tag" or rawArgs[3] == "--waive"
				if
					type(ident) ~= "string"
					or ident == ""
					or string.sub(ident, 1, 2) == "--"
					or (not manifest and (type(rawArgs[3]) ~= "string" or type(rawArgs[4]) ~= "string"))
				then
					return Run.report(
						rec,
						{},
						C.USAGE,
						'ui refs: <identity> "<game>" "<screen words>" [--wiki <fandom subdomain>] [--steam <appid>] [--drop <folder>] [--max 12] [--keep 1,4 --type hud|menu[:<screen>]] | <identity> --index | --tag <file>=hud|menu[:<screen>] | --waive "<the owner\'s words>"',
						'lune run kit ui refs field "a stylized RPG" "title screen menu" --wiki <fandom-wiki>'
					)
				end
				local args = { "kit/ui/refs.py", "--refs", `{Config.path("ui")}/refs` }
				for i = 2, #rawArgs do
					table.insert(args, rawArgs[i])
				end
				local step = Run.content(`ui refs {ident}`, Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or `ui refs {ident}: crashed`,
					r.next_action or "read the error above"
				)
			end
			if sub == "measure" then
				-- a reference still measured by script: colour shares, the accent field's box and top-edge slope,
				-- paper / ink masses, quadrants → <still>.layout.json + a REFS.md line. No number from the eye.
				local still = rawArgs[2]
				if type(still) ~= "string" or still == "" or string.sub(still, 1, 2) == "--" then
					return Run.report(
						rec,
						{},
						C.USAGE,
						'ui measure: <still> [--accent #hex] [--paper #hex] [--ink #hex] [--tol 90] [--parts "menu item,logo"]',
						"lune run kit ui measure assets/ui/refs/field/title_reference.png --accent #e60012"
					)
				end
				local args = { "kit/ui/measure.py" }
				for i = 2, #rawArgs do
					table.insert(args, rawArgs[i])
				end
				local step = Run.content(`ui measure {still}`, Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or `ui measure: crashed`,
					r.next_action or "read the error above"
				)
			end
			if sub == "ink" then
				-- a REAL picture (a render, key art, a photo) becomes flat ink art in the identity's cutout grammar:
				-- cut out, split into ink / mid / paper, the mid-tone as a halftone screen, TEED lines, a paper rim.
				-- kit/ui/ink.py takes the rest of the arguments as given. (A hero character comes from here, not a prompt.)
				local target = rawArgs[2]
				if type(target) ~= "string" or not string.find(target, "/", 1, true) then
					return Run.report(
						rec,
						{},
						C.USAGE,
						"ui ink: name the piece as <identity>/<name>, then --from <picture> [--mid halftone|accent|paper|ink] [--dark 0.36] [--light 0.68] [--pitch 7] [--rim 12] [--size 1400]",
						"lune run kit ui ink field/hero --from assets/ui/refs/field/hero_render.webp --mid halftone"
					)
				end
				local args = { "kit/ui/ink.py", "--art", `{Config.path("ui")}/art` }
				for i = 2, #rawArgs do
					table.insert(args, rawArgs[i])
				end
				local step = Run.content(`ui ink {target}`, Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step, Content.uiVaultStep() }, -- (the rule: everything made is saved to library/ui)
					if step.ok then C.PASS else C.CONTENT,
					r.summary or `ui ink {target}: crashed`,
					r.next_action or "read the error above"
				)
			end
			if sub == "vault" then
				-- the UI library: `ui vault` (save) | check | list | find "<words>" | get <Screen> [--as <New>] [--into <root>]
				local args = { "kit/ui/vault.py" }
				for i = 2, #rawArgs do
					table.insert(args, rawArgs[i])
				end
				table.insert(args, "--ui")
				table.insert(args, Config.path("ui"))
				table.insert(args, "--models")
				table.insert(args, Config.path("uiOut"))
				table.insert(args, "--build")
				table.insert(args, Config.build("ui"))
				local step = Run.content("ui vault", Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or "ui vault: crashed",
					r.next_action or "read the error above"
				)
			end
			if sub == "identity" then
				-- an identity DRAFT from measured references (kit ui measure every still first): palette, shares, the
				-- accent field's lean and home, the rules those numbers imply — refs/<id>/identity.from-refs.json
				local id = rawArgs[2]
				if type(id) ~= "string" or id == "" or string.sub(id, 1, 2) == "--" then
					return Run.report(
						rec,
						{},
						C.USAGE,
						"ui identity: needs an identity name",
						"lune run kit ui identity <id> --from refs   (after lune run kit ui measure on every still)"
					)
				end
				local step = Run.content(
					`ui identity {id}`,
					Run.tool("python"),
					{ "kit/ui/identity_from.py", id, "--refs", `{Config.path("ui")}/refs` }
				)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or `ui identity {id}: crashed`,
					r.next_action or "read the error above"
				)
			end
			if sub == "reel" then
				-- a screen's GAMEPLAY animation rendered (a hit, the ghost draining, a counter, a low-health pulse):
				-- assets/ui/<Screen>.reel.json keyframes -> build/ui/reels/<Screen>.gif + .reel.png (kit/ui/reel.py)
				local name = rawArgs[2]
				if type(name) ~= "string" or name == "" or string.sub(name, 1, 2) == "--" then
					return Run.report(rec, {}, C.USAGE, "ui reel: needs a screen name", "lune run kit ui reel <Screen>")
				end
				local args = {
					"kit/ui/reel.py",
					name,
					"--ui",
					Config.path("ui"),
					"--models",
					Config.path("uiOut"),
					"--out",
					Config.build("ui") .. "/reels",
				}
				local step = Run.content(`ui reel {name}`, Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step, Content.uiVaultStep() }, -- (the rule: everything made is saved to library/ui)
					if step.ok then C.PASS else C.CONTENT,
					r.summary or `ui reel {name}: crashed`,
					r.next_action or "read the error above"
				)
			end
			if sub == "icon" then
				-- ui icon: free ICONS (game-icons.net, CC BY 3.0, vetted 2026-10-14): `ui icon find "<words>"`, then
				-- `ui icon make <identity>/<piece> --icon <name> [--fill] [--ink] [--outline] [--glow]` (kit/ui/icon.py +
				-- Blender); the CC BY credit is written into the identity's PROVENANCE
				if type(rawArgs[2]) ~= "string" or type(rawArgs[3]) ~= "string" then
					return Run.report(
						rec,
						{},
						C.USAGE,
						'ui icon: find "<words>" | make <identity>/<piece> --icon <name>',
						'lune run kit ui icon find "lightning"'
					)
				end
				local args = { "kit/ui/icon.py", "--art", `{Config.path("ui")}/art` }
				for i = 2, #rawArgs do
					table.insert(args, rawArgs[i])
				end
				local step = Run.content(`ui icon {rawArgs[2]}`, Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					if rawArgs[2] == "make" then { step, Content.uiVaultStep() } else { step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or "ui icon: crashed",
					r.next_action or "read the error above"
				)
			end
			if sub == "spin" then
				-- UI MESH VISUALS: a flat piece -> a bevelled 3D mesh (gold / chrome / silver / enamel, its art on the
				-- front) turning: flipbook frames <piece>_spin_f000.. + a sprite sheet + an FBX (kit/ui/spin.py + Blender)
				local target = rawArgs[2]
				if type(target) ~= "string" or not string.find(target, "/", 1, true) then
					return Run.report(
						rec,
						{},
						C.USAGE,
						"ui spin: name the piece as <identity>/<piece> [--material gold|chrome|silver|enamel] [--frames 24] [--motion spin|sway]",
						"lune run kit ui spin witch/halo --material gold"
					)
				end
				local args = { "kit/ui/spin.py", "--art", `{Config.path("ui")}/art` }
				for i = 2, #rawArgs do
					table.insert(args, rawArgs[i])
				end
				local step = Run.content(`ui spin {target}`, Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step, Content.uiVaultStep() }, -- (the rule: everything made is saved to library/ui)
					if step.ok then C.PASS else C.CONTENT,
					r.summary or `ui spin {target}: crashed`,
					r.next_action or "read the error above"
				)
			end
			if sub == "read" then
				-- REFERENCE UNDERSTANDING: `ui read <still>` names + boxes the interface pieces of a game still (SigLIP
				-- heat map, straight-border snap, category + position -> role); `ui read rank <folder> "<what>"` orders
				-- reference candidates by what you need (kit/ui/read.py)
				if type(rawArgs[2]) ~= "string" then
					return Run.report(
						rec,
						{},
						C.USAGE,
						'ui read: a still, or rank <folder> "<what you need>"',
						"lune run kit ui read assets/ui/refs/field/field_wiki_11.jpg"
					)
				end
				local args = { "kit/ui/read.py" }
				for i = 2, #rawArgs do
					table.insert(args, rawArgs[i])
				end
				if rawArgs[2] ~= "rank" then
					-- ui read --draft: the draft lands in the active game's ui folder
					table.insert(args, "--ui")
					table.insert(args, Config.path("ui"))
				end
				local step = Run.content("ui read", Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or "ui read: crashed",
					r.next_action or "read the error above"
				)
			end
			if sub == "smear" then
				-- a SMEAR of a real picture (graphic design / animation smear frames): its own pixels dragged into a
				-- banded trail that cools to a tint, echo frames, speed lines; --split writes the figure alone (break a frame)
				local target = rawArgs[2]
				if type(target) ~= "string" or not string.find(target, "/", 1, true) then
					return Run.report(
						rec,
						{},
						C.USAGE,
						"ui smear: name the piece as <identity>/<name>, then --from <picture> [--angle 200] [--length 520] [--tint #a66cff] [--echoes 3] [--split]",
						"lune run kit ui smear field/hero_smear --from assets/ui/refs/field/hero_render.webp --split"
					)
				end
				local args = { "kit/ui/smear.py", "--art", `{Config.path("ui")}/art` }
				for i = 2, #rawArgs do
					table.insert(args, rawArgs[i])
				end
				local step = Run.content(`ui smear {target}`, Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step, Content.uiVaultStep() }, -- (the rule: everything made is saved to library/ui)
					if step.ok then C.PASS else C.CONTENT,
					r.summary or `ui smear {target}: crashed`,
					r.next_action or "read the error above"
				)
			end
			if sub == "letter" then
				-- FLAT cut lettering (a logo, a shout word): real pinned fonts, glyph cards, ink outline, a hard offset
				-- shadow, a lean — no chrome, no gradient (WordArt on a cut-paper screen). kit/ui/letter.py takes the rest.
				local target = rawArgs[2]
				if type(target) ~= "string" or not string.find(target, "/", 1, true) then
					return Run.report(
						rec,
						{},
						C.USAGE,
						"ui letter: name the piece as <identity>/<name>, then --text ... [--font bangers] [--size 360] [--fill #] [--ink #] [--outline .06] [--shadow .08] [--lean -6] [--cards] [--wobble 6]",
						'lune run kit ui letter arcade5/logo_flat --text "UMBRA" --font bangers --shadow 0.09 --lean -5'
					)
				end
				local args = { "kit/ui/letter.py", "--art", `{Config.path("ui")}/art` }
				for i = 2, #rawArgs do
					table.insert(args, rawArgs[i])
				end
				local step = Run.content(`ui letter {target}`, Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step, Content.uiVaultStep() }, -- (the rule: everything made is saved to library/ui)
					if step.ok then C.PASS else C.CONTENT,
					r.summary or `ui letter {target}: crashed`,
					r.next_action or "read the error above"
				)
			end
			if sub == "find" then
				-- the piece bank: every proven UI piece across identities and the example library, found by words,
				-- with how it was made — a new screen starts from proven art before any generator is asked
				local words = {}
				for i = 2, #rawArgs do
					if string.sub(rawArgs[i], 1, 2) ~= "--" then
						table.insert(words, rawArgs[i])
					end
				end
				if #words == 0 then
					return Run.report(
						rec,
						{},
						C.USAGE,
						"ui find: what are you looking for?",
						`lune run kit ui find "chrome logo"   (searches assets/ui/art and the kit's starter art by name, sidecar and provenance)`
					)
				end
				local args = { "kit/ui/find.py", table.concat(words, " "), "--art", `{Config.path("ui")}/art` }
				local step = Run.content("ui find", Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or "ui find: crashed",
					r.next_action or "read the error above"
				)
			end
			if sub == "gauge" then
				-- an ornate gauge HUD from one small spec: assets/ui/<Screen>.gauge.json -> assets/ui/<Screen>.json
				-- (a rendered plate, live cells over its wells from the render's anchors, an emblem, a pip row, a name)
				local name = rawArgs[2]
				if type(name) ~= "string" or name == "" or string.sub(name, 1, 2) == "--" then
					return Run.report(
						rec,
						{},
						C.USAGE,
						"ui gauge: name the screen",
						"lune run kit ui gauge ActionGaugeGear"
					)
				end
				local step = Run.content(
					`ui gauge {name}`,
					Run.tool("python"),
					{ "kit/ui/gauge.py", name, "--specs", Config.path("ui") }
				)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step, Content.uiVaultStep() }, -- (the rule: everything made is saved to library/ui)
					if step.ok then C.PASS else C.CONTENT,
					r.summary or `ui gauge {name}: crashed`,
					r.next_action or "read the error above"
				)
			end
			if sub == "ab" then
				-- v7.16 a BLIND A/B pick (kit/ui/ab.py): a local page, X / Y in a random order, the pick into the vault;
				-- the page's address must reach the owner, so the child prints straight to this terminal
				local args = { "kit/ui/ab.py" }
				for i = 2, #rawArgs do
					table.insert(args, rawArgs[i])
				end
				local ok, res = pcall(process.exec, Run.tool("python"), args, { stdio = "inherit" })
				local code = if ok then res.code else 127
				return Run.report(
					rec,
					{ Run.step("ui ab", ok and code == 0, if ok then `exit {code}` else tostring(res)) },
					if ok and code == 0 then C.PASS else C.CONTENT,
					if ok and code == 0 then "ui ab: the pick is in the vault (--tag ab)" else "ui ab: no pick recorded",
					if ok and code == 0
						then "build on the winner"
						else "lune run kit ui ab <A> <B> (screen names, or two PNGs + --name <Screen>)"
				)
			end
			if
				sub == "font"
				or sub == "motion-ref"
				or sub == "diff"
				or sub == "guide"
				or sub == "glance"
				or sub == "direct"
				or sub == "saliency"
			then
				-- v7.5 a bitmap font for any text (kit/ui/font.py), v7.6 motion measured from a clip (motionref.py),
				-- v7.7 visual regression against the owner-approved goldens (diff.py), v7.16 an identity's style-guide
				-- page (guide.py) and the five-second test packet (glance.py): every argument passes through
				local tool = ({
					font = "kit/ui/font.py",
					["motion-ref"] = "kit/ui/motionref.py",
					diff = "kit/ui/diff.py",
					guide = "kit/ui/guide.py",
					glance = "kit/ui/glance.py",
					direct = "kit/ui/direct.py", -- v8 the creative director
					-- V4 UI-X: the first look lands on the focus (UEyes / UIGaze; check / calibrate / gaze)
					saliency = "kit/ui/saliency.py",
				})[sub]
				local args = { tool }
				for i = 2, #rawArgs do
					table.insert(args, rawArgs[i])
				end
				local step = Run.content(`ui {sub}`, Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or `ui {sub}: crashed`,
					r.next_action or "read the error above"
				)
			end
			if sub == "loc" then
				-- other languages (v6.13): a pseudo-localized render + every lettered word that will not translate
				local step = Run.content("ui loc", Run.tool("python"), {
					"kit/ui/loc.py",
					tostring(rawArgs[2] or ""),
					"--models",
					Config.path("uiOut"),
					"--ui",
					Config.path("ui"),
					"--out",
					Config.build("ui"),
				})
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or "ui loc: <Screen>",
					r.next_action or "lune run kit ui loc RushHud"
				)
			end
			if sub == "hudsize" then
				-- a HUD written as game code, measured on screen against its reference (kit/lib/hudsize.luau): every
				-- <root>assets/ui/huds/*.json, or the one named (a path, or a HUD name in the active game's folder)
				local only: { string }? = nil
				local name = rawArgs[2]
				if type(name) == "string" and name ~= "" then
					local path = if string.sub(name, -5) == ".json"
						then name
						else `{Config.path("ui")}/huds/{name}.json`
					if not fs.isFile(path) then
						return Run.report(
							rec,
							{},
							C.USAGE,
							`ui hudsize: no contract at {path}`,
							"lune run kit ui hudsize [<Hud> | <contract.json>] (contracts: <root>assets/ui/huds/<Hud>.json)"
						)
					end
					only = { path }
				end
				local step = Content.uiHudSizeStep(only)
				print(step.tail)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or "ui hudsize",
					r.next_action
						or "keep the HUD at its reference size; re-measure the reference only on the owner's words"
				)
			end
			if sub == "fuzz" then
				-- a screen under EDGE DATA (v6.12): words 60% longer, numbers at 9,999,999; only what breaks is reported
				local step = Run.content("ui fuzz", Run.tool("python"), {
					"kit/ui/fuzz.py",
					tostring(rawArgs[2] or ""),
					"--models",
					Config.path("uiOut"),
					"--out",
					Config.build("ui"),
				})
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or "ui fuzz: <Screen>",
					r.next_action or "lune run kit ui fuzz SimShop"
				)
			end
			if sub == "flow" then
				-- a FLOW of screens checked and filmed as one (v6.11): assets/ui/flows/<Flow>.json
				local step = Run.content("ui flow", Run.tool("python"), {
					"kit/ui/flow.py",
					tostring(rawArgs[2] or ""),
					"--ui",
					Config.path("ui"),
					"--models",
					Config.path("uiOut"),
					"--build",
					Config.build("ui"),
				})
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or "ui flow: <Flow> (assets/ui/flows/<Flow>.json)",
					r.next_action or "lune run kit ui flow SimShopFlow"
				)
			end
			if sub == "style" then
				-- an identity as a Roblox StyleSheet (v6.10): a game's own hand-made screens wear it (Ui.link)
				local idn = rawArgs[2]
				local step = Run.content("ui style", Run.tool("python"), {
					"kit/ui/style.py",
					tostring(idn or ""),
					"--ui",
					Config.path("ui"),
					"--out",
					Config.path("uiOut") .. "/styles",
				})
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or "ui style: <identity>",
					r.next_action or "lune run kit ui style sim"
				)
			end
			if sub == "ground" then
				-- the GAME FRAME an identity's screens are judged over (v6.7): our own world's look render or a picture
				-- -> assets/ui/grounds/<identity>.png (never uploaded); the preview and the busy-ground check use it
				local args = { "kit/ui/ground.py" }
				for i = 2, #rawArgs do
					table.insert(args, rawArgs[i])
				end
				table.insert(args, "--ui")
				table.insert(args, Config.path("ui"))
				local step = Run.content("ui ground", Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or "ui ground: <identity> <picture> | <identity> --world <World> [--view eye_2]",
					r.next_action or "lune run kit ui ground riff --world BattlegroundsArena --view eye_2"
				)
			end
			if sub == "verify" then
				-- the VERIFIER (mission 03 5.7): the same piece cut from a real 1080p still and from this build's frame,
				-- side by side at one scale; a fresh model answers one difference + one edit per piece and the bugs, no
				-- score. --pairs drafts <Screen>.pairs.json from the read stills; --record <verdict.json> keeps it
				local name = rawArgs[2]
				if type(name) ~= "string" or name == "" or string.sub(name, 1, 2) == "--" then
					return Run.report(
						rec,
						{},
						C.USAGE,
						"ui verify: <Screen> [--pairs | --record <verdict.json>]",
						"lune run kit ui verify StriveDuel --pairs"
					)
				end
				local mode, verdict = "packet", nil
				for i = 3, #rawArgs do
					if rawArgs[i] == "--pairs" then
						mode = "pairs"
					elseif rawArgs[i] == "--record" then
						mode, verdict = "record", rawArgs[i + 1]
					end
				end
				local args = {
					"kit/ui/verify.py",
					mode,
					name,
					"--specs",
					Config.path("ui"),
					"--refs",
					`{Config.path("ui")}/refs`,
					"--ui",
					Config.build("ui"),
					"--models",
					Config.path("uiOut"),
					"--out",
					Config.build("judge/ui"),
				}
				if mode == "record" then
					table.insert(args, "--verdict")
					table.insert(args, verdict or "")
				end
				local step = Run.content(`ui verify {name}`, Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or `ui verify {name}: crashed`,
					r.next_action or "read the error above"
				)
			end
			if sub == "plan" or sub == "look" then
				local name = rawArgs[2]
				if type(name) ~= "string" or name == "" or string.sub(name, 1, 2) == "--" then
					return Run.report(
						rec,
						{},
						C.USAGE,
						`ui {sub}: name the screen`,
						if sub == "plan"
							then "lune run kit ui plan SimHud"
							else 'lune run kit ui look SimHud "what you saw on the sheet, what you will change"'
					)
				end
				local args
				if sub == "plan" then
					-- where this screen is in the pass (identity → art → spec → build → preview → look → judge →
					-- promote) and the next command: the hand-holder for any model
					args = {
						"kit/ui/plan.py",
						name,
						"--specs",
						Config.path("ui"),
						"--models",
						Config.path("uiOut"),
						"--ui",
						Config.build("ui"),
						"--starter",
						"kit/starter/ui",
						"--verify",
						".verify/ui.json",
					}
				else
					-- the look record: a model says what it SAW on the built sheet; the judge packet and promote refuse
					-- a build nobody looked at (the score is gameable, the eye is not)
					local note = rawArgs[3]
					local by = "unknown"
					for i = 3, #rawArgs do
						if rawArgs[i] == "--as" then
							by = rawArgs[i + 1] or by
						end
					end
					args = {
						"kit/ui/judge.py",
						"look",
						name,
						"--note",
						if type(note) == "string" then note else "",
						"--by",
						by,
						"--ui",
						Config.build("ui"),
						"--specs",
						Config.path("ui"),
						"--models",
						Config.path("uiOut"),
					}
				end
				local step = Run.content(`ui {sub}`, Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or `ui {sub}: crashed`,
					r.next_action or "read the error above"
				)
			end
			if sub == "judge" then
				local names, record = {}, nil
				local ownerScore, ownerWords = nil, nil
				local i = 2
				while i <= #rawArgs do
					local a = rawArgs[i]
					if a == "--record" then
						record = rawArgs[i + 1]
						i += 1
					elseif a == "--owner" then
						-- the OWNER's verdict: `kit ui judge <Screen> --owner 85 "genuinely impressed"` — recorded on the
						-- screen and kept as an anchor every later judge packet shows (the owner's eye outranks the rubric)
						ownerScore = rawArgs[i + 1]
						ownerWords = rawArgs[i + 2]
						i += 2
					elseif string.sub(a, 1, 2) ~= "--" then
						table.insert(names, a)
					end
					i += 1
				end
				if ownerScore then
					if #names ~= 1 or type(ownerWords) ~= "string" then
						return Run.report(
							rec,
							{},
							C.USAGE,
							"ui judge --owner: one screen, a score and the owner's words",
							'lune run kit ui judge WitchGauge --owner 85 "genuinely impressed"'
						)
					end
					local args = {
						"kit/ui/judge.py",
						"owner",
						names[1],
						"--score",
						ownerScore,
						"--words",
						ownerWords,
						"--ui",
						Config.build("ui"),
						"--specs",
						Config.path("ui"),
						"--models",
						Config.path("uiOut"),
					}
					local step = Run.content("ui judge owner", Run.tool("python"), args)
					local r = step.result or {}
					if step.ok then
						-- the ONE verdict record: the knowledge vault files the owner's verdict now (store "ui")
						Run.spawn(
							"vault sync ui",
							Run.tool("python"),
							{ "kit/scripts/vault_migrate.py", "--only", "ui" },
							true
						)
					end
					return Run.report(
						rec,
						{ step },
						if step.ok then C.PASS else C.CONTENT,
						r.summary or "ui judge --owner: crashed",
						r.next_action or "read the error above"
					)
				end
				if #names == 0 then
					return Run.report(
						rec,
						{},
						C.CONTENT,
						"ui judge: name the screen(s) to judge",
						"lune run kit ui judge RpgHud RpgTitle   (then: --record verdict.json)"
					)
				end
				local packet = Config.build("judge") .. "/ui/" .. table.concat(names, "+")
				local args = if record
					then {
						"kit/ui/judge.py",
						"record",
						"--packet",
						packet,
						"--verdict",
						record,
						"--models",
						Config.path("uiOut"),
						"--out",
						Config.path("ui"),
					}
					else {
						"kit/ui/judge.py",
						"packet",
						"--out",
						packet,
						"--ui",
						Config.build("ui"),
						"--specs",
						Config.path("ui"),
						"--models",
						Config.path("uiOut"),
						"--identities",
						Config.path("ui") .. "/identities",
						table.unpack(names),
					}
				local step =
					Run.content(if record then "ui judge record" else "ui judge packet", Run.tool("python"), args)
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or "ui judge: crashed",
					r.next_action or "read the error above"
				)
			end
			if sub == "fonts" then
				local step = Content.uiFontsStep()
				local r = step.result or {}
				return Run.report(
					rec,
					{ step },
					if step.ok then C.PASS else C.CONTENT,
					r.summary or "ui fonts: crashed",
					r.next_action or "read the error above"
				)
			end
			if sub == "identities" then
				local identities, problems = Content.uiIdentities()
				local lines = {}
				for name, id in identities do
					local plates = 0
					for _ in id.plates or {} do
						plates += 1
					end
					local refs = #(id.references or {})
					table.insert(
						lines,
						`{name}: {id.about or "(no about)"} — fonts {(id.fonts or {}).font or "?"} / {(id.fonts or {}).titleFont or "?"}, {refs} reference(s), {plates} plate override(s)`
					)
				end
				table.sort(lines)
				for _, p in problems do
					table.insert(lines, p)
				end
				print(table.concat(lines, "\n"))
				return Run.report(
					rec,
					{},
					if #problems == 0 then C.PASS else C.CONTENT,
					`{#lines - #problems} identity pack(s) in {Config.path("ui")}/identities`,
					if #problems > 0
						then problems[1]
						else 'a screen uses one with "identity": "<name>" (kit new screen X --from RpgHud)'
				)
			end
			local motion = false
			local names = {}
			for _, a in rawArgs do
				if a == "--motion" then
					motion = true
				elseif string.sub(a, 1, 2) ~= "--" then
					table.insert(names, a)
				end
			end
			for _, n in names do -- (each named screen's clock and route: kit/lib/prebuild.luau)
				local held = Content.laneHeld("ui", n)
				if held then
					return held
				end
			end
			local heldAll = Content.laneHeldAll("ui", Config.path("ui")) -- (every screen compiles, named or not)
			if heldAll then
				return heldAll
			end
			local fonts = Content.uiFontsStep()
			local art = Content.uiArtStep()
			local words = Content.uiWordsStep()
			local plates = Content.uiPlatesStep()
			local compiled, compiledNames = Content.uiCompile(true)
			local place = Config.build("place.rbxlx")
			local shown = if #names > 0 then names else compiledNames
			return Run.chain("ui", {
				function()
					return fonts
				end,
				function()
					return art
				end,
				function()
					return words
				end,
				function()
					return plates
				end,
				function()
					return compiled
				end,
				Steps.build,
				function()
					return Content.uiInspect(compiledNames, place)
				end,
				function()
					return Content.uiPreviewStep(shown, nil, nil, motion)
				end,
				function() -- what a named screen's fresh preview LOOKS like among the past pieces (kit alike: a report)
					return require("../lib/alike").previewStep("ui", shown, Config.build("ui"))
				end,
				function()
					-- the owner's rule: everything the UI pipeline makes is SAVED, packaged by part (library/ui)
					return Content.uiVaultStep()
				end,
			}, function(step)
				return if step.name == "rojo build" then C.BUILD else C.CONTENT
			end, `ui: {#compiledNames} screen(s) compiled, built, in the place, previewed in {Config.build("ui")}`)
		end
	)
end

-- ---------------------------------------------------------------- world (level blueprints)
local World = require("../lib/world")

-- -> (the step, every world's name, the worlds whose compiled model this run wrote DIFFERENTLY: the build looks at those)
function Content.worldCompile(write: boolean): (Run.Step, { string }, { string })
	local specDir, outDir = Config.path("worlds"), Config.path("worldOut")
	local names, problems, errors, drift = {}, {}, 0, {}
	local changed: { string } = {}
	if fs.isDir(specDir) then
		for _, file in fs.readDir(specDir) do
			if string.sub(file, -5) ~= ".json" then
				continue
			end
			local ok, bp = pcall(serde.decode, "json" :: any, fs.readFile(specDir .. "/" .. file))
			if not ok then
				errors += 1
				table.insert(problems, `{file}: invalid JSON`)
				continue
			end
			local model, parts, issues, extras = World.compile(bp)
			for _, issue in issues do
				if issue.severity == "error" then
					errors += 1
				end
				table.insert(problems, `[{issue.severity}] {bp.name or file}.{issue.path}: {issue.message}`)
			end
			if model and bp.name then
				local path = `{outDir}/{bp.name}.model.json`
				if write then
					Config.ensureDir(outDir)
					if not fs.isFile(path) or not sameModel(path, model) then
						table.insert(changed, bp.name)
					end
					fs.writeFile(path, serde.encode("json", model, true))
					-- the terrain MaterialVariants (MaterialService <- src/materials): written when the maps are uploaded
					local matDir = Config.root() .. "src/materials"
					local matPath = `{matDir}/{bp.name}.model.json`
					-- (a game that maps MaterialService keeps its folder: an empty Folder until the maps are uploaded)
					if (extras and extras.materials) or fs.isDir(matDir) then
						Config.ensureDir(matDir)
						fs.writeFile(
							matPath,
							serde.encode("json", (extras and extras.materials) or { ClassName = "Folder" }, true)
						)
					end
					Config.ensureDir(Config.build("worlds"))
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
					-- (terrain, objectives, zones and the player's numbers ride along for `kit world check`)
					fs.writeFile(
						Config.build("worlds") .. `/{bp.name}.json`,
						serde.encode("json", {
							name = bp.name,
							blueprint = specDir .. "/" .. file, -- (kit world check reads its design: worldcheck design_lint)
							parts = flat,
							terrain = World.terrainField(World.inSeason(bp)),
							paints = extras and extras.paints,
							ambient = World.inSeason(bp).ambient,
							objectives = bp.objectives,
							zones = bp.zones,
							player = bp.player,
							checks = bp.checks,
						})
					)
				elseif not fs.isFile(path) or not sameModel(path, model) then
					table.insert(drift, path)
				end
				table.insert(names, bp.name)
			end
		end
	end
	local next_action = nil
	if errors > 0 then
		for _, p in problems do
			if string.find(p, "^%[error%]") then
				next_action = p
				break
			end
		end
	elseif #drift > 0 then
		next_action = `{drift[1]} is out of date with its blueprint — run: lune run kit world`
	end
	return Run.step(
		if write then "world compile" else "world up to date",
		errors == 0 and #drift == 0,
		table.concat(problems, "\n"),
		{
			summary = `{#names} world(s)` .. (if #drift > 0 then `, {#drift} stale` else "") .. (if #problems > 0
				then `, {#problems} issue(s)`
				else ""),
			next_action = next_action,
		}
	),
		names,
		changed
end

function Content.worldInspect(names: { string }, place: string): Run.Step
	local roblox = require("@lune/roblox")
	local report = {}
	local ok, err = pcall(function()
		local game = roblox.deserializePlace(fs.readFile(place))
		local root = game.Workspace:FindFirstChild("KitWorld")
		for _, name in names do
			local model = root and root:FindFirstChild(name)
			if not model then
				table.insert(
					report,
					`Workspace.KitWorld.{name} missing (is {Config.path("worldOut")} mapped in the Rojo project? run kit init)`
				)
				continue
			end
			local flat = serde.decode("json", fs.readFile(Config.build("worlds") .. `/{name}.json`))
			local count = 0
			for _, d in model:GetDescendants() do
				if d:IsA("BasePart") then
					count += 1
				end
			end
			if count ~= #flat.parts then
				table.insert(report, `{name}: place has {count} parts, blueprint compiled {#flat.parts}`)
			end
		end
	end)
	local good = ok and #report == 0
	return Run.step(`world inspect {place}`, good, if ok then table.concat(report, "\n") else tostring(err), {
		summary = if good then `{#names} world(s) present with every part` else nil,
		next_action = if good then nil else (report[1] or tostring(err)),
	})
end

function Content.registerWorld(Cli: any, Steps: any)
	Cli.command(
		"3d",
		"world",
		"world [--no-look]  |  world <check|look|studio|terrain|web> ...",
		"compile assets/worlds/*.json blueprints → Workspace.KitWorld + gates + top-down map, then LOOK: a world the build changed is rendered at its stations beside its references (the last line names the folder; --no-look skips the render); the sub-commands (kit/cmd/world.luau) prove it plays and show it at eye level and in Roblox Studio's light",
		function(args)
			local WorldSub = require("./world")
			if WorldSub.has(args[1]) then
				return WorldSub.run(args)
			end
			-- (--no-look: build without rendering the changed worlds' stations; the LOOK line then says they are stale)
			local noLook = args[1] == "--no-look" and args[2] == nil
			if args[1] ~= nil and not noLook then -- a typo must not pass as "0 worlds built"
				return Run.report(
					"world",
					{},
					C.USAGE,
					`world: unknown sub-command "{args[1]}"`,
					"lune run kit world  (compile all)  |  kit world check <Name>  |  kit world look <Name>  |  kit world terrain <Name>  |  kit world web <Name>"
				)
			end
			-- the quality lock: a world made after the locks compiles only beside its real references
			local locked = require("../lib/lanelocks").world()
			if #locked > 0 then
				print(table.concat(locked, "\n"))
				return Run.report(
					"world",
					{},
					C.CONTENT,
					`world: {#locked} quality lock(s) hold a new world (references, rig sheet, layout, lessons)`,
					locked[1]
				)
			end
			-- every blueprint's clock and route (kit/lib/prebuild.luau): a blueprint new or changed since the last build
			-- starts its clock; past its budget it builds only as it was - a change to it needs the owner's words
			local held = Content.laneHeldAll("world", Config.path("worlds"))
			if held then
				return held
			end
			local compiled, names, changed = Content.worldCompile(true)
			local plan = {
				function()
					return compiled
				end,
			}
			for _, n in names do
				table.insert(plan, function()
					return Run.content(
						`map {n}`,
						Run.tool("python"),
						{ "kit/world/preview.py", Config.build("worlds") .. `/{n}.json` }
					)
				end)
			end
			table.insert(plan, Steps.build)
			table.insert(plan, function()
				return Content.worldInspect(names, Config.build("place.rbxlx"))
			end)
			-- the build's LAST step: `LOOK: <folder> - what is in it`, a line a world (kit/cmd/world.luau
			-- WorldCmd.buildLooks). A world this build changed is rendered now, its stations beside their references
			-- at full size; a look that fails never fails the build. The first line rides in the report's
			-- next_action (the last step's "look at ..."), so the build ends with it and .verify/world.json keeps it
			-- (board/plans/archive/2026-11-11-world-studio-route-plan.md, W0)
			table.insert(plan, function()
				local okLook, lines = pcall(WorldSub.buildLooks, names, changed, noLook)
				local out: { string } = if okLook
					then lines
					else { `LOOK: not made ({tostring(lines)}): lune run kit world look <Name>` }
				for _, line in out do
					Run.out(line)
				end
				return Run.step("world look", true, table.concat(out, "\n"), {
					summary = `{#out} LOOK line(s)`,
					next_action = `look at the pictures - {out[1]}`,
					look = out,
				})
			end)
			return Run.chain("world", plan, function(step)
				return if step.name == "rojo build" then C.BUILD else C.CONTENT
			end, `world: {#names} world(s) built — look at {Config.build("worlds")}/<name>.png`)
		end
	)
end

-- ---------------------------------------------------------------- animation (kit/cmd/anim.luau; `kit verify` runs the compile gate)
local AnimCmd = require("./anim")
Content.animCompile = AnimCmd.compile
Content.animInspect = AnimCmd.inspect
Content.animFixture = AnimCmd.fixtureStep

return Content

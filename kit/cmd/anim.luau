-- anim.luau — `lune run kit anim ...`: the animation discipline's commands, and the compile step `kit verify` runs
-- as a gate (Content.animCompile points here).
--   kit anim [<Name> ...]        every assets/animations/<Name>.json spec (or .blend, baked first) -> the neutral clip
--                                (build/animations/<Name>.clip.json) -> KeyframeSequences (R6 + R15), the time strip
--                                (+ gif), the motion metrics + gates, the built place checked
--   kit anim rig --probe         print the Luau that reads rigs inside Studio (run it through the Studio MCP)
--   kit anim rig --from <dump>   turn the probe's JSON into kit/anim/rigs/<rig>.json (R6, R15, a custom rig)
--   kit anim rig <rig> --blend   the Blender rig from that engine data -> build/animations/rigs/<rig>.blend
--   kit anim blend <Name>        the spec's keys (or a gait's clip, frame by frame) on the rig in Blender ->
--                                assets/animations/<Name>.blend: from then on the .blend is the source; --preview
--                                writes build/animations/<Name>.blend to look at instead (the source stays)
--   kit anim bake <Name>         assets/animations/<Name>.blend -> the clip (markers = events); `kit anim` does it too
--   kit anim import <file> --clip <Anim> --as <Name> [--loop] [--fps N]   a REAL animation (glTF/GLB/FBX/BVH: a vetted
--                                library or mocap file) retargeted onto the R15 rig (kit/anim/retarget.py) ->
--                                assets/animations/<Name>.import.json + the clip; kit anim then compiles / gates it
--   kit anim keys <Name> --from <Ref>  a finished reference's BODY as editable technique keys (.move.json) for
--                                strike.py: the animator's turning frames, the weapon arc yours to write (kit/anim/keys_from.py)
--   kit anim rearm <Name> --from <Clip>  a weapon put into a finished R6 clip: both arms on the hilt, the blade with
--                                its own momentum, Hits re-timed to the tip (kit/anim/rearm.py)
--   kit anim feel <Name> --from <Clip>  the FEEL pass on a finished body: anticipation hold, two-frame strike snap,
--                                hitstop hold, overshoot + settle, slow recovery, head lag (kit/anim/feel.py)
--   kit anim fit <Name> --to <Ref>  an R6 gait's parameters set from a reference clip's measured curves (kit/anim/fit_r6.py)
--   kit anim measure <Name> [--vs <Other>]  what the clip DOES in numbers (kit/anim/measure.py): per-joint curves over
--                                the cycle, ranges, phase relations; --vs = the distance between two clips
--   kit anim look <Name>         Blender renders the clip as a person judges it (kit/anim/look.py: shaded body,
--                                three-quarter + side, every frame) -> build/animations/<Name>.look.gif + .look.png;
--                                --rig R6; --every N (sheet step); --studio bundles the Studio LOOK probe instead
--                                (kit/anim/look_probe.luau: a live loop on a fresh humanoid in the viewport, --at
--                                x,y,z); kit anim look --stop bundles the remover
--   kit anim sheet <Name>        the move LARGE, beside its reference (kit/anim/pose_sheet.py, the studio route's A0):
--                                every key pose on the owner's rig from the player's camera, the side and above (768 px
--                                high), the blade's path through the keys and the weight over the feet drawn on them,
--                                the dossier's reference frame of each pose's phase beside it; 12-a-second strips with
--                                the hands', feet's and blade tip's paths -> build/animations/<Name>.sheet/. A build
--                                that names its moves makes it by itself and ENDS with `LOOK: <folder> ...`
--   kit anim block <Move> --sheet  BLOCKING the owner answers from a picture (kit/anim/blocking.py, the studio route's
--                                A2): the move's key poses HELD at its own timing as the pose sheet + blocking.gif
--                                (pose, hold, pose in real time) -> build/animations/<Move>.blocking/; nothing is built.
--                                --note <pose> "<his words>" keeps his words with the pose he saw (answered when that
--                                pose's own key changed); --approve "<his words>" --by owner --id <the id on the sheet
--                                he saw> = his yes to THAT blocking (stale when a pose changes); --state = where it
--                                stands (--need approved fails otherwise). A blocking older than its move takes none
--                                --check = the FINISHED clip against the poses he approved (A4, blocking.py kept): a
--                                pose a later pass moved is named with its limb; every build and kit verify run it
--                                on a move that has his yes
--   kit anim play <Name>         bundle the Studio probe (kit/anim/play_probe.luau): the engine plays the clip and
--                                reports every joint per frame; kit anim record <Name> <file> compares it to the clip
--   kit anim new <Name> --gait <kind>  procedural locomotion (walk jog run back strafe_left strafe_right idle jump
--                                fall land): assets/animations/<Name>.gait.json, generated by kit anim (kit/anim/gait.py)
--                                --rig R6: an R6-NATIVE gait (walk run sprint idle; kit/anim/gait_r6.py: pendulum legs,
--                                pumping arms, the Roblox R6 style) - what the owner judges on the owner's rig
--   kit anim new <Name> --pose   an R6 animation AUTHORED ON THE OWNER'S RIG: assets/animations/<Name>.pose.json holds
--                                key poses of the rig's controllers (body, head, arms by hand position + blade
--                                direction, IK feet on the floor, the left hand on the hilt); kit anim poses
--                                assets/rigs/R6_IK.blend with its IK legs on, bakes the parts into the clip
--                                (kit/anim/pose_r6.py, checked to 0.01 studs) and saves build/animations/<Name>.r6.blend
--   kit anim edit <Name>         that posed file -> assets/animations/<Name>.blend: edit it in Blender; from then on
--                                the .blend is the source (kit anim bakes it)
--   kit anim profile <Name> [--vs <Ref>]  the craft numbers (kit/anim/anim_profile.py): swing amplitudes, opposition / drag
--                                phases, bob, twinning, snap, the ground speed the feet do not skate at; --vs: every
--                                gap to an approved reference as a sentence
--   kit anim pose-from <Ref> --as <Name>  a finished R6 clip as editable key poses on the owner's rig (kit/anim/pose_from.py)
--   kit anim new <Name> --cycle <walk|run|sprint> [--params '{"scale": 1.1}']  a locomotion cycle rebuilt from the
--                                MEASURED key poses of an approved clip (kit/anim/cycle_r6.py; presets learned with
--                                `python kit/anim/cycle_r6.py learn <clip> --kind <k>`): legs as swing + slide (the R6
--                                knee), hands where the reference puts them, knobs for scale / timing / asymmetry / drag
--   kit anim new <Name> --strike <jab|cross|hook|uppercut>  an AUTHORED R6 strike from the judged craft rules
--                                (kit/anim/strike_r6.py; the set's guard, coil, hip lead, Hit = fastest + full reach)
--   kit anim moveset <Set>      assets/animations/movesets/<Set>.json checked as ONE thing (kit/anim/moveset.py):
--                                chain seams, guard, tempo, snaps, a contact sheet, chain previews; moves -> rig keys
--   kit anim book               the STYLE BOOK (kit/anim/book.py): every R6 clip measured with one ruler (key
--                                density, snaps, body drive, speed, snap, holds, startup / active / recovery) beside
--                                the owner's verdicts, and what separates loved from rejected, per kind
--   kit anim verdict <Name> <loved|good|ok|bad|horrible> "why"  the owner's word as data (assets/animations/verdicts.json)
--   kit anim derive <Name>      a NEW animation from loved ones' CURVES: assets/animations/<Name>.derive.json (a
--                                recipe: despike, retime, amplify, posture, shift, layer, mirror, style, blend;
--                                kit/anim/derive.py) -> editable reduced keys on the owner's rig (<Name>.pose.json)
--   kit anim snaps <Name>       single frames that jump much further than their neighbours (kit/anim/snaps.py);
--                                `kit anim pose-from <Ref> --as <Name> --despike` re-spaces them on the way to the rig
--   kit anim sil <Name> [--vs <Ref>] [--frames 8]  flat silhouettes (side + front) and hand / foot ARCS, the reference
--                                underneath at the same cycle shares (kit/anim/silhouette.py, no Blender, seconds)
--   kit anim judge <Name>        a packet for a FRESH reviewer (strip, motion grid, brief, metrics, rubric);
--                                --record <verdict.json> validates and keeps the verdict (score /100, located gaps)
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")
local task = require("@lune/task")

local Anim = require("../lib/anim")
local Config = require("../lib/config")
local JsonModel = require("../lib/jsonmodel")
local Run = require("../lib/run")
local Vault = require("../lib/vault")

local C = Run.CODES
local AnimCmd = {}

local function usage(message: string, example: string): number
	return Run.report("anim", {}, C.USAGE, message, example)
end

local function blenderArgs(script: string, extra: { string }): { string }
	local args = { "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--" }
	for _, a in extra do
		table.insert(args, a)
	end
	return args
end

local function readJson(path: string): (boolean, any)
	-- the read inside the pcall: a missing file is (false, why), never a crash (a game with no dossiers folder
	-- yet - SampleGame made active, 2026-11-01 - threw out of the dossier gate and killed kit verify)
	return pcall(function()
		return serde.decode("json", fs.readFile(path))
	end)
end

local function sha256(path: string): string
	return serde.hash("sha256", fs.readFile(path))
end

-- one hash over several files' bytes in order: a generator and the module it computes with (kit/anim/clip.py)
-- the owner's R6 rig (a Roblox Blender-Animations rig with IK legs): pose sources are posed on it, R6 looks render it
-- the R6 IK rig: PARALLAX_R6_RIG (any path), else the project's assets/rigs/R6_IK.blend (optional: the
-- procedural / FK rigs in kit/anim/rigs/ need none)
local OWNER_RIG = process.env.PARALLAX_R6_RIG or "assets/rigs/R6_IK.blend"

-- a re-armed / feel clip depends on the clip it is built from: by that clip's IDENTITY (its spec + tool hashes,
-- recorded as from_sha256 / from_tool_sha256), not its bytes - compile rewrites clip files
local function upstreamChanged(source: { [string]: any }): boolean
	local okU, up = readJson(source.from)
	if not okU or type(up) ~= "table" or type(up.source) ~= "table" then
		return true
	end
	return up.source.sha256 ~= source.from_sha256 or up.source.tool_sha256 ~= source.from_tool_sha256
end

local function sha256Of(paths: { string }): string
	local parts = {}
	for _, path in paths do
		table.insert(parts, fs.readFile(path))
	end
	return serde.hash("sha256", table.concat(parts))
end

local function clipPathOf(name: string, rigName: string?): string
	return Config.build("animations") .. (if rigName == "R6" then `/{name}.r6.clip.json` else `/{name}.clip.json`)
end

-- the motion gates on one clip (kit/anim/metrics.py): a step
local function motionStep(name: string, clipPath: string, label: string?): Run.Step
	return Run.content(label or `motion {name}`, Run.tool("python"), { "kit/anim/metrics.py", clipPath })
end

-- THE SHEET (the animation studio route's A0, kit/anim/pose_sheet.py): a move's key poses LARGE on the owner's rig
-- (the player's camera, the side, above; the blade's path through the keys and the weight over the feet drawn on
-- them), each beside its dossier's reference frame of that phase, and its motion as 12-a-second strips with the
-- hands', feet's and blade tip's paths. `kit anim sheet <Name>` makes it; a build that NAMES a move makes it by
-- itself and ends with `LOOK: <folder> ...` (AnimCmd.buildLooks), so no session builds a move and reads only its gates.
AnimCmd.BUILD_LOOKS = 4 -- how many moves ONE build renders by itself (each about 17 s); the rest are named

function AnimCmd.sheetDir(name: string): string
	return Config.build("animations") .. `/{name}.sheet`
end

-- the clip a sheet shows: the R6 fold, else the clip itself (one born on R6; an R15-only clip is refused by the plan)
local function sheetClip(name: string): string
	return if fs.isFile(clipPathOf(name, "R6")) then clipPathOf(name, "R6") else clipPathOf(name)
end

-- plan (the key poses, the strip's frames, each key's reference frame) -> the owner's rig rendered at those frames
-- (kit/anim/look_r6.py --sheet: the lane's one renderer) -> the pages + look.json
-- opts.clip + opts.dir: a clip that is not a built animation (a candidate of a round) and where its sheet goes
-- opts.move + opts.blocking: a BLOCKING's own key times and its manifest (kit/anim/blocking.py make): the sheet then
-- shows exactly its poses, how long each is held and the owner's notes on each
function AnimCmd.sheetSteps(
	name: string,
	opts: {
		dossier: string?,
		strips: boolean?,
		clip: string?,
		dir: string?,
		move: string?,
		blocking: string?,
	}?
): { () -> Run.Step }
	local dir = (opts and opts.dir) or AnimCmd.sheetDir(name)
	local clipPath = (opts and opts.clip) or sheetClip(name)
	local env = { KIT_BUILD = Config.path("build") }
	return {
		function()
			local argv = {
				"kit/anim/pose_sheet.py",
				"plan",
				name,
				"--out",
				dir,
				"--clip",
				clipPath,
				"--anims",
				Config.path("anims"),
			}
			if opts and type(opts.dossier) == "string" then
				table.insert(argv, "--dossier")
				table.insert(argv, opts.dossier)
			end
			if opts and opts.strips == false then
				table.insert(argv, "--no-strips")
			end
			if opts and type(opts.move) == "string" then
				table.insert(argv, "--move")
				table.insert(argv, opts.move)
			end
			if opts and type(opts.blocking) == "string" then
				table.insert(argv, "--blocking")
				table.insert(argv, opts.blocking)
			end
			return Run.content(`sheet plan {name}`, Run.tool("python"), argv, env)
		end,
		function()
			-- a clip posed ON the owner's rig is rendered from its own file, as kit anim look renders it
			local posedBlend: string? = nil
			local okC, c = readJson(clipPath)
			if
				okC
				and type(c) == "table"
				and type(c.source) == "table"
				and (c.source.kind == "pose" or c.source.posed == true)
				and type(c.source.blend) == "string"
				and fs.isFile(c.source.blend)
			then
				posedBlend = c.source.blend
			end
			local argv = {
				"-b",
				posedBlend or OWNER_RIG,
				"--disable-autoexec",
				"--python-exit-code",
				"2",
				"-P",
				"kit/anim/look_r6.py",
				"--",
				`{name}.r6`,
				"--clip",
				clipPath,
				"--out",
				dir,
				"--sheet",
				`{dir}/plan.json`,
			}
			if posedBlend then
				table.insert(argv, "--posed")
			end
			return Run.content(`sheet render {name}`, Run.tool("blender"), argv, env)
		end,
		function() -- (isolated python: the pages read downloaded footage)
			return Run.content(`sheet {name}`, Run.tool("python"), { "-I", "kit/anim/pose_sheet.py", "pages", dir })
		end,
	}
end

-- THE FINISHED CLIP HELD TO THE POSES THE OWNER APPROVED (the studio route's A4, kit/anim/blocking.py kept): a move
-- with a blocking record (assets/animations/blocks/<Name>.blocking.json: his notes, his yes and the poses he said it
-- to) has its built clip checked against those poses - one a later pass moved is named with its limb and how far.
-- nil = the move has no record or no built clip (every move made before the stage: nothing to hold it to)
function AnimCmd.keptStep(name: string, clipPath: string?): Run.Step?
	local anims = Config.path("anims")
	local clip = clipPath or sheetClip(name)
	if not fs.isFile(`{anims}/blocks/{name}.blocking.json`) or not fs.isFile(clip) then
		return nil
	end
	return Run.content(
		`kept {name}`,
		Run.tool("python"),
		{ "kit/anim/blocking.py", "kept", name, "--clip", clip, "--anims", anims },
		{ KIT_BUILD = Config.path("build") }
	)
end

-- THE LOCK: POSES FIRST, MOTION AFTER (the owner, 2026-11-13: every method "enforced in the terms of being used";
-- kit/anim/blocking.py lock, the studio route's A2). A move made AFTER the rule, on a route whose key poses can be shown
-- before any motion exists (a strike move's keys, a dossier built on a strike move file, a procedural sword move's
-- gesture), is not made at any build unless the owner's yes stands for its key poses as they are now. Made before the
-- rule = named in <anims>/blocks/_before_blocking.json (frozen once: kit/anim/blocking.py freeze); those moves are
-- never asked and spawn nothing, so a project builds exactly as before.
-- -> { [name]: true } of the moves made before the rule (a project with no list has none). posed = true: the
-- hand-posed files made before the lock reached THEM (_before_blocking_posed.json, 2026-11-14): each list excuses
-- its own kind only (a new move file under an old posed name is asked)
function AnimCmd.beforeBlocking(posed: boolean?): { [string]: boolean }
	local out: { [string]: boolean } = {}
	local file = if posed then "_before_blocking_posed.json" else "_before_blocking.json"
	local okB, list = readJson(Config.path("anims") .. "/blocks/" .. file)
	if okB and type(list) == "table" and type(list.moves) == "table" then
		for _, n in list.moves do
			if type(n) == "string" then
				out[n] = true
			end
		end
	end
	return out
end

-- pairs: "<Name>=move=<its .move.json>" | "<Name>=blade=<its move dossier>[=<gesture>]"
-- -> the pairs of the strike moves and dossier picks made AFTER the rule (the only ones the lock reads)
function AnimCmd.lockPairs(sources: { any }): { string }
	local out: { string } = {}
	local before, posedBefore = AnimCmd.beforeBlocking(), AnimCmd.beforeBlocking(true)
	for _, src in sources do
		if before[src.name] and (src.move or src.dossier) then
			continue
		end
		if src.move then
			table.insert(out, `{src.name}=move={src.move}`)
		elseif src.dossier then
			local okD, spec = readJson(src.dossier)
			if okD and type(spec) == "table" and type(spec.dossier) == "string" then
				table.insert(out, `{src.name}=blade={spec.dossier}`)
			end
		elseif src.pose and not src.blend and not posedBefore[src.name] then
			-- a hand-posed file: its yes is to the sheet made from the file as it was (one the owner made his own
			-- .blend of - kit anim edit - builds from that .blend: not this file's lock)
			table.insert(out, `{src.name}=pose={src.pose}`)
		end
	end
	return out
end

-- -> nil (free to be made), or the refusal { summary, next_action }
-- THE OWNER'S YES TO ONE ANIMATION STAGE through `kit approve anim <name> "<words>" --by owner --stage
-- blocking|design --id <id>` (card rpdz; the owner's V3 list, anim stage A.2): the very record the lane's own commands
-- write (kit anim block <Move> --approve / kit anim design <Set> --approve) - one record, two ways in. -> the step
AnimCmd.STAGES = { "blocking", "design" }
function AnimCmd.stageApprove(stage: string, name: string, words: string, by: string?, id: string?): Run.Step
	local argv: { string }
	if stage == "blocking" then
		argv = { "kit/anim/blocking.py", "approve", name, words }
		for _, a in { "--out", Config.build("animations") .. `/{name}.blocking`, "--anims", Config.path("anims") } do
			table.insert(argv, a)
		end
	else
		argv = { "kit/anim/set_design.py", "approve", name, words }
	end
	if by then
		table.insert(argv, "--by")
		table.insert(argv, by)
	end
	if id then
		table.insert(argv, "--id")
		table.insert(argv, id)
	end
	if stage == "design" then
		for _, a in
			{
				"--page",
				Config.build("animations") .. `/{name}.design.png`,
				"--designs",
				Config.path("anims") .. "/designs",
			}
		do
			table.insert(argv, a)
		end
	end
	return Run.content(`anim {stage} {name}`, Run.tool("python"), argv, { KIT_BUILD = Config.path("build") })
end

function AnimCmd.blockingLock(pairs: { string }): { summary: string, next_action: string }?
	if #pairs == 0 then
		return nil
	end
	local argv = { "kit/anim/blocking.py", "lock" }
	for _, p in pairs do
		table.insert(argv, p)
	end
	table.insert(argv, "--anims")
	table.insert(argv, Config.path("anims"))
	local step = Run.spawn("anim blocking lock", Run.tool("python"), argv, true)
	if step.ok then
		return nil
	end
	local r = step.result
	if type(r) == "table" and type(r.summary) == "string" then
		return { summary = r.summary, next_action = tostring(r.next_action) }
	end
	return {
		summary = `anim: STOP - the blocking lock could not be read ({step.tail}): a new move is not made on a check that crashed`,
		next_action = `python {table.concat(argv, " ")}`,
	}
end

-- THE SET FIRST, THEN ITS MOVES (the studio route's A1, kit/anim/set_design.py lock): a NEW move that a design page
-- names (assets/animations/designs/<Set>.design.json) is not made, at any build, unless the owner's yes stands for
-- that design as it is now; a new move a game's style lists in a set and no design names is not made either. A move
-- made before the rule is never asked, and a project with no designs folder and no style spawns nothing.
-- pairs: AnimCmd.lockPairs' (the moves made after the rule) -> nil, or the refusal { summary, next_action }
function AnimCmd.designLock(pairs: { string }): { summary: string, next_action: string }?
	local designs = Config.path("anims") .. "/designs"
	-- the styles that may list a move in a set: the active game's (games/<Game>/anim_style.json, where
	-- kit/anim/style_check.py reads it); with no game active, every game's (their moves live in this project's own
	-- assets/animations)
	local styles: { string } = {}
	local game = Config.game()
	if game then
		if fs.isFile(`{Config.GAMES}/{game}/anim_style.json`) then
			table.insert(styles, `{Config.GAMES}/{game}/anim_style.json`)
		end
	elseif fs.isDir(Config.GAMES) then
		for _, g in fs.readDir(Config.GAMES) do
			if fs.isFile(`{Config.GAMES}/{g}/anim_style.json`) then
				table.insert(styles, `{Config.GAMES}/{g}/anim_style.json`)
			end
		end
		table.sort(styles)
	end
	if #pairs == 0 or (not fs.isDir(designs) and #styles == 0) then
		return nil
	end
	local argv = { "kit/anim/set_design.py", "lock" }
	for _, p in pairs do
		table.insert(argv, (string.match(p, "^([^=]+)") or p))
	end
	for _, kv in { { "--designs", designs }, { "--anims", Config.path("anims") } } do
		table.insert(argv, kv[1])
		table.insert(argv, kv[2])
	end
	for _, st in styles do
		table.insert(argv, "--style")
		table.insert(argv, st)
	end
	local step = Run.spawn("anim design lock", Run.tool("python"), argv, true)
	if step.ok then
		return nil
	end
	local r = step.result
	if type(r) == "table" and type(r.summary) == "string" then
		return { summary = r.summary, next_action = tostring(r.next_action) }
	end
	return {
		summary = `anim: STOP - the design lock could not be read ({step.tail}): a new move is not made on a check that crashed`,
		next_action = `python {table.concat(argv, " ")}`,
	}
end

-- the three steps, stopped at the first that fails -> (ok, the last step's JSON verdict or the failing step's)
function AnimCmd.sheet(
	name: string,
	opts: { dossier: string?, strips: boolean?, clip: string?, dir: string? }?
): (boolean, any, { Run.Step })
	local steps: { Run.Step } = {}
	for _, make in AnimCmd.sheetSteps(name, opts) do
		local step = make()
		table.insert(steps, step)
		if not step.ok then
			return false, step.result or {}, steps
		end
	end
	return true, steps[#steps].result or {}, steps
end

-- a sheet's state against what it was made from (look.json's `inputs`: the clip, its move, its dossier, the two
-- kit files that draw it): "none" (no sheet), "stale" (an input changed or is gone), "fresh" -> (state, its LOOK line)
function AnimCmd.sheetState(name: string, dir: string?): (string, string?)
	local okL, look = readJson((dir or AnimCmd.sheetDir(name)) .. "/look.json")
	if not okL or type(look) ~= "table" or type(look.look) ~= "string" then
		return "none", nil
	end
	if type(look.inputs) ~= "table" or type(look.inputs_sha256) ~= "string" then
		return "stale", look.look
	end
	for _, path in look.inputs do
		if type(path) ~= "string" or not fs.isFile(path) then
			return "stale", look.look
		end
	end
	-- a reference frame's footage that arrived (or left) since: the sheet's reference panes are no longer true
	if type(look.reference_files) == "table" then
		for path, existed in look.reference_files do
			if type(path) == "string" and fs.isFile(path) ~= (existed == true) then
				return "stale", look.look
			end
		end
	end
	return if sha256Of(look.inputs) == look.inputs_sha256 then "fresh" else "stale", look.look
end

-- the lines an animation build ends with: `LOOK: <folder> - what is in it`, one per move. A build that NAMES its
-- moves (kit anim <Name> ..., kit anim bake <Name>) renders each one's sheet here and now (the first BUILD_LOOKS
-- whose inputs changed since their sheet); a build of every clip renders nothing (hundreds of clips: it names the
-- sheets that went stale). A sheet that fails never fails the build: its line says why. `skip`: --no-look.
function AnimCmd.buildLooks(names: { string }, named: boolean, skip: boolean?, rig: string?): { string }
	local build = Config.build("animations")
	if not fs.isFile(rig or OWNER_RIG) then
		return {
			`LOOK: {build}/ - only the box strips (<Name>.png): this project has no {rig or OWNER_RIG}, the rig a move's sheet is rendered on`,
		}
	end
	local sorted = {}
	for _, n in names do
		if string.sub(n, -4) ~= "_R15" and not table.find(sorted, n) then
			table.insert(sorted, n)
		end
	end
	table.sort(sorted)
	local lines = {}
	if not named then
		local fresh, stale = 0, {}
		for _, n in sorted do
			local state = AnimCmd.sheetState(n)
			if state == "fresh" then
				fresh += 1
			elseif state == "stale" then
				table.insert(stale, n)
			end
		end
		for i = 1, math.min(#stale, 3) do
			table.insert(
				lines,
				`LOOK: {AnimCmd.sheetDir(stale[i])}/ - {stale[i]} changed since its sheet was made: lune run kit anim sheet {stale[i]}`
			)
		end
		if #stale > 3 then
			table.insert(lines, `LOOK: {build}/ - and {#stale - 3} more move(s) changed since their sheets`)
		end
		table.insert(
			lines,
			`LOOK: {build}/ - {#sorted} clip(s) built, each with its box strip <Name>.png; {fresh} have a current sheet (<Name>.sheet/pose_sheet.png). A move you are working on: lune run kit anim sheet <Name> (or build it by name: the build then renders it)`
		)
		return lines
	end
	local rendered = 0
	for _, n in sorted do
		local dir = AnimCmd.sheetDir(n)
		local state, kept = AnimCmd.sheetState(n)
		if state == "fresh" and kept then
			table.insert(lines, `{kept} [{n}: unchanged since this sheet]`)
		elseif skip then
			local was = if state == "stale" then "from BEFORE this build" else "not made"
			table.insert(
				lines,
				`LOOK: {dir}/ - {n} was built and its sheet is {was} (--no-look): lune run kit anim sheet {n}`
			)
		elseif rendered >= AnimCmd.BUILD_LOOKS then
			table.insert(
				lines,
				`LOOK: {dir}/ - {n} is not rendered (this build rendered {AnimCmd.BUILD_LOOKS} sheets already): lune run kit anim sheet {n}`
			)
		else
			rendered += 1
			local ok, r = AnimCmd.sheet(n)
			if ok and type(r.look) == "string" then
				table.insert(lines, `{r.look} [{n}: rendered by this build]`)
			else
				table.insert(
					lines,
					`LOOK: {dir}/ - NOT rendered for {n} ({r.summary or "the sheet failed"}): lune run kit anim sheet {n}`
				)
			end
		end
	end
	if #lines == 0 then
		table.insert(lines, `LOOK: {build}/ - nothing was built that a sheet can show`)
	end
	return lines
end

-- the animations of this project: { name, spec = <json path>?, blend = <blend path>? }, by name
export type Source = {
	name: string,
	spec: string?,
	blend: string?,
	gait: string?,
	move: string?,
	import: string?,
	rearm: string?,
	feel: string?,
	pose: string?,
	warp: string?,
	dossier: string?, -- <Name>.dossier.json: built from a move dossier (+ a candidate's efforts) by proc_candidates emit
}
function AnimCmd.sources(only: { string }?): { Source }
	local dir = Config.path("anims")
	local byName: { [string]: Source } = {}
	if fs.isDir(dir) then
		for _, file in fs.readDir(dir) do
			-- a <Name>.derive.json is a RECIPE (kit anim derive writes its <Name>.pose.json, the source) and
			-- verdicts.json is the owner's verdicts (kit anim book): neither is an animation
			if
				string.match(file, "%.derive%.json$")
				or string.match(file, "%.prop%.json$")
				or file == "verdicts.json"
			then
				continue -- (a prop's file belongs in props/: never a character's animation source)
			end
			local gaitStem = string.match(file, "^(.+)%.gait%.json$")
			local moveStem = string.match(file, "^(.+)%.move%.json$")
			local importStem = string.match(file, "^(.+)%.import%.json$")
			local rearmStem = string.match(file, "^(.+)%.rearm%.json$")
			local feelStem = string.match(file, "^(.+)%.feel%.json$")
			local poseStem = string.match(file, "^(.+)%.pose%.json$")
			local warpStem = string.match(file, "^(.+)%.warp%.json$")
			local dossierStem = string.match(file, "^(.+)%.dossier%.json$")
			local stem, ext = string.match(file, "^(.+)%.(%a+)$")
			if gaitStem then
				stem, ext = gaitStem, "gait"
			elseif moveStem then
				stem, ext = moveStem, "move"
			elseif importStem then
				stem, ext = importStem, "import"
			elseif rearmStem then
				stem, ext = rearmStem, "rearm"
			elseif feelStem then
				stem, ext = feelStem, "feel"
			elseif poseStem then
				stem, ext = poseStem, "pose"
			elseif warpStem then
				stem, ext = warpStem, "warp"
			elseif dossierStem then
				stem, ext = dossierStem, "dossier"
			end
			if
				not stem
				or (ext ~= "json" and ext ~= "blend" and ext ~= "gait" and ext ~= "move" and ext ~= "import" and ext ~= "rearm" and ext ~= "feel" and ext ~= "pose" and ext ~= "warp" and ext ~= "dossier")
				or string.sub(stem, 1, 1) == "_"
			then
				continue
			end
			if only and not table.find(only, stem) then
				continue
			end
			local s = byName[stem] or { name = stem }
			byName[stem] = s
			if ext == "json" then
				s.spec = `{dir}/{file}`
			elseif ext == "gait" then
				s.gait = `{dir}/{file}`
			elseif ext == "move" then
				s.move = `{dir}/{file}`
			elseif ext == "import" then
				s.import = `{dir}/{file}`
			elseif ext == "rearm" then
				s.rearm = `{dir}/{file}`
			elseif ext == "feel" then
				s.feel = `{dir}/{file}`
			elseif ext == "pose" then
				s.pose = `{dir}/{file}`
			elseif ext == "warp" then
				s.warp = `{dir}/{file}`
			elseif ext == "dossier" then
				s.dossier = `{dir}/{file}`
			else
				s.blend = `{dir}/{file}`
			end
		end
	end
	local out = {}
	for _, s in byName do
		table.insert(out, s)
	end
	table.sort(out, function(a, b)
		-- a re-armed clip is built after the clip it is built from; a feel pass after that
		local function rank(x: Source): number
			return if x.feel then 2 elseif x.rearm or x.warp or x.dossier then 1 else 0 -- a reaction plays on a base idle
		end
		local ra, rb = rank(a), rank(b)
		if ra ~= rb then
			return ra < rb
		end
		return a.name < b.name
	end)
	return out
end

local function rigBlend(rigName: string): string
	return Config.build("animations/rigs") .. `/{string.lower(rigName)}.blend`
end

-- the rig a spec animates on: its own custom rig, else R15 (the humanoid clip namespace)
local function rigOfSpec(spec: any): string
	if type(spec) == "table" and type(spec.rig) == "string" and Anim.RIGS[spec.rig] and spec.rig ~= "R6" then
		return spec.rig
	end
	return "R15"
end

-- the Blender rig from engine data (a step; builds only when the file is missing unless force)
function AnimCmd.rigBlendStep(rigName: string, force: boolean?): () -> Run.Step
	return function()
		local out = rigBlend(rigName)
		if fs.isFile(out) and not force then
			return Run.step(`rig {rigName}`, true, "", { summary = `{out} (kept)` })
		end
		if not Anim.RIGS[rigName] then
			return Run.step(`rig {rigName}`, false, "", {
				next_action = `no rig data for {rigName}: lune run kit anim rig --probe, then --from <file>`,
			})
		end
		Config.ensureDir(Config.build("animations/rigs"))
		return Run.content(
			`rig {rigName}`,
			Run.tool("blender"),
			blenderArgs("kit/anim/rig_blender.py", { rigName, out }),
			{ KIT_BUILD = Config.path("build") }
		)
	end
end

-- bake one animation's .blend (or a spec's keys with opts.spec) into its clip; opts.save = also write the .blend
function AnimCmd.bakeStep(name: string, opts: any?): () -> Run.Step
	return function()
		local o = opts or {}
		local dir = Config.path("anims")
		local specPath = o.spec or `{dir}/{name}.json`
		local blendPath = `{dir}/{name}.blend`
		local okSpec, spec = false, nil
		if fs.isFile(specPath) then
			okSpec, spec = readJson(specPath)
		end
		local rigName = o.rig or (if okSpec then rigOfSpec(spec) else "R15")
		local rigStep = AnimCmd.rigBlendStep(rigName)()
		if not rigStep.ok then
			return rigStep
		end
		local out = o.out or (Config.build("animations") .. `/{name}.clip.json`)
		Config.ensureDir(Config.build("animations"))
		local args = { name, "--rig", rigBlend(rigName), "--out", out }
		local savePath = if type(o.save) == "string" then o.save else blendPath
		if o.clip then -- a built clip keyed frame by frame (a gait's motion as an animator's starting point)
			table.insert(args, "--clip")
			table.insert(args, o.clip)
			if o.save then
				table.insert(args, "--save")
				table.insert(args, savePath)
			end
		elseif o.spec or not fs.isFile(blendPath) then
			if not okSpec then
				return Run.step(`bake {name}`, false, "", {
					next_action = `no {blendPath} and no spec to bake from — lune run kit new anim {name}`,
				})
			end
			table.insert(args, "--spec")
			table.insert(args, specPath)
			if o.save then
				table.insert(args, "--save")
				table.insert(args, savePath)
			end
		else
			table.insert(args, "--blend")
			table.insert(args, blendPath)
		end
		return Run.content(
			`bake {name}`,
			Run.tool("blender"),
			blenderArgs("kit/anim/bake.py", args),
			{ KIT_BUILD = Config.path("build") }
		)
	end
end

-- procedural locomotion: <Name>.gait.json -> the clip (kit/anim/gait.py)
local GAIT_KIND_LIST = { "walk", "jog", "run", "back", "strafe_left", "strafe_right", "idle", "jump", "fall", "land" }
local GAIT_KINDS: { [string]: boolean } = {}
for _, kind in GAIT_KIND_LIST do
	GAIT_KINDS[kind] = true
end
-- a gait spec with "rig": "R6" is an R6-NATIVE gait (kit/anim/gait_r6.py: pendulum legs, pumping arms - the way R6
-- animations are made); without it, the human gait on R15 (kit/anim/gait.py), folded to R6 afterwards
local R6_GAIT_KINDS = { walk = true, run = true, sprint = true, idle = true }
function AnimCmd.gaitTool(gaitPath: string): string
	local ok, g = readJson(gaitPath)
	if ok and type(g) == "table" and g.rig == "R6" then
		return "kit/anim/gait_r6.py"
	end
	return "kit/anim/gait.py"
end
function AnimCmd.gaitStep(name: string, gaitPath: string): () -> Run.Step
	return function()
		Config.ensureDir(Config.build("animations"))
		local out = Config.build("animations") .. `/{name}.clip.json`
		return Run.content(
			`gait {name}`,
			Run.tool("python"),
			{ AnimCmd.gaitTool(gaitPath), gaitPath, "--out", out },
			{ KIT_BUILD = Config.path("build") }
		)
	end
end

-- a real animation: <Name>.import.json (a motion file + a clip name) -> the clip. A glTF / GLB / FBX / BVH is
-- retargeted onto R15 inside Blender (kit/anim/retarget.py); a Roblox model file (.rbxm / .rbxmx holding
-- KeyframeSequences: a community pack, a Roblox default) is read AS IT IS into an R6-native clip
-- (kit/anim/kfs_import.py through kit/anim/kfs_dump.luau) - no fold, no retarget: the reference the owner judges
local function isRobloxModel(file: string?): boolean
	local f = string.lower(tostring(file))
	-- a model file, or a Studio dump of a Creator Store model's KeyframeSequences (kit/anim/kfs_studio.luau)
	return string.match(f, "%.rbxmx?$") ~= nil
		or string.match(f, "%.rbxlx?$") ~= nil
		or string.match(f, "%.kfs%.json$") ~= nil
end
function AnimCmd.importTool(importPath: string): string
	local ok, spec = readJson(importPath)
	if ok and type(spec) == "table" and isRobloxModel(spec.file) then
		return "kit/anim/kfs_import.py"
	end
	return "kit/anim/retarget.py"
end
function AnimCmd.importStep(name: string, importPath: string): () -> Run.Step
	return function()
		Config.ensureDir(Config.build("animations"))
		local out = Config.build("animations") .. `/{name}.clip.json`
		local ok, spec = readJson(importPath)
		if ok and type(spec) == "table" and isRobloxModel(spec.file) then
			return Run.content(
				`import {name}`,
				Run.tool("python"),
				{ "kit/anim/kfs_import.py", tostring(spec.file), "--spec", importPath, "--out", out },
				{ KIT_BUILD = Config.path("build") }
			)
		end
		return Run.content(
			`import {name}`,
			Run.tool("blender"),
			blenderArgs("kit/anim/retarget.py", { importPath, "--out", out }),
			{ KIT_BUILD = Config.path("build") }
		)
	end
end

-- a weapon put into a finished R6 clip: <Name>.rearm.json ("from": <Clip>, sword, hands, lag) -> the R6 clip with
-- both arms on the hilt and the blade (kit/anim/rearm.py); built after the clip it is built from
function AnimCmd.rearmStep(name: string, rearmPath: string): () -> Run.Step
	return function()
		Config.ensureDir(Config.build("animations"))
		local out = Config.build("animations") .. `/{name}.clip.json`
		return Run.content(
			`rearm {name}`,
			Run.tool("python"),
			{ "kit/anim/rearm.py", rearmPath, "--out", out },
			{ KIT_BUILD = Config.path("build") }
		)
	end
end

-- a WARPED clip: <Name>.warp.json (a dense human-made base + displacement-map ops: time_warp, amp_scale, additive,
-- transplant) -> the R6 clip, dense frames exported Linear (kit/anim/warp.py)
-- a clip built from its MOVE DOSSIER: <Name>.dossier.json (the dossier + a candidate's efforts) -> the game clip, the same
-- builder `kit anim candidates` used (kit/anim/proc_candidates.py emit) - how a candidate becomes a game animation
function AnimCmd.dossierStep(name: string, specPath: string): () -> Run.Step
	return function()
		Config.ensureDir(Config.build("animations"))
		local out = Config.build("animations") .. `/{name}.clip.json`
		return Run.content(
			`dossier {name}`,
			Run.tool("python"),
			{ "kit/anim/proc_candidates.py", "emit", specPath, "--out", out },
			{ KIT_BUILD = Config.path("build") }
		)
	end
end

function AnimCmd.warpStep(name: string, warpPath: string): () -> Run.Step
	return function()
		Config.ensureDir(Config.build("animations"))
		local out = Config.build("animations") .. `/{name}.clip.json`
		return Run.content(
			`warp {name}`,
			Run.tool("python"),
			{ "kit/anim/warp.py", warpPath, "--out", out },
			{ KIT_BUILD = Config.path("build") }
		)
	end
end

-- an R6 animation authored on the owner's rig: <Name>.pose.json (key poses of its controllers) -> the clip, baked
-- off the evaluated rig with its IK legs on (kit/anim/pose_r6.py), + the posed rig as build/animations/<Name>.r6.blend
function AnimCmd.poseStep(name: string, posePath: string): () -> Run.Step
	return function()
		if not fs.isFile(OWNER_RIG) then
			return Run.step(`pose {name}`, false, "", {
				next_action = `no {OWNER_RIG}: the owner's R6 rig is the pose source's body (copy it there)`,
			})
		end
		Config.ensureDir(Config.build("animations"))
		local out = Config.build("animations") .. `/{name}.clip.json`
		local blend = Config.build("animations") .. `/{name}.r6.blend`
		return Run.content(`pose {name}`, Run.tool("blender"), {
			"-b",
			OWNER_RIG,
			"--disable-autoexec",
			"--python-exit-code",
			"2",
			"-P",
			"kit/anim/pose_r6.py",
			"--",
			posePath,
			"--out",
			out,
			"--save",
			blend,
		}, { KIT_BUILD = Config.path("build") })
	end
end

-- the FEEL pass: <Name>.feel.json ("from": <Clip>, anticipation, snap, hitstop, overshoot, settle, recovery, lag) ->
-- the same R6 clip retimed around its Hits (kit/anim/feel.py); built after the clip it is built from
function AnimCmd.feelStep(name: string, feelPath: string): () -> Run.Step
	return function()
		Config.ensureDir(Config.build("animations"))
		local out = Config.build("animations") .. `/{name}.clip.json`
		return Run.content(
			`feel {name}`,
			Run.tool("python"),
			{ "kit/anim/feel.py", feelPath, "--out", out },
			{ KIT_BUILD = Config.path("build") }
		)
	end
end

-- a weapon moveset clip: <Name>.move.json (technique keys) -> the R6 clip (kit/anim/strike.py)
function AnimCmd.moveStep(name: string, movePath: string): () -> Run.Step
	return function()
		Config.ensureDir(Config.build("animations"))
		local out = Config.build("animations") .. `/{name}.clip.json`
		return Run.content(
			`move {name}`,
			Run.tool("python"),
			{ "kit/anim/strike.py", movePath, "--out", out },
			{ KIT_BUILD = Config.path("build") }
		)
	end
end

-- a baked clip takes its metadata from the spec beside it (keys there are ignored: the .blend is the motion)
-- WHAT A MOVE ASKS, kept through the owner's Blender edit (the owner's V3 list, anim stage F.1; card r66z: "a pose
-- edited in Blender loses its match ask"): an edited .blend of a pose source keeps its OWN motion, timing and markers
-- (the pose file is not its spec), but the pose file's asks that are not motion - to be matched, which hands hold the
-- weapon, the slides and contacts it means, a hand on the blade, its target, its upper-body version - still hold
AnimCmd.ASKS = { "match", "hands", "slides", "contact", "on_blade", "target", "upper" }
function AnimCmd.blendAsks(clip: any, pose: any): any
	if type(pose) ~= "table" or type(clip) ~= "table" then
		return clip
	end
	for _, k in AnimCmd.ASKS do
		if pose[k] ~= nil and clip[k] == nil then
			clip[k] = pose[k]
		end
	end
	return clip
end

local function mergeMeta(clip: any, spec: any): any
	if type(spec) ~= "table" then
		return clip
	end
	for _, k in
		{
			"priority",
			"loop",
			"feel",
			"beats",
			"gate",
			"match",
			"upper",
			"finish",
			"target",
			"contact",
			"hands",
			"slides",
			"on_blade",
		}
	do
		-- a feel TIER ("medium" / {tier = ...}, kit/anim/feel_presets.json): the clip already carries its resolved
		-- numbers (strike.resolve_feel) - the game needs the numbers, never the tier's name
		local tiered = k == "feel" and (type(spec[k]) == "string" or (type(spec[k]) == "table" and spec[k].tier ~= nil))
		if spec[k] ~= nil and not (tiered and type(clip.feel) == "table") then
			clip[k] = spec[k]
		end
	end
	-- (the finish is the SOURCE's word, present or not: one taken out of the source is taken off the clip, so a
	-- clip still stamped for it is seen to be stale - kit/anim/finish.py)
	clip.finish = spec.finish
	if (clip.events == nil or #clip.events == 0) and type(spec.events) == "table" then
		clip.events = spec.events
	end
	return clip
end

-- the game cutscenes in a Cutscenes.luau text that are STALE against the clips' metadata `metas` (name -> {duration,
-- events}) and their scripts on disk: each timeline names what it was built from (sources: the script's sha256 with
-- line endings normalised, each game clip's length + events) -> one line per stale cutscene with the command to re-plan
function AnimCmd.cutscenesStale(text: string, metas: { [string]: any }): { string }
	local out = {}
	local eqs = string.match(text, "JSONDecode%(%[(=+)%[")
	local body = eqs and string.match(text, "JSONDecode%(%[" .. eqs .. "%[(.*)%]" .. eqs .. "%]%)")
	local ok, all = pcall(serde.decode, "json", body or "")
	if not ok or type(all) ~= "table" then
		return {
			"Cutscenes.luau cannot be read - re-plan every cutscene: lune run kit anim cutscene <script> --timeline",
		}
	end
	local names = {}
	for name in all do
		table.insert(names, name)
	end
	table.sort(names)
	for _, name in names do
		local src = (all[name] :: any).sources
		local script = type(src) == "table" and type(src.script) == "table" and src.script.path or nil
		local redo = `lune run kit anim cutscene {script or `assets/animations/cutscenes/{name}.json`} --timeline`
		local why: string? = nil
		if type(src) ~= "table" then
			why = "it names no sources (made before the staleness check)"
		elseif script and not fs.isFile(script) then
			why = `its script {script} is gone`
		elseif script then
			local now = serde.hash("sha256", (string.gsub(fs.readFile(script), "\r\n", "\n")))
			if now ~= src.script.sha256 then
				why = `its script {script} changed`
			end
		end
		if not why and type(src) == "table" and type(src.clips) == "table" then
			for clip, fp in src.clips do
				local m = metas[clip]
				if not m then
					why = `it plays {clip}, which the game no longer has`
					break
				end
				local evs = m.events or {}
				local same = math.abs((tonumber(m.duration) or 0) - (tonumber(fp.duration) or 0)) < 1e-3
					and #evs == #(fp.events or {})
				if same then
					for i, e in evs do
						local f = fp.events[i]
						if e.name ~= f[1] or math.abs((tonumber(e.t) or 0) - (tonumber(f[2]) or 0)) >= 1e-3 then
							same = false
							break
						end
					end
				end
				if not same then
					why = `{clip} changed since it was planned (its length or its events)`
					break
				end
			end
		end
		if why then
			table.insert(out, `Cutscenes.luau: {name} is stale - {why} - run: {redo}`)
		end
	end
	return out
end

-- every source -> build/animations/<Name>.clip.json + src/animations/<Name>.model.json (R6) + <Name>_R15.model.json
-- (write = false: only check that the models on disk match their sources — the verify gate)
-- THE MOVE-DOSSIER GATE (owner 2026-10-14: "get more data on said animation ur building"): every AUTHORED clip source
-- made after the rule needs a complete dossier - assets/animations/dossiers/<move>.json, named by the source's
-- "dossier" field or the snake_case of its name. Imports are reference data (exempt); sources older than the rule are
-- listed in dossiers/_legacy.json (frozen). -> { [source name]: why it is refused }, and for each move that passed,
-- what the loved catalogue has of its like (catalog_coverage.line: the build says an UNSUPPORTED one)
-- is this clip QUARANTINED by the active profile? (`--profile core`: Sample Game's move sets kept at the kit's root,
-- profiles.core.exclude_dossiers - the owner's card: GT stays out of the kit's gates). Its clip is still BUILT (the
-- game's Meta keeps it); only a motion-gate failure on it is said instead of stopping the bake / verify
local function quarantinedSource(src: any, excl: { [string]: boolean }): boolean
	for _, file in { src.spec, src.pose, src.move, src.gait, src.rearm, src.feel, src.warp, src.dossier } do
		local ok, data = readJson(file :: string)
		if file and ok and type(data) == "table" and type(data.dossier) == "string" then
			return excl[data.dossier] == true
		end
	end
	return excl[string.lower((string.gsub(src.name, "([%l%d])(%u)", "%1_%2")))] == true
end

function AnimCmd.quarantined(name: string): boolean
	local excl = Config.excludedDossiers()
	if next(excl) == nil then
		return false
	end
	for _, src in AnimCmd.sources({ name }) do
		return quarantinedSource(src, excl)
	end
	return false
end

function AnimCmd.dossierGate(only: { string }?): ({ [string]: string }, { [string]: string })
	local dir = Config.path("anims")
	local okL, legacyFile = readJson(`{dir}/dossiers/_legacy.json`)
	local legacy: { [string]: boolean } = {}
	if okL and type(legacyFile) == "table" and type(legacyFile.sources) == "table" then
		for _, n in legacyFile.sources do
			legacy[n] = true
		end
	end
	local pairs_: { string } = {}
	for _, src in AnimCmd.sources(only) do
		if src.import or legacy[src.name] then
			continue
		end
		local dossier: string? = nil
		for _, file in { src.spec, src.pose, src.move, src.gait, src.rearm, src.feel, src.warp, src.dossier } do
			local ok, data = readJson(file :: string)
			if file and ok and type(data) == "table" and type(data.dossier) == "string" then
				dossier = data.dossier
				break
			end
		end
		-- the same snake_case as proc_dossier.snake (a digit counts as lower case: BgM1Heavy -> bg_m1_heavy)
		local snake = string.lower((string.gsub(src.name, "([%l%d])(%u)", "%1_%2")))
		-- (a move of a dossier the active profile leaves out - `--profile core`: Sample Game's own, kept at the kit's
		--  root - is not the kit's to hold to its dossier here; its own lane's gates hold it. LIMITATIONS_FIXES_V4 Phase 0)
		if Config.excludedDossiers()[dossier or snake] then
			continue
		end
		table.insert(pairs_, `{src.name}={dossier or snake}={src.move or ""}`)
	end
	local out: { [string]: string } = {}
	local coverage: { [string]: string } = {}
	if #pairs_ == 0 then
		return out, coverage
	end
	local args = { "kit/anim/proc_dossier.py", "gate" }
	for _, p in pairs_ do
		table.insert(args, p)
	end
	local step = Run.spawn("anim dossiers", Run.tool("python"), args, true)
	if step.result and type(step.result.missing) == "table" then
		for name, why in step.result.missing do
			out[name] = tostring(why)
		end
	elseif not step.ok then
		for _, p in pairs_ do
			out[string.match(p, "^([^=]+)") :: string] = `the dossier check crashed: {step.tail}`
		end
	end
	if step.result and type(step.result.coverage) == "table" then
		for name, said in step.result.coverage do
			coverage[name] = tostring(said)
		end
	end
	return out, coverage
end

-- PROPS BUILT ON A 3D-LANE MODEL (kit anim prop <asset> --model): are their clips still made on the joints the model
-- has NOW? (kit/anim/prop_rig.py stale-all) -> the reason for each prop that is not; {} when no prop was ever built
function AnimCmd.propsStale(): { string }
	local keep = Config.build("animations") .. "/props"
	if not fs.isDir(keep) then
		return {}
	end
	local step = Run.spawn(
		"anim props",
		Run.tool("python"),
		{ "kit/anim/prop_rig.py", "stale-all", keep, Config.build("models") },
		true
	)
	if step.ok then
		return {}
	end
	local r = step.result
	if type(r) == "table" and type(r.stale) == "table" then
		return r.stale
	end
	return { `the props' check crashed: {step.tail}` }
end

-- the match tables a clip asks for (its "match"; kit/anim/match_tables.py `for`) -> the tables, or nil and why not
function AnimCmd.matchTables(name: string, clip: any): (any?, string?)
	local dir = Config.build("animations") .. "/_match"
	Config.ensureDir(dir)
	-- (files of this call's own: two sessions in one checkout build and test at the same time)
	local tag = string.format("%d_%d", math.floor(os.clock() * 1e6), math.random(1, 1e9))
	local inPath, outPath = `{dir}/{name}.{tag}.clip.json`, `{dir}/{name}.{tag}.match.json`
	fs.writeFile(inPath, serde.encode("json", clip))
	local step = Run.spawn(
		`match tables {name}`,
		Run.tool("python"),
		{ "kit/anim/match_tables.py", "for", inPath, "--out", outPath },
		true
	)
	local tables: any = nil
	if step.ok and fs.isFile(outPath) then
		local okT, decoded = pcall(serde.decode, "json" :: any, fs.readFile(outPath))
		if okT and type(decoded) == "table" then
			tables = decoded
		end
	end
	for _, p in { inPath, outPath } do
		if fs.isFile(p) then
			fs.removeFile(p)
		end
	end
	if tables then
		return tables, nil
	end
	local r = step.result
	return nil, if type(r) == "table" and type(r.summary) == "string" then r.summary else step.tail
end

-- ONE FINISHING CONTRACT FOR EVERY ROUTE (kit/anim/finish.py `apply`; the owner's limitations list 2026-11-15, A-R09):
-- a source of ANY route (a move, a keyframe spec, a gait, an import, a pose file, a bake) that says "finish" has its
-- clip finished here, at the one place every route's clip passes - filter, velocity, handles, then the checks. -> the
-- finished clip (stamped: it is never finished twice), or nil and why the finish was refused
function AnimCmd.finish(name: string, clip: any): (any?, string?)
	local dir = Config.build("animations") .. "/_finish"
	Config.ensureDir(dir)
	-- (files of this call's own: two sessions in one checkout build and test at the same time)
	local tag = string.format("%d_%d", math.floor(os.clock() * 1e6), math.random(1, 1e9))
	local inPath, outPath = `{dir}/{name}.{tag}.clip.json`, `{dir}/{name}.{tag}.finished.json`
	fs.writeFile(inPath, serde.encode("json", clip))
	local step = Run.spawn(
		`finish {name}`,
		Run.tool("python"),
		{ "kit/anim/finish.py", "apply", inPath, "--out", outPath },
		true
	)
	local done: any = nil
	if step.ok and fs.isFile(outPath) then
		local okT, decoded = pcall(serde.decode, "json" :: any, fs.readFile(outPath))
		if okT and type(decoded) == "table" and type(decoded.joints) == "table" then
			done = decoded
		end
	end
	for _, p in { inPath, outPath } do
		if fs.isFile(p) then
			fs.removeFile(p)
		end
	end
	if done then
		return done, nil
	end
	local r = step.result
	return nil, if type(r) == "table" and type(r.summary) == "string" then r.summary else step.tail
end

-- THE UPPER-BODY VERSION of a move that asks for one ("upper": true; the owner's method lists: animation masking): the
-- same R6 clip with its legs left out, named <Name>Upper - a KeyframeSequence only drives the joints it keys, so the
-- walk keeps the legs under it. The game plays it instead of the move while the character is moving
-- (src/kit/MovesRules.clipFor, called by src/kit/Moves). -> the clip, or nil and why it cannot be made
-- R6 HAS NO WAIST: both legs hang off the Torso, so a version whose Torso turns or moves would carry the walking legs
-- with it (feet walking off the line of travel, legs sunk into the floor). Such a move is refused: its upper-body
-- version would have to lose its body turn, which is a different look - the owner's call, not the build's.
AnimCmd.LEGS = { "Right Leg", "Left Leg" }
AnimCmd.UPPER_TORSO_DEG = 15 -- the most the Torso may turn from its first pose in an upper-body version
AnimCmd.UPPER_TORSO_STUDS = 0.1 -- ... and the most it may move

function AnimCmd.upperClip(clip: any): (any?, string?)
	if type(clip) ~= "table" or clip.upper ~= true then
		return nil, `"upper" is true (the move is also built legs-free), false, or left out`
	end
	if clip.rig ~= "R6" then
		return nil, `an upper-body version is made of an R6 clip (this one is {tostring(clip.rig)})`
	end
	if clip.mask == "upper" then
		return nil, `it is an upper-body move already ("mask": "upper"): it needs no second version`
	end
	local travel = 0
	for _, f in if type(clip.root) == "table" then clip.root else {} do
		travel = math.max(travel, math.sqrt((f[5] or 0) ^ 2 + (f[7] or 0) ^ 2))
	end
	if travel > 0.05 then
		return nil,
			string.format(
				"it travels %.2f studs (a root track): a move that moves the whole body cannot be played over the walk",
				travel
			)
	end
	local torso = if type(clip.joints) == "table" and type(clip.joints.Torso) == "table"
		then clip.joints.Torso.frames
		else nil
	if type(torso) == "table" and #torso > 0 then
		local f0 = torso[1]
		local turn, move = 0, 0
		for _, f in torso do
			local dot = math.abs(f[1] * f0[1] + f[2] * f0[2] + f[3] * f0[3] + f[4] * f0[4])
			turn = math.max(turn, math.deg(2 * math.acos(math.min(1, dot))))
			move = math.max(move, math.sqrt((f[5] - f0[5]) ^ 2 + (f[6] - f0[6]) ^ 2 + (f[7] - f0[7]) ^ 2))
		end
		if turn > AnimCmd.UPPER_TORSO_DEG or move > AnimCmd.UPPER_TORSO_STUDS then
			return nil,
				string.format(
					"its torso turns %.0f degrees and moves %.2f studs (at most %d and %.1f): R6 has no waist, so the walking "
						.. "legs would be carried with it",
					turn,
					move,
					AnimCmd.UPPER_TORSO_DEG,
					AnimCmd.UPPER_TORSO_STUDS
				)
		end
	end
	local joints: { [string]: any } = {}
	local dropped, kept = 0, 0
	for name, track in if type(clip.joints) == "table" then clip.joints else {} do
		if table.find(AnimCmd.LEGS, name) then
			dropped += 1
		else
			joints[name] = track
			kept += 1
		end
	end
	if dropped == 0 or kept == 0 then
		return nil, "it keys no leg (nothing to leave out) or nothing but legs (nothing left)"
	end
	local up = table.clone(clip)
	up.name = tostring(clip.name) .. "Upper"
	up.joints = joints
	up.mask = "upper"
	up.root, up.warp, up.upper, up.match, up.additive = nil, nil, nil, nil, nil
	return up, nil
end

-- A MOTION SET's database (kit/anim/match_tables.py `set`; the owner's method lists: motion matching): setPath = its
-- file ({"clips": [...]}), clipsByName = the R6 clips this build made -> the database, or nil and why not
function AnimCmd.motionDb(setPath: string, clipsByName: { [string]: any }): (any?, string?)
	local okS, spec = pcall(serde.decode, "json" :: any, fs.readFile(setPath))
	if not okS or type(spec) ~= "table" then
		return nil, `{setPath} is not valid JSON`
	end
	local dir = Config.build("animations")
		.. string.format("/_match/set_%d_%d", math.floor(os.clock() * 1e6), math.random(1, 1e9))
	Config.ensureDir(dir)
	local okW, whyW = pcall(function()
		for _, name in if type(spec.clips) == "table" then spec.clips else {} do
			local plain = type(name) == "string" and not string.find(name, "[/\\:]") and string.sub(name, 1, 1) ~= "."
			local clip = if plain then clipsByName[name] else nil
			if clip then
				fs.writeFile(`{dir}/{name}.clip.json`, serde.encode("json", clip))
			end
		end
	end)
	if not okW then
		pcall(fs.removeDir, dir)
		return nil, `a clip of the set could not be handed to the database ({tostring(whyW)})`
	end
	local outPath = `{dir}/db.json`
	local step = Run.spawn(
		"motion set",
		Run.tool("python"),
		{ "kit/anim/match_tables.py", "set", setPath, "--clips", dir, "--out", outPath },
		true
	)
	local db: any = nil
	if step.ok and fs.isFile(outPath) then
		local okD, decoded = pcall(serde.decode, "json" :: any, fs.readFile(outPath))
		if okD and type(decoded) == "table" then
			db = decoded
		end
	end
	pcall(fs.removeDir, dir)
	if db then
		return db, nil
	end
	local r = step.result
	return nil, if type(r) == "table" and type(r.summary) == "string" then r.summary else step.tail
end

-- the generated module's text for a JSON value (the form of Meta.luau: a long string the JSON never closes)
function AnimCmd.jsonModule(comment: string, value: any, pretty: boolean?): string
	local json = serde.encode("json", value, pretty == true)
	local eq = "=="
	while string.find(json, "]" .. eq .. "]", 1, true) do
		eq ..= "="
	end
	return `-- {comment}\nreturn game:GetService("HttpService"):JSONDecode([{eq}[` .. json .. `]{eq}])\n`
end

function AnimCmd.compile(write: boolean, only: { string }?): (Run.Step, { string })
	local outDir = Config.path("animOut")
	local names, problems, errors, drift = {}, {}, 0, {}
	local metas: { [string]: any } = {}
	local upperOf: { [string]: string } = {} -- <Name>Upper -> the move it is the upper-body version of
	local r6Clips: { [string]: any } = {} -- every clip of this build as its R6 version (the motion sets read them)
	local undocumented, coverage = AnimCmd.dossierGate(only)
	-- a QUARANTINED source (the active profile's exclude_dossiers: Sample Game's work kept at the kit's root) with no
	-- dossier is said, not an error: under `--profile core` GT stays out of the kit's gates (owner, 2026-11-20).
	-- It is still never built (undocumented skips it below); without a profile it stays an error
	local exclDossier = Config.excludedDossiers()
	local quarantinedByName: { [string]: boolean } = {}
	if next(exclDossier) ~= nil then
		for _, src in AnimCmd.sources(only) do
			if undocumented[src.name] and quarantinedSource(src, exclDossier) then
				quarantinedByName[src.name] = true
			end
		end
	end
	for name, why in undocumented do
		if quarantinedByName[name] then
			table.insert(
				problems,
				`[warn] {name}: no complete move dossier ({why}) — quarantined by the active profile (profiles.core.exclude_dossiers), not built`
			)
			continue
		end
		errors += 1
		table.insert(
			problems,
			`[error] {name}: no complete move dossier ({why}) — research the move first: lune run kit anim dossier new <move>`
		)
	end
	-- a move the loved catalogue has nothing like is said on its build (V3 anim stage A.2), not refused: its numbers
	-- come from its own dossier alone, which the dossier lock holds to measured evidence
	for name, said in coverage do
		if string.find(said, "UNSUPPORTED", 1, true) then
			table.insert(problems, `[warn] {name}: {said}`)
		end
	end
	-- QUARANTINED clips (the active profile's exclude_dossiers: under `--profile core`, Sample Game's move sets kept at
	-- the kit's root) keep their COMMITTED outputs - their model.json files and their Meta entry are neither rewritten
	-- nor checked here (owner 2026-11-20, a board card: "do not commit GT churn"); their clip in build/ is still baked and
	-- their motion gates still said (as warnings). Without a profile nothing is frozen.
	local frozen: { [string]: boolean } = {}
	local excl = Config.excludedDossiers()
	for _, src in AnimCmd.sources(only) do
		if undocumented[src.name] then
			continue -- never built without its research (owner 2026-10-14)
		end
		if next(excl) ~= nil and quarantinedSource(src, excl) then
			frozen[src.name] = true
			continue
		end
		local clip, issues = nil, {}
		local spec = nil
		if src.spec then
			local ok, decoded = readJson(src.spec)
			if not ok then
				errors += 1
				table.insert(problems, `[error] {src.spec}: invalid JSON`)
				continue
			end
			spec = decoded
		end
		-- (an edited .blend of a pose source keeps its OWN metadata: the pose file is not its spec)
		if
			(
				src.gait
				or src.move
				or src.import
				or src.rearm
				or src.feel
				or src.warp
				or src.dossier
				or (src.pose and not src.blend)
			) and not spec
		then
			local okG, g = readJson(
				(
						src.gait
						or src.move
						or src.import
						or src.rearm
						or src.feel
						or src.warp
						or src.dossier
						or src.pose :: string?
					) :: string
			)
			if okG and type(g) == "table" then
				spec = g
			end
		end
		if
			src.blend
			or src.gait
			or src.move
			or src.import
			or src.rearm
			or src.feel
			or src.warp
			or src.dossier
			or src.pose
		then
			-- the motion is the bake / the gait / the move / the import / the re-arm / the feel pass (kit anim runs it
			-- first); the file beside is metadata
			local clipPath = clipPathOf(src.name)
			local from = (
				src.blend
				or src.gait
				or src.move
				or src.import
				or src.rearm
				or src.feel
				or src.warp
				or src.dossier
				or src.pose
			) :: string
			if not fs.isFile(clipPath) then
				if write then
					errors += 1
					table.insert(
						problems,
						`[error] {src.name}: {from} is not generated yet — run: lune run kit anim {src.name}`
					)
				else
					table.insert(drift, clipPath)
				end
				continue
			end
			local ok, decoded = readJson(clipPath)
			if not ok or type(decoded) ~= "table" or type(decoded.joints) ~= "table" then
				errors += 1
				table.insert(
					problems,
					`[error] {src.name}: {clipPath} is not a clip — run: lune run kit anim {src.name}`
				)
				continue
			end
			-- the clip must come from THIS source file, by THIS generator, on THIS rig: their sha256s ride in the
			-- clip (a stale bake is stale; so is a clip made before the generator or the rig data changed)
			local source = if type(decoded.source) == "table" then decoded.source else {}
			local tool = if src.gait
				then AnimCmd.gaitTool(src.gait :: string)
				elseif src.move then "kit/anim/strike.py"
				elseif src.import then AnimCmd.importTool(src.import :: string)
				elseif src.rearm then "kit/anim/rearm.py"
				elseif src.feel then "kit/anim/feel.py"
				elseif src.warp then "kit/anim/warp.py"
				elseif src.dossier then "kit/anim/proc_candidates.py"
				elseif src.pose and not src.blend then "kit/anim/pose_r6.py"
				else "kit/anim/bake.py"
			local rigFile = `kit/anim/rigs/{string.lower(tostring(decoded.rig or "R15"))}.json`
			local stale = if source.sha256 ~= sha256(from)
				then `its source {from} changed`
				elseif
					source.tool_sha256 ~= sha256Of({ tool, "kit/anim/clip.py" })
				then `{tool} or kit/anim/clip.py changed`
				elseif source.rig_sha256 ~= sha256(rigFile) then `{rigFile} changed`
				elseif type(source.from) == "string" and type(source.from_sha256) == "string" and upstreamChanged(
					source
				) then `the clip it is built from ({source.from}) changed`
				elseif
					type(source.owner_rig_sha256) == "string"
					and fs.isFile(OWNER_RIG)
					and source.owner_rig_sha256 ~= sha256(OWNER_RIG)
				then `the owner's rig {OWNER_RIG} changed`
				else nil
			if stale then
				if write then
					errors += 1
					table.insert(
						problems,
						`[error] {src.name}: {clipPath} is stale ({stale}) — run: lune run kit anim`
					)
				else
					table.insert(drift, `{clipPath} ({stale})`)
				end
				continue
			end
			clip = mergeMeta(decoded, spec)
			if src.blend and src.pose and not spec then -- (the owner's edit of a posed move: its asks still hold)
				local okP, pose = readJson(src.pose :: string)
				if okP then
					clip = AnimCmd.blendAsks(clip, pose)
				end
			end
			clip.name = src.name
			if write then
				fs.writeFile(clipPath, serde.encode("json", clip, true))
			end
		elseif spec then
			if type(spec.name) == "string" and spec.name ~= src.name then
				table.insert(problems, `[warn] {src.name}: the spec says "name": "{spec.name}" — the file name wins`)
			end
			clip, issues = Anim.clipFromSpec(spec, { source = { kind = "spec", file = src.spec } })
			for _, issue in issues do
				if issue.severity == "error" then
					errors += 1
				end
				table.insert(problems, `[{issue.severity}] {src.name}.{issue.path}: {issue.message}`)
			end
			if clip then
				clip.name = src.name
				if write then
					Config.ensureDir(Config.build("animations"))
					fs.writeFile(clipPathOf(src.name), serde.encode("json", clip, true))
				end
			end
		end
		if not clip then
			continue
		end
		-- one clip -> both humanoid rigs (the R6 version is the fold of the R15 clip; a custom-rig clip -> that rig)
		local clips: { [string]: any } = { [clip.rig] = clip }
		if clip.rig == "R15" then
			local folded, foldIssues = Anim.foldToR6(clip)
			for _, issue in foldIssues do
				table.insert(problems, `[{issue.severity}] {src.name}.{issue.path} (R6): {issue.message}`)
			end
			clips.R6 = folded
			if write then
				fs.writeFile(clipPathOf(src.name, "R6"), serde.encode("json", folded, true))
			end
		end
		-- THE FINISH (AnimCmd.finish): whatever route made the clip, a source that says "finish" has it applied HERE,
		-- on the R6 clip (the curve tools read R6: a keyed or imported clip is finished as its fold), before the
		-- models and every gate read it; a finish that is refused FAILS the build
		if (clip :: any).finish == nil and (clip :: any).finished ~= nil then
			errors += 1
			table.insert(
				problems,
				`[error] {src.name}: its clip was finished for a "finish" its source no longer asks for (a finish cannot be taken back out) — run: lune run kit anim {src.name}`
			)
			continue
		end
		if (clip :: any).finish ~= nil then
			local r6c = clips.R6
			local done: any, why: string? = nil, "a finish is applied to the R6 clip, and this source has none"
			if r6c then
				done, why = AnimCmd.finish(src.name, r6c)
			end
			if done then
				clips.R6 = done
				if clip.rig == "R6" then
					clip = done
				end
				if write then
					fs.writeFile(
						clipPathOf(src.name, if clip.rig == "R6" then nil else "R6"),
						serde.encode("json", done, true)
					)
				end
			else
				errors += 1
				table.insert(problems, `[error] {src.name}: its finish ("finish") was refused - {why}`)
				continue
			end
		end
		-- a one-shot's ROOT track (it travels: a dash, a lunge) rides in the metadata so Anim moves the character
		-- (a KeyframeSequence only drives the Motor6Ds - 47 clips played their travel in place)
		local rootTrack = nil
		-- (a finished clip: its handles re-timed the root with the body - the game is given THAT root)
		local cr = (if clips.R6 and (clips.R6 :: any).finished ~= nil then clips.R6 :: any else clip :: any).root
		if clip.loop ~= true and type(cr) == "table" and #cr > 1 then
			local travel = 0 -- the FARTHEST it gets (a lunge that comes back still travels)
			for _, f in cr do
				travel = math.max(travel, math.sqrt((f[5] or 0) ^ 2 + (f[7] or 0) ^ 2))
			end
			if travel > 0.05 then
				-- compact: one "x z yaw" string per frame (the 7-number rows made Meta 252 KB instead of ~40)
				rootTrack = {}
				for _, f in cr do
					local yaw = 2 * math.atan2(f[2] or 0, f[4] or 1)
					table.insert(rootTrack, string.format("%.3f %.3f %.4f", f[5] or 0, f[7] or 0, yaw))
				end
			end
		end
		metas[src.name] = {
			speed = if type(clip.locomotion) == "table" then clip.locomotion.speed else nil,
			duration = clip.duration,
			loop = clip.loop == true,
			priority = clip.priority,
			events = clip.events,
			feel = clip.feel,
			beats = clip.beats,
			root = rootTrack,
			fps = if rootTrack then clip.fps else nil,
			-- AAA gaps v2 (src/kit/Anim): the motion-warp window (the travel scaled + turned toward a target) and
			-- the camera kick along the blade at the Hit
			warp = if rootTrack then (clip :: any).warp else nil,
			camera_kick = (clip :: any).camera_kick,
			-- an authored camera track (D9): a finisher's own shot, keys in the character's starting root space
			camera = (clip :: any).camera,
		}
		-- MATCH TABLES (kit/anim/match_tables.py `for`; the owner's method lists: pose matching, distance matching):
		-- a clip that says "match" gets the tables it names in the game's data (src/kit/Anim.play enters it by them);
		-- one it cannot give FAILS the build - the game is never handed a clip that says it can and cannot
		r6Clips[src.name] = clips.R6 or clip -- (for the motion sets, below)
		if (clip :: any).match ~= nil then
			local r6 = clips.R6 or clip
			r6.match = (clip :: any).match
			local tables, why = AnimCmd.matchTables(src.name, r6)
			if tables then
				metas[src.name].match = tables
			else
				errors += 1
				table.insert(problems, `[error] {src.name}: it asks to be matched ("match") and cannot be - {why}`)
			end
		end
		local targets = if clip.rig == "R15" then { "R6", "R15" } else { clip.rig }
		for _, target in targets do
			local model, data, more = Anim.modelFromClip(clips[target], target)
			for _, issue in more do
				if issue.severity == "error" then
					errors += 1
				end
				table.insert(problems, `[{issue.severity}] {clip.name}.{issue.path} ({target}): {issue.message}`)
			end
			if not (model and data) then
				break
			end
			-- ADDITIVE (AAA gaps v2 D3): a clip marked `additive` (true or { frame = k }) also carries its change from
			-- that base frame, so src/kit/Anim.additive can lay it over any pose
			local add = (clip :: any).additive
			if target == "R6" and add then
				local baseFrame = if type(add) == "table" then tonumber(add.frame) or 0 else 0
				metas[src.name].additive = Anim.additiveTrack(data, baseFrame)
			end
			local outName = if target == "R6" then clip.name else `{clip.name}_{target}`
			local path = `{outDir}/{outName}.model.json`
			if write then
				Config.ensureDir(outDir)
				fs.writeFile(path, serde.encode("json", model, true))
			elseif not fs.isFile(path) or not JsonModel.same(fs.readFile(path), model) then
				table.insert(drift, path)
			end
			table.insert(names, outName)
		end
		-- THE UPPER-BODY VERSION (AnimCmd.upperClip): a move that says "upper" is also built with its legs left out,
		-- and its metadata says where (Meta.<Name>.upper) so the game can pick it while the character moves; a move
		-- that asks and cannot have one FAILS the build
		if (clip :: any).upper ~= nil and (clip :: any).upper ~= false then
			local r6 = clips.R6 or clip
			r6.upper = (clip :: any).upper
			local up, why = AnimCmd.upperClip(r6)
			local upName = src.name .. "Upper"
			if up and (metas[upName] ~= nil or upperOf[upName] ~= nil) then
				up, why = nil, `another clip is named {upName}`
			end
			local model, more = nil, {}
			if up then
				model, _, more = Anim.modelFromClip(up, "R6")
				for _, issue in more do
					if issue.severity == "error" then
						model, why = nil, issue.message
					end
				end
			end
			if up and model then
				local meta = table.clone(metas[src.name])
				meta.root, meta.fps, meta.warp, meta.match, meta.additive, meta.upper = nil, nil, nil, nil, nil, nil
				-- (an authored camera is keyed where the move STARTS: over a walk the body would leave its own shot)
				meta.camera, meta.camera_kick = nil, nil
				meta.mask = "upper"
				metas[upName] = meta
				metas[src.name].upper = upName
				upperOf[upName] = src.name
				local path = `{outDir}/{upName}.model.json`
				if write then
					Config.ensureDir(outDir)
					fs.writeFile(path, serde.encode("json", model, true))
				elseif not fs.isFile(path) or not JsonModel.same(fs.readFile(path), model) then
					table.insert(drift, path)
				end
				-- (NOT one of the build's `names`: those go on to strips, motion gates and looks, each of which reads a
				-- clip file - the version has none, it is the move's own gated motion minus its legs)
			else
				errors += 1
				table.insert(
					problems,
					`[error] {src.name}: it asks for an upper-body version ("upper") and cannot have one - {why}`
				)
			end
		end
	end
	-- a clip of the build's own name that another move's upper-body version also takes
	for upName, owner in upperOf do
		for _, src in AnimCmd.sources(nil) do -- (EVERY source: a build of one move must not overwrite another clip)
			if src.name == upName then
				errors += 1
				table.insert(
					problems,
					`[error] {upName}: {owner}'s upper-body version takes this name - rename the clip`
				)
			end
		end
	end
	-- the clips' metadata for the runtime (ground speeds, durations, events, feel): one generated module
	local metaPath = `{outDir}/Meta.luau`
	-- a run over SOME clips (kit anim <Name> ...) keeps the others' entries: the module lists every compiled clip; a
	-- quarantined clip (above) keeps its committed entry, and so does its upper-body version (<Name>Upper)
	if (only or next(frozen) ~= nil) and fs.isFile(metaPath) then
		local old = fs.readFile(metaPath)
		local eqs = string.match(old, "JSONDecode%(%[(=+)%[") or "=="
		local body = string.match(old, "JSONDecode%(%[" .. eqs .. "%[(.*)%]" .. eqs .. "%]%)")
		local okOld, prev = pcall(serde.decode, "json", body or "")
		if okOld and type(prev) == "table" then
			for name, meta in prev do
				local keep = only ~= nil
					or frozen[name]
					or (
						type(meta) == "table"
						and meta.mask == "upper"
						and string.sub(name, -5) == "Upper"
						and frozen[string.sub(name, 1, -6)]
					)
				if keep and metas[name] == nil and fs.isFile(`{outDir}/{name}.model.json`) then
					metas[name] = meta
				end
			end
		end
	end
	local metaJson = serde.encode("json", metas, true)
	-- a long-string level whose closer the JSON never holds (an event value with "]==]" in it would end it early)
	local eq = "=="
	while string.find(metaJson, "]" .. eq .. "]", 1, true) do
		eq ..= "="
	end
	local metaText = "-- generated by `lune run kit anim`: every clip's metadata for the runtime (Anim.locomotion, Feel). Never edit.\n"
		.. `return game:GetService("HttpService"):JSONDecode([{eq}[`
		.. metaJson
		.. `]{eq}])\n`
	if write then
		Config.ensureDir(outDir)
		fs.writeFile(metaPath, metaText)
	elseif fs.isFile(metaPath) then
		if fs.readFile(metaPath) ~= metaText then
			table.insert(drift, metaPath)
		end
	elseif next(metas) ~= nil then
		-- (no clip and no database is not stale: the runtime reads Meta only when it is there - Anim.meta; a fresh
		-- project, and the kit's own repo, have neither)
		table.insert(drift, metaPath)
	end
	if not write and errors == 0 and #drift == 0 then
		-- the motion gates are part of the verify gate: a clip that fails them is not done
		for _, src in AnimCmd.sources(only) do
			for _, rigName in { "R15", "R6" } do
				local cp = clipPathOf(src.name, if rigName == "R6" then "R6" else nil)
				if fs.isFile(cp) then
					local step = motionStep(src.name, cp, `motion {src.name}{if rigName == "R6" then " (R6)" else ""}`)
					if not step.ok and AnimCmd.quarantined(src.name) then
						table.insert(
							problems,
							`[warn] {src.name}: quarantined by --profile {Config.profile()} - {step.result and step.result.summary or step.tail}`
						)
					elseif not step.ok then
						errors += 1
						table.insert(problems, `[error] {src.name}: {step.result and step.result.summary or step.tail}`)
					end
				end
			end
			-- ... and a clip whose blocking the owner approved must still pass through the poses he approved
			local kept = AnimCmd.keptStep(src.name)
			if kept and not kept.ok then
				errors += 1
				table.insert(problems, `[error] {src.name}: {kept.result and kept.result.summary or kept.tail}`)
			end
		end
	end
	-- MOTION SETS (assets/animations/motion/<Set>.motion.json; the owner's method lists: motion matching): each set's
	-- database goes into the game (KitAnimations.Motion, read by src/kit/Anim.motion); a set that names a clip this
	-- build did not make, or whose clips cannot share a database, FAILS the build. A run over SOME clips does not ask.
	if not only then
		local setDir = Config.path("anims") .. "/motion"
		local dbs: { [string]: any } = {}
		local any = false
		if fs.isDir(setDir) then
			local files = fs.readDir(setDir)
			table.sort(files)
			for _, f in files do
				local setName = string.match(f, "^(.+)%.motion%.json$")
				if setName then
					local db, why = AnimCmd.motionDb(`{setDir}/{f}`, r6Clips)
					if db then
						dbs[setName] = db
						any = true
					else
						errors += 1
						table.insert(problems, `[error] motion set {setName}: {why}`)
					end
				end
			end
		end
		local motionPath = `{outDir}/Motion.luau`
		if any then
			local text = AnimCmd.jsonModule(
				"generated by `lune run kit anim`: every motion set's database for the runtime (Anim.motion). Never edit.",
				dbs
			)
			if write then
				Config.ensureDir(outDir)
				fs.writeFile(motionPath, text)
			elseif not fs.isFile(motionPath) or fs.readFile(motionPath) ~= text then
				table.insert(drift, motionPath)
			end
		elseif fs.isFile(motionPath) then
			if write then
				fs.removeFile(motionPath) -- (no set is left: the game is not handed a stale database)
			else
				table.insert(drift, motionPath)
			end
		end
	end
	-- PROPS (kit anim prop <asset> --model): clips built on joints the model no longer has turn a part the wrong way
	-- or not at all - an error at every build and in the verify gate (a run over SOME clips does not ask)
	if not only then
		for _, why in AnimCmd.propsStale() do
			errors += 1
			table.insert(problems, `[error] prop {why}`)
		end
	end
	-- GAME CUTSCENES (Cutscenes.luau, kit anim cutscene --timeline): one built from a clip or a script that changed
	-- since is stale - an error in the verify gate, a warning when building (a build does not re-plan cutscenes); checked
	-- AFTER the motion gates, so a stale cutscene never hides a clip's gate failure (review 2026-10-24)
	local cutPath = `{outDir}/Cutscenes.luau`
	if fs.isFile(cutPath) then
		for _, why in AnimCmd.cutscenesStale(fs.readFile(cutPath), metas) do
			if write then
				table.insert(problems, `[warn] {why}`)
			else
				errors += 1
				table.insert(problems, `[error] {why}`)
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
		next_action = `{drift[1]} is out of date with its source — run: lune run kit anim`
	end
	return Run.step(
		if write then "anim compile" else "anim up to date",
		errors == 0 and #drift == 0,
		table.concat(problems, "\n"),
		{
			summary = `{#names} animation(s)`
				.. (if #drift > 0 then `, {#drift} stale` else "")
				.. (if #problems > 0 then `, {#problems} issue(s)` else ""),
			next_action = next_action,
		}
	),
		names
end

-- the built place holds every KeyframeSequence (ReplicatedStorage.KitAnimations.<Name>) with at least 2 keyframes
function AnimCmd.inspect(names: { string }, place: string): Run.Step
	local roblox = require("@lune/roblox")
	local missing = {}
	local ok, err = pcall(function()
		local game = roblox.deserializePlace(fs.readFile(place))
		local folder = game.ReplicatedStorage:FindFirstChild("KitAnimations")
		for _, name in names do
			local seq = folder and folder:FindFirstChild(name)
			if not seq or seq.ClassName ~= "KeyframeSequence" then
				table.insert(missing, `ReplicatedStorage.KitAnimations.{name} (run kit init so it is mapped)`)
				continue
			end
			local keys = 0
			for _, d in seq:GetDescendants() do
				if d.ClassName == "Keyframe" then
					keys += 1
				end
			end
			if keys < 2 then
				table.insert(missing, `{name}: only {keys} keyframe(s) in the place`)
			end
		end
	end)
	local good = ok and #missing == 0
	return Run.step(`anim inspect {place}`, good, if ok then table.concat(missing, "\n") else tostring(err), {
		summary = if good then `{#names} KeyframeSequence(s) present` else nil,
		next_action = if good then nil else (missing[1] or tostring(err)),
	})
end

-- a selftest fixture (kit/selftest/anim/<name>.json) compiled into build/selftest/anim and run through the motion
-- gates: the step fails for the fixture's own reason (pops / foot slide / loop seam) — `kit selftest` expects that
function AnimCmd.fixtureStep(name: string): () -> Run.Step
	return function()
		local file = `kit/selftest/anim/{name}.json`
		local ok, spec = readJson(file)
		if not ok then
			return Run.step(`anim fixture {name}`, false, `{file}: {spec}`, { next_action = `fix {file}` })
		end
		local clip, issues = Anim.clipFromSpec(spec, { source = { kind = "selftest", file = file } })
		if not clip then
			return Run.step(`anim fixture {name}`, false, issues[1] and issues[1].message or "no clip", {
				next_action = `fix {file}: {issues[1] and issues[1].message or "?"}`,
			})
		end
		local dir = Config.build("selftest/anim")
		Config.ensureDir(dir)
		local clipPath = `{dir}/{name}.clip.json`
		fs.writeFile(clipPath, serde.encode("json", clip, true))
		return Run.content(`motion {name}`, Run.tool("python"), { "kit/anim/metrics.py", clipPath })
	end
end

-- the Blender round trip for the selftest: the template's keys on the rig, baked, every key reproduced (bake.py
-- fails itself above 0.5 degrees)
function AnimCmd.roundTripStep(): () -> Run.Step
	return function()
		local dir = Config.build("selftest/anim")
		Config.ensureDir(dir)
		local spec = `{dir}/_selftest_roundtrip.json`
		fs.writeFile(spec, (string.gsub(fs.readFile("kit/templates/anim.json"), "__NAME__", "_selftest_roundtrip")))
		return AnimCmd.bakeStep("_selftest_roundtrip", { spec = spec, out = `{dir}/_selftest_roundtrip.clip.json` })()
	end
end

-- `kit anim look <Name>`: the Studio LOOK probe (kit/anim/look_probe.luau) with this clip's compiled poses inside,
-- compact (12 numbers per moved pose per keyframe): a live loop on a fresh humanoid of the rig, far from the place's
-- content, for a human to look at in the viewport -> build/animations/<Name>.look.luau
function AnimCmd.lookBundle(name: string, rigName: string, spot: { number }?): (string?, string?)
	local modelPath = `{Config.path("animOut")}/{if rigName == "R6" then name else `{name}_{rigName}`}.model.json`
	if not fs.isFile(modelPath) then
		return nil, `no {modelPath} — run: lune run kit anim {name}`
	end
	local okModel, model = readJson(modelPath)
	if not okModel or type(model) ~= "table" then
		return nil, `{modelPath} is not JSON`
	end
	local function r4(v: number): number
		return math.floor(v * 1e4 + 0.5) / 1e4
	end
	local keyframes = {}
	for _, child in model.Children or {} do
		if child.ClassName == "Keyframe" then
			table.insert(keyframes, child)
		end
	end
	table.sort(keyframes, function(x, y)
		return (x.Properties.Time or 0) < (y.Properties.Time or 0)
	end)
	local data = {
		root = nil :: string?,
		parent = {} :: { [string]: string },
		times = {} :: { number },
		poses = {} :: { [string]: { { number } } },
		loop = if model.Properties then model.Properties.Loop else true,
		priority = if model.Properties then model.Properties.Priority else "Movement",
	}
	local n = #keyframes
	local function walk(node: any, parent: string?, i: number)
		local pname = node.Name
		if parent then
			data.parent[pname] = parent
		else
			data.root = pname
		end
		local props = node.Properties or {}
		if (props.Weight or 0) > 0 and props.CFrame and props.CFrame.CFrame then
			local cf = props.CFrame.CFrame
			local row = {}
			for _, v in cf.position do
				table.insert(row, r4(v))
			end
			for _, o in cf.orientation do
				for _, v in o do
					table.insert(row, r4(v))
				end
			end
			if not data.poses[pname] then
				data.poses[pname] = table.create(n, { 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1 })
			end
			data.poses[pname][i] = row
		end
		for _, c in node.Children or {} do
			if c.ClassName == "Pose" then
				walk(c, pname, i)
			end
		end
	end
	for i, kf in keyframes do
		table.insert(data.times, r4(kf.Properties.Time or 0))
		for _, c in kf.Children or {} do
			if c.ClassName == "Pose" then
				walk(c, nil, i)
			end
		end
	end
	if not data.root or n == 0 then
		return nil, `{modelPath} holds no keyframes`
	end
	local json = serde.encode("json", data, false)
	if string.find(json, "]==]", 1, true) then
		return nil, "the pose data contains ]==] (cannot be embedded)"
	end
	local src = fs.readFile("kit/anim/look_probe.luau")
	local function set(tag: string, kitTag: string, value: string)
		local found = false
		src = string.gsub(src, `local {tag} = [^\n]* %-%- @kit:{kitTag}`, function()
			found = true
			return `local {tag} = {value} -- @kit:{kitTag}`
		end)
		assert(found, `kit/anim/look_probe.luau has no "@kit:{kitTag}" line`)
	end
	local at = spot or { -60, 0, 60 }
	set("NAME", "name", `"{name}"`)
	set("RIG", "rig", `"{rigName}"`)
	set("SPOT", "spot", `\{ {at[1]}, {at[2]}, {at[3]} \}`)
	set("DATA_JSON", "data", `[==[{json}]==]`)
	local out = Config.build("animations") .. `/{name}.look.luau`
	fs.writeFile(out, src)
	return out, nil
end

-- `kit anim play <Name>`: the Studio probe (kit/anim/play_probe.luau) with this clip's compiled model inside ->
-- build/animations/<Name>.play.luau, to run through the Studio MCP (execute_luau, Edit): the engine plays and steps
-- the animation and returns every joint's Transform per frame
function AnimCmd.playBundle(name: string, rigName: string): (string?, string?)
	local clipPath = Config.build("animations") .. `/{name}.clip.json`
	local modelPath = `{Config.path("animOut")}/{if rigName == "R6" then name else `{name}_{rigName}`}.model.json`
	if not fs.isFile(clipPath) or not fs.isFile(modelPath) then
		return nil, `no {clipPath} / {modelPath} — run: lune run kit anim {name}`
	end
	local okClip, clip = readJson(clipPath)
	if not okClip then
		return nil, `{clipPath} is not JSON`
	end
	local events = {}
	for _, ev in clip.events or {} do
		if type(ev.name) == "string" and not table.find(events, ev.name) then
			table.insert(events, ev.name)
		end
	end
	local eventsLuau = {}
	for _, e in events do
		table.insert(eventsLuau, `"{e}"`)
	end
	local okModel, decodedModel = readJson(modelPath)
	if not okModel then
		return nil, `{modelPath} is not JSON`
	end
	local model = serde.encode("json", decodedModel, false) -- one line: small, and nothing a long bracket minds
	if string.find(model, "]==]", 1, true) then
		return nil, "the model JSON contains ]==] (cannot be embedded)"
	end
	local src = fs.readFile("kit/anim/play_probe.luau")
	local function set(tag: string, kitTag: string, value: string)
		local found = false
		src = string.gsub(src, `local {tag} = [^\n]* %-%- @kit:{kitTag}`, function()
			found = true
			return `local {tag} = {value} -- @kit:{kitTag}`
		end)
		assert(found, `kit/anim/play_probe.luau has no "@kit:{kitTag}" line`)
	end
	set("NAME", "name", `"{name}"`)
	set("RIG", "rig", `"{rigName}"`)
	set("FPS", "fps", tostring(clip.fps or 30))
	set("FRAMES", "frames", tostring(#(clip.times or {})))
	set("EVENTS", "events", `\{ {table.concat(eventsLuau, ", ")} \}`)
	set("MODEL_JSON", "model", `[==[{model}]==]`)
	local out = Config.build("animations") .. `/{name}.play.luau`
	fs.writeFile(out, src)
	return out, nil
end

-- `kit anim record <Name> <file>`: what the engine played (the probe's JSON) against the clip, frame by frame:
-- every moved joint's Transform vs the clip's joint-space transform, every marker vs its event time
function AnimCmd.record(name: string, file: string): number
	local raw = string.gsub(fs.readFile(file), "^%s+", "")
	if string.sub(raw, 1, 1) == '"' then
		local okUnq, unq = pcall(serde.decode, "json" :: any, raw)
		raw = if okUnq then unq else raw
	end
	local ok, played = pcall(serde.decode, "json" :: any, raw)
	if not ok or type(played) ~= "table" or type(played.frames) ~= "table" then
		return usage("anim record: the file is not the probe's JSON", "save exactly the string execute_luau returned")
	end
	if played.error then
		return Run.report(
			`anim-play-{name}`,
			{},
			C.PLAYTEST,
			`anim play {name}: the probe failed in Studio: {played.error}`,
			"read the error; the probe needs Edit mode and an R6/R15 humanoid"
		)
	end
	local rigName = played.rig or "R15"
	local rig = Anim.RIGS[rigName]
	if not rig then
		return usage(`anim record: unknown rig {rigName}`, "lune run kit anim rig --probe")
	end
	-- an R6-NATIVE clip (a pose / an import / a dossier build) has no separate .r6 fold: its own clip is the R6 one
	local cpath = clipPathOf(name, if rigName == "R6" then "R6" else nil)
	if not fs.isFile(cpath) then
		cpath = clipPathOf(name)
	end
	local okClip, clip = false, nil
	if fs.isFile(cpath) then
		okClip, clip = readJson(cpath)
	end
	if not okClip or clip.rig ~= rigName then
		return usage(`anim record: no {rigName} clip for {name}`, `lune run kit anim {name}`)
	end
	-- the clip's expected joint-space transform per rig part per clip frame
	local sources: { [string]: { string } } = {}
	for jn in clip.joints do
		if rig.joints[jn] then
			sources[jn] = { jn }
		end
	end
	local worst, worstAt, worstPos = 0, "", 0
	local compared = 0
	for _, rec in played.frames do
		-- the clip frame at this time
		local idx = nil
		for i, t in clip.times do
			if math.abs(t - rec.t) < 1e-3 then
				idx = i
				break
			end
		end
		if not idx then
			continue
		end
		for part, names in sources do
			local m, p = { { 1, 0, 0 }, { 0, 1, 0 }, { 0, 0, 1 } }, { 0, 0, 0 }
			for _, jn in names do
				local r, q = Anim.frameValue(clip.joints[jn], idx)
				m = Anim.CF.rot(Anim.CF.mul(Anim.CF.fromRot(m), Anim.CF.fromRot(r)))
				p = { p[1] + q[1], p[2] + q[2], p[3] + q[3] }
			end
			local jt, jp = Anim.toJointM(rig.joints[part].c0, m, p)
			local got = rec.joints and rec.joints[part]
			local gotRot = if got
				then { { got[4], got[5], got[6] }, { got[7], got[8], got[9] }, { got[10], got[11], got[12] } }
				else { { 1, 0, 0 }, { 0, 1, 0 }, { 0, 0, 1 } }
			local gotPos = if got then { got[1], got[2], got[3] } else { 0, 0, 0 }
			local a = Anim.Q.angle(Anim.Q.fromMatrix(jt), Anim.Q.fromMatrix(gotRot))
			local d = math.sqrt((jp[1] - gotPos[1]) ^ 2 + (jp[2] - gotPos[2]) ^ 2 + (jp[3] - gotPos[3]) ^ 2)
			compared += 1
			if a > worst then
				worst, worstAt = a, `{part} at {string.format("%.2f", rec.t)} s`
			end
			worstPos = math.max(worstPos, d)
		end
	end
	local markerLines, markerBad = {}, false
	for _, ev in clip.events or {} do
		local hit = nil
		for _, m in played.markers or {} do
			if m.name == ev.name and (hit == nil or math.abs(m.t - ev.t) < math.abs(hit.t - ev.t)) then
				hit = m
			end
		end
		if not hit then
			markerBad = true
			table.insert(markerLines, `{ev.name} never fired`)
		else
			local delta = (hit.t - ev.t) * (clip.fps or 30)
			if math.abs(delta) > 1 then
				markerBad = true
			end
			table.insert(
				markerLines,
				`{ev.name} fired at {string.format("%.3f", hit.t)} s ({string.format("%+.1f", delta)} frames)`
			)
		end
	end
	local expected = #(clip.times or {})
	local covered = 0
	for _, rec in played.frames do
		for _, t in clip.times do
			if math.abs(t - rec.t) < 1e-3 then
				covered += 1
				break
			end
		end
	end
	local enough = covered >= math.floor(0.8 * expected)
	local good = compared > 0 and enough and worst <= 2 and worstPos <= 0.05 and not markerBad
	local summary =
		`{name} in the engine: {compared} joint-frames compared, worst {string.format("%.2f", worst)} deg ({worstAt}), {string.format(
			"%.3f",
			worstPos
		)} studs; {if #markerLines > 0 then table.concat(markerLines, "; ") else "no markers"}`
	local step = Run.step(`anim play {name}`, good, "", {
		summary = summary,
		next_action = if good
			then nil
			elseif
				compared == 0 or not enough
			then `only {covered} of {expected} clip frames were played — did the probe step at the clip's fps?`
			elseif markerBad then "a marker is off its event time by more than a frame (or never fired)"
			else "the engine's pose differs from the clip: the Pose easing words or the joint maths (kit/lib/anim.luau)",
	})
	return Run.report(
		`anim-play-{name}`,
		{ step },
		if good then C.PASS else C.PLAYTEST,
		summary,
		if good then "none — proceed" else step.result.next_action :: string
	)
end

-- `kit anim rig ...`
local function rigCommand(pos: { string }, flags: any): number
	if flags.probe then
		print(fs.readFile("kit/anim/rig_probe.luau"))
		return Run.report(
			"anim",
			{},
			C.PASS,
			"rig probe: the Luau above reads R15 + R6 (or TARGET, a custom model) inside Studio",
			'Studio MCP: execute_luau datamodel_type="Edit" code=<the Luau above>; save the string it returns to a file; then: lune run kit anim rig --from <file>'
		)
	end
	if flags.blend then
		local rigName = pos[2] or "R15"
		if not Anim.RIGS[rigName] then
			return usage(
				`anim rig: no rig data for "{rigName}" ({table.concat(Anim.rigs(), " | ")})`,
				"lune run kit anim rig r15 --blend"
			)
		end
		return Run.chain("anim", { AnimCmd.rigBlendStep(Anim.RIGS[rigName].rig, true) }, function()
			return C.CONTENT
		end, `anim rig: {rigBlend(rigName)}`)
	end
	if type(flags.from) ~= "string" then
		return usage(
			"anim rig: --probe (print the Studio Luau), --from <probe json>, or <rig> --blend",
			"lune run kit anim rig --probe"
		)
	end
	if not fs.isFile(flags.from) then
		return usage(`anim rig: no file {flags.from}`, "lune run kit anim rig --from _artifacts/anim/rig_probe.json")
	end
	local raw = string.gsub(fs.readFile(flags.from), "^%s+", "")
	if string.sub(raw, 1, 1) == '"' then -- the MCP tool may hand the JSON back wrapped in quotes
		local okUnq, unq = pcall(serde.decode, "json" :: any, raw)
		raw = if okUnq then unq else raw
	end
	local ok, dump = pcall(serde.decode, "json" :: any, raw)
	if not ok or type(dump) ~= "table" then
		return usage("anim rig: the file is not the probe's JSON", "save exactly the string execute_luau returned")
	end
	-- one rig (dump.rig) or several (r15 / r6 / custom keys)
	local rigs = {}
	if dump.rig and dump.parts then
		table.insert(rigs, dump)
	else
		for _, key in { "r6", "r15", "custom" } do
			if type(dump[key]) == "table" and dump[key].parts then
				table.insert(rigs, dump[key])
			end
		end
	end
	local written, problems = {}, {}
	local source = { probe = dump.probe or "kit anim rig --probe", date = dump.date, file = flags.from }
	for _, d in rigs do
		local rig, why = Anim.ingestRig(d, source)
		if not rig then
			table.insert(problems, `{tostring(d.rig)}: {why}`)
			continue
		end
		Config.ensureDir(Anim.RIG_DIR)
		local path = `{Anim.RIG_DIR}/{string.lower(rig.rig)}.json`
		fs.writeFile(path, serde.encode("json", rig, true))
		table.insert(written, `{rig.rig} ({#rig.order} joints, {rig.jointType}) -> {path}`)
	end
	Anim.forgetRigs()
	local good = #written > 0 and #problems == 0
	local step = Run.step("rig ingest", good, table.concat(problems, "\n"), {
		summary = if #written > 0 then table.concat(written, "; ") else "no rig in the file",
		next_action = if good
			then nil
			else (problems[1] or "the file holds no rig (r15 / r6 / custom / a single dump)"),
	})
	return Run.chain("anim", {
		function()
			return step
		end,
	}, function()
		return C.CONTENT
	end, `anim rig: {#written} rig(s) written from the engine`)
end

function AnimCmd.register(Cli: any, Steps: any)
	Cli.command(
		"3d",
		"anim",
		'anim [<Name> ...] [--no-look] | anim sheet <Name> [--dossier <move>] [--no-strips] [--clip <candidate.clip.json>] | anim timing <Name> [--clip <clip.json>] [--move <move.json> | --no-move] | anim prop <Prop> | anim match pose|distance|motion <clip.json>... --out <table> | anim design <Set> [--new --attacks <n> | --from <moves> | --approve "<the owner words>" --by owner --id <id> | --state] | anim block <Move> --sheet [--move <move.json> | --proc <dossier> [--blade <gesture>] | --clip <clip.json>] | --note <pose> "<the owner words>" | --approve "<the owner words>" --by owner --id <blocking id> | --state [--need approved] | --check [--clip <clip.json>] | anim rig --probe | --from <dump> | <rig> --blend | anim blend <Name> [--preview] | anim bake <Name> | anim look <Name> [--rig R6] [--stop] | anim measure <Name> [--vs <Other>] | anim fit <Name> --to <Reference> | anim rearm <Name> --from <Clip> | anim feel <Name> --from <Clip> | anim new <Name> --pose | anim edit <Name> | anim profile <Name> [--vs <Ref>] | anim pose-from <Ref> --as <Name> | anim new <Name> --cycle <kind> | anim derive <Name> | anim snaps <Name> | anim book | anim verdict <Name> <word> | anim moveset <Set> | anim new <Name> --strike <kind> | anim sil <Name> [--vs <Ref>] | anim keys <Name> --from <Reference> | anim play <Name> | anim record <Name> <file> | anim judge <Name> [--record <file>]',
		"compile assets/animations/*.json or *.blend → clip + KeyframeSequences (R6 + R15) + time strip + motion gates, then LOOK: a build that names its moves renders each one's sheet and its last lines name them (--no-look skips); sheet: a built move's key poses large on the owner's rig beside the dossier's reference frames + its 12-a-second strips; rig: engine rig data / the Blender rig; blend: a spec's keys or a gait's clip as an animator's .blend (--preview: into build/); bake: a .blend into the clip",
		function(args)
			local pos, flags = Cli.parse(args)
			if pos[1] == "rig" then
				return rigCommand(pos, flags)
			end
			if pos[1] == "dossier" then
				-- the MOVE DOSSIER: the research behind one animation, required before it is built (kit/anim/proc_dossier.py)
				local verb, move = pos[2], pos[3]
				if not (verb == "new" or verb == "check" or verb == "measure" or verb == "footage") or not move then
					return usage(
						"anim dossier: new <move> [--category idle|combat|locomotion|reaction|emote] | check <move> | measure <move> <Clip> | footage <move> <video.mp4|landmarks.json> [--start S --end S]",
						"lune run kit anim dossier new front_kick --category combat"
					)
				end
				if verb == "footage" then
					-- REAL FOOTAGE of the move -> its numbers (MediaPipe Pose, VETLOG 2026-10-16): the video's 33 world
					-- landmarks per frame, then every clean kick in it measured (footage_measure.py) - numbers, never poses
					local src = pos[4]
					if not src or not fs.isFile(src) then
						return usage(
							"anim dossier footage: needs a video (or a .landmarks.json) of the move - private, measure-only",
							`lune run kit anim dossier footage {move} _artifacts/footage/{move}/<clip>.mp4`
						)
					end
					local lm = src
					local steps = {}
					local isLandmarks = string.match(string.lower(src), "%.json$") ~= nil
					if isLandmarks and (flags.start ~= nil or flags["end"] ~= nil) then
						return usage(
							"anim dossier footage: --start/--end cut the VIDEO; a landmarks file is measured whole",
							`lune run kit anim dossier footage {move} <clip>.mp4 --start 12 --end 15`
						)
					end
					if not isLandmarks then
						local dir = `_artifacts/footage/{move}`
						fs.writeDir(dir)
						lm = `{dir}/{(string.match(src, "([^/\\]+)%.%w+$") or "clip")}.landmarks.json`
						local ex = { "-I", "kit/anim/footage_landmarks.py", src, lm }
						for _, key in { "start", "end" } do
							if flags[key] ~= nil then
								table.insert(ex, `--{key}`)
								table.insert(ex, tostring(flags[key]))
							end
						end
						table.insert(steps, function()
							return Run.content(`anim footage landmarks {move}`, Run.tool("python"), ex)
						end)
					end
					-- a WEAPON move (--kind swing | spin, kit/anim/footage_weapon.py): the sword hand's strokes or the
					-- body's spin rate; a kick (the default): footage_measure.py
					local kind = flags.kind
					local measureArgs = { "-I", "kit/anim/footage_measure.py", lm }
					if kind == "swing" or kind == "spin" then
						measureArgs = { "-I", "kit/anim/footage_weapon.py", lm, "--kind", kind }
					elseif kind ~= nil then
						return usage(
							"anim dossier footage: --kind is swing or spin (a weapon move); leave it out for a kick",
							`lune run kit anim dossier footage {move} <clip>.mp4 --kind swing`
						)
					end
					table.insert(steps, function()
						return Run.content(`anim footage measure {move}`, Run.tool("python"), measureArgs)
					end)
					return Run.chain("anim", steps, function()
						return C.CONTENT
					end, `anim dossier footage {move}`)
				end
				local argv = { "kit/anim/proc_dossier.py", verb, move }
				if verb == "new" and type(flags.category) == "string" then
					table.insert(argv, "--category")
					table.insert(argv, flags.category)
				elseif verb == "measure" then
					local clipName = pos[4]
					local cp = clipName and (if fs.isFile(clipName) then clipName else clipPathOf(clipName, "R6"))
					if not cp or not fs.isFile(cp) then
						return usage(
							"anim dossier measure: needs a built clip",
							`lune run kit anim dossier measure {move} <Clip>`
						)
					end
					table.insert(argv, cp)
				end
				return Run.chain("anim", {
					function()
						return Run.content(`anim dossier {verb} {move}`, Run.tool("python"), argv)
					end,
				}, function()
					return C.CONTENT
				end, `anim dossier {verb} {move}`)
			end
			if pos[1] == "compare" then
				-- the REFERENCE BESIDE THE RESULT (AAA plan #6, kit/anim/compare.py): the dossier's footage frames at its
				-- phase moments beside our look frames; isolated python (it reads downloaded footage)
				local name = pos[2]
				if not name then
					return usage("anim compare: <Name> [--dossier <move>]", "lune run kit anim compare Katana4Kiriage")
				end
				local argv = { "-I", "kit/anim/compare.py", name }
				if type(flags.dossier) == "string" then
					table.insert(argv, "--dossier")
					table.insert(argv, flags.dossier)
				end
				return Run.chain("anim", {
					function()
						return Run.content(
							`anim compare {name}`,
							Run.tool("python"),
							argv,
							{ KIT_BUILD = Config.path("build") }
						)
					end,
				}, function()
					return C.CONTENT
				end, `anim compare {name}`)
			end
			if pos[1] == "block" then
				-- the BLOCKING PASS on the owner's rig (AAA plan #1, kit/anim/block.py): a strike move's key poses only,
				-- held, as <Move>Block on R6_IK; --base saves the as-exported bake; --read turns his edits into the
				-- move's key_edits (assets/animations/blocks/<Move>.edits.json)
				local name = pos[2]
				if not name then
					return usage(
						'anim block: <Move> [--edit] [--base | --read]   |   <Move> --sheet [--clip <clip.json> | --move <move.json> | --proc <dossier> [--blade <gesture>]] [--dossier <move>]   |   <Move> --note <pose> "<the owner\'s words>"   |   <Move> --approve "<the owner\'s words>" --by owner --id <the blocking\'s id on the sheet he saw>   |   <Move> --state [--need approved]   |   <Move> --check [--clip <clip.json>]',
						"lune run kit anim block Katana4Kiriage --sheet"
					)
				end
				-- BLOCKING THE OWNER APPROVES FROM A PICTURE (the studio route's A2, kit/anim/blocking.py): --sheet = the
				-- move's key poses HELD at its own timing, on the owner's rig as the pose sheet (every pose large, how
				-- long it is held, his notes on it) + blocking.gif (pose, hold, pose in real time); --note / --approve
				-- keep HIS words with the poses he saw (a note is answered when its pose's own key changed; his yes
				-- names the blocking he saw and goes stale when any pose changes); --state says where it stands.
				-- Nothing here builds the move: no clock starts
				if flags.check then
					-- the FINISHED clip against the poses he approved (A4): the built clip, or one named (--clip)
					local clipPath: string = if type(flags.clip) == "string" then flags.clip else sheetClip(name)
					if not fs.isFile(clipPath) then
						return usage(
							`anim block --check: no built clip of {name} ({clipPath})`,
							`lune run kit anim {name}   |   lune run kit anim block {name} --check --clip <clip.json>`
						)
					end
					return Run.chain("anim", {
						function()
							return Run.content(`kept {name}`, Run.tool("python"), {
								"kit/anim/blocking.py",
								"kept",
								name,
								"--clip",
								clipPath,
								"--anims",
								Config.path("anims"),
							}, { KIT_BUILD = Config.path("build") })
						end,
					}, function()
						return C.CONTENT
					end, `anim block {name} --check`)
				end
				if flags.sheet or flags.note ~= nil or flags.approve ~= nil or flags.state then
					local dir = Config.build("animations") .. `/{name}.blocking`
					local anims = Config.path("anims")
					local env = { KIT_BUILD = Config.path("build") }
					if flags.note ~= nil or flags.approve ~= nil or flags.state then
						local argv: { string }
						if flags.note ~= nil then
							argv = { "kit/anim/blocking.py", "note", name, tostring(flags.note), pos[3] or "" }
						elseif flags.approve ~= nil then
							argv = {
								"kit/anim/blocking.py",
								"approve",
								name,
								if type(flags.approve) == "string" then flags.approve else "",
							}
						else
							argv = { "kit/anim/blocking.py", "state", name }
						end
						for _, a in { "--out", dir, "--anims", anims } do
							table.insert(argv, a)
						end
						if type(flags.by) == "string" then
							table.insert(argv, "--by")
							table.insert(argv, flags.by)
						end
						-- --id: the blocking he said yes to (the id on the sheet he saw); --need: the state a caller requires
						for _, key in { "id", "need" } do
							if type(flags[key]) == "string" then
								table.insert(argv, `--{key}`)
								table.insert(argv, flags[key])
							end
						end
						return Run.chain("anim", {
							function()
								return Run.content(`anim block {name}`, Run.tool("python"), argv, env)
							end,
						}, function()
							return C.CONTENT
						end, `anim block {name}`)
					end
					if not fs.isFile(OWNER_RIG) then
						return usage(
							`anim block --sheet: this project has no {OWNER_RIG} (the rig a blocking is shown on)`,
							"lune run kit anim block <Move>"
						)
					end
					-- where the poses come from: a clip named, a procedural weapon dossier's gesture (--proc), the
					-- move's own keys (assets/animations/<Move>.move.json, generated here: nothing is built), else
					-- the built clip's own key moments
					local source: { string }
					local posedFrom: string? = nil
					local movePath = `{anims}/{name}.move.json`
					if type(flags.clip) == "string" then
						if not fs.isFile(flags.clip) then
							return usage(
								`anim block --sheet: no clip at {flags.clip}`,
								`lune run kit anim block {name} --sheet`
							)
						end
						source = { "--clip", flags.clip }
					elseif type(flags.proc) == "string" then
						source = { "--dossier", flags.proc }
						if type(flags.blade) == "string" then -- (the gesture `kit anim candidates --blade` makes it from)
							table.insert(source, "--gesture")
							table.insert(source, flags.blade)
						end
					elseif type(flags.move) == "string" then -- (a move file elsewhere: a fixture, a draft)
						if not fs.isFile(flags.move) then
							return usage(
								`anim block --sheet: no move file at {flags.move}`,
								`lune run kit anim block {name} --sheet`
							)
						end
						source = { "--from-move", flags.move }
					elseif fs.isFile(movePath) then
						source = { "--from-move", movePath }
					elseif fs.isFile(`{anims}/{name}.pose.json`) then
						-- a HAND-POSED file: the owner's rig poses its keys (its own solver, in Blender) into the
						-- blocking's folder - never the build's clip, no clock - and the blocking holds those keys
						posedFrom = `{anims}/{name}.pose.json`
						source = { "--clip", `{dir}/posed.clip.json`, "--pose", posedFrom }
					elseif fs.isFile(sheetClip(name)) then
						source = { "--clip", sheetClip(name) }
					else
						return usage(
							`anim block --sheet: {name} has no move file ({movePath}) and no built clip`,
							`lune run kit anim block {name} --sheet --clip <clip.json>   |   --proc <dossier>`
						)
					end
					local steps: { () -> Run.Step } = {}
					if posedFrom then
						local posePath: string = posedFrom
						table.insert(steps, function()
							Config.ensureDir(dir)
							return Run.content(`blocking pose {name}`, Run.tool("blender"), {
								"-b",
								OWNER_RIG,
								"--disable-autoexec",
								"--python-exit-code",
								"2",
								"-P",
								"kit/anim/pose_r6.py",
								"--",
								posePath,
								"--out",
								`{dir}/posed.clip.json`,
							}, env)
						end)
					end
					table.insert(steps, function()
						local argv = { "kit/anim/blocking.py", "make", name, "--out", dir, "--anims", anims }
						for _, a in source do
							table.insert(argv, a)
						end
						return Run.content(`blocking {name}`, Run.tool("python"), argv, env)
					end)
					for _, make in
						AnimCmd.sheetSteps(name, {
							dossier = if type(flags.dossier) == "string"
								then flags.dossier
								elseif type(flags.proc) == "string" then flags.proc
								else nil,
							clip = `{dir}/blocking.clip.json`,
							dir = dir,
							move = `{dir}/blocking.move.json`,
							blocking = `{dir}/blocking.json`,
						})
					do
						table.insert(steps, make)
					end
					table.insert(steps, function()
						return Run.content(
							`blocking gif {name}`,
							Run.tool("python"),
							{ "kit/anim/blocking.py", "gif", dir },
							env
						)
					end)
					local code = Run.chain(
						"anim",
						steps,
						function()
							return C.CONTENT
						end,
						`anim block {name}: {dir}/pose_sheet.png (its key poses held, large) + blocking.gif (the poses at their real timing) - the owner's words on a pose: lune run kit anim block {name} --note <pose> "<his words>"; his yes names this sheet's id (--approve "<his words>" --by owner --id <id>)`
					)
					if code == C.PASS then
						local _, line = AnimCmd.sheetState(name, dir)
						Run.out(line or `LOOK: {dir}/`)
					end
					return code
				end
				local verb = if flags.read then "read" elseif flags.base then "base" else "export"
				return Run.chain("anim", {
					function()
						return Run.content(
							`anim block {name}`,
							Run.tool("python"),
							if flags.edit
								then { "kit/anim/block.py", verb, name, "--edit" }
								else { "kit/anim/block.py", verb, name },
							{ KIT_BUILD = Config.path("build") }
						)
					end,
				}, function()
					return C.CONTENT
				end, `anim block {name}`)
			end
			if pos[1] == "plan" then
				-- where ONE action stands in the route + at most five commands per stage (kit/anim/anim_plan.py)
				local name = pos[2]
				if not name then
					return usage(
						"anim plan: <Name> [--dossier <move>]",
						"lune run kit anim plan Roundhouse --dossier roundhouse_kick"
					)
				end
				local argv = { "kit/anim/anim_plan.py", name }
				if type(flags.dossier) == "string" then
					table.insert(argv, "--dossier")
					table.insert(argv, flags.dossier)
				end
				return Run.chain("anim", {
					function()
						return Run.content(`anim plan {name}`, Run.tool("python"), argv)
					end,
				}, function()
					return C.CONTENT
				end, `anim plan {name}`)
			end
			if pos[1] == "picks" then
				-- the PICK SHEET of a candidate round: real-time gifs on the owner's rig (three-quarter + game camera,
				-- the fidelity line), the dossier's cues beside them, hotkeys to pick 1-2 (kit/anim/proc_picks.py)
				local name = pos[2]
				if not name then
					return usage("anim picks: <Name> [--round K]", "lune run kit anim picks Roundhouse --round 0")
				end
				local argv = { "kit/anim/proc_picks.py", name }
				if flags.round ~= nil then
					table.insert(argv, "--round")
					table.insert(argv, tostring(flags.round))
				end
				-- --no-loved: no loved clip beside the cards (ruling 3: loved clips calibrate, they are never a design
				-- source - the governor's re-plan 2026-11-05)
				if flags["no-loved"] ~= nil then
					table.insert(argv, "--no-loved")
				end
				-- then each candidate's kit warnings go ON the sheet, under its card (2026-11-08: on 11-04 every shown
				-- candidate carried "below the loved range" warnings on the limbs the owner then rejected, and nobody saw them)
				local warnArgv = { "kit/anim/pick_warnings.py", name }
				if flags.round ~= nil then
					table.insert(warnArgv, "--round")
					table.insert(warnArgv, tostring(flags.round))
				end
				local picked: Run.Step? = nil
				local pickCode = Run.chain("anim", {
					function()
						local step = Run.content(`anim picks {name}`, Run.tool("python"), argv)
						picked = step
						return step
					end,
					function()
						return Run.content(
							`anim picks {name}: the kit's warnings on the sheet`,
							Run.tool("python"),
							warnArgv
						)
					end,
					function() -- each candidate against the owner's own loved and rejected pieces, by look (a report)
						return require("../lib/alike").roundStep(
							name,
							if flags.round ~= nil then tostring(flags.round) else nil
						)
					end,
					function() -- the lane's taste model orders the round (off until it agrees with the owner enough)
						return require("../lib/alike").tasteStep(
							"anim",
							name,
							if flags.round ~= nil then tostring(flags.round) else nil
						)
					end,
				}, function()
					return C.CONTENT
				end, `anim picks {name}`)
				local pickLook = picked and picked.result and picked.result.look
				if pickCode == C.PASS and type(pickLook) == "string" then
					Run.out(pickLook)
				end
				return pickCode
			end
			if pos[1] == "direction" then
				-- CREATIVE DIRECTION before an original animation (the owner, 2026-10-24: the craft is fine, the
				-- direction is the gap): kit/direction.py --lane anim -> assets/animations/direction/<Piece>.md; frames
				-- are key-pose sheets on the owner's rig; draft -> ready (show him the frames) -> picked
				local name = pos[2]
				if not name then
					return usage(
						"anim direction: <Piece> [--new | --frames]",
						"lune run kit anim direction KatanaIaigiri --new"
					)
				end
				-- --frames: render the options' concept key poses (direction/poses/<Piece><Letter>.pose.json) on the
				-- owner's rig into the doc's Frame pictures (kit/anim/direction_frames.py)
				local argv = if flags.frames == true
					then { "kit/anim/direction_frames.py", name }
					else {
						"kit/direction.py",
						if flags.new == true then "new" else "check",
						`assets/animations/direction/{name}.md`,
						"--lane",
						"anim",
						"--name",
						name,
					}
				return Run.chain("anim", {
					function()
						return Run.content(`anim direction {name}`, Run.tool("python"), argv)
					end,
				}, function()
					return C.CONTENT
				end, `anim direction {name}`)
			end
			if pos[1] == "calibrate" then
				-- a dossier's ranges taught by the OWNER's loved clips (his own score >= 7 only): each check widened
				-- just enough to hold the clip's measured value, citing his verdict (kit/anim/calibrate.py)
				if not pos[2] or type(flags.from) ~= "string" then
					return usage(
						"anim calibrate: <dossier> --from <Clip>[,<Clip>] [--apply]",
						"lune run kit anim calibrate katana_hit_heavy --from KatanaHitReactionBackHeavy"
					)
				end
				local argv = { "kit/anim/calibrate.py", pos[2], "--from", flags.from }
				if flags.apply == true then
					table.insert(argv, "--apply")
				end
				return Run.chain("anim", {
					function()
						return Run.content(`anim calibrate {pos[2]}`, Run.tool("python"), argv)
					end,
				}, function()
					return C.CONTENT
				end, `anim calibrate {pos[2]}`)
			end
			if pos[1] == "ab" then
				-- BLIND A/B (AAA gaps v2 F3): two versions on the owner's rig as X / Y in a random order, names
				-- revealed only after the pick (kit/anim/ab_picks.py)
				if not pos[2] or not pos[3] then
					return usage("anim ab: <A> <B> [--seed n]", "lune run kit anim ab Katana4Kiriage Katana4KiriageV2")
				end
				local argv = { "kit/anim/ab_picks.py", pos[2], pos[3] }
				if flags.seed ~= nil then
					table.insert(argv, "--seed")
					table.insert(argv, tostring(flags.seed))
				end
				return Run.chain("anim", {
					function()
						return Run.content(`anim ab {pos[2]} {pos[3]}`, Run.tool("python"), argv)
					end,
				}, function()
					return C.CONTENT
				end, `anim ab {pos[2]} {pos[3]}`)
			end
			if pos[1] == "gallery" then
				-- GALLERY TUNING (kit/anim/anim_gallery.py, research proposal 10): what the owner's picks and rejections on
				-- a move's rounds taught the taste model that chooses the next `anim candidates` sheet (no name: every move)
				local argv = { "kit/anim/anim_gallery.py" }
				if pos[2] then
					table.insert(argv, pos[2])
				end
				return Run.chain("anim", {
					function()
						local step = Run.content("anim gallery", Run.tool("python"), argv)
						-- each move's line (what it learned from, its best guesses) above the summary
						for _, line in string.split(step.tail or "", "\n") do
							if line ~= "" and string.sub(line, 1, 1) ~= "{" then
								print(line)
							end
						end
						return step
					end,
				}, function()
					return C.CONTENT
				end, "anim gallery")
			end
			if pos[1] == "candidates" then
				-- OUR candidates for one action: the dossier's keys varied by the effort sliders, every one gated; the
				-- next round breeds only from the owner's picks (kit/anim/proc_candidates.py); the SHEET is chosen from a
				-- bigger gate-clean pool by gallery tuning - spaced apart by motion, steered by the owner's picks and
				-- rejections (kit/anim/anim_gallery.py)
				local name = pos[2]
				if not name then
					return usage(
						"anim candidates: <Name> [--dossier <move>] [--n 8] [--round K --parents <id>,<id>] [--fresh --change '<what>'] [--intent calm|proper|aggressive] [--blade <gesture>] [--overwrite]",
						"lune run kit anim candidates Roundhouse --dossier roundhouse_kick --n 8"
					)
				end
				-- POSES FIRST (AnimCmd.blockingLock): candidates ARE motion - a new sword move's are not made before
				-- the owner's yes to its key poses (a kick or a reaction has no blocking before its motion yet: free)
				if not AnimCmd.beforeBlocking()[name] then
					local dossierName = if type(flags.dossier) == "string" then flags.dossier else ""
					local gesture = if type(flags.blade) == "string" then flags.blade else ""
					local pair = `{name}=blade={dossierName}={gesture}`
					local stop = AnimCmd.designLock({ pair }) or AnimCmd.blockingLock({ pair })
					if stop then
						return Run.report("anim", {}, C.CONTENT, stop.summary, stop.next_action)
					end
				end
				local argv = { "kit/anim/proc_candidates.py", name }
				-- --by <who>: who picked the --parents (default the owner; an agent breeding under a blanket approval
				-- says so, and gallery tuning never learns the owner's taste from it)
				-- --intent: what the move MEANS (the owner, 2026-11-10: "there's aggressive, there's calm, there is
				-- proper") - read from the loved R6 strikes' tempo (kit/anim/intent.py), a candidate reading as another
				-- intent refused
				-- --blade <gesture>: the dossier's move made on the procedural weapon route (proc_blade) from a craft
				-- gesture in assets/animations/gestures (a two-handed one keeps both fists on the hilt) - candidates only
				for _, key in { "dossier", "n", "round", "parents", "change", "by", "intent", "blade" } do
					if flags[key] ~= nil then
						table.insert(argv, `--{key}`)
						table.insert(argv, tostring(flags[key]))
					end
				end
				for _, key in { "fresh", "overwrite" } do
					if flags[key] then
						table.insert(argv, `--{key}`)
					end
				end
				local made: Run.Step? = nil
				local code = Run.chain("anim", {
					function()
						local step = Run.content(`anim candidates {name}`, Run.tool("python"), argv)
						made = step
						return step
					end,
				}, function()
					return C.CONTENT
				end, `anim candidates {name}`)
				-- (the round's clips are not pictures yet: its last line names the commands that make them)
				local look = made and made.result and made.result.look
				if code == C.PASS and type(look) == "string" then
					Run.out(look)
				end
				return code
			end
			if pos[1] == "edit" then
				-- the posed rig (a pose source's build) becomes the source: the owner edits it in Blender
				local name = pos[2]
				if not name then
					return usage("anim edit: needs a name", "lune run kit anim edit GreatswordLight1")
				end
				local from = Config.build("animations") .. `/{name}.r6.blend`
				local to = `{Config.path("anims")}/{name}.blend`
				if not fs.isFile(from) then
					return usage(`anim edit: no {from} (a pose source builds it)`, `lune run kit anim {name}`)
				end
				if fs.isFile(to) and not flags.force then
					return usage(
						`anim edit: {to} exists - it is already the source (open it in Blender)`,
						`lune run kit anim edit {name} --force (replaces your edits with the pose source's build)`
					)
				end
				fs.writeFile(to, fs.readFile(from))
				return Run.report(
					"anim",
					{},
					C.PASS,
					`anim edit: {to} - open it in Blender (the owner's rig, IK legs, the motion on its controllers); kit anim bakes it from now on. The left hand on the hilt is KEYED per frame (Arm.L): change Arm.R and re-pose Arm.L too`,
					`edit, save, then: lune run kit anim {name} && lune run kit anim look {name} --rig R6`
				)
			end
			if pos[1] == "moveset" then
				-- a MOVESET checked as one thing (kit/anim/moveset.py): every move derived from loved curves, chain seams,
				-- guard, tempo, snaps, a contact sheet and chain previews; the moves land on the owner's rig as keys
				local set = pos[2]
				local file = if set then `{Config.path("anims")}/movesets/{set}.json` else nil
				if not file or not fs.isFile(file) then
					return usage(
						"anim moveset: needs a set in assets/animations/movesets/<Set>.json",
						"lune run kit anim moveset Brawler"
					)
				end
				return Run.chain(
					"anim",
					{
						function()
							return Run.content(
								`moveset {set}`,
								Run.tool("python"),
								{ "kit/anim/moveset.py", file },
								{ KIT_BUILD = Config.path("build") }
							)
						end,
					},
					function()
						return C.CONTENT
					end,
					`anim moveset: build/animations/{set}.moveset.png (contact sheet) - then lune run kit anim <Move> for each move`
				)
			end
			if
				pos[1] == "library"
				or pos[1] == "find"
				or pos[1] == "compose"
				or pos[1] == "critic"
				or pos[1] == "cutscene"
			then
				-- "animate ANYTHING on R6" (owner-approved 2026-10-12): a model DIRECTS in words, real human-made R6
				-- motion PERFORMS - the model never sets a joint. library = describe + cut + learn the critic;
				-- find = words -> clips (or pieces with --take); compose = a script of worded steps -> one clip from
				-- real pieces; critic = P(human-made); cutscene = actors + beats -> one rendered scene
				local steps: { string } = {}
				if pos[1] == "library" then
					steps = {
						"kit/anim/motion_lib.py|build",
						"kit/anim/motion_vocab.py|build",
						"kit/anim/motion_critic.py|train",
					}
				elseif pos[1] == "find" then
					if not pos[2] then
						return usage(
							"anim find: needs words",
							'lune run kit anim find "heavy two handed overhead slam"'
						)
					end
					steps = if flags.take ~= nil
						then { `kit/anim/motion_vocab.py|find|{pos[2]}|--take|{tostring(flags.take)}` }
						else { `kit/anim/motion_lib.py|find|{pos[2]}` }
				elseif pos[1] == "compose" or pos[1] == "cutscene" then
					if not pos[2] or not fs.isFile(pos[2]) then
						return usage(
							`anim {pos[1]}: needs a script file`,
							if pos[1] == "compose"
								then "write {name, steps: [{say, take}]} (kit/anim/motion_vocab.py), then lune run kit anim compose <file> --render"
								else "write {name, actors, beats} (kit/anim/cutscene.py), then lune run kit anim cutscene <file>"
						)
					end
					local tool = if pos[1] == "compose"
						then "kit/anim/motion_vocab.py|compose"
						else "kit/anim/cutscene.py|make"
					local s = `{tool}|{pos[2]}`
					if flags.render ~= nil and pos[1] == "compose" then
						s ..= "|--render"
					end
					-- --timeline: the cutscene for the GAME, its timeline -> KitAnimations.Cutscenes (src/kit/Cutscene plays it);
					-- --plan: the plan alone, no render
					if pos[1] == "cutscene" and flags.timeline ~= nil then
						s ..= `|--game|{Config.path("animOut")}`
					elseif pos[1] == "cutscene" and flags.plan ~= nil then
						s ..= "|--plan"
					end
					if flags.seed ~= nil then
						s ..= `|--seed|{tostring(flags.seed)}`
					end
					steps = { s }
				else
					if not pos[2] then
						return usage(
							"anim critic: needs clip files",
							"lune run kit anim critic build/animations/GsM1.clip.json"
						)
					end
					local s = "kit/anim/motion_critic.py|score"
					for i = 2, #pos do
						s ..= `|{pos[i]}`
					end
					steps = { s }
				end
				local fns = {}
				for _, s in steps do
					local argv = string.split(s, "|")
					table.insert(fns, function()
						return Run.content(
							`{pos[1]} {argv[1]}`,
							Run.tool("python"),
							argv,
							{ KIT_BUILD = Config.path("build") }
						)
					end)
				end
				return Run.chain("anim", fns, function()
					return C.CONTENT
				end, `anim {pos[1]}: done`)
			end
			if pos[1] == "export" then
				-- a clip OUT of Roblox (2026-10-24): kit/anim/export_clip.py -> build/export/<Name>.glb (glTF 2.0: the six
				-- R6 parts + a sword clip's blade as animated nodes, the root travel in), --fbx adds <Name>.fbx through
				-- Blender - for Blender, Unity, Unreal, Godot, three.js, a video editor
				local name = pos[2]
				if not name then
					return usage("anim export: needs a clip name", "lune run kit anim export KatanaKaeshi [--fbx]")
				end
				-- (--cutscene: a planned cutscene's every actor on one clock - kit/anim/cutscene.py's scene.json)
				local r6 = `{Config.build("animations")}/{name}.r6.clip.json`
				local any = `{Config.build("animations")}/{name}.clip.json`
				local src = if flags.cutscene ~= nil
					then `_artifacts/r6lib/cutscenes/{name}/scene.json`
					elseif fs.isFile(r6) then r6
					else any
				if not fs.isFile(src) then
					return usage(
						`anim export: no built {if flags.cutscene ~= nil then "cutscene" else "clip"} {name}`,
						if flags.cutscene ~= nil
							then `lune run kit anim cutscene assets/animations/cutscenes/{name}.json --plan  (then export it)`
							else `lune run kit anim {name}  (then export it)`
					)
				end
				local outDir = Config.build("export")
				Config.ensureDir(outDir)
				local argv = { "kit/anim/export_clip.py", src, `{outDir}/{name}.glb` }
				if flags.cutscene ~= nil then
					table.insert(argv, "--cutscene")
				end
				if flags.gltf ~= nil then
					table.insert(argv, "--gltf")
				end
				if flags.fbx ~= nil then
					table.insert(argv, "--fbx")
					table.insert(argv, `{outDir}/{name}.fbx`)
				end
				return Run.chain(
					"anim",
					{
						function()
							return Run.content(`export {name}`, Run.tool("python"), argv)
						end,
					},
					function()
						return C.CONTENT
					end,
					`anim export: {outDir}/{name}.glb{if flags.fbx ~= nil then " + .fbx" else ""} - open it in Blender or any glTF viewer`
				)
			end
			if pos[1] == "roto" then
				-- POSE BY POINTING (AAA gaps v2 A3): click the joints on any picture -> an R6 pose fitted to them
				-- (kit/anim/roto.py; the page runs until Save) -> assets/animations/poses/<Pose>.roto.json
				local picture = pos[2]
				if not picture or type(flags.as) ~= "string" then
					return usage(
						"anim roto: <picture> --as <Pose> [--clicks <clicks.json>]",
						"lune run kit anim roto refs/underhip_frame.png --as UnderhipTop"
					)
				end
				local argv = if type(flags.clicks) == "string"
					then { "kit/anim/roto.py", "fit", picture, "--as", flags.as, "--clicks", flags.clicks }
					else { "kit/anim/roto.py", "serve", picture, "--as", flags.as }
				return Run.chain("anim", {
					function()
						return Run.content(
							`roto {flags.as}`,
							Run.tool("python"),
							argv,
							{ KIT_BUILD = Config.path("build") }
						)
					end,
				}, function()
					return C.CONTENT
				end, `anim roto {flags.as}: done`)
			end
			if pos[1] == "film" then
				-- FILM YOURSELF (AAA gaps v2 A2): a phone video of the move -> MediaPipe -> the key frames -> R6 key poses
				-- (kit/anim/film_keys.py through the pose-by-pointing fitter)
				if not pos[2] or type(flags.as) ~= "string" then
					return usage(
						"anim film: <video.mp4> --as <Move> [--start s] [--end s] [--keys n]",
						"lune run kit anim film my_kick.mp4 --as KickFilm --start 1.2 --end 2.4"
					)
				end
				local argv = { "kit/anim/film_keys.py", pos[2], "--as", flags.as }
				for _, f in { "start", "end", "keys" } do
					if type(flags[f]) == "string" then
						table.insert(argv, "--" .. f)
						table.insert(argv, flags[f])
					end
				end
				return Run.chain("anim", {
					function()
						return Run.content(
							`film {flags.as}`,
							Run.tool("python"),
							argv,
							{ KIT_BUILD = Config.path("build") }
						)
					end,
				}, function()
					return C.CONTENT
				end, `anim film {flags.as}: done`)
			end
			if pos[1] == "polish" then
				-- LAYERED POLISH, root outward (AAA gaps v2 A4): which layer to smooth next (kit/anim/polish.py)
				if not pos[2] then
					return usage("anim polish: <Name>", "lune run kit anim polish Katana1Kesa")
				end
				return Run.chain("anim", {
					function()
						return Run.content(
							`polish {pos[2]}`,
							Run.tool("python"),
							{ "kit/anim/polish.py", pos[2] },
							{ KIT_BUILD = Config.path("build") }
						)
					end,
				}, function()
					return C.CONTENT
				end, `anim polish {pos[2]}: done`)
			end
			if pos[1] == "design" then
				-- THE ATTACK SET'S DESIGN PAGE (the studio route's A1, kit/anim/set_design.py): a string of attacks
				-- designed before any of them is posed - each one's cut on the wheel, its height, what the body does,
				-- its frame budget, its intent, the pose it ends in, what follows - with two attacks that are too alike
				-- named COUSINS (by design, and by measure once their keys exist), the owner's yes to the design as it
				-- is, and the lock: a new move of the set is not made before that yes
				local set = pos[2]
				if not set then
					return usage(
						'anim design: <Set> [--new --attacks <n> [--weapon <word>] | --from <a.move.json>,<b.move.json>,... | --approve "<the owner\'s words>" --by owner --id <the id on the page he saw> | --state [--need approved]]',
						"lune run kit anim design KatanaString --new --attacks 5"
					)
				end
				local designs = Config.path("anims") .. "/designs"
				local out = Config.build("animations") .. `/{set}.design.png`
				local argv: { string }
				if flags.new then
					if not tonumber(flags.attacks) then
						return usage(
							"anim design --new: how many attacks? --attacks <n> (two or more)",
							`lune run kit anim design {set} --new --attacks 5`
						)
					end
					argv = { "new", set, "--attacks", tostring(flags.attacks) }
					if type(flags.weapon) == "string" then
						table.insert(argv, "--weapon")
						table.insert(argv, flags.weapon)
					end
				elseif type(flags.from) == "string" then
					argv = { "from-moves", set }
					for _, p in string.split(flags.from, ",") do
						if p ~= "" then
							table.insert(argv, p)
						end
					end
					if type(flags.weapon) == "string" then
						table.insert(argv, "--weapon")
						table.insert(argv, flags.weapon)
					end
				elseif flags.approve ~= nil then
					argv = { "approve", set, if type(flags.approve) == "string" then flags.approve else "" }
					for _, key in { "by", "id" } do
						if type(flags[key]) == "string" then
							table.insert(argv, `--{key}`)
							table.insert(argv, flags[key])
						end
					end
					table.insert(argv, "--page") -- (his yes is to the page that was drawn: `kit anim design <Set>`)
					table.insert(argv, out)
				elseif flags.state then
					argv = { "state", set }
					if type(flags.need) == "string" then
						table.insert(argv, "--need")
						table.insert(argv, flags.need)
					end
				else
					argv = { "page", set, "--out", out }
				end
				table.insert(argv, 1, "kit/anim/set_design.py")
				table.insert(argv, "--designs")
				table.insert(argv, designs)
				local isPage = argv[2] == "page"
				local made: Run.Step? = nil
				local code = Run.chain("anim", {
					function()
						local step =
							Run.content(`design {set}`, Run.tool("python"), argv, { KIT_BUILD = Config.path("build") })
						made = step
						return step
					end,
				}, function()
					return C.CONTENT
				end, `anim design {set}: {designs}/{set}.design.json`)
				-- the page is drawn whether the design passes or not: its problems are ON it
				if isPage and made and made.result and type(made.result.page) == "string" then
					Run.out(
						`LOOK: {made.result.page} - the design page of {set}: every attack's cut on the wheel (red = designed, blue = its keys), its frame budget, the string's rhythm, the problems and notes on top`
					)
				end
				return code
			end
			if pos[1] == "match" then
				-- THE TABLES THE GAME MATCHES AGAINST (kit/anim/match_tables.py; the owner's method lists: pose
				-- matching, distance matching, motion matching), baked from built clips for src/kit/AnimMatch.luau:
				--   kit anim match pose <clip.json> --out <table.json>
				--   kit anim match distance <clip.json> [--to <Event>] --out <table.json>
				--   kit anim match motion <clip.json> <clip.json>... --out <db.json>
				local kind = pos[2]
				if
					(kind ~= "pose" and kind ~= "distance" and kind ~= "motion")
					or not pos[3]
					or type(flags.out) ~= "string"
				then
					return usage(
						"anim match: pose|distance|motion <clip.json | the name of a built clip>... [--to <Event>] --out <table.json>",
						"python kit/anim/match_tables.py   (its first lines say what each table is)"
					)
				end
				local argv = { "kit/anim/match_tables.py", kind }
				for i = 3, #pos do
					-- a file, or the NAME of a built clip (its R6 version when the build made one)
					local given = pos[i]
					local found = if fs.isFile(given)
						then given
						elseif fs.isFile(clipPathOf(given, "R6")) then clipPathOf(given, "R6")
						elseif fs.isFile(clipPathOf(given)) then clipPathOf(given)
						else nil
					if not found then
						return usage(
							`anim match: {given} is neither a file nor a built clip ({clipPathOf(given)} or {clipPathOf(
								given,
								"R6"
							)})`,
							"give the clip's file, or build the clip first and give its name"
						)
					end
					table.insert(argv, found)
				end
				if type(flags.to) == "string" then
					table.insert(argv, "--to")
					table.insert(argv, flags.to)
				end
				table.insert(argv, "--out")
				table.insert(argv, flags.out)
				return Run.chain("animmatch", {
					function()
						return Run.content(`match {kind}`, Run.tool("python"), argv)
					end,
				}, function()
					return C.CONTENT
				end, `anim match {kind}: {flags.out}`)
			end
			if pos[1] == "prop" then
				-- A PROP'S CLIPS, THE WHOLE WAY (kit/anim/prop_rig.py go; the owner's method lists: object animation):
				-- <anims>/props/<Prop>.prop.json (boxes on hinges and slides) -> its rig; every keyframe spec in
				-- <anims>/props/<Prop>/ -> a clip held to the prop's joints -> the KeyframeSequence model the game
				-- plays, in <animOut>/props/<Prop>/ (models only; the rig, clips and manifest go to
				-- build/animations/props/<Prop>). A clip that breaks a joint leaves no model.
				-- --dir <props folder> / --out <folder>: another place (a fixture, a draft)
				-- --model: the prop is a MODEL THE 3D LANE BUILT with moving parts (a.joint): its rig is read from
				-- build/models/<Prop>.manifest.json, the joints src/kit/Models.luau spawns (--model <manifest>: another)
				local prop = pos[2]
				if not prop then
					return usage(
						"anim prop: <Prop> [--model [<manifest>] [--tool] [--check]] [--dir <props folder>] [--out <folder>]",
						"lune run kit anim prop Chest"
					)
				end
				local dir = if type(flags.dir) == "string" then flags.dir else Config.path("anims") .. "/props"
				local out = if type(flags.out) == "string" then flags.out else Config.path("animOut") .. `/props/{prop}`
				local propFile = `{dir}/{prop}.prop.json`
				if flags.model then
					propFile = if type(flags.model) == "string"
						then flags.model
						else Config.build("models") .. `/{prop}.manifest.json`
					if not fs.isFile(propFile) then
						return usage(
							`anim prop: no {propFile} (the built model's manifest: build it first)`,
							`lune run kit asset {prop}`
						)
					end
				elseif not fs.isFile(propFile) then
					return usage(
						`anim prop: no {propFile} (the prop's parts, pivots, hinges and slides)`,
						"python kit/anim/prop_rig.py   (its first lines show the file; a built model: --model)"
					)
				end
				if flags.model and flags.check then
					-- the clips the last build left, against the joints the model has NOW
					return Run.chain("animprop", {
						function()
							return Run.content(
								`prop {prop} (its clips against the model's joints)`,
								Run.tool("python"),
								{
									"kit/anim/prop_rig.py",
									"stale",
									propFile,
									"--props",
									Config.build("animations") .. `/props/{prop}/{string.lower(prop)}.props.json`,
								}
							)
						end,
					}, function()
						return C.CONTENT
					end, `anim prop {prop}: its clips were built on the joints the model has now`)
				end
				local argv = { "kit/anim/prop_rig.py", "go", propFile }
				local specs = {}
				if fs.isDir(`{dir}/{prop}`) then
					for _, f in fs.readDir(`{dir}/{prop}`) do
						if string.sub(f, -5) == ".json" then
							table.insert(specs, `{dir}/{prop}/{f}`)
						end
					end
				end
				table.sort(specs)
				if #specs == 0 then
					return usage(
						`anim prop: no keyframe spec in {dir}/{prop}/ (one .json a clip, "rig": "{prop}")`,
						`lune run kit anim prop {prop}`
					)
				end
				for _, sp in specs do
					table.insert(argv, sp)
				end
				table.insert(argv, "--out")
				table.insert(argv, out)
				table.insert(argv, "--name") -- (the file must BE this prop: its specs name it)
				table.insert(argv, prop)
				if flags.tool then
					table.insert(argv, "--tool") -- (spawned by Models.tool: its root is named Handle)
				end
				table.insert(argv, "--keep") -- (the rig, the clips and the manifest: beside the build, never in the game's tree)
				table.insert(argv, Config.build("animations") .. `/props/{prop}`)
				return Run.chain("animprop", {
					function()
						return Run.content(
							`prop {prop}`,
							Run.tool("python"),
							argv,
							{ KIT_BUILD = Config.path("build") }
						)
					end,
				}, function()
					return C.CONTENT
				end, `anim prop {prop}: {out}/ (its rig, a model and a clip for each spec)`)
			end
			if pos[1] == "timing" then
				-- THE TIMING CHART of a built move or of any clip (kit/anim/timing_chart.py): the striker's spacing frame
				-- by frame with the keys and the Hit marked, and its reading in words. Every sheet carries the same chart
				-- (timing.png); this is the chart alone, in a second, with no render
				local name = pos[2]
				if not name then
					return usage(
						"anim timing: <Name> [--clip <clip.json>] [--move <move.json> | --no-move]",
						"lune run kit anim timing GreatswordSideCut"
					)
				end
				local clipFlag: string? = if type(flags.clip) == "string" then flags.clip else nil
				local clip = clipFlag or sheetClip(name)
				if not fs.isFile(clip) then
					return usage(
						if clipFlag
							then `anim timing: no clip at {clipFlag}`
							else `anim timing: no built clip of {name}`,
						`lune run kit anim {name}`
					)
				end
				-- the move file of the NAME belongs to the built clip of that name: a clip named by --clip is charted
				-- alone unless its move is named too (--move); --no-move charts any clip alone
				local movePath: string? = nil
				if flags.move ~= nil then
					if type(flags.move) ~= "string" or not fs.isFile(flags.move) then
						return usage(
							`anim timing: no move file at {tostring(flags.move)}`,
							`lune run kit anim timing {name} --move <move.json>`
						)
					end
					movePath = flags.move
				elseif not clipFlag and not flags["no-move"] then
					movePath = `{Config.path("anims")}/{name}.move.json`
				end
				local out = if clipFlag
					then (string.gsub(string.gsub(clipFlag, "\\", "/"), "%.clip%.json$", "")) .. ".timing.png"
					else Config.build("animations") .. `/{name}.timing.png`
				local argv = { "kit/anim/timing_chart.py", clip, "--out", out }
				if movePath and fs.isFile(movePath) then
					table.insert(argv, "--move")
					table.insert(argv, movePath)
				end
				return Run.chain("anim", {
					function()
						return Run.content(`timing {name}`, Run.tool("python"), argv)
					end,
				}, function()
					return C.CONTENT
				end, `anim timing {name}: {out}`)
			end
			if pos[1] == "sheet" then
				-- THE SHEET of a built move (the studio route's A0, kit/anim/pose_sheet.py): its key poses large on the
				-- owner's rig beside the dossier's reference frames, and its 12-a-second strips with the paths drawn
				local name = pos[2]
				if not name then
					return usage(
						"anim sheet: <Name> [--dossier <move>] [--no-strips] [--clip <a candidate's .clip.json>]",
						"lune run kit anim sheet GreatswordSideCut"
					)
				end
				-- --clip: a clip that is not a built animation - one candidate of a round (build/candidates/<Name>/
				-- round_K/<id>.clip.json); its sheet goes beside it, <id>.sheet/
				local clipFlag: string? = if type(flags.clip) == "string" then flags.clip else nil
				if clipFlag and not fs.isFile(clipFlag) then
					return usage(
						`anim sheet: no clip at {clipFlag}`,
						`lune run kit anim sheet {name} --clip build/candidates/{name}/round_0/<id>.clip.json`
					)
				end
				if not fs.isFile(OWNER_RIG) then
					return usage(
						`anim sheet: this project has no {OWNER_RIG} (the rig a sheet is rendered on)`,
						"lune run kit anim look <Name>"
					)
				end
				if not clipFlag and not fs.isFile(clipPathOf(name, "R6")) and not fs.isFile(clipPathOf(name)) then
					return usage(`anim sheet: no built clip of {name}`, `lune run kit anim {name}`)
				end
				local dir = if clipFlag
					then (string.gsub(string.gsub(clipFlag, "\\", "/"), "%.clip%.json$", "")) .. ".sheet"
					else AnimCmd.sheetDir(name)
				local code = Run.chain(
					"anim",
					AnimCmd.sheetSteps(name, {
						dossier = if type(flags.dossier) == "string" then flags.dossier else nil,
						strips = if flags["no-strips"] then false else nil,
						clip = clipFlag,
						dir = if clipFlag then dir else nil,
					}),
					function()
						return C.CONTENT
					end,
					`anim sheet {name}: {dir}/pose_sheet.png (every key pose beside its reference), keys/ (the same panes at full size), the strips - the LOOK line below says what is in it`
				)
				if code == C.PASS then
					local _, line = AnimCmd.sheetState(name, dir)
					Run.out(line or `LOOK: {dir}/`)
				end
				return code
			end
			if pos[1] == "diff" or pos[1] == "thumbs" then
				-- VERSION DIFF dailies (A5: kit/anim/diff.py <A> <B>) and SILHOUETTE THUMBNAILS (A1: kit/anim/thumbs.py)
				local sub = pos[1]
				if not pos[2] or (sub == "diff" and not pos[3]) then
					return usage(
						if sub == "diff" then "anim diff: <A> <B>" else "anim thumbs: <Name>",
						if sub == "diff"
							then "lune run kit anim diff KatanaChain KatanaChainStepped"
							else "lune run kit anim thumbs Katana1Kesa"
					)
				end
				local argv = if sub == "diff"
					then { "kit/anim/diff.py", pos[2], pos[3] }
					else { "kit/anim/thumbs.py", pos[2] }
				return Run.chain("anim", {
					function()
						return Run.content(
							`{sub} {pos[2]}`,
							Run.tool("python"),
							argv,
							{ KIT_BUILD = Config.path("build") }
						)
					end,
				}, function()
					return C.CONTENT
				end, `anim {sub}: done`)
			end
			if pos[1] == "appeal" then
				-- POSE APPEAL in numbers (AAA gaps v2 B3 / B4 / B5): line of action, twinning, the silhouette from the
				-- player's camera per key pose, balance on still frames, and (--cheat) camera cheats as key_edits
				local name = pos[2]
				if not name then
					return usage(
						"anim appeal: <Name> [--cheat] [--max <deg>]",
						"lune run kit anim appeal Katana1Kesa --cheat"
					)
				end
				local argv = { "kit/anim/pose_appeal.py", name }
				if flags.cheat then
					table.insert(argv, "--cheat")
				end
				if type(flags.max) == "string" then
					table.insert(argv, "--max")
					table.insert(argv, flags.max)
				end
				return Run.chain("anim", {
					function()
						return Run.content(
							`appeal {name}`,
							Run.tool("python"),
							argv,
							{ KIT_BUILD = Config.path("build") }
						)
					end,
				}, function()
					return C.CONTENT
				end, `anim appeal {name}: done`)
			end
			if pos[1] == "style" then
				-- the game's ANIMATION STYLE GUIDE on a set (AAA gaps v2 A6 / C1 / C2): the opener on the guard pose, every
				-- cut linked to the last, startups inside their feel tier's budget (games/<Game>/anim_style.json)
				local set = pos[2]
				if not set then
					return usage("anim style: <Set> [--game <Game>]", "lune run kit anim style KatanaSet")
				end
				local argv = { "kit/anim/style_check.py", set }
				if type(flags.game) == "string" then
					table.insert(argv, "--game")
					table.insert(argv, flags.game)
				end
				return Run.chain("anim", {
					function()
						return Run.content(
							`style {set}`,
							Run.tool("python"),
							argv,
							{ KIT_BUILD = Config.path("build") }
						)
					end,
				}, function()
					return C.CONTENT
				end, `anim style {set}: done`)
			end
			if pos[1] == "note" then
				-- DAILIES with frame-accurate notes (AAA plan #8): the owner's words about ONE frame of a clip -> a
				-- verdict with the frame (default "bad": a note is a correction) -> the dossier gate quotes the frame
				local name, frame, words = pos[2], tonumber(pos[3]), pos[4]
				if not name or not frame or frame % 1 ~= 0 or frame < 0 or not words then
					return usage(
						'anim note: <Name> <frame> "<what the owner said>" [--word bad|ok|good|horrible|loved]',
						'lune run kit anim note Katana4Kiriage 18 "the blade dips here"'
					)
				end
				local word = if type(flags.word) == "string" then flags.word else "bad"
				return Run.chain("anim", {
					function()
						return Run.content(
							`note {name}`,
							Run.tool("python"),
							{ "kit/anim/book.py", "--verdict", name, word, words, "--frame", tostring(frame) },
							{ KIT_BUILD = Config.path("build") }
						)
					end,
					function()
						local scoreOfWord = { loved = 9, good = 7, ok = 5, bad = 2, horrible = 1 }
						local path, err = Vault.record({
							kind = "anim",
							name = name,
							score = scoreOfWord[string.lower(word)],
							words = `{word} at frame {frame}: {words}`,
							tags = { "anim-verdict", "frame-note" },
						})
						return Run.step(
							"vault",
							path ~= nil,
							err or "",
							{ summary = if path then `recorded: {path}` else `not recorded: {err}` }
						)
					end,
				}, function()
					return C.CONTENT
				end, `anim note: {name} frame {frame} ({word})`)
			end
			if pos[1] == "book" or pos[1] == "verdict" then
				-- the style book (kit/anim/book.py): every R6 clip measured with one ruler beside the owner's verdicts,
				-- and what separates loved from rejected per kind; verdict: record the owner's word on a clip
				local argv: { string }
				if pos[1] == "verdict" then
					if not pos[2] or not pos[3] then
						return usage(
							'anim verdict: needs <Name> <loved|good|ok|bad|horrible> ["why"]',
							'lune run kit anim verdict RigSprint loved "the legs no longer snap"'
						)
					end
					argv = { "kit/anim/book.py", "--verdict", pos[2], pos[3], pos[4] or "" }
				else
					argv = { "kit/anim/book.py", "--out", Config.build("animations") .. "/book" }
				end
				return Run.chain(
					"anim",
					{
						function()
							return Run.content(
								`{pos[1]}`,
								Run.tool("python"),
								argv,
								{ KIT_BUILD = Config.path("build") }
							)
						end,
						function()
							-- the ONE verdict record (kit/knowledge/vault): the owner's word on a clip lands beside
							-- every other department's verdicts (loved 9 / good 7 / ok 5 / bad 2 / horrible 1)
							if pos[1] ~= "verdict" then
								return Run.step("vault", true, "", { summary = "book: nothing to record" })
							end
							local scoreOfWord = { loved = 9, good = 7, ok = 5, bad = 2, horrible = 1 }
							local path, err = Vault.record({
								kind = "anim",
								name = pos[2],
								score = scoreOfWord[string.lower(pos[3])],
								words = if pos[4] and pos[4] ~= "" then `{pos[3]}: {pos[4]}` else pos[3],
								tags = { "anim-verdict" },
							})
							return Run.step(
								"vault",
								path ~= nil,
								err or "",
								{ summary = if path then `recorded: {path}` else `not recorded: {err}` }
							)
						end,
					},
					function()
						return C.CONTENT
					end,
					if pos[1] == "book"
						then "anim book: build/animations/book.md (every clip, the verdicts, what separates loved from rejected)"
						else `anim verdict: {pos[2]} {pos[3]} (the book + the vault)`
				)
			end
			if pos[1] == "derive" then
				-- a NEW animation derived from loved ones by editing their curves (kit/anim/derive.py: despike, retime,
				-- amplify, posture, shift, layer, mirror, style transfer, blend), then put on the owner's rig as
				-- editable reduced keys (kit/anim/pose_from.py --reduce): assets/animations/<Name>.pose.json
				local name = pos[2]
				if not name or not string.match(name, "^%a[%w_]*$") then
					return usage("anim derive: needs a name", "lune run kit anim derive GSRun")
				end
				local recipe = `{Config.path("anims")}/{name}.derive.json`
				if not fs.isFile(recipe) then
					return usage(
						`anim derive: no {recipe}`,
						"write the recipe: {name, from, ops: [...]} (kit/anim/derive.py)"
					)
				end
				local src = Config.build("animations") .. `/{name}.src.clip.json`
				local tol = if flags.reduce ~= nil then tostring(flags.reduce) else "2"
				return Run.chain(
					"anim",
					{
						function()
							return Run.content(
								`derive {name}`,
								Run.tool("python"),
								{ "kit/anim/derive.py", recipe, "--out", src },
								{ KIT_BUILD = Config.path("build") }
							)
						end,
						function()
							return Run.content(`derive {name} -> rig keys`, Run.tool("python"), {
								"kit/anim/pose_from.py",
								src,
								"--as",
								name,
								"--reduce",
								tol,
								"--out",
								`{Config.path("anims")}/{name}.pose.json`,
							}, { KIT_BUILD = Config.path("build") })
						end,
					},
					function()
						return C.CONTENT
					end,
					`anim derive: assets/animations/{name}.pose.json (from its .derive.json) - now: lune run kit anim {name}`
				)
			end
			if pos[1] == "new" and type(flags.strike) == "string" then
				-- an AUTHORED strike from the judged craft rules (kit/anim/strike_r6.py): one guard, coil, hip-lead
				-- breakdown, the Hit on the fastest frame at full reach, overshoot, the torso home before the arm
				local name = pos[2]
				if not name or not string.match(name, "^%a[%w_]*$") then
					return usage("anim new: needs a name", "lune run kit anim new MyJab --strike jab")
				end
				local path = `{Config.path("anims")}/{name}.pose.json`
				if fs.isFile(path) and not flags.force then
					return usage(
						`anim new: {path} exists`,
						`lune run kit anim new {name} --strike {flags.strike} --force`
					)
				end
				return Run.chain("anim", {
					function()
						-- how much loved data backs this kind (a kick: none - its dossier carries the numbers)
						return Run.content(
							`calibration coverage {flags.strike}`,
							Run.tool("python"),
							{ "kit/anim/proc_calib.py", "coverage", "combat", "--kind", flags.strike }
						)
					end,
					function()
						return Run.content(
							`strike {name}`,
							Run.tool("python"),
							{ "kit/anim/strike_r6.py", flags.strike, "--as", name, "--out", path },
							{ KIT_BUILD = Config.path("build") }
						)
					end,
				}, function()
					return C.CONTENT
				end, `anim new: {path} - now: lune run kit anim {name} && lune run kit anim judge {name} --rig R6`)
			end
			if pos[1] == "new" and type(flags.cycle) == "string" then
				-- a locomotion cycle from the measured key poses of an approved clip (kit/anim/cycle_r6.py)
				local name = pos[2]
				if not name or not string.match(name, "^%a[%w_]*$") then
					return usage(
						"anim new: needs a name (letters, digits, _)",
						"lune run kit anim new RigRun3 --cycle run"
					)
				end
				local path = `{Config.path("anims")}/{name}.pose.json`
				if fs.isFile(path) and not flags.force then
					return usage(
						`anim new: {path} exists`,
						`lune run kit anim new {name} --cycle {flags.cycle} --force`
					)
				end
				Config.ensureDir(Config.path("anims"))
				local argv = { "kit/anim/cycle_r6.py", flags.cycle, "--as", name, "--out", path }
				if type(flags.params) == "string" then
					table.insert(argv, "--params")
					table.insert(argv, flags.params)
				end
				return Run.chain(
					"anim",
					{
						function()
							return Run.content(
								`cycle {name}`,
								Run.tool("python"),
								argv,
								{ KIT_BUILD = Config.path("build") }
							)
						end,
					},
					function()
						return C.CONTENT
					end,
					`anim new: {path} - now: lune run kit anim {name} && lune run kit anim sil {name} --vs <the reference>`
				)
			end
			if pos[1] == "new" and flags.pose then
				local name = pos[2]
				if not name or not string.match(name, "^%a[%w_]*$") then
					return usage(
						"anim new: needs a name (letters, digits, _)",
						"lune run kit anim new GreatswordLight1 --pose"
					)
				end
				local path = `{Config.path("anims")}/{name}.pose.json`
				if fs.isFile(path) and not flags.force then
					return usage(`anim new: {path} exists`, `lune run kit anim new {name} --pose --force`)
				end
				Config.ensureDir(Config.path("anims"))
				fs.writeFile(path, (string.gsub(fs.readFile("kit/templates/anim.pose.json"), "__NAME__", name)))
				return Run.report(
					"anim",
					{},
					C.PASS,
					`anim new: {path} (key poses on the owner's R6 rig: body, head, hands + blade, IK feet)`,
					`edit the keys (stage axes: x right, y up from the floor, z forward), then: lune run kit anim {name} && lune run kit anim look {name} --rig R6`
				)
			end
			if pos[1] == "new" and flags.gait then
				local name = pos[2]
				if not name then
					return usage("anim new: needs a name", "lune run kit anim new Walk --gait walk")
				end
				local kind = tostring(flags.gait)
				local r6 = flags.rig == "R6"
				if r6 and not R6_GAIT_KINDS[kind] then
					return usage(`anim new: unknown R6 gait kind "{kind}"`, "one of: walk run sprint idle (--rig R6)")
				end
				if not r6 and not GAIT_KINDS[kind] then
					return usage(`anim new: unknown gait kind "{kind}"`, `one of: {table.concat(GAIT_KIND_LIST, " ")}`)
				end
				if not string.match(name, "^%a[%w_]*$") then
					return usage(
						`anim new: "{name}" is not a name (letters, digits, _)`,
						"lune run kit anim new Walk --gait walk"
					)
				end
				local path = `{Config.path("anims")}/{name}.gait.json`
				if fs.isFile(path) and not flags.force then
					return usage(`anim new: {path} exists`, `lune run kit anim new {name} --gait {flags.gait} --force`)
				end
				Config.ensureDir(Config.path("anims"))
				local spec: { [string]: any } = { name = name, kind = flags.gait, fps = 30 }
				if r6 then
					spec.rig = "R6"
				end
				fs.writeFile(path, serde.encode("json", spec, true))
				return Run.report(
					"anim",
					{},
					C.PASS,
					`anim new: {path} ({flags.gait}{if r6 then ", R6-native" else ""})`,
					if r6
						then `edit its parameters (speed, cycle, duty, amplitude, band, lean, arm, arm_back, arm_in, arm_out, knee, twist, sway, bob, rise, overshoot, head, look; idle: period, breathe, arm_out; kit/anim/gait_r6.py KINDS), then: lune run kit anim {name} and kit anim look {name} --rig R6`
						else `edit its parameters (human gaits: hip, knee, stance, cycle, style, lean, sway, arm, elbow, head; strafes: hip, knee, stance, cycle, roll, twist, lean, arm, elbow, head; idle: breathe, roll, twist, lean, arm, elbow, head; kit/anim/gait.py KINDS), then: lune run kit anim {name}`
				)
			end
			if pos[1] == "judge" then
				local name = pos[2]
				if not name then
					return usage("anim judge: needs an animation name", "lune run kit anim judge Slash")
				end
				if not flags.packet and not flags.record then
					-- THE VERIFIER (mission 04-anim 5.11): the clip against its move dossier, ONE difference + ONE edit,
					-- never a score (kit/anim/dossier_verify.py); the old fresh-reviewer packet: --packet
					local argv = { "kit/anim/dossier_verify.py", name }
					if type(flags.dossier) == "string" then
						table.insert(argv, "--dossier")
						table.insert(argv, flags.dossier)
					end
					return Run.chain("anim", {
						function()
							return Run.content(`anim judge {name}`, Run.tool("python"), argv)
						end,
					}, function()
						return C.CONTENT
					end, `anim judge {name}: no difference outside its dossier`)
				end
				local py = { "kit/anim/judge.py", if flags.record then "record" else "packet", name }
				if flags.record then
					if type(flags.record) ~= "string" or not fs.isFile(flags.record) then
						return usage(
							"anim judge --record: needs the reviewer's verdict file",
							`lune run kit anim judge {name} --record build/judge/anim/{name}/verdict.json`
						)
					end
					table.insert(py, flags.record)
				end
				return Run.chain("anim", {
					function()
						return Run.content(`judge {name}`, Run.tool("python"), py, { KIT_BUILD = Config.path("build") })
					end,
				}, function()
					return C.CONTENT
				end, if flags.record
					then `anim judge: {name} recorded`
					else `anim judge: packet for a fresh reviewer`)
			end
			if pos[1] == "import" then
				local file, clipName, name = pos[2], flags.clip, flags["as"]
				if not file or type(clipName) ~= "string" or type(name) ~= "string" then
					return usage(
						"anim import: needs <motion file> --clip <animation name> --as <Name>",
						"lune run kit anim import _downloads/quaternius_ual2/UAL2_Standard.glb --clip Sword_Regular_A --as SwordA"
					)
				end
				if not fs.isFile(file) then
					return usage(
						`anim import: no file {file}`,
						"a vetted motion file (VETLOG.md): glTF / GLB / FBX / BVH, or a Roblox .rbxm holding KeyframeSequences"
					)
				end
				if not string.match(name, "^%a[%w_]*$") then
					return usage(`anim import: "{name}" is not a name (letters, digits, _)`, "--as SwordA")
				end
				Config.ensureDir(Config.path("anims"))
				local path = `{Config.path("anims")}/{name}.import.json`
				local spec = {
					name = name,
					file = file,
					clip = clipName,
					fps = tonumber(flags.fps) or 30,
					loop = flags.loop == true,
					priority = if type(flags.priority) == "string"
						then flags.priority
						elseif flags.loop == true then "Movement"
						else "Action",
					-- a library's keyed whips (a knee snapping straight at touchdown) read as snaps to the kit's
					-- 15-degree rule; 40 still catches real glitches (90+). Tighten per clip if the motion is calm.
					gate = { pop_deg = 40 },
				}
				if isRobloxModel(file) then
					-- a finished Roblox animation, kept as it is: its feet skate as every R6 foot does, its loop may
					-- not quite close - the gates report, the owner's eye judges
					spec.gate =
						{ foot_slide = 1.0, foot_skate = 1.0, pop_deg = 60, penetration = 0.5, loop_seam_deg = 5 }
					spec.note =
						"a finished Roblox R6 animation imported as it is (no fold, no retarget): a REFERENCE judged by eye; the gates only report (speed: set `speed` for the runtime)"
					spec.loop = nil
					spec.priority = nil
				end
				fs.writeFile(path, serde.encode("json", spec, true))
				return Run.chain("anim", { AnimCmd.importStep(name, path) }, function()
					return C.CONTENT
				end, `anim import: {path} (edit: hit, trim, map, arms, events) — now: lune run kit anim {name}`)
			end
			if pos[1] == "keys" then
				-- a finished reference clip's BODY as editable technique keys (kit/anim/keys_from.py -> <Name>.move.json)
				local name = pos[2]
				if not name or type(flags.from) ~= "string" then
					return usage(
						"anim keys: needs <Name> --from <Reference> [--length 5.2] [--grip 0.8] [--grip-pitch 20] [--every 2] [--hands 2|1]",
						"lune run kit anim keys ClaymoreWhirlKeys --from RefFinisher"
					)
				end
				if not string.match(name, "^%a[%w_]*$") then
					return usage(`anim keys: "{name}" is not a name (letters, digits, _)`, "ClaymoreWhirlKeys")
				end
				local refNative = clipPathOf(flags.from)
				local okR, refClip = readJson(refNative)
				local refPath = if okR
						and type(refClip) == "table"
						and refClip.rig == "R6"
					then refNative
					else clipPathOf(flags.from, "R6")
				if not fs.isFile(refPath) then
					return usage(`anim keys: no R6 clip for {flags.from}`, `lune run kit anim {flags.from}`)
				end
				Config.ensureDir(Config.path("anims"))
				local out = `{Config.path("anims")}/{name}.move.json`
				local argv = { "kit/anim/keys_from.py", refPath, "--as", name, "--out", out }
				for _, f in { "length", "grip", "grip-pitch", "every", "hands" } do
					if flags[f] ~= nil then
						table.insert(argv, "--" .. f)
						table.insert(argv, tostring(flags[f]))
					end
				end
				return Run.chain(
					"anim",
					{
						function()
							return Run.content(
								`keys {name}`,
								Run.tool("python"),
								argv,
								{ KIT_BUILD = Config.path("build") }
							)
						end,
					},
					function()
						return C.CONTENT
					end,
					`anim keys: {out} (the body of {flags.from} as technique keys) - now: lune run kit anim {name} && kit anim look {name} --rig R6; edit grip / dir for the weapon arc`
				)
			end
			if pos[1] == "rearm" then
				local name = pos[2]
				if not name or type(flags.from) ~= "string" then
					return usage(
						"anim rearm: needs <Name> --from <Clip> [--length 4.8] [--grip 0.75] [--grip-pitch 0] [--lag 0.04] [--hands 2]",
						"lune run kit anim rearm GreatswordLight1 --from SwordA --length 4.8"
					)
				end
				if not string.match(name, "^%a[%w_]*$") then
					return usage(`anim rearm: "{name}" is not a name (letters, digits, _)`, "GreatswordLight1")
				end
				Config.ensureDir(Config.path("anims"))
				local path = `{Config.path("anims")}/{name}.rearm.json`
				local spec = {
					name = name,
					from = flags.from,
					sword = {
						length = tonumber(flags.length) or 4.8,
						grip = tonumber(flags.grip) or 0.75,
						grip_pitch = tonumber(flags["grip-pitch"]) or 0,
					},
					hands = tonumber(flags.hands) or 2,
					lag = tonumber(flags.lag) or 0.04,
					note = "a weapon put into a finished R6 clip (kit/anim/rearm.py): the body is the source's, both arms solved onto the hilt, the blade trailing by lag with its own momentum; Hits re-timed to the blade tip",
				}
				fs.writeFile(path, serde.encode("json", spec, true))
				return Run.chain("anim", { AnimCmd.rearmStep(name, path) }, function()
					return C.CONTENT
				end, `anim rearm: {path} - now: lune run kit anim {name} && kit anim look {name} --rig R6`)
			end
			if pos[1] == "feel" then
				-- the FEEL pass: a finished body retimed around its Hits (kit/anim/feel.py -> <Name>.feel.json)
				local name = pos[2]
				if not name or type(flags.from) ~= "string" then
					return usage(
						"anim feel: needs <Name> --from <Clip> [--anticipation 1.5] [--snap 0.55] [--hitstop 3] [--overshoot 0.18] [--settle 4] [--recovery 1.15]",
						"lune run kit anim feel ClaymoreHit1Feel --from ClaymoreHit1"
					)
				end
				if not string.match(name, "^%a[%w_]*$") then
					return usage(`anim feel: "{name}" is not a name (letters, digits, _)`, "ClaymoreHit1Feel")
				end
				Config.ensureDir(Config.path("anims"))
				local path = `{Config.path("anims")}/{name}.feel.json`
				local spec = {
					name = name,
					from = flags.from,
					hits = "auto",
					anticipation = tonumber(flags.anticipation) or 1.5,
					snap = tonumber(flags.snap) or 0.55,
					hitstop = tonumber(flags.hitstop) or 3,
					overshoot = tonumber(flags.overshoot) or 0.18,
					settle = tonumber(flags.settle) or 4,
					recovery = tonumber(flags.recovery) or 1.15,
					lag = { Head = 1 },
					note = "the feel pass (kit/anim/feel.py): anticipation hold before the strike, the strike snapped to two frames, the hit pose held (hitstop), overshoot + settle after it, a slow recovery, the head trailing a frame",
				}
				fs.writeFile(path, serde.encode("json", spec, true))
				return Run.chain(
					"anim",
					{ AnimCmd.feelStep(name, path) },
					function()
						return C.CONTENT
					end,
					`anim feel: {path} - now: lune run kit anim {name} && kit anim look {name} --rig R6 (compare with {flags.from})`
				)
			end
			if pos[1] == "fit" then
				-- an R6 gait's parameters set from a REFERENCE clip's measured curves (kit/anim/fit_r6.py)
				local name = pos[2]
				if not name or type(flags.to) ~= "string" then
					return usage(
						"anim fit: needs <Name> --to <Reference>",
						"lune run kit anim fit RunR6 --to CommunitySprint"
					)
				end
				local gaitPath = `{Config.path("anims")}/{name}.gait.json`
				if not fs.isFile(gaitPath) then
					return usage(
						`anim fit: no {gaitPath} (an R6 gait: kit anim new {name} --gait run --rig R6)`,
						`lune run kit anim new {name} --gait run --rig R6`
					)
				end
				local refNative = clipPathOf(flags.to)
				local okR, refClip = readJson(refNative)
				local refPath = if okR
						and type(refClip) == "table"
						and refClip.rig == "R6"
					then refNative
					else clipPathOf(flags.to, "R6")
				if not fs.isFile(refPath) then
					return usage(`anim fit: no R6 clip for {flags.to}`, `lune run kit anim {flags.to}`)
				end
				local argv = { "kit/anim/fit_r6.py", gaitPath, "--to", refPath, "--write" }
				if tonumber(flags.rounds) then
					table.insert(argv, "--rounds")
					table.insert(argv, tostring(flags.rounds))
				end
				return Run.chain(
					"anim",
					{
						function()
							return Run.content(
								`fit {name}`,
								Run.tool("python"),
								argv,
								{ KIT_BUILD = Config.path("build") }
							)
						end,
						AnimCmd.gaitStep(name, gaitPath),
					},
					function()
						return C.CONTENT
					end,
					`anim fit: {gaitPath} fitted to {flags.to} — now: lune run kit anim {name} && kit anim look {name} --rig R6`
				)
			end
			if pos[1] == "profile" or pos[1] == "pose-from" or pos[1] == "sil" or pos[1] == "snaps" then
				-- profile: the CRAFT numbers of an R6 clip (kit/anim/anim_profile.py: swing amplitudes, opposition / drag
				-- phases, bob, twinning, snap, the ground speed the feet do not skate at) and, with --vs, every gap to an
				-- approved reference as a sentence. pose-from: a finished R6 clip as editable key poses on the owner's
				-- rig (kit/anim/pose_from.py -> assets/animations/<Name>.pose.json)
				local function r6Of(n: string): string?
					local native = clipPathOf(n)
					local okN, decoded = readJson(native)
					if okN and type(decoded) == "table" and decoded.rig == "R6" then
						return native
					end
					local folded = clipPathOf(n, "R6")
					return if fs.isFile(folded) then folded else nil
				end
				local name = pos[2]
				if not name then
					return usage(
						`anim {pos[1]}: needs an animation name`,
						if pos[1] == "profile"
							then "lune run kit anim profile RigRun --vs CommunitySprint"
							else "lune run kit anim pose-from CommunitySprint --as RigSprint"
					)
				end
				local clipPath = r6Of(name)
				if not clipPath then
					return usage(`anim {pos[1]}: no R6 clip for {name}`, `lune run kit anim {name}`)
				end
				local argv: { string }
				if pos[1] == "snaps" then
					-- single frames that jump much further than their neighbours (kit/anim/snaps.py); report only:
					-- fix a reference on its way to the rig with `kit anim pose-from <Ref> --as <Name> --despike`
					argv = { "kit/anim/snaps.py", clipPath }
				elseif pos[1] == "sil" then
					argv = { "kit/anim/silhouette.py", clipPath }
					if type(flags.vs) == "string" then
						local other = r6Of(flags.vs)
						if not other then
							return usage(`anim sil: no R6 clip for {flags.vs}`, `lune run kit anim {flags.vs}`)
						end
						table.insert(argv, "--vs")
						table.insert(argv, other)
					end
					if flags.frames ~= nil then
						table.insert(argv, "--frames")
						table.insert(argv, tostring(flags.frames))
					end
					table.insert(argv, "--out")
					table.insert(argv, Config.build("animations") .. `/{name}.sil.png`)
				elseif pos[1] == "profile" then
					argv = { "kit/anim/anim_profile.py", clipPath }
					if type(flags.vs) == "string" then
						local other = r6Of(flags.vs)
						if not other then
							return usage(`anim profile: no R6 clip for {flags.vs}`, `lune run kit anim {flags.vs}`)
						end
						table.insert(argv, "--vs")
						table.insert(argv, other)
					end
					if flags.walkspeed ~= nil then
						table.insert(argv, "--walkspeed")
						table.insert(argv, tostring(flags.walkspeed))
					end
					table.insert(argv, "--out")
					table.insert(argv, Config.build("animations") .. `/{name}.profile.json`)
				else
					if type(flags.as) ~= "string" or not string.match(flags.as, "^%a[%w_]*$") then
						return usage(
							"anim pose-from: needs --as <Name> (letters, digits, _)",
							"lune run kit anim pose-from CommunitySprint --as RigSprint"
						)
					end
					Config.ensureDir(Config.path("anims"))
					argv = {
						"kit/anim/pose_from.py",
						clipPath,
						"--as",
						flags.as,
						"--out",
						`{Config.path("anims")}/{flags.as}.pose.json`,
					}
					if flags.every ~= nil then
						table.insert(argv, "--every")
						table.insert(argv, tostring(flags.every))
					end
					if flags.despike then
						table.insert(argv, "--despike")
					end
				end
				return Run.chain(
					"anim",
					{
						function()
							return Run.content(
								`{pos[1]} {name}`,
								Run.tool("python"),
								argv,
								{ KIT_BUILD = Config.path("build") }
							)
						end,
					},
					function()
						return C.CONTENT
					end,
					if pos[1] == "snaps"
						then `anim snaps: {name}`
						elseif
							pos[1] == "sil"
						then `anim sil: build/animations/{name}.sil.png - LOOK at it: legs under the body, arms pumping across, a clear lean, smooth arcs`
						elseif pos[1] == "profile" then `anim profile: build/animations/{name}.profile.json`
						else `anim pose-from: assets/animations/{flags.as}.pose.json - now: lune run kit anim {flags.as}`
				)
			end
			if pos[1] == "measure" then
				-- what a clip DOES in numbers (kit/anim/measure.py): per-joint curves over the cycle, ranges, phase
				-- relations; --vs <Other> = the distance between two clips (a reference and the kit's own)
				local name = pos[2]
				if not name then
					return usage(
						"anim measure: needs an animation name",
						"lune run kit anim measure CommunityWalk --vs WalkR6"
					)
				end
				local function r6ClipOf(n: string): string?
					local native = clipPathOf(n)
					local okN, decoded = readJson(native)
					if okN and type(decoded) == "table" and decoded.rig == "R6" then
						return native
					end
					local folded = clipPathOf(n, "R6")
					return if fs.isFile(folded) then folded else nil
				end
				local clipPath = r6ClipOf(name)
				if not clipPath then
					return usage(`anim measure: no R6 clip for {name}`, `lune run kit anim {name}`)
				end
				local argv = { "kit/anim/measure.py", clipPath }
				if type(flags.vs) == "string" then
					local other = r6ClipOf(flags.vs)
					if not other then
						return usage(`anim measure: no R6 clip for {flags.vs}`, `lune run kit anim {flags.vs}`)
					end
					table.insert(argv, "--vs")
					table.insert(argv, other)
				end
				table.insert(argv, "--out")
				table.insert(argv, Config.build("animations") .. `/{name}.measure.json`)
				return Run.chain("anim", {
					function()
						return Run.content(
							`measure {name}`,
							Run.tool("python"),
							argv,
							{ KIT_BUILD = Config.path("build") }
						)
					end,
				}, function()
					return C.CONTENT
				end, `anim measure: build/animations/{name}.measure.json`)
			end
			if pos[1] == "look" then
				local name = pos[2]
				if flags.stop then
					local out = Config.build("animations") .. "/look_stop.luau"
					Config.ensureDir(Config.build("animations"))
					fs.writeFile(
						out,
						table.concat({
							'local m = game:GetService("Workspace"):FindFirstChild("_kit_anim_look")',
							"if m then",
							'\tlocal s = m:FindFirstChild("Stop")',
							"\tif s then",
							"\t\ts.Value = true",
							"\tend",
							"\ttask.wait()",
							"\tm:Destroy()",
							"end",
							'return "look: removed"',
							"",
						}, "\n")
					)
					print(
						`bundled {out}: execute_luau datamodel_type="Edit" code=<its contents> removes the look avatar`
					)
					return Run.report("anim", {}, C.PASS, `anim look --stop: {out}`, "run it through the Studio MCP")
				end
				if not name then
					return usage("anim look: needs an animation name", "lune run kit anim look Walk")
				end
				local rigName = if flags.rig == "R6" then "R6" else "R15"
				do -- a clip born on R6 (a weapon move) is looked at on R6
					local okN, native = readJson(clipPathOf(name))
					if okN and type(native) == "table" and native.rig == "R6" then
						rigName = "R6"
					end
				end
				if flags.studio then
					local spot = nil
					if type(flags.at) == "string" then
						spot = {}
						for v in string.gmatch(flags.at, "[-%d%.]+") do
							table.insert(spot, tonumber(v) or 0)
						end
						if #spot ~= 3 then
							return usage(
								"anim look: --at wants x,y,z",
								"lune run kit anim look Walk --studio --at -60,0,60"
							)
						end
					end
					local out, why = AnimCmd.lookBundle(name, rigName, spot)
					if not out then
						return usage(`anim look: {why}`, `lune run kit anim {name}`)
					end
					print(
						`bundled {out} (a live loop of {name} on an {rigName} humanoid, far from the place's content)`
					)
					print("Run it with the Roblox Studio MCP tools (Studio open, Edit mode):")
					print(`  execute_luau datamodel_type="Edit" code=<the full contents of {out}>`)
					print(
						"  then select Workspace._kit_anim_look in the Explorer and press F to look (it loops until stopped)"
					)
					print("  remove it: lune run kit anim look --stop (then run that bundle the same way)")
					return Run.report(
						"anim",
						{},
						C.PASS,
						`anim look --studio: {out}`,
						`execute_luau (Edit) with the contents of {out}; look at Workspace._kit_anim_look; kit anim look --stop to remove`
					)
				end
				-- the default: Blender renders the clip (shaded body, three-quarter + side, every frame) -> gif + sheet
				local clipPath = clipPathOf(name, if rigName == "R6" then "R6" else nil)
				if rigName == "R6" and not fs.isFile(clipPath) then
					clipPath = clipPathOf(name) -- born on R6: the clip itself
				end
				if not fs.isFile(clipPath) then
					return usage(`anim look: no {clipPath}`, `lune run kit anim {name}`)
				end
				local blendPath = Config.build("animations") .. `/{name}{if rigName == "R6" then ".r6" else ""}.blend`
				-- R6 is looked at on the OWNER'S rig (assets/rigs/R6_IK.blend: the real character, its CONTROLLERS keyed
				-- by kit/anim/look_r6.py, which saves the posed rig as blendPath with the clip as an action); R15 on the
				-- kit rig's shaded body (a preview .blend)
				local ownerRig = OWNER_RIG
				local onOwnerRig = rigName == "R6" and fs.isFile(ownerRig)
				-- a clip posed ON the owner's rig (a pose source, or an edited .blend of one): its own file is rendered,
				-- IK legs, sword and all, not a re-keyed copy
				local posedBlend: string? = nil
				if onOwnerRig then
					local okC, c = readJson(clipPath)
					if
						okC
						and type(c) == "table"
						and type(c.source) == "table"
						and (c.source.kind == "pose" or c.source.posed == true)
						and type(c.source.blend) == "string"
						and fs.isFile(c.source.blend)
					then
						posedBlend = c.source.blend
					end
				end
				local steps = {}
				if not onOwnerRig then
					table.insert(
						steps,
						AnimCmd.bakeStep(name, {
							clip = clipPath,
							rig = rigName,
							save = blendPath,
							out = Config.build("animations") .. `/{name}.blendcheck.clip.json`,
						})
					)
				end
				table.insert(steps, function()
					local every = tostring(tonumber(flags.every) or 2)
					local views = tostring(tonumber(flags.views) or 2)
					local argv = if onOwnerRig
						then {
							"-b",
							posedBlend or ownerRig,
							"--disable-autoexec",
							"--python-exit-code",
							"2",
							"-P",
							"kit/anim/look_r6.py",
						}
						else {
							"-b",
							blendPath,
							"--factory-startup",
							"--python-exit-code",
							"2",
							"-P",
							"kit/anim/look.py",
						}
					for _, v in
						{
							"--",
							if rigName == "R6" then `{name}.r6` else name,
							"--out",
							Config.build("animations"),
							"--every",
							every,
							"--views",
							views,
							"--clip",
							clipPath,
						}
					do
						table.insert(argv, v)
					end
					if posedBlend then
						table.insert(argv, "--posed")
					end
					if flags.arcs and rigName == "R6" then
						table.insert(argv, "--arcs") -- the hands' + blade tip's trails, a tick per frame (AAA plan #3)
					end
					if flags.fp and rigName == "R6" then
						table.insert(argv, "--fp") -- first person: the eye's view, only the arms + weapon (Sample Game)
					end
					return Run.content(`look {name}`, Run.tool("blender"), argv, { KIT_BUILD = Config.path("build") })
				end)
				table.insert(steps, function()
					-- a posed look already rendered every Nth frame: its sheet shows each of them
					local every = if posedBlend then "1" else tostring(tonumber(flags.every) or 2)
					local dir = Config.build("animations") .. `/{name}{if rigName == "R6" then ".r6" else ""}.look`
					return Run.content(
						`look sheet {name}`,
						Run.tool("python"),
						{ "kit/anim/look_sheet.py", dir, "--every", every }
					)
				end)
				local lookCode = Run.chain(
					"anim",
					steps,
					function()
						return C.CONTENT
					end,
					`anim look: build/animations/{name}{if rigName == "R6" then ".r6" else ""}.look.gif (moving) + .look.png (sheet) — LOOK at them`
				)
				if lookCode == C.PASS then
					local stem = `{name}{if rigName == "R6" then ".r6" else ""}`
					Run.out(
						`LOOK: {Config.build("animations")}/ - {stem}.look.gif (the move in real time) + {stem}.look.png (one frame in every {tostring(
							tonumber(flags.every) or 2
						)}, small); its key poses large, beside their reference: lune run kit anim sheet {name}`
					)
				end
				return lookCode
			end
			if pos[1] == "play" then
				local name = pos[2]
				if not name then
					return usage("anim play: needs an animation name", "lune run kit anim play Slash")
				end
				local rigName = if flags.rig == "R6" then "R6" else "R15"
				local out, why = AnimCmd.playBundle(name, rigName)
				if not out then
					return usage(`anim play: {why}`, `lune run kit anim {name}`)
				end
				print(`bundled {out} (plays {name} on an {rigName} humanoid, stepped frame by frame in Edit mode)\n`)
				if flags.run then
					-- the kit runs the probe itself through StudioMCP (kit/lib/mcp.luau), in the Studio NAMED by --studio
					-- (never a shared one by accident), saves what it returns and records it - the probe never passes
					-- through an agent's context (it is 100-300 KB of Luau)
					local studioId = flags.studio
					if type(studioId) ~= "string" then
						return usage(
							"anim play --run: needs --studio <id> (lune run kit playtest list shows them; never a shared one)",
							`lune run kit anim play {name} --rig R6 --run --studio <id>`
						)
					end
					local Mcp = require("../lib/mcp")
					local studio, cerr = Mcp.connect()
					if not studio then
						return Run.report("anim", {}, C.PLAYTEST, `anim play: {cerr}`, "is Roblox Studio running?")
					end
					local okE, result = studio:call(
						"execute_luau",
						{ code = fs.readFile(out), datamodel_type = "Edit", studio_id = studioId },
						300
					)
					studio:close()
					if not okE or type(result) ~= "string" then
						return Run.report(
							"anim",
							{},
							C.PLAYTEST,
							`anim play: Studio did not run the probe ({result})`,
							"check the Studio id"
						)
					end
					local saved = `{Config.build("animations")}/{name}.play.json`
					fs.writeFile(saved, (string.gsub(result, "^%s+", "")))
					return AnimCmd.record(name, saved)
				end
				print("Run it with the Roblox Studio MCP tools (Studio open, Edit mode):")
				print(`  1. execute_luau     datamodel_type="Edit"  code=<the full contents of {out}>`)
				print(`  2. save the JSON string it returns to {Config.build("animations")}/{name}.play.json`)
				print(`  3. lune run kit anim record {name} {Config.build("animations")}/{name}.play.json`)
				return Run.report(
					"anim",
					{},
					C.PASS,
					`anim play: {out}`,
					`run steps 1-3 above, then: lune run kit anim record {name} {Config.build("animations")}/{name}.play.json`
				)
			end
			if pos[1] == "record" then
				local name, file = pos[2], pos[3]
				if not name or not file or not fs.isFile(file) then
					return usage(
						"anim record: needs the animation name and the saved probe result",
						"lune run kit anim record Slash build/animations/Slash.play.json"
					)
				end
				return AnimCmd.record(name, file)
			end
			if pos[1] == "blend" then
				local name = pos[2]
				if not name then
					return usage("anim blend: needs an animation name", "lune run kit anim blend Slash")
				end
				-- --preview: the .blend goes to build/ to LOOK at (the source stays what it is)
				local blendPath = if flags.preview
					then Config.build("animations") .. `/{name}.blend`
					else `{Config.path("anims")}/{name}.blend`
				if fs.isFile(blendPath) and not flags.force and not flags.preview then
					return usage(
						`anim blend: {blendPath} exists (an animator may have edited it) — add --force to replace it`,
						`lune run kit anim blend {name} --force`
					)
				end
				local specPath = `{Config.path("anims")}/{name}.json`
				local gaitPath = `{Config.path("anims")}/{name}.gait.json`
				local steps = {}
				if fs.isFile(specPath) then
					table.insert(steps, AnimCmd.bakeStep(name, { spec = specPath, save = blendPath }))
				elseif fs.isFile(gaitPath) then
					-- a generated gait: its clip, keyed frame by frame on the rig (the clip itself is left alone)
					table.insert(steps, AnimCmd.gaitStep(name, gaitPath))
					table.insert(
						steps,
						AnimCmd.bakeStep(name, {
							clip = clipPathOf(name),
							save = blendPath,
							out = Config.build("animations") .. `/{name}.blendcheck.clip.json`,
						})
					)
				else
					return usage(`anim blend: no {specPath} and no {gaitPath}`, `lune run kit new anim {name}`)
				end
				return Run.chain(
					"anim",
					steps,
					function()
						return C.CONTENT
					end,
					if flags.preview
						then `anim blend: {blendPath} — open it in Blender to look (a preview; the source is unchanged)`
						else `anim blend: {blendPath} — open it in Blender; from now on it is the source (the .json / .gait.json is metadata)`
				)
			end
			if pos[1] == "bake" then
				local name = pos[2]
				-- a bake writes the clip: a build of its dossier (its clock and route: kit/lib/prebuild.luau)
				local held = if name then require("../lib/prebuild").held("anim", name) else nil
				if held then
					return held
				end
				if not name then
					return usage("anim bake: needs an animation name", "lune run kit anim bake Slash")
				end
				if not fs.isFile(`{Config.path("anims")}/{name}.blend`) then
					return usage(`anim bake: no {Config.path("anims")}/{name}.blend`, `lune run kit anim blend {name}`)
				end
				local baked = Run.chain("anim", { AnimCmd.bakeStep(name) }, function()
					return C.CONTENT
				end, `anim bake: build/animations/{name}.clip.json`)
				if baked == C.PASS then
					-- a bake writes the clip only; the build that follows writes its R6 fold and renders its sheet (a
					-- sheet from the fold as it stands would show the motion from BEFORE this bake)
					Run.out(
						`LOOK: {AnimCmd.sheetDir(name)}/ - {name} is baked; its sheet (the key poses large, beside their reference) is rendered by the build that follows: lune run kit anim {name}`
					)
				end
				return baked
			end
			local only = if #pos > 0 then pos else nil
			-- --no-look: build without rendering the named moves' sheets (the LOOK lines then say they are stale)
			local noLook = flags["no-look"] ~= nil
			if only then -- (each named clip's dossier: its clock and its route - kit/lib/prebuild.luau)
				for _, n in only do
					local held = require("../lib/prebuild").held("anim", n)
					if held then
						return held
					end
				end
			else -- (every clip: the dossiers past their budget or made a new way)
				local held = require("../lib/prebuild").heldAll("anim", Config.path("anims") .. "/dossiers")
				if held then
					return held
				end
			end
			local plan = {}
			local sources = AnimCmd.sources(only)
			if only then -- a named re-arm / feel / warp whose source was never built: build that source too (its own step)
				local extra = {}
				for _, src in sources do
					local dep = src.rearm or src.feel or src.warp
					local okD, spec = false, nil
					if dep then
						okD, spec = readJson(dep) -- (an if-expression keeps ONE value: spec was always nil)
					end
					local from = okD and type(spec) == "table" and spec.from
					if
						type(from) == "string"
						and not fs.isFile(clipPathOf(from, "R6"))
						and not fs.isFile(clipPathOf(from))
						and not table.find(only, from)
						and not table.find(extra, from)
					then
						table.insert(extra, from)
					end
				end
				if #extra > 0 then
					only = table.clone(only)
					for _, n in extra do
						table.insert(only, n)
					end
					sources = AnimCmd.sources(only)
				end
			end
			-- POSES FIRST (AnimCmd.blockingLock): a strike move or a sword pick made after the rule is not built
			-- unless the owner's yes stands for its key poses; every move made before it builds as it always did
			do
				local newMoves = AnimCmd.lockPairs(sources)
				local stop = AnimCmd.designLock(newMoves) or AnimCmd.blockingLock(newMoves) -- (the set, then the move)
				if stop then
					return Run.report("anim", {}, C.CONTENT, stop.summary, stop.next_action)
				end
			end
			-- a re-arm / feel / warp reads its SOURCE clip's R6 fold, which the compile writes: on an empty build
			-- (a fresh checkout, kit prove) the first re-arm failed. When a source's R6 clip is missing, compile the
			-- base clips first (the final compile below rewrites everything, so a warm build is unchanged)
			local bases, needBases = {}, false
			for _, src in sources do
				local dep = src.rearm or src.feel or src.warp
				if dep then
					local okD, spec = readJson(dep)
					local from = okD and type(spec) == "table" and spec.from
					if
						type(from) == "string"
						and not fs.isFile(clipPathOf(from, "R6"))
						and not fs.isFile(clipPathOf(from))
					then
						needBases = true
						if not table.find(bases, from) then
							table.insert(bases, from) -- `kit anim <ReArmed>` alone: its source too
						end
					end
				else
					table.insert(bases, src.name)
				end
			end
			local basesQueued = false
			-- THE BASE SOURCES AT ONCE (PARALLAX_FINAL_CLOSURE_SPEC A5, 2026-11-22): each base step (blend / gait / move /
			-- import / dossier / pose) writes its own clip and reads no other clip, so a run of them goes as one batch,
			-- PARALLAX_ANIM_JOBS at a time (default 12; 1 = one at a time), the Blender ones (.blend bakes, pose rigs) at
			-- most PARALLAX_ANIM_BLENDER_JOBS (4). A batch starts when the chain reaches it (Run.parallel lazy), so the
			-- base compile and the derived steps (re-arm / feel / warp: they read compiled folds, and each other) stay
			-- exactly where they were, one at a time
			local jobs = tonumber(process.env.PARALLAX_ANIM_JOBS or "") or 12
			local blenderJobs = tonumber(process.env.PARALLAX_ANIM_BLENDER_JOBS or "") or 4
			local batch: { () -> Run.Step } = {}
			local kinds: { string } = {}
			local function flushBatch()
				if #batch == 0 then
					return
				end
				local k = kinds
				for _, step in
					Run.parallel(batch, math.max(1, jobs), function(i)
						return k[i]
					end, { blender = math.max(1, blenderJobs) }, true)
				do
					table.insert(plan, step)
				end
				batch, kinds = {}, {}
			end
			for _, src in sources do
				if needBases and not basesQueued and (src.rearm or src.feel or src.warp) then
					basesQueued = true
					flushBatch()
					table.insert(plan, function()
						local step = AnimCmd.compile(true, bases)
						return step
					end)
				end
				if src.blend then
					table.insert(batch, AnimCmd.bakeStep(src.name))
					table.insert(kinds, "blender")
				elseif src.gait then
					table.insert(batch, AnimCmd.gaitStep(src.name, src.gait))
					table.insert(kinds, "plain")
				elseif src.move then
					table.insert(batch, AnimCmd.moveStep(src.name, src.move))
					table.insert(kinds, "plain")
				elseif src.import then
					table.insert(batch, AnimCmd.importStep(src.name, src.import))
					table.insert(kinds, "plain")
				elseif src.rearm then
					flushBatch()
					table.insert(plan, AnimCmd.rearmStep(src.name, src.rearm))
				elseif src.feel then
					flushBatch()
					table.insert(plan, AnimCmd.feelStep(src.name, src.feel))
				elseif src.warp then
					flushBatch()
					table.insert(plan, AnimCmd.warpStep(src.name, src.warp))
				elseif src.dossier then
					table.insert(batch, AnimCmd.dossierStep(src.name, src.dossier))
					table.insert(kinds, "plain")
				elseif src.pose then
					table.insert(batch, AnimCmd.poseStep(src.name, src.pose))
					table.insert(kinds, "blender")
				end
			end
			flushBatch()
			local names = {}
			table.insert(plan, function()
				local step, built = AnimCmd.compile(true, only)
				names = built
				return step
			end)
			table.insert(plan, function()
				-- one strip + one set of metrics per clip (the R15 model and the R6 model share it). The clips at once,
				-- PARALLAX_ANIM_JOBS at a time (each writes only its own strip / metrics; A5): the first failure IN NAME
				-- ORDER is the one reported, as when they ran one after another
				local summaries = {}
				local function perClip(n: string): Run.Step
					local clipPath = clipPathOf(n)
					local strip =
						Run.content(`strip {n}`, Run.tool("python"), { "kit/anim/strip.py", clipPath, "--gif" })
					if not strip.ok then
						return strip
					end
					local motion = motionStep(n, clipPath)
					if not motion.ok and AnimCmd.quarantined(n) then
						print(`  [warn] {n}: quarantined by --profile {Config.profile()} - its motion gate failed`)
					elseif not motion.ok then
						return motion
					end
					if fs.isFile(clipPathOf(n, "R6")) then
						-- the R6 version gets its own strip (a straight-legged fold reads differently) and gates
						local strip6 = Run.content(
							`strip {n} (R6)`,
							Run.tool("python"),
							{ "kit/anim/strip.py", clipPathOf(n, "R6"), "--gif" }
						)
						if not strip6.ok then
							return strip6
						end
						local r6 = motionStep(n, clipPathOf(n, "R6"), `motion {n} (R6)`)
						if not r6.ok and AnimCmd.quarantined(n) then
							print(
								`  [warn] {n} (R6): quarantined by --profile {Config.profile()} - its motion gate failed`
							)
						elseif not r6.ok then
							return r6
						end
					end
					-- a move whose blocking the owner approved: the built clip must keep those poses
					local kept = AnimCmd.keptStep(n)
					if kept and not kept.ok then
						return kept
					end
					return {
						name = `clip {n}`,
						cmd = "(in-process)",
						exit = 0,
						ok = true,
						tail = "",
						result = { summary = tostring(motion.result and motion.result.summary) },
					} :: any
				end
				local makes: { () -> Run.Step } = {}
				for _, n in names do
					if string.sub(n, -4) ~= "_R15" then
						table.insert(makes, function()
							return perClip(n)
						end)
					end
				end
				for _, wait in Run.parallel(makes, math.max(1, jobs)) do
					local step = wait()
					if not step.ok then
						return step
					end
					table.insert(summaries, tostring(step.result and step.result.summary))
				end
				return Run.step("strips + motion gates", true, "", {
					summary = if #summaries > 0 then table.concat(summaries, " | ") else "nothing to draw",
				})
			end)
			table.insert(plan, Steps.build)
			table.insert(plan, function()
				return AnimCmd.inspect(names, Config.build("place.rbxlx"))
			end)
			-- LOOK (the studio route's A0): a build that names its moves renders each one's sheet - the key poses large on
			-- the owner's rig beside their reference frames, the 12-a-second strips - and the build's LAST lines name
			-- them. A sheet that fails never fails the build (its line says why)
			local lookLines: { string } = {}
			table.insert(plan, function()
				local okL, lines = pcall(AnimCmd.buildLooks, names, only ~= nil, noLook)
				lookLines = if okL
					then lines
					else { `LOOK: not made ({tostring(lines)}): lune run kit anim sheet <Name>` }
				local first = string.match(lookLines[1] or "", "^LOOK: (%S+%.sheet)/")
				return Run.step("look", true, "", {
					summary = `{#lookLines} LOOK line(s), the build's last`,
					next_action = if first
						then `look at {first}/pose_sheet.png, then its keys/key_*.png at full size (the LOOK line(s) below)`
						else nil,
				})
			end)
			local code = Run.chain(
				"anim",
				plan,
				function(step)
					return if step.name == "rojo build" then C.BUILD else C.CONTENT
				end,
				`anim: {#sources} animation(s) built — its strip {Config.build("animations")}/<Name>.png + <Name>.metrics.json; the LOOK line(s) below name each move's sheet`
			)
			if code == C.PASS then
				for _, line in lookLines do
					Run.out(line)
				end
			end
			return code
		end
	)
end

return AnimCmd

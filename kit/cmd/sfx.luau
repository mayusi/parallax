-- sfx.luau — the SFX pipeline's sub-commands (`kit sfx <sub> ...`); `kit sfx <name|all>` itself (render + gate) stays
-- in content.luau and hands any word listed here to this module. Every sub-command is one Python tool under
-- kit/audio/ that prints a JSON verdict; the plan and the ideas behind them: board/plans/archive/2026-10-12-sfx-pipeline-v2.md.
local Config = require("../lib/config")
local Run = require("../lib/run")

local Sfx = {}

type Sub = { script: string, usage: string, about: string }

local SUBS: { [string]: Sub } = {
	sheet = {
		script = "kit/audio/sheet.py",
		usage = "sfx sheet <name|all|file> [--ref <file|name>] [--loop]",
		about = "the SOUND SHEET: waveforms of every take, spectrogram, loudness + brightness over time, ears v2; with --ref the differences in words",
	},
	set = {
		script = "kit/audio/sets.py",
		usage = "sfx set <set|all>",
		about = "render a sound SET (assets/sounds/sets/<set>.json: shared DNA + members + weights) and gate it as one family",
	},
	listen = {
		script = "kit/audio/booth.py",
		usage = "sfx listen <name ...> [--ref(s) <file|name>] [--blind] [--port 8791]",
		about = "the LISTENING BOOTH on localhost: the owner plays takes beside the reference and scores them -> <name>.verdict.json",
	},
	av = {
		script = "kit/audio/av.py",
		usage = "sfx av <name> --video <file> [--at <seconds>]",
		about = "put a sound on a picture (VFX reel, anim strip GIF, gameplay clip) -> build/sounds/av/<name>.mp4 to judge it in context",
	},
	match = {
		script = "kit/audio/match.py",
		usage = "sfx match <name> --to <file|name> [--iters 60] [--write]",
		about = "fit the recipe's numbers to a reference by measured ears (gains, decays, cutoffs, pitch)",
	},
	find = {
		script = "kit/audio/sfxlib.py",
		usage = 'sfx find "<words>" [--n 12] [--describe]  |  sfx index <dir> [--licence CC0]',
		about = "search the local indexed library of real recordings (or index a folder of them)",
	},
	clap = {
		script = "kit/audio/clap.py",
		usage = "sfx clap index  |  sfx clap eval",
		about = 'embed the sound library once for search by DESCRIPTION (LAION CLAP: kit vision setup clap-general first) - then: sfx find "<a description>" --describe',
	},
	index = {
		script = "kit/audio/sfxlib.py",
		usage = "sfx index <dir> --licence <CC0|royalty-free|own> [--source <name>]",
		about = "cut a folder of recordings into single events, measure them and add them to the local library",
	},
	direction = {
		script = "kit/direction.py",
		usage = "sfx direction <Piece> [--new]",
		about = "DIRECTION before an original sound world: intent, the one idea, >= 6 references (take / leave), 3 pillars, bans, 3 directions each with a sketch -> <sounds>/direction/<Piece>.md; draft -> ready (play the owner the sketches) -> picked",
	},
	soundscript = {
		script = "kit/audio/soundscript.py",
		usage = "sfx soundscript [--game <Name>] [--order A,B,C]",
		about = "the world's SOUND SCRIPT (the audio director's colour script): each place's picked (or recommended) sketch in journey order - loudness, density, brightness, how long its space rings, spectrograms; names neighbours with no change of dynamics",
	},
	board = {
		script = "kit/direction_page.py",
		usage = "sfx board [--game <Name>]",
		about = "the owner's REVIEW BOARD: every sound direction doc of the game as one page (the one idea, three sketches to play side by side, axes, pillars, bans, the pick)",
	},
	sketch = {
		script = "kit/audio/sketch.py",
		usage = "sfx sketch <scene.json> [--out <file.ogg>]",
		about = "a SONIC DIRECTION sketch: beds, one-shots and recurring events on a timeline, placed in stereo and distance, played in ONE convolution space (an impulse response from size / decay / brightness) -> a stereo .ogg + its spectrogram",
	},
	identity = {
		script = "kit/audio/identity.py",
		usage = "sfx identity <identity> [--check <name|set ...>]",
		about = "a game's SONIC IDENTITY (assets/sounds/identities/<id>.json): gate sounds against it, or derive it from references",
	},
	modal = {
		script = "kit/audio/modal.py",
		usage = "sfx modal <file> [--modes 24] [--as <name>]",
		about = "extract the resonant modes of a recorded hit -> a modal layer that re-strikes it with endless variation",
	},
	mix = {
		script = "kit/audio/mix.py",
		usage = "sfx mix <events.json> [--seconds 30]",
		about = "re-render a playtest's sound log through the bus graph offline: density, masking, fatigue, a real fight mix",
	},
	plan = {
		script = "kit/audio/plan.py",
		usage = "sfx plan <set>",
		about = "ONE sound set's route stage by stage from its own files - refs, identity, design, match, sheet, booth, av, runtime, upload: done / partly / to do, the next stage's commands (<= 5)",
	},
	ambience = {
		script = "kit/audio/ambience.py",
		usage = "sfx ambience <World>",
		about = "a world's AMBIENCE: zones from its own blueprint (water, forests, stone clusters, open) x the beds + scatter of assets/sounds/ambience/<World>.json -> src/shared/<World>Ambience.json (kit Ambience plays it) + the zone map",
	},
	catalog = {
		script = "kit/audio/catalog.py",
		usage = "sfx catalog",
		about = "compile assets/sounds/events.json (+ uploaded ids) into src/kit/SfxCatalog.luau for the Sfx runtime",
	},
}

function Sfx.has(word: string?): boolean
	return word ~= nil and SUBS[word] ~= nil
end

function Sfx.help(): string
	local lines = {}
	for _, name in
		{
			"plan",
			"sheet",
			"set",
			"listen",
			"av",
			"match",
			"find",
			"index",
			"identity",
			"modal",
			"mix",
			"ambience",
			"catalog",
		}
	do
		table.insert(lines, string.format("    %-62s %s", SUBS[name].usage, SUBS[name].about))
	end
	return table.concat(lines, "\n")
end

function Sfx.run(args: { string }): number
	local word = args[1]
	local sub = SUBS[word]
	local rest = { word }
	for i = 2, #args do
		table.insert(rest, args[i])
	end
	-- the tool gets the sub-command word first only when two words share a script (find / index)
	local toolArgs = { sub.script }
	local shared = word == "find" or word == "index"
	for i, a in rest do
		if i > 1 or shared then
			table.insert(toolArgs, a)
		end
	end
	-- inside a game (--game / games/.active) a set lives in the game's own folders
	if word == "set" and Config.root() ~= "" and not table.find(toolArgs, "--sets") then
		for _, a in { "--sets", Config.path("sounds") .. "/sets", "--out", Config.build("sounds") } do
			table.insert(toolArgs, a)
		end
	end
	-- the quality lock: a set made after the locks renders on the owner's chosen reference
	if word == "set" then
		-- the names exactly as sets.py reads them: --sets / --out take a value, everything else is a set (or a file)
		local names, setsDir = {}, nil
		local i = 2
		while i <= #args do
			if args[i] == "--sets" or args[i] == "--out" then
				if args[i] == "--sets" then
					setsDir = args[i + 1]
				end
				i += 2
			else
				table.insert(names, args[i])
				i += 1
			end
		end
		local locked = require("../lib/lanelocks").sfx(names, "sets", nil, setsDir)
		if #locked > 0 then
			print(table.concat(locked, "\n"))
			return Run.report(
				"sfx-set",
				{},
				Run.CODES.CONTENT,
				`sfx set: {#locked} new set(s) without the owner's reference (quality lock)`,
				locked[1]
			)
		end
		for _, n in names do -- (each set's clock and route, found by its file: kit/lib/prebuild.luau)
			local file = if string.sub(n, -5) == ".json"
				then n
				else `{setsDir or (Config.path("sounds") .. "/sets")}/{n}.json`
			local held = require("../lib/prebuild").held("sfx", file)
			if held then
				return held
			end
		end
		if #names == 0 then -- (every set: the ones past their budget or made a new way)
			local held = require("../lib/prebuild").heldAll("sfx", setsDir or (Config.path("sounds") .. "/sets"))
			if held then
				return held
			end
		end
	end
	if word == "soundscript" then
		local game = Config.game()
		if not game then
			return Run.report(
				"sfx-soundscript",
				{},
				Run.CODES.USAGE,
				"sfx soundscript: which game?",
				"lune run kit sfx soundscript --game <Name>"
			)
		end
		toolArgs = { "kit/audio/soundscript.py", game :: string }
		for i = 2, #args do
			table.insert(toolArgs, args[i])
		end
	end
	if word == "board" then
		local game = Config.game()
		if not game then
			return Run.report(
				"sfx-board",
				{},
				Run.CODES.USAGE,
				"sfx board: which game?",
				"lune run kit sfx board --game <Name>"
			)
		end
		toolArgs = { "kit/direction_page.py", game :: string, "--lane", "sfx" }
	end
	if word == "direction" then
		local name = args[2]
		if not name or string.sub(name, 1, 2) == "--" then
			return Run.report(
				"sfx-direction",
				{},
				Run.CODES.USAGE,
				"sfx direction: which piece?",
				"lune run kit sfx direction <Piece> [--new]"
			)
		end
		toolArgs = {
			"kit/direction.py",
			if table.find(args, "--new") then "new" else "check",
			`{Config.path("sounds")}/direction/{name}.md`,
			"--lane",
			"sfx",
			"--name",
			name,
		}
	end
	local step = Run.content(`sfx {word}`, Run.tool("python"), toolArgs)
	local r = step.result or {}
	return Run.report(
		`sfx-{word}`,
		{ step },
		if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
		if type(r.summary) == "string" then `sfx {word}: {r.summary}` else `sfx {word}: crashed`,
		if type(r.next_action) == "string" then r.next_action else "read the error above"
	)
end

return Sfx

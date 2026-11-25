-- judge.luau — models are checked by an INDEPENDENT reviewer, never by the model that built them.
--   kit judge <asset>                     THE VERIFIER (kit/blender/verifier.py): per traced view the SAME crop of the
--                                         reference and the render side by side, the worst places at 1:1, the owner's
--                                         words first -> build/judge/<asset>/verify/PROMPT.md for a fresh verifier: ONE
--                                         difference per image, ONE edit, no score; ten rounds per attempt, then STOP
--   kit judge <asset> --record [answer]   keep the verifier's round in assets/models/<asset>.verify.json
--   kit judge <asset> --score [--record]  the old SCORING judge (sheet + rubric -> <asset>.judge.json): its numbers
--                                         never predicted the owner (r 0.60); kept for the record and `kit verify`
--   kit judge <asset> --pair [[A] B] [--judges N]  PAIRWISE: two builds side by side (six views, the brief's game
--                                         camera, every region beside its reference crop), sides shuffled, the key
--                                         kept apart: build/judge/<asset>/pair/judge_<n>/ (kit/blender/judge_pair.py)
--   kit judge <asset> --tally [answer.json ...]   the judges' picks -> win / loss / tie per item, where they disagree
-- The reviewer is a fresh context: a subagent, another session, another model. Its answer is tied to the build it saw.
local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")

local Config = require("../lib/config")
local Owner = require("../lib/owner")
local Run = require("../lib/run")
local VisionWorker = require("../lib/visionworker")

local Judge = {}

Judge.BARS = { prop = 55, hero = 75, aaa = 88 }

-- verify gate: every hero / aaa build needs a verdict for THIS build at or above its bar.
-- -> list of problems ("asset: why — what to run")
function Judge.problems(): { string }
	local out = {}
	local dir = Config.build("models")
	if not fs.isDir(dir) then
		return out
	end
	for _, file in fs.readDir(dir) do
		local asset = string.match(file, "^(.+)%.manifest%.json$")
		if not asset or not fs.isFile(`{Config.path("models")}/build_{asset}.py`) then
			continue
		end
		local ok, m = pcall(serde.decode, "json" :: any, fs.readFile(`{dir}/{file}`))
		-- (a PRIVATE asset or a MASTER never enters the game as built: judging it is the builder's business, not the
		-- game's models being in order)
		if not ok or (m.tier ~= "hero" and m.tier ~= "aaa") or m.private == true or m.stage == "master" then
			continue
		end
		local bar = Judge.BARS[m.tier]
		local path = `{Config.path("models")}/{asset}.judge.json`
		if not fs.isFile(path) then
			table.insert(out, `{asset} ({m.tier}) has never been judged — run: lune run kit judge {asset}`)
			continue
		end
		local okJ, j = pcall(serde.decode, "json" :: any, fs.readFile(path))
		if not okJ then
			table.insert(out, `{asset}: {path} is unreadable — run: lune run kit judge {asset}`)
		elseif j.build == nil then -- (only a pairwise tally so far: no absolute verdict yet)
			table.insert(out, `{asset} ({m.tier}) has never been judged — run: lune run kit judge {asset}`)
		elseif j.build ~= m.build_id then
			table.insert(
				out,
				`{asset}: the verdict is for build {j.build}, not the current {m.build_id} — run: lune run kit judge {asset}`
			)
		elseif (tonumber(j.score) or 0) < bar then
			table.insert(
				out,
				`{asset}: judged {j.score} < {m.tier} bar {bar} — fix the judge's gaps in {path}, rebuild, re-judge`
			)
		end
	end
	return out
end

function Judge.register(Cli: any)
	Cli.command(
		"3d",
		"judge",
		'judge <asset> [--record [answer.json]] [--score [--structural "<what changed>"]] [--pair [[A] B] [--judges N]] [--tally [answers.json ...]]',
		"the VERIFIER: per view the same crop of reference and model, one difference per image + ONE edit for a fresh reviewer, the owner's words first, no score, ten rounds then the owner (--record keeps the round); --score: the old scoring judge; --pair / --tally: blind A-or-B judges",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			local asset = args[1]
			if not asset then
				return Run.report(
					"judge",
					{},
					Run.CODES.USAGE,
					"judge: needs an asset name",
					"lune run kit judge orbital_sniper"
				)
			end
			-- the values after a flag, up to the next flag (--pair A B, --tally a.json b.json)
			local function after(flag: string): { string }?
				local at = table.find(rawArgs, flag)
				if not at then
					return nil
				end
				local vals = {}
				for j = at + 1, #rawArgs do
					if string.sub(rawArgs[j], 1, 2) == "--" then
						break
					end
					table.insert(vals, rawArgs[j])
				end
				return vals
			end
			local pairArgs, tallyArgs = after("--pair"), after("--tally")
			local py, label
			if pairArgs then
				py = { "kit/blender/judge_pair.py", "pair", asset, table.unpack(pairArgs, 1, math.min(#pairArgs, 2)) }
				if type(flags.judges) == "string" then
					table.insert(py, "--judges")
					table.insert(py, flags.judges)
				end
				label = `judge-pair-{asset}`
			elseif tallyArgs then
				py = { "kit/blender/judge_pair.py", "tally", asset, table.unpack(tallyArgs) }
				label = `judge-tally-{asset}`
			elseif not flags.score then
				-- THE VERIFIER (the default, mission 01-3d 5.10): the same crop of reference and model per view, ONE
				-- difference per image, ONE edit, the owner's words first, no score, ten rounds per attempt
				py = { "kit/blender/verifier.py", if flags.record then "record" else "packet", asset }
				if type(flags.record) == "string" then
					table.insert(py, flags.record)
				end
				label = `judge-verify-{asset}`
			else
				-- (--score: the old scoring judge — its numbers never predicted the owner; kept for the record)
				py = { "kit/blender/judge.py", if flags.record then "record" else "packet", asset }
				if not flags.record and type(flags.structural) == "string" then
					-- (after a stall: the round names the change in METHOD that earns it, and asks a panel of 3)
					table.insert(py, "--structural")
					table.insert(py, flags.structural)
				end
				if type(flags.record) == "string" then
					table.insert(py, flags.record)
				end
				label = `judge-{asset}`
			end
			local step = Run.content("judge", Run.tool("python"), py)
			local r = step.result or {}
			return Run.report(
				label,
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
				r.summary or "judge: crashed",
				r.next_action or "read the error above"
			)
		end
	)
	Cli.command(
		"3d",
		"schematic",
		"schematic <asset>",
		"blueprint sheets for a mechanism (a.joint): orthographic + section + dimensions, exploded + motion",
		function(rawArgs)
			local args = Cli.parse(rawArgs)
			local asset = args[1]
			if not asset then
				return Run.report(
					"schematic",
					{},
					Run.CODES.USAGE,
					"schematic: needs an asset name",
					"lune run kit schematic pistol"
				)
			end
			local step = Run.content("schematic", Run.tool("python"), { "kit/blender/schematic.py", asset })
			local r = step.result or {}
			return Run.report(
				`schematic-{asset}`,
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
				r.summary or "schematic: crashed",
				r.next_action or "read the error above"
			)
		end
	)
	Cli.command(
		"3d",
		"trace",
		"trace <image> --name <outline> [--box x0,y0,x1,y1] [--front left|right] [--bg auto|dark|light] [--cutout]"
			.. ' [--part-point name=x,y] [--part-box name=x0,y0,x1,y1] [--part-text name="what it is"[#k]]',
		"TRACE a reference view into the exact outline a build extrudes (assets/models/<name>.trace.json + preview);"
			.. " every part's mask judged (part_quality: fills its box, one area with another, a dropped piece, a"
			.. " plain box); --part-text = SAM 3 by words (the TRELLIS.2 environment)",
		function(rawArgs)
			-- what it cannot run without is a usage error, said plainly (never "crashed"): a picture that exists, a name
			local picture, named = false, false
			for i, a in rawArgs do
				local ext = string.lower(string.match(a, "%.(%w+)$") or "")
				local image = ext == "png" or ext == "jpg" or ext == "jpeg" or ext == "webp" or ext == "bmp"
				picture = picture or (image and fs.isFile(a))
				named = named or (a == "--name" and rawArgs[i + 1] ~= nil and string.sub(rawArgs[i + 1], 1, 2) ~= "--")
			end
			if not picture or not named then
				return Run.report(
					"trace",
					{},
					Run.CODES.USAGE,
					if not picture
						then "trace: needs the picture to trace (a .png / .jpg / .webp that exists)"
						else "trace: needs --name <outline> (the trace is saved as assets/models/<outline>.trace.json)",
					"run: lune run kit trace refs/<picture>.png --name <outline> [--front left|right] [--ortho] [--cutout]  (every option: lune run kit help)"
				)
			end
			local step = Run.content("trace", Run.tool("python"), { "kit/blender/trace.py", table.unpack(rawArgs) })
			local r = step.result or {}
			return Run.report(
				"trace",
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
				r.summary or "trace: stopped without a verdict",
				r.next_action or "read the error above"
			)
		end
	)
	Cli.command(
		"3d",
		"vision",
		'vision setup|doctor | serve [--idle s] [--stop] [--status] | edges|cutout|depth <image> | mask <image> --point x,y | similar|differ <a> <b> | view <image> | relief <cut-out.png> | parts <image> --text <thing> | albedo <image> | vectorize <image> [--color] [--speckle n] [-o out.svg] | upscale <image> [--x 2|4] [--fast] [-o out.png] | light <picture> [-o out.exr] | concept "<description>" [--sheet turnaround|views|single] [--seed N] | angle <image> --azimuth <deg> --elevation <deg> [--distance near|mid|far] | edit <image> --prompt <instruction>',
		"local vision models (vetted + pinned, offline): edges, cutout, ONE part's mask, depth, look-alike, where two differ, view; an ornament's relief from its picture; every match of a text prompt (SAM 3); colour without its lighting + roughness + metalness (Marigold-IID); lines to SVG curves (vtracer); a picture 2x / 4x bigger (Real-ESRGAN); a picture's lighting as an HDR map + facts (DiffusionLight-Turbo); a concept picture or turnaround sheet from words (FLUX.2 klein 4B); the same object from another camera, or a picture edited by an instruction (Qwen-Image-Edit-2511: LOW TRUST, generated — look, never measure)",
		function(rawArgs)
			local sub = rawArgs[1]
			local step
			if sub == "serve" then -- (the WARM worker: kit/vision/run.py's models loaded once, every call in-process)
				if table.find(rawArgs, "--stop") then
					local stopped = VisionWorker.stop()
					return Run.report(
						"vision",
						{},
						Run.CODES.PASS,
						if stopped then "vision serve: the warm worker stopped" else "vision serve: none was running",
						"none — proceed (calls run cold until `lune run kit vision serve` again)"
					)
				end
				if table.find(rawArgs, "--status") then
					local st = VisionWorker.status()
					return Run.report(
						"vision",
						{},
						Run.CODES.PASS,
						if st
							then `vision serve: warm (pid {st.pid}, {st.calls} call(s), loaded: {table.concat(
								st.loaded or {},
								", "
							)})`
							else "vision serve: none running (calls run cold)",
						if st then "none — proceed" else "lune run kit vision serve"
					)
				end
				local i = table.find(rawArgs, "--idle")
				local idle = if i then tonumber(rawArgs[i + 1]) else nil
				if VisionWorker.status() then
					return Run.report(
						"vision",
						{},
						Run.CODES.PASS,
						"vision serve: one is already warm (kit vision serve --status)",
						"none — proceed"
					)
				end
				-- FOREGROUND: the worker lives as long as this command (Lune ends what it started when it exits) —
				-- run it in its own terminal or in the background; every other kit command finds it meanwhile
				print(
					`vision serve: warm until idle {idle or 1200} s or \`lune run kit vision serve --stop\` — run this in its own terminal (or in the background): every kit vision call, cut-out and rank goes through it meanwhile`
				)
				local ok, res = pcall(
					process.exec,
					Run.tool("python"),
					{ "kit/vision/serve.py", "--idle", tostring(idle or 1200) },
					{ env = { KIT_BUILD = Config.path("build") } } :: any
				)
				if not ok or not res.ok then
					return Run.report(
						"vision",
						{},
						Run.CODES.TOOLCHAIN,
						`vision serve: the worker stopped with an error ({if ok then res.code else res})`,
						`read {Config.path("build")}/vision_worker.log`
					)
				end
				return Run.report(
					"vision",
					{},
					Run.CODES.PASS,
					"vision serve: the warm worker ended (idle, --stop, a crashed call, or the vision code / pins changed)",
					"none — calls run cold until `lune run kit vision serve` again"
				)
			elseif sub == "light" or sub == "concept" or sub == "plate" then -- (diffusion models: the diffusers environment, kit/gen/vision3.py)
				step = Run.content("vision", Run.tool("diffusers"), { "kit/gen/vision3.py", table.unpack(rawArgs) })
			elseif sub == "relief" or sub == "parts" or sub == "albedo" then -- (phase B models: the TRELLIS.2 environment, kit/gen/vision2.py)
				step = Run.content("vision", Run.tool("trellis2"), { "kit/gen/vision2.py", table.unpack(rawArgs) })
			elseif sub == "vectorize" or sub == "upscale" then -- (the kit's python: kit/tools/pins/kit-python.txt)
				step = Run.content("vision", Run.tool("python"), { `kit/vision/{sub}.py`, table.unpack(rawArgs, 2) })
			elseif sub == "angle" or sub == "edit" then -- (Qwen-Image-Edit-2511 run by stable-diffusion.cpp: kit/gen/qwen_edit.py)
				step = Run.content("vision", Run.tool("python"), { "kit/gen/qwen_edit.py", table.unpack(rawArgs) })
			else
				local script = if sub == "setup" then "kit/vision/setup.py" else "kit/vision/run.py"
				local args = if sub == "setup" then { table.unpack(rawArgs, 2) } else rawArgs
				step = Run.content("vision", Run.tool("python"), { script, table.unpack(args) })
			end
			local r = step.result or {}
			return Run.report(
				"vision",
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
				r.summary or "vision: crashed",
				r.next_action or "read the error above"
			)
		end
	)
	Cli.command(
		"3d",
		"accept",
		'accept <asset> ["the owner\'s words"] [--lower] | accept <vfx|screen|sound|world|anim|system> <name> [...]',
		"lock the OWNER-approved build as the floor (the ratchet): a later build measuring more than 2 raw points below it fails; every other kind: kit/qa/accept.luau (kit verify holds the floors)",
		function(rawArgs)
			-- the other kinds' ratchet (mission 06 5.8) lives with QA; `accept asset <name>` is this one
			if table.find(require("../qa/accept").KINDS, rawArgs[1]) and rawArgs[2] then
				return require("./qa").accept(rawArgs)
			end
			if rawArgs[1] == "asset" and rawArgs[2] then
				rawArgs = { table.unpack(rawArgs, 2) }
			end
			local asset = rawArgs[1]
			local hist = if asset then Config.build("models") .. `/{asset}.quality.json` else ""
			if not asset or not fs.isFile(hist) then
				return Run.report(
					"accept",
					{},
					Run.CODES.USAGE,
					"accept: needs an asset with a full build",
					"lune run kit asset <asset> (a full build, not --geo), look at it, then: lune run kit accept <asset>"
				)
			end
			local entries = serde.decode("json", fs.readFile(hist))
			local last = entries[#entries]
			if type(last.score) ~= "number" or type(last.components) ~= "table" then
				return Run.report(
					"accept",
					{},
					Run.CODES.USAGE,
					`accept: {asset}'s last build has no measured score (a --geo build, or one from an older kit)`,
					`lune run kit asset {asset}`
				)
			end
			local manifest = Config.build("models") .. `/{asset}.manifest.json`
			local build = nil
			if fs.isFile(manifest) then
				local ok, m = pcall(serde.decode, "json" :: any, fs.readFile(manifest))
				build = if ok and m then m.build_id else nil
			end
			local path = `{Config.path("models")}/{asset}.accepted.json`
			local lower = table.find(rawArgs, "--lower") ~= nil
			local noteWords = {}
			for i = 2, #rawArgs do
				if rawArgs[i] ~= "--lower" then
					table.insert(noteWords, rawArgs[i])
				end
			end
			-- both builds re-scored with TODAY's weights (rbx_score floor): stored raws are on the weights of their
			-- day. A drop below the floor is a lowering (small steps would walk it down); a floor measured by other
			-- code, or unreadable, is a re-base. A floor goes down — or onto a different build — only by the OWNER:
			-- --lower, confirmed at their terminal. The one re-base without them: a build MADE by the floor's script
			-- (the file Blender ran, its sha recorded when it was built) that is the floor's model (the fingerprint
			-- the floor kept). The floor compared is the COMMITTED one once there is one (found whatever the spelling
			-- or the models folder): no edit, deletion or breakage of the file moves it, a new floor holds once
			-- committed, and a floor never committed is only its file; a build measured by older code is never
			-- accepted at all.
			Run.expectingFailure = true
			local cmp = Run.content("floor", Run.tool("python"), { "kit/blender/rbx_score.py", "floor", path, hist })
			Run.expectingFailure = false
			local c = cmp.result or {}
			if not cmp.ok or c.stale == true then
				return Run.report(
					"accept",
					{ cmp },
					Run.CODES.USAGE,
					`accept: {asset}'s last build was measured by older measuring code (or could not be compared) — a floor holds only today's measurements`,
					`rebuild it with the current kit first: lune run kit asset {asset}`
				)
			end
			local previous = if type(c.previous) == "table" then c.previous else nil
			local lowering, rebase = c.lowering == true, c.rebase == true
			local sameBuild = rebase and c.same_script == true
			if lowering or (rebase and not sameBuild) then
				local why = if lowering
					then `{asset} iteration {last.iteration} (raw {c.now}) is BELOW its accepted floor (raw {c["then"]} re-scored today)`
					elseif
						type(c.changed) == "string" and c.changed ~= ""
					then `{asset}'s floor was measured by other measuring code and this build is not its model any more ({c.changed})`
					else `{asset}'s floor was measured by other measuring code (or is unreadable), and not from this script: the two cannot be compared`
				if not lower then
					return Run.report(
						"accept",
						{},
						Run.CODES.USAGE,
						`accept: {why} — a floor is lowered, or moved to another build, only by the owner`,
						`only if the OWNER approved THIS build: lune run kit accept {asset} "<the owner's words>" --lower  (they confirm it at their terminal)`
					)
				end
				local confirmed, refusal = Owner.confirm(
					if lowering
						then `OWNER: lower {asset}'s floor (raw {c["then"]} -> {c.now})`
						else `OWNER: move {asset}'s floor onto this build (iteration {last.iteration})`,
					asset
				)
				if not confirmed then
					return Run.report(
						"accept",
						{},
						Run.CODES.USAGE,
						`accept: {refusal}`,
						`the owner runs  lune run kit accept {asset} "<their words>" --lower  in their own terminal`
					)
				end
			end
			fs.writeFile(path, serde.encode("json", {
				asset = asset,
				score = last.score,
				raw = last.raw,
				iteration = last.iteration,
				build = build,
				components = last.components,
				measure = last.measure,
				-- the accepted build's identity: its script (sha) and its model (fingerprint)
				script_sha = c.script_sha,
				tris = c.tris,
				size = c.size,
				note = table.concat(noteWords, " "),
				lowered = if lowering then true else nil,
				rebased = if rebase then true else nil,
				rebased_same_build = if sameBuild then true else nil,
				restored_from_git = if c.from_git then true else nil,
				previous = if previous
					then {
						raw = previous.raw,
						iteration = previous.iteration,
						measure = previous.measure,
						script_sha = previous.script_sha,
						at = previous.at,
					}
					else nil,
				at = os.date("!%Y-%m-%dT%H:%M:%SZ"),
			}, true) .. "\n")
			local how = if lowering
				then " (LOWERED by the owner)"
				elseif sameBuild then " (RE-BASED: the same build under new measuring code)"
				elseif rebase then " (RE-BASED by the owner)"
				else ""
			return Run.report(
				"accept",
				{},
				Run.CODES.PASS,
				`accept: {asset} iteration {last.iteration} ({last.score}, raw {last.raw}) is the floor now{how} — a later build measuring more than 2 raw points below it (re-scored with the weights of the day, measured alike) fails`,
				`commit {path}; the next model starts from it`
			)
		end
	)
end

return Judge

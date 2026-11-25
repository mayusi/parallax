--!strict
-- prompt.luau — `kit prompt ...`: PROMPT-X (LIMITATIONS_FIXES_V4 section 9 / 13.7; the owner, 2026-11-19: "it will take
-- my horrible prompts and ... make it a really good prompt to actually use itself ... I want to make this from
-- scratch"). The owner's raw words -> the lanes they need, the repo's own rules and records for those lanes, at most 3
-- questions, and a prompt compiled for the model that runs it (claude | codex | gemini | local), inside its token
-- budget, plus the kit tools' prompts (FLUX.2 positive words only, Qwen-Edit, TRELLIS.2, the lane DSLs' numbers).
-- kit/prompt/ does the work (standard-library Python, offline, deterministic):
--   kit prompt compile "<words>" [--model M] [--answers "q1=A,q2=B"] [--lane L] [--out F] [--kickoff <Name>] [--full]
--   kit prompt clarify "<words>"            the questions only (the rest is filled from the repo silently)
--   kit prompt route "<words>"              the lanes, coupling and the graveyard / golden records it pulled
--   (compile --copy puts the prompt on the clipboard; every packet is kept as build/prompt/packets/<sha>.json)
--   kit prompt evolve <packet.json | sha> <0-10> "<the owner's words>" [--verify .verify/verify.json] [--dry]
--       (the score + words must quote a verdict kit verdict recorded from the owner: never an invented one)
--   kit prompt evolve --verdicts [--dry]   the loop over every owner verdict whose piece had a prompt (--piece <name>)
--   kit prompt bench [--model M]            the 10 real failed owner prompts replayed: each must carry its guardrail
--   kit prompt sub "<text>" [--ban a,b]     the FLUX.2 positive substitution alone
--   kit prompt case <lane> "<words>"        the matched CASE CONTRACT + the lane's capability menu (<= 25 lines)
--   kit case <lane> "<words>"               the same, as its own command (PARALLAX spec §3.2)
-- compile writes the session token .verify/parallax_session.json (--no-session: not; --session <id>: the harness's)
-- --kickoff <Name> with 2 or more lanes runs `kit kickoff` (board/briefs/<Name>.md and one task per lane).
local Cli = require("../lib/cli")
local Run = require("../lib/run")

local VALUED = { "model", "game", "answers", "lane", "out", "kickoff", "verify", "ban", "piece", "session" }
local SWITCHES = { "full", "dry", "copy", "verdicts", "no-session" }

local function report(step: Run.Step, label: string): number
	local r = step.result or {}
	for _, line in (if type(r.lines) == "table" then r.lines else {}) :: { any } do
		print("  " .. tostring(line))
	end
	local code = if step.ok then Run.CODES.PASS elseif step.result then Run.CODES.CONTENT else Run.CODES.TOOLCHAIN
	return Run.report(
		label,
		{ step },
		code,
		tostring(r.summary or `{label}: the compiler gave no verdict`),
		tostring(r.next_action or "read the error above")
	)
end

return function(Cli_: any)
	Cli_.command(
		"work",
		"prompt",
		'prompt compile "<words>" [--model claude|codex|gemini|local] [--answers "q1=A"] [--lane L] [--kickoff <Name>] [--piece <name>] [--session <id>] [--no-session] [--full] | clarify "<words>" | route "<words>" | case <lane> "<words>" | evolve <packet.json> <0-10> "<words>" [--dry] | evolve --verdicts [--dry] | bench [--model M] | sub "<text>"',
		"PROMPT-X: the owner's raw words compiled into a repo-grounded prompt for the model that runs it (lanes, the vault's graveyard and golden records, at most 3 questions, a token budget per model) plus the tools' prompts; evolve learns from verdicts, bench replays 10 real failed prompts",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			if #args == 0 then
				return Run.report(
					"prompt",
					{},
					Run.CODES.USAGE,
					"prompt: compile | clarify | route | case | evolve | bench | sub",
					'lune run kit prompt compile "make a heavy katana slash with fire"'
				)
			end
			local argv = { "kit/prompt/cli.py" }
			for _, a in args do
				table.insert(argv, a)
			end
			for _, f in VALUED do
				if type(flags[f]) == "string" then
					table.insert(argv, "--" .. f)
					table.insert(argv, flags[f])
				end
			end
			for _, f in SWITCHES do
				if flags[f] then
					table.insert(argv, "--" .. f)
				end
			end
			local step = Run.content(`prompt {args[1]}`, Run.tool("python"), argv)
			local r = step.result or {}
			-- two or more lanes and --kickoff <Name>: seed the brief and one board task per lane through kit kickoff
			if step.ok and type(r.kickoff_args) == "table" and type(r.lanes) == "table" and #r.lanes >= 2 then
				-- (r.kickoff_args: kit kickoff's own arguments, the Name first; r.kickoff is the whole line, for people)
				local kick = { "run", "kit", "kickoff" }
				for _, a in r.kickoff_args :: { any } do
					table.insert(kick, tostring(a))
				end
				local k = Run.spawn("prompt kickoff", Run.tool("lune"), kick)
				print(k.tail)
				if not k.ok then
					return Run.report(
						"prompt",
						{ step, k },
						Run.CODES.CONTENT,
						"prompt compile: the packet is written but kit kickoff failed",
						"read kit kickoff's message above"
					)
				end
			end
			return report(step, "prompt")
		end
	)
	Cli_.command(
		"work",
		"case",
		'case <3d|vfx|anim|world|ui|sfx|code|qa> "<words>" [--piece <name>]',
		"the CASE a request is in its lane (kit/knowledge/cases/<lane>.json): the contract's floor, forbidden routes and owner stops + the lane's capability menu and escalation ladder, in <= 25 lines",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			local argv = { "kit/prompt/cli.py", "case" }
			for _, a in args do
				table.insert(argv, a)
			end
			if type(flags.piece) == "string" then
				table.insert(argv, "--piece")
				table.insert(argv, flags.piece)
			end
			return report(Run.content("case", Run.tool("python"), argv), "case")
		end
	)
end

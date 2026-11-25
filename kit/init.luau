-- kit — Roblox production pipeline for any model in any harness. Entry point: `lune run kit <command> [args]`.
-- Start with `lune run kit status` (briefing) or `lune run kit help` (every command).
-- kit/ and src/kit/ are KIT-OWNED (replaced by `kit update`); everything else in the project is yours.
local process = require("@lune/process")

-- `--game <Name>` (which game the command works in) is taken off the command line before any module reads the config
local Config = require("@self/lib/config")
local argv = Config.applyArgs(process.args)
Config.game()
if Config.missingGame and argv[1] ~= "game" and argv[1] ~= "new" and argv[1] ~= "help" then
	print(`[FAIL] no game "{Config.missingGame}" (from --game / KIT_GAME / games/.active): nothing would land in it`)
	print("summary: unknown game")
	print("next_action: lune run kit game list  (then --game <Name>, or kit game use <Name> | none)")
	process.exit(7)
end

local Cli = require("@self/lib/cli")
local Content = require("@self/cmd/content")
local Core = require("@self/cmd/core")
local Judge = require("@self/cmd/judge")
local Learn = require("@self/cmd/learn")
local Libs = require("@self/cmd/libs")
local Qa = require("@self/cmd/qa")
local Upgrade = require("@self/cmd/upgrade")

local Steps = Core.steps()

require("@self/cmd/work")(Cli)
require("@self/cmd/scaffold")(Cli)
require("@self/cmd/setup")(Cli, Steps)
Core.register(Cli, Steps, Content, Qa)
Content.register(Cli, Steps)
Content.registerWorld(Cli, Steps)
require("@self/cmd/anim").register(Cli, Steps)
Qa.register(Cli, Content)
Learn.register(Cli)
Judge.register(Cli)
Libs.register(Cli)
require("@self/cmd/upload")(Cli)
require("@self/cmd/refs")(Cli)
require("@self/cmd/library")(Cli)
require("@self/cmd/knowledge")(Cli)
require("@self/cmd/watch")(Cli)
require("@self/cmd/materials")(Cli)
require("@self/cmd/fit")(Cli)
require("@self/cmd/tools")(Cli)
require("@self/cmd/plan")(Cli)
require("@self/cmd/rate")(Cli)
require("@self/cmd/start")(Cli)
require("@self/cmd/approve")(Cli)
require("@self/cmd/kickoff")(Cli)
require("@self/cmd/look")(Cli)
require("@self/cmd/family")(Cli)
require("@self/cmd/alike").register(Cli)
require("@self/cmd/docs").register(Cli)
require("@self/cmd/design")(Cli)
require("@self/cmd/study")(Cli)
require("@self/cmd/sheet")(Cli)
require("@self/cmd/sharpen")(Cli)
require("@self/cmd/board")(Cli)
require("@self/cmd/review")(Cli)
require("@self/cmd/pack")(Cli)
require("@self/cmd/dossier")(Cli)
require("@self/cmd/make")(Cli)
require("@self/cmd/net").register(Cli)
require("@self/cmd/systems")(Cli)
require("@self/cmd/moves").register(Cli)
require("@self/cmd/game").register(Cli)
require("@self/cmd/vault")(Cli)
require("@self/cmd/prove")(Cli)
require("@self/cmd/parts")(Cli)
require("@self/cmd/prompt")(Cli)
require("@self/cmd/contract").register(Cli)
Upgrade.register(Cli)

-- every command passes the Parallax gate first (kit/lib/enforcer.luau): the department's vault page (once per window;
-- kit/lib/vaultgate.luau), then a session + PROMPT-X before a mutating pipeline command, a <piece>.plan.json before a
-- heavy build, the case contract - it REFUSES with exit 6 (PARALLAX spec §5.1 step 5)
local Enforcer = require("@self/lib/enforcer")
Cli.before = Enforcer.before
-- a lane's gate that fails shows the lessons that match its words (kit/lib/failhints.luau, loaded only when one fails;
-- set here, never where a spec can require it)
require("@self/lib/run").onFail = function(file: string, summary: string, tails: string)
	for _, line in require("@self/lib/failhints").lines(file, summary, tails) do
		print(line)
	end
end
local code = Cli.dispatch(argv)
-- a passing verify / prove and a written handoff are stamped on the session (the Stop hook then stays quiet)
pcall(Enforcer.after, argv[1] or "help", code)
process.exit(code)

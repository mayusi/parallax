--!strict
-- docs.luau — `kit docs <words | Class.member>`: the Roblox Engine API reference, searched locally (2026-11-08, sprint 5:
-- proposal 11 - the code lane had no API docs). The source is the reference Roblox Studio ships on this machine (its
-- content/api_docs/en-us.json; nothing downloaded, nothing of Roblox's text copied into the repo); the declared type
-- of a member comes from the kit's own type file (kit/types/globalTypes.d.luau). kit/tools/docs.py does the search.
local Cli = require("../lib/cli")
local Run = require("../lib/run")

local Docs = {}

function Docs.register(Cli_: typeof(Cli))
	Cli_.command(
		"code",
		"docs",
		"docs <words | Class.member> [--k 6]",
		"the Roblox Engine API reference, searched locally (Roblox Studio's own en-us.json): an exact Class.member first, then by words, each with its declared type from the kit's type file",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			if #args == 0 then
				return Run.report(
					"docs",
					{},
					Run.CODES.USAGE,
					"docs: which words or Class.member?",
					'lune run kit docs Players.PlayerAdded  /  lune run kit docs "raycast exclude list"'
				)
			end
			local argv = { "kit/tools/docs.py", table.concat(args, " ") }
			if type(flags.k) == "string" then
				table.insert(argv, "--k")
				table.insert(argv, flags.k)
			end
			local step = Run.spawn("docs", Run.tool("python"), argv, true)
			local r = step.result or {}
			for _, line in (if type(r.lines) == "table" then r.lines else {}) :: { any } do
				print("  " .. tostring(line))
			end
			local code = if step.ok
				then Run.CODES.PASS
				elseif step.result then Run.CODES.CONTENT
				else Run.CODES.TOOLCHAIN
			return Run.report(
				"docs",
				{ step },
				code,
				tostring(r.summary or "docs: the search gave no verdict"),
				tostring(r.next_action or "lune run kit doctor")
			)
		end
	)
end

return Docs

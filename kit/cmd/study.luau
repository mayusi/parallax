-- study.luau — `kit study <asset> [--new]`: the REFERENCE STUDY (kit/tools/study.py; the owner, 2026-10-28: "it didn't
-- deep analyze the references fully ... and use that to learn. And then from that, create its own version"). Each
-- gathered reference read (silhouette, measured proportions, shape language, why it looks good, surface, what is weak),
-- the common ground every good one shares, OUR version (keep / change / signature / target numbers) and the vault
-- lessons this build applies, cited by id. kit plan's gather stage and kit asset's quality lock both need it.
--   kit study <asset> --new   write assets/models/<asset>.study.md: the gathered references, measured sizes, the vault
--                             lessons and past cases that match the object
--   kit study <asset>         check it; when it passes, the cited lessons are recorded on the piece (board/citations.json)
--                             so the owner's later verdict credits or flags each one
local Board = require("../lib/board")
local Run = require("../lib/run")
local Vault = require("../lib/vault")

-- the lessons last recorded for this piece (a study checked twice is one citation, not two)
local function lastCited(name: string): { string }?
	local list = Vault.citations()
	for i = #list, 1, -1 do
		local c = list[i]
		if type(c) == "table" and c.kind == "asset" and c.name == name and type(c.lessons) == "table" then
			return c.lessons
		end
	end
	return nil
end

local function same(a: { string }?, b: { string }): boolean
	if not a or #a ~= #b then
		return false
	end
	local set = {}
	for _, x in a do
		set[x] = true
	end
	for _, x in b do
		if not set[x] then
			return false
		end
	end
	return true
end

return function(Cli: any)
	Cli.command(
		"3d",
		"study",
		"study <asset> [--new | --reroute] [--as <who>]",
		"the reference study before the shape: every gathered reference read (silhouette, measured proportions, shape language, why it works, surface, weak points), what all good ones share, our own version (keep / change / signature / target numbers) and the vault lessons it applies, cited by id; kit plan's gather stage and kit asset's quality lock need it. --reroute: the build's route changed (kit asset refuses it) - the old answers kept to read, every matched lesson asked again for the new route",
		function(rawArgs)
			local args, flags = Cli.parse(rawArgs)
			local pyArgs = { "kit/tools/study.py" }
			for _, a in args do
				table.insert(pyArgs, a)
			end
			if flags.new then
				table.insert(pyArgs, "--new")
			end
			if flags.reroute then -- (kit asset refused the build: the route changed - every lesson asked again for it)
				table.insert(pyArgs, "--reroute")
			end
			if type(flags.root) == "string" then
				table.insert(pyArgs, "--root")
				table.insert(pyArgs, flags.root)
			end
			require("../lib/locks").studyExempt("") -- (freezes the study lock's grandfathered list on its first run)
			local step = Run.content("study", Run.tool("python"), pyArgs)
			local r = step.result or {}
			local summary = r.summary or "study: crashed"
			-- --new SHOWED the matched lessons for this piece: recorded as served (the owner's verdict credits them
			-- at half weight even if the study's answers never name them)
			if
				step.ok
				and (flags.new or flags.reroute)
				and type(r.lessons_matched) == "table"
				and #r.lessons_matched > 0
				and args[1]
			then
				local fresh = Vault.serve("asset", args[1], r.lessons_matched :: { string }, Board.agent(flags.as))
				if #fresh > 0 then
					summary ..= ` - {#fresh} matched lesson(s) recorded as shown for {args[1]}`
				end
			end
			if step.ok and not flags.new and type(r.lessons) == "table" and #r.lessons > 0 and args[1] then
				local ids = r.lessons :: { string }
				if not same(lastCited(args[1]), ids) then
					local ok, err = Vault.cite("asset", args[1], ids, Board.agent(flags.as))
					summary ..= if ok
						then ` - recorded the {#ids} lesson(s) on {args[1]}: the owner's verdict will credit or flag them`
						else ` - the lessons could not be recorded: {err}`
				end
			end
			return Run.report(
				"study",
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.CONTENT,
				summary,
				r.next_action or "read the error above"
			)
		end
	)
end

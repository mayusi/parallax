-- dossier.luau — `kit dossier ...`: what we KNOW about a real object and how sure we are (kit/refs/dossier.py) — the
-- INPUT every build of it starts from, compiled once and reused: identity and the tells that set the variant apart,
-- sizes graded A-D from their sources (a number a model typed counts only once a script found it in the cited source,
-- or two reviewers confirmed it), the anatomy from the maker's parts list, pictures and models measured by script and
-- reviewed by two keys (one blind), and the owner's approval of the reference sheet.
local Run = require("../lib/run")

return function(Cli: any)
	Cli.command(
		"3d",
		"dossier",
		'dossier new "<object>" --category <pistol|rifle|generic> [--maker-domain d] [--alias a] [--family f] [--private] | dossier "<object>" | dossier source|fact|part|tell|marking|add "<object>" ... | dossier images <page url> | dossier check|sheet "<object>" | dossier review "<object>" --as <you> [--blind] [--apply <answers.json>] | dossier approve "<object>" --as owner --note "..."',
		"the object's DOSSIER: every fact graded from its sources (A maker / patent / owner, B two sites agree, C one source, D disagree), the anatomy, pictures and models checked by script and by two reviewers (one blind), the reference sheet the owner approves",
		function(rawArgs)
			local step = Run.content("dossier", Run.tool("python"), { "kit/refs/dossier.py", table.unpack(rawArgs) })
			for _, row in (step.result and step.result.rows or {}) :: { string } do
				print(row)
			end
			local r = step.result or {}
			return Run.report(
				"dossier",
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.USAGE,
				r.summary or "dossier: crashed",
				r.next_action or "read the error above"
			)
		end
	)
end

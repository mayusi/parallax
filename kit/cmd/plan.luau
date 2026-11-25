-- plan.luau — `kit plan <asset>`: the 3D PIPELINE for one asset, stage by stage (kit/tools/plan.py) — brief, gather,
-- 3D draft, shape, surface, mechanism, look and judge, present: each done / partly done / to do from the asset's own
-- files, what is missing, and the exact commands (at most five) of the first stage not done. The route is LOCKED:
-- every stage after the first one not done is refused (`--stage <key>` is the one way into a stage), and the clock
-- (assets/models/<asset>.clock.json: 10 min a prop, 30 complex, 60 a hero) STOPS everything but the look at the
-- budget — render, look, show the owner; only the owner's words extend it (`--extend <min> "<words>"`, `--restart
-- "<words>"`). The stages and every tool in them: kit/skills/parallax-3d/SKILL.md ("The pipeline at a glance").
local fs = require("@lune/fs")

local Config = require("../lib/config")
local Run = require("../lib/run")
local Vault = require("../lib/vault")

return function(Cli: any)
	Cli.command(
		"3d",
		"plan",
		'plan <asset> [--stage <key>] [--extend <min> "<owner\'s words>"] [--restart "<owner\'s words>"]',
		"the 3D pipeline for one asset in order, LOCKED — brief, gather every reference, a generated 3D draft, shape, surface, mechanism, look and judge, present: each done / partly done / to do, at most five commands for the next stage, a later stage refused until the earlier ones are done, and the clock against the tier's budget (10 / 30 / 60 min) that stops the build",
		function(rawArgs)
			-- the 3D department's page first (the owner's rules, the golden set, the graveyard, the last verdicts)
			-- within the vault budget: the plan is read against the record, never against memory
			if Vault.exists() and fs.isDir(Vault.dir("3d")) then
				local cfg = Config.load()
				print(Vault.page("3d", (cfg.vault and tonumber(cfg.vault.budget)) or 1500))
				print("")
			end
			-- (the study lock's grandfathered list is frozen on its first run: the planner reads it from board/locks.json)
			require("../lib/locks").studyExempt("")
			require("../lib/locks").stagesExempt("") -- (the same for the model sheet's and the blockout's approvals)
			require("../lib/locks").methodsExempt("") -- (and for the methods lock: a plan names each part's method)
			local step = Run.content("plan", Run.tool("python"), { "kit/tools/plan.py", table.unpack(rawArgs) })
			local r = step.result or {}
			-- (printed from the verdict itself: a step's printed tail keeps only its last lines)
			local ck = r.clock
			if ck then
				print(
					string.format(
						"  clock %.1f / %g%s min (%s)",
						ck.elapsed_min or 0,
						ck.budget_min or 0,
						if (ck.extended_min or 0) > 0 then string.format("+%g", ck.extended_min) else "",
						tostring(ck.tier)
					)
				)
			end
			for i, st in r.stages or {} do
				local locked = st.locked and (st.status == "to do" or st.status == "partial")
				print(
					string.format(
						"  %d %-15s %-11s%s %s",
						i - 1,
						st.title,
						string.upper(st.status),
						if locked then "  LOCKED" else "",
						table.concat(st.found or {}, "; ")
					)
				)
				for _, m in st.missing or {} do
					print(string.format("  %-29s- %s", "", m))
				end
			end
			-- the verdict's own `commands`: a refusal's (the blocking stage's, or the stop's), an opened stage's, the
			-- stop's, the next stage's — at most five
			if r.locked then
				print(`\nREFUSED — {r.locked}:`)
			elseif r.stop then
				print(`\nSTOP — {r.stop}:`)
			elseif r.open then
				print(`\nstage {r.open} open:`)
			elseif r.commands and #r.commands > 0 then
				print("\nnext (later stages LOCKED until it is done):")
			end
			for _, c in r.commands or {} do
				print(`  {c}`)
			end
			return Run.report(
				"plan",
				{ step },
				if step.ok then Run.CODES.PASS else Run.CODES.USAGE,
				r.summary or "plan: crashed",
				r.next_action or "read the error above"
			)
		end
	)
end

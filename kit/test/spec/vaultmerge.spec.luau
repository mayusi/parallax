-- vaultmerge.spec.luau (kit) — `kit install --update` never wipes a project's own record: its golden / graveyard rows
-- and the owner's standing orders are merged with the home's, its rules, distil history, inbox and notes stay its own,
-- and only the kit's own pages (index, boot sheets, README) are refreshed.
local fs = require("@lune/fs")

local frk = require("../frk")
local test, check = frk.test, frk.check

local VaultMerge = require("../../lib/vaultmerge")

return function()
	test.suite("vault merge on a kit update", function()
		test.case("each vault file has a policy: kit pages replaced, rows and orders merged, the rest kept", function()
			check.equal(VaultMerge.policy("3d/index.md"), "replace")
			check.equal(VaultMerge.policy("vfx/boot.md"), "replace")
			check.equal(VaultMerge.policy("README.md"), "replace")
			check.equal(VaultMerge.policy("Verdicts.base"), "replace")
			check.equal(VaultMerge.policy("3d/golden.md"), "merge")
			check.equal(VaultMerge.policy("ui/graveyard.md"), "merge")
			check.equal(VaultMerge.policy("shared/orders.md"), "merge")
			check.equal(VaultMerge.policy("3d/rules.md"), "keep")
			check.equal(VaultMerge.policy("3d/distil.md"), "keep")
			check.equal(VaultMerge.policy("inbox.md"), "keep")
			check.equal(VaultMerge.policy("ui/verdicts/fieldhud--2026-10-12.md"), "keep")
		end)

		test.case("a merge keeps every line the project wrote and adds only the home's new ones", function()
			local project = "# golden\n\n| a | 9 |\n| project row | 8 |\n"
			local home = "# golden\n\n| a | 9 |\n| home row | 9 |\n"
			local out = VaultMerge.merge(project, home)
			check.truthy(string.find(out, "| project row | 8 |", 1, true))
			check.truthy(string.find(out, "| home row | 9 |", 1, true))
			local _, rows = string.gsub(out, "| a | 9 |", "")
			check.equal(rows, 1) -- a shared row once
			check.equal(VaultMerge.merge(out, home), out) -- a second update changes nothing
		end)

		test.case(
			"copy: a project's own rules and notes survive, its orders gain the home's, kit pages refresh",
			function()
				local tmp = ".verify/_vaultmerge_spec"
				if fs.isDir(tmp) then
					fs.removeDir(tmp)
				end
				fs.writeDir(tmp)
				local function both(name: string, home: string, project: string?)
					fs.writeFile(`{tmp}/home_{name}`, home)
					if project then
						fs.writeFile(`{tmp}/proj_{name}`, project)
					end
				end
				both(
					"rules.md",
					"- R-3d-1 (2026-10-01): home rule\n",
					"- R-3d-1 (2026-10-01): the project's own rule\n"
				)
				both("orders.md", "- all local only\n", "- the project's own order\n")
				both("index.md", "new kit index\n", "old kit index\n")
				both("note.md", "home note\n", nil)
				local ok, err = pcall(function()
					check.falsy(VaultMerge.copy(`{tmp}/home_rules.md`, `{tmp}/proj_rules.md`, "3d/rules.md"))
					check.truthy(string.find(fs.readFile(`{tmp}/proj_rules.md`), "the project's own rule", 1, true))
					check.truthy(VaultMerge.copy(`{tmp}/home_orders.md`, `{tmp}/proj_orders.md`, "3d/orders.md"))
					local orders = fs.readFile(`{tmp}/proj_orders.md`)
					check.truthy(string.find(orders, "the project's own order", 1, true))
					check.truthy(string.find(orders, "all local only", 1, true))
					check.truthy(VaultMerge.copy(`{tmp}/home_index.md`, `{tmp}/proj_index.md`, "3d/index.md"))
					check.equal(fs.readFile(`{tmp}/proj_index.md`), "new kit index\n")
					check.truthy(VaultMerge.copy(`{tmp}/home_note.md`, `{tmp}/proj_note.md`, "3d/lessons/x.md")) -- missing: copied
				end)
				fs.removeDir(tmp)
				if not ok then
					error(err)
				end
			end
		)
	end)
end

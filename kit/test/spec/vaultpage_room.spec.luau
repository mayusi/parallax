-- vaultpage_room.spec.luau (kit) — a short department page keeps the owner's record in its budget: when the live
-- rules would push LAST VERDICTS past it, the page shows fewer (the newest) rules and names the rest (Vault.page;
-- 2026-11-20: the 3D distil took its live rules from 3 to 6 and kit start's 3D sheet lost its vault page).
local fs = require("@lune/fs")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Vault = require("../../lib/vault")

return function()
	test.suite("vault page: the record keeps its room", function()
		test.case("a tight page drops older rules before the owner's verdicts", function()
			local tmp = "kit/selftest/vault/_tmp_room"
			if fs.isDir(tmp) then
				fs.removeDir(tmp)
			end
			fs.writeDir(tmp .. "/3d/verdicts")
			fs.writeFile(
				`{tmp}/3d/verdicts/lamp--2026-11-15.md`,
				"---\nkind: verdict\narea: 3d\nname: lamp\nscore: 10\ndate: 2026-11-15\nsource: owner\n---\n\nbeautiful\n"
			)
			local saved = Vault.ROOT
			Vault.ROOT = tmp
			local ok, err = pcall(function()
				for i = 1, 6 do
					Vault.ruleChange(
						"3d",
						"add",
						nil,
						`rule number {i}: ` .. string.rep("a long reading of a verdict ", 8)
					)
				end
				check.equal(#Vault.rules("3d"), 6)
				-- roomy: every live rule (the short cap) and the record
				local roomy = Vault.page("3d", 2400, true)
				check.truthy(string.find(roomy, "R-3d-1:", 1, true))
				check.truthy(string.find(roomy, "LAST VERDICTS", 1, true))
				-- tight: all six rules would cut the record off - older rules give way until it fits
				local budget = 250
				local tight = Vault.page("3d", budget, true)
				local at = string.find(tight, "LAST VERDICTS", 1, true)
				check.truthy(at)
				check.falsy(string.find(tight, "chars cut by the vault budget", 1, true)) -- the record was not cut
				check.truthy(string.find(tight, "lamp: 10/10", 1, true)) -- its words, not only its header
				check.truthy(string.find(tight, "R-3d-6:", 1, true)) -- the newest rule is kept
				check.falsy(string.find(tight, "R-3d-1:", 1, true)) -- an older one gives way, and is named
				check.truthy(string.find(tight, "older live rule(s)", 1, true))
				check.truthy(#tight <= budget * 4)
			end)
			Vault.ROOT = saved
			fs.removeDir(tmp)
			if not ok then
				error(err)
			end
		end)
	end)
end

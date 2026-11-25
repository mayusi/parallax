-- startrecord.spec.luau (kit) — kit start reads two records that were written and never read (2026-11-08, sprint 4):
-- the owner's own before -> after pairs (kit vault garden writes <dept>/pairs/) - the one fitting the piece named,
-- else the newest - and, for the sound lane, the owner's measured ear (kit/audio/booth.py's sfx_taste.json).
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Start = require("../../cmd/start")({ command = function() end })
local Vault = require("../../lib/vault")

local TMP = "kit/selftest/vault/_tmp_startrecord"

local function pair(name: string, date: string, turn: string)
	fs.writeFile(
		`{TMP}/anim/pairs/{string.lower(name)}--{date}.md`,
		`---\nkind: pair\narea: anim\nname: {name}\ndate: {date}\n---\n\n# {name}: {turn}\n\n- Before: horrible\n- After: loved\n`
	)
end

local function withVault(body: () -> ())
	if fs.isDir(TMP) then
		fs.removeDir(TMP)
	end
	fs.writeDir(TMP .. "/anim/pairs")
	local savedRoot, savedTaste = Vault.ROOT, Start.TASTE
	Vault.ROOT = TMP
	Start.TASTE = TMP .. "/sfx_taste.json"
	local ok, err = pcall(body)
	Vault.ROOT, Start.TASTE = savedRoot, savedTaste
	fs.removeDir(TMP)
	if not ok then
		error(err)
	end
end

return function()
	test.suite("start: the owner's before -> after and the owner's ear", function()
		test.case("the pair fitting the piece named, else the newest; none without pairs", function()
			withVault(function()
				check.equal(Start.pairLine("anim", "Anything"), nil)
				pair("GreatswordSideCut", "2026-10-18", "1/10 -> 9/10")
				pair("Katana4Kiriage", "2026-10-19", "2/10 -> 9/10")
				local newest = Start.pairLine("anim", nil) or ""
				check.truthy(string.find(newest, "Katana4Kiriage 2/10 -> 9/10", 1, true))
				check.truthy(string.find(newest, "katana4kiriage--2026-10-19.md", 1, true))
				local fit = Start.pairLine("anim", "GreatswordOverhead") or ""
				check.truthy(string.find(fit, "GreatswordSideCut 1/10 -> 9/10", 1, true))
			end)
		end)

		test.case(
			"the taste model's line: on with its agreement, off with why, or switched off by the owner",
			function()
				withVault(function()
					check.equal(Start.tasteModelLine("anim"), nil) -- never trained
					local path = Vault.dir("anim", "taste.json")
					fs.writeFile(
						path,
						serde.encode("json", { lane = "anim", n = 13, enabled = false, why = "13 piece(s) (needs 20)" })
					)
					check.truthy(string.find(Start.tasteModelLine("anim") or "", "off - 13 piece(s)", 1, true))
					fs.writeFile(
						path,
						serde.encode("json", { lane = "anim", n = 24, enabled = true, pairwise = 0.674 })
					)
					check.truthy(
						string.find(
							Start.tasteModelLine("anim") or "",
							"agrees with the owner on 67% of pairs",
							1,
							true
						)
					)
					fs.writeFile(
						path,
						serde.encode("json", { lane = "anim", n = 24, enabled = true, pairwise = 0.674, off = true })
					)
					check.truthy(string.find(Start.tasteModelLine("anim") or "", "switched off by the owner", 1, true))
				end)
			end
		)

		test.case("the sound lane reads the ear: its leanings, or how many verdicts it still needs", function()
			withVault(function()
				check.equal(Start.tasteLine("sfx"), nil) -- no file yet
				fs.writeFile(
					Start.TASTE,
					serde.encode("json", { verdicts = 4, note = "4 scored verdict(s): needs 6+" })
				)
				check.truthy(string.find(Start.tasteLine("sfx") or "", "needs 6+", 1, true))
				check.equal(Start.tasteLine("anim"), nil)
				fs.writeFile(
					Start.TASTE,
					serde.encode("json", {
						verdicts = 7,
						leans = { { trait = "brightness_hz", r = 0.71, owner_prefers = "brighter" } },
					})
				)
				check.truthy(string.find(Start.tasteLine("sfx") or "", "brightness_hz: brighter (r 0.71)", 1, true))
			end)
		end)
	end)
end

-- cutscenestale.spec.luau — a game cutscene (KitAnimations.Cutscenes, kit anim cutscene --timeline) goes STALE when a
-- clip it plays or its script changes, and kit anim's verify says so with the command that re-plans it (2026-10-24).
local frk = require("../frk")
local fs = require("@lune/fs")
local serde = require("@lune/serde")
local test, check = frk.test, frk.check

local AnimCmd = require("../../cmd/anim")

local DIR = ".verify/_spec_cutscenestale"

local function moduleText(timelines: any): string
	return 'return game:GetService("HttpService"):JSONDecode([==[' .. serde.encode("json", timelines) .. "]==])\n"
end

return function()
	test.suite("kit anim: stale game cutscenes", function()
		-- (the cases run after this body: each writes its own fixture script; the last one removes the folder)
		local script = `{DIR}/Duel.json`
		local function fixture()
			fs.writeDir(DIR)
			fs.writeFile(script, '{"name": "Duel"}\r\n')
		end
		local sha = serde.hash("sha256", '{"name": "Duel"}\n') -- (line endings normalised)
		local metas = {
			Cut = { duration = 0.85, events = { { name = "Hit", t = 0.4333 } } },
			Guard = { duration = 1.0, events = { { name = "Parry", t = 0.15 }, { name = "Hit", t = 0.47 } } },
		}
		local function timelines(clips: any): any
			return {
				Duel = {
					duration = 7,
					sources = { script = { path = script, sha256 = sha }, clips = clips },
				},
			}
		end
		local fresh = {
			Cut = { duration = 0.85, events = { { "Hit", 0.4333 } } },
			Guard = { duration = 1.0, events = { { "Parry", 0.15 }, { "Hit", 0.47 } } },
		}

		test.case("a timeline built from today's clips and script is not stale", function()
			fixture()
			check.equal(#AnimCmd.cutscenesStale(moduleText(timelines(fresh)), metas), 0)
		end)
		test.case("a clip whose Hit moved makes it stale, with the command that re-plans it", function()
			fixture()
			local moved = { Cut = { duration = 0.85, events = { { "Hit", 0.4 } } }, Guard = fresh.Guard }
			local out = AnimCmd.cutscenesStale(moduleText(timelines(moved)), metas)
			check.equal(#out, 1)
			check.truthy(string.find(out[1], "Cut changed", 1, true) ~= nil)
			check.truthy(string.find(out[1], `kit anim cutscene {script} --timeline`, 1, true) ~= nil)
		end)
		test.case("a clip the game no longer has makes it stale", function()
			fixture()
			local out = AnimCmd.cutscenesStale(moduleText(timelines(fresh)), { Cut = metas.Cut })
			check.equal(#out, 1)
			check.truthy(string.find(out[1], "no longer has", 1, true) ~= nil)
		end)
		test.case("an edited script makes it stale", function()
			fixture()
			fs.writeFile(script, '{"name": "Duel", "beats": []}\n')
			local out = AnimCmd.cutscenesStale(moduleText(timelines(fresh)), metas)
			check.equal(#out, 1)
			check.truthy(string.find(out[1], "script", 1, true) ~= nil)
		end)
		test.case("a clip whose length or an event's name changed makes it stale", function()
			fixture()
			local longer = { Cut = { duration = 0.9, events = fresh.Cut.events }, Guard = fresh.Guard }
			check.equal(#AnimCmd.cutscenesStale(moduleText(timelines(longer)), metas), 1)
			local renamed =
				{ Cut = fresh.Cut, Guard = { duration = 1.0, events = { { "Block", 0.15 }, { "Hit", 0.47 } } } }
			check.equal(#AnimCmd.cutscenesStale(moduleText(timelines(renamed)), metas), 1)
		end)
		test.case("a timeline that names no sources is stale (made before the check)", function()
			local out = AnimCmd.cutscenesStale(moduleText({ Old = { duration = 1 } }), metas)
			check.equal(#out, 1)
			check.truthy(string.find(out[1], "no sources", 1, true) ~= nil)
		end)
		test.case("an unreadable module is reported, never passed", function()
			check.equal(#AnimCmd.cutscenesStale("return nil", metas), 1)
			if fs.isDir(DIR) then
				fs.removeDir(DIR)
			end
		end)
	end)
end

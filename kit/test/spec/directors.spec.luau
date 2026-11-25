-- directors.spec.luau (kit) — a director profile re-learns BY ITSELF only when what it is distilled from changed
-- (2026-11-08, sprint 3): its inputs' fingerprint (golden, graveyard, orders, rules, lessons) is kept after each learn;
-- a lane with no profile yet is stale, the same inputs are not, a changed lesson is - and a lane with no director
-- (3D) never spawns anything.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Directors = require("../../lib/directors")

local TMP = "kit/selftest/vault/_tmp_directors"
local DEPT = "zz_spec_lane"
local STAMP = `.verify/director-{DEPT}.json`

local function withDir(body: () -> ())
	if fs.isDir(TMP) then
		fs.removeDir(TMP)
	end
	fs.writeDir(TMP .. "/lessons")
	fs.writeFile(TMP .. "/golden.md", "| piece | score |\n| lamp | 9 |\n")
	fs.writeFile(TMP .. "/lessons/one.md", "---\nkind: lesson\n---\n\nA lesson.\n")
	fs.writeFile(TMP .. "/director.md", "the profile\n")
	local ok, err = pcall(body)
	fs.removeDir(TMP)
	if fs.isFile(STAMP) then
		fs.removeFile(STAMP)
	end
	if not ok then
		error(err)
	end
end

return function()
	test.suite("directors: re-learn only when the record changed", function()
		test.case("no stamp is stale; the same inputs are not; a changed lesson is", function()
			withDir(function()
				check.truthy(Directors.stale(DEPT, TMP))
				if not fs.isDir(".verify") then
					fs.writeDir(".verify")
				end
				fs.writeFile(STAMP, serde.encode("json", { fingerprint = Directors.fingerprint(TMP) }))
				check.falsy(Directors.stale(DEPT, TMP))
				fs.writeFile(TMP .. "/lessons/one.md", "---\nkind: lesson\n---\n\nA lesson, now longer.\n")
				check.truthy(Directors.stale(DEPT, TMP))
			end)
		end)

		test.case("one changed letter in the middle of a long lesson, same length, is stale", function()
			withDir(function()
				local body = string.rep("The river carves the valley first. ", 6)
				fs.writeFile(TMP .. "/lessons/one.md", "---\nkind: lesson\n---\n\n" .. body .. "\n")
				local before = Directors.fingerprint(TMP)
				local edited = string.sub(body, 1, 100) .. "X" .. string.sub(body, 102)
				check.equal(#edited, #body)
				fs.writeFile(TMP .. "/lessons/one.md", "---\nkind: lesson\n---\n\n" .. edited .. "\n")
				check.truthy(Directors.fingerprint(TMP) ~= before)
			end)
		end)

		test.case("a director's own inputs count too: a changed brief two folders deep is stale", function()
			withDir(function()
				fs.writeDir(TMP .. "/g/one/d")
				fs.writeDir(TMP .. "/g/two/d")
				fs.writeFile(TMP .. "/g/one/d/a.json", '{"pick": "A"}')
				fs.writeFile(TMP .. "/g/two/d/b.json", '{"pick": "B"}')
				fs.writeFile(TMP .. "/g/two/d/notes.txt", "not a brief")
				check.equal(#Directors.expand(TMP .. "/g/*/d/*.json"), 2)
				check.equal(#Directors.expand(TMP .. "/nowhere/*/d/*.json"), 0)
				Directors.LEARN[DEPT] = { argv = { "never-run" }, inputs = { TMP .. "/g/*/d/*.json" } }
				local ok, err = pcall(function()
					local before, laneOnly = Directors.fingerprint(TMP, DEPT), Directors.fingerprint(TMP)
					fs.writeFile(TMP .. "/g/two/d/b.json", '{"pick": "C"}')
					check.truthy(Directors.fingerprint(TMP, DEPT) ~= before)
					check.equal(Directors.fingerprint(TMP), laneOnly) -- without the director: the lane's files only
					local mid = Directors.fingerprint(TMP, DEPT)
					fs.writeFile(TMP .. "/g/two/d/notes.txt", "still not a brief, changed")
					check.equal(Directors.fingerprint(TMP, DEPT), mid) -- a file the pattern does not name
				end)
				Directors.LEARN[DEPT] = nil
				if not ok then
					error(err)
				end
			end)
		end)

		test.case("a lane with no director never spawns anything", function()
			check.equal(Directors.relearn("3d", TMP), nil)
			check.equal(Directors.relearn(nil, nil), nil)
			check.equal(Directors.retest("3d", "kit/selftest/vault/_no_such_dir"), nil)
		end)
	end)
end

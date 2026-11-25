-- starters.spec.luau (kit) — an untouched kit starter in a project is the kit's piece (kit/lib/starters.luau): the VFX
-- presets step leaves the making gates to its first edit. What decides is the kit's record of every text a starter
-- shipped with (kit/vfx/starters.json), never the project's kit/starter/ copy. A copy with other line endings is the
-- same piece; an edit, a new name, a path for a name, a missing or broken record are not. The kit's own record must
-- hold every starter piece as it is now (this case is what keeps kit/vfx/starters.py --write from being forgotten).
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Config = require("../../lib/config")
local Starters = require("../../lib/starters")

local BODY = '{\n "version": 3,\n "duration": 1,\n "layers": []\n}\n'

return function()
	test.suite("kit starters: a copy is the kit's while its text is one the kit recorded", function()
		local root = Config.build(`selftest/starters_spec_{math.floor(os.clock() * 1e6)}`)
		local game, recordPath = `{root}/game`, `{root}/starters.json`

		local function reset()
			if fs.isDir(root) then
				fs.removeDir(root)
			end
			Config.ensureDir(game)
			fs.writeFile(`{game}/spark.json`, BODY)
			fs.writeFile(
				recordPath,
				serde.encode("json", { schema = 1, pieces = { ["effect/spark"] = { Starters.sha(BODY) } } })
			)
		end

		test.case("a copy as init made it is the kit's, whatever its line endings", function()
			reset()
			local record = Starters.load(recordPath)
			check.is_true(Starters.untouchedVfx(game, "spark.json", record))
			fs.writeFile(`{game}/spark.json`, (string.gsub(BODY, "\n", "\r\n")))
			check.is_true(Starters.untouchedVfx(game, "spark.json", record))
		end)

		test.case("an edit makes it the project's piece", function()
			reset()
			local record = Starters.load(recordPath)
			fs.writeFile(`{game}/spark.json`, (string.gsub(BODY, '"duration": 1', '"duration": 2')))
			check.is_true(not Starters.untouchedVfx(game, "spark.json", record))
			fs.writeFile(`{game}/spark.json`, BODY .. " ") -- (one byte more is an edit)
			check.is_true(not Starters.untouchedVfx(game, "spark.json", record))
		end)

		test.case("a new name, a path, a missing file, no record and a broken record are never the kit's", function()
			reset()
			local record = Starters.load(recordPath)
			fs.writeFile(`{game}/mine.json`, BODY) -- (a starter's text under a new name: a new piece)
			check.is_true(not Starters.untouchedVfx(game, "mine.json", record))
			check.is_true(not Starters.untouchedVfx(game, "../game/spark.json", record))
			check.is_true(not Starters.untouchedVfx(game, "gone.json", record))
			check.is_true(not Starters.untouchedVfx(game, "spark.json", Starters.load(`{root}/no_such_record.json`)))
			fs.writeFile(recordPath, "{ not json")
			check.is_true(not Starters.untouchedVfx(game, "spark.json", Starters.load(recordPath)))
			fs.removeDir(root)
		end)

		test.case("the kit's record holds every starter piece as it is now", function()
			-- (in the kit's home only, where the record is written: a project's kit/starter may hold a piece promoted
			-- there until `sync` brings the home's record, and that piece passed the making gates to be promoted)
			if not fs.isFile("kit/.source") then
				return
			end
			local record = Starters.load()
			local starter = "kit/starter"
			local seen = 0
			local function expect(kind: string, dir: string)
				if not fs.isDir(dir) then
					return
				end
				for _, f in fs.readDir(dir) do
					if string.sub(f, -5) == ".json" and string.sub(f, 1, 1) ~= "_" and fs.isFile(`{dir}/{f}`) then
						local shas = record[`{kind}/{string.sub(f, 1, -6)}`]
						local ok = shas ~= nil and shas[Starters.sha(fs.readFile(`{dir}/{f}`))] == true
						if not ok then
							print(
								`  not in kit/vfx/starters.json: {kind} {dir}/{f} (python kit/vfx/starters.py --write)`
							)
						end
						check.is_true(ok)
						seen += 1
					end
				end
			end
			expect("effect", `{starter}/vfx`)
			expect("mesh", `{starter}/vfx/meshes`)
			expect("texture", `{starter}/textures`)
			if fs.isDir(`{starter}/vfx/_deps`) then
				for _, ex in fs.readDir(`{starter}/vfx/_deps`) do
					expect("part", `{starter}/vfx/_deps/{ex}/parts`)
					expect("texture", `{starter}/vfx/_deps/{ex}/textures`)
				end
			end
			check.is_true(seen > 0) -- (kit/starter ships starter pieces)
		end)
	end)
end

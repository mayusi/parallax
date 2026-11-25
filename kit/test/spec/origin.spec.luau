-- origin.spec.luau (kit) — kit/lib/origin.luau: what put a project's kit files there last decides where an edited one
-- is restored from. A record `upgrade` wrote (no source = "clone") is a release's whatever kit/HOME says - a game
-- installed from a clone and upgraded since must not be sent to `sync` (its home may be older, and the update is
-- refused); otherwise a kit home that is there is `sync`'s; a kit/HOME that points nowhere, or a clone's record without
-- a home, is a clone's (never the release route); nothing at all is the kit's own home. laterVersion compares
-- numerically (v10 after v9) and never guesses.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Config = require("../../lib/config")
local Origin = require("../../lib/origin")

return function()
	test.suite("origin: what put a project's kit files there last", function()
		test.case("every kit/HOME (there / dangling / none) beside every record (clone / release / none)", function()
			local root = Config.build(`selftest/origin_spec_{math.floor(os.clock() * 1e6)}`)
			local home = `{root}/home`
			local game = `{root}/game`
			Config.ensureDir(`{home}/kit`)
			Config.ensureDir(`{game}/kit`)
			local function setHome(which: string)
				local file = `{game}/kit/HOME`
				if which == "there" then
					fs.writeFile(file, home .. "/\n") -- (a trailing slash and newline are fine)
				elseif which == "dangling" then
					fs.writeFile(file, `{root}/no/such/home\n`)
				elseif fs.isFile(file) then
					fs.removeFile(file)
				end
			end
			local function setRecord(which: string)
				local file = `{game}/kit/UPSTREAM.json`
				if which == "none" then
					if fs.isFile(file) then
						fs.removeFile(file)
					end
				elseif which == "unreadable" then
					fs.writeFile(file, "not json")
				else
					fs.writeFile(
						file,
						serde.encode("json", {
							schema = 1,
							installed_tag = "v3.0.0",
							source = if which == "clone" then "clone" else nil,
						})
					)
				end
			end
			local seen = {}
			for _, h in { "there", "dangling", "none" } do
				for _, r in { "clone", "release", "none", "unreadable" } do
					setHome(h)
					setRecord(r)
					seen[`{h}/{r}`] = Origin.of(game)
				end
			end
			setHome("there")
			seen.homePath = Origin.home(game)
			setHome("dangling")
			seen.danglingPath = Origin.home(game)
			setRecord("unreadable")
			seen.unreadableRecord = Origin.record(game)
			fs.removeDir(root)
			-- a home that is there
			check.equal(seen["there/clone"], "home")
			check.equal(seen["there/release"], "release") -- (upgraded since it was installed from the clone)
			check.equal(seen["there/none"], "home") -- (a 3.0.0 kit: no record)
			check.equal(seen["there/unreadable"], "home")
			-- a home that points nowhere
			check.equal(seen["dangling/clone"], "clone")
			check.equal(seen["dangling/release"], "release")
			check.equal(seen["dangling/none"], "clone")
			check.equal(seen["dangling/unreadable"], "clone")
			-- no kit/HOME at all
			check.equal(seen["none/clone"], "clone")
			check.equal(seen["none/release"], "release")
			check.equal(seen["none/none"], "none")
			check.equal(seen["none/unreadable"], "none")
			check.equal(seen.homePath, home)
			check.equal(seen.danglingPath, "")
			check.equal(seen.unreadableRecord, nil)
		end)

		test.case("laterVersion: numeric, either side with or without the v, unreadable = no", function()
			check.truthy(Origin.laterVersion("v3.1.0", "v3.0.0"))
			check.truthy(Origin.laterVersion("v3.0.1", "3.0.0"))
			check.truthy(Origin.laterVersion("v10.0.0", "v9.9.9"))
			check.truthy(Origin.laterVersion("v4.0.0", "v3.99.99"))
			check.falsy(Origin.laterVersion("v3.0.0", "v3.0.0"))
			check.falsy(Origin.laterVersion("v3.0.0", "v3.1.0"))
			check.falsy(Origin.laterVersion("v9.9.9", "v10.0.0"))
			check.falsy(Origin.laterVersion("main", "v3.0.0"))
			check.falsy(Origin.laterVersion("v3.1.0", ""))
		end)
	end)
end

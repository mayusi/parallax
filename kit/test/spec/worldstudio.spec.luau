-- worldstudio.spec.luau (kit) — the world lane's eyes (board/plans/archive/2026-11-11-world-studio-route-plan.md, W0): the
-- scratch place a world is shown in in Roblox Studio, the LOOK: lines a world build ends with, and the guard that
-- throws away a Studio capture of a world that has changed since it was taken.
local fs = require("@lune/fs")
local task = require("@lune/task")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Config = require("../../lib/config")
local World = require("../../lib/world")
local WorldCmd = require("../../cmd/world")

local function part(name: string, transparency: number, collide: boolean): any
	return {
		ClassName = "Part",
		Name = name,
		Properties = { Size = { Vector3 = { 4, 4, 4 } }, Transparency = transparency, CanCollide = collide },
	}
end

-- a compiled world as World.compile writes one: a house under a mesh skin (its blockout hidden, the skin's
-- placeholder invisible), a lamp of plain parts, and a barrier the blueprint itself made invisible
local function model(): any
	return {
		ClassName = "Model",
		Name = "T",
		Children = {
			{
				ClassName = "Model",
				Name = "House",
				Children = {
					part("Wall", 1, true),
					part("Roof", 1, false),
					part("Table", 0, true),
					part("KitMesh", 1, false),
				},
			},
			{ ClassName = "Model", Name = "Lamp", Children = { part("Post", 0, true) } },
			{ ClassName = "Model", Name = "Barrier", Children = { part("Edge", 1, true) } },
		},
	}
end

local function rmTree(path: string)
	if fs.isDir(path) then
		fs.removeDir(path)
	end
end

return function()
	test.suite("world studio: the scratch place", function()
		test.case("the blockout a mesh skin hides is shown again; the skin's placeholder is not", function()
			local scratch, shown, skins = World.scratchModel(model())
			check.equal(shown, 2) -- (the wall and the roof)
			check.equal(skins, 1)
			local house = scratch.Children[1].Children
			check.equal(house[1].Properties.Transparency, 0)
			check.equal(house[2].Properties.Transparency, 0)
			check.equal(house[3].Properties.Transparency, 0)
			check.equal(house[4].Properties.Transparency, 1) -- (KitMesh: nothing is uploaded, nothing to show)
		end)
		test.case("an invisible part of a step with no skin is left alone", function()
			local scratch = World.scratchModel(model())
			check.equal(scratch.Children[3].Children[1].Properties.Transparency, 1)
		end)
		test.case("the compiled model itself is not touched", function()
			local m = model()
			World.scratchModel(m)
			check.equal(m.Children[1].Children[1].Properties.Transparency, 1)
		end)
		test.case("the project holds the world alone, the kit's runtime, Future light and the marker", function()
			local p = World.scratchProject("GothicCourtyard", "../../../../src/kit")
			check.equal(p.name, "KitWorldScratch_GothicCourtyard")
			check.equal(p.name, World.scratchName("GothicCourtyard"))
			local tree = p.tree
			check.equal(tree.Workspace.KitWorldScratch["$className"], "StringValue")
			check.equal(tree.Workspace.KitWorldScratch["$properties"].Value, "GothicCourtyard")
			check.equal(tree.Workspace.KitWorld.GothicCourtyard["$path"], "GothicCourtyard.model.json")
			check.equal(tree.ReplicatedStorage.kit["$path"], "../../../../src/kit")
			check.equal(tree.Lighting["$properties"].Technology, "Future")
			-- nothing else: no other world, no asset ids, no script but the kit's own two (a scratch place uploads and
			-- saves nothing). Until 2026-11-15 this said "no server scripts" and counted 3 services: the first Studio
			-- session showed that PLAY then runs nothing of the world - the two below are counted and named
			local services = 0
			for k in tree do
				if string.sub(k, 1, 1) ~= "$" then
					services += 1
				end
			end
			check.equal(services, 5)
			local scripts = 0
			for k in tree.ServerScriptService do
				scripts += if string.sub(k, 1, 1) ~= "$" then 1 else 0
			end
			for k in tree.StarterPlayer.StarterPlayerScripts do
				scripts += if string.sub(k, 1, 1) ~= "$" then 1 else 0
			end
			check.equal(scripts, 2)
			check.equal(World.scratchProject("T", nil).tree.ReplicatedStorage.kit, nil)
			-- PLAY in the scratch place runs the world as a game does: the kit's environment script on the server and
			-- its weather script on each client, where a game's project puts them (under ReplicatedStorage a script
			-- does not run: the first Studio session showed a bare model under Studio's default light)
			local played = World.scratchProject("GothicCourtyard", "../../../../src/kit").tree
			check.equal(
				played.ServerScriptService.KitEnvironment["$path"],
				"../../../../src/kit/server/Environment.server.luau"
			)
			check.equal(
				played.StarterPlayer.StarterPlayerScripts.KitAmbient["$path"],
				"../../../../src/kit/client/Ambient.client.luau"
			)
			check.equal(World.scratchProject("T", nil).tree.ServerScriptService, nil)
			check.equal(World.scratchProject("T", nil).tree.StarterPlayer, nil)
		end)
		test.case("the marker carries the build the place was made from", function()
			-- (Studio does not reload a place file rebuilt on disk: the capture script carries the same key and
			-- refuses a place that still shows an older build)
			local marker = World.scratchProject("T", nil, "key-of-this-build").tree.Workspace.KitWorldScratch
			check.equal(marker.Build["$className"], "StringValue")
			check.equal(marker.Build["$properties"].Value, "key-of-this-build")
			check.equal(World.scratchProject("T", nil).tree.Workspace.KitWorldScratch.Build["$properties"].Value, "")
		end)
	end)

	test.suite("world studio: a capture of the world as it was", function()
		local shots = Config.build("selftest") .. "/worldstudio_spec/shots"
		local function plant(key: string?)
			rmTree(Config.build("selftest") .. "/worldstudio_spec")
			Config.ensureDir(shots)
			fs.writeFile(shots .. "/eye_1.png", "png")
			fs.writeFile(shots .. "/over.png", "png")
			fs.writeFile(shots .. "/capture.json", "{}")
			if key then
				fs.writeFile(shots .. "/of.txt", key)
			end
		end
		test.case("is kept while the world and its stations are the same", function()
			plant("abc")
			check.equal(WorldCmd.dropStaleCapture(shots, "abc"), 0)
			check.is_true(fs.isFile(shots .. "/eye_1.png"))
			check.is_true(fs.isFile(shots .. "/capture.json"))
		end)
		test.case("is thrown away once either changed", function()
			plant("abc")
			check.equal(WorldCmd.dropStaleCapture(shots, "other"), 2)
			check.is_false(fs.isFile(shots .. "/eye_1.png"))
			check.is_false(fs.isFile(shots .. "/over.png"))
			check.is_false(fs.isFile(shots .. "/capture.json"))
			check.is_false(fs.isFile(shots .. "/of.txt"))
		end)
		test.case("with no record of what it is of, is thrown away", function()
			plant(nil)
			check.equal(WorldCmd.dropStaleCapture(shots, "abc"), 2)
		end)
		test.case("no capture at all is nothing to throw away", function()
			rmTree(Config.build("selftest") .. "/worldstudio_spec")
			check.equal(WorldCmd.dropStaleCapture(shots, "abc"), 0)
		end)
		rmTree(Config.build("selftest") .. "/worldstudio_spec")
	end)

	test.suite("world build: the LOOK lines it ends with", function()
		local A, B = "SpecLookWorldA", "SpecLookWorldB"
		local look = Config.build("worlds") .. "/look/"
		local function clean()
			rmTree(look .. A)
			rmTree(look .. B)
		end
		test.case("no world has pictures: one line that says so and names the command", function()
			clean()
			local lines = WorldCmd.buildLooks({ A, B }, {}, true)
			check.equal(#lines, 1)
			check.is_true(string.sub(lines[1], 1, 6) == "LOOK: ")
			check.truthy(string.find(lines[1], "no eye-level look yet", 1, true))
			check.truthy(string.find(lines[1], "lune run kit world look", 1, true))
		end)
		test.case("an unchanged world's line names its pages folder and what is in it", function()
			clean()
			Config.ensureDir(look .. A .. "/pages")
			fs.writeFile(look .. A .. "/pages/01_eye_1.png", "png")
			fs.writeFile(look .. A .. "/pages/02_over.png", "png")
			fs.writeFile(look .. A .. "/pages/index.json", "{}")
			local lines = WorldCmd.buildLooks({ A, B }, {}, true)
			check.equal(#lines, 1)
			check.truthy(string.find(lines[1], `LOOK: {look}{A}/pages/ - 2 station page(s) of {A}`, 1, true))
			check.truthy(string.find(lines[1], "unchanged in this build", 1, true))
			clean()
		end)
		test.case("a changed world that is not rendered says its pictures are from before the change", function()
			clean()
			Config.ensureDir(look .. A .. "/pages")
			fs.writeFile(look .. A .. "/pages/01_eye_1.png", "png")
			local lines = WorldCmd.buildLooks({ A, B }, { A, B }, true) -- (--no-look)
			check.equal(#lines, 2)
			check.truthy(
				string.find(
					lines[1],
					`{A} changed since its pictures were made (they are from BEFORE the change)`,
					1,
					true
				)
			)
			check.truthy(string.find(lines[1], `lune run kit world look {A}`, 1, true))
			check.truthy(string.find(lines[2], `{B} changed since its pictures were made (they are not made)`, 1, true))
			clean()
		end)
		test.case("pictures older than their blueprint are a change the build itself cannot see", function()
			-- (a view or a label moved: neither is in the compiled model, so the model did not change)
			local dir = Config.build("selftest") .. "/worldstudio_spec_times"
			rmTree(dir)
			Config.ensureDir(dir)
			fs.writeFile(dir .. "/blueprint.json", "{}")
			task.wait(0.05)
			fs.writeFile(dir .. "/stations.json", "{}")
			check.is_false(WorldCmd.olderThan(dir .. "/stations.json", dir .. "/blueprint.json"))
			task.wait(0.05)
			fs.writeFile(dir .. "/blueprint.json", '{ "views": [] }')
			check.is_true(WorldCmd.olderThan(dir .. "/stations.json", dir .. "/blueprint.json"))
			check.is_false(WorldCmd.olderThan(dir .. "/none.json", dir .. "/blueprint.json")) -- (no pictures yet)
			check.is_false(WorldCmd.olderThan(dir .. "/stations.json", dir .. "/none.json"))
			rmTree(dir)
		end)
	end)
end

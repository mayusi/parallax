-- worldstream.spec.luau (kit) — LOADING INTENT for a world that streams (kit/lib/worldstream.luau; the owner's
-- limitations list, W-R03): how fast its players move and how far they drop, what must never be missing, where a
-- player is sent to - and what the compiler, the lock and the runtime (src/kit/WorldStream.luau) make of each.
-- Not claimed here: that Roblox loads what is asked in time (its own page promises nothing of it). Only a play
-- session shows that.
local frk = require("../frk")
local test, check = frk.test, frk.check

local LaneLocks = require("../../lib/lanelocks")
local Stream = require("../../lib/worldstream")
local World = require("../../lib/world")
local WorldStream = require("../../../src/kit/WorldStream")

local PALETTE = { stone = { material = "Concrete", color = { 96, 98, 104 } } }

local function compile(streaming: any, steps: { any }, bare: boolean?): (any, { any }, { string }, any, { string })
	local build: { any } = {}
	if not bare then
		table.insert(build, { floor = { name = "Ground", center = { 0, 0, 0 }, size = { 900, 900 }, mat = "stone" } })
	end
	for _, s in steps do
		table.insert(build, s)
	end
	local model, parts, issues, extras =
		World.compile({ name = "T", palette = PALETTE, scale = "r6", streaming = streaming, build = build })
	local errors, warns = {}, {}
	for _, i in issues do
		table.insert(if i.severity == "error" then errors else warns, i.message)
	end
	return model, parts, errors, extras, warns
end

local function child(model: any, name: string): any
	for _, c in model.Children or {} do
		if c.Name == name then
			return c
		end
	end
	return nil
end

return function()
	test.suite("Loading intent: what a world's players need kept loaded", function()
		test.case("four seconds of their fastest way, never under Roblox's own 64; the target twice that", function()
			local function need(streaming: any): (number, number)
				local intent, wrong = Stream.intent(streaming)
				check.equal(#wrong, 0)
				return Stream.need(intent), Stream.target(intent)
			end
			check.equal((need({ cell = 256 })), 64) -- (no word: on foot)
			check.equal((need({ speed = 16 })), 64)
			check.equal((need({ speed = 40 })), 160)
			check.equal((need({ speed = 16.1 })), 65) -- (rounded up: a radius a little short is ground not there)
			check.equal((need({ speed = 300 })), 1200)
			check.equal((need(nil)), 64)
			local _, target = need({ speed = 40 })
			check.equal(target, 320)
			-- a drop is NOT a radius (it would load that far in every direction): it is asked for ahead
			check.equal((need({ speed = 16, fall = 300 })), 64)
			local intent = Stream.intent({ speed = 16, fall = 300 })
			check.equal(intent.fall, 300)
		end)

		test.case("what the words refuse", function()
			-- (under a walk too: a world that said 1 would ask nothing of the game)
			for _, bad in { "fast", -1, 0, 1, 15.9, 2001, 0 / 0, math.huge, true } do
				local intent, wrong = Stream.intent({ speed = bad })
				check.equal(#wrong, 1)
				check.truthy(string.find(wrong[1], '"streaming.speed" is the fastest a player moves', 1, true))
				check.equal(intent.speed, nil)
			end
			for _, bad in { "high", -5, 0 / 0, math.huge } do
				local _, wrong = Stream.intent({ speed = 20, fall = bad })
				check.equal(#wrong, 1)
				check.truthy(string.find(wrong[1], '"streaming.fall" is the highest drop', 1, true))
			end
			check.equal(Stream.mode(nil), "")
			check.equal(Stream.mode("always"), "Persistent")
			check.equal(Stream.mode("whole"), "Atomic")
			check.equal(Stream.mode("area"), "")
			for _, bad in { "never", true, 1, "", "Persistent" } do
				local mode, why = Stream.mode(bad)
				check.equal(mode, nil)
				check.truthy(string.find(why :: string, '"stream" is "always"', 1, true))
			end
			local list, wrong = Stream.arrivals({
				arrivals = {
					{ name = "Gate", pos = { 1, 2, 3 } },
					{ name = "Gate", pos = { 4, 5, 6 } },
					{ pos = { 0, 0, 0 } },
					{ name = "Air", pos = { 1, 2 } },
					{ name = "Word", pos = "there" },
					"x",
					{ name = "Keep", pos = { 7, 8, 9 } },
				},
			})
			check.equal(#list, 2)
			check.equal(list[2].name, "Keep")
			check.equal(#wrong, 5)
			check.equal(#Stream.arrivals({}), 0)
			local _, notList = Stream.arrivals({ arrivals = "Gate" })
			check.equal(#notList, 1)
		end)
	end)

	test.suite("Loading intent: what the compiler makes of it", function()
		local function tower(more: any): any
			local t: any = { name = "Keep", center = { 0, 0, 0 }, radius = 8, height = 40, mat = "stone" }
			for k, v in more do
				t[k] = v
			end
			return { tower = t }
		end
		-- a step 600 studs long: wider than a cell of 256
		local function wall(more: any): any
			local w: any = {
				name = "Long wall",
				from = { -300, 100 },
				to = { 300, 100 },
				height = 10,
				thickness = 2,
				mat = "stone",
				gaps = { { at = 100, width = 6 }, { at = 300, width = 6 }, { at = 500, width = 6 } },
			}
			for k, v in more do
				w[k] = v
			end
			return { wall = w }
		end

		test.case('"always" never streams out, "whole" is one piece however wide, no word goes by its place', function()
			local model, _, errors, _, warns = compile({ cell = 256, speed = 16 }, {
				tower({ stream = "always" }),
				wall({}),
				wall({ name = "Bridge", stream = "whole" }),
				wall({ name = "Fence", stream = "area" }),
				{
					path = {
						name = "Road",
						points = { { -300, -200 }, { 300, -200 } },
						width = 8,
						mat = "stone",
						stream = "always",
					},
				},
			})
			check.equal(#errors, 0)
			local keep = child(model, "Keep")
			check.equal(keep.Properties.ModelStreamingMode, "Persistent")
			check.equal(keep.Properties.LevelOfDetail, nil)
			-- the plain long wall is cut into a model a cell; the bridge is ONE model, told to arrive whole
			check.equal(child(model, "Long wall"), nil)
			local cells = 0
			for _, c in model.Children do
				if string.sub(c.Name, 1, 11) == "Long wall_c" then
					cells += 1
					check.equal(c.Properties.ModelStreamingMode, nil)
					check.equal(c.Properties.LevelOfDetail, "StreamingMesh")
				end
			end
			check.truthy(cells >= 2)
			local bridge = child(model, "Bridge")
			check.equal(bridge.Properties.ModelStreamingMode, "Atomic")
			check.equal(bridge.Properties.LevelOfDetail, "StreamingMesh") -- (its far stand-in is kept)
			check.truthy(#bridge.Children >= 7) -- (every run and lintel of it, 600 studs long, in one)
			check.equal(child(model, "Bridge_c0_0"), nil)
			check.equal(child(model, "Fence"), nil) -- ("area": cut by its place, like no word)
			-- a step that ends its own turn early (a path) carries its word too
			check.equal(child(model, "Road").Properties.ModelStreamingMode, "Persistent")
			-- 600 studs arriving in one piece is said (more than two cells of 256)
			local said = false
			for _, w in warns do
				said = said or (string.find(w, '"whole": 600 studs across arrives all at once', 1, true) ~= nil)
			end
			check.truthy(said)
			-- the same world with no "stream" word anywhere: the keep is an ordinary model that streams
			local plain = compile({ cell = 256, speed = 16 }, { tower({}) })
			check.equal(child(plain, "Keep").Properties.ModelStreamingMode, nil)
		end)

		test.case("a word that is none, a word with no streaming, too much kept for ever", function()
			local _, _, errors = compile({ cell = 256, speed = 16 }, { tower({ stream = "never" }) })
			check.equal(#errors, 1)
			check.truthy(string.find(errors[1], '"stream" is "always"', 1, true))
			-- without a "streaming" block the word does nothing: said (a warning), and the model is plain
			local model, _, none, _, warns = compile(nil, { tower({ stream = "always" }) })
			check.equal(#none, 0)
			check.equal((child(model, "Keep").Properties or {}).ModelStreamingMode, nil)
			local told = false
			for _, w in warns do
				told = told or (string.find(w, '"stream" does nothing', 1, true) ~= nil)
			end
			check.truthy(told)
			-- 400 parts may be kept loaded for every player: a wall of 500 pieces marked "always" is refused
			local gaps = {}
			for k = 1, 250 do
				table.insert(gaps, { at = k * 2, width = 0.5, sill = 1 })
			end
			local _, parts, many = compile({ cell = 256, speed = 16 }, {
				wall({ name = "District", stream = "always", gaps = gaps }),
			})
			check.truthy(#parts > 400)
			check.equal(#many, 1)
			check.truthy(string.find(many[1], 'parts are marked "stream": "always"', 1, true))
			check.truthy(string.find(many[1], "400 at most", 1, true))
			-- ... a bad speed is the compiler's error too
			local _, _, speed = compile({ cell = 256, speed = "fast" }, {})
			check.equal(#speed, 1)
			check.truthy(string.find(speed[1], '"streaming.speed"', 1, true))
		end)

		test.case("a town says it of its landmark house; a word on the town itself is refused", function()
			local function town(more: any): any
				local t: any = {
					name = "Old Town",
					center = { 0, 0, 0 },
					area = { 256, 224 },
					seed = 3,
					gates = { "S" },
					bend = 0,
					market = false,
					yards = false,
					slope = false,
					mats = { street = "stone", block = "stone", wall = "stone", roof = "stone" },
				}
				for k, v in more do
					t[k] = v
				end
				return { town = t }
			end
			local model, _, errors = compile(
				{ cell = 256, speed = 16 },
				{ town({ landmark = { stream = "always" } }) },
				true
			)
			check.equal(#errors, 0)
			local always, houses = 0, 0
			for _, c in model.Children do
				if (c.Properties or {}).ModelStreamingMode == "Persistent" then
					always += 1
					check.truthy(string.find(c.Name, "Landmark", 1, true) ~= nil)
				end
				houses += if string.sub(c.Name, 1, 5) == "House" then 1 else 0
			end
			check.equal(always, 1) -- (the landmark house, and it alone)
			check.truthy(houses > 30)
			local _, _, whole = compile({ cell = 256, speed = 16 }, { town({ stream = "always" }) }, true)
			check.equal(#whole, 1)
			check.truthy(string.find(whole[1], "a town is not kept loaded as a whole", 1, true))
		end)

		test.case("arrivals: each an unseen part in a model that never streams out", function()
			local model, _, errors, extras = compile({
				cell = 256,
				speed = 40,
				fall = 90,
				arrivals = { { name = "Keep gate", pos = { 20, 0, 30 } }, { name = "Tower top", pos = { 0, 41, 0 } } },
			}, { { floor = { name = "Top", center = { 0, 40, 0 }, size = { 10, 10 }, mat = "stone" } } })
			check.equal(#errors, 0)
			local folder = child(model, "KitArrivals")
			check.equal(folder.Properties.ModelStreamingMode, "Persistent")
			check.equal(#folder.Children, 2)
			local gate = folder.Children[1]
			check.equal(gate.Name, "Keep gate")
			check.equal(gate.Properties.Transparency, 1)
			check.equal(gate.Properties.CanCollide, false)
			check.equal(gate.Properties.Anchored, true)
			check.equal(gate.Properties.Attributes.Attributes.KitArrival.String, "Keep gate")
			check.equal(gate.Properties.CFrame.CFrame.position[3], 30)
			-- what the world needs kept loaded rides along for the build's own report
			check.equal(extras.streaming.need, 160)
			check.equal(#extras.streaming.arrivals, 2)
			-- no arrivals: no model for them
			check.equal(child((compile({ cell = 256, speed = 16 }, {})), "KitArrivals"), nil)
		end)

		test.case("an arrival stands ON something and IN nothing", function()
			local function arrive(pos: { number }, steps: { any }, bare: boolean?): { string }
				local _, _, errors =
					compile({ cell = 256, speed = 16, arrivals = { { name = "There", pos = pos } } }, steps, bare)
				return errors
			end
			-- in the air (41 over the ground, nothing under it within 30), under the floor, off the map
			for _, pos in { { 200, 41, 200 }, { 20, -5, 30 }, { 5000, 0, 0 } } do
				local air = arrive(pos, {})
				check.equal(#air, 1)
				check.truthy(string.find(air[1], 'arrival "There"', 1, true))
				check.truthy(string.find(air[1], "stands on nothing", 1, true))
			end
			-- 30 studs over a floor is the most
			check.equal(#arrive({ 0, 30, 200 }, {}), 0)
			check.equal(#arrive({ 0, 30.6, 200 }, {}), 1)
			-- a part that does not collide is no floor (a rug of light, a banner laid flat)
			local ghost = {
				part = { name = "Glow", pos = { 100, 20, 100 }, size = { 20, 1, 20 }, mat = "stone", collide = false },
			}
			check.equal(#arrive({ 100, 20.5, 100 }, { ghost }, true), 1) -- (nothing else under it)
			local solid = { part = { name = "Deck", pos = { 100, 20, 100 }, size = { 20, 1, 20 }, mat = "stone" } }
			check.equal(#arrive({ 100, 20.5, 100 }, { solid }, true), 0)
			-- INSIDE a block, and under a slab too low to stand under (its underside 1.5 over the feet): refused
			local block = { part = { name = "Block", pos = { 100, 10, 100 }, size = { 20, 20, 20 }, mat = "stone" } }
			local inBlock = arrive({ 100, 5, 100 }, { block })
			check.equal(#inBlock, 1)
			check.truthy(string.find(inBlock[1], "stands inside Block", 1, true))
			local low = { part = { name = "Lintel", pos = { 100, 2, 100 }, size = { 20, 1, 20 }, mat = "stone" } }
			local under = arrive({ 100, 0, 100 }, { low })
			check.equal(#under, 1)
			check.truthy(string.find(under[1], "stands inside Lintel", 1, true))
			-- a ceiling 6 studs over the feet is room enough
			local high = { part = { name = "Ceiling", pos = { 100, 6.5, 100 }, size = { 20, 1, 20 }, mat = "stone" } }
			check.equal(#arrive({ 100, 0, 100 }, { high }), 0)
			-- on a RAMP with no ground under it: the player stands on its slope, not on the box round it. A slab 40
			-- long tilted 25 degrees about z, its middle at 50 up
			local ramp = {
				part = { name = "Ramp", pos = { 0, 50, 0 }, size = { 40, 1, 10 }, rot = { 0, 0, 25 }, mat = "stone" },
			}
			local function surface(x: number): number
				return 50 + math.tan(math.rad(25)) * x + 0.5 / math.cos(math.rad(25))
			end
			check.equal(#arrive({ -15, surface(-15) + 0.1, 0 }, { ramp }, true), 0)
			check.equal(#arrive({ 15, surface(15) + 0.1, 0 }, { ramp }, true), 0)
			-- ... over a stud INTO the ramp is inside it; beside the ramp there is nothing
			check.equal(#arrive({ -15, surface(-15) - 1.2, 0 }, { ramp }, true), 1)
			check.equal(#arrive({ -15, surface(-15) + 0.1, 30 }, { ramp }, true), 1)
		end)
	end)

	test.suite("Loading intent: the lock", function()
		local function lines(dir: string, words: string): { string }
			local out = {}
			for _, line in LaneLocks.world(nil, dir) do
				if string.find(line, words, 1, true) then
					table.insert(out, line)
				end
			end
			return out
		end

		test.case("the game's own streaming is read: plain numbers, Rojo's explicit forms, none, no project", function()
			local ok = LaneLocks.streamProps("kit/selftest/locks/worlds_intent_ok/default.project.json")
			check.equal(ok.min, 160)
			check.equal(ok.target, 1024)
			check.equal(ok.pause, true)
			local plain = LaneLocks.streamProps("kit/selftest/locks/worlds_intent/default.project.json")
			check.equal(plain.min, 64)
			check.equal(plain.target, 1024)
			check.equal(plain.pause, false)
			-- { "Float32": 200 }, { "Int32": 2048 }, { "Enum": 3 }
			local explicit = LaneLocks.streamProps("kit/selftest/locks/projects/explicit.project.json")
			check.equal(explicit.min, 200)
			check.equal(explicit.target, 2048)
			check.equal(explicit.pause, true)
			check.equal(LaneLocks.streamRadius("kit/selftest/locks/projects/explicit.project.json"), 200)
			check.equal(LaneLocks.streamProps("kit/selftest/locks/worlds_intent/no-such.project.json"), nil)
			check.equal(LaneLocks.streamProps("kit/selftest/locks/worlds_intent/UnsaidSpeed.json"), nil)
		end)

		test.case("a world that streams says how fast its players move - whatever its block says else", function()
			local said = lines("kit/selftest/locks/worlds_intent", "does not say how fast its players move")
			check.equal(#said, 1)
			check.truthy(string.find(said[1], "UnsaidSpeed: it streams", 1, true))
			check.truthy(string.find(said[1], '"speed"', 1, true))
			-- "lod": false: the reach rule does not count the block, the compiler still packs it - so it is asked
			check.equal(#lines("kit/selftest/locks/worlds_intent_lod", "does not say how fast its players move"), 1)
			check.equal(#lines("kit/selftest/locks/worlds_intent_fast", "does not say how fast"), 0)
			check.equal(#lines("kit/selftest/locks/worlds_intent_ok", "does not say how fast"), 0)
		end)

		test.case(
			"players faster than a walk: the radius, the target and the engine's own pause, each by name",
			function()
				local radius = lines("kit/selftest/locks/worlds_intent_fast", "StreamingMinRadius")
				check.equal(#radius, 1)
				check.truthy(string.find(radius[1], "FastRider: its players move 40 studs a second", 1, true))
				check.truthy(string.find(radius[1], "is 160 studs", 1, true))
				check.truthy(string.find(radius[1], "keeps 64", 1, true))
				check.truthy(string.find(radius[1], '"StreamingMinRadius": 160', 1, true))
				check.truthy(string.find(radius[1], "recommends 64", 1, true)) -- (what the bigger radius costs is said)
				local pause = lines("kit/selftest/locks/worlds_intent_fast", "PauseOutsideLoadedArea")
				check.equal(#pause, 1)
				check.equal(#lines("kit/selftest/locks/worlds_intent_fast", "StreamingTargetRadius"), 0) -- (320 of 1,024)
				-- 300 studs a second with the minimum set to 1,200: the target (Roblox's 1,024) is under it
				local target = lines("kit/selftest/locks/worlds_intent_target", "StreamingTargetRadius")
				check.equal(#target, 1)
				check.truthy(string.find(target[1], "Flyer: its players need 1200 studs", 1, true))
				check.truthy(string.find(target[1], "streams in to 1024", 1, true))
				check.truthy(string.find(target[1], "set it to 2400", 1, true))
				check.equal(#lines("kit/selftest/locks/worlds_intent_target", "StreamingMinRadius"), 0)
				-- the same fast rider where the game does not stream at all: the switch is the fault, no radius is held
				check.equal(#lines("kit/selftest/locks/worlds_intent_off", "does not turn streaming on"), 1)
				check.equal(#lines("kit/selftest/locks/worlds_intent_off", "StreamingMinRadius"), 0)
				check.equal(#lines("kit/selftest/locks/worlds_intent_off", "PauseOutsideLoadedArea"), 0)
				-- on foot with Roblox's own radius, and the rider whose game is ready: nothing to say
				for _, words in { "StreamingMinRadius", "StreamingTargetRadius", "PauseOutsideLoadedArea", "drop" } do
					check.equal(#lines("kit/selftest/locks/worlds_intent_mark", words), 0)
					check.equal(#lines("kit/selftest/locks/worlds_intent_ok", words), 0)
				end
			end
		)

		test.case("a drop past what the game keeps loaded needs its landing named", function()
			local said = lines("kit/selftest/locks/worlds_intent_fall", "its players drop 200 studs")
			check.equal(#said, 1)
			check.truthy(string.find(said[1], "LongDrop:", 1, true))
			check.truthy(string.find(said[1], "keeps 64 studs", 1, true))
			check.truthy(string.find(said[1], "WorldStream.ahead", 1, true))
			-- (the ready rider drops 300 with 160 kept: its landing is a named arrival)
			check.equal(#lines("kit/selftest/locks/worlds_intent_ok", "its players drop"), 0)
		end)

		test.case("a landmark of a world that streams says whether it streams out", function()
			local said = lines("kit/selftest/locks/worlds_intent_mark", "do not say whether they stream out")
			check.equal(#said, 1)
			check.truthy(string.find(said[1], "UnsaidMark: 1 landmark(s)", 1, true))
			check.truthy(string.find(said[1], '"Watch tower"', 1, true))
			check.equal(#lines("kit/selftest/locks/worlds_intent_ok", "do not say whether they stream out"), 0)
			local unsaid = LaneLocks.unsaidLandmarks({
				build = {
					{ tower = { name = "A", landmark = true } },
					{ tower = { name = "B", landmark = true, stream = "always" } },
					{ tower = { name = "C", landmark = true, stream = "area" } },
					{ tower = { name = "D", landmark = true, stream = "sometimes" } },
					{ tower = { name = "E" } },
					{ tower = { landmark = true } },
					-- the compiler's own landmarks: a tower of 60, a house of three storeys, a tree of 150
					{ tower = { name = "Tall", height = 60 } },
					{ tower = { name = "Short", height = 59 } },
					{ building = { name = "Hall", floors = 3 } },
					{ building = { name = "Hut", floors = 2 } },
					{ tree = { name = "Elder", height = 150 } },
					{ tower = { name = "Said", height = 80, stream = "area" } },
					{ tower = { name = "NotOne", height = 80, landmark = false } },
					-- a town always has its landmark house
					{ town = { name = "Old Town" } },
					{ town = { name = "Lit", landmark = { stream = "always" } } },
					{ town = { name = "Odd", landmark = { stream = "yes" } } },
				},
			})
			check.equal(
				table.concat(unsaid, " | "),
				"A | D | build[6].tower | Tall | Hall | Elder | Old Town's landmark | Odd's landmark"
			)
			check.equal(#LaneLocks.unsaidLandmarks(nil), 0)
		end)

		test.case(
			"the kit's proving game stood before the lane's locks (grandfathered): it is left as it is",
			function()
				for _, line in
					LaneLocks.world(
						{ "SampleRegion" },
						"games/SampleRegion/assets/worlds",
						"games/SampleRegion/default.project.json"
					)
				do
					check.falsy(string.find(line, "how fast its players move", 1, true))
					check.falsy(string.find(line, "whether they stream out", 1, true))
				end
			end
		)
	end)

	test.suite("Loading intent: sending a player to a place (the runtime, on stand-ins for the engine)", function()
		local function world(names: { [string]: any }): any
			local kids = {}
			for name, pos in names do
				table.insert(kids, {
					Position = pos,
					GetAttribute = function(_, k: string)
						return if k == "KitArrival" then name else nil
					end,
				})
			end
			local folder = {
				GetChildren = function()
					return kids
				end,
			}
			return {
				FindFirstChild = function(_, n: string)
					return if n == "KitArrivals" then folder else nil
				end,
			}
		end
		-- takes: how long Roblox takes to answer; it returns nothing either way (its own page)
		local function engine(root: any, takes: number?, throws: boolean?): any
			local e: any = { log = {}, warned = {}, clock = 100 }
			e.deps = {
				root = function()
					return root
				end,
				request = function(player: any, pos: any, timeout: number)
					table.insert(e.log, `request {player.Name} {pos} {timeout}`)
					e.clock += math.min(takes or 0.3, timeout)
					if e.during then
						e.during()
					end
					if throws then
						error("player is not in the game")
					end
				end,
				place = function(character: any, pos: any)
					table.insert(e.log, `place {character.Name} {pos}`)
				end,
				now = function()
					return e.clock
				end,
				warn = function(text: string)
					table.insert(e.warned, text)
				end,
			}
			return e
		end
		local function player(): any
			local workspace = {}
			return { Name = "Ada", Parent = {}, Character = { Name = "AdaChar", Parent = workspace } }
		end

		test.case("the ground is asked for FIRST, then the player is moved", function()
			local e = engine(world({ ["Keep gate"] = "P1", ["Tower top"] = "P2" }))
			local ok, why = WorldStream.arrive(player(), "Keep gate", e.deps)
			check.equal(ok, true)
			check.equal(why, nil)
			check.equal(table.concat(e.log, " | "), "request Ada P1 5 | place AdaChar P1")
			check.equal(#e.warned, 0)
		end)

		test.case("a place the world does not name, no world, a player who left or respawned meanwhile", function()
			local e = engine(world({ Gate = "P1" }))
			local ok, why = WorldStream.arrive(player(), "Nowhere", e.deps)
			check.equal(ok, false)
			check.truthy(string.find(why :: string, 'no arrival "Nowhere"', 1, true))
			check.equal(#e.log, 0)
			local none = engine(nil)
			check.equal((WorldStream.arrive(player(), "Gate", none.deps)), false)
			-- the request yields: the player leaves meanwhile - nobody is moved
			local gone = engine(world({ Gate = "P1" }))
			local p = player()
			gone.during = function()
				p.Parent = nil
			end
			local moved, left = WorldStream.arrive(p, "Gate", gone.deps)
			check.equal(moved, false)
			check.truthy(string.find(left :: string, "the player left", 1, true))
			check.equal(table.concat(gone.log, " | "), "request Ada P1 5")
			-- ... or their character is taken away (they died on the way)
			local dead = engine(world({ Gate = "P1" }))
			local q = player()
			dead.during = function()
				q.Character.Parent = nil
			end
			check.equal((WorldStream.arrive(q, "Gate", dead.deps)), false)
			local bare = engine(world({ Gate = "P1" }))
			local r = player()
			r.Character = nil
			check.equal((WorldStream.arrive(r, "Gate", bare.deps)), false)
			-- they died AND respawned while the ground loaded: the character they have NOW is the one moved
			local again = engine(world({ Gate = "P1" }))
			local s = player()
			again.during = function()
				s.Character.Parent = nil
				s.Character = { Name = "AdaNew", Parent = {} }
			end
			check.equal((WorldStream.arrive(s, "Gate", again.deps)), true)
			check.equal(again.log[2], "place AdaNew P1")
		end)

		test.case("Roblox gives a request up at its timeout and says nothing: told by the clock, and said", function()
			-- it took the whole 5 s: given up - the player is moved all the same, "late"
			local e = engine(world({ Gate = "P1" }), 5)
			local ok, why = WorldStream.arrive(player(), "Gate", e.deps)
			check.equal(ok, true)
			check.equal(why, "late")
			check.equal(table.concat(e.log, " | "), "request Ada P1 5 | place AdaChar P1")
			check.equal(#e.warned, 1)
			check.truthy(string.find(e.warned[1], 'arrival "Gate"', 1, true))
			-- 4.5 s is in time
			local quick = engine(world({ Gate = "P1" }), 4.5)
			local _, onTime = WorldStream.arrive(player(), "Gate", quick.deps)
			check.equal(onTime, nil)
			check.equal(#quick.warned, 0)
			-- a request that throws (it should not: a bad argument) is late too, never a crash
			local thrown = engine(world({ Gate = "P1" }), 0.1, true)
			local moved, late = WorldStream.arrive(player(), "Gate", thrown.deps)
			check.equal(moved, true)
			check.equal(late, "late")
		end)

		test.case("ahead asks for the ground and moves nobody (the top of a long drop)", function()
			local e = engine(world({ Landing = "P9" }))
			local ok, why = WorldStream.ahead(player(), "Landing", e.deps)
			check.equal(ok, true)
			check.equal(why, nil)
			check.equal(table.concat(e.log, " | "), "request Ada P9 5")
			check.equal((WorldStream.ahead(player(), "Nowhere", e.deps)), false)
			local slow = engine(world({ Landing = "P9" }), 9)
			local _, late = WorldStream.ahead(player(), "Landing", slow.deps)
			check.equal(late, "late")
		end)
	end)
end

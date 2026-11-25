-- worldsky.spec.luau (kit) — A SKY OF THE KIT'S OWN IN A WORLD'S LIGHTING (kit/lib/environment.luau "sky"; the owner's
-- method list: "Skyboxes"). The six pictures are rendered in Blender (kit world sky: kit/world/sky_blender.py, which
-- checks each run itself; its faces and words are tested in test_world_sky.py). Here the compile is held to what it
-- does with a sky's name: a sky that is not made is an error; one that is made and not uploaded is SAID and leaves
-- Roblox's own sky; one whose six pictures have ids is handed to the game, each id on its own face.
-- Not claimed here: that the sky is seen right in a game. That needs an upload, and a look.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Environment = require("../../lib/environment")
local SkyRules = require("../../../src/kit/SkyRules")
local World = require("../../lib/world")

local RECORD = {
	name = "Day",
	sun = { elevation = 39.8, azimuth = 51.3, vector = { 0.6, 0.64, -0.48 } },
	faces = { SkyboxFt = "Day_ft.png" },
}
local IDS =
	{ SkyboxBk = 101, SkyboxDn = 102, SkyboxFt = "rbxassetid://103", SkyboxLf = 104, SkyboxRt = 105, SkyboxUp = 106 }

-- the compile with what is known of skies given by hand (no files read)
local function compile(lighting: any, known: { [string]: any }): (any, { string }, { string })
	local read = Environment.readSky
	Environment.readSky = function(name: string)
		local k = known[name]
		return if k then k.record else nil, if k then k.ids else nil
	end
	local ok, env, issues = pcall(Environment.compile, { name = "T", lighting = lighting })
	Environment.readSky = read
	assert(ok, tostring(env))
	local errors, warns = {}, {}
	for _, i in issues do
		table.insert(if i.severity == "error" then errors else warns, i.message)
	end
	return env, errors, warns
end

return function()
	test.suite("A sky of the kit's own in a world's lighting", function()
		test.case("uploaded: each picture's id on its own face, the sun it was drawn with", function()
			local env, errors, warns = compile(
				{ preset = "noon", sky = "Day" },
				{ Day = { record = RECORD, ids = IDS } }
			)
			check.equal(#errors, 0, table.concat(errors, " | "))
			check.equal(#warns, 0)
			local sky = env.lighting.sky
			check.equal(sky.name, "Day")
			check.equal(sky.faces.SkyboxFt, "rbxassetid://103")
			check.equal(sky.faces.SkyboxBk, "rbxassetid://101")
			check.equal(sky.faces.SkyboxDn, "rbxassetid://102")
			check.equal(sky.faces.SkyboxLf, "rbxassetid://104")
			check.equal(sky.faces.SkyboxRt, "rbxassetid://105")
			check.equal(sky.faces.SkyboxUp, "rbxassetid://106")
			local n = 0
			for _ in sky.faces do
				n += 1
			end
			check.equal(n, 6)
			check.equal(`{sky.sun[1]} {sky.sun[2]} {sky.sun[3]}`, "0.6 0.64 -0.48")
			check.equal(sky.fixed, nil) -- (a sky of air and clouds is turned to the light)
			-- the rest of the lighting is as it was
			check.truthy(env.lighting.clockTime ~= nil)
			-- the six faces the compile knows are the Sky object's six
			check.equal(table.concat(Environment.FACES, " "), "SkyboxBk SkyboxDn SkyboxFt SkyboxLf SkyboxRt SkyboxUp")
		end)

		test.case("made and not uploaded: said, and Roblox's own sky stays", function()
			local env, errors, warns = compile({ preset = "noon", sky = "Day" }, { Day = { record = RECORD } })
			check.equal(#errors, 0)
			check.equal(#warns, 1)
			check.truthy(
				string.find(warns[1], 'the sky "Day" is not uploaded (6 of 6 pictures have no id', 1, true),
				warns[1]
			)
			check.truthy(string.find(warns[1], "skies.Day.SkyboxFt", 1, true), warns[1])
			check.truthy(string.find(warns[1], "kit upload does not take skies yet", 1, true))
			check.equal(env.lighting.sky, nil)
			-- five of six: the one that is missing is named, and no half sky is handed on
			local five = table.clone(IDS)
			five.SkyboxUp = nil
			env, errors, warns = compile({ preset = "noon", sky = "Day" }, { Day = { record = RECORD, ids = five } })
			check.equal(#errors, 0)
			check.truthy(string.find(warns[1], "1 of 6 pictures have no id: SkyboxUp)", 1, true), warns[1])
			check.equal(env.lighting.sky, nil)
			-- an id is a whole number over 0, or that number as a string (bare, or after rbxassetid://): nothing
			-- else is dug out of what stands there
			for _, bad in
				{ "soon", -5, 1.5, 0, "0", "v2-build-17", "https://x/9/y", {}, true, "rbxassetid://", "12 ", 2 ^ 60 } :: { any }
			do
				local odd = table.clone(IDS)
				odd.SkyboxFt = bad
				env, errors, warns = compile({ preset = "noon", sky = "Day" }, { Day = { record = RECORD, ids = odd } })
				check.equal(#errors, 0)
				check.truthy(#warns == 1 and string.find(warns[1], "SkyboxFt", 1, true) ~= nil, tostring(bad))
				check.equal(env.lighting.sky, nil)
			end
			for _, good in { 103, "103", "rbxassetid://103" } :: { any } do
				local fine = table.clone(IDS)
				fine.SkyboxFt = good
				env, errors, warns = compile(
					{ preset = "noon", sky = "Day" },
					{ Day = { record = RECORD, ids = fine } }
				)
				check.equal(#warns, 0, tostring(good))
				check.equal(env.lighting.sky.faces.SkyboxFt, "rbxassetid://103")
			end
		end)

		test.case("what is no sky is said", function()
			local function wrong(sky: any, known: any, text: string)
				local env, errors = compile({ preset = "noon", sky = sky }, known)
				check.truthy(#errors >= 1)
				check.truthy(string.find(table.concat(errors, " | "), text, 1, true), table.concat(errors, " | "))
				check.equal(env.lighting.sky, nil)
			end
			wrong(
				"Dusk",
				{ Day = { record = RECORD, ids = IDS } },
				'no sky "Dusk" - make it: lune run kit world sky Dusk'
			)
			-- a record that is there and cannot be read: said as that, not as "not made"
			wrong("Day", { Day = { record = { name = "Day" }, ids = IDS } }, "has no record that can be read")
			wrong("Day", { Day = { record = false, ids = IDS } }, "has no record that can be read")
			for _, vector in
				{
					{ 0.5, 0.5 },
					{ "a", "b", "c" },
					{},
					{ 0 / 0, 0, 1 },
					{ 3, 4, 0 },
					{ 0.1, 0.1, 0.1 },
					{ 0.6, 0.64, -0.48, 0 },
				} :: { any }
			do
				wrong(
					"Day",
					{ Day = { record = { name = "Day", sun = { vector = vector } }, ids = IDS } },
					"has no record that can be read"
				)
			end
			-- a key of the day's cycle cannot change the sky
			local env2, errors2 = compile({ preset = "noon", sky = "Day" }, { Day = { record = RECORD, ids = IDS } })
			check.equal(#errors2, 0)
			check.truthy(env2.lighting.sky ~= nil)
			local read = Environment.readSky
			Environment.readSky = function(_n: string)
				return RECORD, IDS
			end
			local _, dayIssues = Environment.compile({
				name = "T",
				lighting = { preset = "noon", sky = "Day" },
				day = {
					length = 600,
					keys = { { hour = 6, preset = "golden", sky = "Dusk" }, { hour = 18, preset = "night" } },
				},
			})
			Environment.readSky = read
			local saidKey = false
			for _, issue in dayIssues do
				saidKey = saidKey or string.find(issue.message, "a world has one sky", 1, true) ~= nil
			end
			check.truthy(saidKey)
			wrong(5, {}, "sky is the name of a sky")
			wrong("my sky", {}, "sky is the name of a sky")
			wrong("../Day", {}, "sky is the name of a sky")
			wrong(true, {}, "sky is the name of a sky")
			-- no sky asked: nothing said, nothing set
			local env, errors, warns = compile({ preset = "noon" }, {})
			check.equal(#errors + #warns, 0)
			check.equal(env.lighting.sky, nil)
		end)

		test.case("a world's compile carries the word on", function()
			local read = Environment.readSky
			Environment.readSky = function(_name: string)
				return RECORD, nil
			end
			local _, _, issues =
				World.compile({ name = "T", palette = {}, lighting = { preset = "noon", sky = "Day" }, build = {} })
			Environment.readSky = read
			local said = false
			for _, i in issues do
				said = said
					or (
						i.severity ~= "error"
						and string.find(i.message, 'the sky "Day" is not uploaded', 1, true) ~= nil
					)
				check.truthy(i.severity ~= "error", i.message)
			end
			check.truthy(said)
		end)

		test.case("a sky with far ridges stands as it was rendered", function()
			local ridged = table.clone(RECORD) :: any
			ridged.fixed = true
			ridged.ridges = { count = 2, height = 8 }
			local env, errors, warns = compile(
				{ preset = "noon", sky = "Day" },
				{ Day = { record = ridged, ids = IDS } }
			)
			check.equal(#errors, 0, table.concat(errors, " | "))
			check.equal(#warns, 0)
			check.equal(env.lighting.sky.fixed, true)
			-- the game's rule: a fixed sky has no drawn sun to turn by, any other has its own
			check.equal(SkyRules.drawn(env.lighting.sky), nil)
			check.equal(SkyRules.drawn({ faces = {}, sun = { 1, 0.5, 0 } }), 90)
			check.equal(SkyRules.drawn({ faces = {}, sun = { 0, 0.5, 1 }, fixed = false }), 180)
			check.equal(SkyRules.drawn({ faces = {}, sun = { 1, 0.5, 0 }, fixed = true }), nil)
			check.equal(SkyRules.drawn({ faces = {} }), nil)
			check.equal(SkyRules.drawn({ faces = {}, sun = { "1", 0, 0 } }), nil)
			check.equal(SkyRules.drawn({ faces = {}, sun = { 0, 1, 0 } }), nil) -- (straight up: no side)
			check.equal(SkyRules.drawn(nil), nil)
			-- only the record's own true fixes it; a word in its place is a damaged record
			for _, word in { "yes", 1, {} } :: { any } do
				local odd = table.clone(RECORD) :: any
				odd.fixed = word
				local _, bad = compile({ preset = "noon", sky = "Day" }, { Day = { record = odd, ids = IDS } })
				check.equal(#bad, 1)
				check.truthy(string.find(bad[1], "no record that can be read", 1, true))
			end
			local loose = table.clone(RECORD) :: any
			loose.fixed = false
			check.equal(
				compile({ preset = "noon", sky = "Day" }, { Day = { record = loose, ids = IDS } }).lighting.sky.fixed,
				nil
			)
			-- under a day's cycle the light moves and a fixed sky does not: said; a turned sky says nothing
			local function day(record: any): { string }
				local read = Environment.readSky
				Environment.readSky = function()
					return record, IDS
				end
				local ok, _, issues = pcall(Environment.compile, {
					name = "T",
					lighting = { preset = "noon", sky = "Day" },
					day = { length = 600, keys = { { hour = 6, preset = "golden" }, { hour = 12, preset = "noon" } } },
				})
				Environment.readSky = read
				assert(ok, "the compile crashed")
				local said = {}
				for _, i in issues do
					check.equal(i.severity, "warn")
					table.insert(said, i.message)
				end
				return said
			end
			local said = day(ridged)
			check.equal(#said, 1)
			check.truthy(string.find(said[1], "is not turned to the light", 1, true))
			check.equal(#day(RECORD), 0)
			-- said before the sky is uploaded too (a reader found it silent until all six ids stood)
			local read = Environment.readSky
			Environment.readSky = function()
				return ridged, nil
			end
			local _, early = Environment.compile({
				name = "T",
				lighting = { preset = "noon", sky = "Day" },
				day = { length = 600, keys = { { hour = 6, preset = "golden" }, { hour = 12, preset = "noon" } } },
			})
			Environment.readSky = read
			local turnedWord = 0
			for _, i in early do
				if string.find(i.message, "is not turned to the light", 1, true) then
					turnedWord += 1
				end
			end
			check.equal(turnedWord, 1)
		end)

		test.case("the turn that stands the drawn sun over the light", function()
			-- compass sides, from -Z round toward +X
			check.equal(SkyRules.azimuth(0, -1), 0)
			check.equal(SkyRules.azimuth(1, 0), 90)
			check.equal(SkyRules.azimuth(0, 1), 180)
			check.equal(SkyRules.azimuth(-1, 0), -90)
			check.equal(SkyRules.azimuth(0, 0), nil)
			-- a sun drawn in the north, the light from the east: a positive turn about Y takes degrees OFF an
			-- azimuth (it carries -Z toward -X), so the sky is turned by -90 to bring 0 to 90
			check.equal(SkyRules.turn(0, 0.8, 0.6, 0), -90)
			check.equal(SkyRules.turn(90, 0.8, 0.6, 0), 0) -- (drawn where the light is: no turn)
			check.equal(SkyRules.turn(90, 0, 0.6, -0.8), 90)
			check.equal(SkyRules.turn(180, 0.8, 0.6, 0), 90)
			-- the turn applied to the drawn sun brings it over the real one, whatever the two are
			for _, case in
				{ { 135, 0.3, 0.5, 0.8 }, { -170, -0.7, 0.2, -0.1 }, { 10, 0.05, 0.9, -0.4 }, { 179, -0.2, 0.3, 0.9 } }
			do
				local turn = SkyRules.turn(case[1], case[2], case[3], case[4]) :: number
				check.truthy(turn >= -180 and turn <= 180)
				local real = SkyRules.azimuth(case[2], case[4]) :: number
				check.truthy(math.abs(((case[1] - turn - real) + 180) % 360 - 180) < 1e-9)
			end
			check.truthy(math.abs((SkyRules.turn(170, -0.17365, 0.5, 0.98481) :: number) - -20) < 0.01) -- (170 to -170: the short way)
			-- at night, and with the sun straight overhead, the sky is left as it stands
			check.equal(SkyRules.turn(90, 0.8, -0.2, 0), nil)
			check.equal(SkyRules.turn(90, 0.8, 0.01, 0), nil)
			check.equal(SkyRules.turn(90, 0, 1, 0), nil)
			check.equal(SkyRules.NAME, "KitSky")
		end)
	end)
end

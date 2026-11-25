-- vfxmood.spec.luau (kit) — the client's one mood stack (src/kit/VfxMood.luau; the V3 doc, VFX stage B: "a
-- ref-counted priority mood stack"). Two world layers at once used to fight over Lighting (the second saved the first
-- one's sky, whichever ended last wrote its snapshot back); an impact frame's FogEnd = 1 is ignored under an
-- Atmosphere. The rules here run on a fake scene; the last case reads VfxStage's own source for its use of them.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local VfxMood = require("../../../src/kit/VfxMood")

local function scene(values: { [string]: any })
	local writes = 0
	local mood = VfxMood.new(function(key)
		return values[key]
	end, function(key, v)
		values[key] = v
		writes += 1
	end)
	return mood, values, function()
		return writes
	end
end

local function code(path: string): string
	local out = {}
	for line in string.gmatch(fs.readFile(path), "[^\n]+") do
		local cut = string.find(line, "--", 1, true)
		table.insert(out, if cut then string.sub(line, 1, cut - 1) else line)
	end
	return (string.gsub(table.concat(out, " "), "%s+", " "))
end

return function()
	test.suite("VfxMood", function()
		test.case("two effects at once end in EITHER order and the scene is its own again", function()
			for _, order in { { "a", "b" }, { "b", "a" } } do
				local mood, live = scene({ exposure = 0, ["atmo.density"] = 0.3 })
				local ids = { a = {}, b = {} }
				mood:push(ids.a, 0, { exposure = -2, ["atmo.density"] = 0.9 })
				-- the second reads the SCENE's value, not the first one's darkened sky
				check.equal(mood:baseOf("exposure"), 0)
				mood:push(ids.b, 0, { exposure = -1 })
				check.equal(live.exposure, -1) -- a tie: the latest pushed
				check.equal(live["atmo.density"], 0.9)
				mood:pop(ids[order[1]])
				mood:pop(ids[order[2]])
				check.equal(live.exposure, 0)
				check.equal(live["atmo.density"], 0.3)
				check.equal(mood:holders(), 0)
			end
		end)

		test.case("a higher priority wins its keys while it holds them; the rest show through", function()
			local mood, live = scene({ fogEnd = 500, ["atmo.color"] = "grey", ["atmo.glare"] = 0.4 })
			local world, frame = {}, {}
			mood:push(world, 0, { ["atmo.color"] = "orange", fogEnd = 200 })
			mood:push(frame, 10, { ["atmo.color"] = "paper", ["atmo.glare"] = 0 })
			mood:push(world, 0, { ["atmo.color"] = "red", fogEnd = 150 }) -- the world layer moves on underneath
			check.equal(live["atmo.color"], "paper")
			check.equal(live.fogEnd, 150)
			check.equal(live["atmo.glare"], 0)
			mood:pop(frame)
			check.equal(live["atmo.color"], "red") -- back to the world layer, not to the scene
			check.equal(live["atmo.glare"], 0.4) -- a key only the frame held: the scene's own
			mood:pop(world)
			check.equal(live["atmo.color"], "grey")
			check.equal(live.fogEnd, 500)
		end)

		-- LIMITATIONS_FIXES_V4 3.4 step 1: "fix VfxMood.luau to preserve Glare & Offset on stack pop". The impact frame's
		-- paper zeroes the Atmosphere's Glare and Offset (a world layer never pushes them): when the frame lets go, in
		-- either order with a world layer, both come back to the scene's own - including a scene value of 0 (falsy in
		-- no Luau sense, but a "zero = unset" slip would keep the paper's) - through VfxStage's REAL Atmosphere keys
		test.case("Glare and Offset come back to the scene's own when the impact frame pops (either order)", function()
			for _, order in { { "frame", "world" }, { "world", "frame" } } do
				for _, scenery in { { glare = 0.5, offset = 0.15 }, { glare = 0, offset = 0.25 } } do
					local mood, live = scene({
						["atmo.glare"] = scenery.glare,
						["atmo.offset"] = scenery.offset,
						["atmo.density"] = 0.36,
					})
					local ids = { world = {}, frame = {} }
					mood:push(ids.world, 0, { ["atmo.density"] = 0.6, ["atmo.haze"] = 3 })
					mood:push(ids.frame, 10, { ["atmo.density"] = 1, ["atmo.offset"] = 0, ["atmo.glare"] = 0 })
					check.equal(live["atmo.glare"], 0)
					check.equal(live["atmo.offset"], 0)
					mood:pop(ids[order[1]])
					mood:pop(ids[order[2]])
					check.equal(live["atmo.glare"], scenery.glare)
					check.equal(live["atmo.offset"], scenery.offset)
					check.equal(live["atmo.density"], 0.36)
					check.equal(mood:holders(), 0)
				end
			end
			-- the stage's reader / writer reach the Atmosphere's Glare and Offset (a key missing there is pushed, never
			-- read, never given back: the paper's 0 would stay for good)
			local stage = code("src/kit/VfxStage.luau")
			check.is_true(string.find(stage, '["atmo.offset"] = "Offset",', 1, true) ~= nil)
			check.is_true(string.find(stage, '["atmo.glare"] = "Glare",', 1, true) ~= nil)
			check.is_true(string.find(stage, "local a = ATMO_KEYS[key]", 1, true) ~= nil)
		end)

		test.case("a key an effect stops wanting goes back; nothing to read is never written", function()
			local mood, live, writes = scene({ exposure = 1 })
			local id = {}
			mood:push(id, 0, { exposure = 3, ["atmo.haze"] = 5 }) -- no Atmosphere: nothing read for atmo.haze
			check.equal(live.exposure, 3)
			mood:push(id, 0, { ["atmo.haze"] = 5 })
			check.equal(live.exposure, 1)
			local before = writes()
			mood:pop(id)
			check.equal(live["atmo.haze"], 5) -- (written while held, as the engine ignores a missing Atmosphere)
			check.equal(writes(), before) -- its base was nothing: no write back
			mood:pop(id) -- an unknown id: nothing happens
			mood:pop({})
			check.equal(mood:holders(), 0)
		end)

		test.case(
			"after the last lets go the scene is read AGAIN (a day / night change between effects is kept)",
			function()
				local mood, live = scene({ brightness = 2 })
				local id = {}
				mood:push(id, 0, { brightness = 4 })
				mood:pop(id)
				live.brightness = 3 -- the game's own change, between two effects
				mood:push(id, 0, { brightness = 5 })
				mood:pop(id)
				check.equal(live.brightness, 3)
			end
		)

		test.case(
			"VfxStage's world layer and impact frame go through the stack (no Lighting written directly)",
			function()
				local stage = code("src/kit/VfxStage.luau")
				local function has(s: string): boolean
					return string.find(stage, s, 1, true) ~= nil
				end
				check.is_true(has("local mood = VfxMood.new("))
				check.is_true(has("mood:push(frame.id, 10, {")) -- the impact frame, over any world layer
				check.is_true(has('["atmo.density"] = 1,')) -- the paper fills the Atmosphere, not FogEnd alone
				check.is_true(has('["atmo.glare"] = 0,'))
				check.is_true(has('["atmo.offset"] = 0,'))
				check.is_true(has("mood:push(id, 0, want)")) -- the world layer
				check.is_true(has("mood:pop(id)"))
				check.is_true(has("mood:pop(frame.id)"))
				for _, prop in
					{ "FogEnd", "FogStart", "FogColor", "ExposureCompensation", "Brightness", "OutdoorAmbient" }
				do
					check.is_true(not has(`Lighting.{prop} =`)) -- only the stack's writer touches them
				end
				check.is_true(not string.find(stage, "atmo%.Density%s*="))
			end
		)
	end)
end

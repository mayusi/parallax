-- harnessnoise.spec.luau (kit) — the playtest harness's console filter (kit/qa/harness.luau gameError): a red line from
-- Studio itself is not the game's and never fails a playtest; every other red line does. Found in Studio 2026-11-21 by
-- tests/playtest/kit_integration_arena: a 2-player test's server logged "Unable to load plugin icon: rbxassetid://..."
-- as an error (lower-case "plugin": the filter matched "Plugin" only) and the arena failed on Studio's own noise.
-- The function is read out of the harness text and run here (it is pure: string.find on the message).
local fs = require("@lune/fs")
local luau = require("@lune/luau")

local frk = require("../frk")
local test, check = frk.test, frk.check

local function gameErrorFromHarness(): (string) -> boolean
	local src = fs.readFile("kit/qa/harness.luau")
	local body = string.match(src, "(local function gameError%(.-\nend)\n")
	assert(body, "kit/qa/harness.luau has no gameError function")
	return luau.load(body .. "\nreturn gameError", { debugName = "harness.gameError" })()
end

return function()
	test.suite("playtest harness: Studio's own console lines are not the game's", function()
		local gameError = gameErrorFromHarness()
		test.case("Studio and plugin lines are noise, whatever their case", function()
			for _, msg in
				{
					"Unable to load plugin icon: rbxassetid://10000000004",
					"Plugin_123.Main:4: something",
					"BuiltInPlugins.Foo: bar",
					"CoreGui.RobloxGui.Modules: x",
					"CorePackages.Workspace: y",
					"StudioService: z",
					"[Roblox][Script Context.StarterScript] Script Context.StarterScript:507: Invalid value for enum CreatorType",
				}
			do
				check.equal(gameError(msg), false, msg)
			end
		end)
		test.case("a game script's error still counts", function()
			for _, msg in
				{
					"ServerScriptService.KitArenaServer:12: attempt to index nil with 'Name'",
					"ReplicatedStorage.kit.Moves:300: boom",
					"Infinite yield possible on 'ReplicatedStorage:WaitForChild(\"KitArenaLink\")'",
				}
			do
				check.equal(gameError(msg), true, msg)
			end
		end)
	end)
end

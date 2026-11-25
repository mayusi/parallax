-- audio_api_graph.spec.luau (kit) — the kit's sound modules are on ONE Audio API graph (PARALLAX_FINAL_CLOSURE_SPEC
-- Step 6, SFX-X): Sfx and the six that used the legacy objects (EchoZones, Music, Ambience, WindVoice, GustEvents, Foley)
-- plus Assets (Foley's bridge) create no Sound, SoundGroup or legacy SoundEffect and type nothing as one; GustEvents
-- times its gusts on the game's one clock, not os.clock. A source check: the graph itself is held in Studio by the
-- sfx_graph / sfx_acoustic_sync playtests.
local fs = require("@lune/fs")

local frk = require("../frk")
local test, check = frk.test, frk.check

local MODULES = { "Sfx", "EchoZones", "Music", "Ambience", "WindVoice", "GustEvents", "Foley", "Assets" }
local LEGACY = {
	'Instance.new%("Sound"%)',
	'Instance.new%("SoundGroup"%)',
	'Instance.new%("%a*SoundEffect"%)',
	"SoundService",
	"%f[%w]SoundGroup%f[%W]",
	":%s*Sound%f[%W]", -- (a value typed as a legacy Sound)
	"EqualizerSoundEffect",
}

-- the module's CODE: its comments left out (a header may tell the story of what it replaced)
local function code(name: string): string
	local text = fs.readFile(`src/kit/{name}.luau`)
	text = string.gsub(text, "%-%-%[(=*)%[.-%]%1%]", "")
	text = string.gsub(text, "%-%-[^\n]*", "")
	return text
end

return function()
	test.suite("audio: the kit's sound modules on the Audio API", function()
		test.case("no legacy Sound / SoundGroup / SoundEffect in any of them", function()
			local found = {}
			for _, m in MODULES do
				local c = code(m)
				for _, pat in LEGACY do
					if string.find(c, pat) then
						table.insert(found, `{m}: {pat}`)
					end
				end
			end
			check.equal(table.concat(found, "; "), "")
		end)

		test.case("the modules play through kit Sfx's graph", function()
			for _, m in { "Music", "Ambience", "WindVoice", "GustEvents" } do
				check.is_true(string.find(code(m), "Sfx.voice(", 1, true) ~= nil)
			end
			check.is_true(string.find(code("EchoZones"), ".voice(", 1, true) ~= nil)
			check.is_true(string.find(code("Assets"), ".voice(", 1, true) ~= nil) -- (Foley plays through Assets.play)
			check.is_true(string.find(code("Sfx"), 'Instance.new("AudioPlayer")', 1, true) ~= nil)
		end)

		test.case("GustEvents times on the game's one clock", function()
			local c = code("GustEvents")
			check.is_true(string.find(c, "os.clock", 1, true) == nil)
			check.is_true(string.find(c, "GetServerTimeNow", 1, true) ~= nil)
		end)
	end)
end

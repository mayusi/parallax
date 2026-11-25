-- engine.spec.luau (kit) — the engine seam (docs/ENGINES.md): a project names its engine in kit.config.json; "roblox"
-- is the default and the only one with emitters today; a planned engine (godot, unreal, unity) is answered with the
-- roadmap, an unknown one with the choices - never silently treated as Roblox.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Config = require("../../lib/config")

return function()
	test.suite("engine seam", function()
		test.case("roblox is the default and works; planned and unknown engines are said, not assumed", function()
			local cfg = Config.load()
			local was = cfg.engine
			check.equal(Config.DEFAULTS.engine, "roblox")
			cfg.engine = nil
			check.equal((Config.engine()), "roblox")
			cfg.engine = "Roblox"
			check.equal((Config.engine()), "roblox")
			cfg.engine = "godot"
			local e, why = Config.engine()
			check.equal(e, nil)
			check.truthy(why and string.find(why, "docs/ENGINES.md", 1, true))
			cfg.engine = "cryengine"
			local e2, why2 = Config.engine()
			check.equal(e2, nil)
			check.truthy(why2 and string.find(why2, "unknown engine", 1, true))
			cfg.engine = was
		end)
	end)
end

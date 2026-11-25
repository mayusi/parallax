-- profilecore.spec.luau (kit) — `--profile core` (kit/lib/config.luau Config.profile / excludedGames, kit/lib/lanelocks
-- LaneLocks.roots): a project keeps its own private games / move dossiers out of the kit's gates by listing them in
-- profiles.core (the kit ships it EMPTY). With no profile every game is walked; with core the games in
-- profiles.core.exclude_games are not; "all" is no profile; an unknown profile is refused by name rather than silently
-- walking everything.
local process = require("@lune/process")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Config = require("../../lib/config")
local LaneLocks = require("../../lib/lanelocks")

local function has(list: { string }, want: string): boolean
	for _, v in list do
		if v == want then
			return true
		end
	end
	return false
end

return function()
	test.suite("profile core: a project's private games out of the kit's gates", function()
		test.case("the kit ships the core profile empty", function()
			local core = Config.DEFAULTS.profiles.core
			check.equal(next(core.exclude_games), nil)
			check.equal(next(core.exclude_dossiers), nil)
			check.equal(next(core.exclude_patterns), nil)
		end)
		test.case("no profile, all, core, and an unknown one", function()
			-- (both names, as Config.setEnv writes them: Config.env reads PARALLAX_PROFILE first, and kit prove hands
			-- its sandbox's verify a real PARALLAX_PROFILE=core - a case that set only KIT_PROFILE read "core" there)
			local was, wasP = process.env.KIT_PROFILE, process.env.PARALLAX_PROFILE
			local function profile(v: string?)
				process.env.KIT_PROFILE = v
				process.env.PARALLAX_PROFILE = v
			end
			profile(nil)
			check.equal(Config.profile(), nil)
			check.equal(next(Config.excludedGames()), nil)
			check.equal(next(Config.excludedDossiers()), nil)
			local everyRoot = LaneLocks.roots()
			check.truthy(has(everyRoot, "")) -- (the kit's home is always walked)
			profile("all")
			check.equal(Config.profile(), nil)
			profile("core")
			check.equal(Config.profile(), "core")
			-- a project that lists its own private game + dossier (a fixture: the kit itself lists nothing)
			local cfg = Config.load()
			local saved = cfg.profiles.core
			cfg.profiles.core = { exclude_games = { "SamplePrivateGame" }, exclude_dossiers = { "sample_dossier" } }
			check.equal(Config.excludedGames().SamplePrivateGame, true)
			check.equal(Config.excludedDossiers().sample_dossier, true)
			local core = LaneLocks.roots()
			check.truthy(not has(core, "games/SamplePrivateGame/"))
			check.truthy(has(core, ""))
			cfg.profiles.core = saved
			profile("nosuch")
			local ok, err = pcall(Config.excludedGames)
			check.equal(ok, false)
			check.truthy(string.find(tostring(err), "no such profile", 1, true) ~= nil)
			process.env.KIT_PROFILE = was
			process.env.PARALLAX_PROFILE = wasP
		end)
	end)
end

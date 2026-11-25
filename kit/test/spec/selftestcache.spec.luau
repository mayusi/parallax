-- selftestcache.spec.luau (kit) — `kit selftest`'s fast paths (kit/lib/selftestcache.luau, owner 2026-11-20): a case's
-- lane is its label's first word; the flags pick lanes, turn the cache on or off, and refuse an unknown lane; a
-- linked worktree (kit prove's sandbox) runs cold unless asked.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Cache = require("../../lib/selftestcache")

return function()
	test.suite("selftest cache: lanes and flags", function()
		test.case("a label's first word names its lane", function()
			check.equal(Cache.laneOf("3d sliver gate (a 0.5 mm skin)"), "3d")
			check.equal(Cache.laneOf("blender gate"), "3d")
			check.equal(Cache.laneOf("vfx dailies (made clips)"), "vfx")
			check.equal(Cache.laneOf("anim dossier gate"), "anim")
			check.equal(Cache.laneOf("world reach gate"), "world")
			check.equal(Cache.laneOf("audio loudness"), "sfx")
			-- PROMPT-X has its own lane (PARALLAX_FINAL_CLOSURE_SPEC A2: kit/prompt + kit/selftest/prompt), so an edit
			-- there re-runs its cases, not every Blender fixture; a label naming no lane still keys on the whole kit
			check.equal(Cache.laneOf("prompt-x trap"), "prompt")
			check.equal(Cache.laneOf("harness drift"), "kit")
			check.equal(Cache.laneOf(""), "kit")
		end)
		test.case("flags: lanes, cache on/off, a primary checkout vs a linked worktree", function()
			local o = Cache.options({}, true)
			check.equal(o.cache, true)
			check.equal(o.lanes, nil)
			check.equal(Cache.options({}, false).cache, false) -- (kit prove's sandbox: cold)
			check.equal(Cache.options({ "--cache" }, false).cache, true)
			check.equal(Cache.options({ "--no-cache" }, true).cache, false)
			o = Cache.options({ "--lane", "3d,vfx" }, true)
			check.equal((o.lanes :: any)["3d"], true)
			check.equal((o.lanes :: any).vfx, true)
			check.equal((o.lanes :: any).anim, nil)
			o = Cache.options({ "--lane=blender" }, true)
			check.equal((o.lanes :: any)["3d"], true)
			check.truthy(Cache.options({ "--lane", "nosuch" }, true).bad ~= nil)
			check.truthy(Cache.options({ "--lane" }, true).bad ~= nil)
			check.equal(Cache.options({ "--changed" }, true).changed, true)
			-- --jobs N: the lanes at once (8 by default; 1 = one case at a time)
			check.equal(Cache.options({}, true).jobs, 8)
			check.equal(Cache.options({ "--jobs", "1" }, true).jobs, 1)
			check.equal(Cache.options({ "--jobs", "4" }, true).jobs, 4)
			check.equal(Cache.options({ "--jobs=3" }, true).jobs, 3)
			check.truthy(Cache.options({ "--jobs", "0" }, true).bad ~= nil)
			check.truthy(Cache.options({ "--jobs" }, true).bad ~= nil)
		end)
	end)
end

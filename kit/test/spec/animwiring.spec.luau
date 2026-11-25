-- animwiring.spec.luau — the build's two calls of the KEPT check are there (kit/cmd/anim.luau; card r66z: "the
-- build's two calls of the kept check are proven by no build in a made project - deleting either call fails no
-- test"; the owner's V3 list, anim stage F.1). Read from the command's own source: the verify gate in compile, and
-- the named build's "strips + motion gates" step, each fails the build on a clip that drifted from his poses.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local function body(text: string, from: string, upto: string): string
	local a = string.find(text, from, 1, true)
	if not a then
		return ""
	end
	local b = string.find(text, upto, a + #from, true) or #text
	return string.sub(text, a, b)
end

return function()
	test.suite("the kept check is wired into the build (kit/cmd/anim.luau)", function()
		local src = fs.readFile("kit/cmd/anim.luau")
		test.case("compile (kit verify's anim gate) holds every source's clip to his approved poses", function()
			local compile = body(src, "function AnimCmd.compile(", "\nfunction AnimCmd.")
			check.truthy(#compile > 0)
			local at = string.find(compile, "AnimCmd.keptStep(src.name)", 1, true)
			check.truthy(at ~= nil)
			-- ... and a drifted clip is an ERROR there, not a note
			local after = string.sub(compile, at or 1, (at or 1) + 300)
			check.truthy(string.find(after, "errors += 1", 1, true) ~= nil)
		end)
		test.case("the named build's motion-gates step fails on a drifted clip", function()
			local at = string.find(src, "local kept = AnimCmd.keptStep(n)", 1, true)
			check.truthy(at ~= nil)
			local after = string.sub(src, at or 1, (at or 1) + 160)
			check.truthy(string.find(after, "return kept", 1, true) ~= nil)
		end)
	end)
end

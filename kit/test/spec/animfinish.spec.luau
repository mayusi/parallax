-- animfinish.spec.luau — ONE FINISHING CONTRACT, the build's side (the owner's limitations list, 2026-11-15, A-R09):
-- a KEYED source (a keyframe spec) that says "finish" carries the ask onto its clip and through the fold, the build's
-- own step (AnimCmd.finish -> kit/anim/finish.py `apply`) finishes its fold to R6 (the curve tools read R6) and
-- stamps it, a finish that is refused comes back with its reason, and the build still applies it at the one place
-- every route's clip passes. The contract itself and the other routes: kit/test/python/test_anim_finish.py.
local frk = require("../frk")
local fs = require("@lune/fs")
local test, check = frk.test, frk.check

local Anim = require("../../lib/anim")
local AnimCmd = require("../../cmd/anim")

local function spec(finish: any): any
	return {
		name = "SpecFinish",
		rig = "R6",
		fps = 30,
		keys = {
			{ t = 0, pose = { Torso = { 0, 0, 0 }, Head = { 0, 0, 0 }, ["Right Arm"] = { 0, 0, 0 } } },
			{ t = 0.4, pose = { Torso = { 0, 30, 0 }, Head = { 10, -20, 0 }, ["Right Arm"] = { 110, 0, 0 } } },
			{ t = 1.0, pose = { Torso = { 0, 0, 0 }, Head = { 0, 0, 0 }, ["Right Arm"] = { 0, 0, 0 } } },
		},
		events = { { name = "Hit", t = 0.4 } },
		finish = finish,
	}
end

-- the keyed source as the build has it when it finishes it: compiled, then folded to R6
local function folded(finish: any): any
	return Anim.foldToR6(Anim.clipFromSpec(spec(finish), {}) :: any)
end

return function()
	test.suite("one finishing contract: a keyed source through the build's own step", function()
		test.case(
			"the ask rides on the clip and through the fold; the step finishes the R6 clip and stamps it",
			function()
				local ask = { filter = { hz = 10, joints = { "Head" } }, velocity = { max_deg_s = 5000 } }
				local clip = Anim.clipFromSpec(spec(ask), {})
				check.truthy(clip ~= nil and (clip :: any).finish == ask)
				local r6 = Anim.foldToR6(clip :: any) :: any
				check.truthy(r6.rig == "R6" and r6.finish == ask)
				local done, why = AnimCmd.finish("SpecFinish", r6)
				check.truthy(done ~= nil and why == nil)
				check.truthy(type(done.finished) == "string" and #done.finished == 16)
				check.equal(#done.finish_log, 2)
				check.truthy(string.find(done.finish_log[1], "filter", 1, true) == 1)
				check.truthy(string.find(done.finish_log[2], "velocity", 1, true) == 1)
				-- its length and its events are the spec's own
				check.equal(#done.times, #r6.times)
				check.truthy(done.events[1].name == "Hit" and math.abs(done.events[1].t - 0.4) < 1e-9)
				-- finished once: the step hands a stamped clip back as it is
				local again = AnimCmd.finish("SpecFinish", done)
				check.truthy(again ~= nil and again.finished == done.finished and #again.finish_log == 2)
				-- the clip in its R15 names is not what is finished: said, not guessed at
				local d15, why15 = AnimCmd.finish("SpecFinish", clip)
				check.truthy(
					d15 == nil and string.find(why15 :: string, "a finish is applied to the R6 clip", 1, true) ~= nil
				)
			end
		)
		test.case("a spec that asks for nothing carries nothing", function()
			local clip = Anim.clipFromSpec(spec(nil), {})
			check.truthy(clip ~= nil and (clip :: any).finish == nil)
			check.truthy(folded(nil).finish == nil and folded(nil).finished == nil)
		end)
		test.case("a finish that is refused comes back with its reason", function()
			local d1, why1 = AnimCmd.finish("SpecFinish", folded({ velocity = { max_deg_s = 1 } }))
			check.truthy(d1 == nil and string.find(why1 :: string, "still turns", 1, true) ~= nil)
			local d2, why2 = AnimCmd.finish("SpecFinish", folded({ polish = true }))
			check.truthy(d2 == nil and string.find(why2 :: string, 'has no "polish"', 1, true) ~= nil)
			local d3, why3 = AnimCmd.finish("SpecFinish", folded({ handles = { { from = 0.3, to = 0.5 } } }))
			check.truthy(d3 == nil and string.find(why3 :: string, "Hit", 1, true) ~= nil) -- (a Hit inside the stretch)
		end)
		test.case(
			"the build applies it where every route's clip passes, and every route's source may say it",
			function()
				local build = fs.readFile("kit/cmd/anim.luau")
				for _, line in
					{
						"if (clip :: any).finish ~= nil then",
						"done, why = AnimCmd.finish(src.name, r6c)",
						'its finish ("finish") was refused',
						'{ "kit/anim/finish.py", "apply", inPath, "--out", outPath }',
					}
				do
					check.truthy(string.find(build, line, 1, true) ~= nil)
				end
				-- AFTER the fold (the R6 clip is what is finished) and BEFORE the clip's metadata and models are made of it
				local at = string.find(build, "done, why = AnimCmd.finish(src.name, r6c)", 1, true) :: number
				local fold = string.find(build, "local folded, foldIssues = Anim.foldToR6(clip)", 1, true) :: number
				local meta = string.find(build, "metas[src.name] = {", 1, true) :: number
				check.truthy(fold < at and at < meta)
				-- a move, a gait, an import, a pose file: their source file's "finish" is merged onto the route's clip
				check.truthy(string.find(build, '"upper",\n\t\t\t"finish",\n\t\t\t"target",', 1, true) ~= nil)
				local gates = fs.readFile("kit/anim/metrics.py")
				check.truthy(string.find(gates, "finished, unfinished = FN.gate(clip)", 1, true) ~= nil)
			end
		)
	end)
end

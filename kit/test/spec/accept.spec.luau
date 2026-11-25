-- accept.spec.luau — the accept ratchet for every kind (kit/qa/accept.luau): one fixture per kind, measured, then a
-- worse build fails, a changed look is only a note, and a floor needs the owner's >= 7 and moves down only by them.
local frk = require("../frk")
local test, check = frk.test, frk.check

local fs = require("@lune/fs")
local serde = require("@lune/serde")

local Accept = require("../../qa/accept")

local FIX = "build/_acceptfix/"

local function put(rel: string, data: any)
	local path = FIX .. rel
	local cur = ""
	local parts = string.split(path, "/")
	for i = 1, #parts - 1 do
		cur = if cur == "" then parts[i] else cur .. "/" .. parts[i]
		if not fs.isDir(cur) then
			fs.writeDir(cur)
		end
	end
	fs.writeFile(path, if type(data) == "string" then data else serde.encode("json", data))
end

local function fresh()
	if fs.isDir("build/_acceptfix") then
		fs.removeDir("build/_acceptfix")
	end
end

-- a stand-in vault: { ["kind/name"] = score }
local scores: { [string]: number } = {}
local realVerdict = Accept.verdictOf
local function stub()
	Accept.verdictOf = function(kind: string, name: string): (number?, any)
		local s = scores[kind .. "/" .. name]
		return s, if s then { front = { date = "2026-10-16" }, rel = "fixture" } else nil
	end
end

local function warnings(n: number, e: number?): (string) -> any
	return function(_: string): any
		return { summary = `{e or 0} error(s), {n} warning(s)` }
	end
end

local function floorOf(m: Accept.Measure): any
	return { numbers = m.numbers, hashes = m.hashes, verdict = { score = 8 } }
end

return function()
	test.suite("kit accept — measures per kind", function()
		test.case("vfx: booth checks failed is the number; one more failure breaks the floor", function()
			fresh()
			put("assets/effects/fx.json", { beats = {} })
			put(
				"build/vfx/booth/fx_play.metrics.json",
				{ views = { hero = { checks = { { ok = true }, { ok = false } } } } }
			)
			local m = Accept.measure("vfx", "fx", FIX)
			check.equal(m.numbers.booth_failed, 1)
			put(
				"build/vfx/booth/fx_play.metrics.json",
				{ views = { hero = { checks = { { ok = false }, { ok = false } } } } }
			)
			local fails = Accept.compare(floorOf(m), Accept.measure("vfx", "fx", FIX))
			check.equal(#fails, 1)
		end)
		test.case("screen: a changed spec is a note for the owner's eye, never a failure", function()
			fresh()
			put("assets/ui/Scr.json", { a = 1 })
			put("build/ui/Scr.png", "png-1")
			local m = Accept.measure("screen", "Scr", FIX)
			check.is_true(m.hashes.source ~= nil and m.hashes.evidence ~= nil)
			put("assets/ui/Scr.json", { a = 2 })
			local fails, notes = Accept.compare(floorOf(m), Accept.measure("screen", "Scr", FIX))
			check.equal(#fails, 0)
			check.equal(#notes, 1)
		end)
		test.case("sound: the owner's newest verdict is the measure; below the floor past 1 point fails", function()
			fresh()
			stub()
			put("assets/sounds/snd.json", { layers = {} })
			scores["sound/snd"] = 8
			local m = Accept.measure("sound", "snd", FIX)
			check.equal(m.numbers.owner_score, 8)
			scores["sound/snd"] = 7.5
			check.equal(#(Accept.compare(floorOf(m), Accept.measure("sound", "snd", FIX))), 0)
			scores["sound/snd"] = 6
			check.equal(#(Accept.compare(floorOf(m), Accept.measure("sound", "snd", FIX))), 1)
			Accept.verdictOf = realVerdict
		end)
		test.case("world: check errors never rise; warnings may drift by 2", function()
			fresh()
			put("assets/worlds/W.json", { build = {} })
			put("build/worlds/W.json", { parts = {} })
			local m = Accept.measure("world", "W", FIX, warnings(3))
			check.equal(m.numbers.check_errors, 0)
			check.equal(m.numbers.check_warnings, 3)
			check.equal(#(Accept.compare(floorOf(m), Accept.measure("world", "W", FIX, warnings(5)))), 0)
			check.equal(#(Accept.compare(floorOf(m), Accept.measure("world", "W", FIX, warnings(6)))), 1)
			check.equal(#(Accept.compare(floorOf(m), Accept.measure("world", "W", FIX, warnings(3, 1)))), 1)
		end)
		test.case("anim: a clip that gains a measured problem breaks the floor", function()
			fresh()
			put("assets/animations/A.json", { keys = {} })
			put("build/animations/A.metrics.json", { problems = {} })
			local m = Accept.measure("anim", "A", FIX)
			check.equal(m.numbers.problems, 0)
			put("build/animations/A.metrics.json", { problems = { "foot slides 12 studs" } })
			check.equal(#(Accept.compare(floorOf(m), Accept.measure("anim", "A", FIX))), 1)
		end)
		test.case("system: a dropped spec case or regression case breaks the floor", function()
			fresh()
			local spec = 'test.case("a", function() end)\ntest.case("b", function() end)\n'
			put("sys/tests/x.spec.luau", spec)
			put("sys/tests/regressions.json", { cases = { { id = "r1" } } })
			put("sys/src/shared/XRules.luau", "return {}")
			local m = Accept.measure("system", "Sys", FIX .. "sys/")
			check.equal(m.numbers.spec_cases, 2)
			check.equal(m.numbers.regression_cases, 1)
			put("sys/tests/x.spec.luau", 'test.case("a", function() end)\n')
			check.equal(#(Accept.compare(floorOf(m), Accept.measure("system", "Sys", FIX .. "sys/"))), 1)
			put("sys/tests/x.spec.luau", spec)
			put("sys/tests/regressions.json", { cases = {} })
			check.equal(#(Accept.compare(floorOf(m), Accept.measure("system", "Sys", FIX .. "sys/"))), 1)
		end)
		test.case("a missing piece or an unknown kind is named, never measured as zero", function()
			fresh()
			check.is_true(Accept.measure("vfx", "nothing", FIX).missing ~= nil)
			check.is_true(Accept.measure("teapot", "x", FIX).missing ~= nil)
		end)
	end)

	test.suite("kit accept — the owner's floor", function()
		test.case("no owner verdict >= 7: no floor", function()
			fresh()
			stub()
			put("assets/animations/A.json", { keys = {} })
			scores["anim/A"] = 6.5
			local ok = Accept.accept("anim", "A", FIX, "", false)
			check.is_false(ok)
			check.is_false(fs.isFile(Accept.floorPath(FIX, "anim", "A")))
			Accept.verdictOf = realVerdict
		end)
		test.case("rated >= 7: the floor is written; a worse build is refused; only the owner lowers it", function()
			fresh()
			stub()
			put("assets/animations/A.json", { keys = {} })
			put("build/animations/A.metrics.json", { problems = {} })
			scores["anim/A"] = 8
			local ok, _, _, path = Accept.accept("anim", "A", FIX, "the owner's words", false)
			check.is_true(ok)
			local floor = serde.decode("json", fs.readFile(path :: string))
			check.equal(floor.numbers.problems, 0)
			check.equal(floor.verdict.score, 8)
			put("build/animations/A.metrics.json", { problems = { "pop" } })
			check.is_false((Accept.accept("anim", "A", FIX, "", false)))
			local refuse = function(_: string, _: string): (boolean, string?)
				return false, "no terminal"
			end
			check.is_false((Accept.accept("anim", "A", FIX, "", true, nil, refuse)))
			check.equal(serde.decode("json", fs.readFile(path :: string)).numbers.problems, 0)
			local owner = function(_: string, _: string): (boolean, string?)
				return true, nil
			end
			check.is_true((Accept.accept("anim", "A", FIX, "", true, nil, owner)))
			local lowered = serde.decode("json", fs.readFile(path :: string))
			check.equal(lowered.numbers.problems, 1)
			check.is_true(lowered.lowered)
			Accept.verdictOf = realVerdict
			fresh()
		end)
	end)
end

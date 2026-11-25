-- chainbackground.spec.luau (kit) — Run.background (PARALLAX_FINAL_CLOSURE_SPEC A3, 2026-11-22): a step marked as
-- background STARTS when the chain starts (kit verify's ~47-minute Python lane no longer waits for format, selene,
-- types and the Luau specs) and is JOINED at its own place in the plan, so the report keeps the declared order; a
-- background step that crashes is one more red, never the end of the run.
local fs = require("@lune/fs")
local serde = require("@lune/serde")
local task = require("@lune/task")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Run = require("../../lib/run")

local FILE = "zz-spec-chainbackground"

local function quiet<T>(f: () -> T): T
	local was = Run.expectingFailure
	local wasOut = Run.out
	Run.expectingFailure = true
	Run.out = function() end
	local ok, r = pcall(f)
	Run.expectingFailure = was
	Run.out = wasOut
	if not ok then
		error(r, 0)
	end
	return r
end

local function cleanup()
	if fs.isFile(`.verify/{FILE}.json`) then
		fs.removeFile(`.verify/{FILE}.json`)
	end
end

local function step(name: string, ok: boolean): any
	return { name = name, cmd = "(spec)", exit = if ok then 0 else 1, ok = ok, tail = "", result = nil }
end

return function()
	test.suite("Run.background: a long step starts with the chain", function()
		test.case("it starts before the steps ahead of it and keeps its place in the report", function()
			local wasHook = Run.onFail
			Run.onFail = nil
			local events = {}
			local plan = {
				function()
					table.insert(events, "a")
					task.wait(0.05) -- (a step ahead of it that takes a while: the background one is already running)
					return step("a", true)
				end,
				Run.background(function()
					table.insert(events, "bg start")
					task.wait(0.15)
					table.insert(events, "bg end")
					return step("bg", true)
				end),
				function()
					table.insert(events, "c")
					return step("c", true)
				end,
			}
			local code = quiet(function()
				return Run.chain(FILE, plan, function()
					return Run.CODES.CONTENT
				end, "all green")
			end)
			Run.onFail = wasHook
			check.equal(code, Run.CODES.PASS)
			-- it started before step a ran, and step c waited for it
			check.equal(events[1], "bg start")
			check.equal(events[2], "a")
			check.equal(events[#events], "c")
			local bgEnd = table.find(events, "bg end") or math.huge
			local cAt = table.find(events, "c") or 0
			check.is_true(bgEnd < cAt)
			local report = serde.decode("json", fs.readFile(`.verify/{FILE}.json`))
			check.equal(#report.steps, 3)
			check.equal(report.steps[1].name, "a")
			check.equal(report.steps[2].name, "bg")
			check.equal(report.steps[3].name, "c")
			cleanup()
		end)

		test.case("a background step that fails or crashes is one more red", function()
			local wasHook = Run.onFail
			Run.onFail = nil
			local plan = {
				function()
					return step("a", true)
				end,
				Run.background(function(): any
					error("boom")
				end),
				Run.background(function()
					return step("bg2", false)
				end),
			}
			local code = quiet(function()
				return Run.chain(FILE, plan, function()
					return Run.CODES.CONTENT
				end, "all green", { continue = true })
			end)
			Run.onFail = wasHook
			check.equal(code, Run.CODES.CONTENT)
			local report = serde.decode("json", fs.readFile(`.verify/{FILE}.json`))
			check.equal(#report.steps, 3)
			check.equal(report.steps[2].ok, false)
			check.is_true(string.find(report.steps[2].tail, "boom", 1, true) ~= nil)
			check.equal(report.steps[3].name, "bg2")
			check.equal(report.steps[3].ok, false)
			cleanup()
		end)

		-- (the owner, 2026-11-23: "speed it up with more cores" - kit verify starts its Python lane once the lint gates
		-- pass and joins it LAST, so the content gates run beside it)
		test.case("a lane whose .start sits further down starts THERE and is joined at its own place", function()
			local wasHook = Run.onFail
			Run.onFail = nil
			local events = {}
			local lane = Run.background(function()
				table.insert(events, "bg start")
				task.wait(0.1)
				table.insert(events, "bg end")
				return step("bg", true)
			end)
			local plan = {
				function()
					table.insert(events, "a")
					return step("a", true)
				end,
				lane.start,
				function()
					table.insert(events, "c")
					return step("c", true)
				end,
				lane,
			}
			local code = quiet(function()
				return Run.chain(FILE, plan, function()
					return Run.CODES.CONTENT
				end, "all green")
			end)
			Run.onFail = wasHook
			check.equal(code, Run.CODES.PASS)
			check.equal(events[1], "a") -- (it did NOT start with the chain)
			check.equal(events[2], "bg start")
			check.equal(events[3], "c") -- (c ran beside it, not after it)
			check.equal(events[4], "bg end")
			local report = serde.decode("json", fs.readFile(`.verify/{FILE}.json`))
			check.equal(#report.steps, 3) -- (the .start is no step)
			check.equal(report.steps[3].name, "bg")
			check.is_true(type(report.steps[3].seconds) == "number" and report.steps[3].seconds >= 0.09)
			cleanup()
		end)

		test.case("a chain that stops at a failure waits for its running lane and reports it too", function()
			local wasHook = Run.onFail
			Run.onFail = nil
			local events = {}
			local lane = Run.background(function()
				task.wait(0.1)
				table.insert(events, "bg end")
				return step("bg", false)
			end)
			local never = Run.background(function()
				table.insert(events, "never")
				return step("never", true)
			end)
			local plan = {
				lane.start,
				function()
					return step("b", false)
				end,
				never.start, -- (past the failure: never started, never waited for)
				lane,
				never,
			}
			local code = quiet(function()
				return Run.chain(FILE, plan, function(s)
					return if s.name == "b" then Run.CODES.LINT else Run.CODES.CONTENT
				end, "all green")
			end)
			Run.onFail = wasHook
			check.equal(code, Run.CODES.LINT) -- (the first failure leads)
			check.equal(events[1], "bg end") -- (the report waited for it)
			check.is_true(table.find(events, "never") == nil)
			local report = serde.decode("json", fs.readFile(`.verify/{FILE}.json`))
			check.equal(#report.steps, 2)
			check.equal(report.steps[1].name, "b")
			check.equal(report.steps[2].name, "bg")
			check.equal(report.steps[2].ok, false)
			cleanup()
		end)
	end)
end

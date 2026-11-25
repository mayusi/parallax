-- chaincontinue.spec.luau (kit) — Run.chain's `continue` option (`kit verify --continue`, owner 2026-11-20: "a single
-- run reports all failing gates at once instead of stopping at the first red"): without it the first red stops the
-- chain (the old behaviour, unchanged); with it every step runs, the report names every red, the FIRST red's code
-- leads, and a step that crashes is one more red instead of the end of the run.
local fs = require("@lune/fs")
local serde = require("@lune/serde")

local frk = require("../frk")
local test, check = frk.test, frk.check

local Run = require("../../lib/run")

local FILE = "zz-spec-chaincontinue"

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

return function()
	test.suite("Run.chain --continue: every red at once", function()
		test.case("without continue the first red stops the chain; with it every step runs", function()
			local wasHook = Run.onFail
			Run.onFail = nil
			local ran = {}
			local function step(name: string, ok: boolean, code: number?): () -> any
				return function()
					table.insert(ran, name)
					return {
						name = name,
						cmd = "(spec)",
						exit = if ok then 0 else (code or 1),
						ok = ok,
						tail = "",
						result = if ok then nil else { next_action = `fix {name}` },
					}
				end
			end
			local codeFor = function(s: any): number
				return if s.name == "b" then Run.CODES.UNIT else Run.CODES.CONTENT
			end
			local plan = { step("a", true), step("b", false), step("c", true), step("d", false) }

			local code = quiet(function()
				return Run.chain(FILE, plan, codeFor, "all green")
			end)
			check.equal(table.concat(ran, ","), "a,b") -- (stopped at the first red)
			check.equal(code, Run.CODES.UNIT)

			ran = {}
			code = quiet(function()
				return Run.chain(FILE, plan, codeFor, "all green", { continue = true })
			end)
			check.equal(table.concat(ran, ","), "a,b,c,d") -- (every step ran)
			check.equal(code, Run.CODES.UNIT) -- (the FIRST red's code leads)
			local report = serde.decode("json", fs.readFile(`.verify/{FILE}.json`))
			check.truthy(string.find(report.summary, "2 step(s) failed: b, d", 1, true) ~= nil)
			check.truthy(string.find(report.next_action, "[b] fix b", 1, true) ~= nil)
			check.truthy(string.find(report.next_action, "[d] fix d", 1, true) ~= nil)

			-- a crashing step under continue is one more red, and the steps after it still run
			ran = {}
			code = quiet(function()
				return Run.chain(FILE, {
					step("a", true),
					function()
						error("boom")
					end,
					step("c", true),
				}, codeFor, "all green", { continue = true })
			end)
			check.equal(table.concat(ran, ","), "a,c")
			check.truthy(code ~= Run.CODES.PASS)

			-- all green under continue is the plain pass
			code = quiet(function()
				return Run.chain(FILE, { step("a", true) }, codeFor, "all green", { continue = true })
			end)
			check.equal(code, Run.CODES.PASS)
			Run.onFail = wasHook
			cleanup()
		end)
	end)
end

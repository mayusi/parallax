-- cli.spec.luau (kit) — the dispatcher's safety rules: `--help` / `-h` on any command prints its usage and NEVER
-- runs it (kit upload --help once started a real full upload), and the before-hook runs first without blocking.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Cli = require("../../lib/cli")

return function()
	test.suite("cli: --help never runs a command", function()
		test.case("--help and -h return before the command body", function()
			local ran = 0
			Cli.command("kit", "_spec_danger", "_spec_danger [--x]", "a command that must not run on --help", function()
				ran += 1
				return 0
			end)
			check.equal(Cli.dispatch({ "_spec_danger", "--help" }), 0)
			check.equal(Cli.dispatch({ "_spec_danger", "--x", "-h" }), 0)
			check.equal(ran, 0)
			check.equal(Cli.dispatch({ "_spec_danger", "--x" }), 0)
			check.equal(ran, 1)
		end)
		test.case("a failing before-hook never blocks the command", function()
			local ran = 0
			Cli.command("kit", "_spec_hooked", "_spec_hooked", "runs despite a broken hook", function()
				ran += 1
				return 0
			end)
			local saved = Cli.before
			Cli.before = function()
				error("hook broke")
			end
			check.equal(Cli.dispatch({ "_spec_hooked" }), 0)
			Cli.before = saved
			check.equal(ran, 1)
		end)
	end)
end

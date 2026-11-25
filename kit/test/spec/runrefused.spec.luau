-- runrefused.spec.luau (kit) — a script that refused its ARGUMENTS is not a crash (kit/lib/run.luau Run.refused; the
-- V3 list's kit hygiene: `kit ui direct` "crashed" when a sub-command was given no name): argparse's own error line,
-- for the program and for a sub-command's parser, is read back as the refusal; anything else stays a crash.
local frk = require("../frk")
local test, check = frk.test, frk.check

local Run = require("../../lib/run")

return function()
	test.suite("run: wrong arguments are said, not called a crash", function()
		test.case("the program's own parser and a sub-command's", function()
			check.equal(
				Run.refused(
					2,
					"usage: direct.py [-h] {new,check}\ndirect.py: error: argument cmd: invalid choice: 'X'\n"
				),
				"argument cmd: invalid choice: 'X'"
			)
			check.equal(
				Run.refused(
					2,
					"usage: direct.py board [-h] [--game GAME] name\ndirect.py board: error: the following arguments are required: name\n"
				),
				"the following arguments are required: name"
			)
			check.equal(
				Run.refused(
					2,
					"usage: run.py vision-plate [-h]\nrun.py vision-plate: error: unrecognized arguments: --x\r\n"
				),
				"unrecognized arguments: --x"
			)
		end)
		test.case("a crash stays a crash", function()
			check.equal(Run.refused(1, "direct.py board: error: the following arguments are required: name"), nil)
			check.equal(Run.refused(2, "Traceback (most recent call last):\n  KeyError: 'x'\n"), nil)
			check.equal(Run.refused(2, nil), nil)
			check.equal(Run.refused(nil, "direct.py: error: x"), nil)
		end)
	end)
end

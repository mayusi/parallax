-- frk.luau — single import point for frktest. In any spec:
--   local frk = require("@kit/test/frk")      (project specs; alias from .luaurc)
--   local test, check = frk.test, frk.check
local frktest = require("../../DevPackages/_Index/itsfrank_frktest@0.0.2/frktest/src/frktest")

return {
	frktest = frktest,
	test = frktest.test,
	check = frktest.assert.check,
	require = frktest.assert.require,
}

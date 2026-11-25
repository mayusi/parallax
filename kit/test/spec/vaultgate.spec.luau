-- vaultgate.spec.luau (kit) — the department page before a pipeline's own commands (kit/lib/vaultgate.luau):
-- every pipeline's commands map to their department, lookups and unrelated commands get no page, and the page
-- shows once per window, not on every call.
local fs = require("@lune/fs")

local frk = require("../frk")
local test, check = frk.test, frk.check

local VaultGate = require("../../lib/vaultgate")

return function()
	test.suite("vaultgate: which commands show a department page", function()
		test.case("each pipeline's own commands map to its department", function()
			check.equal(VaultGate.deptFor("ui", { "plan", "FieldHud" }), "ui")
			check.equal(VaultGate.deptFor("vfx", { "chart", "x" }), "vfx")
			check.equal(VaultGate.deptFor("anim", { "new", "X" }), "anim")
			check.equal(VaultGate.deptFor("world", { "check", "W" }), "world")
			check.equal(VaultGate.deptFor("sfx", { "sheet", "s" }), "sfx")
			check.equal(VaultGate.deptFor("cad", { "check", "a" }), "3d")
			check.equal(VaultGate.deptFor("trace", { "a" }), "3d")
			check.equal(VaultGate.deptFor("net", {}), "code")
			check.equal(VaultGate.deptFor("playtest", { "bundle", "p" }), "qa")
		end)
		test.case("lookups, and commands that print the page themselves or belong to no pipeline, get none", function()
			check.equal(VaultGate.deptFor("ui", { "find", "bar" }), nil)
			check.equal(VaultGate.deptFor("vfx", { "list" }), nil)
			check.equal(VaultGate.deptFor("ui", { "--help" }), nil)
			check.equal(VaultGate.deptFor("plan", { "glock" }), nil) -- kit plan prints it itself
			check.equal(VaultGate.deptFor("new", { "vfx", "x" }), nil) -- kit new prints it itself
			check.equal(VaultGate.deptFor("status", {}), nil)
			check.equal(VaultGate.deptFor("verify", {}), nil)
		end)
	end)

	test.suite("vaultgate: once per window", function()
		test.case("the first call is due, the next one inside the window is not, a zero window always is", function()
			local saved = VaultGate.STAMP
			VaultGate.STAMP = "kit/selftest/vault/_seen_tmp.json"
			if fs.isFile(VaultGate.STAMP) then
				fs.removeFile(VaultGate.STAMP)
			end
			local ok, err = pcall(function()
				check.truthy(VaultGate.due("ui", 120))
				check.falsy(VaultGate.due("ui", 120))
				check.truthy(VaultGate.due("vfx", 120)) -- another department has its own window
				check.truthy(VaultGate.due("ui", 0))
			end)
			if fs.isFile(VaultGate.STAMP) then
				fs.removeFile(VaultGate.STAMP)
			end
			VaultGate.STAMP = saved
			if not ok then
				error(err)
			end
		end)
	end)
end

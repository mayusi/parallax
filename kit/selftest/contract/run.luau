--!strict
-- run.luau — the `kit contract` self-test (LIMITATIONS_FIXES_V4 §13.8 item 1): the good contract (written from
-- kit/selftest/contract/fixture/ by `kit contract new`) must pass `check`, and the bad one (the same contract with its
-- opener's hit frame moved, as if the anim lane retimed the clip after it was signed) must be caught BY NAME.
--   lune run kit/selftest/contract/run              both (exit 0 when the good passes and the bad is caught)
--   lune run kit/selftest/contract/run good | bad   one; prints the check's own JSON verdict line
-- kit selftest runs the same two through ContractCmd.step (kit/cmd/contract.luau).
local process = require("@lune/process")
local serde = require("@lune/serde")

local ContractCmd = require("../../cmd/contract")
local Run = require("../../lib/run")

local GOOD, BAD = "kit/selftest/contract/good", "kit/selftest/contract/bad"
local NEEDLE = "movesTimeline.hitFrame: 20 -> 18"

local which = process.args[1]
if which == "good" or which == "bad" then
	Run.expectingFailure = which == "bad"
	local step = ContractCmd.step(if which == "good" then GOOD else BAD)
	local r = step.result or {}
	print(serde.encode("json", { status = r.status, summary = r.summary, next_action = r.next_action }))
	process.exit(if step.ok then 0 else 1)
end

local good = ContractCmd.step(GOOD)
Run.expectingFailure = true
local bad = ContractCmd.step(BAD)
Run.expectingFailure = false
local caught = not bad.ok and string.find(tostring(bad.result and bad.result.summary), NEEDLE, 1, true) ~= nil
print(`[{if good.ok then "ok" else "FAIL"}] contract (a good contract passes): {tostring(good.result.summary)}`)
print(
	`[{if caught then "caught" else "MISSED"}] contract (a moved hit frame): {tostring(
		bad.result and bad.result.summary
	)}`
)
local ok = good.ok and caught
print(serde.encode("json", {
	status = if ok then "pass" else "fail",
	summary = if ok
		then "contract self-test: the good contract passes, the moved hit frame is caught by name"
		else "contract self-test: " .. (if good.ok
			then "the bad contract was NOT caught"
			else "the good contract failed"),
	next_action = if ok then "none" else "fix kit/lib/contract.luau or kit/cmd/contract.luau - never the fixture",
}))
process.exit(if ok then 0 else 1)

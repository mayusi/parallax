-- hudsize.luau — a game-code HUD's size on screen against its reference (kit/lib/hudsize.luau says how); one JSON
-- line out (status / summary / next_action / blocks), exit 1 on a fail. The owner's sg_hud5 3/10 (2026-10-29):
-- "what the hell, I told you not this small".
--
--   lune run kit/ui/hudsize <contract.json> [--code <the HUD's .luau>]
--   (--code replaces the contract's "code": the selftest's frozen copies of the real files)
local process = require("@lune/process")
local serde = require("@lune/serde")

local HudSize = require("../lib/hudsize")

local contractPath: string? = nil
local code: string? = nil
local i = 1
while i <= #process.args do
	local a = process.args[i]
	if a == "--code" and process.args[i + 1] then
		code = process.args[i + 1]
		i += 2
	else
		if not contractPath then
			contractPath = a
		end
		i += 1
	end
end

if not contractPath then
	print(serde.encode("json", {
		schema = 1,
		status = "fail",
		summary = "hud size: name a contract (<root>assets/ui/huds/<Hud>.json)",
		next_action = "lune run kit/ui/hudsize games/<Game>/assets/ui/huds/<Hud>.json",
	}))
	process.exit(1)
end

local r = HudSize.run(contractPath :: string, code)
print(serde.encode("json", {
	schema = 1,
	status = if r.ok then "pass" else "fail",
	summary = r.summary,
	next_action = r.next_action,
	blocks = r.blocks,
	notes = r.notes,
}))
process.exit(if r.ok then 0 else 1)

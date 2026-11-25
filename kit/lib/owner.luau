-- owner.luau — some acts are the OWNER's alone: a grade (it sets every project's quality scale) and a floor lowered or
-- re-based onto a different build (it lets a worse model pass). They are confirmed with the owner's own keystrokes at
-- a real terminal. An agent's shell has none — stdio.prompt fails with "not a terminal", piped input or not — so a
-- model can propose the act, or start the command in the owner's terminal, but only the owner completes it.
local stdio = require("@lune/stdio")

local Owner = {}

-- ask the owner to type `expect` -> (true) | (false, why): no terminal, or not confirmed
function Owner.confirm(question: string, expect: string): (boolean, string?)
	-- (the exact characters to type, quoted: "type 85 to confirm" was read as "type the word confirm", 2026-10-10)
	local ok, answer = pcall(
		stdio.prompt,
		"text",
		`{question} — to confirm, type exactly "{expect}" and press Enter (anything else cancels)`
	)
	if not ok then
		return false,
			"this is the OWNER's act, confirmed at a real terminal, and this shell has none (an agent's shell)"
	end
	local typed = string.match(tostring(answer), "^%s*(.-)%s*$") or ""
	if string.lower(typed) ~= string.lower(expect) then
		return false, "not confirmed (the answer did not match)"
	end
	return true, nil
end

return Owner
